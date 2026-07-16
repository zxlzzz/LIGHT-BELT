#ifndef LIGHT_BELT_ESP32_FRAME_STATE_H
#define LIGHT_BELT_ESP32_FRAME_STATE_H

#include <stdint.h>

#include "owned_frame.h"

namespace light_belt {

// A new Host UDP v3 output starts exactly once with KEY_FRAME/sequence 1.
// No other flag/sequence combination is allowed to reset an existing session.
bool isSessionStartFrame(const OwnedNodeFrame &candidate);
bool isFrameSequenceAcceptable(
    const OwnedNodeFrame &candidate,
    bool has_previous_sequence,
    uint32_t previous_sequence);

// Generation zero is the startup sentinel, not an admitted Host session.
// Once a KEY has been fully prepared, later complete frames may recover the
// session even if that KEY's timed physical transaction fails.
bool isSessionGenerationAdmitted(
    uint32_t session_generation,
    uint32_t prepared_session_generation,
    uint32_t committed_session_generation);

// Network-task-local identity for redundant scheduled KEY packets. Clearing
// it after an output-stage failure allows a later copy of the same KEY to be
// treated as a retry instead of a duplicate.
class ScheduledSessionIdentity {
 public:
  bool remember(const OwnedNodeFrame &candidate);
  bool matches(const OwnedNodeFrame &candidate) const;
  void clear();
  bool valid() const;

 private:
  bool valid_ = false;
  uint64_t apply_at_us_ = 0;
  uint64_t media_timestamp_us_ = 0;
};

// Tracks only frames proven visible by the physical backend. Candidate
// validation never mutates committed state.
class MultiOutputFrameState {
 public:
  MultiOutputFrameState(const OutputDescriptor *outputs, uint8_t output_count);

  bool configurationValid() const;
  bool isCandidateAcceptable(const OwnedNodeFrame &candidate) const;

  // Call commitFrame only after every configured physical output succeeded.
  bool commitFrame(const OwnedNodeFrame &candidate, uint32_t accepted_at_ms);
  // Call commitSafeBlack only after a complete physical black refresh.
  bool commitSafeBlack(uint32_t committed_at_ms);

  bool timedOut(uint32_t now_ms, uint32_t timeout_ms) const;

  const OutputDescriptor &descriptor(uint8_t output_index) const;
  const RgbPixel *pixels(uint8_t output_index) const;
  const OwnedNodeFrame *committedFrame() const;
  uint8_t outputCount() const;
  uint32_t refreshCount() const;
  bool hasAcceptedFrame() const;
  bool hasCommittedSequence() const;
  uint32_t lastSequence() const;
  bool safeBlackCommitted() const;

 private:
  bool valid_ = false;
  uint8_t output_count_ = 0;
  OutputDescriptor outputs_[MAX_OUTPUTS] = {};
  OwnedNodeFrame committed_ = {};
  bool has_committed_frame_ = false;
  bool has_sequence_ = false;
  uint32_t last_sequence_ = 0;
  bool has_accepted_frame_ = false;
  bool safe_black_committed_ = false;
  uint32_t last_accepted_ms_ = 0;
  uint32_t last_committed_ms_ = 0;
  uint32_t refresh_count_ = 0;
};

}  // namespace light_belt

#endif
