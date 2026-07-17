#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC) || \
    defined(LIGHT_BELT_FASTLED_GPIO4_IMMEDIATE_AB)

#include "fastled_ws2811_backend.h"

#include <Arduino.h>

#include "config.h"

namespace light_belt {

namespace {

static_assert(NODE_ID == 2, "FastLED diagnostic is Node 2 only");
#if defined(LIGHT_BELT_FASTLED_GPIO4_IMMEDIATE_AB)
static_assert(OUTPUT_COUNT == 1, "FastLED GPIO4 A/B expects one output");
static_assert(OUTPUT_0_GPIO == 4, "FastLED GPIO4 A/B must use GPIO4");
#else
static_assert(OUTPUT_COUNT == 3, "FastLED diagnostic expects three outputs");
static_assert(OUTPUT_0_GPIO == 4, "FastLED output 1 must use GPIO4");
static_assert(OUTPUT_1_GPIO == 5, "FastLED output 2 must use GPIO5");
static_assert(OUTPUT_2_GPIO == 6, "disabled output 3 must remain GPIO6");
#endif

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
      output_count != OUTPUT_COUNT || outputs[0].gpio != OUTPUT_0_GPIO) {
    return false;
  }
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  if (outputs[1].gpio != OUTPUT_1_GPIO || outputs[2].gpio != OUTPUT_2_GPIO) {
    return false;
  }
#endif
  for (uint8_t index = 0; index < output_count; ++index) {
    outputs_[index] = outputs[index];
  }

#if WS2811_COLOR_ORDER == WS2811_COLOR_ORDER_GRB
  FastLED.addLeds<WS2811, OUTPUT_0_GPIO, GRB>(
      pixels_[0], outputs_[0].pixel_count);
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  FastLED.addLeds<WS2811, OUTPUT_1_GPIO, GRB>(
      pixels_[1], outputs_[1].pixel_count);
#endif
#else
  FastLED.addLeds<WS2811, OUTPUT_0_GPIO, RGB>(
      pixels_[0], outputs_[0].pixel_count);
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  FastLED.addLeds<WS2811, OUTPUT_1_GPIO, RGB>(
      pixels_[1], outputs_[1].pixel_count);
#endif
#endif
  FastLED.setBrightness(255);
  FastLED.setCorrection(UncorrectedColor);
  FastLED.setTemperature(UncorrectedTemperature);
  FastLED.setDither(DISABLE_DITHER);

#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  pinMode(OUTPUT_2_GPIO, OUTPUT);
  digitalWrite(OUTPUT_2_GPIO, LOW);
#endif
  initialized_ = true;
  return true;
}

bool FastLedWs2811Backend::stage(
    const OwnedNodeFrame &frame, SpiRefreshReport *report) {
  if (report == nullptr) {
    return false;
  }
  if (!initialized_) {
    report->status = SpiRefreshStatus::NotInitialized;
    return false;
  }
  if (frame.output_count != OUTPUT_COUNT) {
    report->status = SpiRefreshStatus::InvalidFrame;
    return false;
  }
  for (uint8_t index = 0; index < frame.output_count; ++index) {
    if (!sameDescriptor(frame.outputs[index].descriptor, outputs_[index])) {
      report->status = SpiRefreshStatus::InvalidFrame;
      return false;
    }
  }

  for (uint8_t output_index = 0; output_index < kDrivenOutputCount;
       ++output_index) {
    const OwnedOutputFrame &source = frame.outputs[output_index];
    for (uint16_t pixel = 0; pixel < source.descriptor.pixel_count; ++pixel) {
      pixels_[output_index][pixel] = CRGB(
          source.pixels[pixel].r,
          source.pixels[pixel].g,
          source.pixels[pixel].b);
    }
  }
  report->status = SpiRefreshStatus::Ok;
  return true;
}

SpiRefreshReport FastLedWs2811Backend::showStaged() {
  SpiRefreshReport report{};
  if (!initialized_) {
    report.status = SpiRefreshStatus::NotInitialized;
    return report;
  }
  FastLED.show();
  report.successful_transactions = 1;
  report.status = SpiRefreshStatus::Ok;
  return report;
}

SpiRefreshReport FastLedWs2811Backend::prepare(const OwnedNodeFrame &frame) {
  SpiRefreshReport report{};
  (void)frame;
  report.status = SpiRefreshStatus::PrepareUnsupported;
  return report;
}

SpiRefreshReport FastLedWs2811Backend::transmitPrepared() {
  SpiRefreshReport report{};
  report.status = SpiRefreshStatus::PrepareUnsupported;
  return report;
}

void FastLedWs2811Backend::cancelPrepared() {}

bool FastLedWs2811Backend::hasPreparedFrame() const { return false; }

bool FastLedWs2811Backend::supportsScheduledApply() const {
  return false;
}

uint32_t FastLedWs2811Backend::preparedWireTimeUs() const { return 0; }

SpiRefreshReport FastLedWs2811Backend::refresh(const OwnedNodeFrame &frame) {
  SpiRefreshReport report{};
  if (!stage(frame, &report)) {
    return report;
  }
  return showStaged();
}

}  // namespace light_belt

#endif
