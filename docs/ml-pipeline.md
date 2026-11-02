# ML pipeline

Two independent models are used for two different jobs:

| Model | Job | Input | Output | Where it runs |
|---|---|---|---|---|
| 1D-CNN | power-quality disturbance (PQD) classification | `(160, 2)` V/I window | 5-class probability vector | ESP32 (int8 weights) and Python |
| Isolation Forest | predictive maintenance | 8 scalar telemetry features | anomaly score + health index | cloud |

## 1. PQD classifier

### Data

Because no public dataset matches the exact `(160, 2)` acquisition format of
this prototype, training uses a **physically parameterised synthetic
generator** (`ml/dataset.py`), not arbitrary noise:

| Class | Generation |
|---|---|
| `NORMAL` | 230 V ±2 %, 1.5–10.5 A, PF 0.88–1.0, 1–3 % V THD, 2–6 % I THD |
| `VOLTAGE_SAG` | retained voltage 0.55–0.86 pu, 5–20° phase jump, constant-power current rise |
| `VOLTAGE_SWELL` | 1.08–1.30 pu voltage, current change following the load model |
| `HARMONIC_DISTORTION` | strong 3rd/5th/7th harmonics on V and I (up to ~40 % I THD) |
| `SHORT_CIRCUIT_OVERLOAD` | current surge above the 12 A rating plus a voltage dip |

Every window includes sensor realism: gain error (±0.8–1.0 %), DC offset,
white noise, 49.6–50.4 Hz frequency wander, and random start phase. 55 % of
sag/swell windows are full-window events; the rest start part-way through with
a 1 ms raised-cosine edge. 600 windows per class → 3,000 total, split
70/15/15 **stratified** (2,100 / 450 / 450).

Regenerate the dataset with:

```powershell
python -m ml.train_cnn --per-class 600 --epochs 40
```

Add `--reuse-dataset` to train on the existing `data/processed/` arrays.

### Architecture

```
input (160, 2)
  Conv1D  8 filters, kernel 5, ReLU        → (156, 8)
  MaxPool 2                                → (78, 8)
  Conv1D 16 filters, kernel 3, ReLU        → (76, 16)
  MaxPool 2                                → (38, 16)
  global average ‖ global max              → (32,)
  Dense 32, ReLU
  Dense 5, softmax
```

1,709 parameters. The two-branch global pooling (mean + max) preserves both
average harmonic energy and short transients, which matters because a sag or
overload may occupy only part of the 80 ms window.

Normalisation is **fixed**, not per-window: `V / 230` and `I / 12`. Per-window
standardisation would erase the amplitude difference between a sag and a
swell, which is exactly the information the classifier needs.

### Training

- Pure NumPy forward/backward implementation (`ml/cnn.py`) with im2col,
  He initialisation, Adam (lr 3e-3, weight decay 1e-4), dropout-free but
  augmented (`ml/cnn.py::augment`: small time shift, gain and noise jitter).
- Label smoothing 0.05, batch 64, early stopping on validation accuracy
  (patience 8).
- CPU-only; the shipped run took **7.1 s** for 32 epochs on the development
  machine. No GPU or TensorFlow is required.

Artifacts:

| File | Contents |
|---|---|
| `models/cnn_weights.npz` | fp32 weights and architecture metadata |
| `models/cnn_model_card.json` | input spec, classes, metrics, limitations |
| `reports/cnn_metrics.json` | held-out metrics, per-class table, confusion matrix |
| `reports/confusion_matrix.png`, `reports/training_curve.png` | plots |
| `firmware/arduino/gridshield_node/model_weights.h` | int8 weights + scales for the ESP32 |

### Held-out results

Accuracy 0.9778, macro F1 0.9779 on 450 unseen synthetic windows. See
`reports/cnn_metrics.json` for the exact confusion matrix. The remaining
errors are almost entirely NORMAL ↔ sag/swell, which is expected because the
mildest synthetic sags overlap the normal voltage tolerance band.

> These results validate the pipeline, not field performance. Real PQD data
> includes capacitor-switching transients, multiple simultaneous disturbances,
> and sensor artefacts not covered by the generator.

### Edge deployment and quantisation

`ml/export_c_header.py` writes:

- symmetric per-tensor int8 weights for both convolutions and both dense
  layers (`int8_t` arrays),
- fp32 biases,
- one scale per tensor,
- shape constants that the firmware asserts against `ml/config.py`.

The firmware (`ai.cpp`) dequantises weights on the fly into fp32 and runs
portable loops. This is **weight-only** quantisation: activations remain fp32,
so there is no int8 activation requantisation error. The activation arena is
about 13 KiB of static RAM and the whole build fits in 71 % of a 4 MB flash
partition (935,970 B flash, 75,196 B static RAM).

`tests/test_ml.py::test_exported_int8_header_matches_fp32_model` parses the
generated header, reconstructs the network in NumPy, and checks that the
quantised model agrees with the fp32 model on held-out windows. This is the
guard against a silent export regression.

### Optional TFLite Micro path

`ml/export_tflite.py` converts the trained weights to a `.tflite` flatbuffer
and emits a C array, for teams that want the standard TFLM runtime. It requires
TensorFlow, which currently has no wheels for Python 3.13+; run it in a
Python 3.10–3.12 environment:

```powershell
pip install -r requirements-tflite.txt
python -m ml.export_tflite
```

The TFLite path is **not** exercised by the default test suite or by the
shipped firmware. The paper's claim of sub-millisecond ESP32 inference is
therefore not reproduced here; the firmware reports the measured latency in
`ai_latency_ms`, and that value should be used in any write-up.

## 2. Isolation Forest (predictive maintenance)

### Features

Eight scalars per telemetry point (`ml/features.py`):

```
v_pu, i_pu, pf, thd_v, thd_i, p_kw, crest_i, freq_dev
```

### Training

- 5,000 synthetic healthy rows plus 2,000 synthetic degraded rows used only
  for evaluation.
- `StandardScaler` fitted on healthy data, then
  `IsolationForest(n_estimators=300, contamination=0.05, random_state=42)`.
- Threshold = p95 of healthy training scores → **0.5536**.

`contamination=0.05` is an **assumed** outlier rate; it sets the decision
boundary, it does not estimate the real fault prevalence.

### Scoring

`cloud/anomaly.py` maps the raw decision function to:

- bounded score in `[0, 1]`,
- `health_index = 100 × (1 − score)` (clipped),
- `degraded = score > threshold`.

The pipeline does not alert on a single point. It keeps a rolling window
(default 20) and requires the **median** score to exceed `1.10 × threshold`
after at least 10 observations. This suppresses isolated spikes at the cost of
a few seconds of detection delay.

### Results

| Metric | Value |
|---|---|
| Synthetic degradation detection | 0.9995 |
| Healthy false-positive rate | 0.05 |
| Threshold (p95 healthy) | 0.5536 |

The synthetic degradation model drifts PF down, THD up, voltage down and crest
factor up together. Real degradation signatures differ (bearing wear, capacitor
aging, loose terminals), so these numbers are an upper bound. The design
intentionally favours explainability (8 named features) over a deep
autoencoder.

## Reproducing everything

```powershell
python -m ml.train_cnn --per-class 600 --epochs 40
python -m ml.train_anomaly --rows 5000 --contamination 0.05
python -m unittest discover -s tests -v
```

The exporter is invoked automatically by `train_cnn.py`, so `model_weights.h`
is regenerated in the same run. If you change the architecture, update
`ml/config.py` and re-run; the firmware-contract tests fail if the header and
the Python config disagree.
