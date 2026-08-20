# Preregistration: Strong-Buy ratings prospective capture (SBR, 2026-08-19)

Status: **DRAFT — becomes FROZEN upon owner adoption.** This document
preregisters a CAPTURE stream only. The evaluation gets its own frozen
preregistration later, before the first evaluation look (section 6).

## 1. Why capture-first

The owner's strategy Step 1 selects stocks by analyst "Strong Buy"
consensus. QuantConnect has NO point-in-time analyst-ratings dataset
(feasibility probe 2026-08-19: Morningstar fundamentals carry no
ratings; Benzinga on QC is news only; the only recommendations dataset
tracks CNBC personalities). Today's consensus applied to historical
prices is look-ahead — untestable honestly. The only clean path is
prospective: snapshot the consensus NOW, monthly, with hashes and
timestamps, and let point-in-time evidence accumulate by construction.
This is the same reasoning that closed Stage 2 PEAD, applied
productively instead of terminally.

## 2. Relation to closed programs

Ranking stocks by a NEW data source (live analyst consensus) with a
FRESH preregistration and a NEW owner decision is exactly what the
A-002 closure permits. The owner's adoption of this document is that
decision for the CAPTURE stage only; no evaluation, ranking-quality
statistic, or trading rule is authorized by it.

## 3. Frozen capture specification

| Item | Value |
|---|---|
| Universe | The NASDAQ-100 constituent list as of the registration date, frozen and recorded in the stream config (aligns with the owner's beat-NASDAQ goal). Constituent changes after registration do NOT alter the list; departures are captured as unavailable and disclosed. |
| Fields per ticker | Analyst recommendation counts by bucket (strongBuy / buy / hold / sell / strongSell) and the count total, as reported by the provider at capture time |
| Provider | yfinance recommendations summary (exploratory-grade, marked `point_in_time_data=false` for its own history; the SNAPSHOTS are point-in-time by construction because capture time = knowledge time) |
| Cadence | Monthly: first weekday of each calendar month, 17:15 ET |
| Storage | Append-only JSONL under the operational clone's data tree, one record per (capture_date, ticker), canonical JSON, per-capture-file SHA-256 recorded in a manifest; never committed to the public repo (counts are not market data, but the no-clutter and provenance rules both favor machine-local artifacts with hashes in the record) |
| Failures | A ticker whose fetch fails is recorded as `available=false` with the error class — never silently dropped, never retried into a different-day snapshot |
| Scheduler | Windows scheduled task, **Interactive logon** (S4U is dead on this host), installed with first-firing verification — registration alone is never trusted |

## 4. What the capture runtime is NOT

Per the ML-LR-6 anti-generic-adapter precedent this is a task-specific
capture script, not an extension of the defensive-carry overlay
runtime, whose contracts (carry weights, band state) do not describe
this task. Zero order, proposal, or promotion authority; failure of
this stream must not affect reconciliation or any operational task.

## 5. Milestones

- SBR-1: capture script + tests (fetch mocking, refusal paths, hash
  and manifest behavior) + scheduled-task installer. One branch,
  independent review, owner-present install.
- SBR-2 (later, separate): evaluation preregistration — frozen only
  after at least **12 monthly snapshots** exist, and BEFORE any
  ranking-quality statistic is computed from them. Until then, nobody
  looks: no correlations, no sorting by subsequent returns, no
  "just checking" queries. Each snapshot is data, not a result.

## 6. Look discipline

The capture files may be READ for operational integrity (counts,
availability, hash verification) at any time. Any computation that
joins a snapshot to subsequent PRICES is an evaluation look and is
forbidden until SBR-2's preregistration is frozen. This sentence is
the contract the SBR-2 reviewer enforces.

## 7. Adoption

Owner adoption line (date + wording) to be recorded here; the capture
spec above freezes at that moment. SBR-1 may then be scheduled.
