# Alpha battery — results

Date: 2026-08-15
Author: Claude
Specification: `docs/ALPHA_BATTERY_2026-08-15_PREREGISTRATION.md` (frozen
and committed as `db0045a` before the run)
Runner: `scripts/run_alpha_battery_20260815.py`
Status: **INVALIDATED BY INDEPENDENT REVIEW (2026-08-16).** The submitted
bootstrap used 2,000 draws, whose smallest attainable p-value is 1/2,001 =
0.000500 -- above the declared 0.000476 threshold. The test therefore could
not possibly clear its own gate. Long-short turnover also compared only the
set of held names, so a name moving directly from long to short registered no
trade and cost was understated. Point estimates remain a preserved record of
the original exploratory run, but its significance and net-cost conclusions
must not be used. A clean rerun is required. Nothing here authorizes any trade,
allocation, or policy change.

## Headline

**Zero of 21 executed specifications clear the pre-declared Bonferroni
threshold of p < 0.000476.** The closest is
`INDUSTRY_ADJ_REVERSAL_3D_hold2` at **p = 0.00050**, which misses — and
which loses money at every non-zero transaction cost anyway.

This is the outcome the pre-registration predicted, and it is consistent
with the project's eleven prior signals, none of which were confirmed.

## Data actually used

- 4,200 sessions x 103 tickers, **2009-12-02 to 2026-08-14** (16.7 years).
- yfinance adjusted closes. `point_in_time_data=false`.
- `REMX` excluded as an ETF. Fundamentals-dependent alphas (009, 010, 011)
  not run — see the pre-registration.
- Entry lag one full session, verified: `MOM_12_1` reads `t-21 / t-252`,
  forward returns run close `t+1` to `t+1+h`.

## The benchmark, without which none of this is interpretable

Equal-weight universe, monthly rebalance, no costs:

| | |
|---|---|
| CAGR | **19.15%** |
| Annualised volatility | 16.03% |
| **Sharpe** | **1.18** |
| Max drawdown | −24.3% |
| Win rate | 68% |

Sixteen years of holding 103 companies that all survived to 2026. **Any
long-only result must be read against this line**, and it is inflated by
survivorship: the failures are not in the universe.

## Result 1 — every long-only construction is market beta

Top-decile long-only, net of 10bps:

| Spec | Sharpe | CAGR | Max DD |
|---|---|---|---|
| **Benchmark (equal-weight hold)** | **1.18** | **19.2%** | **−24.3%** |
| RESIDUAL_MOM_6_1 | 1.27 | 33% | −33% |
| MOM_6_1 | 1.24 | 35% | −30% |
| RESIDUAL_MOM_12_1 | 1.20 | 32% | −31% |
| MOM_12_1 | 1.19 | 33% | −29% |
| MOM_9_1 | 1.12 | 30% | −35% |
| INDUSTRY_ADJ_REVERSAL_3D_hold10 | 0.95 | 23% | −40% |
| MAX_20_alone | 0.54 | 7% | −33% |

The higher CAGRs buy exactly proportional volatility. The best Sharpe in
the battery (1.27) beats buy-and-hold by 0.09 while carrying **9 points
more drawdown**. **No long-only construction is worth its complexity.**
This repeats the project's standing pattern: a result that looks good on
return and loses once risk is priced.

## Result 2 — the entire reversal family is destroyed by costs

Long-short Sharpe as costs rise:

| Spec | Turnover | 0bps | 5bps | 10bps | 25bps |
|---|---|---|---|---|---|
| INDUSTRY_ADJ_REVERSAL_3D_hold2 | 0.63 | **0.71** | −0.06 | −0.83 | −3.14 |
| INDUSTRY_ADJ_REVERSAL_5D_hold2 | 0.52 | **0.76** | 0.14 | −0.48 | −2.34 |
| REVERSAL_5D_hold2 | 0.53 | 0.38 | −0.07 | −0.52 | −1.88 |
| ABNORMAL_VOLUME_REVERSAL | 0.74 | 0.11 | −0.25 | −0.60 | −1.67 |
| MAX_20_x_REVERSAL | 0.74 | 0.16 | −0.23 | −0.63 | −1.83 |

