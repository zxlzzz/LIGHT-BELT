#ifndef LIGHT_BELT_ESP32_OWNED_FRAME_H
#define LIGHT_BELT_ESP32_OWNED_FRAME_H

#include <stdint.h>

#include "protocol.h"

namespace light_belt {

struct RgbPixel {
  uint8_t r;
  uint8_t g;
  uint8_t b;
};

static_assert(sizeof(RgbPixel) == 3, "RGB pixels must remain tightly packed");

struct OwnedOutputFrame {
  OutputDescriptor descriptor;
  RgbPixel pixels[MAX_PIXELS_PER_OUTPUT];
};

// Unlike UdpV3Frame, this type owns every pixel. It is safe to place in a
// FreeRTOS queue after the UDP receive buffer has been reused.
struct OwnedNodeFrame {
  uint8_t node_id;
  uint8_t flags;
  uint32_t sequence;
  uint64_t media_timestamp_us;
  uint64_t apply_at_us;
  uint8_t output_count;
  OwnedOutputFrame outputs[MAX_OUTPUTS];
};

// Copies a parsed frame into configured-output order. Failure leaves out
// unchanged, so callers cannot enqueue a partially copied node frame.
bool copyUdpV3Frame(
    const UdpV3Frame &source,
    const OutputDescriptor *configured_outputs,
    uint8_t configured_output_count,
    OwnedNodeFrame *out);

}  // namespace light_belt

#endif
