#include "ws2811_spi_encoder.h"

#include <string.h>

namespace light_belt {

namespace {

uint8_t encodedNibble(bool one) { return one ? 0x0C : 0x08; }

void encodeByte(uint8_t source, uint8_t *destination) {
  for (uint8_t pair = 0; pair < 4; ++pair) {
    const uint8_t high_bit = static_cast<uint8_t>(7U - pair * 2U);
    const uint8_t low_bit = static_cast<uint8_t>(high_bit - 1U);
    destination[pair] = static_cast<uint8_t>(
        (encodedNibble((source & (1U << high_bit)) != 0) << 4) |
        encodedNibble((source & (1U << low_bit)) != 0));
  }
}

bool validColorOrder(Ws2811ColorOrder color_order) {
  return color_order == Ws2811ColorOrder::RGB ||
         color_order == Ws2811ColorOrder::GRB;
}

}  // namespace

size_t ws2811SpiFrameSize(uint16_t group_count) {
  if (group_count == 0 || group_count > MAX_PIXELS_PER_OUTPUT) {
    return 0;
  }
  return 2U * WS2811_SPI_GUARD_BYTES +
         static_cast<size_t>(group_count) * WS2811_SPI_BYTES_PER_GROUP;
}

bool encodeWs2811Spi(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len) {
  const size_t required = ws2811SpiFrameSize(group_count);
  if (pixels == nullptr || destination == nullptr || encoded_len == nullptr ||
      required == 0 || destination_capacity < required ||
      !validColorOrder(color_order)) {
    return false;
  }

  memset(destination, 0, required);
  size_t cursor = WS2811_SPI_GUARD_BYTES;
  for (uint16_t pixel = 0; pixel < group_count; ++pixel) {
    const uint8_t channels_rgb[] = {
        pixels[pixel].r,
        pixels[pixel].g,
        pixels[pixel].b,
    };
    const uint8_t channels_grb[] = {
        pixels[pixel].g,
        pixels[pixel].r,
        pixels[pixel].b,
    };
    const uint8_t *channels =
        color_order == Ws2811ColorOrder::RGB ? channels_rgb : channels_grb;
    for (uint8_t channel = 0; channel < 3; ++channel) {
      encodeByte(channels[channel], destination + cursor);
      cursor += 4;
    }
  }
  // The pre-filled zero tail is the low reset/guard interval.
  *encoded_len = required;
  return true;
}

}  // namespace light_belt
