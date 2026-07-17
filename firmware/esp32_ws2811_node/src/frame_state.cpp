#include "frame_state.h"

#include <string.h>

namespace light_belt {

bool isSessionStartFrame(const OwnedNodeFrame &candidate) {
  return candidate.sequence == 1U &&
         (candidate.flags & UDP_V3_FLAG_KEY_FRAME) != 0;
}

bool isFrameSequenceAcceptable(
    const OwnedNodeFrame &candidate,
    bool has_previous_sequence,
    uint32_t previous_sequence) {
  return !has_previous_sequence || isSessionStartFrame(candidate) ||
         isNewerSequence(candidate.sequence, previous_sequence);
}

bool requiresAdmittedSession(const OwnedNodeFrame &candidate) {
  return (candidate.flags & UDP_V3_FLAG_SCHEDULED_APPLY) != 0 &&
         !isSessionStartFrame(candidate);
}

namespace {

constexpr RgbPixel kBlack = {0x00, 0x00, 0x00};
constexpr RgbPixel kBlue20 = {0x00, 0x00, 0x20};
constexpr RgbPixel kGreen20 = {0x00, 0x20, 0x00};
constexpr RgbPixel kOrange20_08 = {0x20, 0x08, 0x00};
constexpr RgbPixel kOrange20_10 = {0x20, 0x10, 0x00};

bool samePixel(const RgbPixel &left, const RgbPixel &right) {
  return left.r == right.r && left.g == right.g && left.b == right.b;
}

bool sameDescriptor(
    const OutputDescriptor &left,
    const OutputDescriptor &right) {
  return left.output_id == right.output_id && left.gpio == right.gpio &&
         left.pixel_count == right.pixel_count;
}

}  // namespace

EmergencyPayloadState classifyEmergencyPayload(
    const OwnedNodeFrame &candidate,
    const EmergencyOutputPolicy &policy) {
  if (policy.output.output_id != 1 || policy.output.gpio != 4 ||
      policy.output.pixel_count < 2 ||
      policy.output.pixel_count > MAX_PIXELS_PER_OUTPUT ||
      candidate.node_id != policy.node_id || candidate.output_count != 1 ||
      (candidate.flags & ~UDP_V3_ALLOWED_FLAGS) != 0 ||
      (candidate.flags & UDP_V3_FLAG_SCHEDULED_APPLY) != 0 ||
      !sameDescriptor(
          candidate.outputs[0].descriptor, policy.output)) {
    return {EmergencyPayloadKind::Unknown, 0};
  }

  const uint8_t pixel_count =
      static_cast<uint8_t>(policy.output.pixel_count);
  const uint8_t usable_count = static_cast<uint8_t>(pixel_count - 1U);

  const RgbPixel *pixels = candidate.outputs[0].pixels;
  if (!samePixel(pixels[0], kBlack)) {
    return {EmergencyPayloadKind::Unknown, 0};
  }

  uint8_t blue_dots = 0;
  uint8_t green_dots = 0;
  uint8_t orange_dots = 0;
  uint8_t blue_position = 0;
  uint8_t green_position = 0;
  uint8_t orange_position = 0;
  bool all_black = true;
  bool all_green = true;
  bool all_orange_08 = true;
  bool all_orange_10 = true;
  for (uint8_t group = 1; group < pixel_count; ++group) {
    const RgbPixel &pixel = pixels[group];
    const bool black = samePixel(pixel, kBlack);
    const bool blue = samePixel(pixel, kBlue20);
    const bool green = samePixel(pixel, kGreen20);
    const bool orange_08 = samePixel(pixel, kOrange20_08);
    const bool orange_10 = samePixel(pixel, kOrange20_10);
    if (!black && !blue && !green && !orange_08 && !orange_10) {
      return {EmergencyPayloadKind::Unknown, 0};
    }
    blue_position = blue ? static_cast<uint8_t>(group - 1U) : blue_position;
    green_position =
        green ? static_cast<uint8_t>(group - 1U) : green_position;
    orange_position =
        orange_08 ? static_cast<uint8_t>(group - 1U) : orange_position;
    blue_dots += blue ? 1U : 0U;
    green_dots += green ? 1U : 0U;
    orange_dots += orange_08 ? 1U : 0U;
    all_black = all_black && black;
    all_green = all_green && green;
    all_orange_08 = all_orange_08 && orange_08;
    all_orange_10 = all_orange_10 && orange_10;
  }

  if ((candidate.flags & UDP_V3_FLAG_SAFE_STATE) != 0) {
    return all_black
        ? EmergencyPayloadState{EmergencyPayloadKind::Black, 0}
        : EmergencyPayloadState{EmergencyPayloadKind::Unknown, 0};
  }
  if (all_black) {
    return {EmergencyPayloadKind::Black, 0};
  }
  if (all_green) {
    return {EmergencyPayloadKind::GreenUniform, 0};
  }
  if (all_orange_08) {
    return {EmergencyPayloadKind::WarmLow, 0};
  }
  if (all_orange_10) {
    return {EmergencyPayloadKind::WarmHigh, 0};
  }

  const bool one_blue_dot =
      blue_dots == 1 && green_dots == 0 && orange_dots == 0;
  const bool one_green_dot =
      green_dots == 1 && blue_dots == 0 && orange_dots == 0;
  const bool one_orange_dot =
      orange_dots == 1 && blue_dots == 0 && green_dots == 0;
  if (one_blue_dot || one_green_dot || one_orange_dot) {
    for (uint8_t group = 1; group < pixel_count; ++group) {
      const RgbPixel &pixel = pixels[group];
      if (!samePixel(pixel, kBlack) &&
          !(one_blue_dot && samePixel(pixel, kBlue20)) &&
          !(one_green_dot && samePixel(pixel, kGreen20)) &&
          !(one_orange_dot && samePixel(pixel, kOrange20_08))) {
        return {EmergencyPayloadKind::Unknown, 0};
      }
    }
    if (one_blue_dot) {
      return {EmergencyPayloadKind::BlueDot, blue_position};
    }
    if (one_green_dot) {
      return {EmergencyPayloadKind::GreenDot, green_position};
    }
    return {EmergencyPayloadKind::OrangeDot, orange_position};
  }

  if (green_dots == 0 && orange_dots == 0) {
    for (uint8_t phase = 0; phase < 3; ++phase) {
      bool matches = true;
      for (uint8_t position = 0; position < usable_count; ++position) {
        const bool expected_blue = position % 3U == phase;
        const RgbPixel &pixel = pixels[position + 1U];
        matches = matches && samePixel(
            pixel, expected_blue ? kBlue20 : kBlack);
      }
      if (matches) {
        return {EmergencyPayloadKind::BlueTheater, phase};
      }
    }
  }
  return {EmergencyPayloadKind::Unknown, 0};
}

bool isEmergencyFrameAllowed(
    const OwnedNodeFrame &candidate,
    const EmergencyOutputPolicy &policy) {
  return classifyEmergencyPayload(candidate, policy).kind !=
         EmergencyPayloadKind::Unknown;
}

bool isEmergencyTransitionAllowed(
    const OwnedNodeFrame &previous,
    const OwnedNodeFrame &candidate,
    const EmergencyOutputPolicy &policy) {
  const EmergencyPayloadState from =
      classifyEmergencyPayload(previous, policy);
  const EmergencyPayloadState to = classifyEmergencyPayload(candidate, policy);
  const uint8_t usable_count =
      static_cast<uint8_t>(policy.output.pixel_count - 1U);
  if (from.kind == EmergencyPayloadKind::Unknown ||
      to.kind == EmergencyPayloadKind::Unknown) {
    return false;
  }
  if (to.kind == EmergencyPayloadKind::Black) {
    return true;
  }
  if (from.kind == to.kind && from.position == to.position) {
    return true;
  }
  if (from.kind == EmergencyPayloadKind::Black) {
    return to.kind == EmergencyPayloadKind::WarmLow ||
           (to.kind == EmergencyPayloadKind::BlueDot && to.position == 0) ||
           (to.kind == EmergencyPayloadKind::OrangeDot && to.position == 0) ||
           to.kind == EmergencyPayloadKind::GreenUniform ||
           (to.kind == EmergencyPayloadKind::GreenDot && to.position == 0) ||
           (to.kind == EmergencyPayloadKind::BlueTheater && to.position == 0);
  }
  if (from.kind == EmergencyPayloadKind::WarmLow) {
    return to.kind == EmergencyPayloadKind::WarmHigh;
  }
  if (from.kind == EmergencyPayloadKind::WarmHigh) {
    return to.kind == EmergencyPayloadKind::WarmLow;
  }
  if (from.kind == EmergencyPayloadKind::BlueDot &&
      to.kind == EmergencyPayloadKind::BlueDot) {
    return to.position ==
           static_cast<uint8_t>((from.position + 1U) % usable_count);
  }
  if (from.kind == EmergencyPayloadKind::OrangeDot &&
      to.kind == EmergencyPayloadKind::OrangeDot) {
    return to.position ==
           static_cast<uint8_t>((from.position + 1U) % usable_count);
  }
  if (from.kind == EmergencyPayloadKind::GreenDot &&
      to.kind == EmergencyPayloadKind::GreenDot) {
    return to.position ==
           static_cast<uint8_t>((from.position + 1U) % usable_count);
  }
  if (from.kind == EmergencyPayloadKind::BlueTheater &&
      to.kind == EmergencyPayloadKind::BlueTheater) {
    return to.position == static_cast<uint8_t>((from.position + 1U) % 3U);
  }
  return false;
}

bool isEmergencyChangeIntervalAllowed(
    uint32_t previous_write_ms,
    uint32_t candidate_write_ms,
    bool payload_changed,
    bool safe_state) {
  return !payload_changed || safe_state ||
         static_cast<uint32_t>(candidate_write_ms - previous_write_ms) >=
             EMERGENCY_MIN_CHANGE_INTERVAL_MS;
}

bool physicalPixelPayloadsEqual(
    const OwnedNodeFrame &left,
    const OwnedNodeFrame &right) {
  if (left.output_count != right.output_count) {
    return false;
  }
  if (left.output_count == 0 || left.output_count > MAX_OUTPUTS) {
    return false;
  }
  for (uint8_t output = 0; output < left.output_count; ++output) {
    const OutputDescriptor &left_descriptor =
        left.outputs[output].descriptor;
    const OutputDescriptor &right_descriptor =
        right.outputs[output].descriptor;
    if (left_descriptor.pixel_count == 0 ||
        left_descriptor.pixel_count > MAX_PIXELS_PER_OUTPUT ||
        !sameDescriptor(left_descriptor, right_descriptor) ||
        memcmp(
            left.outputs[output].pixels,
            right.outputs[output].pixels,
            static_cast<size_t>(left_descriptor.pixel_count) *
                sizeof(RgbPixel)) != 0) {
      return false;
    }
  }
  return true;
}

bool canSkipPhysicalRefresh(
    const OwnedNodeFrame &candidate,
    const OwnedNodeFrame &last_physical,
    bool has_last_physical,
    bool safe_recovery_pending) {
  return has_last_physical && !safe_recovery_pending &&
         (candidate.flags & UDP_V3_FLAG_KEY_FRAME) == 0 &&
         physicalPixelPayloadsEqual(candidate, last_physical);
}

bool canSkipContentDedupeRefresh(
    const OwnedNodeFrame &candidate,
    const OwnedNodeFrame &last_physical,
    bool has_last_physical,
    bool safe_recovery_pending) {
  return (candidate.flags & UDP_V3_FLAG_SAFE_STATE) == 0 &&
         canSkipPhysicalRefresh(
             candidate, last_physical, has_last_physical,
             safe_recovery_pending);
}

bool isSessionRecoveryEligible(
    const OwnedNodeFrame &candidate,
    ApplyDeadlineResult deadline_result,
    PresentationClockStatus clock_status,
    uint64_t last_host_beacon_us,
    uint64_t max_host_distance_us) {
  const bool acquiring_clock =
      deadline_result == ApplyDeadlineResult::ClockNotReady &&
      (clock_status == PresentationClockStatus::InsufficientSamples ||
       clock_status == PresentationClockStatus::Uncertain);
  return acquiring_clock && isSessionStartFrame(candidate) &&
         (candidate.flags & UDP_V3_FLAG_SCHEDULED_APPLY) != 0 &&
         candidate.apply_at_us != 0 && last_host_beacon_us != 0 &&
         candidate.apply_at_us >= last_host_beacon_us &&
         candidate.apply_at_us - last_host_beacon_us <= max_host_distance_us;
}

bool isSessionGenerationAdmitted(
    uint32_t session_generation,
    uint32_t prepared_session_generation,
    uint32_t committed_session_generation) {
  return session_generation != 0 &&
         (prepared_session_generation == session_generation ||
          committed_session_generation == session_generation);
}

bool ScheduledSessionIdentity::remember(const OwnedNodeFrame &candidate) {
  if (!isSessionStartFrame(candidate) ||
      (candidate.flags & UDP_V3_FLAG_SCHEDULED_APPLY) == 0 ||
      candidate.apply_at_us == 0) {
    return false;
  }
  valid_ = true;
  apply_at_us_ = candidate.apply_at_us;
  media_timestamp_us_ = candidate.media_timestamp_us;
  return true;
}

bool ScheduledSessionIdentity::matches(
    const OwnedNodeFrame &candidate) const {
  return valid_ && isSessionStartFrame(candidate) &&
         (candidate.flags & UDP_V3_FLAG_SCHEDULED_APPLY) != 0 &&
         candidate.apply_at_us == apply_at_us_ &&
         candidate.media_timestamp_us == media_timestamp_us_;
}

void ScheduledSessionIdentity::clear() {
  valid_ = false;
  apply_at_us_ = 0;
  media_timestamp_us_ = 0;
}

bool ScheduledSessionIdentity::valid() const { return valid_; }

MultiOutputFrameState::MultiOutputFrameState(
    const OutputDescriptor *outputs, uint8_t output_count)
    : valid_(validateOutputDescriptors(outputs, output_count)),
      output_count_(valid_ ? output_count : 0) {
  if (!valid_) {
    return;
  }
  committed_.output_count = output_count_;
  for (uint8_t index = 0; index < output_count_; ++index) {
    outputs_[index] = outputs[index];
    committed_.outputs[index].descriptor = outputs[index];
  }
}

bool MultiOutputFrameState::configurationValid() const { return valid_; }

bool MultiOutputFrameState::isCandidateAcceptable(
    const OwnedNodeFrame &candidate,
    bool allow_sequence_reset) const {
  if (!valid_ || candidate.output_count != output_count_ ||
      (candidate.flags & ~UDP_V3_ALLOWED_FLAGS) != 0 ||
      (!allow_sequence_reset &&
       !isFrameSequenceAcceptable(candidate, has_sequence_, last_sequence_))) {
    return false;
  }
  for (uint8_t index = 0; index < output_count_; ++index) {
    const OutputDescriptor &configured = outputs_[index];
    const OutputDescriptor &received = candidate.outputs[index].descriptor;
    if (received.output_id != configured.output_id ||
        received.gpio != configured.gpio ||
        received.pixel_count != configured.pixel_count) {
      return false;
    }
  }
  return true;
}

bool MultiOutputFrameState::commitFrame(
    const OwnedNodeFrame &candidate,
    uint32_t accepted_at_ms,
    bool allow_sequence_reset) {
  if (!isCandidateAcceptable(candidate, allow_sequence_reset)) {
    return false;
  }
  committed_ = candidate;
  const bool safe_state =
      (candidate.flags & UDP_V3_FLAG_SAFE_STATE) != 0;
  if (safe_state) {
    for (uint8_t index = 0; index < output_count_; ++index) {
      memset(
          committed_.outputs[index].pixels,
          0,
          sizeof(committed_.outputs[index].pixels));
    }
  }
  has_committed_frame_ = true;
  has_sequence_ = true;
  last_sequence_ = candidate.sequence;
  has_accepted_frame_ = true;
  safe_black_committed_ = safe_state;
  last_accepted_ms_ = accepted_at_ms;
  last_committed_ms_ = accepted_at_ms;
  ++refresh_count_;
  return true;
}

bool MultiOutputFrameState::commitSafeBlack(uint32_t committed_at_ms) {
  if (!valid_) {
    return false;
  }

  if (!has_committed_frame_) {
    committed_ = {};
    committed_.output_count = output_count_;
    for (uint8_t index = 0; index < output_count_; ++index) {
      committed_.outputs[index].descriptor = outputs_[index];
    }
  } else {
    for (uint8_t index = 0; index < output_count_; ++index) {
      memset(
          committed_.outputs[index].pixels,
          0,
          sizeof(committed_.outputs[index].pixels));
    }
  }
  committed_.flags = UDP_V3_FLAG_SAFE_STATE;
  has_committed_frame_ = true;
  safe_black_committed_ = true;
  last_committed_ms_ = committed_at_ms;
  ++refresh_count_;
  return true;
}

bool MultiOutputFrameState::timedOut(
    uint32_t now_ms, uint32_t timeout_ms) const {
  return has_accepted_frame_ && !safe_black_committed_ &&
         static_cast<uint32_t>(now_ms - last_accepted_ms_) > timeout_ms;
}

const OutputDescriptor &MultiOutputFrameState::descriptor(
    uint8_t output_index) const {
  return outputs_[output_index];
}

const RgbPixel *MultiOutputFrameState::pixels(uint8_t output_index) const {
  return committed_.outputs[output_index].pixels;
}

const OwnedNodeFrame *MultiOutputFrameState::committedFrame() const {
  return has_committed_frame_ ? &committed_ : nullptr;
}

uint8_t MultiOutputFrameState::outputCount() const { return output_count_; }

uint32_t MultiOutputFrameState::refreshCount() const { return refresh_count_; }

bool MultiOutputFrameState::hasAcceptedFrame() const {
  return has_accepted_frame_;
}

bool MultiOutputFrameState::hasCommittedSequence() const {
  return has_sequence_;
}

uint32_t MultiOutputFrameState::lastSequence() const { return last_sequence_; }

bool MultiOutputFrameState::safeBlackCommitted() const {
  return safe_black_committed_;
}

}  // namespace light_belt
