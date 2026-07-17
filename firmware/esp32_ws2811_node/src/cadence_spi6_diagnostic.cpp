#include <Arduino.h>

#include "driver/spi_master.h"
#include "esp_attr.h"
#include "esp_err.h"

#if defined(LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC)
#include "ws2811_spi_encoder.h"
#else
#include "ws2811_spi6_encoder.h"
#endif

#include <string.h>

namespace {

using light_belt::RgbPixel;
using light_belt::Ws2811ColorOrder;
#if !defined(LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC)
using light_belt::encodeWs2811Spi6;
#endif

constexpr uint8_t kDataPin = 4;
constexpr uint16_t kGroupCount = 10;
// Matches the quantized channel value produced by the current Immediate A/B
// profile: (0.65 * 0.35) ^ 1.30 * 255 ~= 37.
constexpr uint8_t kBlueLevel = 0x25;
constexpr uint16_t kRepeatedFrames = 200;
constexpr uint16_t kDynamicFrames = 300;
constexpr uint32_t kRepeatedPeriodUs = 33000;
constexpr uint32_t kSeparatorMs = 2000;
constexpr uint32_t kMinimumResetLowUs = 500;
#if defined(LIGHT_BELT_CHANGE_ONLY_EFFECTS_DIAGNOSTIC)
constexpr uint16_t kChangeOnlyFrames = 200;
constexpr uint32_t kChangeOnlyHoldMs = 200;
constexpr uint8_t kBreathLevels[] = {
    4, 6, 8, 10, 12, 15, 18, 22, 27, 32,
    37, 32, 27, 22, 18, 15, 12, 10, 8, 6,
};
static_assert(
    kChangeOnlyFrames % (sizeof(kBreathLevels) / sizeof(kBreathLevels[0])) ==
        0,
    "change-only breath must end on a complete cycle");
#endif
#if defined(LIGHT_BELT_CHANGE_ONLY_SUITE_DIAGNOSTIC)
constexpr uint16_t kSuiteFirstGroup = 1;
constexpr uint16_t kSuiteGroupCount = kGroupCount - kSuiteFirstGroup;
constexpr uint32_t kSuiteHoldMs = 200;
constexpr uint8_t kSuiteBreathLevels[] = {4, 8, 16, 32, 16, 8};
static_assert(kSuiteGroupCount == 9, "suite must leave only group zero dark");
#endif
#if defined(LIGHT_BELT_CHANGE_ONLY_WARM_SUITE_DIAGNOSTIC) || \
    defined(LIGHT_BELT_TWO_LEVEL_WARM_PULSE_DIAGNOSTIC)
constexpr uint16_t kWarmFirstGroup = 1;
constexpr uint16_t kWarmGroupCount = kGroupCount - kWarmFirstGroup;
constexpr uint32_t kWarmStateHoldMs = 200;
constexpr uint32_t kWarmPaletteHoldMs = 3000;
constexpr uint8_t kWarmBreathRed[] = {4, 8, 16, 32, 16, 8};
constexpr uint8_t kWarmBreathGreen[] = {1, 2, 4, 8, 4, 2};
static_assert(kWarmGroupCount == 9, "warm suite must leave group zero dark");
static_assert(
    sizeof(kWarmBreathRed) == sizeof(kWarmBreathGreen),
    "warm breath channel tables must match");
#endif
#if defined(LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC)
constexpr uint32_t kSpiClockHz = light_belt::WS2811_SPI_CLOCK_HZ;
constexpr size_t kSpi4TargetGuardBytes = 200;
constexpr size_t kSpi4ExtraGuardBytes =
    kSpi4TargetGuardBytes - light_belt::WS2811_SPI_GUARD_BYTES;
constexpr size_t kEncodedCapacity =
    light_belt::WS2811_SPI_MAX_FRAME_BYTES + 2U * kSpi4ExtraGuardBytes;
static_assert(
    light_belt::WS2811_SPI_GUARD_BYTES < kSpi4TargetGuardBytes,
    "SPI4 diagnostic must extend the standard guard");
static_assert(
    static_cast<uint64_t>(kSpi4TargetGuardBytes) * 8U * 1000000U >=
        static_cast<uint64_t>(kSpiClockHz) * kMinimumResetLowUs,
    "SPI4 diagnostic guard must provide at least 500 us low");
#else
constexpr uint32_t kSpiClockHz = light_belt::WS2811_SPI6_CLOCK_HZ;
constexpr size_t kEncodedCapacity =
    light_belt::WS2811_SPI6_MAX_FRAME_BYTES;
#endif
#if defined(LIGHT_BELT_SPI6_RGB_STATIC_DIAGNOSTIC) || \
    defined(LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC) || \
    defined(LIGHT_BELT_CHANGE_ONLY_EFFECTS_DIAGNOSTIC) || \
    defined(LIGHT_BELT_CHANGE_ONLY_SUITE_DIAGNOSTIC) || \
    defined(LIGHT_BELT_CHANGE_ONLY_WARM_SUITE_DIAGNOSTIC) || \
    defined(LIGHT_BELT_TWO_LEVEL_WARM_PULSE_DIAGNOSTIC)
constexpr uint32_t kSingleWriteHoldMs = 4000;
constexpr Ws2811ColorOrder kDiagnosticColorOrder = Ws2811ColorOrder::RGB;
#else
constexpr Ws2811ColorOrder kDiagnosticColorOrder = Ws2811ColorOrder::GRB;
#endif

spi_device_handle_t device = nullptr;
RgbPixel pixels[kGroupCount] = {};
alignas(4) DRAM_ATTR uint8_t encoded[kEncodedCapacity] = {};
size_t encodedLength = 0;
uint32_t lastTransmitEndUs = 0;

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

bool initializeSpi() {
  spi_bus_config_t bus{};
  bus.mosi_io_num = kDataPin;
  bus.miso_io_num = -1;
  bus.sclk_io_num = -1;
  bus.quadwp_io_num = -1;
  bus.quadhd_io_num = -1;
  bus.data4_io_num = -1;
  bus.data5_io_num = -1;
  bus.data6_io_num = -1;
  bus.data7_io_num = -1;
  bus.max_transfer_sz = sizeof(encoded);
  bus.flags = SPICOMMON_BUSFLAG_MASTER | SPICOMMON_BUSFLAG_MOSI;
  if (spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO) != ESP_OK) {
    return false;
  }

