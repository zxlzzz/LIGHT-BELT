#ifndef LIGHT_BELT_ESP32_LED_OUTPUT_H
#define LIGHT_BELT_ESP32_LED_OUTPUT_H

#include <Arduino.h>
#include <stdint.h>

#include "config.h"
#include "frame_state.h"
#include "owned_frame.h"
#include "protocol.h"
#include "runtime_stats.h"
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC) || \
    defined(LIGHT_BELT_FASTLED_GPIO4_IMMEDIATE_AB)
#include "fastled_ws2811_backend.h"
#else
#include "spi_ws2811_backend.h"
#endif

namespace light_belt {

class LedOutput {
 public:
  explicit LedOutput(RuntimeStats *stats);

  bool begin();
  // prepareFrame performs validation and memory-only encoding on the
  // scheduled production backend. State is committed only by a successful
  // transmitPrepared call.
  bool prepareFrame(
      const OwnedNodeFrame &frame,
      bool allow_sequence_reset = false);
  bool transmitPrepared(uint32_t now_ms, bool retry_on_failure = true);
  void cancelPrepared();
  bool hasPreparedFrame() const;
#if defined(LIGHT_BELT_CONTENT_DEDUPE_HOST_WRITE_OFFSET_US)
  bool physicalWritePending() const;
#endif
  bool supportsScheduledApply() const;
  uint32_t preparedWireTimeUs() const;
  bool acceptFrame(const OwnedNodeFrame &frame, uint32_t now_ms);
  bool showBlack(uint32_t now_ms, bool timeout_generated);
  bool timedOut(uint32_t now_ms) const;
  bool safeBlackCommitted() const;

  const OutputDescriptor *descriptors() const;
  uint8_t outputCount() const;

 private:
  OwnedNodeFrame normalizedFrame(const OwnedNodeFrame &frame) const;
  OwnedNodeFrame blackFrame() const;
  SpiRefreshReport transmitPendingBackend();
  SpiRefreshReport transmit(const OwnedNodeFrame &frame);
  bool recoverCommittedOrBlack(uint32_t now_ms);
  void accountReport(const SpiRefreshReport &report);
#if defined(LIGHT_BELT_EMERGENCY_CHANGE_ONLY_AB) || \
    defined(LIGHT_BELT_CONTENT_DEDUPE_AB)
  void rememberPhysicalPayload(const OwnedNodeFrame &frame);
#endif

  RuntimeStats *stats_;
  MultiOutputFrameState state_;
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC) || \
    defined(LIGHT_BELT_FASTLED_GPIO4_IMMEDIATE_AB)
  FastLedWs2811Backend backend_;
#else
  SpiWs2811Backend backend_;
#endif
  OwnedNodeFrame pending_frame_ = {};
  bool has_pending_frame_ = false;
  bool pending_allows_sequence_reset_ = false;
  bool backend_frame_prepared_ = false;
  bool needs_safe_recovery_ = false;
#if defined(LIGHT_BELT_EMERGENCY_CHANGE_ONLY_AB) || \
    defined(LIGHT_BELT_CONTENT_DEDUPE_AB)
  OwnedNodeFrame last_physical_frame_ = {};
  bool has_last_physical_frame_ = false;
  bool pending_physical_identical_ = false;
#endif
#if defined(LIGHT_BELT_EMERGENCY_CHANGE_ONLY_AB)
  uint32_t last_physical_write_ms_ = 0;
#endif
};

}  // namespace light_belt

#endif
