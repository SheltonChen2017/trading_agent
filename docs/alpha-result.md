# Alpha result ledger

**Long-lived record of every QuantConnect run.** Rejected, inconclusive,
invalidated, stale and unavailable results are kept here permanently. An
unfavourable result is never deleted and never silently replaced by a
rerun; a rerun is a new entry that references the one it supersedes.

**2026-08-17 audit status:** every local and QuantConnect alpha result listed
below is invalid, refused, unanalysed, pending review, or provenance
incomplete. None is usable evidence of an edge. At the owner's direction,
invalid raw logs, generated JSON artifacts, and superseded result narratives
were removed from the active `docs/` tree after their exact Git history,
run identity, status, and SHA-256 values were preserved in this ledger. Their
removal is housekeeping, not deletion of an inconvenient research outcome.

**Hash-verification convention (recorded 2026-08-17, CCR3-D):** every SHA-256
in this ledger was computed over the checked-out Windows working-tree bytes,
which use CRLF line endings under this repository's `core.autocrlf=true`
setting. Git blobs store LF, so recovering a deleted file with `git show
b4e9ee0^:docs/<name>` and hashing it directly yields a DIFFERENT digest.
To verify, convert LF to CRLF first (for example
`git show b4e9ee0^:docs/<name> | unix2dos | sha256sum`). All fourteen removed
artifacts were re-verified this way during the 2026-08-17 final counter-review
and every ledger hash matched; a bare-blob hash mismatch is the line-ending
convention, not evidence of tampering.

Nothing in this file is trading authorization. QuantConnect is historical
replication only; Alpaca Paper is a later, separate forward-validation
stage.

## Status vocabulary

| Status | Meaning |
|---|---|
| VALID | Ran on reviewed code, complete output, statistics usable |
| INVALIDATED | Ran, but a defect found afterwards makes the numbers unusable |
| REFUSED | The algorithm declined to emit results; no statistics exist |
| UNANALYSED | Complete raw output exists, but controlled analysis has not been run |
| PENDING_REVIEW | Output came from code that had not completed the review gate; unusable |
| PROVENANCE_INCOMPLETE | Run identity cannot be tied completely to reviewed source and artifacts |
| INCONCLUSIVE | Complete output, but the design cannot answer the question |
| STALE | Superseded by a later run on corrected code |
| UNAVAILABLE | Could not be run |

## Cumulative look accounting

Method V2 section 1.10 counts every real-market cloud execution, even when it
refuses, is never locally analysed, or ran accidentally. At this ledger's
opening there are **five additional run-level looks**: R-001, both R-002
runs, R-003, and R-004. The emitted alpha-cell exposure is **80**: 40 short-
horizon cells across A/B plus 40 monthly cells from the accidental A run.
R-001 emitted zero cells but still consumed a run; R-004 is a benchmark run,
not an alpha cell. Together with the prior 348 declared cells, the conservative
lifetime alpha-cell exposure floor is **428**. These counts do not make any
result valid and do not authorize analysis outside the reviewed workflow.

**Current pre-run gate (2026-08-17):** no REP-H52 or REP-IDV cloud run has
been recorded. The Stage 1 implementation at `dc63eec` and all earlier alpha
research/QC code were re-audited. The current local correction is `855941a`;
the final documentation head will be recorded in the handoff after validation.
No fresh run is allowed until Claude counter-reviews the final pushed Codex
head. A future run belongs in a new `R-005`-or-later entry. If any run was
launched before that gate, it must be added here as `PENDING_REVIEW` and
counted; it must not be silently treated as the reviewed run.

---

## R-001 — Monthly battery, Universe B_core, corrected code (REFUSED)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery: MOM_3/6/9/12_1, RESIDUAL_MOM_6/12_1, GROSS_PROFITABILITY, QUALITY_COMPOSITE, QUALITY_MOMENTUM, MULTI_ALPHA_COMPOSITE |
| **Replication or new** | Exact replication of the frozen 2026-08-16 pre-registration, on corrected code |
| **Research look** | Counted real-market run; zero emitted alpha cells |
| **Multiplicity family** | QC alpha battery 2026-08-16 (declared 135; Codex QCAR-006 corrects the family to 180) |
| **Source commit** | `e8eb558` (Codex correction), merged via `f4c81dd` |
| **QC project ID** | `35244708` (`tg-rr-mon-B`) |
| **Compile ID** | not recorded — gap, fixed for later entries |
| **Backtest ID** | `e3132ae2e9f37235893a77437cc7bb87` |
| **Run date** | 2026-08-16 |
| **Data period** | 2012-01-01 to 2024-12-31 |
| **Universe** | B_core: price ≥ $5, market cap ≥ $500M, ADV20 ≥ $5M; point-in-time Morningstar fundamentals; `MarketCap == 0` treated as missing with shares-outstanding fallback |
| **Costs / turnover / benchmark** | n/a — no series emitted |
| **Removed raw artifact identity** | `qc_rr_mon_B_20260816.log`, 7 lines, sha256:`516fe20b04ec940007bce8d9a97c2ed363f422655ebcd61b84fef2aa8525e868`; removed from active docs on 2026-08-17, recoverable from Git history |
| **Primary statistics** | **none** |
| **Gate outcome** | n/a |
| **Validity** | **REFUSED** |
| **Provenance** | **PROVENANCE_INCOMPLETE** — compile ID absent |

