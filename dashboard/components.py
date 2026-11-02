"""Reusable rendering helpers for the SCADA dashboard."""
from __future__ import annotations

import html
import json
import math
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

OK = "#22c55e"
WARN = "#f59e0b"
CRIT = "#ef4444"
CYAN = "#22d3ee"
VIOLET = "#a78bfa"
MUTED = "#8b9bb4"
AMBER = "#eab308"
GRID = "rgba(148,163,184,0.10)"

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

STATUS_META = {
    "normal": ("Nominal", "ok", OK, "●"),
    "voltage": ("Voltage deviation", "warn", AMBER, "â–²"),
    "degraded": ("Degradation watch", "warn", WARN, "â—†"),
    "trip": ("Relay tripped", "crit", CRIT, "■"),
    "offline": ("Offline", "muted", "#64748b", "â—‹"),
}


def esc(value: Any) -> str:
    return html.escape(str(value))


def fmt(value: Any, digits: int = 1, fallback: str = "--") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return f"{number:,.{digits}f}"


def age_seconds(row: dict | None, now: float) -> float | None:
    if not row or row.get("ts_epoch") is None:
        return None
    return max(0.0, now - float(row["ts_epoch"]))


def node_status(row: dict | None, now: float, offline_s: int = 15) -> str:
    if not row:
        return "offline"
    age = age_seconds(row, now)
    if age is None or age > offline_s:
        return "offline"
    if row.get("tripped"):
        return "trip"
    if row.get("degraded"):
        return "degraded"
    v = row.get("v_rms")
    if v is not None and abs(float(v) - 230.0) > 0.07 * 230.0:
        return "voltage"
    return "normal"


def chip(status: str) -> str:
    label, tone, _, icon = STATUS_META.get(status, STATUS_META["offline"])
    return f'<span class="gs-chip {tone}">{icon} {esc(label)}</span>'


def kpi(label: str, value: str, unit: str = "", sub: str = "", tone: str = "info") -> str:
    unit_html = f'<span class="unit">{esc(unit)}</span>' if unit else ""
    sub_html = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    return (
        f'<div class="gs-card {tone}"><div class="label">{esc(label)}</div>'
        f'<div class="value">{value}{unit_html}</div>{sub_html}</div>'
    )


def kpi_grid(cards: list[str]) -> str:
    return '<div class="gs-kpis">' + "".join(cards) + "</div>"


def section(title: str, hint: str = "") -> str:
    hint_html = f'<div class="hint">{esc(hint)}</div>' if hint else ""
    return f'<div class="gs-section"><div class="title">{esc(title)}</div>{hint_html}</div>'


def ai_probabilities(row: dict | None) -> dict[str, float]:
    if not row or not row.get("payload_json"):
        return {}
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return {}
    probs = payload.get("ai_probs") or {}
    if not isinstance(probs, dict):
        return {}
    out = {}
    for key, value in probs.items():
        try:
            out[str(key).upper()] = float(value)
        except (TypeError, ValueError):
            continue
    return out


# --------------------------------------------------------------------- charts
def _layout(fig: go.Figure, height: int = 260, title: str = "") -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=10, r=10, t=34 if title else 12, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui", size=11, color="#cbd5e1"),
        title=dict(text=title, font=dict(size=12, color="#94a3b8"), x=0.01) if title else None,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0.0, font=dict(size=10)),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, showline=False)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, showline=False)
    return fig


def voltage_current_figure(history: list[dict]) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if history:
        x = [datetime.fromtimestamp(float(r["ts_epoch"])) for r in history]
        fig.add_trace(
            go.Scatter(x=x, y=[r["v_rms"] for r in history], name="Voltage (V)", mode="lines",
                       line=dict(color=CYAN, width=2), hovertemplate="%{y:.1f} V<extra></extra>"),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(x=x, y=[r["i_load"] for r in history], name="Load current (A)", mode="lines",
                       line=dict(color=VIOLET, width=2), hovertemplate="%{y:.2f} A<extra></extra>"),
            secondary_y=True,
        )
        fig.add_hline(y=230, line_dash="dot", line_color="rgba(34,211,238,0.35)", secondary_y=False)
        fig.add_hline(y=12, line_dash="dot", line_color="rgba(239,68,68,0.4)", secondary_y=True)
    fig.update_yaxes(title_text="Volts", secondary_y=False, range=[140, 290])
    fig.update_yaxes(title_text="Amps", secondary_y=True, range=[0, 32], showgrid=False)
    return _layout(fig, 270)


