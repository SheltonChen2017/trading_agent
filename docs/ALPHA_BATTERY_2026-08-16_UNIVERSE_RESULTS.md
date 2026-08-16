# Three-universe alpha results

Date: 2026-08-16
Specification: `docs/ALPHA_BATTERY_2026-08-16_UNIVERSE_PREREGISTRATION.md`
(frozen before the run; deviations recorded in its section 6)
Status: **Exploratory. Nothing confirmed. No trade, allocation or policy
change is authorized by anything here.**

Panel: 4,329 sessions x 3,793 tickers after the data-quality screen
dropped 725 corrupt series. Universe medians per rebalance: **A 409,
B 1,420, C 1,810 names.**

Declared Bonferroni threshold: **p < 0.000794**.

## Headline: nothing clears the threshold, but the failure modes are now
legible

| Alpha | A net | B net | C net | A IC | B IC | C IC | IC p (best) | Honest class |
|---|---|---|---|---|---|---|---|---|
| MOM_6_1 | **0.27** | 0.02 | 0.00 | 0.0068 | 0.0067 | 0.0096 | 0.226 | LARGE-CAP DEPENDENT |
| MOM_12_1 | **0.29** | 0.04 | 0.08 | 0.0161 | 0.0171 | 0.0191 | 0.049 | LARGE-CAP DEPENDENT |
| RESIDUAL_MOM_6_1 | **0.39** | −0.11 | 0.00 | 0.0179 | 0.0101 | 0.0137 | 0.046 | UNSTABLE |
| RESIDUAL_MOM_12_1 | **0.34** | −0.17 | −0.06 | 0.0187 | 0.0130 | 0.0168 | 0.068 | UNSTABLE |
| REVERSAL_5D_hold5 | −0.52 | −0.28 | −0.07 | 0.0079 | 0.0093 | 0.0120 | 0.004 | REJECT (cost) |
| INDUSTRY_ADJ_REVERSAL | −0.52 | −0.27 | −0.07 | 0.0079 | 0.0094 | 0.0121 | **0.0015** | **VOID** |

Net Sharpe is long-short after 10bps per side.

## Correction to my own classifier

The script labelled MOM_6_1 and MOM_12_1 **ROBUST**. That label is wrong
and the code that produced it is too lenient: it tested `a > 0 and b > 0
and c > 0`, so net Sharpes of 0.27 / 0.02 / 0.00 satisfied it. The
specification defines ROBUST as working in all three "with reasonable
degradation", and 0.02 is not working. Corrected by hand above to
**LARGE-CAP DEPENDENT**, a category the specification does not contain
because it anticipated the opposite failure.

## Result 1 — reversal is the interpretation rule's exact warning case

Gross long-short Sharpe rises monotonically as the universe broadens:

| | A_large | B_core | C_broad |
|---|---|---|---|
| **Gross** Sharpe | 0.21 | 0.55 | **0.77** |
| Mean IC | 0.0079 | 0.0093 | 0.0120 |
| **Net @10bps** | −0.52 | −0.28 | −0.07 |
| **Net @25bps** | −1.61 | −1.51 | −1.35 |
| Turnover | 0.68 | 0.67 | 0.66 |

This is precisely the pattern the owner's specification says to flag: an
alpha that materially strengthens only once smaller and less liquid
securities are admitted. Its best IC p-value (0.0040 in C) is also its
broadest universe.

**And it is still unprofitable everywhere after costs.** Gross 0.77
becomes −0.07 at 10bps and −1.35 at 25bps on 66% turnover per five-day
rebalance. The signal is real enough to see and too small to keep.

Two independent reasons to reject it, which is a stronger conclusion than
either alone: it is concentrated where tradability is worst, and it does
not survive the cost of trading it.

## Result 2 — momentum inverts the published pattern

Momentum here is a **large-cap** effect, strongest in Universe A and
absent in B and C. Published momentum is usually stronger in smaller
names. The attribution inside Universe B agrees, in mean decile spread:

| Spec | large | mid | small |
|---|---|---|---|
| MOM_6_1 | +0.411% | +0.416% | +0.116% |
| MOM_12_1 | +0.569% | +0.554% | +0.170% |
| RESIDUAL_MOM_6_1 | +0.575% | +0.559% | +0.111% |
| RESIDUAL_MOM_12_1 | +0.337% | +0.164% | **−0.581%** |

