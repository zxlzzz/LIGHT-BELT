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

uint64_t readU64(const uint8_t *data) {
  return (static_cast<uint64_t>(readU32(data)) << 32) | readU32(data + 4);
}

const OutputDescriptor *findOutput(
    const OutputDescriptor *outputs, uint8_t output_count, uint8_t output_id) {
  for (uint8_t index = 0; index < output_count; ++index) {
    if (outputs[index].output_id == output_id) {
      return &outputs[index];
    }
  }
  return nullptr;
}

bool isSupportedGpio(uint8_t gpio) {
  return gpio == 4 || gpio == 5 || gpio == 6;
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

bool validateOutputDescriptors(
    const OutputDescriptor *outputs, uint8_t output_count) {
  if (outputs == nullptr || output_count == 0 || output_count > MAX_OUTPUTS) {
    return false;
  }
  for (uint8_t index = 0; index < output_count; ++index) {
    const OutputDescriptor &output = outputs[index];
    if (output.output_id == 0 || !isSupportedGpio(output.gpio) ||
        output.pixel_count == 0 || output.pixel_count > MAX_PIXELS_PER_OUTPUT) {
      return false;
    }
    for (uint8_t previous = 0; previous < index; ++previous) {
      if (outputs[previous].output_id == output.output_id ||
          outputs[previous].gpio == output.gpio) {
        return false;
      }
    }
  }
  return true;
}

ParseResult parseUdpV3Frame(
    const uint8_t *data,
    size_t len,
    uint8_t local_node_id,
    const OutputDescriptor *configured_outputs,
    uint8_t configured_output_count,
    UdpV3Frame *out) {
  if (data == nullptr || len < UDP_V3_HEADER_LEN + UDP_V3_CRC_LEN) {
    return ParseResult::TooShort;
  }
  if (len > UDP_V3_MAX_PACKET_LEN) {
    return ParseResult::TooLarge;
  }
  if (!validateOutputDescriptors(configured_outputs, configured_output_count)) {
    return ParseResult::BadOutputCount;
  }
  if (readU16(data) != UDP_V3_MAGIC) {
    return ParseResult::BadMagic;
  }
  if (data[2] != UDP_V3_VERSION) {
    return ParseResult::BadVersion;
  }
  if (data[3] != UDP_V3_MESSAGE_FRAME) {
    return ParseResult::BadMessageType;
  }
  if (data[4] != local_node_id) {
    return ParseResult::WrongNode;
  }
  if ((data[5] & ~UDP_V3_ALLOWED_FLAGS) != 0) {
    return ParseResult::BadFlags;
  }

  const uint8_t output_count = data[26];
  const uint16_t payload_len = readU16(data + 27);
  if (output_count == 0 || output_count > MAX_OUTPUTS) {
    return ParseResult::BadOutputCount;
  }
  if (len != UDP_V3_HEADER_LEN + payload_len + UDP_V3_CRC_LEN) {
    return ParseResult::BadLengths;
  }
  const uint32_t expected_crc = readU32(data + len - UDP_V3_CRC_LEN);
  if (crc32Ethernet(data, len - UDP_V3_CRC_LEN) != expected_crc) {
    return ParseResult::BadCrc;
  }

  const uint64_t apply_at_us = readU64(data + 18);
  const bool scheduled =
      (data[5] & UDP_V3_FLAG_SCHEDULED_APPLY) != 0;
  if (scheduled != (apply_at_us != 0)) {
    return ParseResult::BadSchedule;
  }

  UdpV3Frame parsed{};
  parsed.node_id = data[4];
  parsed.flags = data[5];
  parsed.sequence = readU32(data + 6);
  parsed.media_timestamp_us = readU64(data + 10);
  parsed.apply_at_us = apply_at_us;
  parsed.output_count = output_count;
  parsed.payload_len = payload_len;

  size_t cursor = UDP_V3_HEADER_LEN;
  const size_t payload_end = cursor + payload_len;
  for (uint8_t output_index = 0; output_index < output_count; ++output_index) {
    if (cursor + UDP_V3_OUTPUT_DESCRIPTOR_LEN > payload_end) {
      return ParseResult::BadLengths;
    }
    const uint8_t output_id = data[cursor];
    const uint8_t gpio = data[cursor + 1];
    const uint16_t pixel_count = readU16(data + cursor + 2);
    const uint16_t output_len = readU16(data + cursor + 4);
    cursor += UDP_V3_OUTPUT_DESCRIPTOR_LEN;
    if (output_id == 0 || pixel_count == 0 || pixel_count > MAX_PIXELS_PER_OUTPUT ||
        output_len != pixel_count * 3U || cursor + output_len > payload_end) {
      return ParseResult::BadLengths;
    }
    for (uint8_t previous = 0; previous < output_index; ++previous) {
      if (parsed.outputs[previous].descriptor.output_id == output_id ||
          parsed.outputs[previous].descriptor.gpio == gpio) {
        return ParseResult::DuplicateOutput;
      }
    }
    const OutputDescriptor *configured = findOutput(
        configured_outputs, configured_output_count, output_id);
    if (configured == nullptr || configured->gpio != gpio ||
        configured->pixel_count != pixel_count) {
      return ParseResult::UnknownOutput;
    }
    parsed.outputs[output_index] = {
        *configured,
        output_len,
        data + cursor,
    };
    cursor += output_len;
  }
  if (cursor != payload_end) {
    return ParseResult::BadLengths;
  }
  if (output_count != configured_output_count) {
    return ParseResult::IncompleteOutputSet;
  }
  for (uint8_t index = 0; index < configured_output_count; ++index) {
    bool found = false;
    for (uint8_t received = 0; received < output_count; ++received) {
      if (parsed.outputs[received].descriptor.output_id == configured_outputs[index].output_id) {
        found = true;
        break;
      }
    }
    if (!found) {
      return ParseResult::IncompleteOutputSet;
    }
  }
  if (out != nullptr) {
    *out = parsed;
  }
  return ParseResult::Ok;
}

ClockBeaconParseResult parseUdpV3ClockBeacon(
    const uint8_t *data,
    size_t len,
    UdpV3ClockBeacon *out) {
  if (data == nullptr || len != UDP_V3_CLOCK_BEACON_LEN) {
    return ClockBeaconParseResult::BadLength;
  }
  if (readU16(data) != UDP_V3_MAGIC) {
    return ClockBeaconParseResult::BadMagic;
  }
  if (data[2] != UDP_V3_VERSION) {
    return ClockBeaconParseResult::BadVersion;
  }
  if (data[3] != UDP_V3_MESSAGE_CLOCK_BEACON) {
    return ClockBeaconParseResult::BadMessageType;
  }
  const uint32_t expected_crc =
      readU32(data + UDP_V3_CLOCK_BEACON_LEN - UDP_V3_CRC_LEN);
  if (crc32Ethernet(
          data, UDP_V3_CLOCK_BEACON_LEN - UDP_V3_CRC_LEN) != expected_crc) {
    return ClockBeaconParseResult::BadCrc;
  }

  if (out != nullptr) {
    out->beacon_sequence = readU32(data + 4);
    out->host_monotonic_us = readU64(data + 8);
  }
  return ClockBeaconParseResult::Ok;
}

bool isNewerSequence(uint32_t candidate, uint32_t previous) {
  return candidate != previous &&
         static_cast<int32_t>(candidate - previous) > 0;
}

}  // namespace light_belt
