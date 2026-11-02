"""Feature engineering shared by the simulator, cloud and anomaly model."""
from __future__ import annotations

from typing import Mapping

import numpy as np

from .config import FS, I_RATED, V_NOMINAL
from .dataset import thd_from_window

FEATURE_NAMES = (
    "v_pu",        # RMS voltage / nominal
    "i_pu",        # load current / rated
    "pf",          # displacement power factor
    "thd_v",       # voltage THD (fraction)
    "thd_i",       # current THD (fraction)
    "p_kw",        # active power (kW)
    "crest_i",     # current crest factor (peak / RMS)
    "freq_dev",    # |f - 50| in Hz
)


def waveform_stats(v: np.ndarray, i: np.ndarray) -> dict[str, float]:
    """Compute the electrical scalars the edge node would report."""
    v = np.asarray(v, dtype=np.float64)
    i = np.asarray(i, dtype=np.float64)
    v_rms = float(np.sqrt(np.mean(v**2)))
    i_rms = float(np.sqrt(np.mean(i**2)))
    p_active = float(np.mean(v * i))  # mean of instantaneous power = real power
    s_apparent = v_rms * i_rms
    pf = float(np.clip(p_active / s_apparent, 0.0, 1.0)) if s_apparent > 1e-9 else 0.0
    i_peak = float(np.max(np.abs(i)))
    return {
        "v_rms": v_rms,
        "i_rms": i_rms,
        "p_active": p_active,
        "pf": pf,
        "thd_v": thd_from_window(v) * 100.0,
        "thd_i": thd_from_window(i) * 100.0,
        "crest_i": i_peak / i_rms if i_rms > 1e-9 else 0.0,
    }


def telemetry_features(row: Mapping[str, float]) -> np.ndarray:
    """Build the anomaly-detector feature vector from one telemetry record."""
    v = float(row.get("v_rms") or 0.0)
    i = float(row.get("i_load") or 0.0)
    pf = float(row.get("pf") or 0.0)
    p_kw = float(row.get("p_active") if row.get("p_active") is not None else (v * i * pf / 1000.0))
    crest = float(row.get("crest_i") or 1.414)
    freq = float(row.get("freq") or 50.0)
    return np.asarray(
        [
            v / V_NOMINAL,
            i / I_RATED,
            np.clip(pf, 0.0, 1.0),
            max(float(row.get("thd_v") or 0.0), 0.0) / 100.0,
            max(float(row.get("thd_i") or 0.0), 0.0) / 100.0,
            p_kw,
            max(crest, 0.0),
            abs(freq - 50.0),
        ],
        dtype=np.float64,
    )


def synthesize_healthy_rows(n: int, rng: np.random.Generator) -> np.ndarray:
    """Draw the healthy operating envelope used to fit the Isolation Forest.

    The ranges are deliberately wider than "lab clean" so ordinary load steps,
    inverter ripple and ADC noise do not look like faults.
    """
    v = rng.normal(230.0, 4.5, n)
    i = rng.uniform(0.3, 10.5, n)
    pf = rng.uniform(0.90, 1.0, n)
    thd_v = rng.uniform(0.6, 5.5, n)
    thd_i = rng.uniform(1.0, 10.0, n)
    crest = rng.uniform(1.30, 1.70, n)
    freq_dev = np.abs(rng.normal(0.0, 0.05, n))
    rows = np.column_stack(
        [
            v / V_NOMINAL,
            i / I_RATED,
            pf,
            thd_v / 100.0,
            thd_i / 100.0,
            v * i * pf / 1000.0,
            crest,
            freq_dev,
        ]
    )
    return rows


def synthesize_degraded_rows(n: int, rng: np.random.Generator) -> np.ndarray:
    """Chronic-degradation signatures (loose terminals, ageing insulation, heat).

    These are *not* used for fitting.  They only measure whether the detector
    generalises to the failure mode it is supposed to catch.
    """
    v = rng.uniform(198.0, 224.0, n)
    i = rng.uniform(6.0, 11.0, n)
    pf = rng.uniform(0.68, 0.90, n)
    thd_v = rng.uniform(7.0, 20.0, n)
    thd_i = rng.uniform(14.0, 42.0, n)
    crest = rng.uniform(1.55, 2.10, n)
    freq_dev = np.abs(rng.normal(0.09, 0.05, n))
    return np.column_stack(
        [
            v / V_NOMINAL,
            i / I_RATED,
            pf,
            thd_v / 100.0,
            thd_i / 100.0,
            v * i * pf / 1000.0,
            crest,
            freq_dev,
        ]
    )
