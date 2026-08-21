# QuantConnect smoke tests — findings

> **2026-08-17 audit note:** Retained as plumbing history, not alpha evidence.
> The later full audit corrected the executable algorithms to QuantConnect's
> current Python API and fixed the local cloud runner so missing numeric
> progress cannot wait forever. These smoke observations do not validate the
> later alpha algorithms, and their incomplete source/compile provenance
> prevents reuse as a review gate.

> **PROVENANCE LIMIT (independent review, 2026-08-16):** This historical
> report did not commit the QuantConnect project/backtest IDs or hashes of the
> retrieved logs. Its qualitative observations are retained, but another
> reviewer cannot link them to exact cloud snapshots from Git alone. Future
> result analysis now refuses to run without exact backtest IDs and records
> every input log hash (`e8eb558`).

Date: 2026-08-16
Author: Claude
Method: `docs/Archive/Research/ALPHA_BATTERY_METHOD_V2.md` step 4
Status: **Plumbing evidence only. No alpha statistic was produced, and
none of these runs counts as a research look** — both algorithms are
incapable of reporting one, which `tests/test_lean_smoke_test.py` enforces
against the source rather than trusting the author.

FIVE cloud runs, all inert (`orders placed: 0`, confirmed independently by
QuantConnect's own `runtimeStatistics`: Volume $0.00, Holdings $0.00). Each
was written to answer the question the previous one raised.

| Run | Project | Window | Question it answered |
|---|---|---|---|
| universe smoke | 35239775 | 2013-2016 | dynamic membership, field availability |
| delisting probe | 35239902 | 2022-2023 | do dead companies exist in the data at all |
| universe smoke 2 | 35239933 | 2022-2023 | do the SCREENS see those deaths |
| retention probe | 35240088 | 2022-2023 | does keeping the subscription surface them |
| bank trace probe | 35240157 | 2022-2023 | why were the three failed banks never selected |

The chain matters more than any single run: each result was implausible in
a specific way, and following that rather than accepting it is what
produced section 8, which is the finding that changes the plan.

## 1. The survivorship hole is genuinely fixed — verified directly

The local dataset could not price a delisted company at all: yfinance
returned **zero rows** for SIVB, FRC and SBNY. Subscribing to them directly
on QuantConnect:

| Ticker | Bars | Last price | Delisting events |
|---|---|---|---|
| SIVB | 206 | $106.04 | WARNING 2023-03-27, **DELISTED 2023-03-28** |
| SBNY | 206 | $64.60 | WARNING 2023-03-27, **DELISTED 2023-03-28** |
| FRC | 231 | **$1.82** | WARNING 2023-05-02, **DELISTED 2023-05-03** |
| MSFT (control) | 398 | — | none, still listed |

FRC's final print at $1.82 is the collapse itself. The control matters: had
MSFT also returned zero bars, "zero bars for a dead company" would have
meant a broken probe rather than missing data.

**This is the single claim the whole move to QuantConnect rests on, and it
holds.**

## 2. Two of five tickers silently resolved to the WRONG company

| Requested | Resolved to | Bars | Reality |
|---|---|---|---|
| BBBY | `OSTK SF3G193U19ID` | **0** | Overstock took the Bed Bath & Beyond ticker |
| CS | `CSR S8C8M5R54WV9` | 398 | not Credit Suisse |

`AddEquity("TICKER")` resolves against the **current** ticker map, not the
company that held the ticker on the historical date. This is exactly the
ticker-reuse hazard the owner's specification warns about, and one this
project has already been bitten by once (SBNY's ticker was reused).

**Binding rule for the LEAN alpha implementation:** universe selection via
coarse/fine returns `Symbol` objects carrying a `SecurityIdentifier` and is
safe. **A hardcoded ticker string is not, anywhere, ever.** Had the probe
lacked a control and a resolved-ID log, both failures would have read as
"no data for a dead company" — the opposite of the truth.

## 3. The screens hide the deaths that matter

The first smoke test reported **1 delisting across ~1,300 names over four
years**, which is implausible. Moving the same inert algorithm onto
2022-2023 raised it to **11** — and **SIVB, SBNY and FRC are not among
them**, though section 1 proves they are in the dataset with delisting
events inside that window.

The mechanism: a company that starts failing breaks the price, market-cap
or ADV screen and leaves the universe at the next reconstruction. Its
delisting then fires while the algorithm is no longer subscribed, so it is
never observed. SIVB traded above $100 until days before failure and still
escaped detection, because the collapse and the delisting are three weeks
apart and the screens act in between.

**This is not the dataset's survivorship bias. It is a strategy-construction
artifact that MIMICS one**, and it is more insidious because the data is
fine — only the algorithm's view of it is truncated.

**Consequence for the alpha work, which is the reason this matters:** the
window between "starts failing" and "delists" is where the most extreme
negative returns live. A screened universe that drops names at the start of
that window systematically excludes them, which **understates what a short
leg would have earned** and flatters a long-only book. Any momentum or
reversal result computed this way inherits the distortion.

**Requirement added for the LEAN implementation:** a security must be held
until its delisting resolves, not dropped when it exits the universe.
Universe removal governs new positions; it must not govern existing ones.

## 4. Field availability

| Field | Result |
|---|---|
| Industry classification | **0 rows missing** in both runs |
| Point-in-time market cap | 411,431 missing rows (2013-16), 37,256 (2022-23) |
| Universe size, 2013-16 | min/median/max **940 / 1,317 / 1,715** |
| Universe size, 2022-23 | min/median/max **1,475 / 2,010 / 2,321** |

Industry codes being complete **un-voids the industry-adjusted
specification**, which had no honest local implementation (the local proxy
used size buckets and leaked future capitalization — ABR-005).

Universe sizes are close to the local build's B_core median of 1,163 for
the overlapping era, which is a mild independent check that the screens are
being applied comparably.

The missing-market-cap counts are cumulative across ~1,000 selections and
represent names without fundamentals, which the screen already excludes.
They are recorded rather than interpreted: **this run does not establish
what fraction of any single date's cross-section is affected**, and that is
the number that would actually matter.

## 5. API facts learned, worth not rediscovering

- `authenticate` returns only `{"success": true}`. **CQC-001 remains
  partially open**: it is the one endpoint QuantConnect documents as
  returning `success`, so a clean authenticate proves nothing about the
  others. In practice every endpoint used here did return it.
- Logs are **not** in `backtests/read`. They come from
  `backtests/read/log`, which requires a `query` parameter and paginates at
  **200 lines**, with `start`/`end` as LINE NUMBERS. Its error message
  calls them timestamps, which is wrong and cost two probe attempts.
- `projects/create` returns `{"projects": [...]}`; the id is
  `projects[0].projectId`.
- A new project already contains `main.py`, so `files/update` is the
  correct call and `files/create` is the fallback, not the reverse.

## 6. What is still not established

- **No alpha result exists.** Nothing here says anything about any signal.
- Whether the delisting RETURN is usable in a portfolio calculation, as
  opposed to the delisting event being visible.
- Per-date fundamental coverage, per section 4.
- Whether the LEAN alpha implementation reproduces the local one. That is
  the replication test, and it has not been attempted.

Nothing in this document authorizes a trade, allocation, policy change,
deployment, or epoch action.

## 7. Retention works, and confirms the screens were hiding deaths

A fourth inert run retained each security's subscription when it left the
universe, re-adding BY SYMBOL rather than by ticker string:

| | Delistings observed |
|---|---|
| Screened universe, subscriptions dropped on exit | **11** |
| Same screens, subscriptions retained | **88** |

**84 of the 88 fired AFTER the security had left the universe.** That is
the mechanism proved directly: the screens were hiding roughly eight
delistings out of every nine.

**Requirement stands: universe removal governs new positions only. A held
security must be tracked until its delisting resolves.**

## 8. The fundamentals are missing for exactly the companies that died

Retention still did not surface SIVB, SBNY or FRC. A fifth probe traced
them through coarse and fine selection:

| Ticker | Coarse | Fine | Cause | Fate |
|---|---|---|---|---|
| **SIVB** | 195 | **0** | `HasFundamentalData=False`, every appearance | failed 2023-03 |
| **FRC** | 231 | 229 | `MarketCap = 0`, every appearance | failed 2023-05 |
| **SBNY** | 197 | 196 | `MarketCap = 0`, every appearance | failed 2023-03 |
| PACW | 272 | 268 | cap $3.7bn -- **included** | survived, later merged |

Their PRICE data is perfect: SIVB shows $488.57 at $527m daily dollar
volume. It is the FUNDAMENTALS that are absent, and they are absent for
the three that failed while present for the one that did not.

**This is the finding that matters most, and it is not fixed by moving to
QuantConnect.** A market-cap screen silently excludes companies whose
fundamental data is missing, and missingness correlates with failure. The
result is a survivorship-shaped bias arriving through a different door
than the local dataset's: not absent prices, but absent fundamentals.

`MarketCap == 0` was being read as "below the $500m threshold" rather than
"unknown". Failing closed on a missing value is defensible. Doing it
SILENTLY is not, because the excluded set is then invisible and correlated
with the outcome being studied.

**Requirements added to Method V2 before any alpha runs:**

1. Universe construction must distinguish **excluded by screen on a real
   value** from **excluded because the value is missing**, and report both
   counts per rebalance date. Without that split, a liquidity screen and a
   data gap are indistinguishable in the output.
2. `MarketCap == 0` must be treated as MISSING, never as a small number.
3. `HasFundamentalData` is not a clean security-type filter. It rejected a
   $40bn bank. Any use of it must report what it removed.
4. The A/B/C comparison inherits this: a stricter cap screen excludes more
   fundamentals-missing names, so part of any A-versus-C difference is a
   data-coverage difference rather than a size effect.

## 9. Corrected summary of what these runs establish

- **Delisted PRICE history exists and is usable.** Verified directly.
- **Delisting events are observable**, but only if subscriptions are
  retained past universe exit.
- **Point-in-time fundamentals have outcome-correlated gaps.** Verified on
  four named companies with a surviving control.
- Industry classification is complete where fundamentals exist.
- **No alpha result exists, and the universe construction is not yet
  trustworthy enough to produce one.**

The honest position is that QuantConnect fixes the price half of the
survivorship problem and does not fix the fundamentals half. That is still
a large improvement over a dataset which had neither, but the earlier
framing -- that the cloud dataset removes survivorship bias -- is too
strong and is corrected here.
