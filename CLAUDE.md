# LIGHT-BELT project instructions

## Mission

Build a reliable RK3588-hosted, video/music-driven lighting controller for the
2100 mm x 1000 mm x 1800 mm cabin installation:

- 13 independently driven 24V WS2811 RGB strips through 13 ESP32-S3 controllers
- one 24V common-anode RGB+CCT COB zone through one STM32 RS-485 node

The cabin dimensions, placements, lengths, group counts, controller allocation,
electrical plan, and synchronization behavior are `NOT HARDWARE VERIFIED`.
They are the approved configurable contract, not proof of installed wiring.

RK3588 is the only production brain. RK3568 is backup/testing only.

## Hardware truth

Analog COB is not RGBW. It is six-wire common-anode RGB+CCT:

`+24V / R / G / B / WW / CW`

The only target analog run is physical label `32`, with logical ID `zone_32`.
It uses one configurable STM32 RS-485 node. Physical label `32` does not force
the STM32 bus address. This allocation is `NOT HARDWARE VERIFIED`.

Target digital logical IDs are `strip_<physical-label>` for physical labels
`11`, `12`, `21`, `22`, `31`, `41`, `42`, `43`, `44`, `45`, `91`, `92`, and
`93`. Physical label, logical ID, ESP32 node ID, GPIO, protocol node ID, and
Host API target ID are distinct concepts and must not be inferred from one
another.

### Cabin topology contract

All placement, length, and WS2811 group values in this table are
`NOT HARDWARE VERIFIED` and must remain configurable.

| Physical label | Logical ID | Placement | Technology | Length | Groups |
|---|---|---|---|---:|---:|
| 11 | `strip_11` | screen surround | WS2811 | 0.5 m | 10 |
| 12 | `strip_12` | ceiling edge | WS2811 | 2 m | 40 |
| 21 | `strip_21` | screen surround | WS2811 | 0.5 m | 10 |
| 22 | `strip_22` | floor/wall edge | WS2811 | 2 m | 40 |
| 31 | `strip_31` | screen surround | WS2811 | 0.5 m | 10 |
| 32 | `zone_32` | left porthole/door | RGB+CCT COB | configurable | n/a |
| 41 | `strip_41` | screen surround | WS2811 | 0.5 m | 10 |
| 42 | `strip_42` | right-wall wave | WS2811 | 1 m | 20 |
| 43 | `strip_43` | right-wall wave | WS2811 | 1 m | 20 |
| 44 | `strip_44` | right-wall wave | WS2811 | 1 m | 20 |
| 45 | `strip_45` | right-wall wave | WS2811 | 1 m | 20 |
| 91 | `strip_91` | reserved/removable run | WS2811 | 1 m | 20 |
| 92 | `strip_92` | reserved/removable run | WS2811 | 1 m | 20 |
| 93 | `strip_93` | reserved/removable run | WS2811 | 1 m | 20 |

The 13 digital runs total 260 independently addressable WS2811 groups.

### Production controller and electrical contract

Production uses one ESP32-S3 per WS2811 strip. Each node has exactly one
production output: `output_id: 1` on GPIO4. Node allocation is physical
configuration; logical IDs remain independent of node IDs, GPIO, and IP.

| ESP32 node | Logical strip | Groups | Output | GPIO | Site IPv4 |
|---:|---|---:|---:|---:|---|
| 1 | `strip_11` | 10 | 1 | 4 | `192.168.31.201` |
| 2 | `strip_41` | 10 | 1 | 4 | `192.168.31.202` |
| 3 | `strip_44` | 20 | 1 | 4 | `192.168.31.203` |
| 4 | `strip_12` | 40 | 1 | 4 | `192.168.31.204` |
| 5 | `strip_22` | 40 | 1 | 4 | `192.168.31.205` |
| 6 | `strip_21` | 10 | 1 | 4 | `192.168.31.206` |
| 7 | `strip_31` | 10 | 1 | 4 | `192.168.31.207` |
| 8 | `strip_42` | 20 | 1 | 4 | `192.168.31.208` |
| 9 | `strip_91` | 20 | 1 | 4 | `192.168.31.209` |
| 10 | `strip_92` | 20 | 1 | 4 | `192.168.31.210` |
| 11 | `strip_43` | 20 | 1 | 4 | `192.168.31.211` |
| 12 | `strip_45` | 20 | 1 | 4 | `192.168.31.212` |
| 13 | `strip_93` | 20 | 1 | 4 | `192.168.31.213` |

The current field subset is nodes `1`, `2`, `4`, `5`, `6`, `7`, `8`, `9`, and
`10`. Nodes `3`, `11`, `12`, and `13` belong to the complete target but are not
part of the nine-node field profile.

