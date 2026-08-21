# Analyst-Consensus ETF Rotation (ACER) — research program plan

Status: **PARTIALLY FROZEN (2026-08-20).** The owner split the freeze:

- **ACER-0A owner decisions are FROZEN, but its executable
  preregistration is INCOMPLETE.** Its operative decision record is
  `docs/research/ACER_2026-08-20_ACER0A_FREEZE.md`, whose section 9 lists the
  definitions that must still be frozen before any real-outcome execution.
  Where that document and this one differ, **it governs for ACER-2**.
- **ACER-0B is NOT frozen** — the contingent ETF-level ACER-3 test. ETF
  benchmark and investability decisions are deliberately deferred so they are
  not forced before a stock-level signal is shown to exist. ACER-0B requires a
  separate owner act and only becomes reachable if ACER-2 passes.

Everything in this file that concerns ACER-3 and later remains DRAFT and
acquires no authority. Nothing here is scheduled or implemented beyond the
ACER-1 data plumbing already reviewed.

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
- **Aggregation is expected to dilute the signal it depends on.** Summing
  weighted stock-level revisions across 50–500 holdings should project largely
  onto the ETF's common factor, and scores across large-cap technology ETFs
  are expected to be highly correlated because the same mega-caps carry large
  weights in SMH, VGT, XLK and QQQ alike — so "ranking ETFs" may partly
  re-rank one factor. **This is reasoning, not a measurement**: no correlation
  has been computed here, and stating it as established would repeat the
  unsupported-quantity error that sank amendment SBPA-001. ACER-3 must measure
  the realized cross-sectional correlation of ETF scores and report it beside
  any ranking result. If a genuine stock-level edge exists, trading the stocks
  may dominate trading the wrapper: the ETF layer buys diversification,
  capacity, and access to leveraged/inverse products, and plausibly pays for
  them in signal strength. That trade must be measured, not assumed.
- The failure mode this project has already met twice is a long-only result
  that clears a gross-versus-zero test while sitting on top of its own
  benchmark. Every ACER comparison therefore requires a cadence-matched
  benchmark on identical dates, and a beta-free construction before any edge
  claim.

## 3. What this replaces, and what it does not

| Item | Disposition |
|---|---|
| `docs/Archive/Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md` (SBP-0..5) | **SUPERSEDED as the priority program, 2026-08-20, while still a draft.** It was never adopted or frozen, so no evidence, capture, or result is affected. Retained in full, including amendments SBPA-001..011, as the record of a reviewed design decision. |
| `docs/Archive/Research/STRONGBUY_RATINGS_2026-08-19_CAPTURE_PREREGISTRATION.md` (SBR) | **Frozen contract, closed before its first verified capture.** No snapshot is committed, the task must not be installed, and the 2026-08-20 read-only host measurement found the task absent and zero capture artifacts. See section 3.1 and `docs/operations/OPERATIONAL_FACTS.md`. |
| `docs/Plan/Research/LEVERAGED_THRESHOLD_2026-08-19_PREREGISTRATION.md` (LEV) | **Unchanged and still separate.** LEV-2..4 remain a fast historical read on TQQQ timing. It is not ACER evidence and ACER does not consume it. |
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
machine-local task and artifact state was measured read-only on 2026-08-20:
the task was absent and the plausible artifact roots contained zero capture
artifacts. No committed evidence or epoch was disturbed.

## 4. Data requirements, and what is actually verified

