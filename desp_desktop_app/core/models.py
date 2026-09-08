from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    label: str
    kind: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    decimals: int = 3
    suffix: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    help_text: str = ""


@dataclass(frozen=True)
class MethodSpec:
    method_id: str
    short_name: str
    name: str
    year: int
    summary: str
    intended_use: str
    limitation: str
    reference: str
    reference_url: str
    thesis_pages: str
    thesis_pdf_page: int
    thesis_page_label: str
    flow: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    accent: str
    local_reference_file: str | None = None
    local_reference_page: int | None = None
    reference_basis: str = "tesis"


@dataclass
class SignalRecord:
    source_path: Path
    channel: str
    time_s: np.ndarray
    acceleration_mps2: np.ndarray
    sampling_rate_hz: float
    input_unit: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.time_s = np.asarray(self.time_s, dtype=float).reshape(-1)
        self.acceleration_mps2 = np.asarray(self.acceleration_mps2, dtype=float).reshape(-1)
        if self.time_s.size != self.acceleration_mps2.size or self.time_s.size < 4:
            raise ValueError("La señal debe contener al menos cuatro pares tiempo-aceleración.")
        if not np.all(np.isfinite(self.time_s)) or not np.all(np.isfinite(self.acceleration_mps2)):
            raise ValueError("La señal contiene valores no finitos.")
        if np.any(np.diff(self.time_s) <= 0.0):
            raise ValueError("El tiempo debe ser estrictamente creciente.")
        if not np.isfinite(self.sampling_rate_hz) or self.sampling_rate_hz <= 0.0:
            raise ValueError("La frecuencia de muestreo debe ser positiva.")


@dataclass
class ProcessStep:
    key: str
    title: str
    description: str
    x: np.ndarray
    series: dict[str, np.ndarray]
    x_label: str
    y_label: str
    series_styles: dict[str, str] = field(default_factory=dict)


@dataclass
class MethodResult:
    method_id: str
    method_name: str
    time_s: np.ndarray
    acceleration_mps2: np.ndarray
    velocity_mps: np.ndarray
    displacement_m: np.ndarray
    parameters: dict[str, Any]
    steps: list[ProcessStep]
    diagnostics: dict[str, Any]
    elapsed_s: float

    def summary(self) -> dict[str, Any]:
        displacement = np.asarray(self.displacement_m, dtype=float)
        tail_size = max(1, int(round(0.05 * displacement.size)))
        return {
            "method_id": self.method_id,
            "method": self.method_name,
            "peak_displacement_m": float(np.max(np.abs(displacement))),
            "residual_displacement_m": float(np.mean(displacement[-tail_size:])),
            "rms_displacement_m": float(np.sqrt(np.mean(np.square(displacement)))),
            "peak_velocity_mps": float(np.max(np.abs(self.velocity_mps))),
            "elapsed_s": float(self.elapsed_s),
            **self.diagnostics,
        }


@dataclass
class PartialMethodResult:
    method_id: str
    method_name: str
    steps: list[ProcessStep]
    failure_message: str
    elapsed_s: float