Gross Sharpe up to 0.76 becomes **negative at 5-10bps** — a cost level
below what a retail account actually pays. Turnover of 0.52-0.74 per
rebalance on a **daily** schedule is the mechanism.

**Flagged exactly as the brief asked**: apparent profitability that
disappears under reasonable execution. The only reversal spec still
positive at 10bps is `INDUSTRY_ADJ_REVERSAL_5D_hold10` at **0.01**, which
is zero.

## Result 3 — momentum is the only family that survives costs, and it is
still not significant

| Spec | Mean IC | IC IR | %positive | IC p | L/S net@10bps |
|---|---|---|---|---|---|
| MOM_3_1 | −0.0006 | −0.003 | 50% | 0.969 | −0.16 |
| MOM_6_1 | 0.0155 | 0.067 | 54% | 0.288 | 0.34 |
| MOM_9_1 | 0.0202 | 0.081 | 54% | 0.189 | 0.22 |
| MOM_12_1 | 0.0239 | 0.099 | 54% | 0.137 | 0.31 |
| RESIDUAL_MOM_6_1 | 0.0238 | **0.157** | **57%** | 0.028 | **0.41** |
| RESIDUAL_MOM_12_1 | 0.0164 | 0.102 | 51% | 0.215 | 0.39 |

Two things here are genuinely encouraging and still insufficient:

**The parameter ladder is monotone.** IC rises 3 → 6 → 9 → 12 months
(−0.0006, 0.0155, 0.0202, 0.0239). That is the smooth parameter behaviour
the brief asks for and the opposite of a lone lucky spike. The 3-month
variant being flatly null also matches the published story that the
skip-month effect needs a longer formation window.

**Residual momentum does what it is supposed to do.** Its IC standard
deviation is **0.152 versus 0.231-0.240** for raw momentum — stripping
market and industry return genuinely removes noise rather than signal, and
`RESIDUAL_MOM_6_1` posts the battery's best IC information ratio (0.157)
and best cost-adjusted long-short Sharpe (0.41). That is an economically
coherent improvement, not a data artifact.

**It is still 59x away from the corrected threshold** (p = 0.028 versus
0.000476 required), and a Sharpe of 0.41 is not a strategy.

## Result 4 — no subperiod stability

Long-short net@10bps Sharpe:

| Spec | 2010-14 | 2015-19 | 2020-22 | 2023-now |
|---|---|---|---|---|
| MOM_6_1 | −0.22 | 1.11 | 0.03 | 0.66 |
| MOM_12_1 | −0.12 | 0.40 | 0.07 | 0.87 |
| RESIDUAL_MOM_6_1 | 0.40 | 0.66 | 0.09 | 0.41 |
| RESIDUAL_MOM_12_1 | 0.49 | 0.04 | −0.51 | 1.21 |
| INDUSTRY_ADJ_REVERSAL_3D_hold2 | −0.83 | −1.84 | −0.34 | −0.62 |

The swings dwarf the means. `RESIDUAL_MOM_12_1` runs from −0.51 to +1.21.
**Only `RESIDUAL_MOM_6_1` keeps the same sign in all four periods**, which
is the single most durable observation in this battery — and it is one
signal out of 21 across four windows, which is roughly what chance
produces.

Walk-forward on the pre-declared split:

| Spec | train 10-18 | validation 19-22 | OOS 23-now |
|---|---|---|---|
| MOM_6_1 | 0.30 | 0.19 | 0.66 |
| MOM_12_1 | 0.20 | 0.06 | 0.87 |
| RESIDUAL_MOM_6_1 | 0.69 | 0.04 | 0.41 |
| RESIDUAL_MOM_12_1 | 0.43 | −0.70 | 1.21 |

Momentum's best window is the final out-of-sample block. **I am treating
that as a warning, not a result**: ~40 months is far too short to carry a
Sharpe estimate, and 2023-2026 was a strong, narrow, momentum-friendly
market. Nothing was tuned on the training period, so this is not
overfitting — it is a regime, and regimes revert.

