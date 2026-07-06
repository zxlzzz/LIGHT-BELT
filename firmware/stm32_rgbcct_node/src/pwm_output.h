#ifndef LIGHT_BELT_STM32_PWM_OUTPUT_H
#define LIGHT_BELT_STM32_PWM_OUTPUT_H

#include <Arduino.h>
#include <stdint.h>

#include "protocol.h"

namespace light_belt {

struct RgbCctLevels {
  uint8_t r;
  uint8_t g;
  uint8_t b;
  uint8_t warm_white;
  uint8_t cool_white;
};

class PwmOutput {
 public:
  void begin();
  void setTarget(const RgbCctFrame &frame, uint32_t now_ms);
  void setBlack(uint32_t now_ms);
  void update(uint32_t now_ms);

 private:
  RgbCctLevels current_{};
  RgbCctLevels start_{};
  RgbCctLevels target_{};
  uint32_t fade_start_ms_ = 0;
  uint16_t fade_duration_ms_ = 0;
  void writeLevels(const RgbCctLevels &levels);
};

}  // namespace light_belt

#endif
