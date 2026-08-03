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

## GR-1 — execution kernel split: **COMPLETE after independent GR-1E review (2026-08-03)**

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

- `assistant/execution_service.py` measured 2,040 lines at the GR-1A freeze
  (larger than working estimates; the archived plan itself states no line
  count — an earlier revision of this section attributed a "~1,450" figure
  to the plan that appears nowhere in it);
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

#### Review-of-review follow-ups (2026-08-02)

Every review change was independently verified before acceptance: the
`DuplicateIntentConflict` restoration is correct (the name was importable
from the facade at `d9e3196`, so dropping it was an API change regardless of
in-repo usage), the corrected `outcomes.py` docstring fixes a real defect the
decomposition introduced ("never transitions a proposal" became false when
`resolve_failed_submission` moved in), and the 1,361 figure is exact.

Two gaps in the review itself were closed as follow-ups:

- **The telemetry fall-through hazard was not addressed.** The facade
  previously called `release_after_telemetry_failure()` with no independent
  `raise` at the call site, so "never submit after a telemetry failure"
  silently depended on the helper always raising. The helper is now annotated
  `NoReturn`, the call site has a bare-`raise` guard, and
  `test_a_neutered_release_helper_still_never_submits_to_the_broker` neuters
  the helper into a plain return and proves an order is still never submitted.
  Mutation-verified: deleting the guard fails that test.
- **The stale-name fix was not generalized.** The review corrected two
  references to the never-existent `submit_approved_proposal()` but the same
  wrong name survived in four more places (`order_lifecycle.py`,
  `order_reconciler.py`, `test_absence_age_guard.py`,
  `test_stranded_claim_recovery.py`); `git log -S` confirms no function of
  that name ever existed. All four now name
  `execute_approved_paper_proposal()`. Comment-only edits; no test behavior
  changed.

### GR-1C — validation orchestration moved behind explicit dependency injection

The step GR-1B's review named is done: the 315-line
`validate_proposal_for_execution()` body now lives in
`assistant/execution_kernel/validate.py` as `run_proposal_validation()`,
together with the `ProposalValidationOutcome` dataclass (re-exported from the
facade as the same class object). `execution_service.py` is down from 1,361
to 1,094 lines after all independent-review compatibility corrections. Claude's
implementation added 2 characterization tests and 2 identity/export pins;
the review added 2 more characterization tests and expanded the export pin.

The mechanism is the one GR-1B's deviation #1 predicted would be required.
Every callable the orchestration used to resolve from the facade's module
namespace is now an explicit field on a frozen `ProposalValidationDeps`
contract:

| Injected seam | Legacy facade name |
|---|---|
| deferred broker import (provider, called mid-sequence) | `import execution.alpaca_broker` inline |
| validation clock/type | `datetime` |
| decimal-zero factory | `Decimal` |
| open-order intent construction | `TradeIntent` |
| decimal conversion | `to_decimal` |
| environment kill switch | `env_kill_switch_active` |
| policy fingerprint | `compute_policy_fingerprint` |
| stored-intent parsing | `_intent_from_dict` |
| pending-buy exposure estimation | `_pending_buy_value_by_ticker` |
| earnings-date resolution | `_resolve_earnings_days_away` |
| the risk gate itself | `validate_trade_intent` |

The facade wrapper constructs the deps INSIDE its function body from bare
names, so each name is resolved from `assistant.execution_service.__dict__`
at call time — which is exactly what keeps
`execution_service.validate_trade_intent = stub`
(`tests/test_personal_assistant.py:1465`) working after the move. The broker
dependency is a provider function rather than a module object so the deferred
import still runs AFTER the existence/expiry/policy refusals, preserving
which error wins when the broker package itself cannot import. A side
benefit: the kernel resolves none of these collaborators from its own runtime
namespace, so the section 6.2 private-peer-import guard is satisfied
structurally rather than by aliasing.

