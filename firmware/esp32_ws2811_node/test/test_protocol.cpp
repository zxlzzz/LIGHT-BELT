#ifdef ARDUINO
#include <Arduino.h>
#endif
#include <string.h>
#include <unity.h>

#include "../../shared/udp_v3_golden.h"
#include "../src/frame_state.h"
#include "../src/owned_frame.h"
#include "../src/presentation_clock.h"
#include "../src/protocol.h"
#include "../src/runtime_stats.h"
#include "../src/ws2811_parallel_spi_encoder.h"
#include "../src/ws2811_rmt_encoder.h"
#include "../src/ws2811_spi3_encoder.h"
#include "../src/ws2811_spi6_encoder.h"
#include "../src/ws2811_spi_encoder.h"

namespace light_belt {

constexpr EmergencyOutputPolicy kNode2EmergencyTestPolicy = {2, {1, 4, 10}};

bool isNode2EmergencyFrameAllowed(const OwnedNodeFrame &candidate) {
  return isEmergencyFrameAllowed(candidate, kNode2EmergencyTestPolicy);
}

bool isNode2EmergencyTransitionAllowed(
    const OwnedNodeFrame &previous,
    const OwnedNodeFrame &candidate) {
  return isEmergencyTransitionAllowed(
      previous, candidate, kNode2EmergencyTestPolicy);
}

bool isNode2EmergencyChangeIntervalAllowed(
    uint32_t previous_write_ms,
    uint32_t candidate_write_ms,
    bool payload_changed,
    bool safe_state) {
  return isEmergencyChangeIntervalAllowed(
      previous_write_ms, candidate_write_ms, payload_changed, safe_state);
}

}  // namespace light_belt

namespace {

const light_belt::OutputDescriptor kOneOutput[] = {{1, 4, 2}};
const light_belt::OutputDescriptor kScheduledGoldenOutput[] = {{1, 4, 1}};
const light_belt::OutputDescriptor kTwoOutputs[] = {{1, 4, 2}, {2, 5, 1}};
const light_belt::OutputDescriptor kTwoOutputsReversed[] = {{2, 5, 1}, {1, 4, 2}};
const light_belt::OutputDescriptor kThreeOutputs[] = {
    {1, 4, 1}, {2, 5, 2}, {3, 6, 3}};

void writeU16(uint8_t *target, uint16_t value) {
  target[0] = static_cast<uint8_t>(value >> 8);
  target[1] = static_cast<uint8_t>(value);
}

void writeU32(uint8_t *target, uint32_t value) {
  target[0] = static_cast<uint8_t>(value >> 24);
  target[1] = static_cast<uint8_t>(value >> 16);
  target[2] = static_cast<uint8_t>(value >> 8);
  target[3] = static_cast<uint8_t>(value);
}

void writeU64(uint8_t *target, uint64_t value) {
  writeU32(target, static_cast<uint32_t>(value >> 32));
  writeU32(target + 4, static_cast<uint32_t>(value));
}

void repairCrc(uint8_t *raw, size_t len) {
  writeU32(raw + len - light_belt::UDP_V3_CRC_LEN,
           light_belt::crc32Ethernet(raw, len - light_belt::UDP_V3_CRC_LEN));
}

size_t makeFrame(
    uint8_t *raw,
    uint8_t node_id,
    uint32_t sequence,
    const light_belt::OutputDescriptor *outputs,
    uint8_t output_count,
    uint64_t apply_at_us = 0,
    uint8_t flags = 0) {
  memset(raw, 0, light_belt::UDP_V3_MAX_PACKET_LEN);
  writeU16(raw, light_belt::UDP_V3_MAGIC);
  raw[2] = light_belt::UDP_V3_VERSION;
  raw[3] = light_belt::UDP_V3_MESSAGE_FRAME;
  raw[4] = node_id;
  raw[5] = static_cast<uint8_t>(
      flags | (apply_at_us == 0 ? 0 :
          light_belt::UDP_V3_FLAG_SCHEDULED_APPLY));
  writeU32(raw + 6, sequence);
  writeU64(raw + 18, apply_at_us);
  raw[26] = output_count;
  size_t cursor = light_belt::UDP_V3_HEADER_LEN;
  for (uint8_t output = 0; output < output_count; ++output) {
    raw[cursor] = outputs[output].output_id;
    raw[cursor + 1] = outputs[output].gpio;
    writeU16(raw + cursor + 2, outputs[output].pixel_count);
    writeU16(raw + cursor + 4, outputs[output].pixel_count * 3U);
    cursor += light_belt::UDP_V3_OUTPUT_DESCRIPTOR_LEN;
    for (uint16_t pixel = 0; pixel < outputs[output].pixel_count; ++pixel) {
      raw[cursor++] = static_cast<uint8_t>(10 * outputs[output].output_id + pixel);
      raw[cursor++] = static_cast<uint8_t>(20 * outputs[output].output_id + pixel);
      raw[cursor++] = static_cast<uint8_t>(30 * outputs[output].output_id + pixel);
    }
  }
  writeU16(raw + 27, static_cast<uint16_t>(cursor - light_belt::UDP_V3_HEADER_LEN));
  const size_t len = cursor + light_belt::UDP_V3_CRC_LEN;
  repairCrc(raw, len);
  return len;
}

void makeClockBeacon(
    uint8_t *raw,
    uint32_t beacon_sequence,
    uint64_t host_monotonic_us) {
  memset(raw, 0, light_belt::UDP_V3_CLOCK_BEACON_LEN);
  writeU16(raw, light_belt::UDP_V3_MAGIC);
  raw[2] = light_belt::UDP_V3_VERSION;
  raw[3] = light_belt::UDP_V3_MESSAGE_CLOCK_BEACON;
  writeU32(raw + 4, beacon_sequence);
  writeU64(raw + 8, host_monotonic_us);
  repairCrc(raw, light_belt::UDP_V3_CLOCK_BEACON_LEN);
}

light_belt::UdpV3Frame parse(
    const uint8_t *raw,
    size_t len,
    uint8_t node_id,
    const light_belt::OutputDescriptor *outputs,
    uint8_t output_count) {
  light_belt::UdpV3Frame frame{};
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::Ok),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, len, node_id, outputs, output_count, &frame)));
  return frame;
}

light_belt::OwnedNodeFrame own(
    const light_belt::UdpV3Frame &frame,
    const light_belt::OutputDescriptor *outputs,
    uint8_t output_count) {
  light_belt::OwnedNodeFrame owned{};
  TEST_ASSERT_TRUE(light_belt::copyUdpV3Frame(
      frame, outputs, output_count, &owned));
  return owned;
}

light_belt::OwnedNodeFrame makeEmergencyFrame(uint32_t sequence = 1) {
  light_belt::OwnedNodeFrame frame{};
  frame.node_id = 2;
  frame.sequence = sequence;
  frame.output_count = 1;
  frame.outputs[0].descriptor = {1, 4, 10};
  return frame;
}

uint8_t encodedPair(uint8_t source, uint8_t pair) {
  const uint8_t high_bit = static_cast<uint8_t>(7U - pair * 2U);
  const uint8_t low_bit = static_cast<uint8_t>(high_bit - 1U);
  const uint8_t high = (source & (1U << high_bit)) != 0 ? 0x0C : 0x08;
  const uint8_t low = (source & (1U << low_bit)) != 0 ? 0x0C : 0x08;
  return static_cast<uint8_t>((high << 4) | low);
}

void assertEncodedByte(
    const uint8_t *encoded, size_t offset, uint8_t source) {
  for (uint8_t pair = 0; pair < 4; ++pair) {
    TEST_ASSERT_EQUAL_HEX8(encodedPair(source, pair), encoded[offset + pair]);
  }
}

void assertParallelEncodedChannel(
    const uint8_t *encoded,
    size_t offset,
    uint8_t active_lane_mask,
    uint8_t lane_bit,
    uint8_t source) {
  for (uint8_t bit_index = 0; bit_index < 8; ++bit_index) {
    const uint8_t source_bit = static_cast<uint8_t>(7U - bit_index);
    const uint8_t one_lane_mask =
        (source & (1U << source_bit)) != 0 ? lane_bit : 0;
    TEST_ASSERT_EQUAL_HEX8(
        static_cast<uint8_t>((active_lane_mask << 4) | one_lane_mask),
        encoded[offset + bit_index * 2U]);
    TEST_ASSERT_EQUAL_HEX8(0, encoded[offset + bit_index * 2U + 1U]);
  }
}

void assertRmtEncodedByte(
    const light_belt::Ws2811RmtPulse *encoded,
    size_t offset,
    uint8_t source) {
  for (uint8_t bit_index = 0; bit_index < 8; ++bit_index) {
    const uint8_t source_bit = static_cast<uint8_t>(7U - bit_index);
    const bool one = (source & (1U << source_bit)) != 0;
    TEST_ASSERT_EQUAL_UINT16(
        one ? light_belt::WS2811_RMT_ONE_HIGH_TICKS
            : light_belt::WS2811_RMT_ZERO_HIGH_TICKS,
        encoded[offset + bit_index].high_ticks);
    TEST_ASSERT_EQUAL_UINT16(
        one ? light_belt::WS2811_RMT_ONE_LOW_TICKS
            : light_belt::WS2811_RMT_ZERO_LOW_TICKS,
        encoded[offset + bit_index].low_ticks);
  }
}

void test_udp_v3_immediate_and_scheduled_frames_are_unambiguous() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  size_t len = makeFrame(raw, 2, 1, kOneOutput, 1);
  light_belt::UdpV3Frame frame = parse(raw, len, 2, kOneOutput, 1);
  TEST_ASSERT_EQUAL_UINT64(0, frame.apply_at_us);
  TEST_ASSERT_EQUAL_UINT8(0, frame.flags);

  len = makeFrame(
      raw, 2, 2, kOneOutput, 1, 123456,
      light_belt::UDP_V3_FLAG_KEY_FRAME);
  frame = parse(raw, len, 2, kOneOutput, 1);
  TEST_ASSERT_EQUAL_UINT64(123456, frame.apply_at_us);
  TEST_ASSERT_EQUAL_UINT8(
      light_belt::UDP_V3_FLAG_KEY_FRAME |
          light_belt::UDP_V3_FLAG_SCHEDULED_APPLY,
      frame.flags);

  raw[5] = static_cast<uint8_t>(
      raw[5] & ~light_belt::UDP_V3_FLAG_SCHEDULED_APPLY);
  repairCrc(raw, len);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::BadSchedule),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, len, 2, kOneOutput, 1, &frame)));

  len = makeFrame(raw, 2, 3, kOneOutput, 1);
  raw[5] = light_belt::UDP_V3_FLAG_SCHEDULED_APPLY;
  repairCrc(raw, len);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::BadSchedule),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, len, 2, kOneOutput, 1, &frame)));
}

void test_udp_v3_clock_beacon_has_fixed_broadcast_wire_contract() {
  uint8_t raw[light_belt::UDP_V3_CLOCK_BEACON_LEN] = {};
  makeClockBeacon(raw, 0x01020304, 0x0102030405060708ULL);

  TEST_ASSERT_EQUAL_UINT32(20, light_belt::UDP_V3_CLOCK_BEACON_LEN);
  TEST_ASSERT_EQUAL_HEX8(0x02, raw[3]);
  light_belt::UdpV3ClockBeacon beacon{};
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ClockBeaconParseResult::Ok),
      static_cast<int>(light_belt::parseUdpV3ClockBeacon(
          raw, sizeof(raw), &beacon)));
  TEST_ASSERT_EQUAL_HEX32(0x01020304, beacon.beacon_sequence);
  TEST_ASSERT_EQUAL_UINT64(
      0x0102030405060708ULL, beacon.host_monotonic_us);

  // There is deliberately no node field or expected-node parser argument;
  // the same fixed packet is accepted by every node listening on the port.
  TEST_ASSERT_EQUAL_HEX8(0x01, raw[4]);
  TEST_ASSERT_EQUAL_HEX8(0x02, raw[5]);
}

