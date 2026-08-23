# Independent review — SEP-3 alert-ownership tranche and third dry run

Reviewer: Claude (independent), 2026-08-23
Implementer: Codex
Governing documents: `docs/PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md`,
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, `CLAUDE.md`

**Verdict: accepted. No findings against the submission's substance; one P3
hardening of my own guard (SEP3AR-001) and one structural post-merge
correction (CCR-005) landed with this review.** Codex's finding against my
previous round (CRSEP3R2-001) is confirmed by independent measurement and
accepted.

---

## 1. Exact review snapshot

| Item | Value |
|---|---|
| Implementation branch | `origin/codex/sep3-operational-alert-ownership-20260823` |
| Review head (full object name) | `4bea7f9defa10b7599b4de2ff4c25b1b7c808bd2` |
| Base | `717b014ab22a997d268264fb0a3782b70f6cac19` (my prior review head) |
| Review branch | `user/claude/review-sep3-alertown-20260823` |
| Mainline note | PR #305 merged this branch to `main` as `802ed34` **while this review was in flight**; merged tree verified byte-identical to the reviewed head, so nothing is stranded |

## 2. Commit dispositions

| Commit | Scope | Disposition | Issues |
|---|---|---|---|
| `80819d6` | pins exact importer sides for the stranded modules (CRSEP3R2-001 correction) | **accepted** | none |
| `d1fdac9` | counter-review record of my residual round | **accepted** | none |
| `9f68fb5` | handoff after the counter-review | **accepted** (one sentence corrected post-merge, see §5) | none |
| `73acf48` | assigns `data/operational_alerts.py` to the assistant as a `product_owned_service`, with rationale and a cross-import guard | **accepted** | none |
| `984fee3` | third dry-run manifest (candidate `73acf48`) | **accepted** | none |
| `e75f4f5` | plan record for the third dry run | **accepted** | none |
| `4bea7f9` | handoff finalization | **accepted** | none |

## 3. CRSEP3R2-001 against my previous review is correct — reproduced independently

My residual-round review said **five** of the ten stranded modules were
dual-use and marked `portfolio_mandate`, `runtime_identity`, and `macro_data`
as having no research importer. Codex measured **nine** dual-use, with only
`data.operational_alerts` assistant-only.

I re-measured with my own census — product packages **plus each product's
owned scripts**, composition scripts out of scope — and got exactly **nine**:
`ml/filings.py` imports `filing_extraction`; research-owned scripts import
`macro_data` (`run_macro_signals_significance_check.py` among others),
`portfolio_mandate` (`run_portfolio_research_report.py`), and
`runtime_identity` (`capture_analyst_ratings.py`, `report_acer_identity.py`).

**Why my five was wrong, stated precisely:** my review table's "also imported
by research?" column came from my *first* measurement pass (packages only),
while my stranded set came from the *second* pass (packages plus owned
scripts). I published a composite of two different scopes without noticing
they disagreed. The blocker itself still failed closed — the error could only
have misled a later tranche into treating four dual-use modules as safe
single-product reassignments, which is exactly why Codex's importer-side
ledger is the right correction. My archived report keeps the wrong sentence
under the never-retro-edit rule; the dated correction lives in Codex's
counter-review and the current records.

## 4. The tranche's substance, verified

**The `operational_alerts` reassignment is sound under its declared scope.**
The one module my census confirms as assistant-only moves from
`neutral_contracts` to a new `product_owned_services` category with a written
rationale, `data_destination` flips to `trading_assistant`, and it leaves the
stranded list — nine genuinely dual-use modules remain blocking. The two
research-**hosted** scripts that do import it (`run_ml_shadow.py`,
`run_ml_evidence_supervisor.py`) are **composition-hosted**, deliberately
outside the stranded measurement and already counted in the 11-file
composition ledger; the rationale states this dependency explicitly rather
than glossing it, and those runners' fate stays a declared blocker.

**The new guard bites.** Mutation: `ml/monitoring.py` importing
`data.operational_alerts` fails
`test_product_owned_services_do_not_cross_product_owned_sources` with the
exact offender; restored green.

**The importer-sides ledger is exact and refuses both falsification
directions.** Probed against a scratch manifest: claiming `macro_data` is
research-only → validator exits 2 with the stale-blocker refusal; deleting
`runtime_identity` from the sides ledger → same refusal. Codex's own claimed
mutation (`test_incorrect_stranded_importer_side_is_refused`) is present and
passing.

**Third dry-run counts reproduce on my own run**: candidate `73acf48`, 745
tracked paths (+2 = the two review records the candidate commit itself
carries), destinations 501 / 240 / 4, tests 83 / 70 / 1 / 54, status
`valid-third-dry-run-not-ready-for-physical-extraction`,
`physical_extraction_authorized: false`. Focused suites: **41 passed**.

## 5. Two items landed with this review, neither against the tranche

**SEP3AR-001 (P3, mine):** counter-review records escaped the separation
finding-ID guard — `COUNTER_REVIEW_*` does not start with `REVIEW_`, so a
`CRSEP…` finding raised only in a counter-review could vanish from the
current handoff without failing anything. Same risk class as SEP2F-002.
Measured green across all nine existing counter-review files **before**
extending; the globs now cover them and the grammar accepts `CR`-prefixed
IDs. Mutation: dropping `CRSEP3R2-001` from the handoff is red; restored
green.

**CCR-005 post-merge correction (structural, by design):** PR #305 merged
this tranche while the review was in flight, which made the handoff's claim
that the `9f68fb5` counter-review commits were "unpushed" false by
construction the moment it landed — the exact failure mode CCR-005's
reachability guard exists to catch, and it caught it on my first full
doc-guard run. The sentence now records the merge and the correction. This is
the third time this session a merge has outrun a record; the guard, not
vigilance, is what catches it.

## 6. Validation on the final tree

| Check | Result |
|---|---|
| Focused SEP suites (dry run + entry points + shared package) | 41 passed |
| `tests/test_active_document_consistency.py` | 56 passed after the CCR-005 correction |
| Complete suite | recorded in handoff section 7eh |
| `git diff --check` | clean |
| Mutations | ownership guard red/green; importer-sides falsified both directions → refused; SEP3AR-001 red/green; CRSEP3R2-001 reproduced with an independent census |

## 7. Untested surface, stated plainly

- The nine dual-use modules remain unresolved; this tranche resolved the one
  module whose import graph already decided its home. The genuinely
  contested design — where dual-use neutral modules live under a
  two-repository topology — is still ahead and partly an owner call.
- The composition-scope choice (11 hosted runners outside both product
  censuses) is load-bearing for the `operational_alerts` assignment; it is
  disclosed in the rationale, but resolving the composition ledger later must
  revisit those two alert-writing runners explicitly.
- No provider, broker, licensed row, operator database, scheduled task,
  deployment, backtest, outcome, research look, or evidence epoch was
  accessed or changed. `paper-epoch-006` is untouched.

## 8. Next step

Codex counter-reviews the exact pushed head of
`user/claude/review-sep3-alertown-20260823`. SEP-3 continues: the nine
dual-use modules, the integration/governance partition, the composition
ledger, and the owner-gated runtime topology — then a fourth dry run.
Physical extraction remains unauthorized.
