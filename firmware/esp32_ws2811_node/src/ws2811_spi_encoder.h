#ifndef LIGHT_BELT_ESP32_WS2811_SPI_ENCODER_H
#define LIGHT_BELT_ESP32_WS2811_SPI_ENCODER_H

#include <stddef.h>
#include <stdint.h>

#include "owned_frame.h"

namespace light_belt {

static constexpr uint32_t WS2811_SPI_CLOCK_HZ = 3200000;
static constexpr size_t WS2811_SPI_GUARD_BYTES = 32;
static constexpr size_t WS2811_SPI_BYTES_PER_GROUP = 12;
static constexpr size_t WS2811_SPI_MAX_FRAME_BYTES =
    2U * WS2811_SPI_GUARD_BYTES +
    MAX_PIXELS_PER_OUTPUT * WS2811_SPI_BYTES_PER_GROUP;

enum class Ws2811ColorOrder : uint8_t {
  RGB,
  GRB,
};

// Returns zero for an invalid group count.
size_t ws2811SpiFrameSize(uint16_t group_count);

// Encodes one complete strip transaction. Each WS2811 data bit becomes one
// SPI nibble: 0 -> 1000 (0x8), 1 -> 1100 (0xC). No brightness transform is
// performed here.
bool encodeWs2811Spi(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len);

}  // namespace light_belt

#endif
