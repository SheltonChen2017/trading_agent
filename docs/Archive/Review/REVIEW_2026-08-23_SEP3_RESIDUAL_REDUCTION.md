# Independent review — SEP-3 second dry run and test-partition tranche

Reviewer: Claude (independent), 2026-08-23
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted after correction. No P0/P1; one P2 and one P3 corrected.**

The P2 is a residual neither dry run measured: the declared partition strands
ten assistant-needed `data` modules in the research repository — the
mandate-fingerprint pair among them. It was present in the **first** dry run
too, which my own previous review accepted; §4 records that plainly.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep3-residual-reduction-20260823` |
| Review head (full object name) | `e03a69fcd0585db49363e4a9b62f19fde56126ad` |
| Base | `18afbf4045ceb4f00be5d42e4f66d582ea195e61` (my prior review head; tree-identical to merged `main` `bc8900a`, verified) |
| Review branch | `user/claude/review-sep3-residuals-20260823` |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `ab91271` | hardens my finding-ID grammar (CRSEP3R-001) | **accepted — a correct finding against my own work** | see §3 |
| `089fa53` | counter-review record of my previous round | **accepted** | none |
| `edb1e1d` | handoff for the second review round | **accepted** | none |
| `b15aac8` | test-partition implementation: full-module-name classification, shared-package behavior suite | **accepted** | none |
| `4e1aae4` | second dry-run manifest (schema 2) and validator rewrite | **accepted after correction** | SEP3R-001, SEP3R-002 |
| `3a734a6` | plan record for the second dry run | **accepted** | none |
| `e03a69f` | handoff finalization | **accepted** | none |

No merge commit in the range.

## 3. Codex's finding against my guard is correct — verified on my head

CRSEP3R-001: my generalized finding-ID pattern `\bSEP[23][A-Z]?-\d{3}\b`
permits at most one letter after the milestone digit. Verified on my exact
head `18afbf4`: `SEP3X-001` matches, but round-qualified forms **`SEP3CR-001`
and `SEP3CR2-002` do not** — and adjacent separation chains already use
multi-part suffixes, so the guard could again pass while a finding was absent
from the handoff. Codex's correction `[A-Z0-9]*` accepts them, and I probed
the over-match direction too: `SEPTEMBER-123` and `STEP3-001` still refuse,
because a `2`/`3` must immediately follow `SEP`. Accepted.

## 4. SEP3R-001 (P2): the declared partition strands ten assistant-needed modules

**The finding.** `data_destination` sends 14 `data` modules to
`strategy_research`. Cross-checking every module against what actually imports
it — product packages **plus each product's owned scripts**, measured by AST
over full module names — shows **ten** of them are imported from the
trading-assistant side:

| Module | Needed by (examples) | Also imported by research? |
|---|---|---|
| `data.mandate_evaluation` | `assistant/mandate.py` | yes |
| `data.portfolio_mandate` | `assistant/mandate.py` | no |
| `data.runtime_identity` | `assistant/runtime_identity.py` | no |
| `data.operational_alerts` | `assistant/operations.py` | no |
| `data.market_data` | `assistant/context_builder.py`, `assistant/macro_context.py`, `assistant/portfolio_history.py` | yes |
| `data.portfolio_metrics` | `assistant/paper_evidence.py` | yes |
| `data.price_target_data` | `assistant/stock_lookup.py` | yes |
| `data.research_statistics` | `assistant/research_looks.py` | yes |
| `data.macro_data` | `assistant/macro_context.py` | no |
| `data.filing_extraction` | `scripts/run_filing_extraction.py` (assistant-owned) | yes |

Executed as declared, the extraction would break the trading assistant at
import time — including the **owner-approved mandate fingerprint path** and
the **evidence-lineage identity** — or force exactly the cross-repository
dependency the plan's objective forbids ("operating the assistant should not
require importing the whole research stack"). Five of the ten are imported by
**both** products, so a single-repository destination strands one side
whichever way it points; those are the modules SEP-2 classified as *neutral*,
and neutrality is precisely why no single product repository can own them.

**Why P2 and not P1.** Nothing executes this partition:
`physical_extraction_authorized` is `false`, other declared blockers stand,
and no runtime behavior changed. But the dry run's entire purpose is to
surface blocking product crossings before the owner authorizes extraction —
the plan says "only after a dry run reports no blocking product crossings may
a separately authorized migration create the research repository" — and both
dry runs **reported nothing** about these ten. A validation artifact that
passes silently on the largest remaining crossing fails its definition of
done.

**Also a gap in my own earlier review, stated plainly.** The destinations are
byte-identical to the first dry run's, which I reviewed as "accepted, no
findings". My untested-surface section disclosed the class ("the validator…
does not prove that a real extraction would produce two working
repositories") but I did not run the one measurement that would have found
it: destination versus importer. This round did.

**The correction — deliberately not a partition decision.** The validator now
computes the stranded set from the candidate commit (product packages plus
owned scripts, full module names), requires
`known_blockers.stranded_data_modules` to match it **exactly** — an
under-declared *and* an over-declared list both refuse, so the ledger is
driven down by fixing modules, never by editing the declaration — and reports
the set in its result. Where each module ultimately goes (shared package,
assistant ownership, or a removed import) is partition design for a later
reviewed tranche and in some cases an owner call; note the tiny-package route
is closed for `data.market_data`-class modules, whose vendor imports the
shared allowlist correctly refuses.

**Verification.** Measured set == declared set on the candidate commit;
mutation disabling the staleness check turns both refusal tests red; restored
green 16/16.

## 5. SEP3R-002 (P3): a duplicate dict key hid an incomplete edit

`test_second_extraction_dry_run_is_exact_and_not_authorized` asserted
`destination_counts` with **both** `"shared_contracts": 3` and
`"shared_contracts": 4` in one literal. Python keeps the later duplicate
silently, so the assertion passed while the stale `3` sat as dead text — an
incomplete edit that looked like a double-check. Removed, with a comment. The
asserted value `4` was and is correct.

## 6. What I verified independently on the tranche itself

- **The claimed first-validator defect is real.** Old line 232:
  `touches_shared = bool(roots & shared_roots) or "data" in roots` — any test
  importing anything under `data.*` counted as shared. The replacement
  resolves **full module names** against the ownership manifests
  (`product_roots`, `product_top_level_files`, `data_destination`,
  `source_to_package`, script ownership), which is the correct fix.
- **All counts reproduce on my own validator run**: candidate `b15aac8`, 743
  paths, destinations 498 / 241 / 4, tests 83 / 70 / 1 / 54, status refusing
  extraction.
- **The validator remains genuinely read-only** after its rewrite: git
  plumbing only (`show`, `ls-tree`, `cat-file -t`, `rev-parse`), no
  filesystem writes; executed, tree unchanged afterwards.
- **The shared-package behavior suite is real behavior**, not import
  ceremony: it pins `EvidenceStatus` values, exact-decimal round-trips, and
  research-result contract refusals.
- The relay base is lossless: `18afbf4` and merged `main` `bc8900a` share one
  tree.

## 7. Validation on the final tree

| Check | Result |
|---|---|
| `tests/test_sep3_extraction_dry_run.py` + `tests/test_shared_contract_package.py` | 16 passed |
| Complete suite | **4,550 passed / 0 failed / 25 warnings** in 913.67s — Codex's 4,547 plus three stranded-module tests, rerun clean on the final tree |
| `compileall` incl. `research/` | passes |
| `git diff --check` | clean |
| Mutations | CRSEP3R-001 verified on my own head both directions; SEP3R-001 staleness check reverse-mutated red/green; over-declaration refusal pinned |

## 8. Untested surface, stated plainly

- The stranded-set measurement is **direct-import** scope over first-party
  files at the candidate commit. A dynamic or string-built import would
  escape it; `scripts/` is separately guarded against those forms, product
  packages are not.
- The measurement treats composition-hosted scripts as neither side, which
  under-counts nothing today (all ten stranded modules surface through
  packages or owned scripts) but is a scope choice, not a proof.
- Resolving the ten modules is unstarted. The known blockers now name the
  problem; no tranche has yet designed the answer.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was
  accessed or changed. `paper-epoch-006` is untouched.

## 9. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep3-residuals-20260823`. SEP-3 then continues: resolve
the ten stranded data modules (partition design, in places an owner call),
the integration/governance partition, and the owner-gated runtime topology —
then a third dry run. Only after a dry run reports **no** blocking product
crossings may a separately authorized migration create the research
repository and shared package.
