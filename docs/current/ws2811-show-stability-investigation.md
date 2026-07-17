# WS2811 Show Stability Investigation

Status: active investigation; a corrected 5 V level-shifter baseline is being
retested before the 30 FPS physical-output gate; updated 2026-07-17.

All physical conclusions in this document are **NOT HARDWARE VERIFIED** unless
the specific observation is recorded below. This document is an evidence
ledger, not a replacement for `docs/IMPLEMENTATION_PLAN.md` or the hardware
acceptance checklist.

## Goal and fixed test identity

The production goal is one ESP32-S3 per physical WS2811 strip. Every node must
play 30 FPS static and dynamic Show content without unintended color changes,
brightness jumps, black flashes, freezes, or spatial corruption. Multiple
nodes must later apply the same scheduled frame boundary together.

The primary isolation fixture is:

| Item | Value |
|---|---|
| ESP32 | Node 2, ESP32-S3 |
| Serial | COM7 |
| IPv4 | `192.168.31.202` |
| Strip | `strip_41` |
| Installed length | 0.5 m / 10 WS2811 groups |
| Data output | GPIO4 |
| Level conversion | GPIO4 -> replacement SN74LVC1T45 A -> B -> strip DI |
| Power | 24 V strip supply; XL4015 5 V for ESP32 and VCCB |

Do not change wiring, firmware, transport, timing, group count, color order,
or power state within one A/B unless that item is the declared independent
variable.

## Current conclusion

### 2026-07-17 level-shifter supply correction supersedes the old fixture

The operator found that the SN74LVC1T45 B-side supply must be connected to
5 V and corrected the fixture. Strip 41 became visibly much more stable after
that correction. Although the intended wiring in this ledger already listed
`VCCB=5 V`, the earlier physical runs did not establish that the real VCCB pin
was at 5 V. Those runs therefore used an invalid or unverified fixture
condition.

Until the corrected fixture is retested, all earlier conclusions that used the
SN74 path to reject SPI4, the V2.1 timing table, or two-node operation are
historical observations with a VCCB confound. They are not deleted, but they no
longer close those branches. The current controlled assumption is:

- both SN74LVC1T45 modules have `VCCA=3.3 V`, `DIR=3.3 V`, and `VCCB=5.0 V`;
- both ESP32 nodes and both strips share the intended ground reference;
- Node 2 and Node 8 both use the same guarded SPI4 encoder: 3.2 MHz,
  `0=1000`, `1=1100`, RGB/MSB-first, and 500 us low guards;
- the known Blue20 staged payload remains unchanged so the hardware-supply and
  SPI6-to-SPI4 correction are not mixed with a new palette or effect;
- the preserved C477 SPI6 binary is excluded because its 200 ns T0H is below
  the supplied V2.1 minimum of 220 ns.

The next physical gate is the existing staged Node 2 plus Node 8 Immediate
Show: Node 2 alone, Node 8 alone, then both together. It is **NOT HARDWARE
VERIFIED** until the corrected two-node fixture completes the gate. Immediate
mode tests independent addressing and joint playback, not strict scheduled
synchronization.

The two current-source candidates were rebuilt before this gate:

| Node | Environment | Size | SHA-256 |
|---|---|---:|---|
| 2 | `esp32-s3-node-2-emergency-change-only-ab` | 729168 | `F01B83C8BEF564578E36C49E50C6BC3324ED17A1BD251853729C35B7F318B90A` |
| 8 | `esp32-s3-node-8-emergency-change-only-ab` | 729168 | `C99629D842EC523FB3C6001BF31682AB94625EBF173C2D25316F93D32D50B841` |

Both builds completed successfully and contain the guarded-SPI4 backend
identity. Neither had been flashed when these hashes were recorded.

### 2026-07-17 frozen-breath wiring A/B localizes the dominant fault

After the VCCB correction and powered static checks, Node 2 was moved to the
unrestricted RGB/SPI4 presentation A/B image and strip 41 ran a uniform pure
blue breath. Host-side tests decoded every UDP payload and proved that all ten
groups were identical, red and green were always zero, and blue was confined
to raw values 5 through 37. The 15 FPS live breath nevertheless produced about
50 whole-strip red events per run.

To remove the live effect renderer, transform, mapping, and Show runtime from
the playback interval, the same 600 Immediate UDP packets were generated in
advance, validated, and frozen. The trace semantic SHA-256 is
`A07C59FD0AA9AD18E8BE1FD421CAFFBAF5E46947D8B1956E2ED016BAB7431436`.
It contains 450 active frames, 32 blue levels, ten identical groups per frame,
and no nonzero red or green byte. Frozen replay initially reproduced between
53 and 60 whole-strip wrong-color events in two runs.

The operator then disconnected and reconnected all three strip wires. No
firmware, Host payload, profile, Show, SPI timing, or supply setting changed.
The next frozen replay fell to three events: two red and one green. A following
identical replay had zero visible events. This is the strongest current A/B:
the dominant instability changes with the physical three-wire connection while
the complete software and wire-data intent remain fixed.

The result does not identify which conductor or endpoint was responsible
because 24 V, GND, and DI were moved together. It does localize the next work
to connector contact, local ground reference, SN74 B-to-DI wiring, or the strip
input connection. One zero-event run is promising but is not a reusable pass.
Keep the fixture untouched and require two more consecutive zero-event frozen
replays before returning to live breath. Any new event fails the current
physical-connection gate. All candidates retain the V2.1-compliant guarded
SPI4 timing; the result does not justify returning to the noncompliant SPI6
baseline.

### 2026-07-17 per-strip DI pull-down and Node 8-only breath observation

The operator added one 10 kohm pull-down resistor at each strip-side data
input: strip 41 DI to its strip-side GND, and strip 42 DI to its strip-side
GND. Both resistors were present for the following observation. This is a new
fixture condition and must remain fixed during the next discriminator.

The Node 8-only unrestricted 15 FPS pure-blue breath then made strip 42 breathe
normally. During the same run, strip 41 showed physical group 1 black and
physical groups 2-10 white. The Node 8-only Host profile contains only node 8
at `.208`, output 1 on GPIO4, and all 20 groups of strip 42; its Show commands
all 20 strip-42 groups to the same pure-blue breath value. It contains no node
2 or strip-41 output and no legal white or partial-strip state.

This observation does not yet establish that Node 8 activity caused the
strip-41 state. Strip 41 was not first placed in a deliberately observed black
state and paired with before/after Node 2 counters, so the white groups could
have been an older latched state. Electrical interaction correlated with the
Node 8 run also remains possible. Record both explanations as open; do not
promote either to a located cause.

A follow-up observation weakens the pure old-latch explanation. A directed
Node 2 black command could make all of strip 41 black. While the Node 8-only
breath remained active, repeated Node 2 black commands cleared strip 41 only
temporarily; strip 41 physical group 2 and later groups subsequently lit red
again and could change color, although the relit state was not described as
flashing. Strip 42 continued its breath stably throughout. Because Node 2
`received` and `spi_ok` deltas were not captured immediately before and after
the relight, this observation still cannot distinguish an unintended software
sender from a physical response correlated with Node 8 activity. It does show
that an untouched stale strip-41 latch is no longer sufficient by itself.

A subsequent isolated stats window closes the normal Node 2 software-output
branch for the captured interval. COM7 uptime advanced continuously by
30,024 ms while `received`, `queued`, `attempts`, `refresh_ok`, `spi_ok`,
`encoded_hash_checks`, `uniform_checks`, `safe_frames`, `timeout_black`,
`last_rx`, and `last_commit` all had zero delta and remained respectively
45/45/45/45/47/47/47/1/0/45/45. Over the same captured window, COM13
`received`, `queued`, `attempts`, `refresh_ok`, `spi_ok`,
`encoded_hash_checks`, and `uniform_checks` each increased by 385, with all
reported error counters remaining zero. The attachment ended at Node 8 frame
385 of the expected 600 and before its SAFE frame (`safe_frames=0`), so the
complete 40-second Show is not accepted. If the reported strip-41 visual event
occurred inside this exact window, it was not caused by Host UDP reception at
Node 2 or a normal Node 2 firmware SPI transaction. Node 8 activity-correlated
electrical coupling, a local strip-41 electrical fault, and a previously
misdecoded black transaction remain possible.

The final stats completed that same run. Node 8 reached
`received/queued/attempts/refresh_ok=600/600/600/600`,
`spi_ok/encoded_hash_checks/uniform_checks=602/602/602`, and
`safe_frames=1`, with all reported error counters zero. Node 2 remained at
`received/queued/attempts/refresh_ok=45/45/45/45`,
`spi_ok/encoded_hash_checks/uniform_checks=47/47/47`, and `safe_frames=1`
through COM7 `uptime_ms=365126`, also with all reported errors zero. The
complete Node 8-only software contract therefore passed and the Node 2 control
path had zero activity throughout it. Any strip-41 visual anomaly observed in
this interval was not direct software control through Node 2; investigation
must remain on the electrical or physical paths still listed above.

The decisive in-run physical A/B localized the remaining interaction to the
two data branches. While the Node 8 breath was running, separating the two
green SN74 `B -> DI` jumper wires prevented Node 8 activity from changing
strip 41. Bringing those same two data wires close together during the same
run made strip 41 light immediately or relight. Node 2 counters had zero delta
throughout this interval. This excludes Host misrouting and normal Node 2
firmware output and identifies near-field coupling between the two `B -> DI`
data branches as the demonstrated trigger. The exact electromagnetic coupling
mechanism and noise margin remain unmeasured.

The immediate fixture mitigation is to keep the two data branches physically
separated, avoid parallel routing and bundles, route each `B -> DI` conductor
close to its own ground return, and keep each branch as short as practical.
Where data branches must cross, cross them at approximately 90 degrees. Retain
the 10 kohm `DI -> GND` pull-down on each strip input.

With that separated routing fixed and each data branch kept with its own
ground return, the Node 2-only 15 FPS pure-blue breath passed: all ten groups
of strip 41 breathed as commanded and strip 42 remained black throughout.
Together with the corresponding Node 8-only result under separated routing,
single-node isolation has now passed in both directions on this fixture. The
next physical gate is the staged two-node breath: Node 2 alone, Node 8 alone,
then both nodes breathing together without changing the wiring.

That staged two-node breath failed visually despite exact software counters.
During the 5-35 second Node 8-only cue, strip 41 physical group 1 flashed
wrong colors. During the 40-70 second simultaneous breath, both strips showed
minor wrong-color events, with more events on strip 41. Each node increased
`received`, `queued`, `attempts`, `refresh_ok`, and `spi_ok` by 1125, accepted
one SAFE frame, and reported zero errors. The unrestricted presentation A/B
firmware therefore transmitted every logical frame physically. Inactive Node
2 repeatedly sent complete black WS2811 transactions during the Node 8-only
cue; logical black was not an electrically quiet data branch, and its repeated
T0 activity remained available to couple into the adjacent path.

The next A/B separates unrestricted content acceptance from physical refresh
cadence. New macro `LIGHT_BELT_CONTENT_DEDUPE_AB` enables exact complete-pixel
payload deduplication without the emergency whitelist, state graph, group-0
restriction, or 150 ms interval. KEY and SAFE frames always force a physical
write. Both candidates retain RGB guarded SPI4 at 3.2 MHz with `0=1000`,
`1=1100`, and 500 us low guards:

