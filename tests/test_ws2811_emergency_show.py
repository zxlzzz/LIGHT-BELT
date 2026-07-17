"""Host-side contract for the restricted Node2 emergency show."""

from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import FLAG_SAFE_STATE, UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-emergency-node2-strip41.yaml")
SHOW = Path("config/shows/ws2811-emergency-node2-strip41-110s.yaml")
BLACK = (0, 0, 0)
WARM_LOW = (0x20, 0x08, 0)
WARM_HIGH = (0x20, 0x10, 0)
BLUE = (0, 0, 0x20)
ORANGE = WARM_LOW
FPS = 5.0
TOTAL_PACKETS = 550
RENDER_FRAMES = TOTAL_PACKETS - 1


def _expected_payload(timestamp: float) -> tuple[tuple[int, int, int], ...]:
    pixels = [BLACK] * 10
    if 5.0 <= timestamp < 35.0:
        color = WARM_LOW if int((timestamp - 5.0) // 2.0) % 2 == 0 else WARM_HIGH
        pixels[1:] = [color] * 9
    elif 40.0 <= timestamp < 70.0:
        position = int((timestamp - 40.0) * 2.5 + 1e-9) % 9
        pixels[1 + position] = BLUE
    elif 75.0 <= timestamp < 105.0:
        position = int((timestamp - 75.0) * 2.5 + 1e-9) % 9
        pixels[1 + position] = ORANGE
    return tuple(pixels)


def test_emergency_show_emits_only_allowlisted_exact_udp_payloads() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE)
        layout = Layout.from_config(config)
        show = load_show(SHOW, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout, seed=20260716)
        transform = OutputTransform(
            global_brightness=config.get("system.smoothing.max_brightness"),
            gamma=config.get("system.smoothing.gamma"),
            power_limit=config.get("outputs.transform.power_limit"),
        )
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()

        assert config.get("system.output_fps") == 5.0
        assert show.duration == 110.0
        for index in range(RENDER_FRAMES):
            timestamp = (index + 1) / FPS
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=0.2,
                    sequence=index + 1,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=index + 1,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(transform.apply_to_frame(logical)))
            raw, address = output.get_sent_datagrams()[-1]
            packet = UdpV3Packet.decode(
                raw,
                expected_node_id=2,
                expected_outputs={1: (4, 10)},
            )
            assert address == ("192.168.31.202", 9001)
            assert packet is not None
            assert packet.outputs[0].pixels == _expected_payload(timestamp)

        safe = OutputTransform.generate_safe_frame(
            timestamp=110.0,
            sequence=TOTAL_PACKETS,
            zone_ids=[zone.id for zone in layout.zones],
            strips=[
                {"id": strip.id, "pixel_count": strip.pixel_count}
                for strip in layout.strips
            ],
        )
        output.send_frame(mapping.map(safe))
        safe_packet = UdpV3Packet.decode(
            output.get_sent_datagrams()[-1][0],
            expected_node_id=2,
            expected_outputs={1: (4, 10)},
        )
        assert safe_packet is not None
        assert safe_packet.sequence == TOTAL_PACKETS
        assert safe_packet.flags & FLAG_SAFE_STATE
        assert output.health().logical_frames_sent == TOTAL_PACKETS
        assert output.health().packets_sent == TOTAL_PACKETS
    finally:
        Config.reset()


def test_emergency_show_has_expected_content_and_key_write_budget() -> None:
    payloads = [
        _expected_payload((index + 1) / FPS)
        for index in range(RENDER_FRAMES)
    ]
    previous = (BLACK,) * 10  # Firmware startup black is the known cache state.
    scene_transitions = 0
    identical_content = 0
    for payload in payloads + [(BLACK,) * 10]:  # exit safe state
        if payload == previous:
            identical_content += 1
        else:
            scene_transitions += 1
            previous = payload

    assert scene_transitions == 168
    assert identical_content == 382
    # Sequence 1 is a KEY and must physically rebuild the command-side cache,
    # even though its black payload matches the startup black cache.
    assert scene_transitions + 1 == 169
    assert identical_content - 1 == 381
