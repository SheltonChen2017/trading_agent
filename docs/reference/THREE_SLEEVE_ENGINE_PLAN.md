# Three-sleeve engine — owner-defined allocation engine (implementation plan)

Status: **owner-adopted 2026-08-09** (in-session, this document is the record).
Scope class: this is the owner decision that unblocked the allocation work the
action plan tracked as GR-7d. It deliberately does NOT implement the archived
plan's "rebalance-to-target proposals" shape — the owner defined an engine of
their own instead, and this plan records that engine exactly rather than
relabelling it. GR-7d's original shape is superseded, not silently completed.

**Prior-decision disclosure (found 2026-08-09, after adoption).** The owner
had already decided GR-7d once before, differently: on 2026-08-06 they chose
an equal-weight target across all `UNIVERSE` names with a ±25% relative band,
and a report-only drift slice was implemented (`assistant/rebalance.py`, 639
test lines) on `user/claude/gr-7d-rebalance-targets-20260806` — which was
never merged, so `main` still said "blocked" and neither the owner nor the
2026-08-09 session remembered it when this engine was adopted. Under the
instruction hierarchy the later explicit decision governs: **this plan
supersedes the 2026-08-06 equal-weight decision as well**, surfaced to the
owner the same day. **That branch was deleted by owner instruction on
2026-08-13** during a repository cleanup, so the equal-weight slice is no
longer reachable from any current local or fetched remote branch. Review on
2026-08-13 found that this checkout still retains the deleted branch tip as
the dangling Git object `85a77291a3a8de88a82b3670dcf05793b6825c1c`
(`assistant/rebalance.py` plus its 639 test lines). That object is local-only,
not fetchable from the approved remote, and may disappear during Git pruning;
it is a recovery lead, not durable preservation and not authority to restore
the superseded feature. Its two-machines operational facts survive
independently: they were ported to
`docs/operations/OPERATIONAL_FACTS.md` on 2026-08-09 because they are true regardless
of which allocation shape governs.

Audience: repository owner, Claude Code, Codex, and future reviewers.

## 1. The engine, in the owner's words (2026-08-09)

1. Retain at least 10-15% of the portfolio in a dividend-income sleeve
   (aside from cash). Candidate holdings: JEPQ, JEPI, NVDY.
2. Buy semiconductor and tech stocks. +5% is the gain-review threshold:
   if price grows to over 105% of the buying price, the owner intends to
   sell. −10% is the decline-review threshold: if price declines to 90%
   of the buying price or lower, consider buying additional shares — not
   automatically; a notification is enough.
3. Dividends from the dividend sleeve are reinvested into leveraged ETFs
   such as NVDL, SOXL, TQQQ.

Plus one standing owner instruction, same date: **keep the tax-reduction
mechanism** — the tax-consequence surfacing described in §4 is a first-class
requirement of every milestone, not an optional annotation.

## 1.1 REVISION 2 — the growth rule, revised on measured evidence
(owner-adopted 2026-08-09, same day, after the backtest)

Before M2 encoded anything, the §1.2 rule was backtested against
buy-and-hold on the six candidate names over the project-standard ~7-year
window (next-open fills, 37%/15% annual tax netting with carryforward,
terminal liquidation taxed on both sides, 3% cash yield, dividend-adjusted
prices; dated experiment scripts under `scripts/`, registry entry in
`assistant/research_findings.json`). Findings, all structural rather than
marginal:

The after-tax figures are explicitly **modeled proxies**, not tax-accounting
results: auto-adjusted prices fold dividends into price return, so the scripts
do not separately model dividend tax timing/classification, and their simple
`>365 days` term test can differ from the app's calendar/leap-day-correct tax
authority at boundary dates. Those limitations weaken the tax-number precision,
not the observed structural fact that the full-exit rule spent almost all of
the window in cash.

- the adopted +5% any-term full exit produced a **3.29%** modeled
  after-tax-proxy CAGR vs
  **48.14%** for buy-and-hold — the rule sat in cash 95-99% of all days,
  and at 0% cash yield its CAGR was 0.30%;
