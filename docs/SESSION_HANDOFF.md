# Development session handoff

Prepared: 2026-08-05 (midday) — **the first paper evidence epoch is
ACTIVE.** Phase 5 deployment completed end to end this session: review
round merged (PR #152), tasks running, ledger bootstrapped and reconciled
clean, epoch started on the frozen commit, and all five required drills
passed and recorded under exact epoch lineage.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. THE EPOCH

    evidence_epoch   = paper-epoch-001 (ACTIVE since 2026-08-05T18:27:04Z)
    code_commit      = 8a2233c5e54c08a405b712e99020f05d40495186 (PR #152)
    strategy         = owner-directed-paper-policy 1.0.0
    model_id         = no-ml-model (no ML participates in any decision)
    mandate          = 693799c0acb440040064eaa69a57d87c32186e63709f49ffa52f6feb39956487 (approved)
    policy           = 66dd70e1bd74ce56e02e3f770cce7d5f68f50f3fd7eb55f202d8243c374d759f
    broker account   = Alpaca paper 15f1e8ef-3b48-406b-80a7-2960e3098b80
    lineage_hash     = 71d228d9ec5a948eca251958720a13e7e0f58ba5335626f50e7dc8d3a78a9ba2

**Standing rules while the epoch is active (model 2):**

- The operational checkout `C:\git\trading_agent_operational` stays on
  `8a2233c` until `paper-epoch-close`. Development continues freely on
  `main`/branches in the dev checkout and is simply NOT deployed there.
- One operational host (this machine), one operator database
  (`C:\git\customizedAgent\trading_agent\data\trading_assistant.db`), one
  Alpaca paper account. The owner places paper trades only from this
  machine via `C:\git\launch_trading_app.ps1`.
- The 60-session / 30-order clock counts only observations recorded
  inside this epoch; trades from before 18:27Z today do not count.

## 2. What was completed this session (all verified)

1. **Review round merged**: PR #152
   (`codex/review-recent-claude-changes-20260805`, second parent
   `f2c97cc` = Claude's counter-review tip). All six RCREV findings were
   counter-review-confirmed red on the submitted snapshots; CRRC-001
   added the user-scope credential lift to the generated launcher.
   Full suite on that tree: 2,757 passed / 1 skipped / 25 warnings.
2. **Scheduled tasks live**: the four `TradingAgent-Paper-*` tasks run
   under Interactive logon (Credential Guard blocks S4U on this
   domain-joined machine — diagnosis proven with an Interactive probe
   task). OrderMonitor + Watchdog are long-running console windows in the
   owner's session (minimize, never close). The two long-running tasks
   were restarted after the operational checkout moved to `8a2233c`.
3. **Wrappers regenerated from the reviewed bootstrap**
   (`scripts/setup_operational_host.ps1` at `8a2233c`): launcher with
   registry credential lift; elevated wrapper with
   `-TaskLogonType Interactive` and `-RequireTaskRun` verification.
4. **Ledger**: `readiness` exit 0 → `ledger-bootstrap --confirm
   bootstrap` (opening snapshot hashed
   `6b46f16e…`) → `ledger-reconcile`: **matched, 0 mismatches**
   (AAPL 3, AMZN 8, AVGO 7, BBB 16, MSFT 5, NFLX 20 + cash).
5. **Epoch started** (block above), `already_started: false`, exit 0.
6. **All five required drills passed and recorded inside the epoch**:
   - `ambiguous_submission` drill-7e0ca9abe7a118d6d8aae48a
   - `kill_switch` drill-f70b9e987af57520780e55e5
   - `restart_recovery` drill-b653bcf9c869efb77b7c305f
     (fault matrix report sha256 `99db1702…`, 11/11 fault IDs)
   - `backup_restore` via `recovery-drill`: restore verified,
     `table_counts_match: true`
   - `alert_delivery` via `alert-self-test --record-drill`: real Windows
     toast delivered, storage-verified, `passed: true`
   `paper-evidence-status paper-epoch-001`:
   `all_required_drills_passed: true`, `lineage_consistent: true`.
7. **Operational health**: after bootstrap + the cycle's first backup,
   the ONLY failing check was `backup_restore_drill: never completed`,
   and the recovery drill has now completed it. Old open alerts in the
   table predate bootstrap (historical, deduplicated).

## 3. Expected staged states (do NOT relabel as failures)

- `platform-readiness` remains nonzero: evidence needs 60 sessions/30
  orders (day zero), strategy needs a confirmed production-authoritative
  finding (none exists), data_integrity is blocked-by-design until GR-4,
  and offline mode skips broker checks. This is the documented staged
  condition.
- `paper-evidence-status` reports `metric_error: at least two paper
  observations are required` — correct until two session closes.
- The PaperObservation task's `last_result` stays 1 until its first
  post-epoch scheduled run (16:30 local daily); OperationsCycle turns
  fully green now that ledger + backup + restore drill exist. The strict
  verifier (`-Scope operational -ExpectedTaskLogonType Interactive
  -RequireTaskRun`) should exit 0 after today's 16:30 observation run;
  verify then rather than immediately.
- Earlier field incidents, all resolved: stale-credential
  "unauthorized" (launcher now lifts user-scope registry values), stale
  AVGO duplicate-order block (order had actually filled; reconciled),
  Alpaca transient 500 (self-recovered).

## 4. What is next

1. **Nothing is owner-blocked.** The owner paper-trades daily via the
   launcher; the cadence records evidence automatically. Suggested
   check-in: `paper-evidence-status paper-epoch-001` after a few sessions.
2. Next code milestone (dev checkout, not deployed): **GR-4 data-layer
   honesty** per the action plan. Also available owner decisions:
   committee experiment-gate removal (all ADR prerequisites met); ML
   shadow tasks for a later epoch.
3. At the epoch boundary (60+ sessions or a deliberate close):
   `paper-epoch-close`, then the operational checkout may move forward.

## 5. Non-negotiable boundaries

- Paper trading only; `allow_autonomous_execution` remains false; every
  order still requires exact human approval + deterministic revalidation.
- Never deploy moving development commits into the operational checkout
  during the epoch; never run a second operational host or cadence.
- No manual edits to evidence tables, ever.
- ML/LLM output stays advisory/observational; committee remains
  experiment-gated until a separately owner-authorized removal.
- Never commit credentials, operator databases, licensed data, or
  evidence artifacts.

## 6. Machine-local state (re-measured this session)

- `C:\git\trading_agent_operational`: clean `main` at `8a2233c` (FROZEN).
- `C:\git\trading_agent_venv`: task interpreter, suite-validated.
- `C:\git\launch_trading_app.ps1` + `C:\git\install_operational_tasks_elevated.ps1`:
  regenerated from the reviewed bootstrap at `8a2233c`.
- Four tasks installed (Interactive); OrderMonitor/Watchdog running; the
  OrderMonitor's Alpaca websocket flaps on the corporate network and
  falls back to polling by design.
- The owner's Streamlit app runs via the launcher against the frozen
  checkout and single operator DB.
