#ifndef LIGHT_BELT_ESP32_FASTLED_WS2811_BACKEND_H
#define LIGHT_BELT_ESP32_FASTLED_WS2811_BACKEND_H

#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC) || \
    defined(LIGHT_BELT_FASTLED_GPIO4_IMMEDIATE_AB)

#include <FastLED.h>
#include <stdint.h>

#include "owned_frame.h"
#include "spi_ws2811_backend.h"

namespace light_belt {

class FastLedWs2811Backend {
 public:
  bool begin(const OutputDescriptor *outputs, uint8_t output_count);
  SpiRefreshReport prepare(const OwnedNodeFrame &frame);
  SpiRefreshReport transmitPrepared();
  void cancelPrepared();
  bool hasPreparedFrame() const;
  bool supportsScheduledApply() const;
  uint32_t preparedWireTimeUs() const;
  SpiRefreshReport refresh(const OwnedNodeFrame &frame);

 private:
#if defined(LIGHT_BELT_FASTLED_GPIO4_IMMEDIATE_AB)
  static constexpr uint8_t kDrivenOutputCount = 1;
#else
  static constexpr uint8_t kDrivenOutputCount = 2;
#endif
  bool stage(const OwnedNodeFrame &frame, SpiRefreshReport *report);
  SpiRefreshReport showStaged();

  CRGB pixels_[kDrivenOutputCount][MAX_PIXELS_PER_OUTPUT] = {};
  OutputDescriptor outputs_[MAX_OUTPUTS] = {};
  bool initialized_ = false;
};

}  // namespace light_belt

#endif

#endif