- EVERY full-exit variant strands (+50 any-term 6.5%; long-term-gated full
  exits ~10.7%): once fully out, re-entry at −10% from disposal rarely
  arrives in a trending name;
- trimming HALF the lot instead of exiting repairs it (~26% CAGR, worst
  ticker drawdown −38% vs buy-and-hold's −66%);
- LONG-TERM-GATING the trim was 0.55 CAGR point higher in this run (26.33%
  vs 25.78% ungated), and the observed run realized no short-term gains;
  only scheduled gain-review trims are structurally gated — a terminal or
  owner-directed liquidation can still realize a short-term result; and
- the trim threshold is insensitive (+50 vs +100 within 0.1 CAGR point),
  i.e. not a knife-edge fit.

**The owner therefore revised rule 2 to: LONG-TERM-GATED TRIM-HALF AT
+50%.** A gain review fires only when a lot is at or above +50% on its own
basis AND past its long-term date, and it proposes trimming HALF the lot,
never exiting it. A lot above the price threshold but still short-term is a
distinct reported state — "awaiting long-term", whose content is the
days-to-long-term countdown — and is deliberately NOT a crossing. The −10%
decline review, per-lot basis, re-entry rule, floor, and
notification-not-automatic stance are unchanged.

Also revised for M3 by the same decision: **dividend income funds pending
decline-review adds first**; leveraged-ETF reinvestment happens only when
no dip-add is waiting. This addresses the measured drag of trim proceeds
idling in cash and breaks the NVDY→NVDL single-issuer pipeline (§3).

The backtest numbers are DESIGN GUIDANCE, not a research finding: one
window, hindsight-selected names, eight uncounted variant looks. What was
adopted is the structure (trim + gate + dip-adds), not a performance claim.
The revised rule earns prospective evidence in paper like everything else.

### 1.2 Original rule 2 as first adopted (superseded by §1.1, kept for the
record)

+5% was the gain-review threshold: if price grew past 105% of a lot's
buying price, the owner intended to sell the lot. Rejected by measurement
the same day — see §1.1.

## 2. Resolved design decisions (owner delegated to recommended defaults,
2026-08-09)

| # | Decision | Resolution |
|---|---|---|
| 1 | Growth-sleeve candidate list | `NVDA, AMD, AVGO, TSM, MSFT, SOXX` — five researched semis/tech names plus one diversified semiconductor ETF anchor. Owner may edit the config list at any time; the list is data, not code. |
| 2 | Threshold basis | **Per-lot**, never average cost. Each lot carries its own gain/decline reference (its `cost_per_share`), which cleanly defines what happens after averaging down: the new lot gets its own thresholds and the old lot keeps its own. Matches how `assistant/tax_lots.py` already models the portfolio, and average cost is exactly the lens that module's docstring warns "hides real money". Unchanged by revision 2. |
| 3 | Re-entry after a gain-review disposal | The name **stays in the candidate list**; a fresh decline-review notification requires a −10% move measured from the disposal price recorded at sale time (a fresh setup), not from the original basis. Under revision 2 a gain review trims rather than exits, so full flatness is rarer — the rule still matters for the remainder path and for owner-initiated exits. Implemented in M2 (it is notification state, not report state). |
| 4 | Dividend-sleeve floor | **Warn below 10.00%** of total equity — the low end of the owner's 10-15% range, chosen because `max_position_pct` (5%) means a 15% sleeve requires all three candidate names at cap exactly, with zero slack. One number, exact boundary, no range logic. |

## 3. What this engine is, and is not

These targets and thresholds are the **owner's stated preference**. Nothing
in this plan or its implementation may describe them as validated, optimal,
researched, or evidence-backed. Revision 2 was *informed by* a descriptive
backtest (§1.1), which is design guidance — one window, hindsight names,
uncounted variant looks — not confirmation under this project's rigor bar.
The original +5%/−10% rule ran counter to the project's strongest confirmed
finding (the wide-rebalance-band tax result); the measured backtest agreed,
and revision 2 realigned the rule with that finding. The paper epoch is
where the revised rule earns prospective evidence.

