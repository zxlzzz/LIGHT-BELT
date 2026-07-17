# WS2811 Emergency Path Handoff

This is the short handoff for a second engineer. The evidence ledger remains
the source of detailed history:

- `docs/current/ws2811-show-stability-investigation.md`

## Current Scope

- Fixture: Node 2, COM7, IP `192.168.31.202`, MAC
  `E0:72:A1:D3:30:3C`, GPIO4, replacement SN74LVC1T45, strip 41.
- Frame: one output, RGB order, exactly 10 WS2811 groups.
- Payload group 0 is commanded black. Effects target groups 1-9, which are
  physical groups 2-10.
- Status: promising degraded emergency path, **NOT HARDWARE VERIFIED**.
- The DI-side first physical group remains uncontrolled and is scored
  separately.
- Rare physical wrong-position/wrong-color events have occurred even when all
  transport, state-graph, encoder, and SPI counters were exact and error-free.
- Node 8, COM13, IP `192.168.31.208`, GPIO4, strip 42, and exactly 20 groups
  completed the 60-second Blue20 change-only gate with exact software counters
  and only extremely rare visible jumps. This is promising fixture evidence,
  not a zero-event hardware pass.
- The earlier powered two-node electrical-isolation gate failed while the real
  SN74 VCCB condition was wrong or unverified. Preserve that observation, but
  do not use it to reject the corrected two-node topology. Both translators
  must first be confirmed at `VCCB=5.0 V` and retested with the same SPI4 image.

Do not generalize this evidence to another strip/ESP32, multiple active nodes,
30 FPS, Scheduled presentation, or free APP control.

### Superseding VCCB correction

On 2026-07-17 the operator corrected the SN74LVC1T45 B-side supply to 5 V and
reported that strip 41 became markedly more stable. The wiring text below was
the intended topology, but earlier testing did not prove the physical VCCB pin
actually met it. Earlier SN74, SPI4, and powered-two-node failures are therefore
confounded fixture history and require repetition on the corrected baseline.

The next bounded gate uses no new color or effect data. Both boards use the
current guarded-SPI4 emergency environments and the existing Blue20 staged
Show:

```text
Node 2: COM7, 192.168.31.202, GPIO4, 10 groups
Node 8: COM13, 192.168.31.208, GPIO4, 20 groups
SPI4: 3.2 MHz, 0=1000, 1=1100, RGB, 500 us pre/post low
Show: ws2811-emergency-two-node-blue-staged-110s.yaml
```

The preserved C477 SPI6 image is historical only and must not be used for this
gate: its 200 ns T0H is outside the supplied V2.1 timing window. This Immediate
gate checks Node 2 alone, Node 8 alone, and both together. It does not establish
strict scheduled synchronization.

### Latest physical-connection A/B

The strongest current observation supersedes blind software timing changes.
An unrestricted 15 FPS pure-blue breath produced about 50 whole-strip red
events. A frozen 600-packet replay removed live effect rendering while keeping
the exact same pure-blue payload sequence. Its semantic SHA-256 is
`A07C59FD0AA9AD18E8BE1FD421CAFFBAF5E46947D8B1956E2ED016BAB7431436`.
Two frozen replays still produced 53-60 events.

The operator then unplugged and reconnected all three strip wires without any
software or timing change. The next replay produced only three events, two red
and one green, and the following replay produced none. Treat this as strong
evidence for the physical three-wire connection, ground reference, B-to-DI
path, or strip connector. It does not isolate one wire because all three moved
together. Do not alter the fixture while confirming it: require two more
consecutive zero-event frozen replays, then rerun live 15 FPS breath. Keep the
V2.1-compliant RGB/SPI4/500 us firmware; do not restore SPI6.

### Latest per-strip pull-down observation

On 2026-07-17 the operator added a 10 kohm pull-down from DI to GND at the
strip-side input of each strip. With both pull-downs present, the Node 8-only
15 FPS pure-blue breath made strip 42 breathe normally. Strip 41 was also lit:
its DI-side physical group 1 was black and physical groups 2-10 were white.

Do not describe this as proven Node 8-to-strip-41 coupling. The Node 8-only
profile sends only to `.208` and commands all 20 strip-42 groups to uniform
pure blue; it sends nothing to Node 2 or strip 41 and contains no white or
partial-strip payload. Strip 41 was not first deliberately cleared and paired
with a Node 2 counter baseline, so an older latched strip-41 state and a state
induced during Node 8 activity are both still open.

