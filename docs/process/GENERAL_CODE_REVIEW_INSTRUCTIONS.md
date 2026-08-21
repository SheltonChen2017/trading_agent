# General Code Review Instructions

Status: required general workflow for reviewing code produced by a developer,
agent, branch, pull request, or milestone.

This document supplements `CLAUDE.md` and
`docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`. Safety and authorization
rules in those documents remain controlling.

## 1. Confirm and review every commit

Establish the exact repository state before reviewing:

```powershell
git fetch --all --prune
git status --short --branch
git log --all -20 --oneline --decorate
git branch --all --verbose
```

**Review begins only from a pushed remote branch and its exact fetched remote
head.** A local branch, local commit, dirty worktree, or uncommitted shared-
checkout state is not a review snapshot. Fetch first, resolve and record the
full object name of `origin/<implementation-branch>`, and create the review
branch from that object. If the remote head changes after review begins, stop,
record the new range, and deliberately restart or extend scope; never drift
silently onto a merely local or moving implementation.

Identify the base commit, review head, and complete ordered commit range. List
the commits explicitly, for example with:

```powershell
git log --reverse --oneline <base>..<review-head>
```

Every commit in the range requires an explicit review disposition. Do not
review only the branch tip or a combined pull-request diff. For each commit:

1. read its message and complete diff;
2. identify its intended behavior and affected contracts;
3. inspect production code, tests, migrations, configuration, and
   documentation together;
4. determine whether it is correct by itself and in the cumulative final tree;
5. record `accepted`, `accepted after correction`, or `rejected`; and
6. record either its issues or `no issue found` so no commit is silently
   skipped.

Review merge commits as well as ordinary commits. For a merge commit, examine
the resulting combined tree and any conflict-resolution changes. Documentation,
test-only, and follow-up commits are still commits and must be reviewed.

Preserve a clean mapping from every commit hash to its review disposition. If
the range changes while review is underway, stop, identify the new commits,
and add them to the review scope before continuing.

## 2. Maintain a prioritized issue ledger while reviewing

Keep a live issue ledger in the review report from the first finding until the
review closes. Use stable issue identifiers and order open issues by severity.

| Priority | Meaning |
|---|---|
| P0 | Catastrophic: active or imminent loss of funds or data, live-authority escape, secret exposure with immediate impact, or unrecoverable corruption. |
| P1 | Critical: credible unsafe execution, duplicate orders, broken atomicity, incorrect broker outcome, major security failure, or another defect likely to cause severe harm. |
| P2 | Material: public compatibility regression, incorrect durable state, meaningful fail-open/fail-closed behavior, missing recovery, or failure to meet a milestone's definition of done. |
| P3 | Minor: maintainability, inaccurate documentation, weak test sensitivity, or a low-risk edge case without current safety impact. |

Use this minimum ledger shape:

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| REV-001 | P2 | Open | `<hash>` | `<file:line>` | `<what is wrong and why it matters>` | `<reproduction or source evidence>` | `<why this must be fixed instead of accepted>` | `<pending or implemented change>` | `<red/green test or other proof>` |

For every issue, state the reason for the fix in concrete terms. The reason
must describe the violated contract, unsafe failure direction, user-visible
regression, incorrect state transition, or maintainability cost. “Cleanup,”
“best practice,” and “looks better” are insufficient on their own.

Verify material findings before correcting them. Where practical, add a test,
run it red on the uncorrected commit, apply the smallest correct fix, and run
it green. Keep the ledger current as evidence changes. A closed item must name
the correction and its verification; a false alarm must explain why it was
closed without a code change.

The final report must retain both open and resolved issues. Do not delete a
finding merely because it was fixed during review.

## 3. Maintain the completed feature and milestone record

Maintain `docs/FEATURE_MILESTONE_RECORD.md` as the durable, audience-friendly
record of completed work. Add an entry only when a feature or milestone has
actually met its definition of done and completed its required review. Do not
record plans, partial scaffolding, or unreviewed implementation as complete.

