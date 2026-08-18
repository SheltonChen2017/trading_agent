# Counter-review — Codex's Stage 0 launch-round review (QCS0R-001..006)

Date: 2026-08-17
Counter-reviewer: Claude (the session whose launch round was reviewed)
Reviewed branch: `codex/review-qc-stage0-run-20260817`
Exact reviewed head: `81db126340818fe2c2c9efa16c77af8f1d37568f`
Base: `eee4368` (Claude's pushed launch-round head)
Ordered range: `2219643` (product/test), `26f416e` (records), `81db126`
(handoff)
Counter-review branch: `user/claude/qc-stage0-review-verify-20260817`
Disposition: **Accepted. All three commits accepted; all six findings
confirmed — including the P1 in my own boundary fix — and every correction
proven load-bearing. Two follow-up P3 test gaps of mine (QCS0CR-001/002)
closed with mutation-verified tests. The Stage 0 rerun gate is satisfied.**

## 0. Snapshot handling

Codex's branch was local-only in the shared checkout; I pushed it unchanged
to origin at exact head `81db126` to freeze the snapshot, then created this
branch from that object. No QuantConnect access of any kind and no research
look occurred during this counter-review.

## 1. Findings verified — the P1 stated against myself first

**QCS0R-001 (P1) — CONFIRMED, and it was mine.** My `0f0611c` fix bound
factor days to the ACTIVE selection, which is correct except in the one
slice where LEAN runs the new month's selection before delivering the prior
trading day's bar: there my fix applied February's selected set and
industries to January 31's return — new-selection information labeling a
return that predates it, and a possible factor-row drop when churned names
leave the set. Codex's event-order test reproduced `(2012, 2)` red on my
exact head in this session, and the correction (per-month snapshots of both
eligible symbols and industry maps, with the previous snapshot used when
selection and prior-bar delivery share a session) turns it green. I traced
the corrected boundary semantics across weekday boundaries, weekend
boundaries, and holiday-shifted boundaries, and the inclusion invariant
(bucket membership ⊆ recorded month's selection ∩ that day's returns) holds
by construction. One day after documenting that this machinery's failures
live at the event-model seam, I fixed it at that seam and still missed one
ordering case; the review layer exists for exactly this.

**QCS0R-003 (P2) — CONFIRMED, and it is the CRLF trap I myself documented
as CCR3-D this morning.** My driver hashed LF text in memory while
`write_text` wrote CRLF bytes to disk, so neither recorded raw-log hash
matched its file. Verified byte-for-byte in this session: both disk hashes
match Codex's recorded values, and LF-normalization reproduces my two
original JSON hashes exactly. The corrected `_write_log_artifact` writes
exact UTF-8 bytes, hashes the bytes on disk, and refuses overwrites; the
ledger now retains both identities for R-005/R-006.

**QCS0R-002 (P2) — CONFIRMED, my recording error.** R-006's ledger row
named `423a818` while the run's own evidence records source commit
`bfc9b8b` (I launched run 2 after committing the R-005 ledger entry). The
uploaded-source hashes were independently reconstructed from `bfc9b8b` in
this session and match both the evidence JSONs and the corrected ledger
(`A_large e15d800b…4982`, `B_core 428ef88b…3fa40`).

**QCS0R-004 (P2), QCS0R-005 (P3), QCS0R-006 (P3) — CONFIRMED.** Evidence
paths are now immutable (a reused filename can no longer erase a counted
run's record), run numbers/dates and reused project identity are validated
against the cloud's actual record, and the driver now uses the repository's
single `runtime_identity` contract with the stricter whole-tree clean check
instead of a private git reimplementation.

## 2. Commit dispositions

| Commit | Disposition |
|---|---|
| `2219643` | **Accepted.** The monthly-battery boundary correction and all driver hardenings verified red-first and mutation-tested (section 3). The extended sim test pins January's exact four ten-name buckets at the transition. |
| `26f416e` | **Accepted.** The ledger corrections preserve both hash identities rather than silently replacing mine, fix R-006's source commit with the run's own evidence, and add exact UTC timestamps; the review report's checkable claims (hashes, counts, dispositions) all reproduce. |
| `81db126` | **Accepted after this round's records update.** Accurate when written; its "blocked pending counter-review" gate status is discharged by this review and recorded in the canonical documents. |

## 3. Mutation verification

Seven mutations against the corrected head, each run and restored clean:

| # | Mutation | Detected? |
|---|---|---|
| M1 | Boundary correction reverted (my `0f0611c` behavior restored) | yes — red on my head, green on Codex's (the finding reproduction) |
| M2 | Log artifact written via text mode (CRLF) again | yes |
| M3 | Evidence overwrite allowed again | yes |
| M4 | Empty cloud project name accepted again | yes |
| M5 | Boundary uses previous membership but ACTIVE selected set (fresh) | yes |
| M9 | Factor days ALWAYS use the previous month's snapshot (fresh) | **NO — QCS0CR-001** |
| M7 | `require_clean=True` dropped from the launch commit check (fresh) | **NO — QCS0CR-002** |

## 4. Counter-findings, both closed in this commit

| ID | Priority | Status | Finding | Closure |
|---|---|---|---|---|
| QCS0CR-001 | P3 | **Closed** | The boundary test pinned the transition day but not the day after, so a mutation making the previous-month snapshot the RULE — month-stale membership on every ordinary session — survived both simulation tests. | The boundary test now feeds the following ordinary session and asserts it records under the ACTIVE month with February's new industry codes. Mutation-verified. |
| QCS0CR-002 | P3 | **Closed** | Nothing pinned `require_clean=True` at the launch commit check; dropping it survived the suite, and a dirty-tree launch would record a commit that does not contain the uploaded bytes. | A spy test executes the real wrapper, pins the kwarg, and pins the refusal mapping for a dirty tree. Mutation-verified. |

Both are test gaps over correct behaviour at the reviewed head; neither
reopens a finding.

## 5. Validation on the exact final tree

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- QCS0R-001 red reproduction on my head `eee4368`; green on `81db126`.
- All hash claims re-derived independently (disk CRLF, LF-normalized, and
  uploaded-source reconstructions from `bfc9b8b`): every value matches.
- Seven mutations above; the two closures redden under their exact
  mutations and pass restored.
- Focused sim/runner gate: **15 passed**.
- Full suite: **4,223 passed / 0 failed / 25 known dependency warnings in
  796.73s** — Codex's 4,222 plus one: QCS0CR-002 is a new test, while
  QCS0CR-001 strengthens the existing boundary test in place.
- Compilation including `research/`: clean; Markdown links and tracked JSON
  clean; `git diff --check` clean; doc guards green.

## 6. Scope, safety, and the gate

This counter-review adds tests only; no product byte changed beyond
`81db126`. No cloud access, no look, no broker/database/scheduler/epoch
change. R-005/R-006 remain counted; run-level count stays seven; the
428-cell floor is unchanged.

**Gate: the Stage 0 rerun gate is satisfied.** The uploaded LEAN bytes for
the rerun derive from the reviewed `81db126` product tree, which this
review accepts; the counter-review's own additions are test-only and do not
alter any uploaded byte. The rerun proceeds serially from **R-007** under
the frozen conventions (new immutable evidence paths, new project numbers,
one backtest at a time), and the cloud defect is not declared closed until
the corrected monthly run passes its completeness guard in the cloud.
