# Development session handoff

Prepared: 2026-08-06 morning, after Codex independently reviewed Claude's
CROPS-003 follow-up (`6f9a82a`, already on `main` via PR #157) and corrected
it on `codex/review-crops003-ops-followup-20260806`.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-001` ACTIVE since 2026-08-05T18:27Z on frozen commit
`8a2233c`. Operational checkout verified this session still at that commit,
clean. Never deploy development commits mid-epoch.

Session 1 of 60 recorded (`paperobs-94882d5da9668087e99355c5`). Do not
assume later sessions without re-checking the operator database.

## 2. OPEN OWNER DECISION — epoch bound to the wrong policy file

Unchanged from 2026-08-05:

| Thing | Policy |
|---|---|
| `paper-epoch-001` lineage | `assistant/default_policy.json` |
| What the owner actually trades under | `assistant/my_policy.json` |

Options:

- **A (recommended): re-bind now.** Close epoch, deploy merged tip to the
  operational checkout, start `paper-epoch-002` under the resolved personal
  policy.
- **B: keep the epoch.** Stay on `8a2233c` until the natural boundary; do
  not deploy policy-default or singleton changes mid-epoch.

## 3. Latest review outcome (2026-08-06)

Claude tip reviewed: `6f9a82a` (AST pin for CLI `load_policy` sites +
self-heal observation notes). **Accepted after correction.**

| ID | Pri | Result |
|---|---|---|
| CROPS-003 | P2 | Accepted (AST invariant pin) |
| CCROPS-001 | P2 | AST shape tightened to exact `_cli_policy_path(args)` |
| CCROPS-002 | P1 | Live duplicate OrderMonitor/Watchdog processes despite IgnoreNew; process-level singleton added in code (deploy deferred) |
| CCROPS-003 | P3 | Stale "push/PR still needed" handoff text removed |

Ledger: `docs/REVIEW_2026-08-06_CROPS003_OPS_FOLLOWUP.md`.

Claude follow-up quality: **8.5/10 submitted; 9.4/10 corrected**.

Ops-hardening / UI chrome round (PR #157) remains accepted; this review is
the post-merge counter-follow-up pass.

## 4. Machine state (verified 2026-08-06)

- Tasks registered; OrderMonitor/Watchdog Running; heal trigger present;
  `MultipleInstances=IgnoreNew` present.
- **Duplicate long-runners observed** against the shared operator DB
  (`monitor-orders` and `watchdog` each twice, ~09:35 local). Owner should
  manually collapse to one pair; the new singleton lock is in the
  development tree only until an authorized deploy.
- Self-heal can restart a dead task; it cannot guarantee single-process
  uniqueness without the process lock.

## 5. Validation (exact final tree)

- Focused: **32 passed** (singleton, policy path, task resilience, import boundary).
- Full suite: **2875 passed / 1 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.
- No funded-account contact. Singleton not deployed to operational checkout.

## 6. What is next

1. Owner decision on §2 (epoch re-bind A vs B).
2. Owner: collapse duplicate long-runner processes on this host.
3. Roadmap: GR-7b / GR-7c / GR-6, or GR-7d owner decision — unchanged.
4. Deploy singleton + policy-default only at epoch boundary (or with
   explicit owner deploy authorization).

## 7. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Incomplete/unverified reports must say so in the artifact.
- Wash-sale output stays advisory.
- Which policy file governs must always be visible on screen.
- Long-running workers must be single-instance at the process level, not
  only at the Task Scheduler instance level.
