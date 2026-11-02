// Shared data types for the GridShield firmware.
#pragma once

#include <Arduino.h>

#include "config.h"
#include "model_weights.h"

struct Measurements {
    float v_rms = 0.0f;
    float i_load = 0.0f;
    float i_solar = 0.0f;
    float p_active = 0.0f;
    float p_net_kw = 0.0f;
    float pf = 0.0f;
    float freq = 50.0f;
    float thd_v = 0.0f;
    float thd_i = 0.0f;
    float crest_i = 1.414f;
    float energy_import_kwh = 0.0f;
    float energy_export_kwh = 0.0f;
    bool load_meter_ok = false;
    bool solar_meter_ok = false;
    bool waveform_ok = false;
    bool valid = false;  // at least one trustworthy voltage source seen
    uint32_t seq = 0;
};

struct WaveWindow {
    float v[GS_WINDOW] = {0};
    float i[GS_WINDOW] = {0};
    uint32_t seq = 0;
};

struct WindowMetrics {
    float v_rms = 0.0f;
    float i_rms = 0.0f;
    float thd_v = 0.0f;
    float thd_i = 0.0f;
    float crest_i = 1.414f;
    bool valid = false;
    uint32_t seq = 0;
};

struct AiResult {
    uint8_t class_index = 0;
    float confidence = 0.0f;
    float probs[GS_MODEL_N_CLASSES] = {0};
    float latency_ms = 0.0f;
    bool valid = false;
    uint32_t seq = 0;

    const char* className() const {
        if (class_index >= GS_MODEL_N_CLASSES) {
            return "NORMAL";
        }
        return kClassNames[class_index];
    }
};
