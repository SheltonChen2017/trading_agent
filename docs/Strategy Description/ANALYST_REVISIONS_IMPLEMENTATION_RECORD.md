# Analyst Revisions ETF Strategy V2 — implementation and session record

Status: **PLANNED; NO V2 SIGNAL, OUTCOME TEST, ETF PORTFOLIO, OR QC ALGORITHM
HAS BEEN IMPLEMENTED.**

Branch: `codex/strategy-analyst-revisions-v2`

Governing owner source:
`ANALYST_REVISIONS_ETF_STRATEGY_BLUEPRINT_V2_EN.pdf`, 64 pages, 271,570
bytes, SHA-256
`eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193`.
The PDF identifies itself as v2.0 dated 2026-08-22 and replaces the former
analyst-consensus plan.

Codex is the primary implementer. Claude is the independent reviewer. Both
agents work serially on the same branch and follow
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`. During parallel development neither
agent may edit `docs/ACTION_PLAN_2026-08-20.md` or
`docs/SESSION_HANDOFF.md`; this record is the lane's status and handoff.

## 1. Canonical strategy contract

The first executable family is the PDF's rating-only V2, not a free-form
blend:

- identify genuine upgrades and downgrades using each firm's own ordered
  rating vocabulary normalized to `[-1, +1]`;
- deduplicate to institution-stock-day, use a 20-trading-day half-life, sum
  decayed events, robustly z-score within sector, and shrink by
  `N_eff / (N_eff + 3)` times measured data quality;
- discover candidate ETFs from signaled stocks, then aggregate stock scores
  using point-in-time holdings and coverage normalization;
- apply ETF reliability
  `sqrt(coverage) * min(1, sqrt(N_eff / 5))` and rank ETFs relative to peers;
- treat novelty, price-target revisions, EPS revisions, breadth, and analyst
  quality as separate diagnostics or preregistered extensions. They must not
  be silently multiplied into the canonical rating score;
- trade no earlier than the next open after public availability; a date-only
  event receives the PDF's conservative one-day delay;
- use hysteresis (enter rank 90, exit rank 70), hold at most five ETFs, cap an
  ETF at 20%, sector exposure at 40%, overlap clusters at 30%, and leave cash
  residuals when necessary; and
- use no leverage in the canonical program. Leveraged or inverse overlays are
  outside V2 until the unlevered research and risk gates pass.

Every row must retain event time, effective time, available time, ingestion
time, source identity, immutable version, and revision lineage. Current-ticker
joins are prohibited. ETF candidate weight mapping must reach at least 99% or
fail closed.

## 2. Current ACER foundation versus V2

The old ACER V1 documents are archived. The existing code and datasets are
not discarded; they are assessed below as infrastructure, not as V2
completion.

| Area | Current repository state | V2 requirement / gap | Disposition |
|---|---|---|---|
| Vendor capture | Immutable Massive-Benzinga snapshot validation exists. | Re-verify current entitlement, complete pagination, amendment/deletion behavior, and transfer rights for QC. | Reuse after audit. |
| Event normalization | `research/acer/` produces a canonical event table with named refusals. Reviewed snapshot: 587,046 raw rows, 584,916 accepted events, 2,130 refusals (99.64% retained), roughly Dec-2011 through Aug-2026. | Add V2 institution-stock-day dedupe, event taxonomy, corrected/withdrawn-event lineage, and explicit availability rules. | Extend; do not rewrite raw history. |
| Time semantics | Date-level conservative availability exists. | V2 needs trustworthy `effective_time` and `available_time`, next-open cohorting, and explicit date-only delay. Intraday history may be incomplete. | Blocking audit. |
| Firm identity | Firm name and Benzinga firm/analyst identifiers are present in source rows. | Build durable firm identity and a firm-specific ordered-rating ontology; reject ambiguous vocabularies. | Not implemented. |
| Rating scale | No production rating scale exists. Old V1 proposed a global five-level map but it was never adopted. | V2 requires firm-specific normalized ordered scales in `[-1,+1]`. | Replace proposal; implement only after tests. |
| Signal formula | No production ACER signal exists. Old V1 proposed two encodings, 21/63/126 half-lives, coverage-neutral means, and a six-cell family. | Canonical V2 is genuine changes, 20-session half-life, decayed event sum, sector robust z-score, reliability shrinkage. | Entirely new work. |
| Consensus/novelty | No historical active-rating state engine. | Reconstruct contributor-excluded consensus with 90/180/365-day rating expiry; keep novelty diagnostic separate. | Not implemented. |
| Targets/EPS | Raw current/previous targets exist; no vetted target signal. No analyst EPS-revision history is established. | Targets and EPS are diagnostic/extension channels and need their own PIT availability, units, splits/currency, and multiplicity budget. | Deferred from canonical. |
| Issuer identity | A name/ticker diagnostic found 768 deterministic interleavings; it is explicitly a lower bound, not an allowlist. | Durable PIT security master across ticker reuse, share classes, mergers, delistings, and corporate actions. | Blocking. |
| Sector model | SIC may be locally available; no accepted PIT V2 sector taxonomy. | Robust sector standardization with a frozen, point-in-time taxonomy and sparse-sector fallback. | Not implemented. |
| Prices/outcomes | No event has been joined to price or return. The EDGAR/yfinance path lacks decision-grade delisting/terminal returns; Databento remains unmeasured. | Split/dividend-adjusted PIT total returns including delistings, next-open execution, 20-day primary horizon, and 0/5/10/20 bps cost grid. | Blocking; no look consumed. |
| ETF topology | ACER V1 deliberately deferred ETF contract; no reverse constituent index or ETF score exists. | Stock-first discovery, PIT holdings, >=99% mapped candidate weight, ETF eligibility, coverage normalization, reliability, peer ranking. | Not implemented. |
| Portfolio/QC | No ACER portfolio or QC algorithm exists. | Hysteresis, caps, overlap clusters, cash, scheduling, custom immutable signal ingest, and execution tests. | Not implemented. |
| Research design | Legacy residualized-IC/bootstrap utilities exist; old preregistration remained incomplete. | Re-preregister V2 rounds 0-8, stock/industry/ETF topology comparison, 5y/2y/1y walk-forward, 20-day primary horizon, multiplicity and permanent look ledger. | New freeze required before outcomes. |

No real-outcome research look has been performed for V2. The migration of the
existing event dataset into a V2 schema is the first bounded engineering task;
it must preserve the immutable original rather than mutating it in place.

## 3. Milestone ladder

| Milestone | Scope | Exit gate |
|---|---|---|
| ARV2-0 | Freeze schemas, ontology rules, event availability, identifiers, data quality, test family, cost model, and look budget. | Every ambiguous choice is fixed; no outcome code can run. |
| ARV2-1 | Audit/extend immutable ratings ingest and build firm-rating ontology with fail-closed refusals. | Synthetic and sampled structural tests; exact lineage and dedupe invariants. |
| ARV2-2 | Build PIT issuer/security master and event-to-security mapping. | Ticker reuse/share-class/delisting mutations fail; coverage and ambiguity reported. |
| ARV2-3 | Implement canonical stock score and separate diagnostic channels. | Golden equations, sparse-sector behavior, no outcome imports, no leakage. |
| ARV2-4 | Build PIT ETF reverse index, eligibility, mapping, and ETF aggregation. | >=99% mapped candidate weight; stale/dynamic/transitive bypasses fail. |
| ARV2-5 | Register and run stock-first structural/event study under the frozen budget. | Permanent look logged; topology decision made without final holdout. |
| ARV2-6 | Walk-forward ETF research with fixed costs and baselines. | OOS gate, robustness, capacity, turnover, overlap, and null handling. |
| ARV2-7 | Implement QC algorithm using immutable custom/precomputed signals. | Deterministic parity, scheduling, sizing, cash/cap/failure tests; still research-only. |
| ARV2-8 | Independent final holdout and promotion dossier. | Explicit owner decision required for any paper deployment. |

## 4. First implementation scope

The first Codex implementation session should implement **tests and schema
only for ARV2-0/ARV2-1**:

1. pin the V2 raw/canonical fields and availability ordering;
2. prove institution-stock-day deduplication and corrected-event lineage;
3. build a versioned, data-derived firm-rating vocabulary inventory without
   assigning outcome-informed scores;
4. add dangerous-direction tests for global-map fallback, current-ticker
   joins, date-only same-day trading, and silent unknown-rating coercion; and
5. update this record before the first push.

Do not add a price join, calculate forward returns, tune a rating order from
returns, construct ETFs, or launch QuantConnect in this milestone.

## 5. Session / push ledger

Append one row before every push. Never rewrite earlier rows.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Next |
|---|---|---|---|---|---|---|---|
| 2026-08-25 | Codex planning | `6156ef9` -> this shared baseline | Documentation only | V2 source reviewed; legacy/current gap measured; no implementation. | PDF text and all 64 rendered pages inspected; no outcome access; 0 looks. | V2 is a replacement, not a parameter patch. | Claude reviews the documentation baseline; implementation waits for owner instruction. |
