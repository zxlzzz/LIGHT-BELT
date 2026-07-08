# Show Orchestration V1 Software Acceptance Checkpoint

## Status

Show Orchestration V1 software acceptance checkpoint has been reached.

This checkpoint is tagged as:

`show-orchestration-v1-software-acceptance-20260708`

## Branch

`campaign/show-orchestration-v1`

## Scope

This is a software acceptance milestone, not a final hardware acceptance milestone.

Hardware status remains:

`NOT HARDWARE VERIFIED`

## Implemented Capabilities

- Strict versioned show YAML schema
- Continuous virtual paths across physical LED strips
- Target-scoped concurrent effects
- Deterministic compositor
- Exact `[start, end)` timeline semantics
- Fade-in and fade-out behavior
- Cue-local time
- Deterministic music-control features
- Cue-bounded adaptive effect selection
- Five-minute software acceptance show
- 9000 authored frames at 30 FPS
- Two-run digest equality
- Protocol sequence evidence
- Seam continuity evidence
- Concurrent target evidence
- Fade evidence
- Music fallback evidence
- Bounded runtime state evidence
- STM32 firmware build reproducibility
- ESP32 firmware build reproducibility

## Acceptance Evidence

Primary evidence artifact:

`artifacts/show_acceptance/summary.json`

Key evidence:

- `NOT HARDWARE VERIFIED`
- `frame_count = 9000`
- `digest_equal = true`
- `dropped_frames = 0`
- `late_frames = 0`
- `sequence_mismatches = 0`

## Notes

The ESP32 FastLED build may emit a warning about the unavailable parallel clockless I2S driver. This is not a blocking issue for this software acceptance checkpoint because the firmware build completes successfully.

Further work may continue after this checkpoint, including hardware validation, physical LED layout tuning, real strip testing, and RK3588 deployment validation.
