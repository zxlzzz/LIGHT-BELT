from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import wave
from pathlib import Path


class VerificationError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace",
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise VerificationError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def verify(root: Path) -> None:
    contracts = [
        "docs/contracts/FRAME_CONTRACT.md",
        "docs/contracts/COMPOSE_CONTRACT.md",
        "docs/contracts/TIME_CONTRACT.md",
        "docs/contracts/MUSIC_CONTROL_CONTRACT.md",
        "docs/contracts/QUALITY_GATE_CONTRACT.md",
        ".agent/contracts/phase-audit.schema.json",
    ]
    for rel in contracts:
        require((root / rel).is_file(), f"Missing contract: {rel}")

    audit = json.loads((root / ".agent/contracts/phase-audit.schema.json").read_text(encoding="utf-8"))
    require(audit.get("title") == "Show Orchestration Phase Audit Evidence", "Unexpected audit schema")

    golden_dir = root / "tests/goldens/show_orchestration/v1"
    manifest_path = golden_dir / "MANIFEST.sha256"
    require(manifest_path.is_file(), "Missing golden manifest")
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        target = golden_dir / name
        require(target.is_file(), f"Missing golden: {name}")
        require(sha256(target) == expected, f"Golden hash mismatch: {name}")

    audio_dir = root / "tests/fixtures/audio/show_orchestration_v1"
    audio_manifest = json.loads((audio_dir / "manifest.json").read_text(encoding="utf-8"))
    tracked = set(git(root, "ls-files").splitlines())
    for item in audio_manifest["fixtures"]:
        target = audio_dir / item["file"]
        require(target.is_file(), f"Missing audio fixture: {item['file']}")
        require(sha256(target) == item["sha256"], f"Audio hash mismatch: {item['file']}")
        rel = target.relative_to(root).as_posix()
        require(rel in tracked, f"Audio fixture is not tracked by Git (use git add -f): {rel}")
        with wave.open(str(target), "rb") as handle:
            require(handle.getframerate() == audio_manifest["sample_rate"], f"Sample-rate mismatch: {rel}")
            require(handle.getnchannels() == audio_manifest["channels"], f"Channel mismatch: {rel}")

    campaigns = sorted((root / ".agent/campaigns").glob("show-orchestration-v1*.json"))
    require(len(campaigns) == 5, f"Expected 5 campaign manifests, found {len(campaigns)}")
    for campaign in campaigns:
        data = json.loads(campaign.read_text(encoding="utf-8"))
        require(data.get("steps"), f"Campaign has no steps: {campaign.name}")
        for step in data["steps"]:
            task = root / step["task"]
            require(task.is_file(), f"Missing task referenced by {campaign.name}: {step['task']}")
            match = re.search(r"## Phase ID\s+([^\s]+)", task.read_text(encoding="utf-8"))
            require(match is not None and match.group(1) == step["phase_id"], f"Phase ID mismatch: {task}")

    full = json.loads((root / ".agent/campaigns/show-orchestration-v1.json").read_text(encoding="utf-8"))
    expected_repairs = [2, 2, 2, 2, 3, 3, 1]
    require([step["max_repairs"] for step in full["steps"]] == expected_repairs, "Unexpected repair budgets")

    status = git(root, "status", "--porcelain")
    require(status == "", "Working tree is not clean")

    print("SHOW_ORCHESTRATION_BASELINE_OK")
    print(f"branch={git(root, 'branch', '--show-current')}")
    print(f"head={git(root, 'rev-parse', 'HEAD')}")
    print(f"golden_manifest_sha256={sha256(manifest_path)}")
    print(f"audio_manifest_sha256={sha256(audio_dir / 'manifest.json')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the locked Show Orchestration V1 planning baseline.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        verify(args.root.resolve())
        return 0
    except (VerificationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print("SHOW_ORCHESTRATION_BASELINE_FAILED", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
