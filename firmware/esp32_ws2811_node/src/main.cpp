#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include <esp_timer.h>
#include <atomic>
#include <string.h>

#include "config.h"
#include "led_output.h"
#include "owned_frame.h"
#include "presentation_clock.h"
#include "protocol.h"
#include "runtime_stats.h"
#if defined(LIGHT_BELT_QIO_DIAGNOSTIC)
#include "ws2811_parallel_spi_encoder.h"
#endif
#if defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC)
#include "ws2811_spi3_encoder.h"
#endif
#if defined(LIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC)
#include "ws2811_spi6_encoder.h"
#endif
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
constexpr const char *kBackendName = "fastled_rmt4_builtin_gpio4_gpio5_diagnostic";
constexpr uint32_t kBackendClockHz = 800000;
#elif defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
#include "ws2811_rmt_encoder.h"
#endif
#include "ws2811_spi_encoder.h"

namespace {

WiFiUDP udp;
light_belt::RuntimeStats runtime_stats;
light_belt::LedOutput led_output(&runtime_stats);

struct QueuedNodeFrame {
  light_belt::OwnedNodeFrame frame;
  uint32_t session_generation;
  uint64_t local_deadline_us;
};

QueueHandle_t frame_queue = nullptr;
std::atomic<uint32_t> announced_session_generation{0};
std::atomic<uint32_t> prepared_session_generation{0};
std::atomic<uint32_t> committed_session_generation{0};
uint8_t packet_buffer[light_belt::UDP_V3_MAX_PACKET_LEN];
bool runtime_ready = false;

constexpr uint32_t kStatsIntervalMs = 5000;
constexpr uint32_t kWifiRetryMs = 10000;
constexpr uint32_t kSafeRetryMs = 100;
constexpr uint32_t kOutputPollMs = 20;
constexpr uint64_t kScheduledLateToleranceUs = 2000;
constexpr uint64_t kFinalScheduleSpinUs = 250;
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
constexpr const char *kBackendName = "fastled_rmt4_builtin_gpio4_gpio5_diagnostic";
constexpr uint32_t kBackendClockHz = 800000;
#elif defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
constexpr const char *kBackendName =
    "fixed_gpio5_rmt0_gpio4_gpio6_disabled_diagnostic";
constexpr uint32_t kBackendClockHz = light_belt::WS2811_RMT_TICK_HZ;
#elif defined(LIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC)
constexpr const char *kBackendName = "gpio5_spi3_5m_6bit_short_t0_diagnostic";
constexpr uint32_t kBackendClockHz = light_belt::WS2811_SPI_CLOCK_HZ;
#elif defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC)
constexpr const char *kBackendName = "gpio5_spi3_2m4_3bit_diagnostic";
constexpr uint32_t kBackendClockHz = light_belt::WS2811_SPI_CLOCK_HZ;
#elif defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC) && \
    defined(LIGHT_BELT_HYBRID_SPI_HOST_SWAP)
constexpr const char *kBackendName = "spi_hosts_swapped_fixed_diagnostic";
constexpr uint32_t kBackendClockHz = light_belt::WS2811_SPI_CLOCK_HZ;
#elif defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
constexpr const char *kBackendName = "spi2_spi3_rmt_fixed_diagnostic";
constexpr uint32_t kBackendClockHz = light_belt::WS2811_SPI_CLOCK_HZ;
#elif defined(LIGHT_BELT_QIO_DIAGNOSTIC)
constexpr const char *kBackendName = "spi_dma_qio_parallel_diagnostic";
constexpr uint32_t kBackendClockHz =
    light_belt::WS2811_PARALLEL_SPI_CLOCK_HZ;
#elif defined(LIGHT_BELT_NODE2_GPIO4_STRIP42_DIAGNOSTIC)
constexpr const char *kBackendName = "fixed_gpio4_strip42_20_group_diagnostic";
constexpr uint32_t kBackendClockHz = light_belt::WS2811_SPI_CLOCK_HZ;
#elif defined(LIGHT_BELT_FIXED_GPIO4_DIAGNOSTIC)
constexpr const char *kBackendName = "spi_dma_fixed_gpio4_diagnostic";
constexpr uint32_t kBackendClockHz = light_belt::WS2811_SPI_CLOCK_HZ;
#elif defined(LIGHT_BELT_FIXED_GPIO4_SPI)
constexpr const char *kBackendName = "spi_dma_fixed_gpio4";
constexpr uint32_t kBackendClockHz = light_belt::WS2811_SPI_CLOCK_HZ;
#else
constexpr const char *kBackendName = "spi_dma";
constexpr uint32_t kBackendClockHz = light_belt::WS2811_SPI_CLOCK_HZ;
#endif

bool hasPlaceholderWifi() {
  return strcmp(WIFI_SSID, "PLACEHOLDER_SSID") == 0 ||
         strcmp(WIFI_PASSWORD, "PLACEHOLDER_PASSWORD") == 0;
}

void printStartupIdentity() {
  Serial.printf(
      "node_start node_id=%u outputs=%u dir=3v3 backend=%s "
      "spi_hz=%lu expected_ip=%u.%u.%u.%u color_order=%s\n",
      NODE_ID, led_output.outputCount(), kBackendName,
      static_cast<unsigned long>(kBackendClockHz),
      WIFI_IPV4_A, WIFI_IPV4_B, WIFI_IPV4_C, NODE_IPV4_D,
#if WS2811_COLOR_ORDER == WS2811_COLOR_ORDER_GRB
      "GRB"
#else
      "RGB"
#endif
  );
  for (uint8_t index = 0; index < led_output.outputCount(); ++index) {
    const light_belt::OutputDescriptor &output = led_output.descriptors()[index];
    Serial.printf("node_output id=%u gpio=%u groups=%u\n", output.output_id,
                  output.gpio, output.pixel_count);
  }
#if defined(LIGHT_BELT_FASTLED_NODE2_DIAGNOSTIC)
  Serial.println(
      "node_timing transport=fastled_rmt4_builtin ws_hz=800000 "
      "gpio4=enabled gpio5=enabled gpio6=disabled brightness=255 dither=0");
#elif defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
  Serial.printf(
      "node_timing gpio4_transport=disabled gpio4_level=0 "
      "gpio5_transport=rmt0 gpio5_tick_hz=%lu "
      "gpio5_t0_ticks=%u/%u gpio5_t1_ticks=%u/%u "
      "gpio5_reset_us=500 gpio5_drive_cap=2 "
      "gpio6_transport=disabled gpio6_level=0\n",
      static_cast<unsigned long>(light_belt::WS2811_RMT_TICK_HZ),
      light_belt::WS2811_RMT_ZERO_HIGH_TICKS,
      light_belt::WS2811_RMT_ZERO_LOW_TICKS,
      light_belt::WS2811_RMT_ONE_HIGH_TICKS,
      light_belt::WS2811_RMT_ONE_LOW_TICKS);
#elif defined(LIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC)
  Serial.printf(
      "node_timing gpio4_hz=%lu gpio4_bits_per_ws=4 "
      "gpio5_hz=%lu gpio5_bits_per_ws=6 gpio5_t0h_ns=200\n",
      static_cast<unsigned long>(light_belt::WS2811_SPI_CLOCK_HZ),
      static_cast<unsigned long>(light_belt::WS2811_SPI6_CLOCK_HZ));
#elif defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC)
  Serial.printf(
      "node_timing gpio4_hz=%lu gpio4_bits_per_ws=4 "
      "gpio5_hz=%lu gpio5_bits_per_ws=3\n",
      static_cast<unsigned long>(light_belt::WS2811_SPI_CLOCK_HZ),
      static_cast<unsigned long>(light_belt::WS2811_SPI3_CLOCK_HZ));
#elif defined(LIGHT_BELT_FIXED_GPIO4_SPI)
  Serial.printf(
      "node_timing gpio4_transport=spi2 gpio4_hz=%lu "
      "gpio4_bits_per_ws=4 routing=permanent\n",
      static_cast<unsigned long>(light_belt::WS2811_SPI_CLOCK_HZ));
#endif
}

bool isExpectedLocalIp(const IPAddress &address) {
  return address[0] == WIFI_IPV4_A && address[1] == WIFI_IPV4_B &&
         address[2] == WIFI_IPV4_C && address[3] == NODE_IPV4_D;
}

bool waitForTransmitStart(
    uint64_t local_start_us, uint32_t session_generation) {
  for (;;) {
    if (session_generation != announced_session_generation.load()) {
      return false;
    }
    const uint64_t now_us = static_cast<uint64_t>(esp_timer_get_time());
    if (now_us >= local_start_us) {
      return true;
    }
    const uint64_t remaining_us = local_start_us - now_us;
    if (remaining_us > 2000) {
      const uint64_t coarse_ms = (remaining_us - 1000) / 1000;
      if (coarse_ms > 0) {
        vTaskDelay(pdMS_TO_TICKS(static_cast<uint32_t>(coarse_ms)));
        continue;
      }
    }
    if (remaining_us > kFinalScheduleSpinUs) {
      delayMicroseconds(
          static_cast<uint32_t>(remaining_us - kFinalScheduleSpinUs));
      continue;
    }
    while (static_cast<uint64_t>(esp_timer_get_time()) < local_start_us) {
      if (session_generation != announced_session_generation.load()) {
        return false;
      }
    }
    return session_generation == announced_session_generation.load();
  }
}

int32_t deadlineErrorUs(uint64_t completed_us, uint64_t deadline_us) {
  if (completed_us >= deadline_us) {
    const uint64_t late = completed_us - deadline_us;
    return late > static_cast<uint64_t>(INT32_MAX)
        ? INT32_MAX
        : static_cast<int32_t>(late);
  }
  const uint64_t early = deadline_us - completed_us;
  return early > static_cast<uint64_t>(INT32_MAX)
      ? INT32_MIN
      : -static_cast<int32_t>(early);
}

void networkTask(void *) {
  light_belt::PresentationClock presentation_clock;
  bool udp_started = false;
  bool has_rx_sequence = false;
  uint32_t last_rx_sequence = 0;
  uint32_t rx_session_generation = 0;
  bool has_scheduled_session_identity = false;
  uint64_t last_session_apply_at_us = 0;
  uint64_t last_session_media_timestamp_us = 0;
  uint32_t last_wifi_begin_ms = 0;
  uint32_t last_placeholder_log_ms = 0;

  bool network_configured = false;
  if (!hasPlaceholderWifi()) {
    WiFi.persistent(false);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    const bool wifi_power_save_disabled = WiFi.getSleep() == WIFI_PS_NONE;
    if (!wifi_power_save_disabled) {
      runtime_stats.network_config_errors.fetch_add(1);
      Serial.println("fatal wifi_power_save_disable_failed");
      network_configured = false;
    } else {
      Serial.println("wifi_power_save mode=none");
    }
    WiFi.setAutoReconnect(true);
    const IPAddress local_ip(
        WIFI_IPV4_A, WIFI_IPV4_B, WIFI_IPV4_C, NODE_IPV4_D);
    const IPAddress gateway(
        WIFI_IPV4_A, WIFI_IPV4_B, WIFI_IPV4_C, WIFI_GATEWAY_D);
    const IPAddress subnet(
        WIFI_SUBNET_A, WIFI_SUBNET_B, WIFI_SUBNET_C, WIFI_SUBNET_D);
    network_configured =
        wifi_power_save_disabled && WiFi.config(local_ip, gateway, subnet, gateway);
    if (!network_configured) {
      runtime_stats.network_config_errors.fetch_add(1);
      Serial.println("fatal wifi_static_config_failed");
    }
    Serial.printf("wifi_station mac=%s\n", WiFi.macAddress().c_str());
  }

  for (;;) {
    const uint32_t now_ms = millis();
    if (hasPlaceholderWifi()) {
      runtime_stats.clock_ready.store(0);
      if (static_cast<uint32_t>(now_ms - last_placeholder_log_ms) >=
          kStatsIntervalMs) {
        Serial.println("wifi_placeholder compile_only=1");
        last_placeholder_log_ms = now_ms;
      }
      vTaskDelay(pdMS_TO_TICKS(250));
      continue;
    }
    if (!network_configured) {
      runtime_stats.clock_ready.store(0);
      vTaskDelay(pdMS_TO_TICKS(1000));
      continue;
    }

    if (WiFi.status() != WL_CONNECTED) {
      runtime_stats.wifi_connected.store(0);
      runtime_stats.clock_ready.store(0);
      if (udp_started) {
        udp.stop();
        udp_started = false;
        runtime_stats.udp_bound.store(0);
      }
      if (last_wifi_begin_ms == 0 ||
          static_cast<uint32_t>(now_ms - last_wifi_begin_ms) >= kWifiRetryMs) {
        WiFi.disconnect();
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        last_wifi_begin_ms = now_ms;
        runtime_stats.wifi_reconnects.fetch_add(1);
        Serial.println("wifi_connecting");
      }
      vTaskDelay(pdMS_TO_TICKS(250));
      continue;
    }

    if (runtime_stats.wifi_connected.exchange(1) == 0) {
      Serial.printf("wifi_connected ip=%s rssi=%d\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
    }
    if (!isExpectedLocalIp(WiFi.localIP())) {
      runtime_stats.wifi_connected.store(0);
      runtime_stats.clock_ready.store(0);
      runtime_stats.ip_mismatches.fetch_add(1);
      Serial.printf("wifi_ip_mismatch actual=%s expected=%u.%u.%u.%u\n",
                    WiFi.localIP().toString().c_str(), WIFI_IPV4_A,
                    WIFI_IPV4_B, WIFI_IPV4_C, NODE_IPV4_D);
      WiFi.disconnect();
      vTaskDelay(pdMS_TO_TICKS(1000));
      continue;
    }
    if (!udp_started) {
      if (udp.begin(UDP_PORT) != 1) {
        runtime_stats.udp_bind_errors.fetch_add(1);
        runtime_stats.udp_bound.store(0);
        runtime_stats.clock_ready.store(0);
        Serial.printf("udp_bind_failed port=%u\n", UDP_PORT);
        vTaskDelay(pdMS_TO_TICKS(1000));
        continue;
      }
      udp_started = true;
      runtime_stats.udp_bound.store(1);
      Serial.printf("udp_bound port=%u\n", UDP_PORT);
    }

    const int packet_size = udp.parsePacket();
    if (packet_size <= 0) {
      runtime_stats.clock_ready.store(
          presentation_clock.status(
              static_cast<uint64_t>(esp_timer_get_time())) ==
                  light_belt::PresentationClockStatus::Ready
              ? 1U
              : 0U);
      vTaskDelay(pdMS_TO_TICKS(1));
      continue;
    }
    runtime_stats.datagrams_received.fetch_add(1);
    if (static_cast<size_t>(packet_size) > sizeof(packet_buffer)) {
      // WiFiUDP retains rx_buffer until read or flush. Without this flush,
      // all later parsePacket() calls return zero until reboot.
      udp.flush();
      runtime_stats.oversized_rejected.fetch_add(1);
      continue;
    }

    const int read_len = udp.read(packet_buffer, sizeof(packet_buffer));
    if (read_len != packet_size) {
      udp.flush();
      runtime_stats.read_rejected.fetch_add(1);
      continue;
    }
    const uint64_t local_receive_us =
        static_cast<uint64_t>(esp_timer_get_time());

    if (static_cast<size_t>(read_len) ==
        light_belt::UDP_V3_CLOCK_BEACON_LEN) {
      runtime_stats.clock_beacons_received.fetch_add(1);
      light_belt::UdpV3ClockBeacon beacon{};
      const light_belt::ClockBeaconParseResult beacon_result =
          light_belt::parseUdpV3ClockBeacon(
              packet_buffer, static_cast<size_t>(read_len), &beacon);
      if (beacon_result != light_belt::ClockBeaconParseResult::Ok) {
        runtime_stats.clock_beacons_rejected.fetch_add(1);
        runtime_stats.parse_rejected.fetch_add(1);
        continue;
      }
      if (!presentation_clock.observeBeacon(
              beacon.beacon_sequence, beacon.host_monotonic_us,
              local_receive_us)) {
        runtime_stats.clock_beacons_rejected.fetch_add(1);
        continue;
      }
      runtime_stats.clock_beacons_accepted.fetch_add(1);
      runtime_stats.clock_samples.store(presentation_clock.sampleCount());
      const uint64_t uncertainty_us = presentation_clock.uncertaintyUs();
      runtime_stats.clock_uncertainty_us.store(
          uncertainty_us > UINT32_MAX
              ? UINT32_MAX
              : static_cast<uint32_t>(uncertainty_us));
      runtime_stats.clock_ready.store(
          presentation_clock.status(local_receive_us) ==
                  light_belt::PresentationClockStatus::Ready
              ? 1U
              : 0U);
      continue;
    }

    light_belt::UdpV3Frame parsed{};
    const light_belt::ParseResult parse_result = light_belt::parseUdpV3Frame(
        packet_buffer, static_cast<size_t>(read_len), NODE_ID,
        led_output.descriptors(), led_output.outputCount(), &parsed);
    if (parse_result != light_belt::ParseResult::Ok) {
      runtime_stats.parse_rejected.fetch_add(1);
      continue;
    }

    const bool scheduled =
        (parsed.flags & light_belt::UDP_V3_FLAG_SCHEDULED_APPLY) != 0;
    uint64_t local_deadline_us = 0;
    if (scheduled) {
      const uint64_t local_now_us =
          static_cast<uint64_t>(esp_timer_get_time());
      const light_belt::ApplyDeadline deadline =
          presentation_clock.evaluateDeadline(parsed.apply_at_us, local_now_us);
      runtime_stats.clock_ready.store(
          deadline.clock_status == light_belt::PresentationClockStatus::Ready
              ? 1U
              : 0U);
      if (deadline.result != light_belt::ApplyDeadlineResult::Ok) {
        runtime_stats.scheduled_dropped.fetch_add(1);
        runtime_stats.state_rejected.fetch_add(1);
        switch (deadline.result) {
          case light_belt::ApplyDeadlineResult::ClockNotReady:
            runtime_stats.clock_not_ready_dropped.fetch_add(1);
            break;
          case light_belt::ApplyDeadlineResult::TooLate:
            runtime_stats.scheduled_too_late_dropped.fetch_add(1);
            break;
          case light_belt::ApplyDeadlineResult::TooFar:
            runtime_stats.scheduled_too_far_dropped.fetch_add(1);
            break;
          case light_belt::ApplyDeadlineResult::InvalidApplyTime:
          case light_belt::ApplyDeadlineResult::ConversionOutOfRange:
          case light_belt::ApplyDeadlineResult::Ok:
            runtime_stats.scheduled_invalid_dropped.fetch_add(1);
            break;
        }
        continue;
      }
      local_deadline_us = deadline.local_deadline_us;
    } else {
#if defined(LIGHT_BELT_REQUIRE_SCHEDULED_APPLY) && \
    LIGHT_BELT_REQUIRE_SCHEDULED_APPLY
      runtime_stats.immediate_dropped.fetch_add(1);
      runtime_stats.state_rejected.fetch_add(1);
      continue;
#endif
    }

    light_belt::OwnedNodeFrame owned{};
    if (!light_belt::copyUdpV3Frame(parsed, led_output.descriptors(),
                                    led_output.outputCount(), &owned)) {
      runtime_stats.state_rejected.fetch_add(1);
      continue;
    }
    const bool session_start = light_belt::isSessionStartFrame(owned);
    if (scheduled && session_start && has_scheduled_session_identity &&
        owned.apply_at_us == last_session_apply_at_us &&
        owned.media_timestamp_us == last_session_media_timestamp_us) {
      // The Host intentionally repeats the same scheduled KEY frame. Once one
      // copy is queued, later identical copies are delivery redundancy, not
      // new sessions and must not reset the output generation again.
      runtime_stats.session_key_duplicates.fetch_add(1);
      continue;
    }
    if (!light_belt::isFrameSequenceAcceptable(
            owned, has_rx_sequence, last_rx_sequence)) {
      runtime_stats.state_rejected.fetch_add(1);
      continue;
    }
    if (has_rx_sequence && !session_start &&
        static_cast<uint32_t>(owned.sequence - last_rx_sequence) != 1U) {
      runtime_stats.rx_sequence_gaps.fetch_add(1);
    }

    uint32_t candidate_generation = rx_session_generation;
    if (session_start) {
      ++candidate_generation;
      if (candidate_generation == 0) {
        candidate_generation = 1;
      }
      // Announce first so an old item already taken by outputTask cannot pass
      // its generation check after this new session has been observed.
      const uint32_t previous_announced_generation =
          announced_session_generation.load();
      announced_session_generation.store(candidate_generation);
      if (xQueueReset(frame_queue) != pdPASS) {
        announced_session_generation.store(previous_announced_generation);
        runtime_stats.state_rejected.fetch_add(1);
        continue;
      }
    } else if (!light_belt::isSessionGenerationAdmitted(
                   rx_session_generation,
                   prepared_session_generation.load(),
                   committed_session_generation.load())) {
      // Never overwrite the session-start frame before it is physically
      // visible. The next accepted frame may jump forward after it commits.
      runtime_stats.state_rejected.fetch_add(1);
      continue;
    }

    const QueuedNodeFrame queued = {
        owned, candidate_generation, local_deadline_us};
    const bool overwrote = uxQueueMessagesWaiting(frame_queue) != 0;
    if (xQueueOverwrite(frame_queue, &queued) != pdPASS) {
      runtime_stats.state_rejected.fetch_add(1);
      continue;
    }
    if (overwrote) {
      runtime_stats.queue_overwritten.fetch_add(1);
    }
    runtime_stats.frames_queued.fetch_add(1);
    if (scheduled) {
      runtime_stats.scheduled_queued.fetch_add(1);
    }
    runtime_stats.last_received_sequence.store(owned.sequence);
    rx_session_generation = candidate_generation;
    last_rx_sequence = owned.sequence;
    has_rx_sequence = true;
    if (scheduled && session_start) {
      has_scheduled_session_identity = true;
      last_session_apply_at_us = owned.apply_at_us;
      last_session_media_timestamp_us = owned.media_timestamp_us;
    }
  }
}

void revokePreparedSession(const QueuedNodeFrame &candidate) {
  if (!light_belt::isSessionStartFrame(candidate.frame)) {
    return;
  }
  uint32_t expected = candidate.session_generation;
  prepared_session_generation.compare_exchange_strong(expected, 0);
}

void outputTask(void *) {
  QueuedNodeFrame candidate{};
  uint32_t last_safe_attempt_ms = 0;
  for (;;) {
    const uint32_t safety_now_ms = millis();
    if (led_output.timedOut(safety_now_ms) &&
        static_cast<uint32_t>(safety_now_ms - last_safe_attempt_ms) >=
            kSafeRetryMs) {
      led_output.showBlack(safety_now_ms, true);
      last_safe_attempt_ms = safety_now_ms;
    }

    if (xQueueReceive(frame_queue, &candidate,
                      pdMS_TO_TICKS(kOutputPollMs)) == pdPASS) {
      if (candidate.session_generation !=
          announced_session_generation.load()) {
        runtime_stats.state_rejected.fetch_add(1);
        revokePreparedSession(candidate);
        continue;
      }
      runtime_stats.refresh_attempts.fetch_add(1);
      const uint32_t errors_before = runtime_stats.output_errors.load();
      bool accepted = false;
      if (candidate.local_deadline_us == 0) {
        accepted = led_output.acceptFrame(candidate.frame, millis());
      } else {
        if (!led_output.supportsScheduledApply() ||
            !led_output.prepareFrame(candidate.frame)) {
          if (runtime_stats.output_errors.load() == errors_before) {
            runtime_stats.state_rejected.fetch_add(1);
          }
          runtime_stats.scheduled_dropped.fetch_add(1);
          runtime_stats.scheduled_invalid_dropped.fetch_add(1);
          led_output.cancelPrepared();
          revokePreparedSession(candidate);
          continue;
        }
        if (light_belt::isSessionStartFrame(candidate.frame)) {
          // The session-start frame now owns a complete encoded buffer. The
          // network task may retain the next latest frame while this one waits.
          prepared_session_generation.store(candidate.session_generation);
        }

        const uint32_t wire_time_us = led_output.preparedWireTimeUs();
        light_belt::TransmitStart start =
            light_belt::calculateTransmitStart(
                candidate.local_deadline_us, wire_time_us,
                static_cast<uint64_t>(esp_timer_get_time()),
                kScheduledLateToleranceUs);
        if (start.result != light_belt::TransmitStartResult::Ok) {
          runtime_stats.scheduled_dropped.fetch_add(1);
          if (start.result == light_belt::TransmitStartResult::TooLate) {
            runtime_stats.scheduled_start_late_dropped.fetch_add(1);
          } else {
            runtime_stats.scheduled_invalid_dropped.fetch_add(1);
          }
          led_output.cancelPrepared();
          // The session was already admitted by its encoded KEY. Every later
          // UDP frame is complete and can recover the physical output without
          // waiting for a KEY copy that has already been sent.
          continue;
        }
        if (!waitForTransmitStart(
                start.local_start_us, candidate.session_generation)) {
          runtime_stats.scheduled_cancelled.fetch_add(1);
          runtime_stats.scheduled_dropped.fetch_add(1);
          led_output.cancelPrepared();
          revokePreparedSession(candidate);
          continue;
        }

        // A coarse task wake can overrun the target. Re-evaluate immediately
        // before touching GPIO and fail closed if the miss exceeds tolerance.
        start = light_belt::calculateTransmitStart(
            candidate.local_deadline_us, wire_time_us,
            static_cast<uint64_t>(esp_timer_get_time()),
            kScheduledLateToleranceUs);
        const bool generation_cancelled =
            candidate.session_generation !=
            announced_session_generation.load();
        if (start.result != light_belt::TransmitStartResult::Ok ||
            generation_cancelled) {
          runtime_stats.scheduled_dropped.fetch_add(1);
          if (start.result == light_belt::TransmitStartResult::TooLate) {
            runtime_stats.scheduled_start_late_dropped.fetch_add(1);
          } else {
            runtime_stats.scheduled_cancelled.fetch_add(1);
          }
          led_output.cancelPrepared();
          if (generation_cancelled) {
            revokePreparedSession(candidate);
          }
          continue;
        }

        // A scheduled retry would start a second full wire transaction after
        // the validated start deadline. Fail closed and recover locally.
        accepted = led_output.transmitPrepared(millis(), false);
        if (accepted) {
          const uint64_t completed_us =
              static_cast<uint64_t>(esp_timer_get_time());
          runtime_stats.last_deadline_error_us.store(
              deadlineErrorUs(completed_us, candidate.local_deadline_us));
          runtime_stats.scheduled_committed.fetch_add(1);
        } else {
          runtime_stats.scheduled_dropped.fetch_add(1);
        }
      }
      if (!accepted && runtime_stats.output_errors.load() == errors_before) {
        runtime_stats.state_rejected.fetch_add(1);
      } else if (accepted) {
        committed_session_generation.store(candidate.session_generation);
        uint32_t prepared = candidate.session_generation;
        prepared_session_generation.compare_exchange_strong(prepared, 0);
      }
      continue;
    }
  }
}

void printStats() {
  Serial.printf(
      "stats uptime_ms=%lu wifi=%u udp=%u received=%u oversized=%u "
      "read_rejected=%u parse_rejected=%u state_rejected=%u "
      "beacon_rx=%u beacon_ok=%u beacon_rejected=%u "
      "clock_samples=%u clock_uncertainty_us=%u clock_ready=%u "
      "scheduled_queued=%u scheduled_commit=%u scheduled_dropped=%u "
      "clock_not_ready=%u "
      "scheduled_late=%u scheduled_far=%u scheduled_invalid=%u "
      "scheduled_start_late=%u scheduled_cancelled=%u session_key_dupes=%u "
      "deadline_error_us=%ld immediate_dropped=%u queued=%u "
      "queue_overwritten=%u rx_gaps=%u display_gaps=%u attempts=%u "
      "refresh_ok=%u spi_ok=%u output_errors=%u invariant_errors=%u "
      "rollback_ok=%u "
      "safe_frames=%u timeout_black=%u wifi_reconnects=%u "
      "net_config_errors=%u ip_mismatches=%u udp_bind_errors=%u "
      "last_rx=%u last_commit=%u\n",
      millis(), runtime_stats.wifi_connected.load(),
      runtime_stats.udp_bound.load(), runtime_stats.datagrams_received.load(),
      runtime_stats.oversized_rejected.load(),
      runtime_stats.read_rejected.load(), runtime_stats.parse_rejected.load(),
      runtime_stats.state_rejected.load(),
      runtime_stats.clock_beacons_received.load(),
      runtime_stats.clock_beacons_accepted.load(),
      runtime_stats.clock_beacons_rejected.load(),
      runtime_stats.clock_samples.load(),
      runtime_stats.clock_uncertainty_us.load(),
      runtime_stats.clock_ready.load(), runtime_stats.scheduled_queued.load(),
      runtime_stats.scheduled_committed.load(),
      runtime_stats.scheduled_dropped.load(),
      runtime_stats.clock_not_ready_dropped.load(),
      runtime_stats.scheduled_too_late_dropped.load(),
      runtime_stats.scheduled_too_far_dropped.load(),
      runtime_stats.scheduled_invalid_dropped.load(),
      runtime_stats.scheduled_start_late_dropped.load(),
      runtime_stats.scheduled_cancelled.load(),
      runtime_stats.session_key_duplicates.load(),
      static_cast<long>(runtime_stats.last_deadline_error_us.load()),
      runtime_stats.immediate_dropped.load(),
      runtime_stats.frames_queued.load(),
      runtime_stats.queue_overwritten.load(),
      runtime_stats.rx_sequence_gaps.load(),
      runtime_stats.display_sequence_gaps.load(),
      runtime_stats.refresh_attempts.load(), runtime_stats.refresh_ok.load(),
      runtime_stats.spi_transactions_ok.load(),
      runtime_stats.output_errors.load(), runtime_stats.invariant_errors.load(),
      runtime_stats.rollback_ok.load(),
      runtime_stats.safe_frames.load(), runtime_stats.timeout_black.load(),
      runtime_stats.wifi_reconnects.load(),
      runtime_stats.network_config_errors.load(),
      runtime_stats.ip_mismatches.load(), runtime_stats.udp_bind_errors.load(),
      runtime_stats.last_received_sequence.load(),
      runtime_stats.last_committed_sequence.load());
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  printStartupIdentity();

  frame_queue = xQueueCreate(1, sizeof(QueuedNodeFrame));
  if (frame_queue == nullptr) {
    Serial.println("fatal queue_create_failed");
    return;
  }
  if (!led_output.begin()) {
    Serial.println("fatal output_init_failed");
    return;
  }
#if defined(LIGHT_BELT_REQUIRE_SCHEDULED_APPLY) && \
    LIGHT_BELT_REQUIRE_SCHEDULED_APPLY
  if (!led_output.supportsScheduledApply()) {
    Serial.println("fatal scheduled_output_unsupported");
    return;
  }
#endif

  TaskHandle_t output_task = nullptr;
  TaskHandle_t network_task = nullptr;
  if (xTaskCreatePinnedToCore(outputTask, "light-output", 8192, nullptr, 3,
                              &output_task, 1) != pdPASS ||
      xTaskCreatePinnedToCore(networkTask, "light-network", 8192, nullptr, 2,
                              &network_task, 0) != pdPASS) {
    Serial.println("fatal task_create_failed");
    return;
  }
  runtime_ready = true;
}

void loop() {
  static uint32_t last_stats_ms = 0;
  const uint32_t now_ms = millis();
  if (static_cast<uint32_t>(now_ms - last_stats_ms) >= kStatsIntervalMs) {
    printStats();
    last_stats_ms = now_ms;
  }
  if (!runtime_ready) {
    delay(100);
    return;
  }
  delay(10);
}
