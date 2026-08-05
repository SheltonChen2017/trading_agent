# Development session handoff

Prepared: 2026-08-05 (afternoon), after independent Codex review of GR-4
including late audit follow-ups. GR-4 data-layer honesty is complete after
correction on `codex/review-gr4-data-honesty-20260805`. All work is
DEV-SIDE ONLY: nothing was deployed to the frozen operational checkout,
and `paper-epoch-001` is unaffected.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Standing state: THE EPOCH (unchanged, do not disturb)

`paper-epoch-001` is ACTIVE since 2026-08-05T18:27Z on frozen commit
`8a2233c` (lineage hash `71d228d9...a9ba2`; strategy
owner-directed-paper-policy 1.0.0; no-ml-model; approved mandate
`693799c0...9487`). All five drills passed and are recorded in-epoch. The
operational checkout `C:\git\trading_agent_operational` stays on `8a2233c`
until `paper-epoch-close`; the four Interactive-logon tasks run there; the
owner trades only via `C:\git\launch_trading_app.ps1`. Never deploy
development commits (including this branch) to the operational checkout
mid-epoch.

## 2. GR-4 data-layer honesty — complete after independent review

Implementation branch: `user/claude/gr-4-data-honesty-20260805`
(`3fa4229`, `eb33aa9`, `a4f09e3` on base `86c5f77`).
Review branch: `codex/review-gr4-data-honesty-20260805`.
First corrections commit: `7eef1c5`.
Follow-up corrections close GR4REV-008..010 on this tip.

Completed behavior after review correction:

- Declared `PriceSource` boundary; yfinance lineage is honestly `False`.
- Append-only `data_provider_fetches` evidence; all-empty and
  unrequested-only responses are failures.
- Failure-streak alert after three consecutive provider failures.
- NYSE-calendar freshness: latest completed session required; current-date
  bars pass only during a real open session.
- Platform readiness threads its pinned `now` into data-integrity freshness.
- DecisionPacket freshness fields and Briefing `DATA DEGRADED` banner,
  including short histories that cannot compute trend.
- Strategy proposals refuse missing/stale bars; risk-reduction proposals
  remain available.
- New proposals bind exact proposal-time shares; pre-submit validation
  refuses split-shaped forward/reverse share drift before broker preflight.
- Import-boundary-safe helper lives in `assistant/share_reconciliation.py`.

Confirmed review ledger: GR4REV-001..010 (all P2, all resolved). Full
dispositions are in `docs/REVIEW_2026-08-05_GR4_DATA_HONESTY.md`.

Final validation on the exact reviewed tree (Windows, Python 3.13.14):

- Follow-up focused suite: **91 passed**.
- Exact final tree: **2,798 passed / 1 skipped / 25 warnings** in 544.22s.
- `compileall` and `git diff --check` clean.

Quality score for the submitted Claude GR-4 tree: **6.8/10**.
Quality after independent review corrections: **9.5/10**.

## 3. Owner-dictated exploratory backtest (corrected)

`scripts/run_sharpest_decline_dip_2026_08_05.py` remains exploratory only.
Review refuses underfilled horizons, keeps episode and universe baseline
paired, prints paired diffs/beat rates, reports universe coverage, and
discloses non-PIT adjusted yfinance history. Corrected real-data rerun:

- Episodes: **1,698** full-horizon paired only.
- Grid: mean +8.36%, median +4.78%, positive rate 58.2%, p5 −42.08%.
- Hold: mean +9.12%, median +3.78%, positive rate 56.2%, p5 −43.98%.
- Universe: mean +5.04%, median +5.40%, positive rate 74.7%.
- Coverage: min 93 / median 102 / max 103 of 104 requested tickers.
- Paired: grid−hold mean −0.76%, median 0.00%; hold−universe median
  −1.39%; grid−universe median −0.30%.
- Paired beat rates: P(hold>universe) 47.2%; P(grid>universe) 49.1%.

Same-series positive rates are not beat rates. No significance, no edge
claim, no authority. Survivorship-biased universe; `point_in_time_data=false`.

## 4. What is next

1. Owner merge decision for the reviewed GR-4 branch. Under model 2 the
   merge deploys nowhere; the operational checkout stays frozen at
   `8a2233c`.
2. Next action-plan items after GR-4: GR-7 product completeness (fold in
   the allocation-service design), with GR-6 recovery/portability also
   open. Owner decisions available: committee experiment-gate removal; ML
   shadow tasks for a later epoch.
3. The epoch clock runs by itself on the operational host.

## 5. Non-negotiable boundaries

- Paper trading only; the epoch binds one host/commit/database/account;
  never deploy dev commits to the operational checkout mid-epoch.
- Never synthesize a missing price; refuse or visibly degrade instead.
- A conservative safeguard must not obstruct risk reduction — pinned by
  the stale-bars test.
- Exploratory backtest results are never evidence and never authorize
  anything.
- ML/LLM output stays advisory/observational; never commit credentials or
  operator data.

## 6. Machine-local state

Unchanged from the epoch handoff: operational checkout frozen at
`8a2233c`; venv task interpreter; launcher + elevated wrapper regenerated
from the reviewed bootstrap; four tasks live (OrderMonitor/Watchdog
running with the corporate-network websocket flap falling back to
polling). The owner's app runs via the launcher. The operator database
was untouched by this session's development work (all tests used the
pytest-isolated database).
