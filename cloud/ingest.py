"""MQTT ingestor for real GridShield edge nodes.

The simulator publishes *and* ingests locally, but a hardware node needs a
long-running subscriber on the broker.  This process subscribes to

    <prefix>/households/+/telemetry

validates each packet with the same contract as the simulator
(:mod:`cloud.models`), runs the shared pipeline (anomaly scoring, safety
mirror, alerts) and writes to SQLite for the dashboard.

Run from the project root:

    python -m cloud.ingest                 # uses .env / defaults
    python -m cloud.ingest --host 192.168.1.10 --db data/site.db
    python -m cloud.ingest --duration 600   # stop after 10 minutes
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

from ml.config import ANOMALY_MODEL_PATH

from .anomaly import AnomalyDetector
from .config import (
    DB_PATH,
    MQTT_HOST,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_TLS,
    MQTT_TOPIC_PREFIX,
    MQTT_USERNAME,
    RETENTION_DAYS,
    telemetry_topic,
)
from .models import PayloadError, Telemetry
from .pipeline import TelemetryPipeline, check_offline_nodes
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NODES = ROOT / "config" / "nodes.json"


def device_from_topic(topic: str, prefix: str = MQTT_TOPIC_PREFIX) -> str | None:
    """Extract the device id from ``<prefix>/households/<id>/telemetry``.

    Returns ``None`` for any other topic so command echoes and broker system
    topics are ignored.  Prefixes with slashes are supported.
    """
    prefix_parts = [p for p in prefix.strip("/").split("/") if p]
    parts = topic.split("/")
    if len(parts) != len(prefix_parts) + 3:
        return None
    if parts[: len(prefix_parts)] != prefix_parts:
        return None
    if parts[-3] != "households" or parts[-1] != "telemetry":
        return None
    device_id = parts[-2].strip()
    return device_id or None


def run(args: argparse.Namespace) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:  # pragma: no cover - dependency issue
        raise SystemExit("paho-mqtt is required: pip install -r requirements.txt") from exc

    store = Store(args.db)
    if args.nodes.exists():
        store.seed_nodes(args.nodes)
    detector = None
    if not args.no_anomaly:
        detector = AnomalyDetector() if ANOMALY_MODEL_PATH.exists() else None
        if detector is None:
            print("WARNING: anomaly model missing — run `python -m ml.train_anomaly`")
    pipeline = TelemetryPipeline(store, detector)

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"gridshield-ingest-{uuid.uuid4().hex[:8]}",
    )
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS:
        client.tls_set()
    client.reconnect_delay_set(min_delay=2, max_delay=60)

    def on_connect(client, userdata, flags, reason_code, properties=None):
        if getattr(reason_code, "is_failure", False):
            print(f"MQTT connect failed: {reason_code}")
            return
        topic = telemetry_topic("+")
        client.subscribe(topic, qos=0)
        print(f"MQTT connected to {args.host}:{args.port}; subscribed to {topic}")

    def on_disconnect(client, userdata, flags, reason_code, properties=None):
        if getattr(reason_code, "is_failure", False):
            print(f"MQTT disconnected ({reason_code}); retrying ...")

    def on_message(client, userdata, message):
        device_id = device_from_topic(message.topic)
        if device_id is None:
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            telemetry = Telemetry.from_payload(payload, received_at=time.time())
            result = pipeline.process(telemetry)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"rejected {device_id}: invalid JSON ({exc})")
            return
        except PayloadError as exc:
            print(f"rejected {device_id}: {exc}")
            return
        except Exception as exc:  # pragma: no cover - defensive
            # A single malformed packet must never kill the ingestor.
            print(f"pipeline error for {device_id}: {exc!r}")
            return

        if result["alerts"]:
            print(f"{device_id}: {', '.join(result['alerts'])}")
        if args.verbose:
            print(result["telemetry"].summary())

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    print(f"connecting to {args.host}:{args.port} ...")
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    started = time.time()
    last_check = started
    last_prune = started
    try:
        while True:
            now = time.time()
            if args.duration and now - started >= args.duration:
                break
            if now - last_check >= args.offline_check:
                last_check = now
                offline = check_offline_nodes(store)
                if offline:
                    print(f"offline: {', '.join(offline)}")
            if now - last_prune >= 3600:
                last_prune = now
                store.prune(args.retention_days)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        client.loop_stop()
        client.disconnect()
        store.prune(args.retention_days)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--nodes", type=Path, default=DEFAULT_NODES, help="optional node seed file")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--duration", type=float, default=0.0, help="seconds; 0 = run forever")
    parser.add_argument("--offline-check", type=float, default=15.0, help="seconds between staleness scans")
    parser.add_argument("--retention-days", type=int, default=RETENTION_DAYS)
    parser.add_argument("--no-anomaly", action="store_true", help="skip Isolation Forest scoring")
    parser.add_argument("--verbose", action="store_true", help="print every accepted packet")
    parser.add_argument("--host", default=MQTT_HOST)
    parser.add_argument("--port", type=int, default=MQTT_PORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    run(parse_args(argv))


if __name__ == "__main__":
    main()
