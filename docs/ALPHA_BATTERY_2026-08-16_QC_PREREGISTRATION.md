# QuantConnect alpha battery — pre-registration

> **POST-RUN AUDIT NOTE (2026-08-16):** This file is preserved as the frozen
> historical declaration, not edited into a claim that the submitted run
> followed it. Independent review found that the implementation violated its
> entry-lag, delisting, residual-regression, construction, turnover, and
> return-normalization rules. Section 4 also counted 135 portfolio tests but
> omitted the IC hypothesis used for the headline gate; the actual declared
> family is 15 specifications × 3 universes × 4 tested outcomes = **180**.
> All submitted results are invalid pending a corrected cloud rerun.

Date: 2026-08-16
Author: Claude
Governing method: `docs/ALPHA_BATTERY_METHOD_V2.md`
Status: **Frozen before any QuantConnect alpha result was observed.**
Written and committed before the algorithms were run.

## 1. What changed since the local battery

Five inert smoke runs (`docs/QUANTCONNECT_SMOKE_2026-08-16.md`) established
what the cloud dataset does and does not fix, and a sixth measured field
availability directly:

| Field | Present | Zero |
|---|---|---|
| GrossProfit, TotalAssets, TotalDebt, NetIncome, FreeCashFlow, ROE, ROA, TotalEquity | 100% | ~0% |
| MorningstarIndustryCode / SectorCode | 100% | 0% |
| **MarketCap** | 100% | **21.4%** |

Consequences, all decided before running anything:

- **ALPHA 009, 010 and 011 become testable for the first time.** Every
  field they need is present at 100%. They were refused locally for lack
  of point-in-time fundamentals.
- **ALPHA 004 stops being void.** Real industry codes exist, so the
  industry adjustment is a real adjustment rather than the size-bucket
  proxy that leaked future capitalization (ABR-005).
- **The market-cap screen must treat 0 as MISSING.** One row in five
  carries zero, and every screen so far read that as "below the
  threshold". Where a fallback is available (price x shares outstanding)
  it is used, and **both the fallback rate and the still-missing rate are
  reported per rebalance**.
- **Securities are retained until delisting resolves.** The retention
  probe raised observed delistings from 11 to 88, with 84 of 88 firing
  after universe exit.

## 2. Specifications

Two algorithms, split by rebalance cadence, each run on all three
universes.

**Monthly (`alpha_battery_monthly.py`), 10 specifications:**

| # | Spec | Definition |
|---|---|---|
| 001 | MOM_3_1, MOM_6_1, MOM_9_1, MOM_12_1 | price[t-21]/price[t-21m] - 1 |
| 002 | RESIDUAL_MOM_6_1, RESIDUAL_MOM_12_1 | cumulative residual after joint market+industry regression |
| 009 | GROSS_PROFITABILITY | GrossProfit / TotalAssets |
| 010 | QUALITY_COMPOSITE | z(ROE) + z(FCF/Assets) - z(TotalDebt/Assets) |
| 011 | QUALITY_MOMENTUM | z(MOM_12_1) + z(QUALITY_COMPOSITE) |
| 012 | MULTI_ALPHA_COMPOSITE | equal-weight z of MOM_12_1, RESIDUAL_MOM_12_1, GROSS_PROFITABILITY, QUALITY_COMPOSITE |

**Short-horizon (`alpha_battery_short.py`), 5 specifications, 5-day
holding:**

| # | Spec | Definition |
|---|---|---|
| 003 | REVERSAL_5D | -(5-day return) |
| 004 | INDUSTRY_ADJ_REVERSAL_5D | -(5-day return - industry mean), real Morningstar industry |
| 005 | ABNORMAL_VOLUME_REVERSAL | -(5-day return) x clipped volume z-score |
| 006 | MAX_20 | -(max daily return over 20 sessions) |
| 006b | MAX_x_REVERSAL | -(5-day return) x percentile rank of MAX_20 |

**Not run: ALPHA 007 and 008 (PEAD).** They need an event study keyed to
announcement dates, not a cross-sectional panel, and building that
properly is a separate piece of work. Recording them as not-run is
consistent with how they were handled locally, and is preferable to a
rushed event study. This is a **deviation from "all alphas" and is stated
here rather than discovered in the results.**

## 3. Frozen measurement rules

- **Entry lag one session.** Score from closes through `t`, position from
  the close of `t+1`.
- **Equal weight** within the selected decile.
- **Constructions:** long-only top 10%, long-only top 20%, long-short
  top-minus-bottom decile.
- **Costs:** 0, 5, 10, 25 bps per side on realised turnover.
- **Turnover is drift-aware** (Method V2 section 1.2): prior weights are
  carried forward through their own returns before comparison, and a
  long-to-short flip costs the full round trip.
- **IC** is Spearman rank IC per date, never pooled.
- **Significance** is computed LOCALLY from the per-date series that the
  algorithms emit, using the reviewed, tested `stationary_bootstrap_p`
  with **20,000 draws**. No significance code is written inside LEAN.
- **Gate reachability is asserted before use** (Method V2 section 1.1):
  `1/(draws+1)` must be below the corrected threshold, or the run refuses.

## 4. Declared look count

15 specifications x 3 universes x 3 constructions = **135 looks.**

**Bonferroni threshold: 0.05/135 = 0.00037.**

With 20,000 draws the smallest attainable p-value is `1/20001 =
0.00005`, which is **below** the threshold, so the gate is reachable. That
check is asserted in code, because the first local battery's headline was
arithmetically impossible for exactly this reason and nobody noticed.

Cost scenarios are not counted; they are one hypothesis under different
assumptions. Size buckets, liquidity terciles and subperiods are
descriptive.

**Cumulative:** these specifications have now been examined on three
occasions (105 + 63 + 135). A nominal pass on a third look at the same
hypothesis deserves discounting, and any result near the threshold will be
reported against both the 135-look and the 303-look correction.

## 5. Prior expectation

The local batteries returned nulls, and their measurement was defective
enough that the nulls carry little information. This battery has a genuine
chance of detecting something because the cross-section is larger, the
fundamentals exist, and delisted names are priced.

**It also has more ways to produce a false positive**, and the direction of
every known residual bias is the same: missing market caps exclude names
non-randomly, delisting returns are still not modelled in the portfolio
arithmetic, and the universe screens still eject failing companies before
they die. All three flatter results. **A positive finding here should be
treated as a hypothesis about the data pipeline until proven otherwise.**

Nothing in this battery authorizes a trade, allocation, policy change,
deployment, or epoch action.
