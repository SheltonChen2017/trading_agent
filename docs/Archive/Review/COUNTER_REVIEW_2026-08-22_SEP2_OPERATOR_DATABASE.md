# Counter-review — SEP-2 operator-database review

Date: 2026-08-22
Reviewer: Codex
Claude branch: `origin/user/claude/review-sep2-operatordb-20260822`
Exact reviewed head: `07ef9290081ca2920ec73dc73cdc93fbd8386699`
Submission base: `58199138afa28f1b711232b5d441a6adb305f0bb`

## Verdict

**Accepted after correction.** Claude correctly found that a method-name
ledger did not bound the generic `set_system_state` capability, but the first
correction still had two generalized gaps: an ordinary bound-method alias
bypassed the AST check, and `get_system_state` reads were not bounded at all.
The correction at `8839c12` now permits only direct calls whose keys resolve
to reviewed literal prefixes, refuses aliases and reflective access, and pins
both read and write namespaces. No provider, broker, database, task, backtest,
outcome, research look, or evidence epoch was accessed.

The review record identified one P2 and one P3. Its current handoff verdict
restated only the P2, so that current record is corrected without altering
Claude's archived report.

## Ordered commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `b567e942ecb7b4d0c09a32ce6f23abb0ecfd0aab` | **Accepted after correction** | The reserved-write finding and direction are correct. The implementation required generalized read-key and alias/reflection closure at `8839c12`. |
| `07ef9290081ca2920ec73dc73cdc93fbd8386699` | **Accepted after correction** | The review report is complete and reproducible. The current handoff omitted its own SEP2D-002 P3 from the verdict summary; the dated correction restores the exact count. |

## P0–P3 ledger

| ID | Priority | Status | Finding | Reproduction | Resolution |
|---|---:|---|---|---|---|
| CRSEP2D-001 | P2 | Corrected | The new state-key guard inspected only direct `store.set_system_state(...)` calls. `write_state = store.set_system_state; write_state("kill_switch", ...)` passed, and an undeclared `store.get_system_state("ledger_bootstrap")` also passed. | Each mutation left Claude's 20 entry-point guards green on the reviewed head. | `8839c12` rejects aliases/reflection, bounds reads and writes to explicit prefixes, rejects dynamic keys and unused grants, and retains reserved-write exclusion. Both mutations fail after the correction. |
| CRSEP2D-002 | P3 | Corrected in current records | Claude's report records SEP2D-001 P2 and SEP2D-002 P3, while `SESSION_HANDOFF` section 7du said only “one P2.” | Direct comparison of the immutable review report and current handoff. | Current handoff now records both findings; archived evidence remains unchanged. |

P0: 0. P1: 0. P2: 1 corrected. P3: 1 corrected.

## Independent checks

- Exact ancestry reproduced: merge-base and submission base are both
  `58199138afa28f1b711232b5d441a6adb305f0bb`.
- Claude's five-importer ledger and 7/56/12 ownership counts reproduced on the
  reviewed head.
- The two dangerous-direction mutations above were independently run before
  correction and both remained green; after correction both fail closed.
- Focused restored-tree coverage passed before the next implementation tranche.
- Full-suite, compilation, document, secret, topology, and clean-tree results
  are recorded in the final session handoff for the combined one-push tree.

## Remaining scope

This counter-review does not authorize a physical database/task move. SEP-2
continues through bounded ownership reductions while `paper-epoch-006` and all
operational authority remain untouched.
