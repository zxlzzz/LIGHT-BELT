# Phase 12 — Virtual Paths and Continuous Global Coordinates

## Phase ID

phase-12-virtual-paths

## Goal

Add validated virtual paths that concatenate logical digital-strip ranges into one continuous global coordinate space, render once in that space, and split contributions back without seam resets.

## Background

Starting the same strip-local effect on two strips creates synchronized duplicates. A screen-to-wall motion requires one global phase and one moving head across all participating segments.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Extend layout parsing with typed virtual-path and segment definitions.
- Each segment MUST declare `strip_id`, `source_start`, `pixel_count`, and `direction` (`forward` or `reverse`); safe defaults may be supplied only when unambiguous and documented.
- Each segment MAY declare non-negative integer `gap_after_pixels` (default `0`). Gap coordinates extend the virtual path and animation time/phase but map to no physical destination contribution.
- Validate unique path IDs, non-empty paths, known digital-strip IDs, integer ranges, positive lengths, and in-range source intervals.
- V1 duplicate policy: a source pixel MUST NOT appear more than once inside the same virtual path; overlapping ranges and duplicate ranges MUST fail.
- The same strip MAY appear in different path definitions; runtime overlap is handled later by the compositor.
- Compute immutable global half-open intervals `[global_start, global_end)` for mapped segments, explicit unmapped gap intervals, and exact total virtual length including gaps.
- Path coordinates MUST be monotonic integers `0..total_length-1` independent of physical node routing.
- Render a complete path-sized contribution exactly once, then split it into strip/range contributions. Calling an effect separately for each segment is forbidden.
- `reverse` MUST reverse destination pixel order only; it MUST NOT restart or reverse the global animation phase.
- Partial-strip segments MUST leave pixels outside the selected range absent/no-contribution, not black.
- Integrate actual virtual-path IDs into show reference validation.
- Document that V1 supports authored `gap_after_pixels` only. Millimetre-based calibration and unequal pixels-per-metre compensation remain out of scope.
- Produce a deterministic path summary containing mapped-pixel count, gap-coordinate count, total virtual length, participating strips, subranges, and directions.

## Out of Scope

- Cue scheduling.
- Multiple effects at once.
- Fade transitions.
- Audio adaptation.
- Metric/centimetre coordinate correction and automatic conversion from physical distance to gap pixels.
- Network or firmware changes.

## Allowed Files

- light_engine/mapping/**
- light_engine/show/**
- light_engine/config/**
- light_engine/models.py
- config/layout*.yaml
- config/virtual_paths*.yaml
- tests/test_virtual_paths.py
- tests/test_physical_mapping.py
- tests/test_config_validation.py
- tests/test_show_config.py
- docs/architecture.md
- docs/configuration.md

## Forbidden Files

- firmware/**
- light_engine/outputs/**
- light_engine/analysis/**
- .agent/**
- scripts/agent_*.py

## Binding Quality Constraints

These constraints are part of acceptance, not suggestions:

- MUST follow the planning-baseline contracts listed above. If implementation requires changing a contract, stop and report a BLOCKER; do not edit the contract inside this Phase.
- MUST NOT modify `docs/contracts/**`, `.agent/contracts/**`, `tests/goldens/show_orchestration/v1/**`, `tests/fixtures/audio/show_orchestration_v1/**`, or `scripts/verify_show_orchestration_baseline.py`.
- The report MUST include audit evidence conforming to `.agent/contracts/phase-audit.schema.json`: base/head SHA, changed files, tests added/modified, skip/xfail counts before/after, golden manifest SHA-256, exact command return codes, traceability, artifacts, and blockers.
- MUST NOT add or broaden `pytest.skip`, `pytest.mark.skip`, `xfail`, or equivalent bypasses.
- MUST NOT delete existing tests, weaken assertions, reduce test coverage intentionally, or change expected values merely to match an incorrect implementation.
- MUST NOT add production branches that detect tests, fixture names, or CI environments.
- MUST NOT silently accept invalid configuration or silently fall back after a validation error.
- New tests MUST assert concrete domain outputs (IDs, coordinates, pixels, weights, states, sequences, or exact errors); `is not None`/"does not crash" alone is insufficient.
- Existing backward-compatible behavior MUST be covered by regression tests.
- If a requirement cannot be satisfied within Allowed Files, stop and report a BLOCKER instead of modifying a forbidden file.
- The phase report MUST include a traceability table: `Requirement | Implementation | Test | Evidence`.
- Automated success proves software behavior only. It MUST NOT claim hardware verification unless the phase explicitly performs documented hardware tests.

## Acceptance Criteria

- A path joins at least two logical digital strips with independent directions and optional subranges.
- Mapped segment intervals plus declared gap intervals cover exactly the total virtual coordinate range with no accidental holes or overlaps.
- A moving head crossing a seam produces exactly one head and never restarts at the second strip.
- Reverse mapping changes destination order only; global phase remains continuous.
- Pixels outside partial ranges remain absent and cannot erase unrelated content.
- Invalid references, ranges, directions, duplicate source pixels, and lengths fail at startup.
- Existing `PhysicalMapping` behavior remains compatible.

## Required Gold Tests

Tests MUST include this exact vector:

```text
path buffer = [R, G, B, Y, M]
segment A = strip_a[0:3], forward
segment B = strip_b[0:2], reverse
expected strip_a contribution = [R, G, B]
expected strip_b contribution = [M, Y]
```

They MUST also prove:

1. A one-pixel head moves from the final coordinate of segment A to the first global coordinate of segment B with one lit head in each frame.
2. Segment B's first global coordinate lands on the correct reversed destination pixel.
3. Overlapping source ranges in one path fail.
4. A path result is identical regardless of ESP32 node assignments.
5. Locked `G3_virtual_path.json` is consumed exactly, including its reverse vector and two-coordinate virtual-gap case.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_virtual_paths.py tests/test_physical_mapping.py tests/test_config_validation.py tests/test_show_config.py -v
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
git diff --check
git status --short
git diff --stat
```

## Required Report

Include the exact gold vector, a screen-to-wall seam trace, direction semantics, duplicate policy, modified files, traceability table, commands/results, and suggested commit message.

## Commit Message

Phase 12: Add continuous virtual strip paths
