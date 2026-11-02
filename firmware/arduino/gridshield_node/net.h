// WiFi + MQTT transport. Topic contract matches cloud/config.py:
//   smart_grid/households/{device_id}/telemetry
//   smart_grid/households/{device_id}/cmd
//   smart_grid/households/{device_id}/status   (LWT)
#pragma once

#include <Arduino.h>

#include "state.h"

namespace net {

void begin();
void loop();
bool connected();

bool publish(const Measurements& measurements,
             const AiResult& ai,
             const WaveWindow& window,
             bool tripped,
             const char* fault_code,
             uint32_t uptime_s);

}  // namespace net
