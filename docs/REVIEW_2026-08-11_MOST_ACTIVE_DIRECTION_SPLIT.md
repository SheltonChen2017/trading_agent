# Independent review — most-active price-direction split

Prepared: 2026-08-11

Reviewer: Codex

## Outcome

**Accepted after correction.** Claude made the right product decision: the
yfinance most-actives screen reports trading volume and price change, not a
buyer-versus-seller decomposition, so the UI must not present its volume as
"most bought" or "most sold." The implementation correctly added the
provider's `regularMarketChangePercent`, rejected unusable numeric values,
kept flat and unknown changes distinct, and rendered advancing and declining
names in separate research-only columns. No proposal, approval, policy,
broker, order, scheduler, epoch, ML/LLM-authority, or live-trading path was
added or changed.

The submitted implementation was good but not fully review-complete. Two
user-visible edge cases were reproduced red and corrected: verification
normalizes symbols to uppercase while the provider-detail join was
case-sensitive, and the UI labelled the current click time as the fetch time
even though its loader may return a result cached for 15 minutes. Review also
narrowed categorical claims about the availability of order-flow data and
removed language implying that volume caused the observed price move. Final
implementation quality: **8/10** — sound design and careful numeric handling,
with minor data-joining, freshness-disclosure, and copy-precision misses.

## Exact snapshot and commit disposition

- Base: merged `main` / `origin/main` `2c886c1` (PR #185).
- Implementation branch: `user/claude/most-active-direction-split-20260810`.
- Implementation commit: `3be6326`, published at
  `origin/user/claude/most-active-direction-split-20260810`.
- Review branch: `codex/review-most-active-direction-split-20260811`.
- Correction commit: `3b72242` (`Correct most-active direction presentation`).
- The correction and subsequent review documentation were local-only when
  this report was prepared. Nothing was pushed, merged, deployed, or applied
  to the active evidence epoch during the review.

| Commit | Disposition | Result |
|---|---|---|
| `3be6326` | **Accepted after correction** | The feature boundary and main behavior are correct. Three P3 issues were closed by `3b72242`; no P0, P1, or P2 defect was found. |

## Prioritized issue ledger

Final state: **0 P0, 0 P1, 0 P2, and 0 P3 open**.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| MAD-001 | P3 | Closed | `3be6326` | `assistant/recommended_stocks.py::build_recommended_tickers` | Provider metadata was keyed with the provider's original symbol while `verify_tickers()` returns stripped uppercase symbols. A case-only difference made a verified row lose its real volume and price direction and appear as "not reported." | A lowercase `mixed` provider row verified as `MIXED` produced `price_direction=None` and omitted volume; the regression failed red. | The two sides violated the verification contract's explicit symbol normalization and could misstate provider facts on a valid row. | Canonicalize both provider and verified join keys with `strip().upper()`. | Red: focused regression failed with `None != "advancing"`. Green: the same test passed and preserved volume `1,234` and change `+1.25%`. |
| MAD-002 | P3 | Closed | `3be6326` | `scripts/personal_assistant_ui.py`, Ticker Suggestions result caption | The page displayed `ran_at` — the current button-click time — as "Fetched at" even though `_load_recommended_tickers` caches results for 900 seconds. A user could read a cached direction as freshly fetched. | A real AppTest session seeded data fetched at 16:00 and displayed at 16:14; the submitted UI omitted 16:00 and any cache disclosure, so the regression failed red. | Freshness is part of the meaning of a same-day market screen; the UI must distinguish source time from display time instead of overstating recency. | Derive source fetch times from returned rows, label display time separately, and disclose the 15-minute cache bound. | Red: AppTest could not find the source timestamp. Green: it found the source timestamp, display context, cache disclosure, both direction tables, and the flat/unknown captions. |
| MAD-003 | P3 | Closed | `3be6326` | `assistant/recommended_stocks.py`; `scripts/personal_assistant_ui.py`; action-plan/handoff prose | Comments and documentation said no retail-accessible feed reports order flow and described heavy volume as "pushing" price up or down. The first claim was broader than the yfinance contract established here; the second implied unsupported causality. | The reviewed source only establishes that this yfinance screen supplies volume and price change. The installed yfinance 1.5.2 live response confirmed `regularMarketVolume` and `regularMarketChangePercent`, not classified order flow. | Source-specific, descriptive language is required so an observation-only UI does not turn an unmeasured market-data claim or causal interpretation into fact. | State only that this screener does not provide classified order flow; describe heavily traded names whose prices rose or fell. | Focused source guards and the real Streamlit renderer passed; final diff inspection confirmed the categorical and causal phrases were removed from current feature prose. |

## Contract review

- **Data source:** installed yfinance 1.5.2 returns numeric
  `regularMarketChangePercent` on the live `most_actives` response. The feature
  carries that field without deriving buy/sell pressure.
- **Numeric failure direction:** `None`, bool, unparseable values, NaN, and
  both infinities remain unknown; exact zero remains `unchanged`.
- **Visibility:** advancing and declining rows retain source order inside
  their respective columns. Flat and unknown rows are explicitly named and
  are not silently folded into either direction.
- **Compatibility:** `RecommendedTicker.price_direction` is optional and
  defaulted; the dataclass is in-memory only. Existing IPO and AI lanes remain
  unchanged.
- **Authority:** the page is still research-only. A user must separately add
  a ticker to Buying and pass the existing proposal, policy, validation, and
  exact-approval workflow before any paper order can be submitted.

## Validation

Environment: Windows, repository `.venv`, Python 3.13.14, Streamlit 1.60.0,
yfinance 1.5.2.

- Submitted-tree red evidence: **2 failed as intended** (normalized-symbol
  metadata join and cached-source freshness disclosure).
- Corrected narrow regressions: **2 passed** in 2.53s.
- Focused recommendation/UI/theme suite: **76 passed** in 47.98s.
- Full repository suite: **3,378 passed, 0 failed, 0 skipped** — A–F 1,035 in
  152.08s; G–M 1,025 in 197.61s; N–S 1,028 in 128.15s; T–Z 275 in 184.10s;
  nested fault matrix 15 in 5.51s. The 25 warnings are the existing one
  websockets and 24 joblib/NumPy dependency deprecations.
- Repository-prescribed `compileall`: clean.
- `git diff --check`: clean apart from expected Windows line-ending notices.
- Narrow changed-file secret-shape scan: zero matches.
- Read-only live screener contract check returned symbols with numeric volume
  and `regularMarketChangePercent`; no broker API or operator database was
  touched.

## Remaining limits and next step

This view is descriptive, not predictive: an advancing high-volume name is
not a buy signal, a declining one is not a sell signal, and the project still
has zero confirmed predictive strategies. The source is cached for up to 15
minutes and the UI now says so. The feature does not supply trade-initiator
classification or prove that volume caused the price move.

The immediate repository step is owner authorization to publish and merge the
review branch. That does not authorize deployment. The separate operational
priority remains an owner-authorized epoch-004 roll before the scheduled AEP
dividend payment on 2026-09-10, so the already-merged dividend and AP-7 fixes
enter the frozen runtime together; the complete epoch transition runbook must
be followed rather than patching epoch-003 in place.
