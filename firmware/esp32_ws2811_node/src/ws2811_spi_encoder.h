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

// The fixed-GPIO4 production candidate uses the same 3.2 MHz symbols as the
// legacy SPI4 diagnostics, but retains a symmetric 500 us reset-low margin.
static constexpr uint32_t WS2811_FIXED_GPIO4_SPI_RESET_LOW_US = 500;
static constexpr size_t WS2811_FIXED_GPIO4_SPI_GUARD_BYTES = 200;
static constexpr size_t WS2811_FIXED_GPIO4_SPI_MAX_FRAME_BYTES =
    2U * WS2811_FIXED_GPIO4_SPI_GUARD_BYTES +
    MAX_PIXELS_PER_OUTPUT * WS2811_SPI_BYTES_PER_GROUP;

static_assert(
    static_cast<uint64_t>(WS2811_FIXED_GPIO4_SPI_GUARD_BYTES) * 8U *
            1000000U >=
        static_cast<uint64_t>(WS2811_SPI_CLOCK_HZ) *
            WS2811_FIXED_GPIO4_SPI_RESET_LOW_US,
    "fixed GPIO4 SPI guard must provide at least 500 us reset low");

enum class Ws2811ColorOrder : uint8_t {
  RGB,
  GRB,
};

// Returns zero for an invalid group count.
size_t ws2811SpiFrameSize(uint16_t group_count);

// Returns the fixed-GPIO4 production-candidate frame size, including its
// longer reset-low guards. Returns zero for an invalid group count.
size_t ws2811FixedGpio4SpiFrameSize(uint16_t group_count);

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

bool encodeWs2811FixedGpio4Spi(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len);

// Deterministic full-buffer diagnostic hash. This is not a wire checksum.
uint32_t ws2811EncodedHash(const uint8_t *encoded, size_t encoded_len);

// Verifies that every encoded 12-byte group equals group zero, including
// exact channel order and bit encoding. Intended for uniform static frames.
bool ws2811UniformEncodedGroups(
    const uint8_t *encoded,
    size_t encoded_len,
    uint16_t group_count);

bool ws2811FixedGpio4SpiUniformEncodedGroups(
    const uint8_t *encoded,
    size_t encoded_len,
    uint16_t group_count);

}  // namespace light_belt

#endif