void test_udp_v3_clock_beacon_rejects_length_header_and_crc_errors() {
  uint8_t raw[light_belt::UDP_V3_CLOCK_BEACON_LEN + 1] = {};
  makeClockBeacon(raw, 7, 9000000);
  light_belt::UdpV3ClockBeacon unchanged{0xAABBCCDD, 0x1122334455667788ULL};

  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ClockBeaconParseResult::BadLength),
      static_cast<int>(light_belt::parseUdpV3ClockBeacon(
          nullptr, light_belt::UDP_V3_CLOCK_BEACON_LEN, &unchanged)));
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ClockBeaconParseResult::BadLength),
      static_cast<int>(light_belt::parseUdpV3ClockBeacon(
          raw, light_belt::UDP_V3_CLOCK_BEACON_LEN - 1, &unchanged)));
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ClockBeaconParseResult::BadLength),
      static_cast<int>(light_belt::parseUdpV3ClockBeacon(
          raw, sizeof(raw), &unchanged)));

  raw[0] ^= 1;
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ClockBeaconParseResult::BadMagic),
      static_cast<int>(light_belt::parseUdpV3ClockBeacon(
          raw, light_belt::UDP_V3_CLOCK_BEACON_LEN, &unchanged)));
  raw[0] ^= 1;
  raw[2] = 4;
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ClockBeaconParseResult::BadVersion),
      static_cast<int>(light_belt::parseUdpV3ClockBeacon(
          raw, light_belt::UDP_V3_CLOCK_BEACON_LEN, &unchanged)));
  raw[2] = light_belt::UDP_V3_VERSION;
  raw[3] = light_belt::UDP_V3_MESSAGE_FRAME;
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ClockBeaconParseResult::BadMessageType),
      static_cast<int>(light_belt::parseUdpV3ClockBeacon(
          raw, light_belt::UDP_V3_CLOCK_BEACON_LEN, &unchanged)));
  raw[3] = light_belt::UDP_V3_MESSAGE_CLOCK_BEACON;
  raw[8] ^= 1;
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ClockBeaconParseResult::BadCrc),
      static_cast<int>(light_belt::parseUdpV3ClockBeacon(
          raw, light_belt::UDP_V3_CLOCK_BEACON_LEN, &unchanged)));
  TEST_ASSERT_EQUAL_HEX32(0xAABBCCDD, unchanged.beacon_sequence);
  TEST_ASSERT_EQUAL_UINT64(
      0x1122334455667788ULL, unchanged.host_monotonic_us);
}

void test_presentation_clock_uses_window_minimum_and_spread() {
  light_belt::PresentationClockConfig config;
  config.window_size = 3;
  config.min_samples = 3;
  config.max_uncertainty_us = 1000;
  light_belt::PresentationClock clock(config);

  TEST_ASSERT_TRUE(clock.configurationValid());
  TEST_ASSERT_TRUE(clock.observeBeacon(1, 10000, 11200));
  TEST_ASSERT_TRUE(clock.observeBeacon(2, 20000, 21000));
  TEST_ASSERT_TRUE(clock.observeBeacon(3, 30000, 31400));
  TEST_ASSERT_EQUAL_INT64(1000, clock.offsetUs());
  TEST_ASSERT_EQUAL_UINT64(400, clock.uncertaintyUs());
  TEST_ASSERT_EQUAL_UINT8(3, clock.sampleCount());
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Ready),
      static_cast<int>(clock.status(31400)));

  TEST_ASSERT_TRUE(clock.observeBeacon(4, 40000, 41300));
  TEST_ASSERT_TRUE(clock.observeBeacon(5, 50000, 51250));
  TEST_ASSERT_EQUAL_INT64(1250, clock.offsetUs());
  TEST_ASSERT_EQUAL_UINT64(150, clock.uncertaintyUs());
  TEST_ASSERT_EQUAL_UINT8(3, clock.sampleCount());
}

void test_presentation_clock_lower_envelope_ignores_slow_outliers() {
  light_belt::PresentationClockConfig config;
  config.window_size = 8;
  config.min_samples = 3;
  config.max_uncertainty_us = 100;
  light_belt::PresentationClock clock(config);

  const int64_t offsets[] = {
      1000, 1050, 53000, 1040, 52000, 1070, 54000, 1080,
  };
  for (uint32_t index = 0; index < 8; ++index) {
    const uint64_t host_us = static_cast<uint64_t>(index + 1U) * 100000U;
    TEST_ASSERT_TRUE(clock.observeBeacon(
        index + 1U, host_us,
        host_us + static_cast<uint64_t>(offsets[index])));
  }

  TEST_ASSERT_EQUAL_INT64(1000, clock.offsetUs());
  TEST_ASSERT_EQUAL_UINT64(50, clock.uncertaintyUs());
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Ready),
      static_cast<int>(clock.status(801080)));

  clock.reset();
  TEST_ASSERT_TRUE(clock.observeBeacon(1, 100000, 101000));
  TEST_ASSERT_TRUE(clock.observeBeacon(2, 200000, 252000));
  TEST_ASSERT_TRUE(clock.observeBeacon(3, 300000, 353000));
  TEST_ASSERT_EQUAL_INT64(1000, clock.offsetUs());
  TEST_ASSERT_EQUAL_UINT64(52000, clock.uncertaintyUs());
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Uncertain),
      static_cast<int>(clock.status(353000)));
}

void test_default_presentation_clock_uses_bounded_32_sample_window() {
  light_belt::PresentationClock clock;

  // Three low-delay samples form a stable lower-envelope quorum even when
  // most of the 32-sample Wi-Fi window consists of temporary slow packets.
  for (uint32_t index = 0; index < 32; ++index) {
    const uint64_t host_us = static_cast<uint64_t>(index + 1U) * 100000U;
    const uint64_t offset_us =
        index == 0 ? 1000U : index == 10 ? 1100U : index == 20 ? 1200U
                                                         : 50000U + index;
    TEST_ASSERT_TRUE(clock.observeBeacon(
        index + 1U, host_us, host_us + offset_us));
  }

  TEST_ASSERT_EQUAL_UINT8(32, clock.sampleCount());
  TEST_ASSERT_EQUAL_INT64(1000, clock.offsetUs());
  TEST_ASSERT_EQUAL_UINT64(200, clock.uncertaintyUs());
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Ready),
      static_cast<int>(clock.status(3250031)));

  // A full new window must evict every old lower-envelope sample. This keeps
  // the estimator robust without pinning its offset to historical latency.
  for (uint32_t index = 0; index < 32; ++index) {
    const uint64_t host_us = static_cast<uint64_t>(index + 33U) * 100000U;
    const uint64_t offset_us = 20000U + (index % 3U) * 100U;
    TEST_ASSERT_TRUE(clock.observeBeacon(
        index + 33U, host_us, host_us + offset_us));
  }

  TEST_ASSERT_EQUAL_UINT8(32, clock.sampleCount());
  TEST_ASSERT_EQUAL_INT64(20000, clock.offsetUs());
  TEST_ASSERT_EQUAL_UINT64(0, clock.uncertaintyUs());
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Ready),
      static_cast<int>(clock.status(6420100)));
}

void test_presentation_clock_readiness_checks_samples_age_and_uncertainty() {
  light_belt::PresentationClockConfig config;
  config.window_size = 3;
  config.min_samples = 3;
  config.max_age_us = 1000;
  config.max_uncertainty_us = 50;
  light_belt::PresentationClock clock(config);

  TEST_ASSERT_TRUE(clock.observeBeacon(1, 10000, 10100));
  TEST_ASSERT_EQUAL(
      static_cast<int>(
          light_belt::PresentationClockStatus::InsufficientSamples),
      static_cast<int>(clock.status(10100)));
  const light_belt::ApplyDeadline not_ready =
      clock.evaluateDeadline(11000, 10100);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ApplyDeadlineResult::ClockNotReady),
      static_cast<int>(not_ready.result));
  TEST_ASSERT_EQUAL(
      static_cast<int>(
          light_belt::PresentationClockStatus::InsufficientSamples),
      static_cast<int>(not_ready.clock_status));
  TEST_ASSERT_TRUE(clock.observeBeacon(2, 10500, 10700));
  TEST_ASSERT_TRUE(clock.observeBeacon(3, 11000, 11120));
  TEST_ASSERT_EQUAL_UINT64(100, clock.uncertaintyUs());
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Uncertain),
      static_cast<int>(clock.status(11120)));
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Stale),
      static_cast<int>(clock.status(12121)));
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Stale),
      static_cast<int>(clock.status(11119)));

  config.min_samples = 4;
  light_belt::PresentationClock invalid(config);
  TEST_ASSERT_FALSE(invalid.configurationValid());
  TEST_ASSERT_FALSE(invalid.observeBeacon(1, 1, 1));
  TEST_ASSERT_EQUAL(
      static_cast<int>(
          light_belt::PresentationClockStatus::InvalidConfiguration),
      static_cast<int>(invalid.status(1)));
}

void test_presentation_clock_accepts_zero_policy_tolerances() {
  light_belt::PresentationClockConfig config;
  config.window_size = 1;
  config.min_samples = 1;
  config.max_age_us = 0;
  config.max_uncertainty_us = 0;
  config.late_tolerance_us = 0;
  config.max_future_us = 0;
  light_belt::PresentationClock clock(config);

  TEST_ASSERT_TRUE(clock.configurationValid());
  TEST_ASSERT_TRUE(clock.observeBeacon(1, 1000, 1000));
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Ready),
      static_cast<int>(clock.status(1000)));
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ApplyDeadlineResult::Ok),
      static_cast<int>(clock.evaluateDeadline(1000, 1000).result));
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ApplyDeadlineResult::TooFar),
      static_cast<int>(clock.evaluateDeadline(1001, 1000).result));
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::PresentationClockStatus::Stale),
      static_cast<int>(clock.status(1001)));
}

void test_presentation_clock_orders_by_host_time_and_reacquires_after_expiry() {
  light_belt::PresentationClockConfig config;
  config.window_size = 3;
  config.min_samples = 2;
  config.max_age_us = 15000;
  light_belt::PresentationClock clock(config);

  TEST_ASSERT_TRUE(clock.observeBeacon(100, 10000, 11000));
  // Host process restart: sequence restarts, but monotonic time continues.
  TEST_ASSERT_TRUE(clock.observeBeacon(1, 20000, 21100));
  TEST_ASSERT_EQUAL_UINT32(1, clock.lastBeaconSequence());
  TEST_ASSERT_FALSE(clock.observeBeacon(2, 19000, 22000));
  TEST_ASSERT_FALSE(clock.observeBeacon(2, 20000, 22000));
  TEST_ASSERT_EQUAL_UINT8(2, clock.sampleCount());

  // Host-machine restart: only a stale clock may accept the smaller epoch.
  TEST_ASSERT_TRUE(clock.observeBeacon(1, 100, 40001));
  TEST_ASSERT_EQUAL_UINT8(1, clock.sampleCount());
  TEST_ASSERT_EQUAL_UINT64(100, clock.lastHostMonotonicUs());
  TEST_ASSERT_EQUAL_UINT64(40001, clock.lastLocalReceiveUs());
  TEST_ASSERT_EQUAL_INT64(39901, clock.offsetUs());
  TEST_ASSERT_EQUAL(
      static_cast<int>(
          light_belt::PresentationClockStatus::InsufficientSamples),
      static_cast<int>(clock.status(40001)));
}

void test_presentation_clock_deadline_boundaries_are_explicit() {
  light_belt::PresentationClockConfig config;
  config.window_size = 3;
  config.min_samples = 3;
  config.max_uncertainty_us = 1000;
  config.late_tolerance_us = 2000;
  config.max_future_us = 100000;
  light_belt::PresentationClock clock(config);
  TEST_ASSERT_TRUE(clock.observeBeacon(1, 100000, 101200));
  TEST_ASSERT_TRUE(clock.observeBeacon(2, 200000, 201000));
  TEST_ASSERT_TRUE(clock.observeBeacon(3, 300000, 301400));

  light_belt::ApplyDeadline deadline = clock.evaluateDeadline(450000, 400000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ApplyDeadlineResult::Ok),
      static_cast<int>(deadline.result));
  TEST_ASSERT_EQUAL_UINT64(451000, deadline.local_deadline_us);

  deadline = clock.evaluateDeadline(397000, 400000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ApplyDeadlineResult::Ok),
      static_cast<int>(deadline.result));
  TEST_ASSERT_EQUAL_UINT64(398000, deadline.local_deadline_us);
  deadline = clock.evaluateDeadline(396999, 400000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ApplyDeadlineResult::TooLate),
      static_cast<int>(deadline.result));

  deadline = clock.evaluateDeadline(499000, 400000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ApplyDeadlineResult::Ok),
      static_cast<int>(deadline.result));
  deadline = clock.evaluateDeadline(499001, 400000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ApplyDeadlineResult::TooFar),
      static_cast<int>(deadline.result));

  deadline = clock.evaluateDeadline(0, 400000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ApplyDeadlineResult::InvalidApplyTime),
      static_cast<int>(deadline.result));
}

void test_presentation_clock_rejects_unrepresentable_offsets_and_deadlines() {
  light_belt::PresentationClock clock;
  TEST_ASSERT_FALSE(clock.observeBeacon(1, UINT64_MAX, 0));
  TEST_ASSERT_EQUAL_UINT8(0, clock.sampleCount());

  TEST_ASSERT_TRUE(clock.observeBeacon(1, 10000, 11000));
  TEST_ASSERT_TRUE(clock.observeBeacon(2, 20000, 21000));
  TEST_ASSERT_TRUE(clock.observeBeacon(3, 30000, 31000));
  const light_belt::ApplyDeadline overflow =
      clock.evaluateDeadline(UINT64_MAX, 31000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(
          light_belt::ApplyDeadlineResult::ConversionOutOfRange),
      static_cast<int>(overflow.result));

  light_belt::PresentationClock negative;
  TEST_ASSERT_TRUE(negative.observeBeacon(1, 10000, 9000));
  TEST_ASSERT_TRUE(negative.observeBeacon(2, 20000, 19000));
  TEST_ASSERT_TRUE(negative.observeBeacon(3, 30000, 29000));
  const light_belt::ApplyDeadline underflow =
      negative.evaluateDeadline(500, 29000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(
          light_belt::ApplyDeadlineResult::ConversionOutOfRange),
      static_cast<int>(underflow.result));
}

