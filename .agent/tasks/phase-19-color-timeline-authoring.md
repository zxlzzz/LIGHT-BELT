# Phase 19 — Authored Color Timeline Curves

## Phase ID

phase-19-color-timeline-authoring

## Goal

Add strict show-authoring support for smooth manual color changes inside a cue through `color_timeline`, with deterministic interpolation and concrete rendering tests.

## Background

A five-minute authored show cannot rely only on abrupt fixed colors or many overlapping cue fades. Show authors need a single cue to express “this effect remains active while its base color changes smoothly over time.” Phase 18 makes cue parameters trustworthy; this phase adds a new color curve parameter on top of that foundation.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`


## Vocabulary and Naming Lock

This phase introduces exactly one new show-authoring parameter name: `color_timeline`. This name was selected during authoring design and MUST NOT be renamed to `color_curve`, `gradient`, `palette`, `color_keyframes`, or any other synonym.

The only allowed `color_timeline` child names in V1 are:

- `interpolation`
- `keyframes`
- `time`
- `color`

The only required interpolation value is `rgb_linear`. Do not add HSV, easing, palette, gradient, video-mix, or APP-facing names unless reported as a later-phase proposal.

`color_timeline` is an internal show.yaml field. It is not a Host API V1 field and MUST NOT be added to `host_api_v1.openapi.yaml` in this phase.

## In Scope

- Extend strict show validation to accept `color_timeline` only for supported effects.
- Implement a deterministic RGB linear color interpolation helper.
- Use cue-local time (`show_time - cue.start`) to evaluate `color_timeline`.
- Add strict validation for keyframes and interpolation names.
- Preserve existing `color` behavior when `color_timeline` is absent.
- Define and document precedence:
  - for manual-color effects, `color_timeline` at current cue-local time overrides `color`;
  - `color` overrides config/default color;
  - video/rainbow color sources remain governed by the existing effect policy unless explicitly documented otherwise.
- Support at least these effects:
  - `static`
  - `breath`
  - `audio_pulse`
  - `bass_pulse`
  - `calm`
- Support `chase` and `comet` if their current color-source model can support manual timeline color without violating scope. If not, report the limitation and do not fake support.
- Update configuration/show docs with examples for show authors.

Recommended YAML shape:

```yaml
effect:
  mode: fixed
  name: static
  parameters:
    color_timeline:
      interpolation: rgb_linear
      keyframes:
        - time: 0.0
          color: [1.0, 0.25, 0.05]
        - time: 6.0
          color: [1.0, 0.75, 0.20]
        - time: 14.0
          color: [0.20, 0.45, 1.0]
```

## Out of Scope

- Audio modulation.
- Interpolation modes other than `rgb_linear`.
- Host API changes.
- GUI/editor features.
- Firmware/protocol changes.
- Real hardware verification.

## Allowed Files

- light_engine/show/**
- light_engine/effects/**
- light_engine/color/**
- light_engine/engine/**
- light_engine/models.py
- config/show*.yaml
- tests/test_color_timeline.py
- tests/test_effect_color_timeline.py
- tests/test_show_config.py
- tests/test_show_engine.py
- tests/test_effects.py
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

- A valid `color_timeline` with at least two keyframes loads successfully.
- Missing, malformed, non-monotonic, negative-time, non-finite, boolean-as-number, numeric-string, out-of-range, or unknown-interpolation timelines fail with exact YAML paths.
- `static` output at exact keyframes matches authored colors.
- `static` output halfway between two keyframes matches exact RGB linear interpolation.
- `breath` uses the timeline color as the base color while still applying its brightness envelope.
- `audio_pulse` or `bass_pulse` uses timeline base color while preserving audio-envelope behavior.
- Existing shows without `color_timeline` are unchanged.
- Repeated renders at the same timestamp are deterministic.

## Required Gold Tests

At minimum:

1. Keyframe at local time 0.0 returns first color exactly.
2. Midpoint between red and blue under `rgb_linear` returns exact expected RGB values within declared tolerance.
3. Time before first keyframe clamps to first color; time after last keyframe clamps to last color.
4. Non-monotonic keyframes fail with the exact nested path.
5. Boolean/numeric-string/non-finite keyframe times or colors fail.
6. Existing `parameters.color` still works when no timeline is provided.
7. A show cue starting late uses cue-local time, not absolute show time, when evaluating the timeline.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_color_timeline.py tests/test_effect_color_timeline.py tests/test_show_config.py tests/test_show_engine.py -v
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

Report the `color_timeline` schema, interpolation formula, validation matrix, supported effects, unsupported effect limitations if any, exact tests/commands/return codes, sample rendered colors, audit-schema fields, traceability table, and suggested commit message.

## Commit Message

Phase 19: Add authored color timelines
