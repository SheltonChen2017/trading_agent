# Alpha battery — pre-registration

> **2026-08-17 validity note:** This remains the frozen historical declaration,
> but the result generated from it is invalid. The result Markdown and JSON
> were removed from active docs after their exact hashes and disposition were
> preserved in `docs/alpha-result.md`. The local runner's turnover/NAV,
> leave-one-out peer, and joint-regression defects are corrected for code
> integrity, but static latest basket labels and survivor-selected yfinance
> data mean this declaration cannot produce confirmation evidence.

Date: 2026-08-15
Author: Claude, at the owner's request
Status: **Frozen before any result was observed.** Written and committed
before `scripts/run_alpha_battery_20260815.py` was executed on real data.

This document exists because `CLAUDE.md` section 6 requires specifications
and gates to be frozen before confirmation results are seen, and every
research look to be counted. A battery of this size is otherwise a
false-discovery generator.

## 1. What this repository can and cannot support

The request specifies a survivorship-bias-aware US common-stock universe
with price, market-cap and liquidity screens, point-in-time fundamentals,
and point-in-time consensus estimates. Measured against what exists here:

| Requirement | Reality | Consequence |
|---|---|---|
| Survivorship-bias-aware universe | `config.UNIVERSE` is 104 hand-picked large/mega caps with no historical constituent history | **Survivorship bias is unavoidable and material.** Already a recorded project finding: three banks that failed inside the lookback window (SIVB, SBNY, FRC) are absent, and SBNY's ticker was silently reused |
| Exclude ETFs/preferred/warrants/SPAC/OTC | The universe already contains an ETF (`REMX`) and former SPAC-adjacent names | Handled by an explicit exclusion list, not by security-master metadata |
| Min price $5, min cap $500M, min ADV $5M | Every surviving name clears all three by orders of magnitude | **All three screens are no-ops.** They cannot be exercised |
| 2010-present | yfinance daily bars; many names IPO'd later (PLTR 2020, ABNB 2020, COIN 2021, RIVN 2021) | Early subperiods run on a smaller, even more survivor-skewed cross-section |
| Point-in-time fundamentals (revenue, COGS, assets, ROE, FCF, debt) | **Not available.** `signals/fundamentals.py` documents why: yfinance exposes only a CURRENT snapshot with no as-reported history, so using it on past dates is severe look-ahead | **ALPHA 009 and ALPHA 010 cannot be tested honestly and will not be run** |
| Point-in-time consensus EPS | `data/earnings_data.py` supplies disclosure dates, reported EPS and the estimate, with after-close releases mapped to the next session | PEAD is testable, but the estimate is the provider's stored figure and is **not independently verifiable as the pre-release consensus** |
| Sector/industry classification | `config.BASKETS` gives 16 hand-assigned groupings | Industry adjustment is an approximation, not GICS |
| Bid/ask spreads, market impact data | Not available | Slippage is modelled as a cost assumption only, never measured |

**Prices are yfinance adjusted closes.** Per `CLAUDE.md`, this is
exploratory and every artifact this run produces is marked
`point_in_time_data=false`.

## 2. Alphas that will be run, and those that will not

Run: ALPHA 001 (momentum, 4 variants), 002 (residual momentum, 2), 003
(reversal, 3 holding periods), 004 (industry-adjusted reversal, 3
lookbacks), 005 (volume-conditioned reversal, 4 buckets plus an
interaction), 006 (MAX effect, 3 specifications), 007 (PEAD SUE, 4 holding
periods), 008 (PEAD composite, 2 specifications), 012 (equal-weight
multi-alpha composite over whichever inputs survive).

**Not run: ALPHA 009 (gross profitability) and ALPHA 010 (quality
composite).** Neither can be computed from data that was publicly available
at the historical dates. Substituting today's fundamentals would produce
numbers, and those numbers would be look-ahead bias with a Sharpe ratio
attached. ALPHA 011 (momentum x quality) falls with them: its quality leg
does not exist.

Refusing these three is not a gap to fill later with the same data. It
needs a point-in-time fundamentals source this project does not have.

## 3. Frozen specification