void test_transmit_start_compensates_wire_time_and_rejects_late_frames() {
  light_belt::TransmitStart start = light_belt::calculateTransmitStart(
      10000, 1360, 8000, 2000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::TransmitStartResult::Ok),
      static_cast<int>(start.result));
  TEST_ASSERT_EQUAL_UINT64(8640, start.local_start_us);
  TEST_ASSERT_EQUAL_UINT64(0, start.start_lateness_us);

  start = light_belt::calculateTransmitStart(10000, 1360, 9000, 2000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::TransmitStartResult::Ok),
      static_cast<int>(start.result));
  TEST_ASSERT_EQUAL_UINT64(360, start.start_lateness_us);

  start = light_belt::calculateTransmitStart(10000, 1360, 10641, 2000);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::TransmitStartResult::TooLate),
      static_cast<int>(start.result));
  TEST_ASSERT_EQUAL_UINT64(2001, start.start_lateness_us);

  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::TransmitStartResult::InvalidWireTime),
      static_cast<int>(
          light_belt::calculateTransmitStart(10000, 0, 0, 2000).result));
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::TransmitStartResult::DeadlineUnderflow),
      static_cast<int>(
          light_belt::calculateTransmitStart(1000, 1360, 0, 2000).result));
}

void test_runtime_scheduling_stats_are_independent_and_zero_initialized() {
  light_belt::RuntimeStats stats;
  TEST_ASSERT_EQUAL_UINT32(0, stats.clock_beacons_received.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.clock_beacons_accepted.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.clock_beacons_rejected.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.clock_samples.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.clock_uncertainty_us.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.clock_ready.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.scheduled_queued.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.scheduled_committed.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.scheduled_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.clock_not_ready_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.scheduled_too_late_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.scheduled_too_far_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.scheduled_invalid_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.scheduled_start_late_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.scheduled_cancelled.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.session_key_duplicates.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.immediate_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.identical_skipped.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.physical_offset_waits.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.physical_offset_cancelled.load());
  TEST_ASSERT_EQUAL_UINT32(0, stats.emergency_payload_rejected.load());
  TEST_ASSERT_EQUAL_INT32(0, stats.last_deadline_error_us.load());

  stats.clock_beacons_received.fetch_add(3);
  stats.clock_beacons_accepted.fetch_add(2);
  stats.clock_beacons_rejected.fetch_add(1);
  stats.clock_samples.store(8);
  stats.clock_uncertainty_us.store(250);
  stats.clock_ready.store(1);
  stats.scheduled_queued.fetch_add(10);
  stats.scheduled_committed.fetch_add(6);
  stats.scheduled_dropped.fetch_add(4);
  stats.clock_not_ready_dropped.fetch_add(1);
  stats.scheduled_too_late_dropped.fetch_add(1);
  stats.scheduled_too_far_dropped.fetch_add(1);
  stats.scheduled_invalid_dropped.fetch_add(1);
  stats.scheduled_start_late_dropped.fetch_add(2);
  stats.scheduled_cancelled.fetch_add(3);
  stats.session_key_duplicates.fetch_add(4);
  stats.immediate_dropped.fetch_add(5);
  stats.identical_skipped.fetch_add(6);
  stats.physical_offset_waits.fetch_add(8);
  stats.physical_offset_cancelled.fetch_add(9);
  stats.emergency_payload_rejected.fetch_add(7);
  stats.last_deadline_error_us.store(-17);

  TEST_ASSERT_EQUAL_UINT32(3, stats.clock_beacons_received.load());
  TEST_ASSERT_EQUAL_UINT32(2, stats.clock_beacons_accepted.load());
  TEST_ASSERT_EQUAL_UINT32(1, stats.clock_beacons_rejected.load());
  TEST_ASSERT_EQUAL_UINT32(8, stats.clock_samples.load());
  TEST_ASSERT_EQUAL_UINT32(250, stats.clock_uncertainty_us.load());
  TEST_ASSERT_EQUAL_UINT32(1, stats.clock_ready.load());
  TEST_ASSERT_EQUAL_UINT32(10, stats.scheduled_queued.load());
  TEST_ASSERT_EQUAL_UINT32(6, stats.scheduled_committed.load());
  TEST_ASSERT_EQUAL_UINT32(4, stats.scheduled_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(1, stats.clock_not_ready_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(1, stats.scheduled_too_late_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(1, stats.scheduled_too_far_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(1, stats.scheduled_invalid_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(2, stats.scheduled_start_late_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(3, stats.scheduled_cancelled.load());
  TEST_ASSERT_EQUAL_UINT32(4, stats.session_key_duplicates.load());
  TEST_ASSERT_EQUAL_UINT32(5, stats.immediate_dropped.load());
  TEST_ASSERT_EQUAL_UINT32(6, stats.identical_skipped.load());
  TEST_ASSERT_EQUAL_UINT32(8, stats.physical_offset_waits.load());
  TEST_ASSERT_EQUAL_UINT32(9, stats.physical_offset_cancelled.load());
  TEST_ASSERT_EQUAL_UINT32(7, stats.emergency_payload_rejected.load());
  TEST_ASSERT_EQUAL_INT32(-17, stats.last_deadline_error_us.load());
}

void test_node2_emergency_whitelist_accepts_only_exact_full_frames() {
  light_belt::OwnedNodeFrame frame = makeEmergencyFrame();
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyFrameAllowed(frame));

  for (uint8_t group = 1; group < 10; ++group) {
    frame.outputs[0].pixels[group] = {0x20, 0x08, 0x00};
  }
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyFrameAllowed(frame));

  for (uint8_t group = 1; group < 10; ++group) {
    frame.outputs[0].pixels[group] = {0x20, 0x10, 0x00};
  }
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyFrameAllowed(frame));

  frame = makeEmergencyFrame();
  frame.outputs[0].pixels[1] = {0x00, 0x00, 0x20};
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyFrameAllowed(frame));
  frame.outputs[0].pixels[1] = {0x20, 0x08, 0x00};
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyFrameAllowed(frame));

  frame.outputs[0].pixels[2] = {0x20, 0x08, 0x00};
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyFrameAllowed(frame));
  frame = makeEmergencyFrame();
  frame.outputs[0].pixels[0] = {0x00, 0x00, 0x20};
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyFrameAllowed(frame));
  frame = makeEmergencyFrame();
  frame.outputs[0].pixels[1] = {0x20, 0x04, 0x00};
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyFrameAllowed(frame));
  frame = makeEmergencyFrame();
  frame.flags = light_belt::UDP_V3_FLAG_SCHEDULED_APPLY;
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyFrameAllowed(frame));
  frame = makeEmergencyFrame();
  frame.flags = light_belt::UDP_V3_FLAG_SAFE_STATE;
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyFrameAllowed(frame));
  frame.outputs[0].pixels[1] = {0x20, 0x08, 0x00};
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyFrameAllowed(frame));
  frame = makeEmergencyFrame();
  frame.outputs[0].descriptor.pixel_count = 9;
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyFrameAllowed(frame));
  frame = makeEmergencyFrame();
  frame.node_id = 8;
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyFrameAllowed(frame));
}

void test_identical_physical_payload_skip_requires_success_cache_and_no_recovery() {
  light_belt::OwnedNodeFrame physical = makeEmergencyFrame(10);
  for (uint8_t group = 1; group < 10; ++group) {
    physical.outputs[0].pixels[group] = {0x20, 0x08, 0x00};
  }
  light_belt::OwnedNodeFrame candidate = physical;
  candidate.sequence = 11;
  candidate.media_timestamp_us = 123456;
  candidate.apply_at_us = 654321;
  candidate.flags = light_belt::UDP_V3_FLAG_KEY_FRAME;

  TEST_ASSERT_TRUE(
      light_belt::physicalPixelPayloadsEqual(candidate, physical));
  TEST_ASSERT_FALSE(light_belt::canSkipPhysicalRefresh(
      candidate, physical, false, false));
  TEST_ASSERT_FALSE(light_belt::canSkipPhysicalRefresh(
      candidate, physical, true, true));
  TEST_ASSERT_FALSE(light_belt::canSkipPhysicalRefresh(
      candidate, physical, true, false));
  candidate.flags = 0;
  TEST_ASSERT_TRUE(light_belt::canSkipPhysicalRefresh(
      candidate, physical, true, false));
  TEST_ASSERT_TRUE(light_belt::canSkipContentDedupeRefresh(
      candidate, physical, true, false));
  candidate.flags = light_belt::UDP_V3_FLAG_SAFE_STATE;
  TEST_ASSERT_TRUE(light_belt::canSkipPhysicalRefresh(
      candidate, physical, true, false));
  TEST_ASSERT_FALSE(light_belt::canSkipContentDedupeRefresh(
      candidate, physical, true, false));
  candidate.flags = 0;

  candidate.outputs[0].pixels[9].g = 0x10;
  TEST_ASSERT_FALSE(
      light_belt::physicalPixelPayloadsEqual(candidate, physical));
  TEST_ASSERT_FALSE(light_belt::canSkipPhysicalRefresh(
      candidate, physical, true, false));
  candidate = physical;
  candidate.outputs[0].descriptor.gpio = 5;
  TEST_ASSERT_FALSE(
      light_belt::physicalPixelPayloadsEqual(candidate, physical));
}

void test_node2_emergency_transition_graph_and_change_interval() {
  light_belt::OwnedNodeFrame black = makeEmergencyFrame();
  light_belt::OwnedNodeFrame warm_low = makeEmergencyFrame();
  light_belt::OwnedNodeFrame warm_high = makeEmergencyFrame();
  for (uint8_t group = 1; group < 10; ++group) {
    warm_low.outputs[0].pixels[group] = {0x20, 0x08, 0x00};
    warm_high.outputs[0].pixels[group] = {0x20, 0x10, 0x00};
  }
  light_belt::OwnedNodeFrame blue0 = makeEmergencyFrame();
  light_belt::OwnedNodeFrame blue1 = makeEmergencyFrame();
  light_belt::OwnedNodeFrame blue8 = makeEmergencyFrame();
  blue0.outputs[0].pixels[1] = {0x00, 0x00, 0x20};
  blue1.outputs[0].pixels[2] = {0x00, 0x00, 0x20};
  blue8.outputs[0].pixels[9] = {0x00, 0x00, 0x20};

  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      black, warm_low));
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyTransitionAllowed(
      black, warm_high));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      warm_low, warm_high));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      warm_high, warm_low));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      warm_low, black));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      black, blue0));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      blue0, blue1));
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyTransitionAllowed(
      blue0, blue8));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      blue8, blue0));

  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyChangeIntervalAllowed(
      1000, 1100, true, false));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyChangeIntervalAllowed(
      1000, 1150, true, false));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyChangeIntervalAllowed(
      1000, 1001, false, false));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyChangeIntervalAllowed(
      1000, 1001, true, true));
}

void test_node2_emergency_gate1m_payloads_and_edges() {
  light_belt::OwnedNodeFrame black = makeEmergencyFrame();
  light_belt::OwnedNodeFrame green_uniform = makeEmergencyFrame();
  for (uint8_t group = 1; group < 10; ++group) {
    green_uniform.outputs[0].pixels[group] = {0x00, 0x20, 0x00};
  }
  TEST_ASSERT_TRUE(
      light_belt::isNode2EmergencyFrameAllowed(green_uniform));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      black, green_uniform));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      green_uniform, black));

  light_belt::OwnedNodeFrame green0 = makeEmergencyFrame();
  light_belt::OwnedNodeFrame green1 = makeEmergencyFrame();
  green0.outputs[0].pixels[1] = {0x00, 0x20, 0x00};
  green1.outputs[0].pixels[2] = {0x00, 0x20, 0x00};
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      black, green0));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      green0, green1));
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyTransitionAllowed(
      green1, green_uniform));

  light_belt::OwnedNodeFrame phases[3] = {
      makeEmergencyFrame(), makeEmergencyFrame(), makeEmergencyFrame()};
  for (uint8_t phase = 0; phase < 3; ++phase) {
    for (uint8_t position = phase; position < 9; position += 3) {
      phases[phase].outputs[0].pixels[position + 1U] = {0x00, 0x00, 0x20};
    }
    TEST_ASSERT_TRUE(light_belt::isNode2EmergencyFrameAllowed(phases[phase]));
  }
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      black, phases[0]));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      phases[0], phases[1]));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      phases[1], phases[2]));
  TEST_ASSERT_TRUE(light_belt::isNode2EmergencyTransitionAllowed(
      phases[2], phases[0]));
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyTransitionAllowed(
      phases[0], phases[2]));
  phases[0].outputs[0].pixels[2] = {0x00, 0x00, 0x20};
  TEST_ASSERT_FALSE(light_belt::isNode2EmergencyFrameAllowed(phases[0]));
}

