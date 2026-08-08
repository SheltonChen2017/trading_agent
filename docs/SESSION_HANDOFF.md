# Development session handoff

Prepared: 2026-08-07, after a full-codebase sweep on
`user/claude/full-codebase-sweep-20260807`.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff
**and is therefore the wrong place for anything durable.**

> **Read `docs/OPERATIONAL_FACTS.md` first.** Standing owner decisions,
> machine-local operational knowledge, and engineering watch items live
> there because this file is rewritten every round. Do not copy them back
> into this file; link to them. Six watch items were added this round.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json`. Operational checkout pinned there.
**Never deploy development commits mid-epoch.** Nothing this round is
deployed.

`paper-epoch-001` is CLOSED (plumbing shakedown only; do not cite).

## 2. Latest outcome — full-codebase sweep; 2 of 4 P2s fixed

Owner asked for a whole-repository scan for flaws, defects, bugs, orphans
and inconsistencies, then for the two highest-consequence defects to be
fixed. Branch `user/claude/full-codebase-sweep-20260807`.

Ledger: `docs/REVIEW_2026-08-07_FULL_CODEBASE_SWEEP.md` (FCS-001..017).
**0 P0, 0 P1, 4 P2, 13 P3.** All four P2s reproduced.
**FCS-001 and FCS-016 are FIXED with red/green + reverse-mutation evidence.
FCS-002, FCS-003 and all thirteen P3s are recorded but UNFIXED**, and no
independent reviewer has confirmed the two fixes.

| ID | Pri | Summary |
|---|---|---|
| FCS-001 | P2 | **FIXED.** `strategy_proposals.py` divided by `current_price` unguarded (4 sites); the UI's narrow `except` let the resulting `ZeroDivisionError` **suppress already-computed risk-reduction sells**. Both legs' prices are now validated (new `StrategyPositionDataError`, a `StrategyMarketDataError` subclass so existing callers already catch it) and the UI handler is widened to `Exception`, matching the CLI. Severity correction found while fixing: NaN is NOT reachable (the snapshot builder rejects non-finite prices on both production paths); **zero/negative** is. |
| FCS-016 | P2 | **FIXED.** `tax_lots.is_long_term` compared **timestamps** where its own docstring and the IRS rule are **date**-based: a sale on the one-year anniversary at a later time of day than the purchase is classified long-term when it is short-term. Understates tax in the accountant-facing GR-7a export. Both existing boundary tests use the same time-of-day for buy and sell — the one case the bug cannot fail — which is why three rounds missed it. Now compares market-local dates from one shared `_one_year_on()`; `MARKET_TIMEZONE` is defined once in `tax_lots` and imported by `tax_reporting`. |
| FCS-002 | P2 | `earnings_experiments.calibration_error` divides scored-pair numerator by raw `len(actual)`; the metric improves as coverage worsens (0.1500 → 0.0150 measured). FPS-004 class, same module. |
| FCS-003 | P2 | `research/quantconnect._assert_allowed` accepts percent-encoded traversal (`backtests/%2e%2e/data/read`). Licence-boundary control; module dormant. |
| FCS-004..015 | P3 | cash-report headroom ignores pending buys; 4th bare `Decimal(str())`; dead `worst_case_fill_price`; undocumented 4th risk-check scatter point; mixed pct/fraction units on the gate; telemetry decision≡arrival price; stale doc line counts; Python 3.14 vs 3.12/3.13 CI; dead `_non_negative_int` + unbounded `list --limit -1`; non-atomic tax-report write; 6 orphan symbols; `save_policy` temp-name race. |

Prior ledgers verified genuinely closed: all four 2026-07-30 P1s are fixed
in code (checked, not assumed).

## 3. Validation

- Base tree `011ae5c` before any change: **3015 passed / 0 failed / 0 skipped
  / 25 warnings** (257s).
- **Exact final tree: 3041 passed / 0 failed / 0 skipped / 25 warnings**
  (352s). The +26 is exactly the tests the two fixes added (18 in
  `test_tax_lots.py`, 8 in `test_strategy_proposals.py`); no pre-existing test
  changed its result.
- `compileall` clean; `git diff --check` clean.
- Reverse mutations, applied in the fixed code's own location and restored:
  FCS-016 → **8 fail** (and both ORIGINAL boundary tests still passed, which
  is their insensitivity made executable); FCS-001 → **7 fail**.
- Run on **Python 3.14.6**; CI covers only 3.12/3.13 (FCS-011).
- FPS-003 did not reproduce. It stays open — a green run is not evidence.

## 4. Coverage honesty — this sweep was NOT exhaustive

All 199 production modules received mechanical AST coverage (unguarded
division, `except: pass`, SQL interpolation, non-atomic artifact writes,
naive datetimes, mutable defaults, `Decimal(str())`, `or 0`, full orphan
graph). Only ~35 were read line by line; ~45K of 62K lines were not.

**Not read at line level:** most of `ml/`, most of `scripts/`, the bulk of
`storage.py`, `personal_assistant_ui.py`, `backtest/engine.py`,
`portfolio_ledger`, `paper_evidence`, `tax_reporting`,
`operations`, `assistant/llm/*`, `signals/`, `strategies/`. See §3 of the
review for the full table. Every P2 was found by a scan flagging candidates
**plus** a read of the flagged site beside its correct sibling; that pairing
has not been applied to the packages above.

## 5. What is next

1. **Independent review of the two fixes** (FCS-001, FCS-016). Neither has
   been reviewed by anyone but their author. Note FCS-016 changes a value in
   an accountant-facing export, so a previously generated tax report may
   disagree with a regenerated one — that is the fix working, but the owner
   should know before regenerating anything already sent.
2. **FCS-002**, then **FCS-003**, then **FCS-017**. FCS-005 should become the
   AST lint `OPERATIONAL_FACTS` §3 has now been triggered into requiring.
3. Continue the sweep over the packages listed in §4.
4. Owner sets QC credentials and runs one live `authenticate()` (watch CQC-001).
5. Owner decision: news allowlist scope for holdings vs UNIVERSE/known.
6. **GR-6** off-machine backup is **blocked on this host** (owner, 2026-08-07):
   corporate machine, no uploads permitted. Only a physical medium would
   qualify. See `docs/OPERATIONAL_FACTS.md` §2. Do not re-propose OneDrive.
7. Roadmap unchanged: remaining GR-6 items needing no off-machine copy, or
   the GR-7d owner decision (rebalance targets).

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
