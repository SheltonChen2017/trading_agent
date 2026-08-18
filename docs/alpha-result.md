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
been recorded. Fable's final counter-review was merged as PR #243, but Codex's
verification found four surviving Stage 0 methodology defects and corrected
them at `ac96d47`. The corrections affect holding-period turnover, short-family
annualization, MAX(20) input refusal, and missing-industry peer construction.
No historical result changes status, no cloud run occurred, the lifetime
alpha-cell floor remains 428, and the run-level count remains five. Claude's
independent counter-review accepted the exact pushed correction head
`9e45803` on 2026-08-17, confirming all four findings and closing two
follow-up P3 gaps (FCR-001 exit-drift pin; FCR-002 Stage 1 dead-state
industry-code port). Codex independently accepted those closures at exact
head `9a7e9fc`, merged by PR #244 at `b6f577e`; its only correction was a P3
call-site regression guard with no algorithm behavior change. **Before a
fresh run:** the owner's stage-order choice and execution from the exact
merged reviewed source under the frozen evidence contract. A future run
belongs in a new `R-005`-or-later entry. If
any run was launched before that gate, it must be added here as
`PENDING_REVIEW` and counted; it must not be silently treated as the reviewed
run.

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

**Stage 0 rerun gate (2026-08-17, after R-005/R-006):** Codex's launch-round
correction head `81db126` was counter-reviewed and accepted the same day
(`docs/Review/REVIEW_2026-08-17_QC_STAGE0_LAUNCH_COUNTERREVIEW.md`); the
counter-review added tests only. Stage 0 resumes serially at **R-007** from
the accepted product tree, one backtest at a time, with new immutable
evidence paths and new project numbers. The weekend-label factor defect is
not declared closed until the corrected monthly run passes its completeness
guard in the cloud.

## R-007 — Stage 0 monthly battery, A_large, corrected code (UNANALYSED)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery, 10 specifications (rerun of R-005's family) |
| **Research look** | Counted real-market run (run-level count 7 → 8); 40 repeated cells emitted (10 specs × 4 outcomes) |
| **Multiplicity family** | QC alpha battery 2026-08-16, 180 cells; lifetime floor stays 428 |
| **Source commit** | `75ad8dc` (product tree identical to accepted review head `81db126`) |
| **Uploaded source SHA-256** | recorded in `run3_monthly_A_r007.json` (`ACTIVE_UNIVERSE="A_large"` rewrite) |
| **QC project** | `35289096` — requested `3. MONTHLY_BATTERY_A_LARGE - 20260817`, returned `3 MONTHLY_BATTERY_A_LARGE - 20260817` |
| **Compile ID** | `cd95739866906027d85df5c14e4652d3-6df45b581037ee1efc8de43eda2c77cc` |
| **Backtest ID** | `8ea519e2754a5bf0280fa3148dad46a8` |
| **Completed** | 130.16 s engine time, 27,299,669 points; `cap_rows=178769 cap_fallback=16826 cap_missing=3206` (identical universe numbers to R-005) |
| **Output** | **COMPLETE**: no `INCOMPLETE` marker; all ten specs declared; `DATES\|142` with 142 ROW lines |
| **Raw log** | `artifacts/qc_stage0_20260817/run3_monthly_A_r007.log`, 151 lines, exact-file sha256:`a4c1669d600b52de87f9019ddaf992a9cfd56de2af0ec9888330c83cbf66035d` (bytes-exact write) |
| **Validity** | **UNANALYSED** — complete raw output; statistics deferred to the frozen analyser after all nine Stage 0 runs, with full run identities |

The weekend-label factor defect is now closed in the cloud, not only in
simulation: the completeness guard that refused R-005/R-006 passed on the
corrected code, and residual momentum emitted alongside every other
specification. No statistic has been observed or computed from this output.

**Status corrected to STALE the same day.** Post-run inspection found the
run's rows carry per-date SPEC SUBSETS (specifications legitimately skip
months independently), which the frozen parser refused as truncation — the
algorithm's emission contract and the parser's completeness contract had
never been consistent for the monthly battery, and this was the first run
to reach the parser. The log also predates the SPECMETA per-spec count
declaration that resolves it. R-007 is therefore unanalysable as recorded
and is superseded by a rerun on corrected code; its identity, hashes, and
look remain counted. Its only missing month is the benign 2024-12 tail
cohort (settles beyond the window end).

## R-008 — Stage 0 monthly battery, B_core, corrected code (INVALIDATED)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery, 10 specifications (rerun of R-006's family) |
| **Research look** | Counted real-market run (run-level count 8 → 9); 40 repeated cells emitted |
| **Source commit** | `100bd0f` (product tree identical to accepted review head `81db126`) |
| **Uploaded source SHA-256** | recorded in `run4_monthly_B_r008.json` (`ACTIVE_UNIVERSE="B_core"` rewrite) |
| **QC project** | `35289185` — requested `4. MONTHLY_BATTERY_B_CORE - 20260817`, returned `4 MONTHLY_BATTERY_B_CORE - 20260817` |
| **Compile ID** | `9184cf4829b55603eb1cb891e53d57cc-25c0bda49c1cafc56bdf0136f834980a` |
| **Backtest ID** | `1329770d81d3c84573afc2638835111d` |
| **Completed** | 563.28 s engine time, 31,945,614 points; `cap_rows=312696 cap_fallback=35268 cap_missing=7291` |
| **Output** | `DATES\|48` with 48 rows — continuous 2013-02..2017-01, then NOTHING for eight years |
| **Raw log** | `artifacts/qc_stage0_20260817/run4_monthly_B_r008.log`, 57 lines, exact-file sha256:`c14bdc627830b43227175777f841158d2bf0bb5f17a78fdbb7edeb2efb51167a` |
| **Validity** | **INVALIDATED** — a state-machine defect, not honest refusals, truncated coverage after 2017-01 |

### The die-off and its root cause

The clean truncation signature exposed an unrecoverable refusal spiral: one
month in which every specification skipped left the settling-cohort
`prior_outcomes` empty forever against non-empty stale weights, so every
later bind refused. R-007 (A_large) simply never hit an all-skip month.
Fix (same-day, local): drift outcomes now come from each book's own stored
entry prices against current/terminal prices — the self-contained pattern
Stage 1 and both benchmarks already used — so a refused month retries and
recovers; stale-book names also survive universe removal so their prices
stay observable. Together with the SPECMETA emission and the parser's
SPECMETA-verified ragged-date acceptance (the R-007 defect), both fixes are
pinned by `tests/test_alpha_battery_monthly_sim.py`'s forced-skip-month
drive, which feeds the algorithm's own emitted log into the real parser —
red on the pre-fix tree in both directions. **Stage 0 remains halted
pending independent review of these fixes; monthly A and B rerun after
acceptance as new R-numbers.**

