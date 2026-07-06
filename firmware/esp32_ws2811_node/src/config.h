#ifndef LIGHT_BELT_ESP32_CONFIG_H
#define LIGHT_BELT_ESP32_CONFIG_H

#include "config.example.h"

#if __has_include("config.local.h")
#define HAS_LOCAL_CONFIG 1
#include "config.local.h"
#else
#define WIFI_SSID "PLACEHOLDER_SSID"
#define WIFI_PASSWORD "PLACEHOLDER_PASSWORD"
#endif

#endif