The IPv4 column is the site address contract. It is implemented by
`cabin-lighting-v3-site-local.yaml` for the complete target and by
`ws2811-installed-one-esp-per-strip.yaml` for the current subset. The generic
`cabin-lighting-v3-production.yaml` intentionally retains non-routable
`192.0.2.x` TEST-NET endpoints and `REPLACE_WITH_RS485_PORT`; it is an offline
production-shape template, not a site deployment profile. Never run it as a
substitute for either site profile or describe its TEST-NET endpoints as the
assigned site addresses.

Each strip data path passes through its controller's SN74LVC1T45. The strips
use parallel 24V power, the level shifters use a 5V B-side logic supply, and
all supplies/controllers require a common ground. This electrical plan, site
endpoint assignment, power segmentation, and real synchronization performance
remain configurable and `NOT HARDWARE VERIFIED`.

## Architectural invariants

- Analysis and effects are hardware-agnostic.
- Effects produce logical frames; physical mapping produces node frames.
- One logical frame owns one shared sequence and media timestamp.
- A newly opened UDP v3 Host session marks only sequence 1 as `KEY_FRAME`;
  Host pre-encodes every node before sending, then sends three byte-identical
  per-node rounds with one apply/media identity at 2 ms spacing. Firmware may
  reset committed sequence only for that exact pair and treats redundant
  copies idempotently. Successful KEY preparation admits the session. A later
  timed-output failure rolls back physically but keeps that admission so the
  next complete scheduled frame can recover without a blind late retry.
- RS-485 and UDP use that same sequence.
- Protocol codecs are pure and testable without hardware.
- Production transport failures must be explicit; never silently fall back to memory and report success.
- Fake/memory transports require explicit config or dependency injection.
- Output queues keep only the latest complete logical frame.
- Do not interleave packets from different logical frames.
- A digital physical node receives one complete UDP frame and refreshes once.
- Apply brightness exactly once.
- Do not claim hardware verification without real evidence.

## Protocols

RS-485 v2 is the documented 16-byte RGB+CCT frame using:

- sync `A5 5A`
- version 2
- node ID
- sequence
- R/G/B/WW/CW
- fade
- flags
- CRC-16/CCITT-FALSE

UDP v2 is the implemented legacy codec: one `pixel_count` and one continuous
RGB pixel payload per ESP32 node, with version, node ID, sequence, payload
length, and CRC32. Its codec, tests, and golden vectors remain unchanged.

UDP v3 is the target protocol introduced in Phase 26. Its general contract
continues to carry one complete node frame with one to three independent output
descriptors and payloads. Phase 31 production profiles use exactly one output
descriptor per ESP32-S3 (`output_id: 1`, GPIO4); this topology rule does not
narrow the codec or firmware protocol capability. Separate strips must not be
represented as one electrically concatenated strip. New cabin production
profiles use v3, while v2 remains legacy.

Phase 31 production presentation is scheduled. The Host broadcasts its
monotonic clock, assigns one shared `apply_at_us = host_monotonic_us + 20 ms`
to every UDP v3 node packet for a logical frame, and sets `SCHEDULED_APPLY`.
Each ESP32 estimates `local_monotonic_us - host_monotonic_us` from the minimum
offset in a bounded beacon window, prepares the complete strip frame without
touching GPIO, and starts its fixed GPIO4 SPI transaction early enough for the
common `apply_at_us` to mean guaranteed WS2811 latch completion. The fixed
GPIO4 production candidate uses 3.2 MHz four-bit `1000`/`1100` encoding with
symmetric 200-byte (500 us) low guards. Complete wire times are 1300 us for 10
groups, 1600 us for 20 groups, and 2200 us for 40 groups. This output candidate
remains **NOT HARDWARE VERIFIED**.

All production `esp32-s3-node-N` images require scheduled frames. Explicit
legacy Node 2 diagnostic images retain immediate application and are not
strict-synchronization evidence. The Host/firmware scheduling contract is
software implemented, but actual cross-node latch skew remains **NOT HARDWARE
VERIFIED** until powered nodes are measured with a logic analyzer.

The firmware output task checks safe timeout on every loop, including under a
continuous scheduled queue. A scheduled SPI failure must not blindly repeat a
full wire transaction after the validated start deadline; it fails closed and
recovers locally. Immediate diagnostic output may retain its explicit retry
behavior.

Keep protocol golden vectors shared between host and firmware documentation/tests.

## Compatibility

- Preserve the validated video/audio analyzers and effects unless a test proves change is required.
- Keep Windows development/simulation working.
- Support RK3588 ARM64 Linux.
- Use config for hardware-specific values.
- If public models are migrated, update all callers and tests consistently; do not leave mixed RGBW/RGB+CCT semantics.

