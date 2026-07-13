# ESP32-S3 independent WS2811 outputs (UDP v3)

NOT HARDWARE VERIFIED.

This firmware consumes exactly one complete UDP v3 frame for one ESP32-S3
node.  It supports one to three electrically independent WS2811 strips, with
one distinct GPIO per strip: GPIO4, GPIO5, and GPIO6 only.  It never joins
their pixel buffers into a continuous strip.

Configure `src/config.example.h` (or your local build configuration) with one
non-zero output ID, one GPIO, and a length of 1–100 pixels for every enabled
output.  GPIO and output IDs must be unique.  The default has three 10-pixel
outputs solely as a compile-time example; it is not a final wiring plan.

Each output needs its own data path:

```text
ESP32 GPIO4/5/6 -> SN74LVC1T45 A -> SN74LVC1T45 B -> matching WS2811 DI
```

Use ESP32 3V3 for `VCCA` and `DIR`, 5V for `VCCB`, and a common ground for the
ESP32, level shifters, WS2811 strips, 24V supply return, and 5V buck return.
The 24V strip power is parallel power, not a data daisy chain.  This electrical
description and all GPIO assignments are NOT HARDWARE VERIFIED.

For deterministic reset behavior, hold each SN74LVC1T45 A-side data input low
with an external 10 kOhm pull-down and keep `DIR` defined high with a direct
3V3 connection or pull-up. A 220-470 Ohm series resistor near each strip DI is
also recommended. Firmware drives GPIO4/5/6 low before enabling the direction
signals, but external biasing is still required while the MCU itself is held
in reset and its GPIOs are high-impedance.

The parser validates the whole datagram—v3 header, node, CRC, configured
output IDs, GPIOs, lengths, output set, and sequence—before any displayed
buffer changes.  An accepted packet stages every output, then performs exactly
one `FastLED.show()` across the registered GPIO outputs.  Duplicate, stale,
out-of-order, malformed, incomplete, unknown, or oversized packets retain the
last complete visible frame. `apply_at_us` is parsed but not scheduled in this
initial release. After `SAFE_TIMEOUT_MS` without an accepted frame, every
configured output is refreshed black.

Build and run native protocol/state tests:

```powershell
pio test -d firmware/esp32_ws2811_node -e native
pio run -d firmware/esp32_ws2811_node
```

`firmware/shared/udp_v3_golden.h` is generated from the JSON Golden Vector
source and is consumed by the native protocol tests.  It must not be edited by
hand.
