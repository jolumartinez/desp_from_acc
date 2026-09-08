"""Shared axle geometry for the BU and Tokunaga railway methods."""
from __future__ import annotations

import re
from typing import Any

import numpy as np


DEFAULT_AXLE_SPACINGS_M = "17.4, 17.75, 17.75, 17.75, 17.4"


def parse_axle_spacings(value: Any) -> np.ndarray:
    """Convert consecutive positive spacings to axle positions from the first axle.

    Spacings need not increase. Commas, whitespace, semicolons and vertical bars
    are accepted as separators; the decimal separator is a point.
    """
    tokens = [token for token in re.split(r"[,;|\s]+", str(value).strip()) if token]
    if not tokens:
        raise ValueError("Introduce las separaciones entre ejes consecutivos, en metros.")
    if len(tokens) > 799:
        raise ValueError("La geometría admite como máximo 800 ejes (799 separaciones).")
    try:
        spacings = np.asarray([float(token) for token in tokens], dtype=float)
    except ValueError as exc:
        raise ValueError("Las separaciones entre ejes deben ser números separados por coma.") from exc
    if not np.all(np.isfinite(spacings)) or np.any(spacings <= 0.0):
        raise ValueError("Las separaciones entre ejes deben ser finitas y mayores que cero.")
    with np.errstate(over="ignore"):
        positions = np.concatenate(([0.0], np.cumsum(spacings)))
    if not np.all(np.isfinite(positions)) or np.any(np.diff(positions) <= 0.0):
        raise ValueError("La suma de las separaciones no produce posiciones de ejes finitas y distintas.")
    return positions
