// Fail-safe relay interlock.
//
// Policy:
//   * The relay is energised to keep the load connected. Loss of ESP32 power
//     therefore opens the load (the only genuinely fail-safe behaviour an
//     inexpensive relay module can offer).
//   * A trip latches. It never auto-recloses; a human must call requestReset()
//     from the dashboard, the physical button, or MQTT after the measurements
//     have stayed inside the reset envelope for the confirmation period.
//   * Thresholds are checked every 200 ms using PZEM RMS values. The edge AI
//     can add a trip for SHORT_CIRCUIT_OVERLOAD, never suppress one.
#include "safety.h"

#include "config.h"

namespace safety {
namespace {

bool s_tripped = false;
const char* s_fault = nullptr;
uint8_t s_tripCount = 0;
uint8_t s_resetCount = 0;
uint8_t s_armCount = 0;
bool s_outputClosed = false;

bool s_resetRequested = false;
uint32_t s_resetRequestedAt = 0;

uint32_t s_sensorLostSince = 0;

void setRelay(bool closed) {
    digitalWrite(PIN_RELAY, closed ? RELAY_CLOSED_LEVEL : RELAY_OPEN_LEVEL);
}

void applyTrip(const char* code) {
    s_tripped = true;
    s_fault = code;
    s_tripCount = 0;
    s_resetCount = 0;
    s_armCount = 0;
    s_resetRequested = false;
    s_outputClosed = false;
    setRelay(false);
}

void closeRelay() {
    s_tripped = false;
    s_fault = nullptr;
    s_tripCount = 0;
    s_resetCount = 0;
    s_armCount = 0;
    s_resetRequested = false;
    s_outputClosed = true;
    setRelay(true);
}

bool resetEnvelope(const Measurements& measurements) {
    return measurements.i_load <= GS_I_RESET_A &&
           measurements.v_rms >= GS_V_RESET_MIN &&
           measurements.v_rms <= GS_V_RESET_MAX;
}

}  // namespace

void begin() {
    // Drive the safe level before enabling the output so the relay cannot
    // chatter during boot.
    digitalWrite(PIN_RELAY, RELAY_OPEN_LEVEL);
    pinMode(PIN_RELAY, OUTPUT);
    setRelay(false);

    pinMode(PIN_LED_OK, OUTPUT);
    pinMode(PIN_LED_TRIP, OUTPUT);
    pinMode(PIN_BUZZER, OUTPUT);
    pinMode(PIN_RESET_BUTTON, INPUT_PULLUP);

    digitalWrite(PIN_LED_OK, LOW);
    digitalWrite(PIN_LED_TRIP, HIGH);
    digitalWrite(PIN_BUZZER, BUZZER_ACTIVE_HIGH ? LOW : HIGH);

    s_tripped = false;
    s_fault = nullptr;
    s_tripCount = 0;
    s_resetCount = 0;
    s_armCount = 0;
    s_resetRequested = false;
    s_outputClosed = false;
    s_sensorLostSince = millis();
}

void evaluate(const Measurements& measurements, const AiResult& ai, uint32_t now_ms) {
    if (!measurements.valid) {
        // No trustworthy voltage/current source. After a grace period this is
        // itself a fault: we must not keep a load energised while blind.
        s_armCount = 0;
        if (now_ms - s_sensorLostSince >= GS_SENSOR_FAULT_MS && !s_tripped) {
            applyTrip("SENSOR_FAULT");
        }
        return;
    }
    s_sensorLostSince = now_ms;

    if (s_tripped) {
        if (!s_resetRequested) {
            return;
        }
        if (now_ms - s_resetRequestedAt > GS_RESET_REQUEST_TIMEOUT_MS) {
            s_resetRequested = false;
            s_resetCount = 0;
            return;
        }
        if (resetEnvelope(measurements)) {
            if (++s_resetCount >= GS_RESET_CONFIRM_SAMPLES) {
                closeRelay();
            }
        } else {
            s_resetCount = 0;
        }
        return;
    }

    const char* code = nullptr;
    if (measurements.i_load > GS_I_TRIP_A) {
        code = "OVERCURRENT";
    } else if (measurements.v_rms < GS_V_MIN_TRIP) {
        code = "UNDERVOLTAGE";
    } else if (measurements.v_rms > GS_V_MAX_TRIP) {
        code = "OVERVOLTAGE";
    } else if (ai.valid && ai.class_index == 4 &&
               ai.confidence >= GS_AI_TRIP_CONFIDENCE) {
        code = "AI_OVERLOAD";
    }

    if (code == nullptr) {
        s_tripCount = 0;
        // Boot/recovery: stay open until the rule base has seen a full
        // confirmation period of healthy measurements, then energise the load.
        if (!s_outputClosed) {
            if (++s_armCount >= GS_TRIP_CONFIRM_SAMPLES) {
                closeRelay();
            }
        }
        return;
    }
    s_armCount = 0;
    if (++s_tripCount >= GS_TRIP_CONFIRM_SAMPLES) {
        applyTrip(code);
    }
}

void serviceIndicators(uint32_t now_ms) {
    digitalWrite(PIN_LED_OK, s_tripped ? LOW : HIGH);
    digitalWrite(PIN_LED_TRIP, s_tripped ? HIGH : LOW);

    bool buzzer = false;
    if (s_tripped) {
        buzzer = (now_ms % 2000UL) < 180UL;
    }
    if (BUZZER_ACTIVE_HIGH) {
        digitalWrite(PIN_BUZZER, buzzer ? HIGH : LOW);
    } else {
        digitalWrite(PIN_BUZZER, buzzer ? LOW : HIGH);
    }
}

bool tripped() {
    return s_tripped;
}

const char* faultCode() {
    return s_fault;
}

void requestReset() {
    if (!s_tripped || s_resetRequested) {
        return;
    }
    s_resetRequested = true;
    s_resetRequestedAt = millis();
    s_resetCount = 0;
}

void remoteTrip() {
    // Tripping is always safe to accept remotely. Resetting is not.
    if (!s_tripped) {
        applyTrip("REMOTE");
    }
}

}  // namespace safety
