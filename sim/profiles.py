"""Slow load and solar irradiance profiles used by the demo simulator."""
from __future__ import annotations

import math
import time

import numpy as np


def load_kw(t_seconds: float, rng: np.random.Generator, base: float = 1.1, amplitude: float = 0.9) -> float:
    """Evening/morning-ish load with a slow oscillation (period ~4 min in demo)."""
    slow = 0.5 * (1.0 + math.sin(2.0 * math.pi * t_seconds / 240.0 - 1.2))
    ripple = 0.12 * math.sin(2.0 * math.pi * t_seconds / 17.0)
    value = base + amplitude * slow + ripple + rng.normal(0.0, 0.06)
    return float(max(0.15, value))


def solar_kw(
    t_seconds: float,
    capacity_kwp: float,
    rng: np.random.Generator,
    mode: str = "cycle",
    cycle_seconds: float = 480.0,
) -> float:
    """Solar generation.

    ``cycle`` compresses a day into ``cycle_seconds`` so a short demo shows
    both import and export.  ``diurnal`` uses wall-clock local time.
    """
    if capacity_kwp <= 0:
        return 0.0
    if mode == "diurnal":
        now = time.localtime()
        hour = now.tm_hour + now.tm_min / 60.0
        daylight = math.sin(math.pi * (hour - 6.0) / 12.0)
        factor = max(0.0, daylight) ** 1.4
    else:
        daylight = math.sin(2.0 * math.pi * t_seconds / max(cycle_seconds, 1.0) + 1.2)
        factor = max(0.0, daylight) ** 1.5
    clouds = 1.0 - 0.12 * rng.random()
    return float(max(0.0, capacity_kwp * factor * clouds))
