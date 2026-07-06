#include <Arduino.h>
#include <unity.h>

#include "golden_vectors.h"
#include "../src/protocol.h"

void test_udp_golden_vector_parses() {
  light_belt::UdpV2Frame frame{};
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::Ok),
      static_cast<int>(light_belt::parseUdpV2Frame(
          UDP_V2_GOLDEN_0,
          UDP_V2_GOLDEN_0_len,
          7,
          2,
          &frame)));
  TEST_ASSERT_EQUAL_UINT8(7, frame.node_id);
  TEST_ASSERT_EQUAL_UINT8(2, frame.flags);
  TEST_ASSERT_EQUAL_UINT32(0x01020304, frame.sequence);
  TEST_ASSERT_EQUAL_UINT16(2, frame.pixel_count);
  TEST_ASSERT_EQUAL_UINT16(6, frame.payload_len);
  TEST_ASSERT_EQUAL_UINT8(1, frame.payload[0]);
  TEST_ASSERT_EQUAL_UINT8(128, frame.payload[4]);
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_udp_golden_vector_parses);
  UNITY_END();
}

void loop() {}
