#ifndef LIGHT_BELT_ESP32_PROTOCOL_H
#define LIGHT_BELT_ESP32_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

namespace light_belt {

static constexpr uint16_t UDP_V2_MAGIC = 0x4C45;
static constexpr uint8_t UDP_V2_VERSION = 0x02;
static constexpr uint8_t UDP_V2_MESSAGE_FRAME = 0x01;
static constexpr uint8_t UDP_V2_FLAG_KEY_FRAME = 0x02;
static constexpr size_t UDP_V2_HEADER_LEN = 14;
static constexpr size_t UDP_V2_CRC_LEN = 4;
static constexpr uint8_t BROADCAST_NODE_ID = 0xFF;

struct UdpV2Frame {
  uint8_t node_id;
  uint8_t flags;
  uint32_t sequence;
  uint16_t pixel_count;
  uint16_t payload_len;
  const uint8_t *payload;
};

enum class ParseResult {
  Ok,
  TooShort,
  BadMagic,
  BadVersion,
  BadMessageType,
  WrongNode,
  BadFlags,
  BadLengths,
  BadCrc,
};

uint32_t crc32Ethernet(const uint8_t *data, size_t len);
ParseResult parseUdpV2Frame(
    const uint8_t *data,
    size_t len,
    uint8_t local_node_id,
    uint16_t configured_pixel_count,
    UdpV2Frame *out);

}  // namespace light_belt

#endif
