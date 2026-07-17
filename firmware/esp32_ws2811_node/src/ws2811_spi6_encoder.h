#ifndef LIGHT_BELT_ESP32_WS2811_SPI6_ENCODER_H
#define LIGHT_BELT_ESP32_WS2811_SPI6_ENCODER_H

#include <stddef.h>
#include <stdint.h>

#include "owned_frame.h"
#include "ws2811_spi_encoder.h"

namespace light_belt {

static constexpr uint32_t WS2811_SPI6_CLOCK_HZ = 5000000;
static constexpr uint32_t WS2811_SPI6_RESET_LOW_US = 500;
// 313 bytes at 5 MHz hold the line low for 500.8 us. Symmetric reset guards
// make a retry safe even if the preceding transaction ended partially, while
// transaction completion remains the visible-latch boundary.
static constexpr size_t WS2811_SPI6_PRE_GUARD_BYTES = 313;
static constexpr size_t WS2811_SPI6_POST_GUARD_BYTES = 313;
static constexpr size_t WS2811_SPI6_BYTES_PER_GROUP = 18;
static constexpr size_t WS2811_SPI6_MAX_FRAME_BYTES =
    WS2811_SPI6_PRE_GUARD_BYTES + WS2811_SPI6_POST_GUARD_BYTES +
    MAX_PIXELS_PER_OUTPUT * WS2811_SPI6_BYTES_PER_GROUP;

static_assert(
    static_cast<uint64_t>(WS2811_SPI6_PRE_GUARD_BYTES) * 8U * 1000000U >=
        static_cast<uint64_t>(WS2811_SPI6_CLOCK_HZ) *
            WS2811_SPI6_RESET_LOW_US,
    "SPI6 pre guard must provide at least 500 us reset low");
static_assert(
    static_cast<uint64_t>(WS2811_SPI6_POST_GUARD_BYTES) * 8U * 1000000U >=
        static_cast<uint64_t>(WS2811_SPI6_CLOCK_HZ) *
            WS2811_SPI6_RESET_LOW_US,
    "SPI6 post guard must provide at least 500 us reset low");

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

// Verifies that every encoded 18-byte group equals group zero. Intended for
// uniform-frame diagnostics; pre/post guards are included in length checks.
bool ws2811Spi6UniformEncodedGroups(
    const uint8_t *encoded,
    size_t encoded_len,
    uint16_t group_count);

}  // namespace light_belt

#endif
