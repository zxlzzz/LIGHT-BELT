"""Auto-discover shows from assets/ subdirectories with optional manifest overlay.

Discovery rules:
  - Each first-level subdir of assets/ becomes a show (show_id = dirname).
  - Media files (.mp4/.mkv/.mov/.mp3/.wav/.flac) → media_path
    (dict-order first if multiple; warning logged).
  - .yaml files → show_yaml (dict-order first if multiple; warning logged).
  - Subdirs with neither media nor yaml are skipped with a warning.
  - duration_ms probed via ffprobe; 0 on failure (no error raised).
  - data/shows_manifest.json is an optional overlay: dict keyed by show_id;
    each entry overrides / supplements auto-discovered fields for that show,
    and may introduce new shows not in assets/ (legacy fallback).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

_log = logging.getLogger(__name__)

_MEDIA_SUFFIXES = {".mp4", ".mkv", ".mov", ".mp3", ".wav", ".flac"}
_YAML_SUFFIXES = {".yaml", ".yml"}

_HERE = Path(__file__).resolve().parent.parent  # repo root


def _default_assets_dir() -> Path:
    return _HERE / "assets"


def _default_manifest_path() -> Path:
    return _HERE / "data" / "shows_manifest.json"


def _probe_duration_ms(media_path: str) -> int:
    """Return duration in ms via ffprobe, or 0 on any failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_entries", "format=duration",
                media_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            dur = data.get("format", {}).get("duration")
            if dur is not None:
                return int(float(dur) * 1000)
    except Exception:
        pass
    return 0


def _discover_assets(assets_dir: Path) -> dict[str, dict]:
    """Return {show_id: show_dict} for each valid subdir in assets_dir."""
    shows: dict[str, dict] = {}
    if not assets_dir.is_dir():
        return shows

    for entry in sorted(assets_dir.iterdir()):
        if not entry.is_dir():
            continue
        show_id = entry.name

        media_files = sorted(
            p for p in entry.iterdir() if p.suffix.lower() in _MEDIA_SUFFIXES
        )
        yaml_files = sorted(
            p for p in entry.iterdir() if p.suffix.lower() in _YAML_SUFFIXES
        )

        if not media_files and not yaml_files:
            _log.warning("shows_loader: %s has no media or yaml; skipped", show_id)
            continue

        media_path: str | None = None
        if media_files:
            if len(media_files) > 1:
                _log.warning(
                    "shows_loader: %s has multiple media files; using %s",
                    show_id, media_files[0].name,
                )
            media_path = str(media_files[0])

        show_yaml: str | None = None
        if yaml_files:
            if len(yaml_files) > 1:
                _log.warning(
                    "shows_loader: %s has multiple yaml files; using %s",
                    show_id, yaml_files[0].name,
                )
            show_yaml = str(yaml_files[0])

        duration_ms = _probe_duration_ms(media_path) if media_path else 0

        shows[show_id] = {
            "show_id": show_id,
            "name": show_id,
            "description": None,
            "duration_ms": duration_ms,
            "media_path": media_path,
            "show_yaml": show_yaml,
        }

    return shows


def _load_manifest_overlay(manifest_path: Path) -> dict[str, dict]:
    """Load optional overlay from manifest JSON. Returns {} if absent."""
    if not manifest_path.exists():
        return {}
    try:
        with open(manifest_path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        _log.warning("shows_loader: failed to read manifest %s: %s", manifest_path, exc)
        return {}

    if isinstance(raw, list):
        # Legacy array format: convert to dict keyed by show_id.
        overlay: dict[str, dict] = {}
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                _log.warning("shows_loader: manifest entry %d is not an object; skipped", i)
                continue
            sid = entry.get("show_id")
            if not sid:
                _log.warning("shows_loader: manifest entry %d missing show_id; skipped", i)
                continue
            overlay[sid] = entry
        return overlay

    if isinstance(raw, dict):
        return raw

    _log.warning("shows_loader: manifest %s has unexpected type %s; ignored", manifest_path, type(raw).__name__)
    return {}


def load_shows(
    assets_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> list[dict]:
    """Discover shows and apply manifest overlay. Returns list of show dicts.

    Each dict contains at minimum: show_id, name, description, duration_ms,
    media_path, show_yaml.  The aux_triggers field (if present in the overlay)
    is preserved and passed through; it is hidden from the API by engine_adapter.
    """
    ad = Path(assets_dir) if assets_dir is not None else _default_assets_dir()
    mp = Path(manifest_path) if manifest_path is not None else _default_manifest_path()

    discovered = _discover_assets(ad)
    overlay = _load_manifest_overlay(mp)

    # Merge: overlay fields win over auto-discovered ones.
    for show_id, ovr in overlay.items():
        if show_id in discovered:
            discovered[show_id].update(ovr)
        else:
            # Overlay-only entry (legacy or explicit-only show).
            entry = {"show_id": show_id, "name": show_id, "description": None,
                     "duration_ms": 0, "media_path": None, "show_yaml": None}
            entry.update(ovr)
            discovered[show_id] = entry

    # Validate: show_id and name are required; skip invalid entries.
    result: list[dict] = []
    for show in discovered.values():
        if not show.get("show_id") or not show.get("name"):
            _log.warning("shows_loader: entry missing show_id or name; skipped: %r", show)
            continue
        result.append(show)

    return result
