# Configuration Reference

All configuration files are in `config/` and loaded as YAML.

## system.yaml

| Key | Type | Default | Unit | Range | Description |
|-----|------|---------|------|-------|-------------|
| system.version | string | "0.1.0" | - | - | Software version |
| system.output_fps | float | 30.0 | Hz | 1-120 | Light output frame rate |
| system.video_analysis_fps | float | 10.0 | Hz | 1-60 | Video analysis rate |
| system.audio_update_fps | float | 60.0 | Hz | 1-240 | Audio feature update rate |
| system.audio.sample_rate | int | 44100 | Hz | 8000-192000 | Target audio sample rate |
| system.audio.window_size | float | 0.05 | s | 0.01-1.0 | FFT window size |
| system.audio.hop_size | float | 0.025 | s | >0 | Hop between FFT windows |
| system.audio.history_duration | float | 3.0 | s | 0.1-60 | Rolling history for normalization |
| system.audio.freq_bands.bass | [int,int] | [20,200] | Hz | - | Low frequency range |
| system.audio.freq_bands.mid | [int,int] | [200,2000] | Hz | - | Mid frequency range |
| system.audio.freq_bands.treble | [int,int] | [2000,12000] | Hz | - | High frequency range |
| system.smoothing.color_smoothing | float | 0.15 | - | 0-1 | EMA alpha (0=instant) |
| system.smoothing.brightness_attack | float | 0.3 | - | >0 | Attack rate for brightness |
| system.smoothing.brightness_release | float | 0.08 | - | >0 | Release rate for brightness |
| system.smoothing.max_brightness | float | 0.85 | - | 0-1 | Global max brightness |
| system.smoothing.min_brightness | float | 0.01 | - | 0-1 | Black floor |
| system.smoothing.max_delta_per_frame | float | 0.15 | - | 0-1 | Max color change per frame |
| system.smoothing.flash_suppression | float | 0.5 | - | 0-1 | Flash suppression |
| system.smoothing.transition_duration | float | 0.5 | s | >0 | Mode switch crossfade |
| system.smoothing.gamma | float | 2.2 | - | >0 | Global gamma |
| system.video.analysis_size | [int,int] | [160,90] | px | - | Downscale resolution |
| system.video.black_threshold | int | 15 | - | 0-255 | Pixel value considered black |
| system.video.black_ratio_limit | float | 0.95 | - | 0-1 | Dark frame threshold |
| system.video.zone_grid | [int,int] | [3,3] | - | - | Zone partitioning |
| system.video.scene_change_threshold | float | 0.15 | - | 0-1 | Scene change sensitivity |
| system.logging.level | string | "INFO" | - | DEBUG/INFO/WARNING/ERROR | Log level |
| system.logging.per_frame_log | bool | false | - | - | Enable per-frame logging |
| system.logging.error_rate_limit | int | 10 | /min | - | Max identical errors/min |

## layout.yaml

Defines logical analog zones, digital strips, physical node mapping, and
authored virtual paths.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| layout.total_strips | int | 6 | Total number of strips |
| layout.zones | list | 6 items | RGB+CCT zone definitions |
| layout.strips | list | 6 items | Digital strip definitions |
| layout.virtual_paths | list | [] | Continuous virtual digital-strip paths |

Zone definition:
| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique zone identifier |
| type | string | "rgbcct" (analog) |
| label | string | Human-readable name |

Strip definition:
| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique strip identifier |
| type | string | "digital" |
| pixel_count | int | Number of pixels (>0) |
| direction | string | "forward" or "reverse" |
| video_zone | string | Mapped video region |

Virtual path definition:
| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique virtual path identifier used by show targets |
| segments | list | Non-empty ordered list of path segments |

Virtual path segment:
| Field | Type | Description |
|-------|------|-------------|
| strip_id | string | Existing logical digital strip id |
| source_start | int | First source pixel in the logical strip; defaults to 0 only when omitted |
| pixel_count | int | Positive number of mapped pixels |
| direction | string | "forward" or "reverse"; reverse changes destination order only |
| gap_after_pixels | int | Optional authored unmapped pixel coordinates after this segment; defaults to 0 |

Virtual path coordinates are continuous integers from `0` to
`total_virtual_length - 1`. Segment intervals and gap intervals cover that
range exactly. `gap_after_pixels` extends animation time/phase but produces no
physical destination contribution. V1 supports authored pixel gaps only;
millimetre calibration and unequal pixels-per-metre compensation are out of
scope.

## effects.yaml

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| effects.active | string | "demo" | Active effect |

Per-effect parameters documented in effects.yaml comments.

## outputs.yaml

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| outputs.enabled | list | ["simulator","json"] | Active output backends |
| outputs.json.path | string | "output/light_data.jsonl" | JSONL output path |
| outputs.udp.host | string | "192.168.1.100" | ESP32-S3 IP |
| outputs.udp.port | int | 9001 | UDP port |
| outputs.udp.max_packet_size | int | 1400 | Max UDP payload |
| outputs.serial.port | string | "COM3" | STM32 serial port |
| outputs.serial.baudrate | int | 115200 | Baud rate |
