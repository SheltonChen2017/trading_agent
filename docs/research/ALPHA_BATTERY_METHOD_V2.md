# Alpha battery — Method V2

Date: 2026-08-16
Author: Claude
Status: **Frozen methodology. Written and committed before any Method V2
result was observed, local or cloud. Re-audited 2026-08-17; no valid Method
V2 result exists and a clean counter-reviewed QC rerun is still pending.**
Supersedes: the methodology used in the 2026-08-15 and 2026-08-16 battery
result files, whose generated narratives/artifacts were invalidated and then
removed from active docs at the owner's direction. Their exact hashes and
dispositions remain in `docs/alpha-result.md` and Git history.
Incorporates: `docs/Review/REVIEW_2026-08-16_ALPHA_BATTERY.md` (ABR-001..007) and
Codex's 2026-08-16 recommendation on QuantConnect.

## 0. Why V2 exists

Two research rounds produced numbers. Independent review found five P2 and
two P3 defects, and **every reported result is invalid**. The defects were
not in the ideas; they were in the measurement. Better data does not fix
any of them, which is the whole argument for freezing a corrected method
before moving to a better data environment.

The most instructive one:

**ABR-001 — the headline was a tautology.** With 2,000 bootstrap draws and
the add-one estimator, the smallest obtainable p-value is
`1/2001 = 0.00049975`. Round 1's gate was `0.05/105 = 0.00047619`. **No
specification could ever have cleared it, whatever the data said.** The
reported "zero of 21 clear the threshold" measured the resolution of my
bootstrap, not the market.

This is the same shape as the two Stage 3 trim defects earlier in the same
week: a refusal that always fires is indistinguishable from a careful one.
There it produced a blocked workflow, which was visible. Here it produced a
plausible research finding, which was not. **A statistical gate must be
proven reachable before it is used**, and V2 makes that an assertion rather
than an assumption.

Round 2's gates (0.00079, 0.00093) were reachable, so its "nothing clears"
was a real measurement — invalidated instead by ABR-002/003/005.

## 1. Corrections that are binding in V2

### 1.1 The significance gate must be provably reachable

Before any specification is evaluated:

```
min_achievable_p = 1 / (draws + 1)
assert min_achievable_p < alpha / declared_looks
```

If it fails, raise. Never run. Required draws for a Bonferroni gate at
`n` looks is at least `n/alpha + 1`; for 105 looks at 0.05 that is 2,101,
so V2 uses **20,000 draws** to leave a full order of magnitude of headroom
and to stabilise the estimate near the tail.

The assertion is a hard refusal, not a warning. A warning would be read
past.

### 1.2 Turnover is drift-aware capital turnover, not name churn

V1 compared the SET of names held. Two failures followed: a security
flipping from long to short stayed in the set and registered **zero**
turnover, and an equal-weight book that drifts between rebalances needs
real trading to return to equal weight, which the set comparison cannot
see. Both understate cost, and every net-Sharpe and cost-destruction claim
depended on them.

V2 computes turnover from **signed target weights**:

```
turnover_t = 0.5 * sum_i | w_i,t - w_i,t-1_drifted |
w_i,t-1_drifted = w_i,t-1 * (1 + r_i) / (1 + r_portfolio)
```

A long-to-short flip now costs the full round trip. Drift back to equal
weight is charged. The one-half prevents double counting a switch.

**Status: ABR-002 was closed for the flip half and left open for the drift
half.** Codex's correction introduced signed weights, which fixes the
side-flip case its docstring describes, but it compares last period's
TARGET weights to this period's targets without carrying the old targets
forward through their own returns. Demonstrated on the merged code: four
equal-weight names where one doubles drift to 40/20/20/20, and restoring
them to 25 each is **15% of the book charged as zero**. Both halves
understate cost independently, so closing one does not close the finding.
`drift_weights()` and two regression tests close the remainder; one
mutation, detected.

### 1.3 Market cap must not mix adjusted and unadjusted units

V1 multiplied a **split-adjusted** historical close by an **unadjusted**
reported share count. After a 1:10 split the adjusted price is a tenth of
the traded price while the filed share count is pre-split, so the product
is wrong by the split factor in the direction that changes membership.

V2 requires both legs in the same basis: unadjusted close with as-reported
shares, or adjusted close with adjusted shares. Where the provider supplies
market cap directly as a point-in-time field, use that and skip the
multiplication.

### 1.4 Availability comes from the filing date, never a guessed lag

V1 assumed period end plus 90 days. The SEC frames payload carries the
actual `filed` date and V2 reads it. A guess is only defensible when the
value is unavailable; here it was present and unused.

### 1.5 Survivorship must be measured on the ELIGIBLE universe

The "70.2% survivorship loss" counted historical SEC filers **before**
price, market-cap, ADV, history, venue and security-type screens could be
applied. Most of those filers would never have entered any universe. It is
a **current-ticker coverage gap**, not a measured survivorship loss on the
investable set, and V2 reports it under that name.

