#ifndef LIGHT_BELT_ESP32_PROTOCOL_H
#define LIGHT_BELT_ESP32_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

namespace light_belt {

// UDP v3: one complete, self-describing frame for one physical ESP32 node.
static constexpr uint16_t UDP_V3_MAGIC = 0x4C45;
static constexpr uint8_t UDP_V3_VERSION = 0x03;
static constexpr uint8_t UDP_V3_MESSAGE_FRAME = 0x01;
static constexpr uint8_t UDP_V3_MESSAGE_CLOCK_BEACON = 0x02;
static constexpr uint8_t UDP_V3_FLAG_SAFE_STATE = 0x01;
static constexpr uint8_t UDP_V3_FLAG_KEY_FRAME = 0x02;
static constexpr uint8_t UDP_V3_FLAG_SCHEDULED_APPLY = 0x04;
static constexpr uint8_t UDP_V3_ALLOWED_FLAGS =
    UDP_V3_FLAG_SAFE_STATE | UDP_V3_FLAG_KEY_FRAME |
    UDP_V3_FLAG_SCHEDULED_APPLY;
static constexpr size_t UDP_V3_HEADER_LEN = 29;
static constexpr size_t UDP_V3_OUTPUT_DESCRIPTOR_LEN = 6;
static constexpr size_t UDP_V3_CRC_LEN = 4;
// Broadcast clock beacons deliberately contain no node or output field.
static constexpr size_t UDP_V3_CLOCK_BEACON_LEN = 20;
static constexpr uint8_t MAX_OUTPUTS = 3;
static constexpr uint16_t MAX_PIXELS_PER_OUTPUT = 100;
static constexpr size_t UDP_V3_MAX_PACKET_LEN =
    UDP_V3_HEADER_LEN +
    MAX_OUTPUTS * (UDP_V3_OUTPUT_DESCRIPTOR_LEN + MAX_PIXELS_PER_OUTPUT * 3U) +
    UDP_V3_CRC_LEN;

struct OutputDescriptor {
  uint8_t output_id;
  uint8_t gpio;
  uint16_t pixel_count;
};

struct UdpV3OutputView {
  OutputDescriptor descriptor;
  uint16_t payload_len;
  const uint8_t *payload;
};

struct UdpV3Frame {
  uint8_t node_id;
  uint8_t flags;
  uint32_t sequence;
  uint64_t media_timestamp_us;
  // Zero is immediate and must omit SCHEDULED_APPLY; nonzero is scheduled and
  // must carry SCHEDULED_APPLY.
  uint64_t apply_at_us;
  uint8_t output_count;
  uint16_t payload_len;
  UdpV3OutputView outputs[MAX_OUTPUTS];
};

struct UdpV3ClockBeacon {
  uint32_t beacon_sequence;
  uint64_t host_monotonic_us;
};

enum class ParseResult {
  Ok,
  TooShort,
  TooLarge,
  BadMagic,
  BadVersion,
  BadMessageType,
  WrongNode,
  BadFlags,
  BadSchedule,
  BadOutputCount,
  BadLengths,
  UnknownOutput,
  DuplicateOutput,
  IncompleteOutputSet,
  BadCrc,
};

enum class ClockBeaconParseResult {
  Ok,
  BadLength,
  BadMagic,
  BadVersion,
  BadMessageType,
  BadCrc,
};

uint32_t crc32Ethernet(const uint8_t *data, size_t len);

bool validateOutputDescriptors(
    const OutputDescriptor *outputs, uint8_t output_count);

ParseResult parseUdpV3Frame(
    const uint8_t *data,
    size_t len,
    uint8_t local_node_id,
    const OutputDescriptor *configured_outputs,
    uint8_t configured_output_count,
    UdpV3Frame *out);

ClockBeaconParseResult parseUdpV3ClockBeacon(
    const uint8_t *data,
    size_t len,
    UdpV3ClockBeacon *out);

// Strictly newer under uint32 wrap-around semantics. Equal is a duplicate.
bool isNewerSequence(uint32_t candidate, uint32_t previous);

}  // namespace light_belt

#endif