- **Entry lag**: one full trading day. A signal computed from closes up to
  and including session `t` is entered at the close of `t+1`. Nothing is
  ever entered at a price used to compute the signal.
- **Weighting**: equal, within the selected set, rebalanced on schedule.
- **Long-only**: top 10% and, separately, top 20%.
- **Long-short**: top decile long, bottom decile short, dollar-neutral.
- **Rebalance**: monthly (last session of the month) for the momentum
  family; daily for the reversal family; event-driven for PEAD.
- **Costs**: 0, 5, 10, 25 bps per side, applied to realised turnover.
- **IC**: Spearman rank IC computed **per date, never pooled**, reusing
  `ml/evaluation.py`'s `date_level_spearman_ic`. Pooled or row-level
  statistics are a standing project prohibition.
- **Significance**: block bootstrap over dates, never i.i.d. resampling,
  because overlapping holding periods make adjacent observations dependent.
- **Subperiods**: 2010-2014, 2015-2019, 2020-2022, 2023-present, declared
  now and not chosen after seeing results.

## 4. Declared look count and multiplicity correction

Every specification below is one look. They are declared now, before any
result is seen, and the count is used for the correction whether or not any
of them later looks interesting.

| Family | Specifications | Holding periods | Looks |
|---|---|---|---|
| MOM (3-1, 6-1, 9-1, 12-1) | 4 | 1 | 4 |
| Residual MOM (6-1, 12-1) | 2 | 1 | 2 |
| Reversal 5D | 1 | 3 | 3 |
| Industry-adjusted reversal (3D, 5D, 10D) | 3 | 3 | 9 |
| Volume-conditioned reversal (4 buckets + interaction) | 5 | 1 | 5 |
| MAX effect (MAX alone, reversal alone, interaction) | 3 | 1 | 3 |
| PEAD SUE | 1 | 4 | 4 |
| PEAD composite (additive, sign-interaction) | 2 | 2 | 4 |
| Multi-alpha composite | 1 | 1 | 1 |
| **Total primary looks** | | | **35** |

Portfolio construction multiplies each primary look by three (long-only
10%, long-only 20%, long-short). Cost scenarios are **not** counted: they
are the same hypothesis under different assumptions, not independent
hypotheses. Construction variants **are** counted: 35 x 3 = **105 looks**.

**Declared correction: Bonferroni at 105 tests.** A per-look p-value must
fall below 0.05/105 = **0.000476** to count as anything other than noise.

Subperiod, regime, and size-bucket breakdowns are **descriptive only** and
carry no independent significance claim. Reporting a subperiod as
significant after the full-period test failed would be exactly the
look-inflation this correction exists to prevent.

## 5. The prior that matters most

This project has already measured its own detection floor on this universe.
The recorded finding (2026-08-03) is a **minimum detectable effect of
roughly 2-4% per trade**, far larger than any realistic cross-sectional
equity alpha. Eleven signals have been tested here; **zero have been
confirmed.**

The honest expectation for this battery is therefore that **most or all of
these 35 specifications will be indistinguishable from noise at the
corrected threshold, and that outcome is the most likely correct answer
rather than a failure of the test.** A specification that does clear the
threshold on 104 survivor-selected large caps should attract more
suspicion, not less.

## 6. What a result from this battery can and cannot mean

It can establish that a signal is not detectable here. It cannot establish
that a signal has persistent alpha: this universe is survivor-selected, the
prices are adjusted rather than point-in-time, the fundamental legs are
missing, and no result here has prospective out-of-sample evidence.

Nothing in this battery authorizes any trade, proposal, allocation change,
policy change, deployment, or epoch action.

---

## Independent-review addendum (2026-08-16; not part of the frozen spec)

The pre-registration was committed before results and its conservative
105-look threshold is retained. The submitted runner did not implement all 35
primary looks and, more importantly, its 2,000-draw bootstrap could not produce
a p-value below the frozen 0.000476 gate. Its set-based turnover also missed
long/short side flips. The resulting artifact is invalidated pending a clean
rerun with the reviewed code; this addendum does not rewrite the frozen plan.