The honest version requires knowing which delisted companies would have
passed the screens, which needs their prices — the very thing that is
missing. So on the local dataset this quantity is **bounded, not
measured**, and V2 says so rather than quoting a number that sounds
measured.

### 1.6 Industry classification must be point-in-time and real

V1 used each ticker's **latest** size bucket as an industry label across
all history. That is two defects: size is not industry, and using the
latest value historically **leaks future capitalization**. Any V1 result
depending on it — both residual-momentum specs and the industry-adjusted
reversal — is void, not merely weak.

V2 requires a genuine point-in-time industry classification. Where none is
available, the specification is **not run**. It is not approximated.

### 1.7 Residual momentum uses one joint regression

V1 ran two sequential univariate rolling regressions, market first and
industry on the residual, with betas shifted 21 sessions. That is not the
textbook specification and I could not defend the shift under review.

V2 estimates market and industry loadings **jointly** on a rolling window
that ends strictly before the measurement window opens, and cumulates the
residual over the measurement window only.

The 2026-08-17 full audit found the older local runner still implemented the
rejected sequential calculation and included each stock inside its own peer
average. Correction `1e2b631` uses a leave-one-out peer factor and one frozen
joint regression. This repairs executable methodology; it does
**not** rehabilitate the old local result, whose static latest basket
classifications are not point-in-time and remain prohibited by section 1.6.

### 1.8 Classification thresholds are magnitude-based

V1's classifier called net Sharpes of 0.27 / 0.02 / 0.00 "ROBUST" because
it tested only for positive signs. V2 requires a minimum magnitude and a
bounded degradation ratio between universes, and adds the
**LARGE-CAP DEPENDENT** category that V1's vocabulary lacked because it
anticipated only the opposite failure.

### 1.9 Corrections already merged, and what remained

`docs/Review/REVIEW_2026-08-16_ALPHA_BATTERY.md` closed ABR-001 through ABR-007
in code before this document was written. Verified on the merged tree
rather than assumed: bootstrap draws now default to 10,000 (making the
round-1 gate reachable), turnover uses signed weights, EDGAR facts read
the actual `filed` date, market cap uses unadjusted price, the classifier
no longer calls near-zero results ROBUST, and the runner refuses a
pre-correction membership cache. Seven of Codex's tests pin these.

**One remainder was found while verifying: the drift half of ABR-002,
recorded in 1.2 above.** Finding a partial fix is the expected outcome of
counter-review and is not a criticism of the review; it is what the second
pass is for.

### 1.10 Every real-market run is a counted look

Cloud backtests are counted the same as local runs. A smoke test that
reports no alpha statistic is exempt and must be **incapable** of reporting
one, not merely silent about it.

## 2. QuantConnect: replication backend, not data download

Adopted from Codex's recommendation, and it is a better framing than mine.

**QuantConnect is used as an INDEPENDENT REPLICATION of a corrected local
implementation, not as a replacement for it.** If a from-scratch LEAN
implementation and the corrected local implementation reach the same
conclusion, that is far stronger evidence than either alone — and the two
implementations sharing an author is precisely why the agreement is worth
testing.

### 2.1 The categorical claim is withdrawn

`research/quantconnect.py` currently describes QuantConnect as
"survivorship-bias-free, point-in-time-corrected". **That is too
categorical and V2 withdraws it.** Specific datasets provide those
protections, and only if the algorithm actually uses the dynamic universe,
the Security Master, historical fundamentals, the correct normalization
mode, and proper delisting handling. A LEAN algorithm can reintroduce
survivorship bias in a dozen ways — a hardcoded symbol list being the
easiest.

The protections must be **demonstrated by the algorithm**, not inherited
from the platform's reputation.

### 2.2 Ordering, which is not negotiable

1. Method V2 frozen and committed. **This document.**
2. Corrected local implementation, reviewed, with the gate-reachability
   assertion and drift-aware turnover under test.
3. LEAN implementation written independently against this same frozen
   method.
4. **Technical smoke test only** — confirms data plumbing, universe size,
   and delisting handling; reports no IC, no Sharpe, no alpha statistic.
5. Review and commit both implementations before any cloud alpha result is
   observed.
6. Run the frozen A/B/C battery **once**.
7. Retrieve aggregate results only. QuantConnect's licence forbids
   exporting raw data, and this project must not convert it into local
   frames.
8. Commit cloud results separately, then compare against the corrected
   local results as a replication test.

Pressing Run before step 5 forfeits the replication argument, because a
method adjusted after seeing cloud output is no longer independent of it.

## 3. What V2 does not fix

- **Delisting returns** remain unavailable locally. On QuantConnect they
  are available and must be shown to be in use.
- **No prospective evidence.** Every V2 result is retrospective. Nothing in
  this document moves any signal toward authorization.
- **The local dataset stays survivorship-affected.** V2 changes how that is
  reported, not whether it is true.

## 4. Standing prohibition

Nothing in Method V2, and no result produced under it, authorizes a trade,
a proposal, an allocation change, a policy change, a deployment, or an
epoch action. ML and LLM output remain observation only.
