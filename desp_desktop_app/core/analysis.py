from __future__ import annotations

from typing import Iterable

import numpy as np

from .models import MethodResult


def comparison_rows(results: Iterable[MethodResult]) -> list[dict[str, float | str]]:
    items = list(results)
    if not items:
        return []
    stack = np.vstack([item.displacement_m for item in items])
    consensus = np.median(stack, axis=0)
    consensus_scale = max(float(np.ptp(consensus)), np.finfo(float).eps)
    rows: list[dict[str, float | str]] = []
    for item in items:
        values = item.displacement_m
        correlation = float(np.corrcoef(values, consensus)[0, 1]) if np.std(values) > 0.0 and np.std(consensus) > 0.0 else 0.0
        nrmse = float(np.sqrt(np.mean(np.square(values - consensus))) / consensus_scale)
        summary = item.summary()
        rows.append(
            {
                "method_id": item.method_id,
                "method": item.method_name,
                "peak_m": float(summary["peak_displacement_m"]),
                "residual_m": float(summary["residual_displacement_m"]),
                "rms_m": float(summary["rms_displacement_m"]),
                "correlation_consensus": correlation,
                "nrmse_consensus": nrmse,
                "elapsed_s": item.elapsed_s,
            }
        )
    return rows


def pairwise_correlation(results: Iterable[MethodResult]) -> tuple[list[str], np.ndarray]:
    items = list(results)
    names = [item.method_name for item in items]
    if not items:
        return names, np.empty((0, 0), dtype=float)
    if len(items) == 1:
        return names, np.ones((1, 1), dtype=float)
    matrix = np.corrcoef(np.vstack([item.displacement_m for item in items]))
    return names, np.nan_to_num(matrix, nan=0.0)


def comparison_envelope(results: Iterable[MethodResult]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    items = list(results)
    if not items:
        raise ValueError("No hay resultados para comparar.")
    stack = np.vstack([item.displacement_m for item in items])
    return np.min(stack, axis=0), np.median(stack, axis=0), np.max(stack, axis=0)