void test_node8_emergency_policy_requires_exact20_and_usable19_graph() {
  const light_belt::EmergencyOutputPolicy node8_policy = {8, {1, 4, 20}};
  light_belt::OwnedNodeFrame black = makeEmergencyFrame();
  black.node_id = 8;
  black.outputs[0].descriptor.pixel_count = 20;

  TEST_ASSERT_TRUE(light_belt::isEmergencyFrameAllowed(black, node8_policy));
  TEST_ASSERT_FALSE(light_belt::isEmergencyFrameAllowed(
      black, light_belt::kNode2EmergencyTestPolicy));
  light_belt::OwnedNodeFrame wrong_length = black;
  wrong_length.outputs[0].descriptor.pixel_count = 19;
  TEST_ASSERT_FALSE(
      light_belt::isEmergencyFrameAllowed(wrong_length, node8_policy));

  light_belt::OwnedNodeFrame blue18 = black;
  light_belt::OwnedNodeFrame blue0 = black;
  light_belt::OwnedNodeFrame blue17 = black;
  blue18.outputs[0].pixels[19] = {0x00, 0x00, 0x20};
  blue0.outputs[0].pixels[1] = {0x00, 0x00, 0x20};
  blue17.outputs[0].pixels[18] = {0x00, 0x00, 0x20};
  TEST_ASSERT_TRUE(light_belt::isEmergencyTransitionAllowed(
      black, blue0, node8_policy));
  TEST_ASSERT_TRUE(light_belt::isEmergencyTransitionAllowed(
      blue18, blue0, node8_policy));
  TEST_ASSERT_FALSE(light_belt::isEmergencyTransitionAllowed(
      blue17, blue0, node8_policy));

  light_belt::OwnedNodeFrame phases[3] = {black, black, black};
  const uint8_t expected_counts[3] = {7, 6, 6};
  for (uint8_t phase = 0; phase < 3; ++phase) {
    uint8_t count = 0;
    for (uint8_t position = phase; position < 19; position += 3) {
      phases[phase].outputs[0].pixels[position + 1U] = {0x00, 0x00, 0x20};
      ++count;
    }
    TEST_ASSERT_EQUAL_UINT8(expected_counts[phase], count);
    TEST_ASSERT_TRUE(
        light_belt::isEmergencyFrameAllowed(phases[phase], node8_policy));
  }
  TEST_ASSERT_TRUE(light_belt::isEmergencyTransitionAllowed(
      black, phases[0], node8_policy));
  TEST_ASSERT_TRUE(light_belt::isEmergencyTransitionAllowed(
      phases[0], phases[1], node8_policy));
  TEST_ASSERT_TRUE(light_belt::isEmergencyTransitionAllowed(
      phases[1], phases[2], node8_policy));
  TEST_ASSERT_TRUE(light_belt::isEmergencyTransitionAllowed(
      phases[2], phases[0], node8_policy));
  TEST_ASSERT_FALSE(light_belt::isEmergencyTransitionAllowed(
      phases[0], phases[2], node8_policy));
}

void test_identical_logical_commit_advances_sequence_and_watchdog() {
  light_belt::OwnedNodeFrame physical = makeEmergencyFrame(1);
  for (uint8_t group = 1; group < 10; ++group) {
    physical.outputs[0].pixels[group] = {0x20, 0x08, 0x00};
  }
  const light_belt::OutputDescriptor output = {1, 4, 10};
  light_belt::MultiOutputFrameState state(&output, 1);
  TEST_ASSERT_TRUE(state.commitFrame(physical, 100));

  light_belt::OwnedNodeFrame candidate = physical;
  candidate.sequence = 2;
  TEST_ASSERT_TRUE(light_belt::canSkipPhysicalRefresh(
      candidate, physical, true, false));
  TEST_ASSERT_TRUE(state.commitFrame(candidate, 900));
  TEST_ASSERT_EQUAL_UINT32(2, state.lastSequence());
  TEST_ASSERT_EQUAL_UINT32(2, state.refreshCount());
  TEST_ASSERT_FALSE(state.timedOut(1900, 1000));
  TEST_ASSERT_TRUE(state.timedOut(1901, 1000));
}

void test_scheduled_udp_v3_golden_vector_preserves_apply_deadline() {
  const light_belt::UdpV3Frame frame = parse(
      UDP_V3_GOLDEN_1, UDP_V3_GOLDEN_1_len, 8,
      kScheduledGoldenOutput, 1);
  TEST_ASSERT_EQUAL_UINT32(1, frame.sequence);
  TEST_ASSERT_EQUAL_UINT64(33333, frame.media_timestamp_us);
  TEST_ASSERT_EQUAL_UINT64(987654321, frame.apply_at_us);
  TEST_ASSERT_TRUE(
      (frame.flags & light_belt::UDP_V3_FLAG_KEY_FRAME) != 0);
  TEST_ASSERT_TRUE(
      (frame.flags & light_belt::UDP_V3_FLAG_SCHEDULED_APPLY) != 0);

  const light_belt::OwnedNodeFrame owned =
      own(frame, kScheduledGoldenOutput, 1);
  TEST_ASSERT_EQUAL_UINT8(17, owned.outputs[0].pixels[0].r);
  TEST_ASSERT_EQUAL_UINT8(34, owned.outputs[0].pixels[0].g);
  TEST_ASSERT_EQUAL_UINT8(51, owned.outputs[0].pixels[0].b);
}

void test_udp_v3_golden_vector_copies_and_commits_only_after_success() {
  const light_belt::UdpV3Frame frame = parse(
      UDP_V3_GOLDEN_0, UDP_V3_GOLDEN_0_len, 2, kTwoOutputs, 2);
  TEST_ASSERT_EQUAL_UINT32(0x01020304, frame.sequence);
  TEST_ASSERT_EQUAL_UINT64(1234567, frame.media_timestamp_us);

  const light_belt::OwnedNodeFrame owned = own(frame, kTwoOutputs, 2);
  light_belt::MultiOutputFrameState state(kTwoOutputs, 2);
  TEST_ASSERT_TRUE(state.configurationValid());
  TEST_ASSERT_TRUE(state.isCandidateAcceptable(owned));

  // A physical-output failure is represented by not committing the accepted
  // candidate. No visible state or sequence changes in that case.
  TEST_ASSERT_NULL(state.committedFrame());
  TEST_ASSERT_FALSE(state.hasCommittedSequence());
  TEST_ASSERT_EQUAL_UINT32(0, state.refreshCount());
  TEST_ASSERT_TRUE(state.isCandidateAcceptable(owned));

  TEST_ASSERT_TRUE(state.commitFrame(owned, 50));
  TEST_ASSERT_EQUAL_UINT32(1, state.refreshCount());
  TEST_ASSERT_EQUAL_UINT32(0x01020304, state.lastSequence());
  TEST_ASSERT_EQUAL_UINT8(1, state.pixels(0)[0].r);
  TEST_ASSERT_EQUAL_UINT8(6, state.pixels(0)[1].b);
  TEST_ASSERT_EQUAL_UINT8(254, state.pixels(1)[0].r);
  TEST_ASSERT_EQUAL_UINT8(128, state.pixels(1)[0].g);
}

void test_owned_frame_survives_udp_buffer_reuse_and_uses_configured_order() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  const size_t len = makeFrame(raw, 2, 91, kTwoOutputsReversed, 2, 77);
  const light_belt::UdpV3Frame view = parse(raw, len, 2, kTwoOutputs, 2);
  const light_belt::OwnedNodeFrame owned = own(view, kTwoOutputs, 2);

  TEST_ASSERT_EQUAL_UINT8(1, owned.outputs[0].descriptor.output_id);
  TEST_ASSERT_EQUAL_UINT8(2, owned.outputs[1].descriptor.output_id);
  TEST_ASSERT_EQUAL_UINT8(10, owned.outputs[0].pixels[0].r);
  TEST_ASSERT_EQUAL_UINT8(40, owned.outputs[1].pixels[0].g);
  memset(raw, 0xE7, sizeof(raw));
  TEST_ASSERT_EQUAL_UINT8(10, owned.outputs[0].pixels[0].r);
  TEST_ASSERT_EQUAL_UINT8(40, owned.outputs[1].pixels[0].g);

  light_belt::OwnedNodeFrame unchanged{};
  unchanged.sequence = 0xAABBCCDD;
  light_belt::UdpV3Frame invalid = view;
  invalid.payload_len = static_cast<uint16_t>(invalid.payload_len - 1);
  TEST_ASSERT_FALSE(light_belt::copyUdpV3Frame(
      invalid, kTwoOutputs, 2, &unchanged));
  TEST_ASSERT_EQUAL_HEX32(0xAABBCCDD, unchanged.sequence);
}

void test_one_two_and_three_outputs_remain_independent() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  for (uint8_t output_count = 1; output_count <= 3; ++output_count) {
    const light_belt::OutputDescriptor *outputs =
        output_count == 1 ? kOneOutput :
        output_count == 2 ? kTwoOutputs : kThreeOutputs;
    const size_t len = makeFrame(raw, 9, 10 + output_count, outputs, output_count, 77);
    const light_belt::OwnedNodeFrame frame =
        own(parse(raw, len, 9, outputs, output_count), outputs, output_count);
    light_belt::MultiOutputFrameState state(outputs, output_count);
    TEST_ASSERT_TRUE(state.commitFrame(frame, 100));
    TEST_ASSERT_EQUAL_UINT32(1, state.refreshCount());
    for (uint8_t output = 0; output < output_count; ++output) {
      TEST_ASSERT_EQUAL_UINT8(10 * (output + 1), state.pixels(output)[0].r);
      TEST_ASSERT_EQUAL_UINT8(20 * (output + 1), state.pixels(output)[0].g);
      TEST_ASSERT_EQUAL_UINT8(30 * (output + 1), state.pixels(output)[0].b);
    }
  }
}

void test_invalid_incomplete_duplicate_and_oversized_frames_do_not_commit() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  const size_t valid_len = makeFrame(raw, 2, 50, kTwoOutputs, 2);
  light_belt::MultiOutputFrameState state(kTwoOutputs, 2);
  TEST_ASSERT_TRUE(state.commitFrame(
      own(parse(raw, valid_len, 2, kTwoOutputs, 2), kTwoOutputs, 2), 10));
  const uint8_t initial_red = state.pixels(0)[0].r;

  raw[valid_len - 1] ^= 1;
  light_belt::UdpV3Frame ignored{};
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::BadCrc),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, valid_len, 2, kTwoOutputs, 2, &ignored)));

  const size_t duplicate_len = makeFrame(raw, 2, 51, kTwoOutputs, 2);
  raw[light_belt::UDP_V3_HEADER_LEN +
      light_belt::UDP_V3_OUTPUT_DESCRIPTOR_LEN +
      kTwoOutputs[0].pixel_count * 3U] = 1;
  repairCrc(raw, duplicate_len);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::DuplicateOutput),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, duplicate_len, 2, kTwoOutputs, 2, &ignored)));

  const size_t incomplete_len = makeFrame(raw, 2, 52, kOneOutput, 1);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::IncompleteOutputSet),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, incomplete_len, 2, kTwoOutputs, 2, &ignored)));

  uint8_t too_large[light_belt::UDP_V3_MAX_PACKET_LEN + 1] = {};
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::TooLarge),
      static_cast<int>(light_belt::parseUdpV3Frame(
          too_large, sizeof(too_large), 2, kTwoOutputs, 2, &ignored)));
  TEST_ASSERT_EQUAL_UINT8(initial_red, state.pixels(0)[0].r);
  TEST_ASSERT_EQUAL_UINT32(1, state.refreshCount());
}

void test_duplicate_stale_and_wrap_sequences_use_only_committed_sequence() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  light_belt::MultiOutputFrameState state(kOneOutput, 1);
  size_t len = makeFrame(raw, 3, 0xFFFFFFFF, kOneOutput, 1);
  light_belt::OwnedNodeFrame frame =
      own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_TRUE(state.isCandidateAcceptable(frame));
  TEST_ASSERT_TRUE(state.commitFrame(frame, 10));

  len = makeFrame(raw, 3, 0, kOneOutput, 1);
  frame = own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_TRUE(state.commitFrame(frame, 20));
  TEST_ASSERT_EQUAL_UINT32(2, state.refreshCount());
  TEST_ASSERT_FALSE(state.isCandidateAcceptable(frame));

  len = makeFrame(raw, 3, 0xFFFFFFFF, kOneOutput, 1);
  frame = own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_FALSE(state.isCandidateAcceptable(frame));
  TEST_ASSERT_FALSE(state.commitFrame(frame, 30));
  TEST_ASSERT_EQUAL_UINT32(2, state.refreshCount());
  TEST_ASSERT_EQUAL_UINT32(0, state.lastSequence());
}

