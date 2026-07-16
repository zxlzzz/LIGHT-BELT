#include "ws2811_rmt_encoder.h"

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

Ws2811RmtPulse encodedPulse(bool one) {
  if (one) {
    return {WS2811_RMT_ONE_HIGH_TICKS, WS2811_RMT_ONE_LOW_TICKS};
  }
  return {WS2811_RMT_ZERO_HIGH_TICKS, WS2811_RMT_ZERO_LOW_TICKS};
}

}  // namespace

size_t ws2811RmtPulseCount(uint16_t group_count) {
  if (group_count == 0 || group_count > MAX_PIXELS_PER_OUTPUT) {
    return 0;
  }
  return static_cast<size_t>(group_count) * WS2811_RMT_PULSES_PER_GROUP;
}

bool encodeWs2811Rmt(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    Ws2811RmtPulse *destination,
    size_t destination_capacity,
    size_t *encoded_count) {
  const size_t required = ws2811RmtPulseCount(group_count);
  if (pixels == nullptr || destination == nullptr || encoded_count == nullptr ||
      required == 0 || destination_capacity < required ||
      !validColorOrder(color_order)) {
    return false;
  }

  size_t cursor = 0;
  for (uint16_t group = 0; group < group_count; ++group) {
    for (uint8_t channel = 0; channel < 3; ++channel) {
      const uint8_t value = channelValue(pixels[group], color_order, channel);
      for (uint8_t bit_index = 0; bit_index < 8; ++bit_index) {
        const uint8_t source_bit = static_cast<uint8_t>(7U - bit_index);
        destination[cursor++] =
            encodedPulse((value & (1U << source_bit)) != 0);
      }
    }
  }

  *encoded_count = required;
  return true;
}

}  // namespace light_belt
