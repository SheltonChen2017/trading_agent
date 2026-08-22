# PROJECT SEPARATION IMPLEMENTATION PLAN

Status: **ACTIVE — SEP-2 entry-point, dependency, and data-ownership classification**

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

### SEP-1 — shared contracts and read-only research adapter (reviewed)

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

#### SEP-1 implementation state (Codex, 2026-08-21)

Commit `18868d3` completes the first coherent extraction tranche without
claiming the whole milestone complete:

- broker/manual portfolio snapshot construction now lives in
  `assistant.portfolio_snapshot`; `assistant.allocation_batch` imports that
  narrow module rather than the research-aware context builder;
- the only execution-authority-to-research path is removed, so
  `allowed_authority_research_paths` is empty;
- exact decimal helpers and `EvidenceStatus` now live in the temporary shared
  kernel, with identity-preserving compatibility facades at
  `assistant.money` and `assistant.schemas`;
- four neutral ML-to-assistant edges leave the debt ledger, reducing the
  direct cross-product count from **13 to 9**; and
- new guards reject a shared-kernel dependency back into either product,
  facade identity drift, and restoration of the allocation-to-context path.

Commit `7f8c47f` updates the repository-wide raw-decimal guard to recognize
`data.financial_primitives` as the canonical implementation while continuing
to accept the `assistant.money` facade. Its focused guard/precision/boundary
suite passes 16 tests.

Mutation checks proved both dangerous directions: restoring the old
allocation import produced the exact former transitive violation and failed
two guards; adding a shared-module import of `assistant.schemas` failed the
new shared-kernel direction guard. Existing import paths remain supported.

Independently reviewed 2026-08-21 (accepted after correction): handoff
section 7df and `docs/Archive/Review/REVIEW_2026-08-21_SEP1_EXTRACTION_TRANCHE.md`.
The zero-authority-path claim and the behaviour-equivalence of the moved
functions were both reproduced independently. Two P2 corrections landed:
the `EvidenceStatus` definitions deleted during the move were restored,
and the milestone-state guard was rewritten as a relationship after it
had to be edited twice in one session.

Commit `636d164` is the second coherent extraction tranche. It removes five
more direct product crossings without changing the old public import paths:

- volatility measurement and regime classification now live in neutral
  `market_analytics`, with `signals.regime` retaining identity-preserving
  compatibility exports;
- portfolio risk metrics, mandate evaluation, and research multiplicity
  arithmetic now live in product-neutral `data` modules;
- existing assistant/backtest facades resolve to the same function and error
  objects, so callers do not acquire duplicate runtime types or lose existing
  exception-catching behavior; the moved exception's module/name metadata is
  not claimed to be byte-for-byte serialization-compatible with the old class;
- assistant context, stock lookup, paper evidence, and look accounting use the
  neutral implementations directly; and
- the exact direct-crossing ledger falls from **9 to 4**, while the
  execution-authority exception count remains zero.

The focused affected-module suite passes 200 tests. Boundary tests pin facade
identity and reject restoration of a migrated product crossing. This tranche
does not call a provider, broker, backtest, outcome, operator database, task,
deployment, or evidence epoch.

The second tranche was independently reviewed
2026-08-22 (accepted after correction; one P3 — restored rationales — see
`docs/Archive/Review/REVIEW_2026-08-22_SEP1_CONTRACTS_TRANCHE.md` and
handoff section 7di).

Commit `a8c2b77` completes the implementation side of SEP-1's third tranche:

- immutable, provider-neutral result contracts live in
  `data.research_results`; they contain measurements and input bindings, not
  proposal, approval, broker, database, or execution authority;
- research-owned builders in `research.assistant_results` retain the scanner,
  regime, and strategy calculations;
- assistant explanation and proposal modules consume the typed results and
  fail closed when a result is absent or names the wrong ticker, and proposal
  sizing additionally refuses a mismatched date, parameter digest, or exact
  close-history digest;
- `scripts.product_composition` is the temporary mixed-root entry-point seam
  that builds and supplies those results while `scripts/` awaits SEP-2
  classification; neither product imports that seam or the other product;
- production UI/CLI entry points use the seam without changing paper-trading,
  approval, policy, proposal, or broker authority; and
- the exact direct-crossing ledger falls from **4 to 0**, with zero
  execution-authority exceptions. Permanent guards require both counts to
  remain zero and reject either product importing the temporary seam.

Independently reviewed 2026-08-22 (accepted after correction; two P3 — an
untested over-cap refusal now regression-pinned, and a dated source
verification added to the licence correction — see
`docs/Archive/Review/REVIEW_2026-08-22_SEP1_ADAPTER_TRANCHE.md` and
handoff section 7dl). The zero-edge and zero-authority-path claims were
reproduced with an independent scanner.

Codex counter-reviewed Claude's exact review head `6f8228f` on 2026-08-22
(accepted after correction; one P3 direct-run-harness truth defect corrected
at `00d5abe`; see
`docs/Archive/Review/COUNTER_REVIEW_2026-08-22_SEP1_ADAPTER_TRANCHE.md`).
The review chain is closed and SEP-1 meets its definition of done. The
feature-milestone record now carries the completed milestone. `scripts/`
classification remains SEP-2 work.

### SEP-2 — entry points, dependencies, and data ownership (current)

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