  spi_device_interface_config_t config{};
  config.mode = 0;
  config.duty_cycle_pos = 128;
  config.clock_speed_hz = kSpiClockHz;
  config.spics_io_num = -1;
  config.flags = SPI_DEVICE_HALFDUPLEX;
  config.queue_size = 1;
  if (spi_bus_add_device(SPI2_HOST, &config, &device) != ESP_OK) {
    spi_bus_free(SPI2_HOST);
    device = nullptr;
    return false;
  }
  return true;
}

bool encodePixels() {
#if defined(LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC)
  const size_t innerLength = light_belt::ws2811SpiFrameSize(kGroupCount);
  if (innerLength == 0) {
    return false;
  }
  const size_t totalLength = innerLength + 2U * kSpi4ExtraGuardBytes;
  if (totalLength > sizeof(encoded)) {
    return false;
  }
  memset(encoded, 0, totalLength);
  size_t actualInnerLength = 0;
  if (!light_belt::encodeWs2811Spi(
          pixels,
          kGroupCount,
          kDiagnosticColorOrder,
          encoded + kSpi4ExtraGuardBytes,
          sizeof(encoded) - kSpi4ExtraGuardBytes,
          &actualInnerLength) ||
      actualInnerLength != innerLength) {
    return false;
  }
  encodedLength = totalLength;
  return true;
#else
  return encodeWs2811Spi6(
      pixels, kGroupCount, kDiagnosticColorOrder, encoded, sizeof(encoded),
      &encodedLength);
#endif
}

