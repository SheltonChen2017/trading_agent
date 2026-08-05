# Development session handoff

Prepared: 2026-08-05 (afternoon), first development session after
`paper-epoch-001` went active. GR-4 data-layer honesty is implemented and
pushed for review, plus one owner-dictated exploratory backtest with a
frozen spec. All work is DEV-SIDE ONLY: nothing was deployed to the frozen
operational checkout, and the epoch is unaffected.

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

## 2. GR-4 data-layer honesty — implemented, awaiting review

Branch `user/claude/gr-4-data-honesty-20260805` (based on `86c5f77`,
post PR #153). Contract: archived plan §9 plus GR-0's requirement that
data_integrity derive from authenticated records with no assertion escape.

- **`data/price_source.py` (new, pure):** `PriceSource` protocol with a
  MANDATORY `provides_point_in_time_lineage` declaration (yfinance
  honestly False, mirroring ml/availability.py); `ProviderFetchRecord`
  where an all-empty response is a FAILED fetch ("provider returned no
  usable data"), never "zero matching tickers", and error text preserves
  only the exception type (no detail leakage); NYSE-calendar bar
  freshness: fresh = bars reach the latest COMPLETED session, an
  in-progress session's partial bar passes, and a bar beyond today is
  refused as future-dated (fail-closed both directions). The staleness-SLA
  table deliberately omits "quote": order-time quote freshness stays owned
  by the execution gate/policy (single-authority rule).
- **`assistant/data_integrity.py` (new):** `fetch_daily_bars_recorded()`
  records every fetch in the append-only `data_provider_fetches` table
  (schema addition, idempotent CREATE) and raises a deduplicated CRITICAL
  operational alert after PROVIDER_ALERT_FAILURE_STREAK=3 consecutive
  failures; data returns exactly as fetched (never synthesized/filled).
  `build_data_layer_evidence()` derives GR-0's three checks
  (price_freshness / provider_health / adjustment_honesty) from those
  records; zero records blocks everything.
- **`assistant/platform_readiness.py`:** `build_data_integrity(store)`
  now derives from evidence; `None` stays blocked with an explicit
  reason; any non-store argument (e.g. the old `True` assertion) raises
  TypeError — the pre-existing escape-hatch test passes UNCHANGED.
- **Degradation surfaces:** `build_decision_packet(..., store=None)`
  fetches the regime through the recorded path when a store is supplied
  and appends a `"DATA DEGRADED:"`-prefixed warning on stale bars (the
  prefix is the contract); the Briefing renders those as a dedicated
  st.error banner (the plan's definition of done); data_freshness gains
  market_bars_expected_session/market_bars_fresh. CLI `_packet()` gained
  a store parameter and every store-bearing call site passes it.
- **Stale bars block only their dependents:**
  `StaleMarketDataError` in strategy_proposals refuses to size a
  leveraged-pair rebalance from bars missing the latest completed
  session (raised loudly; UI catches per-pair alongside
  MissingResearchDependencyError; CLI already catches broadly).
  Risk-reduction proposals never consult bars and are untouched — the
  plan's risk-reduction guarantee is pinned by test.
- **Split detection:** `detect_split_like_share_mismatch()` in
  corporate_actions classifies a share-count mismatch as split-shaped by
  near-integer ratio (never a price heuristic; pure; confirming a split
  remains a journal action), and `reconcile_snapshot()` annotates
  position mismatches with `suspected_split` while STILL counting them
  as mismatches (fail-closed). Deferred by explicit scope decision:
  wiring a snapshot-shares field into proposals + a registry gate check
  for submit-time split refusal — recorded here so review can judge the
  boundary.
- **Test-harness ripples:** two existing tests stubbed `_packet` with the
  old signature and were updated to accept the `store` kwarg
  (test_committee_cli, test_alert_delivery) — stub-shape updates only, no
  expectation changed.

Validation (exact final tree): new suite tests/test_data_integrity.py
28 passed; adjacent focused set (platform readiness, strategy proposals,
context builder, ledger, import boundary, schema verification)
150 passed; full suite **2,785 passed / 1 skipped / 25 warnings** in
439.80s; compileall and `git diff --check` clean. Reverse mutations shown
red then restored green: (1) laundering an all-empty response into a
success — caught by the record test plus streak tests; (2) the stale-bar
rule silently passing — caught by FOUR tests spanning the unit rule, the
GR-0 adapter, the briefing banner, and the strategy-proposal refusal.

## 3. Owner-dictated exploratory backtest (separate commit, frozen spec)

`scripts/run_sharpest_decline_dip_2026_08_05.py` — the owner's "LLM scans
for the sharpest daily decline, buy the dip, sell 5% per +5% rise"
strategy, spec FROZEN before results (deterministic worst-1-day-return
proxy for the LLM scan; $10k next-open entries; 5%-trim ratchet; 63-session
cap flagged as a project addition; slippage per leg; two frozen baselines).
Measured outcome (1,760 overlapping episodes, exploratory only, no
significance claimed, survivorship-biased universe): the trim grid
SUBTRACTS value vs holding the same picks (grid-hold mean −0.71%, median
0.00%); the dip-pick's mean premium over the average stock (+8.65% vs
+5.01%) comes with a worse median (+3.68% vs +5.29%), a far worse win rate
(56% vs 76%), and a −41% p5 tail — risk compensation flattered by
survivorship, not evident skill. Reported to the owner with those caveats.

## 4. What is next

1. Codex review of this branch (implementation commit + research-script
   commit + docs commit), then the owner's merge decision. Under model 2
   the merge deploys nowhere; the operational checkout stays frozen.
2. Next action-plan items after GR-4: GR-7 product completeness (fold in
   the allocation-service design), with GR-6 recovery/portability also
   open. Owner decisions available: committee experiment-gate removal; ML
   shadow tasks for a later epoch.
3. The epoch clock runs by itself; first session observation lands at the
   16:30 ET close today.

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
