# Cabin Lighting V3 Phase 31 Software Acceptance

Date: 2026-07-16

Status: **ONE-ESP32-PER-STRIP AND SCHEDULED-PRESENTATION SOFTWARE ACCEPTED;
NOT HARDWARE VERIFIED**

This report covers the Phase 31 digital topology migration and the implemented
scheduled-presentation software contract. It does not accept physical wiring,
power, endpoint reachability, visible output, the independent RGB+CCT COB, or
measured cross-node latch timing.

## Accepted topology

- Complete digital target: 13 ESP32-S3 nodes and 13 WS2811 strips, 260 groups.
- Current field subset: nodes `1`, `2`, `4`, `5`, `6`, `7`, `8`, `9`, and
  `10`, with no placeholder outputs for absent nodes.
- Every production node has one UDP v3 output: `output_id: 1` on GPIO4.
- Complete site endpoints are `192.168.31.201` through `.213`; the generic
  production-shape profile retains explicit TEST-NET placeholders.
- Host validation rejects empty, duplicate, or unknown output backends,
  duplicate UDP endpoints, invalid hosts/ports, missing UDP v3 production
  transport, and a missing or nonconforming topology policy.
- UDP v3 retains its general one-to-three-output wire contract; production
  single-output topology is a configuration rule rather than a codec change.

## Show and runtime evidence

- `ws2811-stage3-installed-300s.yaml` covers the exact current nine-node field
  subset.
- `ws2811-stage3-full-300s.yaml` covers all 13 digital nodes.
- Both shows contain five fixed 60-second sections and remain independent of
  video, audio, beat, node ID, output ID, GPIO, host, and port.
- The complete-show integration test decodes 13 UDP v3 datagrams per sampled
  frame and checks shared sequence/media timestamp, output 1, GPIO4, endpoint,
  and configured group count.
- A newly opened Host UDP v3 output marks only sequence 1 as `KEY_FRAME`.
  Before sending it, Host encodes every target node successfully, then sends
  three complete rounds 2 ms apart. Each node's packet is byte-identical in
  all three rounds, and all nodes/rounds retain the same apply and media time.
  Firmware treats repeated sequence-1 KEY packets with the same apply/media
  identity idempotently without creating extra sessions. Successful KEY
  preparation admits the generation; a later timed-output failure restores the
  previous frame or black while the next complete scheduled frame can recover.
  Generation zero, ordinary duplicate, and stale non-KEY sequences are
  rejected.
- Unknown output names cannot produce an empty output dictionary, and a
  production send exception stops `run` with a nonzero result instead of
  printing a false successful completion.
- Production site profiles use the Host monotonic clock for broadcast clock
  beacons and one common `apply_at_us` 20 ms ahead for every node packet in a
  logical frame. `SCHEDULED_APPLY` and nonzero apply time are inseparable.
- Firmware estimates local-minus-Host time from the minimum offset in a bounded
  beacon window, rejects scheduled frames while that clock is not ready, and
  never falls back to immediate application in a production node image.
- The fixed GPIO4 backend prepares without touching GPIO and subtracts the
  complete 5 MHz six-bit encoded wire time from the common latch deadline.
  With symmetric 313-byte low guards, 10 groups are 806 bytes / 1290 us, 20
  groups are 986 bytes / 1578 us, and 40 groups are 1346 bytes / 2154 us.
- Explicit legacy Node 2 diagnostic images retain immediate application and
  are not scheduled-synchronization evidence.

The later shared SPI6 production promotion passed native tests and Node 2 /
Node 4 firmware builds, but no production UDP image containing that promotion
has been flashed and observed. Its UDP playback, safe recovery, and cross-node
latch behavior remain **NOT HARDWARE VERIFIED**.
- The output task evaluates safe timeout at the start of every loop, including
  while scheduled traffic remains queued. A scheduled SPI failure is not
  blindly transmitted a second time after its validated start deadline; it
  fails closed and performs local recovery.

## Commands and results

