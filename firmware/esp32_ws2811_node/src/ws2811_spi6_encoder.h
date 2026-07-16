#ifndef LIGHT_BELT_ESP32_WS2811_SPI6_ENCODER_H
#define LIGHT_BELT_ESP32_WS2811_SPI6_ENCODER_H

#include <stddef.h>
#include <stdint.h>

#include "owned_frame.h"
#include "ws2811_spi_encoder.h"

namespace light_belt {

static constexpr uint32_t WS2811_SPI6_CLOCK_HZ = 5000000;
static constexpr size_t WS2811_SPI6_GUARD_BYTES = 32;
static constexpr size_t WS2811_SPI6_BYTES_PER_GROUP = 18;
static constexpr size_t WS2811_SPI6_MAX_FRAME_BYTES =
    2U * WS2811_SPI6_GUARD_BYTES +
    MAX_PIXELS_PER_OUTPUT * WS2811_SPI6_BYTES_PER_GROUP;

// Returns zero for an invalid group count.
size_t ws2811Spi6FrameSize(uint16_t group_count);

// At 5 MHz, 0 -> 100000 and 1 -> 111000. The resulting pulse timings are
// T0H/T0L=200/1000 ns and T1H/T1L=600/600 ns.
bool encodeWs2811Spi6(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len);

}  // namespace light_belt

#endif
