# Development session handoff

Prepared: 2026-08-03T13:30:00-07:00

Audience: Codex, Claude Code, and the repository owner after moving to another
computer.

Purpose: record the independently reviewed and corrected Phase 2 hygiene
milestone, safety posture, Git topology, validation, local-data observations,
and next step. This file contains no secret values, brokerage account numbers,
or licensed market data. Every machine-local and time-sensitive statement
must be verified after a move.

## 1. Read this first

On the new computer, clone or update the repository and give either agent this
instruction:

```text
Read CLAUDE.md, AGENTS.md, docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md,
and docs/SESSION_HANDOFF.md completely before acting. Then read
docs/ACTION_PLAN_2026-08-02.md — the owner-adopted go-to plan that alone
decides sequencing (adopted 2026-08-02; individual plans are archived in
docs/reference/ and remain authoritative only for milestone definitions).
Then docs/GENERAL_READINESS_STATUS.md and docs/ARCHITECTURE_DEBT.md.
Establish the actual remote branches, HEAD, worktree, Python version,
ignored-data state, credential presence, paper-account identity, and
scheduler state. Preserve uncommitted work. Do not infer live trading,
model promotion, or autonomous execution authority. Report any drift from
the handoff before continuing. GR-1C is implemented and independently
reviewed; do not redo it. UI feature controls (Phase 1) are fully merged:
implementation PR #116, review chain PR #117 at 661a7d4. Do not redo or
bypass that review. Action-plan Phase 2 hygiene (AP-1, AP-2, AP-4) is
COMPLETE: implemented at 34ce463, independently accepted after correction at
36c69d3, MERGED as PR #118 at 8278510, and third-round confirmed by Claude
(red-proof on the exact snapshot, reverse-mutation, evidence checks) at
5cffb1f on local branch user/claude/phase2-confirmation-20260803. Do not
reimplement or repeat that review. The owner granted the Phase 3 GR-1D
go-ahead on 2026-08-03; GR-1D is IMPLEMENTED at dce5e23 on LOCAL-ONLY
branch user/claude/gr-1d-reconciliation-extraction-20260803 and awaits
independent review — do not reimplement it, and do not push or merge it
without owner approval. GR-1E assessment follows the GR-1D review.
```

Initial commands:

```powershell
git fetch --all --prune
git status --short --branch
git log --all -20 --oneline --decorate
git branch --all --verbose
```

Do not reset, clean, delete, or overwrite a dirty worktree merely to reproduce
this snapshot.

### Canonical cross-computer synchronization rule

This tracked file is the canonical development-session state. After every
completed review, feature, or milestone — and after any material change to
branch availability, open issues, validation, authorization, machine-local
state, or the next step — update and commit `docs/SESSION_HANDOFF.md`
separately from the implementation/review commits it describes.

Do not use a loose copied session file as the normal computer-transfer method.
Cross-computer synchronization is complete only when this handoff commit and
every commit needed to resume are verified on the approved Git remote. Pushing
or merging still requires explicit owner authorization; until then, mark the
branch local-only and warn that another computer cannot fetch it. The reusable
workflow is in `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`.

## 2. Critical Git snapshot

Repository:

```text
https://github.com/SheltonChen2017/trading_agent.git
```

State after the merged and confirmed Phase 2 hygiene milestone (2026-08-03):

```text
origin/main and local main:
  40af55c  Merge PR #119, the Phase 2 third-round confirmation
           (PR #118 at 8278510 merged the reviewed Phase 2 chain earlier)

GR-1D (ACTIVE), based on main 40af55c:
  branch: user/claude/gr-1d-reconciliation-extraction-20260803 — LOCAL
          ONLY, NOT PUSHED; another computer cannot fetch it until the
          owner authorizes a push
  implementation: dce5e23  (reconciliation extraction behind call-time
          ReconciliationDeps; details in section 5)
  handoff: the commit containing this text
  status: awaiting independent review

Phase 2 hygiene, based on main 661a7d4 — COMPLETE AND MERGED:
  implementation branch: user/claude/phase2-hygiene-20260803
  implementation: 34ce463
  implementation handoff: c8271a1
  review branch: codex/review-phase2-hygiene-20260803
  review correction/report: 36c69d3
  push-state correction: 35fc2dd
  merge: 8278510 (PR #118; origin/main)
  disposition: accepted after one resolved P2 and two resolved P3 findings;
               no P0/P1 and no open issue

Claude third-round confirmation, based on merged main 8278510:
  branch: user/claude/phase2-confirmation-20260803 — LOCAL ONLY until the
          owner authorizes a push
  confirmation: 5cffb1f (review-report addendum: commit dispositions,
          red-proof on exact 34ce463, reverse-mutation, PH2REV-002/003
          evidence checks, merged-tree full-suite validation, 9/10 review
          rating, one documented residual boundary)
  handoff: the commit containing this text

UI implementation, pushed and merged:
  branch: user/claude/ui-feature-controls-20260802
  implementation: edc87e9
  implementation handoff: 47effd7
  merge: 4c8e959 (PR #116)

Codex independent UI review:
  branch: codex/review-ui-feature-controls-20260803
  review correction/report: a6d5254
  disposition: accepted after two resolved P2 findings and one P3 handoff
               correction; no P0/P1 and no open issue

Claude third-round confirmation (2026-08-03), based on Codex tip 1bdbd4e:
  branch: user/claude/ui-review-confirmation-20260803 — PUSHED AND MERGED
  as PR #117 (661a7d4), carrying the Codex review commits as ancestors
  contents: independent re-verification of both P2 corrections (all three
  new tests red on pre-correction 4c8e959; 3/3 reverse-mutation sweep
  caught: ignored source flag, non-rebinding editor state, missing
  rerun-after-save), plus one new finding fixed in this round: the
  runtime-identity non-repo test was environment-sensitive (an in-repo
  --basetemp made it fail on a clean worktree and pass vacuously on a
  dirty one); hardened with GIT_CEILING_DIRECTORIES

Original GR-1C implementation and review, pushed and merged:
  b4d9b1f  Claude validation extraction and dependency injection
  465df8d  Codex independent review corrections
  5750af3  review/handoff process documentation
  091efc2  Merge PR #109, reviewed GR-1C

Claude review-of-review follow-up, pushed and merged:
  branch: user/claude/gr-1c-review-followups-20260802
  implementation: 7058cb2
  handoff: b06a281
  merge: 2882889

Codex independent follow-up review branch:
  branch: codex/review-claude-gr1c-followups-20260802
  correction: c1de927  Complete independent GR-1C follow-up review
  status-doc correction: d2d836b  Correct GR-1C follow-up size accounting
  reviewed handoff: 6d3a703  Update session handoff after reviewed GR-1C follow-ups
  general workflow docs: 3c180b4  Add general code review and milestone record instructions
  canonical-handoff rule: 1cdff99  Make session handoff the canonical cross-computer state
  remote state: PUSHED (the earlier LOCAL ONLY statement in 1cdff99's text
  became stale the moment the branch itself was pushed)

Claude third-round confirmation branch, based on Codex tip 1cdff99:
  branch: user/claude/gr-1c-followup-confirmation-20260802
  contents: the previously in-flight three-file edit set 1cdff99 flagged as
  "preserve, do not overwrite" (now committed and validated), plus the
  CLAUDE.md / skill / milestone-record wiring for the owner-mandated general
  instructions, plus this handoff update
  commits: 7f431b6, e9f2e83, f2b5fa9
  remote state: PUSHED AND MERGED as ef77bbf (PR #111)

Codex independent confirmation-review branch:
  branch: codex/review-claude-gr1c-confirmation-20260803
  base: ef77bbf
  review report/correction: 85c72da
  disposition: accepted after one P3 handoff-state correction; no P0-P2 issue
  remote state: PUSHED AND MERGED as ff8c16e (PR #112)

Consolidated plans, both PUSHED AND MERGED (PR #113 Codex, PR #114 Claude;
main at ded68b0):
  Claude draft ca4bae4, Codex draft 9fcf254

Plan adoption (owner decision, 2026-08-02, after discussing both drafts
with Codex): Claude's plan is the adopted go-to plan. It was renamed to
docs/ACTION_PLAN_2026-08-02.md, re-sequenced so UI feature controls are
Phase 1 (owner starts daily paper trading 2026-08-03), and bound as a
standing instruction in CLAUDE.md section 2 and the new AGENTS.md. All
individual implementation/design plans, plus Codex's draft, are archived
under docs/reference/ (git mv, history preserved) with a README stating
they remain authoritative for milestone definitions but not sequencing.
```

