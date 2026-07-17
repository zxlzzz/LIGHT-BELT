#include <Arduino.h>
#include <FastLED.h>

namespace {

constexpr uint8_t kDataPin = 4;
constexpr uint16_t kGroupCount = 10;
constexpr uint8_t kBrightness = 64;
constexpr uint16_t kRepeatedFrames = 200;
constexpr uint32_t kSeparatorMs = 2000;

CRGB leds[kGroupCount];

void waitUntilMicros(uint32_t deadline) {
  while (static_cast<int32_t>(micros() - deadline) < 0) {
    const uint32_t remaining = deadline - micros();
    if (remaining > 2000) {
      delay(1);
    } else if (remaining > 0) {
      delayMicroseconds(remaining);
    }
  }
}

void showBlackSeparator() {
  fill_solid(leds, kGroupCount, CRGB::Black);
  FastLED.show();
  delay(kSeparatorMs);
}

void runRepeatedBlue(const char* phase, uint32_t periodMs) {
  Serial.printf(
      "phase=%s expected=solid_blue period_ms=%lu frames=%u\n",
      phase,
      static_cast<unsigned long>(periodMs),
      kRepeatedFrames);

  fill_solid(leds, kGroupCount, CRGB::Blue);
  const uint32_t periodUs = periodMs * 1000U;
  uint32_t nextStart = micros();

  for (uint16_t frame = 0; frame < kRepeatedFrames; ++frame) {
    waitUntilMicros(nextStart);
    FastLED.show();
    nextStart += periodUs;
  }

  Serial.printf("phase=%s complete\n", phase);
  showBlackSeparator();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1000);

#if defined(LIGHT_BELT_WS2811_400KHZ)
  FastLED.addLeds<WS2811_400, kDataPin, GRB>(leds, kGroupCount);
#else
  FastLED.addLeds<WS2811, kDataPin, GRB>(leds, kGroupCount);
#endif
  FastLED.setBrightness(kBrightness);
  FastLED.setDither(0);

#if defined(LIGHT_BELT_WS2811_400KHZ)
  Serial.println(
      "cadence_diagnostic_start timing_khz=400 gpio=4 groups=10 "
      "color=blue brightness=64");
#else
  Serial.println(
      "cadence_diagnostic_start timing_khz=800 gpio=4 groups=10 "
      "color=blue brightness=64");
#endif
  showBlackSeparator();

  Serial.println("phase=A expected=solid_blue mode=single_write hold_ms=5000");
  fill_solid(leds, kGroupCount, CRGB::Blue);
  FastLED.show();
  delay(5000);
  Serial.println("phase=A complete");
  showBlackSeparator();

  runRepeatedBlue("B", 120);
  runRepeatedBlue("C", 60);
  runRepeatedBlue("D", 33);
  runRepeatedBlue("E", 20);

  Serial.println("cadence_diagnostic_complete expected=black");
}

void loop() {
  delay(1000);
}
