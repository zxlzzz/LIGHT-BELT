# LIGHT-BELT Show Orchestration V1 — Hardened Execution Plan

## Objective

Add a deterministic, YAML-authored five-minute show system supporting:

1. Different effects on different targets at the same time.
2. Virtual paths spanning multiple WS2811 strips with continuous global coordinates.
3. Cue-level fade-in, fade-out, and overlap composition.
4. Music-derived control that remains usable for rhythmic, piano, string, ambient, drone, and sustained-bass material.
5. Cue-bounded automatic effect selection; YAML remains the director.
6. Existing direct-effect CLI and physical-output behavior remaining backward compatible.

## Architectural rule

```text
YAML policy + layout
        ↓
strict typed validation
        ↓
Timeline resolves active cues at show time t
        ↓
independent target-scoped effect instances
        ↓
virtual paths render once in global coordinates
        ↓
transition weights + deterministic compositor
        ↓
one final logical PixelFrame
        ↓
existing PhysicalMapping
        ↓
RS-485 / UDP with existing sequence semantics
```

Audio analysis may modulate or select only inside the cue's declared policy.

## Single-authority contracts

All Phases MUST use these planning-baseline contracts instead of redefining semantics locally:

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

A Phase may not edit these files. A genuine conflict returns a BLOCKER for planning revision.

## Locked cross-Phase evidence

The bundle includes immutable evidence:

- `tests/goldens/show_orchestration/v1/G1…G8`
- `tests/goldens/show_orchestration/v1/MANIFEST.sha256`
- `tests/fixtures/audio/show_orchestration_v1/*.wav`
- `tests/fixtures/audio/show_orchestration_v1/manifest.json`

Every later Phase preserves earlier goldens. The fixed WAVs are deterministic synthetic material, not copyrighted music.

## Non-negotiable semantics

- Show schema requires `schema_version: 1`.
- Unknown fields and implicit numeric coercions fail at every nested schema level.
- Analog and digital targets use distinct target kinds even when IDs share text.
- Virtual-path effects render one global buffer, not one effect per strip.
- Optional `gap_after_pixels` creates unmapped virtual coordinates; millimetre calibration is not V1.
- Missing contribution means absent, not black.
- Cue intervals are `[start, end)`.
- Each cue receives `show_time` and `cue_local_time`.
- Backward time fails; V1 reset/replay is explicit and arbitrary stateful seek is not promised.
- Each cue owns an independent effect instance.
- `replace`, `add`, and weighted variants use the contract formulas.
- BPM confidence controls whether beat sync is allowed; low confidence never stops animation.
- Adaptive decisions expose documented reason codes and source-feature evidence.
- Automated completion is software evidence only.

## Phase order and repair budgets

- **Phase 11:** strict versioned show schema — 2 repairs.
- **Phase 12:** virtual paths, global coordinates, optional virtual gaps — 2 repairs.
- **Phase 13:** target-scoped effects and deterministic compositor — 2 repairs.
- **Phase 14:** timeline runtime, fades, reset/pause semantics, and CLI — 2 repairs.
- **Phase 15:** deterministic music-control features — 3 repairs.
- **Phase 16:** cue-bounded adaptive selector and decision evidence — 3 repairs.
- **Phase 17:** five-minute software acceptance and real-time soak — 1 repair.

Music features and selection remain separate because they require different evidence and failure isolation.

## Recommended human checkpoints

The full seven-Phase manifest remains available. The recommended execution uses four segmented manifests so a human can inspect high-risk boundaries without abandoning automated Codex/Claude collaboration:

1. `show-orchestration-v1-a-foundation.json` — Phases 11–12.
2. `show-orchestration-v1-b-runtime.json` — Phases 13–14.
3. `show-orchestration-v1-c-music.json` — Phases 15–16.
4. `show-orchestration-v1-d-acceptance.json` — Phase 17.

Checkpoint evidence:

- after Phase 12: inspect G3 seam and gap behavior;
- after Phase 14: preview a short authored show and boundary/fade evidence;
- after Phase 16: inspect fixed-fixture feature summaries and selector reason logs;
- after Phase 17: inspect offline digests, real-time soak, protocol traces, then perform hardware acceptance.

## Synchronization definition

1. **Temporal synchronization:** all targets use the same show timestamp and sequence.
2. **Spatial continuity:** a virtual path assigns monotonically increasing global coordinates across strips and optional unmapped gap coordinates.
3. **Phase continuity:** effects calculate from global path position, never each strip's local zero.
4. **Physical verification:** actual cross-node continuity is tested later on real strips and is not proven by software tests.

## Music fallback order

```text
reliable beat sync
→ event/onset sync
→ envelope/trend sync
→ free-running animation with bounded subtle modulation
```

A sustained low-frequency pad is represented mainly by `bass_ambient`; only positive transient excess contributes to `bass_pulse`.

## Audit and anti-gaming gates

Every Phase forbids:

- adding skip/xfail bypasses;
- deleting or weakening tests;
- test-aware production branches;
- silent validation fallbacks;
- vague non-crash-only tests;
- editing contracts, locked goldens, or fixed WAV fixtures.

Every report supplies the fields described by `.agent/contracts/phase-audit.schema.json`, including baseline SHA, changed files, test changes, skip/xfail delta, golden manifest hash, commands, traceability, and artifact hashes.
The committed planning baseline is mechanically checked by `scripts/verify_show_orchestration_baseline.py` before the agent pipeline starts.

## Acceptance levels

1. **Phase tests:** prove local contracts and all previous goldens remain valid.
2. **Phase 17 offline integration:** exactly 9000 deterministic authored frames and protocol continuity.
3. **Phase 17 real-time soak:** 300 seconds with FPS, P95 processing time, memory/queue and sequence evidence.
4. **Hardware acceptance:** actual screen-to-wall continuity, node synchronization, installation direction, network recovery, and five-minute visual quality.

Phase 17 MUST state `NOT HARDWARE VERIFIED`.

## Authoring templates

- `config/show.minimal.example.yaml`: smallest understandable multi-target show.
- `config/show.example.yaml`: full fixed/adaptive five-minute example.
- `config/virtual_paths.example.yaml`: virtual path and gap syntax.

## Explicit V1 non-goals

- Machine-learning genre/emotion classification.
- Automatic creation of a complete show from arbitrary music.
- GUI timeline editor.
- Millimetre-based calibration or automatic pixels-per-metre correction.
- Sub-frame synchronization guarantees across Wi-Fi nodes.
- Firmware redesign.
- Aesthetic approval without human observation.
- GitHub Actions/CODEOWNERS/attestation governance; the current execution target is the local PowerShell/worktree pipeline.