### Local-only strategy-tool document

The previously missing strategy-tool work is present in this checkout:

```text
branch: codex/ai-strategy-tool-doc-v2-20260802
commit: a656015  Document AI-driven strategy backtest tool
file: docs/AI_DRIVEN_STRATEGY_FORMING_TOOL_IMPLEMENTATION.md
current state: LOCAL ONLY, NOT PUSHED OR MERGED
```

`git cat-file` and `git show` both resolve `a656015` here, and `git branch -vv`
lists the local branch. The file is deliberately absent from the active review
tree and `origin/main`; switch to or inspect that branch to read it. The
similarly named `929ba09` is a different GR-1B follow-up and must not be
mistaken for it.

### Required action before abandoning this computer

The full UI review chain is merged into `origin/main` at `661a7d4`. Reviewed
Phase 2 branch `codex/review-phase2-hygiene-20260803` is PUSHED with
implementation `34ce463`, implementation handoff `c8271a1`, review correction
`36c69d3`, and the handoff commits; another computer can fetch it. What is NOT
on the remote: local strategy-tool branch
`codex/ai-strategy-tool-doc-v2-20260802` (`a656015`). Another computer cannot
fetch that branch. The pre-change operator-database backup
`data/backups/trading_assistant-pre-phase2-schema-20260803T171810Z.db` is
Git-ignored and machine-local.

## 3. Relevant GR-1 commit history

Recent sequence:

```text
dce5e23  Claude: GR-1D reconciliation extraction (LOCAL ONLY, awaiting review)
40af55c  Merge PR #119: Phase 2 third-round confirmation into main
6b1b174  Claude: update session handoff after confirmed Phase 2 (MERGED)
5cffb1f  Claude: confirm the Phase 2 hygiene review (MERGED via PR #119)
8278510  Merge PR #118: the reviewed Phase 2 hygiene chain into main
35fc2dd  Codex: record pushed Phase 2 review branch (PUSHED, MERGED)
e3a5b9a  Codex: update handoff after reviewed Phase 2 hygiene (PUSHED, MERGED)
36c69d3  Codex: complete independent Phase 2 hygiene review (PUSHED, MERGED)
c8271a1  Claude: Phase 2 implementation handoff (PUSHED via review branch)
34ce463  Claude: Phase 2 hygiene implementation (PUSHED via review branch)
661a7d4  Merge PR #117: the complete UI review chain into main
8093fa2  Claude: confirm the UI-controls review; harden the
         environment-sensitive identity test
1bdbd4e  Codex: update handoff after reviewed UI controls
a6d5254  Codex: independent UI review corrections/report (pushed via the
         Claude confirmation branch)
4c8e959  Merge PR #116: Claude UI feature controls into main
47effd7  Claude: UI implementation handoff, awaiting review
edc87e9  Claude: UI feature controls implementation
6f658fb  Merge PR #115: adopt the go-to action plan
9fcf254  Codex: add consolidated implementation action plan (merged via PR #113)
ca4bae4  Claude: add consolidated implementation action plan (merged via PR #114)
ff8c16e  Merge PR #112: Codex independent GR-1C confirmation review into main
77c266a  Codex: update handoff after GR-1C confirmation review
85c72da  Codex: complete independent GR-1C confirmation review
ef77bbf  Merge PR #111: Claude GR-1C third-round confirmation into main
f2b5fa9  Claude: update session handoff after confirmed GR-1C follow-up review
e9f2e83  Claude: wire owner-mandated review workflow into instructions/record
7f431b6  Claude: confirm follow-up review and pin residual class-resolved seam
1cdff99  Codex: make session handoff the canonical cross-computer state (pushed)
3c180b4  Codex: add general code review and milestone record instructions (pushed)
6d3a703  Codex: update session handoff after reviewed GR-1C follow-ups (pushed)
d2d836b  Codex: correct GR-1C follow-up size accounting (pushed)
c1de927  Codex: complete independent GR-1C follow-up review (pushed)
2882889  Merge PR #110: Claude GR-1C review follow-ups into main
b06a281  Claude: update session handoff after GR-1C review follow-ups
7058cb2  Claude: pin the injection boundary the original review left implicit
091efc2  Merge PR #109: reviewed GR-1C into main
5750af3  Codex: document mandatory review and handoff process
c280142  Codex: replace session handoff after reviewed GR-1C
465df8d  Codex: complete independent GR-1C review
b4d9b1f  Claude: GR-1C validation extraction and dependency injection
5dda78e  Merge PR #107: GR-1B follow-up review into main
9eaa06f  Codex: clarify GR-1B telemetry guard contract
```

Historical branch names are not instructions to resume obsolete work. The
active review branch and current status documents supersede the earlier GR-1A
and GR-1B handoff text.

## 4. GR-1C implementation and independent review

### Claude's implementation

Claude moved the 315-line body of
`validate_proposal_for_execution()` into:

```text
assistant/execution_kernel/validate.py::run_proposal_validation
```

