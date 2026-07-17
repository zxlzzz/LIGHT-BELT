# Test and Show Purposes

Every Python test below is a software/Host test unless explicitly paired with
an onsite visual run and serial stats. Passing Python does not prove physical
WS2811 stability.

## Focused Python tests

| File | Purpose | Passing does not prove |
|---|---|---|
| `test_ws2811_breath_show.py` | Validate strip41 blue-breath Host frames, transform, UDP payloads, black state, and quantized levels. | The strip will not jump color. |
| `test_ws2811_breath_trace_replay.py` | Validate frozen trace serialization, semantic hash, and replay input stability. | Physical replay is correct. |
| `test_ws2811_emergency_gate1m_show.py` | Validate the 600-frame Gate1m payload sequence, SAFE, state holds, and write/skip budget. | SPI6 or the strip is stable. |
| `test_ws2811_emergency_node8_two_node.py` | Validate Node8-only and two-node emergency addresses, topology, Shows, and dedupe budgets. | Two-node hardware passes. |
| `test_ws2811_emergency_show.py` | Validate Node2 emergency whitelist states, KEY use, and physical-write count. | Whitelisted colors are physically safe. |
| `test_ws2811_node8_breath_show.py` | Prove a Node8-only breath sends only to `.208` with 20 uniform blue groups. | Strip42 or an inactive strip remains stable. |
| `test_ws2811_staged_shows.py` | Preserve older QIO, Stage1/2/3 mapping, packet, and long memory-transport contracts. | The current VCCB=5 V fixture or installed site passed. |
| `test_ws2811_two_node_all_effects_show.py` | Prove all 17 registered effects load and render both strip41 and strip42. | Those effects or colors are physically safe. |
| `test_ws2811_two_node_breath_isolation_show.py` | Validate the 74-second 41-only/42-only/both timeline and Host packet contract. | A short no-event run is a reusable repair. |
| `test_ws2811_two_node_breath_show.py` | Validate the staged 75-second breath, in-phase Host content, and dedupe budget. | Simultaneous physical playback is stable. |
| `test_ws2811_two_node_virtual_path_comet_show.py` | Prove one comet crosses the 41/42 logical seam, reverses the whole path, and changes hue. | The physical seam is gap-free or strictly synchronized. |

## Foundational tests included in the snapshot

| File | Purpose |
|---|---|
| `test_effects.py` | Registry and renderer contracts for all effects, including the discrete investigation effects. |
| `test_show_v2.py` | Authored Show v2 parsing, origin modes, virtual-path order, and override behavior. |
| `test_virtual_paths.py` | Continuous virtual-coordinate splitting and seam behavior independent of node assignment. |
| `test_compositor.py` | Target-scoped composition and virtual-path conversion back to physical strips. |

## Evidence tools

| File | Purpose |
|---|---|
| `monitor_esp32_stats.py` | Capture complete COM7/COM13 stats without DTR/RTS resets; it records but does not visually judge. |
| `replay_ws2811_breath_trace.py` | Prepare, validate, and replay a frozen UDP trace to remove live effect-rendering variability. |

## Current A/B and exploratory Shows

| Show | Purpose |
|---|---|
| `ws2811-ab-strip41-blue-10s.yaml` | Node2 static-blue smoke test. |
| `ws2811-ab-strip41-rgb-static-steps.yaml` | Static R/G/B order and uniformity control. |
| `ws2811-ab-strip41-blue-breath-40s.yaml` | Isolate strip41 breath behavior. |
| `ws2811-ab-strip42-blue-breath-40s.yaml` | Isolate strip42 breath behavior. |
| `ws2811-ab-two-node-blue-breath-staged-75s.yaml` | Compare Node8-only with simultaneous changing outputs. |
| `ws2811-ab-two-node-blue-breath-isolation-39s.yaml` | Short 41-only/42-only/both discriminator. |
| `ws2811-ab-two-node-blue-breath-isolation-74s.yaml` | Longer form of the same discriminator to increase event exposure. |
| `ws2811-ab-two-node-all-effects-171s.yaml` | Explore every registered effect; not a safe-palette test. |
| `ws2811-ab-two-node-virtual-path-color-comet-32s.yaml` | Observe one color-changing comet crossing and reversing over both strips. |

## Emergency Shows

| Show | Purpose |
|---|---|
| `ws2811-emergency-black-sentinel-3s.yaml` | Force and observe a directed black state; black alone does not prove color data. |
| `ws2811-emergency-node2-strip41-blue-60s.yaml` | Restricted Node2 blue flow/breath experiment for its matching emergency firmware. |
| `ws2811-emergency-node2-strip41-110s.yaml` | Restricted Node2 pulse, blue flow, and orange flow sequence. |
| `ws2811-emergency-node2-strip41-gate1m-120s.yaml` | Expanded Node2 control/theater/static/orange gate with exact state budgets. |
| `ws2811-emergency-node8-strip42-blue-60s.yaml` | Restricted Node8 mirror path. |
| `ws2811-emergency-two-node-blue-staged-110s.yaml` | Restricted Node2-only, Node8-only, and joint blue flow comparison. |
| `ws2811-emergency-two-node-green-static-staged-35s.yaml` | Static green routing and isolation control. |

## Historical and architecture Shows

| Show | Purpose |
|---|---|
| `ws2811-diagnostic-strip41-only.yaml` | Early strip41 target-routing smoke test. |
| `ws2811-diagnostic-strip42-only.yaml` | Early strip42 target-routing smoke test. |
| `ws2811-diagnostic-strip41-strip42.yaml` | Early dual-target routing smoke test. |
| `ws2811-node2-lane-isolation.yaml` | Historical Node2 SPI-lane isolation input. |
| `ws2811-qio-node2-static-lanes.yaml` | Historical QIO static-lane experiment. |
| `ws2811-stage1-strip41-nine-effects.yaml` | Older single-strip nine-effect software/hardware gate. |
| `ws2811-stage2-strip41-to-strip42.yaml` | Logical cross-fade from strip41 to strip42. |
| `ws2811-stage3-full-300s.yaml` | Thirteen-strip full topology and long transport target. |
| `ws2811-stage3-installed-300s.yaml` | Installed-topology variant of the Stage3 run. |
| `ws2811-strip42-gpio4-split-pattern.yaml` | Historical first/last group split diagnostic. |
| `ws2811-strip42-gpio4-static.yaml` | Historical strip42 GPIO4 static control. |

Only a matching firmware/profile/Show, real visual record, exact serial counter
deltas, and final SAFE black state can create hardware evidence.
