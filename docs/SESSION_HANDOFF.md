# Session handoff — REBAL-1 Stage 1 implemented

Prepared: 2026-08-15 by Claude, after counter-reviewing HEDGE-1 and then
implementing Stage 1 of Codex's REBAL-1 milestone plan.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/REBAL1_MILESTONE_PLAN.md`
4. `docs/REVIEW_2026-08-15_HEDGE1_COUNTERREVIEW.md`
5. `docs/REVIEW_2026-08-14_HEDGE1_DEFENSIVE_SLEEVE.md`
6. `docs/MANDATE.md` (§2, §4, §6)
7. `docs/OPERATIONAL_FACTS.md`
8. `docs/OPERATIONS_RUNBOOK.md`

Nothing here authorizes a push, deployment, evidence repair, epoch roll, M4,
funded-account access, live trading, operator-database mutation, or scheduled-
task change.

## 1. Repository topology

- Repository: `https://github.com/SheltonChen2017/trading_agent`.
- Current `main` and `origin/main`: `17be33b`, PR #223's merge of HEDGE-1.
- Claude implementation branch:
  `user/claude/hedge1-defensive-sleeve-20260814`, pushed at integration merge
  `0e5dadb`; implementation commit `1f60ebf`; merged to main at `17be33b`.
- Current review branch:
  `codex/review-hedge1-defensive-sleeve-20260814`, based on exact merged main
  `17be33b`.
- Product/test correction: `46e1248`; review records: `b37aa44`.
- Claude counter-review branch:
  `user/claude/hedge1-counterreview-20260815`, based on the review tip
  `b37aa44`. It contains the counter-review corrections and this handoff.
- The review branch, correction, and this final review/documentation state are
  **local-only and not recoverable on another computer by fetch** until the
  owner explicitly authorizes a push.
- Operational checkout: separately frozen at deployed commit `752d3b7` in
  active `paper-epoch-005`. No HEDGE-1 or review commit was copied there.
- Epoch-005 roll lineage remains rooted in Claude's `4de784e` chain and
  Codex's independent correction `1cb8abf`; this review did not reopen it.
- The completed BUY-1 review remains at correction `44a7f85` on
  `codex/review-buy1-suggestion-picker-20260813`; it is historical recovery
  context, not open work.

Commit dispositions:

| Commit | Disposition | Note |
|---|---|---|
| `1f60ebf` | accepted after correction | Sound feature direction; five P2 and three P3 defects required correction. |
| `0e5dadb` | accepted after correction | Merge conflicts were documentation-only; inherited stale/incorrect records were corrected. |
| `17be33b` | accepted after correction | Merge tree equals `0e5dadb`; inherited findings closed on the review branch. |
| `46e1248` | accepted after correction | Product and regression-test correction. Seven of eight findings reproduce exactly on the submitted tree; two of the corrections introduced new defects, one a P2. |
| `b37aa44` | accepted after correction | Records are accurate; the topology guard they rely on could not stay green past its own merge. |

## 2. Completed HEDGE-1 behavior

The Hedging page measures an owner-selected subset of the configured SH,
BTAL, TLT, and GLD sleeve against an owner-entered percentage of total equity.
It subtracts selected holdings and measurable selected pending buys, then
splits any remaining dollar shortfall equally. It can create ordinary buy
proposals only. Each proposal requires its own typed approval and fresh
execution-gate validation; the page has no hedge sell or submit-all action.

The independent review retained that architecture and corrected these
failure directions:

- the public module now refuses names outside the configured sleeve instead
  of allowing an arbitrary equity to be labeled a hedge;
- malformed or zero authoritative values on a held selected ETF refuse rather
  than falling back to a rounded float or understating current exposure;
- known pending buys reduce the gap, while unavailable open-order data or an
  unknown selected pending value refuses target sizing;
