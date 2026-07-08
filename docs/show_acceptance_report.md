# Phase 17 Show Acceptance Report

Status: software acceptance evidence generated, with firmware build verification blocked by restricted PlatformIO package downloads.

This acceptance is `NOT HARDWARE VERIFIED`.

## Evidence Summary

- Authored frames: 9000 at 30 FPS for timestamps `n/30`, `n = 0..8999`.
- Two-run digest: `53cf300d290e86065177ccd7e325ec22797f1d98b389f6c908c315f01b9430f2`.
- Digest equality: true.
- Offline capacity from latest CLI run: 489.441 show frames/second.
- Software soak output FPS from latest CLI run: 501.187.
- Golden manifest SHA-256: `28a00eb88e3c3443746d91efa72ea6dcd1e8e49f9619f8b737d3d4ba3f1d4e3f`.
- G8 acceptance SHA-256: `485f2621061b5a8ffd8c140f4743c586473b960856ee258211646c9a4b500f24`.
- Machine-readable evidence: `artifacts/show_acceptance/summary.json`.

## Traceability

| Requirement | Implementation | Test | Evidence |
|---|---|---|---|
| 9000 authored frames | `scripts/show_acceptance.py` renders fixed 300s/30 FPS grid | `tests/test_show_e2e_acceptance.py` | `summary.json.frame_count` |
| Deterministic two-run digest | Two complete offline renders compare SHA-256 | `tests/test_show_e2e_acceptance.py` | `two_run_digests.json` |
| Seam crossing | Acceptance chase over `screen_to_wall` virtual path | `tests/test_show_e2e_acceptance.py` | `seam_concurrency_frames.json` |
| Three concurrent targets | Seam chase, wall wave, ceiling analog cue overlap | `tests/test_show_e2e_acceptance.py` | `seam_concurrency_frames.json` |
| Fade formulas | `transition_weight` samples at start/mid/full/out/end | `tests/test_show_e2e_acceptance.py` | `summary.json.evidence.fade_samples` |
| Music fallback timeline | Procedural `MusicControlState` sections drive adaptive selector | `tests/test_show_e2e_acceptance.py` | `music_decision_timeline.json` |
| Protocol sequence equality | Existing RS-485 v2 and UDP v2 codecs encode/decode selected frames | `tests/test_show_e2e_acceptance.py` | `protocol_sequence_trace.json` |
| Bounded state and soak metrics | Primary run retains selected traces only; soak records queue and timing metrics | `tests/test_show_e2e_acceptance.py` | `benchmark_soak_metrics.json` |

## Limitations

- Firmware builds did not complete because PlatformIO attempted to install missing `ststm32` and `espressif32` platforms and failed with `HTTPClientError` under restricted network.
- No physical RS-485, UDP, STM32, ESP32-S3, RK3588, power, thermal, or visual validation was performed.
- The software soak is simulator/memory/fake transport evidence only.

## Required Physical Follow-Up

- Run the five-minute authored show on RK3588 with production RS-485 and UDP transports.
- Confirm all six RGB+CCT analog nodes render the expected channels without RGBW fallback.
- Confirm the ESP32-S3 node receives one complete UDP v2 frame per logical frame and refreshes once.
- Record real hardware frame drops, thermal/power behavior, bus errors, and safe-state behavior.
