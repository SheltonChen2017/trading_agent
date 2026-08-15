# Claude counter-review — Codex's correction of REBAL-1 Stage 1

Date: 2026-08-15
Reviewer: Claude
Base reviewed: `afa47d9` (Stage 1 as merged by PR #226)
Commits under review: `5519a69` (product/test correction), `ccb00f4` (records)
Counter-review branch: `user/claude/rebal1-stage1-counterreview-20260815`
Disposition: **Codex's correction accepted; one P2 found and closed**

## Scope and method

Codex reviewed and corrected REBAL-1 Stage 1, which I implemented. This
reviews Codex's correction: every changed hunk in `5519a69`, the tests it
added, the two module contracts it changed, the Streamlit edits, and the
records commit `ccb00f4`.

Method: each of Codex's eight findings was **re-derived against the submitted
tree** in a throwaway worktree at `afa47d9` rather than accepted on the
report's word; each correction was proven load-bearing by reverse mutation;
and Codex's new tests were themselves mutation-tested. All eight reproduce.
Nine mutations against Codex's fixes were all detected — unlike the previous
two rounds, no vacuous test was found in this correction.

No database write, broker request, order, scheduler change, deployment, or
epoch transition occurred. A temporary worktree was created outside the
repository and removed.

## Codex's findings, independently re-derived

All eight confirmed. The three that matter most:

**REBAL1R-001 (P2) — confirmed, and the worst defect in my Stage 1.** My
projection moved the asset sleeve without the opposite cash leg, so a $500
hedge buy took hedge 5%→10% while cash stayed 95% and **projected weights
summed to 105%**. A projection that does not conserve equity is not a
projection. Codex's fix applies the opposite signed leg to cash and the total
is now exactly 100%.

**REBAL1R-005 (P2) — confirmed.** My module documents that invalid input
returns an unusable report; `evaluate_portfolio_rebalance(snapshot, object())`
raised `AttributeError` instead, escaping its own fail-closed boundary.

**REBAL1R-006 (P3) — confirmed, and a direct `CLAUDE.md` §7 violation.**
`@dataclasses.dataclass(frozen=True)` does not freeze a nested dict, so the
caller's `targets` mapping stayed live: mutating it after construction
changed the profile's fingerprint with no new object and no version event —
defeating the staleness mechanism the profile exists to provide. `CLAUDE.md`
requires deep-copying and freezing nested caller-owned structures; I did not.

Also confirmed: **R-002** (the approved profile is infeasible under the
active policy — see below), **R-003** (a malformed authoritative notional
fell back to `qty × limit_price`, measuring corruption as $1,000), **R-004**
(tickerless and non-dict order rows were silently dropped; unknown pending
residual tickers never appeared), **R-007** (`None` became ticker `"NONE"`
and `True` became `"TRUE"`), and **R-008** (exact money strings converted
through binary float for display).

## Prioritized issue ledger — this counter-review

| ID | Priority | Status | Location | Evidence and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| REBAL1CR-001 | P2 | Closed | `assistant/portfolio_rebalance.py`, Portfolio Rebalancing page | `policy_conflict` occupied the `status` field, so it MASKED the band state, and the headline "Bands breached" counts only band breaches. Against the owner's approved profile and the active `my_policy.json`, the page reported **1 breached band while 6 sleeves were outside theirs** — the most prominent number on a page whose entire purpose is showing drift, understated by five sleeves. The status precedence was mine; Codex's correct R-002 expansion of conflict detection (0 → 5 conflicted sleeves) turned a latent flaw into an active one. | Feasibility and drift are independent facts, so they are now independent fields: `status` keeps the band/data state and a new `policy_conflict_reason` carries the conflict, surfaced as its own "Target reachable" column and still present in the disclosures. | Two mutations — restoring the masking branch, and dropping the reason from the row — each redden four tests. Three module regressions and two UI regressions added, including one asserting the headline equals the true count of sleeves outside their bands. |

Issue total: **0 P0 / 0 P1 / 1 P2 / 0 P3; closed; 0 open.**

### Contract change, flagged for the plan's author

Stage 1's spec lists `policy conflict` among the supported statuses. It is no
longer *assigned* as one; the constant remains exported and the concept is
strictly more visible than before (its own column, its own field, plus the
existing disclosure). This is a deliberate deviation from the plan's letter
in service of the plan's purpose, and Codex should push back if the status
enumeration was load-bearing for something I have not seen.

## Codex's work verified sound and retained

- The cash opposite-leg projection, the authoritative-notional rule, the
  unidentifiable-order refusals, the public-boundary guard, the
  `MappingProxyType` freeze, the config ticker validation, and the Decimal
  display formatting. All load-bearing under reverse mutation.
- The **status precedence change** putting `pending_value_unknown` ahead of
  the conflict: I probed whether one unknown market order could hide a
  durable policy conflict, and it cannot — the conflict still reaches the
  reader through `report.disclosures`.
- **Status computed from projected rather than current values.** I checked the
  direction that would have been dangerous: a pending order too small to fix
  a breach still reports the breach (hedge 0% → 1% against a 7.5% lower edge
  still reads `underweight`).
- Codex's rewrite of two of my tests is a legitimate contract change, not a
  weakened test.

## The finding the owner needs

The approved profile is **not reachable under the active policy**, and this
is a real decision rather than a display issue:

- the profile targets 90% invested; `my_policy.json` caps total exposure at
  **50%**; and
- growth targets 40% while its six configured tickers, each capped at
  `max_position_pct` 5%, can jointly hold at most **30%**.

Stage 1 now states both on the page. Either the profile or the policy has to
move before Stage 2 could steer money toward these targets, and that is an
owner decision, not something this feature should resolve.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- `tests/test_portfolio_rebalance.py`: **69 passed** (66 before).
- `tests/test_ui_portfolio_rebalance.py`: **11 passed** (9 before).
- Mutation verification: **9 against Codex's corrections**, all detected, and
  **2 against this counter-review's own**, both detected.
- Full settled tree: recorded in `docs/SESSION_HANDOFF.md`.

## Untested and out of scope

- Nothing here touches a real broker, order, or paper account; the feature is
  exercised against fixtures.
- Stage 1 remains read-only. Stages 2 and 3 are unstarted; Stage 3 still needs
  its own explicit authorization.
- This counter-review authorizes no deployment, epoch roll, scheduler change,
  database mutation, or live trading. Deploying would change `code_commit` and
  close active `paper-epoch-005`.