def power_flow_figure(history: list[dict]) -> go.Figure:
    fig = go.Figure()
    if history:
        x = [datetime.fromtimestamp(float(r["ts_epoch"])) for r in history]
        p = [float(r.get("p_net_kw") or 0.0) for r in history]
        imports = [v if v >= 0 else 0.0 for v in p]
        exports = [v if v < 0 else 0.0 for v in p]
        fig.add_trace(go.Scatter(x=x, y=imports, name="Import", mode="lines",
                                 line=dict(color=WARN, width=1.6), fill="tozeroy",
                                 fillcolor="rgba(245,158,11,0.14)"))
        fig.add_trace(go.Scatter(x=x, y=exports, name="Export", mode="lines",
                                 line=dict(color=OK, width=1.6), fill="tozeroy",
                                 fillcolor="rgba(34,197,94,0.14)"))
        fig.add_hline(y=0, line_color="rgba(148,163,184,0.35)", line_width=1)
    fig.update_yaxes(title_text="kW")
    return _layout(fig, 230)


def ai_probability_figure(probs: dict[str, float], predicted: str | None) -> go.Figure:
    order = ["NORMAL", "VOLTAGE_SAG", "VOLTAGE_SWELL", "HARMONIC_DISTORTION", "SHORT_CIRCUIT_OVERLOAD"]
    labels = order + [k for k in probs if k not in order]
    values = [probs.get(k, 0.0) for k in labels]
    colours = [CYAN if k == (predicted or "") else "rgba(100,116,139,0.55)" for k in labels]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=colours, line=dict(width=0)),
        text=[f"{v*100:.0f}%" if v else "" for v in values], textposition="outside",
        hovertemplate="%{y}: %{x:.3f}<extra></extra>",
    ))
    fig.update_xaxes(range=[0, 1.08], showticklabels=False, title_text="softmax confidence")
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=10))
    return _layout(fig, 230)


def anomaly_figure(history: list[dict], threshold: float | None) -> go.Figure:
    fig = go.Figure()
    if history:
        x = [datetime.fromtimestamp(float(r["ts_epoch"])) for r in history]
        scores = [r.get("anomaly_score") for r in history]
        if any(s is not None for s in scores):
            fig.add_trace(go.Scatter(x=x, y=scores, name="Anomaly score", mode="lines",
                                     line=dict(color=VIOLET, width=2), connectgaps=True))
        health = [r.get("health_index") for r in history]
        if any(h is not None for h in health):
            fig.add_trace(go.Scatter(x=x, y=health, name="Health index", mode="lines",
                                     line=dict(color=OK, width=1.4, dash="dot"), yaxis="y2"))
    if threshold is not None:
        fig.add_hline(y=threshold, line_dash="dash", line_color="rgba(239,68,68,0.55)",
                      annotation_text="95th pct", annotation_font_size=9,
                      annotation_font_color="#fca5a5")
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 105], showgrid=False,
                                  title="health"))
    fig.update_yaxes(title_text="score (higher = more anomalous)")
    return _layout(fig, 240)


def waveform_figure(wave: dict | None) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if wave and wave.get("v") and wave.get("i"):
        n = min(len(wave["v"]), len(wave["i"]))
        x = [i * (80.0 / max(n - 1, 1)) for i in range(n)]
        fig.add_trace(go.Scatter(x=x, y=wave["v"][:n], name="Voltage", line=dict(color=CYAN, width=1.8)),
                      secondary_y=False)
        fig.add_trace(go.Scatter(x=x, y=wave["i"][:n], name="Current", line=dict(color=VIOLET, width=1.8)),
                      secondary_y=True)
    fig.update_xaxes(title_text="ms (80 ms window)")
    fig.update_yaxes(title_text="V", secondary_y=False)
    fig.update_yaxes(title_text="A", secondary_y=True, showgrid=False)
    return _layout(fig, 225)


