#ifndef LIGHT_BELT_ESP32_LED_OUTPUT_H
#define LIGHT_BELT_ESP32_LED_OUTPUT_H

#include <Arduino.h>
#include <FastLED.h>
#include <stdint.h>

#include "config.h"
#include "protocol.h"

namespace light_belt {

class LedOutput {
 public:
  void begin();
  void applyFrame(const UdpV2Frame &frame);
  void showBlack();

 private:
  CRGB pixels_[PIXEL_COUNT];
};

}  // namespace light_belt

#endif
