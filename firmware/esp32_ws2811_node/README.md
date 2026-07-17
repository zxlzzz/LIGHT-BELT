# ESP32-S3 one-strip WS2811 nodes (UDP v3)

NOT HARDWARE VERIFIED.

Each production ESP32 consumes one complete UDP v3 node frame and drives one
WS2811 strip through output ID 1 on GPIO4. One logical strip maps to one
physical node; production firmware does not join strip buffers or share one
ESP32 data backend across strips. Explicit legacy Node 2 environments retain
the earlier multi-output diagnostics for comparison only.

Every newly opened Host UDP v3 output marks sequence 1 as `KEY_FRAME`. Host
encodes every target node before any send, then transmits three complete rounds
2 ms apart. Each node receives the same raw KEY bytes in every round, and all
nodes/rounds share one apply/media identity. Firmware treats only that exact
flag/sequence pair as a new session and deduplicates repeated apply/media
identity without advancing generation. Successful KEY preparation admits the
generation. If its timed physical output later fails, the backend restores the
previous committed frame or black while the next complete scheduled frame may
recover. Generation zero, ordinary duplicate, and stale non-KEY frames remain
rejected. This allows a completed show to run again without resetting ESP32.

## Scheduled production presentation

Every `esp32-s3-node-N` production image enables both
`LIGHT_BELT_FIXED_GPIO4_SPI` and `LIGHT_BELT_REQUIRE_SCHEDULED_APPLY`.
Production therefore rejects an immediate UDP v3 frame instead of displaying
it on receipt. Explicit legacy Node 2 diagnostic environments do not enable
that requirement and retain immediate behavior.

The site profiles use one Host monotonic clock for both a broadcast clock
beacon and the frame deadline. On output startup the Host sends five beacons
10 ms apart; during playback it sends a beacon at most every 500 ms. Every
node datagram for one logical frame shares
`apply_at_us = host_monotonic_us + 20000` and sets `SCHEDULED_APPLY`.

These are the current formal profile values, not a hardware-accepted timing
set. The robust Node 2 A/B used a 60 ms lead, 100 ms beacon interval, and 32
startup beacons 50 ms apart. Formal profile migration remains a P1 Scheduled
hardware gate and must not be mixed into Immediate output commissioning.

Firmware samples `local esp_timer - Host monotonic` and uses the minimum
offset in its bounded window as the conversion estimate; the window spread is
reported as clock uncertainty. Current defaults require at least 3 samples in
a 32-sample window, reject samples older than 2 s or uncertainty above 5 ms,
allow at most 2 ms start lateness, and reject deadlines more than 100 ms ahead.
There is no wall-clock or UTC dependency.

The production output task prepares the complete DMA buffer without touching
GPIO, computes `tx_start = local_apply_deadline - encoded_wire_time`, and only
then starts the permanently routed GPIO4 SPI transaction. The common
`apply_at_us` is the guaranteed WS2811 latch-completion boundary, not the time
at which every unequal-length strip begins sending:

| Groups | Encoded bytes | 3.2 MHz wire time |
|---:|---:|---:|
| 10 | 520 | 1300 us |
| 20 | 640 | 1600 us |
| 40 | 880 | 2200 us |

Clock-not-ready, invalid, too-late, too-far, cancelled, and immediate
production frames fail closed and are counted in serial statistics. The
Host/firmware scheduling path is software implemented. Actual cross-node
latch skew remains **NOT HARDWARE VERIFIED** until powered GPIO/data paths are
captured with a logic analyzer.

The output task checks safe timeout before every queue receive so a continuous
frame stream cannot starve safe black. Scheduled transmission calls
`transmitPrepared(..., false)`: if SPI fails, firmware cancels the backend's
prepared buffer and recovers locally instead of blindly sending a second full
transaction after the validated start deadline. Session admission remains
available to the next complete scheduled frame. Immediate diagnostics retain
their explicit retry behavior.

## Electrical assumption

Each production node uses one independent level shifter:

```text
ESP32 GPIO4 -> SN74LVC1T45 A -> SN74LVC1T45 B -> WS2811 DI
```

For the current installation, connect SN74LVC1T45 `DIR` directly to ESP32
3V3. The firmware has no direction-control GPIO. Use 3V3 for `VCCA`, 5V for
`VCCB`, and a common ground for the ESP32, level shifters, WS2811 strips, 24V
supply return, and 5V buck return. Every encoded transaction starts and ends
with a low reset interval; no production firmware path drives GPIO5, GPIO6,
GPIO15, GPIO16, or GPIO17. Explicit legacy Node 2 diagnostics may still drive
GPIO5 and GPIO6.

The 24V strip supply is parallel power, not a data daisy chain. All electrical
details and the complete 13-node topology remain NOT HARDWARE VERIFIED until
onsite acceptance completes. The fixed GPIO4 single-lane path has prior onsite
evidence, but that evidence does not verify the new node assignments.

## Node selection

`src/config.local.h` contains only the Wi-Fi credentials. Start from the
ignored example:

```powershell
Copy-Item firmware\esp32_ws2811_node\src\config.local.example.h `
  firmware\esp32_ws2811_node\src\config.local.h