| Command | Return code and result |
|---|---|
| Bundled-Python identity assertion from `AGENTS.md` | 0, `PROJECT_PYTHON_OK` |
| `.\.python\Scripts\python.exe -m pytest -q` | 0, `701 passed in 141.36s` |
| Scheduled/topology focused Python regression | 0, `165 passed in 54.91s` |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File firmware\esp32_ws2811_node\scripts\run_native_tests_msvc.ps1` | 0, `39 Tests 0 Failures`, 10.9 s in the final run |
| One combined low-concurrency Node 1-13 build command | 124 at the external 480 s tool limit; this was a command timeout, not a compiler failure |
| Sequential low-concurrency production builds, Nodes 1-7 | 0, all seven environments succeeded |
| Sequential low-concurrency production builds, Nodes 8-13 | 0, all six environments succeeded |
| Final single-process build listing Nodes 1-13 together | 0, all 13 environments succeeded in 214.799 s (218.7 s wall time) |
| `pio run -j 2 -d firmware\esp32_ws2811_node -e esp32-s3-node-2-fixed-gpio4-diagnostic` | 0, diagnostic environment succeeded |
| `.\.python\Scripts\python.exe -m light_engine --config config\profiles\ws2811-installed-one-esp-per-strip.yaml validate-show --show config\shows\ws2811-stage3-installed-300s.yaml` | 0, 5 cues / 300 s |
| `.\.python\Scripts\python.exe -m light_engine --config config\profiles\cabin-lighting-v3-site-local.yaml validate-show --show config\shows\ws2811-stage3-full-300s.yaml` | 0, 5 cues / 300 s |
| `.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800` | 0, 229.1 FPS; P50 4.10 ms; P95 6.42 ms; P99 7.65 ms; 0 drops |

Every final production node build produced a 723,408-byte `firmware.bin`.
PlatformIO reported 52,160 bytes of RAM and 723,037 bytes of flash used. ELF
sizes range from 13,046,516 to 13,047,288 bytes because node-specific debug
metadata differs; the linked firmware size is identical. The earlier
fixed-GPIO4 immediate diagnostic build also succeeded, using 52,168 bytes of
RAM and 722,057 bytes of flash before the final production-only session-gate
refinement.

The first direct PlatformIO attempt returned 1 before compilation because the
external `pio` launcher tried to create the operator profile's default
`.platformio` directory on C. The
successful command explicitly set `PLATFORMIO_CORE_DIR`, platform/package/cache
directories, telemetry, and all temporary directories to the A-drive firmware
project. No project cache or build artifact was intentionally placed on C.

An attempted multi-process build was discarded after PlatformIO processes
contended over the shared project build directory. Split single-process builds
then proved each environment, and the final retained-artifact build used one
PIO process listing all 13 environments together; it returned 0 with all 13
successful. The final filesystem check found no PIO/Python build processes and
confirmed that the operator profile's default `.platformio` directory,
`C:\tmp\light-belt`, and `C:\tmp\platformio` do not exist.

## Explicit limitations

- No ESP32 was flashed during this acceptance run and the strips were not
  powered. All physical behavior is **NOT HARDWARE VERIFIED**.
- UDP `sendto` success proves only Host socket submission, not receipt or
  visible refresh. Commissioning must inspect node statistics and the lights.
- Host-monotonic beacons, a common 20 ms apply deadline, bounded minimum-offset
  firmware clocks, prepare/transmit separation, and length compensation are
  implemented in software. Their actual network delay, GPIO start, WS2811
  latch completion, and cross-node skew are **NOT HARDWARE VERIFIED**. Powered
  nodes and a retained logic-analyzer capture are required before claiming
  strict synchronization passed.
- The two site profiles are UDP-only. They do not control or accept `zone_32`;
  COB acceptance requires a separately configured RS-485 scope.
- Nodes 3, 11, 12, and 13 have software configurations and build artifacts but
  are absent from the current nine-node field set and have no physical
  acceptance evidence.

The superseded five-controller Phase 29 report is retained at
`docs/history/acceptance/cabin-lighting-v3-phase29-software-acceptance.md` as
historical evidence only.
