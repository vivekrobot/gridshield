"""Shared configuration for the GridShield ML pipeline.

Every number that the firmware also needs lives here (or is written into the
generated ``model_weights.h``) so that edge and cloud stay in sync.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"
FIRMWARE_DIR = ROOT / "firmware" / "arduino" / "gridshield_node"

# ---------------------------------------------------------------------------
# Signal acquisition
# ---------------------------------------------------------------------------
FS = 2000                 # samples / second (2 kHz)
WINDOW = 160              # 160 samples = 80 ms = 4 cycles at 50 Hz
N_CHANNELS = 2            # channel 0 = voltage, channel 1 = load current
V_NOMINAL = 230.0         # V RMS
I_RATED = 12.0            # A RMS (trip threshold)
V_MIN = 180.0             # V RMS
V_MAX = 270.0             # V RMS

# Fixed normalisation (NOT per-window standardisation: that would erase the
# amplitude information needed to tell a sag from a swell).
V_SCALE = V_NOMINAL       # pu voltage, nominal peak = 1.414
I_SCALE = I_RATED         # pu current, rated peak = 1.414

# ---------------------------------------------------------------------------
# 1D-CNN architecture (kept small enough for an ESP32)
# ---------------------------------------------------------------------------
CONV1_FILTERS = 8
CONV1_KERNEL = 5
CONV2_FILTERS = 16
CONV2_KERNEL = 3
POOL_SIZE = 2
DENSE_UNITS = 32
N_CLASSES = 5

CLASSES = (
    "NORMAL",
    "VOLTAGE_SAG",
    "VOLTAGE_SWELL",
    "HARMONIC_DISTORTION",
    "SHORT_CIRCUIT_OVERLOAD",
)
CLASS_TO_INDEX = {name: i for i, name in enumerate(CLASSES)}
INDEX_TO_CLASS = {i: name for name, i in CLASS_TO_INDEX.items()}

# Expected input length at each stage (valid convolutions, no padding).
L1 = WINDOW - CONV1_KERNEL + 1          # 156
L2 = L1 // POOL_SIZE - CONV2_KERNEL + 1  # 76
L3 = L2 // POOL_SIZE                     # 38
POOLED_FEATURES = CONV2_FILTERS * 2      # global average + global max

# ---------------------------------------------------------------------------
# Training / artefacts
# ---------------------------------------------------------------------------
SEED = 42
TRAIN_FRACTION = 0.70
VAL_FRACTION = 0.15
# Remaining 0.15 is the held-out test set.

WEIGHTS_PATH = MODELS_DIR / "cnn_weights.npz"
MODEL_CARD_PATH = MODELS_DIR / "cnn_model_card.json"
C_HEADER_PATH = FIRMWARE_DIR / "model_weights.h"
METRICS_PATH = REPORTS_DIR / "cnn_metrics.json"
CONFUSION_MATRIX_PATH = REPORTS_DIR / "confusion_matrix.png"
TRAINING_CURVE_PATH = REPORTS_DIR / "training_curve.png"

ANOMALY_MODEL_PATH = MODELS_DIR / "isolation_forest.joblib"
ANOMALY_META_PATH = MODELS_DIR / "anomaly_meta.json"

for _d in (PROCESSED_DIR, MODELS_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
