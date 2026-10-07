# Guidance Revision Drift - lane implementation record

Status: **Offline engineering batch ENG-1..ENG-6 implemented; independent review pending.**
Current scope/evidence are sections 7 through 11 (2026-10-07). Sections 2 through 6 preserve
the initial GDR-0A snapshot and its then-current restrictions; section 7
supersedes only its stop-for-review and no-push sequencing for this batch.
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
  `docs/SESSION_HANDOFF.md` retains its generic-workflow handoff role. No
  same-branch Claude exception, standing push permission or root-handoff
  exemption is inferred from the other four lanes' arrangements.

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
