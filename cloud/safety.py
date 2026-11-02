"""Python mirror of the firmware safety interlock (used for tests and the sim).

The real trip decision is made on the ESP32.  This module exists to
(a) unit-test the rule base, (b) let the simulator behave like the firmware,
and (c) let the cloud flag a mismatch between the reported and expected state.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import (
    AI_TRIP_CONFIDENCE,
    I_RESET_A,
    I_TRIP_A,
    RESET_CONFIRM_SAMPLES,
    TRIP_CONFIRM_SAMPLES,
    V_MAX_TRIP,
    V_MIN_TRIP,
    V_RESET_MAX,
    V_RESET_MIN,
)


@dataclass(frozen=True)
class Limits:
    i_trip_a: float = I_TRIP_A
    v_min: float = V_MIN_TRIP
    v_max: float = V_MAX_TRIP
    i_reset_a: float = I_RESET_A
    v_reset_min: float = V_RESET_MIN
    v_reset_max: float = V_RESET_MAX
    trip_confirm: int = TRIP_CONFIRM_SAMPLES
    reset_confirm: int = RESET_CONFIRM_SAMPLES
    ai_trip_confidence: float = AI_TRIP_CONFIDENCE


@dataclass(frozen=True)
class TripState:
    tripped: bool
    fault_code: str | None
    reason: str
    newly_tripped: bool = False


class SafetyEvaluator:
    """Latching interlock with confirmation counts (debounce)."""

    def __init__(self, limits: Limits | None = None):
        self.limits = limits or Limits()
        self.tripped = False
        self.fault_code: str | None = None
        self._trip_count = 0
        self._reset_count = 0

    def evaluate(
        self,
        v_rms: float,
        i_load: float,
        ai_class: str = "NORMAL",
        ai_conf: float = 0.0,
    ) -> TripState:
        if self.tripped:
            return TripState(True, self.fault_code, "latched")

        reason = ""
        code = None
        if i_load > self.limits.i_trip_a:
            reason, code = f"over-current {i_load:.1f} A", "OVERCURRENT"
        elif v_rms < self.limits.v_min:
            reason, code = f"under-voltage {v_rms:.1f} V", "UNDERVOLTAGE"
        elif v_rms > self.limits.v_max:
            reason, code = f"over-voltage {v_rms:.1f} V", "OVERVOLTAGE"

        if not reason and ai_class == "SHORT_CIRCUIT_OVERLOAD" and ai_conf >= self.limits.ai_trip_confidence:
            reason, code = f"edge AI overload ({ai_conf:.2f})", "AI_OVERLOAD"

        self._trip_count = self._trip_count + 1 if reason else 0
        if self._trip_count >= max(1, self.limits.trip_confirm):
            self.tripped = True
            self.fault_code = code
            self._reset_count = 0
            return TripState(True, code, reason or "trip", newly_tripped=True)

        return TripState(False, None, "armed" if not reason else f"pending: {reason}")

    def safe_to_reset(self, v_rms: float, i_load: float) -> bool:
        """True when the current sample is inside the reset envelope.

        This is a pure predicate (no state change).  The confirmation count is
        accumulated by :meth:`reset`, mirroring the firmware, where a human
        reset request arms the counter and each subsequent evaluation adds one
        sample while the measurements stay in the envelope.
        """
        return (
            i_load <= self.limits.i_reset_a
            and self.limits.v_reset_min <= v_rms <= self.limits.v_reset_max
        )

    def reset(self, v_rms: float, i_load: float) -> bool:
        """Feed one reset-confirmation sample; return True when re-closed.

        Consecutive in-envelope samples are required (``reset_confirm``).  Any
        sample outside the envelope drops the counter to zero, so a single
        good reading can never re-close the relay.
        """
        if not self.tripped:
            return True
        if not self.safe_to_reset(v_rms, i_load):
            self._reset_count = 0
            return False
        self._reset_count += 1
        if self._reset_count < max(1, self.limits.reset_confirm):
            return False
        self.tripped = False
        self.fault_code = None
        self._trip_count = 0
        self._reset_count = 0
        return True

    def force_trip(self, code: str = "REMOTE") -> None:
        self.tripped = True
        self.fault_code = code
        self._trip_count = 0
        self._reset_count = 0

    def force_reset(self) -> None:
        """Trust an explicit, safe CLOSED report from the edge node."""
        self.tripped = False
        self.fault_code = None
        self._trip_count = 0
        self._reset_count = 0
