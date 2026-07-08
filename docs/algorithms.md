# Algorithm Reference

## Video Color Analysis

### Average Color
- Frame downscaled to configurable resolution (default 160×90)
- Black border pixels filtered (edge 5% + threshold < 15/255)
- Near-black pixels filtered when ratio < 95%
- Mean of remaining pixels in RGB space
- Temporal smoothing via EMA (alpha=0.15)

### Dominant Color
- Quantized 3D histogram: 8 bins per channel (512 total)
- Pixels quantized to nearest bin, histogram accumulated
- Dominant bin decoded to RGB center value
- Suitable for real-time (no K-means)

### Zone Colors
- Grid partitioning (default 3×3)
- Left, center, right, top, bottom zones
- Per-zone average RGB after black filtering

### Brightness
- Grayscale mean of downscaled frame, normalized to [0,1]

### Saturation
- Mean of HSV S channel, normalized to [0,1]

### Scene Change Detection
- Frame difference between consecutive analysis frames
- Mean absolute difference normalized to [0,1]

### Flash Suppression
- Brightness delta per frame limited by `max_delta_per_frame`

## Audio Analysis

### Frequency Bands
- Bass: 20-200 Hz
- Mid: 200-2000 Hz
- Treble: 2000-12000 Hz
- Bands configurable; capped at Nyquist frequency

### RMS Energy
- Root mean square of audio samples
- Dynamic normalization: P95 of rolling history (3 seconds)
- Scaled to [0,1]

### Band Energy
- FFT with Hanning window (cached, not recreated per frame)
- Power spectrum computed
- Band energy = sum of power in band / total power

### Spectral Flux
- Sum of absolute differences between consecutive spectra
- Normalized by P90 of rolling history

### Beat Detection
- Flux-based: beat when flux > 2.5× EMA-smoothed flux
- Cooldown: ~200ms minimum between beats
- Disabled during silence

### Silence Detection
- RMS < 0.01 after normalization

### Dynamic Normalization
- Rolling history of RMS and band values
- P95 normalization to handle volume differences between tracks

## Music Control Features

Music control consumes `AudioFeatures` history and emits immutable
`MusicControlState` values. It does not select or switch lighting effects.

### Bounds and Windows
- Short history: 2 seconds, capped at 128 frames
- Medium history: 8 seconds, capped at 488 frames
- Long history: 30 seconds, capped at 1808 frames
- Beat-event history: capped at 64 timestamps
- Total stored history bound: 2488 entries
- Tempo support range: 60-180 BPM
- Confidence, phase, strength, regularity, energy, transient, bass ambience,
  bass pulse, and spectral motion are clamped to [0,1]
- Energy trend is clamped to [-1,1]

### Bass Ambience and Pulse
- `bass_ambient` follows sustained low-frequency level with a slow-rising
  baseline
- `bass_pulse` is positive excess above that baseline
- Sustained bass can keep ambience high, but pulse decays after the attack

### Tempo and Confidence
- Beat candidates require positive envelope or bass excess and a refractory
  interval compatible with 60-180 BPM
- BPM is the median interval of bounded beat-event history
- Confidence combines interval inlier ratio, regularity, and minimum evidence
- Low-information or irregular material reports low confidence instead of a
  fabricated strong BPM

## Cue-Bounded Adaptive Effect Selection

Adaptive show cues consume `MusicControlState` and the cue's YAML policy. The
selector never reads raw audio and never chooses an effect outside the cue's
declared `allowed` mapping or explicit fallback.

### Music State Decision Table

Rows are evaluated in order:

| State | Condition |
| --- | --- |
| `silence` | `energy <= 0.03` and `transient <= 0.05` |
| `impact` | `energy >= 0.15` and (`bass_pulse >= 0.65` or `transient >= 0.85`) |
| `energetic` | `energy >= 0.72` and `spectral_motion >= 0.35` |
| `rhythmic` | tempo confidence and beat regularity meet cue thresholds, and `beat_strength >= 0.35` |
| `transition` | `abs(energy_trend) >= 0.25` or `spectral_motion >= 0.50` |
| `ambient` | `bass_ambient >= 0.55` and `bass_pulse < 0.35` |
| `flowing` | `energy >= 0.18`, `spectral_motion >= 0.18`, or `abs(energy_trend) >= 0.12` |
| `calm` | `energy >= 0.04` |
| `silence` | fallback |

