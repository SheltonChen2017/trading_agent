# QuantConnect alpha battery — results

> **INVALIDATED BY INDEPENDENT REVIEW (2026-08-16).** The statistics and
> conclusions below were produced by code that used raw, split-affected bars
> for returns; entered on the scoring close instead of the next session;
> counted non-session `OnData` calls as short holding days; omitted terminal
> delisting outcomes; implemented residual momentum differently from Method
> V2; reused long-short turnover for long-only portfolios; and omitted IC
> from the multiplicity family. The benchmark was neither date- nor
> cost-matched. These artifacts remain only as audit history. **Do not cite
> any pass, null, profitability, benchmark, or survivorship conclusion from
> this document.** Correction `e8eb558` requires a fresh independent
> QuantConnect rerun; no corrected cloud result exists yet.

Date: 2026-08-16
Author: Claude
Specification: `docs/ALPHA_BATTERY_2026-08-16_QC_PREREGISTRATION.md`
(frozen and committed before any result was observed)
Governing method: `docs/ALPHA_BATTERY_METHOD_V2.md`
Historical submitted status (now void): **Exploratory. One specification clears the pre-declared threshold
and is described below with the reasons to doubt it. Nothing here
authorizes a trade, allocation, policy change, deployment, or epoch
action.**

Panel: 2012-01 to 2024-12, **142 monthly observations**, three universes
reconstructed point-in-time from QuantConnect fundamentals.

Gate: **Bonferroni at 135 declared looks, p < 0.00037.** Bootstrap: 20,000
draws, smallest attainable p 0.00005, so the gate is reachable — asserted
in code before any result was computed.

## 1. The headline: one specification clears

**`QUALITY_COMPOSITE` in Universe A_large: IC p ≤ 0.00005 against a gate
of 0.00037.** This is the first result in this project's history to clear
a pre-declared, multiplicity-corrected threshold.

The p-value sits at the bootstrap floor: no resampled series out of 20,000
produced a mean IC as large as the observed one. It should be read as
`p ≤ 0.00005`, censored, not as a point estimate.

| Universe | Mean IC | IC IR | % positive | IC p | Verdict at gate |
|---|---|---|---|---|---|
| **A_large** | **0.0355** | **0.322** | 63% | **≤0.00005** | **CLEARS** |
| B_core | 0.0238 | 0.265 | 61% | 0.00040 | misses by 0.00003 |
| C_broad | 0.0211 | 0.246 | 61% | 0.00065 | misses |

Definition: `z(ROE) + z(FCF/Assets) - z(TotalDebt/Assets)`, winsorised at
1/99 before standardising, computed from point-in-time Morningstar
fundamentals.

### Why this one survives the checks that killed everything else

**Sign stability in all nine cells.** Across three universes and three
subperiods, the mean IC is positive in every one:

| Universe | 2012-16 | 2017-20 | 2021-24 |
|---|---|---|---|
| A_large | +0.028 | +0.053 | +0.025 |
| B_core | +0.025 | +0.014 | +0.033 |
| C_broad | +0.022 | +0.007 | +0.035 |

Every prior candidate in this project flipped sign across subperiods.

**It decays as the universe broadens** (0.0355 → 0.0238 → 0.0211), which
is the OPPOSITE of the specification's small-cap-dependence warning
pattern. It is not an artifact of admitting small illiquid names; it is
strongest among the largest, most liquid companies.

**The effect size is plausible rather than suspicious.** A monthly rank IC
around 0.02-0.04 is what the published quality literature reports. A
look-ahead leak would typically produce something far larger, so the
magnitude is mild evidence against contamination rather than for it.

## 2. The finding that matters more: significance without profitability

**Every long-short construction loses money, in every universe, at every
cost level** — including the specification that clears the IC gate.

This looked exactly like the contamination that invalidated the local
battery, so it was checked rather than explained away. It is not
contamination:

- IC and decile spread **correlate 0.70-0.88 per date**
- They **agree in sign 73-86% of months**

The ranking is not inverted. What kills the book is asymmetry in the short
leg. For `QUALITY_COMPOSITE` in B_core the mean bottom-decile return is
**+1.98%/month against the top decile's +1.19%**, and the medians agree
(1.69% vs 1.16%). The worst months are junk rallies — short legs up ~20%
in 2020-04, 2020-05 and 2021-04 — which swamp many small wins.

**A signal can rank correctly and still be unprofitable long-short.** That
is the single most useful thing this battery has produced, and it would
have been invisible if only IC had been reported.

## 3. Everything else

