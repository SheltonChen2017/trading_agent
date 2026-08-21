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

Owner decision, 2026-08-21: for the current ACER sequence, **Codex is the
implementer and Claude is the independent reviewer**. Codex uses a `codex/`
implementation branch and stops at a stable committed snapshot. Claude reviews
that exact pushed snapshot on a separate `user/claude/` review branch under the
standing review workflow. This assignment may be changed only by a later owner
instruction; it does not weaken the requirement for independent review.

When a phase completes or the owner reorders priorities, update
`docs/ACTION_PLAN_2026-08-20.md` and `docs/SESSION_HANDOFF.md` rather than
letting the plan drift stale.

## Standing workflow references

- `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` — commit-by-commit review
  dispositions and the P0-P3 issue ledger (owner-mandated, binding).
- `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md` — the review/handoff
  sequence both agents follow.
- `docs/FEATURE_MILESTONE_RECORD.md` — two-paragraph entry (technical +
  plain-language) for every genuinely completed milestone.
- `docs/SESSION_HANDOFF.md` — the canonical cross-computer state; update
  and commit it before ending any session that changed durable state.

## Shared-worktree caution

Claude and Codex often operate in the same checkout. Before staging or
committing, re-verify `HEAD` and `git status`; another agent may have
switched branches or committed since you last looked. Preserve any
uncommitted work you did not author.
