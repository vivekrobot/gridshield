"""Topic-routing tests for the MQTT ingestor (no broker required)."""
from __future__ import annotations

import unittest

from cloud.ingest import device_from_topic, parse_args


class IngestTopicTests(unittest.TestCase):
    def test_standard_topic(self) -> None:
        self.assertEqual(
            device_from_topic("smart_grid/households/node-001/telemetry"),
            "node-001",
        )

    def test_multi_segment_prefix(self) -> None:
        self.assertEqual(
            device_from_topic("site/a/households/node-9/telemetry", prefix="site/a"),
            "node-9",
        )

    def test_rejects_commands_and_system_topics(self) -> None:
        for topic in (
            "smart_grid/households/node-001/cmd",
            "smart_grid/households/node-001/telemetry/extra",
            "smart_grid/other/node-001/telemetry",
            "$SYS/broker/uptime",
            "",
        ):
            with self.subTest(topic=topic):
                self.assertIsNone(device_from_topic(topic))

    def test_cli_defaults(self) -> None:
        args = parse_args([])
        self.assertEqual(args.duration, 0.0)
        self.assertFalse(args.no_anomaly)
        self.assertEqual(args.offline_check, 15.0)


if __name__ == "__main__":
    unittest.main()
