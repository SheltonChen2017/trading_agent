# Four-strategy research program

Status: **ACTIVE ZERO-ACCESS CONTRACT/SAFETY IMPLEMENTATION, NOT RESEARCH
ACCEPTANCE.** Every lane is building and reviewing frozen contracts, fixtures,
and fail-closed loaders under the same-branch Claude review plus Codex
counter-review loop. No lane has an authenticated production signal, a
real-outcome result, a spent research look, a QuantConnect job, a deployment,
or paper/live trading authority. The lane record is the only authoritative
statement of a lane's current milestone; the table below is a directory index
and deliberately does not repeat milestone identifiers that change every round.

The owner supplied three strategy blueprints on 2026-08-25 and a fourth,
separately governed Target-Price Revisions blueprint on 2026-08-29. They
replace the former single-strategy ACER V1 planning surface:

| Strategy lane | Current state (2026-09-04) | Governing source | Active implementation record | Long-lived branch |
|---|---|---|---|---|
| Analyst revisions V2 | Zero-access contract/safety candidates under same-branch review; no signal, outcome, or look authority | `ANALYST_REVISIONS_ETF_STRATEGY_BLUEPRINT_V2_EN.pdf` | `ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md` | `codex/strategy-analyst-revisions-v2` |
| Insider buying | Zero-access source-inventory and contract milestones (IB ladder) under same-branch review; no provider, outcome, or look authority | `INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf` | `INSIDER_BUYING_IMPLEMENTATION_RECORD.md` | `codex/strategy-insider-buying` |
| Short interest | Zero-access inventory and contract milestones (SI ladder) under same-branch review; no provider, outcome, or look authority | `SHORT_INTEREST_ETF_STRATEGY_BLUEPRINT_EN.pdf` | `SHORT_INTEREST_IMPLEMENTATION_RECORD.md` | `codex/strategy-short-interest` |
| Target-price revisions | Zero-access preregistration/trust-root milestones (TPR ladder) under same-branch review; fourth shared-family slot fixed at `1/80`; no source, outcome, or look authority | `TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf` | `TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md` | `codex/strategy-target-price-revisions` |

Each lane is developed in its own checkout (a sibling clone or `git worktree`,
resolved with `git worktree list` rather than a pinned path) so that lane
sessions never share a working tree.

Read `THREE_STRATEGY_PARALLEL_WORKFLOW.md` before changing any lane. It is the
binding coordination contract for Codex and Claude while these branches are
developed in parallel; its frozen-file rule and the recorded owner-directed
exceptions apply to all four lanes. `THREE_STRATEGY_DATA_SOURCE_REGISTER.md`
records what the assumed Massive-Benzinga Analyst Ratings and QuantConnect
subscriptions do and do not establish. The shared four-family selection
accounting and the common final-holdout boundary are frozen in
`../THREE_STRATEGY_PROJECT_DIRECTION.md`.

The three 2026-08-25 PDFs are immutable owner inputs. If a PDF and its
Markdown record differ, the PDF governs unless the owner has made an explicit
amendment that is quoted in the record. Ambiguity is a stop condition, not
permission to improvise. The Target-Price Revisions blueprint was authored by
an agent under owner direction and is pinned by digest in its lane record; the
"PDF governs" rule protects owner intent, not an agent-authored PDF from
owner-approved correction recorded in that lane.

Issues found during lane reviews that concern the shared trading application,
test infrastructure, or repository tooling rather than a strategy are
documented in the lane record and deliberately not fixed on the lane. The
owner-directed cross-lane integration of those items on 2026-09-04 is recorded
in `../Archive/Review/BUG_FIX_INTEGRATION_2026-09-04.md`.

The former ACER V1 plan, source PDF, partial freeze, proposals, and data audits
are preserved under `docs/Archive/Plans/`, `docs/Archive/Reference/`, and
`docs/Archive/Research/ACER_V1/`. They are historical evidence only. The
existing `research/acer/` event-normalization code remains reusable plumbing;
its existence does not make any V2 signal or test complete.

Software safety primitives, synthetic/fixture validation, and review acceptance
are separate from evidence of market edge. None of these lane records grants
provider access, outcome access, deployment, portfolio execution, order
authority, or autonomous trading authority.
