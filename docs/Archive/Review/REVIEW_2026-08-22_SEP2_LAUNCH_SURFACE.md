# Independent review — SEP-2 launch-surface and mandate-contract tranche

Reviewer: Claude (independent), 2026-08-22
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted after correction. No P0/P1/P2; two P3.**

This is the cleanest tranche of the SEP-2 series. Both findings are records
lagging the code they describe: a test name, and a resume prompt carrying two
contradictory current baselines.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep2-launch-surface-reduction-20260822` |
| Review head (full object name) | `7a21597c38287938a574ae1deddceaf61a0dca14` |
| Base | `0a346a282bf6f4b0c979f6079d1d5df7a5bdffc3` (my prior review head) |
| Review branch | `user/claude/review-sep2-launch-20260822` |

The branch is based on my review head rather than on the merge commit
`a52abd6`. That is correct and loses nothing: `a52abd6`'s second parent **is**
`0a346a2`, and I had already verified `git diff 0a346a2 origin/main` is empty,
so the two trees are identical. Branching from the exact reviewed commit is the
documented relay pattern.

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `a723e94` | counter-review of my provider-ownership review (accepted, no findings) | **accepted** | none |
| `2fb1754` | mandate contract extraction, three scripts repointed, guard driven to zero | **accepted after correction** | SEP2L-001 |
| `7b142a3` | plan tranche record | **accepted** | none |
| `491eef3` | handoff update | **accepted after correction** | SEP2L-002 |
| `7a21597` | final validation record | **accepted** | none |

No merge commit in the range.

## 3. The mandate move — the highest-risk change in the SEP series so far

`assistant/mandate.py` carries the owner's approved mandate. Moving
`PortfolioMandate` to `data/portfolio_mandate.py` could have invalidated the
owner's 2026-08-04 approval, because `assistant/default_mandate.json` stores an
`approved_fingerprint` and `docs/operations/MANDATE.md` states that changing any
behaviour field invalidates it and "requires a new reviewed approval, not an
edit". A fingerprint that incorporated a module or class name would have broken
silently on a module move.

Measured rather than assumed:

| Check | Result |
|---|---|
| Stored `approved_fingerprint` vs recomputed on this tree | **identical** (`693799c0…56487`), status `approved`, `approved_by sheltonchen` |
| `assistant.mandate.PortfolioMandate is data.portfolio_mandate.PortfolioMandate` | **True** |
| `compute_mandate_fingerprint` source references `__module__` / `__qualname__` / `__class__` / `type(` / the class name | **none of them** — the fingerprint is value-derived |
| `DEFAULT_MANDATE_PATH` still resolves to `assistant/default_mandate.json` | **yes**, the default asset stays product-owned |
| `evaluate_live_promotion` (the authority-bearing gate) | **stayed in the assistant**, correctly |

**`validate()` is provably formatting-only.** Its AST differs because an
intermediate `percentages` tuple binding was inlined, so I compared semantics
instead: all **27** string constants (every validated field name and every
error message) identical, both numeric constants identical, and the entire
`If`/`For`/`Compare`/`BoolOp`/`UnaryOp`/`Raise` sequence identical, element for
element. `to_dict` is AST-identical.

**Persistence risk checked.** A moved class breaks stored artifacts that
reference it by module path. `PortfolioMandate` has no pickle or joblib site;
it is persisted through `to_dict()`, which is name-independent. Its only
research-side mention, `backtest/research_report.py:209`, is prose in a
docstring — that module imports the neutral `data.mandate_evaluation`, not the
assistant.

**One behaviour trap that could have hidden here and did not.**
`scripts/run_portfolio_research_report.py` swapped `load_mandate(args.mandate)`
for `load_portfolio_mandate(args.mandate)`, and the neutral loader has no
default path. That would matter if `--mandate` had defaulted through the
assistant module — but the script already constructed its own default pointing
at `assistant/default_mandate.json`, so the same path is passed as before and
the report still scores against the owner-approved mandate.

## 4. SEP2-006 is genuinely closed — the class, not just the named instance

My earlier review recorded a lazy chain from a research-hosted entry point to
the broker module. The previous tranche fixed the named script; this one fixed
the sibling and drove the guard to `== set()`.

I checked whether that actually closes the class or merely the one route, since
`assistant.storage` still reaches six non-assistant entry points:

- a breadth-first trace over first-party imports from **every** research-hosted
  and shared-composition entry point now reaches `alpaca` **nowhere**; and
- `assistant.storage` does **not** reach `execution/` or `alpaca` at all.

So `assistant.operations` was the only path, and the reach is gone rather than
relocated. This closes SEP2-006.

## 5. Other verification

- **Ledger movement is exact and matches the record**: script ownership
  7 / 56 / 12 (composition 13 → 12), declared crossings 9 → 8, data ownership
  19 declared = 19 actual with `portfolio_mandate` as the ninth neutral
  contract and shared provider debt still **0**.
- `data/portfolio_mandate.py` imports nothing from either product.
- Direct cross-product imports **0** and authority→research paths **0** are
  unchanged.
- **All three of Codex's claimed dangerous-direction mutations reproduce**:
  the reclassified research launcher importing the assistant fails product
  ownership; `assistant.operations` added to another research-hosted surface
  fails the zero-tolerance guard; the neutral mandate contract importing the
  assistant fails the shared-kernel direction guard.
- **My own additional mutation**: replacing the facade's `PortfolioMandate`
  with a shadow class is caught by two independent tests
  (`test_neutral_contract_compatibility_facades_preserve_identity` and the new
  `test_assistant_mandate_facade_preserves_contract_identity_and_load_behavior`).
- The owner-approval property is not merely true, it is **pinned**:
  `tests/test_mandate.py::test_default_mandate_is_owner_approved_with_bound_fingerprint`
  already asserts stored equals computed, so a fingerprint-breaking move would
  have failed the suite.

## 6. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP2L-002 | P3 | Closed | `491eef3` | `docs/SESSION_HANDOFF.md` resume prompt | The resume prompt stated **two different current baselines in one paragraph**: the stale "75 script files, 13 composition files and 9 crossings are the current exact baselines" that I wrote last round, immediately followed by the new "current exact SEP-2 surface is 7 assistant / 56 research / 12 composition files and 8 Python crossing roots". The new sentence was appended without retiring the old one. | Both sentences present, eight lines apart, each claiming to be current. | The resume prompt is the first thing a new session reads; two contradictory "current" figures make the reader pick one, and the stale pair understates the progress this tranche made. Dated historical sections legitimately keep the old numbers — an active instruction block must not. | Removed the stale figures and replaced them with the section pointers; the later sentence remains the single current statement. | `test_active_document_consistency.py` 53/53; a grep for the old figures now returns hits only inside dated sections 7dp/7dq, which are correctly never retro-edited. |
| SEP2L-001 | P3 | Closed | `2fb1754` | `tests/test_project_separation_entrypoints.py` | The guard's assertion was correctly strengthened from an exact one-entry ledger to `== set()`, but the function name still read `..._is_an_exact_shrinking_ledger`. A name advertising a ledger, over an assertion demanding emptiness, invites a future change to re-add an entry as though a retained exception were the sanctioned form. | The docstring was updated and is accurate; only the name lagged. | This repository's own lesson set covers exactly this: a consistency test must assert a relationship rather than a current value (CCX-002), and a test that names something must actually test that thing (the tax-lot boundary case). The correct way to satisfy this guard is to remove the import, never to record it. | Renamed to `test_no_entry_point_outside_the_trading_assistant_reaches_broad_operations`; docstring records the transition and says explicitly that re-adding an entry is not the sanctioned remedy. Assertion, scope and behaviour unchanged. | 16/16 green after the rename; mutation reintroducing `assistant.operations` into `run_ml_shadow.py` is still red under the new name. |

## 7. Validation on the final tree

Environment: Python 3.13.14, Windows.

| Check | Result |
|---|---|
| `tests/test_project_separation_entrypoints.py` | 16 passed |
| Focused: entry points + boundary + mandate | 30 passed |
| Complete suite | **4,523 passed / 0 failed / 25 warnings** in 730.99s — unchanged from Codex's 4,523 because a rename is count-neutral |
| `compileall` incl. `research/` | passes |
| `git diff --check` | clean |
| Mutations | 3 Codex claims reproduced; facade-identity and guard-rename mutations verified; all restored |

Codex's submitted-snapshot counts (4,523 tests, 25 warnings, 714.96s, 53/53
active-document) are accepted on its record; I validated the final tree myself.

## 8. Untested surface, stated plainly

- The mandate move is proved by fingerprint equality, object identity,
  AST-level semantic comparison and the existing suites. I did **not** run a
  live promotion evaluation or a real research report end to end.
- The `alpaca`-reachability result is a static first-party import trace; it
  does not prove the absence of a runtime path constructed dynamically, though
  `scripts/` is separately guarded against dynamic and relative import forms.
- `assistant.storage` remains imported by six non-assistant entry points. It
  carries no broker reach, but it is still the mutable operator database that
  plan §3 says no adapter may expose to research code — the largest remaining
  SEP-2 item.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was accessed
  or changed. `paper-epoch-006` is untouched.

## 9. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep2-launch-20260822`. SEP-2 is still not complete and no
feature-milestone entry is written. Remaining: the `assistant.storage`
operator-database boundary across six entry points, per-product launch
surfaces, the residual 12 composition files and 8 crossings, and shrinking the
`data` / `config.py` / `market_analytics.py` shared kernel.
