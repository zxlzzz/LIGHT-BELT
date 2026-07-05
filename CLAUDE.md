# LIGHT-BELT project instructions

## Mission

Build a reliable RK3588-hosted, video/music-driven lighting controller for:

- 6 analog 24V common-anode RGB+CCT zones
- 24V WS2811 digital RGB strips through ESP32-S3
- STM32 nodes over one addressed RS-485 bus

RK3588 is the only production brain. RK3568 is backup/testing only.

## Hardware truth

Analog COB is not RGBW. It is six-wire common-anode RGB+CCT:

`+24V / R / G / B / WW / CW`

Logical analog zones and node IDs:

1. ceiling_left
2. ceiling_right
3. wall_left
4. wall_right
5. front
6. rear

Current COB and WS2811 stock is 15 m each, but final installed lengths are unknown. Never hardcode lengths, pixel counts, power, IPs, serial paths, or final topology.

## Architectural invariants

- Analysis and effects are hardware-agnostic.
- Effects produce logical frames; physical mapping produces node frames.
- One logical frame owns one shared sequence and media timestamp.
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

UDP v2 sends one complete physical RGB frame per ESP32 node with version, node ID, sequence, lengths, payload, and CRC32.

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
Codex on Windows may remap the repository into a sandbox path such as
`C:\Users\CodexSandboxOffline\.codex\.sandbox\cwd\<sandbox-id>`, so do not
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

`pio run -d firmware/esp32_ws2811_node`

Show commands and results. Never delete or weaken tests just to pass.


## Working method

For repository-wide changes, explore and produce a plan before implementation. Address root causes, keep changes incremental, and document assumptions. Ask only about blocker decisions that change wire format, hardware pinout, or safety behavior.

## Documentation precedence

When project documents conflict, use this order of authority:

1. CLAUDE.md 鈥?permanent project facts and invariants
2. docs/CLOSED_LOOP_SPEC.md 鈥?target architecture and acceptance criteria
3. Current source code and tests 鈥?current implementation truth
4. Other files under docs/ 鈥?legacy/current-state reference only

The following documents describe the legacy v1 implementation and are not
the target architecture:

- docs/protocol.md
- docs/architecture.md
- docs/hardware-integration.md
- docs/configuration.md

Do not implement RGBW, 11-byte serial v1, per-strip UDP fragmentation, or
WS2812B as the new target merely because they appear in legacy documents.
Preserve them only where explicitly required for migration or legacy mode.

