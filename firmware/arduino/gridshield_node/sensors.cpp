// PZEM-004T v3 (Modbus RTU) + dual-channel ADC sampling.
//
// The PZEM gives trustworthy RMS aggregates but no raw waveform. The 1D-CNN
// needs a waveform, so V and I are also sampled from an AC front-end
// (ZMPT101B + SCT-013 with burden) at 2 kHz. PZEM values remain authoritative
// for protection; the ADC path is used for the classifier, THD and crest
// factor, and as a fallback when a meter is unreachable.
#include "sensors.h"

#include <math.h>
#include <string.h>

#include "config.h"

namespace sensors {
namespace {

constexpr int kHarmonics = 7;  // fundamental + 6 harmonics
constexpr int kFundamentalBin = 4;  // 50 Hz at Fs=2 kHz, N=160 -> bin 4

struct PzemSample {
    bool ok = false;
    float v = 0.0f;
    float i = 0.0f;
    float p = 0.0f;
    float pf = 0.0f;
    float freq = 50.0f;
};

HardwareSerial& kLoadPort = Serial2;
HardwareSerial& kSolarPort = Serial1;

portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;
WaveWindow s_pending;
WindowMetrics s_pendingMetrics;
bool s_ready = false;
uint32_t s_windowSeq = 0;

int16_t s_rawV[GS_WINDOW];
int16_t s_rawI[GS_WINDOW];
float s_workV[GS_WINDOW];
float s_workI[GS_WINDOW];
float s_goertzelCos[kHarmonics];
float s_goertzelCoeff[kHarmonics];

uint32_t s_lastMeterMs = 0;
PzemSample s_load;
PzemSample s_solar;

uint16_t crc16(const uint8_t* data, size_t length) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; ++bit) {
            if (crc & 0x0001) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

void flushPort(HardwareSerial& port) {
    while (port.available() > 0) {
        (void)port.read();
    }
}

bool readPzem(HardwareSerial& port, uint8_t address, PzemSample& out) {
    uint8_t request[8] = {address, 0x04, 0x00, 0x00, 0x00, 0x0A, 0x00, 0x00};
    uint16_t crc = crc16(request, 6);
    request[6] = static_cast<uint8_t>(crc & 0xFF);
    request[7] = static_cast<uint8_t>(crc >> 8);

    flushPort(port);
    port.write(request, sizeof(request));
    port.flush();

    uint8_t response[25];
    const uint32_t started = millis();
    while (port.available() < static_cast<int>(sizeof(response)) &&
           millis() - started < PZEM_TIMEOUT_MS) {
        delay(1);
    }
    if (port.available() < static_cast<int>(sizeof(response))) {
        flushPort(port);
        return false;
    }
    if (port.readBytes(response, sizeof(response)) != sizeof(response)) {
        flushPort(port);
        return false;
    }

    const uint16_t expected = static_cast<uint16_t>(response[23]) |
                              (static_cast<uint16_t>(response[24]) << 8);
    if (response[0] != address || response[1] != 0x04 || response[2] != 20 ||
        crc16(response, 23) != expected) {
        return false;
    }

    uint16_t regs[10];
    for (int i = 0; i < 10; ++i) {
        regs[i] = (static_cast<uint16_t>(response[3 + 2 * i]) << 8) |
                  static_cast<uint16_t>(response[4 + 2 * i]);
    }

    const uint32_t currentRaw = (static_cast<uint32_t>(regs[2]) << 16) | regs[1];
    const uint32_t powerRaw = (static_cast<uint32_t>(regs[4]) << 16) | regs[3];
    out.v = regs[0] / 10.0f;
    out.i = currentRaw / 1000.0f;
    out.p = powerRaw / 10.0f;
    out.freq = regs[7] / 10.0f;
    out.pf = regs[8] / 100.0f;
    out.ok = out.v > 1.0f && out.v < 400.0f && out.freq > 40.0f && out.freq < 70.0f;
    return out.ok;
}

// Goertzel magnitude at an exact DFT bin, scaled to sine amplitude.
float goertzel(const float* samples, int count, float coeff) {
    float s1 = 0.0f;
    float s2 = 0.0f;
    for (int n = 0; n < count; ++n) {
        const float s0 = samples[n] + coeff * s1 - s2;
        s2 = s1;
        s1 = s0;
    }
    const float power = s1 * s1 + s2 * s2 - coeff * s1 * s2;
    return sqrtf(power > 0.0f ? power : 0.0f) / (count / 2.0f);
}

float thdPercent(const float* samples) {
    const float fundamental = goertzel(samples, GS_WINDOW, s_goertzelCoeff[0]);
    if (fundamental < 1e-3f) {
        return 0.0f;
    }
    float harmonicPower = 0.0f;
    for (int h = 1; h < kHarmonics; ++h) {
        const float magnitude = goertzel(samples, GS_WINDOW, s_goertzelCoeff[h]);
        harmonicPower += magnitude * magnitude;
    }
    return 100.0f * sqrtf(harmonicPower) / fundamental;
}

void precomputeGoertzel() {
    for (int h = 0; h < kHarmonics; ++h) {
        const int bin = kFundamentalBin * (h + 1);
        s_goertzelCoeff[h] = 2.0f * cosf(2.0f * PI * static_cast<float>(bin) / GS_WINDOW);
    }
}

void finishWindow() {
    float meanV = 0.0f;
    float meanI = 0.0f;
    for (int n = 0; n < GS_WINDOW; ++n) {
        meanV += s_rawV[n];
        meanI += s_rawI[n];
    }
    meanV /= GS_WINDOW;
    meanI /= GS_WINDOW;

    float sumV2 = 0.0f;
    float sumI2 = 0.0f;
    float peakI = 0.0f;
    for (int n = 0; n < GS_WINDOW; ++n) {
        float v = (s_rawV[n] - meanV) * GS_VOLT_SCALE;
        float i = (s_rawI[n] - meanI) * GS_CURRENT_SCALE;
#if GS_VOLT_INVERT
        v = -v;
#endif
#if GS_CURRENT_INVERT
        i = -i;
#endif
        if (v > 400.0f) v = 400.0f;
        if (v < -400.0f) v = -400.0f;
        if (i > 80.0f) i = 80.0f;
        if (i < -80.0f) i = -80.0f;
        s_workV[n] = v;
        s_workI[n] = i;
        sumV2 += v * v;
        sumI2 += i * i;
        const float absI = fabsf(i);
        if (absI > peakI) peakI = absI;
    }

    WindowMetrics metrics;
    metrics.v_rms = sqrtf(sumV2 / GS_WINDOW);
    metrics.i_rms = sqrtf(sumI2 / GS_WINDOW);
    metrics.thd_v = metrics.v_rms > 5.0f ? thdPercent(s_workV) : 0.0f;
    metrics.thd_i = metrics.i_rms > 0.02f ? thdPercent(s_workI) : 0.0f;
    metrics.crest_i = metrics.i_rms > 0.02f ? peakI / metrics.i_rms : 1.414f;
    metrics.valid = metrics.v_rms > 10.0f;
    metrics.seq = ++s_windowSeq;

    portENTER_CRITICAL(&s_mux);
    memcpy(s_pending.v, s_workV, sizeof(s_pending.v));
    memcpy(s_pending.i, s_workI, sizeof(s_pending.i));
    s_pending.seq = metrics.seq;
    s_pendingMetrics = metrics;
    s_ready = true;
    portEXIT_CRITICAL(&s_mux);
}

void samplingTask(void* /*argument*/) {
    const uint32_t periodUs = 1000000UL / GS_SAMPLE_HZ;
    uint32_t nextUs = micros();
    int index = 0;

    for (;;) {
        const uint32_t nowUs = micros();
        if (static_cast<int32_t>(nowUs - nextUs) >= 0) {
            nextUs += periodUs;
            // If WiFi or a long flash write delayed us, resynchronise instead
            // of burst-sampling a distorted window.
            if (static_cast<int32_t>(nowUs - nextUs) > 2000) {
                nextUs = nowUs + periodUs;
                index = 0;
            }
            s_rawV[index] = static_cast<int16_t>(analogRead(PIN_ADC_V));
            s_rawI[index] = static_cast<int16_t>(analogRead(PIN_ADC_I));
            if (++index >= GS_WINDOW) {
                finishWindow();
                index = 0;
            }
        }
        taskYIELD();
    }
}

}  // namespace

void begin() {
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);

