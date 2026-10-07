# Guidance Revision Drift - lane implementation record

Status: **GDR-0A offline implementation candidate; independent review pending.**
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
