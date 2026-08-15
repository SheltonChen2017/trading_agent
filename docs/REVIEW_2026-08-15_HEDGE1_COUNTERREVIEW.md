# Claude counter-review — Codex's correction of the HEDGE-1 defensive sleeve

Date: 2026-08-15
Reviewer: Claude
Base reviewed: `17be33b` (HEDGE-1 as merged to `main` by PR #223)
Commits under review: `46e1248` (product/test correction), `b37aa44` (records)
Counter-review branch: `user/claude/hedge1-counterreview-20260815`
Disposition: **Codex's correction accepted; four further defects found and
closed, one finding partially corrected**

## Scope and method

Codex reviewed and corrected HEDGE-1, which I implemented. This document
reviews Codex's correction, not my original commit: every changed hunk in
`46e1248`, the three tests it added, the two it rewrote, the Streamlit
changes, and the records commit `b37aa44`.

Method, per `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`:

* every commit in the range received an explicit disposition;
* each of Codex's eight findings was **re-derived against the submitted tree**
  in a throwaway worktree at `17be33b`, not accepted on the report's word;
* each correction was proven load-bearing by reverse mutation — revert the
  fix, confirm exactly the intended test reddens, restore;
* Codex's new tests were themselves mutation-tested, which is how the one
  unpinned fix was found; and
* each confirmed defect was searched for generalized instances.

No database write, scheduled-task change, deployment, epoch transition, order,
broker request, or funded-account access occurred. A temporary git worktree
was created outside the repository and removed (IPRCR-002: a leftover review
worktree once broke pytest collection). `refs/remotes/origin/main` was moved
locally for two simulations and restored, verified by SHA both times; no
remote ref was touched.

## Commit-by-commit disposition

| Commit | Author | Disposition | Result |
|---|---|---|---|
| `46e1248` | Codex | **Accepted after correction** | Seven of eight findings are real and reproduce exactly on the submitted tree; the eighth is right in direction with a stated arithmetic that does not reproduce. Two of the corrections introduce new defects of their own, one of them a P2. |
| `b37aa44` | Codex | **Accepted after correction** | The epoch-lineage correction is important and right. The new topology guard it relies on cannot stay green and is corrected here. |

## Codex's findings, independently re-derived

Every one of these was reproduced on a worktree at the submitted tree
`17be33b` before being accepted.

**HEDGER-001 (P2) — confirmed.** `evaluate_hedge_sleeve(..., tickers=["AAPL"])`
returned a usable report with `tickers=('AAPL',)` and a $1,000 shortfall. The
UI never offered it, but the module presented configuration as authoritative
while not enforcing it.

**HEDGER-002 (P2) — confirmed, both halves.** A `market_value_exact` of
`"not-a-number"` silently fell back to the rounded display float and reported
`hedge_value=400`. Separately, a position of 2 shares with exact value `"0"`
was counted as zero exposure and produced the full $1,000 shortfall. Both
understate the sleeve and oversize the buy.

**HEDGER-003 (P2) — confirmed, and my worst defect in this feature.** With
BTAL unpriced, the submitted code proposed GLD/SH/TLT reweighted to 33.3%
each: the owner selects four instruments and silently receives three. With
BTAL merely unaffordable, the same silent three-leg basket appeared. Codex's
all-or-nothing rule is correct.

**HEDGER-004 (P2) — confirmed, and the most operationally dangerous.** With a
known $400 SH buy already working, the submitted evaluator still reported the
full $1,000 shortfall. Clicking twice would have prepared roughly double the
intended hedge.

**HEDGER-005 (P3) — partially correct.** The direction and the fix are right
and I have kept them, but the stated evidence does not reproduce: Codex wrote
that "`100 / 3` float weights could exceed the stated total by representation
error", and `100.0/3*3 == 100.0` exactly, because the rounding cancels. The
excess is real one step later, in the summed per-ticker target dollars
(`1000.000000000000071` against a $1,000 budget). Its magnitude is ~7e-14
dollars, far below the share-flooring threshold, so no runtime test can
observe it — which is exactly why the fix went unpinned. See HEDGE1CR-005.

**HEDGER-006 (P2) — confirmed, and the most important finding against my own
work.** My handoff said HEDGE-1 "carries no deployment-closes-the-epoch
consequence of its own" because neither fingerprint changed. Traced to source:
`build_paper_lineage()` makes `code_commit` a first-class lineage field, and
`assistant/paper_evidence.py` refuses drill evidence when "the drill runtime
commit is X, but the active evidence epoch is bound to Y". Deploying HEDGE-1
would change the runtime commit and close epoch-005 regardless of the stable
mandate and policy hashes. My sentence could have been read as clearance to
deploy during the owner's 60-day hold. Codex's rewording is accurate.

**HEDGER-007 (P3) — confirmed.** Both records still called `85338fc` current
main after PR #223 moved it to `17be33b`. The correction is right; the guard
added alongside it is not — see HEDGE1CR-001.

**HEDGER-008 (P3) — confirmed.** My module docstring said "Nothing here
creates, approves, sizes, submits, cancels, or replaces an order" while
`generate_hedge_buy_proposals()` plainly creates and sizes proposals. The
sentence contradicted the function directly beneath it.

## Prioritized issue ledger — this counter-review

| ID | Priority | Status | Location | Evidence and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| HEDGE1CR-001 | P2 | Closed | `tests/test_active_document_consistency.py` | `test_current_topology_hashes_match_the_published_mainline` asserts the records name the CURRENT `origin/main`. That can never stay satisfied: merging the branch that updates the records creates a merge commit, so the declared hash is one behind the instant it lands, and a records-only follow-up merges as another commit and is stale again. `main` itself would carry the red test. It also contradicts this module's own docstring rule — "never one that must stay true". | Assert the declared hash is REACHABLE from the mainline rather than equal to its tip. That still catches what HEDGER-007 was about (a fictional, mistyped, or branch-only hash) without asserting recency, which cannot be asserted from inside the commit being merged. | Simulated a merge by pointing `origin/main` at a synthetic merge commit: the original guard FAILED, the replacement PASSED. A fabricated hash (`deadbee`) still fails the replacement. `origin/main` restored and verified by SHA after each run. |
| HEDGE1CR-002 | P2 | Closed | `assistant/hedge_sleeve.py` | The `open_orders_available` refusal is correctly gated on `not report_only`; the sibling `unknown_pending` refusal is not. Any plain market buy on a sleeve ticker therefore turned the page's DEFAULT state — no target typed — into a red error reading "refusing to size another purchase", when nothing had been asked for. Report-only mode exists precisely so a first visit is not a refusal. | Gate it the same way. In report-only the same fact becomes a disclosure explaining why the projected weight is incomplete; with a target supplied it still refuses. | Regression covers both modes; reverting the gate reddens exactly that test. |
| HEDGE1CR-003 | P3 | Closed | `assistant/hedge_sleeve.py` | The new `shares <= 0` refusal treats a zero-share, zero-value row as an unreadable holding. `build_portfolio_snapshot` constructs exactly such a row through its documented API, and the result blocked the entire page including the read-only view of the current weight, with no remedy. The message also called a value "unreadable" that was read perfectly well and was zero. | A zero-quantity, zero-value row is the not-held case and reads as such. A positive quantity worth zero — HEDGER-002b's real defect — still refuses, and is now named "impossible" rather than "unreadable". | Two regressions, one per direction; reverting either fix reddens exactly its own test. |
| HEDGE1CR-004 | P3 | Closed | `assistant/hedge_sleeve.py` | HEDGER-003 turned a silent degradation into a hard block, which makes the way out matter: neither all-or-nothing refusal named one. The owner is told the basket cannot be sized and not that deselecting the instrument, raising the target, or enabling fractional shares would resolve it. This is the same defect class as SET1CR-001, which Codex accepted earlier. | Both refusals now name the authorized remedies. | Regression asserts the remedy text and the absence of doubled punctuation; removing it reddens the test. |
| HEDGE1CR-005 | P3 | Closed | `tests/test_hedge_sleeve.py` | HEDGER-005's Decimal fix was unpinned: reverting the equal-weight split to `100.0 / len(...)` left all 50 tests green. The error is ~7e-14 dollars, below the flooring threshold that could make it observable, so no behavioral test can catch it. | A source-level guard, which `CLAUDE.md` §9 permits exactly when the invariant is not runtime-observable, and which this repository already uses for the `Decimal(str(...))` ban. | Reverting the split to float reddens the new guard. |

Issue total: **0 P0 / 0 P1 / 2 P2 / 3 P3; all closed; 0 open.**

## Codex's work verified sound and retained

* The instrument allowlist, the exact-value authority rule, the
  complete-basket contract, and the pending-exposure subtraction. All four
  close real defects and all four are load-bearing under reverse mutation.
* The `estimate_pending_buy_value_by_ticker` seam. I suspected its
  `float(value)` return would reintroduce binary error into the shortfall,
  and checked: `assistant/money.to_decimal` uses `Decimal(str(value))`, which
  recovers the human-visible amount exactly for any dollar figure under
  ~17 significant digits. No finding.
* The surplus wording when pending buys push the projected sleeve past
  target. It reports holdings, pending value, projected weight, and the
  overshoot separately, and still refuses to sell.
* The epoch-lineage correction (HEDGER-006), which is accurate against
  `build_paper_lineage()` and the drill-evidence check.
* Rewriting my two contradicted docstring and guide claims (HEDGER-008).
* Codex's rewrite of the unpriced-instrument test into its refusing form is a
  legitimate contract change, not a weakened test: it asserts strictly more
  and is accompanied by the reasoning.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.
(Codex used `C:\git\trading_agent_venv` after reporting the repository `.venv`
was not launchable in its session; the repository `.venv` launched normally
here and is the environment for every number below.)

* `tests/test_hedge_sleeve.py`: **55 passed** (50 before).
* `tests/test_active_document_consistency.py`: **30 passed**.
* Focused adjacent set — hedge module, hedge UI, document consistency,
  allocation proposals, ML import boundary: **130 passed**.
* Mutation verification: **9 against Codex's corrections** (8 detected, the
  9th being the unpinnable Decimal fix now closed as HEDGE1CR-005), and
  **7 against my own** (5 module mutations plus both directions of the
  rewritten topology guard), each detected by exactly the intended test.
* Full suite result for the exact final tree is recorded in
  `docs/SESSION_HANDOFF.md`.

## Untested and out of scope

* Nothing here exercises the real Alpaca paper account, a real hedge order,
  or the real price behaviour of these instruments.
* **No evidence establishes that the hedge works.** Fixtures prove software
  behaviour only. This project has confirmed zero signals as real edge and has
  measured nothing about drawdown reduction for this basket.
* Options, futures, short selling, automatic rebalancing, and live execution
  remain out of scope.
* This counter-review authorizes no deployment, scheduler change, epoch roll,
  database mutation, funded-account access, or live trading. Deploying
  HEDGE-1 would change `code_commit` and close active `paper-epoch-005`.
