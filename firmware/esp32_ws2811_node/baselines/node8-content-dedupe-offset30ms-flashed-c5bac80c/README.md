# Node 8 current flashed 30 ms baseline

- Device: Node 8 / COM13 / `192.168.31.208`
- MAC observed by esptool: `28:84:85:8A:36:B0`
- Environment: `esp32-s3-node-8-fixed-gpio4-content-dedupe-offset30ms-ab`
- Size: 727952 bytes
- SHA-256: `C5BAC80C948578AC3EA6D0873D004795B0C42B97C0221BA05F1EB56D8126A44B`
- Upload: all written partitions reported `Hash of data verified`.
- Field readback: offset `0x10000`, length 727952 bytes; esptool 4.11.0
  produced the same SHA-256 without erasing or writing.

This is the authoritative retained Node 8 field image for the 2026-07-17 asset
freeze. It uses guarded SPI4, exact-content dedupe, and a 30 ms delay for
non-skipped Immediate Host writes. It is a diagnostic image and is **NOT
HARDWARE VERIFIED** as a production solution.
