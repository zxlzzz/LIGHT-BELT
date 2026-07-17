# LIGHT-BELT

LIGHT-BELT is the RK3588-hosted lighting controller for the provisional cabin
installation: 13 independent 24V WS2811 RGB strips, each on its own ESP32-S3,
and one RGB+CCT COB zone through STM32 RS-485. Every production ESP32 has one
UDP v3 output (`output_id: 1`) on GPIO4; the protocol retains its general
one-to-three-output capability.

The topology, protocol, and scheduled-presentation software contracts are
accepted by the final regression suite.
Physical wiring, endpoint assignment, power distribution, cross-node timing,
and visible output remain **NOT HARDWARE VERIFIED**.

All production UDP v3 node packets for one logical frame share sequence,
media time, and one Host-monotonic `apply_at_us` 20 ms in the future. A
broadcast clock beacon lets each ESP32 convert that deadline into its local
clock using the minimum offset in a bounded sample window; firmware pre-encodes
the frame and compensates the 10/20/40-group SPI wire times before completing
the WS2811 latch at the shared deadline.
Production images require this scheduled path, while explicit diagnostics
remain immediate. The scheduling software is implemented; actual multi-node
latch skew is still **NOT HARDWARE VERIFIED** and requires powered logic
analyzer acceptance.

At scheduled session start, sequence 1 is fully encoded for every node before
any packet is sent, then delivered in three byte-identical per-node rounds 2 ms
apart with one apply/media identity. Firmware deduplicates those copies
idempotently. A fully prepared KEY admits the session; a later physical-output
failure rolls back but lets the next complete scheduled frame recover. The
output loop checks safe timeout every pass and never blindly retries scheduled
SPI after its deadline.

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
  --config config/profiles/cabin-lighting-v3-production.yaml `
  validate-show --show config/shows/cabin-show-v2.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-production.yaml `
  inspect-topology --show config/shows/cabin-show-v2.yaml
```

The production profile intentionally contains placeholder endpoints and fails
explicitly until real installation values are supplied. Memory and fake
transports require explicit configuration.

The current field subset uses
`config/profiles/ws2811-installed-one-esp-per-strip.yaml`: nodes 1, 2, 4, 5,
6, 7, 8, 9, and 10 at `192.168.31.201` through `.210` with the unused node 3
address omitted. The complete target also reserves nodes 3, 11, 12, and 13 at
`.203` and `.211` through `.213`. Logical `strip_*` IDs and Show v2 content do
not change when physical nodes change. All endpoint and visible-output claims
remain **NOT HARDWARE VERIFIED**.

Use `config/shows/ws2811-stage3-installed-300s.yaml` for the current nine-node
digital acceptance scope and `config/shows/ws2811-stage3-full-300s.yaml` only
for a physically complete thirteen-node digital scope.

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