## Result 5 — the volume-conditioned result is a small-sample mirage

ALPHA 005 asked whether reversal behaves differently under abnormal
volume. It does, apparently:

| Bucket | Mean IC | Dates | p |
|---|---|---|---|
| z < 0 | 0.0032 | 775 | 0.698 |
| 0 ≤ z < 1 | 0.0116 | 476 | 0.345 |
| **1 ≤ z < 2** | **0.0558** | **49** | 0.333 |
| z ≥ 2 | 0.0276 | 26 | 0.649 |

The `1 ≤ z < 2` bucket has an IC **4.8x the full-sample reversal IC** —
easily the largest effect in the entire battery. It rests on **49 dates**,
its p-value is 0.333, and its positive-date fraction is 51%, which is a
coin flip. The z ≥ 2 bucket has 26 dates and a positive-date fraction of
**42%**, i.e. the mean is carried by a few large observations.

**This is the exact shape the brief warned about**, and it is why the
conditional buckets were pre-declared as descriptive rather than
significance-bearing. A researcher who went looking for a subgroup after
seeing a null headline would have found this one and reported it.

## Result 6 — MAX_20 comes out backwards, and survivorship is the
likely reason

`MAX_20_alone` has a long-short Sharpe of **−0.79** gross, meaning the
inverse — buying the highest-lottery names — would have paid. The
published MAX effect points the other way.

The explanation is almost certainly the universe. On 103 names that all
survived to 2026, the high-volatility cohort is the *survivors* of a
high-volatility cohort, and the ones that blew up are absent. That is
survivorship bias generating an inverted factor, not a discovery. It is
the cleanest illustration in this battery of why the universe limitation
is not a footnote.

## Summary table and verdicts

| Alpha | Mean IC | IC IR | Gross LS Sharpe | Net@10 | OOS | Cost sensitivity | Verdict |
|---|---|---|---|---|---|---|---|
| MOM_3_1 | −0.0006 | −0.003 | −0.06 | −0.16 | — | low | **REJECT** |
| MOM_6_1 | 0.0155 | 0.067 | 0.41 | 0.34 | 0.66 | low | **WEAK** |
| MOM_9_1 | 0.0202 | 0.081 | 0.26 | 0.22 | — | low | **WEAK** |
| MOM_12_1 | 0.0239 | 0.099 | 0.35 | 0.31 | 0.87 | low | **WEAK** |
| RESIDUAL_MOM_6_1 | 0.0238 | 0.157 | 0.51 | 0.41 | 0.41 | low | **WEAK (best of batch)** |
| RESIDUAL_MOM_12_1 | 0.0164 | 0.102 | 0.45 | 0.39 | 1.21 | low | **WEAK** |
| REVERSAL_5D (all holds) | ≤0.0120 | ≤0.055 | ≤0.38 | ≤−0.21 | neg | **fatal** | **REJECT** |
| INDUSTRY_ADJ_REVERSAL (all 9) | ≤0.0111 | ≤0.085 | ≤0.76 | ≤0.01 | neg | **fatal** | **REJECT** |
| ABNORMAL_VOLUME_REVERSAL | 0.0014 | 0.009 | 0.11 | −0.60 | neg | **fatal** | **REJECT** |
| MAX_20_alone | −0.0109 | −0.043 | −0.79 | −0.98 | — | low | **REJECT (inverted)** |
| MAX_20_x_REVERSAL | 0.0035 | 0.020 | 0.16 | −0.63 | neg | **fatal** | **REJECT** |
| ALPHA 007/008 PEAD | not run this pass | | | | | | **deferred** |
| ALPHA 009/010/011 | **not runnable** | | | | | | **REFUSED — no point-in-time fundamentals** |

**Nothing is rated STRONG or PROMISING.** Under the declared correction
that is the only defensible classification.

## Answers to the ten closing questions

