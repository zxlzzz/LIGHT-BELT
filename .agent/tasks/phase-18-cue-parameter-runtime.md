# Phase 18 — Cue Parameter Runtime Binding

## Phase ID

phase-18-cue-parameter-runtime

## Goal

Make the currently accepted `cue.effect.parameters` contract real at runtime: parameters authored in show YAML MUST deterministically override effect defaults and measurably affect rendered frames.

## Background

Phase 11 introduced strict show validation and effect parameter whitelists. Later phases added target-scoped rendering, timeline execution, music features, and adaptive selection. However, a strict loader is not enough: if an effect still reads only `config/effects.yaml`, a show author can write a syntactically valid parameter that does not change the visual output. This phase closes that contract gap without adding new show schema fields.

This phase is deliberately before `color_timeline` and `audio_modulation`; those features rely on reliable cue-parameter delivery.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`


## Vocabulary and Naming Lock

This phase MUST NOT introduce new public show fields, Host API fields, target names, effect names, physical IDs, or protocol names. It may only make already whitelisted `cue.effect.parameters` runtime-effective.

Allowed vocabulary is limited to existing project terms:

- show terms: `cue.effect.parameters`, `mode_parameters`, `cue_local_time`, `show_time`;
- effect names: `static`, `breath`, `color_wave`, `chase`, `comet`, `audio_pulse`, `bass_pulse`, `spectrum`, `video_ambient`, `video_audio_fusion`, `calm`, `demo`;
- parameter names exactly as listed in this task's V1 parameter table.

Do not add or rename APP-facing `target_id`, Host API `params`, Host API `effect_params`, or physical IDs.

## In Scope

- Audit the current effect registry and show loader parameter metadata.
- Ensure every currently whitelisted `cue.effect.parameters` key is either:
  - consumed by the relevant effect/runtime path and covered by tests; or
  - reported as a BLOCKER with the exact reason it cannot be made runtime-effective within this phase.
- Establish a single precedence rule:
  - cue-authored runtime parameters override `config/effects.yaml` defaults;
  - missing cue parameters preserve existing defaults and backward-compatible behavior.
- Implement a small internal helper if useful for typed parameter reads from the cue/runtime context.
- Preserve strict validation: unknown effect parameter keys MUST still fail in the loader.
- Keep fixed and adaptive cues compatible with existing Phase 16 selector behavior.
- Preserve direct non-show `--effect` workflows.
- Document which parameters are runtime-effective and which effect paths use them.

Current V1 parameter surface to bind:

| effect | parameters |
|---|---|
| `static` | `color` |
| `breath` | `period`, `min_brightness`, `color` |
| `color_wave` | `speed`, `width`, `hue_cycle_rate` |
| `chase` | `speed`, `width`, `gap`, `direction`, `trail`, `color_source`, `beat_boost` |
| `comet` | `speed`, `tail_length`, `decay` |
| `audio_pulse` | `attack`, `release`, `color` |
| `bass_pulse` | `attack`, `release`, `color` |
| `spectrum` | `bass_zones`, `mid_zones`, `treble_zones` |
| `video_ambient` | `smoothing` |
| `video_audio_fusion` | `video_weight`, `audio_weight`, `bass_boost`, `treble_limit` |
| `calm` | `period`, `color` |
| `demo` | `cycle_interval`, `effects` |

## Out of Scope

- Adding `color_timeline` or any new show schema field.
- Adding `audio_modulation` or new music-control policy.
- Changing Host API V1, REST/WSS behavior, or APP-facing contracts.
- Firmware changes, protocol changes, or real hardware verification.
- Rewriting the aesthetic behavior of effects beyond making authored parameters take effect.

## Allowed Files

- light_engine/effects/**
- light_engine/show/**
- light_engine/engine/**
- light_engine/models.py
- config/effects.yaml
- config/show*.yaml
- tests/test_effects.py
- tests/test_show_config.py
- tests/test_show_engine.py
- tests/test_adaptive_selector.py
- tests/test_engine.py
- docs/architecture.md
- docs/algorithms.md
- docs/configuration.md

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

- A cue-authored `static.color` changes the rendered color compared with the config/default value.
- A cue-authored `breath.period` changes the breathing phase at a fixed cue-local time while preserving default behavior when omitted.
- A cue-authored `chase.speed`, `width`, `gap`, and `direction` changes digital pixel placement/direction in a deterministic test.
- A cue-authored `comet.speed`, `tail_length`, and `decay` changes the expected comet head/tail output in a deterministic test.
- `video_ambient.smoothing` and `video_audio_fusion` weights affect output in tests using deterministic media feature inputs.
- Missing cue parameters preserve prior config-driven behavior.
- Unknown parameters still fail fast with exact YAML paths.
- Existing direct effect/demo/benchmark workflows remain green.

## Required Gold Tests

At minimum, tests MUST prove:

1. Cue parameters override defaults for `static`, `breath`, `chase`, and `comet`.
2. Omitted parameters fall back to config/default behavior.
3. Unknown parameters still fail validation with an exact nested path.
4. Runtime parameter changes are visible in concrete channel or pixel outputs, not only in internal objects.
5. Fixed and adaptive cue paths both pass through the same parameter-binding behavior when an effect instance is rendered.
6. Existing show examples still validate.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_effects.py tests/test_show_config.py tests/test_show_engine.py tests/test_adaptive_selector.py -v
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

Report changed files, parameter precedence rules, per-effect runtime parameter evidence, validation evidence for unknown keys, backward-compatibility evidence, exact commands/return codes, test totals, blockers, audit-schema fields, traceability table, and suggested commit message.

## Commit Message

Phase 18: Bind cue parameters at runtime
