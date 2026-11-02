# Deliberate departures from the paper

The implementation follows the paper's architecture (ESP32 edge node, 1D-CNN,
PZEM metering, MQTT, Streamlit/Folium, Isolation Forest) but corrects several
design and reporting flaws. Each change is listed here so the paper and the
artefacts do not contradict each other.

## Summary

| # | Paper / common claim | This implementation | Why |
|---|---|---|---|
| 1 | CNN input `(160, 1)` | `(160, 2)` — voltage **and** load current | overload is a current phenomenon; a voltage-only window cannot separate a short circuit from a sag |
| 2 | PZEM provides the CNN waveform | PZEM for RMS/energy; separate 2 kHz ADC front-end for waveforms | PZEM-004T v3 exposes only Modbus RMS aggregates, no samples |
| 3 | `.tflite` model on the ESP32 | portable C++ int8-weight kernels; `.tflite` export optional | works without TFLM/TensorFlow and is testable here; the TFLite path is documented but unverified |
| 4 | "sub-millisecond" inference | measured `ai_latency_ms` is published; no sub-ms claim | the claim depends on clock, compiler and TFLM; it must be measured, not assumed |
| 5 | `contamination=0.05` as fault rate | 0.05 is the *assumed* outlier fraction that sets the boundary | contamination is a hyperparameter, not an estimate of real fault prevalence |
| 6 | high accuracy as field performance | 97.8 % on 450 held-out **synthetic** windows | no field dataset; synthetic results validate the pipeline only |
| 7 | relay protection | latching interlock, boot-open, sensor-fault trip, human reset only | a prototype must fail open and must not auto-reclose after a fault |
| 8 | cloud dashboard as part of protection | cloud is observation/ops only; edge decides | network latency and outages must not affect protection |

## 1. Two-channel input

The paper's `(160, 1)` input is sufficient for voltage sag/swell and harmonic
distortion, but **not** for `SHORT_CIRCUIT_OVERLOAD`: a voltage-only window
sees a sag, which is indistinguishable from a downstream fault elsewhere on the
feeder. Adding the load-current channel makes the overload class separable and
also lets the model see the constant-power current rise during a sag.

Cost: the model has 1,709 parameters instead of roughly 1,600, and the firmware
needs a second ADC channel. Benefit: the class the protection actually cares
about is physically observable.

The cost is also reflected in the data contract: the firmware sends both
channels in the optional `wave` preview, and the model card records
`v_scale_volts=230`, `i_scale_amps=12`.

## 2. PZEM cannot supply a waveform

The PZEM-004T v3 is a Modbus energy meter. It returns voltage, current, power,
energy, frequency and power factor as **aggregates**; there is no raw-sample
register. A CNN fed only those numbers would not be doing waveform
classification.

The implementation therefore uses two paths:

- **PZEM (authoritative):** RMS voltage/current, PF, frequency, energy, and the
  input to the trip rule base.
- **ADC front-end (classifier):** ZMPT101B voltage and SCT-013 current sampled
  at 2 kHz into 160-sample windows, used by the CNN, THD/crest computation and
  as a fallback when the load meter is unreachable.

This is a hardware addition relative to a literal reading of the paper. It is
also what makes the paper's own THD/crest and "waveform" figures meaningful.

## 3. Weight-only int8 instead of TFLite Micro

`ml/export_c_header.py` emits symmetric per-tensor int8 weights, fp32 biases
and per-tensor scales. `firmware/.../ai.cpp` dequantises weights on the fly and
runs portable loops. There is **no int8 activation requantisation**, so the
firmware is numerically close to the fp32 model; the parity test reconstructs
the header and compares outputs on held-out windows.

Why not TFLite Micro in the shipped build:

- TensorFlow has no wheels for the Python 3.13/3.14 environment used here, so
  the export could not be run or verified.
- TFLM adds a runtime and a flatbuffer to the firmware; the int8 header keeps
  the build simple and inspectable.
- The paper's `.tflite` deployment is still supported by
  `ml/export_tflite.py` for a Python 3.10–3.12 environment. It is explicitly
  **not** covered by the default tests.