### What happened

The algorithm refused to emit:

```
INCOMPLETE|missing_specs=MULTI_ALPHA_COMPOSITE|RESIDUAL_MOM_12_1|RESIDUAL_MOM_6_1
```

Codex's completeness guard worked as designed. Rather than emit seven of
ten specifications as though the series were whole — which the previous
generation of this code did, and which produced a headline — it declined
to emit anything.

Universe construction itself was sound and matches the earlier run
exactly: `cap_rows=312696 cap_fallback=35268 cap_missing=7291`. The run
processed 31,958,444 data points in 4,819 seconds (7k points/sec against
303k/sec for the defective version — the corrections are roughly 40x more
expensive, mostly retained delisted subscriptions and adjusted bars).

### Root cause, found by counter-review

The submitted peer-length equality did make every residual score unavailable,
so the refusal correctly exposed a real defect. Independent review then found
a deeper issue in the proposed slice fix: the helper summed the most-recent
21 sessions, which are the month a 6-1/12-1 signal must skip. The reviewed
correction uses a fixed 252-session joint market/leave-one-out-industry fit,
then sums residuals over `t-126..t-21` or `t-252..t-21`. All monthly output
from the slice-only implementation is stale pending Claude's counter-review
and a new QC run.

### Limitations and review status

- No statistic exists. Nothing about any alpha can be inferred from this
  entry.
- The slice-only fix was reviewed and corrected again; it must not be run or
  cited. Claude must counter-review the Codex head before a fresh QC run.
- Compile ID was not captured. Later entries record it.

---

## R-002 — Short battery, B_core and A_large, corrected code (UNANALYSED)

| Field | Value |
|---|---|
| **Alpha / specification** | REVERSAL_5D, INDUSTRY_ADJ_REVERSAL_5D, ABNORMAL_VOLUME_REVERSAL, MAX_20, MAX_X_REVERSAL |
| **Replication or new** | Exact replication of the frozen pre-registration, on corrected code |
| **Research look** | Two counted real-market runs; 40 emitted alpha cells total |
| **Source commit** | `e8eb558` (Codex correction), merged via `f4c81dd` |
| **QC project / compile IDs** | not recorded |
| **Backtest IDs** | B_core `a364f6872f6b0827b8adfb22ac20337e`; A_large `6dec09106141c24fbf884738db84c36a` |
| **Data period** | 2012-01-01 to 2024-12-31 |
| **Output** | 534 declared dates, 54 base64 blocks each, layout `b64block_date_u32_i32x4_u16x3` |
| **Removed raw artifact identities** | `qc_rr_sht_B_20260816.log` sha256:`a4237e06c00bf6b07fff192a1a4fbd6ab42efe9b6dab0c9b3f6b660a2f8c7f58`; `qc_rr_sht_A_20260816.log` sha256:`f96b076d79729e8906e940f2711cc22b65091ea6d14698cc8b23d8b90e3816b1`; removed from active docs on 2026-08-17, recoverable from Git history |
| **Validity** | **UNANALYSED** — complete output, statistics not yet computed |
| **Provenance** | **PROVENANCE_INCOMPLETE** — project and compile IDs absent |

### The timing correction is confirmed by arithmetic

The invalidated run reported **1,283** non-overlapping five-session
observations over ~3,275 sessions, which implies 2.55 sessions each and is
impossible; the ceiling is 655. The corrected run declares **534**, which
sits just under that ceiling.

This was set as a falsifiable pre-check before the run: if the count came
back near 1,283 the timing fix had not bound and nothing else in the run
would be worth reading. It came back at 534. **QCAR-002 is fixed in
substance, not merely in intent.**

### Why it is UNANALYSED rather than VALID