A later observation makes a pure old-latch explanation insufficient. A Node 2
black command could clear all of strip 41, but while the Node 8-only breath was
active, repeated Node 2 black commands cleared it only temporarily. Strip 41
physical group 2 and later groups then relit red and could change color without
obvious flashing, while strip 42 continued breathing stably. This still does
not prove electrical coupling: no immediately paired Node 2 `received` and
`spi_ok` deltas were recorded, so an unintended software sender and a physical
response correlated with Node 8 activity remain open. Capture those deltas
before assigning the cause.

The next captured isolation window supplied that missing Node 2 evidence for
only part of the Show. COM7 uptime advanced continuously by 30,024 ms while
`received/queued/attempts/refresh_ok` stayed at `45/45/45/45`,
`spi_ok/encoded_hash_checks/uniform_checks` stayed at `47/47/47`, and
`safe_frames/timeout_black/last_rx/last_commit` stayed at `1/0/45/45`.
Every listed Node 2 delta was zero. During the same window COM13 increased its
receive, queue, attempt, refresh, SPI, encoded-hash, and uniform counters by
385, with no reported errors. The log stopped at 385 of the expected 600
Node 8 frames and before SAFE (`safe_frames=0`), so do not mark the complete
40-second Show accepted. A strip-41 event inside this window excludes Host UDP
delivery to Node 2 and normal Node 2 firmware SPI output; it still permits an
electrical response correlated with Node 8, a local strip-41 electrical fault,
or a previously misdecoded black transaction.

Final stats subsequently completed the run. Node 8 ended at
`received/queued/attempts/refresh_ok=600/600/600/600`,
`spi_ok/encoded_hash_checks/uniform_checks=602/602/602`, and
`safe_frames=1`; all reported errors were zero. Node 2 stayed fixed at
`45/45/45/45`, `47/47/47`, and `safe_frames=1` respectively through COM7
`uptime_ms=365126`, also with zero reported errors. This passes the complete
Node 8-only software contract and proves zero Node 2 control-path activity for
the run. A strip-41 visual event in that interval is not direct software
control through Node 2; continue with the remaining electrical and physical
hypotheses.

A decisive same-run wiring A/B then localized the trigger. With the Node 8
breath active, separating the two green SN74 `B -> DI` jumper wires prevented
any effect on strip 41. Moving those same wires close together made strip 41
light immediately or relight, while Node 2 counters remained unchanged. Host
misrouting and normal Node 2 firmware output are therefore excluded for this
event; near-field coupling between the two data branches is now the located
trigger. The exact coupling mechanism and available electrical margin are not
yet measured.

For the temporary onsite fix, keep the two data branches separated, do not run
them parallel or bundle them, keep each `B -> DI` wire short and close to its
own ground return, and cross unavoidable data paths at approximately 90
degrees. Keep each existing 10 kohm strip-input `DI -> GND` pull-down fitted.

With this separated routing held fixed and each data branch kept with its own
ground return, the Node 2-only 15 FPS pure-blue breath passed. All ten strip-41
groups breathed as expected and strip 42 stayed black for the entire run.
Combined with the Node 8-only isolated result, both single-node directions now
pass on this fixture. Run the staged two-node breath next: Node 2 alone, Node 8
alone, then both together, without moving either data or ground-return wire.

The staged two-node breath then failed visually. During the 5-35 second Node
8-only cue, strip 41 physical group 1 flashed wrong colors. During the 40-70
second simultaneous cue, both strips had minor wrong-color events, with strip
41 worse. Both nodes increased receive, queue, attempt, refresh, and SPI
counters by exactly 1125, accepted one SAFE, and reported zero errors. The
unrestricted firmware physically sent every black frame to the inactive node,
so Node 2 still generated repeated T0 wire activity throughout the nominally
Node 8-only cue. Do not equate an inactive black payload with an electrically
quiet data branch.

The next diagnostic uses unrestricted exact-content deduplication, independent
of all emergency whitelist and transition restrictions. Macro
`LIGHT_BELT_CONTENT_DEDUPE_AB` keeps guarded SPI4 and forces KEY and SAFE to
write physically, while an unchanged ordinary payload commits without another
SPI transaction. The then-current **NOT HARDWARE VERIFIED** binaries for that
historical step were:

| Node | Environment | Size | SHA-256 |
|---|---|---:|---|
| 2 | `esp32-s3-node-2-fixed-gpio4-content-dedupe-ab` | 727456 | `469631595379B5436CB1D1212419B7F6D6B45E2A77C60A602133896DCADBAFD0` |
| 8 | `esp32-s3-node-8-fixed-gpio4-content-dedupe-ab` | 727456 | `C3E2FD215B6F544E0CB089717860EFEBE19E538CBF9ACAF90F6E1B89828007F8` |

