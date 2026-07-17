# Current Implementation Plan

Status: **Phase 31 topology and scheduled-presentation software accepted on
2026-07-16; physical acceptance remains NOT HARDWARE VERIFIED**.

Product implementation Phases 0-29 are complete. Their original approved plan
is preserved at
`docs/history/implementation/implementation-plan-phases-0-29.md` and is no
longer an active instruction source. Phases 30 and 31 are complete. No later
implementation phase is currently approved.

## Phase 31: One ESP32 per WS2811 strip

Replace the provisional five-controller, multi-output production topology with
one ESP32-S3 per physical WS2811 strip. The complete target has 13 digital
nodes; every production node has exactly one output, `output_id: 1`, on GPIO4.

| Node | Logical strip | Groups | Output | GPIO | Site IPv4 |
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

The current field subset is exactly nodes `1`, `2`, `4`, `5`, `6`, `7`, `8`,
`9`, and `10`, covering nine installed strips. Nodes `3`, `11`, `12`, and `13`
remain part of the complete target but must not be represented as connected in
the nine-node field profile.

The table's IPv4 values are the site contract. The complete site profile
`cabin-lighting-v3-site-local.yaml` and the nine-node field profile implement
those addresses. The generic `cabin-lighting-v3-production.yaml` remains an
offline production-shape template with non-routable `192.0.2.x` TEST-NET
endpoints and `REPLACE_WITH_RS485_PORT`; preserving that explicit failure
boundary is not a different site allocation.

All physical assignments and observed behavior remain **NOT HARDWARE
VERIFIED** until recorded against real hardware.

Phase 31 production packets share logical sequence, media timestamp, and one
Host-monotonic `apply_at_us` 20 ms in the future. The Host emits broadcast
clock beacons; firmware estimates the local-minus-Host offset from the minimum
sample in a bounded window, prepares the frame before its deadline, and
subtracts the complete 3.2 MHz four-bit SPI wire time from the common
latch-completion deadline. The fixed GPIO4 production candidate encodes
`0=1000` and `1=1100` with 500 us low guards before and after the payload. The
complete durations are 1300 us for 10 groups, 1600 us for 20 groups, and 2200
us for 40 groups. The candidate remains **NOT HARDWARE VERIFIED**.
Production node images require scheduled frames;
explicit legacy diagnostic images remain immediate.

For a scheduled session start, Host encodes every target node before the first
send and transmits three complete rounds 2 ms apart. Each node receives the
same raw KEY packet and all packets retain one apply/media identity. Firmware
deduplicates that identity without creating extra session generations. A fully
prepared KEY admits its generation; a later timed-output failure rolls back
physically while the next complete scheduled frame remains able to recover.
The output loop checks safe timeout before each queue pass. Scheduled SPI
failure is rolled back and is not blindly retried after its validated start
deadline.

This scheduling contract is implemented in software. It is not evidence of
actual simultaneous light output: powered cross-node latch skew remains **NOT
HARDWARE VERIFIED** until captured with a logic analyzer.

## Approved scope

1. Add a parallel field profile at
   `config/profiles/ws2811-installed-one-esp-per-strip.yaml` for the exact
   nine-node field subset; do not silently repurpose an old multi-output
   diagnostic profile.
2. Migrate the complete cabin production topology to the 13-node node/strip/
   groups/output/GPIO mapping above. Apply the table's site IPv4 values in
   `cabin-lighting-v3-site-local.yaml`; retain explicit TEST-NET endpoints in
   the generic offline `cabin-lighting-v3-production.yaml` template.
3. Provide firmware node configurations for nodes 1-13 with one output each,
   `output_id: 1`, GPIO4, and the matching group count and site IPv4 suffix.
4. Keep UDP v3's general codec and firmware capability for one to three
   independent outputs. The Phase 31 production topology uses one descriptor;
   it does not narrow or replace the wire protocol.
5. Preserve all logical IDs, layouts, virtual paths, cue timing, effects, and
   Show v2 target semantics. Shows continue to address `strip_*`, never node,
   output, GPIO, or IP values.
6. Update current documentation and hardware acceptance instructions. Preserve
   historical plans and old acceptance reports as evidence of their original
   topology.
7. Add topology, firmware-contract, show-compatibility, and staged-profile
   tests covering both the complete target and current field subset.
8. Schedule production UDP v3 frames against one Host monotonic clock with a
   20 ms shared apply deadline, broadcast clock beacons, fail-closed firmware
   clock readiness, and per-strip encoded-wire compensation. Preserve
   immediate application only in explicit diagnostic environments.