| Node | Environment | Size | SHA-256 |
|---|---|---:|---|
| 2 | `esp32-s3-node-2-fixed-gpio4-content-dedupe-ab` | 727456 | `469631595379B5436CB1D1212419B7F6D6B45E2A77C60A602133896DCADBAFD0` |
| 8 | `esp32-s3-node-8-fixed-gpio4-content-dedupe-ab` | 727456 | `C3E2FD215B6F544E0CB089717860EFEBE19E538CBF9ACAF90F6E1B89828007F8` |

For the unchanged 1125-frame staged breath, the predicted Host-triggered
physical-write/identical-skip budgets are 313/812 on Node 2 and 624/501 on
Node 8. Including the two startup black writes, final `spi_ok` should be 315
and 626 respectively. These binaries and budgets are **NOT HARDWARE VERIFIED**.
Flash both matching candidates and rerun the unchanged staged Show without
moving the separated data/ground routing. If wrong colors remain in the
simultaneous phase, the next single-variable A/B is a 5 ms offset between the
two nodes' physical transactions.

Both content-dedupe candidates were then flashed successfully. Node 2 was
flashed on COM7 and identifies with MAC `E0:72:A1:D3:30:3C`; Node 8 was flashed
on COM13 and identifies with MAC `28:84:85:8A:36:B0`. Esptool verified the hash
of every written partition for both boards. The post-flash files on disk retain
the audited size and SHA-256 values above. The next gate is the unchanged
75-second staged breath from fresh counters. Expected final content-dedupe
counters are Node 2 `spi_ok=315`, `identical_skipped=812`, and Node 8
`spi_ok=626`, `identical_skipped=501`, with 1125 accepted frames and one SAFE
on each node.

The content-dedupe staged hardware run passed the 5-35 second Node 8-only
phase: strip 42 breathed stably and strip 41 remained stable. The 40-70 second
simultaneous phase still produced wrong-color jumps on both strips. The second
run's counter deltas exactly matched the oracle: Node 2 added 313 physical SPI
writes and 812 identical skips; Node 8 added 624 physical writes and 501
identical skips. Reported error and mismatch counters remained zero. Exact
content deduplication therefore removed the repeated-black T0 trigger on the
inactive branch, but it did not remove the interaction when both branches
changed and transmitted physically.

The next single-variable candidate delays only Node 8 non-skipped Immediate
Host physical writes by 5 ms. It does not delay skipped frames, Node 2,
Scheduled frames, startup black, watchdog black, recovery, or rollback. KEY
and SAFE are non-skipped Host writes and receive the same delay. Runtime stats
expose `physical_offset_waits` and `physical_offset_cancelled` so the A/B can
prove the delay path actually ran and whether any pending wait was cancelled.
The final **NOT HARDWARE VERIFIED** binary is preserved at
`firmware/esp32_ws2811_node/baselines/node8-content-dedupe-offset5ms-a1a81d6c/`:

| Environment | Size | SHA-256 |
|---|---:|---|
| `esp32-s3-node-8-fixed-gpio4-content-dedupe-offset5ms-ab` | 727952 | `A1A81D6CBA0FC958FD5C355F0079952F06393BE3AA13862509B88BF5C5263D2C` |

The COM13 upload succeeded with the expected Node 8 MAC
`28:84:85:8A:36:B0`, and esptool verified the written hashes. PlatformIO
rebuilt during upload, so the actual flashed file is distinct from the
pre-upload A1A81 build. Both identities are preserved separately:

- pre-upload: `firmware/esp32_ws2811_node/baselines/node8-content-dedupe-offset5ms-a1a81d6c/firmware.bin`, SHA-256 `A1A81D6CBA0FC958FD5C355F0079952F06393BE3AA13862509B88BF5C5263D2C`;
- post-upload/flashed: `firmware/esp32_ws2811_node/baselines/node8-content-dedupe-offset5ms-flashed-3b46d919/firmware.bin`, SHA-256 `3B46D919A1DB836707B1B08DF3B9AB74ADB0A5F7563F7219028A3FF0FC886971`.

Both files are 727952 bytes and retain the declared content-dedupe,
offset-counter, and guarded-SPI4 identities. The current onsite Node 8
firmware identity is the post-upload `3B46D919...6971` hash.

For a fresh unchanged 75-second staged run, expect Node 2
`received=1125`, `spi_ok=315`, `identical_skipped=812`; expect Node 8
`received=1125`, `spi_ok=626`, `identical_skipped=501`,
`physical_offset_waits=624`, and `physical_offset_cancelled=0`. Each node must
accept one SAFE and report no rejects, errors, or mismatches.

The next single-variable gate is:

1. Stop other senders and record baseline stats from both nodes.
2. Send the directed Node 2 black sentinel, confirm all ten strip-41 groups are
   visibly black, and record that only Node 2 counters changed.
3. Without resetting, repowering, rewiring, or changing either 10 kohm
   pull-down, run the exact same Node 8-only 15 FPS blue-breath profile and
   Show once.
4. Record both final stats and the complete visual state of both strips. Node 2
   must show zero receive/queue/attempt/refresh/SPI delta during the Node 8
   run. If strip 41 changes from the confirmed black state while those Node 2
   counters remain unchanged, that supports an electrical response correlated
   with Node 8 activity. If strip 41 remains black, the prior white state is
   consistent with an old latch. Any Node 2 counter growth invalidates sender
   isolation and the gate must be repeated.

### 2026-07-17 30 ms offset and single-path residual instability

The follow-up Node 8 candidate increased the Immediate physical-write offset
from 5 ms to 30 ms while retaining exact-content deduplication and the guarded
SPI4 waveform. It was flashed successfully to COM13 / Node 8; esptool reported
MAC `28:84:85:8A:36:B0` and verified every written partition. The preserved
image is 727952 bytes with SHA-256
`C5BAC80C948578AC3EA6D0873D004795B0C42B97C0221BA05F1EB56D8126A44B`.

The latest onsite isolation observation reported that strip 41 can still
flash during its Node 2-only breath phase. No exact event count or complete
counter delta accompanied that observation, so it is a visual failure record,
not a quantified acceptance run. It does establish that simultaneous changing
output from Node 8 is not necessary for every observed strip-41 anomaly. A
Node 8-only offset also cannot repair a fault that occurs while Node 2 is the
only active transmitter.

This strengthens the physical single-path and regenerated-signal hypothesis,
especially in combination with the earlier frozen-trace result changing after
the strip's three wires were reseated. It does not by itself locate the defect
inside the strip IC. The remaining boundary still includes the Node 2 GPIO4
output, SN74 B output and supply reference, data/ground conductors and contacts,
strip DI input, first receiver, and downstream regeneration.

The new 171-second two-strip all-effects Show is therefore exploratory only.
It covers all 17 registered effects with one-second black separators and puts
deterministic pure-color effects before inherently multicolor, random, and
generated-media effects. Visible wrong colors, extra lit groups, black-state
violations, or latching remain physical failures when Host payload and node
counters pass, but this sweep must not be used to claim a safe palette, strict
synchronization, unrestricted APP color control, or production acceptance.

The following 32-second virtual-path Show is also preserved as an exploratory
asset: `ws2811-ab-two-node-virtual-path-color-comet-32s.yaml`. It renders one
30-group comet over the authored path `strip_41[0..9] -> strip_42[0..19]`, then
reverses the complete path. At speed 6 the comet wraps after approximately
`(30 + 2) / 6 = 5.33` seconds and advances its default hue by 60 degrees, so
each 14-second direction contains multiple colors. The focused Host test proves
logical seam crossing, reverse mapping, and color changes. It does not prove a
physical seamless boundary: the current Node 8 30 ms offset can create a short
gap or overlap at the cross-node seam, and the physical installation direction
has not been independently surveyed.

### 2026-07-17 field readback and asset freeze

Both onsite ESP32-S3 application regions were read without erasing or writing.
Esptool 4.11.0 connected to the expected MAC on each port, read the exact
recorded application length from flash offset `0x10000`, and hard-reset the
board after the read:

| Node | Port | MAC | Read length | Readback SHA-256 | Recorded image match |
|---|---|---|---:|---|---|
| 2 | COM7 | `E0:72:A1:D3:30:3C` | 727456 | `469631595379B5436CB1D1212419B7F6D6B45E2A77C60A602133896DCADBAFD0` | exact |
| 8 | COM13 | `28:84:85:8A:36:B0` | 727952 | `C5BAC80C948578AC3EA6D0873D004795B0C42B97C0221BA05F1EB56D8126A44B` | exact |

The Node 2 readback closes the prior binary-preservation gap. Its exact image
is retained under
`firmware/esp32_ws2811_node/baselines/node2-content-dedupe-field-readback-46963159/`.
The Node 8 readback is byte-identical to the already preserved 30 ms flashed
image. The complete diagnostic snapshot is in
`artifacts/baselines/ws2811-two-node-good-effects-20260717/`, with a generated
SHA-256 inventory and verifier. These exact readbacks preserve the current
good-effects state; they do not change its **NOT HARDWARE VERIFIED** status or
remove the residual wrong-color observation.

The reproduced visual corruption does not require Python effects, Show
mapping, UDP reception, scheduled clock estimation, RGB/GRB selection, a
missing first logical group, or a multi-output ESP32 topology.

An exact-length standalone FastLED image with no Wi-Fi, UDP, clock, Show, or
effect code reproduced the failure while repeatedly transmitting an unchanged
solid-blue buffer. A later short-T0H SPI6 diagnostic appeared stable for the
low-entropy blue value `0x40` on groups 2-10, and its changing-frame E/F phases
were reported as passing once after an explicit low interval was added. Those
observations did not generalize to the Host-equivalent `0x25` wire value.

An earlier autonomous `0x25` rerun on the original data interface failed both
functionally and spatially. The controlled baseline is now the replacement
SN74LVC1T45 on the same Node 2 / strip 41 / GPIO4 path. With that baseline, a
SPI6 single-write diagnostic sent raw R, G, and B channel values of `0x25`.
All 10 groups, including the DI-side first group, displayed the correct uniform
red, green, and blue without any flash; its black states were fully black.

That single-write pass did not generalize to repeated or changing frames on
the same replacement-SN74 path. In the SPI6 cadence diagnostic, repeated blue
in D flashed red, E showed both red and blue groups while red was unstable and
flashed off, and some groups commanded black in F displayed red. The current
SPI6 candidate therefore still fails the physical-output gate. The new SN74
improves the baseline and proves single-write RGB function, but it is not a
completed repair and does not permit Show testing.

The controlled SPI4 comparison then changed only the wire timing to 3.2 MHz,
`0=1000`, and `1=1100` while retaining the replacement SN74, GPIO4, 10 groups,
raw `0x25`, 500 us pre/post guards, and the RGB single-write plus D/K/E/F
sequence. The onsite result was "failed, about the same as the previous SPI6
run." SPI4 therefore does not recover repeated/dynamic stability. This closes
software timing enumeration; another guessed SPI encoding is not the next
gate.

The 400 kHz hardware gate no longer supports classifying this fixture as a
FastLED `WS2811_400` strip. The evidence does not yet distinguish these
remaining causes:

1. The installed strip is consistent with the 800 kHz decoding family, but the
   tested combination of 200 ns T0H, 600 ns T1H, and long reset-low intervals
   is not a passing production candidate. It passed only selected `0x40` and
   black patterns and failed the autonomous Host-equivalent `0x25` sequence.