For the same 1125-frame staged Show, expect Node 2 physical writes/skips of
313/812 and Node 8 writes/skips of 624/501. With two startup black writes,
final `spi_ok` should be 315 and 626. Flash both matching images and rerun with
the current separated routing untouched. If the simultaneous phase still
jumps color, test a 5 ms inter-node physical-transaction offset as the next
single-variable A/B.

Both images have now been flashed successfully. Node 2 used COM7 and MAC
`E0:72:A1:D3:30:3C`; Node 8 used COM13 and MAC `28:84:85:8A:36:B0`. Esptool
reported hash verification for every written partition on both boards, and
the post-flash `firmware.bin` size and SHA-256 values remain exactly those in
the table above. Run the unchanged 75-second staged breath next from fresh
counters. Expected finals are Node 2 `spi_ok=315`,
`identical_skipped=812`, and Node 8 `spi_ok=626`,
`identical_skipped=501`, with 1125 accepted frames and one SAFE on each.

The content-dedupe hardware run made the 5-35 second Node 8-only phase stable,
but both strips still jumped color during the 40-70 second simultaneous phase.
The second run matched the predicted deltas exactly: Node 2 added 313 SPI
writes and 812 skips; Node 8 added 624 SPI writes and 501 skips, with reported
errors and mismatches at zero. Dedupe has therefore removed repeated black T0
activity as the inactive-branch trigger. It has not solved the case where both
branches change and physically transmit.

The next Node 8-only firmware variable adds a 5 ms delay to each non-skipped
Immediate Host physical write. It leaves skips, Node 2, Scheduled frames,
startup, watchdog, recovery, and rollback untouched; KEY and SAFE are delayed
because they force Host writes. Use `physical_offset_waits` and
`physical_offset_cancelled` to verify the runtime path. The final **NOT
HARDWARE VERIFIED** image is preserved in
`firmware/esp32_ws2811_node/baselines/node8-content-dedupe-offset5ms-a1a81d6c/`:

| Environment | Size | SHA-256 |
|---|---:|---|
| `esp32-s3-node-8-fixed-gpio4-content-dedupe-offset5ms-ab` | 727952 | `A1A81D6CBA0FC958FD5C355F0079952F06393BE3AA13862509B88BF5C5263D2C` |

The COM13 upload succeeded with the expected Node 8 MAC
`28:84:85:8A:36:B0`, and esptool verified the written hashes. PlatformIO
rebuilt during upload, so keep the two 727952-byte identities distinct:

- pre-upload: `baselines/node8-content-dedupe-offset5ms-a1a81d6c/firmware.bin`, SHA-256 `A1A81D6CBA0FC958FD5C355F0079952F06393BE3AA13862509B88BF5C5263D2C`;
- actual post-upload: `baselines/node8-content-dedupe-offset5ms-flashed-3b46d919/firmware.bin`, SHA-256 `3B46D919A1DB836707B1B08DF3B9AB74ADB0A5F7563F7219028A3FF0FC886971`.

Both retain the declared content-dedupe, offset-counter, and guarded-SPI4
identities. Post-upload `3B46D919...6971` was the flashed Node 8 identity for
that 5 ms trial; A1A81 remains the pre-upload history only.

Fresh 75-second staged expectations are Node 2 `received=1125`,
`spi_ok=315`, `identical_skipped=812`; Node 8 `received=1125`,
`spi_ok=626`, `identical_skipped=501`, `physical_offset_waits=624`, and
`physical_offset_cancelled=0`. Both must commit one SAFE with no rejects,
errors, or mismatches.

The next gate must first send the directed Node 2 black sentinel and visually
confirm all ten strip-41 groups black. Record both nodes' counters, then change
nothing and rerun the exact same Node 8-only 15 FPS breath. Record both final
counters. Node 2 must have zero receive, queue, attempt, refresh, and SPI delta
during the Node 8 run. A strip-41 change with zero Node 2 delta supports an
electrical response correlated with Node 8 activity; strip 41 remaining black
supports the old-latch explanation. Node 2 counter growth invalidates the
sender-isolation gate.

The later Node 8 trial increased only that Immediate offset to 30 ms. COM13
reported the expected Node 8 MAC and esptool verified every partition. The
current flashed/preserved image is 727952 bytes, SHA-256
`C5BAC80C948578AC3EA6D0873D004795B0C42B97C0221BA05F1EB56D8126A44B`.
The latest visual isolation observation reported that strip 41 can still flash
during the Node 2-only breath phase. This means simultaneous Node 8 activity is
not necessary for every strip-41 event and the Node 8 offset cannot be a full
repair. It supports a residual single-path or regenerated-signal problem but
does not yet distinguish Node 2 output/interface/contact/ground/DI from a strip
receiver defect.

