# Guidance Revision Drift - lane implementation record

Status: **Section 19 (Codex counter-review of section 18, per-frame native
account checkpoint and the owner-approval closure) independently reviewed by
Claude in section 20 (2026-10-09): all three commits accepted, one lane test
pin added, one P2 pre-launch packaging risk documented, no production defect.
Codex counter-review of section 20 pending.
Under section 19.6 a synthetic-only order-based QuantConnect evaluation may
start only after that counter-review accepts this review. Native LEAN/QC
execution and empirical backtest readiness remain unverified/blocked. The
original economic, data, empirical, account and trading gates remain closed.**
Current scope/evidence are sections 17 through 20. Sections 2 through 6 preserve
the initial GDR-0A snapshot and its then-current restrictions; section 7
supersedes only its stop-for-review and no-push sequencing for this batch, and
section 12 records the owner's 2026-10-07 application of the standing lane
review workflow (same branch and worktree, lane-record-only findings, one push
per review round) to this lane.
The owner requested a distinct development lane and the start of
implementation on 2026-10-06. This record defines the first bounded scope;
it does not mark GDR-0 complete or adopt a research/trading mandate.

## 1. Worktree, branch and document authority

- Dedicated absolute worktree:
  `/Users/sheltonchen/.codex/worktrees/guidance-revision-drift/trading_agent`.
- Long-lived implementation branch: `codex/strategy-guidance-revision-drift`.
  All lane repository commands, edits, validation and commits run here.
  Do not return to the older planning checkout or a sibling lane for work.
  Verify root, branch and status before each commit and any authorized push.
- Freshly fetched `origin/main` base:
  `ff0bb2098d1a06184d41bf1dcc1bb113aaac2174`.
- Planning deliverable imported as `cc614d33`, cherry-picking only original
  design commit `4b8447ed829d3e7cb6a724070dcf130dbecbea68` onto that base.
  The older planning branch's handoff was not copied over current-main state.
- Original immutable design source:
  `docs/Plan/GUIDANCE_REVISION_DRIFT_RESEARCH_PLAN_2026-10-06.md`, SHA-256
  `26478c3ba90a60bb321f664eaa0f1afb163883bedba06fb9a03345e8d60dfe11`.
- Original PDF:
  `output/pdf/GUIDANCE_REVISION_DRIFT_RESEARCH_PLAN_2026-10-06.pdf`, SHA-256
  `f8d7855b076eb064c45089020d277b2f96f00405477b19b1610a7f3aaf42af70`.
  Its queued/no-implementation wording records the earlier design-delivery
  state. This record and `docs/ACTION_PLAN_2026-08-20.md` supply the subsequent
  bounded implementation status; numeric assumptions remain proposals.
- `CLAUDE.md` and `AGENTS.md` still govern. The Action Plan owns sequencing;
  the explicit 2026-10-07 owner decision in section 17 supersedes the earlier
  generic handoff policy for this lane: both agents update this lane record
  only; root Session Handoff and Action Plan remain frozen. The same existing
  lane branch/worktree and one combined push per round apply.

The four existing branches/worktrees are not modified. A fifth development
folder does not create a fifth statistical allocation in their fixed family.

## 2. GDR-0A scope and definition of done

This is the offline, implementation-preparation part of GDR-0, not GDR-1's
provider audit or GDR-2's executable strategy/simulator. Its bounded candidate
must provide all of the following:

1. One machine-readable inventory of the proposed plan settings, exact
   source hashes, unresolved approvals and zero external authorities.
2. Strict malformed/duplicate/type/semantic mutation refusal, stable
   canonical identity and immutable loaded state.
3. A local inspection/preflight command which validates the proposal but
   cannot promote any gate or call any external system.
4. Pure exact-decimal range arithmetic verifying the proposed formulas with
   synthetic fixtures, without asserting event comparability or tradeability.
5. Relevant focused behavioral, dangerous-direction, import-boundary,
   compilation and document-consistency checks, then a stable committed
   snapshot for independent review.

Independent acceptance and the owner's exact parameter/research freeze
remain necessary for GDR-0 completion. There is no milestone-record completion
entry while they remain absent. GDR-1 and later milestones do not start merely
because this preparation is implemented.

## 3. Implementation surface and semantics

New lane package: `research/guidance_revision_drift/`.

- `specs/gdr0a.draft.json`: the sole proposed parameter inventory, with
  `status=draft_unreviewed`; all eleven unresolved decisions remain null.
  Canonical UTF-8 JSON SHA-256, without final LF:
  `b52aedd6ca6dea4a14bc46ddb6c09a6d36bbf994fc21edb9ddb916194f03ad3c`.
- `contracts.py`: bounded UTF-8 JSON decoding, duplicate-key and numeric-float
  refusal, exact pinned semantic identity, immutable canonical bytes and
  fresh decoded projections. Unknown/missing fields, changed values/types,
  rehashed approvals, nonzero look allowances and sibling permissions refuse.
  Hashes prove consistency only, not authenticity, approval or availability.
  Input readers cap JSON at 64 KiB and each planning source at 1 MiB, refuse
  symlink/nonregular leaf files, and recheck opened descriptor identity,
  size and type before a bounded read.
- `readiness.py`: a pure read-only projection; all external permissions stay
  false, permitted research looks stay zero, and every unresolved decision
  is listed. No caller-provided review/PIT/permission flag is accepted.
- `formulas.py`: frozen finite Decimal ranges, bounded coefficient/exponent,
  exact midpoint and cross-multiplied comparisons. Thresholds are proposed
  revenue 0.02, EPS 0.05 and prior EPS midpoint 0.25. Ratios are deterministic
  display projections only, never acceptance operands. Equal endpoints are
  arithmetic inputs, not proof that the source published point guidance.
- `__main__.py`: `show-candidate` exits 0 for a valid inspection, `preflight`
  exits 2 with `blocked`, and invalid contract/source files exit 1. No
  download, capture, backtest, provider, broker or order command exists.

Reused unchanged product-neutral modules are `data.hashing` and
`data.financial_primitives`. No sibling lane, ML, assistant, risk or execution
package is imported. New LF attributes apply only to this package and the
one hashed Markdown source. No shared behavior or dependency was modified.

There is no provider normalizer, point-in-time event qualification, production
signal, universe builder, calendar evaluator, portfolio/order simulator, QC
adapter, research-look persistence, dataset download, migration or execution
integration in this milestone. `passes_arithmetic` means only that numeric
conditions matched; it cannot establish any of those missing stages.

## 4. Evidence, authority and unresolved decisions

No private source data or prices have been read. Research looks consumed: 0.
QC attempts: 0. No capture, provider API, cloud upload/processing, outcome
study, scheduler, operator database, broker, paper/live order or capital use
is authorized or performed. Presence of credentials or sibling permissions
is irrelevant to this candidate.

Unresolved: owner parameter freeze; independent specification review;
source rights/availability; historical identity/terminal outcomes; statistical
family and allocation; permitted looks; evidence windows; power/final-look
rule; exact engine/fee/settlement contract; immutable source/code epoch.
There is no inherited 0.0125 allocation. All outcomes remain closed; the
proposal quarantines 2026-09-01 onward and does not borrow the four-lane
2027-09-01 through 2029-08-31 final holdout.

Before an eventual authorized backtest, use order-based QC validation and
the maximum-three-unsuccessful-attempt/Mia rule in the owner instructions.
It is not possible to test cloud completion while its authorization and data
gates are closed; no attempt is consumed by local arithmetic tests.

## 5. Validation and review status

Focused validation uses bundled Python 3.12.14 on macOS. Synthetic tests
establish behavior, not alpha. Advisory subagent feedback is author QA, not
the repository's independent Claude review.

| Check | Result |
|---|---|
| `test_contracts.py` | 27 passed, including malformed input, semantic mutations, file-type/size/race bounds and legacy-reader mutation detection |
| `test_readiness.py` | 11 passed, including all CLI exits and zero authority |
| `test_formulas.py` | 15 passed, including just-below-threshold rounding and hostile Decimal contexts |
| `test_boundaries.py` | 6 passed, including transitive imports, observed read-only files and active document references |
| Total focused assertions | 59 tests passed; 0 failed, 0 skipped, no warnings emitted |
| Compilation | `python -m compileall -q research/guidance_revision_drift tests/guidance_revision_drift` passed |
| Source identity | Original Markdown/PDF hashes verified; scoped LF/binary attributes verified |
| Diff | `git diff --check` and `git diff --cached --check` passed |

Author-QA issue ledger (not independent review):

| ID | Priority | Status | Finding, correction and verification |
|---|---|---|---|
| GDR-QA-001 | P2 | Corrected before first implementation commit | Initial planning-source reads were unbounded and input readers could open a FIFO. Corrupt local inputs could exhaust memory or hang inspection instead of refusing. One lane-local bounded regular-file reader now covers candidate and both sources, with descriptor revalidation/closure. Eight new tests cover upfront refusals, descriptor replacement, post-stat growth and a mocked legacy-reader regression; all pass. |

No known open author-QA finding remains in this bounded surface. This is not
an independent acceptance verdict. Windows execution, provider availability,
real event semantics, order simulation and QC completion remain untested.

No complete lane or repository suite is authorized. The new tests are
`unittest.TestCase` modules and are also pytest-discoverable. Focused unittest
invocations avoid importing the repository pytest conftest's operator-runtime
fixtures because these modules require no operator state; the existing guards
are not changed or disabled. Existing pytest checks require the application's
pinned runtime dependencies, unlike the stdlib-only GDR components.

System Python 3.9 was rejected by an initial arithmetic-test collection
(`typing.TypeAlias` is unavailable in that interpreter); no strategy test ran
in that attempt. Subsequent checks use bundled Python 3.12.14, consistent with
the repository's Python 3.12+ requirement. No dependency was installed or
changed to make the new lane run.

## 6. Next bounded action and handoff

Local committed snapshot:

| Commit | Scope | Independent disposition |
|---|---|---|
| `cc614d33042caac9a463a3df95c8f7ead70358f9` | Import original Markdown/PDF proposal and index | Pending review |
| `9775e284d2ed9b785fb173b2aaf52affb29efb4c` | Offline GDR-0A candidate, tests, status and author-QA correction | Pending review |

The implementation range is
`ff0bb2098d1a06184d41bf1dcc1bb113aaac2174..9775e284d2ed9b785fb173b2aaf52affb29efb4c`;
the following documentation-only handoff commit must also be included in any
eventual exact-snapshot review. All are local-only: no push, PR or merge, and
another computer cannot retrieve this new lane with `git fetch`. All changes
are committed in this dedicated lane; no unrelated dirty work was present.

After the GDR-0A candidate is committed, stop for owner-directed publication
and independent review of that exact snapshot. No push or PR is authorized
by the present request. Resolve and freeze the outstanding GDR-0 decisions
before a production/source/outcome milestone. Future implementation remains
in this worktree and branch; reviewer topology follows the generic workflow
unless the owner explicitly changes it for Guidance Revision Drift.

Copyable resume prompt:

> Work only in /Users/sheltonchen/.codex/worktrees/guidance-revision-drift/trading_agent
> on codex/strategy-guidance-revision-drift. Read CLAUDE.md, AGENTS.md, the
> current Action Plan, this lane record, the original GDR plan and Session
> Handoff. Verify root/branch/HEAD/status. GDR-0A is an offline unreviewed
> candidate, not accepted data/QC/trading authority. Continue only the owner's
> exact next scope; preserve sibling lanes and protected evidence.

## 7. Owner-authorized six-increment engineering batch, 2026-10-07

The owner explicitly accepted six **code-only** increments, using the proposed
parameters, without provider-data access, QC jobs, or paper/live accounts.
Several local commits are allowed; exactly one push occurs at the end. Claude
reviews the exact final pushed snapshot. This is a scoped override of the
one-milestone-before-review sequencing, not a statistical allocation, source
audit, parameter acceptance, or completion of original GDR-1 through GDR-6.

| Increment | Implementation deliverable and focused verification |
|---|---|
| ENG-1 | Strict synthetic guidance normalization, immutable version/receipt archive; malformed/type/duplicate/tamper checks |
| ENG-2 | Comparable predecessors, economic identity and event lifecycle; bootstrap/edit/duplicate/conflict/correction/withdrawal tests |
| ENG-3 | Explicit synthetic session schedule, cutoff/expiry timing, dated security eligibility and exact deterministic ranking; calendar/availability/universe boundary tests |
| ENG-4 | Incremental order-based synthetic portfolio with reservations, fills, fees, settlement, exits and corporate actions; accounting and adverse-path fixtures |
| ENG-5 | Offline QuantConnect data-boundary adapter and synthetic integration; no cloud-executable deployment or SDK/cloud parity claim |
| ENG-6 | Synthetic lineage/run ledger, closed research-access controls, immutable local artifacts, comparator/report diagnostics and end-to-end review package |

All are implementation candidates until independent review. Fixtures are
invented, not licensed market observations, and never claim point-in-time
provenance or market edge. The original Markdown/PDF and GDR-0A proposal/hash
remain unchanged. No shared behavior, sibling record, operator state,
credential, research registry, scheduler or execution integration is touched.
The one permitted publication targets only this existing branch from this
exact worktree; no PR, merge or additional branch is authorized.

## 8. Implemented batch and definition-of-done assessment

All six **engineering** deliverables in section 7 are implemented and locally
checked, but are not independently accepted milestones. No completion entry
has been added to `docs/FEATURE_MILESTONE_RECORD.md`. These deliverables neither
complete the original GDR research stages nor change the eleven unresolved
GDR-0 decisions. Numeric settings are still proposals. Production research,
provider/PIT evidence, cloud completion and trading readiness are unproven.

- ENG-1/2: strict `gdr.synthetic.disclosure.v1` normalization and immutable
  `gdr.synthetic.archive.v1` chain, with separately retained expected-head
  verification. Replay distinguishes bootstrap, duplicates, metadata edits,
  comparable same-FY raises, conflicting versions, corrections and
  withdrawals. Risk invalidation is separate from positive-entry eligibility.
- ENG-3: explicit session schedule/hash; New York cutoff and D+3/E+2 timing;
  dated stock mapping, listing history, raw price/ADV eligibility and exact
  rational ranking. `assessment.py` composes event visibility, cutoff slicing
  and universe checks; future revisions cannot change an earlier result.
  `fixtures.py` supplies only a built-in invented 2025 corpus and schedule.
- ENG-4: atomic in-memory order transitions; quote-side fills with proposed
  base/stress impact and order-level commission floors; share/dollar capacity;
  current-quote NAV sizing, cash reservations, partial fills and explicit
  cancellation acknowledgment; settlement receivables; risk/time/trim exits;
  whole-share splits, dividends, and explicit terminal proceeds or unresolved
  state. Snapshots expose orders, fills, cash movements and corporate actions.
  This engine is not connected to the application's proposal/execution roots.
- ENG-5: `qc_adapter.py` accepts paired, non-fill-forward raw quote/trade
  snapshots with explicit UTC and dated synthetic security bindings. It
  deduplicates callbacks and drives the local simulator. It is **not** a
  cloud-executable `QCAlgorithm`, licensed source bridge, LEAN compilation or
  accepted QC fill model. Engine/project/backtest bindings remain null.
- ENG-6: exact source/candidate/calendar/code fixture epochs, separate
  base/stress start/terminal receipts, unconditional external-access refusal,
  bounded content-addressed local report publication, actual-fill-matched
  SYN-SPY order/tranche accounting, complete paired daily NAV diagnostics and
  the runnable built-in `synthetic-demo` command. `adapter-manifest` is also
  read-only. All commands verify the original candidate and design-source
  hashes. `preflight` still exits 2 / blocked; a successful demo exits 0 for
  local software completion only, never research approval.

The economic scope and CLI/storage details are in the package README. Only
lane code/tests, that README and the necessary associated/coordination records
changed. No dependency, shared application behavior, sibling record, database,
runtime fence, credentials, scheduler or operational artifact was changed.
The existing neutral decimal/hash helpers were reused without modification.

Important bounded limitations:

1. Fixtures are invented. No vendor decoder, source audit, actual permanent-ID
   history, audited exchange calendar or historical terminal coverage exists.
   The 93-session example is not a claim that the real NYSE calendar was audited.
2. The simulator is an in-memory engineering model, not durable broker
   restart/reconciliation. Terminal actions assert synthetic terminality;
   ordinary cancellation requests never stand in for acknowledgment.
3. Fractional split/cash-in-lieu and noncash merger conversions refuse.
   Comparator corporate actions are not supported. Generic comparator inputs
   assert synthetic source fills, not externally verified executions.
4. The comparator retains permanent timing/funding/underfill/valuation gaps;
   it does not conceal them by topping up or dropping dates. Whole-share
   residual cash is explicit. Pure report arithmetic requires an explicit
   expected calendar, not inferred weekdays. No confidence interval, power,
   allocation, multiplicity test or empirical acceptance is produced.
5. Archive and ledger hashes establish consistency, not authenticity or
   anti-rollback authority. The ledger is exported with a completed report,
   not a crash-recoverable global research registry. No real research look can
   be started. A failure before report publication has no durable run receipt.
6. Local artifact publication is atomic/no-overwrite within an owner-controlled
   directory, with a flushed staging file. It is not adversarial directory
   isolation or guaranteed power-loss durability (no directory fsync). The
   publisher is capped at 64 KiB; the separate in-memory archive supports up to
   256 observations / 8 MiB, so larger archives need a later storage contract.
7. All provider/outcome/QC gates stay closed, including pre-2026 dates. The
   protected 2026-09-01 onward windows and the other lanes' statistical family
   are untouched. The maximum-three-unsuccessful-QC-attempt/Mia rule is exposed
   as a refusal/recovery disposition, not a launch permission. QC attempts: 0.

