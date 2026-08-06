# Development session handoff

Prepared: 2026-08-06 morning, after Codex independently reviewed Claude's
CROPS-003 follow-up (`6f9a82a`, already on `main` via PR #157) and corrected
it on `codex/review-crops003-ops-followup-20260806`.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json` (`4a942cbc…`). The operational
checkout is now pinned there. **Never deploy development commits
mid-epoch** — the next deploy waits for the next epoch boundary.

`paper-epoch-001` is CLOSED (2026-08-06T17:55Z) with one observation,
retained as a plumbing shakedown only. See §2.

Sessions recorded under `paper-epoch-002`: expect the first at the 16:30
capture on 2026-08-06. Do not assume any count without re-checking
`paper_account_observations` in the operator database.

## 2. RESOLVED (2026-08-06): epoch re-bound to the personal policy

The owner initially chose option B (keep the epoch, select the policy by
hand), then reversed to **option A** once the evidence consequence was
spelled out. Executed the same morning. The policy/lineage mismatch that
sat open since 2026-08-05 is **closed**.

| | `paper-epoch-001` (closed) | `paper-epoch-002` (active) |
|---|---|---|
| Policy | `default_policy.json` | **`my_policy.json`** |
| Policy fingerprint | `66dd70e1…` | **`4a942cbc…`** |
| `allow_new_positions` | False | **True** |
| Code commit | `8a2233c` | **`9a91498`** |
| Sessions | 1 (discarded) | collecting |
| Strategy / model | `owner-directed-paper-policy` 1.0.0 / `no-ml-model` | identical |

Mandate fingerprint and broker account are unchanged across both, so the
only deliberate lineage differences are the policy and the code commit.

**Why the reversal.** Under B the scheduled `PaperObservation` task — which
passes no `--policy` — kept resolving `default_policy.json` and kept
matching epoch-001's bound fingerprint, so capture would have succeeded for
60 sessions while the owner traded under `my_policy.json`. The epoch would
have accumulated a full record whose own lineage named a policy forbidding
the buys it contained: unusable as evidence for the strategy actually being
run. The cost of fixing it was **one** discarded session against roughly
three months of unusable record, and delay to first citable evidence
(≈October vs ≈February).

`paper-epoch-001` is retained as a closed plumbing shakedown. Do not cite
it as prospective evidence for anything.

## 2a. Deploy performed 2026-08-06 (epoch boundary)

The operational checkout advanced `8a2233c` → `9a91498` — the designed
moment under epoch model 2, not a mid-epoch deploy. Sequence, all verified:

1. Four `TradingAgent-Paper-*` tasks stopped and **disabled** via
   `C:\git\epoch_swap_tasks_elevated.ps1` (machine-local, elevated). On this
   host a non-elevated `Stop-ScheduledTask` succeeds but `Disable` returns
   "Access is denied", so a stopped long-runner is restarted by its
   5-minute heal trigger — disabling is what actually holds them down.
2. Streamlit stopped; verified no Python process held the operator DB.
3. Verified backup: `data/backups/trading_assistant-20260806T175415Z.db`.
4. `git pull --ff-only` to `9a91498`; clean; resolver, `process_singleton`,
   `_HELD` fix and `my_policy.json` all confirmed present in the deployed
   tree.
5. Confirmed `resolve_policy_path()` returns `my_policy.json` /
   `4a942cbc…` **before** closing anything.
6. `paper-epoch-close paper-epoch-001`, then `paper-epoch-start
   paper-epoch-002` reusing 001's strategy and model identifiers.
7. `_active_runtime_lineage()` exercised with the exact argument shape the
   scheduled task produces (`policy=None`, default mandate): **PASS**.
8. Tasks re-enabled, long-runners started, app relaunched.

`requirements.txt` was unchanged across the range, so no dependency install
was needed. The `storage.py` additions in the range are the GR-7a schema
migrations, applied idempotently on first open.

The process singleton is now **live**: `data/locks/order-monitor.lock` and
`data/locks/operations-watchdog.lock` are held by the running workers,
which is direct evidence the deployed code — not the old tree — is what is
executing. `data/locks/` is gitignored.

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

State after the epoch swap (§2a), all four tasks enabled:

- OrderMonitor `Running` (PID 1088), Watchdog `Running` (PID 41008), both
  started 10:56:34 — exactly one of each. OperationsCycle and
  PaperObservation `Ready`; next capture 16:30.
- **Process singleton is live.** `data/locks/order-monitor.lock` and
  `data/locks/operations-watchdog.lock` are held by the running workers.
  Their existence is the direct evidence that the deployed tree — not the
  previous one — is what is executing.
- Streamlit relaunched 10:56 from the operational checkout via
  `C:\git\launch_trading_app.ps1` (health `ok` on 8501). It now seeds
  `my_policy.json` by itself; **no manual sidebar change is needed any
  more.**
- Earlier the same morning, duplicate long-runners were observed (~09:35)
  and had resolved on their own by ~10:05; cause never established
  (CCCROPS-002). A recurrence should now surface as a singleton refusal
  rather than silent duplication.
- Self-heal can restart a dead task; it cannot guarantee single-process
  uniqueness without the process lock.
- On this host, modifying these tasks requires elevation: a non-elevated
  `Stop-ScheduledTask` works but `Disable-ScheduledTask` returns "Access is
  denied". Use `C:\git\epoch_swap_tasks_elevated.ps1 -Action Disable|Enable`
  (machine-local, not in the repo).

## 4a. Full-project review (2026-08-06, later the same day)

Owner asked for a module-by-module sweep — the first since 2026-07-30, and
**378 commits** of ~62K production lines. Branch
`user/claude/full-project-sweep-20260806`, commit `87593f8`, pushed; PR not
opened. Ledger: `docs/REVIEW_2026-08-06_FULL_PROJECT_SWEEP.md`.

| ID | Pri | Result |
|---|---|---|
| FPS-001 | P2 | **Fixed.** `assistant/corporate_actions.py` bypassed `money.to_decimal` at three sites; `decimal.InvalidOperation` is an `ArithmeticError`, not a `ValueError`, so malformed journal metadata escaped both handlers and would traceback in the Streamlit/CLI callers of `tax_ledger_with_coverage` instead of reporting "unavailable". Malformed/missing split ratio now fails closed. |
| FPS-004 | P2 | **Fixed.** `ml/earnings_experiments._slice_metrics` printed `event_count = len(group)` beside metrics that silently drop non-finite pairs, so a slice the model mostly failed on showed a strong score over its few survivors. Added `usable_pair_count()` + `scored_event_count`. |
| FPS-002 | P3 | **Fixed.** A permanently-skipped parametrized case in `test_ml_experiments.py`; the case passes as written. Suite skip count 1 → 0. |
| FPS-003 | P2 | **OPEN.** `test_ui_chrome.py::test_app_title_is_trading_assistant` failed with `RuntimeError` on the pre-existing `main` baseline. **Intermittent, not order-dependent** — passes alone, with all 46 UI tests, and after the credential-mutating broker modules; did not reproduce on two later full runs. Disproven: the 3s `AppTest` default (already 60), live Alpaca calls (conftest clears creds), credential leakage from `test_alpaca_broker.py`. Not yet ruled out: `st.cache_data` global state, load-related timeout. **A single green suite is not evidence it is gone.** |

Both P2s are evidence-integrity defects, not execution defects — neither
could submit, size, or mis-price an order.

Reverse mutation recorded for both code fixes. Coverage was class-driven,
not line-by-line; §7 of the review names what was deliberately **not**
cleared (`ml/databento_source`/`_authoritative` bulk, `run_ml_shadow`, the
one-off research scripts, `ai_advisor`, `platform_readiness`,
`risk_copilot`, `strategy_proposals`, `execution_telemetry`,
`alert_delivery`, most of `storage.py`).

## 4b. Owner decision recorded: `require_earnings_data` stays `false`

Measured, not assumed, against the account's real holdings on 2026-08-06:
the feed resolves 5/7 (AAPL, AMZN, AVGO, MSFT, NFLX) and fails on **NVDL**
and **BBB**. Those two failures are structurally different and the policy
**cannot distinguish them**: NVDL is a leveraged ETF with no earnings event
at all, while BBB is a small cap whose real earnings the provider does not
carry. Setting the flag `true` would permanently block every ETF buy —
including the SOXX/SOXL-style strategy — while correctly blocking BBB.

Leave it `false` until "not a single-name equity" is separable from
"earnings exist but are not visible". Residual exposure is BBB-like names:
real earnings, invisible to the feed, silently unchecked. Risk-reducing
SELLs are exempt either way.

## 5. Validation (exact final tree)

Ops/singleton round (`a947146`):

- Focused: **36 passed** (singleton 6, policy path / UI chrome / task
  resilience 30).
- Full suite: **2876 passed / 1 skipped / 25 warnings** (588s).

Full-project sweep (`87593f8`, later the same day):

- Full suite: **2888 passed / 0 failed / 0 skipped / 25 warnings** (450s).
  Skip count reaching zero is FPS-002.
- `compileall` clean; `git diff --check` clean.
- No funded-account contact. Nothing from either round is deployed; the
  operational checkout stays frozen at `9a91498`.

## 6. What is next

1. §2 resolved and executed 2026-08-06. Nothing outstanding.
2. **Confirm the first `paper-epoch-002` session lands** at the 16:30
   capture on 2026-08-06. This is the one step not yet verified — the
   lineage gate was exercised directly and passed, but no observation has
   actually been written under the new epoch yet.
3. Owner: nothing outstanding on duplicate processes (resolved on their
   own); re-check PIDs rather than assuming, since the cause is unknown
   (CCCROPS-002). The singleton is now live and should make a recurrence
   visible as a refusal rather than as silent duplication.
4. Roadmap: GR-7b / GR-7c / GR-6, or GR-7d owner decision — unchanged.
5. The operational checkout is pinned at `9a91498` again. Development
   continues un-deployed; the next deploy waits for the next epoch
   boundary or an explicit owner authorization.
6. **Open PR for `user/claude/full-project-sweep-20260806` (`87593f8`)** —
   pushed, not merged. `gh` cannot create PRs on this repo (Enterprise
   Managed User), so the owner opens it.
7. **FPS-003 remains open** (§4a). Because it is intermittent, the way to
   make progress is to capture the full traceback the next time a full
   suite fails — the original baseline run was piped through `tail`, which
   discarded it. Do not treat a green suite as closure.

## 7. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Incomplete/unverified reports must say so in the artifact.
- Wash-sale output stays advisory.
- Which policy file governs must always be visible on screen.
- Long-running workers must be single-instance at the process level, not
  only at the Task Scheduler instance level.
