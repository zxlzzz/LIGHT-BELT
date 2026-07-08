# Phase 16 — Cue-Bounded Adaptive Effect Selector

## Phase ID

phase-16-adaptive-selector

## Goal

Use `MusicControlState` to choose and modulate effects only within each cue's YAML policy, with deterministic fallback, hysteresis, and anti-chatter behavior.

## Background

Music features and effect policy are separate concerns. YAML remains the director. The selector may only choose from declared mappings and must keep animation running when BPM is weak or absent.

## Binding Contract References

- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add a typed rule-based music state:
  `silence | calm | flowing | rhythmic | energetic | impact | transition | ambient`.
- Classify state solely from `MusicControlState` and documented thresholds; do not reimplement raw audio analysis.
- Implement exact fallback selection order:
  1. `beat_sync` only when tempo confidence and beat regularity meet cue thresholds;
  2. `event_sync` when transient/onset evidence is sufficient;
  3. `envelope_sync` when energy trend or spectral motion is informative;
  4. `free_run` otherwise.
- Adaptive cues MUST choose only from their YAML `allowed` mapping. Missing mapping for the active state MUST use an explicitly configured fallback or fail validation; it MUST NOT choose arbitrarily.
- Fixed cues MUST remain fixed and bypass selection.
- Implement state confirmation time, hysteresis, minimum effect hold, and switch cooldown using show time.
- Define tempo-derived period as `beats_per_cycle * 60 / tempo_bpm` when beat sync is active.
- Quantize only to configured beat subdivisions and smooth period/speed changes; no frame-to-frame jumps.
- Low-confidence tempo MUST NOT freeze or zero animation speed.
- Create a fresh effect instance when the selected effect actually changes; do not recreate it every frame.
- Preserve deterministic seeded behavior.
- Produce an immutable `SelectionDecision` (or equivalently named record) for every evaluation containing show time, classified state, sync mode, selected/previous effect, finite source-feature snapshot, hold/cooldown/confirmation status, and one documented `reason_code` from the locked G7 set.
- Selection policy MUST be implemented as a documented decision table/state machine. Free-form condition chains without externally testable reason codes are insufficient.
- Fixed-effect cues remain available for music modulation without automatic switching; automatic switching is never mandatory for authored shows.

## Out of Scope

- Raw BPM/audio feature extraction.
- ML genre/emotion recognition.
- Automatic whole-show generation.
- Selection outside YAML policy.
- Firmware/output changes.

## Allowed Files

- light_engine/show/**
- light_engine/effects/**
- light_engine/models.py
- config/show*.yaml
- config/effects.yaml
- tests/test_adaptive_selector.py
- tests/test_show_engine.py
- tests/test_effects.py
- docs/algorithms.md
- docs/architecture.md
- docs/configuration.md

## Forbidden Files

- light_engine/analysis/**
- light_engine/outputs/**
- firmware/**
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

- Rhythmic high-confidence input uses beat sync and a declared rhythmic effect.
- Piano-like irregular input uses event fallback without mandatory BPM lock.
- String-like crescendo uses envelope behavior.
- Sustained-bass/ambient input does not repeatedly enter impact after the attack.
- Near-static input uses free run and continues animating.
- No selected effect falls outside the cue's allowed mapping.
- Threshold noise does not cause selector chatter.
- Minimum hold and cooldown are enforced by show time.
- Tempo modulation is smooth and bounded.
- Behavior is deterministic for fixed input and seed.

## Required Gold Tests

1. A state oscillating around one threshold does not switch repeatedly because hysteresis/confirmation apply.
2. An effect cannot switch before `min_effect_hold` even if another state appears briefly.
3. It cannot switch again during `switch_cooldown`.
4. Low-confidence tempo selects event/envelope/free-run and speed remains positive.
5. An effect name absent from `allowed` is never instantiated.
6. Fixed cues ignore adaptive state changes.
7. Two identical runs produce the same selected-effect timeline.
8. Every decision uses a locked/documented reason code and exposes the feature snapshot and hold/cooldown status that caused it.
9. The locked G7 fixture expectations drive a decision-table test for rhythmic, piano, crescendo, sustained-bass, and silence cases.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_adaptive_selector.py tests/test_show_engine.py tests/test_effects.py -v
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show.example.yaml
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
git diff --check
git status --short
git diff --stat
```

## Required Report

Include threshold/state decision table, complete reason-code catalog, per-fixture decision logs, fallback decisions, allowed-mapping proof, hold/cooldown traces, tempo smoothing evidence, audit-schema fields, traceability table, commands/results, and suggested commit message.

## Commit Message

Phase 16: Add cue-bounded adaptive effect selection