| Spec | A IC | B IC | C IC | best p | Verdict |
|---|---|---|---|---|---|
| QUALITY_COMPOSITE | 0.0355 | 0.0238 | 0.0211 | **≤0.00005** | **clears in A** |
| GROSS_PROFITABILITY | 0.0330 | 0.0278 | 0.0255 | 0.0032 | misses |
| MULTI_ALPHA_COMPOSITE | 0.0344 | 0.0256 | 0.0230 | 0.0080 | misses |
| QUALITY_MOMENTUM | 0.0285 | 0.0207 | 0.0195 | 0.0160 | misses |
| RESIDUAL_MOM_12_1 | 0.0117 | 0.0103 | 0.0099 | 0.316 | null |
| MOM_9_1 | 0.0116 | 0.0097 | 0.0112 | 0.232 | null |
| MOM_12_1 | 0.0109 | 0.0089 | 0.0099 | 0.353 | null |
| MOM_6_1 | 0.0070 | 0.0076 | 0.0099 | 0.215 | null |
| RESIDUAL_MOM_6_1 | 0.0028 | 0.0057 | 0.0067 | 0.396 | null |
| MOM_3_1 | −0.0021 | −0.0020 | 0.0001 | 0.835 | null |

**The momentum family is null on honest data.** On the local
survivor-selected universe it looked like the only family surviving costs;
here, with delisted names priced and point-in-time fundamentals, every
momentum specification has p > 0.2. That is a direct correction of a local
result rather than a new one.

**`GROSS_PROFITABILITY` decays sharply in the recent period** (A: +0.0184,
+0.0782, then +0.0016 across the three subperiods). `QUALITY_COMPOSITE`
does not, and is strongest recently in B and C.

## 4. Universe construction, measured

| | A_large | B_core | C_broad |
|---|---|---|---|
| Fine rows | 178,769 | 312,696 | 429,848 |
| Market cap reconstructed from shares | 16,826 (9.4%) | 35,268 (11.3%) | 52,239 (12.2%) |
| Still missing, excluded | 3,206 (1.8%) | 7,291 (2.3%) | 12,771 (3.0%) |

The bank-trace probe found `MarketCap == 0` on 21.4% of raw rows, which
every earlier screen silently read as "below threshold". Reconstructing
from shares outstanding recovers most of it; the residual 1.8-3.0% is
excluded and **counted**, so the excluded set is no longer invisible.

## 5. Reasons to doubt the headline, stated plainly

1. **IC significance is not profitability.** The specification that clears
   the gate loses money long-short in all three universes.
2. **The p-value is censored at the bootstrap floor.** It is `≤0.00005`,
   and 20,000 draws cannot say how much smaller.
3. **Third look at the same hypothesis.** Quality has now been examined
   across 105 + 63 + 135 declared looks. Against the cumulative 303-look
   correction (0.000165) it still clears, but a third-look pass deserves
   discounting.
4. **Delisting returns are still not in the portfolio arithmetic.** The
   universe now contains companies that later died, and the retention
   finding shows the screens eject them before death. The residual bias
   flatters results.
5. **Survivorship of the fundamentals, not the prices.** SIVB carried no
   fundamental data at all and FRC/SBNY carried zero market caps, so the
   three most famous failures of the period were absent from every
   universe here. A quality signal is exactly the signal that would have
   ranked them badly, and they are missing.

Point 5 is the one I would attack first. **A quality factor evaluated on a
universe that structurally excludes the companies whose fundamentals
collapsed is measuring quality among survivors of a fundamentals screen.**

## 6. Short-horizon family: statistically real, commercially dead

Six runs (three universes x two date windows, merged), **1,221-1,299
five-day observations** against the monthly family's 142. The extra power
changes the picture completely.

| Spec | A IC p | B IC p | C IC p | Clears gate |
|---|---|---|---|---|
| INDUSTRY_ADJ_REVERSAL_5D | 0.00015 | 0.00015 | 0.00005 | **all three** |
| MAX_X_REVERSAL | 0.00005 | 0.00010 | 0.00035 | **all three** |
| REVERSAL_5D | 0.00035 | 0.00105 | 0.00045 | A only |
| MAX_20 | 0.181 | 0.0066 | 0.00010 | C only |
| ABNORMAL_VOLUME_REVERSAL | 0.176 | 0.850 | 0.0217 | none |

**And every one of them loses money after costs**, in every universe:

| Spec | Turnover | A gross | B gross | C gross | A net10 | B net10 | C net10 |
|---|---|---|---|---|---|---|---|
| INDUSTRY_ADJ_REVERSAL_5D | 0.60 | 0.70 | 0.72 | **0.87** | −0.58 | −0.47 | −0.27 |
| MAX_X_REVERSAL | 0.57 | 0.55 | 0.53 | 0.57 | −0.25 | −0.28 | −0.22 |
| REVERSAL_5D | 0.61 | 0.48 | 0.48 | 0.48 | −0.35 | −0.34 | −0.34 |
| ABNORMAL_VOLUME_REVERSAL | 0.77 | −0.12 | 0.05 | 0.36 | −1.58 | −1.60 | −1.39 |

