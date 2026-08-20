# Analyst-Consensus ETF Rotation (ACER) — research program plan

Status: **DRAFT — owner-directed replacement for the Strong-Buy portfolio
program (2026-08-20). Not frozen, not scheduled, not implemented.** The owner
adopted this direction as the priority-1 research program; that is a
*sequencing* decision. No signal definition, threshold, gate, universe, or
cost assumption below acquires authority until an ACER-0 freeze, which is a
separate owner act.

Source specification: `docs/reference/analyst-consensus-etf-strategy.pdf`,
SHA-256 `3700ab4bb64dfd6e29e5f8bbc2b7e3dd3fa089050b25cbb5e315450a8d86cf23`,
138,347 bytes, supplied by the owner 2026-08-20. That document is the design
narrative; this file is the operative contract shape used by this repository,
and where the two differ this file governs.

**Nothing here authorizes** a QuantConnect run, a data purchase, a broker
action, a scheduled task, a deployment, an epoch action, or any live or paper
order. ML/LLM boundaries in `CLAUDE.md` are unchanged: no research artifact
acquires execution authority, and any eventual trading still goes through the
reviewed execution kernel with its typed approval, policy fingerprinting,
kill switch, and reconciliation.

---

## 1. The question

Do recent **stock-level analyst recommendation revisions**, aggregated through
**point-in-time ETF constituent weights** with breadth and coverage
adjustments, predict future ETF returns after controlling for momentum,
earnings-related information, common risk exposures, overlapping holdings, and
realistic trading costs — and only if they do, can regime-aware inverse or
leveraged implementation improve risk-adjusted outcomes without unacceptable
path dependence or tail risk?

The order of that question is binding: unlevered bullish rotation first, then
bearish implementations, then leverage overlays. Leverage is a portfolio
overlay, never part of the signal.

## 2. Honest prior, stated before any result is seen

This section exists because this repository requires related prior evidence to
be disclosed in advance, and because the source document does not carry it.

- This project has produced **zero confirmed predictive signals**. Eleven
  local candidate signals were null; the Stage 0 battery (180 cells) and
  Stage 1 (24 cells) closed **null on every beta-free cell** (`A-001`,
  `A-002`); the allocation-policy family closed null (`A-003`). The lifetime
  alpha-cell floor is 452.
- Post-recommendation drift is among the most heavily studied and most
  heavily arbitraged anomalies in the published literature. A fresh
  independent edge is not the base case.
- **Aggregation dilutes the signal it depends on.** Summing weighted
  stock-level revisions across 50–500 holdings projects mostly onto the ETF's
  common factor. Scores across large-cap technology ETFs will be strongly
  collinear because the same mega-caps dominate SMH, VGT, XLK and QQQ alike,
  so "ranking ETFs" partly re-ranks one factor. If a genuine stock-level edge
  exists, trading the stocks dominates trading the wrapper: the ETF layer buys
  diversification, capacity, and access to leveraged/inverse products, and it
  pays for them in signal strength. That trade must be measured, not assumed.
- The failure mode this project has already met twice is a long-only result
  that clears a gross-versus-zero test while sitting on top of its own
  benchmark. Every ACER comparison therefore requires a cadence-matched
  benchmark on identical dates, and a beta-free construction before any edge
  claim.

## 3. What this replaces, and what it does not

| Item | Disposition |
|---|---|
| `docs/reference/STRONGBUY_PORTFOLIO_TEST_PLAN.md` (SBP-0..5) | **SUPERSEDED as the priority program, 2026-08-20, while still a draft.** It was never adopted or frozen, so no evidence, capture, or result is affected. Retained in full, including amendments SBPA-001..011, as the record of a reviewed design decision. |
| `docs/research/STRONGBUY_RATINGS_2026-08-19_CAPTURE_PREREGISTRATION.md` (SBR) | **Frozen contract, closed before its first verified capture.** No snapshot is committed, and the task must not be installed. The machine-local task and artifact state has not been measured, so it cannot truthfully be described as verified absent. See section 3.1. |
| `docs/research/LEVERAGED_THRESHOLD_2026-08-19_PREREGISTRATION.md` (LEV) | **Unchanged and still separate.** LEV-2..4 remain a fast historical read on TQQQ timing. It is not ACER evidence and ACER does not consume it. |
| MPQ / HPQ | Unchanged: proposed, on hold. |
| Closed families (`A-001`, `A-002`, `A-003`) | Unchanged and still closed. ACER is permitted under the A-002 closure because it brings a **new data source** (analyst revision history), a **fresh preregistration**, and an **owner decision** — all three, which that closure requires. |

