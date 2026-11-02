"""Common ingestion pipeline used by both MQTT and the offline simulator."""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from typing import Any

from .anomaly import AnomalyDetector
from .config import ALERT_COOLDOWN_SECONDS, ANOMALY_ROLLING_WINDOW, NODE_OFFLINE_SECONDS
from .models import Telemetry
from .safety import Limits, SafetyEvaluator
from .store import Store


class TelemetryPipeline:
    def __init__(
        self,
        store: Store,
        detector: AnomalyDetector | None = None,
        limits: Limits | None = None,
        rolling_window: int = ANOMALY_ROLLING_WINDOW,
    ):
        self.store = store
        self.detector = detector
        self.limits = limits or Limits()
        self.rolling_window = max(3, rolling_window)
        self._safety: dict[str, SafetyEvaluator] = {}
        self._scores: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=self.rolling_window))
        self._last_tripped: dict[str, bool] = {}
        self._last_degraded: dict[str, bool] = {}
        self._known_nodes: set[str] = {n["device_id"] for n in store.nodes()}

    def _evaluator(self, device_id: str) -> SafetyEvaluator:
        if device_id not in self._safety:
            self._safety[device_id] = SafetyEvaluator(self.limits)
        return self._safety[device_id]

    def process(self, payload: dict[str, Any] | bytes | str, received_at: float | None = None) -> dict[str, Any]:
        t = payload if isinstance(payload, Telemetry) else Telemetry.from_payload(payload, received_at)
        if t.device_id not in self._known_nodes:
            self.store.upsert_node(t.device_id, t.device_id)
            self._known_nodes.add(t.device_id)

        row = t.to_row()
        anomaly = self.detector.score_row(row) if self.detector is not None else None

        rolling_median: float | None = None
        degraded = False
        if anomaly is not None:
            scores = self._scores[t.device_id]
            scores.append(anomaly.score)
            ordered = sorted(scores)
            rolling_median = ordered[len(ordered) // 2]
            # Require a margin above the 95th-percentile training score and a
            # minimum number of observations; single borderline points are not
            # a maintenance signal.
            sustained = len(scores) >= min(10, self.rolling_window)
            degraded = sustained and rolling_median > anomaly.threshold * 1.10

        # -------- safety mirror -------------------------------------------
        evaluator = self._evaluator(t.device_id)
        if t.tripped and not evaluator.tripped:
            evaluator.force_trip(t.fault_code or "NODE_REPORTED_TRIP")
        elif not t.tripped and evaluator.tripped:
            # The edge node is authoritative: it may have auto-reclosed after
            # its own reset confirmation. Re-arm the cloud mirror immediately.
            evaluator.force_reset()
        expected = evaluator.evaluate(t.v_rms, t.i_load, t.ai_class, t.ai_conf)
        mismatch = bool(t.tripped) != expected.tripped

        # -------- alerts ---------------------------------------------------
        alerts: list[str] = []
        was_tripped = self._last_tripped.get(t.device_id, False)
        if t.tripped and not was_tripped:
            if self.store.add_alert(
                t.device_id,
                "critical",
                "TRIP",
                f"{t.device_id}: relay opened ({t.fault_code or 'unknown'}) at "
                f"V={t.v_rms:.1f} V, I={t.i_load:.2f} A"
                + (" (post-trip)" if t.i_load == 0 else ""),
                cooldown_seconds=30,
            ):
                alerts.append("TRIP")
        self._last_tripped[t.device_id] = t.tripped

        if t.ai_class == "SHORT_CIRCUIT_OVERLOAD" and t.ai_conf >= 0.85:
            if self.store.add_alert(
                t.device_id,
                "critical",
                "AI_OVERLOAD",
                f"{t.device_id}: edge AI detected SHORT_CIRCUIT_OVERLOAD "
                f"({t.ai_conf:.2f}) at {t.i_load:.2f} A",
                cooldown_seconds=ALERT_COOLDOWN_SECONDS,
            ):
                alerts.append("AI_OVERLOAD")

        was_degraded = self._last_degraded.get(t.device_id, False)
        if degraded and not was_degraded and anomaly is not None:
            if self.store.add_alert(
                t.device_id,
                "warning",
                "DEGRADATION_WARNING",
                f"{t.device_id}: predictive maintenance flagged component degradation "
                f"(health {anomaly.health_index:.0f}/100, score {anomaly.score:.2f})",
                cooldown_seconds=ALERT_COOLDOWN_SECONDS,
            ):
                alerts.append("DEGRADATION_WARNING")
        self._last_degraded[t.device_id] = degraded

        if mismatch:
            if self.store.add_alert(
                t.device_id,
                "warning",
                "SAFETY_MISMATCH",
                f"{t.device_id}: reported relay={t.relay} but rules expect "
                f"{'OPEN' if expected.tripped else 'CLOSED'}",
                cooldown_seconds=ALERT_COOLDOWN_SECONDS,
            ):
                alerts.append("SAFETY_MISMATCH")

        safe_payload = {k: v for k, v in t.raw.items() if k != "wave"}
        self.store.insert_telemetry(
            row,
            wave=t.wave or None,
            anomaly_score=anomaly.score if anomaly else None,
            health_index=anomaly.health_index if anomaly else None,
            degraded=degraded,
            payload_json=json.dumps(safe_payload, separators=(",", ":")),
        )

        return {
            "telemetry": t,
            "anomaly": anomaly,
            "rolling_score": rolling_median,
            "degraded": degraded,
            "expected_trip": expected.tripped,
            "mismatch": mismatch,
            "alerts": alerts,
        }


def check_offline_nodes(store: Store, threshold_seconds: int = NODE_OFFLINE_SECONDS) -> list[str]:
    """Create an alert for every node that has gone silent. Returns device ids."""
    latest = store.latest_by_node()
    now = time.time()
    offline: list[str] = []
    for node in store.nodes():
        device_id = node["device_id"]
        row = latest.get(device_id)
        if not row:
            continue
        age = now - float(row["ts_epoch"])
        if age > threshold_seconds:
            offline.append(device_id)
            store.add_alert(
                device_id,
                "warning",
                "NODE_OFFLINE",
                f"{device_id}: no telemetry for {age:.0f} s (threshold {threshold_seconds} s)",
                cooldown_seconds=max(60, ALERT_COOLDOWN_SECONDS),
            )
    return offline
