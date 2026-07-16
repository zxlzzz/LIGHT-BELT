#include "ws2811_parallel_spi_encoder.h"

#include <string.h>

namespace light_belt {

namespace {

bool validColorOrder(Ws2811ColorOrder color_order) {
  return color_order == Ws2811ColorOrder::RGB ||
         color_order == Ws2811ColorOrder::GRB;
}

uint8_t channelValue(
    const RgbPixel &pixel,
    Ws2811ColorOrder color_order,
    uint8_t channel) {
  if (channel == 2) {
    return pixel.b;
  }
  if (color_order == Ws2811ColorOrder::RGB) {
    return channel == 0 ? pixel.r : pixel.g;
  }
  return channel == 0 ? pixel.g : pixel.r;
}

bool validateLanes(
    const Ws2811ParallelSpiLane *lanes,
    uint8_t lane_count,
    uint16_t *max_group_count) {
  if (lanes == nullptr || max_group_count == nullptr || lane_count == 0 ||
      lane_count > WS2811_PARALLEL_SPI_MAX_LANES) {
    return false;
  }

  uint16_t longest = 0;
  for (uint8_t lane = 0; lane < lane_count; ++lane) {
    if (lanes[lane].pixels == nullptr || lanes[lane].group_count == 0 ||
        lanes[lane].group_count > MAX_PIXELS_PER_OUTPUT) {
      return false;
    }
    if (lanes[lane].group_count > longest) {
      longest = lanes[lane].group_count;
    }
  }
  *max_group_count = longest;
  return true;
}

}  // namespace

size_t ws2811ParallelSpiFrameSize(
    const Ws2811ParallelSpiLane *lanes, uint8_t lane_count) {
  uint16_t max_group_count = 0;
  if (!validateLanes(lanes, lane_count, &max_group_count)) {
    return 0;
  }
  return 2U * WS2811_PARALLEL_SPI_GUARD_BYTES +
         static_cast<size_t>(max_group_count) *
             WS2811_PARALLEL_SPI_BYTES_PER_GROUP;
}

bool encodeWs2811ParallelSpi(
    const Ws2811ParallelSpiLane *lanes,
    uint8_t lane_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len) {
  uint16_t max_group_count = 0;
  if (!validateLanes(lanes, lane_count, &max_group_count) ||
      !validColorOrder(color_order)) {
    return false;
  }

  const size_t required =
      2U * WS2811_PARALLEL_SPI_GUARD_BYTES +
      static_cast<size_t>(max_group_count) *
          WS2811_PARALLEL_SPI_BYTES_PER_GROUP;
  if (destination == nullptr || encoded_len == nullptr ||
      destination_capacity < required) {
    return false;
  }

  memset(destination, 0, required);
  size_t cursor = WS2811_PARALLEL_SPI_GUARD_BYTES;
  const uint8_t active_lane_mask =
      static_cast<uint8_t>((1U << lane_count) - 1U);

  for (uint16_t group = 0; group < max_group_count; ++group) {
    for (uint8_t channel = 0; channel < 3; ++channel) {
      for (uint8_t bit_index = 0; bit_index < 8; ++bit_index) {
        const uint8_t source_bit = static_cast<uint8_t>(7U - bit_index);
        uint8_t one_lane_mask = 0;
        for (uint8_t lane = 0; lane < lane_count; ++lane) {
          if (group >= lanes[lane].group_count) {
            continue;
          }
          const uint8_t value =
              channelValue(lanes[lane].pixels[group], color_order, channel);
          if ((value & (1U << source_bit)) != 0) {
            one_lane_mask =
                static_cast<uint8_t>(one_lane_mask | (1U << lane));
          }
        }

        destination[cursor++] = static_cast<uint8_t>(
            (active_lane_mask << 4) | one_lane_mask);
        destination[cursor++] = 0;
      }
    }
  }

  *encoded_len = required;
  return true;
}

}  // namespace light_belt
