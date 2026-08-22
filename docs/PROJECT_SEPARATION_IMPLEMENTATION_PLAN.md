# PROJECT SEPARATION IMPLEMENTATION PLAN

Status: **ACTIVE — SEP-1 shared contracts and read-only research adapter**

Owner direction: 2026-08-21

Implementer: Codex

Independent reviewer: Claude

## 1. Plain-language objective

The repository currently contains two products that grew together:

1. a **trading assistant** that helps the owner understand a portfolio,
   prepares tightly controlled proposals, requires explicit approval, talks to
   Alpaca paper trading, and keeps the operational record; and
2. a **strategy-research workbench** that defines hypotheses, prepares
   point-in-time data, runs backtests and statistical checks, and records
   whether ideas such as ACER have evidence.

They should become independently maintainable. A research experiment must not
be able to acquire order authority merely because it lives beside the trading
assistant, and operating the assistant should not require importing the whole
research stack. Separation must preserve history, tests, provenance, safety
gates, and the still-running paper evidence epoch.

## 2. Target boundary

| Product | Initial owned code | Does not own |
|---|---|---|
| Trading assistant | `assistant/`, `execution/`, `risk/` | Backtests, research hypotheses, ML experiments, or strategy calculations |
| Strategy research | `research/`, `backtest/`, `ml/`, `signals/`, `strategies/`, `baskets.py` | Broker submission, approvals, reconciliation, or operational authority |
| Shared kernel (temporary) | `data/`, `config.py`, `market_analytics.py` | Product policy; this surface must shrink or be split as ownership becomes clear |
| Unclassified migration surface | `scripts/` | No whole-directory ownership is assumed; each entry point must be classified before extraction |

The machine-readable counterpart is
`architecture/project_boundaries.json`. Its listed cross-product imports are
an exact debt ledger, not a permanent allowlist. A new crossing fails tests.

## 3. Current coupling that must be removed

The scan at SEP-0 found finite, concrete crossings in both directions:

- assistant context, explanations, evidence, research-look accounting, stock
  lookup, and strategy proposal modules call `signals`, `strategies`, or
  `backtest` directly;
- backtest and ML modules import assistant mandate, schema, and money helpers;
- `scripts/` mixes UI/operations entry points with research runners.

The first extraction candidates are therefore neutral types and adapters:

1. evidence status and research-result schemas;
2. decimal/financial primitives that carry no assistant authority;
3. mandate evaluation inputs and outputs;
4. a read-only research-result adapter consumed by the assistant; and
5. separately classified assistant and research entry points.

No adapter may expose a broker, approval token, execution gate, mutable
operator database, or licensed raw dataset to research code.

## 4. Milestones

### SEP-0 — boundary baseline (reviewed)

- record product ownership and every existing cross-product direct import;
- fail on a new or silently removed ledger edge;
- pin the one discovered transitive execution-authority-to-research path and
  refuse any expansion; this is a violation to remove, not an approved API;
- update the action plan and session handoff;
- make no runtime behavior change and move no production file.

Definition of done: the focused boundary tests, active-document checks, full
suite, compilation, diff and secret checks pass; Claude independently reviews
the exact pushed snapshot.

### SEP-1 — shared contracts and read-only research adapter (current)

- first remove
  `assistant.allocation_batch -> assistant.context_builder -> signals.regime`
  by extracting the broker portfolio-snapshot boundary from the broad context
  builder;
- extract the neutral schemas and financial primitives identified in SEP-0;
- replace assistant-to-research calculation imports with typed, read-only
  research results;
- remove corresponding ledger edges rather than broadening exceptions;
- keep all proposal, approval, execution, and reconciliation authority solely
  in the trading assistant.

### SEP-2 — entry points, dependencies, and data ownership

- classify every `scripts/` entry point;
- give each product its own launch surface and dependency declaration;
- split shared data access into explicit interfaces and product-owned
  implementations;
- keep licensed datasets and immutable research snapshots on the research
  side, with only non-reconstructable approved outputs crossing the boundary.

### SEP-3 — physical extraction decision

After SEP-0 through SEP-2 are reviewed and green, produce a dry-run extraction
manifest with retained history and exact source commits. The owner then chooses
between two repositories and an explicit shared package, or a permanently
partitioned monorepo. No repository deletion, history rewrite, deployment,
credential move, scheduled-task change, or operator-database move is authorized
by this plan.

## 5. Safety and evidence invariants

- Trading remains paper-only, human-approved, and fail-closed.
- The active operational checkout and `paper-epoch-006` are untouched.
- Research results do not become trade authority.
- ACER remains outcome-unrun and subject to its own licence, entitlement,
  identity, point-in-time, and preregistration gates.
- Git history and archived evidence are preserved.
- A moved module is not complete until imports, tests, documents, provenance,
  and the reverse dependency direction are verified.

## 6. Explicit non-goals for SEP-0

SEP-0 does not create a second repository, move files, rename packages, change
the Streamlit UI, call a broker or vendor, run a backtest, consume a research
look, alter the operator database, deploy, or roll an evidence epoch.