| Requirement | Source | Status |
|---|---|---|
| Historical stock prices, including securities while listed | Provider-neutral requirement; QuantConnect/AlgoSeek and CRSP are candidates | **Unmeasured for ACER on this machine.** QuantConnect credentials are visible to the current process, but credentials do not prove the organization's dataset entitlements, delisted coverage, or downloadable history. |
| Terminal value after delisting | CRSP `DLRET` is the preferred candidate; another source must prove equivalent semantics | **Unavailable locally.** A QuantConnect delisting event identifies the event but has not been shown to include the post-delisting return needed by the frozen total-return outcome. |
| Historical ETF prices incl. leveraged/inverse | QuantConnect/AlgoSeek or another audited price source | **Unmeasured for ACER.** Do not infer availability from an API token. |
| Corporate actions, ticker/security mapping | QuantConnect US Equity Security Master, CRSP, or another audited security master | **Unmeasured for ACER.** QuantConnect documents map/factor files and splits, dividends, delistings, mergers, and ticker changes from 1998, but the current process has not verified the owner's subscription or materialized the data. |
| **Historical ETF constituents with weights** | QuantConnect `ETFConstituentUniverse` candidate | **Schema documented, entitlement/coverage unverified.** The API exposes `EndTime`, `LastUpdate`, `Weight`, `SharesHeld`, and `MarketValue`; actual point-in-time coverage, delay semantics, and owner access remain ACER-1 measurements. |
| Execution simulation, fees, slippage | Local LEAN | **Local engine verified end to end; ACER data path unresolved.** LEAN CLI `1.0.228`, the isolated workspace, Docker client/server `29.7.2`, and the generated sample execution through LEAN Engine `2.5.0.0` passed on 2026-08-21. This proves the execution environment, not ACER dataset availability, licence, point-in-time fitness, or research authority. |
| **Analyst revision history** | Benzinga Analyst Ratings via Massive | **Purchased and structurally audited.** The immutable machine-local snapshot remains licensed data and is not committed or authorized for third-party upload. Issuer mapping and Snapshot B remain open ACER-1 gates. |
| **Control set for Stage 2** — earnings dates, standardized surprise, size, liquidity, volatility, value, sector | Candidate: Massive/Benzinga Earnings plus separately verified point-in-time market/fundamental sources | **Not adopted.** The owner authorized up to $99 for a one-month structural Earnings audit. Surprise semantics, value source and the remaining formulas are open in ACER-0A.2–0A.10. |

The two original ratings-vendor blockers passed the structural audit: dated
per-firm actions reach 2011-12 and include probed delisted names, while
`previous_rating` permits event-state reconstruction without a current-state
consensus endpoint. That does not finish ACER-1: inconsistent ticker-rename
and reuse behavior requires ambiguity-refusing issuer mapping, and Snapshot B
must measure whether stable vendor rows are restated.

### 4.1 Subscription and acquisition reality (2026-08-21)

The recorded **Benzinga Analyst Ratings** purchase is enough for the analyst
event side of ACER-1, subject to normalization, issuer mapping, Snapshot B and
the recorded licence boundary. It is **not enough for ACER-2**. Massive sells
Benzinga Earnings as a separate expansion, and the repository has not recorded
that expansion as purchased. The local LEAN CLI and authenticated QuantConnect
session are now verified, but they do not establish access to the US Equity
Security Master, US Equities history, US Fundamental Data, or ETF constituent
history.

Before ACER-2 can become runnable, the implementer must produce non-outcome
structural evidence for each of these capabilities:

1. Benzinga Earnings entitlement and point-in-time estimate-history semantics;
2. point-in-time daily stock prices with known-delisted coverage;
3. terminal delisting returns, preferably CRSP `DLRET` or a demonstrably
   equivalent field;
4. durable issuer/security identity with ticker-reuse boundaries;
5. historical security type and primary-listing eligibility;
6. splits, dividends, and other corporate actions sufficient for total return;
7. point-in-time shares outstanding, book value, and sector taxonomy;
8. ETF constituent history and its publication-lag semantics for later ACER-3;
9. a materialized, hash-bound normalized ratings dataset; and
10. the licensed-data rule for whichever local or cloud engine is selected.

Databento is one optional candidate for some market/reference items. It is not
a prerequisite and its current key is not visible to this process. The
capability checker must remain green or red on capabilities, never vendor
brand names.