- every selected leg needs a usable recorded close and a valid minimum order
  quantity; one bad or unaffordable leg blocks the complete basket instead of
  redistributing its dollars or silently returning a different subset;
- recorded prices, the shortfall, and equal weights remain Decimal through
  the authoritative sizing input; and
- the UI shows projected exposure including pending buys and disables proposal
  creation while the selected quote set is incomplete.

HEDGE-1 still carries an explicit statement that this project has not shown
the basket reduces drawdown. SH's single-day reset warning remains attached.
The feature establishes software behavior only; it does not establish a
profitable or effective hedge.

## 3. Review findings

The durable issue ledger is in
`docs/REVIEW_2026-08-14_HEDGE1_DEFENSIVE_SLEEVE.md`.

- **0 P0 / 0 P1 / 5 P2 / 3 P3**.
- All eight findings are closed; zero remain open.
- Red-before-green proof comprised nine failures in the first combined run,
  one separate unaffordable-leg failure, and one separate zero-held-value
  failure.
- A generic active-document guard checks the declared current mainline hash
  against the repository's actual mainline, addressing the stale-topology
  recurrence left by PR #223. Its first form asserted EQUALITY with the tip
  and is corrected below.

### Counter-review findings (Claude, 2026-08-15)

The durable ledger is in `docs/REVIEW_2026-08-15_HEDGE1_COUNTERREVIEW.md`.
Every one of Codex's eight findings was re-derived on a throwaway worktree at
the submitted tree `17be33b` rather than accepted on the report's word. Seven
reproduced exactly. HEDGER-005 is partially correct: the direction and fix are
right and retained, but its stated `100/3` float arithmetic does not reproduce
(`100.0/3*3 == 100.0` exactly); the excess appears one step later in the
summed target dollars at ~7e-14 dollars.

- **0 P0 / 0 P1 / 2 P2 / 3 P3**, all closed.
- **HEDGE1CR-001 (P2)** — the new topology guard asserted equality with the
  current `origin/main` tip. That cannot stay green: merging the branch that
  updates the records creates a merge commit, so the declared hash is one
  behind the instant it lands, and a records-only follow-up merges as another
  commit and is stale again. `main` itself would carry the red test. Proven by
  pointing `origin/main` at a synthetic merge commit (restored and verified by
  SHA). Replaced with a REACHABILITY assertion, which still catches a
  fictional, mistyped, or branch-only hash.
- **HEDGE1CR-002 (P2)** — the `open_orders_available` refusal is gated on
  report-only mode and its sibling `unknown_pending` refusal was not, so any
  plain market buy on a sleeve ticker turned the page's default state into a
  red error saying it was "refusing to size another purchase" when nothing had
  been asked for. It is now a disclosure in report-only and still a refusal
  once a target is supplied.
- **HEDGE1CR-003 (P3)** — the new `shares <= 0` refusal treated a zero-share,
  zero-value row (constructible through `build_portfolio_snapshot`'s
  documented API) as unreadable, blocking even the read-only weight. Zero
  quantity now reads as not held; a positive quantity worth zero still refuses
  and is named "impossible" rather than "unreadable".
- **HEDGE1CR-004 (P3)** — the new all-or-nothing refusals named no remedy,
  the same defect class as SET1CR-001. Both now name them.
- **HEDGE1CR-005 (P3)** — HEDGER-005's Decimal fix was unpinned; reverting it
  left all 50 tests green. Now source-guarded, which `CLAUDE.md` §9 permits
  when the invariant is not runtime-observable.

## 4. Validation

Authoritative review environment: `C:\git\trading_agent_venv`, Python
3.13.14, Streamlit 1.60.0, Windows. The repository-local `.venv` executable
could not be launched in this restricted session; the project-configured
shared environment has the same pinned versions.

- Submitted HEDGE tests: **51 passed**.
- Corrected HEDGE module and Streamlit UI: **59 passed**.
- HEDGE plus adjacent allocation, portfolio, execution, and UI suites:
  **165 passed** in 69.86 seconds.
