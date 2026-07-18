# Host Service Deployment

The host service (`host_services/`) is a FastAPI application that exposes the
LIGHT-BELT REST and WebSocket API on the RK3588 production brain or on a
development machine.

## Local development

Install the package with the `host` extra from the repository root:

```
pip install -e ".[dev,host]"
```

Start the service:

```
python -m host_services
```

The service listens on `http://0.0.0.0:8443` by default.
Interactive docs: `http://localhost:8443/docs`
Status check: `GET http://localhost:8443/api/v1/status`

## RK3588 deployment

1. Clone the repository and install with the `host` extra (or install from
   a built wheel).
2. Create runtime data directory and copy the manifest:
   ```
   mkdir -p /opt/light-belt/data
   cp config/examples/shows-manifest.example.json \
      /opt/light-belt/data/shows_manifest.json
   ```
   Edit `shows_manifest.json` to point `media_path` fields at the real asset
   files on the device.
3. Set `SHOWS_MANIFEST_PATH` in `host_services/config.py` to the full path
   if you place the manifest somewhere other than `data/shows_manifest.json`
   relative to the working directory.
4. Run as a systemd service or via a process supervisor:
   ```
   python -m host_services
   ```

## TLS certificates

By default the service runs over plain HTTP (`ENABLE_TLS = False`).

To enable HTTPS:

1. Place the certificate and key at:
   - `/etc/light-belt/cert.pem`
   - `/etc/light-belt/key.pem`
2. Set `ENABLE_TLS = True` in `host_services/config.py`.

The paths are configurable via `TLS_CERTFILE` and `TLS_KEYFILE` in `config.py`.
Self-signed certificates are sufficient for local LAN use; on RK3588 a
Let's Encrypt or internal CA certificate is recommended.

## Shows manifest

`data/shows_manifest.json` is the runtime source of truth for available shows.
It is not checked into git (covered by `.gitignore`). Each entry:

| Field | Type | Description |
|-------|------|-------------|
| `show_id` | string | Unique identifier used in API calls |
| `name` | string | Human-readable display name |
| `duration_ms` | integer | Total duration in milliseconds |
| `description` | string | Short description for the UI |
| `media_path` | string | Absolute path to the video/audio asset |

An example is committed at `config/examples/shows-manifest.example.json`.

If the file is absent at startup, the service starts with an empty show list
and logs a warning. No crash occurs.
