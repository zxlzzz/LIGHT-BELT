# Phase 11 — Versioned Show Schema and Strict Validation

## Phase ID

phase-11-show-schema

## Goal

Introduce immutable show-domain models and a versioned, strict YAML loader for authored shows, without changing Engine runtime behavior.

## Background

The project loads system, layout, effects, and outputs configuration but has no first-class show/cue contract. Later phases require a schema that rejects ambiguity rather than guessing.

## Binding Contract References

- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add typed immutable models for `ShowDefinition`, `Cue`, `TargetSelector`, `EffectSpec`, `TransitionSpec`, and `AudioControlSpec` (or equivalently named types).
- Require top-level `schema_version: 1`; unsupported or missing versions MUST fail.
- Load YAML only through `yaml.safe_load` or the repository's existing safe loader.
- Reject unknown fields at every schema level, including nested transition/audio/effect specifications. Strictness MUST apply recursively; a strict top-level model with permissive nested models is not acceptable.
- Validate all numeric inputs as finite and type-strict; reject NaN, infinity, booleans used as numbers, numeric strings such as `"10"`, and invalid ranges unless a field contract explicitly allows coercion.
- Enforce `duration > 0` and `0 <= start < end <= duration`.
- Reject duplicate cue IDs.
- Define unambiguous target kinds: `analog_zone`, `digital_strip`, `analog_group`, `digital_group`, `virtual_path`, `all_analog`, `all_digital`, and `all`.
- Validate target references against an explicit target catalog supplied by the caller; analog and digital IDs MUST remain distinct even when their text IDs match.
- Validate effect names against the effect registry.
- Validate effect parameter keys against registered V1 parameter metadata; unknown parameter names MUST fail.
- Validate transition values, priority, blend mode, adaptive mappings, minimum hold, cooldown, and tempo thresholds.
- Provide path-aware errors such as `show.cues[2].transition.fade_in`.
- Add a valid example show.

## Out of Scope

- Timeline execution.
- Virtual path layout parsing.
- Frame composition.
- BPM/audio feature implementation.
- CLI `--show` execution.
- Firmware and transport changes.

## Allowed Files

- light_engine/show/**
- light_engine/config/**
- light_engine/models.py
- light_engine/effects/base.py
- config/show*.yaml
- tests/test_show_config.py
- tests/test_config*.py
- tests/test_effect_registry.py
- docs/configuration.md
- docs/architecture.md

## Forbidden Files

- firmware/**
- light_engine/outputs/**
- light_engine/mapping/physical.py
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

- A valid 300-second show containing fixed and adaptive cues loads into typed models.
- Missing/unsupported `schema_version`, unknown fields, invalid timestamps, duplicate IDs, malformed targets, invalid references, unsupported blend modes, negative fades, unknown effects, and unknown effect parameters fail fast.
- Validation errors include the exact YAML path and the invalid value/reason.
- `validate` APIs perform no output, network, serial, media playback, or clock side effects.
- No show execution code is introduced.
- Existing tests remain green.

## Required Gold Tests

At minimum, tests MUST prove:

1. `schema_version: 1` succeeds and missing/`2` fails.
2. Locked fixtures `G1_unknown_top_level.yaml` and `G2_unknown_nested_parameter.yaml` fail with exact nested paths.
3. A misspelled key such as `fade_int` fails; it is not ignored.
4. `analog_zone: wall_left` and `digital_strip: wall_left` resolve as different target types.
5. Unknown target/effect/parameter names fail with exact paths.
6. NaN, infinity, boolean-as-number, and numeric-string inputs fail.
7. A valid 300-second example round-trips to the expected typed values.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_show_config.py tests/test_config.py tests/test_config_validation.py tests/test_effect_registry.py -v
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
git diff --check
git status --short
git diff --stat
```

## Required Report

Report modified files, schema decisions, complete validation matrix, traceability table, exact commands/return codes, test totals, unresolved issues, and suggested commit message.

## Commit Message

Phase 11: Add strict versioned show schema
