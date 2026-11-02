"""Streamlit entrypoint for a self-contained, live public demo.

Use this file as the Streamlit Community Cloud "Main file path":

    dashboard/demo_app.py

It writes synthetic telemetry to ``data/demo.db`` before loading the normal
dashboard.  For a real installation use ``dashboard/app.py`` and run
``cloud.ingest`` (or the Docker image) instead.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("GRIDSHIELD_DEMO", "1")
os.environ.setdefault("GRIDSHIELD_DB", str(ROOT / "data" / "demo.db"))

runpy.run_path(str(ROOT / "dashboard" / "app.py"), run_name="__main__")
