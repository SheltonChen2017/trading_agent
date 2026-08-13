# Session handoff — owner-directed sell, atop merged M3

Prepared: 2026-08-13, after the owner merged the three-sleeve M3 review
branch (PR #201) and this Selling-tab milestone was integrated on top of it.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md` (rows SELL-1, AP-11, GR-7d)
3. `docs/REVIEW_2026-08-13_THREE_SLEEVE_M3.md` including its counter-review
   section
4. `docs/reference/THREE_SLEEVE_ENGINE_PLAN.md` §1.1 / §5 M3
5. `docs/OPERATIONAL_FACTS.md`
6. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`

The action plan remains the sequencing authority. Nothing here authorizes
deployment, an epoch roll, M4, live trading, or any funded action.

## 1. Repository topology

- `main` / `origin/main`: `022c456` — PR #201, which merged
  `codex/review-three-sleeve-m3-20260813`. That branch carried three-sleeve
  M3 (`7ee4786`), Codex's correction (`b6685b5`), its review record
  (`55b4518`), and Claude's counter-review (`a5fc599`). **M3 and its six
  corrections are therefore on `main`.**
- This branch: `user/claude/user-directed-sell-20260813` — implementation
  `918eecd` plus this integration merge of `origin/main`.
- The now-superseded `user/claude/three-sleeve-m3-earmarks-20260813` holds
  only the pre-review M3 commit. Everything in it reached `main` through
  PR #201; it can be deleted whenever convenient. Do NOT merge it — doing so
  would add nothing and only re-open reviewed history.

### Integration merge — what was resolved, and why

The two threads were developed from the same base and both touched the
Selling/Buying pages and the CLI, so the merge produced three conflicts.
Recorded because a conflict resolution is exactly where work silently
disappears:

- `scripts/run_personal_assistant.py` — the real one. Git interleaved
  `command_sell_holding` with M3's `command_sleeve_reinvest_propose`
  because both handlers end in the same "Approve with:" shape, producing a
  chimera that would have compiled while mixing two features' output. It was
  NOT hand-patched: the file was rebuilt from `origin/main`'s version (the
  authority for M3) with this branch's handler and subparser re-inserted
  verbatim from `918eecd` at stable anchors. Verified afterwards by AST that
  all five handlers (`command_sell_holding`, `command_sleeve_reinvest`,
  `command_sleeve_reinvest_propose`, `_print_reinvest_status`,
  `command_sleeve_report`) exist exactly once.
- `tests/test_active_document_consistency.py` — the placeholder-token regex.
  This branch's version is a strict superset of main's, so it was taken
  whole; no token stopped being guarded.
- `docs/SESSION_HANDOFF.md` — rewritten (this file) for the post-merge
  reality rather than either side being picked, which is the IPRCR-001
  staleness class this project keeps re-learning.

`scripts/personal_assistant_ui.py` auto-merged: M3's expander lives in the
Buying page, this milestone's section in the Selling page.

## 2. This milestone — owner-directed sell (SELL-1)

Owner request: the Selling tab only ever proposed sells when a deterministic
policy breach demanded one; the owner asked to be able to sell an individual
currently-held position on their own judgement.

- `assistant/user_directed_sell.py`:
  `generate_user_directed_sell_proposal(...) -> {"created": bool, ...}` and
  `sellable_whole_shares(...)`. Evidence status `user_directed_sell` — its
  own module and status, because the policy-breach generator's
  `deterministic_risk_policy` means the PROJECT computed a breach, and this
  claims nothing of the sort.
- Every refusal is a stated sentence, never a silent edit of the owner's
  instruction: unheld ticker; a share count that is not a real positive
  `int` (reuses `risk.execution_gate.is_valid_share_quantity`, so bools,
  whole-valued floats, NaN, and strings are rejected exactly as the broker
  layer rejects them); more shares than held, with holdings floored to whole
  shares because rounding up would propose a short; an unusable price; and a
  notional above `max_order_value`, which names how many shares WOULD fit
  rather than quietly proposing fewer than asked.
- The tax-consequence disclosure was consolidated into
  `assistant.proposals.attach_tax_lot_advisory`, now shared with the
  policy-breach generator instead of hand-copied; a test pins that both
  callers use the same object.
- Surfaces: a Selling-tab section above and visually divided from the
  policy-breach section, with copy disclaiming any recommendation, plus CLI
  `sell-holding --ticker --shares [--json]`.
- Deliberately not implemented: limit orders, scheduled or conditional
  sells, bulk multi-ticker sells, and any auto-submission. Nothing here
  weakens `risk/execution_gate.py`, which re-checks everything at approval.

## 3. Validation (repository venv, Python 3.13.14 / Streamlit 1.60.0)

Pre-merge, on `918eecd`:

- `tests/test_user_directed_sell.py` **40 passed**;
  `tests/test_ui_user_directed_sell.py` **3 passed**.
- Four safety guards mutation-verified (over-sell refusal, share-validity,
  floor-not-ceil, max-order-value refusal): each reddened exactly its own
  tests and passed restored.
- The `assistant/proposals.py` extraction proven behavior-preserving:
  `tests/test_proposals.py` + `tests/test_tax_lots.py` **105 passed** before
  and after.
- Branch tree: **3,537 collected, 0 unexpected failures**.

Post-merge, on this integrated tree:

- Both feature suites together — `test_user_directed_sell`,
  `test_ui_user_directed_sell`, `test_sleeve_reinvest`,
  `test_ui_sleeve_reinvest`, `test_proposals`: **128 passed**.
- Validating run (everything final except this line): **3,609 passed,
  1 failed, 25 known dependency warnings** in 679.01 s — the single failure
  was the placeholder guard correctly rejecting this line's own then-unfilled
  token. Total collected 3,610 = merged `main`'s 3,567 plus this branch's 43,
  which is the arithmetic proof that the merge dropped no test from either
  side.
- Exact final tree differs only by this validation text; the doc-consistency
  suite (the only tests reading this file) was rerun green on the final text.
- `compileall` and `git diff --check`: clean.

## 4. Operational truth — do not disturb the epoch

- `paper-epoch-004` is the only active evidence epoch, frozen at `b837374`
  in `C:\git\trading_agent_operational`. Nothing here is deployed.
- AP-8, AP-9, QC-2, AP-10, AP-11, M3 (now on `main`), and SELL-1 (pending)
  all ride the next owner-authorized epoch roll.
- CR-W3 watch unchanged: the first real AEP dividend subtype may over-refuse
  safely around 2026-09-10; JNLC still needs operator accounting judgement;
  never widen reconciliation tolerance or use a manual compensating entry.
- When M3 first deploys, the dividend pool will be non-zero immediately
  (the operator ledger already holds confirmed dividends). Nothing spends it
  without an explicitly approved proposal.

## 5. Next step

Independent review of this branch (SELL-1 has had no outside review), then
the owner's merge. M4 remains deferred by default. Unchanged open owner
decisions: epoch-roll timing, the physical-media-only off-machine backup,
the unidentified `origin/Funny` branch, and deletion of the superseded
`user/claude/three-sleeve-m3-earmarks-20260813`.

## 6. Resume prompt

```text
Verify a clean worktree and confirm whether user/claude/user-directed-sell-
20260813 has merged. Read CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md
(SELL-1, AP-11, GR-7d), docs/SESSION_HANDOFF.md, and
docs/REVIEW_2026-08-13_THREE_SLEEVE_M3.md including its counter-review
section. Pending work is independent review of SELL-1. Do not deploy, touch
the operator database, roll paper-epoch-004, or begin M4 without a new owner
instruction.
```
