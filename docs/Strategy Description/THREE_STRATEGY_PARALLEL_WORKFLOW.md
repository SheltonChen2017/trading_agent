# Three-strategy parallel development workflow

Status: **OWNER-DIRECTED AND BINDING from the shared 2026-08-25 baseline.**

## 1. Purpose and branch topology

Three independent Codex sessions will develop three strategies without
sharing a working branch:

1. `codex/strategy-analyst-revisions-v2`
2. `codex/strategy-insider-buying`
3. `codex/strategy-short-interest`

All three branches start at the same documentation-only baseline commit. They
are long-lived lane branches. During this parallel phase, neither Codex nor
Claude creates an implementation, review, counter-review, checkpoint, or
handoff branch for a lane. Every commit for one strategy stays on that
strategy's named branch.

This topology is intentionally temporary. Combining validated strategies into
one QuantConnect trading agent is a later integration milestone, not something
any lane may implement by inference.

## 2. Files that are frozen during parallel development

Until the owner explicitly ends the parallel phase, agents on all three lanes
**must not edit**:

- `docs/ACTION_PLAN_2026-08-20.md`
- `docs/SESSION_HANDOFF.md`
- this workflow file;
- `docs/Strategy Description/README.md`;
- `docs/Strategy Description/THREE_STRATEGY_DATA_SOURCE_REGISTER.md`;
- another strategy's PDF, implementation record, code, tests, or artifacts.

The usual repository requirement to update the Action Plan or Session Handoff
is replaced for these three lanes by the owner's more specific instruction:
the lane's implementation record is its sole current status and handoff
ledger. The shared Action Plan and Session Handoff were updated once in the
common baseline and are then frozen to prevent three branches from repeatedly
conflicting. This exception ends when the branches are integrated or the owner
says otherwise.

If a shared file truly must change, stop and ask the owner to coordinate one
common-baseline amendment. Do not make three competing copies.

### One-time common-remediation exception (owner direction, 2026-08-26)

The owner has authorized one bounded synchronization from
`codex/full-review-p1-remediation-20260826` before the ordinary lane loop
resumes. Shared safety fixes from that remediation series may be synchronized
identically to all three named strategy lanes, including the minimum shared
files and regression tests required to preserve those fixes. Analyst-specific
research-layer fixes may be synchronized only to
`codex/strategy-analyst-revisions-v2`; they must not enter the Insider Buying
or Short Interest lanes. Each target lane updates only its own implementation
record with exact synchronized commits, validation, zero-access accounting,
and remaining review gates.

This is a one-time exception to the frozen-file rule, not permission for
ordinary cross-lane development. Synchronization is not acceptance:
acceptance remains withheld until Claude reviews the exact pushed snapshot on
each same lane branch and Codex counter-reviews every Claude commit. The
synchronization grants no credential, provider endpoint, licensed row, or
outcome access; no QuantConnect research or backtest job; no QC processing or
upload permission; no broker or operator-database action; no paper/live
deployment; and no trading authority. It expires after the three directed
synchronizations and lane-record updates. A later common-baseline or shared-
file change again requires a separate owner decision.

### Owner-directed cross-lane bug-fix integration (owner direction, 2026-09-04)

The owner made that separate decision on 2026-09-04 for one bounded purpose:
the shared trading-application, test-infrastructure, and repository-tooling
defects that the four lane reviews had documented but, under the lane scope
rule, deliberately not fixed. The dedicated review session confirmed each
candidate on `main` first, fixed only the confirmed ones on the integration
branch `Feature-bug-fix-integration-2026-09-04` (branched from `main`), and
applied the identical commits to all four lane branches so no lane carries a
divergent copy of a shared file. The complete item ledger, including every item
examined and left unfixed with its reason, is
`docs/Archive/Review/BUG_FIX_INTEGRATION_2026-09-04.md`; each lane record gains
one short pointer section and nothing else. The owner performs the merge.

This exception covers only those recorded items. It grants no lane any
authority to edit shared files afterwards, and it is not acceptance of any
lane milestone: acceptance remains withheld until Claude reviews the exact
pushed snapshot on each same lane branch and Codex counter-reviews every Claude
commit. It grants no provider, outcome, look, QuantConnect (QC), broker,
operator-database, deployment, paper, live, or trading authority, and it
expires when the integration branch is merged. Any later shared-file change
again requires a separate owner decision.

