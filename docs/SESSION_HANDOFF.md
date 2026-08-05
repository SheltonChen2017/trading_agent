# Development session handoff

Prepared: 2026-08-05 (evening), after GR-4 merged as PR #154 and GR-7 was
split into sub-milestones. GR-7a (annual tax reporting) is implemented and
pushed for review. All work is DEV-SIDE ONLY: nothing was deployed to the
frozen operational checkout, and `paper-epoch-001` is unaffected.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Standing state: THE EPOCH (day 1 complete, do not disturb)

`paper-epoch-001` ACTIVE since 2026-08-05T18:27Z on frozen commit
`8a2233c` (lineage hash `71d228d9...a9ba2`; strategy
owner-directed-paper-policy 1.0.0; model_id `no-ml-model`; approved
mandate `693799c0...9487`). All five drills passed in-epoch.

**Session 1 of 60 is recorded.** Today's observation was captured manually
at 14:42 PT (market closed 13:00 PT; the scheduled 16:30 run would
otherwise have been lost if the machine were shut down first) — the books
reconciled exactly, cash and all seven positions. Epoch-window orders:
1 of 30. Open alerts: 0.

Standing rules: the operational checkout stays on `8a2233c` until
`paper-epoch-close`; the four Interactive-logon tasks run there; the owner
trades only via `C:\git\launch_trading_app.ps1`; never deploy development
commits (including this branch) to the operational checkout mid-epoch.

**Daily habit that matters:** either leave the machine on past 16:30
local, or ask Claude to capture the observation after the close. That is
the only recurring obligation of the 60 sessions.

**Known timing note (not a defect, do not change mid-epoch):** the
observation task fires at 16:30 *local* (Pacific) = 19:30 ET. The
installer default assumes an Eastern-time host where that is 30 minutes
post-close. Harmless here (the close is long final), but if this host ever
moves east of Eastern the default would fire BEFORE the close and must be
revisited.

## 2. Merged this session

PR #154 (`codex/review-gr4-data-honesty-20260805`, second parent
`dfc26cd`) closed the GR-4 round: implementation + Codex's ten GR4REV
corrections + Claude's counter-review (all ten independently verified,
three re-proven red with fresh probes, plus CRGR4-001 closing the third
member of the delegated-`bool()` laundering family in the GR-5 alert
self-test check). `main` is `376175e`; branches deleted local and remote.

## 3. GR-7 split into sub-milestones (decision recorded in the action plan)

The archived plan's §12 lists five items — several branches of work — so
GR-7 is split. The archived plan remains authoritative per item.

| # | Item | State |
|---|---|---|
| GR-7a | Annual tax reporting export | **implemented this session, awaiting review** |
| GR-7b | Idle-cash / mandate reporting | open (small) |
| GR-7c | Performance attribution | open |
| GR-7d | Rebalance-to-target proposals + allocation-service fold-in | **BLOCKED ON AN OWNER DECISION** |

**GR-7d is blocked on a decision, not on code.** The archived plan asserts
"the mandate already defines targets". It does not: the mandate defines
*risk-shape* targets (volatility band, drawdown, time-under-water, capture
ratios) and the policy defines *caps* (max position 5%, max exposure 50%,
min cash 10%, max leveraged ETF 20%). A cap is not a target — curing a cap
breach is what today's risk-reduction engine already does. Generating
rebalance proposals requires the owner to define what the target portfolio
IS (explicit weights, or a rule deriving them). Inventing one would be
inventing an investment policy and asserting an allocation claim with no
evidence behind it. The allocation design's own §6 lists the same
unresolved decisions (candidate universe, sizing shape, sell-leg support).

Also found while scoping: the archived plan's "tax-aware sell preview"
item is **already substantially shipped** — `assistant/proposals.py`
surfaces `tax_lot_advisory` (lot-level realized-gain consequences) on
risk-reduction proposals. GR-7a therefore did not re-implement it.

## 4. GR-7a — annual tax reporting (this branch)

Branch `user/claude/gr-7a-tax-reporting-20260805`, based on `376175e`.

- **`assistant/tax_reporting.py` (new)** — a REPORTING layer only. Every
  number comes from `assistant/tax_lots.py`'s already-tested machinery
  (lot selection, holding-period classification, wash-sale flagging)
  replayed over journal fills + journal-confirmed corporate actions, via
  the same `fills_with_confirmed_splits()` construction proposals use.
  Nothing re-derives a basis, a holding period, or a wash sale.
  - `build_annual_tax_report(store, year, *, portfolio=None, now=None)`
  - `render_tax_report_csv()` / `render_tax_report_json()`
  - Money is Decimal end to end; `realized_pnl` is recomputed from the
    exact decimal basis/proceeds (not converted from the float), so rows
    sum to totals with zero drift. Exported text uses the project's
    canonical `decimal_text`.