# ------------------------------------------------------------------------ map
def map_html(
    nodes: list[dict],
    latest: dict[str, dict],
    now: float,
    offline_s: int,
    center: tuple[float, float],
    zoom: int,
) -> str:
    try:
        import folium
    except ImportError:
        return ""

    located = [n for n in nodes if n.get("lat") is not None and n.get("lon") is not None]
    if located:
        lats = [float(n["lat"]) for n in located]
        lons = [float(n["lon"]) for n in located]
        location = (sum(lats) / len(lats), sum(lons) / len(lons))
    else:
        location = center

    fmap = folium.Map(
        location=location,
        zoom_start=zoom,
        tiles="OpenStreetMap",
        attr="&copy; OpenStreetMap &copy; CARTO",
        control_scale=True,
        prefer_canvas=True,
    )
    if located:
        fmap.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(40, 40))

    for node in located:
        row = latest.get(node["device_id"])
        status = node_status(row, now, offline_s)
        _, _, colour, _ = STATUS_META[status]
        age = age_seconds(row, now)
        v = fmt(row.get("v_rms") if row else None, 1)
        i = fmt(row.get("i_load") if row else None, 2)
        p = fmt(row.get("p_net_kw") if row else None, 2)
        health = fmt(row.get("health_index") if row else None, 0)
        ai = esc(row.get("ai_class", "--") if row else "--")
        popup = f"""
        <div style="font-family:Inter,sans-serif;color:#e6edf7;background:#0b1220;padding:8px 10px;border-radius:8px;min-width:190px">
          <div style="font-weight:700;font-size:13px">{esc(node.get('name', node['device_id']))}</div>
          <div style="color:#8b9bb4;font-size:11px;margin-bottom:6px">{esc(node['device_id'])} Â· {esc(node.get('meta', {}).get('feeder', '')) if isinstance(node.get('meta'), dict) else ''}</div>
          <div style="font-size:11px;line-height:1.6">
            V {v} V &nbsp; I {i} A<br/>
            Net {p} kW &nbsp; Health {health}/100<br/>
            AI <b>{ai}</b><br/>
            Updated {('%.0f s ago' % age) if age is not None else 'never'}
          </div>
        </div>"""
        folium.CircleMarker(
            location=(float(node["lat"]), float(node["lon"])),
            radius=9 if status != "offline" else 7,
            color=colour,
            weight=2,
            fill=True,
            fill_color=colour,
            fill_opacity=0.85 if status != "offline" else 0.35,
            tooltip=f"{node['device_id']} Â· {status}",
            popup=folium.Popup(popup, max_width=260),
        ).add_to(fmap)

    legend = """
    <div style="position:fixed;left:14px;bottom:18px;z-index:9999;background:rgba(11,18,32,0.92);
                border:1px solid rgba(148,163,184,0.2);border-radius:10px;padding:9px 12px;
                font-family:Inter,sans-serif;font-size:11px;color:#cbd5e1;line-height:1.8">
      <div><span style="color:#22c55e">●</span> Nominal &nbsp; <span style="color:#eab308">▲</span> Voltage deviation</div>
      <div><span style="color:#f59e0b">◆</span> Degradation &nbsp; <span style="color:#ef4444">■</span> Tripped &nbsp; <span style="color:#64748b">○</span> Offline</div>
    </div>"""
    fmap.get_root().html.add_child(folium.Element(legend))
    return fmap._repr_html_()


# ---------------------------------------------------------------------- table
def telemetry_frame(nodes: list[dict], latest: dict[str, dict], now: float, offline_s: int) -> pd.DataFrame:
    rows = []
    for node in nodes:
        row = latest.get(node["device_id"])
        status = node_status(row, now, offline_s)
        label, _, _, icon = STATUS_META[status]
        age = age_seconds(row, now)
        rows.append({
            "Node": node["device_id"],
            "Site": node.get("name", ""),
            "Status": f"{icon} {label}",
            "V (V)": round(float(row["v_rms"]), 1) if row and row.get("v_rms") is not None else None,
            "I (A)": round(float(row["i_load"]), 2) if row and row.get("i_load") is not None else None,
            "P net (kW)": round(float(row["p_net_kw"]), 2) if row and row.get("p_net_kw") is not None else None,
            "PF": round(float(row["pf"]), 3) if row and row.get("pf") is not None else None,
            "AI class": row.get("ai_class", "--") if row else "--",
            "Conf": round(float(row["ai_conf"]) * 100, 0) if row and row.get("ai_conf") is not None else None,
            "Health": round(float(row["health_index"]), 0) if row and row.get("health_index") is not None else None,
            "Relay": row.get("relay", "--") if row else "--",
            "Age (s)": round(age, 1) if age is not None else None,
        })
    return pd.DataFrame(rows)


def alerts_frame(alerts: list[dict]) -> pd.DataFrame:
    icons = {"critical": "🔴", "warning": "🟠", "info": "ℹ️"}
    rows = []
    for alert in alerts:
        rows.append({
            "": icons.get(alert["severity"], "â€¢"),
            "Time": datetime.fromtimestamp(float(alert["ts_epoch"])).strftime("%H:%M:%S"),
            "Severity": str(alert["severity"]).upper(),
            "Code": alert["code"],
            "Node": alert.get("device_id") or "system",
            "Message": alert["message"],
            "Ack": "âœ“" if alert.get("acknowledged") else "",
        })
    return pd.DataFrame(rows)


def class_tone(ai_class: str | None, tripped: bool, degraded: bool) -> str:
    if tripped:
        return "crit"
    if ai_class and ai_class != "NORMAL":
        return "crit" if ai_class == "SHORT_CIRCUIT_OVERLOAD" else "warn"
    if degraded:
        return "warn"
    return "ok"