void test_only_key_frame_sequence_one_starts_a_new_session() {
  light_belt::OwnedNodeFrame candidate{};
  candidate.sequence = 1;
  TEST_ASSERT_FALSE(light_belt::isSessionStartFrame(candidate));
  TEST_ASSERT_FALSE(
      light_belt::isFrameSequenceAcceptable(candidate, true, 100));

  candidate.flags = light_belt::UDP_V3_FLAG_KEY_FRAME;
  TEST_ASSERT_TRUE(light_belt::isSessionStartFrame(candidate));
  TEST_ASSERT_TRUE(
      light_belt::isFrameSequenceAcceptable(candidate, true, 100));

  candidate.sequence = 2;
  TEST_ASSERT_FALSE(light_belt::isSessionStartFrame(candidate));
  TEST_ASSERT_FALSE(
      light_belt::isFrameSequenceAcceptable(candidate, true, 100));

  candidate.flags = 0;
  candidate.sequence = 101;
  TEST_ASSERT_TRUE(
      light_belt::isFrameSequenceAcceptable(candidate, true, 100));

  TEST_ASSERT_FALSE(light_belt::isSessionGenerationAdmitted(0, 0, 0));
  TEST_ASSERT_FALSE(light_belt::isSessionGenerationAdmitted(4, 0, 0));
  TEST_ASSERT_TRUE(light_belt::isSessionGenerationAdmitted(4, 4, 0));
  TEST_ASSERT_TRUE(light_belt::isSessionGenerationAdmitted(4, 0, 4));
  TEST_ASSERT_FALSE(light_belt::isSessionGenerationAdmitted(4, 3, 5));
}

void test_only_scheduled_continuations_require_admitted_session() {
  light_belt::OwnedNodeFrame candidate{};
  candidate.sequence = 57;

  TEST_ASSERT_FALSE(light_belt::requiresAdmittedSession(candidate));

  candidate.flags = light_belt::UDP_V3_FLAG_SCHEDULED_APPLY;
  TEST_ASSERT_TRUE(light_belt::requiresAdmittedSession(candidate));

  candidate.sequence = 1;
  candidate.flags = light_belt::UDP_V3_FLAG_SCHEDULED_APPLY |
                    light_belt::UDP_V3_FLAG_KEY_FRAME;
  TEST_ASSERT_FALSE(light_belt::requiresAdmittedSession(candidate));
}

void test_session_recovery_requires_recent_scheduled_key_and_safe_deadline() {
  light_belt::OwnedNodeFrame candidate{};
  candidate.sequence = 1;
  candidate.flags = light_belt::UDP_V3_FLAG_KEY_FRAME |
                    light_belt::UDP_V3_FLAG_SCHEDULED_APPLY;
  candidate.apply_at_us = 1020000;

  TEST_ASSERT_TRUE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::ClockNotReady,
      light_belt::PresentationClockStatus::Uncertain,
      1000000, 2000000));
  TEST_ASSERT_TRUE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::ClockNotReady,
      light_belt::PresentationClockStatus::InsufficientSamples,
      1000000, 2000000));
  TEST_ASSERT_FALSE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::TooLate,
      light_belt::PresentationClockStatus::Ready,
      1000000, 2000000));
  TEST_ASSERT_FALSE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::TooFar,
      light_belt::PresentationClockStatus::Ready,
      1000000, 2000000));
  TEST_ASSERT_FALSE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::InvalidApplyTime,
      light_belt::PresentationClockStatus::Ready,
      1000000, 2000000));
  TEST_ASSERT_FALSE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::Ok,
      light_belt::PresentationClockStatus::Ready,
      1000000, 2000000));
  TEST_ASSERT_FALSE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::ClockNotReady,
      light_belt::PresentationClockStatus::Stale,
      1000000, 2000000));

  candidate.flags = light_belt::UDP_V3_FLAG_SCHEDULED_APPLY;
  TEST_ASSERT_FALSE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::ClockNotReady,
      light_belt::PresentationClockStatus::Uncertain,
      1000000, 2000000));
  candidate.flags = light_belt::UDP_V3_FLAG_KEY_FRAME |
                    light_belt::UDP_V3_FLAG_SCHEDULED_APPLY;
  TEST_ASSERT_FALSE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::ClockNotReady,
      light_belt::PresentationClockStatus::Uncertain,
      0, 2000000));
  TEST_ASSERT_FALSE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::ClockNotReady,
      light_belt::PresentationClockStatus::Uncertain,
      1020001, 2000000));
  TEST_ASSERT_FALSE(light_belt::isSessionRecoveryEligible(
      candidate, light_belt::ApplyDeadlineResult::ClockNotReady,
      light_belt::PresentationClockStatus::Uncertain,
      1000000, 10000));
}

void test_recovery_sequence_reset_is_explicit_and_commits_only_on_success() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  light_belt::MultiOutputFrameState state(kOneOutput, 1);

  size_t len = makeFrame(raw, 3, 300, kOneOutput, 1);
  light_belt::OwnedNodeFrame frame =
      own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_TRUE(state.commitFrame(frame, 10));

  len = makeFrame(raw, 3, 2, kOneOutput, 1);
  frame = own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_FALSE(state.isCandidateAcceptable(frame));
  TEST_ASSERT_TRUE(state.isCandidateAcceptable(frame, true));
  TEST_ASSERT_EQUAL_UINT32(300, state.lastSequence());

  // Granting recovery at preparation time never mutates committed state.
  TEST_ASSERT_EQUAL_UINT32(300, state.lastSequence());
  TEST_ASSERT_TRUE(state.commitFrame(frame, 20, true));
  TEST_ASSERT_EQUAL_UINT32(2, state.lastSequence());

  len = makeFrame(raw, 3, 1, kOneOutput, 1);
  frame = own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_FALSE(state.commitFrame(frame, 30));
}

void test_key_frame_sequence_one_resets_committed_sequence_and_refreshes() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  light_belt::MultiOutputFrameState state(kOneOutput, 1);

  size_t len = makeFrame(raw, 3, 100, kOneOutput, 1);
  light_belt::OwnedNodeFrame frame =
      own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  frame.outputs[0].pixels[0].r = 100;
  TEST_ASSERT_TRUE(state.commitFrame(frame, 10));

  len = makeFrame(raw, 3, 1, kOneOutput, 1);
  frame = own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_FALSE(state.commitFrame(frame, 20));

  len = makeFrame(
      raw, 3, 2, kOneOutput, 1, 0,
      light_belt::UDP_V3_FLAG_KEY_FRAME);
  frame = own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_FALSE(state.commitFrame(frame, 30));

  len = makeFrame(
      raw, 3, 1, kOneOutput, 1, 0,
      light_belt::UDP_V3_FLAG_KEY_FRAME);
  frame = own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  frame.outputs[0].pixels[0].r = 1;
  TEST_ASSERT_TRUE(state.isCandidateAcceptable(frame));
  TEST_ASSERT_TRUE(state.commitFrame(frame, 40));
  TEST_ASSERT_EQUAL_UINT32(1, state.lastSequence());
  TEST_ASSERT_EQUAL_UINT32(2, state.refreshCount());
  TEST_ASSERT_EQUAL_UINT8(1, state.pixels(0)[0].r);

  len = makeFrame(raw, 3, 2, kOneOutput, 1);
  frame = own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_TRUE(state.commitFrame(frame, 50));
  TEST_ASSERT_EQUAL_UINT32(2, state.lastSequence());
  TEST_ASSERT_EQUAL_UINT32(3, state.refreshCount());
  TEST_ASSERT_FALSE(state.commitFrame(frame, 60));

  len = makeFrame(raw, 3, 1, kOneOutput, 1);
  frame = own(parse(raw, len, 3, kOneOutput, 1), kOneOutput, 1);
  TEST_ASSERT_FALSE(state.commitFrame(frame, 70));
  TEST_ASSERT_EQUAL_UINT32(3, state.refreshCount());
}

void test_timeout_black_commits_only_after_physical_success() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  const size_t len = makeFrame(raw, 4, 1, kThreeOutputs, 3);
  const light_belt::OwnedNodeFrame frame =
      own(parse(raw, len, 4, kThreeOutputs, 3), kThreeOutputs, 3);
  light_belt::MultiOutputFrameState state(kThreeOutputs, 3);
  TEST_ASSERT_TRUE(state.commitFrame(frame, 100));
  TEST_ASSERT_FALSE(state.timedOut(1100, 1000));
  TEST_ASSERT_TRUE(state.timedOut(1101, 1000));

  // A failed black refresh does not call commitSafeBlack, so timeout remains
  // active and the physical layer can retry.
  TEST_ASSERT_FALSE(state.safeBlackCommitted());
  TEST_ASSERT_TRUE(state.timedOut(1200, 1000));
  TEST_ASSERT_EQUAL_UINT32(1, state.refreshCount());

  TEST_ASSERT_TRUE(state.commitSafeBlack(1200));
  TEST_ASSERT_TRUE(state.safeBlackCommitted());
  TEST_ASSERT_FALSE(state.timedOut(1201, 1000));
  TEST_ASSERT_EQUAL_UINT32(2, state.refreshCount());
  TEST_ASSERT_TRUE(state.hasCommittedSequence());
  TEST_ASSERT_EQUAL_UINT32(1, state.lastSequence());
  TEST_ASSERT_NOT_NULL(state.committedFrame());
  TEST_ASSERT_EQUAL_UINT8(
      light_belt::UDP_V3_FLAG_SAFE_STATE, state.committedFrame()->flags);
  for (uint8_t output = 0; output < state.outputCount(); ++output) {
    for (uint16_t pixel = 0; pixel < state.descriptor(output).pixel_count; ++pixel) {
      TEST_ASSERT_EQUAL_UINT8(0, state.pixels(output)[pixel].r);
      TEST_ASSERT_EQUAL_UINT8(0, state.pixels(output)[pixel].g);
      TEST_ASSERT_EQUAL_UINT8(0, state.pixels(output)[pixel].b);
    }
  }
}

void test_udp_safe_state_commit_is_normalized_to_black_and_does_not_timeout() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  const size_t len = makeFrame(raw, 4, 7, kOneOutput, 1);
  light_belt::OwnedNodeFrame frame =
      own(parse(raw, len, 4, kOneOutput, 1), kOneOutput, 1);
  frame.flags = static_cast<uint8_t>(
      frame.flags | light_belt::UDP_V3_FLAG_SAFE_STATE);
  TEST_ASSERT_NOT_EQUAL(0, frame.outputs[0].pixels[0].r);

  light_belt::MultiOutputFrameState state(kOneOutput, 1);
  TEST_ASSERT_TRUE(state.commitFrame(frame, 100));
  TEST_ASSERT_TRUE(state.safeBlackCommitted());
  TEST_ASSERT_EQUAL_UINT32(7, state.lastSequence());
  TEST_ASSERT_EQUAL_UINT8(0, state.pixels(0)[0].r);
  TEST_ASSERT_EQUAL_UINT8(0, state.pixels(0)[0].g);
  TEST_ASSERT_EQUAL_UINT8(0, state.pixels(0)[0].b);
  TEST_ASSERT_FALSE(state.timedOut(5000, 1000));
}

void test_spi_encoder_exact_00_ff_aa_55_patterns_and_guards() {
  const uint8_t sources[] = {0x00, 0xFF, 0xAA, 0x55};
  for (const uint8_t source : sources) {
    const light_belt::RgbPixel pixel = {source, source, source};
    uint8_t encoded[light_belt::WS2811_SPI_MAX_FRAME_BYTES] = {};
    size_t encoded_len = 0;
    TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi(
        &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
        encoded, sizeof(encoded), &encoded_len));
    TEST_ASSERT_EQUAL_UINT32(76, static_cast<uint32_t>(encoded_len));
    for (size_t index = 0; index < light_belt::WS2811_SPI_GUARD_BYTES; ++index) {
      TEST_ASSERT_EQUAL_HEX8(0, encoded[index]);
      TEST_ASSERT_EQUAL_HEX8(0, encoded[encoded_len - 1 - index]);
    }
    for (uint8_t channel = 0; channel < 3; ++channel) {
      assertEncodedByte(
          encoded,
          light_belt::WS2811_SPI_GUARD_BYTES + channel * 4U,
          source);
    }
  }
}

void test_spi_encoder_preserves_warm_rgb_values_and_reorders_grb_only() {
  const light_belt::RgbPixel warm = {0xFF, 0x60, 0x10};
  uint8_t rgb[light_belt::WS2811_SPI_MAX_FRAME_BYTES] = {};
  uint8_t grb[light_belt::WS2811_SPI_MAX_FRAME_BYTES] = {};
  size_t rgb_len = 0;
  size_t grb_len = 0;
  TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi(
      &warm, 1, light_belt::Ws2811ColorOrder::RGB,
      rgb, sizeof(rgb), &rgb_len));
  TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi(
      &warm, 1, light_belt::Ws2811ColorOrder::GRB,
      grb, sizeof(grb), &grb_len));
  TEST_ASSERT_EQUAL_UINT32(rgb_len, grb_len);

  const size_t data = light_belt::WS2811_SPI_GUARD_BYTES;
  assertEncodedByte(rgb, data, 0xFF);
  assertEncodedByte(rgb, data + 4, 0x60);
  assertEncodedByte(rgb, data + 8, 0x10);
  assertEncodedByte(grb, data, 0x60);
  assertEncodedByte(grb, data + 4, 0xFF);
  assertEncodedByte(grb, data + 8, 0x10);
}

