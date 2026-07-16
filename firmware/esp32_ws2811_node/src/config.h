#ifndef LIGHT_BELT_ESP32_CONFIG_H
#define LIGHT_BELT_ESP32_CONFIG_H

#include "config.example.h"

#if __has_include("config.local.h")
#define HAS_LOCAL_CONFIG 1
#include "config.local.h"
#else
#define HAS_LOCAL_CONFIG 0
#define WIFI_SSID "PLACEHOLDER_SSID"
#define WIFI_PASSWORD "PLACEHOLDER_PASSWORD"
#endif

#if defined(NODE_ID) || defined(OUTPUT_COUNT)
#error "config.local.h must contain Wi-Fi credentials only; select the node with the PlatformIO environment"
#endif

#ifndef LIGHT_BELT_NODE_CONFIG
#error "Build with esp32-s3-node-1 through esp32-s3-node-13"
#elif LIGHT_BELT_NODE_CONFIG == 1
#include "node_configs/node_1.h"
#elif LIGHT_BELT_NODE_CONFIG == 2
#include "node_configs/node_2.h"
#elif LIGHT_BELT_NODE_CONFIG == 3
#include "node_configs/node_3.h"
#elif LIGHT_BELT_NODE_CONFIG == 4
#include "node_configs/node_4.h"
#elif LIGHT_BELT_NODE_CONFIG == 5
#include "node_configs/node_5.h"
#elif LIGHT_BELT_NODE_CONFIG == 6
#include "node_configs/node_6.h"
#elif LIGHT_BELT_NODE_CONFIG == 7
#include "node_configs/node_7.h"
#elif LIGHT_BELT_NODE_CONFIG == 8
#include "node_configs/node_8.h"
#elif LIGHT_BELT_NODE_CONFIG == 9
#include "node_configs/node_9.h"
#elif LIGHT_BELT_NODE_CONFIG == 10
#include "node_configs/node_10.h"
#elif LIGHT_BELT_NODE_CONFIG == 11
#include "node_configs/node_11.h"
#elif LIGHT_BELT_NODE_CONFIG == 12
#include "node_configs/node_12.h"
#elif LIGHT_BELT_NODE_CONFIG == 13
#include "node_configs/node_13.h"
#else
#error "LIGHT_BELT_NODE_CONFIG must be an integer from 1 through 13"
#endif

#endif
