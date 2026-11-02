// PZEM metering, 2 kHz waveform acquisition, THD/crest estimation.
#pragma once

#include <Arduino.h>

#include "state.h"

namespace sensors {

void begin();

// Non-blocking: polls both PZEM meters when their 1 s slot is due.
void readMeters(Measurements& measurements, uint32_t now_ms);

// Copies the most recent completed 80 ms window, if a new one is available.
bool takeWindow(WaveWindow& window, WindowMetrics& metrics);

void integrateEnergy(Measurements& measurements, float dt_seconds);

}  // namespace sensors
