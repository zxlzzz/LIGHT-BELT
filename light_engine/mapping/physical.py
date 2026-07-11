"""Physical mapping from logical lighting frames to node-oriented frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from light_engine.models import PixelFrame, RGBCCTColor
from light_engine.mapping.resolve import validate_direction


@dataclass(frozen=True)
class AnalogNodeMapping:
    node_id: int
    zone_id: str
    video_zone: str = "center"
    channel_order: str = "RGBWC"
    fade_ms: int = 0


@dataclass(frozen=True)
class DigitalNodeMapping:
    node_id: int
    host: str
    port: int
    pixel_count: int
    max_udp_payload: int = 4096
    protocol_version: int = 2


@dataclass(frozen=True)
class DigitalSegmentMapping:
    segment_id: str
    strip_id: str
    node_id: int
    offset: int
    pixel_count: int
    direction: str = "forward"
    video_zone: str = "center"


@dataclass(frozen=True)
class DigitalOutputMapping:
    """One independent ESP32 GPIO output at the physical boundary.

    This deliberately sits below :class:`DigitalStrip`: logical strips know
    nothing about node addresses, GPIOs, or network transport.
    """

    node_id: int
    output_id: int
    gpio: int
    strip_id: str
    pixel_count: int
    direction: str = "forward"


@dataclass(frozen=True)
class AnalogNodeCommand:
    node_id: int
    zone_id: str
    color: RGBCCTColor
    fade_ms: int = 0
    channel_order: str = "RGBWC"


@dataclass(frozen=True)
class DigitalNodeFrame:
    node_id: int
    host: str
    port: int
    # ``pixels`` is retained solely for UDP v2/legacy layouts.  UDP v3 uses
    # ``outputs`` and never joins independent strips into one pixel stream.
    pixels: list[tuple[float, float, float]] = field(default_factory=list)
    outputs: list["DigitalOutputFrame"] = field(default_factory=list)


@dataclass(frozen=True)
class DigitalOutputFrame:
    """One separately-addressed physical WS2811 output in a node frame."""

    output_id: int
    gpio: int
    strip_id: str
    pixels: list[tuple[float, float, float]]


@dataclass(frozen=True)
class PhysicalFrame:
    sequence: int
    timestamp: float
    analog_commands: list[AnalogNodeCommand] = field(default_factory=list)
    digital_frames: list[DigitalNodeFrame] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class PhysicalMapping:
    """Map logical PixelFrame data into physical analog and digital node views."""

    def __init__(self, layout: Any):
        self._layout = layout
        self._zone_ids = {zone.id for zone in layout.zones}
        self._strips_by_id = {strip.id: strip for strip in layout.strips}
        self._analog_nodes: list[AnalogNodeMapping] = list(layout.analog_nodes)
        self._digital_nodes: list[DigitalNodeMapping] = list(layout.digital_nodes)
        self._digital_segments: list[DigitalSegmentMapping] = list(
            layout.digital_segments
        )
        self._digital_outputs: list[DigitalOutputMapping] = list(
            getattr(layout, "digital_outputs", ())
        )
        self._validate()

    def _require_int(
        self, value: Any, locator: str, field_name: str, min_value: int
    ) -> None:
        if type(value) is not int or value < min_value:
            raise ValueError(
                f"{locator}: field '{field_name}' = {value!r}, "
                f"expected integer >= {min_value}"
            )

    def _require_nonempty_str(
        self, value: Any, locator: str, field_name: str
    ) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"{locator}: field '{field_name}' = {value!r}, "
                "expected non-empty string"
            )

    def _validate(self) -> None:
        expected_analog_nodes = 1 if getattr(self._layout, "topology_version", 2) == 3 else 6
        if len(self._analog_nodes) != expected_analog_nodes:
            raise ValueError(f"Layout must define exactly {expected_analog_nodes} analog nodes")
        if getattr(self._layout, "topology_version", 2) == 3 and any(
            node.protocol_version != 3 for node in self._digital_nodes
        ):
            raise ValueError("Cabin v3 topology requires UDP v3 on every digital node")

        node_ids: dict[int, str] = {}
        for idx, node in enumerate(self._analog_nodes):
            locator = f"layout.analog_nodes[{idx}]"
            self._require_int(node.node_id, locator, "node_id", 1)
            self._require_int(node.fade_ms, locator, "fade_ms", 0)
            self._require_nonempty_str(node.zone_id, locator, "zone_id")
            if node.zone_id not in self._zone_ids:
                raise ValueError(
                    f"{locator}: field 'zone_id' = {node.zone_id!r}, "
                    "expected existing layout.zones id"
                )
            previous = node_ids.get(node.node_id)
            if previous is not None:
                raise ValueError(
                    f"{locator}: field 'node_id' = {node.node_id!r}, "
                    f"expected globally unique node id; already used by {previous}"
                )
            node_ids[node.node_id] = locator

        node_by_id = {node.node_id: node for node in self._digital_nodes}
        occupied: dict[int, set[int]] = {node.node_id: set() for node in self._digital_nodes}
        for idx, node in enumerate(self._digital_nodes):
            locator = f"layout.digital_nodes[{idx}]"
            self._require_int(node.node_id, locator, "node_id", 1)
            self._require_int(node.port, locator, "port", 1)
            self._require_int(node.pixel_count, locator, "pixel_count", 1)
            self._require_int(node.max_udp_payload, locator, "max_udp_payload", 1)
            previous = node_ids.get(node.node_id)
            if previous is not None:
                raise ValueError(
                    f"{locator}: field 'node_id' = {node.node_id!r}, "
                    f"expected globally unique node id; already used by {previous}"
                )
            node_ids[node.node_id] = locator
            if node.protocol_version not in {2, 3}:
                raise ValueError(
                    f"{locator}: field 'protocol_version' = {node.protocol_version!r}, "
                    "expected 2 or 3"
                )
            if node.protocol_version == 2 and node.pixel_count * 3 > node.max_udp_payload:
                raise ValueError(
                    f"{locator}: field 'max_udp_payload' = {node.max_udp_payload!r}, "
                    f"expected >= physical payload size {node.pixel_count * 3}"
                )

        if self._digital_outputs:
            self._validate_v3_outputs(node_by_id)
        elif any(node.protocol_version == 3 for node in self._digital_nodes):
            raise ValueError("UDP v3 digital nodes require layout.digital_outputs")

        segment_ids: set[str] = set()
        for idx, segment in enumerate(self._digital_segments):
            locator = f"layout.digital_segments[{idx}]"
            self._require_nonempty_str(segment.segment_id, locator, "segment_id")
            if segment.segment_id in segment_ids:
                raise ValueError(
                    f"{locator}: field 'segment_id' = {segment.segment_id!r}, "
                    "expected unique segment id"
                )
            segment_ids.add(segment.segment_id)
            self._require_nonempty_str(segment.strip_id, locator, "strip_id")
            self._require_int(segment.node_id, locator, "node_id", 1)
            self._require_int(segment.offset, locator, "offset", 0)
            self._require_int(segment.pixel_count, locator, "pixel_count", 1)
            try:
                validate_direction(segment.direction, segment.segment_id)
            except ValueError as exc:
                raise ValueError(
                    f"{locator}: field 'direction' = {segment.direction!r}, "
                    "expected 'forward' or 'reverse'"
                ) from exc

            node = node_by_id.get(segment.node_id)
            if node is None:
                raise ValueError(
                    f"{locator}: field 'node_id' = {segment.node_id!r}, "
                    "expected existing layout.digital_nodes node_id"
                )
            strip = self._strips_by_id.get(segment.strip_id)
            if strip is None:
                raise ValueError(
                    f"{locator}: field 'strip_id' = {segment.strip_id!r}, "
                    "expected existing layout.strips id"
                )
            source_start = 0
            source_end = source_start + segment.pixel_count
            if source_end > strip.pixel_count:
                raise ValueError(
                    f"{locator}: field 'pixel_count' = {segment.pixel_count!r}, "
                    f"expected source range [{source_start}, {source_end}) within "
                    f"logical strip {segment.strip_id!r} length {strip.pixel_count}"
                )
            end = segment.offset + segment.pixel_count
            if end > node.pixel_count:
                raise ValueError(
                    f"{locator}: field 'offset' = {segment.offset!r}, "
                    f"expected physical range [{segment.offset}, {end}) within "
                    f"digital node {segment.node_id} length {node.pixel_count}"
                )
            for idx in range(segment.offset, end):
                if idx in occupied[segment.node_id]:
                    raise ValueError(
                        f"{locator}: segment {segment.segment_id!r} overlaps "
                        f"node {segment.node_id} pixel {idx}"
                    )
                occupied[segment.node_id].add(idx)

    def _validate_v3_outputs(self, node_by_id: dict[int, DigitalNodeMapping]) -> None:
        """Validate complete independent-output topology for UDP v3."""
        outputs_by_node: dict[int, list[DigitalOutputMapping]] = {}
        mapped_strips: set[str] = set()
        for index, output in enumerate(self._digital_outputs):
            locator = f"layout.digital_outputs[{index}]"
            self._require_int(output.node_id, locator, "node_id", 1)
            self._require_int(output.output_id, locator, "output_id", 1)
            self._require_int(output.gpio, locator, "gpio", 0)
            self._require_int(output.pixel_count, locator, "pixel_count", 1)
            self._require_nonempty_str(output.strip_id, locator, "strip_id")
            if output.node_id not in node_by_id:
                raise ValueError(f"{locator}: node_id must reference a digital node")
            node = node_by_id[output.node_id]
            if node.protocol_version != 3:
                raise ValueError(f"{locator}: node {output.node_id} must use UDP v3")
            strip = self._strips_by_id.get(output.strip_id)
            if strip is None:
                raise ValueError(f"{locator}: strip_id must reference a logical strip")
            if output.pixel_count != strip.pixel_count:
                raise ValueError(
                    f"{locator}: pixel_count must equal logical strip {output.strip_id!r} length"
                )
            if output.pixel_count > 100:
                raise ValueError(f"{locator}: pixel_count must be <= 100 for an ESP32 output")
            try:
                validate_direction(output.direction, output.strip_id)
            except ValueError as exc:
                raise ValueError(f"{locator}: invalid direction") from exc
            outputs_by_node.setdefault(output.node_id, []).append(output)
            if output.strip_id in mapped_strips:
                raise ValueError(f"{locator}: strip_id {output.strip_id!r} is mapped more than once")
            mapped_strips.add(output.strip_id)

        if mapped_strips != set(self._strips_by_id):
            missing = sorted(set(self._strips_by_id) - mapped_strips)
            raise ValueError(f"layout.digital_outputs: missing logical strips {missing}")
        for node_id, node in node_by_id.items():
            if node.protocol_version != 3:
                continue
            node_outputs = outputs_by_node.get(node_id, [])
            if not node_outputs:
                raise ValueError(f"digital node {node_id} has no independent outputs")
            if len(node_outputs) > 3:
                raise ValueError(f"digital node {node_id} has more than three outputs")
            output_ids = [item.output_id for item in node_outputs]
            gpios = [item.gpio for item in node_outputs]
            if len(set(output_ids)) != len(output_ids):
                raise ValueError(f"digital node {node_id} has duplicate output_id")
            if len(set(gpios)) != len(gpios):
                raise ValueError(f"digital node {node_id} has duplicate gpio")
            mapped_pixel_count = sum(item.pixel_count for item in node_outputs)
            if mapped_pixel_count != node.pixel_count:
                raise ValueError(
                    f"digital node {node_id}: output pixel total {mapped_pixel_count} "
                    f"must equal node pixel_count {node.pixel_count}"
                )
            # v3 header + descriptors + payload + CRC; this makes a partial
            # datagram impossible by rejecting oversized node configurations.
            encoded_size = 29 + sum(6 + item.pixel_count * 3 for item in node_outputs) + 4
            if encoded_size > node.max_udp_payload:
                raise ValueError(
                    f"digital node {node_id}: UDP v3 datagram {encoded_size} exceeds "
                    f"max_udp_payload {node.max_udp_payload}"
                )

    def _copy_color(self, color: RGBCCTColor) -> RGBCCTColor:
        return RGBCCTColor(
            r=color.r,
            g=color.g,
            b=color.b,
            warm_white=color.warm_white,
            cool_white=color.cool_white,
        )

    def map(self, logical_frame: PixelFrame) -> PhysicalFrame:
        zones = {zone.zone_id: zone for zone in logical_frame.zones}
        strips = {strip.strip_id: strip for strip in logical_frame.strips}

        analog_commands = []
        for mapping in sorted(self._analog_nodes, key=lambda item: item.node_id):
            zone = zones.get(mapping.zone_id)
            color = self._copy_color(zone.color) if zone is not None else RGBCCTColor()
            analog_commands.append(
                AnalogNodeCommand(
                    node_id=mapping.node_id,
                    zone_id=mapping.zone_id,
                    color=color,
                    fade_ms=mapping.fade_ms,
                    channel_order=mapping.channel_order,
                )
            )

        digital_pixels = {
            node.node_id: [(0.0, 0.0, 0.0)] * node.pixel_count
            for node in self._digital_nodes
        }
        for segment in self._digital_segments:
            strip = strips.get(segment.strip_id)
            if strip is None:
                source = [(0.0, 0.0, 0.0)] * segment.pixel_count
            else:
                source = list(strip.pixels[: segment.pixel_count])
                if len(source) < segment.pixel_count:
                    source.extend([(0.0, 0.0, 0.0)] * (segment.pixel_count - len(source)))
            if segment.direction == "reverse":
                source = list(reversed(source))
            dest = digital_pixels[segment.node_id]
            dest[segment.offset : segment.offset + segment.pixel_count] = source

        outputs_by_node: dict[int, list[DigitalOutputFrame]] = {}
        for mapping in self._digital_outputs:
            strip = strips.get(mapping.strip_id)
            source = list(strip.pixels) if strip is not None else []
            source = source[: mapping.pixel_count]
            if len(source) < mapping.pixel_count:
                source.extend([(0.0, 0.0, 0.0)] * (mapping.pixel_count - len(source)))
            if mapping.direction == "reverse":
                source.reverse()
            outputs_by_node.setdefault(mapping.node_id, []).append(
                DigitalOutputFrame(
                    output_id=mapping.output_id,
                    gpio=mapping.gpio,
                    strip_id=mapping.strip_id,
                    pixels=source,
                )
            )

        digital_frames = [
            DigitalNodeFrame(
                node_id=node.node_id,
                host=node.host,
                port=node.port,
                pixels=(
                    [] if node.protocol_version == 3 else digital_pixels[node.node_id]
                ),
                outputs=sorted(outputs_by_node.get(node.node_id, []), key=lambda item: item.output_id),
            )
            for node in sorted(self._digital_nodes, key=lambda item: item.node_id)
        ]

        return PhysicalFrame(
            sequence=logical_frame.sequence,
            timestamp=logical_frame.timestamp,
            analog_commands=analog_commands,
            digital_frames=digital_frames,
            metadata=dict(logical_frame.metadata),
        )
