# Counter-review — SET-1 independent correction (`89156b7`)

Date: 2026-08-14
Reviewer: Claude (counter-review of Codex's independent SET-1 review)
Base reviewed: `ca0cdf0` (`origin/main`, PR #217)
Correction branch: `user/claude/set1-counterreview-20260814`
Final disposition: **accepted after correction**

## Scope and method

Codex's review did far more than review. `89156b7` built the entire
fractional-share order path that SET-1 had deliberately left unbuilt — 1,030
insertions across the risk gate, the broker adapter, the execution kernel,
proposal sizing, and the UI. That is the most safety-critical surface in this
repository, so this counter-review treated it as new execution code rather
than as review commentary.

Method: every commit in `cfed8c8..ca0cdf0` received a disposition; the
quantity authority was probed directly rather than read (strict/permissive
refusals, precision boundary, magnitude, non-finite text, scientific
notation); `whole_shares_only` was traced from policy through every call site
to the broker; and each correction below was mutation-tested — the fix was
reverted, the intended test was confirmed to redden, and the original bytes
were restored in a `finally`.

No funded-account call, order, deployment, scheduled-task change, operator
database mutation, or epoch operation occurred.

## SET1R-001 is conceded

Codex's central finding is correct and this counter-review does not contest
it. The owner asked that deactivating the toggle let the app "allow fraction
shares." SET-1 shipped the authority helper, the policy field, the fingerprint
binding, and the UI switch, but no production path could produce or submit a
fractional quantity. A permission control that grants nothing is materially
misleading, and "the order path is not yet fractional end to end" in a commit
message does not repair the surface the owner actually uses. The correction
was the right call.

## Commit-by-commit disposition

| Commit | Type | Disposition | Result |
|---|---|---|---|
| `89156b7` | Codex fractional path | **Accepted after correction** | Threading, fail-closed defaults, and reconciliation exactness verified sound. Four defects found and corrected here (SET1CR-001 … SET1CR-004). |
| `6b944ac` | Codex review record | **Accepted** | Ledger and dispositions match the code. |
| `d4d43cf` | Codex handoff refresh | **Accepted after correction** | Accurate when written; superseded by PR #217 merging. Corrected here. |
| `55a1110` | Codex branch record | **Accepted after correction** | Described the correction branch as unmerged; PR #217 has since merged it. Corrected here. |
| `ca0cdf0` | PR #217 merge | **Accepted after correction** | No conflict-resolution regression. The Action Plan still said `main` was `cfed8c8`. Corrected here. |

## Verified sound — no action taken

These were checked specifically because they are where this change could have
gone wrong, and each held:

- **Strict remains the default at every layer.** `validate_trade_intent`,
  `resolve_submission_call`, `_require_valid_shares`, and both broker submit
  functions default to `whole_shares_only=True`. A caller that forgets to
  thread the policy refuses a fractional order rather than admitting it.
- **`whole_shares_only` is threaded from the policy at both real call sites**
  (`validate.py:550`, `execution_service.py:666`) — not defaulted, not
  inferred from the intent.
- **The broker fractionable flag fails closed**:
  `bool(getattr(asset, "fractionable", False))`. A broker response that omits
  the field refuses the order.
- **Floats remain rejected in both modes.** Permitting fractions did not
  reopen binary float as an order quantity — the SELREV-001/002 defect class.
- **Reconciliation is now exact.** The `1e-9` float tolerance is gone, and
  `shares_decimal` is preferred over the float field, so a one-nanoshare
  identity mismatch under the same idempotency key can no longer reconcile as
  a match.

## Prioritized issue ledger

| ID | Priority | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| SET1CR-001 | P2 | Closed | `scripts/personal_assistant_ui.py`, `assistant/user_directed_sell.py` | The whole-share floor makes a real holding **unsellable and invisible**. A 0.5-share position floors to 0, is filtered out of the Discrete Selling dropdown, and leaves no trace on the page — the owner's own stock silently absent from the only page that sells it. A 10.5-share position reports "10 whole share(s)" as though that were the holding, and selling all 10 then reports "closes the position" while 0.5 remains. Fractional buys make this reachable by ordinary use; it also already applied to fractions arriving from dividend reinvestment or corporate actions. CLAUDE.md §5 names this exact direction: a conservative safeguard must not obstruct a legitimate risk-reducing sell. | Disclose both cases and name the authorized remedy (turn the setting off, which is already a typed, fingerprinted, owner-only act). The floor itself is unchanged — the defect was silence, not strictness. | 5 tests, including a negative case proving the remedy is not offered when it would not help, and one proving the advertised remedy genuinely closes the position. |
| SET1CR-002 | P3 | Closed | `risk/execution_gate.py`, `assistant/discrete_trade.py` | The quantity authority bounded **precision but not magnitude**. `1E+1000` has zero decimal places, so it passed the nine-decimal rule and was returned as a valid quantity, becoming a 1001-digit integer in durable proposal JSON. Nothing downstream was unsafe — the max-order-value check refuses it on notional — but the durable artifact is written before that refusal, and a quantity authority that answers "valid" for a quantity no broker could accept is the wrong boundary to trust. | Bound the magnitude at the authority, in **both** modes (a plain `int` reaches strict mode by a different branch, so applying it on one side only would have made the stricter mode the permissive one). The bound now lives once, in the gate; `discrete_trade` imports it instead of keeping its second copy. | 4 tests, including the strict-mode branch and a drift test pinning the two former copies to one value. |
| SET1CR-003 | P3 | Closed | `assistant/execution_kernel/validate.py` | An unreadable quantity was replaced with `Decimal("0")` by a broad `except Exception`. Zero is integral, so the broker fractionable check immediately below it silently did not run. **Reachability, stated honestly: this branch is not reachable through a durable proposal** — the stored-intent parser refuses the quantity first, which the counter-review confirmed by trying to reach it. The finding is therefore about a banned pattern and a defense-in-depth guard, not a live hole. | Narrow the handler and refuse rather than manufacture a plausible quantity. | A behavioural test pinning the upstream refusal that makes this unreachable (so a future loosening fails there), plus a structural test on the handler shape. |
| SET1CR-004 | P3 | Closed | `assistant/execution_kernel/submit.py` | `Decimal(intent.shares)` became a bare **string** conversion the moment `TradeIntent.shares` changed to `int | str`. Bare `Decimal(<str>)` accepts `"NaN"`/`"Infinity"` and raises `InvalidOperation` — an `ArithmeticError`, not a `ValueError` — so it escapes the `ValueError` handlers around it. A NaN here would poison the daily-budget reservation: the FPS-001 → GFPS-001 → CFPS-001 class this repository has already paid for three times. The AST guard did not catch it because the guard bans `Decimal(str(...))`, not `Decimal(<a str variable>)`. | Use the guarded conversion. | 2 tests: refusal on `"NaN"`, and a valid fractional quantity still computing its notional. |

Issue total: **0 P0 / 0 P1 / 1 P2 / 3 P3; all closed; 0 open**.

## Open design question for the owner — not a defect

SET1CR-001 discloses the stranded remainder and names the remedy, but keeps
the floor: under **Whole shares only**, a fractional holding still cannot be
sold without first turning the setting off.

The alternative is to permit a fractional sell **only when it closes the
entire remaining position**, since that can never increase exposure and is the
canonical risk-reducing action. That was deliberately not implemented here.
It would need the exception to hold consistently across four layers that are
independent on purpose — the gate, the sell generator, the last-mile broker
check, and the fractionable preflight, which currently runs only when the
policy is permissive. Widening what strict mode permits is an owner decision
about the safety model, not a correction a reviewer should make unilaterally,
and the existing remedy is a genuine one: turning the setting off is already
a typed, fingerprinted, owner-only act.

## Validation

Environment: repository `.venv`, Python 3.13.14, Streamlit 1.60.0, Windows.

- New counter-review suite `tests/test_set1_counterreview.py`: **15 passed**.
- **Mutation testing: 5 of 5 fixes detected.** Each fix was reverted
  individually and the intended test confirmed to fail; original bytes were
  restored in a `finally`, and `git diff` confirmed the restoration was exact.
- Full repository suite: **3,752 passed / 1 failed / 25 warnings** in
  848.07 s. The single failure was `test_no_document_calls_a_merged_commit_unreachable`,
  a documentation-continuity guard catching this counter-review's own
  handoff wording: it placed the word "unmerged" beside merged commit
  hashes while stating they were merged. The guard matches proximity, not
  meaning, and it was right to fire on a sentence that reads ambiguously.
  Reworded; no production, policy, gate, broker, execution, or UI test
  failed.
- Affected suites re-run after the documentation edits (document
  consistency, counter-review, discrete tabs, settings, owner-directed
  sell, dollar sizing, decimal guard, ML import boundary, risk registry):
  **196 passed**.
- `compileall`: clean. `git diff --check`: clean. `launch_dev_app.ps1`
  parse-checked without executing it.

A caveat recorded rather than hidden: an earlier full-suite run reported two
failures in `tests/test_risk_check_registry.py`. That run overlapped edits to
`risk/execution_gate.py`, and those tests inspect source from disk. Re-run on
the settled tree, they pass. The failures were an artifact of measuring a tree
while changing it, not a defect — and the general lesson is that a suite run
concurrent with edits validates nothing.

## Untested and out of scope

- No fractional order has ever been submitted to Alpaca from this code. The
  REST fractional path, the nine-decimal limit, and fractionable-asset
  eligibility are verified against fixtures and Alpaca's documented contract,
  **not** against a live broker response. First real use should be watched.
- `time_in_force="day"` and limit-order support for fractional quantities are
  taken from Alpaca's documented contract, not observed.
- The stranded-remainder disclosure is verified in Discrete Selling. Policy
  Based Selling and the allocation paths were not re-examined for the same
  wording, because they do not floor a holding for display.

## Operational and authorization result

Development code only. `paper-epoch-005` remains pinned to deployed commit
`752d3b7`; nothing here is deployed. `whole_shares_only` participates in
`compute_policy_fingerprint`, so deploying even its safe default changes
execution lineage and closes the active epoch. Deployment, epoch roll,
funded-account access, live trading, and operator-database mutation all remain
unauthorized absent a separate explicit owner instruction.
