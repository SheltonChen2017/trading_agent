# Claude counter-review — Codex's correction of REBAL-1 Stage 2

Date: 2026-08-15
Reviewer: Claude
Base reviewed: `7420a99` (Stage 2 as submitted)
Commits under review: `bdeb61d` (product/test correction), `c14acfc` (records)
Counter-review branch: `user/claude/rebal1-stage2-counterreview-20260815`
Disposition: **Codex's correction accepted; one P3 found and closed. No
finding against the execution-path change.**

## Scope and method

Codex reviewed and corrected REBAL-1 Stage 2, which I implemented. This
reviews the correction — every hunk in `bdeb61d`, including the changes to
`assistant/execution_kernel/validate.py` and `assistant/execution_service.py`,
which are execution-path modules and therefore got the most scrutiny.

Each of Codex's six findings was re-derived against the submitted tree in a
throwaway worktree at `7420a99`. Each correction was proven load-bearing by
reverse mutation, and Codex's new tests were themselves mutation-tested.

No database write, broker request, order, scheduler change, deployment, or
epoch transition occurred. The worktree was created outside the repository
and removed.

## Codex's findings, independently re-derived

**REBAL2CR-001 (P2) — confirmed, and this one is on me twice over.** Every
Stage 2 proposal carried a `Decimal` in `reference_price`, and
`save_proposal()` JSON-encodes: `json.dumps(proposal.to_dict())` raises
`Object of type Decimal is not JSON serializable`. The feature's only action
path crashed before an approval card could exist.

Worse than missing it: I *saw* the type discrepancy and wrote a comment
rationalising it — "Annotated `object` because it holds a Decimal, not a
float… Claiming `float` here would be a lie." I made the annotation honest
and never asked the next question, which was whether anything downstream
required the float. Documenting a smell is not the same as chasing it.

My tests missed it because they only inspected in-memory proposal fields, and
my UI tests never drove the button. The whole action path was untested end to
end, which is exactly the gap `CLAUDE.md` §9 warns about when it says to
prefer behavioural tests over asserting on constructed objects.

**REBAL2CR-002 (P2) — confirmed.** Budgets `2000` and `2000.01` produced four
legs each with different `proposal_id` and *identical* `idempotency_key`, and
`trade_proposals.idempotency_key` is unique. Saving the second set would raise
a database uniqueness error. I had salted the id with the budget and the key
with only the profile — the two ought to have been derived from one another,
which is what the correction does.

**REBAL2CR-003 (P2) — confirmed, and the correction is architecturally the
right shape.** The profile fingerprint changed proposal *identity* but was
never an execution-time condition, so a proposal persisted before a profile
edit stayed reachable from History and could execute under the new profile.
Binding identity prevents row reuse; it does not invalidate a stored row.

**REBAL2CR-004 (P2) — confirmed.** My hand-built staleness signature used
date, equity, choices, budget and pending totals. Two holdings moving in
opposite directions on the same day leave all of those unchanged while the
sleeve weights move, so a card sized from stale weights stayed visible.

**REBAL2CR-005 (P3) — confirmed.** I reconstructed exact dollars from
`projected_pct` and `lower_edge_pct`, which are display floats. The
correction computes the edge from the profile's Decimal band and subtracts
the row's exact values.

**REBAL2CR-006 (P3) — confirmed.** My records claimed profile binding lived
in identity and idempotency, and that the short signature covered snapshot
staleness. Both were incomplete descriptions of what the code did.

## The execution-path change, audited separately

This is the part of `bdeb61d` that most deserved scrutiny, because it adds a
check inside the execution kernel. My conclusion is that it is sound:

- **Dependency shape is correct.** `validate_proposal_context` is injected
  through `ProposalValidationDeps` at call time, not imported by the kernel.
  The kernel keeps its zero-module-global boundary, and the seam is pinned by
  `test_gr1c_every_injected_seam_resolves_from_the_facade_at_call_time`.
