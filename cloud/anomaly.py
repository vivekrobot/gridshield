"""Cloud-side wrapper around the Isolation Forest artifact."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import joblib
import numpy as np

from ml.config import ANOMALY_META_PATH, ANOMALY_MODEL_PATH
from ml.features import telemetry_features


@dataclass(frozen=True)
class AnomalyResult:
    score: float
    threshold: float
    is_anomaly: bool
    health_index: float


class AnomalyDetector:
    def __init__(self, model_path: str | Path = ANOMALY_MODEL_PATH, meta_path: str | Path = ANOMALY_META_PATH):
        bundle = joblib.load(model_path)
        self.scaler = bundle["scaler"]
        self.model = bundle["model"]
        self.threshold = float(bundle["threshold"])
        self.feature_names = tuple(bundle.get("feature_names", []))
        quantiles = bundle.get("score_quantiles", {"p50": self.threshold * 0.6, "p99": self.threshold * 1.4})
        self.p50 = float(quantiles.get("p50", 0.0))
        self.p99 = float(quantiles.get("p99", max(self.threshold * 1.5, 1e-6)))
        self.meta = {}
        if Path(meta_path).exists():
            self.meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))

    def score_features(self, features: np.ndarray) -> AnomalyResult:
        vector = np.asarray(features, dtype=np.float64).reshape(1, -1)
        score = float(-self.model.score_samples(self.scaler.transform(vector))[0])
        if score <= self.threshold:
            span = max(self.threshold - self.p50, 1e-9)
            health = 100.0 - 20.0 * min(max((score - self.p50) / span, 0.0), 1.0)
        else:
            ceiling = max(self.p99 * 1.5, self.threshold * 1.2)
            span = max(ceiling - self.threshold, 1e-9)
            health = 80.0 * (1.0 - min(max((score - self.threshold) / span, 0.0), 1.0))
        return AnomalyResult(
            score=score,
            threshold=self.threshold,
            is_anomaly=score > self.threshold,
            health_index=health,
        )

    def score_row(self, row: Mapping[str, float]) -> AnomalyResult:
        return self.score_features(telemetry_features(row))