`config/shows/ws2811-ab-two-node-all-effects-171s.yaml` is the next exploratory
sweep. It covers all 17 registered effects on both strips, uses one-second
black separators, and puts deterministic pure-color effects before generated
media and full-color effects. It is not an acceptance gate or evidence for
unrestricted APP color control.

`config/shows/ws2811-ab-two-node-virtual-path-color-comet-32s.yaml` is the
shorter logical-path demonstration. It treats strip 41 followed by strip 42 as
one 30-group path, runs one color-changing comet forward for 14 seconds, then
reverses the whole path for 14 seconds. The Host-focused test proves one path
render and both logical directions. The onsite Node 8 30 ms offset means the
physical cross-node seam is intentionally not a strict synchronization test.

The 2026-07-17 asset freeze read both onsite application regions at flash
offset `0x10000` without erasing or writing. COM7 reported Node 2 MAC
`E0:72:A1:D3:30:3C`; its 727456-byte readback SHA-256 is
`469631595379B5436CB1D1212419B7F6D6B45E2A77C60A602133896DCADBAFD0`.
COM13 reported Node 8 MAC `28:84:85:8A:36:B0`; its 727952-byte readback SHA-256
is `C5BAC80C948578AC3EA6D0873D004795B0C42B97C0221BA05F1EB56D8126A44B`.
Both exactly match their recorded field identities. Node 2 is now retained in
`baselines/node2-content-dedupe-field-readback-46963159/`; Node 8 matches the
existing 30 ms flashed baseline. The full Host/source/docs/binary snapshot is
`artifacts/baselines/ws2811-two-node-good-effects-20260717/`.

## Reported Wiring

This wiring is operator-reported and has not been independently probed:

```text
24 V V+ -> strip 41 24V+
24 V V- -> strip 41 GND and XL4015 IN-
XL4015 5.0 V OUT+ -> ESP32 5V and SN74LVC1T45 VCCB
XL4015 OUT- -> ESP32 GND and SN74LVC1T45 GND
ESP32 3V3 -> SN74LVC1T45 VCCA and DIR
ESP32 GPIO4 -> SN74LVC1T45 A
SN74LVC1T45 B -> strip 41 DI
```

The XL4015 is non-isolated, so the reported grounds are common. Current cable
colors are red `24V+`, white `GND`, and green `DI`. The installed data path has
no 220-330 ohm source resistor because none was available. The level shifter
module was replaced during diagnosis. One ESP32 now controls one strip.

## Why The Current Path Is More Stable

The improvement is a containment strategy, not a discovered safe color range:

1. Host uses Immediate UDP at 5 logical FPS.
2. Dynamic states change at 2.5 FPS and are delivered twice.
3. ESP commits duplicate logical frames but suppresses another SPI write when
   the complete post-transform pixel payload is identical.
4. Colors use exact sparse raw bytes such as `0x20`, `0x10`, and `0x08`.
5. The Host transform is identity: brightness `1.0`, gamma `1.0`.
6. Effects are discrete. There is no interpolation, trail, fractional
   brightness, or sinusoidal scaling.
7. Firmware admits exact complete payloads and directed transitions, with a
   150 ms minimum interval between different physical payloads.
8. The first KEY frame of a Host session always writes physically to rebuild
   the command-side cache.

`spi_ok` proves only that the backend reported a completed transaction. It
does not prove that the real strip latched the requested pixels.

## Reproduction Artifacts

Worktree:

```text
<repository>\.agent-worktrees\ws2811-show-stability
branch: codex/one-esp-per-strip
```

Historical source environment name (the current source under this name no
longer reproduces the baseline binary):

```text
esp32-s3-node-2-emergency-change-only-ab
```

Recovered Node 2 Gate 1m SPI6 baseline identity:

```text
size: 731328 bytes
SHA256: C47760A6B33A36B1CB4D67AF3A380742B93C7701036B02B45A501FA6881AE420
preserved path: firmware/esp32_ws2811_node/baselines/
                node2-gate1m-spi6-c477/firmware.bin
```

This exact binary was recovered from the operator's Downloads directory and
copied byte-for-byte to drive A on 2026-07-17. Its embedded identity is
`spi6_dma_fixed_gpio4`, Immediate, emergency change-only, exact 10 groups, and
group 0 black. It is not any cadence/static autonomous diagnostic and is not
the guarded-SPI4 candidate. Do not rebuild the similarly named environment
when the intent is to restore this baseline; verify and flash the preserved
binary directly.

