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
    const OwnedNodeFrame &candidate) const {
  if (!valid_ || candidate.output_count != output_count_ ||
      (candidate.flags & ~UDP_V3_ALLOWED_FLAGS) != 0 ||
      !isFrameSequenceAcceptable(candidate, has_sequence_, last_sequence_)) {
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
    const OwnedNodeFrame &candidate, uint32_t accepted_at_ms) {
  if (!isCandidateAcceptable(candidate)) {
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
