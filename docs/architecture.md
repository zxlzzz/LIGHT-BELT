> [!NOTE]
> This document describes the current v1 software architecture.
> Target v2 architecture is defined by docs/CLOSED_LOOP_SPEC.md.

# Architecture

## Module Overview

```
┌──────────────────────────────────────────┐
│                  CLI                      │
│   demo | run | simulator | export | bench │
└──────────────────┬───────────────────────┘
                   │
┌──────────────────▼───────────────────────┐
│                Engine                     │
│  Timeline | Fusion | Effect Mgr | Output │
└──┬─────────┬─────────┬──────────┬───────┘
   │         │         │          │
┌──▼──┐ ┌───▼───┐ ┌───▼───┐ ┌───▼──────┐
│Media│ │Analysis│ │Effects│ │ Outputs   │
│ I/O │ │Video   │ │12 fx  │ │Null/Json  │
│     │ │Audio   │ │        │ │Sim/UDP/Ser│
└─────┘ └───────┘ └───────┘ └──────────┘
```

## Data Flow

1. **Input**: Media files or SyntheticDataSource produce raw frames/samples
2. **Analysis**: VideoAnalyzer and AudioAnalyzer extract low-level features
3. **Music control**: MusicControlAnalyzer derives bounded control state from
   AudioFeatures history without selecting effects
4. **Context**: EffectContext bundles features with timing and parameters
5. **Effect**: Active effect processes context → PixelFrame
6. **Output**: PixelFrame sent to all enabled output backends

## Virtual Paths

Virtual paths concatenate authored logical digital-strip subranges into one
continuous integer coordinate space. A virtual-path effect renders one complete
path-sized buffer in global coordinates, then the mapping layer splits that
buffer into sparse strip-range contributions. Reversed segments reverse only
the destination pixel order; they do not restart or reverse global animation
phase.

Authored `gap_after_pixels` values create unmapped virtual coordinates that
advance animation phase and time while producing no physical destination
contribution. Pixels outside selected partial-strip ranges remain absent/no
contribution. ESP32 node assignment and UDP routing are handled later by
physical mapping and do not affect virtual path coordinates.

## Thread Model

Current implementation is single-threaded. Engine time is owned by an injectable
clock: deterministic internal/offline clocks for tests and exports, and an mpv
JSON IPC clock for playback-synchronized runs. Analysis runs inline at
configurable rates (video: 10Hz, audio: 60Hz, output: 30Hz).

Future: Offload analysis to background threads for RK3588.

## Timeline Design

- All timestamps in seconds (float)
- Engine receives the unified timeline from its configured clock
- Frame period = 1/output_fps
- Analysis rates independently configurable
- Synthetic data has configurable duration (default 120s)
- Seek jumps reset stateful analyzers and effects while preserving engine-owned
  sequence numbers
- Paused media keeps output deterministic and skips analysis updates

## Performance Strategy

- Video frames downscaled to 160x90 for analysis
- Color quantization with 8 bins/channel (512 colors)
- FFT window and frequency bins cached
- No per-frame config reloading
- No per-frame FFT initialization
- NullOutput for pure computation benchmarking

## Degradation Strategy

- No video → synthetic or dark ambient fallback
- No audio → silent features, video-only effect
- No video + no audio → CALM or STATIC fallback
- Output failure → isolate, log, continue with remaining outputs
- GUI unavailable → terminal simulator or JSONL export
