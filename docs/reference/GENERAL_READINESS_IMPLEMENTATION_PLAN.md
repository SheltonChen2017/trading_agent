# Path to a Complete Trading App — General Readiness Implementation Plan

Status: execution plan for the development sequence after the ML roadmap

Prepared: 2026-07-31

Companion documents:

- `docs/ML_LIVE_TRADING_READINESS_IMPLEMENTATION_PLAN.md` — the model/research track
- `docs/operations/LIVE_PROMOTION_CHECKLIST.md` — the evidence **gate** for live capital
- `docs/operations/OPERATIONS_RUNBOOK.md` — how to **operate** what already exists
- `docs/architecture/ARCHITECTURE_DEBT.md` — the structural debt this plan pays down
- `docs/operations/MANDATE.md` — the risk contract every milestone answers to

## 1. What this document is, and is not

The three companion docs above answer *may I go live?*, *how do I run it?*,
and *what is structurally wrong?*. None answers **what does this need to
become a complete application?** That is this document's job.

"Complete" here has a deliberately narrow, achievable definition. It does
**not** mean "profitable", and no milestone below promises alpha:

> A complete trading app is one the owner can depend on daily, whose
> failures are safe and **visible**, whose data is trustworthy or honestly
> marked untrustworthy, and whose one production capability — deterministic
> risk reduction — is reliable enough to run with bounded real capital.

### 1.1 The honest starting assessment

Engineering maturity substantially **exceeds** strategic maturity. That gap
is the central fact this plan is organized around.

Strong today, verified rather than assumed: fail-closed defaults throughout;
exact decimal money arithmetic; an immutable, hash-verified audit trail;
atomic writes with integrity checked on bytes before deserialization;
architectural boundaries enforced by AST tests rather than convention; CI on
two Python versions; roughly 2,000 tests across ~78K lines.

Weak today: no validated edge (zero confirmed signals, by the project's own
repeated finding); no real-money execution ever; failure paths that exist but
have never been exercised under stress; a single retroactively-adjusted data
provider; observability that records alerts but has never delivered one; a
bus factor of one; and Windows-only operational scheduling.

**No amount of further engineering closes the strategy gap.** This plan
therefore does not try. It closes the *dependability* gap, so that when
evidence eventually exists, the platform underneath it is trustworthy.

## 2. Non-negotiable boundaries

These hold for every milestone below and are not subject to a milestone's
own convenience:

- `config.PAPER_TRADING` stays `True` and the separate `I_UNDERSTAND`
  confirmation stays required. No milestone here flips either.
- Every order keeps its exact human approval phrase and its post-approval
  revalidation against a **fresh** broker snapshot.
- No milestone weakens a policy limit, exposure cap, execution gate, kill
  switch, reconciliation rule, or stale-order rule.
- No milestone may delay or block a risk-reducing sale.
- Missing, stale, or ambiguous data produces refusal, never a default.
- No research finding is written to `assistant/research_findings.json`
  automatically.
- Every schema change is additive and migration-tested against a database
  created by the previous version.
- `tests/test_ml_import_boundary.py` and the committee import guard stay
  green.

## 3. Milestone overview

| Milestone | Purpose | Implementable now? | Production behavior |
|---|---|---:|---|
| GR-0 | Readiness taxonomy and measurable definition of complete | Yes | None |
| GR-1 | Execution kernel structural split | Yes | Refactor only |
| GR-2 | Risk-check consolidation | Yes | Refactor only |
| GR-3 | Fault injection and adversarial operational drills | Yes | None |
| GR-4 | Data-layer resilience and honesty | Yes | Read-path only |
| GR-5 | Observability and operator alerting that actually delivers | Yes | Alerting only |
| GR-6 | Recovery, secrets, and portability | Yes | Operational only |
| GR-7 | Product completeness — the buy-side gap and reporting | Partly | New proposals, still approval-gated |
| GR-8 | Bounded live canary operations | Requires GR-1..GR-6 + owner action | Real capital, tightly capped |
| GR-9 | Explicitly deferred work | No | None |

Order rationale: GR-1 and GR-2 come first because every later milestone adds
code to the execution path, and adding to a structure already flagged as debt
compounds it. GR-3 comes before GR-4/GR-5 because there is no point improving
data and alerting if the failure paths they feed have never been proven to
work.

## 4. Delivery rules

Identical discipline to the ML plan, for the same reasons:

1. One milestone per branch, stop for review after each.
2. State exactly what is implemented and what is still missing.
3. List every schema and contract change.
4. Identify any behavior that can affect the live assistant.
5. Run focused tests, full tests, `compileall`, and `git diff --check`.
6. Do not call a milestone complete when only its primitives exist.
7. Prefer extending an existing module over adding a parallel one. This
   repository already carries three near-duplicate JSON-freezing helpers and
   several error-translation shims; that drift is a real cost.