The facade-surface rule applies without distinguishing standard-library from
first-party names when GR-1 itself makes an existing import dead. The full
pre-GR-1C importable surface stays importable and identity-pinned by
`test_gr1c_preserves_the_facades_export_only_names` — the review rejected
dropping `DuplicateIntentConflict` on exactly this ground, so the same rule
is applied consistently. Precision correction (third round): the passage
above previously described every pinned name as having "no remaining facade
call site", which was wrong from the moment the deps wiring existed —
`Decimal`, `to_decimal`, and `TradeIntent` have been facade call sites since
the review's injection (`465df8d`), and `FAILURE_DATA_INTEGRITY` /
`FAILURE_INFRASTRUCTURE` joined them in the follow-up review (`c1de927`).
The genuinely export-only names are `MoneyInput`, `ValidationResult`,
`intent_fingerprint`, `dataclasses`, `FAILURE_DETERMINISTIC_POLICY`, and
`FAILURE_NONE`. The earlier removal of an unrelated pre-existing dead `os`
import was cleanup; removing names solely because this refactor moved their
call sites would be a GR-1 compatibility change.

#### Independent review corrections

The review found that the original seven-field dependency bundle was not yet
complete. The moved body still resolved `datetime`, `Decimal`, `TradeIntent`,
and `to_decimal` inside the kernel. On Claude's committed snapshot, focused
tests proved that replacing each corresponding facade name no longer affected
validation, even though the milestone claimed every callable seam remained a
call-time facade dependency. The review injected those four runtime
collaborators, covered both expiration and quote-receipt clock reads, restored
the two dropped facade exports, and corrected the module's description from
"pure" to "read-only": validation reads durable state and queries the broker,
but does not mutate proposal, reservation, telemetry, or order state.

#### Review-of-review follow-ups and independent correction (2026-08-02)

Every review change was independently verified before acceptance. The four
injections are correct and complete for their category (no direct
`datetime`/`Decimal`/`TradeIntent`/`to_decimal` calls remain in the body),
the two new seam tests are load-bearing (reverse-mutations restoring each
kernel-resolved call fail them — both clock reads verified independently),
and the facade-surface rule is internally consistent: the GR-1B `os`
removal survives it because `os` was already dead at `d9e3196`, before any
GR-1 refactor orphaned anything.

Claude's follow-up identified two precision gaps:

- **"Injected every runtime collaborator" claimed more than the code
  enforced.** Claude documented and allowlisted the three remaining
  categories: `ProposalValidationOutcome`, `timezone`, and the
  behavior-bearing `FAILURE_*` constants.
- **The "pure" sweep was incomplete** — the reviewed rename fixed the module
  docstring and one test, but "pure, side-effect-free" survived in the
  `ProposalValidationOutcome` class docstring and a
  `test_personal_assistant.py` section comment. Both now say read-only.
  Comment-only edits.

The independent review accepted the terminology cleanup but rejected the
allowlist as a compatibility solution. Before extraction, replacing any of
those names on `assistant.execution_service` changed validation behavior;
after Claude's follow-up it did not. Three red characterization tests proved
the regressions independently for outcome construction, the UTC argument, and
failure classification. `ProposalValidationDeps` now carries the facade's
outcome factory, timezone collaborator, and data-integrity/infrastructure
constants at call time. The kernel body has no module-global runtime reads,
pinned by `test_gr1c_the_kernel_body_reads_no_module_globals`. The guard uses
Python's symbol table rather than a hand-rolled AST scope approximation, so
nested scopes and module globals shadowing builtins cannot create false
negatives.

#### Confirmation of the follow-up review (Claude, 2026-08-02, third round)

Every correction in `c1de927`/`d2d836b` was independently re-verified before
acceptance:

- all three new characterization tests fail red on the exact pre-correction
  tree (`2882889`) and the symtable guard fails there naming exactly the four
  residual globals;
- reverse-mutating each injected seam back to kernel-local resolution
  (`outcome_factory` → direct construction, `timezone_type` → kernel-imported
  `timezone`, `failure_data_integrity` → kernel-imported constant) is caught
  by BOTH the guard and the matching behavioral test — six of six detections;
