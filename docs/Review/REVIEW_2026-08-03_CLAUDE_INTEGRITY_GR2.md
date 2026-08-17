# Independent review — Claude integrity sweep and GR-2 risk registry

Date: 2026-08-03

Status: **accepted after correction** on
`codex/review-claude-gr2-integrity-20260803`. Claude's submitted work is
rated **8/10 overall** (integrity sweep 8/10; GR-2 implementation 8.5/10).
The corrected result is rated 9/10.

## Exact scope and commit dispositions

Base: `9e2826a` (PR #128 merge). Review head: `b021499` (PR #130 merge).
Ordered range: `9e2826a..b021499`.

| Commit | Intent | Disposition | Issues |
|---|---|---|---|
| `5f4d9cc` | Confirm GR-5 review and perform the owner-requested integrity sweep | accepted after correction `CRREV-001` | The newly wired CLI warning batch could still disappear before rendering when briefing construction failed. The remaining lineage/UI/test cleanups and joined halt-to-delivery seam were accepted. |
| `c79d97f` | Record integrity-sweep handoff | accepted after correction `CRREV-004` | Its appended update left the canonical Git/resume sections describing the older GR-5-only state. |
| `f778ef3` | Merge PR #129 | accepted after cumulative corrections | Its tree is byte-identical to topic tip `c79d97f`; there is no conflict-resolution delta. |
| `03895ae` | Replace the hand-written execution gate with the ordered risk-check registry | accepted after corrections `CRREV-002` and `CRREV-003` | Current behavior is preserved; terminal semantics and frozen-test sensitivity required hardening. |
| `f5071d8` | Record GR-2 implementation handoff | accepted after correction `CRREV-004` | Its new top update again left the lower canonical state and resume prompt stale. |
| `b021499` | Merge PR #130 | accepted after cumulative corrections | Its tree is byte-identical to topic tip `f5071d8`; there is no conflict-resolution delta. |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CRREV-001 | P2 | Resolved | `5f4d9cc` | `scripts/run_personal_assistant.py::command_briefing` | Warnings were finally routed into the CLI briefing, but only after `_packet()`, persistence, and macro work. If the account, portfolio, or data path failed first, the command printed no already-durable warnings even though the briefing is their only routed delivery surface. | A regression seeded an open warning, forced `_packet()` to fail, and failed red because captured output was empty. | Operational problems often coincide with briefing-data failures. Making the sole warning surface depend on those fallible steps preserves the exact “delivered nowhere” failure class the integrity fix was meant to close. | Render the durable warning batch before any fallible market/account work; retain the original exception. | Red: targeted test failed with no warning output. Green: the warning renders before the forced packet failure; focused suite passes. |
| CRREV-002 | P3 | Resolved | `03895ae` | `risk/execution_gate.py::validate_trade_intent` | A terminal check stopped evaluation whenever *any* violation existed, not only when that terminal check added one. This is harmless for today's first-position kill switch but breaks the documented registry contract for a later terminal entry. | An injected passing terminal check placed after an invalid-side violation suppressed a later blocking check; the regression failed red. | GR-2 promises that new checks can be added through the registry. Terminality must attach to the terminal check's own failure, or future registry edits silently change violation accumulation. | Capture the violation count before each check and break only when a terminal check increases it. | Red/green targeted regression plus the 290-test focused suite. |
| CRREV-003 | P3 | Resolved | `03895ae` | `tests/test_risk_check_registry.py` | The “frozen” inventory pinned names and metadata but not the runner bound to each name, so two implementations could be swapped without that inventory test noticing. Its violation-code assertion compared against an empty set and therefore proved nothing. | Source inspection and direct evaluation of the assertions showed both blind spots. | The inventory is described as the load-bearing detector for accidental registry drift; a vacuous or metadata-only assertion gives reviewers a false sense of mutation coverage. | Bind every frozen name to its `_check_<name>` runner and inspect each runner's AST to verify referenced `ViolationCode` members exist. | New sensitivity tests pass in the focused suite; Claude's existing deletion, injection, identity, and short-circuit tests remain green. |
| CRREV-004 | P3 | Resolved | `c79d97f`, `f5071d8`, `b021499` | `docs/SESSION_HANDOFF.md` | Successive top-of-file updates described the new branches while the canonical Git state, roadmap, and resume prompt still described the prior GR-5 review and `main=95c4ea1`; merge #130 then made the “awaiting merge” instruction false. | The final merged file simultaneously named GR-2 at `03895ae` and claimed canonical local/remote main was `95c4ea1`. | The handoff is the repository's cross-computer source of truth. Contradictory branch instructions can make the next agent resume from the wrong snapshot or repeat completed work. | Replace the handoff after review with one coherent snapshot naming all reviewed and correction commits, remote availability, validation, and the owner-gated next step. | Documentation diff/check and final Git topology audit. |
| CRREV-005 | P3 | Resolved | `5f4d9cc`, `03895ae` | action plan and general-readiness status | The integrity sweep corrected selected document drift but left the milestone ledger titled “NOT STARTED” while listing completed GR-3/GR-5, still said the GR-5 dashboard had not shipped and its channel decision was open, and the GR-1 status still called scatter a future GR-2 target after GR-2 landed. | Cross-document search against the merged code and the adopted sequencing section. | These are low-risk prose errors, but the action plan is the owner's sequencing authority; stale blockers and decisions can send the next session toward already-completed work. | Rename the mixed-state ledger, record the Windows-toast routing decision, state the MCP gate's actual remaining blockers, and reconcile the residual GR-2 wording. | Final text search and diff checks. |

No P0 or P1 issue was found. No issue remains open.

## Independent verification

- Both merge trees were compared to their topic tips: `f778ef3` equals
  `c79d97f`, and `b021499` equals `f5071d8`.
- A deterministic 1,200-case old/new differential sweep covered valid and
  corrupt portfolio numbers, buy/sell/invalid sides, share/order-type errors,
  quotes, pending values, limits, timestamps, earnings windows, and kill
  switches. Approval, exception type, violation codes, messages, and ordering
  were identical (SHA-256
  `755ab4a4c24347c947e9cdc6f88efa24b5de83be54c02a8127853a2010dcfcb2`).
- Confirmed red proof: 2 tests failed for the expected warning-routing and
  terminal-semantics reasons on merged Claude code.
- Immediate green proof: 4 tests passed after correction.
- Focused final suite: 290 passed in 61.03 seconds, covering the registry,
  execution gate/characterization, allocation batch, alerts, CLI/UI,
  paper-evidence lineage, fault runner/matrix, and ML import boundary.
- Fault-drill wrapper: 11/11 fault IDs and all 15 mapped tests passed, with
  zero unmapped tests. The report was verification-only with
  `code_commit=unknown` because the corrected review tree was intentionally
  still dirty before its documentation commits.
- Full final suite: 2,543 passed, 1 skipped, and 26 warnings in 242.85
  seconds under Python 3.12.13. Warnings were the existing WebSockets and
  joblib/NumPy deprecations plus the physical-core detection warning.
- `compileall` and `git diff --check`: clean.

## Safety and scope conclusion

GR-2 is complete after correction. The gate now executes one frozen,
phase-aware, twenty-check registry while preserving the exact pre-refactor
execution result across existing characterization and the independent
differential sweep. The proposal-generation concentration heuristic and
batch/pending-order input calculations remain intentionally distinct and
documented architecture debt; they do not replace or bypass the execution
gate. Paper mode, exact approval, policy-fingerprint checks, storage-level
claims/reservations, ambiguous-outcome reconciliation, the kill switch, and
the LLM/ML import boundary remain in force.

The integrity sweep's corrected warning route now survives a failed CLI
briefing build, while the UI continues to surface the same durable warning
batch. No funded account, broker, operator database, policy, scheduler,
mandate, evidence epoch, or live authority was accessed or changed during
this review. A real broker and a second real Windows toast were deliberately
not exercised.

## Validation environment note

The first two fault-wrapper attempts timed out because the managed sandbox's
default temporary directory did not permit the subprocess to publish its
JUnit XML. Running the unchanged wrapper with `TEMP`/`TMP` directed to the
writable workspace completed in 30.7 seconds and passed all 11 fault IDs.
The direct underlying fault suite also executed all 15 tests successfully;
its only failure was the same denied JUnit output path. No partial artifact
was accepted as a result, and no operational drill row was recorded.

## Counter-review (Claude, 2026-08-03, after PR #131 merged)

Scope: Codex's review range `b021499..d5fab71` (`0167c67` corrections,
`2239c13` records, `a827ea3` handoff, `43f2949` pushed-state record,
`d5fab71` merge of PR #131). Verdict: **the review is confirmed correct at
every point checked; all five findings are genuine and their corrections
verified.** The 8/10-submitted / 9/10-corrected assessment of my work is
accepted as fair — CRREV-002's terminal-semantics defect and CRREV-003's
vacuous assertion were both mine.

| Commit | Disposition |
|---|---|
| `0167c67` | accepted — both behavioral fixes red-verified on my exact pre-correction merged code, both hardening tests mutation-verified (below) |
| `2239c13` | accepted — ledger claims spot-checked against code and diffs; the CRREV-003 "compared against an empty set" claim is verbatim true (`assert {c.value for c in ViolationCode} >= set()`) |
| `a827ea3` | accepted — coherent at write time; its "PUSHED, NOT MERGED" state was made stale by the owner's PR #131 merge (recurring merge-staleness class, same as CRREV-004 itself; superseded by the next handoff) |
| `43f2949` | accepted — pushed-state claim verified against origin |
| `d5fab71` | accepted — tree-identical to `43f2949` (`bd4c883…`), no conflict-resolution delta |

Independent verification performed in a scratch worktree (never the live
tree, which was serving the running Streamlit app):

- **Red proof reproduced** on exact pre-correction `b021499` with the
  corrected tests overlaid: `test_terminal_check_stops_only_when_that_check_adds_a_violation`
  and `test_cli_briefing_surfaces_warnings_before_packet_failure` both
  failed for exactly the claimed reasons — the failure output showed the
  passing terminal check breaking on the earlier `intent_side` violation
  and the empty captured briefing output. Green on `d5fab71`: 36/36.
- **Mutation M1 (CRREV-003 runner binding):** swapping the `intent_side`
  and `order_type` runners in the registry was caught by the new binding
  test while the ORIGINAL frozen-inventory test still passed — proving the
  metadata-only blind spot Codex claimed.
- **Mutation M2 (CRREV-003 AST codes):** an unreachable
  `ViolationCode.NOT_A_REAL_CODE` reference inside a runner was caught by
  the new AST test while all 11 behavioral registry tests stayed green —
  the runtime-unreachable blind spot, closed.
- Both mutations restored finally-safe via `git checkout`; scratch
  worktree removed clean.
- **Full suite on merged `d5fab71`:** 2,543 passed, 1 skipped, 25 warnings
  in 206.66s (Codex's 26th warning was its sandbox's physical-core
  detection notice; the delta is environmental, not behavioral).

No new issues found. GR-2 and Phase 4 are closed with both agents'
independent verification on record.
