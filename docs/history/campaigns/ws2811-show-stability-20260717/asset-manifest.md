# Key Asset Manifest

This human-readable manifest identifies the field binaries and current Host
oracles. `SHA256SUMS.txt` remains the complete machine-readable inventory.

## Field application images

| File | Bytes | SHA-256 |
|---|---:|---|
| `firmware/node2/firmware.bin` | 727456 | `469631595379B5436CB1D1212419B7F6D6B45E2A77C60A602133896DCADBAFD0` |
| `firmware/node8/firmware.bin` | 727952 | `C5BAC80C948578AC3EA6D0873D004795B0C42B97C0221BA05F1EB56D8126A44B` |

Both were read from onsite flash offset `0x10000` with esptool 4.11.0 and
exactly matched the previously recorded identities. See
`firmware/READBACK_RECORD.md`.

## Active profile

| File | SHA-256 |
|---|---|
| `host/config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml` | `1F035FC715A8FEF9B3DD0CF6A3EC3938EADD31BB4FCE92A8E2D870BAC1F9018D` |

## Key Shows

| File | SHA-256 |
|---|---|
| `ws2811-ab-two-node-blue-breath-isolation-39s.yaml` | `C62F4B1D3A3ED0AC29005F3E9F9FF4E816F7F5EC88B537C4AB87366C689D20C3` |
| `ws2811-ab-two-node-blue-breath-isolation-74s.yaml` | `EF2097C8B32CB968A3FB13BEF64860034CDAFF93B76D0FC351B4915C4E67CE8D` |
| `ws2811-ab-two-node-blue-breath-staged-75s.yaml` | `9F606DC467CB26A37C753D8E418AF6B78D1D80CB96A0F4A9CFDE7338B8880364` |
| `ws2811-ab-two-node-all-effects-171s.yaml` | `AB4E4445AB1C4F32543C60E45EBBF815C1C03150386B6AF17A4293D59283CFE2` |
| `ws2811-ab-two-node-virtual-path-color-comet-32s.yaml` | `8662A532A9CEDB1F1F101BAD5F63570838367C125C26117ACFD65B594249A21B` |

All paths are below `host/config/shows/`.

## Focused Host tests

| File | SHA-256 |
|---|---|
| `test_ws2811_two_node_breath_isolation_show.py` | `13D1C8D74A2556088D9F8B22C206B2E7975EA4EBD7D13B5C9FBCF7E18B566C7E` |
| `test_ws2811_two_node_breath_show.py` | `F9B92C2D8B8325ADF9D5074B4306AD2745338C6124B0A1B7352F2E4AEAB54B28` |
| `test_ws2811_two_node_all_effects_show.py` | `E70B284F487B2D15945A530808A016C232762D87160F110D6FBE3989064CA323` |
| `test_ws2811_two_node_virtual_path_comet_show.py` | `A0EC4E3EEC9E24168F38B155FEB46CC6F2A10AF57075C7864A74B29F0EC3620F` |

All paths are below `host/tests/`. These tests prove Host contracts only.

## Evidence documents

| File | SHA-256 |
|---|---|
| `docs/ws2811-show-stability-investigation.md` | `C9110229510BE42A390563E24DA99A499915F514DB00C0DC38D31E418D161C19` |
| `docs/ws2811-emergency-handoff.md` | `D292A6387CBA3E9972E3E3DFD0306408CC74805751909CE36A58322734168CAD` |

The snapshot is a complete diagnostic checkpoint but remains **NOT HARDWARE
VERIFIED** for production. Rare wrong-color events are still open.
