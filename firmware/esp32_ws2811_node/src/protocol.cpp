#include "protocol.h"

namespace light_belt {

namespace {

uint16_t readU16(const uint8_t *data) {
  return (static_cast<uint16_t>(data[0]) << 8) | data[1];
}

uint32_t readU32(const uint8_t *data) {
  return (static_cast<uint32_t>(data[0]) << 24) |
         (static_cast<uint32_t>(data[1]) << 16) |
         (static_cast<uint32_t>(data[2]) << 8) |
         data[3];
}

}  // namespace

uint32_t crc32Ethernet(const uint8_t *data, size_t len) {
  uint32_t crc = 0xFFFFFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      if ((crc & 1U) != 0) {
        crc = (crc >> 1) ^ 0xEDB88320UL;
      } else {
        crc >>= 1;
      }
    }
  }
  return ~crc;
}

ParseResult parseUdpV2Frame(
    const uint8_t *data,
    size_t len,
    uint8_t local_node_id,
    uint16_t configured_pixel_count,
    UdpV2Frame *out) {
  if (len < UDP_V2_HEADER_LEN + UDP_V2_CRC_LEN) {
    return ParseResult::TooShort;
  }
  if (readU16(data) != UDP_V2_MAGIC) {
    return ParseResult::BadMagic;
  }
  if (data[2] != UDP_V2_VERSION) {
    return ParseResult::BadVersion;
  }
  if (data[3] != UDP_V2_MESSAGE_FRAME) {
    return ParseResult::BadMessageType;
  }
  if (data[4] != local_node_id && data[4] != BROADCAST_NODE_ID) {
    return ParseResult::WrongNode;
  }
  if ((data[5] & ~UDP_V2_FLAG_KEY_FRAME) != 0) {
    return ParseResult::BadFlags;
  }

  const uint16_t pixel_count = readU16(data + 10);
  const uint16_t payload_len = readU16(data + 12);
  if (pixel_count != configured_pixel_count || payload_len != pixel_count * 3U) {
    return ParseResult::BadLengths;
  }
  if (len != UDP_V2_HEADER_LEN + payload_len + UDP_V2_CRC_LEN) {
    return ParseResult::BadLengths;
  }

  const uint32_t expected_crc = readU32(data + len - UDP_V2_CRC_LEN);
  if (crc32Ethernet(data, len - UDP_V2_CRC_LEN) != expected_crc) {
    return ParseResult::BadCrc;
  }

  if (out != nullptr) {
    out->node_id = data[4];
    out->flags = data[5];
    out->sequence = readU32(data + 6);
    out->pixel_count = pixel_count;
    out->payload_len = payload_len;
    out->payload = data + UDP_V2_HEADER_LEN;
  }
  return ParseResult::Ok;
}

}  // namespace light_belt
