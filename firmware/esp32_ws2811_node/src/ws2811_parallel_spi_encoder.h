#ifndef LIGHT_BELT_ESP32_WS2811_PARALLEL_SPI_ENCODER_H
#define LIGHT_BELT_ESP32_WS2811_PARALLEL_SPI_ENCODER_H

#include <stddef.h>
#include <stdint.h>

#include "owned_frame.h"
#include "ws2811_spi_encoder.h"

namespace light_belt {

static constexpr uint32_t WS2811_PARALLEL_SPI_CLOCK_HZ = 3200000;
static constexpr uint8_t WS2811_PARALLEL_SPI_MAX_LANES = 3;
static constexpr size_t WS2811_PARALLEL_SPI_GUARD_BYTES = 640;
static constexpr size_t WS2811_PARALLEL_SPI_BYTES_PER_GROUP = 48;
static constexpr size_t WS2811_PARALLEL_SPI_MAX_FRAME_BYTES =
    2U * WS2811_PARALLEL_SPI_GUARD_BYTES +
    MAX_PIXELS_PER_OUTPUT * WS2811_PARALLEL_SPI_BYTES_PER_GROUP;

struct Ws2811ParallelSpiLane {
  const RgbPixel *pixels;
  uint16_t group_count;
};

// Returns zero when the lane set or any group count is invalid.
size_t ws2811ParallelSpiFrameSize(
    const Ws2811ParallelSpiLane *lanes, uint8_t lane_count);

// Encodes DATA0..DATA2 into bits 0..2 of each QIO nibble. DATA3 remains low.
// Each WS2811 bit is emitted as four slots: active, one-bits, low, low.
bool encodeWs2811ParallelSpi(
    const Ws2811ParallelSpiLane *lanes,
    uint8_t lane_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len);

}  // namespace light_belt

#endif
