# Epoch-005 roll plan — prepared 2026-08-13, NOT YET AUTHORIZED

Status: **prepared for owner review. Nothing in this document has been
executed.** Deployment and epoch closure are owner-authorized actions; this
plan exists so the decision is made against exact facts rather than during
the procedure.

Authority: `docs/OPERATIONS_RUNBOOK.md` owns the canonical order and drill
list. This plan does not restate it loosely — it records the host-specific
values, the preconditions to check first, and the judgement calls.

## 1. Why roll now rather than later

Rolling closes `paper-epoch-004` and restarts the 60-session / 30-order
evidence clock at zero. **The cost of a roll is exactly the evidence you
discard, and that cost only grows.**

- `paper-epoch-004` has **2 recorded sessions** (2026-08-11, 2026-08-12) out
  of 60. Discarding two days is close to free; discarding thirty is not.
- Seven merged, independently reviewed changes are waiting and cannot reach
  the running app any other way: AP-8, AP-9, QC-2, AP-10, AP-11, three-sleeve
  M3, and SELL-1 (plus the SELREV/SELCR exact-share corrections).
- Two of those are features the owner asked for and cannot currently use —
  M3 dividend reinvestment and SELL-1 owner-directed sells.
- AP-11's false negative-age freshness warnings continue on the deployed
  runtime until it is replaced. They are noise, not danger, but they also
  make every future alert harder to read.

The argument against rolling is only ever "we lose accrued evidence". At two
sessions that argument is at its weakest it will ever be.

## 2. Exact state this plan assumes (re-verify before executing)

| Fact | Value at preparation | How to re-check |
|---|---|---|
| Active epoch | `paper-epoch-004`, started 2026-08-11T22:15:53Z | `paper-epoch-status` |
| Sessions recorded | 2 (2026-08-11, 2026-08-12) | read-only DB query |
| Deployed runtime | `b837374` in `C:\git\trading_agent_operational` | `git -C ... log --oneline -1` |
| Target commit | current `main` tip, **merged and reviewed only** | `git log --oneline -1 main` |
| Operator DB | `C:\git\customizedAgent\trading_agent\data\trading_assistant.db` | `TRADING_ASSISTANT_DB` |
| Epoch host | `REDMOND\sheltonchen` | `whoami` |
| Task interpreter | `C:\git\trading_agent_venv` | installed task action |
| Observation trigger | **16:30 LOCAL** (see §5) | read the trigger, never derive it |

## 3. Preconditions — all must hold before step 1

1. **Zero open operational alerts, with causes understood.** At preparation
   there were **5 open** (one critical `portfolio_accounting` staleness, one
   critical `operations_cycle` failure, one critical `broker_account`, plus
   two warnings), all traceable to an Alpaca connectivity outage on
   2026-08-13 (~08:27–10:15 local; the endpoint answered normally at 15:22).
   Do not roll while the broker is unreachable: step 4 requires a real
   reconciliation, and a network failure mid-roll is indistinguishable from
   a genuine accounting problem.
2. **Books matched.** `ledger-reconcile` returns `matched: true` with zero
   mismatches on the CURRENT runtime, before anything is disabled.
3. **Clean worktrees.** The operational checkout must be clean; evidence
   capture refuses a dirty tree or a commit other than the epoch's.
4. **The target commit is merged to `main` and independently reviewed.**
   Never deploy a topic branch.
5. **Owner is present.** This is not an unattended procedure.

## 4. Order of operations (canonical order, runbook §"replacing a frozen
runtime")

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

Then, before calling evidence "accumulating": confirm the first SCHEDULED
`paper-observation` completed under epoch-005 and bound the deployed
lineage. A green manual `operations-cycle` does not prove the evidence
cadence — with zero observations, `lineage_consistent: true` is vacuous.

## 5. Host-specific hazards for THIS roll

- **The observation fires at 16:30 local, not 13:30.** The installed trigger
  is `2026-08-05T16:30:00-07:00`, registered three days before
  `Convert-EasternClockToLocal` entered the installer. Step 6 re-enables the
  existing tasks rather than reinstalling them, so this survives the roll.
  **Do not re-run the installer as part of the roll** unless you intend to
  move the observation to 13:30 local — that would be a silent cadence
  change on the same day the epoch restarts, confounding both.
- **Plan the timing around the observation.** Rolling shortly before 16:30
  local risks the first scheduled observation landing while tasks are
  disabled. Prefer rolling early in the day, or immediately after a
  successful capture.
- **M3's dividend pool will be non-zero on first deploy.** The operator
  ledger already holds confirmed corporate-action dividends, so the
  reinvestment surface will show real available dollars immediately. Nothing
  spends them without an explicitly approved proposal, but expect the number
  rather than being surprised by it.
- **CR-W3 remains a watch, not a blocker.** The AEP dividend (~2026-09-10)
  needs the already-deployed CR-W2 handler plus the acknowledgement path;
  both shipped in the epoch-004 roll. Rolling now neither helps nor hurts it.
- **JNLC still requires operator accounting judgement.** Never widen
  reconciliation tolerance; never post a manual compensating entry.

## 6. What this plan deliberately does not decide

- **Whether to roll at all, and when.** Owner's call.
- **Whether to reinstall the tasks** and adopt the 16:30-Eastern rule. That
  is a separate, separately-verified change; §5 recommends not bundling it.
- **M4** (prepared gain-review trim proposals) remains deferred by default.
- **GR-6 off-machine backup** stays blocked by the corporate-host
  constraint: no cloud destination is permitted, so only physical media
  qualifies. Unchanged by this roll.

## 7. If the roll is authorized

Ask for the runbook's exact commands at execution time rather than copying
them from here — the runbook is the authority and may have moved. Record the
outcome in `docs/OPERATIONAL_FACTS.md` (epoch id, start time, deployed
commit, lineage hash, drill results, first scheduled observation) the same
way the epoch-004 roll was recorded, and update
`docs/ACTION_PLAN_2026-08-02.md` so the deployed/undeployed status of every
listed item stays true.
