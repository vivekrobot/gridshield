"""Dark industrial theme for the Streamlit SCADA dashboard."""
from __future__ import annotations

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
    --bg: #060a11;
    --panel: #0b1220;
    --panel-2: #0f1829;
    --line: rgba(148, 163, 184, 0.14);
    --text: #e6edf7;
    --muted: #8b9bb4;
    --cyan: #22d3ee;
    --green: #22c55e;
    --amber: #f59e0b;
    --red: #ef4444;
    --violet: #a78bfa;
}

html, body, [class*="css"] { font-family: 'Inter', system-ui, sans-serif; }
.stApp {
    background:
        radial-gradient(1100px 500px at 8% -10%, rgba(34, 211, 238, 0.10), transparent 60%),
        radial-gradient(900px 500px at 95% 0%, rgba(167, 139, 250, 0.08), transparent 55%),
        var(--bg);
    color: var(--text);
}
.block-container { padding-top: 1.1rem; padding-bottom: 2rem; max-width: 1560px; }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #080e19 0%, #060a11 100%);
    border-right: 1px solid var(--line);
}
section[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }

h1, h2, h3, h4 { letter-spacing: -0.01em; }
h2 { font-size: 1.05rem !important; font-weight: 600 !important; margin: 0.2rem 0 0.6rem 0 !important; }
p, label, span { color: var(--text); }

.gs-header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px; padding: 4px 2px 14px 2px; border-bottom: 1px solid var(--line); margin-bottom: 16px;
}
.gs-brand { display: flex; align-items: center; gap: 12px; }
.gs-logo {
    width: 40px; height: 40px; border-radius: 11px;
    background: linear-gradient(140deg, rgba(34,211,238,0.22), rgba(167,139,250,0.18));
    border: 1px solid rgba(34,211,238,0.35);
    display: grid; place-items: center; font-size: 19px;
    box-shadow: 0 0 24px rgba(34, 211, 238, 0.15) inset;
}
.gs-title { font-size: 1.18rem; font-weight: 700; letter-spacing: -0.02em; }
.gs-sub { font-size: 0.74rem; color: var(--muted); letter-spacing: 0.14em; text-transform: uppercase; margin-top: 2px; }
.gs-meta { display: flex; align-items: center; gap: 10px; font-size: 0.78rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; }
.gs-live {
    display: inline-flex; align-items: center; gap: 7px; padding: 5px 11px; border-radius: 999px;
    background: rgba(34, 197, 94, 0.10); border: 1px solid rgba(34, 197, 94, 0.35);
    color: #86efac; font-weight: 600; font-size: 0.72rem; letter-spacing: 0.08em;
}
.gs-live .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 10px var(--green); animation: pulse 1.8s infinite; }
.gs-live.offline { background: rgba(239,68,68,0.10); border-color: rgba(239,68,68,0.4); color: #fca5a5; }
.gs-live.offline .dot { background: var(--red); box-shadow: 0 0 10px var(--red); }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

.gs-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: 10px; margin-bottom: 14px; }
.gs-card {
    position: relative; background: linear-gradient(160deg, var(--panel-2), var(--panel));
    border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px 11px 14px;
    overflow: hidden; min-height: 84px;
}
.gs-card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--tone, var(--cyan)); opacity: 0.9; }
.gs-card .label { color: var(--muted); font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.12em; font-weight: 600; }
.gs-card .value { font-family: 'JetBrains Mono', monospace; font-size: 1.42rem; font-weight: 600; margin-top: 6px; line-height: 1.1; }
.gs-card .unit { font-size: 0.7rem; color: var(--muted); margin-left: 4px; font-family: 'Inter', sans-serif; font-weight: 500; }
.gs-card .sub { margin-top: 5px; font-size: 0.68rem; color: var(--muted); }
.gs-card.ok { --tone: var(--green); }
.gs-card.warn { --tone: var(--amber); }
.gs-card.crit { --tone: var(--red); }
.gs-card.info { --tone: var(--cyan); }
.gs-card.violet { --tone: var(--violet); }
.gs-card.muted { --tone: #475569; }

.gs-chip {
    display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px; border-radius: 999px;
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;
    border: 1px solid transparent; white-space: nowrap;
}
.gs-chip.ok { background: rgba(34,197,94,0.12); color: #86efac; border-color: rgba(34,197,94,0.3); }
.gs-chip.warn { background: rgba(245,158,11,0.12); color: #fcd34d; border-color: rgba(245,158,11,0.32); }
.gs-chip.crit { background: rgba(239,68,68,0.13); color: #fca5a5; border-color: rgba(239,68,68,0.35); }
.gs-chip.muted { background: rgba(100,116,139,0.14); color: #94a3b8; border-color: rgba(100,116,139,0.3); }

.gs-section { display: flex; align-items: baseline; justify-content: space-between; margin: 6px 0 8px 0; }
.gs-section .title { font-size: 0.94rem; font-weight: 650; }
.gs-section .hint { font-size: 0.72rem; color: var(--muted); }
.gs-panel {
    background: linear-gradient(180deg, rgba(15,24,41,0.65), rgba(11,18,32,0.65));
    border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px;
}

div[data-testid="stPlotlyChart"] { border: 1px solid var(--line); border-radius: 12px; padding: 6px 6px 0 6px; background: rgba(11,18,32,0.55); }
div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
div[data-testid="stMetric"] { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 8px 12px; }

.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] { background: rgba(15,24,41,0.6); border-radius: 8px; padding: 6px 14px; border: 1px solid var(--line); }
.stTabs [aria-selected="true"] { background: rgba(34,211,238,0.12); border-color: rgba(34,211,238,0.35); color: #a5f3fc; }

.stButton > button {
    background: rgba(15,24,41,0.85); color: var(--text); border: 1px solid var(--line);
    border-radius: 9px; font-size: 0.8rem; font-weight: 550; transition: all 0.15s ease;
}
.stButton > button:hover { border-color: rgba(34,211,238,0.5); color: #a5f3fc; background: rgba(34,211,238,0.08); }
.stButton > button[kind="primary"] { background: rgba(34,211,238,0.14); border-color: rgba(34,211,238,0.45); color: #a5f3fc; }

.stSelectbox [data-baseweb="select"] > div, .stNumberInput input, .stTextInput input {
    background: var(--panel) !important; border-color: var(--line) !important; color: var(--text) !important;
}
.stSlider [data-baseweb="slider"] { padding-top: 4px; }

code, pre, .mono { font-family: 'JetBrains Mono', monospace !important; }
pre { background: #070d18 !important; border: 1px solid var(--line) !important; border-radius: 10px !important; }

.gs-empty { border: 1px dashed rgba(148,163,184,0.25); border-radius: 14px; padding: 28px; text-align: center; color: var(--muted); }
.gs-legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 0.72rem; color: var(--muted); margin: 4px 0 10px 2px; }
.gs-legend i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 5px; }
.gs-alert { border-left: 3px solid var(--tone); background: rgba(15,24,41,0.6); border-radius: 8px; padding: 9px 11px; margin-bottom: 7px; }
.gs-alert .top { display: flex; justify-content: space-between; gap: 10px; font-size: 0.68rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.07em; }
.gs-alert .msg { font-size: 0.8rem; margin-top: 4px; line-height: 1.35; }
</style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
