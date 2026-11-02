# Architecture

GridShield has three planes with a hard rule: **protection never depends on the
network or the cloud**. The ESP32 makes and latches its own trip decision; the
cloud and dashboard are observers and maintenance tools.

```
┌─────────────────────── edge plane (deterministic, offline-capable) ───────────────────────┐
│                                                                                           │
│  AC front-end          ADC task (core 1, 2 kHz)          loop() task                      │
│  ZMPT101B ──▶ GPIO34 ─▶ ring buffer of 160 samples ─┬──▶ ai::classify() every 1 s          │
│  SCT-013  ──▶ GPIO35 ─┘  80 ms window (4 cycles)     │     1D-CNN, int8 weights           │
│                                                      ├──▶ THD / crest / RMS metrics       │
│  PZEM-004T #1 (load)  ── UART2, Modbus RTU ──────────┤                                     │
│  PZEM-004T #2 (solar) ── UART1, Modbus RTU ──────────┴──▶ safety::evaluate() every 200 ms  │
│                                                              │                            │
│  relay GPIO25 ◀── latching trip (energise-to-close) ◀────────┘                            │
│  LEDs / buzzer ── serviceIndicators()                                                     │
│                                                                                           │
│  net::publish() every 2 s ──▶ MQTT telemetry                                              │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                       │
┌────────────────────────── cloud plane ────────────────────────────────────────────────────┐
│  cloud/ingest.py (or sim/run.py --mode mqtt)                                              │
│      subscribe <prefix>/households/+/telemetry                                            │
│      Telemetry.from_payload()  → range validation + normalisation                         │
│      TelemetryPipeline.process():                                                         │
│          Isolation Forest score + rolling median → degradation warning                    │
│          safety mirror → SAFETY_MISMATCH warning                                          │
│          alert de-duplication/cooldown                                                    │
│          SQLite insert (WAL: one writer, many dashboard readers)                          │
│      check_offline_nodes() → NODE_OFFLINE warning                                         │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                       │
┌────────────────────────── presentation plane ─────────────────────────────────────────────┐
│  Streamlit dashboard ── reads SQLite every 2-10 s (read-only)                             │
│      Folium site map, KPI strip, node table, waveform, class probabilities,               │
│      alerts + acknowledge, energy/net-metering, maintenance health                        │
│      operator commands ──▶ MQTT cmd topic (reset / trip)                                  │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

## Why two current paths?

The PZEM-004T v3 exposes only RMS aggregates over Modbus; it cannot provide a
waveform. The CNN needs waveform shape (phase jumps, harmonic content, crest).
Therefore V and I are **also** sampled by the ESP32 ADC through a biased AC
front-end, while the PZEM remains authoritative for protection thresholds and
energy metering. If the load meter is unreachable, the firmware falls back to
ADC-derived RMS so the interlock stays active; a total loss of trustworthy
measurement trips `SENSOR_FAULT` after 10 s.

## Timing budget

| Task | Period | Notes |
|---|---|---|
| ADC sampling | 500 µs (2 kHz) | dedicated task pinned to core 1; resynchronises after long stalls |
| PZEM Modbus reads | 1 s | two meters, 150 ms timeout each |
| CNN inference | 1 s | 160×2 input, 1,709 parameters; measured on-device latency is published in `ai_latency_ms` |
| Safety evaluation | 200 ms | uses PZEM values (or ADC fallback) |
| Telemetry publish | 2 s | ~1.5–3 KiB JSON including an 80-point waveform preview |
| Dashboard refresh | 2–10 s | configurable; fragment-based `run_every` |

The firmware is single-writer for telemetry state; the ADC task only publishes
a completed window through a critical-section mailbox. The classification uses
the most recent completed window and is skipped when the load current is below
`GS_AI_MIN_CURRENT_A` (a de-energised load is reported as NORMAL rather than
letting noise drive a fault).

## Failure modes and responses

| Failure | Response |
|---|---|
| Wi-Fi / broker down | local protection continues; publish returns false and retries every 5 s |
| PZEM load meter silent | ADC RMS fallback; after 10 s without any valid measurement → `SENSOR_FAULT` trip |
| Solar meter silent | `i_solar = 0`; net metering temporarily conservative (no phantom export) |
| Node reboot | relay driven OPEN before `pinMode(OUTPUT)`, so no boot-time chatter; trip state is not persisted (documented limitation) |
| MCU power loss | relay de-energises → load opens (energise-to-close wiring) |
| Out-of-envelope reset attempt | reset confirmation counter cleared; relay stays open |
| Cloud/edge disagreement | edge is authoritative; cloud raises `SAFETY_MISMATCH` and re-arms when the node reports CLOSED |

## Deployment topology

- **Broker:** any MQTT 3.1.1 broker. TLS and username/password are supported in
  `cloud/config.py` and the firmware (`secrets.h`).
- **Storage:** SQLite by default for a single-site prototype; `cloud/store.py`
  is deliberately thin so it can be swapped for TimescaleDB/Postgres.
- **Dashboard:** stateless Streamlit process; it never writes telemetry and
  can be restarted without affecting ingestion.
- **Scaling:** each node has an independent topic and its own safety evaluator
  in the pipeline. A production deployment would shard by site/feeder and move
  the ingestor behind a queue.
