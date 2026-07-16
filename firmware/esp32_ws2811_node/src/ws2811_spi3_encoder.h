#ifndef LIGHT_BELT_ESP32_WS2811_SPI3_ENCODER_H
#define LIGHT_BELT_ESP32_WS2811_SPI3_ENCODER_H

#include <stddef.h>
#include <stdint.h>

#include "owned_frame.h"
#include "ws2811_spi_encoder.h"

namespace light_belt {

static constexpr uint32_t WS2811_SPI3_CLOCK_HZ = 2400000;
static constexpr size_t WS2811_SPI3_GUARD_BYTES = 32;
static constexpr size_t WS2811_SPI3_BYTES_PER_GROUP = 9;
static constexpr size_t WS2811_SPI3_MAX_FRAME_BYTES =
    2U * WS2811_SPI3_GUARD_BYTES +
    MAX_PIXELS_PER_OUTPUT * WS2811_SPI3_BYTES_PER_GROUP;

// Returns zero for an invalid group count.
size_t ws2811Spi3FrameSize(uint16_t group_count);

// Encodes each WS2811 data bit into three continuous MSB-first SPI bits:
// 0 -> 100, 1 -> 110. No brightness transform is performed here.
bool encodeWs2811Spi3(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len);

}  // namespace light_belt

#endif