If you use the TFLite path, report the actual arena size and latency; do not
copy the paper's numbers.

## 4. The inference-latency claim

"Sub-millisecond" is not reproducible without stating the clock, compiler
optimisation level, TFLM version and whether the measurement includes input
normalisation. The firmware measures the full `classify()` call with `micros()`
and publishes `ai_latency_ms` in every telemetry packet. Any paper revision
should quote that measured value (and the board/clock), not a theoretical
operation count.

At 1,709 parameters and 2 kHz acquisition, inference once per second is not a
real-time constraint; the 200 ms safety loop never waits for the CNN.

## 5. Contamination is not a fault rate

`IsolationForest(contamination=0.05)` tells the estimator to expect about 5 %
outliers in the training set and places the decision boundary accordingly.
It does **not** mean 5 % of households are faulty. In this repository:

- the threshold is the p95 of healthy training scores (0.5536),
- the healthy false-positive rate is 5 % **by construction**,
- the synthetic degradation detection rate (99.9 %) is measured against
  synthetic drift, not field failures,
- the cloud requires a rolling median above `1.10 × threshold` before alerting.

A paper must report the threshold, the score distribution and the alerting
rule, not just `contamination=0.05`.

## 6. Synthetic results are not field accuracy

The 97.8 % held-out accuracy is on windows from the same physical generator as
the training data, with different random seeds. It demonstrates that the
pipeline learns the intended physics; it does not establish performance on:

- real PQD recordings with background harmonics and capacitor switching,
- multiple simultaneous disturbances,
- CT saturation, ADC clipping or phase error,
- other feeders, climates and load mixes.

The model card and README state this limitation explicitly. A field study
should use a held-out site, not a random split of the same generator.

## 7. Protection changes

The paper describes the relay as a protective actuator. The implementation adds
constraints that a protection review would require:

- **energise-to-close** wiring, so loss of MCU power opens the load;
- **boot open** and a 600 ms healthy-measurement arming period;
- **latching** trips with no automatic reclosing (`GS_AUTO_RESET_MS 0`);
- **human reset** only after five consecutive in-envelope samples within a
  30 s request window;
- **sensor-fault trip** after 10 s without a trustworthy measurement;
- **AI trip gating** at confidence 0.85, and never as the only protection;
- cloud/edge **mismatch alerts** without cloud control of the relay.

A hobby relay is still not a certified protective device. The paper should not
present this prototype as a replacement for an MCB/RCD.

## 8. Cloud is not in the protection loop

The Streamlit dashboard is read-mostly and polls SQLite. It can request a reset
or a remote trip, but it cannot force the relay closed and it is not needed for
a trip. This is a deliberate inversion of any architecture in which the cloud
"decides" to protect: WAN latency, broker outages and dashboard restarts are
not safety requirements.

The cloud does add value: payload validation, anomaly scoring, alert
de-duplication, offline detection and the safety mirror that flags a node whose
reported relay state contradicts the thresholds.

## 9. Smaller contract and reproducibility fixes

- The firmware publishes a full JSON contract (units, ranges, class names,
  fault codes) and the cloud rejects implausible values rather than storing
  them. A paper table alone is not a contract.
- Energy is integrated separately for import and export; net power is
  `V·(I_load − I_solar)/1000`. The simulator and cloud use the same convention,
  so "negative kW" always means export.
- Training is a dependency-light NumPy implementation with a fixed seed, so the
  reported metrics are reproducible on CPU. The environment is pinned in
  `requirements.txt`; the TFLite extra is separate.
- The paper's MQTT topic shape is kept
  (`smart_grid/households/<device_id>/telemetry`) and extended with a `cmd`
  topic and a retained `status` topic.

## What is faithful to the paper

- ESP32 edge deployment with a 1D-CNN for five PQD classes.
- 160-sample windows (80 ms at 50 Hz).
- PZEM-004T metering and a relay/buzzer/LED actuator set.
- MQTT telemetry to a Streamlit + Folium SCADA dashboard.
- Isolation Forest for predictive maintenance with contamination 0.05.
- Solar net metering with import/export accounting.

The corrections above are engineering and reporting fixes, not a change of
scope.