Known, disclosed characteristics the owner accepted:

- Under revision 2 a scheduled gain review can never realize a short-term
  gain (the long-term gate is part of the rule). Owner-initiated sales
  outside the rule can still be short-term; the report's term/countdown
  fields exist so that consequence is visible first.
- Trim proceeds idle at cash yield until a decline review or the M3
  dividend-routing deploys them — the measured cost of trimming versus
  never selling (~26% vs ~36% CAGR in the backtest window) is accepted as
  the price of a profit-taking discipline.
- NVDY is a single-stock synthetic covered-call ETF (NVDA), not a
  diversified income fund like JEPI/JEPQ; NVDY income buying NVDL (NVDA 2x)
  concentrates a single issuer on both sides of the dividend pipeline. The
  report surfaces this overlap by name (§5 M1).

## 4. The tax-reduction mechanism (first-class, every milestone)

Wherever a gain-review threshold crossing is reported or notified, the payload
MUST carry, per lot:

- unrealized gain (money, decimal path);
- `term_if_sold_now` (`short` / `long`);
- `days_to_long_term` and the first long-term date, from
  `assistant/tax_lots.py::unrealized_by_lot` — the already-reviewed
  authority (leap-day correct, IRS day-after-acquisition rule);
- no invented tax brackets: classification and dates only. Estimating the
  owner's marginal rate is out of scope; naming the term and the date the
  term changes is the mechanism.

Intent as originally adopted: when a lot crossed the threshold at day 340,
the owner saw "short-term; long-term in 26 days" next to the gain and could
choose to wait. **Revision 2 promoted this mechanism from advisory to
binding**: the long-term gate means a scheduled gain review cannot exist
for a short-term lot, and the "awaiting long-term" report state carries the
same countdown. The fields remain on every lot row so owner-initiated
sales outside the rule still see their tax consequence first. The engine
still never makes the choice.

## 5. Milestones (one branch each; stop for independent review between)

### M1 — config + sleeve status report (read-only) — THIS MILESTONE

New config (all deliberately outside `UNIVERSE`/`BASKETS`; membership in a
list is never an allocation authorization, same convention as
`DEFENSIVE_CARRY_TICKERS`):

- `DIVIDEND_INCOME_TICKERS = ["JEPQ", "JEPI", "NVDY"]`
- `GROWTH_ROTATION_TICKERS = ["NVDA", "AMD", "AVGO", "TSM", "MSFT", "SOXX"]`
- `DIVIDEND_REINVEST_TICKERS = ["NVDL", "SOXL", "TQQQ"]` (must be a subset
  of `LEVERAGED_ETF_TICKERS` so existing leveraged-exposure accounting and
  the `max_leveraged_etf_pct` cap automatically cover them — enforced by
  test)
- `SINGLE_STOCK_INCOME_ETF_UNDERLYING = {"NVDY": "NVDA"}` (overlap
  disclosure only; NVDY is NOT added to any leveraged list because that
  would change `max_leveraged_etf_pct` enforcement, a policy behavior
  change this milestone must not make)
- `DIVIDEND_SLEEVE_FLOOR_PCT = 10.0`
- `GROWTH_GAIN_REVIEW_THRESHOLD_PCT` — `5.0` at first adoption; **`50.0`
  under §1.1 revision 2**
- `GROWTH_GAIN_REVIEW_REQUIRES_LONG_TERM = True` (added by revision 2)
- `GROWTH_GAIN_REVIEW_TRIM_FRACTION = 0.5` (added by revision 2)
- `GROWTH_DECLINE_REVIEW_THRESHOLD_PCT = -10.0`

New module `assistant/sleeve_report.py`, shaped like
`assistant/cash_reporting.py` (pure evaluation function over passed-in
contracts; store access only in a thin composition helper):

