# Wiring and hardware

> **Danger: mains voltage.** This section describes a prototype that connects
> to 230 V AC. Work only if you are competent to do so, use an enclosure,
> fuse/MCB and RCD, and never prototype mains wiring on a breadboard. The
> firmware relay is an additional load switch, not a replacement for certified
> protection.

Reference drawings: [`hardware-design.md`](hardware-design.md) explains the
blocks, power budget and layout rules; [`circuit-sheet-1-power.svg`](circuit-sheet-1-power.svg)
(mains path and meters), [`circuit-sheet-2-isolation.svg`](circuit-sheet-2-isolation.svg)
(isolation barrier) and [`circuit-sheet-3-mcu-io.svg`](circuit-sheet-3-mcu-io.svg)
(MCU and I/O) are the schematics. All of them, plus this document, are compiled
into `build/GridShield-Project.pdf` by `scripts/build-pdf.ps1`.

## Bill of materials

| Item | Suggested part | Notes |
|---|---|---|
| MCU | ESP32 DevKit v1 (ESP32-WROOM-32) | 4 MB flash; 3.3 V logic; ADC1 only |
| Voltage sensor | ZMPT101B module | transformer-isolated, adjustable gain |
| Current sensor | SCT-013-030 (30 A / 1 V) | voltage-output clamp CT; use SCT-013-000 + burden for higher ranges |
| Energy meters | 2 × PZEM-004T v3.0 (100 A) | Modbus RTU, 9600 8N1; one load, one solar |
| Relay | opto-isolated 1-channel 5 V module, ≥10 A | energise-to-close wiring; add snubber for inductive loads |
| Indicators | red/green LEDs + 220 Ω, active buzzer | buzzer via NPN if >20 mA |
| Reset button | momentary NO push-button | to GPIO14, internal pull-up, to GND |
| Passives | 2 × 10 kΩ (bias), 2 × 10 µF, 2 × 1 kΩ series, 2 × 100 nF, 3.3 V TVS/clamp diodes | ADC front-end protection |
| Supply | 5 V / 2 A isolated supply | PZEM needs 5 V; ESP32 devkit regulator |
| Protection | 6–10 A MCB + 30 mA RCD, MOV | upstream of everything |

## Pin map

| ESP32 pin | Direction | Function |
|---|---|---|
| GPIO34 | ADC1_CH6 input | conditioned voltage waveform |
| GPIO35 | ADC1_CH7 input | conditioned load-current waveform |
| GPIO25 | output | relay coil (active-LOW module by default) |
| GPIO27 | output | buzzer |
| GPIO32 | output | green "OK" LED |
| GPIO33 | output | red "TRIP" LED |
| GPIO14 | input, pull-up | reset button (active-LOW) |
| GPIO16 / GPIO17 | UART2 RX / TX | PZEM load meter |
| GPIO18 / GPIO19 | UART1 RX / TX | PZEM solar meter |

ADC2 pins are avoided because they are unavailable while Wi-Fi is active.
GPIO34/35 are input-only and have no internal pull-ups; the external bias
network defines the DC operating point.

## AC front-end (both channels)

Each sensor output must be biased to mid-rail and clamped to the ADC range:

```
sensor out ──1k──┬─────────────── GPIO34/35
                 │
        100nF ───┴── GND
                 │
      3.3V ──10k──┼──10k── GND        (bias tee, 1.65 V)
                 │
        clamp: Schottky to 3.3V and to GND
```

- ZMPT101B: power the module from **3.3 V** if it is stable at that supply, so
  its output bias is ~1.65 V and the full-scale output stays inside the ADC
  range. If your board requires 5 V, keep it on 5 V and level-shift/bias the
  output so the ADC pin never exceeds 3.3 V. Set the on-board potentiometer so
  ~230 V RMS gives roughly 1.0 V RMS at the output; then
  `GS_VOLT_SCALE ≈ 0.174 V/count` after calibration.
- SCT-013-030: its internal burden gives ~1 V at 30 A, so 12 A produces
  ~0.4 V RMS. With the default `GS_CURRENT_SCALE = 0.0227 A/count`, 12 A uses
  about 13 % of the 3 V ADC full scale. If you use an SCT-013-000 (50 mA
  secondary), fit a burden resistor (e.g. 33 Ω), recalculate the scale and
  recalibrate; never leave a current-output CT open-circuit while current
  flows.
- `analogSetAttenuation(ADC_11db)` gives an input range of roughly 0–3.1 V.
  `GS_ADC_BIAS` is documented as 2048 counts but the firmware removes the
  measured per-window mean, so a small bias error does not affect RMS or the
  classifier.
- Keep the analogue ground return separate from relay/PZEM current paths and
  keep sensor leads short and twisted.

## PZEM-004T v3 wiring and isolation

Each meter has two mains terminals (**L, N**) plus a 4-pin TTL header
(**5 V, GND, TX, RX**). Isolation varies between clones and revisions:
**do not assume the TTL header is safe to touch or to tie to the ESP32 ground**
until you have verified it. Treat the whole module as live.

