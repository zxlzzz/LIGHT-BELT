# Phase 23 鈥?Authoring Documentation and Host API Alignment

## Phase ID

phase-23-authoring-docs-host-api-alignment

## Goal

Document the new authoring features and clearly align show.yaml internals with Host API V1 externals so show authors and APP developers do not confuse cue IDs, target IDs, physical IDs, and API fields.

## Background

The project has two layers that must remain distinct:

- Internal show authoring: `show.yaml`, cues, `target.type`, `target.id`, `effect.parameters`, `color_timeline`, `audio_modulation`, virtual paths, and physical layout.
- External Host API V1: APP-facing `target_id`, `effect_type`, `params`, `effect_params`, `transition_ms`, `/shows`, `/playback/*`, `/lights/set`, `/effects/set`, `/capabilities`, and WebSocket messages.

This phase updates documentation only. It must not implement Host Service or change API schemas unless a documentation inconsistency is found and reported.

## Binding Contract References

- `docs/contracts/QUALITY_GATE_CONTRACT.md`


## Vocabulary and Naming Lock

This phase is documentation-only. It must use the exact Host API V1 names from `docs/host_api_v1.md` and `docs/host_api_v1.openapi.yaml`:

- `target_id`
- `effect_type`
- `params`
- `effect_params`
- `transition_ms`
- `show_id`
- `duration_ms`
- `brightness`
- `color_temperature`
- `audio_available`
- `video_available`
- `audio_link_enabled`
- `video_link_enabled`

It must distinguish these from internal show names: `target.type`, `target.id`, `target.ids`, `effect.name`, `cue.effect.parameters`, `transition.fade_in`, `transition.fade_out`, `color_timeline`, and `audio_modulation`.

It MUST NOT add new Host API enum values, physical IDs, REST endpoints, WebSocket message types, or OpenAPI schemas unless only documenting an already existing file value.

## In Scope

- Add or update show-authoring documentation for:
  - cue field meanings;
  - `target.type` vs Host API `target_id`;
  - `cue.id` vs `target.id` vs physical IDs such as `11`, `41`, `91`;
  - effect `mode`, `name`, and parameters;
  - `color_timeline` authoring;
  - `audio_control` vs `audio_modulation`;
  - virtual-path implementation and limitations;
  - PC-first debugging workflow and multi-computer restrictions.
- Add a Host API alignment document explaining:
  - `show.yaml effect.name` 鈫?Host API `effect_type`;
  - internal `cue.effect.parameters` 鈫?Host API `params` / `effect_params`;
  - internal `target.type: virtual_path`, `id: screen_to_wall` 鈫?Host API `target_id: virtual_path.screen_to_wall`;
  - `transition.fade_in/fade_out` seconds vs Host API `transition_ms` milliseconds;
  - `show.duration` seconds vs Host API `duration_ms`;
  - physical IDs are not APP-facing targets unless a future API explicitly exposes them.
- Document that APP does not directly edit cues in Host API V1.
- Document that 91/92/93 should be represented in physical/layout planning but may be enabled/disabled by mapping rather than show rewrites.
- Ensure examples use only schema fields that are actually implemented after Phases 18-22.

## Out of Scope

- Implementing Host API service.
- Editing OpenAPI schemas except typo-only documentation fixes if already present and justified.
- Adding new code behavior.
- Firmware/protocol changes.
- Creating the final 306-second teacher show.

## Allowed Files

- docs/show_306/**
- docs/architecture.md
- docs/configuration.md
- docs/algorithms.md
- docs/host_api_v1.md
- docs/host_api_v1.openapi.yaml
- docs/host_api_v1_changelog.md
- docs/archive/**
- config/show*.yaml

## Forbidden Files

- artifacts/show_acceptance/**
- light_engine/**
- firmware/**
- tests/**
- .agent/**
- scripts/**
- docs/contracts/**
- certs/**
- artifacts/**

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

- Documentation distinguishes internal show authoring from Host API V1 external control.
- Documentation explains `color_timeline` and `audio_modulation` using implemented field names and valid examples.
- Documentation includes a concrete mapping table for internal vs external concepts.
- Documentation states that APP does not directly edit cue lists in Host API V1.
- Documentation states that physical IDs are installation/mapping identifiers, not automatically API `target_id` values.
- Documentation includes the PC-first debugging flow and states that final multi-node synchronized shows should use one Host, not multiple computers sending to the same ESP32 nodes.
- No code, test, firmware, cert, or artifact file is changed.

## Required Gold Tests

At minimum, the implementer report MUST cite exact document sections proving:

1. `cue.id`, `target.id`, and `physical_id` are distinguished.
2. `target.type + id/ids` is mapped to Host API `target_id` only through Host Service.
3. `effect.name` is mapped to Host API `effect_type`.
4. `parameters` are mapped to Host API `params/effect_params`, not treated as identical wire formats.
5. `color_timeline` and `audio_modulation` examples are clearly marked as implemented after the prior phases.
6. APP cannot directly edit cues through Host API V1.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show.example.yaml
```

## Required Full Verification

The full verification intentionally excludes `tests/test_show_e2e_acceptance.py` because that legacy Phase 17 acceptance test rewrites `artifacts/show_acceptance/**`, which is outside this phase scope. Phase 22 adds a separate authoring-modulation acceptance path under `artifacts/authoring_modulation_acceptance/**`.

```powershell
.\.python\Scripts\python.exe -m pytest -q --ignore=tests/test_show_e2e_acceptance.py --ignore=tests/test_authoring_modulation_acceptance.py
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show.example.yaml
git diff --check
git status --short
git diff --stat
```

## Required Report

Report changed docs, section-by-section alignment summary, examples added/updated, Host API mapping table, limitations, exact commands/return codes, audit-schema fields, traceability table, and suggested commit message.

## Commit Message

Phase 23: Document authoring features and Host API alignment

## Phase 22 Artifact Lock

This phase MUST NOT run validation commands that rewrite Phase 22 acceptance artifacts or reports.

Do not run `tests/test_authoring_modulation_acceptance.py` in this phase. That test belongs to Phase 22 and rewrites:

- artifacts/authoring_modulation_acceptance/**
- docs/authoring_modulation_acceptance_report.md

Phase 23 is documentation and Host API alignment only. It must not regenerate, update, normalize, or restamp Phase 22 acceptance evidence.
