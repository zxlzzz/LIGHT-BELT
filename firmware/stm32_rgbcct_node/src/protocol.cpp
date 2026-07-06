#include "protocol.h"

#include "config.h"

namespace light_belt {

uint16_t crc16CcittFalse(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit) {
      if ((crc & 0x8000) != 0) {
        crc = static_cast<uint16_t>((crc << 1) ^ 0x1021);
      } else {
        crc = static_cast<uint16_t>(crc << 1);
      }
    }
  }
  return crc;
}

ParseResult parseRs485V2Frame(
    const uint8_t *data,
    size_t len,
    uint8_t local_node_id,
    uint8_t broadcast_node_id,
    RgbCctFrame *out) {
  if (len != RS485_V2_FRAME_LEN) {
    return ParseResult::WrongLength;
  }
  if (data[0] != RS485_V2_SYNC_0 || data[1] != RS485_V2_SYNC_1) {
    return ParseResult::BadSync;
  }
  if (data[2] != RS485_V2_VERSION) {
    return ParseResult::BadVersion;
  }
  if (data[3] != RS485_V2_COMMAND_SET_RGB_CCT) {
    return ParseResult::BadCommand;
  }
  if (data[4] != local_node_id && data[4] != broadcast_node_id) {
    return ParseResult::WrongNode;
  }
  if ((data[13] & ~RS485_V2_FLAG_APPLY) != 0) {
    return ParseResult::BadFlags;
  }
  const uint16_t expected_crc =
      (static_cast<uint16_t>(data[14]) << 8) | data[15];
  if (crc16CcittFalse(data, RS485_V2_FRAME_LEN - 2) != expected_crc) {
    return ParseResult::BadCrc;
  }

  if (out != nullptr) {
    out->node_id = data[4];
    out->sequence = data[5];
    out->r = data[6];
    out->g = data[7];
    out->b = data[8];
    out->warm_white = data[9];
    out->cool_white = data[10];
    out->fade_ms = (static_cast<uint16_t>(data[11]) << 8) | data[12];
    out->flags = data[13];
  }
  return ParseResult::Ok;
}

void Rs485FrameReader::reset() {
  used_ = 0;
  last_byte_ms_ = 0;
}

bool Rs485FrameReader::push(uint8_t byte, uint32_t now_ms, RgbCctFrame *out) {
  if (used_ > 0 && now_ms - last_byte_ms_ > BYTE_TIMEOUT_MS) {
    reset();
  }
  last_byte_ms_ = now_ms;

  if (used_ == 0 && byte != RS485_V2_SYNC_0) {
    return false;
  }
  if (used_ == 1 && byte != RS485_V2_SYNC_1) {
    reset();
    if (byte == RS485_V2_SYNC_0) {
      buffer_[used_++] = byte;
    }
    return false;
  }

  buffer_[used_++] = byte;
  if (used_ < RS485_V2_FRAME_LEN) {
    return false;
  }

  const ParseResult result = parseRs485V2Frame(
      buffer_, RS485_V2_FRAME_LEN, NODE_ID, BROADCAST_NODE_ID, out);
  reset();
  return result == ParseResult::Ok;
}

}  // namespace light_belt
