"""Synthetic live feed for the public Streamlit demo.

The production dashboard remains read-only: telemetry is written by
``cloud.ingest`` (hardware) or ``sim.run`` (local demo).  This module is only
activated by ``dashboard/demo_app.py`` and advances the simulation when the
Streamlit fragment refreshes, so a hosted demo is never an empty page.

No background thread is used.  That keeps Streamlit Community Cloud simple and
avoids duplicate writers when several browser sessions are open.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np

from cloud.anomaly import AnomalyResult
from cloud.models import Telemetry
from cloud.pipeline import TelemetryPipeline
from cloud.store import Store
from ml.config import ANOMALY_META_PATH
from ml.infer import PQDClassifier
from sim import profiles
from sim.node import SimulatedNode

ROOT = Path(__file__).resolve().parents[1]
NODES_PATH = ROOT / "config" / "nodes.json"

HISTORY_SECONDS = 5 * 60
SEED_TICK = 5.0
MAX_TICK_SECONDS = 15.0

# Repeated every SCENARIO_PERIOD seconds so a visitor sees every panel move.
SCENARIO = (
    (12.0, "node-001", "VOLTAGE_SAG", 8.0),
    (32.0, "node-002", "HARMONIC_DISTORTION", 8.0),
    (52.0, "node-003", "SHORT_CIRCUIT_OVERLOAD", 6.0),
    (74.0, "node-001", "VOLTAGE_SWELL", 6.0),
)
SCENARIO_PERIOD = 100.0


class SyntheticDetector:
    """Fast health proxy for the public demo.

    The production pipeline (``cloud.ingest``) loads the trained Isolation
    Forest.  Streamlit Community Cloud cold starts are much faster without the
    5 MB joblib unpickle, and the demo only needs a plausible score that tracks
    the same degradation signature.
    """

    def __init__(self) -> None:
        self.threshold = 0.5536
        try:
            meta = json.loads(ANOMALY_META_PATH.read_text(encoding="utf-8"))
            self.threshold = float(meta.get("score_threshold", self.threshold))
        except (OSError, ValueError, TypeError):
            pass

    def score_row(self, row: dict) -> AnomalyResult:
        pf = float(row.get("pf") or 0.0)
        thd_v = float(row.get("thd_v") or 0.0)
        thd_i = float(row.get("thd_i") or 0.0)
        degree = max(
            0.0,
            (0.97 - pf) / 0.12,
            (thd_v - 2.1) / 8.0,
            (thd_i - 4.0) / 18.0,
        )
        score = min(0.95, 0.28 + 0.35 * degree)
        health = max(0.0, 98.0 - 28.0 * degree)
        return AnomalyResult(
            score=score,
            threshold=self.threshold,
            is_anomaly=score > self.threshold,
            health_index=health,
        )


class DemoFeed:
    """Owns the simulator state for one Streamlit server process."""

    def __init__(self, db_path: str | Path) -> None:
        self.store = Store(db_path)
        self.store.seed_nodes(NODES_PATH)
        specs = json.loads(NODES_PATH.read_text(encoding="utf-8"))
        classifier = PQDClassifier()
        self.nodes = [
            SimulatedNode(
                spec=spec,
                classifier=classifier,
                rng=np.random.default_rng(2026 + index),
                # A slow ramp keeps the maintenance panel interesting without
                # saturating during a long-running public demo.
                degradation_rate=0.0008 if spec["device_id"] == "node-004" else 0.0,
                solar_mode="cycle",
                solar_cycle_s=240.0,
                auto_reset_s=12.0,
            )
            for index, spec in enumerate(specs)
        ]
        self._by_id = {node.device_id: node for node in self.nodes}
        self.pipeline = TelemetryPipeline(self.store, SyntheticDetector())
        self._lock = threading.Lock()
        self._elapsed = 0.0
        self._last_tick = time.time()
        self._seeded = False

    # ------------------------------------------------------------------ setup
    def ensure_seed(self) -> None:
        """Create a fresh history window if the demo DB is missing/stale."""
        with self._lock:
            if self._seeded:
                return
            latest = self.store.latest_by_node()
            span = self.store.telemetry_span()
            now = time.time()
            full_window = span is not None and (span[1] - span[0]) >= HISTORY_SECONDS * 0.8
            if latest and full_window and now - float(span[1]) < 60:
                # A previous process may have left a complete, fresh demo DB
                # behind.  Restore the integration state before appending.
                for node in self.nodes:
                    row = latest.get(node.device_id)
                    if not row:
                        continue
                    node.meter.import_kwh = float(row.get("energy_import_kwh") or 0.0)
                    node.meter.export_kwh = float(row.get("energy_export_kwh") or 0.0)
                    node.seq = int(row.get("seq") or 0)
                    if row.get("health_index") is not None:
                        node.degradation = max(
                            0.0, min(1.0, (98.0 - float(row["health_index"])) / 28.0)
                        )
                newest = max(latest.values(), key=lambda item: float(item["ts_epoch"]))
                self._elapsed = float(newest.get("uptime_s") or 0.0)
                self._last_tick = now
                self._seeded = True
                return
            if latest:
                # Partial window (for example after a Streamlit restart) would
                # leave the chart nearly empty, so rebuild a full history.
                self._clear_data()
            self._backfill(now)
            self._seeded = True

    def _clear_data(self) -> None:
        with self.store.connect() as conn:
            for table in ("telemetry", "alerts", "commands", "waveform_latest"):
                conn.execute(f"DELETE FROM {table}")

    def _backfill(self, now: float) -> None:
        """Seed history without running the CNN/anomaly model 700+ times.

        The first live tick immediately produces a real classifier result and
        a waveform, so the expensive path stays on the live sample only.
        """
        start = now - HISTORY_SECONDS
        steps = int(HISTORY_SECONDS / SEED_TICK)
        records: list[dict] = []
        for index in range(steps + 1):
            elapsed = index * SEED_TICK
            stamp = start + elapsed
            for node in self.nodes:
                records.append(self._seed_row(node, elapsed, SEED_TICK, stamp))
        self.store.insert_telemetry_many(records)
        self._elapsed = HISTORY_SECONDS
        self._last_tick = now

    def _seed_row(self, node: SimulatedNode, elapsed: float, dt: float, stamp: float) -> dict:
        rng = node.rng
        node.seq += 1
        node.degradation = min(1.0, node.degradation + max(0.0, node.degradation_rate) * dt)
        degree = node.degradation

        load_kw = profiles.load_kw(elapsed, rng)
        solar_kw = profiles.solar_kw(elapsed, node.solar_kwp, rng, node.solar_mode, node.solar_cycle_s)
        i_solar = solar_kw * 1000.0 / 230.0
        pf = float(np.clip(0.97 - 0.12 * degree, 0.60, 1.0))
        v_rms = 230.0 + rng.normal(0.0, 1.1) - 1.4 * load_kw - 7.0 * degree
        i_load = load_kw * 1000.0 / max(v_rms * pf, 1.0)
        thd_v = 2.1 + 1.2 * rng.random() + 8.0 * degree
        thd_i = 4.0 + 2.5 * rng.random() + 18.0 * degree
        energy = node.meter.update(v_rms, i_load, i_solar, dt)

        score = float(np.clip(0.28 + 0.35 * degree + 0.04 * rng.random(), 0.0, 1.0))
        health = float(np.clip(98.0 - 28.0 * degree - 2.0 * rng.random(), 0.0, 100.0))
        probs = {"NORMAL": 0.98, "VOLTAGE_SAG": 0.005, "VOLTAGE_SWELL": 0.005,
                 "HARMONIC_DISTORTION": 0.005, "SHORT_CIRCUIT_OVERLOAD": 0.005}
        row = Telemetry(
            device_id=node.device_id,
            ts_epoch=stamp,
            v_rms=round(v_rms, 2),
            i_load=round(i_load, 3),
            i_solar=round(i_solar, 3),
            p_active=round(v_rms * i_load * pf, 1),
            p_net_kw=round(energy["p_net_kw"], 4),
            pf=round(pf, 4),
            freq=round(50.0 + float(rng.normal(0.0, 0.02)), 4),
            thd_v=round(thd_v, 2),
            thd_i=round(thd_i, 2),
            crest_i=round(1.414 + 0.04 * rng.random(), 3),
            energy_import_kwh=round(energy["energy_import_kwh"], 5),
            energy_export_kwh=round(energy["energy_export_kwh"], 5),
            ai_class="NORMAL",
            ai_conf=0.98,
            ai_latency_ms=0.0,
            relay="CLOSED",
            tripped=False,
            rssi=int(-52 - rng.integers(0, 18)),
            uptime_s=int(elapsed),
            seq=node.seq,
        ).to_row()
        row["anomaly_score"] = score
        row["health_index"] = health
        row["degraded"] = score > 0.55
        row["payload_json"] = json.dumps({"ai_probs": probs})
        return row

    # ------------------------------------------------------------------- live
    def tick(self, dt: float | None = None) -> None:
        """Advance every virtual node by one dashboard refresh."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_tick if dt is None else float(dt)
            elapsed = max(0.5, min(elapsed, MAX_TICK_SECONDS))
            previous = self._elapsed
            self._elapsed += elapsed
            self._last_tick = now
            self._fire_scenarios(previous, self._elapsed, now)
            for node in self.nodes:
                payload = node.step(self._elapsed, elapsed, now)
                self.pipeline.process(payload, received_at=now)

    def _fire_scenarios(self, previous: float, current: float, now: float) -> None:
        first = int(previous // SCENARIO_PERIOD)
        last = int(current // SCENARIO_PERIOD)
        for cycle in range(first, last + 1):
            base = cycle * SCENARIO_PERIOD
            for trigger, device_id, fault, duration in SCENARIO:
                at = base + trigger
                if previous < at <= current:
                    self._by_id[device_id].inject(fault, duration, now)

    # --------------------------------------------------------------- controls
    def inject(self, device_id: str, fault: str, duration_s: float = 8.0) -> bool:
        with self._lock:
            node = self._by_id.get(device_id)
            if node is None:
                return False
            return node.inject(fault, duration_s, time.time())

    def reset(self, device_id: str) -> bool:
        with self._lock:
            node = self._by_id.get(device_id)
            if node is None:
                return False
            node.reset()
            return True
