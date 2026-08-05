# Independent review — GR-4 data-layer honesty — 2026-08-05

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

## 1. Reviewed commits

Base: `86c5f77` (`origin/main`, post PR #153).
Implementation branch tip before review: `a4f09e3`.
Review branch: `codex/review-gr4-data-honesty-20260805`.
Corrections commits: `7eef1c5` plus the follow-up commit(s) recorded below for GR4REV-008..010.

| Commit | Message | Disposition |
|---|---|---|
| `3fa4229` | GR-4: data-layer resilience and honesty | accepted after correction (GR4REV-001..006, GR4REV-008..009) |
| `eb33aa9` | Add the owner-dictated sharpest-decline dip-grid exploratory backtest | accepted after correction (GR4REV-007, GR4REV-010) |
| `a4f09e3` | Record GR-4 implementation state and replace the session handoff | accepted after correction in the cumulative final tree (documentation reconciled by this review) |

No P0 or P1 issue was found. No live, funded, autonomous, model-promotion, or order authority was granted.

## 2. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| GR4REV-001 | P2 | Resolved | `3fa4229` | `data/price_source.py` | Current-date bars on Saturday or pre-open Monday were accepted as fresh because the rule only required `latest_session >= expected`. | `evaluate_bar_freshness("2026-08-08", now=Saturday)` returned `fresh=True`. | Calendar honesty requires a later-than-expected bar to be a real in-progress NYSE session. | Refuse non-session current-date bars with an explicit detail. | Red then green: `test_current_date_bar_is_fresh_only_during_a_real_open_session`. |
| GR4REV-002 | P2 | Resolved | `3fa4229` | `assistant/storage.py`, `data/price_source.py` | Non-boolean lineage/time values could be persisted or recorded as evidence (`"false"` is truthy). | `record_provider_fetch(... point_in_time_lineage="false")` and `build_fetch_record` with naive timestamps succeeded. | Evidence used by readiness must reject assertion-shaped or malformed declarations. | Strict boolean and timezone-aware validation on record construction and storage. | Red then green: `test_fetch_record_rejects_malformed_lineage_and_naive_time`, `test_provider_fetch_storage_rejects_assertion_shaped_lineage`. |
| GR4REV-003 | P2 | Resolved | `3fa4229` | `assistant/platform_readiness.py` | Malformed data-layer `ok` values were coerced with `bool(...)`, so `"false"` made readiness ready. | `build_data_integrity(store)` returned `ready` under a stub returning `"false"`. | Same GR-0 fail-closed rule already applied to operational checks. | Require real booleans/details; otherwise block. | Red then green: `test_platform_readiness_rejects_non_boolean_derived_verdicts`. |
| GR4REV-004 | P2 | Resolved | `3fa4229` | `assistant/context_builder.py` | Stale short histories that could not compute trend never emitted `DATA DEGRADED`, so the Briefing definition of done was incomplete. | Packet with stale 10-bar history had no `DATA DEGRADED` warning. | Plan §9.4 requires a visible degradation banner for stale bars. | Evaluate freshness from observed bar dates even when trend is unavailable. | Red then green: `test_stale_short_history_still_renders_the_degradation_banner`. |
| GR4REV-005 | P2 | Resolved | `3fa4229` | `assistant/strategy_proposals.py` | Missing strategy bars returned `[]`, indistinguishable from "no rebalance needed". | `generate_leveraged_pair_rebalance_proposals(..., market_data={})` returned `[]`. | Plan §9.3 requires refusal of dependent surfaces rather than silent empty success. | Raise `MarketDataUnavailableError`; UI catches the strategy-market-data family. | Red then green: `test_missing_strategy_bars_are_a_visible_refusal`. |
| GR4REV-006 | P2 | Resolved | `3fa4229` | `assistant/strategy_proposals.py`, `assistant/portfolio_analytics.py`, `assistant/execution_kernel/validate.py` | Strategy fetches bypassed recorded provider health, and forward splits escaped F6 because `sell_exceeds_held` only catches fewer shares. | F6 with 10→20 shares submitted; strategy empty-provider path wrote no fetch row. | Plan §9.2 requires split detection between snapshot and submit and recorded provider health on the production read path that sizes trades. | Record strategy fetches when a store is supplied; store proposal-time shares; refuse split-shaped share drift before broker preflight; keep the helper import-boundary-safe. | Red then green: F6 forward-split case, seam freeze, and `test_strategy_provider_failure_is_recorded_before_refusal`. |
| GR4REV-007 | P2 | Resolved | `eb33aa9` | `scripts/run_sharpest_decline_dip_2026_08_05.py` | End-of-sample episodes silently shortened the frozen 63-session horizon and still entered labeled statistics. | `_simulate_episode(..., entry_index near end)` returned `sessions_held=1`. | Research honesty forbids pooling underfilled horizons into a frozen comparison. | Refuse underfilled episodes; reran real-data script; corrected reported counts/metrics. | Red then green: `tests/test_sharpest_decline_dip.py`; rerun reported 1,698 full-horizon episodes. |
| GR4REV-008 | P2 | Resolved | `3fa4229` | `data/price_source.py` | A provider response containing only unrequested tickers was recorded as a successful fetch (`ok=True`). | `build_fetch_record(..., ["AAA"], {"WRONG": bars})` returned `ok=True`. | Provider health/freshness evidence must answer the requested universe. | Count and succeed only on requested tickers; spurious keys cannot launder an empty request. | Red then green: `test_spurious_ticker_response_is_not_a_successful_requested_fetch`. |
| GR4REV-009 | P2 | Resolved | `3fa4229` | `assistant/platform_readiness.py` | `build_platform_readiness(now=...)` stamped `checked_at` from the pinned clock but evaluated bar freshness against wall clock. | Saturday-pinned report could keep Wednesday freshness ready. | The report's clock and freshness SLA must be the same instant. | Thread `now` through `build_data_integrity` into `build_data_layer_evidence`. | Red then green: `test_platform_readiness_threads_pinned_now_into_data_freshness`. |
| GR4REV-010 | P2 | Resolved | `eb33aa9` | `scripts/run_sharpest_decline_dip_2026_08_05.py` | Pick-vs-universe conclusions used unpaired series stats; universe baseline could truncate or desync from episodes; PIT caveat omitted. | Script printed only grid−hold paired diffs; baseline used `min(... len-1)`. | Research comparisons must stay on identical observations and disclose non-PIT adjusted history. | Require paired full-horizon baselines, print hold/grid−universe paired diffs and beat rates, report coverage, label positive-rate vs beat-rate, disclose `point_in_time_data=false`. | Red then green: `tests/test_sharpest_decline_dip.py`; real-data rerun 1,698 paired episodes. |

No open P0–P2 issue remains for the reviewed GR-4 scope. Intentional residuals: research/presentation-only historical fetches outside the DecisionPacket/strategy path are not automatically recorded as operational provider-health evidence; CLI briefing prints `DATA DEGRADED` as ordinary warning text rather than a Streamlit-style banner; uncommon non-integer split ratios stay ordinary share mismatches without a split-shaped hint.

## 3. Compatibility and boundary assessment

Checked against the rest of the app:

- DecisionPacket gained additive freshness fields and warnings only; no existing required schema fields were removed.
- CLI `_packet(..., store=...)` and UI packet loading pass the store so regime fetches are recorded.
- Deterministic risk-reduction proposals remain bar-independent and available under stale bars.
- Quote freshness remains owned by the execution gate/policy; no second quote SLA was introduced.
- Import boundary stays clean: the execution facade uses `assistant.share_reconciliation`, not the heavier corporate-actions presentation module.
- GR-1C call-time DI remains intact: `detect_split_like_share_mismatch` is injected through `ProposalValidationDeps`.
- Active paper epoch on frozen commit `8a2233c` is untouched; this branch is development-side only.

## 4. Quality score

Submitted quality: **6.8/10**.
Corrected quality: **9.5/10**.

The architecture and honesty vocabulary were sound, but fail-open edges around calendar freshness, evidence typing, readiness clock agreement, requested-ticker success, missing-data surfaces, forward-split identity, and unpaired research comparisons had to be closed before GR-4 met its definition of done.

## 5. Validation

Review machine: Windows, Python 3.13.14.

- Red-before-green review run: 9 expected failures.
- Corrected focused/compatibility run: 200 passed, 1 warning.
- Broader GR-4/execution/UI/import compatibility run: 287 passed, 1 warning.
- Corrected exploratory dip-grid real-data rerun: 1,698 full-horizon episodes; grid-hold mean −0.76%, median 0.00%; exploratory only.
- Follow-up focused suite after GR4REV-008..010: 91 passed.
- Exact final tree: **2,798 passed / 1 skipped / 25 warnings** in 544.22s.
- `python -m compileall -q assistant backtest data execution ml risk scripts signals strategies tests baskets.py config.py market_analytics.py` clean.
- `git diff --check` clean.

Tests used scripted providers, temporary databases, and mocked brokers. No test contacted Anthropic, Alpaca, or a funded account. The real-data exploratory script contacted yfinance only.

## 6. Deliberately not claimed complete by this review

- Recording every research/UI historical fetch as operational provider-health evidence.
- Changing quote freshness authority.
- Adding a stale persisted earnings cache/SLA where none exists.
- Deploying GR-4 into the frozen operational checkout mid-epoch.
- Promoting the exploratory dip-grid result to evidence or authority.
