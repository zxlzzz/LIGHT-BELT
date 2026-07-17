#include "spi_ws2811_backend.h"

#include <driver/gpio.h>
#if defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
#include <driver/rmt.h>
#include <esp_intr_alloc.h>
#endif
#include <esp_attr.h>
#include <esp_rom_gpio.h>
#include <soc/gpio_sig_map.h>
#include <soc/soc_memory_types.h>

#include "config.h"
#if defined(LIGHT_BELT_QIO_DIAGNOSTIC)
#include "ws2811_parallel_spi_encoder.h"
#endif
#if defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
#include "ws2811_rmt_encoder.h"
#endif
#if defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC)
#include "ws2811_spi3_encoder.h"
#endif
#if defined(LIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC)
#include "ws2811_spi6_encoder.h"
#endif
#include "ws2811_spi_encoder.h"

#if defined(LIGHT_BELT_FIXED_GPIO4_DIAGNOSTIC) && \
    !defined(LIGHT_BELT_FIXED_GPIO4_SPI)
#error "fixed GPIO4 diagnostics require the permanent GPIO4 SPI backend"
#endif
#if defined(LIGHT_BELT_QIO_DIAGNOSTIC) && \
    defined(LIGHT_BELT_FIXED_GPIO4_SPI)
#error "QIO and fixed GPIO4 SPI backends are mutually exclusive"
#endif
#if defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC) && \
    (defined(LIGHT_BELT_QIO_DIAGNOSTIC) || \
     defined(LIGHT_BELT_FIXED_GPIO4_SPI))
#error "hybrid and fixed GPIO4 SPI backends are mutually exclusive"
#endif
#if defined(LIGHT_BELT_HYBRID_SPI_HOST_SWAP) && \
    !defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
#error "SPI host swap requires the hybrid diagnostic"
#endif
#if defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC) && \
    !defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
#error "GPIO5 three-bit encoding requires the hybrid diagnostic"
#endif
#if defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC) && \
    defined(LIGHT_BELT_HYBRID_SPI_HOST_SWAP)
#error "GPIO5 timing and SPI host swap diagnostics are mutually exclusive"
#endif
#if defined(LIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC) && \
    !defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
#error "GPIO5 six-bit encoding requires the hybrid diagnostic"
#endif
#if defined(LIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC) && \
    (defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC) || \
     defined(LIGHT_BELT_HYBRID_SPI_HOST_SWAP))
#error "GPIO5 six-bit timing diagnostic must be isolated"
#endif
#if defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC) && \
    !defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
#error "GPIO5 RMT diagnostic requires the hybrid diagnostic"
#endif
#if defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC) && \
    (defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC) || \
     defined(LIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC) || \
     defined(LIGHT_BELT_HYBRID_SPI_HOST_SWAP))
#error "GPIO5 RMT diagnostic must be isolated"
#endif