bool prepareUniform(uint8_t red, uint8_t green, uint8_t blue) {
  for (uint16_t group = 0; group < kGroupCount; ++group) {
    pixels[group] = {red, green, blue};
  }
  return encodePixels();
}

bool transmitPrepared() {
  if (lastTransmitEndUs != 0) {
    waitUntilMicros(lastTransmitEndUs + kMinimumResetLowUs);
  }
  spi_transaction_t transaction{};
  transaction.length = encodedLength * 8U;
  transaction.tx_buffer = encoded;
  const bool transmitted =
      spi_device_polling_transmit(device, &transaction) == ESP_OK;
  lastTransmitEndUs = micros();
  return transmitted;
}

bool prepareMovingBlue(uint16_t position) {
  for (uint16_t group = 0; group < kGroupCount; ++group) {
    const uint8_t blue = group == position ? kBlueLevel : 0;
    pixels[group] = {0, 0, blue};
  }
  return encodePixels();
}

bool prepareBlueCheckerboard(uint16_t parity) {
  for (uint16_t group = 0; group < kGroupCount; ++group) {
    const uint8_t blue = group % 2U == parity ? kBlueLevel : 0;
    pixels[group] = {0, 0, blue};
  }
  return encodePixels();
}

bool showUniform(uint8_t red, uint8_t green, uint8_t blue) {
  return prepareUniform(red, green, blue) && transmitPrepared();
}

bool blackSeparator() {
  if (!showUniform(0, 0, 0)) {
    return false;
  }
  delay(kSeparatorMs);
  return true;
}

#if defined(LIGHT_BELT_CHANGE_ONLY_WARM_SUITE_DIAGNOSTIC) || \
    defined(LIGHT_BELT_TWO_LEVEL_WARM_PULSE_DIAGNOSTIC)
void clearWarmPixels() {
  for (uint16_t group = 0; group < kGroupCount; ++group) {
    pixels[group] = {0, 0, 0};
  }
}

bool transmitWarmPixels() {
  return encodePixels() && transmitPrepared();
}

bool showWarmUniform(uint8_t red, uint8_t green, uint8_t blue) {
  clearWarmPixels();
  for (uint16_t group = kWarmFirstGroup; group < kGroupCount; ++group) {
    pixels[group] = {red, green, blue};
  }
  return transmitWarmPixels();
}

bool runWarmPalette() {
  struct PaletteEntry {
    const char *name;
    uint8_t red;
    uint8_t green;
    uint8_t blue;
  };
  constexpr PaletteEntry kPalette[] = {
      {"RED20", 0x20, 0x00, 0x00},
      {"GREEN20", 0x00, 0x20, 0x00},
      {"BLUE20", 0x00, 0x00, 0x20},
      {"ORANGE20_08", 0x20, 0x08, 0x00},
      {"AMBER20_10", 0x20, 0x10, 0x00},
  };
  Serial.printf(
      "phase=PALETTE9 expected=uniform_power2_colors hold_ms=%lu "
      "states=%u\n",
      static_cast<unsigned long>(kWarmPaletteHoldMs),
      static_cast<unsigned>(sizeof(kPalette) / sizeof(kPalette[0])));
  for (const PaletteEntry &entry : kPalette) {
    Serial.printf(
        "palette_state=%s rgb=%u,%u,%u\n",
        entry.name, entry.red, entry.green, entry.blue);
    if (!showWarmUniform(entry.red, entry.green, entry.blue)) {
      return false;
    }
    delay(kWarmPaletteHoldMs);
  }
  Serial.println("phase=PALETTE9 complete");
  return true;
}