- dividend sleeve: per-name and total market value and % of equity
  (decimal path), floor check at exactly 10.00% (below → warn field, at or
  above → clear), names in the candidate list not currently held;
- growth sleeve: per-lot rows via `unrealized_by_lot` for each held
  candidate, each row carrying the crossed-gain / crossed-decline review
  booleans (exact, inclusive boundaries on the lot's `unrealized_pnl_pct`)
  plus the §4 tax fields. Under §1.1 revision 2 a gain crossing
  additionally requires the lot to be long-term, and a price-met-but-
  short-term lot is reported as the distinct
  `gain_threshold_met_awaiting_long_term` state with its countdown —
  never as crossed;
- lot-coverage honesty: a growth position whose snapshot shares disagree
  with its ledger lots (or that has no lots at all — bought outside the
  app or before ledger bootstrap) is listed explicitly with both numbers
  and a reason; never silently skipped, and threshold flags are only
  computed for covered lots;
- dividend income: confirmed distributions from the account journal
  (`assistant/corporate_actions.py::confirmed_distributions`) — total and
  per ticker. M1 reports income received only; there is deliberately NO
  "reinvestable budget" field until M3 introduces earmark records,
  because an unearmarked budget number would be an action-shaped
  temptation with double-spend semantics nobody has defined yet;
- reinvest sleeve: current market value and % of equity of
  `DIVIDEND_REINVEST_TICKERS` holdings;
- single-issuer overlap: when a held income ETF's underlying (per
  `SINGLE_STOCK_INCOME_ETF_UNDERLYING`) is also reachable through a held
  growth position or a held reinvest ETF (`LEVERAGED_ETF_UNDERLYING`),
  name the issuer and every route to it.

Surfaces: CLI `sleeve-report` (mirrors `idle-cash`: refuses loudly when the
snapshot is unavailable; `--json`), and a Reports-page panel (read-only,
same expander pattern as GR-7a/b/c).

Payload naming rule: report keys must satisfy the existing
action-shaped-field lexical guard — no buy/sell words in keys; "gain
review" / "decline review" / "committed" style naming throughout.

Definition of done: module + CLI + panel + tests (exact threshold and floor
boundaries; NaN/zero/negative/missing price and equity refusals; lot
coverage disagreement; overlap detection; subset config test; read-only
proof over registry and execution tables; payload lexical guard applied to
the new report), full suite green, docs and handoff updated, branch pushed,
independent review requested. Not in M1: notifications, budget tracking,
proposals, any write path.

### M2 — threshold notifications (durable, batched)

