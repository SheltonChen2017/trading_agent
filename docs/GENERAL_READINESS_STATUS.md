# General Readiness implementation status

Companion to `docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md`, recording what
is built and every deliberate deviation from the plan. Updated 2026-08-02.

The plan was written before the ML full-system milestones landed. Each
milestone therefore needs a gap analysis against the current code *before*
implementation, and the deviations that analysis produces are recorded here
so a future reviewer does not mistake them for accidental divergence.

## GR-0 — readiness taxonomy: **built and independently reviewed**

`assistant/platform_readiness.py`, CLI `platform-readiness`,
`tests/test_platform_readiness.py`.

Five dimensions scored independently and never averaged. Strictly read-only:
it calls `operational_health()` and never `run_operational_check()`, which
persists alerts and heartbeat state.

Observed on a fresh store, 2026-08-02: all five dimensions `blocked`. That is
the honest starting measurement GR-0 exists to produce, not a target. It is
recorded here as an observation; the tests prove `ready`, `degraded`, and
`blocked` independently from fixtures rather than pinning today's result.

### Deviations from plan section 5, and why

**1. The plan's `_check()` instruction is obsolete.**

> §5.2: "Reuse `assistant/readiness.py`'s existing `_check()` shape rather
> than inventing a second report format."

Three incompatible shapes now exist:

| Module | Shape |
|---|---|
| `assistant/readiness.py:44` | `{name, ok, detail}` |
| `assistant/operations.py:32` | `{name, ok, detail, severity, category}` |
| `ml/evidence_operations.py:68` | `{name, ok, severity, detail, evidence}` |

`readiness.py`'s bare boolean cannot express the three-valued status GR-0 is
required to emit. Importing another module's private `_check()` would also
repeat the drift the 2026-08-02 audit found in eleven other helper families
(`tests/test_ml_helper_divergence.py`). GR-0 therefore defines one public
typed contract — `ReadinessCheck` / `DimensionReadiness` /
`PlatformReadinessReport` — and adapts the existing formats into it. No
existing producer was modified.

**2. Severity is decided per dimension, never inherited.**

`operational_health()` labels `environment_kill_switch` and
`persistent_kill_switch` as `warning`. Inheriting that would report an
engaged emergency stop as "degraded" — platform impaired but operable —
which is the opposite of what an engaged kill switch means. Every check in
`execution_integrity` is mandatory regardless of its source label.

Outside execution safety the producer's own split is correct and is honoured:
a stale backup is a genuine deficiency that does not make the platform unsafe
to operate, so it degrades rather than blocks.

Pinned by `test_an_engaged_kill_switch_blocks_despite_its_warning_label`, and
mutation-verified: reinstating the blanket rule turns that test red.

**3. Strategy readiness rests on authority, not on a false premise.**

> §5.2: "`strategy_readiness` must report `blocked` while zero confirmed
> findings exist — currently and correctly zero."

Registry 1.4.1 holds 17 findings, **2 of them confirmed**. Not zero. But
`production_authoritative` means "re-verified since the lookback-days fix
(`9f0ebc1`)" and is orthogonal to the verdict:

```
verdict == confirmed        : 2   (neither authoritative)
production authoritative    : 14  (mostly the 13 REJECTIONS)
confirmed AND authoritative : 0
```

A production-authoritative *rejection* is real research evidence and says
nothing about a strategy being ready. GR-0 therefore requires at least one
finding that is both confirmed and production-authoritative. The verdict is
unchanged today, but it no longer depends on a false premise and will not
silently flip to `ready` when one of those two findings is re-verified.

**4. Absent evidence and invalid evidence are distinguished.**

Both block, but they demand completely different responses — one machine has
not started collecting, the other has corrupt or unattributable evidence — so
the report preserves the distinction in its explanation rather than
collapsing every `PaperEvidenceError` into "no epoch".

**5. `data_integrity` refuses rather than crossing the import boundary.**

`assistant/` may not import `ml/`, so this report cannot reach
`ml/availability.py` for adjustment honesty. GR-0 reports all three plan checks
— price freshness, provider health, and adjustment honesty — as unavailable
and blocked. GR-4 must supply a data-layer adapter that derives them from
authenticated provider records. GR-0 deliberately has no caller-settable
`point_in_time_data=True` escape hatch: a boolean assertion is not evidence.

Pinned by `test_platform_readiness_does_not_import_ml`.

### Independent review corrections

The 2026-08-02 independent review found and fixed five material readiness
misclassifications before GR-0 was accepted:

- `stranded_pre_broker_claims` was misspelled in the mandatory inventory, so a
  stuck claim was reported `degraded` instead of `blocked`;
- `portfolio_ledger_reconciliation` was placed under operations even though
  the plan explicitly makes clean reconciliation part of execution integrity;
- delegated values were coerced with `bool(...)`, so malformed
  `{"ok": "false"}` was treated as passing;
