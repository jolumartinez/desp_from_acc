from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .models import SignalRecord


TIME_NAMES = {"time", "time_s", "timestamp", "t", "datetime", "fecha_hora", "tiempo"}
UNIT_FACTORS = {"m/s²": 1.0, "cm/s²": 0.01, "g": 9.80665}


def scan_txt_files(folder: Path) -> list[Path]:
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"No existe la carpeta: {folder}")
    return sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() == ".txt")


def _looks_numeric(value: object) -> bool:
    try:
        float(str(value).strip())
    except ValueError:
        return False
    return True


def read_txt_frame(path: Path) -> pd.DataFrame:
    path = Path(path)
    frame = pd.read_csv(path, sep=None, engine="python", comment="#")
    if frame.shape[1] < 2:
        frame = pd.read_csv(path, sep=None, engine="python", comment="#", header=None)
    elif all(_looks_numeric(column) for column in frame.columns):
        frame = pd.read_csv(path, sep=None, engine="python", comment="#", header=None)
    if frame.empty or frame.shape[1] < 2:
        raise ValueError("El TXT debe tener al menos dos columnas: tiempo y aceleración.")
    if all(isinstance(column, int) for column in frame.columns):
        frame.columns = ["time"] + [f"channel_{index}" for index in range(1, frame.shape[1])]
    return frame


def available_channels(path: Path) -> list[str]:
    frame = read_txt_frame(path)
    time_column = _time_column(frame)
    return [str(column) for column in frame.columns if column != time_column]


def _time_column(frame: pd.DataFrame) -> object:
    return next(
        (column for column in frame.columns if str(column).strip().lower() in TIME_NAMES),
        frame.columns[0],
    )


def _header_sampling_rate(path: Path) -> float | None:
    with Path(path).open("r", encoding="utf-8", errors="ignore") as source:
        header = "".join(source.readline() for _ in range(120))
    direct = re.search(
        r"(?im)^\s*#?\s*(?:sample\s*rate|sampling\s*(?:rate|frequency)|rate|fs)\s*=\s*([0-9.eE+-]+)",
        header,
    )
    if direct:
        value = float(direct.group(1))
        return value if value > 0.0 else None
    return None


def load_signal(
    path: Path,
    channel: str,
    input_unit: str,
    sampling_rate_override_hz: float | None = None,
) -> SignalRecord:
    path = Path(path).expanduser().resolve()
    frame = read_txt_frame(path)
    time_column = _time_column(frame)
    channel_column = next((column for column in frame.columns if str(column) == channel), None)
    if channel_column is None:
        raise ValueError(f"No existe el canal '{channel}' en {path.name}.")

    values = pd.to_numeric(frame[channel_column], errors="coerce").to_numpy(dtype=float)
    raw_time = frame[time_column]
    numeric_time = pd.to_numeric(raw_time, errors="coerce").to_numpy(dtype=float)
    if np.all(np.isfinite(numeric_time)):
        time_s = numeric_time - numeric_time[0]
    else:
        parsed = pd.to_datetime(raw_time, errors="coerce", utc=True, format="mixed")
        if parsed.notna().sum() != len(parsed):
            raise ValueError("La columna de tiempo no es numérica ni contiene fechas válidas.")
        nanoseconds = parsed.astype("int64").to_numpy(dtype=np.int64)
        time_s = (nanoseconds - nanoseconds[0]).astype(float) / 1.0e9

    valid = np.isfinite(time_s) & np.isfinite(values)
    time_s = time_s[valid]
    values = values[valid]
    if time_s.size < 4:
        raise ValueError("No hay suficientes muestras numéricas válidas.")
    unique = np.concatenate(([True], np.diff(time_s) > 0.0))
    time_s = time_s[unique]
    values = values[unique]

    time_steps = np.diff(time_s)
    median_step = float(np.median(time_steps))
    inferred_fs = 1.0 / median_step
    relative_jitter = float(np.max(np.abs(time_steps - median_step)) / median_step)
    header_fs = _header_sampling_rate(path)
    sampling_rate = float(sampling_rate_override_hz or header_fs or inferred_fs)
    time_axis_reconstructed = sampling_rate_override_hz is not None or header_fs is not None
    if time_axis_reconstructed:
        time_s = np.arange(time_s.size, dtype=float) / sampling_rate
    elif relative_jitter > 0.02:
        raise ValueError(
            "La señal no tiene muestreo uniforme (variación mayor al 2 %). "
            "Indica una frecuencia de muestreo para reconstruir el eje temporal."
        )
    factor = UNIT_FACTORS.get(input_unit)
    if factor is None:
        raise ValueError(f"Unidad de aceleración no soportada: {input_unit}")
    return SignalRecord(
        source_path=path,
        channel=str(channel),
        time_s=time_s,
        acceleration_mps2=values * factor,
        sampling_rate_hz=sampling_rate,
        input_unit=input_unit,
        metadata={
            "inferred_sampling_rate_hz": inferred_fs,
            "header_sampling_rate_hz": header_fs,
            "time_step_relative_jitter": relative_jitter,
            "time_axis_reconstructed": time_axis_reconstructed,
        },
    )


def crop_signal(record: SignalRecord, start_s: float, end_s: float) -> SignalRecord:
    start = max(float(record.time_s[0]), float(start_s))
    end = min(float(record.time_s[-1]), float(end_s))
    if end <= start:
        raise ValueError("El final del recorte debe ser posterior al inicio.")
    mask = (record.time_s >= start) & (record.time_s <= end)
    if int(np.count_nonzero(mask)) < 4:
        raise ValueError("El segmento debe contener al menos cuatro muestras.")
    selected_time = record.time_s[mask]
    actual_start = float(selected_time[0])
    actual_end = float(selected_time[-1])
    metadata = dict(record.metadata)
    metadata.update(
        {
            "crop_start_s": actual_start,
            "crop_end_s": actual_end,
            "original_samples": int(record.time_s.size),
        }
    )
    return SignalRecord(
        source_path=record.source_path,
        channel=record.channel,
        time_s=selected_time - selected_time[0],
        acceleration_mps2=record.acceleration_mps2[mask],
        sampling_rate_hz=record.sampling_rate_hz,
        input_unit=record.input_unit,
        metadata=metadata,
    )
