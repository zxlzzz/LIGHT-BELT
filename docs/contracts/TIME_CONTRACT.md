# Show Orchestration V1 — Time Contract

This document is the single authority for authored show time.

## Cue intervals

Cue intervals use half-open semantics `[start, end)`:

- `t < start`: inactive
- `t == start`: active
- `start <= t < end`: active
- `t == end`: inactive

Show frames are authored for `0 <= t < duration`.

## Context times

Every cue receives:

```text
show_time = t
cue_local_time = t - cue.start
```

Cue-local time starts at zero regardless of where the cue begins in the show.

## Pause

Repeating the same timestamp represents pause. Time-dependent state MUST NOT advance.

## Reset and backward time

A normal run uses monotonically non-decreasing timestamps. A backward timestamp is an error unless the caller performs an explicit reset/replay operation. Arbitrary stateful random-access reconstruction is not a V1 guarantee.

`reset()` recreates all cue-level effect instances and deterministic cue seeds. Repeating a run with the same configuration, inputs, timestamps, and seed MUST reproduce the same authored frames.

## Transition weight

```text
fade_in_factor  = 1 if fade_in == 0 else clamp((t - start) / fade_in, 0, 1)
fade_out_factor = 1 if fade_out == 0 else clamp((end - t) / fade_out, 0, 1)
weight          = min(fade_in_factor, fade_out_factor)
```

This formula is not renormalized when fade windows overlap.

## Offline acceptance grid

The 300-second, 30 FPS offline acceptance evaluates exactly:

```text
t_n = n / 30, for n = 0..8999
```

A shutdown black frame is lifecycle output and is not one of the 9000 authored frames.