### 3.1 Why SBR-1's capture stream stops before it starts

SBR-1 captures monthly consensus **bucket counts** (`strongBuy`, `buy`,
`hold`, `sell`, `strongSell`). ACER's primary signal is the **revision** —
a per-firm rating change with its own timestamp. Monthly count snapshots
cannot reconstruct per-firm actions: a count that moves from 12 to 13 Buys
does not say which firm acted, when, or from what prior rating, and two
offsetting actions inside one month are invisible.

The capture code, its tests, and its installer are **retained** (they remain
reviewed work and a level-based hypothesis could revive them), but the stream
is closed and its task must not be installed. No snapshot is committed. The
machine-local task and artifact state has not been measured, so a later reader
must not turn that absence of repository evidence into a claim of verified
zero captures. No committed evidence or epoch is disturbed.

## 4. Data requirements, and what is actually verified

| Requirement | Source | Status |
|---|---|---|
| Historical stock prices, delisted included | QuantConnect | Available |
| Historical ETF prices incl. leveraged/inverse | QuantConnect | Available |
| Corporate actions, ticker/security mapping | QuantConnect | Available |
| **Historical ETF constituents with weights** | QuantConnect `ETFConstituentUniverse` | **Verified**: exposes `EndTime`, `LastUpdate`, `Weight`, `SharesHeld`, `MarketValue`, daily resolution. QuantConnect states the dataset "is created by tracking the host ETF websites and can be delayed by up to 1 week". Coverage figures (about 2,650 ETFs from June 2009, daily from January 2015, monthly before) are the owner's research and are **not independently verified here** — ACER-1 must confirm them. |
| Execution simulation, fees, slippage | QuantConnect / LEAN | Available; research only, never an execution path for this project |
| **Analyst revision history** | External purchase (Zacks ZRH, Benzinga via Massive, FMP, or equivalent) | **Not owned.** QuantConnect's Benzinga integration is a news feed, not analyst ratings. |
| **Control set for Stage 2** — earnings dates, standardized surprise, size, liquidity, volatility, value, sector | Partly QuantConnect fundamentals; standardized surprise needs an estimates dataset | **Not owned, and not covered by a ratings subscription.** This is a second, separate data cost that the source document does not price. |

Two vendor questions remain open and decide the ratings purchase: does the
candidate's ratings history contain **dated actions for delisted and
deregistered tickers, and from what start date**; and can consensus be
retrieved **as of a past date** rather than only as current state. A
current-state consensus endpoint is the same look-ahead that closed Stage 2
PEAD and is unusable for history.

### 4.1 Point-in-time rules that must hold regardless of vendor

- Analyst data is downloaded **once** into an immutable, hash-verified,
  normalized snapshot; the backtest reads that snapshot and never calls a
  vendor API. Reuse `ml/artifacts.py`, the canonical-JSON hashing, and the
  dataset sidecar helpers rather than building parallel machinery. A vendor
  restating an old record must never silently change a past result.
- The holdings **availability bound** must be pinned by a test, not inferred
  from the framework. `EndTime`, `LastUpdate`, and QuantConnect's ingestion
  lag are three different things, and none is guaranteed to be the moment the
  information became knowable. ACER-1 declares which field bounds availability
  and enforces a declared minimum lag on top of it.
- Cloud-resident datasets **cannot be hashed** by this project. That is a real
  gap against the repository's content-addressing rule and must be disclosed
  in every run record, compensated by recording dataset name and version,
  project name, compile ID, backtest ID, source-file SHA-256, and the
  uploaded custom-data SHA-256.
- Rating scales must be standardized across brokerages before scoring, and
  that mapping is a **specification decision recorded in advance**, not a
  data-cleaning step performed while looking at results.

## 5. Milestone ladder

Each milestone is one branch, independently reviewed, with its own definition
of done. Gates are pass/fail before the next milestone begins.

