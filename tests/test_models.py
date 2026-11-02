"""Telemetry contract validation tests."""
from __future__ import annotations

import json
import time
import unittest

from cloud.models import PayloadError, Telemetry


def payload(**overrides):
    base = {
        "device_id": "node-001",
        "v_rms": 230.0,
        "i_load": 4.0,
        "i_solar": 1.0,
        "pf": 0.98,
        "freq": 50.0,
        "ai_class": "NORMAL",
        "ai_conf": 0.99,
        "relay": "CLOSED",
        "tripped": False,
        "wave": {"v": [0.0] * 80, "i": [0.0] * 80},
    }
    base.update(overrides)
    return base


class ModelTests(unittest.TestCase):
    def test_defaults_and_net_power(self) -> None:
        telemetry = Telemetry.from_payload(payload())
        self.assertAlmostEqual(telemetry.p_net_kw, 230.0 * 3.0 / 1000.0)
        self.assertEqual(telemetry.relay, "CLOSED")
        self.assertEqual(len(telemetry.wave["v"]), 80)
        self.assertEqual(telemetry.ai_class, "NORMAL")

    def test_millisecond_timestamp(self) -> None:
        now = time.time()
        telemetry = Telemetry.from_payload(payload(ts=int(now * 1000)))
        self.assertAlmostEqual(telemetry.ts_epoch, now, delta=5)

    def test_missing_optional_fields_get_safe_defaults(self) -> None:
        telemetry = Telemetry.from_payload({"device_id": "node-002", "v_rms": 230, "i_load": 2})
        self.assertEqual(telemetry.i_solar, 0.0)
        self.assertEqual(telemetry.relay, "CLOSED")
        self.assertEqual(telemetry.ai_conf, 0.0)

    def test_invalid_device_id_rejected(self) -> None:
        for bad in ("", "../etc/passwd", "node 001", "x" * 65):
            with self.assertRaises(PayloadError):
                Telemetry.from_payload(payload(device_id=bad))

    def test_implausible_values_rejected(self) -> None:
        with self.assertRaises(PayloadError):
            Telemetry.from_payload(payload(v_rms=500))
        with self.assertRaises(PayloadError):
            Telemetry.from_payload(payload(i_load=-1))
        with self.assertRaises(PayloadError):
            Telemetry.from_payload(payload(pf=1.2))
        with self.assertRaises(PayloadError):
            Telemetry.from_payload(payload(freq=500))

    def test_invalid_relay_rejected(self) -> None:
        with self.assertRaises(PayloadError):
            Telemetry.from_payload(payload(relay="MAYBE"))

    def test_non_json_rejected(self) -> None:
        with self.assertRaises(PayloadError):
            Telemetry.from_payload(b"{not json")
        with self.assertRaises(PayloadError):
            Telemetry.from_payload(json.dumps([1, 2, 3]))

    def test_wave_length_filtered(self) -> None:
        short = Telemetry.from_payload(payload(wave={"v": [0] * 7, "i": [0] * 7}))
        self.assertEqual(short.wave, {})
        long = Telemetry.from_payload(payload(wave={"v": [0] * 200, "i": [0] * 200}))
        self.assertEqual(long.wave, {})

    def test_oversized_payload_rejected(self) -> None:
        with self.assertRaises(PayloadError):
            Telemetry.from_payload(payload(note="x" * 9000))

    def test_row_has_schema_columns(self) -> None:
        row = Telemetry.from_payload(payload()).to_row()
        for column in ("device_id", "ts_utc", "ts_epoch", "v_rms", "i_load", "tripped", "relay"):
            self.assertIn(column, row)
        self.assertEqual(row["tripped"], 0)

    def test_bool_relay_is_normalised(self) -> None:
        telemetry = Telemetry.from_payload(payload(relay=True))
        self.assertEqual(telemetry.relay, "CLOSED")


if __name__ == "__main__":
    unittest.main()