- **It runs before `deps.import_broker()`**, so a refusal happens before any
  broker I/O.
- **Adding a required field to the frozen deps dataclass breaks no other
  caller**: `ProposalValidationDeps(` has exactly one construction site.
- **Other proposal families are untouched.** The guard keys on
  `evidence_status` and returns `None` immediately for everything else; I
  pinned that with a test across four other families plus a row with no
  `evidence_status` at all, and removing the key check reddens it.
- **The failure class is consistent.** `failure_data_integrity` is what the
  six sibling pre-broker refusals in the same function already use.
- **The deferred import of `rebalance_profile` inside `execution_service`**
  keeps the generic kernel independent of the rebalancing feature and adds no
  path toward `ml`.

## Prioritized issue ledger — this counter-review

| ID | Priority | Status | Location | Evidence and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| REBAL2CCR-001 | P3 | Closed | `assistant/execution_service.py` | The context check has two arms — missing fingerprint and mismatched fingerprint — and only the mismatch arm was pinned. Deleting the missing-value branch left the entire suite green. **Safety was never at risk**, and my first reading of this overstated it: without that branch `None != current` still refuses the proposal. What is lost is the accuracy of the reason — the owner is told the profile "does not match" when there is nothing to match, sending them to look for a profile edit that never happened. The missing case is the reachable one, since any steering proposal saved before this guard existed carries no fingerprint. | Two regressions: one drives a real `AssistantStore` with the fingerprint stripped and asserts the refusal says *missing* and not *does not match*; the other pins that four other proposal families and a row with no `evidence_status` pass through untouched. | Removing the missing-value branch reddens the first; removing the `evidence_status` key check reddens the second. |

Issue total: **0 P0 / 0 P1 / 0 P2 / 1 P3; closed; 0 open.**

## Mutation results against Codex's corrections

Eight mutations, seven detected by exactly the intended test:

| Mutation | Detected |
|---|---|
| `reference_price` back to `Decimal` | yes — two tests |
| Context check removed from the kernel | yes |
| Validator always returns `None` | yes |
| Missing-fingerprint branch removed | **no** → REBAL2CCR-001 |
| Shortfall recomputed from display floats | yes |
| Snapshot dropped from the staleness fingerprint | not alone — see below |
| Snapshot *and* report both dropped | yes |
| `evidence_status` key check removed | yes (after my test) |

The staleness result is worth stating precisely rather than as a near-miss:
the fingerprint payload contains both the full portfolio snapshot and the
report, and the report already carries per-sleeve market values. Removing
either alone leaves the property defended by the other, so
`test_same_day_market_value_change_invalidates_the_ui_signature` is
discriminating, not vacuous — it reddens once both are removed. Belt and
braces, not redundancy to trim.

## A note for whoever builds multi-profile support

`_validate_proposal_context` compares against the module constant
`OWNER_APPROVED_PROFILE`, while `generate_steering_proposals` accepts a
`profile` argument. Today the UI only ever passes the constant, so they agree.
The moment Stage 0 grows editable or multiple profiles — which the milestone
plan implies, since it requires a profile change to invalidate prior work —
this check must resolve the *active* profile instead, or every proposal made
against a non-constant profile will be permanently unexecutable. That is the
fail-closed direction, so it is a trap for a future change rather than a
present defect, and it is not fixed here.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- `tests/test_rebalance_steering.py`: **32 passed** (30 before).
- Full settled tree: recorded in `docs/SESSION_HANDOFF.md`.
- `compileall` and `git diff --check`: clean.

## Untested and out of scope

- Nothing here touches a real broker, order, or paper account.
- **No evidence supports the target shape.** Fixtures prove software
  behaviour only.
- Stage 3 is not started and requires separate explicit authorization; it is
  the first stage that would let the app originate rebalancing sells.
- This work is development-only and authorizes no deployment, epoch roll,
  scheduler change, operator-database mutation, or live trading. Deploying
  would change `code_commit` and close active `paper-epoch-005`.
