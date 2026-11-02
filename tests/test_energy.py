"""Net-metering and energy integration tests."""
from __future__ import annotations

import unittest

from cloud.energy import EnergyMeter, net_current, net_power_kw


class EnergyTests(unittest.TestCase):
    def test_net_current_and_power(self) -> None:
        self.assertAlmostEqual(net_current(8.0, 3.0), 5.0)
        self.assertAlmostEqual(net_power_kw(230.0, 5.0), 1.15)

    def test_import_and_export_accumulate_separately(self) -> None:
        meter = EnergyMeter()
        imported = meter.update(230.0, 10.0, 2.0, 60.0)
        self.assertAlmostEqual(imported["p_net_kw"], 230.0 * 8.0 / 1000.0)
        self.assertAlmostEqual(imported["energy_import_kwh"], 1.84 * 60 / 3600)
        self.assertEqual(imported["energy_export_kwh"], 0.0)

        exported = meter.update(230.0, 1.0, 6.0, 60.0)
        self.assertLess(exported["p_net_kw"], 0.0)
        self.assertAlmostEqual(exported["energy_export_kwh"], 1.15 * 60 / 3600)
        self.assertAlmostEqual(exported["energy_import_kwh"], 1.84 * 60 / 3600)

    def test_negative_and_huge_dt_are_clamped(self) -> None:
        meter = EnergyMeter()
        self.assertEqual(meter.update(230, 5, 0, -10)["energy_import_kwh"], 0.0)
        meter.update(230, 5, 0, 60)
        self.assertAlmostEqual(meter.import_kwh, 1.15 * 60 / 3600)
        meter.update(230, 5, 0, 999999)  # clamped to 60 s
        self.assertAlmostEqual(meter.import_kwh, 2 * 1.15 * 60 / 3600)

    def test_snapshot(self) -> None:
        meter = EnergyMeter(import_kwh=2.0, export_kwh=0.5)
        self.assertEqual(meter.snapshot(), {"energy_import_kwh": 2.0, "energy_export_kwh": 0.5})


if __name__ == "__main__":
    unittest.main()
