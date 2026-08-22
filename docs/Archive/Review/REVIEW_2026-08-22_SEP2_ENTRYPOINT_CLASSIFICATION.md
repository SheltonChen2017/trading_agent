# Independent review — SEP-2 entry-point and dependency classification tranche

Reviewer: Claude (independent), 2026-08-22
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted after correction. No P0/P1; two P2, three P3 corrected;
two P3 recorded for the next tranche.**

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep2-entrypoints-data-restart-20260822` |
| Review head (full object name) | `eb2e22f19ebd4fa817583922b0a8378e18bd5f47` |
| Base | `main` `728c7109e0dbe99ce54f0c5f251430b1fca8a2d4` |
| Merge base | confirmed identical to base |
| Review branch | `user/claude/review-sep2-entrypoints-20260822` |
| Ordered range | `ba8d0eb`, `eb2e22f` |

The branch was fetched before review and its remote head resolved to the
object above; no local or moving implementation was reviewed.

## 2. Commit dispositions

Every commit in the range has an explicit disposition.

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `ba8d0eb` | `architecture/entry_points.json`, boundary-manifest status/classification keys, four `requirements/` manifests, widened `test_project_separation_boundary.py` root check, new `tests/test_project_separation_entrypoints.py` | **accepted after correction** | SEP2-001, SEP2-002, SEP2-003, SEP2-005 |
| `eb2e22f` | plan tranche subsection, handoff section 7dn, "what is next" and resume-prompt updates | **accepted after correction** | SEP2-004 |

There is no merge commit in the range.

## 3. What I reproduced independently

Nothing below is carried from the submission's prose; each was measured on the
review tree.

- **Script inventory.** 75 files under `scripts/` (68 `.py`, 7 `.ps1`),
  partitioned 7 trading-assistant / 50 strategy-research / 18 composition.
  Exact, no duplicates, no omissions.
- **Crossing ledger.** Re-derived all 14 Python composition crossings with my
  own AST scanner: **14/14 identical to `declared_python_cross_product_roots`,
  zero differences.**
- **Product launchers are clean.** All 54 product-owned Python launchers — 4
  assistant-owned and 50 research-owned; the remaining 3 assistant-owned
  entries are PowerShell — carry **zero** cross-product imports.
- **Data inventory.** 1 package marker + 6 neutral contracts + 9 shared
  provider debts = 16, and `data/*.py` is 16 files. (The submitted plan prose
  said 15 — see SEP2-004.)
- **Helper honesty.** All four declared non-launch helpers, and the exempted
  `personal_assistant_ui.py`, genuinely lack a `__main__` runner. All 7 `.ps1`
  entries are genuine executable surfaces (`[CmdletBinding…]` or launcher
  headers), not dot-sourced libraries.
- **Dependency reconstruction.** `requirements/development.txt` expands to
  exactly the 13 pins in the legacy `requirements.txt`.
- **Dependency split is factually correct for eager imports.** No module under
  `assistant/`, `execution/`, or `risk/` imports `sklearn`, `joblib`, or
  `databento`; no module under `backtest/`, `ml/`, `research/`, `signals/`,
  `strategies/`, or `baskets.py` imports `alpaca`, `streamlit`, or
  `anthropic`; the shared kernel (`data/`, `config.py`, `market_analytics.py`)
  needs only packages in `common.txt`.
- **Codex's three claimed mutations all reproduce exactly**: a new unclassified
  top-level script fails `test_every_script_is_classified_exactly_once`; a
  `backtest` import added to the assistant-only watchdog fails
  `test_product_entry_points_do_not_gain_cross_product_imports`; an ACER
  licensed-snapshot import added to `assistant/proposals.py` fails
  `test_licensed_research_surfaces_cannot_enter_execution_products`.
- **Hygiene.** `git diff --check` clean over the range; `compileall` including
  `research/` passes; no secret, credential, account identifier, or absolute
  account balance appears in the diff.

**Scope statement.** This tranche changes no runtime import, launcher,
provider call, scheduled task, operator database, deployment, backtest,
research look, or evidence epoch. I verified that independently: the only
non-test, non-documentation files touched are four new `requirements/*.txt`
manifests and two JSON manifests under `architecture/`. `paper-epoch-006` and
the operational checkout are untouched.

## 4. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP2-001 | P2 | Closed | `ba8d0eb` | `tests/test_project_separation_entrypoints.py` (composition ledger) | The ledger records **root packages**, not modules. `declared_python_cross_product_roots` says a research-hosted script imports `assistant`; it cannot distinguish `assistant.runtime_identity` from `assistant.execution_service`. The single most dangerous edit to an existing crossing — repointing it at broker submission, the execution kernel, or the risk gate — changes no declared root and fails no guard. | Mutation: added `from assistant.execution_service import execute_approved_paper_proposal` to `scripts/run_qc_stage0.py` (strategy-research hosted). **All 16 separation guards and all 8 ML import-boundary guards stayed green.** | The plan's target boundary states strategy research does not own broker submission, approvals, reconciliation, or operational authority, and that no adapter may expose a broker, approval token, or execution gate to research code. A guard whose stated purpose is to make new crossings fail is fail-open on the exact direction the milestone exists to prevent. | New `test_entry_points_outside_the_trading_assistant_cannot_import_authority`: every entry point not hosted by the trading assistant must import no module under `authority_roots`. Direct-import scope, stated in the docstring. | Red on the mutation, green restored. Control: the two trading-assistant launchers that genuinely import `assistant.execution_service`, `execution.alpaca_broker`, `assistant.allocation_batch`, and `risk.execution_gate` today still pass, so the guard permits the legitimate case rather than banning the import globally. |
| SEP2-002 | P2 | Closed | `ba8d0eb` | same module, `scripts/` and `data/` inventories | Both inventories used `iterdir()` / `glob("*.py")`, which see only the top level. A Python file added inside a new subdirectory of `scripts/` was therefore **neither classified nor scanned for cross-product imports** — it escaped `test_every_script_is_classified_exactly_once`, `test_product_entry_points_do_not_gain_cross_product_imports`, and `test_composition_crossings_are_an_exact_debt_ledger` simultaneously, because the latter two iterate only over manifest-declared paths. | Mutation: `scripts/zz_mutation_pkg/rogue.py` importing **both** `backtest` and `assistant` — an unclassified entry point with a direct cross-product crossing — **passed 8/8**. | The module docstring states the manifest "is an exact inventory, not an allowlist for silent growth" and that "a new script, a new cross-product import, or a new shared provider module must fail until it is deliberately owned". Reorganizing `scripts/` into subdirectories is on SEP-3's own path, so this is a hole on the route the project is taking. | Added `_source_files()`, which walks recursively and excludes `__pycache__`; used for both inventories and for the licensed-surface scan. | Red on the same mutation, green restored; the 75-file inventory is unchanged on the real tree. |
| SEP2-003 | P3 | Closed | `ba8d0eb` | same module, both crossing tests | Root normalization was asymmetric: the research side applied `Path(root).stem` (needed because `strategy_research` owns `baskets.py`), the assistant side used the raw manifest value. Adding any top-level `.py` module to `trading_assistant`'s `owned_roots` would silently blind that half of the guard, since `"module.py"` can never equal an import root. The precedent for a `.py` owned root already exists in the sibling product. | Matched-control mutation. Assistant-owned script importing research-owned `baskets.py` → **fails** (stem applied). Research-owned script importing an assistant-owned top-level `.py` module → **passes** (blind). Same defect class, opposite direction, only one side caught. | A latent fail-open in a boundary guard, where the triggering condition is a manifest edit the sibling product already demonstrates as normal. | Added `_product_import_roots()` and used it for both products. | Red on the assistant-side mutation after the fix, green restored. |
| SEP2-004 | P3 | Closed | `eb2e22f` | `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md` | The tranche record says "all **15** `data/*.py` files are classified as one package marker, six neutral contracts, or nine named shared-provider debts". Its own enumeration sums to 16, and `data/*.py` is 16 files. | `ls data/*.py \| wc -l` → 16; manifest categories 1 + 6 + 9 → 16. | This repository pins document truth with guard tests and treats counts as load-bearing; an inventory record whose total contradicts its own parts is exactly the drift the classification exists to remove. (The handoff's section 7dn states the same fact without a total and is correct.) | Corrected to 16. | Enumeration, manifest, and filesystem now agree; `test_active_document_consistency.py` 53/53. |
| SEP2-005 | P3 | Closed | `ba8d0eb` | `requirements/strategy-research.txt` | `scripts/run_filing_extraction.py` is classified strategy-research and its extraction path imports `anthropic`, which only `requirements/trading-assistant.txt` pins. A research-only install imports the script successfully and fails at call time. | Transitive closure over research-hosted entry points; import site is `scripts/run_filing_extraction.py:153`. | The milestone bullet is "give each product its own launch surface and **dependency declaration**". A declaration that omits a package one of its own entry points needs is incomplete, even when the failure is deferred. | Recorded as a comment naming the file, the laziness, and the open ownership question. **No package was moved**: which product owns the LLM extraction surface is a SEP-2 ownership decision, not a reviewer's call. | Comments are stripped by `_requirements()`, so `test_product_dependency_declarations_reconstruct_the_legacy_environment` stays green (9/9 module, 78/78 focused). |
| SEP2-006 | P3 | **Open — recorded, not fixed** | pre-existing | `scripts/run_ml_evidence_supervisor.py` | Measured transitive chain from a research-hosted entry point to the broker module: `scripts/run_ml_evidence_supervisor.py → assistant/operations.py → assistant/readiness.py → execution/alpaca_broker.py`. | Breadth-first trace over first-party imports. Every hop is function-local/lazy (`readiness.py:269`; every `alpaca` import in `execution/alpaca_broker.py` is function-local and commented "package optional until used"), so nothing breaks and no package is required. | Not introduced by this commit and not a defect in it. The reach is operational-health composition, not trade authority: the supervisor writes health reports and alerts only, and human approval, policy fingerprinting, the execution gate, and reconciliation are untouched. Naming the exact chain tells the next tranche where to cut. | None in this review. The direct-import guard added for SEP2-001 deliberately does not fail on it; the docstring says so. | Recorded here and in the plan's next-tranche text. |
| SEP2-007 | P3 | **Open — recorded, not fixed** | `ba8d0eb` | `test_product_dependency_declarations_reconstruct_the_legacy_environment` | The dependency test asserts the manifests against **each other** and against hardcoded literals; it never compares them to actual imports. If `assistant/` began importing `sklearn`, or `ml/` began importing `streamlit`, the test would stay green. | Read of the test; the split was measured correct today (section 3). | A self-referential assertion cannot detect drift between the declaration and the code it describes. | None. An import-based guard is worth adding, but a transitive resolver must model lazy imports correctly (see SEP2-006) or it will overstate requirements, and that is more than a classification tranche should carry. | Recommended for the next tranche. |

Resolved items are retained above rather than deleted.

## 5. A correction to my own reasoning, recorded

My first pass suspected a **P2**: that neither product's declared environment
could run its own entry points, because `anthropic` is reachable from
research-hosted scripts and `alpaca` is reachable from research-hosted scripts
through `assistant/readiness.py`. That was wrong, and the reason matters.

My AST closure treated every import as eager. Both are deliberately lazy —
`scripts/run_filing_extraction.py:153` carries an explicit comment that it
"Mirrors `assistant/llm/anthropic_provider.py`'s established pattern: lazy",
and every `alpaca` import in `execution/alpaca_broker.py` is function-local
and commented "package optional until used". The environments are installable
and the entry points import fine.

What survived the check is narrower and real: SEP2-005 (an undeclared
call-time dependency) and SEP2-006 (a boundary reach, not a packaging fault).
The generalizable rule: **a static import graph answers "what could be
imported", not "what must be installed"; before calling a dependency
declaration broken, read the import site and check whether it is module-level.**

## 6. Milestone assessment

The submission is explicit that this is "a classification and dependency
tranche, not completion of SEP-2", and that is accurate. Measured against the
plan's four SEP-2 bullets:

| SEP-2 bullet | State |
|---|---|
| classify every `scripts/` entry point | **Done.** 75/75 owned exactly once, enforced recursively after SEP2-002. |
| give each product its own launch surface and dependency declaration | **Partial.** Dependency declarations exist and reconstruct the legacy environment. Ownership of launchers is *declared*; no per-product launcher has been created, and 18 files remain explicit composition. |
| split shared data access into explicit interfaces and product-owned implementations | **Not started, honestly declared.** Nine `data/` provider modules remain shared debt, named and frozen against growth. |
| keep licensed datasets on the research side | **Done and guarded.** ACER and Databento surfaces cannot be imported by `assistant/`, `execution/`, or `risk/`. |

The zero-direct-crossing and zero-authority-exception invariants from SEP-1
are intact: `allowed_direct_cross_product_imports` and
`allowed_authority_research_paths` both remain empty, and
`test_project_separation_boundary.py` passes unchanged in substance.

## 7. Validation on the final tree

Environment: Python 3.13.14, Windows.

| Check | Result |
|---|---|
| `tests/test_project_separation_entrypoints.py` | 9 passed (8 submitted + 1 added) |
| Focused set: separation entrypoints + separation boundary + active-document + ML import boundary | 78 passed |
| Complete suite | **4,515 passed / 0 failed / 25 warnings** in 638.69s |
| `compileall` incl. `research/` | passes |
| `git diff --check` | clean |
| Mutations | SEP2-001 red/green; SEP2-002 red/green; SEP2-003 red/green with matched control; all three restored byte-identical |

Codex's submitted-snapshot counts (16/16 focused, 69/69 combined, 4,514 full,
25 warnings, 804.49s) are accepted on its record; I reproduced the 16/16 and
the 69/69 composition (16 + 53) directly and validated the final tree myself.

## 8. Untested surface, stated plainly

- The classification is a **static** judgement. No entry point was executed;
  "launch surface" is established from `__main__` presence, PowerShell
  headers, and source reading, not from running anything.
- The `.ps1` entries are classified and host-assigned but no guard inspects
  their contents, so a PowerShell script could acquire a cross-product or
  authority dependency without failing any test.
- All import analysis is static. There are currently no dynamic imports
  (`importlib`, `__import__`, `exec`) and no relative imports anywhere in
  `scripts/` — I verified this — so the AST scope is complete today, but it
  would not survive their introduction.
- SEP2-006's transitive chain is measured but its runtime consequence is not:
  I did not determine whether `run_ml_evidence_supervisor` actually reaches
  the lazy broker call in practice.
- No provider, broker, licensed row, QuantConnect account, operator database,
  scheduled task, deployment, backtest, outcome, research look, or evidence
  epoch was accessed or changed during this review.

## 9. Next step

Codex counter-reviews this review's corrections at the exact pushed head of
`user/claude/review-sep2-entrypoints-20260822`. SEP-2 is **not** complete and
no feature-milestone entry is written for it. After the chain closes, the next
tranche owns or interfaces the nine shared provider modules, reduces the 18
composition files rather than broadening their ledger, and should consider
SEP2-006 and SEP2-007.
