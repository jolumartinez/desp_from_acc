"""Analytical spectra from Tokunaga et al. (2022), equations 16–19.

These are continuous Fourier transforms (seconds), not unscaled DFT arrays.
The finite sum and sinc representation evaluate the removable singularities
without perturbing the physical transfer function.
"""
from __future__ import annotations

import numpy as np


def half_sine_spectrum(omega: np.ndarray, crossing_time_s: float) -> np.ndarray:
    """Transform of sin(pi*t/T) on [0, T], including omega=0 and pi/T."""
    omega = np.asarray(omega, dtype=float)
    duration = float(crossing_time_s)
    if not np.isfinite(duration) or duration <= 0.0:
        raise ValueError("El tiempo de cruce del vano debe ser positivo.")
    natural = np.pi / duration

    def exponential_integral(frequency: np.ndarray) -> np.ndarray:
        phase = frequency * duration / 2.0
        return duration * np.exp(-1j * phase) * np.sinc(phase / np.pi)

    return (exponential_integral(omega - natural) - exponential_integral(omega + natural)) / (2j)


def train_spectrum(
    omega: np.ndarray,
    span_m: float,
    speed_mps: float,
    axle_positions_m: np.ndarray,
    entry_offset_s: float,
) -> np.ndarray:
    """Unnormalised modal excitation spectrum F_lambda, equation 17."""
    omega = np.asarray(omega, dtype=float)
    axle_phases = np.zeros(omega.shape, dtype=complex)
    # Sum by axle to avoid allocating a frequencies-by-axles matrix.
    for position in np.asarray(axle_positions_m, dtype=float):
        axle_phases += np.exp(-1j * omega * (entry_offset_s + position / speed_mps))
    return half_sine_spectrum(omega, span_m / speed_mps) * axle_phases


def modal_load_time(
    relative_time_s: np.ndarray,
    span_m: float,
    speed_mps: float,
    axle_positions_m: np.ndarray,
    entry_offset_s: float,
) -> np.ndarray:
    """Dimensionless sum of first-mode axle loads; no lambda_max division."""
    time = np.asarray(relative_time_s, dtype=float)
    duration = span_m / speed_mps
    load = np.zeros_like(time)
    for position in axle_positions_m:
        age = time - entry_offset_s - position / speed_mps
        active = (age >= 0.0) & (age <= duration)
        load[active] += np.sin(np.pi * age[active] / duration)
    return load
