# ESP32-S3 WS2811 Node

NOT HARDWARE VERIFIED.

PlatformIO firmware for one ESP32-S3 UDP v2 digital node. The node validates a
complete UDP v2 frame, applies latest-frame semantics by replacing the LED
buffer with each valid full frame, and calls `FastLED.show()` once per valid
frame. The default safe state is all black.

`src/config.example.h` is committed for non-secret defaults. Local Wi-Fi
credentials may be placed in `src/config.local.h`; when absent, placeholder
credentials compile and the firmware logs `WiFi placeholder SSID` at runtime.

Build:

```powershell
pio run -d firmware/esp32_ws2811_node
```
