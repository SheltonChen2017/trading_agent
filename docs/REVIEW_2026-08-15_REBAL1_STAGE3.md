# REBAL-1 Stage 3 — tax-aware trims of overweight sleeves

Date: 2026-08-15
Author: Claude
Base: `45faf1c` (Stage 2 counter-review merged by PR #229)
Branch: `user/claude/rebal1-stage3-tax-aware-trims-20260815`
Status: **Implemented; pending independent review.**

## Authorization

The milestone plan required Stage 3 to have "separate explicit authorization
naming it" before any code was written, because it is the first path where a
rebalancing sell originates from the app's own arithmetic. The owner gave
that on 2026-08-15 ("now start implementing stage 3").

That authorization covers *building* the workflow. It does not authorize
deployment, an epoch roll, or any change to the operational checkout, and
nothing here submits an order.

## Why this stage is different

Every other sell in this app is either a computed policy breach
(`assistant/proposals.py`) or the owner naming a holding they want to sell
(`assistant/user_directed_sell.py`). Stage 3 is the app saying "this sleeve
is above its band" and preparing a sale in response. That difference is why
the module refuses in more places than it proposes, and why the page states
plainly that it is the only such path.

## What the owner decides, and the app never does

Sleeve, ticker, amount, and lot strategy. All four are required inputs with
no default; the controls start at "-- choose --" and zero, and the check
button stays disabled until all of them are set.

## What the module computes

Amount above the band, amount that restores the target, the individual open
lots with acquisition date and holding period, which lots the chosen strategy
would consume, the realized gain split into short- and long-term, any working
sell already reducing the sleeve, and the remainder left behind.

## The five refusals, and why each direction was chosen

1. **Non-overweight sleeve.** Nothing inside or below its band can be
   trimmed.
2. **Cash and the residual are untrimmable.** Cash is not a holding, and
   absence from the profile is never a reason to sell — the rule Stage 1
   states about the residual, applied where it would actually bite.
3. **A sale beyond the target-restoration amount is refused.** Trimming past
   target does not get ahead; it flips the sleeve underweight and hands the
   next Stage 2 pass a shortfall to buy back, paying spread and tax in both
   directions.
4. **An incomplete tax ledger refuses the whole trim.** This stage exists to
   show the realized-gain consequence. A trim proposal that silently omitted
   it because the ledger cannot cover the position is precisely the
   pre-tax-looks-good trap this project has been caught by before, and
   `docs/MANDATE.md` rates tax sensitivity High for that reason.
5. **A working sell already counts against the excess**, measured on the
   projected value, so a second trim is not prepared for a gap the first is
   already closing (HEDGER-004's lesson).

## Execution-time binding

`_validate_proposal_context` now covers `user_directed_rebalance_trim` as
well as the Stage 2 buy status, through a named
`_PROFILE_BOUND_EVIDENCE_STATUSES` set so the intent is legible rather than
a growing string comparison.

Trims are bound for a stronger reason than buys, and the docstring says so: a
stale buy spends money toward a target the owner has since moved, while a
stale trim **sells** toward one and realizes gains that no later profile edit
can un-realize.

## A consequence worth knowing

The restoration cap makes it arithmetically impossible to sell most of a
sleeve's *only* holding: restoring a 40% target from a heavily overweight
sleeve always leaves far more than a sub-one-share remainder. Closing a
position through a trim is therefore only reachable when that position is a
minor part of its sleeve. This is correct behaviour rather than a limitation
to work around, and it is pinned by a test so nobody later "fixes" it.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- `tests/test_rebalance_trim.py`: **36 passed** (new).
- `tests/test_ui_portfolio_rebalance.py`: **20 passed** (16 before).
- Mutation verification: **6 mutations, 6 detected** by exactly the intended
  test — allowing a sale past target restoration, dropping the incomplete-
  ledger refusal, making non-overweight sleeves trimmable, making cash and
  the residual trimmable, measuring the excess on current instead of
  projected value, and removing trims from the execution-time profile
  binding.
- Full settled tree result: recorded in `docs/SESSION_HANDOFF.md`.

Two test fixtures were wrong on first write and are worth recording, because
both failed for a reason that turned out to be the design working: a
fractional remainder and a full position close are both unreachable on a
single-name sleeve under the restoration cap. The fixtures now use a
two-name sleeve, which is also the realistic shape.

## Untested and out of scope

- Nothing here touches a real broker, order, or paper account.
- **Lot selection is advisory.** The app records which lots the owner chose;
  it does not instruct the broker to use them, and the proposal says so.
- The realized gain is an estimate against the displayed reference price, not
  a settlement figure.
- **No evidence supports the target shape.** Trimming realizes tax now in
  exchange for a portfolio shape this project has not shown to be better.
- Development-only. Authorizes no deployment, epoch roll, scheduler change,
  operator-database mutation, or live trading. Deploying would change
  `code_commit` and close active `paper-epoch-005`.
