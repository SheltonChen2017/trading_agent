# Counter-review — Codex's Stage 0 methodology correction (FQCV-001..005)

> **Post-merge verification (2026-08-17):** Codex independently accepted this
> three-commit counter-review after adding one P3 call-site regression guard;
> no result-changing defect was found. PR #244 merged exact head `9a7e9fc` at
> `b6f577e`. Current gate and topology are recorded in
> `REVIEW_2026-08-17_ALPHA_QC_STAGE0_COUNTERREVIEW_VERIFICATION.md`.

Date: 2026-08-17
Counter-reviewer: Claude (the session whose review FQCV disproved in part)
Reviewed branch: `codex/review-alpha-qc-fable-counterreview-20260817`
Exact reviewed head: `9e4580334f0e0a6a072c650a3b19c89d8492ea8a`
Base: `6bd962fac9e417f0f1d014b4128c2a9597d45e5b` (Fable's merged head)
Ordered range: `ac96d47`, `dd664f9`, `9e45803`
Counter-review branch: `user/claude/alpha-qc-fable-cr-verify-20260817`
Disposition: **Accepted. All three commits accepted; all four FQCV code
findings confirmed and their corrections proven load-bearing. Two follow-up
P3 closures of my own (FCR-001, FCR-002). Codex's central criticism of my
prior review is CORRECT and I record it plainly below.**

## 0. Snapshot handling

Codex's branch existed only locally in the shared checkout when this review
began (its handoff said "local pending this final handoff commit"). To
freeze the snapshot durably before reviewing, I pushed the branch unchanged
to `origin/codex/review-alpha-qc-fable-counterreview-20260817` at exact head
`9e45803`, verified the remote object, and created this counter-review
branch from it. `origin/main` is `4151b3f` (PR #243). No QuantConnect
authentication, upload, compile, backtest, result read, broker access,
database mutation, scheduler change, epoch action, or research look occurred.

## 1. The headline, stated against myself first

My final counter-review concluded "no product defect found" and declared the
QC gate open. **That conclusion was wrong.** FQCV-001 and FQCV-002 are real
P2 result-methodology defects in files I reviewed, inside checklist items I
was explicitly given ("calculate one-way turnover consistently", "do not mix
gross returns, net returns, and transaction costs inconsistently"). Worse,
I had seen the edge of FQCV-001 — I recorded the uncharged staging-session
drift as a minor observation — and misjudged its magnitude: the real issue
was not one session of drift but the whole cost model, worth roughly a
missed 1.0 one-way turnover per six-session cycle (~8.4%/year of untracked
cost at 10 bps/side). FQCV-003 was my own disclosed observation that I chose
not to fix; Codex was right that Method V2's exact-window rule makes it a
finding. FQCV-004 I missed outright: I verified the peer-refusal path on the
assumption that a missing code became `None`, when `int(code or 0)`
manufactured a valid-looking industry 0. The lesson for the next reviewer:
an "observation, not a finding" entry is a finding you have decided not to
verify the consequences of.

## 2. Commit dispositions

| Commit | Disposition |
|---|---|
| `ac96d47` | **Accepted.** All four code findings reproduced red on the pre-correction tree `6bd962f` in this session (unchanged book charged 0.0 per period against a true 1.0 round trip; a 21-close MAX window with one zero scored 19 returns including a fabricated −100% move; missing Morningstar codes stored as bucket 0; the analyser's global `default=12.0` applied to the 42/year short family with no inference). The corrections implement the right contracts: per-period entry-plus-drifted-exit turnover charged on the settling row with cross-period state removed; per-family cadence inference with the CLI value demoted to a refusing assertion; an exact 21-close finite-positive MAX window; positive-only industry codes with stale-code eviction, while the monthly market factor correctly regains unclassified names. Seven mutations below; one survivor became FCR-001. |
| `dd664f9` | **Accepted.** The FQCV report's claims verify (dispositions, evidence, validation arithmetic: 4,196 + 7 new tests = 4,203); the Method V2 additions are dated, appended clarifications freezing the four contracts before any result is observed under them — preregistration, not rewriting frozen history; the plan/ledger/action-plan updates and the supersession note prepended to my report preserve rather than rewrite the record. |
| `9e45803` | **Accepted after this review's records update.** Its topology was accurate when written; the branch's "local pending" status and closed-gate wording are superseded by this counter-review's push and acceptance, recorded in the canonical documents rather than by editing the commit. |

## 3. FQCV findings — verification detail

- **FQCV-001 (P2) — CONFIRMED.** The frozen short experiment measures a
  5-session return once per 6-session cycle; the staging session's return is
  not in the series, so the modeled strategy is in cash through it and every
  period is an independent round trip. The old cross-period drift model
  charged an unchanged book ~0.0 (reproduced) and was inconsistent even on
  its own terms (drift measured only to settle; stale outcomes after a
  failed bind — both noted in my prior review as "minor"). The correction's
  `_round_trip_turnover` = entry (0.5·Σ|w|) + drifted exit
  (0.5·Σ|w(1+r)/(1+R)|), refusing missing outcomes and wiped-out books, is
  the self-consistent treatment, and the exit cost lands on the return that
  caused it. The local battery does NOT share this defect: its daily windows
  tile with no gap (next entry session = previous exit session), so its
  continuous drift model remains self-consistent; likewise the monthly
  battery (settle and re-enter in the same session) and the Stage 1 monthly
  design, whose separate drift-at-rebalance turnover was explicitly frozen in
  round 2.
- **FQCV-002 (P2) — CONFIRMED.** One global `--periods-per-year 12.0`
  default annualized the 42/year short family as monthly, and a mixed
  monthly+short invocation could not be correct at all. The corrected
  analyser infers 12 vs `252/6 = 42` from the exact frozen spec family,
  refuses unknown families, records the choice in the report, and treats a
  conflicting operator value as a refusal. 42/year is consistent with the
  R-002 ledger arithmetic (534 periods over 13 years). The local runner
  already inferred cadence per family and needed no change; the Stage 1
  analyser's fixed 12 remains correct for its monthly cadence.
- **FQCV-003 (P3) — CONFIRMED**, and identical to the observation my review
  recorded without fixing. `_max_daily_return` now requires exactly 21
  finite positive closes; a zero denominator can no longer shrink the window
  or fabricate a −100% return into MAX.
- **FQCV-004 (P3) — CONFIRMED.** `int(code or 0)` pooled every unclassified
  name into fictitious industry 0 for the industry-relative and residual
  signals. The correction keeps missing codes missing (peer refusal via the
  existing leave-one-out path), evicts a stale code when a later month's
  classification disappears, and stops restricting the monthly market factor
  to industry-classified names.
- **FQCV-005 (P3) — CONFIRMED** records staleness, corrected in `dd664f9`.

## 4. Mutation verification

Seven mutations against the corrected head, each run and restored with a
clean `git status`; Codex's requested FQCV-001/002 mutations included.

| # | Mutation | Detected? |
|---|---|---|
| A | Round trip loses its exit leg (entry only) | yes |
| B | Settler reverts to cross-period drift turnover | yes (AST call-site pin) |
| C | Short family annualized as monthly again | yes (2 tests) |
| D | MAX window accepts 20 closes | yes |
| E | Industry code 0 accepted again (short) | yes |
| F | Exit leg ignores drift (undrifted gross ×2) | **NO — FCR-001** |
| G | Short cadence changed to 252/5 | yes |

Post-closure: mutation F reddens `test_short_round_trip_exit_leg_liquidates_
the_drifted_book`; the FCR-002 mutation (`code >= 0` in Stage 1) reddens the
extended directory-wide industry test. Both verified red then green.

## 5. Counter-findings, both closed in this commit

| ID | Priority | Status | Finding | Closure |
|---|---|---|---|---|
| FCR-001 | P3 | **Closed** | The exit leg's DRIFT was unpinned: on a long-only book the drifted weights renormalise to gross 1.0, so the flat-outcome regression cannot distinguish a drifted exit from an undrifted one, and a mutation replacing the exit leg with a second entry leg survived all 36 tests. The drift is load-bearing exactly where signed weights matter — a long/short book whose legs both win shrinks to gross 10/11 of NAV before liquidation (true round trip 0.9545, not 1.0); legs both losing cost 1.0556. | Behavioural test pinning both asymmetric long/short cases and the wiped-out-book refusal. Mutation-verified. |
| FCR-002 | P3 | **Closed** | One FQCV-004 instance survived the generalized-instance search: `research/lean/alpha_stage1_replications.py` still stored `int(code or 0)`. The state is currently dead (written, never read — Stage 1 computes no industry factor), so no result path is affected today, but the file's own design rule is that its machinery mirrors the reviewed monthly battery, and a future industry variant would inherit the fake bucket. | Stage 1 ingestion now mirrors the corrected monthly pattern (`_valid_industry_code`, stale-code eviction), and the directory-wide missing-industry regression is extended to the Stage 1 file. Mutation-verified. |

Severity rationale: FCR-001 is a test gap over correct behaviour; FCR-002 is
a dead-state hygiene port of an already-closed finding. Neither invalidates
`ac96d47`, and FCR-002's product delta cannot change any Stage 0 or Stage 1
result today.

## 6. Validation on the exact final tree

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- FQCV red-reproductions on pre-correction `6bd962f`: all four defects
  reproduce exactly as the report claims.
- Corrected QC battery file after both closures: **38 passed** (36 from the
  head + FCR-001 + the Stage 1 parametrization).
- Focused research/QC/LEAN/document gate: **176 passed**.
- Full suite: **4,205 passed / 0 failed / 25 known dependency warnings in
  906.90s** (the head's 4,203 plus the two closure tests).
- Repository-wide compilation including `research/`: clean.
- Markdown relative-link check: **128 files, 0 broken links** (includes this
  report). Docs/mandate JSON parse: clean. `git diff --check`: clean.
  Staged-content and ordered-commit inspection before each commit.

## 7. Scope, safety, and the gate

Product changes in this counter-review are confined to Stage 1's dead
industry-ingestion state plus two regression tests; no analyser, turnover,
cadence, proposal, risk, execution, broker, registry, mandate, policy,
scheduler, database, or epoch behaviour changed beyond `ac96d47` itself.
No historical result was rehabilitated; the lifetime alpha-cell floor
remains **428** and the run ledger remains five.

**Gate status:** Codex's stated condition — an accepted independent
counter-review of `ac96d47` from its exact pushed head — is satisfied by
this review. One residue is procedural: FCR-002 touches a result-algorithm
file (dead state only, mutation-tested). By the letter of the staged
workflow a Codex acknowledgement of FCR-001/002 is the clean final step
before launch; the owner may instead waive it given the delta's size. After
that, the owner chooses Stage 0 battery completion or Stage 1, the run
executes from the exact merged reviewed head, and every execution is
appended to `docs/Archive/Research/alpha-result.md` as R-005+ with full
project/compile/backtest/source/log identity and before/after look counts.
