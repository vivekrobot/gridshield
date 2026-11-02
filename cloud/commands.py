"""Publish operator commands (fault injection / relay reset) over MQTT."""
from __future__ import annotations

import json
import uuid

from .config import (
    MQTT_HOST,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_TLS,
    MQTT_USERNAME,
    command_topic,
)


def publish_command(
    device_id: str,
    action: str,
    fault: str | None = None,
    duration_s: float = 8.0,
    host: str = MQTT_HOST,
    port: int = MQTT_PORT,
    timeout: float = 4.0,
) -> tuple[bool, str]:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return False, "paho-mqtt is not installed"

    payload: dict = {"action": action, "ts": None}
    if fault:
        payload["fault"] = fault
        payload["duration_s"] = duration_s

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"gridshield-dash-{uuid.uuid4().hex[:8]}",
    )
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS:
        client.tls_set()

    try:
        client.connect(host, port, keepalive=10)
    except OSError as exc:
        return False, f"broker unreachable at {host}:{port} ({exc})"

    client.loop_start()
    try:
        info = client.publish(command_topic(device_id), json.dumps(payload), qos=1)
        info.wait_for_publish(timeout=timeout)
        if not info.is_published():
            return False, "publish timed out"
        return True, f"{action} command sent to {device_id}"
    except Exception as exc:  # pragma: no cover - network dependent
        return False, f"publish failed: {exc}"
    finally:
        client.loop_stop()
        client.disconnect()
