"""Generate the figures used in the PPT report.

Run:  python scripts/make_ppt_figures.py
Out:  build/img/fig_confusion.png, build/img/fig_energy.png
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "build" / "img"
INK = "#0f172a"
ACCENT = "#0284c7"
MUTED = "#64748b"

plt.rcParams.update({
    "font.family": "Segoe UI",
    "font.size": 10,
    "axes.edgecolor": "#cbd5e1",
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "text.color": INK,
})


def confusion() -> None:
    data = json.loads((ROOT / "reports" / "cnn_metrics.json").read_text())
    cm = np.array(data["test"]["confusion_matrix"])
    labels = ["NORMAL", "SAG", "SWELL", "HARMONIC", "OVERLOAD"]

    fig, ax = plt.subplots(figsize=(6.2, 5.4), dpi=200)
    im = ax.imshow(cm, cmap="Blues", vmin=0, vmax=cm.max())
    ax.set_xticks(range(5), labels, rotation=28, ha="right", fontsize=9)
    ax.set_yticks(range(5), labels, fontsize=9)
    ax.set_xlabel("predicted", fontsize=9)
    ax.set_ylabel("actual", fontsize=9)
    for i in range(5):
        for j in range(5):
            v = cm[i, j]
            ax.text(j, i, str(v), ha="center", va="center", fontsize=11,
                    color="white" if v > cm.max() * 0.55 else INK,
                    fontweight="bold" if i == j else "normal")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("Held-out test set — 450 windows", fontsize=10, color=MUTED, pad=10)
    fig.colorbar(im, ax=ax, fraction=0.045, pad=0.03).ax.tick_params(labelsize=8)
    fig.tight_layout()
    fig.savefig(IMG / "fig_confusion.png", facecolor="white")
    plt.close(fig)


def energy() -> None:
    db = ROOT / "data" / "report.db"
    if not db.exists():
        print("  generating data/report.db (one-off 200 s demo run) ...")
        subprocess.run(
            [sys.executable, "-m", "sim.run", "--mode", "local",
             "--duration", "200", "--db", str(db), "--solar-cycle", "120"],
            cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
        )
    if not db.exists():
        print("skip energy figure: no report database")
        return
    con = sqlite3.connect(db)
    rows = con.execute(
        "select ts_epoch, p_net_kw, energy_import_kwh, energy_export_kwh "
        "from telemetry where device_id='node-001' order by ts_epoch"
    ).fetchall()
    con.close()
    if not rows:
        print("skip energy figure: no rows")
        return

    t = np.array([r[0] for r in rows], dtype=float)
    net = np.array([r[1] for r in rows], dtype=float)
    imp = np.array([r[2] for r in rows], dtype=float)
    exp = np.array([r[3] for r in rows], dtype=float)

    # Keep only the most recent contiguous simulator run, so a gap between
    # demo sessions is not drawn as a straight line across the chart.
    gaps = np.flatnonzero(np.diff(t) > 30.0)
    start = int(gaps[-1]) + 1 if len(gaps) else 0
    if len(t) - start < 20:
        start = 0
    t, net, imp, exp = t[start:], net[start:], imp[start:], exp[start:]

    minutes = (t - t[0]) / 60.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 3.4), dpi=200,
                                   gridspec_kw={"width_ratios": [2.1, 1]})
    ax1.axhline(0, color="#94a3b8", lw=1)
    ax1.fill_between(minutes, net, 0, where=net >= 0, color="#f59e0b", alpha=0.35,
                     interpolate=True, label="import")
    ax1.fill_between(minutes, net, 0, where=net < 0, color="#10b981", alpha=0.35,
                     interpolate=True, label="export")
    ax1.plot(minutes, net, color=INK, lw=1.3)
    ax1.set_xlabel("minutes of demo run")
    ax1.set_ylabel("net power (kW)")
    ax1.set_title("node-001 — net metering, accelerated solar cycle (positive = import)",
                  fontsize=10, loc="left")
    ax1.legend(frameon=False, fontsize=8, loc="upper left")
    ax1.grid(axis="y", color="#e2e8f0", lw=0.6)
    ax1.set_axisbelow(True)

    labels = ["import", "export"]
    vals = [imp[-1] - imp[0], exp[-1] - exp[0]]
    bars = ax2.bar(labels, vals, color=["#f59e0b", "#10b981"], width=0.55)
    for b, v in zip(bars, vals):
        shown = f"{v * 1000:.0f} Wh" if v < 0.1 else f"{v:.2f} kWh"
        ax2.text(b.get_x() + b.get_width() / 2, v, shown,
                 ha="center", va="bottom", fontsize=9, color=INK)
    ax2.set_title("accumulated energy", fontsize=10, loc="left")
    ax2.grid(axis="y", color="#e2e8f0", lw=0.6)
    ax2.set_axisbelow(True)
    ax2.set_ylim(0, max(vals) * 1.25 if max(vals) > 0 else 1)

    for ax in (ax1, ax2):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(IMG / "fig_energy.png", facecolor="white")
    plt.close(fig)
    print(f"  energy figure: {len(t)} rows, {minutes[-1]:.1f} min, "
          f"import {vals[0] * 1000:.0f} Wh, export {vals[1] * 1000:.0f} Wh")


def main() -> int:
    IMG.mkdir(parents=True, exist_ok=True)
    confusion()
    energy()
    for p in sorted(IMG.glob("fig_*.png")):
        print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