| ID | Work | Gate |
|---|---|---|
| **ACER-0** | Freeze this contract: signal encoding, decay grid, eligibility, controls, benchmarks, gates, cell count, and the run budget. Choose the ratings vendor from the two open questions in section 4. | Owner adoption. Nothing below may start first. |
| **ACER-1** | Data audit: verify point-in-time ratings timestamps and standardized histories; verify ETF constituents, weights, and actual availability semantics; build a survivorship-aware universe; quantify missingness and coverage. | Proceed only if the data can support a genuinely point-in-time test. A failure here ends the program cheaply. |
| **ACER-2** | **Stock-level signal validation — the decisive milestone.** Do revisions carry incremental out-of-sample information after momentum, earnings, size, liquidity, volatility and sector controls? Levels versus revisions; alternative encodings; decay half-lives chosen out-of-sample. | Revisions must show incremental **out-of-sample** information under the frozen gate. In-sample correlation is not a pass. **Null here closes the program.** |
| **ACER-3** | Unlevered ETF aggregation: raw, coverage-adjusted, breadth-filtered and equal-weighted variants; ETF clustering to prevent duplicated exposure; ranking and threshold portfolios. | The 1x strategy must survive costs, a cadence-matched benchmark on identical dates, and reasonable alternative specifications. |
| **ACER-4** | Robustness and falsification: walk-forward or nested validation, a reserved untouched test period, regime and sector splits, placebo timestamps, shuffled signals, delayed-signal tests, comparison against ETF momentum and sector rotation, multiplicity correction, parameter sensitivity. | Stability, not one narrow parameter choice or subperiod. |
| **ACER-5** | Bearish implementation, tested as three separate strategies (avoidance, ordinary short, inverse ETF) with borrow, daily reset, fees, spreads, tracking error, and tail/rebound risk modelled. | Retain bearish exposure only if it beats simply reducing long exposure. |
| **ACER-6** | Leverage overlay on a validated 1x strategy: volatility targeting, regime gates, leverage caps, drawdown control, concentration limits, actual leveraged-fund returns where the products existed. | Leverage must improve the objective after costs and tail risk, not merely magnify gross return. |
| **ACER-7** | Prospective paper observation of the full process with no capital: every input, signal, eligibility decision and hypothetical trade logged; expected versus realized turnover, spreads, tracking and decay compared; model-change and shutdown criteria predefined. | Evidence sufficiency under a preregistered floor, exactly as the paper-evidence epochs already work. |

**ACER-2 is the whole program.** It requires no ETF holdings, no inverse
products, and no leverage. Scope and price ACER-2 alone; everything after it
is contingent.

## 6. Look accounting and multiplicity — the discipline the source lacks

The source document says to correct for multiple testing but declares no
family size, gate, or run budget. Without those, a seven-stage program over
one historical sample is a false-discovery generator, which is exactly the
failure this repository's look registry exists to prevent.

Binding rules for ACER, to be given concrete numbers at ACER-0:

- Every cloud execution — including refusals, errors, and accidental
  launches — is appended to `docs/alpha-result.md` as a new `R-nnn` entry with
  full identity, and counts as a research look.
- Each milestone declares its **cell count and family gate before any result
  is observed**, and the lifetime floor accumulates across milestones.
- Discovery and confirmation are separate: parameters chosen in ACER-2/3 may
  never be re-chosen after seeing ACER-4's reserved period, and that period
  stays untouched until the single frozen pass.
- Statistical testing uses this repository's existing toolkit, including
  out-of-sample block significance rather than pooled, row-level, or
  by-date-only significance.
- A null result closes its family. It is not a reason to tune a threshold and
  re-run.

## 7. Owner decisions required before ACER-0 can freeze

1. **Ratings vendor**, resolved against the two open questions in section 4
   (dated actions for delisted tickers; as-of retrieval of consensus).
2. **Control-set data** for ACER-2 — which estimates/fundamentals source, and
   its budget, given that a ratings subscription does not cover it.
3. **Run budget and family sizes** for ACER-2 and ACER-3, since these fix the
   multiplicity correction before any look.
4. **Benchmarks**: the cadence-matched comparator for each variant, and
   whether SPY, QQQ, or an equal-weight ETF basket is primary.
5. **Universe eligibility**: listing history, assets, volume, spread, and
   holdings-availability thresholds for an ETF to be investable.
6. Confirmation that **SBR-1's task stays uninstalled** and its stream closed
   (section 3.1), or an explicit decision to run it anyway as a secondary
   level-based dataset.

## 8. What this plan deliberately does not do

It does not adopt or freeze any value; it does not authorize a purchase, a
QuantConnect run, or any operational action; it does not treat the source
document's design as evidence of an edge; it does not reopen the closed alpha,
allocation-policy, or Strong-Buy programs; and it grants no execution
authority to any research artifact, in LEAN or anywhere else.
