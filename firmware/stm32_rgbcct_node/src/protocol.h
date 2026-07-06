#ifndef LIGHT_BELT_STM32_PROTOCOL_H
#define LIGHT_BELT_STM32_PROTOCOL_H

#include <Arduino.h>
#include <stddef.h>
#include <stdint.h>

namespace light_belt {

static constexpr size_t RS485_V2_FRAME_LEN = 16;
static constexpr uint8_t RS485_V2_SYNC_0 = 0xA5;
static constexpr uint8_t RS485_V2_SYNC_1 = 0x5A;
static constexpr uint8_t RS485_V2_VERSION = 0x02;
static constexpr uint8_t RS485_V2_COMMAND_SET_RGB_CCT = 0x01;
static constexpr uint8_t RS485_V2_FLAG_APPLY = 0x01;

struct RgbCctFrame {
  uint8_t node_id;
  uint8_t sequence;
  uint8_t r;
  uint8_t g;
  uint8_t b;
  uint8_t warm_white;
  uint8_t cool_white;
  uint16_t fade_ms;
  uint8_t flags;
};

enum class ParseResult {
  Ok,
  WrongLength,
  BadSync,
  BadVersion,
  BadCommand,
  WrongNode,
  BadFlags,
  BadCrc,
};

uint16_t crc16CcittFalse(const uint8_t *data, size_t len);
ParseResult parseRs485V2Frame(
    const uint8_t *data,
    size_t len,
    uint8_t local_node_id,
    uint8_t broadcast_node_id,
    RgbCctFrame *out);

class Rs485FrameReader {
 public:
  bool push(uint8_t byte, uint32_t now_ms, RgbCctFrame *out);
  void reset();

 private:
  uint8_t buffer_[RS485_V2_FRAME_LEN] = {};
  size_t used_ = 0;
  uint32_t last_byte_ms_ = 0;
};

}  // namespace light_belt

#endif
