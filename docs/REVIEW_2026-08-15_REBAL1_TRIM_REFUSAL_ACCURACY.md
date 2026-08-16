# REBAL-1 Stage 3 — the trim refusal stated a reason that was not true

Date: 2026-08-15
Author: Claude
Base: `a0a657b` (the feasibility-visibility round)
Branch: `user/claude/rebal-trim-refusal-accuracy-20260815`
Status: **Implemented; pending independent review.**

## How it was found

The owner opened the Stage 3 trim section on a real book and reported:

> "mine shows: No sleeve is above its upper band, so there is nothing to
> trim."

The same page, three subheadings higher, reported **Bands breached: 6**.
Both statements cannot be true.

## The defect

`overweight_sleeves()` filters on two independent conditions in one pass —
*above the upper band* AND *trimmable* — and returns a single list. An empty
result therefore cannot tell a caller which condition failed, and the UI
reported only one of the two.

Reproduced deterministically, holding one unsleeved position plus cash:

```
cash                     proj= 50.00%  band  7.50-12.50  band_state='overweight'
dividend_income          proj=  0.00%  band 11.25-18.75  band_state='underweight'
growth                   proj=  0.00%  band 30.00-50.00  band_state='underweight'
leveraged_reinvestment   proj=  0.00%  band 11.25-18.75  band_state='underweight'
hedge                    proj=  0.00%  band  7.50-12.50  band_state='underweight'
other_unassigned         proj= 50.00%  band  7.50-12.50  band_state='overweight'

overweight_sleeves()      -> []
above the upper band      -> ['cash', 'other_unassigned']
```

**The refusal was correct; only its stated reason was false.** Cash is not a
holding, and the residual is the set of positions the profile does not
describe, so trimming there is exactly the reading Stage 1 forbids. Nothing
about which sleeves may be trimmed has changed.

That distinction is the whole point. A refusal that misreports why it fired
is indistinguishable from a broken feature, and this workflow has already
lost two rounds to that shape: ST3R-001 and ST3CCR-001 both refused every
trim while reading like careful safeguards. This is the same family seen
from the reader's side rather than the code's.

## The change

`untrimmable_overweight_sleeves(report)` answers the second question on its
own. The page now distinguishes:

* sleeves over the band but never trimmable — names them, and says why cash
  and the residual are excluded; and
* nothing over the band at all — keeps the original sentence, which is true
  in that case and only that case.

## Two mistakes of mine that this round exposed

**1. An existing test pinned the false message.**
`test_the_trim_section_appears_only_when_a_sleeve_is_overweight` deliberately
forced a book where cash is the only overweight sleeve — precisely the
owner's situation — and asserted `"nothing to trim" in rendered`. Its
docstring congratulates itself for forcing the book rather than assuming it.
The setup was right and the expectation was wrong, so the defect was tested
*in*. Replaced with the accurate assertion, plus the existing
no-sell-control guarantee.

**2. The first fix could have moved the lie rather than removed it.**
A mutation reporting the untrimmable reason for *every* empty case survived
the first version of these tests. It would have told an owner whose book is
exactly on target that cash and the residual are above their bands. A test
forcing an exactly-on-target book — 10/15/40/15/10/10 of a $10,000 book —
now pins the other cause.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- `tests/test_rebalance_trim.py` and `tests/test_ui_portfolio_rebalance.py`:
  **76 passed** (50 + 26; 48 + 24 before).
- Mutation verification: **4 mutations, 4 detected** — restoring the false
  message, moving it to the other case, ignoring `band_state` in the new
  helper, and inverting its membership test.
- Full settled tree: recorded in `docs/SESSION_HANDOFF.md`.
- `compileall` and `git diff --check` clean. `assistant/rebalance_trim.py`
  had eighteen bare-LF lines from scripted editing and was normalized to
  CRLF; the mutation run that first exposed it failed to apply and was
  correctly reported as not-applied rather than as a survivor.

## Untested and out of scope

- Nothing here touches a real broker, order, or paper account.
- **No test drives the Streamlit trim button through to a saved proposal.**
  Unchanged by this round.
- **No evidence supports the target shape.** An accurate refusal message
  does not make the targets right; they remain owner preference.
- Development-only. Authorizes no deployment, epoch roll, scheduler change,
  operator-database mutation, or live trading. Deploying would change
  `code_commit` and close active `paper-epoch-005`.
