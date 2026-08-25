# Counter-review — SEP-3 market-analytics ownership review

Counter-reviewer: Codex, 2026-08-25

Reviewed Claude branch:
`origin/user/claude/review-sep3-marketanalytics-20260825` at exact pushed head
`8f0ec2d8345ecf093ca02a8d2e59331de4a8c551`. The remote head was checked
twice and remained stable. Its merge-base with exact submitted Codex head
`8db2251f31a338f6b205082dba1219af38fd167e` is that submitted head. The
complete ordered Claude range contains one commit:

1. `8f0ec2d8345ecf093ca02a8d2e59331de4a8c551` — Record the independent
   review of the SEP-3 market-analytics tranche.

The counter-review ran in a separate isolated worktree on local branch
`codex/counterreview-sep3-marketanalytics-20260825`. The shared checkout was
not switched or modified.

## Verdict and commit disposition

**Accepted.** Claude's sole review commit is accepted with no issue found. Its
review-state advance is supported by the candidate-specific review record,
and its substantive conclusions reproduce independently: assistant production
uses private market-display calculations, the research-owned root module has
no assistant-owned production importer, the equivalence guard detects minute
arithmetic drift, and the sixth candidate remains a valid dry run that refuses
physical extraction.

## P0–P3 ledger

| Priority | Open | Resolved | Disposition |
|---|---:|---:|---|
| P0 | 0 | 0 | No issue found. |
| P1 | 0 | 0 | No issue found. |
| P2 | 0 | 0 | No issue found. |
| P3 | 0 | 0 | No issue found. |

## Independent reproduction

- The implementation range `1680f6e..8db2251` contains the ten commits Claude
  listed, in the same order. Merged `origin/main` at `38def143` has no tree
  difference from submitted head `8db2251`.
- Candidate `c4c6ed897be3c8cf7d11f345523f43ea6647e316` reproduces **752** tracked
  paths with inventory SHA-256
  `dbf460e5def6a06f8d65b4d09029b7a7b05739f8de05653bb06e0f4ce8fa7460`.
- Destinations reproduce as **502 trading assistant / 246 strategy research /
  4 shared contracts**, assigned exactly once.
- Test partitions reproduce as **84 assistant / 75 research / 1 shared / 42
  integration / 6 governance** with the manifest-pinned ordered hashes.
- The validator returns
  `valid-sixth-dry-run-not-ready-for-physical-extraction`, accepted review
  status, eight dual-use `data.*` modules, `config` as the sole stranded
  top-level module, 11 composition files, six Python crossing roots, four
  non-assistant operator-store importers, and physical authorization false.
- The focused boundary, dry-run, entry-point, and active-document suites pass
  **113 tests** in 451.94 seconds. An earlier attempt passed 95 tests but had
  18 setup errors solely because the isolated pytest temporary parent did not
  yet exist; after creating that ignored parent, the unchanged suite passed.
- The three explicit top-level dangerous-direction checks pass: deleting the
  stranded declaration, falsifying importer sides, or restoring an assistant
  import of research-owned market analytics is refused.
- A verified `1e-9` relative drift in assistant trailing volatility makes the
  cross-implementation equivalence test fail on the changed value. Restoring
  the exact implementation returns the test green, and the restored blob hash
  matches `HEAD`.

No provider, credential, licensed row, broker, operator database, installed
task, deployment, backtest, outcome, research look, evidence epoch, or
`paper-epoch-006` state was accessed or changed.

## Next authorized step

Under the owner's standing loop, this counter-review remains local-only and
must not be pushed as a standalone branch. Continue from its finalized tree on
one fresh `codex/` implementation branch. The earliest code-determined
ownership reduction is `data.runtime_identity`: the extraction manifest
already sends it to strategy research, while the assistant reaches it only
through `assistant.runtime_identity`. Replace that facade with an assistant-
private, behavior-equivalent implementation, keep research scripts on the
research-owned definition, and regression-pin both behaviors and the removed
product-to-product direction. This does not choose product policy, move a
runtime path or database, or grow the tiny shared package.
