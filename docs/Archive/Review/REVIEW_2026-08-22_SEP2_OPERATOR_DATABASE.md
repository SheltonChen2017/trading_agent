# Independent review — SEP-2 operator-database boundary tranche

Reviewer: Claude (independent), 2026-08-22
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted after correction. No P0/P1; one P2 and one P3 corrected.**

The P2 is a fail-open in the artifact whose whole purpose is to bound the
operator-database surface: a granted generic method subsumed the persistent
kill switch that the same ledger deliberately withholds.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep2-operator-db-boundary-20260822` |
| Review head (full object name) | `58199138afa28f1b711232b5d441a6adb305f0bb` |
| Base / merge-base with `main` | `b4b896f8606f7ce520b13fcd4d71f68793328e34` (my prior review head) |
| Review branch | `user/claude/review-sep2-operatordb-20260822` |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `03b4cfa` | counter-review record of my launch-surface review | **accepted** | none |
| `9b3836d` | corrects my handoff's finding count | **accepted — a correct finding against my own work** | see §3 |
| `0e98d42` | operator-DB ledger and guard, `StrategyOperationalStore` protocol, `verify_research_report` move | **accepted after correction** | SEP2D-001 |
| `018d7ba` | plan tranche record | **accepted** | none |
| `5819913` | handoff update and validation record | **accepted after correction** | SEP2D-002 |

No merge commit in the range.

## 3. Codex's finding against my own review is correct

`9b3836d` corrects handoff section 7ds from "one P3" to "two P3". Verified at
my own head `b4b896f`: the handoff said "one P3" in three places and described
only the test-name finding, while my review report said "two P3" and carried
the full SEP2L-002 ledger row.

This is my error and I accept it without qualification. I found SEP2L-002 late
in the round, updated the review report's verdict and ledger, and did not carry
the change back into the handoff. The irony is exact: **SEP2L-002 was itself a
finding about a document contradicting itself on a current figure, and I
introduced the same defect class into my own records while closing it.** The
rule I take from it is narrower than "be careful": when a finding is added
after a verdict line is already written, the verdict line and every document
that restates it are part of the fix, not commentary on it.

## 4. What I verified independently

**The `StrategyOperationalStore` protocol is satisfied.** The change is
annotation-only, and Python does not enforce annotations, so the real question
is whether the concrete class actually provides the surface. All six protocol
methods exist on `AssistantStore` with **matching parameter lists**, and
`issubclass(AssistantStore, StrategyOperationalStore)` is `True` under the
`runtime_checkable` protocol.

**The `verify_research_report` move is a clean move, not a reimplementation.**
Its body is byte-identical to the original in `backtest/research_report.py`.
This matters more than an ordinary move: the function verifies an evidence
digest, so any drift in `json.dumps` arguments between writer and verifier
would silently invalidate previously-good reports or accept tampered ones. The
writer (`build_research_report`) is unchanged and the verifier's serialization
is identical, so they still agree. The legacy export is preserved —
`backtest/research_report.py:24` re-imports it — and the new test pins **object
identity** between the legacy and neutral names, matching the convention used
throughout SEP-1.

**No orphaned imports.** Removing the function from `backtest/research_report.py`
left `json` and `hashlib` still used (4 attribute uses each), unlike the
`assistant/operations.py` case I found two tranches ago.

**Ledger movement matches the record exactly**: script ownership unchanged at
7 / 56 / 12, declared Python crossings **8 → 7** (the personal-assistant runner
drops its `backtest` crossing), direct non-assistant `assistant.storage`
importers **6 → 5** (`scripts/product_composition.py` becomes type-only and is
recorded under `removed_type_only_importers`).

**The tranche's claims are honest about scope.** The ledger's own status is
`sep2-exact-boundary-pending-physical-split` with
`physical_split_authorized: false`, and the plan record says the tranche does
not claim SEP-2 complete. It pins the boundary rather than removing it, and
says so.

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP2D-002 | P3 | Closed | `5819913` | `docs/SESSION_HANDOFF.md` resume prompt | The tranche reduced the Python crossing ledger from 8 to 7 and the operator-database importers from 6 to 5, and said so in its own dated section 7dt, but the resume prompt's "current exact SEP-2 surface" line was left at **8** crossing roots. | Measured: `declared_python_cross_product_roots` holds 7, and the handoff commit's diff does not touch the resume-prompt figure. | The resume prompt is the first thing a new session reads, so a stale "current" figure there is read as fact. This is the same stale-current-figure class as SEP2L-002 — which Codex had just corrected in my own records — so it is worth naming plainly rather than fixing quietly: the recurring pattern is that a tranche updates its own dated section and leaves the standing instruction block behind. | Updated to 7 crossing roots, added the 5 bounded operator-database importers, and recorded the state-key rule so the next reader inherits the capability principle rather than a method list. | `test_active_document_consistency.py` 53/53; the figure now matches the manifest. |
| SEP2D-001 | **P2** | Closed | `0e98d42` | `architecture/operator_database_access.json`, `tests/test_project_separation_entrypoints.py` | The ledger enumerates each grantee's exact `AssistantStore` method surface, and deliberately does **not** grant `set_kill_switch`. But it does grant the generic `set_system_state` to `scripts/run_ml_shadow.py` and `scripts/run_ml_evidence_supervisor.py`, and `AssistantStore.set_kill_switch` is literally `self.set_system_state("kill_switch", {...})`. `get_kill_switch()` is a plain read of the same key. The withheld capability is therefore fully reachable through the granted one — along with `ledger_bootstrap`, `last_order_reconciliation`, the backup and restore-drill markers, and the trade-stream state. The guard compares **method names only** (`node.attr in public_methods`) and never inspects the key argument. | Mutation: adding `store.set_system_state("kill_switch", {"active": False, "reason": ""})` to a granted research-hosted script — disarming the persistent kill switch — passed **all 35** separation, boundary and ML-import guards. | The kill switch is the execution gate's terminal check (`risk/execution_gate.py`, `terminal=True`), and the separation plan's §3 states that no adapter may expose a broker, approval token, or **execution gate** to research code. An allowed method name is not an allowed capability; a ledger that claims to be exact must bound the capability, not the spelling. | The ledger now declares the **nine** assistant-reserved state keys and, per grantee, the literal key prefixes it may write. New guard `test_granted_state_writes_cannot_reach_assistant_reserved_keys` requires every `set_system_state` key to resolve to a literal prefix within the declared prefixes, refuses any key it cannot bound statically, and refuses any declared prefix that could produce a reserved key. | Four directions, each red then green: `kill_switch` write, `ledger_bootstrap` write, a fully dynamic key, and an ungranted script beginning to write state (which fails two guards). Real tree green 20/20. |

**What this finding is not.** No current script wrote a reserved key — both
write only namespaced heartbeats (`ml_shadow_…`, `ml_evidence_supervisor_heartbeat:…`),
which is why this is a latent fail-open rather than an active exposure, and why
it is P2 rather than P1. The exposure also predates this tranche, since these
scripts already imported `AssistantStore`. What makes it a defect *in* this
tranche is that the tranche's stated purpose is to define the exact permitted
surface, and the enumeration it produced does not actually bound it.

## 6. Validation on the final tree

Environment: Python 3.13.14, Windows.

| Check | Result |
|---|---|
| `tests/test_project_separation_entrypoints.py` | 20 passed (19 submitted + 1 added) |
| Complete suite | **4,527 passed / 0 failed / 25 warnings** in 817.78s (Codex's 4,526 plus my added guard) |
| `compileall` incl. `research/` | passes |
| `git diff --check` | clean |
| Mutations | SEP2D-001 verified in four directions; **all three of Codex's claimed mutations reproduce** (new `assistant.storage` importer, widened method surface, restored personal-assistant `backtest` crossing); all restored |

Codex's submitted-snapshot counts (83/83 focused on my tree, 130/130
implementation, 53/53 active-document, 4,526 full, 25 warnings, 854.23s) are
accepted on its record.

**A correction to my own verification.** My first attempt at Codex's new-importer mutation added `assistant.storage` to `scripts/run_overlay_shadow.py` and passed 20/20 — but that script is already a declared ledger member, so it was not a new importer and the mutation was invalid, not the claim. Redone against research-owned `scripts/run_qc_stage0.py`, which is outside the ledger, it fails two guards as claimed. A mutation that does not actually create the condition under test proves nothing about the guard.

## 7. Untested surface, stated plainly

- The protocol change is annotation-only; Python enforces nothing at runtime.
  I proved structural satisfaction statically and via `issubclass`, but no test
  passes a deliberately non-conforming object through the production path.
- My new guard bounds `set_system_state` keys **statically**. A key assembled
  at runtime from a non-literal source is refused rather than analysed, which
  is the correct direction but means the guard reasons about source text, not
  execution.
- The guard covers `set_system_state` only. Other generic writers on
  `AssistantStore`, if any were granted in future, would need the same
  treatment — the ledger records the principle in its `boundary_note` so the
  next grant is judged on capability rather than spelling.
- `assistant.storage` is still imported by five research-hosted entry points.
  This tranche bounds that surface; it does not remove it.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was accessed
  or changed. `paper-epoch-006` is untouched.

## 8. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep2-operatordb-20260822`. SEP-2 remains incomplete and no
feature-milestone entry is written. Remaining: removing rather than bounding
the five operator-database crossings, per-product launch surfaces, the residual
12 composition files and 7 crossings, and shrinking the shared kernel.