namespace light_belt {

namespace {

#if WS2811_COLOR_ORDER == WS2811_COLOR_ORDER_GRB
constexpr Ws2811ColorOrder kColorOrder = Ws2811ColorOrder::GRB;
#else
constexpr Ws2811ColorOrder kColorOrder = Ws2811ColorOrder::RGB;
#endif

#if defined(LIGHT_BELT_FIXED_GPIO4_SPI) && \
    !defined(LIGHT_BELT_FIXED_GPIO4_DIAGNOSTIC)
constexpr bool kScheduledApplySupported = true;
constexpr uint32_t kPrimarySpiClockHz = WS2811_SPI_CLOCK_HZ;
constexpr size_t kPrimarySpiMaxFrameBytes =
    WS2811_FIXED_GPIO4_SPI_MAX_FRAME_BYTES;
#else
constexpr bool kScheduledApplySupported = false;
constexpr uint32_t kPrimarySpiClockHz = WS2811_SPI_CLOCK_HZ;
constexpr size_t kPrimarySpiMaxFrameBytes = WS2811_SPI_MAX_FRAME_BYTES;
#endif

uint32_t wireTimeUs(size_t encoded_len, uint32_t clock_hz) {
  if (encoded_len == 0 || clock_hz == 0) {
    return 0;
  }
  const uint64_t bit_micros =
      static_cast<uint64_t>(encoded_len) * 8U * 1000000U;
  const uint64_t rounded =
      (bit_micros + static_cast<uint64_t>(clock_hz) - 1U) / clock_hz;
  return rounded <= UINT32_MAX ? static_cast<uint32_t>(rounded) : 0;
}

bool pixelsUniform(const RgbPixel *pixels, uint16_t pixel_count) {
  if (pixels == nullptr || pixel_count == 0) {
    return false;
  }
  for (uint16_t pixel = 1; pixel < pixel_count; ++pixel) {
    if (pixels[pixel].r != pixels[0].r ||
        pixels[pixel].g != pixels[0].g ||
        pixels[pixel].b != pixels[0].b) {
      return false;
    }
  }
  return true;
}

#if defined(LIGHT_BELT_QIO_DIAGNOSTIC)
alignas(4) DMA_ATTR uint8_t
    kParallelDmaBuffer[WS2811_PARALLEL_SPI_MAX_FRAME_BYTES] = {};
#else
alignas(4) DMA_ATTR uint8_t
    kDmaBuffers[MAX_OUTPUTS][kPrimarySpiMaxFrameBytes] = {};
size_t kEncodedLengths[MAX_OUTPUTS] = {};
#endif

#if defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
DRAM_ATTR Ws2811RmtPulse kRmtPulses[WS2811_RMT_MAX_PULSES] = {};
DRAM_ATTR rmt_item32_t kRmtItems[WS2811_RMT_MAX_PULSES + 1U] = {};
#endif

bool supportedDataPin(uint8_t gpio) {
  return gpio == 4 || gpio == 5 || gpio == 6;
}

#if defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
bool initializeFixedSpi(
    spi_host_device_t host,
    uint8_t gpio,
    uint32_t clock_hz,
    spi_device_handle_t *device) {
  if (device == nullptr) {
    return false;
  }
  spi_bus_config_t bus{};
  bus.mosi_io_num = gpio;
  bus.miso_io_num = -1;
  bus.sclk_io_num = -1;
  bus.quadwp_io_num = -1;
  bus.quadhd_io_num = -1;
  bus.data4_io_num = -1;
  bus.data5_io_num = -1;
  bus.data6_io_num = -1;
  bus.data7_io_num = -1;
  bus.max_transfer_sz = kPrimarySpiMaxFrameBytes;
  bus.flags = SPICOMMON_BUSFLAG_MASTER | SPICOMMON_BUSFLAG_MOSI;
  if (spi_bus_initialize(host, &bus, SPI_DMA_CH_AUTO) != ESP_OK) {
    return false;
  }

  spi_device_interface_config_t config{};
  config.mode = 0;
  config.duty_cycle_pos = 128;
  config.clock_speed_hz = clock_hz;
  config.spics_io_num = -1;
  config.flags = SPI_DEVICE_HALFDUPLEX;
  config.queue_size = 1;
  if (spi_bus_add_device(host, &config, device) != ESP_OK) {
    spi_bus_free(host);
    *device = nullptr;
    return false;
  }
  return true;
}

void releaseFixedSpi(
    spi_host_device_t host, spi_device_handle_t *device) {
  if (device != nullptr && *device != nullptr) {
    spi_bus_remove_device(*device);
    *device = nullptr;
    spi_bus_free(host);
  }
}
#endif

#if defined(LIGHT_BELT_FIXED_GPIO4_SPI)
static_assert(OUTPUT_0_GPIO == 4, "fixed GPIO4 SPI backend requires GPIO4");
#if !defined(LIGHT_BELT_FIXED_GPIO4_DIAGNOSTIC)
static_assert(OUTPUT_COUNT == 1,
              "production fixed GPIO4 SPI expects exactly one output");
#endif
#endif

#if defined(LIGHT_BELT_FIXED_GPIO4_DIAGNOSTIC)
static_assert(NODE_ID == 2, "fixed GPIO4 diagnostic is Node 2 only");
#if defined(LIGHT_BELT_NODE2_GPIO4_STRIP42_DIAGNOSTIC)
static_assert(OUTPUT_COUNT == 1, "strip 42 GPIO4 diagnostic expects one output");
static_assert(OUTPUT_0_PIXELS == 20, "strip 42 GPIO4 diagnostic expects 20 groups");
#else
static_assert(OUTPUT_COUNT == 3, "fixed GPIO4 diagnostic expects three outputs");
#endif
#endif

#if defined(LIGHT_BELT_QIO_DIAGNOSTIC)
static_assert(NODE_ID == 2, "QIO diagnostic is Node 2 only");
static_assert(OUTPUT_COUNT == 3, "QIO diagnostic expects three outputs");
static_assert(OUTPUT_0_GPIO == 4, "QIO DATA0 must drive GPIO4");
static_assert(OUTPUT_1_GPIO == 5, "QIO DATA1 must drive GPIO5");
static_assert(OUTPUT_2_GPIO == 6, "QIO DATA2 must drive GPIO6");
constexpr uint8_t kUnusedQioData3Gpio = 7;
#endif

#if defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
static_assert(NODE_ID == 2, "hybrid diagnostic is Node 2 only");
static_assert(OUTPUT_COUNT == 3, "hybrid diagnostic expects three outputs");
static_assert(OUTPUT_0_GPIO == 4, "SPI2 must drive GPIO4");
#if defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
static_assert(OUTPUT_1_GPIO == 5, "RMT0 must drive GPIO5");
static_assert(OUTPUT_2_GPIO == 6, "disconnected output 3 must remain GPIO6");
#else
static_assert(OUTPUT_1_GPIO == 5, "SPI3 must drive GPIO5");
static_assert(OUTPUT_2_GPIO == 6, "RMT0 must drive GPIO6");
#endif
constexpr rmt_channel_t kHybridRmtChannel = RMT_CHANNEL_0;
constexpr uint8_t kHybridRmtClockDivider = 5;
constexpr uint8_t kHybridRmtMemoryBlocks = 4;
constexpr uint32_t kHybridRmtClockHz = 16000000;
constexpr TickType_t kHybridRmtWaitTicks = pdMS_TO_TICKS(10);
#if defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
constexpr uint16_t kHybridRmtResetTicks = 8000;
constexpr uint8_t kSecondarySpiOutputIndex = 2;
constexpr uint8_t kRmtOutputIndex = 1;
static_assert(
    kHybridRmtResetTicks >= kHybridRmtClockHz / 2000U,
    "GPIO5 RMT reset must be at least 500 us");
#else
constexpr uint16_t kHybridRmtResetTicks = 1280;
constexpr uint8_t kSecondarySpiOutputIndex = 1;
constexpr uint8_t kRmtOutputIndex = 2;
#endif
#if defined(LIGHT_BELT_HYBRID_SPI_HOST_SWAP)
constexpr spi_host_device_t kOutput0SpiHost = SPI3_HOST;
constexpr spi_host_device_t kOutput1SpiHost = SPI2_HOST;
#else
constexpr spi_host_device_t kOutput0SpiHost = SPI2_HOST;
constexpr spi_host_device_t kOutput1SpiHost = SPI3_HOST;
#endif

bool initializeHybridRmt(uint8_t gpio) {
  rmt_config_t config = RMT_DEFAULT_CONFIG_TX(
      static_cast<gpio_num_t>(gpio), kHybridRmtChannel);
  config.clk_div = kHybridRmtClockDivider;
  config.mem_block_num = kHybridRmtMemoryBlocks;
  config.tx_config.carrier_en = false;
  config.tx_config.loop_en = false;
  config.tx_config.idle_output_en = true;
  config.tx_config.idle_level = RMT_IDLE_LEVEL_LOW;

  if (rmt_config(&config) != ESP_OK ||
      rmt_set_source_clk(kHybridRmtChannel, RMT_BASECLK_APB) != ESP_OK ||
      rmt_driver_install(
          kHybridRmtChannel, 0, ESP_INTR_FLAG_IRAM) != ESP_OK) {
    return false;
  }
#if defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
  gpio_drive_cap_t configured_drive = GPIO_DRIVE_CAP_0;
  if (gpio != OUTPUT_1_GPIO ||
      gpio_set_drive_capability(
          static_cast<gpio_num_t>(gpio), GPIO_DRIVE_CAP_2) != ESP_OK ||
      gpio_get_drive_capability(
          static_cast<gpio_num_t>(gpio), &configured_drive) != ESP_OK ||
      configured_drive != GPIO_DRIVE_CAP_2) {
    rmt_driver_uninstall(kHybridRmtChannel);
    return false;
  }
#endif

  uint8_t configured_blocks = 0;
  uint8_t configured_divider = 0;
  uint32_t counter_hz = 0;
  if (rmt_get_mem_block_num(kHybridRmtChannel, &configured_blocks) != ESP_OK ||
      rmt_get_clk_div(kHybridRmtChannel, &configured_divider) != ESP_OK ||
      rmt_get_counter_clock(kHybridRmtChannel, &counter_hz) != ESP_OK ||
      configured_blocks != kHybridRmtMemoryBlocks ||
      configured_divider != kHybridRmtClockDivider ||
      counter_hz != kHybridRmtClockHz) {
    rmt_driver_uninstall(kHybridRmtChannel);
    return false;
  }
  return true;
}
#endif

}  // namespace

bool SpiWs2811Backend::begin(
    const OutputDescriptor *outputs, uint8_t output_count) {
  if (initialized_) {
    return true;
  }
  if (!validateOutputDescriptors(outputs, output_count)) {
    return false;
  }
  for (uint8_t index = 0; index < output_count; ++index) {
    const uint8_t pin = outputs[index].gpio;
    if (!supportedDataPin(pin)) {
      return false;
    }
    last_gpio_error_ =
        gpio_set_direction(static_cast<gpio_num_t>(pin), GPIO_MODE_OUTPUT);
    if (last_gpio_error_ != ESP_OK) {
      return false;
    }
    last_gpio_error_ = gpio_set_level(static_cast<gpio_num_t>(pin), 0);
    if (last_gpio_error_ != ESP_OK) {
      return false;
    }
    esp_rom_gpio_connect_out_signal(pin, SIG_GPIO_OUT_IDX, false, false);
  }
#if defined(LIGHT_BELT_NODE2_GPIO4_STRIP42_DIAGNOSTIC)
  for (uint8_t pin = 5; pin <= 6; ++pin) {
    if (gpio_set_direction(static_cast<gpio_num_t>(pin), GPIO_MODE_OUTPUT) !=
            ESP_OK ||
        gpio_set_level(static_cast<gpio_num_t>(pin), 0) != ESP_OK) {
      return false;
    }
    esp_rom_gpio_connect_out_signal(pin, SIG_GPIO_OUT_IDX, false, false);
  }
#endif
#if defined(LIGHT_BELT_QIO_DIAGNOSTIC)
  last_gpio_error_ = gpio_set_direction(
      static_cast<gpio_num_t>(kUnusedQioData3Gpio), GPIO_MODE_OUTPUT);
  if (last_gpio_error_ != ESP_OK) {
    return false;
  }
  last_gpio_error_ =
      gpio_set_level(static_cast<gpio_num_t>(kUnusedQioData3Gpio), 0);
  if (last_gpio_error_ != ESP_OK ||
      !esp_ptr_dma_capable(kParallelDmaBuffer)) {
    return false;
  }
#else
  for (uint8_t index = 0; index < MAX_OUTPUTS; ++index) {
    if (!esp_ptr_dma_capable(kDmaBuffers[index])) {
      return false;
    }
  }
#endif

#if defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
  if (output_count != OUTPUT_COUNT ||
      outputs[0].gpio != OUTPUT_0_GPIO ||
      outputs[1].gpio != OUTPUT_1_GPIO ||
      outputs[2].gpio != OUTPUT_2_GPIO ||
      !esp_ptr_internal(kRmtPulses) || !esp_ptr_internal(kRmtItems)) {
    return false;
  }
#if defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
  constexpr uint8_t rmt_gpio = OUTPUT_1_GPIO;
#else
  if (!initializeFixedSpi(
          kOutput0SpiHost, OUTPUT_0_GPIO, WS2811_SPI_CLOCK_HZ, &device_)) {
    return false;
  }
#if defined(LIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC)
  constexpr uint32_t output1_clock_hz = WS2811_SPI6_CLOCK_HZ;
#elif defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC)
  constexpr uint32_t output1_clock_hz = WS2811_SPI3_CLOCK_HZ;
#else
  constexpr uint32_t output1_clock_hz = WS2811_SPI_CLOCK_HZ;
#endif
  constexpr uint8_t secondary_spi_gpio = OUTPUT_1_GPIO;
  constexpr uint8_t rmt_gpio = OUTPUT_2_GPIO;
  if (!initializeFixedSpi(
          kOutput1SpiHost, secondary_spi_gpio, output1_clock_hz,
          &secondary_device_)) {
    releaseFixedSpi(kOutput0SpiHost, &device_);
    return false;
  }
#endif
  if (!initializeHybridRmt(rmt_gpio)) {
    releaseFixedSpi(kOutput1SpiHost, &secondary_device_);
    releaseFixedSpi(kOutput0SpiHost, &device_);
    return false;
  }
  rmt_initialized_ = true;
  backend_fault_latched_ = false;
  current_gpio_ = -1;
  initialized_ = true;
  return true;
#endif

  spi_bus_config_t bus{};
#if defined(LIGHT_BELT_QIO_DIAGNOSTIC)
  // QIO routes its four data lanes once during initialization. DATA3 is not
  // connected to the lighting topology and remains zero in every nibble.
  bus.data0_io_num = OUTPUT_0_GPIO;
  bus.data1_io_num = OUTPUT_1_GPIO;
  bus.data2_io_num = OUTPUT_2_GPIO;
  bus.data3_io_num = kUnusedQioData3Gpio;
  bus.sclk_io_num = -1;
  bus.data4_io_num = -1;
  bus.data5_io_num = -1;
  bus.data6_io_num = -1;
  bus.data7_io_num = -1;
  bus.max_transfer_sz = WS2811_PARALLEL_SPI_MAX_FRAME_BYTES;
  bus.flags = SPICOMMON_BUSFLAG_MASTER | SPICOMMON_BUSFLAG_QUAD;
#else
  // IDF configures SPI2 MOSI on the first output. Production keeps that
  // GPIO4 route for the lifetime of the firmware image.
  bus.mosi_io_num = outputs[0].gpio;
  bus.miso_io_num = -1;
  bus.sclk_io_num = -1;
  bus.quadwp_io_num = -1;
  bus.quadhd_io_num = -1;
  bus.data4_io_num = -1;
  bus.data5_io_num = -1;
  bus.data6_io_num = -1;
  bus.data7_io_num = -1;
  bus.max_transfer_sz = kPrimarySpiMaxFrameBytes;
  bus.flags = SPICOMMON_BUSFLAG_MASTER | SPICOMMON_BUSFLAG_MOSI;
#endif
  if (spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO) != ESP_OK) {
    return false;
  }

