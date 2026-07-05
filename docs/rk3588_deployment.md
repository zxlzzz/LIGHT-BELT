# RK3588 Deployment Notes

NOT HARDWARE VERIFIED.

These notes describe the intended RK3588 host setup for Phase 7 media clock
integration. They have not been verified on the final RK3588 hardware, RS-485
bus, ESP32-S3 node, or installed light hardware.

## Runtime Shape

- Use the RK3588 as the single production host.
- Run LIGHT-BELT with the bundled project environment created for the target
  host, not with a Windows interpreter copied from development.
- Use mpv JSON IPC as the production media clock when lights must follow actual
  playback position.
- Keep device paths, media paths, users, and output mode in configuration or
  service environment files; do not hardcode them in source.

## mpv IPC

Start mpv with a stable IPC socket:

```bash
mpv --input-ipc-server=/run/light-belt/mpv.sock --idle=yes /path/to/media
```

Then run LIGHT-BELT against the same socket:

```bash
python -m light_engine run-mpv --mpv-socket /run/light-belt/mpv.sock
```

`run-mpv` can also launch mpv for a media file:

```bash
python -m light_engine run-mpv --media /path/to/media --mpv-socket /run/light-belt/mpv.sock
```

If mpv is missing, the socket cannot be reached, or IPC fails, the engine raises
an explicit error. It does not fall back to an internal clock.

## Clock Modes

- `internal`: deterministic fixed-step clock for local development.
- `offline`: deterministic fixed-step clock for export and benchmark workflows.
- `fake`: test-only manually controlled clock.
- `mpv`: production media clock sourced from mpv JSON IPC.

## systemd Example

This is a template only. Replace user, paths, config directory, and socket path
for the target host.

```ini
[Unit]
Description=LIGHT-BELT controller
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/light-belt
Environment=LIGHT_BELT_MPV_SOCKET=/run/light-belt/mpv.sock
ExecStart=/opt/light-belt/.venv/bin/python -m light_engine run-mpv --mpv-socket ${LIGHT_BELT_MPV_SOCKET}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Use udev rules or system configuration to create stable RS-485 device names.
This document does not require root access or prescribe a specific production
device path.
