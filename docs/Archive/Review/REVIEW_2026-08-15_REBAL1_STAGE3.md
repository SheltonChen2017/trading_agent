# REBAL-1 Stage 3 — tax-aware trims of overweight sleeves

Date: 2026-08-15
Implementation author: Claude
Independent reviewer: Codex
Base: `45faf1c` (Stage 2 counter-review merged by PR #229)
Branch: `user/claude/rebal1-stage3-tax-aware-trims-20260815`
Submitted remote head: `bedeea2bd6a5c6639bff071ac18c8714cda1b8c3`
Review branch: `codex/review-rebal1-stage3-20260815`
Correction: `ed6879d5c56ecfa5435b5b73dc661f038add11d5` (local only)
Status: **Accepted after independent correction; not pushed, merged, or deployed.**

## Independent review scope and disposition

The review began only after fetching Claude's pushed remote branch and fixed
the scope at base `45faf1c`, ordered range `0490d9d..bedeea2`, and exact remote
head `bedeea2`. The remote range contained exactly two commits:

| Commit | Disposition | Reason |
|---|---|---|
| `0490d9d` | Accepted after correction | The core Stage 3 design and safety direction are sound, but its real coverage integration made every trim unusable and eight material edge/binding contracts needed correction in `ed6879d`. |
| `bedeea2` | Accepted after correction | The records accurately describe the intended design, but incorrectly claimed the submitted UI left all four choices unset and overstated production readiness; this final report, action plan, milestone record, and handoff supersede those claims. |

The target-restoration ceiling is accepted: it is the owner-adopted bound and
prevents a trim from manufacturing an immediate Stage 2 shortfall. Requiring a
complete ledger is also accepted because this workflow's defining promise is
to show the tax consequence; ordinary risk-reducing and owner-directed sells
remain available elsewhere when lot coverage is incomplete. Lot selection
remains explicitly advisory to Alpaca. The review added a current-ledger
fingerprint check before broker import so a fill, split, or consumed lot after
proposal creation forces regeneration rather than leaving the owner to approve
stale basis information.

## Independent issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| ST3R-001 | P2 | Closed | `0490d9d` | `assistant/rebalance_trim.py:plan_trim` | The real app refused every trim even with complete coverage because Stage 3 expected per-ticker `complete`, while the production provider emits global `complete` plus per-ticker `matched`. | A regression using `tax_ledger_with_coverage()` returned a complete ledger and still failed on the submitted tree. | This broke the feature's only action path and its definition of done. | Consume the actual global/per-ticker coverage contract and replace the invented fixture shape. | Red in the initial six-failure review run; green in the 243-test focused run. |
| ST3R-002 | P2 | Closed | `0490d9d` | `scripts/personal_assistant_ui.py` | The sleeve picker auto-selected the first overweight sleeve although the report and module said all four owner decisions start unset. | AppTest observed `Growth`, not `-- choose --`. | The app was making one of the four decisions it promised never to make. | Add a non-choice sentinel and keep the button disabled until sleeve, ticker, quantity, and strategy are explicit. | Red in the initial six-failure run; green AppTest. |
| ST3R-003 | P2 | Closed | `0490d9d` | Stage 3 UI quantity input | Fractional mode passed Streamlit's binary `float` into an exact boundary that intentionally rejects floats, so fractional Stage 3 could not create a plan. | Source path plus AppTest: no exact fractional text control existed. | The active SET-1 fractional policy was advertised but unusable on this sell path. | Use exact decimal text and canonical quantity validation; retain the whole-share control in strict mode. | Red in the initial six-failure run; green AppTest and focused suite. |
| ST3R-004 | P2 | Closed | `0490d9d` | `TrimPlan.pending_sell_value_exact` and UI | The field promised a working sell but carried signed net pending exposure (`-2000`, or `-1500` after a simultaneous buy) and was never rendered. | Two regressions reproduced both wrong values. | A required owner-visible consequence was missing and financially mislabeled. | Compute positive gross priced sells by sleeve, store them, and render a Working sells metric; projected band arithmetic remains signed/net. | Both regressions red then green. |
| ST3R-005 | P2 | Closed | `0490d9d` | proposal durability/idempotency | Tax lots and realized consequence were absent from durable expected impact and proposal identity, so a reconciled ledger could generate a different card that collided with the older stored proposal ID. | Two complete ledgers with different basis produced one ID and no durable lot list. | The owner could see new tax numbers while execution loaded an older stored decision. | Persist per-lot consequence and hash it into proposal identity. | Red in the initial six-failure run; green identity regression. |
| ST3R-006 | P2 | Closed | `0490d9d` | `plan_trim` / `unrealized_by_lot` | Plan classification used independent wall clocks while the durable proposal accepted an injected clock, allowing holding-period labels and short/long totals to disagree at the one-year boundary. | Source comparison showed two `datetime.now()` calls outside the proposal clock. | Tax-term classification is financially material and one proposal must describe one instant. | Thread the proposal time through planning and per-lot presentation. | Boundary regression green with a fixed clock; full tax-lot suite green. |
| ST3R-007 | P2 | Closed | `0490d9d` | `assistant.tax_lots.select_lots` | Named-lot selection accepted a duplicate lot ID and counted the same shares twice. | Dedicated regression failed to raise on `['f1', 'f1']`. | The direct Stage 3 API advertised named lots and could show false basis coverage. | Reject duplicate specific-lot IDs. | Dedicated regression red then green. |
| ST3R-008 | P2 | Closed | `0490d9d` | execution context binding | Approval-time validation rechecked the allocation profile but not the complete tax-lot ledger, despite incomplete coverage blocking proposal creation. | Changed-ledger and missing-fingerprint regressions reached broker configuration on the submitted tree instead of refusing pre-broker. | A later fill, split, or consumed lot could make the displayed tax consequence stale at approval. | Bind an open-lot fingerprint in the proposal and revalidate complete current coverage/fingerprint through the characterized execution dependency before broker import. | Two regressions red then green; facade characterization and 4,026-test full suite green. |
| ST3R-009 | P3 | Closed | `0490d9d` | UI imports | Claude's diff imported the same steering fingerprint twice. | Commit diff/source inspection. | Duplicate imports obscure dependency review on a high-risk page. | Remove the duplicate. | Compilation and diff checks clean. |

No P0 or P1 issue was found. No review issue remains open.

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
   `docs/operations/MANDATE.md` rates tax sensitivity High for that reason.
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

## Submitted validation (Claude)

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
- **Lot selection is advisory.** The app records which lots the chosen
  strategy would consume; it does not instruct the broker to use them, and
  the proposal says so.
- The realized gain is an estimate against the displayed reference price, not
  a settlement figure.
- **No evidence supports the target shape.** Trimming realizes tax now in
  exchange for a portfolio shape this project has not shown to be better.
- Development-only. Authorizes no deployment, epoch roll, scheduler change,
  operator-database mutation, or live trading. Deploying would change
  `code_commit` and close active `paper-epoch-005`.

## Final independent validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- Baseline submitted head: 56 focused tests passed.
- Material red evidence: the initial review regression run produced six
  expected failures; duplicate named lots and both stale-ledger execution
  cases were separately demonstrated red.
- Final focused set: **243 passed in 30.77 seconds** across Stage 3, its UI,
  shared tax lots, Stage 2 profile binding, and execution characterization.
- Final settled tree: **4,026 passed / 0 failed / 25 known dependency warnings
  in 606.37 seconds**.
- `compileall`: clean. `git diff --check`: clean.
- Product/test correction: `ed6879d`; documentation/handoff commit follows
  separately and remains local until the owner authorizes a push.

Safety disposition: paper mode, exact typed approval, kill switches, atomic
claiming, reservations for ambiguous outcomes, idempotency, reconciliation,
and import-authority boundaries were unchanged. The only execution-kernel
contract change adds the Stage 3-specific current-ledger context arguments and
still runs before broker import; characterization and the full suite passed.
No broker account, order, operator database, scheduler, deployment, or epoch
state was accessed or mutated during review.