2. The replacement SN74 path controls the DI-side first group correctly in the
   single-write RGB diagnostic, but repeated/dynamic first-group behavior was
   not reported separately.
3. The current 833.3 kHz SPI6 waveform, especially its 200 ns T0H, may lack
   decode margin for repeated and spatially changing `0x25` frames, but the
   standard 800 kHz-family SPI4 comparison also failed and did not isolate
   SPI6 timing as the sole cause.
4. The replacement level-shifter path, missing source resistor, ground
   reference, or first WS2811 DI receiver may still be marginal under repeated
   transitions even though single-write RGB now passes.

Previously observed static colors, including white in the legacy sequence,
could remain latched without continuous refresh. That reduces the likelihood
of a simple steady-state current shortage as the only cause, but it does not
exclude ground-reference error, transient supply noise, or a marginal data
threshold during transmission.

## Evidence status snapshot

| Statement | Status | Basis or limitation |
|---|---|---|
| One autonomous blue write can remain stable for 5 s | Observed on this fixture | Exact 10-group cadence image, phase A |
| Repeating the identical blue buffer can cause brightness/color corruption | Observed on this fixture | Exact 10-group cadence image, phases B-E |
| Faster phases looked visually more active | Observed, not quantified | All phases used 200 writes but had unequal durations; no event counter or fixed-frame video analysis |
| Python/effect rendering is required to create the fault | Disproved for this fixture | Standalone image contains no Python, Show, UDP, Wi-Fi, or effect renderer |
| CPU-side SPI data changed unexpectedly | Not supported by the executed diagnostic | Hash and uniform checks stayed clean; GPIO was not measured |
| The FastLED 400 kHz controller produces the commanded blue | Disproved on this fixture | Startup confirmed `timing_khz=400`; phase A displayed stable white instead of blue |
| Shorter 800 kHz-family T0H stabilizes repeated blue on groups 2-10 | Observed once on this fixture | SPI6 A and D were stable pure blue after the first group |
| Original SPI6 diagnostic controls group one and ends fully black | Failed in the earlier run | Group one did not follow; immediate final black left blue residual light |
| SPI6 plus >=500 us low passes repeated blue D and repeated black K on groups 2-10 | Observed on this fixture | Both 33 ms phases matched expected output onsite |
| Latest D/K run controls the DI-side first group | Unknown | The user did not explicitly report that group in this run |
| SPI6 changing-frame E/F at blue `0x40` passes | Observed once on this fixture | Narrow historical observation; DI group one was not described separately and `0x25` later failed |
| Original-interface autonomous blue `0x25` is functionally correct and stable | Disproved on this fixture | A displayed stable green; D jumped among three colors; E and F were spatially/color corrupted |
| Replacement-SN74 SPI6 single-write raw RGB `0x25` is correct | Observed on this fixture | R/G/B and black were correct and stable across all 10 groups, including the DI-side first group |
| Replacement-SN74 SPI6 cadence `0x25` is stable | Disproved on this fixture | D flashed red; E contained unstable red and blue groups; F displayed red in some commanded-black groups |
| Replacing the SN74 completed the repair or permits Show playback | Disproved | The same replacement-SN74 path passed single writes and failed repeated/dynamic cadence |
| Replacement-SN74 SPI4 cadence is stable | Disproved on this fixture | The controlled 3.2 MHz `1000/1100` run failed about the same as SPI6 |
| Further blind software timing enumeration is justified | Disproved as the next action | Both controlled SPI6 and standard SPI4 failed repeated/dynamic cadence |
| Current shared production SPI6 backend is hardware accepted | Disproved as a promotion claim | The matching autonomous timing/guard candidate failed at `0x25`; production code remains **NOT HARDWARE VERIFIED** and must not be deployed |
| Original SN74LVC1T45 path contributed to the severe failure | Supported, not isolated | Replacement greatly improved single-write behavior, but cadence still fails and no waveform was retained |
| Power-of-two channel values define a continuous safe color range | Disproved as a promotion claim | Static and FLOW states passed selected values, but the two-level pulse in Gate 1k failed in both observed runs |
| The two-level fixed-red pulse is accepted for emergency playback | Disproved on this fixture | Both onsite Gate 1k runs contained an unintended visible event |
| UDP playback can repair the autonomous physical-output fault | Not supported | UDP may reduce physical writes through node-side content dedupe, but every changed payload still requires the same unverified WS2811 transaction |
| The APP can expose arbitrary color or brightness controls | Not authorized | Only exact payloads and directed transitions that pass a bounded gate may be emergency candidates |
| Every other strip/node has the same failure | Unknown | The decisive cadence gate has only been run on Node 2 / strip 41 |
| Multiple nodes can now run a synchronized dynamic Show | Not verified | Single-output 30 FPS stability must pass first |

## Evidence chronology

### Multi-output Node 2 stage

- Node 2 originally drove strips 41 and 42 through separate GPIO/level-shifter
  paths. Each strip could behave correctly alone, while simultaneous connection
  produced cross-strip corruption or a persistently lit region.
- Moving and swapping GPIO4/GPIO5/GPIO7 paths changed which strip failed.
- These results motivated the one-ESP-per-strip production topology. They did
  not prove that multiple logical outputs or the effect renderer were the root
  cause.

### Host and protocol defects that were real

- One Immediate image received packets but rejected every state candidate:
  `received=297`, `state_rejected=297`, `attempts=0`. Cold-start KEY admission
  was repaired; later Immediate runs reached complete acceptance and refresh.
- Scheduled runs initially lost large numbers of frames while the clock was not
  ready. The estimator lower envelope and a 32-sample startup/window removed the
  dominant `clock_not_ready` failure. A later run reached 301 scheduled commits
  with zero scheduled drops, although other runs still had one or two late
  frames.
- An RGB override was introduced after a stable red/green reversal was
  observed. Color order can explain a repeatable swap, not random flashing;
  the production color order still requires per-strip hardware acceptance.

These fixes remain useful. None is evidence that the physical output became
stable.

### SPI output observations

- Immediate RGB steps reached `451/451` accepted and refreshed frames with zero
  state rejection or output errors while the installed strip still jumped.
- Encoded-buffer hash and uniform-frame checks reported zero mismatches. These
  checks prove that the CPU-side encoded buffer was internally consistent up to
  submission. They do not measure the GPIO waveform or what WS2811 latched.
- The production SPI encoder uses 3.2 MHz symbols: `0=1000`, `1=1100`. This is
  approximately `T0H=312.5 ns` and `T1H=625 ns`, close to FastLED's 800 kHz
  WS2811 timing.

### FastLED and legacy-program observations

- A one-output FastLED Immediate image reproduced visual corruption even when
  its UDP and output counters were clean. Together with the standalone result,
  this excludes an SPI-peripheral-only explanation but does not exclude a pulse
  timing assumption shared by the SPI encoder and FastLED controller.
- The original autonomous `main.cpp` has no Wi-Fi, UDP, clock, or Python. Its
  one-write solid colors and 120 ms theater chase appeared stable. Effects that
  refreshed every 20-45 ms did not appear stable.
- The legacy image declared 100 pixels while strip 41 contains 10 groups. That
  mismatch distorts wipe, center, reverse, and comet geometry, so those effects
  are not a clean cadence test.

### Exact-length constant-frame cadence gate

The temporary environment
`esp32-s3-gpio4-cadence-diagnostic` uses FastLED 3.10.3, GPIO4, 10 groups,
brightness 64, no dithering, no network, and an unchanged blue buffer.

| Phase | Physical writes | Period | Observed result |
|---|---:|---:|---|
| A | 1 | hold 5 s | Stable |
| B | 200 | 120 ms / about 24 s | Occasional brightness jump; fewer visible color jumps |
| C | 200 | 60 ms / about 12 s | Unstable; visibly faster events than B |
| D | 200 | 33 ms / about 6.6 s | Unstable; difficult to separate visually from C/E |
| E | 200 | 20 ms / about 4 s | Unstable; difficult to separate visually from C/D |

The DI-side first group changed with the other nine groups during this gate.
This disproves the earlier working theory that software permanently omitted
group zero or that only its visible output was frozen.

Because B-E each contain exactly 200 writes but have different durations, the
visual rate alone does not prove a hard cadence threshold or a higher error
probability per transmitted frame. The robust statement is that repeated
physical writes reproduce corruption and faster writes compress the same 200
opportunities into less wall-clock time. Even the 120 ms phase had an anomaly,
so reducing Show FPS is neither a production fix nor a passing fallback.

Every later cadence phase with an explicit 500 us low guard leaves the data
line in the WS2811 reset/latch state longer than the V2.1 minimum of 280 us.
A 20 ms frame period alone is not reset evidence unless DIN is confirmed low
during the idle interval. The later guarded phases satisfy the requirement by
construction, and 120 ms cadence cannot repair a malformed wire transaction.
Sending black immediately before each intended frame would add another
physical transmission and another opportunity for corruption; it would also
risk a visible black event. It is not a reset fix and is not an acceptance
candidate.

The final blue-to-black transition was a different boundary from the 33 ms
repeated-blue cadence. The then-tested Gate 1b SPI6 frame had a 32-byte low
guard before and after its payload. At 5 MHz, both guards together represented
about 102.4 us of low symbols, while either individual guard was about 51.2 us.
That historical detail can explain why a separate reset-low experiment was
needed, but it cannot explain away the later `0x25` failure: the later candidate
used symmetric 313-byte guards, approximately 500.8 us each.

## Investigated and failed routes

| Route | What it established | Why it did not finish the task |
|---|---|---|
| Rewrite/tune authored effects and Show YAML | Found real renderer/configuration issues | Standalone unchanged pixels still fail |
| Host output-health counters | Host submitted every logical frame without local drops | They do not prove ESP receipt, GPIO integrity, or WS2811 latch state |
| Wi-Fi/IP and UDP repair | Restored packet reception | Autonomous firmware fails without networking |
| Immediate session admission repair | Changed all-state-rejected runs into accepted/committed runs | Clean acceptance still accompanied visual corruption |
| Scheduled clock lower envelope/window tuning | Removed dominant clock-not-ready drops and produced a 301/301 run | A clean scheduled run is transport evidence, not physical stability |
| RGB/GRB override | Addresses deterministic red/green reversal | Cannot explain intermittent white, black, or brightness events |
| SPI DMA buffer/uniform hashes | Found no CPU-buffer mutation before submission | Does not observe GPIO4, level-shifter B, or DI |
| SPI versus FastLED output | Both can reproduce repeated-refresh corruption | They share an approximately 800 kHz timing family and the same physical path |
| One ESP32 per strip | Removes multi-output contention and is still the intended topology | It does not repair a marginal single data path |
| Treat DI group zero separately | Earlier observations suggested a special first-group fault | Exact-length cadence phases moved the first group with the other nine |

A previous one-off success of the nine-effect Show is evidence that the system
can sometimes display valid frames. It is not contradictory to an intermittent
per-refresh fault and must not be used as acceptance evidence.

## What not to repeat

Do not return to any of these until the standalone physical-refresh gate passes:

- rewriting authored effects in C++;
- changing Python effect mapping, Show YAML, UDP packet cadence, session keys,
  or scheduled-clock parameters;
- adding more CPU buffer hashes without measuring the physical signal;
- switching RGB and GRB to address random flashing;
- retrying multi-strip effects or multi-node synchronization;
- treating one visually successful run as hardware acceptance;
- limiting production animation to approximately 8 FPS.

