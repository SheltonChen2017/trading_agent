# Counter-review — Codex's alpha QC round 2 / full research audit

Date: 2026-08-17
Counter-reviewer: Claude
Reviewed range: `a37e73b..b4e9ee0` on
`origin/codex/review-alpha-qc-round2-20260817` (seven commits)
Merged into: `user/claude/alpha-qc-round-20260816` (fast-forward)
Disposition: **All thirteen findings confirmed. Corrections accepted.
Three test-coverage counter-findings raised (CR2-001..003), all closed in
this commit with mutation-verified tests. No product defect found in the
Codex head.**

## Method

Verification was behavioural, not by reading: seven independent mutations
were applied to the Codex head in an isolated worktree, chosen to be
different from the mutations Codex reported using, and the suite was run
after each. A finding's correction counts as verified only when a mutation
reintroducing the defect reddens a test.

| # | Mutation (reintroduced defect) | Target claim | Detected? |
|---|---|---|---|
| M1 | Stage 1 scores formed at the ENTRY close (`end_ago=0`) | AQR2-001 | **NO — CR2-001** |
| M2 | Market factor fabricates `0.0` and records the session on a thin day | AQR2-002 | **NO — CR2-002** |
| M3a | `self.fundamentals = {}` reintroduced in a LEAN file | AQR2-005 | yes |
| M3b | One legacy `self.SetCash(...)` PascalCase call | AQR2-005 | yes |
| M4 | Drift removed from Stage 1's own `_drift_turnover` | AQR2-007 family | **NO — CR2-003** |
| M5 | Local leave-one-out peers include the stock itself | AQR2-011 | yes |
| M6 | Residual-momentum fit window slides into the measurement period | AQR2-011 | yes |
| M7 | Local turnover drifts on CURRENT-period outcomes (lookahead) | AQR2-007 | yes |

Every mutation was reverted and `git status` confirmed clean before the
next; the algorithm source in this commit is byte-identical to `b4e9ee0`.

## Commit dispositions

| Commit | Disposition |
|---|---|
| `b143c60` | **Accepted.** The Stage 1 timing correction implements the frozen experiment: month-transition detection, features frozen at the prior close, entry at the current close, independently settled 21-session cohorts. M1 showed the *call-site* is not behaviourally pinned (CR2-001, closed here); the implementation itself is correct. |
| `fd007c8` | **Accepted.** Plan/ledger/action-plan updates match the code. The 452-cell lifetime gate (`428 + 24`) is arithmetically consistent with the frozen Stage 1 family. |
| `65e8bb0` | **Accepted.** The review record's claims were spot-checked against the tree: the 13-finding ledger, the disposition table covering all 35 commits of `006a9d5..a37e73b`, and the validation counts reproduce. |
| `2e2a77e` | **Accepted.** The Stage 1 implementation report addendum honestly reclassifies the "machinery is copied, deliberately" defence as implementation history rather than evidence of safety — which M4 independently confirms was the right call: the copy diverged from its tests, not from its source. |
| `855941a` | **Accepted.** The tree-wide correction verified on five axes: AST dialect/shadowing guards bind (M3a/M3b); bounded QC polling covers stall, timeout, and permanently-`None` progress with tests for each; the restored `docs/Archive/Research/alpha-result.md` retains all five run identities, statuses, and artifact SHA-256 values with a recoverability note; analyser identity refusals are tested; the benchmark's `_drift_turnover` copy differs textually from the monthly battery's but is semantically identical (the missing-outcome guard makes the `.get` fallbacks unreachable). |
| `1e2b631` | **Accepted.** The local joint 3-factor regression fits on a window that ends exactly where measurement begins (M6 reddens on overlap), peers are leave-one-out (M5 reddens on self-inclusion), and turnover uses previous-period outcomes only (M7 reddens on lookahead). |
| `b4e9ee0` | **Accepted.** The reorganization moves every review into `docs/Archive/Review/` and research/process/operations docs into their directories; link updates verified by the 124-file relative-link check and the updated active-document guard. The deletion of invalid generated results/JSON/logs is owner-directed housekeeping, and — the point that matters — every deleted artifact's identity and SHA-256 survives in the permanent ledger, so no look is erased. My own `a37e73b` ledger deletion was correctly rejected and reversed: the owner's slate-clearing instruction covered invalid artifacts, not the look-accounting record itself. |

