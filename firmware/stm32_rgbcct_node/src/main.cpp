#include <Arduino.h>

#include "config.h"
#include "protocol.h"
#include "pwm_output.h"

using light_belt::PwmOutput;
using light_belt::RgbCctFrame;
using light_belt::Rs485FrameReader;

namespace {

PwmOutput pwm_output;
Rs485FrameReader frame_reader;
uint32_t last_valid_frame_ms = 0;
bool safe_state_applied = false;

}  // namespace

void setup() {
  pwm_output.begin();
  pwm_output.setBlack(millis());
  Serial1.setRx(UART_RX);
  Serial1.setTx(UART_TX);
  Serial1.begin(RS485_BAUDRATE);
  last_valid_frame_ms = millis();
}

void loop() {
  const uint32_t now_ms = millis();
  while (Serial1.available() > 0) {
    RgbCctFrame frame{};
    if (frame_reader.push(static_cast<uint8_t>(Serial1.read()), now_ms, &frame)) {
      pwm_output.setTarget(frame, now_ms);
      last_valid_frame_ms = now_ms;
      safe_state_applied = false;
    }
  }

  if (!safe_state_applied && now_ms - last_valid_frame_ms > SAFE_STATE_TIMEOUT_MS) {
    pwm_output.setBlack(now_ms);
    safe_state_applied = true;
  }
  pwm_output.update(now_ms);
}
