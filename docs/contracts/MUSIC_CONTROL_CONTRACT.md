# Show Orchestration V1 — Music Control and Selection Contract

This document is the single authority for music-derived control and adaptive selection.

## Separation of concerns

Phase 15 derives control features. It MUST NOT choose lighting effects.
Phase 16 consumes those features and YAML policy. It MUST NOT reimplement raw audio analysis.

## Required control state

The control state includes finite, documented values for tempo, confidence, beat phase/strength/regularity, energy/trend, transient, sustained bass ambience, bass pulse, and spectral motion.

`bass_ambient` represents sustained low-frequency level. `bass_pulse` represents positive transient excess above a smoothed baseline. A sustained pad may keep ambient high, but pulse MUST decay after attack.

## Confidence behavior

Low-information or irregular music yields low tempo confidence. The system MUST NOT fabricate a strong BPM merely to keep beat sync active.

## Fallback order

```text
reliable beat sync
→ event/onset sync
→ envelope/trend sync
→ free-running animation with bounded subtle modulation
```

Low confidence never sets speed to zero and never stops animation.

## YAML authority

YAML is the director. Adaptive selection may instantiate only effects declared by the cue's `allowed` mapping or explicit fallback. Fixed cues remain fixed; they may still use music modulation implemented by their effect without entering the selector.

## Decision evidence

Every adaptive decision exposes an immutable evidence record containing at least:

- `show_time`
- `music_state`
- `sync_mode`
- `selected_effect`
- `previous_effect`
- `reason_code`
- relevant source-feature snapshot
- hold/cooldown/confirmation status

The reason code MUST come from a documented finite set. Free-form explanations alone are insufficient evidence.
