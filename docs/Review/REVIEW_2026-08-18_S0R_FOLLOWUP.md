# Independent review: commits since `de1beac` (S0R follow-up through PR #254)

Status: **accepted** for the Stage 1 *code* gate. Prepared: 2026-08-18.
Reviewer: Cursor Grok 4.6. This is a new independent look at
`de1beac..07bb819`, not a rubber-stamp of the Claude hardening review
already on the tree.

Frozen analysers were **not** run on the nine Stage 0 logs. No new
Sharpe, IC, p-value, or net-return statistic was computed from them.
A-001 remains the single authorized observation. All executions below
used synthetic fixtures or the test suite.

## 1. Snapshot

| Item | Value |
|---|---|
| Requested range | `de1beac..07bb819` (20 commits) — everything since the previous Cursor/Grok review head |
| Base | `de1beac16930690cda0f23dbe6f584e99600ac66` |
| Review head | `07bb819c147afafce6444c1dcbdf530193ce4826` (`origin/main`, PR #254) |
| Review branch (local only, not pushed) | `user/cursor/review-s0r-followup-20260818` |
| `origin/main` at review start | `07bb819c147afafce6444c1dcbdf530193ce4826` |
| Worktree | clean; `HEAD` == `origin/main` |

Fetched before review. Every commit in
`git log --reverse --oneline de1beac..07bb819` is dispositioned below.
The combined tip was not used as a substitute.

Product vs records: **one product/test commit** (`602dc0b`). The other
nineteen are owner merges or documentation/ledger records.

Nine owner merges were checked as `merge^{tree} == second-parent^{tree}`
(exact). None hid a conflict-resolution product change.

Focused validation on `07bb819` (synthetic fixtures only):

```text
102 passed in 6.93s
tests/test_alpha_stage1_hardening.py
tests/test_qc_alpha_battery.py
tests/test_alpha_battery_research.py
tests/test_alpha_stage1_replications.py
tests/test_universe_benchmark_sim.py
tests/test_alpha_battery_monthly_sim.py
tests/test_alpha_battery_short_emitter.py
```

Two reverse mutations (restored afterwards):

- reinstating `if any(value is None for value in turns): continue` in
  `alpha_stage1_replications.py` →
  `test_replications_bind_survives_unpriceable_turnover` **RED**
  (`assert 0 == 1` on `len(cohorts)`);
- `fillna(1.0)` → `fillna(0.0)` in `analyse_qc_alpha_battery.py` →
  `test_alpha_analyser_charges_full_turnover_for_unavailable_months`
  **RED** (delta `0.0` vs `0.0001538…`).

Both tests **GREEN** after restore. `compileall` on the changed modules
clean. `git diff --check` clean.

Full suite, and SHA-256 re-hash of the three A-001 JSON artifacts, were
**not** reproduced here. The artifacts are not in this checkout. The
implementer/prior-reviewer figure of 4,246 passed / 0 failed / 25
warnings is not independently reproduced in this session.

## 2. Verdict

**Accept all twenty commits.** `602dc0b` genuinely closes S0R-001, 002,
003, 004, 005, and 008. S0R-006 closed by merge topology (`c9e7a69`).
S0R-007 closed by the A-001 append-only amendment (`8c9fdc8`).

**The Stage 1 code gate is cleared.** This review does **not** authorize
a Stage 1 QuantConnect launch. That remains a separate owner decision
weighing a 24-cell counted family against the A-001 nulls. The first
Stage 1 cloud run must still round-trip the frozen parsers before any
statistic is read: the stub harness exercises the real classes, not
LEAN's callback ordering.

No P0. No P1. No P2. One open P3 (ledger headings). One P3 closed
without a code change (VALID vs UNANALYSED sequencing).

A-001 is accepted as a **process record**, not as evidence of
stock-selection edge. The entry itself states that the six long-only
cells that cleared the frozen gross-mean-vs-zero test are beta-carrying
and that the equal-weight benchmarks would pass the same test.

## 3. Contracts checked

1. **Turnover is a cost, never a result-row bind gate** on Stage 1
   replications and Stage 1 benchmark, matching the Stage 0 monthly /
   short / universe-benchmark contract. Unavailable turnover emits as an
   empty field; analysis charges 1.0 one-way and discloses
   `unavailable_turnover_periods`.
2. **Underfill is recorded** on the Stage 1 benchmark when
   `len(outcomes) >= MIN_NAMES`; five-field BROW carries priced and
   entered. The Stage 1 analyser discloses `underfilled_months`.
3. **Present `nan` tokens are refused** on decimal ROW ic/turnover and
   BROW turnover (`_optional_finite` / `math.isfinite`). Empty remains
   declared unavailability. Packed v2 still cannot encode NaN.
4. **Local universes runner heals the book** after an unpriceable month:
   the return is kept, that month's turnover is omitted, `previous` is
   still replaced.
5. **Settle-side `any(symbol not in outcomes): continue`** on monthly,
   short, and Stage 1 replications is **not** a bind-gate sibling. It
   mutates no `previous_weights`; SPECMETA makes a dropped (spec, date)
   visible; substituting a priced-subset mean would change the portfolio.
   Left unchanged, correctly.
6. **Ledger:** A-001 is a new entry; R-001 through R-022 are retained.
   Run-level look count stays 23; lifetime cell floor stays 428. The
   nine completers were upgraded VALID before the analyser outputs
   existed (`2be903f` at 11:02:17 −0700; A-001 records outputs at 11:03).
   Analyser code at `2be903f` is docs-only vs `de1beac`
   (`git diff --name-only de1beac 2be903f` is five documents). Parser
   hardening in `602dc0b` landed **after** A-001 and is not
   result-changing for logs that already used empty or finite fields, so
   A-001 need not be rerun for S0R-003.

## 4. Per-commit dispositions

Order is `git log --reverse --oneline de1beac..07bb819`.

### Owner merges (9) — all accepted

Each merge tree equals its second-parent tree. No hidden product delta.

| Commit | Second parent | Disposition |
|---|---|---|
| `ff3c45c` Merge PR #246 | `e2ed7eb` | **Accepted.** Inside the previously reviewed `81db126..de1beac` range. |
| `a9d253b` Merge PR #247 | `075e982` | **Accepted.** Same. |
| `28e4c02` Merge PR #248 | `32998e5` | **Accepted.** Same. |
| `c9e7a69` Merge PR #249 | `de1beac` | **Accepted.** This is the merge that closed S0R-006. |
| `c066b1e` Merge PR #250 | `5e4b724` | **Accepted.** |
| `fbf7043` Merge PR #251 | `8c9fdc8` | **Accepted.** |
| `f97a003` Merge PR #252 | `c0ec727` | **Accepted.** |
| `a2fec99` Merge PR #253 | `fba1c0b` | **Accepted.** |
| `07bb819` Merge PR #254 | `57356ec` | **Accepted.** |

### Product / test (1)

| Commit | Disposition | Verification |
|---|---|---|
| `602dc0b` Harden Stage 1 and local runners | **Accepted.** Closes S0R-001/002/003/004/005/008. | Claim-by-claim in section 5. Two reverse mutations red then restored. 102 focused tests green on the final tree. |

### Documentation / records (10)

| Commit | Disposition | Verification |
|---|---|---|
| `5e4b724` Record Cursor/Grok Stage 0 review + Claude counter-review | **Accepted.** | Adds the two review documents plus handoff/action-plan updates. Content matches the previous independent review this session authored. No sneaked statistic. |
| `2be903f` Nine runs PENDING_REVIEW → VALID | **Accepted.** S0R2-001 (headings leftover); S0R2-002 (skipped UNANALYSED, closed on the final tree). | Diff is exactly nine Validity-row replacements in `docs/alpha-result.md`. Grep of the diff finds no Sharpe/IC/p-value/CAGR. Committed before A-001. See section 6. |
| `8c9fdc8` Record A-001 | **Accepted** as a process record, not as edge. | New `## A-001` entry: once, full identities, Bonferroni 0.05/180, look count 23, floor 428, one insufficient cell disclosed (23 < 24), IC/long-short null, long-only clears labelled beta-carrying. S0R-007 closed by amendment; R-022 text unedited. Artifact JSON hashes were **not** re-hashed here (files absent). Internal arithmetic of the narrative is consistent: 45 spec-universe cells × 4 hypotheses = 180; one insufficient cell removes 4 hypotheses → 44 IC + 44 LS + 88 LO; short restatement 15 × 4 = 60. |
| `c0ec727` Hardening-round record + env note | **Accepted.** | Documents the fix inventory and a machine-local long-path/streamlit mismatch. Does not change code. |
| `fba1c0b` Fully green validation record | **Accepted.** | Records 4,246/0/25 after LongPathsEnabled. Not reproduced this session. |
| `d905f2b` Independent S0R hardening review (draft) | **Accepted** as a draft later completed. | Adds `REVIEW_2026-08-18_S0R_HARDENING_REVIEW.md`. Later commits correct the premature full-suite placeholder. This follow-up independently re-verified the product rather than citing that review as authority. |
| `0bb1914` Accept the review; flag unfilled full-suite line | **Accepted.** | Honest shared-worktree note. |
| `3a59568` Fill the reviewer's own 4,246/0/25 | **Accepted.** | Completes the draft. |
| `f84f5fa` Correct premature-acceptance attribution | **Accepted.** | Eight mutations, not nine; reviewer's own suite. |
| `57356ec` Authoring-session counter-review | **Accepted** as a counter-review of the hardening review. | Cannot substitute for this session's independence on `602dc0b`. Tree-identity and merge-fast-forward claims re-verified here and match. |

## 5. Primary commit `602dc0b` — claim-by-claim

**S0R-001 (replications bind) — CLOSED, verified.**
`research/lean/alpha_stage1_replications.py`: the
`if any(value is None for value in turns): continue` gate is gone; bind
updates `previous_weights` / `previous_entries` unconditionally and
stores possibly-None turnovers on the cohort. Emitter writes `""` via
`_turn` and emits per-spec SPECMETA (R-007 class). Reverse mutation of
the gate went red on `len(cohorts) == 1`.

**S0R-002 (benchmark bind / settle / analyser) — CLOSED, verified.**
`alpha_stage1_benchmark.py`: bind no longer returns on an unpriceable
prior name or on `turnover is None`; settle emits at
`len(outcomes) >= MIN_NAMES` with priced **and** entered; `on_end`
emits five-field BROW with an empty-turnover path.
`analyse_qc_alpha_stage1.py` charges `fillna(1.0)` and discloses
`unavailable_turnover_periods` and `underfilled_months`.
`test_stage1_benchmark_zombie_month_cannot_kill_the_series` drives the
real class through bind, underfilled settle, and parser round-trip.
`test_stage1_analyser_charges_full_turnover_and_discloses` pins the
charge magnitude.

**S0R-003 (present nan token) — CLOSED, verified.**
Decimal ROW ic/turnover go through `_optional_finite` (empty → None;
present non-finite → `InvalidLog`). BROW present turnover must be
`math.isfinite`.
`test_parsers_refuse_present_nonfinite_turnover_or_ic_tokens` uses a
literal `nan` token. Packed v2 cannot encode NaN; left unchanged.

**S0R-004 (universes runner heal) — CLOSED, verified.**
`run_alpha_universes_20260816.py`: after recording the return, a None
drift omits that month's turnover **and still** replaces `previous`.
`test_universe_portfolio_heals_after_an_unpriceable_book` requires
dates[1] absent from turnover and dates[2] present.

**S0R-005 (monthly docstring) — CLOSED, verified.**
`_rebalance_turnover` now describes the never-gate / charge-1.0
contract, not the removed retry contract.

**S0R-008 (charge magnitude) — CLOSED, verified.**
Exact net-vs-gross mean delta
`1.0 * 2.0 * 10bps / 10000 / n` on a synthetic log with one empty
turnover and all other turnovers 0.0. Reverse mutation to `fillna(0.0)`
went red on that assertion; the old count-only tests would have stayed
green.

**Deliberate non-change (settle-side full-book continue).** Agreed
correct, same four reasons as the hardening review: no persistent-state
contamination; SPECMETA-visible gap; equal-weight benchmark is a
different statistic from a named long/short book; changing Stage 1
alone would diverge the two stages mid-campaign. Residual caveat
disclosed: dropped alpha months could cluster; Stage 1 mitigates by
matching the benchmark to alpha dates.

**Vacuous-pass audit.** The bind test asserts `len(cohorts) == 1` and
the full spec set before looping. The charge tests index concrete
report keys (KeyError on absence) and pin an exact delta. The universes
test asserts exact index membership. None of these can pass on empty
results.

## 6. Ledger sequencing (`2be903f` / A-001)

Frozen vocabulary:

- **VALID** = reviewed code, complete output, **statistics usable**
- **UNANALYSED** = complete output, analysis not yet run
- **PENDING_REVIEW** = review gate not completed

`2be903f` jumped PENDING_REVIEW → VALID **before** A-001 computed
statistics. The honest intermediate token was UNANALYSED. The commit
message is explicit that no statistic existed yet. That is S0R2-002:
intent (record acceptance before seeing numbers) is correct; the status
token was overloaded. On the **final tree**, after A-001, VALID is
defensible because statistics now exist and are usable with the stated
limits. Do not rewrite the nine VALID rows.

What remains wrong on the final tree is **S0R2-001**: the nine section
headings still say `(PENDING_REVIEW)`, and the pre-A-001 summary
paragraphs still say the nine runs are PENDING_REVIEW and that no
statistic has been observed — immediately above A-001, which observed
one. Those headings were not updated when the Validity rows were. A
reader grepping headings, or stopping at line 744, gets the wrong
current state.

A-001 process (checked without treating numbers as edge):

- claimed once-only observation of the 180-cell family;
- analyser identity claimed byte-identical to reviewed `de1beac`;
- both Bonferroni gates named; smallest attainable p reachable;
- insufficiency for MULTI_ALPHA_COMPOSITE / A_large disclosed with
  required 24 / observed 23 / NOT MET;
- look count stays 23; lifetime floor stays 428;
- IC and long-short reported as failing the frozen gate;
- long-only clears labelled as **not** stock-selection edge beyond the
  market, in the same entry as the result;
- S0R-007 closed by a new amendment, R-022 unedited.

This session did **not** re-hash the three machine-local JSON files and
did **not** re-run the analysers. Parser hardening after A-001 does not
require a rerun for empty/finite logs.

## 7. Issue ledger

Prior-review items, closure status as verified this session:

| ID | Priority | Status | Notes |
|---|---|---|---|
| S0R-001 | P2 | **Closed** | `602dc0b`; mutation red on bind test, restored green. |
| S0R-002 | P2 | **Closed** | `602dc0b`; bind, underfill settle, five-field BROW, analyser fillna+disclosure. |
| S0R-003 | P3 | **Closed** | `602dc0b`; `_optional_finite` / BROW isfinite; nan-token test. |
| S0R-004 | P3 | **Closed** | `602dc0b`; universes healer test. |
| S0R-005 | P3 | **Closed** | `602dc0b`; docstring. |
| S0R-006 | P3 | **Closed** | `c9e7a69` merged `de1beac`. |
| S0R-007 | P3 | **Closed** | `8c9fdc8` A-001 amendment; R-022 unedited. |
| S0R-008 | P3 | **Closed** | `602dc0b`; exact delta; fillna mutation red, restored green. |

New items from this follow-up. Resolved items retained.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| S0R2-001 | P3 | Open | `2be903f` (incomplete heading update); still present at `07bb819` | `docs/alpha-result.md` R-009/011/012/014/015/016/020/021/022 headings; summaries ~L586–589 and ~L737–744 | Nine `##` headings still say `(PENDING_REVIEW)` while the Validity row is **VALID**. The battery-complete summary still says all nine are PENDING_REVIEW and that no statistic has been observed, immediately above A-001. | Grep of headings vs Validity rows; those two summary paragraphs sit above `## A-001`. | The Validity field is the contract, but headings and the last pre-A-001 summary are what a reader hits first. `2be903f` already rewrote Validity rows, so append-only does not require leaving the headings stale. | Pending: retitle the nine headings to VALID, and append (do not rewrite A-001) a one-line current-status note that the pre-A-001 summaries are superseded. Do not change R-022's output paragraph. | Confirmed by reading the ledger on `07bb819`. |
| S0R2-002 | P3 | Closed — no change needed on the final tree | `2be903f` | `docs/alpha-result.md` Validity rows | Intermediate commit used VALID before statistics existed; UNANALYSED was the vocabulary fit. | Frozen status table L35–38 vs commit message "before any statistic exists." | Sequencing intent was correct (acceptance recorded before results). After A-001, VALID is the right durable status. Rewriting VALID back through UNANALYSED would be theatre. | None. Record only. | Source + `2be903f` diff (nine Validity rows, no statistic). |

SHR-001 (malformed `abc` token → uncaught `ValueError`) and SHR-002
(bind test stubs `_rebalance_turnover`) from the hardening review are
agreed: P3, closed without code change. Not re-probed this session;
failure direction of SHR-001 is fail-closed either way.

## 8. Generalized-instance search

Re-ran across `research/lean/` and `scripts/`:
`if any(value is None for value in turns)`, `if turnover is None:`,
`if drifted is None`, `if exit_turnover is None`.

- **No bind-side turnover gate remains.** Surviving `turnover is None`
  hits are the two emitters' empty-field paths
  (`universe_benchmark.py`, `alpha_stage1_benchmark.py`).
- `alpha_battery_short.py:115` (`if exit_turnover is None: return None`)
  is the v2 unavailability **producer**, not a result-row gate.
- Settle-side `any(symbol not in outcomes)` remains at monthly, short,
  and Stage 1 replications — deliberate, section 5.
- `dropna()` before the later finite check still exists in the battery
  and benchmark parsers as defense-in-depth; present `nan` can no
  longer reach it from the decimal path.

No new sibling found in `assistant/`, `execution/`, or `risk/`.

## 9. What this review does and does not authorize

- `602dc0b` **passes independent review.** The Stage 1 code gate is
  cleared.
- **Stage 1 execution is NOT authorized by this document.** Launching
  it is an owner decision (24 new counted cells weighed against A-001).
- No analyser rerun on the nine Stage 0 logs; A-001 remains the single
  observation. No deployment, epoch roll, operator-database mutation,
  paper orders, or live trading.
- No `FEATURE_MILESTONE_RECORD.md` entry: this is a research/review
  round, not a completed platform milestone.
- This review file is local to `user/cursor/review-s0r-followup-20260818`
  and is **not committed or pushed** unless the owner asks.

## 10. Counter-verification notes (for a later Claude pass)

Verify before classifying, then search siblings. Do not run the frozen
analysers on the nine logs.

1. Confirm `git log --reverse --oneline de1beac..07bb819` is still 20
   commits and `origin/main` is still `07bb819` before starting. If the
   remote moved, stop and extend scope.
2. For S0R2-001: open `docs/alpha-result.md` and confirm the nine
   `## R-0xx … (PENDING_REVIEW)` headings against Validity **VALID**,
   and the two summary paragraphs above A-001. If those headings have
   already been retitled, close S0R2-001 with the correcting commit.
3. For `602dc0b` closures: do not accept the commit message. Re-read
   the bind/settle/emitter/analyser sites and, if practical, reverse-
   mutate the replications bind gate and battery `fillna(1.0)` as this
   session did.
4. Do not treat A-001's six long-only clears as stock-selection
   evidence. The entry already says they are not.
5. Do not launch Stage 1 from this review.
