# Agent instructions (Codex and any other coding agent)

This repository's general instructions live in `CLAUDE.md` at the repo root.
They apply to every coding agent equally — safety boundaries, document
hierarchy, financial correctness rules, testing expectations, validation
requirements, Git discipline, and handoff rules. Read `CLAUDE.md` completely
before acting; nothing below weakens it.

## The go-to plan

`docs/ACTION_PLAN_2026-08-02.md` is the owner-adopted, single sequencing
authority for all workstreams (adopted 2026-08-02 after independent Claude
and Codex audits converged; the Codex draft is preserved at
`docs/reference/ACTION_PLAN_codex.md`). Use it to decide what is done, what
is in progress, what is next, and what is blocked or prohibited.

The individual implementation plans are archived in `docs/reference/` (see
its README). They remain authoritative for their own milestone definitions,
safety gates, and definitions of done — but their internal "begin with X"
sequencing statements are superseded by the action plan. Never start a
milestone merely because an archived plan names it next.

When a phase completes or the owner reorders priorities, update
`docs/ACTION_PLAN_2026-08-02.md` and `docs/SESSION_HANDOFF.md` rather than
letting the plan drift stale.

## Standing workflow references

- `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` — commit-by-commit review
  dispositions and the P0-P3 issue ledger (owner-mandated, binding).
- `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md` — the review/handoff
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
