from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

import numpy as np
from scipy import signal as scipy_signal

from .catalog import METHOD_BY_ID
from .models import MethodResult, PartialMethodResult, ProcessStep, SignalRecord
from .signal_ops import (
    butter_filter,
    butterworth_order_from_specs,
    derivative,
    effective_cutoff,
    fft_spectrum,
    integrate_signal,
    polynomial_trend,
)


_STEP_TRACE: ContextVar[list[ProcessStep] | None] = ContextVar("method_step_trace", default=None)
_STEP_CALLBACK: ContextVar[Callable[[ProcessStep], None] | None] = ContextVar(
    "method_step_callback", default=None
)

@dataclass(frozen=True)
class _BunceCandidate:
    score: float
    start: int
    end: int
    leading_score: float
    trailing_score: float
    shoulder_score: float
    peak_score: float
    direction: str
    lift: float
    detected_peak_count: int
    matched_peak_count: int


def _record_step(step: ProcessStep) -> ProcessStep:
    trace = _STEP_TRACE.get()
    if trace is not None:
        trace.append(step)
    callback = _STEP_CALLBACK.get()
    if callback is not None:
        callback(step)
    return step


def _zero_phase(parameters: dict[str, Any]) -> bool:
    return str(parameters.get("filter_phase", "zero_phase")) == "zero_phase"


def _phase_label(zero_phase: bool) -> str:
    return "sin desfase (filtfilt)" if zero_phase else "causal"


def _highpass_parameters(parameters: dict[str, Any], sampling_rate_hz: float) -> tuple[int, float, str]:
    if str(parameters.get("highpass_design", "manual")) == "specifications":
        order, cutoff = butterworth_order_from_specs(
            sampling_rate_hz,
            float(parameters["passband_hz"]),
            float(parameters["stopband_hz"]),
            float(parameters["passband_ripple_db"]),
            float(parameters["stopband_attenuation_db"]),
        )
        return order, cutoff, "buttord"
    order = int(parameters["highpass_order"])
    cutoff = effective_cutoff(float(parameters["highpass_hz"]), sampling_rate_hz)
    return order, cutoff, "manual"


def _step(
    key: str,
    title: str,
    description: str,
    time_s: np.ndarray,
    series: dict[str, np.ndarray],
    y_label: str,
    series_styles: dict[str, str] | None = None,
) -> ProcessStep:
    return _record_step(
        ProcessStep(
            key,
            title,
            description,
            np.asarray(time_s),
            series,
            "Tiempo [s]",
            y_label,
            series_styles or {},
        )
    )


def _explanation(what: str, why: str, interpretation: str, reference: str) -> str:
    return (
        f"Qué muestra: {what}\n"
        f"Por qué se hace: {why}\n"
        f"Cómo interpretarla: {interpretation}\n"
        f"Referencia: {reference}"
    )


def _spectrum_step(
    key: str,
    title: str,
    description: str,
    values: np.ndarray,
    sampling_rate_hz: float,
) -> ProcessStep:
    frequency, amplitude = fft_spectrum(values, sampling_rate_hz)
    return _record_step(
        ProcessStep(
            key,
            title,
            description,
            frequency,
            {"Amplitud": amplitude},
            "Frecuencia [Hz]",
            "Amplitud",
        )
    )


def default_parameters(method_id: str) -> dict[str, Any]:
    return {parameter.key: parameter.default for parameter in METHOD_BY_ID[method_id].parameters}


def _result(
    record: SignalRecord,
    method_id: str,
    parameters: dict[str, Any],
    steps: list[ProcessStep],
    acceleration: np.ndarray,
    velocity: np.ndarray,
    displacement: np.ndarray,
    diagnostics: dict[str, Any],
    started: float,
) -> MethodResult:
    arrays = (acceleration, velocity, displacement)
    if any(np.asarray(array).shape != record.time_s.shape for array in arrays):
        raise RuntimeError("El método produjo una serie con longitud inconsistente.")
    if any(not np.all(np.isfinite(array)) for array in arrays):
        raise RuntimeError("El método produjo valores no finitos.")
    return MethodResult(
        method_id=method_id,
        method_name=METHOD_BY_ID[method_id].name,
        time_s=record.time_s.copy(),
        acceleration_mps2=np.asarray(acceleration, dtype=float),
        velocity_mps=np.asarray(velocity, dtype=float),
        displacement_m=np.asarray(displacement, dtype=float),
        parameters=dict(parameters),
        steps=steps,
        diagnostics=diagnostics,
        elapsed_s=perf_counter() - started,
    )


def _initial_steps(record: SignalRecord) -> list[ProcessStep]:
    return [
        _step(
            "raw_acceleration",
            "Aceleración de entrada",
            "Señal seleccionada, convertida a unidades SI sin corrección.",
            record.time_s,
            {"Original": record.acceleration_mps2},
            "Aceleración [m/s²]",
        ),
        _spectrum_step(
            "raw_spectrum",
            "Espectro de entrada",
            "Espectro unilateral para reconocer la banda de señal y el ruido.",
            record.acceleration_mps2,
            record.sampling_rate_hz,
        ),
    ]


def _run_trifunac_lee(record: SignalRecord, p: dict[str, Any]) -> MethodResult:
    started = perf_counter()
    t, a, fs = record.time_s, record.acceleration_mps2, record.sampling_rate_hz
    low = effective_cutoff(float(p["lowpass_hz"]), fs)
    high = effective_cutoff(float(p["highpass_hz"]), fs)
    zero_phase = _zero_phase(p)
    phase = _phase_label(zero_phase)
    steps = _initial_steps(record)
    a_low = butter_filter(a, fs, low, int(p["lowpass_order"]), "lowpass", zero_phase=zero_phase)
    steps.append(_step("lowpass_acceleration", "Pasa baja en aceleración", f"Butterworth {phase}, orden {int(p['lowpass_order'])}, corte efectivo {low:.4g} Hz.", t, {"Original": a, "Filtrada": a_low}, "Aceleración [m/s²]"))
    a_high = butter_filter(a_low, fs, high, int(p["highpass_order"]), "highpass", zero_phase=zero_phase)
    steps.append(_step("highpass_acceleration", "Pasa alta en aceleración", f"Butterworth {phase}, orden {int(p['highpass_order'])}, corte {high:.4g} Hz.", t, {"Pasa baja": a_low, "Corregida": a_high}, "Aceleración [m/s²]"))
    velocity_raw = integrate_signal(a_high, t, str(p["integration"]))
    steps.append(_step("integrated_velocity", "Primera integración", "Velocidad antes de su corrección de periodo largo.", t, {"Velocidad": velocity_raw}, "Velocidad [m/s]"))
    velocity = butter_filter(velocity_raw, fs, high, int(p["highpass_order"]), "highpass", zero_phase=zero_phase)
    steps.append(_step("highpass_velocity", "Pasa alta en velocidad", "Mismo corte usado para la aceleración.", t, {"Antes": velocity_raw, "Corregida": velocity}, "Velocidad [m/s]"))
    displacement_raw = integrate_signal(velocity, t, str(p["integration"]))
    steps.append(_step("integrated_displacement", "Segunda integración", "Desplazamiento antes de la corrección final.", t, {"Desplazamiento": displacement_raw}, "Desplazamiento [m]"))
    displacement = butter_filter(displacement_raw, fs, high, int(p["highpass_order"]), "highpass", zero_phase=zero_phase)
    steps.append(_step("final_displacement", "Desplazamiento corregido", "Último filtrado pasa alta del método.", t, {"Antes": displacement_raw, "Final": displacement}, "Desplazamiento [m]"))
    return _result(record, "trifunac_lee", p, steps, a_high, velocity, displacement, {"effective_lowpass_hz": low, "effective_highpass_hz": high, "filter_phase": phase}, started)


def _run_chiu(record: SignalRecord, p: dict[str, Any]) -> MethodResult:
    started = perf_counter()
    t, a, fs = record.time_s, record.acceleration_mps2, record.sampling_rate_hz
    steps = _initial_steps(record)
    trend = polynomial_trend(a, t, int(p["acceleration_degree"]))
    adjusted = a - trend
    steps.append(_step("acceleration_fit", "Ajuste de aceleración", "Tendencia por mínimos cuadrados retirada del registro.", t, {"Original": a, "Tendencia": trend, "Ajustada": adjusted}, "Aceleración [m/s²]"))
    zero_phase = _zero_phase(p)
    phase = _phase_label(zero_phase)
    high_order, high, high_design = _highpass_parameters(p, fs)
    filtered = butter_filter(adjusted, fs, high, high_order, "highpass", zero_phase=zero_phase)
    steps.append(_step("highpass_acceleration", "Pasa alta", f"Butterworth {phase}, orden calculado {high_order}, corte {high:.4g} Hz, diseño {high_design}.", t, {"Ajustada": adjusted, "Filtrada": filtered}, "Aceleración [m/s²]"))
    low = None
    if bool(p["use_lowpass"]):
        low = effective_cutoff(float(p["lowpass_hz"]), fs)
        filtered = butter_filter(filtered, fs, low, int(p["lowpass_order"]), "lowpass", zero_phase=zero_phase)
        steps.append(_step("lowpass_acceleration", "Pasa baja", f"Butterworth {phase}, orden {int(p['lowpass_order'])}, corte {low:.4g} Hz.", t, {"Filtrada": filtered}, "Aceleración [m/s²]"))
    velocity_raw = integrate_signal(filtered, t, str(p["integration"]))
    steps.append(_step("integrated_velocity", "Primera integración", "Velocidad antes de retirar la deriva.", t, {"Velocidad": velocity_raw}, "Velocidad [m/s]"))
    correction = str(p["drift_correction"])
    if correction == "velocity":
        velocity_trend = polynomial_trend(velocity_raw, t, int(p["final_degree"]))
        velocity = velocity_raw - velocity_trend
        steps.append(_step("velocity_fit", "Corrección en velocidad", "Ajuste por mínimos cuadrados previo a la segunda integración.", t, {"Velocidad": velocity_raw, "Tendencia": velocity_trend, "Corregida": velocity}, "Velocidad [m/s]"))
        displacement = integrate_signal(velocity, t, str(p["integration"]))
        steps.append(_step("integrated_displacement", "Segunda integración", "Integración de la velocidad corregida, correspondiente al paso 6 de la opción 2 del script MATLAB.", t, {"Desplazamiento": displacement}, "Desplazamiento [m]"))
    else:
        velocity = velocity_raw
        displacement_raw = integrate_signal(velocity, t, str(p["integration"]))
        steps.append(_step("integrated_displacement", "Segunda integración", "Desplazamiento previo al ajuste final de la opción 1.", t, {"Desplazamiento": displacement_raw}, "Desplazamiento [m]"))
        displacement_trend = polynomial_trend(displacement_raw, t, int(p["final_degree"]))
        displacement = displacement_raw - displacement_trend
        steps.append(_step("displacement_fit", "Corrección en desplazamiento", "Ajuste por mínimos cuadrados retirado después de integrar.", t, {"Antes": displacement_raw, "Tendencia": displacement_trend, "Corregido": displacement}, "Desplazamiento [m]"))
    steps.append(_step("final_displacement", "Desplazamiento final", f"Variante Chiu con corrección en {correction}.", t, {"Final": displacement}, "Desplazamiento [m]"))
    return _result(record, "chiu", p, steps, filtered, velocity, displacement, {"effective_highpass_hz": high, "effective_highpass_order": high_order, "highpass_design": high_design, "effective_lowpass_hz": low, "filter_phase": phase, "correction_variant": correction}, started)


