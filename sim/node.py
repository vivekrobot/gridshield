"""A simulated GridShield edge node (no hardware required)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from cloud.energy import EnergyMeter
from cloud.safety import Limits, SafetyEvaluator
from ml.features import waveform_stats
from ml.infer import PQDClassifier
from sim import profiles
from sim.waveform import build_window, decimate

FAULT_CLASSES = {
    "VOLTAGE_SAG",
    "VOLTAGE_SWELL",
    "HARMONIC_DISTORTION",
    "SHORT_CIRCUIT_OVERLOAD",
}


@dataclass
class SimulatedNode:
    spec: dict
    classifier: PQDClassifier
    rng: np.random.Generator
    degradation_rate: float = 0.0
    solar_mode: str = "cycle"
    solar_cycle_s: float = 480.0
    auto_reset_s: float = 10.0
    limits: Limits = field(default_factory=lambda: Limits(trip_confirm=2, reset_confirm=3))

    def __post_init__(self) -> None:
        self.device_id = self.spec["device_id"]
        self.name = self.spec.get("name", self.device_id)
        self.rated_current = float(self.spec.get("rated_current_a", 12.0))
        self.solar_kwp = float(self.spec.get("solar_kwp", 0.0))
        self.lat = self.spec.get("lat")
        self.lon = self.spec.get("lon")
        self.meter = EnergyMeter()
        self.safety = SafetyEvaluator(self.limits)
        self.degradation = 0.0
        self.seq = 0
        self.trip_age = 0.0
        self.reset_pending = False
        self.reset_deadline = 0.0
        self.fault = None
        self.fault_until = 0.0

    # ------------------------------------------------------------------ fault
    def inject(self, fault: str, duration_s: float, now: float) -> bool:
        fault = fault.upper()
        if fault == "RESET":
            self.reset_pending = True
            self.reset_deadline = now + 30.0  # mirrors GS_RESET_REQUEST_TIMEOUT_MS
            return True
        if fault not in FAULT_CLASSES:
            return False
        self.fault = fault
        self.fault_until = now + max(1.0, duration_s)
        return True

    def reset(self) -> None:
        self.reset_pending = True
        self.reset_deadline = time.time() + 30.0

    def _active_fault(self, now: float) -> str | None:
        if self.fault and now >= self.fault_until:
            self.fault = None
        return self.fault

    # ------------------------------------------------------------------- step
    def step(self, t: float, dt: float, now: float) -> dict:
        self.seq += 1
        self.degradation = min(1.0, self.degradation + max(0.0, self.degradation_rate) * dt)
        deg = self.degradation
        fault = self._active_fault(now)

        load_kw = profiles.load_kw(t, self.rng)
        solar_kw = profiles.solar_kw(t, self.solar_kwp, self.rng, self.solar_mode, self.solar_cycle_s)
        i_solar = solar_kw * 1000.0 / 230.0

        pf = float(np.clip(0.97 - 0.12 * deg - (0.02 if fault == "HARMONIC_DISTORTION" else 0.0), 0.60, 1.0))
        v_target = 230.0 + self.rng.normal(0.0, 1.1) - 1.4 * load_kw - 7.0 * deg
        thd_v = 2.1 + 1.2 * self.rng.random() + 8.0 * deg
        thd_i = 4.0 + 2.5 * self.rng.random() + 18.0 * deg
        i_target = load_kw * 1000.0 / max(v_target * pf, 1.0)
        overload = False
        phase_jump = 0.0

        if fault == "VOLTAGE_SAG":
            v_target *= 0.82
            phase_jump = 12.0
        elif fault == "VOLTAGE_SWELL":
            v_target *= 1.12
        elif fault == "HARMONIC_DISTORTION":
            thd_v = 17.0 + 4.0 * self.rng.random()
            thd_i = 38.0 + 10.0 * self.rng.random()
        elif fault == "SHORT_CIRCUIT_OVERLOAD":
            overload = True
            v_target *= 0.90
            i_target = 19.0 + 4.0 * self.rng.random()
            thd_i = 12.0 + 5.0 * self.rng.random()

        # If the interlock is latched, the relay has opened the load branch.
        tripped_before = self.safety.tripped
        if tripped_before:
            i_target = 0.0
            overload = False
            thd_i = 0.0

        wave = build_window(
            v_rms=v_target,
            i_rms=i_target,
            pf=pf,
            thd_v_pct=thd_v,
            thd_i_pct=thd_i,
            rng=self.rng,
            overload=overload,
            phase_jump_deg=phase_jump,
            freq=50.0 + float(self.rng.normal(0.0, 0.02)),
        )
        if tripped_before:
            wave[:, 1] = 0.0

        stats = waveform_stats(wave[:, 0], wave[:, 1])
        pred = self.classifier.predict_window(wave)
        ai_class = pred["class"] if not tripped_before else "NORMAL"
        ai_conf = pred["confidence"] if not tripped_before else 1.0

        if self.reset_pending:
            # A reset request stays armed until it is confirmed or it times
            # out, exactly like the firmware.  Every step contributes one
            # in-envelope confirmation sample.
            if now > self.reset_deadline:
                self.reset_pending = False
            elif self.safety.reset(stats["v_rms"], stats["i_rms"]):
                self.reset_pending = False
        state = self.safety.evaluate(stats["v_rms"], stats["i_rms"], ai_class, ai_conf)
        if state.newly_tripped:
            self.trip_age = 0.0

        if self.safety.tripped:
            self.trip_age += dt
            if self.auto_reset_s > 0 and self.trip_age >= self.auto_reset_s:
                if self.safety.reset(stats["v_rms"], stats["i_rms"]):
                    self.trip_age = 0.0

        relay = "OPEN" if self.safety.tripped else "CLOSED"
        if self.safety.tripped:
            i_reported = 0.0
            pf_reported = 0.0
        else:
            i_reported = stats["i_rms"]
            pf_reported = stats["pf"]

        energy = self.meter.update(stats["v_rms"], i_reported, i_solar, dt)
        p_net_kw = energy["p_net_kw"]

        payload = {
            "schema": 1,
            "source": "simulator",
            "device_id": self.device_id,
            "ts": now,
            "seq": self.seq,
            "v_rms": round(stats["v_rms"], 2),
            "i_load": round(i_reported, 3),
            "i_solar": round(i_solar, 3),
            "p_active": round(stats["v_rms"] * i_reported * pf_reported, 1),
            "p_net_kw": round(p_net_kw, 4),
            "pf": round(pf_reported, 4),
            "freq": round(50.0 + float(self.rng.normal(0.0, 0.02)), 4),
            "thd_v": round(stats["thd_v"], 2),
            "thd_i": round(max(stats["thd_i"], 0.0), 2),
            "crest_i": round(stats["crest_i"], 3),
            "energy_import_kwh": round(energy["energy_import_kwh"], 5),
            "energy_export_kwh": round(energy["energy_export_kwh"], 5),
            "ai_class": ai_class,
            "ai_conf": round(ai_conf, 4),
            "ai_probs": {k: round(v, 4) for k, v in pred["probabilities"].items()},
            "ai_latency_ms": 0.0,
            "relay": relay,
            "tripped": self.safety.tripped,
            "fault_code": self.safety.fault_code,
            "rssi": int(-52 - self.rng.integers(0, 18)),
            "uptime_s": int(t),
            "wave": decimate(wave),
        }
        return payload
