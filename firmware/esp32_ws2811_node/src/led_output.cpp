#include "led_output.h"

#include <string.h>

namespace light_belt {

namespace {

constexpr OutputDescriptor kConfiguredOutputs[] = {
    {OUTPUT_0_ID, OUTPUT_0_GPIO, OUTPUT_0_PIXELS},
#if OUTPUT_COUNT >= 2
    {OUTPUT_1_ID, OUTPUT_1_GPIO, OUTPUT_1_PIXELS},
#endif
#if OUTPUT_COUNT >= 3
    {OUTPUT_2_ID, OUTPUT_2_GPIO, OUTPUT_2_PIXELS},
#endif
};

static_assert(OUTPUT_COUNT >= 1 && OUTPUT_COUNT <= MAX_OUTPUTS,
              "OUTPUT_COUNT must be 1, 2, or 3");

}  // namespace

LedOutput::LedOutput(RuntimeStats *stats)
    : stats_(stats), state_(kConfiguredOutputs, OUTPUT_COUNT) {}

bool LedOutput::begin() {
  if (!state_.configurationValid() ||
      !backend_.begin(kConfiguredOutputs, OUTPUT_COUNT)) {
    return false;
  }

  // DIR is wired directly to 3V3. Production controls one GPIO4 data path.
  const OwnedNodeFrame black = blackFrame();
  SpiRefreshReport first = transmit(black);
  if (!first.ok()) {
    cancelPrepared();
    return false;
  }
  delay(5);
  SpiRefreshReport second = transmit(black);
  if (!second.ok()) {
    cancelPrepared();
    return false;
  }
  state_.commitSafeBlack(millis());
  needs_safe_recovery_ = false;
  return true;
}

bool LedOutput::prepareFrame(const OwnedNodeFrame &frame) {
  // Invalid or failed preparation must not leave an older frame armed.
  cancelPrepared();
  if (!state_.isCandidateAcceptable(frame)) {
    return false;
  }

  const OwnedNodeFrame candidate = normalizedFrame(frame);
#if !defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  if (backend_.supportsScheduledApply()) {
    const SpiRefreshReport report = backend_.prepare(candidate);
    if (!report.ok()) {
      if (stats_ != nullptr) {
        stats_->output_errors.fetch_add(1);
      }
      backend_.cancelPrepared();
      return false;
    }
    backend_frame_prepared_ = true;
  }
#endif
  pending_frame_ = candidate;
  has_pending_frame_ = true;
  return true;
}

bool LedOutput::transmitPrepared(uint32_t now_ms, bool retry_on_failure) {
  if (!has_pending_frame_) {
    return false;
  }

  const bool had_sequence = state_.hasCommittedSequence();
  const uint32_t previous_sequence = state_.lastSequence();

  SpiRefreshReport report = transmitPendingBackend();
  if (!report.ok() && retry_on_failure) {
    if (stats_ != nullptr) {
      stats_->output_errors.fetch_add(1);
    }
    // Retry the same fully encoded logical frame once. No state was committed.
    report = transmitPendingBackend();
  }
  if (!report.ok()) {
    if (stats_ != nullptr) {
      stats_->output_errors.fetch_add(1);
    }
    cancelPrepared();
    needs_safe_recovery_ = !recoverCommittedOrBlack(now_ms);
    return false;
  }

  if (!state_.commitFrame(pending_frame_, now_ms)) {
    // This is a software invariant failure after a successful physical write.
    if (stats_ != nullptr) {
      stats_->invariant_errors.fetch_add(1);
    }
    cancelPrepared();
    needs_safe_recovery_ = !recoverCommittedOrBlack(now_ms);
    return false;
  }
  needs_safe_recovery_ = false;
  if (stats_ != nullptr) {
    stats_->refresh_ok.fetch_add(1);
    stats_->last_committed_sequence.store(pending_frame_.sequence);
    if (had_sequence &&
        static_cast<uint32_t>(pending_frame_.sequence - previous_sequence) !=
            1U) {
      stats_->display_sequence_gaps.fetch_add(1);
    }
    if ((pending_frame_.flags & UDP_V3_FLAG_SAFE_STATE) != 0) {
      stats_->safe_frames.fetch_add(1);
    }
  }
  cancelPrepared();
  return true;
}

void LedOutput::cancelPrepared() {
#if !defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  backend_.cancelPrepared();
#endif
  has_pending_frame_ = false;
  backend_frame_prepared_ = false;
}

bool LedOutput::hasPreparedFrame() const { return has_pending_frame_; }

