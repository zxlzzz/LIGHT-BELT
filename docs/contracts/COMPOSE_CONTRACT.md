# Show Orchestration V1 — Composition Contract

This document is the single authority for composition order and formulas.

## Ordering

Active contributions are applied in this deterministic order:

```text
(priority ascending, declaration_index ascending)
```

Later contributions in that order apply later. Dictionary/hash iteration order MUST NOT influence output.

## Unweighted blend modes

For participating values only:

- `replace`: `out = incoming`
- `add`: `out = clamp(base + incoming, 0, 1)`

`add` is applied independently to digital R/G/B and analog R/G/B/WW/CW channels.

Absent values do not participate and leave `base` unchanged. Explicit black participates normally.

## Weighted blend modes

Given transition weight `w` in `[0, 1]`:

- weighted `replace`: `out = base * (1 - w) + incoming * w`
- weighted `add`: `out = clamp(base + incoming * w, 0, 1)`

The same formulas apply to every participating channel/pixel. There is no hidden gamma, renormalization, or channel coupling in V1.

## Base frame

The show compositor starts from one explicit black base covering configured targets. Timeline absence produces no contributions; it is not itself a black contribution.

## State isolation

Every cue owns its own effect instance and mutable effect state. Two cues naming the same effect MUST NOT share random state, phase state, tail buffers, or caches.
