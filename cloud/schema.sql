-- GridShield SCADA storage schema (SQLite, WAL mode)
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS nodes (
    device_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    lat             REAL,
    lon             REAL,
    rated_current_a REAL NOT NULL DEFAULT 12.0,
    solar_kwp       REAL DEFAULT 0.0,
    meta_json       TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS telemetry (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id         TEXT NOT NULL REFERENCES nodes(device_id),
    ts_utc            TEXT NOT NULL,
    ts_epoch          REAL NOT NULL,
    seq               INTEGER,
    v_rms             REAL,
    i_load            REAL,
    i_solar           REAL,
    p_active          REAL,
    p_net_kw          REAL,
    pf                REAL,
    freq              REAL,
    thd_v             REAL,
    thd_i             REAL,
    crest_i           REAL,
    energy_import_kwh REAL,
    energy_export_kwh REAL,
    ai_class          TEXT,
    ai_conf           REAL,
    ai_latency_ms     REAL,
    relay             TEXT,
    tripped           INTEGER NOT NULL DEFAULT 0,
    fault_code        TEXT,
    rssi              INTEGER,
    uptime_s          INTEGER,
    anomaly_score     REAL,
    health_index      REAL,
    degraded          INTEGER NOT NULL DEFAULT 0,
    payload_json      TEXT
);

CREATE INDEX IF NOT EXISTS idx_telemetry_node_ts ON telemetry(device_id, ts_epoch DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(ts_epoch DESC);

-- Only the newest window per node is kept (48-point preview for the dashboard).
CREATE TABLE IF NOT EXISTS waveform_latest (
    device_id   TEXT PRIMARY KEY REFERENCES nodes(device_id),
    ts_epoch    REAL NOT NULL,
    v_json      TEXT NOT NULL,
    i_json      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     TEXT,
    ts_utc        TEXT NOT NULL,
    ts_epoch      REAL NOT NULL,
    severity      TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
    code          TEXT NOT NULL,
    message       TEXT NOT NULL,
    acknowledged  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts_epoch DESC);

CREATE TABLE IF NOT EXISTS commands (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id    TEXT NOT NULL,
    ts_utc       TEXT NOT NULL,
    ts_epoch     REAL NOT NULL,
    action       TEXT NOT NULL,
    payload_json TEXT,
    status       TEXT NOT NULL DEFAULT 'sent'
);