bool LedOutput::supportsScheduledApply() const {
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  return false;
#else
  return backend_.supportsScheduledApply();
#endif
}

uint32_t LedOutput::preparedWireTimeUs() const {
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  return 0;
#else
  return has_pending_frame_ && backend_frame_prepared_
      ? backend_.preparedWireTimeUs()
      : 0;
#endif
}

bool LedOutput::acceptFrame(const OwnedNodeFrame &frame, uint32_t now_ms) {
  return prepareFrame(frame) && transmitPrepared(now_ms);
}

bool LedOutput::showBlack(uint32_t now_ms, bool timeout_generated) {
  // A timeout or explicit safe state always wins over a scheduled candidate.
  cancelPrepared();
  if (state_.safeBlackCommitted() && !needs_safe_recovery_) {
    return true;
  }
  const OwnedNodeFrame black = blackFrame();
  SpiRefreshReport report = transmit(black);
  if (!report.ok()) {
    if (stats_ != nullptr) {
      stats_->output_errors.fetch_add(1);
    }
    report = transmit(black);
  }
  if (!report.ok()) {
    if (stats_ != nullptr) {
      stats_->output_errors.fetch_add(1);
    }
    cancelPrepared();
    needs_safe_recovery_ = true;
    return false;
  }
  if (!state_.commitSafeBlack(now_ms)) {
    if (stats_ != nullptr) {
      stats_->invariant_errors.fetch_add(1);
    }
    needs_safe_recovery_ = true;
    return false;
  }
  needs_safe_recovery_ = false;
  if (timeout_generated && stats_ != nullptr) {
    stats_->timeout_black.fetch_add(1);
  }
  return true;
}

bool LedOutput::timedOut(uint32_t now_ms) const {
  return needs_safe_recovery_ || state_.timedOut(now_ms, SAFE_TIMEOUT_MS);
}

bool LedOutput::safeBlackCommitted() const {
  return state_.safeBlackCommitted() && !needs_safe_recovery_;
}

const OutputDescriptor *LedOutput::descriptors() const {
  return kConfiguredOutputs;
}

uint8_t LedOutput::outputCount() const { return state_.outputCount(); }

OwnedNodeFrame LedOutput::normalizedFrame(const OwnedNodeFrame &frame) const {
  OwnedNodeFrame normalized = frame;
  if ((normalized.flags & UDP_V3_FLAG_SAFE_STATE) != 0) {
    for (uint8_t index = 0; index < normalized.output_count; ++index) {
      memset(normalized.outputs[index].pixels, 0,
             sizeof(normalized.outputs[index].pixels));
    }
  }
  return normalized;
}

OwnedNodeFrame LedOutput::blackFrame() const {
  OwnedNodeFrame black{};
  black.node_id = NODE_ID;
  black.flags = UDP_V3_FLAG_SAFE_STATE;
  black.output_count = state_.outputCount();
  for (uint8_t index = 0; index < black.output_count; ++index) {
    black.outputs[index].descriptor = state_.descriptor(index);
  }
  return black;
}

SpiRefreshReport LedOutput::transmitPendingBackend() {
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  SpiRefreshReport report = backend_.refresh(pending_frame_);
#else
  SpiRefreshReport report = backend_frame_prepared_
      ? backend_.transmitPrepared()
      : backend_.refresh(pending_frame_);
#endif
  accountReport(report);
  return report;
}

SpiRefreshReport LedOutput::transmit(const OwnedNodeFrame &frame) {
  SpiRefreshReport report = backend_.refresh(frame);
  accountReport(report);
  return report;
}

bool LedOutput::recoverCommittedOrBlack(uint32_t now_ms) {
  cancelPrepared();
  const OwnedNodeFrame *committed = state_.committedFrame();
  SpiRefreshReport recovery =
      committed != nullptr ? transmit(*committed) : transmit(blackFrame());
  if (!recovery.ok()) {
    if (stats_ != nullptr) {
      stats_->output_errors.fetch_add(1);
    }
    cancelPrepared();
    return false;
  }
  if (committed == nullptr) {
    state_.commitSafeBlack(now_ms);
  }
  if (stats_ != nullptr) {
    stats_->rollback_ok.fetch_add(1);
  }
  return true;
}

void LedOutput::accountReport(const SpiRefreshReport &report) {
  if (stats_ != nullptr && report.successful_transactions != 0) {
    stats_->spi_transactions_ok.fetch_add(report.successful_transactions);
  }
}

}  // namespace light_belt
