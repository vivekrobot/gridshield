"""SQLite store tests (WAL, history, alerts, commands, pruning)."""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from cloud.models import Telemetry
from cloud.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.db")
        self.store.upsert_node("node-001", "Test site", 28.5, 77.1, meta={"feeder": "F-1"})

    def tearDown(self) -> None:
        self.temp.cleanup()

    def telemetry(self, **overrides) -> Telemetry:
        data = {
            "device_id": "node-001",
            "v_rms": 230.0,
            "i_load": 4.0,
            "i_solar": 1.0,
            "pf": 0.98,
            "ai_class": "NORMAL",
            "ai_conf": 0.9,
            "relay": "CLOSED",
            "tripped": False,
        }
        data.update(overrides)
        return Telemetry.from_payload(data)

    def test_seed_and_nodes(self) -> None:
        self.assertEqual(len(self.store.nodes()), 1)
        self.assertEqual(self.store.nodes()[0]["name"], "Test site")

    def test_insert_latest_and_history(self) -> None:
        first = self.telemetry()
        self.store.insert_telemetry(first.to_row(), wave={"v": [1.0] * 80, "i": [0.5] * 80})
        second = self.telemetry(i_load=6.0)
        self.store.insert_telemetry(second.to_row())

        latest = self.store.latest("node-001")
        assert latest is not None
        self.assertAlmostEqual(latest["i_load"], 6.0)
        self.assertEqual(len(self.store.history("node-001", minutes=15)), 2)
        self.assertEqual(len(self.store.history_since("node-001", time.time() - 60)), 2)

        wave = self.store.waveform("node-001")
        assert wave is not None
        self.assertEqual(len(wave["v"]), 80)

    def test_telemetry_requires_known_node(self) -> None:
        import sqlite3

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.insert_telemetry(self.telemetry(device_id="node-404").to_row())

    def test_alert_cooldown_and_acknowledge(self) -> None:
        self.assertTrue(self.store.add_alert("node-001", "warning", "TEST", "first", cooldown_seconds=60))
        self.assertFalse(self.store.add_alert("node-001", "warning", "TEST", "second", cooldown_seconds=60))
        alerts = self.store.alerts(limit=10)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["acknowledged"], 0)
        self.store.acknowledge_alert(alerts[0]["id"])
        self.assertEqual(len(self.store.alerts(only_unacknowledged=True)), 0)

    def test_commands_are_logged(self) -> None:
        self.store.log_command("node-001", "inject", {"fault": "VOLTAGE_SAG"}, "sent")
        commands = self.store.commands()
        self.assertEqual(commands[0]["action"], "inject")
        self.assertEqual(commands[0]["status"], "sent")

    def test_prune_removes_old_rows(self) -> None:
        old = self.telemetry()
        row = old.to_row()
        row["ts_epoch"] = time.time() - 86400 * 10
        self.store.insert_telemetry(row)
        self.store.insert_telemetry(self.telemetry().to_row())
        self.assertEqual(self.store.counts()["telemetry"], 2)
        removed = self.store.prune(retention_days=5)
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.counts()["telemetry"], 1)

    def test_counts(self) -> None:
        self.store.insert_telemetry(self.telemetry().to_row())
        self.store.add_alert("node-001", "info", "HELLO", "test")
        self.assertEqual(self.store.counts(), {"telemetry": 1, "alerts": 1, "nodes": 1})


if __name__ == "__main__":
    unittest.main()
