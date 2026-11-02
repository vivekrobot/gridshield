# Data contract

Everything on the wire is JSON (`application/json`), one object per MQTT
message. Units are SI with the suffixes shown in the field names. The same
contract is used by the ESP32 firmware, the simulator, the ingestor and the
dashboard.

## MQTT topics

`MQTT_TOPIC_PREFIX` defaults to `smart_grid`.

| Topic | Direction | QoS | Retained | Purpose |
|---|---|---|---|---|
| `<prefix>/households/<device_id>/telemetry` | node → cloud | 0 | no | periodic measurement packet (every 2 s) |
| `<prefix>/households/<device_id>/cmd` | dashboard/simulator → node | 0–1 | no | operator command |
| `<prefix>/households/<device_id>/status` | node → broker | 0 | yes | `online` / `offline` last-will |

Device ids must match `[A-Za-z0-9._-]{1,64}`; the ingestor derives the id from
the topic and the validator re-checks the JSON `device_id`.

## Telemetry packet

Example (abridged; whitespace added for readability):

```json
{
  "schema": 1,
  "source": "esp32",
  "device_id": "node-001",
  "ts": 1762000000,
  "seq": 4211,
  "v_rms": 229.84,
  "i_load": 4.312,
  "i_solar": 1.950,
  "p_active": 972.4,
  "p_net_kw": 0.5432,
  "pf": 0.981,
  "freq": 50.02,
  "thd_v": 2.41,
  "thd_i": 5.63,
  "crest_i": 1.432,
  "energy_import_kwh": 1234.56789,
  "energy_export_kwh": 87.65432,
  "ai_class": "NORMAL",
  "ai_conf": 0.9731,
  "ai_latency_ms": 41.27,
  "ai_probs": {
    "NORMAL": 0.9731,
    "VOLTAGE_SAG": 0.0091,
    "VOLTAGE_SWELL": 0.0074,
    "HARMONIC_DISTORTION": 0.0061,
    "SHORT_CIRCUIT_OVERLOAD": 0.0043
  },
  "relay": "CLOSED",
  "tripped": false,
  "fault_code": null,
  "rssi": -57,
  "uptime_s": 84213,
  "wave": {"v": [0.0, 162.4, 318.1], "i": [0.0, 3.1, 6.0]}
}
```

### Required fields

Only four fields are strictly required: `device_id`, `v_rms`, `i_load` and
either `ts` or `ts_epoch`. Everything else has a safe default. The
validator (`cloud/models.py`) rejects non-finite values, out-of-range values
and packets larger than 8 KiB.

### Field reference and validation ranges

| Field | Unit | Required | Range / default | Notes |
|---|---|---|---|---|
| `schema` | – | no | 1 | informational |
| `source` | – | no | `esp32` / `simulator` | informational |
| `device_id` | – | **yes** | 1–64 chars `[A-Za-z0-9._-]` | must match topic id |
| `ts` / `ts_epoch` | s | no | epoch seconds; ms auto-detected | stale (>1 y) or >5 min future → receive time |
| `seq` | – | no | integer ≥ 0 | per-node monotonic counter |
| `v_rms` | V RMS | **yes** | 0–400 | |
| `i_load` | A RMS | **yes** | 0–80 | load branch current |
| `i_solar` | A RMS | no | 0–80, default 0 | solar inverter output |
| `p_active` | W | no | default `V·I·PF` | load active power |
| `p_net_kw` | kW | no | default `V·(I_load−I_solar)/1000` | positive = import |
| `pf` | – | no | 0–1, default 0.98 | displacement PF |
| `freq` | Hz | no | 40–70, default 50 | |
| `thd_v` | % | no | 0–300, default 0 | harmonics 3/5/7 |
| `thd_i` | % | no | 0–300, default 0 | |
| `crest_i` | – | no | 0–10, default 1.414 | peak / RMS current |
| `energy_import_kwh` | kWh | no | ≥ 0, default 0 | cumulative |
| `energy_export_kwh` | kWh | no | ≥ 0, default 0 | cumulative |
| `ai_class` | – | no | one of the 5 class names | uppercased by validator |
| `ai_conf` | – | no | 0–1 | |
| `ai_latency_ms` | ms | no | 0–60 000 | measured on-device inference time |
| `ai_probs` | – | no | keys → 0–1 | rounded to 4 dp |
| `relay` | – | no | `CLOSED` / `OPEN` | booleans normalised (true→CLOSED) |
| `tripped` | – | no | bool, default `relay == OPEN` | |
| `fault_code` | – | no | ≤ 48 chars | one of the codes below |
| `rssi` | dBm | no | integer | |
| `uptime_s` | s | no | integer | |
| `wave` | – | no | object with `v`,`i` arrays, 8–160 points each | 80-point preview in firmware; stored as the latest window only |