bool runWarmFlow(
    const char *phase, uint8_t red, uint8_t green, uint8_t blue) {
  constexpr uint16_t kFrames = kWarmGroupCount * 3U;
  Serial.printf(
      "phase=%s expected=one_moving_group rgb=%u,%u,%u hold_ms=%lu "
      "frames=%u\n",
      phase, red, green, blue,
      static_cast<unsigned long>(kWarmStateHoldMs), kFrames);
  for (uint16_t frame = 0; frame < kFrames; ++frame) {
    clearWarmPixels();
    pixels[kWarmFirstGroup + frame % kWarmGroupCount] = {red, green, blue};
    if (!transmitWarmPixels()) {
      return false;
    }
    delay(kWarmStateHoldMs);
  }
  Serial.printf("phase=%s complete\n", phase);
  return true;
}

bool runWarmBreath() {
  constexpr size_t kLevelCount = sizeof(kWarmBreathRed);
  constexpr uint16_t kFrames = static_cast<uint16_t>(kLevelCount * 3U);
  Serial.printf(
      "phase=ORANGE_BREATH9 expected=uniform_warm_power2_steps "
      "hold_ms=%lu frames=%u\n",
      static_cast<unsigned long>(kWarmStateHoldMs), kFrames);
  for (uint16_t frame = 0; frame < kFrames; ++frame) {
    const size_t level = frame % kLevelCount;
    if (!showWarmUniform(
            kWarmBreathRed[level], kWarmBreathGreen[level], 0)) {
      return false;
    }
    delay(kWarmStateHoldMs);
  }
  Serial.println("phase=ORANGE_BREATH9 complete");
  return true;
}

bool runTwoLevelWarmPulse() {
  constexpr uint16_t kTransitions = 30;
  constexpr uint32_t kPulseHoldMs = 2000;
  Serial.printf(
      "phase=TWO_LEVEL_WARM_PULSE9 expected=warm_tint_pulse "
      "low_rgb=32,8,0 high_rgb=32,16,0 hold_ms=%lu transitions=%u\n",
      static_cast<unsigned long>(kPulseHoldMs), kTransitions);
  for (uint16_t transition = 0; transition < kTransitions; ++transition) {
    const uint8_t green = transition % 2U == 0 ? 0x08 : 0x10;
    if (!showWarmUniform(0x20, green, 0)) {
      return false;
    }
    delay(kPulseHoldMs);
  }
  Serial.println("phase=TWO_LEVEL_WARM_PULSE9 complete");
  return true;
}
#endif

#if defined(LIGHT_BELT_CHANGE_ONLY_SUITE_DIAGNOSTIC)
void clearSuitePixels() {
  for (uint16_t group = 0; group < kGroupCount; ++group) {
    pixels[group] = {0, 0, 0};
  }
}

bool transmitSuitePixels() {
  return encodePixels() && transmitPrepared();
}

bool runSuiteFlow() {
  constexpr uint16_t kFrames = kSuiteGroupCount * 3U;
  Serial.printf(
      "phase=FLOW9 expected=one_blue_group hold_ms=%lu frames=%u\n",
      static_cast<unsigned long>(kSuiteHoldMs), kFrames);
  for (uint16_t frame = 0; frame < kFrames; ++frame) {
    clearSuitePixels();
    pixels[kSuiteFirstGroup + frame % kSuiteGroupCount] = {0, 0, kBlueLevel};
    if (!transmitSuitePixels()) {
      return false;
    }
    delay(kSuiteHoldMs);
  }
  Serial.println("phase=FLOW9 complete");
  return true;
}

bool runSuiteScanner() {
  constexpr uint16_t kBounceStates = 2U * kSuiteGroupCount - 2U;
  constexpr uint16_t kFrames = kBounceStates * 3U;
  Serial.printf(
      "phase=SCANNER9 expected=one_blue_group_bounce hold_ms=%lu frames=%u\n",
      static_cast<unsigned long>(kSuiteHoldMs), kFrames);
  for (uint16_t frame = 0; frame < kFrames; ++frame) {
    const uint16_t state = frame % kBounceStates;
    const uint16_t position = state < kSuiteGroupCount
        ? state
        : kBounceStates - state;
    clearSuitePixels();
    pixels[kSuiteFirstGroup + position] = {0, 0, kBlueLevel};
    if (!transmitSuitePixels()) {
      return false;
    }
    delay(kSuiteHoldMs);
  }
  Serial.println("phase=SCANNER9 complete");
  return true;
}

