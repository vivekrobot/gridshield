"""Build the GridShield PowerPoint report.

Run:  python scripts/make_ppt.py
Out:  build/GridShield-Report.pptx
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx.dml.color import RGBColor as RGB
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN

from pptkit import (
    ACCENT, ACCENT_L, AMBER, GREEN, INK, INK2, LINE, MUTED, PANEL, RED,
    WHITE, blank, bullets, deck, header, kpi, picture, rect,
    reference, table, text,
)

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "build" / "img"
OUT = ROOT / "build" / "GridShield-Report.pptx"

METRICS = json.loads((ROOT / "reports" / "cnn_metrics.json").read_text())
ANOMALY = json.loads((ROOT / "models" / "anomaly_meta.json").read_text())


def slide_title(prs):
    s = blank(prs, INK)
    rect(s, 0, 7.2, 13.333, 0.06, fill=ACCENT)
    rect(s, 0.95, 1.62, 0.06, 1.55, fill=ACCENT_L)
    text(s, 1.15, 1.58, 9, 0.3, "PROJECT REPORT  ·  NOVEMBER 2026", 11, ACCENT_L, bold=True)
    text(s, 1.15, 1.92, 9, 1.2, "GridShield", 64, WHITE, bold=True)
    text(s, 0.95, 3.42, 8.4, 1.4,
         "Edge-AI power-quality monitoring, protection and\npredictive maintenance for LV distribution networks",
         20, ACCENT_L, spacing=1.12)
    text(s, 0.95, 5.05, 7.6, 1.5,
         "ESP32 edge node  ·  1D-CNN  ·  MQTT  ·  Streamlit SCADA  ·  Isolation Forest",
         11.5, MUTED)
    text(s, 0.95, 6.55, 7, 0.3, "github-free local build  ·  build/GridShield-Project.pdf", 9.5, INK2)
    # accent blocks
    rect(s, 10.3, 1.6, 2.1, 0.09, fill=ACCENT)
    rect(s, 10.3, 1.85, 1.4, 0.09, fill=ACCENT_L)
    rect(s, 10.3, 2.1, 0.75, 0.09, fill=MUTED)


def slide_agenda(prs, n):
    s = blank(prs)
    header(s, n, "Contents", "What this report covers")
    items = [
        ("01", "Problem and objectives", "Why LV power quality needs edge intelligence"),
        ("02", "System architecture", "Three planes: edge, transport, cloud"),
        ("03", "Edge node hardware", "Sensing, metering, isolation, actuation"),
        ("04", "Signal chain and 1D-CNN", "From 2 kHz samples to a class label"),
        ("05", "Classification results", "Held-out accuracy and per-class behaviour"),
        ("06", "Safety interlock", "Fail-safe policy, latching and reset"),
        ("07", "Energy and net metering", "Import/export split with a solar meter"),
        ("08", "SCADA dashboard", "Live map, KPIs and event log"),
        ("09", "Predictive maintenance", "Isolation Forest on eight features"),
        ("10", "Limits and roadmap", "What is honest about this prototype"),
    ]
    for i, (num, title, desc) in enumerate(items):
        col, row = i // 5, i % 5
        x = 0.75 + col * 6.15
        y = 2.05 + row * 0.94
        text(s, x, y, 0.6, 0.4, num, 16, ACCENT, bold=True)
        text(s, x + 0.62, y - 0.02, 4.9, 0.3, title, 14.5, INK, bold=True)
        text(s, x + 0.62, y + 0.3, 4.9, 0.28, desc, 10, MUTED)


def slide_problem(prs, n):
    s = blank(prs)
    header(s, n, "01 · Problem", "The grid tells you what happened, after it happened",
           "Residential feeders are measured once a month, protected by slow breakers and repaired after failure.")
    cards = [
        ("01", "Power-quality events are invisible",
         "Sags, swells and harmonics are reported by the customer, not measured at the node.", RED),
        ("02", "Protection cannot see waveforms",
         "A domestic board has an MCB, not a waveform analyser. Trip decisions are thermal.", AMBER),
        ("03", "Energy flow is opaque",
         "Solar net metering is a monthly bill, never a live import/export signal.", ACCENT),
        ("04", "Degradation is discovered late",
         "Assets fail when something trips — there is no early-warning signal.", GREEN),
    ]
    w = 2.79
    for i, (num, title, desc, color) in enumerate(cards):
        x = 0.7 + i * 3.05
        rect(s, x, 2.25, w, 2.85, fill=PANEL, line=LINE, radius=0.06)
        text(s, x + 0.24, 2.45, 1.0, 0.5, num, 22, color, bold=True)
        text(s, x + 0.24, 3.02, w - 0.45, 1.0, title, 13.5, INK, bold=True)
        text(s, x + 0.24, 4.02, w - 0.45, 0.9, desc, 10, MUTED)
    rect(s, 0.7, 5.45, 11.93, 1.05, fill=INK, radius=0.05)
    rect(s, 1.0, 5.63, 0.4, 0.3, fill=None, line=None)
    text(s, 1.0, 5.63, 0.36, 0.3, "→", 18, ACCENT_L, bold=True)
    text(s, 1.5, 5.62, 10.85, 0.7,
         "GridShield closes the loop at the node: measure the waveform, classify it on-device,\n"
         "trip locally in milliseconds, and stream only the decision and the features.",
         12.5, WHITE)


def slide_objectives(prs, n):
    s = blank(prs)
    header(s, n, "01 · Objectives", "Four design goals, one bill of materials",
           "Each goal answers a specific failure mode and is backed by a measured artefact in this report.")

    columns = [
        (0.95, 1.30, "GOAL"),
        (2.40, 3.90, "WHAT WE BUILD"),
        (6.55, 2.75, "WHY IT MATTERS"),
        (9.55, 3.00, "EVIDENCE"),
    ]
    for x, w, label in columns:
        text(s, x, 2.06, w, 0.24, label, 8.5, MUTED, bold=True)
    rect(s, 0.7, 2.34, 11.93, 0.012, fill=LINE)

    rows = [
        ("Classify", "Five PQD classes on-device",
         "Sag, swell, harmonic distortion, overload and normal from one 80 ms V/I window.",
         "RMS alone cannot tell a sag from a short circuit; waveform shape can.",
         "97.8 % held-out accuracy", "1,709 params · 0.089 ms host inference"),
        ("Protect", "Local trip, no network in the loop",
         "A latching relay driven by firmware thresholds, mirrored by the cloud but never dependent on it.",
         "Cloud latency or an outage must never delay a trip on a live feeder.",
         "12 A / 180–270 V trip limits", "latching relay · reset only after ACK"),
        ("Observe", "One live view of every node",
         "MQTT telemetry into SQLite, rendered as a Streamlit + Folium console with an event log.",
         "Operators need the event, the waveform and the energy flow on one timeline.",
         "2 s ingest · session energy", "map, alerts and CSV export"),
        ("Predict", "Degradation before failure",
         "Isolation Forest over eight power-quality features with a rolling health index.",
         "Breakdowns are gradual; a trend turns a surprise trip into planned maintenance.",
         "0.9995 synthetic detection", "8 features · 5 % healthy false positives"),
    ]

    for i, (verb, title, desc, why, ev_value, ev_note) in enumerate(rows):
        y = 2.46 + i * 1.0
        rect(s, 0.7, y, 0.055, 0.88, fill=ACCENT)
        text(s, 0.95, y - 0.02, 1.30, 0.32, verb, 16, ACCENT, bold=True)
        text(s, 2.40, y - 0.04, 3.90, 0.30, title, 12.5, INK, bold=True)
        text(s, 2.40, y + 0.29, 3.90, 0.55, desc, 9.0, MUTED)
        text(s, 6.55, y + 0.02, 2.75, 0.72, why, 9.0, INK2)
        text(s, 9.55, y + 0.02, 3.00, 0.30, ev_value, 9.4, INK2, bold=True)
        text(s, 9.55, y + 0.34, 3.00, 0.42, ev_note, 8.6, MUTED)
        if i < len(rows) - 1:
            rect(s, 0.7, y + 0.94, 11.93, 0.008, fill=LINE)

    text(s, 0.7, 6.55, 11.93, 0.40,
         "Every goal is exercised by the 60-test suite and the public demo. The paper's 1D-CNN and five-class "
         "taxonomy are kept, corrected where the hardware cannot deliver.",
         9.2, MUTED)


def slide_architecture(prs, n):
    s = blank(prs)
    header(s, n, "02 · Architecture", "Three planes, one contract",
           "The edge never waits for the cloud; the cloud never assumes a node is alive.")
    for x, label in ((0.7, "EDGE"), (4.95, "TRANSPORT"), (8.55, "CLOUD AND UI")):
        text(s, x, 2.02, 3.5, 0.25, label, 9.5, MUTED, bold=True)

    rect(s, 0.7, 2.32, 3.75, 3.75, fill=PANEL, line=LINE, radius=0.05)
    text(s, 0.95, 2.5, 3.2, 0.3, "ESP32 node", 14, INK, bold=True)
    text(s, 0.95, 2.8, 3.2, 0.25, "firmware/arduino/gridshield_node", 8.5, MUTED)
    edge_items = ["2 kHz ADC · 160-sample window", "1D-CNN int8 · 5 classes",
                  "Fail-safe interlock", "Relay · buzzer · LEDs"]
    for i, item in enumerate(edge_items):
        y = 3.2 + i * 0.52
        rect(s, 0.95, y + 0.09, 0.08, 0.08, fill=ACCENT, shape=MSO_SHAPE.OVAL)
        text(s, 1.15, y, 3.05, 0.4, item, 10, INK2)

    rect(s, 4.95, 2.32, 3.1, 3.75, fill=WHITE, line=LINE, radius=0.05)
    text(s, 5.2, 2.5, 2.6, 0.3, "MQTT broker", 14, INK, bold=True)
    text(s, 5.2, 2.82, 2.65, 0.9, "smart_grid/households/\n{device_id}/telemetry", 9, ACCENT)
    text(s, 5.2, 3.75, 2.65, 1.6,
         "commands QoS 1 (down)\ntelemetry QoS 0 (up)\none topic per node\nretain off", 9.5, MUTED)

    rect(s, 8.55, 2.32, 4.08, 3.75, fill=PANEL, line=LINE, radius=0.05)
    text(s, 8.8, 2.5, 3.6, 0.3, "Ingest → SQLite → pipeline", 14, INK, bold=True)
    cloud_items = ["safety mirror + alerts", "energy and net metering",
                   "Isolation Forest health score", "Streamlit + Folium SCADA"]
    for i, item in enumerate(cloud_items):
        y = 3.05 + i * 0.52
        rect(s, 8.8, y + 0.09, 0.08, 0.08, fill=GREEN, shape=MSO_SHAPE.OVAL)
        text(s, 9.0, y, 3.4, 0.4, item, 10, INK2)

    for x in (4.52, 8.12):
        rect(s, x, 3.95, 0.36, 0.42, fill=ACCENT, shape=MSO_SHAPE.RIGHT_ARROW)

    rect(s, 0.7, 6.35, 11.93, 0.52, fill=WHITE, line=LINE, radius=0.12)
    text(s, 0.95, 6.48, 11.5, 0.3,
         "Budget: 80 ms window · 0.09 ms host inference · 1 s publish interval · 2 s dashboard refresh",
         10, MUTED)


def slide_hw_power(prs, n):
    s = blank(prs)
    header(s, n, "03 · Hardware", "Power path: two meters, one relay",
           "Metering is split so that import and export are never inferred from a single reading.")
    items = [
        ("Waveform pair. ", "ZMPT101B and SCT-013-030 feed the ADC; PZEM-004T supplies RMS and energy over Modbus."),
        ("Two meters. ", "PZEM #1 is in series with the load, PZEM #2 sits on the inverter branch for net metering."),
        ("Fail-open. ", "K1 is energise-to-close: loss of MCU power opens the load."),
        ("Not protection. ", "The MCB and 30 mA RCD are mandatory upstream; K1 is an extra load switch."),
    ]
    bullets(s, 0.7, 2.2, 4.75, 3.6, items, 12.5, gap=14)
    rect(s, 0.7, 5.75, 4.75, 0.95, fill=PANEL, line=LINE, radius=0.06)
    text(s, 0.95, 5.9, 4.3, 0.7,
         "Isolation warning: the PZEM TTL header may be mains-referenced on some clones — see Sheet 2.",
         9.5, AMBER, bold=True)
    picture(s, IMG / "sheet1.png", 5.6, 2.05, 7.0, 4.6)
    text(s, 5.6, 6.72, 7.0, 0.25, "Sheet 1 — mains path, metering and load switching", 8.5, MUTED,
         align=PP_ALIGN.CENTER)


def slide_hw_mcu(prs, n):
    s = blank(prs)
    header(s, n, "03 · Hardware", "Sensing front-end and fail-safe actuation",
           "Two conditioned ADC channels, one relay driver, and a reset button that can only ask.")
    items = [
        ("Front-end. ", "1 kΩ series, 220 nF anti-alias, 10k/10k bias to 1.65 V, BAT54S clamps on both channels."),
        ("ADC rules. ", "ADC1 only (GPIO34/35); ADC2 is unusable while Wi-Fi is on. Input-only pins, external bias."),
        ("Relay drive. ", "GPIO25 → 1 kΩ → 2N2222 → K1 coil with a 1N4007 flyback; active-LOW module."),
        ("Reset. ", "GPIO14 button with internal pull-up and 40 ms debounce — it requests re-arm, nothing more."),
    ]
    bullets(s, 0.7, 2.2, 4.9, 3.8, items, 12.5, gap=14)
    picture(s, IMG / "sheet3.png", 5.75, 2.05, 6.85, 4.6)
    text(s, 5.75, 6.72, 6.85, 0.25, "Sheet 3 — MCU, analogue front-end and indicators", 8.5, MUTED,
         align=PP_ALIGN.CENTER)


def slide_pipeline(prs, n):
    s = blank(prs)
    header(s, n, "04 · Signal chain", "From 2 kHz samples to a class label",
           "Every block fits on the ESP32: no host, no GPU, no round trip.")
    stages = [
        ("ACQUIRE", "2 kHz, 12-bit,\n2 channels"),
        ("WINDOW", "160 samples,\n80 ms"),
        ("CONDITION", "remove DC,\nper-unit"),
        ("1D-CNN", "int8 weights,\n1,709 params"),
        ("DECIDE", "class +\nconfidence"),
    ]
    x = 0.72
    for i, (name, desc) in enumerate(stages):
        fill = INK if i == 3 else PANEL
        rect(s, x, 2.25, 2.18, 1.25, fill=fill, line=None if i == 3 else LINE, radius=0.08)
        text(s, x + 0.18, 2.42, 1.9, 0.3, name, 11, ACCENT_L if i == 3 else ACCENT, bold=True)
        text(s, x + 0.18, 2.72, 1.9, 0.7, desc, 9.5, WHITE if i == 3 else MUTED)
        if i < 4:
            rect(s, x + 2.22, 2.72, 0.24, 0.3, fill=LINE, shape=MSO_SHAPE.RIGHT_ARROW)
        x += 2.47

    kpi(s, 0.7, 3.85, 2.85, 1.25, "1,709", "trainable parameters", INK, "≈ 1.7 kB int8")
    kpi(s, 3.7, 3.85, 2.85, 1.25, "0.089 ms", "host inference (median)", INK, "numpy parity path")
    kpi(s, 6.7, 3.85, 2.85, 1.25, "5", "PQD classes", INK, "single-label softmax")
    kpi(s, 9.7, 3.85, 2.93, 1.25, "97.8 %", "held-out accuracy", GREEN, "synthetic dataset")

    items = [
        ("Architecture. ", "Two convolution blocks (8 and 16 filters, 5/3 kernels), global mean+max pooling, dense 32→5 — small enough to run in the loop."),
        ("Why weights-only int8. ", "TensorFlow has no wheel for the project's Python 3.14, so the export carries int8 weights and a portable C++ kernel in firmware/."),
        ("Normalisation. ", "The mean is removed per window for RMS/THD, but the CNN input keeps amplitude — that is the signal for sag and swell."),
    ]
    bullets(s, 0.7, 5.35, 11.93, 1.5, items, 11.5, gap=8, line_spacing=1.05)


def slide_isolation(prs, n):
    s = blank(prs)
    header(s, n, "03 · Hardware", "The PZEM header is not SELV — treat it as live",
           "The TTL side may be mains-referenced depending on the clone. The barrier is not optional on a real installation.")
    picture(s, IMG / "sheet2.png", 0.55, 2.02, 7.35, 4.55)
    text(s, 0.55, 6.66, 7.35, 0.25, "Sheet 2 — isolated supplies, UART barrier and connector pinout", 8.5,
         MUTED, align=PP_ALIGN.CENTER)

    text(s, 8.15, 2.08, 4.5, 0.3, "Two ways to be safe", 14, INK, bold=True)
    cards = [
        ("Isolate", "B0505S-1W DC-DC + ADuM1201 per meter", GREEN,
         "Keeps the USB port and laptop at earth potential while the meter floats."),
        ("Replace", "certified RS485 meter + isolated transceiver", ACCENT,
         "Eastron SDM120 and similar are specified for this, with a datasheet to prove it."),
    ]
    for i, (title, sub, color, desc) in enumerate(cards):
        y = 2.5 + i * 1.42
        rect(s, 8.15, y, 4.5, 1.28, fill=PANEL, line=LINE, radius=0.06)
        rect(s, 8.15, y, 0.055, 1.28, fill=color)
        text(s, 8.38, y + 0.13, 4.0, 0.28, title.upper(), 9.5, color, bold=True)
        text(s, 8.38, y + 0.4, 4.0, 0.3, sub, 11.5, INK, bold=True)
        text(s, 8.38, y + 0.72, 4.05, 0.5, desc, 9.5, MUTED)

    text(s, 8.15, 5.45, 4.5, 0.3, "Power budget — 5 V SELV rail", 12, INK, bold=True)
    rows = [
        ("ESP32 + Wi-Fi", "100 mA · 240 mA peak"),
        ("2 × PZEM", "40 mA + DC-DC loss"),
        ("K1 coil", "70 mA energised"),
        ("Supply", "5 V / 1 A, 470 µF bulk"),
    ]
    for i, (a, b) in enumerate(rows):
        y = 5.78 + i * 0.28
        text(s, 8.15, y, 2.2, 0.24, a, 9.5, INK2)
        text(s, 10.45, y, 2.2, 0.24, b, 9.5, MUTED, align=PP_ALIGN.RIGHT)
    rect(s, 8.15, 6.92, 4.5, 0.012, fill=LINE)


def slide_results(prs, n):
    s = blank(prs)
    header(s, n, "05 · Results", "97.8 % held-out accuracy, with honest caveats",
           "450 windows, five classes, 90 per class. The model confuses sag and swell with normal, not with each other's extremes.")
    picture(s, IMG / "fig_confusion.png", 0.55, 2.0, 5.6, 4.35)
    text(s, 0.55, 6.42, 5.6, 0.25, "Confusion matrix · rows = actual, columns = predicted", 8.5,
         MUTED, align=PP_ALIGN.CENTER)

    kpi(s, 6.45, 2.0, 2.75, 1.16, "0.9778", "accuracy", INK, "macro F1 0.9779")
    kpi(s, 9.35, 2.0, 3.28, 1.16, "0.868", "mean confidence", INK, "softmax on the winning class")

    rows = [("Class", "Precision", "Recall", "F1")]
    pretty = {
        "NORMAL": "NORMAL", "VOLTAGE_SAG": "VOLTAGE_SAG", "VOLTAGE_SWELL": "VOLTAGE_SWELL",
        "HARMONIC_DISTORTION": "HARMONIC", "SHORT_CIRCUIT_OVERLOAD": "OVERLOAD",
    }
    for name, m in METRICS["test"]["per_class"].items():
        rows.append((pretty[name], f"{m['precision']:.3f}", f"{m['recall']:.3f}", f"{m['f1']:.3f}"))
    table(s, 6.45, 3.42, 6.18, rows, [2.5, 1.2, 1.2, 1.0], font=10, row_h=0.33)

    items = [
        ("Errors are boundary errors. ", "7 of 10 mistakes are sag or swell called NORMAL — the amplitude is only just outside tolerance."),
        ("No cross-talk at the extremes. ", "Harmonic and overload classes are perfect; the model is not guessing from one feature."),
        ("Synthetic data only. ", "The dataset is generated, so this is a pipeline check, not a field-accuracy claim."),
    ]
    bullets(s, 6.45, 5.7, 6.2, 1.15, items, 10.5, gap=6, line_spacing=1.02)


def slide_safety(prs, n):
    s = blank(prs)
    header(s, n, "06 · Safety", "The trip lives on the node, not in the cloud",
           "A cloud outage, a Wi-Fi stall or a dashboard crash cannot keep a faulted load energised.")
    states = [
        (0.7, "BOOT", "relay open", MUTED),
        (3.35, "ARMED_OPEN", "3 healthy samples", ACCENT),
        (6.0, "CLOSED", "normal operation", GREEN),
        (8.65, "TRIPPED", "latched open", RED),
    ]
    for x, name, sub, color in states:
        rect(s, x, 2.15, 2.15, 0.95, fill=PANEL, line=color, lw=1.5, radius=0.08)
        text(s, x + 0.16, 2.3, 1.85, 0.28, name, 11.5, color, bold=True)
        text(s, x + 0.16, 2.62, 1.85, 0.28, sub, 9.5, MUTED)
    for x in (2.88, 5.53, 8.18):
        rect(s, x, 2.5, 0.35, 0.24, fill=LINE, shape=MSO_SHAPE.RIGHT_ARROW)
    rect(s, 8.3, 3.12, 2.85, 0.5, fill=WHITE, line=LINE, radius=0.1)
    text(s, 8.45, 3.24, 2.6, 0.26, "reset request → AWAITING_RESET", 9, ACCENT, bold=True)
    rect(s, 0.7, 3.75, 5.2, 2.55, fill=PANEL, line=LINE, radius=0.05)
    text(s, 0.92, 3.92, 4.8, 0.28, "POLICY", 9.5, MUTED, bold=True)
    items = [
        ("Energise-to-close. ", "Losing MCU power opens the load."),
        ("Boot open. ", "safety::begin() drives the pin before OUTPUT."),
        ("Latching. ", "No auto-reclose timer exists (GS_AUTO_RESET_MS 0)."),
        ("Debounced. ", "3 samples to trip, 5 to re-arm."),
        ("Blind = open. ", "No valid V/I for 10 s → SENSOR_FAULT."),
    ]
    bullets(s, 0.95, 4.22, 4.75, 2.0, items, 10.2, gap=5, line_spacing=1.02)

    rows = [
        ("Parameter", "Trip", "Reset"),
        ("Load current", "> 12.0 A", "≤ 10.5 A"),
        ("Voltage", "< 180 / > 270 V", "190–250 V"),
        ("Confirmation", "3 samples", "5 samples"),
        ("AI overload", "conf ≥ 0.85", "—"),
        ("Reset window", "—", "30 s"),
    ]
    table(s, 6.25, 3.75, 6.38, rows, [2.2, 2.3, 1.6], font=10, row_h=0.33)
    text(s, 6.25, 5.95, 6.4, 0.6,
         "Thresholds are duplicated in config.h and cloud/config.py; a test fails if the two ever drift.",
         9.5, MUTED)
    rect(s, 6.25, 6.45, 6.38, 0.5, fill=WHITE, line=LINE, radius=0.12)
    text(s, 6.45, 6.56, 6.0, 0.28,
         "The CNN may only add a trip — it can never suppress a rule.", 10, INK, bold=True)


def slide_energy(prs, n):
    s = blank(prs)
    header(s, n, "07 · Energy", "Net metering without guessing the sign",
           "A second meter on the inverter branch makes import and export independent measurements.")
    picture(s, IMG / "fig_energy.png", 0.65, 2.02, 12.0, 3.1)
    kpi(s, 0.7, 5.35, 2.85, 1.1, "2", "meters per node", INK, "load + solar branch")
    kpi(s, 3.7, 5.35, 2.85, 1.1, "1 s", "sampling period", INK, "aggregated in SQLite")
    kpi(s, 6.7, 5.35, 2.85, 1.1, "2×", "energy registers", GREEN, "import / export split")
    kpi(s, 9.7, 5.35, 2.93, 1.1, "kW + kvar", "derived from V and I", INK, "PF and THD alongside")
    text(s, 0.7, 6.62, 11.9, 0.28,
         "Net current is load minus solar; the dashboard keeps the sign, so an export evening cannot be mistaken for a light-load import.",
         10, MUTED)


def slide_dashboard(prs, n):
    s = blank(prs)
    header(s, n, "08 · SCADA", "One map, four nodes, live telemetry",
           "Streamlit + Folium over SQLite: works on a laptop with no broker and no internet.")
    rect(s, 0.68, 2.02, 8.55, 4.55, fill=INK, radius=0.03)
    picture(s, IMG / "dashboard.png", 0.78, 2.12, 8.35, 4.35)
    text(s, 0.68, 6.66, 8.55, 0.25, "dashboard/app.py — captured from the local demo run", 8.5,
         MUTED, align=PP_ALIGN.CENTER)

    items = [
        ("Map. ", "Colour-coded pins for normal, warning and tripped nodes, with solar kWp per site."),
        ("KPIs. ", "Live voltage, current, PF, THD and energy totals per device."),
        ("Events. ", "Trips, resets and AI classes in one log, newest first."),
        ("Control. ", "A reset button that publishes MQTT — it can request, never force."),
    ]
    bullets(s, 9.4, 2.1, 3.25, 3.2, items, 10.5, gap=9)
    rect(s, 9.4, 5.35, 3.25, 1.2, fill=PANEL, line=LINE, radius=0.06)
    text(s, 9.62, 5.5, 2.85, 0.3, "STACK", 9, MUTED, bold=True)
    text(s, 9.62, 5.78, 2.85, 0.65,
         "Streamlit 1.66 · Folium 0.20\nSQLite (WAL) · paho-mqtt 2.1", 9.5, INK2)


def slide_pdm(prs, n):
    s = blank(prs)
    header(s, n, "09 · Predictive maintenance", "Catch the slow faults the classifier ignores",
           "An Isolation Forest watches the shape of normal operation; the CNN watches the waveform.")
    kpi(s, 0.7, 2.05, 2.85, 1.14, "300", "trees", INK, "contamination 0.05")
    kpi(s, 3.7, 2.05, 2.85, 1.14, "0.5536", "threshold (p95)", INK)
    kpi(s, 6.7, 2.05, 2.85, 1.14, "99.95 %", "degradation caught", GREEN, "synthetic")
    kpi(s, 9.7, 2.05, 2.93, 1.14, "5 %", "healthy FP", AMBER, "by construction")

    text(s, 0.7, 3.6, 5.4, 0.3, "Eight features per telemetry point", 13, INK, bold=True)
    feats = [
        ("v_pu", "voltage per unit"), ("i_pu", "current per unit"),
        ("pf", "power factor"), ("thd_v", "voltage THD"),
        ("thd_i", "current THD"), ("p_kw", "active power"),
        ("crest_i", "current crest factor"), ("freq_dev", "frequency deviation"),
    ]
    for i, (name, desc) in enumerate(feats):
        col, row = i // 4, i % 4
        x = 0.7 + col * 2.75
        y = 3.98 + row * 0.52
        rect(s, x, y, 2.5, 0.44, fill=PANEL, line=LINE, radius=0.1)
        text(s, x + 0.14, y + 0.04, 1.0, 0.2, name, 9.5, ACCENT, bold=True)
        text(s, x + 0.14, y + 0.25, 2.25, 0.18, desc, 8, MUTED)

    text(s, 0.7, 6.05, 5.6, 0.3, "How it is used", 12, INK, bold=True)
    items = [
        "Score every telemetry point; the cloud smooths over a rolling window before alerting.",
        "Health index and degraded flag are written back into SQLite for the dashboard.",
    ]
    bullets(s, 0.7, 6.34, 5.6, 0.55, items, 9.5, gap=3, line_spacing=1.0)

    rect(s, 6.5, 3.6, 6.13, 3.3, fill=INK, radius=0.04)
    text(s, 6.75, 3.78, 5.6, 0.3, "WHY TWO MODELS", 9, ACCENT_L, bold=True)
    text(s, 6.75, 4.1, 5.6, 0.5, "They fail in different directions.", 15, WHITE, bold=True)
    text(s, 6.75, 4.65, 5.65, 1.5,
         "The CNN needs a labelled event inside an 80 ms window. The Isolation Forest needs\n"
         "nothing but healthy history, so it catches a slow drift — a rising THD, a falling\n"
         "power factor, a sensor going soft — that never looks like a sag or a swell.",
         10.5, RGB(203, 213, 225))
    text(s, 6.75, 6.42, 5.65, 0.28, "Caveat: degradation rows are synthetic; field tuning is still required.",
         9, ACCENT_L)


def slide_limits(prs, n):
    s = blank(prs)
    header(s, n, "10 · Limits and roadmap", "What this prototype does not claim",
           "The engineering is real; the evidence is synthetic. Both statements belong in the report.")
    cols = [
        ("WORKS TODAY", GREEN, [
            "5-class PQD at 97.8 % on synthetic windows",
            "Fail-safe, latching trip on the ESP32",
            "Two-meter net metering with signed flow",
            "MQTT + SQLite + Streamlit SCADA",
            "Anomaly scoring with a health index",
        ]),
        ("NOT PROVEN", AMBER, [
            "Field accuracy on real LV feeders",
            "Certified isolation for the PZEM path",
            "Welded-contact detection (impossible)",
            "Long-run thermal behaviour of K1",
            "Multi-node scale beyond four devices",
        ]),
        ("NEXT", ACCENT, [
            "Replace PZEM clones with RS485 meters",
            "Capture a labelled field dataset",
            "Move the int8 kernels to ESP-DL",
            "Add signed OTA and config versioning",
            "Certify the enclosure and clearances",
        ]),
    ]
    for i, (title, color, items) in enumerate(cols):
        x = 0.7 + i * 4.1
        rect(s, x, 2.05, 3.75, 4.15, fill=PANEL, line=LINE, radius=0.05)
        rect(s, x, 2.05, 3.75, 0.06, fill=color)
        text(s, x + 0.24, 2.28, 3.2, 0.3, title, 9.5, color, bold=True)
        for j, item in enumerate(items):
            text(s, x + 0.24, 2.72 + j * 0.62, 3.3, 0.55, "·  " + item, 10, INK2)
    text(s, 0.7, 6.45, 11.9, 0.4,
         "The honest summary: a complete, working prototype whose numbers must be re-measured on hardware before anyone quotes them.",
         10.5, MUTED)


def slide_references(prs, n):
    s = blank(prs)
    header(s, n, "References", "Standards, methods and software",
           "Primary sources behind the measurement, machine-learning and safety decisions in this report.")

    standards = [
        ("1", "IEEE Std 1159-2019. ",
         "IEEE Recommended Practice for Monitoring Electric Power Quality. IEEE, 2019. "
         "doi:10.1109/IEEESTD.2019.8796486"),
        ("2", "IEC 61000-4-30:2015. ",
         "Electromagnetic compatibility (EMC) – Part 4-30: Testing and measurement "
         "techniques – Power quality measurement methods. IEC, 2015."),
        ("3", "IEEE Std 519-2022. ",
         "IEEE Standard for Harmonic Control in Electric Power Systems. IEEE, 2022. "
         "doi:10.1109/IEEESTD.2022.9848440"),
        ("4", "IEC 60364-4-41:2017. ",
         "Low-voltage electrical installations – Part 4-41: Protection for safety – "
         "Protection against electric shock. IEC, 2017."),
        ("5", "IEC 60898-1:2015. ",
         "Electrical accessories – Circuit-breakers for overcurrent protection for "
         "household and similar installations – Part 1: Circuit-breakers for a.c. "
         "operation. IEC, 2015."),
    ]
    methods = [
        ("6", "Liu, Ting & Zhou (2008). ",
         "Isolation Forest. Proc. 8th IEEE International Conference on Data Mining "
         "(ICDM), pp. 413–422. doi:10.1109/ICDM.2008.17"),
        ("7", "Kiranyaz et al. (2021). ",
         "1D convolutional neural networks and applications: A survey. Mechanical "
         "Systems and Signal Processing, 151, 107398. doi:10.1016/j.ymssp.2020.107398"),
        ("8", "Kingma & Ba (2015). ",
         "Adam: A method for stochastic optimization. International Conference on "
         "Learning Representations (ICLR). arXiv:1412.6980"),
        ("9", "Loshchilov & Hutter (2019). ",
         "Decoupled weight decay regularization. International Conference on Learning "
         "Representations (ICLR). arXiv:1711.05101"),
        ("10", "OASIS (2014). ",
         "MQTT Version 3.1.1. OASIS Standard, 29 October 2014. "
         "https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/"),
    ]

    for x, heading, refs in (
        (0.7, "STANDARDS AND PRACTICE", standards),
        (6.85, "METHODS AND PROTOCOLS", methods),
    ):
        text(s, x, 2.14, 5.6, 0.26, heading, 9.5, MUTED, bold=True)
        rect(s, x, 2.43, 5.55, 0.012, fill=LINE)
        for i, (num, lead, rest) in enumerate(refs):
            reference(s, x, 2.6 + i * 0.78, 5.55, 0.72, num, lead, rest, size=9.0)

    rect(s, 0.7, 6.5, 11.93, 0.012, fill=LINE)
    text(s, 0.7, 6.62, 11.93, 0.36,
         "Hardware and software documentation: Espressif ESP32 datasheet; Peacefair PZEM-004T v3 manual; "
         "YHDC SCT-013 and ZMPT101B datasheets; NumPy, scikit-learn, Streamlit and Folium documentation.",
         8.2, MUTED)


def slide_close(prs, n):
    s = blank(prs, INK)
    rect(s, 0, 0, 13.333, 0.09, fill=ACCENT)
    text(s, 0.95, 1.15, 8, 0.3, "SUMMARY", 11, ACCENT_L, bold=True)
    text(s, 0.95, 1.55, 10.5, 1.0, "Measure. Decide. Disconnect.", 40, WHITE, bold=True)
    text(s, 0.95, 2.65, 8.6, 1.0,
         "A few-dollar MCU that classifies power quality, trips locally in under a second,\n"
         "and reports enough to run a feeder — with no cloud in the safety path.",
         15, RGB(203, 213, 225))

    stats = [("97.8 %", "held-out accuracy"), ("0.09 ms", "host inference"),
             ("936 kB", "firmware flash (71 %)"), ("60", "tests passing")]
    for i, (v, l) in enumerate(stats):
        x = 0.95 + i * 2.95
        text(s, x, 4.05, 2.6, 0.5, v, 24, ACCENT_L, bold=True)
        text(s, x, 4.62, 2.6, 0.3, l, 9.5, MUTED)

    text(s, 0.95, 5.45, 5.2, 0.3, "ARTIFACTS", 9.5, MUTED, bold=True)
    text(s, 0.95, 5.75, 5.3, 1.0,
         "build/GridShield-Project.pdf\nbuild/GridShield-Report.pptx\ndocs/circuit-sheet-{1,2,3}-*.svg",
         9.5, RGB(203, 213, 225))
    rect(s, 6.6, 5.4, 5.8, 1.25, fill=RGB(30, 41, 59), radius=0.05)
    text(s, 6.85, 5.56, 5.4, 1.0,
         "Reference prototype — not a certified protective device.\nMCB, RCD and a certified contactor remain mandatory.",
         10, RGB(252, 165, 165))


def main() -> int:
    prs = deck()
    builders = [
        slide_title, slide_agenda, slide_problem, slide_objectives,
        slide_architecture, slide_hw_power, slide_hw_mcu, slide_isolation,
        slide_pipeline, slide_results, slide_safety, slide_energy,
        slide_dashboard, slide_pdm, slide_limits, slide_references, slide_close,
    ]
    assets = {
        slide_hw_power: "sheet1.png",
        slide_hw_mcu: "sheet3.png",
        slide_isolation: "sheet2.png",
        slide_results: "fig_confusion.png",
        slide_energy: "fig_energy.png",
        slide_dashboard: "dashboard.png",
    }
    runnable = []
    for build in builders:
        asset = assets.get(build)
        if asset and not (IMG / asset).exists():
            print(f"  ! build/img/{asset} missing — skipping {build.__name__}")
            continue
        runnable.append(build)

    for i, build in enumerate(runnable):
        if build is slide_title:
            build(prs)
        else:
            build(prs, i + 1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} kB, "
          f"{len(prs.slides._sldIdLst)} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
