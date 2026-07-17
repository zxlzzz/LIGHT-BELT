# Node 2 Gate 1m SPI6 Baseline

This directory preserves the exact onsite Node 2 emergency binary that gave
the best recorded Gate 1m behavior. It is a hardware-investigation baseline,
not a production-approved image.

```text
file: firmware.bin
size: 731328 bytes
SHA256: C47760A6B33A36B1CB4D67AF3A380742B93C7701036B02B45A501FA6881AE420
node: 2
expected IP: 192.168.31.202
output: GPIO4, 10 groups
backend: spi6_dma_fixed_gpio4
presentation: Immediate
policy: emergency change-only, group 0 black, restricted state graph
wire timing: 5 MHz, 0=100000, 1=111000, 500 us low reset guard
status: NOT HARDWARE VERIFIED; T0H=200 ns is outside the user-provided
        WS2811 V2.1 excerpt's 220 ns minimum
```

The file was recovered from `<operator-downloads>\firmware.bin` on 2026-07-17
and copied byte-for-byte to the project workspace. The source tree has since
changed: rebuilding the similarly named PlatformIO environment does not
reproduce this binary and currently selects guarded SPI4. Do not replace this
file with a fresh build.

Before every flash, verify the SHA-256. The embedded startup identity must
contain `spi6_dma_fixed_gpio4`, `change_only=1`, `presentation=immediate`,
`exact_groups=10`, and `group0=black`.