The legacy C++ program and the original-timing constant-frame standalone
program both failed under repeated physical refresh. The revised SPI6 plus
500 us-low diagnostic passed selected constant `0x40` blue and black patterns
once, but the autonomous `0x25` rerun failed without any effect or network
runtime. Effect language is still not the current boundary.

## Next decision gates

### Gate 1 result: 400 kHz functional decode failed

The gate kept GPIO4, the 10-group blue buffer, brightness, cadence phases,
level shifter, wiring, and power unchanged. The two standalone images differed
only in selecting FastLED `WS2811` (800 kHz) or `WS2811_400` (400 kHz).

The 800 kHz result above was the control. The 400 kHz environment was built and
flashed successfully, and its serial startup line confirmed
`timing_khz=400`. In phase A, commanded solid blue displayed as stable white.
At the start of phase B it still displayed white; the user did not report
whether B contained brightness or color jumps.

This is a functional failure: the 400 kHz controller did not produce the
commanded color. It supports treating the installed strip as an 800 kHz decode
family rather than selecting FastLED `WS2811_400` for production. It does not
prove that the present 800 kHz waveform has adequate voltage or timing margin,
and the apparently stable white must not be recorded as a stability pass.
FastLED's controller selection was the intended independent variable, but no
retained waveform verifies the actual pulse widths at GPIO4 or DI.

The 400 kHz candidate is closed. Proceed to the data-interface gate; do not add
400 kHz to the shared backend or repeat effect tests with it.

### Gate 1b result: short T0H partially passed

Before replacing the physical data interface, the standalone timing gate was
built and run as PlatformIO environment
`esp32-s3-gpio4-spi6-cadence-diagnostic`. It is hardware observed on Node 2 /
strip 41 but is not an accepted production backend.

The diagnostic uses GPIO4, exactly 10 groups, an unchanged blue value of 64,
and a 5 MHz SPI clock with six encoded bits per WS2811 data bit:

| WS2811 bit | SPI symbol | High | Low | Total |
|---|---|---:|---:|---:|
| 0 | `100000` | 200 ns | 1000 ns | 1200 ns |
| 1 | `111000` | 600 ns | 600 ns | 1200 ns |

Compared with the failed common 800 kHz-family control, the key independent
variable is the shorter 200 ns T0H. The fixture, data pin, group count, color,
level, power, and data interface must remain unchanged. The image contains only
the two decisive phases:

- A: one physical blue write, then hold for 5 seconds;
- D: the identical blue frame every 33 ms for 200 frames.

Observed result:

- A: groups 2-10 were stable pure blue; DI-side group one did not follow;
- D: groups 2-10 remained stable pure blue for the 33 ms / 200-frame phase;
- final black: did not fully latch, leaving blue residual light.

The repeated-blue result is evidence for the shorter T0H, but the whole-strip
and safe-black requirements failed. The group-one behavior must remain an open
strip41-local first-group or frame-start candidate; it is not proof of a dead
first WS2811, omitted software group, or one specific electrical defect.

### Gate 1c result: explicit low interval passed `0x40` groups 2-10 once

The revised diagnostic forces GPIO4 low for at least 500 us between physical
transactions while retaining the SPI6 5 MHz symbols: T0H 200 ns and T1H 600 ns.
It repeats pure blue every 33 ms in D and repeats black every 33 ms in K.

Onsite observation reported that D and K both matched their expected results.
This remains valid evidence for those exact `0x40` and black patterns on groups
2-10, but the later autonomous `0x25` failure supersedes any interpretation of
this result as a generally passing timing. The user did not explicitly report
the DI-side first group in this run.

### Gate 1d result: `0x40` changing-frame motion passed once

This historical gate kept the SPI6 symbols that had passed the narrow `0x40`
constant-frame observation, at least 500 us inter-transaction low interval,
GPIO4, level, group count, power, and data interface unchanged. The next
standalone image built successfully in 16.80 seconds and was then run onsite.

The image retains SPI6, the 500 us low interval, 10 groups, blue level 64, and
a 33 ms physical-frame period. Each commanded visible state is deliberately
held for six physical frames, approximately 198 ms:

1. E, moving group: exactly one blue group moves from the DI-side first group
   through group 10. There are 300 physical frames, covering five complete
   10-position passes.
2. F, alternating checkerboard: one state lights five blue groups and leaves
   the other five black; the next state swaps odd and even positions. There are
   300 physical frames, with each state held for six frames.

The diagnostic writes black between E and F and again after F.

E passes only if exactly one group is illuminated at every visible step, every
one of the 10 groups participates in order, and no group shows an unintended
color, brightness change, black interruption, skip, or extra illumination. F
passes only if every state contains exactly five blue and five black groups,
the odd/even sets swap cleanly, and there is no unintended color or flash to
black. The separator and final state must be fully black.

Record the DI-side first group explicitly in both phases. Whole-strip timing
acceptance requires all 10 groups to follow; otherwise retain the group-one
issue as a strip41-local/frame-start gate and proceed to a controlled
physical-interface or known-good-strip comparison.

The user reported that E and F passed. This is onsite evidence that these exact
`0x40` changing-frame phases behaved as expected once on strip 41. The report
covers each phase as a whole but did not separately describe DI-side group one.
The later `0x25` rerun failed both spatial phases, so Gate 1d is not production
promotion evidence.

### Gate 1e result: Host-equivalent `0x25` failed autonomously

The autonomous rerun changed the blue channel value from the earlier `0x40` to
`0x25`. The latter matches the quantized channel value produced by the current
Immediate A/B profile for authored color `0.65`, maximum brightness `0.35`, and
gamma `1.30`. It retained GPIO4, 10 groups, SPI6 at 5 MHz, 200/600 ns high
times, 33 ms repeated cadence, and symmetric 313-byte low guards. It did not
contain Wi-Fi, UDP, clock synchronization, Show playback, Python, queues, or
production tasks.

| Phase | Command | Onsite result |
|---|---|---|
| Startup | Black | All 10 groups black |
| A | One blue `0x25` write, hold 5 s | Stable green, therefore functionally wrong |
| A separator | Black | Matched expected black |
| D | Repeat blue `0x25` every 33 ms | Repeatedly jumped among three colors |
| K | Repeat black every 33 ms | Not separately described; no result inferred |
| E | One moving blue group | User described "red in front, black behind" as two adjacent moving groups; a green flash could appear one group later |
| E separator | Black | Not separately described; no result inferred |
| F | Alternating blue/black checkerboard | Groups commanded black displayed red |
| Final | Black | Not separately described; no result inferred |

The DI-side first group was not described separately. The stable green in A
cannot be dismissed as an RGB/GRB red-green swap because blue remains the third
channel in both orders. D, E, and F also demonstrate color and spatial decode
failures from an autonomous, internally fixed data sequence. This gate fails;
do not proceed to effects, UDP presentation, Scheduled timing, Node 8, or
multi-node playback.

### Gate 1f result: replacement SN74 passes single writes, fails cadence

The data interface was replaced with another SN74LVC1T45 while Node 2,
strip 41, GPIO4, 10 groups, power, and SPI6 timing remained the controlled
fixture. The single-write control sent uniform raw channel values without
Host transforms or effect rendering:

| Phase | Raw command | Onsite result |
|---|---|---|
| R | `R=0x25, G=0, B=0` | Correct stable red on all 10 groups |
| Black | All channels zero | All 10 groups black |
| G | `R=0, G=0x25, B=0` | Correct stable green on all 10 groups |
| Black | All channels zero | All 10 groups black |
| B | `R=0, G=0, B=0x25` | Correct stable blue on all 10 groups |
| Final black | All channels zero | All 10 groups black |

The DI-side first group matched the other nine groups throughout this control.
No phase flashed or displayed an unintended color. This is a hardware-observed
single-write functional pass for the replacement-SN74 baseline only.

The same physical path then ran the SPI6 cadence diagnostic at `0x25`:

| Phase | Command | Onsite result |
|---|---|---|
| D | Repeat uniform blue every 33 ms | Flashed red |
| E | One moving blue group, each visible state repeated six frames | Red and blue groups appeared; red was unstable and flashed off |
| F | Alternating blue/black checkerboard | Some groups commanded black displayed red |

A single-write pass and a repeated/dynamic failure are not contradictory. A
single physical write offers one decode opportunity and then leaves the latched
state unchanged. D offers 200 transmission opportunities, while E and F also
exercise changing black/blue group boundaries and repeatedly transmit each
visible state. A marginal pulse or bit boundary can therefore be exposed only
during the cadence phases. Reducing refresh or sending only once would hide
the failure and would not satisfy the 30 FPS production goal.

Gate 1f fails overall. Do not infer that the replacement SN74 fixed the system,
and do not proceed to Show, effects, UDP, Scheduled, or multi-node playback.

### Gate 1g result: standard SPI4 comparison failed

Gate 1g fixed Node 2, strip 41, GPIO4, the replacement SN74LVC1T45, 10 groups,
raw channel level `0x25`, RGB order, power, synchronous SPI submission, and the
single-write plus A/D/K/E/F cadence structure. It changed the WS2811 wire
encoding from SPI6 to the standard 800 kHz-family SPI4 candidate:

| Parameter | Gate 1g value |
|---|---|
| SPI clock | 3.2 MHz |
| Zero symbol | `1000`, T0H 312.5 ns |
| One symbol | `1100`, T1H 625 ns |
| WS2811 bit cell | 1.25 us / 800 kHz |
| Pre-payload low guard | 500 us |
| Post-payload low guard | 500 us |

A parallel implementation task expanded the SPI4 diagnostic to include raw
R/G/B single-write phases before D/K/E/F. This was not silently omitted from
the hardware record: the produced ELF was audited to contain the SPI4 startup
identity and expanded phase sequence, and the flashed image hash was verified
against that build before the onsite run.

The user summarized the complete physical result as: "failed, about the same
as the previous SPI6 run." No more detailed per-phase SPI4 observation was
reported, so none is inferred here. This is sufficient to fail Gate 1g: moving
from SPI6's 833.3 kHz / 200 ns T0H to SPI4's 800 kHz / 312.5 ns T0H did not
restore the required repeated/dynamic behavior on the controlled replacement-
SN74 fixture.

Software timing enumeration stops at this result. Do not proceed to Show,
Immediate, effects, Scheduled, other strips, or multi-node playback. The next
evidence must come from GPIO4/level-shifter-B/DI waveform capture, a standard
AHCT-class data interface with local decoupling and source resistance, or a
controlled known-good-strip cross-test.

### Gate 1h result: change-only 5 FPS emergency effects improved but did not pass

Gate 1h retained Node 2, strip 41, GPIO4, the replacement SN74LVC1T45, the
SPI6 wire path, raw RGB, and exactly 10 configured groups. It deliberately did
not retest 30 FPS cadence. Each new visible state was physically transmitted
once and then held for 200 ms without retransmitting an identical frame, for
an effective maximum state-change rate of 5 FPS.

The autonomous emergency sequence exercised two coarse effects:

- `FLOW`: a single lit group advanced across the strip. The flow was basically
  correct, but the DI-side first group was occasionally red.
- `BREATH`: all 10 groups changed brightness together in coarse steps. It was
  substantially improved over repeated 30 FPS output, but still occasionally
  jumped to an unintended color.

The user judged this a significant improvement and requested continued work
on the emergency-effect direction. Gate 1h is therefore retained as evidence
that avoiding identical physical retransmission materially reduces the visible
failure rate on this fixture.

