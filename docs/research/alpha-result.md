# Alpha result ledger

**Long-lived record of every QuantConnect run.** Rejected, inconclusive,
invalidated, stale and unavailable results are kept here permanently. An
unfavourable result is never deleted and never silently replaced by a
rerun; a rerun is a new entry that references the one it supersedes.

**This ledger is ACTIVE, not archived.** The programs recorded below are
closed, but the ledger itself is the repository's live look-accounting record:
every future real-outcome execution — including ACER's two authorized slots,
and including refusals, errors and accidental launches — appends a new `R-nnn`
entry here, and the lifetime cell floor keeps accruing across programs. The
2026-08-21 lifecycle reorganization briefly filed it under `docs/Archive/`;
that was corrected, because a look ledger read as history is a look ledger
someone restarts (CDR-004).

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

Independent review (`docs/Archive/Review/REVIEW_2026-08-16_QUANTCONNECT_ALPHA_BATTERY.md`)
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
(`docs/Archive/Review/REVIEW_2026-08-17_QC_STAGE0_LAUNCH_COUNTERREVIEW.md`); the
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
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`); no rerun required |

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
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`); the ~7% of months with unavailable turnover are each charged the conservative full 1.0 one-way at analysis, with counts disclosed per construction |

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
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`); the ~12–17% of months with unavailable turnover are each charged the conservative full 1.0 one-way at analysis, with counts disclosed per construction |

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
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

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
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

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
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

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
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

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
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

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
| **Validity** | **VALID** — accepted 2026-08-18: independent review (Cursor/Grok 4.6) and Claude counter-review of `81db126..de1beac` both accepted the generating code with no result-changing defect, and the owner accepted the review pair the same day (see `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` and `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`) |

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

## R-023 — Stage 1 replications, A_large, reviewed code (VALID)

First Stage 1 cloud run, on fully reviewed code (`602dc0b` chain:
author + fresh-Claude + two Cursor rounds), launched under the owner GO
of 2026-08-18 (handoff 7af/7ag).

| Field | Value |
|---|---|
| **Alpha / specification** | Stage 1 replications: REP_H52 (52-week-high proximity), REP_IDV (idiosyncratic-volatility proxy); monthly formation, 21-session holds |
| **Multiplicity family** | Stage 1 replications 2026-08-18, 24 cells, gates frozen in `scripts/analyse_qc_alpha_stage1.py` (stage 0.05/24; lifetime floor 428 → 452 at the family's single observation) |
| **Research look** | Counted real-market run (run-level count 23 → 24); no statistic observed |
| **Source commit** | `875d003` (merged main; driver delta independently reviewed the same day) |
| **Uploaded source SHA-256** | `d425add463d211f64c695cce97e8962387099c1f2df1bd510723a16f6165a9c0` (`ACTIVE_UNIVERSE="A_large"` rewrite; recorded in `run19_stage1_A.json`) |
| **QC project** | `35331806` — requested `19. STAGE1_REPLICATIONS_A_LARGE - 20260818`, returned `19 STAGE1_REPLICATIONS_A_LARGE - 20260818` |
| **Compile ID** | `65204785eed2028b98dcd360683eb375-0ada5e2487422ef21bcfd7d78261ea95` |
| **Backtest ID** | `79013bc214c12d5ab9463857fef6e363` |
| **Launched / completed (UTC)** | 2026-08-18T21:31:01.441083+00:00 / 2026-08-18T21:32:10.519438+00:00 |
| **Output** | STRUCTURALLY COMPLETE: both specs declared and parsed; DATES 142; 281 spec-date rows (REP_H52 140, REP_IDV 141 — per-spec raggedness round-tripped through the SPECMETA inventory, the first cloud proof of the S0R-001/R-007 hardening); coverage 2013-01..2024-10 (300-session warm-up head, 21-session settle tail); 4 declared-unavailable turnovers (all long-only-20), charged 1.0 at analysis; 0 INCOMPLETE lines; `cap_rows=178769 cap_fallback=16826 cap_missing=3206`. Orders/holdings $0.00 — inert as designed. Structural inspection only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage1_20260818/run19_stage1_A.log`, 153 lines, exact-file sha256:`85aa8e0aecd0775758abd8624c487a7d9e9b9d94cc758a441a96b242bbea0668` |
| **Validity** | **VALID** — reviewed code, complete output, analysed once in A-002 |

## R-024 — Stage 1 replications, B_core, reviewed code (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Stage 1 replications: REP_H52, REP_IDV (as R-023) |
| **Multiplicity family** | Stage 1 replications 2026-08-18, 24 cells (as R-023) |
| **Research look** | Counted real-market run (run-level count 24 → 25); no statistic observed |
| **Source commit** | `875d003` |
| **Uploaded source SHA-256** | `9227d81a2605da86f93635dbc0fafc53232030065526b6f136a2420440f5c68c` (`ACTIVE_UNIVERSE="B_core"` rewrite; recorded in `run20_stage1_B.json`) |
| **QC project** | `35331896` — `20. STAGE1_REPLICATIONS_B_CORE - 20260818` |
| **Compile ID** | `928c4cda9df1bb798f90848eef872b96-56aa99aed02fb6d09afc6e891ab7bc35` |
| **Backtest ID** | `99c98809508f74f917b07036afd9d13d` |
| **Launched / completed (UTC)** | 2026-08-18T21:33:38.416479+00:00 / 2026-08-18T21:37:24.099760+00:00 |
| **Output** | STRUCTURALLY COMPLETE: both specs; DATES 128; 248 spec-date rows (REP_H52 123, REP_IDV 125), coverage 2013-01..2024-09/10. Lower date coverage than A_large's 142 is the disclosed settle-side contract on the zombie-heavier universe (a spec-date needs every book name priced at settlement; drops are visible via SPECMETA periods), NOT a series die-off — the bind-side channel worked as designed, with 74 declared-unavailable turnover cells across the six constructions charged 1.0 at analysis. 0 INCOMPLETE lines; `cap_rows=312696 cap_fallback=35268 cap_missing=7291`. Inert. Structural inspection only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage1_20260818/run20_stage1_B.log`, 139 lines, exact-file sha256:`6c7a05e07efb5329a7310ffc46ba84145f798c8f37c050b40e7dc24936f28963` |
| **Validity** | **VALID** — reviewed code, complete output, analysed once in A-002 |

## R-025 — Stage 1 replications, C_broad, reviewed code (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Stage 1 replications: REP_H52, REP_IDV (as R-023) |
| **Multiplicity family** | Stage 1 replications 2026-08-18, 24 cells (as R-023) |
| **Research look** | Counted real-market run (run-level count 25 → 26); no statistic observed |
| **Source commit** | `875d003` |
| **Uploaded source SHA-256** | `fa109519f1cf3a1c62abf04b38d94579edeba61b84fd7332d2e4bf379d2ee236` (`ACTIVE_UNIVERSE="C_broad"` rewrite; recorded in `run21_stage1_C.json`) |
| **QC project** | `35332045` — `21. STAGE1_REPLICATIONS_C_BROAD - 20260818` |
| **Compile ID** | `93678192cb74d1a8329dfb112838a4aa-507b4beaa16db59a5e99152af844ad13` |
| **Backtest ID** | `17e298a2d4f7b756c32f3520224a675b` |
| **Launched / completed (UTC)** | 2026-08-18T21:38:17.939566+00:00 / 2026-08-18T21:43:37.841048+00:00 |
| **Output** | STRUCTURALLY COMPLETE: both specs; DATES 117; 219 spec-date rows (REP_H52 110, REP_IDV 109), coverage 2013-01..2024-09/10. The coverage gradient across universes (A_large 142 → B_core 128 → C_broad 117 dates) tracks zombie density monotonically under the disclosed settle contract; 134 declared-unavailable turnover cells across the six constructions, charged 1.0 at analysis; 0 INCOMPLETE lines; `cap_rows=429848 cap_fallback=52239 cap_missing=12771`. Inert. Structural inspection only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage1_20260818/run21_stage1_C.log`, 128 lines, exact-file sha256:`76de5389e176297568eb25384d61edb8f10ee20376c2949d56ba37a21aaaf313` |
| **Validity** | **VALID** — reviewed code, complete output, analysed once in A-002 |

## R-026 — Stage 1 benchmark, A_large, reviewed code (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Stage 1 cadence-matched equal-weight benchmark (21-session cohorts) — not an alpha cell |
| **Research look** | Counted real-market run (run-level count 26 → 27); zero alpha cells; no statistic observed |
| **Source commit** | `875d003` |
| **Uploaded source SHA-256** | `7da083775ff2dde2c175891b0e443e76f506a6852d4ab88fce2d3e6a735e8d05` (`ACTIVE_UNIVERSE="A_large"` rewrite; recorded in `run22_s1bench_A.json`) |
| **QC project** | `35332210` — `22. STAGE1_BENCHMARK_A_LARGE - 20260818` |
| **Compile ID** | `63cf8fb63e44fc5c8c3891a9ab9f20c2-cc4d3af41150c1d6925b088de9d2a729` |
| **Backtest ID** | `b7b4e3b5b7a19581ca6739cd8c0e2d16` |
| **Launched / completed (UTC)** | 2026-08-18T21:44:26.806992+00:00 / 2026-08-18T21:45:07.053844+00:00 |
| **Output** | STRUCTURALLY COMPLETE: **154 gapless months** (2012-01..2024-10 — no warm-up head, 21-session settle tail), a strict superset of R-023's alpha dates, so the analyser's benchmark-same-dates matching cannot refuse. 5 declared-unavailable turnovers and 6 underfilled months disclosed (five-field BROW — first cloud proof of the S0R-002 port); 0 INCOMPLETE lines. Inert. Structural inspection only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage1_20260818/run22_s1bench_A.log`, 161 lines, exact-file sha256:`6cded4c9ebe3fb752b7f51f1bb4fd244f256ab67691c2e275e6e77987f050547` |
| **Validity** | **VALID** — reviewed code, complete output, analysed once in A-002 |

## R-027 — Stage 1 benchmark, B_core, reviewed code (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Stage 1 cadence-matched equal-weight benchmark — not an alpha cell |
| **Research look** | Counted real-market run (run-level count 27 → 28); zero alpha cells; no statistic observed |
| **Source commit** | `875d003` |
| **Uploaded source SHA-256** | `58781194e493fcb4dc72bdffd173574ff3f510b8cc7e1445561694848e57e5a4` (`ACTIVE_UNIVERSE="B_core"` rewrite; recorded in `run23_s1bench_B.json`) |
| **QC project** | `35332245` — `23. STAGE1_BENCHMARK_B_CORE - 20260818` |
| **Compile ID** | `647ffba8445641ba4cc2a1ababfa2c93-99139ae1b7f8bc41b0c3cedc8caae45c` |
| **Backtest ID** | `68d539d90a2db12a1e6e6743b1ed77ee` |
| **Launched / completed (UTC)** | 2026-08-18T21:45:55.836023+00:00 / 2026-08-18T21:48:38.753072+00:00 |
| **Output** | STRUCTURALLY COMPLETE: 154 gapless months (2012-01..2024-10); R-024's alpha dates verified a subset of the benchmark months. 33 declared-unavailable turnovers and 29 underfilled months disclosed; 0 INCOMPLETE lines. Inert. Structural inspection only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage1_20260818/run23_s1bench_B.log`, 161 lines, exact-file sha256:`39d04138eabb9e17856a4d1ef146d99e271d086fdfa4f380fd61a84e7f0d3c1b` |
| **Validity** | **VALID** — reviewed code, complete output, analysed once in A-002 |

## R-028 — Stage 1 benchmark, C_broad, reviewed code (VALID)

| Field | Value |
|---|---|
| **Alpha / specification** | Stage 1 cadence-matched equal-weight benchmark — not an alpha cell |
| **Research look** | Counted real-market run (run-level count 28 → 29); zero alpha cells; no statistic observed |
| **Source commit** | `875d003` |
| **Uploaded source SHA-256** | `40cfbe9125d8c59710209705e9b99d6d4558d3cd30d52744efac461245d5812d` (`ACTIVE_UNIVERSE="C_broad"` rewrite; recorded in `run24_s1bench_C.json`) |
| **QC project** | `35332356` — `24. STAGE1_BENCHMARK_C_BROAD - 20260818` |
| **Compile ID** | `609f5c9677443641e553f6b4fc94f07a-1528a369f417fd388572a85c27e68b00` |
| **Backtest ID** | `d94bc57211a5c1f10343a5e870fa8e51` |
| **Launched / completed (UTC)** | 2026-08-18T21:49:35.177290+00:00 / 2026-08-18T21:52:52.494640+00:00 |
| **Output** | STRUCTURALLY COMPLETE: 154 gapless months (2012-01..2024-10); R-025's alpha dates verified a subset. 53 declared-unavailable turnovers and 55 underfilled months disclosed — the heaviest disclosure of the three, consistent with the broadest universe; 0 INCOMPLETE lines. Inert. Structural inspection only; no statistic observed. |
| **Raw log** | `artifacts/qc_stage1_20260818/run24_s1bench_C.log`, 161 lines, exact-file sha256:`79162d8b9fecc291346a5c1cd81c07fac580c8f17b841dc40d2dae09bea24fbf` |
| **Validity** | **VALID** — reviewed code, complete output, analysed once in A-002 |

**The six-run Stage 1 battery is complete on reviewed code, first attempt,
zero refusals.** Replications: R-023 (A_large), R-024 (B_core), R-025
(C_broad). Benchmarks: R-026 (A_large), R-027 (B_core), R-028 (C_broad).
Every log round-tripped the frozen parsers structurally; every alpha date
is covered by its benchmark. Per the owner GO and recorded sequence
(handoff 7af/7ag), the frozen Stage 1 analyser now runs ONCE — the only
step at which any Stage 1 statistic is observed. Stage gate 0.05/24;
lifetime cell floor 428 → 452 at this observation.

## A-002 — Stage 1 single frozen-analyser pass (OBSERVED, 2026-08-18) — NULL; the program closes

The one preregistered observation of the Stage 1 24-cell family, run
after all six runs completed structurally (R-023..R-028, upgraded to
VALID in this same commit via the proper UNANALYSED→VALID rung).

| Field | Value |
|---|---|
| **What** | `scripts/analyse_qc_alpha_stage1.py` run ONCE over the three alpha logs and three cadence-matched benchmark logs with full run identities. |
| **Invocation note** | The first invocation (`python scripts/analyse_qc_alpha_stage1.py`) crashed at import — the script lacks the `sys.path` bootstrap its two sibling analysers carry, so script-mode cannot resolve the `scripts` package. It touched no data and observed nothing. The successful pass used `python -m scripts.analyse_qc_alpha_stage1` from the repo root: identical frozen bytes, no code change. The missing bootstrap is a P3 for the next hardening round. |
| **Code identity** | Analyser tree at `875d003` (merged main; the `602dc0b` chain independently reviewed by fresh-Claude and two Cursor rounds). |
| **Output** | `artifacts/qc_stage1_20260818/analysis_stage1_20260818.json`, 73,283 bytes, sha256 `02c5cbd988ce38a2db3735eb236723efdca4675ba45935b1a33d6a16d65700d4` (machine-local; hash recorded here). |
| **Multiplicity** | Stage family 24 cells, gate 0.05/24 = 2.083e-3; **lifetime cell floor 428 → 452**, lifetime gate 0.05/452 = 1.106e-4; 20,000 draws, smallest attainable p 5.0e-5 < both gates. First and only observation of the family. |

