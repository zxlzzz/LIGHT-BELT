# Phase 15 — Deterministic Music Control Features

## Phase ID

phase-15-music-control

## Goal

Derive stable, bounded, deterministic music-control features from existing `AudioFeatures` history without selecting or switching lighting effects.

## Background

Current analysis exposes RMS, bass/mid/treble, spectral flux, onset/beat, and silence. Robust adaptive control additionally needs long-term baselines, transient separation, tempo confidence, and trend information. This phase isolates feature correctness from effect-selection policy.

## Binding Contract References

- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add a typed immutable `MusicControlState` containing at least:
  - `tempo_bpm`
  - `tempo_confidence`
  - `beat_phase`
  - `beat_strength`
  - `beat_regularity`
  - `energy`
  - `energy_trend`
  - `transient`
  - `bass_ambient`
  - `bass_pulse`
  - `spectral_motion`
- Use bounded short-, medium-, and long-window history; memory MUST NOT grow with song duration.
- Separate sustained low-frequency baseline from positive transient excess:
  - a sustained bass tone may keep `bass_ambient` high;
  - after the initial attack, `bass_pulse` MUST decay near zero rather than repeatedly firing.
- Add deterministic tempo/BPM estimation with a documented supported range and confidence in `[0,1]`.
- Low-information or irregular material MUST produce low confidence rather than a fabricated strong BPM.
- All outputs MUST be finite and range-bounded as documented.
- Consume the locked WAV fixtures under `tests/fixtures/audio/show_orchestration_v1/**` and their manifest. Additional procedural unit fixtures MAY be added, but the locked WAVs and hashes MUST NOT be regenerated or edited.
- Emit a deterministic JSON feature summary for each locked fixture so Phase 16 and Phase 17 can reuse evidence without reinterpreting raw waveforms.
- Keep existing `AudioFeatures` and existing effects backward compatible.
- Measure feature-processing cost and bounded history size.

## Out of Scope

- Music-state classification.
- Effect selection or switching.
- YAML allowed mappings.
- Hysteresis/minimum-hold/cooldown policy.
- ML genre/emotion recognition.
- External analysis services.
- Firmware changes.

## Allowed Files

- light_engine/analysis/**
- light_engine/models.py
- tests/test_music_control.py
- tests/test_analysis.py
- tests/fixtures/audio/generated_show_orchestration/**
- docs/algorithms.md
- docs/architecture.md

## Forbidden Files

- light_engine/show/**
- light_engine/effects/**
- light_engine/outputs/**
- firmware/**
- .agent/**
- scripts/agent_*.py
- tests/fixtures/audio/show_orchestration_v1/**

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

- Periodic kick fixtures produce stable BPM and meaningful confidence after warm-up.
- Irregular piano-like events do not require or fabricate high-confidence BPM.
- Slow string crescendo yields a positive energy trend while tempo confidence may remain low.
- Sustained bass yields high `bass_ambient` and only an attack-localized `bass_pulse`.
- Near-static ambience remains finite and stable.
- Silence yields safe low-energy outputs.
- History storage remains bounded after processing a 300-second fixture.
- The same fixture and seed produce identical state sequences.

## Required Gold Tests

At minimum:

1. A 120 BPM periodic fixture estimates within a documented tolerance and confidence threshold after warm-up.
2. A sustained bass fixture triggers at attack but does not produce repeated pulses during the steady section.
3. A crescendo fixture has later `energy` greater than earlier `energy` and positive trend over the rising interval.
4. An irregular onset fixture has lower tempo confidence than the periodic fixture.
5. A 300-second generated fixture leaves history length at or below the documented bound.
6. No output contains NaN or infinity.
7. Locked `G7_music_expectations.json` relational expectations are satisfied; tests MUST prefer documented ranges/relations over brittle exact floating-point snapshots.
8. Locked WAV hashes match `tests/fixtures/audio/show_orchestration_v1/manifest.json` before analysis.

## Performance Gate

The feature stage MUST sustain processing capacity above the project's 60 FPS audio-analysis target on the reference test environment. Report average and P95 per-window processing time, fixture duration, and history bound; failure is a BLOCKER with measured evidence.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_music_control.py tests/test_analysis.py -v
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

Include algorithms, history bounds, locked fixture hashes, per-fixture JSON summaries, BPM tolerance/confidence evidence, sustained-bass trace, average/P95 processing cost, audit-schema fields, traceability table, commands/results, and suggested commit message.

## Commit Message

Phase 15: Add deterministic music control features
