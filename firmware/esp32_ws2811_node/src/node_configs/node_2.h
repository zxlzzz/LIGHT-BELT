#ifndef LIGHT_BELT_ESP32_NODE_2_H
#define LIGHT_BELT_ESP32_NODE_2_H

#define NODE_ID 2
#define NODE_IPV4_D 202
#if defined(LIGHT_BELT_NODE2_GPIO4_STRIP42_DIAGNOSTIC) && \
    defined(LIGHT_BELT_NODE2_LEGACY_MULTI_OUTPUT)
#error "strip 42 isolation and legacy multi-output modes are mutually exclusive"
#endif

#if defined(LIGHT_BELT_NODE2_GPIO4_STRIP42_DIAGNOSTIC)
#define OUTPUT_COUNT 1
#define OUTPUT_0_ID 1
#define OUTPUT_0_GPIO 4
#define OUTPUT_0_PIXELS 20
#elif defined(LIGHT_BELT_NODE2_LEGACY_MULTI_OUTPUT)
#define OUTPUT_COUNT 3
#define OUTPUT_0_ID 1
#define OUTPUT_0_GPIO 4
#define OUTPUT_0_PIXELS 10
#define OUTPUT_1_ID 2
#define OUTPUT_1_GPIO 5
#define OUTPUT_1_PIXELS 20
// Keep output 3 configured while strip_43 is physically disconnected so the
// node continues to accept the host's complete three-output UDP v3 frame.
#define OUTPUT_2_ID 3
#define OUTPUT_2_GPIO 6
#define OUTPUT_2_PIXELS 20
#else
#define OUTPUT_COUNT 1
#define OUTPUT_0_ID 1
#define OUTPUT_0_GPIO 4
#define OUTPUT_0_PIXELS 10
#endif

#endif
