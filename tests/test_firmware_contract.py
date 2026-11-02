"""Keep the firmware constants and the cloud mirror in sync."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from cloud import config as cloud_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG_H = ROOT / "firmware" / "arduino" / "gridshield_node" / "config.h"


def firmware_define(name: str) -> str:
    text = CONFIG_H.read_text(encoding="utf-8")
    match = re.search(rf"#define {name}\s+([^\s/]+)", text)
    if not match:
        raise AssertionError(f"{name} missing from config.h")
    return match.group(1)


def firmware_float(name: str) -> float:
    return float(firmware_define(name).rstrip("f"))


class FirmwareContractTests(unittest.TestCase):
    def test_safety_limits_match_cloud(self) -> None:
        self.assertAlmostEqual(firmware_float("GS_I_TRIP_A"), cloud_config.I_TRIP_A)
        self.assertAlmostEqual(firmware_float("GS_V_MIN_TRIP"), cloud_config.V_MIN_TRIP)
        self.assertAlmostEqual(firmware_float("GS_V_MAX_TRIP"), cloud_config.V_MAX_TRIP)
        self.assertAlmostEqual(firmware_float("GS_I_RESET_A"), cloud_config.I_RESET_A)
        self.assertAlmostEqual(firmware_float("GS_V_RESET_MIN"), cloud_config.V_RESET_MIN)
        self.assertAlmostEqual(firmware_float("GS_V_RESET_MAX"), cloud_config.V_RESET_MAX)
        self.assertAlmostEqual(firmware_float("GS_AI_TRIP_CONFIDENCE"), cloud_config.AI_TRIP_CONFIDENCE)
        self.assertEqual(int(firmware_define("GS_TRIP_CONFIRM_SAMPLES")), cloud_config.TRIP_CONFIRM_SAMPLES)
        self.assertEqual(int(firmware_define("GS_RESET_CONFIRM_SAMPLES")), cloud_config.RESET_CONFIRM_SAMPLES)

    def test_acquisition_matches_ml_config(self) -> None:
        from ml import config as ml_config

        self.assertEqual(int(firmware_define("GS_SAMPLE_HZ")), ml_config.FS)
        self.assertEqual(int(firmware_define("GS_WINDOW")), ml_config.WINDOW)

    def test_automatic_reclose_is_disabled(self) -> None:
        self.assertEqual(int(firmware_define("GS_AUTO_RESET_MS")), 0)

    def test_topics_match_contract(self) -> None:
        text = CONFIG_H.read_text(encoding="utf-8")
        self.assertIn('#define GS_MQTT_TOPIC_PREFIX "smart_grid"', text)
        self.assertIn("/households/%s/telemetry", (ROOT / "firmware/arduino/gridshield_node/net.cpp").read_text(encoding="utf-8"))
        self.assertIn("/households/%s/cmd", (ROOT / "firmware/arduino/gridshield_node/net.cpp").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
