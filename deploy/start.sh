#!/usr/bin/env sh
set -eu

export GRIDSHIELD_DB="${GRIDSHIELD_DB:-/data/gridshield.db}"
PORT="${PORT:-8501}"

if [ "${GRIDSHIELD_MODE:-demo}" = "live" ]; then
    echo "Starting MQTT ingestor (live mode)..."
    python -m cloud.ingest &
else
    echo "Starting local simulator (demo mode)..."
    python -m sim.run --mode local --duration 0 &
fi

exec python -m streamlit run dashboard/app.py \
    --server.address 0.0.0.0 \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false
