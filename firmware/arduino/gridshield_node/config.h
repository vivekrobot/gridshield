// GridShield edge-node configuration.
//
// Every safety limit below mirrors cloud/config.py. If you change one, change
// the other and re-run `python -m unittest discover -s tests` so the cloud
// mirror and the firmware stay in agreement.
#pragma once

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------
#ifndef GS_DEVICE_ID
#define GS_DEVICE_ID "node-001"
#endif
#ifndef GS_SITE_NAME
#define GS_SITE_NAME "Demo household"
#endif
#define GS_FIRMWARE_VERSION "1.0.0"

// WLAN/MQTT secrets live in secrets.h (git-ignored). Copy
// secrets.example.h to secrets.h and edit it.
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

// ---------------------------------------------------------------------------
// Network
// ---------------------------------------------------------------------------
#define GS_MQTT_PORT 1883
#define GS_MQTT_TOPIC_PREFIX "smart_grid"
#define GS_MQTT_BUFFER_BYTES 6144
#define GS_PUBLISH_INTERVAL_MS 2000
#define GS_WIFI_RETRY_MS 10000
#define GS_MQTT_RETRY_MS 5000

// ---------------------------------------------------------------------------
// Pins (ESP32 DevKit v1). ADC1 is used because ADC2 is unavailable while WiFi
// is active. 34/35 are input-only pins with no internal pulls, which is fine
// for the biased AC front-end.
// ---------------------------------------------------------------------------
#define PIN_ADC_V 34
#define PIN_ADC_I 35

#define PIN_RELAY 25
#define PIN_BUZZER 27
#define PIN_LED_OK 32
#define PIN_LED_TRIP 33
#define PIN_RESET_BUTTON 14

// Most inexpensive relay boards are active-LOW: the coil is energised when the
// pin is LOW, which is also the fail-safe choice (loss of power opens the
// load). Set RELAY_CLOSED_LEVEL to HIGH for an active-HIGH module.
#define RELAY_CLOSED_LEVEL LOW
#define RELAY_OPEN_LEVEL HIGH
#define BUZZER_ACTIVE_HIGH 1

// PZEM-004T v3 energy meters (Modbus RTU, 9600 8N1).
#define PZEM_LOAD_RX 16
#define PZEM_LOAD_TX 17
#define PZEM_LOAD_ADDR 0x01
#define PZEM_SOLAR_RX 18
#define PZEM_SOLAR_TX 19
#define PZEM_SOLAR_ADDR 0x02
#define PZEM_BAUD 9600
#define PZEM_TIMEOUT_MS 150

// ---------------------------------------------------------------------------
// Acquisition. 2 kHz, 160 samples = 80 ms = 4 mains cycles at 50 Hz. The same
// window is fed to the 1D-CNN and used for THD/crest fallback measurements.
// ---------------------------------------------------------------------------
#define GS_SAMPLE_HZ 2000
#define GS_WINDOW 160
#define GS_ADC_MAX 4095
#define GS_ADC_BIAS 2048.0f  // mid-rail of the AC front-end

// Calibration: physical units per ADC count. Measure with a trusted reference
// and adjust. Defaults assume:
//   * ZMPT101B adjusted for ~1.0 V RMS output at 230 V RMS;
//   * SCT-013-030 (1 V RMS output at 30 A) with the bias tee below.
// With a 12-bit ADC at 11 dB attenuation (~3.0 V full scale, 0.733 mV/count):
//   V: 230 V / (1.0 V / 0.000733 V) = 0.169 V/count  -> 0.174 with margin
//   I:  30 A / (1.0 V / 0.000733 V) = 0.022 A/count  -> 0.0227 with margin
// If you fit a different CT/burden, recalculate and re-run the calibration.
#define GS_VOLT_SCALE 0.174f   // volts per ADC count
#define GS_CURRENT_SCALE 0.0227f  // amps per ADC count
#define GS_VOLT_INVERT 0
#define GS_CURRENT_INVERT 0

// ---------------------------------------------------------------------------
// Safety envelope (mirror of cloud/config.py)
// ---------------------------------------------------------------------------
#define GS_I_TRIP_A 12.0f
#define GS_V_MIN_TRIP 180.0f
#define GS_V_MAX_TRIP 270.0f
#define GS_I_RESET_A 10.5f
#define GS_V_RESET_MIN 190.0f
#define GS_V_RESET_MAX 250.0f
#define GS_TRIP_CONFIRM_SAMPLES 3
#define GS_RESET_CONFIRM_SAMPLES 5
#define GS_AI_TRIP_CONFIDENCE 0.85f

#define GS_SAFETY_INTERVAL_MS 200
#define GS_AI_INTERVAL_MS 1000
#define GS_METER_INTERVAL_MS 1000
#define GS_SENSOR_FAULT_MS 10000
#define GS_RESET_REQUEST_TIMEOUT_MS 30000

// Local auto-reclose is deliberately disabled. A human must reset after a
// trip. Set to a positive value only for a supervised bench demo.
#define GS_AUTO_RESET_MS 0

#define GS_AI_MIN_CURRENT_A 0.05f