The existing public function remains on `assistant.execution_service` as a
small wrapper. It constructs a frozen `ProposalValidationDeps` object inside
the wrapper on every call, using the facade's current module namespace. This
preserves the established behavior where tests or tooling can replace
`execution_service.validate_trade_intent` and have validation use the
replacement.

Claude also:

- moved `ProposalValidationOutcome` into the kernel and re-exported the exact
  same class object from the facade;
- deferred the broker import through an injected provider so early
  existence/expiry/policy failures retain their historical precedence;
- kept validation read-only with respect to proposal, reservation, telemetry,
  and broker-order state;
- added characterization, identity, export, and mutation-sensitive tests;
- reduced `assistant/execution_service.py` substantially; and
- updated `GENERAL_READINESS_STATUS.md` and `ARCHITECTURE_DEBT.md`.

Claude reported `2405 passed, 1 skipped, 25 warnings` on `b4d9b1f`.

### Independent review finding and correction

The architecture was sound, but the original dependency bundle did not fully
meet its own compatibility claim. Four runtime collaborators that the moved
body previously resolved from the facade still resolved inside the kernel:

```text
datetime     expiration and quote-receipt timestamps
Decimal      zero value for cumulative pending exposure
TradeIntent  normalization of open broker orders
to_decimal   conversion of cumulative batch exposure
```

Claude also removed the previously importable facade names `dataclasses` and
`Decimal` while documenting the facade import surface as a compatibility
contract.

The review added tests before correcting the code. On the exact uncorrected
Claude snapshot:

```text
3 focused tests failed:
  - patched facade TradeIntent/to_decimal did not reach the kernel;
  - patched facade datetime did not control validation time;
  - facade dataclasses/Decimal exports were missing.
```

Commit `465df8d`:

- adds all four collaborators to `ProposalValidationDeps`;
- routes both the expiration clock and quote-receipt clock through the injected
  facade `datetime`;
- routes open-order construction, decimal-zero construction, and conversion
  through the facade-built dependency object;
- restores exact `dataclasses` and `Decimal` facade exports;
- adds red/green characterization coverage;
- changes the validation description from **pure** to **read-only** because it
  reads durable state and performs broker preflight/quote queries; and
- records the independent-review corrections in the readiness documents.

Final exact sizes after review:

```text
assistant/execution_service.py:          1,090 lines
assistant/execution_kernel/validate.py:    462 lines
execute_approved_paper_proposal():         281 lines
reconcile_submission():                    221 lines
```

Assessment: Claude's GR-1C core design and extraction were strong, but the
claim that every runtime facade collaborator was injected was incomplete.
After correction, GR-1C is accepted. A fair quality assessment is about
8.5/10: strong architecture and testing, with a material but contained
compatibility miss caught during independent review.

### Review-of-review follow-ups (Claude, 2026-08-02, after the merge)

Branch `user/claude/gr-1c-review-followups-20260802`, commit `7058cb2`,
based on merged `main` (`091efc2`), pushed. Claude verified every review
change before acceptance: the four injections are complete for their
category, both new seam tests fail under reverse-mutation (each clock read
independently), and the facade-surface rule is internally consistent (`os`
was already dead at `d9e3196`, so the GR-1B removal survives the sharper
rule). Two precision gaps were closed:

- the "injected every runtime collaborator" claim was itself over-broad —
  `ProposalValidationOutcome`, `timezone`, and the `FAILURE_*` constants
  remain kernel-resolved, deliberately; the boundary is now documented in
  the `ProposalValidationDeps` docstring and enforced by a new exact
  two-sided AST allowlist guard over the body's module-global reads
  (mutation-verified in both regression directions); and
- the pure -> read-only sweep missed the `ProposalValidationOutcome` class
  docstring and a `test_personal_assistant.py` section comment (both
  comment-only).

Validation on that tree: `2408 passed, 1 skipped, 25 warnings`
(+1 = the AST guard), compileall clean, `git diff --check` clean.

### Independent review of Claude's follow-up (Codex, 2026-08-02)

Claude correctly identified that the earlier phrase "every runtime
collaborator" overclaimed what the seven-plus-four-field dependency bundle
enforced. Its terminology cleanup and reverse-mutation work were useful, but
the proposed allowlist was not compatible with GR-1's unchanged-facade
contract. Before extraction, the moved body resolved all of these names from
`assistant.execution_service`; after the follow-up, replacing them there no
longer changed validation:

```text
ProposalValidationOutcome  construction of every returned outcome
timezone                   UTC supplied to both validation clock reads
FAILURE_DATA_INTEGRITY     durable failure classification
FAILURE_INFRASTRUCTURE     durable failure classification
```

Three focused characterization tests failed red on the exact merged Claude
tree `2882889`: facade outcome replacement was ignored, facade timezone
replacement was ignored, and facade failure constants were ignored. This is a
P2 public-compatibility regression, not merely an imprecise description.

Correction `c1de927`:

- injects the facade's outcome factory, timezone object, and both
  behavior-bearing failure constants through `ProposalValidationDeps`;
- resolves `timezone.utc` inside the kernel at its historical point in the
  check order rather than evaluating it early in the wrapper;
- routes every outcome construction and validation failure classification
  through the injected bundle;
- replaces the non-empty allowlist with a zero-module-global invariant for
  `run_proposal_validation()`; and
- uses Python's symbol table for the structural guard, covering nested scopes
  and module globals that shadow builtins without the hand-rolled AST
  collector's false-negative cases.

The new guard was mutation-verified: restoring one direct kernel outcome
construction failed by naming `ProposalValidationOutcome`, then passed after
the correction was restored. Claude's follow-up is accepted after correction.
Quality assessment for the follow-up itself: **7.5/10** — strong diagnosis and
test intent, but a material compatibility exception was documented instead of
preserved and the claimed exact guard was not scope-exact.

Current exact sizes after `c1de927` (AST-inclusive function spans):

```text
assistant/execution_service.py:          1,094 lines
assistant/execution_kernel/validate.py:    479 lines
run_proposal_validation():                 294 lines
execute_approved_paper_proposal():         281 lines
reconcile_submission():                    221 lines
```

### Third-round confirmation (Claude, 2026-08-02)

Every Codex correction was independently re-verified before acceptance, per
`docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` (commit-by-commit dispositions and
the P0–P3 ledger live in the review report):

- all three new characterization tests fail red on the exact pre-correction
  tree `2882889` (an initial "3 passed" observation was a measurement
  artifact — the probe imported the corrected code from the main worktree via
  the working directory; rerun correctly inside the pre-correction worktree,
  all three fail red) and the symtable guard fails there naming exactly
  `ProposalValidationOutcome`, `timezone`, `FAILURE_DATA_INTEGRITY`,
  `FAILURE_INFRASTRUCTURE`;
