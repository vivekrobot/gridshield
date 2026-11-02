"""Fit the unsupervised Isolation Forest for predictive maintenance.

Run:
    python -m ml.train_anomaly
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .config import ANOMALY_META_PATH, ANOMALY_MODEL_PATH, SEED
from .features import FEATURE_NAMES, synthesize_degraded_rows, synthesize_healthy_rows


def train(n_healthy: int = 5000, contamination: float = 0.05, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    healthy = synthesize_healthy_rows(n_healthy, rng)
    degraded = synthesize_degraded_rows(2000, rng)

    scaler = StandardScaler().fit(healthy)
    model = IsolationForest(
        n_estimators=300,
        max_samples="auto",
        contamination=contamination,
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(scaler.transform(healthy))

    healthy_scores = -model.score_samples(scaler.transform(healthy))
    degraded_scores = -model.score_samples(scaler.transform(degraded))
    threshold = float(np.quantile(healthy_scores, 1.0 - contamination))
    detection_rate = float((degraded_scores > threshold).mean())
    false_positive_rate = float((healthy_scores > threshold).mean())

    quantiles = {
        "p50": float(np.quantile(healthy_scores, 0.50)),
        "p90": float(np.quantile(healthy_scores, 0.90)),
        "p95": float(np.quantile(healthy_scores, 0.95)),
        "p99": float(np.quantile(healthy_scores, 0.99)),
    }

    bundle = {
        "scaler": scaler,
        "model": model,
        "threshold": threshold,
        "feature_names": list(FEATURE_NAMES),
        "score_quantiles": quantiles,
        "contamination": contamination,
        "seed": seed,
    }
    joblib.dump(bundle, ANOMALY_MODEL_PATH)

    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "IsolationForest",
        "n_estimators": 300,
        "contamination": contamination,
        "seed": seed,
        "training_rows": n_healthy,
        "feature_names": list(FEATURE_NAMES),
        "score_threshold": threshold,
        "healthy_score_quantiles": quantiles,
        "synthetic_degradation_detection_rate": detection_rate,
        "healthy_false_positive_rate": false_positive_rate,
        "notes": [
            "contamination is the *assumed* outlier fraction, not a guaranteed fault rate.",
            "Degradation rows are synthetic and only test generalisation, not field accuracy.",
            "Scores are computed on single telemetry points; the cloud also smooths them over a rolling window.",
        ],
    }
    ANOMALY_META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {ANOMALY_MODEL_PATH}")
    print(f"wrote {ANOMALY_META_PATH}")
    print(f"threshold={threshold:.4f}  degraded detection={detection_rate:.3f}  healthy FP={false_positive_rate:.3f}")
    return meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--contamination", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    train(args.rows, args.contamination, args.seed)


if __name__ == "__main__":
    main()