bool runSuiteTheater() {
  constexpr uint16_t kFrames = 18;
  Serial.printf(
      "phase=THEATER9 expected=three_blue_groups hold_ms=%lu frames=%u\n",
      static_cast<unsigned long>(kSuiteHoldMs), kFrames);
  for (uint16_t frame = 0; frame < kFrames; ++frame) {
    const uint16_t phase = frame % 3U;
    clearSuitePixels();
    for (uint16_t offset = 0; offset < kSuiteGroupCount; ++offset) {
      if (offset % 3U == phase) {
        pixels[kSuiteFirstGroup + offset] = {0, 0, kBlueLevel};
      }
    }
    if (!transmitSuitePixels()) {
      return false;
    }
    delay(kSuiteHoldMs);
  }
  Serial.println("phase=THEATER9 complete");
  return true;
}

bool runSuiteWipe() {
  constexpr uint16_t kCycleStates = 2U * kSuiteGroupCount - 1U;
  constexpr uint16_t kFrames = kCycleStates * 3U;
  Serial.printf(
      "phase=WIPE9 expected=blue_fill_then_clear hold_ms=%lu frames=%u\n",
      static_cast<unsigned long>(kSuiteHoldMs), kFrames);
  for (uint16_t frame = 0; frame < kFrames; ++frame) {
    const uint16_t state = frame % kCycleStates;
    clearSuitePixels();
    if (state < kSuiteGroupCount) {
      for (uint16_t offset = 0; offset <= state; ++offset) {
        pixels[kSuiteFirstGroup + offset] = {0, 0, kBlueLevel};
      }
    } else {
      const uint16_t cleared = state - kSuiteGroupCount + 1U;
      for (uint16_t offset = cleared; offset < kSuiteGroupCount; ++offset) {
        pixels[kSuiteFirstGroup + offset] = {0, 0, kBlueLevel};
      }
    }
    if (!transmitSuitePixels()) {
      return false;
    }
    delay(kSuiteHoldMs);
  }
  Serial.println("phase=WIPE9 complete");
  return true;
}

bool runSuiteBreath() {
  constexpr size_t kLevelCount =
      sizeof(kSuiteBreathLevels) / sizeof(kSuiteBreathLevels[0]);
  constexpr uint16_t kFrames = static_cast<uint16_t>(kLevelCount * 3U);
  Serial.printf(
      "phase=BREATH9 expected=uniform_blue_four_levels hold_ms=%lu "
      "frames=%u\n",
      static_cast<unsigned long>(kSuiteHoldMs), kFrames);
  for (uint16_t frame = 0; frame < kFrames; ++frame) {
    clearSuitePixels();
    const uint8_t level = kSuiteBreathLevels[frame % kLevelCount];
    for (uint16_t group = kSuiteFirstGroup; group < kGroupCount; ++group) {
      pixels[group] = {0, 0, level};
    }
    if (!transmitSuitePixels()) {
      return false;
    }
    delay(kSuiteHoldMs);
  }
  Serial.println("phase=BREATH9 complete");
  return true;
}
#endif

#if defined(LIGHT_BELT_CHANGE_ONLY_EFFECTS_DIAGNOSTIC)
bool runChangeOnlyFlow() {
  Serial.printf(
      "phase=FLOW expected=single_blue_group mode=change_only "
      "hold_ms=%lu frames=%u cycles=%u\n",
      static_cast<unsigned long>(kChangeOnlyHoldMs),
      kChangeOnlyFrames,
      kChangeOnlyFrames / kGroupCount);
  for (uint16_t frame = 0; frame < kChangeOnlyFrames; ++frame) {
    if (!prepareMovingBlue(frame % kGroupCount) || !transmitPrepared()) {
      return false;
    }
    delay(kChangeOnlyHoldMs);
  }
  Serial.println("phase=FLOW complete");
  return true;
}

