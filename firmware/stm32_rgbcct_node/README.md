# STM32 RGB+CCT Node

NOT HARDWARE VERIFIED.

PlatformIO firmware for one addressed STM32F103C8T6 RGB+CCT node on the shared
RS-485 v2 bus. The default board target is `bluepill_f103c8`.

Central configuration lives in `src/config.h`: node ID, five PWM pins, USART1
pins, baud rate, byte timeout, and safety timeout. The default safe state is
all black.

Build:

```powershell
pio run -d firmware/stm32_rgbcct_node
```