Gate 1h is **not** a zero-error pass and is **not** a formal repair. The first-
group red event and the breath color jumps are real failures. It does not
validate repeated output, 30 FPS effects, Host/Python playback, Scheduled
presentation, Node 8, multi-node synchronization, or the shared production
backend. It authorizes only a bounded emergency path in which coarse effect
states change no faster than 5 FPS and every unchanged pixel payload remains
latched without another physical WS2811 transaction.

### Gate 1i result: expanded change-only suite remained usable but imperfect

Gate 1i extended the Gate 1h change-only emergency direction. The animation
payload addressed groups 2 through 10, while every commanded frame kept the
DI-side first group black. Unchanged visible states were still held without
retransmitting an identical frame.

The user reported these physical observations:

- `BREATH9` used raw levels `0x04`, `0x08`, `0x10`, and `0x20`. The nine active
  groups completed the observed sequence without a color jump.
- `FLOW` and `SCANNER` remained recognizable. Across each complete loop, the
  user roughly estimated no more than about seven unintended color jumps. This
  count is an onsite visual estimate, not an instrumented measurement.
- `THEATER` produced more unintended color jumps than `FLOW` or `SCANNER`.
- `WIPE` did not appear to jump many times, but an occasional whole-strip pink
  jump was conspicuous.
- Although group 1 was commanded black, each physical state update could leave
  the DI-side first group at a random color or off.

This is still not a zero-error pass and does not validate 30 FPS, Host-driven,
Scheduled, or multi-node playback. It does strengthen the bounded emergency
finding: lower-rate, change-only coarse effects can remain recognizable and
substantially more usable than repeated identical refresh on this fixture. The
user judged the direction worth continuing.

The next controlled A/B changes exactly one effect-payload variable: replace
raw level `0x25` with `0x20`. Keep the node, strip, GPIO, replacement SN74,
SPI6 encoding and guards, group-1-black command, effect states, 200 ms hold,
and change-only transmission policy unchanged.

### Gate 1j result: restricted power-of-two palette passed static and flow

Gate 1j retained the change-only policy, groups 2 through 10 as the animated
region, and group 1 commanded black. It used a restricted warm-color suite
built from power-of-two raw channel values.

The user reported these physical results:

- All five static colors were correct and stable across the nine controlled
  groups.
- `BLUE20_FLOW9` completed with zero observed unintended color jumps.
- `ORANGE_FLOW9`, using raw RGB `(0x20, 0x08, 0x00)`, completed with zero
  observed unintended color jumps.
- `ORANGE_BREATH9` still failed: it could jump to blue or red during the
  brightness sequence.
- The DI-side first group remained in its previous uncontrolled state and did
  not follow the commanded group-1 black payload.
- The final black state was correct for the controlled nine-group region.

This is bounded hardware evidence for the emergency direction: the restricted
palette plus change-only transmission has now passed static and spatial `FLOW`
behavior on groups 2 through 10. It is not a general effect or full-strip pass.
Warm `BREATH` is the only remaining failed behavior in this suite, and the
DI-side first group remains explicitly outside the verified region.

The next candidate keeps raw red fixed at `0x20` and changes only the raw green
channel. Keep every other fixture, encoding, group mask, effect-state, hold,
and transmission-policy variable unchanged.

### Gate 1k result: two-level fixed-red pulse failed twice

Gate 1k narrowed the remaining warm-pulse candidate rather than adding another
effect. It retained Node 2, strip 41, GPIO4, the replacement SN74LVC1T45,
SPI6, exact 10-group payloads, the DI-side first group commanded black, and
one physical write per changed state followed by a 200 ms hold. The animated
region remained physical groups 2 through 10. Raw red stayed at `0x20`, raw
blue stayed at zero, and raw green alternated only between the two
power-of-two values `0x08` and `0x10`.

The two onsite runs both contained an unintended visible event. No zero-error
run of this two-level pulse was recorded. The observation was not
instrumented per directed edge, so this ledger does not assign the event to
`0x08 -> 0x10` or `0x10 -> 0x08`. Gate 1k nevertheless disproves promotion of
the two-level pulse as an accepted emergency effect on this fixture.

This result is a counterexample to endpoint-only reasoning. Selected static
power-of-two colors, `BLUE20_FLOW9`, and `ORANGE_FLOW9` can pass while a short
sequence built from selected power-of-two channel values still fails. A
static payload pass does not validate transitions into or out of that payload.

#### DI-side first group and the second physical group

Commanding the DI-side first group black does not bypass its WS2811 receiver.
The first receiver must still recognize the frame boundary, consume the first
24 data bits, and regenerate the remaining stream on its data output. A local
DI threshold, ground, supply, latch, or regeneration fault can therefore
coexist with an anomaly in the second physical group even though the first
payload slot is always black.

The current observations do not prove that the first group causes every
downstream event. Its visible latch could be faulty while its regenerated data
is correct, or one upstream waveform-margin problem could affect separate
parts of the same frame. Distinguishing those cases requires a retained
waveform at the first receiver input and output, or a controlled physical
bypass of that receiver. A software black value is not such a bypass.

The DI-side first group remains outside even the bounded nine-group emergency
observation. Its uncontrolled state also prevents any full-strip black,
full-strip effect, or safe-state claim.

#### Candidate state graph, not a safe color range

There is no evidence for a continuous safe numeric color range. Adjacent raw
values can have very different serialized bit patterns; for example, `0x20`
is `00100000`, while `0x1f` is `00011111`. Risk may depend on the complete RGB
tuple, channel position, all 10 group payloads, the prior payload, and the
physical transaction rather than numeric brightness alone.

Any further emergency restriction must therefore be described as a candidate
state graph. A node in that graph is one exact post-transform physical
payload. An edge is one explicitly tested directed transition from one exact
payload to the next, including the loop edge from the final state back to the
first state. A list of allowed channel values or colors is insufficient.
Passing graph nodes or edges on this fixture would still be bounded evidence,
not proof that the underlying data path is safe.

The operator APP must not expose a free color picker, arbitrary brightness
slider, arbitrary palette editing, interpolation, or a generic effect editor
for this emergency branch. Those controls can create untested raw values or
directed transitions. The APP may eventually expose only named, exact states
and sequences that have their post-transform payloads and transitions recorded
by a hardware gate. Unknown values must not be silently clamped into another
untested payload.

#### UDP and content-dedupe boundaries

UDP does not inherently improve a physical transaction that already fails in
an autonomous image. It can add packet loss, reordering, session admission,
queue, Host transform, timeout, and reconnect behavior. Its one useful
containment mechanism is node-side dedupe of consecutive identical
post-transform physical payloads.

Dedupe does not remove a write when every 200 ms state differs. It also has no
physical feedback: a permitted payload can be mis-latched while the ESP32
records a successful SPI transaction, after which identical commands are
skipped and the wrong visible state remains. Host-only dedupe is weaker because
a single lost UDP transition may never be applied. Network liveness and pixel
content must remain separate so repeated logical delivery can recover packet
loss without repeating an unchanged WS2811 transaction.

Timeout black and reconnect are not automatically safe. Timeout black is
another unverified physical write, and the first group is already known not to
obey commanded black reliably. Repeating timeout black recreates cadence risk;
reconnect catch-up can create a burst of stale states. A meaningful emergency
UDP gate must use the exact autonomous state graph and raw payload hashes,
prove that physical attempts equal the declared unique transitions plus
explicit startup/final/timeout actions, apply only the latest complete frame
after reconnect, and score the visible result rather than transport health
alone.

#### Gate 1k commitment boundary

Gate 1k is a Node 2 / strip 41 observation only. It does not verify strip 42,
Node 8, another ESP32, another first WS2811 receiver, or multi-node playback.
The emergency branch and the shared production backend remain **NOT HARDWARE
VERIFIED**.

Historical successful static colors and an occasional successful Show run do
not establish a general later software regression. The legacy `main.cpp`
opened each solid-color phase with one physical write followed by a long hold,
which is consistent with the later single-write control. A genuine regression
claim requires the exact earlier firmware binary to pass the same repeated or
changing gate on the unchanged current fixture across repeated runs. Real Host,
protocol, mapping, and GPIO-output defects were fixed during this investigation,
but autonomous failures show that those fixes do not explain away the remaining
physical-output fault.

### Gate 1l software candidate: restricted Immediate UDP state graph

Gate 1l is a software candidate for the next physical A/B, not a hardware
result. It adds the isolated PlatformIO environment
`esp32-s3-node-2-emergency-change-only-ab`, the immediate 5 FPS profile
`ws2811-emergency-node2-strip41.yaml`, and the fixed 110-second Show
`ws2811-emergency-node2-strip41-110s.yaml`. Production environments do not
define the emergency macro.

The Show commands all 10 groups but holds payload group 0 black and targets
effects only to physical groups 2 through 10. Its exact sequence is five
seconds black, 30 seconds of the known-imperfect two-level warm pulse,
five seconds black, 30 seconds of blue single-dot flow, five seconds black,
30 seconds of orange single-dot flow, and five seconds black followed by one
SAFE packet. The pulse is included only because the operator explicitly
accepted rare isolated glitches for this degraded experiment. It remains a
known Gate 1k failure and is not a safe or accepted general effect.

The firmware now classifies the complete 10-group post-transform payload and
admits only this directed graph:

- black may remain black or enter warm-low, blue position 0, or orange
  position 0;
- warm-low and warm-high may remain unchanged, alternate with each other, or
  return to black;
- each single dot may remain at its current position, move forward exactly one
  position including the 8-to-0 loop edge, or return to black;
- SAFE may command only the full black payload.

Different physical payloads less than 150 ms apart are rejected. The Host
still emits logical frames at 5 FPS, but each flow position is repeated twice,
so the planned flow physical change rate is 2.5 FPS. Consecutive identical
payloads still advance sequence and watchdog state without another SPI write.
The first KEY packet of each Host session always writes physically even when
its black payload matches the startup cache.

The cache records only that the backend reported a complete successful SPI
transaction. It does not prove that the strip latched the requested state.
An isolated physical mis-latch can therefore remain visible while duplicate
logical frames are skipped. This design reduces transaction count; it does
not add physical feedback or self-correction.

Unknown frames are rejected before queueing. The exact current behavior is
conditional hold-last, not immediate black: an already admitted state remains
until one second passes without another admitted frame, then the watchdog
attempts black. If admitted and rejected frames are interleaved, admitted
frames continue the watchdog. This policy is acceptable only for the fixed
manual A/B command. It is not an APP safety boundary, and the APP must not
offer this profile as a free-color or free-effect surface.

For the fixed 550 logical packets, the Host-side exact-payload trace contains
168 content transitions and 382 content-identical deliveries. Because the
first matching black packet is a forced KEY write, the firmware candidate
expects 169 Host-triggered physical writes and 381 identical skips. Including
the two startup black writes, the no-error expected `spi_ok` is 171. These are
software predictions only; timeout, retry, recovery, packet loss, or rejection
changes the counters and fails the controlled run.

Software evidence recorded before the physical A/B:

- Host effect and exact UDP payload tests: 50 passed.
- Native firmware protocol/state tests: 49 passed, 0 failed.
- Emergency firmware and the ordinary Node 2 production environment both
  built successfully from the same worktree.
