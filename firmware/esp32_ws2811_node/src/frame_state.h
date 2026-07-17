#ifndef LIGHT_BELT_ESP32_FRAME_STATE_H
#define LIGHT_BELT_ESP32_FRAME_STATE_H

#include <stdint.h>

#include "owned_frame.h"
#include "presentation_clock.h"

namespace light_belt {

// A new Host UDP v3 output starts exactly once with KEY_FRAME/sequence 1.
// No other flag/sequence combination is allowed to reset an existing session.
bool isSessionStartFrame(const OwnedNodeFrame &candidate);
bool isFrameSequenceAcceptable(
    const OwnedNodeFrame &candidate,
    bool has_previous_sequence,
    uint32_t previous_sequence);

// Scheduled continuation frames depend on an admitted KEY generation.
// Immediate frames are complete snapshots and may establish receiver state
// from the first datagram that arrives, even if sequence 1 was lost in UDP.
bool requiresAdmittedSession(const OwnedNodeFrame &candidate);

struct EmergencyOutputPolicy {
  uint8_t node_id;
  OutputDescriptor output;
};

// An emergency image accepts only the exact physical topology compiled for
// that node and the bounded payload graph below.
bool isEmergencyFrameAllowed(
    const OwnedNodeFrame &candidate,
    const EmergencyOutputPolicy &policy);

enum class EmergencyPayloadKind : uint8_t {
  Unknown = 0,
  Black,
  WarmLow,
  WarmHigh,
  GreenUniform,
  BlueDot,
  OrangeDot,
  GreenDot,
  BlueTheater,
};

struct EmergencyPayloadState {
  EmergencyPayloadKind kind;
  uint8_t position;
};

constexpr uint32_t EMERGENCY_MIN_CHANGE_INTERVAL_MS = 150;

EmergencyPayloadState classifyEmergencyPayload(
    const OwnedNodeFrame &candidate,
    const EmergencyOutputPolicy &policy);
bool isEmergencyTransitionAllowed(
    const OwnedNodeFrame &previous,
    const OwnedNodeFrame &candidate,
    const EmergencyOutputPolicy &policy);
bool isEmergencyChangeIntervalAllowed(
    uint32_t previous_write_ms,
    uint32_t candidate_write_ms,
    bool payload_changed,
    bool safe_state);

// Physical-payload equality excludes sequence, timestamps, and flags. A skip
// is permitted only when a prior successful backend write established the
// command-side cache
// and no safe-state recovery is pending. A KEY always writes physically so a
// new Host session can rebuild the command-side cache.
bool physicalPixelPayloadsEqual(
    const OwnedNodeFrame &left,
    const OwnedNodeFrame &right);
bool canSkipPhysicalRefresh(
    const OwnedNodeFrame &candidate,
    const OwnedNodeFrame &last_physical,
    bool has_last_physical,
    bool safe_recovery_pending);

// The unrestricted diagnostic also forces SAFE physically. This keeps its
// exit black independent of an earlier identical command-side cache entry.
bool canSkipContentDedupeRefresh(
    const OwnedNodeFrame &candidate,
    const OwnedNodeFrame &last_physical,
    bool has_last_physical,
    bool safe_recovery_pending);

// A session-start packet rejected while the clock is still acquiring may be
// encoded as a preparation-only admission when it is a complete scheduled KEY
// with a recent Host deadline. It is then cancelled without touching GPIO.
bool isSessionRecoveryEligible(
    const OwnedNodeFrame &candidate,
    ApplyDeadlineResult deadline_result,
    PresentationClockStatus clock_status,
    uint64_t last_host_beacon_us,
    uint64_t max_host_distance_us);

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
  bool isCandidateAcceptable(
      const OwnedNodeFrame &candidate,
      bool allow_sequence_reset = false) const;

  // Call commitFrame only after every configured physical output succeeded,
  // or after exact equality with a cache established by such a success.
  bool commitFrame(
      const OwnedNodeFrame &candidate,
      uint32_t accepted_at_ms,
      bool allow_sequence_reset = false);
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