Node 8 previously carried this SPI6 exact-20 candidate for its first
60-second onsite run:

```text
Node8 flashed SPI6 exact-20 identity
  size: 731408 bytes
  SHA256: 86AF165BBC4F29F09AEC21A05A03FB5805B2EE2C9D89511AFFA289999B944329
```

The build directories contain newly rebuilt guarded-SPI4 candidates. These
exact hashes had not yet been flashed when recorded; the older Node 8 image on
COM13 has a different hash and must be replaced for the common gate:

```text
Node2 guarded-SPI4 emergency candidate
  env: esp32-s3-node-2-emergency-change-only-ab
  path: firmware/esp32_ws2811_node/.pio/build/
        esp32-s3-node-2-emergency-change-only-ab/firmware.bin
  size: 729168 bytes
  SHA256: F01B83C8BEF564578E36C49E50C6BC3324ED17A1BD251853729C35B7F318B90A

Node8 guarded-SPI4 emergency candidate
  env: esp32-s3-node-8-emergency-change-only-ab
  path: firmware/esp32_ws2811_node/.pio/build/
        esp32-s3-node-8-emergency-change-only-ab/firmware.bin
  size: 729168 bytes
  SHA256: C99629D842EC523FB3C6001BF31682AB94625EBF173C2D25316F93D32D50B841
```

Node 2 was overwritten by standalone cadence/static comparison images during
the investigation. On 2026-07-17 the operator reported flashing the preserved
C477 binary back to COM7. The setup-time identity banner was not observed
because USB CDC re-enumeration completed after the one-shot print; the flash
hash/verify result and the Gate 1m counters remain the required evidence.
Node 8 now carries the guarded-SPI4 binary above. The earlier SPI6 60-second
run's final counters were
`received=queued=attempts=refresh_ok=300`, `identical_skipped=198`,
`spi_ok=104`, and `safe_frames=1`, with all reject, gap, timeout, error, hash,
and uniform mismatch counters zero.

Current source images now keep the immediate setup banner but also replay the
complete identity once when USB CDC first reports a connected monitor. If no
connection is reported, they replay once immediately before the first 5-second
stats line. This is non-blocking and does not touch the LED backend. The
preserved C477 binary predates this logging repair and must not be replaced
merely to obtain the banner.

Repeated C477 Gate 1m runs are now failing on both strip 41 and the original
5 m strip on the same Node 2 signal chain. Blue `00 00 20` has appeared as
green `00 20 00`, while one orange `20 08 00` point has split into adjacent
blue `00 00 20` and red `08 00 00` groups. A later run failed with a different
wrong-color pattern. Treat this as an unstable bit/byte frame boundary after
the verified Host payload, not as a safe-palette issue or a strip-41-only
fault. C477 remains the preserved best baseline but has not passed repeated
single-strip Gate 1m.

The latest recorded failure followed an ESP RST and used clean runtime state;
the wrong-color pattern differed from the previous run. A later strip-power
cycle did not reset Node 2: the next trace began at 360 seconds uptime because
USB still supplied the ESP. Do not call that a full cold start.

The next gate is `full-cold / no-USB-during-show / original-5m / C477`:
stop Host output, unplug USB, remove 24 V, confirm all board lights are off and
`.202` is unreachable, wait at least 30 seconds, then restore 24 V only. Run
the same Gate 1m over Wi-Fi after `.202` returns. Attach USB only after the
Show to read stats.

Host profile and fixed Shows:

```text
config/profiles/ws2811-emergency-node2-strip41.yaml
config/shows/ws2811-emergency-black-sentinel-3s.yaml
config/shows/ws2811-emergency-node2-strip41-110s.yaml
config/shows/ws2811-emergency-node2-strip41-gate1m-120s.yaml
config/profiles/ws2811-emergency-node8-strip42.yaml
config/shows/ws2811-emergency-node8-strip42-blue-60s.yaml
config/profiles/ws2811-emergency-two-node-41-42.yaml
config/shows/ws2811-emergency-two-node-blue-staged-110s.yaml
```

Primary implementation and tests:

```text
firmware/esp32_ws2811_node/platformio.ini
firmware/esp32_ws2811_node/src/frame_state.h
firmware/esp32_ws2811_node/src/frame_state.cpp
firmware/esp32_ws2811_node/src/led_output.h
firmware/esp32_ws2811_node/src/led_output.cpp
firmware/esp32_ws2811_node/src/main.cpp
firmware/esp32_ws2811_node/src/runtime_stats.h
firmware/esp32_ws2811_node/test/test_protocol.cpp
light_engine/effects/step_pulse.py
light_engine/effects/single_dot.py
light_engine/effects/theater_phase.py
tests/test_ws2811_emergency_show.py
tests/test_ws2811_emergency_gate1m_show.py
tests/test_ws2811_emergency_node8_two_node.py
```

