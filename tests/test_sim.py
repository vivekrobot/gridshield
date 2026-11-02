"""Simulator behaviour that mirrors the firmware safety state machine."""
from __future__ import annotations

import unittest

import numpy as np

from cloud.safety import Limits
from ml.infer import PQDClassifier
from sim.node import SimulatedNode


class SimulatorResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.classifier = PQDClassifier()

    def make_node(self) -> SimulatedNode:
        spec = {
            "device_id": "node-test",
            "name": "Test household",
            "rated_current_a": 12.0,
            "solar_kwp": 0.0,
        }
        return SimulatedNode(
            spec=spec,
            classifier=self.classifier,
            rng=np.random.default_rng(7),
            auto_reset_s=0.0,
            limits=Limits(trip_confirm=1, reset_confirm=3),
        )

    def test_reset_request_requires_consecutive_samples(self) -> None:
        node = self.make_node()
        now = 1_000.0
        node.step(0.0, 1.0, now)
        node.safety.force_trip("REMOTE")
        node.reset()

        # The request stays armed across ticks; only the third in-envelope
        # sample re-closes the relay.
        self.assertTrue(node.step(1.0, 1.0, now + 1).get("tripped"))
        self.assertTrue(node.step(2.0, 1.0, now + 2).get("tripped"))
        payload = node.step(3.0, 1.0, now + 3.0)
        self.assertFalse(payload["tripped"])
        self.assertEqual(payload["relay"], "CLOSED")
        self.assertIsNone(payload["fault_code"])
        self.assertFalse(node.reset_pending)

    def test_reset_request_expires(self) -> None:
        node = self.make_node()
        node.safety.force_trip("REMOTE")
        node.reset()
        node.reset_deadline = 0.0  # force the 30 s request window to be over
        payload = node.step(1.0, 1.0, 10.0)
        self.assertTrue(payload["tripped"])
        self.assertFalse(node.reset_pending)


if __name__ == "__main__":
    unittest.main()