1. **Strongest individual alpha**: `RESIDUAL_MOM_6_1` — best IC IR
   (0.157), best cost-adjusted long-short Sharpe (0.41), lowest IC
   dispersion in the momentum family. Strongest of a null batch.
2. **Most stable**: `RESIDUAL_MOM_6_1`, the only spec holding one sign
   across all four subperiods.
3. **Highest IC**: `MOM_12_1` (0.0239) and `RESIDUAL_MOM_6_1` (0.0238),
   indistinguishable from each other.
4. **Best net Sharpe after costs**: `RESIDUAL_MOM_6_1` at 0.41.
5. **Least correlated**: the reversal family is structurally orthogonal to
   the momentum family (opposite horizons, opposite sign conventions), but
   since the reversal family is unprofitable net of costs, its
   diversification value is unusable.
6. **Redundant**: `MOM_9_1` and `MOM_12_1` are near-duplicates; the nine
   industry-adjusted reversal variants are one signal with three knobs.
7. **Fail out of sample**: every reversal spec — negative in the
   out-of-sample block and negative net of costs in all four subperiods.
8. **Work only in small caps or illiquid names**: **cannot be answered.**
   There are no small caps and no illiquid names in this universe. Given
   that published short-term reversal is concentrated in exactly those
   segments, the null reversal result here is what theory predicts for
   large caps and is **not** evidence against reversal generally.
9. **Survive realistic costs**: only the momentum family (6/9/12-month and
   both residual variants). Everything else dies at 5-10bps.
10. **Best diversified portfolio**: none is supportable. Combining signals
    that are individually indistinguishable from noise produces a
    combination indistinguishable from noise. ALPHA 012 was therefore not
    constructed: the pre-registration conditions it on inputs that show
    reasonable out-of-sample behaviour, and none qualified.

## KEEP / MODIFY / DROP

| Alpha | Call | Reason |
|---|---|---|
| MOM_12_1, MOM_6_1 | **MODIFY** | Monotone parameter behaviour and cost-survival justify retesting on a universe that can actually detect a 1-2% effect. Not tradeable here |
| RESIDUAL_MOM_6_1 | **MODIFY** | Same, and it is the most economically coherent result in the battery — residualisation demonstrably cut IC variance by a third |
| MOM_3_1, MOM_9_1 | **DROP** | Null and redundant respectively |
| REVERSAL_5D (all) | **DROP** | Negative net of costs in every period |
| INDUSTRY_ADJ_REVERSAL (all 9) | **DROP** | Best gross Sharpe in the battery, unprofitable at 5bps |
| ABNORMAL_VOLUME_REVERSAL | **DROP** | Null, and the conditional buckets are small-sample artifacts |
| MAX_20 (all 3) | **DROP** | Inverted sign, most plausibly survivorship |
| ALPHA 009/010/011 | **DROP until data exists** | Not a modelling gap; needs point-in-time fundamentals |

## What would actually change these answers

Not more signal variants on this universe. The binding constraint is
measurement, not ideas: this universe's minimum detectable effect is
2-4% per trade, so a real 0.5% cross-sectional edge is invisible here by
construction. That is the same ceiling recorded on 2026-08-03, and this
battery is a 21-specification confirmation of it.

In order of expected value:

1. **A survivorship-free universe with historical constituents.** Without
   it, results like the inverted MAX effect are uninterpretable.
2. **Point-in-time fundamentals**, which unlocks three of the twelve
   alphas and the entire quality dimension.
3. **More names, not more signals.** Statistical power scales with the
   cross-section; 103 correlated large caps is the ceiling here.

## Honest limitations

- Survivorship bias is present, material, and demonstrably distorting at
  least one result.
- Prices are adjusted closes, not point-in-time.
- The industry proxy is 16 hand-assigned baskets, not GICS.
- Costs are assumptions; no spread or market-impact data exists here.
- PEAD (007, 008) was specified and not executed in this pass; the
  earnings path needs per-event alignment rather than the cross-sectional
  panel used here, and I would rather report it as not-run than ship a
  rushed event study.
- No result here has prospective out-of-sample evidence. Every number is
  retrospective.