- the size corrections are exact as of `c1de927` (`execution_service.py`
  1,094; `execute_approved_paper_proposal` 281; `validate.py` 479;
  `run_proposal_validation` 294); the follow-up's earlier 276/1,090 figures
  were stale carry-forwards, correctly caught. (`validate.py` then grew to
  490 lines when this same round's `7f431b6` added the residual-seam
  property docstring — the 479 above is the figure verified at `c1de927`,
  not the current size.)

The P2 classification of the allowlist is accepted: by the standard this
repository already applied to `DuplicateIntentConflict`, "no test uses the
seam" does not make removing the seam compatible.

One residual of the same regression class remains, on the class rather than
the body: `ProposalValidationOutcome.resolved_failure_class` still resolves
its `FAILURE_NONE` / `FAILURE_DETERMINISTIC_POLICY` fallbacks from the
kernel's namespace at property-access time. Pre-GR-1C the class lived on the
facade, so patching either facade constant changed the property's output
(verified on `5dda78e`); it no longer does. This is documented rather than
fixed because both available fixes are worse than the gap: injecting the
fallbacks would change the frozen dataclass's public field set (a larger
compatibility break than the seam it restores), and resolving them from the
facade would invert the kernel→facade dependency direction GR-1 forbids.
`test_gr1c_resolved_failure_class_fallbacks_are_class_resolved` pins the
boundary so changing it becomes an explicit decision.

### GR-1C mutation results

Every mutation was applied in the code's NEW location (or to the new
wrapper), run, and restored. All seven were detected:

| Mutation | Result |
|---|---|
| kernel resolves `validate_trade_intent` from its own namespace instead of the injected dep — the exact regression this milestone exists to prevent | DETECTED (2 tests: the new seam freeze AND the pre-existing `validation_failed` test) |
| facade passes the real gate directly, bypassing its own namespace | DETECTED (same 2 tests) |
| kernel kill-switch refusal deleted | DETECTED (2 tests) |
| expiry check deleted | DETECTED |
| policy-fingerprint check deleted | DETECTED (2 tests) |
| open-orders fail-closed check deleted | DETECTED |
| wrapper silently drops the `extra_open_order_count` passthrough | DETECTED (4 batch-cap tests) |

Precision notes, stated so the table cannot over-claim:

- The kill-switch deletion is single-site WITHIN validation:
  `validate_trade_intent()` also receives the flag and still rejects, so what
  the deletion loses is the error-classified hard refusal (`outcome.error`)
  in favour of a policy-violation rejection — and that is precisely the form
  the new seam test pins.
- The passthrough mutation class is NEW risk introduced by the wrapper shape
  itself (a kwarg silently dropped between wrapper and kernel would revert
  that parameter to its default). One representative passthrough was mutated;
  the others are exercised by `test_allocation_batch`'s
  override-comparison tests and the existing preflight suite.

Honest limit: the orchestration body moved verbatim, and its internal
branches remain covered by the same pre-existing suite as before — the new
tests freeze the injection contract, they do not add branch coverage. GR-1
remains partial: the 281-line execute composition, the 221-line
`reconcile_submission`, and the two recovery functions still live on the
1,094-line facade, and whether that satisfies the plan's "thin composition
layer" is a reviewer call, not a claim made here.

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

### GR-1D — manual reconciliation extraction: built and independently reviewed

The 221-line `reconcile_submission()` orchestration moved token-verbatim
(813 tokens identical after seam-rename and one trailing-comma
normalization) into
`assistant/execution_kernel/reconcile.py::run_submission_reconciliation`,
behind a frozen 13-field `ReconciliationDeps` contract the facade builds at
call time from its own namespace. The injection boundary was enumerated
MECHANICALLY BEFORE the move (symtable over the pre-move facade body — the
lesson GR-1C taught three times), yielding exactly twelve module-global
reads plus the deferred broker import:

