# Phase 21 — Cue-Scoped Parallel Audio Modulation

## Phase ID

phase-21-audio-modulation-layer

## Goal

Add cue-scoped `audio_modulation` so fixed or adaptive effects can keep their authored identity while music independently modulates brightness, speed, and intensity.

## Background

Adaptive selection lets music choose an allowed effect inside a cue policy. That is different from the show-authoring need here: the director may want a fixed `comet` or `chase` to remain fixed while audio makes it brighter, faster, or more intense. Phase 20 provides real `MusicControlState` in Engine; this phase adds the schema, validation, and runtime modulation layer.

## Binding Contract References

- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`


## Vocabulary and Naming Lock

This phase introduces exactly one new cue-level show field: `audio_modulation`. Do not rename it to `audio_driver`, `music_modulation`, `music_control`, `dynamic_control`, or any other synonym.

The only allowed modulation channel names in V1 are:

- `brightness`
- `speed`
- `intensity`

The only allowed channel property names in V1 are:

- `source`
- `amount`
- `min_multiplier`
- `max_multiplier`
- `smoothing_seconds`

The only allowed source names in V1 are exactly those listed in In Scope, and each source MUST map directly to an existing `MusicControlState` field or `AudioFeatures` field. Do not invent semantic aliases such as `dynamic_strength`, `beat_power`, `music_energy`, `bass_hit`, or `rhythm_intensity`.

`audio_modulation` is an internal show.yaml field. It is not a Host API V1 field and MUST NOT be added to `host_api_v1.openapi.yaml` in this phase. Host API still exposes runtime effect control through `params` / `effect_params`.

## In Scope

- Add strict cue-level `audio_modulation` schema.
- Support these modulation channels in V1:
  - `brightness`
  - `speed`
  - `intensity`
- Support source names with explicit namespaces:
  - `music.energy`
  - `music.energy_trend`
  - `music.beat_strength`
  - `music.bass_pulse`
  - `music.bass_ambient`
  - `music.transient`
  - `music.spectral_motion`
  - `music.tempo_confidence`
  - `music.beat_regularity`
  - `audio.rms`
  - `audio.bass`
  - `audio.mid`
  - `audio.treble`
  - `audio.spectral_flux`
  - `audio.onset`
- Validate each modulation channel strictly:
  - `source`
  - `amount`
  - `min_multiplier`
  - `max_multiplier`
  - `smoothing_seconds`
- Define deterministic multiplier formula and clamp behavior.
- Apply `speed` and `intensity` before `effect.process(ctx)` through a scoped context/view.
- Apply `brightness` to the cue contribution/output for that cue only; it MUST NOT globally dim unrelated cues.
- Preserve transition fade and blend semantics after modulation.
- Define no-audio behavior as neutral multipliers of `1.0`.
- Allow `fixed + audio_modulation` and `adaptive + audio_modulation`, with documented order: adaptive selection first, modulation second.
- Add deterministic tests proving modulation does not switch fixed effects.

Recommended YAML shape:

```yaml
audio_modulation:
  enabled: true
  brightness:
    source: music.energy
    amount: 0.30
    min_multiplier: 0.75
    max_multiplier: 1.30
    smoothing_seconds: 0.25
  speed:
    source: music.beat_strength
    amount: 0.35
    min_multiplier: 0.80
    max_multiplier: 1.50
    smoothing_seconds: 0.20
  intensity:
    source: music.bass_pulse
    amount: 0.50
    min_multiplier: 0.70
    max_multiplier: 1.60
    smoothing_seconds: 0.20
```

## Out of Scope

- Modulating hue, saturation, width, gap, tail length, start/end, or effect selection outside existing adaptive policy.
- Beat-trigger event scheduling beyond continuous scalar modulation.
- Host API changes.
- Firmware/protocol/hardware changes.
- Claiming audio-hardware closed-loop validation.

## Allowed Files

- light_engine/show/**
- light_engine/engine/**
- light_engine/effects/**
- light_engine/analysis/**
- light_engine/models.py
- config/show*.yaml
- tests/test_audio_modulation_loader.py
- tests/test_audio_modulation_runtime.py
- tests/test_show_engine_audio_modulation.py
- tests/test_show_config.py
- tests/test_show_engine.py
- tests/test_adaptive_selector.py
- docs/configuration.md
- docs/architecture.md
- docs/algorithms.md
- docs/show_306/**

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

- Valid `audio_modulation` loads into typed show models.
- Invalid modulation fields fail with exact YAML paths.
- Fixed cue + audio modulation keeps the fixed effect name and changes brightness/speed/intensity as configured.
- Adaptive cue + audio modulation first selects an allowed effect, then applies modulation.
- No-audio rendering is identical to disabled modulation for the same cue.
- Smoothing is deterministic and bounded.
- Modulation affects only the current cue contribution and does not pollute other cues.
- Existing `audio_control` behavior remains backward compatible.

## Required Gold Tests

At minimum:

1. `brightness` modulation increases/decreases concrete RGB/WW/CW/pixel output within configured min/max bounds.
2. `speed` modulation changes the speed value visible to a deterministic test effect or changes a known pixel position.
3. `intensity` modulation changes the intensity value visible to a deterministic test effect or output amplitude.
4. Unknown source names fail validation.
5. `min_multiplier > max_multiplier` fails validation.
6. Missing audio/music state yields multiplier `1.0` for every channel.
7. Two overlapping cues prove modulation is cue-local.
8. Fixed effects are not switched by modulation.
9. Adaptive effects are selected only from allowed mappings before modulation is applied.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_audio_modulation_loader.py tests/test_audio_modulation_runtime.py tests/test_show_engine_audio_modulation.py tests/test_show_config.py tests/test_show_engine.py tests/test_adaptive_selector.py -v
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

Report schema, source catalog, multiplier formula, smoothing behavior, no-audio behavior, adaptive/fixed interaction order, cue-locality proof, exact commands/return codes, test totals, audit-schema fields, traceability table, and suggested commit message.

## Commit Message

Phase 21: Add cue-scoped audio modulation
