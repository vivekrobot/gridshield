# Hardware design

This is the reference hardware design for the GridShield edge node. It is a
**documented prototype**, not a certified product: no PCB layout or CAD files
are included in this repository. The firmware pin map and constants live in
`firmware/arduino/gridshield_node/config.h`; step-by-step hookup and isolation
options are in [`wiring.md`](wiring.md).

> **Mains safety.** The node measures and switches 230 V AC. Use an enclosure,
> an upstream MCB and RCD/GFCI, and certified terminals. Never work on the
> board while it is connected to mains. The relay is an additional load switch,
> not a substitute for protective devices.

## 1. Requirements

| Requirement | Target |
|---|---|
| Mains | 230 V RMS, 50 Hz, single phase |
| Load current | 0–12 A continuous, trip above 12 A |
| Waveform acquisition | 2 kHz, 160 samples (80 ms), V and I |
| PQD classes | NORMAL, sag, swell, harmonic, short-circuit overload |
| Local protection | latching trip, fail-open on power loss, human reset |
| Energy | import/export with a separate solar meter |
| Connectivity | Wi-Fi 2.4 GHz + MQTT |
| Environment | indoor, 0–40 °C, non-condensing (prototype) |

## 2. Block diagram

The three schematic sheets are
[`circuit-sheet-1-power.svg`](circuit-sheet-1-power.svg) (mains path),
[`circuit-sheet-2-isolation.svg`](circuit-sheet-2-isolation.svg) (isolation and
supplies) and [`circuit-sheet-3-mcu-io.svg`](circuit-sheet-3-mcu-io.svg) (MCU,
sensing and actuation). They are embedded in `build/GridShield-Project.pdf`.

```
        230 V L ── MCB ── RCD ──┬───────────────┬──────────────────────┐
                                │               │                      │
                                │          [PZEM #1 load]         [PZEM #2 solar]
                                │               │                      │
                                │          load branch            solar inverter
                                │               │                      │
                                │          relay NO/COM               │
                                │               │                      │
                                │             load(s)                 │
                                │                                      │
                           ZMPT101B            SCT-013-030             │
                                │                    │                 │
                           bias + clamp        bias + clamp            │
                                │                    │                 │
                          GPIO34 (ADC1)       GPIO35 (ADC1)           │
                                └──────────┬─────────┘                 │
                                           │                           │
                                      ESP32 DevKit v1                  │
                                   2 kHz sampler / CNN                │
                                   safety interlock                   │
                                   Wi-Fi + MQTT                       │
                                           │                           │
                             GPIO25 ── relay driver ── relay coil ◀────┘
                             GPIO27 ── buzzer
                             GPIO32/33 ── LEDs
                             GPIO14 ── reset button
                             UART1/2 ── isolated PZEM links
```