| Seam | Fields |
|---|---|
| Deferred broker import (first statement inside the try, after the atomic claim) | `import_broker` (shared `_import_execution_broker` provider) |
| Clock | `datetime_type`, `timezone_type` (`timezone.utc` resolved at its historical evaluation points) |
| Exception identity (raised AND caught through the same injected object) | `proposal_execution_error` |
| Behavior-bearing status constants | `submitting`, `submission_unknown`, `reconciling` |
| Stored-intent parsing | `intent_from_dict` |
| Broker lookup / matching / replacement chains / absence age | `lookup_order_outcome`, `order_matches_intent`, `authoritative_order_for`, `broker_absence_is_old_enough` |
| Order journaling | `journal_broker_order_update` |

Eight seam-freeze characterization tests were written FIRST and run green on
the pre-move code, then re-run green after the move; the sys.modules-level
broker-fake suites (`test_replacement_chain_round3.py`,
`test_absence_age_guard.py`) pass unchanged because the injected provider
executes the same `import execution.alpaca_broker` statement. The kernel
body has zero module-global runtime reads, pinned by
`test_gr1d_the_kernel_body_reads_no_module_globals` (same symtable mechanism
as GR-1C). The mechanical pre/post facade-surface comparison shows nothing
removed and exactly two additions (`ReconciliationDeps`,
`run_submission_reconciliation`, both the exact kernel objects). The atomic
claim and every conditional transition remain `AssistantStore` operations.
`execution_service.py` is now 952 lines (from 1,094); `reconcile.py` is 269.

### GR-1D mutation results

Every mutation was applied in the code's NEW location (or to the new
wrapper), run, and restored. All eight were detected:

| Mutation | Result |
|---|---|
| fresh-404 grace guard deleted (too-recent absence becomes confirmed failure) | DETECTED (3 tests) |
| unconfirmed lookup collapsed into the confirmed-absence branch | DETECTED (3 tests, incl. `test_a_failed_lookup_is_never_treated_as_confirmed_absence`) |
| same-key mismatch guard deleted (mismatched order journaled) | DETECTED (8 tests) |
| replacement-chain resolution bypassed | DETECTED (12 tests) |
| unexpected-error recovery write no-oped (proposal strands in `reconciling`) | DETECTED (4 tests, incl. journal-failure recovery) |
| kill-switch activation on direct mismatch deleted | DETECTED (1 test — the new seam test; precision note: pre-existing direct-mismatch tests assert the refusal but not kill-switch persistence, and the round3 kill-switch test covers only the chain-mismatch branch) |
| grace-clock `preserve_updated_at` dropped (retry starvation) | DETECTED (`test_a_blocked_reconcile_attempt_does_not_restart_the_grace_clock`) |
| wrapper resolves a dep from the kernel instead of the facade namespace | DETECTED (5 seam tests) |

### GR-1D independent review (2026-08-03)

PR #120 merged the topic at `711095c`; its merge tree is byte-identical to
topic tip `88b06f8`. Independent review found no P0-P2 defect in the
extraction. The old branch order, three-way lookup interpretation,
fresh-absence reservation hold, aged-confirmed-absence release, replacement
chain, mismatch kill switch, and unexpected-error recovery were checked in
the new location. The facade still constructs all thirteen dependencies at
call time, the kernel body still reads zero module-global runtime names, and
all claims/transitions remain storage-level operations.

The focused reconciliation set passed 119 tests. Two representative reverse
mutations were reproduced independently and detected: bypassing the facade's
lookup seam changed the outcome branch, and suppressing the direct-mismatch
kill switch failed the safety assertion. The corrected combined review tree
passed 2,485 tests with 1 skipped and 25 warnings; compilation and diff checks
were clean. Durable disposition:
`docs/REVIEW_2026-08-03_GR1D_RECONCILIATION.md` (`2f37210`). GR-1D is
accepted; GR-1 remains partial pending the GR-1E assessment below.

### GR-1E — composition-thinning assessment: NO FURTHER EXTRACTION; GR-1 accepted complete (2026-08-03)

