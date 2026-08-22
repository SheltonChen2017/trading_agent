# Independent review — SEP-2 provider-ownership tranche and counter-review round

Reviewer: Claude (independent), 2026-08-22
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted after correction. No P0/P1/P2; three P3 corrected.**

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep2-provider-ownership-20260822` |
| Review head (full object name) | `809aa0c9ca8002ff8df1eefbaff51518ab7f94fc` |
| Base | `cd11beaf4dbf40a852928944ef11b23849fd3493` (my prior review head) |
| Merge base | confirmed identical to base |
| Review branch | `user/claude/review-sep2-provider-20260822` |

Codex branched from my exact pushed review head, so the relay is clean and no
work was rebased away.

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `3cdb2ed` | counter-review correction: expand parent-package `from` imports in the scanner | **accepted** | none — this is a correct finding against my own work, see §3 |
| `91aefe5` | counter-review record | **accepted** | none |
| `de2bd1a` | provider ownership, runtime-identity and alert extraction, script repointing, six new guards | **accepted after correction** | SEP2P-001, SEP2P-002 |
| `86822c7` | plan tranche record | **accepted after correction** | SEP2P-003 |
| `bb9396d` | handoff update | **accepted** | none |
| `809aa0c` | final validation record | **accepted** | none |

No merge commit in the range.

## 3. The counter-review finding against my own correction: CONFIRMED

Codex's CRSEP2-001 says my SEP2-001 authority guard was still bypassable,
because `_imported_modules` kept only `node.module` for an `ImportFrom` — so
`from assistant import execution_service` yielded `"assistant"`, never
`"assistant.execution_service"`, and my guard's prefix match could not fire.

I verified this against my own head rather than accepting it:

| Scanner | Mutation `from assistant import execution_service` in a research-hosted script |
|---|---|
| Mine (`cd11bea`) | **passed** — guard blind |
| Codex's corrected (`3cdb2ed`) | **failed** — guard fires |

The finding is correct and the fix is right. It is worth naming what happened:
this is the **same granularity defect I raised against Codex's ledger**,
reproduced inside my own correction one step down — I moved from root
granularity to module granularity but left the one spelling that collapses
back to a root. The same hole also let `from research import acer` evade the
licensed-surface guard, which Codex's shared-helper fix closes at both sites.

## 4. What I reproduced independently

- **The moved bodies are behaviourally identical.** `data/runtime_identity.py`
  is byte-identical to the former `assistant/runtime_identity.py` from the
  first line after its module docstring onward; only the docstring's opening
  sentence was reworded to be product-neutral. `append_alerts_jsonl` moved
  with one cosmetic line-wrap and no semantic change.
- **The path-depth assumption survived the move.** `_REPOSITORY_ROOT` is
  `Path(__file__).resolve().parent.parent`; `data/` sits at the same depth as
  `assistant/`, and I confirmed at runtime that it still resolves to the
  repository root. A move one level deeper would have silently pointed every
  lineage check at the wrong tree, so this was checked rather than assumed.
- **Facade identity is real, not nominal.** `assistant.runtime_identity.current_commit
  is data.runtime_identity.current_commit`, the same for
  `RuntimeIdentityError`, and `assistant.operations.append_alerts_jsonl is
  data.operational_alerts.append_alerts_jsonl` — all `True`, so existing
  `except RuntimeIdentityError` handlers keep working.
- **The shared kernel does not import a product.** Both new `data/` modules
  import only the standard library.
- **The ownership assignments match reality.** For each of the six
  product-owned providers I listed every product module that imports it:
  `corporate_actions`, `event_data`, `price_source` are imported only by
  `assistant/`; `earnings_data` only by `ml/` and `signals/`;
  `analyst_data` and `pit_universe` have no product importer at all. **No
  provider is imported by its non-owner.**
- **Ledger movement is exact**: composition files 18 → 13, declared Python
  crossings 14 → 9, `shared_provider_debt` 9 → 0, replaced by 3 assistant-owned
  + 3 research-owned + 3 provider-neutral services each carrying a written
  rationale. `data/*.py` is now 18 files and the manifest accounts for all 18.
- **Both of Codex's claimed dangerous-direction mutations reproduce**: an
  assistant import of a research-owned provider fails the ownership guard, and
  an assistant import of undeclared `joblib` fails the dependency guard.

Codex also closed two items I had recorded as open in the previous round —
**SEP2-007** (the dependency manifests are now compared against actual product
and hosted-launcher imports, with a declared `platform_provided_imports`
escape for QuantConnect's injected `AlgorithmImports`) and the dynamic-import
gap I had listed only as untested surface (`scripts/` now refuses relative
imports, `__import__`, `importlib.import_module`, and `exec`). The dependency
guard is deliberately **direct-import scoped**, which is the correct choice:
a transitive version would demand `alpaca-py` in the research manifest for a
lazy import that never executes there.

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP2P-001 | P3 | Closed | `de2bd1a` | `tests/test_project_separation_entrypoints.py` | `test_ml_evidence_supervisor_avoids_broad_operational_authority_reach` named the single repaired file. Its sibling `scripts/run_ml_shadow.py:36` holds the identical `from assistant.operations import append_alerts_jsonl` and therefore the identical lazy reach through `assistant.readiness` to `execution/alpaca_broker.py`. A guard that pins one filename leaves a new instance free and cannot notice when the last one is removed. | With `run_ml_shadow.py` unchanged and carrying the import, the suite passes 16/16. Adding the same import to a third research script (`run_overlay_shadow.py`) also passed under the submitted guard. | This is the repository's own standing watch item — "a guard added to one generator is not added to its sibling" (`OPERATIONAL_FACTS.md` §3, FCS-001) — combined with CCX-002's rule that a consistency test must assert a relationship, not a current value. | Replaced with an exact shrinking ledger over every non-assistant-hosted entry point. | Three-direction mutation: new importer **red**; repaired supervisor regressing **red** (Codex's protection retained); removing the final ledger entry **red**, so the debt must be driven down deliberately. Restored **green** 16/16. |
| SEP2P-002 | P3 | Closed | `de2bd1a` | `assistant/operations.py:5` | Moving `append_alerts_jsonl` out removed the only consumer of `import json`, leaving it orphaned. | AST: zero `json` Name references and zero `json.<attr>` uses remain. (A substring count is misleading here — `append_alerts_jsonl` contains "json".) | A dead import created by this commit is in scope for it, and it misrepresents the module's dependencies. | Removed. | `assistant.operations` imports cleanly; focused operations/boundary/document/runtime set 106 passed. |
| SEP2P-003 | P3 | Closed | `86822c7` | `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md` | The tranche record said the supervisor change removed "the recorded lazy reach through readiness to the broker module". It removed the exact chain SEP2-006 named, but not the class: the same reach persists through `scripts/run_ml_shadow.py`. | Breadth-first trace after the tranche returns `scripts/run_ml_shadow.py -> assistant/operations.py -> assistant/readiness.py -> execution/alpaca_broker.py`. | An accurate record is the point of the tranche; a reader would take the sentence as the class being closed. Codex's own counter-review record is careful here — it says SEP2-006 "remains planned separation debt" — so the two documents were in tension. | Reworded to name the exact chain removed and the residual instance, and to point at the new ledger. | `test_active_document_consistency.py` passes; the plan and counter-review record now agree. |

Resolved items are retained rather than deleted.

## 6. Milestone assessment

Measured against the plan's SEP-2 bullets, this tranche moves the third one
from "not started" to substantially done:

| SEP-2 bullet | State after this tranche |
|---|---|
| classify every `scripts/` entry point | **Done**, recursively enforced, and now also proof against dynamic/relative import forms. |
| own launch surface and dependency declaration per product | **Improved.** Declarations are now checked against actual imports rather than only against each other. Ownership is declared; no separate per-product launcher exists yet. |
| split shared data access into explicit interfaces and product-owned implementations | **Substantially done.** Nine shared debts became 3 + 3 product-owned and 3 provider-neutral services with written rationales; a guard prevents either product importing the other's implementation. The implementations keep their `data.*` locations for compatibility, so this is ownership, not physical separation. |
| keep licensed datasets on the research side | **Done and now harder to evade**, since the licensed-surface guard sees parent-package spellings. |

SEP-1's invariants are intact: `allowed_direct_cross_product_imports` and
`allowed_authority_research_paths` are both still empty.

**One forward-looking note, not a defect.** `data/corporate_actions.py` is
assigned to the trading assistant on today's evidence, which is correct — only
`assistant/context_builder.py` imports it. But ACER's own data requirements
(plan §4.1 item 6) call for splits, dividends and other corporate actions on
the **research** side for total-return outcomes. When that work starts, this
assignment will need revisiting rather than being treated as settled.

## 7. Validation on the final tree

Environment: Python 3.13.14, Windows.

| Check | Result |
|---|---|
| `tests/test_project_separation_entrypoints.py` | 16 passed |
| Focused: operations + separation entrypoints + separation boundary + active-document + ML boundary + runtime identity | 106 passed |
| Complete suite | **4,522 passed / 0 failed / 25 warnings** in 719.15s — unchanged from Codex's 4,522 because this round replaced one guard with another rather than adding one |
| `compileall` incl. `research/` | passes |
| `git diff --check` | clean |
| Mutations | CRSEP2-001 re-verified against my own head; both Codex claims reproduced; SEP2P-001 verified in three directions; all restored |

Codex's submitted-snapshot counts (26/26 counter-review focused, 76/76, 129/129,
4,522 full, 25 warnings, 671.62s) are accepted on its record; I validated the
final tree myself.

## 8. Untested surface, stated plainly

- The runtime-identity move is proved by source equivalence, runtime object
  identity, and the existing suites. I did **not** execute a real evidence
  capture or epoch operation against the moved module, so its behaviour under
  a genuine dirty-tree or ignored-source condition is covered only by the
  existing unit tests, not by an operational run.
- `data/analyst_data.py` and `data/pit_universe.py` have no product importer,
  so their ownership assignment rests on their subject matter and script
  callers, not on an import measurement.
- The `.ps1` composition entries are host-assigned but no guard inspects their
  contents.
- The dependency guard is direct-import scoped by design; a package needed
  only through another product's module is not detected, which is correct for
  lazy imports but means the manifests do not describe transitive closure.
- No provider, broker, licensed row, QuantConnect account, operator database,
  scheduled task, deployment, backtest, outcome, research look, or evidence
  epoch was accessed or changed. `paper-epoch-006` is untouched.

## 9. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep2-provider-20260822`. SEP-2 is still not complete and no
feature-milestone entry is written. Remaining: per-product launch surfaces, a
further reduction of the 13 composition files and 9 crossings, and driving the
broad-operational-reach ledger to empty.