## R-009 — Stage 0 monthly battery, A_large, spiral/parser fixes (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery, 10 specifications (rerun of R-007) |
| **Research look** | Counted real-market run (run-level count 9 → 10); 40 repeated cells emitted |
| **Source commit** | `05929a5` (contains Claude fixes `49e8160`, not yet independently reviewed — hence PENDING_REVIEW at the owner's explicit direction to continue) |
| **Uploaded source SHA-256** | recorded in `run5_monthly_A_r009.json` |
| **QC project** | `35289732` — `5. MONTHLY_BATTERY_A_LARGE - 20260817` |
| **Compile ID** | `57ba8b55f5f8359f537e88e6ced39eb8-684591190549d64f684d2fcf8440733b` |
| **Backtest ID** | `7ebe7a44eef6bf8ff34e3a06205edaca` |
| **Completed** | 207.93 s engine time; `cap_rows=178769 cap_fallback=16826 cap_missing=3206` |
| **Output** | COMPLETE: all ten specs, `DATES\|142` = 142 rows, 10 SPECMETA lines; the raw cloud log **round-trips through the frozen parser** (619 spec-rows; per-spec periods disclosed, e.g. GROSS 142, MOM_3 107, RESIDUAL 65, MOM_12/QUALITY 35, MULTI 23). Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run5_monthly_A_r009.log`, 161 lines, exact-file sha256:`7581a59c2bd8add5f61e10f03d3f3ff1c160704fcd78a04a43ff561245c61b9e` |
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`); no rerun required |

