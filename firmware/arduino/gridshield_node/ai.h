// Int8-weight 1D-CNN inference (architecture exported by ml/export_c_header.py).
#pragma once

#include <Arduino.h>

#include "state.h"

namespace ai {

void begin();
void classify(const WaveWindow& window, AiResult& result);

}  // namespace ai
