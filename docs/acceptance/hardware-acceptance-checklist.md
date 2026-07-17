# Phase 31 Hardware Acceptance Checklist

Software campaign success is not hardware acceptance. Perform and retain this
checklist after the one-ESP32-per-strip software gates pass. Until then, all
physical claims remain **NOT HARDWARE VERIFIED**.

## Acceptance scope

Select exactly one scope and do not generalize its result:

- **Current field subset:** nodes `1`, `2`, `4`, `5`, `6`, `7`, `8`, `9`, and
  `10`, covering nine strips.
- **Complete target:** nodes `1` through `13`, covering all 13 strips.

A current-field result does not accept nodes `3`, `11`, `12`, or `13`.
Both scopes above are digital WS2811 scopes. Their site profiles are UDP-only
and do not control or accept the independent `zone_32` RGB+CCT COB. Record COB
acceptance separately with an explicitly configured, enabled RS-485 transport.

## Test setup record

Record before power-up:

- PC or RK platform, software commit, dirty-tree status, exact commands, and
  selected profile/show hashes;
- router/network, RS-485 port, UDP port, and production versus isolated test
  mode;
- each ESP32 Node, physical-board label, MAC, firmware commit/build, logical
  strip, groups, direction, output ID, GPIO, and site IP;
- proof that every selected digital node uses `output_id: 1`, GPIO4, UDP v3,
  and a unique endpoint;
- logical strip IDs, physical lengths, installed directions, configured
  `gap_after_pixels`, measured gaps, and pixels per metre;
- power supplies, protection, cable gauge, injection points, common-ground
  arrangement, brightness limit, and measured idle/loaded voltages;
- show YAML, layout/profile YAML, golden manifest, and fixed-fixture hashes.

The authoritative complete mapping is:

| Node | Strip | Groups | Site IP |
|---:|---|---:|---|
| 1 | `strip_11` | 10 | `192.168.31.201` |
| 2 | `strip_41` | 10 | `192.168.31.202` |
| 3 | `strip_44` | 20 | `192.168.31.203` |
| 4 | `strip_12` | 40 | `192.168.31.204` |
| 5 | `strip_22` | 40 | `192.168.31.205` |
| 6 | `strip_21` | 10 | `192.168.31.206` |
| 7 | `strip_31` | 10 | `192.168.31.207` |
| 8 | `strip_42` | 20 | `192.168.31.208` |
| 9 | `strip_91` | 20 | `192.168.31.209` |
| 10 | `strip_92` | 20 | `192.168.31.210` |
| 11 | `strip_43` | 20 | `192.168.31.211` |
| 12 | `strip_45` | 20 | `192.168.31.212` |
| 13 | `strip_93` | 20 | `192.168.31.213` |

## Exact profile/show commands

Run all commands from the repository root. For the current nine-node field
subset, validate, inspect, and then run this exact pair:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-installed-one-esp-per-strip.yaml `
  validate-show --show config/shows/ws2811-stage3-installed-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-installed-one-esp-per-strip.yaml `
  inspect-topology --show config/shows/ws2811-stage3-installed-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-installed-one-esp-per-strip.yaml run `
  --show config/shows/ws2811-stage3-installed-300s.yaml
```

For the complete thirteen-node digital target, validate, inspect, and then run
this exact pair only after every controller is physically present:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-site-local.yaml `
  validate-show --show config/shows/ws2811-stage3-full-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-site-local.yaml `
  inspect-topology --show config/shows/ws2811-stage3-full-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-site-local.yaml run `
  --show config/shows/ws2811-stage3-full-300s.yaml
```

Do not substitute one show for the other. A successful digital run is not
evidence for `zone_32`, because both commands use UDP-only site profiles.

## Pre-cutover gates

1. Archive successful `validate-show` and `inspect-topology` output for the
   exact deployment profile and show.
2. Confirm every selected logical strip resolves exactly once and no absent
   node is represented by a placeholder output in the field profile.
3. Confirm each controller label, MAC, Node, strip, groups, output 1 / GPIO4,
   firmware build, and IP against the setup record.
4. Commission each selected node alone with its own strip: all black, low-level
   red, green, blue, dynamic output, timeout to black, and recovery without a
   stale frame.
