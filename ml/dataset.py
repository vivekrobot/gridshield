"""Synthetic power-quality disturbance (PQD) waveform generator.

The generator is deliberately *physical*: every window is produced in volts and
amperes (not arbitrary numbers) so the saved model card, the dashboard and the
firmware all share the same calibration.

Classes
-------
NORMAL                 sinusoidal voltage/current with realistic noise
VOLTAGE_SAG            voltage amplitude collapse, with phase jump
VOLTAGE_SWELL          voltage amplitude rise
HARMONIC_DISTORTION    strong 3rd/5th/7th harmonic content on both channels
SHORT_CIRCUIT_OVERLOAD current surge well above the 12 A rating, voltage dip

A 160-sample window at 2 kHz covers four 50 Hz cycles, which is the smallest
window that still gives a stable fundamental estimate while keeping the ESP32
memory footprint small.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .config import (
    CLASSES,
    CLASS_TO_INDEX,
    FS,
    I_RATED,
    I_SCALE,
    N_CHANNELS,
    N_CLASSES,
    V_NOMINAL,
    V_SCALE,
    WINDOW,
)

V_PEAK = V_NOMINAL * np.sqrt(2.0)
HARMONIC_ORDERS = (3, 5, 7)
# Relative harmonic magnitudes used to shape the THD of a distorted waveform.
HARMONIC_SHAPE = np.array([1.0, 0.55, 0.30])
HARMONIC_SHAPE /= np.linalg.norm(HARMONIC_SHAPE)


@dataclass(frozen=True)
class Waveform:
    """One 160 x 2 window in physical units plus the ground-truth labels."""

    samples: np.ndarray          # shape (160, 2), columns = volts, amps
    label: str
    v_rms: float
    i_rms: float
    thd_v: float
    thd_i: float

    def normalised(self) -> np.ndarray:
        out = self.samples.astype(np.float32, copy=True)
        out[:, 0] /= V_SCALE
        out[:, 1] /= I_SCALE
        return out


def _time_axis(rng: np.random.Generator) -> tuple[np.ndarray, float, float]:
    t = np.arange(WINDOW, dtype=np.float64) / FS
    freq = rng.uniform(49.6, 50.4)
    phase = rng.uniform(0.0, 2.0 * np.pi)
    return t, 2.0 * np.pi * freq, phase


def _harmonic_sum(
    t: np.ndarray,
    omega: float,
    phase: float,
    thd: float,
    rng: np.random.Generator,
    phases: Iterable[float] | None = None,
) -> np.ndarray:
    """Return a harmonic train whose RMS equals ``thd`` (per unit of fundamental)."""
    if thd <= 0:
        return np.zeros_like(t)
    if phases is None:
        phases = rng.uniform(0.0, 2.0 * np.pi, size=len(HARMONIC_ORDERS))
    phases = np.asarray(tuple(phases), dtype=np.float64)
    out = np.zeros_like(t)
    for order, weight, hphase in zip(HARMONIC_ORDERS, HARMONIC_SHAPE, phases):
        # weight is an RMS fraction; convert to a peak amplitude.
        out += np.sqrt(2.0) * thd * weight * np.sin(order * (omega * t + phase) + hphase)
    return out


def _step_envelope(
    length: int, rng: np.random.Generator, min_start: int = 20, max_start: int = 70
) -> np.ndarray:
    """1.0 for the whole window or a step that starts part-way through."""
    if rng.random() < 0.55:
        return np.ones(length)
    start = int(rng.integers(min_start, max_start))
    env = np.ones(length)
    env[start:] = 0.0
    # 1 ms raised-cosine transition avoids an unrealistically sharp edge.
    ramp = max(2, int(0.001 * FS))
    edge = np.linspace(0.0, 1.0, ramp)
    env[start : start + ramp] = edge
    return env


def _phase_jump(t: np.ndarray, start: int, degrees: float) -> np.ndarray:
    out = np.zeros_like(t)
    out[start:] = np.deg2rad(degrees)
    return out


def _add_sensor_noise(
    v: np.ndarray, i: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    # Gain error, DC offset and white noise: what a real ADC + front-end gives.
    v = v * rng.normal(1.0, 0.008) + rng.normal(0.0, 0.35) + rng.normal(0.0, 2.2, v.shape)
    i = i * rng.normal(1.0, 0.010) + rng.normal(0.0, 0.02) + rng.normal(0.0, 0.06, i.shape)
    return v, i


def _assemble(
    v: np.ndarray,
    i: np.ndarray,
    label: str,
    rng: np.random.Generator,
) -> Waveform:
    v = np.clip(v, -700.0, 700.0)
    i = np.clip(i, -80.0, 80.0)
    v_rms = float(np.sqrt(np.mean(v**2)))
    i_rms = float(np.sqrt(np.mean(i**2)))
    return Waveform(
        samples=np.column_stack([v, i]).astype(np.float32),
        label=label,
        v_rms=v_rms,
        i_rms=i_rms,
        thd_v=_thd_from_window(v),
        thd_i=_thd_from_window(i),
    )


def _thd_from_window(signal: np.ndarray, fundamental_hz: float = 50.0) -> float:
    """THD of harmonics 3/5/7 using an FFT (window is an integer number of cycles)."""
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    freqs = np.fft.rfftfreq(len(signal), d=1.0 / FS)
    h1 = _peak_near(spectrum, freqs, fundamental_hz)
    if h1 <= 1e-9:
        return 0.0
    harmonics = sum(
        _peak_near(spectrum, freqs, fundamental_hz * order) ** 2 for order in HARMONIC_ORDERS
    )
    return float(np.sqrt(harmonics) / h1)


# Public alias used by the feature extractor and the simulator.
thd_from_window = _thd_from_window


def _peak_near(spectrum: np.ndarray, freqs: np.ndarray, target: float, tol: float = 20.0) -> float:
    mask = np.abs(freqs - target) <= tol
    if not np.any(mask):
        return 0.0
    return float(np.max(spectrum[mask]))


def synth_waveform(label: str, rng: np.random.Generator | None = None) -> Waveform:
    """Generate one physically consistent window for ``label``."""
    if label not in CLASS_TO_INDEX:
        raise ValueError(f"unknown class {label!r}")
    rng = rng or np.random.default_rng()
    t, omega, phase = _time_axis(rng)
    fund = omega * t + phase

    # Nominal load: 1.5 - 10.5 A, PF 0.88 - 1.0.
    i_rms_nom = rng.uniform(1.5, 10.5)
    pf = rng.uniform(0.88, 1.0)
    current_lag = np.arccos(pf)
    v_thd = rng.uniform(0.01, 0.03)
    i_thd = rng.uniform(0.02, 0.06)

    v_amp = V_PEAK * rng.uniform(0.98, 1.02)

    if label == "NORMAL":
        v = v_amp * np.sin(fund) + v_amp * _harmonic_sum(t, omega, phase, v_thd, rng)
        i = (
            np.sqrt(2.0) * i_rms_nom * np.sin(fund - current_lag)
            + np.sqrt(2.0) * i_rms_nom * _harmonic_sum(t, omega, phase, i_thd, rng)
        )

    elif label == "VOLTAGE_SAG":
        retained = rng.uniform(0.55, 0.86)
        envelope = _step_envelope(len(t), rng)
        # Voltage drops by (1 - retained) where the envelope is active.
        scale = 1.0 - (1.0 - retained) * envelope
        jump = _phase_jump(t, int(np.argmax(envelope < 0.999)) if np.any(envelope < 0.999) else 0, rng.uniform(5.0, 20.0))
        v = v_amp * scale * np.sin(fund + jump) + v_amp * _harmonic_sum(t, omega, phase, v_thd, rng)
        # Constant-power-ish load: current rises while voltage is low.
        i_rms = np.clip(i_rms_nom / max(scale.mean(), 0.55), 1.5, 11.5)
        i = (
            np.sqrt(2.0) * i_rms * np.sin(fund + jump - current_lag)
            + np.sqrt(2.0) * i_rms * _harmonic_sum(t, omega, phase, i_thd, rng)
        )

    elif label == "VOLTAGE_SWELL":
        retained = rng.uniform(1.10, 1.34)
        envelope = _step_envelope(len(t), rng)
        scale = 1.0 + (retained - 1.0) * envelope
        v = v_amp * scale * np.sin(fund) + v_amp * _harmonic_sum(t, omega, phase, v_thd, rng)
        i_rms = np.clip(i_rms_nom / max(scale.mean(), 1.0), 1.2, 10.5)
        i = (
            np.sqrt(2.0) * i_rms * np.sin(fund - current_lag)
            + np.sqrt(2.0) * i_rms * _harmonic_sum(t, omega, phase, i_thd, rng)
        )

    elif label == "HARMONIC_DISTORTION":
        v_dist = rng.uniform(0.10, 0.30)
        i_dist = rng.uniform(0.25, 0.65)
        # Flat-topped current is typical of SMPS / LED / inverter loads.
        v = v_amp * np.sin(fund) + v_amp * _harmonic_sum(t, omega, phase, v_dist, rng)
        i = np.sqrt(2.0) * i_rms_nom * np.sin(fund - current_lag) + np.sqrt(
            2.0
        ) * i_rms_nom * _harmonic_sum(
            t, omega, phase, i_dist, rng, phases=(-np.pi / 2, 0.0, np.pi / 2)
        )

    elif label == "SHORT_CIRCUIT_OVERLOAD":
        i_rms = rng.uniform(13.5, 30.0)
        retained = rng.uniform(0.80, 0.96)
        v = v_amp * retained * np.sin(fund) + v_amp * _harmonic_sum(
            t, omega, phase, rng.uniform(0.02, 0.08), rng
        )
        i = np.sqrt(2.0) * i_rms * np.sin(fund - current_lag) + np.sqrt(
            2.0
        ) * i_rms * _harmonic_sum(t, omega, phase, rng.uniform(0.03, 0.12), rng)
        # Fault inrush: decaying DC offset for the first few cycles.
        decay = np.exp(-t / 0.03)
        i += 0.35 * i_rms * decay

    else:  # pragma: no cover - guarded above
        raise AssertionError(label)

    v, i = _add_sensor_noise(v, i, rng)
    return _assemble(v, i, label, rng)


def make_dataset(
    n_per_class: int = 600,
    seed: int | None = None,
    classes: Iterable[str] = CLASSES,
) -> tuple[np.ndarray, np.ndarray, list[Waveform]]:
    """Return (X, y, waves) where X is (N, 160, 2) normalised and y is (N,)."""
    rng = np.random.default_rng(seed)
    classes = tuple(classes)
    xs: list[np.ndarray] = []
    ys: list[int] = []
    waves: list[Waveform] = []
    for label in classes:
        for _ in range(n_per_class):
            wave = synth_waveform(label, rng)
            xs.append(wave.normalised())
            ys.append(CLASS_TO_INDEX[label])
            waves.append(wave)
    X = np.stack(xs).astype(np.float32)
    y = np.asarray(ys, dtype=np.int64)
    if X.shape[1:] != (WINDOW, N_CHANNELS):  # pragma: no cover
        raise RuntimeError(f"unexpected window shape {X.shape}")
    return X, y, waves


def stratified_split(
    X: np.ndarray,
    y: np.ndarray,
    train_fraction: float,
    val_fraction: float,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Reproducible per-class split into train / val / test."""
    rng = np.random.default_rng(seed)
    train_idx: list[int] = []
    val_idx: list[int] = []
    test_idx: list[int] = []
    for cls in range(N_CLASSES):
        idx = np.flatnonzero(y == cls)
        rng.shuffle(idx)
        n_train = int(round(train_fraction * len(idx)))
        n_val = int(round(val_fraction * len(idx)))
        train_idx.extend(idx[:n_train])
        val_idx.extend(idx[n_train : n_train + n_val])
        test_idx.extend(idx[n_train + n_val :])
    return (
        X[train_idx],
        y[train_idx],
        X[val_idx],
        y[val_idx],
        X[test_idx],
        y[test_idx],
    )