GR-1E was defined as an assessment first, not an automatic extraction:
compare the remaining facade against the archived definition of done
(plan section 6.4) and record one of two honest outcomes. The assessment
was performed over the exact tree at `c66db0a` and independently reviewed
against the merged tree at `16e0451`. The implementation did not retain its
line-classification script, so the original 172-line/19-domain-call figures
are descriptive measurements rather than a reproducible acceptance gate.
The independent review instead recorded a reproducible Python-AST inventory:
the function contains 54 statement nodes, 49 call nodes, and 28 distinct call
expressions. Those calls include kernel phases, gate and telemetry seams,
ordinary constructors/formatters, and exactly one broker submission call.

#### What the facade actually contains (952 lines)

| Segment | Lines | Of which executable code |
|---|---|---|
| Module docstring (19-round audit history, deliberately retained) | 198 | 0 |
| Imports incl. review-pinned compatibility re-exports | ~90 | — |
| `execute_approved_paper_proposal` | 281 | 172 (implementer classification) |
| `validate_proposal_for_execution` (GR-1C wrapper) | 90 | 43 |
| `reconcile_submission` (GR-1D wrapper) | 72 | 18 |
| `recover_stale_reconciliation` | 75 | 31 |
| `recover_stale_claim` | 98 | 51 |
| Remaining helpers/docstrings/comments | — | — |

The execution composition invokes the named domain phases
(`resolve_kill_switch`, `verify_execution_preconditions`,
`claim_for_execution`, `classify_override_review`,
`build_reviewed_override_record`, `_transition_pre_broker_claim`,
`reserve_daily_budget`, `resolve_submission_call`,
`release_after_telemetry_failure`, `resolve_failed_submission`,
`journal_accepted_order`), the GR-1C validation wrapper, a risk-gate
authorization (`authorize_trade_intent` /
`authorize_overridden_trade_intent`), and telemetry recorders — plus exactly
one broker-contact line. It also performs the ordinary coordinator work the
AST inventory makes explicit: branching, exception mapping, timestamps, and
message/list/dictionary construction. There is no inline financial
computation, no inline state-transition SQL, and no interpretation logic
left in the body: what remains is the phase ORDER, the exception→terminal-
status mapping, and two telemetry calls that stay facade-resolved by
documented seam design (`record_submission_started` is monkeypatched by
tests on the facade). That control flow is not residue to be extracted —
it is the composition layer the definition of done asks for. Moving it
into a kernel function behind another deps contract would relocate the
composition, not thin it.

#### Definition-of-done adjudication (plan sections 6.2-6.4)

- **"`execution_service.py` is a thin composition layer"** — MET, as
  measured above: ~315 executable orchestration lines across five
  functions, all sequencing, argument validation, or refusal-message
  construction around kernel and storage primitives.
- **"Each kernel module independently testable"** — MET: eight kernel
  modules (`claim`, `revalidate`, `submit`, `outcomes`, `errors`,
  `intents`, `validate`, `reconcile`), each exercised directly by the
  characterization/execution suites plus their structural guards.
- **"No test file changed except by import path"** — NOT LITERALLY
  SATISFIABLE alongside section 6.3's requirement to add characterization
  tests. Across the GR-1 history, existing characterization files gained new
  assertions and a few import/comment adjustments. Independent review found
  no pre-existing behavioral assertion relaxed or rewritten to make an
  extraction pass. This is the behavior-preservation intent used for
  acceptance; the archived plan's contradictory literal wording remains
  recorded rather than misreported as held.
- **"The atomic claim stays a single conditional UPDATE"** — HELD; it
  never left `AssistantStore`, and both recovery paths use the same
  conditional `reclaim_stale_status` primitive.
- **"No module may import another's private helpers"** — HELD,
  AST-enforced since GR-1A's review.
- **"An ambiguous submission still resolves to the reconciler, not a
  retry"** — HELD (`resolve_failed_submission`, characterization-frozen).

#### The residual, stated honestly