Official [US-equity data documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/handling-data)
and [fill-model concepts](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts)
were checked on 2026-10-07 for field/interface concepts. This public-document
check used no provider data and establishes no SDK/cloud parity. An actual
order-based QC completion must be proved later, only after its gates open.

## 9. Final focused validation and reproducible fixture receipt

Runtime: macOS, bundled Python 3.12.14 at
`/Users/sheltonchen/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`.
Each selected test module was run explicitly with
`-m unittest discover -s tests/guidance_revision_drift -p <module> -q`
(some earlier final checks used `-v`). The table records final relevant runs,
not a full lane/repository suite. No normal pytest isolation guard was bypassed;
these lane-local stdlib tests require no operator state. Existing application
pytest tests/full suites were not run. No runtime/dependency was installed.

| Focused module | Passed | Final observed duration |
|---|---:|---:|
| `test_events.py` | 34 | 0.729 s |
| `test_archive.py` | 14 | 0.270 s |
| `test_timing.py` | 13 | 0.008 s |
| `test_universe.py` | 12 | 0.254 s |
| `test_assessment.py` | 5 | 0.349 s |
| `test_simulation.py` | 41 | 0.144 s |
| `test_comparison.py` | 19 | 0.024 s |
| `test_qc_adapter.py` | 7 | 0.003 s |
| `test_controls.py` | 8 | 0.116 s |
| `test_artifacts.py` | 6 | 0.015 s |
| `test_reporting.py` | 8 | 0.008 s |
| `test_scenario.py` | 7 | 3.456 s |
| `test_readiness.py` | 11 | 0.052 s |
| `test_boundaries.py` | 6 | Rechecked after final documentation |
| Total selected tests | **191** | 0 failures/errors/skips; no warnings emitted |

Compilation: `python -m compileall -q research/guidance_revision_drift
tests/guidance_revision_drift` passed. Fresh-process imports include every new
module; transitive AST checks permit only stdlib/lane/neutral primitives. Active
lane documentation references and the root handoff size limit are checked by
`test_boundaries.py`. Original Markdown/PDF and candidate identities remain
unchanged. Working/staged diff checks passed. Neither Windows behavior nor
LEAN/QC execution was tested. Full independent lane validation belongs to Claude.

An initial artifact-test assertion compared macOS `/var` and `/private/var`
spellings rather than canonical paths; the assertion now resolves the expected
directory. No product behavior was relaxed. Deliberate mutation failures below
are sensitivity evidence, not failures in the restored final implementation.
The 59-check table in section 5 is the historical GDR-0A run, not 59 additional
tests claimed for this batch. The unchanged contract/formula modules were not
rerun as a complete lane suite.

`python -B -m research.guidance_revision_drift synthetic-demo` produces a
deterministic 22,056-byte canonical JSON report before the CLI's trailing LF.
Both base and stress complete 2 strategy fills, 2 comparator fills, 93 paired
daily observations and final settlement; their local completion/parity blocker
flags are false. This is a software fixture result, not a market-return result.
No example report file is required to resume; it is reproducible from source.

| Identity | SHA-256 |
|---|---|
| Canonical report | `b51d2ef2371464aeb92cb427aad1c209dcd1e7fdfebf3a6047fef6bb977e0a7a` |
| Fixture epoch | `f9fa3d8000f5155293e34bfd92cca034a13beef57dab79dcfae4031fce29451d` |
| Actual lane/neutral code-file manifest | `feb4a5ebeb19869ef6ad4fad2fe9f13ab704a93d728c25e2afb00fa80cfa9603` |
| Invented corpus | `a707af71604122b9c8d61f7f1772f3d346659b1786880c8485c84c81d9b4a320` |
| Explicit schedule | `b3fa4cbf9be8dccf3b8ad4287b651c2bbee64004be80575bd79591614d5322f3` |
| Receipt ledger | `4d8b47f47a3ac13a8dce2160cf2aa50d8a16a9e18968158916201ff4699de22f` |

## 10. Retained author-QA finding ledger

These are verified issues corrected **before the relevant initial batch
commits**, not Claude findings or independent acceptance. Locations are relative
to the lane package; named regressions are in its matching test module. No known
open defect remains in this bounded author-QA scope; exclusions/gates above are
not silently treated as verified functionality. GDR-QA-001 remains in section 5.

| ID | Priority/status | Commit/location | Issue, required correction and verification |
|---|---|---|---|
| GDR-QA-002 | P2 / corrected | `40003585`, `events.py::_replay` | An incompatible new-entry predecessor could suppress a comparable cut to a held candidate. Risk checks now operate independently on the held candidate's economics. `test_incomparable_entry_predecessor_does_not_suppress_comparable_risk_cut` passes. |
| GDR-QA-003 | P2 / corrected | `40003585`, `events.py::_replay` | Nearest-FY entry selection could hide a cut to the older held FY. Risk checks inspect each active candidate's own fiscal period. `test_fiscal_year_rollover_does_not_suppress_old_period_risk_cut` passes. |
| GDR-QA-004 | P2 / corrected | `40003585`, `events.py::_replay` | Different IDs at one issuer/publication instant left ambiguous positive authority. Replay quarantines the issuer and invalidates the first candidate; simultaneous-disclosure regression passes. |
| GDR-QA-005 | P2 / corrected | `40003585`, `events.py::_nearest` | UTC date could expire a fiscal period while the New York announcement date was still valid. NY-date regression passes. |
| GDR-QA-006 | P2 / corrected | `40003585`, `events.py::EventDecision`, `archive.py` | Mutable decision fields/unbound candidate objects and constructor-only duplicate archives weakened immutable/replay consistency. Revalidate/copy/source-bind decisions and reject duplicate archive payloads. Decision mutation, direct constructor duplicate and re-chained duplicate regressions pass. |
| GDR-QA-007 | P2 / corrected | `40003585`, `events.py::_replay` | Apr-1 raise captured Apr-3 followed by an Apr-2 cut captured later Apr-3 did not invalidate the raise, because entry-only prepublication capture also gated risk reduction. Economic comparability now stands alone for later cuts. Delayed-receipt regression passes; restoring the old gate in memory produced one expected failure, then passed after restoration. |
| GDR-QA-008 | P2 / corrected | `1fb696d3`, `timing.py::availability_refusals` | Publication exactly at cutoff was accepted despite the strict-before rule. Publication is now strict; receipt/ingestion equality remains valid. Boundary test passes and detects an in-memory removal of the publication refusal. |
| GDR-QA-009 | P2 / corrected | `1fb696d3`, `assessment.py` | Future bar/mapping revisions could turn an earlier passing assessment into a duplicate/ambiguous-history refusal. Known future observations are filtered before universe selection. Future-revision invariance regression passes and fails when filtering is replaced in memory with always-visible. |
| GDR-QA-010 | P2 / corrected | `bcfdb02a`, `simulation.py` | Filled trims retained their original scheduled quantity and could cause repeated sales. Actual fills now decrement/remove due quantities. Trim-completion/partial-exit tests pass. |
| GDR-QA-011 | P2 / corrected | `bcfdb02a`, `simulation.py` | Invalidation before the first fill did not liquidate a cancellation-racing fill. Bind invalidation to the affected entry order; preserve independent later events. Both racing-fill and unrelated-later-event regressions pass. |
| GDR-QA-012 | P2 / corrected | `bcfdb02a`, `simulation.py` | Cancellation acknowledgment lacked proof of a request and required idempotency after a racing full fill. Explicit request/ack tracking now governs reserve release; unrequested ack and full/partial racing-fill regressions pass. |
| GDR-QA-013 | P2 / corrected | `bcfdb02a`, `simulation.py` | Tiny legitimate sells were refused when fees exceeded proceeds. Pay the shortfall from settled cash and use a zero rather than negative receivable; tiny-exit regression passes. |
| GDR-QA-014 | P2 / corrected | `bcfdb02a`, `simulation.py` | Carried exits could fill on a refreshed decision minute through an old timestamp. Reset `execution_after` for each new opportunity; daily-dollar-cap/price-gap test rejects the new 10:00 decision bar. |
| GDR-QA-015 | P2 / corrected | `bcfdb02a`, `simulation.py` | Missing quotes did not preserve consumed entry opportunities; new entries also sized held exposure from stale prior-close marks. Record a `missing_quote` refusal/attempt and require all fresh current portfolio quotes. Both targeted regressions pass. |
| GDR-QA-016 | P2 / corrected | `bcfdb02a`, `simulation.py` | Unknown terminal economics could regain a valid NAV via later marks, and an unfilled terminated identity could reopen. Preserve unresolved terminal marks, cancel pending terminal entries and permanently close that issuer identity. Terminal regressions pass. |
| GDR-QA-017 | P2 / corrected | `bcfdb02a`, `simulation.py`, `comparison.py` | Historical missing NAV/calendar rows could stop blocking completion after liquidation/settlement. Retain permanent missing-session/valuation blockers on both sleeves. Post-liquidation regressions pass. |
| GDR-QA-018 | P2 / corrected | `bcfdb02a`, `simulation.py::_exit` | An old 22-share remaining trim constrained a new 48-share full stop. Explicit open-order amendment preserves fills/cumulative fee and raises the remaining quantity; pending cancellations still require reconciliation. Both regressions pass. In-memory restoration of the old cap produced one expected failure, followed by restored green. |
| GDR-QA-019 | P2 / corrected | `78914637`, `qc_adapter.py` | Caller mutation of a retained security binding could redirect future data. Clone/revalidate bindings. Mutation regression detects restored aliasing in memory (empty-fill/index error), then passes after restoration. |
| GDR-QA-020 | P2 / corrected | `dc474392`, `reporting.py` | A wholly omitted calendar row could be treated as one daily interval. Require exact equality with explicit expected session dates before diagnostics. Omitted-date regression passes and detects an in-memory bypass. |
| GDR-QA-021 | P3 / corrected | `40003585`, `test_events.py` | Malformed-range fixtures accidentally exercised only endpoint type rejection. They now mutate the intended range object; intended inverted/nonfinite/unbounded/implicit-point paths are tested. |
| GDR-QA-022 | P2 / corrected | `bcfdb02a`, `simulation.py::snapshot` | Settled receivables/actions disappeared from the exposed view, weakening audit reconciliation. Persistent cash movements/action journal now retain them; cash-journal reconciliation regression passes. |

Mutation experiments were in-memory, automatically restored, and made no
repository edits. Other fixes have targeted behavioral coverage but were not
all separately mutation-tested. Internal peer feedback remains author QA.

## 11. Exact review range, publication and next action

This round starts at `ab15d5a19db39912178f1efd77bf68c2a1f23a84`; its final code
head is `dc4743923f9890a6682dade4a5f3d6c23e8805a6`. The initial proposal/GDR-0A
commits were never independently accepted, so Claude must review the entire
range from base `ff0bb2098d1a06184d41bf1dcc1bb113aaac2174` through the exact
final fetched remote head, including the associated-record and root-handoff
commits following this code head. Review every commit, not only the combined
diff; do not accept author-QA dispositions as an independent verdict.

| Commit | Scope | Independent disposition |
|---|---|---|
| `cc614d33042caac9a463a3df95c8f7ead70358f9` | Original Markdown/PDF proposal and index | Pending Claude review |
| `9775e284d2ed9b785fb173b2aaf52affb29efb4c` | GDR-0A contracts, exact arithmetic and blocked readiness | Pending Claude review |
| `ab15d5a19db39912178f1efd77bf68c2a1f23a84` | Initial dedicated-lane root handoff | Pending Claude review |
| `400035856de49330a5765e1583c6abb5664eb37b` | ENG-1/2 normalization, archive and event lifecycle | Pending Claude review |
| `1fb696d37cb32b258b1ccc67efaebc3de5d4bf28` | ENG-3 timing, eligibility, as-of composition and invented corpus | Pending Claude review |
| `bcfdb02a1c674b3d363a5c9b553888fb170f21d6` | ENG-4 simulation plus ENG-6 comparator dependency | Pending Claude review |
| `78914637972ab2828e936fe731cb952a606c4016` | ENG-5 adapter plus ENG-6 closed controls/ledger dependency | Pending Claude review |
| `dc4743923f9890a6682dade4a5f3d6c23e8805a6` | ENG-6 integration/report/artifact CLI, tests and package README | Pending Claude review |
| This associated-record commit | Scope/status, findings and validation ledger; Action Plan/index update | Pending Claude review; resolve exact hash from ordered log |
| Following root-handoff commit | Final cross-computer resume pointer | Pending Claude review; resolve exact hash from final remote head |

Publication protocol: one authorized non-force push from this exact worktree,
targeting only `origin` branch `codex/strategy-guidance-revision-drift`, after
all product, record and root-handoff commits. This record is prepared before
that transaction and does not itself prove remote availability. Until the
remote ref contains the handoff commit, the batch is local-only and cannot be
retrieved on another machine. The final owner response reports the verified
remote head. No PR or merge, alternate worktree/branch, provider/QC job or
additional milestone is part of this publication.

Next: owner-directed Claude independent review of that exact pushed snapshot,
including the full lane suite and commit-by-commit P0-P3 ledger. This lane has
not inherited the other strategies' same-branch-review exception; use the
governing generic topology unless the owner explicitly changes it. Keep Codex
implementation in its existing designated worktree/branch. After review,
counter-review every Claude commit under the applicable owner workflow before
any further implementation. Shared/main-owned findings must be reported, not
silently fixed in this lane. Do not start original GDR-1 or an empirical run.

Copyable review scope:

> Read CLAUDE.md, AGENTS.md, the Action Plan, this record (current sections
> 7-11), the original GDR plan and Session Handoff section 0E. Fetch the exact
> published codex/strategy-guidance-revision-drift head and enumerate every
> commit from ff0bb2098d1a06184d41bf1dcc1bb113aaac2174 through that head.
> Independently review all eight listed product/history commits and the two
> documentation commits. Run the full lane suite under the repository's
> isolation requirements; retain resolved and open findings and exact per-commit
> dispositions. No data/QC/broker/paper/live/merge authority is granted by this
> review handoff. All fixture success remains non-empirical.

## 12. Independent Claude review of `ff0bb209..8424a2b3`, 2026-10-07

### 12.1 Scope, topology and method

Reviewed range: every commit from base `ff0bb2098d1a06184d41bf1dcc1bb113aaac2174`
through the fetched remote head `8424a2b3` (ten Codex commits, no Claude
commit before this section). The worktree was clean (zero dirty paths) and
equal to `origin/codex/strategy-guidance-revision-drift` at the start.

Owner instruction received in the review session chat on 2026-10-07: this
session is dedicated to this lane and branch; "review all unreviewed commits,
apply corrections where necessary, push once when done." That applies the
owner's standing strategy-lane review workflow (2026-09-06, "any later lane")
to Guidance Revision Drift: Claude reviews and corrects on the same branch and
worktree, records findings only in this lane record, and makes exactly one push
per review round. It supersedes the section 1 and section 11 statements that no
same-branch Claude exception was inferred. Codex counter-reviews every Claude
commit next, under the same workflow.

Method: every commit read individually (`git show`), every lane module and
test module read in full, the record's hashes and counts reproduced, each
suspected gap probed by an in-memory mutant before a finding was written.
Host: macOS, Homebrew Python 3.13.15 in a virtualenv built from the pinned
`requirements.txt`, pytest 9.1.1. Every pytest and mutation process ran
network-denied under `sandbox-exec -p '(version 1)(allow default)(deny network*)'`;
the profile was proved first by a refused connect to 192.0.2.1:443 (EPERM).
All validation ran in the designated worktree except the per-commit
informational runs in 12.4, which used `git archive` exports under the review
scratchpad and are labelled as such. No provider, QC, broker, paper or live
system was contacted; research looks consumed: 0; QC attempts: 0.

### 12.2 Commit dispositions

Vocabulary: accepted / accepted after correction / rejected. Corrections in
this round are tests only; no production module changed, so every hash in
section 9 still reproduces (12.4).

