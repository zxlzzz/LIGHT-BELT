# Node 2 current field readback

- Device: Node 2 / COM7 / `192.168.31.202`
- MAC observed by esptool: `E0:72:A1:D3:30:3C`
- Recorded environment: `esp32-s3-node-2-fixed-gpio4-content-dedupe-ab`
- Flash region: offset `0x10000`, length 727456 bytes
- SHA-256: `469631595379B5436CB1D1212419B7F6D6B45E2A77C60A602133896DCADBAFD0`
- Acquisition: esptool 4.11.0 `read_flash`; no erase or write operation.

The readback exactly matches the field identity recorded before the source tree
continued to evolve. A later rebuild did not reproduce this hash, so this
readback is the authoritative recoverable Node 2 application image for the
2026-07-17 freeze. It remains a diagnostic, **NOT HARDWARE VERIFIED**
production candidate.
