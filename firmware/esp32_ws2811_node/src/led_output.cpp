#include "led_output.h"

namespace light_belt {

namespace {

constexpr OutputDescriptor kConfiguredOutputs[] = {
    {OUTPUT_0_ID, OUTPUT_0_GPIO, OUTPUT_0_PIXELS},
#if OUTPUT_COUNT >= 2
    {OUTPUT_1_ID, OUTPUT_1_GPIO, OUTPUT_1_PIXELS},
#endif
#if OUTPUT_COUNT >= 3
    {OUTPUT_2_ID, OUTPUT_2_GPIO, OUTPUT_2_PIXELS},
#endif
};

constexpr uint8_t kDirectionPins[] = {15, 16, 17};

static_assert(OUTPUT_COUNT >= 1 && OUTPUT_COUNT <= MAX_OUTPUTS,
              "OUTPUT_COUNT must be 1, 2, or 3");

}  // namespace

LedOutput::LedOutput() : state_(kConfiguredOutputs, OUTPUT_COUNT) {}

bool LedOutput::begin() {
  if (!state_.configurationValid()) {
    return false;
  }
  // Keep every level-shifter input low before enabling its A-to-B direction.
  // This minimizes WS2811 data glitches while the MCU leaves reset.
  for (uint8_t index = 0; index < state_.outputCount(); ++index) {
    const OutputDescriptor &output = state_.descriptor(index);
    pinMode(output.gpio, OUTPUT);
    digitalWrite(output.gpio, LOW);
  }
  for (const uint8_t pin : kDirectionPins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, HIGH);
  }
  for (uint8_t index = 0; index < state_.outputCount(); ++index) {
    const OutputDescriptor &output = state_.descriptor(index);
    if (output.gpio == 4) {
      FastLED.addLeds<WS2811, 4, COLOR_ORDER>(pixels_[index], output.pixel_count);
    } else if (output.gpio == 5) {
      FastLED.addLeds<WS2811, 5, COLOR_ORDER>(pixels_[index], output.pixel_count);
    } else if (output.gpio == 6) {
      FastLED.addLeds<WS2811, 6, COLOR_ORDER>(pixels_[index], output.pixel_count);
    } else {
      return false;
    }
  }
  FastLED.setBrightness(BRIGHTNESS_MAX);
  return showBlack();
}

bool LedOutput::acceptFrame(const UdpV3Frame &frame, uint32_t now_ms) {
  if (!state_.applyFrame(frame)) {
    return false;
  }
  state_.noteAcceptedAt(now_ms);
  copyStateToLeds();
  // One FastLED.show() refreshes all independently registered GPIO outputs.
  FastLED.show();
  return true;
}

bool LedOutput::showBlack() {
  if (!state_.applySafeBlack()) {
    return false;
  }
  copyStateToLeds();
  FastLED.show();
  return true;
}

bool LedOutput::timedOut(uint32_t now_ms) const {
  return state_.timedOut(now_ms, SAFE_TIMEOUT_MS);
}

const OutputDescriptor *LedOutput::descriptors() const { return kConfiguredOutputs; }

uint8_t LedOutput::outputCount() const { return state_.outputCount(); }

void LedOutput::copyStateToLeds() {
  for (uint8_t output_index = 0; output_index < state_.outputCount(); ++output_index) {
    const OutputDescriptor &output = state_.descriptor(output_index);
    const RgbPixel *source = state_.pixels(output_index);
    for (uint16_t pixel = 0; pixel < output.pixel_count; ++pixel) {
      pixels_[output_index][pixel] = CRGB(source[pixel].r, source[pixel].g, source[pixel].b);
    }
  }
}

}  // namespace light_belt
