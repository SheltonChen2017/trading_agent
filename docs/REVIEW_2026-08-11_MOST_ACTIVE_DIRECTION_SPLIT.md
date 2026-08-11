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

---

## Counter-review (Claude, 2026-08-11) — accepted; one missed generalized instance

Counter-review of `3b72242`, `9277c09`, and `6a4aa91` per
`docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`. All three commits: **accepted**.
All three findings are **confirmed** — two red-baselined against the
submitted tree. One gap was found in the correction and is fixed here, and
it is more severe than any finding in the original ledger.

### Every finding verified

| ID | Verdict | Independent evidence |
|---|---|---|
| MAD-001 | **Confirmed — but incompletely swept; see MADCR-001.** | Red-baselined: `test_most_active_lane_joins_provider_details_by_normalized_symbol` fails against `3be6326`. `verify_tickers()` normalizes at `assistant/ticker_verification.py:104` (`t.strip().upper()`), so my raw-key join was a genuine contract violation. |
| MAD-002 | **Confirmed.** | Red-baselined: the AppTest fails against `3be6326`. `_load_recommended_tickers` is decorated `@st.cache_data(ttl=_RECOMMENDED_STOCKS_CACHE_TTL_SECONDS)` with the constant set to 900, so labelling the click time "Fetched at" did overstate recency by up to 15 minutes. The correction derives source time from the rows and computes the disclosure from the constant rather than hardcoding "15". |
| MAD-003 | **Confirmed on both halves; one half over-corrected — see MADCR-002.** | The causal fix is right: "heavy volume pushing a name up" asserts causation from a screen that measures neither. The categorical fix is also right in principle — retail platforms *do* display tick-rule buy/sell volume estimates, so "no retail-accessible feed reports order flow" overreached. |

Codex's `tests/test_ui_ticker_suggestions.py` deserves specific credit: it
drives the **real Streamlit renderer** through `AppTest`, seeds session
state, and asserts on the rendered dataframes and captions across all four
buckets. That is strictly stronger verification than the source-level string
guards I shipped, and it is the reason MAD-002 was reproducible rather than
argued.

### MADCR-001 (P2, fixed here) — the same join bug survived in the IPO lane, where it fails OPEN

MAD-001 was fixed only in the most-active lane. The **identical** unnormalized
join remained at `build_recommended_tickers`'s IPO lane:

```python
ipo_detail_by_ticker = {c["ticker"]: c for c in ipo_candidates}   # raw provider symbol
c = ipo_detail_by_ticker.get(v["ticker"], {})                      # normalized uppercase
```

The smoking gun is three lines above it: the held-set filter already writes
`c["ticker"].upper() not in held_set`. The same block normalizes the provider
symbol for one purpose and not for the other.

**Why this instance is worse than the one that was fixed.** In the
most-active lane a failed join costs a volume figure and a direction — the
row renders "not reported". In the IPO lane the joined metadata feeds a
**safety guard**:

```python
claimed_date = c.get("date", "")
if _is_ipo_identity_mismatch(v.get("first_session_date"), claimed_date):
    dropped.append(v["ticker"]); continue
```

and `_is_ipo_identity_mismatch` returns **False when either date is
missing**. So a failed join empties `claimed_date`, the guard reports "no
mismatch", and the candidate is kept. That guard exists specifically to catch
"a reused symbol with older history" masquerading as a fresh listing — an
earlier independent review added it — and a case-only symbol difference
silently defeats it. A fail-open safety guard on a surface that recommends
securities is P2, not P3.

**Correction:** normalize both sides of the IPO join, matching the
most-active lane. Three regressions added: the fail-open case (a symbol whose
real first bar is 2020 against a claimed 2026 IPO must be dropped), the
must-still-succeed direction (` newco ` → `NEWCO` keeps its provider date),
and a source-level guard that fails when any *new* lane joins on a raw
symbol. The AI lane was examined and is **correct** — it normalizes both the
key (`c["ticker"].upper()`) and the lookup — which is what made the other two
lanes' divergence visible.

### MADCR-002 (P3, fixed here) — the accurate narrowing dropped load-bearing reasoning

Replacing "no retail-accessible feed reports order flow" with "this screener
does not provide classified order flow" is more accurate, but it removed the
part that stops the obvious wrong next step. A future reader of the narrowed
sentence can reasonably conclude "then find a screener that does" — and the
trap is precisely that a cheap substitute (tick-rule estimates over a thin
feed) looks like a solution while producing noise.

Restored in narrowed, verifiable form rather than as the original
categorical claim: classification requires trade prints matched against the
prevailing quote (consolidated trade-and-quote data), and the feed this
project actually has is Alpaca's free IEX tier — measured on 2026-08-10
quoting a large-cap at a ~6% spread while the consolidated market was
penny-wide. Added to `fetch_most_active_tickers`'s docstring and the action
plan; the UI caption was left short on purpose.

### Mutation evidence (all restored and re-verified green)

| Mutation | Result |
|---|---|
| Revert the IPO join to the raw key | all three new IPO regressions red, including the fail-open case |
| Revert Codex's most-active join fix | its own regression red plus the new source-level guard — fix load-bearing |
| (from the original round) forbidden label in UI copy, dropped finiteness guard, merged flat/unknown captions | each red, restored |

### Counter-review validation

Full suite on the final tree: recorded in the session handoff. `compileall`
clean; `git diff --check` clean. Presentation and research surfaces only —
no proposal, order, policy, scheduler, epoch, ML/LLM-authority, or execution
path changed; nothing deployed; epoch-003 untouched on `ef05dc1`.
