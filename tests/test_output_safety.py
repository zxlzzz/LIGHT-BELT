"""Phase 6 output transport safety tests."""

from __future__ import annotations

import pytest

from light_engine.config import Config
from light_engine.mapping.physical import (
    AnalogNodeCommand,
    DigitalNodeFrame,
    PhysicalFrame,
)
from light_engine.models import RGBCCTColor
from light_engine.outputs import OutputMode, create_outputs, open_all, send_all
from light_engine.outputs.rs485_v2 import FRAME_LENGTH, RS485v2Packet
from light_engine.outputs.serial_output import SerialOutputV2
from light_engine.outputs.udp_output import UdpOutputV2
from light_engine.outputs.udp_v2 import FLAG_SAFE_STATE, UdpV2Packet


class FailingSerial:
    def write(self, _data: bytes) -> int:
        raise OSError("serial write failed")


def _frame(sequence: int = 1, *, safe: bool = False) -> PhysicalFrame:
    return PhysicalFrame(
        sequence=sequence,
        timestamp=0.0,
        analog_commands=[
            AnalogNodeCommand(
                node_id=node_id,
                zone_id=f"zone_{node_id}",
                color=RGBCCTColor(r=0.1 * node_id),
            )
            for node_id in range(1, 7)
        ],
        digital_frames=[
            DigitalNodeFrame(
                node_id=7,
                host="192.0.2.7",
                port=9001,
                pixels=[(0.0, 0.0, 0.0)] if safe else [(1.0, 0.0, 0.0)],
            )
        ],
        metadata={"SAFE_STATE": True} if safe else {},
    )


def test_production_serial_write_failure_does_not_fall_back_to_memory() -> None:
    output = SerialOutputV2(mode=OutputMode.PRODUCTION, transport=FailingSerial())
    output.open()

    with pytest.raises(OSError, match="serial write failed"):
        output.send_frame(_frame())

    assert output.health().healthy is False
    assert output.get_memory_bytes() == b""
    assert output.health().packets_sent == 0


def test_memory_mode_is_explicit_and_records_rs485_bytes() -> None:
    output = SerialOutputV2(mode=OutputMode.MEMORY)
    output.open()

    output.send_frame(_frame())

    assert output.capabilities()["mode"] == "memory"
    assert len(output.get_memory_bytes()) == FRAME_LENGTH * 6


def test_fake_mode_counts_success_without_hardware_bytes() -> None:
    output = SerialOutputV2(mode=OutputMode.FAKE)
    output.open()

    output.send_frame(_frame())

    assert output.health().logical_frames_sent == 1
    assert output.health().packets_sent == 6
    assert output.get_memory_bytes() == b""


def test_latest_frame_queue_overwrites_old_frames() -> None:
    output = UdpOutputV2(mode=OutputMode.MEMORY, auto_flush=False)
    output.open()

    for sequence in range(1, 6):
        output.send_frame(_frame(sequence=sequence))
    output.flush_latest()

    sent = output.get_sent_datagrams()
    assert len(sent) == 1
    decoded = UdpV2Packet.decode(sent[0][0])
    assert decoded is not None
    assert decoded.sequence == 5
    assert output.health().frames_dropped == 4
    assert output.pending_frames() == 0


def test_safe_state_sets_protocol_flags_and_black_payloads() -> None:
    rs485 = SerialOutputV2(mode=OutputMode.MEMORY)
    udp = UdpOutputV2(mode=OutputMode.MEMORY)
    rs485.open()
    udp.open()

    safe_frame = _frame(sequence=10, safe=True)
    rs485.send_frame(safe_frame)
    udp.send_frame(safe_frame)

    raw = rs485.get_memory_bytes()
    first = RS485v2Packet.decode(raw[:FRAME_LENGTH])
    assert first is not None
    assert first.flags & FLAG_SAFE_STATE

    datagram = udp.get_sent_datagrams()[0][0]
    decoded = UdpV2Packet.decode(datagram)
    assert decoded is not None
    assert decoded.flags & FLAG_SAFE_STATE
    assert decoded.pixels == [(0, 0, 0)]


def test_create_outputs_rejects_legacy_v1_output_names() -> None:
    Config.reset()
    config = Config()
    config._data["outputs"]["enabled"] = ["serial", "udp"]

    with pytest.raises(ValueError, match="Legacy v1 outputs are removed"):
        create_outputs(config)


@pytest.mark.parametrize(
    ("enabled", "message"),
    [
        (["udp_v33"], "Unknown outputs.enabled entries: udp_v33"),
        ([], "must select at least one output"),
        (["udp_v3", "udp_v3"], "entries must be unique"),
    ],
)
def test_create_outputs_rejects_unknown_or_empty_output_selection(
    enabled: list[str], message: str
) -> None:
    Config.reset()
    config = Config()
    config._data["outputs"]["enabled"] = enabled

    with pytest.raises(ValueError, match=message):
        create_outputs(config)


def test_open_all_reraises_production_open_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadSerialModule:
        class Serial:
            def __init__(self, *_args, **_kwargs) -> None:
                raise OSError("port missing")

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "serial":
            return BadSerialModule
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    output = SerialOutputV2(mode=OutputMode.PRODUCTION, port="COM404")

    with pytest.raises(RuntimeError, match="COM404"):
        open_all({"rs485_v2": output})

    assert output.health().healthy is False


def test_production_send_failure_is_reraised_and_never_falls_back(
    caplog: pytest.LogCaptureFixture,
) -> None:
    output = SerialOutputV2(mode=OutputMode.PRODUCTION, transport=FailingSerial())
    output.open()

    with pytest.raises(OSError, match="serial write failed"):
        send_all({"rs485_v2": output}, _frame())

    assert output.health().healthy is False
    assert output.get_memory_bytes() == b""
    assert "production output rs485_v2 failed: serial write failed" in caplog.text
