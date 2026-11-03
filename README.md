# GridShield

[![Live demo](https://img.shields.io/badge/demo-live-brightgreen)](https://gridshieldd.streamlit.app/)

Edge-AI power-quality monitoring and fail-safe load protection for low-voltage
distribution networks. An ESP32 node samples voltage and current, classifies
power-quality disturbances with a 1D-CNN, trips a latching relay locally, and
publishes telemetry over MQTT. A Streamlit + Folium SCADA dashboard visualises
the site, and an Isolation Forest flags slow component degradation before it
becomes a failure.

This repository is the complete, runnable implementation of the GridShield
system described in the accompanying paper, with the paper's design flaws
corrected and documented in [`docs/paper-corrections.md`](docs/paper-corrections.md).

## What actually runs

| Layer | Implementation | Verified |
|---|---|---|
| Edge firmware | ESP32 Arduino / PlatformIO, 2 kHz dual-channel acquisition, PZEM-004T v3 Modbus, latching relay interlock, PubSubClient MQTT | `arduino-cli compile` OK — 935,970 B flash (71 %), 75,196 B RAM (22 %) |
| PQD classifier | 1D-CNN, 1,709 parameters, input `(160, 2)` = 80 ms of V + I at 2 kHz | held-out accuracy **97.8 %**, macro F1 **97.8 %** (synthetic data) |
| Edge inference | Portable C++ int8-weight kernels, no TensorFlow runtime needed | parity test against fp32 NumPy model |
| Predictive maintenance | Isolation Forest, 8 features, contamination 0.05 | synthetic-degradation detection 99.9 %, 5 % healthy false positives |
| Cloud | Payload validation, SQLite (WAL), alerts, safety mirror, net metering | 60 unit tests |
| Dashboard | Streamlit + Folium map, live KPIs, waveform, alerts, maintenance panel | headless `AppTest` smoke test, 0 exceptions |
| Simulator | 4 virtual households, fault injection, solar cycling, degradation ramp | end-to-end local run |
| Ingestor | MQTT → validation → pipeline → SQLite | topic-routing tests |

## Architecture

```
                    ┌──────────────────────────── ESP32 edge node ───────────────────────────┐
  ZMPT101B ──ADC34──▶│ 2 kHz sampler ─▶ 160-sample window ─▶ 1D-CNN (int8 weights)          │
  SCT-013  ──ADC35──▶│        │                    │                                        │
                     │        └──▶ RMS/THD/crest  │  PZEM-004T v3 ×2 (load + solar)        │
                     │                             ▼                                        │
                     │   safety.cpp: debounced, latching trip ─▶ relay (energise-to-close)  │
                     │        │                                                             │
                     │        └── telemetry JSON ──MQTT──▶ smart_grid/households/<id>/telemetry
                     └──────────────────────────────────────────────────────────────────────┘
                                              │
                    smart_grid/households/<id>/cmd  ◀── operator reset / trip
                                              │
                              ┌───────────────▼────────────────┐
                              │ cloud/ingest.py                │
                              │ validate → anomaly → safety     │
                              │ mirror → alerts → SQLite (WAL)  │
                              └───────────────┬────────────────┘
                                              │
                              ┌───────────────▼────────────────┐
                              │ Streamlit + Folium dashboard    │
                              └────────────────────────────────┘
```

## Quick start (Windows / PowerShell)

The verified environment is Python 3.14.6 with the versions pinned in
`requirements.txt`. Any Python >= 3.10 should work, but use the pinned
Streamlit release: the dashboard uses the recent `st.iframe` API.

```powershell
cd GridShield

# 1. virtual environment + dependencies + local config templates
.\scripts\setup.ps1

# 2. retrain both models (optional; artefacts are committed)
.\scripts\train.ps1

# 3. start the dashboard with simulated telemetry
.\scripts\demo.ps1 -Duration 180

# in a second terminal, open http://localhost:8501
```

Or manually:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m sim.run --mode local --duration 180
python -m streamlit run dashboard/app.py
```

`scripts\setup.ps1 -Python "C:\path\to\python.exe"` lets you reuse an existing
interpreter (the development venv lives outside this folder, so `-Python` may
be simpler than creating `.venv`).

### MQTT mode

Start a broker (Mosquitto, EMQX, …), then:

```powershell
# real hardware
python -m cloud.ingest --host 192.168.1.10

# or the simulator publishing to the same topics
python -m sim.run --mode mqtt --host 192.168.1.10 --duration 0

# dashboard reads the same SQLite file in both cases
$env:GRIDSHIELD_DB = "data/gridshield.db"
python -m streamlit run dashboard/app.py
```

Telemetry topic: `smart_grid/households/<device_id>/telemetry`
Command topic: `smart_grid/households/<device_id>/cmd`
(`{"action": "reset" | "trip" | "inject", ...}`; `inject` is simulator-only).
Add each physical node to `config/nodes.json` (id, name, lat/lon, solar kWp)
before starting the ingestor so it appears on the map; unknown ids are still
accepted and registered under their id.

## Results

**PQD classifier** — 3,000 synthetic windows (600/class), 70/15/15 split,
seed 42, 32 epochs in 7.1 s on CPU:

| Class | Precision | Recall | F1 |
|---|---|---|---|
| NORMAL | 0.926 | 0.967 | 0.946 |
| VOLTAGE_SAG | 0.989 | 0.956 | 0.972 |
| VOLTAGE_SWELL | 0.978 | 0.967 | 0.972 |
| HARMONIC_DISTORTION | 1.000 | 1.000 | 1.000 |
| SHORT_CIRCUIT_OVERLOAD | 1.000 | 1.000 | 1.000 |
| **Accuracy / macro F1** | | | **0.9778 / 0.9779** |

Confusion matrix and training curve are in `reports/`; the machine-readable
report is `reports/cnn_metrics.json`. These numbers are on synthetic waveforms
and are **not** a field-accuracy claim.

**Isolation Forest** — trained on 5,000 healthy rows; score threshold 0.5536
(p95); synthetic degradation detection 99.9 %; healthy false-positive rate 5 %.

## Repository layout

```
cloud/          payload contract, SQLite store, pipeline, safety mirror,
                energy/net-metering, anomaly wrapper, MQTT commands + ingestor
config/         nodes.json: device ids, geo coordinates, solar kWp
dashboard/      Streamlit app, Folium map and HTML components, theme
firmware/
  arduino/gridshield_node/   ESP32 sketch, sensors, safety, AI kernels, weights
  platformio.ini
ml/             dataset synthesis, NumPy 1D-CNN, training, int8/TFLite export,
                feature extraction, inference wrapper
models/         trained weights, model card, Isolation Forest, metadata
reports/        metrics JSON and plots
scripts/        setup / train / demo / test PowerShell entry points
sim/            waveform builder, load & solar profiles, virtual node, runner
tests/          stdlib unittest suite (no pytest needed)
docs/           architecture, wiring, ML, data contract, safety, paper notes
```

## Firmware build

1. Copy `firmware/arduino/gridshield_node/secrets.example.h` to `secrets.h`
   and set Wi-Fi, broker IP and MQTT credentials.
2. Install the ESP32 Arduino core and `PubSubClient` (2.8+).
3. Build/flash:

```powershell
pio run -d firmware
pio run -d firmware -t upload
pio device monitor -b 115200
```

Without PlatformIO:

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 firmware\arduino\gridshield_node
arduino-cli upload  --fqbn esp32:esp32:esp32 -p COM5 firmware\arduino\gridshield_node
```

> **Safety:** this is a research prototype. A hobby relay module is not a
> certified protective device. Never use GridShield as a substitute for an
> MCB, RCD/GFCI or AFCI. See [`docs/safety.md`](docs/safety.md).

## Tests

```powershell
.\scripts\test.ps1
# or
python -m unittest discover -s tests -v
```

The suite covers payload validation, SQLite storage, the energy meter, the
safety rule base, pipeline alerts, dashboard rendering, ML metrics/parity, the
MQTT topic contract, and firmware/cloud threshold parity. The firmware-contract
tests fail if `config.h` and `cloud/config.py` drift apart.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — components, data flow, timing budgets
- [`docs/hardware-design.md`](docs/hardware-design.md) — blocks, power budget, PCB/layout, acceptance tests
- [`docs/wiring.md`](docs/wiring.md) — BOM, pin map, AC front-end, calibration, PZEM isolation
- [`docs/ml-pipeline.md`](docs/ml-pipeline.md) — dataset, CNN, training, quantisation, TFLite path
- [`docs/data-contract.md`](docs/data-contract.md) — MQTT payload, validation ranges, DB schema, commands
- [`docs/safety.md`](docs/safety.md) — interlock policy, reset semantics, fail-safe limits
- [`docs/paper-corrections.md`](docs/paper-corrections.md) — deliberate departures from the paper

## Circuit diagrams and PDF

The reference schematics are vector SVGs and are also printed inside the
project PDF:

- [`docs/circuit-sheet-1-power.svg`](docs/circuit-sheet-1-power.svg) — mains path, MCB/RCD, PZEM meters, relay, load
- [`docs/circuit-sheet-2-isolation.svg`](docs/circuit-sheet-2-isolation.svg) — PZEM isolation barrier, isolated 5 V supplies
- [`docs/circuit-sheet-3-mcu-io.svg`](docs/circuit-sheet-3-mcu-io.svg) — ESP32 pin map, ADC front-end, relay driver

Regenerate the drawings and rebuild the full documentation PDF (README plus
every file in `docs/`, the three schematic sheets and a file inventory):

```powershell
.\scripts\build-pdf.ps1
# output: build\GridShield-Project.pdf
```

The PDF is produced by converting Markdown to HTML and printing it with headless
Chrome/Edge, so no extra Python packages beyond `markdown` are required.

## Report deck

`build/GridShield-Report.pptx` is a 16-slide project report with the schematics,
the confusion matrix, a live dashboard capture and the net-metering chart:

| Slides | Content |
|---|---|
| 1–4 | Title, agenda, problem statement, objectives |
| 5–8 | Architecture, mains path, MCU front-end, PZEM isolation |
| 9–11 | Signal chain and 1D-CNN, held-out results, safety interlock |
| 12–14 | Net metering, SCADA dashboard, predictive maintenance |
| 15–16 | Limits and roadmap, summary |

Rebuild it with:

```powershell
.\scripts\build-ppt.ps1
.\scripts\build-ppt.ps1 -Capture    # refresh the live dashboard screenshot first
```

`-Capture` starts the simulator and Streamlit, waits for the page to render and
saves it with Playwright driving your installed Chrome or Edge (about two
minutes). Without `-Capture` the existing `build/img/dashboard.png` is reused.
On a fresh checkout the first build also synthesises `data/report.db` with a
200 s demo run for the net-metering chart. When PowerPoint is installed the
script also writes `build/GridShield-Report.pdf` as a preview. The reporting
dependencies are `python-pptx` and `matplotlib`; `playwright` is only needed
for a fresh capture.

## Deployment

GitHub Pages cannot run Streamlit. Use one of these paths:

- **Public demo:** Streamlit Community Cloud with the main file set to
  `dashboard/demo_app.py`. It seeds 5 minutes of synthetic history and keeps
  refreshing without a broker.
- **Live node:** build the Docker image and run it on Render, Railway or Fly.io
  with a persistent volume at `/data` and `GRIDSHIELD_MODE=live`.

```powershell
docker build -t gridshield .
docker run --rm -p 8501:8501 -v gridshield-data:/data gridshield
```

See [`docs/deployment.md`](docs/deployment.md) for GitHub push, Streamlit
Community Cloud, Render/Railway/Fly.io, MQTT environment variables and the
security checklist.

## Licence

Research and educational use. Third-party libraries retain their own licences.
