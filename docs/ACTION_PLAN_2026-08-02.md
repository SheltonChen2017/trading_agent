# ACTION PLAN — the go-to consolidated done / remaining ledger

Status: **owner-adopted go-to plan** (2026-08-02). After independent audits
by Claude and Codex converged on the same facts, the owner selected this
plan as the single sequencing authority for all workstreams. Codex's
independent draft is preserved at `docs/reference/ACTION_PLAN_codex.md`;
its doc-inventory table and staleness corrections are incorporated by
reference. The individual implementation plans are archived in
`docs/reference/` and remain authoritative for their own milestone
*definitions* — this document decides only *what happens next*.

Owner priority change (2026-08-02): **UI feature controls moved to the
front of the queue** — the owner begins daily paper trading to gather real
transaction data, and the Settings/policy/AI controls directly support
that. Both audits agree this reordering is safe: the UI consumes only the
characterization-pinned execution facade, so it neither blocks nor is
blocked by the remaining GR-1 kernel work.

Prepared: 2026-08-02, by Claude, at `origin/main` = `ff8c16e` (post PR #112);
adopted and reprioritized at `ded68b0` (post PR #113/#114); UI Phase 1
implemented and merged as PR #116 at `4c8e959`, independently accepted
after corrections (`a6d5254`), confirmed by Claude's third round, and the
whole review chain merged as PR #117 at `661a7d4` (2026-08-03).
Phase 2 hygiene was implemented at `34ce463` and independently accepted
after correction on `codex/review-phase2-hygiene-20260803`, then merged as
PR #118 and confirmed through PR #119. GR-1D merged as PR #120 at `711095c`
and was independently accepted at `2f37210`. PR #121 added four exploratory
candidate-signal utilities at `5a6ffd5`; independent review corrected their
family-wide evidence reporting at `6d3603d` without changing roadmap order.

Method: four parallel verified surveys over every implementation plan and
design document under `docs/`, each claim checked against the actual code
(module/function existence, line numbers, table row counts, scheduled-task
enumeration, live read-only database inspection) rather than trusting status
prose. Where this document says "verified", a file path or measurement backs
it; where a status doc disagreed with code, the code won and the discrepancy
is listed in section 7.

Nothing in this document grants authority. Live trading, funded accounts,
model promotion, autonomous execution, and every ML/LLM boundary in
`CLAUDE.md` and `docs/SESSION_HANDOFF.md` remain exactly as constrained.

Current development topology (2026-08-17): `origin/main` is
`1457169ba10f6aac0f1fb98b60b92a4607f8331c` after PR #245 merged the Codex
Stage 0 verification branch. Before it, PR #244 at `b6f577e` merged Claude's
Stage 0 correction counter-review head `9a7e9fc`; its tree is byte-identical
to that exact reviewed head. PR #243 at `4151b3f` had merged Fable's final
counter-review head `6bd962f`, and PR #242 at `f937bfb` had merged the
Codex counter-review integration branch, and PR #241 at `d8a3260` had merged
the full Codex alpha/QC audit before it. Fable's three commits were reviewed
individually and their added tests are useful, but the conclusion that the
tree contained no product defect did not survive verification. Codex review
branch `codex/review-alpha-qc-fable-counterreview-20260817` contains product/
test correction `ac96d47`: the Stage 0 short battery now charges the entry and
later re-entry around its cash/staging session, MAX(20) refuses anything
other than 21 finite positive closes, missing Morningstar industries cannot
become a fictitious peer group, and the analyser infers 12 observations/year
for monthly families versus 42 for the non-overlapping six-session short
cycle. See
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_FABLE_COUNTERREVIEW.md`. Claude's
independent counter-review of that exact pushed head `9e45803` (branch
`user/claude/alpha-qc-fable-cr-verify-20260817`) accepted all three commits,
confirmed all four FQCV code findings with pre-correction red reproductions
and seven mutations, and closed two follow-up P3 gaps: FCR-001 pins the
drifted exit leg on long/short books, and FCR-002 ports the industry-code
correction into Stage 1's dead copied ingestion state. See
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_CORRECTION_COUNTERREVIEW.md`.
Codex then independently verified Claude's exact three-commit range from
`9e45803` through `9a7e9fc`. Both FCR closures are accepted. One P3 test gap
was closed on `codex/review-alpha-qc-fable-cr2-20260817`: the prior helper-only
industry test did not prove that each live `_fine` ingestion path actually
used the strict guard, so a mutation reverting the Stage 1 call site survived.
The new regression pins all three algorithms' live guard call and stale-map
eviction. No algorithm behavior changed in this verification. See
`docs/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_COUNTERREVIEW_VERIFICATION.md`.
Product/test corrections `855941a` and `1e2b631`
repair the current LEAN Python API, framework
member collisions, point-in-time and exact-session factors, Stage 1 cadence,
benchmark/analyser provenance, bounded QC polling, older local turnover/NAV,
leave-one-out peers, and joint residual regression. No QuantConnect access or
new research look occurred in any review lane.

Every submitted local/cloud alpha result remains unusable. At the owner's
direction, invalid generated result narratives, JSON artifacts, and raw logs
were removed from active docs only after `docs/alpha-result.md` preserved
their run identities, statuses, hashes, and look accounting. The frozen
historical contracts remain under `docs/research/`; no result was promoted and
no alpha feature milestone completed. **The independent counter-review of
`ac96d47` is complete and accepting**, satisfying the gate Codex set. Codex's
independent verification accepts FCR-001/002 and closes the acknowledgement
residue. The only research choice before launch is the owner's stage order —
Stage 0 battery completion or Stage 1 — followed by execution under the
frozen evidence contract. None of this is deployed: the
operational runtime remains frozen at `752d3b7` in active `paper-epoch-005`.
Any deployment would close that epoch by changing its `code_commit`.

---

## 1. The one-paragraph state of the project

The platform's **code** is far ahead of its **operations and evidence**. The
deterministic execution path (propose → validate → approve → claim → submit →
reconcile) is built, characterization-frozen, and three-review hardened; the
ML research/shadow stack is software-complete through monitoring and dossier;
the LLM committee foundation is built and gated; the execution-kernel split
(GR-1) is complete after the independently reviewed 2026-08-03 GR-1E
assessment; GR-2 through GR-5 are complete and independently reviewed. GR-7a
through GR-7c are also complete, and the adopted three-sleeve replacement for
GR-7d is complete through independently reviewed M3; optional M4 remains
deferred. What remains incomplete is GR-6, the allocation service, every AI
*product* plan beyond the committee (strategy authoring, debate, and MCP), and
— most importantly — enough **elapsed frozen-
epoch evidence**: `paper-epoch-001` and `paper-epoch-002` are closed, and
`paper-epoch-003` and `paper-epoch-004` are closed, and
**`paper-epoch-005` is active since 2026-08-13** on the epoch host at
deployed commit `752d3b7`, bound to `my_policy.json`.
Development changes in this checkout are not deployed into that epoch.
**Update 2026-08-13 (executed): the epoch-005 roll.** Owner-authorized and
run in runbook order after that day's observation was safely captured.
`paper-epoch-004` closed 23:57:17Z on frozen `b837374`, retaining its 3
observations (discarded evidence is the accepted cost of rolling, paid
deliberately while the count was small); deployed `752d3b7` (PR #205);
`ledger-reconcile` matched with 0 mismatches on its first run under the new
code; readiness green; **`paper-epoch-005` started 23:59:07Z** with unchanged
mandate/policy/strategy/model lineage (only `code_commit` moved), lineage
hash `0b7702b2…`; **5/5 drills recorded under epoch-005**; tasks re-enabled
and a manual `operations-cycle` verified green; all 5 pre-roll alerts
acknowledged with causes verified resolved, **0 open at completion**. This
roll deployed AP-8, AP-9, QC-2, AP-10, AP-11, three-sleeve M3, and SELL-1.
The 60-session clock restarts at the first scheduled observation under
epoch-005; until that row exists the epoch has 0 observations. Details and
roll-specific gotchas are in `docs/operations/OPERATIONAL_FACTS.md`.

**Update 2026-08-10 (executed):** epoch-002 stalled at 1 session on
uningested broker CAT fees (defect AP-6 below). The fix was independently
corrected (`a8174b9`), counter-reviewed and accepted in full, merged as
**PR #182** (`ef05dc1`), and the owner-authorized epoch swap was executed
the same day: epoch-002 **closed**, the merged tree **deployed**,
`ledger-reconcile` **matched on the first run** (the three CAT fees posted
exactly once), and **`paper-epoch-003` was started** at `ef05dc1` with the
same mandate/policy/strategy/model lineage, **all five required drills
passed and recorded**, tasks re-enabled, a manual operations-cycle green,
and zero open alerts at swap completion. The first scheduled post-close
capture then succeeded on 2026-08-10: epoch-003 now has **one observation**,
its capture-time lineage hash matches the epoch, the ledger mismatch count is
zero, and the scheduler returned success. The 60-session / 30-order minimums
are now accumulating from that first post-swap capture. The scarcest
resource on the critical path is not engineering — it is elapsed calendar time on that
frozen runtime, plus a small number of owner decisions and data purchases.

**Epoch-004 roll EXECUTED 2026-08-11 (owner-authorized).** epoch-003 closed
at 22:14:52Z on its frozen runtime with 1 discarded observation; merged
`b837374` (PR #189) deployed; `ledger-reconcile` matched with 0 mismatches;
readiness green; `paper-epoch-004` started 22:15:53Z with unchanged lineage;
**5/5 drills recorded**; tasks re-enabled and a manual operations-cycle
verified green. This single roll deployed CR-W2 dividend ingestion, both
AP-7 freshness sites, the MADCR-001 IPO fail-open fix, and the operator
acknowledgement path. Across the first two post-roll cycles, both AP-7 alerts
reported non-negative ages, did not re-raise, and were acknowledged; there
were **0 open alerts at that observation point**. That observation did not
establish the complete production call path: AP-11 later reproduced a live
negative age in the nested readiness check because its outer caller still
froze the clock. The AP-11 repair is merged development code at `72b6278`
was not deployed to epoch-004; it subsequently deployed in epoch-005 at
`752d3b7`. The 60-session / 30-order evidence window restarted at the next
epoch boundary. With the acknowledgement path live, an
unsupported broker activity now costs one explicit operator decision instead
of the accumulated run, so **CR-W3 is a watch item rather than an
epoch-killer**.

---

## 2. DONE — implemented, reviewed, and verified in code

### 2.1 Execution platform (general readiness)

| Item | Where | Review state |
|---|---|---|
| GR-0 five-dimension platform readiness (never averaged; fail-closed) | `assistant/platform_readiness.py` (778 lines as of 2026-08-07), CLI `platform-readiness` | independently reviewed |
| GR-1A execution characterization freeze (5 public entry points, atomic-claim pin, 4-writer contention) | `tests/test_execution_characterization.py` | independently reviewed |
| GR-1A/B helper + orchestration extraction (7 kernel modules) | `assistant/execution_kernel/{claim,revalidate,submit,outcomes,errors,intents,validate}.py` | independently reviewed |
| GR-1C validation orchestration behind complete call-time DI (15-field frozen `ProposalValidationDeps`; kernel body has zero module-global runtime reads, symtable-pinned) | `assistant/execution_kernel/validate.py` | three review rounds, closed at PR #112 |
| GR-1D manual reconciliation behind complete call-time DI (13-field frozen `ReconciliationDeps`; kernel body has zero module-global runtime reads, symtable-pinned) | `assistant/execution_kernel/reconcile.py` | merged as PR #120; independently accepted at `2f37210` |
| Execution-kernel import boundary: no direct or transitive path from kernel/assistant/execution/risk roots into `ml` or proposal generation | `tests/test_ml_import_boundary.py` (transitive graph walk, fails closed on unresolvable imports) | reviewed |
| Order lifecycle: idempotent submission, ambiguous-outcome reconciliation, replacement chains, absence-age grace, reservation accounting, telemetry-before-submission | `assistant/execution_service.py` (facade, 900 lines as of 2026-08-07), `assistant/order_lifecycle.py`, `assistant/order_reconciler.py` | multiple review rounds |
| Risk-metrics consolidation (`max_drawdown_pct` single source) | `backtest/risk_metrics.py` | closed in ARCHITECTURE_DEBT |

### 2.2 ML stack (all **observation-only**, promotion-blocked by design)

| Item | Where |
|---|---|
| Contracts, manifests, hashing, artifact integrity (ML-1) | `ml/contracts.py`, `ml/hashing.py`, `ml/artifacts.py` |
| PIT features/labels, purged grouped walk-forward splits, immutable datasets (ML-2, ML-LR-1) | `ml/features.py`, `ml/labels.py`, `ml/splits.py`, `ml/datasets.py`, `ml/availability.py` |
| Factor risk, volatility/correlation research, earnings-gap research (ML-3/4/5, ML-LR-3/4) | `ml/factor_risk.py`, `ml/volatility.py`, `ml/earnings_*.py`, `ml/portfolio_*.py` |
| Durable experiment runner + review-gated campaign CLI (ML-LR-2, ML-FS-6 prep) | `ml/experiments.py`, `ml/research_orchestration.py`, `scripts/run_ml_research_campaign.py`, `research/ml_specs/` |
| Supervised-volatility shadow runtime + evidence epochs (ML-LR-6) | `ml/shadow_runtime.py`, `scripts/run_ml_shadow.py` (register/predict/mature/monitor/status/close-epoch) |
| Monitoring reports + promotion dossier (read-only; no registry writes) (ML-LR-7) | `ml/monitoring_reports.py`, `ml/promotion.py`, `scripts/run_ml_promotion_dossier.py` |
| Read-only presentation with action-shape rejection (ML-LR-8) | `ml/presentation.py` |
| Paper portfolio collection + capture manifests (ML-FS-1), pre-broker execution telemetry (ML-FS-2) | `assistant/paper_evidence.py`, `assistant/execution_telemetry.py` |
| Databento ingest/PIT software incl. authoritative builder (ML-FS-3, software only) | `ml/databento_*.py`, `scripts/run_databento_ingest.py` (8 subcommands) |
| Evidence-operations supervisor + Windows task installers + verifier (ML-FS-7, software only) | `ml/evidence_operations.py`, `scripts/install_windows_*.ps1`, `scripts/verify_windows_evidence_tasks.ps1` |

### 2.3 LLM features (all advisory-only, audited)

| Item | Where |
|---|---|
| Investment-committee foundation: schemas, projection with privacy modes, deterministic validators, pure orchestration | `assistant/llm/` (10 files) |
| Real Anthropic provider (typed error codes, bounded timeout, `max_retries=0`) + mandatory audit persistence (audit failure ⇒ review unavailable) | `assistant/llm/anthropic_provider.py`, `committee_service.py` |
| Streamlit surface: sell-only eligibility, exact-input-hash cache binding, double-gated (`ANTHROPIC_API_KEY` AND `ENABLE_EXPERIMENTAL_COMMITTEE=1`) | `scripts/personal_assistant_ui.py` |
| Advisory helpers: news summaries, similar-ticker suggestions, allocation commentary — all with action-language rejection + `ai_runs` audit | `assistant/ai_advisor.py`, `assistant/news_summary.py` |

### 2.4 Process infrastructure (2026-08-02)

Commit-by-commit review with P0–P3 ledger (`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`),
two-paragraph milestone record (`docs/FEATURE_MILESTONE_RECORD.md`), canonical
git-synchronized session handoff (`docs/SESSION_HANDOFF.md`), all wired into
`CLAUDE.md` and the review skill.

### 2.5 UI feature controls (2026-08-03)

The Streamlit app gained its sixth and seventh tabs here (Settings & Features and a
research-only Ticker Suggestions surface; GR-5 later added an eighth, read-only Operations tab). Session-scoped AI preferences gate
all optional LLM surfaces; provider and safety state are read-only; and
`allow_new_positions` / `enable_strategy_proposals` use a protected typed
confirmation, validate-before-write, version/fingerprint-changing persistence
workflow. Independent review added behavioral coverage proving the real UI
toggle persists and refreshes authoritative status in both directions, binds
editor state to the selected policy, and prevents disabled suggestion sources
from calling their providers. Implementation merge: `4c8e959`; accepted after
review correction `a6d5254`; the full review chain (correction, handoff,
third-round confirmation) merged as PR #117 at `661a7d4`.

The later owner-requested Alpaca-inspired AUI restyle is also **complete and
independently accepted after correction 2026-08-09**. PR #180 merged the
implementation at `aaf7497`; browser-equipped review corrected Streamlit
1.60 selectors for visible checked/focus marks, the alert markdown typeface,
and bordered-container panels at `45cae5b`. All ten pages smoke-test, rendered
warning contrast clears AA with margin, and no authority path changed. See
`docs/Review/REVIEW_2026-08-09_AUI_CORRECTIONS.md`. This presentation milestone does
not reorder the roadmap or authorize M3.

**Most-actives split by price direction (owner request, 2026-08-10;
completed and independently accepted after correction 2026-08-11).** The
Ticker Suggestions tab's most-active screen now renders two columns instead
of one list. The owner asked for "most actively bought" and "most actively
sold"; **that split was deliberately NOT built because the yfinance
most-actives source does not provide classified order flow.** Volume is
symmetric — every share traded was bought by one party and sold by another —
so its single volume number cannot be decomposed into bought-versus-sold
shares. Nor is this a swap-the-screener fix (counter-review MADCR-002):
classifying a trade as buyer- or seller-initiated needs trade prints matched
against the prevailing quote, i.e. consolidated trade-and-quote data, and the
feed this project actually has is Alpaca's free IEX tier — measured on
2026-08-10 quoting a large-cap at a ~6% spread while the consolidated market
was penny-wide. Estimating direction from that would produce confident-looking
noise. This preserves the standing rule already stated in
`assistant/recommended_stocks.fetch_most_active_tickers`: never label volume
"most bought" in code, comments, or UI copy.

What ships instead is the same most-active list split by the provider-reported
price direction — heavily traded names whose prices rose versus heavily
traded names whose prices fell. `classify_price_direction()` rejects
NaN/infinity explicitly (every
ordered comparison against NaN is False, so an unguarded sign chain would
report a corrupt value as "unchanged"), and distinguishes a genuine 0.00%
close from a change the provider never reported; the two are surfaced in
separate captions rather than folded together. UI copy states plainly that
this is not a buy/sell split and not a signal. Observation and presentation
only: no proposal, order, policy, epoch, or authority path changed, and the
project still has **zero confirmed predictive signals**. Implementation
`3be6326` was accepted after correction `3b72242`; review fixed the
case-normalized provider-detail join, separated cached source time from display
time, narrowed unsupported data-availability/causality claims, and added real
Streamlit behavioral coverage. Final validation passed 3,378 tests. See
`docs/Review/REVIEW_2026-08-11_MOST_ACTIVE_DIRECTION_SPLIT.md`.

### 2.6 Exploratory candidate-signal software (2026-08-03)

PR #121 added causal residual momentum/reversal, volatility-scaled momentum,
and consecutive-earnings-surprise persistence scanners plus reporting-only
block-bootstrap runners. Independent review at `6d3603d` made the two runners
share the full eight-cell Bonferroni family, made evidence-column drift fail
closed, and documented PEAD's long-only direction asymmetry. These are
reviewed research utilities, not confirmed findings: yfinance/current-universe
inputs are not point-in-time, no result was promoted, and no proposal,
execution, policy, scheduler, epoch, or live-authority path changed. This
already-merged work does not reorder the adopted next step.

---

## 3. IN PROGRESS — started, not finished

| Item | Remaining | Size |
|---|---|---|
| **GR-1E** — ~~assess the composition + recovery wrappers~~ **COMPLETE AND INDEPENDENTLY REVIEWED 2026-08-03: no extraction. The 281-line coordinator sequences extracted phases, performs ordinary control/exception/message composition, contains one broker-submission call, and contains no inline financial math, transition SQL, or broker interpretation. Recovery remains around the atomic storage primitive; the claim wrapper may try more than one candidate status. GR-1 is complete against the archived plan's intended §6.4 scope; `allocation_batch.py` debt remains open. See GENERAL_READINESS_STATUS and the GR-1E review report.** | none | complete |
| **Committee release gates** — **COMPLETE AND INDEPENDENTLY REVIEWED AFTER CORRECTION 2026-08-05**: `tests/committee_corpus/cases.json` contains 69 frozen cases (51 replay / 10 injection / 8 memory-poisoning) executed through the real pipeline, with ADR-minimum inventory gates and a canonical SHA-256 content identity so a case cannot be silently gutted while retaining its ID/category. The `committee-review` CLI gives every covered failure one explicit `Review unavailable (<code>)` line; review added the missing packet-construction failure path. The `ENABLE_EXPERIMENTAL_COMMITTEE=1` gate is deliberately NOT removed — removal is a separately reviewed, owner-authorized decision. | owner decision on gate removal | complete |
| **ML-FS-6 real discovery/confirmation** — spec `research/ml_specs/volatility-discovery-v1.json` is review-ready; no `SpecReviewAttestation` exists | blocked on owner-designated reviewer + real PIT data | owner + data |
| **CR-W2 cash-dividend / explicit cash-transfer handler** — **COMPLETE, MERGED, AND DEPLOYED IN EPOCH-004**: Claude implementation `25a2e7b`, Codex correction `a6770f7`, Claude counter-review correction `cf9cdc2`, merged as **PR #184 at `0ee3a22`** and deployed in the owner-authorized 2026-08-11 roll at frozen runtime `b837374`. The AEP position acquired 2026-08-07 is scheduled for a $0.95/share dividend on **2026-09-10** (official AEP record/ex-date 2026-08-10). The handler journals USD plain/explicit-CDIV cash dividends with unknown tax classification and explicit CSD deposits / CSW withdrawals; economic dates use market-local midnight, and amount, sign, currency, subtype, per-share arithmetic, and broker-ID identity fail closed. JNLC, stock/substitute dividends, interest, tax-specific variants, non-USD amounts, and unknowns remain loud refusals. | Watch **CR-W3**: the `""`/`CDIV` allowlist is not yet verified against a real account dividend and may over-refuse once while naming the subtype. | complete and operational |
| **Operator acknowledgement path for refused broker activities** — **COMPLETE, MERGED, AND DEPLOYED IN EPOCH-004**: Claude implementation merged as PR #188 at `24de4f5`; Codex correction `74376e4` and Claude's BAACR-001 choke-point correction merged through PR #189 at `b837374`, the frozen epoch-004 runtime. The additive acknowledgement table, exact-row fingerprint, and account-bound `ledger-activity-review` / `ledger-activity-acknowledge` turn one unsupported post-bootstrap activity into an explicit operator decision rather than a code deploy. Preview is genuinely read-only through a verified disposable SQLite snapshot; acknowledgement is restricted to a row currently refused by sync and remains record-only until the next ordinary sync. Executed status, currency, explicit amount/sign, explicit zero for `no_cash_effect`, account/bootstrap binding, timezone-aware audit time, immutable cross-type broker ID, and operator/rationale identity all fail closed. BAACR-001 moved account binding into `_sync_broker_activities_from_alpaca` before the fetch so every scheduled and manual caller is protected. | none beyond ordinary operator review of genuinely unsupported rows | complete and operational |
| **Broker-activity ingestion (AP-6 fix)** — **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-10** at `a8174b9`: paginated raw-REST `list_account_activities()` in `execution/alpaca_broker.py` (pinned alpaca-py lacks the endpoint); fail-closed `sync_broker_activities()` in `assistant/portfolio_ledger.py`; idempotent FEE journaling; exact bootstrap-bound fetch and local pre-bootstrap exclusion; published minimal-response compatibility; unsupported post-bootstrap types still refuse; `operations-cycle` preserves reconciliation, backup, health, and alert work before returning the failure. Review closed 3 P2 implementation findings, 1 P2 deployment-procedure finding, and 3 P3 findings. Counter-review (Claude, 2026-08-10) accepted all findings with live endpoint verification and four reverse mutations proving the corrected guards load-bearing; two P3 watch items recorded (surrogate/`created_at` content conflict on provider transition; a future paper-cash top-up fails closed until a reviewed `JNLC` handler exists). **Merged as PR #182 and DEPLOYED 2026-08-10: the full swap sequence executed — epoch-002 closed, `ledger-reconcile` matched first-run, epoch-003 active at `ef05dc1`, 5/5 drills recorded, tasks re-enabled, cycle green, 0 open alerts.** | none — complete and operational; watch items CR-W1/CR-W2 stand | complete |
| **Ticker-suggestion disclosure policy (AP-8b)** — **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-12; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Claude implementation `d326a74`; Codex correction `7c21339` on `codex/review-ap8-ticker-disclosure-20260812`. Owner decision: this research surface is disclosure the reader judges, so all three `build_recommended_tickers()` lanes stop screening named US equities on size, age, price, or liquidity and instead show below-usual/unavailable measurements on each row. Review closed four P2 and one P3 findings: company name remains part of identity (with `longName`/`shortName`/`displayName` fallback); zero/non-finite/malformed closes cannot become verified or abort the batch; missing liquidity stays unavailable instead of becoming measured `$0`; Briefing always discloses the relaxed screen; the prior recent-IPO policy import remains compatible; and touched Streamlit tables use the 1.60 width API. Strict `DEFAULT_ELIGIBILITY_POLICY` callers are unchanged. Final validation: 3,454 passed, 0 failed/skipped, 25 dependency warnings under Python 3.13.14 / Streamlit 1.60.0.  **Counter-review (Claude, 2026-08-12) accepted all five findings — each verified against the submitted tree and each correction mutated to prove it load-bearing — with one qualification and two further fixes.** AP8REV-004 is *partially correct*: its reasoning holds, but nothing in this repository still imported `RECENT_IPO_ELIGIBILITY_POLICY`, so the compatibility break was hypothetical; the restored constant is accepted as harmless. **AP8CR-001 (P2):** AP8REV-003's two copy corrections were applied to Briefing only, leaving the dedicated Ticker Suggestions page — the surface AP-8 is about — still claiming an unnamed identity floor and asserting that omitted symbols "could not be identified", which a provider outage is indistinguishable from; a test asserting the absence of the obsolete literal had also become vacuous. **AP8CR-002 (P2):** AP8REV-002's batch-isolation fix stopped one line short — the first-session date was still derived unguarded, so a frame with a non-datetime index aborted the whole batch and discarded already-validated tickers; the candidate is now dropped rather than given an empty date, which would have silently disarmed the reused-symbol guard. **AP8CR-003 (P3):** a pre-existing block of standing host rules in `OPERATIONAL_FACTS.md` had no heading and was being adopted by each appended milestone note. | complete after review and counter-review; deployed in epoch-005 |

---

## 4. Planned-code milestone ledger — current completion state

| Milestone | Scope (one line) | Verified-absent marker |
|---|---|---|
| GR-2 risk-check registry | ~~ordered registry replacing the hand-written gate sequence~~ **COMPLETE AND INDEPENDENTLY REVIEWED 2026-08-03**: 20-check `RISK_CHECK_REGISTRY` with `applies_at` phases, exact old/new behavior preservation, runner-bound frozen inventory, registry-injection proof, and corrected terminal semantics. Implementation `03895ae`; review correction `0167c67`. | complete |
| GR-3 fault-injection drills | ~~9 named faults + drill harness~~ **COMPLETE AND INDEPENDENTLY REVIEWED 2026-08-03**: 11 fault IDs / 14 behavioral tests plus an atomic hash-stamped runner. Review corrected active-epoch lineage binding, skipped/abnormal pytest fail-open behavior, the missing F4 critical alert, the absent true `submitting` restart case, partial-state assertions, and artifact atomicity. Records ambiguous_submission/restart_recovery/kill_switch rows only under exact epoch lineage or as explicit verification-only evidence. | complete |
| GR-4 data-layer honesty | **COMPLETE AND INDEPENDENTLY REVIEWED AFTER CORRECTION 2026-08-05.** `data/price_source.py` and `assistant/data_integrity.py` provide declared provider lineage, strict recorded-fetch evidence, NYSE-session freshness, failure-streak alerts, and the GR-0 adapter. Review corrected non-session bars accepted as fresh, malformed lineage/readiness values accepted as evidence, stale short histories missing the banner, missing strategy bars looking like no rebalance, and forward-split proposal drift reaching submission. New proposals bind exact proposal-time shares and revalidation refuses a split-shaped fresh-snapshot mismatch before broker preflight; old stored proposals remain readable. The active regime and strategy-proposal fetches are recorded; quote freshness remains the execution gate's authority, current earnings reads expose unavailable values directly, and research/presentation-only historical fetches are not falsely described as provider-health evidence. It was not deployed mid-epoch; it entered the operational tree only at the owner-authorized epoch-003 boundary (`ef05dc1`). | complete |
| GR-5 alert delivery | ~~a real channel + delivery records + weekly self-test + operator dashboard~~ **COMPLETE AND INDEPENDENTLY REVIEWED 2026-08-03**: Windows toast for critical (owner decision), warnings batched to the briefing, immutable `alert_deliveries` records, escalation on failure, storage-verified weekly self-test producing the `alert_delivery` drill, readiness checks, and the Streamlit Operations tab. Review corrected a P2 gap: a durable broken-channel alert now keeps mandatory readiness failed until a later successful self-test proves recovery and acknowledges it. | complete |
| GR-6 recovery/portability | off-machine backup restore, secrets audit, key rotation, portable scheduler, second-machine stand-up proven once | zero matches for all markers |
| GR-7 product completeness | **Split into sub-milestones 2026-08-05** (the archived plan's five items are far too large for one reviewed branch; one milestone per branch per CLAUDE.md §3). **GR-7a annual tax reporting** — **COMPLETE AND INDEPENDENTLY REVIEWED AFTER CORRECTION 2026-08-05.** Review closed sample-as-broker coverage verification, float-product money conversion, stdout artifact pollution, Reports-page provider-fetch writes, year/report desync, and coverage freeze/outage honesty. **GR-7b idle-cash/mandate reporting** — **COMPLETE AND INDEPENDENTLY REVIEWED AFTER CORRECTION 2026-08-06.** Review closed CLI/UI provider-fetch writes on a claimed read-only surface, NaN measured-vol traceback, and negative measured vol. **GR-7c performance attribution** — **COMPLETE AND INDEPENDENTLY REVIEWED AFTER CORRECTION 2026-08-06; follow-ups (cash-flow skip + session-equalized weight) independently reviewed after correction 2026-08-07.** Single-bucket SPY cash-drag / residual; session sufficiency; review closed silent cash>equity clamp, NaN cost typing, read-only proof, overinvested label honesty, post-flow equity TWR wiring (deposit-as-return), weight-method disclosure, and human-CLI cash-drag hardcoding. **GR-7d rebalance-to-target proposals — BLOCKED ON AN OWNER DECISION** (see below), not on code. The archived plan's "tax-aware sell preview" item was found already substantially shipped: `assistant/proposals.py` surfaces `tax_lot_advisory` (lot-level realized-gain consequences) on risk-reduction proposals. | GR-7a/b/c complete after review |
| Allocation service | delta-vs-target primitive, calibrated regime threshold, cadence, universe list, sizing | only the `strategy_evaluations` table exists |
| Proposal-history cleanup | `dismissed` status, preview-first dismissal CLI, and History UI are complete as UI-2d; optional explicit-trigger expiry and physical purge remain separately deferred | first milestone complete; automatic expiry/purge not built |
| AI strategy authoring AS-0..AS-7 | prose → StrategySpec → compiler → evaluation plan → orchestrated backtest → dossier → registry | 0% of strategy authoring — no `strategy_lab/` or DSL. The separate read-only UI-3 Backtest page is complete and must not be confused with this authoring pipeline. |
| AI debate surface | `assistant/ai_debate.py` parallel-framing design | 0%; its own doc questions whether the safe version is worth building |
| MCP read-only server | `mcp_bridge/` + 9 tools | 0%; GR-5's dashboard prerequisite is now satisfied, but the §3.6 activation gate still fails because the broader GR list is incomplete, no five-question preceding-month need is recorded, and higher-leverage work remains open. |
| QC-2 research-look registry | honest denominator for the multiplicity correction on the interactive research surface | **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-11; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Claude implementation `f09682f`, merged as PR #192 at `62c8270`; Codex correction `7fc9db8` on `codex/review-qc2-look-counting-registry-20260811`. Scope was owner-approved because no earlier definition of done existed. New `research_looks` storage and `assistant/research_looks.py` record a tested family before the Backtest engine reveals its result. Review closed four P2 defects: repeat identity now binds exact dated frame content and a clean code commit; the denominator counts every selected horizon × the two dip/up direction cells rather than one click; real-market presentation excludes synthetic fixture runs while still auditing them; and strict finite-JSON plus storage conflict checks prevent canonical-identity collisions or silent immutable-content changes. Exact replays increment only `repeat_count`; changed configuration, data, code, source, or cell count is a new family. There is no delete/rewrite path, and registry failure warns without gating research. Final validation: 3,429 passed, 0 failed/skipped, 25 dependency warnings under Python 3.13.14 / Streamlit 1.60.0. This is bookkeeping, not a significance result or authority path. | complete after review; deployed in epoch-005 |
| QC-1 QuantConnect research client | allowlisted results-only cloud transport (`research/quantconnect.py`); no raw market-data export path | **COMPLETE AND INDEPENDENTLY REVIEWED AFTER CORRECTION 2026-08-07.** Review forced POST-for-all (including authenticate), hardened allowlist against prefix/`../` bypass, required in-band `success is True`, and rejected bad ids/timeouts. Live `authenticate()` still unproven until credentials are set. QC-2 now covers the local interactive Backtest surface; QuantConnect cloud-run look integration is outside QC-2 and remains unbuilt. |

---

## 5. BLOCKED — not by code, by data / time / authorization

| Blocker class | Items |
|---|---|
| **Data purchase** | authoritative historical index/strategy membership (NOT purchasable from Databento — needs a separate vendor decision); Databento statistics captures per session/vintage (~$0.06/session measured), reference security-master + adjustment-factors snapshots, universe + cutoffs artifacts, then a real `build-authoritative` run; authoritative earnings/consensus event data |
| **Elapsed time on a frozen runtime** | mandate minimums: **60 paper sessions / 30 broker orders inside ONE evidence epoch** (~3+ calendar months); ML shadow evidence duration; 30-day backup-restore-drill freshness window |
| **Owner authorization only** | ML-FS-8/ML-LR-9 promotion registry; ML-FS-9/ML-LR-10 canary; AS-8+ adapters; GR-8 live canary; committee gate removal. Mandate approval was granted 2026-08-04 and is no longer a blocker. |
| **Prohibited until conditions change** | ML-LR-11 / ML-9 execution-quality modeling (needs representative *live* order data + explicit authorization); AS-11 autonomous strategy mutation (permanent); GR-9 non-goals (permanent) |

---

## 6. Defects found during this survey (fix cheaply, soon)

| ID | Priority | Finding | Fix |
|---|---|---|---|
| AP-1 | P2 | **Operator DB schema is stale**: `execution_telemetry_events` and `portfolio_capture_sessions` are declared in `assistant/storage.py` but absent from `data/trading_assistant.db` (24 tables present). Telemetry/capture chains cannot run until current code opens the DB. | **Resolved and reviewed 2026-08-03:** `verify-db-schema` and `verify_database_schema()` provide a read-only compatibility check plus explicit `--apply`. The measured operator DB was already current for an unknown historical reason: all required tables/columns were present and every named index/trigger definition matched current code. A pre-change SQLite backup was verified. Table column types and constraints are not compared byte-for-byte. |
| AP-2 | P2 | **`.gitignore` gap**: ML runtime writes `artifacts/shadow.json`, `artifacts/model/`, `artifacts/{datasets,experiments,reviews}/` — none ignored. First scheduled run dirties the worktree, and evidence capture **refuses a dirty worktree** → silent cadence failure. | **Resolved and reviewed 2026-08-03:** `artifacts/` is ignored wholesale and enforced through `git check-ignore` regression coverage. |
| AP-3 | P3 | 118 `portfolio_equity_snapshots` rows are mixed briefing/test-pollution provenance (pre-2026-08-02); any evidence report over them is unreliable | treat pre-2026-08-02 rows as non-evidence; decide retention at epoch start |
| AP-4 | P3 | Doc staleness cluster: `validate.py` figure 479→490 (grew in `7f431b6`); characterization-suite docstring still says "2,040 lines"; STATUS "corrects" a 1,450 figure the plan never contained; GR-1D/1E exist only in SESSION_HANDOFF, absent from plan and status docs; ML status doc has 3 internally stale paragraphs (spec library "not built" vs delivered; "calibration emitted empty" vs wired; ML-FS §2 overstates ML-FS-6) | **Resolved and reviewed 2026-08-03:** reconciled all listed statements, added GR-1D/1E status, and recorded post-PR-#117 state. |
| AP-6 | P2 | **Broker non-trade activities were never ingested** (found 2026-08-10 tracing epoch-002's stall): Alpaca charges CAT fees on paper accounts as account *activities*, not fills; the journal only ingested fills (`sync_app_fills`), so ledger cash drifted +$0.01 per fee day. By 2026-08-07 the drift ($0.03 = three post-bootstrap fees, verified to the cent against `/v2/account/activities`) exceeded the $0.01 reconciliation tolerance and every nightly `paper-observation` correctly refused to capture evidence — the epoch stalled at 1 session with a critical alert. Dividends/interest arrive on the same stream. This is incorrect durable state / missing recovery (P2), not unsafe execution or broken atomicity (P1). The detector worked; the books were wrong. | **Resolved after independent correction 2026-08-10** at `a8174b9`; see `docs/Review/REVIEW_2026-08-10_EPOCH_ACTIVITY_INGESTION.md`. Merged as PR #182 and deployed 2026-08-10. **The self-heal is now verified operational fact:** first post-deployment `ledger-reconcile` inserted the three fees exactly once and returned `matched: true` with zero mismatches; the follow-up operations-cycle replay counted them as 3 idempotent duplicates. Widening the tolerance remains rejected. |
| AP-7 | P2 | **False-positive critical alert from a negative-age race** (measured read-only 2026-08-10 on the epoch host). `operational_health()` captured `now` before readiness/broker work, while overlapping scheduled processes could commit a reconciliation, backup, or restore drill just afterward. The correct future-date lower bound then treated that valid newly read fact as future-dated. The observed critical alert said matched with zero mismatches but still blocked the operations cycle and promotion gate. This is material fail-closed operational behavior, not a minor documentation issue. | **Corrected, independently reviewed, counter-reviewed, merged as PR #185 at `2c886c1`, and deployed in the owner-authorized epoch-004 roll at `b837374`.** Each freshness site contains a post-read-clock correction, reports signed `age_seconds`, and still uses a frozen caller-supplied as-of clock so genuine future rows refuse. The first two post-deployment cycles reported non-negative ages, but that observation did **not** prove the whole production call path: AP-11 later showed the outer orchestration still supplied a manufactured frozen clock to the nested readiness site. The site-level AP-7 code deployed with epoch-004; the end-to-end AP-11 repair **deployed 2026-08-13 in the epoch-005 roll** at `752d3b7`, so the full production path is now corrected — watch for the absence of new negative-age freshness warnings under epoch-005 rather than assuming it. Deliberately not unified with `risk/execution_gate.py`'s external broker-clock tolerance. |
| AP-5 | P3 | 4 of 5 `REQUIRED_PROMOTION_DRILLS` have no producer (only `backup_restore` does) — structurally unproducible until GR-3/GR-5 | **Resolved and independently reviewed 2026-08-03:** GR-3 adds exact-lineage producers for ambiguous_submission, restart_recovery, and kill_switch; GR-5 adds alert_delivery through its storage-verified self-test. All five drill types now have producers. Do not fake any of them. |
| AP-8 | P2 | **Ticker-suggestion surface silently withheld real, top-of-market rows** (found 2026-08-12 when the owner compared the module against yfinance by hand and asked why SPCX was missing). Live measurement that day: 3 of the 10 most-active names were dropped. Two distinct causes. (a) A genuine defect — `verify_tickers()` read only `info["longName"]`, so NBIS (Nebius Group N.V., Nasdaq NMS, ~$3.6B median daily dollar volume) was rejected as having no company name although yfinance persistently returns it in `shortName`/`displayName`; a provider metadata gap was being reported as a fact about the security. (b) `DEFAULT_ELIGIBILITY_POLICY`'s size/age/price screen removing real listings — SPCX at 41 sessions against the 60-session floor despite a ~$1.9T market cap and ~$10.7B median daily dollar volume, and PLUG at $2.28 against the $5.00 floor. Compounding both, the UI reported only a bare count ("3 candidate ticker(s) could not be verified"), which is why this stayed invisible until an external comparison. | **RESOLVED AFTER INDEPENDENT CORRECTION 2026-08-12; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Implementation `d326a74`, correction `7c21339`; see the AP-8b row and `docs/Review/REVIEW_2026-08-12_AP8_TICKER_SUGGESTION_DISCLOSURE.md`. The owner-directed disclosure policy now shows rather than screens real named US equities, while review restored the exact identity/data-validity boundaries and made both UI consumers disclose the relaxed screen. |
| AP-9 | P2 | **The Buying page discarded valid Claude allocation reviews and said nothing** (owner-reported 2026-08-12 after enabling AI and finding no review under the inverse-volatility purchase split). Diagnosed read-only from the operator `ai_runs` audit log: the call fired twice that afternoon (~9s each) and both were rejected with `failed post-hoc validation`. Cause was an undocumented, untested `_MAX_SUMMARY_LENGTH = 500` character cap; the two rejected summaries were 554 and 670 characters, against 480 and 441 for the two that succeeded on 2026-08-07. **Length was never a safety property here** — the checks that carry the safety (percentages, dollar figures, unknown tickers, advice language, per-ticker number attribution) read the whole string regardless of length, and re-running every observation from both rejected responses through all four confirmed each one passes. Compounding it, `review_allocation_plan()` returned `None` on every failure path and the UI rendered `if ai_review:` — so a rejected review, a failed call, and an unticked checkbox were visually identical. `_MAX_CLAIM_LENGTH = 300` was worse in kind: an over-long claim was dropped silently, and if it was the only one the all-observations-failed rule rejected the whole review. | **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-12; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Claude implementation `3f1faf3`; Codex correction `6295b2f` on `codex/review-ap9-allocation-visibility-20260812`; detailed disposition in `docs/Review/REVIEW_2026-08-12_AP9_ALLOCATION_REVIEW_VISIBILITY.md`. Owner decision remains no prose-length cap. Review bound every outcome to the exact cart/weights/volatility/basket inputs so stale commentary is hidden after a split change; enforced the outcome XOR invariant; classified wrong-root JSON and empty input honestly; and updated the touched Streamlit dataframe API. Reviewer validation: 3,445 passed, 0 failed/skipped, 25 known warnings under Python 3.13.14 / Streamlit 1.60.0. **Counter-review (Claude, 2026-08-12) accepted all five findings — each re-established by mutation — and closed two more, both generalizations of review findings.** AP9CR-001 (P3): AP9R-003's honesty fix guarded the JSON root but not the fields — `observations` as null or a number raised TypeError into the broad except and was reported as a failed call, and a string iterated silently into a misleading all-observations-failed reason; a non-list `observations` now reports as unparseable, while an absent key still yields a valid summary-only review. AP9CR-002 (P3): the identical stale-state defect AP9R-001 fixed existed one block above it — `watchlist_ai_suggestions` stored no cart identity, so suggestions and their measured-evidence columns rendered under a header naming the CURRENT cart after an edit; the stored state now carries its cart and a mismatch hides with a reason, legacy state failing safe as stale. Counter-review also merged `origin/main` `27fa872` (AP-8) into the branch, resolving documentation-only conflicts, so integration is done. |
| AP-10 | P2 | **One malformed optional most-active volume suppressed the whole recommendation batch** (independent full-project review 2026-08-12). `classify_price_direction()` validated its adjacent provider field, but `build_recommended_tickers()` sent raw `volume` to the comma-format mini-language. A truthy string raised `ValueError`; NaN, infinity, a bool, a negative count, or a fractional count rendered as measured trading volume. This contradicted AP-8's batch-isolation and unavailable-data contracts. | **RESOLVED, MERGED to `main` via PR #196 at `1a46881` (2026-08-12); DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Correction `67558f5` on `codex/independent-full-review-20260812`: `_trading_volume_detail()` now uses the canonical finite decimal boundary, accepts only non-negative whole share counts, and emits `trading volume today: not reported` for every unusable value without dropping any verified row. Seven dangerous-direction cases plus a valid sibling row are regression-pinned; reverse mutation failed all seven. **Counter-review (Claude, 2026-08-12): confirmed** — the mutation result was independently reproduced (7 failed reverted, 7 passed restored) and no further instance of the raw-optional-provider-field formatting class was found; two follow-ups (IPRCR-001 P3 post-merge handoff topology, IPRCR-002 P2 leftover review worktree breaking pytest collection on the development checkout) are recorded and resolved in the review report's counter-review section. Advisory presentation only; no proposal, policy, broker, order, scheduler, epoch, or execution path changed. |
| AP-11 | P2 | **The AP-7 freshness-race fix is dead code on every production path** (observed live 2026-08-13T05:40:49Z on deployed epoch-004: `reconciliation_freshness` warned `age_seconds=-0.117315, errors=0` for a healthy reconciliation, and `healthy=all(...)` fails the operations cycle on it). The AP-7/DCCR-CR-002 corrections capture a post-read clock only when `now` is None — but `operational_health()` did `now = now or datetime.now(...)` at entry and passed that manufactured clock down as an explicit `now` into `transaction_readiness()`, freezing the nested check to a clock captured before ~5 s of integrity/broker work. `monitor-orders` rewrites `last_order_reconciliation` every 30 s; a write landing inside that window looks future-dated. `build_platform_readiness()` had the same manufacture-then-pass shape. The AP-7 regression tests stayed green because they call each function directly with `now=None` — the shape production never uses. | **RESOLVED, MERGED via PR #198 at `72b6278`, and DEPLOYED 2026-08-13 in the epoch-005 roll at `752d3b7`.** Both sites now forward the CALLER's original clock (`now=explicit_now`) instead of the manufactured entry clock: live paths let the nested checks capture post-read clocks, while a genuine caller-supplied as-of clock still freezes the whole chain (FCS-017 unchanged, pinned in both directions). New regression tests drive the exact production call shape (`operational_health` with `now=None`, advancing clock, concurrent write) and the platform-report forwarding contract; both reddened under fix-reverting mutation and passed restored. **Independent Codex review 2026-08-13: accepted after CODCR-001 (P3) corrected the current action-plan and durable operational-facts claims that still called the full deployed AP-7 path fixed. Production code and submitted AP-11 tests were accepted unchanged.** |
| SELL-1 | feature | **Owner request 2026-08-13: sell an individual currently-held position from the Selling tab.** Until now the Selling page could only act on a deterministic policy breach (`generate_risk_reduction_proposals`), so there was no in-app way for the owner to sell a specific holding on their own judgement. | **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-13; merged to `main` in PR #203 at `08fde9f`; DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** Claude implementation `918eecd`; integration merge `dc1233a`; Codex correction `3ba3d41` on `codex/review-claude-sell1-cleanup-20260813`; detailed dispositions and issue ledger in `docs/Review/REVIEW_2026-08-13_SELL1_AND_BRANCH_CLEANUP.md`. The reviewed module produces one `proposed`, typed-approval-gated sell with evidence status `user_directed_sell`, explicit refusals, exact broker-share and Decimal order-value boundaries, truthful fractional-remainder wording, and the same tax advisory as the policy-breach path. The Streamlit card is hidden when ticker or share selection no longer matches. The shared execution gate now checks exact broker share text, closing a P1 route where `10.999999999999999999` rounded to `11.0` and authorized an 11-share sale. Nothing auto-submits; fresh paper-only validation remains authoritative. |
| BUY-1 | feature | **Owner request 2026-08-13: add a third cart source to the Buying panel.** The Buying page accepted candidates two ways (pick from common tickers, type any ticker). The owner asked to also pick from the most-active ticker suggestions — the same rows the Ticker Suggestions tab shows — by clicking a ticker straight into the cart. | **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-13; merged to `main` in PR #208 at `e0df810`; review correction `44a7f85` on `codex/review-buy1-suggestion-picker-20260813`; not deployed.** The explicit-click expander reuses the cached verified most-active lane without an AI or IPO call, keeps every row's AP-8 size/age/price/liquidity disclosure beside its Add control, distinguishes source fetch time from display time, and names suggestion provenance in the cart. Independent review closed two P2 and two P3 findings: flat and unavailable-change rows were named but not clickable despite the every-row contract; changing the cart left checked prices/volatility active and could expose approve-gated proposal controls for the previous cart; the click time hid cached source freshness; and current records still called the merged feature pending. Checked results now carry the exact cart identity and fail closed on any edit. Adding still buys nothing: cart selection, deterministic checking/splitting, proposal creation, typed approval, and fresh paper execution validation remain separate. **The review branch was owner-merged as PR #209 at `df83510`. Counter-review (Claude, 2026-08-13): all four findings confirmed** — each re-established red on the exact submitted tree `e0df810` and each code correction proven load-bearing by reverse mutation (3/3 caught) — **and one generalized P3 instance closed at `2fe6747` on `user/claude/buy1-counterreview-20260813` (BUY1CR-001):** the dedicated Ticker Suggestions page named flat/unavailable-change most-active rows by bare ticker without their AP-8 measurement detail, the same direction-as-disclosure-gate defect BUY1R-002 fixed on the Buying picker. **Independent Codex verification of Claude's two-commit range (`df83510..276b3c2`) accepted both commits without further correction:** the focused suite passed 69 tests, the detail-table reverse mutation failed the intended behavioral regression, and the full suite passed 3,635 tests with a writable base-temp. See `docs/Review/REVIEW_2026-08-13_BUY1_SUGGESTION_PICKER.md`. |
| TRADE-1 | feature | **Owner request 2026-08-14: separate budget/policy trading from owner-directed trading, and support dollar-sized orders.** "Buying" was budget-driven (one amount split across a cart by inverse volatility) and "Selling" was policy-driven (act only on a computed breach). The owner asked to rename those to **Budgeted Buying** and **Policy Based Selling**, and to add **Discrete Buying** and **Discrete Selling** for single-name decisions, each sized either by share count or by dollar amount, with the BUY-1 suggestion picker available on Discrete Buying. | **COMPLETE AFTER INDEPENDENT CORRECTION AND COUNTER-REVIEW; MERGED TO `main` IN PR #214 AT `cfed8c8`; not deployed.** Claude implementation `c1dec52` plus follow-up `c638bc7`; Codex corrections `93953ef` and `7ad7f7d`; Claude counter-review `9e07bf9` confirmed all eight findings and closed TRADE1CR-001. The reviewed four-page separation, exact Decimal dollar budgeting, stale-card binding, BUY-1 disclosures, and Alpaca-inspired Streamlit shell are preserved in the merged tree. SET-1 now optionally changes quantity granularity, but the TRADE-1 workflow separation is unchanged. Full disposition remains in `docs/Review/REVIEW_2026-08-14_TRADE1_DISCRETE_TRADING.md`; the integration disposition is in `docs/Review/REVIEW_2026-08-14_SET1_SETTINGS_AND_FRACTIONAL_TRADING.md`. Development remains separate from the frozen epoch-005 runtime at `752d3b7`. |
| SET-1 | feature | **Owner request 2026-08-14: make whole-share-only ordering and the cash reserve owner-configurable.** The owner wants optional fractional shares and treats Alpaca as only a small slice of total assets, so an in-account reserve may be unnecessary. Both controls must remain safe by default. | **COMPLETE AFTER INDEPENDENT CORRECTION, COUNTER-REVIEW, AND INDEPENDENT VERIFICATION 2026-08-14.** Claude's implementation reached `main` through PR #213 at `a62aa1a`; Codex's end-to-end fractional correction `89156b7` merged through PR #217 at `ca0cdf0`; Claude's counter-review `45a510c` merged through PR #218 at `7055142`; and Codex's verification correction `29290d9` merged through PR #219 at `0f4f41c`. Claude verified strict defaults, fail-closed `fractionable`, exact reconciliation, and closed SET1CR-001 … 004: stranded fractions were hidden, magnitude was unbounded, one unreachable defensive handler manufactured zero, and daily-budget conversion was unguarded. Codex independently accepted all four trading fixes after correction: the added development launcher isolated SQLite but did not engage the kill switch protecting the shared paper account (P2), omitted two supported provider keys (P3), and adjacent AppTests leaked cached policy/widget state (P3); post-merge active records were also stale (P3). See `docs/Review/REVIEW_2026-08-14_SET1_COUNTERREVIEW.md` and `docs/Review/REVIEW_2026-08-14_CODEX_SET1_COUNTERREVIEW.md`. `whole_shares_only` remains strict by default, boolean-validated and fingerprint-bound; when explicitly disabled, Budgeted Buying, Discrete Buying, and Discrete Selling preserve exact quantities up to nine decimal places through proposal, authorization, gate, broker submission, and reconciliation. Fresh validation and submission require broker-marked fractionability; floats remain invalid. Reserve-off writes zero but negative cash still refuses. Both settings remain behind typed `UPDATE POLICY`, atomic expected-fingerprint persistence, and proposal invalidation. One owner design question remains open: whether strict mode should allow a fractional sell only when it closes the entire position. Nothing is deployed; operational commit `752d3b7` and epoch-005 are unchanged. **Deployment consequence:** the new fingerprint field changes execution lineage even at its safe default, so deployment closes epoch-005 and still requires separate owner authorization. |
| STALL-1 | operations | **Owner request 2026-08-14: detect when paper-evidence observations stop accumulating.** The existing capture path fails closed and alerts on an individual refusal, but the owner also needs a direct read-only answer about the active epoch's multi-session cadence. | **COMPLETE AFTER INDEPENDENT CORRECTION AND COUNTER-REVIEW 2026-08-14; merged to `main` in PR #221 at `1babbcf`; not deployed.** Claude implementation `6aa7069`; Codex correction `4273de6`; full disposition in `docs/Review/REVIEW_2026-08-14_EPOCH_STALL_DETECTOR.md`. The standalone CLI classifies `NOT_DUE_YET`, `HEALTHY`, `BEHIND`, `STALLED`, and `NO_ACTIVE_EPOCH`, opens SQLite with enforced `mode=ro`, anchors expected sessions to the active epoch, and treats only the two healthy states as exit 0. Review corrected two P2 and five P3 defects, chiefly replacing market-close-derived timing with the measured fixed 16:30 Pacific task wall clock plus configurable remeasurement options, and making no active epoch unhealthy. Full corrected tree: 3,783 passed. This is advisory only: it does not write, repair, restart, schedule, deploy, roll an epoch, or trade. The operational runtime remains `752d3b7` under the owner's 60-day hold. |
| HEDGE-1 | feature | **Owner request 2026-08-14: add hedging.** The app could buy, sell on policy breach, and sell on owner instruction, but had no way to size a DEFENSIVE position against portfolio exposure. Owner selected an inverse/defensive ETF sleeve over options, and proposal-only over observation-only. | **COMPLETE AFTER INDEPENDENT CORRECTION 2026-08-14; merged to `main` by PR #223 at `17be33b`; review correction `46e1248` awaits owner authorization to push.** Claude's `1f60ebf` implementation adds an owner-directed equal-weight SH/BTAL/TLT/GLD sleeve, report-only mode, APPROVE-gated buy proposals, no sell, and no submit-all. Codex review closed five P2 and three P3 findings: the public module now enforces the configured instrument set; corrupt or zero exact held values refuse; open-order availability and pending buy values participate in the target gap; every selected leg must have a usable price and minimum quantity or the whole basket refuses; authoritative money and price inputs stay Decimal; deployment/epoch language is correct; and active-document topology is regression-pinned. The feature still makes no protection or profit claim. Mandate and policy fingerprints are unchanged, but any deployment would change `code_commit` and close active epoch-005; no deployment occurred. **Counter-review (Claude, 2026-08-15): all eight review findings independently re-derived on a worktree at the submitted tree `17be33b`; seven confirmed exactly, HEDGER-005 partially correct (right direction and fix, but its stated `100/3` float arithmetic does not reproduce -- the excess appears one step later at ~7e-14 dollars). Four further defects closed at `user/claude/hedge1-counterreview-20260815`:** the new topology guard asserted equality with the current `origin/main` tip and therefore could not stay green past its own merge (P2, now a reachability assertion); the pending-order refusal was not gated on report-only mode and turned the page's default state into a red error (P2); a zero-share row bricked the whole page including the read-only weight (P3); and the new all-or-nothing refusals named no remedy (P3, the SET1CR-001 class). The Decimal fix was also unpinned and is now source-guarded (P3). See `docs/Review/REVIEW_2026-08-14_HEDGE1_DEFENSIVE_SLEEVE.md` and `docs/Review/REVIEW_2026-08-15_HEDGE1_COUNTERREVIEW.md`. |
| REBAL-1 | feature | **Owner request 2026-08-15: wide-band portfolio rebalancing.** | **ALL THREE STAGES COMPLETE IN DEVELOPMENT AFTER INDEPENDENT REVIEW AND MERGED INTO `main` BY PR #230; not deployed.** Stage 1 is the exact read-only drift report, Stage 2 is owner-directed buy-only cash steering, and Stage 3 is separately approved tax-aware trimming. The allocation targets are owner preference, not evidence of edge. See the three REBAL review reports and `docs/REBAL1_MILESTONE_PLAN.md`. |
| REBAL-2 | feature | **Stage 2: buy-only cash steering.** | **COMPLETE, MERGED THROUGH PR #229, not deployed.** Implementation `c0d56d5`, independent correction `bdeb61d`, counter-review `bedb598`; 3,977 tests passed on that reviewed tree. Stage 3 is complete after the separate REBAL-3 review below. |
| REBAL-3 | feature | **Stage 3: tax-aware trims of overweight sleeves, explicitly authorized by the owner on 2026-08-15.** | **ACCEPTED AFTER INDEPENDENT CORRECTION 2026-08-15; MERGED INTO `main` BY PR #230 AT `84e73af`; NOT DEPLOYED.** Claude's pushed exact head is `bedeea2` (`0490d9d` product, `bedeea2` records); Codex correction is `ed6879d` on `codex/review-rebal1-stage3-20260815`. Review closed eight P2 and one P3 findings: the real coverage contract now works, every owner choice starts unset, fractional input stays exact, working sells are positive/gross and visible, proposal identity and durable evidence bind the tax lots, one clock controls holding-period labels, duplicate named lots refuse, and execution revalidates the complete current lot ledger before broker import. Final validation: 243 focused and 4,026 full-suite tests, 25 known warnings, clean compilation/diff. Lot selection remains advisory to Alpaca; every sale still needs separate typed approval and all normal paper-only execution checks. See `docs/Review/REVIEW_2026-08-15_REBAL1_STAGE3.md`. |
- **Counter-review (Claude, 2026-08-15): all nine review findings independently re-derived on a worktree at the submitted tree `bedeea2`; all nine confirmed.** ST3R-001 is the headline and deserves stating plainly: the submitted feature REFUSED EVERY TRIM, always, because it read a per-ticker `complete` key the real coverage provider never emits (`broker_shares`/`ledger_shares`/`matched`). The tests passed only because the fixture was an invented shape rather than one obtained from the real producer -- the same root cause as Stage 2's REBAL2CR-001 one round earlier, and worse here because a refusal that always fires is indistinguishable from a careful safeguard. ST3R-002 also contradicted the submitted documentation: the sleeve picker auto-selected while the handoff claimed all four owner decisions start unset. ST3R-007 was a defect in shared tax machinery -- `select_lots` took 150 shares from a 100-share lot on a duplicated lot id. **One P2 closed at `user/claude/rebal1-stage3-counterreview-20260815` (ST3CCR-001):** the corrected coverage gate still required GLOBAL completeness, and since `list_fills` documents that pre-app holdings produce no lots, a single such holding refused every trim permanently -- the same always-refuses outcome through a different gate, and the owner's real book would have hit it. Both the creation and approval gates are now scoped to the trimmed ticker's `matched` flag, which is necessary and sufficient because the sale realizes gains from that ticker's lots alone; the uncovered remainder is disclosed instead of blocking. The ST3R-008 execution-path change was audited separately and accepted. See `docs/Review/REVIEW_2026-08-15_REBAL1_STAGE3_COUNTERREVIEW.md`. Full pinned-venv tree 4,031 passed / 0 failed; 4 mutations against the fix, all detected. |
| REBAL-3E | quality | **Owner request 2026-08-15: add the end-to-end test with real fills.** Three consecutive rounds of Stage 2 and Stage 3 failed the same way -- an interface-shape mistake that hand-written fixtures could not detect -- and two of them produced a refusal that always fired, which reads exactly like a careful safeguard. | **IMPLEMENTED 2026-08-15; MERGED INTO `main` BY PR #230 AT `84e73af`; NOT DEPLOYED; still awaiting independent review of the end-to-end round itself.** Branch `user/claude/rebal1-e2e-real-fills-20260815`; disposition in `docs/Review/REVIEW_2026-08-15_REBAL1_STAGE3_END_TO_END.md`. `tests/test_rebalance_trim_end_to_end.py` invents no shapes: fills are journaled through `journal_broker_order_update`, ledger and coverage come from the real providers, the proposal is persisted through `AssistantStore.save_proposal` and reloaded, and approval runs the real validation path. **Writing it immediately found a fourth instance of the same defect, in my own previous fix:** `tax_ledger_with_coverage` returns `(ledger if complete else None, ...)`, so it withholds the ledger ENTIRELY when any holding is unreconciled -- meaning the ST3CCR-001 fix, verified only against a hand-built dict pairing a real ledger with `complete: False`, never worked against the real provider and Stage 3 was still unusable on any book with a pre-app holding. Fixed with a new sibling `ticker_tax_ledger_with_coverage(store, portfolio, ticker)` rather than by loosening the shared portfolio-wide contract: the two answer different questions, and a trim's realized gain depends on one ticker's lots alone. All three call sites -- `plan_trim`, the execution-time revalidation, and the Stage 3 UI -- now use it. Remaining gap recorded: no test clicks the Streamlit trim button through to a saved proposal. Full pinned-venv tree 4,041 passed / 0 failed; 10 new end-to-end tests; 3 mutations against the new provider, 3 detected. |
| REBAL-3V | quality | **Owner-reported usability defect while exercising the dev app, 2026-08-15.** The owner could not find the "Target reachable" column, and reported that the drift table has no horizontal scrollbar. Feasibility was the ninth and last column of a nine-column table, so on a normal window the one fact stating whether the sleeve targets can be reached at all was unreadable in the real app -- and the positive case was never stated at all, leaving "reachable" to be inferred from an absent warning. | **ACCEPTED AFTER INDEPENDENT CORRECTION; merged by PR #231, with correction `3a506ae` and records `dae34d0` merged by PR #234 at `f63fe2c`; not deployed.** The width-independent positive/negative block and per-row "Reachable" value are correct and presentation-only. Review closed one P3 test-sensitivity defect: one submitted pytest was empty, and the claimed positive-case test accepted either exclusive branch while depending on an ignored personal policy. Deterministic coverage pins the positive case plus all four real conflict rules. See `docs/Review/REVIEW_2026-08-15_REBAL3V_REBAL3W_INDEPENDENT.md`. |
| REBAL-3W | quality | **Owner-reported contradiction, 2026-08-15, found while exercising Stage 3 on a real book.** The page reported "Bands breached: 6" in its headline and, three subheadings lower, "No sleeve is above its upper band". Both cannot be true, and the second was false: cash and the residual were both above their upper bands. The submitted generic `overweight_sleeves()` combined above-band and trimmable into one filtered list, so an empty result lost which condition failed. | **ACCEPTED AFTER INDEPENDENT CORRECTION; merged by PR #232 at `18a3ee5`, with correction `3a506ae` and records `dae34d0` merged by PR #234 at `f63fe2c`; not deployed.** The refusal/eligibility direction is unchanged. One immutable classification now returns both trimmable and untrimmable groups, and the refusal states the exact trim-eligible fact. See `docs/Review/REVIEW_2026-08-15_REBAL3V_REBAL3W_INDEPENDENT.md`. |
| ALPHA-BATTERY-20260815/16 | research | **Owner-requested broad alpha battery and three-universe rerun, merged by PR #236 at `3d58f6b`.** | **SUBMITTED RESULTS INVALIDATED BY INDEPENDENT REVIEW 2026-08-16; no signal confirmed.** Review of every commit in `f63fe2c..3d58f6b` closed five P2 and two P3 findings in correction `124192f` (merged by PR #237): the first test could not attain its own Bonferroni threshold; long/short side flips registered zero turnover; market caps mixed split-adjusted prices with raw shares; SEC availability was guessed instead of filed; the “survivorship loss” denominator preceded the universe screens; the latest size bucket leaked into all historical industry/residual scores; and the merged classifier called near-zero broad results robust. Invalid generated JSON/Markdown was removed from active docs on 2026-08-17 after its hashes and disposition were preserved in `docs/alpha-result.md`. Corrected code uses actual filing dates and raw screening prices, refuses old caches and unavailable point-in-time industry inputs, and labels the panel non-point-in-time. A clean reviewed QC rerun is required; no registry, mandate, proposal, execution, or epoch authority changed. See `docs/Review/REVIEW_2026-08-16_ALPHA_BATTERY.md`. |
| QC-ALPHA-20260816 | research | **Claude's QuantConnect smoke work and A/B/C replication battery at pushed head `667cbf4`.** | **ALL SUBMITTED CLOUD RESULTS REJECTED; FULL RE-AUDIT SUPERSEDES THE EARLIER CORRECTION.** The first independent review closed ten P2 and one P3 findings in `e8eb558`; the 2026-08-17 full-tree audit found additional current-API, framework-shadowing, PIT-factor, exact-session, provenance, numeric-refusal, and stall-handling defects and corrected them in `855941a`. Invalid generated results/logs were removed from active docs after permanent ledger preservation. No QuantConnect call occurred during either Codex review. Claude must counter-review and rerun exact final pushed source before any result is cited. See `docs/Review/REVIEW_2026-08-16_QUANTCONNECT_ALPHA_BATTERY.md` and the round-2 report. |
| ALPHA-QC-ROUND1-20260816 | research | **First staged Claude push on `origin/user/claude/alpha-qc-round-20260816` at exact head `ad6475d`: five preserved QC artifacts, result-ledger opening, and residual peer-length fix.** | **ACCEPTED AFTER CORRECTION; COUNTER-REVIEW AND NEW QC RERUN PENDING.** Independent review closed four P2 and one P3 findings. The peer equality was a real refusal cause, but the slice-only fix measured the skipped latest month instead of the 6-1/12-1 formation window. Product correction `8bf8a82` now uses a fixed 252-session joint market/leave-one-out-industry fit, measures 105/231 formation sessions, skips the latest 21, and has behavioral tests. Follow-up `56bc86d` binds every deque close to its exact exchange session and refuses missing, duplicated, or post-universe-gap history instead of manufacturing adjacent returns. The ledger now counts all five cloud executions, records 80 emitted repeated-look cells and a conservative lifetime floor of 428, acknowledges the existing base64 decoder, uses exact artifact hashes/backtest IDs, and marks missing compile/project identities. No saved market output was analysed and no QC access occurred. `docs/Alpha_Test_Implementation_Plan.md` freezes the staged replication/new-hypothesis program and reserves Alpaca Paper for later forward/execution testing. See `docs/Review/REVIEW_2026-08-16_ALPHA_QC_ROUND1.md`. |
| ALPHA-QC-STAGE1-20260817 | research | **Claude's REP-H52 / REP-IDV Stage 1 implementation at exact pushed head `dc63eec`.** | **ACCEPTED AFTER CORRECTION; CLAUDE COUNTER-REVIEW AND QC EXECUTION PENDING.** Independent review closed two P1 and two P2 findings in `b143c60`. Submitted scoring happened at the first monthly session and settlement at the next month's entry, not the frozen month-end/next-close/exact-21 experiment; REP-IDV applied the score-date universe backward across 111 factor days and filled unavailable factor returns with zero; and no cadence-matched benchmark or Stage 1 analyser existed. Corrected code freezes the immediately preceding month-end, enters next close, tracks overlapping exact-21-session cohorts, records PIT daily equal-weight factor returns with exact-session refusal, adds a matching benchmark, and requires full alpha/benchmark run identity plus 24-cell and 452-cell gates. No QC access or run occurred and the lifetime floor remains 428. See `docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md`. |
| ALPHA-QC-FULL-AUDIT-20260817 | research quality | **Owner-directed clean-slate review of all research/QC code and today's documentation.** | **CORRECTED, VALIDATED, MERGED BY PR #241 AT `d8a3260`, COUNTER-REVIEWED BY CLAUDE AT `ad3b3a8`, INDEPENDENTLY ACCEPTED BY CODEX AFTER A P3 RECORD CORRECTION, MERGED BY PR #242 AT `f937bfb`, AND FINALLY COUNTER-REVIEWED AGAIN BY AN INDEPENDENT CLAUDE SESSION ON 2026-08-17 (ALL TEN COMMITS ACCEPTED; FOUR P3 GAPS CCR3-A..D CLOSED); QC RERUN IS THE ONLY REMAINING RESEARCH STEP, PENDING THE OWNER'S STAGE-ORDER CALL.** Claude's counter-review verified the head with seven independent mutations: four detected, three surviving mutations became findings CR2-001..003 (all P3 test gaps over correct behaviour — the Stage 1 score-cutoff call site, the market-factor recorder's refusal, and Stage 1's own turnover copy were unpinned) and were closed with mutation-verified tests in the counter-review commit. Codex retained all three tests and corrected stale main/branch/worktree claims as CR2IR-001 on `codex/review-alpha-qc-counterreview-20260817`; see both counter-review records under `docs/Review/`. Corrections `855941a` and `1e2b631` repair the full LEAN/analyzer/runner surface and the older local turnover/NAV/peer/regression methodology. Every commit from `db0045a` through `a37e73b` has an explicit disposition. Invalid active artifacts were removed while the permanent ledger preserved identities and look counts; the docs tree was organized; a plain-language alpha glossary was added. Final pinned-environment validation after integrating the counter-review tests: 4,192 passed, 0 failed, 25 known warnings. No valid result or milestone exists, no QC access occurred, and the lifetime floor remains 428. The 2026-08-17 final counter-review re-verified the whole chain with sixteen mutations and closed four further P3 gaps (unpinned 24/428 multiplicity gates, the untested poll-deadline path, the incomplete LEAN legacy-name blocklist, and the ledger's undocumented CRLF hash convention). See `docs/Review/REVIEW_2026-08-17_ALPHA_QC_ROUND2.md` and `docs/Review/REVIEW_2026-08-17_ALPHA_QC_FINAL_COUNTERREVIEW.md`. |
| ALPHA-QC-FABLE-VERIFY-20260817 | research quality | **Owner request: verify Fable's merged final counter-review before starting QC.** | **COMPLETE AFTER CLAUDE COUNTER-REVIEW AND CODEX VERIFICATION; ALGORITHM CODE ACCEPTED AT PR #244.** Fable's exact three-commit range `5816f6f..6bd962f` was reviewed commit by commit after PR #243 merged it at `4151b3f`. Its tests are accepted, but its no-product-defect conclusion missed two P2 and two P3 Stage 0 defects. Correction `ac96d47` assigns each short holding its own entry plus exit turnover, infers the frozen 12/monthly and 42/short annualization cadence per family, requires an exact finite-positive MAX(20) window, and prevents missing industries from becoming a fake peer bucket. Claude's counter-review reproduced all four defects red on the pre-correction tree, ran seven mutations (one survivor became FCR-001: the drifted exit leg was unpinned on long/short books), found one surviving FQCV-004 instance in Stage 1's dead copied ingestion (FCR-002), and closed both with mutation-verified tests. PR #244 merged exact Claude head `9a7e9fc` at `b6f577e` with a byte-identical tree. Codex accepted all three commits and both closures; its only finding, FCRV-001 (P3), was a helper-only test that failed to pin the live industry ingestion call site, closed by test-only commit `39e5d99`. No QC access or look occurred; the cell/run ledgers remain 428/five. See `docs/Review/REVIEW_2026-08-17_ALPHA_QC_FABLE_COUNTERREVIEW.md`, `docs/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_CORRECTION_COUNTERREVIEW.md`, and `docs/Review/REVIEW_2026-08-17_ALPHA_QC_STAGE0_COUNTERREVIEW_VERIFICATION.md`. |
| ALPHA-QC-STAGE0-LAUNCH-20260817 | research quality | **Owner selected Stage 0 and authorized the frozen QC runs.** | **BATTERY COMPLETE 2026-08-18, ALL NINE CELLS PENDING_REVIEW; NO STATISTIC OBSERVED.** The owner-directed serial rerun ("continue to test. 1 at a time") ran to completion: monthly R-009/R-011/R-012 (A/B/C), short R-014/R-015/R-016 (A/B/C), benchmark R-022/R-020/R-021 (A/B/C), every raw cloud log round-tripping the frozen parsers, ledgered with full identity in `docs/alpha-result.md`. Run-level looks are now twenty-three. Two further defect classes surfaced and were fixed en route, both descendants of R-010's turnover-gating: R-013 (short A_large REFUSED — the packed v1 layout could not declare an absent spec-date, so one honest missing MAX_20 date withheld all 2,664 cells; fix `46221db` adds a per-date spec-presence mask and a turnover-unavailability sentinel, keeping v1 logs decodable) and R-017/R-019 (benchmark: the turnover-gated bind died silently at 2015-12 reporting 48 of ~156 months, then the all-names-priced settlement gate collapsed B_core coverage to 94/156 in a selectively calm pattern; fixes `5b5184a` and `39b3b89` make the bind unconditional and record underfill — priced AND entered counts per month — instead of dropping months). R-022's 149 months shared with the superseded R-018 replicate to 0.0 difference. **Independent review DONE 2026-08-18 (Cursor/Grok 4.6, substituting for token-exhausted Codex): full range `81db126..de1beac` dispositioned, all 27 commits accepted, eight findings (2 P2 blocking Stage 1 only, 6 P3), none invalidating the nine logs; Claude counter-review verified every finding — see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`. Remaining gate: owner acceptance of the review pair; upon acceptance the nine ledger entries upgrade and the frozen analysers run ONCE with full run identities — the only step at which statistics are observed. Stage 1 stays blocked until S0R-001/S0R-002 are ported.** Earlier this round: fix `d305ea0` (turnover is a cost input that never gates a result row) closed R-010's zombie-name die-off; R-009 cloud-confirmed the R-007/R-008 fixes. Earlier history: the rerun round found two defects: R-007 (A_large) completed fully but its legitimate per-date spec subsets were unparseable under the frozen parser (STALE, rerun required with SPECMETA counts), and R-008 (B_core) died off after 2017-01 to an unrecoverable turnover-refusal spiral (INVALIDATED). Both fixes are implemented with a forced-skip-month simulation that pipes the algorithm's own log through the real parser; R-007 (A_large) completed fully but its legitimate per-date spec subsets were unparseable under the frozen parser (STALE, rerun required with SPECMETA counts), and R-008 (B_core) died off after 2017-01 to an unrecoverable turnover-refusal spiral (INVALIDATED). Both fixes are implemented with a forced-skip-month simulation that pipes the algorithm's own log through the real parser. Before that, both monthly A_large and B_core refused with the same three missing residual/composite specs, consumed two run-level looks, emitted zero cells, and left the 428-cell floor unchanged. Claude correctly stopped and found the weekend-label empty-bucket defect, but its first fix still applied a newly selected month's universe backward to the prior day's bar on ordinary first-trading-day ordering. Codex correction `2219643` snapshots both selected names and industries at each selection and preserves the prior snapshot for that return. It also prevents evidence overwrite, records returned cloud project identity, hashes exact log bytes, uses the canonical runtime-identity service, and corrects R-006's source commit/hash. See `docs/Review/REVIEW_2026-08-17_QC_STAGE0_LAUNCH_ROUND.md`. |

## 7. The critical-path insight that should drive sequencing

An evidence epoch binds the exact git commit; **any runtime change closes the
epoch, and observations cannot pool across epochs**. Therefore the 60-session
clock only accumulates on a *frozen* runtime. Two workable models:

1. **Freeze-then-collect**: finish the runtime-touching code milestones
   (GR-1D/E, GR-2, GR-4, GR-7 core) first, then freeze and start the epoch.
   Cost: evidence start delayed by the remaining code work.
2. **Pinned operational host**: the operational machine runs a designated
   frozen release commit for the whole epoch while development continues on
   branches that are simply not deployed to it. Cost: discipline (the shared
   dev machine must not run the operational cadence from a moving checkout).

Since development currently happens on the same machine that would run the
cadence, model 1 is the safe default — but the owner should choose, because
model 2 starts the 3-month clock **now** and time is the scarcest input.

---

## 8. Adopted sequencing (owner-approved 2026-08-02)

**Phase 1 — UI feature controls (COMPLETE AND MERGED: implementation
PR #116, review chain PR #117 at `661a7d4`):**
Implemented `docs/reference/UI_FEATURE_CONTROLS_DESIGN.md` as one milestone:
the Settings & Features tab (three control classes), AI master + per-feature
preferences gating all four LLM surfaces, read-only data-source and safety
status panels (reading from the enforcing functions, never re-implementing
checks), the protected policy-update workflow for `allow_new_positions` /
`enable_strategy_proposals` (validation → explicit typed confirmation →
atomic write → version bump → new fingerprint → prior-proposal invalidation
warning), and the dedicated Ticker Suggestions surface. The design's four
open decisions are resolved (§9 item 11). PR #116 merged the implementation
at `4c8e959`; independent review accepted it after two P2 corrections
(`a6d5254`); Claude's third-round confirmation re-verified both corrections
red/green with a three-mutation sweep (all caught) and hardened one
environment-sensitive runtime-identity test the confirmation run exposed.
The review chain from `user/claude/ui-review-confirmation-20260803` merged
as PR #117. No live authority or formal evidence epoch was enabled.

**Phase 2 — hygiene (COMPLETE AFTER INDEPENDENT CORRECTION, 2026-08-03):**
AP-1 schema apply/verify, AP-2 runtime-artifact ignores, and AP-4 document
reconciliation were implemented at `34ce463`. Independent review corrected
one P2 fail-open verifier gap: same-named weakened indexes/triggers must not
pass. The durable disposition and issue ledger are in
`docs/Review/REVIEW_2026-08-03_PHASE2_HYGIENE.md`.

**Phase 3 — finish the kernel (COMPLETE AND INDEPENDENTLY REVIEWED):**
GR-1D reconciliation extraction is implemented, merged as PR #120 at
`711095c`, and independently accepted at `2f37210` with no code correction.
The GR-1E assessment (2026-08-03) declared GR-1 COMPLETE with no further
extraction. Independent review accepted that architectural conclusion after
correcting overbroad measurement, test-history, recovery-call, and
architecture-debt claims. The records are the GR-1E section of
`docs/operations/GENERAL_READINESS_STATUS.md` and
`docs/Review/REVIEW_2026-08-03_GR1E_ASSESSMENT.md`. Phase 4 later completed GR-3,
GR-5, and the independently reviewed GR-2 registry.

**Phase 4 — operational drill/alert prerequisites (COMPLETE AND
INDEPENDENTLY REVIEWED, 2026-08-03):**
GR-3 fault drills and GR-5 alert delivery are COMPLETE AND INDEPENDENTLY
REVIEWED. GR-5 uses Windows desktop toasts immediately for critical alerts,
batches warnings, preserves immutable delivery attempts, and requires a
successful self-test to clear a previous channel-failure condition. GR-2's
risk-check registry was implemented at `03895ae` and independently accepted
after correction at `0167c67`; Claude's counter-review (2026-08-03, appended
to `docs/Review/REVIEW_2026-08-03_CLAUDE_INTEGRITY_GR2.md`) confirmed every finding
and correction, closing Phase 4 with both agents' verification on record.
Phase 5 is active and owner-heavy. Its non-elevated preflight was independently
reviewed and corrected 2026-08-03 on the development machine (installer
previews, CLI producers, fault harness, fail-closed readiness; see
`docs/operations/PHASE5_DEPLOYMENT_SESSION.md` for results and the ordered owner
session). On 2026-08-04 the owner chose model 2, approved the mandate, retained
the existing operator database, and chose the owner's account for scheduled
tasks. The mandate implementation and independent review merged through
PRs #146/#147; PR #148 then added the reviewed operational-only verifier scope.
The first elevated install on 2026-08-05 registered all four operational tasks
but Credential Guard blocked their S4U launches. The independently corrected
follow-up adds Interactive-logon host bootstrap and post-start
`-RequireTaskRun` verification; the owner must reinstall/start/verify before
ledger bootstrap or any epoch action. No such action follows without the
owner's specific direction.

**Phase 5 — operational deployment + epoch collection (COMPLETE AGAIN after
the 2026-08-13 epoch-005 roll; epochs 001 through 004 are closed;
`paper-epoch-005` is active on the epoch host at `752d3b7`; see
`docs/operations/OPERATIONAL_FACTS.md` for the executed sequence):**
merge the independently reviewed approved mandate → pin the model-2
operational checkout → elevated scheduler window under the owner's account →
install + verify the 4 operational tasks (`-WhatIf` first) → install the
additional 4 ML shadow tasks only if a reviewed shadow configuration and
artifact are available and the owner wants ML collection in this epoch →
ledger bootstrap/reconcile → start the first paper evidence epoch on the
frozen commit → run all 5 drills inside it → let the 60-session clock run.
From here on, the machine collects evidence while development continues
un-deployed under model-2 discipline. Note: the owner's informal paper trading
does not substitute for formal epoch evidence. **Owner ops/UI hygiene
(2026-08-05 → 2026-08-06):** policy-path resolution, task self-heal,
singleton, and UI chrome are merged (PRs #157–#159). **Epoch re-bind
executed 2026-08-06:** `paper-epoch-001` closed; `paper-epoch-002` ran on
frozen commit `9a91498` bound to `my_policy.json`, later stalled at one
captured session by AP-6. **AP-6 swap EXECUTED 2026-08-10 in exactly the
required order** (disable tasks → close epoch-002 on its frozen runtime →
deploy merged `ef05dc1` → `ledger-reconcile` matched → readiness → start
epoch-003 → all five drills recorded → tasks re-enabled and a manual
operations-cycle verified green, 0 open alerts at swap completion). The first
scheduled epoch-003 post-close capture then succeeded on 2026-08-10 with one
lineage-matched observation and zero ledger mismatches, so the evidence clock
has started. **Full-project sweep
(2026-08-06, PR #160 / `87593f8`):** independently accepted after correction
— FPS-001/004 evidence-integrity fixes confirmed; residual
`tax_ledger_with_coverage` share conversion closed (GFPS-001); FPS-003
intermittent UI chrome left open. Does **not** reorder the roadmap. See
`docs/Review/REVIEW_2026-08-06_FULL_PROJECT_SWEEP.md`,
`docs/Review/REVIEW_2026-08-06_FULL_PROJECT_SWEEP_INDEPENDENT.md`, and
`docs/SESSION_HANDOFF.md`.
(from 2026-08-03) already accumulates real order/telemetry/ledger data before
any formal epoch; that data informs execution realism but does not count toward
the mandate's 60-session minimum, which requires one immutable epoch.

**Phase 6 — parallel product work during the evidence window (pick by owner
preference, all non-runtime):**
**UI Phase 2 (owner-requested 2026-08-03, jumps to the front of this phase
— the owner is paper trading daily and these directly support it)** →
~~committee replay corpus + CLI surface~~ (complete after independent
correction 2026-08-05) → ~~GR-4 data honesty~~ (complete after independent
correction 2026-08-05) → GR-7 product
completeness (fold in the allocation-service design here, per Codex's
recommendation, so the app keeps one authoritative sizing path).

**UI Phase 2 — four owner requests, grouped into implementation milestones:**

| # | Item | Owner request | Scope and constraints | Size |
|---|---|---|---|---|
| UI-2a | Rename "Watchlist" to **"Buying"** | request 2 | **Completed and independently accepted after correction** at implementation `cbae8e6` plus review `3a29138`, together with UI-2c. User-facing navigation/copy says Buying; internal domain identifiers remain stable. | done |
| UI-2b | History **outcome filtering** | request 4 | **Completed and independently accepted 2026-08-04** at implementation `335c9fc` plus review hardening `9dcff80`. The exhaustive mapping lives beside `STATUSES`, unknown statuses fail-safe to Other/unknown, legacy `executed` stays unresolved, and the read-only SQL query applies filtering before the row limit. Outcome multi-select is primary, exact status is Advanced, and intersections are stated. Review found no runtime defect and added a reverse-mutation-proven large-history UI regression. | done |
| UI-2c | **Left-side navigation** replacing the top tab bar | request 1 | **Completed and independently accepted after correction** at implementation `cbae8e6` plus review `3a29138`. All 8 surfaces route from the sidebar with policy context separate. Review corrected one missed render-control effect: benign page inputs now survive navigation through an explicit whitelist, while approval/override/bulk-submit/cancel/emergency confirmations deliberately do not. | done |
| UI-2d | History **entry removal, persisted** | request 3 | **Completed and independently accepted after correction 2026-08-04** at implementation `6d287f0`, documentation `1ff8063`, merge `8f2e9a7`, and review correction `a118470`. Dismiss/archive only, never deletion: terminal `dismissed` status (canonical, non-inflight, outcome group Closed without fill), storage eligibility limited to pristine never-broker-touched `proposed`/`expired` rows, preview-hash-bound all-or-nothing atomic dismissal with idempotent replay, `list_proposals` visibility flags, preview-first CLI `dismiss-proposals`, and the History Manage-unused-proposals expander with default-off archive visibility. Review made execution telemetry disqualifying, made structurally malformed allocation-batch references fail closed, and bound the confirmation hash to the complete durable proposal state. Automatic expiry remains a separately approved follow-up; physical purge remains deferred and owner-authorized. | done |

UI-2b's frozen outcome groups are:

- **Awaiting decision:** `proposed`, `override_available`;
- **Processing:** `validating`, `approved`;
- **Broker working / unresolved:** `submitting`, `submission_unknown`,
  `reconciling`, `broker_accepted`, `partially_filled`, `cancel_pending`, and
  legacy `executed` (which means accepted, not confirmed filled);
- **Filled:** `filled` only;
- **Refused / failed:** `blocked`, `validation_failed`, `submission_failed`,
  `broker_rejected`;
- **Closed without fill:** `canceled`, `broker_expired`, `expired`, and
  `dismissed`; and
- **Other / unknown:** any future value absent from the frozen mapping.

The implementation must define this map beside the canonical status constants
and test `set(mapping) == set(STATUSES)`; the UI imports it rather than
reconstructing financial lifecycle meaning.

Sequencing: **UI-2a + UI-2c completed and reviewed** as one navigation
milestone; **UI-2b completed and independently reviewed 2026-08-04**;
**UI-3 (Backtest page) completed and independently reviewed 2026-08-04**;
**UI-2d completed and independently accepted after correction 2026-08-04**.
Automatic
expiry, if still desired, follows as
a separately approved lifecycle milestone; physical purge stays deferred.
UI-2d changes runtime durable state even though it grants no execution
authority. If a formal evidence epoch has started under model 1
(frozen runtime) before this work merges, deployment of these changes to the
operational machine waits for the epoch boundary; under model 2 they proceed
on the development side immediately.

Then: proposal-history physical purge remains deferred as before.

**GR-7 — product completeness, split into sub-milestones (2026-08-05):**

The archived plan (`docs/reference/GENERAL_READINESS_IMPLEMENTATION_PLAN.md`
§12) lists five items ordered by value-per-risk. That is several branches of
work, so it is split here; the archived plan remains authoritative for each
item's definition of done.

| # | Item | State |
|---|---|---|
| GR-7a | **Annual tax reporting export** — realized gains by lot, short/long-term split, wash-sale flags, accountant-readable CSV/JSON, coverage honesty | **COMPLETE AFTER INDEPENDENT REVIEW 2026-08-05.** Pure reporting layer over `assistant/tax_lots.py`; only live `source="alpaca"` snapshots may verify coverage; sample/manual portfolios stay unverified. |
| GR-7b | **Idle-cash / mandate reporting** — cash position measured against the approved mandate | **COMPLETE AFTER INDEPENDENT REVIEW 2026-08-06.** Pure `assistant/cash_reporting.py`; CLI `idle-cash` and Reports panel use Alpaca/sample snapshots only (no provider-fetch writes); mandate bridge is descriptive required invested volatility; refuses unusable measured vol. |
| GR-7c | **Performance attribution** — decompose return into allocation/selection/timing/cost/tax rather than the aggregate `performance.py` already reports | **COMPLETE AFTER INDEPENDENT REVIEW 2026-08-06; follow-ups reviewed after correction 2026-08-07.** `assistant/attribution.py` + CLI `attribution`. Single SPY bucket; sector allocation undefined without mandate weights; selection is a labelled residual; cost/tax already-inside, never re-deducted; session-based sufficiency; session-equalized BoP weight; post-flow snapshot equity mapped correctly into TWR. |
| GR-7d | **Rebalance-to-target proposals** (+ the `docs/reference/ALLOCATION_SERVICE_DESIGN.md` fold-in) | **SUPERSEDED; ADOPTED THREE-SLEEVE REPLACEMENT COMPLETE THROUGH M3 AFTER INDEPENDENT CORRECTION AND DEPLOYED 2026-08-13 IN EPOCH-005 AT `752d3b7`.** M1 plus revision 2 are complete after review at merged `02484bb`; M2 durable batched notifications are complete at implementation `8f5acb7` / validation `5ff39ed` plus correction `c314245`. M3 dividend-funded, APPROVE-gated proposals and exact earmark accounting are accepted at Claude implementation `7ee4786` plus Codex correction `b6685b5`; review closed 2 P1 and 4 P2 findings involving fill evidence, the authoritative journal-backed pool fence, corrupt/future earmark state, and JSON output. Optional M4 prepared trims remain deferred and unauthorized. See `docs/Review/REVIEW_2026-08-13_THREE_SLEEVE_M3.md`. |

**Why GR-7d is blocked.** The archived plan says "the mandate already
defines targets; propose the deterministic trades that restore them." It
does not. The approved mandate defines *risk-shape* targets (volatility
band, max drawdown, time-under-water, capture ratios) and the policy
defines *caps* (`max_position_pct` 5%, `max_total_exposure_pct` 50%,
`min_cash_reserve_pct` 10%, `max_leveraged_etf_pct` 20%). Neither is a
target **allocation**, and a cap is not a target: today's engine already
proposes sells to cure a cap breach, which is the only deterministic
"restore" that exists. Generating rebalance proposals therefore requires
the owner to first define what the target portfolio *is* (explicit target
weights, or a rule that derives them). Inventing one would be inventing an
investment policy and asserting an allocation claim this project has no
evidence for — exactly what `CLAUDE.md` §1/§6 forbid. The allocation
design's own §6 flags the same gap (candidate universe, sizing shape, and
sell-leg support are all listed as unresolved decisions). **Owner decision
required before GR-7d can start; it is not an engineering blocker.**

**Resolution (2026-08-09).** The owner made the decision this section asked
for, in a different shape than the archived plan anticipated: rather than
defining target weights, the owner adopted a three-sleeve engine
(dividend-income floor, per-lot growth gain/decline review thresholds with a
mandatory tax-consequence mechanism, dividend-to-leveraged reinvestment).
That preference is recorded verbatim in
`docs/reference/THREE_SLEEVE_ENGINE_PLAN.md`, which now governs this
workstream. The engine is explicitly an owner preference, not validated
research, and every milestone of it stays notification- or APPROVE-gated.
M1 is complete after independent review and merged at `02484bb`. M2 durable
batched notifications are complete after independent review at `8f5acb7` /
`5ff39ed` plus `c314245`. M3 dividend-earmark accounting and APPROVE-gated
reinvestment proposals are complete after independent correction at
implementation `7ee4786` plus correction `b6685b5`. Integration and deployment
were owner-authorized and completed in the 2026-08-13 epoch-005 roll at
`752d3b7`. Optional M4 prepared trims remain deferred and require a separate
owner authorization.

**UI-3 — interactive Backtest page (owner-requested 2026-08-04, inserted
into this phase ahead of UI-2d at the owner's direction):**

The owner asked to set up signals and run backtests directly in the UI,
with a graphic showing the result. This is a **read-only research
surface** — the plan below was written before implementation and is the
milestone's contract:

1. **Scope.** One new sidebar page, "Backtest", that (a) selects one of
   the existing price-only `scan_fn` signals from `signals/` (dip/up
   z-score, momentum, relative dip/up, 52-week breakout, 52-week-high
   proximity, vol-scaled momentum — PEAD/fundamentals are excluded in v1
   because they need an earnings feed, and residual momentum/reversal and
   idio vol because they refuse to run without a precomputed residual or
   benchmark feed), (b) exposes that signal's own parameters as widgets
   from a
   frozen inventory, (c) chooses data source, universe scope (whole
   universe or one basket), lookback, and hold horizons, (d) runs the
   walk-forward engine on demand, and (e) renders a multi-horizon summary
   table plus a cumulative-net-return chart per signal direction.
2. **Composition, not reimplementation.** The page calls the SAME
   `backtest/engine.py` functions the CLI scripts call
   (`run_multi_horizon_backtest`, `summarize_multi_horizon`) through a
   thin pure module (`backtest/interactive.py`) holding the frozen signal
   inventory, strict parameter validation (unknown signal or parameter
   fails closed), and chart-frame builders. No backtest math lives in the
   Streamlit script.
3. **Research honesty is part of the definition of done.** Synthetic data
   is the default source and every synthetic result is labeled as a
   plumbing check whose expected win rate is ~50%. Real-data results are
   labeled exploratory: not point-in-time, no multiplicity correction, and
   an on-page statement that confirmatory significance runs only in the
   frozen CLI pipeline (`run_significance_check.py` /
   `run_out_of_sample_check.py`). The page must not compute or display a
   pooled significance number.
4. **Runtime behavior.** Runs execute only on an explicit button click;
   results persist in session state so navigation and widget interaction
   do not re-trigger computation; real-data fetches are cached with a TTL;
   entry timing is the executable `next_open` default and is displayed,
   not chosen.
5. **Boundary.** The page has no path to proposals, approvals, orders,
   policy, or the research registry: no action-shaped controls, no
   registry writes, no execution imports from `backtest/interactive.py`
   (structurally tested). A good-looking chart must lead nowhere.
6. **Tests.** Inventory/validation/chart-frame unit tests; an AppTest
   proving the page renders, a synthetic run completes end to end on a
   small basket/lookback, and the exploratory labeling is present; the
   reachability suite gains the page; the import-boundary suite still
   passes.

Size: medium. Read-only; no persistence schema, lifecycle, or authority
change. UI-2d follows after this milestone's review unless the owner
reorders again.

Status: **completed and independently accepted after correction on
2026-08-04** at implementation `198339d`, documentation `d664402`, and
review correction `540467e`. The submitted architecture and authority
boundary were sound, but review corrected two P2 research-correctness gaps:
empty/partial provider data and impossible signal/history combinations can
no longer look like a fully covered zero-signal run, and the composition
helper no longer truncates fractional integer parameters or accepts invalid
horizons/slippage. Actual coverage, horizons, entry timing, and slippage are
stored with the session result; partial real-data coverage is disclosed.
Review also strengthened exact-frame UI/engine equivalence, real-data caveat
coverage, and the transitive research/authority import boundary. Corrected
validation passed 88 focused tests and 2,613 full-suite tests with 1 skipped
and 25 known warnings; compileall and diff checks were clean. No result was
promoted and no proposal, policy, registry, broker, schema, scheduler, epoch,
ML/LLM, or execution-authority behavior changed.

Sequencing after UI Phase 2: UI-2d is complete after independent correction.
Automatic expiry remains a separately approved optional milestone and physical
purge remains deferred. Phase 5 operational deployment and epoch start are
closed again: the AP-6 epoch swap was owner-authorized and executed
2026-08-10. The four original owner decisions were made on 2026-08-04 and the
mandate approval and its independent review are merged. The operational-only
verifier scope also merged in PR #148. Future epoch actions, deployments, and
task changes still require explicit owner direction each time.

**Phase 7 — data purchases, whenever decided (independent of code):**
membership vendor decision → Databento statistics/reference captures →
universe/cutoffs artifacts → real authoritative build → real ML discovery/
confirmation under the review-gated campaign.

**Deliberately queued indefinitely:** AI strategy authoring (its own plan
sequences it after ML-LR and GR complete), AI debate (open value question),
MCP (fails its own activation gate), GR-8 (requires everything above plus
explicit authorization).

---

## 9. Owner decisions required (consolidated, deduplicated)

1. ~~GR-1D go-ahead/review~~ — **RESOLVED 2026-08-03: granted,
   implemented, merged as PR #120, and independently accepted at `2f37210`.**
   ~~Still open from this item: epoch model 1 vs 2 (§7).~~ — **RESOLVED
   2026-08-04: model 2 (pinned operational checkout).** The operational
   clone lives at `C:\git\trading_agent_operational` (pinned to the frozen
   epoch commit at epoch start); the machine-local launcher
   `C:\git\launch_trading_app.ps1` starts the app from it with
   `TRADING_ASSISTANT_DB` pointed at the single operator database.
2. ~~Approve the mandate (or first revise its DRAFT §2 targets)~~ —
   **RESOLVED 2026-08-04: owner approved with targets unchanged** after a
   plain-language walkthrough. `assistant/default_mandate.json` is status
   `approved`, fingerprint-bound; `docs/operations/MANDATE.md` §2 and change control
   updated. `allow_autonomous_execution` remains false.
3. ~~GR-5 alert delivery channel~~ — **RESOLVED 2026-08-03:** immediate
   critical alerts use Windows desktop toasts; warnings batch into the daily
   briefing. Webhooks remain out of scope.
4. ~~Task-account choice~~ — **RESOLVED 2026-08-04: scheduled tasks run
   under the owner's own account** (single-owner paper machine; no dedicated
   task account or account-creation elevation). Scheduler registration still
   requires its owner-led elevated window and successful preview/verification;
   that is an operational step, not an unresolved design decision.
5. ~~Operator DB path~~ — **RESOLVED 2026-08-04: keep
   `data/trading_assistant.db`** as the single record; every checkout
   (including the operational clone) reaches it via `TRADING_ASSISTANT_DB`.
6. Historical-membership vendor selection and funding (not Databento).
7. Databento statistics/reference budget + ticker/session range;
   Reference-API subscription confirmation.
8. Who writes/reviews the vintage-correct adjustment builder; who signs the
   `SpecReviewAttestation` for the volatility discovery spec.
9. Handling of the 118 mixed-provenance equity snapshots (AP-3).
10. ~~Whether UI feature controls jump ahead~~ — **RESOLVED 2026-08-02: yes,
    UI controls are Phase 1** (owner priority change to support daily paper
    trading from 2026-08-03).
11. ~~UI design's four open decisions~~ — **RESOLVED 2026-08-02** with the
    defaults both audits recommended: (a) session-state preferences first,
    durable persistence only if re-toggling proves annoying; (b) policy
    edits write the sidebar-selected policy file through the full protected
    workflow (no new policy-record store yet); (c) existing Briefing/
    Watchlist suggestion surfaces remain alongside the dedicated tab;
    (d) the master AI preference is a hard gate ANDed with per-feature
    toggles.
12. Whether strategy-tool commit `a656015` can be retrieved — **OPEN again
    after independent verification 2026-08-03:** neither the commit nor its
    former local branch resolves in this checkout or the fetched refs. Treat
    that work as unavailable unless another machine or backup still has it;
    do not plan against it as preserved implementation.
13. Whether AI debate is worth building at all (its own doc doubts it).
14. ~~`.gitignore` extension for ML artifact paths (AP-2)~~ — **RESOLVED
    2026-08-03:** `artifacts/` is ignored wholesale and regression-tested.

---

## 10. What this plan deliberately does not do

It does not restate every sub-check of every milestone (the per-milestone
plans, archived in `docs/reference/`, remain authoritative for their
internals); it does not adjudicate GR-1's "thin composition layer" DoD
(that is GR-1E's question); it does not propose starting any
authorization-gated work; and it does not treat any synthetic/fixture
result as market evidence anywhere. This adopted plan replaces the need to
juggle individual plan docs for day-to-day sequencing, while leaving those
docs as the detailed specs they are. Keep it current: when a phase
completes or the owner reorders priorities, update THIS file (and
`docs/SESSION_HANDOFF.md`) rather than resurrecting per-plan sequencing.