## 5. GR-0 — readiness taxonomy

### 5.1 Purpose

"Complete" is currently a feeling. Make it a measurement, so progress is
arguable from evidence rather than from vibes.

### 5.2 Implementation

Add `assistant/platform_readiness.py` producing a typed, read-only report
across independent dimensions. Reuse `assistant/readiness.py`'s existing
`_check()` shape rather than inventing a second report format.

Dimensions, each scored independently and **never** averaged into a single
number (an average lets a strong dimension hide a fatal one):

```text
execution_integrity     -- reconciliation clean, no unresolved outcomes
data_integrity          -- freshness, provider health, adjustment honesty
operational_readiness   -- drills current, backups verified, alerts delivered
evidence_readiness      -- paper sessions, epoch lineage (delegates to existing code)
strategy_readiness      -- confirmed findings; currently and correctly zero
```

Each returns `ready | degraded | blocked` plus the specific failing checks.
`strategy_readiness` must report `blocked` while zero confirmed findings
exist — the platform being excellent does not make the strategy ready, and
the report must never let one imply the other.

### 5.3 Tests

- a failing dimension cannot be masked by passing dimensions;
- an unavailable check is `blocked`, never `ready`;
- `strategy_readiness` is `blocked` given the current registry;
- the report creates no proposal, order, or execution state;
- the report is JSON-serializable and hash-stable for fixed inputs.

### 5.4 Definition of done

`python scripts/run_personal_assistant.py platform-readiness` prints the five
dimensions with their failing checks, and the numbers match what the existing
evidence commands already report. No dimension is fabricated.

## 6. GR-1 — execution kernel structural split

### 6.1 Purpose

`docs/architecture/ARCHITECTURE_DEBT.md` item 1 has been deliberately deferred for months.
It is now the single highest-leverage engineering item, because
`assistant/execution_service.py` has accumulated claiming, expiry,
revalidation, submission, reconciliation coupling, and error mapping in one
module — and every subsequent milestone wants to add to it.

### 6.2 Implementation

Split along the seams the debt doc already identifies, preserving behavior
exactly:

```text
execution/kernel/claim.py        -- atomic proposal claiming and expiry
execution/kernel/revalidate.py   -- post-approval fresh-snapshot checks
execution/kernel/submit.py       -- broker submission and idempotency
execution/kernel/outcomes.py     -- broker outcome interpretation
```

Hard requirements:

- **Behavior-preserving.** Every existing execution test passes unchanged. A
  refactor that needs its tests rewritten is not a refactor.
- The atomic claim stays a single conditional `UPDATE`. Splitting it into
  read-then-write across module boundaries would reintroduce the exact race
  that `claim_proposal()` was built to close.
- No module may import another's private helpers; the seams must be real.
- Add an AST test pinning that `submit.py` cannot import proposal-generation
  modules.

### 6.3 Tests

- the full existing execution suite passes with zero edits;
- a characterization test captures current behavior **before** the split and
  is diffed after;
- concurrent claim attempts still yield exactly one winner;
- an ambiguous submission still resolves to the reconciler, not a retry.

### 6.4 Definition of done

`execution_service.py` is a thin composition layer, each kernel module is
independently testable, and no test file changed except by import path.

## 7. GR-2 — risk-check consolidation

### 7.1 Purpose

`ARCHITECTURE_DEBT.md` item 2: risk checks are scattered across
`risk/execution_gate.py`, `assistant/policy.py`, `assistant/proposals.py`,
and the UI. Scatter means a new check can be added in one place and silently
missed in another — and a check that runs at proposal time but not at
execution time is a check that does not exist.

### 7.2 Implementation

Introduce a single ordered registry of named checks with explicit
`applies_at` phases (`proposal`, `pre_submit`, `post_approval`). Each check
declares its phase; the gate runs the registry rather than a hand-written
sequence.

Critically: consolidation must not *reduce* what runs. Enumerate every check
that exists today, assign each a phase, and add a test asserting the
registry's contents against that frozen list, so a future deletion is loud.

### 7.3 Tests

- every check that ran before runs after, at the same phase or earlier;
- a check added to the registry automatically runs at its phase;
- removing a check fails the frozen-inventory test;
- a failing check still fails closed with its original error identity.

### 7.4 Definition of done

One registry, one execution order, and a test that enumerates every check by
name. Adding a risk rule becomes a one-line registry entry.

