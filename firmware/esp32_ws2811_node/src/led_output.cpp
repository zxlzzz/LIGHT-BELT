#include "led_output.h"

#include "config.h"

namespace light_belt {

void LedOutput::begin() {
  FastLED.addLeds<WS2811, LED_PIN, COLOR_ORDER>(pixels_, PIXEL_COUNT);
  FastLED.setBrightness(BRIGHTNESS_MAX);
  showBlack();
}

void LedOutput::applyFrame(const UdpV2Frame &frame) {
  for (uint16_t i = 0; i < frame.pixel_count; ++i) {
    const uint16_t offset = i * 3U;
    pixels_[i] = CRGB(frame.payload[offset], frame.payload[offset + 1], frame.payload[offset + 2]);
  }
  FastLED.show();
}

void LedOutput::showBlack() {
  fill_solid(pixels_, PIXEL_COUNT, CRGB::Black);
  FastLED.show();
}

}  // namespace light_belt
