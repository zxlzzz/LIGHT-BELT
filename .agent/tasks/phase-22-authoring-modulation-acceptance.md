# Phase 22 — Authoring Modulation Software Acceptance

## Phase ID

phase-22-authoring-modulation-acceptance

## Goal

Produce deterministic software-only acceptance evidence that cue parameter binding, color timelines, Engine music-control state, audio modulation, adaptive selection, transitions, and virtual-path rendering work together.

## Background

Phases 18 through 21 add authoring features. This phase is integration evidence only. It MUST NOT repair production architecture; a production defect discovered here is a BLOCKER assigned back to the responsible phase.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`


## Vocabulary and Naming Lock

This phase may only use field names and values implemented by Phases 18-21 plus existing show/orchestration terms. It MUST NOT invent new target IDs, effect names, modulation names, APP fields, or physical IDs.

Use existing public test names where possible. For virtual-path evidence, use the existing `screen_to_wall` path unless the previous phases have explicitly added another path. Do not introduce `screen_right_to_right_wave`, `screen_top_to_ceiling`, or other physical-layout-specific path IDs in this acceptance phase. Those belong to later physical-layout planning.

All generated artifacts MUST remain software-only and MUST include `NOT HARDWARE VERIFIED`.

## In Scope

- Add a representative software-only acceptance show fixture using:
  - cue-authored effect parameters;
  - `color_timeline`;
  - `audio_modulation` brightness/speed/intensity;
  - fixed cues;
  - adaptive cues;
  - transitions and overlaps;
  - at least one virtual-path effect crossing a seam.
- Add deterministic generated/procedural audio/video inputs if needed; do not modify locked fixtures.
- Render a bounded deterministic frame set twice and require matching digests.
- Capture sample frames proving:
  - color interpolation;
  - modulation multiplier effects;
  - virtual-path seam continuity;
  - transition/overlap behavior;
  - no-audio fallback behavior.
- Produce hashed artifacts under `artifacts/authoring_modulation_acceptance/**`.
- Produce a concise acceptance report with the exact phrase `NOT HARDWARE VERIFIED`.
- Keep runtime short enough for the automated agent loop while still exercising the full integration surface.

## Out of Scope

- Production-code changes except a BLOCKER report; this phase should mainly add tests, fixtures, scripts, and artifacts.
- Real hardware claims.
- Firmware changes or builds unless already required by the existing full test suite.
- Host API service implementation.
- Aesthetic approval or final 306-second show authoring.

## Allowed Files

- tests/test_authoring_modulation_acceptance.py
- tests/fixtures/show/**
- tests/fixtures/audio/acceptance/**
- tests/fixtures/video/**
- config/show_authoring_modulation_acceptance.yaml
- config/layout_authoring_modulation_acceptance.yaml
- scripts/authoring_modulation_acceptance.py
- docs/authoring_modulation_acceptance_report.md
- docs/show_306/**
- artifacts/authoring_modulation_acceptance/**

## Forbidden Files

- artifacts/show_acceptance/**
- light_engine/**
- firmware/**
- .agent/**
- AGENTS.md
- CLAUDE.md
- scripts/agent_*.py
- scripts/agent_worktree.py
- scripts/verify_show_orchestration_baseline.py
- tests/fixtures/audio/show_orchestration_v1/**
- tests/goldens/show_orchestration/v1/**
- docs/contracts/**

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

- Acceptance show validates successfully.
- Two deterministic runs produce identical digest(s).
- `color_timeline` sample frames match expected interpolation values.
- `audio_modulation` sample frames prove brightness/speed/intensity changes compared with disabled/neutral modulation.
- No-audio fallback produces neutral multipliers and valid output.
- A virtual-path effect crosses a seam continuously.
- Transitions and overlaps retain Phase 14 semantics.
- Adaptive selection remains constrained by allowed mappings while modulation remains cue-local.
- No NaN or infinity appears in logical or physical frames.
- Report and artifacts explicitly state `NOT HARDWARE VERIFIED`.

## Required Evidence Tests

1. Exact sample colors at at least three local times in a color timeline.
2. Exact or bounded multipliers for brightness/speed/intensity modulation.
3. Selected representative pixels/channels before, at, and after a virtual-path seam.
4. Transition weights at fade-in midpoint and fade-out midpoint.
5. A fixed-effect cue proving modulation does not change the effect name.
6. An adaptive cue proving allowed effect selection plus modulation order.
7. Digest equality across two runs.
8. Artifact SHA-256 values are present and internally consistent.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_authoring_modulation_acceptance.py -v
.\.python\Scripts\python.exe scripts/authoring_modulation_acceptance.py --show config/show_authoring_modulation_acceptance.yaml --layout config/layout_authoring_modulation_acceptance.yaml
```

## Required Full Verification

The full verification intentionally excludes `tests/test_show_e2e_acceptance.py` because that legacy Phase 17 acceptance test rewrites `artifacts/show_acceptance/**`, which is outside this phase scope. Phase 22 adds a separate authoring-modulation acceptance path under `artifacts/authoring_modulation_acceptance/**`.

```powershell
.\.python\Scripts\python.exe -m pytest -q --ignore=tests/test_show_e2e_acceptance.py
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show_authoring_modulation_acceptance.yaml
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
git diff --check
git status --short
git diff --stat
```

## Required Report

Report exact commands/return codes, base/head SHA, digest evidence, color timeline evidence, modulation evidence, seam evidence, transition evidence, adaptive/fixed evidence, artifact paths/SHA-256, limitations, `NOT HARDWARE VERIFIED`, audit-schema fields, traceability table, and suggested commit message.

## Commit Message

Phase 22: Add authoring modulation acceptance evidence
