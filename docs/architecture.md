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
2. **Analysis**: VideoAnalyzer and AudioAnalyzer extract features
3. **Context**: EffectContext bundles features with timing and parameters
4. **Effect**: Active effect processes context → PixelFrame
5. **Output**: PixelFrame sent to all enabled output backends

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
