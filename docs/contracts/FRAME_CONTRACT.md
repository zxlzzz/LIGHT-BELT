# Show Orchestration V1 — Frame Contract

This document is the single authority for logical frame and contribution semantics used by Phases 12–17.

## Identity and timing

Every final logical frame carries exactly one show timestamp and one sequence number. Composition, physical mapping, RS-485 encoding, UDP encoding, and memory/JSON evidence MUST preserve that frame identity. A component MUST NOT invent a second sequence for the same authored frame.

## Contribution states

A target or pixel has two distinct states:

1. **Absent / no contribution** — the effect does not participate. Existing lower-priority content remains unchanged.
2. **Explicit value** — the effect participates. An explicit value may be black/zero and therefore may intentionally extinguish prior content under `replace`.

Missing targets and pixels outside a selected partial range MUST be absent. Implementations MUST NOT materialize them as black placeholders.

## Target domains

Analog and digital targets are different typed domains even if their text IDs match. Analog values use RGBCCT channels; digital values use RGB pixels. Conversion between these domains is not implicit.

## Immutability

Effects, target masks, virtual-path splitting, and the compositor MUST NOT mutate input frames, input contributions, color objects, or pixel lists in place. A composed result is a new value.

## Numeric validity

All channels are finite normalized values in `[0, 1]` after composition. NaN and infinity are invalid. Clamp operations apply only where a contract explicitly specifies clamping; invalid non-finite values MUST fail rather than silently clamp.

## Virtual-path output

A virtual-path effect produces one global path buffer. Splitting that buffer creates target contributions. Unmapped virtual gap coordinates create no destination contribution.

## Compatibility

When no show runtime is active, the pre-existing single-effect logical frame behavior remains unchanged.
