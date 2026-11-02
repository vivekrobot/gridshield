"""Capture a live dashboard screenshot for the PPT report.

Starts the local simulator and Streamlit, waits until the page has rendered,
then saves a viewport screenshot with Playwright driving the installed Chrome.

Run:  python scripts/capture_dashboard.py
Out:  build/img/dashboard.png

The simulator writes to data/ppt.db so the normal demo database is untouched.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "img" / "dashboard.png"
DB = ROOT / "data" / "ppt.db"


def wait_health(url: str, timeout: float = 120.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1.0)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8514)
    ap.add_argument("--duration", type=float, default=100.0,
                    help="simulator run time in seconds")
    ap.add_argument("--width", type=int, default=1800)
    ap.add_argument("--height", type=int, default=940)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed:  pip install playwright")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    DB.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ, GRIDSHIELD_DB=str(DB))
    sim = subprocess.Popen(
        [sys.executable, "-m", "sim.run", "--mode", "local",
         "--duration", str(args.duration), "--db", str(DB)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ui = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "dashboard/app.py",
         "--server.port", str(args.port), "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    ok = False
    try:
        url = f"http://localhost:{args.port}"
        if not wait_health(url + "/_stcore/health"):
            print("dashboard did not become healthy")
            return 1
        time.sleep(12)  # let a few telemetry rows land

        with sync_playwright() as p:
            last_error = None
            for channel in ("chrome", "msedge", None):
                try:
                    browser = p.chromium.launch(channel=channel, headless=True)
                    break
                except Exception as exc:  # channel not installed
                    last_error = exc
            else:
                print("no Chromium-based browser found:", last_error)
                return 1

            page = browser.new_page(
                viewport={"width": args.width, "height": args.height},
                device_scale_factor=2,
            )
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            try:
                page.wait_for_function(
                    "document.body.innerText.includes('GridShield') "
                    "&& document.body.innerText.length > 400",
                    timeout=90_000,
                )
            except Exception:
                print("page did not finish rendering")
            page.wait_for_timeout(6000)
            page.screenshot(path=str(args.out), full_page=False)
            args.out.with_suffix(".txt").write_text(page.inner_text("body"), encoding="utf-8")
            print("title:", page.title())
            browser.close()
        ok = True
        print(f"wrote {args.out.relative_to(ROOT)} ({args.out.stat().st_size / 1024:.0f} kB)")
    finally:
        for proc in (ui, sim):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