## Windows Python interpreter

On Windows, this repository must use only the bundled interpreter:

`.\\.python\\Scripts\\python.exe`

Never invoke any of the following on Windows:

* `python`
* `python3`
* `py`
* a Python executable outside this repository
* a Python executable from the C: drive

All Python commands must begin with:

`.\\.python\\Scripts\\python.exe`

Before the first Python command in each Claude Code session, verify the interpreter.
Codex on Windows may remap the repository into a sandbox-local path such as
`<sandbox-home>\.codex\.sandbox\cwd\<sandbox-id>`, so do not
require `sys.executable` to contain the original drive path or repository
directory name.

`.\\.python\\Scripts\\python.exe -c "import sys, pathlib, light_engine; cwd=pathlib.Path.cwd().resolve(); exe=pathlib.Path(sys.executable).resolve(); pkg=pathlib.Path(light_engine.__file__).resolve(); candidates=[cwd/'.python'/'Scripts'/'python.exe', cwd/'.python'/'python.exe']; existing=[c for c in candidates if c.exists()]; assert existing, 'No bundled Python found'; assert any(c.resolve()==exe for c in existing), 'Executable mismatch'; assert exe.name.lower()=='python.exe'; assert str(pkg).startswith(str(cwd)); print('executable=', exe); print('package=', pkg); print('PROJECT_PYTHON_OK')"`

The command is valid when it was invoked as `.\\.python\\Scripts\\python.exe`,
the current workspace contains `.python\\Scripts\\python.exe` (or the legacy
`.python\\python.exe`), at least one of those candidate paths resolves to the
same file as `sys.executable` (tolerating Windows Junctions that share a venv
across worktrees), `light_engine` imports successfully, and the imported
package file is also under the current workspace mapping.

If the bundled interpreter does not exist or cannot run, stop and report the error. Do not fall back to another Python installation.

## Verification

Before editing:

`.\\.python\\Scripts\\python.exe -m pytest -q`

After each coherent change, run relevant tests using the same bundled interpreter.

Before finishing, run:

`.\\.python\\Scripts\\python.exe -m pytest -q`

`.\\.python\\Scripts\\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800`

If firmware projects exist or are added:

`pio run -d firmware/stm32_rgbcct_node`

For ESP32-S3 on Windows, run the native firmware tests with the repository
MSVC wrapper so build and temporary files remain project-local:

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File firmware/esp32_ws2811_node/scripts/run_native_tests_msvc.ps1`

On a host that already provides `gcc` and `g++`, the equivalent command is
`pio test -d firmware/esp32_ws2811_node -e native`.

Then build every production image in Node order with a low-concurrency,
sequential PowerShell loop:

`1..13 | ForEach-Object { pio run -j 2 -d firmware/esp32_ws2811_node -e "esp32-s3-node-$_"; if ($LASTEXITCODE -ne 0) { throw "ESP32 Node $_ build failed with exit code $LASTEXITCODE" } }`

Before either ESP32 command, confirm `pio` is on A: and set
`PLATFORMIO_CORE_DIR`, `PLATFORMIO_PLATFORMS_DIR`,
`PLATFORMIO_PACKAGES_DIR`, `PLATFORMIO_CACHE_DIR`, `TEMP`, `TMP`, and `TMPDIR`
to the project-local `firmware/esp32_ws2811_node/.pio` paths documented in the
firmware README. Do not build the 13 environments concurrently; sequential
builds reduce memory and Windows paging pressure, while all project cache and
temporary files stay on A:.

Show commands and results. Never delete or weaken tests just to pass.


## Working method

For repository-wide changes, explore and produce a plan before implementation. Address root causes, keep changes incremental, and document assumptions. Ask only about blocker decisions that change wire format, hardware pinout, or safety behavior.

## Documentation precedence

When project documents conflict, use this order of authority:

1. `CLAUDE.md`: permanent project facts and invariants.
2. `docs/CLOSED_LOOP_SPEC.md`: target architecture and acceptance criteria.
3. `docs/IMPLEMENTATION_PLAN.md`: the currently approved work only.
4. Current source code and tests: implemented behavior and evidence.

The following documents describe the legacy v1 implementation and are not
the target architecture:

- `docs/history/legacy-prototype/protocol-v1.md`
- `docs/history/legacy-prototype/architecture.md`
- `docs/history/legacy-prototype/hardware-integration.md`
- `docs/history/legacy-prototype/configuration.md`

Do not implement RGBW, 11-byte serial v1, per-strip UDP fragmentation, or
WS2812B as the new target merely because they appear in legacy documents.
Preserve them only where explicitly required for migration or legacy mode.