### Sync Fallback Decision Table

| Reason code | Sync mode | Condition |
| --- | --- | --- |
| `BEAT_CONFIDENT` | `beat_sync` | tempo confidence and beat regularity meet cue thresholds |
| `EVENT_FALLBACK` | `event_sync` | `transient >= 0.45` or `bass_pulse >= 0.45` |
| `ENVELOPE_FALLBACK` | `envelope_sync` | `abs(energy_trend) >= 0.08` or `spectral_motion >= 0.12` |
| `FREE_RUN_FALLBACK` | `free_run` | no stronger sync evidence |

Additional gate reason codes are `FIXED_CUE`, `HOLD_ACTIVE`,
`COOLDOWN_ACTIVE`, and `STATE_UNCONFIRMED`. Each evaluation emits an immutable
selection decision with show time, state, sync mode, selected and previous
effect names, finite source-feature snapshot, hold/cooldown/confirmation
status, tempo period, speed, and one reason code from this catalog.

When beat sync is active, period is
`beats_per_cycle * 60 / tempo_bpm` after quantizing `beats_per_cycle` to the
configured beat subdivision. Period and speed are smoothed over the cue's
`speed_smoothing_seconds`; low-confidence tempo falls through to event,
envelope, or free run and keeps positive speed.

## Color Conversions

### RGB ↔ HSV
- Standard colorsys module
- Handles hue wrap-around in HSV interpolation

### RGB → RGBW (4 strategies)
1. **NONE**: W = 0, pass-through
2. **MIN**: W = min(R,G,B), subtract from RGB
3. **DESATURATE**: W = min(R,G,B) × (1 - saturation); preserves saturation
4. **PERCEPTUAL**: W = luminance × (0.3 + 0.7 × (1 - saturation)); natural look

Default: DESATURATE (visual natural, preserves approximate brightness)

### Gamma Correction
- sRGB gamma = 2.2
- Applied to output, decoded from input
- Roundtrip preserves within 1% error

## Smoothing & Visual Safety

### Color Smoothing
- EMA per channel: new = α × old + (1-α) × sample
- α = 0.15 (configurable `color_smoothing`)

### Brightness Envelope
- Attack/release envelope with different rates
- Attack: 0.3 (fast response to audio)
- Release: 0.08 (natural decay)
- Limits sudden brightness changes

### Delta Limiting
- Per-frame max color change: 0.15 per channel
- Global max brightness: 0.85
- Global min brightness: 0.01 (black floor)

### Mode Transition
- Crossfade over configurable duration (default 0.5s)

## Lighting Effects

### STATIC
Constant color across all strips and zones.

### BREATH
Sinusoidal brightness oscillation with configurable period (default 4.0s).

### COLOR_WAVE
Hue cycles along strip length. Uses HSV space for smooth color transitions.
Speed configurable.

### CHASE
Delta-time-based running light. Supports: forward, reverse, bounce directions.
Rainbow or video-sourced color. Beat detection boosts speed.

### COMET
Meteor with decaying tail. Multiple active comets per strip.
Tail length and decay rate configurable.

### AUDIO_PULSE
Global brightness follows RMS energy with attack/release envelope.

### BASS_PULSE
Bass energy drives brightness with faster attack (0.6) than release (0.2).

### SPECTRUM
Bass, mid, treble bands mapped to different zones.
Bass → ceiling zones, Mid → wall zones, Treble → front/rear zones.

### VIDEO_AMBIENT
Strip colors smoothed from video zone colors.
Uses per-strip ColorSmoother for independent smoothing.

### VIDEO_AUDIO_FUSION
Core fusion mode:
- Video → base hue and zone colors (weight 0.65)
- Audio RMS → brightness
- Bass → center diffusion pulse
- Mid → saturation boost
- Treble → subtle per-pixel shimmer (capped at 0.4)
- Beat → short brightness pulse
- Silence → preserves ambient video light (no blackout)

### CALM
Ultra-slow hue drift in HSV. Low brightness (max 0.35).
Suitable for relaxation environments.

### DEMO
Auto-rotates through effects at configurable interval (default 10s).
Maintains per-effect state across rotations.