## 3. Same-branch Codex/Claude loop

Each lane uses this serialized loop on its one branch:

1. **Codex implementation.** Codex fetches, verifies the lane branch and clean
   tree, implements one bounded milestone, runs the required validation,
   updates the lane implementation record, commits, and pushes.
2. **Claude independent review.** Claude fetches the exact pushed head,
   verifies ancestry, reviews every new Codex commit and changed file, records
   accepted / accepted-after-correction / rejected dispositions plus a P0-P3
   ledger in the lane record or a lane-specific review record, commits any
   authorized corrections and the review record on the **same lane branch**,
   and pushes once.
3. **Codex counter-review and next milestone.** Codex fetches and fast-forwards
   the exact reviewed head, counter-reviews every Claude commit, independently
   reproduces material claims, corrects confirmed defects, and adds
   dangerous-direction regressions. If the review is accepted or
   accepted-after-correction and no owner decision blocks progress, Codex then
   implements the next bounded lane milestone. Codex validates both stages,
   updates the lane record, commits them separately where appropriate, and
   makes exactly one combined push. A rejection or owner-decision blocker
   stops the loop before the next milestone and before any push.
4. Claude reviews that exact combined push, and the loop repeats from step 3.

**Owner clarification, 2026-08-26:** the standing Codex counter-review step is
required. An instruction removing it was accidental and is superseded by this
three-step loop.

Only one agent may write or push a lane at a time. Before every commit and
push, the acting agent must recheck the branch, exact `HEAD`, upstream head,
working-tree status, and ordered commit range. Never force-push, rewrite,
rebase published history, or push a partial/checkpoint state. If the remote
advanced unexpectedly, stop and reconcile by review; do not overwrite it.

## 4. Required update on every push

Before every push, the acting agent updates the relevant strategy's
implementation record with:

- role and agent (`Codex implementation`, `Claude review`, or `Codex
  counter-review and implementation`);
- exact starting and ending commits;
- milestone and bounded scope;
- files changed;
- tests and mutations run with exact results;
- findings and dispositions;
- data sources and vintages used;
- whether any real outcomes were accessed and the permanent look identifier;
- remaining gates and next authorized step.

No undocumented push is acceptable. A code commit and its record update may be
separate commits, but both must be present before the push.

## 5. Research and safety boundaries

- The PDFs define research hypotheses, not trading authority.
- All availability timing, identifiers, corporate actions, ETF weights, and
  classifications must be point-in-time and fail closed.
- Structural/data-quality work precedes outcome access. Synthetic tests do
  not consume a look; any real signal/outcome join does and must be registered
  before execution.
- The canonical first implementations are unlevered, long-only or
  underweight/avoidance as specified. No lane may add leverage, inverse funds,
  options, short selling, machine learning, or discretionary tuning outside
  its PDF.
- No credentials, licensed rows, broker access, operator database, scheduled
  tasks, evidence epochs, or paper/live orders are accessed or changed unless
  the owner separately authorizes that exact action.
- No licensed raw, normalized, or derived representation is moved into
  QuantConnect without verified vendor processing/storage rights and owner
  permission for that exact representation.
- Research outputs have no execution authority. A later autopilot must still
  pass an explicit integration design, risk policy, independent review,
  paper-trading evidence, promotion, monitoring, kill-switch, and rollback
  milestone.

## 6. Integration rule

The branches should not be merged simply because their unit tests pass. After
all three canonical V1/V2 lanes have independently reached their defined
research gates, the owner should schedule a fourth integration milestone that:

1. selects a reviewed merge order and reconciles shared data abstractions;
2. freezes a late-fusion ensemble and correlation/risk budget without using
   the final holdout to choose weights;
3. validates combined turnover, overlap, concentration, liquidity, costs, and
   failure behavior;
4. runs one final untouched out-of-sample portfolio evaluation; and
5. only then considers a separately approved QuantConnect paper deployment.

Until that milestone exists, each branch owns only one strategy and no branch
may create the combined autopilot.
