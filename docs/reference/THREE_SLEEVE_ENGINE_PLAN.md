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
owner the same day. The branch stays unmerged and undeleted as the archived
record of that alternative; its two-machines operational facts were ported
to `docs/OPERATIONAL_FACTS.md` separately because they are true regardless
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

## 2. Resolved design decisions (owner delegated to recommended defaults,
2026-08-09)

| # | Decision | Resolution |
|---|---|---|
| 1 | Growth-sleeve candidate list | `NVDA, AMD, AVGO, TSM, MSFT, SOXX` — five researched semis/tech names plus one diversified semiconductor ETF anchor. Owner may edit the config list at any time; the list is data, not code. |
| 2 | Threshold basis | **Per-lot**, never average cost. Each lot carries its own +5%/−10% reference (its `cost_per_share`), which cleanly defines what happens after averaging down: the new lot gets its own thresholds and the old lot keeps its own. Matches how `assistant/tax_lots.py` already models the portfolio, and average cost is exactly the lens that module's docstring warns "hides real money". |
| 3 | Re-entry after a gain-review exit | The name **stays in the candidate list**; a fresh decline-review notification requires a −10% move measured from the exit lot's disposal price recorded at sale time (a fresh setup), not from the original basis. Prevents the rule from silently draining the growth sleeve to cash with no way back in. Implemented in M2 (it is notification state, not report state). |
| 4 | Dividend-sleeve floor | **Warn below 10.00%** of total equity — the low end of the owner's 10-15% range, chosen because `max_position_pct` (5%) means a 15% sleeve requires all three candidate names at cap exactly, with zero slack. One number, exact boundary, no range logic. |

## 3. What this engine is, and is not

These targets and thresholds are the **owner's stated preference**. Nothing
in this plan or its implementation may describe them as validated, optimal,
researched, or evidence-backed — no such evidence exists, and the +5%/−10%
rule in particular runs **counter** to this project's strongest confirmed
finding (the wide-rebalance-band tax result). That tension is deliberate and
owner-acknowledged: the paper epoch is where the rule gets tested honestly.
The reporting layer must therefore make the rule's costs visible (§4), never
hide them.

Known, disclosed characteristics the owner accepted on adoption:

- Every +5% exit is a short-term gain by construction unless the lot
  happens to be past its long-term date.
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

Intent: when a lot crosses +5% at day 340, the owner sees "short-term;
long-term in 26 days" next to the gain and can choose to wait. The engine
never makes that choice.

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
- `GROWTH_GAIN_REVIEW_THRESHOLD_PCT = 5.0`
- `GROWTH_DECLINE_REVIEW_THRESHOLD_PCT = -10.0`

New module `assistant/sleeve_report.py`, shaped like
`assistant/cash_reporting.py` (pure evaluation function over passed-in
contracts; store access only in a thin composition helper):

- dividend sleeve: per-name and total market value and % of equity
  (decimal path), floor check at exactly 10.00% (below → warn field, at or
  above → clear), names in the candidate list not currently held;
- growth sleeve: per-lot rows via `unrealized_by_lot` for each held
  candidate, each row carrying `crossed_gain_threshold` /
  `crossed_decline_threshold` booleans (exact boundary: `>= +5.00` /
  `<= −10.00` on the lot's `unrealized_pnl_pct`) plus the §4 tax fields;
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
alerts once rather than daily. Decline-review re-entry state (decision #3)
lives here. Notification failure must never suppress any other briefing
content, and a lot that loses data coverage mid-stream must surface as
"coverage lost", not as silence.

### M3 — dividend → reinvest proposals (earmark accounting)

Confirmed dividend income becomes an APPROVE-gated buy proposal for an
owner-chosen ticker from `DIVIDEND_REINVEST_TICKERS`, through the existing
proposal pipeline with `max_leveraged_etf_pct` untouched as the backstop.
Earmark records make each dividend dollar spendable exactly once:
earmarked at proposal creation, released exactly once on
rejection/cancel/expiry, consumed on fill — same reservation discipline and
terminal-path tests as the existing budget code. Never auto-submitted.

### M4 — prepared gain-review exit proposals — DEFERRED BY DEFAULT

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
