#ifndef LIGHT_BELT_ESP32_WS2811_RMT_ENCODER_H
#define LIGHT_BELT_ESP32_WS2811_RMT_ENCODER_H

#include <stddef.h>
#include <stdint.h>

#include "ws2811_spi_encoder.h"

namespace light_belt {

static constexpr uint8_t WS2811_RMT_CLOCK_DIVIDER = 5;
static constexpr uint32_t WS2811_RMT_TICK_HZ = 16000000;
static constexpr uint16_t WS2811_RMT_ZERO_HIGH_TICKS = 5;
static constexpr uint16_t WS2811_RMT_ZERO_LOW_TICKS = 15;
static constexpr uint16_t WS2811_RMT_ONE_HIGH_TICKS = 10;
static constexpr uint16_t WS2811_RMT_ONE_LOW_TICKS = 10;
static constexpr size_t WS2811_RMT_PULSES_PER_GROUP = 24;
static constexpr size_t WS2811_RMT_MAX_PULSES =
    MAX_PIXELS_PER_OUTPUT * WS2811_RMT_PULSES_PER_GROUP;

// One WS2811 bit. The backend emits high_ticks at level 1 followed by
// low_ticks at level 0, then holds the output low for the reset interval.
struct Ws2811RmtPulse {
  uint16_t high_ticks;
  uint16_t low_ticks;
};

// Returns zero for an invalid group count. The reset interval is not included.
size_t ws2811RmtPulseCount(uint16_t group_count);

// Encodes channel bytes MSB first without applying brightness or adding reset.
bool encodeWs2811Rmt(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    Ws2811RmtPulse *destination,
    size_t destination_capacity,
    size_t *encoded_count);

}  // namespace light_belt

#endif
