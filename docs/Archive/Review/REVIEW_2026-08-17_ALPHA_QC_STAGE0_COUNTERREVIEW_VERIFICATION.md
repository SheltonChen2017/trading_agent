# Independent verification — Stage 0 correction counter-review

Date: 2026-08-17
Reviewer: Codex
Reviewed remote: `origin/user/claude/alpha-qc-fable-cr-verify-20260817`
Exact reviewed head: `9a7e9fc70471d70114831d2209551dd330cf3e4f`
Exact base: `9e4580334f0e0a6a072c650a3b19c89d8492ea8a`
Ordered range: `c2f594e`, `4ee9419`, `9a7e9fc`
Merged topology: PR #244, merge `b6f577e078750634c6599d1b8987f0cb35d9de6c`
Verification branch: `codex/review-alpha-qc-fable-cr2-20260817`

Disposition: **accepted after one P3 regression-sensitivity correction. No
result-changing defect was found. The QuantConnect algorithm tree at PR #244
is accepted for the owner's next frozen run after the owner chooses Stage 0
or Stage 1.**

## 1. Snapshot and topology

The review began only after the exact Claude branch was pushed. Its merge
base with the correction branch is `9e45803`; the ordered three-commit range
above is complete. PR #244 later merged exact head `9a7e9fc` into `main` at
`b6f577e`. The merge tree and Claude head have the same tree object
`0fe65449a58aaca1363fc9d4783ee89ccf1cfbcc`, so the merged source is exactly
the reviewed source. No local-only or uncommitted Claude work was reviewed.

## 2. Commit-by-commit dispositions

| Commit | Disposition |
|---|---|
| `c2f594e` | **Accepted after test hardening.** FCR-001 correctly charges the drifted exit leg and refuses an insolvent denominator; independent arithmetic and an exact mutation confirmed that its behavioral test is load-bearing. FCR-002 correctly ports the strict industry-code guard and stale-code eviction into Stage 1's currently unused copied state. Its helper-only test, however, did not prove the live `_fine` call site used that helper; FCRV-001 closes that P3 sensitivity gap without changing product behavior. |
| `4ee9419` | **Accepted after current-state documentation correction.** It accurately records the counter-review, reproductions, mutations, validation, result validity, and unchanged look counts. Its then-current topology and remaining Codex-acknowledgement gate are superseded by PR #244 and this verification. |
| `9a7e9fc` | **Accepted after current-state handoff correction.** Its section 7q is an accurate historical account. The topology, gate, and next-step text are advanced by this review rather than rewriting the original commit. |
| `b6f577e` | **Accepted as merge topology.** PR #244's merge tree is byte-identical to exact reviewed Claude head `9a7e9fc`; it introduces no independent content. |

## 3. Verification of the two Claude findings

### FCR-001 — drifted exit leg

For a 50/50 long-short book where both legs win 10%, the post-return gross
weight is `10/11`; round-trip turnover is therefore
`0.5 + 0.5 * 10/11 = 0.954545...`, not 1.0. When both legs lose 10%, it is
`0.5 + 0.5 * 10/9 = 1.055555...`. Claude's correction produces those values
and refuses a wiped-out denominator. Replacing the exit with the old flat
liquidation made the new FCR-001 test fail, then restoring it returned green.

### FCR-002 — Stage 1 industry ingestion

The Stage 1 industry map is written but not consumed by a current Stage 1
factor, so this correction cannot alter a current result. The port is still
correct preventive maintenance: missing or malformed Morningstar industry
codes are not stored as a fictitious industry zero and stale valid codes are
evicted.

## 4. Issue ledger

| ID | Priority | Status | Finding | Resolution |
|---|---:|---|---|---|
| FCRV-001 | P3 | **Closed** | The Stage 1 extension of `test_missing_industry_is_not_turned_into_a_fake_peer_group` exercised only `_valid_industry_code`. Reverting the live `_fine` call site to `int(code or 0)` while leaving the helper untouched therefore survived that test. | Added a three-algorithm AST regression that requires each live `_fine` path to call `_valid_industry_code`, forbids direct conversion of `morningstar_industry_code`, and requires stale-map eviction. The exact Stage 1 call-site mutation fails this guard; restored source passes. |
| FCRV-002 | P3 | **Closed** | Canonical records still described `main` at PR #243, the Claude branch as awaiting merge, and Codex acknowledgement as outstanding. | Recorded PR #244 at `b6f577e`, the exact tree identity, this verification, and the now-satisfied code-review gate. |

No open P0, P1, P2, or P3 finding remains in this reviewed range.

## 5. Validation

- Focused QC/Stage 1/LEAN/client/document gate: **242 passed**.
- Corrected QC battery file: **41 passed**.
- Full repository suite: **4,208 passed / 0 failed / 25 known dependency
  warnings in 631.32 seconds**.
- Compilation including `research/`: **clean**.
- Active-document gate: **31 passed**. All **131 tracked Markdown files** have
  zero broken relative links; all **5 tracked docs/assistant JSON files**
  parse. Diff, status, staged-content, and ordered-commit checks are clean.
- No QuantConnect authentication, upload, compile, cloud run, or result read;
  no broker, database, scheduler, epoch, or trading-state access; no new
  research look. The lifetime alpha-cell floor remains 428 and the run ledger
  remains five.

## 6. QC launch disposition

The reviewed algorithm code merged in PR #244 needs no further correction.
This review closes the requested Codex acknowledgement of FCR-001/002. The
only remaining research decision is the owner's stage order: finish frozen
Stage 0 first or run the already-frozen Stage 1 replication first. Whichever
is chosen must use the exact PR #244 algorithm source (or a later tree proven
identical for those source files), preserve the frozen contract, and append
the execution as R-005 or later with full project, compile, backtest, source,
log/result-hash, window, and before/after look-count evidence.