- **Three honesty rules, each test-pinned:**
  1. **Coverage lives in the artifact.** Complete / incomplete /
     unverified is embedded in the CSV's *first lines* and in the JSON —
     an accountant reads the file, not the terminal. `complete` is True
     only when coverage was VERIFIED complete; unverified is not
     completeness, it is an unanswered question.
  2. **Wash sales are flags, never adjustments.** Basis is never modified;
     the disclaimer states the cross-account rule this project cannot see.
  3. **Tax years are market-local calendar years.** A sale at
     2026-01-01T02:00Z is 2025-12-31 21:00 ET and belongs to tax year
     2025. UTC bucketing would silently move late-December sales.
  - An unbuildable ledger raises `TaxReportError` rather than emitting a
    confident-looking empty report.
- **CLI `tax-report --year N [--format csv|json] [--output PATH]
  [--no-coverage-check]`** — read-only; exits 2 when coverage is
  incomplete or unverified while STILL writing the artifact; a broker
  outage during the coverage check degrades the claim instead of crashing
  the export. Verified against the real operator database (read-only):
  0 realized sales in 2026 so far, coverage-unverified path exercised.
- **UI: new "Reports" page** (tenth page, between Backtest and
  Operations) — deliberately the shared home for GR-7b/GR-7c too rather
  than each inventing a surface. On-demand build (opening the page
  computes nothing), coverage banner, totals + per-lot tables, CSV/JSON
  downloads, no action-shaped controls.
- Docs: README (ten pages, Reports page, CLI section) and the action plan
  (split table + the GR-7d blocked rationale).

## 5. Validation (development machine, Python 3.13, exact final tree)

    new: tests/test_tax_reporting.py 26 passed
    new: tests/test_ui_reports_page.py 6 passed
    adjacent (tax lots, corporate actions, UI feature controls,
        import boundary): 112 passed
    full suite: see the commit message for the exact final count
    compileall + git diff --check: clean

Reverse mutations (applied, shown red, restored):

1. Treating UNVERIFIED coverage as complete → caught by FOUR tests
   spanning the report, the CSV artifact, and both CLI paths.
2. Bucketing the tax year in UTC instead of market-local time → caught by
   the unit rule and the New-Year-boundary integration test.

Known limits, stated for the reviewer: fees/commissions are excluded
unless journaled (stated in the artifact's disclaimers); the report covers
realized sales only (open-lot unrealized reporting is out of scope);
`tax_lots.py`'s FIFO default is used and reported, not made selectable;
and the CSV is a reconciliation aid, not a 1099-B substitute.

## 6. What is next

1. Codex review of this branch, then the owner's merge decision. Under
   model 2 the merge deploys nowhere; the operational checkout stays
   frozen at `8a2233c`.
2. Then GR-7b (idle-cash/mandate reporting) or GR-7c (attribution) —
   both land on the new Reports page. GR-6 recovery/portability is also
   open. **GR-7d needs the owner's target-portfolio decision first.**
3. Owner decisions available anytime: committee experiment-gate removal
   (all ADR prerequisites met); ML shadow tasks for a later epoch (ML
   tables are currently all zero, by design).

## 7. Non-negotiable boundaries

- Paper trading only; the epoch binds one host/commit/database/account;
  never deploy dev commits to the operational checkout mid-epoch.
- Reporting surfaces are read-only: they may not propose, approve, size,
  submit, or dismiss anything.
- An incomplete or unverified financial report must say so in the
  artifact; never export partial data as though it were complete.
- Wash-sale output stays advisory; basis is never adjusted here.
- ML/LLM output stays advisory/observational; never commit credentials or
  operator data.

## 8. Machine-local state

Operational checkout frozen at `8a2233c`; venv task interpreter;
launcher + elevated wrapper generated from the reviewed bootstrap; four
tasks live (OperationsCycle green every 10 minutes; OrderMonitor and
Watchdog running as visible console windows — minimize, never close; the
Alpaca websocket flaps on the corporate network and falls back to polling
by design). The owner's Streamlit app runs detached via the launcher so no
agent shell can terminate it. The operator database was not mutated by
this session's development work (all tests used the pytest-isolated
database; the only touch was the read-only `tax-report` CLI run and the
epoch observation capture).
