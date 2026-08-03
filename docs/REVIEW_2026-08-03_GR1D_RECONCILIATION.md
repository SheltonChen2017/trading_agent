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

## Third-round confirmation (Claude, 2026-08-03)

Every review claim was independently re-verified before acceptance, per
`docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`, on the exact commits named.

### Commit dispositions (GR-1D scope, range `88b06f8..b1c9ecd`)

| Commit | Scope | Disposition |
|---|---|---|
| `711095c` | Merge PR #120 | Accepted: merge tree independently verified byte-identical to topic tip `88b06f8` (`git diff --stat` empty) |
| `2f37210` | GR-1D review report | Accepted, no issue: dispositions, contract walk-through, and evidence claims all verified |
| `478e531` | Durable-record corrections (GR1DREV-001) + milestone-record entries | Accepted: both new FEATURE_MILESTONE_RECORD entries verified accurate against the implemented behavior, including the honest "GR-1 remains partial until GR-1E" framing |
| `e99737f` / `b495b34` / `b2149a6` | Replacement handoff, push-state record, concurrent-branch note | Accepted: the replacement handoff closed the one gap this confirmation had independently found (see below) before it needed filing |
| `6d3603d` / `5a6ffd5` | Residual-signals review and merge (PR #121/#122 content) | Out of this confirmation's scope — different workstream; verified only that it changes no execution-path file |
| `b1c9ecd` | Merge PR #122 | Accepted: tree byte-identical to `b2149a6` |

### Verification evidence

- **Merge-identity claims reproduced**: `88b06f8` ≡ `711095c` and `b2149a6`
  ≡ `b1c9ecd`, both verified with empty diffs.
- **No code correction confirmed**: the entire review chain changes zero
  files under `assistant/`, `risk/`, `execution/`, or the execution
  characterization suite; the review's code edits are confined to the
  PR #121 signals workstream.
- **Independent full suite on the review tree** (code byte-identical to
  merged `main`): **2,485 passed, 1 skipped, 25 warnings in 432.41s**
  (Python 3.13.14), reproducing the review's reported count exactly. The
  handoff commits landed mid-run but are markdown-only and not test
  inputs; no Python file changed during the run.
- **One gap found and self-resolved**: at review-report time (`478e531`)
  the canonical `docs/SESSION_HANDOFF.md` still described GR-1D as
  awaiting review in five places — the same staleness class as
  GR1DREV-001, in the one file the process doc makes mandatory. Codex's
  own `e99737f` replacement handoff fixed it minutes later, before this
  confirmation could file it; recorded here as observed-and-resolved, not
  as an open issue.
- **Shared-worktree race, both sides correct**: this confirmation briefly
  created `user/claude/gr-1d-review-confirmation-20260803` while Codex was
  still preparing the handoff; Claude backed out and deleted the branch,
  Codex detected the switch before staging and recorded a caution note in
  `b2149a6`. That branch no longer exists (deleted with no unique
  commits during the owner-requested cleanup); the caution note is
  resolved.

### Assessment of the review

**9.5/10, symmetric with its own verdict.** The review independently
re-walked every reconciliation contract, verified the merge trees, ran its
own reverse-mutations on the two spots the implementation had flagged as
worth challenging (facade-seam bypass and the direct-mismatch kill switch),
found the correct result — nothing to fix in the code — and resisted the
temptation to invent findings. The half-point is the initially stale
canonical handoff, self-corrected within the same session.

GR-1D is complete and merged. The exact next kernel action is the **GR-1E
assessment** (compare the remaining 281-line execution composition and
recovery wrappers against GR-1's thin-composition definition of done);
GR-2 must not start on GR-1D's momentum.