bool runChangeOnlyBreath() {
  constexpr size_t kLevelCount =
      sizeof(kBreathLevels) / sizeof(kBreathLevels[0]);
  Serial.printf(
      "phase=BREATH expected=uniform_blue_steps mode=change_only "
      "hold_ms=%lu levels=%u frames=%u cycles=%u\n",
      static_cast<unsigned long>(kChangeOnlyHoldMs),
      static_cast<unsigned>(kLevelCount),
      kChangeOnlyFrames,
      static_cast<unsigned>(kChangeOnlyFrames / kLevelCount));
  for (uint16_t frame = 0; frame < kChangeOnlyFrames; ++frame) {
    const uint8_t level = kBreathLevels[frame % kLevelCount];
    if (!showUniform(0, 0, level)) {
      return false;
    }
    delay(kChangeOnlyHoldMs);
  }
  Serial.println("phase=BREATH complete");
  return true;
}
#endif

#if defined(LIGHT_BELT_SPI6_RGB_STATIC_DIAGNOSTIC) || \
    defined(LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC)
bool runSingleUniform(
    const char *phase,
    uint8_t wire_slot,
    uint8_t red,
    uint8_t green,
    uint8_t blue) {
  Serial.printf(
      "phase=%s expected=stable_uniform mode=single_write wire_slot=%u "
      "wire_rgb=%u,%u,%u hold_ms=%lu\n",
      phase,
      wire_slot,
      red,
      green,
      blue,
      static_cast<unsigned long>(kSingleWriteHoldMs));
  if (!showUniform(red, green, blue)) {
    return false;
  }
  delay(kSingleWriteHoldMs);
  return blackSeparator();
}
#endif

