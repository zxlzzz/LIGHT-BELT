"""Contracts for the staged WS2811 hardware acceptance shows."""

from __future__ import annotations

import random
import zlib
from pathlib import Path

import pytest

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import (
    AudioFeatures,
    DigitalStrip,
    EffectContext,
    MusicControlState,
    PixelFrame,
    VideoFeatures,
)
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


NODE2_PROFILE = Path("config/profiles/node2-effects-demo.yaml")
INSTALLED_PROFILE = Path(
    "config/profiles/ws2811-installed-one-esp-per-strip.yaml"
)
TWO_NODE_PROFILE = Path("config/profiles/ws2811-two-node-41-42.yaml")
SITE_PROFILE = Path("config/profiles/cabin-lighting-v3-site-local.yaml")
QIO_STATIC_SHOW = Path("config/shows/ws2811-qio-node2-static-lanes.yaml")
STAGE1_SHOW = Path("config/shows/ws2811-stage1-strip41-nine-effects.yaml")
STAGE2_SHOW = Path("config/shows/ws2811-stage2-strip41-to-strip42.yaml")
STAGE3_SHOW = Path("config/shows/ws2811-stage3-installed-300s.yaml")
FULL_STAGE3_SHOW = Path("config/shows/ws2811-stage3-full-300s.yaml")

STAGE1_EFFECTS = (
    "static",
    "breath",
    "color_wave",
    "chase",
    "comet",
    "calm",
    "demo",
    "color_wipe",
    "twinkle",
)
INSTALLED_ACTIVE_STRIPS = (
    "strip_11",
    "strip_21",
    "strip_31",
    "strip_41",
    "strip_42",
    "strip_12",
    "strip_91",
    "strip_92",
    "strip_22",
)
FULL_ACTIVE_STRIPS = (
    "strip_11",
    "strip_21",
    "strip_31",
    "strip_41",
    "strip_42",
    "strip_43",
    "strip_44",
    "strip_45",
    "strip_93",
    "strip_12",
    "strip_91",
    "strip_92",
    "strip_22",
)
NODE2_DIAGNOSTIC_OUTPUTS = {1: (4, 10), 2: (5, 20), 3: (6, 20)}
INSTALLED_EXPECTED_OUTPUTS = {
    1: {1: (4, 10)},
    2: {1: (4, 10)},
    4: {1: (4, 40)},
    5: {1: (4, 40)},
    6: {1: (4, 10)},
    7: {1: (4, 10)},
    8: {1: (4, 20)},
    9: {1: (4, 20)},
    10: {1: (4, 20)},
}
INSTALLED_EXPECTED_STRIPS = {
    1: {1: "strip_11"},
    2: {1: "strip_41"},
    4: {1: "strip_12"},
    5: {1: "strip_22"},
    6: {1: "strip_21"},
    7: {1: "strip_31"},
    8: {1: "strip_42"},
    9: {1: "strip_91"},
    10: {1: "strip_92"},
}
EXPECTED_ADDRESSES = {
    ("192.168.31.201", 9001): 1,
    ("192.168.31.202", 9001): 2,
    ("192.168.31.204", 9001): 4,
    ("192.168.31.205", 9001): 5,
    ("192.168.31.206", 9001): 6,
    ("192.168.31.207", 9001): 7,
    ("192.168.31.208", 9001): 8,
    ("192.168.31.209", 9001): 9,
    ("192.168.31.210", 9001): 10,
}
TWO_NODE_EXPECTED_OUTPUTS = {
    2: {1: (4, 10)},
    8: {1: (4, 20)},
}
TWO_NODE_EXPECTED_ADDRESSES = {
    ("192.168.31.202", 9001): 2,
    ("192.168.31.208", 9001): 8,
}
FULL_EXPECTED_ROUTES = {
    1: ("strip_11", 10),
    2: ("strip_41", 10),
    3: ("strip_44", 20),
    4: ("strip_12", 40),
    5: ("strip_22", 40),
    6: ("strip_21", 10),
    7: ("strip_31", 10),
    8: ("strip_42", 20),
    9: ("strip_91", 20),
    10: ("strip_92", 20),
    11: ("strip_43", 20),
    12: ("strip_45", 20),
    13: ("strip_93", 20),
}
FULL_EXPECTED_OUTPUTS = {
    node_id: {1: (4, pixel_count)}
    for node_id, (_strip_id, pixel_count) in FULL_EXPECTED_ROUTES.items()
}
FULL_EXPECTED_ADDRESSES = {
    (f"192.168.31.{200 + node_id}", 9001): node_id
    for node_id in FULL_EXPECTED_ROUTES
}


