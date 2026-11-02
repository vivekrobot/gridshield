"""Payload validation and normalisation for the MQTT telemetry contract."""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class PayloadError(ValueError):
    """Raised when a telemetry packet cannot be trusted."""


def _finite(name: str, value: Any, default: float | None = None) -> float:
    if value is None:
        if default is None:
            raise PayloadError(f"missing field {name!r}")
        return float(default)
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise PayloadError(f"field {name!r} is not numeric: {value!r}") from exc
    if not math.isfinite(out):
        raise PayloadError(f"field {name!r} is not finite")
    return out


def _clamp(name: str, value: float, low: float, high: float) -> float:
    if value < low or value > high:
        raise PayloadError(f"field {name!r}={value} outside plausible range [{low}, {high}]")
    return value


@dataclass
class Telemetry:
    device_id: str
    ts_epoch: float
    v_rms: float
    i_load: float
    i_solar: float = 0.0
    p_active: float = 0.0
    p_net_kw: float = 0.0
    pf: float = 0.0
    freq: float = 50.0
    thd_v: float = 0.0
    thd_i: float = 0.0
    crest_i: float = 1.414
    energy_import_kwh: float = 0.0
    energy_export_kwh: float = 0.0
    ai_class: str = "NORMAL"
    ai_conf: float = 0.0
    ai_latency_ms: float = 0.0
    relay: str = "CLOSED"
    tripped: bool = False
    fault_code: str | None = None
    rssi: int = 0
    uptime_s: int = 0
    seq: int = 0
    wave: dict[str, list[float]] = field(default_factory=dict)
    ai_probs: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ts_utc(self) -> str:
        return datetime.fromtimestamp(self.ts_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | bytes | str,
        received_at: float | None = None,
    ) -> "Telemetry":
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8", errors="strict")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise PayloadError(f"invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise PayloadError("payload must be a JSON object")
        if len(json.dumps(payload)) > 8192:
            raise PayloadError("payload too large (max 8 KiB)")

        device_id = str(payload.get("device_id", "")).strip()
        if not device_id or len(device_id) > 64 or not all(
            c.isalnum() or c in "-_." for c in device_id
        ):
            raise PayloadError("invalid device_id")

        now = time.time()
        ts = payload.get("ts", payload.get("ts_epoch", now))
        ts_epoch = _finite("ts", ts, now)
        if ts_epoch > 1e12:  # milliseconds from a JS/Node client
            ts_epoch /= 1000.0
        # Reject obviously stale / future packets but allow clock-less nodes.
        if ts_epoch < now - 86400 * 365 or ts_epoch > now + 300:
            ts_epoch = received_at or now

        v_rms = _clamp("v_rms", _finite("v_rms", payload.get("v_rms")), 0.0, 400.0)
        i_load = _clamp("i_load", _finite("i_load", payload.get("i_load")), 0.0, 80.0)
        i_solar = _clamp("i_solar", _finite("i_solar", payload.get("i_solar"), 0.0), 0.0, 80.0)
        pf = _clamp("pf", _finite("pf", payload.get("pf"), 0.98), 0.0, 1.0)
        freq = _clamp("freq", _finite("freq", payload.get("freq"), 50.0), 40.0, 70.0)
        thd_v = _clamp("thd_v", _finite("thd_v", payload.get("thd_v"), 0.0), 0.0, 300.0)
        thd_i = _clamp("thd_i", _finite("thd_i", payload.get("thd_i"), 0.0), 0.0, 300.0)
        crest_i = _clamp("crest_i", _finite("crest_i", payload.get("crest_i"), 1.414), 0.0, 10.0)

        p_active = _finite("p_active", payload.get("p_active"), v_rms * i_load * pf)
        p_net_kw = _finite("p_net_kw", payload.get("p_net_kw"), v_rms * (i_load - i_solar) / 1000.0)

        relay_raw = payload.get("relay", "OPEN" if payload.get("tripped") else "CLOSED")
        if isinstance(relay_raw, bool):
            relay = "CLOSED" if relay_raw else "OPEN"
        else:
            relay = str(relay_raw).upper()
        if relay not in {"CLOSED", "OPEN"}:
            raise PayloadError(f"invalid relay state {relay_raw!r}")
        tripped = bool(payload.get("tripped", relay == "OPEN"))

        ai_class = str(payload.get("ai_class", "NORMAL")).upper()
        ai_conf = _clamp("ai_conf", _finite("ai_conf", payload.get("ai_conf"), 0.0), 0.0, 1.0)
        ai_latency = _clamp("ai_latency_ms", _finite("ai_latency_ms", payload.get("ai_latency_ms"), 0.0), 0.0, 60000.0)

        wave = payload.get("wave") or {}
        clean_wave: dict[str, list[float]] = {}
        if isinstance(wave, dict):
            for key in ("v", "i"):
                values = wave.get(key)
                if isinstance(values, list) and 8 <= len(values) <= 160:
                    clean_wave[key] = [round(float(v), 2) for v in values]
        probs = payload.get("ai_probs") or {}
        clean_probs = {}
        if isinstance(probs, dict):
            for key, value in probs.items():
                try:
                    clean_probs[str(key).upper()] = round(float(value), 4)
                except (TypeError, ValueError):
                    continue

        return cls(
            device_id=device_id,
            ts_epoch=float(ts_epoch),
            v_rms=v_rms,
            i_load=i_load,
            i_solar=i_solar,
            p_active=p_active,
            p_net_kw=p_net_kw,
            pf=pf,
            freq=freq,
            thd_v=thd_v,
            thd_i=thd_i,
            crest_i=crest_i,
            energy_import_kwh=_finite("energy_import_kwh", payload.get("energy_import_kwh"), 0.0),
            energy_export_kwh=_finite("energy_export_kwh", payload.get("energy_export_kwh"), 0.0),
            ai_class=ai_class,
            ai_conf=ai_conf,
            ai_latency_ms=ai_latency,
            relay=relay,
            tripped=tripped,
            fault_code=(str(payload["fault_code"])[:48] if payload.get("fault_code") else None),
            rssi=int(payload.get("rssi", 0) or 0),
            uptime_s=int(payload.get("uptime_s", 0) or 0),
            seq=int(payload.get("seq", 0) or 0),
            wave=clean_wave,
            ai_probs=clean_probs,
            raw=payload,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "ts_utc": self.ts_utc,
            "ts_epoch": self.ts_epoch,
            "seq": self.seq,
            "v_rms": self.v_rms,
            "i_load": self.i_load,
            "i_solar": self.i_solar,
            "p_active": self.p_active,
            "p_net_kw": self.p_net_kw,
            "pf": self.pf,
            "freq": self.freq,
            "thd_v": self.thd_v,
            "thd_i": self.thd_i,
            "crest_i": self.crest_i,
            "energy_import_kwh": self.energy_import_kwh,
            "energy_export_kwh": self.energy_export_kwh,
            "ai_class": self.ai_class,
            "ai_conf": self.ai_conf,
            "ai_latency_ms": self.ai_latency_ms,
            "relay": self.relay,
            "tripped": int(self.tripped),
            "fault_code": self.fault_code,
            "rssi": self.rssi,
            "uptime_s": self.uptime_s,
        }

    def summary(self) -> str:
        return (
            f"{self.device_id} V={self.v_rms:.1f} I={self.i_load:.2f}A "
            f"P={self.p_net_kw:+.2f}kW class={self.ai_class}({self.ai_conf:.2f}) "
            f"relay={self.relay}"
        )
