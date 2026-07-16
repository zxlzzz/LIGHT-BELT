#include "owned_frame.h"

#include <stddef.h>

namespace light_belt {

bool copyUdpV3Frame(
    const UdpV3Frame &source,
    const OutputDescriptor *configured_outputs,
    uint8_t configured_output_count,
    OwnedNodeFrame *out) {
  if (out == nullptr ||
      !validateOutputDescriptors(configured_outputs, configured_output_count) ||
      source.output_count != configured_output_count ||
      (source.flags & ~UDP_V3_ALLOWED_FLAGS) != 0) {
    return false;
  }

  size_t expected_payload_len = 0;
  OwnedNodeFrame staged{};
  staged.node_id = source.node_id;
  staged.flags = source.flags;
  staged.sequence = source.sequence;
  staged.media_timestamp_us = source.media_timestamp_us;
  staged.apply_at_us = source.apply_at_us;
  staged.output_count = configured_output_count;

  for (uint8_t configured_index = 0;
       configured_index < configured_output_count;
       ++configured_index) {
    const OutputDescriptor &configured = configured_outputs[configured_index];
    const UdpV3OutputView *received = nullptr;
    uint8_t match_count = 0;
    for (uint8_t received_index = 0;
         received_index < source.output_count;
         ++received_index) {
      if (source.outputs[received_index].descriptor.output_id ==
          configured.output_id) {
        received = &source.outputs[received_index];
        ++match_count;
      }
    }

    const size_t pixel_bytes = static_cast<size_t>(configured.pixel_count) * 3U;
    if (match_count != 1 || received == nullptr || received->payload == nullptr ||
        received->descriptor.gpio != configured.gpio ||
        received->descriptor.pixel_count != configured.pixel_count ||
        received->payload_len != pixel_bytes) {
      return false;
    }

    OwnedOutputFrame &target = staged.outputs[configured_index];
    target.descriptor = configured;
    for (uint16_t pixel = 0; pixel < configured.pixel_count; ++pixel) {
      const size_t offset = static_cast<size_t>(pixel) * 3U;
      target.pixels[pixel] = {
          received->payload[offset],
          received->payload[offset + 1],
          received->payload[offset + 2],
      };
    }
    expected_payload_len += UDP_V3_OUTPUT_DESCRIPTOR_LEN + pixel_bytes;
  }

  if (source.payload_len != expected_payload_len) {
    return false;
  }

  *out = staged;
  return true;
}

}  // namespace light_belt
