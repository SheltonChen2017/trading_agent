# Independent review: QuantConnect Stage 0 nine-run battery completion

Status: **conditionally accepted** for Stage 0 analyser execution.
Prepared: 2026-08-18. Reviewer: Cursor Grok 4.6.
Frozen analysers were **not** run on the nine PENDING_REVIEW logs. No
Sharpe, IC, p-value, or net-return statistic was observed.

## 1. Snapshot

| Item | Value |
|---|---|
| Requested range | `81db126..de1beac` (27 commits) |
| Base | `81db126340818fe2c2c9efa16c77af8f1d37568f` (last independently reviewed launch-round head) |
| Review head | `de1beac16930690cda0f23dbe6f584e99600ac66` |
| Review branch (local only, not pushed) | `user/cursor/review-qc-stage0-battery-20260818` |
| `origin/main` at review start | `28e4c020c75ea6eb7dcacb92b9a816cee018f7b0` (PR #248) |
| PR #248 second parent | `32998e5`, **not** `de1beac` |
| Worktree | clean at review start |

`origin/main` is a merge of `a9d253b` and `32998e5`. Trees differ from
`de1beac` only in `docs/SESSION_HANDOFF.md` (the four-line owner deferral
that this review now supersedes). See S0R-006.

Every commit in `git log --reverse --oneline 81db126..de1beac` received an
explicit disposition below. The combined tip was not used as a substitute.

Focused validation on `de1beac` (synthetic fixtures only):

```text
108 passed in 11.14s
tests/test_alpha_battery_monthly_sim.py
tests/test_qc_stage0_runner.py
tests/test_alpha_battery_short_emitter.py
tests/test_qc_alpha_battery.py
tests/test_universe_benchmark_sim.py
tests/test_alpha_battery_research.py
tests/test_alpha_stage1_replications.py
```

Full suite, `compileall`, and `git diff --check` were not re-run in this
findings-only session. The implementer recorded 4,239 passed / 25 known
warnings on the final battery tree; that figure is not independently
reproduced here.

## 2. Verdict

**Accept the seven Stage 0 product/test commits** (`df59519`, `49e8160`,
`d305ea0`, `46221db`, `075e982`, `5b5184a`, `39b3b89`) and the twenty
record commits. The nine PENDING_REVIEW cloud logs may be analysed **once**
by the frozen analysers after owner authorization. They must not be
rehabilitated, overwritten, or selectively dropped.

**Do not launch Stage 1** until S0R-001 and S0R-002 are closed. Those are
the same two defect classes this range just finished chasing through the
Stage 0 algorithms.

No P0. No P1. Two open P2. Five open P3.

## 3. Contracts checked

1. **Turnover is a cost, never a result-row gate** on the Stage 0 monthly,
   short, and universe-benchmark algorithms and on
   `scripts/run_alpha_battery_20260815.py`. Unavailable turnover is an empty
   field (decimal) or u16 65535 (packed v2 only); analysis charges 1.0
   one-way and discloses `unavailable_turnover_periods`. A fourth and fifth
   live copy remain in Stage 1 (S0R-001, S0R-002). A sixth remains in
   `scripts/run_alpha_universes_20260816.py` (S0R-004).
2. **Packed v1 compatibility:**
   `test_v1_layout_keeps_65535_as_a_real_turnover_value` requires 65535 →
   6.5535. The parser applies the sentinel only when `layout == 2`.
3. **Underfill is recorded** on `universe_benchmark.py` when
   `len(outcomes) >= MIN_NAMES` (30). Five-field BROW carries priced and
   entered. Parser accepts legacy four-field (`entered = priced`) and
   refuses `priced > entered`. Stage 1 benchmark still requires a full
   book (S0R-002).
4. **Fail-closed packing:** unrepresentable real turnover (`scaled > 65534`)
   emits `INCOMPLETE|turnover_out_of_range` and no B64BLOCK. Empty /
   out-of-range masks and trailing / truncated payload bytes raise
   `InvalidLog` / `TruncatedLog`. Pinned.
5. **Ledger:** R-001 through R-022 are retained. Invalidated and stale
   entries were not deleted. Run-level count ends at 23 on R-022. The nine
   completers are R-009/011/012, R-014/015/016, R-022/020/021, all
   PENDING_REVIEW with project, compile, backtest, source SHA-256, log line
   count, and file sha256. No frozen-analyser output appears in the ledger.
6. **No sneaked analyser result.** Parser round-trip counts, DATES
   declarations, and unavailable-turnover *counts* are structural. R-022's
   pairwise raw-return identity check is the only numeric comparison of
   series values (S0R-007).

## 4. Per-commit dispositions

### Production / test (7)

| Commit | Disposition | Notes |
|---|---|---|
| `df59519` Close QCS0CR-001/002 | **Accepted.** No issue found. | Tests-only pin of the previous counter-review. Production already passes `current_commit(require_clean=True)` from `scripts/run_qc_stage0.py:_git_commit_of`. The added February-session assertion would fail if ordinary days kept the previous month's industry snapshot. |
| `49e8160` Recoverable turnover; SPECMETA ragged dates | **Accepted.** Intermediate. | `_rebalance_turnover` from stored entry prices; retained stale-book subscriptions; SPECMETA per-spec counts; parser accepts ragged dates only when SPECMETA inventory is complete, otherwise keeps the old every-spec-every-date TruncatedLog. The bind still `continue`d on `None` turnover; that remaining gate is removed in `d305ea0`. |
| `d305ea0` Turnover never gates a result row | **Accepted.** S0R-003 (P3) in the parser it introduced. | Removes the monthly bind-gate. Empty turnover fields. Analyser `fillna(1.0)` plus disclosure. Local `long_short_returns` keeps the return and omits that month from the turnover index; `net_of_costs` charge is magnitude-pinned. |
| `46221db` Masked packed layout, v2 sentinel | **Accepted.** No issue found. | Presence mask; 65535 reserved in v2 only; settle no longer gates on turnover; oversized real turnover refuses the run; parser walks both layouts and rejects empty/high masks and trailing bytes. |
| `075e982` Empty results must fail | **Accepted.** No issue found. | Closes the vacuous pass where reinstating the settle gate emptied `results` and skipped per-row assertions. |
| `5b5184a` Benchmark bind never gates on turnover | **Accepted.** No issue found. | Third Stage 0 copy of R-010. Empty BROW turnover; analyser charges 1.0 and discloses. CAGR 10bps-vs-0bps test pins the charge, unlike the alpha-analyser tests (S0R-008). |
| `39b3b89` Benchmark records underfill | **Accepted.** No issue found. | Emits priced subset at `MIN_NAMES`; five-field BROW; legacy four-field accepted; `priced > entered` refused. |

### Documentation / records (20)

All twenty are **accepted**. None rehabilitates an invalidated run or
records a frozen-analyser statistic. Status changes are STALE / INVALIDATED
/ INCONCLUSIVE / PENDING_REVIEW / REFUSED as required by the ledger
vocabulary.

| Commit | Disposition |
|---|---|
| `1bb1a7a` Launch-round counter-review record | Accepted. No issue found. |
| `75ad8dc` Handoff after launch-round counter-review | Accepted. No issue found. |
| `100bd0f` Append R-007 UNANALYSED | Accepted. Inserted after the launch narrative; does not rewrite R-005/R-006 identity. |
| `05929a5` R-007 STALE / R-008 INVALIDATED | Accepted. Status update; identities retained. |
| `8957e32` Append R-009 PENDING_REVIEW | Accepted. Parser round-trip only. |
| `e2ed7eb` Ledger R-010 INVALIDATED and fix round | Accepted. |
| `7b588d4` Append R-011 PENDING_REVIEW | Accepted. Full identity present. |
| `f470ee6` Append R-012 PENDING_REVIEW | Accepted. DNS re-attach recorded honestly. |
| `1700bc7` Append R-013 REFUSED | Accepted. Failure ledgered before the packed-layout fix. |
| `c9d8a4f` Append R-014 PENDING_REVIEW | Accepted. |
| `802c436` Append R-015 PENDING_REVIEW | Accepted. |
| `966d12f` Append R-016 PENDING_REVIEW | Accepted. |
| `9847965` Append R-017 INVALIDATED | Accepted. Failure ledgered before the benchmark bind fix. |
| `6d3c000` Append R-018 PENDING_REVIEW | Accepted. Later marked STALE by `b3e1979`, not deleted. |
| `12a1ced` Append R-019 INCONCLUSIVE | Accepted. Correct vocabulary for a selectively calm baseline sample. |
| `cd21495` Append R-020 PENDING_REVIEW | Accepted. |
| `01ce8f1` Append R-021 PENDING_REVIEW | Accepted. |
| `b3e1979` Append R-022 PENDING_REVIEW, R-018 STALE | Accepted. S0R-007 (P3) in the replication-check wording. |
| `32998e5` Handoff and action-plan completion record | Accepted. Structural completion, review still gated. |
| `de1beac` Owner deferral until Codex tokens | Accepted. Superseded by this review. Missing from `origin/main` (S0R-006). |

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| S0R-001 | P2 | Open | pre-existing; unfixed by `d305ea0` | `research/lean/alpha_stage1_replications.py:444-445` | Bind still `continue`s when any construction's `_rebalance_turnover` returns `None`. Previous weights are not replaced, so a zombie name kills later cohorts the same way R-010 killed monthly B_core. | Source: `if any(value is None for value in turns): continue` immediately above the `previous_weights` update. Same shape as monthly.py before `d305ea0`. No Stage 1 test mentions this gate. | The review contract was to confirm no fourth sibling of the three Stage 0 copies. Stage 1 is the next frozen QC stage and uses overlapping 21-session cohorts, so the same silent die-off will consume a counted look. | Pending: port the d305ea0 contract (bind always; emit empty turnover; analyser charges 1.0). | Not mutated this session. Confirmed by source. Focused Stage 1 tests (108-file run included `test_alpha_stage1_replications.py`) do not cover this path. |
| S0R-002 | P2 | Open | pre-existing; unfixed by `5b5184a`/`39b3b89` | `research/lean/alpha_stage1_benchmark.py:173-178,204-210,228-232` | Three surviving copies of defects this range just closed: (1) bind `return`s if any prior name is unpriceable, then again if `_drift_turnover` is `None`; (2) settle requires `len(outcomes) == len(cohort["entry"])`; (3) `on_end` still emits four-field BROW and `round(turnover, 4)` with no empty-field path. `scripts/analyse_qc_alpha_stage1.py:129-133` still does `matched["turnover"].mean()` and subtracts without `fillna(1.0)`. | Source inspection of those line ranges. Compare `universe_benchmark.py` after `39b3b89`. | Stage 1 benchmark is the cadence-matched baseline for REP-H52/REP-IDV. Dropping underfilled months recreates R-019's selectively calm sample. A turnover-gated bind recreates R-017. | Pending: port both Stage 0 benchmark contracts, including five-field BROW and analyser disclosure. | Confirmed by source. |
| S0R-003 | P3 | Open | `d305ea0`, `5b5184a` | `scripts/analyse_qc_alpha_battery.py:233-235,291-297`; `scripts/analyse_qc_benchmark.py:67-71` | Comment says a *present* turnover must be finite. Implementation does `pd.to_numeric(...).dropna()` *before* the finite check, so a literal `nan`/`inf` token becomes declared unavailability and is charged 1.0 instead of `InvalidLog`. Packed v2 cannot represent NaN (u16). Decimal ROW and BROW can. | `float(turn_ls) if turn_ls else None` plus `dropna()`; `"nan"` is truthy. Existing `test_parser_refuses_non_finite_results_or_negative_turnover` injects `nan` into the **return** field, not turnover. | Fail-closed logs should refuse corruption rather than relabel it as the new unavailability channel. Does not change the nine PENDING_REVIEW logs, which emit empty fields or finite numbers. | Pending: treat non-finite *present* turnover as InvalidLog; keep only empty/`None` as unavailability. Pin with a ROW/BROW `nan` case. | Confirmed by source. Parser was not executed on a crafted log (review instruction). |
| S0R-004 | P3 | Open | unfixed sibling of `d305ea0` | `scripts/run_alpha_universes_20260816.py:201-206` | After recording the month's return, `if drifted is None: continue` skips turnover **and** skips `previous = weights`. A wipeout therefore never heals: later months keep returns against a permanently unpriceable prior book. | Source. `test_universe_portfolio_charges_drift_not_target_to_target_turnover` covers the happy path only. Contrast `test_unpriceable_prior_book_never_drops_the_months_return`, which pins the 20260815 runner. | Same local-battery class `d305ea0` claimed to close. Does not affect QC Stage 0 logs. | Pending: match `long_short_returns` (keep return, omit turnover, update previous). | Confirmed by source. |
| S0R-005 | P3 | Open | leftover from `49e8160` after `d305ea0` | `research/lean/alpha_battery_monthly.py:519-527` | `_rebalance_turnover` docstring still describes the recoverable-retry contract ("a month whose turnover refuses simply retries next month"). The bind no longer retries; it records unavailability and replaces the book. | Docstring vs `_bind_staged_entry` after `d305ea0`. | A later reader will re-implement the R-010 gate thinking the comment is the contract. | Pending: rewrite the docstring to the never-gate contract. | Confirmed by source. |
| S0R-006 | P3 | Open | merge topology | `origin/main` `28e4c02` vs `de1beac` | PR #248 merged `32998e5`, not `de1beac`. Main lacks the four-line owner-deferral note. Trees otherwise match. | `git rev-parse 28e4c02^2` = `32998e5`; `git diff de1beac 28e4c02` is `docs/SESSION_HANDOFF.md` only. | Cross-computer handoff on `main` does not record the deferral (now superseded). Fast-forward or cherry-pick if that sentence should live on main. | Pending owner decision. This review supersedes the deferral. | `git merge-base --is-ancestor de1beac origin/main` is false. |
| S0R-007 | P3 | Open | `b3e1979` | `docs/Archive/Research/alpha-result.md` R-022 | The entry reports max absolute return difference **0.0** versus R-018 on 149 shared months, then says "Parsing only; no statistic observed." That comparison inspects return values outside the frozen analyser. It is not IC/Sharpe/p and does not sneak a family-gate result. | Ledger text at R-022. | Keep the identity check if useful, but do not call it "no statistic." Do not treat 0.0 as analyser output. | Pending wording. | Confirmed by reading the ledger. Returns themselves were not re-computed here. |
| S0R-008 | P3 | Open | `d305ea0` tests | `tests/test_alpha_battery_monthly_sim.py:340-345`; `tests/test_alpha_battery_short_emitter.py:132-137` | Alpha-analyser tests only assert `unavailable_turnover_periods >= 1`. A mutation `fillna(1.0)` → `fillna(0.0)` would still pass them. The benchmark analyser test compares 10bps vs 0bps CAGR and would catch it; the local `net_of_costs` test already pins the 1.0 charge. | Contrast `test_benchmark_analyser_charges_full_turnover_for_unavailable_months` and `test_unpriceable_prior_book_never_drops_the_months_return`. | Same vacuous-pass class `075e982` closed for settle emission. Production fillna(1.0) is correct. | Pending: pin net 10bps vs 0bps (or the charged delta) on a monthly/short synthetic log. | Confirmed by reading tests. Not mutated this session. |

## 6. Generalized-instance search

Search: `if any(value is None for value in turns)`, `if turnover is None`,
`if drifted is None`, `_drift_turnover` / `_round_trip_turnover` call sites
under `research/lean/` and `scripts/`.

| Location | After this range |
|---|---|
| `alpha_battery_monthly.py` bind | Fixed `d305ea0` |
| `alpha_battery_short.py` settle | Fixed `46221db` |
| `universe_benchmark.py` bind | Fixed `5b5184a` |
| `universe_benchmark.py` settle full-book | Fixed `39b3b89` |
| `run_alpha_battery_20260815.py` `long_short_returns` | Fixed `d305ea0` |
| `alpha_stage1_replications.py` bind | **Unfixed (S0R-001)** |
| `alpha_stage1_benchmark.py` bind + settle + emit | **Unfixed (S0R-002)** |
| `run_alpha_universes_20260816.py` `_portfolio` | **Unfixed (S0R-004)** |
| `analyse_qc_alpha_stage1.py` net costs | Still assumes finite present turnover |

No seventh LEAN algorithm copy was found. Assistant/execution/risk paths
do not share this state machine.

## 7. What this review does not authorize

- Running `scripts/analyse_qc_alpha_battery.py` or
  `scripts/analyse_qc_benchmark.py` on the nine logs (owner must authorize
  that single analyser pass after accepting this review).
- Upgrading PENDING_REVIEW to VALID before that pass and a records commit.
- Stage 1 QC execution.
- Deployment, epoch roll, operator-database mutation, paper orders, or
  live trading.

## 8. Recommended next step

1. Owner accepts this review for Stage 0 only.
2. Port S0R-001/S0R-002 before any Stage 1 compile, or explicitly defer
   Stage 1 with those items open.
3. Optionally close P3 items on a records/test-hardening commit.
4. Then run the frozen analysers **once**, with full run identities, and
   append results without rewriting R-009 through R-022.