```

Select the physical node only through its PlatformIO environment:

| Environment | Node | Logical strip | Fixed IP | Output | GPIO | Groups |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `esp32-s3-node-1` | 1 | `strip_11` | `192.168.31.201` | 1 | 4 | 10 |
| `esp32-s3-node-2` | 2 | `strip_41` | `192.168.31.202` | 1 | 4 | 10 |
| `esp32-s3-node-3` | 3 | `strip_44` | `192.168.31.203` | 1 | 4 | 20 |
| `esp32-s3-node-4` | 4 | `strip_12` | `192.168.31.204` | 1 | 4 | 40 |
| `esp32-s3-node-5` | 5 | `strip_22` | `192.168.31.205` | 1 | 4 | 40 |
| `esp32-s3-node-6` | 6 | `strip_21` | `192.168.31.206` | 1 | 4 | 10 |
| `esp32-s3-node-7` | 7 | `strip_31` | `192.168.31.207` | 1 | 4 | 10 |
| `esp32-s3-node-8` | 8 | `strip_42` | `192.168.31.208` | 1 | 4 | 20 |
| `esp32-s3-node-9` | 9 | `strip_91` | `192.168.31.209` | 1 | 4 | 20 |
| `esp32-s3-node-10` | 10 | `strip_92` | `192.168.31.210` | 1 | 4 | 20 |
| `esp32-s3-node-11` | 11 | `strip_43` | `192.168.31.211` | 1 | 4 | 20 |
| `esp32-s3-node-12` | 12 | `strip_45` | `192.168.31.212` | 1 | 4 | 20 |
| `esp32-s3-node-13` | 13 | `strip_93` | `192.168.31.213` | 1 | 4 | 20 |

Every production environment enables `LIGHT_BELT_FIXED_GPIO4_SPI`. SPI2 is
routed to GPIO4 once during initialization and remains attached while frames
play; production refreshes never detach or reroute the GPIO matrix signal.
The startup log identifies the current production candidate as
`spi4_dma_fixed_gpio4_500us_candidate_not_hardware_verified`. It uses the
3.2 MHz `1000`/`1100` encoding with symmetric 500 us reset-low guards. This
identity is a deployment diagnostic, not a hardware-verification claim.

The old three-output Node 2 header is available only when
`LIGHT_BELT_NODE2_LEGACY_MULTI_OUTPUT` is defined by an explicit diagnostic
environment. The normal `esp32-s3-node-2` image is now one 10-group output for
`strip_41`.

`esp32-s3-node-2-fixed-gpio4-diagnostic` accepts the legacy complete Node 2
three-output UDP frame but physically refreshes only strip 41 through the
permanently routed GPIO4 SPI signal. The separate
`esp32-s3-node-2-fixed-gpio4-strip42-diagnostic` remains a one-output,
20-group strip 42 isolation image.

`esp32-s3-node-2-qio-parallel-diagnostic` was a hardware candidate. It sends
one QIO DMA transaction with permanently routed `DATA0/1/2` on GPIO4/5/6.
Unused `DATA3` is routed to otherwise-unused GPIO7 and every encoded DATA3 bit
is zero. The QIO buffer-to-DATA lane order remains NOT HARDWARE VERIFIED;
GPIO7's onsite electrical availability is also NOT HARDWARE VERIFIED.

The QIO gate failed on real hardware: white/black frames produced flashing,
cross-lane colors, and an incomplete final black state. It must not be used for
Stage 2 or promoted to production.

`esp32-s3-node-2-hybrid-fixed-diagnostic` preserves the successful strip 41
path on permanently bound SPI2/GPIO4, adds a separate permanently bound
SPI3/GPIO5 for strip 42, and reserves one fixed RMT0/GPIO6 channel for strip
43. It never changes GPIO matrix routing while frames are playing. This is the
legacy multi-output hardware gate. It is not a production environment.

The firmware sends host-quantized RGB bytes without applying another
brightness scale. `WS2811_COLOR_ORDER` is a project-owned RGB/GRB setting and
does not depend on FastLED.

## Build and upload

Keep PlatformIO state and build products under this A-drive worktree and turn
off telemetry for the current PowerShell session:

```powershell
$project = (Resolve-Path "firmware\esp32_ws2811_node").Path
$env:PLATFORMIO_CORE_DIR = Join-Path $project ".pio\core"
$env:PLATFORMIO_PLATFORMS_DIR = Join-Path $project ".pio\platforms"
$env:PLATFORMIO_PACKAGES_DIR = Join-Path $project ".pio\packages"
$env:PLATFORMIO_CACHE_DIR = Join-Path $project ".pio\cache"
$env:PLATFORMIO_BUILD_CACHE_DIR = Join-Path $project ".pio\cache\build"
$temp = Join-Path $project ".pio\tmp"
New-Item -ItemType Directory -Force -Path $temp | Out-Null
$env:TEMP = $temp
$env:TMP = $temp
$env:TMPDIR = $temp
$env:PLATFORMIO_SETTING_ENABLE_TELEMETRY = "No"
```

Confirm that `(Get-Command pio).Source` is also on the A drive before running
PlatformIO. The Windows sandbox helper searches only the project-local
`PROJECT_PACKAGES_DIR` and `.pio\packages`; it does not inspect a user-profile
`.platformio` directory.

The default environment is deliberately non-hardware `native`. Every firmware
build and upload must name exactly one `esp32-s3-node-N` environment.

On Windows, run the native protocol, ownership, state, and encoder tests with
the repository wrapper. It uses the installed Visual Studio C++ compiler and
writes every object, executable, dependency, and temporary file below the
project-local `.pio` directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  firmware\esp32_ws2811_node\scripts\run_native_tests_msvc.ps1
```