def _run_converse_brady(record: SignalRecord, p: dict[str, Any]) -> MethodResult:
    started = perf_counter()
    t, a, fs = record.time_s, record.acceleration_mps2, record.sampling_rate_hz
    steps = _initial_steps(record)
    baseline = str(p["baseline"])
    if baseline == "linear":
        trend = polynomial_trend(a, t, 1)
    elif baseline == "mean":
        trend = np.full_like(a, float(np.mean(a)))
    else:
        trend = np.full_like(a, float(p["baseline_constant"]))
    adjusted = a - trend
    zero_phase = _zero_phase(p)
    phase = _phase_label(zero_phase)
    steps.append(_step("baseline", "Corrección de línea base", f"Modo seleccionado: {baseline}.", t, {"Original": a, "Línea base": trend, "Corregida": adjusted}, "Aceleración [m/s²]"))
    low = effective_cutoff(float(p["lowpass_hz"]), fs)
    initial_pad = float(p["initial_pad_s"])
    initial_pad_samples = max(0, int(round(initial_pad * fs)))
    initially_padded = np.pad(adjusted, (initial_pad_samples, initial_pad_samples), mode="constant")
    initial_time = (np.arange(initially_padded.size) - initial_pad_samples) / fs
    steps.append(
        _step(
            "initial_padding",
            "Pad inicial",
            f"Se añadieron {initial_pad_samples} ceros por extremo antes del pasa baja.",
            initial_time,
            {"Aceleración con pad": initially_padded},
            "Aceleración [m/s²]",
        )
    )
    low_filtered = butter_filter(
        initially_padded,
        fs,
        low,
        int(p["lowpass_order"]),
        "lowpass",
        zero_phase=zero_phase,
    )
    steps.append(
        _step(
            "lowpass",
            "Pasa baja",
            f"Butterworth {phase}, orden {int(p['lowpass_order'])}, corte {low:.4g} Hz; se conserva el pad.",
            initial_time,
            {"Antes": initially_padded, "Pasa baja": low_filtered},
            "Aceleración [m/s²]",
        )
    )
    high_order, high, high_design = _highpass_parameters(p, fs)
    nroll = max(0.5, high_order / 2.0)
    requested_pad = max(initial_pad, float(p["high_pad_factor"]) * nroll / high)
    total_pad_samples = max(initial_pad_samples, int(np.floor(requested_pad * fs)))
    if total_pad_samples > 2_000_000:
        raise ValueError(
            "El pad calculado supera dos millones de muestras por extremo; "
            "revisa la frecuencia pasa alta para evitar un consumo excesivo de memoria."
        )
    additional_pad_samples = total_pad_samples - initial_pad_samples
    fully_padded = np.pad(low_filtered, (additional_pad_samples, additional_pad_samples), mode="constant")
    padded_time = (np.arange(fully_padded.size) - total_pad_samples) / fs
    steps.append(
        _step(
            "extended_padding",
            "Pad extendido",
            f"Pad total de {total_pad_samples / fs:.3f} s por extremo antes del pasa alta.",
            padded_time,
            {"Aceleración con pad": fully_padded},
            "Aceleración [m/s²]",
        )
    )
    filtered_padded = butter_filter(
        fully_padded,
        fs,
        high,
        high_order,
        "highpass",
        zero_phase=zero_phase,
    )
    steps.append(
        _step(
            "highpass",
            "Pasa alta",
            f"Butterworth {phase}, orden {high_order}, corte {high:.4g} Hz, diseño {high_design}.",
            padded_time,
            {"Antes": fully_padded, "Banda corregida": filtered_padded},
            "Aceleración [m/s²]",
        )
    )
    velocity_padded = integrate_signal(filtered_padded, padded_time, str(p["integration"]))
    displacement_padded = integrate_signal(velocity_padded, padded_time, str(p["integration"]))
    steps.append(_step("velocity", "Primera integración", "El pad se conserva durante la integración.", padded_time, {"Velocidad": velocity_padded}, "Velocidad [m/s]"))
    steps.append(_step("padded_displacement", "Segunda integración con pad", "Desplazamiento antes de retirar los pads de procesamiento.", padded_time, {"Desplazamiento": displacement_padded}, "Desplazamiento [m]"))
    original_slice = slice(total_pad_samples, total_pad_samples + t.size)
    filtered = filtered_padded[original_slice]
    velocity = velocity_padded[original_slice]
    displacement = displacement_padded[original_slice]
    steps.append(_step("final_displacement", "Desplazamiento final", "Tramo correspondiente al registro original después de conservar los pads durante la doble integración.", t, {"Desplazamiento": displacement}, "Desplazamiento [m]"))
    return _result(record, "converse_brady", p, steps, filtered, velocity, displacement, {"effective_lowpass_hz": low, "effective_highpass_hz": high, "effective_highpass_order": high_order, "highpass_design": high_design, "filter_phase": phase, "pad_seconds": total_pad_samples / fs, "pad_samples": total_pad_samples, "additional_pad_samples": additional_pad_samples}, started)


def _run_boore(record: SignalRecord, p: dict[str, Any]) -> MethodResult:
    started = perf_counter()
    t, a, fs = record.time_s, record.acceleration_mps2, record.sampling_rate_hz
    steps = _initial_steps(record)
    arrival = min(max(float(p["arrival_s"]), float(t[1])), float(t[-2]))
    arrival_index = max(2, int(np.searchsorted(t, arrival)))
    pre_mean = float(np.mean(a[:arrival_index]))
    zero_corrected = a - pre_mean
    steps.append(_step("zero_order", "Corrección de orden cero", f"Media preevento hasta {arrival:.3f} s: {pre_mean:.5g} m/s².", t, {"Original": a, "Corregida": zero_corrected}, "Aceleración [m/s²]"))
    velocity_initial = integrate_signal(zero_corrected, t, str(p["integration"]))
    steps.append(_step("initial_velocity", "Velocidad inicial", "Integración usada para observar y ajustar la deriva.", t, {"Velocidad": velocity_initial}, "Velocidad [m/s]"))
    tau = t[arrival_index:] - t[arrival_index]
    degree = int(p["velocity_degree"])
    design = np.column_stack([tau ** power for power in range(1, degree + 1)])
    coefficients, *_ = np.linalg.lstsq(design, velocity_initial[arrival_index:], rcond=None)
    fit_segment = design @ coefficients
    velocity_fit = np.zeros_like(velocity_initial)
    velocity_fit[arrival_index:] = fit_segment
    correction = np.zeros_like(a)
    correction[arrival_index:] = sum(
        power * coefficients[power - 1] * tau ** (power - 1)
        for power in range(1, degree + 1)
    )
    adjusted = zero_corrected - correction
    steps.append(_step("velocity_fit", "Ajuste restringido de velocidad", "El polinomio pasa por cero en el tiempo de arribo.", t, {"Velocidad": velocity_initial, "Ajuste": velocity_fit}, "Velocidad [m/s]"))
    steps.append(_step("acceleration_correction", "Derivada del ajuste", "La derivada del polinomio se sustrae de la aceleración.", t, {"Orden cero": zero_corrected, "Corrección": correction, "Ajustada": adjusted}, "Aceleración [m/s²]"))
    high = None
    if bool(p["use_highpass"]):
        high = effective_cutoff(float(p["highpass_hz"]), fs)
        zero_phase = _zero_phase(p)
        adjusted = butter_filter(
            adjusted,
            fs,
            high,
            int(p["highpass_order"]),
            "highpass",
            zero_phase=zero_phase,
        )
        steps.append(_step("optional_highpass", "Pasa alta opcional", f"Butterworth {_phase_label(zero_phase)}, orden {int(p['highpass_order'])}, corte {high:.4g} Hz.", t, {"Filtrada": adjusted}, "Aceleración [m/s²]"))
    velocity = integrate_signal(adjusted, t, str(p["integration"]))
    displacement = integrate_signal(velocity, t, str(p["integration"]))
    steps.append(_step("final_velocity", "Velocidad final", "Integración de la aceleración corregida.", t, {"Velocidad": velocity}, "Velocidad [m/s]"))
    steps.append(_step("final_displacement", "Desplazamiento final", "Segunda integración; puede conservar un residual no nulo.", t, {"Desplazamiento": displacement}, "Desplazamiento [m]"))
    return _result(record, "boore", p, steps, adjusted, velocity, displacement, {"arrival_s": arrival, "pre_event_mean_mps2": pre_mean, "effective_highpass_hz": high}, started)


