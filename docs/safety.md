# Safety interlock

The interlock is implemented **on the ESP32**, in `safety.cpp`. The cloud
mirror (`cloud/safety.py`) exists only to test the rule base, drive the
simulator and detect a disagreement between what the node reports and what the
rules say. No cloud outage can prevent a trip.

## Policy

1. **Energise-to-close.** The relay coil is energised while the load is
   allowed to draw power. Loss of MCU power, a firmware reset or a crash
   de-energises the coil and opens the load.
2. **Boot open.** `safety::begin()` drives the open level *before* configuring
   the pin as an output, preventing a boot-time glitch. The output stays open
   for three consecutive healthy evaluations (600 ms at the 200 ms safety
   period), then closes.
3. **Latching trip.** Once tripped, the relay never recloses automatically.
   There is no auto-reclose timer in the firmware (`GS_AUTO_RESET_MS 0`).
4. **Debounced decisions.** A trip requires three consecutive fault samples;
   a reset requires five consecutive in-envelope samples.
5. **Human reset.** A reset must be requested from the physical button, the
   dashboard (`reset` command) or MQTT. The request arms a 30 s window; if the
   measurements do not stay in the reset envelope for five consecutive samples
   during that window, the request expires and the relay stays open.
6. **Edge AI cannot suppress a trip.** The CNN may only *add* an
   `AI_OVERLOAD` trip when `SHORT_CIRCUIT_OVERLOAD` confidence is ≥ 0.85 for
   three consecutive samples. Rule-based trips take precedence.
7. **Blind = open.** If no trustworthy voltage/current measurement is
   available for 10 s, the firmware trips `SENSOR_FAULT`. The load is never
   left energised without supervision.

## Thresholds

| Parameter | Trip | Reset | Rationale |
|---|---|---|---|
| Load current | > 12.0 A | ≤ 10.5 A | 12 A is the benchmark household rating; the 1.5 A hysteresis prevents chatter at the boundary |
| Voltage | < 180 V or > 270 V | 190–250 V | protects against deep sags/swells while tolerating normal ±10 % variation |
| Confirmation | 3 samples (600 ms) | 5 samples (1 s) | rejects single-sample spikes and meter glitches |
| AI overload | class 4 and confidence ≥ 0.85 | – | high-confidence only; never the sole protection |
| Sensor loss | 10 s | – | allows a PZEM retry/brown-out before declaring a fault |
| Reset request timeout | – | 30 s | an operator request cannot stay armed indefinitely |

All values are duplicated in `firmware/.../config.h` and `cloud/config.py`.
`tests/test_firmware_contract.py` parses both files and fails if they drift.
The firmware build has no runtime configuration path for these limits; changing
them requires a reflash, which is intentional.

## State machine

```
                 boot
                  │ relay OPEN
                  ▼
        ┌──▶ ARMED_OPEN ── 3 healthy samples ──▶ CLOSED (normal)
        │         │                                   │
        │         └── fault ×3 ───────────────┐       │ fault ×3
        │                                     ▼       ▼
        │                                  TRIPPED (latched, relay OPEN)
        │                                     │
        │           reset request ────────────┘
        │                │
        │                ▼
        │        AWAITING_RESET
        │          │            │
        │   5 in-envelope    out-of-envelope / timeout
        │          │            │
        │          ▼            └──▶ TRIPPED (counter cleared)
        └──── CLOSED
```

`requestReset()` does nothing when the node is not tripped, so a stuck button
cannot force the relay closed from the normal state. `remoteTrip()` is always
accepted. `inject` is rejected by physical firmware.

## Reset semantics in the Python mirror

`SafetyEvaluator.safe_to_reset(v, i)` is a **pure predicate** for the current
sample. `SafetyEvaluator.reset(v, i)` feeds one confirmation sample and
returns `True` only on the confirmation-th consecutive in-envelope call. Any
out-of-envelope sample zeroes the counter. The simulator keeps a reset request
armed for 30 s and polls `reset()` once per tick, matching the firmware.

The cloud pipeline treats the edge as authoritative: if the node reports
`tripped=false` while the mirror is latched (for example after a successful
local reset), the mirror is re-armed with `force_reset()`. If the node reports
`relay=CLOSED` while the rules expect a trip, the cloud raises
`SAFETY_MISMATCH` but does **not** attempt to control the relay; the edge keeps
protecting.

## What this design does *not* protect against

| Limitation | Consequence / mitigation |
|---|---|
| Welded relay contact | The firmware cannot detect it. Use a certified contactor/breaker and consider an auxiliary contact in production. |
| Hobby relay module | Not certified for mains isolation or fault current. Use a proper contactor or SSR with appropriate ratings. |
| Single-pole switching | The neutral stays connected. Use a double-pole contactor if the installation requires full isolation. |
| No RCD/GFCI/arc detection | GridShield does not detect earth leakage or series arcs. Keep the upstream RCD/MCB/AFCI. |
| Trip state lost on reboot | The relay boots open and needs 600 ms of healthy measurements; the fault code is not persisted. |
| No hardware watchdog in this prototype | A hung loop stops safety evaluation. The relay stays in its last state, which may be closed. Add an external watchdog or enable the ESP32 task watchdog for production. |
| PZEM is not isolated from mains | The whole module is live; see the wiring warnings. |
| Cloud-only alerts | A broker/network outage delays alerts but never the trip. |

## Bench verification checklist

1. Power the node with no load: relay must be open, then close only after
   valid measurements and roughly 600 ms.
2. Apply 13 A (supervised load bank): relay opens on the third 200 ms sample;
   red LED and buzzer activate; `fault_code=OVERCURRENT`.
3. Remove the fault, do not press reset: relay stays open indefinitely.
4. Press reset while voltage is 260 V: relay stays open (outside reset
   envelope) and the request expires after 30 s.
5. Restore 230 V and press reset: relay closes after five in-envelope samples
   (about 1 s), `tripped=false`, `fault_code=null`.
6. Disconnect the PZEM and the ADC front-end: `SENSOR_FAULT` after 10 s.
7. Cut ESP32 power while the load is on: relay opens immediately.
8. Force a trip from the dashboard: `REMOTE` appears and the relay opens.
9. Send a cloud command while the node is offline: nothing happens; the edge
   remains in its last safe state.

## Testing

- `tests/test_safety.py` covers debounce, latching, the reset envelope,
  counter reset on an unsafe sample, force trip/reset and the AI confidence
  gate.
- `tests/test_firmware_contract.py` checks threshold parity, topic format and
  that automatic reclose stays disabled.
- `tests/test_pipeline.py` checks reported-trip alerts, the cloud mismatch
  detection and the sustained-degradation alert.
