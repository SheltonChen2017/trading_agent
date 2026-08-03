# Independent review — GR-1D manual reconciliation extraction

Prepared: 2026-08-03 by Codex.

Review base: `40af55c`
Implementation: `dce5e23`
Implementation handoffs: `d5ff75b`, `88b06f8`
Merge: `711095c` (PR #120)
Review branch: `codex/review-pr120-pr121-20260803`
Review report: the commit containing this file

## Commit dispositions

| Commit | Scope | Disposition |
|---|---|---|
| `dce5e23` | Move `reconcile_submission()` into `execution_kernel/reconcile.py` behind call-time `ReconciliationDeps`; add characterization and structural guards | Accepted; no code correction required |
| `d5ff75b` | Record the implemented GR-1D state and validation in the canonical handoff | Accepted as accurate at commit time |
| `88b06f8` | Record the authorized branch push and correct earlier local-only wording | Accepted as accurate at commit time |
| `711095c` | Merge PR #120 into `main` | Accepted; merge tree is byte-identical to topic tip `88b06f8` |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| GR1DREV-001 | P3 | Resolved | `711095c` | `docs/ACTION_PLAN_2026-08-02.md`, `docs/GENERAL_READINESS_STATUS.md`, `docs/ARCHITECTURE_DEBT.md`, `docs/SESSION_HANDOFF.md` | After PR #120 merged and this review completed, the durable records still described GR-1D as unmerged and awaiting review. A new session would repeat completed review work instead of performing the required GR-1E assessment. | Git places PR #120 at `711095c`, while the pre-review records named pushed topic commit `dce5e23` as active and unreviewed. | The action plan and handoff are the sequencing and cross-computer authorities; completed review state must be recorded before handoff. | Mark GR-1D merged and independently reviewed, add the completed milestone record, and make GR-1E assessment the next kernel action. | Final document cross-check, commit inventory, and handoff resume instructions on the review branch. |

No P0, P1, or P2 issue was found, and no issue remains open.

## Contract and safety review

The extracted function preserves the historical order: read the proposal,
atomically claim only `submitting`/`submission_unknown` into `reconciling`,
then import the broker inside the protected block. It continues to distinguish
an order dict, broker-confirmed aged absence (`None`), and an unconfirmed
lookup sentinel. Fresh broker absence retains the execution reservation and
restores the original `updated_at`; only aged confirmed absence calls the
storage-level atomic failure-and-release transition. A same-key intent
mismatch returns to `submission_unknown`, retains the reservation, and
activates the persistent kill switch. Replacement-chain resolution and broker
order journaling remain in their established helpers, and every unexpected
local failure attempts to restore a retryable unresolved state rather than
claiming broker-confirmed failure.

The frozen 13-field dependency object is constructed inside the facade on
every call. The kernel body reads no module-global runtime collaborator; the
exception class used for both raising and catching, status constants, clock,
deferred broker provider, intent parser, lookup/match/chain/absence helpers,
and journal function all resolve through the facade's current namespace.
`AssistantStore` still owns the atomic claim and conditional transitions. The
facade retains its public imports and exact kernel object identities. This is
an internal decomposition only: it adds no execution path, trading authority,
policy change, broker retry, or reservation-release condition.

## Verification and conclusion

PR #120's merge result was checked with `git diff --exit-code 88b06f8
711095c` and is exact. Focused reconciliation validation passed **119 tests
in 33.46 seconds** across execution characterization, absence-age,
replacement-chain, and stranded-claim recovery suites. Independent reverse
mutations were detected: bypassing the facade's injected lookup changed the
grace path and failed the seam test; suppressing persistent kill-switch
activation on a direct mismatch failed the safety assertion. Both mutations
were restored before final validation.

On the corrected combined review tree, `compileall` and `git diff --check`
were clean, and the full isolated suite passed **2,485 tests, 1 skipped, 25
warnings in 512.22 seconds**. The warnings are the same third-party
`websockets` and `joblib` deprecations seen in earlier baselines.

Final disposition: **accepted, 9.5/10**. The implementation is unusually
disciplined for a state-machine extraction: it enumerated the facade seams
before moving code, preserved the exception and deferred-import behavior, left
atomicity in storage, added behavioral plus structural guards, and supplied
load-bearing mutation evidence. The remaining limitation is not a GR-1D bug:
`execution_service.py` is still 952 lines and retains the 281-line execution
composition plus recovery wrappers. GR-1E must now assess that residue before
GR-1 is called complete; GR-2 must not begin merely because GR-1D passed.
