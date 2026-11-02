// GridShield ESP32 edge node.
//
// Responsibilities:
//   * sample V and I at 2 kHz into 80 ms windows,
//   * run the int8 1D-CNN with a ~13 KiB fp32 activation arena,
//   * read two PZEM-004T meters (load and solar) over Modbus RTU,
//   * enforce a latching fail-safe relay interlock locally,
//   * publish the telemetry contract over MQTT and accept reset/trip commands.
//
// Build with PlatformIO (`pio run -d firmware`) or Arduino IDE (install the
// PubSubClient library, select "ESP32 Dev Module", 4 MB flash).
#include <Arduino.h>

#include "ai.h"
#include "config.h"
#include "net.h"
#include "safety.h"
#include "sensors.h"
#include "state.h"

Measurements g_measurements;
AiResult g_ai;
WaveWindow g_window;
WindowMetrics g_lastMetrics;
bool g_haveMetrics = false;

uint32_t g_lastAiMs = 0;
uint32_t g_lastSafetyMs = 0;
uint32_t g_lastPublishMs = 0;
uint32_t g_lastEnergyMs = 0;
uint32_t g_lastStatusMs = 0;

bool g_buttonDown = false;
uint32_t g_buttonDownMs = 0;

void printStatus() {
    Serial.printf(
        "V=%.1f I=%.2f Is=%.2f Pnet=%+.3fkW PF=%.2f AI=%s(%.2f) %s H? relay=%s\n",
        g_measurements.v_rms, g_measurements.i_load, g_measurements.i_solar,
        g_measurements.p_net_kw, g_measurements.pf, g_ai.className(),
        g_ai.confidence, safety::tripped() ? "TRIP" : "ok",
        safety::tripped() ? "OPEN" : "CLOSED");
}

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.printf("\nGridShield %s device=%s\n", GS_FIRMWARE_VERSION, GS_DEVICE_ID);

    safety::begin();
    ai::begin();
    sensors::begin();
    net::begin();

    g_lastEnergyMs = millis();
    g_lastSafetyMs = millis();
}

void loop() {
    const uint32_t now = millis();
    net::loop();

    // ---------------------------------------------------------------- waveform
    WaveWindow window;
    WindowMetrics metrics;
    if (sensors::takeWindow(window, metrics)) {
        g_window = window;
        g_lastMetrics = metrics;
        g_haveMetrics = metrics.valid;
        g_measurements.waveform_ok = metrics.valid;
        g_measurements.thd_v = metrics.thd_v;
        g_measurements.thd_i = metrics.thd_i;
        g_measurements.crest_i = metrics.crest_i;
    }

    // ---------------------------------------------------------------- meters
    sensors::readMeters(g_measurements, now);

    const bool fallback = !g_measurements.load_meter_ok && g_haveMetrics;
    if (fallback) {
        g_measurements.v_rms = g_lastMetrics.v_rms;
        g_measurements.i_load = safety::tripped() ? 0.0f : g_lastMetrics.i_rms;
        g_measurements.pf = 0.98f;  // unknown without the meter
    }

    g_measurements.valid =
        (g_measurements.load_meter_ok || fallback) && g_measurements.v_rms > 10.0f;

    if (safety::tripped()) {
        g_measurements.i_load = 0.0f;
    }
    g_measurements.p_active =
        g_measurements.v_rms * g_measurements.i_load * g_measurements.pf;
    g_measurements.p_net_kw =
        g_measurements.v_rms * (g_measurements.i_load - g_measurements.i_solar) / 1000.0f;

    // ---------------------------------------------------------------- energy
    const uint32_t energyNow = millis();
    const float dtSeconds = (energyNow - g_lastEnergyMs) / 1000.0f;
    g_lastEnergyMs = energyNow;
    if (g_measurements.valid) {
        sensors::integrateEnergy(g_measurements, dtSeconds);
    }

    // -------------------------------------------------------------------- AI
    if (now - g_lastAiMs >= GS_AI_INTERVAL_MS && g_window.seq > 0) {
        g_lastAiMs = now;
        ai::classify(g_window, g_ai);
    }

    // ---------------------------------------------------------------- safety
    if (now - g_lastSafetyMs >= GS_SAFETY_INTERVAL_MS) {
        g_lastSafetyMs = now;
        safety::evaluate(g_measurements, g_ai, now);
    }

    // Physical reset button: request only, never force the relay closed.
    const bool buttonDown = digitalRead(PIN_RESET_BUTTON) == LOW;
    if (buttonDown && !g_buttonDown) {
        g_buttonDownMs = now;
    }
    if (!buttonDown && g_buttonDown && now - g_buttonDownMs > 40) {
        safety::requestReset();
        Serial.println("[button] reset requested");
    }
    g_buttonDown = buttonDown;

    // -------------------------------------------------------------- telemetry
    if (now - g_lastPublishMs >= GS_PUBLISH_INTERVAL_MS) {
        g_lastPublishMs = now;
        net::publish(g_measurements, g_ai, g_window, safety::tripped(),
                     safety::faultCode(), now / 1000UL);
    }

    safety::serviceIndicators(now);

    if (now - g_lastStatusMs >= 5000) {
        g_lastStatusMs = now;
        printStatus();
    }
}