### Option A - bench only, after verifying isolation

Only if a continuity test shows a high resistance (no galvanic path) between
L/N and the TTL GND, and the module is powered from an isolated 5 V supply:

```
ESP32 5V  ─────────── PZEM 5V        (isolated supply)
ESP32 GND ─────────── PZEM GND
ESP32 GPIO16 (RX) ◀── 1k/2k divider ◀── PZEM TX   (5 V → 3.3 V)
ESP32 GPIO17 (TX) ──1k───────────────▶ PZEM RX    (3.3 V is accepted as HIGH)
```

- PZEM TX is a 5 V output; never connect it directly to an ESP32 pin.
- Use one supply for the ESP32 and a **separate isolated** 5 V output for the
  meters. Do not power the meters from the ESP32 devkit's 5 V pin unless the
  meter's isolation has been verified.
- Repeat the continuity check on every unit. Clones differ.

### Option B - recommended for a permanent prototype

Add an isolation barrier for both power and UART:

```
ESP32 side                    barrier                    PZEM side
5V  ──▶ isolated DC-DC (1 kV) ──────────────────────────▶ 5V
GND ──────────────────────────────────────────────────▶ GND_PZEM
GPIO17 ──▶ digital isolator (UART TX) ─────────────────▶ RX
GPIO16 ◀── digital isolator (UART RX) ◀───────────────── TX
```

- Use a ready-made digital isolator module rated for at least the 9600 baud
  UART (e.g. an ADuM1201/Si862x breakout) and a 1 W isolated 5 V DC-DC
  (e.g. B0505S-1W). Both directions must be isolated; a divider alone is not
  isolation.
- The isolated side's ground is **PZEM GND only**. Never bridge it to the
  ESP32 ground.
- This keeps the ESP32, USB programmer and dashboard safe while the meter
  references mains.

### Option C - best for a real installation

Use a certified isolated energy meter with RS485 (for example an Eastron
SDM120/SDM230) and an isolated RS485 transceiver. This is the normal
industrial solution and avoids the PZEM isolation question entirely. The
firmware's Modbus request in `sensors.cpp` would need to be adapted to the
meter's register map and the transceiver's direction control.

### Common checks

- Set unique Modbus addresses (`PZEM_LOAD_ADDR = 0x01`,
  `PZEM_SOLAR_ADDR = 0x02`) with the vendor tool before deployment.
- The firmware polls input registers `0x0000..0x0009` in one request:
  voltage, current (2 regs), power (2 regs), energy (2 regs), frequency, PF.
- Both meters use separate UART peripherals but the same 9600 8N1 format.
- If the load meter is unreachable, the firmware falls back to the ADC RMS
  values, so classification and the interlock keep working (with reduced
  energy accuracy).

## Relay wiring (energise-to-close)

Use a normally-open contact in series with the load, and wire the module so the
coil is energised only while the firmware holds the pin at
`RELAY_CLOSED_LEVEL` (default LOW for common active-low boards):

```
L ── MCB ── RCD ── relay COM ── relay NO ── load ── N
```

Consequences:

- MCU power loss or firmware reset → coil de-energises → load opens.
- `safety::begin()` drives the open level before `pinMode(OUTPUT)` to avoid a
  boot-time glitch.
- A welded relay contact cannot be detected by this hardware. Use a certified
  contactor/breaker for real protection; consider feedback on an auxiliary
  contact in a production design.
- Add a flyback diode/snubber at the load for inductive appliances; the relay
  module usually has one for its own coil, not for the load.

## Bench calibration

1. **Voltage:** apply a known AC voltage (variac or a safe low-voltage AC
   source), read the ADC-derived RMS over serial, and solve
   `GS_VOLT_SCALE_new = GS_VOLT_SCALE_old × V_reference / V_measured`.
2. **Current:** use a resistive load and a clamp meter. Adjust
   `GS_CURRENT_SCALE` the same way. Confirm the phase/polarity; set
   `GS_CURRENT_INVERT`/`GS_VOLT_INVERT` if a channel is inverted.
3. **PZEM cross-check:** with the load meter healthy, compare PZEM RMS against
   ADC RMS. They should agree within a few percent; the PZEM value wins for
   protection and energy.
4. **Trip test:** use a low-voltage bench setup or a supervised load bank.
   Confirm 3 consecutive samples over 12 A latch the relay, and that it stays
   open until 5 consecutive samples are within 190–250 V and ≤10.5 A **and** a
   reset is requested.
5. **Fail-safe test:** pull the ESP32 power while the load is energised and
   confirm the relay opens.

## Enclosure and EMC

- Keep the 230 V compartment physically separate from the ESP32 and antennas;
  use a plastic enclosure with a DIN rail for the MCB/RCD.
- Do not power the ESP32 from the same unregulated rail as the relay coil;
  add bulk capacitance and a separate 5 V feed if the relay chatters.
- Route the CT lead away from switching nodes; twisted pair reduces pickup.
- Add a 100 nF capacitor at each ADC pin to ground (already in the front-end)
  and keep the Wi-Fi antenna clear of the mains wiring.
