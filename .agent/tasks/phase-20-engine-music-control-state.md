# Phase 20 — Engine MusicControlState Runtime Wiring

## Phase ID

phase-20-engine-music-control-state

## Goal

Wire the existing `MusicControlAnalyzer` into the Engine/show runtime so every show frame can receive a real `EffectContext.music_control_state` derived from current `AudioFeatures`.

## Background

Phase 15 created deterministic `MusicControlState`. Phase 16 uses it for adaptive selection policy. The next `audio_modulation` phase requires the Engine to populate music-control state during normal show rendering. This phase adds the runtime data path only; it does not introduce new show schema.

## Binding Contract References

- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`


## Vocabulary and Naming Lock

This phase MUST NOT add show schema fields. It only wires existing music-control analysis into existing runtime context. Use the exact existing names:

- `MusicControlAnalyzer`
- `MusicControlState`
- `EffectContext.music_control_state`
- `AudioFeatures`
- `audio_features`

The only allowed `MusicControlState` field names are the existing model fields: `tempo_bpm`, `tempo_confidence`, `beat_phase`, `beat_strength`, `beat_regularity`, `energy`, `energy_trend`, `transient`, `bass_ambient`, `bass_pulse`, and `spectral_motion`.

Do not introduce `music_state`, `audio_state`, `audio_driver`, `music_driver`, `dynamic_state`, or any Host API names in production code.

## In Scope

- Instantiate and retain `MusicControlAnalyzer` in the relevant Engine/show runtime path.
- On each audio-feature update, produce a bounded `MusicControlState` and pass it through `EffectContext.music_control_state`.
- Preserve the existing `EffectContext.audio_features` path.
- Define no-audio behavior: no audio MUST produce a safe `None` or documented neutral state, and must not crash.
- Reset/seek/show-runtime reset MUST reset music-control analyzer state consistently.
- Repeated timestamps/pause MUST not fabricate extra musical progress.
- Keep memory bounded; do not store unbounded audio history in Engine.
- Expose enough test hooks or deterministic fixtures to prove the state reaches fixed/adaptive rendering paths.
- Preserve backward-compatible direct effect workflows.

## Out of Scope

- Adding `audio_modulation` schema or behavior.
- Changing `MusicControlAnalyzer` algorithms unless a small integration bug fix is required.
- Reworking adaptive selector policy.
- Host API changes.
- Firmware/protocol/hardware changes.

## Allowed Files

- light_engine/engine/**
- light_engine/show/**
- light_engine/analysis/**
- light_engine/effects/**
- light_engine/models.py
- tests/test_engine_music_control_state.py
- tests/test_show_engine.py
- tests/test_music_control.py
- tests/test_adaptive_selector.py
- tests/test_engine.py
- docs/architecture.md
- docs/algorithms.md

## Forbidden Files

- artifacts/show_acceptance/**
- firmware/**
- light_engine/outputs/**
- light_engine/protocols/**
- tests/fixtures/audio/show_orchestration_v1/**
- tests/goldens/show_orchestration/v1/**
- docs/contracts/**
- .agent/**
- scripts/agent_*.py

## Artifact Scope Lock

This phase MUST NOT modify `artifacts/show_acceptance/**`. Those files belong to the earlier Phase 17 acceptance baseline and are known to contain runtime/benchmark outputs. Do not update them to make this phase pass. If a command incidentally rewrites those files, treat that as a validation-command problem and avoid that command in this phase; do not commit the rewritten artifacts.


## Binding Quality Constraints

These constraints are part of acceptance, not suggestions:

- MUST follow the referenced contracts. If implementation requires changing a contract, stop and report a BLOCKER; do not edit the contract inside this Phase.
- MUST NOT modify `docs/contracts/**`, `.agent/contracts/**`, `tests/goldens/show_orchestration/v1/**`, `tests/fixtures/audio/show_orchestration_v1/**`, or `scripts/verify_show_orchestration_baseline.py`.
- The report MUST include audit evidence conforming to `.agent/contracts/phase-audit.schema.json`: base/head SHA, changed files, tests added/modified, skip/xfail counts before/after, golden manifest SHA-256 when applicable, exact command return codes, traceability, artifacts, and blockers.
- MUST NOT add or broaden `pytest.skip`, `pytest.mark.skip`, `xfail`, or equivalent bypasses.
- MUST NOT delete existing tests, weaken assertions, reduce test coverage intentionally, or change expected values merely to match an incorrect implementation.
- MUST NOT add production branches that detect tests, fixture names, or CI environments.
- MUST NOT silently accept invalid configuration or silently fall back after a validation error.
- New tests MUST assert concrete domain outputs: colors, pixels, channels, target IDs, cue IDs, speed/intensity values, transition weights, selected states, sequences, or exact validation errors. `is not None`/"does not crash" alone is insufficient.
- Existing backward-compatible behavior MUST be covered by regression tests.
- If a requirement cannot be satisfied within Allowed Files, stop and report a BLOCKER instead of modifying a forbidden file.
- The phase report MUST include a traceability table: `Requirement | Implementation | Test | Evidence`.
- Automated success proves software behavior only. It MUST NOT claim hardware verification unless the phase explicitly performs documented hardware tests.


## Acceptance Criteria

- With audio features present, Engine/show runtime provides non-`None` `music_control_state` to rendering/selector paths.
- With no audio, rendering remains deterministic and does not crash.
- Reset clears analyzer state so a second run from the same seed/input reproduces the same music-control state sequence.
- Adaptive cues use the Engine-provided `music_control_state` rather than a fabricated or stale value.
- Existing audio feature behavior is unchanged.
- History and retained state remain bounded.

## Required Gold Tests

At minimum:

1. A deterministic audio-features sequence produces a deterministic `MusicControlState` sequence inside Engine/show runtime.
2. A fixed cue can observe the same music-control state in its context without selecting a new effect.
3. An adaptive cue receives music-control state and produces a decision using it.
4. `reset()` reproduces the same first N music-control states.
5. No-audio show render keeps `music_control_state` neutral/None and output valid.
6. Repeating the same timestamp does not advance music-control state spuriously.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_engine_music_control_state.py tests/test_show_engine.py tests/test_music_control.py tests/test_adaptive_selector.py -v
```

## Required Full Verification

The full verification intentionally excludes `tests/test_show_e2e_acceptance.py` because that legacy Phase 17 acceptance test rewrites `artifacts/show_acceptance/**`, which is outside this phase scope. Phase 22 adds a separate authoring-modulation acceptance path under `artifacts/authoring_modulation_acceptance/**`.

```powershell
.\.python\Scripts\python.exe -m pytest -q --ignore=tests/test_show_e2e_acceptance.py
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show.example.yaml
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
git diff --check
git status --short
git diff --stat
```

## Required Report

Report the runtime data path, no-audio behavior, reset semantics, bounded-state evidence, adaptive selector evidence, exact commands/return codes, test totals, audit-schema fields, traceability table, and suggested commit message.

## Commit Message

Phase 20: Wire music control state into engine
