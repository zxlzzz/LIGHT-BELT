# Node 8 Content-Dedupe Offset 5 ms Flashed Image

Status: **NOT HARDWARE VERIFIED**

- Flashed: 2026-07-17 to COM13 / MAC `28:84:85:8A:36:B0`
- Environment: `esp32-s3-node-8-fixed-gpio4-content-dedupe-offset5ms-ab`
- File: `firmware.bin`
- Size: `727952` bytes
- SHA-256: `3B46D919A1DB836707B1B08DF3B9AB74ADB0A5F7563F7219028A3FF0FC886971`
- Upload result: every esptool section reported `Hash of data verified`

PlatformIO/esptool reported `SHA digest in image updated` during upload. The
pre-upload build artifact is preserved separately under
`node8-content-dedupe-offset5ms-a1a81d6c`; this directory preserves the
post-upload image left in the build path and used for the COM13 upload.

Behavior and runtime oracle are otherwise identical to the pre-upload README:
only non-skipped Immediate Host writes on Node 8 wait 5000 us, and the staged
75-second Show must report `physical_offset_waits=624` and
`physical_offset_cancelled=0`.
