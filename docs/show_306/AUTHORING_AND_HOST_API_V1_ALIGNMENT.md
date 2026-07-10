# Show Authoring and Host API V1 Alignment

This guide keeps two interfaces separate:

- **Show authoring** is the versioned `show.yaml` input consumed by the
  LIGHT-BELT engine. Authors define the timeline, cue selection, and logical
  targets.
- **Host API V1** is the APP-facing REST/WebSocket contract described in
  [`../host_api_v1.md`](../host_api_v1.md). It exposes runtime controls and
  capabilities through Host Service; it is not a YAML editing API.

The examples below use fields implemented by the completed authoring phases
through Phase 22. They do not add Host API values or runtime behavior.

## 1. Keep the identifiers separate

| Namespace | Example | Meaning | Do not confuse it with |
|---|---|---|---|
| Cue ID | `opening-screen-to-wall` | `cue.id` is a unique timeline entry within one `show.yaml`. It identifies when and how a cue runs. | A target, device, or Host API value. |
| Show target | `target: {type: virtual_path, id: screen_to_wall}` | `target.type` selects a show resolver; `target.id` names one logical object. `target.ids` selects members for `analog_group` or `digital_group`. | `cue.id`, a physical node address, or an API field by itself. |
| Physical/layout ID | `11`, `41`, `91` | An installation/mapping planning identifier for a controller, output, or segment. It belongs in physical/layout planning. | `target_id`; it is **not** automatically visible to an APP. |
| Host API target | `virtual_path.screen_to_wall` | `target_id` is a Host Service capability exposed to the APP. | The YAML `target.id` string, unless Host Service deliberately maps it. |

`cue.id`, `target.id`, and a physical ID are therefore three different
identifiers. The values `11`, `41`, `91`, `92`, and `93` must not be placed in
an APP request as `target_id` merely because they appear in an installation
plan. Physical IDs are exposed to the APP only if a future API explicitly
defines that mapping.

For planned physical IDs `91`/`92`/`93`, keep the devices and segments in the
physical layout plan. Enabling, disabling, or rerouting them should normally
be a mapping/layout change, not a rewrite of show cues. A cue remains aimed at
its logical target, such as `screen_to_wall` or `wall_right`.

## 2. Author a cue in `show.yaml`

The current top-level shape is `schema_version` plus `show`. A show has an
`id`, `duration` in seconds, optional `defaults`, and `cues`. Every cue has a
unique `id`, `start` and `end` in show seconds, a non-negative `priority`, a
`target`, and an `effect`. It can also have `transition`, `audio_control`, and
`audio_modulation`.

| Cue field | Authoring meaning |
|---|---|
| `id` | Unique cue identifier within the show. It is not a target ID. |
| `start`, `end` | Cue interval in seconds; `end` must be after `start` and no later than `show.duration`. |
| `priority` | Tie-breaking priority when cues overlap. |
| `target.type` | Resolver kind: `analog_zone`, `digital_strip`, `analog_group`, `digital_group`, `virtual_path`, `all_analog`, `all_digital`, or `all`. |
| `target.id` | One logical target for a single-target type. |
| `target.ids` | Logical member IDs only for `analog_group` and `digital_group`; it is not a list of physical node IDs. |
| `effect` | Fixed or adaptive effect definition; see the next section. |
| `transition.fade_in`, `transition.fade_out` | Cue-local fade times in **seconds**. `blend`, `min_effect_hold`, and `switch_cooldown` are also authoring fields. |
| `audio_control` | Adaptive-selection and tempo-control policy. |
| `audio_modulation` | Continuous cue-local brightness/speed/intensity multipliers. |

Example: a fixed cue aimed at the logical virtual path. `screen_to_wall` is
resolved by the layout; it is not a controller address.

```yaml
- id: opening-screen-to-wall
  start: 0.0
  end: 20.0
  priority: 10
  target:
    type: virtual_path
    id: screen_to_wall
  effect:
    mode: fixed
    name: chase
    parameters:
      speed: 9.0
      width: 6
      gap: 12
      color_source: video
  transition:
    fade_in: 2.0
    fade_out: 2.0
```

Validate an authored show before playback:

```powershell
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show.example.yaml
```

## 3. Effect mode, name, and parameters

`effect.mode` is either `fixed` or `adaptive`:

- A `fixed` effect requires `effect.name` and may set
  `cue.effect.parameters`. The parameter names must be valid for that effect.
- An `adaptive` effect has no `effect.name`. It defines the music-state map in
  `effect.allowed` and a `effect.fallback` selected from that map. Its
  `audio_control` policy determines how the adaptive selector evaluates music
  state and tempo.

`cue.effect.parameters` are typed, engine-facing YAML values. They override
the corresponding `effects.yaml` defaults for that cue render only. They are
not a Host API request body.

### `color_timeline` (implemented authoring feature)

`color_timeline` is an implemented fixed-effect parameter for `static`,
`breath`, `audio_pulse`, `bass_pulse`, and `calm`. It supplies a cue-local
smooth RGB transition. It uses only `rgb_linear`, needs at least two strictly
increasing keyframes, and uses RGB floats in `[0.0, 1.0]`. Before/after the
keyframes, the first/last color is held. It is not supported by `chase` or
`comet`.

```yaml
effect:
  mode: fixed
  name: static
  parameters:
    color_timeline:
      interpolation: rgb_linear
      keyframes:
        - time: 0.0
          color: [1.0, 0.25, 0.05]
        - time: 6.0
          color: [1.0, 0.75, 0.20]
        - time: 14.0
          color: [0.20, 0.45, 1.0]
```

