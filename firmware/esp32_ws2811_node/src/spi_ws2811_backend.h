#ifndef LIGHT_BELT_ESP32_SPI_WS2811_BACKEND_H
#define LIGHT_BELT_ESP32_SPI_WS2811_BACKEND_H

#include <driver/spi_master.h>
#include <esp_err.h>
#include <stddef.h>
#include <stdint.h>

#include "owned_frame.h"

namespace light_belt {

enum class SpiRefreshStatus : uint8_t {
  Ok,
  NotInitialized,
  InvalidFrame,
  EncodeFailed,
  PrepareUnsupported,
  NotPrepared,
  RouteFailed,
  TransmitFailed,
  IntegrityFailed,
};

struct SpiRefreshReport {
  SpiRefreshStatus status = SpiRefreshStatus::NotInitialized;
  uint8_t successful_transactions = 0;
  uint8_t encoded_hash_checks = 0;
  uint8_t encoded_hash_mismatches = 0;
  uint8_t uniform_frame_checks = 0;
  uint8_t uniform_frame_mismatches = 0;
  esp_err_t esp_error = ESP_OK;

  bool ok() const { return status == SpiRefreshStatus::Ok; }
};

class SpiWs2811Backend {
 public:
  bool begin(const OutputDescriptor *outputs, uint8_t output_count);
  // The scheduled production path separates memory-only encoding from the
  // physical SPI transaction. Legacy diagnostics continue to use refresh().
  SpiRefreshReport prepare(const OwnedNodeFrame &frame);
  SpiRefreshReport transmitPrepared();
  void cancelPrepared();
  bool hasPreparedFrame() const;
  bool supportsScheduledApply() const;
  uint32_t preparedWireTimeUs() const;
  SpiRefreshReport refresh(const OwnedNodeFrame &frame);
  bool initialized() const;

 private:
  bool routeTo(uint8_t gpio);
  bool detachCurrent();

  spi_device_handle_t device_ = nullptr;
  spi_device_handle_t secondary_device_ = nullptr;
  int8_t current_gpio_ = -1;
  bool initialized_ = false;
  bool rmt_initialized_ = false;
  bool backend_fault_latched_ = false;
  bool prepared_ = false;
  size_t prepared_encoded_len_ = 0;
  uint32_t prepared_encoded_hash_ = 0;
  uint32_t actual_clock_hz_ = 0;
  esp_err_t last_gpio_error_ = ESP_OK;
};

}  // namespace light_belt

#endif
