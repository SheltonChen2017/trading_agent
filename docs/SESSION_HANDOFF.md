# Development session handoff

Prepared: 2026-08-07, after a full-codebase sweep and the fix of every
finding it produced, on `user/claude/full-codebase-sweep-20260807`.

Audience: Codex, Claude Code, Grok, and the repository owner after a
computer, model, or session change. This file completely replaces the prior
handoff **and is therefore the wrong place for anything durable.**

> **Read `docs/OPERATIONAL_FACTS.md` first.** Standing owner decisions,
> machine-local operational knowledge, and engineering watch items live
> there because this file is rewritten every round. Do not copy them back
> into this file; link to them. **Six watch items were added this round** —
> they are the generalizable lessons, and they matter more than any
> individual fix.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json`. Operational checkout pinned there.
**Never deploy development commits mid-epoch.** Nothing this round is
deployed; the operational checkout is untouched.

`paper-epoch-001` is CLOSED (plumbing shakedown only; do not cite).

## 2. What happened this round

The owner asked for a whole-repository scan for flaws, defects, bugs,
orphans and inconsistencies, then for every defect found to be fixed.

Branch: `user/claude/full-codebase-sweep-20260807` — local only, not pushed.
Ledger: `docs/REVIEW_2026-08-07_FULL_CODEBASE_SWEEP.md`; findings in §2,
**corrections and their verification in §2b**, honest coverage in §3.

**0 P0 · 0 P1 · 4 P2 · 13 P3 · all 17 fixed · none independently reviewed.**

### The four P2s

| ID | What was wrong | Fix |
|---|---|---|
| FCS-001 | `strategy_proposals` divided by `current_price` unguarded at four sites, while the sibling `proposals.py` has guarded that exact idiom since 2026-07-29. The UI caught only two narrow exception types, so the `ZeroDivisionError` escaped and **suppressed risk-reduction sells already computed in the same handler**. | Both legs validated → new `StrategyPositionDataError`, a `StrategyMarketDataError` subclass so existing callers already catch it. UI handler widened to `Exception`, matching the CLI. |
| FCS-016 | `tax_lots.is_long_term` compared **timestamps** where its own docstring and the IRS rule are **date**-based, and judged in UTC while `tax_reporting` prints and buckets in Eastern. An exported row could read `acquired 2025-03-10, sold 2026-03-10, LONG-TERM`. | One `_one_year_on()` comparing market-local dates; `MARKET_TIMEZONE` defined once in `tax_lots` and imported by `tax_reporting`. |
| FCS-002 | `calibration_error` divided a finite-pair numerator by the raw row count, so the reported error improved as coverage worsened (0.1500 → 0.0150 measured). | All five classification metrics scored on the same finite pairs; both counts published. Also closed a second half found while fixing: `NaN >= threshold` scored a declined prediction as a confident negative. |
| FCS-003 | The QuantConnect allowlist accepted percent-encoded traversal, one day after being hardened against the literal form. | Double percent-decode before the check, plus outright rejection of `%`. |

### The thirteen P3s

`FCS-004` headroom nets out committed capital · `FCS-005` AST lint banning
bare `Decimal(str(...))` — the guard `OPERATIONAL_FACTS` §3 demanded after a
fourth occurrence · `FCS-006` dead float `worst_case_fill_price` removed,
rationale relocated and corrected · `FCS-007` fourth risk-check scatter point
documented · `FCS-008` the gate's mixed pct/fraction units documented at the
signature and pinned · `FCS-009` telemetry states that decision and arrival
price are one observation · `FCS-010` stale doc line counts · `FCS-011` CI
gains Python 3.14 · `FCS-012` unwired validator applied; `list --limit -1` no
longer unbounded · `FCS-013` atomic tax-report write · `FCS-014` orphans ·
`FCS-015` `save_policy` temp-name race · `FCS-017` four freshness checks no
longer read a future timestamp as fresh.

### Two corrections I made to my own findings

Recorded because a review that only sharpens other people's work is not being
run honestly.

1. **FCS-001's severity was overstated.** The first write-up claimed NaN was
   reachable. It is not — `build_portfolio_snapshot` rejects non-finite
   prices and the Alpaca builder delegates to it; the reproduction had
   hand-built a `PortfolioPosition` and bypassed that boundary. **Zero and
   negative** are the reachable trigger.
2. **FCS-016's first fix guidance was wrong.** "Compare `.date()` values" was
   tested and still returns long-term on the UTC/Eastern case. The comparison
   has to use market-local dates.

## 3. Validation (exact final tree)

- Base `011ae5c` before any change: **3015 passed / 0 failed / 0 skipped /
  25 warnings**.
- **Final tree: 3085 passed / 0 failed / 0 skipped / 25 warnings** (347s).
  The +70 over baseline is entirely new regression tests; **no pre-existing
  test changed its result**, which is the claim that matters.
- `compileall` clean; `git diff --check` clean.
- Reverse mutations, each applied in the fixed code's own location and then
  restored: FCS-016 → **8 fail**, and **both original boundary tests still
  passed**, which is their insensitivity made executable; FCS-001 → **7
  fail**; FCS-002 → **1 fail**; FCS-003 → **5 fail** with both layers
  removed, **1** with only the `%` rule removed, **0 with only the decoding
  removed** — recorded because it shows which layer carries which input;
  FCS-004 → **1 fail**.
- Run on **Python 3.14.6**. CI now covers 3.12/3.13/3.14 (FCS-011), but the
  3.14 job has never executed — it will on first push.
- FPS-003 did not reproduce. It stays open — a green run is not evidence.

## 4. Coverage honesty — the sweep was NOT exhaustive

All 199 production modules received mechanical AST coverage: unguarded
division, `except: pass`, SQL interpolation, non-atomic artifact writes,
naive datetimes, mutable defaults, `Decimal(str())`, `or 0`, freshness
bounds, the FPS-004 count-vs-denominator class, and a full orphan graph.

**Only ~35 modules were read line by line; roughly 44K of 62K lines were
not.** Not read: most of `ml/`, most of `scripts/`, the bulk of
`storage.py`, `personal_assistant_ui.py`, `backtest/engine.py`,
`portfolio_ledger`, `paper_evidence`, `tax_reporting` beyond its row and
coverage layer, `operations` beyond its freshness checks, `assistant/llm/*`,
`signals/`, `strategies/`.

Every P2 was found by a scan flagging candidates **plus** reading the flagged
site beside its correct sibling. That pairing has not reached the packages
above, so "all findings fixed" means every finding *this sweep produced* —
not that the codebase is clean.

## 5. What is next

1. **Independent review of all 17 fixes.** None has been reviewed by anyone
   but its author, and this round produced two self-corrections.
2. **FCS-016 changes a value in an accountant-facing export.** A tax report
   generated before today may disagree with a regenerated one for any sale on
   a one-year anniversary — previously long-term, correctly short-term, so
   the earlier file understated tax. If one has already been sent, say so.
3. Continue the sweep over the packages in §4, using the scan-then-read
   pairing that produced every P2.
4. Owner sets QC credentials and runs one live `authenticate()` (watch
   CQC-001 in `OPERATIONAL_FACTS`).
5. Owner decision: news allowlist scope for holdings vs UNIVERSE/known.
6. **GR-6** off-machine backup is **blocked on this host** (owner,
   2026-08-07): corporate machine, no uploads permitted. Only a physical
   medium qualifies. See `docs/OPERATIONAL_FACTS.md` §2. Do not re-propose
   OneDrive.
7. Roadmap otherwise unchanged: remaining GR-6 items needing no off-machine
   copy, or the GR-7d owner decision (rebalance targets).

## 6. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Reports/CLI reporting must not write provider-fetch or execution evidence.
- Incomplete/insufficient samples must say so in the artifact.
- Selection residual is not a skill claim.
- **QuantConnect raw market data must never enter this repository.** Results
  only; the endpoint allowlist in `research/quantconnect.py` is the
  enforcement, and weakening it breaks their licence (see FCS-003).
- Snapshot `total_equity` is post-flow; subtract `net_external_flow` before
  any `Observation.value_before_flow` mapping.
- AI refusal reasons must be fixed labels — never withheld model prose or
  invented figures.
- **An optional feature's failure must never suppress a risk-reducing
  proposal** (FCS-001).
- **A metric's denominator must be the observations it actually scored**
  (FPS-004, FCS-002).
