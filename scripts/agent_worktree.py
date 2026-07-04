from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(RuntimeError):
    """Raised when an isolated agent worktree cannot be prepared safely."""


@dataclass(frozen=True)
class WorktreePlan:
    phase_id: str
    branch_name: str
    worktree_path: Path
    base_branch: str
    base_commit: str


def run_git(
    args: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def repository_root(start: Path) -> Path:
    result = run_git(
        ["rev-parse", "--show-toplevel"],
        cwd=start,
    )

    if result.returncode != 0:
        raise WorktreeError(
            "Current directory is not inside a Git repository.\n"
            f"{result.stderr.strip()}"
        )

    return Path(result.stdout.strip()).resolve()


def require_clean_worktree(repo_root: Path) -> None:
    result = run_git(
        ["status", "--porcelain"],
        cwd=repo_root,
    )

    if result.returncode != 0:
        raise WorktreeError(result.stderr.strip())

    if result.stdout.strip():
        raise WorktreeError(
            "The main repository working tree is not clean.\n"
            "Commit, stash, or remove current changes before preparing "
            "an agent worktree.\n"
            f"{result.stdout.strip()}"
        )


def require_branch(repo_root: Path, expected: str) -> None:
    result = run_git(
        ["branch", "--show-current"],
        cwd=repo_root,
    )

    if result.returncode != 0:
        raise WorktreeError(result.stderr.strip())

    actual = result.stdout.strip()

    if actual != expected:
        raise WorktreeError(
            f"Expected base branch '{expected}', but current branch is "
            f"'{actual}'."
        )


def validate_phase_id(value: str) -> str:
    phase_id = value.strip()

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", phase_id):
        raise WorktreeError(
            "Phase ID must contain only lowercase letters, numbers, and "
            "hyphens; length must be 3 to 64 characters."
        )

    return phase_id


def require_task_file(repo_root: Path, task: Path) -> Path:
    task_path = task

    if not task_path.is_absolute():
        task_path = repo_root / task_path

    task_path = task_path.resolve()

    try:
        task_path.relative_to(repo_root)
    except ValueError as exc:
        raise WorktreeError(
            "Task file must be inside the repository."
        ) from exc

    if not task_path.is_file():
        raise WorktreeError(
            f"Task file does not exist: {task_path}"
        )

    return task_path


def build_plan(
    repo_root: Path,
    *,
    phase_id: str,
    base_branch: str,
) -> WorktreePlan:
    commit_result = run_git(
        ["rev-parse", base_branch],
        cwd=repo_root,
    )

    if commit_result.returncode != 0:
        raise WorktreeError(
            f"Unable to resolve base branch '{base_branch}'.\n"
            f"{commit_result.stderr.strip()}"
        )

    branch_name = f"agent/{phase_id}"
    worktree_path = (
        repo_root
        / ".agent-worktrees"
        / phase_id
    ).resolve()

    return WorktreePlan(
        phase_id=phase_id,
        branch_name=branch_name,
        worktree_path=worktree_path,
        base_branch=base_branch,
        base_commit=commit_result.stdout.strip(),
    )


def require_available_plan(
    repo_root: Path,
    plan: WorktreePlan,
) -> None:
    branch_result = run_git(
        [
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{plan.branch_name}",
        ],
        cwd=repo_root,
    )

    if branch_result.returncode == 0:
        raise WorktreeError(
            f"Agent branch already exists: {plan.branch_name}"
        )

    if branch_result.returncode not in (0, 1):
        raise WorktreeError(
            "Unable to check whether the agent branch exists."
        )

    if plan.worktree_path.exists():
        raise WorktreeError(
            f"Worktree path already exists: {plan.worktree_path}"
        )


def print_plan(
    plan: WorktreePlan,
    task_path: Path,
) -> None:
    print("AGENT_WORKTREE_PLAN_OK")
    print(f"phase_id={plan.phase_id}")
    print(f"task={task_path}")
    print(f"base_branch={plan.base_branch}")
    print(f"base_commit={plan.base_commit}")
    print(f"branch={plan.branch_name}")
    print(f"worktree={plan.worktree_path}")


def create_worktree(
    repo_root: Path,
    plan: WorktreePlan,
) -> None:
    plan.worktree_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = run_git(
        [
            "worktree",
            "add",
            "-b",
            plan.branch_name,
            str(plan.worktree_path),
            plan.base_commit,
        ],
        cwd=repo_root,
    )

    if result.returncode != 0:
        raise WorktreeError(
            "Failed to create agent worktree.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    print("AGENT_WORKTREE_CREATED")
    print(f"branch={plan.branch_name}")
    print(f"worktree={plan.worktree_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a safe isolated LIGHT-BELT agent worktree."
    )
    parser.add_argument(
        "--phase-id",
        required=True,
        help="Lowercase Phase identifier.",
    )
    parser.add_argument(
        "--task",
        required=True,
        type=Path,
        help="Task Markdown file inside the repository.",
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Clean base branch. Default: main.",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--plan-only",
        action="store_true",
        help="Validate and print the plan without creating a worktree.",
    )
    mode.add_argument(
        "--create",
        action="store_true",
        help="Create the isolated branch and Git worktree.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        repo_root = repository_root(Path.cwd())
        require_clean_worktree(repo_root)
        require_branch(repo_root, args.base_branch)

        phase_id = validate_phase_id(args.phase_id)
        task_path = require_task_file(repo_root, args.task)

        plan = build_plan(
            repo_root,
            phase_id=phase_id,
            base_branch=args.base_branch,
        )

        require_available_plan(repo_root, plan)
        print_plan(plan, task_path)

        if args.create:
            create_worktree(repo_root, plan)

        return 0

    except WorktreeError as exc:
        print("AGENT_WORKTREE_FAILED", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
