# Counter-review — SEP-3 research-statistics review

Counter-reviewer: Codex, 2026-08-24

Reviewed Claude branch:
`origin/user/claude/review-sep3-resstats-20260823` at exact pushed head
`ea6448425ba1508503081e6eb35e30ee4a55f894`. The remote head was checked
twice and remained stable. Its merge-base with the exact submitted Codex head
`0de7920d0f2bcf2b2329600959a2208de4ea15c1` is that submitted head. The
complete ordered Claude range contains one commit:

1. `ea6448425ba1508503081e6eb35e30ee4a55f894` — Record the independent
   review of the SEP-3 research-statistics tranche.

The counter-review ran in a separate isolated worktree on local branch
`codex/counterreview-sep3-research-statistics-20260824`. The shared checkout
was not switched or modified.

## Verdict and commit disposition

**Accepted after correction.** Claude's sole review commit is accepted after
correction. Its central conclusions are correct: the fourth-dry-run evidence
reproduces; assistant display arithmetic is exactly equal to the research
helper over the reachable positive-count domain; the zero-count caller branch
bypasses the private helper; the assistant no longer imports the research-
owned service; and the merged `3391875` tree is byte-identical to submitted
head `0de7920` (`f2b0207b2cef6575c9991b1684e1250ffdbaa7ea`).

## P0–P3 ledger

| ID | Severity | Status | Finding and disposition |
|---|---:|---|---|
| CRSEP3S-001 | P3 | Resolved | Both services classified as product-owned still carried source-level ownership claims from their former classification: `data/operational_alerts.py` said provider-neutral and `data/research_statistics.py` said policy-neutral and shared across both products. Claude accepted the architecture reassignment but missed these contradictory source contracts. Correction `6341d6a` makes the docstrings assistant-owned and research-owned respectively, clarifies that the assistant may independently render equivalent arithmetic but cannot import the research helper, and adds a generalized manifest-driven guard over every product-owned service. Mutation restored the stale research docstring and failed with the exact path and both forbidden claims; restoration passed. |

No P0, P1, or P2 issue was found.

One wording qualification does not change the verdict: Claude grouped all
`n_tests <= 0` behavior as a stricter negative threshold. Negative counts do
produce that conservative value, but a direct zero call would divide by zero;
zero remains unreachable because `research_look_summary` explicitly bypasses
the helper when the stored count is zero. The production and ownership claims
remain correct.

## Independent reproduction

- Candidate `8cb47e1714ebea2e93ddd578801d2a953588bef0` reproduces **747** tracked
  paths with inventory SHA-256
  `b22d5c3450a5f00fcbfa035c151bea9cc4443e8211951d0be74bf5c37add5834`.
- Destinations reproduce as **503 trading assistant / 240 strategy research /
  4 shared contracts**, assigned exactly once.
- Test partitions remain **83 assistant / 70 research / 1 shared / 54
  integration** with the pinned ordered hashes.
- Eight dual-use data modules, 11 composition files, six Python crossing
  roots, four non-assistant operator-store importers, 54 integration tests,
  and pending governance/documentation ownership remain blockers.
- Status remains `fourth-dry-run-not-ready-for-physical-extraction`, with
  physical extraction false.
- Exact arithmetic matched for 60,000 reachable `(n, alpha)` combinations.
- Focused dry-run, entry-point, active-document, and research-look suites pass
  **117 tests** in 372.11 seconds after the new regression.

No provider, credential, licensed row, broker, operator database, installed
task, deployment, backtest, outcome, research look, evidence epoch, or
`paper-epoch-006` state was accessed or changed.

## Next authorized step

Under the owner's standing loop, this counter-review remains local-only and
must not be pushed as a standalone branch. Continue from its finalized tree on
one fresh `codex/` implementation branch, implement the next safe bounded
SEP-3 item, validate the combined series, and push that implementation branch
exactly once. Do not guess through an owner-level product destination or
physical topology decision.
