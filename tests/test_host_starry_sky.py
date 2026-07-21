"""Unit tests for host_services/starry_sky.py.

Socket is monkeypatched so no real UDP is sent.
"""

import socket
import pytest
from unittest.mock import MagicMock, patch, call

import host_services.starry_sky as ss


@pytest.fixture(autouse=True)
def reset_state():
    ss.reset_state()
    yield
    ss.reset_state()


def _make_mock_socket():
    """Return a mock that behaves as a socket context manager."""
    sock = MagicMock()
    sock.__enter__ = MagicMock(return_value=sock)
    sock.__exit__ = MagicMock(return_value=False)
    return sock


# ── ensure_on ────────────────────────────────────────────────────────────────

def test_ensure_on_sends_toggle_when_off():
    mock_sock = _make_mock_socket()
    with patch("host_services.starry_sky.socket.socket", return_value=mock_sock):
        ss.ensure_on()
    mock_sock.sendto.assert_called_once_with(b"toggle", (ss.HOST, ss.PORT))
    assert ss.get_assumed_state() is True


def test_ensure_on_no_send_when_already_on():
    ss._assumed_on = True
    with patch("host_services.starry_sky.socket.socket") as mock_cls:
        ss.ensure_on()
    mock_cls.assert_not_called()
    assert ss.get_assumed_state() is True


def test_ensure_on_idempotent_twice():
    mock_sock = _make_mock_socket()
    with patch("host_services.starry_sky.socket.socket", return_value=mock_sock):
        ss.ensure_on()
        ss.ensure_on()
    assert mock_sock.sendto.call_count == 1


# ── ensure_off ───────────────────────────────────────────────────────────────

def test_ensure_off_sends_toggle_when_on():
    ss._assumed_on = True
    mock_sock = _make_mock_socket()
    with patch("host_services.starry_sky.socket.socket", return_value=mock_sock):
        ss.ensure_off()
    mock_sock.sendto.assert_called_once_with(b"toggle", (ss.HOST, ss.PORT))
    assert ss.get_assumed_state() is False


def test_ensure_off_no_send_when_already_off():
    with patch("host_services.starry_sky.socket.socket") as mock_cls:
        ss.ensure_off()
    mock_cls.assert_not_called()
    assert ss.get_assumed_state() is False


# ── failure handling ──────────────────────────────────────────────────────────

def test_ensure_on_failure_does_not_flip_state():
    mock_sock = _make_mock_socket()
    mock_sock.sendto.side_effect = OSError("network unreachable")
    with patch("host_services.starry_sky.socket.socket", return_value=mock_sock):
        ss.ensure_on()
    # State must NOT have changed to True on failure.
    assert ss.get_assumed_state() is False


def test_ensure_off_failure_does_not_flip_state():
    ss._assumed_on = True
    mock_sock = _make_mock_socket()
    mock_sock.sendto.side_effect = OSError("network unreachable")
    with patch("host_services.starry_sky.socket.socket", return_value=mock_sock):
        ss.ensure_off()
    assert ss.get_assumed_state() is True


# ── reset_state ───────────────────────────────────────────────────────────────

def test_reset_state_clears_on_flag():
    ss._assumed_on = True
    ss.reset_state()
    assert ss.get_assumed_state() is False
