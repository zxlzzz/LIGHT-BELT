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

size_t frameSizeWithGuard(uint16_t group_count, size_t guard_bytes) {
  if (group_count == 0 || group_count > MAX_PIXELS_PER_OUTPUT) {
    return 0;
  }
  return 2U * guard_bytes +
         static_cast<size_t>(group_count) * WS2811_SPI_BYTES_PER_GROUP;
}

bool encodeWithGuard(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    size_t guard_bytes,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len) {
  const size_t required = frameSizeWithGuard(group_count, guard_bytes);
  if (pixels == nullptr || destination == nullptr || encoded_len == nullptr ||
      required == 0 || destination_capacity < required ||
      !validColorOrder(color_order)) {
    return false;
  }

  memset(destination, 0, required);
  size_t cursor = guard_bytes;
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
  *encoded_len = required;
  return true;
}

bool uniformEncodedGroupsWithGuard(
    const uint8_t *encoded,
    size_t encoded_len,
    uint16_t group_count,
    size_t guard_bytes) {
  if (encoded == nullptr ||
      encoded_len != frameSizeWithGuard(group_count, guard_bytes)) {
    return false;
  }
  const uint8_t *first = encoded + guard_bytes;
  for (uint16_t group = 1; group < group_count; ++group) {
    const uint8_t *candidate =
        first + static_cast<size_t>(group) * WS2811_SPI_BYTES_PER_GROUP;
    if (memcmp(first, candidate, WS2811_SPI_BYTES_PER_GROUP) != 0) {
      return false;
    }
  }
  return true;
}

}  // namespace

size_t ws2811SpiFrameSize(uint16_t group_count) {
  return frameSizeWithGuard(group_count, WS2811_SPI_GUARD_BYTES);
}

size_t ws2811FixedGpio4SpiFrameSize(uint16_t group_count) {
  return frameSizeWithGuard(
      group_count, WS2811_FIXED_GPIO4_SPI_GUARD_BYTES);
}

bool encodeWs2811Spi(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len) {
  return encodeWithGuard(
      pixels, group_count, color_order, WS2811_SPI_GUARD_BYTES, destination,
      destination_capacity, encoded_len);
}

bool encodeWs2811FixedGpio4Spi(
    const RgbPixel *pixels,
    uint16_t group_count,
    Ws2811ColorOrder color_order,
    uint8_t *destination,
    size_t destination_capacity,
    size_t *encoded_len) {
  return encodeWithGuard(
      pixels, group_count, color_order,
      WS2811_FIXED_GPIO4_SPI_GUARD_BYTES, destination,
      destination_capacity, encoded_len);
}

uint32_t ws2811EncodedHash(const uint8_t *encoded, size_t encoded_len) {
  if (encoded == nullptr || encoded_len == 0) {
    return 0;
  }
  uint32_t hash = 2166136261U;
  for (size_t index = 0; index < encoded_len; ++index) {
    hash ^= encoded[index];
    hash *= 16777619U;
  }
  return hash;
}

bool ws2811UniformEncodedGroups(
    const uint8_t *encoded,
    size_t encoded_len,
    uint16_t group_count) {
  return uniformEncodedGroupsWithGuard(
      encoded, encoded_len, group_count, WS2811_SPI_GUARD_BYTES);
}

bool ws2811FixedGpio4SpiUniformEncodedGroups(
    const uint8_t *encoded,
    size_t encoded_len,
    uint16_t group_count) {
  return uniformEncodedGroupsWithGuard(
      encoded, encoded_len, group_count,
      WS2811_FIXED_GPIO4_SPI_GUARD_BYTES);
}

}  // namespace light_belt
