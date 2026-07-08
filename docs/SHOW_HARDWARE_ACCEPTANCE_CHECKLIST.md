# Show Orchestration Hardware Acceptance Checklist

Software campaign success is not hardware acceptance. Perform this checklist after Phase 17.

## Test setup record

Record:

- PC or RK platform and software commit;
- router/network;
- ESP32 node IDs and firmware commit;
- protocol versions and compatibility matrix;
- logical strip IDs, physical lengths, pixel counts, installed directions, and configured `gap_after_pixels`;
- measured physical gaps and pixels-per-metre for later calibration evidence;
- power supplies and brightness limit;
- show YAML, layout YAML, golden manifest, and fixed-fixture hashes.

## Required physical tests

1. **Direction identification:** light the first and last controllable group of every strip and verify configuration.
2. **Single-seam motion:** run one narrow head from the final screen segment into the first wall segment; verify no duplicate head, reset, reversal, or dark extra frame beyond an intentionally configured virtual gap.
3. **Gap calibration:** compare `gap_after_pixels=0` with the authored value and record which better matches the real screen-to-wall distance. V1 does not automatically derive this value.
4. **Reverse segment:** repeat with a physically reversed wall strip.
5. **Cross-node synchronization:** place two nodes side by side, flash the same sequence, and measure/record visible or instrumented skew. Record maximum observed frame skew/sequence drift rather than claiming exact simultaneity.
6. **Concurrent effects:** verify at least three targets visibly run different effects without cross-erasing.
7. **Fade boundaries:** observe and record cue start, midpoint, full level, and end.
8. **Music cases:** test rhythmic music, piano, string crescendo, sustained low-frequency ambience, and silence/free-run behavior.
9. **Network interruption:** interrupt UDP and verify safe timeout; restore network and verify recovery without stale queued frames.
10. **Five-minute run:** run the complete 300-second show and record dropped frames, resets, thermal/power issues, and visual defects.
11. **Final black/safe state:** verify stop and fault behavior.

## Acceptance statement

Only after this checklist is documented may the project state:

`HARDWARE VERIFIED FOR THE RECORDED TEST CONFIGURATION`

The statement does not generalize to a different layout, power system, network, firmware build, gap calibration, or software commit.