    pinMode(PIN_ADC_V, INPUT);
    pinMode(PIN_ADC_I, INPUT);

    kLoadPort.begin(PZEM_BAUD, SERIAL_8N1, PZEM_LOAD_RX, PZEM_LOAD_TX);
    kSolarPort.begin(PZEM_BAUD, SERIAL_8N1, PZEM_SOLAR_RX, PZEM_SOLAR_TX);
    kLoadPort.setTimeout(PZEM_TIMEOUT_MS);
    kSolarPort.setTimeout(PZEM_TIMEOUT_MS);

    precomputeGoertzel();
    s_lastMeterMs = millis() - GS_METER_INTERVAL_MS;

    xTaskCreatePinnedToCore(samplingTask, "gs_adc", 4096, nullptr, 1, nullptr, 1);
}

void readMeters(Measurements& measurements, uint32_t now_ms) {
    if (now_ms - s_lastMeterMs < GS_METER_INTERVAL_MS) {
        return;
    }
    s_lastMeterMs = now_ms;

    s_load = PzemSample{};
    s_solar = PzemSample{};
    readPzem(kLoadPort, PZEM_LOAD_ADDR, s_load);
    readPzem(kSolarPort, PZEM_SOLAR_ADDR, s_solar);

    measurements.load_meter_ok = s_load.ok;
    measurements.solar_meter_ok = s_solar.ok;
    measurements.seq++;

    if (s_load.ok) {
        measurements.v_rms = s_load.v;
        measurements.i_load = s_load.i;
        measurements.pf = s_load.pf;
        measurements.freq = s_load.freq;
    }

    if (s_solar.ok) {
        // PZEM reports solar current in the same direction as the load meter.
        measurements.i_solar = s_solar.i;
        if (measurements.i_solar < 0.0f) {
            measurements.i_solar = 0.0f;
        }
    } else {
        measurements.i_solar = 0.0f;
    }

    measurements.p_active = measurements.v_rms * measurements.i_load * measurements.pf;
    measurements.p_net_kw =
        measurements.v_rms * (measurements.i_load - measurements.i_solar) / 1000.0f;
}

bool takeWindow(WaveWindow& window, WindowMetrics& metrics) {
    bool available = false;
    portENTER_CRITICAL(&s_mux);
    if (s_ready) {
        window = s_pending;
        metrics = s_pendingMetrics;
        s_ready = false;
        available = true;
    }
    portEXIT_CRITICAL(&s_mux);
    return available;
}

void integrateEnergy(Measurements& measurements, float dt_seconds) {
    if (dt_seconds <= 0.0f) {
        return;
    }
    if (dt_seconds > 5.0f) {
        dt_seconds = 5.0f;
    }
    const float p = measurements.p_net_kw;
    if (p >= 0.0f) {
        measurements.energy_import_kwh += p * dt_seconds / 3600.0f;
    } else {
        measurements.energy_export_kwh += -p * dt_seconds / 3600.0f;
    }
}

}  // namespace sensors
