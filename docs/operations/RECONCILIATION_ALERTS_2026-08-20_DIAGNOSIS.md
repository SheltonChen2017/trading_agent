# Read-only diagnosis — the two open reconciliation alerts

Status: **read-only diagnosis, owner-authorized 2026-08-20. Nothing was
acknowledged, closed, altered, or repaired.** The operator database was
opened through a `mode=ro` URI; no scheduled task, power setting, threshold,
or alert row was touched.

## Verdict

**Both alerts are stale alert state, not a live fault, and not missing
operational work.** Reconciliation is running correctly right now. The
alerts were raised by genuine staleness at the time they fired, that
staleness was caused by the **host sleeping**, and the condition has since
cleared without any repair.

Neither alert indicates a data mismatch. Both carry `matched=True`,
`mismatches=0`, `errors=0`.

## The two alerts as they stand

| alert_id | Severity | Check | Occurrences | First seen | Last **failure** |
|---|---|---|---:|---|---|
| 3 | critical | `portfolio_ledger_reconciliation` | 2,071 | 2026-08-05T17:51:42Z | 2026-08-21T02:49:04Z |
| 105 | warning | `reconciliation_freshness` | 17 | 2026-08-06T00:02:14Z | 2026-08-21T02:49:04Z |

`last_seen_at` updates only when the check **fails**, so both rows record
the last failure, not a current one. The two differ only in threshold:
`portfolio_ledger_reconciliation` allows 30 minutes
(`assistant/operations.py`), `reconciliation_freshness` allows 5 minutes
(`assistant/readiness.py`).

## Evidence that reconciliation is healthy now

- `ledger_reconciliation_runs` holds 1,323 runs from 2026-08-05T18:23Z to
  **2026-08-21T06:02Z**, on a steady ~10-minute cadence.
- **20 reconciliation runs have completed since the last alert failure** at
  02:49Z, every one `matched=True` with `mismatch_count=0`.
- No mismatch appears anywhere in the most recent 40 runs.

## Root cause: the host sleeps, and the tasks are not allowed to wake it

Every multi-hour reconciliation gap corresponds to a Windows sleep window.
The correlation is exact, not approximate:

| Sleep (Power-Troubleshooter) | Wake | Reconciliation gap |
|---|---|---|
| 2026-08-21T00:45:07Z | 02:42:58Z | 00:42:23Z → 02:49:06Z |
| 2026-08-20T15:22:46Z | 17:00:50Z | 15:22:22Z → 17:07:22Z |
| 2026-08-19T00:49:33Z | 04:44:12Z | 00:22:24Z → 04:50:20Z |
| 2026-08-18T00:52:49Z | 02:10:02Z | 00:22:22Z → 02:16:30Z |
| 2026-08-17T14:54:51Z | 16:44:44Z | 14:53:25Z → 16:50:58Z |
| 2026-08-15T00:27:28Z | 01:38:33Z | 00:22:25Z → 01:44:41Z |
| 2026-08-12T07:05:37Z | 17:09:10Z | 07:02:44Z → 17:15:15Z |

There are 22 gaps over 30 minutes across the whole history, and the ones
inspected all match a sleep window. All three paper tasks are registered
with **`WakeToRun=False`** and `StartWhenAvailable=True`: they do not wake
the machine, and on wake they resume rather than backfill. So a sleep longer
than 30 minutes guarantees the critical check fails at least once on wake.

This is the alerting system working as designed. It is reporting a real
property of the host — that supervision stops while the machine sleeps —
rather than misfiring.

## Effect on epoch-006 evidence

**No epoch-006 observation has been lost, and no captured evidence is
corrupted.**

- Paper observations are captured at 23:30Z daily. None of the sleep windows
  above covers 23:30Z.
- `paper-epoch-006` holds **2 observations**, session dates 2026-08-19 and
  2026-08-20 — one for each trading session since the epoch opened at
  2026-08-19T19:48Z. Nothing is missing.
- Correction to an earlier verbal report in this session: the figure "11
  observations" was the **all-epoch total** across epochs 001–006, not
  epoch-006's count. Per-epoch: 001=1, 002=1, 003=1, 004=3, 005=3, **006=2**.

The residual risk is not corruption but **missed observations**. The
fail-closed path is real and has fired before: the acknowledged alert
"paper observation failed: Ledger reconciliation failed; refusing to capture
paper NAV" (first seen 2026-08-05, last 2026-08-07) coincides with the
missing 2026-08-07 session observation. If the host sleeps across 23:30Z on
a trading day, the observation is refused rather than captured with stale
inputs — correct behaviour, but it lengthens time-to-sufficiency for an
epoch that needs 60 observations and currently has 2.

## Proposed correction — requires owner approval, not performed

Ranked, with the safest first. **None of these has been done.**

1. **Acknowledge both alerts** (owner action, operator UI). This clears
   resolved noise and changes no operational behaviour. It is the minimal
   correct response to stale state, and it is reversible.
2. **Decide deliberately about sleep.** The durable options are to stop the
   host sleeping during the observation window, or to set `WakeToRun=True`
   on the paper tasks so supervision survives sleep. Either is an
   operational change to installed tasks or power policy and needs explicit
   owner instruction; both would also change the machine's behaviour outside
   this project.
3. **Do not loosen the thresholds.** The 30-minute and 5-minute windows are
   genuine execution-readiness gates. Widening them to accommodate sleep
   would weaken a real safety control to silence a truthful alarm, and would
   make a future *genuine* reconciliation outage invisible for longer.

A separate, smaller improvement worth considering later: freshness alerts
have no auto-resolution, so a transient condition leaves a permanently open
row that must be cleared by hand. Auto-closing after N consecutive passing
checks would reduce standing noise without touching any threshold. That is a
code change, not an operational one, and is out of scope here.

## What was not examined

The 2,071 occurrence count spans 2026-08-05 onward and was not decomposed
sleep-by-sleep; only the most recent gaps were correlated. Whether every one
of the 22 long gaps has a matching sleep event is therefore probable but not
established. No non-paper task, no broker state, and no order-lifecycle
table was inspected.