void test_spi_encoder_lengths_for_1_10_20_40_and_100_groups() {
  light_belt::RgbPixel pixels[light_belt::MAX_PIXELS_PER_OUTPUT] = {};
  uint8_t storage[light_belt::WS2811_SPI_MAX_FRAME_BYTES + 2] = {};
  const uint16_t counts[] = {1, 10, 20, 40, 100};
  for (const uint16_t count : counts) {
    memset(storage, 0xA5, sizeof(storage));
    size_t encoded_len = 0;
    TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi(
        pixels, count, light_belt::Ws2811ColorOrder::GRB,
        storage + 1, sizeof(storage) - 2, &encoded_len));
    const size_t expected = 64U + static_cast<size_t>(count) * 12U;
    TEST_ASSERT_EQUAL_UINT32(expected, encoded_len);
    TEST_ASSERT_EQUAL_UINT32(expected, light_belt::ws2811SpiFrameSize(count));
    TEST_ASSERT_EQUAL_HEX8(0xA5, storage[0]);
    TEST_ASSERT_EQUAL_HEX8(0xA5, storage[encoded_len + 1]);
    for (size_t index = 0; index < light_belt::WS2811_SPI_GUARD_BYTES; ++index) {
      TEST_ASSERT_EQUAL_HEX8(0, storage[1 + index]);
      TEST_ASSERT_EQUAL_HEX8(0, storage[encoded_len - index]);
    }
  }
}

void test_fixed_gpio4_spi4_encoder_uses_500us_guards_and_uniform_region() {
  light_belt::RgbPixel pixels[3] = {
      {0x12, 0x34, 0x56},
      {0x12, 0x34, 0x56},
      {0x12, 0x34, 0x56},
  };
  uint8_t encoded[light_belt::WS2811_FIXED_GPIO4_SPI_MAX_FRAME_BYTES] = {};
  size_t encoded_len = 0;
  TEST_ASSERT_TRUE(light_belt::encodeWs2811FixedGpio4Spi(
      pixels, 3, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_EQUAL_UINT32(436, encoded_len);
  for (size_t index = 0;
       index < light_belt::WS2811_FIXED_GPIO4_SPI_GUARD_BYTES; ++index) {
    TEST_ASSERT_EQUAL_HEX8(0, encoded[index]);
    TEST_ASSERT_EQUAL_HEX8(0, encoded[encoded_len - 1U - index]);
  }
  assertEncodedByte(
      encoded, light_belt::WS2811_FIXED_GPIO4_SPI_GUARD_BYTES, 0x12);
  TEST_ASSERT_TRUE(light_belt::ws2811FixedGpio4SpiUniformEncodedGroups(
      encoded, encoded_len, 3));
  const uint32_t original_hash =
      light_belt::ws2811EncodedHash(encoded, encoded_len);
  encoded[light_belt::WS2811_FIXED_GPIO4_SPI_GUARD_BYTES +
          light_belt::WS2811_SPI_BYTES_PER_GROUP] ^= 0x01;
  TEST_ASSERT_NOT_EQUAL(
      original_hash, light_belt::ws2811EncodedHash(encoded, encoded_len));
  TEST_ASSERT_FALSE(light_belt::ws2811FixedGpio4SpiUniformEncodedGroups(
      encoded, encoded_len, 3));
}

void test_scheduled_production_spi4_wire_times_cover_installed_lengths() {
  const uint16_t groups[] = {10, 20, 40};
  const uint32_t expected_bytes[] = {520, 640, 880};
  const uint32_t expected_micros[] = {1300, 1600, 2200};
  for (size_t index = 0; index < 3; ++index) {
    const uint64_t encoded_len =
        light_belt::ws2811FixedGpio4SpiFrameSize(groups[index]);
    const uint64_t bit_micros = encoded_len * 8U * 1000000U;
    const uint32_t wire_time_us = static_cast<uint32_t>(
        (bit_micros + light_belt::WS2811_SPI_CLOCK_HZ - 1U) /
        light_belt::WS2811_SPI_CLOCK_HZ);
    TEST_ASSERT_EQUAL_UINT32(expected_bytes[index], encoded_len);
    TEST_ASSERT_EQUAL_UINT32(expected_micros[index], wire_time_us);
  }
  TEST_ASSERT_GREATER_OR_EQUAL_UINT64(
      static_cast<uint64_t>(light_belt::WS2811_SPI_CLOCK_HZ) *
          light_belt::WS2811_FIXED_GPIO4_SPI_RESET_LOW_US,
      static_cast<uint64_t>(
          light_belt::WS2811_FIXED_GPIO4_SPI_GUARD_BYTES) * 8U *
          1000000U);
}

void test_spi_encoder_rejects_invalid_inputs_without_touching_destination() {
  const light_belt::RgbPixel pixel = {1, 2, 3};
  uint8_t encoded[light_belt::WS2811_SPI_MAX_FRAME_BYTES] = {};
  memset(encoded, 0x5A, sizeof(encoded));
  size_t encoded_len = 123;
  const size_t required = light_belt::ws2811SpiFrameSize(1);
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi(
      &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, required - 1, &encoded_len));
  TEST_ASSERT_EQUAL_UINT32(123, encoded_len);
  TEST_ASSERT_EQUAL_HEX8(0x5A, encoded[0]);
  TEST_ASSERT_EQUAL_HEX8(0x5A, encoded[required - 2]);
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi(
      &pixel, 0, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi(
      &pixel, 1, static_cast<light_belt::Ws2811ColorOrder>(99),
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_EQUAL_UINT32(0, light_belt::ws2811SpiFrameSize(0));
  TEST_ASSERT_EQUAL_UINT32(
      0, light_belt::ws2811SpiFrameSize(
             light_belt::MAX_PIXELS_PER_OUTPUT + 1));
}

void test_spi_encoded_diagnostics_cover_buffer_and_uniform_groups() {
  light_belt::RgbPixel pixels[3] = {
      {0x12, 0x34, 0x56},
      {0x12, 0x34, 0x56},
      {0x12, 0x34, 0x56},
  };
  uint8_t encoded[light_belt::WS2811_SPI_MAX_FRAME_BYTES] = {};
  size_t encoded_len = 0;
  TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi(
      pixels, 3, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_TRUE(
      light_belt::ws2811UniformEncodedGroups(encoded, encoded_len, 3));

  const uint32_t original_hash =
      light_belt::ws2811EncodedHash(encoded, encoded_len);
  TEST_ASSERT_NOT_EQUAL(0, original_hash);
  encoded[light_belt::WS2811_SPI_GUARD_BYTES +
          light_belt::WS2811_SPI_BYTES_PER_GROUP] ^= 0x01;
  TEST_ASSERT_NOT_EQUAL(
      original_hash, light_belt::ws2811EncodedHash(encoded, encoded_len));
  TEST_ASSERT_FALSE(
      light_belt::ws2811UniformEncodedGroups(encoded, encoded_len, 3));
  TEST_ASSERT_FALSE(
      light_belt::ws2811UniformEncodedGroups(encoded, encoded_len - 1, 3));
  TEST_ASSERT_EQUAL_UINT32(0, light_belt::ws2811EncodedHash(nullptr, 0));
}

void test_spi3_encoder_exact_00_ff_aa_55_patterns_and_guards() {
  TEST_ASSERT_EQUAL_UINT32(2400000, light_belt::WS2811_SPI3_CLOCK_HZ);
  TEST_ASSERT_EQUAL_UINT32(32, light_belt::WS2811_SPI3_GUARD_BYTES);
  TEST_ASSERT_EQUAL_UINT32(9, light_belt::WS2811_SPI3_BYTES_PER_GROUP);
  TEST_ASSERT_EQUAL_UINT32(964, light_belt::WS2811_SPI3_MAX_FRAME_BYTES);

  const uint8_t sources[] = {0x00, 0xFF, 0xAA, 0x55};
  const uint8_t expected[][3] = {
      {0x92, 0x49, 0x24},
      {0xDB, 0x6D, 0xB6},
      {0xD3, 0x4D, 0x34},
      {0x9A, 0x69, 0xA6},
  };
  for (size_t pattern = 0; pattern < sizeof(sources); ++pattern) {
    const light_belt::RgbPixel pixel = {
        sources[pattern], sources[pattern], sources[pattern]};
    uint8_t encoded[light_belt::WS2811_SPI3_MAX_FRAME_BYTES] = {};
    size_t encoded_len = 0;
    TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi3(
        &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
        encoded, sizeof(encoded), &encoded_len));
    TEST_ASSERT_EQUAL_UINT32(73, static_cast<uint32_t>(encoded_len));

    for (size_t index = 0;
         index < light_belt::WS2811_SPI3_GUARD_BYTES;
         ++index) {
      TEST_ASSERT_EQUAL_HEX8(0, encoded[index]);
      TEST_ASSERT_EQUAL_HEX8(0, encoded[encoded_len - 1U - index]);
    }
    for (uint8_t channel = 0; channel < 3; ++channel) {
      TEST_ASSERT_EQUAL_HEX8_ARRAY(
          expected[pattern],
          encoded + light_belt::WS2811_SPI3_GUARD_BYTES + channel * 3U,
          3);
    }
  }
}

void test_spi3_encoder_preserves_rgb_and_reorders_grb_only() {
  const light_belt::RgbPixel pixel = {0x00, 0xFF, 0xAA};
  uint8_t rgb[light_belt::WS2811_SPI3_MAX_FRAME_BYTES] = {};
  uint8_t grb[light_belt::WS2811_SPI3_MAX_FRAME_BYTES] = {};
  size_t rgb_len = 0;
  size_t grb_len = 0;
  TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi3(
      &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
      rgb, sizeof(rgb), &rgb_len));
  TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi3(
      &pixel, 1, light_belt::Ws2811ColorOrder::GRB,
      grb, sizeof(grb), &grb_len));
  TEST_ASSERT_EQUAL_UINT32(rgb_len, grb_len);

  const uint8_t zero[] = {0x92, 0x49, 0x24};
  const uint8_t ones[] = {0xDB, 0x6D, 0xB6};
  const uint8_t alternating[] = {0xD3, 0x4D, 0x34};
  const size_t data = light_belt::WS2811_SPI3_GUARD_BYTES;
  TEST_ASSERT_EQUAL_HEX8_ARRAY(zero, rgb + data, 3);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(ones, rgb + data + 3U, 3);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(alternating, rgb + data + 6U, 3);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(ones, grb + data, 3);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(zero, grb + data + 3U, 3);
  TEST_ASSERT_EQUAL_HEX8_ARRAY(alternating, grb + data + 6U, 3);
}

void test_spi3_encoder_lengths_for_1_10_20_40_and_100_groups() {
  light_belt::RgbPixel pixels[light_belt::MAX_PIXELS_PER_OUTPUT] = {};
  uint8_t storage[light_belt::WS2811_SPI3_MAX_FRAME_BYTES + 2U] = {};
  const uint16_t counts[] = {1, 10, 20, 40, 100};
  for (const uint16_t count : counts) {
    memset(storage, 0xA5, sizeof(storage));
    size_t encoded_len = 0;
    TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi3(
        pixels, count, light_belt::Ws2811ColorOrder::GRB,
        storage + 1, sizeof(storage) - 2U, &encoded_len));
    const size_t expected = 64U + static_cast<size_t>(count) * 9U;
    TEST_ASSERT_EQUAL_UINT32(expected, encoded_len);
    TEST_ASSERT_EQUAL_UINT32(expected, light_belt::ws2811Spi3FrameSize(count));
    TEST_ASSERT_EQUAL_HEX8(0xA5, storage[0]);
    TEST_ASSERT_EQUAL_HEX8(0xA5, storage[encoded_len + 1U]);
    for (size_t index = 0;
         index < light_belt::WS2811_SPI3_GUARD_BYTES;
         ++index) {
      TEST_ASSERT_EQUAL_HEX8(0, storage[1U + index]);
      TEST_ASSERT_EQUAL_HEX8(0, storage[encoded_len - index]);
    }
  }
}

void test_spi3_encoder_rejects_invalid_inputs_without_mutation() {
  const light_belt::RgbPixel pixel = {1, 2, 3};
  uint8_t encoded[light_belt::WS2811_SPI3_MAX_FRAME_BYTES] = {};
  memset(encoded, 0x5A, sizeof(encoded));
  size_t encoded_len = 123;
  const size_t required = light_belt::ws2811Spi3FrameSize(1);

  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi3(
      &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, required - 1U, &encoded_len));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi3(
      nullptr, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, required, &encoded_len));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi3(
      &pixel, 0, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi3(
      &pixel, light_belt::MAX_PIXELS_PER_OUTPUT + 1U,
      light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi3(
      &pixel, 1, static_cast<light_belt::Ws2811ColorOrder>(99),
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi3(
      &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
      nullptr, required, &encoded_len));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi3(
      &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, required, nullptr));

  TEST_ASSERT_EQUAL_UINT32(123, encoded_len);
  for (size_t index = 0; index < sizeof(encoded); ++index) {
    TEST_ASSERT_EQUAL_HEX8(0x5A, encoded[index]);
  }
  TEST_ASSERT_EQUAL_UINT32(0, light_belt::ws2811Spi3FrameSize(0));
  TEST_ASSERT_EQUAL_UINT32(
      0, light_belt::ws2811Spi3FrameSize(
             light_belt::MAX_PIXELS_PER_OUTPUT + 1U));
}