  spi_device_interface_config_t config{};
  config.mode = 0;
  config.duty_cycle_pos = 128;
#if defined(LIGHT_BELT_QIO_DIAGNOSTIC)
  config.clock_speed_hz = WS2811_PARALLEL_SPI_CLOCK_HZ;
#else
  config.clock_speed_hz = kPrimarySpiClockHz;
#endif
  config.spics_io_num = -1;
  config.flags = SPI_DEVICE_HALFDUPLEX;
  config.queue_size = 1;
  if (spi_bus_add_device(SPI2_HOST, &config, &device_) != ESP_OK) {
    spi_bus_free(SPI2_HOST);
    device_ = nullptr;
    return false;
  }

  if (kScheduledApplySupported) {
    const int actual_clock =
        spi_get_actual_clock(APB_CLK_FREQ, kPrimarySpiClockHz, 128);
    const uint64_t required_guard_bit_micros =
        actual_clock > 0
        ? static_cast<uint64_t>(actual_clock) *
              WS2811_FIXED_GPIO4_SPI_RESET_LOW_US
        : 0;
    const uint64_t pre_guard_bit_micros =
        static_cast<uint64_t>(WS2811_FIXED_GPIO4_SPI_GUARD_BYTES) * 8U *
        1000000U;
    const uint64_t post_guard_bit_micros =
        static_cast<uint64_t>(WS2811_FIXED_GPIO4_SPI_GUARD_BYTES) * 8U *
        1000000U;
    if (actual_clock <= 0 ||
        pre_guard_bit_micros < required_guard_bit_micros ||
        post_guard_bit_micros < required_guard_bit_micros) {
      spi_bus_remove_device(device_);
      spi_bus_free(SPI2_HOST);
      device_ = nullptr;
      return false;
    }
    actual_clock_hz_ = static_cast<uint32_t>(actual_clock);
  }