## R-010 — Stage 0 monthly battery, B_core, spiral/parser fixes (INVALIDATED)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery, 10 specifications (rerun of R-008) |
| **Research look** | Counted real-market run (run-level count 10 → 11); 40 repeated cells emitted |
| **Source commit** | `8957e32` (contains Claude fixes `49e8160`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `6592a89f9c03ca253379447732264748069c735d3b5afa77d732c5654224a415` (`ACTIVE_UNIVERSE="B_core"` rewrite; recorded in `run6_monthly_B_r010.json`) |
| **QC project** | `35289860` — requested `6. MONTHLY_BATTERY_B_CORE - 20260817`, returned `6 MONTHLY_BATTERY_B_CORE - 20260817` |
| **Compile ID** | `24a386fbc64902dfd35456469070aae7-6ec3cc5fd0c91952f5785a9e5eb8b104` |
| **Backtest ID** | `bb7d45db1fefda2f1e58aadd4e9c7621` |
| **Launched / completed (UTC)** | 2026-08-17T23:37:07.782077+00:00 / 2026-08-17T23:46:24.398662+00:00 (543.61 s engine time); `cap_rows=312696 cap_fallback=35268 cap_missing=7291` |
| **Output** | `DATES\|54`, rows 2013-02..2018-11 with PROGRESSIVE per-spec collapse (SPECMETA periods: GROSS 8, MOM_3 8, MOM_6 3, QUALITY_COMPOSITE 3, MOM_12/MOM_9/QUALITY_MOMENTUM 35, RESIDUAL_6 42) — each specification dies at a different date and never returns |
| **Raw log** | `artifacts/qc_stage0_20260817/run6_monthly_B_r010.log`, 73 lines, exact-file sha256:`a0149c5dd9c03b66a0a1b095451f563d364233eaf7bd5ed2ae6b8c07bd8fb9aa` |
| **Validity** | **INVALIDATED** — a second, distinct state-machine defect truncated coverage per specification; not honest refusals |

### Zombie names: the root cause behind the per-spec die-off

The R-008 spiral fix worked exactly as designed — rows recover past 2017-01
and per-spec retries are visible — but a deeper defect surfaced once binds
could retry: a name whose market data simply ENDS without any delisting
event (common in B_core's broad cross-section) stays trapped in the last
bound book at an entry price that can never be marked again. The per-key
drift turnover for that book therefore refused every later month, and
because the bind gated on turnover, each specification died permanently the
first time its own long/short book trapped such a "zombie" name — hence the
staggered per-spec death dates instead of R-008's single cliff. A_large
(R-009) never trapped one; B_core traps them readily.

Fix `d305ea0` removes the entire class rather than patching the instance:
**turnover is a cost input and never gates a result row.** The bind always
proceeds; a month whose prior book cannot be priced emits an EMPTY turnover
field (declared unavailability), and the frozen analyser accepts it,
charges the conservative full 1.0 one-way turnover for that month — the
same convention the local battery's `net_of_costs` has always used — and
disclosures `unavailable_turnover_periods` per construction. The same
class existed in the local battery (`long_short_returns` dropped the
month's RETURN when a drift refused — selective-sample contamination) and
is fixed identically. Pinned by a zombie-name LEAN-stub simulation that
round-trips the algorithm's own log through the real parser and analyser,
plus a local wiped-out-book return-retention test; four reverse mutations
(bind gate, local gate, parser strictness, analyser refusal) all redden.
**PENDING independent review together with `49e8160`; B_core reruns after
as a new R-number.**

## R-011 — Stage 0 monthly battery, B_core, zombie-name fix (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery, 10 specifications (rerun of R-010) |
| **Research look** | Counted real-market run (run-level count 11 → 12); 40 repeated cells emitted |
| **Source commit** | `e2ed7eb` (contains Claude fixes `49e8160` and `d305ea0`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `f571e516a6fa8e55689030150e505d30af5ac97226051493770a24ab159f2330` (`ACTIVE_UNIVERSE="B_core"` rewrite; recorded in `run7_monthly_B_r011.json`) |
| **QC project** | `35290755` — requested `7. MONTHLY_BATTERY_B_CORE - 20260817`, returned `7 MONTHLY_BATTERY_B_CORE - 20260817` |
| **Compile ID** | `d681949544dcd20d117dd6fee048eb10-1a9ee502e4a13d70722065662d8df838` |
| **Backtest ID** | `a6d44d74ba1f9497fd87cd588c0dca6c` |
| **Launched / completed (UTC)** | 2026-08-18T00:11:51.703542+00:00 / 2026-08-18T00:20:06.844904+00:00; 32,054,443 data points; `cap_rows=312696 cap_fallback=35268 cap_missing=7291` (identical universe numbers to R-006/R-008/R-010) |
| **Output** | COMPLETE: all ten specs, `DATES\|142` = 142 rows (2013-02..2024-11, same depth as A_large's R-009), 10 SPECMETA lines with per-spec periods 116..133 (vs R-010's collapsed 3..42). The raw cloud log **round-trips through the frozen parser** (1,233 spec-rows). Unavailable-turnover fields present as designed: 89/54/94 rows (long_short/long_only_10/long_only_20) spread across ALL ten specifications (8–18 dates each) — every spec chain survived a trapped zombie name and retried instead of dying. Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run7_monthly_B_r011.log`, 161 lines, exact-file sha256:`351665870750f3505bd5bfec48a85220faad9dcbd27f746f378c7e1dfefb70f9` |
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`); the ~7% of months with unavailable turnover are each charged the conservative full 1.0 one-way at analysis, with counts disclosed per construction |

The zombie-name defect is now closed in the cloud, not only in simulation:
B_core — the universe that killed R-006 (weekend labels), R-008 (refusal
spiral), and R-010 (zombie names) — has produced its first complete,
parseable monthly-battery output at full 142-date depth. Monthly coverage
of Stage 0 now has both A_large (R-009) and B_core (R-011) awaiting review;
C_broad is next.

## R-012 — Stage 0 monthly battery, C_broad, zombie-name fix (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery, 10 specifications, universe C_broad (first C_broad monthly attempt of the campaign) |
| **Research look** | Counted real-market run (run-level count 12 → 13); 40 new cells emitted |
| **Source commit** | `7b588d4` (contains Claude fixes `49e8160` and `d305ea0`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `9b455f64c120022983bb15fddbbe5f16f77605d6eb31053bf683b9e9420c3d25` (`ACTIVE_UNIVERSE="C_broad"` rewrite; recorded in `run8_monthly_C_r012.json`) |
| **QC project** | `35291038` — requested `8. MONTHLY_BATTERY_C_BROAD - 20260817`, returned `8 MONTHLY_BATTERY_C_BROAD - 20260817` |
| **Compile ID** | `f3266e1163ce99faba8534d99b4cd159-082843e364531931bf059215337c6f82` |
| **Backtest ID** | `6af91e4542fec9cc4d7a4324d03f0a00` |
| **Launched / completed (UTC)** | 2026-08-18T00:21:33.564735+00:00 / 2026-08-18T02:50:30.284162+00:00; 34,641,380 data points; `cap_rows=429848 cap_fallback=52239 cap_missing=12771`. The first `wait` attempt dropped at ~72% on a transient local DNS failure (`getaddrinfo failed`) and was re-attached; the cloud run was unaffected. The evidence JSON retains the stale `unresolved_reason` field beside `status=completed` as an honest record of that interruption. |
| **Output** | COMPLETE: all ten specs, `DATES\|140` = 140 rows (2013-02..2024-11), 10 SPECMETA lines with per-spec periods 98..126 and median names 1,664–2,392 (broad universe as designed). The raw cloud log **round-trips through the frozen parser** (1,089 spec-rows). Unavailable-turnover fields present as designed: 164/121/186 rows (long_short/long_only_10/long_only_20) spread across ALL ten specifications (7–22 dates each) — more than B_core's 89/54/94, consistent with a broader universe holding more zombie names. Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run8_monthly_C_r012.log`, 159 lines, exact-file sha256:`98ce6c4f02b43f2a547a494f521ec507919aeea7d149da4c8bbac649580f33e8` |
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`); the ~12–17% of months with unavailable turnover are each charged the conservative full 1.0 one-way at analysis, with counts disclosed per construction |

The monthly leg of Stage 0 is now complete in the cloud: A_large (R-009),
B_core (R-011), and C_broad (R-012) all produced full-depth, parseable
output on the same fixed code, all awaiting the same independent review.
Next in the serial plan: the short battery (A_large, then B_core, then
C_broad), then the three benchmarks.

## R-013 — Stage 0 short battery, A_large, packed-format refusal (REFUSED)

| Field | Value |
|---|---|
| **Alpha / specification** | Short battery, 5 specifications, universe A_large |
| **Research look** | Counted real-market run (run-level count 13 → 14); **zero cells emitted** — the algorithm refused |
| **Source commit** | `f470ee6` (short battery file itself last changed at `ac96d47`; the R-010 zombie fix `d305ea0` touched the monthly battery only) |
| **Uploaded source SHA-256** | `b99c7dda8f1adab2ce0b572c6f163b926cc0b2df2f0f14cfb3f5888aa5b481c3` (`ACTIVE_UNIVERSE="A_large"` rewrite; recorded in `run9_short_A_r013.json`) |
| **QC project** | `35295425` — requested `9. SHORT_BATTERY_A_LARGE - 20260817`, returned `9 SHORT_BATTERY_A_LARGE - 20260817` |
| **Compile ID** | `7bb84f7834dcb4c9d1f2598a0c53eead-27e0bb70576f053089ad7d4b1c47be75` |
| **Backtest ID** | `8c549f41169f85ffd6bc4819fe0090b3` |
| **Launched / completed (UTC)** | 2026-08-18T02:52:20.743710+00:00 / 2026-08-18T02:54:01.612704+00:00; 27,300,655 data points; `cap_rows=178769 cap_fallback=16826 cap_missing=3206` |
| **Output** | `INCOMPLETE\|missing_date_specs\|2016-01-29` and **no B64BLOCK payload at all**. `DATES\|533` declared; SPECMETA shows MAX_20 at periods=532 while the other four specs are at 533 — MAX_20 is missing exactly one date, and the packed emitter's all-or-nothing rule (every date must carry all five specs) refused the entire output. Fail-closed worked: nothing partial or corrupt was emitted, and no statistic was or could be observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run9_short_A_r013.log`, 15 lines, exact-file sha256:`dffe320d0b1823096de06d3d4ced1dcdffaad5071a7ade9159523291dc250bd0` |
| **Validity** | **REFUSED** — no results exist; a rerun on fixed code will be a new R-number |

### Root cause: the packed format cannot say "this spec is absent today"

Per-spec ragged dates are ordinary and honest: the monthly battery's ROW
format discloses them via SPECMETA (R-011's per-spec periods were 116..133
out of 142), and the short battery computes its rows the same way — `_settle`
legitimately skips a spec-date when usable names fall below MIN_NAMES, when
a held name has no outcome, or when exit turnover is unpriceable (the
zombie-name mechanism of R-010, to which MAX_20's extreme-volatility book is
especially exposed; which of the three gates fired on 2016-01-29 is not
observable from the refused log). But the packed `b64block_date_u32_i32x4_u16x3`
layout has no absence channel, so its emitter demands every date × every
spec and refuses everything otherwise. R-002 passed with 534/534 full dates
by luck; this run hit one ragged spec-date and the refusal withheld 2,664
honest spec-date cells because one was absent. The short battery also still
gates result rows on turnover (`_settle`), contradicting the R-010 contract
that turnover is a COST input, never a gate. Fix round follows: an absence-
aware packed layout plus turnover-unavailability sentinel, with the v1
decoder retained so R-002's historical logs stay readable.

## R-014 — Stage 0 short battery, A_large, absence-aware format (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Short battery, 5 specifications, universe A_large (rerun of R-013) |
| **Research look** | Counted real-market run (run-level count 14 → 15); 20 repeated cells emitted |
| **Source commit** | `075e982` (contains Claude fixes `49e8160`, `d305ea0`, `46221db`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `08598e849a9546142a010b6fd9be491438a878146a35c1922d8f612a53c57771` (`ACTIVE_UNIVERSE="A_large"` rewrite; recorded in `run10_short_A_r014.json`) |
| **QC project** | `35296236` — requested `10. SHORT_BATTERY_A_LARGE - 20260817`, returned `10 SHORT_BATTERY_A_LARGE - 20260817` |
| **Compile ID** | `4dfba63bcc3f5e4f6e04ef6422b3b4a1-99fb9a7542762222e8ba20bb7a31a6e6` |
| **Backtest ID** | `0c51fbeb49fa4291f53242f888646e14` |
| **Launched / completed (UTC)** | 2026-08-18T03:18:21.954651+00:00 / 2026-08-18T03:19:33.127045+00:00; 27,300,655 data points; `cap_rows=178769 cap_fallback=16826 cap_missing=3206` — identical universe numbers to R-013, confirming the same computation now reports instead of refusing |
| **Output** | COMPLETE: `DATES\|533`, layout `b64block_date_u32_mask_u8_i32x4_u16x3` (the R-013 fix), SPECMETA per-spec periods 533/533/532/533/533. The raw cloud log **round-trips through the frozen parser**: 2,664 spec-rows, 2012-04-04..2024-12-19. MAX_20's single absent date is exactly R-013's `2016-01-29`, now disclosed by the presence mask instead of refusing the run. Zero unavailable-turnover cells (the sentinel path was not needed on this universe). Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run10_short_A_r014.log`, 69 lines, exact-file sha256:`5a6224cd2c9d43f023a159e018d5bbc4ada70adb0cbfa4679a13f5711a760cbd` |
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

The R-013 defect is closed in the cloud: the identical A_large computation
that refused on 2026-08-18 (same cap statistics, same 27.3M data points,
same 533 dates, same single ragged MAX_20 date) now emits all 2,664 honest
spec-date cells with the one absence declared. Note this run supersedes the
role of R-002's A_large leg for Stage 0 purposes; R-002 remains in the
ledger untouched and its v1 logs remain decodable. Next in the serial plan:
short B_core, short C_broad, then the three benchmarks.

## R-015 — Stage 0 short battery, B_core, absence-aware format (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Short battery, 5 specifications, universe B_core |
| **Research look** | Counted real-market run (run-level count 15 → 16); 20 cells emitted (repeat of R-002's B_core leg on corrected methodology) |
| **Source commit** | `c9d8a4f` (contains Claude fixes `49e8160`, `d305ea0`, `46221db`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `6b8927bc54244364528ce4b88d5e68d77264ab4a4a674297cf6af17741eb527f` (`ACTIVE_UNIVERSE="B_core"` rewrite; recorded in `run11_short_B_r015.json`) |
| **QC project** | `35296313` — requested `11. SHORT_BATTERY_B_CORE - 20260817`, returned `11 SHORT_BATTERY_B_CORE - 20260817` |
| **Compile ID** | `cb0e2c3cc08ac6458900486f61e66301-9018086f5a085488628cbc7150b284da` |
| **Backtest ID** | `a6d824d8ff110932609d44f327e57b1d` |
| **Launched / completed (UTC)** | 2026-08-18T03:20:35.785136+00:00 / 2026-08-18T03:26:20.703864+00:00; 31,956,942 data points; `cap_rows=312696 cap_fallback=35268 cap_missing=7291` (the same B_core universe numbers as the monthly runs) |
| **Output** | COMPLETE: `DATES\|533`, masked layout, per-spec periods 531/521/508/527/528 — far more ragged than A_large's 532..533, so **this run would have been refused outright by the v1 all-or-nothing format**; the R-013 fix is what makes B_core's short battery reportable at all. The raw cloud log **round-trips through the frozen parser**: 2,615 spec-rows, 2012-04-04..2024-12-19. Zero unavailable-turnover cells. Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run11_short_B_r015.log`, 69 lines, exact-file sha256:`cc8bd06b71c3d9be412721c1432c3fe2777cf42781bb75a9a9a62993af2f88bb` |
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

Short-battery coverage now: A_large (R-014) and B_core (R-015) complete
awaiting review. B_core's 25 absent MAX_20 dates (and 5–12 for the other
specs) are the honest cost of a mid-cap universe with more disappearing
names; every absence is declared per date by the presence mask and per spec
by SPECMETA. Next: short C_broad, then the three benchmarks.

## R-016 — Stage 0 short battery, C_broad, absence-aware format (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Short battery, 5 specifications, universe C_broad (first C_broad short attempt of the campaign) |
| **Research look** | Counted real-market run (run-level count 16 → 17); 20 new cells emitted |
| **Source commit** | `802c436` (contains Claude fixes `49e8160`, `d305ea0`, `46221db`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `1284a5b3b2100ac8042cf6cc104fea496a818e0645969e343e8af5d24bec0ebe` (`ACTIVE_UNIVERSE="C_broad"` rewrite; recorded in `run12_short_C_r016.json`) |
| **QC project** | `35296502` — requested `12. SHORT_BATTERY_C_BROAD - 20260817`, returned `12 SHORT_BATTERY_C_BROAD - 20260817` |
| **Compile ID** | `aa27f65f4bae9cdd25d83c375fb96eb8-b1278e0eec0128aa551d53ba3ab8646d` |
| **Backtest ID** | `8d5cf84c274b74bf9141c1a37aba3c2e` |
| **Launched / completed (UTC)** | 2026-08-18T03:27:17.192922+00:00 / 2026-08-18T03:37:09.078093+00:00; 34,541,299 data points; `cap_rows=429848 cap_fallback=52239 cap_missing=12771` (the same C_broad universe numbers as monthly R-012) |
| **Output** | COMPLETE: `DATES\|532`, masked layout, per-spec periods 523/513/496/519/519 — the most ragged of the three universes, again unreportable under the v1 all-or-nothing format. The raw cloud log **round-trips through the frozen parser**: 2,570 spec-rows, 2012-04-04..2024-12-19. Zero unavailable-turnover cells. Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run12_short_C_r016.log`, 69 lines, exact-file sha256:`da0ac76705706c0763992cc60ed88b45929338eb47d6706b48782b63d29c0044` |
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

Both alpha families are now complete in the cloud on the fixed code across
all three universes: monthly (R-009, R-011, R-012) and short (R-014, R-015,
R-016), all PENDING_REVIEW on the same review range. Only the three
equal-weight benchmark runs remain; they are not alpha cells.

*Current-status note (2026-08-18, closes review finding S0R2-001): the
paragraph above described the state at battery time and is superseded —
all nine runs were upgraded to VALID on owner acceptance (`2be903f`) and
the single analyser pass has since run (entry A-001 below).*

## R-017 — Stage 0 universe benchmark, A_large, silent die-off (INVALIDATED)

| Field | Value |
|---|---|
| **Alpha / specification** | Equal-weight universe benchmark, A_large — not an alpha cell |
| **Research look** | Counted real-market run (run-level count 17 → 18); zero alpha cells |
| **Source commit** | `966d12f` (`research/lean/universe_benchmark.py` untouched by any of the R-006..R-013 fixes) |
| **Uploaded source SHA-256** | `f91e1bb1bb9aebe8f1c1cade36d60e73bce0ed6a3e13c04419cbbc299a8097c6` (`ACTIVE_UNIVERSE="A_large"` rewrite; recorded in `run13_benchmark_A_r017.json`) |
| **QC project** | `35296819` — requested `13. UNIVERSE_BENCHMARK_A_LARGE - 20260817`, returned `13 UNIVERSE_BENCHMARK_A_LARGE - 20260817` |
| **Compile ID** | `ef808bfb0af7fee3170d53dda38d49a0-ba19fc5003330f64153fb8c7aa6f9d0e` |
| **Backtest ID** | `22328e264fae96c5d9f1742819e3cdc4` |
| **Launched / completed (UTC)** | 2026-08-18T03:38:04.891513+00:00 / 2026-08-18T03:39:29.140044+00:00; 27,298,298 data points |
| **Output** | `DATES\|48` with 48 BROW rows, 2012-01..**2015-12 only** — the algorithm processed thirteen years of data and silently reported four. The log is internally consistent (declared count matches rows, parser accepts it); only the expected-coverage arithmetic (≈156 months for 2012–2024) exposes the loss. No statistic was computed from the series. |
| **Raw log** | `artifacts/qc_stage0_20260817/run13_benchmark_A_r017.log`, 55 lines, exact-file sha256:`6d12a14da5f0dd8eb6210d4e053f9a5709f062f3cda8582dd24fb7b14d37c75e` |
| **Validity** | **INVALIDATED** — a 2012–2015 series is unusable as the 2012–2024 benchmark; rerun on fixed code will be a new R-number |

### Root cause: the R-010 zombie die-off, third instance, in the one file no fix touched

`_bind_staged_entry` gates the monthly bind on turnover: when
`_drift_turnover` returns None (a held name with no outcome — the zombie
pattern that stalls in January 2016 on every battery), the bind returns
early and `previous_weights` keeps the stale book. The zombie never prices
again, so every later month's turnover is None, every later bind refuses,
and the series dies permanently while the run "completes" normally. This
is exactly R-010's defect; `d305ea0` fixed it in the monthly battery and
`46221db` fixed its format-level cousin in the short battery, but the
benchmark kept its own private copy of the gated bind. Unlike R-013's
fail-closed refusal, this failure is **fail-silent**: the output passes
every internal consistency check and would have quietly become the
denominator under every long-only result. Fix round follows: bind always;
unpriceable turnover becomes a declared-unavailability empty field charged
at the conservative full 1.0 by the analyser; a genuinely unpriceable
month's return stays absent (visible as a month gap) but can no longer
poison its successors.

## R-018 — Stage 0 universe benchmark, A_large, fixed bind (STALE)

| Field | Value |
|---|---|
| **Alpha / specification** | Equal-weight universe benchmark, A_large (rerun of R-017) — not an alpha cell |
| **Research look** | Counted real-market run (run-level count 18 → 19); zero alpha cells |
| **Source commit** | `5b5184a` (contains Claude fixes `49e8160`, `d305ea0`, `46221db`, `5b5184a`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `a45120e895a1b83ae94862b75dd8181fd9ab0750952d39803bd98e554f5803b6` (`ACTIVE_UNIVERSE="A_large"` rewrite; recorded in `run14_benchmark_A_r018.json`) |
| **QC project** | `35297525` — requested `14. UNIVERSE_BENCHMARK_A_LARGE - 20260817`, returned `14 UNIVERSE_BENCHMARK_A_LARGE - 20260817` |
| **Compile ID** | `e9b0641659d9efa86f73a20d8f9b8fd0-9f71c2f6d2cf0891266b7ded064a062a` |
| **Backtest ID** | `9be317244e6260b8855785dde71df2e1` |
| **Launched / completed (UTC)** | 2026-08-18T03:58:20.313086+00:00 / 2026-08-18T03:58:58.699318+00:00 |
| **Output** | COMPLETE: 149 BROW rows, 2012-01..2024-11 — versus R-017's 48 rows dead at 2015-12 on the same universe. The raw cloud log **round-trips through the frozen benchmark parser**. Seven months absent from the full 156-month grid: 2016-01 (the zombie month that killed R-017, now honestly absent instead of fatal), 2019-07, 2022-01, 2022-02, 2022-09, 2023-09 (other unpriceable books), and 2024-12 (end boundary — the final book settles after END, matching the batteries' 2024-11 endpoint). Five months carry declared-unavailable turnover (the recovery rebalances after unpriceable books), each to be charged the conservative full 1.0 at analysis. Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run14_benchmark_A_r018.log`, 156 lines, exact-file sha256:`0a391739a89910b78980c7689b924aceb0881c55b719532f7d90daea2a9165ff` |
| **Validity** | **STALE** — superseded by R-022, the same computation on the underfill-recording contract (`39b3b89`); R-022's 149 shared months match this run's returns exactly |

The R-017 die-off is closed in the cloud: the same A_large benchmark
computation now reports thirteen years instead of four, with every
unpriceable month visible as a disclosed gap rather than a silent
truncation of everything after it.

## R-019 — Stage 0 universe benchmark, B_core, biased month coverage (INCONCLUSIVE)

| Field | Value |
|---|---|
| **Alpha / specification** | Equal-weight universe benchmark, B_core — not an alpha cell |
| **Research look** | Counted real-market run (run-level count 19 → 20); zero alpha cells |
| **Source commit** | `6d3c000` |
| **Uploaded source SHA-256** | `bc87fd277cddc94ca5c6db5e34d91fddd671949eb51272ab12833ffe28bf9455` (`ACTIVE_UNIVERSE="B_core"` rewrite; recorded in `run15_benchmark_B_r019.json`) |
| **QC project** | `35297590` — requested `15. UNIVERSE_BENCHMARK_B_CORE - 20260817`, returned `15 UNIVERSE_BENCHMARK_B_CORE - 20260817` |
| **Compile ID** | `d383f3d05eaf2c08c0a3d9a65eb95fec-f697135a16d509fe24abe178ebd9b5a7` |
| **Backtest ID** | `9e2441dd4332990c207e7d4e737ec183` |
| **Launched / completed (UTC)** | 2026-08-18T03:59:52.068279+00:00 / 2026-08-18T04:01:33.081260+00:00 |
| **Output** | Parses cleanly: 94 BROW rows, 2012-01..2024-10, 31 months with declared-unavailable turnover. The R-017 die-off is confirmed fixed (gaps recover instead of cascading). But **62 of 156 months are absent**, clustered in 2018–2024's heavy-delisting stretches. |
| **Raw log** | `artifacts/qc_stage0_20260817/run15_benchmark_B_r019.log`, 101 lines, exact-file sha256:`b05e5d998c44abd02800073b9d6dc801a59f534227f02f3ce4d3c7944ac0e660` |
| **Validity** | **INCONCLUSIVE** — every emitted number is correct per its contract, but a baseline missing 40% of months in a systematically zombie-clustered pattern cannot serve as the honest line under long-only results |

### Root cause: all-names-or-nothing settlement cannot scale to broad books

`_settle` emits a month only when EVERY entered name is priceable on the
exact settlement session (`len(outcomes) == len(pending["entry"])`). A
~300-name A_large book rarely fails that (R-018 lost 6 mid-period months);
a ~1,700-name B_core book fails it 40% of the time, and the failures
cluster exactly in stressed, delisting-heavy periods — a selective sample
that overstates calm months, which the project methodology explicitly
forbids for baselines ("include missing baseline rows rather than allowing
selective samples"; "record refusals and underfill instead of dropping
them"). Fix round follows: the month's return is computed over the priced
subset (≥ MIN_NAMES still required) with BOTH counts — priced and entered
— disclosed in an extended BROW row, so underfill is recorded instead of
dropped. Excluding mid-month zombies overstates the benchmark in crashes,
which penalises rather than flatters alpha claims measured against it —
conservative in the correct direction for a baseline. All three benchmark
universes will be rerun on the extended contract for uniformity.

## R-020 — Stage 0 universe benchmark, B_core, underfill-recording (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Equal-weight universe benchmark, B_core (rerun of R-019) — not an alpha cell |
| **Research look** | Counted real-market run (run-level count 20 → 21); zero alpha cells |
| **Source commit** | `39b3b89` (contains Claude fixes `49e8160`, `d305ea0`, `46221db`, `5b5184a`, `39b3b89`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `b080124852f142727c3b2e8d4cb1e1dd818f3cf73129c4e5cb87efa369ca7b5f` (`ACTIVE_UNIVERSE="B_core"` rewrite; recorded in `run16_benchmark_B_r020.json`) |
| **QC project** | `35298290` — requested `16. UNIVERSE_BENCHMARK_B_CORE - 20260817`, returned `16 UNIVERSE_BENCHMARK_B_CORE - 20260817` |
| **Compile ID** | `975958cef0be3ab42d6154ee3f24f28e-7caa049758ef091ccc7bd92dd1b64bc8` |
| **Backtest ID** | `03cbf3fbcda0190b408f156f876781f6` |
| **Launched / completed (UTC)** | 2026-08-18T04:18:47.345291+00:00 / 2026-08-18T04:20:57.961762+00:00 |
| **Output** | COMPLETE: **155 of 156 months** (only the 2024-12 end boundary absent, matching the batteries' 2024-11 endpoint), versus R-019's 94. The raw cloud log **round-trips through the frozen benchmark parser** (five-field rows). 61 months carry disclosed underfill — worst coverage 99.83% priced, i.e. the old all-names gate was discarding whole months over 1–3 unpriceable names out of ~1,700. 60 months carry declared-unavailable turnover, each charged the conservative full 1.0 at analysis with counts disclosed. Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run16_benchmark_B_r020.log`, 162 lines, exact-file sha256:`dbf6ad69c3720e0453318d58449b01dcab532aa4773a000c3f5b2b5e04ecffda` |
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

The R-019 coverage collapse is closed in the cloud: B_core's baseline now
spans the full period with every underfilled month recorded rather than
dropped. C_broad and the A_large rerun (for five-field uniformity across
all three universes) remain.

## R-021 — Stage 0 universe benchmark, C_broad, underfill-recording (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Equal-weight universe benchmark, C_broad — not an alpha cell |
| **Research look** | Counted real-market run (run-level count 21 → 22); zero alpha cells |
| **Source commit** | `cd21495` (contains Claude fixes `49e8160`, `d305ea0`, `46221db`, `5b5184a`, `39b3b89`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `1711a5eb6779ee6c9730231b806d6f3c6155812aae067defab2e725d1d5af116` (`ACTIVE_UNIVERSE="C_broad"` rewrite; recorded in `run17_benchmark_C_r021.json`) |
| **QC project** | `35298403` — requested `17. UNIVERSE_BENCHMARK_C_BROAD - 20260817`, returned `17 UNIVERSE_BENCHMARK_C_BROAD - 20260817` |
| **Compile ID** | `328ba81c396811cb5f76379174f4527c-d5ee65c509d8b4876977a9b235eb3d1e` |
| **Backtest ID** | `8ba1f192438bec65313dcd2133c124b1` |
| **Launched / completed (UTC)** | 2026-08-18T04:21:52.870250+00:00 / 2026-08-18T04:25:10.381972+00:00 |
| **Output** | COMPLETE: **155 of 156 months** (only the 2024-12 end boundary absent). The raw cloud log **round-trips through the frozen benchmark parser** (five-field rows). 86 months carry disclosed underfill — worst coverage 99.72% priced — and 85 months carry declared-unavailable turnover, each charged the conservative full 1.0 at analysis with counts disclosed. The broadest universe shows the most zombie churn, exactly as R-012/R-016 predicted. Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run17_benchmark_C_r021.log`, 162 lines, exact-file sha256:`aa8a09872e8eab1640d79ecc2eb4f4ed80fd2ba91dfb067dd4f6d757e7c777dc` |
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

Only the A_large benchmark rerun remains (five-field uniformity across all
three universes; its R-018 log predates the underfill-recording contract).

## R-022 — Stage 0 universe benchmark, A_large, underfill-recording (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Equal-weight universe benchmark, A_large (supersedes R-018 for five-field uniformity) — not an alpha cell |
| **Research look** | Counted real-market run (run-level count 22 → 23); zero alpha cells |
| **Source commit** | `01ce8f1` (contains Claude fixes `49e8160`, `d305ea0`, `46221db`, `5b5184a`, `39b3b89`, not yet independently reviewed) |
| **Uploaded source SHA-256** | `f2c6e240e6e83f6d7f4411d5eba8f074536ec2a688022a6050dad768214601c4` (`ACTIVE_UNIVERSE="A_large"` rewrite; recorded in `run18_benchmark_A_r022.json`) |
| **QC project** | `35298527` — requested `18. UNIVERSE_BENCHMARK_A_LARGE - 20260817`, returned `18 UNIVERSE_BENCHMARK_A_LARGE - 20260817` |
| **Compile ID** | `7dcffef48e4926fc953db6d9ac164774-dc838b3c9896aa50a9e1a2ecd7d93dfa` |
| **Backtest ID** | `022b32d7e7414bf945a73254a63eaea9` |
| **Launched / completed (UTC)** | 2026-08-18T04:25:56.576347+00:00 / 2026-08-18T04:27:06.095429+00:00 |
| **Output** | COMPLETE: **155 of 156 months** (only the 2024-12 end boundary absent). The raw cloud log **round-trips through the frozen benchmark parser** (five-field rows). 6 months carry disclosed underfill and 6 declared-unavailable turnover. **Replication check against R-018:** the 149 months both runs emitted have max absolute return difference **0.0** — the underfill contract changed nothing on full months and only recovered the six R-018 had dropped. Parsing only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage0_20260817/run18_benchmark_A_r022.log`, 162 lines, exact-file sha256:`b8ace1727a06f4d022e7c7130c0bd88d01fe0ccd90ad73668189f11160e94149` |
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

**The nine-run Stage 0 battery is complete on the fixed code.** Monthly:
R-009 (A_large), R-011 (B_core), R-012 (C_broad). Short: R-014 (A_large),
R-015 (B_core), R-016 (C_broad). Benchmark: R-022 (A_large), R-020
(B_core), R-021 (C_broad). All nine are PENDING_REVIEW on the same range
`49e8160`..`39b3b89`. No statistic has been observed from any of them; the
frozen analysers run once, with full run identities, only after the review
gate — so look accounting and result identity are recorded before any
statistic exists, exactly as the R-002 precedent required.

*Current-status note (2026-08-18, closes review finding S0R2-001): the
paragraph above was written before the review gate cleared and is
superseded — the review pair was owner-accepted, the nine runs are
VALID (`2be903f`), and the single frozen-analyser observation exists as
entry A-001 immediately below.*

## A-001 — Stage 0 single frozen-analyser pass (OBSERVED, 2026-08-18)

The one preregistered observation of the Stage 0 battery. Owner accepted
the review pair and authorized this pass on 2026-08-18; the nine VALID
runs' entries were upgraded and committed (`2be903f`) BEFORE any
statistic was computed, so acceptance is recorded ahead of results.

| Field | Value |
|---|---|
| **What** | `scripts/analyse_qc_alpha_battery.py` run once over the monthly family (R-009/R-011/R-012) and once over the short family (R-014/R-015/R-016); `scripts/analyse_qc_benchmark.py` run once over R-022/R-020/R-021. No other statistic source exists for these runs. |
| **Code identity** | Analyser scripts byte-identical to independently reviewed head `de1beac` (the post-acceptance commits `c066b1e`/`2be903f` changed documents only). Executed on branch `user/claude/qc-stage0-analysis-20260818` at `2be903f`. |
| **Inputs** | The nine ledgered raw logs. The benchmark analyser's independently computed input hashes and a fresh SHA-256 of all six battery logs match this ledger's recorded hashes exactly (9/9). |
| **Outputs** | `artifacts/qc_stage0_20260817/analysis_monthly_20260818.json` (301,532 bytes, sha256 `a3ddf7ee84b595160d8ebb24c999a112c6e05ed78f9cbcab33b24e7a8f469963`), `analysis_short_20260818.json` (153,264 bytes, `f38ca4ade3bb5dc6417051a3cfec9447943af6b6c319cd3fbddf68a454fa3007`), `analysis_benchmark_20260818.json` (82,750 bytes, `211ec24a9953f6de1203e30ac4352afec517aee359809f0711089790a4067126`); machine-local, hashes recorded here. |
| **Multiplicity** | Family: QC alpha battery 2026-08-16, 180 cells. Bonferroni gate 0.05/180 = 2.7778e-4. Stationary block bootstrap, 20,000 draws, smallest attainable p 4.99975e-5 < gate (reachable, per the ABR-001 guard). This is the FIRST AND ONLY observation of the family; run-level look count stays 23; lifetime cell floor stays 428 under the repeated-look convention. |
| **Observation units** | Monthly family: calendar months (102–142 independent months per cell, varying by spec lookback and universe history). Short family: non-overlapping six-session cycles (~530 per cell). Benchmark: calendar months (155). The frozen bootstrap requires n ≥ 24; every cell meets it except one (below). |

**Results against the frozen gate:**

- **IC (the headline signal test): 0 of 44 defined cells pass.** Minimum
  ic_p = 2.70e-3 (QUALITY_COMPOSITE, A_large) — an order of magnitude
  above the gate.
- **Long-short (self-financing, beta-free): 0 of 44 defined cells pass.**
  Minimum p = 3.20e-3 (QUALITY_MOMENTUM, A_large, gross Sharpe 1.56).
- **Long-only: 6 of 88 defined cells pass** (2 of 44 LO10, 4 of 44
  LO20) on the frozen two-sided
  gross-mean-vs-zero test: A_large GROSS_PROFITABILITY LO20 (p=1.0e-4,
  142 mo, gross/net-25bps CAGR 15.7%/15.3%, Sharpe 0.97/0.94); B_core
  MOM_12_1 LO20 (p=2.5e-4, 124 mo, 18.5%/16.1%, 1.00/0.89); B_core
  QUALITY_MOMENTUM LO10 (p=1.5e-4, 130 mo, 17.3%/15.4%, 0.96/0.87) and
  LO20 (p=1.5e-4, 130 mo, 16.2%/14.5%, 0.96/0.87); C_broad MOM_6_1 LO10
  (p=1.5e-4, 102 mo, 22.6%/18.6%, 1.27/1.08) and LO20 (p=5.0e-5, 102 mo,
  20.7%/16.9%, 1.29/1.08).
- **Short battery: 0 of its 60 cells pass** on any hypothesis (closest:
  MAX_20 long-only p ≈ 4.0e-4–9.5e-4 across universes, still above the
  gate).
- **Insufficiency (disclosed, not dropped):** MULTI_ALPHA_COMPOSITE on
  A_large emitted only 23 months (its components' joint availability on
  the megacap universe), below the frozen bootstrap minimum of 24 —
  ic/long-short/long-only p-values are undefined for that spec-universe.
  Required count: 24; observed: 23; sufficiency: NOT MET.
- **Benchmarks (equal-weight, 155 months, not alpha cells):** A_large
  CAGR 12.8%, Sharpe 0.85, maxDD −27.6% (6 unavailable-turnover, 6
  underfilled months); B_core 12.6%, 0.73, −33.9% (60/61); C_broad
  14.2%, 0.76, −34.7% (85/86).

**Interpretation limits (stated with the result, not a post-hoc gate
change):** the frozen per-cell test is gross-mean-vs-zero. For long-only
constructions that series carries full market beta, and the equal-weight
benchmarks themselves (Sharpe 0.73–0.85 over the same 2012–2024 era)
would pass the same test — so the six passing long-only cells are NOT
evidence of stock-selection edge beyond the market. The beta-free reads
(IC and long-short) fail everywhere. The passing cells are also not
observation-matched to the benchmark (102–142 months vs 155; e.g.
C_broad MOM_6_1's maxDD of −10.3% over its 102 covered months against
the benchmark's −34.7% over 155 partly reflects the differing window,
not only selection). A cadence-matched benchmark-same-dates comparison
is exactly what the Stage 1 design adds; any claim beyond "these six
cells cleared the preregistered Stage 0 gate" requires it.

**Amendment to R-022 (closes review finding S0R-007):** R-022's phrase
"Parsing only; no statistic observed" was imprecise — the max-absolute-
difference replication check against R-018 was a numeric comparison of
raw return values performed outside the frozen analyser. It was an
identity check with no directional or performance content and is not
analyser output; the R-022 text stands unedited per the append-only
rule, with this entry as the clarification of record.

## R-005 — Stage 0 monthly battery, A_large, reviewed code (REFUSED)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery: MOM_3/6/9/12_1, RESIDUAL_MOM_6/12_1, GROSS_PROFITABILITY, QUALITY_COMPOSITE, QUALITY_MOMENTUM, MULTI_ALPHA_COMPOSITE |
| **Replication or new** | First Stage 0 execution on fully counter-reviewed code (post-`ac96d47`/FCR closures) |
| **Research look** | Counted real-market run (run-level count 5 → 6); zero emitted alpha cells |
| **Multiplicity family** | QC alpha battery 2026-08-16, 180 cells (repeated look; lifetime floor stays 428) |
| **Source commit** | `423a818` (contains merged `1457169` = PR #245 product tree; LEAN sources byte-identical to reviewed `main`) |
| **Uploaded source SHA-256** | `e15d800bd5fc444ab943164514819d3d10dd871b16ef3838bce2c60af0ec4982` (`alpha_battery_monthly.py`, `ACTIVE_UNIVERSE="A_large"` rewrite) |
| **QC project** | `35285587` — `1. MONTHLY_BATTERY_A_LARGE - 20260817` (QC displays the name without the dot) |
| **Compile ID** | `536ba0397b5aaee05599c4f894a04aa6-b781d55b4f49dfabcb81ae12f6998bab` |
| **Backtest ID** | `b141aeae803521352a74760573ffcda0` |
| **Launched / completed (UTC)** | 2026-08-17T21:02:23 / ~21:04 (64.22 s engine time, 27,299,669 points, 425k/s) |
| **Data period / universe** | 2012-01-01..2024-12-31; A_large: price ≥ $5, cap ≥ $10B, ADV20 ≥ $25M; `cap_rows=178769 cap_fallback=16826 cap_missing=3206` |
| **Raw log** | `artifacts/qc_stage0_20260817/run1_monthly_A.log`, 7 lines. Actual Windows-file SHA-256: `56cdb97757ac56ce2d215142177bb6801652c5582ad809995786f034024b8674`. Original driver/evidence JSON recorded LF-normalized SHA-256 `23fc9e859485b43bb68e541f1ccb50b02d78d75586bbd9f4f3f6493e50a1e2ed`; both are retained because QCS0R-003 found that the driver hashed text before Windows newline translation. |
| **Orders / holdings** | Volume $0.00, Holdings $0.00 — inert as designed |
| **Primary statistics** | **none** |
| **Validity** | **REFUSED** — `INCOMPLETE\|missing_specs=MULTI_ALPHA_COMPOSITE\|RESIDUAL_MOM_12_1\|RESIDUAL_MOM_6_1` |

### What happened and the open diagnosis

Both residual-momentum specifications produced zero usable rows across the
entire window, so `MULTI_ALPHA_COMPOSITE` (which consumes one of them) also
emitted nothing and the completeness guard withheld the whole run, including
the seven specifications that did produce data. This is the first cloud
execution of the corrected point-in-time factor machinery.

Working hypothesis, decided BEFORE the next run so it is falsifiable: the
corrected leave-one-out industry factor refuses a stock's whole 504-session
factor window if the stock's point-in-time Morningstar industry bucket has
fewer than three members with returns on ANY session in the window. Among
A_large's ~mega-cap cross-section most industries hold one or two members,
so the residual cross-section falls below `MIN_NAMES=30` on every score date
— a data-driven structural refusal, not a code fault. The alternative — a
factor-recording/selection-timing defect that starves the residual factor on
every universe — is distinguished by run 2 (B_core, required by the frozen
plan anyway): if B_core also refuses identically, treat it as a suspected
code defect, STOP Stage 0, and take the diagnosis back through review; if
B_core completes, the A_large refusal stands as this cell family's honest
result.

Also recorded: LEAN logged a deprecation warning for the
`add_universe(coarse, fine)` overload (non-fatal), and adjusted start dates
for six factor-file symbols (BCE, CVE, RCI, CNI, SJR, TCK).

## R-006 — Stage 0 monthly battery, B_core, reviewed code (REFUSED)

| Field | Value |
|---|---|
| **Alpha / specification** | Monthly battery, 10 specifications (same family as R-005) |
| **Replication or new** | Stage 0 execution on the same counter-reviewed source as R-005 |
| **Research look** | Counted real-market run (run-level count 6 → 7); zero emitted alpha cells |
| **Multiplicity family** | QC alpha battery 2026-08-16, 180 cells (repeated look; lifetime floor stays 428) |
| **Source commit** | `bfc9b8b` (the driver/log-evidence follow-up; uploaded LEAN bytes still derive from the reviewed PR #245 algorithm) |
| **Uploaded source SHA-256** | `428ef88bd9d39b1ca060ee82ef49dc5ede8802e6e900e83c1c1df0e7e823fa40` (`alpha_battery_monthly.py`, `ACTIVE_UNIVERSE="B_core"` rewrite) |
| **QC project** | `35285594` — `2. MONTHLY_BATTERY_B_CORE - 20260817` |
| **Compile ID** | `86b7cd76c8b0063c3444a288d49111d8-10dea6d5c90b29a72b09c4aa1958b967` |
| **Backtest ID** | `896f7f2c72b5acdb03859d79497973c3` |
| **Launched / completed (UTC)** | 2026-08-17T21:07:50.028845+00:00 / 2026-08-17T21:11:06.918222+00:00 (190.01 s engine time, 31,944,196 points, 168k/s) |
| **Data period / universe** | 2012-01-01..2024-12-31; B_core; `cap_rows=312696 cap_fallback=35268 cap_missing=7291` (identical to R-001's universe numbers) |
| **Raw log** | `artifacts/qc_stage0_20260817/run2_monthly_B.log`, 7 lines. Actual Windows-file SHA-256: `e2a038564d4254f41a773ee6103d910b862eb564305de3963dc446664203941a`. Original driver/evidence JSON recorded LF-normalized SHA-256 `8858e6f63b2f4cdfb3bed388fad89a4db14f90d0ad82baf1ff8a6391b1bc395b`; both are retained because QCS0R-003 found that the driver hashed text before Windows newline translation. |
| **Primary statistics** | **none** |
| **Validity** | **REFUSED** — identical `INCOMPLETE\|missing_specs=MULTI_ALPHA_COMPOSITE\|RESIDUAL_MOM_12_1\|RESIDUAL_MOM_6_1` |

### The hypothesis test this run was declared to be

R-005's thin-industry hypothesis is **falsified**: B_core's broad
cross-section refused identically, and the run was ~25× faster than R-001's
corrected-code run — the expensive residual path is clearly never receiving
usable factor input. Per the pre-declared decision rule, this is now treated
as a **suspected defect in the corrected point-in-time factor machinery**
(`_record_factor_returns` / `_factor_returns`, first cloud-executed in this
pair of runs). **Stage 0 is STOPPED at two of nine runs**; runs 3–9 are not
launched. The diagnosis moves to a local LEAN-stub integration harness — no
cloud compute may be used to debug unreviewed hypotheses — and any fix goes
back through the review loop before a rerun. Both refusals remain counted,
permanent ledger entries.

**Root cause CONFIRMED locally the same day (no further cloud access).** A
LEAN-stub simulation reproduced the exact refusal signature once it modeled
LEAN's real event timing: daily bars are labeled with the NEXT calendar day,
so the last bar of a month ending on a Friday arrives labeled
Saturday-the-1st — before the new month's universe selection exists. The
factor recorder keyed membership by the label's month, recorded those days
with empty industry buckets, and one poisoned day refused every 504-session
residual window spanning it; months end on Fridays roughly one in four, so
every window was poisoned and both residual specifications refused totally
while all non-membership specifications emitted. Fix `0f0611c` binds each
factor day to the membership actually in force at record time and makes
score-time lookups reuse exactly that recorded month key;
`tests/test_alpha_battery_monthly_sim.py` drives the real algorithm class
through the weekend-boundary event model and reddens under the reverted fix.
The Stage 1, short-battery, and benchmark algorithms hold no month-keyed
membership history and are unaffected. The fix awaits independent review
before any rerun; reruns will be new R-numbers.

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
