# Current Implementation Plan

Status: **Phase 30 completed on 2026-07-13; stop boundary reached**.

Product implementation Phases 0-29 are complete. Their original approved plan
is preserved at
`docs/history/implementation/implementation-plan-phases-0-29.md` and is no
longer an active instruction source.

## Previously completed scope

1. Inventory and classify repository files.
2. Establish one current documentation entry point.
3. Archive completed plans, task files, campaign manifests, and legacy docs.
4. Separate committed acceptance baselines from disposable run output.
5. Organize configuration by runtime, profile, show, example, and acceptance
   purpose; improve ambiguous filenames.
6. Remove only confirmed accidental, broken, or ad-hoc duplicate files, then
   stop.

## Phase 30: Show v2 brightness tracks

Approved scope:

1. Add optional, strictly validated Show v2 `brightness_tracks`.
2. Resolve each track through the existing logical target model.
3. Support `linear` and `step` keyframe interpolation in show time.
4. Apply independent target levels after cue composition and before the final
   output transform.
5. Preserve a neutral level of `1.0` for shows, targets, and time ranges with
   no authored brightness track.
6. Reject overlapping active tracks for the same concrete logical target.
7. Add loader, runtime, compatibility, and output-ownership tests, then stop.

## Boundaries

- Do not change wire formats, topology, safety behavior, global brightness
  ownership, sequence ownership, or production transport semantics.
- `brightness_tracks` are target-level logical automation. Final global
  brightness remains owned by `OutputTransform` and is still applied once.
- Do not add effect-specific brightness parameters or change existing cue
  audio modulation behavior.
- Preserve all user work already present in the working tree.
- Prefer archival moves over deleting historical documentation.
- Do not begin work beyond Phase 30.
- Keep physical behavior labeled **NOT HARDWARE VERIFIED**.

## Phase 30 completion gates

- Existing v1 and v2 shows produce unchanged output when no tracks are authored.
- Different logical targets can have different levels in the same frame.
- Linear interpolation, step changes, untracked targets, bounded time ranges,
  and neutral gaps are covered by tests.
- Invalid values, malformed keyframes, duplicate IDs, and overlapping resolved
  tracks fail explicitly.
- Relevant tests and the full test suite pass.
- Physical behavior remains **NOT HARDWARE VERIFIED**.

## Previous completion gates

- Root and documentation indexes point only to current paths.
- Archived material is clearly separated from active instructions.
- Full pytest no longer changes committed acceptance baselines or reports.
- Config and document references resolve after moves.
- The full test suite and required benchmark pass.
- Firmware builds pass if the configured PlatformIO environment remains
  available.

The previous gates passed in the repository-governance completion audit.
All Phase 30 gates passed with the repository test suite at 574 tests.