- reverse-mutating each injected seam back to kernel-local resolution is
  caught by BOTH the guard and the matching behavioral test (six of six
  detections);
- the size corrections are exact; the follow-up's earlier 276/1,090 figures
  were stale carry-forwards;
- the P2 classification of the allowlist is accepted as fair.

One residual of the same regression class was found and documented rather
than fixed: `ProposalValidationOutcome.resolved_failure_class` resolves its
`FAILURE_NONE`/`FAILURE_DETERMINISTIC_POLICY` fallbacks from the kernel at
property-access time; pre-GR-1C a facade patch of either constant reached it
(verified on `5dda78e`), and it no longer does. Both available fixes are
worse than the gap (injecting changes the frozen dataclass's public field
set; facade resolution inverts the kernel->facade dependency direction), so
the boundary is documented in the property docstring and pinned by
`test_gr1c_resolved_failure_class_fallbacks_are_class_resolved`, which also
proves itself non-vacuous by patching the kernel side. Codex should treat
that boundary as open for challenge in its next review round.

### Independent review of the third-round confirmation (Codex, 2026-08-02)

Codex reviewed every commit from `1cdff99..ef77bbf` separately. Commit
`7f431b6` is accepted: the class-resolved fallback compatibility difference
is real, explicitly documented, non-vacuously tested, and restoring
property-time facade lookup would require a kernel-to-facade dependency,
mutable class-wide resolver state, or a public construction-contract change.
Commit `e9f2e83` is accepted with no issue; it correctly wires the owner's
review and record requirements and adds the required two-paragraph GR-1C
milestone entry. Commit `f2b5fa9` is accepted with no issue at its pre-merge
snapshot. Merge `ef77bbf` is accepted after correction: it merged cleanly but
made the canonical handoff's pending-merge decision and topic-branch resume
instructions stale.

The durable report is
`docs/REVIEW_2026-08-02_GR1C_CONFIRMATION.md` at `85c72da`. Its retained issue
ledger contains one resolved P3 (`REV-001`, stale post-merge handoff state)
and no P0, P1, or P2 findings. The review rates Claude's latest round 9/10.

## 5. GR-1 status and the exact next development step

GR-1 is **partial**. GR-1A, GR-1B, and GR-1C are implemented and independently
reviewed, but `assistant.execution_service` is not yet the plan's thin
composition layer.

Completed and reviewed:

- characterization across all five public execution entry points;
- atomic conditional claim ownership remains in `AssistantStore`;
- outcome interpretation, intent parsing, revalidation inputs, claim fencing,
  submission sizing/dispatch, reservation handling, and shared exception
  definitions are in `assistant/execution_kernel/`;
- execution phases are named and their order remains explicit;
- telemetry failure cannot fall through into order submission;
- ambiguous broker outcomes keep budget reserved;
- replacement-chain identity and mismatch behavior remain fail-closed;
- exact exception identities and facade imports are pinned;
- validation orchestration now lives behind call-time dependency injection
  covering every facade-derived runtime name the moved body resolves; the
  kernel function has zero module-global runtime reads, pinned by a
  mutation-verified symbol-table guard; and
- execution-kernel import boundaries prevent direct or transitive reach into
  proposal-generation code.

Still on the facade:

- the 281-line execution composition;
- the 221-line manual `reconcile_submission()` workflow;
- stale reconciliation/claim recovery wrappers; and
- several compatibility exports and top-level composition responsibilities.

Phase 1 (UI feature controls) is fully merged: implementation PR #116
(`4c8e959`), review chain PR #117 (`661a7d4`), accepted after two P2
corrections (`a6d5254`) and Claude's third-round confirmation. The complete
record is in `docs/REVIEW_2026-08-03_UI_FEATURE_CONTROLS.md` and
`docs/FEATURE_MILESTONE_RECORD.md`.

Active milestone status (2026-08-03): **GR-1D is IMPLEMENTED and awaiting
independent review** (owner go-ahead granted 2026-08-03).

```text
branch: user/claude/gr-1d-reconciliation-extraction-20260803
        (LOCAL ONLY, base 40af55c = merged main after PR #119)
implementation commit: dce5e23
scope: the 221-line reconcile_submission() body moved token-verbatim
       (813 tokens identical after seam-rename + one trailing-comma
       normalization) into
       assistant/execution_kernel/reconcile.py::run_submission_reconciliation
       behind a frozen 13-field ReconciliationDeps the facade builds at
       call time from its own namespace. Seams were enumerated
       MECHANICALLY (symtable) BEFORE the move: the exception class
       (raised AND caught through the injected object), SUBMITTING /
       SUBMISSION_UNKNOWN / RECONCILING, datetime + timezone, the deferred
       broker import (shared _import_execution_broker provider, executed
       first inside the try after the atomic claim), and the six helpers
       (intent parsing, lookup, matching, replacement chains, absence age,
       journaling). Atomic claim and all conditional transitions remain
       AssistantStore operations. Facade 1,094 -> 952 lines.
tests: 10 new (8 seam-freeze tests written FIRST and green on the
       pre-move code, kernel-object identity, symtable zero-global guard);
       zero existing tests edited. Mechanical pre/post facade-surface
       comparison: nothing removed, exactly ReconciliationDeps and
       run_submission_reconciliation added.
mutation sweep (applied in the NEW location, restored finally): 8/8
       DETECTED — fresh-404 grace deleted (3 tests), unconfirmed lookup
       collapsed into confirmed absence (3, incl. the never-treat-failed-
       lookup-as-absence freeze), mismatch guard deleted (8), replacement
       chain bypassed (12), unexpected-error recovery no-oped (4),
       kill-switch-on-direct-mismatch deleted (1 — only the NEW seam test;
       precision note recorded in the GR status doc), grace-clock
       preserve_updated_at dropped (the anti-starvation test), facade
       wrapper resolving a dep from the kernel (5 seam tests).
validation: full suite 2451 passed / 1 skipped / 25 warnings in 448.48s
       (Python 3.13.14); focused 122 passed; compileall clean;
       git diff --check clean.
honest limits: the recovery wrappers (recover_stale_reconciliation,
       recover_stale_claim) and the 281-line execution composition remain
       on the facade — that residue is GR-1E's assessment question; no
       broker, policy, scheduler, or epoch state was touched.
next: independent Codex review of dce5e23; then GR-1E assessment. Do not
       begin GR-2.
```

