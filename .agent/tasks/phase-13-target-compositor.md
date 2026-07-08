# Phase 13 — Target-Scoped Effects and Deterministic Compositor

## Phase ID

phase-13-target-compositor

## Goal

Allow independent effect instances to render different analog zones, digital strips, groups, and virtual paths in the same frame, then combine typed contributions deterministically.

## Background

The current Engine owns one active effect. Multi-effect shows require explicit target masking and exact overlap mathematics. "No contribution" must never be confused with intentional black.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add target resolution for all Phase 11 target kinds.
- Add a typed contribution model that distinguishes:
  - **absent/no contribution**: this effect does not participate in that target/pixel;
  - **explicit black**: this effect intentionally renders zero.
- Missing targets MUST be absent. They MUST NOT be materialized as black.
- Give every render job/cue its own effect instance and mutable effect state. Sharing one stateful effect instance between cues is forbidden.
- Provide a scoped immutable context/view containing only selected analog/digital definitions and global/cue metadata needed by effects.
- A virtual-path render MUST use the Phase 12 global path buffer and then split to contributions before composition.
- Define deterministic application order as `(priority ascending, declaration_index ascending)`; later contributions in that order apply later. Cue IDs remain unique and are evidence/debug labels, not an unordered-map iteration source.
- Implement exact V1 blend modes:
  - `replace`: incoming explicit values replace prior values on participating channels/pixels;
  - `add`: `out = clamp(base + incoming, 0, 1)` independently for RGB, WW, and CW channels.
- Preserve master sequence and timestamp.
- Never mutate an input frame, contribution, pixel list, or color object in place.
- Clamp and reject non-finite results.
- Preserve the existing single-effect Engine path unchanged when no show runtime is used.

## Out of Scope

- Timeline active-cue lookup.
- Fade/alpha weight calculation.
- BPM/audio selector.
- Transport changes.

## Allowed Files

- light_engine/show/**
- light_engine/effects/**
- light_engine/models.py
- light_engine/engine/**
- tests/test_target_resolution.py
- tests/test_compositor.py
- tests/test_effects.py
- tests/test_engine.py
- docs/architecture.md

## Forbidden Files

- firmware/**
- light_engine/outputs/rs485_v2.py
- light_engine/outputs/udp_v2.py
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

- At one timestamp, digital strip A runs chase, digital strip B runs comet, and analog zone C runs breath.
- A virtual-path effect coexists with unrelated strip/zone effects.
- An absent contribution leaves existing content unchanged.
- Explicit black under `replace` extinguishes the selected target.
- `add` applies exact per-channel clamped addition.
- Two cues using the same effect name have independent state.
- Results are independent of dictionary/hash iteration and repeat exactly across runs.
- Existing one-effect Engine behavior and tests remain valid.

## Required Gold Tests

At minimum:

1. Base strip is red; an absent contribution leaves red unchanged.
2. Base strip is red; explicit-black `replace` yields black.
3. `(0.8, 0.2, 0.1) add (0.5, 0.9, 0.0)` yields `(1.0, 1.0, 0.1)`.
4. RGBCCT addition clamps all five channels independently.
5. Two seeded comet cues advance independently.
6. Reordering an internal dictionary without changing priority/declaration order does not alter output.
7. Inputs are byte-for-byte/equality unchanged after composition.
8. Locked `G4_compositor.json` is consumed as the authoritative absence/black/add vector.

## Performance Gate

Capture the required benchmark before and after implementation. Post-change processing capacity MUST NOT regress by more than 20% without a reviewer-approved BLOCKER explaining the measured cause.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_target_resolution.py tests/test_compositor.py tests/test_effects.py tests/test_engine.py -v
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
git diff --check
git status --short
git diff --stat
```

## Required Report

Report composition formulas, absent-vs-black contract, state-isolation evidence, deterministic ordering trace, benchmark baseline/result, compatibility evidence, audit-schema fields, traceability table, commands/return codes, and suggested commit message.

## Commit Message

Phase 13: Add deterministic target-scoped composition
