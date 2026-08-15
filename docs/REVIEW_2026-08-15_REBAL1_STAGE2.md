# REBAL-1 Stage 2 — buy-only cash steering, plus one Stage 1 correction

Date: 2026-08-15
Author: Claude
Base: `f64b668` (Stage 1 counter-review merged by PR #228)
Branch: `user/claude/rebal1-stage2-buy-steering-20260815`
Status: **Implemented; pending independent review.**

Two pieces on one branch, at the owner's direction.

## 1. Owner decision recorded: policy raised, not the profile

Stage 1's review surfaced that the owner-approved sleeve profile was
unreachable under the active policy:

- the profile targets 90% invested; `my_policy.json` capped total exposure at
  50%; and
- growth targets 40% while its six configured tickers, each capped at
  `max_position_pct` 5%, could jointly hold at most 30%.

The owner chose to **raise the policy** rather than lower the profile,
reasoning that this is a small testing and experimentation account where the
extra concentration is acceptable. `assistant/my_policy.json` in the
DEVELOPMENT checkout now carries `max_total_exposure_pct` 0.90 and
`max_position_pct` 0.07 (six growth names × 7% = 42%, above the 40% target),
version bumped to `0.3.0-personal.1` with the rationale in its `notes`.

**The operational checkout was deliberately not touched, and this is the
important part.** `_active_runtime_lineage()` computes
`policy_fingerprint=compute_policy_fingerprint(policy)` from the live policy
file, and `capture_paper_account_observation()` raises `PaperEvidenceError`
when the epoch's recorded lineage differs. Editing the operational policy
during the 60-day hold would therefore make every nightly capture refuse —
the epoch-002 stall exactly. `C:\git\trading_agent_operational` keeps
0.50/0.05 until the owner authorizes a deployment, which closes epoch-005 on
its own account by changing `code_commit`.

`my_policy.json` is untracked, so this change is local and appears in no
commit. `assistant/default_policy.json` is unchanged: the committed baseline
stays conservative, and a fresh clone still sees the conflict disclosures.

## 2. REBAL1CR-002 — a second masking defect in Stage 1

My Stage 1 counter-review fixed `policy_conflict` masking the band status,
but left the identical defect one status along. `unassigned_holdings` also
occupies `status`, and the headline breach count read `status` — so a
residual at 21.8% against a 7.5–12.5% band was outside its band and not
counted. Same undercount, different label.

Fixed at the root rather than per-status: `SleeveRow` now carries
`band_state` computed independently of the display label, and `breached` is
derived from it. Which label a row shows can no longer change how many
breaches are counted. `band_state` is empty when the band genuinely cannot be
judged (unknown pending value, unusable data), and such rows contribute no
breach in either direction.

Two mutations confirm it: reading `status` for the count reddens the residual
test, and guessing a band state for an unknown-pending row reddens the other.

## 3. Stage 2 — buy-only cash steering

`assistant/rebalance_steering.py`, plus a section on the existing Portfolio
Rebalancing page. The owner enters a new-money budget and picks one ticker
per under-band sleeve; the module produces one APPROVE-gated buy proposal per
funded sleeve.

Against Codex's Stage 2 specification:

| Requirement | How |
|---|---|
| Count holdings and pending orders | Eligibility runs off the Stage 1 report, which already includes measurable working orders in a cash-conserving projection |
| Allocate only toward sleeves below their lower bands | `eligible_sleeves()` reads `band_state == underweight` |
| Owner selects the ticker within each sleeve | `selections` is required; a sleeve with no choice is refused, never filled in |
| Whole-share and fractional modes | Delegated to `build_allocation_plan`, the same sizer the preview uses |
| Show residual unallocated money | `SteeringPlan.unallocated_exact`, displayed |
| Separately approved proposals | One `TradeProposal` per sleeve, each through `_render_proposal_approval` |
| No submit-all | None exists; pinned by a UI test |
| Never silently omit an unaffordable leg | Named in `disclosures` with the remedy |
| Bound to the allocation-profile fingerprint | Fingerprint is part of both the proposal id salt and the idempotency key |
| Stale cards hidden | Signature covers profile fingerprint, snapshot date, equity, ticker choices, budget, and per-sleeve pending values |

Design decisions worth pressing on in review:

- **Sized to the LOWER EDGE, not the target.** The band's purpose is that
  being inside it is enough; steering to the target spends more than the
  profile asks and hands back the turnover the band exists to avoid.
- **Cash and the residual can never receive money**, whatever their band says.
  Cash is the budget's source; the residual is by definition the holdings the
  profile does not describe, so buying toward it would be buying toward a
  target that names nothing.
- **An overweight sleeve produces nothing at all** — not a reduced buy, not a
  suggestion. Selling to rebalance is Stage 3 and needs separate
  authorization.
- **Budget is split proportionally to each sleeve's shortfall and capped at
  it**, so no sleeve is steered past its lower edge. Leftover money is
  reported, never pushed onto another sleeve to make the number come out even.
- **Eligibility is measured on the projected weight**, so money already
  working in an unfilled order counts. Sizing against the current weight is
  how the hedge sleeve once prepared a duplicate correction (HEDGER-004).

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- `tests/test_rebalance_steering.py`: **26 passed** (new).
- `tests/test_portfolio_rebalance.py`: **71 passed** (69 before).
- `tests/test_ui_portfolio_rebalance.py`: **16 passed** (11 before).
- Mutation verification: **8 mutations, 8 detected** — 2 against the
  band-state fix, 6 against Stage 2, including eligibility widening to
  overweight sleeves, cash and the residual becoming destinations, sizing to
  the target instead of the edge, silent omission of an unchosen sleeve,
  silent omission of an unaffordable leg, and dropping the profile
  fingerprint from proposal identity.
- Full settled tree: recorded in `docs/SESSION_HANDOFF.md`.

Two of those mutations only worked on the second attempt: the first
"unchosen sleeve" mutation left the refusal in place and so changed nothing
observable, and the first Stage 1 residual mutation had the same shape. A
mutation that does not actually create the dangerous behaviour proves
nothing about the test.

## Untested and out of scope

- Nothing here touches a real broker, order, or paper account.
- **No evidence supports the target shape.** Fixtures prove software
  behaviour; this project has confirmed no signal as real edge, and the
  wide-band result behind the mechanism was measured on the SOXX/SOXL pair.
- Stage 3 (tax-aware trims) is not started and needs separate explicit
  authorization, because it is where rebalancing first sells on the app's own
  initiative.
- This work is development-only. It authorizes no deployment, epoch roll,
  scheduler change, operator-database mutation, or live trading. Deploying
  would change `code_commit` and close active `paper-epoch-005`.

## Observation for the reviewer, not acted on

`test_sell1_current_records_do_not_reopen_merged_review_work` bans the
literal phrase **"Independent review of this branch"** anywhere in
`SESSION_HANDOFF.md`. That phrase is generic: it is the natural sentence for
any handoff whose branch has not yet been reviewed, which is the ordinary
state of every feature branch. It collided with this handoff and will collide
with the next one.

That is the same failure mode the module's own docstring records about this
guard's first version — *"the guard reddened on the very next feature and the
obvious 'fix' would have been to weaken it"* — and the rule it states is that
a banned literal must be a claim that can never be true again, not one that
must stay true.

I reworded the handoff instead of touching the guard, because weakening a
test to make my own text pass is exactly what `CLAUDE.md` §9 forbids, and
because the judgement about whether SELL-1's protection still needs that
literal belongs to whoever owns the guard. If the intent is "SELL-1's record
must not reopen SELL-1", the ban would be safer scoped to a SELL-1-specific
phrase, as the sibling assertion on the ledger row already is.