On a host where `gcc` and `g++` are already available, the equivalent
PlatformIO command remains `pio test -d firmware/esp32_ws2811_node -e native`.

Build every production node image explicitly and sequentially. Keep SCons at
two jobs so Windows does not expand its C-drive page file under compiler
pressure:

```powershell
1..13 | ForEach-Object {
  pio run -j 2 -d firmware\esp32_ws2811_node -e "esp32-s3-node-$_"
  if ($LASTEXITCODE -ne 0) {
    throw "ESP32 Node $_ build failed with exit code $LASTEXITCODE"
  }
}
```

Always name exactly one environment and the intended serial port when
uploading. For example, Node 8 on COM7 is:

```powershell
pio run -d firmware\esp32_ws2811_node -e esp32-s3-node-8 `
  -t upload --upload-port COM7
pio device monitor --port COM7 --baud 115200
```

The production single-lane candidate encodes WS2811 data at 3.2 MHz with
`0=1000` and `1=1100`, producing 312.5/937.5 ns for zero and 625/625 ns for
one. Symmetric 200-byte zero guards hold GPIO4 low for 500 us before and after
every payload. It uses the previously exercised SPI2/GPIO4 path and keeps that
route permanent from initialization onward. It pre-encodes before the
scheduled start and compensates the complete transaction length shown above,
including both reset guards. This candidate is **NOT HARDWARE VERIFIED**. The
hybrid SPI3/RMT, QIO, timing, SPI6, and FastLED variants remain explicit
immediate legacy diagnostics.

`firmware/shared/udp_v3_golden.h` is generated from the JSON Golden Vector
source and is consumed by native protocol tests. It must not be edited by
hand.

## Legacy Node 2 diagnostics

The fixed-GPIO4 isolation image completed the earlier Stage 1 on strip 41.
These commands reproduce the old three-output Node 2 diagnostics; their UDP
frame contract does not match the production one-strip Node 2 image. Set the
observed serial port once, then build, upload, and monitor the explicit legacy
hybrid image:

```powershell
$port = "COM7"
pio run -d firmware\esp32_ws2811_node `
  -e esp32-s3-node-2-hybrid-fixed-diagnostic `
  -t upload --upload-port $port
pio device monitor --port $port --baud 115200
```

The startup log must identify `node_id=2`,
`backend=spi2_spi3_rmt_fixed_diagnostic`, `dir=3v3`, and
`expected_ip=192.168.31.202`, followed by `wifi_connected` and `udp_bound`.
`wifi_placeholder compile_only=1` means the wrong image was built and is a
hard failure.

First run the 17-second white/black lane isolation from a second PowerShell.
Only strip 41 may be white from 2-7 seconds, only strip 42 may be white from
9-14 seconds, and both must be black in every gap and after exit:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config "config\profiles\node2-effects-demo.yaml" run `
  --show "config\shows\ws2811-node2-lane-isolation.yaml"
```

Then rerun the Stage 1 nine-effect strip 41 show:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config "config\profiles\node2-effects-demo.yaml" run `
  --show "config\shows\ws2811-stage1-strip41-nine-effects.yaml"
```

Only after both strips remain stable, run the deterministic strip 41 to strip
42 cross-fade:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config "config\profiles\node2-effects-demo.yaml" run `
  --show "config\shows\ws2811-stage2-strip41-to-strip42.yaml"
```

Production acceptance requires all intended one-strip nodes to be flashed with
their matching `esp32-s3-node-N` environments. Run the complete show only with
the matching one-ESP-per-strip physical profile:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config "config\profiles\ws2811-installed-one-esp-per-strip.yaml" run `
  --show "config\shows\ws2811-stage3-installed-300s.yaml"
```

During an uninterrupted production run, `parse_rejected`, `state_rejected`,
`clock_not_ready`, `scheduled_late`, `scheduled_far`, `scheduled_invalid`,
`scheduled_start_late`, `scheduled_cancelled`, `immediate_dropped`,
`output_errors`, `invariant_errors`, and `timeout_black` must remain zero;
`beacon_ok`, `clock_samples`, `clock_ready`, `scheduled_commit`, and
`deadline_error_us` must be retained with the acceptance record.
`session_key_dupes` is expected to count redundant session-start copies, but
those copies must create only one generation and one physical commit.
The first-group electrical behavior, actual RGB/GRB order, installed wiring,
every visual result, and real latch skew remain NOT HARDWARE VERIFIED until
these stages and powered logic-analyzer acceptance pass.