Phase 2 hygiene (COMPLETE — reviewed, merged as PR #118 `8278510`,
confirmation merged as PR #119 `40af55c`):

```text
implementation branch: user/claude/phase2-hygiene-20260803
implementation commit: 34ce463
implementation handoff: c8271a1
review branch: codex/review-phase2-hygiene-20260803 (PUSHED)
review correction/report: 36c69d3
merge: 8278510 (PR #118; merge tree verified byte-identical to 35fc2dd)
third-round confirmation: 5cffb1f on user/claude/phase2-confirmation-20260803
  (LOCAL ONLY until pushed): PH2REV-001 red-proof reproduced in a worktree
  at exact 34ce463 (matches=True on weakened same-named objects);
  correction reverse-mutated and detected; PH2REV-002 reproduced via
  git cat-file and branch inventory; PH2REV-003 corrected text verified;
  merge tree equality verified; full suite on the merged tree 2441 passed /
  1 skipped / 25 warnings in 341.77s (Python 3.13.14); review rated 9/10;
  one residual boundary documented (--apply creates missing objects but
  deliberately cannot repair a same-named mismatched index/trigger — it
  surfaces in mismatched_* instead)
disposition: accepted after correction; confirmation found no new issue
scope:
  AP-1 - assistant/storage.py gains verify_database_schema() (read-only,
       fail-closed, expected schema built by the real AssistantStore
       initialization path so it cannot drift) and a SchemaVerificationResult
       contract; scripts/run_personal_assistant.py gains verify-db-schema,
       which deliberately runs WITHOUT main()'s store construction (that
       construction IS the migration) so the read-only default is truly
       read-only; --apply opts into open-with-current-code then verify.
  AP-2 - .gitignore now ignores artifacts/ wholesale (nothing under it was
       ever tracked; runbook-documented runtime writes land there and
       evidence capture refuses ANY untracked file).
  AP-4 - doc reconciliation: phantom "~1,450" plan attribution fixed in
       GENERAL_READINESS_STATUS; 479-vs-490 validate.py figure annotated;
       GR-1A characterization docstring made historical ("was 2,040
       lines"); stale "validation purity" wording corrected; GR-1D/GR-1E
       sections added to the GR status doc; ML status doc contradictions
       fixed (spec library delivered, calibration reports wired, ML-FS §2
       no longer sweeps ML-FS-6 into "software-complete"); action plan
       updated to the post-PR-#117 merged state and reviewed Phase 2 state.
review findings:
  PH2REV-001 P2 - same-named weakened indexes/triggers passed the original
       verifier. Corrected by comparing normalized definitions and reporting
       mismatched_indexes/mismatched_triggers; proven red then green.
  PH2REV-002 P3 - the implementation handoff incorrectly said a656015 was
       absent from this clone. The commit and local branch are present.
  PH2REV-003 P3 - "EXACT MATCH" and the claimed cause of operator-DB drift
       exceeded the evidence. Corrected to compatibility match and unknown
       historical provenance.
tests: implementation added 13 tests (12 schema + 1 artifact-ignore);
       independent review added the thirteenth schema test, for 14 total new
       Phase 2 tests. Mutation/red evidence includes the original three
       implementation probes plus the review's same-name definition probe.
operational AP-1 run (this machine): operator DB backed up FIRST via the
       SQLite backup API from a read-only connection
       (data/backups/trading_assistant-pre-phase2-schema-20260803T171810Z.db,
       integrity ok, SHA-256 cc70b8d39fdd854075c81f17666d5ac8c1147344d4
       6f8837ee2cb3fa41ccb6b5); corrected read-only verification reports a
       compatibility match: all required tables/columns present and all
       named index/trigger definitions matched. --apply was not needed; no
       schema change was made to the operator DB during implementation or
       review. How this DB became current is not established.
validation: corrected focused suite 81 passed in 21.74s; corrected full suite
       2441 passed / 1 skipped / 25 warnings in 316.46s under Python 3.13.14;
       compileall and git diff --check clean. The first full review attempt
       was externally terminated at 120s and is not counted.
honest limits: verify-db-schema compares table/column presence and exact
       normalized named-index/trigger definitions, not table column types or
       constraints byte-for-byte;
       the operator-DB drift noted in section 8 is recorded, not explained;
       no execution-kernel file changed; no policy, broker, scheduler, or
       epoch state was touched.
next: Phase 2 is merged and closed.
```

The GR-1D pre-implementation checklist (characterize first, symtable-
enumerate every facade-resolved global, mechanical facade-surface
comparison, storage-level transitions untouched, the seven-branch mutation
list, focused/full validation, stop for review) was executed in full; the
evidence lives in the GR-1D sections of `docs/GENERAL_READINESS_STATUS.md`
and in `tests/test_execution_characterization.py`'s gr1d test family.

After the GR-1D review, reassess whether one final GR-1E is needed to thin
the 281-line execution composition and recovery wrappers. Do not begin GR-2
merely because GR-1D is implemented.

## 6. Non-negotiable safety boundaries

These rules apply to Codex, Claude, scripts, tests, UI work, and future plans:

- `config.PAPER_TRADING` remains `True`.
- Never operate a funded brokerage account without a new, explicit, narrowly
  scoped owner authorization.
- Every order remains subject to deterministic policy, fresh validation,
  durable idempotency, exact human approval, reservation accounting, and
  broker reconciliation.
- The atomic proposal claim remains a conditional storage operation. Never
  replace it with a service-layer read followed by a write.
- A timeout, network failure, or failed lookup is not proof of broker absence.
- Reserved budget is released only on paths where absence/failure is proven by
  the existing contract; ambiguous outcomes keep the hold.
- A mismatched order under this platform's idempotency key is a platform-halt
  anomaly, not an order to adopt automatically.
- Telemetry must be recorded before broker submission. Telemetry failure must
  not fall through into submission.
- ML and LLM output remains observation, research, explanation, or draft data
  only.
- No ML or LLM output may create, approve, size, submit, cancel, replace, or
  weaken a deterministic trading control.
- Missing, stale, invalid, corrupt, or unavailable AI output is equivalent to
  no AI output.
- AI failure must not stop reconciliation or a legitimate risk-reducing sale.
- Backtests, fixture success, software completion, and shadow predictions do
  not establish market edge or grant promotion authority.
- No UI toggle may enable live trading or autonomous execution.

Read `CLAUDE.md` completely. Its Git, testing, data, safety, and handoff rules
apply equally to both agents.

## 7. Final reviewed validation baseline

Environment used by Codex:

```text
Python 3.12.13 in .venv
```

This matches the project-preferred reconstruction command. The earlier GR-1C
review also passed under Python 3.13.14; preserve both observations rather than
silently assuming all future supported-version runs are equivalent.

Focused GR-1C/execution suite:

```text
402 passed in 58.80 seconds
```

This focused set covered validation, submission characterization,
reconciliation, replacement chains, reservations, telemetry, transaction
readiness, broker isolation, the execution gate, and import boundaries.

Full suite:

```text
2411 passed, 1 skipped, 26 warnings in 166.45 seconds
```

Third-round confirmation run (Claude, Python 3.12.13, on the final tree with
the confirmation commits' code/test changes applied):

```text
2412 passed, 1 skipped, 25 warnings in 376.99 seconds
(+1 = test_gr1c_resolved_failure_class_fallbacks_are_class_resolved)
focused: tests/test_execution_characterization.py +
         tests/test_ml_import_boundary.py = 50 passed
```

Independent confirmation review (Codex, Python 3.12.13, exact merge tree
`ef77bbf` before documentation-only review commits):

```text
focused: 50 passed in 26.28 seconds
full: 2412 passed, 1 skipped, 26 warnings in 333.69 seconds
```

Consolidated Codex action-plan audit (Python 3.12.13, documentation-only
commit `9fcf254` plus the pending handoff update):

```text
full: 2412 passed, 1 skipped, 26 warnings in 238.98 seconds
compileall: clean
git diff --check: clean
```

Independent UI feature-controls review (Python 3.12.13, merge `4c8e959`
plus correction `a6d5254`):

```text
red proof:
  provider-control test failed because disabled-source flags did not exist
  Streamlit policy file advanced to 1.1.1 while status stayed at 1.1.0
corrected focused: 236 passed in 78.60 seconds
corrected full: 2427 passed, 1 skipped, 26 warnings in 203.31 seconds
compileall: clean
git diff --check: clean after removing review-report trailing whitespace
end-to-end temporary-policy toggle: off -> on -> off; persisted policy,
  version, fingerprint, checkbox, and read-only status agreed both times
```

The normal full command's `--cache-clear` failed before collection because
Windows denied access to the pre-existing repository `.pytest_cache\v`
directory. The recorded full run used `-p no:cacheprovider`; this disabled
only pytest's result cache, not test collection, fixtures, or behavior.

Phase 2 hygiene implementation (Claude, Python 3.13.14 in this machine's
`.venv`, tree `34ce463`):

```text
focused: 80 passed (schema verification, artifact ignores, CLI parser,
         execution characterization, ML import boundary)
full: 2440 passed, 1 skipped, 25 warnings in 434.76s
compileall: clean
git diff --check: clean
mutation/red evidence: needs_store dispatch broken -> detected; missing-
  column comparison neutralized -> detected; .gitignore rule reverted ->
  detected; all restored green
```

Independent Phase 2 review (Codex, Python 3.13.14, corrected tree
`36c69d3`):

```text
red proof: replacing idx_one_active_paper_epoch with a same-named non-unique
  index and fk_broker_orders_proposal_insert with a same-named no-op trigger
  still produced matches=True on 34ce463
corrected focused: 81 passed in 21.74 seconds
corrected full: 2441 passed, 1 skipped, 25 warnings in 316.46 seconds
operator DB read-only compatibility check: match; no missing or mismatched
  required objects
compileall: clean
git diff --check: clean
```

The first Codex full-suite attempt was terminated by its command runner's
120-second limit and then encountered a closed stdout pipe; it is not a test
failure and is not counted. The clean retry above is the authoritative result.

Additional gates:

```text
compileall: clean
git diff --check: clean
review branch: clean before editing this handoff
mutation: direct kernel outcome construction detected, then restored green
third-round mutation sweep: all three seam reverse-mutations caught by both
  the symtable guard and the matching behavioral test (six of six)
Codex confirmation review: compileall clean; git diff --check clean;
  no residual `if False:` mutation markers
```

The warnings were non-failing third-party/environment notices. Do not convert
the count into a readiness claim; the behavioral invariants and red/green
regressions above are the meaningful evidence.

Required validation command pattern:

```powershell
New-Item -ItemType Directory -Force .venv\codex_test_tmp | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --disable-warnings --cache-clear --basetemp=.venv\codex_test_tmp\full
.\.venv\Scripts\python.exe -m compileall -q assistant backtest data execution ml risk scripts signals strategies tests baskets.py config.py market_analytics.py
git diff --check
git status --short --branch
```

`tests/conftest.py` isolates pytest from the operator database and inherited
broker credentials. Preserve that protection.

## 8. Current machine-local operational snapshot

Captured on this computer during handoff preparation. Recheck after stopping
all writers and again after restoring on the new computer.

### Operator database

Re-measured read-only on 2026-08-03 during the Phase 2 AP-1 run:

```text
path: C:\git\customizedagent\trading_agent\data\trading_assistant.db
size: 3,670,016 bytes
WAL: present, 0 bytes
PRAGMA quick_check: ok
schema: compatibility match against current code (verify-db-schema,
        read-only); all required tables/columns present and all named
        index/trigger definitions match, including execution_telemetry_events
        (11 declared columns) and portfolio_capture_sessions (14 declared
        columns). Table column types and constraints are not compared
        byte-for-byte.
pre-change backup: data/backups/
        trading_assistant-pre-phase2-schema-20260803T171810Z.db
        (SQLite backup API from a read-only connection; integrity_check ok;
        SHA-256 cc70b8d39fdd854075c81f17666d5ac8c1147344d46f8837ee2cb3fa41ccb6b5)
```

Selected row counts (2026-08-03):

```text
decision_packets:                209
trade_proposals:                   7
portfolio_equity_snapshots:       78
broker_orders:                     0
journal_transactions:              0
```

DRIFT WARNING: the previous revision of this section (prepared
2026-08-03T00:17) recorded size 2,920,448, 24 tables with both AP-1 tables
ABSENT, and larger row counts (decision_packets 277, trade_proposals 31,
portfolio_equity_snapshots 118). Current code may have opened and migrated
this database, but the measurements may instead describe different restored
databases or machine profiles; the historical cause is not established. The
documented decision-packet migration can collapse exact duplicate packets,
but the trade-proposal and equity-snapshot decreases are NOT explained by any
migration. Do not silently combine the snapshots; treat provenance as
unresolved (related to the open owner decision on historical contamination).
No paper-evidence epoch has started here, and no broker lifecycle or
reservation evidence exists in this database.

The database is Git-ignored. Stop Streamlit, tests, schedulers, paper
operations, and other writers before making a transfer backup. Prefer the
documented SQLite backup/restore workflow over copying a live file. Recompute
the hash of the actual backup; the value above identifies only this snapshot.

After restore:

1. verify the transfer hash;
2. run SQLite integrity/quick checks;
3. confirm the expected paper account identity without printing credentials;
4. reconcile the ledger against Alpaca paper state;
5. run operational health/readiness checks; and
6. confirm development/tests use a separate database.

### Credentials

Presence only; no values were read or recorded. Re-measured 2026-08-03
during the Phase 2 session:

```text
APCA_API_KEY_ID         process=True   user=True
APCA_API_SECRET_KEY     process=True   user=True
DATABENTO_API_KEY       process=False  user=False
ANTHROPIC_API_KEY      process=False  user=False
FINNHUB_API_KEY        process=False  user=False
```

Drift from the previous revision: DATABENTO_API_KEY was recorded
present/present there and is absent in both scopes here — consistent with
the two revisions describing different machines or profiles. Do not assume
Databento access on this machine without re-provisioning.

Recreate required secrets through a secure mechanism. Start a new terminal or
agent process so it inherits them. Confirm Alpaca points to the intended paper
account. Never paste values into this document, Git, logs, screenshots, or
issue comments.

### Scheduler

```text
Scheduler state could not be verified: Get-ScheduledTask returned Access denied.
```

Do not infer either installed or absent tasks from that failed query, and do
not assume paper or ML evidence collection is running. Recheck in an elevated
operator session. Install tasks only through reviewed scripts with explicit
repository, Python, database, config, artifact, and alert paths, then verify
`LastTaskResult` and owner-visible delivery.

### Databento artifacts

Re-measured 2026-08-03: `artifacts/` does not exist in this worktree at
all, and DATABENTO_API_KEY is absent (see above). The previous revision's
"artifacts/databento/: present (4 files)" describes a different machine or
an earlier state. If licensed Databento files are still wanted, they must
be transferred privately from wherever they live; never commit licensed
contents. (The whole `artifacts/` directory is now Git-ignored — AP-2.)

### Paper mode

```text
config.py: PAPER_TRADING = True
```

Do not change it as part of environment reconstruction or GR-1 work.

## 9. ML and evidence posture

The ML subsystem is substantial but remains non-authoritative and isolated
from execution authority.

High-level state:

| Area | State |
|---|---|
| Experiment/evaluation contracts | Built |
| Point-in-time data contracts | Built; real authoritative coverage absent |
| Immutable experiment orchestration | Built |
| Volatility/portfolio research software | Built; real evidence underfilled |
| Earnings/filing research software | Built; authoritative event data absent |
| Supervised-volatility shadow runtime | Built, observational only |
| Monitoring/dossier software | Built |
| Read-only ML presentation | Built |
| Promotion registry/bounded adapter | Not implemented or authorized |
| Limited-capital canary | Not authorized |
| Execution-quality modeling | Deferred pending representative order data |
| Paper evidence cadence on this machine | Not deployed |

Yfinance remains exploratory and must not be represented as authoritative
point-in-time evidence. Databento market data alone does not provide historical
strategy/index membership. Raw as-printed prices require vintage-correct
corporate-action handling; splits must not be treated as genuine returns.

Do not begin ML promotion, bounded adapters, or a funded canary merely because
software scaffolding exists. Real-data lineage, untouched confirmation,
paper-evidence duration/counts, monitoring, reconciliation, drills, and a
separate owner decision remain mandatory.

## 10. Product and design documents

All individual product/design plans were archived to `docs/reference/` on
2026-08-02 when the go-to plan was adopted (see section 2). The paths below
reflect that location; the documents' content is unchanged and they remain
authoritative for their own milestone definitions.

### UI feature controls — PHASE 1 COMPLETE AND MERGED (PR #116 + PR #117)

`docs/reference/UI_FEATURE_CONTROLS_DESIGN.md` is the governing design. Its
four open decisions were resolved by the owner on 2026-08-02 (recorded in
`docs/ACTION_PLAN_2026-08-02.md` section 9). It covers:

- UI controls for `enable_strategy_proposals` and `allow_new_positions`;
- read-only secret/provider availability instead of exposing API key values;
- optional AI feature preferences; and
- a dedicated, research-only ticker-suggestions surface.

It does not authorize a live toggle, secret editing in Streamlit, autonomous
approval, or direct suggestion-to-proposal conversion. Implementation is
merged at `4c8e959` (PR #116) and the accepted corrected review chain is
merged at `661a7d4` (PR #117). The durable two-paragraph completion record
is in `docs/FEATURE_MILESTONE_RECORD.md`.

### AI strategy authoring

`docs/reference/AI_STRATEGY_AUTHORING_IMPLEMENTATION_PLAN.md` is the comprehensive
long-term roadmap. Many prerequisites already exist—backtest engines, research
reports, manifests, LLM provider/auditing, ML experiments, and hand-coded
strategies—but the actual product chain is not implemented:

```text
owner prose -> restricted StrategySpec -> deterministic compiler/interpreter
-> generic backtest adapter -> persisted run -> Backtest UI page
```

The narrower product draft is available on local-only branch
`codex/ai-strategy-tool-doc-v2-20260802` at `a656015`, described in the Git
section above. It remains absent from the active tree and remote. No
strategy-language, compiler, authoring workflow, generic adapter, job runner,
or Backtest page has been implemented.

### Proposal history cleanup

`docs/reference/PROPOSAL_HISTORY_CLEANUP_IMPLEMENTATION_PLAN.md` remains
planning only. No destructive cleanup should be inferred or performed from
the existence of that plan.

### Consolidated action plan — adopted

Both agents produced independent consolidated audits (Codex `9fcf254`,
Claude `ca4bae4`; merged via PR #113/#114) that converged on the same
milestone facts. After discussing both with Codex, the owner adopted
Claude's plan. It now lives at `docs/ACTION_PLAN_2026-08-02.md`, is the
single sequencing authority (bound in CLAUDE.md section 2 and AGENTS.md),
incorporates Codex's doc-inventory and staleness corrections by reference,
and was re-sequenced with UI feature controls as Phase 1 by owner priority
change. Codex's draft is preserved at
`docs/reference/ACTION_PLAN_codex.md`.

Do not mix product milestones into the execution-kernel split; each remains
its own reviewed branch.

## 11. Files and documents to read in order

For the next coding session:

1. `CLAUDE.md` and `AGENTS.md`
2. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`
3. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
4. `docs/FEATURE_MILESTONE_RECORD.md`
5. `docs/SESSION_HANDOFF.md`
6. `docs/ACTION_PLAN_2026-08-02.md` — the adopted go-to plan
7. `docs/GENERAL_READINESS_STATUS.md`
8. `docs/ARCHITECTURE_DEBT.md`
9. the archived plan in `docs/reference/` covering the scheduled milestone;
   `docs/reference/README.md` maps the plans. Phase 2 hygiene is specified
   directly by AP-1/AP-2/AP-4 in the go-to action plan.
10. `assistant/execution_service.py`
11. every file under `assistant/execution_kernel/`
12. `tests/test_execution_characterization.py`, plus reconciliation,
   replacement-chain, transaction-readiness, telemetry, and import-boundary
   tests
13. `docs/ML_IMPLEMENTATION_STATUS.md`
14. `docs/OPERATIONS_RUNBOOK.md`
15. `docs/LIVE_PROMOTION_CHECKLIST.md`
16. `docs/DATABENTO_DATA_SOURCE.md`
17. the focused AI strategy-tool document on local branch
    `codex/ai-strategy-tool-doc-v2-20260802` if that branch is preserved

The current code and latest specific status section override stale historical
statements in older documents. Update stale text rather than reimplementing
completed work.

## 12. Private transfer checklist

Git does not transfer ignored or host-level state. Before leaving the old
computer, stop writers and privately inventory/transfer as applicable:

- a consistent backup of `data/trading_assistant.db`;
- any licensed Databento raw files and manifests from another machine;
- ML datasets, model artifacts, monitoring reports, dossiers, and shadow
  configurations that are intentionally ignored;
- alert JSONL, heartbeat, backup, restore, and drill evidence;
- local policy/mandate/config files not tracked by Git;
- scheduled-task definitions and service-account requirements;
- the local-only Git branches named in section 2; and
- credentials via a secret manager or manual recreation, never this file.

Use encrypted storage or direct trusted-device transfer. Do not copy `.venv`,
`.pytest_cache`, `__pycache__`, or temporary test directories.

## 13. Environment reconstruction

Preferred clean setup:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

If the project intentionally standardizes on Python 3.13 instead, record that
decision and rerun the full suite rather than relying on this machine's result.

After restoring machine-local state and verifying paper mode:

```powershell
.\.venv\Scripts\python.exe -m streamlit run scripts/personal_assistant_ui.py
```

Do not let UI/development tests share the restored operational database.

## 14. Owner workflow preferences

- Codex and Claude may alternate implementation and independent review.
- When reviewing Claude, verify the exact commit, reproduce findings, correct
  confirmed defects where practical, and give a genuine 1-10 assessment.
- Commit review fixes unless the owner says not to; branch first when on main.
- Preserve unrelated/uncommitted work in the shared worktree.
- Do not push, merge, or open a pull request unless explicitly requested.
- Use one coherent milestone per branch and stop after independent review.
- Do not call a milestone complete because files or commands exist; verify its
  definition of done and failure directions.
- Prefer red/green characterization and mutation evidence over raw test count.
- Explain complex roadmap items in plain language when asked.

## 15. Decisions still requiring the owner

Do not infer answers to these:

1. ~~Merge the UI/Phase 2 review chains and the Phase 2 confirmation~~ —
   **RESOLVED 2026-08-03**: PR #117 (`661a7d4`), PR #118 (`8278510`), and
   PR #119 (`40af55c`) all merged. NEW: whether to push (for review) the
   GR-1D branch `user/claude/gr-1d-reconciliation-extraction-20260803`
   (`dce5e23` + handoff, currently LOCAL ONLY).
2. ~~Push/cross-review the consolidated plans~~ — **RESOLVED 2026-08-02**:
   both plans merged (PR #113/#114); the owner adopted Claude's plan as
   `docs/ACTION_PLAN_2026-08-02.md` with UI feature controls as Phase 1;
   Codex's draft is archived at `docs/reference/ACTION_PLAN_codex.md`.
3. Whether to push/merge or otherwise transfer the now-available local-only
   strategy-tool branch `codex/ai-strategy-tool-doc-v2-20260802` (`a656015`).
4. ~~When to begin GR-1D~~ — **RESOLVED 2026-08-03: go-ahead granted;
   implemented same day (`dce5e23`), awaiting independent review.**
5. Which authoritative historical membership/reference-data source will be
   obtained and funded.
6. When to deploy the operational paper cadence and start the first immutable
   evidence epoch.
7. Which owner-visible delivery channel GR-5 should implement and verify.
8. Whether and how to handle historical operator-database contamination or
   divergent snapshots after backup and provenance analysis.
9. When an elevated Windows deployment/credential-rotation window is
   available.
10. When, if ever, AI strategy authoring, proposal-history cleanup, ranker work,
   promotion adapters, or funded-account work should supersede readiness work.

None of these decisions grants live or funded-account authority by
implication.

## 16. Exact resume sequence on the new computer

```powershell
git fetch --all --prune
git switch main
git pull --ff-only
git status --short --branch
git log -10 --oneline --decorate
```

Verify that `main` is at or after `40af55c` (PR #119, the merged Phase 2
confirmation) and that history contains the GR-1C chain through `ff8c16e`.
The GR-1D branch `user/claude/gr-1d-reconciliation-extraction-20260803`
(`dce5e23` + this handoff commit) is LOCAL ONLY until the owner authorizes a
push — another computer cannot fetch it and must not recreate it from
memory. Local strategy-tool branch
`codex/ai-strategy-tool-doc-v2-20260802` (`a656015`) also remains local-only.
Everything merged syncs through Git alone — no session files need copying.

Recommended resume prompt:

```text
Read CLAUDE.md, AGENTS.md, docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md,
and docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md completely, then
docs/FEATURE_MILESTONE_RECORD.md, docs/SESSION_HANDOFF.md, and the adopted
go-to plan docs/ACTION_PLAN_2026-08-02.md. Verify origin/main and all
branch/commit claims against Git. The GR-1C chain (through merge ff8c16e)
is complete and independently reviewed; do not redo it. Preserve facade
imports and complete call-time DI, including the outcome factory, datetime,
timezone, Decimal, TradeIntent, to_decimal, and behavior-bearing failure
constants; the one documented residual is
ProposalValidationOutcome.resolved_failure_class's kernel-resolved fallbacks.
Verify paper mode, database isolation, credential presence without values,
scheduler state, and ignored artifact transfer. Do not start live trading, an
evidence epoch, scheduled tasks, ML/LLM proposal integration, or destructive
cleanup. UI feature controls (Phase 1) are fully merged: PR #116 plus the
review chain PR #117 at 661a7d4; do not repeat that review. Action-plan
Phase 2 hygiene (AP-1, AP-2, AP-4) is COMPLETE: implemented at 34ce463,
accepted after correction at 36c69d3, merged as PR #118 at 8278510, and
third-round confirmed and merged as PR #119 at 40af55c — do not
reimplement or repeat any of it. Note the AP-1 operational finding: the
operator database passes the corrected read-only compatibility check and has
a pre-change backup under data/backups/, but the historical source of
database drift remains unknown. Local strategy-tool branch
codex/ai-strategy-tool-doc-v2-20260802 at a656015 is present but
unpublished. GR-1D (Phase 3, owner go-ahead 2026-08-03) is IMPLEMENTED at
dce5e23 on LOCAL-ONLY branch
user/claude/gr-1d-reconciliation-extraction-20260803 with a symtable-
enumerated 13-field ReconciliationDeps, a token-verbatim move, 10 new
characterization tests, and an 8/8 mutation sweep — do not reimplement it.
The next action is an independent review of that exact commit per
docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md; after review, the GR-1E
assessment decides whether GR-1's thin-composition definition of done is
met. Do not begin GR-2.
```
