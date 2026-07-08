# Show Orchestration V1 — Quality Gate Contract

## Gate A — hard correctness

A Phase cannot pass if any of these fail:

- required contract/golden behavior;
- full existing tests;
- no new skip/xfail bypass;
- no forbidden-file changes;
- no unknown-field fallback or test-aware production behavior;
- finite/bounded-state requirements;
- required traceability and audit evidence.

## Gate B — measured engineering evidence

The following are measured and reported. A threshold explicitly marked MUST remains blocking; an informational baseline is not silently converted into a pass/fail rule:

- processing capacity and P95 processing time;
- real-time output FPS;
- memory/queue/history measurements;
- selector decision counts and fallback distribution;
- hardware/network observations.

A reviewer may declare a BLOCKER when a measured regression threatens the 30 FPS target, but MUST include measurements and the responsible contract.

## Locked evidence

Files under `tests/goldens/show_orchestration/v1/**`, fixed audio fixtures under `tests/fixtures/audio/show_orchestration_v1/**`, and `docs/contracts/**` are planning-baseline evidence. Implementation Phases MUST NOT edit or regenerate them. A conflict is a BLOCKER requiring planning revision outside the Phase.

## Test governance

A Phase report MUST state:

- test files added;
- pre-existing test files modified;
- skip count before/after;
- xfail count before/after;
- golden manifest SHA-256;
- exact command return codes.

## Cross-Phase regression

Every Phase runs the complete test suite. Later Phases MUST preserve all earlier contract/golden tests. A later Phase may add new tests but MUST NOT rewrite earlier expected values.