9. Make the scheduled sequence-1 KEY frame atomic across nodes: encode all
   node datagrams first, send three identical rounds 2 ms apart, deduplicate
   repeated apply/media identity in firmware, reject generation-zero non-KEY
   traffic, and retain session admission after successful KEY preparation so
   the next complete frame can recover from a timed-output failure.

## Boundaries

- Do not change UDP v2 or the documented UDP v3 frame/beacon layouts, CRC,
  sequence ownership, queue semantics, timeout safety, production transport
  failure behavior, or the shared logical-frame/apply-time contract.
- Do not place physical topology in `DigitalStrip`, effects, analysis, Show v2
  cues, or logical target IDs. Physical details remain in profiles, mapping,
  `PhysicalFrame`, protocol, transport, and firmware layers.
- Do not re-author a show merely because a strip moved to another controller.
- Do not remove general UDP v3 multi-output support or its golden vectors and
  tests. Production `output_count == 1` is a topology rule, not a protocol rule.
- Do not mix old five-node frames, old multi-output firmware, or old wiring with
  the Phase 31 topology during a live run.
- Do not overwrite history or claim that an untested endpoint, pin, power plan,
  refresh skew, or visible result is hardware verified.
- Do not begin work beyond Phase 31 without explicit approval.

## Atomic field cutover

The field transition is one controlled change, not an incremental live mix:

1. Freeze the node/strip/MAC/IP/firmware record and archive validation output.
2. With production output disabled, flash and label every controller in the
   selected deployment set and commission each node in isolation.
3. Validate the selected profile and shows offline; confirm that every active
   logical strip resolves exactly once and that all active nodes use output 1,
   GPIO4, UDP v3, and unique endpoints.
4. Power down the lighting system. Change physical data connections and select
   `ws2811-installed-one-esp-per-strip.yaml` while outputs remain disabled.
5. Power and test the entire selected set, including all-black, primary colors,
   isolation, timeout, shared sequence/apply capture, beacon readiness,
   scheduled-commit diagnostics, logic-analyzer latch skew, and the 300-second
   show.
6. On any gate failure, stop output and roll back the profile, firmware set, and
   wiring together. Never retain a partially mixed topology.

The complete 13-node profile and the current nine-node field profile are
different deployment sets. A nine-node acceptance run cannot be presented as
acceptance of nodes 3, 11, 12, or 13.

## Phase 31 completion gates

- The complete production mapping contains exactly nodes 1-13 and all 13
  `strip_*` logical IDs exactly once, matching the table above.
- The field profile contains exactly nodes 1, 2, 4, 5, 6, 7, 8, 9, and 10 and
  their nine assigned strips, with no placeholder output for an absent node.
- Every Phase 31 production/field digital node has one output with
  `output_id: 1`, GPIO4, the correct group count, UDP v3, a unique node ID, and
  the correct endpoint for its deployment profile.
- Firmware node configurations 1-13 match the complete mapping and build from
  a clean output directory. General UDP v3 one-to-three-output codec coverage
  remains green.
- Existing shows resolve the same logical targets and produce the same logical
  strip content before and after remapping. No cue timing, effect, logical ID,
  or virtual-path edit is required for the topology migration.
- Validation rejects duplicate nodes/endpoints/outputs, missing mapped strips,
  wrong group counts, and any Phase 31 production node using an output other
  than output 1 on GPIO4.
- Production profiles schedule one shared apply deadline 20 ms ahead and emit
  Host-monotonic broadcast beacons. Production firmware rejects immediate
  frames, fails closed while its bounded minimum-offset clock is not ready,
  prepares before GPIO output, and compensates complete 10/20/40-group wire
  times as 1300/1600/2200 us. Diagnostic images retain immediate behavior.
- Session-start sequence 1 is encoded for every node before any send, repeated
  for three rounds at 2 ms spacing, and idempotently deduplicated by common
  apply/media identity. Successful KEY preparation admits the generation; a
  timed-output failure rolls back while the next complete frame can recover.
  Safe timeout is checked each output loop, and scheduled SPI failure never
  triggers an unplanned second transaction after deadline.
- Relevant tests, the full repository test suite, the required benchmark, and
  the ESP32 firmware build pass and are reported with actual commands and
  return codes.
- The atomic cutover checklist is documented. Any physical result not backed by
  a powered logic-analyzer and real-hardware record remains **NOT HARDWARE
  VERIFIED**.

Stop after all Phase 31 gates are satisfied.