- Final full Python regression after the state-graph tightening: 714 passed.
- Final emergency `firmware.bin`: 730,896 bytes; SHA256
  `1B3B12D3C8BDE2D06B057C114959FF0157BD794CF6A19448FE981B460B718B49`.

#### Gate 1l preliminary onsite result

The first onsite run of the restricted 110-second Immediate UDP Show was
visually much better than the earlier unrestricted effects. The operator
reported that the warm two-level pulse, black intervals, and the rest of the
fixed sequence behaved well. During flow, a lit group could very rarely jump
toward the DI end and appear in an unintended color. No exact event count or
final frame-550 serial line was supplied with this first report, so it is not
a formal zero-error pass.

The supplied frame-526 checkpoint was internally exact: `received=526`,
`queued=526`, `attempts=526`, `refresh_ok=526`,
`identical_skipped=357`, and `spi_ok=171`. All reject, gap, timeout, output,
invariant, rollback, hash-mismatch, and uniform-mismatch counters were zero.
Frame 526 is the transition into the final black interval, so all planned
physical writes have completed by that point. The remaining 25 logical black
deliveries, including exit SAFE, should change only `identical_skipped` from
357 to 381 and `safe_frames` from 0 to 1. This checkpoint strongly validates
the software transaction budget but does not erase the observed physical
flow glitch.

This result supports the emergency containment strategy: exact sparse raw
values, identity Host transform, discrete state changes, repeated logical
delivery, node-side identical-content suppression, a directed transition
graph, and a physical flow change rate of 2.5 FPS. It does not identify a safe
numeric color range and does not disprove the remaining physical link fault.
The rare spatial/color event is direct evidence that even an admitted graph
edge can still be mis-latched by the real strip.

Further effects and colors should extend this state graph one bounded family
at a time. Reuse already admitted payloads first to test new spatial edges;
then add exact sparse-bit color tuples while retaining the same spatial graph.
Do not change spatial pattern, palette, cadence, and transition policy in one
gate. Free RGB, interpolation, arbitrary brightness, and general APP control
remain outside the evidence.

The two new effects are registered reusable Host effects and accept authored
parameters. The fixed profile does not cryptographically bind the fixed Show,
and no APP policy has been implemented. Firmware payload and transition checks
are the last defense, not proof that arbitrary APP control is available.

### Gate 1m software candidate: Blue20 mask and Green20 channel controls

Gate 1m is the next bounded physical A/B candidate. It retains the Gate 1l
Node 2, strip 41, GPIO4, replacement SN74, SPI6 backend, exact 10-group frame,
group-0 black command, identity Host transform, 5 FPS logical delivery,
150 ms firmware minimum interval, and two logical deliveries per dynamic
state. It does not add reverse motion, free masks, interpolation, or arbitrary
colors.

The fixed 120-second Show is:

- 0-5 seconds: black;
- 5-25: admitted Blue20 forward single-dot control;
- 25-30: black;
- 30-50: new Blue20 three-phase theater mask;
- 50-55: black;
- 55-60: new uniform Green20 static hold;
- 60-65: black;
- 65-85: new Green20 forward single-dot using the admitted spatial graph;
- 85-90: black;
- 90-110: admitted Orange20_08 forward single-dot control;
- 110-120: black, followed by one SAFE packet.

The new theater node has exactly three Blue20 groups: usable path positions
whose index modulo three equals the phase. Its only non-black directed edges
are phase 0 to 1, 1 to 2, and 2 to 0, with unchanged duplicates allowed.
Green20 uniform may only enter from black, remain unchanged, and return to
black. Green20 single-dot may only enter at position 0, remain unchanged,
advance by one position including the 8-to-0 loop, and return to black.
Adding Green20 does not authorize any other green value or mixed color.

The real Engine trace is 599 ordinary rendered packets plus one SAFE packet,
600 total. It contains 206 content transitions and 394 content-identical
deliveries. The initial matching KEY forces one additional physical write, so
the no-error prediction is 207 Host-triggered writes, 393 identical skips, and
`spi_ok=209` after the two startup black writes. Final expected counters are
`received=queued=attempts=refresh_ok=last_rx=last_commit=600`,
`identical_skipped=393`, `spi_ok=209`, and `safe_frames=1`, with every reject,
gap, overwrite, timeout, output, invariant, hash, and uniform mismatch counter
at zero.

Software evidence before this A/B:

- exact Host/effect/UDP targeted tests: 54 passed;
- native firmware payload/edge tests: 50 passed, 0 failed;
- final full Python regression: 718 passed;
- emergency and ordinary Node 2 firmware environments both built successfully;
- Gate 1m emergency `firmware.bin`: 731,328 bytes, SHA256
  `C47760A6B33A36B1CB4D67AF3A380742B93C7701036B02B45A501FA6881AE420`.

The physical comparison remains asymmetric by design. Blue20 forward and
Orange20_08 forward are controls. Blue20 theater changes only the spatial
mask. Green20 static isolates the new channel tuple before Green20 reuses the
forward single-dot graph. A theater-only increase in errors implicates the
multi-point mask; a Green-only increase implicates the new channel tuple.
Rare events shared by all single-dot controls remain evidence of the common
physical link. No short run can promote any node or edge to a safe palette.

#### Gate 1m preliminary onsite result

The operator ran Gate 1m several times. Later runs became very stable, and the
last reported run was visually perfect. No matching final frame-600 serial
line or fixed-camera event count accompanied this report. Record it as a
promising repeated-run observation, not proof of burn-in, learning, network
warm-up, or a repaired physical link. WS2811 receivers and the current
firmware have no adaptation mechanism that would justify such a causal claim.

The run-to-run improvement may reflect uncontrolled startup state, power or
ground settling, connector contact, first-receiver state, observation
sampling, or chance. The earlier Gate 1l rare wrong-position/wrong-color event
remains valid counterevidence. The next synchronized investigation should
retain the same binary and fixture, capture every run from power application,
and pair the video with the final serial counters before changing code.

### Gate 1n software candidate: Node 8 and staged two-node Immediate

Gate 1n begins the one-ESP-per-strip expansion. The emergency implementation
no longer contains a runtime Node 2 / 10-group assumption. Each PlatformIO
environment still compiles exactly one node ID and one output descriptor:
Node 2 accepts only output 1 / GPIO4 / 10 groups, while Node 8 accepts only
output 1 / GPIO4 / 20 groups. This is compile-time reuse, not a firmware image
that accepts either topology.

The complete payload classifier keeps group 0 black and derives the usable
path from groups 1 through `pixel_count - 1`. Node 2 therefore has nine usable
positions and Node 8 has nineteen. Single-dot wrap is 8-to-0 or 18-to-0,
respectively. The three-phase Blue20 theater mask is matched pixel by pixel;
Node 2 has 3/3/3 lit groups, while Node 8 has 7/6/6. Native tests explicitly
reject Node 8 packets with the Node 2 descriptor and Node 8 descriptors with
19 rather than 20 groups.

Node 8 must pass alone before any two-node effect run. Its fixed 60-second
Blue20 gate is 0-5 black, 5-45 one-dot forward at 2.5 physical states per
second, and 45-60 black followed by SAFE. The real Engine contract is 299
ordinary rendered frames plus SAFE: 300 logical packets, 102 Host-triggered
physical writes including KEY, 198 identical skips, and `spi_ok=104` after two startup black
writes. All reject, gap, overwrite, timeout, and error counters must be zero.

Only after the Node 8 gate passes does the staged 110-second two-node gate run:

- 0-5 seconds: both black;
- 5-35: Node 2 Blue20 flow, Node 8 receives admitted black heartbeats;
- 35-40: both black;
- 40-70: Node 8 Blue20 flow, Node 2 receives admitted black heartbeats;
- 70-75: both black;
- 75-105: both Blue20 flow at the same absolute 2.5 positions per second;
- 105-110: both black followed by SAFE.

The Host owns 550 logical frames and sends 1,100 UDP packets. Each ESP is
scored independently and should report 550 received/queued/attempted/committed
frames, 397 identical skips, `spi_ok=155`, `safe_frames=1`, and zero reject,
gap, timeout, and error counters. The two strip lengths wrap at different
times; that is expected. Immediate mode can prove shared sequence and bounded
visible skew, not strict simultaneous apply.

Software evidence before Node 8 hardware work:

- final full Python regression: 724 passed;
- exact Node 8 and two-node Host UDP tests: 8 passed;
- native firmware protocol/topology/state tests: 51 passed, 0 failed;
- Node 2/Node 8 emergency and ordinary production environments: four builds
  succeeded;
- new generic-policy Node 2 candidate: 731,408 bytes, SHA256
  `0D475E07DDD9C143015B6A89FCF1370DE1141F926FBAD76D69D570E3F4AA9D5C`;
- Node 8 exact-20 candidate: 731,408 bytes, SHA256
  `86AF165BBC4F29F09AEC21A05A03FB5805B2EE2C9D89511AFFA289999B944329`.

The Node 8 exact-20 candidate was flashed on COM13 and ran the 60-second Blue20
gate on strip 42. The operator reported basically correct motion with only
extremely rare jumps. Final counters matched the corrected Engine contract
exactly: `received=queued=attempts=refresh_ok=300`,
`identical_skipped=198`, `spi_ok=104`, and `safe_frames=1`; every reject, gap,
overwrite, timeout, output, invariant, hash, and uniform mismatch counter was
zero. This is a promising fixture observation, not a zero-event hardware pass.

Strip 41 was also powered and lit during this Node 8-only run. Network checks
at that time reached Node 8 at `.208` but not Node 2 at `.202`; the Node 8-only
profile sends no packets to `.202`. The operator reports that the Node 2 ESP32
was powered; the failed ping therefore does not prove that the board was
powered off or that its firmware was not running. With no new Host frame,
strip 41 can retain its prior/undefined latched state. In particular, a Node 2
startup-black transaction sent before strip 41 receives power is not replayed
continuously and cannot clear the later-powered strip. The observation does
not prove cross-route coupling. The
operator confirmed that strip 41 stayed fixed and did not follow strip 42's
motion, so there is no visual evidence of cross-route coupling in this run.
This initial observation was superseded by the directed isolation test below.

#### Gate 1n powered two-node isolation result: failed

Node 8 was then flashed on COM13 with the guarded-SPI4 emergency candidate:
729,056 bytes, SHA256
`84DF511C0DA64EEFCF9038AF61854B68AA9D166FDFD01E68D1D0EDC314E15D88`.
The upload identified MAC `28:84:85:8A:36:B0`, wrote the complete image, and
verified every flashed segment. Node 2 remained on the earlier Gate 1m SPI6
image. The following observations were made with both ESP32 boards and both
strips powered:

1. The three-second Node 2 black sentinel made strip 41 black as intended.
2. Starting the Node 8-only strip-42 Show made strip 41 become white.
3. Pressing Node 2 RST made strip 41 black and strip 42 white. Pressing the
   other controller's RST produced the reciprocal result: its own strip went
   black while the other strip went white.
4. While the Node 8 Show was running, another Node 2 black sentinel made strip
   41 turn off briefly. At exactly that transition, strip 42 changed to white
   for exactly ten groups beginning at its DI end.

The ten-group boundary is a high-information fingerprint because Node 2 emits
an exact ten-group transaction while Node 8 is compiled for twenty groups.
The observed white does not mean that the Host commanded white: colliding or
degraded zero symbols can be mis-latched as one bits. The directed response to
a physical RST also exists without a Host routing decision. These observations
fail the one-ESP/one-strip electrical-isolation gate and are much more specific
than the earlier undirected fixed-light observation.