- Final full settled tree: **3,853 passed / 0 failed / 25 known dependency
  warnings** in 729.21 seconds (12:09).
- Final active-record, mandate, and HEDGE suite: **94 passed** in 8.41
  seconds.

Counter-review environment (Claude, 2026-08-15): repository `.venv`, Python
3.13.14, Streamlit 1.60.0, Windows. The repository `.venv` launched normally
here and is the environment for every number below.

- `tests/test_hedge_sleeve.py`: **55 passed** (50 before).
- `tests/test_active_document_consistency.py`: **30 passed**.
- Focused adjacent set (hedge module, hedge UI, document consistency,
  allocation proposals, ML import boundary): **130 passed**.
- Mutation verification: **9 against Codex's corrections** (8 detected; the
  9th was the unpinnable Decimal fix, closed as HEDGE1CR-005) and **7 against
  the counter-review's own** (5 module mutations plus both directions of the
  rewritten topology guard), each detected by exactly the intended test.
- Full settled tree in the repository `.venv`: **3,858 passed / 0 failed / 25
  known dependency warnings** in 683.29 seconds. That is Codex's 3,853 plus
  this counter-review's 5 new tests.
- Final repository compilation: clean.
- Final diff checks: clean. At handoff commit the branch contains the product
  correction followed by the documentation/handoff commit and has no
  unstaged source change.

No real Alpaca request, paper order, funded account, live order, or operator
database write was used as test evidence.

## 5. Mandate, policy, and epoch truth

HEDGE-1 uses long-only ETFs already permitted by the approved mandate. It did
not change `assistant/default_mandate.json`, `TradingPolicy`, or either
fingerprint. The hedge target remains a per-run UI input rather than durable,
fingerprint-bound policy.

That does **not** exempt HEDGE-1 from evidence lineage. Active epoch-005 is
unchanged only because none of this development code is deployed. Any later
deployment changes the epoch's `code_commit` and closes the active epoch even
if the mandate and policy fingerprints remain identical.

Owner instruction dated 2026-08-14: leave epoch-005 unchanged for 60 days.
Do not deploy this feature, use `-AllowPaperOrders` against the shared paper
account, roll the epoch, or alter its scheduled tasks unless the owner gives a
new explicit instruction. Sixty calendar days is not the same as 60 captured
market sessions; that interpretation remains an owner question.

## 6. Machine-local and operational state

- The operational database and credentials were not opened or changed during
  this review.
- Existing Python processes were observed and left running; no app or monitor
  process was stopped.
- `scripts/launch_dev_app.ps1` remains the development entry point. Its
  default scratch database and environment kill switch block submission.
  `-AllowPaperOrders` can reach the same Alpaca paper account as the frozen
  runtime and remains prohibited during the hold absent fresh owner approval.
- CR-W3 remains an operational watch item around the first real AEP dividend
  subtype. Use the reviewed acknowledgement path if it fails closed; do not
  widen reconciliation tolerance or post a manual compensating entry.
- No account number, credential value, balance, or private artifact content is
  recorded here.

## 6b. REBAL-1 Stage 1 (this session's product work)