The two recovery wrappers (82 implementer-classified executable lines
combined) remain on the facade DELIBERATELY: each is input validation around
the atomic `AssistantStore.reclaim_stale_status` primitive plus precise
refusal diagnosis. `recover_stale_reconciliation` has one invocation;
`recover_stale_claim` has one static call site inside a bounded status loop
and can invoke the primitive more than once before one candidate succeeds.
Their entire concurrency and
atomicity risk already lives in `AssistantStore.reclaim_stale_status`;
extracting them would add a third deps contract and seam-test family
while reducing no risk and simplifying nothing. If a future milestone
changes recovery SEMANTICS, extraction can be reconsidered then, with
characterization first.

Outside the archived GR-1 plan's execution-service scope and therefore NOT
closed by this declaration: `allocation_batch.py` still owns cross-leg
reservation math separately from storage-level budget reservation. That work
remains open in ARCHITECTURE_DEBT items 1 and 2 and must follow the adopted
action plan's sequencing. Risk-check scatter remains GR-2's consolidation
target.

**Independent-review decision: outcome 1 — no GR-1E extraction; GR-1 is
complete against the archived plan's intended definition of done.** The
review accepted the architectural conclusion after correcting the evidence
and scope statements above; see
`docs/REVIEW_2026-08-03_GR1E_ASSESSMENT.md`.

## GR-3 — fault injection and adversarial drills: COMPLETE after independent review (2026-08-03)

The archived plan's section 8.2 fault matrix is implemented as
`tests/faults/` (a self-contained harness: real `AssistantStore` on
temporary SQLite, the real execution entry points, and a scripted broker
patched at the same `execution.alpaca_broker` attributes the deferred
import resolves) plus `scripts/run_fault_drill.py`, which runs the whole
matrix, maps every plan row to its observed outcome, and atomically writes a
hash-stamped JSON report. The eleven fault IDs map to fourteen behavioral
tests asserting the mandated refusal/resolution and applicable no-partial-
state invariants (shared referential-integrity checks plus per-fault state
snapshots); the two 2026-08-02 isolation incidents the
previous revision of this section earmarked (pytest touching the operator
database, live broker calls during collection) are standing drills F10/F11.

Notable mechanics:

- the disk-full fault (F8) injects a `sqlite3.OperationalError` carrying
  SQLite's ``database or disk is full`` message on the events insert INSIDE
  the atomic journal projection, after earlier statements of the same
  transaction have really executed. This is statement-level fault injection,
  not physical disk exhaustion; the observed rollback (no half-journal) is
  SQLite's own, and the drill also proves the accepted order is never reported
  as a submission failure and that reconciliation repairs the record;
- F3 now includes the actual startup case left by a process death in
  `submitting`: broker lookup adopts the already-accepted order without any
  resubmit, retains its reservation, and leaves no orphan;
- F4 now atomically persists both the kill switch and a deduplicated critical
  `broker_reconciliation` alert. The same invariant covers manual, startup,
  stream, and replacement-chain identity mismatch paths, ready for GR-5's
  later delivery channel;
- the harness records the three newly producible promotion drill types
  (``ambiguous_submission`` ← F1/F2, ``restart_recovery`` ← F3,
  ``kill_switch`` ← F4/F9) via ``--record-database``: epoch-bound through
  `assistant.paper_evidence.record_operational_drill` when an active epoch
  exists, else explicitly ``verification_only`` with ``evidence_epoch``
  NULL. Active-epoch recording now requires the drill report's exact clean
  commit to equal the epoch lineage; unknown, dirty, or different code is
  refused before any drill row is written. Failed drills are recorded as
  failures, never dropped;
- lineage is fail-closed: a dirty worktree records ``code_commit=unknown`` in
  the standalone report and cannot be written into an active epoch;
- the fault inventory cannot silently shrink: a listed test that fails to
  collect or is skipped is a FAILED drill, abnormal pytest exits without a
  matching failed/error case abort the harness, and any unmapped test in
  `tests/faults/` fails the report (mutation-verified: renaming the F6 entry
  produced overall ``passed=false``, exit 2, and surfaced the orphaned
  real test in ``unmapped_tests``; neutering the F8 injector was detected
  by the F8 test itself).

