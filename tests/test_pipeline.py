"""End-to-end ingestion pipeline tests, including the safety mirror."""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from cloud.anomaly import AnomalyDetector
from cloud.pipeline import TelemetryPipeline
from cloud.store import Store


def payload(**overrides):
    base = {
        "device_id": "node-001",
        "v_rms": 230.0,
        "i_load": 4.0,
        "i_solar": 1.0,
        "pf": 0.98,
        "freq": 50.0,
        "thd_v": 2.0,
        "thd_i": 4.0,
        "crest_i": 1.42,
        "ai_class": "NORMAL",
        "ai_conf": 0.95,
        "relay": "CLOSED",
        "tripped": False,
        "ts": time.time(),
    }
    base.update(overrides)
    return base


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "pipeline.db")
        self.store.upsert_node("node-001", "Test site")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_normal_packet_is_stored(self) -> None:
        pipeline = TelemetryPipeline(self.store)
        result = pipeline.process(payload())
        self.assertFalse(result["mismatch"])
        self.assertEqual(result["alerts"], [])
        self.assertEqual(self.store.counts()["telemetry"], 1)

    def test_reported_trip_creates_alert(self) -> None:
        pipeline = TelemetryPipeline(self.store)
        result = pipeline.process(payload(tripped=True, relay="OPEN", fault_code="OVERCURRENT", i_load=0.0))
        self.assertIn("TRIP", result["alerts"])
        alerts = self.store.alerts(limit=10)
        self.assertEqual(alerts[0]["code"], "TRIP")

    def test_cloud_detects_mismatch_when_relay_stays_closed(self) -> None:
        pipeline = TelemetryPipeline(self.store)
        # 15 A for three packets should trip the cloud mirror while the node
        # still claims the relay is closed.
        for _ in range(3):
            result = pipeline.process(payload(i_load=15.0))
        self.assertTrue(result["expected_trip"])
        self.assertTrue(result["mismatch"])
        self.assertIn("SAFETY_MISMATCH", result["alerts"])

    def test_ai_overload_alert(self) -> None:
        pipeline = TelemetryPipeline(self.store)
        result = pipeline.process(payload(ai_class="SHORT_CIRCUIT_OVERLOAD", ai_conf=0.93))
        self.assertIn("AI_OVERLOAD", result["alerts"])

    def test_sustained_degradation_alert(self) -> None:
        detector = AnomalyDetector()
        pipeline = TelemetryPipeline(self.store, detector)
        degraded = dict(
            v_rms=205.0,
            i_load=9.0,
            pf=0.72,
            thd_v=18.0,
            thd_i=36.0,
            crest_i=2.0,
            p_active=1.3,
            freq=50.12,
        )
        result = None
        seen_alerts = []
        for _ in range(12):
            result = pipeline.process(payload(**degraded))
            seen_alerts.extend(result["alerts"])
        assert result is not None
        self.assertTrue(result["degraded"])
        self.assertIsNotNone(result["rolling_score"])
        self.assertGreater(result["rolling_score"], detector.threshold * 1.10)
        self.assertIn("DEGRADATION_WARNING", seen_alerts)

    def test_unknown_device_is_registered(self) -> None:
        pipeline = TelemetryPipeline(self.store)
        pipeline.process(payload(device_id="node-999"))
        ids = [node["device_id"] for node in self.store.nodes()]
        self.assertIn("node-999", ids)


if __name__ == "__main__":
    unittest.main()
