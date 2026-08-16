# Three-universe alpha run — pre-registration (amendment)

Date: 2026-08-16
Author: Claude, at the owner's request
Amends: `docs/ALPHA_BATTERY_2026-08-15_PREREGISTRATION.md`
Status: **Frozen before any three-universe result was observed.**

The first battery's binding constraint was the universe: 104 hand-picked
survivors, where the minimum detectable effect (2-4% per trade) exceeded
any realistic alpha. The owner supplied a point-in-time universe
specification on 2026-08-16 to attack exactly that. This amendment
declares what will be run against it, and the correction, before results
exist.

## 1. What the new universe fixes, and what it does not

Built by `data/pit_universe.py` and `scripts/build_pit_universe_20260816.py`.

**Fixed:**

- **Point-in-time market cap.** Share counts come from the filing that
  reported them, with a 90-day publication lag, so a market cap at date T
  uses a share count a participant could have known at T. Verified: a Q1
  count is invisible on 1 April and becomes usable at the end of June.
- **CIK, not ticker, as the primary key.** A ticker change does not create
  a new company.
- **Cross-section size.** Roughly 2,500-3,500 names per date against 103,
  which moves the detection floor from 2-4% toward roughly 0.4-0.8% per
  trade — for the first time inside the range where real cross-sectional
  alpha lives.
- **Real Universe A/B/C splits, size buckets and liquidity terciles**,
  computed within each date from that date's market caps and ADV20.
- **Point-in-time fundamentals**, which makes ALPHA 009 testable for the
  first time. It was refused on 2026-08-15 for lack of exactly this.

**Not fixed, and this is the material limitation:**

- **Delisted securities still have no prices.** EDGAR supplies membership
  for companies that later died — SVB Financial appears in the CY2015Q1
  frame — but no available price source serves their bars. Measured
  attrition of US filers that no longer have a ticker: **65.5% for 2013,
  55.4% for 2016, 42.5% for 2019, 32.3% for 2022, 14.8% for 2025.**
- **No delisting returns.** A company leaving the universe leaves without
  a final return. This biases results UPWARD by an amount this data cannot
  reveal.
- **No point-in-time index membership.**
- **Prices remain yfinance adjusted closes**, not point-in-time.

The survivorship gap is now *measured on every rebalance date* rather than
assumed. It is not removed. **Early subperiods are the least trustworthy,
because that is where attrition is worst** — a strong 2010-2015 result is
a survivorship suspect first and a finding second.

## 2. Specifications to be run

Seven, chosen before seeing any three-universe result:

| Spec | Why it is included |
|---|---|
| MOM_6_1, MOM_12_1 | The only family that survived transaction costs |
| RESIDUAL_MOM_6_1, RESIDUAL_MOM_12_1 | Best IC information ratio; residualisation cut IC standard deviation from ~0.235 to 0.152 |
| REVERSAL_5D_hold5 | **Diagnostic.** Tests whether its null was a large-cap artifact |
| INDUSTRY_ADJ_REVERSAL_5D_hold5 | **Diagnostic.** Best gross Sharpe last time, destroyed by costs |
| GROSS_PROFITABILITY | Newly testable. `GrossProfit / Assets`, both point-in-time |

The two reversal specs are included **because** they were rejected. The
three-universe test exists to detect signals whose apparent alpha depends
on small or illiquid names, and reversal is the canonical case. Running
only the survivors would waste the diagnostic.

`GROSS_PROFITABILITY` uses the reported `us-gaap:GrossProfit` tag rather
than `Revenues - CostOfRevenue`, because the derived form has roughly half
the coverage. Companies not reporting it — largely banks and REITs — drop
out, which matches the standard treatment, since gross profitability is
not defined for financials.

QUALITY_COMPOSITE (ALPHA 010) and QUALITY_MOMENTUM (ALPHA 011) remain
deferred rather than rushed; they need four further tags whose coverage
has not been checked.

## 3. Declared look count and correction

7 specifications x 3 universes x 3 constructions (long-only 10%,
long-only 20%, long-short) = **63 looks.**

**Declared correction: Bonferroni at 63 tests, p < 0.05/63 = 0.000794.**

Cost scenarios are not counted: same hypothesis, different assumptions.
Size buckets, liquidity terciles, subperiods, regimes and capacity
scenarios are **descriptive only** and carry no significance claim.

