# Configuration Layout

| Path | Purpose |
| --- | --- |
| `system.yaml`, `layout.yaml`, `effects.yaml`, `outputs.yaml` | Default runtime configuration loaded by the package |
| `profiles/` | Environment or installation overlays |
| `shows/` | Maintained Show v2 programs |
| `examples/` | Teaching, compatibility, and authoring examples |
| `acceptance/` | Fixed inputs for named software acceptance campaigns |

Hardware endpoints, GPIO mappings, and physical topology remain configurable.
Files under `acceptance/` are test fixtures, not production profiles.

`profiles/wled-five-board-phase-17.yaml` is the historical five-board WLED
Profile and remains unchanged for compatibility. The current nine-board Host
template is `profiles/rk3588-host-service.yaml`; `scripts/resolve_nodes.py`
copies it to ignored `config/runtime/wled-ddp-mdns.yaml` after Avahi mDNS
resolution. Do not edit or deploy the tracked template as a resolved profile.
Unresolved nodes are disabled, not redirected to an old address. This is **NOT
HARDWARE VERIFIED**.

For custom firmware only, `profiles/udp-v3-nine-strip-maintenance.yaml` uses
the same nine logical strips with UDP v3 and no RGB+CCT nodes. It is not valid
for WLED. Stop the show, set `ENGINE_PROFILE_PATH`, and restart the Host to
change mode; there is no APP hot-switch. **NOT HARDWARE VERIFIED.**