**Results against the frozen gates:**

- **IC (the signal test): 0 of 6 cells pass either gate.** Best:
  REP_IDV/C_broad ic_p = 3.20e-3, above the 2.08e-3 stage gate; the
  other five range 0.026–0.493.
- **Long-short (self-financing, beta-free): 0 of 6 cells pass.** All
  p ≥ 0.129, and three of the six gross Sharpes are NEGATIVE
  (REP_H52/B_core −0.13, REP_IDV/B_core −0.42, REP_IDV/C_broad −0.28).
- **Long-only: 10 of 12 cells pass the stage gate** (4 of those also
  under the lifetime gate) on the frozen gross-mean-vs-zero test — and
  the cadence-matched benchmark now shows directly what Stage 0 could
  only argue: the passing cells' gross Sharpes (0.84–1.01) sit on top
  of their own universes' same-dates equal-weight benchmarks (A_large
  0.80, B_core 0.83, C_broad 0.78). The long-only clears are the
  market, not selection; the constructions that isolate selection (IC,
  long-short) are null everywhere.
- **Benchmarks (same dates as each alpha):** A_large n=142 CAGR 12.3%
  Sharpe 0.80 maxDD −23.3%; B_core n=128 15.0%/0.83/−31.9%; C_broad
  n=117 14.1%/0.78/−33.3%. Disclosure: unavailable-turnover months
  5/32/45 and underfilled months 6/15/30 respectively, all charged or
  recorded per the reviewed contracts.

**Verdict: NULL.** No cell of either Stage 1 specification shows
selection edge on any universe. This is the second full family
(Stage 0's 180 cells, Stage 1's 24) with zero beta-free passes, on top
of eleven earlier local signals — all consistent with the measured
power ceiling of this universe/data combination.

**Preregistered consequence (owner GO of 2026-08-18, handoff 7af):
the cross-sectional alpha program on this universe is CLOSED.** No
further signal variants, threshold tweaks, or family repeats. Research
effort redirects to the workstreams with surviving evidence (portfolio
construction, risk, paper-observation infrastructure). Any future
reopening requires a new owner decision, a new universe or data source,
and a fresh preregistration — never a rehabilitation of these results.

## R-029 — Allocation-policy QC family, single authorized run (VALID)

The APQ-4 cloud run of the frozen allocation-policy family
(`docs/Archive/Plans/ALLOCATION_POLICY_QC_PLAN.md`; preregistration
`docs/Archive/Research/ALLOCATION_POLICY_2026-08-18_PREREGISTRATION.md`). This
is an allocation-policy observation, NOT an alpha cell: it carries its
own 3-cell family and 0.05/3 gate and adds nothing to the closed
cross-sectional program's lifetime floor (A-002 untouched).

