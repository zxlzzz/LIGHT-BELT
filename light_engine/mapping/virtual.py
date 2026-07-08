"""Validated virtual digital-strip paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, Iterable, Mapping, Sequence, TypeVar

from light_engine.config import ConfigError
from light_engine.mapping.resolve import validate_direction


_MISSING = object()
T = TypeVar("T")


@dataclass(frozen=True)
class VirtualPathGap:
    """Unmapped half-open interval in virtual path coordinates."""

    global_start: int
    global_end: int

    @property
    def pixel_count(self) -> int:
        return self.global_end - self.global_start


@dataclass(frozen=True)
class VirtualPathSegment:
    """Mapped virtual path segment backed by a logical digital strip range."""

    strip_id: str
    source_start: int
    pixel_count: int
    direction: str
    gap_after_pixels: int
    global_start: int
    global_end: int

    @property
    def source_end(self) -> int:
        return self.source_start + self.pixel_count


@dataclass(frozen=True)
class StripRangeContribution(Generic[T]):
    """Sparse contribution for a strip subrange.

    `pixels[0]` maps to `source_start`. Pixels outside the half-open
    destination range remain absent/no-contribution.
    """

    strip_id: str
    source_start: int
    pixels: tuple[T, ...]

    @property
    def pixel_count(self) -> int:
        return len(self.pixels)

    @property
    def source_end(self) -> int:
        return self.source_start + self.pixel_count


@dataclass(frozen=True)
class VirtualPathSummary:
    path_id: str
    mapped_pixel_count: int
    gap_coordinate_count: int
    total_virtual_length: int
    participating_strips: tuple[str, ...]
    subranges: tuple[Mapping[str, Any], ...]
    gaps: tuple[Mapping[str, int], ...]


@dataclass(frozen=True)
class VirtualPath:
    """Continuous global coordinate space over logical digital strip ranges."""

    id: str
    segments: tuple[VirtualPathSegment, ...]
    gaps: tuple[VirtualPathGap, ...]
    total_length: int

    @property
    def mapped_pixel_count(self) -> int:
        return sum(segment.pixel_count for segment in self.segments)

    @property
    def gap_coordinate_count(self) -> int:
        return sum(gap.pixel_count for gap in self.gaps)

    def split(self, path_buffer: Sequence[T]) -> tuple[StripRangeContribution[T], ...]:
        """Split one complete path-sized buffer into sparse strip ranges."""
        if len(path_buffer) != self.total_length:
            raise ValueError(
                f"virtual path {self.id!r}: path buffer length {len(path_buffer)} "
                f"does not match total virtual length {self.total_length}"
            )

        contributions: list[StripRangeContribution[T]] = []
        for segment in self.segments:
            pixels = tuple(path_buffer[segment.global_start : segment.global_end])
            if segment.direction == "reverse":
                pixels = tuple(reversed(pixels))
            contributions.append(
                StripRangeContribution(
                    strip_id=segment.strip_id,
                    source_start=segment.source_start,
                    pixels=pixels,
                )
            )
        return tuple(contributions)

    def summary(self) -> VirtualPathSummary:
        """Return deterministic authored-coordinate summary for reports/UI."""
        participating_strips = tuple(
            dict.fromkeys(segment.strip_id for segment in self.segments)
        )
        return VirtualPathSummary(
            path_id=self.id,
            mapped_pixel_count=self.mapped_pixel_count,
            gap_coordinate_count=self.gap_coordinate_count,
            total_virtual_length=self.total_length,
            participating_strips=participating_strips,
            subranges=tuple(
                {
                    "strip_id": segment.strip_id,
                    "source_start": segment.source_start,
                    "source_end": segment.source_end,
                    "global_start": segment.global_start,
                    "global_end": segment.global_end,
                    "direction": segment.direction,
                    "gap_after_pixels": segment.gap_after_pixels,
                }
                for segment in self.segments
            ),
            gaps=tuple(
                {
                    "global_start": gap.global_start,
                    "global_end": gap.global_end,
                    "pixel_count": gap.pixel_count,
                }
                for gap in self.gaps
            ),
        )


def render_virtual_path(
    path: VirtualPath, renderer: Callable[[int], Sequence[T]]
) -> tuple[StripRangeContribution[T], ...]:
    """Render one path-sized buffer once, then split it into strip ranges."""
    path_buffer = renderer(path.total_length)
    return path.split(path_buffer)


def build_virtual_paths(
    raw_paths: Iterable[Any],
    strip_lengths: Mapping[str, int],
    *,
    base_path: str = "layout.virtual_paths",
) -> tuple[VirtualPath, ...]:
    """Validate and build virtual paths from parsed layout config data."""
    paths: list[VirtualPath] = []
    path_ids: set[str] = set()
    for path_index, raw_path in enumerate(raw_paths):
        path_locator = f"{base_path}[{path_index}]"
        path_data = _mapping(raw_path, path_locator, "item")
        path_id = _nonempty_str(path_data.get("id", _MISSING), path_locator, "id")
        if path_id in path_ids:
            raise ConfigError(path_locator, "id", path_id, "unique virtual path id")
        path_ids.add(path_id)
        segments_data = _list(
            path_data.get("segments", _MISSING), path_locator, "segments"
        )
        if not segments_data:
            raise ConfigError(path_locator, "segments", segments_data, "non-empty list")
        paths.append(
            _build_virtual_path(
                path_id,
                segments_data,
                strip_lengths,
                path_locator=f"{path_locator}.segments",
            )
        )
    return tuple(paths)


def _build_virtual_path(
    path_id: str,
    segments_data: Sequence[Any],
    strip_lengths: Mapping[str, int],
    *,
    path_locator: str,
) -> VirtualPath:
    segments: list[VirtualPathSegment] = []
    gaps: list[VirtualPathGap] = []
    used_sources: dict[str, set[int]] = {}
    cursor = 0

    for segment_index, raw_segment in enumerate(segments_data):
        locator = f"{path_locator}[{segment_index}]"
        data = _mapping(raw_segment, locator, "item")
        strip_id = _nonempty_str(data.get("strip_id", _MISSING), locator, "strip_id")
        if strip_id not in strip_lengths:
            raise ConfigError(
                locator, "strip_id", strip_id, "existing layout.strips id"
            )
        source_start = _int(
            data.get("source_start", 0), locator, "source_start", minimum=0
        )
        pixel_count = _int(
            data.get("pixel_count", _MISSING), locator, "pixel_count", minimum=1
        )
        direction = _direction(
            data.get("direction", _MISSING), locator, "direction"
        )
        gap_after_pixels = _int(
            data.get("gap_after_pixels", 0),
            locator,
            "gap_after_pixels",
            minimum=0,
        )

        source_end = source_start + pixel_count
        if source_end > strip_lengths[strip_id]:
            raise ConfigError(
                locator,
                "pixel_count",
                pixel_count,
                f"source range [{source_start}, {source_end}) within "
                f"logical strip {strip_id!r} length {strip_lengths[strip_id]}",
            )
        occupied = used_sources.setdefault(strip_id, set())
        for source_pixel in range(source_start, source_end):
            if source_pixel in occupied:
                raise ConfigError(
                    locator,
                    "source_start",
                    source_start,
                    f"non-overlapping source pixels within virtual path {path_id!r}",
                )
            occupied.add(source_pixel)

        global_start = cursor
        global_end = cursor + pixel_count
        segments.append(
            VirtualPathSegment(
                strip_id=strip_id,
                source_start=source_start,
                pixel_count=pixel_count,
                direction=direction,
                gap_after_pixels=gap_after_pixels,
                global_start=global_start,
                global_end=global_end,
            )
        )
        cursor = global_end
        if gap_after_pixels:
            gap_start = cursor
            gap_end = cursor + gap_after_pixels
            gaps.append(VirtualPathGap(global_start=gap_start, global_end=gap_end))
            cursor = gap_end

    return VirtualPath(
        id=path_id,
        segments=tuple(segments),
        gaps=tuple(gaps),
        total_length=cursor,
    )


def _mapping(value: Any, path: str, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(path, field, value, "mapping")
    return value


def _list(value: Any, path: str, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(path, field, value, "list")
    return value


def _nonempty_str(value: Any, path: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(path, field, value, "non-empty string")
    return value


def _int(value: Any, path: str, field: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ConfigError(path, field, value, f"integer >= {minimum}")
    return value


def _direction(value: Any, path: str, field: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(path, field, value, "one of ['forward', 'reverse']")
    try:
        return validate_direction(value, path)
    except ValueError as exc:
        raise ConfigError(path, field, value, "one of ['forward', 'reverse']") from exc
