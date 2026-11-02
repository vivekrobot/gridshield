#include "net.h"

#include <PubSubClient.h>
#include <WiFi.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "config.h"
#include "safety.h"

namespace net {
namespace {

WiFiClient s_wifi;
PubSubClient s_client(s_wifi);

char s_clientId[64];
char s_telemetryTopic[128];
char s_commandTopic[128];
char s_statusTopic[128];

uint32_t s_lastWifiAttempt = 0;
uint32_t s_lastMqttAttempt = 0;
bool s_timeConfigured = false;

size_t appendf(char* buffer, size_t capacity, size_t length, const char* format, ...) {
    if (length >= capacity) {
        return capacity;
    }
    va_list args;
    va_start(args, format);
    const int written = vsnprintf(buffer + length, capacity - length, format, args);
    va_end(args);
    if (written < 0) {
        return length;
    }
    const size_t next = length + static_cast<size_t>(written);
    return next < capacity ? next : capacity;
}

bool readJsonString(const char* json, const char* key, char* out, size_t outSize) {
    const char* cursor = strstr(json, key);
    if (cursor == nullptr) {
        return false;
    }
    cursor = strchr(cursor + strlen(key), ':');
    if (cursor == nullptr) {
        return false;
    }
    ++cursor;
    while (*cursor == ' ' || *cursor == '\t') {
        ++cursor;
    }
    if (*cursor != '"') {
        return false;
    }
    ++cursor;
    size_t index = 0;
    while (*cursor != '\0' && *cursor != '"' && index + 1 < outSize) {
        out[index++] = *cursor++;
    }
    out[index] = '\0';
    return true;
}

void onMessage(char* topic, byte* payload, unsigned int length) {
    (void)topic;
    if (length > 256) {
        length = 256;
    }
    char message[257];
    memcpy(message, payload, length);
    message[length] = '\0';

    char action[24];
    if (!readJsonString(message, "\"action\"", action, sizeof(action))) {
        return;
    }

    if (strcmp(action, "reset") == 0) {
        safety::requestReset();
        Serial.println("[mqtt] reset requested by operator");
    } else if (strcmp(action, "trip") == 0) {
        safety::remoteTrip();
        Serial.println("[mqtt] remote trip accepted");
    } else if (strcmp(action, "inject") == 0) {
        // A physical node cannot synthesise a waveform fault. The simulator
        // implements `inject`; here it is deliberately rejected.
        Serial.println("[mqtt] inject is not supported on physical hardware");
    }
}

void configureTopics() {
    snprintf(s_telemetryTopic, sizeof(s_telemetryTopic), "%s/households/%s/telemetry",
             GS_MQTT_TOPIC_PREFIX, GS_DEVICE_ID);
    snprintf(s_commandTopic, sizeof(s_commandTopic), "%s/households/%s/cmd",
             GS_MQTT_TOPIC_PREFIX, GS_DEVICE_ID);
    snprintf(s_statusTopic, sizeof(s_statusTopic), "%s/households/%s/status",
             GS_MQTT_TOPIC_PREFIX, GS_DEVICE_ID);

    const uint32_t chip = static_cast<uint32_t>(ESP.getEfuseMac() & 0xFFFFFF);
    snprintf(s_clientId, sizeof(s_clientId), "gridshield-%s-%06lX", GS_DEVICE_ID,
             static_cast<unsigned long>(chip));
}

void connectMqtt() {
    if (strlen(GS_MQTT_USERNAME) > 0) {
        s_client.connect(s_clientId, GS_MQTT_USERNAME, GS_MQTT_PASSWORD,
                         s_statusTopic, 0, true, "offline");
    } else {
        s_client.connect(s_clientId, nullptr, nullptr,
                         s_statusTopic, 0, true, "offline");
    }

    if (s_client.connected()) {
        s_client.publish(s_statusTopic, "online", true);
        s_client.subscribe(s_commandTopic, 0);
        Serial.printf("[mqtt] connected to %s:%d\n", GS_MQTT_HOST, GS_MQTT_PORT);
    }
}

}  // namespace

void begin() {
    configureTopics();

    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.setSleep(false);
    WiFi.begin(GS_WIFI_SSID, GS_WIFI_PASSWORD);
    s_lastWifiAttempt = millis();

    s_client.setServer(GS_MQTT_HOST, GS_MQTT_PORT);
    s_client.setBufferSize(GS_MQTT_BUFFER_BYTES);
    s_client.setKeepAlive(20);
    s_client.setSocketTimeout(5);
    s_client.setCallback(onMessage);
}

void loop() {
    const uint32_t now = millis();

    if (WiFi.status() != WL_CONNECTED) {
        s_lastMqttAttempt = 0;
        if (now - s_lastWifiAttempt >= GS_WIFI_RETRY_MS) {
            s_lastWifiAttempt = now;
            WiFi.reconnect();
        }
        return;
    }

    if (!s_timeConfigured) {
        configTime(0, 0, GS_NTP_SERVER_1, GS_NTP_SERVER_2);
        s_timeConfigured = true;
    }

    if (!s_client.connected()) {
        if (s_lastMqttAttempt == 0 || now - s_lastMqttAttempt >= GS_MQTT_RETRY_MS) {
            s_lastMqttAttempt = now;
            connectMqtt();
        }
        return;
    }

    s_client.loop();
}

bool connected() {
    return WiFi.status() == WL_CONNECTED && s_client.connected();
}

bool publish(const Measurements& measurements,
             const AiResult& ai,
             const WaveWindow& window,
             bool tripped,
             const char* fault_code,
             uint32_t uptime_s) {
    if (!connected()) {
        return false;
    }

    static char payload[GS_MQTT_BUFFER_BYTES];
    size_t length = 0;
    const size_t capacity = sizeof(payload);

    const long epoch = static_cast<long>(time(nullptr));
    const long timestamp = epoch > 1000000000L ? epoch : 0;

    length = appendf(payload, capacity, length,
                     "{\"schema\":1,\"source\":\"esp32\",\"device_id\":\"%s\","
                     "\"ts\":%ld,\"seq\":%lu,"
                     "\"v_rms\":%.2f,\"i_load\":%.3f,\"i_solar\":%.3f,"
                     "\"p_active\":%.1f,\"p_net_kw\":%.4f,"
                     "\"pf\":%.3f,\"freq\":%.2f,\"thd_v\":%.2f,\"thd_i\":%.2f,"
                     "\"crest_i\":%.3f,\"energy_import_kwh\":%.5f,"
                     "\"energy_export_kwh\":%.5f,"
                     "\"ai_class\":\"%s\",\"ai_conf\":%.4f,\"ai_latency_ms\":%.2f,"
                     "\"ai_probs\":{\"NORMAL\":%.4f,\"VOLTAGE_SAG\":%.4f,"
                     "\"VOLTAGE_SWELL\":%.4f,\"HARMONIC_DISTORTION\":%.4f,"
                     "\"SHORT_CIRCUIT_OVERLOAD\":%.4f},"
                     "\"relay\":\"%s\",\"tripped\":%s,\"fault_code\":%s,"
                     "\"rssi\":%d,\"uptime_s\":%lu",
                     GS_DEVICE_ID, timestamp, static_cast<unsigned long>(measurements.seq),
                     measurements.v_rms, measurements.i_load, measurements.i_solar,
                     measurements.p_active, measurements.p_net_kw,
                     measurements.pf, measurements.freq, measurements.thd_v,
                     measurements.thd_i, measurements.crest_i,
                     measurements.energy_import_kwh, measurements.energy_export_kwh,
                     ai.className(), ai.confidence, ai.latency_ms,
                     ai.probs[0], ai.probs[1], ai.probs[2], ai.probs[3], ai.probs[4],
                     tripped ? "OPEN" : "CLOSED", tripped ? "true" : "false",
                     fault_code != nullptr ? "\"" : "null",
                     WiFi.RSSI(), static_cast<unsigned long>(uptime_s));

    if (fault_code != nullptr) {
        length = appendf(payload, capacity, length, "%s\"", fault_code);
    }

    if (window.seq > 0 && length + 32 < capacity) {
        // 80 points (every second sample) are enough for a dashboard preview
        // and keep the packet comfortably inside the MQTT buffer.
        length = appendf(payload, capacity, length, ",\"wave\":{\"v\":[");
        for (int n = 0; n < GS_WINDOW; n += 2) {
            length = appendf(payload, capacity, length, "%s%.1f", n == 0 ? "" : ",",
                             window.v[n]);
        }
        length = appendf(payload, capacity, length, "],\"i\":[");
        for (int n = 0; n < GS_WINDOW; n += 2) {
            length = appendf(payload, capacity, length, "%s%.2f", n == 0 ? "" : ",",
                             window.i[n]);
        }
        length = appendf(payload, capacity, length, "]}");
    }

    length = appendf(payload, capacity, length, "}");

    if (length >= capacity - 1) {
        Serial.println("[mqtt] telemetry packet truncated, not published");
        return false;
    }

    const bool ok = s_client.publish(s_telemetryTopic, payload, false);
    if (!ok) {
        Serial.println("[mqtt] publish failed");
    }
    return ok;
}

}  // namespace net
