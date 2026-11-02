"""GridShield cloud SCADA dashboard (Streamlit).

Run from the project root:

    streamlit run dashboard/app.py

The dashboard is read-mostly: it polls the SQLite store written by the MQTT
ingestor or the local simulator, so it never blocks the telemetry path.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cloud.commands import publish_command  # noqa: E402
from cloud.config import (  # noqa: E402
    DB_PATH,
    MQTT_HOST,
    MQTT_PORT,
    NODE_OFFLINE_SECONDS,
    SITE_LAT,
    SITE_LON,
    SITE_ZOOM,
)
from cloud.store import Store  # noqa: E402
from dashboard import components as C  # noqa: E402
from dashboard.theme import inject_theme  # noqa: E402
from ml.config import ANOMALY_META_PATH, ANOMALY_MODEL_PATH  # noqa: E402

DEMO_MODE = os.getenv("GRIDSHIELD_DEMO", "").strip().lower() in {"1", "true", "yes", "on"}

st.set_page_config(
    page_title="GridShield SCADA",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()


@st.cache_resource
def get_store() -> Store:
    return Store(DB_PATH)


@st.cache_resource
def get_demo_feed():
    """Only used by dashboard/demo_app.py; production keeps the dashboard read-only."""
    if not DEMO_MODE:
        return None
    from dashboard.demo import DemoFeed

    return DemoFeed(DB_PATH)


@st.cache_data(ttl=30)
def anomaly_meta() -> dict:
    if ANOMALY_META_PATH.exists():
        return json.loads(ANOMALY_META_PATH.read_text(encoding="utf-8"))
    return {}


store = get_store()
demo = get_demo_feed()
if demo is not None:
    with st.spinner("Preparing live demo telemetry..."):
        demo.ensure_seed()
nodes = store.nodes()

if not nodes:
    st.markdown(
        '<div class="gs-empty"><h3>No nodes registered</h3>'
        "<p>Seed the demo grid with <code>python -m sim.run --mode local --duration 300</code>.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()

labels = {node["device_id"]: f"{node['device_id']} · {node.get('name', '')}" for node in nodes}

with st.sidebar:
    st.markdown(
        '<div class="gs-brand" style="padding:2px 0 14px 0">'
        '<div class="gs-logo">⚡</div><div><div class="gs-title">GridShield</div>'
        '<div class="gs-sub">Operator console</div></div></div>',
        unsafe_allow_html=True,
    )
    selected_id = st.selectbox("Node", [n["device_id"] for n in nodes], format_func=lambda x: labels.get(x, x))
    window_min = st.selectbox("History window", [5, 15, 60, 180], index=1, format_func=lambda m: f"last {m} min")
    refresh_s = st.select_slider("Refresh", options=[2, 3, 5, 10], value=2, format_func=lambda s: f"{s}s")

    st.divider()
    st.markdown("**Operator controls**")
    if demo is not None:
        st.caption("Demo feed · synthetic telemetry")
    else:
        st.caption(f"MQTT {MQTT_HOST}:{MQTT_PORT}")
    cmd_cols = st.columns(2)
    commands = [
        ("Sag", "VOLTAGE_SAG"),
        ("Swell", "VOLTAGE_SWELL"),
        ("Harmonic", "HARMONIC_DISTORTION"),
        ("Overload", "SHORT_CIRCUIT_OVERLOAD"),
    ]
    for index, (label, fault) in enumerate(commands):
        with cmd_cols[index % 2]:
            if st.button(label, key=f"cmd_{fault}", width="stretch"):
                if demo is not None:
                    ok = demo.inject(selected_id, fault)
                    message = "Demo fault injected" if ok else "Unknown demo node"
                else:
                    ok, message = publish_command(selected_id, "inject", fault, duration_s=8.0)
                store.log_command(
                    selected_id,
                    "inject",
                    {"fault": fault},
                    ("accepted" if ok else "failed") if demo is not None else ("sent" if ok else "failed"),
                )
                st.session_state["cmd_msg"] = (ok, message)
                st.rerun()
    if st.button("Reset relay", key="cmd_reset", type="primary", width="stretch"):
        if demo is not None:
            ok = demo.reset(selected_id)
            message = "Demo relay reset requested" if ok else "Unknown demo node"
        else:
            ok, message = publish_command(selected_id, "reset")
        store.log_command(
            selected_id,
            "reset",
            {},
            ("accepted" if ok else "failed") if demo is not None else ("sent" if ok else "failed"),
        )
        st.session_state["cmd_msg"] = (ok, message)
        st.rerun()

    if "cmd_msg" in st.session_state:
        ok, message = st.session_state.pop("cmd_msg")
        (st.success if ok else st.warning)(message)
    if demo is not None:
        st.caption("Commands act on the in-process demo simulator; no physical relay is connected.")
    else:
        st.caption("Commands are published to the edge node and only take effect if the simulator/ingestor is in MQTT mode.")

    st.divider()
    history_for_csv = store.history(selected_id, minutes=window_min)
    if history_for_csv:
        csv = pd.DataFrame(history_for_csv).drop(columns=["payload_json"], errors="ignore").to_csv(index=False)
        st.download_button(
            "Download node CSV",
            csv,
            file_name=f"{selected_id}_{window_min}min.csv",
            mime="text/csv",
            width="stretch",
        )
    if st.button("Acknowledge all alerts", width="stretch"):
        for alert in store.alerts(limit=500, only_unacknowledged=True):
            store.acknowledge_alert(alert["id"])
        st.toast("All alerts acknowledged")

    st.divider()
    st.caption("Edge AI: 1D-CNN · int8 weights · 2 kHz V/I window")
    st.caption("Predictive maintenance: Isolation Forest (contamination 0.05)")
    st.caption("Not a certified protection device. See docs/safety.md.")


@st.fragment(run_every=f"{refresh_s}s")
def live(device_id: str, minutes: int) -> None:
    if demo is not None:
        demo.tick(refresh_s)
    now = time.time()
    latest = store.latest_by_node()
    selected = latest.get(device_id)
    status = C.node_status(selected, now, NODE_OFFLINE_SECONDS)
    history = store.history(device_id, minutes=minutes)
    age = C.age_seconds(selected, now)
    updated = datetime.now().strftime("%H:%M:%S")

    live_cls = "offline" if status == "offline" else ""
    live_text = "NODE OFFLINE" if status == "offline" else "LIVE"
    st.markdown(
        f"""
        <div class="gs-header">
          <div class="gs-brand">
            <div class="gs-logo">⚡</div>
            <div>
              <div class="gs-title">GridShield SCADA</div>
              <div class="gs-sub">Edge-AI microgrid control center</div>
            </div>
          </div>
          <div class="gs-meta">
            <span>{C.esc(labels.get(device_id, device_id))}</span>
            <span>{updated}</span>
            <span class="gs-live {live_cls}"><span class="dot"></span>{live_text}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not latest:
        st.markdown(
            '<div class="gs-empty"><h3>Waiting for telemetry</h3>'
            "<p>Start the simulator in another terminal:</p>"
            "<pre>python -m sim.run --mode local --duration 300</pre>"
            "<p>or connect a real node over MQTT. The dashboard refreshes automatically.</p></div>",
            unsafe_allow_html=True,
        )
        return

    v = selected.get("v_rms") if selected else None
    i = selected.get("i_load") if selected else None
    p = selected.get("p_net_kw") if selected else None
    pf = selected.get("pf") if selected else None
    freq = selected.get("freq") if selected else None
    ai_class = selected.get("ai_class", "NORMAL") if selected else "NORMAL"
    conf = selected.get("ai_conf") if selected else None
    health = selected.get("health_index") if selected else None
    tripped = bool(selected.get("tripped")) if selected else False
    degraded = bool(selected.get("degraded")) if selected else False

    v_tone = "ok" if v is not None and 207 <= v <= 253 else "warn"
    if v is not None and (v < 180 or v > 270):
        v_tone = "crit"
    i_tone = "crit" if i is not None and i > 12 else "ok"
    p_tone = "ok" if p is not None and p < 0 else "info"
    h_tone = "ok" if health is not None and health >= 80 else ("warn" if health is not None and health >= 60 else "crit")

    cards = [
        C.kpi("Voltage", C.fmt(v, 1), "V", "nominal 230 V", v_tone),
        C.kpi("Load current", C.fmt(i, 2), "A", "12 A trip threshold", i_tone),
        C.kpi("Net power", ("+" if p is not None and p > 0 else "") + C.fmt(p, 2), "kW",
              "importing from grid" if p is not None and p >= 0 else "exporting solar", p_tone),
        C.kpi("Power factor", C.fmt(pf, 3), "", "displacement", "ok" if pf is not None and pf > 0.9 else "warn"),
        C.kpi("Frequency", C.fmt(freq, 2), "Hz", "50 Hz nominal", "ok"),
        C.kpi("Edge AI", ai_class.replace("_", " "), "", f"{C.fmt((conf or 0) * 100, 0)}% confidence",
              C.class_tone(ai_class, tripped, degraded)),
        C.kpi("Relay", "OPEN" if tripped else "CLOSED", "",
              (selected.get("fault_code") or "interlock armed") if selected else "--",
              "crit" if tripped else "ok"),
        C.kpi("Health index", C.fmt(health, 0), "/ 100", "Isolation Forest", h_tone),
        C.kpi("Imported", C.fmt(selected.get("energy_import_kwh") if selected else None, 2), "kWh", "session total", "warn"),
        C.kpi("Exported", C.fmt(selected.get("energy_export_kwh") if selected else None, 2), "kWh", "solar to grid", "ok"),
    ]
    st.markdown(C.kpi_grid(cards), unsafe_allow_html=True)

    probs = C.ai_probabilities(selected)
    left, right = st.columns([2.25, 1.0])
    with left:
        st.markdown(C.section("Voltage & load current", f"{len(history)} points · {minutes} min"), unsafe_allow_html=True)
        st.plotly_chart(C.voltage_current_figure(history), width="stretch", config=C.PLOTLY_CONFIG)
    with right:
        st.markdown(C.section("Edge classifier", "softmax over 5 PQD classes"), unsafe_allow_html=True)
        st.plotly_chart(C.ai_probability_figure(probs, ai_class), width="stretch", config=C.PLOTLY_CONFIG)

    left, right = st.columns(2)
    meta = anomaly_meta()
    threshold = meta.get("score_threshold")
    with left:
        st.markdown(C.section("Bidirectional power flow", "positive = import · negative = export"), unsafe_allow_html=True)
        st.plotly_chart(C.power_flow_figure(history), width="stretch", config=C.PLOTLY_CONFIG)
    with right:
        st.markdown(C.section("Predictive maintenance", f"threshold {C.fmt(threshold, 3)}"), unsafe_allow_html=True)
        st.plotly_chart(C.anomaly_figure(history, threshold), width="stretch", config=C.PLOTLY_CONFIG)

    map_col, alert_col = st.columns([1.3, 1.0])
    with map_col:
        st.markdown(C.section("Geospatial grid health", "marker colour = latest node state"), unsafe_allow_html=True)
        map_html = C.map_html(nodes, latest, now, NODE_OFFLINE_SECONDS, (SITE_LAT, SITE_LON), SITE_ZOOM)
        if map_html:
            st.iframe(map_html, height=430)
        else:
            st.info("Install `folium` to enable the GIS map.")
    with alert_col:
        alerts = store.alerts(limit=12)
        st.markdown(C.section("Operator alerts", f"{len(alerts)} most recent"), unsafe_allow_html=True)
        if alerts:
            st.dataframe(C.alerts_frame(alerts), hide_index=True, width="stretch", height=405)
        else:
            st.markdown('<div class="gs-panel">No alerts recorded. All clear.</div>', unsafe_allow_html=True)

    wave = store.waveform(device_id)
    details_col, wave_col = st.columns([1.0, 1.35])
    with details_col:
        st.markdown(C.section("Node details"), unsafe_allow_html=True)
        if selected:
            rows = [
                ("Last packet", f"{C.fmt(age, 1)} s ago"),
                ("Sequence", C.fmt(selected.get("seq"), 0)),
                ("Uptime", f"{C.fmt(selected.get('uptime_s'), 0)} s"),
                ("RSSI", f"{C.fmt(selected.get('rssi'), 0)} dBm"),
                ("THD V / I", f"{C.fmt(selected.get('thd_v'), 1)}% / {C.fmt(selected.get('thd_i'), 1)}%"),
                ("Anomaly score", C.fmt(selected.get("anomaly_score"), 3)),
                ("Fault code", C.esc(selected.get("fault_code") or "none")),
            ]
            body = "".join(
                f'<div style="display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-bottom:1px solid rgba(148,163,184,0.08)">'
                f'<span style="color:#8b9bb4;font-size:0.75rem">{C.esc(k)}</span>'
                f'<span style="font-family:JetBrains Mono,monospace;font-size:0.78rem">{v}</span></div>'
                for k, v in rows
            )
            st.markdown(f'<div class="gs-panel">{body}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div style="margin-top:10px">{C.chip(status)}</div>',
                unsafe_allow_html=True,
            )
    with wave_col:
        st.markdown(C.section("Waveform preview", "last 80 ms · decimated for MQTT"), unsafe_allow_html=True)
        st.plotly_chart(C.waveform_figure(wave), width="stretch", config=C.PLOTLY_CONFIG)

    st.markdown(C.section("Fleet telemetry", "every registered node"), unsafe_allow_html=True)
    st.dataframe(
        C.telemetry_frame(nodes, latest, now, NODE_OFFLINE_SECONDS),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "GridShield research prototype · synthetic/demo data unless a physical node is connected · "
        "not a certified protection device."
    )


if not ANOMALY_MODEL_PATH.exists():
    st.warning("Anomaly model missing. Run `python -m ml.train_anomaly` to enable predictive maintenance.")

live(selected_id, window_min)
