"""Run the GridShield edge-node simulator.

Local mode (no broker required, writes straight to SQLite):

    python -m sim.run --mode local --duration 180

MQTT mode (real topic contract, broker required):

    python -m sim.run --mode mqtt --host localhost --duration 0

The default scenario injects a sag, a harmonic distortion event, an overload
trip and a slow degradation on one node so every dashboard panel gets exercised.
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

import numpy as np

from cloud.anomaly import AnomalyDetector
from cloud.config import (
    DB_PATH,
    MQTT_HOST,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_TLS,
    MQTT_TOPIC_PREFIX,
    MQTT_USERNAME,
    command_topic,
    telemetry_topic,
)
from cloud.pipeline import TelemetryPipeline
from cloud.store import Store
from ml.config import ANOMALY_MODEL_PATH
from ml.infer import PQDClassifier
from sim.node import SimulatedNode

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NODES = ROOT / "config" / "nodes.json"

DEFAULT_SCENARIO = [
    (12.0, "node-001", "VOLTAGE_SAG", 8.0),
    (28.0, "node-002", "HARMONIC_DISTORTION", 8.0),
    (44.0, "node-003", "SHORT_CIRCUIT_OVERLOAD", 6.0),
    (64.0, "node-001", "VOLTAGE_SWELL", 6.0),
]


def build_nodes(specs: list[dict], args: argparse.Namespace) -> list[SimulatedNode]:
    classifier = PQDClassifier()
    nodes = []
    for i, spec in enumerate(specs):
        degradation_rate = 0.0
        if not args.no_degradation and spec["device_id"] == args.degradation_node:
            degradation_rate = args.degradation_rate
        nodes.append(
            SimulatedNode(
                spec=spec,
                classifier=classifier,
                rng=np.random.default_rng(1000 + i),
                degradation_rate=degradation_rate,
                solar_mode=args.solar_mode,
                solar_cycle_s=args.solar_cycle,
                auto_reset_s=args.auto_reset,
            )
        )
    return nodes


def print_status(nodes: list[SimulatedNode], results: dict[str, dict]) -> None:
    parts = []
    for node in nodes:
        result = results.get(node.device_id)
        t = result["telemetry"] if result else None
        if not t:
            continue
        health = f"{result['anomaly'].health_index:.0f}" if result.get("anomaly") else "--"
        flag = "TRIP" if t.tripped else "ok"
        parts.append(
            f"{t.device_id} V={t.v_rms:5.1f} I={t.i_load:5.2f} P={t.p_net_kw:+5.2f}kW "
            f"{t.ai_class[:9]:9s} {flag:4s} H={health:>3s}"
        )
    print(" | ".join(parts), flush=True)


def run_local(args: argparse.Namespace, specs: list[dict]) -> None:
    store = Store(args.db)
    store.seed_nodes(args.nodes)
    detector = AnomalyDetector() if ANOMALY_MODEL_PATH.exists() else None
    if detector is None:
        print("WARNING: anomaly model missing — run `python -m ml.train_anomaly`")
    pipeline = TelemetryPipeline(store, detector)
    nodes = build_nodes(specs, args)
    by_id = {n.device_id: n for n in nodes}

    scenario = [] if args.scenario == "none" else DEFAULT_SCENARIO
    executed: set[int] = set()
    started = time.time()
    next_tick = started
    results: dict[str, dict] = {}

    print(f"local simulation: {len(nodes)} nodes, tick={args.tick}s, duration={args.duration or '∞'}s")
    try:
        while True:
            now = time.time()
            elapsed = now - started
            if args.duration and elapsed >= args.duration:
                break
            for index, (trigger, device, fault, duration) in enumerate(scenario):
                if index not in executed and elapsed >= trigger and device in by_id:
                    by_id[device].inject(fault, duration, now)
                    print(f"[scenario] {device} <- {fault} for {duration:.0f}s")
                    executed.add(index)

            for node in nodes:
                payload = node.step(elapsed, args.tick, now)
                results[node.device_id] = pipeline.process(payload)

            if int(elapsed) % max(5, args.print_every) == 0:
                print_status(nodes, results)

            next_tick += args.tick
            time.sleep(max(0.0, next_tick - time.time()))
    except KeyboardInterrupt:
        print("\nstopped")
    store.prune(args.retention_days)
    print(f"database: {args.db}  counts={store.counts()}")


def run_mqtt(args: argparse.Namespace, specs: list[dict]) -> None:
    import paho.mqtt.client as mqtt

    store = Store(args.db)
    store.seed_nodes(args.nodes)
    detector = AnomalyDetector() if ANOMALY_MODEL_PATH.exists() else None
    pipeline = TelemetryPipeline(store, detector)
    nodes = build_nodes(specs, args)
    by_id = {n.device_id: n for n in nodes}
    scenario = [] if args.scenario == "none" else DEFAULT_SCENARIO
    executed: set[int] = set()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"gridshield-sim-{uuid.uuid4().hex[:8]}",
    )
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS:
        client.tls_set()

    def on_connect(client, userdata, flags, reason_code, properties=None):
        print(f"MQTT connected rc={reason_code}")
        client.subscribe(f"{MQTT_TOPIC_PREFIX}/households/+/cmd", qos=0)

    def on_message(client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"bad command payload on {message.topic}")
            return
        parts = message.topic.split("/")
        device_id = parts[-2] if len(parts) >= 2 else ""
        node = by_id.get(device_id)
        if node is None:
            return
        action = str(payload.get("action", "")).lower()
        if action == "inject":
            fault = str(payload.get("fault", "")).upper()
            duration = float(payload.get("duration_s", 8.0))
            ok = node.inject(fault, duration, time.time())
            print(f"[command] {device_id} inject {fault} ok={ok}")
            store.log_command(device_id, "inject", payload, "accepted" if ok else "rejected")
        elif action in {"reset", "clear_trip"}:
            node.reset()
            print(f"[command] {device_id} reset requested")
            store.log_command(device_id, "reset", payload, "accepted")
        else:
            store.log_command(device_id, "unknown", payload, "rejected")

    client.on_connect = on_connect
    client.on_message = on_message
    print(f"connecting to {args.host}:{args.port} ...")
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    started = time.time()
    next_tick = started
    try:
        while True:
            now = time.time()
            elapsed = now - started
            if args.duration and elapsed >= args.duration:
                break
            for index, (trigger, device, fault, duration) in enumerate(scenario):
                if index not in executed and elapsed >= trigger and device in by_id:
                    by_id[device].inject(fault, duration, now)
                    print(f"[scenario] {device} <- {fault}")
                    executed.add(index)

            for node in nodes:
                payload = node.step(elapsed, args.tick, now)
                result = pipeline.process(payload)
                topic = telemetry_topic(node.device_id)
                info = client.publish(topic, json.dumps(payload, separators=(",", ":")), qos=0)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    print(f"publish failed for {node.device_id}: {info.rc}")
                _ = result

            if int(elapsed) % max(5, args.print_every) == 0:
                latest = store.latest_by_node()
                print(f"t={elapsed:6.0f}s " + " ".join(
                    f"{n.device_id}:{latest.get(n.device_id, {}).get('ai_class', '--')}"
                    for n in nodes
                ), flush=True)

            next_tick += args.tick
            time.sleep(max(0.0, next_tick - time.time()))
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        client.loop_stop()
        client.disconnect()
        store.prune(args.retention_days)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["local", "mqtt"], default="local")
    parser.add_argument("--nodes", type=Path, default=DEFAULT_NODES)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--duration", type=float, default=180.0, help="0 = run forever")
    parser.add_argument("--tick", type=float, default=1.0)
    parser.add_argument("--print-every", type=int, default=10)
    parser.add_argument("--scenario", choices=["default", "none"], default="default")
    parser.add_argument("--degradation-node", default="node-004")
    parser.add_argument("--degradation-rate", type=float, default=0.0055)
    parser.add_argument("--no-degradation", action="store_true")
    parser.add_argument("--solar-mode", choices=["cycle", "diurnal"], default="cycle")
    parser.add_argument("--solar-cycle", type=float, default=600.0)
    parser.add_argument("--auto-reset", type=float, default=10.0, help="seconds; 0 disables")
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--host", default=MQTT_HOST)
    parser.add_argument("--port", type=int, default=MQTT_PORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    specs = json.loads(args.nodes.read_text(encoding="utf-8"))
    if args.mode == "local":
        run_local(args, specs)
    else:
        run_mqtt(args, specs)


if __name__ == "__main__":
    main()