def _load(profile_path: Path, show_path: Path):
    Config.reset()
    config = Config.get_instance(profile_path)
    layout = Layout.from_config(config)
    show = load_show(show_path, TargetCatalog.from_layout(layout))
    return config, layout, show


def _extreme_media() -> dict[str, object]:
    return {
        "video_features": VideoFeatures(
            timestamp=0.0,
            average_rgb=(1.0, 0.0, 1.0),
            dominant_rgb=(0.0, 1.0, 1.0),
            zone_colors={
                "left": (1.0, 0.0, 0.0),
                "right": (0.0, 0.0, 1.0),
                "center": (1.0, 1.0, 1.0),
                "top": (0.0, 1.0, 0.0),
                "bottom": (1.0, 0.0, 1.0),
            },
            brightness=1.0,
            saturation=1.0,
            scene_change=1.0,
        ),
        "audio_features": AudioFeatures(
            timestamp=0.0,
            rms=1.0,
            bass=1.0,
            mid=1.0,
            treble=1.0,
            spectral_flux=1.0,
            beat=True,
            onset=1.0,
            silence=False,
        ),
        "music_control_state": MusicControlState(
            timestamp=0.0,
            tempo_bpm=180.0,
            tempo_confidence=1.0,
            beat_phase=1.0,
            beat_strength=1.0,
            beat_regularity=1.0,
            energy=1.0,
            energy_trend=1.0,
            transient=1.0,
            bass_ambient=1.0,
            bass_pulse=1.0,
            spectral_motion=1.0,
        ),
    }


def _output_transform(config: Config) -> OutputTransform:
    transform = config.get("outputs.transform")
    return OutputTransform(
        global_brightness=config.get("system.smoothing.max_brightness"),
        gamma=config.get("system.smoothing.gamma"),
        power_limit=transform["power_limit"],
        per_zone_warm_bias=transform["per_zone_warm_bias"],
        per_zone_cool_bias=transform["per_zone_cool_bias"],
    )


def _trace(
    profile_path: Path,
    show_path: Path,
    *,
    fps: float,
    extreme_media: bool,
    black_strips: tuple[str, ...],
) -> tuple[tuple[tuple[str, tuple[tuple[float, float, float], ...]], ...], ...]:
    previous_random = random.getstate()
    Config.reset()
    try:
        _config, layout, show = _load(profile_path, show_path)
        runtime = ShowRuntime.from_layout(show, layout, seed=20260715)
        random.seed(20260715)
        media = _extreme_media() if extreme_media else {}
        frames = []
        for index in range(int(show.duration * fps)):
            timestamp = index / fps
            sequence = index + 1
            base = black_base_frame(
                timestamp=timestamp,
                sequence=sequence,
                analog_zones=layout.zones,
                digital_strips=layout.strips,
            )
            frame = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / fps,
                    sequence=sequence,
                    **media,
                ),
                base,
            )
            by_id = {strip.strip_id: strip for strip in frame.strips}
            for strip_id in black_strips:
                assert all(
                    pixel == (0.0, 0.0, 0.0)
                    for pixel in by_id[strip_id].pixels
                )
            frames.append(
                tuple(
                    (
                        strip.strip_id,
                        tuple(
                            tuple(round(channel, 12) for channel in pixel)
                            for pixel in strip.pixels
                        ),
                    )
                    for strip in frame.strips
                )
            )
        return tuple(frames)
    finally:
        Config.reset()
        random.setstate(previous_random)


