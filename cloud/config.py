"""Cloud-side configuration, loaded from environment / .env (no extra deps)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = _get_int("MQTT_PORT", 1883)
MQTT_TLS = _get_bool("MQTT_TLS", False)
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "gridshield-cloud")
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "smart_grid").rstrip("/")

DB_PATH = Path(os.getenv("GRIDSHIELD_DB", str(ROOT / "data" / "gridshield.db")))

NODE_OFFLINE_SECONDS = _get_int("NODE_OFFLINE_SECONDS", 15)
RETENTION_DAYS = _get_int("RETENTION_DAYS", 30)
ANOMALY_ROLLING_WINDOW = _get_int("ANOMALY_ROLLING_WINDOW", 20)
ALERT_COOLDOWN_SECONDS = _get_int("ALERT_COOLDOWN_SECONDS", 300)

SITE_LAT = _get_float("SITE_LAT", 28.6139)
SITE_LON = _get_float("SITE_LON", 77.2090)
SITE_ZOOM = _get_int("SITE_ZOOM", 11)

# Safety envelope — keep in sync with firmware/arduino/gridshield_node/config.h
I_TRIP_A = _get_float("I_TRIP_A", 12.0)
V_MIN_TRIP = _get_float("V_MIN_TRIP", 180.0)
V_MAX_TRIP = _get_float("V_MAX_TRIP", 270.0)
I_RESET_A = _get_float("I_RESET_A", 10.5)
V_RESET_MIN = _get_float("V_RESET_MIN", 190.0)
V_RESET_MAX = _get_float("V_RESET_MAX", 250.0)
TRIP_CONFIRM_SAMPLES = _get_int("TRIP_CONFIRM_SAMPLES", 3)
RESET_CONFIRM_SAMPLES = _get_int("RESET_CONFIRM_SAMPLES", 5)
AI_TRIP_CONFIDENCE = _get_float("AI_TRIP_CONFIDENCE", 0.85)


def telemetry_topic(device_id: str = "+") -> str:
    return f"{MQTT_TOPIC_PREFIX}/households/{device_id}/telemetry"


def command_topic(device_id: str) -> str:
    return f"{MQTT_TOPIC_PREFIX}/households/{device_id}/cmd"