`alert_delivery` remains the one drill type without a producer until GR-5
ships a real channel; `backup_restore` keeps its existing `recovery-drill`
producer. The runbook's incident section now links every fault row to its
observed behavior and the drill command. Independent review and validation
are recorded in `docs/REVIEW_2026-08-03_GR3_FAULT_DRILLS.md`.

## GR-5 — observability that actually delivers: IMPLEMENTED, awaiting review (2026-08-03)

`operational_alerts` had always RECORDED alerts; nothing had ever DELIVERED
one, so a critical broker-identity halt could sit in SQLite while the
operator watched a green screen. `assistant/alert_delivery.py` closes that:

- **Channel (owner decision 2026-08-03):** Windows desktop notification is
  the mandatory immediate channel for `critical`; `warning` batches into the
  daily briefing; webhook is deliberately out of scope. The toast goes
  through PowerShell's built-in WinRT API, so the milestone adds **no new
  pinned dependency**, and alert text is passed on **stdin as JSON** rather
  than interpolated into a command line.
- **Delivery is recorded, never assumed:** every attempt appends an
  immutable `alert_deliveries` row (channel, outcome, attempted/delivered
  timestamps, occurrence count at attempt). A later success never erases an
  earlier failure, so "this took three attempts" and "this was never
  delivered" both remain answerable.
- **Failure escalates:** a channel exception is caught only to record it,
  then surfaced via the return value (nonzero CLI exit) AND a durable
  critical `alert_delivery` alert. It is never recorded as delivered. The
  "delivery is broken" alert is deliberately not pushed through the broken
  channel.
- **Re-delivery is occurrence-based:** an unchanged condition is not
  re-toasted every 60-second sweep; a genuinely new occurrence is.
- **Self-test:** emits a synthetic critical alert, delivers it, and verifies
  the receipt **read back from storage** (not the in-memory return), then
  acknowledges the synthetic alert so it cannot pollute the operator's list.
  It records the `alert_delivery` promotion drill — epoch-bound only when
  the runtime commit exactly matches the active epoch's lineage (the GR-3
  review's GR3REV-001 rule, applied here from the start), else
  verification-only. A failed self-test is recorded and escalated.
- **Detection:** `platform-readiness` now reports `critical_alert_delivery`
  (mandatory) and `alert_channel_self_test` (degrades only).

**Design note worth preserving:** these two checks live in the READ-ONLY
readiness report rather than `operational_health`. An earlier revision put
them in `operational_health`, whose caller persists an alert for every
failing check — so "undelivered critical alerts exist" raised a critical
alert that was itself undelivered, manufacturing a new alert every cycle. A
pre-existing dedup test caught it. `test_delivery_health_never_manufactures_
its_own_alert` now pins the resolution.

New operator surface: the Streamlit **Operations** tab (undelivered
criticals, self-test freshness, open alerts with delivered flags, recent
delivery attempts, readiness dimensions, heartbeat/backup/epoch state,
recent drills) plus CLI `deliver-alerts` and `alert-self-test`.

Mutation-verified: recording a failed send as delivered, dropping severity
routing, and dropping occurrence-based re-delivery are each detected.
`alert_delivery` was the last `REQUIRED_PROMOTION_DRILLS` type without a
producer — **AP-5 is now closed**; all five drill types can be produced.

Honest limits: the Windows channel is exercised through its failure
directions (missing PowerShell, nonzero exit, stdin argument passing) and
never by raising a real toast in tests; delivery proves the notification was
*raised*, not that a human read it; scheduled-task installation for
`deliver-alerts`/`alert-self-test` is Phase 5 deployment work, not this
milestone.

## GR-2, GR-4, GR-6 .. GR-9 — not started

Each requires its own gap analysis first; the plan predates the ML
full-system additions throughout.

Known items already identified for later milestones:

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