**Cumulative honesty.** These specifications have now been examined twice:
105 looks on 2026-08-15 and 63 here, 168 in total. A nominal p-value that
lands just under the threshold on the *second* look at the same hypothesis
deserves discounting, not celebration. Where a result is close, both the
63-look and the 168-look thresholds (0.000794 and 0.000298) will be
reported.

## 4. Interpretation rule, declared in advance

Per the owner's specification, a signal that strengthens as the universe
broadens is **not** thereby robust. Classification is frozen now:

- **ROBUST** — works in A, B and C with reasonable degradation
- **CORE-DEPENDENT** — works in B and C, substantially weaker in A
- **SMALL-CAP DEPENDENT** — weak in A and B, strong mainly in C
- **ILLIQUIDITY-DEPENDENT** — returns concentrated in the lowest
  liquidity tercile
- **UNSTABLE** — changes direction across universe definitions
- **REJECT** — profitable only under unrealistic small-cap or illiquid
  assumptions

A large Universe C number with a weak Universe A number will be reported
as a **warning**, never as the headline.

## 5. Prior expectation

The first battery returned 21 nulls. The universe was the identified
cause, and it is now materially better, so a real effect has a genuine
chance of becoming visible. That cuts both ways: **the same improvement
that makes detection possible also makes survivorship distortion easier to
mistake for signal**, and the 2013 cross-section is still missing
two-thirds of the companies that existed.

Nothing in this run authorizes a trade, allocation, policy change,
deployment, or epoch action.

---

## 6. Corrections to this pre-registration, recorded after the first run

Two deviations from what is declared above. Both are recorded here rather
than by quietly restating the plan.

**GROSS_PROFITABILITY was declared and not run.** Section 2 lists seven
specifications; six were implemented. The point-in-time fundamentals panel
(`us-gaap:GrossProfit` over `Assets`) was verified as available -- roughly
2,400-2,900 companies per period -- but not built in this pass. The
declared look count of 63 is therefore **54 actual looks** (6 x 3 x 3),
and the Bonferroni threshold for what was actually run is
**0.05/54 = 0.000926**. The stricter declared threshold of 0.000794 is
retained, because loosening a pre-declared threshold after the fact is the
exact move the declaration exists to prevent.

**INDUSTRY_ADJ_REVERSAL_5D_hold5 is VOID in this run.** Its industry leg
groups by size bucket rather than sector, and in Universe A almost every
name is large-cap, so subtracting a constant per date left the ranks
unchanged: it returned results identical to plain reversal (IC 0.0030
against 0.0030). The specification is not refuted; it was not tested. It
needs real SIC sectors, which requires an EDGAR submissions ingest that
was not performed.

**A data-quality failure invalidated the first run entirely and it was
discarded, not reported.** The owner's specification requires excluding
securities with clearly erroneous price data; that screen was not
implemented. yfinance's back-adjustment of large reverse splits leaves
artifacts -- one name reads $275,000,000 in 2019, another has a price of
exactly zero -- producing single-day returns of up to 720,000,000%. The
symptom was diagnostic: rank IC was unaffected, because ranks ignore
outlier magnitude, while every portfolio number was destroyed, including
maximum drawdowns of -36.93 and -50.47 which are arithmetically
impossible. `data/pit_universe.usable_price_columns` now drops the
offending SERIES rather than clipping individual returns, because one
corrupted adjustment poisons every window that spans it. Portfolio
outcomes are additionally winsorised within each date; **rank IC is
deliberately computed on raw outcomes**, since winsorising before ranking
would misstate the ordering the signal actually produced.

---

## 7. Independent-review addendum (2026-08-16; not part of the frozen spec)

The implementation did not satisfy the document's “point-in-time universe”
claim. SEC facts were made available on a guessed date instead of their actual
filing date; adjusted prices were incompatible with raw share counts for
market-cap screens; current ticker identity remained; and the reported 70.2%
number was a current-ticker/price coverage gap among candidate filers, not the
fraction of otherwise-eligible securities lost to survivorship. In addition,
the latest size bucket was applied to all history for the residual and
industry-adjusted signals. The committed results and audit artifacts are
invalidated. Reviewed code now refuses the industry-dependent specifications
until point-in-time industry data exists and labels the broader panel
non-point-in-time; all results require a clean rerun.