  current_gpio_ = -1;
#if defined(LIGHT_BELT_QIO_DIAGNOSTIC)
  // The SPI driver permanently owns DATA0..3 for the lifetime of this image.
#elif defined(LIGHT_BELT_FIXED_GPIO4_SPI)
  current_gpio_ = static_cast<int8_t>(outputs[0].gpio);
  // Keep GPIO4 permanently connected to SPI2. Legacy isolation images may
  // configure GPIO5/6 as ordinary low outputs, but never refresh them here.
  esp_rom_gpio_connect_out_signal(
      outputs[0].gpio, FSPID_OUT_IDX, false, false);
#else
  if (!detachCurrent()) {
    spi_bus_remove_device(device_);
    spi_bus_free(SPI2_HOST);
    device_ = nullptr;
    return false;
  }
#endif
  initialized_ = true;
  cancelPrepared();
  return true;
}

SpiRefreshReport SpiWs2811Backend::prepare(const OwnedNodeFrame &frame) {
  SpiRefreshReport report{};
  // A failed preparation must never leave a previously encoded frame armed.
  cancelPrepared();
  if (!initialized_ || device_ == nullptr) {
    report.status = SpiRefreshStatus::NotInitialized;
    return report;
  }
#if !defined(LIGHT_BELT_FIXED_GPIO4_SPI) || \
    defined(LIGHT_BELT_FIXED_GPIO4_DIAGNOSTIC)
  (void)frame;
  report.status = SpiRefreshStatus::PrepareUnsupported;
  return report;
#else
  if (!kScheduledApplySupported) {
    report.status = SpiRefreshStatus::PrepareUnsupported;
    return report;
  }
  if (frame.output_count != 1 ||
      frame.outputs[0].descriptor.output_id != OUTPUT_0_ID ||
      frame.outputs[0].descriptor.gpio != OUTPUT_0_GPIO ||
      frame.outputs[0].descriptor.pixel_count != OUTPUT_0_PIXELS) {
    report.status = SpiRefreshStatus::InvalidFrame;
    return report;
  }

  size_t encoded_len = 0;
  const OwnedOutputFrame &output = frame.outputs[0];
  if (!encodeWs2811FixedGpio4Spi(
          output.pixels, output.descriptor.pixel_count, kColorOrder,
          kDmaBuffers[0], sizeof(kDmaBuffers[0]), &encoded_len) ||
      wireTimeUs(encoded_len, actual_clock_hz_) == 0) {
    report.status = SpiRefreshStatus::EncodeFailed;
    return report;
  }

#if defined(LIGHT_BELT_ENCODED_FRAME_DIAGNOSTIC)
  if (pixelsUniform(output.pixels, output.descriptor.pixel_count)) {
    report.uniform_frame_checks = 1;
    if (!ws2811FixedGpio4SpiUniformEncodedGroups(
            kDmaBuffers[0], encoded_len, output.descriptor.pixel_count)) {
      report.uniform_frame_mismatches = 1;
      report.status = SpiRefreshStatus::IntegrityFailed;
      return report;
    }
  }
  prepared_encoded_hash_ =
      ws2811EncodedHash(kDmaBuffers[0], encoded_len);
#endif

  prepared_encoded_len_ = encoded_len;
  kEncodedLengths[0] = encoded_len;
  prepared_ = true;
  report.status = SpiRefreshStatus::Ok;
  return report;
#endif
}

