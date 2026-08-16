# REBAL-1 — making target feasibility visible without horizontal scrolling

Date: 2026-08-15
Author: Claude
Base: `84e73af` (PR #230, the combined Stage 3 chain)
Branch: `user/claude/rebal-feasibility-visible-20260815`
Status: **Accepted after independent correction `3a506ae`; not deployed.**

## Why this round exists

The owner exercised the Portfolio Rebalancing page in the development app and
reported two things in sequence:

1. "Bands breached: 6 ... didn't find 'Target reachable'."
2. "There is no horizontal roll."

The first was not a defect. I had predicted five breaches from a stale
calculation made before REBAL1CR-002, which is precisely the change that
stopped a display status from masking a real band breach. Six is correct: the
residual sleeve sits far above its band and now reports `band_state =
overweight` while its `status` stays `unassigned_holdings`. **The app was
right and I was wrong**, and the owner's own arithmetic on the four sleeves
they checked was right too.

The second was a real defect. "Target reachable" was the ninth and last
column of a nine-column table, and Streamlit did not give that table a
horizontal scrollbar at the owner's window width. The one column stating
whether the targets can be reached at all was therefore unreachable itself —
an unusually bad place for a column to be truncated.

## The failure direction that matters

The conflict text was never lost: `evaluate_portfolio_rebalance` also puts
each conflict into `report.disclosures`, which the page renders as warnings
above the table. So an *infeasible* profile was still shouted about.

The dangerous direction was the opposite one. When every target IS reachable
the page said nothing at all, and a reader had to infer feasibility from the
absence of a warning they had never seen fire. An absence is not a statement,
and this project has been caught before by a safeguard that is
indistinguishable from a broken one when both look like silence.

## The change

Presentation only. No computation, refusal, threshold, count, or contract
moved.

- Feasibility is stated **below** the drift table, where table width cannot
  hide it. When any target is unreachable, a bordered block names each
  affected sleeve with its exact conflict reason and repeats the rule that a
  band around an unreachable target is fiction. When all of them are
  reachable, the page says so explicitly and names the active policy file.
- The per-row column survives, shortened from "Target reachable" to
  "Reachable" and reduced to yes/no, so the fact stays adjacent to the row it
  describes while taking a fraction of the width. The reason now lives in the
  block below rather than inside a cell.
- Column ORDER is deliberately unchanged. The owner is mid-way through
  testing this page, and silently reshuffling it would cost more than it
  buys now that the statement below the table cannot be truncated.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- `tests/test_ui_portfolio_rebalance.py`: **24 passed** (21 before).
- The conflict branch is driven through the REAL conflict rule rather than a
  stub: the test replaces the loaded policy with one capping total exposure
  at 50% — the operational policy's actual value — against the approved
  profile's 90% invested target, and asserts the rendered text.
- Mutation verification: **3 mutations, 3 detected.**
- Full settled tree and compilation results: recorded in
  `docs/SESSION_HANDOFF.md`.

**One mutation initially survived, and it is the finding of this round.** I
removed the sleeve label from each conflict line, leaving only the reason,
and every test still passed. Naming the sleeve is load-bearing: the
total-exposure conflict applies to *every* funded sleeve simultaneously, so
an unlabelled list is the same sentence repeated five times with no way to
tell which sleeve each belongs to. The test now pins `**Growth**`, which also
distinguishes this block from the raw-key disclosure warning (`growth: ...`)
the report already emits. A test that asserts a message appeared is not the
same as a test that asserts the message is useful.

## Independent review addendum

Codex reviewed every commit in the owner-named range
`84e73af..006a9d5`, not only the merged tip. The presentation behavior is
accepted, but the submitted tests contained one collected function with no
executable body and one assertion that accepted either the positive or the
negative feasibility branch while claiming to prove the positive case. The
correction removes the no-op, forces a known permissive policy for the
positive case, and drives all four implemented conflict rules through the
real report and Streamlit UI, including the per-row `Reachable` value.

The complete dispositions and P0-P3 ledger are in
`docs/REVIEW_2026-08-15_REBAL3V_REBAL3W_INDEPENDENT.md`. No feasibility
calculation, policy limit, band state, breach count, refusal, proposal, or
execution path changed in review.

## Untested and out of scope

- Nothing here touches a real broker, order, or paper account.
- **No test drives the Streamlit trim button through to a saved proposal.**
  That gap, recorded in the end-to-end round, is unchanged by this one.
- **No evidence supports the target shape.** Making feasibility legible does
  not make the targets right; they remain owner preference.
- Development-only. Authorizes no deployment, epoch roll, scheduler change,
  operator-database mutation, or live trading. Deploying would change
  `code_commit` and close active `paper-epoch-005`.