Power: a 5 V isolated supply feeds the ESP32 devkit and the relay module. The
PZEM meters need their own isolated 5 V feed (or a verified-isolated TTL side);
see [`wiring.md`](wiring.md#pzem-004t-v3-wiring-and-isolation).

## 3. Power budget

| Rail / load | Typical | Peak | Notes |
|---|---|---|---|
| ESP32 (Wi-Fi STA) | 100 mA | 240 mA | peak during TX; add 470 µF bulk |
| PZEM-004T ×2 | 20 mA each | 40 mA | plus isolated DC-DC losses |
| Relay coil (5 V) | 70 mA | 90 mA | only while closed |
| LEDs + buzzer | 15 mA | 40 mA | buzzer pulsed |
| **5 V total** | **~250 mA** | **~450 mA** | use a 5 V / 1 A isolated supply |

Use a certified isolated AC-DC module (e.g. HLK-PM01 class, 5 V 0.6–1 A) or an
external 5 V SELV adapter. Keep the relay coil on a short, separate trace with
a bulk capacitor; do not share the ADC ground return with the relay current.

## 4. Measurement front-end

### 4.1 Voltage channel (ZMPT101B)

The ZMPT101B is a small voltage transformer with an adjustable gain. Set its
output to about **1.0 V RMS at 230 V RMS** (2.83 V peak-to-peak; ±1.414 V
around the bias).

```
ZMPT OUT ──1k──┬─────────────── GPIO34
               │
            220nF
               │
              GND
               │
     3.3V ──10k─┼─10k── GND        (bias = 1.65 V)
               │
      clamp: BAT54S / TVS to 3.3V and GND
```

- Bias tee: two 10 kΩ resistors from 3.3 V to GND, decoupled with 10 µF.
- Series 1 kΩ limits fault current into the ADC; 220 nF to GND gives an
  anti-alias corner of `1/(2π·1k·220n) ≈ 723 Hz`, above the 7th harmonic
  (350 Hz) and below Nyquist (1 kHz).
- Schottky clamps (BAT54S) or a 3.3 V TVS protect the pin if the sensor is
  disconnected or the gain is misadjusted.
- Do not exceed 3.3 V at the pin. If the module needs a 5 V supply, power it
  from 5 V and divide/bias the output; never feed 5 V to the ADC.

**Scale:** with a 12-bit ADC at 11 dB attenuation (≈3.0 V full scale,
0.733 mV/count) and 1.0 V RMS output at 230 V:

```
V_per_count = 230 / (1.0 / 0.000733) ≈ 0.169 V/count
GS_VOLT_SCALE = 0.174   (with margin; calibrate against a reference)
```

### 4.2 Current channel (SCT-013-030)

The SCT-013-030 is a voltage-output clamp CT: 1 V RMS at 30 A. At 12 A it gives
0.4 V RMS (±0.566 V peak). Use the same bias tee and clamps as the voltage
channel.

```
SCT OUT ──1k──┬─────────────── GPIO35
              │
           220nF
              │
             GND
              │
    3.3V ──10k─┼─10k── GND
              │
     clamp to 3.3V / GND
```

**Scale:**

```
I_per_count = 30 / (1.0 / 0.000733) ≈ 0.022 A/count
GS_CURRENT_SCALE = 0.0227
```

- 12 A uses about 13 % of the ADC range; resolution is ~23 mA/count, ample for
  RMS and THD at the rated current.
- For an SCT-013-000 (100 A / 50 mA), fit a burden resistor (e.g. 33 Ω), then
  recalculate: 12 A → 6 mA → 0.198 V RMS → ~270 counts → ~0.044 A/count.
  Never open-circuit a current-output CT while current is flowing.
- Keep the CT lead twisted and away from the relay and PZEM switching nodes.

### 4.3 ADC configuration

- `analogReadResolution(12)`, `analogSetAttenuation(ADC_11db)`.
- ADC1 only (GPIO32–39); ADC2 is unavailable while Wi-Fi is active.
- GPIO34/35 are input-only, no internal pulls; the external bias tee sets the
  operating point.
- The firmware removes the per-window mean before RMS/THD, so a small bias
  error is harmless. Do not use per-window normalisation for the CNN: the
  amplitude is the signal.
- A dedicated task samples at 2 kHz, pinned to core 1. If Wi-Fi or flash
  stalls the loop for more than 2 ms, the sampler resynchronises and discards
  the partial window rather than publishing a distorted one.

### 4.4 PZEM meters

The PZEM-004T v3 supplies RMS voltage, current, power, energy, frequency and
PF over Modbus RTU. It does **not** provide waveforms, so it is used for
protection/energy only. Its TTL side may be mains-referenced depending on the
clone; use an isolated DC-DC and digital isolators, or a certified RS485 meter.
The complete wiring and isolation options are in
[`wiring.md`](wiring.md#pzem-004t-v3-wiring-and-isolation).

## 5. Actuation

### 5.1 Relay

Use an opto-isolated relay module rated for the load, or a discrete driver:

```
GPIO25 ──1k── base of NPN (2N2222/BC547)
                 │
               relay coil (5 V) ── collector
                 │
               flyback diode 1N4007 across coil
                 │
                GND
```

- The firmware is **energise-to-close**: `RELAY_CLOSED_LEVEL = LOW` for a
  common active-low module. Loss of MCU power opens the load.
- `safety::begin()` drives the open level before `pinMode(OUTPUT)`.
- The relay contact must be rated for the load's inrush (motors, compressors).
  Add an RC snubber (100 Ω + 100 nF X2) or MOV across an inductive load.
- A welded contact cannot be detected by this design. Use a certified
  contactor/breaker for real protection; an auxiliary contact feedback is a
  production improvement.
- For a 230 V load, switch the line conductor, not the neutral. A
  double-pole contactor is preferred for full isolation.

### 5.2 Indicators, buzzer, button

- Green LED (OK) on GPIO32, red LED (TRIP) on GPIO33, each with 220 Ω.
- Active buzzer on GPIO27; if it draws more than ~20 mA, drive it through an
  NPN transistor with a base resistor and a flyback diode.
- Reset button from GPIO14 to GND; the internal pull-up is enabled and the
  firmware debounces 40 ms. The button only *requests* a reset; it cannot force
  the relay closed.

## 6. Pin map

| ESP32 pin | Function | Notes |
|---|---|---|
| GPIO34 | voltage ADC | ADC1_CH6, input only |
| GPIO35 | current ADC | ADC1_CH7, input only |
| GPIO25 | relay | active-LOW module by default |
| GPIO27 | buzzer | active-high default |
| GPIO32 | green LED | 220 Ω to GND |
| GPIO33 | red LED | 220 Ω to GND |
| GPIO14 | reset button | to GND, internal pull-up |
| GPIO16 / GPIO17 | PZEM #1 RX / TX | UART2, 9600 8N1 |
| GPIO18 / GPIO19 | PZEM #2 RX / TX | UART1, 9600 8N1 |
| 5 V / GND | supply | isolated 5 V, bulk 470 µF |

## 7. PCB and layout guidance

If you turn this into a PCB:

- **Creepage/clearance:** at least 6 mm between mains (L/N, relay contacts,
  PZEM terminals) and SELV (ESP32, ADC, USB). Use an isolation slot under the
  relay and PZEM area. Follow IEC 60664-1 for the actual pollution degree.
- **Fusing:** 6–10 A fuse or MCB in the line, plus a 30 mA RCD upstream. Add a
  MOV (275 V) and an X2 capacitor at the input.
- **Terminals:** 5.08 mm pitch, ≥300 V, 10 A screw terminals or ferrules;
  strain relief and cable glands.
- **Grounding:** star ground at the ESP32; keep the ADC return away from the
  relay/PZEM return. Do not create a ground loop through the USB cable.
- **ADC traces:** short, guarded by GND, away from the relay and the Wi-Fi
  antenna keep-out. Place the bias/clamp parts at the ADC pin.
- **Relay:** keep the coil loop small; flyback diode at the coil; snubber at
  the contact. Consider a slot between contact and coil pins.
- **Thermal:** the 5 V regulator and relay coil are the main heat sources;
  keep them away from the ADC and the PZEM.
- **Markings:** label L, N, load, solar, 5 V, GND, polarity and fuse rating.
  Add a "prototype — not certified" label.

## 8. Enclosure and installation

- Flame-retardant ABS enclosure, IP54 or better, DIN-rail mountable.
- Separate the mains compartment from the ESP32/antenna with a physical
  barrier; bring the antenna outside if the enclosure is metallic.
- Use cable glands and ferrules; torque terminals to the manufacturer's spec.
- Bond the enclosure/earth according to local wiring rules.
- Leave the USB port accessible only when the mains is isolated, or use an
  external programming header with the board powered from SELV.

## 9. Bill of materials (reference)

| Ref | Part | Qty | Notes |
|---|---|---|---|
| U1 | ESP32 DevKit v1 (ESP32-WROOM-32) | 1 | 4 MB flash, 3.3 V |
| U2, U3 | PZEM-004T v3.0, 100 A | 2 | load + solar; set addresses 1/2 |
| U4 | ZMPT101B module | 1 | voltage transformer |
| CT1 | SCT-013-030 | 1 | 30 A / 1 V clamp |
| K1 | opto-isolated relay module, 5 V, ≥10 A | 1 | or discrete relay + driver |
| PS1 | isolated 5 V / 1 A AC-DC | 1 | HLK-PM01 class or certified adapter |
| PS2 | isolated 5 V DC-DC, 1 W (B0505S) | 2 | if PZEM isolation is required |
| ISO1 | digital isolator breakout (ADuM1201/Si862x) | 2 | UART isolation, 2 channels each |
| R1–R4 | 10 kΩ 1 % | 4 | bias dividers |
| R5–R8 | 1 kΩ 1 % | 4 | series protection |
| C1–C4 | 220 nF 50 V | 4 | anti-alias |
| C5–C8 | 10 µF 16 V | 4 | bias decoupling |
| D1–D4 | BAT54S / 3.3 V TVS | 4 | ADC clamps |
| D5 | 1N4007 | 1 | relay flyback (if discrete) |
| LED1/2 | green/red 3 mm | 2 | 220 Ω series |
| BZ1 | active buzzer 5 V | 1 | NPN driver if needed |
| SW1 | momentary push-button | 1 | reset request |
| F1 | 6–10 A fuse / MCB | 1 | line |
| RCD | 30 mA RCD/GFCI | 1 | upstream, mandatory |
| MOV1 | 275 V MOV | 1 | surge |
| C9 | 100 nF X2 | 1 | snubber, with 100 Ω |

## 10. Acceptance tests

1. **Insulation:** with the board unpowered, measure >10 MΩ between mains and
   SELV (use a proper insulation tester; do not apply high voltage to the
   ESP32).
2. **Power:** 5 V rail stays within ±5 % with Wi-Fi transmitting and the relay
   energised.
3. **ADC:** inject a known AC signal; verify RMS and THD against a reference
   meter; calibrate `GS_VOLT_SCALE`/`GS_CURRENT_SCALE`.
4. **PZEM:** compare PZEM RMS with the reference; verify Modbus CRC and
   addresses; disconnect one meter and confirm the ADC fallback.
5. **Protection:** supervised load bank; confirm trip at >12 A after 3 samples,
   latching, and reset only after 5 in-envelope samples.
6. **Fail-safe:** cut MCU power while the load is on; the relay must open.
7. **Thermal:** run at rated current for 1 h; check terminal and relay
   temperatures.
8. **EMC pre-check:** no reset/reboot with the relay switching an inductive
   load; add snubber/ferrite if needed.

## 11. Known limitations / next steps

- No PCB, CAD, or certified enclosure design is included; the design is
  schematic-level.
- The relay is a hobby module and cannot detect a welded contact.
- PZEM isolation depends on the module revision; the safe design adds a
  barrier or uses a certified RS485 meter.
- No hardware watchdog or auxiliary contact feedback in this revision.
- Production work: 4-layer PCB with isolation slots, certified AC-DC, EMC
  pre-compliance, enclosure thermal test, and a proper protection relay.
