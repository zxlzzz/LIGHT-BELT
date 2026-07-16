#include "presentation_clock.h"

#include <limits.h>

namespace light_belt {

namespace {

bool differenceAsInt64(uint64_t left, uint64_t right, int64_t *out) {
  if (out == nullptr) {
    return false;
  }
  if (left >= right) {
    const uint64_t difference = left - right;
    if (difference > static_cast<uint64_t>(INT64_MAX)) {
      return false;
    }
    *out = static_cast<int64_t>(difference);
    return true;
  }

  const uint64_t difference = right - left;
  const uint64_t min_magnitude = static_cast<uint64_t>(INT64_MAX) + 1U;
  if (difference > min_magnitude) {
    return false;
  }
  if (difference == min_magnitude) {
    *out = INT64_MIN;
  } else {
    *out = -static_cast<int64_t>(difference);
  }
  return true;
}

uint64_t negativeMagnitude(int64_t value) {
  return static_cast<uint64_t>(-(value + 1)) + 1U;
}

}  // namespace

TransmitStart calculateTransmitStart(
    uint64_t local_deadline_us,
    uint32_t wire_time_us,
    uint64_t local_now_us,
    uint64_t late_tolerance_us) {
  if (wire_time_us == 0) {
    return {TransmitStartResult::InvalidWireTime, 0, 0};
  }
  if (local_deadline_us < wire_time_us) {
    return {TransmitStartResult::DeadlineUnderflow, 0, 0};
  }

  const uint64_t local_start_us = local_deadline_us - wire_time_us;
  const uint64_t start_lateness_us =
      local_now_us > local_start_us ? local_now_us - local_start_us : 0;
  if (start_lateness_us > late_tolerance_us) {
    return {
        TransmitStartResult::TooLate,
        local_start_us,
        start_lateness_us,
    };
  }
  return {
      TransmitStartResult::Ok,
      local_start_us,
      start_lateness_us,
  };
}

PresentationClock::PresentationClock(const PresentationClockConfig &config)
    : config_(config) {}

bool PresentationClock::configurationValid() const {
  return config_.window_size > 0 &&
         config_.window_size <= PRESENTATION_CLOCK_MAX_SAMPLES &&
         config_.min_samples > 0 &&
         config_.min_samples <= config_.window_size;
}

void PresentationClock::reset() {
  next_sample_ = 0;
  sample_count_ = 0;
  offset_us_ = 0;
  uncertainty_us_ = 0;
  last_local_receive_us_ = 0;
  last_host_monotonic_us_ = 0;
  last_beacon_sequence_ = 0;
  has_last_beacon_ = false;
}

bool PresentationClock::observeBeacon(
    uint32_t beacon_sequence,
    uint64_t host_monotonic_us,
    uint64_t local_receive_us) {
  if (!configurationValid()) {
    return false;
  }

  if (has_last_beacon_) {
    if (local_receive_us < last_local_receive_us_) {
      return false;
    }
    const bool expired =
        local_receive_us - last_local_receive_us_ > config_.max_age_us;
    if (host_monotonic_us <= last_host_monotonic_us_) {
      if (!expired || host_monotonic_us == last_host_monotonic_us_) {
        return false;
      }
      reset();
    } else if (expired) {
      reset();
    }
  }

  int64_t sample_offset = 0;
  if (!differenceAsInt64(
          local_receive_us, host_monotonic_us, &sample_offset)) {
    return false;
  }

  appendOffset(sample_offset);
  last_local_receive_us_ = local_receive_us;
  last_host_monotonic_us_ = host_monotonic_us;
  last_beacon_sequence_ = beacon_sequence;
  has_last_beacon_ = true;
  return true;
}

PresentationClockStatus PresentationClock::status(
    uint64_t local_now_us) const {
  if (!configurationValid()) {
    return PresentationClockStatus::InvalidConfiguration;
  }
  if (sample_count_ == 0) {
    return PresentationClockStatus::InsufficientSamples;
  }
  if (!has_last_beacon_ || local_now_us < last_local_receive_us_ ||
      local_now_us - last_local_receive_us_ > config_.max_age_us) {
    return PresentationClockStatus::Stale;
  }
  if (sample_count_ < config_.min_samples) {
    return PresentationClockStatus::InsufficientSamples;
  }
  if (uncertainty_us_ > config_.max_uncertainty_us) {
    return PresentationClockStatus::Uncertain;
  }
  return PresentationClockStatus::Ready;
}

ApplyDeadline PresentationClock::evaluateDeadline(
    uint64_t apply_at_host_us,
    uint64_t local_now_us) const {
  const PresentationClockStatus clock_status = status(local_now_us);
  if (clock_status != PresentationClockStatus::Ready) {
    return {
        ApplyDeadlineResult::ClockNotReady,
        clock_status,
        0,
    };
  }
  if (apply_at_host_us == 0) {
    return {
        ApplyDeadlineResult::InvalidApplyTime,
        clock_status,
        0,
    };
  }

  uint64_t local_deadline_us = 0;
  if (!convertHostToLocal(apply_at_host_us, &local_deadline_us)) {
    return {
        ApplyDeadlineResult::ConversionOutOfRange,
        clock_status,
        0,
    };
  }
  if (local_deadline_us < local_now_us &&
      local_now_us - local_deadline_us > config_.late_tolerance_us) {
    return {
        ApplyDeadlineResult::TooLate,
        clock_status,
        local_deadline_us,
    };
  }
  if (local_deadline_us > local_now_us &&
      local_deadline_us - local_now_us > config_.max_future_us) {
    return {
        ApplyDeadlineResult::TooFar,
        clock_status,
        local_deadline_us,
    };
  }
  return {
      ApplyDeadlineResult::Ok,
      clock_status,
      local_deadline_us,
  };
}

uint8_t PresentationClock::sampleCount() const {
  return sample_count_;
}

int64_t PresentationClock::offsetUs() const {
  return offset_us_;
}

uint64_t PresentationClock::uncertaintyUs() const {
  return uncertainty_us_;
}

uint64_t PresentationClock::lastLocalReceiveUs() const {
  return last_local_receive_us_;
}

uint64_t PresentationClock::lastHostMonotonicUs() const {
  return last_host_monotonic_us_;
}

uint32_t PresentationClock::lastBeaconSequence() const {
  return last_beacon_sequence_;
}

void PresentationClock::appendOffset(int64_t offset_us) {
  offsets_[next_sample_] = offset_us;
  next_sample_ = static_cast<uint8_t>(
      (next_sample_ + 1U) % config_.window_size);
  if (sample_count_ < config_.window_size) {
    ++sample_count_;
  }
  recomputeEstimate();
}

void PresentationClock::recomputeEstimate() {
  if (sample_count_ == 0) {
    offset_us_ = 0;
    uncertainty_us_ = 0;
    return;
  }

  int64_t ranked[PRESENTATION_CLOCK_MAX_SAMPLES] = {};
  for (uint8_t index = 0; index < sample_count_; ++index) {
    ranked[index] = offsets_[index];
  }
  for (uint8_t index = 1; index < sample_count_; ++index) {
    const int64_t candidate = ranked[index];
    uint8_t position = index;
    while (position > 0 && ranked[position - 1] > candidate) {
      ranked[position] = ranked[position - 1];
      --position;
    }
    ranked[position] = candidate;
  }

  const int64_t minimum = ranked[0];
  const uint8_t quorum_index = static_cast<uint8_t>(
      (sample_count_ < config_.min_samples ? sample_count_
                                           : config_.min_samples) -
      1U);
  const int64_t quorum_maximum = ranked[quorum_index];
  offset_us_ = minimum;
  uncertainty_us_ =
      static_cast<uint64_t>(quorum_maximum) - static_cast<uint64_t>(minimum);
}

bool PresentationClock::convertHostToLocal(
    uint64_t host_monotonic_us,
    uint64_t *local_monotonic_us) const {
  if (local_monotonic_us == nullptr) {
    return false;
  }
  if (offset_us_ >= 0) {
    const uint64_t positive_offset = static_cast<uint64_t>(offset_us_);
    if (host_monotonic_us > UINT64_MAX - positive_offset) {
      return false;
    }
    *local_monotonic_us = host_monotonic_us + positive_offset;
    return true;
  }

  const uint64_t magnitude = negativeMagnitude(offset_us_);
  if (host_monotonic_us < magnitude) {
    return false;
  }
  *local_monotonic_us = host_monotonic_us - magnitude;
  return true;
}

}  // namespace light_belt
