#ifndef LIGHT_BELT_ESP32_RUNTIME_STATS_H
#define LIGHT_BELT_ESP32_RUNTIME_STATS_H

#include <atomic>
#include <stdint.h>

namespace light_belt {

struct RuntimeStats {
  std::atomic<uint32_t> datagrams_received{0};
  std::atomic<uint32_t> oversized_rejected{0};
  std::atomic<uint32_t> read_rejected{0};
  std::atomic<uint32_t> parse_rejected{0};
  std::atomic<uint32_t> state_rejected{0};
  std::atomic<uint32_t> clock_beacons_received{0};
  std::atomic<uint32_t> clock_beacons_accepted{0};
  std::atomic<uint32_t> clock_beacons_rejected{0};
  std::atomic<uint32_t> clock_samples{0};
  std::atomic<uint32_t> clock_uncertainty_us{0};
  std::atomic<uint32_t> clock_ready{0};
  std::atomic<uint32_t> scheduled_queued{0};
  std::atomic<uint32_t> scheduled_committed{0};
  std::atomic<uint32_t> scheduled_dropped{0};
  std::atomic<uint32_t> clock_not_ready_dropped{0};
  std::atomic<uint32_t> scheduled_too_late_dropped{0};
  std::atomic<uint32_t> scheduled_too_far_dropped{0};
  std::atomic<uint32_t> scheduled_invalid_dropped{0};
  std::atomic<uint32_t> scheduled_start_late_dropped{0};
  std::atomic<uint32_t> scheduled_cancelled{0};
  std::atomic<uint32_t> session_key_duplicates{0};
  std::atomic<uint32_t> immediate_dropped{0};
  std::atomic<int32_t> last_deadline_error_us{0};
  std::atomic<uint32_t> frames_queued{0};
  std::atomic<uint32_t> queue_overwritten{0};
  std::atomic<uint32_t> rx_sequence_gaps{0};
  std::atomic<uint32_t> display_sequence_gaps{0};
  std::atomic<uint32_t> refresh_attempts{0};
  std::atomic<uint32_t> refresh_ok{0};
  std::atomic<uint32_t> identical_skipped{0};
  std::atomic<uint32_t> physical_offset_waits{0};
  std::atomic<uint32_t> physical_offset_cancelled{0};
  std::atomic<uint32_t> emergency_payload_rejected{0};
  std::atomic<uint32_t> spi_transactions_ok{0};
  std::atomic<uint32_t> encoded_hash_checks{0};
  std::atomic<uint32_t> encoded_hash_mismatches{0};
  std::atomic<uint32_t> uniform_frame_checks{0};
  std::atomic<uint32_t> uniform_frame_mismatches{0};
  std::atomic<uint32_t> output_errors{0};
  std::atomic<uint32_t> invariant_errors{0};
  std::atomic<uint32_t> rollback_ok{0};
  std::atomic<uint32_t> safe_frames{0};
  std::atomic<uint32_t> timeout_black{0};
  std::atomic<uint32_t> wifi_reconnects{0};
  std::atomic<uint32_t> network_config_errors{0};
  std::atomic<uint32_t> ip_mismatches{0};
  std::atomic<uint32_t> udp_bind_errors{0};
  std::atomic<uint32_t> wifi_connected{0};
  std::atomic<uint32_t> udp_bound{0};
  std::atomic<uint32_t> last_received_sequence{0};
  std::atomic<uint32_t> last_committed_sequence{0};
};

}  // namespace light_belt

#endif