No statistics have been computed. Contrary to the submitted note,
`scripts/analyse_qc_alpha_battery.py` already contains a reviewed base64-block
decoder and `tests/test_qc_alpha_battery.py` round-trips the exact layout.
Codex deliberately did not run it: analysis belongs after the current code
correction and Claude counter-review so look accounting and result identity
are recorded before any statistic is observed.

A separate process failure was recorded here rather than hidden: my run
queue reported these two runs as `TRUNCATED` because it counts `ROW|`
lines and the corrected short battery emits `B64BLOCK|` lines. The logs are
complete; the checker was wrong. A completeness check that does not
understand the format it is checking gives false alarms in one direction
and would give false assurance in the other.

---

## R-003 — Monthly battery, A_large (PENDING_REVIEW, not usable)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery, 10 specifications |
| **Research look** | Counted real-market run; 40 emitted alpha cells |
| **Source commit** | `f4c81dd` **plus an uncommitted, unreviewed local fix** to `_residual_momentum` |
| **QC project / compile IDs** | not recorded |
| **Backtest ID** | `df324dbbca4070ac0f45f270406e673a` |
| **Data period** | 2012-01-01 to 2024-12-31 |
| **Output** | 142 dates, complete, no INCOMPLETE marker |
| **Removed raw artifact identity** | `qc_rr_mon_A_20260816.log` sha256:`7e161182fb2c0baf711d1b90ebc784301edd80b0edab17fcb5152553c2ca8639`; removed from active docs on 2026-08-17, recoverable from Git history |
| **Validity** | **PENDING_REVIEW — must not be used for any conclusion** |
| **Provenance** | **PROVENANCE_INCOMPLETE** — project and compile IDs absent |

### Why this entry exists at all

**This run should not have happened.** The workflow adopted for this round
is that QuantConnect runs only code that Codex has reviewed and I have
counter-reviewed. My run queue reads the algorithm file at call time, so
when I fixed `_residual_momentum` locally, the queue's next monthly job
silently picked up that unreviewed fix. It emitted 142 complete dates,
which the pre-fix code could not have done — that is how the violation was
detected.

The queue predated the rule, and I did not think through that a running
queue would re-read edited files. The rule is about not using cloud
compute to debug unreviewed code, and that is exactly what happened,
accidentally.

The result is recorded because deleting an inconvenient run is precisely
what this ledger exists to prevent. It is marked unusable, and it will be
superseded by a reviewed rerun rather than promoted.

---

## R-004 — Universe benchmark, B_core, corrected code (UNANALYSED)

| Field | Value |
|---|---|
| **Specification** | Equal-weight benchmark of the point-in-time B_core universe |
| **Research look** | Counted real-market benchmark run; not an alpha cell |
| **Source commit** | `e8eb558`, merged via `f4c81dd` |
| **QC project / compile IDs** | not recorded |
| **Backtest ID** | `e3c2ff22333f1c923502b3d1c399fcbb` |
| **Data period** | 2012-01-01 to 2024-12-31 |
| **Output** | 155 declared dates, 155 rows, complete |
| **Removed raw artifact identity** | `qc_rr_ben_B_20260816.log` sha256:`ec623810fb53df1021d357a15874595b161ba000fb8614eea49fec3e23021489`; removed from active docs on 2026-08-17, recoverable from Git history |
| **Validity** | **UNANALYSED** — complete, statistics not computed |
| **Provenance** | **PROVENANCE_INCOMPLETE** — project and compile IDs absent |

The corrected benchmark now carries its own delisting arithmetic and cost
treatment (QCAR-008), so it is not comparable to the invalidated
benchmark figures in R-000 and those must not be carried forward.

---

## R-000 — Superseded battery, all universes (INVALIDATED)

Kept because deleting it would remove the most instructive evidence in
this ledger.

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery (10 specs) and short-horizon battery (5 specs), Universes A/B/C |
| **Replication or new** | First execution of the frozen 2026-08-16 pre-registration |
| **Research look** | 135 declared; QCAR-006 finds the true family is 180 |
| **Source commit** | `3a3132e`, `e3e8a23`, `6707a97` |
| **QC project IDs** | monthly 35240692 / 35241425 / 35241487; short 6 windowed projects; benchmark 3 projects |
| **Backtest IDs** | monthly B `238f133c9856464cbed5fb087f10f1e6`; others not recorded — QCAR-010 |
| **Data period** | 2012-01-01 to 2024-12-31 |
| **Reported statistics** | `QUALITY_COMPOSITE` A_large IC 0.0355, p ≤ 0.00005 vs gate 0.00037; `INDUSTRY_ADJ_REVERSAL_5D` and `MAX_X_REVERSAL` clearing in all three universes; benchmarks A 0.87 / B 0.92 / C 0.94 Sharpe |
| **Gate outcome** | Three specifications appeared to clear |
| **Validity** | **INVALIDATED** |