The keyframe `time` values are seconds relative to `cue.start`, not absolute
show times and not API milliseconds. When `color_timeline` is present, its
color takes precedence over `parameters.color` for that cue-local time.

### `audio_control` versus `audio_modulation` (implemented authoring features)

These similarly named fields have different jobs:

| Field | Job | Use with |
|---|---|---|
| `audio_control` | Selects/tempo-controls an **adaptive** effect using fields such as `tempo_sync`, `tempo_confidence_min`, `beat_regularity_min`, `no_beat_fallback`, `beats_per_cycle`, `beat_subdivision`, `speed_smoothing_seconds`, `state_confirmation_seconds`, `min_effect_hold`, and `switch_cooldown`. | `effect.mode: adaptive` |
| `audio_modulation` | Continuously multiplies `brightness`, `speed`, and/or `intensity` for one cue. Each channel has `source`, `amount`, `min_multiplier`, `max_multiplier`, and `smoothing_seconds`. | Fixed or adaptive cue, where the selected effect preserves the intended dimension. |

`audio_modulation` sources are validated engine feature names, for example
`music.energy`, `music.beat_strength`, and `music.bass_pulse`. Missing audio
data produces neutral multipliers rather than selecting a different effect.

```yaml
audio_modulation:
  brightness:
    source: music.energy
    amount: 0.5
    min_multiplier: 0.5
    max_multiplier: 1.5
    smoothing_seconds: 0.2
  speed:
    source: music.beat_strength
    amount: 0.5
    min_multiplier: 0.5
    max_multiplier: 1.5
    smoothing_seconds: 0.2
```

## 4. Virtual paths are logical, continuous paths

`target.type: virtual_path` renders one path-sized logical pixel buffer. The
layout maps its continuous coordinates to ordered digital-strip subranges;
the effect never needs to know ESP32 node IDs, UDP hosts, ports, or segment
offsets. A reversed segment reverses destination pixel order only—it does not
restart or reverse the global animation phase.

`gap_after_pixels` creates unmapped virtual coordinates. A moving effect
continues through the gap, but the gap produces no physical pixels. V1 uses
integer pixel coordinates and authored pixel gaps only; millimetre
calibration and unequal pixels-per-metre compensation are not implemented.

Virtual paths therefore express show intent. Physical routing remains in the
layout/mapping layer, so adding or changing a mapped physical node does not
turn that node ID into a show `target.id` or an APP `target_id`.

## 5. Host API V1 mapping boundary

Host Service translates its APP-facing contract into runtime behavior. The
following table is an alignment guide, not a claim that the fields have the
same wire format or that the APP may edit YAML.

| Internal show authoring | Host API V1 external concept | Boundary rule |
|---|---|---|
| `show.id` | `show_id` in `/shows`, playback state, and playback commands | The APP chooses/observes a loaded show; it does not upload or edit its cue list. |
| `show.duration` (seconds) | `duration_ms` (milliseconds) | Host Service converts units for its external response. |
| `cue.id` | None | A cue ID is internal timeline identity; there is no Host API V1 cue-edit endpoint. |
| `target.type` plus `target.id`/`target.ids` | `target_id` | Only Host Service maps logical show targets to APP-visible capability targets. For example, `target.type: virtual_path` with `id: screen_to_wall` maps to `target_id: virtual_path.screen_to_wall` when that capability is exposed. |
| `effect.name` for a fixed cue | `effect_type` | The effect naming vocabulary aligns, but fixed/adaptive cue selection remains show-runtime behavior. |
| `cue.effect.parameters` | `params` and `effect_params` | Host Service interprets and splits APP generic/effect-specific request values. These structures are **not** identical wire formats: YAML color timelines use normalized RGB arrays, while the API example uses `params.color.r/g/b` values; API `params`/`effect_params` do not author a cue timeline. |
| `transition.fade_in` / `transition.fade_out` (seconds) | `transition_ms` (milliseconds) | A cue has separate fade-in/out authoring semantics; the API exposes one runtime transition value. Do not copy the numeric values without unit/semantic conversion. |
| `audio_control`, `audio_modulation`, `color_timeline` | None in an API request | These are authored runtime policies, not Host API V1 `params` or `effect_params` schemas. |
| Physical node/segment IDs, for example `11`, `41`, `91` | None by default | They remain installation/mapping identifiers and are not automatically APP-facing `target_id` values. |

The APP should discover its valid `target_id` and `effect_type` values from
`GET /capabilities`, then use the documented `/shows`, `/playback/*`,
`/lights/set`, and `/effects/set` interfaces. Runtime state and WebSocket
messages use the documented `show_id`, `duration_ms`, `brightness`,
`color_temperature`, `audio_available`, `video_available`,
`audio_link_enabled`, and `video_link_enabled` names. Host API V1 does **not**
provide a way for an APP to directly add, change, reorder, or delete
`show.yaml` cues.

## 6. PC-first debugging and deployment boundary

Use a PC-first workflow while authoring:

1. Edit `show.yaml`, `layout.yaml`, and effect configuration as logical,
   version-controlled inputs.
2. Run `validate-show` on the PC and resolve YAML/schema errors before output
   testing.
3. Exercise the show with the configured development/simulation setup and
   inspect logical target and virtual-path behavior.
4. Move the validated configuration to the single production Host and test
   the physical mapping there. Hardware behavior remains **NOT HARDWARE
   VERIFIED** until it is observed on the installed system.

For final synchronized multi-node shows, use one Host as the source of the
logical frame, sequence, and timestamp. Do not use multiple computers to send
independently to the same ESP32 nodes: competing senders can break the
single-frame ordering and synchronization assumptions. Additional computers
may be used for offline authoring, validation, or observation, but not as
concurrent output hosts for the same installation.
