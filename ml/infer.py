"""Inference helpers for the cloud simulator and tests."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .cnn import CNN1D
from .config import CLASSES, I_SCALE, MODEL_CARD_PATH, V_SCALE, WEIGHTS_PATH, WINDOW


class PQDClassifier:
    """Loads the trained 1D-CNN and classifies physical (V, I) windows."""

    def __init__(self, weights_path: str | Path = WEIGHTS_PATH, model_card_path: str | Path = MODEL_CARD_PATH):
        self.model = CNN1D.load(weights_path)
        self.classes = tuple(self.model.meta.get("classes", CLASSES))
        self.card = {}
        if Path(model_card_path).exists():
            self.card = json.loads(Path(model_card_path).read_text(encoding="utf-8"))
        input_info = self.card.get("input", {})
        self.v_scale = float(input_info.get("v_scale_volts", V_SCALE))
        self.i_scale = float(input_info.get("i_scale_amps", I_SCALE))

    def normalise(self, window: np.ndarray) -> np.ndarray:
        window = np.asarray(window, dtype=np.float32)
        if window.shape != (WINDOW, 2):
            raise ValueError(f"expected waveform ({WINDOW}, 2), got {window.shape}")
        out = window.copy()
        out[:, 0] /= self.v_scale
        out[:, 1] /= self.i_scale
        return out

    def predict_window(self, window: np.ndarray) -> dict:
        probs = self.model.predict_proba(self.normalise(window)[None, ...])[0]
        idx = int(probs.argmax())
        return {
            "class": self.classes[idx],
            "confidence": float(probs[idx]),
            "probabilities": {name: float(p) for name, p in zip(self.classes, probs)},
        }

    def predict_batch(self, windows: np.ndarray) -> np.ndarray:
        batch = np.stack([self.normalise(w) for w in windows])
        return self.model.predict(batch)
