# Session handoff — owner-directed sell implemented (M3 review complete)

Prepared: 2026-08-13. Two independent threads ran this session: the
three-sleeve M3 review loop closed, and a new owner-requested Selling-tab
capability was implemented on its own branch.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md` (rows AP-11, SELL-1, GR-7d)
3. `docs/REVIEW_2026-08-13_THREE_SLEEVE_M3.md` including its counter-review
   section
4. `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` §1.1 / §5 M3
5. `docs/OPERATIONAL_FACTS.md`
6. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`

The action plan remains the sequencing authority. Nothing here authorizes
deployment, an epoch roll, M4, live trading, or any funded action.

## 1. Repository topology

- `main` / `origin/main`: `60ed001` (PR #200 merge).
- **Thread A — three-sleeve M3**, branch
  `user/claude/three-sleeve-m3-earmarks-20260813` (`7ee4786`), reviewed by
  Codex on `codex/review-three-sleeve-m3-20260813` (correction `b6685b5`,
  documentation `55b4518`) and counter-reviewed by Claude on the same review
  branch. Both branches are pushed; the owner's merge is the remaining
  action. Merge the review branch (it contains M3 plus its corrections).
- **Thread B — owner-directed sell**, branch
  `user/claude/user-directed-sell-20260813`, created from `60ed001`. It does
  NOT depend on M3 and shares no code with it; it was deliberately branched
  from `main` rather than stacked, so either can merge first. Both touch
  `scripts/personal_assistant_ui.py` and `scripts/run_personal_assistant.py`
  in different page/subparser regions — expect a trivial textual conflict at
  most, in different functions.

## 2. Thread A — M3 review outcome and counter-review

Codex found **2 P1 and 4 P2**, all fixed in `b6685b5`; full ledger in the
review report. Claude's counter-review confirmed every one by mutation and
closed two further findings. The two P1s were real defects in the submitted
implementation and are worth remembering:

- **M3REV-001:** `_has_fill_evidence` read only the incremental `fill_qty`,
  but poll reconciliation records only the cumulative `filled_qty` (the
  repository's own `list_recorded_fills` docstring states this). A poll-only
  partial fill followed by cancellation therefore looked like zero fill
  evidence and released dividend dollars that had actually been spent.
- **M3REV-002:** fill evidence was consulted only for `canceled` /
  `broker_expired`, so a fill followed by `broker_rejected` released the
  whole earmark. The corrected rule — recorded spending outranks every
  lifecycle label, known or not — is strictly more conservative.

Claude's counter-review findings, both resolved on the review branch:

- **M3CR-001 (P2):** the disposition table had no exhaustiveness contract.
  `override_available` is the sharp edge — the kernel leaves a proposal there
  precisely so a human can re-invoke with `override_policy_violations=True`,
  so its dollars are still spendable, yet it reads like a stopped validation
  and held only via a default branch. Added guards expressed as relationships
  over the canonical status vocabulary (every in-flight status plus
  `proposed`/`override_available` must hold; nothing releases once fill
  evidence exists) so a future status inherits the rule.
- **M3CR-002 (P2):** with the fence no longer trusting a caller-supplied
  income total, `storage.py` repeats the account name as the SQL literal
  `'INCOME:DIVIDENDS'` (it cannot import `portfolio_ledger` — a cycle) while
  the module reads `ACCOUNT_DIVIDEND_INCOME`. Nothing pinned their agreement
  and the drift direction is silent and unsafe. Pinned behaviorally at the
  exact boundary.
- **M3CR-003 (P3, recorded not fixed):** the same two-column fill duality
  exists in `storage.py::get_execution_budget_usage`, whose `filled_notional`
  under-reports poll-only fills. Pre-existing, reporting-only (the caps are
  enforced on `submitted_notional`), and outside M3's scope.

## 3. Thread B — owner-directed sell (SELL-1)

Owner request, verbatim in intent: the Selling tab only ever proposed sells
on a deterministic policy breach; the owner asked to be able to sell an
individual currently-held position directly.

- `assistant/user_directed_sell.py`:
  `generate_user_directed_sell_proposal(...) -> {"created": bool, ...}` and
  `sellable_whole_shares(...)`. Evidence status `user_directed_sell`, its own
  module and status so it never borrows the policy-breach path's meaning.
- Every refusal is a stated sentence, never a silent edit: unheld ticker;
  share count that is not a real positive `int` (reuses
  `risk.execution_gate.is_valid_share_quantity`, so bools, whole-valued
  floats, NaN, and strings are rejected exactly as the broker layer rejects
  them); more shares than held (holdings floor to whole shares — rounding up
  would propose a short); unusable price; notional above `max_order_value`,
  which names how many shares WOULD fit rather than quietly shrinking the
  owner's instruction.
- The tax-consequence disclosure was consolidated into
  `assistant.proposals.attach_tax_lot_advisory` and is now shared with the
  policy-breach generator instead of hand-copied; a test pins that both
  callers use the same object.
- Surfaces: a Selling-tab section placed above and visually divided from the
  policy-breach section, with copy that disclaims any recommendation, plus
  CLI `sell-holding --ticker --shares [--json]`.
- Not implemented on purpose: limit orders, scheduled/conditional sells,
  bulk multi-ticker sells, and any auto-submission.

## 4. Validation (repository venv, Python 3.13.14 / Streamlit 1.60.0)

Thread A (in the review worktree):

- M3 suite after both counter-review guards: **72 passed**.
- Six review findings mutation-verified (seven runs; M3REV-004 at both
  sites); two counter-review guards mutation-verified.
- Exact counter-review tree: **3,567 passed, 0 failed, 0 skipped, 25 known dependency warnings** in 705.61 s (review worktree, repository venv).

Thread B (this branch):

- `tests/test_user_directed_sell.py`: **40 passed**, including the exact
  boundary at `max_order_value`, fractional-holding flooring, and the
  full bad-share-quantity matrix.
- `tests/test_ui_user_directed_sell.py`: **3 passed** (section renders, copy
  disclaims recommendation, share widget bounded by the holding).
- Four safety guards mutation-verified: over-sell refusal, share-validity
  check, floor-not-ceil, and the max-order-value refusal each reddened
  exactly their tests and passed restored.
- `assistant/proposals.py` extraction proven behavior-preserving:
  `tests/test_proposals.py` + `tests/test_tax_lots.py` **105 passed**
  before and after.
- Validating run (everything final except this line): **3,536 passed,
  1 failed, 25 known dependency warnings** in 641.68 s — the single failure
  was the extended placeholder guard correctly rejecting this line's own
  then-unfilled token. Total collected 3,537 = `main`'s 3,494 plus this
  branch's 43 new tests.
- Exact final tree differs from that run only by this validation text; the
  doc-consistency suite (the only tests that read this file) was rerun green
  on the final text: **19 passed**.
- Repository-prescribed `compileall` and `git diff --check`: clean.

## 5. Operational truth — do not disturb the epoch

- `paper-epoch-004` is the only active evidence epoch, frozen at `b837374`.
  Neither thread is deployed there.
- AP-8, AP-9, QC-2, AP-10, AP-11, M3, and SELL-1 are all merged-or-pending
  development code riding the next owner-authorized epoch roll.
- CR-W3 watch unchanged (first real AEP dividend subtype ~2026-09-10; JNLC
  needs operator judgement; never widen reconciliation tolerance or use a
  manual compensating entry).

## 6. Next step

Owner merges of the two pushed branches, and an independent review of
Thread B (`user/claude/user-directed-sell-20260813`), which has had no
outside review yet. M4 remains deferred by default. Other open owner
decisions are unchanged: epoch-roll timing, the physical-media-only
off-machine backup, and the unidentified `origin/Funny` branch.

## 7. Resume prompt

```text
Verify a clean worktree and check which of the two branches have merged.
Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md (AP-11, SELL-1, GR-7d),
docs/REVIEW_2026-08-13_THREE_SLEEVE_M3.md including its counter-review
section, and docs/SESSION_HANDOFF.md. The pending work is independent
review of user/claude/user-directed-sell-20260813. Do not deploy, touch the
operator database, roll paper-epoch-004, or begin M4 without a new owner
instruction.
```
