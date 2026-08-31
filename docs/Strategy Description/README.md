# Three-strategy research program

Status: **ACTIVE SAFETY IMPLEMENTATION, NOT RESEARCH ACCEPTANCE.** The Analyst
Revisions V2 contract/safety candidate is assembled but remains unaccepted
pending Claude's review of the exact pushed snapshot and Codex's counter-review
of Claude's exact reviewed push. Insider Buying and Short Interest remain at
their planning/baseline stage. No lane has an authenticated production signal,
real-outcome result, deployment, or paper/live trading authority.

The owner supplied three strategy blueprints on 2026-08-25. They replace the
former single-strategy ACER V1 planning surface:

| Strategy lane | Current state | Governing source | Active implementation record | Long-lived branch |
|---|---|---|---|---|
| Analyst revisions V2 | Strict contract/safety primitives assembled; production normalization, signal/score, cross-section, nonempty portfolio, outcome, and QC boundaries remain zero-access; candidate unaccepted | `ANALYST_REVISIONS_ETF_STRATEGY_BLUEPRINT_V2_EN.pdf` | `ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md` | `codex/strategy-analyst-revisions-v2` |
| Insider buying | Planning/baseline only | `INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf` | `INSIDER_BUYING_IMPLEMENTATION_RECORD.md` | `codex/strategy-insider-buying` |
| Short interest | Planning/baseline only | `SHORT_INTEREST_ETF_STRATEGY_BLUEPRINT_EN.pdf` | `SHORT_INTEREST_IMPLEMENTATION_RECORD.md` | `codex/strategy-short-interest` |

Read `THREE_STRATEGY_PARALLEL_WORKFLOW.md` before changing any lane. It is the
binding coordination contract for Codex and Claude while these branches are
developed in parallel. `THREE_STRATEGY_DATA_SOURCE_REGISTER.md` records what
the assumed Massive-Benzinga Analyst Ratings and QuantConnect subscriptions do
and do not establish.

The PDFs are immutable owner inputs. If a PDF and its Markdown record differ,
the PDF governs unless the owner has made an explicit amendment that is quoted
in the record. Ambiguity is a stop condition, not permission to improvise.

The former ACER V1 plan, source PDF, partial freeze, proposals, and data audits
are preserved under `docs/Archive/Plans/`, `docs/Archive/Reference/`, and
`docs/Archive/Research/ACER_V1/`. They are historical evidence only. The
existing `research/acer/` event-normalization code remains reusable plumbing;
its existence does not make any V2 signal or test complete.

Software safety primitives, synthetic/fixture validation, and review acceptance
are separate from evidence of market edge. None of these lane records grants
provider access, outcome access, deployment, portfolio execution, order
authority, or autonomous trading authority.