Each entry must have a heading naming the feature or milestone and its final
commit or merge commit. Beneath that heading, the functional record must
contain exactly two prose paragraphs:

1. **Technical paragraph:** use software-development language to explain the
   implemented behavior, architecture, interfaces, data or schema changes,
   important safety properties, compatibility effects, and validation.
2. **Plain-language paragraph:** explain the same functionality for a high
   school student. Avoid unexplained jargon and describe what the feature does,
   why it matters, and any important limitation in ordinary language.

The two paragraphs must describe the same completed scope. Neither paragraph
may claim live authority, market edge, operational readiness, or completeness
that the evidence does not establish. If later work materially changes the
feature, add a new dated entry or clearly supersede the old entry; do not
silently rewrite history.

## 4. Keep session state synchronized through Git

`docs/SESSION_HANDOFF.md` is the canonical cross-computer development state.
Do not maintain a private replacement, rely on conversation memory, or copy a
loose version of the file between computers as the normal synchronization
method.

Update the handoff whenever a review, feature, or milestone is completed, and
whenever branch topology, commit availability, validation, open issues,
machine-local dependencies, authorization, or the recommended next step
materially changes. At minimum, record:

- the repository, active branch, base commit, review head, and final commits;
- whether each required commit is local-only, pushed, or merged;
- the disposition of every reviewed commit;
- the P0–P3 issue summary, including unresolved items and corrected findings;
- exact focused/full validation and environment versions;
- completed milestone functionality and the next authorized step;
- dirty-worktree or local-only work that must be preserved; and
- machine-local state by presence, path, hash, or non-sensitive metadata only.

Never place secret values, account numbers, private keys, licensed data, or
other sensitive contents in the handoff.

Every implementation or review commit series must also update only the
authoritative associated record whose behavior or evidence changed. Do not
make ceremonial edits to unrelated plans or records. The general Action Plan
changes only when sequencing, milestone status, a gate, or the next authorized
step changes; its update is a concise reference to the associated record, not
a duplicate implementation narrative, finding ledger, or test report.

Commit the handoff separately after the implementation or review commits it
describes exist, so it can name their exact hashes. Cross-computer sync is not
complete until the handoff commit and every commit needed to resume are
reachable from an approved Git remote. Pushing or merging still requires the
repository owner's explicit authorization. Until that authorization is given,
the handoff must prominently mark the branch and commits as local-only and
warn that another computer cannot retrieve them with `git fetch`.

On a new computer, fetch and switch to the recorded branch, then read the
tracked handoff from that branch before acting:

```powershell
git fetch --all --prune
git switch --track origin/<recorded-branch>
git status --short --branch
Get-Content -Raw docs\SESSION_HANDOFF.md
```

Do not claim that a computer transition is ready merely because the handoff
file is committed locally. Verify that its commit is present on the remote and
that a fresh clone or fetch can resolve the recorded history.

## 5. Review completion requirements

A review is complete only when:

1. every commit has a recorded disposition;
2. every issue is ranked P0 through P3 and includes a reason for fixing or
   closing it;
3. confirmed defects have corrections and verification where authorized;
4. focused tests, the full suite, compile checks, and diff checks have run on
   the final code tree in proportion to risk;
5. the final report states acceptance, conditional acceptance, or rejection;
6. any completed feature or milestone has its two-paragraph entry in
   `docs/FEATURE_MILESTONE_RECORD.md`;
7. `docs/SESSION_HANDOFF.md` reflects the final commits, validation, issue
   state, remote availability, remaining work, and next step;
8. review corrections and handoff updates are committed separately unless the
   repository owner directs otherwise; and
9. cross-computer synchronization is reported as complete only after the
   required branch and handoff commit are verified on the approved remote.

Do not push, merge, or open a pull request without explicit authorization.
