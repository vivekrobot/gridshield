"""Physically parameterised waveform builder for the edge-node simulator.

Unlike ``ml.dataset.synth_waveform`` (which draws a random operating point),
this builder takes the *current* operating point from the load/solar profiles
so the simulated telemetry evolves smoothly.  The shapes are the same, which
keeps the trained classifier in-distribution.
"""
from __future__ import annotations

import numpy as np

from ml.config import FS, WINDOW

HARMONICS = (3, 5, 7)
SHAPE = np.array([1.0, 0.55, 0.30])
SHAPE = SHAPE / np.linalg.norm(SHAPE)


def _harmonics(t: np.ndarray, freq: float, phase: float, thd: float, rng: np.random.Generator) -> np.ndarray:
    if thd <= 0:
        return np.zeros_like(t)
    out = np.zeros_like(t)
    for order, weight in zip(HARMONICS, SHAPE):
        out += np.sqrt(2.0) * thd * weight * np.sin(
            order * (2.0 * np.pi * freq * t + phase) + rng.uniform(0.0, 2.0 * np.pi)
        )
    return out


def build_window(
    v_rms: float,
    i_rms: float,
    pf: float,
    thd_v_pct: float,
    thd_i_pct: float,
    rng: np.random.Generator,
    *,
    overload: bool = False,
    phase_jump_deg: float = 0.0,
    freq: float = 50.0,
    phase: float | None = None,
) -> np.ndarray:
    """Return a (160, 2) window in volts and amps."""
    t = np.arange(WINDOW, dtype=np.float64) / FS
    if phase is None:
        phase = rng.uniform(0.0, 2.0 * np.pi)
    jump = np.deg2rad(phase_jump_deg)
    v_pk = np.sqrt(2.0) * max(v_rms, 1.0)
    i_pk = np.sqrt(2.0) * max(i_rms, 0.0)

    v = v_pk * np.sin(2.0 * np.pi * freq * t + phase + jump)
    v += v_pk * _harmonics(t, freq, phase + jump, thd_v_pct / 100.0, rng)

    lag = np.arccos(np.clip(pf, 0.0, 1.0))
    i = i_pk * np.sin(2.0 * np.pi * freq * t + phase + jump - lag)
    i += i_pk * _harmonics(t, freq, phase + jump - lag, thd_i_pct / 100.0, rng)
    if overload:
        i += 0.35 * i_pk * np.exp(-t / 0.03)  # fault inrush / decaying DC

    # Sensor chain: gain error, DC offset, white noise.
    v = v * rng.normal(1.0, 0.006) + rng.normal(0.0, 0.4) + rng.normal(0.0, 1.8, v.shape)
    i = i * rng.normal(1.0, 0.008) + rng.normal(0.0, 0.02) + rng.normal(0.0, 0.05, i.shape)
    return np.column_stack([v, i]).astype(np.float32)


def decimate(wave: np.ndarray, points: int = 48) -> dict[str, list[float]]:
    """Down-sample a window for the low-bandwidth MQTT preview."""
    idx = np.linspace(0, len(wave) - 1, num=min(points, len(wave))).astype(int)
    return {
        "v": [round(float(v), 1) for v in wave[idx, 0]],
        "i": [round(float(i), 2) for i in wave[idx, 1]],
    }