def _fit_bilinear(time_s: np.ndarray, values: np.ndarray, breakpoint_s: float) -> tuple[np.ndarray, float]:
    breakpoint = min(max(float(breakpoint_s), float(time_s[1])), float(time_s[-2]))
    breakpoint_value = float(np.interp(breakpoint, time_s, values))
    fit = np.interp(
        time_s,
        [float(time_s[0]), breakpoint, float(time_s[-1])],
        [float(values[0]), breakpoint_value, float(values[-1])],
    )
    return fit, float(np.mean(np.square(values - fit)))


def _run_darragh(record: SignalRecord, p: dict[str, Any]) -> MethodResult:
    started = perf_counter()
    t, a, fs = record.time_s, record.acceleration_mps2, record.sampling_rate_hz
    steps = _initial_steps(record)
    velocity_initial = integrate_signal(a, t, str(p["integration"]))
    steps.append(_step("initial_velocity", "Primera integración", "Velocidad sin corrección de línea base.", t, {"Velocidad": velocity_initial}, "Velocidad [m/s]"))
    start_s = min(max(float(p["fit_start_s"]), float(t[0])), float(t[-3]))
    start = int(np.searchsorted(t, start_s))
    ts, vs = t[start:], velocity_initial[start:]
    candidates: dict[str, tuple[np.ndarray, float, float | None]] = {}
    for name, degree in (("linear", 1), ("quadratic", 2)):
        coefficients = np.polyfit(ts - ts[0], vs, degree)
        fit = np.polyval(coefficients, ts - ts[0])
        candidates[name] = (fit, float(np.mean(np.square(vs - fit))), None)
    requested_break = float(p["breakpoint_s"])
    if ts.size < 8:
        breaks = np.array([float(ts[len(ts) // 2])])
    elif requested_break > start_s:
        breaks = np.array([min(requested_break, float(ts[-2]))])
    else:
        breaks = np.linspace(float(ts[2]), float(ts[-3]), min(30, max(6, ts.size // 20)))
    bilinear_options = [(*_fit_bilinear(ts, vs, point), point) for point in breaks]
    bilinear_fit, bilinear_error, selected_break = min(bilinear_options, key=lambda item: item[1])
    candidates["bilinear"] = (bilinear_fit, bilinear_error, float(selected_break))
    requested = str(p["fit_type"])
    selected = min(candidates, key=lambda name: candidates[name][1]) if requested == "auto" else requested
    fit_segment, fit_error, selected_break = candidates[selected]
    velocity_fit = np.full_like(velocity_initial, float(fit_segment[0]))
    velocity_fit[start:] = fit_segment
    correction = derivative(velocity_fit, t)
    correction[:start] = 0.0
    adjusted = a - correction
    steps.append(_step("velocity_models", "Modelos de línea base", f"Forma seleccionada: {selected}; error medio cuadrático {fit_error:.4g}.", t, {"Velocidad": velocity_initial, "Ajuste": velocity_fit}, "Velocidad [m/s]"))
    steps.append(_step("acceleration_correction", "Corrección de aceleración", "Se deriva el ajuste elegido y se sustrae del registro original.", t, {"Original": a, "Derivada": correction, "Corregida": adjusted}, "Aceleración [m/s²]"))
    low = None
    if bool(p["use_lowpass"]):
        low = effective_cutoff(float(p["lowpass_hz"]), fs)
        zero_phase = _zero_phase(p)
        adjusted = butter_filter(adjusted, fs, low, int(p["lowpass_order"]), "lowpass", zero_phase=zero_phase)
        steps.append(_step("lowpass", "Pasa baja", f"Butterworth {_phase_label(zero_phase)}, orden {int(p['lowpass_order'])}, corte {low:.4g} Hz.", t, {"Filtrada": adjusted}, "Aceleración [m/s²]"))
    velocity = integrate_signal(adjusted, t, str(p["integration"]))
    displacement = integrate_signal(velocity, t, str(p["integration"]))
    steps.append(_step("final_velocity", "Velocidad final", "Integración tras retirar la tendencia seleccionada.", t, {"Velocidad": velocity}, "Velocidad [m/s]"))
    steps.append(_step("final_displacement", "Desplazamiento final", "Resultado PEER equivalente de la implementación.", t, {"Desplazamiento": displacement}, "Desplazamiento [m]"))
    return _result(record, "darragh", p, steps, adjusted, velocity, displacement, {"selected_fit": selected, "fit_mse": fit_error, "breakpoint_s": selected_break, "effective_lowpass_hz": low}, started)


def _run_park(record: SignalRecord, p: dict[str, Any]) -> MethodResult:
    started = perf_counter()
    t, a = record.time_s, record.acceleration_mps2
    steps = _initial_steps(record)
    acceleration_mean = float(np.mean(a))
    adjusted = a - acceleration_mean
    steps.append(_step("acceleration_mean", "Media de aceleración", f"Se sustrae {acceleration_mean:.5g} m/s².", t, {"Original": a, "Corregida": adjusted}, "Aceleración [m/s²]"))
    velocity_raw = integrate_signal(adjusted, t, str(p["integration"]))
    steps.append(_step("integrated_velocity", "Primera integración", "Velocidad antes de corregir su media.", t, {"Velocidad": velocity_raw}, "Velocidad [m/s]"))
    velocity_mean = float(np.mean(velocity_raw))
    velocity = velocity_raw - velocity_mean
    steps.append(_step("velocity_mean", "Media de velocidad", f"Se sustrae {velocity_mean:.5g} m/s.", t, {"Antes": velocity_raw, "Corregida": velocity}, "Velocidad [m/s]"))
    displacement = integrate_signal(velocity, t, str(p["integration"]))
    steps.append(_step("final_displacement", "Desplazamiento final", "Segunda integración después de corregir condiciones iniciales.", t, {"Desplazamiento": displacement}, "Desplazamiento [m]"))
    return _result(record, "park", p, steps, adjusted, velocity, displacement, {"acceleration_mean_mps2": acceleration_mean, "velocity_mean_mps": velocity_mean}, started)


def _automatic_load_interval(
    record: SignalRecord,
) -> tuple[float, float, np.ndarray, float]:
    t = record.time_s
    centered = record.acceleration_mps2 - polynomial_trend(record.acceleration_mps2, t, 1)
    window = max(3, int(round(0.10 * record.sampling_rate_hz)))
    kernel = np.full(window, 1.0 / window)
    envelope = np.sqrt(np.convolve(np.square(centered), kernel, mode="same"))
    edge_size = max(4, min(t.size // 5, int(round(record.sampling_rate_hz))))
    edge_values = np.concatenate((envelope[:edge_size], envelope[-edge_size:]))
    edge_median = float(np.median(edge_values))
    edge_mad = float(np.median(np.abs(edge_values - edge_median)))
    threshold = max(edge_median + 6.0 * 1.4826 * edge_mad, 0.08 * float(np.max(envelope)))
    active = np.flatnonzero(envelope > threshold)
    if active.size < 4:
        raise ValueError(
            "No fue posible detectar automáticamente el paso de la carga. "
            "Selecciona límites manuales de entrada y salida."
        )
    half_window = max(1, window // 2)
    start = max(2, int(active[0]) - half_window)
    end = min(t.size - 3, int(active[-1]) + half_window)
    if end <= start:
        raise ValueError("El intervalo de carga detectado no es válido.")
    return float(t[start]), float(t[end]), envelope, threshold


def _parse_increasing_positive_values(value: Any, label: str) -> np.ndarray:
    tokens = [token for token in re.split(r"[,;\s]+", str(value).strip()) if token]
    if not tokens:
        return np.array([], dtype=float)
    try:
        values = np.asarray([float(token) for token in tokens], dtype=float)
    except ValueError as exc:
        raise ValueError(f"{label} deben ser números separados por coma.") from exc
    if np.any(values <= 0.0) or np.any(np.diff(values) <= 0.0):
        raise ValueError(f"{label} deben ser positivos y crecientes.")
    return values


def _parse_expected_peak_offsets(value: Any) -> np.ndarray:
    return _parse_increasing_positive_values(value, "Los tiempos de picos esperados")


def _resolve_train_peak_offsets(
    parameters: dict[str, Any],
    event_start: float,
    event_end: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    if str(parameters["quality_mode"]) != "train":
        return np.array([], dtype=float), {
            "train_peak_source": "disabled",
            "train_timing_basis": "disabled",
        }

    source = str(parameters["train_peak_source"])
    if source == "manual":
        offsets = _parse_expected_peak_offsets(parameters["expected_peak_offsets_s"])
        if offsets.size < 2:
            raise ValueError(
                "El control ferroviario necesita al menos dos recuperaciones P_i esperadas. "
                "Introduce sus tiempos o usa el control básico por hombros."
            )
        diagnostics = {
            "train_peak_source": "manual",
            "train_timing_basis": "manual",
        }
    elif source == "geometry":
        bridge_span = float(parameters["bridge_span_m"])
        sensor_position = float(parameters["sensor_position_m"])
        train_length = float(parameters["train_length_m"])
        if bridge_span <= 0.0 or train_length <= 0.0:
            raise ValueError(
                "Para calcular las recuperaciones por geometría, la luz del puente y la longitud "
                "entre ejes extremos deben ser mayores que cero."
            )
        if sensor_position < 0.0 or sensor_position > bridge_span:
            raise ValueError(
                "La posición del acelerómetro debe estar entre 0 y la luz del puente, "
                "medida desde el apoyo de entrada."
            )
        midpoints = _parse_increasing_positive_values(
            parameters["peak_midpoint_distances_m"],
            "Las distancias de los puntos medios m_i",
        )
        if midpoints.size < 2:
            raise ValueError(
                "El control ferroviario necesita al menos dos puntos medios m_i de recuperación. "
                "Indica sus distancias desde el primer eje o usa el control por hombros."
            )
        if np.any(midpoints >= train_length):
            raise ValueError(
                "Cada punto medio m_i debe quedar entre el primer y el último eje del tren."
            )

        total_crossing_distance = bridge_span + train_length
        distances_to_sensor = midpoints + sensor_position
        event_duration = event_end - event_start
        timing_basis = str(parameters["train_timing_basis"])
        if timing_basis == "event_duration":
            effective_speed = total_crossing_distance / event_duration
            offsets = distances_to_sensor / total_crossing_distance * event_duration
            predicted_duration = event_duration
        elif timing_basis == "speed":
            speed_kmh = float(parameters["train_speed_kmh"])
            if speed_kmh <= 0.0:
                raise ValueError(
                    "La velocidad aproximada debe ser mayor que cero cuando se usa como base temporal."
                )
            effective_speed = speed_kmh / 3.6
            offsets = distances_to_sensor / effective_speed
            predicted_duration = total_crossing_distance / effective_speed
        else:
            raise ValueError(f"Base temporal ferroviaria desconocida: {timing_basis}")

        duration_difference = predicted_duration - event_duration
        diagnostics = {
            "train_peak_source": "geometry",
            "train_timing_basis": timing_basis,
            "bridge_span_m": bridge_span,
            "sensor_position_from_entry_m": sensor_position,
            "train_first_to_last_axle_m": train_length,
            "train_peak_midpoints_m": midpoints.tolist(),
            "train_peak_distances_to_sensor_m": distances_to_sensor.tolist(),
            "train_total_crossing_distance_m": total_crossing_distance,
            "train_effective_speed_mps": float(effective_speed),
            "train_effective_speed_kmh": float(effective_speed * 3.6),
            "train_predicted_passage_s": float(predicted_duration),
            "train_observed_passage_s": float(event_duration),
            "train_passage_difference_s": float(duration_difference),
        }
    else:
        raise ValueError(f"Origen de picos ferroviarios desconocido: {source}")

    if np.any(offsets >= event_end - event_start):
        raise ValueError(
            "Las recuperaciones calculadas quedan fuera del paso observado. Revisa la dirección de entrada, "
            "la geometría, la velocidad o los límites del evento."
        )
    return offsets, {
        **diagnostics,
        "expected_peak_offsets_s": offsets.tolist(),
    }


def _bunce_extrema_indices(
    time_s: np.ndarray,
    displacement_m: np.ndarray,
    event_start: float,
    event_end: float,
    direction: str,
    minimum_spacing_s: float,
    minimum_width_s: float,
    minimum_prominence_m: float,
    *,
    recoveries: bool,
) -> np.ndarray:
    """Locate BU recovery peaks or load troughs inside the forced interval."""
    event_indices = np.flatnonzero((time_s >= event_start) & (time_s <= event_end))
    if event_indices.size < 3:
        return np.array([], dtype=int)

    event_time = time_s[event_indices]
    sample_step = float(np.median(np.diff(event_time)))
    recovery_orientation = displacement_m if direction == "negative" else -displacement_m
    oriented = recovery_orientation if recoveries else -recovery_orientation
    find_options: dict[str, float | int] = {
        "distance": max(1, int(np.ceil(minimum_spacing_s / sample_step))),
        "prominence": max(0.0, minimum_prominence_m),
    }
    if recoveries:
        find_options["width"] = max(1.0, minimum_width_s / sample_step)
    local_indices, _properties = scipy_signal.find_peaks(
        oriented[event_indices],
        **find_options,
    )
    return event_indices[local_indices]


def _match_bunce_recoveries(
    time_s: np.ndarray,
    detected_indices: np.ndarray,
    expected_times: np.ndarray,
    tolerance_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Associate detected peaks with expected P_i without reusing a detection."""
    possible_matches = sorted(
        (
            (abs(float(time_s[peak_index]) - float(expected_time)), expected_index, peak_index)
            for expected_index, expected_time in enumerate(expected_times)
            for peak_index in detected_indices
            if abs(float(time_s[peak_index]) - float(expected_time)) <= tolerance_s
        ),
        key=lambda item: item[0],
    )
    used_expected: set[int] = set()
    used_peaks: set[int] = set()
    matches: list[tuple[int, int]] = []
    for _distance, expected_index, peak_index in possible_matches:
        peak_index = int(peak_index)
        if expected_index in used_expected or peak_index in used_peaks:
            continue
        used_expected.add(expected_index)
        used_peaks.add(peak_index)
        matches.append((expected_index, peak_index))
    matches.sort(key=lambda item: item[0])
    return (
        np.asarray([item[0] for item in matches], dtype=int),
        np.asarray([item[1] for item in matches], dtype=int),
    )


def _candidate_indices(first: int, last: int, stride: int) -> np.ndarray:
    values = np.arange(first, last + 1, stride, dtype=int)
    if values.size == 0 or values[-1] != last:
        values = np.append(values, last)
    return np.unique(values)


def _run_bunce_bridge(record: SignalRecord, p: dict[str, Any]) -> MethodResult:
    started = perf_counter()
    t, a, fs = record.time_s, record.acceleration_mps2, record.sampling_rate_hz
    steps = [
        _step(
            "raw_acceleration",
            "Aceleración original sin filtrar",
            _explanation(
                "el canal seleccionado en unidades SI, exactamente como entra al método.",
                "BU 2023 evita filtros para no depender de frecuencias de corte capaces de deformar la respuesta cuasiestática.",
                "comprueba que existan reposo antes y después del paso, que no haya saturación y que la polaridad sea coherente con la flecha esperada.",
                "Bunce et al. (2023), Secciones 1.4 y 2; Figuras 1(a), 2 y 15(a).",
            ),
            t,
            {"Aceleración original": a},
            "Aceleración [m/s²]",
        ),
        _spectrum_step(
            "raw_spectrum",
            "Espectro diagnóstico de entrada",
            _explanation(
                "la amplitud de las componentes de frecuencia presentes en la aceleración.",
                "es una ayuda de DESP Studio para reconocer ruido de baja frecuencia, aunque el artículo no usa el espectro para filtrar ni clasificar ventanas.",
                "energía muy cerca de 0 Hz anticipa una gran sensibilidad de la doble integración; no debe eliminarse automáticamente porque puede contener respuesta física.",
                "Vista complementaria de la aplicación; BU 2023 procesa la aceleración sin filtrar.",
            ),
            a,
            fs,
        ),
    ]
    if str(p["event_mode"]) == "automatic":
        event_start, event_end, event_envelope, event_threshold = _automatic_load_interval(record)
        event_source = "detección auxiliar por energía"
        steps.append(
            _step(
                "event_detection",
                "Detección auxiliar del paso",
                _explanation(
                    "la envolvente RMS de 0.1 s y el umbral robusto usados para proponer entrada y salida.",
                    "el algoritmo publicado necesita conocer el tramo forzado, pero no prescribe esta detección automática; DESP la ofrece para iniciar la revisión.",
                    "la envolvente debe superar claramente el umbral durante el paso. Si incluye actividad ajena al tren, cambia a límites manuales.",
                    "Ayuda propia de DESP Studio; los límites del evento son un insumo de BU 2023.",
                ),
                t,
                {
                    "Envolvente RMS": event_envelope,
                    "Umbral": np.full_like(t, event_threshold),
                },
                "Aceleración RMS [m/s²]",
                {"Umbral": "dashed"},
            )
        )
    else:
        event_start = float(p["event_start_s"])
        event_end = float(p["event_end_s"])
        event_source = "límites del analista"

    sample_step = float(np.median(np.diff(t)))
    if event_start < float(t[2]) or event_end > float(t[-3]) or event_end <= event_start:
        raise ValueError(
            "La entrada y salida deben dejar muestras descargadas antes y después del paso. "
            f"Para esta señal usa valores dentro de {t[2]:.4g}-{t[-3]:.4g} s."
        )
    event_mask = (t >= event_start) & (t <= event_end)
    event_indicator = np.zeros_like(a)
    event_indicator[event_mask] = max(float(np.max(np.abs(a))) * 0.15, np.finfo(float).eps)
    steps.append(
        _step(
            "load_interval",
            "Intervalo de respuesta forzada",
            _explanation(
                f"la aceleración y el intervalo entre {event_start:.4g} s y {event_end:.4g} s, definido mediante {event_source}.",
                "separa el paso del vehículo de los tramos descargados que servirán para evaluar los hombros.",
                "la banda debe contener el paso completo; deben quedar muestras de reposo a ambos lados.",
                "Bunce et al. (2023), Sección 2 y Figuras 1(a), 2 y 15(a).",
            ),
            t,
            {"Aceleración": a, "Intervalo de carga": event_indicator},
            "Aceleración [m/s²]",
        )
    )

    zone = float(p["search_zone_s"])
    start_low = int(np.searchsorted(t, max(float(t[0]), event_start - zone), side="left"))
    start_high = int(np.searchsorted(t, event_start - sample_step, side="right") - 1)
    end_low = int(np.searchsorted(t, event_end + sample_step, side="left"))
    end_high = int(np.searchsorted(t, min(float(t[-1]), event_end + zone), side="right") - 1)
    if start_high < start_low or end_high < end_low:
        raise ValueError("Las zonas de búsqueda no contienen hombros suficientes antes y después de la carga.")

    stride = max(1, int(round(float(p["candidate_step_s"]) * fs)))
    start_indices = _candidate_indices(start_low, start_high, stride)
    end_indices = _candidate_indices(end_low, end_high, stride)
    max_candidates = int(p["max_candidates"])
    thinning = 1
    while start_indices.size * end_indices.size > max_candidates:
        thinning += 1
        start_indices = _candidate_indices(start_low, start_high, stride * thinning)
        end_indices = _candidate_indices(end_low, end_high, stride * thinning)

    start_zone = np.full_like(t, np.nan)
    load_zone = np.full_like(t, np.nan)
    end_zone = np.full_like(t, np.nan)
    start_zone[start_low : start_high + 1] = 1.0
    load_zone[event_mask] = 2.0
    end_zone[end_low : end_high + 1] = 3.0
    candidate_count = int(start_indices.size * end_indices.size)
    steps.append(
        _step(
            "search_zones",
            "Zonas de inicio y final",
            _explanation(
                f"las regiones que producen {start_indices.size} inicios y {end_indices.size} finales, combinados en {candidate_count:,} ventanas.",
                "cada par inicio-final genera una recta de tendencia ligeramente distinta; BU busca exhaustivamente la combinación menos sensible a deriva.",
                "el nivel 1 debe quedar antes de la carga, el 2 contiene el paso y el 3 queda después. Más amplitud de zona aumenta diversidad y costo.",
                "Bunce et al. (2023), Sección 2 y Figuras 2 y 3.",
            ),
            t,
            {
                "Inicios candidatos (1)": start_zone,
                "Carga (2)": load_zone,
                "Finales candidatos (3)": end_zone,
            },
            "Zona indicativa",
        )
    )

    configured_direction = str(p["deflection_direction"])
    lift_limit_m = float(p["max_lift_mm"]) / 1000.0
    quality_mode = str(p["quality_mode"])
    expected_offsets, train_diagnostics = _resolve_train_peak_offsets(p, event_start, event_end)
    expected_times = event_start + expected_offsets
    peak_tolerance = float(p["peak_tolerance_s"])
    minimum_peak_spacing = float(p["minimum_peak_spacing_s"])
    minimum_peak_width = float(p["minimum_peak_width_s"])
    minimum_peak_prominence_m = float(p["minimum_peak_prominence_mm"]) / 1000.0
    integration = str(p["integration"])

    if quality_mode == "train" and expected_times.size:
        expected_on_acceleration = np.full_like(a, np.nan)
        for expected_time in expected_times:
            index = int(np.argmin(np.abs(t - expected_time)))
            expected_on_acceleration[index] = a[index]
        expected_text = ", ".join(f"{value:.3f}" for value in expected_times)
        steps.append(
            _step(
                "expected_train_peaks",
                f"Recuperaciones P_i esperadas ({expected_times.size})",
                _explanation(
                    f"las posiciones temporales P_i previstas sobre la aceleración: {expected_text} s.",
                    "cuando los centros de los huecos entre conjuntos de ejes pasan el sensor, el puente tiende a descargarse y el desplazamiento forma recuperaciones comparables.",
                    f"los puntos son centros de asociación, no máximos medidos. {expected_times.size} recuperaciones P_i pueden separar {expected_times.size + 1} valles de carga T_i; revisa geometría y duración.",
                    "Bunce et al. (2023), Sección 4, Ecuación (1) y Figuras 10, 11 y 15(a).",
                ),
                t,
                {
                    "Aceleración": a,
                    "P_i esperadas": expected_on_acceleration,
                },
                "Aceleración [m/s²]",
                {"P_i esperadas": "points"},
            )
        )

    accepted_candidates: list[_BunceCandidate] = []
    evaluated_candidates: list[_BunceCandidate] = []
    rejected_by_lift = 0
    minimum_lift = {"negative": float("inf"), "positive": float("inf")}
    for start_index in start_indices:
        for end_index in end_indices:
            window_time = t[start_index : end_index + 1]
            local_time = window_time - window_time[0]
            window_acceleration = a[start_index : end_index + 1]
            coefficients = np.polyfit(local_time, window_acceleration, 1)
            corrected = window_acceleration - np.polyval(coefficients, local_time)
            velocity = integrate_signal(corrected, local_time, integration)
            displacement = integrate_signal(velocity, local_time, integration)

            lift_by_direction = {
                "negative": max(0.0, float(np.max(displacement))),
                "positive": max(0.0, float(np.max(-displacement))),
            }
            for candidate_direction, lift in lift_by_direction.items():
                minimum_lift[candidate_direction] = min(minimum_lift[candidate_direction], lift)
            if configured_direction == "automatic":
                negative_excursion = abs(float(np.min(displacement)))
                positive_excursion = max(0.0, float(np.max(displacement)))
                effective_direction = "negative" if negative_excursion >= positive_excursion else "positive"
            else:
                effective_direction = configured_direction
            excessive_lift = lift_by_direction[effective_direction] > lift_limit_m
            if excessive_lift:
                rejected_by_lift += 1

            leading = window_time < event_start
            trailing = window_time > event_end
            if np.count_nonzero(leading) < 2 or np.count_nonzero(trailing) < 2:
                continue
            leading_score = float(np.mean(np.abs(velocity[leading])))
            trailing_score = float(np.mean(np.abs(velocity[trailing])))
            shoulder_count = int(np.count_nonzero(leading) + np.count_nonzero(trailing))
            shoulder_score = float(
                (
                    np.sum(np.abs(velocity[leading]))
                    + np.sum(np.abs(velocity[trailing]))
                )
                / shoulder_count
            )
            peak_score = 0.0
            detected_peak_count = 0
            matched_peak_count = 0
            if (
                quality_mode == "train"
                and expected_times.size >= 2
                and not excessive_lift
            ):
                detected_peak_indices = _bunce_extrema_indices(
                    window_time,
                    displacement,
                    event_start,
                    event_end,
                    effective_direction,
                    minimum_peak_spacing,
                    minimum_peak_width,
                    minimum_peak_prominence_m,
                    recoveries=True,
                )
                _matched_expected, matched_peak_indices = _match_bunce_recoveries(
                    window_time,
                    detected_peak_indices,
                    expected_times,
                    peak_tolerance,
                )
                detected_peak_count = int(detected_peak_indices.size)
                matched_peak_count = int(matched_peak_indices.size)
                if matched_peak_count >= 2:
                    peak_values = displacement[matched_peak_indices]
                    peak_locations = window_time[matched_peak_indices]
                    peak_score = float(
                        np.mean(
                            np.abs(np.diff(peak_values))
                            / np.maximum(np.diff(peak_locations), np.finfo(float).eps)
                        )
                    )
            score = shoulder_score + peak_score
            candidate = _BunceCandidate(
                score=score,
                start=int(start_index),
                end=int(end_index),
                leading_score=leading_score,
                trailing_score=trailing_score,
                shoulder_score=shoulder_score,
                peak_score=peak_score,
                direction=effective_direction,
                lift=lift_by_direction[effective_direction],
                detected_peak_count=detected_peak_count,
                matched_peak_count=matched_peak_count,
            )
            evaluated_candidates.append(candidate)
            if not excessive_lift:
                accepted_candidates.append(candidate)

    if not evaluated_candidates:
        raise ValueError("Las ventanas generadas no contienen hombros suficientes para clasificarlas.")
    lift_control_passed = bool(accepted_candidates)
    quality_warnings: list[str] = []
    if lift_control_passed:
        candidates = list(accepted_candidates)
    else:
        candidates = list(evaluated_candidates)
        best_direction = min(minimum_lift, key=minimum_lift.get)
        observed_mm = minimum_lift[best_direction] * 1000.0
        opposite_direction = "positive" if best_direction == "negative" else "negative"
        opposite_mm = minimum_lift[opposite_direction] * 1000.0
        quality_warnings.append(
            "Ninguna ventana cumplió el control de levantamiento; el resultado continúa como "
            "estimación no validada. "
            f"Mínimos observados: {observed_mm:.3g} mm con flecha {best_direction} y "
            f"{opposite_mm:.3g} mm con la convención opuesta, frente al límite de "
            f"{lift_limit_m * 1000.0:.3g} mm."
        )
    train_peak_control_passed = True
    if quality_mode == "train":
        expected_peak_count = int(expected_times.size)
        complete_candidates = [
            candidate
            for candidate in candidates
            if candidate.matched_peak_count == expected_peak_count
        ]
        train_peak_control_passed = bool(complete_candidates)
        if train_peak_control_passed:
            candidates = complete_candidates
        else:
            best_match_count = max(candidate.matched_peak_count for candidate in candidates)
            quality_warnings.append(
                "Ninguna ventana permitió asociar todas las recuperaciones ferroviarias: "
                f"se esperaban {expected_peak_count} P_i y el mejor candidato asoció "
                f"{best_match_count}. El cálculo continúa como estimación no validada por "
                "el control ferroviario; revisa la agrupación de ejes, la luz, la velocidad "
                "y los parámetros de detección."
            )
            candidates.sort(key=lambda candidate: (-candidate.matched_peak_count, candidate.score))
    if train_peak_control_passed:
        candidates.sort(key=lambda candidate: candidate.score)
    selected_candidate = candidates[0]
    score = selected_candidate.score
    best_start = selected_candidate.start
    best_end = selected_candidate.end
    leading_score = selected_candidate.leading_score
    trailing_score = selected_candidate.trailing_score
    shoulder_score = selected_candidate.shoulder_score
    peak_score = selected_candidate.peak_score
    effective_direction = selected_candidate.direction
    selected_lift = selected_candidate.lift
    window_time = t[best_start : best_end + 1]
    local_time = window_time - window_time[0]
    window_acceleration = a[best_start : best_end + 1]
    coefficients = np.polyfit(local_time, window_acceleration, 1)
    trend = np.polyval(coefficients, local_time)
    corrected = window_acceleration - trend
    velocity = integrate_signal(corrected, local_time, integration)
    displacement = integrate_signal(velocity, local_time, integration)

    ranking_description = (
        f"{len(accepted_candidates):,} ventanas aceptadas y "
        f"{rejected_by_lift:,} fuera del límite de levantamiento."
    )
    if not lift_control_passed:
        ranking_description += " Se clasificaron todas como resultados exploratorios no validados."

    grid_limit = min(2_500, len(evaluated_candidates))
    grid_positions = np.unique(
        np.linspace(0, len(evaluated_candidates) - 1, grid_limit, dtype=int)
    )
    grid_start = np.asarray(
        [t[evaluated_candidates[index].start] for index in grid_positions], dtype=float
    )
    grid_end = np.asarray(
        [t[evaluated_candidates[index].end] for index in grid_positions], dtype=float
    )
    grid_start = np.append(grid_start, t[best_start])
    grid_end = np.append(grid_end, t[best_end])
    selected_window_point = np.full(grid_end.shape, np.nan)
    selected_window_point[-1] = t[best_end]
    steps.append(
        _record_step(
            ProcessStep(
                "candidate_grid",
                "Ventanas de aceleración evaluadas",
                _explanation(
                    f"una muestra de {grid_positions.size:,} pares inicio-final de las {len(evaluated_candidates):,} ventanas evaluadas; la ventana ganadora está destacada.",
                    "visualiza la búsqueda cartesiana que sustituye el ensayo manual de una ventana tras otra.",
                    "cada punto une un inicio descargado del eje horizontal con un final descargado del eje vertical. El destacado es el par que minimiza el indicador tras los controles físicos.",
                    "Bunce et al. (2023), Sección 2 y Figuras 2 y 3.",
                ),
                grid_start,
                {
                    "Ventanas evaluadas": grid_end,
                    "Ventana seleccionada": selected_window_point,
                },
                "Inicio de ventana [s]",
                "Final de ventana [s]",
                {
                    "Ventanas evaluadas": "points",
                    "Ventana seleccionada": "points",
                },
            )
        )
    )

    rank_limit = min(5_000, len(candidates))
    ranked_candidates = candidates[:rank_limit]
    rank_x = np.arange(1, rank_limit + 1, dtype=float)
    rank_series = {
        "Indicador total": np.asarray([item.score for item in ranked_candidates], dtype=float),
        "Hombros combinados": np.asarray(
            [item.shoulder_score for item in ranked_candidates], dtype=float
        ),
        "Hombro inicial": np.asarray(
            [item.leading_score for item in ranked_candidates], dtype=float
        ),
        "Hombro final": np.asarray(
            [item.trailing_score for item in ranked_candidates], dtype=float
        ),
    }
    if quality_mode == "train":
        rank_series["Consistencia entre recuperaciones"] = np.asarray(
            [item.peak_score for item in ranked_candidates], dtype=float
        )
    steps.append(
        _record_step(
            ProcessStep(
                "candidate_ranking",
                "Descomposición del indicador de calidad",
                _explanation(
                    f"los componentes de calidad de los {rank_limit:,} mejores candidatos. {ranking_description}",
                    "BU ordena por hombros de desplazamiento planos, medidos como velocidad absoluta media sobre todas sus muestras; en tren añade el gradiente entre recuperaciones P_i detectadas.",
                    "el candidato 1 es el mejor. Valores bajos y un crecimiento gradual respaldan la selección; valores parecidos entre varios candidatos sugieren soluciones alternativas estables.",
                    "Bunce et al. (2023), Secciones 2, 3.4 y 4; Figuras 3, 4 y 15.",
                ),
                rank_x,
                rank_series,
                "Candidato ordenado",
                "Velocidad equivalente [m/s]",
            )
        )
    )

    lift_ranked = sorted(evaluated_candidates, key=lambda item: item.score)
    lift_limit = min(5_000, len(lift_ranked))
    lift_x = np.arange(1, lift_limit + 1, dtype=float)
    lift_values_mm = np.asarray(
        [item.lift * 1000.0 for item in lift_ranked[:lift_limit]], dtype=float
    )
    steps.append(
        _record_step(
            ProcessStep(
                "uplift_control",
                "Control físico de levantamiento",
                _explanation(
                    f"el levantamiento aparente de los {lift_limit:,} candidatos de menor indicador y el límite configurado de {lift_limit_m * 1000.0:.3g} mm.",
                    "en un vano simple no se espera un desplazamiento importante contrario a la flecha; el artículo excluye esas soluciones antes de clasificarlas.",
                    "los puntos sobre la línea discontinua incumplen el control. Si todos la superan, DESP conserva una estimación exploratoria con advertencia, no una validación.",
                    "Bunce et al. (2023), Secciones 2 y 3.4; el artículo emplea 5 mm como umbral práctico.",
                ),
                lift_x,
                {
                    "Levantamiento aparente": lift_values_mm,
                    "Límite configurado": np.full_like(lift_x, lift_limit_m * 1000.0),
                },
                "Candidato por indicador",
                "Levantamiento [mm]",
                {"Límite configurado": "dashed"},
            )
        )
    )

    alternative_series: dict[str, np.ndarray] = {}
    for alternative_rank, candidate in enumerate(candidates[:5], start=1):
        candidate_start, candidate_end = candidate.start, candidate.end
        candidate_time = t[candidate_start : candidate_end + 1]
        candidate_local_time = candidate_time - candidate_time[0]
        candidate_acceleration = a[candidate_start : candidate_end + 1]
        candidate_coefficients = np.polyfit(
            candidate_local_time, candidate_acceleration, 1
        )
        candidate_corrected = candidate_acceleration - np.polyval(
            candidate_coefficients, candidate_local_time
        )
        candidate_velocity = integrate_signal(
            candidate_corrected, candidate_local_time, integration
        )
        candidate_displacement = integrate_signal(
            candidate_velocity, candidate_local_time, integration
        )
        full_candidate = np.full_like(t, np.nan)
        full_candidate[candidate_start : candidate_end + 1] = candidate_displacement * 1000.0
        alternative_series[f"Rango {alternative_rank}"] = full_candidate
    steps.append(
        _step(
            "candidate_robustness",
            "Estabilidad de las mejores ventanas",
            _explanation(
                f"las {len(alternative_series)} soluciones mejor clasificadas, cada una calculada con límites y tendencias ligeramente diferentes.",
                "el artículo muestra que puede haber varias ventanas correctas; compararlas revela cuánto depende la forma final de una única selección.",
                "si las curvas coinciden durante la carga, la solución es estable frente a pequeños cambios de ventana. Una dispersión grande exige revisar evento, ruido y zonas.",
                "Bunce et al. (2023), Sección 2 y Figura 4.",
            ),
            t,
            alternative_series,
            "Desplazamiento [mm]",
        )
    )

    steps.append(
        _step(
            "selected_detrend",
            "Tendencia de la ventana seleccionada",
            _explanation(
                f"la aceleración ganadora entre {window_time[0]:.4g} y {window_time[-1]:.4g} s y su recta de mínimos cuadrados, con pendiente {coefficients[0]:.4g} m/s³.",
                "una aceleración residual diminuta produce deriva grande tras dos integraciones; cada ventana debe tener su propia recta.",
                "la tendencia puede parecer casi horizontal y aun ser decisiva. Debe representar sesgo instrumental, no seguir las oscilaciones rápidas del puente.",
                "Bunce et al. (2023), Sección 2 y Figuras 1(b), 1(d), 1(f), 3 y 9(a).",
            ),
            window_time,
            {"Aceleración": window_acceleration, "Tendencia": trend},
            "Aceleración [m/s²]",
            {"Tendencia": "dashed"},
        )
    )
    steps.append(
        _step(
            "corrected_acceleration",
            "Aceleración sin tendencia",
            _explanation(
                "el residuo obtenido al sustraer la recta de la aceleración de la ventana ganadora.",
                "impone una línea base compatible con reposo sin aplicar un filtro pasa-altas ni alterar deliberadamente el contenido de baja frecuencia.",
                "debe quedar centrada alrededor de cero en los tramos descargados. Una inclinación residual reaparecerá amplificada en velocidad y desplazamiento.",
                "Bunce et al. (2023), Secciones 1.4 y 2; flujo de la Figura 3.",
            ),
            window_time,
            {"Corregida": corrected, "Cero": np.zeros_like(corrected)},
            "Aceleración [m/s²]",
            {"Cero": "dashed"},
        )
    )

    preload = window_time < event_start
    forced = (window_time >= event_start) & (window_time <= event_end)
    postload = window_time > event_end
    steps.append(
        _step(
            "shoulder_quality",
            "Primera integración: velocidad y gradiente de hombros",
            _explanation(
                f"la velocidad integrada, separada en precarga, paso y poscarga. Las medias |v| son {leading_score:.4g} y {trailing_score:.4g} m/s.",
                "la velocidad es la pendiente del desplazamiento; por eso permite medir la planitud de los hombros sin derivar una curva ya integrada.",
                "precarga y poscarga deben permanecer cerca de cero. Se usa valor absoluto para impedir que pendientes positivas y negativas se cancelen.",
                "Bunce et al. (2023), Sección 2, páginas 5-6, y Sección 3.4.",
            ),
            window_time,
            {
                "Precarga": np.where(preload, velocity, np.nan),
                "Paso": np.where(forced, velocity, np.nan),
                "Poscarga": np.where(postload, velocity, np.nan),
                "Cero": np.zeros_like(velocity),
            },
            "Velocidad [m/s]",
            {"Cero": "dashed"},
        )
    )

    displacement_mm = displacement * 1000.0
    steps.append(
        _step(
            "integrated_displacement",
            "Segunda integración: desplazamiento y hombros",
            _explanation(
                "el desplazamiento de la ventana ganadora, dividido en precarga, respuesta forzada y poscarga.",
                "los hombros descargados ofrecen una comprobación física interna: el puente parte y termina aproximadamente en su posición de reposo.",
                "busca hombros planos y próximos a 0 mm. La parte central es la flecha estimada; una deriva exterior indica una tendencia inadecuada.",
                "Bunce et al. (2023), Sección 2 y Figuras 1(c), 1(e), 1(g), 3 y 9(b).",
            ),
            window_time,
            {
                "Precarga": np.where(preload, displacement_mm, np.nan),
                "Paso": np.where(forced, displacement_mm, np.nan),
                "Poscarga": np.where(postload, displacement_mm, np.nan),
                "Cero": np.zeros_like(displacement_mm),
            },
            "Desplazamiento [mm]",
            {"Cero": "dashed"},
        )
    )

    selected_peak_locations: list[float] = []
    selected_peak_values: list[float] = []
    detected_peak_locations: list[float] = []
    unmatched_peak_locations: list[float] = []
    load_trough_locations: list[float] = []
    if quality_mode == "train" and expected_times.size >= 2:
        expected_markers = np.full_like(displacement_mm, np.nan)
        matched_markers = np.full_like(displacement_mm, np.nan)
        unmatched_markers = np.full_like(displacement_mm, np.nan)
        trough_markers = np.full_like(displacement_mm, np.nan)
        for expected_time in expected_times:
            expected_index = int(np.argmin(np.abs(window_time - expected_time)))
            expected_markers[expected_index] = displacement_mm[expected_index]

        detected_peak_indices = _bunce_extrema_indices(
            window_time,
            displacement,
            event_start,
            event_end,
            effective_direction,
            minimum_peak_spacing,
            minimum_peak_width,
            minimum_peak_prominence_m,
            recoveries=True,
        )
        _matched_expected_indices, matched_peak_indices = _match_bunce_recoveries(
            window_time,
            detected_peak_indices,
            expected_times,
            peak_tolerance,
        )
        matched_peak_set = {int(index) for index in matched_peak_indices}
        unmatched_peak_indices = np.asarray(
            [index for index in detected_peak_indices if int(index) not in matched_peak_set],
            dtype=int,
        )
        trough_indices = _bunce_extrema_indices(
            window_time,
            displacement,
            event_start,
            event_end,
            effective_direction,
            minimum_peak_spacing,
            minimum_peak_width,
            minimum_peak_prominence_m,
            recoveries=False,
        )
        matched_markers[matched_peak_indices] = displacement_mm[matched_peak_indices]
        unmatched_markers[unmatched_peak_indices] = displacement_mm[unmatched_peak_indices]
        trough_markers[trough_indices] = displacement_mm[trough_indices]
        selected_peak_locations = window_time[matched_peak_indices].astype(float).tolist()
        selected_peak_values = displacement[matched_peak_indices].astype(float).tolist()
        detected_peak_locations = window_time[detected_peak_indices].astype(float).tolist()
        unmatched_peak_locations = window_time[unmatched_peak_indices].astype(float).tolist()
        load_trough_locations = window_time[trough_indices].astype(float).tolist()

        if unmatched_peak_indices.size:
            quality_warnings.append(
                f"Se detectaron {unmatched_peak_indices.size} recuperaciones prominentes adicionales "
                "sin correspondencia con los P_i previstos. Revisa la agrupación de ejes, la "
                "geometría y los parámetros de separación, anchura y prominencia."
            )
        observed_text = (
            ", ".join(f"{value:.3f}" for value in selected_peak_locations)
            if selected_peak_locations
            else "ninguna"
        )
        steps.append(
            _step(
                "train_peak_quality",
                "Recuperaciones P_i y valles de carga T_i",
                _explanation(
                    f"{expected_times.size} recuperaciones previstas, {detected_peak_indices.size} detectadas y {matched_peak_indices.size} asociadas de forma única dentro de ±{peak_tolerance:.3g} s ({observed_text} s); además se muestran {trough_indices.size} valles T_i.",
                    f"BU usa máximos locales reales con separación mínima {minimum_peak_spacing:.3g} s, anchura {minimum_peak_width:.3g} s y prominencia {minimum_peak_prominence_m * 1000.0:.3g} mm. Las recuperaciones entre valles deberían tener alturas comparables.",
                    "Los P_i asociados deben aproximarse a los previstos. Es normal que haya un valle T_i más que recuperaciones P_i; recuperaciones extra o faltantes indican que la geometría, la detección o la hipótesis de descarga deben revisarse.",
                    "Bunce et al. (2023), Sección 4, Ecuación (1) y Figuras 10, 11 y 15(b).",
                ),
                window_time,
                {
                    "Desplazamiento": displacement_mm,
                    "P_i previstas": expected_markers,
                    "P_i detectadas": matched_markers,
                    "Recuperaciones extra": unmatched_markers,
                    "Valles de carga T_i": trough_markers,
                },
                "Desplazamiento [mm]",
                {
                    "P_i previstas": "points",
                    "P_i detectadas": "points",
                    "Recuperaciones extra": "points",
                    "Valles de carga T_i": "points",
                },
            )
        )

    acceleration_full = np.zeros_like(a)
    velocity_full = np.zeros_like(a)
    displacement_full = np.zeros_like(a)
    acceleration_full[best_start : best_end + 1] = corrected
    velocity_full[best_start : best_end + 1] = velocity
    displacement_full[best_start : best_end + 1] = displacement
    displacement_full[best_end + 1 :] = displacement[-1]
    steps.append(
        _step(
            "final_displacement",
            "Desplazamiento de la ventana mejor clasificada",
            _explanation(
                "la estimación seleccionada situada sobre el eje temporal completo del registro.",
                "es la salida que participa en comparación e informes después de superar, o advertir explícitamente, los controles de calidad.",
                "interpreta únicamente la ventana calculada. Los ceros anteriores y el valor constante posterior son relleno de alineación, no mediciones de desplazamiento.",
                "Bunce et al. (2023), Figuras 4, 9, 15 y 17.",
            ),
            t,
            {"Desplazamiento": displacement_full},
            "Desplazamiento [m]",
        )
    )
    return _result(
        record,
        "bunce_bridge",
        p,
        steps,
        acceleration_full,
        velocity_full,
        displacement_full,
        {
            "event_start_s": event_start,
            "event_end_s": event_end,
            "event_source": event_source,
            "window_start_s": float(window_time[0]),
            "window_end_s": float(window_time[-1]),
            "candidate_windows": int(start_indices.size * end_indices.size),
            "accepted_windows": len(accepted_candidates),
            "ranked_windows": len(candidates),
            "rejected_by_lift": rejected_by_lift,
            "lift_control_passed": lift_control_passed,
            "train_peak_control_passed": train_peak_control_passed,
            "selected_apparent_lift_mm": selected_lift * 1000.0,
            "quality_status": "accepted" if not quality_warnings else "warning",
            "quality_warnings": quality_warnings,
            "configured_deflection_direction": configured_direction,
            "effective_deflection_direction": effective_direction,
            "minimum_apparent_lift_negative_mm": minimum_lift["negative"] * 1000.0,
            "minimum_apparent_lift_positive_mm": minimum_lift["positive"] * 1000.0,
            "quality_score_mps": score,
            "leading_mean_abs_velocity_mps": leading_score,
            "trailing_mean_abs_velocity_mps": trailing_score,
            "shoulder_mean_abs_velocity_mps": shoulder_score,
            "train_peak_gradient_mps": peak_score,
            "specific_train_check": quality_mode == "train",
            "expected_peak_times_s": expected_times.tolist(),
            "expected_recovery_count": int(expected_times.size),
            "detected_recovery_count": len(detected_peak_locations),
            "matched_recovery_count": len(selected_peak_locations),
            "missing_recovery_count": int(expected_times.size - len(selected_peak_locations)),
            "unmatched_recovery_count": len(unmatched_peak_locations),
            "detected_recovery_times_s": detected_peak_locations,
            "unmatched_recovery_times_s": unmatched_peak_locations,
            "detected_load_trough_count": len(load_trough_locations),
            "detected_load_trough_times_s": load_trough_locations,
            "selected_peak_times_s": selected_peak_locations,
            "selected_peak_displacements_m": selected_peak_values,
            "detrend_intercept_mps2": float(coefficients[1]),
            "detrend_slope_mps3": float(coefficients[0]),
            **train_diagnostics,
        },
        started,
    )


def _wang_correction(time_s: np.ndarray, t1: float, t2: float, vf: float, af: float) -> np.ndarray:
    correction = np.zeros_like(time_s)
    ramp = (time_s > t1) & (time_s < t2)
    correction[ramp] = vf * (time_s[ramp] - t1) / max(t2 - t1, np.finfo(float).eps)
    after = time_s >= t2
    correction[after] = vf + af * (time_s[after] - t2)
    return correction


def _wang_integrated_correction(
    time_s: np.ndarray,
    t1: float,
    t2: float,
    vf: float,
    af: float,
) -> np.ndarray:
    """Analytical integral of Wang's velocity correction for fast grid search."""
    result = np.zeros_like(time_s, dtype=float)
    duration = max(t2 - t1, np.finfo(float).eps)
    ramp = (time_s > t1) & (time_s < t2)
    ramp_time = time_s[ramp] - t1
    result[ramp] = 0.5 * vf * np.square(ramp_time) / duration
    after = time_s >= t2
    post_time = time_s[after] - t2
    result[after] = 0.5 * vf * duration + vf * post_time + 0.5 * af * np.square(post_time)
    return result


def _run_wang(record: SignalRecord, p: dict[str, Any]) -> MethodResult:
    started = perf_counter()
    t, a = record.time_s, record.acceleration_mps2
    steps = _initial_steps(record)
    pre_end = max(3, min(a.size - 3, int(np.searchsorted(t, float(p["pre_event_s"])))))
    noise_metric = str(p["noise_metric"])
    if noise_metric == "mean_abs":
        noise_level = float(np.mean(np.abs(a[:pre_end])))
    else:
        noise_level = float(np.std(a[:pre_end]))
    threshold = max(np.finfo(float).eps, float(p["noise_multiplier"]) * noise_level)
    arrivals = np.flatnonzero(np.abs(a) > threshold)
    arrival_index = int(arrivals[0]) if arrivals.size else pre_end
    arrival_index = max(1, min(arrival_index, a.size - 4))
    pre_mean = float(np.mean(a[:arrival_index]))
    adjusted = a - pre_mean
    steps.append(_step("arrival", "Detección y corrección preevento", f"tp={t[arrival_index]:.3f} s; umbral={threshold:.4g} m/s²; media hasta tp={pre_mean:.4g} m/s².", t, {"Original": a, "Corregida": adjusted, "+umbral": np.full_like(a, threshold), "-umbral": np.full_like(a, -threshold)}, "Aceleración [m/s²]"))
    pga_index = int(np.argmax(np.abs(adjusted)))
    energy = np.cumsum(np.square(adjusted))
    energy /= max(float(energy[-1]), np.finfo(float).eps)
    final_index = int(np.searchsorted(energy, float(p["energy_fraction"])))
    final_index = max(arrival_index + 3, min(final_index, a.size - 2))
    end_index = a.size - 1
    if bool(p["limit_post_event"]):
        end_index = min(end_index, arrival_index + 4 * (final_index - arrival_index))
    end_index = max(final_index + 2, end_index)
    steps.append(_step("energy_window", "Ventana energética", f"tPGA={t[pga_index]:.3f} s; tf={t[final_index]:.3f} s; te={t[end_index]:.3f} s.", t, {"Energía acumulada": energy}, "Fracción de energía"))
    velocity_raw = integrate_signal(adjusted, t, str(p["integration"]))
    displacement_raw = integrate_signal(velocity_raw, t, str(p["integration"]))
    steps.append(_step("uncorrected_motion", "Movimiento sin corrección", "Doble integración usada para determinar tD0 y tPGD.", t, {"Desplazamiento": displacement_raw}, "Desplazamiento [m]"))
    products = displacement_raw[:-1] * displacement_raw[1:]
    crossings = np.flatnonzero(products < 0.0)
    crossings = crossings[(crossings >= arrival_index) & (crossings < final_index)]
    d0_index = int(crossings[-1]) if crossings.size else arrival_index
    pgd_search_end = max(arrival_index + 1, d0_index + 1)
    pgd_index = arrival_index + int(np.argmax(np.abs(displacement_raw[arrival_index:pgd_search_end])))
    post_time = t[final_index : end_index + 1] - t[final_index]
    post_disp = displacement_raw[final_index : end_index + 1]
    degree = min(int(p["post_degree"]), max(1, post_disp.size - 1))
    post_coefficients = np.polyfit(post_time, post_disp, degree)
    post_fit = np.polyval(post_coefficients, post_time)
    first_derivative = np.polyder(post_coefficients, 1)
    second_derivative = np.polyder(post_coefficients, 2)
    vf = float(np.polyval(first_derivative, 0.0))
    af = float(np.polyval(second_derivative, 0.0)) if degree >= 2 else 0.0
    fit_full = np.full_like(displacement_raw, np.nan)
    fit_full[final_index : end_index + 1] = post_fit
    steps.append(_step("post_event_fit", "Ajuste del postevento", f"Polinomio grado {degree}; vf={vf:.4g} m/s; af={af:.4g} m/s².", t, {"Desplazamiento": displacement_raw, "Ajuste": fit_full}, "Desplazamiento [m]"))

    density = int(p["grid_points"])
    search_step = max(float(t[end_index] - t[0]) / density, 1.0 / record.sampling_rate_hz)
    lower_t2 = max(float(t[pga_index]), float(t[d0_index]), float(t[arrival_index + 1]))
    upper_t2 = float(t[final_index])
    if lower_t2 >= upper_t2:
        lower_t2 = float(t[arrival_index + 1])
    t2_values = np.arange(lower_t2, upper_t2 + 0.5 * search_step, search_step)
    t2_values = np.unique(np.minimum(t2_values, upper_t2))
    if t2_values.size == 0:
        t2_values = np.array([upper_t2])
    evaluation = np.unique(np.linspace(0, a.size - 1, min(1800, a.size), dtype=int))
    sampled_time = t[evaluation]
    sampled_raw = displacement_raw[evaluation]
    step_mode = str(p["step_search_mode"])
    if step_mode == "manual_range":
        step_min = float(p["step_min_m"])
        step_max = float(p["step_max_m"])
        if step_max <= step_min:
            raise ValueError("d_f máximo debe ser mayor que d_f mínimo.")
        step_increment = (step_max - step_min) * float(p["step_increment_fraction"])
    else:
        step_min = step_max = step_increment = 0.0
    best: tuple[float, float, float, float, float] | None = None
    for t2 in t2_values:
        lower_t1 = min(float(t[pgd_index]), t2 - max(2.0 / record.sampling_rate_hz, 1e-6))
        lower_t1 = max(float(t[arrival_index]), lower_t1)
        t1_values = np.arange(lower_t1, t2, search_step)
        if t1_values.size == 0:
            t1_values = np.array([lower_t1])
        for t1 in t1_values:
            sampled = sampled_raw - _wang_integrated_correction(sampled_time, float(t1), float(t2), vf, af)
            suffix_sum = np.cumsum(sampled[::-1])[::-1]
            suffix_square = np.cumsum(np.square(sampled[::-1]))[::-1]
            total_square = float(suffix_square[0])
            t3_values = np.arange(t1, t2 + 0.5 * search_step, search_step)
            indices = np.searchsorted(sampled_time, t3_values, side="left")
            valid = indices < sampled.size
            if not np.any(valid):
                continue
            indices = indices[valid]
            t3_values = t3_values[valid]
            count = sampled.size - indices
            before_square = total_square - suffix_square[indices]
            optimum_steps = suffix_sum[indices] / count
            if step_mode == "manual_range":
                target_steps = step_min + np.round((optimum_steps - step_min) / step_increment) * step_increment
                target_steps = np.clip(target_steps, step_min, step_max)
            else:
                target_steps = optimum_steps
            errors = (
                before_square
                + suffix_square[indices]
                - 2.0 * target_steps * suffix_sum[indices]
                + count * np.square(target_steps)
            ) / sampled.size
            selected = int(np.argmin(errors))
            error = float(errors[selected])
            if best is None or error < best[0]:
                best = (error, float(t1), float(t2), float(t3_values[selected]), float(target_steps[selected]))
    if best is None:
        raise RuntimeError("No se encontró una corrección continua válida para Wang.")
    error, t1, t2, t3, target_step = best
    correction = _wang_correction(t, t1, t2, vf, af)
    velocity = velocity_raw - correction
    displacement = integrate_signal(velocity, t, str(p["integration"]))
    residual = float(np.mean(displacement[t >= t3]))
    target = np.where(t >= t3, target_step, 0.0)
    steps.append(_step("continuous_correction", "Corrección continua óptima", f"t1={t1:.3f} s; t2={t2:.3f} s; t3={t3:.3f} s; error={error:.4g}.", t, {"Velocidad original": velocity_raw, "Corrección vc": correction, "Velocidad final": velocity}, "Velocidad [m/s]"))
    steps.append(_step("final_displacement", "Desplazamiento y escalón", f"Residual estimado {residual:.5g} m; d_f objetivo {target_step:.5g} m.", t, {"Desplazamiento": displacement, "Escalón ajustado": target}, "Desplazamiento [m]"))
    return _result(record, "wang", p, steps, adjusted, velocity, displacement, {"arrival_s": float(t[arrival_index]), "pre_event_mean_mps2": pre_mean, "t_pga_s": float(t[pga_index]), "t_final_energy_s": float(t[final_index]), "noise_metric": noise_metric, "noise_level_mps2": noise_level, "search_divisions": density, "search_step_s": search_step, "step_search_mode": step_mode, "t1_s": t1, "t2_s": t2, "t3_s": t3, "step_target_m": target_step, "step_displacement_m": residual, "search_mse": error}, started)


RUNNERS: dict[str, Callable[[SignalRecord, dict[str, Any]], MethodResult]] = {
    "trifunac_lee": _run_trifunac_lee,
    "chiu": _run_chiu,
    "converse_brady": _run_converse_brady,
    "boore": _run_boore,
    "wang": _run_wang,
    "darragh": _run_darragh,
    "park": _run_park,
    "bunce_bridge": _run_bunce_bridge,
}


def run_method(method_id: str, record: SignalRecord, parameters: dict[str, Any] | None = None) -> MethodResult:
    if method_id not in RUNNERS:
        raise KeyError(f"Método desconocido: {method_id}")
    merged = default_parameters(method_id)
    if parameters:
        merged.update(parameters)
    return RUNNERS[method_id](record, merged)


def run_method_traced(
    method_id: str,
    record: SignalRecord,
    parameters: dict[str, Any] | None = None,
    step_callback: Callable[[ProcessStep], None] | None = None,
) -> MethodResult | PartialMethodResult:
    """Run a method while retaining every completed visual step on failure."""
    started = perf_counter()
    trace: list[ProcessStep] = []
    trace_token = _STEP_TRACE.set(trace)
    callback_token = _STEP_CALLBACK.set(step_callback)
    try:
        return run_method(method_id, record, parameters)
    except Exception as exc:  # noqa: BLE001
        spec = METHOD_BY_ID.get(method_id)
        return PartialMethodResult(
            method_id=method_id,
            method_name=spec.name if spec is not None else method_id,
            steps=trace.copy(),
            failure_message=str(exc),
            elapsed_s=perf_counter() - started,
        )
    finally:
        _STEP_CALLBACK.reset(callback_token)
        _STEP_TRACE.reset(trace_token)