## Counter-findings

All three are the same shape: **the pure helpers are behaviourally tested;
the algorithm's use of them was not.** This is AQR1-004's lesson applied
one seam higher — a correct helper under test proves nothing about the
call that feeds it.

| ID | Priority | Status | Finding | Closure |
|---|---|---|---|---|
| CR2-001 | P3 | **Closed in this commit** | Mutating `_form_and_bind` to score with `end_ago=0` — features formed on the entry close, a look-ahead-shaped timing defect — survived the entire suite. `test_month_end_score_uses_prior_close_and_next_session_entry` pins the helper, not the call. | AST test pinning `end_ago=1` at the call site. AST is justified here because LEAN cannot be imported locally, so no runtime assertion in this repository can observe the wiring; the arithmetic remains behaviourally tested. Mutation-verified. |
| CR2-002 | P3 | **Closed in this commit** | Mutating `_record_market_return` to append a fabricated `0.0` with the session recorded — precisely the AQR2-002 defect direction — survived the suite. The refusal test exercises `_aligned_observation_tail`, and the recorder's own test only asserts (via AST) that it does not call `_returns`. | Behavioural test executing the extracted method against a stub: no returns → no append; `MIN_NAMES - 1` names → no append; `MIN_NAMES` names → equal-weight mean bound to the exact session. Mutation-verified. |
| CR2-003 | P3 | **Closed in this commit** | The `_real()` test loader stops at `def _drift_turnover`, so Stage 1's own turnover copy is executed by no test; only the monthly battery's copy is pinned. Removing drift from Stage 1's copy reddened nothing. Source parity holds today (`stage1 == monthly` byte-identical), but parity is not a test. | Behavioural test executing Stage 1's own copy with the Method V2 §1.2 cases: the 15% drift-restoration charge, free flat-return re-entry, missing-outcome refusal, and the empty-book base case. Mutation-verified. |

Severity rationale: all three are test gaps over correct product behaviour
at the reviewed head, so none invalidates the audit or blocks the QC rerun;
they are P3 hygiene that would have let a future edit silently regress a
frozen contract.

## Remaining observations, not findings

- The benchmark's `_drift_turnover` textual divergence (noted under
  `855941a`) is worth eliminating in a future pass so the parity argument
  stays checkable, but it is semantically inert today.
- The round-2 rerun contract centres on Stage 1 and its benchmarks while
  plan §5 still requires Stage 0 battery completion. The stage ORDER for
  the next cloud runs is an owner decision recorded before launching, not
  a code question.

## Verification

- Focused suites on the Codex head before any change: 129 passed
  (research/QC/LEAN), matching the review's declared count.
- Full suite on unmodified head `b4e9ee0` in the repository `.venv`
  (Python 3.13.14): **4,189 passed / 0 failed / 25 known dependency
  warnings in 773.16s** — independently reproducing the review's declared
  final validation.
- Seven mutations above; per-mutation suite runs; three new tests each
  verified to redden under their exact mutation and pass on the restored
  tree.
- Full suite on the exact final counter-review tree: **4,192 passed / 0
  failed / 25 known dependency warnings in 727.62s** (the three closing
  tests account for the delta). Focused research/QC/document gate: 163
  passed. Repository-wide compilation including `research/` and
  `git diff --check`: clean.

## Disposition

Accepted in full and fast-forwarded into the long-lived alpha branch. With
this counter-review, the reviewed workflow's gate for the next QuantConnect
runs is satisfied. No historical result is rehabilitated; the lifetime
alpha-cell floor remains 428 and the run ledger remains five.