void fail(const char* stage) {
  Serial.printf("diagnostic_failed stage=%s\n", stage);
  while (true) {
    delay(1000);
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1000);

  if (!initializeSpi()) {
    fail("spi_init");
  }

#if defined(LIGHT_BELT_TWO_LEVEL_WARM_PULSE_DIAGNOSTIC)
  Serial.println(
      "spi6_two_level_warm_pulse_start gpio=4 groups=10 "
      "animated_groups=2-10 clock_hz=5000000 color_order=RGB "
      "low_rgb=32,8,0 high_rgb=32,16,0 pulse_hold_ms=2000 "
      "repeated_state_writes=0 group1_command=black");
  if (!blackSeparator()) {
    fail("startup_black");
  }
  Serial.println("phase=LOW_STATIC9 rgb=32,8,0 hold_ms=10000");
  if (!showWarmUniform(0x20, 0x08, 0)) {
    fail("phase_LOW_STATIC9");
  }
  delay(10000);
  if (!blackSeparator()) {
    fail("separator_LOW_HIGH");
  }
  Serial.println("phase=HIGH_STATIC9 rgb=32,16,0 hold_ms=10000");
  if (!showWarmUniform(0x20, 0x10, 0)) {
    fail("phase_HIGH_STATIC9");
  }
  delay(10000);
  if (!blackSeparator()) {
    fail("separator_HIGH_PULSE");
  }
  if (!runTwoLevelWarmPulse() || !blackSeparator()) {
    fail("phase_TWO_LEVEL_WARM_PULSE9");
  }
  Serial.println(
      "spi6_two_level_warm_pulse_complete expected=black "
      "physical_writes=36");
#elif defined(LIGHT_BELT_CHANGE_ONLY_WARM_SUITE_DIAGNOSTIC)
  Serial.println(
      "spi6_change_only_warm_suite_start gpio=4 groups=10 "
      "animated_groups=2-10 clock_hz=5000000 color_order=RGB "
      "state_hold_ms=200 repeated_state_writes=0 group1_command=black");
  if (!blackSeparator()) {
    fail("startup_black");
  }
  if (!runWarmPalette() || !blackSeparator()) {
    fail("phase_PALETTE9");
  }
  if (!runWarmFlow("BLUE20_FLOW9", 0, 0, 0x20) || !blackSeparator()) {
    fail("phase_BLUE20_FLOW9");
  }
  if (!runWarmFlow("ORANGE_FLOW9", 0x20, 0x08, 0) ||
      !blackSeparator()) {
    fail("phase_ORANGE_FLOW9");
  }
  if (!runWarmBreath() || !blackSeparator()) {
    fail("phase_ORANGE_BREATH9");
  }
  Serial.println(
      "spi6_change_only_warm_suite_complete expected=black "
      "physical_writes=82");
#elif defined(LIGHT_BELT_CHANGE_ONLY_SUITE_DIAGNOSTIC)
  Serial.println(
      "spi6_change_only_suite_start gpio=4 groups=10 animated_groups=2-10 "
      "clock_hz=5000000 color_order=RGB state_hold_ms=200 "
      "repeated_state_writes=0 group1_command=black");
  if (!blackSeparator()) {
    fail("startup_black");
  }
  if (!runSuiteFlow() || !blackSeparator()) {
    fail("phase_FLOW9");
  }
  if (!runSuiteScanner() || !blackSeparator()) {
    fail("phase_SCANNER9");
  }
  if (!runSuiteTheater() || !blackSeparator()) {
    fail("phase_THEATER9");
  }
  if (!runSuiteWipe() || !blackSeparator()) {
    fail("phase_WIPE9");
  }
  if (!runSuiteBreath() || !blackSeparator()) {
    fail("phase_BREATH9");
  }
  Serial.println(
      "spi6_change_only_suite_complete expected=black physical_writes=168");
#elif defined(LIGHT_BELT_CHANGE_ONLY_EFFECTS_DIAGNOSTIC)
  Serial.println(
      "spi6_change_only_effects_start gpio=4 groups=10 "
      "clock_hz=5000000 t0h_ns=200 t1h_ns=600 color_order=RGB "
      "level_max=37 state_hold_ms=200 repeated_state_writes=0 "
      "pre_guard_us=500 post_guard_us=500");
  if (!blackSeparator()) {
    fail("startup_black");
  }
  if (!runChangeOnlyFlow()) {
    fail("phase_FLOW");
  }
  if (!blackSeparator()) {
    fail("separator_FLOW_BREATH");
  }
  if (!runChangeOnlyBreath()) {
    fail("phase_BREATH");
  }
  if (!blackSeparator()) {
    fail("final_black");
  }
  Serial.println(
      "spi6_change_only_effects_complete expected=black "
      "physical_writes=403");
#elif defined(LIGHT_BELT_SPI6_RGB_STATIC_DIAGNOSTIC)
  Serial.println(
      "spi6_rgb_static_start gpio=4 groups=10 clock_hz=5000000 "
      "t0h_ns=200 t1h_ns=600 color_order=RGB level=37 "
      "mode=single_write hold_ms=4000 "
      "pre_guard_us=500 post_guard_us=500");
  if (!blackSeparator()) {
    fail("startup_black");
  }
  if (!runSingleUniform("R", 0, kBlueLevel, 0, 0)) {
    fail("phase_R");
  }
  if (!runSingleUniform("G", 1, 0, kBlueLevel, 0)) {
    fail("phase_G");
  }
  if (!runSingleUniform("B", 2, 0, 0, kBlueLevel)) {
    fail("phase_B");
  }
  Serial.println("spi6_rgb_static_complete expected=black");
#else
#if defined(LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC)
  Serial.println(
      "spi4_cadence_start gpio=4 groups=10 clock_hz=3200000 "
      "bits_per_ws=4 symbol0=1000 symbol1=1100 "
      "t0h_ns=312.5 t1h_ns=625 color_order=RGB raw_level=37 "
      "pre_guard_us=500 post_guard_us=500");
#else
  Serial.println(
      "spi6_cadence_start gpio=4 groups=10 clock_hz=5000000 "
      "t0h_ns=200 t1h_ns=600 color=blue level=37");
#endif
  if (!blackSeparator()) {
    fail("startup_black");
  }

#if defined(LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC)
  if (!runSingleUniform("R", 0, kBlueLevel, 0, 0)) {
    fail("phase_R");
  }
  if (!runSingleUniform("G", 1, 0, kBlueLevel, 0)) {
    fail("phase_G");
  }
  if (!runSingleUniform("B", 2, 0, 0, kBlueLevel)) {
    fail("phase_B");
  }
#else
  Serial.println("phase=A expected=solid_blue mode=single_write hold_ms=5000");
  if (!showUniform(0, 0, kBlueLevel)) {
    fail("phase_A");
  }
  delay(5000);
  Serial.println("phase=A complete");
  if (!blackSeparator()) {
    fail("separator_A_D");
  }
#endif

  Serial.println("phase=D expected=solid_blue period_ms=33 frames=200");
  if (!prepareUniform(0, 0, kBlueLevel)) {
    fail("phase_D_encode");
  }
  uint32_t nextStart = micros();
  for (uint16_t frame = 0; frame < kRepeatedFrames; ++frame) {
    waitUntilMicros(nextStart);
    if (!transmitPrepared()) {
      fail("phase_D_transmit");
    }
    nextStart += kRepeatedPeriodUs;
  }
  Serial.println("phase=D complete");

  Serial.println("phase=K expected=black period_ms=33 frames=200");
  if (!prepareUniform(0, 0, 0)) {
    fail("phase_K_encode");
  }
  nextStart = micros();
  for (uint16_t frame = 0; frame < kRepeatedFrames; ++frame) {
    waitUntilMicros(nextStart);
    if (!transmitPrepared()) {
      fail("phase_K_transmit");
    }
    nextStart += kRepeatedPeriodUs;
  }
  Serial.println("phase=K complete");

  Serial.println(
      "phase=E expected=moving_blue_group period_ms=33 hold_frames=6 "
      "frames=300");
  nextStart = micros();
  for (uint16_t frame = 0; frame < kDynamicFrames; ++frame) {
    if (frame % 6U == 0) {
      const uint16_t position = (frame / 6U) % kGroupCount;
      if (!prepareMovingBlue(position)) {
        fail("phase_E_encode");
      }
    }
    waitUntilMicros(nextStart);
    if (!transmitPrepared()) {
      fail("phase_E_transmit");
    }
    nextStart += kRepeatedPeriodUs;
  }
  Serial.println("phase=E complete");
  if (!blackSeparator()) {
    fail("separator_E_F");
  }

  Serial.println(
      "phase=F expected=blue_checkerboard_swap period_ms=33 hold_frames=6 "
      "frames=300");
  nextStart = micros();
  for (uint16_t frame = 0; frame < kDynamicFrames; ++frame) {
    if (frame % 6U == 0) {
      const uint16_t parity = (frame / 6U) % 2U;
      if (!prepareBlueCheckerboard(parity)) {
        fail("phase_F_encode");
      }
    }
    waitUntilMicros(nextStart);
    if (!transmitPrepared()) {
      fail("phase_F_transmit");
    }
    nextStart += kRepeatedPeriodUs;
  }
  Serial.println("phase=F complete");
  if (!blackSeparator()) {
    fail("final_black");
  }

#if defined(LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC)
  Serial.println("spi4_cadence_complete expected=black");
#else
  Serial.println("spi6_cadence_complete expected=black");
#endif
#endif
}

void loop() {
  delay(1000);
}