5. Record failures. Do not convert a failed isolated node into a skipped item.

## Atomic cutover record

Record start/end time and responsible people for all steps:

1. Disable Host physical output and power down the lighting system.
2. Confirm no controller retains the old five-node multi-output firmware.
3. Connect one strip to each selected ESP32 through its GPIO4 data path.
4. Select `config/profiles/ws2811-installed-one-esp-per-strip.yaml` with
   `config/shows/ws2811-stage3-installed-300s.yaml` for the current field
   subset, or `config/profiles/cabin-lighting-v3-site-local.yaml` with
   `config/shows/ws2811-stage3-full-300s.yaml` for the complete onsite digital
   target. Never use the TEST-NET
   `config/profiles/cabin-lighting-v3-production.yaml` template for a live
   deployment.
5. Power up and begin with a complete black frame.
6. On failure, stop output and roll back profile, firmware set, and wiring
   together. Record the rollback; do not continue with a mixed topology.

## Required physical tests

1. **Black and isolation:** with all selected nodes connected, hold all black
   and verify no persistent white, red, pink, or other lit segment. Address one
   node at a time and verify no other strip changes.
2. **Primary colors and group count:** display red, green, blue, and black on
   every strip; verify color order, exact controllable length, first/last group,
   and installed direction.
3. **Concurrent nodes:** run distinct colors/effects on at least three nodes,
   including nodes 1/2/8 when present, and check for cross-erasing or data-path
   interference.
4. **Shared logical frame:** capture or instrument every selected UDP endpoint
   for a frame and verify one UDP v3 datagram per node, one output descriptor,
   and the same Engine-owned sequence/media timestamp. If a separately enabled
   RS-485/COB scope is also being accepted, verify that it shares the same
   logical identity in that separate record.
5. **Cross-node synchronization:** place at least two strips side by side and
   measure maximum visible or instrumented skew and sequence drift. Phase 31
   schedules every node against one shared Host `apply_at_us` 20 ms ahead and
   starts each wire transaction early by its encoded strip duration. Capture
   the completed latch edge, not packet arrival, before accepting strict
   simultaneity.
6. **Single-seam motion:** run one narrow head from the final screen segment
   into the first wall segment; verify no duplicate head, reset, reversal, or
   unconfigured dark frame.
7. **Gap calibration:** compare `gap_after_pixels=0` with the authored value and
   record which better matches the real screen-to-wall distance.
8. **Reverse segment:** repeat continuity tests with a physically reversed
   strip and verify mapping direction, not rewired Show targets, controls it.
9. **Concurrent effects:** verify at least three logical targets visibly run
   different effects without cross-erasing.
10. **Fade boundaries:** observe and record cue start, midpoint, full level,
    and end.
11. **Music cases:** test rhythmic music, piano, string crescendo, sustained
    low-frequency ambience, and silence/free-run behavior.
12. **Network interruption:** interrupt UDP and verify safe timeout to black;
    restore it and verify recovery without stale queued frames. Then restart
    the Host show without resetting any ESP32 and verify the new
    `KEY_FRAME`/sequence 1 session is accepted and normal sequence progression
    resumes.
13. **Power and thermal:** measure supply voltage/current at representative
    low and high loads; record resets, thermal rise, cable/connector heating,
    and visible color shift. Do not infer this result from an isolated strip.
14. **Five-minute run:** run `ws2811-stage3-installed-300s.yaml` for the selected
    nine-node scope or `ws2811-stage3-full-300s.yaml` for the selected
    thirteen-node scope. Record dropped frames, resets, sequence gaps,
    thermal/power issues, and visual defects.
15. **Final black/safe state:** verify normal stop and fault behavior across all
    selected digital nodes. Verify `zone_32` only in its separate RS-485
    acceptance scope; an UDP-only site-profile run cannot accept it.

## Acceptance statement

Only after every applicable item is supported by retained real-hardware
evidence may the project state:

`HARDWARE VERIFIED FOR THE RECORDED TEST CONFIGURATION AND NODE SET`

The statement does not generalize to a different node set, layout, power
system, network, firmware build, mapping, direction/gap calibration, software
commit, or show. Empty rows and planned IP addresses are not hardware evidence.
