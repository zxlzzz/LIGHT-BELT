#ifndef LIGHT_BELT_ESP32_PRESENTATION_CLOCK_H
#define LIGHT_BELT_ESP32_PRESENTATION_CLOCK_H

#include <stddef.h>
#include <stdint.h>

namespace light_belt {

static constexpr uint8_t PRESENTATION_CLOCK_MAX_SAMPLES = 32;

struct PresentationClockConfig {
  uint8_t window_size = 8;
  uint8_t min_samples = 3;
  uint64_t max_age_us = 2000000;
  uint64_t max_uncertainty_us = 5000;
  uint64_t late_tolerance_us = 2000;
  uint64_t max_future_us = 100000;
};

enum class PresentationClockStatus {
  Ready,
  InvalidConfiguration,
  InsufficientSamples,
  Stale,
  Uncertain,
};

enum class ApplyDeadlineResult {
  Ok,
  ClockNotReady,
  InvalidApplyTime,
  ConversionOutOfRange,
  TooLate,
  TooFar,
};

struct ApplyDeadline {
  ApplyDeadlineResult result;
  PresentationClockStatus clock_status;
  uint64_t local_deadline_us;
};

enum class TransmitStartResult {
  Ok,
  InvalidWireTime,
  DeadlineUnderflow,
  TooLate,
};

struct TransmitStart {
  TransmitStartResult result;
  uint64_t local_start_us;
  uint64_t start_lateness_us;
};

// Converts a common visible-latch completion deadline into the start time for
// one strip's encoded wire length. A slightly late start remains usable within
// the explicit tolerance; larger misses are dropped instead of displayed out
// of step.
TransmitStart calculateTransmitStart(
    uint64_t local_deadline_us,
    uint32_t wire_time_us,
    uint64_t local_now_us,
    uint64_t late_tolerance_us);

// Estimates local_monotonic_us - host_monotonic_us from one-way beacon
// samples. The minimum offset in the current window is the lower-envelope
// estimate. Readiness uses the spread of the lowest min_samples offsets, so a
// quorum of low-delay samples is required while isolated slow packets do not
// invalidate the entire window.
class PresentationClock {
 public:
  explicit PresentationClock(
      const PresentationClockConfig &config = PresentationClockConfig{});

  bool configurationValid() const;
  void reset();

  // Host time must increase strictly while the clock is fresh. Beacon
  // sequence is retained for diagnostics but may restart independently when
  // the Host process restarts. After expiry, a smaller Host timestamp starts
  // a new epoch, allowing recovery from a Host-machine reboot.
  bool observeBeacon(
      uint32_t beacon_sequence,
      uint64_t host_monotonic_us,
      uint64_t local_receive_us);

  PresentationClockStatus status(uint64_t local_now_us) const;
  ApplyDeadline evaluateDeadline(
      uint64_t apply_at_host_us,
      uint64_t local_now_us) const;

  uint8_t sampleCount() const;
  int64_t offsetUs() const;
  uint64_t uncertaintyUs() const;
  uint64_t lastLocalReceiveUs() const;
  uint64_t lastHostMonotonicUs() const;
  uint32_t lastBeaconSequence() const;

 private:
  void appendOffset(int64_t offset_us);
  void recomputeEstimate();
  bool convertHostToLocal(
      uint64_t host_monotonic_us,
      uint64_t *local_monotonic_us) const;

  PresentationClockConfig config_;
  int64_t offsets_[PRESENTATION_CLOCK_MAX_SAMPLES] = {};
  uint8_t next_sample_ = 0;
  uint8_t sample_count_ = 0;
  int64_t offset_us_ = 0;
  uint64_t uncertainty_us_ = 0;
  uint64_t last_local_receive_us_ = 0;
  uint64_t last_host_monotonic_us_ = 0;
  uint32_t last_beacon_sequence_ = 0;
  bool has_last_beacon_ = false;
};

}  // namespace light_belt

#endif