The checked-in software route does not send either single-node Show to both
nodes. The Node 2 profile contains only node 2 / `.202:9001` / GPIO4 / ten
groups. The Node 8 profile contains only node 8 / `.208:9001` / GPIO4 / twenty
groups. `PhysicalMapping` creates only that configured digital node, UDP v3
sends unicast to the frame's host, and firmware rejects the wrong node ID or
output descriptor. Host endpoint-contract tests cover the Node 2 sentinel and
Node 8-only Show, and the full 726-test suite passed. A leftover second Host
process must still be excluded from the live machine, but it cannot explain
why pressing one board's RST changes the other physical strip.

The leading hardware hypotheses, not yet continuity- or scope-verified, are:

1. the two SN74LVC1T45 B outputs, green DI wires, terminal rows, or strip DI
   connectors are accidentally connected or coupled strongly enough to decode;
2. A/GPIO nets are connected, or one translator/strip ground is open or high
   resistance and data current returns through the other signal path;
3. shared 5 V, 3.3 V, USB back-power, or ground transients disturb the other
   translator. This ranks below a data-path connection because it does not by
   itself explain the exact ten-group boundary.

A perfect hard tie between two B outputs would normally cause severe
push-pull contention, while Node 8 can still look mostly correct. The open
possibility is therefore broader than a zero-ohm short: a shared terminal or
breadboard row, partial/contaminated connection, close coupled lines, a weak
ground reference, translator-rail bounce, or USB/XL4015 back-power can inject
enough of the finite ten-group burst for the other DIN to misdecode it.

SN74LVC1T45 B is a push-pull output, not a wired bus. If two B outputs are tied,
simultaneous drive causes source/sink contention and risks device damage. Stop
all simultaneous two-output Shows until the physical isolation check passes.
With all 24 V, 5 V, and USB power removed, continuity should exist between
grounds but not between B1/B2, DI41/DI42, A1/A2, GPIO4-Node2/GPIO4-Node8, or the
two boards' separately regulated 3.3 V rails. The minimum powered A/B then
disconnects and insulates one translator B-to-DI lead at the B output before
power is restored. Any other-strip response to the disconnected controller's
RST or Show is an immediate stop condition.

For a final software/electrical discriminator after wiring is safe, record
both serial baselines, run only the Node 2 black sentinel, and compare deltas.
Node 2 should add 15 received/queued/attempted/committed logical frames,
14 identical skips, one SPI transaction, and one SAFE frame. Node 8 must add
zero received, rejected, queued, attempted, committed, or SPI counters. If
strip 42 changes while Node 8 `received` remains unchanged, the change is
electrical rather than a Host command.

#### Unpowered continuity result

The operator removed all power and checked the first three requested pairs.
With the strip power wiring still connected, B1-to-B2, the two strip green DI
leads, and A1-to-A2 all triggered the meter's continuity indication. After the
strip power leads were disconnected, A1-to-A2, B1-to-B2, and the two strip DI
leads all measured `OL` in both directions.

This result argues against a permanent direct copper short or shared breadboard
row between the converter A pins or between the converter B pins. The indicated
path depends on the connected strip/power network. It therefore raises the
priority of a path through strip input protection structures, common 24 V/GND,
a weak/open signal return, or rail/back-power coupling. It does not yet prove a
low-ohm power fault: a continuity buzzer can also trigger through semiconductor
junctions, so resistance in both probe directions or diode-mode readings would
be needed to classify the passive path. The next powered test must retain only
one connected B-to-DI data path and must not restore simultaneous push-pull
drive.

The operator then isolated the two power rails while keeping all supplies
disconnected. With only the two strip GND/white leads common, DI41-to-DI42 did
not trigger continuity and measured `OL`. With only the two 24V+/red leads
common, it also did not trigger and measured `OL`. The previously indicated
path therefore requires both strip power rails and the complete unpowered strip
circuits to be connected. This further rejects a direct short through either
single supply conductor, but it does not establish whether the complete path is
benign input protection or the path responsible for powered interference.

In the first powered one-data-path A/B, Node 8 B was disconnected and insulated,
strip 42's lamp-side DI was held at its own GND, and only Node 2 B remained
connected to strip 41 DI. The Node 2 black-sentinel run caused no visible
synchronous response during execution. Pressing either ESP32's RST also caused
no cross-strip response in this isolated arrangement. Strip 42 did light after
the Host command had completed, so the run is not a clean end-state pass; the
relationship of that delayed event to exit SAFE, later firmware timeout, or an
unrelated power-up latch was not instrumented.

The disappearance of the immediate reciprocal RST response is the stronger
directed result: the prior cross-strip response requires both B-to-DI data
branches to be connected. Shared supply alone did not reproduce it while one
data branch was isolated and held low. This moves simultaneous data-branch
coupling, translator/strip input interaction, or output contention back above a
standalone common-supply transient. A reverse one-data-path A/B is required
before either branch can be called independently safe.

The two strips retain their intended parallel 24V+/GND supply connection during
these powered A/B tests. Before disconnecting one data branch, the operator
also checked the two SN74 B endpoints with the parallel strip power wiring in
place and reported them open. Provided this measurement was made with all
supplies removed, it further excludes a DC hard tie between the B outputs.
Parallel strip power is not itself a wiring violation; the remaining candidates
are dynamic and need not appear in a continuity test.

The reverse one-data-path A/B then disconnected Node 2 B from strip 41, held
strip 41 DI low at its own GND, and connected only Node 8 B to strip 42. Strip
41 remained black throughout. Node 2 RST affected neither strip, while Node 8
RST affected only its own strip 42. This passes the reverse cross-route
isolation observation and matches the first direction: with only one B-to-DI
branch connected, neither controller immediately changes the other strip.

Strip 42's guarded-SPI4 playback was subjectively less stable than its earlier
run. No event count or serial trace accompanied this comparison, so it is not a
quantified regression, but it is direct counterevidence to any claim that
moving the source waveform inside the quoted WS2811 timing window repaired the
physical link. Single-strip stability and dual-branch coupling remain separate
open failures.

The one-path A/B also removed both USB connections, while the original dual
test used serial monitoring. Data-branch count and USB/back-power were therefore
changed together. The next shortest discriminator restores both B-to-DI paths
but keeps both USB cables absent and powers both ESP32 boards only from XL4015.
Short Node 2 and Node 8 black sentinels must precede any effect. Any other-strip
response immediately fails this no-USB dual-path gate and stops the test.

The no-USB dual-path gate reproduced the reciprocal failure exactly. With both
independent B-to-DI leads restored, parallel strip power retained, both ESP32
boards powered only by XL4015, and both USB cables absent:

- Node 2 black made strip 41 black and strip 42 light;
- Node 8 black made strip 42 black and strip 41 light;
- Node 2 RST made strip 41 black and strip 42 light;
- Node 8 RST made strip 42 black and strip 41 light.

The operator again measured the two SN74 B endpoints open with power removed.
This fails the no-USB gate, excludes USB back-power as a necessary cause, and
confirms that DC continuity between B outputs is not required. Combined with
both passing one-data-path directions, the interference requires both data
branches to be physically connected and active in the complete powered system.

The complementary black/white result is consistent with a coupled or
reference-shifted zero-symbol waveform being decoded as one bits on the other
DIN. This is an interpretation, not a captured waveform. Leading mechanisms
are capacitive/inductive coupling between fast 5 V data edges, common-ground
bounce, or translator VCCB interaction. Host routing, USB, and a zero-ohm B-to-B
short no longer explain the evidence. The immediate component-free A/B is to
physically separate and shorten both data runs, keep each beside its own local
ground return, and separate the translator modules before repeating only the
two black sentinels.

### Shared production promotion status: withdrawn

Before the specification audit, the shared one-output GPIO4 production and
emergency backends used SPI6 timing: 5 MHz, `0=100000`, `1=111000`, and
symmetric 313-byte low guards. The user supplied a complete eight-page
Worldsemi WS2811 V2.1 PDF. It gives T0H 220-380 ns, T1H/T0L/T1L 580-1000 ns,
reset at least 280 us, and RGB/MSB-first transmission. The PDF has not been
independently retrieved from the manufacturer, and the installed strip has not
been proved to contain that exact die revision. Against this document, SPI6
has one definite source-timing
violation: its 200 ns T0H is below the 220 ns minimum. T0L at 1000 ns, T1H/T1L
at 600 ns, and the 500.8 us guards are inside the quoted limits. Software tests
and firmware builds do not make it a physical fix. Gate 1e failed with the
same timing and guard candidate before
networking was introduced, and Gate 1f still failed repeated/dynamic cadence
after the SN74 replacement despite a clean single-write RGB control. The
controlled SPI4 comparison in Gate 1g used 3.2 MHz `1000/1100`, nominal
312.5/937.5 ns for zero and 625/625 ns for one, plus 500 us guards. It is fully
inside the quoted excerpt yet also failed. Therefore SPI6 must be withdrawn as
a compliant production candidate, while switching to guarded SPI4 is only a
deterministic compliance correction, not proof that the physical corruption
is fixed.

The source candidate now uses the existing SPI4 symbols through a dedicated
fixed-GPIO4 encoder with symmetric 200-byte guards at 3.2 MHz, exactly 500 us
low on each side. Generic SPI4 retains its historical 32-byte guards, and SPI6
remains available only in explicitly named diagnostic environments. Startup
identity reports `spi4_dma_fixed_gpio4_500us_candidate_not_hardware_verified`,
4 bits per WS bit, `zero=1000`, and `one=1100`. Four Node 2/Node 8 production
and emergency builds succeeded; native firmware tests passed 52/52 and the
full Python suite passed 726 tests. New emergency binaries are:

- Node 2: 729,056 bytes, SHA256
  `F8DFC50B629409E191FEE8E3D60B7F7908970D1A454AA50A68B7FA7A6EBE3A52`;
- Node 8: 729,056 bytes, SHA256
  `84DF511C0DA64EEFCF9038AF61854B68AA9D166FDFD01E68D1D0EDC314E15D88`.

Node 2 still carries its earlier SPI6 emergency image. Node 8 now carries the
guarded-SPI4 image above, but the powered two-node isolation gate failed. The
candidate therefore remains **NOT HARDWARE VERIFIED** and no production or
multi-node promotion is allowed.

### 2026-07-17 version-control incident and recovered baseline

For a known-good-strip comparison, Node 2 was first flashed with the standalone
SPI6 RGB single-write diagnostic and then, incorrectly, with
`esp32-s3-gpio4-spi6-cadence-diagnostic`. The latter repeats unchanged payloads
every 33 ms in its D phase and is an already documented failure mode. Both the
original 5 m strip and strip 41 showed substantially more jumps under that
image. This result is invalid as a comparison of strip quality and does not
show that either strip regressed. Do not use any cadence environment as a Show
or emergency-path substitute.

The operator then supplied `<operator-downloads>\firmware.bin`. Its exact
identity is 731,328 bytes and SHA256
`C47760A6B33A36B1CB4D67AF3A380742B93C7701036B02B45A501FA6881AE420`, matching
the previously recorded best Node 2 Gate 1m image. Embedded strings confirm
`spi6_dma_fixed_gpio4`, 5 MHz six-bit symbols, 500 us reset low, Immediate,
emergency change-only, exact 10 groups, and group 0 black. It is neither the
cadence diagnostic nor the guarded-SPI4 candidate.

