# Phase 14 — Timeline Runtime, Exact Fades, and Show CLI

## Phase ID

phase-14-timeline-transitions

## Goal

Execute authored cues from the existing media/show clock, apply mathematically specified transition weights, compose overlaps, and expose backward-compatible show CLI commands.

## Background

Validated cues, virtual paths, and the compositor exist after prior phases. Timeline semantics must be exact; boundary ambiguity creates duplicate or missing frames.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add a Timeline/ShowRuntime resolving active cues at show timestamp `t`.
- Cue intervals MUST use half-open semantics `[start, end)`:
  - at `t == start`, the cue is active;
  - at `t == end`, the cue is inactive.
- Show frames MUST be evaluated for `0 <= t < duration`; `t >= duration` ends the show.
- Each cue MUST receive both `show_time=t` and `cue_local_time=t-start`.
- Normal runtime timestamps MUST be monotonically non-decreasing. V1 does not promise arbitrary stateful seek reconstruction. A backward jump MUST fail clearly; the caller must explicitly reset and replay from the beginning.
- Repeating the same timestamp (pause) MUST not advance time-dependent state.
- Add explicit `reset()` that recreates per-cue effect state and deterministic cue-level random seeds.
- Instantiate each cue effect once per run and retain it for the cue lifetime; never recreate per frame.
- Implement exact linear transition weight:

```text
fade_in_factor  = 1 if fade_in == 0 else clamp((t - start) / fade_in, 0, 1)
fade_out_factor = 1 if fade_out == 0 else clamp((end - t) / fade_out, 0, 1)
weight          = min(fade_in_factor, fade_out_factor)
```

- This formula MUST also govern overlapping fades where `fade_in + fade_out > cue_duration`; no hidden renormalization.
- Apply weight through the compositor:
  - weighted `replace`: `out = base * (1-weight) + incoming * weight` on participating values;
  - weighted `add`: `out = clamp(base + incoming * weight, 0, 1)`.
- Timeline no-cue state MUST produce no contributions; ShowEngine MUST compose against an explicit black base frame covering all configured targets.
- At completion/shutdown, emit/document one safe black final state according to existing output lifecycle without changing transport protocols.
- Add `--show PATH` and `validate-show --show PATH` (or equivalent). Validation MUST not open outputs, serial ports, UDP sockets, or media playback.
- Use the existing monotonic/media time contract; do not create an independent drifting wall clock.
- Keep direct `--effect` workflows unchanged.

## Out of Scope

- Automatic music-state selection.
- Arbitrary exact random-access reconstruction of stateful effects without replay.
- GUI editor.
- Firmware changes.

## Allowed Files

- light_engine/show/**
- light_engine/engine/**
- light_engine/cli/**
- light_engine/__main__.py
- light_engine/models.py
- config/show*.yaml
- tests/test_timeline.py
- tests/test_show_engine.py
- tests/test_engine.py
- tests/test_clock_integration.py
- docs/configuration.md
- docs/architecture.md
- docs/#U706f#U6548#U4f7f#U7528#U8bf4#U660e.md

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

- A YAML show runs for arbitrary duration including 300 seconds.
- Boundary behavior exactly matches `[start, end)`.
- Fade weights and weighted blend formulas match exact expected values.
- Cue-local time starts at zero even when the cue begins late in the show.
- Overlapping cues compose predictably.
- Effect state persists per cue and resets between show runs.
- Pause does not advance animation; backward time without explicit reset fails clearly.
- Existing `--effect` commands work unchanged.
- Invalid shows validate without starting outputs.

## Required Gold Tests

Tests MUST cover:

```text
t = start - epsilon
t = start
t = start + fade_in/2
t = start + fade_in
t = end - fade_out
t = end - epsilon
t = end
```

And MUST prove:

1. For a 2-second fade-in, the midpoint weight is exactly 0.5 within a declared numeric tolerance.
2. A cue starting at show time 120 receives `cue_local_time == 0` at activation.
3. Two consecutive cues have neither a duplicate active endpoint nor a gap caused by inclusive ends.
4. A reset with the same seed reproduces the same first N frames.
5. Repeating timestamp `t` yields no time advancement.
6. `validate-show` creates no output objects/sockets.
7. Locked `G5_G6_time.json` is consumed exactly for boundary, weight, local-time, and 9000-frame-grid semantics.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_timeline.py tests/test_show_engine.py tests/test_engine.py tests/test_clock_integration.py -v
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

Report exact boundary/fade formulas, local/global time behavior, backward-time failure/reset-replay behavior, CLI commands, compatibility evidence, audit-schema fields, traceability table, test totals, and suggested commit message.

## Commit Message

Phase 14: Add exact YAML show timeline and transitions