| Commit | Scope | Disposition | Notes |
|---|---|---|---|
| `cc614d33` | Original Markdown/PDF proposal and index | Accepted | Blobs identical to design commit `4b8447ed` (parent `e1a0efe6`, matching the plan's recorded base); Markdown and PDF SHA-256 match the candidate pins |
| `9775e284` | GDR-0A contracts, exact arithmetic, blocked readiness | Accepted | Candidate canonical hash `b52aedd6...` reproduces; 59 tests; mutants M36, M37, M49 caught; shared-file edit noted in GDR-CR12-001 |
| `ab15d5a1` | Initial lane root handoff | Accepted | Documentation only; shared-file edit noted in GDR-CR12-001 |
| `40003585` | ENG-1/2 normalization, archive, event lifecycle | Accepted | Mutants M38-M41, M48 caught, including the GDR-QA-007 delayed-receipt gate; GDR-CR12-010 documented |
| `1fb696d3` | ENG-3 timing, eligibility, as-of composition, corpus | Accepted after correction | One test added for the New York announcement date in `assessment.py` (GDR-CR12-006); M27-M35 caught; GDR-CR12-007 documented |
| `bcfdb02a` | ENG-4 simulation and ENG-6 comparator | Accepted after correction | Ten simulation tests added (GDR-CR12-002/003/004); comparator mutants M43, M44, M55 caught; GDR-CR12-009 documented |
| `78914637` | ENG-5 adapter and ENG-6 controls/ledger | Accepted after correction | One ledger chain-link test added (GDR-CR12-005); M46, M50 caught; GDR-CR12-012 documented |
| `dc474392` | ENG-6 integration, report, artifact CLI, README | Accepted | Report, epoch, manifest, corpus, schedule and ledger hashes reproduce; CLI exit codes 0/2/0/0 as documented |
| `6ca9892a` | Sections 7-11, Action Plan and index update | Accepted | Counts consistent (191 focused plus 59 GDR-0A less 17 shared equals the 233 collected); shared-file edit noted in GDR-CR12-001 |
| `8424a2b3` | Root handoff section 0E | Accepted | Documentation only; shared-file edit noted in GDR-CR12-001; GDR-CR12-008 documented |

### 12.3 Findings ledger

IDs are `GDR-CR12-NNN` (Claude review, section 12). Priorities follow the
repository's P0-P3 scale. "Corrected" means a lane test now fails without the
pinned behaviour; the production behaviour was already correct in every case.
Resolved items stay in this table.

| ID | Priority / status | Location | Finding, disposition and verification |
|---|---|---|---|
| GDR-CR12-001 | P2 / documented, not fixed | `9775e284`, `ab15d5a1`, `6ca9892a`, `8424a2b3`; `docs/ACTION_PLAN_2026-08-20.md`, `docs/SESSION_HANDOFF.md` | Four lane commits edited the two shared coordination documents that `THREE_STRATEGY_PARALLEL_WORKFLOW.md` section 2 and the owner's machine-wide lane rule freeze during parallel strategy development. Section 1 shows this was deliberate: Codex followed the root `CLAUDE.md` handoff rule and declined to infer the lane exception. With the owner's 2026-10-07 instruction the lane workflow now applies, so both files are frozen for this lane from this round on. No revert was made here: a revert would itself edit the frozen files and would remove the Action Plan's owner-directed sequencing entry. Owner to confirm at integration: (a) the 2026-10-06 lane and implementation-start direction cited in the status block; (b) the six code-only increments and single-push authorization in section 7; (c) the Action Plan amendment text dated 2026-10-07; and (d) whether the two shared-file edits stand or are re-applied as one common-baseline amendment. |
| GDR-CR12-002 | P3 / corrected | `bcfdb02a`, `simulation.py::close_session`; `test_simulation.py` | The program-drawdown and position-stop tests used marks far below their thresholds, so the inclusive boundaries were untested: mutants M01 (`<=` to `<`), M02 (0.85 to 0.84), M03 (`<=` to `<`) and M24 (basis `reference_quantity` to current `quantity`) survived the original selection. Added `test_program_drawdown_stop_is_inclusive_at_exactly_fifteen_percent` (ten 50-share fills at 99.0495 and a 69.0695 close give NAV exactly 85,000; 69.0696 must not stop), `test_position_stop_is_inclusive_at_exactly_ninety_percent_of_entry_cost` (90.0450 stops, 90.0451 does not) and `test_position_stop_stays_price_based_after_a_partial_trim` (26 of 49 shares retained after a 23-share trim: 95 must not stop, 90.0450 must). All four mutants now fail; the real code passes. |
| GDR-CR12-003 | P3 / corrected | `bcfdb02a`, `simulation.py::submit_entry`; `test_simulation.py` | Three refusals were asserted only as a `None` return, and in every existing fixture a later check (`missing_current_portfolio_quotes`) refused anyway, so removing the guard was invisible: `exits_must_precede_entries` (M12), `missing_valuation` (M25) and `missing_previous_session_valuation` (M58). Added three tests that supply fresh valuation quotes for the holding and assert the exact refusal reason, including the positive case that the same entry is admitted the next session once the trim has filled and no exit is due. All three mutants now fail. |
| GDR-CR12-004 | P3 / corrected | `bcfdb02a`, `simulation.py::request_cancel`, `_tick`, `process_minute`, `terminal_settlement`; `test_simulation.py` | Reservation and settlement lifecycle gaps: releasing reserves on an explicit `request_cancel` (M14), settling a receivable on a pre-open tick of its pay session (M11), dropping the in-loop 10:05 conversion of an open buy to `cancel_requested` (M52), and crediting a terminal payout to an issuer with only a pending entry (M60; the real code refuses "without a held entitlement", the mutant would raise `KeyError` after popping a missing position) all survived. Added four tests. Note for readers: the 10:05 conversion sits inside the fill loop after the capacity check, so a zero-volume minute at or after 10:05 leaves the status `open`; that is harmless because no fill is possible without capacity and `cancel_entry_remainders` is the explicit path, and the new test therefore uses an executable minute priced above the limit. |
| GDR-CR12-005 | P3 / corrected | `78914637`, `controls.py::FixtureLedger.__post_init__`; `test_controls.py` | The `previous_sha256` chain-link check was redundant with the sequence and epoch checks in every existing fixture (M47 survived: reversed receipts and a wrong sequence are caught earlier). Added `test_broken_previous_hash_link_is_refused_with_intact_sequence_and_epoch`, covering construction and `from_bytes`. M47 now fails. |
| GDR-CR12-006 | P3 / corrected | `1fb696d3`, `assessment.py::assess_candidate`; `test_assessment.py` | The entry window is derived from the New York date of publication, but every assessment fixture publishes at 12:00Z, where the UTC date is the same, so M56 (UTC date) survived although `events._nearest` has such a test. Added `test_entry_window_uses_new_york_announcement_date_not_utc_date`: a raise published 2025-04-02T01:00Z (21:00 New York on 04-01) must be eligible on 04-04 and not yet reached on 04-03. M56 now fails. |
| GDR-CR12-007 | P3 / documented | `1fb696d3`, `timing.py::select_entry_opportunity`, `assessment.py::assess_candidate` | The composed assessment re-implements the per-opportunity clock loop instead of calling `select_entry_opportunity`; the composed path can therefore never emit the plan's `stale_event`, `entry_attempt_already_consumed` or `announcement_precedes_publication_date` labels (it emits the underlying `*_after_cutoff` reasons instead). One rule at two call sites can drift. Not changed in review; Codex to decide whether to route the assessment through the timing function or retire the unused labels. |
| GDR-CR12-008 | P3 / documented | `8424a2b3`, `test_boundaries.py::test_active_document_references_agree_on_lane_and_draft_sources` | The lane gate binds to the size of the frozen shared `docs/SESSION_HANDOFF.md` (`< 50000` bytes); at this head the file is 49,887 bytes, 113 bytes of headroom. Any later handoff edit on `main` or another lane turns this lane's gate red without a lane change. Not changed (the handoff is frozen and the guard is Codex's); recommend dropping the size assertion or binding it to a lane-owned file. |
| GDR-CR12-009 | P3 / documented, design observation | `bcfdb02a`, `simulation.py::close_session` trim scheduling | Plan section 5 schedules a risk-reducing trim for any drift above the 5% position ceiling with no tolerance band. A position sized at 5% of NAV that appreciates slightly relative to the sleeve is trimmed by one or two shares at the next 10:00 with the USD 1 commission floor charged per trim order. The code matches the plan; the owner may want a tolerance band in the GDR-0 parameter freeze. |
| GDR-CR12-010 | P3 / documented | `40003585`, `events.py::_replay` version gate | The forced conflict for a same-ID later version applies only to `kind == "disclosure"`: a version 2 record of kind correction or withdrawal under an existing disclosure ID passes the gate, and a version 2 correction with changed economics replaces the effective predecessor without quarantine. Corrections and withdrawals can only invalidate candidates, so no positive entry can be created or re-timed; documented for the GDR-0 contract rather than fixed. |
| GDR-CR12-011 | P3 / documented | `9775e284`, `tests/guidance_revision_drift/` | The lane's test directory has no `__init__.py`, unlike `tests/analyst_revisions_v2/` and `tests/target_price_revisions/`; pytest imports its modules as top-level names (`test_events`, `test_contracts`, ...). No basename collision exists in the repository today; a later same-named test file in another package-less directory would collide. Not changed. |
| GDR-CR12-012 | P3 / documented | `78914637`, `qc_adapter.py::QcFixtureAdapter.on_minute` | The dated security binding is checked against `quote.end_utc.date()`, the UTC calendar date, while the rest of the package uses the New York date. Regular-session minutes (13:30-21:00 UTC) have equal UTC and New York dates, so no behaviour differs today; the inconsistency is noted for the eventual licensed bridge, where extended-hours bars would not. |
| GDR-CR12-013 | P2 / documented, out of lane | `origin/main` `ff0bb209`; `tests/test_decimal_conversion_guard.py`, `tests/test_project_separation_entrypoints.py`; Insider and Target-Price worktree guards | The repository suite excluding Analyst V2 is red on fifteen tests at this lane's head, and the four shared-gate failures are red on `origin/main` itself after the four lane merges (`#329`, `#343`, `#344`, `#345`): 22 Analyst QC `Decimal(str(...))` sites, a `scripts/` classification manifest 27 entries behind, and Analyst QC bare sibling imports counted as undeclared roots. The other eleven are Insider and Target-Price tests that refuse outside their own worktrees and cannot pass in any other checkout. None involves a lane file (12.4 note). Shared/main work: reported here, not fixed in this lane; the owner's deferred shared-remediation routing applies. |

Scripted count from this table: P0 0, P1 0, P2 2, P3 11; corrected 5, documented 8.

### 12.4 Validation

| Check | Scope | Result |
|---|---|---|
| Lane selection at the pushed head `8424a2b3` | worktree, network-denied | 233 passed, 849 subtests, 7.68 s |
| Lane selection after the twelve added tests | worktree, network-denied | 245 passed, 853 subtests, 7.40 s |
| Lane selection per code commit (informational, `git archive` exports) | `9775e284` / `40003585` / `1fb696d3` / `bcfdb02a` / `78914637` / `dc474392` | 59 / 107 / 137 / 197 / 212 / 233 passed, 0 failed |
| Repository suite excluding `tests/analyst_revisions_v2` | worktree at `8424a2b3` plus uncommitted lane tests, network-denied | 15 failed, 11,122 passed, 56 skipped, 28 warnings, 849 subtests, 1:05:58; all fifteen failures attributed outside this lane in the note below and in GDR-CR12-013; none names a lane file |
| `tests/analyst_revisions_v2` | not run | out of lane, see note below |
| `python -m compileall -q research/guidance_revision_drift tests/guidance_revision_drift` | worktree | passed |
| `git diff --check` | worktree | passed |
| CLI exit codes (`show-candidate`, `preflight`, `adapter-manifest`, `synthetic-demo`) | worktree, network-denied | 0 / 2 / 0 / 0; `preflight` printed `status=blocked` |
| Section 9 identities | `synthetic-demo` output | all six reproduce: report `b51d2ef2...`, epoch `f9fa3d80...`, code manifest `feb4a5eb...`, corpus `a707af71...`, schedule `b3fa4cbf...`, ledger `4d8b47f4...`; 22,056 bytes before the trailing LF |
| Design-source identities | worktree | Markdown `26478c3b...` and PDF `f8d7855b...` match the candidate; `cc614d33` blobs identical to `4b8447ed` |

The fifteen repository-suite failures fall into two classes, neither touched
by this range. (1) Four shared gates that are already red on `origin/main`
(`ff0bb209`): the same four tests fail identically in a `git archive` export of
that commit. `test_decimal_conversion_guard.py` lists 22 bare `Decimal(str(...))`
sites, all under `research/analyst_revisions_v2_qc/`; `grep` finds none in this
lane. `test_project_separation_entrypoints.py` reports a stale `scripts/`
classification manifest (27 unclassified scripts, first
`scripts/run_out_of_sample_check.py`) and undeclared "third-party" roots that
are Analyst QC bare sibling imports (`accepted_risk_*`). (2) Eleven tests of
the Insider Buying and Target-Price lanes that refuse outside their own
designated worktrees: ten Insider tests fail with `REFUSED: ... outside the
designated lane`, `offline validator module is not from the designated lane` or
`exact clean committed Insider lane is required` before reaching the behaviour
they assert, and `target_price_revisions/test_preregistration.py` fails with
`review anchor Git verification failed`. Re-running those eleven alone on this
worktree reproduced the same eleven refusals (11 failed, 135 passed in the
five files); the tree then differed from the committed head only by this
record and `test_boundaries.py`, and no refusal mentions head or status.

The Analyst Revisions V2 test directory was deliberately not run in this
review. No file it reads is touched by this range, and in any worktree other
than the Analyst lane's it is known to error rather than skip: its six-universe
modules load the gitignored `artifacts/analyst_revisions_v2/` package and
twelve of its scripts refuse unless the worktree name is
`trading_agent__analyst_revisions_v2` (documented on the Target-Price lane as
`TPR-OOL-015` and `TPR-OOL-016`). Running it here would produce only those
known out-of-lane errors. The repository suite row above therefore excludes
that directory and covers every shared gate the lane could affect, including
the active-document consistency, docs-root, module-hygiene and import-boundary
tests. Windows and LEAN/QC execution remain untested, as section 9 states.

### 12.5 Mutation trials

Sixty single-behaviour in-memory mutants (source rewrite of one function at
pytest configure time; no repository file edited) were each run against the
whole lane selection in a separate network-denied process. Caught means at
least one lane test failed.

| Class | Count | Mutants |
|---|---:|---|
| Caught by Codex's original tests | 46 | M04-M10, M13, M15-M23, M26-M46, M48-M51, M53-M55, M59 |
| Survived the original tests, now caught by added tests | 13 | M01, M02, M03, M11, M12, M14, M24, M25, M47, M52, M56, M58, M60 |
| Unreachable by construction, no test added | 1 | M57: fill ordering sells-before-buys within one minute; an issuer can never hold both an active buy and an active sell (`submit_entry` refuses while a sell is active and `_exit` refuses while a buy is active), so the ordering never decides anything |

Representative caught mutants: adverse impact removed (M16), commission floor
removed (M15), limit protection removed (M17), same-bar fills (M09), E moved to
D+2 (M27), cutoff moved to 19:00 (M28), publication-equals-cutoff accepted
(M29), time exit on session 20 (M30), ADV and price thresholds off by one unit
(M31, M32), future bars visible (M34), missed-opportunity guard removed (M35),
raise and EPS-floor comparisons made strict (M36, M37), predecessor-capture and
delayed-receipt risk gates removed (M38, M39), protected-date boundary moved
(M46), archive checkpoint and candidate hash pins removed (M48, M49), external
refusal turned into a no-op (M50). Section 10 claims GDR-QA-007, QA-008,
QA-009 and QA-020 were mutation-verified; M39, M29, M34 and the reporting
calendar test reproduce those catches.

### 12.6 Record maintenance

The status block now names this section and the pending counter-review. The
lane gate in `test_boundaries.py` pinned the phrase "independent review
pending", which is no longer true; it now pins "Codex counter-review of section
12 pending" and carries a comment that the phrase rotates with each review
section. The handoff size assertion is unchanged (GDR-CR12-008).

### 12.7 Commits, publication and next action

| Commit | Scope |
|---|---|
| `2dc6fd9c` | Twelve lane regression tests (GDR-CR12-002 through GDR-CR12-006) |
| This record commit | Section 12, status block, `test_boundaries.py` pin rotation |

One push of this round after both commits exist, to
`origin codex/strategy-guidance-revision-drift`, guarded on the remote head
still being `8424a2b3`; never force. Next: Codex counter-reviews section 12 and
both Claude commits, rotates the `test_boundaries.py` phrase, and answers
GDR-CR12-007 and GDR-CR12-008. GDR-CR12-013 is shared-main state for the owner's
deferred remediation routing, not lane work. No GDR-1 or empirical, data, QC, broker, paper
or live step starts from this review. `docs/ACTION_PLAN_2026-08-20.md` and
`docs/SESSION_HANDOFF.md` were not edited in this round and remain frozen for
this lane pending the owner's decision under GDR-CR12-001.

## 13. Codex counter-review of the completed Claude push, 2026-10-07

Trigger: remote lane head changed from
`8424a2b393b4d0803172b87aaa4d494776b977cc` to
`c1be751ac403b5906428cbf9f86673e1bc23527e`, observed at the 17:40 UTC
monitor check, then fetched explicitly. Baseline ancestry, exact review target
in section 12, both complete commit diffs, clean designated worktree and matching
local/remote heads were verified. Earlier dirty/local-only review work was not
used to start implementation. This is the one triggering review for automation
`guidance-claude-push-counter-review`; later Codex publication is not a new
Claude trigger. No other branch or worktree was used.

| Exact reviewed commit | Disposition | Evidence / correction |
|---|---|---|
| `2dc6fd9cf9208d0acfcc53bb92434567c69aabbe` | Accepted after correction | All twelve added tests pass; all thirteen documented targeted mutants independently caught, with thirteen restored originals green. CCR13-001 adds an isolated active-sell regression. No production defect in these additions. |
| `c1be751ac403b5906428cbf9f86673e1bc23527e` | Accepted after correction | Complete review record and status-test diff inspected. The historical report is retained; this section qualifies its process, correction-lineage and out-of-lane attribution claims, and records lane-owned follow-ups below. |

