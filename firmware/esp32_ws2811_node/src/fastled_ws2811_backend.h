#ifndef LIGHT_BELT_ESP32_FASTLED_WS2811_BACKEND_H
#define LIGHT_BELT_ESP32_FASTLED_WS2811_BACKEND_H

#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)

#include <FastLED.h>
#include <stdint.h>

#include "owned_frame.h"
#include "spi_ws2811_backend.h"

namespace light_belt {

class FastLedWs2811Backend {
 public:
  bool begin(const OutputDescriptor *outputs, uint8_t output_count);
  SpiRefreshReport refresh(const OwnedNodeFrame &frame);

 private:
  CRGB pixels_[2][MAX_PIXELS_PER_OUTPUT] = {};
  OutputDescriptor outputs_[MAX_OUTPUTS] = {};
  bool initialized_ = false;
};

}  // namespace light_belt

#endif

#endif
