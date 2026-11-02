"""Safety interlock tests, mirroring the firmware rule base."""
from __future__ import annotations

import unittest

from cloud.safety import Limits, SafetyEvaluator


def evaluator(**overrides) -> SafetyEvaluator:
    values = dict(trip_confirm=3, reset_confirm=3)
    values.update(overrides)
    return SafetyEvaluator(Limits(**values))


class SafetyTests(unittest.TestCase):
    def test_overcurrent_requires_confirmation(self) -> None:
        safety = evaluator()
        self.assertFalse(safety.evaluate(230, 13.0).tripped)
        self.assertFalse(safety.evaluate(230, 13.0).tripped)
        state = safety.evaluate(230, 13.0)
        self.assertTrue(state.tripped)
        self.assertTrue(state.newly_tripped)
        self.assertEqual(safety.fault_code, "OVERCURRENT")

    def test_single_spike_does_not_trip(self) -> None:
        safety = evaluator()
        safety.evaluate(230, 20.0)
        safety.evaluate(230, 4.0)
        self.assertFalse(safety.evaluate(230, 4.0).tripped)

    def test_undervoltage_and_overvoltage(self) -> None:
        low = evaluator()
        for _ in range(3):
            low.evaluate(170.0, 3.0)
        self.assertEqual(low.fault_code, "UNDERVOLTAGE")

        high = evaluator()
        for _ in range(3):
            high.evaluate(280.0, 3.0)
        self.assertEqual(high.fault_code, "OVERVOLTAGE")

    def test_ai_only_trips_above_confidence(self) -> None:
        safety = evaluator(ai_trip_confidence=0.85)
        for _ in range(3):
            safety.evaluate(230, 4.0, "SHORT_CIRCUIT_OVERLOAD", 0.84)
        self.assertFalse(safety.tripped)

        for _ in range(3):
            safety.evaluate(230, 4.0, "SHORT_CIRCUIT_OVERLOAD", 0.92)
        self.assertTrue(safety.tripped)
        self.assertEqual(safety.fault_code, "AI_OVERLOAD")

    def test_trip_latches_until_safe_reset(self) -> None:
        safety = evaluator()
        for _ in range(3):
            safety.evaluate(230, 13.0)
        self.assertTrue(safety.tripped)

        for _ in range(10):
            safety.evaluate(260.0, 0.0)  # outside the reset voltage envelope
        for _ in range(3):
            self.assertFalse(safety.safe_to_reset(260.0, 0.0))
        self.assertFalse(safety.reset(260.0, 0.0))
        self.assertTrue(safety.tripped)

        self.assertTrue(safety.safe_to_reset(230.0, 0.0))
        # Reset confirmation is debounced: the relay only re-closes after the
        # configured number of consecutive in-envelope samples.
        for _ in range(safety.limits.reset_confirm - 1):
            self.assertFalse(safety.reset(230.0, 0.0))
        self.assertTrue(safety.tripped)
        self.assertTrue(safety.reset(230.0, 0.0))
        self.assertFalse(safety.tripped)
        self.assertIsNone(safety.fault_code)

    def test_reset_counter_drops_on_unsafe_sample(self) -> None:
        safety = evaluator()
        safety.force_trip("REMOTE")
        self.assertFalse(safety.reset(230.0, 0.0))
        self.assertFalse(safety.reset(230.0, 0.0))
        # A single out-of-envelope sample must discard the progress.
        self.assertFalse(safety.reset(260.0, 0.0))
        for _ in range(safety.limits.reset_confirm - 1):
            self.assertFalse(safety.reset(230.0, 0.0))
        self.assertTrue(safety.reset(230.0, 0.0))
        self.assertFalse(safety.tripped)

    def test_force_trip_and_reset(self) -> None:
        safety = evaluator()
        safety.force_trip("REMOTE")
        self.assertTrue(safety.tripped)
        self.assertEqual(safety.fault_code, "REMOTE")
        safety.force_reset()
        self.assertFalse(safety.tripped)


if __name__ == "__main__":
    unittest.main()