## 8. GR-3 — fault injection and adversarial drills

### 8.1 Purpose

The most important gap in the entire platform. Failure handling exists —
reconciler, stale-order rules, kill switch, ambiguous-submission resolution —
and **none of it has ever been exercised under real adversity.** Untested
error handling is a hypothesis, not a safeguard.

### 8.2 Implementation

Add `tests/faults/` plus a `scripts/run_fault_drill.py` harness that injects
failures against a real SQLite database and a scripted fake broker:

| Fault | Must result in |
|---|---|
| Broker times out after submit, before ack | Reconciler resolves; never a blind resubmit |
| Broker returns a duplicate order ID | Idempotent; one order, one journal entry |
| Process killed mid-submission | Restart resolves the claim; no orphan |
| Broker reports a fill the ledger does not expect | Critical alert; refuse further submissions |
| Ticker halted between approval and submit | Refuse; risk-reducing sells still permitted per mandate |
| Corporate action between snapshot and submit | Refuse on share-count mismatch |
| Clock skew / stale snapshot | Refuse on freshness |
| Disk full during journal write | Transaction rolls back; no partial state |
| Kill switch flips mid-flight | No new submissions; in-flight resolves cleanly |

### 8.3 Tests

Every row above is a test. Each asserts both the refusal **and** that no
partial execution state persists afterwards.

### 8.4 Definition of done

`run_fault_drill.py` runs the whole matrix, writes an immutable drill record
via the existing `operational_drill_runs` table, and the runbook's incident
section links each fault to its observed behavior.

## 9. GR-4 — data-layer resilience and honesty

### 9.1 Purpose

Every number the app shows traces to one provider (yfinance) whose closes are
retroactively adjusted and whose outage mode is an empty frame. The ML track
already established the vocabulary for this; the production read path has not
adopted it.

### 9.2 Implementation

- A `PriceSource` protocol with a declared `provides_point_in_time_lineage`
  flag, mirroring `ml/availability.py`'s existing honesty rule.
- An explicit staleness SLA per data class (quote, bar, fundamental,
  earnings). Breaching it degrades the surface that depends on it, and only
  that surface.
- Provider health recorded per fetch; repeated failure raises an operational
  alert rather than silently returning empty frames.
- Extend `assistant/corporate_actions.py` coverage so a split between
  snapshot and submit is detected, not inferred from a price jump.
- **Never** synthesize a missing price. Refuse the dependent surface.

### 9.3 Tests

- an empty provider response degrades exactly one surface, not the briefing;
- a stale bar past its SLA blocks the proposals that depend on it while
  leaving risk-reduction sells available;
- a split is detected by share-count reconciliation, not price heuristics;
- provider failures raise an alert after a declared threshold.

### 9.4 Definition of done

The briefing renders with a visible degradation banner when data is stale,
rather than rendering confidently from old numbers.

## 10. GR-5 — observability that actually delivers

### 10.1 Purpose

`operational_alerts` records alerts. Nothing has ever *delivered* one. An
alert nobody receives is a log line.

### 10.2 Implementation

- A delivery protocol with at least one real channel the owner will actually
  see. Local desktop notification is sufficient for a single operator; email
  or push is optional.
- Severity routing: `critical` delivers immediately; `warning` batches into
  the daily briefing.
- Delivery is recorded (`delivered_at`, channel, outcome), so an undelivered
  critical alert is itself detectable.
- A weekly self-test that emits a synthetic alert and verifies receipt —
  because a channel that silently broke is worse than no channel.
- A single operator dashboard view in the Streamlit UI: readiness dimensions,
  open alerts, last reconciliation, last drill, evidence-epoch status.

### 10.3 Tests

- a critical alert delivers and records its delivery;
- a delivery failure escalates rather than being swallowed;
- the self-test detects a broken channel;
- duplicate alerts deduplicate by fingerprint (the existing helper).

### 10.4 Definition of done

A critical alert reaches the owner without them looking for it, and the
promotion checklist's "alert delivery exercised" item can be honestly ticked.

## 11. GR-6 — recovery, secrets, and portability

### 11.1 Purpose

Bus factor is one, the machine is one, and the credentials are environment
variables. None of these is exotic to fix; all are load-bearing.

### 11.2 Implementation

- **Recovery objective stated explicitly**: how much history may be lost
  (target: zero committed transactions) and how long restoration may take.
  Verify against the existing backup/restore drill rather than asserting it.
- Off-machine backup of the SQLite database and research artifacts, with the
  restore drill run against the off-machine copy — a backup that has only
  ever been restored locally is not proven.
