// Latching fail-safe interlock. Mirrors cloud/safety.py.
#pragma once

#include <Arduino.h>

#include "state.h"

namespace safety {

void begin();
void evaluate(const Measurements& measurements, const AiResult& ai, uint32_t now_ms);
void serviceIndicators(uint32_t now_ms);

bool tripped();
const char* faultCode();
void requestReset();
void remoteTrip();

}  // namespace safety
