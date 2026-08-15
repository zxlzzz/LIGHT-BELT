# LIGHT-BELT

LIGHT-BELT's current/default deployment is DDP to nine independent WLED
boards: node 1 `strip_32` (40), node 2 `strip_41` (10), node 3 `strip_44`
(20), node 4 `strip_12` (40), node 5 `strip_22` (40), node 6 `strip_31`
(10), node 7 `strip_43` (20), node 8 `strip_11` (10), and node 9 `strip_21`
(10). Every board has only `output_id: 1`; GPIO16 is topology metadata only.
This Profile has no RGB+CCT zones, analog nodes, STM32 devices, or RS-485
transport. **NOT HARDWARE VERIFIED.**

The topology, protocol, and scheduled-presentation software contracts are
accepted by the final regression suite.
Physical wiring, endpoint assignment, power distribution, cross-node timing,
and visible output remain **NOT HARDWARE VERIFIED**.

The Host default is the ignored runtime Profile
`config/runtime/wled-ddp-mdns.yaml`. In real mode it runs
`scripts/resolve_nodes.py` against the tracked WLED template, resolving unique
Avahi names `wled-strip-<label>.local`. An unresolved board is disabled; DDP
continues to every other board without stale-address/cache, HTTP, MAC-derived,
or subnet-scan fallback. All nine `strip_*` targets remain available to the
Host API. **NOT HARDWARE VERIFIED.**

`config/profiles/udp-v3-nine-strip-maintenance.yaml` is for custom UDP v3
firmware only; WLED cannot receive project UDP v3. Stop output, select a
Profile through `ENGINE_PROFILE_PATH`, and restart the Host to change modes.
The APP has no live transport/Profile switch. The older 13-controller,
RGB+CCT/STM32, RS-485, and UDP v3 production descriptions below are historical
compatibility material, not the current/default installation.

## Start here

- [Install and run](INSTALL_AND_RUN.md)
- [Documentation index](docs/README.md)
- [Cabin operator guide](docs/current/cabin-lighting-v3-operator-guide.md)
- [Show v2 authoring](docs/current/show-v2-authoring.md)
- [Effect reference](docs/reference/effect-reference.md)

## Quick validation

Use only the bundled Windows interpreter:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/rk3588-host-service.yaml `
  validate-show --show config/shows/cabin-show-v2.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/rk3588-host-service.yaml `
  inspect-topology --show config/shows/cabin-show-v2.yaml
```

The tracked WLED template uses mDNS names; production uses its generated
runtime Profile. Memory and fake transports require explicit configuration.

Historical compatibility field material uses
`config/profiles/ws2811-installed-one-esp-per-strip.yaml`: nodes 1, 2, 4, 5,
6, 7, 8, 9, and 10 at `192.168.31.201` through `.210` with the unused node 3
address omitted. The complete target also reserves nodes 3, 11, 12, and 13 at
`.203` and `.211` through `.213`. Logical `strip_*` IDs and Show v2 content do
not change when physical nodes change. All endpoint and visible-output claims
remain **NOT HARDWARE VERIFIED**.

The listed UDP v3 shows and Profiles are historical compatibility material;
they are not the current WLED/DDP deployment path.

## Repository map

| Path | Purpose |
| --- | --- |
| `light_engine/` | Runtime, analysis, effects, mapping, protocols, and outputs |
| `firmware/` | STM32 and ESP32-S3 firmware plus shared golden vectors |
| `config/` | Runtime defaults, profiles, shows, examples, and acceptance inputs |
| `tests/` | Unit, integration, golden, and software acceptance tests |
| `docs/current/` | Current operating and authoring instructions |
| `docs/reference/` | Current API and effect reference material |
| `docs/acceptance/` | Human-readable accepted software evidence |
| `docs/history/` | Historical plans and legacy prototype documentation |
| `artifacts/baselines/` | Committed acceptance evidence; normal tests do not write here |
| `artifacts/runs/` | Disposable local acceptance output; ignored by Git |

License: proprietary, internal use.