### 4.2 Point-in-time rules that must hold regardless of vendor

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
| **ACER-0A** | **PARTIAL FREEZE 2026-08-20** (`docs/research/ACER_2026-08-20_ACER0A_FREEZE.md`): six-cell family, named primary, Bonferroni 0.05/6, provisional two-slot budget, numeric stock thresholds, benchmark policy and engine ruling are frozen owner decisions. | **Not executable.** ACER-0A.1–0A.10 must close before any real signal/outcome join; these include the actual signal, controls, statistic, split, confirmation and slot-failure definitions. |
| **ACER-0B** | **NOT frozen, deliberately.** The ETF-level ACER-3 contract: ETF eligibility (AUM, spread, volume, holdings coverage), the equal-weight comparator, and ACER-3's own cells and budget. | Requires a separate owner act, reachable only if ACER-2 passes. ACER-3's run budget is **zero** until then. |
| **ACER-1** | Data audit: verify point-in-time ratings timestamps and standardized histories; verify ETF constituents, weights, and actual availability semantics; build a survivorship-aware universe; quantify missingness and coverage. **Also measure the machine-local SBR state on the operational host** (task presence and snapshot count) and record it in `docs/operations/OPERATIONAL_FACTS.md`, so the closure in section 3.1 rests on a measurement rather than on absence of repository evidence. | Proceed only if the data can support a genuinely point-in-time test. A failure here ends the program cheaply. The SBR measurement is read-only; finding snapshots would be a material discovery, not a footnote. |
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

- Every execution against real outcomes, local or cloud — including refusals, errors, and accidental
  launches — is appended to `docs/Archive/Research/alpha-result.md` as a new `R-nnn` entry with
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

## 7. Owner decisions — resolved 2026-08-20 for ACER-0A

The six owner questions are settled at the decision level. They do not by
themselves make ACER-2 executable; section 9 of
`docs/research/ACER_2026-08-20_ACER0A_FREEZE.md` is the remaining freeze
ledger.

1. **Ratings vendor** — **RESOLVED**: Benzinga via Massive, purchased and
   audited. Both blocking questions answered favourably (dated per-firm
   actions from 2011-12 with pre-delisting coverage; `previous_rating` makes
   state reconstructible without an as-of consensus endpoint).
2. **Control-set data** — **CANDIDATE CHOSEN, NOT ADOPTED**: the
   Massive/Benzinga Earnings expansion, with **$99** authorized for a
   one-month structural audit against eight named criteria. Adoption depends
   on that audit passing. `eps_surprise_percent` is not trusted; this project
   freezes its own standardized-surprise formula afterwards (item ACER-0A.2).
3. **Run budget and family sizes** — **RESOLVED for ACER-2**: six cells,
   Bonferroni 0.05/6, one development execution, one confirmation execution,
   unlimited synthetic tests that never touch real outcomes. **ACER-3's
   budget is zero** until ACER-0B is separately frozen.
4. **Benchmarks** — **RESOLVED**: ACER-2 has no index benchmark; its gate is
   residualized stock-level IC. If ACER-2 passes, ACER-3's primary comparator
   will be an equal-weight basket of the same eligible ETFs on identical
   dates. SPY and QQQ are secondary descriptive comparisons only.
5. **Universe eligibility** — **RESOLVED for stocks** (US primary-listed
   common stock, 252 sessions, $5, $10M 60-session median dollar volume,
   point-in-time controls, delisted-eligible, named refusals). **ETF**
   eligibility is deliberately deferred to ACER-0B.
6. **SBR-1** — **RESOLVED**: stays closed and uninstalled. Machine-local
   state measured read-only 2026-08-20 and recorded in
   `docs/operations/OPERATIONAL_FACTS.md`: task absent, zero artifacts, so
   the closure now rests on a measurement rather than on absence of
   repository evidence.

Two further rulings were made in the same act: **local LEAN is the
authoritative engine** and reconstructable Benzinga rows must not be uploaded
to QuantConnect without separate explicit evidence that the terms permit it;
and **QuantConnect access is authorized for read-only symbol-mapping work
only**, with no upload, no outcome join, no backtest, and no research look.

## 8. What this plan deliberately does not do

It does not freeze ACER-3 or the still-open ACER-2 definitions; it authorizes
no purchase beyond the $99 Earnings audit, no real-outcome execution, no
QuantConnect run, and no operational action. It does not treat the source
document's design as evidence of an edge, reopen the closed alpha,
allocation-policy or Strong-Buy programs, or grant execution authority to any
research artifact, in LEAN or anywhere else.
