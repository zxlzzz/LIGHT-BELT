# Phase 17 — Five-Minute Software End-to-End Acceptance

## Phase ID

phase-17-show-acceptance

## Goal

Produce deterministic software-only acceptance evidence for a complete 300-second authored show spanning schema, virtual paths, simultaneous effects, transitions, music fallbacks, mapping, and existing protocol encoders.

## Background

This phase validates integration. It MUST NOT repair production architecture. A discovered production defect is a BLOCKER assigned back to the responsible earlier phase.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Reuse the locked goldens and fixed audio fixtures; additional deterministic generated video/compact procedural sources MAY be added without modifying locked evidence.
- Add a representative versioned 300-second show fixture and matching virtual-path layout fixture.
- Evaluate exactly 9000 show frames at timestamps `n/30` for `n = 0..8999` using an offline/fake clock. An optional final shutdown black frame is separate and MUST NOT change the 9000 count.
- Run the complete offline acceptance twice and require identical SHA-256 output digest(s).
- Include a moving effect crossing a virtual-path seam.
- Include at least three concurrent independent effects on distinct targets.
- Include cue fade-in, fade-out, and overlap.
- Include rhythmic, piano/onset, sustained-string, ambient/sustained-bass, and silence sections.
- Verify final logical frames, PhysicalMapping results, fake RS-485 v2 packets, fake UDP v2 packets, and JSON/memory output where applicable.
- Verify same show-frame sequence is preserved across output paths.
- Check finite values, bounded retained buffers/history, and reported processing capacity.
- Run a separate real-time 300-second software soak using simulator/memory/fake transports. Record actual output FPS, dropped/late frames, average and P95 processing time, peak queue depth, sequence mismatches, and peak memory/RSS where available.
- Produce hashed acceptance artifacts: summary JSON, command log, golden hashes, two-run digests, selected seam/concurrency frames, music decision timeline, protocol-sequence trace, benchmark/soak metrics, and firmware build logs.
- Produce an acceptance report with limitations and the exact phrase `NOT HARDWARE VERIFIED`.

## Out of Scope

- Any production-code change.
- Real hardware claims.
- Firmware feature changes.
- GUI editor.
- Aesthetic approval by the teacher/user.

## Allowed Files

- tests/test_show_e2e_acceptance.py
- tests/fixtures/show/**
- tests/fixtures/audio/acceptance/**
- tests/fixtures/video/**
- config/show_acceptance.yaml
- config/layout_acceptance.yaml
- scripts/show_acceptance.py
- docs/show_acceptance_report.md
- artifacts/show_acceptance/**

## Forbidden Files

- light_engine/**
- firmware/**
- .agent/**
- AGENTS.md
- CLAUDE.md
- scripts/** except scripts/show_acceptance.py
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

- Exactly 9000 authored show frames are produced without wall-clock waiting.
- Two complete runs produce identical output digest(s).
- No NaN or infinity appears in logical, physical, or encoded data.
- A virtual-path chase crosses a strip seam with one continuous head and exact expected destination coordinates.
- At least three targets show different concurrent effects in a selected interval.
- Fade boundary/midpoint values match Phase 14 formulas.
- Sustained bass does not cause repeated impact pulses after attack.
- Low-confidence tempo sections continue animating through event/envelope/free-run fallback.
- Protocol packets decode, CRC checks pass, and same-frame sequences agree.
- Retained queue/history sizes remain bounded after all 9000 frames.
- Offline processing capacity is measured and exceeds 30 show frames/second on the reference environment; otherwise the phase fails with measured evidence.
- The real-time 300-second soak completes without crash, stale-frame accumulation, sequence mismatch, or unbounded queue/history growth. Output FPS, late/dropped frames, P95 processing time, and memory evidence are reported; any result incompatible with the 30 FPS target is a BLOCKER.
- Full tests and both firmware builds pass without modifying firmware.
- The report clearly states `NOT HARDWARE VERIFIED` and lists required physical tests.

## Required Evidence Tests

1. Exact seam frames immediately before, at, and after crossing.
2. Exact target/effect IDs and representative pixels/channels during a concurrent interval.
3. Exact fade weights at start, midpoint, full level, fade-out midpoint, and end.
4. A time trace proving sustained-bass `bass_pulse` decays after attack.
5. A selected-effect/fallback timeline for each generated music section.
6. Sequence equality across logical frame, physical frame, RS-485 packet(s), UDP packet(s), and JSON/memory record.
7. Digest equality across two runs.
8. Locked `G8_acceptance.json` requirements and the golden manifest hash are reproduced in the summary.
9. Real-time soak metrics and artifact SHA-256 values are present and internally consistent.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_show_e2e_acceptance.py -v
.\.python\Scripts\python.exe scripts/show_acceptance.py --show config/show_acceptance.yaml --layout config/layout_acceptance.yaml
.\.python\Scripts\python.exe scripts/show_acceptance.py --show config/show_acceptance.yaml --layout config/layout_acceptance.yaml --realtime-soak 300
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show_acceptance.yaml
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
pio run -d firmware/stm32_rgbcct_node
pio run -d firmware/esp32_ws2811_node
git diff --check
git status --short
git diff --stat
```

## Required Report

Report exact commands/return codes, base/head SHA, frame count, two-run digests, locked golden/fixture hashes, seam evidence, concurrent target evidence, transition evidence, music decision/reason evidence, protocol evidence, bounded-state evidence, real-time soak metrics, artifact paths/SHA-256, test totals, firmware builds, limitations, audit-schema fields, traceability table, and suggested commit message.

## Commit Message

Phase 17: Add show orchestration software acceptance evidence
