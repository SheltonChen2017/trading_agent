# Full-project review — 2026-08-06

Audience: repository owner, Codex, Claude Code, and future reviewers.

Owner request: "go over the project module by module, find inconsistencies
or bugs, and fix them." First full sweep since
`docs/REVIEW_2026-07-30_FULL_CODEBASE.md` (0 P0 / 4 P1 / 8 P2).

Base: `07781c7` (`main`, post PR #159).
Scope: **378 commits** since the last full review; ~62K lines of production
Python across nine packages, plus the test suite.

## 1. Headline

No P0. No P1. **Two confirmed P2 defects, both fixed** — one in the
corporate-action reader (FPS-001), one in ML slice reporting (FPS-004).
One P3 test-hygiene issue, fixed (FPS-002). One P2 test-reliability issue
**open and characterized but not root-caused** (FPS-003, §4). Several
candidates investigated and classified as false alarms (§5) — recorded so
the next reviewer does not re-derive them.

Both P2s are evidence-integrity defects rather than execution defects:
neither could submit, size, or mis-price an order. Each made a *report*
claim more than the data behind it supported — the first by crashing where
it promised to degrade, the second by printing a sample count the metric
had not actually used.

The codebase is in materially better shape than the commit count suggests.
Repeated adversarial review rounds have left dense, accurate safety
comments, and the sweeps below for whole classes of defect came back empty.

## 2. Issue ledger

| ID | Priority | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| FPS-001 | P2 | **Fixed** | `assistant/corporate_actions.py` | Three sites bypassed `assistant/money.py:to_decimal` and used raw `Decimal(str(...))`. Malformed journal metadata raises `decimal.InvalidOperation`, which is an **`ArithmeticError`, not a `ValueError`** — so it escaped `confirmed_distributions`' `except (ValueError, KeyError)` and `tax_ledger_with_coverage`'s `except (TaxLotError, ValueError, KeyError)`. The module's docstring promises malformed actions are "reported as unavailable rather than reverse-engineered"; instead they surfaced as an uncaught traceback in the two Streamlit callers and the CLI caller. | Use `to_decimal` at all three sites. It normalizes `InvalidOperation` → `ValueError` and additionally rejects NaN/Infinity. For splits, a malformed **or** missing ratio now raises `ValueError` — fail-closed, since silently dropping a split would corrupt every later share count and cost basis. | Reproduced pre-fix (`InvalidOperation` escaped); 12 tests added/passing; reverse mutation reverting all three sites: **4 tests fail**, restored green. |
| FPS-002 | P3 | **Fixed** | `tests/test_ml_experiments.py` | A parametrized case declaring that a `label_version` spec/dataset mismatch must be refused called `pytest.skip("caught earlier by join_for_evaluation")`. The claim is true at the lower layer, but the skip removed assertion of the refusal at **this** boundary and left a permanent "1 skipped" in every validation run — standing ambiguity in a report CLAUDE.md §10 requires to be exact. | Skip removed; the case now asserts the refusal. | Verified by removal: all six parametrized cases pass. Suite skip count 1 → 0. |
| FPS-004 | P2 | **Fixed** | `ml/earnings_experiments.py::_slice_metrics` | The failure-slice report published `event_count = len(group)` beside a metric computed by `brier_score`/`mean_absolute_error`, both of which drop non-finite pairs inside `_finite_pairs`. The count therefore counted rows the metric never scored. A slice the model largely **failed** to predict displays a strong score over its few easy survivors — the number improves as coverage gets worse. Reproduced: a 10-event slice with 7 NaN predictions reports `event_count=10` beside a Brier of 0.0100 computed on 3 events. This is the selective-sample failure CLAUDE.md §6 names, in the exact report used to judge whether a model works in a regime. | Added `ml/evaluation.py::usable_pair_count()` and published `scored_event_count` beside `event_count`, matching the convention the fold summaries (`validation_row_count` / `evaluated_validation_row_count`) and `ml/monitoring_reports.py` already use. | Reproduced pre-fix; 2 tests added; reverse mutation restoring `len(group)`: **1 test fails**, restored green. |
| FPS-003 | P2 | **Open — characterized, not root-caused** | `tests/test_ui_chrome.py::test_app_title_is_trading_assistant` | Failed with a `RuntimeError` during the full-suite baseline on `main` (2875 passed, 1 failed). **Order-dependent**: passes alone, passes with all 46 UI tests together, passes after the credential-mutating broker/CLI modules. Not caused by any change in this review. Impact is on the validation gate itself, not on runtime behavior: a suite that fails intermittently cannot support CLAUDE.md §10's "report exact pass/skip/failure counts". | None yet — see §4 for what was ruled out and the next step. | Reproduction attempt logged; hypotheses disproven rather than assumed. |

## 3. Sweeps that came back clean

Recorded because a negative result from a systematic sweep is evidence, and
re-running them is cheaper than re-deriving what was checked.

| Sweep | Result |
|---|---|
| Mutable default arguments (`=[]`, `={}`, `=set()`) across all production packages | **none** |
| `datetime.utcnow()` / naive-datetime construction | **none** in production code |
| `TODO` / `FIXME` / `XXX` / `HACK` / `NotImplementedError` | **none** in production code |
| `getattr(policy, "field", <default>)` — drifting fallback defaults for policy limits | **none**; policy is a frozen dataclass read directly |
| Binary float in authoritative money arithmetic | **none reachable**; the float columns found (`storage.reserve_execution_budget`, `portfolio_analytics`) are secondary/presentation, with `reserved_notional_text` Decimal as the authority |
| `ml` reachable transitively from execution-capable roots | **0 violations** across 13 roots, following function-local imports |
| `assistant.llm` / `ai_advisor` / `news_summary` reachable transitively from execution-capable roots | **0 violations** — the LLM advisory layer cannot be reached from any order path |

The existing `test_no_execution_capable_module_reaches_ml_transitively` is
**stronger** than the independent walker written for this review: it uses
every module in `assistant`/`execution`/`risk` as a root rather than a
hand-picked list, and fails on unresolved import forms. CLAUDE.md §4's
transitive-closure requirement is satisfied.

## 4. FPS-003: what was ruled out

Left open deliberately rather than guessed at. Disproven hypotheses:

- **`AppTest` default 3-second timeout** — the test already passes
  `default_timeout=60`.
- **Live Alpaca call from the app under test** — `tests/conftest.py`
  clears `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` at collection and
  redirects `TRADING_ASSISTANT_DB` to a temp path, precisely to stop this.
- **Credential leak from `test_alpaca_broker.py`**, which sets those
  variables directly in `os.environ` many times — every site clears them,
  and running
  `test_alpaca_broker.py test_personal_assistant.py test_ui_chrome.py`
  in sequence passes (148 passed).
- **UI-test cross-contamination** — all 46 `test_ui_*` tests pass together.

Not yet ruled out: `st.cache_data`/`cache_resource` global state left by a
non-UI test, and load-related timeout under full-suite contention. The next
step is a full-suite run with the complete traceback captured (the baseline
was piped through `tail`, which discarded it) and, if it reproduces,
bisecting by module.

## 5. Candidates investigated and dismissed

Verified before acting, per CLAUDE.md §9. None required a change.

- **`performance.py:514`** — `factor = (current_price + paid_per_share) / previous_price`
  divides without a zero guard, while the near-identical chain-link in
  `time_weighted_return` (line 209) carefully skips and *counts* zero-start
  periods. Looked like the classic duplicated-rule drift. **False alarm:**
  entry validation at line 446 rejects any non-positive or non-finite
  price, so `previous_price` cannot be zero here.
- **`execution_kernel/validate.py:310`** — `projected_open_orders >= policy.max_open_orders`
  looked like an off-by-one against the `>` used for daily order count.
  **False alarm:** `projected_open_orders` excludes the order being
  validated, so `>=` correctly permits exactly `max_open_orders` open.
- **`revalidate.py:234`** — `except Exception: return None` on the earnings
  lookup skips the blackout check when data is unavailable. **Not a
  defect:** `TradingPolicy.require_earnings_data` is the owner-visible
  control for this, default `false`, deliberate and documented in
  `execution_service.py`'s own history (item 7). See the note in §6.
- **`price_source.evaluate_bar_freshness`** — compares a UTC-derived
  `today_date` against Eastern session dates, the same confusion that
  caused a real bug in `storage.get_execution_budget_usage`. **False
  alarm:** the `in_progress` NYSE-schedule check catches the 20:00–24:00 ET
  window that the fast-path future-date check lets through.
- **`submit.reserve_daily_budget`** — transitions to BLOCKED without
  calling `release_execution_reservation`, unlike its sibling
  `resolve_submission_call`. **Correct as written:**
  `reserve_execution_budget` runs inside `BEGIN IMMEDIATE` and rolls back,
  so there is no reservation row to release.

## 6. `require_earnings_data`: measured, with a design gap

`require_earnings_data` defaults to `false`, so when live earnings-date
data cannot be resolved the blackout check is **silently skipped** for
BUYs. Rather than reason about whether to flip it, the feed was measured
against the account's actual holdings (2026-08-06):

| Ticker | Resolved | Days away |
|---|---|---|
| AAPL | yes | 84 |
| AMZN | yes | 84 |
| AVGO | yes | 27 |
| MSFT | yes | 83 |
| NFLX | yes | 75 |
| **BBB** | **no** | — |
| **NVDL** | **no** | — |

5 of 7. The two failures are **structurally different, and the policy
cannot tell them apart**:

- **NVDL is a leveraged ETF.** It has no earnings event at all. Its
  "unavailable" is correct and permanent.
- **BBB is a small cap** whose fundamentals the provider does not carry.
  Its "unavailable" hides a real earnings event — exactly the case the
  blackout exists for.

`data.event_data.fetch_upcoming_earnings` returns `available=False` for
both, so `require_earnings_data: true` would **permanently block every
buy of NVDL and any other ETF** while correctly blocking BBB. That is a
false positive on an instrument that cannot have the risk, not added
safety.

Recommendation: **leave it `false`** until "no earnings because this is not
a single-name equity" is distinguishable from "earnings exist but are not
visible". Flipping it today would break leveraged-ETF trading — which is
the SOXX/SOXL-style strategy this project has spent the most research
effort on — without protecting anything that a manual approval step does
not already cover. The genuine residual exposure is BBB-like names: real
earnings, invisible to the feed, silently unchecked. Risk-reducing SELLs
are exempt either way.

## 7. Coverage and honesty

This sweep was **class-driven, not line-by-line**: systematic searches for
the failure classes CLAUDE.md enumerates, plus targeted deep reads of the
highest-risk code. Reading all 62K lines was not attempted and is not
claimed.

Second pass (owner asked for the areas the first pass had scoped out):

| Area | What was checked | Result |
|---|---|---|
| `ml/` evaluation + evidence reporting | silent row dropping in every scalar metric; count-vs-metric denominators; fold purge/embargo reporting | **FPS-004 found and fixed**; fold summaries and `monitoring_reports.py` slice reporting already correct |
| `signals/` (incl. the six new signals) | rolling-baseline self-contamination (`.shift(1)` before `.rolling()`), future indexing, cross-sectional vs time-series z-scores | clean — the `scanner.py` fix propagated to `residual.py`; `vol_scaled_momentum` slices are all `[:idx+1]`, no future data |
| `backtest/`, `strategies/` | look-ahead in forward-return construction and fill timing | clean — `shift(-n)` is outcome measurement; `decline_grid` excludes today from its prior window and fills at next open |
| `assistant/storage.py` migrations | idempotency, backward compatibility, transaction boundaries | clean — `PRAGMA table_info` guards, `IF NOT EXISTS`, `DROP INDEX IF EXISTS`; documented rationale per migration |
| `scripts/personal_assistant_ui.py` | silent zero substitution, action-shaped fields in presentation payloads | clean — only two `or 0` defaults, both display-only and unreachable |
| Operator DB spot check | an unexpected `BBB` position looked like test-fixture leakage | **not a defect** — `source='alpaca'` with a valid hash chain; a genuine paper-account holding |

Third pass (owner pointed out the module tasks were still open):

| Area | Invariant checked | Result |
|---|---|---|
| `assistant/order_lifecycle.py` | broker-status → proposal-status mapping; event-id stability for dedup | clean — replaced→`submission_unknown`, unknown non-terminal→`broker_accepted` (keeps reserving); `broker_event_id` deliberately excludes the `now()` fallback that `normalized_event_at` uses, so dedup identity stays stable |
| All execution modules | "a status mapping alone is not a valid state transition" | clean — **every** production write uses the fenced `update_proposal_status_if_current`; zero callers of the unconditional `update_proposal_status`. The 2026-07-30 review's item #2 (unconditional write in the order-type fallback) is resolved by the kernel split |
| Reservation release paths | "release reservations exactly once" | clean — all funnel through the atomic, status-conditional `mark_submission_failed_and_release`; double-release is structurally prevented |
| `assistant/portfolio_ledger.py` | double-entry balance | clean — enforced at write **and** at read (trial balance), all Decimal; the 1e-6 tolerance is applied to the aggregate on read, so accumulated drift cannot hide |
| `assistant/allocation_batch.py` | "submit none, or all"; preflight/enforcer parity | clean — parity is explicit and deliberate (strict `>`, gross submitted notional, shared cumulative open-order count) |
| `assistant/paper_evidence.py` | no cross-epoch pooling | clean — every observation query is epoch-scoped and each row's `lineage_hash` is checked against the epoch's |
| `scripts/personal_assistant_ui.py` | stale/synthesized money; approval gating | clean — persistent stale flags, submit disabled while stale, explicit "unavailable" states instead of zeros, price revalidated at approval rather than via the digest |
| Read-only command contracts | reporting surfaces leave execution tables unchanged | clean and already well-tested (`test_execution_characterization`, `test_platform_readiness`, `test_ml_shadow`, `test_allocation_batch` byte-for-byte preflight, `test_proposal_outcome_groups`) |
| `ml/databento_pit.py` | "do not allow a caller to assert point-in-time status" | clean — `point_in_time_data` is hardcoded `False` and the prerequisite evaluator **verifies** it rather than trusting the manifest |

Still **not** deep-read, and therefore not claimed: `ml/databento_source.py`
and `ml/databento_authoritative.py` bulk, `scripts/run_ml_shadow.py`, the
one-off research significance scripts, `assistant/ai_advisor.py`,
`platform_readiness.py`, `risk_copilot.py`, `strategy_proposals.py`,
`execution_telemetry.py`, `alert_delivery.py`, and the remaining bulk of
`storage.py` outside its reservation, order-update, and migration paths.
Several of these carry their own dedicated test modules; absence from this
list of findings is not a clearance.

## 8. Validation

Windows, Python 3.13.

- Baseline before any change (`main` at `07781c7`): **2875 passed,
  1 failed, 1 skipped, 25 warnings** — the failure is FPS-003.
- Full suite on the exact final tree: **2888 passed, 0 failed, 0 skipped,
  25 warnings** (450s). The skip count reaching zero is FPS-002.
- Reverse mutation on FPS-001: 4 tests fail with the fix reverted.
  Reverse mutation on FPS-004: 1 test fails with the fix reverted. Both
  restored and re-verified green.
- `compileall` clean; `git diff --check` clean.

FPS-003 did **not** reproduce on either of the two subsequent full runs,
which is itself the finding: it is intermittent, not deterministic, so a
single green suite is not evidence it is gone.

No test contacted a funded account. No proposal, approval, sizing,
submission, execution, or broker path was modified. The operational
checkout stays frozen at `9a91498` under `paper-epoch-002`; nothing here is
deployed.

## 9. Independent review (2026-08-06, appended)

Independent confirmation of FPS-001/002/004 and of the §5 dismissals is
recorded in `docs/REVIEW_2026-08-06_FULL_PROJECT_SWEEP_INDEPENDENT.md`.
Corrections: residual share-conversion escape in `tax_ledger_with_coverage`
(GFPS-001), comment honesty on monitoring_reports (GFPS-002), and
post-merge handoff cleanup (GFPS-003 / PR #160).