`INDUSTRY_ADJ_REVERSAL_5D` is the cleanest example of the whole battery:
it clears a multiplicity-corrected gate in **all three universes** on
~1,250 observations, and it is unprofitable at 10bps everywhere. Its gross
Sharpe also RISES as the universe broadens (0.70 → 0.72 → 0.87), which is
the specification's small-cap-dependence warning pattern and is flagged
as such.

`ABNORMAL_VOLUME_REVERSAL` changes IC sign across universes (−0.0035,
+0.0004, +0.0036): **UNSTABLE**, rejected.

### The MAX effect corrects a local finding

On the local survivor-selected universe, `MAX_20` came out **inverted**
versus the published effect (Sharpe −0.79, implying lottery stocks
outperformed), and the local results document argued this was survivorship
— the high-volatility names that blew up were missing from a universe of
companies that survived to 2026.

On data that prices delisted companies, `MAX_20` shows **positive IC**
(+0.006 / +0.011 / +0.016), meaning low-lottery stocks outperform, which
is the documented direction. **The hypothesis was confirmed by better
data rather than by argument**, and it is the clearest single demonstration
in this project that the local universe was distorting results rather than
merely limiting them.

## 7. The benchmark, and the conclusion it forces

Equal-weight buy-and-hold of the same point-in-time universes, monthly
rebalance, no costs:

| Universe | CAGR | Sharpe | Max DD |
|---|---|---|---|
| A_large | 12.88% | **0.87** | −25.4% |
| B_core | 16.25% | **0.92** | −30.0% |
| C_broad | 17.20% | **0.94** | −31.2% |

Best long-only top-decile constructions, net of 10bps:

| | Best spec | Sharpe | CAGR |
|---|---|---|---|
| A_large | QUALITY_COMPOSITE / GROSS_PROFITABILITY | 0.79 | ~13% |
| B_core | QUALITY_COMPOSITE | 0.82 | 13.3% |
| Short-horizon family (B) | MAX_20 | 0.29 | 2.3% |

**Not one construction beats holding the universe — on either axis.** The
best long-only Sharpe in the entire battery (0.82) loses to the B_core
benchmark (0.92), and its CAGR of 13.3% loses to 16.25%. The broadest
universe has the best benchmark (0.94 Sharpe, 17.20% CAGR), so the
comparison gets harder, not easier, as the universe widens.

This is the same conclusion the local work reached, now on data that
prices delisted companies and carries point-in-time fundamentals. The
local version could be dismissed as an artifact of a survivor-selected
universe. This one cannot.

The benchmark series covers 155 months against the battery's 142, because
the battery discards the first year to accumulate the history its
momentum specifications need. The gap is not large enough to reverse a
0.10 Sharpe difference, but the comparison is not exactly like-for-like
and is stated rather than smoothed over.

## 8. What this battery actually established

1. **Several specifications clear a pre-declared, multiplicity-corrected
   significance gate.** `QUALITY_COMPOSITE` monthly in Universe A;
   `INDUSTRY_ADJ_REVERSAL_5D` and `MAX_X_REVERSAL` short-horizon in all
   three universes. This is the first time anything in this project has
   done that.
2. **None of them is profitable.** Every long-short construction is
   negative after costs. Every long-only construction loses to
   equal-weight buy-and-hold.
3. **Statistical significance and economic value came apart cleanly**, and
   the battery is only able to say so because it measured both. Reporting
   IC alone would have produced a triumphant and false result.
4. **The momentum family is null on honest data**, correcting a local
   result that survived costs only because the universe was
   survivor-selected.
5. **The MAX effect returns to its published direction**, confirming that
   the local inversion was survivorship.

**Nothing here is a tradable edge, and nothing here authorizes a trade,
allocation, policy change, deployment, or epoch action.**

## 9. Not run, and the reasons to doubt what was

**ALPHA 007 and 008 (PEAD) were not run.** They need an event study keyed
to announcement dates rather than a cross-sectional panel. Declared in the
pre-registration as not-run; repeated here so it is not mistaken for a
null result.

Reasons to doubt the significant findings, in the order I would attack
them:

1. **The fundamentals survivorship hole.** SIVB carried no fundamental
   data and FRC/SBNY carried `MarketCap == 0` on every appearance, so the
   three most famous failures of the period were absent from every
   universe. **A quality factor is precisely the signal that would have
   ranked them badly, and they are missing.** This is the strongest
   objection to the `QUALITY_COMPOSITE` result.
2. **Delisting returns are still not in the portfolio arithmetic**, and
   the retention probe showed screens eject failing companies before they
   die. The residual bias flatters every result.
3. **The p-values are censored at the bootstrap floor** (0.00005 with
   20,000 draws). Several results sit exactly there.
4. **Third look at the same hypotheses** (105 + 63 + 135 declared looks).
   Against the cumulative 303-look threshold (0.000165) the leading
   results still clear, but a third-look pass deserves discounting.
5. **Costs are assumptions.** No spread or market-impact data was used;
   10bps per side is a modelling choice, and the reversal family's
   verdict is sensitive to it in a way the monthly family's is not.