Counter-review code/test correction commit:
`9d6f2037951266c283c6c3672f622daf373e05de` (local-only until this combined
round's single publication). The following record commit also removes the
redundant lane handoff-size assertion and updates the current-status guard.

### 13.1 Retained P0-P3 finding dispositions

No P0/P1 was found. Prior findings remain in section 12 rather than being
deleted. These are counter-review conclusions, not a claim to have rerun
Claude's full suite or all sixty mutation trials.

| Finding | Priority / disposition | Evidence, action and verification |
|---|---|---|
| GDR-CR12-001 | P2 / partially correct; unauthorized-edit conclusion not established | The four shared-document edits occurred. However, root AGENTS and parallel-workflow sections 1-2 explicitly name the three original lanes; the machine-wide rule does not itself freeze the root handoff. The quoted review-session instruction is retained as Claude's reported provenance, not a new human instruction to this session. The current explicit owner heartbeat requires this round's GDR root handoff and Action Plan sequencing reference. No shared revert or general freeze override follows. Updates are limited to that coordination scope; shared behavior, sibling documents and workflow files stay unchanged. |
| GDR-CR12-002 | P3 / accepted, corrected by Claude | Inclusive drawdown/position boundaries and post-trim reference basis verified; M01/M02/M03/M24 independently caught. |
| GDR-CR12-003 | P3 / accepted after CCR13-001 | Missing-valuation, skipped-close and scheduled-exit refusal isolation verified; M12/M25/M58 caught. Independent active-sell arm needs the additional test below. |
| GDR-CR12-004 | P3 / accepted, corrected by Claude | Explicit cancel preserves reserves; pre-open settlement refuses; executable 10:05 data requests cancellation; terminal payout without entitlement refuses atomically. M11/M14/M52/M60 caught. Zero-volume limitation is correctly disclosed. |
| GDR-CR12-005 | P3 / accepted, corrected by Claude | Receipt previous-hash chain guard is isolated; M47 caught. |
| GDR-CR12-006 | P3 / accepted, corrected by Claude | NY publication date determines D+3; M56 caught. |
| GDR-CR12-007 | P3 / partially correct, corrected | Clock/stale labeling duplication confirmed. Assessment cannot have an announcement-before-publication mismatch because it derives the date; consumed attempts belong to simulation. A shared per-opportunity availability helper now serves timing and assessment, including final `stale_event`; dated-universe iteration remains in assessment so first clock eligibility is not confused with first full eligibility. New late-receipt test was red before the correction; first-universe-opportunity invariance stays green. |
| GDR-CR12-008 | P3 / confirmed, corrected | Removed only the redundant lane assertion of shared handoff size. The unchanged project-wide `test_current_handoff_is_a_bounded_unique_resume_snapshot` still enforces its 50,000-byte bound. Source/status consistency checks remain. |
| GDR-CR12-009 | P3 / accepted design observation, no economic change | No-tolerance whole-share trims match the proposal. A tolerance band remains an unresolved owner parameter choice, not a counter-review fix. |
| GDR-CR12-010 | P3 / mechanics accepted, wording qualified | Explicit corrections never directly create/re-time a positive entry, but their corrected economics intentionally become the predecessor for later genuine disclosures. Existing `test_corrected_predecessor_is_used_and_withdrawn_predecessor_not_skipped` pins this. A 102/1.05 disclosure corrected to 90/.90 followed by fresh 92/.95 news can qualify against the corrected baseline. No new quarantine or economics is introduced. |
| GDR-CR12-011 | P3 / latent maintenance risk corrected | Added the lane test package marker; package-qualified imports pass. No existing basename collision was claimed. |
| GDR-CR12-012 | P3 / confirmed consistency issue, corrected | Binding lookup now uses the explicit NY date. Regular-session behavior is unchanged; new midnight-boundary tests still refuse extended-hours data atomically and retain no receipt. The old UTC mapping produced two wrong-exception errors in that regression. |
| GDR-CR12-013 | P2 / shared-main finding retained, attribution corrected | Four exact shared guards independently fail on pre-existing surfaces: 22 Analyst QC bare Decimal conversions, 27 unclassified scripts, and 39 undeclared Analyst QC import roots. GDR changed none of those source/guard/manifest bytes. Claude's full totals and ten Insider path/branch refusals remain reviewer-reported, not rerun. The additional reproduced Target-Price refusal is a macOS/Windows-Git compatibility problem: its trusted runner pins `C:\\Program Files\\Git\\cmd\\git.exe`, and authentication fails before the empty-registry guard. It is not a demonstrated Target-Price worktree-location refusal. No shared or sibling correction is authorized here. |
| GDR-CCR13-001 | P3 / confirmed, corrected | Claude's due-exit/active-sell test retained a due-map entry during both assertions; deleting just the active-sell arm survived. Added `test_active_sell_without_scheduled_exit_refuses_entry_with_fresh_quotes`, using a direct exit with an empty due map and fresh held quotes. Guard removed: one failure (new buy incorrectly admitted); restored: one pass. No production change. |

### 13.2 Validation and authority disposition

Bundled Python 3.12.14/macOS. Read-only counter-review selected seven existing
event/timing/assessment/adapter/document tests: seven passed. Claude's twelve
new tests: twelve passed, zero failed/skipped (0.097 s). Thirteen in-memory
mutants were caught and thirteen restored single-test reruns passed; the new
active-sell mutant also fails and restores green. Corrections selection:
13 timing + 8 assessment + 8 adapter + 2 import-boundary tests = 31 passed;
seven changed files compiled in memory and three package-qualified test imports
passed. The six lane boundary tests passed before correction. Final cumulative
focused checks and exact correction commit are recorded below before publication.
Final cumulative selection (simulation, controls, timing, assessment, adapter
and lane boundaries): **96 passed, zero failures/errors/skips in 0.741 s**;
lane compilation and `git diff --check` passed. No full lane or repository
suite was run by Codex.

Shared diagnostic checks used the normal pytest conftest/isolation under a
network-denied process: four selected shared checks failed (4.25 s), and the
one Target-Price environment diagnostic failed (0.44 s). Those failures are
reported, not hidden or repaired from this lane. The affected pre-existing
modules are outside this package's permitted dependency closure and do not
block the approved offline engineering work. Original research/operation
readiness remains blocked. Counter-review acceptance grants no source rights,
PIT claim, empirical look, parameter freeze, QC attempt or trading authority.

## 14. Owner-authorized next ten offline increments, 2026-10-07

The owner explicitly directed waiting for Claude's completed push, then
counter-review, then **ten** increments before the next independent Claude
review. This expands the approved offline direction; it does not start the
original GDR-1..6 research stages. Several commits, exactly one combined
non-force push to this lane from its designated worktree after the batch.
No partial/checkpoint publication, PR, merge, or second branch/worktree.

Definitions of done recorded before implementation:

| Increment | Bounded deliverable | Required focused evidence / limitation |
|---|---|---|
| ENG-7 | Executable proposal/specification inventory binding the unchanged candidate and design hashes, explicit event/clock/trim/correction/fee/settlement semantics and per-action decision/rights matrix. | Mutation/refusal and consistency tests; all eleven original sign-offs remain unresolved and external permissions false. This is freeze-ready, not owner-frozen. |
| ENG-8 | Strict provider-shaped guidance payload decoder using invented values and documented public fields, explicit normalized units/FY/basis/identity/receipt inputs, immutable raw provenance and named refusals. | Malformed/missing/unknown fields, invalid numeric ranges/units/basis/period/time checks. No credentials, licensed rows, download or claim that public fields establish private entitlement or original receipt. |
| ENG-9 | Provider identity/version receipt lineage with duplicate/conflict/correction/withdrawal handling and cutoff replay into the synthetic event model. | Exact replay, delayed/out-of-order receipts, immutable projections, changed predecessor and withdrawal tests. Source consistency only: no real capture service or PIT attestation. |
| ENG-10 | Dated raw market/reference input contracts bound to permanent synthetic identities, explicit exchange/session calendar and as-of availability. | Missing/stale/future/ambiguous mapping, raw-vs-adjusted price, quote/trade/calendar alignment fixtures; no fetch route or claim of an audited historical calendar. |
| ENG-11 | One explicit corporate-action input path for strategy and matched comparator, integrating whole-share splits, cash dividends and supplied terminal economics. | NAV/cash/position reconciliation, idempotence, pending-order/action ordering and unsupported fractional/noncash/missing-terminal refusal. Never invent cash-in-lieu or a terminal payout. |
| ENG-12 | Bounded local research-only immutable command/event journal and checkpoint contracts with no-overwrite publication, content/sequence/epoch checks and crash acknowledgment semantics. | Corruption, incomplete publication, competing/stale append, checkpoint and crash-boundary tests. Owner-controlled synthetic store only; no operator database, external anti-rollback authority or unproved power-loss guarantee. |
| ENG-13 | Reconstruct the synthetic engine from verified committed command history; reconcile attempts, partial fills, cancellation requests/acks, reservations and settlement exactly once. | Restart vs uninterrupted state equality, retry/conflicting-ID/racing-fill/recovery refusal tests. Snapshots are reports, not trusted recovery state; no broker reconciliation claim. |
| ENG-14 | Isolated actual LEAN `QCAlgorithm` source package connecting deterministic decisions to order submission/events, explicit synthetic input, fill/fee/settlement model assumptions and local callback contract checks. | Prove local order/callback wiring and fail-closed unsupported/live paths; compile source locally. If SDK/LEAN is unavailable, state that explicitly. No upload/job, hosted dataset access, deployment, SDK execution or cloud completion claim. |
| ENG-15 | Repeatable local strategy/comparator integration across the new input/action/persistence boundaries, with an explicit complete expected calendar and retained refusals/underfills. | Base/stress, missing data, actions, restart and parity-blocker fixtures; report native-engine limitations. Local fixture success never substitutes for an actual completed QC backtest. |
| ENG-16 | Pre-QC release manifest/report package binding actual source/candidate/input/calendar/engine contracts, reproducible fixture checks and unconditional closed launch preflight. | Tamper/omitted-manifest/different-epoch/report reproducibility/refusal tests, import/document/compilation/diff/status checks. Later separately authorized order-based QC run instructions retain max-three-failed-attempt/Mia recovery rule. |

Stop any increment whose required work needs a material unresolved economic
choice or new external authority; do not declare it complete or split the push.
Report the blocker to the owner and pause the one-cycle monitor. Proposed
numeric settings and original Markdown/PDF/candidate bytes are unchanged;
protected dates, four-lane allocations and every provider/outcome/account gate
remain closed. Source access and real QC completion are deliberately outside
these offline definitions, not silently counted as finished.

## 15. Ten-increment offline delivery and review handoff, 2026-10-07

The section-14 deliverables are implemented and author-validated, not
independently accepted or owner-frozen. This is the authorized combined
counter-review/batch round triggered by `c1be751ac403b5906428cbf9f86673e1bc23527e`.
No new Claude trigger is inferred from the eventual Codex push. Original
GDR-0..6 stages remain incomplete; no shared milestone ledger is marked done.

### 15.1 Delivered behavior, technical and plain-language

**ENG-7 — executable proposed specification.** `specification.py` binds the
unchanged candidate/source hashes, runs exact threshold/calendar witnesses,
and inventories eleven unresolved owner decisions plus closed action rights.
Correction-predecessor, no-tolerance trim, fee, cutoff and synthetic settlement
semantics are explicit; there is no approval/freeze operation.

In plain language: the proposed rules are inspectable and checked against
the implementation, but the software cannot sign off the owner's decisions.

**ENG-8 — vendor-shaped synthetic normalization.** `vendor_payloads.py` parses
one invented Massive/Benzinga-shaped record with exact JSON decimal numbers,
strict keys, ranges, units, annual period, basis, identities and clocks. Raw
bytes and synthetic-context hashes survive normalization. Missing provider
semantics require explicit synthetic context; previous-value fields never
become captured predecessors. Zero-revenue cuts remain valid risk information.

In plain language: the parser can reject malformed examples without pretending
that undocumented units, receipt times or correction rules were verified from
a subscription. It has no API client or licensed-data route.

**ENG-9 — receipt lineage and as-of replay.** `lineage.py` retains at most 128
raw/context receipts, hashes/checkpoints their immutable order, deduplicates
economic redeliveries without resetting first capture, and replays corrections,
withdrawals and conflicts through the existing event model. Identity remaps
remain evidence in the journal but block replay rather than inventing a mapping.

In plain language: later edits cannot masquerade as earlier knowledge. This
demonstrates invented-version handling, not a real capture service or PIT proof.

**ENG-10 — dated market-input contracts.** `market_inputs.py` binds raw paired
quote/trade snapshots and permanent synthetic references to an explicit
calendar/session, source and receipt/validation clocks. Fresh quote inspection
allows at most 60 seconds; executable-minute preparation requires availability
at that minute's actual end, preventing delayed receipts from backdating fills.

In plain language: stale, adjusted, mismatched or not-yet-known data is refused.
The 93-session schedule remains a test fixture, not an audited exchange calendar.

**ENG-11 — paired corporate-action accounting.** `corporate_actions.py` applies
explicit whole-share splits, independent cash dividends and terminal inputs
atomically to affected sleeves. Comparator source-share denominators adjust
without rewriting original fill receipts. Duplicate action success requires
both affected domain receipts to match; pending/fractional/noncash unsupported
cases refuse without partial mutation.

In plain language: stock splits and declared cash can be reconciled. A source
terminal payout does not justify an invented SPY sale: that comparator position
remains visible with a permanent unsupported-schedule blocker. No terminal
economics or new exit-timing rule was invented.

**ENG-12 — bounded durable research journal.** `persistence.py` publishes
immutable numbered commands by no-overwrite hard link, verifies content,
genesis/predecessor/sequence/IDs, and synchronizes file and directory entries.
Stale writers refuse. A lost post-link acknowledgment is explicitly uncertain;
idempotent retry/recovery must complete synchronization before acknowledgment.
Limits are 1,024 commands and 64 KiB per record.

In plain language: an interrupted local write is not silently treated as absent
or complete. Retained hashes detect corruption/truncation relative to those
anchors; there is no adversarial rollback root or cross-platform power-loss
guarantee, and this is not an operator database.

**ENG-13 — deterministic paired recovery.** `recovery.py` constructs fresh
event/strategy/comparator engines from pinned genesis and allowlisted public
commands. It verifies every result/post-state hash and checkpoint while
reconciling partial fills, reservations, cancellation races, settlement and
corporate actions. Comparator commands reference actual strategy-fill indices.
Correction/withdrawal/conflict chains survive restart. Snapshots are reports,
never trusted private-state restore images.

In plain language: restarting the invented engine produces the same state and
does not repeat an acknowledged order effect. There is no broker connection or
production recovery claim; the release caller verifies supplied source hashes.

**ENG-14 — actual order-based LEAN source.** Isolated `lean/main.py` contains
`QCAlgorithm`, custom `PythonData` and `FillModel` classes. Deterministic
decisions issue native limit/async market orders; exact receipts drive native
fees and order-event reconciliation. `lean_bridge.py` rejects missing, shifted,
conflicting or unacknowledged callbacks. Only the exact generated synthetic
sidecar and custom SYN benchmark are accepted; live initialization refuses.

In plain language: actual algorithm methods are wired and locally exercised,
but AlgorithmImports/QuantConnect/Python.NET are not installed here. The shim
does not prove LEAN overloads, reader integration or native fill scheduling.
Native cash uses an explicitly immediate-settlement envelope while shadow
dated settlement controls spending; this is not cash-account parity. Native
comparator/corporate-action parity is also unverified. No SDK/cloud run occurred.

**ENG-15 — stitched input/action/restart integration.** `integration.py` composes
the actual synthetic vendor parser, as-of lineage, eligibility, dated market
contracts, durable paired command engine, actions and checkpoint/recovery.
Seven scenarios each retain 93 paired dates: base/stress actions, missing input,
stale input, underfill, source terminal, and missing historical NAV. Restarted
and uninterrupted histories reproduce exact state/head/report identities.

In plain language: supported split/dividend cases settle both sleeves. Refusal
and underfill cases deliberately keep their blockers instead of passing by
dropping bad dates or inventing trades. These are software checks, not returns
from market data or completed QuantConnect backtests.

**ENG-16 — reproducible pre-QC review release.** `release.py` fingerprints actual
recursive source bytes (including native entrypoint and neutral helpers),
candidate, proposed specification, contracts, calendar, generated sidecar,
Python environment and original/stitch reports. Verification reconstructs
canonical bytes, so rehashed omitted fields, bool/int aliases or forged launch
flags cannot self-certify. The CLI publishes a content-addressed synthetic
manifest; `launch-preflight` always exits 2 with all authority closed.

In plain language: Claude can reproduce what was checked and see exactly what
was not. `lean/README.md` specifies later separately authorized order-based
evaluation, exact source/runtime receipts and the three-failed-attempt/Mia rule.
No upload, job, source access, paper/live deployment or financial promise follows.

### 15.2 Author-QA finding ledger

This is implementation QA, not Claude's independent review. No P0/P1 was found.
Section 13 retains every Claude finding/disposition and the unresolved P2
shared/main issues; none was hidden by this new batch or repaired out of lane.

| ID | Priority / final state | Evidence and correction |
|---|---|---|
| GDR-ENGQA-001 | P2 / corrected | Parser-only revenue-positive restriction could suppress a zero-revenue risk cut. Removed it; finite/bounded range validation remains; risk-cut regression passes. |
| GDR-ENGQA-002 | P2 / corrected | A fresh delayed market receipt must not create a backdated fill. Quote inspection and exact-minute executable preparation now have separate checks; focused regression passes. |
| GDR-ENGQA-003 | P2 / corrected | A readable linked journal record did not alone prove directory-sync acknowledgment. Duplicate append and recovery now re-synchronize; lost-ack tests pass. Both removed-sync mutants fail and safely restored originals pass. |
| GDR-ENGQA-004 | P2 / corrected | Python equality could alias boolean/integer command retries. Retry identity now compares exact canonical bytes; alias mutant fails and restored regression passes. |
| GDR-ENGQA-005 | P2 / corrected | Duplicate action acknowledgment trusted only the comparator receipt and could accept an untouched replacement strategy. Both affected domain fingerprints are required; mixed-engine duplicate refuses without mutation. |
| GDR-ENGQA-006 | P3 / corrected | Direct bridge dictionary equality accepted `False` as frame index zero. Strict integer type required; native reader already had this guard. |
| GDR-ENGQA-007 | P2 / corrected | Initial release schema did not satisfy the existing synthetic-only publisher. Narrowed to `gdr.synthetic.review-release.v1`; real CLI output-directory/idempotent-publication regression passes. |
| GDR-ENGQA-008 | P2 / corrected | Rehashed release `False`/`0` substitutions could survive dict comparison. Verifier now compares reconstructed canonical bytes; both alias regressions refuse. |
| GDR-ENGQA-009 | P2 / explicitly unverified runtime boundary | LEAN native scheduling, SDK binding and cash-account settlement parity are not demonstrated by local callback tests. Runtime/version/completion flags stay false, native limitations are documented, and external launch preflight is closed. No claim of actual QC completion. |

Additional targeted mutation evidence: disabling USD-unit scaling and exact
redelivery suppression each made its focused parser/lineage regression fail;
both were restored and rerun green. Counter-review's separately reproduced
fourteen mutants remain documented in section 13. No broad mutation battery or
full suite is claimed.

### 15.3 Validation and release evidence

Python 3.12.14/macOS; all repository execution used the designated worktree and
branch. Final selected new/affected modules: **134 tests passed in 15.092 s**
(specification, vendor payloads, lineage, market inputs, corporate actions,
persistence, recovery, LEAN bridge/source shim, comparator, reporting, scenario,
and lane boundaries). Stitched integration: **8 passed in 70.124 s**. Release
reconstruction/export/gate checks: **6 passed in 109.534 s**. Total **148 distinct
batch-focused checks**, zero failures/errors/skips. These are selected modules,
not the complete lane or repository suite. Counter-review separately passed
its 96-check selection. Additional author-QA independently reran five targeted
durability/recovery checks, all passing; these are not added to the unique total.

Lane/test compilation and `git diff --check` passed. Original Markdown, PDF
and candidate hash verification remains unchanged. Full lane/repository suites,
Windows behavior and LEAN/QC execution were not run. Actual provider/outcome
reads, empirical looks and QC launch attempts: **zero**. Root coordination edits
are limited to this GDR status/next-action reference; shared behavior, sibling
lanes, broker/operator/scheduler state and workflow instructions are unchanged.

Post-document checks: six lane boundary tests passed again (0.115 s), including
fresh-process imports of every new core module without SDK/provider/execution
packages. Three selected unchanged shared active-document guards passed (0.45 s)
under normal pytest isolation with network denied: docs-root inventory, bounded
unique handoff, and both review topologies. The root handoff stays below 50,000
bytes. These three shared checks are additional to the 148 batch checks.

Committed content-addressed release artifact:
`research/guidance_revision_drift/releases/fccbef76a0921015e120dbaa73cf09f07ef6d20ac8d42839c7d4f47bce79f305.json`.
Its filename is its exact-byte SHA-256. The successful actual CLI publication
returned zero external authority and zero QC attempts. Reproduction requires
the recorded CPython 3.12.14 environment; environment changes are a different
release, not permission to relabel the old one.

| Release identity | SHA-256 |
|---|---|
| Actual source manifest | `27bf1f0edf93c339e8705ef9aa818d3767f7c04b1d4fc3e12efaabceb5e40757` |
| Executable proposed specification | `35ed8fcad1a61961b1e7a468c5a49efe6069db08b730fdbca42318f7eba5340c` |
| Original base/stress fixture report | `d5b5d304f0dcc024dd9414b60924ebba5ba188a79788fd5e4c516b52c2997503` |
| Seven-scenario stitched integration report | `e0a974f3230daa2378c2214e9c056141f2b5ac995086b6e13b22830ca916fbeb` |
| Generated native synthetic sidecar (43,135 bytes, not uploaded) | `8f35d56a335d3f7d9dad016e1e2236de7fcd2635e5c463c30081f97b7b944458` |

### 15.4 Exact range, one publication and Claude resume instructions

The completed Claude review target was baseline
`8424a2b393b4d0803172b87aaa4d494776b977cc`; its two pushed commits through
`c1be751ac403b5906428cbf9f86673e1bc23527e` have the section-13 per-commit
dispositions. Codex's next independently reviewable range begins **after**
that trigger, `c1be751ac403b5906428cbf9f86673e1bc23527e..HEAD`, where HEAD is
the enclosing final handoff/publication commit on this lane:

1. `9d6f2037951266c283c6c3672f622daf373e05de` — verified counter-review
   clock, test-isolation, package and mapping consistency corrections.
2. `9630ac3221182a1dff83a9b788dd86202d567199` — all Claude dispositions,
   shared-finding qualification and ten pre-implementation definitions of done.
3. `0d32ebb813f11c4a5136de0a507a16bfe5487b6b` — ENG-7..16 source/tests,
   package documentation and exact release JSON. This is the final code snapshot.
4. The enclosing handoff commit — this section and the concise GDR-only root
   Session Handoff/Action Plan coordination update, with no source change.

Prepared for exactly one successful non-force push, from the designated
worktree to only `refs/heads/codex/strategy-guidance-revision-drift`. The remote
was rechecked at `c1be751a` before final publication preparation; the publishing
session must verify its final remote HEAD and record the resulting exact hash
in thread/monitor completion state. Do not interpret pre-push text alone as
proof of fetchability. No PR, merge, second push or next batch is authorized.

Claude: fetch the exact resulting lane head, read current CLAUDE/AGENTS, this
record sections 13-15, original plan, Action Plan GDR entry and root handoff0E.
Review every commit above and every retained finding with P0-P3 dispositions;
independently run the full lane suite and adversarially examine source lineage,
paired actions, crash boundaries, replay and native callback assumptions.
Do not infer SDK/cloud success from shim/fixture passes. Source rights, owner
freeze, research-family allocation, protected dates, provider/capture/QC job,
account/paper/live and capital gates remain closed. Codex stops here; the
one-cycle monitor is paused after remote verification. A later review/development
round requires the owner's next instruction, not our own push as a trigger.

## 16. Independent Claude review of `c1be751a..d522fad7`, 2026-10-07

### 16.1 Scope and method

Reviewed range: the four Codex commits after the section-12 push, `9d6f2037`,
`9630ac32`, `0d32ebb8` and `d522fad7` (the fetched remote head). The worktree
was clean and equal to the remote head at the start. Host, isolation and
method are as in 12.1: every commit read individually, every new or changed
module and test read in full, every pytest and mutation process network-denied
under the proved `sandbox-exec` profile, all validation in the designated
worktree except the per-commit informational runs in `git archive` exports.
No provider, QC, broker, paper or live system was contacted; research looks 0;
QC attempts 0. The LEAN SDK is not installed here either, so nothing in this
review verifies native LEAN scheduling, bindings or cloud completion; section
15's statements to that effect stand.

### 16.2 Disposition of the section-13 counter-review

| Section-13 item | Claude disposition |
|---|---|
| GDR-CCR13-001 | Accepted. My section-12 precedence test kept a due-map entry during both assertions, so deleting only the active-sell arm survived; Codex's isolated test is correct and is retained. |
| GDR-CR12-001 qualification | Partially accepted. The four edits occurred and were deliberate; whether the machine-wide lane rule freezes the root handoff for this lane is an owner-channel question (Codex's heartbeat requires the root handoff and Action Plan reference; Claude's session instruction applies the lane workflow). Neither role can settle it; recorded for the owner as GDR-CR16-001 together with the fourth edit in `d522fad7`. No revert. |
| GDR-CR12-007 correction | Accepted and verified: `opportunity_availability_refusals` now serves both the clock-only API and the composed assessment; `stale_event` is emitted only at the final opportunity (mutants N33 "never" and N34 "always" both fail the timing and assessment tests). |
| GDR-CR12-008 correction | Accepted: the lane no longer asserts the shared handoff size; the project-wide guard still does. |
| GDR-CR12-010 qualification | Accepted: a correction's economics intentionally become the predecessor for later genuine disclosures, pinned by the existing test. |
| GDR-CR12-011 correction | Accepted: `tests/guidance_revision_drift/__init__.py` added; the cross-test import in `test_lineage.py` loads exactly one module object under the package-qualified name (checked in-process). |
| GDR-CR12-012 correction | Accepted and verified: the adapter binding uses the New York date with a midnight-boundary regression. |
| GDR-CR12-013 attribution | Accepted as a correction of my section 12.4 wording: the Target-Price failure is the Windows Git trust-root path (`review anchor Git verification failed`), not a worktree-location refusal; the ten Insider refusals stand as described. Recorded as GDR-CR16-002. |

### 16.3 Commit dispositions

| Commit | Scope | Disposition | Notes |
|---|---|---|---|
| `9d6f2037` | Counter-review clock/test-isolation corrections | Accepted | Shared per-opportunity helper, New York binding date, test package marker, four added tests; mutants N33, N34 caught |
| `9630ac32` | Section 13-14 record, pin rotation, size assertion removal | Accepted | Documentation and lane-gate change only |
| `0d32ebb8` | ENG-7..ENG-16 source, tests, README, release artifact | Accepted after correction | Three tests added (GDR-CR16-003/004/005); 30 of the 35 round-two mutants that target this commit's modules were caught by its own tests; release artifact content-addressed and reproduced (16.5) |
| `d522fad7` | Section 15, Action Plan and Session Handoff update | Accepted | Documentation only; shared-file edit recorded in GDR-CR16-001 |

### 16.4 Findings ledger

IDs are `GDR-CR16-NNN`. Resolved items stay in this table.

| ID | Priority / status | Location | Finding, disposition and verification |
|---|---|---|---|
| GDR-CR16-001 | P2 / documented, owner decision | `d522fad7`; `docs/ACTION_PLAN_2026-08-20.md`, `docs/SESSION_HANDOFF.md` | The frozen shared documents were edited a fifth time, under Codex's reported owner heartbeat that requires a GDR root-handoff and Action Plan reference each round. Claude's reported session instruction applies the lane workflow, under which both files are frozen. The two instructions reach the two roles through different channels and are recorded side by side; neither role re-asserts its reading. No revert. Owner to state, where both roles can read it, whether the root handoff and Action Plan are frozen for this lane or updated each round, and whether the existing edits stand at integration. |
| GDR-CR16-002 | P3 / accepted correction of section 12 | section 12.4 note | Section 12.4 described all eleven Insider and Target-Price failures as worktree-location refusals. Codex's 13.1 is right that the Target-Price test fails on its Windows Git trust-root path before reaching the guard it asserts. The ten Insider refusals are unchanged. Section 12 is retained as written; this row supersedes that one attribution. |
| GDR-CR16-003 | P3 / corrected | `0d32ebb8`, `lean_bridge.py::SyntheticOrderBridge.issue_fill`; `test_lean_bridge.py` | The README's central contract, that a native fill must be evaluated in the exact minute of the shadow receipt, had no test: mutant N26 (shift check removed) survived. Added `test_native_fill_processed_at_a_shifted_minute_is_refused_before_issue`: a fill model invoked one minute later, one minute earlier or one second later is refused with the receipt still pending, and the exact-minute invocation then issues it once. N26 now fails. |
| GDR-CR16-004 | P3 / corrected | `0d32ebb8`, `lean_bridge.py::SyntheticOrderBridge.finish`; `test_lean_bridge.py` | `finish` emitting a report while the shadow strategy is incomplete was untested: mutant N30 survived because the lineage counts still reconcile. Added `test_finish_refuses_a_report_while_the_shadow_strategy_is_incomplete` (every post-entry minute starved of capacity, so the time exit never fills). N30 now fails. |
| GDR-CR16-005 | P3 / corrected | `0d32ebb8`, `comparison.py::MatchedComparator.apply_source_split`; `test_comparison.py` | The fractional-source-split refusal was untested (N36 survived). Inside the paired coordinator it is redundant, because the strategy engine refuses the fractional split first and the lineage equality check makes both share counts equal; the method is public, so a direct caller could have its remaining source shares silently floored. Added `test_source_split_refuses_fractional_remaining_shares_without_flooring`. N36 now fails. |
| GDR-CR16-006 | P3 / documented | `0d32ebb8`, `release.py::build_release`, `releases/fccbef76...json` | The release identity binds `platform.python_version()`, so `verify_release` can only reproduce the committed artifact under CPython 3.12.14. Built here under 3.13.15, the release differs in exactly that one field; `code_sha256`, `proposed_specification_sha256` and both report hashes are identical, which is the strongest reproduction available off the authoring interpreter. Recommend recording a content identity that excludes the environment fingerprint beside the environment-bound one, so a reviewer on another interpreter can verify the content exactly. Not changed in review. |
| GDR-CR16-007 | P3 / documented | `0d32ebb8`, `integration.py::run_integrated_fixture` | The recipe ingests each provider observation on the day `published_at.date()` falls, the UTC date, while the rest of the package keys announcement dates to New York. Harmless for the 12:00Z fixtures; a late-evening fixture would ingest one session later than the New York date. Fixture code only. |
| GDR-CR16-008 | P2 / documented, out of lane | repository suite | The repository suite excluding Analyst V2 is red on the same fifteen tests as at `8424a2b3`: four shared gates already red on `origin/main` (Analyst QC `Decimal(str(...))` sites, the stale `scripts/` classification manifest, Analyst QC bare sibling imports) and eleven Insider and Target-Price tests that cannot pass outside their own hosts or worktrees (with the Target-Price attribution corrected in GDR-CR16-002). The failure set is byte-identical to round one and none involves a lane file; this range changed no shared file other than the two coordination documents in GDR-CR16-001. Shared/main work, reported here and not fixed in this lane. |

Scripted count from this table: P0 0, P1 0, P2 2, P3 6; corrected 3, accepted correction 1, documented 4.

### 16.5 Validation

| Check | Scope | Result |
|---|---|---|
| Lane selection at the pushed head `d522fad7` | worktree, network-denied | 357 passed, 1,023 subtests, 4:17 |
| Lane selection per commit (informational, `git archive` exports) | `9d6f2037` / `9630ac32` / `0d32ebb8` | 249 / 249 / 357 passed, 0 failed |
| Lane selection after the three added tests | worktree, network-denied | 360 passed, 1,026 subtests, 4:12 |
| Repository suite excluding `tests/analyst_revisions_v2` | worktree at `d522fad7`, network-denied | 15 failed, 11,246 passed, 56 skipped, 28 warnings, 1,023 subtests, 1:02:46; the fifteen failures are the identical set recorded in section 12.4 (GDR-CR12-013), and the pass count rose by exactly the 124 lane tests added since `8424a2b3` |
| `python -m compileall -q research/guidance_revision_drift tests/guidance_revision_drift` | worktree | passed |
| `git diff --check` | worktree | passed |
| CLI `review-release` / `launch-preflight` | worktree, network-denied | exit 0 / exit 2 with `status=blocked` and every launch, upload and paper/live flag false |
| Release artifact | `releases/fccbef76a0921015e120dbaa73cf09f07ef6d20ac8d42839c7d4f47bce79f305.json` | filename equals the SHA-256 of its 15,100 bytes; rebuilt here with one differing field (`engine.python_version` 3.12.14 vs 3.13.15); `code_sha256` `27bf1f0e...`, specification `35ed8fca...`, base/stress report `d5b5d304...` and integration report `e0a974f3...` identical |
| Analyst V2 directory | not run | out of lane, as in section 12.4 |

### 16.6 Mutation trials

Thirty-seven single-behaviour in-memory mutants over the ENG-7..ENG-16 modules
and the section-13 corrections, each run network-denied against the test files
that own the mutated module (survivors re-checked against the whole affected
selection by the added tests).

| Class | Count | Mutants |
|---|---:|---|
| Caught by Codex's tests | 32 | N01-N16, N18-N23, N25, N27-N29, N31-N35, N37 |
| Survived, now caught by added tests | 3 | N26 (shifted native fill), N30 (finish on incomplete shadow), N36 (fractional source split) |
| Redundant by construction, no test added | 2 | N17: the coordinator's own session-open check duplicates the engines' checks (`apply_split`, `credit_dividend`, comparator `_action`), which refuse first and roll back; N24: the recovery reload latch duplicates the store re-read in `execute` and `checkpoint`, which refuses a changed head on its own |

Representative caught mutants: vendor `last_updated` after receipt accepted
(N01), USD-to-millions scaling removed (N02), lineage redelivery treated as new
(N05), as-of filter made strict (N06), identity remap accepted (N07), future
or 61-second quotes accepted (N09, N10), backdated execution minute accepted
(N11), reference availability boundary moved (N12), corporate action
received after its effective open (N14), coordinator rollback removed (N15),
one-sleeve receipt acknowledging an untouched partner (N16), journal overwrite
on an existing file (N19), stale append head accepted (N20), directory-sync
failure reported as definite failure (N21), truncation behind the anchor
accepted (N22), replay state hash unchecked (N23), comparator fill index
unchecked (N25), bridge re-issuing a fill or accepting a modified frame or a
rejected status (N27-N29), release verifier comparing dictionaries instead of
canonical bytes (N31), launch preflight opened (N32), `stale_event` never or
always (N33, N34), comparator terminal identity reopened (N35), unresolved
terminal NAV reported (N37).

### 16.7 Record maintenance, commits and next action

The status block names this section; the `test_boundaries.py` review-state
phrase is rotated to "Codex counter-review of section 16 pending".

| Commit | Scope |
|---|---|
| `5f7dc308` | Three lane regression tests (GDR-CR16-003 through GDR-CR16-005) |
| This record commit | Section 16, status block, `test_boundaries.py` pin rotation |

One push of this round after both commits exist, guarded on the remote head
still being `d522fad7`; never force. Next: Codex counter-reviews section 16 and
both Claude commits and rotates the pin; the owner decides GDR-CR16-001. No
GDR-1 or empirical, data, QC, broker, paper or live step starts from this
review. `docs/ACTION_PLAN_2026-08-20.md` and `docs/SESSION_HANDOFF.md` were
not edited in this round.

## 17. Codex section-16 counter-review and next bounded batch (2026-10-07)

### 17.1 Owner direction and exact reviewed snapshot

Owner request: counter-review Claude, implement the next ten milestones or
until ready for backtesting, and push only once. The subsequent explicit
answer is **"Lane record only; freeze root documents (recommended)"**.
Both agents therefore leave `docs/SESSION_HANDOFF.md` and
`docs/ACTION_PLAN_2026-08-20.md` frozen for Guidance rounds. Historical root
edits are preserved, not reverted or retroactively approved for main. This
resolves GDR-CR16-001's future handoff question; integration acceptance remains
separate. This record carries current lane status and the authorized sequence.

Verified clean designated worktree/branch and matching pushed review head
`a6cc4035361e883ad1ce60e18f2b456b06992de3`, descending from Codex publication
`d522fad7c3b849f008a369a7a6f458dfdcdc797c`. Reviewed every change in both commits:

| Claude commit | Disposition | Evidence |
|---|---|---|
| `5f7dc3087d5c0dd6d3a3e8c9db1aa2084121baf5` | accepted | All three exact regressions pass; isolated N26/N30/N36 mutants fail and restored originals pass; no source change |
| `a6cc4035361e883ad1ce60e18f2b456b06992de3` | accepted after correction | Findings retained; owner resolves handoff; environment identity and ingestion timing receive bounded corrections below; review status rotates only with this record |

CR16-002's Windows Git trust-root attribution is accepted. CR16-003/004/005
are accepted with independent red/green verification. CR16-006's distinction
between interpreter-bound and portable content identity is accepted; the strict
original verifier will not be weakened. CR16-007 is accepted with a causality
qualification: ingestion must follow validation availability, not merely a New
York replacement for the UTC publication date. CR16-008 remains shared/main
work, not a Guidance source defect; no shared behavior is changed. Claude's
archive-export validation is historical informational evidence, not permission
to validate this round outside the designated worktree.

### 17.2 Definitions of done, recorded before implementation

These are ten offline engineering increments, **not** GDR-0 freeze, GDR-1
source audit, GDR-3 empirical completion, SDK acceptance or trading authority.
No proposal economics, protected dates, rights or frozen candidate pins change.
Completion means implemented and focused-tested, pending independent Claude
review of the final pushed snapshot. Work stops if a required material choice
or external action cannot remain inside these definitions.

| Increment | Precise bounded definition of done |
|---|---|
| ENG-17 — native zero-fee protocol | Accept LEAN's zero-fee null-currency non-economic statuses, still reject non-USD economic fills/nonzero malformed receipts; primary-source contract and failing-then-passing regression |
| ENG-18 — native cancel lifecycle | Explicit requested `CancelPending` acknowledgement, no premature reservation release, idempotent duplicate and invalid-transition refusals |
| ENG-19 — multi-day strict reader | Read all exact sidecar frames through one LEAN reader enumeration regardless of source creation date; strict JSON/type/unknown-frame refusal with multiday regression |
| ENG-20 — receipt availability composition | Integration ingests each observation at the first decision after validated availability in receipt order; late/night/weekend receipts are not backdated or lost; current daytime fixture economics unchanged |
| ENG-21 — portable content identity | Separate environment-independent content identity beside exact environment-bound identity; verification reconstructs source/content, never ignores economic/code/calendar/authority changes |
| ENG-22 — deterministic source bundle | Build bounded local deterministic archive of explicitly inventoried source/candidate and exact synthetic sidecar; no credentials, SDK, upload, download or empirical inputs |
| ENG-23 — bundle integrity verification | Retained outer anchor plus exact member inventory/content validation; refuse traversal, duplicates, extras, altered sources and oversize/unsafe members; no archive code execution or automatic extraction |
| ENG-24 — callback evidence trace | Bounded hash-linked native protocol transcript with frame/order/fill/cancel evidence and explicit non-native-test labels; deterministic replay, duplicate and failure checks; no cloud-completion claim |
| ENG-25 — preparation CLI and readiness report | Local bundle export/verification and machine-readable separation of offline prepared, native unverified and empirical blocked; no launch/approval switch and original gates retained |
| ENG-26 — review release | Regenerate content-addressed review artifact only after source stabilizes; include bundle/portable identity and exact focused evidence; document missing native/comparator/settlement/data validation and next separately authorized action |

Native audit already reproduced zero-fee `QCC` status rejection and the reader
discarding all but four of 372 multiday frames; `CancelPending` is absent from
the protocol. Official LEAN source, not an engine run, establishes the callback
contracts. Native scheduling/overloads remain unverified. No installed LEAN,
AlgorithmImports, QuantConnect, clr, dotnet or Docker runtime was found.

### 17.3 Findings ledger and dispositions

Resolved findings remain visible. No P0 or P1 finding was identified in this
counter-review. The shared CR16-008 P2 finding remains open outside this lane.

| ID | Priority / status | Evidence and disposition |
|---|---|---|
| GDR-CCR17-001 | P2 / corrected | Native `on_order_event` rejected LEAN's `OrderFee.Zero` currency `QCC` even for zero-economic submitted/cancel statuses. Reproduced exact submission refusal, then added narrow control-event handling; economic fills remain USD-only. ENG-17. |
| GDR-CCR17-002 | P2 / corrected | LEAN emits `CancelPending`; neither adapter nor bridge supported it. Reproduced rejection with a partial position and 4494.5 cash still reserved. ENG-18 requires an ordered request acknowledgement, preserves reservations, and releases only at terminal cancellation. |
| GDR-CCR17-003 | P2 / corrected | LEAN keeps the source creation date while enumerating this single multiday file. Reader filtered out 368 of 372 exact rows. ENG-19 validates each frame and uses its own timestamp; creation-day filtering removed. Strict JSON also rejects previously accepted duplicate keys. |
| GDR-CCR17-004 | P3 / corrected | CR16-007's UTC publication-date ingestion also lost weekend/night observations, backdated delayed validations and ingested post-final or duplicate receipts. Actual durable command regressions failed before correction. ENG-20 uses the visible as-of archive suffix and checks its durable count/head, not a date-only timezone substitution. |
| GDR-CCR17-005 | P3 / improved | CR16-006's strict interpreter identity was correct but insufficient for cross-interpreter content comparison. ENG-21 adds a separate portable identity/verifier; original exact byte verifier remains strict. No runtime-parity claim. |
| GDR-CCR17-006 | P2 / unresolved execution limitation | Source/shim corrections do not prove pinned LEAN overloads, bindings, reader integration or transaction timing. Current public LEAN source scans before and after `OnData`; no confirmed scheduling defect was found, but no native/QC run occurred. Missing native comparator/actions and equity cash-settlement parity also remain explicit blockers. |

Primary contract evidence (checked 2026-10-07; current public source, **not** a
pinned engine acceptance):
[OrderFee.Zero](https://github.com/QuantConnect/Lean/blob/master/Common/Orders/Fees/OrderFee.cs),
[null currency](https://github.com/QuantConnect/Lean/blob/master/Common/Currencies.cs),
[backtesting brokerage](https://github.com/QuantConnect/Lean/blob/master/Brokerages/Backtesting/BacktestingBrokerage.cs),
[cancel request events](https://github.com/QuantConnect/Lean/blob/master/Engine/TransactionHandlers/BrokerageTransactionHandler.cs),
[fixed reader date](https://github.com/QuantConnect/Lean/blob/master/Engine/DataFeeds/TextSubscriptionDataSourceReader.cs),
[source reuse](https://github.com/QuantConnect/Lean/blob/master/Engine/DataFeeds/SubscriptionDataReader.cs),
[transaction scan ordering](https://github.com/QuantConnect/Lean/blob/master/Engine/AlgorithmManager.cs).

### 17.4 Implemented milestone notes

**ENG-17 technical:** Native adapter normalizes only zero-economic control
receipts with the documented null-currency sentinel. USD remains mandatory
for fills; malformed quantities, fees and unsupported currencies refuse.

Plain language: a normal engine status update no longer aborts the fixture,
but the fix does not allow foreign-currency trades or unexplained charges.

**ENG-18 technical:** Bridge records monotonic event IDs, submission and
cancel-pending acknowledgements, exact duplicate identities and terminal
cancel state. Cash remains reserved throughout the cancellation request.

Plain language: asking to cancel is distinct from a confirmed cancellation;
the same money cannot be spent twice while the request is pending.

**ENG-19 technical:** Strict bounded JSON parsing validates every known frame
from the single multiday source without filtering against source creation day.
The shim enumerates all 372 records and scans transactions before/after data.

Plain language: the prepared data file now reaches its later days instead of
silently ending after day one. This still needs a real engine integration run.

**ENG-20 technical:** Each fixed 10:00 decision ingests only the new validated
as-of archive prefix, retaining receipt order and first-capture deduplication.
Tests inspect actual command journals and preserve the original 93-day NAVs.

Plain language: information is not used before it arrives, nor lost because
it arrived overnight. This is not a new real-time capture service.

**ENG-21 technical:** Release v2 binds portable content separately from two
interpreter labels. Verification requires retained artifact/content anchors
and reconstruction; source, engine settings, economics and authority stay bound.

Plain language: another Python version can verify the same research content
without falsely claiming that the two execution environments are equivalent.

**ENG-22 technical:** A bounded deterministic ZIP contains 36 explicit
source/helper/candidate members, the exact synthetic sidecar and a manifest.
Sorted stored members have fixed metadata; source changes during reads refuse.

Plain language: the code and invented input can be handed over as one exact,
repeatable package. No credentials, licensed observations or SDK are bundled.

**ENG-23 technical:** Bundle verification checks the retained outer hash,
canonical inventory and current source bytes, refusing unsafe paths, duplicate
or extra members, compression, metadata changes and self-rehashed forgeries.
Publication uses no-overwrite hard links with explicit ambiguous-error handling.

Plain language: a changed or damaged package cannot pass just by recalculating
its own checksum. Verification never extracts or executes archive code.

**ENG-24 technical:** Bounded canonical hash-linked protocol records cover
frames, native bindings, issued fills and acknowledgements. Base replay has
380 records; duplicates do not add records, and capacity failures are atomic.

Plain language: callback/order discrepancies can be traced back to a specific
step. The trace is in-memory synthetic evidence, not proof of a cloud run.

**ENG-25 technical:** `prepare-bundle` and `verify-bundle` expose local-only
preparation with retained anchors and exclusive flags. Preflight separates
offline unreviewed source, native unverified execution and blocked empirical use.

Plain language: successful packaging means the package was prepared, not that
the strategy is ready to trade or permitted to start a backtest.

**ENG-26 technical:** The final source epoch is rebuilt into a content-addressed
v2 review release plus a separate source bundle. Exact reconstruction and
published portable-content verification passed; final hashes and range are below.

Plain language: Claude receives one stable review snapshot and explicit
remaining blockers, without confusing fixture completion with market evidence.

### 17.5 Validation and release

| Focused check | Result |
|---|---|
| Three exact Claude regressions | 3 passed; N26/N30/N36 mutants failed; restored tests passed |
| Native bridge/source tests | 20 passed in 33.582s; four isolated mutants caught/restored (QCC control, multiday reader, premature cancel cash release, trace capacity) |
| Receipt integration tests | Original code: 2 failed / 1 passed; corrected: 3 passed in 24.369s; actual durable ordering/restart and unchanged economic/NAV checks |
| Bundle, CLI, portable identity and boundaries | 36 passed in 0.811s after source freeze; bundle selection includes 21 tests and 44 subtests; three bundle mutants caught/restored (current-source comparison, compression precheck, overwrite publication) |
| Active-document guard via normal pytest/conftest | 69 passed in 1.06s |
| Python compilation | 63 lane source/test files compiled in memory, no bytecode publication; SDK imports not executed |
| Original proposal, candidate and root documents | Candidate/source pins verified; root Action Plan, Session Handoff and Feature Milestone Record unchanged |
| Exact release reconstruction/publication | 6 tests passed in 181.215s, including actual reconstruction; CLI local bundle/review publication both exit 0; published artifact portable-content reconstruction passed with changed interpreter label, runtime parity still false |

Temporary test failures in bundle/CLI assertions were macOS `/var` versus
resolved `/private/var` path expectations; tests were corrected to compare
resolved output roots. No production path behavior changed to hide them.
Author/subagent QA is not independent Claude acceptance. No full lane or
repository suite, Windows validation, SDK/native/QC run, provider read or
outcome access was performed. Source/provider, outcome, QC upload/job, broker,
paper/live and capital gates remain closed.

Source epoch is frozen at code-manifest SHA-256
`19175ad06bdb4b8e63b00e60181d0fa5d3e96c97c58cef0a552f57983ca49ecf`.
The source implementation commit is
`eba0fe5212726e95c01e61d3a30067c7518a91ee`, containing the counter-review,
ENG-17..25 and ENG-26 release machinery/validation. This closing record/artifact
commit finishes ENG-26; it changes no producing source. No intermediate push
was made. The sole push follows final root/branch/HEAD/status, diff and remote
head checks and targets only `codex/strategy-guidance-revision-drift`.

### 17.6 Exact release, exclusions and next action

Closing verification: 2026-10-08, 07:00 UTC. Final combined active-document
and lane-boundary selection: **75 passed in 1.19s**. Both published filenames
match their bytes; release/current-source identity and source-bundle
reconstruction were checked again after the producing-source commit.

Reviewed Claude range:
`d522fad7c3b849f008a369a7a6f458dfdcdc797c..a6cc4035361e883ad1ce60e18f2b456b06992de3`.
New producing-source range:
`a6cc4035361e883ad1ce60e18f2b456b06992de3..eba0fe5212726e95c01e61d3a30067c7518a91ee`.
Claude must review that source commit **and this closing record/artifact
commit** at the final pushed lane HEAD; the exact published SHA is also in the
owner-facing handoff and Git remote. No claim of independent acceptance of
this new batch is made.

All artifact paths below are under `research/guidance_revision_drift/releases/`:

| Identity | Value |
|---|---|
| Review JSON filename/SHA-256 | `0f22e92a7e9627d8b72b4ffc9aba4372225ab8c692e235952f17de71750ff029.json` (26,152 bytes) |
| Source bundle filename/SHA-256 | `4dd53e405596d8169d0fd4f83ae2166bb9c56102090e509b5e3a59b86b76fe69.zip` (423,249 bytes, 38 members) |
| Portable release content SHA-256 | `260096a102a672c74670fc113c4de4da4f02a99950bb4db62219b0b5ef9fec2c` |
| Interpreter environment SHA-256 | `8494750c6fbf1d47fb632bfe24d2d82cd401cc86b45cffbf9725613739a553e3` (CPython 3.12.14) |
| Original base/stress fixture report SHA-256 | `5012f6bc81cc7f9b6fe95bf51917f281b65b64ac97941445cb0c02e0d1839b3b` |
| Integrated fixture report SHA-256 | `c9efe5e08be5f38d9335f395c8c983e97474d889db937ef82cafb0b62785d120` |

Report hashes change with the producing source epoch even when fixture
economics do not. Original candidate, MD/PDF, calendar and sidecar pins remain
unchanged. The preceding `fccbef76...json` release is retained as historical
evidence; it is not claimed to reproduce against this new source.

Published JSON verification rebuilt all bounded recipes with a patched
descriptive Python-version label (`3.13.15`), retained the portable identity,
and reported `environment_matches=false`, `runtime_parity_verified=false` and
`qc_launch_allowed=false`. This tests label separation, **not** execution under
Python 3.13. Exact-environment reconstruction was separately tested. Every
artifact hash matches its filename; the source bundle reproduces current
source without extraction or execution. It intentionally excludes planning
documents and the SDK, so it is neither a standalone release-regeneration
checkout nor a ready-to-upload QC project.

No provider credentials/data, historical/protected outcomes, statistical
allocation, operator database, broker, scheduler, paper/live deployment,
PR/main merge, force push, SDK installation or QuantConnect attempt occurred.
This is ten implemented offline engineering increments, **not ready for an
empirical backtest** and not completion of original GDR-0..GDR-6 stages.

Next: Claude independently reviews the exact combined pushed snapshot and
performs the full lane validation; Codex counter-reviews every resulting
commit. After that, the owner must separately scope a pinned synthetic-engine
integration evaluation and/or zero-outcome source/rights audit before those
activities start. Real-data evaluation additionally needs the unresolved
freeze, dated inputs, engine/comparator/settlement contracts, evidence windows
and look/family allocation. No new implementation batch or monitor cycle
starts automatically. Both agents continue lane-record-only handoffs; root
documents remain frozen and historical edits remain for later integration review.

## 18. Independent Claude review of `a6cc4035..b3d54777`, 2026-10-08

### 18.1 Scope and method

Reviewed range: the two Codex commits after the section-16 push, `eba0fe52`
(section-17 counter-review, ENG-17..ENG-25 and the ENG-26 release machinery)
and `b3d54777` (section 17 closing record, the v2 review release JSON and the
source bundle ZIP), the fetched remote head. The worktree was clean and equal
to the remote head at the start, and no frozen root document was touched in
this range. Host, isolation and method are as in 12.1 and 16.1: every commit
read individually, every new or changed module and test read in full, every
pytest and mutation process network-denied under the proved `sandbox-exec`
profile, all validation in the designated worktree except the per-commit
informational run in a `git archive` export. No provider, QC, broker, paper or
live system was contacted; research looks 0; QC attempts 0. No LEAN SDK is
installed here, so native scheduling, bindings and cloud completion remain
unverified exactly as section 17 states.

### 18.2 Disposition of the section-17 counter-review

| Section-17 item | Claude disposition |
|---|---|
| Owner answer "Lane record only; freeze root documents" | Accepted as reported by Codex; it matches the reading under which Claude has worked since section 12. GDR-CR16-001 is closed for future rounds: both agents leave `docs/ACTION_PLAN_2026-08-20.md` and `docs/SESSION_HANDOFF.md` frozen, this record is the handoff for both, and the historical edits stay for integration review. This range confirms it: neither file changed. |
| `5f7dc308` accepted, `a6cc4035` accepted after correction | Accepted. |
| GDR-CCR17-001 (zero-fee `QCC` control receipts) | Accepted and verified: fills remain USD-only, control receipts admit the null-currency sentinel only with zero quantity, price and fee; the shim regression covers both directions. |
| GDR-CCR17-002 (`CancelPending` protocol) | Accepted and verified: a pending acknowledgement is required before the terminal cancellation, reservations are retained until then, duplicates are idempotent and out-of-order event IDs refuse (mutants Q01, Q02, Q05 caught). |
| GDR-CCR17-003 (multiday reader) | Accepted and verified: the reader keys every record to its own timestamp and all 372 frames reach the shim. |
| GDR-CCR17-004 (receipt-ordered as-of ingestion) | Accepted; it supersedes my GDR-CR16-007 wording, which proposed a date-only timezone substitution where availability order was the right rule. Durable-journal regressions pin night, weekend, delayed, tied and post-decision receipts. |
| GDR-CCR17-005 (portable content identity) | Accepted: `verify_release` stays strict and `verify_release_content` permits differences only in the two interpreter labels (18.5 reproduces the committed v2 artifact here that way). |
| GDR-CCR17-006 (unresolved native execution limitation) | Accepted as stated; nothing in this review changes it. |

### 18.3 Commit dispositions

| Commit | Scope | Disposition | Notes |
|---|---|---|---|
| `eba0fe52` | Section 17.1-17.5, ENG-17..ENG-25 source and tests, release v2 machinery | Accepted after correction | Two test pins added against its modules (GDR-CR18-002, GDR-CR18-003); 15 of the 24 round-three mutants targeting it were caught by its own tests, 7 are redundant by construction, 2 are now pinned |
| `b3d54777` | Section 17.6, v2 release JSON, source bundle ZIP | Accepted after correction | Both artifacts content-addressed and reproduced (18.5); the ZIP lacked a Git attribute (GDR-CR18-001, corrected in-lane) |

### 18.4 Findings ledger

| ID | Priority / status | Location | Finding, disposition and verification |
|---|---|---|---|
| GDR-CR18-001 | P3 / corrected | `b3d54777`, `research/guidance_revision_drift/.gitattributes`, `releases/4dd53e40...zip`; `test_boundaries.py` | The committed content-addressed ZIP had no Git attribute (`git check-attr -a` printed nothing), unlike the JSON artifacts under `*.json -text`; its byte identity relied on Git's binary heuristic rather than on the lane's declared contract. Added `*.zip binary` and pinned it in `test_source_byte_contract_has_lane_scoped_eol_rules`, which fails with the line removed. The attribute changes no tracked bytes and no hash. |
| GDR-CR18-002 | P3 / corrected | `eba0fe52`, `bundle.py::publish_bundle`; `test_bundle.py` | With the overwrite comparison removed (mutant P06), a tampered existing bundle still refused, but as `BundlePublicationUncertain` from the post-sync verification instead of the definite conflict, and the existing test accepted either. A caller that treats "uncertain" as "verify and retry" would loop on a destination it can never match. The tampered-bundle test now requires the "different bytes" message and asserts the exception is not the uncertain subtype. P06 now fails. |
| GDR-CR18-003 | P3 / corrected | `eba0fe52`, `lean_bridge.py::SyntheticOrderBridge.order_event`; `test_lean_bridge.py` | The new requirement that a fill receipt follow the order's submission acknowledgement had no test (mutant Q03 survived; `finish` would only have caught it at the end of the run). Added `test_fill_receipt_without_submission_acknowledgement_is_unsolicited`: the fill is refused with the shadow receipt still pending and the trace unchanged, and is accepted once the submission is acknowledged. Q03 now fails. |
| GDR-CR18-004 | P3 / documented | `eba0fe52`, `test_release_identity.py` | The identity-policy tests use the retained historical release `releases/fccbef76...json` as their fixture body. That is a sound choice today, but it binds the test to a historical artifact that section 17.6 describes as evidence, not as a maintained fixture; if that file is ever retired, the tests fail for a reason unrelated to the verifier. A copy under `tests/` or a built-in minimal body would decouple them. Not changed. |
| GDR-CR18-005 | P2 / documented, out of lane | repository suite | The repository suite excluding Analyst V2 is red on the same fifteen tests as at `8424a2b3` and `d522fad7`: four shared gates already red on `origin/main` (Analyst QC `Decimal(str(...))` sites, the stale `scripts/` classification manifest, Analyst QC bare sibling imports), ten Insider tests that refuse outside their own worktree, and the Target-Price Windows Git trust-root test (GDR-CR16-002). None involves a lane file and this range changed no shared file at all. Shared/main work, reported here and not fixed in this lane, as in GDR-CR12-013 and GDR-CR16-008. |

Scripted count from this table: P0 0, P1 0, P2 1, P3 4; corrected 3, documented 2.

### 18.5 Validation

| Check | Scope | Result |
|---|---|---|
| Lane selection at the pushed head `b3d54777` | worktree, network-denied | 401 passed, 1,110 subtests, 7:36 (under concurrent load) |
| Lane selection per commit (informational, `git archive` export) | `eba0fe52` | 401 passed, 1,110 subtests, 0 failed |
| Lane selection after the corrections | worktree, network-denied | 402 passed, 1,110 subtests, 14:05 (under concurrent load); an earlier run of the same tree failed only the lane gate because the status block had wrapped the pinned phrase across two lines, corrected by reflowing the status block |
| Repository suite excluding `tests/analyst_revisions_v2` | worktree at `b3d54777`, network-denied | 15 failed, 11,290 passed, 56 skipped, 28 warnings, 1,110 subtests, 1:42:37 under concurrent load; the fifteen failures are byte-identical to the sets in sections 12.4 and 16.5, and the pass count rose by exactly the 44 lane tests added since `d522fad7` |
| `python -m compileall -q research/guidance_revision_drift tests/guidance_revision_drift` | worktree | passed |
| `git diff --check` | worktree | passed |
| CLI `verify-bundle` on the committed ZIP with its filename as anchor | worktree, network-denied | exit 0, `verified_offline_content_only`, 423,249 bytes, bundle source manifest `19175ad0...`, preflight `blocked`; a wrong anchor exits 1 with `offline_command_failed` |
| Committed artifacts | `releases/0f22e92a...json` (26,152 bytes), `releases/4dd53e40...zip` (423,249 bytes, 38 stored members) | both filenames equal the SHA-256 of their bytes; no absolute path or user name in either; the v2 release rebuilt here differs in exactly two fields, `engine.python_version` (3.12.14 vs 3.13.15) and `identities.environment_sha256`; `code_sha256` `19175ad0...`, the portable content projection and `source_bundle.sha256` are identical; `verify_release_content` accepts the committed JSON with `environment_matches=false` and `runtime_parity_verified=false`, and the strict `verify_release` refuses it as designed |
| Analyst V2 directory | not run | out of lane, as in section 12.4 |

### 18.6 Mutation trials

Twenty-four single-behaviour in-memory mutants over the bundle, bridge protocol,
reader, release identity and ingestion changes, each run network-denied against
the test files that own the mutated module.

| Class | Count | Mutants |
|---|---:|---|
| Caught by Codex's tests | 15 | P03, P04, P05, P07, P08, Q01, Q02, Q04, Q05, Q07, R01, R02, R03, R04, I02 |
| Survived, now caught by added pins | 2 | P06 (tampered bundle reported as uncertain), Q03 (fill before submission acknowledgement) |
| Redundant by construction, no test added | 7 | P01 traversal parts (the path regex and the exact member set refuse first); P02 member set (the exact member comparison refuses any extra or missing member); P09 member date and P10 manifest canonical form (the canonical re-encode and member comparison refuse); Q06 finish acknowledgement count (every terminal order state already requires the acknowledgement per receipt); I01 archive prefix extension (an as-of replay archive can only grow as the decision advances); I03 durable count/head (the recovery engine's per-command result and post-state hashes already bind the archive) |

Representative caught mutants: compression accepted before read (P03),
altered source member accepted (P04), noncanonical archive encoding accepted
(P05), anchor unchecked (P07), inventory extension accepted (P08), event IDs out
of order (Q01), terminal cancel without the pending acknowledgement (Q02), trace
published before validation (Q04), repeated cancel-pending (Q05), malformed
fill request (Q07), `LEAN_version` dropped from the portable projection (R01),
content rebuild comparison removed (R02), identity or portable anchor unchecked
(R03, R04), ingestion looking one day ahead (I02).

### 18.7 Record maintenance, commits and next action

The status block names this section; the `test_boundaries.py` review-state
phrase is rotated to "Codex counter-review of section 18 pending".

| Commit | Scope |
|---|---|
| `73084917` | ZIP binary attribute and its pin (GDR-CR18-001); tampered-bundle refusal type (GDR-CR18-002); fill-before-submission-acknowledgement refusal (GDR-CR18-003) |
| This record commit | Section 18, status block, `test_boundaries.py` pin rotation |

One push of this round after both commits exist, guarded on the remote head
still being `b3d54777`; never force. Next: Codex counter-reviews section 18 and
both Claude commits and rotates the pin. The lane remains an offline
engineering candidate: no GDR-1 source audit, synthetic-engine evaluation,
empirical backtest, data, QC, broker, paper or live step starts from this
review; each needs the owner's separate scope, as section 17.6 states.
`docs/ACTION_PLAN_2026-08-20.md` and `docs/SESSION_HANDOFF.md` were not edited
in this round and stay frozen for both agents.

## 19. Codex counter-review and remaining readiness work, 2026-10-08

### 19.1 Exact trigger and authorized scope

The monitor consumed completed Claude review head
`c0137c518277c8a9a87af51f52add3eccd088617`, fetched from the matching lane
ref and equal to the clean designated worktree HEAD. Its exact ancestor is
Codex baseline `b3d5477740534da9a2428e9c44e4f4303bb33ff0`. The ordered
review range contains `73084917deaf5ec129b3d459b5afa2386a67624f` and
`c0137c518277c8a9a87af51f52add3eccd088617`; section 18 explicitly hands the
completed review back to Codex. Earlier monitor baselines are historical.

The owner's 2026-10-08 instruction is to counter-review this push and build
until backtest-ready, without another artificial milestone quota. It permits
substantive offline software preparation, not a native engine installation,
evaluation, provider/rights audit, outcome look or QC launch. Only this record
and lane-owned source/tests/documentation may change. Root documents remain
frozen. All changes accumulate for one final combined push; an owner-input
blocker pauses publication rather than publishing a partial round.

### 19.2 Remaining gaps and definitions of done before implementation

Current source checks native inventory/cash only at the final callback. A
temporary mismatch that disappears before the end can therefore evade that
check. This is a concrete integration gap that can be addressed with the
existing exact synthetic accounting, without choosing financial assumptions.

| Work | Bounded definition of done and evidence |
|---|---|
| Review corrections | Counter-review both Claude commits and every CR18 finding; reproduce the three regression pins with focused tests/mutants; retain per-commit dispositions and P0-P3 ledger. Correct minor commit attribution: the ZIP attribute is in `73084917`, its boundary-test pin is in `c0137c51`. |
| Identity-policy test ownership | Replace the historical release dependency of CR18-004 with a minimal explicit unit body. Preserve hostile identity/authority/type mutations and keep actual release reconstruction owned by its existing separate tests. No production identity policy change. |
| Native account checkpoints | Before each native callback advances the bridge, verify whole native SYN-GDR inventory and immediate-envelope cash against the acknowledged shadow state. Cash equals settled cash plus exact outstanding receivables, never available cash or reservation-adjusted cash. Reject malformed/unequal input or pending acknowledgements without index/trace/state effects. Trace successful observations, preserve existing end checks, and test partial fills, transient drift, unsettled sale proceeds and later dated settlement. This verifies adapter enforcement only, not native cash-account settlement. |
| Reviewable local handoff | Focused source/bridge/identity regressions, import/document checks, compilation, exact frozen-document/candidate checks and diff/status; current source evidence and next exact gate retained here. No complete lane/repository suite. |

Dependencies still required for actual order-based empirical readiness are a
pinned native LEAN/Python-.NET evaluation, separately designed native matched
SPY/account/corporate-action integration, validated equity settlement and
rights-cleared dated guidance/market/reference/action inputs. The original
parameter freeze, source audit, family/look allocation and evidence windows
are unresolved. A stronger synthetic checkpoint cannot close any of these.
No runtime is installed or run under this work definition. Once the safe
offline changes above are verified, the next necessary external/owner gate
must be presented to the owner before continuing or publishing.

### 19.3 Counter-review dispositions and retained findings

| Claude commit | Disposition | Evidence |
|---|---|---|
| `73084917deaf5ec129b3d459b5afa2386a67624f` | accepted | Complete diff and affected contracts inspected. Three exact correction regressions passed; all three guard-removal mutants failed at the intended guard and restored green. No production logic changed. |
| `c0137c518277c8a9a87af51f52add3eccd088617` | accepted-after-correction | Complete record/test diff inspected; baseline ancestry and completed handoff verified. Section 18 is retained. This section corrects minor commit attribution and CR18-004's test ownership. Claude's full-suite results remain attributed to Claude; Codex did not repeat them. |

| ID | Priority / status | Evidence, reason and disposition |
|---|---|---|
| GDR-CR18-001 | P3 / accepted, corrected | `*.zip binary` is a valid lane-local byte contract. The exact boundary pin fails without it; artifact bytes and hashes are unchanged. The attribute is in `73084917`, but the boundary pin is in `c0137c51`. |
| GDR-CR18-002 | P3 / accepted, corrected | The tampered destination regression requires definite `different bytes` refusal, not uncertain publication. Removing the conflict guard makes it fail; no overwrite occurs. This distinguishes a retryable ambiguous result from an immutable conflict. |
| GDR-CR18-003 | P3 / accepted, corrected | A fill before submission acknowledgement is refused with pending receipt/trace/state retained; acknowledgement then permits the exact receipt. Removing the acknowledgement guard makes the pin fail. |
| GDR-CR18-004 | P3 / corrected here | Identity-policy tests depended on a historical artifact unrelated to their unit contract. Replaced it with an explicit representative body, retaining all hostile mutations. Added filesystem-independent fixture and canonical Boolean/integer type checks. Restored-file and loose-equality mutants fail; actual release reconstruction remains separately owned. Historical releases are not deleted. |
| GDR-CR18-005 | P2 / accepted as reported, out of lane | Claude's fifteen shared/Insider/Target-Price failures remain reported, not fixed or rerun here. Review range changes only lane files and this record; it cannot correct other lanes' worktree restrictions or shared contracts. |
| GDR-CCR19-001 | P3 / corrected documentation attribution | Section 18.7 and `73084917` message group attribute and boundary pin under the first commit; actual diff places the pin in the second. Exact ownership is recorded above without rewriting history. |
| GDR-CCR19-002 | P2 / corrected source candidate | End-only native cash/inventory checks miss temporary drift. Two new tests reproduced six failing subcases before implementation. Per-frame draft checkpoint enforcement now refuses transient mismatch, nonfinite/fractional/negative scalars, aliases, partial inputs and trace exhaustion without consuming effects. Immediate cash includes receivables; original proposed economics remain unchanged. |
| GDR-CCR19-003 | P2 / native validation pending | No pinned native runtime/binding run exists; no native matched-SPY/actions/equity-settlement or rights-cleared real-data adapter exists. Python/shim checks cannot establish these. At the paused checkpoint this required owner scope before platform work or publication. Section 19.6 now resolves authorization narrowly for publication and post-review synthetic QC evaluation, not the missing validation or empirical readiness. |

No P0/P1 issue was identified. CR18 findings retain P0 0, P1 0, P2 1,
P3 4; this counter-review adds one corrected P3 and two P2 items (one
corrected source candidate, one blocked validation requirement). Shared
failures and the blocker remain visible. Review-quality assessment: 8/10 for
the bounded offline scope; no empirical/native-readiness rating is implied.

### 19.4 Implemented behavior and current boundary

Technical: native `on_data` supplies cash/inventory to bridge `step`. Exact
checks run before shadow advancement and only after prior receipts clear.
Checkpoint and frame trace publication occur on the same draft, preserving
atomic refusal even if the second trace record exceeds capacity. The native
source requires all 372 checkpoints at completion; base native-source trace
count is 752. Offline protocol-only diagnostics remain explicit (zero account
checks / 380 base trace records). Settlement parity stays false. The unit
identity fixture no longer depends on retained release availability.

Plain language: the fixture now detects an unexplained balance or share
change immediately, even if it later disappears. Money waiting to settle is
still accounted for, but it is not treated as spendable by the shadow engine.
This makes software checks stronger; it does not show that the real engine
works or that the strategy makes money.

The new source epoch supersedes the section-17 source bundle for current-source
verification. Old content-addressed artifacts remain historical and must
refuse current-source verification. No provider/account credential, operator
database, broker, scheduler, protected outcome, research look, QC job, PR or
main merge was used. The dependency audit found CPython 3.12.14; AlgorithmImports,
QuantConnect and clr absent, and no dotnet, Docker or LEAN executable on PATH.
No dependency installation or supported-Windows/native run was attempted.

### 19.5 Focused validation, local state and resume handoff

| Check | Result |
|---|---|
| Three exact Claude regression pins | 3 passed in 1.32s; three guard-removal mutants failed at their intended checks and restored green |
| New temporal checkpoint regressions before correction | Six failing subcases (cash/inventory drift plus fractional, NaN, infinite and negative account values); no fail-open acceptance after correction |
| Source callbacks and bridge protocol, final producing tree | 24 passed, 40 subtests, 52.07s; full 372-frame base and partial/cancel scans, sale-to-settlement continuity, exact fee/cash checks, temporal drift and draft rollback |
| Identity-policy fixture | 6 passed, 18 subtests, 0.60s; filesystem-dependency and loose Boolean/integer-equality mutants failed and restored green |
| Active documents, lane imports/boundaries and identity tests | 81 passed, 18 subtests, 1.48s under normal pytest isolation |
| Python compilation | 63 source/test files compiled in memory; no SDK imports or bytecode publication |
| Current source bundle | Built/verified in memory, 426,246 bytes, 38 members; old `4dd53e40...zip` correctly refuses as not reproducing current source; no extraction or publication |
| Frozen candidate/plan/root documents | Original candidate and MD/PDF pins verified; Action Plan, Session Handoff, Feature Milestone Record, CLAUDE and AGENTS byte-unchanged against the baseline |
| Git attributes/diff/status | ZIP binary set, text/diff/merge unset; diff check passed; only intended lane files/record changed |

The identity-mutation harness's first loose-type trial was cancelled when a
copied-global seam bypassed its mock and began local synthetic reconstruction;
the corrected live-global, unit-isolated trial caught the mutant. This was not
an empirical look or QC attempt. No full lane/repository suite was rerun, and
Claude's earlier full-suite results are not relabelled as Codex validation.

Producing-source commit is local-only
`8e5714a2a2ff89c50a01cbe958d298f0ade39e9b`. Its range is
`c0137c518277c8a9a87af51f52add3eccd088617..8e5714a2a2ff89c50a01cbe958d298f0ade39e9b`.
Source manifest SHA-256 is
`4e9389e994c0e7063d68430052d2cef2280e0f31356ce2fc5f855878351f9afc`.
The in-memory deterministic bundle SHA-256 is
`1c18e76bc3e61edde2ac119de22eab1c9a9afe4eded9c743f545b48279b990f3`;
it was not saved as a new release. The candidate canonical identity remains
`b52aedd6ca6dea4a14bc46ddb6c09a6d36bbf994fc21edb9ddb916194f03ad3c`.
The exact closing record commit follows and is identified by local Git HEAD.

**At the paused checkpoint, publication was withheld: zero pushes this round.**
The remote lane still named consumed Claude head `c0137c51`, not the new local source. This
record/test-pin commit is a durable local checkpoint, not a completed remote
handoff or backtest-ready release. Monitor state must retain the consumed
trigger and pause for owner input; it must not re-review that same push or
treat a future Codex publication as a Claude trigger.

Next required decision: scope a pinned **synthetic-only native-engine
integration evaluation**, specifying local runtime setup/execution versus
QuantConnect upload/job, exact candidate/source and allowed packaging. The
recommended authoritative target is order-based QC after exact-source Claude
review, limited to the fixed invented sidecar, no provider data or empirical
outcomes, every launch retained, maximum three unsuccessful attempts before
Mia/owner recovery. This paragraph grants no such action. The owner must also
decide how to publish the review snapshot at this blocker without changing the
one-push agreement by inference; no partial publication occurs automatically.

Resume in the exact worktree/branch in section 1. First verify local HEAD,
remote head and clean status; read sections 18 and 19. Keep the two Claude
dispositions and all corrected/open findings, preserve the local source and
closing-record commits, and continue this same cycle only after the owner
provides its exact next scope. Do not repeat ENG-1..26, install a runtime,
access credentials/data/outcomes, create a new branch, switch worktrees or
push while this blocker is unresolved. Native comparator/actions, cash-account
settlement, rights/availability audit, candidate freeze, evidence dates and
family/look allocation remain necessary before empirical readiness.

### 19.6 Owner approval, publication closure and next exact review gate

On 2026-10-08 the owner answered **yes** to: "May I publish this checkpoint
as the round's single push for Claude, then—after review—perform a
synthetic-only QuantConnect upload/run, with no real data and at most three
unsuccessful attempts?" This supersedes only section 19.5's publication and
synthetic-engine authorization blocker. It permits the accumulated checkpoint
to be published now, despite empirical readiness remaining blocked, without
an intermediate or second push in this round. It is not a specification
freeze, data/rights audit authorization, empirical outcome look or permission
to run the proposed strategy on market data.

The publication range starts at consumed Claude head
`c0137c518277c8a9a87af51f52add3eccd088617` and includes producing source
`8e5714a2a2ff89c50a01cbe958d298f0ade39e9b`, closing record/test pin
`ad075cf2dae64729d1d10f8e9e43c838c1f2a89f`, and this documentation-only
approval closure. The closure's Git HEAD identifies the exact review snapshot;
the monitor retains the verified remote publication SHA. Source manifest,
in-memory bundle and original candidate identities remain those in section
19.5. No new artifact or code is generated by this approval. Read-only final
publication audit confirmed lane-only changes, unchanged candidate/plan/root
documents and the exact source manifest SHA; no execution/data authority or
secret values were added to source. The documentation-only approval closure
passed focused active-document and lane-boundary checks: 75 passed in 1.12s;
`git diff --check` passed. No source suite or cloud action was repeated.

Next authorized sequence: verify root, branch, HEAD/status and unchanged remote
`c0137c51`; make exactly one non-force push only to the matching lane ref;
verify that remote head; re-arm the existing monitor with that exact new
baseline; wait for Claude's explicit completed pushed review of it; then
counter-review every review commit and finding in the same serialized lane.
A local commit, dirty work, partial review or this Codex push is not a trigger.
Do not start implementation or QC while Claude owns the lane or ownership is
ambiguous. Claude retains full independent lane validation; Codex uses focused
checks, not a full lane/repository suite.

Only after that review is accepted or accepted-after-correction may Codex
package/upload the exact reviewed source and fixed invented 372-frame sidecar
for a **synthetic-only order-based QuantConnect integration evaluation**.
Record source/package hashes, project, compile/run IDs, engine/binding details,
every launch and terminal result. No provider credentials, source capture,
market/reference/action download, empirical/protected outcomes or real data
may enter this evaluation. No local runtime/dependency installation is
authorized by this cloud-only approval. Existing authenticated QC access may
be used for the scoped upload/run; unavailable access, required purchase or
broader rights/account changes return to the owner.

The attempt ledger starts at zero. A compile failure, runtime error or other
unsuccessful terminal launch counts; stop after at most three unsuccessful
attempts for this exact candidate. Then use authenticated controllable Mia
when available, otherwise ask the owner to use Mia. Retrieve and diff Mia's
source against the exact local candidate before accepting or porting only
verified lane-specific corrections. Do not accept economic changes by
inference. A completed synthetic QC job validates only the tested integration;
it cannot establish matched-SPY/action/settlement parity, point-in-time data,
GDR-0..6 completion, empirical backtest readiness or market edge.

The immutable draft's null decisions, false permissions and zero allocated
looks remain unchanged; this external human authorization is retained here,
not self-certified into the proposed research candidate. All other source,
rights, data, family/look, protected-date, account, paper/live, broker and
capital gates stay closed. No operator database, broker, scheduler, PR,
main merge, cross-lane mutation or force push is permitted. Pause the monitor
after the scoped cycle completes or an owner-input blocker; stay quiet for
unchanged/non-actionable remote state. A subsequent round retains its own
single-push agreement; this closure does not authorize a second publication
of the current round.

## 20. Independent Claude review of `c0137c51..9df3a12f`, 2026-10-09

### 20.1 Scope and method

Reviewed range: the three Codex commits after the section-18 push,
`8e5714a2` (section-18 counter-review, per-frame native account checkpoint,
identity-policy fixture decoupling), `ad075cf2` (section 19.1-19.5 record and
lane-gate rotation) and `9df3a12f` (section 19.6, the owner-approval closure),
the fetched remote head. The worktree was clean and equal to the remote head
at the start; no frozen root document changed in this range. Host, isolation
and method are as in 12.1: every commit read individually, every changed
module and test read in full, every pytest and mutation process network-denied
under the proved `sandbox-exec` profile, all validation in the designated
worktree except the per-commit informational run in a `git archive` export. No
provider, QC, broker, paper or live system was contacted; research looks 0; QC
attempts 0. Two public primary sources were read for 20.4: LEAN's
`BacktestingBrokerage.cs` (master) and the QuantConnect documentation pages on
custom-data examples and project files, all on 2026-10-09. No LEAN SDK is
installed here.

### 20.2 Disposition of the section-19 counter-review

| Section-19 item | Claude disposition |
|---|---|
| `73084917` accepted, `c0137c51` accepted after correction | Accepted. |
| GDR-CCR19-001 (attribution) | Accepted. Verified with `git show`: `73084917` changed `.gitattributes`, `test_bundle.py` and `test_lean_bridge.py`; the `*.zip binary` assertion in `test_boundaries.py` landed in `c0137c51`. My `73084917` message and section 18.7 said otherwise because I had not staged that file in the first commit. |
| GDR-CR18-004 correction (identity fixture decoupling) | Accepted: the unit fixture is now an explicit body with the mutated fields and scalar types, and a new test forbids file reads during fixture construction; actual reconstruction stays in `test_release.py`. The historical `fccbef76...json` release is retained. |
| GDR-CCR19-002 (per-frame account checkpoint) | Accepted after verification (20.5, 20.6). Native cash is compared with shadow settled cash plus outstanding receivables, which is the right envelope for LEAN's immediate settlement model, and the check runs on the step draft before the frame's shadow effects. |
| GDR-CCR19-003 (native validation pending) | Accepted as stated; 20.4 adds concrete pre-launch evidence. |
| Section 19.6 owner approval | Recorded by Codex from its own owner channel: on 2026-10-08 the owner answered yes to publishing this checkpoint as the round's single push and, after Claude's exact-source review and Codex's counter-review, a synthetic-only order-based QuantConnect upload and run on the fixed invented sidecar with at most three unsuccessful attempts and Mia recovery. Claude has no independent copy of that exchange; listed in 20.7 for the owner to confirm where both roles can read it. This review is the "Claude exact-source review" gate it names: acceptance here means the reviewed source passed software review, not that native execution, cloud packaging or empirical readiness is established. |

### 20.3 Commit dispositions

| Commit | Scope | Disposition | Notes |
|---|---|---|---|
| `8e5714a2` | Per-frame native account checkpoint, identity fixture, README updates | Accepted after correction | One bridge-level pin added (GDR-CR20-002); 8 of 12 checkpoint mutants caught by its own tests, 3 now pinned, 1 unreachable; export run 406 passed |
| `ad075cf2` | Section 19.1-19.5, lane-gate rotation | Accepted | Documentation and pin only; manifest `4e9389e9...` and bundle `1c18e76b...` claims reproduced (20.5) |
| `9df3a12f` | Section 19.6 owner-approval closure | Accepted | Documentation only; owner direction listed for confirmation in 20.7 |

### 20.4 Findings ledger

| ID | Priority / status | Location | Finding, disposition and verification |
|---|---|---|---|
| GDR-CR20-001 | P2 / documented, pre-launch risk for the authorized synthetic QC evaluation | `lean/main.py` (`DATA_PATH`, `get_source`, `initialize`); section 19.6 | The native source reads its invented sidecar with `SubscriptionTransportMedium.LOCAL_FILE` from `Path(__file__).with_name("gdr-synthetic.jsonl")` and re-reads it in `initialize` with `os.open`, from a `main.py` nested at `research/guidance_revision_drift/lean/`. Public evidence read on 2026-10-09: the QuantConnect custom-data example returns `SubscriptionTransportMedium.OBJECT_STORE` for backtests and `REMOTE_FILE` for live, and does not mention a local file; the project-files page lists `.cs`, `.ipynb`, `.py`, `.html` and `.css` as supported types (no `.jsonl`), says Python projects start with `main.py`, and caps files at 32 KB on the Free tier, while `simulation.py` is 45,352 bytes and the sidecar 43,135 bytes. None of this proves the cloud run fails, and LEAN's documented scan order is not in question. The fee path is consistent: `BacktestingBrokerage.Scan` keeps a non-zero fill-model fee and substitutes the fee model only for a zero-fee `Filled` event, which `ConstantFeeModel(0)` makes a zero USD fee the adapter already accepts. Because every compile or runtime failure spends one of the three allowed attempts, Codex should record a packaging plan before the first launch that settles data transport (for example the exact sidecar in the Object Store, or frames generated in code from `fixture_frames()`), the root entry point that imports the nested algorithm, the organization's file-size tier and how the non-`.py` sidecar is carried. If that plan changes any reviewed source byte, the upload is no longer "the exact reviewed source" of 19.6 and needs review first. Not changed here: the transport is a design choice for Codex, and the source passes its offline contract. |
| GDR-CR20-002 | P3 / corrected | `8e5714a2`, `lean_bridge.py::SyntheticOrderBridge._check_account`; `test_lean_source.py` | Section 19.3 credits the per-frame checkpoint with refusing "nonfinite/fractional/negative scalars", but its finite, non-negative and whole-share guards were never what refused them in the lane tests: mutants S04, S05 and S06 each survived. On the native path `to_decimal` rejects NaN and Infinity before the bridge sees them, and the shadow invariants (settled cash and receivables non-negative, integer quantity) turn any negative, fractional or infinite observation into a plain mismatch. Refusal therefore stayed fail-closed, but the classification the record names was untested, and with the finite guard removed a NaN quantity would surface as `decimal.InvalidOperation` rather than a bridge refusal. Added `test_bridge_classifies_malformed_account_scalars_itself_atomically`: a direct `step` with NaN, Infinity, signalling NaN, negative quantity or cash, or half a share must raise "malformed native account observation" with no checkpoint, trace or shadow effect. S04, S05 and S06 now fail. |

Scripted count from this table: P0 0, P1 0, P2 1, P3 1; corrected 1, documented 1.

### 20.5 Validation

| Check | Scope | Result |
|---|---|---|
| Lane selection at the pushed head `9df3a12f` | worktree, network-denied | 406 passed, 1,124 subtests, 8:27 |
| Lane selection at `8e5714a2` (informational, `git archive` export) | export | 406 passed, 1,124 subtests, 0 failed |
| Lane selection after corrections | worktree, network-denied | 407 passed, 1,130 subtests, 6:31 |
| Repository suite excluding `tests/analyst_revisions_v2` | worktree at `9df3a12f`, network-denied | 15 failed, 11,295 passed, 56 skipped, 28 warnings, 1,124 subtests, 1:11:32; the fifteen failures are byte-identical to sections 12.4, 16.5 and 18.5 (out of lane, GDR-CR18-005), and the pass count rose by exactly the five lane tests added in `8e5714a2` |
| Current-source manifest and bundle | worktree, network-denied | source manifest `4e9389e994c0e706...` and bundle `1c18e76bc3e61edd...` (426,246 bytes, 38 members) reproduce exactly; the section-17 bundle `4dd53e40...zip` refuses current-source verification as section 19.4 says |
| `python -m compileall -q research/guidance_revision_drift tests/guidance_revision_drift` | worktree | passed |
| `git diff --check` | worktree | passed |
| Analyst V2 directory | not run | out of lane, as in section 12.4 |

### 20.6 Mutation trials

Twelve single-behaviour in-memory mutants over the per-frame account
checkpoint, each run network-denied against `test_lean_source.py` and
`test_lean_bridge.py`. The `lean/main.py` end-of-run checkpoint-count check
was not mutated (its module is re-imported under the SDK shim per test); it is
pinned by Codex's explicit 371-checkpoint refusal in
`test_real_callbacks_submit_native_orders_emit_exact_fees_and_finish`.

| Class | Count | Mutants |
|---|---:|---|
| Caught by Codex's tests | 8 | S01 cash comparison removed, S02 inventory comparison removed, S03 receivables excluded from the immediate-cash envelope, S08 checkpoint skipped, S09 partial input silently skips the check, S10 checkpoint count not incremented, S11 checkpoint trace record not published, S12 check run on the live object instead of the step draft |
| Survived, now caught by the added pin | 3 | S04 finite guard, S05 non-negative guard, S06 whole-share guard (GDR-CR20-002) |
| Unreachable by construction, no test added | 1 | S07 fixed-issuer guard: the bridge's fixed fixture only ever submits orders for one invented issuer, so a second shadow position cannot arise |

### 20.7 Owner confirmations, commits and next action

For the owner to confirm where both roles can read it (each is recorded only by
Codex from its own channel): (a) the 2026-10-08 instruction to counter-review
section 18 and build until backtest-ready without a milestone quota (19.1);
(b) the 2026-10-08 "yes" to publishing this checkpoint as the round's single
push and, after review, a synthetic-only order-based QuantConnect upload and
run on the fixed invented sidecar, at most three unsuccessful attempts, then
Mia or the owner (19.6). Claude's instruction in this session was to review all
unreviewed commits on this lane, which is consistent with both.

The status block names this section; the `test_boundaries.py` review-state
phrase is rotated to "Codex counter-review of section 20 pending".

| Commit | Scope |
|---|---|
| `e3a238c6` | Bridge-level malformed native-account classification pin (GDR-CR20-002) |
| This record commit | Section 20, status block, `test_boundaries.py` pin rotation |

One push of this round after every commit exists, guarded on the remote head
still being `9df3a12f`; never force. Next: Codex counter-reviews section 20 and
every Claude commit, rotates the pin, and resolves GDR-CR20-001's packaging
plan before any cloud launch. Under 19.6 the synthetic-only QC evaluation may
start only after that counter-review accepts this review. No GDR-1 source
audit, empirical backtest, real data, broker, paper or live step starts from
this review. `docs/ACTION_PLAN_2026-08-20.md` and `docs/SESSION_HANDOFF.md`
were not edited and stay frozen for both agents.
