from __future__ import annotations

import numpy as np
from scipy import integrate, signal


def integrate_signal(values: np.ndarray, time_s: np.ndarray, method: str = "simpson") -> np.ndarray:
    values = np.asarray(values, dtype=float)
    time_s = np.asarray(time_s, dtype=float)
    if method == "trapezoid":
        return integrate.cumulative_trapezoid(values, time_s, initial=0.0)
    try:
        return integrate.cumulative_simpson(values, x=time_s, initial=0.0)
    except (AttributeError, ValueError):
        return integrate.cumulative_trapezoid(values, time_s, initial=0.0)


def effective_cutoff(cutoff_hz: float, sampling_rate_hz: float) -> float:
    if cutoff_hz <= 0.0:
        raise ValueError("La frecuencia de corte debe ser positiva.")
    return min(float(cutoff_hz), 0.475 * float(sampling_rate_hz))


def butter_filter(
    values: np.ndarray,
    sampling_rate_hz: float,
    cutoff_hz: float,
    order: int,
    btype: str,
    *,
    zero_phase: bool = True,
) -> np.ndarray:
    cutoff = effective_cutoff(cutoff_hz, sampling_rate_hz)
    sos = signal.butter(int(order), cutoff, btype=btype, fs=sampling_rate_hz, output="sos")
    return apply_sos_filter(values, sos, zero_phase=zero_phase)


def apply_sos_filter(
    values: np.ndarray,
    sos: np.ndarray,
    *,
    zero_phase: bool = True,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if not zero_phase:
        return signal.sosfilt(sos, values)
    try:
        return signal.sosfiltfilt(sos, values)
    except ValueError as exc:
        raise ValueError(
            "El segmento es demasiado corto para aplicar el filtro sin desfase; "
            "amplía el intervalo o utiliza explícitamente el modo causal."
        ) from exc


def butterworth_order_from_specs(
    sampling_rate_hz: float,
    passband_hz: float,
    stopband_hz: float,
    passband_ripple_db: float,
    stopband_attenuation_db: float,
) -> tuple[int, float]:
    nyquist = 0.5 * float(sampling_rate_hz)
    passband = float(passband_hz)
    stopband = float(stopband_hz)
    if not 0.0 < passband < nyquist or not 0.0 < stopband < nyquist:
        raise ValueError("Las esquinas pasabanda y de rechazo deben estar entre 0 y Nyquist.")
    if passband <= stopband:
        raise ValueError("Para un pasa alta, Wp debe ser mayor que Ws.")
    order, cutoff = signal.buttord(
        passband,
        stopband,
        float(passband_ripple_db),
        float(stopband_attenuation_db),
        fs=float(sampling_rate_hz),
    )
    return int(order), float(cutoff)


def padded_filter(
    values: np.ndarray,
    sampling_rate_hz: float,
    cutoff_hz: float,
    order: int,
    btype: str,
    pad_seconds: float,
    *,
    zero_phase: bool = True,
) -> tuple[np.ndarray, int]:
    pad_samples = max(0, int(round(float(pad_seconds) * sampling_rate_hz)))
    padded = np.pad(np.asarray(values, dtype=float), (pad_samples, pad_samples), mode="constant")
    filtered = butter_filter(
        padded,
        sampling_rate_hz,
        cutoff_hz,
        order,
        btype,
        zero_phase=zero_phase,
    )
    if pad_samples:
        filtered = filtered[pad_samples:-pad_samples]
    return filtered, pad_samples


def polynomial_trend(values: np.ndarray, time_s: np.ndarray, degree: int) -> np.ndarray:
    centered = np.asarray(time_s, dtype=float) - float(time_s[0])
    coefficients = np.polyfit(centered, np.asarray(values, dtype=float), int(degree))
    return np.polyval(coefficients, centered)


def fft_spectrum(values: np.ndarray, sampling_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(values, dtype=float)
    centered = values - float(np.mean(values))
    frequency = np.fft.rfftfreq(centered.size, d=1.0 / sampling_rate_hz)
    amplitude = np.abs(np.fft.rfft(centered)) * (2.0 / max(1, centered.size))
    if amplitude.size:
        amplitude[0] *= 0.5
    return frequency, amplitude


def derivative(values: np.ndarray, time_s: np.ndarray) -> np.ndarray:
    return np.gradient(np.asarray(values, dtype=float), np.asarray(time_s, dtype=float), edge_order=2)


def displacement_scale(unit: str) -> tuple[float, str]:
    mapping = {"m": (1.0, "m"), "cm": (100.0, "cm"), "mm": (1000.0, "mm")}
    return mapping.get(unit, mapping["mm"])