Gain/decline crossings become warnings batched into the daily briefing via
the GR-5 path, with durable first-crossing-per-lot state so a crossing
alerts once rather than daily. Under §1.1 revision 2, gain notifications
fire only for long-term-gated crossings and describe a trim of
`GROWTH_GAIN_REVIEW_TRIM_FRACTION`; a lot entering "awaiting long-term"
may notify once with its countdown, and MUST NOT re-notify daily while
waiting. Decline-review re-entry state (decision #3) lives here.
Notification failure must never suppress any other briefing content, and a
lot that loses data coverage mid-stream must surface as "coverage lost",
not as silence.

### M3 — dividend → reinvest proposals (earmark accounting)

Revised by §1.1: confirmed dividend income funds **pending decline-review
adds first**; only when no dip-add is waiting does it become an
APPROVE-gated buy proposal for an owner-chosen ticker from
`DIVIDEND_REINVEST_TICKERS`, through the existing proposal pipeline with
`max_leveraged_etf_pct` untouched as the backstop. Earmark records make
each dividend dollar spendable exactly once: earmarked at proposal
creation, released exactly once on rejection/cancel/expiry, consumed on
fill — same reservation discipline and terminal-path tests as the existing
budget code. Never auto-submitted.

### M4 — prepared gain-review trim proposals — DEFERRED BY DEFAULT

Not scheduled. The Selling page plus M2's notification (with §4 tax fields)
keeps a human squarely between the rule and every taxable event at a cost of
two clicks. Revisit only on explicit owner request.

## 6. Safety boundaries (inherited, restated, unweakened)

- Everything through M3 produces observations, notifications, or
  APPROVE-gated proposals. Nothing ever submits, sizes, cancels, or
  replaces an order on its own.
- No ML/LLM involvement anywhere in this engine. Deterministic Python only.
- Policy caps (`max_position_pct`, `max_total_exposure_pct`,
  `min_cash_reserve_pct`, `max_leveraged_etf_pct`) remain the enforcement
  backstop and are not modified by any milestone of this plan.
- Paper account only. Nothing here touches the frozen operational epoch
  checkout; deployment to the operational machine is a separate owner
  decision after review, epoch rules unchanged.
- Missing, stale, or invalid inputs fail closed into explicit refusal or
  unavailability fields — never into a default, a zero, or a dropped row.
- Risk-reducing sells remain possible regardless of any state this engine
  holds; its features must never gate or delay them.

## Change control

- 2026-08-09 — created; owner adopted the engine and delegated decisions
  1-4 to recommended defaults, keeping the tax-reduction mechanism as a
  standing requirement. M1 scheduled.
- 2026-08-09 (same day, revision 2) — after the measured backtest rejected
  the +5% any-term full exit (§1.1), the owner revised the gain review to
  a long-term-gated trim-half at +50% and rerouted M3 dividend income to
  fund decline-review adds before leveraged reinvestment. Decline review,
  per-lot basis, floor, and every safety boundary unchanged. M1 report
  semantics updated in the same change.
- 2026-08-09 (M2 complete after independent review) — threshold
  notifications per §5 M2: durable `(watch_key, kind)` transition state in
  `sleeve_watch_states`, WARNING alerts through the GR-5 briefing batch on
  inactive→active transitions only (an acknowledged alert is never
  re-opened by an unchanged condition), awaiting-long-term notified once
  with its countdown, re-entry watch from the journal's last disposal fill
  through the GR-4 recorded price path (unavailable price pauses the
  watch, never clears it), coverage loss surfaced rather than silent, and
  briefing-level failure isolation.
  Independent review at correction `c314245` added one-transaction alert
  plus watch-state publication, treated partial lot coverage as blindness,
  excluded broker-held tickers from flat re-entry, rejected stale closes,
  and carried exact-text unrealized money in gain/awaiting notifications.
- 2026-08-13 (M3 COMPLETE AFTER INDEPENDENT CORRECTION) — the owner
  authorized M3 in-session ("start"). Implemented per §5 M3 as revised by
  §1.1 on `user/claude/three-sleeve-m3-earmarks-20260813`:
  `sleeve_dividend_earmarks` table (exact-text money, no float twin),
  `assistant/sleeve_reinvest.py`, CLI `sleeve-reinvest` (read-only status
  with derived effective dispositions) and `sleeve-reinvest-propose`
  (GR-4 recorded-close price, refuses without a fresh close), a Buying-page
  expander, and a briefing reconcile hook with M2-style failure isolation.
  Key semantics: the pool counts broker-confirmed corporate-action
  dividends only; the earmark is the proposal-time notional (floor
  remainder stays in the pool); pending `decline_review` AND
  `reentry_decline` watches both outrank leveraged reinvestment; ambiguous
  proposal outcomes HOLD their earmark; any credible incremental or cumulative
  fill evidence consumes the whole earmark regardless of the final lifecycle
  label. Independent review accepted implementation `7ee4786` after correction
  `b6685b5`, closing two P1 and four P2 findings: poll-only cumulative fills and
  partial-fill rejection labels could release spent dollars; storage trusted a
  caller-asserted pool instead of re-reading the journal in its transaction;
  future/corrupt statuses and nonpositive stored money failed open; and a
  reconcile line broke `--json`. The transaction now derives confirmed income
  and every non-released reservation from durable rows under `BEGIN IMMEDIATE`.
  M3 remains unmerged and undeployed; optional M4 remains deferred.
