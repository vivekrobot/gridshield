"""Dashboard rendering helpers (no Streamlit server required)."""
from __future__ import annotations

import time
import unittest

from dashboard import components as C


def row(**overrides):
    base = {
        "device_id": "node-001",
        "ts_epoch": time.time(),
        "v_rms": 230.0,
        "i_load": 4.0,
        "p_net_kw": 0.69,
        "pf": 0.98,
        "freq": 50.0,
        "ai_class": "NORMAL",
        "ai_conf": 0.95,
        "health_index": 96.0,
        "relay": "CLOSED",
        "tripped": 0,
        "degraded": 0,
        "payload_json": '{"ai_probs": {"NORMAL": 0.95, "VOLTAGE_SAG": 0.05}}',
    }
    base.update(overrides)
    return base


class ComponentTests(unittest.TestCase):
    def test_fmt_handles_missing_and_infinite(self) -> None:
        self.assertEqual(C.fmt(None), "--")
        self.assertEqual(C.fmt("abc"), "--")
        self.assertEqual(C.fmt(float("nan")), "--")
        self.assertEqual(C.fmt(12.345, 2), "12.35")

    def test_node_status(self) -> None:
        now = time.time()
        self.assertEqual(C.node_status(None, now), "offline")
        self.assertEqual(C.node_status(row(ts_epoch=now - 60), now), "offline")
        self.assertEqual(C.node_status(row(ts_epoch=now), now), "normal")
        self.assertEqual(C.node_status(row(ts_epoch=now, tripped=1), now), "trip")
        self.assertEqual(C.node_status(row(ts_epoch=now, degraded=1), now), "degraded")
        self.assertEqual(C.node_status(row(ts_epoch=now, v_rms=200.0), now), "voltage")

    def test_ai_probabilities(self) -> None:
        probs = C.ai_probabilities(row())
        self.assertAlmostEqual(probs["NORMAL"], 0.95)
        self.assertEqual(C.ai_probabilities({"payload_json": "not json"}), {})
        self.assertEqual(C.ai_probabilities(None), {})

    def test_kpi_and_sections_escape_text(self) -> None:
        card = C.kpi("V", "230", "V", "<script>", "ok")
        self.assertIn("230", card)
        self.assertNotIn("<script>", card)
        self.assertIn("&lt;script&gt;", card)
        grid = C.kpi_grid([card, card])
        self.assertEqual(grid.count("gs-card"), 2)

    def test_telemetry_frame(self) -> None:
        nodes = [{"device_id": "node-001", "name": "Test"}]
        frame = C.telemetry_frame(nodes, {"node-001": row()}, time.time(), 15)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["Node"], "node-001")
        self.assertEqual(frame.iloc[0]["AI class"], "NORMAL")

    def test_alerts_frame(self) -> None:
        alerts = [
            {
                "severity": "critical",
                "ts_epoch": time.time(),
                "code": "TRIP",
                "device_id": "node-001",
                "message": "relay opened",
                "acknowledged": 0,
            }
        ]
        frame = C.alerts_frame(alerts)
        self.assertEqual(frame.iloc[0]["Code"], "TRIP")
        self.assertEqual(frame.iloc[0]["Ack"], "")

    def test_map_html_contains_markers(self) -> None:
        nodes = [{"device_id": "node-001", "name": "Test", "lat": 28.5, "lon": 77.1, "meta": {}}]
        html = C.map_html(nodes, {"node-001": row()}, time.time(), 15, (28.6, 77.2), 11)
        self.assertTrue(html)
        self.assertIn("node-001", html)
        self.assertIn("OpenStreetMap", html)


if __name__ == "__main__":
    unittest.main()