| Field | Value |
|---|---|
| **Specification** | Four frozen ETF mixes P0 (100% SPY), P1 (40/60 SPY/BIL), P2 (40/20/20/20 +XLP/XLV), P3 (35/55/10 +XLE); monthly close settlement; bind-time drift turnover; window 2022-01-01 → run date |
| **Research look** | Counted real-market run (run-level count 29 → 30); the plan's single authorized backtest; no statistic observed |
| **Source commit** | `5694975` (merged main; APQ-1..3 review chain complete at this merge) |
| **Uploaded source SHA-256** | `86fb7a3f252f8c9848b91abd07ef9607930dec48d15dc6ace1cae0b93c4f8938` (bytes uploaded UNCHANGED — universe-free family, no rewrite) |
| **QC project** | `35377356` — `25. ALLOCATION_POLICY - 20260819` (QC stored the name without the dot) |
| **Compile ID** | `929dd05d66d5c97c6155d25a06c42af2-ca76e88335036c8337d128e6fb01c8c2` |
| **Backtest ID** | `b9696f67a957075103ce848b39d8cc08` |
| **Launched / completed (UTC)** | 2026-08-19T22:59:13.294928+00:00 / 2026-08-19T22:59:27.953234+00:00 |
| **Output** | STRUCTURALLY COMPLETE, first attempt: frozen parser round-trip accepted 54 months (202202..202607, the full expected window — January 2022 is consumed by boundary settlement, August 2026 is incomplete), all four policies on one shared date set, 216 rows, 0 declared-unavailable turnovers, 0 refusals. 54 ≥ the frozen 24-month floor. The algorithm holds no QC positions (synthetic policy accounting only), so QC's runtime statistics are the untouched-account boilerplate and reveal nothing. Structural inspection only; no statistic observed. |
| **Raw log** | `artifacts/qc_apq4_allocation_20260819.log`, 222 lines, exact-file sha256:`898ac2ed4ce67d1f8a6b7b9de25611c79101ca88e737da46e3dafb9d1e36b4e7` (machine-local; hash recorded here) |
| **Validity** | **VALID** — reviewed code, structurally complete output, analysed once in A-003 (upgraded in the same commit as that observation, per the plan's rung) |

## A-003 — Allocation-policy single frozen-analyser pass (OBSERVED, 2026-08-19) — NULL on the gate; the family closes

The one preregistered observation of the allocation-policy 3-cell
family, run under the owner GO ("go APQ5 now") after R-029 completed
structurally and the APQ-1..3 review chain merged.

| Field | Value |
|---|---|
| **What** | `python -m scripts.analyse_qc_allocation_policy` run ONCE over R-029's raw log with full run identity (`--run-id 35377356,929dd05d…,b9696f67…,86fb7a3f…`); log hash re-verified against the ledger immediately before the pass. |
| **Code identity** | Analyser tree at `c4fd16d` (merged main; APQ-2 analyser independently reviewed and counter-reviewed, reporting schema RATIFIED pre-run). |
| **Output** | `artifacts/analysis_apq5_allocation_20260819.json`, 13,048 bytes, sha256 `4bfc831143ebc05f6e1f3099cadef53393680cce60be56aea35f4711526b8af7` (machine-local; hash recorded here). |
| **Multiplicity** | Family: allocation-policy 2026-08-18, 3 cells (P1/P2/P3 vs P0), gate 0.05/3 = 1.667e-2; 20,000 draws, smallest attainable p 5.0e-5 < gate (ABR-001 guard passed). Scope: **this family only** — NOT added to the closed alpha program's lifetime floor; A-002 untouched. First and only observation of the family. |
| **Disclosure** | 0 declared-unavailable turnover months in any policy, so the APQ2-001 `mean_turnover` skipna caveat is moot for this run. All 54 months priced for all four policies. |

**Results against the frozen gate (two-sided stationary bootstrap on
monthly excess vs P0):**

- **0 of 3 cells pass.** P1 p = 0.080, P2 p = 0.121, P3 p = 0.214 —
  all above 1.667e-2. Every candidate's excess monthly mean is
  NEGATIVE (P1 −0.50%, P2 −0.41%, P3 −0.41% per month): the defensive
  mixes gave up return against 100% SPY over this window, as the
  preregistration anticipated for a mostly-rising tape.
- **Descriptives (primary table, 2022-02..2026-07, gross):** P0 CAGR
  13.5% / Sharpe 0.88 / maxDD −20.2%; P1 8.0% / 1.23 / −8.0%; P2 8.9%
  / 0.89 / −12.3%; P3 9.1% / 1.31 / −7.1%. Sharpe differences (+0.35
  P1, +0.01 P2, +0.43 P3) and drawdown reductions are DESCRIPTIVE
  fields under the ratified schema — no frozen test was declared on
  them, and none is claimed. Monthly drift turnover is tiny
  (~1–2%/month); the 25bps net columns are nearly identical to gross,
  so costs decide nothing here.
- **Interpretation limits (recorded before this observation):** the
  2022+ window is regime-conditioned in hindsight — these descriptives
  describe that tape, not forward evidence. P3 is not mined further,
  per the plan.

**Verdict: NULL on the preregistered family.** No allocation policy
shows a mean-return edge over 100% SPY. The descriptive record shows
the expected shape — P1/P3 bought materially smaller drawdowns
(−7% to −8% vs −20%) at the price of ~40% of the return — which is a
risk-preference trade, not an edge, and any paper/live use of these
weights is a **separate owner decision on the Alpaca/REBAL stack**,
explicitly not a QC follow-up.

**Preregistered consequence: the allocation-policy QC family is
CLOSED.** One cloud run, one analyser pass, both spent. No reruns,
no threshold tweaks, no window extensions on this family.

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

## R-030 — Analyst Revisions V2 B5C data-free infrastructure smoke (SPENT; LOCKED AMBIGUOUS; NO OUTCOME)

This entry records an already-spent action; it does not launch a run, grant
access, or authorize a retry. The intended initialization-refusal smoke used
no production input and is not evidence about the strategy.

| Field | Value |
|---|---|
| **Purpose / classification** | `data_free_infrastructure_research_look`; B5C one-file initialization-refusal smoke only |
| **Research-look accounting** | Counted once (shared run-level look count **30 → 31**; ARV2 infrastructure looks **0 → 1**). **Zero** development evaluations, permanent-family looks, confirmatory-alpha looks, or alpha cells; the lifetime alpha-cell exposure floor remains **452**. |
| **Source identity** | B5C projection introduced at `19b52d6`, independently reviewed through `37e2e64`, and counter-reviewed at `4b5e4e6`; uploaded sole `main.py` 3,328 bytes, SHA-256 `327f126311c12e9f37297f229a3946a6cb1f2bbe26ed6c746cf140b26c2e6bf9` |
| **QC project / compile / backtest** | Project `36418640`, `1 ARV2_B5B_REFUSAL_SMOKE - 20260911`; compile `5e6230184c123e9e72b693bbe372641b-3af05f1ebc45736c49793d84adf33bc1` (`BuildSuccess`); backtest `c27cacff90618a3277387096219ab2fb` |
| **Execution interval (UTC)** | 2026-09-12T00:22:40.194284Z → 2026-09-12T00:22:47.656173Z |
| **Receipt state** | `LOCKED_BACKTEST_STATUS_AMBIGUITY`: the statistics-free list envelope contained a forbidden result/statistic-shaped field, so the driver stopped before reading its value, terminal status, or logs. The expected initialization refusal was **not authenticated**. |
| **Access exclusions** | No provider row, production input, Object Store object, market datum, outcome, performance statistic, result value, terminal backtest status, detail endpoint, or log was accessed; no order was permitted. |
| **Durable evidence** | Driver: 34,882 bytes, SHA-256 `b19a489aca60394a2605363be5a1963a9401c37164c5f0da41ea2d45f39b70c0`. Receipt: 3,639 bytes, schema `arv2-qc-b5c-refusal-smoke-receipt-v1`, SHA-256 `6cef656b40ac988afb1d81cf81784fcfad3ca7381ccfea0baabe4e14a6740fb3`. Full evidence and endpoint counts are recorded in Analyst Revisions V2 section 68.2. |
| **Retry / inference** | **No retry.** Ambiguity consumes the one infrastructure look. This is neither a formal ARV2 outcome nor evidence for or against alpha. |

**Cumulative ledger state after R-030:** **31** run-level looks are recorded:
the 30 prior real-market runs through R-029 plus this one data-free
infrastructure look. The cross-sectional lifetime alpha-cell exposure floor
remains **452**, and APQ's separate three-cell family is unchanged. For ARV2,
one infrastructure look is spent; development evaluations and
permanent-family looks remain zero; confirmatory alpha remains unspent; one
prospective permanent look remains. This accounting grants no provider, QC,
outcome, result, deployment, order, or trading authority.

## R-031 through R-052 — Analyst Revisions V2 QC fundamental-universe discovery launches (RETROACTIVELY RECONCILED; NO OUTCOME READ)

This additive reconciliation records every prior QC discovery backtest launch
that had not yet been entered in the shared ledger. On 2026-09-14 the owner
authorized the lane to proceed toward the first outcome-bearing evaluation.
Before that evaluation, an authenticated, statistics-free inventory of the
lane's discovery projects found 22 distinct backtest launches. The inventory
read only project/run identities and terminal status: no performance
statistics, result values, charts, logs, orders, provider rows, or strategy
outcomes were requested or inspected. Attempts 5, 6, and 13 created projects
but launched no backtest; attempts 16 and 17 stopped during local preparation.
Those five attempts therefore consume no look and receive no R-number.

| Entry | Discovery attempt | QC project | QC backtest | Terminal status |
|---|---:|---:|---|---|
| R-031 | 7 | `36536115` | `0014d18dc88f67f958d559a183079a86` | Runtime Error |
| R-032 | 8 | `36536326` | `1054c989da3711446af17a557b637733` | Runtime Error |
| R-033 | 9 | `36536574` | `73a386ec1c1b7b026afacb85a42fddba` | Runtime Error |
| R-034 | 10 | `36536795` | `44d6fe47dfa9406b3b03215f4dae3306` | Runtime Error |
| R-035 | 12 | `36544563` | `3711535499f0da3fee6977c66375acbf` | Runtime Error |
| R-036 | 14 | `36548449` | `a7a5622f29a92bb18be0e52224683743` | Runtime Error |
| R-037 | 15 | `36548598` | `526c6affd022a6d3ab95e54adc5d9eed` | Runtime Error |
| R-038 | 18 | `36548747` | `5409fcd91a1f3618ce071425591750e5` | Runtime Error |
| R-039 | 19 | `36548862` | `9493b882011a4b51cc1333b6709e14ad` | Runtime Error |
| R-040 | 20 | `36549142` | `4937c65e0e7d442fd4268102d4cd0d42` | Runtime Error |
| R-041 | 21 | `36549260` | `c2138164f23169cbd1188e8349b9558d` | Runtime Error |
| R-042 | 22 | `36549367` | `c042d1cf806c5e28b291bb87e0673ac3` | Runtime Error |
| R-043 | 23 | `36549502` | `962664739f6c769f7eea78083deee4d9` | Runtime Error |
| R-044 | 24 | `36549608` | `736d365c3275b072246c47a92bb15752` | Runtime Error |
| R-045 | 25 | `36549752` | `1501f80835f2a9f763343ca53e34db56` | Runtime Error |
| R-046 | 26 | `36549861` | `564537e6ea7831465eaf2c37cb59190e` | Runtime Error |
| R-047 | 27 | `36549947` | `3c0bd1ff2d1afa826ed1259b59064272` | Runtime Error |
| R-048 | 28 | `36550029` | `18b9eb494c5e843a74ec62de2da831a6` | Runtime Error |
| R-049 | 29 | `36550151` | `1db646acc22f79250827b5896f2b7824` | Runtime Error |
| R-050 | 30 | `36550309` | `d81e7304db805a9d5fea3f8159bc23d6` | Runtime Error |
| R-051 | 31 | `36550360` | `0cd205c129624cb83e0e87a580cd5b34` | Runtime Error |
| R-052 | 32 | `36550482` | `1d1ee522af4176cdf8bfeae487d91e03` | Completed. |

All 22 launches are conservatively classified as outcome-free QC
fundamental-universe-discovery infrastructure research looks. Each is a
distinct spent look and cannot be overwritten or retried under the same
entry. The machine-readable successor ledger is
`arv2_infrastructure_look_ledger.11987a12b72d06ea612b442e342ce0b1d2f28c503f0a3b1ca2cf721d8aaa7810.json`
(40,360 bytes; SHA-256
`b1018c54128b9cea5ff0c960e0c6adeab803b085b9dde359f323246d0f82e802`),
which preserves R-030 and binds the statistics-free reconciliation receipt
(SHA-256
`67071bcafa3ec65912983ba0c0834a5980ffaac63c0c2c75bb2f4c3720460a15`).

**Cumulative ledger state after R-052:** **53** run-level looks are recorded;
ARV2 has spent **23** infrastructure looks. ARV2 development evaluations,
permanent-family looks, and confirmatory-alpha looks remain zero. The
cross-sectional lifetime alpha-cell exposure floor remains **452** and one
prospective permanent ARV2 look remains. The next launched outcome-bearing
ARV2 evaluation must be recorded as **R-053**, even if it refuses or errors.

## R-053 — Analyst Revisions V2 accepted-risk preliminary stock IC (COMPLETED; INCONCLUSIVE UNDERFILLED)

This is the first outcome-bearing Analyst Revisions V2 development evaluation.
It is an accepted-risk preliminary stock-IC diagnostic, not the frozen formal
ARV2 result, an ETF backtest, a leveraged test, or a deployment/trading run.

| Field | Value |
|---|---|
| **Purpose / classification** | `development_evaluation`; `arv2-eval-stock-historical-qc-001`; preliminary current-vintage stock IC only |
| **Research-look accounting** | Counted once (shared run-level look count **53 -> 54**; ARV2 development evaluations **0 -> 1**). ARV2 infrastructure looks remain **23**; permanent-family and confirmatory-alpha looks remain zero. The 32 authenticated preliminary cells raise the lifetime alpha-cell exposure floor **452 -> 484**. |
| **Input package** | `arv2-preliminary-qc-package-c381be822c5082fa438fa79c`; SHA-256 `c381be822c5082fa438fa79c01f2f8191b8c93ff872239c49149413ce569d520`; six activation-ordered private QC Object Store objects |
| **QC source projection** | `arv2-preliminary-qc-projection-ddc9747bc25d0cb275a7e165`; SHA-256 `ddc9747bc25d0cb275a7e165fc26b539189e75f2fb82c4e6fd086c515b85be84`; five files, 131,372 bytes; live compilation `BuildSuccess` |
| **Execution identity** | Plan `arv2-preliminary-qc-submission-64c4b1877721635b4f4258f0`; execution permit `arv2-preliminary-qc-execution-permit-d679932f3b21a29b15bc1b97`; launch receipt `arv2-preliminary-qc-launch-c8417014e4a4291ddf83afcc` |
| **QC project / compile / backtest** | Project `36561856`, `1 ARV2_ACCEPTED_RISK_PRELIMINARY - 20260914_R053B_c381be82`; compile `c5a35b93b4cbd5f89ec2ead1290dc3b4-63219dfcf4a70009a48cec609faa255d`; backtest `f3bd9f3fc3c2627784e93d761382cd04`, `ARV2 R053 accepted-risk preliminary stock IC 2021-2025 c381be82` |
| **Launch / terminal** | Launched `2026-09-15T05:20:50Z` at `In Queue...`; statistics-free polling authenticated `Completed.` after 6 polls; terminal receipt SHA-256 `17454854e39e1a0d6e05b714b9f1c2b6aeb9048c4732a8e23d1d71c3d4a02498` |
| **Aggregate-only result** | Exactly 34 expected `ARV2_*` statistics authenticated once: 32 IC cells plus preliminary/runtime metadata. Result receipt `arv2-preliminary-qc-result-750f1ffe69523bb3adbf3ea6`, SHA-256 `750f1ffe69523bb3adbf3ea69bc64ccb5881169d4a9aa9385895d615e643993b`; custom-statistics SHA-256 `80cb59930b7c97c822fc92ec6a348240e29f3e51a9b066d8b31e786a28db2ac3`. |
| **Windows / cells** | 2020-01-02 through 2025-12-31 primary preliminary window and owner-requested 2021-01-04 through 2025-12-31 descriptive sensitivity; two source views x two rating arms x four horizons x two windows = 32 cells |
| **Result** | **32/32 `INCONCLUSIVE_UNDERFILLED`; 0 valid IC dates.** The primary window had 1,508 invalid dates per cell and the 2021-2025 sensitivity had 1,255. Consequently every IC and cross-sectional mean-return statistic is null; there is no favorable, unfavorable, or zero-alpha estimate to interpret. |
| **Coverage diagnostics** | QC resolved 5,113 securities and retained 1,038 named security refusals. Current-row view: 41,628 eligible score rows; accepted outcome pairs H1/H5/H20/H60 = 38,178 / 38,141 / 38,006 / 37,646 (91.71% / 91.62% / 91.30% / 90.43%). Conservatively censored view: 31,940 eligible rows; accepted pairs = 29,252 / 29,220 / 29,125 / 28,902 (91.58% / 91.48% / 91.19% / 90.49%). The reviewed evaluator invalidates a whole date if any sector is refused, any eligible outcome pair is missing, or the cross-section is too small; those strict completeness conditions were not satisfied on any date. |
| **Evidence limitations** | Inputs are current-vintage, non-pristine-PIT Massive rows and current-snapshot Sharadar identity/sector attributes under the owner's accepted-risk decision. The run omits a PIT security master, PIT sector history, measured session-specific quality, formal walk-forward residualization, terminal-payoff/successor authority, multiplicity inference, an economic portfolio, ETF construction, and leverage. |
| **Access exclusions** | The result action selected no raw provider row, raw price row, security-level outcome, unrestricted log, chart, trade, order, deployment, broker action, or trading action. |
| **Disposition** | **Technically valid completion; economically inconclusive because every cell was underfilled.** Do not treat `Completed.` as a strategy pass. Preserve R-053 as spent and send the exact lane snapshot and completeness behavior through independent Claude review before any corrected evaluation or later-window/ETF/leverage work. |

A deterministic package-only diagnostic replay, performed without another QC
or outcome read, reproduced the decisive refusal. In the current-row view,
1,021 dates had all sectors refused and 487 were partially scored; in the
conservatively censored view the counts were 1,132 and 376. Neither view had a
single date on which every sector was admitted. All 16,101 current-row and
16,212 censored sector-date refusals arose from zero sector MAD with
nonconstant sparse scores, not from the total-name or active-name floors. The
year 2020 had all eleven sectors refused on all 253 sessions, so it adds
invalid dates and 1,044,899 refused member-sessions but no eligible or accepted
outcome pairs. This explains why those pair totals match the 2021-2025
sensitivity while the window date counts do not. The behavior matches the
reviewed complete-cross-section rule and its isolated regression; changing
that rule is a new preregistered evaluation and a new R-number, not a technical
retry or reinterpretation of R-053.

**Cumulative ledger state after R-053:** **54** run-level looks are recorded.
ARV2 has spent **23** infrastructure looks and **1** development evaluation.
The lifetime alpha-cell exposure floor is **484**. No permanent-family or
confirmatory-alpha look has been spent, and no paper/live authority follows
from this preliminary result.

## R-054 — Analyst Revisions V2 sparse-signal accepted-risk stock IC (LAUNCHED; TECHNICAL RUNTIME ERROR; NO RESULT READ)

R-054 was preregistered and launched as a new development evaluation. Its
exact v2 rule normalizes each sector from its live analyst-signal names while
retaining unscored names as structural zero, and excludes unavailable price
pairs without imputation when at least 20 actual pairs remain. The 20-name / 5-
active sector floors, complete-sector requirement, horizons, views, arms, and
2020-2025 plus 2021-2025 windows stayed fixed.

| Field | Recorded value |
|---|---|
| **Research-look accounting** | Counted once: shared run-level looks **54 -> 55** and ARV2 development evaluations **1 -> 2**. Because no aggregate result was authenticated or read, the lifetime alpha-cell exposure floor remains **484**, rather than rising to the preregistered conditional value of 516. |
| **Input package** | `arv2-preliminary-qc-package-e9851c2f3bc3f66d761dbff2`; SHA-256 `e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9` |
| **Evaluator manifest** | `arv2-preliminary-rating-manifest-58df928497bd907ea6401109`; SHA-256 `58df928497bd907ea64011093b2c6c3de06661ddecd9f56dd1e7e37811403a20` |
| **QC source projection** | `arv2-preliminary-qc-projection-1c017bc130a6da1903070220`; SHA-256 `1c017bc130a6da1903070220dc04fb3b685241c8d0a70e3cb6b64ab48b40de14`; five files, 131,880 bytes |
| **Execution identity** | Plan `arv2-preliminary-qc-submission-c455edf2b3bf16085a5e27b7`, SHA-256 `c455edf2b3bf16085a5e27b73b9852816ac5a20bd99d8880a0792097afacddcc`; execution permit `arv2-preliminary-qc-execution-permit-4a31edebb6a005070bfde0ab`; launch receipt `arv2-preliminary-qc-launch-412cd2296e621e50581f98d3` |
| **QC project / compile / backtest** | Project `36578018`, `2 ARV2_ACCEPTED_RISK_PRELIMINARY - 20260915_R054A_e9851c2f`; compile `f9268585923d032f45dfa71adefd7b26-3f2c18c888039d6893340cd16f93eb1f`; backtest `30d1a096d2ef7c69c820460d7ad39971`, `ARV2 R054 sparse-signal accepted-risk preliminary stock IC 2021-2025 e9851c2f` |
| **Launch / terminal** | The one-use permit began `2026-09-15T15:55:12Z`. The launch entered `In Queue...`; 104 statistics-free polls authenticated terminal `Runtime Error`. Terminal receipt `arv2-preliminary-qc-terminal-fab47d71f30c0f7e95684460`, SHA-256 `fab47d71f30c0f7e95684460e3a56caf79d54f5e22c3e3cf098c6c8de800d9a7`. |
| **QC runtime evidence** | The QC terminal reported at 2026-05-26 16:00:00 that one algorithm time loop exceeded ten minutes (`Isolator.cs:line 190`). The UI later reported 3,186.19 seconds total runtime and 6,084,172 processed data points. These messages diagnose scheduling/runtime exhaustion, not an alpha result. |
| **Outcome access** | `include_statistics=false` and `result_values_selected=false` throughout terminal polling. No result authority was rendered or signed; no aggregate statistic, valid-date count, security-level outcome, raw provider row, order, deployment, or trading action was read. |
| **Disposition** | **Spent technical development evaluation; no economic result.** The tangible-evidence gate was not tested and remains unmet. No alpha sign, magnitude, sufficiency status, or underfill conclusion may be inferred from this runtime error. |

The prior source-only feasibility replay remains valid evidence about the
signal path: it found all 1,255 gate-window dates feasible in both source
views and score arms, and the empty-history replay completed all 1,508 dates.
Neither replay opened an outcome. The cloud run instead exhausted the QC
execution schedule while advancing the same fixed workload through repeated
`Train(...)` callbacks. Therefore the next action is a scheduling-only retry,
not a strategy-rule relaxation.

**Cumulative ledger state after R-054:** **55** run-level looks are recorded.
ARV2 has spent **23** infrastructure looks and **2** development evaluations.
The lifetime alpha-cell exposure floor remains **484**. No permanent-family or
confirmatory-alpha look has been spent.

## R-055 — Analyst Revisions V2 same-rule scheduling retry (COMPLETED; TANGIBLE PRELIMINARY STOCK-IC EVIDENCE)

R-055 preserved R-054's exact package, evaluator, v2 signal rule, dates,
views, rating arms, horizons, output inventory, and tangible-result gate. Its
only substantive change was execution scheduling: bounded work slices ran
directly from ordinary `OnData` calls instead of through `Train(...)`. The
evaluator, input, score, return, threshold, window, and output cells remained
byte-identical.

| Field | Recorded value |
|---|---|
| **Purpose / classification** | `development_evaluation`; `arv2-eval-stock-historical-qc-001`; accepted-risk preliminary stock IC only, not a formal, confirmatory, ETF, economic-portfolio, deployment, or trading result |
| **Research-look accounting** | Counted once: shared run-level looks **55 -> 56** and ARV2 development evaluations **2 -> 3**. ARV2 infrastructure looks remain **23**; permanent-family and confirmatory-alpha looks remain zero. The 32 authenticated preliminary cells raise the lifetime alpha-cell exposure floor **484 -> 516**. |
| **Input package** | `arv2-preliminary-qc-package-e9851c2f3bc3f66d761dbff2`; SHA-256 `e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9` |
| **Evaluator manifest** | `arv2-preliminary-rating-manifest-58df928497bd907ea6401109`; SHA-256 `58df928497bd907ea64011093b2c6c3de06661ddecd9f56dd1e7e37811403a20` |
| **QC source projection** | `arv2-preliminary-qc-projection-8d194f3486f961601111d49d`; SHA-256 `8d194f3486f961601111d49d5cabcdaba33c095f95858f03a1143280b76ef5bb`; five files, 132,028 bytes |
| **Execution identity** | Plan `arv2-preliminary-qc-submission-d0fe1c6ae7ae01749426a187`, SHA-256 `d0fe1c6ae7ae01749426a1873692b2a264440d5b83f4cc516136a6954eecd68f`; execution permit `arv2-preliminary-qc-execution-permit-556ebf6e2d9ca90400d2f861`, SHA-256 `556ebf6e2d9ca90400d2f86163a7c97f3e77cd91c813bc19b7560eed2ea82035`; launch receipt `arv2-preliminary-qc-launch-6613f6a03413246c5a6ede3f`, SHA-256 `6613f6a03413246c5a6ede3f5a72dc128ea504e220036a41f8ecaaba6a9f86f0` |
| **QC project / compile / backtest** | Project `36580858`, `3 ARV2_ACCEPTED_RISK_PRELIMINARY - 20260915_R055B_e9851c2f`; compile `8d11a427fa02d5a3b7575e6e95673680-b411ae097d26f7fe858a57eb6b31ec73`, `BuildSuccess`; backtest `de2d5930528b5c3bdcc8a802f1332eaa`, `ARV2 R055B direct-runtime accepted-risk stock IC 2021-2025 e9851c2f` |
| **Launch / terminal** | Permit began `2026-09-15T17:23:13Z`; 89 statistics-free polls authenticated exact `Completed.` Terminal receipt `arv2-preliminary-qc-terminal-7461e9c26ebc02d53d119af2`, SHA-256 `7461e9c26ebc02d53d119af2c78d20e503cad5416ca3e0b8dc3faf605ba22cf2`, records `include_statistics=false` and `result_values_selected=false`. |
| **Aggregate-only result** | One-use result permit `arv2-preliminary-qc-result-permit-c8069ece67f6c52bb1a90cd8`, SHA-256 `c8069ece67f6c52bb1a90cd8ecfea836602a573e35b7ef59af134264fdb0bc3c`, made exactly one `backtests/read` call. Exactly 34 expected `ARV2_*` statistics were authenticated: 32 cells plus two metadata records. Result receipt `arv2-preliminary-qc-result-e670b7f94eb993969defc260`, semantic SHA-256 `e670b7f94eb993969defc260bc34932280fb6a9ec9bd12d7d61400b8725a91ec`; persisted-file SHA-256 `05e347c3f8fad101d4c195b3ae8003c73598533364f3c7e256cfda41a7cf5214`; custom-statistics SHA-256 `b37867f0d629714b9c9dede95bc87725585d647aa7dfb17502ae9a8e0f4f2e01`. |
| **Runtime coverage** | QC resolved 5,113 securities and retained 1,038 named refusals, reconciling to 6,151 inputs; 12,244 contributions and all 400 evaluator callbacks completed. Compatibility field `training_slice_count=41`, although R-055 advanced through `OnData`, not `Train(...)`. |
| **2021-2025 gate result** | **16/16 `PRELIMINARY_DESCRIPTIVE_AVAILABLE`; each has 1,255 valid dates, zero invalid dates, and all five preregistered IC/return aggregates non-null.** Accepted actual outcome pairs are 4,990,758 / 4,984,886 / 4,968,962 / 4,928,202 at H1/H5/H20/H60. Mean IC ranges across view/arm are 0.003910-0.004114 / 0.006235-0.006651 / 0.008213-0.009194 / 0.009774-0.011841; positive-IC date share ranges 56.18%-57.45% / 61.59%-62.63% / 63.82%-65.26% / 66.22%-69.08%. |
| **2020-2025 companion** | **16/16 available; each has 1,508 valid and zero invalid dates.** Accepted pairs range from 5,823,350 at H1 to 5,759,773 at H60. Every mean and median IC is positive, but this companion period is not an independent confirmation of the owner-window result. |
| **Return interpretation** | The authenticated actual-outcome fields exist, satisfying the tangible-evidence gate. Their cross-section mean SPY-excess returns at H1/H5/H20/H60 are -0.00010055 / -0.00116854 / -0.00672225 / -0.02626635 (medians -0.00040116 / -0.00225874 / -0.00876165 / -0.02449505). They are aggregate universe outcomes, identical across views/arms at a horizon, and **not** a score-sorted portfolio or ETF P&L. |
| **Evidence limitations** | Metadata remains `formal_result=false`, `alpha_claim_authorized=false`, and `economic_portfolio_evaluation=false`. Inputs are current-vintage, non-pristine-PIT Massive rows and current-snapshot Sharadar identity/sector attributes. The run omits formal controls/inference, terminal-payoff/successor authority, an economic portfolio, ETF construction, and leverage. |
| **Access exclusions** | The result action selected no raw provider row, raw price row, security-level outcome, unrestricted log, chart, trade, order, deployment, broker action, or trading action. |
| **Disposition** | **Technically successful and tangibly populated preliminary stock-IC diagnostic.** The fixed count/status gate passes 16/16, so no counts-only relaxation is permitted or needed. This is encouraging ranking evidence, not yet an investable-return result or formal alpha acceptance. |

The first signed `_01` control attempt failed locally before any QC request
because generic organization discovery occurred after the formal transport had
sealed its runtime namespace. It created no QC project or job and consumed no
look or result. The successful `_02` path instead read the existing private
host binding before importing the sealed transport; no guard was weakened.

R-056's preregistered counts-only underfill contingency is **cancelled
unlaunched and unspent** because R-055 passed the gate by counts and non-null
availability. No observed alpha sign or magnitude selected that decision.
R-056 is retired; any later new evaluation begins no earlier than R-057.

**Cumulative ledger state after R-055:** **56** run-level looks are recorded.
ARV2 has spent **23** infrastructure looks and **3** development evaluations.
The lifetime alpha-cell exposure floor is **516**. No permanent-family or
confirmatory-alpha look has been spent. Independent Claude review of the exact
R-055 snapshot and Codex counter-review are required before later windows,
ETF construction, actual or synthetic leverage, deployment, orders, or
trading.

## R-057 — Analyst Revisions V2 fixed 2019-2023 stock-IC diagnostic (COMPLETED)

R-057 is a preregistered `development_evaluation`, evaluation
`arv2-eval-stock-historical-qc-002`, over 2019-01-02 through 2023-12-29
(1,258 decision sessions). It reused R-055 package
`arv2-preliminary-qc-package-e9851c2f3bc3f66d761dbff2`, SHA-256
`e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9`,
and the exact R-055 score rule.

| Field | Recorded value |
|---|---|
| **Accounting** | Shared run looks **56 -> 57**; ARV2 development evaluations **3 -> 4**; lifetime cell floor **516 -> 532**. Infrastructure remains 23; permanent and confirmatory looks remain zero. |
| **QC identity** | Project `36588837`, `3 ARV2_REGIME_R057_2019_2023 - 20260915`; compile `5442e2cb06ed0f49d6bdbe42754877b2-f80a7ba5ecb832e38e3143452bf8befa`; backtest `067d22ef131633df7002057c796a67f6` |
| **Signed execution chain** | Plan SHA-256 `6518eb27435c5966a1b837d63abbfe80a18adb22e8f5835a36654602a83a3b24`; permit `212ad3eb882ba82e81e75ed4eb3b8a30f448cd2c8f5295655a7620e476295c03`; launch `b11dee9bd901a673aef3fa25f4b3b373bdc7bb76cd21645163038ac3e8e6131c`; authenticated `Completed.` terminal `37b64f14e50896e2e4d96f8f2d7ec489379eb136214020407f417a2c39bc4e1e` after 42 statistics-free polls |
| **Single aggregate read** | Result permit `817688ac5d53235360cb1e34bce547e314dc2189d806316125f2cbd9cce814f1`; exactly one `backtests/read`; exactly 18 expected statistics; result SHA-256 `2c69d6102e53ca4ab95e5c1e30565ba493882d85dc9ad2a9b6e952aa3a0512e6`; persisted file `ef18cbc613b661d9fa9b38ed341f0c44b02e7882103c1f13ef9da1cd1a9664f7`; custom-statistics `b94d132a96db401782a5f88ad9585bc3c5a31993968d270143fc390fa6530900` |
| **Result** | All 16 cells available, each with 1,258 valid and zero invalid dates. H1/H5/H20/H60 mean-IC ranges: `.002342-.002609` / `.003686-.004090` / `.005211-.005831` / `.006073-.007705`; positive-date shares: `53.66%-55.41%` / `56.20%-57.31%` / `56.44%-57.63%` / `58.27%-59.86%`. Every mean and median IC is positive. |
| **Conditioning** | Accepted pairs decline from 4,638,761 at H1 to 4,614,063 at H60; missing pairs rise from 902,126 to 926,824. The mutually exclusive census has zero benchmark refusals and is recorded in Analyst lane section 79. |
| **Disposition** | **Technically successful, descriptively encouraging stock-ranking evidence.** This is not a formal alpha result, score-sorted portfolio, ETF return, or trading authority. |

The QC editor later contained a literal `thanks` before the import in
`main.py`, which the owner reported was probably accidental and removed. It
caused four later editor-build errors and one later successful build, but did
not alter the pinned compile or the sole launched R-057 backtest. It consumed
no retry, duplicate run, read, or additional look.

## R-058 — Analyst Revisions V2 fixed 2023-2025 stock-IC diagnostic (COMPLETED)

R-058 is the conditional preregistered `development_evaluation`, evaluation
`arv2-eval-stock-historical-qc-003`, over 2023-01-03 through 2025-12-31
(752 decision sessions). Its plan was created only after R-057's authenticated
aggregate receipt, with the same package and score rule.

| Field | Recorded value |
|---|---|
| **Accounting** | Shared run looks **57 -> 58**; ARV2 development evaluations **4 -> 5**; lifetime cell floor **532 -> 548**. Infrastructure remains 23; permanent and confirmatory looks remain zero. |
| **QC identity** | Project `36589846`, `4 ARV2_REGIME_R058_2023_2025 - 20260915`; compile `ea42ccbfa6ac47ee195bed14c3fd3027-d2282698abac486a07364fd59c3a90db`; backtest `f07ac3b86cd703103a2cf2ac48598fea` |
| **Signed execution chain** | Plan SHA-256 `d4e12f2bc7c24c8088b9d4df555c06703ea7adb09e3d2841fd82ba24ab1b5bb4`; permit `239df091d4086728f21111585b36e7e7717304856762592d381c4d8fd75226b1`; launch `68176d778ba2241e73d2b812abaf08833745edec0cab53b59be6e452144c08d3`; authenticated `Completed.` terminal `8406b2295e5057db9550cad55ba483f4e8c5c553502cce41d038b992064ac181` after 26 statistics-free polls |
| **Single aggregate read** | Result permit `b3b28065a79e415ded45a09d472649422e4676a35dbfa4221565d68e007dd928`; exactly one `backtests/read`; exactly 18 expected statistics; result SHA-256 `2c83071d8a6d5fb0637243db9457e83a4e6f70527648fb76ba247e3a62e773d0`; persisted file `a8e92f9cade96be133a390db29dbef4ef854d8d418487d9fae79807eba08e202`; custom-statistics `eb680ddc7f486ac7ab8d81ac6871404fdf2a709f2eef7548329bf00358b99854` |
| **Result** | All 16 cells available, each with 752 valid and zero invalid dates. H1/H5/H20/H60 mean-IC ranges: `.003369-.003413` / `.004438-.004562` / `.004716-.005126` / `.003324-.004483`; positive-date shares: `55.85%-56.38%` / `59.18%-60.37%` / `57.31%-59.04%` / `52.66%-55.59%`. Every mean and median IC is positive. |
| **Conditioning** | Accepted pairs decline from 3,004,567 at H1 to 2,948,639 at H60; missing pairs rise from 321,292 to 377,220. The mutually exclusive census has zero benchmark refusals and is recorded in Analyst lane section 79. |
| **Disposition** | **Technically successful, descriptively encouraging recent-regime ranking evidence.** H5/H20 are strongest and H60 weakens; this is not a formal alpha result, portfolio return, ETF return, or trading authority. |

## R-059 — Analyst Revisions V2 fixed 2013-2019 stock-IC diagnostic (COMPLETED; EFFECTIVE IC START 2015-09-29)

R-059 is the conditional preregistered `development_evaluation`, evaluation
`arv2-eval-stock-historical-qc-004`, nominally over 2013-01-02 through
2019-12-31 (1,762 decision sessions). Its plan was created only after R-058's
authenticated aggregate receipt, with the same package and score rule.

| Field | Recorded value |
|---|---|
| **Accounting** | Shared run looks **58 -> 59**; ARV2 development evaluations **5 -> 6**; lifetime cell floor **548 -> 564**. Infrastructure remains 23; permanent and confirmatory looks remain zero. |
| **QC identity** | Project `36590411`, `5 ARV2_REGIME_R059_2013_2019 - 20260915`; compile `96d0d401b9ce8c8bdf3dd327eb91cbfc-3a5aed546bf9f132b7fd3890c7cf89c6`; backtest `1d8c28f4279694c4389ec415a23d6d20` |
| **Signed execution chain** | Plan SHA-256 `0b172beae8d9350dacd65cfe0296e6f807294fd0380ab78d1c6882796105f4fa`; permit `5e32b74278dd29d3371b36e1bd22be84a6158ef30af01e26b8d583658c2e10bf`; launch `228966a43d2f233ebe1c234bb7932a8051e487e82b50cf31821b52011ae6c551`; authenticated `Completed.` terminal `862ea6647dcdb6880f227209edf3a480500c5e15a1bc637b3a686f78ca01005e` after 26 statistics-free polls |
| **Single aggregate read** | Result permit `4c41f2ff6411403869ae73c6c2af80afe8f76a18b6ad84236aa7cd29de49ccf1`; exactly one `backtests/read`; exactly 18 expected statistics; result SHA-256 `f6f6e841e1eae7b73d9fc62b5b8826de7efc70244d4899e2d6575ec7b2e2d016`; persisted file `480915b1bf42f30868c0ddbb6f74f973ab48fbd1571e219ec1e1a4a1fc2e15fa`; custom-statistics `93d6cd7fe4a6298347aa64335762f0397e633147e5c448ea4eb0644493d4cfa8` |
| **Result** | All 16 cells available, each with 1,072 valid and 690 invalid dates. H1/H5/H20/H60 mean-IC ranges: `.001503-.001597` / `.001979-.002152` / `.003321-.003491` / `.004502-.004689`; positive-date shares: `53.64%-55.13%` / `54.94%-56.25%` / `54.85%-55.69%` / `59.33%-60.82%`. Every mean and median IC is positive. |
| **Effective evidence period** | An outcome-free exact-input replay showed every date from 2013-01-02 through 2015-09-28 invalid because at least one sector had fewer than five active analyst signals. Every date from 2015-09-29 through 2019-12-31 was valid. The result therefore does not support an IC claim for 2013-2015. |
| **Conditioning** | Accepted coverage is 74.30%-74.47%; missing coverage is 25.53%-25.70%, dominated by named FIGI refusals and unavailable entry prices. Benchmark refusals are zero. Exact censored/current census is in Analyst lane section 79. |
| **Disposition** | **Technically successful and positive pre-AI robustness evidence from 2015-09-29 onward.** Large mean/median universe-return divergence warns of skew and outliers. It is not a formal result, portfolio P&L, ETF return, or trading authority. |

Across R-057 through R-059, all 48 cells are populated and have positive mean
and median IC. The association is small and horizon-sensitive: 2019-2023 and
the effective pre-2020 sample strengthen toward H60, while 2023-2025 is
strongest at H5/H20 and weakens at H60. This is evidence that the score has
some ranking content across regimes, not proof that an investable portfolio
survives turnover, costs, concentration, capacity, endpoint conditioning, or
leverage.

All three results remain current-vintage, non-pristine point-in-time,
endpoint-conditioned accepted-risk diagnostics. They omit a PIT security
master, terminal-payoff splice, formal controls and inference, economic
portfolio construction, ETF mapping, transaction costs, and leverage. No raw
row, security-level outcome, unrestricted log, chart, order, deployment,
broker, paper, live, or trading action was selected.

**Cumulative ledger state after R-059:** **59** run-level looks are recorded.
ARV2 has spent **23** infrastructure looks and **6** development evaluations.
The lifetime alpha-cell exposure floor is **564**. Permanent-family and
confirmatory-alpha looks remain zero. Independent Claude review and Codex
counter-review are required before unlevered ETF/economic-portfolio work;
actual or synthetic 3x leverage remains conditional on that baseline.

## R-060 — Analyst Revisions V2 unlevered ETF sector baseline (TECHNICAL FAILURE; NO RESULT READ)

R-060 is one accepted-risk `development_evaluation`, evaluation
`arv2-eval-etf-sector-baseline-qc-001`. Before any ETF outcome read, commit
`9164146` freezes a 54-fund unlevered US sector/industry sleeve, the exact
conservative-censored firm-specific R-055 stock score, H1-observed QC
constituents, 99% exact mapping, 20-session/$5 million liquidity, 90/70
hysteresis, five 20% slots, constituent-look-through sector and transitive
overlap-cluster caps, next-open execution, drift-adjusted turnover, and
0/5/10/20 bps cost cases. The profile SHA-256 is
`eadb6aba26495ceb8d11417364e80a18b9860a2488519ee9c692a7031cfa59dd`;
the projection SHA-256 is
`1e0a091aabed725f4a5ed598de488eaec098141866a6d5c015184baaa5b5778d`.

| Field | Prospective value |
|---|---|
| **Accounting if created** | Shared run looks **59 -> 60**; ARV2 development evaluations **6 -> 7**. An authenticated aggregate read exposes three ETF IC cells plus four portfolio-cost cells and moves the lifetime cell floor **564 -> 571**. Until create succeeds or is ambiguous, the recorded totals remain 59 / 6 / 564. |
| **Window** | Warmup 2020-12-01; 1,253 decisions from 2021-01-04 through 2025-12-29; returns through 2025-12-31; H5/H20/H60 outcomes mature by 2026-03-31. |
| **QC identity** | Private project `6 ARV2_ETF_R060_2021_2025 - 20260915`; backtest `ARV2 R060 unlevered ETF sector baseline e9851c2f`. |
| **Tangible-evidence gate** | Each IC cell must account for all decision dates. Portfolio evidence is descriptive only with at least 252 return sessions and 50 actually invested sessions; an all-cash result is underfilled. |
| **Limitations** | Fixed sleeve rather than exhaustive reverse-index discovery; no reliable PIT AUM filter; no direct-stock or industry comparator; current-vintage non-pristine-PIT provider input; endpoint-conditioned outcomes; no terminal-payoff splice; not formal ARV2-5/6. |
| **Access boundary** | One backtest create, statistics-free terminal polling, then at most one separately authorized read of nine aggregate custom statistics. No raw rows, raw constituents, security-level outcomes, unrestricted logs/charts, leverage, deployment, orders, broker access, paper/live state, or trading. |

R-060 created project `36594932`, compiled successfully as
`e7c3ccb5e7fff10ee31b8f0e4ad9048f-88cda038946ad60897ea6ba576eeec88`,
and launched backtest `81c9e7fd7e667ad9f2d54c7208200d92`. Its first
statistics-free poll authenticated `Runtime Error`: a constituent-only QC
Slice and the later daily-bar Slice shared 2020-12-04, while the driver had
incorrectly advanced both as full sessions. No result authority or aggregate
outcome was opened, so the cell floor remains 564. The run nevertheless spends
look **59 -> 60** and ARV2 development evaluation **6 -> 7**. One bounded
technical diagnostic read selected only status/error/stack trace and no
statistics, chart, order, log collection, provider row, or security outcome.

## R-061 — Analyst Revisions V2 same-rule unlevered ETF retry (COMPLETED; TANGIBLE BUT ECONOMICALLY WEAK)

R-061 changes only QC Slice scheduling: the daily SPY TradeBar is now the sole
session clock, so constituent-only Slices cannot advance the strict evaluator.
All section-80 economic rules, dates, inputs, metrics, and gates are unchanged.
The corrected projection is
`arv2-preliminary-qc-projection-1a6d0a13a16d418ca8e50b2a`, SHA-256
`1a6d0a13a16d418ca8e50b2ab56d6c910d55fd4ff5de4261d5288ea5646c3b07`.

| Field | Prospective value |
|---|---|
| **Accounting if created** | Shared run looks **60 -> 61**; ARV2 development evaluations **7 -> 8**. An authenticated aggregate read exposes the unchanged three ETF IC plus four portfolio-cost cells and moves the lifetime cell floor **564 -> 571**. |
| **QC identity** | Private project `7 ARV2_ETF_R061_2021_2025 - 20260915`; backtest `ARV2 R061 unlevered ETF sector baseline retry e9851c2f`. |
| **Unchanged evidence gate** | Every IC cell must census all 1,253 dates; portfolio availability still requires at least 252 return sessions and 50 invested sessions. |
| **Access boundary** | One create/compile/backtest, statistics-free polling, then one separately signed read of exactly nine aggregate custom statistics only after `Completed.` |

R-061 reached authenticated `Completed.` in project `36595261`, compile
`b291aeb27dee2c005bc289635b522295-2f6bfb088f50f8b866262b820d626923`,
backtest `e09e77390435ac6569d2ada4b4acef9f`. One separately signed read
authenticated exactly nine statistics under result receipt SHA-256
`d2e7e4ca4f38b5709c0a9b799df9e967b72e48a37708835c0d1310639c8cfb56`
and custom-statistics SHA-256
`ab094aeba34a4efc158a35bc1ac0ce4d98f31d16d57f14b842adcb120ec610ec`.

All three IC cells account for 358 valid and 895 invalid dates. Mean IC is
0.003093 / 0.009836 / 0.070551 at H5/H20/H60; positive-date shares are
48.88% / 47.49% / 53.07%. The economic portfolio is invested on 358 of 1,254
return sessions and holds 94.11% cash on average. Cumulative return is +2.58%
at zero cost, +0.07% at 5 bps, **-2.38% at the primary 10 bps**, and -7.10%
at 20 bps, versus SPY +91.50%. Primary-cost Sharpe is -0.194 and maximum
drawdown is -7.01%.

**Economic interpretation limitation:** a pre-push source-to-blueprint audit
found that the five-ETF minimum for IC also gates portfolio admission. With
one to four eligible ETFs, the implementation targets all cash, although
blueprint section 20.3 does not specify that minimum. This is the historical
P2 ARV2ETF82-002, so R-061 does not cleanly test the intended portfolio. A
separately identified local correction removes the IC-count economic gate;
it has not run in QC and does not rewrite this result.
All cash earns zero interest, and the exact-prior-session holdings requirement
is an additional conservative restriction beyond H1 availability. The
recorded return is authentic for those implemented rules; it must not be
presented as a definitive failure of the underlying analyst-revision strategy.

The tangible-evidence gate passes, so no further counts-only easing is
triggered. The result is nevertheless economically unattractive at the frozen
primary cost and far behind SPY. It is not a formal alpha acceptance or a
deployment/trading result. Shared run looks are now **61**, ARV2 development
evaluations **8**, infrastructure looks **23**, and the lifetime exposed-cell
floor **571**. Actual and synthetic 3x work remains a separately reviewed
diagnostic after correction of the unlevered portfolio, not a presumed
improvement to this baseline. A corrected specification/run would be a new
prospective diagnostic; this record changes neither R-061 nor its accounting.
The owner's latest next-phase direction is Claude review, Codex counter-review,
then an individual-stock economic implementation and backtest using the
existing analyst score, with ETFs retained as a backup research path. No
additional run or look is created by the local correction or that direction.

## R-062 — Analyst Revisions V2 direct-stock economic portfolio (TECHNICAL FAILURE; NO RESULT READ)

R-062 is one accepted-risk `development_evaluation`, evaluation
`arv2-eval-stock-economic-qc-001`. Commit `2dcd449` freezes the source and
tests before any project creation, outcome read, or aggregate result. It
reuses the exact R-055 conservative-censored firm-specific score and the
authenticated package
`arv2-preliminary-qc-package-e9851c2f3bc3f66d761dbff2`; it does not fit a new
signal or select among variants after seeing portfolio returns.

| Field | Prospective value |
|---|---|
| **Accounting if created** | Shared run looks **61 -> 62**; ARV2 development evaluations **8 -> 9**. A successful separately authorized aggregate read exposes four cost cells and moves the lifetime alpha-cell floor **571 -> 575**. Infrastructure stays 23; permanent and confirmatory looks stay zero. |
| **Profile** | `arv2-stock-long-only-2021-2025-v1`, SHA-256 `8cab242ae28cb29680b4053b7b19fa18f10b57bd21c48523b0d496794f63384b`; projection `arv2-preliminary-qc-projection-86b74c69844a63802b8291df`, SHA-256 `86b74c69844a63802b8291df3721f77922db52897d2f61deb93ae447f86424e3`. |
| **Window** | 261 weekly decisions from 2021-01-04 through 2025-12-29; next-authenticated-open execution; 1,254 return sessions through 2025-12-31. |
| **Portfolio rule** | At each first authenticated session of an ISO week, rank every resolvable score-bearing stock by the unchanged R-055 score; select the top decile, capped at 50, with score/security-ID tie order. Each selected stock targets 1.96%, for at most 98% gross; failed entries and any shortfall remain zero-yield cash. No absolute-positive-score gate, liquidity filter, leverage, order, or trade is introduced. |
| **Comparators and costs** | SPY plus an equal-weight matched portfolio of all resolvable score-bearing names, targeted to the signal sleeve's actually executed gross. Cost scenarios are 0/5/10/20 bps per side; 10 bps is primary. |
| **Missing outcomes** | Within-membership missing opens carry the last observed mark and defer that account's rebalance. An available membership-end open liquidates; an unavailable membership-end open uses a disclosed zero-recovery lower bound. Named FIGI refusals are excluded before ranking. |
| **Tangible-evidence gate** | Exactly 1,254 return sessions and at least 50 signal-invested sessions. Every cell labels stale-price proxy, zero-recovery lower bound, and/or exposure underfill when present. No status is a formal accept/reject disposition. |
| **QC identity** | Private project `8 ARV2_STOCK_R062_2021_2025 - 20260916`; backtest `ARV2 R062 direct stock portfolio e9851c2f`. |
| **Access boundary** | One private project/create/upload/compile/backtest submission; statistics-free terminal polling; then at most one separately signed read of exactly six aggregate custom statistics (runtime metadata, portfolio metadata, and four cost cells). No raw provider row, security-level outcome, unrestricted log/chart, deployment, broker, paper/live state, order, or trading action is authorized. |

This period has already informed prior development and is not untouched
confirmation evidence. R-062 is a practical, current-vintage,
non-pristine-PIT economic diagnostic whose return may remain conditioned on
price proxies and accepted vendor limitations. Its result will be appended
without rewriting this prospective rule block.

R-062 created project `36608248`, compiled successfully, and launched
backtest `fbe0dded7ff5d252fc724c3fd9fa05f1`, but terminated with a runtime
error after completing the economic computation: its metadata statistic was
larger than the frozen 4,096-character transport bound. No aggregate result
was read and no alpha cell was exposed. One bounded technical diagnostic read
selected only terminal status, error and stack trace. R-062 therefore spends
shared look **61 -> 62** and ARV2 development evaluation **8 -> 9**, while the
lifetime cell floor remains **571**. This is a technical failure, not a
positive or negative portfolio result.

## R-063 — Analyst Revisions V2 same-economics direct-stock compact retry (COMPLETED; RESULT READ REFUSED)

R-063 is the one-look technical successor to R-062. It preserves every
economic input and rule, but versions the summary envelope and replaces the
redundant 1.6-KiB embedded profile body with its exact ID and SHA-256. The
complete profile is still authenticated by the projection and summary digest,
and the result validator rehydrates the pinned profile before checking that
digest. A regression requires at least 1,024 characters of headroom below the
same 4,096-character ceiling.

| Field | Prospective value |
|---|---|
| **Accounting if created** | Shared run looks **62 -> 63**; ARV2 development evaluations **9 -> 10**. A successful aggregate read exposes the unchanged four cost cells and moves the lifetime alpha-cell floor **571 -> 575**. |
| **Profile** | `arv2-stock-long-only-2021-2025-r063-v1`, SHA-256 `9f0bf6044dbe181bed69ca76cf6ee0c2e453cbe507d8436d570a95e645aa4afc`; projection SHA-256 `fe5d534c0cd5569177ef2450547bedc89efc4846eb8273f74d94f087ae162801`. |
| **Unchanged economics** | 2021-2025; exact R-055 score; weekly next-open top decile capped at 50; 1.96% per name and 98% maximum gross; zero-yield residual cash; matched eligible-stock and SPY comparators; 0/5/10/20 bps with 10 bps primary; unchanged missing-price and tangible-evidence rules. |
| **QC identity** | Private project `9 ARV2_STOCK_R063_2021_2025 - 20260916`; backtest `ARV2 R063 direct stock compact retry e9851c2f`; plan SHA-256 `cff4e61683788a736b9ed33a5a59c26b0b60bf4835f0f9e521b16e40484a366f`. |
| **Access boundary** | One create/compile/backtest; statistics-free terminal polling; after `Completed.`, one separately signed read of exactly six aggregate statistics. No raw row, unrestricted log/chart, order, deployment, broker, paper/live state, or trading action. |

The result will be appended without changing this prospective rule block.

R-063 created project `36609362`, compiled, and reached authenticated
`Completed.` after 68 statistics-free polls (backtest
`3632b79548f0839f47fbf6e04f62f190`). Its compact metadata corrected R-062's
transport failure. The separately signed one-use aggregate read nevertheless
refused locally before returning or persisting any statistic: the evaluator's
two derived return-difference strings used Python's default 28-digit Decimal
precision, while the validator recomputed them with the lane's 50-digit
financial context. The read permit is consumed and the run will not be read
again. No return value is reported. R-063 spends shared look **62 -> 63** and
development evaluation **9 -> 10**; the lifetime cell floor remains **571**.

## R-064 — Analyst Revisions V2 same-economics exact-arithmetic retry (COMPLETED; TANGIBLE RESULT WITH INVALID MATCHED COMPARATOR)

R-064 changes only those two derived fields, calculating both inside the
existing 50-digit context. The underlying holdings, daily returns, costs,
wealth paths and every frozen economic rule are unchanged. A high-precision
regression now crosses the evaluator-to-validator seam, and the summary schema
is versioned from v2 to v3.

| Field | Prospective value |
|---|---|
| **Accounting if created** | Shared run looks **63 -> 64**; ARV2 development evaluations **10 -> 11**. A successful aggregate read exposes four cost cells and moves the lifetime alpha-cell floor **571 -> 575**. |
| **Profile** | `arv2-stock-long-only-2021-2025-r064-v1`, SHA-256 `37d0b80181dc736365abbf0f6caedd6e4b6bc70f818905681ac5a29bdcce774b`; projection SHA-256 `052879a56d116b339be561da8125a91b16d238b0729b39c30434cf09ae48eb29`. |
| **Unchanged economics** | Exact R-055 score and R-062/R-063 stock portfolio, date, execution, missing-price, benchmark, cost and tangible-evidence rules. |
| **QC identity** | Private project `10 ARV2_STOCK_R064_2021_2025 - 20260916`; backtest `ARV2 R064 direct stock arithmetic retry e9851c2f`; plan SHA-256 `c3c61d26041e41ed72746a55b9c60e1c175013d8af5b9c5f740ddafd8f0645b8`. |
| **Access boundary** | One create/compile/backtest; statistics-free terminal polling; after `Completed.`, one separately signed read of exactly six aggregate statistics. No raw row, unrestricted log/chart, order, deployment, broker, paper/live state, or trading action. |

The result will be appended without changing this prospective rule block.

R-064 created project `36610457`, compiled successfully, and reached
authenticated `Completed.` after 94 statistics-free polls (backtest
`9318e40ca480437127b63d88d2dbcccb`). One separately signed result read
authenticated exactly six aggregate statistics. The result receipt SHA-256 is
`b26d6e828dea3b1a488fc8056f5ae9cf6bd105d120202bb7157ce1eb9bbab50f` and
the custom-statistics SHA-256 is
`f0a5a42eee6eaa7b761ce5b354737a09077c5d9d53f9d9b5e17612cbd49b0714`.

| Cost per side | Signal return | Matched return | SPY return | Signal - matched | Signal - SPY | Sharpe | Max drawdown |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 bps | +27.1499% | +21.0818% | +94.2074% | +6.0681 pp | -67.0574 pp | 0.3238 | -33.9629% |
| 5 bps | +25.6668% | +21.0196% | +94.2074% | +4.6472 pp | -68.5405 pp | 0.3137 | -34.4757% |
| **10 bps primary** | **+24.2010%** | **+20.9575%** | **+94.2074%** | **+3.2435 pp** | **-70.0064 pp** | **0.3036** | **-34.9955%** |
| 20 bps | +21.3200% | +20.8333% | +94.2074% | +0.4867 pp | -72.8873 pp | 0.2833 | -36.0228% |

This is tangible portfolio evidence: 1,253 of 1,254 return sessions are
invested, average gross exposure is 97.992%, average holdings are 49.993, and
all 261 weekly decisions execute. Average daily two-sided turnover is 1.8725%
(approximately 471.9% annualized). The signal itself has one stale-mark
session and two zero-recovery membership-end exits.

The matched comparator is substantially more conditioned: only two
rebalances execute, 259 defer, 1,247 sessions use stale marks, and 585
membership-end exits use zero recovery. The positive signal-minus-matched
difference is therefore not clean alpha evidence. The signal is profitable
after all frozen transaction-cost scenarios, but its primary +24.20% return,
0.304 Sharpe, and -35.00% maximum drawdown compare poorly with SPY's +94.21%.
R-064 does not justify promotion as a standalone strategy or a leveraged
variant. It remains a preliminary, current-vintage, non-pristine-PIT,
price-proxy-conditioned development evaluation with no formal acceptance or
deployment implication.

R-064 moves shared run looks **63 -> 64**, ARV2 development evaluations
**10 -> 11**, and the lifetime exposed-cell floor **571 -> 575**.
Infrastructure remains 23; permanent and confirmatory looks remain zero.

The invalid matched comparator prevents attributing R-064's return difference
to the analyst score. It does not erase the adverse evidence for the exact
implemented construction: that sleeve still returned +24.20% against SPY's
+94.21%, with a 0.304 Sharpe and -35.00% maximum drawdown. R-065 changes only
within-membership stale-price execution mechanics for both sleeves, correcting
the comparator so the next diagnostic can separate ranking from construction
more cleanly.

## R-065 — Analyst Revisions V2 corrected matched-comparator attribution diagnostic (PROSPECTIVE; NOT YET LAUNCHED)

R-065 is one accepted-risk `development_evaluation`, evaluation
`arv2-eval-stock-portfolio-historical-qc-004`. It preserves the exact R-055
conservative-censored firm-specific score, authenticated package, 2021-2025
window, weekly next-open schedule, top-decile/capped-50 signal sleeve, 1.96%
per-name cap, 98% target gross exposure, zero-yield cash, FIGI refusals, SPY,
and membership-end zero-recovery lower bound. It does not fit or select a new
signal after seeing R-064.

| Field | Prospective value |
|---|---|
| **Accounting if created** | Shared run looks **64 -> 65**; ARV2 development evaluations **11 -> 12**. A successful aggregate read exposes four cost cells and moves the lifetime alpha-cell floor **575 -> 579**. Infrastructure stays 23; permanent and confirmatory looks stay zero. |
| **Profile** | `arv2-stock-long-only-2021-2025-r065-v2`, SHA-256 `39773415f5d936166b3a224a5e26c55e4dc20a7e8052fb65c796f9fd3ce65678`; projection `arv2-preliminary-qc-projection-c67cee15e9972c595ebfa22a`, SHA-256 `c67cee15e9972c595ebfa22a7483b72c14d8e0f919364070cb269c06528ef1c5`, seven files, 232,391 total bytes and a 59,683-byte maximum. |
| **Only economic correction** | A within-membership held name without a current price retains its prior mark and drifted weight. It books no impossible trade or turnover. Priceable holdings and targets continue to rebalance inside the remaining gross budget; missing new entries stay cash. When a price resumes, the cumulative prior-mark-to-current return is booked once. The same rule applies to signal and matched accounts. |
| **Diagnostic output** | Exactly six aggregate statistics: compact runtime metadata, portfolio metadata, and one cell for each frozen 0/5/10/20-bps-per-side cost. The 10-bps cell remains primary. The validator requires cross-cell path invariance, monotone cost drag, and closed-form annual cost arithmetic from the 0-bps anchor. Each cell reports signal, corrected all-eligible matched comparator and SPY returns; signal-minus-matched and signal-minus-SPY; risk, drawdown, turnover, cash and explicit per-name stale/partial-rebalance counters. |
| **QC identity if launched after review** | Private project `11 ARV2_STOCK_R065_2021_2025 - 20260916`; backtest `ARV2 R065 corrected comparator e9851c2f`. |
| **Frozen decision rule** | An unreconciled result or failure of the authenticated stale/partial-counter relations is a technical failure. The zero account-wide-deferral and 261-execution checks remain round-trip integrity checks, not data-discriminating evidence. If primary-cost signal-minus-matched is non-positive, do not tune this same window. A positive difference is only a conditional selection effect for this construction, not formal alpha acceptance; SPY remains external absolute-return context. Leverage remains closed unless an unlevered construction first clears a credible benchmark gate. |
| **Access boundary** | At most one reviewed create/compile/backtest and one separately signed read of exactly six aggregate statistics. No raw row, unrestricted log/chart, deployment, broker, paper/live state, order, or trading action. |

This rule block is frozen before project creation, launch, or outcome read.
This code/review round spends **zero** research looks and does not access QC or
provider data. Claude review and Codex counter-review are complete before the
one R-065 launch.

## R-066 — Analyst Revisions V2 historical SPY-holdings eligibility diagnostic (PROSPECTIVE; NOT YET LAUNCHED)

R-066 is one accepted-risk `development_evaluation`, evaluation
`arv2-eval-stock-spy-holdings-qc-005`. It preserves the R-065 signal,
portfolio, execution, missing-price, cost and result-integrity rules. Its only
economic-scope change is to filter the score-bearing input securities before
both top-decile ranking and matched-comparator construction to the exact
authenticated security IDs in historical SPY ETF constituent snapshots. This
is an **S&P 500 holdings proxy**, not official S&P 500 index membership.

| Field | Prospective value |
|---|---|
| **Accounting if created** | Shared run looks **65 -> 66**; ARV2 development evaluations **12 -> 13**. A successful aggregate read exposes four cost cells and moves the lifetime alpha-cell floor **579 -> 583**. Infrastructure stays 23; permanent and confirmatory looks stay zero. |
| **Profile** | `arv2-stock-long-only-spy-holdings-proxy-2021-2025-r066-v1`, SHA-256 `1bd852c327c50d7d410cdac870febcf6ae3b0fb39ddf0f3554363697d1b21660`; projection `arv2-preliminary-qc-projection-deb4ced481a55fd93f7a545f`, SHA-256 `deb4ced481a55fd93f7a545f32b652126fad6af0926435c422974811e8cda143`, seven files, 233,095 total bytes and a 59,683-byte maximum. |
| **Eligibility authority** | QuantConnect US ETF Constituents for SPY. For each of the 261 weekly decisions, select the latest collection `EndTime` strictly before New York decision-date midnight. The collection and every positive-weight constituent `LastUpdate` must be no more than 10 calendar days old at the decision, and `LastUpdate` cannot follow its collection. Nullable, zero and negative finite weights are excluded; malformed or non-finite non-null weights refuse. The positive-weight snapshot must total 0.95-1.05 and at least 99% of that weight must map by exact QC security ID into the authenticated input universe. Missing, stale, malformed, duplicated or insufficiently mapped evidence refuses. |
| **Diagnostic output** | Exactly six aggregate statistics: runtime metadata, portfolio metadata and four 0/5/10/20-bps cost cells, with 10 bps primary and the same cross-cell/path/cost checks as R-065. |
| **QC identity** | Private project `12 ARV2_STOCK_R066_SPY_2021_2025 - 20260916`; backtest `ARV2 R066 SPY holdings proxy e9851c2f`. |
| **Access boundary** | One create/compile/backtest with statistics-free terminal polling, followed only after `Completed.` by one separately signed read of exactly six aggregate statistics. No raw row, unrestricted log/chart, deployment, broker, paper/live state, order, or trading action. |

## R-067 — Analyst Revisions V2 historical QQQ-holdings eligibility diagnostic (PROSPECTIVE; NOT YET LAUNCHED)

R-067 is one accepted-risk `development_evaluation`, evaluation
`arv2-eval-stock-qqq-holdings-qc-006`. It changes R-065 only by applying the
same authenticated historical-constituent filter using QQQ. This is a
**Nasdaq-100 holdings proxy**. It is explicitly **not all Nasdaq-listed
stocks**, and no result may be described that way.

| Field | Prospective value |
|---|---|
| **Accounting if created** | Shared run looks **66 -> 67**; ARV2 development evaluations **13 -> 14**. A successful aggregate read exposes four cost cells and moves the lifetime alpha-cell floor **583 -> 587**. Infrastructure stays 23; permanent and confirmatory looks stay zero. |
| **Profile** | `arv2-stock-long-only-qqq-holdings-proxy-2021-2025-r067-v1`, SHA-256 `4c2fd34f2255bb05adfccec5afc5c7dd408b7c64d3ebc25854a39b92c78c2796`; projection `arv2-preliminary-qc-projection-d34ae49468b502c97b76a095`, SHA-256 `d34ae49468b502c97b76a09528eb607aed573a5851400a72f2337f49fb124d53`, seven files, 233,384 total bytes and a 59,683-byte maximum. |
| **Eligibility authority** | QuantConnect US ETF Constituents for QQQ under the exact same strictly-prior, 10-calendar-day collection/`LastUpdate`, 0.95-1.05 positive-weight and 99%-mapped-weight rules frozen for R-066. The filter applies before both signal ranking and matched-comparator construction. |
| **Diagnostic output** | Exactly six aggregate statistics: runtime metadata, portfolio metadata and four 0/5/10/20-bps cost cells, with 10 bps primary and the same cross-cell/path/cost checks as R-065. |
| **QC identity** | Private project `13 ARV2_STOCK_R067_QQQ_2021_2025 - 20260916`; backtest `ARV2 R067 QQQ holdings proxy e9851c2f`. |
| **Access boundary** | One create/compile/backtest with statistics-free terminal polling, followed only after `Completed.` by one separately signed read of exactly six aggregate statistics. No raw row, unrestricted log/chart, deployment, broker, paper/live state, order, or trading action. |

## R-068 — Analyst Revisions V2 historical SPY-plus-QQQ union diagnostic (PROSPECTIVE; NOT YET LAUNCHED)

R-068 is one accepted-risk `development_evaluation`, evaluation
`arv2-eval-stock-spy-qqq-union-qc-007`. It changes R-065 only by filtering to
the exact authenticated-QC-security-ID union of the R-066 SPY and R-067 QQQ
snapshots at each decision. A name present in both is included once. This is a
union of two ETF-holdings proxies, not official S&P 500 membership or all
Nasdaq-listed stocks.

| Field | Prospective value |
|---|---|
| **Accounting if created** | Shared run looks **67 -> 68**; ARV2 development evaluations **14 -> 15**. A successful aggregate read exposes four cost cells and moves the lifetime alpha-cell floor **587 -> 591**. Infrastructure stays 23; permanent and confirmatory looks stay zero. |
| **Profile** | `arv2-stock-long-only-spy-qqq-union-2021-2025-r068-v1`, SHA-256 `333e26b9645a8f6c3d35886ec7e9cece172d3bb166db22e76037d7b2b9b740e1`; projection `arv2-preliminary-qc-projection-cff9302f23b98bc2bb174682`, SHA-256 `cff9302f23b98bc2bb174682aa48f46ad65ac4206418e19545a0167f0d9f107c`, seven files, 233,385 total bytes and a 59,683-byte maximum. |
| **Eligibility authority** | Both SPY and QQQ snapshots must independently satisfy the exact R-066/R-067 time, source-vintage, weight and mapping rules. Their mapped security IDs are then unioned and sorted exactly before the filter is applied to signal and comparator. |
| **Diagnostic output** | Exactly six aggregate statistics: runtime metadata, portfolio metadata and four 0/5/10/20-bps cost cells, with 10 bps primary and the same cross-cell/path/cost checks as R-065. |
| **QC identity** | Private project `14 ARV2_STOCK_R068_SPY_QQQ_2021_2025 - 20260916`; backtest `ARV2 R068 SPY QQQ union e9851c2f`. |
| **Access boundary** | One create/compile/backtest with statistics-free terminal polling, followed only after `Completed.` by one separately signed read of exactly six aggregate statistics. No raw row, unrestricted log/chart, deployment, broker, paper/live state, order, or trading action. |

R-066 through R-068 are descriptive same-window diagnostics, not a candidate
tournament. Their outcomes will not be used to call the best of the three a
winner, tune the score or silently promote a universe. Any promotion or
holdout claim requires a separately preregistered future evaluation. All four
runs retain the accepted-risk package's current-vintage/non-pristine-PIT
Massive signal limitation. No leverage run is unlocked by merely completing
them; leverage remains closed until an unlevered construction establishes a
credible benchmark result. At this preregistration snapshot no R-065 through
R-068 QC project has been created or launched, no result has been read, and
accounting remains **64 shared looks, 11 ARV2 development evaluations, 23
infrastructure looks, and a 575-cell lifetime floor**.

## R-065 result and R-066 technical failure — 2026-09-16

R-065 completed in private QuantConnect project `36628077` (backtest
`e596fea2ac3c9182d63057fbbbf63e7f`) after 47 statistics-free polls. One
separately signed read authenticated exactly the six preregistered aggregate
statistics. The plan SHA-256 is
`57c97a4d61b176654dbd3be5309240a1e3836801bf7428ecdd9b33ee7eba43cb`,
the aggregate semantic SHA-256 is
`989d4a671f947a8c52b150ba9a5994b1b15ffe3f23191ac7e7f348c16541a654`,
and the custom-statistics SHA-256 is
`eab8ed256005b83cfea3b5a2c97218274b18184b3ab3c69ace420c71bcb9f213`.

| Cost per side | Signal return | Corrected matched return | SPY return | Signal - matched | Signal - SPY | Max drawdown |
|---:|---:|---:|---:|---:|---:|---:|
| 0 bps | +27.1499% | +28.3695% | +94.2074% | -1.2195 pp | -67.0574 pp | -33.9629% |
| 5 bps | +25.6668% | +27.4429% | +94.2074% | -1.7760 pp | -68.5405 pp | -34.4757% |
| **10 bps primary** | **+24.2010%** | **+26.5229%** | **+94.2074%** | **-2.3219 pp** | **-70.0064 pp** | **-34.9955%** |
| 20 bps | +21.3200% | +24.7027% | +94.2074% | -3.3827 pp | -72.8873 pp | -36.0228% |

The signal executes all 261 decisions, is invested for 1,253 of 1,254 return
sessions, averages 97.9925% gross exposure and 50 selected names, and has
about 471.86% annualized two-sided turnover. The corrected comparator also
executes 261 times, rather than freezing after two as in R-064. It remains a
conservative lower-bound implementation: all 259 post-opening comparator
decisions are partial, average gross exposure is 95.3203%, 1,247 sessions
carry at least one stale mark, and 893 membership ends receive zero recovery.
Those limitations remain visible, but the central attribution result is now
directionally adverse: the score-selected sleeve underperforms its matched
all-eligible universe at every frozen cost. No same-window score tuning or
positive alpha claim follows. The already-preregistered universe diagnostics
remain descriptive construction tests, not a search for a winning result.

R-066 then created private project `36629203`, compiled, and launched
backtest `851ebbb854f7b262aa3cf48eb5426ca2`. It reached authenticated
`Runtime Error` after two statistics-free polls. A bounded diagnostic read
selected only its terminal error and stack, not statistics, charts, orders or
provider rows: `constituent-history exact SID mapped weight is below 99%`.
No result authority or result-read permit was issued and no aggregate value
was read. The plan SHA-256 is
`891b27729dec7464547f332e2c1ac108eeb59636a030d07a0632cabf8414830d`
and terminal-receipt SHA-256 is
`5c5d5dd3201db7c98326c898865a904b228047c4219c3c4c495b803f00d4ee9c`.
R-066 therefore consumes shared look **65 -> 66** and development evaluation
**12 -> 13**, but emits zero cells: the authenticated cell floor stays 579.
It is immutable and will not be retried under the same identity.

The failure revealed a specification error, not a QuantConnect entitlement or
API failure. These diagnostics select score-bearing stocks that are members
of the named ETF; they do not replicate the ETF. Requiring the score-bearing
input census to cover 99% of the ETF's full weight incorrectly treats ordinary
out-of-census ETF members as identifier failures. The corrected rule keeps the
full 0.95-1.05 positive ETF-weight, time, freshness, uniqueness and exact-SID
checks, then takes the nonempty exact-QC-SID intersection with the authenticated
score-bearing census. Every selected name is therefore still a point-in-time
member, while no ETF-replication coverage claim is made.

## R-067, R-068 and R-069 corrected intersection diagnostics (PROSPECTIVE)

The unlaunched R-067 and R-068 v1 projections are superseded before project
creation. R-067 v2 and R-068 v2 use the corrected intersection rule. R-069 is
the new technical successor to spent R-066. All three preserve R-065's signal,
portfolio, comparator, price, cost and output rules, use the same accepted-risk
Massive input, and remain current-vintage/non-pristine-PIT diagnostics.

| Ledger | Profile identity | Projection identity | Accounting on successful aggregate read |
|---|---|---|---|
| `R-067`; `arv2-eval-stock-qqq-holdings-intersection-qc-006` | `arv2-stock-long-only-qqq-holdings-intersection-2021-2025-r067-v2`; `a771718c06854a52b58c9c703e88c7429ecea2e0d09b398f73fd983565992293` | `arv2-preliminary-qc-projection-31ae75cdad1693a93c1727fa`; `31ae75cdad1693a93c1727fa1f91d5819f2f0f7b54dbd9ceee45b049cae4a163`; 7 files, 233,473 total / 59,415 max bytes | looks 66 -> 67; evaluations 13 -> 14; cells 579 -> 583 |
| `R-068`; `arv2-eval-stock-spy-qqq-intersection-union-qc-007` | `arv2-stock-long-only-spy-qqq-intersection-union-2021-2025-r068-v2`; `0ba38928df68137f5fcbf224daacea505d805145d8882291384bc4f8a9b19a5b` | `arv2-preliminary-qc-projection-85f87db4615fd46f828a9b18`; `85f87db4615fd46f828a9b18c7ffc0fd189beb69b3f38e04c92cfda526039b17`; 7 files, 233,480 total / 59,415 max bytes | looks 67 -> 68; evaluations 14 -> 15; cells 583 -> 587 |
| `R-069`; `arv2-eval-stock-spy-holdings-intersection-qc-008` | `arv2-stock-long-only-spy-holdings-intersection-2021-2025-r069-v1`; `2461aae1e9418a97ebcf2b45ad48f64cb3fc1ce9a44b21bc98567ccc4bae0521` | `arv2-preliminary-qc-projection-935d3980a826f1a0c8dfa041`; `935d3980a826f1a0c8dfa0417bcc568d148fe3fd53a146591b5726ac7a3880b6`; 7 files, 233,184 total / 59,415 max bytes | looks 68 -> 69; evaluations 15 -> 16; cells 587 -> 591 |

R-067 remains a QQQ/Nasdaq-100 holdings proxy, not all Nasdaq-listed stocks;
R-068 is the exact-SID-deduplicated SPY-plus-QQQ union; R-069 is the SPY/S&P
500 holdings proxy, not official index membership. Their private projects are
prospectively `13 ARV2_STOCK_R067_QQQ_2021_2025 - 20260916`, `14
ARV2_STOCK_R068_SPY_QQQ_2021_2025 - 20260916`, and `15
ARV2_STOCK_R069_SPY_2021_2025 - 20260916`. Their backtest names are `ARV2
R067 QQQ intersection e9851c2f`, `ARV2 R068 SPY QQQ intersection union
e9851c2f`, and `ARV2 R069 SPY intersection retry e9851c2f`.

This block is frozen after the R-066 technical error was known but before any
R-067, R-068 or R-069 project creation, launch or outcome read. The current
accounting is **66 shared looks, 13 development evaluations, 23 infrastructure
looks and a 579-cell floor**. The three runs remain descriptive and are not a
same-window winner-selection exercise. Leverage, formal acceptance,
deployment, orders, broker access, paper/live state and trading remain closed.

## R-067 disposition and R-068/R-069/R-070 successors — 2026-09-16

R-067 used its exact preregistered QQQ-intersection v2 projection. Private
project `36630516`, backtest `82d7a83ec2b9aad77a65c0a56a10b9b3`, reached
authenticated `Completed.` after three statistics-free polls. Its plan,
launch, and terminal SHA-256 values are respectively
`8a3e90228911980f002e8f7b84412edc07ad2b09c9b6d58e549f3c0a91ad05e2`,
`30681dbb8f69c6b491a555d6d06047685ec876147cbd17d4487b43d66b3480bf`,
and `ea4cf4089622d617e148681453e40d26cf5f946267a1a4dcccde30bb635ee7e7`.

The first result action refused before a result permit existed because its
local detached signature verifier was unavailable. A later authenticated
attempt durably spent one-use result-read permit
`e4dea6c1d7b23f2c1f487f2456fb2b63556d5560f494c462417bdbda0d54d19b`
and then locked before an aggregate receipt existed. Local evidence cannot
distinguish a pre-read capability failure, the sole bounded result call, strict
aggregate parsing, or persistence. The permit makes ambiguity consuming and
forbids retry. No result value or aggregate statistic was returned, persisted,
or interpreted. R-067 therefore moves shared looks **66 -> 67** and
development evaluations **13 -> 14**, but adds zero cells: the floor remains
**579**.

A bounded local correction retries exactly one direct `ChildProcessError`
from the detached signature verifier once, with byte-identical inputs and a
fresh process, before a permit is spent. It never retries timeouts,
spawn/OS/cryptographic/integrity refusals and cannot recover an ambiguous
post-permit result action. R-070 is therefore a fresh QQQ identity rather than
a second read of R-067.

| Ledger | Profile identity | Projection identity | Accounting on successful aggregate read |
|---|---|---|---|
| `R-068`; `arv2-eval-stock-spy-qqq-intersection-union-qc-007` | `arv2-stock-long-only-spy-qqq-intersection-union-2021-2025-r068-v2`; `0ba38928df68137f5fcbf224daacea505d805145d8882291384bc4f8a9b19a5b` | `arv2-preliminary-qc-projection-e03eb991acce1ebc01b4fdc4`; `e03eb991acce1ebc01b4fdc44fbcaf0c4f50eb90d5eb50c456d2d4285b938a00`; 7 files, 233,480 total / 59,415 max bytes | looks 67 -> 68; evaluations 14 -> 15; cells 579 -> 583 |
| `R-069`; `arv2-eval-stock-spy-holdings-intersection-qc-008` | `arv2-stock-long-only-spy-holdings-intersection-2021-2025-r069-v1`; `2461aae1e9418a97ebcf2b45ad48f64cb3fc1ce9a44b21bc98567ccc4bae0521` | `arv2-preliminary-qc-projection-54cb25fe96d602fcd0bae047`; `54cb25fe96d602fcd0bae04798286225dbb93980592718b65586a52c3593f25f`; 7 files, 233,184 total / 59,415 max bytes | looks 68 -> 69; evaluations 15 -> 16; cells 583 -> 587 |
| `R-070`; `arv2-eval-stock-qqq-holdings-intersection-qc-009` | `arv2-stock-long-only-qqq-holdings-intersection-2021-2025-r070-v3`; `fd8debc451518a74e426b8c05fb50dc9fc936af2c193b7cbc91040e51e4bfed9` | `arv2-preliminary-qc-projection-d170fa99cfd3c01decc887a7`; `d170fa99cfd3c01decc887a7ce463baf81185545882fe9433c5e72a3b3005361`; 7 files, 233,473 total / 59,415 max bytes | looks 69 -> 70; evaluations 16 -> 17; cells 587 -> 591 |

R-068 is the exact-SID-deduplicated SPY-plus-QQQ holdings-proxy union; R-069
is the historical SPY/S&P 500 holdings proxy; R-070 is the historical
QQQ/Nasdaq-100 holdings proxy, not all Nasdaq-listed stocks. Their projects
are prospectively `14 ARV2_STOCK_R068_SPY_QQQ_2021_2025 - 20260916`, `15
ARV2_STOCK_R069_SPY_2021_2025 - 20260916`, and `16
ARV2_STOCK_R070_QQQ_2021_2025 - 20260916`. Their backtests are `ARV2 R068 SPY
QQQ intersection union e9851c2f`, `ARV2 R069 SPY intersection retry
e9851c2f`, and `ARV2 R070 QQQ result retry e9851c2f`. This block is frozen
before any of those three project creations or outcome reads. They remain
descriptive diagnostics, not a winner-selection exercise; leverage, formal
acceptance, deployment, broker access, orders, paper/live state and trading
remain closed.

## R-068 disposition and EndTime-only R-069/R-070/R-071 successors — 2026-09-16

R-068 used its exact preregistered union-intersection v2 projection in private
project `36631115`, backtest `204434a6f79f319613e9fc3fcdf3f988`. It reached
authenticated `Runtime Error` after two statistics-free polls. Its plan,
launch and terminal SHA-256 values are respectively
`7d48c36a04fb7980e1359c76d0d8b7c965ba45b5ea2df6c535d7edfe47b17294`,
`af866fdba83909626447c6b7286b61c356c011213589efa8b438a943115ebe26`,
and `0e8a64ce0fad273ccd9e49b4657c1b5c5123c33ac5c8b8889eae3c1dccd5d423`.
A bounded exact-run diagnostic read selected only the terminal error and
stack, not statistics, charts, orders, provider rows or security outcomes:
`constituent-history LastUpdate is after collection EndTime`. R-068 consumes
shared look **67 -> 68** and development evaluation **14 -> 15**, but adds
zero cells; live accounting is **68 shared looks, 15 development evaluations,
23 infrastructure looks and a 579-cell floor**.

The failure exposed a timestamp-semantics defect. QuantConnect's LEAN class
defines collection `EndTime` as the availability time and nullable
`LastUpdate` as the previous constituent-data update. The corrected successor
contract never reads `LastUpdate`. It selects the latest collection `EndTime`
strictly before each decision, applies the ten-calendar-day age limit to that
collection per decision, and fully validates/caches only snapshots actually
selected. A malformed selected snapshot refuses without fallback; an
unselected future snapshot cannot poison an earlier decision. Exact
row/collection `EndTime`, SID uniqueness and reverse mapping, total positive
weight 0.95-1.05, and nonempty score-census intersection guards all remain.

| Ledger | Profile identity | Projection identity | Accounting on successful aggregate read |
|---|---|---|---|
| `R-069`; `arv2-eval-stock-spy-holdings-intersection-qc-008` | `arv2-stock-long-only-spy-holdings-intersection-2021-2025-r069-v2`; `83deb4aeb655c0fdfd4714e53e427a3df560c8f5caea40933ae6d76df8beae12` | `arv2-preliminary-qc-projection-38c2b264f42596481b232c06`; `38c2b264f42596481b232c06b445eb6533f08b691cc83b316ce68f6916e4898d`; 7 files, 232,168 total / 59,100 max bytes | looks 68 -> 69; evaluations 15 -> 16; cells 579 -> 583 |
| `R-070`; `arv2-eval-stock-qqq-holdings-intersection-qc-009` | `arv2-stock-long-only-qqq-holdings-intersection-2021-2025-r070-v4`; `733d22be608aa13b55f5b218d6cf45484b9b2271a1812b59e3d9217de8e78979` | `arv2-preliminary-qc-projection-f751279256dbeeaf95723f63`; `f751279256dbeeaf95723f63ba7b74c7a0d7f8e1715cd5578f297000fdcd0e4e`; 7 files, 232,457 total / 59,100 max bytes | looks 69 -> 70; evaluations 16 -> 17; cells 583 -> 587 |
| `R-071`; `arv2-eval-stock-spy-qqq-intersection-union-qc-010` | `arv2-stock-long-only-spy-qqq-intersection-union-2021-2025-r071-v3`; `1f262bbef386d8291afc38e50a6706d4e80020702296b3423b4f2075a1858f87` | `arv2-preliminary-qc-projection-7fc71f66821ee3195bfa3738`; `7fc71f66821ee3195bfa37388a41906a6012b66a78b99ee4a143966e341af0d8`; 7 files, 232,464 total / 59,100 max bytes | looks 70 -> 71; evaluations 17 -> 18; cells 587 -> 591 |

R-069 is a historical SPY/S&P 500 holdings proxy, not official index
membership. R-070 is a QQQ/Nasdaq-100 holdings proxy, explicitly not all
Nasdaq-listed stocks. R-071 is their exact-SID-deduplicated union. Their
private projects are prospectively `15 ARV2_STOCK_R069_SPY_2021_2025 -
20260916`, `16 ARV2_STOCK_R070_QQQ_2021_2025 - 20260916`, and `17
ARV2_STOCK_R071_SPY_QQQ_2021_2025 - 20260916`; their backtests are `ARV2 R069
SPY EndTime retry e9851c2f`, `ARV2 R070 QQQ EndTime retry e9851c2f`, and
`ARV2 R071 SPY QQQ EndTime union retry e9851c2f`. This block is frozen before
any of those project creations, launches or outcome reads. The diagnostics
cannot select a same-window winner or unlock leverage, formal acceptance,
deployment, broker access, orders, paper/live state or trading.

## R-069 disposition and query-window R-072/R-073/R-074 successors — 2026-09-16

R-069 used its exact preregistered SPY EndTime-only projection. A local
signature check first refused before any permit, project or look; the exact
resumable retry launched once. Private project `36633442`, backtest
`9ca1e406f63145b969cca4d1034dbc02`, reached authenticated `Runtime Error`
after two statistics-free polls. Its plan, launch and terminal SHA-256 values
are respectively
`ce8ed24649a8060e2a690967e08afafd530136a6a6f37af1d028ff19b31ea367`,
`e65e2a9abe4ee4a7598884cb506d858721e18bace5c814e1e43e6fc1f1408386`,
and `69545bccb68e3daeb13461fd04dfba7c86a2eb2279fe575563c75f993b8ebfd9`.
A bounded exact-run diagnostic selected only the error and stack, not result
statistics, charts, orders, provider rows or security outcomes:
`constituent-history collection escaped query bounds`. R-069 consumes shared
look **68 -> 69** and development evaluation **15 -> 16**, adds zero cells,
and leaves the floor at **579**.

The unflattened QC ETF-universe Series contained at least one collection
outside the explicit history request. No frozen 2021-2025 decision can select
such a collection. The corrected successor loader still authenticates the
Series/index shape, universe identity and collection `EndTime` type, then
ignores out-of-window collections before duplicate storage or row-payload
traversal. It still requires in-range history and fully validates the latest
strictly-prior selected snapshot without fallback. R-070 and R-071 were never
launched and are superseded by fresh identities that bind this correction.

| Ledger | Profile identity | Projection identity | Accounting on successful aggregate read |
|---|---|---|---|
| `R-072`; `arv2-eval-stock-spy-holdings-intersection-qc-011` | `arv2-stock-long-only-spy-holdings-intersection-2021-2025-r072-v3`; `6667bdeb213b6eaa7f53f56beba042a0aa82e78a664910c495008a7453184681` | `arv2-preliminary-qc-projection-4c2707b03e02f8d24fade31e`; `4c2707b03e02f8d24fade31e898604590250d1f11389cde5fbbf059d92c4f25f`; 7 files, 232,624 total / 59,100 max bytes | looks 69 -> 70; evaluations 16 -> 17; cells 579 -> 583 |
| `R-073`; `arv2-eval-stock-qqq-holdings-intersection-qc-012` | `arv2-stock-long-only-qqq-holdings-intersection-2021-2025-r073-v5`; `2aaee2733ad8c7fcfa4cddcf4ed085ea2a6f082917d16c8ad27bc43de3bc02c2` | `arv2-preliminary-qc-projection-04992d775f0ed55e07a1f3c0`; `04992d775f0ed55e07a1f3c01fc2459a2b37c62447da5b0e13cd1d64084c3161`; 7 files, 232,913 total / 59,100 max bytes | looks 70 -> 71; evaluations 17 -> 18; cells 583 -> 587 |
| `R-074`; `arv2-eval-stock-spy-qqq-intersection-union-qc-013` | `arv2-stock-long-only-spy-qqq-intersection-union-2021-2025-r074-v4`; `a3f568e6c5be11c13a000206ba248a8430c5586aba4957253d374adff250c931` | `arv2-preliminary-qc-projection-231586bf20e5cd7cf57ec006`; `231586bf20e5cd7cf57ec006b11789c964a59bb0030bde3970fc098919a85e28`; 7 files, 232,920 total / 59,100 max bytes | looks 71 -> 72; evaluations 18 -> 19; cells 587 -> 591 |

Their prospective private projects are `18 ARV2_STOCK_R072_SPY_2021_2025 -
20260916`, `19 ARV2_STOCK_R073_QQQ_2021_2025 - 20260916`, and `20
ARV2_STOCK_R074_SPY_QQQ_2021_2025 - 20260916`; their backtests are `ARV2 R072
SPY query-window retry e9851c2f`, `ARV2 R073 QQQ query-window retry
e9851c2f`, and `ARV2 R074 SPY QQQ query-window union retry e9851c2f`. This
block is frozen before any creation, launch or outcome read. QQQ remains a
Nasdaq-100 holdings proxy, not all Nasdaq-listed stocks. No result may select
a same-window winner or unlock leverage, formal acceptance, deployment,
broker access, orders, paper/live state or trading.

## R-072 result, R-073 disposition, and R-075/R-076 successors — 2026-09-16

R-072 completed in private QC project `36633844`, backtest
`e1d3a802a65dad1abd1c07d66bc52722`, after 64 statistics-free polls. Plan,
launch and terminal SHA-256 values are
`bd0632ac8c2293dab9ac4adbee8582a2dda3ebbcddba547b3a33e6cabd338e82`,
`735bbc75e668ced652cb73629b1883dce330099f3aea5c89038f92f0a0ac1927`,
and `4ce7d3e1ec806d85fbd2b6d4d4b1412dcf81eb5b2cabc36bf1c8b1aeb4303236`.
One signed read authenticated exactly six aggregate statistics. Aggregate
receipt SHA-256 is
`aa3380cee5b0d233b5ed5c01b4db37cbc42e9a25aee1e795708528ac0b4d24cf`;
custom-statistics SHA-256 is
`a2abd4b76eb6735b235c70e49f42a798550103115c6f5180d86278f18d899c79`.
No raw provider row, unrestricted log, chart or order was selected.

| Cost per side | Signal | Matched | SPY | Signal minus matched | Signal minus SPY | Maximum drawdown |
|---:|---:|---:|---:|---:|---:|---:|
| 0 bps | +76.5951% | +57.8850% | +94.2074% | +18.7101 pp | -17.6122 pp | -19.2593% |
| 5 bps | +74.9613% | +57.3180% | +94.2074% | +17.6433 pp | -19.2460 pp | -19.3048% |
| **10 bps primary** | **+73.3425%** | **+56.7530%** | **+94.2074%** | **+16.5895 pp** | **-20.8649 pp** | **-19.3502%** |
| 20 bps | +70.1494% | +55.6291% | +94.2074% | +14.5203 pp | -24.0580 pp | -19.4410% |

At the primary cost the signal's annualized arithmetic return is 12.3544%,
zero-rate Sharpe is 0.7667, average cash is 8.3281%, and daily two-sided
turnover is 1.48344% (about 373.83% under a simple 252-session
annualization). It executes all 261 decisions at 91.6700% mean gross and
about 46.77 holdings. The matched comparator also executes all 261. R-072 is
positive selection evidence relative to that matched SPY-holdings-proxy
universe (+16.5895 points at 10 bps), but it trails capitalization-weighted
SPY by 20.8649 points. It remains preliminary, current-vintage/non-pristine-
PIT, exposure-underfilled, without a terminal-payoff splice, and is not a
formal alpha or promotion result.

R-073 launched once in project `36635211`, backtest
`c8295621931bcdca7e332179b3ae891a`, and reached authenticated `Runtime Error`
after two polls: `constituent-history prior snapshot is stale`. Plan, launch
and terminal SHA-256 values are
`5120a91755b43b9e4aae7b32ad9c82962c5bc9dfb586ebe17d08614f98c60e12`,
`a2b67edf7febbd16ba949ea74c58b41f361f5a4820edc05edccc6813784a5b49`,
and `c1368a9e0615c6c66171f7e926956aa111c2e1e0aefa82909fc40a8261409619`.
A bounded diagnostic selected only the error and stack. No result permit or
outcome value exists. R-073 moves looks 70 -> 71 and evaluations 17 -> 18,
adds zero cells, and leaves the floor at 583. R-074 was never launched and is
superseded unspent.

The failure showed that the ten-day rule treated absence of a newer full
holdings file as expiration of the latest authenticated holdings state. The
fresh profiles instead keep each strictly-prior collection-`EndTime` state
effective only until a later collection supersedes it. This changes no signal
or portfolio rule and retains every no-lookahead, identity, selected-state,
weight and mapping guard. The correction is frozen before either successor
launch:

| Ledger | Profile and SHA-256 | Projection and SHA-256 | Accounting on successful read |
|---|---|---|---|
| `R-075`; `arv2-eval-stock-qqq-holdings-intersection-qc-014` | `arv2-stock-long-only-qqq-holdings-intersection-2021-2025-r075-v6`; `71b14b7d5508054f191e7d75114df7dfe680e815fafa52f0a49aa5bc64432667` | `arv2-preliminary-qc-projection-c7e6b9c750f167015a81227d`; `c7e6b9c750f167015a81227da89c3034833c00350f4ed104cd4f39305e5c11fc`; 7 files, 236,355 total / 59,872 max bytes | looks 71 -> 72; evaluations 18 -> 19; cells 583 -> 587 |
| `R-076`; `arv2-eval-stock-spy-qqq-intersection-union-qc-015` | `arv2-stock-long-only-spy-qqq-intersection-union-2021-2025-r076-v5`; `3fa2fcb4f21eea414b0ac425f623d1113d8a648538d5e3ac2bde7dc485aab821` | `arv2-preliminary-qc-projection-699a1b0c706a99e53e067b04`; `699a1b0c706a99e53e067b04aab247c2f197fe686ccece1a8e616bf39f82bc3a`; 7 files, 236,362 total / 59,872 max bytes | looks 72 -> 73; evaluations 19 -> 20; cells 587 -> 591 |

Prospective projects are `21 ARV2_STOCK_R075_QQQ_2021_2025 - 20260916` and
`22 ARV2_STOCK_R076_SPY_QQQ_2021_2025 - 20260916`; backtests are `ARV2 R075
QQQ carried-state retry e9851c2f` and `ARV2 R076 SPY QQQ carried-state union
retry e9851c2f`. QQQ is a Nasdaq-100 holdings proxy, not all Nasdaq-listed
stocks; the union is an exact-security-ID-deduplicated SPY-plus-QQQ holdings
proxy. Results cannot select a same-window winner, tune the score, or unlock
leverage, formal acceptance, deployment, broker access, orders, paper/live
state or trading.

## R-075 failure and R-077/R-078 membership-census successors — 2026-09-16

R-075 launched once in private project `36636665`, backtest
`bf4e0fc5a2cfc9d9cd1bab6dab398606`, and reached authenticated `Runtime Error`
after two statistics-free polls: `constituent-history total positive weight
escaped bounds`. Its plan, launch and terminal SHA-256 values are
`64f279da7ea692822e41d473026febabf8136952302e2273d473bd37b73936c2`,
`710c08529237a6e8c6cfaca39fdd238783e30e8b8c0610734572adca350072f3`,
and `e0af203a4b1b7f818f4b6cc1e6bc41311da5ad1a6ab601a85532d182567f980b`.
A bounded exact-run diagnostic selected only identity, status, error and stack.
No result permit or outcome value exists. R-075 moves looks 71 -> 72 and
evaluations 18 -> 19, adds zero cells, and leaves the floor at 583. R-076 was
not launched and is superseded unspent.

The total-weight bound tests approximate ETF replication, but these profiles
use the payload only to establish point-in-time membership and do not weight
the portfolio by ETF constituent weight. Fresh R-077/R-078 therefore retain
positive finite row evidence, strict-prior collection `EndTime`, state until
superseded, unique SIDs, exact reverse mapping and nonempty score-census
intersection, but replace the replication-weight sum with preregistered
membership-shape bounds: QQQ 75-125 positive constituents and SPY 400-600.
They make no official-index, coverage-completeness or ETF-replication claim.

| Ledger | Profile and SHA-256 | Projection and SHA-256 | Accounting on successful read |
|---|---|---|---|
| `R-077`; `arv2-eval-stock-qqq-holdings-intersection-qc-016` | `arv2-stock-long-only-qqq-holdings-intersection-2021-2025-r077-v7`; `981ad7d698d792542bb68aeb31f18faea1e9c35328fb8b599b92849e07d8b9ee` | `arv2-preliminary-qc-projection-300f114d7a2663de82057b71`; `300f114d7a2663de82057b71994b5025cdd024ec3763edff7e23b5f021cad05d`; 7 files, 238,761 total / 59,444 max bytes | looks 72 -> 73; evaluations 19 -> 20; cells 583 -> 587 |
| `R-078`; `arv2-eval-stock-spy-qqq-intersection-union-qc-017` | `arv2-stock-long-only-spy-qqq-intersection-union-2021-2025-r078-v6`; `04400da58aeaee37edba2685bcaaaf1878f88c542bfb342211698e308cf3d87d` | `arv2-preliminary-qc-projection-4d09391c29bdc20d93de40d1`; `4d09391c29bdc20d93de40d1faa35d075301e2ce3afd85ce2d100edce1736ea8`; 7 files, 238,768 total / 59,444 max bytes | looks 73 -> 74; evaluations 20 -> 21; cells 587 -> 591 |

Prospective projects are `23 ARV2_STOCK_R077_QQQ_2021_2025 - 20260916` and
`24 ARV2_STOCK_R078_SPY_QQQ_2021_2025 - 20260916`; backtests are `ARV2 R077
QQQ membership-count retry e9851c2f` and `ARV2 R078 SPY QQQ membership-count
union e9851c2f`. This block is frozen before either project creation, compile,
launch or outcome read. QQQ remains a Nasdaq-100 holdings proxy, not all
Nasdaq-listed stocks; the union remains an exact-SID SPY-plus-QQQ holdings
proxy. Results cannot select a same-window winner, tune any rule, or unlock
leverage, formal acceptance, deployment, broker access, orders, paper/live
state or trading.

## R-077/R-078 authenticated stock-universe results — 2026-09-16

Both exact preregistered membership-census successors completed in private
QC projects and received one separately signed aggregate-only result read.
R-077 used project `36638005`, backtest
`06584e75d6e90fa25018ae71e1d85468`; aggregate receipt SHA-256 is
`f63f62550fbf36d6d4ee7d7b9a0e9e284ec3b1798e1420e238401a0f33e64dc3`.
R-078 used project `36639211`, backtest
`ecf704c925215b2196e7a8511546d27b`; aggregate receipt SHA-256 is
`b1cbfc9c01ed67e0006b2aaba9a0157d301021911414b490e1e0d0ec5b032fec`.
Each read selected exactly six custom aggregate statistics and no provider
row, unrestricted log, chart or order.

| Run / cost per side | Signal | Matched | SPY | Signal minus matched | Signal minus SPY | Maximum drawdown |
|---|---:|---:|---:|---:|---:|---:|
| R-077 / 0 bps | +9.0656% | +8.8625% | +94.2074% | +0.2031 pp | -85.1417 pp | -12.0150% |
| R-077 / 5 bps | +8.7829% | +8.7594% | +94.2074% | +0.0235 pp | -85.4244 pp | -12.0691% |
| **R-077 / 10 bps primary** | **+8.5010%** | **+8.6564%** | **+94.2074%** | **-0.1554 pp** | **-85.7064 pp** | **-12.1231%** |
| R-077 / 20 bps | +7.9392% | +8.4507% | +94.2074% | -0.5115 pp | -86.2681 pp | -12.2312% |
| R-078 / 0 bps | +70.9113% | +55.8818% | +94.2074% | +15.0295 pp | -23.2960 pp | -20.3325% |
| R-078 / 5 bps | +69.2545% | +55.2942% | +94.2074% | +13.9602 pp | -24.9529 pp | -20.3785% |
| **R-078 / 10 bps primary** | **+67.6135%** | **+54.7088%** | **+94.2074%** | **+12.9048 pp** | **-26.5938 pp** | **-20.4245%** |
| R-078 / 20 bps | +64.3790% | +53.5444% | +94.2074% | +10.8346 pp | -29.8284 pp | -20.5992% |

R-077 averaged nine holdings and only 17.64% gross exposure because its
top-decile selection retained the frozen 1.96%-per-name cap; 82.36% average
cash dominates its absolute result. Its matched comparator had the same gross
exposure and the primary-cost spread is negative, so the run provides no
convincing QQQ-proxy selection edge. R-078 averaged 47.71 holdings and 93.51%
gross exposure. Its +12.9048-point primary-cost matched spread is tangible
positive selection evidence inside the SPY-plus-QQQ holdings proxy, but it
still trails SPY and is weaker than R-072's SPY-only matched spread.

The matched QQQ and union accounts record respectively three and fourteen
membership-end zero recoveries, versus zero for each signal account; that
lower-bound asymmetry can overstate the apparent selection spread by an
unknown amount. Inputs remain current-vintage/non-pristine-PIT, ETF holdings
are proxies rather than official memberships, the terminal-payoff splice is
absent, and these descriptive same-window results cannot select a winner or
authorize tuning, leverage, promotion, deployment, broker access, orders,
paper/live state or trading. Accounting is now **74 shared looks, 21 ARV2
development evaluations, 23 infrastructure looks and a 591-cell floor**.
