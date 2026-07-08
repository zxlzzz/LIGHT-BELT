# Install and Run the Hardened Show Orchestration V1 Campaign

Run from `A:\BaiduNetdiskDownload\LIGHT-BELT` in PowerShell.

## 1. Verify the closed-loop baseline

```powershell
git status --short
git branch --list "campaign/closed-loop-v2"
git log -3 --oneline "campaign/closed-loop-v2"
```

The working tree must be clean.

## 2. Create the planning base branch

The manifests start from a branch that already contains every task, contract, golden, and fixture.

```powershell
git switch campaign/closed-loop-v2
git switch -c campaign/show-orchestration-v1-base
```

If the base branch already exists and is known-good:

```powershell
git switch campaign/show-orchestration-v1-base
```

Record its SHA:

```powershell
$planningBaseSha = git rev-parse HEAD
$planningBaseSha
```

## 3. Copy this bundle into the repository

After copying, verify at least these paths:

```text
.agent\campaigns\show-orchestration-v1.json
.agent\campaigns\show-orchestration-v1-a-foundation.json
.agent\campaigns\show-orchestration-v1-b-runtime.json
.agent\campaigns\show-orchestration-v1-c-music.json
.agent\campaigns\show-orchestration-v1-d-acceptance.json
.agent\contracts\phase-audit.schema.json
.agent\tasks\phase-11-show-schema.md
...
.agent\tasks\phase-17-show-acceptance.md
config\show.minimal.example.yaml
config\show.example.yaml
config\virtual_paths.example.yaml
docs\contracts\FRAME_CONTRACT.md
docs\contracts\COMPOSE_CONTRACT.md
docs\contracts\TIME_CONTRACT.md
docs\contracts\MUSIC_CONTROL_CONTRACT.md
docs\contracts\QUALITY_GATE_CONTRACT.md
tests\goldens\show_orchestration\v1\MANIFEST.sha256
tests\fixtures\audio\show_orchestration_v1\manifest.json
```

Remove obsolete draft tasks if present:

```powershell
Remove-Item .agent\tasks\phase-15-music-adaptation.md -ErrorAction SilentlyContinue
Remove-Item .agent\tasks\phase-16-show-acceptance.md -ErrorAction SilentlyContinue
```

Commit the complete planning baseline, including locked evidence:

```powershell
git add .agent config docs tests/goldens tests/fixtures/audio/show_orchestration_v1/manifest.json scripts/verify_show_orchestration_baseline.py REVIEW_AND_CHANGES.md INSTALL_AND_RUN.md
# The repository .gitignore ignores *.wav globally; these locked synthetic fixtures must be force-added once.
git add -f tests/fixtures/audio/show_orchestration_v1/*.wav
git commit -m "Plan evidence-hardened show orchestration v1 campaign"
```

Record the committed baseline SHA:

```powershell
$planningBaseSha = git rev-parse HEAD
$planningBaseSha
```

## 4. Verify locked evidence before execution

```powershell
Get-Content tests\goldens\show_orchestration\v1\MANIFEST.sha256
Get-Content tests\fixtures\audio\show_orchestration_v1\manifest.json
```

Do not regenerate or edit these files during implementation Phases.

## 5. Verify the committed planning baseline and run preflight

```powershell
.\.python\Scripts\python.exe scripts\verify_show_orchestration_baseline.py
.\.python\Scripts\python.exe scripts\agent_pipeline.py --preflight
git status --short
```

Do not continue unless the commands print `SHOW_ORCHESTRATION_BASELINE_OK` and `AGENT_PIPELINE_PREFLIGHT_OK`, and the working tree is clean.

## 6. Recommended checkpointed execution

This keeps Codex implementation, Claude review, automatic repairs, isolated worktrees, and automatic Git behavior, while allowing inspection at four risk boundaries.

### Campaign A — schema and virtual paths

```powershell
.\.python\Scripts\python.exe scripts\agent_campaign.py `
  --manifest .agent\campaigns\show-orchestration-v1-a-foundation.json
```

Before Campaign B, inspect:

- Phase 11 validation errors for G1/G2;
- Phase 12 G3 seam, reverse, and virtual-gap evidence;
- no unresolved Claude BLOCKER;
- generated campaign branch `campaign/show-orchestration-v1-a-foundation` exists.

### Campaign B — compositor and timeline

```powershell
.\.python\Scripts\python.exe scripts\agent_campaign.py `
  --manifest .agent\campaigns\show-orchestration-v1-b-runtime.json
```

Inspect G4 absence/black behavior, G5/G6 boundary/local-time evidence, and a short simulated show.

### Campaign C — music features and selector

```powershell
.\.python\Scripts\python.exe scripts\agent_campaign.py `
  --manifest .agent\campaigns\show-orchestration-v1-c-music.json
```

Inspect fixed WAV hashes, per-fixture feature summaries, selector reason codes, and hold/cooldown traces.

### Campaign D — acceptance

```powershell
.\.python\Scripts\python.exe scripts\agent_campaign.py `
  --manifest .agent\campaigns\show-orchestration-v1-d-acceptance.json
```

Inspect offline digests, 300-second real-time soak metrics, protocol sequence traces, artifact hashes, and `NOT HARDWARE VERIFIED`.

## 7. Optional uninterrupted full campaign

Use only after the checkpointed manifests and branch chaining have been verified:

```powershell
.\.python\Scripts\python.exe scripts\agent_campaign.py `
  --manifest .agent\campaigns\show-orchestration-v1.json
```

The campaign stops on an unresolved Phase. Do not manually advance past a failed hard gate.

## 8. Inspect reports

```powershell
$phases = @(
  "phase-11-show-schema",
  "phase-12-virtual-paths",
  "phase-13-target-compositor",
  "phase-14-timeline-transitions",
  "phase-15-music-control",
  "phase-16-adaptive-selector",
  "phase-17-show-acceptance"
)

foreach ($phase in $phases) {
  Write-Host "===== $phase ====="
  Get-ChildItem ".agent\reports\$phase" -Recurse -ErrorAction SilentlyContinue
  Get-Content ".agent\reports\$phase\final-result.json" -ErrorAction SilentlyContinue
}

git status --short
git log --oneline --decorate -20
```

A Phase is accepted only if:

- required commands passed;
- no forbidden or locked-evidence file changed;
- skip/xfail counts did not increase;
- golden manifest hash matches;
- audit fields and traceability are present;
- Claude has no unresolved BLOCKER.

## 9. After software acceptance

Phase 17 must still state `NOT HARDWARE VERIFIED`. Perform `docs\SHOW_HARDWARE_ACCEPTANCE_CHECKLIST.md` before making a hardware-complete claim.