def _strip_level(frame, strip_id: str) -> float:
    strip = next(item for item in frame.strips if item.strip_id == strip_id)
    return sum(sum(pixel) for pixel in strip.pixels) / strip.pixel_count


def test_qio_diagnostic_resends_three_distinct_static_lanes_for_60_seconds() -> None:
    Config.reset()
    try:
        _config, layout, show = _load(NODE2_PROFILE, QIO_STATIC_SHOW)
        runtime = ShowRuntime.from_layout(show, layout)
        assert show.duration == 60.0
        assert {cue.target.id for cue in show.cues} == {
            "strip_41",
            "strip_42",
            "strip_43",
        }
        assert all(cue.effect.id == "static" for cue in show.cues)

        observed = []
        strip_ids = ("strip_41", "strip_42", "strip_43")
        for sequence, timestamp in enumerate((0.0, 30.0, 59.9), start=1):
            frame = runtime.render(
                EffectContext(timestamp=timestamp, delta_time=0.1, sequence=sequence),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            by_id = {strip.strip_id: strip for strip in frame.strips}
            colors = tuple(by_id[strip_id].pixels[0] for strip_id in strip_ids)
            assert len(set(colors)) == 3
            for strip_id, color in zip(strip_ids, colors):
                assert color != (0.0, 0.0, 0.0)
                assert all(pixel == color for pixel in by_id[strip_id].pixels)
            observed.append(colors)
        assert observed[0] == observed[1] == observed[2]
    finally:
        Config.reset()


def test_stage1_has_exactly_nine_media_independent_strip41_effects() -> None:
    Config.reset()
    try:
        _config, layout, show = _load(NODE2_PROFILE, STAGE1_SHOW)
        runtime = ShowRuntime.from_layout(show, layout)

        assert show.id == "ws2811-stage1-strip41-nine-effects"
        assert show.duration == 90.0
        assert tuple(cue.effect.id for cue in show.cues) == STAGE1_EFFECTS
        assert [(cue.start, cue.end) for cue in show.cues] == [
            (index * 10.0, (index + 1) * 10.0) for index in range(9)
        ]
        assert all(cue.effect.mode == "fixed" for cue in show.cues)
        assert all(cue.target.kind == "digital_strip" for cue in show.cues)
        assert all(cue.target.id == "strip_41" for cue in show.cues)
        assert all(cue.audio_control is None for cue in show.cues)
        assert all(cue.audio_modulation is None for cue in show.cues)
        assert all(
            tuple(strip.id for strip in job.resolved.digital_strips)
            == ("strip_41",)
            for job in runtime.jobs
        )

        demo = next(cue for cue in show.cues if cue.effect.id == "demo")
        assert set(demo.effect.params["effects"]) == set(STAGE1_EFFECTS) - {"demo"}
        assert not set(demo.effect.params["effects"]) & {
            "audio_pulse",
            "bass_pulse",
            "spectrum",
            "video_ambient",
            "video_audio_fusion",
        }

        visible_effects: set[str] = set()
        for index in range(int(show.duration * 5.0)):
            timestamp = index / 5.0
            frame = runtime.render(
                EffectContext(timestamp=timestamp, delta_time=0.2, sequence=index + 1),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=index + 1,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            by_id = {strip.strip_id: strip for strip in frame.strips}
            assert all(pixel == (0.0, 0.0, 0.0) for pixel in by_id["strip_42"].pixels)
            assert all(pixel == (0.0, 0.0, 0.0) for pixel in by_id["strip_43"].pixels)
            if any(max(pixel) > 0.0 for pixel in by_id["strip_41"].pixels):
                active = next(cue for cue in show.cues if cue.start <= timestamp < cue.end)
                visible_effects.add(active.effect.id)
        assert visible_effects == set(STAGE1_EFFECTS)
    finally:
        Config.reset()


def test_stage1_is_invariant_to_video_audio_and_beat() -> None:
    clean = _trace(
        NODE2_PROFILE,
        STAGE1_SHOW,
        fps=4.0,
        extreme_media=False,
        black_strips=("strip_42", "strip_43"),
    )
    extreme = _trace(
        NODE2_PROFILE,
        STAGE1_SHOW,
        fps=4.0,
        extreme_media=True,
        black_strips=("strip_42", "strip_43"),
    )
    assert clean == extreme


def test_stage1_static_emits_identical_node2_pixels_for_300_refreshes() -> None:
    Config.reset()
    try:
        config, layout, show = _load(NODE2_PROFILE, STAGE1_SHOW)
        runtime = ShowRuntime.from_layout(show, layout)
        transform = _output_transform(config)
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()
        fps = 30.0

        for index in range(300):
            timestamp = index / fps
            sequence = index + 1
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / fps,
                    sequence=sequence,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(transform.apply_to_frame(logical)))

        datagrams = output.get_sent_datagrams()
        assert len(datagrams) == 300
        pixel_frames = []
        for sequence, (raw, address) in enumerate(datagrams, start=1):
            assert address == ("192.168.31.202", 9001)
            packet = UdpV3Packet.decode(
                raw,
                expected_node_id=2,
                expected_outputs=NODE2_DIAGNOSTIC_OUTPUTS,
            )
            assert packet is not None
            assert packet.sequence == sequence
            by_output = {item.output_id: item.pixels for item in packet.outputs}
            assert any(pixel != (0, 0, 0) for pixel in by_output[1])
            assert all(pixel == (0, 0, 0) for pixel in by_output[2])
            assert all(pixel == (0, 0, 0) for pixel in by_output[3])
            pixel_frames.append(tuple(item.pixels for item in packet.outputs))
        assert len(set(pixel_frames)) == 1
    finally:
        Config.reset()


def test_stage1_dynamic_effects_change_and_chase_never_disappears() -> None:
    Config.reset()
    try:
        _config, layout, show = _load(NODE2_PROFILE, STAGE1_SHOW)
        runtime = ShowRuntime.from_layout(show, layout, seed=20260715)
        patterns = {effect_id: set() for effect_id in STAGE1_EFFECTS}
        fps = 30.0
        for index in range(int(show.duration * fps)):
            timestamp = index / fps
            sequence = index + 1
            frame = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / fps,
                    sequence=sequence,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            cue = next(item for item in show.cues if item.start <= timestamp < item.end)
            strip = next(item for item in frame.strips if item.strip_id == "strip_41")
            pattern = tuple(
                tuple(round(channel, 8) for channel in pixel)
                for pixel in strip.pixels
            )
            patterns[cue.effect.id].add(pattern)
            if cue.effect.id == "chase":
                assert any(max(pixel) > 0.0 for pixel in strip.pixels)

        assert len(patterns["static"]) == 1
        for effect_id in set(STAGE1_EFFECTS) - {"static"}:
            assert len(patterns[effect_id]) >= 4, effect_id
    finally:
        Config.reset()


def test_stage2_crossfade_moves_monotonically_from_strip41_to_strip42() -> None:
    Config.reset()
    try:
        _config, layout, show = _load(NODE2_PROFILE, STAGE2_SHOW)
        runtime = ShowRuntime.from_layout(show, layout)
        assert show.duration == 15.0
        assert {track.target.id for track in show.brightness_tracks} == {
            "strip_41",
            "strip_42",
        }
        assert all(cue.effect.id == "static" for cue in show.cues)
        assert all(cue.audio_control is None for cue in show.cues)
        assert all(cue.audio_modulation is None for cue in show.cues)

        times = (0.0, 2.5, 5.0, 6.25, 7.5, 8.75, 10.0, 12.5, 14.9)
        source_levels = []
        destination_levels = []
        source_colors = []
        destination_colors = []
        for sequence, timestamp in enumerate(times, start=1):
            frame = runtime.render(
                EffectContext(timestamp=timestamp, delta_time=0.1, sequence=sequence),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            source_levels.append(_strip_level(frame, "strip_41"))
            destination_levels.append(_strip_level(frame, "strip_42"))
            by_id = {strip.strip_id: strip for strip in frame.strips}
            source_colors.append(by_id["strip_41"].pixels[0])
            destination_colors.append(by_id["strip_42"].pixels[0])
            assert _strip_level(frame, "strip_43") == 0.0

        assert source_levels[0] > 0.0
        assert destination_levels[0] == 0.0
        assert source_levels[2] > 0.0
        assert destination_levels[2] == 0.0
        assert source_levels[4] == pytest.approx(destination_levels[4])
        assert source_colors[4] == pytest.approx(destination_colors[4])
        assert source_levels[6] == 0.0
        assert destination_levels[6] > 0.0
        assert source_levels[-1] == 0.0
        assert destination_levels[-1] > 0.0
        assert all(
            current <= previous + 1e-12
            for previous, current in zip(source_levels, source_levels[1:])
        )
        assert all(
            current + 1e-12 >= previous
            for previous, current in zip(destination_levels, destination_levels[1:])
        )
    finally:
        Config.reset()


def test_stage2_crossfade_survives_transform_mapping_and_node2_packet() -> None:
    Config.reset()
    try:
        config, layout, show = _load(NODE2_PROFILE, STAGE2_SHOW)
        runtime = ShowRuntime.from_layout(show, layout)
        transform = _output_transform(config)
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()
        levels = []

        for sequence, timestamp in enumerate((0.0, 5.0, 7.5, 10.0, 14.9), start=1):
            logical = runtime.render(
                EffectContext(timestamp=timestamp, delta_time=0.1, sequence=sequence),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(transform.apply_to_frame(logical)))
            raw, address = output.get_sent_datagrams()[-1]
            assert address == ("192.168.31.202", 9001)
            packet = UdpV3Packet.decode(
                raw,
                expected_node_id=2,
                expected_outputs=NODE2_DIAGNOSTIC_OUTPUTS,
            )
            assert packet is not None
            assert packet.sequence == sequence
            assert packet.media_timestamp_us == round(timestamp * 1_000_000)
            by_output = {item.output_id: item.pixels for item in packet.outputs}
            assert all(pixel == (0, 0, 0) for pixel in by_output[3])

            def level(output_id: int) -> float:
                pixels = by_output[output_id]
                return sum(sum(pixel) for pixel in pixels) / (len(pixels) * 3)

            levels.append((level(1), level(2)))

        assert levels[0][0] > 0 and levels[0][1] == 0
        assert levels[1][0] > 0 and levels[1][1] == 0
        assert levels[2][0] == pytest.approx(levels[2][1])
        assert levels[3][0] == 0 and levels[3][1] > 0
        assert levels[4][0] == 0 and levels[4][1] > 0
    finally:
        Config.reset()


def test_stage2_installed_profile_emits_node2_and_node8_with_shared_identity() -> None:
    Config.reset()
    try:
        _config, layout, show = _load(INSTALLED_PROFILE, STAGE2_SHOW)
        runtime = ShowRuntime.from_layout(show, layout)
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()
        levels = []

        for sequence, timestamp in enumerate((0.0, 7.5, 10.0), start=1):
            logical = runtime.render(
                EffectContext(timestamp=timestamp, delta_time=0.1, sequence=sequence),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(logical))
            packets = {}
            for raw, address in output.get_sent_datagrams()[-9:]:
                node_id = EXPECTED_ADDRESSES[address]
                packet = UdpV3Packet.decode(
                    raw,
                    expected_node_id=node_id,
                    expected_outputs=INSTALLED_EXPECTED_OUTPUTS[node_id],
                )
                assert packet is not None
                packets[node_id] = packet

            node2 = packets[2]
            node8 = packets[8]
            assert {
                (packet.sequence, packet.media_timestamp_us)
                for packet in (node2, node8)
            } == {(sequence, round(timestamp * 1_000_000))}
            assert len(node2.outputs) == len(node8.outputs) == 1

            def level(packet) -> float:
                pixels = packet.outputs[0].pixels
                return sum(sum(pixel) for pixel in pixels) / (len(pixels) * 3)

            levels.append((level(node2), level(node8)))

        assert levels[0][0] > 0 and levels[0][1] == 0
        assert levels[1][0] == pytest.approx(levels[1][1])
        assert levels[2][0] == 0 and levels[2][1] > 0
    finally:
        Config.reset()


def test_stage2_two_node_profile_emits_only_node2_and_node8() -> None:
    Config.reset()
    try:
        config, layout, show = _load(TWO_NODE_PROFILE, STAGE2_SHOW)
        runtime = ShowRuntime.from_layout(show, layout)
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()

        assert config.get("outputs.udp_v3.presentation.mode") == "scheduled"
        assert config.get("outputs.exit_safe_state") is True
        assert {node.node_id for node in layout.digital_nodes} == {2, 8}
        assert {strip.id for strip in layout.strips} == {"strip_41", "strip_42"}

        for sequence, timestamp in enumerate((0.0, 7.5, 10.0), start=1):
            logical = runtime.render(
                EffectContext(timestamp=timestamp, delta_time=0.1, sequence=sequence),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(logical))
            current = output.get_sent_datagrams()[-2:]
            assert {address for _raw, address in current} == set(
                TWO_NODE_EXPECTED_ADDRESSES
            )

            packets = {}
            for raw, address in current:
                node_id = TWO_NODE_EXPECTED_ADDRESSES[address]
                packet = UdpV3Packet.decode(
                    raw,
                    expected_node_id=node_id,
                    expected_outputs=TWO_NODE_EXPECTED_OUTPUTS[node_id],
                )
                assert packet is not None
                packets[node_id] = packet

            assert {
                (packet.sequence, packet.media_timestamp_us)
                for packet in packets.values()
            } == {(sequence, round(timestamp * 1_000_000))}
            assert all(len(packet.outputs) == 1 for packet in packets.values())
    finally:
        Config.reset()


def test_stage3_profile_and_show_cover_only_installed_nodes_for_300_seconds() -> None:
    Config.reset()
    try:
        config, layout, show = _load(INSTALLED_PROFILE, STAGE3_SHOW)
        runtime = ShowRuntime.from_layout(show, layout)

        assert config.get("layout.total_strips") == 9
        assert {node.node_id for node in layout.digital_nodes} == {
            1, 2, 4, 5, 6, 7, 8, 9, 10
        }
        assert tuple(strip.id for strip in layout.strips) == INSTALLED_ACTIVE_STRIPS
        assert show.duration == 300.0
        assert [(cue.start, cue.end) for cue in show.cues] == [
            (0.0, 60.0),
            (60.0, 120.0),
            (120.0, 180.0),
            (180.0, 240.0),
            (240.0, 300.0),
        ]
        assert all(cue.effect.mode == "fixed" for cue in show.cues)
        assert all(cue.audio_control is None for cue in show.cues)
        assert all(cue.audio_modulation is None for cue in show.cues)
        assert tuple(target.id for target in show.virtual_paths[0].targets) == (
            INSTALLED_ACTIVE_STRIPS
        )
        for job in runtime.jobs:
            assert {strip.id for strip in job.resolved.digital_strips} == set(
                INSTALLED_ACTIVE_STRIPS
            )
        for second in range(300):
            timestamp = second + 0.5
            assert sum(cue.start <= timestamp < cue.end for cue in show.cues) == 1
    finally:
        Config.reset()


def test_stage3_is_media_invariant_for_300_seconds() -> None:
    clean = _trace(
        INSTALLED_PROFILE,
        STAGE3_SHOW,
        fps=1.0,
        extreme_media=False,
        black_strips=(),
    )
    extreme = _trace(
        INSTALLED_PROFILE,
        STAGE3_SHOW,
        fps=1.0,
        extreme_media=True,
        black_strips=(),
    )
    assert len(clean) == 300
    assert clean == extreme


def test_stage3_show_emits_one_complete_udp_v3_packet_per_installed_node() -> None:
    Config.reset()
    try:
        _config, layout, show = _load(INSTALLED_PROFILE, STAGE3_SHOW)
        runtime = ShowRuntime.from_layout(show, layout)
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()

        for sequence, timestamp in enumerate((30.0, 90.0, 150.0, 210.0, 270.0), start=1):
            logical = runtime.render(
                EffectContext(timestamp=timestamp, delta_time=1.0, sequence=sequence),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(logical))
            datagrams = output.get_sent_datagrams()
            assert len(datagrams) == sequence * 9
            current = datagrams[-9:]
            assert {address for _raw, address in current} == set(EXPECTED_ADDRESSES)
            for raw, address in current:
                node_id = EXPECTED_ADDRESSES[address]
                packet = UdpV3Packet.decode(
                    raw,
                    expected_node_id=node_id,
                    expected_outputs=INSTALLED_EXPECTED_OUTPUTS[node_id],
                )
                assert packet is not None
                assert packet.sequence == sequence
                assert [
                    (item.output_id, item.gpio, len(item.pixels))
                    for item in packet.outputs
                ] == [
                    (output_id, gpio, pixel_count)
                    for output_id, (gpio, pixel_count) in INSTALLED_EXPECTED_OUTPUTS[node_id].items()
                ]
                assert len(packet.outputs) == 1
    finally:
        Config.reset()


def test_stage3_mapping_preserves_every_installed_strip_identity() -> None:
    Config.reset()
    try:
        _config, layout, _show = _load(INSTALLED_PROFILE, STAGE3_SHOW)
        fingerprint_pwm = {
            strip_id: (
                17 + index * 19,
                231 - index * 17,
                13 + index * 11,
            )
            for index, strip_id in enumerate(INSTALLED_ACTIVE_STRIPS)
        }
        logical = PixelFrame(
            timestamp=1.0,
            sequence=77,
            strips=[
                DigitalStrip(
                    strip_id=strip.id,
                    pixel_count=strip.pixel_count,
                    pixels=[
                        tuple(channel / 255.0 for channel in fingerprint_pwm[strip.id])
                    ]
                    * strip.pixel_count,
                )
                for strip in layout.strips
            ],
        )
        output = UdpOutputV3()
        output.open()
        output.send_frame(PhysicalMapping(layout).map(logical))

        datagrams = output.get_sent_datagrams()
        assert len(datagrams) == 9
        for raw, address in datagrams:
            node_id = EXPECTED_ADDRESSES[address]
            packet = UdpV3Packet.decode(
                raw,
                expected_node_id=node_id,
                expected_outputs=INSTALLED_EXPECTED_OUTPUTS[node_id],
            )
            assert packet is not None
            for physical_output in packet.outputs:
                strip_id = INSTALLED_EXPECTED_STRIPS[node_id][physical_output.output_id]
                assert set(physical_output.pixels) == {fingerprint_pwm[strip_id]}
    finally:
        Config.reset()


def test_stage3_runs_all_9000_frames_through_transform_mapping_and_udp() -> None:
    Config.reset()
    try:
        config, layout, show = _load(INSTALLED_PROFILE, STAGE3_SHOW)
        runtime = ShowRuntime.from_layout(show, layout, seed=20260715)
        transform = _output_transform(config)
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3(mode="fake")
        output.open()
        fps = 30.0
        visible_by_segment = [set() for _ in range(5)]
        patterns_by_segment = [set() for _ in range(5)]

        for index in range(int(show.duration * fps)):
            timestamp = index / fps
            sequence = index + 1
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / fps,
                    sequence=sequence,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            transformed = transform.apply_to_frame(logical)
            by_id = {strip.strip_id: strip for strip in transformed.strips}
            segment = min(4, int(timestamp // 60.0))
            for strip_id in INSTALLED_ACTIVE_STRIPS:
                if any(max(pixel) > 0.0 for pixel in by_id[strip_id].pixels):
                    visible_by_segment[segment].add(strip_id)
            pwm = bytes(
                round(channel * 255)
                for strip_id in INSTALLED_ACTIVE_STRIPS
                for pixel in by_id[strip_id].pixels
                for channel in pixel
            )
            patterns_by_segment[segment].add(zlib.crc32(pwm))
            output.send_frame(mapping.map(transformed))

        health = output.health()
        assert health.healthy
        assert health.last_error is None
        assert health.logical_frames_sent == 9000
        assert health.packets_sent == 81000
        assert health.frames_dropped == 0
        assert health.packets_dropped == 0
        assert all(
            visible == set(INSTALLED_ACTIVE_STRIPS)
            for visible in visible_by_segment
        )
        assert len(patterns_by_segment[0]) == 1
        assert all(len(patterns) >= 4 for patterns in patterns_by_segment[1:])
    finally:
        Config.reset()


def test_stage3_full_site_covers_thirteen_single_output_nodes_for_300_seconds() -> None:
    Config.reset()
    try:
        config, layout, show = _load(SITE_PROFILE, FULL_STAGE3_SHOW)
        runtime = ShowRuntime.from_layout(show, layout, seed=20260715)

        assert config.get("layout.total_strips") == 13
        assert {node.node_id for node in layout.digital_nodes} == set(range(1, 14))
        assert {
            output.node_id: (output.strip_id, output.pixel_count)
            for output in layout.digital_outputs
        } == FULL_EXPECTED_ROUTES
        assert all(
            output.output_id == 1 and output.gpio == 4
            for output in layout.digital_outputs
        )
        assert show.duration == 300.0
        assert [(cue.start, cue.end) for cue in show.cues] == [
            (0.0, 60.0),
            (60.0, 120.0),
            (120.0, 180.0),
            (180.0, 240.0),
            (240.0, 300.0),
        ]
        assert all(cue.effect.mode == "fixed" for cue in show.cues)
        assert all(cue.audio_control is None for cue in show.cues)
        assert all(cue.audio_modulation is None for cue in show.cues)
        assert tuple(target.id for target in show.virtual_paths[0].targets) == (
            FULL_ACTIVE_STRIPS
        )
        for job in runtime.jobs:
            assert {strip.id for strip in job.resolved.digital_strips} == set(
                FULL_ACTIVE_STRIPS
            )
    finally:
        Config.reset()


def test_stage3_full_site_emits_thirteen_udp_packets_for_each_of_300_seconds() -> None:
    Config.reset()
    try:
        config, layout, show = _load(SITE_PROFILE, FULL_STAGE3_SHOW)
        runtime = ShowRuntime.from_layout(show, layout, seed=20260715)
        transform = _output_transform(config)
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()

        final_visible_nodes = set()
        for second in range(300):
            timestamp = second + 0.5
            sequence = second + 1
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0,
                    sequence=sequence,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(transform.apply_to_frame(logical)))

            datagrams = output.get_sent_datagrams()
            assert len(datagrams) == sequence * 13
            current = datagrams[-13:]
            assert {address for _raw, address in current} == set(
                FULL_EXPECTED_ADDRESSES
            )
            for raw, address in current:
                node_id = FULL_EXPECTED_ADDRESSES[address]
                packet = UdpV3Packet.decode(
                    raw,
                    expected_node_id=node_id,
                    expected_outputs=FULL_EXPECTED_OUTPUTS[node_id],
                )
                assert packet is not None
                assert packet.sequence == sequence
                assert packet.media_timestamp_us == round(timestamp * 1_000_000)
                assert len(packet.outputs) == 1
                physical_output = packet.outputs[0]
                assert (
                    physical_output.output_id,
                    physical_output.gpio,
                    len(physical_output.pixels),
                ) == (1, 4, FULL_EXPECTED_ROUTES[node_id][1])
                if second == 299 and any(
                    any(channel > 0 for channel in pixel)
                    for pixel in physical_output.pixels
                ):
                    final_visible_nodes.add(node_id)

        health = output.health()
        assert health.healthy
        assert health.logical_frames_sent == 300
        assert health.packets_sent == 3900
        assert health.frames_dropped == 0
        assert health.packets_dropped == 0
        assert final_visible_nodes == set(range(1, 14))
    finally:
        Config.reset()