Branch `user/claude/rebal1-stage1-20260815`, product commit `6fcdd35`, based
on `e067ad8` (PR #225). Not pushed pending owner authorization, per the
plan's workflow clause.

Codex authored the milestone plan; it is recorded at
`docs/REBAL1_MILESTONE_PLAN.md` so the staging survives the conversation it
was written in. Stage 1 only is implemented: a read-only Portfolio
Rebalancing page over a versioned, fingerprinted sleeve allocation profile.
Stages 2 and 3 are not started.

**The owner approved the profile numbers on 2026-08-15** -- cash 10,
dividend 15, growth 40, leveraged 15, hedge 10, other 10, band +/-25%
relative -- after being shown that the configured sleeves cover about a
fifth of the current book and ten holdings are unassigned. They are a stated
preference, not a derived or researched allocation. A cap is not a target.

**Codex's correction to Claude's framing is load-bearing and is carried in
code:** the confirmed ~89% wide-band result has `relevant_tickers`
`["SOXX","SOXL"]` and came from the vol-targeting comparison. It is a reason
to prefer the mechanism, not evidence about this portfolio's shape. The
module, the profile notes, the page, and a UI test all say so.

Points a reviewer should press on:

- one unusable authoritative value refuses the WHOLE report, because sleeve
  weights share an equity denominator and dropping the bad row can
  manufacture a phantom breach on a sleeve that reads fine;
- a ticker listed in two sleeves refuses rather than being assigned;
- unassigned holdings are always surfaced, and the residual reads as
  unassigned even inside its band, so it is never taken for a tidy sleeve;
- pending buys add and sells subtract into the projected column only, an
  undeterminable order marks the sleeve, and unavailable open-order data
  refuses the projection; and
- Stage 1 staleness is structural -- nothing is stored in session state, so
  no card can outlive a profile or snapshot change. Stage 2 will need this
  made explicit.

`assistant/rebalance_bands.py` from the exploratory commit merged by PR #225
is REMOVED here: it measured per-ticker targets, which Stage 0 supersedes
with sleeves, and two drift implementations would be the parallel-rule drift
`CLAUDE.md` warns against.

Validation on the exact tree: **3,916 passed / 0 failed** in the pinned
`.venv`; 50 module tests, 8 UI tests; 9 mutations, 9 detected by exactly the
intended test. Three of those only after a first attempt survived and
exposed real gaps -- the inclusive-boundary test pinned only the upper edge,
the duplicate-aggregation test never reached this module because
`build_portfolio_snapshot` aggregates first, and one mutation had targeted
the wrong line.

## 7. Next authorized step

1. Owner authorizes (or declines) pushing
   `user/claude/rebal1-stage1-20260815`.
2. Independent review of REBAL-1 Stage 1, then a decision on whether Stage 2
   (buy-only cash steering) begins. Stage 3 needs its own explicit
   authorization, because it is where rebalancing first sells on the app's
   own initiative rather than on a computed breach or the owner's
   instruction.
3. Keep epoch-005 frozen under the 60-day instruction and clarify whether the
   target means calendar days or captured market sessions.
4. The SET-1 design question remains open: whether strict whole-share mode
   should permit a fractional sell only when it closes an entire position.
5. `TRADE1CR-002` remains open and unscheduled: date-dependent fixtures in
   `tests/test_strategy_proposals_generic.py` can fail between roughly 00:00
   and 09:30 Eastern.

Do not begin M4, mutate the operator database, alter scheduled tasks, access a
funded account, enable live trading, deploy, or roll an epoch without a new
explicit owner instruction.

## 8. Resume prompt

```text
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md,
docs/REVIEW_2026-08-14_HEDGE1_DEFENSIVE_SLEEVE.md, docs/MANDATE.md, and
docs/SESSION_HANDOFF.md. main/origin-main are 17be33b after PR #223 merged
Claude's HEDGE-1. Codex reviewed that exact merge on
codex/review-hedge1-defensive-sleeve-20260814 and corrected it at 46e1248.
The review closed 0 P0 / 0 P1 / 5 P2 / 3 P3 findings: configured instrument
enforcement, exact held values, pending/open orders, complete-basket refusal,
Decimal sizing inputs, UI state, epoch wording, and stale topology. The review
branch is local-only unless a later handoff says it was pushed. HEDGE-1 is
development-only; operational commit 752d3b7 and active paper-epoch-005 remain
frozen under the owner's 60-day hold. Do not deploy, roll the epoch, mutate the
operator database, begin M4, access a funded account, or enable live trading
without explicit owner authorization.
```