### Class names

`NORMAL`, `VOLTAGE_SAG`, `VOLTAGE_SWELL`, `HARMONIC_DISTORTION`,
`SHORT_CIRCUIT_OVERLOAD` (indices 0–4).

### Fault codes

| Code | Source | Meaning |
|---|---|---|
| `OVERCURRENT` | rules | load current above 12 A for 3 consecutive samples |
| `UNDERVOLTAGE` | rules | V < 180 V RMS for 3 samples |
| `OVERVOLTAGE` | rules | V > 270 V RMS for 3 samples |
| `AI_OVERLOAD` | edge AI | `SHORT_CIRCUIT_OVERLOAD` with confidence ≥ 0.85 for 3 samples |
| `SENSOR_FAULT` | rules | no trustworthy measurement for 10 s |
| `REMOTE` | operator | remote trip via MQTT |
| `NODE_REPORTED_TRIP` | cloud | relay reported open without a specific code |

## Commands

Published by the dashboard (`cloud/commands.py`) or the simulator to
`<prefix>/households/<id>/cmd`:

```json
{"action": "reset"}
{"action": "trip"}
{"action": "inject", "fault": "VOLTAGE_SAG", "duration_s": 8}
```

| Action | Firmware | Simulator |
|---|---|---|
| `reset` | arms the reset confirmation counter; relay closes only after 5 consecutive in-envelope samples and before the 30 s request timeout | same |
| `trip` | immediate latching trip (`REMOTE`); always accepted | same |
| `inject` | rejected (a physical node cannot synthesise a waveform) | injects the named fault for `duration_s`; `RESET` is also accepted as an injectable action |
| `clear_trip` | not supported (use `reset`) | alias for `reset` |

Resetting is deliberately **not** a force-close. There is no command that can
close the relay while measurements are outside the envelope.

## SQLite schema

`cloud/schema.sql` creates five tables (WAL mode; one writer, many readers):

| Table | Purpose | Retention |
|---|---|---|
| `nodes` | registry: id, name, lat/lon, rating, solar kWp, JSON metadata | persistent |
| `telemetry` | one row per packet; includes derived anomaly columns | pruned by `RETENTION_DAYS` (30) |
| `waveform_latest` | newest V/I preview per node (48-point down-sample) | one row per node |
| `alerts` | `info`/`warning`/`critical` alerts with acknowledge flag | pruned with telemetry |
| `commands` | audit log of operator actions and simulator injections | pruned with telemetry |

Derived columns added by the pipeline:

- `anomaly_score` — Isolation Forest score in `[0, 1]`
- `health_index` — `100 × (1 − score)`
- `degraded` — rolling-window maintenance flag
- `payload_json` — original packet without the waveform

Alert codes: `TRIP`, `AI_OVERLOAD`, `SAFETY_MISMATCH`, `DEGRADATION_WARNING`,
`NODE_OFFLINE`.

## Compatibility and versioning

- Unknown JSON fields are ignored and preserved in `payload_json`.
- New optional fields can be added without a schema bump. A breaking change
  requires bumping `schema` and keeping a reader branch in `Telemetry.from_payload`.
- The firmware's JSON writer and `cloud/models.py` are covered by
  `tests/test_models.py` and `tests/test_firmware_contract.py`; change one side
  and run the suite.
