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

## GR-1 — execution kernel split: **partial; GR-1B independently reviewed**

GR-1A characterization is built and independently reviewed in
`tests/test_execution_characterization.py`. The first production extraction is
complete: broker outcome interpretation now lives in
`assistant/execution_kernel/outcomes.py`, while
`assistant.execution_service` preserves the existing facade imports.
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
assistant` package cycle. Outcome lookup, identity matching, replacement-chain
interpretation, absence-age classification, stored-intent parsing, pre-broker
claim fencing/recovery support, revalidation inputs, submission sizing, and
the shared exception hierarchy now live there. The unchanged
`assistant.execution_service` facade re-exports the legacy names and exception
objects.

The independent review of the remaining helper extraction found one structural
contract violation: `claim.py` imported the private
`_ProposalClaimLostError` name from the peer `errors.py` seam despite GR-1
section 6.2 forbidding private peer dependencies. The review added an AST
boundary regression test, exposed a public kernel alias, and preserved the
legacy private facade name as the exact same class object.

### GR-1B — orchestration decomposition: built and independently reviewed

`execute_approved_paper_proposal()` is decomposed from 580 lines to 276, and
`assistant/execution_service.py` from 1,656 to 1,361. The twelve phases are
now named calls in a readable sequence. Moved this milestone:

| Phase | Now in |
|---|---|
| kill-switch resolution (caller ∨ env ∨ persistent) | `claim.resolve_kill_switch` |
| pre-claim preconditions and policy binding | `claim.verify_execution_preconditions` |
| atomic claim and conditional expiry fallback | `claim.claim_for_execution` |
| reviewed-override matching and record construction | `revalidate.classify_override_review`, `revalidate.build_reviewed_override_record` |
| budget reservation and its fenced refusal | `submit.reserve_daily_budget` |
| order-type dispatch and unsupported-type release | `submit.resolve_submission_call` |
| telemetry-failure release | `submit.release_after_telemetry_failure` |
| ambiguous-outcome resolution (110 lines, 4 branches) | `outcomes.resolve_failed_submission` |
| accepted-order journaling | `submit.journal_accepted_order` |

The atomic claim did not move: `claim_for_execution()` orchestrates
`AssistantStore.claim_proposal()`'s single conditional UPDATE, as GR-1
section 6.2 requires. No test file was changed except by addition.

#### Deviations, and why

**1. `validate_proposal_for_execution` stays on the facade.**
`tests/test_personal_assistant.py:1465` monkeypatches
`execution_service.validate_trade_intent`. Moving its caller into the kernel
would make that name resolve in the kernel's namespace instead, silently
defeating the patch. That is a caller-visible seam change, not an import-path
change, so the 315-line validation orchestration remains where it is.

**2. The `record_submission_started` CALL stays on the facade, for the same
reason** — and this one was not predicted, it was caught.
`test_pre_submit_telemetry_failure_releases_budget_without_broker_contact`
turned red the moment that call moved into `submit.py`. Only the failure
HANDLING, which has no such seam, was extracted. The characterization suite
did exactly the job it was built for.

**3. `transition_pre_broker_claim` gained a public name.** `submit.py` needs
it, and GR-1 section 6.2 forbids importing a private peer name. Same pattern
the review applied to `ProposalClaimLostError`: the public name is the
definition, the underscore name is an alias to the same function object, and
the facade re-exports the legacy name.

The independent review found one facade-compatibility regression:
`DuplicateIntentConflict` had been dropped merely because the decomposed
implementation no longer used it locally. GR-1 requires the facade to remain
unchanged, so a regression test now pins the export to the exact class object
from `assistant.storage` and the facade re-export is restored. The review also
removed the unrelated dead `os` import and corrected kernel documentation that
understated `outcomes.resolve_failed_submission()`'s durable side effects.

GR-1B's decomposition is accepted, but GR-1 remains partial. At 1,361 lines,
with 315-line validation orchestration and 221-line manual reconciliation
still on the facade, `execution_service.py` is not yet the plan's "thin
composition layer". A remaining GR-1 step should replace the facade
monkeypatch seams with explicit dependency injection before moving those
orchestrators, preserving test and caller behavior while completing the split.

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

### GR-1B mutation results

Every behaviour moved in GR-1B was mutated in its NEW location, measured, and
restored. Five previously uncovered behaviours were found this way and are now
frozen by six added tests (no existing test was modified).

| Mutation | Result |
|---|---|
| `set_kill_switch(True)` removed from the mismatched-order path | DETECTED |
| `_order_matches_intent` always returns True | DETECTED |
| reservation released on a mismatched order | DETECTED |
| `classify_override_review` reduced to `bool(override_requested)` | DETECTED (6 tests) |
| journal failure reported as a submission failure | DETECTED |
| budget refusal raises without the fenced transition | DETECTED *(after new test)* |
| `not_expired_after` dropped from the atomic claim | DETECTED *(after new test)* |
| kill switch reduced to the caller flag, BOTH sites | DETECTED *(after new test)* |
| policy-fingerprint check disabled, BOTH sites | DETECTED *(after new test)* |

Four of these were uncovered before GR-1B and are recorded precisely, because
the imprecise version of each claim is misleading:

- **The mismatched-order platform halt had no test anywhere in the repository.**
  Grepping its error strings across `tests/` returned nothing. It is the only
  execution path that engages the persistent kill switch.
- **The kill switch and the policy fingerprint are each enforced at TWO
  sites** — the pre-claim gate and, authoritatively, inside
  `validate_proposal_for_execution()`. A single-site mutation survives *by
  design*, so it proves nothing. Removing either check from BOTH sites was
  undetected until GR-1B added end-to-end tests, including one for the
  PERSISTENT switch: the pre-existing kill-switch test passes
  `kill_switch_active=True`, so it only ever proved the caller's own flag was
  honoured, not the switch an operator actually flips.
- **Dropping `not_expired_after` does not let an expired order reach the
  broker** — validation still refuses, measured. What it loses is the
  *location*: the proposal gets claimed first and ends `blocked` rather than
  `expired`, briefly holding its ticker/side duplicate slot. The new test
  pins the status precisely to tell the two arrangements apart.

Remaining honest limit: the characterization freezes representative paths, not
every branch of the 1,361-line facade. The 315-line
`validate_proposal_for_execution` orchestration is unchanged by GR-1B and its
internal branches remain covered only by the pre-existing suite.

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