- data integrity covered only adjustment honesty and let a caller assert it
  true; freshness and provider health were absent; and
- one paper session was sufficient for evidence readiness, ignoring the
  mandate's 60-session and 30-order minimums.

The reviewed implementation now validates delegated report types strictly,
blocks when required broker checks are skipped in offline mode, applies the
mandate's evidence counts, and includes every required operational drill
(including alert delivery) in operational readiness. Unreadable delegated
reports become explicit blocked dimensions instead of terminating the whole
command.

## GR-1 — execution kernel split: **partial**

GR-1A characterization is built and independently reviewed in
`tests/test_execution_characterization.py`. No production code has moved yet.
The reviewed freeze covers representative behavior across all five public
entry points, including ordinary submission, broker-call order, reservation
retention/release, immediate timeout reconciliation without a blind retry,
manual reconciliation, recovery, telemetry, persisted order events, exception
identity, the storage-level conditional claim guard, and a synchronized
four-writer contention test that permits exactly one claim winner.

The gap analysis corrected three stale plan assumptions:

- `assistant/execution_service.py` is 2,040 lines, not approximately 1,450;
- the four planned seams are interleaved inside the 582-line
  `execute_approved_paper_proposal()` function; and
- the atomic conditional claim already belongs to `AssistantStore`, so the
  kernel may orchestrate it but must not move or reimplement it.

The reviewed package decision is `assistant/execution_kernel/`, preserving the
existing dependency direction and avoiding an `assistant -> execution ->
assistant` package cycle. GR-1 remains partial until helpers and then the
interleaved orchestration are extracted behind the unchanged
`assistant.execution_service` facade and independently reviewed.

### What the characterization suite can actually detect

A green characterization suite means nothing on its own; it must be shown to
fail when the behaviour it names is removed. Three rounds of mutation testing
were needed here, and every round found tests that passed while their subject
was deleted — first the original suite, then the reviewed extension.

Confirmed **detected** (each verified by deleting the behaviour and observing
a failure, then restoring):

| Mutation | Detected by |
|---|---|
| kill-switch check removed | `test_an_engaged_kill_switch_blocks_...` |
| exception identity changed | `test_wrong_confirmation_phrase_...` |
| reservation release removed on the unsupported-order-type path | `test_an_unsupported_order_type_blocks_and_releases_...` |
| idempotency key not passed to the broker | `test_submission_carries_the_proposals_exact_idempotency_key` |
| unsupported order type silently downgraded to market | `test_an_unsupported_order_type_blocks_and_releases_...` |

All three release paths now have a recorded mutation result. The third,
`mark_submission_failed_and_release` in `reconcile_submission`, is the only
place a broker 404 frees reserved budget, and it is gated on
`BROKER_ABSENCE_GRACE_SECONDS` because a fresh 404 may only mean the broker
has not indexed the order yet. Both halves are frozen and verified:

| Mutation | Result |
|---|---|
| grace period ignored — a fresh 404 trusted as absence | DETECTED |
| confirmed absence no longer releases budget | DETECTED |
| absence check inverted — a 404 never trusted | DETECTED |

**Correction to an earlier entry.** Partial-fill and replacement-chain
handling was previously listed here as uncharacterized. That was wrong.
`execution_service.py:444` delegates to
`order_lifecycle.resolve_replacement_chain()`, which lives in a module GR-1
does not split and carries 42 dedicated tests across
`tests/test_replacement_chain.py` and `tests/test_replacement_chain_round3.py`.
Those were mutation-checked directly: suppressing chain recording fails six
of them. What GR-1 actually moves is the thin delegating wrapper
`_authoritative_order_for()`, not the chain logic.

Remaining honest limit: the characterization freezes representative paths,
not every branch of a 2,040-line module. GR-1B should add a recorded mutation
result for any specific behaviour it moves that is not already listed above,
rather than treating a green suite as sufficient.

## GR-2 .. GR-9 — not started

Each requires its own gap analysis first; the plan predates the ML
full-system additions throughout.

Known items already identified for later milestones:

- **GR-3** drills should include the two isolation failures found on
  2026-08-02: pytest writing to the operator database (`ce03386`) and the
  suite issuing live broker calls during collection (`2203e7e`). Both were
  live for weeks.
- **GR-5** must account for `operational_alerts`, `alerts.jsonl`, and the ML
  evidence supervisor, which already exist. Choosing a real alert channel is
  an owner decision.
- **GR-6** is where a database-identity guard belongs. Under the single
  installation topology chosen over the pinned-worktree alternative, it is
  defense-in-depth rather than a precondition.

## Data-quality note for readiness reporting

`portfolio_equity_snapshots` contains a mixture of legitimate briefing rows
and test pollution written before 2026-08-02, when pytest was isolated from
the operator database. The rows were deliberately **not** deleted. Any
readiness or evidence report covering that table should treat it as
unreliable before that date rather than averaging across the boundary.