SpiRefreshReport SpiWs2811Backend::transmitPrepared() {
  SpiRefreshReport report{};
  if (!initialized_ || device_ == nullptr) {
    report.status = SpiRefreshStatus::NotInitialized;
    return report;
  }
#if !defined(LIGHT_BELT_FIXED_GPIO4_SPI) || \
    defined(LIGHT_BELT_FIXED_GPIO4_DIAGNOSTIC)
  report.status = SpiRefreshStatus::PrepareUnsupported;
  return report;
#else
  if (!kScheduledApplySupported) {
    report.status = SpiRefreshStatus::PrepareUnsupported;
    return report;
  }
  if (!prepared_ || prepared_encoded_len_ == 0) {
    report.status = SpiRefreshStatus::NotPrepared;
    return report;
  }


#if defined(LIGHT_BELT_ENCODED_FRAME_DIAGNOSTIC)
  report.encoded_hash_checks = 1;
  if (ws2811EncodedHash(kDmaBuffers[0], prepared_encoded_len_) !=
      prepared_encoded_hash_) {
    report.encoded_hash_mismatches = 1;
    report.status = SpiRefreshStatus::IntegrityFailed;
    cancelPrepared();
    return report;
  }
#endif

  spi_transaction_t transaction{};
  transaction.length = prepared_encoded_len_ * 8U;
  transaction.tx_buffer = kDmaBuffers[0];
  const esp_err_t result = spi_device_polling_transmit(device_, &transaction);
  if (result != ESP_OK) {
    // Preserve the encoded buffer so LedOutput can retry the same frame once.
    report.status = SpiRefreshStatus::TransmitFailed;
    report.esp_error = result;
    return report;
  }

  report.successful_transactions = 1;
  report.status = SpiRefreshStatus::Ok;
  cancelPrepared();
  return report;
#endif
}

