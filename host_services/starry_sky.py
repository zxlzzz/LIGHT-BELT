"""Starry sky UDP toggle device.

The device at HOST:PORT toggles on/off with any UDP packet.  State is
tracked locally as `_assumed_on`; a packet is only sent when the desired
state differs from the assumed one.  Failures are logged as warnings and
do not change the assumed state (to avoid sending a compensating toggle).
"""

from __future__ import annotations

import logging
import socket

_log = logging.getLogger(__name__)

HOST = "192.168.31.205"
PORT = 3333
_UDP_TIMEOUT = 1.0

_assumed_on: bool = False


def _send_toggle() -> bool:
    """Send a UDP toggle packet.  Returns True on success."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(_UDP_TIMEOUT)
            sock.sendto(b"toggle", (HOST, PORT))
        return True
    except Exception as exc:
        _log.warning("starry_sky: UDP send to %s:%d failed: %s", HOST, PORT, exc)
        return False


def ensure_on() -> None:
    """Turn the starry sky on; no-op if already assumed on."""
    global _assumed_on
    if not _assumed_on:
        if _send_toggle():
            _assumed_on = True


def ensure_off() -> None:
    """Turn the starry sky off; no-op if already assumed off."""
    global _assumed_on
    if _assumed_on:
        if _send_toggle():
            _assumed_on = False


def get_assumed_state() -> bool:
    """Return the current assumed on/off state."""
    return _assumed_on


def reset_state() -> None:
    """Reset assumed state to off.  Used in tests and on service restart."""
    global _assumed_on
    _assumed_on = False
