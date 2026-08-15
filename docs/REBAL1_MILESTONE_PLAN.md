# REBAL-1 — Wide-band portfolio rebalancing (milestone plan)

Author: Codex (plan), relayed and recorded by Claude
Adopted: 2026-08-15
Status: **Stage 1 implemented, pending independent review. Stages 2 and 3
not started.**

This file records the owner-adopted staging so the sequencing survives the
conversation it was written in. It is the authority for what REBAL-1's
stages contain; `docs/ACTION_PLAN_2026-08-02.md` remains the authority for
whether a stage happens next.

## The evidence position, stated first

This project's only `confirmed` research entry is *"Wide rebalance band vs.
tight/continuous vol-targeting"* — ~89% less tax and turnover for
essentially the same performance. Its `relevant_tickers` are `["SOXX",
"SOXL"]` and its source is the vol-targeting comparison.

**That result does not transfer to a general portfolio.** It is a reason to
prefer a wide band over a tight one as a mechanism, and it says nothing
about whether any particular sleeve shape is right. General portfolio
targets and bands are owner preferences and must be presented as such
everywhere they appear. Claude's original framing of this feature leaned on
the finding as general evidence; Codex corrected it, and the correction is
carried into the code, the profile notes, the page text, and a UI test that
pins the page keeps saying so.

## Stage 0 — Allocation profile

A versioned, fingerprinted profile over SLEEVES rather than invented
per-stock targets:

| Sleeve | Membership |
|---|---|
| Cash | computed |
| Dividend income | `config.DIVIDEND_INCOME_TICKERS` |
| Growth | `config.GROWTH_ROTATION_TICKERS` |
| Leveraged reinvestment | `config.DIVIDEND_REINVEST_TICKERS` |
| Hedge | `config.HEDGE_SLEEVE_TICKERS` |
| Other / unassigned | residual |

Rules: targets total exactly 100%; the band is a RELATIVE percentage of each
target, not percentage points; changing the profile makes previous analysis
and proposals stale; unassigned holdings stay visible, and absence from the
profile is never authorization to sell.

**Owner-approved values, 2026-08-15** (cash 10, dividend 15, growth 40,
leveraged 15, hedge 10, other 10; band ±25% relative). The owner approved
these after being shown that the configured sleeves currently cover about a
fifth of the book, with ten holdings unassigned. They are a stated
preference. A cap is not a target: `max_leveraged_etf_pct` says how much
leveraged exposure is forbidden, not how much is wanted, and neither the
mandate nor the policy contains an allocation.

## Stage 1 — Read-only Portfolio Rebalancing page

**Implemented.** Total equity, invested %, cash %, breached-band count, a
sleeve allocation chart, and a drift table carrying sleeve, target, band,
current, pending, projected, dollar gap to target, and status.

Statuses: `inside_band`, `underweight`, `overweight`, `unassigned_holdings`,
`pending_value_unknown`, `data_unavailable`, `policy_conflict`.

Calculation rules: exact broker values and Decimal arithmetic; measurable
pending buys and sells included; projection refused when open-order data is
unavailable; inclusive band boundaries; duplicate position rows aggregated;
every holding surfaced; malformed, non-finite, negative, or otherwise
unusable authoritative values refused.

Stage 1 emits no shares, sides, proposals, approvals, or action-shaped
recommendations.

## Stage 2 — Buy-only cash steering (NOT STARTED)

Separately reviewed milestone. The owner enters a new-money budget used only
to reduce sleeves below their lower bands. It must count holdings and
pending orders, let the owner pick the ticker within each sleeve, support
whole-share and fractional modes, show residual unallocated money, create
separately approved proposals, have no submit-all action, never silently
omit an unaffordable selected leg, bind proposals to the allocation-profile
fingerprint, and hide stale cards after any profile, snapshot,
pending-order, selection, or sizing change.

## Stage 3 — Tax-aware trims (NOT STARTED, requires separate authorization)

An overweight-sleeve workflow showing amount above band, target-restoration
amount, tax lots, holding period, realized-gain consequences, pending sells,
and fractional remainder. The owner selects ticker, amount, and lot
strategy. Each sale remains separately approved.

Stage 3 is where rebalancing first sells on the app's own initiative, unlike
every other sell path in this app, which is either a computed policy breach
or the owner's explicit instruction. It should not begin without explicit
authorization naming it.

## Code archaeology

A deleted historical implementation survives as commit
`85a77291a3a8de88a82b3670dcf05793b6825c1c` (`assistant/rebalance.py`,
`tests/test_rebalance.py`). It was inspected, not restored: its equal-weight
target was superseded by sleeves, and it predates current schemas and safety
contracts. Two of its instincts were carried forward deliberately — position
aggregation before measurement, and a distinct status for holdings outside
the target — as was its central observation that a target had to be chosen
by the owner rather than derived in code.
