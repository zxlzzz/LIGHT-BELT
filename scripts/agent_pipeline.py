from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 3600
DEFAULT_MAX_REPAIRS = 3

REQUIRED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/CLOSED_LOOP_SPEC.md",
    "docs/IMPLEMENTATION_PLAN.md",
    ".agent/review.schema.json",
    ".agent/prompts/implementer.md",
    ".agent/prompts/reviewer.md",
    ".agent/prompts/repairer.md",
    "scripts/agent_worktree.py",
)

REQUIRED_COMMANDS = ("git", "codex", "claude")


class PipelineError(RuntimeError):
    """Raised when the pipeline cannot continue safely."""


@dataclass(frozen=True)
class TaskSpec:
    phase_id: str
    task_path: Path
    task_relative: Path
    allowed_patterns: tuple[str, ...]
    forbidden_patterns: tuple[str, ...]
    targeted_commands: tuple[str, ...]
    full_commands: tuple[str, ...]
    commit_message: str


@dataclass(frozen=True)
class PipelineContext:
    repo_root: Path
    base_branch: str
    base_commit: str
    worktree_path: Path
    agent_branch: str
    report_dir: Path
    project_python: Path
    task: TaskSpec


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_command(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise PipelineError(f"Required command not found on PATH: {name}")
    return resolved


def run_process(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 60,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    if not command:
        raise PipelineError("Refusing to run an empty command.")

    executable = resolve_command(command[0])

    try:
        return subprocess.run(
            [executable, *command[1:]],
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=input_text,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(
            f"Command timed out after {timeout}s: {' '.join(command)}"
        ) from exc


def run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return run_process(["git", *args], cwd=cwd, timeout=timeout)


def find_repo_root(start: Path) -> Path:
    result = run_git(["rev-parse", "--show-toplevel"], cwd=start)
    if result.returncode != 0:
        raise PipelineError(
            "Current directory is not inside a Git repository.\n"
            f"{result.stderr.strip()}"
        )
    return Path(result.stdout.strip()).resolve()


def require_files_and_commands(repo_root: Path) -> None:
    missing_files = [
        item for item in REQUIRED_FILES if not (repo_root / item).is_file()
    ]
    missing_commands = [
        item for item in REQUIRED_COMMANDS if shutil.which(item) is None
    ]

    if missing_files:
        raise PipelineError(
            "Missing required files:\n"
            + "\n".join(f"- {item}" for item in missing_files)
        )
    if missing_commands:
        raise PipelineError(
            "Missing required commands: " + ", ".join(missing_commands)
        )


def get_branch(repo_root: Path) -> str:
    result = run_git(["branch", "--show-current"], cwd=repo_root)
    if result.returncode != 0:
        raise PipelineError(result.stderr.strip())
    return result.stdout.strip()


def get_status(repo_root: Path) -> str:
    result = run_git(["status", "--porcelain"], cwd=repo_root)
    if result.returncode != 0:
        raise PipelineError(result.stderr.strip())
    return result.stdout.strip()


def require_clean_base(repo_root: Path, base_branch: str) -> str:
    current = get_branch(repo_root)
    if current != base_branch:
        raise PipelineError(
            f"Current branch is '{current}', expected '{base_branch}'."
        )

    status = get_status(repo_root)
    if status:
        raise PipelineError(
            "Base worktree must be clean before starting.\n" + status
        )

    result = run_git(["rev-parse", base_branch], cwd=repo_root)
    if result.returncode != 0:
        raise PipelineError(result.stderr.strip())
    return result.stdout.strip()


def validate_phase_id(value: str) -> str:
    phase_id = value.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", phase_id):
        raise PipelineError(
            "Phase ID must use lowercase letters, numbers, and hyphens "
            "(3-64 characters)."
        )
    return phase_id


def resolve_task_path(repo_root: Path, value: Path) -> tuple[Path, Path]:
    task_path = value if value.is_absolute() else repo_root / value
    task_path = task_path.resolve()

    try:
        relative = task_path.relative_to(repo_root)
    except ValueError as exc:
        raise PipelineError("Task file must be inside the repository.") from exc

    if not task_path.is_file():
        raise PipelineError(f"Task file does not exist: {task_path}")

    tracked = run_git(["ls-files", "--error-unmatch", relative.as_posix()], cwd=repo_root)
    if tracked.returncode != 0:
        raise PipelineError(
            "Task file must be committed before the pipeline starts: "
            f"{relative.as_posix()}"
        )

    return task_path, relative


def section_lines(text: str, heading: str) -> list[str]:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return []
    return [line.rstrip() for line in match.group(1).splitlines()]


def bullet_items(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip().strip("`")
            if value:
                items.append(value)
    return items


def command_items(lines: list[str]) -> list[str]:
    commands: list[str] = []
    in_fence = False

    for raw in lines:
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if not line or line.startswith("#"):
            continue
        if in_fence or line.startswith((".\\", "git ", "pio ", "rg ")):
            commands.append(line)

    return commands


def first_nonempty(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("```"):
            return stripped.strip("`")
    return ""


def parse_task(
    repo_root: Path,
    phase_id: str,
    task_path: Path,
    task_relative: Path,
) -> TaskSpec:
    text = task_path.read_text(encoding="utf-8-sig")

    declared_phase = first_nonempty(section_lines(text, "Phase ID"))
    if declared_phase and declared_phase != phase_id:
        raise PipelineError(
            f"Task Phase ID is '{declared_phase}', but CLI Phase ID is "
            f"'{phase_id}'."
        )

    allowed = tuple(bullet_items(section_lines(text, "Allowed Files")))
    forbidden = tuple(bullet_items(section_lines(text, "Forbidden Files")))
    targeted = tuple(command_items(section_lines(text, "Required Targeted Tests")))
    full = tuple(command_items(section_lines(text, "Required Full Verification")))
    commit_message = first_nonempty(section_lines(text, "Commit Message"))

    if not allowed:
        raise PipelineError("Task must contain at least one Allowed Files pattern.")
    if not full:
        raise PipelineError(
            "Task must contain at least one Required Full Verification command."
        )
    if not commit_message:
        commit_message = f"feat: complete {phase_id}"

    return TaskSpec(
        phase_id=phase_id,
        task_path=task_path,
        task_relative=task_relative,
        allowed_patterns=allowed,
        forbidden_patterns=forbidden,
        targeted_commands=targeted,
        full_commands=full,
        commit_message=commit_message,
    )


def verify_project_python(repo_root: Path) -> Path:
    python_executable = repo_root / ".python" / "python.exe"
    if not python_executable.is_file():
        raise PipelineError(
            f"Bundled project Python not found: {python_executable}"
        )

    result = run_process(
        [
            str(python_executable),
            "-c",
            (
                "import pathlib,sys,light_engine;"
                "exe=pathlib.Path(sys.executable).resolve();"
                "cwd=pathlib.Path.cwd().resolve();"
                "pkg=pathlib.Path(light_engine.__file__).resolve();"
                "assert exe.name.lower()=='python.exe';"
                "assert exe.parent.name=='.python';"
                "assert exe.parent.parent==cwd;"
                "assert str(pkg).startswith(str(cwd));"
                "print('PROJECT_PYTHON_OK')"
            ),
        ],
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise PipelineError(
            "Bundled Python verification failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return python_executable


def create_worktree(
    repo_root: Path,
    project_python: Path,
    task: TaskSpec,
    base_branch: str,
    timeout: int,
) -> tuple[Path, str]:
    worktree_path = (repo_root / ".agent-worktrees" / task.phase_id).resolve()
    agent_branch = f"agent/{task.phase_id}"

    result = run_process(
        [
            str(project_python),
            "scripts/agent_worktree.py",
            "--phase-id",
            task.phase_id,
            "--task",
            str(task.task_path),
            "--base-branch",
            base_branch,
            "--create",
        ],
        cwd=repo_root,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise PipelineError(
            "Failed to create isolated worktree.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    if not worktree_path.is_dir():
        raise PipelineError(f"Worktree path missing after creation: {worktree_path}")
    return worktree_path, agent_branch


def _copy_or_link_file(source: str, destination: str) -> str:
    try:
        os.link(source, destination)
        return destination
    except OSError:
        return shutil.copy2(source, destination)


def ensure_worktree_python(repo_root: Path, worktree_path: Path) -> Path:
    source = (repo_root / ".python").resolve()
    destination = worktree_path / ".python"

    if destination.exists():
        python_executable = destination / (
            "python.exe" if os.name == "nt" else "bin/python"
        )
        if python_executable.exists():
            return python_executable
        raise PipelineError(
            f"Existing worktree Python directory is incomplete: {destination}"
        )

    try:
        shutil.copytree(
            source,
            destination,
            copy_function=_copy_or_link_file,
            symlinks=True,
        )
    except Exception as exc:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise PipelineError(
            "Failed to mirror the bundled .python environment into the "
            f"worktree: {exc}"
        ) from exc

    python_executable = destination / (
        "python.exe" if os.name == "nt" else "bin/python"
    )
    if not python_executable.exists():
        raise PipelineError(
            f"Worktree Python mirror is missing its interpreter: "
            f"{python_executable}"
        )

    verification = run_process(
        [
            str(python_executable),
            "-c",
            (
                "import pathlib,sys,light_engine;"
                "exe=pathlib.Path(sys.executable).resolve();"
                "cwd=pathlib.Path.cwd().resolve();"
                "pkg=pathlib.Path(light_engine.__file__).resolve();"
                "assert exe.name.lower()=='python.exe';"
                "assert exe.parent.name=='.python';"
                "assert exe.parent.parent==cwd;"
                "assert str(pkg).startswith(str(cwd));"
                "print('WORKTREE_PROJECT_PYTHON_OK')"
            ),
        ],
        cwd=worktree_path,
        timeout=120,
    )
    if verification.returncode != 0:
        raise PipelineError(
            "Worktree Python verification failed.\n"
            f"stdout:\n{verification.stdout}\n"
            f"stderr:\n{verification.stderr}"
        )

    return python_executable


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_process(
    path: Path,
    command: list[str] | str,
    result: subprocess.CompletedProcess[str],
) -> None:
    write_json(
        path,
        {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "recorded_at_utc": now_utc(),
        },
    )


def shell_command(command: str, *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    if os.name == "nt":
        return run_process(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            cwd=cwd,
            timeout=timeout,
        )

    return run_process(["bash", "-lc", command], cwd=cwd, timeout=timeout)


def build_context(
    repo_root: Path,
    base_branch: str,
    base_commit: str,
    task: TaskSpec,
    project_python: Path,
    timeout: int,
) -> PipelineContext:
    report_dir = (repo_root / ".agent" / "reports" / task.phase_id).resolve()
    if report_dir.exists():
        raise PipelineError(
            f"Report directory already exists: {report_dir}"
        )

    worktree_path, agent_branch = create_worktree(
        repo_root,
        project_python,
        task,
        base_branch,
        timeout,
    )
    ensure_worktree_python(repo_root, worktree_path)
    report_dir.mkdir(parents=True)

    return PipelineContext(
        repo_root=repo_root,
        base_branch=base_branch,
        base_commit=base_commit,
        worktree_path=worktree_path,
        agent_branch=agent_branch,
        report_dir=report_dir,
        project_python=project_python,
        task=task,
    )


def relative_task_in_worktree(ctx: PipelineContext) -> Path:
    task_path = ctx.worktree_path / ctx.task.task_relative
    if not task_path.is_file():
        raise PipelineError(
            f"Committed task file is missing from worktree: {task_path}"
        )
    return task_path


def build_implement_prompt(ctx: PipelineContext, iteration: int) -> str:
    prompt_path = ctx.worktree_path / ".agent" / "prompts" / "implementer.md"
    base = prompt_path.read_text(encoding="utf-8-sig")
    task_relative = ctx.task.task_relative.as_posix()
    report_relative = (
        Path(".agent")
        / "reports"
        / ctx.task.phase_id
        / f"codex-implementation-{iteration}.md"
    ).as_posix()

    return (
        f"{base}\n\n"
        "Orchestrator inputs:\n"
        f"- Task file: `{task_relative}`\n"
        f"- Iteration: {iteration}\n"
        f"- Required report path: `{report_relative}`\n\n"
        "Do not commit, stage, switch branches, or modify files outside this "
        "worktree. Finish by writing the required report file."
    )


def build_repair_prompt(ctx: PipelineContext, iteration: int, review: dict[str, Any]) -> str:
    prompt_path = ctx.worktree_path / ".agent" / "prompts" / "repairer.md"
    base = prompt_path.read_text(encoding="utf-8-sig")
    report_relative = (
        Path(".agent")
        / "reports"
        / ctx.task.phase_id
        / f"codex-repair-{iteration}.md"
    ).as_posix()

    return (
        f"{base}\n\n"
        f"Task file: `{ctx.task.task_relative.as_posix()}`\n"
        f"Repair iteration: {iteration}\n"
        f"Required repair report path: `{report_relative}`\n\n"
        "Independent review JSON:\n"
        + json.dumps(review, indent=2, ensure_ascii=False)
        + "\n\nDo not commit, stage, or switch branches."
    )


def run_codex(
    ctx: PipelineContext,
    prompt: str,
    *,
    report_name: str,
    process_name: str,
    timeout: int,
) -> None:
    worktree_report = (
        ctx.worktree_path / ".agent" / "reports" / ctx.task.phase_id / report_name
    )
    worktree_report.parent.mkdir(parents=True, exist_ok=True)

    result = run_process(
        [
            "codex",
            "exec",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(ctx.worktree_path),
            "--output-last-message",
            str(worktree_report),
            "-",
        ],
        cwd=ctx.worktree_path,
        timeout=timeout,
        input_text=prompt,
    )
    save_process(
        ctx.report_dir / process_name,
        "codex exec --ephemeral --sandbox workspace-write ...",
        result,
    )

    if worktree_report.is_file():
        shutil.copy2(worktree_report, ctx.report_dir / report_name)

    if result.returncode != 0:
        raise PipelineError(
            f"Codex stage failed with return code {result.returncode}. "
            f"See {ctx.report_dir / process_name}"
        )
    if not worktree_report.is_file():
        raise PipelineError(
            f"Codex did not create required report: {worktree_report}"
        )


def changed_files(ctx: PipelineContext) -> list[str]:
    result = run_git(
        ["diff", "--name-only", ctx.base_commit],
        cwd=ctx.worktree_path,
    )
    if result.returncode != 0:
        raise PipelineError(result.stderr.strip())

    untracked = run_git(
        ["ls-files", "--others", "--exclude-standard"],
        cwd=ctx.worktree_path,
    )
    if untracked.returncode != 0:
        raise PipelineError(untracked.stderr.strip())

    names = {
        line.strip().replace("\\", "/")
        for line in (result.stdout + "\n" + untracked.stdout).splitlines()
        if line.strip()
    }
    return sorted(names)


def matches_pattern(path: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/").strip()
    if normalized.endswith("/**"):
        prefix = normalized[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, normalized)


def enforce_file_scope(ctx: PipelineContext) -> list[str]:
    names = changed_files(ctx)
    violations: list[str] = []

    ignored_prefixes = (
        f".agent/reports/{ctx.task.phase_id}/",
    )

    for name in names:
        if name.startswith(ignored_prefixes):
            continue

        forbidden = any(
            matches_pattern(name, pattern)
            for pattern in ctx.task.forbidden_patterns
        )
        allowed = any(
            matches_pattern(name, pattern)
            for pattern in ctx.task.allowed_patterns
        )

        if forbidden or not allowed:
            violations.append(name)

    if violations:
        raise PipelineError(
            "Changed files violate the task scope:\n"
            + "\n".join(f"- {item}" for item in violations)
        )
    return names


def run_quality_gate(
    ctx: PipelineContext,
    *,
    iteration: int,
    timeout: int,
) -> dict[str, Any]:
    commands = [
        *ctx.task.targeted_commands,
        *ctx.task.full_commands,
    ]
    if not commands:
        raise PipelineError("No verification commands were configured.")

    records: list[dict[str, Any]] = []
    passed = True

    for index, command in enumerate(commands, start=1):
        result = shell_command(command, cwd=ctx.worktree_path, timeout=timeout)
        record = {
            "index": index,
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        records.append(record)
        if result.returncode != 0:
            passed = False
            break

    scope_error = ""
    changed: list[str] = []
    try:
        changed = enforce_file_scope(ctx)
    except PipelineError as exc:
        passed = False
        scope_error = str(exc)

    payload = {
        "iteration": iteration,
        "passed": passed,
        "commands": records,
        "changed_files": changed,
        "scope_error": scope_error,
        "recorded_at_utc": now_utc(),
    }
    write_json(
        ctx.report_dir / f"quality-gate-{iteration}.json",
        payload,
    )
    return payload


def git_diff_text(ctx: PipelineContext) -> str:
    result = run_git(["diff", ctx.base_commit, "--"], cwd=ctx.worktree_path)
    if result.returncode != 0:
        raise PipelineError(result.stderr.strip())
    return result.stdout


def build_review_prompt(
    ctx: PipelineContext,
    *,
    iteration: int,
    quality: dict[str, Any],
) -> str:
    reviewer = (
        ctx.worktree_path / ".agent" / "prompts" / "reviewer.md"
    ).read_text(encoding="utf-8-sig")
    task_text = relative_task_in_worktree(ctx).read_text(encoding="utf-8-sig")
    schema = (
        ctx.worktree_path / ".agent" / "review.schema.json"
    ).read_text(encoding="utf-8-sig")
    diff = git_diff_text(ctx)

    return (
        f"{reviewer}\n\n"
        f"Iteration: {iteration}\n\n"
        "TASK FILE:\n"
        f"{task_text}\n\n"
        "QUALITY GATE:\n"
        f"{json.dumps(quality, indent=2, ensure_ascii=False)}\n\n"
        "GIT DIFF AGAINST BASE:\n"
        f"{diff}\n\n"
        "OUTPUT JSON SCHEMA:\n"
        f"{schema}\n"
    )


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(stripped[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError as exc:
            raise PipelineError(
                "Claude output contained invalid JSON."
            ) from exc

    raise PipelineError("Claude output did not contain a JSON object.")


def validate_review(review: dict[str, Any]) -> None:
    required = (
        "verdict",
        "summary",
        "blockers",
        "high",
        "medium",
        "required_actions",
    )
    missing = [key for key in required if key not in review]
    if missing:
        raise PipelineError(
            "Review JSON is missing fields: " + ", ".join(missing)
        )

    if review["verdict"] not in ("PASS", "FAIL"):
        raise PipelineError("Review verdict must be PASS or FAIL.")

    for key in ("blockers", "high", "medium", "required_actions"):
        if not isinstance(review[key], list):
            raise PipelineError(f"Review field '{key}' must be a list.")

    if review["verdict"] == "PASS":
        if review["blockers"] or review["high"]:
            raise PipelineError(
                "PASS review cannot contain BLOCKER or HIGH findings."
            )
    elif not review["required_actions"]:
        raise PipelineError(
            "FAIL review must contain at least one required action."
        )


def run_claude_review(
    ctx: PipelineContext,
    *,
    iteration: int,
    quality: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    before = get_status(ctx.worktree_path)
    prompt = build_review_prompt(ctx, iteration=iteration, quality=quality)

    review_input = (
        ctx.worktree_path
        / ".agent"
        / "reports"
        / ctx.task.phase_id
        / f"review-input-{iteration}.md"
    )
    review_input.parent.mkdir(parents=True, exist_ok=True)
    review_input.write_text(prompt, encoding="utf-8")

    short_prompt = (
        f"Read `{review_input.relative_to(ctx.worktree_path).as_posix()}` "
        "and perform the independent review exactly as instructed there. "
        "Return only the required JSON object."
    )

    result = run_process(
        ["claude", "-p", short_prompt],
        cwd=ctx.worktree_path,
        timeout=timeout,
    )
    save_process(
        ctx.report_dir / f"claude-process-{iteration}.json",
        "claude -p <review input file instruction>",
        result,
    )

    after = get_status(ctx.worktree_path)
    if after != before:
        raise PipelineError(
            "Claude reviewer modified the worktree; review was rejected."
        )
    if result.returncode != 0:
        raise PipelineError(
            f"Claude review failed with return code {result.returncode}."
        )

    review = extract_json_object(result.stdout)
    validate_review(review)
    write_json(ctx.report_dir / f"claude-review-{iteration}.json", review)
    return review


def commit_success(ctx: PipelineContext) -> str:
    add_result = run_git(["add", "-A"], cwd=ctx.worktree_path)
    if add_result.returncode != 0:
        raise PipelineError(add_result.stderr.strip())

    commit_result = run_git(
        ["commit", "-m", ctx.task.commit_message],
        cwd=ctx.worktree_path,
    )
    if commit_result.returncode != 0:
        raise PipelineError(
            "Final commit failed.\n"
            f"stdout:\n{commit_result.stdout}\n"
            f"stderr:\n{commit_result.stderr}"
        )

    hash_result = run_git(["rev-parse", "HEAD"], cwd=ctx.worktree_path)
    if hash_result.returncode != 0:
        raise PipelineError(hash_result.stderr.strip())
    return hash_result.stdout.strip()


def remove_success_worktree(ctx: PipelineContext) -> None:
    result = run_git(
        ["worktree", "remove", str(ctx.worktree_path), "--force"],
        cwd=ctx.repo_root,
    )
    if result.returncode != 0:
        raise PipelineError(
            "Commit succeeded, but worktree removal failed.\n"
            f"{result.stderr.strip()}"
        )
    run_git(["worktree", "prune"], cwd=ctx.repo_root)


def cleanup_failure(ctx: PipelineContext, timeout: int) -> None:
    result = run_process(
        [
            str(ctx.project_python),
            "scripts/agent_worktree.py",
            "--phase-id",
            ctx.task.phase_id,
            "--cleanup",
            "--force",
        ],
        cwd=ctx.repo_root,
        timeout=timeout,
    )
    save_process(
        ctx.report_dir / "cleanup-process.json",
        "agent_worktree.py --cleanup --force",
        result,
    )


def run_pipeline(
    *,
    task_path_arg: Path,
    phase_id_arg: str,
    base_branch: str,
    timeout: int,
    max_repairs: int,
    keep_failed_worktree: bool,
) -> int:
    repo_root = find_repo_root(Path.cwd())
    require_files_and_commands(repo_root)
    project_python = verify_project_python(repo_root)
    base_commit = require_clean_base(repo_root, base_branch)

    phase_id = validate_phase_id(phase_id_arg)
    task_path, task_relative = resolve_task_path(repo_root, task_path_arg)
    task = parse_task(
        repo_root,
        phase_id,
        task_path,
        task_relative,
    )

    ctx: PipelineContext | None = None

    try:
        ctx = build_context(
            repo_root,
            base_branch,
            base_commit,
            task,
            project_python,
            timeout,
        )

        write_json(
            ctx.report_dir / "run-metadata.json",
            {
                "phase_id": phase_id,
                "base_branch": base_branch,
                "base_commit": base_commit,
                "agent_branch": ctx.agent_branch,
                "task": task_relative.as_posix(),
                "started_at_utc": now_utc(),
                "max_repairs": max_repairs,
            },
        )

        iteration = 1
        run_codex(
            ctx,
            build_implement_prompt(ctx, iteration),
            report_name=f"codex-implementation-{iteration}.md",
            process_name=f"codex-process-{iteration}.json",
            timeout=timeout,
        )

        repairs_used = 0

        while True:
            quality = run_quality_gate(
                ctx,
                iteration=iteration,
                timeout=timeout,
            )

            if quality["passed"]:
                review = run_claude_review(
                    ctx,
                    iteration=iteration,
                    quality=quality,
                    timeout=timeout,
                )
            else:
                review = {
                    "verdict": "FAIL",
                    "summary": "Deterministic quality gate failed.",
                    "blockers": [],
                    "high": [],
                    "medium": [],
                    "required_actions": [
                        "Fix every failing quality-gate command and any "
                        "file-scope violation recorded in the latest report."
                    ],
                }
                write_json(
                    ctx.report_dir / f"synthetic-review-{iteration}.json",
                    review,
                )

            if quality["passed"] and review["verdict"] == "PASS":
                commit_hash = commit_success(ctx)
                remove_success_worktree(ctx)
                write_json(
                    ctx.report_dir / "final-result.json",
                    {
                        "status": "PASS",
                        "phase_id": phase_id,
                        "branch": ctx.agent_branch,
                        "commit": commit_hash,
                        "repairs_used": repairs_used,
                        "finished_at_utc": now_utc(),
                    },
                )
                print("AGENT_PIPELINE_PASS")
                print(f"branch={ctx.agent_branch}")
                print(f"commit={commit_hash}")
                print(f"reports={ctx.report_dir}")
                return 0

            if repairs_used >= max_repairs:
                raise PipelineError(
                    f"Maximum repair count reached ({max_repairs})."
                )

            repairs_used += 1
            iteration += 1

            run_codex(
                ctx,
                build_repair_prompt(ctx, iteration, review),
                report_name=f"codex-repair-{iteration}.md",
                process_name=f"codex-repair-process-{iteration}.json",
                timeout=timeout,
            )

    except Exception as exc:
        if ctx is not None:
            write_json(
                ctx.report_dir / "final-result.json",
                {
                    "status": "FAIL",
                    "phase_id": phase_id,
                    "error": str(exc),
                    "finished_at_utc": now_utc(),
                },
            )
            if not keep_failed_worktree:
                cleanup_failure(ctx, timeout)

        if isinstance(exc, PipelineError):
            raise
        raise PipelineError(str(exc)) from exc


def run_preflight() -> int:
    repo_root = find_repo_root(Path.cwd())
    require_files_and_commands(repo_root)
    project_python = verify_project_python(repo_root)

    print("AGENT_PIPELINE_PREFLIGHT_OK")
    print(f"repository={repo_root}")
    print(f"branch={get_branch(repo_root)}")
    print(f"python={project_python}")
    for name in REQUIRED_COMMANDS:
        result = run_process([name, "--version"], cwd=repo_root)
        print(f"{name}={result.stdout.strip()}")
    print("working_tree=CLEAN" if not get_status(repo_root) else "working_tree=DIRTY")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LIGHT-BELT Codex + Claude dual-agent pipeline."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--run", action="store_true")

    parser.add_argument("--phase-id")
    parser.add_argument("--task", type=Path)
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--max-repairs",
        type=int,
        default=DEFAULT_MAX_REPAIRS,
    )
    parser.add_argument(
        "--keep-failed-worktree",
        action="store_true",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.preflight:
            return run_preflight()

        if not args.phase_id or args.task is None:
            raise PipelineError("--phase-id and --task are required with --run.")
        if args.timeout <= 0:
            raise PipelineError("--timeout must be greater than zero.")
        if args.max_repairs < 0 or args.max_repairs > 10:
            raise PipelineError("--max-repairs must be between 0 and 10.")

        return run_pipeline(
            task_path_arg=args.task,
            phase_id_arg=args.phase_id,
            base_branch=args.base_branch,
            timeout=args.timeout,
            max_repairs=args.max_repairs,
            keep_failed_worktree=args.keep_failed_worktree,
        )

    except PipelineError as exc:
        print("AGENT_PIPELINE_FAILED", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
