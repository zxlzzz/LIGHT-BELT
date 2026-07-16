#include "ws2811_spi3_encoder.h"

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

void encodeByte(uint8_t source, uint8_t *destination) {
  uint32_t packed = 0;
  for (uint8_t bit_index = 0; bit_index < 8; ++bit_index) {
    const uint8_t source_bit = static_cast<uint8_t>(7U - bit_index);
    const uint8_t symbol =
        (source & (1U << source_bit)) != 0 ? 0x06 : 0x04;
    packed = (packed << 3) | symbol;
  }
  destination[0] = static_cast<uint8_t>(packed >> 16);
  destination[1] = static_cast<uint8_t>(packed >> 8);
  destination[2] = static_cast<uint8_t>(packed);
}

}  // namespace

size_t ws2811Spi3FrameSize(uint16_t group_count) {
  if (group_count == 0 || group_count > MAX_PIXELS_PER_OUTPUT) {
    return 0;
  }
  return 2U * WS2811_SPI3_GUARD_BYTES +
         static_cast<size_t>(group_count) * WS2811_SPI3_BYTES_PER_GROUP;
}

bool encodeWs2811Spi3(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len) {
  const size_t required = ws2811Spi3FrameSize(group_count);
  if (pixels == nullptr || destination == nullptr || encoded_len == nullptr ||
      required == 0 || destination_capacity < required ||
      !validColorOrder(color_order)) {
    return false;
  }

  memset(destination, 0, required);
  size_t cursor = WS2811_SPI3_GUARD_BYTES;
  for (uint16_t pixel = 0; pixel < group_count; ++pixel) {
    for (uint8_t channel = 0; channel < 3; ++channel) {
      encodeByte(
          channelValue(pixels[pixel], color_order, channel),
          destination + cursor);
      cursor += 3;
    }
  }
  *encoded_len = required;
  return true;
}

}  // namespace light_belt
