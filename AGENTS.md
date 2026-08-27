# Agent instructions (Codex and any other coding agent)

This repository's general instructions live in `CLAUDE.md` at the repo root.
They apply to every coding agent equally — safety boundaries, document
hierarchy, financial correctness rules, testing expectations, validation
requirements, Git discipline, and handoff rules. Read `CLAUDE.md` completely
before acting; nothing below weakens it.

## The go-to plan

`docs/ACTION_PLAN_2026-08-20.md` is the owner-directed, single sequencing
authority for all workstreams (2026-08-20, replacing the 2026-08-02 plan now
archived at `docs/Archive/Plans/ACTION_PLAN_2026-08-02.md`; the older Codex audit
draft is preserved at `docs/Archive/Plans/ACTION_PLAN_codex.md`). Use it to
decide what is done, what is in progress, what is next, and what is blocked
or prohibited.

The actively implemented plan is kept at the root of `docs/`. Plans that are
approved or retained for later work live in `docs/Plan/`; completed,
superseded, and obsolete plans live in `docs/Archive/Plans/`. They remain
authoritative for their own milestone definitions, safety gates, and
definitions of done when scheduled — but their internal "begin with X"
sequencing statements are superseded by the action plan. Never start a
milestone merely because a queued or archived plan names it next.

## Current agent roles

Owner decision, 2026-08-21: under the generic/legacy ACER workflow, **Codex is
the implementer and Claude is the independent reviewer**. Codex uses a
`codex/` implementation branch and stops at a stable committed snapshot.
Claude reviews that exact pushed snapshot on a separate `user/claude/` review
branch under the standing review workflow. This remains the repository default
outside a later, explicitly scoped owner exception; it does not weaken the
requirement for independent review.

### Three-strategy lane exception (later owner decision, 2026-08-26)

The following three lanes use one serialized, long-lived branch each:

- `codex/strategy-analyst-revisions-v2`
- `codex/strategy-insider-buying`
- `codex/strategy-short-interest`

For only these lanes, Codex pushes one bounded implementation milestone;
Claude independently reviews the exact pushed Codex snapshot, commits any
authorized corrections, updates the lane record, and pushes on that **same
lane branch**. Codex then counter-reviews every Claude commit. If the review is
accepted or accepted-after-correction and no owner decision blocks progress,
Codex implements the next bounded milestone, validates both stages, updates
the lane record, and makes one combined push. No implementation, review,
counter-review, checkpoint, or handoff branch is created for these lanes.
This branch-topology exception supersedes the generic separate-review-branch
default only for the three named lanes; it does not make a review non-independent.

#### One-time common-remediation exception (owner direction, 2026-08-26)

The owner has authorized one bounded common-remediation synchronization
from `codex/full-review-p1-remediation-20260826`. Shared safety fixes from that
series may be synchronized identically to all three named lanes.
Analyst-specific research-layer fixes may be synchronized only to
`codex/strategy-analyst-revisions-v2`; they must not enter either other lane.
Each lane must update its own record.
Synchronization is not acceptance: acceptance remains withheld until Claude
reviews the exact pushed lane snapshot and Codex counter-reviews every Claude
commit. This one-time exception grants no provider or outcome access, no
QuantConnect job, no QC processing or upload permission, no broker or
operator-database action, no paper/live deployment, and no trading authority.
It expires after this owner-directed synchronization and does not authorize
later shared-file changes by inference.

Under the generic workflow, every implementation or review commit series must
update the relevant feature/research/operations/review document and
`docs/SESSION_HANDOFF.md` before handoff or push. For the three named strategy
lanes, the lane implementation record replaces the root Session Handoff and
the project-wide documents stay frozen except for an explicit owner-directed
coordination change such as the one-time synchronization above. Do not update
unrelated documents. Update `docs/ACTION_PLAN_2026-08-20.md` only when
sequencing, milestone status, a gate, or the next authorized step changes, and
then add only a concise reference to the authoritative associated document
instead of duplicating its implementation detail or evidence.

## Standing workflow references

- `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` — commit-by-commit review
  dispositions and the P0-P3 issue ledger (owner-mandated, binding).
- `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md` — the review/handoff
  sequence both agents follow.
- `docs/FEATURE_MILESTONE_RECORD.md` — two-paragraph entry (technical +
  plain-language) for every genuinely completed milestone.
- `docs/SESSION_HANDOFF.md` — the canonical project-wide cross-computer state;
  update and commit it before ending any generic-workflow session that changed
  durable state. During the three-strategy parallel phase, each lane's own
  implementation record is its branch-local handoff instead.

## Shared-worktree caution

Claude and Codex often operate in the same checkout. Before staging or
committing, re-verify `HEAD` and `git status`; another agent may have
switched branches or committed since you last looked. Preserve any
uncommitted work you did not author.
