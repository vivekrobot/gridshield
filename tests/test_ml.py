"""Model artefacts: CNN accuracy, int8 header parity, anomaly detector."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import numpy as np

from cloud.anomaly import AnomalyDetector
from ml.cnn import CNN1D
from ml.config import (
    C_HEADER_PATH,
    CONFUSION_MATRIX_PATH,
    METRICS_PATH,
    MODEL_CARD_PATH,
    PROCESSED_DIR,
    TRAIN_FRACTION,
    VAL_FRACTION,
    WEIGHTS_PATH,
)
from ml.dataset import stratified_split
from ml.features import synthesize_degraded_rows, synthesize_healthy_rows

HEADER = Path(C_HEADER_PATH)


def parse_array(text: str, name: str, cast=float) -> np.ndarray:
    match = re.search(rf"static const (?:int8_t|float) {name}\[\] = \{{(.*?)\}};", text, re.S)
    if not match:
        raise AssertionError(f"array {name} not found in header")
    values = re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", match.group(1))
    return np.asarray([cast(v) for v in values])


def parse_float(text: str, name: str) -> float:
    match = re.search(rf"static const float {name} = ([^;]+);", text)
    if not match:
        raise AssertionError(f"constant {name} not found")
    return float(match.group(1).rstrip("f"))


def header_forward(window: np.ndarray, text: str) -> np.ndarray:
    """Re-implement the firmware's weight-only int8 forward pass in NumPy."""
    w1 = parse_array(text, "kConv1W", int).reshape(5, 2, 8) * parse_float(text, "kConv1WScale")
    b1 = parse_array(text, "kConv1B").reshape(8)
    w2 = parse_array(text, "kConv2W", int).reshape(3, 8, 16) * parse_float(text, "kConv2WScale")
    b2 = parse_array(text, "kConv2B").reshape(16)
    w3 = parse_array(text, "kDense1W", int).reshape(32, 32) * parse_float(text, "kDense1WScale")
    b3 = parse_array(text, "kDense1B").reshape(32)
    w4 = parse_array(text, "kDense2W", int).reshape(32, 5) * parse_float(text, "kDense2WScale")
    b4 = parse_array(text, "kDense2B").reshape(5)
    v_scale = parse_float(text, "kInputVoltScale")
    i_scale = parse_float(text, "kInputAmpScale")

    x = window.astype(np.float64).copy()
    x[:, 0] /= v_scale
    x[:, 1] /= i_scale
    x = np.clip(x, -4.0, 4.0)

    def conv_relu(x_in: np.ndarray, w: np.ndarray, b: np.ndarray) -> np.ndarray:
        kernel, channels, filters = w.shape
        length = x_in.shape[0] - kernel + 1
        out = np.empty((length, filters))
        for p in range(length):
            cols = x_in[p : p + kernel, :].reshape(kernel * channels)
            out[p] = cols @ w.reshape(kernel * channels, filters) + b
        return np.maximum(out, 0.0)

    def maxpool(x_in: np.ndarray) -> np.ndarray:
        length = (x_in.shape[0] // 2) * 2
        return x_in[:length].reshape(length // 2, 2, x_in.shape[1]).max(axis=1)

    h = maxpool(conv_relu(x, w1, b1))
    h = maxpool(conv_relu(h, w2, b2))
    z = np.concatenate([h.mean(axis=0), h.max(axis=0)])
    hidden = np.maximum(z @ w3 + b3, 0.0)
    logits = hidden @ w4 + b4
    logits -= logits.max()
    exp = np.exp(logits)
    return exp / exp.sum()


class CnnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = CNN1D.load(WEIGHTS_PATH)
        data = np.load(PROCESSED_DIR / "pqd_dataset.npz")
        _, _, _, _, cls.x_test, cls.y_test = stratified_split(
            data["X"], data["y"], TRAIN_FRACTION, VAL_FRACTION, seed=42
        )

    def test_held_out_accuracy_matches_report(self) -> None:
        report = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        accuracy = float((self.model.predict(self.x_test) == self.y_test).mean())
        self.assertGreater(accuracy, 0.90)
        self.assertAlmostEqual(accuracy, report["test"]["accuracy"], places=6)
        self.assertTrue(CONFUSION_MATRIX_PATH.exists())
        self.assertTrue(MODEL_CARD_PATH.exists())

    def test_input_shape_is_validated(self) -> None:
        with self.assertRaises(ValueError):
            self.model.forward(np.zeros((160, 3), dtype=np.float32))

    def test_probabilities_sum_to_one(self) -> None:
        probs = self.model.predict_proba(self.x_test[:8])
        np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)

    def test_exported_int8_header_matches_fp32_model(self) -> None:
        text = HEADER.read_text(encoding="utf-8")
        agreements = 0
        for index in range(200):
            window = self.x_test[index] * np.asarray([230.0, 12.0], dtype=np.float32)
            probs = header_forward(window, text)
            agreements += int(probs.argmax() == self.model.predict(self.x_test[index : index + 1])[0])
        self.assertGreaterEqual(agreements / 200, 0.95)

    def test_header_constants_match_config(self) -> None:
        text = HEADER.read_text(encoding="utf-8")
        for name, value in {
            "GS_MODEL_INPUT_LEN": "160",
            "GS_MODEL_N_CHANNELS": "2",
            "GS_MODEL_N_CLASSES": "5",
            "GS_CONV1_FILTERS": "8",
            "GS_CONV1_KERNEL": "5",
            "GS_CONV2_FILTERS": "16",
            "GS_CONV2_KERNEL": "3",
            "GS_POOL_SIZE": "2",
            "GS_DENSE_UNITS": "32",
            "GS_L1": "156",
            "GS_L2": "76",
            "GS_L3": "38",
        }.items():
            self.assertIn(f"#define {name} {value}", text)


class AnomalyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.detector = AnomalyDetector()

    def test_threshold_matches_metadata(self) -> None:
        meta = json.loads((WEIGHTS_PATH.parent / "anomaly_meta.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(self.detector.threshold, meta["score_threshold"], places=9)

    def test_healthy_rows_score_well(self) -> None:
        rows = synthesize_healthy_rows(600, np.random.default_rng(11))
        results = [self.detector.score_features(row) for row in rows]
        false_positive_rate = sum(r.is_anomaly for r in results) / len(results)
        median_health = float(np.median([r.health_index for r in results]))
        self.assertLess(false_positive_rate, 0.12)
        self.assertGreater(median_health, 90.0)

    def test_degraded_rows_are_flagged(self) -> None:
        rows = synthesize_degraded_rows(600, np.random.default_rng(12))
        results = [self.detector.score_features(row) for row in rows]
        detection_rate = sum(r.is_anomaly for r in results) / len(results)
        median_health = float(np.median([r.health_index for r in results]))
        self.assertGreater(detection_rate, 0.95)
        self.assertLess(median_health, 70.0)


if __name__ == "__main__":
    unittest.main()
