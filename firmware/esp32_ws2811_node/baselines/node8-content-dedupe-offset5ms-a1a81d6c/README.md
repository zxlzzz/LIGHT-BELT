# Node 8 Content-Dedupe Offset 5 ms A/B

Status: **NOT HARDWARE VERIFIED**

- Built: 2026-07-17
- Environment: `esp32-s3-node-8-fixed-gpio4-content-dedupe-offset5ms-ab`
- File: `firmware.bin`
- Size: `727952` bytes
- SHA-256: `A1A81D6CBA0FC958FD5C355F0079952F06393BE3AA13862509B88BF5C5263D2C`
- Node: 8 / `192.168.31.208` / 20 groups / GPIO4
- Wire encoding: SPI4 at 3.2 MHz, RGB, `0=1000`, `1=1100`
- Reset guards: 500 us before and after every physical transaction
- Content policy: unrestricted complete-payload dedupe; KEY and SAFE force a
  physical write
- Offset policy: only non-skipped Immediate Host writes wait 5000 us after
  preparation; Scheduled, startup, watchdog, recovery, and retry do not
- Runtime oracle for the 75-second staged breath: `physical_offset_waits=624`
  and `physical_offset_cancelled=0`

This is a transaction-overlap diagnostic. It is not a production image and
does not claim strict cross-node synchronization.
