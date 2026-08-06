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

## 2. OWNER DECISION MADE (2026-08-06): option B — keep the epoch

The owner chose to keep `paper-epoch-001` frozen and select
`my_policy.json` manually in the sidebar at each launch, rather than
re-binding the epoch. Do not deploy the policy-default resolver or the
process singleton to the operational checkout without a new, explicit
authorization.

| Thing | Policy | Fingerprint | `allow_new_positions` |
|---|---|---|---|
| `paper-epoch-001` lineage | `assistant/default_policy.json` | `66dd70e1…` | **False** |
| What the owner actually trades under | `assistant/my_policy.json` | `4a942cbc…` | **True** |

Verified 2026-08-06 against the operator database and both checkouts.

**Consequence of B, stated plainly so nobody rediscovers it later.** The
scheduled `PaperObservation` task passes no `--policy`, and the frozen
checkout's eager argparse default is `default_policy.json` — so session
capture keeps matching the epoch's bound fingerprint and keeps succeeding.
Meanwhile the owner's manual trading happens under `my_policy.json`. The
epoch therefore accumulates sessions whose recorded lineage names a policy
that **forbids the very buys being made**.

That is tolerable for paper operation and it is the owner's call, but
`paper-epoch-001` must not later be cited as prospective evidence for
trading under the personal policy. It is evidence for `default_policy.json`
by its own lineage, and for nothing else. The first epoch that can honestly
support the personal policy is the one started after the resolver is
deployed.

`my_policy.json` is gitignored and exists independently in **both**
checkouts (identical, 1,579 bytes), so the manual sidebar selection works
today without any deploy.

## 3. Latest review outcome (2026-08-06)

Claude tip reviewed: `6f9a82a` (AST pin for CLI `load_policy` sites +
self-heal observation notes). **Accepted after correction.**

| ID | Pri | Result |
|---|---|---|
| CROPS-003 | P2 | Accepted (AST invariant pin) |
| CCROPS-001 | P2 | AST shape tightened to exact `_cli_policy_path(args)` |
| CCROPS-002 | P1 | Live duplicate OrderMonitor/Watchdog processes despite IgnoreNew; process-level singleton added in code (deploy deferred) |
| CCROPS-003 | P3 | Stale "push/PR still needed" handoff text removed |

Claude then counter-reviewed the Codex correction (`e3c2433`):

| ID | Pri | Result |
|---|---|---|
| CCCROPS-001 | P2 | **Fixed.** Both call sites discard the returned `ProcessSingleton`, so the lock held only because `atexit.register` incidentally kept the object reachable. Dropping that line — which reads as redundant, since the OS releases file locks on exit — silently released the lock after GC while the worker ran on. All 5 submitted tests passed under that mutation, because every one binds the result to a local and no caller does. Module-level `_HELD` registry now owns it; regression test reproduces the call-site shape across a real process boundary. |
| CCCROPS-002 | P3 | Open (documented). Duplicate-worker observation credible; asserted mechanism not established — the pairs started 9s apart, both parented to the Task Scheduler service, matching neither the heal interval nor a logon. |
| CCCROPS-003 | P3 | Open (documented). Singleton refusal is a new non-zero `LastTaskResult` the verifier treats as failure; only reachable under an orphan, where failing is defensible. |
| CCCROPS-004 | P3 | Open (documented). `lock_path_for` name validation narrower than its docstring (`order:stream` → NTFS ADS; `D:evil` escapes). Unreachable today — literals only. |

Verified empirically, not accepted on inspection: cross-process exclusion
on Windows **and** lock release after a hard kill. The second matters — a
lock surviving a killed process would have bricked self-heal permanently.

Ledger: `docs/REVIEW_2026-08-06_CROPS003_OPS_FOLLOWUP.md`.

Claude follow-up quality: **8.5/10 submitted; 9.4/10 corrected**.
Codex correction quality: **8.5/10 submitted; 9.4/10 counter-corrected**.

Ops-hardening / UI chrome round (PR #157) remains accepted; this review is
the post-merge counter-follow-up pass.

## 4. Machine state (verified 2026-08-06)

- Tasks registered; OrderMonitor/Watchdog Running; heal trigger present;
  `MultipleInstances=IgnoreNew` present.
- **Duplicate long-runners observed** against the shared operator DB
  (`monitor-orders` and `watchdog` each twice, ~09:35 local). **Re-checked
  ~10:05: the duplicates are gone** — one `monitor-orders` (PID 7804) and
  one `watchdog` (PID 5180) remain, both still from 09:34:59. No manual
  collapse is outstanding; re-check PIDs before assuming a healthy pair.
  The singleton lock is in the development tree only until an authorized
  deploy, so the exposure remains live on `8a2233c`.
- Self-heal can restart a dead task; it cannot guarantee single-process
  uniqueness without the process lock.
- Streamlit app relaunched 09:54 from the operational checkout via
  `C:\git\launch_trading_app.ps1` for the owner's 30-trade / 60-session
  run. Note it seeds `default_policy.json` (the `my_policy.json` default is
  development-only), so the sidebar must be pointed at `my_policy.json` for
  buys — which is the §2 decision in miniature.

## 5. Validation (exact final tree)

- Focused: **36 passed** (singleton 6, policy path / UI chrome / task
  resilience 30).
- Full suite: **2876 passed / 1 skipped / 25 warnings** (588s) — one more
  than the Codex tree, which is the added CCCROPS-001 regression test.
- `compileall` clean; `git diff --check` clean.
- No funded-account contact. Singleton not deployed to operational checkout.

## 6. What is next

1. §2 decided (option B, 2026-08-06). Nothing outstanding; deploy of the
   resolver and singleton waits for the next epoch boundary or an explicit
   owner authorization.
2. Owner: nothing outstanding on duplicate processes (resolved on their
   own); re-check PIDs rather than assuming, since the cause is unknown
   (CCCROPS-002).
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