def save_dataset(path, X: np.ndarray, y: np.ndarray, waves: list[Waveform]) -> None:
    import json

    np.savez_compressed(
        path,
        X=X,
        y=y,
        classes=np.array(CLASSES),
        fs=FS,
        window=WINDOW,
        v_scale=V_SCALE,
        i_scale=I_SCALE,
    )
    meta = {
        "n_samples": int(len(X)),
        "classes": list(CLASSES),
        "fs_hz": FS,
        "window_samples": WINDOW,
        "v_rms_mean_by_class": {},
    }
    for label in CLASSES:
        mask = np.array([w.label == label for w in waves])
        meta["v_rms_mean_by_class"][label] = float(np.mean([w.v_rms for w, m in zip(waves, mask) if m]))
    with open(str(path).replace(".npz", "_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)


if __name__ == "__main__":  # quick manual smoke test
    X, y, waves = make_dataset(n_per_class=5, seed=0)
    print("X", X.shape, X.dtype, "y", y.shape, "range", float(X.min()), float(X.max()))
    for label in CLASSES:
        w = next(w for w in waves if w.label == label)
        print(f"{label:26s} Vrms={w.v_rms:7.2f} Arms={w.i_rms:6.2f} THDv={w.thd_v:5.3f} THDi={w.thd_i:5.3f}")
