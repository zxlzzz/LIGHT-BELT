# LIGHT-BELT Codex Instructions

This file defines stable repository-level constraints for future Codex
sessions. Keep it concise, executable, and aligned with the current approved
implementation plan.

## Documentation Authority

When documents or code disagree, use this order:

1. `CLAUDE.md`: permanent project facts and architecture constraints.
2. `docs/CLOSED_LOOP_SPEC.md`: closed-loop target behavior and protocol specs.
3. `docs/IMPLEMENTATION_PLAN.md`: the only authoritative implementation plan.
4. Current source code and tests: evidence of current behavior.

Do not copy the implementation plan into this file. Do not add line-number
references or details likely to drift.

## Windows Python

On Windows, use only the bundled interpreter:

```powershell
.\.python\Scripts\python.exe
```

Never use bare `python`, `python3`, `py`, a Python executable from `C:`, or any
Python executable outside this repository.

Before the first Python command in each Codex session, verify the interpreter.
Codex on Windows may remap the repository into a sandbox path such as
`C:\Users\CodexSandboxOffline\.codex\.sandbox\cwd\<sandbox-id>`, so do not
require `sys.executable` to contain the original drive path or repository
directory name.

```powershell
.\.python\Scripts\python.exe -c "import sys, pathlib, light_engine; cwd=pathlib.Path.cwd().resolve(); exe=pathlib.Path(sys.executable).resolve(); pkg=pathlib.Path(light_engine.__file__).resolve(); candidates=[cwd/'.python'/'Scripts'/'python.exe', cwd/'.python'/'python.exe']; existing=[c for c in candidates if c.exists()]; assert existing, 'No bundled Python found'; assert any(c.resolve()==exe for c in existing), 'Executable mismatch'; assert exe.name.lower()=='python.exe'; assert str(pkg).startswith(str(cwd)); print('executable=', exe); print('package=', pkg); print('PROJECT_PYTHON_OK')"
```

The command is valid when it was invoked as `.\.python\Scripts\python.exe`, the
current workspace contains `.python\Scripts\python.exe` (or the legacy
`.python\python.exe`), at least one of those candidate paths resolves to the
same file as `sys.executable` (tolerating Windows Junctions that share a venv
across worktrees), `light_engine` imports successfully, and the imported
package file is also under the current workspace mapping.

If the bundled interpreter is missing or fails, stop and report the error. Do
not fall back to another Python.

## Working Method

- Start by checking `git status`.
- Implement only the Phase explicitly approved by the user.
- Do not start, prepare, or partially implement later Phases without approval.
- Before modifying files, run the baseline tests with the bundled interpreter:

  ```powershell
  .\.python\Scripts\python.exe -m pytest -q
  ```

- After each coherent change, run relevant tests and then the full test suite.
- Do not delete, skip, loosen, or weaken tests just to get a green result.
- Do not silently swallow errors or manufacture success.
- Do not silently fall back from production hardware transports to memory/fake
  transports.
- Keep changes Phase-scoped and avoid unrelated refactors.
- Do not run `git commit` unless the user explicitly asks for it.

## Core Architecture

- Analog output is RGB+CCT five-channel control: `r`, `g`, `b`,
  `warm_white`, `cool_white`.
- Brightness is applied exactly once, in `OutputTransform`.
- Sequence numbers are assigned only by the Engine.
- One logical frame owns one shared sequence and media timestamp.
- RS-485 and UDP must use the same logical sequence for the same frame.
- Effects and analysis stay hardware-agnostic.
- `DigitalStrip` remains a pure logical model; it must not contain node IDs,
  hosts, ports, offsets, GPIO, or other physical topology.
- Physical details enter only `PhysicalFrame`, physical mapping, protocol, and
  transport layers.
- Protocol codecs must be pure and testable without hardware.
- Golden Vectors use JSON as the single source of truth for host and firmware.
- Production mode must fail explicitly; fake/memory transports require explicit
  config or dependency injection.
- Output queues keep only the latest complete logical frame.
- Do not interleave packets from different logical frames.
- A digital physical node receives one complete UDP frame and refreshes once.
- The default safe state is all black.
- Any behavior not verified on real hardware must be labeled
  `NOT HARDWARE VERIFIED`.

## Git Rules

- Check `git status` before work.
- Keep changes independently reviewable at Phase boundaries.
- Preserve user changes; never overwrite or revert work you did not make.
- Do not use destructive Git commands such as `git reset --hard` or
  `git checkout --` unless the user explicitly requests them.
- Do not stage, commit, push, or create PRs unless explicitly requested.

## Reporting

At the end of a task, report:

- Modified files.
- Actual commands run and their return codes.
- Test count and elapsed time for executed tests.
- Unresolved issues or limitations.
- `git diff --stat`.

If the final required benchmark or firmware build is in scope for the approved
Phase, also report its command, return code, and measured output. Never claim
hardware verification without real evidence.

