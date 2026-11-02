"""SQLite persistence layer (safe for one writer + many readers via WAL)."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import DB_PATH

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utc_now() -> tuple[float, str]:
    now = time.time()
    stamp = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return now, stamp


class Store:
    def __init__(self, path: str | Path = DB_PATH):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(schema)

    # ------------------------------------------------------------------ nodes
    def upsert_node(
        self,
        device_id: str,
        name: str,
        lat: float | None = None,
        lon: float | None = None,
        rated_current_a: float = 12.0,
        solar_kwp: float = 0.0,
        meta: dict | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO nodes (device_id, name, lat, lon, rated_current_a, solar_kwp, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    name=excluded.name, lat=excluded.lat, lon=excluded.lon,
                    rated_current_a=excluded.rated_current_a, solar_kwp=excluded.solar_kwp,
                    meta_json=excluded.meta_json
                """,
                (device_id, name, lat, lon, rated_current_a, solar_kwp, json.dumps(meta or {})),
            )

    def seed_nodes(self, path: str | Path) -> int:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for node in data:
            self.upsert_node(
                node["device_id"],
                node.get("name", node["device_id"]),
                node.get("lat"),
                node.get("lon"),
                float(node.get("rated_current_a", 12.0)),
                float(node.get("solar_kwp", 0.0)),
                node.get("meta"),
            )
        return len(data)

    def nodes(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM nodes ORDER BY device_id").fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------- telemetry
    def insert_telemetry(
        self,
        row: dict[str, Any],
        wave: dict[str, list[float]] | None = None,
        anomaly_score: float | None = None,
        health_index: float | None = None,
        degraded: bool = False,
        payload_json: str | None = None,
    ) -> int:
        values = dict(row)
        values["anomaly_score"] = anomaly_score
        values["health_index"] = health_index
        values["degraded"] = int(degraded)
        values["payload_json"] = payload_json
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with self.connect() as conn:
            cur = conn.execute(
                f"INSERT INTO telemetry ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            if wave and wave.get("v") and wave.get("i"):
                conn.execute(
                    """
                    INSERT INTO waveform_latest (device_id, ts_epoch, v_json, i_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        ts_epoch=excluded.ts_epoch, v_json=excluded.v_json, i_json=excluded.i_json
                    """,
                    (
                        row["device_id"],
                        row["ts_epoch"],
                        json.dumps(wave["v"]),
                        json.dumps(wave["i"]),
                    ),
                )
            return int(cur.lastrowid)

    def latest_by_node(self) -> dict[str, dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.* FROM telemetry t
                JOIN (SELECT device_id, MAX(id) AS max_id FROM telemetry GROUP BY device_id) m
                  ON t.id = m.max_id
                """
            ).fetchall()
        return {r["device_id"]: dict(r) for r in rows}

    def latest(self, device_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM telemetry WHERE device_id=? ORDER BY id DESC LIMIT 1", (device_id,)
            ).fetchone()
        return dict(row) if row else None

    def history(self, device_id: str, minutes: int = 15, limit: int = 3000) -> list[dict[str, Any]]:
        since = time.time() - minutes * 60
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM telemetry
                WHERE device_id=? AND ts_epoch>=?
                ORDER BY ts_epoch ASC LIMIT ?
                """,
                (device_id, since, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def history_since(self, device_id: str, since_epoch: float, limit: int = 5000) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM telemetry WHERE device_id=? AND ts_epoch>=? ORDER BY ts_epoch ASC LIMIT ?",
                (device_id, since_epoch, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def waveform(self, device_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM waveform_latest WHERE device_id=?", (device_id,)).fetchone()
        if not row:
            return None
        return {
            "ts_epoch": row["ts_epoch"],
            "v": json.loads(row["v_json"]),
            "i": json.loads(row["i_json"]),
        }

    # ----------------------------------------------------------------- alerts
    def add_alert(
        self,
        device_id: str | None,
        severity: str,
        code: str,
        message: str,
        cooldown_seconds: int = 0,
        ts_epoch: float | None = None,
    ) -> bool:
        now, stamp = utc_now()
        ts_epoch = now if ts_epoch is None else ts_epoch
        with self.connect() as conn:
            if cooldown_seconds > 0:
                last = conn.execute(
                    """
                    SELECT ts_epoch FROM alerts
                    WHERE device_id IS ? AND code=? ORDER BY ts_epoch DESC LIMIT 1
                    """,
                    (device_id, code),
                ).fetchone()
                if last and now - float(last["ts_epoch"]) < cooldown_seconds:
                    return False
            conn.execute(
                "INSERT INTO alerts (device_id, ts_utc, ts_epoch, severity, code, message) VALUES (?,?,?,?,?,?)",
                (device_id, stamp, ts_epoch, severity, code, message),
            )
        return True

    def alerts(self, limit: int = 50, only_unacknowledged: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM alerts"
        if only_unacknowledged:
            query += " WHERE acknowledged=0"
        query += " ORDER BY id DESC LIMIT ?"
        with self.connect() as conn:
            rows = conn.execute(query, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def acknowledge_alert(self, alert_id: int) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))

    # --------------------------------------------------------------- commands
    def log_command(self, device_id: str, action: str, payload: dict | None = None, status: str = "sent") -> None:
        now, stamp = utc_now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO commands (device_id, ts_utc, ts_epoch, action, payload_json, status) VALUES (?,?,?,?,?,?)",
                (device_id, stamp, now, action, json.dumps(payload or {}), status),
            )

    def commands(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM commands ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- maintenance
    def prune(self, retention_days: int = 30) -> int:
        cutoff = time.time() - retention_days * 86400
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM telemetry WHERE ts_epoch < ?", (cutoff,))
            conn.execute("DELETE FROM alerts WHERE ts_epoch < ?", (cutoff,))
            return int(cur.rowcount)

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            telemetry = conn.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
            alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        return {"telemetry": int(telemetry), "alerts": int(alerts), "nodes": int(nodes)}
