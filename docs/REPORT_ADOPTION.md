# Deep-Research Report Adoption Record

This record distinguishes report recommendations that were adopted, deferred, or rejected for Show Orchestration V1.

## Adopted

1. **Single-authority contracts** — added Frame, Compose, Time, Music, and Quality Gate contracts.
2. **Cross-Phase locked goldens** — added G1–G8 fixtures and SHA-256 manifest; implementation Phases may not edit them.
3. **Fixed music fixture set** — added deterministic WAVs for rhythmic 120 BPM, irregular piano, string crescendo, sustained bass, and silence.
4. **Relational music assertions** — music goldens use documented ranges/relations instead of brittle exact floating-point snapshots.
5. **Adaptive decision explainability** — Phase 16 now requires `SelectionDecision`, finite feature snapshots, and a fixed reason-code catalog.
6. **Differential repair budgets** — Phases 15–16 receive 3 repairs; Phase 17 receives 1.
7. **Human risk checkpoints without losing automation** — added four segmented campaign manifests.
8. **Audit evidence and mechanical preflight** — added required baseline/head SHA, test-change, skip/xfail, golden-hash, command, traceability, and artifact fields, plus `scripts/verify_show_orchestration_baseline.py`.
9. **Physical-gap model at V1 scale** — added optional `gap_after_pixels`; millimetre calibration remains deferred.
10. **Real-time five-minute soak** — Phase 17 now requires a separate 300-second real-time software run and metrics.
11. **Artifact hashes** — Phase 17 must hash summaries, traces, selected frames, metrics, and build logs.
12. **Minimal/full YAML templates** — added a minimal authoring example while retaining the full adaptive example.

## Partially adopted

1. **Immutable tests** — the entire `tests/**` tree is not frozen because each Phase must add legitimate tests. Instead, baseline contracts, G1–G8 data, and fixed audio fixtures are locked, while test-code changes are explicitly audited.
2. **Hard/soft gates** — correctness remains hard; measurements are reported and become blocking only where the task explicitly states a performance requirement.
3. **Music stage further splitting** — the existing split into Phase 15 feature extraction and Phase 16 selection is retained. A third tuning Phase was not added because it would duplicate Phase 16 policy/parameter work without a separate deliverable.
4. **Gap modelling** — pixel gaps are supported; `gap_mm` and pixels-per-metre calibration remain outside V1.

## Deferred or rejected for this campaign

1. **GitHub Actions permissions, CODEOWNERS, third-party Action SHA pinning, and artifact attestation** — valuable for a hosted CI deployment, but not directly applicable to the current local PowerShell + Git worktree + Codex/Claude pipeline.
2. **Automatic assertion-count comparison** — unreliable as a correctness signal and prone to false positives. Concrete goldens and test-diff auditing are used instead.
3. **Machine-learning music classification** — unnecessary and contrary to the deterministic rule-based V1 boundary.
4. **Guaranteeing teacher-approved aesthetics in software tests** — impossible; hardware and human visual acceptance remain mandatory.