The only discovered copy was preserved byte-for-byte at
`firmware/esp32_ws2811_node/baselines/node2-gate1m-spi6-c477/firmware.bin`.
The current source tree no longer rebuilds this exact image: the historically
named `esp32-s3-node-2-emergency-change-only-ab` environment now selects
guarded SPI4. Restoring the onsite baseline therefore requires verifying the
C477 hash and flashing the preserved binary directly. The recovered image
remains an emergency investigation baseline, **NOT HARDWARE VERIFIED** and not
datasheet-compliant under the user-provided V2.1 timing excerpt.

After C477 was restored, PlatformIO monitor again displayed only
`Reconnecting ... Connected!` followed by the first periodic stats line. The
cause is deterministic in the source: `setup()` called `Serial.begin()`,
waited only 200 ms, printed the complete identity once, and never replayed it.
ESP32-S3 USB CDC re-enumeration on Windows can take longer than 200 ms, so the
monitor cannot recover those discarded bytes. This missing banner does not
invalidate a matching flash hash and successful Gate counters.

Current source images retain the immediate print and add a non-blocking replay
when `Serial` first reports a connected monitor. They also make one fallback
replay immediately before the first 5-second stats line when the connection
state has not been observed. There is no `while (!Serial)`, no extra startup
delay, and no LED refresh. Focused tests passed 7/7, the full Python suite
passed 727 tests, and both Node 2 and Node 8 emergency SPI4 candidates built.
This repair is source-verified but **NOT HARDWARE VERIFIED**. It is not present
in the preserved C477 binary, which must not be replaced solely to improve
serial logging.

### 2026-07-17 repeated Gate 1m color and group-boundary failure

After the C477 baseline was restored, repeated Gate 1m runs eventually failed
on both strip 41 and the original 5 m strip when each was tested on the same
Node 2 / GPIO4 / translator chain. One run changed commanded Blue20 into
green. Its Orange20_08 moving point appeared as adjacent red and blue groups.
The byte pattern is diagnostic: Blue20 is `00 00 20`; losing the first zero
byte and regrouping yields `00 20 00` green. An isolated orange point
`20 08 00` preceded by black then regroups as `00 00 20` blue in one group and
`08 00 00` red in the next. RGB/GRB selection cannot produce this spatial
split. The observation is consistent with an eight-WS-bit frame-phase slip
after Host payload construction.

A later run after an ESP RST still produced visible wrong colors but not
exactly the same pattern. The operator clarified that this was the RST-only
run; the full cold-power test had not yet been performed. The RST result
broadens the failure from one fixed byte offset to an unstable bit/byte
boundary and excludes stale ESP runtime state as a sufficient explanation.
The common path, not strip 41 alone, is implicated. The
remaining boundary includes the SPI signal after the verified DMA buffer,
GPIO4, translator supply/output, data/ground return, strip DI, and the first
WS2811 receiver/regenerator.

The attached COM7 interval covered uptime 75,073 through 130,131 ms and
sequence 281 through 555. Its exact deltas were:

```text
received/queued/attempts/refresh_ok: +274
identical_skipped: +171
spi_ok/encoded_hash_checks: +103
last_rx/last_commit: +274
171 skipped + 103 physical writes = 274 accepted logical frames
```

All encoded mismatches, uniform mismatches, output errors, invariant errors,
timeouts, queue overwrites, and receive gaps remained zero. Two emergency
rejections and one display gap were already present in the first captured line
and did not increase during the interval. The trace starts mid-run and ends at
sequence 555, so it is not a complete Gate acceptance record. It does prove
that the captured visual corruption can coexist with exact Host-to-buffer
accounting and successful SPI driver return codes.

The RST-only Gate failed. A subsequent run was initially described as a cold
power cycle, but its first captured uptime was 360,308 ms. USB had kept Node 2
powered, so that run reset only the strip 24 V domain and possibly not the
translator 5 V domain. It must be labeled `strip-power-cycle / original-5m /
C477`, not full cold.

The strip-power-cycle trace again matched the Show exactly. Sequence 209
through 584 contained 375 logical frames; the model requires 125 physical
writes and 250 identical skips, and the trace reported exactly those deltas
with zero new errors or mismatches. It ended before sequence 600, so the final
SAFE result still requires the last line and visual black confirmation.

The next single-variable gate is a true all-rail cold start. Stop all Host
senders, unplug USB, switch off 24 V, verify all board lights are off and `.202`
is unreachable, and wait at least 30 seconds. Keep USB disconnected, restore
only 24 V so XL4015 starts the ESP, translator, and strip together, wait for
`.202`, and run Gate 1m over Wi-Fi. Connect USB only after the Show to collect
stats without intentionally resetting the board. Do not change SPI timing,
translator, cable, or Show. A visible phase slip is a hardware gate failure
even when all software counters are exact.

The formal installed production profiles still specify a 20 ms apply lead,
500 ms runtime beacon interval, and five startup beacons 10 ms apart. The
successful robust Node 2 Scheduled A/B instead used a 60 ms lead, 100 ms beacon
interval, and 32 startup beacons 50 ms apart. Reconciliation is paused until a
single-strip autonomous physical-output gate passes. Do not change those
parameters, run effects, or claim the installed profile passed merely because
the earlier `0x40` E/F gate passed once.

### Current minimum conclusion and paused work

The failure boundary is downstream of effect authoring and does not require a
network runtime. The replacement-SN74 path proves that SPI6 can transmit one
correct raw `0x25` RGB frame to all 10 groups, but repeated and spatially
changing frames still corrupt color and black-group state. The remaining
boundary is repeated physical transmission, especially SPI6 pulse margin, and
the GPIO4-to-level-shifter-B-to-DI waveform.

The single allowed SPI4 timing comparison retained the replacement SN74,
GPIO4, 10 groups, `0x25`, RGB order, RGB single writes, A/D/K/E/F content,
33 ms cadence, synchronous buffer lifetime, and 500 us pre/post guards. It
failed about the same as SPI6. There is no remaining software timing gate.

Gates 1h through 1k add a separate emergency observation, not a cadence
acceptance result. Change-only restricted static and FLOW payloads can be much
more usable when each changed state is written once and held for 200 ms, but
BREATH and even the two-level fixed-red pulse still fail. The DI-side first
group remains uncontrolled. This direction is therefore an explicitly
degraded, non-production experiment, not a safe palette or general effect
surface.

The next evidence must be one controlled physical-boundary action:

1. Capture the same failing frame at GPIO4, replacement-SN74 B, and strip DI.
2. Replace the data interface with a standard 74AHCT125/74HCT125-class buffer,
   local 100 nF decoupling, a 220-330 ohm source resistor, and a short
   data/ground pair, then rerun the existing cadence gate without changing
   firmware.
3. Cross-test the unchanged node/interface with a known-good strip, or the
   unchanged strip with a known-good accepted driver, changing only one side.

Until this repeated/dynamic gate passes, pause general effect and Python
mapping expansion, Scheduled presentation, full-node synchronization,
production deployment, and all further blind software timing enumeration.
The only active exception is the bounded 5 FPS change-only emergency path on
exact compiled node topologies. Node 8 has completed a promising single-strip
run, but the powered-strip-41 observation requires the powered-black isolation
gate above before the staged two-node Show. No result here establishes a safe
color range, free APP control, 30 FPS, strict synchronization, or cross-node
production reuse.

### Gate 2: data interface

The engineering candidate, not a hardware-verified solution, is a 5 V
74AHCT125/74HCT125-class unidirectional buffer, 100 nF local decoupling, a
220-330 ohm source resistor, and a short data/ground pair. The controlled
SN74LVC1T45 replacement has already improved single-write behavior without
passing cadence, so do not repeat another uncontrolled module swap.

- SPI4 was still unstable, so capture GPIO4 A-side, level-shifter B-side, and
  strip DI waveforms, move to the AHCT-class interface above, or perform the
  controlled known-good-strip cross-test. Do not infer a repair from another
  single-write success.

For a genuine V2.1 part in its specified `VDD=4.5-5.5 V` range, 3.3 V
nominally satisfies `VIH >= 0.55*VDD`; at 5.5 V the threshold is 3.025 V.
Direct-drive failure is still ambiguous because DIN voltage at the receiver,
ground bounce, edge quality, and the actual installed die remain unmeasured.

## Reusable acceptance path

Each ESP/strip pair must pass these gates with only node ID, endpoint, group
count, and verified color order changing between nodes:

1. Autonomous repeated identical frame at 33 ms.
2. Autonomous alternating fixed frames at 33 ms.
3. Autonomous one-group moving frame at 33 ms.
4. UDP Immediate static and dynamic frames at 30 FPS.
5. UDP Scheduled static and dynamic frames at 30 FPS.
6. Two-node, then full multi-node, scheduled-boundary playback.

The final autonomous acceptance target is at least five minutes / 9000 frames
with zero unintended color, brightness, black, freeze, or spatial events. The
DI-side first group must be scored separately if it diverges again.

## Temporary artifacts and cleanup

Temporary investigation assets currently include:

- `firmware/esp32_ws2811_node/src/cadence_diagnostic.cpp`
- `firmware/esp32_ws2811_node/src/cadence_spi6_diagnostic.cpp`
- PlatformIO environment `esp32-s3-gpio4-cadence-diagnostic`
- PlatformIO environment `esp32-s3-gpio4-cadence-400khz-diagnostic`
- PlatformIO environment `esp32-s3-gpio4-spi6-cadence-diagnostic`
- PlatformIO environment `esp32-s3-gpio4-spi4-cadence-diagnostic`
- PlatformIO environment `esp32-s3-gpio4-spi6-rgb-static-diagnostic`
- PlatformIO environment `esp32-s3-node-2-fixed-gpio4-presentation-ab`
- PlatformIO environment `esp32-s3-node-2-fastled-gpio4-immediate-ab`
- the `LIGHT_BELT_FASTLED_GPIO4_IMMEDIATE_AB`-only branches in the FastLED
  backend, `LedOutput`, and startup identity code
- `config/profiles/ws2811-ab-node2-strip41-immediate.yaml`
- `config/profiles/ws2811-ab-node2-strip41-scheduled-robust.yaml`
- `config/shows/ws2811-ab-strip41-blue-10s.yaml`
- `config/shows/ws2811-ab-strip41-rgb-static-steps.yaml`
- `scripts/monitor_esp32_stats.py`
- their ignored environment-specific `.pio/build/...` outputs

Do not clean these before the production Scheduled P1 and any required
data-interface A/B are recorded. After the final production backend is
selected, remove the standalone sources, A/B environments, A/B profiles/shows,
monitor helper if it has not become an approved operator tool, macro-only A/B
branches, and ignored builds. Do not remove shared session, clock, or
frame-state repairs merely
because the same files contain an A/B branch. Rebuild the selected production
environments after cleanup so no acceptance result depends on a stale A/B
binary. Preserve this evidence ledger and the final verified timing/interface
decision. Keep all temporary and build artifacts on drive A; do not recreate
them under a C-drive cache.

## New observation template

Record every additional hardware result in this form:

```text
Date/time:
Firmware environment and binary:
ESP / COM / IP:
Strip / group count:
Only changed variable:
Power and wiring state:
Expected phases:
Observed phases, including DI first group:
Serial counters or labels:
Conclusion supported:
Conclusion not supported:
Next action:
```
