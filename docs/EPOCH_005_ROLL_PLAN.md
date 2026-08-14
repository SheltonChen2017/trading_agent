# Epoch-005 roll — prepared and executed 2026-08-13

Status: **owner-authorized and executed 2026-08-13. Do not execute this plan
again.** This file retains the preparation facts and records their outcome;
`docs/OPERATIONAL_FACTS.md` is the current host-state authority.

Authority: `docs/OPERATIONS_RUNBOOK.md` owns the canonical order and drill
list. This plan does not restate it loosely — it records the host-specific
values, the preconditions to check first, and the judgement calls.

## 1. Why the roll was performed

The roll closed `paper-epoch-004` and restarted the 60-session / 30-order
evidence window. **The cost of a roll is exactly the evidence discarded, and
that cost only grows.**

- At preparation, `paper-epoch-004` had **2 recorded sessions** (2026-08-11,
  2026-08-12). The scheduled 2026-08-13 capture completed before the roll, so
  the epoch closed with **3** observations. Paying that cost early was the
  owner's explicit decision.
- Seven merged, independently reviewed changes were waiting: AP-8, AP-9,
  QC-2, AP-10, AP-11, three-sleeve M3, and SELL-1 (plus the SELREV/SELCR
  exact-share corrections). They deployed at `752d3b7`.
- M3 dividend reinvestment and SELL-1 owner-directed sells became available
  on the operational runtime without gaining automatic execution authority.
- Deploying AP-11 removed the known source of false negative-age freshness
  warnings; continued absence under epoch-005 remains the operational check.

The primary cost considered here was lost accrued evidence, and it was still
small. Deployment risk, broker availability, ledger agreement, and task
recovery remained independent reasons to stop; the preconditions below were
the controls for those risks.

## 2. Exact outcome (read-only re-checks)

| Fact | Executed value | How to re-check |
|---|---|---|
| Active epoch | `paper-epoch-005`, started 2026-08-13T23:59:07Z | `paper-evidence-status` |
| Sessions recorded at roll completion | 0 under epoch-005; the first scheduled capture was expected 2026-08-14 | `paper-evidence-status` |
| Deployed runtime | `752d3b7` in `C:\git\trading_agent_operational` | `git -C ... log --oneline -1` |
| Deployed source | merged and independently reviewed `main` tip at execution time | `git show 752d3b7` |
| Operator DB | `C:\git\customizedAgent\trading_agent\data\trading_assistant.db` | `TRADING_ASSISTANT_DB` |
| Epoch host | `REDMOND\sheltonchen` | `whoami` |
| Task interpreter | `C:\git\trading_agent_venv` | installed task action |
| Observation trigger | **16:30 LOCAL** (see §5) | read the trigger, never derive it |

## 3. Preconditions verified for the executed roll

1. **Operational alert causes understood and resolved.** At preparation
   there were **5 open** (one critical `portfolio_accounting` staleness, one
   critical `operations_cycle` failure, one critical `broker_account`, plus
   two warnings), all traceable to an Alpaca connectivity outage on
   2026-08-13 (~08:27–10:15 local; the endpoint answered normally at 15:22).
   Broker calls recovered before the roll; all five alerts were acknowledged
   after their causes were verified resolved, leaving zero open at completion.
2. **Books matched.** `ledger-reconcile` returned `matched: true` with zero
   mismatches before the swap and again on the deployed runtime.
3. **Clean worktrees.** The operational checkout passed the clean-tree and
   exact-commit evidence boundaries.
4. **Reviewed mainline target.** `752d3b7` was merged to `main` and had
   completed independent review before deployment.
5. **Owner present and authorizing.** The procedure was not unattended.

## 4. Executed order (runbook §"replacing a frozen runtime")

Deployment does not close the epoch, and the new epoch must not start before
the upgraded ledger reconciles. That ordering is the whole point.

1. **Disable** all four `TradingAgent-Paper-*` tasks — disabling, not
   stopping; triggers restart a stopped task.
2. **Close** `paper-epoch-004` while `b837374` is still checked out.
3. **Deploy** the reviewed `main` commit into
   `C:\git\trading_agent_operational`.
4. **`ledger-reconcile`** — require `matched: true` before continuing.
5. **`readiness`**, then **start epoch-005** on the exact deployed commit.
6. **All five drills**, re-enable the tasks, verify they execute.

Before calling evidence "accumulating," the remaining check is the first
SCHEDULED
`paper-observation` completed under epoch-005 and bound the deployed
lineage. A green manual `operations-cycle` does not prove the evidence
cadence — with zero observations, `lineage_consistent: true` is vacuous.

## 5. Host-specific hazards and lessons from this roll

- **The observation fires at 16:30 local, not 13:30.** The installed trigger
  is `2026-08-05T16:30:00-07:00`, registered three days before
  `Convert-EasternClockToLocal` entered the installer. Step 6 re-enables the
  existing tasks rather than reinstalling them, so this survives the roll.
  The installer was not re-run, so the 16:30-local cadence was preserved.
  Any future reinstall may move it to 13:30 local and must be re-measured.
- **Plan the timing around the observation.** Rolling shortly before 16:30
  local would risk the scheduled observation landing while tasks are
  disabled. This roll ran immediately after a successful capture.
- **M3's dividend pool was expected to be non-zero on first deploy.** The
  operator ledger already held confirmed corporate-action dividends, so the
  reinvestment surface could expose real available dollars immediately.
  Nothing spends them without an explicitly approved proposal.
- **CR-W3 remains a watch, not a blocker.** The AEP dividend (~2026-09-10)
  needs the already-deployed CR-W2 handler plus the acknowledgement path;
  both shipped in the epoch-004 roll. Rolling now neither helps nor hurts it.
- **JNLC still requires operator accounting judgement.** Never widen
  reconciliation tolerance; never post a manual compensating entry.

## 6. Decisions and unchanged exclusions

- **Whether to roll:** resolved by owner authorization on 2026-08-13.
- **Whether to reinstall the tasks:** resolved for this roll as no. Any
  future cadence change remains separate and separately verified.
- **M4** (prepared gain-review trim proposals) remains deferred by default.
- **GR-6 off-machine backup** stays blocked by the corporate-host
  constraint: no cloud destination is permitted, so only physical media
  qualifies. Unchanged by this roll.

## 7. Recorded result

`paper-epoch-004` closed at 23:57:17Z with 3 observations. The operational
checkout moved to `752d3b7`; reconciliation matched with zero mismatches;
`paper-epoch-005` started at 23:59:07Z; all five required drill types passed;
the tasks were re-enabled; and a manual operations cycle was green. The
lineage hash and detailed drill/alert observations remain in
`docs/OPERATIONAL_FACTS.md`. This record does not authorize another roll.