Small caps contribute a quarter to a third of what large and mid do, and
`RESIDUAL_MOM_12_1` is outright negative there.

**I do not think this is a discovery.** The most likely explanation is
survivorship: the small-cap end of this universe is where attrition is
worst, so the small-cap names present are the ones that survived, and the
momentum losers among them — the names that would have kept falling and
delisted — are absent. Their absence removes exactly the observations that
make the short leg pay. A finding that contradicts the literature in the
direction of the known bias in the data is a bias result until proven
otherwise.

## Result 3 — long-only remains worse than holding the universe

Universe B, top decile, net of 10bps, against equal-weight buy-and-hold of
the same universe:

| | Sharpe | CAGR | Max DD |
|---|---|---|---|
| **Benchmark: equal-weight B** | **0.73** | **11.95%** | **−30.4%** |
| MOM_12_1 | 0.53 | 10% | −45% |
| RESIDUAL_MOM_12_1 | 0.51 | 9% | −40% |
| MOM_6_1 | 0.48 | 9% | −47% |
| REVERSAL_5D_hold5 | 0.27 | 4% | −63% |

Every long-only construction is **worse than the benchmark on all three
axes**. Unlike yesterday, where the best construction at least matched the
benchmark's Sharpe, here nothing does.

Benchmarks for the other two universes: A_large 11.86% CAGR at Sharpe
0.84; C_broad 11.63% at 0.70.

## Result 4 — yesterday's benchmark was inflated by selection

Yesterday's 103 hand-picked names returned **19.15% CAGR at Sharpe 1.18**.
The same calculation on a real point-in-time universe returns **11.95% at
Sharpe 0.73**.

That gap — over seven points of annual return — is the size of the
selection effect embedded in a hand-picked survivor list. Nothing about
the market changed between the two runs; only the universe did. It is the
clearest single argument in this project for why the universe work
mattered more than any additional signal variant would have.

## Result 5 — the p-values moved, and that is a caution

Yesterday, on 103 names, momentum IC p-values sat at 0.14-0.29. Today, on
1,400, `MOM_12_1` reaches 0.049 in C and `REVERSAL` reaches 0.004. The
larger cross-section did increase power as predicted.

**None of it clears 0.000794.** And the improvement cuts both ways: the
same power that would reveal a real effect also sharpens a biased one, and
the biases here (survivorship, no delisting returns) both push in the
direction of making a signal look better than it is.

## Verdicts

| Alpha | Class | Call |
|---|---|---|
| MOM_12_1 | LARGE-CAP DEPENDENT | **MODIFY** — the only spec with a positive net Sharpe in its strongest universe and a coherent IC ladder; not tradable at 0.29 |
| MOM_6_1 | LARGE-CAP DEPENDENT | **MODIFY** |
| RESIDUAL_MOM_6_1 / _12_1 | UNSTABLE | **DROP for now** — sign flips between A and B; the industry leg is a size proxy, so the specification has not had a fair test |
| REVERSAL_5D_hold5 | REJECT | **DROP** — strengthens only as the universe broadens, negative at every cost level |
| INDUSTRY_ADJ_REVERSAL | **VOID** | **RETEST** — not refuted, not tested; needs real SIC sectors |
| GROSS_PROFITABILITY | not run | **PENDING** — declared, not implemented |

## What is still wrong with this test

- **Survivorship remains, median 70.2% of eligible filers unpriceable.**
  Measured now, not removed. It biases upward and it is worst exactly
  where the momentum result is weakest, which is why Result 2 reads as a
  bias signature.
- **No delisting returns.** Names leave without a final return.
- **The industry proxy is size buckets**, which voided one specification
  outright and weakens both residual-momentum specs.
- **No exchange filter.** OTC exclusion is by inference, not by venue.
- **Prices are adjusted closes**, not point-in-time.
- 725 series were dropped as corrupt. That screen is a blunt instrument
  and will have removed some legitimate securities alongside the
  artifacts.

## The next thing worth doing

Not more alphas. In order:

1. **Ingest SIC codes and exchange venue** (~4,500 EDGAR requests, about
   ten minutes). This un-voids one specification, gives both residual
   momentum specs a real industry leg, and implements the venue exclusion
   the specification asks for.
2. **Build the fundamentals panel** and run GROSS_PROFITABILITY, which is
   the one genuinely new alpha this universe unlocked.
3. **Only then** revisit whether any signal deserves further work.