void test_spi6_encoder_exact_vectors_guards_and_group_limits() {
  TEST_ASSERT_EQUAL_UINT32(5000000, light_belt::WS2811_SPI6_CLOCK_HZ);
  TEST_ASSERT_EQUAL_UINT32(500, light_belt::WS2811_SPI6_RESET_LOW_US);
  TEST_ASSERT_EQUAL_UINT32(313, light_belt::WS2811_SPI6_PRE_GUARD_BYTES);
  TEST_ASSERT_EQUAL_UINT32(313, light_belt::WS2811_SPI6_POST_GUARD_BYTES);
  TEST_ASSERT_EQUAL_UINT32(18, light_belt::WS2811_SPI6_BYTES_PER_GROUP);
  TEST_ASSERT_EQUAL_UINT32(2426, light_belt::WS2811_SPI6_MAX_FRAME_BYTES);

  const uint8_t sources[] = {0x00, 0xFF, 0xAA, 0x55};
  const uint8_t expected[][6] = {
      {0x82, 0x08, 0x20, 0x82, 0x08, 0x20},
      {0xE3, 0x8E, 0x38, 0xE3, 0x8E, 0x38},
      {0xE2, 0x0E, 0x20, 0xE2, 0x0E, 0x20},
      {0x83, 0x88, 0x38, 0x83, 0x88, 0x38},
  };
  for (size_t pattern = 0; pattern < sizeof(sources); ++pattern) {
    const light_belt::RgbPixel pixel = {
        sources[pattern], sources[pattern], sources[pattern]};
    uint8_t encoded[light_belt::WS2811_SPI6_MAX_FRAME_BYTES] = {};
    size_t encoded_len = 0;
    TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi6(
        &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
        encoded, sizeof(encoded), &encoded_len));
    TEST_ASSERT_EQUAL_UINT32(644, encoded_len);
    for (size_t index = 0;
         index < light_belt::WS2811_SPI6_PRE_GUARD_BYTES;
         ++index) {
      TEST_ASSERT_EQUAL_HEX8(0, encoded[index]);
    }
    for (size_t index = 0;
         index < light_belt::WS2811_SPI6_POST_GUARD_BYTES;
         ++index) {
      TEST_ASSERT_EQUAL_HEX8(0, encoded[encoded_len - 1U - index]);
    }
    for (uint8_t channel = 0; channel < 3; ++channel) {
      TEST_ASSERT_EQUAL_HEX8_ARRAY(
          expected[pattern],
          encoded + light_belt::WS2811_SPI6_PRE_GUARD_BYTES + channel * 6U,
          6);
    }
  }

  TEST_ASSERT_EQUAL_UINT32(986, light_belt::ws2811Spi6FrameSize(20));
  TEST_ASSERT_EQUAL_UINT32(2426, light_belt::ws2811Spi6FrameSize(100));
  TEST_ASSERT_EQUAL_UINT32(0, light_belt::ws2811Spi6FrameSize(0));
  TEST_ASSERT_EQUAL_UINT32(0, light_belt::ws2811Spi6FrameSize(101));
  const light_belt::RgbPixel pixel = {1, 2, 3};
  uint8_t encoded[light_belt::WS2811_SPI6_MAX_FRAME_BYTES] = {};
  memset(encoded, 0x5A, sizeof(encoded));
  size_t encoded_len = 123;
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Spi6(
      &pixel, 101, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_EQUAL_UINT32(123, encoded_len);
  TEST_ASSERT_EQUAL_HEX8(0x5A, encoded[0]);
  TEST_ASSERT_EQUAL_HEX8(0x5A, encoded[sizeof(encoded) - 1U]);

  light_belt::RgbPixel uniform[3] = {
      {0x12, 0x34, 0x56},
      {0x12, 0x34, 0x56},
      {0x12, 0x34, 0x56},
  };
  size_t uniform_len = 0;
  TEST_ASSERT_TRUE(light_belt::encodeWs2811Spi6(
      uniform, 3, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &uniform_len));
  TEST_ASSERT_TRUE(light_belt::ws2811Spi6UniformEncodedGroups(
      encoded, uniform_len, 3));
  encoded[light_belt::WS2811_SPI6_PRE_GUARD_BYTES +
          light_belt::WS2811_SPI6_BYTES_PER_GROUP] ^= 0x01;
  TEST_ASSERT_FALSE(light_belt::ws2811Spi6UniformEncodedGroups(
      encoded, uniform_len, 3));
  TEST_ASSERT_FALSE(light_belt::ws2811Spi6UniformEncodedGroups(
      encoded, uniform_len - 1U, 3));
}