void SpiWs2811Backend::cancelPrepared() {
  prepared_ = false;
  prepared_encoded_len_ = 0;
  prepared_encoded_hash_ = 0;
#if !defined(LIGHT_BELT_QIO_DIAGNOSTIC)
  kEncodedLengths[0] = 0;
#endif
}

bool SpiWs2811Backend::hasPreparedFrame() const { return prepared_; }

bool SpiWs2811Backend::supportsScheduledApply() const {
  return kScheduledApplySupported;
}

uint32_t SpiWs2811Backend::preparedWireTimeUs() const {
  return prepared_
      ? wireTimeUs(prepared_encoded_len_, actual_clock_hz_)
      : 0;
}

SpiRefreshReport SpiWs2811Backend::refresh(const OwnedNodeFrame &frame) {
  if (kScheduledApplySupported) {
    SpiRefreshReport prepared = prepare(frame);
    if (!prepared.ok()) {
      return prepared;
    }
    SpiRefreshReport transmitted = transmitPrepared();
    transmitted.encoded_hash_checks += prepared.encoded_hash_checks;
    transmitted.encoded_hash_mismatches += prepared.encoded_hash_mismatches;
    transmitted.uniform_frame_checks += prepared.uniform_frame_checks;
    transmitted.uniform_frame_mismatches +=
        prepared.uniform_frame_mismatches;
    return transmitted;
  }

  SpiRefreshReport report{};
#if defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
  if (!initialized_) {
#else
  if (!initialized_ || device_ == nullptr) {
#endif
    report.status = SpiRefreshStatus::NotInitialized;
    return report;
  }
  if (frame.output_count == 0 || frame.output_count > MAX_OUTPUTS) {
    report.status = SpiRefreshStatus::InvalidFrame;
    return report;
  }
#if defined(LIGHT_BELT_HYBRID_FIXED_DIAGNOSTIC)
#if defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
  constexpr bool secondary_ready = true;
#else
  const bool secondary_ready = secondary_device_ != nullptr;
#endif
  if (backend_fault_latched_ || !rmt_initialized_ || !secondary_ready ||
      frame.output_count != OUTPUT_COUNT) {
    report.status = backend_fault_latched_
        ? SpiRefreshStatus::TransmitFailed
        : SpiRefreshStatus::NotInitialized;
    report.esp_error = backend_fault_latched_
        ? ESP_ERR_INVALID_STATE
        : ESP_OK;
    return report;
  }
  for (uint8_t index = 0; index < frame.output_count; ++index) {
    if (frame.outputs[index].descriptor.gpio !=
        static_cast<uint8_t>(4U + index)) {
      report.status = SpiRefreshStatus::InvalidFrame;
      return report;
    }
  }

#if !defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
  const OwnedOutputFrame &spi2_output = frame.outputs[0];
  if (!encodeWs2811Spi(
          spi2_output.pixels, spi2_output.descriptor.pixel_count, kColorOrder,
          kDmaBuffers[0], sizeof(kDmaBuffers[0]), &kEncodedLengths[0])) {
    report.status = SpiRefreshStatus::EncodeFailed;
    return report;
  }
#endif
#if !defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
  const OwnedOutputFrame &spi3_output = frame.outputs[kSecondarySpiOutputIndex];
#if defined(LIGHT_BELT_GPIO5_SPI6BIT_DIAGNOSTIC)
  const bool spi3_encoded = encodeWs2811Spi6(
      spi3_output.pixels, spi3_output.descriptor.pixel_count, kColorOrder,
      kDmaBuffers[kSecondarySpiOutputIndex],
      sizeof(kDmaBuffers[kSecondarySpiOutputIndex]),
      &kEncodedLengths[kSecondarySpiOutputIndex]);
#elif defined(LIGHT_BELT_GPIO5_SPI3BIT_DIAGNOSTIC)
  const bool spi3_encoded = encodeWs2811Spi3(
      spi3_output.pixels, spi3_output.descriptor.pixel_count, kColorOrder,
      kDmaBuffers[kSecondarySpiOutputIndex],
      sizeof(kDmaBuffers[kSecondarySpiOutputIndex]),
      &kEncodedLengths[kSecondarySpiOutputIndex]);
#else
  const bool spi3_encoded = encodeWs2811Spi(
      spi3_output.pixels, spi3_output.descriptor.pixel_count, kColorOrder,
      kDmaBuffers[kSecondarySpiOutputIndex],
      sizeof(kDmaBuffers[kSecondarySpiOutputIndex]),
      &kEncodedLengths[kSecondarySpiOutputIndex]);
#endif
  if (!spi3_encoded) {
    report.status = SpiRefreshStatus::EncodeFailed;
    return report;
  }
#endif
  size_t rmt_pulse_count = 0;
  const OwnedOutputFrame &rmt_output = frame.outputs[kRmtOutputIndex];
  if (!encodeWs2811Rmt(
          rmt_output.pixels, rmt_output.descriptor.pixel_count, kColorOrder,
          kRmtPulses, sizeof(kRmtPulses) / sizeof(kRmtPulses[0]),
          &rmt_pulse_count)) {
    report.status = SpiRefreshStatus::EncodeFailed;
    return report;
  }
  for (size_t index = 0; index < rmt_pulse_count; ++index) {
    rmt_item32_t item{};
    item.level0 = 1;
    item.duration0 = kRmtPulses[index].high_ticks;
    item.level1 = 0;
    item.duration1 = kRmtPulses[index].low_ticks;
    kRmtItems[index] = item;
  }
  rmt_item32_t reset{};
  reset.level0 = 0;
  reset.duration0 = kHybridRmtResetTicks;
  reset.level1 = 0;
  reset.duration1 = 1;
  kRmtItems[rmt_pulse_count] = reset;
  const size_t rmt_item_count = rmt_pulse_count + 1U;

  auto failRmt = [&](esp_err_t error) {
    rmt_tx_stop(kHybridRmtChannel);
    rmt_set_idle_level(
        kHybridRmtChannel, true, RMT_IDLE_LEVEL_LOW);
    backend_fault_latched_ = true;
    report.status = SpiRefreshStatus::TransmitFailed;
    report.esp_error = error;
    return report;
  };
  esp_err_t result =
      rmt_wait_tx_done(kHybridRmtChannel, 0);
  if (result != ESP_OK) {
    return failRmt(result);
  }
  result = rmt_write_items(
      kHybridRmtChannel, kRmtItems,
      static_cast<int>(rmt_item_count), false);
  if (result != ESP_OK) {
    return failRmt(result);
  }
  result = rmt_wait_tx_done(kHybridRmtChannel, kHybridRmtWaitTicks);
  if (result != ESP_OK) {
    return failRmt(result);
  }
  ++report.successful_transactions;

#if defined(LIGHT_BELT_GPIO5_RMT_DIAGNOSTIC)
  report.status = SpiRefreshStatus::Ok;
  return report;
#else
  constexpr uint8_t kSpiOutputIndices[] = {0, kSecondarySpiOutputIndex};
  for (uint8_t transaction_index = 0;
       transaction_index < sizeof(kSpiOutputIndices) /
                               sizeof(kSpiOutputIndices[0]);
       ++transaction_index) {
    const uint8_t output_index = kSpiOutputIndices[transaction_index];
    spi_transaction_t transaction{};
    transaction.length = kEncodedLengths[output_index] * 8U;
    transaction.tx_buffer = kDmaBuffers[output_index];
    spi_device_handle_t target =
        output_index == 0 ? device_ : secondary_device_;
    result = spi_device_polling_transmit(target, &transaction);
    if (result != ESP_OK) {
      report.status = SpiRefreshStatus::TransmitFailed;
      report.esp_error = result;
      return report;
    }
    ++report.successful_transactions;
  }
#endif
  report.status = SpiRefreshStatus::Ok;
  return report;
#endif
#if defined(LIGHT_BELT_QIO_DIAGNOSTIC)
  if (frame.output_count != OUTPUT_COUNT) {
    report.status = SpiRefreshStatus::InvalidFrame;
    return report;
  }

  Ws2811ParallelSpiLane lanes[WS2811_PARALLEL_SPI_MAX_LANES] = {};
  for (uint8_t index = 0; index < frame.output_count; ++index) {
    const OwnedOutputFrame &output = frame.outputs[index];
    if (output.descriptor.gpio != static_cast<uint8_t>(4U + index)) {
      report.status = SpiRefreshStatus::InvalidFrame;
      return report;
    }
    lanes[index] = {output.pixels, output.descriptor.pixel_count};
  }

  size_t encoded_len = 0;
  if (!encodeWs2811ParallelSpi(
          lanes, frame.output_count, kColorOrder, kParallelDmaBuffer,
          sizeof(kParallelDmaBuffer), &encoded_len)) {
    report.status = SpiRefreshStatus::EncodeFailed;
    return report;
  }
  spi_transaction_t transaction{};
  transaction.flags = SPI_TRANS_MODE_QIO;
  transaction.length = encoded_len * 8U;
  transaction.tx_buffer = kParallelDmaBuffer;
  const esp_err_t result =
      spi_device_polling_transmit(device_, &transaction);
  if (result != ESP_OK) {
    report.status = SpiRefreshStatus::TransmitFailed;
    report.esp_error = result;
    return report;
  }
  report.successful_transactions = 1;
  report.status = SpiRefreshStatus::Ok;
  return report;
#endif
#if !defined(LIGHT_BELT_QIO_DIAGNOSTIC)
#if defined(LIGHT_BELT_FIXED_GPIO4_SPI)
  if (frame.output_count != OUTPUT_COUNT) {
    report.status = SpiRefreshStatus::InvalidFrame;
    return report;
  }
  constexpr uint8_t first_output = 0;
  constexpr uint8_t end_output = 1;
#else
  constexpr uint8_t first_output = 0;
  const uint8_t end_output = frame.output_count;
#endif

  // Encode all outputs before changing any physical strip. An encoding error
  // therefore cannot display a partial logical frame.
  for (uint8_t index = first_output; index < end_output; ++index) {
    const OwnedOutputFrame &output = frame.outputs[index];
    if (!supportedDataPin(output.descriptor.gpio) ||
        !encodeWs2811Spi(
            output.pixels,
            output.descriptor.pixel_count,
            kColorOrder,
            kDmaBuffers[index],
            sizeof(kDmaBuffers[index]),
            &kEncodedLengths[index])) {
      report.status = SpiRefreshStatus::EncodeFailed;
      return report;
    }
  }

  for (uint8_t index = first_output; index < end_output; ++index) {
#if !defined(LIGHT_BELT_FIXED_GPIO4_SPI)
    if (!routeTo(frame.outputs[index].descriptor.gpio)) {
      report.status = SpiRefreshStatus::RouteFailed;
      report.esp_error = last_gpio_error_;
      return report;
    }
#endif
    spi_transaction_t transaction{};
    transaction.length = kEncodedLengths[index] * 8U;
    transaction.tx_buffer = kDmaBuffers[index];
    const esp_err_t result = spi_device_polling_transmit(device_, &transaction);
#if defined(LIGHT_BELT_FIXED_GPIO4_SPI)
    if (result != ESP_OK) {
      report.status = SpiRefreshStatus::TransmitFailed;
      report.esp_error = result;
      return report;
    }
#else
    const bool detached = detachCurrent();
    if (result != ESP_OK) {
      report.status = SpiRefreshStatus::TransmitFailed;
      report.esp_error = result;
      return report;
    }
    if (!detached) {
      report.status = SpiRefreshStatus::RouteFailed;
      report.esp_error = last_gpio_error_;
      return report;
    }
#endif
    ++report.successful_transactions;
  }

  report.status = SpiRefreshStatus::Ok;
  return report;
#endif
}

bool SpiWs2811Backend::initialized() const { return initialized_; }

bool SpiWs2811Backend::routeTo(uint8_t gpio) {
  last_gpio_error_ = ESP_OK;
  if (!supportedDataPin(gpio)) {
    last_gpio_error_ = ESP_ERR_INVALID_ARG;
    return false;
  }
  if (!detachCurrent()) {
    return false;
  }
  last_gpio_error_ =
      gpio_set_direction(static_cast<gpio_num_t>(gpio), GPIO_MODE_OUTPUT);
  if (last_gpio_error_ != ESP_OK) {
    return false;
  }
  last_gpio_error_ = gpio_set_level(static_cast<gpio_num_t>(gpio), 0);
  if (last_gpio_error_ != ESP_OK) {
    return false;
  }
  esp_rom_gpio_connect_out_signal(gpio, FSPID_OUT_IDX, false, false);
  current_gpio_ = static_cast<int8_t>(gpio);
  return true;
}

bool SpiWs2811Backend::detachCurrent() {
  if (current_gpio_ < 0) {
    last_gpio_error_ = ESP_OK;
    return true;
  }
  const uint8_t gpio = static_cast<uint8_t>(current_gpio_);
  esp_rom_gpio_connect_out_signal(gpio, SIG_GPIO_OUT_IDX, false, false);
  current_gpio_ = -1;
  last_gpio_error_ =
      gpio_set_direction(static_cast<gpio_num_t>(gpio), GPIO_MODE_OUTPUT);
  if (last_gpio_error_ != ESP_OK) {
    return false;
  }
  last_gpio_error_ = gpio_set_level(static_cast<gpio_num_t>(gpio), 0);
  return last_gpio_error_ == ESP_OK;
}

}  // namespace light_belt