- A secrets audit: confirm no key reaches logs, the audit trail, LLM prompts,
  UI state, or a stack trace. Add a test that scans structured log/alert
  payloads for anything resembling a credential.
- A documented key-rotation procedure, exercised once.
- Replace Windows-only scheduling with a portable entry point; keep the
  PowerShell installer as one adapter rather than the only path.

### 11.3 Tests

- restore from an off-machine backup reproduces byte-identical ledger state;
- structured payloads contain no credential-shaped strings;
- the scheduler entry point runs identically on Linux CI.

### 11.4 Definition of done

The app can be stood up on a second machine from backup plus credentials
alone, and that has actually been done once.

## 12. GR-7 — product completeness

### 12.1 Purpose

Today the only production proposal path is **selling to cure a policy
breach**, plus user-directed allocation buys and the SOXX/SOXL strategy. That
is a risk tool, not a complete app. This milestone closes the product gap
*without* claiming edge.

### 12.2 Implementation

Ordered by value-per-risk:

1. **Rebalance-to-target proposals.** The mandate already defines targets;
   propose the deterministic trades that restore them, using the wide
   rebalance band already validated in this project's own research (89% less
   tax for equivalent performance). This is deterministic, evidence-backed,
   and needs no alpha claim.
2. **Tax-aware sell selection.** `assistant/tax_lots.py` exists; surface
   lot-level consequences in the proposal preview so the owner sees the
   realized-gain cost of each candidate sale.
3. **Performance attribution.** Extend `assistant/performance.py` to answer
   "where did return come from" — allocation, selection, timing, cost, tax —
   rather than only reporting the aggregate.
4. **Annual tax reporting export.** Realized gains by lot, wash-sale flags,
   in a format that survives an accountant reading it.
5. **Cash management.** Idle-cash reporting against the mandate.

Each stays typed, approval-gated, and refuses on stale data.

### 12.3 Tests

- rebalance proposals respect the band and never propose inside it;
- tax-lot preview matches an independently computed realized gain;
- attribution components sum to total return within a stated tolerance;
- every new proposal type is refused when its data is stale.

### 12.4 Definition of done

The owner can run a full portfolio cycle — review, rebalance, tax-aware
trim, and year-end reporting — without leaving the app or doing arithmetic
by hand.

## 13. GR-8 — bounded live canary

### 13.1 Purpose

Paper fills do not reproduce slippage, partial fills, or broker behavior in a
fast market. At some point the only remaining way to learn is a small amount
of real money.

**This milestone requires explicit owner authorization and cannot be started
on an agent's initiative.**

### 13.2 Preconditions

GR-1 through GR-6 complete, the entire `LIVE_PROMOTION_CHECKLIST.md` passed,
and:

- hard caps on capital, per-order notional, and daily loss, enforced in the
  execution gate rather than by intention;
- an automatic halt on cap breach that requires human re-arming;
- the canary limited to the deterministic risk-reduction path only — no model
  output may influence a live order (`ML-LR-9`/`ML-10` remain separate and
  still prohibited);
- a written stop condition decided in advance, including the loss at which
  the canary ends permanently.

### 13.3 Definition of done

A defined number of live sessions complete with reconciliation clean, caps
never breached, and a written comparison of live versus paper fill quality.

## 14. GR-9 — explicitly deferred

Not to be implemented under this plan:

- multi-account or multi-user support (there is one owner);
- intraday or high-frequency execution (the mandate is not intraday);
- options, futures, margin, or shorting (outside the mandate);
- a web-hosted deployment (increases attack surface for zero benefit to a
  single local operator);
- microservice decomposition (the monolith is appropriate at this size);
- any autonomous trading loop without per-order human approval.

## 15. Sequencing summary

```text
GR-0  taxonomy            (1 milestone, small)
GR-1  execution kernel    <- highest engineering leverage
GR-2  risk registry
GR-3  fault injection     <- highest safety leverage
GR-4  data resilience
GR-5  alerting delivery
GR-6  recovery/secrets
GR-7  product completeness <- highest owner-visible value
GR-8  live canary          <- requires explicit authorization
```

If only three are ever done, do **GR-3, GR-1, and GR-7**: prove the failure
paths work, make the execution path safe to extend, and make the app worth
opening daily.

## 16. What this plan deliberately does not fix

Stated plainly so it is never mistaken for an oversight:

- **It does not create edge.** Zero confirmed signals remains the honest
  state, and finishing every milestone here will not change that.
- **It does not unblock ML promotion.** That is gated on point-in-time data
  from an external vendor, which is a purchasing decision rather than an
  engineering one.
- **It does not remove the human.** Every order still requires an exact
  approval phrase, by design and permanently.
