// Portable C++ implementation of the GridShield 1D-CNN.
//
// The exported weights are symmetric per-tensor int8 with fp32 biases. This
// keeps the model small enough for the ESP32 flash while activations stay in
// fp32, so no TFLite Micro runtime is required. `ml/export_tflite.py` can
// produce a .tflite flatbuffer instead if you prefer the TFLM path.
#include "ai.h"

#include <math.h>
#include <string.h>

#include "config.h"

namespace ai {
namespace {

// Static buffers keep the ~13 KiB of activations off the small loop-task
// stack. classify() is only called from loop(), never concurrently.
float s_conv1[GS_L1 * GS_CONV1_FILTERS];
float s_pool1[(GS_L1 / GS_POOL_SIZE) * GS_CONV1_FILTERS];
float s_conv2[GS_L2 * GS_CONV2_FILTERS];
float s_pool2[GS_L3 * GS_CONV2_FILTERS];
float s_features[GS_DENSE_UNITS];
float s_hidden[GS_DENSE_UNITS];
float s_input[GS_WINDOW * GS_MODEL_N_CHANNELS];

inline float relu(float value) {
    return value > 0.0f ? value : 0.0f;
}

void conv1(const float* input) {
    constexpr int kOutLength = GS_L1;
    for (int f = 0; f < GS_CONV1_FILTERS; ++f) {
        for (int p = 0; p < kOutLength; ++p) {
            float acc = kConv1B[f];
            for (int k = 0; k < GS_CONV1_KERNEL; ++k) {
                for (int c = 0; c < GS_MODEL_N_CHANNELS; ++c) {
                    const int wi = ((k * GS_MODEL_N_CHANNELS) + c) * GS_CONV1_FILTERS + f;
                    acc += input[(p + k) * GS_MODEL_N_CHANNELS + c] *
                           (static_cast<float>(kConv1W[wi]) * kConv1WScale);
                }
            }
            s_conv1[p * GS_CONV1_FILTERS + f] = relu(acc);
        }
    }
}

void pool1() {
    constexpr int kOutLength = GS_L1 / GS_POOL_SIZE;
    for (int p = 0; p < kOutLength; ++p) {
        for (int f = 0; f < GS_CONV1_FILTERS; ++f) {
            const float a = s_conv1[(2 * p) * GS_CONV1_FILTERS + f];
            const float b = s_conv1[(2 * p + 1) * GS_CONV1_FILTERS + f];
            s_pool1[p * GS_CONV1_FILTERS + f] = a > b ? a : b;
        }
    }
}

void conv2() {
    constexpr int kInLength = GS_L1 / GS_POOL_SIZE;
    for (int f = 0; f < GS_CONV2_FILTERS; ++f) {
        for (int p = 0; p < GS_L2; ++p) {
            float acc = kConv2B[f];
            for (int k = 0; k < GS_CONV2_KERNEL; ++k) {
                for (int c = 0; c < GS_CONV1_FILTERS; ++c) {
                    const int wi = ((k * GS_CONV1_FILTERS) + c) * GS_CONV2_FILTERS + f;
                    acc += s_pool1[(p + k) * GS_CONV1_FILTERS + c] *
                           (static_cast<float>(kConv2W[wi]) * kConv2WScale);
                }
            }
            s_conv2[p * GS_CONV2_FILTERS + f] = relu(acc);
        }
    }
    (void)kInLength;
}

void pool2AndFeatures() {
    constexpr int kOutLength = GS_L2 / GS_POOL_SIZE;
    for (int p = 0; p < kOutLength; ++p) {
        for (int f = 0; f < GS_CONV2_FILTERS; ++f) {
            const float a = s_conv2[(2 * p) * GS_CONV2_FILTERS + f];
            const float b = s_conv2[(2 * p + 1) * GS_CONV2_FILTERS + f];
            s_pool2[p * GS_CONV2_FILTERS + f] = a > b ? a : b;
        }
    }

    for (int f = 0; f < GS_CONV2_FILTERS; ++f) {
        float sum = 0.0f;
        float maximum = s_pool2[f];
        for (int p = 0; p < kOutLength; ++p) {
            const float value = s_pool2[p * GS_CONV2_FILTERS + f];
            sum += value;
            if (value > maximum) {
                maximum = value;
            }
        }
        s_features[f] = sum / kOutLength;                 // global average
        s_features[GS_CONV2_FILTERS + f] = maximum;      // global max
    }
}

void denseLayers(float* probabilities) {
    for (int j = 0; j < GS_DENSE_UNITS; ++j) {
        float acc = kDense1B[j];
        for (int i = 0; i < GS_DENSE_UNITS; ++i) {
            acc += s_features[i] *
                   (static_cast<float>(kDense1W[i * GS_DENSE_UNITS + j]) * kDense1WScale);
        }
        s_hidden[j] = relu(acc);
    }

    float logits[GS_MODEL_N_CLASSES];
    float maximum = -1e30f;
    for (int j = 0; j < GS_MODEL_N_CLASSES; ++j) {
        float acc = kDense2B[j];
        for (int i = 0; i < GS_DENSE_UNITS; ++i) {
            acc += s_hidden[i] *
                   (static_cast<float>(kDense2W[i * GS_MODEL_N_CLASSES + j]) * kDense2WScale);
        }
        logits[j] = acc;
        if (acc > maximum) {
            maximum = acc;
        }
    }

    float sum = 0.0f;
    for (int j = 0; j < GS_MODEL_N_CLASSES; ++j) {
        const float value = expf(logits[j] - maximum);
        probabilities[j] = value;
        sum += value;
    }
    if (sum <= 0.0f) {
        sum = 1.0f;
    }
    for (int j = 0; j < GS_MODEL_N_CLASSES; ++j) {
        probabilities[j] /= sum;
    }
}

}  // namespace

void begin() {
    memset(s_conv1, 0, sizeof(s_conv1));
    memset(s_conv2, 0, sizeof(s_conv2));
    memset(s_features, 0, sizeof(s_features));
    memset(s_hidden, 0, sizeof(s_hidden));
}

void classify(const WaveWindow& window, AiResult& result) {
    const uint32_t startedUs = micros();

    float sumCurrentSq = 0.0f;
    float sumVoltageSq = 0.0f;
    for (int n = 0; n < GS_WINDOW; ++n) {
        sumCurrentSq += window.i[n] * window.i[n];
        sumVoltageSq += window.v[n] * window.v[n];
    }
    const float currentRms = sqrtf(sumCurrentSq / GS_WINDOW);
    const float voltageRms = sqrtf(sumVoltageSq / GS_WINDOW);

    memset(result.probs, 0, sizeof(result.probs));
    result.seq = window.seq;
    result.valid = true;

    // A de-energised or idle load carries no useful shape; calling it NORMAL
    // prevents the classifier from hallucinating a fault from noise.
    if (currentRms < GS_AI_MIN_CURRENT_A || voltageRms < 10.0f) {
        result.class_index = 0;
        result.confidence = 1.0f;
        result.probs[0] = 1.0f;
        result.latency_ms = (micros() - startedUs) / 1000.0f;
        return;
    }

    for (int n = 0; n < GS_WINDOW; ++n) {
        float v = window.v[n] / kInputVoltScale;
        float i = window.i[n] / kInputAmpScale;
        if (v > 4.0f) v = 4.0f;
        if (v < -4.0f) v = -4.0f;
        if (i > 4.0f) i = 4.0f;
        if (i < -4.0f) i = -4.0f;
        s_input[n * GS_MODEL_N_CHANNELS] = v;
        s_input[n * GS_MODEL_N_CHANNELS + 1] = i;
    }

    conv1(s_input);
    pool1();
    conv2();
    pool2AndFeatures();
    denseLayers(result.probs);

    uint8_t best = 0;
    for (uint8_t j = 1; j < GS_MODEL_N_CLASSES; ++j) {
        if (result.probs[j] > result.probs[best]) {
            best = j;
        }
    }
    result.class_index = best;
    result.confidence = result.probs[best];
    result.latency_ms = (micros() - startedUs) / 1000.0f;
}

}  // namespace ai
