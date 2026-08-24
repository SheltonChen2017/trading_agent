# Counter-review — SEP-3 support-test ownership review

Counter-reviewer: Codex, 2026-08-24

Reviewed Claude branch:
`origin/user/claude/review-sep3-supporttest-20260824` at exact pushed head
`1680f6e512b7bcc828e86036d0d307ab5a1c5271`. The remote head was checked
twice and remained stable. Its merge-base with the exact submitted Codex head
`ae0d563fff5b9348f21ddf711461c075b9e80587` is that submitted head. The
complete ordered Claude range contains one commit:

1. `1680f6e512b7bcc828e86036d0d307ab5a1c5271` — Record the independent
   review of the SEP-3 support-test tranche.

The counter-review ran in a separate isolated worktree on local branch
`codex/counterreview-sep3-support-tests-20260824`. The shared checkout was
not switched or modified.

## Verdict and commit disposition

**Accepted after correction.** Claude's sole review commit is accepted after
correction. Its central support-test conclusions reproduce: the twelve exact
overrides are limited to statically product-import-free files; the split is
three assistant, three research, and six governance tests; the integration
partition falls from 54 to 42; duplicate, stale, hidden-static-import, and
governance-to-research directions fail closed; and the fifth candidate remains
a valid dry run that does not authorize physical extraction.

## P0–P3 ledger

| ID | Severity | Status | Finding and disposition |
|---|---:|---|---|
| CRSEP3ST-001 | P2 | Resolved | The stranded-module proof covered assigned `data.*` modules only. The separate top-level partition sent `config.py` and `market_analytics.py` to the assistant even though exact candidate measurement finds importers on both product sides. Executing that partition would strand research or create the forbidden product-to-product dependency. Correction `aa2fe4f` generalizes assigned-module measurement, pins both top-level modules and their exact importer sides, and refuses missing or inaccurate declarations. Both guards were disabled in turn; the two dangerous-direction tests failed, then passed after restoration. |
| CRSEP3ST-002 | P3 | Resolved | Claude accepted the fifth candidate, but the active plan, separation plan, and manifest still said its independent review was pending. Correction `aa2fe4f` accepts only the supported review states and adds a candidate-specific review-record consistency guard; `cb0c7f8` synchronizes the active documents. A later candidate without its own accepted report naturally returns to pending. |

No P0 or P1 issue was found.

## Independent reproduction

- Candidate `df7eb48b5e17a769d6977d513cafab680f336b66` reproduces **749** tracked
  paths with inventory SHA-256
  `a5c57b9896d22faff9fe3b2bc32126e7ebc89245ce2433b44f69086dbde86797`.
- Destinations reproduce as **502 trading assistant / 243 strategy research /
  4 shared contracts**, assigned exactly once.
- Test partitions reproduce as **86 assistant / 73 research / 1 shared / 42
  integration / 6 governance** with their pinned ordered hashes.
- The twelve support-test overrides reproduce as three assistant, three
  research, and six governance files. They cannot conceal a measured static
  product import or name a missing/duplicate file.
- Eight dual-use data modules, two dual-use top-level modules, 11 composition
  files, six Python crossing roots, four non-assistant operator-store
  importers, 42 integration tests, and non-test governance/documentation
  ownership remain blockers.
- Status remains a valid fifth dry run, independently reviewed but not ready
  for physical extraction; authorization remains false.
- The original focused review suites passed **99 tests** in 307.58 seconds.
  The four new guards first failed on the uncorrected review tree, then passed
  after correction. Disabling the two top-level comparisons made both refusal
  tests fail. The corrected combined suites pass **103 tests** in 488.33
  seconds.

No provider, credential, licensed row, broker, operator database, installed
task, deployment, backtest, outcome, research look, evidence epoch, or
`paper-epoch-006` state was accessed or changed.

## Next authorized step

Under the owner's standing loop, this counter-review remains local-only and
must not be pushed as a standalone branch. Continue from its finalized tree on
one fresh `codex/` implementation branch. The earliest bounded code-determined
item is to remove the assistant's imports of research-owned
`market_analytics.py` with behavior-identical assistant-private calculations,
then reassign that root module to research. `config.py` remains the other
measured top-level blocker. Validate the combined series and push the
implementation branch exactly once.
