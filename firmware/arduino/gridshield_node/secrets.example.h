// Copy this file to secrets.h and fill in your own values.
// secrets.h is git-ignored and must never be committed.
#pragma once

#define GS_WIFI_SSID "your-ssid"
#define GS_WIFI_PASSWORD "your-password"

// Leave username/password empty for an anonymous broker.
#define GS_MQTT_HOST "192.168.1.10"
#define GS_MQTT_USERNAME ""
#define GS_MQTT_PASSWORD ""

// Optional NTP. Time is only used for the telemetry timestamp; the cloud
// substitutes its receive time when the node clock is not synchronised.
#define GS_NTP_SERVER_1 "pool.ntp.org"
#define GS_NTP_SERVER_2 "time.nist.gov"
