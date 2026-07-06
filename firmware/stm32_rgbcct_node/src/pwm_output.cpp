#include "pwm_output.h"

#include "config.h"

namespace light_belt {

namespace {

uint8_t lerpChannel(uint8_t from, uint8_t to, uint32_t elapsed, uint32_t total) {
  if (total == 0 || elapsed >= total) {
    return to;
  }
  const int32_t delta = static_cast<int32_t>(to) - static_cast<int32_t>(from);
  return static_cast<uint8_t>(
      static_cast<int32_t>(from) + (delta * static_cast<int32_t>(elapsed)) /
                                    static_cast<int32_t>(total));
}

}  // namespace

void PwmOutput::begin() {
  pinMode(PWM_PIN_R, OUTPUT);
  pinMode(PWM_PIN_G, OUTPUT);
  pinMode(PWM_PIN_B, OUTPUT);
  pinMode(PWM_PIN_WW, OUTPUT);
  pinMode(PWM_PIN_CW, OUTPUT);
  writeLevels(current_);
}

void PwmOutput::setTarget(const RgbCctFrame &frame, uint32_t now_ms) {
  start_ = current_;
  target_ = {frame.r, frame.g, frame.b, frame.warm_white, frame.cool_white};
  fade_start_ms_ = now_ms;
  fade_duration_ms_ = frame.fade_ms;
  if (fade_duration_ms_ == 0) {
    current_ = target_;
    writeLevels(current_);
  }
}

void PwmOutput::setBlack(uint32_t now_ms) {
  RgbCctFrame frame{};
  frame.fade_ms = 0;
  setTarget(frame, now_ms);
}

void PwmOutput::update(uint32_t now_ms) {
  if (fade_duration_ms_ == 0) {
    return;
  }
  const uint32_t elapsed = now_ms - fade_start_ms_;
  current_.r = lerpChannel(start_.r, target_.r, elapsed, fade_duration_ms_);
  current_.g = lerpChannel(start_.g, target_.g, elapsed, fade_duration_ms_);
  current_.b = lerpChannel(start_.b, target_.b, elapsed, fade_duration_ms_);
  current_.warm_white =
      lerpChannel(start_.warm_white, target_.warm_white, elapsed, fade_duration_ms_);
  current_.cool_white =
      lerpChannel(start_.cool_white, target_.cool_white, elapsed, fade_duration_ms_);
  writeLevels(current_);
  if (elapsed >= fade_duration_ms_) {
    fade_duration_ms_ = 0;
  }
}

void PwmOutput::writeLevels(const RgbCctLevels &levels) {
  analogWrite(PWM_PIN_R, levels.r);
  analogWrite(PWM_PIN_G, levels.g);
  analogWrite(PWM_PIN_B, levels.b);
  analogWrite(PWM_PIN_WW, levels.warm_white);
  analogWrite(PWM_PIN_CW, levels.cool_white);
}

}  // namespace light_belt
