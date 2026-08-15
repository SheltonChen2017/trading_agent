# REBAL-1 Stage 3 — end-to-end coverage against real journaled fills

Date: 2026-08-15
Author: Claude
Base: `c48861e` (Stage 3 counter-review)
Branch: `user/claude/rebal1-e2e-real-fills-20260815`
Status: **Implemented; pending independent review.**

## Why this round exists

Three consecutive rounds of Stage 2 and Stage 3 failed the same way, and no
existing test could have caught any of them:

| Round | Defect | Why the tests missed it |
|---|---|---|
| Stage 2 | `Decimal` in `reference_price` crashed `save_proposal` | tests asserted on in-memory fields and never persisted |
| Stage 3 | read a per-ticker `complete` key that never existed, so every trim was refused | fixture was a hand-written shape, never obtained from the real provider |
| Stage 3 counter-review | required global coverage, which no book with a pre-app holding satisfies | same fixture problem, one layer along |

Every one was an interface-shape mistake. A fixture written from an
assumption cannot detect that the assumption is wrong.

The owner asked for the end-to-end test that closes this. Writing it
immediately found a fourth instance — in my own previous fix.

## What the test drives

`tests/test_rebalance_trim_end_to_end.py` invents no shapes. Fills are
journaled through `journal_broker_order_update`, exactly as the app records a
real fill; the ledger and coverage come from the real providers; the proposal
is persisted through `AssistantStore.save_proposal` and reloaded; and
approval runs through the real validation path. The only stubs are the broker
seam and the clock.

Writing it required reading two real contracts rather than guessing them, and
I guessed wrong on the first: `project_broker_order_event` needs `order_id`
and `proposal_id`, not the `id` an order dict carries elsewhere; and
`list_fills` derives ticker and side from the LINKED PROPOSAL's intent, so a
fill exists only once both the proposal and its order event do.

## The fourth instance, found by the new test

`tax_ledger_with_coverage` returns `(ledger if complete else None, ...)`. It
withholds the ledger **entirely** when any holding is unreconciled — that is
its documented contract, and it is correct for a portfolio-wide tax report.

My ST3CCR-001 fix scoped the caller's `matched` check to the trimmed ticker
and I verified it against a hand-built dict pairing a real ledger with
`complete: False` — a combination the real provider never emits. Against the
real provider there is no ledger at all, so `plan_trim` still refused on
`tax_lot_ledger is None`, and **Stage 3 was still unusable on any book with a
pre-app holding.** I made precisely the mistake I had just written up twice.

## The fix

A new sibling, `ticker_tax_ledger_with_coverage(store, portfolio, ticker)`,
rather than a loosening of the shared function. The two answer different
questions:

* `tax_ledger_with_coverage` — "can this whole book be taxed accurately?"
  Withholding the ledger on partial history is right, and unchanged.
* `ticker_tax_ledger_with_coverage` — "can THIS ticker's lots be accounted
  for?" A trim sells one ticker and its realized gain depends on that
  ticker's lots alone.

The scoped coverage keeps the same shape so callers read it identically, with
`complete` scoped to the requested ticker and `portfolio_complete` carrying
the book-wide answer for disclosure. An uncovered ticker still receives no
ledger. All three call sites — `plan_trim`, the execution-time revalidation,
and the Stage 3 UI — now use it.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- `tests/test_rebalance_trim_end_to_end.py`: **10 passed** (new).
- `tests/test_rebalance_trim.py`: 48 passed; UI 20 passed.
- Mutation verification: **3 mutations against the new provider, 3
  detected** — refusing to rebuild the withheld ledger, un-scoping
  `complete`, and letting an unmatched ticker through.
- Full settled tree result: recorded in `docs/SESSION_HANDOFF.md`.

One mutation initially appeared to survive and did not: it had silently
failed to apply because the anchor used `\n` against a CRLF file. A mutation
that does not change the code proves nothing, and that is the second time
this session a no-op mutation nearly became a false clean bill.

## What is still not covered

- **No test drives the Streamlit trim button end to end.** The UI tests
  assert the controls' disabled state and the section's text; they do not
  click through to a saved proposal. That is the remaining gap of the same
  family, and it is the one I would close next.
- The broker seam and the clock remain stubbed; nothing here contacts a real
  broker or paper account.
- **No evidence supports the target shape.** These tests prove the software
  behaves as described, not that trimming toward the profile is a good idea.
- Development-only. Authorizes no deployment, epoch roll, scheduler change,
  operator-database mutation, or live trading.
