#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)

#include "fastled_ws2811_backend.h"

#include <Arduino.h>

#include "config.h"

namespace light_belt {

namespace {

static_assert(NODE_ID == 2, "FastLED diagnostic is Node 2 only");
static_assert(OUTPUT_COUNT == 3, "FastLED diagnostic expects three outputs");
static_assert(OUTPUT_0_GPIO == 4, "FastLED output 1 must use GPIO4");
static_assert(OUTPUT_1_GPIO == 5, "FastLED output 2 must use GPIO5");
static_assert(OUTPUT_2_GPIO == 6, "disabled output 3 must remain GPIO6");

bool sameDescriptor(
    const OutputDescriptor &left, const OutputDescriptor &right) {
  return left.output_id == right.output_id && left.gpio == right.gpio &&
         left.pixel_count == right.pixel_count;
}

}  // namespace

bool FastLedWs2811Backend::begin(
    const OutputDescriptor *outputs, uint8_t output_count) {
  if (initialized_) {
    return true;
  }
  if (!validateOutputDescriptors(outputs, output_count) ||
      output_count != OUTPUT_COUNT || outputs[0].gpio != OUTPUT_0_GPIO ||
      outputs[1].gpio != OUTPUT_1_GPIO || outputs[2].gpio != OUTPUT_2_GPIO) {
    return false;
  }
  for (uint8_t index = 0; index < output_count; ++index) {
    outputs_[index] = outputs[index];
  }

#if WS2811_COLOR_ORDER == WS2811_COLOR_ORDER_GRB
  FastLED.addLeds<WS2811, OUTPUT_0_GPIO, GRB>(
      pixels_[0], outputs_[0].pixel_count);
  FastLED.addLeds<WS2811, OUTPUT_1_GPIO, GRB>(
      pixels_[1], outputs_[1].pixel_count);
#else
  FastLED.addLeds<WS2811, OUTPUT_0_GPIO, RGB>(
      pixels_[0], outputs_[0].pixel_count);
  FastLED.addLeds<WS2811, OUTPUT_1_GPIO, RGB>(
      pixels_[1], outputs_[1].pixel_count);
#endif
  FastLED.setBrightness(255);
  FastLED.setCorrection(UncorrectedColor);
  FastLED.setTemperature(UncorrectedTemperature);
  FastLED.setDither(DISABLE_DITHER);

  pinMode(OUTPUT_2_GPIO, OUTPUT);
  digitalWrite(OUTPUT_2_GPIO, LOW);
  initialized_ = true;
  return true;
}

SpiRefreshReport FastLedWs2811Backend::refresh(const OwnedNodeFrame &frame) {
  SpiRefreshReport report{};
  if (!initialized_) {
    report.status = SpiRefreshStatus::NotInitialized;
    return report;
  }
  if (frame.output_count != OUTPUT_COUNT) {
    report.status = SpiRefreshStatus::InvalidFrame;
    return report;
  }
  for (uint8_t index = 0; index < frame.output_count; ++index) {
    if (!sameDescriptor(frame.outputs[index].descriptor, outputs_[index])) {
      report.status = SpiRefreshStatus::InvalidFrame;
      return report;
    }
  }

  for (uint8_t output_index = 0; output_index < 2; ++output_index) {
    const OwnedOutputFrame &source = frame.outputs[output_index];
    for (uint16_t pixel = 0; pixel < source.descriptor.pixel_count; ++pixel) {
      pixels_[output_index][pixel] = CRGB(
          source.pixels[pixel].r,
          source.pixels[pixel].g,
          source.pixels[pixel].b);
    }
  }
  FastLED.show();
  report.successful_transactions = 1;
  report.status = SpiRefreshStatus::Ok;
  return report;
}

}  // namespace light_belt

#endif