Original onsite videos referenced during the investigation are external local
evidence and are not part of the repository. Their filenames were:

```text
38766cadaa4e14e7486c393589afacfd.mp4
9e5bac8933db8bbe15f1d94f375b4797.mp4
```

## Commands

**Safety hold:** the commands below are retained for reproducibility, but do
not run either Show with both translator B-to-DI leads connected until the
electrical isolation checks in `Next Useful Evidence` pass. Two push-pull B
outputs must not share a data net.

Build the current guarded-SPI4 candidate only. This command does **not**
recreate the preserved C477 SPI6 baseline:

```powershell
$env:PLATFORMIO_CORE_DIR='A:\PlatformIO'
pio run -d firmware\esp32_ws2811_node `
  -e esp32-s3-node-2-emergency-change-only-ab
```

Restore the exact Node 2 C477 SPI6 baseline (do not rebuild first):

```powershell
$env:PLATFORMIO_CORE_DIR='A:\PlatformIO'
$bin='firmware\esp32_ws2811_node\baselines\node2-gate1m-spi6-c477\firmware.bin'
if ((Get-FileHash -Algorithm SHA256 $bin).Hash -ne `
  'C47760A6B33A36B1CB4D67AF3A380742B93C7701036B02B45A501FA6881AE420') {
  throw 'Node 2 baseline hash mismatch'
}
pio pkg exec --package tool-esptoolpy -- esptool.py `
  --chip esp32s3 --port COM7 --baud 460800 write_flash 0x10000 $bin
pio pkg exec --package tool-esptoolpy -- esptool.py `
  --chip esp32s3 --port COM7 --baud 460800 verify_flash 0x10000 $bin
```

Upload Node 8:

```powershell
$env:PLATFORMIO_CORE_DIR='A:\PlatformIO'
pio run -d firmware\esp32_ws2811_node `
  -e esp32-s3-node-8-emergency-change-only-ab `
  -t upload --upload-port COM13
```

Monitor:

```powershell
pio device monitor --port COM7 --baud 115200 --filter time
```

In another terminal:

```powershell
pio device monitor --port COM13 --baud 115200 --filter time
```

Force Node 2 black before the Node 8 isolation run:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config\profiles\ws2811-emergency-node2-strip41.yaml `
  run `
  --show config\shows\ws2811-emergency-black-sentinel-3s.yaml
```

The sentinel sends 15 logical black packets total. With no errors, the Node 2
counter deltas are 15 receives/attempts/commits, 14 identical skips, one Host
physical write, and one SAFE frame. Record the post-sentinel stats as the
baseline; every Node 2 delta must then remain zero during the Node 8-only Show.

Run Node 8 isolation gate:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config\profiles\ws2811-emergency-node8-strip42.yaml `
  run `
  --show config\shows\ws2811-emergency-node8-strip42-blue-60s.yaml
```

Node 8 must end at 300 receives/attempts/commits, 198 identical skips,
`spi_ok=104`, and one SAFE frame, with all errors zero. Strip 41 must remain
black and Node 2 counters must not move.

Run Gate 1m:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config\profiles\ws2811-emergency-node2-strip41.yaml `
  run `
  --show config\shows\ws2811-emergency-node2-strip41-gate1m-120s.yaml
```

## Gate 1m Timeline And Counters

```text
0-5       black
5-25      Blue20 forward single-dot control
25-30     black
30-50     Blue20 exact three-phase theater mask
50-55     black
55-60     uniform Green20
60-65     black
65-85     Green20 forward single-dot
85-90     black
90-110    Orange20_08 forward single-dot control
110-120   black, then SAFE
```

No-error final counter contract:

```text
received=queued=attempts=refresh_ok=last_rx=last_commit=600
identical_skipped=393
spi_ok=209
safe_frames=1
```

All reject, gap, overwrite, timeout, output, invariant, hash-mismatch, and
uniform-mismatch counters must be zero. A visual event with perfect counters
is still a physical failure event.

## Evidence That Must Not Be Lost

- Autonomous repeated/dynamic tests failed without UDP, so Wi-Fi and Python
  are not necessary causes of the corruption.
- SPI4 and SPI6 both showed dynamic corruption. The problem is not uniquely
  RMT or one SPI encoding width.
- Static endpoint success did not predict transition success. The Gate 1k
  two-level pulse failed twice before the restricted UDP run.
- There is no continuous safe RGB range. Evidence applies to exact complete
  payloads and directed edges only.
- Gate 1l counters matched the software model exactly at frame 526:
  `attempts=refresh_ok=526`, `identical_skipped=357`, `spi_ok=171`, and all
  error counters zero, while a very rare wrong-position/wrong-color flow event
  was still observed.
- Gate 1m became very stable over repeated runs and the last reported run was
  visually perfect. No final frame-600 counters or fixed video were retained,
  so this is not a formal zero-error pass.
- Node 8's 60-second run matched the real Engine budget: 299 ordinary frames
  plus SAFE, 300 total; 102 Host-triggered physical writes, 198 duplicate
  skips, and 104 total SPI transactions including two startup black writes.
- In the first undirected run, strip 41 lit while the Host addressed only
  `.208`; it stayed fixed and did not follow strip 42. Node 2 was powered, so
  the later failed ping did not prove power-off. That observation was
  consistent with a missed startup black or old latch, but it did not pass
  isolation.
- The subsequent directed isolation test failed decisively. Node 8 was on the
  guarded-SPI4 image while Node 2 remained on its Gate 1m SPI6 image. A Node 2
  black sentinel first made strip 41 black. Starting the Node 8-only Show then
  made strip 41 white. Pressing either board's RST made its own strip black and
  the other strip white. While the Node 8 Show was running, a Node 2 black
  sentinel briefly extinguished strip 41 and, at that exact instant, made
  exactly the first ten DI-side groups of strip 42 white.
- The ten-group boundary matches Node 2's compiled frame length and is a strong
  data-transaction fingerprint. White is the observed corrupted latch, not a
  Host white command. The reset-to-other-strip response also bypasses Host
  routing and strongly locates the failure in the electrical data/interface
  layer.
- Software route audit confirms that the Node 2 profile unicasts only to
  `.202:9001` with node 2 / GPIO4 / ten groups, while Node 8-only unicasts only
  to `.208:9001` with node 8 / GPIO4 / twenty groups. Firmware validates node
  ID and descriptor; endpoint-contract tests and the full 726-test suite pass.
- The leading unverified causes are accidental B/DI/A/GPIO connection, terminal
  or breadboard common rows, a high-resistance/open ground that returns through
  another signal, or shared-rail/back-power transients. The exact ten-group
  boundary makes direct data-path connection or contention more likely than a
  generic supply dip.
- The prior production/emergency SPI6 source timing has T0H 200 ns. A
  user-provided WS2811 V2.1 excerpt specifies 220-380 ns, so SPI6 has one
  definite quoted-window violation. The original datasheet is not in the
  repository. Guarded SPI4 is inside the quoted timing/reset windows but also
  failed Gate 1g, so a timing-compliance correction is not a proven root-cause
  repair. Node 8 now runs the guarded-SPI4 candidate, but the electrical
  isolation failure blocks any production inference.

## Next Useful Evidence

The two-node Show is blocked. First stop all Shows and remove 24 V, both ESP32
5 V feeds, and both USB cables. With no power applied:

1. Check continuity. Grounds should connect. B1/B2, DI41/DI42, A1/A2, the two
   GPIO4 pins, and separately regulated 3.3 V/VCCA rails must not connect.
2. Inspect whether the two translator modules share a breadboard row, terminal,
   green-wire splice, or DI connector. Two SN74LVC1T45 B outputs are push-pull
   and must never be tied together.
3. For the minimum powered A/B, disconnect and insulate only the Node 8
   translator B-to-strip42-DI lead at the B output before restoring power.
   Any strip-42 ten-group response to a Node 2 write proves a hidden downstream
   connection; stop immediately.
4. With that B lead still disconnected, any strip-41 response to Node 8 RST or
   Show points to shared power/ground backfeed, an internal common net, or the
   wrong lead having been disconnected. Stop immediately.
5. Repeat in the opposite direction only after the first direction is clean.

If a final counter discriminator is needed after the wiring is safe, record
both serial baselines and run only the Node 2 black sentinel. Node 2 should add
15 received/queued/attempted/committed frames, 14 skips, one SPI transaction,
and one SAFE. Node 8 must add zero to every receive/reject/queue/attempt/SPI
counter. A strip-42 change with Node 8 `received` unchanged is electrical.

Converter heating, ESP resets, repeated USB disconnects, or any other-strip
response to a disconnected controller is an immediate all-power-off condition.

### Latest continuity observation

With all supplies removed but the strip power leads still connected, the meter
continuity indicator sounded for B1/B2, the two green DI leads, and A1/A2. Once
the strip power leads were disconnected, A1/A2, B1/B2, and DI41/DI42 all
measured `OL` in both directions. This makes a permanent converter-side copper
short less likely and shows that the passive path depends on the connected
strip/power network.
Possible paths include WS2811/translator protection junctions, common 24 V/GND,
a weak/open signal return, or supply/back-power coupling. A continuity buzzer
through semiconductor junctions is not proof of a zero-ohm short. Do not
reconnect both B-to-DI paths; the next powered A/B uses only one data path.

With supplies still absent, the operator next connected only the two white/GND
strip leads and measured DI41/DI42, then connected only the two red/24V+ leads
and repeated. Neither configuration buzzed and both measured `OL`. The passive
path appears only when both strip supply rails and both complete strip circuits
are connected; it is not a direct short through either single supply rail.

The first powered single-data-path A/B left Node 8 B disconnected and
insulated, held strip 42's lamp-side DI at its own GND, and connected only Node
2 B to strip 41 DI. The Node 2 black sentinel caused no synchronous response,
and pressing either ESP32 RST caused no cross-strip response. Strip 42 did light
after the Host command finished, leaving a delayed end-state anomaly whose
relationship to SAFE, later timeout, or power-up latch was not captured. The
stronger directed result is that isolating one B-to-DI branch removed the prior
immediate reciprocal RST effect. The interference therefore requires both data
branches connected, rather than shared power alone being sufficient. Reverse
single-data-path A/B is the next gate.

The strips remain on the intended parallel 24V+/GND supply during powered A/B.
Before removing one B-to-DI branch, the operator measured the two SN74 B
endpoints open with the parallel strip wiring present. If measured with every
supply removed, this rules out a DC B-to-B hard tie. It does not rule out
high-frequency coupling, ground bounce, or rail interaction that a continuity
meter cannot observe.

The reverse one-data-path A/B disconnected Node 2 B, held strip 41 DI at its
own GND, and connected only Node 8 B to strip 42. Strip 41 stayed black. Node 2
RST affected neither strip; Node 8 RST affected only strip 42. Both single-data
directions therefore remove the immediate cross-strip effect. Strip 42's
guarded-SPI4 playback was nevertheless subjectively less stable than its prior
run, so compliant nominal source timing is still not a demonstrated physical
repair.

Both one-data tests also omitted USB while the original dual test used serial
monitoring. The next controlled variable is therefore USB/back-power: restore
both independent B-to-DI leads with power off, remove both temporary DI-to-GND
ties, keep both USB cables absent, and power the ESP32 boards only from XL4015.
Run one Node 2 black sentinel and one Node 8 black sentinel before any effect.
Any response on the non-target strip is an immediate stop.

That no-USB dual-path gate failed identically. Node 2 black/RST made strip 41
black and strip 42 light; Node 8 black/RST made strip 42 black and strip 41
light. Both ESP32 boards were powered only by XL4015, both USB cables were
absent, and B1/B2 again measured open with power removed. USB back-power and a
DC B-to-B hard tie are therefore not necessary causes. Both single-data-path
directions remove the effect, while restoring both data paths restores the
reciprocal failure.

The current leading interpretation is dynamic coupling: fast 5 V B-side edges,
common-ground bounce, or translator VCCB interaction reshapes the other path's
zero symbols toward all-one/white decoding. No waveform has yet confirmed the
mechanism. Before another powered test, physically separate and shorten the two
data runs, route each beside its own short local ground return, and separate the
translator modules. Repeat only the two three-second black sentinels; do not run
effects until neither sentinel changes the non-target strip.

For each accepted fixture, also keep the binary, wiring, power, and Show
unchanged while collecting:

1. Fixed-camera video from power application through the complete Show.
2. The final serial stats line paired with each video.
3. At least three cold-start runs and three warm reruns.
4. Whether any event is confined to physical group 1, group 2, or moves toward
   the DI end.
5. If instruments are available, synchronized GPIO4, level-shifter B, and
   strip-DI waveforms for one admitted failing transition.

Do not tune more timing constants during this comparison. If a second engineer
changes firmware, retain the old binary and hash and change only one graph,
palette, cadence, or electrical variable per gate.

## APP Boundary

The current profile is not bound cryptographically to either fixed Show, and
the effects remain reusable parameterized Host effects. The APP must not expose
free RGB, arbitrary brightness, arbitrary speed, mask drawing, interpolation,
or generic effect selection for this emergency path. At most, it may later
expose named presets whose exact Host payload trace and firmware state graph
have passed the same hardware gate.