void test_parallel_spi_encoder_uses_qio_lane_masks_and_keeps_data3_low() {
  const light_belt::RgbPixel lane0[] = {{0x80, 0x00, 0x00}};
  const light_belt::RgbPixel lane1[] = {{0x00, 0x00, 0x00}};
  const light_belt::RgbPixel lane2[] = {{0xC0, 0x00, 0x00}};
  const light_belt::Ws2811ParallelSpiLane lanes[] = {
      {lane0, 1}, {lane1, 1}, {lane2, 1}};
  uint8_t encoded[2U * light_belt::WS2811_PARALLEL_SPI_GUARD_BYTES +
                  light_belt::WS2811_PARALLEL_SPI_BYTES_PER_GROUP] = {};
  size_t encoded_len = 0;

  TEST_ASSERT_TRUE(light_belt::encodeWs2811ParallelSpi(
      lanes, 3, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_EQUAL_UINT32(1328, static_cast<uint32_t>(encoded_len));

  const size_t data = light_belt::WS2811_PARALLEL_SPI_GUARD_BYTES;
  TEST_ASSERT_EQUAL_HEX8(0x75, encoded[data]);
  TEST_ASSERT_EQUAL_HEX8(0x00, encoded[data + 1]);
  TEST_ASSERT_EQUAL_HEX8(0x74, encoded[data + 2]);
  TEST_ASSERT_EQUAL_HEX8(0x00, encoded[data + 3]);
  for (size_t index = 0; index < encoded_len; ++index) {
    TEST_ASSERT_EQUAL_HEX8(0, static_cast<uint8_t>(encoded[index] & 0x88));
  }
  for (size_t index = 0;
       index < light_belt::WS2811_PARALLEL_SPI_GUARD_BYTES;
       ++index) {
    TEST_ASSERT_EQUAL_HEX8(0, encoded[index]);
    TEST_ASSERT_EQUAL_HEX8(0, encoded[encoded_len - 1U - index]);
  }
}

void test_parallel_spi_encoder_preserves_rgb_and_reorders_grb_only() {
  const light_belt::RgbPixel pixel[] = {{0x81, 0x42, 0x24}};
  const light_belt::Ws2811ParallelSpiLane lanes[] = {{pixel, 1}};
  uint8_t rgb[2U * light_belt::WS2811_PARALLEL_SPI_GUARD_BYTES +
              light_belt::WS2811_PARALLEL_SPI_BYTES_PER_GROUP] = {};
  uint8_t grb[sizeof(rgb)] = {};
  size_t rgb_len = 0;
  size_t grb_len = 0;

  TEST_ASSERT_TRUE(light_belt::encodeWs2811ParallelSpi(
      lanes, 1, light_belt::Ws2811ColorOrder::RGB,
      rgb, sizeof(rgb), &rgb_len));
  TEST_ASSERT_TRUE(light_belt::encodeWs2811ParallelSpi(
      lanes, 1, light_belt::Ws2811ColorOrder::GRB,
      grb, sizeof(grb), &grb_len));
  TEST_ASSERT_EQUAL_UINT32(rgb_len, grb_len);

  const size_t data = light_belt::WS2811_PARALLEL_SPI_GUARD_BYTES;
  const size_t channel_bytes = 16;
  assertParallelEncodedChannel(rgb, data, 0x01, 0x01, 0x81);
  assertParallelEncodedChannel(rgb, data + channel_bytes, 0x01, 0x01, 0x42);
  assertParallelEncodedChannel(
      rgb, data + 2U * channel_bytes, 0x01, 0x01, 0x24);
  assertParallelEncodedChannel(grb, data, 0x01, 0x01, 0x42);
  assertParallelEncodedChannel(grb, data + channel_bytes, 0x01, 0x01, 0x81);
  assertParallelEncodedChannel(
      grb, data + 2U * channel_bytes, 0x01, 0x01, 0x24);
}

void test_parallel_spi_encoder_uses_longest_lane_and_black_padding() {
  const light_belt::RgbPixel short_lane[] = {{0xFF, 0xFF, 0xFF}};
  const light_belt::RgbPixel long_lane[] = {
      {0x00, 0x00, 0x00}, {0x80, 0x00, 0x00}};
  const light_belt::Ws2811ParallelSpiLane lanes[] = {
      {short_lane, 1}, {long_lane, 2}};
  uint8_t encoded[2U * light_belt::WS2811_PARALLEL_SPI_GUARD_BYTES +
                  2U * light_belt::WS2811_PARALLEL_SPI_BYTES_PER_GROUP] = {};
  size_t encoded_len = 0;

  TEST_ASSERT_EQUAL_UINT32(
      1376, light_belt::ws2811ParallelSpiFrameSize(lanes, 2));
  TEST_ASSERT_TRUE(light_belt::encodeWs2811ParallelSpi(
      lanes, 2, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_EQUAL_UINT32(1376, static_cast<uint32_t>(encoded_len));

  const size_t second_group =
      light_belt::WS2811_PARALLEL_SPI_GUARD_BYTES +
      light_belt::WS2811_PARALLEL_SPI_BYTES_PER_GROUP;
  TEST_ASSERT_EQUAL_HEX8(0x32, encoded[second_group]);
  TEST_ASSERT_EQUAL_HEX8(0x00, encoded[second_group + 1]);
  for (size_t index = second_group;
       index < encoded_len - light_belt::WS2811_PARALLEL_SPI_GUARD_BYTES;
       index += 2) {
    TEST_ASSERT_EQUAL_HEX8(0, static_cast<uint8_t>(encoded[index] & 0x01));
  }

  light_belt::RgbPixel max_lane[light_belt::MAX_PIXELS_PER_OUTPUT] = {};
  const light_belt::Ws2811ParallelSpiLane max_lanes[] = {
      {max_lane, light_belt::MAX_PIXELS_PER_OUTPUT}};
  TEST_ASSERT_EQUAL_UINT32(
      light_belt::WS2811_PARALLEL_SPI_MAX_FRAME_BYTES,
      light_belt::ws2811ParallelSpiFrameSize(max_lanes, 1));
}

void test_parallel_spi_encoder_rejects_without_mutating_outputs() {
  const light_belt::RgbPixel pixel[] = {{1, 2, 3}};
  light_belt::Ws2811ParallelSpiLane lanes[] = {{pixel, 1}};
  uint8_t encoded[2U * light_belt::WS2811_PARALLEL_SPI_GUARD_BYTES +
                  light_belt::WS2811_PARALLEL_SPI_BYTES_PER_GROUP] = {};
  memset(encoded, 0x5A, sizeof(encoded));
  size_t encoded_len = 123;
  const size_t required = light_belt::ws2811ParallelSpiFrameSize(lanes, 1);

  TEST_ASSERT_FALSE(light_belt::encodeWs2811ParallelSpi(
      lanes, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, required - 1U, &encoded_len));
  TEST_ASSERT_EQUAL_UINT32(123, static_cast<uint32_t>(encoded_len));
  TEST_ASSERT_EQUAL_HEX8(0x5A, encoded[0]);
  TEST_ASSERT_EQUAL_HEX8(0x5A, encoded[required - 1U]);

  lanes[0].pixels = nullptr;
  TEST_ASSERT_FALSE(light_belt::encodeWs2811ParallelSpi(
      lanes, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  lanes[0] = {pixel, 0};
  TEST_ASSERT_FALSE(light_belt::encodeWs2811ParallelSpi(
      lanes, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  lanes[0] = {pixel, light_belt::MAX_PIXELS_PER_OUTPUT + 1U};
  TEST_ASSERT_FALSE(light_belt::encodeWs2811ParallelSpi(
      lanes, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  lanes[0] = {pixel, 1};
  TEST_ASSERT_FALSE(light_belt::encodeWs2811ParallelSpi(
      lanes, 0, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  const light_belt::Ws2811ParallelSpiLane too_many_lanes[] = {
      {pixel, 1}, {pixel, 1}, {pixel, 1}, {pixel, 1}};
  TEST_ASSERT_FALSE(light_belt::encodeWs2811ParallelSpi(
      too_many_lanes, 4, light_belt::Ws2811ColorOrder::RGB,
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811ParallelSpi(
      lanes, 1, static_cast<light_belt::Ws2811ColorOrder>(99),
      encoded, sizeof(encoded), &encoded_len));
  TEST_ASSERT_EQUAL_UINT32(123, static_cast<uint32_t>(encoded_len));
  TEST_ASSERT_EQUAL_HEX8(0x5A, encoded[0]);
  TEST_ASSERT_EQUAL_UINT32(0, light_belt::ws2811ParallelSpiFrameSize(nullptr, 1));
  TEST_ASSERT_EQUAL_UINT32(0, light_belt::ws2811ParallelSpiFrameSize(lanes, 0));
  TEST_ASSERT_EQUAL_UINT32(
      0, light_belt::ws2811ParallelSpiFrameSize(too_many_lanes, 4));
}

void test_rmt_encoder_exact_00_ff_aa_and_55_patterns() {
  TEST_ASSERT_EQUAL_UINT32(5, light_belt::WS2811_RMT_CLOCK_DIVIDER);
  TEST_ASSERT_EQUAL_UINT32(16000000, light_belt::WS2811_RMT_TICK_HZ);
  TEST_ASSERT_EQUAL_UINT16(5, light_belt::WS2811_RMT_ZERO_HIGH_TICKS);
  TEST_ASSERT_EQUAL_UINT16(15, light_belt::WS2811_RMT_ZERO_LOW_TICKS);
  TEST_ASSERT_EQUAL_UINT16(10, light_belt::WS2811_RMT_ONE_HIGH_TICKS);
  TEST_ASSERT_EQUAL_UINT16(10, light_belt::WS2811_RMT_ONE_LOW_TICKS);
  TEST_ASSERT_EQUAL_UINT32(24, light_belt::WS2811_RMT_PULSES_PER_GROUP);
  TEST_ASSERT_EQUAL_UINT32(2400, light_belt::WS2811_RMT_MAX_PULSES);
  const uint8_t sources[] = {0x00, 0xFF, 0xAA, 0x55};
  for (const uint8_t source : sources) {
    const light_belt::RgbPixel pixel = {source, source, source};
    light_belt::Ws2811RmtPulse encoded[
        light_belt::WS2811_RMT_PULSES_PER_GROUP] = {};
    size_t encoded_count = 0;
    TEST_ASSERT_TRUE(light_belt::encodeWs2811Rmt(
        &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
        encoded, light_belt::WS2811_RMT_PULSES_PER_GROUP, &encoded_count));
    TEST_ASSERT_EQUAL_UINT32(
        light_belt::WS2811_RMT_PULSES_PER_GROUP, encoded_count);
    for (uint8_t channel = 0; channel < 3; ++channel) {
      assertRmtEncodedByte(encoded, channel * 8U, source);
    }
  }
}

void test_rmt_encoder_preserves_rgb_and_reorders_grb_only() {
  const light_belt::RgbPixel pixel = {0x81, 0x42, 0x24};
  light_belt::Ws2811RmtPulse rgb[
      light_belt::WS2811_RMT_PULSES_PER_GROUP] = {};
  light_belt::Ws2811RmtPulse grb[
      light_belt::WS2811_RMT_PULSES_PER_GROUP] = {};
  size_t rgb_count = 0;
  size_t grb_count = 0;

  TEST_ASSERT_TRUE(light_belt::encodeWs2811Rmt(
      &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
      rgb, light_belt::WS2811_RMT_PULSES_PER_GROUP, &rgb_count));
  TEST_ASSERT_TRUE(light_belt::encodeWs2811Rmt(
      &pixel, 1, light_belt::Ws2811ColorOrder::GRB,
      grb, light_belt::WS2811_RMT_PULSES_PER_GROUP, &grb_count));
  TEST_ASSERT_EQUAL_UINT32(rgb_count, grb_count);

  assertRmtEncodedByte(rgb, 0, 0x81);
  assertRmtEncodedByte(rgb, 8, 0x42);
  assertRmtEncodedByte(rgb, 16, 0x24);
  assertRmtEncodedByte(grb, 0, 0x42);
  assertRmtEncodedByte(grb, 8, 0x81);
  assertRmtEncodedByte(grb, 16, 0x24);
}

void test_rmt_encoder_lengths_for_1_10_20_40_and_100_groups() {
  static light_belt::RgbPixel pixels[light_belt::MAX_PIXELS_PER_OUTPUT] = {};
  static light_belt::Ws2811RmtPulse storage[
      light_belt::WS2811_RMT_MAX_PULSES + 2U] = {};
  const uint16_t counts[] = {1, 10, 20, 40, 100};
  for (const uint16_t count : counts) {
    for (size_t index = 0;
         index < light_belt::WS2811_RMT_MAX_PULSES + 2U;
         ++index) {
      storage[index] = {0xA5A5, 0x5A5A};
    }
    size_t encoded_count = 0;
    TEST_ASSERT_TRUE(light_belt::encodeWs2811Rmt(
        pixels, count, light_belt::Ws2811ColorOrder::GRB,
        storage + 1, light_belt::WS2811_RMT_MAX_PULSES, &encoded_count));
    const size_t expected =
        static_cast<size_t>(count) * light_belt::WS2811_RMT_PULSES_PER_GROUP;
    TEST_ASSERT_EQUAL_UINT32(expected, encoded_count);
    TEST_ASSERT_EQUAL_UINT32(expected, light_belt::ws2811RmtPulseCount(count));
    TEST_ASSERT_EQUAL_HEX16(0xA5A5, storage[0].high_ticks);
    TEST_ASSERT_EQUAL_HEX16(0x5A5A, storage[0].low_ticks);
    TEST_ASSERT_EQUAL_HEX16(0xA5A5, storage[expected + 1U].high_ticks);
    TEST_ASSERT_EQUAL_HEX16(0x5A5A, storage[expected + 1U].low_ticks);
  }
}

void test_rmt_encoder_rejects_invalid_inputs_without_mutation() {
  const light_belt::RgbPixel pixel = {1, 2, 3};
  light_belt::Ws2811RmtPulse encoded[
      light_belt::WS2811_RMT_PULSES_PER_GROUP] = {};
  for (size_t index = 0;
       index < light_belt::WS2811_RMT_PULSES_PER_GROUP;
       ++index) {
    encoded[index] = {0xA5A5, 0x5A5A};
  }
  size_t encoded_count = 123;
  const size_t required = light_belt::ws2811RmtPulseCount(1);

  TEST_ASSERT_FALSE(light_belt::encodeWs2811Rmt(
      &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, required - 1U, &encoded_count));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Rmt(
      nullptr, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, required, &encoded_count));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Rmt(
      &pixel, 0, light_belt::Ws2811ColorOrder::RGB,
      encoded, required, &encoded_count));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Rmt(
      &pixel, light_belt::MAX_PIXELS_PER_OUTPUT + 1U,
      light_belt::Ws2811ColorOrder::RGB,
      encoded, required, &encoded_count));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Rmt(
      &pixel, 1, static_cast<light_belt::Ws2811ColorOrder>(99),
      encoded, required, &encoded_count));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Rmt(
      &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
      nullptr, required, &encoded_count));
  TEST_ASSERT_FALSE(light_belt::encodeWs2811Rmt(
      &pixel, 1, light_belt::Ws2811ColorOrder::RGB,
      encoded, required, nullptr));

  TEST_ASSERT_EQUAL_UINT32(123, encoded_count);
  TEST_ASSERT_EQUAL_HEX16(0xA5A5, encoded[0].high_ticks);
  TEST_ASSERT_EQUAL_HEX16(0x5A5A, encoded[0].low_ticks);
  TEST_ASSERT_EQUAL_HEX16(0xA5A5, encoded[required - 1U].high_ticks);
  TEST_ASSERT_EQUAL_HEX16(0x5A5A, encoded[required - 1U].low_ticks);
  TEST_ASSERT_EQUAL_UINT32(0, light_belt::ws2811RmtPulseCount(0));
  TEST_ASSERT_EQUAL_UINT32(
      0, light_belt::ws2811RmtPulseCount(
             light_belt::MAX_PIXELS_PER_OUTPUT + 1U));
}

}  // namespace

void setUp() {}
void tearDown() {}

int runTests() {
  UNITY_BEGIN();
  RUN_TEST(test_udp_v3_immediate_and_scheduled_frames_are_unambiguous);
  RUN_TEST(test_udp_v3_clock_beacon_has_fixed_broadcast_wire_contract);
  RUN_TEST(test_udp_v3_clock_beacon_rejects_length_header_and_crc_errors);
  RUN_TEST(test_presentation_clock_uses_window_minimum_and_spread);
  RUN_TEST(test_presentation_clock_lower_envelope_ignores_slow_outliers);
  RUN_TEST(test_default_presentation_clock_uses_bounded_32_sample_window);
  RUN_TEST(test_presentation_clock_readiness_checks_samples_age_and_uncertainty);
  RUN_TEST(test_presentation_clock_accepts_zero_policy_tolerances);
  RUN_TEST(test_presentation_clock_orders_by_host_time_and_reacquires_after_expiry);
  RUN_TEST(test_presentation_clock_deadline_boundaries_are_explicit);
  RUN_TEST(test_presentation_clock_rejects_unrepresentable_offsets_and_deadlines);
  RUN_TEST(test_transmit_start_compensates_wire_time_and_rejects_late_frames);
  RUN_TEST(test_runtime_scheduling_stats_are_independent_and_zero_initialized);
  RUN_TEST(test_node2_emergency_whitelist_accepts_only_exact_full_frames);
  RUN_TEST(test_identical_physical_payload_skip_requires_success_cache_and_no_recovery);
  RUN_TEST(test_node2_emergency_transition_graph_and_change_interval);
  RUN_TEST(test_node2_emergency_gate1m_payloads_and_edges);
  RUN_TEST(test_node8_emergency_policy_requires_exact20_and_usable19_graph);
  RUN_TEST(test_identical_logical_commit_advances_sequence_and_watchdog);
  RUN_TEST(test_udp_v3_golden_vector_copies_and_commits_only_after_success);
  RUN_TEST(test_scheduled_udp_v3_golden_vector_preserves_apply_deadline);
  RUN_TEST(test_owned_frame_survives_udp_buffer_reuse_and_uses_configured_order);
  RUN_TEST(test_one_two_and_three_outputs_remain_independent);
  RUN_TEST(test_invalid_incomplete_duplicate_and_oversized_frames_do_not_commit);
  RUN_TEST(test_duplicate_stale_and_wrap_sequences_use_only_committed_sequence);
  RUN_TEST(test_only_key_frame_sequence_one_starts_a_new_session);
  RUN_TEST(test_only_scheduled_continuations_require_admitted_session);
  RUN_TEST(test_session_recovery_requires_recent_scheduled_key_and_safe_deadline);
  RUN_TEST(test_recovery_sequence_reset_is_explicit_and_commits_only_on_success);
  RUN_TEST(test_key_frame_sequence_one_resets_committed_sequence_and_refreshes);
  RUN_TEST(test_timeout_black_commits_only_after_physical_success);
  RUN_TEST(test_udp_safe_state_commit_is_normalized_to_black_and_does_not_timeout);
  RUN_TEST(test_spi_encoder_exact_00_ff_aa_55_patterns_and_guards);
  RUN_TEST(test_spi_encoder_preserves_warm_rgb_values_and_reorders_grb_only);
  RUN_TEST(test_spi_encoder_lengths_for_1_10_20_40_and_100_groups);
  RUN_TEST(test_fixed_gpio4_spi4_encoder_uses_500us_guards_and_uniform_region);
  RUN_TEST(test_scheduled_production_spi4_wire_times_cover_installed_lengths);
  RUN_TEST(test_spi_encoder_rejects_invalid_inputs_without_touching_destination);
  RUN_TEST(test_spi_encoded_diagnostics_cover_buffer_and_uniform_groups);
  RUN_TEST(test_spi3_encoder_exact_00_ff_aa_55_patterns_and_guards);
  RUN_TEST(test_spi3_encoder_preserves_rgb_and_reorders_grb_only);
  RUN_TEST(test_spi3_encoder_lengths_for_1_10_20_40_and_100_groups);
  RUN_TEST(test_spi3_encoder_rejects_invalid_inputs_without_mutation);
  RUN_TEST(test_spi6_encoder_exact_vectors_guards_and_group_limits);
  RUN_TEST(test_parallel_spi_encoder_uses_qio_lane_masks_and_keeps_data3_low);
  RUN_TEST(test_parallel_spi_encoder_preserves_rgb_and_reorders_grb_only);
  RUN_TEST(test_parallel_spi_encoder_uses_longest_lane_and_black_padding);
  RUN_TEST(test_parallel_spi_encoder_rejects_without_mutating_outputs);
  RUN_TEST(test_rmt_encoder_exact_00_ff_aa_and_55_patterns);
  RUN_TEST(test_rmt_encoder_preserves_rgb_and_reorders_grb_only);
  RUN_TEST(test_rmt_encoder_lengths_for_1_10_20_40_and_100_groups);
  RUN_TEST(test_rmt_encoder_rejects_invalid_inputs_without_mutation);
  return UNITY_END();
}

#ifdef ARDUINO
void setup() { (void)runTests(); }
void loop() {}
#else
int main(int, char **) {
  return runTests();
}
#endif