### Why it is invalid

Independent review (`docs/Review/REVIEW_2026-08-16_QUANTCONNECT_ALPHA_BATTERY.md`)
found ten P2 defects. Three were verified independently before acceptance:

- **QCAR-002, timing.** 1,283 claimed non-overlapping five-session
  observations in ~3,275 sessions implies 2.55 sessions each; the maximum
  possible is 655. The declared entry lag was absent and holding advanced
  on every `OnData` call. **The impossible count was quoted in the results
  document as evidence of statistical power.**
- **QCAR-001, normalization.** Raw (unadjusted) bars fed the return
  windows, so every split became a fictitious return.
- **QCAR-003, basket construction.** Deciles were formed at settlement
  from names satisfying `s in outcomes`, so anything that stopped trading
  was retroactively dropped — survivorship reintroduced at the portfolio
  level, in work whose premise was fixing survivorship.

Every statistic in that run passed through at least one of these paths.
The passes, the null momentum finding, the MAX-effect interpretation and
the benchmark verdict are all void.

### Historical evidence retained without active artifacts

The owner directed that invalid generated documents and artifacts be removed
from the active docs tree while this permanent ledger preserves their exact
disposition. The deleted files remain recoverable from Git history:

| Removed file | SHA-256 |
|---|---|
| `ALPHA_BATTERY_2026-08-15_RESULTS.md` | `8c3bcfec76316361f3227386c8815d6a8ab369f6504f93a95688373dde8cd366` |
| `ALPHA_BATTERY_2026-08-16_UNIVERSE_RESULTS.md` | `d6a502d30ebf76c4b5e93c2d2f99bf01364b5723edb87296d3e2613e39b3f17a` |
| `ALPHA_BATTERY_2026-08-16_QC_RESULTS.md` | `13945703a5207c46279e0df73d48a21edeccf44d71b76091b178472298c4603a` |
| `alpha_battery_20260815_artifact.json` | `8f8be4601de9ad6d7303e06cc8519b4f3f7b6de2692a8e8dd784fe281fac6b84` |
| `alpha_universes_20260816_artifact.json` | `94e0ca1352e414487f57adad720a0e8ccb1f6bd7f2d4a3b40462cb6c057d8423` |
| `universe_audit_20260816.json` | `e39c74db8ca6bc459cbe9676990f150151ea58f9544c6022d9db6a1177c4365a` |
| `qc_alpha_monthly_analysis_20260816.json` | `c9967fce543de299b9d57aaca1b3ec531d92e448408b67074a8e70c414d60228` |
| `qc_alpha_short_analysis_20260816.json` | `82b398e6372bdd3c7a2c65bf8042ee5f9e3112d0ca5c0e7ba6021184a07c8732` |
| `qc_universe_benchmark_20260816.json` | `3e13e7edfa2f3d11636a9de2876fae14dcc9499db419889f19560fdc1255feb4` |

The raw-log hashes are recorded in R-001 through R-004 above. Two defects
were mirror images of errors already documented elsewhere (ABR-001's
unreachable gate and ABR-003's unit mismatch); that lesson remains part of
the durable audit record even though the invalid generated files are no
longer presented as active documentation.

## 2026-08-17 full research/QC audit disposition

- Correction `855941a` standardizes every LEAN algorithm on QuantConnect's
  current Python API, prevents framework-member shadowing, repairs
  point-in-time factor/session handling, and hardens provenance and refusal
  behavior.
- The older local battery now calculates rebalance turnover from the prior
  portfolio after its prior outcome, uses the correct post-return NAV
  denominator, and refuses missing, non-finite, or wiped-out drift states.
  The universe retest uses the same drift-aware method.
- Follow-up `1e2b631` removes each stock from its own peer average and replaces
  the old sequential residual calculation with the frozen joint
  intercept/market/industry fit. This does not rehabilitate the old result;
  its static classifications and survivor-selected data remain invalid.
- The smoke runner records source/compile identity and has bounded total and
  no-progress waits, including when QuantConnect returns no numeric progress.
- No QuantConnect API was accessed and no new research look was consumed in
  this audit.
- Every historical conclusion remains unusable. A clean rerun begins only
  from the final independently counter-reviewed pushed head and is appended
  as R-005 or later; no old statistic may be copied forward.
