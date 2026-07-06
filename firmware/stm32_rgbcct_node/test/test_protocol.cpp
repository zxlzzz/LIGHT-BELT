#include <Arduino.h>
#include <unity.h>

#include "golden_vectors.h"
#include "../src/config.h"
#include "../src/protocol.h"

void test_rs485_golden_vector_parses() {
  light_belt::RgbCctFrame frame{};
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::Ok),
      static_cast<int>(light_belt::parseRs485V2Frame(
          RS485_V2_GOLDEN_0,
          RS485_V2_GOLDEN_0_len,
          3,
          BROADCAST_NODE_ID,
          &frame)));
  TEST_ASSERT_EQUAL_UINT8(3, frame.node_id);
  TEST_ASSERT_EQUAL_UINT8(0xFF, frame.sequence);
  TEST_ASSERT_EQUAL_UINT8(17, frame.r);
  TEST_ASSERT_EQUAL_UINT8(34, frame.g);
  TEST_ASSERT_EQUAL_UINT8(51, frame.b);
  TEST_ASSERT_EQUAL_UINT8(68, frame.warm_white);
  TEST_ASSERT_EQUAL_UINT8(85, frame.cool_white);
  TEST_ASSERT_EQUAL_UINT16(1000, frame.fade_ms);
  TEST_ASSERT_EQUAL_UINT8(1, frame.flags);
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_rs485_golden_vector_parses);
  UNITY_END();
}

void loop() {}
