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

## R-079 — Analyst Revisions V2 sampled PIT market-cap and ETF-membership coverage canary (PREREGISTERED; OUTCOME-FREE)

R-079 is the next shared run-level entry if and only if the fresh canary reaches
`backtests/create`. It is an outcome-free infrastructure diagnostic over
sixteen preregistered 2025/2026 sessions. It may durably return only aggregate
fundamental, positive-market-cap, SPY-membership, QQQ-membership and
SOXX-membership counts plus bounded collection-availability timestamps. It
cannot read or report prices, returns, statistics, charts, orders, holdings,
security identifiers, constituent weights, raw market-cap values, or provider
rows.

The earlier submission identity created QC project `36642921` but refused on
the platform-created `research.ipynb` before source upload, compile, or
backtest launch. It therefore has no R-number and consumes no look. The fresh
retry is project
`26 ARV2_PIT_MARKET_CAP_MEMBERSHIP_COVERAGE_RETRY - 20260917`, backtest
`ARV2 outcome-free PIT market-cap and ETF-membership coverage retry 1`,
projection
`arv2-pit-market-cap-membership-projection-fc7b6963a4b665bcc16999fa`
(SHA-256
`fc7b6963a4b665bcc16999fa5543c314a9c284228d9e994c15590b90437c150b`),
and submission plan
`arv2-pit-market-cap-membership-probe-plan-b5d4385ef36764121aaf23ae`
(SHA-256
`b5d4385ef36764121aaf23ae4df4a4c08bca46a6137f6c8f3b047f207237698f`).
This block is frozen before permit spend.

Once launched, R-079 moves shared looks **74 -> 75** and infrastructure looks
**23 -> 24**, even if its terminal state is a named refusal or runtime error.
ARV2 development evaluations remain **21** and the lifetime alpha-cell floor
remains **591**. No R-079 result may select a strategy, tune an economic rule,
or unlock an outcome run, leverage, deployment, broker access, orders,
paper/live state, or trading.

## R-079 disposition and R-080 outcome-free summary-channel successor — 2026-09-17

R-079 launched once in private QC project `36643367`, backtest
`a2b58090c188fd040217af6c302751b8`, and reached authenticated `Completed.`
after one statistics-free poll. Launch and terminal SHA-256 values are
`334ec5d733f9fb40cb6a32f3d38da23539d64f6a3d6258be9b342c83f70fb300`
and `ce92a3e69a21808e79fc379885ee8cd344064b68cee5fb6bd2138ec3cf6a4174`.
The permitted API Object Store export then returned `success:false` before any
bytes were delivered; a metadata-only check showed that the 798-byte terminal
pointer exists inside QC. The output permit is consumed. R-079 spends shared
look **74 -> 75** and infrastructure look **23 -> 24**, but yields no selected
count, price, return, outcome, order, identifier or raw provider value. Its
status is completed-run/output-unavailable, not coverage success or failure.

The locally signed project-27 candidate made no permit, network call, project,
compile, backtest or look and is superseded unspent. Fresh **R-080** is
preregistered before any external action. It repeats the same sixteen sampled
sessions under private project `28 ARV2_PIT_MARKET_CAP_MEMBERSHIP_SUMMARY_R080
- 20260917`, backtest `ARV2 R080 outcome-free PIT market-cap and ETF-membership
summary`, projection
`arv2-pit-market-cap-membership-projection-6e4128b67ff7604551bf263a`
(SHA-256
`6e4128b67ff7604551bf263a7730a02d247af28d0e37fab5fda966b6882e225f`),
source-set SHA-256
`d511993d530a2ac223d6d9c02fcb303b58ff7ca86f4ae7bbe76509752190ae13`,
and submission-plan SHA-256
`8786f8fb98c52cf4f2292e0b2b7f88c8f0fe774913b642d1340fa8ef7b16ac08`.

On launch, R-080 moves shared looks **75 -> 76** and infrastructure looks **24
-> 25**; development evaluations remain **21** and the cell floor remains
**591**. The full receipt remains inside QC. One separately permitted
`backtests/read` may select only the canonical, at-most-4,096-character
`ARV2_PIT_MARKET_CAP_MEMBERSHIP_COVERAGE` attestation. Success requires all
sixteen sessions to have positive market-cap coverage plus nonempty and
market-cap-covered SPY, QQQ and SOXX membership. The attestation may contain
only aggregate counts, bounded availability extrema, lineage and internal
object hashes/sizes; all raw rows, identifiers, weights, market-cap values,
prices, returns, outcomes, orders and full-object export remain forbidden.
R-080 cannot select a strategy, tune an economic rule, authorize leverage, or
unlock deployment or trading.

## R-080 disposition and R-081 corrected-timestamp successor — 2026-09-17

R-080 launched once in private QC project `36644379`, backtest
`3a9dbca993f41ac41177d2c15bb84450`, and reached authenticated `Completed.`
after two statistics-free polls. Its one permitted `backtests/read` selected
only a bounded named-refusal attestation, artifact SHA-256
`0ca3b24f005475d912a8e74283aef112c9f93331991f8d97a8cc1441818bfcf3`:
`pit_coverage_refused_ValueError_1b17331bb939b176`. The exact reviewed R-080
runtime maps that digest to `ETF constituent row EndTime differs from
collection`. No raw row, identifier, weight, market-cap value, price, return,
outcome, holding or order was selected. R-080 is final and spends shared look
**75 -> 76** and infrastructure look **24 -> 25**; development evaluations
remain **21** and the cell floor remains **591**.

That refusal is a runtime-semantics defect, not evidence of absent data. The
corrected rule treats the unflattened history Series/multi-index collection
timestamp as the sole availability time and never reads a constituent row's
separate `EndTime`. Fresh outcome-free **R-081** is preregistered before any
external action under project
`29 ARV2_PIT_MARKET_CAP_MEMBERSHIP_SUMMARY_R081 - 20260917`, backtest
`ARV2 R081 outcome-free PIT market-cap and ETF-membership summary retry 1`,
contract SHA-256
`32c0583525a2e3cbf677a5ac387b7cd589338146bd0bcaa03da3e0f2200b3525`,
projection SHA-256
`17d4cc56a0b3e2a28e442c74c4ff52bea1d57d45fa4cfd17c7da1b93c98887f3`,
source-set SHA-256
`db2cb863496f9c629361ad4fae68ab508bbc2fb30d46f1645dfb20582d420c34`,
and submission-plan SHA-256
`bfddaa18a7c11c38a6ec1b66f18a6904590b2bb71c67b00bf733525bd00838f8`.

On launch, R-081 moves shared looks **76 -> 77** and infrastructure looks
**25 -> 26**; development evaluations remain **21** and the cell floor
remains **591**. It repeats the same sixteen sampled sessions and may select
only the same bounded aggregate coverage attestation. It is not an alpha
evaluation and grants no tuning, leverage, deployment or trading authority.

## R-081 disposition and R-082 duplicate-SID coverage successor — 2026-09-17

R-081 launched once in private QC project `36644829`, backtest
`1cdc40ccd41877743ad907020a6e2e31`, and reached authenticated `Completed.`
after two statistics-free polls. Its one permitted `backtests/read` selected
only bounded named refusal
`pit_coverage_refused_ValueError_bef7b6927d4aa871`, artifact SHA-256
`4b12471d87f9a7ed918a6a292775e6bc2527deaabc27bda7b3e80c9a2a0af8a1`.
The exact R-081 runtime resolves it to `fundamental collection duplicated an
exact SID`. No raw row, identifier, weight, market-cap value, price, return,
outcome, holding or order was selected. R-081 is final and spends shared look
**76 -> 77** and infrastructure look **25 -> 26**; development evaluations
remain **21** and the cell floor remains **591**.

Fresh outcome-free **R-082** freezes a coverage-only duplicate policy before
external action. Exact fundamental SIDs may collapse only when all repeated
rows share one of four frozen coverage classes: positive, null, nonpositive,
or invalid. Conflicting classes named-refuse; ETF duplicates still refuse.
Duplicate values are neither compared with each other nor emitted, and this
does not authorize production market-cap value selection. The v2 contract is
`e402e58ac9073ee198654cdbc88267ff5795fb98ce9210172dbaf176cbc627d4`.
The private project is
`30 ARV2_PIT_MARKET_CAP_MEMBERSHIP_SUMMARY_R082 - 20260917`; the backtest is
`ARV2 R082 outcome-free PIT market-cap and ETF-membership summary retry 2`.
The plan is
`arv2-pit-market-cap-membership-plan-c68f3356759c1d25abf324f3`
(semantic SHA-256
`108e035ecf8204501526de4fe7e8dac9390b004ef8fbb848a55a716a036a5990`,
artifact SHA-256
`97afe6f3b66afa2579737e040576f594ad365b5d85d2c72206f7a4d929d1cd6f`);
the projection SHA-256 is
`fb892cce42d48e658137843e5690177054c9b58470c7ee1937607b59591d6583`;
the two-file source set SHA-256 is
`9c71c5650813c4e9281f8746edd4ff2c658c1883a60f89d779cb75af6e7b812e`;
the submission-plan SHA-256 is
`dfdd5f9920bd245c72ed1609f696997f620cd2c4f40e0b62f897aa081b1b1ba9`;
the review-claim semantic SHA-256 is
`91d8b3ad867c6d53306b5dc5d308187691b739b245fd68260ac8982b00db2ee8`;
and the unsigned execution-authority bytes SHA-256 is
`d4ef0075939479f7b286c72017ee51cae35b16d2ad220aba6298b34330f5d0e9`.

On launch, R-082 moves shared looks **77 -> 78** and infrastructure looks
**26 -> 27**; development evaluations remain **21** and the cell floor
remains **591**. It repeats the same sixteen sampled sessions and may select
only the bounded aggregate v2 coverage attestation. It is not alpha evidence,
does not authorize production market-cap ranking, and grants no tuning,
leverage, deployment or trading authority.

## R-082 completed PIT market-cap/membership coverage canary — 2026-09-17

R-082 launched once in private QC project `36645473`, backtest
`c90394212ee91c89f0428b3533de45d9`, and reached authenticated `Completed.`
after one statistics-free poll. Its one permitted `backtests/read` selected
only the 3,137-byte v2 aggregate attestation, artifact SHA-256
`60e3e3185a301aec3de7b14d5f4ad58cd10dfc4b30c39d387083fea7db74895b`.
All **16 of 16** sampled sessions passed. The canary processed 1,944,801
source rows; aggregate fundamentals contained 169,080 rows and 169,078 exact
SIDs, including two same-class redundant rows that the frozen v2 policy
collapsed. It observed 74,405 positive-market-cap SIDs. Aggregate positive
SPY/QQQ/SOXX membership was 8,434, with 8,200 market-cap covered and 234
uncovered. Per-session member / covered ranges were SPY 501--503 / 494--497,
QQQ 99--103 / 94--97, SOXX 30 / 24, and combined union 525--528 / 510--514.

No individual SID, constituent weight, market-cap value, raw row, price,
return, outcome, order, holding or portfolio statistic was emitted or read.
This is positive physical-coverage evidence for building the later continuous
point-in-time input; it is not alpha evidence and does not itself authorize a
market-cap-ranked strategy run. R-082 spends shared look **77 -> 78** and
infrastructure look **26 -> 27**. The append-only infrastructure ledger is now
sequence 6, ledger SHA-256
`4a726bcdd9b7232f34a1eaf891f7b8f83334002396aa48720b19abd22391305e`,
artifact SHA-256
`e837946d6fe9d31f16d4a901f878e965036f6931f8ed5bb1806fdb5a1c83cdd9`.

## R-083 through R-090 — market-cap matrix and objective leverage diagnostics (PREREGISTERED; UNRUN) — 2026-09-17

The owner authorized this exact next sequence after independent Claude review
and Codex counter-review. The six unlevered point-in-time market-cap runs are
R-083 through R-088; the two synthetic-leverage diagnostics are R-089 and
R-090. This block is committed before any project creation, upload, compile,
backtest launch, terminal inspection, or result read. The shared package
SHA-256 is
`e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9`;
the host-code-closure SHA-256 for every plan is
`f2e114d751775a448017bd30b7d7dea68e3ab794ac5094bb9609ed4a20e49792`.

| Run | Fixed profile and profile SHA-256 | Exact private project / backtest | Projection ID and SHA-256 | Source-set SHA-256 | Expected-names SHA-256 / count | Submission-plan ID and SHA-256 |
|---|---|---|---|---|---|---|
| R-083 | `arv2-market-cap-stock-qqq-2021-2025-v1` / `3025fff20f0742b60b5e75af22bc71230608fcc7a3af9b043c0c8865dfe0548e` | `31 ARV2_MARKET_CAP_QQQ_R083_2021_2025 - 20260917` / `ARV2 R083 market-cap QQQ 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-215cb2240321828f85195737` / `215cb2240321828f8519573717a356d2c1be590f502aa382817df15589d0faee` | `1880250e2bf83c100a77a6101e37c850a58fa38e2d9bb3d91ba92b4b18062f43` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-e2a33caa678ee14a2d7b83de` / `e2a33caa678ee14a2d7b83de345b2bc35ff515c81cbfd12d49d7c9e09b26cfb4` |
| R-084 | `arv2-market-cap-stock-spy-2021-2025-v1` / `6dcb9a08790a40407622d5a6ec34e5cd8fab5978d8e4cdc0f1ba16fb984063d7` | `32 ARV2_MARKET_CAP_SPY_R084_2021_2025 - 20260917` / `ARV2 R084 market-cap SPY 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-2d011b0a1ab1ba000463db32` / `2d011b0a1ab1ba000463db32611468a62b43e1c98fed1ac544cbb29af9b667ea` | `3f559680b795ec7e181618a631fc261941dd0282d0462283a13491c0791dc08d` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-077b7f9fe2ef4eebcc112908` / `077b7f9fe2ef4eebcc11290809e846c6d736fa266fd2b28911d39429c60053d0` |
| R-085 | `arv2-market-cap-stock-qqq-2019-2023-v1` / `1069bb9717584632cc64a11394ff0cb7bef1d080d4ed0a79ca9eaaf1975596c0` | `33 ARV2_MARKET_CAP_QQQ_R085_2019_2023 - 20260917` / `ARV2 R085 market-cap QQQ 2019-2023 e9851c2f` | `arv2-preliminary-qc-projection-f63cc6775c370392bca6a113` / `f63cc6775c370392bca6a1137620d6587c21229161e64fddb20869da4f7e0d53` | `b921be6ac732312bdd31eb69d97f1acd607b0e03b22c412b83d349e19492cc0c` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-b961c522c05ab0ca6253b4e4` / `b961c522c05ab0ca6253b4e4dd104791685850e13f8634f7b260249e8b06ff2d` |
| R-086 | `arv2-market-cap-stock-spy-2019-2023-v1` / `75f0841eeddbba74f4ac618b754a6d31698716bb5baf12d96461c8f10ea18cde` | `34 ARV2_MARKET_CAP_SPY_R086_2019_2023 - 20260917` / `ARV2 R086 market-cap SPY 2019-2023 e9851c2f` | `arv2-preliminary-qc-projection-9a2990b803405612085a9bfd` / `9a2990b803405612085a9bfdedb7a973508d3dcc72a1b740113967f89e34eaf5` | `dcf4e7110f75e62c1aa99fd29db0ee5568d9eaf0c0e9b8723dc8e9a5b67e12b9` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-ed5f7cba15734cac805887d7` / `ed5f7cba15734cac805887d70cafde094e15745ee3e27bd501a34c53673dadf0` |
| R-087 | `arv2-market-cap-stock-qqq-2023-2025-v1` / `a6eeb831372894fd2ba2d95a6a23daefffe86555dd0d93a97a63d977fc27cc05` | `35 ARV2_MARKET_CAP_QQQ_R087_2023_2025 - 20260917` / `ARV2 R087 market-cap QQQ 2023-2025 e9851c2f` | `arv2-preliminary-qc-projection-a3130fd85e0864746bf40451` / `a3130fd85e0864746bf4045140e414f5de911dd5e2bac0e5217e6251866a9c4e` | `7ccd46bc8bebe39b8b46c15aa414836a265d3b492ed5f36cf509fce2d6ad718d` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-0bb219f78c806dafe912840b` / `0bb219f78c806dafe912840bfaba741432d5e495e6ef1f6f502bb56f5c784ce2` |
| R-088 | `arv2-market-cap-stock-spy-2023-2025-v1` / `bbc3e88fd66cd8ad93ec1d3e48675c03df75460922e0c21d855dc8aa27ab68e4` | `36 ARV2_MARKET_CAP_SPY_R088_2023_2025 - 20260917` / `ARV2 R088 market-cap SPY 2023-2025 e9851c2f` | `arv2-preliminary-qc-projection-47653858e49c370c519d1ad0` / `47653858e49c370c519d1ad002906115657c5b2453c8d357fc7aeca1893c8ab7` | `5b38b95a465467a8f6a0ce4cb803fae8a3d2f8abe083368a28a51615a1f6d564` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-11b9c64a5b645e9679412164` / `11b9c64a5b645e96794121644c4ccf914fc9b690068febe92b31f75cd1483610` |
| R-089 | `arv2-objective-synthetic-leverage-qqq-2021-2025-v1` / `e9ed4d6e1df27c38273958ddfc66b4d8d0adc62c5995bb2f5941d7d3540cc68e` | `37 ARV2_LEVERAGE_QQQ_R089_2021_2025 - 20260917` / `ARV2 R089 synthetic 2x3x QQQ 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-bb35ffb605a2825585c6d933` / `bb35ffb605a2825585c6d93387a368f5a21021de5cb438fa4eb8f1748ac11c76` | `1b297af2aedfa084943bdca46ea50237d705a62ef633f205f6033a16f0cf9407` | `5593312bfb9c79ecdb0ec9e6ebfa709655e7bb40acdfece13cf53c83a6f0a26d` / 6 | `arv2-preliminary-qc-submission-11022a9c630bfd0593d74c45` / `11022a9c630bfd0593d74c45dd45ade000f69936546ee7e781df2554ba24efa5` |
| R-090 | `arv2-objective-synthetic-leverage-spy-2021-2025-v1` / `ed7e3151daf3ae5868695e7753b0bb47119555124efe457cbca5db26a4208584` | `38 ARV2_LEVERAGE_SPY_R090_2021_2025 - 20260917` / `ARV2 R090 synthetic 2x3x SPY 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-c8e4921fe7ba62d6722ee451` / `c8e4921fe7ba62d6722ee45147fd24c2c28ddc78ae45387adaa6914b1ae49321` | `67a9f4bd181c978ce2fedc883b0a467d69ea59e55d863e5679df17ca79ecccbc` | `5593312bfb9c79ecdb0ec9e6ebfa709655e7bb40acdfece13cf53c83a6f0a26d` / 6 | `arv2-preliminary-qc-submission-dd65df97f35e2c1327d9e7ab` / `dd65df97f35e2c1327d9e7ab168e8371e9772bdb1bfc784b08da56e29741be70` |

R-083 through R-088 each preserve the reviewed weekly R-055 score, select the
top decile capped at fifty, and weight the selected sleeve and full eligible
matched comparator separately by exact strictly-prior point-in-time market
capitalization to 98% target gross. QQQ is the QQQ-holdings Nasdaq-100 proxy;
SPY is the SPY-holdings S&P 500 proxy. They retain next-open execution,
adjusted opens, per-name deferral, symmetric eligibility-exit sensitivity, and
the fixed 0/5/10/20-bps-per-side ladder with 10 bps primary.

Before any result is read, the interpretation is fixed as follows. A selected
sleeve whose inverse-HHI effective holdings are below **10** is reported as a
concentrated result with fewer than ten equally weighted holdings' worth of
effective diversification; this is not a literal contributor count and does
not by itself invalidate the run. Both accounts' zero-recovery counts are
reported. The three windows overlap and are descriptive, not independent;
their outcomes may not select a winning universe, period, or later rule.

R-089/R-090 apply the already-reviewed whole-portfolio daily-reset 2x and 3x
transforms to the corresponding 2021-2025 market-cap paths under the frozen
primary (10-bps base path, 6% annual financing) and adverse (20-bps base path,
10% annual financing) scenarios. Each full QC result has six authenticated
statistics: four economic cells, evaluator meta, and runtime meta. There is no
preregistered relative-return direction: daily resetting can widen, narrow, or
reverse an unlevered selected-versus-context gap. Interpretation compares
selected and matched paths under identical factors/scenarios and treats no
amplification or reversal as validation by itself.

Physical jobs are sequential on the one subscribed node: R-083 through R-088
first, then R-089 and R-090. A launch spends one shared look and one development
evaluation even if it later refuses; each authenticated result adds four cells.
After all eight launches, accounting is **86 shared looks, 29 ARV2 development
evaluations, 27 infrastructure looks, and a 623-cell floor**. A technical
failure requires a fresh prospective identity; no observed economic result may
choose a retry rule. Exactly one bounded aggregate result read is allowed per
run. No raw provider row, security identifier, price row, log, chart, holding,
order, deployment, broker state, paper/live state, or trading action is
authorized.

## R-083 disposition; R-084 through R-090 superseded unspent — 2026-09-17

R-083 launched once in private project `36664366`, backtest
`087f91701ac3fb19d9ab6433a03227e6`, and reached authenticated `Runtime Error`
after two statistics-free polls. No aggregate result was read and no economic
cell was emitted. One separately authorized, no-redirect technical diagnostic
selected only the terminal error and stack frame: `PIT fundamentals history
collection escaped request bounds`. No raw provider row, identifier, price,
return, chart, order, holding, deployment, broker state, paper/live state, or
trading action was selected.

R-083 is final: shared looks **78 -> 79**, ARV2 development evaluations
**21 -> 22**, infrastructure looks unchanged at **27**, and lifetime cell
floor unchanged at **591**. A local signature revalidation refusal before
network access spent no look. R-084 through R-090 did not launch and spend
nothing; their physical plans are superseded unspent because the bounded
runtime correction changes their projected-source and host-closure identities.

The prospective correction validates each history collection's shape,
universe identity, and timestamp, then ignores only collections outside the
exact request interval before traversing their rows. In-window PIT and
financial rules are unchanged. Fresh v2 profiles preserve the old v1 records
and carry this policy explicitly. R-091 through R-098 are reserved as fresh
technical successors, starting from **79 shared looks, 22 development
evaluations, 27 infrastructure looks, and a 591-cell floor**. Exact physical
identities must be committed before any external action.

## R-091 through R-098 — corrected market-cap matrix and leverage diagnostics (PREREGISTERED; UNRUN) — 2026-09-17

These are fresh technical successors after R-083's zero-cell runtime refusal.
All eight are committed before external action. The common package SHA-256 is
`e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9`;
the common host-closure SHA-256 is
`7b940f4e3750a1929db388ce12c80113bf6faceea87e03ad23ae579cab29b164`.

| Run | Fixed profile and SHA-256 | Exact private project / backtest | Projection ID / SHA-256 | Source-set SHA-256 | Names SHA-256 / count | Plan ID / SHA-256 |
|---|---|---|---|---|---|---|
| R-091 | `arv2-market-cap-stock-qqq-2021-2025-v2` / `71fe35e9a200e61c9c908fe839e244d97bcef89664a921ddaa3dfd09b8a09178` | `39 ARV2_MARKET_CAP_QQQ_R091_2021_2025 - 20260917` / `ARV2 R091 market-cap QQQ 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-18fdadac5cb448b213806815` / `18fdadac5cb448b21380681554f991be5cbdead42e06f69c59ef46e99cc6ac6b` | `abec99591d1c2e0996ad0806d366cc9cedf4f679969ea1645cc0edb187ba4c9f` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-351f3e6c8a1625d295eea49a` / `351f3e6c8a1625d295eea49ac18179469ee3f7d8cbaa0e06e125e936978748bd` |
| R-092 | `arv2-market-cap-stock-spy-2021-2025-v2` / `0b6587206c68452b7468aff42432cb3b587a0f96cc078fbf57a6473f86feb59d` | `40 ARV2_MARKET_CAP_SPY_R092_2021_2025 - 20260917` / `ARV2 R092 market-cap SPY 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-932e7d229cbf429a7af231be` / `932e7d229cbf429a7af231bed0583a92c0b1a0937cb15e4012059772518de092` | `3bbf168d3d13403e3437020fcbbfc72b67ef6bad263118acb7080e6b69e1e870` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-a5e6ee4c9ba783ab577cb95c` / `a5e6ee4c9ba783ab577cb95c14c415bbf6be8671b82644f4721585ae06a4a99c` |
| R-093 | `arv2-market-cap-stock-qqq-2019-2023-v2` / `661d87e282f6c37cc258db7a3e814e5a261369209fc3fc4a96c1769edd71f83d` | `41 ARV2_MARKET_CAP_QQQ_R093_2019_2023 - 20260917` / `ARV2 R093 market-cap QQQ 2019-2023 e9851c2f` | `arv2-preliminary-qc-projection-633a2c795eabe6f6a256941a` / `633a2c795eabe6f6a256941a425e0a74903752cb5b4fe034b389faf31186f419` | `7584ee6347ef889bdcb1fc9fb38f6a3aa7ce68ecd31e9476ce80242b81772b90` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-698709a4f82df7539b1e8458` / `698709a4f82df7539b1e84585d6d51b2927f36ec6098dc1805057e859f150076` |
| R-094 | `arv2-market-cap-stock-spy-2019-2023-v2` / `72a4b469d7f8fa79ea4ea62836b6b43000069b5e0a7dca6941af00124ca68f4a` | `42 ARV2_MARKET_CAP_SPY_R094_2019_2023 - 20260917` / `ARV2 R094 market-cap SPY 2019-2023 e9851c2f` | `arv2-preliminary-qc-projection-7ff8241567e40c3f4d562f35` / `7ff8241567e40c3f4d562f35990d39324cefdde0303d799a60f19a77f9cd1454` | `289faa5cda77982131097b496c84a5b82d66a59fc7cc31f602dda1cc3e493a39` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-821f783530f5ab6eaf88e73d` / `821f783530f5ab6eaf88e73d54794a5a290e881a4a8d138c844e51b043b001ad` |
| R-095 | `arv2-market-cap-stock-qqq-2023-2025-v2` / `da7f4c75b9504c02f209362d2aebf69188d32cf608ac167fd543beb196067f93` | `43 ARV2_MARKET_CAP_QQQ_R095_2023_2025 - 20260917` / `ARV2 R095 market-cap QQQ 2023-2025 e9851c2f` | `arv2-preliminary-qc-projection-d81b0ae9587127588edf57e0` / `d81b0ae9587127588edf57e0885327b79017bb89c6ba91f1a873075b9b9a99e8` | `09bf5ff8bca26e6ed0651b6b5e330a720ac29102f3d96006a257f70c017a745a` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-fd1167f40d0a2930d06a2b17` / `fd1167f40d0a2930d06a2b1727de002015139d1efcad29b23b2618dc77d36550` |
| R-096 | `arv2-market-cap-stock-spy-2023-2025-v2` / `e56aa1c7777720ec36b8414ae2525858d0911b7c7954adca292d211c767fa0b3` | `44 ARV2_MARKET_CAP_SPY_R096_2023_2025 - 20260917` / `ARV2 R096 market-cap SPY 2023-2025 e9851c2f` | `arv2-preliminary-qc-projection-f14bf8d0971f524918486cc3` / `f14bf8d0971f524918486cc398e1740cc591e36d93b34f71d3e881f2eba5cbdc` | `1f69f61835eab8ddf4af69aaf6b87761a2a489737f008055de55e5ca25883562` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-fda4d07a8cf411cdf0bd52d3` / `fda4d07a8cf411cdf0bd52d3b5dff55f8ab6241010981f8066cec7ac582cfb4c` |
| R-097 | `arv2-objective-synthetic-leverage-qqq-2021-2025-v2` / `a800d1db535ca22fa1bcfc238fbcfabbb463e21b18cf3fc384b606542878192e` | `45 ARV2_LEVERAGE_QQQ_R097_2021_2025 - 20260917` / `ARV2 R097 synthetic 2x3x QQQ 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-c0219bb1e02b54a6e143feed` / `c0219bb1e02b54a6e143feedd02df52c933449c84f0f76f9389a8b9af9dc177a` | `5959a840f122571457dc89825a304da3a93f5e6121c6c4a6585a3557577175d9` | `5593312bfb9c79ecdb0ec9e6ebfa709655e7bb40acdfece13cf53c83a6f0a26d` / 6 | `arv2-preliminary-qc-submission-24013e4ea723a3e4a44155b9` / `24013e4ea723a3e4a44155b96b6000f6032f6946e952fbe6980cd3350e0312a7` |
| R-098 | `arv2-objective-synthetic-leverage-spy-2021-2025-v2` / `07106d52bed121064659b97173f66d1776adf5e72f0f231600d2b7b53299a014` | `46 ARV2_LEVERAGE_SPY_R098_2021_2025 - 20260917` / `ARV2 R098 synthetic 2x3x SPY 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-bccf6d655077c63d8541a873` / `bccf6d655077c63d8541a8735bd243f0f990f4184b9bdcd3f14da30b83de967f` | `57e2f557101849a91dcab7fa17e2c56028a379d800e03e710db574a6f7fd4ddd` | `5593312bfb9c79ecdb0ec9e6ebfa709655e7bb40acdfece13cf53c83a6f0a26d` / 6 | `arv2-preliminary-qc-submission-0b70a4cee19ddc24c6d8f295` / `0b70a4cee19ddc24c6d8f295c41e6dbbab43f836e018b9e47ca2e40a39802eb3` |

Control directories are respectively
`artifacts/analyst_revisions_v2/accepted_risk_market_cap_r091_20260917_01`
through `...r096_20260917_01`, then
`artifacts/analyst_revisions_v2/accepted_risk_leverage_r097_20260917_01`
and `...r098_20260917_01`. R-091 through R-096 execute first in order;
R-097/R-098 follow only after the unlevered sequence. The frozen overlap,
effective-breadth, zero-recovery, matched-comparator, and no-leverage-direction
interpretation rules from the R-083--R-090 block carry forward unchanged.

Accounting transitions by launch/result are: R-091 **79 -> 80 / 22 -> 23 /
591 -> 595**, R-092 **80 -> 81 / 23 -> 24 / 595 -> 599**, R-093 **81 -> 82 /
24 -> 25 / 599 -> 603**, R-094 **82 -> 83 / 25 -> 26 / 603 -> 607**,
R-095 **83 -> 84 / 26 -> 27 / 607 -> 611**, R-096 **84 -> 85 / 27 -> 28 /
611 -> 615**, R-097 **85 -> 86 / 28 -> 29 / 615 -> 619**, and R-098
**86 -> 87 / 29 -> 30 / 619 -> 623** for shared looks / development
evaluations / cell floor. Infrastructure looks remain 27. A launch spends its
look and evaluation even if it refuses; cells accrue only from an authenticated
aggregate result. No raw rows, identifiers, prices, logs, charts, holdings,
orders, deployment, broker access, paper/live state, or trading is authorized.

## R-091 disposition; R-092 through R-098 superseded unspent — 2026-09-17

R-091 launched once in private project `36669747`, backtest
`9118721aa50cb6f5ac60eb1fbaa02fe9`, and reached authenticated
`Runtime Error` after 48 statistics-free polls. No aggregate statistic or
economic cell was emitted or read. The one bounded technical diagnostic
selected only `SPY lacks a market-cap portfolio adjusted open` and its stack
frame. The prefixed `2025-08-28 16:00:00` is the simulated failure time, not
the absent observation's date.

The driver had requested the fixed price range through `2026-03-30` before
the QC simulated clock reached that date. The resulting cache was necessarily
incomplete, and the evaluator correctly refused it. Counter-audit also found
that an immature PIT fundamentals or ETF-membership chunk could otherwise look
like a legitimate no-update interval and carry older state forward. The
prospective correction gates every PIT chunk through its final decision date,
then separately waits until the algorithm date is strictly later than the
exact price-History request end. It permits at most four bounded work units per
daily callback under the existing 240-second soft bound. It neither fills nor
imputes a price and changes no economic rule. The longest profile's
all-resolved worst case needs at most 349 post-maturity evaluator units; the
frozen remaining calendar provides 456.

R-091 is final: shared looks **79 -> 80**, ARV2 development evaluations
**22 -> 23**, infrastructure looks unchanged at **27**, and cell floor
unchanged at **591**. R-092 through R-098 did not launch and spend nothing;
their plans are superseded unspent because projected-source and host-closure
identities change. R-099 through R-106 are reserved in the same profile order,
starting from **80 shared looks, 23 development evaluations, 27
infrastructure looks, and a 591-cell floor**. Exact physical identities must
be committed before external action. No raw provider row, identifier, price,
return, log, chart, holding, order, deployment, broker state, paper/live state,
or trading action was selected.

## R-099 through R-106 — clock-gated market-cap matrix and leverage diagnostics (PREREGISTERED; UNRUN) — 2026-09-17

These are the fresh technical successors to R-091. All eight are frozen before
external action. Common package SHA-256:
`e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9`.
Common host-closure SHA-256:
`c725e9c80da75deb4e7389f1cc63cd31134f1b0551675b3163003b35bf5043f3`.

| Run | Fixed profile | Exact private project / backtest | Projection SHA-256 | Source-set SHA-256 | Names SHA-256 / count | Plan ID / SHA-256 |
|---|---|---|---|---|---|---|
| R-099 | `arv2-market-cap-stock-qqq-2021-2025-v2` | `47 ARV2_MARKET_CAP_QQQ_R099_2021_2025 - 20260917` / `ARV2 R099 market-cap QQQ 2021-2025 e9851c2f` | `b4aaa521d24568ba294edb9f60b3e1a5756560c82e645894671e34376d009e71` | `bf2fccbf4fd968a53bbc4aed71c2cbab507f89a999258b4d3e50a18b6a744f2b` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-4e7956cfb620dea10a014894` / `4e7956cfb620dea10a014894b6835b159d1216fa5cee5b5718171b1cb7de438d` |
| R-100 | `arv2-market-cap-stock-spy-2021-2025-v2` | `48 ARV2_MARKET_CAP_SPY_R100_2021_2025 - 20260917` / `ARV2 R100 market-cap SPY 2021-2025 e9851c2f` | `082f3711b9fc91e13e91337c8b5de2593c5ffd36828f42725371d8733121c2d3` | `47c09bd8372440660f100f74396236201b06bcef94c0ec915e5a8bc4ddf88f34` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-cbab031cf694c4e8a9a95a5f` / `cbab031cf694c4e8a9a95a5f8242df679ec6657cb9bf80cee172aec7a74f04d6` |
| R-101 | `arv2-market-cap-stock-qqq-2019-2023-v2` | `49 ARV2_MARKET_CAP_QQQ_R101_2019_2023 - 20260917` / `ARV2 R101 market-cap QQQ 2019-2023 e9851c2f` | `681f0a9c4703d89aa20d3a968db1343896392308e85f1900ee85e143ef6e2de2` | `eba5ccad36b7565623b256623555138e1b17374b64cf7115568b55b0d9a24271` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-ee0f64f0b4f38e279b8213cc` / `ee0f64f0b4f38e279b8213cc063e285d440b46275735f2e84be35c07db205fb6` |
| R-102 | `arv2-market-cap-stock-spy-2019-2023-v2` | `50 ARV2_MARKET_CAP_SPY_R102_2019_2023 - 20260917` / `ARV2 R102 market-cap SPY 2019-2023 e9851c2f` | `a85cbef7ae4bd87a7d6b02c53113e613849108c666402b6104b1da59bfd10dd8` | `4ed43740c6ddb91a94612ff2bc9bb812444e37a5eef305cd8fcf291b2692da10` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-dca5b01e7b033570acd4635c` / `dca5b01e7b033570acd4635cf280999710e16e1e9cb9429946fec7c41bfa3930` |
| R-103 | `arv2-market-cap-stock-qqq-2023-2025-v2` | `51 ARV2_MARKET_CAP_QQQ_R103_2023_2025 - 20260917` / `ARV2 R103 market-cap QQQ 2023-2025 e9851c2f` | `66151b78ad5d86b317163534b12c4b559c4241e451b63386eae8eec9203e7edf` | `ac5fd5856319985da041704d8d0996c8021ee0c47a93a9ebcca10aebff317914` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-47a38e7697e5a34b7c6b6a75` / `47a38e7697e5a34b7c6b6a75030609500b9d249b66658e016e9272b7f57d5f8f` |
| R-104 | `arv2-market-cap-stock-spy-2023-2025-v2` | `52 ARV2_MARKET_CAP_SPY_R104_2023_2025 - 20260917` / `ARV2 R104 market-cap SPY 2023-2025 e9851c2f` | `1af40154411f1268b351476a750aab91d478191e0a9f3812c3c87a7dff7c921a` | `e2a04227f1aa03e510b2aff2d6fea648d2dd9d7b8e5a6fd8b94cb59ad2d90b90` | `17b4b856849c77359c45f3252dcf0d870c61d25810044e447bf797a7eb5aa144` / 6 | `arv2-preliminary-qc-submission-55bcd6e85ca87a42b8b33b30` / `55bcd6e85ca87a42b8b33b302a751bd525e588e1ea8e98fe91272c1c3edac1ab` |
| R-105 | `arv2-objective-synthetic-leverage-qqq-2021-2025-v2` | `53 ARV2_LEVERAGE_QQQ_R105_2021_2025 - 20260917` / `ARV2 R105 synthetic 2x3x QQQ 2021-2025 e9851c2f` | `cfe7ef21c3ed87fda713878ef652e6cbbc916b33ce5e4b2c96ffbde7145aaaba` | `3c1ee7562d23be4761ef82f42bd1fd74adb73f71bde2ee0487eec90970dcd400` | `5593312bfb9c79ecdb0ec9e6ebfa709655e7bb40acdfece13cf53c83a6f0a26d` / 6 | `arv2-preliminary-qc-submission-ce5d859fe95202480034b30e` / `ce5d859fe95202480034b30e0de7b416ba40c7d3e2bf67236360b1bc96213fbe` |
| R-106 | `arv2-objective-synthetic-leverage-spy-2021-2025-v2` | `54 ARV2_LEVERAGE_SPY_R106_2021_2025 - 20260917` / `ARV2 R106 synthetic 2x3x SPY 2021-2025 e9851c2f` | `3cab3fe5711943d8162ba54858cf7cf59487c33f6eedba6a8cab74b0f49c9af1` | `1ca9f6cc4c37271df191c5deb6d6dc8074a9814bd602212448e76387699951a7` | `5593312bfb9c79ecdb0ec9e6ebfa709655e7bb40acdfece13cf53c83a6f0a26d` / 6 | `arv2-preliminary-qc-submission-1f14645f77aa7fdaa75f635f` / `1f14645f77aa7fdaa75f635f1413c91011b4a7f5f6d061a94a47ba63dd77a102` |

Control directories are `accepted_risk_market_cap_r099_20260917_01`
through `...r104_20260917_01`, then `accepted_risk_leverage_r105_20260917_01`
and `...r106_20260917_01`, all below the private lane artifact root. Execution
is sequential: six unlevered runs first, then two leverage runs. Accounting
transitions are R-099 **80 -> 81 / 23 -> 24 / 591 -> 595**, R-100 **81 -> 82 /
24 -> 25 / 595 -> 599**, R-101 **82 -> 83 / 25 -> 26 / 599 -> 603**, R-102
**83 -> 84 / 26 -> 27 / 603 -> 607**, R-103 **84 -> 85 / 27 -> 28 / 607 ->
611**, R-104 **85 -> 86 / 28 -> 29 / 611 -> 615**, R-105 **86 -> 87 / 29 ->
30 / 615 -> 619**, and R-106 **87 -> 88 / 30 -> 31 / 619 -> 623**, for
shared looks / development evaluations / cell floor. Infrastructure looks stay
27. A launch spends its look even on refusal; cells accrue only from an
authenticated aggregate. No raw inputs, logs, charts, holdings, orders,
deployment, broker state, paper/live state, or trading action is authorized.

## R-099 disposition; R-100 through R-106 superseded unspent — 2026-09-17

R-099 launched once in private project `36673484`, backtest
`5150223203bd90ad8a0de4ac1ec1a3b6`, and reached authenticated
`Runtime Error` after 69 statistics-free polls. No aggregate result or
economic cell was emitted or read. A single bounded, no-redirect technical
diagnostic selected only terminal status, error text, and stack frame. The
reason was `market-cap stock custom summary exceeded compact bound` at
simulated `2026-07-28 16:00:00`. Computation reached summary construction;
the refusal was the 4,096-character QC limit on each custom-statistic value,
not an observed portfolio outcome.

The lossless technical correction leaves the complete logical summary,
economics, Decimal strings, and summary digest unchanged. It transports the
selected and matched 21-field account aggregates as two separate exact
canonical statistics, rehydrates them on the host, and then applies the
existing semantic and full-summary identity checks. Direct tests keep every
market-cap statistic at or below 3,072 characters. The same split is applied
prospectively to the unrun leverage envelope, whose fixture META was already
4,079 characters before its production package identity. Historical leverage
profiles are retained and fresh identities bind the changed exact base source.

Before the successor freeze, counter-review corrected the adapter's stale
hand-copied infrastructure count of 23. Look accounting now derives 27 from
the authenticated ledger and refuses disagreement among its declared count,
actual entries, and total. Direct red/green tests also isolate both compact
result-size guards.

R-099 spends shared looks **80 -> 81** and ARV2 development evaluations
**23 -> 24**. Infrastructure looks remain **27** and the lifetime cell floor
remains **591**. R-100 through R-106 never launched and are superseded unspent.
R-107 through R-114 are reserved in the same sequence, starting from
**81 shared looks, 24 development evaluations, 27 infrastructure looks, and
591 cells**. Their exact physical identities must be committed before any
external action. No raw row, identifier, price, return, log, chart, holding,
order, deployment, broker state, paper/live state, or trading action was
selected or authorized.

## R-107 through R-114 — compact-transport successors (PREREGISTERED; UNRUN) — 2026-09-17

These exact plans were derived from committed source `42a70d7` and are frozen
before external action. Common package SHA-256:
`e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9`.
Common host-closure SHA-256:
`83b9ea687e427042d32b3ecfc818648d0b6a17976537ed97c01dae8636f79e52`.

| Run | Fixed profile | Exact private project / backtest | Projection ID / SHA-256 | Source-set SHA-256 | Names SHA-256 / count | Plan ID / SHA-256 |
|---|---|---|---|---|---|---|
| R-107 | `arv2-market-cap-stock-qqq-2021-2025-v2` | `55 ARV2_MARKET_CAP_QQQ_R107_2021_2025 - 20260917` / `ARV2 R107 market-cap QQQ 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-f36adb56604326e16faaddfb` / `f36adb56604326e16faaddfbac2cb71f5efb95ca996d5fb828c4c8a2b4871cef` | `c7c191d70e9d657b6800743f216cf7850b3102e96eb1456e4c32ac9a3f68bd3a` | `9d6fecefdaa6dc007ec10ef1b2f6bfe7d1630c1a00c7b6a3fd66f66d039c18dd` / 8 | `arv2-preliminary-qc-submission-eadda4e4740d365653ba06f4` / `eadda4e4740d365653ba06f42714c4453732ccd5e7221a086694e3fd749e2e06` |
| R-108 | `arv2-market-cap-stock-spy-2021-2025-v2` | `56 ARV2_MARKET_CAP_SPY_R108_2021_2025 - 20260917` / `ARV2 R108 market-cap SPY 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-a04a415ca15f4f21fcbdad68` / `a04a415ca15f4f21fcbdad687993201c4f2c58c4abbfef72b59beabd56aced99` | `81dfee62a7255db347a856aab9f03a71ceebeff8cc975b91c3bdbc96c52ace43` | `9d6fecefdaa6dc007ec10ef1b2f6bfe7d1630c1a00c7b6a3fd66f66d039c18dd` / 8 | `arv2-preliminary-qc-submission-fd2b13a23ffedbbf10d7793c` / `fd2b13a23ffedbbf10d7793c3018ae8f179b1c15bfb72366411474dc56845c33` |
| R-109 | `arv2-market-cap-stock-qqq-2019-2023-v2` | `57 ARV2_MARKET_CAP_QQQ_R109_2019_2023 - 20260917` / `ARV2 R109 market-cap QQQ 2019-2023 e9851c2f` | `arv2-preliminary-qc-projection-2c9640d0f3922cb4f7267796` / `2c9640d0f3922cb4f7267796d6db57eaba71d236310a62f8947a34d6da62c0ad` | `41a698afa9147ece3a156c7bbf422b1785a7af06007592537a439ae20812ec45` | `9d6fecefdaa6dc007ec10ef1b2f6bfe7d1630c1a00c7b6a3fd66f66d039c18dd` / 8 | `arv2-preliminary-qc-submission-de216f4b8e4cbfe7a27f75f9` / `de216f4b8e4cbfe7a27f75f94d363f0878d1323cb6ae8dea7b37b1ee7739eedc` |
| R-110 | `arv2-market-cap-stock-spy-2019-2023-v2` | `58 ARV2_MARKET_CAP_SPY_R110_2019_2023 - 20260917` / `ARV2 R110 market-cap SPY 2019-2023 e9851c2f` | `arv2-preliminary-qc-projection-a6ae308fe12fccc29e045af8` / `a6ae308fe12fccc29e045af8933d51901ca991ae4773cb726d7b729a7c626b57` | `8971a4f3135506d0b267f4464ef0d9099af44748f95dc06164ed54669718a45e` | `9d6fecefdaa6dc007ec10ef1b2f6bfe7d1630c1a00c7b6a3fd66f66d039c18dd` / 8 | `arv2-preliminary-qc-submission-a5d38b3ee76d6175e4ff7fe7` / `a5d38b3ee76d6175e4ff7fe72102a7963cc0cc954457e0f2e7f5f78d96152033` |
| R-111 | `arv2-market-cap-stock-qqq-2023-2025-v2` | `59 ARV2_MARKET_CAP_QQQ_R111_2023_2025 - 20260917` / `ARV2 R111 market-cap QQQ 2023-2025 e9851c2f` | `arv2-preliminary-qc-projection-0753f411be2df3978b5b57a9` / `0753f411be2df3978b5b57a949e1f459dca56db8368183bcebf91e6bafab391c` | `3e20a45171a31a26877f7a6457d74d0c77d9ef90ab22fe125d2fd95cf4fd68a9` | `9d6fecefdaa6dc007ec10ef1b2f6bfe7d1630c1a00c7b6a3fd66f66d039c18dd` / 8 | `arv2-preliminary-qc-submission-424d9cdedac79722bd81ebb4` / `424d9cdedac79722bd81ebb4be391a64056d086cc20f0ded2bc8df1ae2edd067` |
| R-112 | `arv2-market-cap-stock-spy-2023-2025-v2` | `60 ARV2_MARKET_CAP_SPY_R112_2023_2025 - 20260917` / `ARV2 R112 market-cap SPY 2023-2025 e9851c2f` | `arv2-preliminary-qc-projection-764e182dc5a5a74396e0fae7` / `764e182dc5a5a74396e0fae7cdfd0887b7815ab31ff4d186261506a0a0e34faf` | `40b7de4d536b10bcd167e9d661cb5b5f26b6df2e10cd0585e84058399b22b2bf` | `9d6fecefdaa6dc007ec10ef1b2f6bfe7d1630c1a00c7b6a3fd66f66d039c18dd` / 8 | `arv2-preliminary-qc-submission-2cdb3f970f775ea1a912fe8e` / `2cdb3f970f775ea1a912fe8eff5749969bb12fa4cead76e39c08383e1e4a512b` |
| R-113 | `arv2-objective-synthetic-leverage-qqq-2021-2025-v3` | `61 ARV2_LEVERAGE_QQQ_R113_2021_2025 - 20260917` / `ARV2 R113 synthetic 2x3x QQQ 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-52907f340a720ec888edeb14` / `52907f340a720ec888edeb144a1d5b3e8e0cd95a3910402f3f74d30872aaad6b` | `c4355c7403af700218847381dc7ce49d4cc747b7ea0256df6ab920587be2ade4` | `5650cc7e2eb2a24c2ea9473247d642ecbf4979a7bd1551f60cc18a6a2ec94795` / 8 | `arv2-preliminary-qc-submission-792aa49935732f52ea569b79` / `792aa49935732f52ea569b79f22531e8666fdd2d363ace9a46e1142d3a624dae` |
| R-114 | `arv2-objective-synthetic-leverage-spy-2021-2025-v3` | `62 ARV2_LEVERAGE_SPY_R114_2021_2025 - 20260917` / `ARV2 R114 synthetic 2x3x SPY 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-d632fa55f2944af89dee416e` / `d632fa55f2944af89dee416e0f452e90a7e3ecad2d4644781a0fe7bd1e25322b` | `e1b106a37df7ed176829199ae4a9d8e598997145b0c70a42b545cc88665af9aa` | `5650cc7e2eb2a24c2ea9473247d642ecbf4979a7bd1551f60cc18a6a2ec94795` / 8 | `arv2-preliminary-qc-submission-5c7657556d6e0c80a66933ac` / `5c7657556d6e0c80a66933acfb7a9b254943128c9c16167711d62c18eb7f9c5d` |

Control directories are respectively
`accepted_risk_market_cap_r107_20260917_01` through
`accepted_risk_market_cap_r112_20260917_01`, then
`accepted_risk_leverage_r113_20260917_01` and
`accepted_risk_leverage_r114_20260917_01`, below the private lane artifact
root. R-107 is the mandatory first run; no later run launches unless its
aggregate is tangible. After that gate, the six unlevered runs remain first
and the two synthetic-leverage runs remain last, all sequentially on the one
subscribed node.

Accounting by launch/result is: R-107 **81 -> 82 / 24 -> 25 / 591 -> 595**,
R-108 **82 -> 83 / 25 -> 26 / 595 -> 599**, R-109 **83 -> 84 / 26 -> 27 /
599 -> 603**, R-110 **84 -> 85 / 27 -> 28 / 603 -> 607**, R-111 **85 -> 86 /
28 -> 29 / 607 -> 611**, R-112 **86 -> 87 / 29 -> 30 / 611 -> 615**,
R-113 **87 -> 88 / 30 -> 31 / 615 -> 619**, and R-114 **88 -> 89 / 31 -> 32 /
619 -> 623**, for shared looks / development evaluations / lifetime cell
floor. Infrastructure looks remain **27**. A launch spends its look and
evaluation even on technical failure; cells accrue only after one
authenticated aggregate read. No raw row, identifier, price, log, chart,
holding, order, deployment, broker state, paper/live state, or trading action
is authorized.

## R-107 — QQQ 2021--2025 market-cap diagnostic (AUTHENTICATED; TANGIBLE) — 2026-09-17

Private project `36681064`, backtest
`c21434bbcbca52aa4d7e105e5612892b`, completed after 19 statistics-free
polls. One bounded read authenticated result receipt
`arv2-preliminary-qc-result-58e924566071b88a7f46b704`, SHA-256
`58e924566071b88a7f46b704463221aea869a8df06989321dd2c0173aeb049ff`.
Exactly eight preregistered aggregate statistics were selected; logs, charts,
orders and raw provider rows were not selected.

| Cost per side | Selected cumulative | Matched cumulative | Selected - matched | SPY cumulative | Selected - SPY |
|---:|---:|---:|---:|---:|---:|
| 0 bps | 72.09% | 116.44% | -44.35 pp | 95.67% | -23.58 pp |
| 5 bps | 69.23% | 115.37% | -46.15 pp | 95.67% | -26.44 pp |
| 10 bps | 66.41% | 114.31% | -47.90 pp | 95.67% | -29.25 pp |
| 20 bps | 60.92% | 112.21% | -51.29 pp | 95.67% | -34.74 pp |

At the primary 10-bps cost, selected annualized arithmetic return was 16.34%,
annualized volatility 34.91%, Sharpe 0.468, Sortino 0.659, maximum drawdown
-67.89%, average cash 2.00%, and average daily two-sided turnover 2.683%.
Matched annualized return was 18.12%, volatility 23.64%, Sharpe 0.766,
drawdown -35.34%, cash 2.00%, and daily turnover 0.789%. Costs do not explain
the negative selection gap, and neither does cash.

The profile averaged 82.64 point-in-time eligible names, 82.63 scored names,
and 8.80 selected names. Selected effective breadth averaged only 3.26: the
mean largest position was 48.30% and the observed maximum was 77.68%. Matched
effective breadth was 12.63, with a 16.86% mean largest position and 22.45%
maximum. This is preliminary evidence against the ranking under this exact
market-cap QQQ-proxy construction; it is not a formal disposition, remains
price-proxy conditioned, and QQQ is not all Nasdaq-listed stocks.

The owner's tangible-result prerequisite is satisfied. R-107 moves accounting
to **82 shared looks, 25 development evaluations, 27 infrastructure looks,
and 595 cells**. R-108 is next; the remaining unlevered windows precede both
synthetic-leverage runs. No deployment, broker, order, paper/live, or trading
authority follows.

## R-108 — SPY 2021--2025 market-cap diagnostic (AUTHENTICATED; TANGIBLE) — 2026-09-17

Private project `36682033`, backtest
`df4bc6f06e1e2bee0237c9b8296b502c`, completed after 63 statistics-free
polls. One bounded read authenticated result receipt
`arv2-preliminary-qc-result-e01efc5b388bdb3ccd280c86`, SHA-256
`e01efc5b388bdb3ccd280c8670fc8d7e0c6f1f5ff14f444be3376dc390fbf8ff`.
Exactly eight preregistered aggregate statistics were selected; logs, charts,
orders and raw provider rows were not selected.

| Cost per side | Selected cumulative | Matched cumulative | Selected - matched | SPY cumulative | Selected - SPY |
|---:|---:|---:|---:|---:|---:|
| 0 bps | 113.96% | 90.56% | +23.40 pp | 95.67% | +18.29 pp |
| 5 bps | 111.15% | 89.66% | +21.49 pp | 95.67% | +15.49 pp |
| 10 bps | 108.38% | 88.77% | +19.61 pp | 95.67% | +12.71 pp |
| 20 bps | 102.94% | 87.01% | +15.94 pp | 95.67% | +7.28 pp |

At 10 bps, selected annualized arithmetic return was 17.09%, volatility
21.58%, Sharpe 0.792, Sortino 1.110, drawdown -29.99%, cash 2.00%, and average
daily two-sided turnover 2.111%. Matched return was 14.16%, volatility 16.64%,
Sharpe 0.851, drawdown -24.88%, cash 2.00%, and turnover 0.751%. Selection adds
return across every frozen cost case but does not improve matched Sharpe or
drawdown.

The profile averaged 459.53 point-in-time eligible names, 459.52 scored names,
and 46.52 selected names. Selected effective breadth averaged 10.76, mean
largest position was 24.34%, and maximum position was 41.87%; matched values
were 57.74, 7.21%, and 8.63%. The result is promising preliminary evidence for
the broad SPY-universe construction, not formal acceptance, and remains
price-proxy conditioned.

R-108 moves accounting to **83 shared looks, 26 development evaluations, 27
infrastructure looks, and 599 cells**. R-109 through R-114 stay unlaunched and
unspent. The owner directs a push of this completed round before one common
bounded benchmark-tilt QQQ/SPY implementation. No deployment, broker, order,
paper/live, or trading authority follows.

## R-115 and R-116 — sector-neutral bounded analyst-revision tilt (PREREGISTERED; UNRUN) — 2026-09-18

These exact identities were derived from committed source `18762e5` before
any external action. Common accepted-risk package SHA-256:
`e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9`.
Common host-closure ID / SHA-256:
`arv2-preliminary-qc-host-closure-880f59420a7e544ebb58675a` /
`880f59420a7e544ebb58675ab76ca2a40d975864a082489de91f8233e0d8578c`.
Expected statistic-names SHA-256 / count:
`f59ff651cb2ecaab093da08c9aeb4362197051364aee0b8ae762dc3e5f70745f`
/ 9.

| Run | Profile ID / SHA-256 | Exact private project / backtest | Projection ID / SHA-256 | Source-set SHA-256 | Plan ID / SHA-256 |
|---|---|---|---|---|---|
| R-115 | `arv2-market-cap-stock-qqq-2021-2025-v3` / `9efa7e09241f0f20772260e4e6852bb8a71c46cdc77264cfd10e2b569a4b1b00` | `63 ARV2_BOUNDED_TILT_QQQ_R115_2021_2025 - 20260918` / `ARV2 R115 bounded-tilt QQQ 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-9a0e032ec3ff82f9460cfcbd` / `9a0e032ec3ff82f9460cfcbd2a2405cca6ab526b32c891debc3a08fbc48ac359` | `75ce6368243c08cfb6bce9b4ed43130eeb6947092a41b98bd9918ff082f8a831` | `arv2-preliminary-qc-submission-21e34eaadc8638d8613958b0` / `21e34eaadc8638d8613958b00280d655a022737091b6f759197e1c3696cb58cc` |
| R-116 | `arv2-market-cap-stock-spy-2021-2025-v3` / `8ac07f9fe48d2d6448d4adeb5b2f53c364bad8d4ee3eacd8a23a40a509eb8e38` | `64 ARV2_BOUNDED_TILT_SPY_R116_2021_2025 - 20260918` / `ARV2 R116 bounded-tilt SPY 2021-2025 e9851c2f` | `arv2-preliminary-qc-projection-4eb39a51d842203d91d191de` / `4eb39a51d842203d91d191deb929c396a26a9a03bfc35de0a2b60416f3235516` | `53b226cff014c6533b85f11422af802f4fc2c3b8c065f88aee674b9100b9436f` | `arv2-preliminary-qc-submission-deb002cc0a33890211973d8e` / `deb002cc0a33890211973d8e4d6d36652cba708c5ed3c5aafbcedfc720a482b3` |

Control directories are
`accepted_risk_bounded_tilt_r115_20260918_01` and
`accepted_risk_bounded_tilt_r116_20260918_01` below the private lane artifact
root. R-109 through R-114 are superseded unlaunched and unspent; changed
source/V3 identities named-refuse them before network while their historical
validators remain available.

The matched account is the full point-in-time eligible proxy universe at
market-cap weights and exact frozen 98% gross. The R-055 firm-specific
analyst-revision score is only a bounded overlay, never an admission gate.
Missing/zero score means exact benchmark weight. A tilt requires at least 40
ranked, 20 positive, and 20 negative names; all transfers stay within exact
point-in-time sector. One-way active share is at most 4.9%, each name remains
within 0.8x--1.2x benchmark weight, absolute overweight is at most 0.0049,
and selected HHI is at most 1.44x benchmark HHI. Infeasible breadth or sector
cross-funding yields exact benchmark / `TILT_UNDERFILLED`. Execution does not
redistribute unavailable or stale-locked budget.

Pre-observation diagnostic ranges are mean eligible count **60--110** and
effective breadth **>=8** for R-115, and **350--550** / **>=35** for R-116;
breadth cannot exceed eligible count. Frozen gross is exactly 98%. Executed
gross may differ only through named missing-price sector underfill or
above-target stale-lock exceptions. These are broad diagnostics, not return
predictions. QQQ and SPY are point-in-time holdings proxies, not claims of
official historical index membership; QQQ is not all Nasdaq-listed stocks.

Each aggregate binds benchmark logical ID, total-return normalization,
session-open observation, actual used first/last sessions, **1,254** used
benchmark observations, **1,253** benchmark return intervals, exact Decimal
canonicalization, a raw-observation digest, and a scale-invariant return-path
digest. No raw benchmark price is emitted. The primary comparison is selected
minus matched at 10 bps per side; the full 0/5/10/20-bps ladder, SPY reference,
risk, breadth, bound, provenance, and execution-exception diagnostics are
reported without winner selection.

R-115 must terminally close and its single nine-statistic aggregate read must
authenticate before R-116 launches on the one subscribed node. Accounting is
R-115 **83 -> 84 looks / 26 -> 27 development evaluations / 599 -> 603
cells**, then R-116 **84 -> 85 / 27 -> 28 / 603 -> 607**. Infrastructure
looks remain 27. A launch spends one look/evaluation even on technical
failure; cells accrue only after authenticated result read. No raw rows,
identifiers, prices, returns, logs, charts, holdings, orders, deployment,
broker, paper/live, or trading access is authorized.

## R-115 terminal technical failure; R-116 superseded unspent — 2026-09-18

R-115 launched once in private project `36700291`, backtest
`71335e98ebdc333a7291cc4d8a33033d`, and reached authenticated `Runtime Error`
after 64 statistics-free polls. Terminal receipt
`arv2-preliminary-qc-terminal-0468412659f8dbd15f945f35`, SHA-256
`0468412659f8dbd15f945f3512fa887984aab465f61b99cfeed9374b76b941b3`,
records no selected result value. No result authority, result-read permit,
aggregate, or economic cell exists.

One bounded diagnostic selected only status, error, and stack. The exact
refusal was `benchmark tilt membership mapping is not exhaustive`: the full
cap-eligible point-in-time proxy includes structural-zero names outside the
analyst package's sector-labelled security census. The prospective V4
correction may assign a deterministic reserved sector only to an unmapped
name that also has no R-055 score; that name stays at exact benchmark weight
and cannot transfer weight. Mapped/scored names still require exact sectors,
and scored-but-unmapped names refuse. This changes no observed economic value
because none was emitted.

R-115 moves accounting to **84 shared looks, 27 development evaluations, 27
infrastructure looks, and 599 cells**. R-116 created no project/backtest and
is superseded unspent. Fresh R-117/R-118 successors will move accounting
**84 -> 85 / 27 -> 28 / 599 -> 603**, then **85 -> 86 / 28 -> 29 / 603 ->
607**, if their result reads authenticate. No raw row, identifier, price,
return, statistic, log, chart, holding, order, deployment, broker, paper/live,
or trading access occurred.

The prospective V4 implementation assigns the reserved structural-zero
sector only to an unscored, unmapped eligible name; it preserves that name's
exact benchmark weight and refuses any scored mapping gap. Active V4 profile
SHA-256s are `40626bc6fa7391a0660d93fc553b288d3f1db8c5a1704d784597560a93c44be1`
(QQQ) and `73629240645c04164b81d646ba982b9d8d767ea6d09c1b90e3276291bafa517d`
(SPY). The fresh V4 projection ceiling is 268,000 bytes with at least 4,096
bytes tested headroom; historical V1--V3 projections retain 260,000 bytes.
Independent prelaunch audit accepted the corrected implementation with zero
open findings after one P2 cap-scope correction and two P3 guard-isolation
tests; its final combined rerun was **414 passed**. This records no additional
research look or outcome.

## R-117 and R-118 — corrected sector-neutral bounded tilt (PREREGISTERED; UNRUN) — 2026-09-18

The exact V4 plans were derived from committed correction `bbd146b` before
external action. Common package SHA-256 is
`e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9`;
common host-closure SHA-256 is
`1a49740d46a2e78fcd165ed5bb3b6eeeb7afbbc6195a2f559a9ab4409d0c4cbd`
over 138 sources; expected statistic-names SHA-256 / count is
`f59ff651cb2ecaab093da08c9aeb4362197051364aee0b8ae762dc3e5f70745f`
/ 9.

| Run | Profile SHA-256 | Project / backtest | Projection SHA-256 | Source-set SHA-256 | Plan SHA-256 |
|---|---|---|---|---|---|
| R-117 QQQ | `40626bc6fa7391a0660d93fc553b288d3f1db8c5a1704d784597560a93c44be1` | `65 ARV2_BOUNDED_TILT_QQQ_R117_2021_2025 - 20260918` / `ARV2 R117 bounded-tilt QQQ 2021-2025 e9851c2f` | `9282078935951665f11d4dbb35e1acb3cf483c8c0343d5f21bc7cb0ec17427bb` | `9597182483e25ef95ac1cb3b16de6cd0c1274e39336ae48f7c0b3476364cdde8` | `01c401e5f454590352a066eb4882f601a3be8233dced87be71c05c678f3cdf80` |
| R-118 SPY | `73629240645c04164b81d646ba982b9d8d767ea6d09c1b90e3276291bafa517d` | `66 ARV2_BOUNDED_TILT_SPY_R118_2021_2025 - 20260918` / `ARV2 R118 bounded-tilt SPY 2021-2025 e9851c2f` | `e2ed50ee4a31f1f1569d30d41bdbde7f13b384cd4f161f83ed09b0a0d4f2423a` | `a1eaaa3948d570270516ce2844385f3cf6b66bc0348d619fb5bb9a57a0169057` | `f813898c486e9b70176ab5cdbe6142b28cf6a8b7cd89c20217344b07e8481772` |

Each projection is 259,810 bytes. R-117 must close and authenticate at most
one aggregate read before R-118 launches. Planned accounting is R-117 **84 ->
85 looks / 27 -> 28 development evaluations / 599 -> 603 cells**, then R-118
**85 -> 86 / 28 -> 29 / 603 -> 607**. No outcome has yet been selected.

## R-117 and R-118 — corrected sector-neutral bounded tilt (AUTHENTICATED; TANGIBLE PRELIMINARY) — 2026-09-18

Both preregistered V4 runs reached authenticated terminal `Completed.` and
each consumed exactly one aggregate-only result read selecting the nine
expected custom statistics. No raw provider row, security identifier, price
series, return series, log, chart, holding, or order was selected.

| Run | Private QC identity | Result receipt | 10-bps selected | 10-bps matched | Selected - matched | SPY reference | Selected - SPY |
|---|---|---|---:|---:|---:|---:|---:|
| R-117 QQQ holdings proxy | project `36703035`; backtest `b58922a90d5c361212525375325a119b` | `arv2-preliminary-qc-result-4cf76e6155b6b13bce661a52`; SHA-256 `4cf76e6155b6b13bce661a523a096ddcd2ca753b9c593e37ec2d6415bc580f9c` | +115.3069% | +114.3127% | **+0.9942 pp** | +95.6663% | +19.6405 pp |
| R-118 SPY holdings proxy | project `36704537`; backtest `ee3820c9459206957e6e824e5bfbb597` | `arv2-preliminary-qc-result-2d032398e9155c1a79727e98`; SHA-256 `2d032398e9155c1a79727e98c03534edc269020c6e1fae03169db4583c406704` | +89.5224% | +88.7752% | **+0.7471 pp** | +95.6663% | -6.1440 pp |

R-117 terminal SHA-256 is
`4811287d41a935db0b5e975fba5a20351b1c6fd5509ed7621badca7fe3c23b25`
and its selected-statistics SHA-256 is
`32458947e2b645f124293691f51e4a0d50561423818380219846a62d7f630725`.
R-118 terminal SHA-256 is
`21d91a79580e11f9fa1a10c741e8193b78cd2abf017bc7633367b7f648fad4ed`
and its selected-statistics SHA-256 is
`6c372c160e32119d6b808e7815299ae7291834c7e1c70c18e4fea21ee25de963`.

At 10 basis points per side, R-117 reports 18.2303% annualized arithmetic
return, 23.7224% annualized volatility, 0.7685 zero-rate Sharpe, 1.0880
Sortino, and -35.5455% maximum drawdown. R-118 reports 14.2417%, 16.6788%,
0.8539, 1.2175, and -25.0061%, respectively. Mean cash is approximately 2%
for both; maximum one-way active share is 2.4382% for R-117 and 3.3106% for
R-118.

The bounded overlay added about 0.99 percentage point to its matched
QQQ-holdings proxy and 0.75 percentage point to its matched SPY-holdings proxy
over five years after modeled primary cost. R-117 did not include an actual
QQQ ETF total-return comparator, so its selected-minus-SPY field is not a QQQ
hurdle. R-118 lagged its SPY reference. These are modest, preliminary,
single-window results and do not authorize leverage, paper/live use, or
trading.

The common SPY reference is bound to raw-observation SHA-256
`8c10999f1754960868d7ca201c63fde386aab7a14e5c8ed6015696be01c7fe78`
and return-path SHA-256
`8c9c9296977070c78423bb35f8a3fb5f7538f62892b23d721703757d7b403762`.
Its +95.6663% differs from the earlier +94.2074% data vintage; only comparisons
inside one bound envelope share a basis. R-117 reports two partial rebalance
decisions and 22 stale-mark sessions; R-118 reports five and 47. The recorded
outputs preserve those conservative exceptions rather than hiding them.

R-117 and R-118 close accounting at **86 shared looks, 29 ARV2 development
evaluations, 27 infrastructure looks, and 607 cells**. No deployment, broker,
paper/live, funded-account, or trading authority follows.

## R-119 and R-120 — QQQ bounded-tilt simulated order diagnostics (PREREGISTERED; UNRUN) — 2026-09-18

No external action or outcome access occurred before this entry. Both physical
identities were reconstructed from committed implementation `9dc044a`. Common
delta package ID / SHA-256 / lineage SHA-256:
`arv2-preliminary-qc-package-7803b84f0841f9685a4951de` /
`7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f` /
`54723703380d5011420d8a364cf857a9978092b6b1d0daaa4d367dc1c65fb129`.
Expected aggregate-statistic inventory SHA-256 / count:
`c504e1cba05dd9c4dccae7e8d47eeb26839637c03b27da6f1c352d5912174d37`
/ 2.

| Run | Profile ID / SHA-256 | Exact private project / backtest | Projection ID / SHA-256; source SHA-256 | Plan ID / SHA-256; execution-authority candidate SHA-256 |
|---|---|---|---|---|
| R-119 | `arv2-qqq-order-level-tilt-2026-cutoff-v1` / `f2418eafc7777a6a814d8c73fd4563f5e552aa3c9cc1f2fa8b1cd98a338c5a7f` | `67 ARV2_QQQ_ORDER_R119_2026_YTD - 20260918` / `ARV2 R119 QQQ order-level 2026 YTD 7803b84f` | `arv2-order-level-qc-projection-6774b3c7f8394a68e46c86e2` / `6774b3c7f8394a68e46c86e207a5e74f533f981b09d3dfd6ee0562bb72d6d024`; `c4cb758f4943df06dd2284276d59a3049b7ca3663c866fc52b1d0834e2fe39e4` | `arv2-order-level-plan-b0e00b70cb866c4a858b2eef` / `b0e00b70cb866c4a858b2eefb901f5d25b327e81cd80904e89dac1a3229e7287`; `6d3b5922fcd5074550fbeb4fe869d08882bc640ef621ef4e72b8aba9a92a79f9` |
| R-120 | `arv2-qqq-order-level-tilt-2025-cutoff-v1` / `8a2d1ffbcf2fc6bd7a85931f390e58e77feac1bf26b9b840ba9cd727439df2b1` | `68 ARV2_QQQ_ORDER_R120_2025_NOW - 20260918` / `ARV2 R120 QQQ order-level 2025-now 7803b84f` | `arv2-order-level-qc-projection-ba032031df5c1e611961253f` / `ba032031df5c1e611961253f6c98a5250e1306a04f0b321938732c4fee2e6336`; `b4f84254bc609372145d58418450cfa3b93981e8df3a18bc08a3fff9d9284707` | `arv2-order-level-plan-344657ab3d9d871868405d91` / `344657ab3d9d871868405d9143ca9e23989e2dac120c3f08afb67b13aff6bcbc`; `99058ce096accd2ffcc60876686bf67df5088220e363b419cfde90427392b88b` |

R-119 freezes 2026-01-02 through 2026-09-17, with first simulated
market-on-open execution on 2026-01-05, 39 weekly decisions, 178 observations,
and 177 return intervals. R-120 freezes 2025-01-02 through 2026-09-17, with
first execution on 2025-01-03, 91 decisions, 428 observations, and 427
intervals. Both stop new decisions on 2026-09-16. The selected account is the
QQQ point-in-time holdings proxy plus the unchanged bounded sector-neutral
R-055 tilt; its primary hurdle is an execution-matched 98%-QQQ / 2%-cash
account entering at the same first open. Both use RAW prices, whole-share
market-on-open simulation, exact QC fees, zero slippage, and the frozen
10-basis-point-per-side modeled-cost check. No expected sign or winner was
selected.

R-119 launch moves accounting **86 -> 87 shared looks / 29 -> 30 development
evaluations**, and an authenticated aggregate adds one cell **607 -> 608**.
R-120 is sequential and, only on that authenticated baseline, moves **87 ->
88 / 30 -> 31 / 608 -> 609**. Infrastructure looks remain 27. A technical
failure still spends its look/evaluation and adds no cell; missing R-119 cell
requires a fresh successor accounting entry before R-120. No raw provider or
security row, raw order/fill, holding, price, return, log, chart, standard
statistic, deployment, broker, paper/live, funded-account, or real-trading
access is authorized.

## R-119 — QQQ bounded-tilt 2026 simulated-order diagnostic (TERMINAL TECHNICAL FAILURE; ZERO CELLS) — 2026-09-18

R-119 created private project `36714332` and backtest
`d025d903f859e4825e657d8cbb268d3f`, then reached authenticated `Runtime
Error` on its first statistics-free status poll. Terminal receipt
`arv2-order-level-terminal-7b5ef3f33095183afc1c489a`, SHA-256
`7b5ef3f33095183afc1c489acd6bfa29d6b4b58e1dbb92358e81cc347e341baa`,
contains no statistic. No result-read authority or result read exists.

A separately bounded diagnostic selected only terminal status and error/stack
fields. It read no statistic, chart, order, fill, holding, price, return, or
provider/security row. The error was `order-level PIT fundamentals collection
is outside the authenticated session axis` on the first 2026-01-02 decision:
a legitimate 2026-01-01 holiday fundamental-availability collection was not
itself an exchange-session key. This is a technical refusal before simulated
orders or economic output, not positive or negative strategy evidence.

R-119 spends **86 -> 87 shared looks** and **29 -> 30 ARV2 development
evaluations** but adds zero cells, leaving **607 cells** and 27 infrastructure
looks. R-120 created no project or backtest and is superseded unlaunched and
unspent because its fixed 608-cell baseline and source identities are no
longer true. The correction permits non-session availability mapping only for
fundamentals, retains exact-session constituent evidence, and also closes the
same latent defect in the unrun six-universe runtime. Fresh R-121/R-122 order
successors require new committed identities and accounting; the unpreregistered
six-universe pair moves to R-123/R-124.

## R-121 and R-122 — corrected QQQ bounded-tilt simulated order diagnostics (PREREGISTERED; UNRUN) — 2026-09-18

These successors were derived from committed correction `0baa9f9` before any
external action. Common package SHA-256 / lineage SHA-256:
`7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f` /
`54723703380d5011420d8a364cf857a9978092b6b1d0daaa4d367dc1c65fb129`.
Expected two-statistic inventory SHA-256:
`c504e1cba05dd9c4dccae7e8d47eeb26839637c03b27da6f1c352d5912174d37`.

| Run | Profile SHA-256 | Exact private project / backtest | Projection SHA-256; source inventory SHA-256 | Plan SHA-256; execution-authority candidate SHA-256 |
|---|---|---|---|---|
| R-121 | `f2418eafc7777a6a814d8c73fd4563f5e552aa3c9cc1f2fa8b1cd98a338c5a7f` | `69 ARV2_QQQ_ORDER_R121_2026_YTD - 20260918` / `ARV2 R121 QQQ order-level 2026 YTD 7803b84f` | `8de56ffcd17937b35d5fdaa3d3ae2521082e6ad506eac75c4b67cf7cdf40c6ef`; `82adba43422f4df78c7a53e52964f473ba10d1734715ff807993543dd9f48189` | `fa14e323fca96b51a42c4df65d2201699a117620c8a395078104bd8f8b87019a`; `ff4261a648e05980d7b64f005e54b8854a13094a0caee9339555a78e07fb1f8f` |
| R-122 | `8a2d1ffbcf2fc6bd7a85931f390e58e77feac1bf26b9b840ba9cd727439df2b1` | `70 ARV2_QQQ_ORDER_R122_2025_NOW - 20260918` / `ARV2 R122 QQQ order-level 2025-now 7803b84f` | `58eff6df2808f9eaed1b1f7564828f970c9c180bd258b66913126f7ebeb8fe03`; `34787c0f167b955679d50c2d3fd7e09c6246d1b13ead6b5e43b0d515ea80ab98` | `cb9c26389c563fab942d6764b56a646ca3537bfcf3c2a71349f40ba67d8fb5df`; `2ace00bb95cf12b89014c6e4d9398a7184077d8e0befc87604e215f7331e3a12` |

R-121 uses the 2026-01-02 through 2026-09-17 window; R-122 uses
2025-01-02 through 2026-09-17. Both preserve the section-111 QQQ PIT proxy,
bounded sector-neutral R-055 tilt, weekly after-close decision, next-session
whole-share market-on-open simulation, RAW prices, exact engine fees, zero
slippage, 10-basis-point modeled-cost check, 98% target gross, and
execution-matched QQQ hurdle. No expected sign or winner was selected.

Starting accounting is **87 shared looks, 30 ARV2 development evaluations, 27
infrastructure looks, and 607 cells**. R-121 launch moves to **88 / 31** and
an authenticated aggregate to 608 cells. Only then may R-122 launch, moving to
**89 / 32**, with its authenticated aggregate moving to 609 cells. A technical
failure adds no cell and requires fresh successor accounting. No raw result,
order/fill, or paper/live/trading access is authorized.

## R-121 — corrected QQQ 2026 simulated-order diagnostic (TERMINAL COVERAGE REFUSAL; ZERO CELLS) — 2026-09-18

R-121 created private project `36714714` and backtest
`72cdee2ca23378f8f36bbaae9df739d3`, then reached authenticated `Runtime
Error` on its first statistics-free poll. Terminal receipt
`arv2-order-level-terminal-6d0fe804193067cb7a05d5fd`, SHA-256
`6d0fe804193067cb7a05d5fd9be77a7735bb4dd1ba14e3df37ba7410b708f652`,
contains no statistic. No result-read authority or result read exists.

A bounded diagnostic selected only terminal status and error/stack fields.
The exact refusal was `order-level PIT QQQ market-cap constituent-weight
coverage is below 99 percent` on 2026-01-02. It occurred before any simulated
order or economic output and is not strategy evidence. R-121 spends **87 ->
88 shared looks / 30 -> 31 development evaluations**, adds zero cells, and
leaves **607 cells / 27 infrastructure looks**. R-122 created no project or
backtest and is superseded unlaunched/unspent.

The prospective successor versions the profile and lowers this outcome-free
data-admission floor to 95%, while retaining exact achieved coverage and its
path digest in the authenticated aggregate; below 95% still refuses. Covered
market caps renormalize to 98% gross, so the result remains an accepted-risk
QQQ proxy rather than pristine QQQ replication. Fresh
R-123/R-124 order runs require committed identities and accounting. The
unpreregistered six-universe pair moves to R-125/R-126.

## R-123 and R-124 — versioned 95%-coverage QQQ simulated-order diagnostics (PREREGISTERED; UNRUN) — 2026-09-18

The V2-profile / V4-summary source was committed at `70b8e65` before physical
identity derivation. Both runs use immutable package SHA-256
`7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f`
and expected two-statistic inventory SHA-256
`c504e1cba05dd9c4dccae7e8d47eeb26839637c03b27da6f1c352d5912174d37`.

| Run | Profile SHA-256 | Exact private project / backtest | Projection SHA-256; source inventory SHA-256 | Plan SHA-256; execution-authority candidate SHA-256 |
|---|---|---|---|---|
| R-123 | `e79316b50d9a53f04418d971357278bca2dd5db43eea33e28da25cda785163dc` | `71 ARV2_QQQ_ORDER_R123_2026_YTD - 20260918` / `ARV2 R123 QQQ order-level 2026 YTD 7803b84f` | `5b131125e51007be32e2bd4d6adf52fe8ed277bcb07dd2cfdc7f2386cfb92b92`; `80aca057fcdfc3e0a5167cb311a29afd5895698708227da8c0f876f0950a8035` | `88bddb88428a50e221bfa527899fb7386256b4c33fef77d29252928bc4b42067`; `bed1fedd6eb1b61790bd6554b53b20c818b5b817df9f896748b6f58a848e4ea6` |
| R-124 | `6d4b7c4fe50ca93a32fcdd113a3fcba607897f0e83e00c073f0fc0c9198826e8` | `72 ARV2_QQQ_ORDER_R124_2025_NOW - 20260918` / `ARV2 R124 QQQ order-level 2025-now 7803b84f` | `cf307d99646612ab3c443aac04a8ff610a2a331aa705359e7ac63110e2b16b00`; `f3ba0611d11b00f9c48dd5bf6dc0f698e2a179c11095d2f8d02daa117dfaa3a6` | `2e7906f9a17b1ad1f815574116c983af112df3597269efa10fabe68dd2a23a00`; `a7550739c93ecf4c742ddf12a242922098fefeab4f85118a80f438b6504db120` |

R-123 covers 2026-01-02 through 2026-09-17. R-124 covers 2025-01-02
through 2026-09-17 and is strictly sequential. The frozen 95%-coverage rule
excludes uncovered names, discloses exact missing weight and path digest, and
renormalizes covered market caps to 98% gross; these are accepted-risk QQQ
proxies rather than pristine QQQ replication. No expected sign or winner was
selected.

Starting accounting is **88 shared looks, 31 ARV2 development evaluations, 27
infrastructure looks, and 607 cells**. R-123 launch moves to **89 / 32** and an
authenticated aggregate to 608 cells. Only then may R-124 launch, moving to
**90 / 33**, with its aggregate moving to 609 cells. A technical failure adds
no cell and requires a fresh successor. No raw result, order/fill, or
paper/live/trading access is authorized.

## R-123 — versioned 95%-coverage QQQ simulated-order diagnostic (TERMINAL COVERAGE REFUSAL; ZERO CELLS) — 2026-09-18

R-123 created private project `36714951` and backtest
`7fb5cfba0fdb6ebe27c3a71376c239e6`, then reached `Runtime Error` on its
first statistics-free status poll. Terminal receipt
`arv2-order-level-terminal-4b202bb06eabfb5e7689957a`, SHA-256
`4b202bb06eabfb5e7689957a51e15719cbc3b31491991340d2608725cc16f3ae`,
contains no statistic. No aggregate read or result-read authority exists. A
bounded diagnostic selected only status/error/stack; no statistic, chart,
order, fill, holding, price, return, or provider/security row was selected.

The exact refusal was `order-level PIT QQQ market-cap constituent-weight
coverage is below 95 percent` on 2026-01-02. The achieved ratio was not
exposed by the failed V2 profile. No simulated order or economic output
occurred; it is not signal evidence. R-123 spends **88 -> 89 shared looks / 31
-> 32 development evaluations**, adds zero cells, and leaves **607 cells / 27
infrastructure looks**. R-124 created no project or backtest and is
superseded unlaunched/unspent.

A prospective V3-profile/V5-summary successor sets a 90% cap-covered QQQ
weight floor with exact ratio on refusal; below 90% still refuses. Above it,
uncovered names are excluded and covered caps renormalize to 98% gross. This
remains an accepted-risk QQQ proxy rather than pristine QQQ replication: 90%
is relative to reported positive constituent weight, which can be 95% of
notional, so absolute covered weight may be as low as **85.5%**. This is a
preliminary diagnostic, not a formal or live-ready coverage claim.
Fresh R-125/R-126 order runs require committed identities and accounting; the
unpreregistered six-universe pair moves to R-127/R-128.

## R-125 and R-126 — 90%-coverage QQQ simulated-order diagnostics (PREREGISTERED; UNRUN) — 2026-09-18

The V3/V5 order source was committed at `91a5240` before physical derivation.
Common immutable package SHA-256:
`7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f`;
expected two-statistic inventory SHA-256:
`c504e1cba05dd9c4dccae7e8d47eeb26839637c03b27da6f1c352d5912174d37`.

| Run | Profile SHA-256 | Exact private project / backtest | Projection SHA-256; source inventory SHA-256 | Plan SHA-256; execution-authority candidate SHA-256 |
|---|---|---|---|---|
| R-125 | `6348a47e0fd8806dc5222b98f9ff7923e357adc46ae7c0a6a92e4efed1643158` | `73 ARV2_QQQ_ORDER_R125_2026_YTD - 20260918` / `ARV2 R125 QQQ order-level 2026 YTD 7803b84f` | `46d6e1789a7269ed0c4e9ac6ba4d7399ddff6e64f8e6a2cf39e0b111c7ab713c`; `19579eada5b8322af74f996436df0b79919d489613144c9e69689b7f019aa2ae` | `ddc6f0d070e8ad4f8d8e3934e253984a7263ee252732214eedf99846d5ea75f3`; `3ed7651579b06a4080dfe967c04768677aa9c91f30053299b5871c7a12280b85` |
| R-126 | `564aa98ce9b78fa582a1ca586f03c8a78fee927da6e8b167e55512908209a79d` | `74 ARV2_QQQ_ORDER_R126_2025_NOW - 20260918` / `ARV2 R126 QQQ order-level 2025-now 7803b84f` | `0c4b83ecb7761954f922448f0c5a464ca4bb2e72bf7cbbd57b72a57f75d18628`; `ca19a8a6c5f9d5613250dc6578fdf2dffa8865071eacbc8fc2a4525219a352f2` | `ea5c4a9c6d5e2863bfaf6806d9bdfd6de68edd7dae92ec5d470b1f5e763912b1`; `79cc0c486b3b0bdf2ff59f86cd9cf7cbe060fb9b2909e2fc654a34d02bca2e22` |

R-125 covers 2026-01-02 through 2026-09-17. R-126 covers 2025-01-02
through 2026-09-17 and is strictly sequential. The frozen 90% floor is of
reported positive constituent weight, so absolute covered notional can be
85.5%; this is an exploratory QQQ holdings proxy, not pristine QQQ. Exact
coverage and path digest remain aggregate fields; a sub-90% refusal now
includes the exact ratio. No result sign or winner was selected.

Starting accounting is **89 shared looks, 32 ARV2 development evaluations,
27 infrastructure looks, and 607 cells**. R-125 launch moves to **90 / 33**
and an authenticated aggregate to 608 cells. Only then may R-126 launch,
moving to **91 / 34**, with an authenticated aggregate to 609 cells. A
technical failure adds no cell and requires a fresh successor.

## R-125 — 90%-coverage QQQ simulated-order diagnostic (TERMINAL MEASURED COVERAGE REFUSAL; ZERO CELLS) — 2026-09-18

R-125 created private project `36715111` and backtest
`322314199b7a45edb3c95a8dbda05f95`, then reached `Runtime Error` on the
first statistics-free status poll. Terminal receipt
`arv2-order-level-terminal-8f75c54c8ef367cb15c2370f`, SHA-256
`8f75c54c8ef367cb15c2370fcf01e0113e793ece2db8e873834ae29a55ac98e0`,
contains no statistic. A bounded diagnostic selected only status/error/stack;
no provider/security row, statistic, chart, order, fill, holding, price, or
return was read. The first 2026-01-02 decision refused because exact cap-
covered QQQ reported weight was **0.8592140785921407859214078592**, below
the frozen 90% floor. No simulated order or economic output occurred. This
measures missing cap-join coverage, not signal performance.

R-125 spends **89 -> 90 shared looks / 32 -> 33 development evaluations**,
adds zero cells, and leaves **607 cells / 27 infrastructure looks**. R-126
created no project/backtest and is superseded unlaunched/unspent. The cap-
weighted proxy will not lower its floor again blindly. A separate,
prospectively versioned ETF-holdings-weight core plus bounded revision tilt
would be a new economic construction with its own look/accounting; any such
result remains preliminary because of current-snapshot FIGI identity and
reported-weight coverage. Fresh order numbers R-127/R-128, six-universe
numbers R-129/R-130, remain unpreregistered.

## Separate V4 QQQ PIT ETF-weight order candidate (IMPLEMENTED; NOT YET PREREGISTERED OR RUN) — 2026-09-18

R-125's 85.9214% cap-join coverage stopped the market-cap QQQ proxy; no
further cap-floor reduction follows. V4 is a different economic construction:
the QQQ ETF's own strictly prior, point-in-time positive constituent weights
form the 98%-gross benchmark core, with the same bounded sector-neutral
analyst-revision tilt. It omits the fundamental market-cap history call and
requires at least 95% FIGI-resolved weight out of the reported positive
total, which itself may be 95% of notional. Its minimum absolute resolved
notional is therefore 90.25%, with uncovered weight excluded and the rest
renormalized. This is preliminary accepted-risk evidence, not a pristine QQQ
or live-ready result. A per-decision full-weight-map digest and a distinct
aggregate path digest bind future data-vintage comparisons. The V4 profile
and V6 aggregate schemas, strict-prior and 95%-coverage tests, and exact
parser guard are implemented; no V4 outcome exists yet. Fresh R-127/R-128
one-use physical identities must be committed before any QC action.

## R-127 and R-128 — PIT QQQ ETF-weight simulated-order diagnostics (PREREGISTERED; UNRUN) — 2026-09-18

The separate V4/V6 source was committed at `f86fe44` before physical
derivation. Common immutable package SHA-256:
`7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f`;
exact two-statistic inventory SHA-256:
`c504e1cba05dd9c4dccae7e8d47eeb26839637c03b27da6f1c352d5912174d37`.

| Run | Profile SHA-256 | Exact private project / backtest | Projection SHA-256; source inventory SHA-256 | Plan SHA-256; execution-authority candidate SHA-256 |
|---|---|---|---|---|
| R-127 | `190637eb9145c4b3a9e844cb42eb84d24bb5b318afc56957f98bf9d413d8a3b6` | `75 ARV2_QQQ_ETF_WEIGHT_ORDER_R127_2026_YTD - 20260918` / `ARV2 R127 QQQ ETF-weight order 2026 YTD 7803b84f` | `697cfb357e9d87cad322d4eaa94f2ffd00a93d2490e899cf2a9eb5c6a382a734`; `d1b14807f0598922d880824eb8d6c0397ed247e72278dc2bf661278a7fe12634` | `187d2f1fa9746560f4d7b0a7b8a8ecff971d9bc22e03d31a0a84bc8eca50c61d`; `644c1f2ef219feb88ee3a10fd3b7d405e5c823b1a235c3ab908ffb5f54e9d673` |
| R-128 | `43ea09abd2b6eb9aef23cfb05ec7cb0c19c50451fb41ac78c3aeeac8bd60e518` | `76 ARV2_QQQ_ETF_WEIGHT_ORDER_R128_2025_NOW - 20260918` / `ARV2 R128 QQQ ETF-weight order 2025-now 7803b84f` | `42d9ec0e68f44b58f7bbf7e9f92daa43adf29f43812fdd2dc661dbe9b3b73628`; `bcca83e45bf7d304ff12a71ed58375b0a03d6a4e266eb31aea21d840fee8bd3b` | `ea2ba2877aa4aefa3f5bc16d9c8e7e24136b128078ad94b85a529d7d6a12df70`; `7cb305b18b1931cacbf3fa5e0446e4709f72d00f1f17054b82e66a395a2a873e` |

R-127 covers 2026-01-02 through 2026-09-17; R-128 covers 2025-01-02
through 2026-09-17. Both retain the bounded revision tilt, 98%-gross core,
whole-share simulated next-open execution, 10-basis-point fee check, and
execution-matched QQQ hurdle, but use point-in-time ETF holdings weights
rather than missing market caps. Minimum FIGI-resolved reported weight is
95%, so absolute resolved notional can be 90.25% at the minimum reported
total. No expected sign or winner was selected. This is a separate
preliminary economic construction, not a retry of R-125.

Starting accounting: **90 shared looks, 33 ARV2 development evaluations, 27
infrastructure looks, 607 cells**. R-127 launch spends **90 -> 91 / 33 -> 34**
and only one authenticated aggregate adds **607 -> 608 cells**. Only then may
R-128 launch, spending **91 -> 92 / 34 -> 35**, with its aggregate adding
**608 -> 609 cells**. A technical failure adds no cell and requires fresh
accounting. No raw row, order/fill, or paper/live/trading access is authorized.

## R-127 — PIT QQQ ETF-weight order diagnostic (TERMINAL IDENTITY-COVERAGE REFUSAL; ZERO CELLS) — 2026-09-18

R-127 created private project `36715522` and backtest
`6f06b0abd1dda90f813fd85ec2161dd6`; the first statistics-free status poll
returned `Runtime Error`. Terminal receipt
`arv2-order-level-terminal-9f57dc2ed110f41bd021edf2`, SHA-256
`9f57dc2ed110f41bd021edf2b18dbf0f7ad6ab497c3565276b8e0ac87328fac5`,
contains no statistic. A bounded diagnostic selected status/error/stack only;
no provider/security row, aggregate, chart, order, fill, holding, price, or
return was read. The first 2026-01-02 decision refused because the exact
FIGI-resolved QC SID coverage of reported positive QQQ weight was
`0.8618138186181381861813818618`, below the prospectively frozen 95% floor.
The reported positive weight total had passed its 0.95--1.05 check. No
simulated order or economic result occurred. **86.1814% is an identity-join
coverage ratio, not a backtest return or an alpha estimate.**

R-127 spends **90 -> 91 shared looks / 33 -> 34 development evaluations**,
adds zero cells, and leaves **607 cells / 27 infrastructure looks**. R-128
created no project/backtest and is superseded unlaunched/unspent. No subsequent
six-universe diagnostic is preregistered. A read-only audit found no proven
implementation defect; the aggregate cannot partition the missing 13.8186%
weight among absent admission, named FIGI refusal, and SID mismatch. R-125's
earlier cap join was only 0.2600 percentage points lower on the same decision.
Do not weaken the spent R-127 guard or call an unrun successor a return. Any
neutral-QQQ residual proxy or mapping census is a separately versioned,
prospectively committed and authorized diagnostic.

## V5/V7 neutral-QQQ residual simulated-order candidate (IMPLEMENTED; UNRUN) — 2026-09-18

The next prospectively versioned construction holds exactly resolved QQQ
constituent stocks at their reported immediately prior ETF weights and puts
all unjoined reported weight into one unscored QQQ ETF position. Positive
reported total remains 0.95--1.05 and exactly resolved stocks must represent
at least 80% of that total; below the floor the run refuses with the exact
ratio. The full reported weight is normalized to 98% gross. Only exactly
resolved stocks can receive the unchanged bounded sector-neutral analyst
revision tilt. This is an economically distinct proxy, **not a rerun of
R-127** or exact QQQ replication: QQQ overlaps the stock holdings, so a
portfolio-minus-QQQ difference cannot isolate analyst signal alpha.

2026 profile SHA-256 `af5e102c5dcd62878eb1046ac63f259e6c4cddf9944cd09c6a5826144a8a914a`;
2025 profile SHA-256 `c3faf484e37d312de849589668b76ea68fa80b48413eb01e636f7e1a4170c86d`.
V7 separately authenticates residual-weight ratios, path digests, overlap
disclosure, simulated order/fee lifecycle, and exact aggregate field inventory.
The local focused/import-boundary battery passed 221 tests, the independent
audit passed 210, and the projected ten-file source fits its per-file and
fixed-closure limits. No QC run or economic cell exists under V5 yet. Starting
accounting remains **91 shared looks, 34 development evaluations, 27
infrastructure looks, 607 cells**. Fresh R-129/R-130 project/plan/authority
identities must be committed before a launch; R-130 depends on R-129's first
authenticated aggregate cell. Six-universe work remains unpreregistered.

## R-129 and R-130 — prospectively frozen QQQ residual-proxy simulated-order runs (UNLAUNCHED) — 2026-09-18

The separate V5/V7 source was committed at `9e2dff1` before either physical
identity was derived. Immutable input-package SHA-256
`7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f`;
two-statistic inventory SHA-256
`c504e1cba05dd9c4dccae7e8d47eeb26839637c03b27da6f1c352d5912174d37`.
Both exact projections have ten files and 273,393 bytes. Neither has a
preselected sign or winner; their QQQ ETF residual overlaps mapped stocks.

| Run | Profile SHA-256 | Exact private project / backtest | Projection SHA-256; source-inventory SHA-256 | Plan SHA-256; unsigned execution-authority SHA-256 |
|---|---|---|---|---|
| R-129 | `af5e102c5dcd62878eb1046ac63f259e6c4cddf9944cd09c6a5826144a8a914a` | `77 ARV2_QQQ_RESIDUAL_ORDER_R129_2026_YTD - 20260918` / `ARV2 R129 QQQ residual order 2026 YTD 7803b84f` | `628abd19f0aa86b1e9d34583cfde670d10199604196166e7079db826b547f824`; `400c90c56c2ff85fd62ca7de7541887df6ecb6331a4b4564e8a438a480c51306` | `53fd49e6fb52bdf7ca18d0bcfd413ce16a6df0a330045dab8771d51234237cd0`; `afd1f5985b535be1fe1ab5dbf153e69776ab0ba27891b07fa061ae025ba3f6df` |
| R-130 | `c3faf484e37d312de849589668b76ea68fa80b48413eb01e636f7e1a4170c86d` | `78 ARV2_QQQ_RESIDUAL_ORDER_R130_2025_NOW - 20260918` / `ARV2 R130 QQQ residual order 2025-now 7803b84f` | `6c55f86c9d1d560790244b5e07c3b403d3063f11717566cd6aabc26c200fa235`; `84017d5273c370373d0e3962ef957ba762db229bbaf4ecd397c0fce44e40e3c5` | `b7642655b48481a7692166a829cc7a3286efb832b1a3e8f0caf5c329e51978c6`; `545ef39d4aa9795ebf2ea1f2660ad2ec4539c584b58ff6d7e7d813b2fc454e99` |

R-129 spans 2026-01-02--2026-09-17; R-130 spans
2025-01-02--2026-09-17. Starting accounting is **91 shared looks, 34
development evaluations, 27 infrastructure looks, 607 cells**. R-129
launch spends **91 -> 92 / 34 -> 35** and only its authenticated aggregate
adds **607 -> 608 cells**. Only then may R-130 launch, spending
**92 -> 93 / 35 -> 36** and adding at most one authenticated cell. A
technical failure adds zero cells and invalidates R-130's fixed accounting.
No six-universe look is preregistered.

## R-129 — QQQ residual-proxy simulated-order diagnostic (TERMINAL ORDER-EVENT REFUSAL; ZERO CELLS) — 2026-09-18

The prospectively frozen source at `920a4e7` passed the complete Analyst V2
suite (6,497 passed, 8 skipped). One signed submission created private QC
project `36718112`, compile
`5fbb4de8a1a22fa36b101a68aeb43acd-6d8adeeb3b32a64b7a9e8be7068e946a`,
and backtest `20a204b3921f9ddb20cd34b2bf99d03f`. The first
statistics-disabled poll authenticated `Runtime Error`; terminal receipt
`arv2-order-level-terminal-7c406102639c92d9b9382f85`, SHA-256
`7c406102639c92d9b9382f853692dfd1c5a92f53b69860474281d3e575242195`.
A bounded technical diagnostic selected only status/error/stack and found
`order-level event references an unknown QC order` at the first Friday
after-close decision (2026-01-02 16:00). A callback could occur before the
MOO call returns its ticket and registers its ID; the existing tests did not
cover that reentrancy. The diagnostic does not show the event status or why
QC sent it. There was no aggregate, return, fill, price, or alpha cell.

R-129 spends **91 -> 92 shared looks / 34 -> 35 ARV2 development
evaluations**, adds **zero** cells, and leaves **607 cells / 27
infrastructure looks**. R-130 is superseded unlaunched/unspent; its fixed
starting accounting and first-cell contingency no longer hold. A new source
version and separately preregistered run must correct/test the order-event
race and validate next-session MOO timing. Do not retry R-129 or interpret
its terminal failure as evidence for or against analyst revisions.

## R-131 and R-132 — V6 preopen QQQ residual-proxy order diagnostics (PREREGISTERED; UNLAUNCHED) — 2026-09-18

The corrected V6 source was committed at `5a430a9` before physical plan
derivation. Its distinct stock-plus-unjoined-QQQ ETF proxy keeps the R-129
80% identity-coverage floor, unchanged bounded analyst-revision tilt,
98%-gross target and 10-bps-per-side modeled fee. It buffers synchronous
order callbacks until exact ticket identity is known, then submits the
frozen prior-close plan on the authenticated next session no later than
09:27 New York time. QQQ extended-hours minute bars advance the backtest
preopen clock; a late callback still refuses. This is a new source and
numbered run, not a rerun of R-129. Input package SHA-256 remains
`7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f`.

| Run | Profile SHA-256 | Exact private project / backtest | Projection SHA-256; source inventory SHA-256 | Plan SHA-256; unsigned execution-authority SHA-256 |
|---|---|---|---|---|
| R-131 | `9d80f749ee84114397054d2305d316564d741179c36738dfcb300a7230569135` | `79 ARV2_QQQ_PREOPEN_ORDER_R131_2026_YTD - 20260918` / `ARV2 R131 QQQ preopen order 2026 YTD 7803b84f` | `4f06f82cf4bc44163700c8df561e8b3cc1e48eb50042842d5ed1cb9dcae89266`; `898c39efc8f14ec803e2249c5dd1d6d5257b4199971ba3b627634a47853eafa9` | `4c11ea59741bca071a00b3377e1edd769eaf1fb899ef4575d8fcd23e23be350b`; `a10010fcb002a1baa58955e92cf9aa281267fa640c389d6d71be28b382eca818` |
| R-132 (contingent) | `f2f3afb724dee0de0143e1d8432cd75ae86609669f8fb10d86427139d28b57c1` | `80 ARV2_QQQ_PREOPEN_ORDER_R132_2025_NOW - 20260918` / `ARV2 R132 QQQ preopen order 2025-now 7803b84f` | `915258fd6daca4b7fdad7875dfe2bad7f0397e000f01db874d2d953aed9b5ebb`; `6dbf89009a40470e75ed5076410a4c0256a62595fc32d9e28709ec10d2e1bc61` | `9077315f43518cecc9e3e6ef8116e61c6d87966dca8e0c6def1f7450ed6e9aa8`; `0edda2bdbb8684d82fff3ffa89de2122c0187fc04f93b20f7dffec9b3645332c` |

R-131 covers 2026-01-02 through the 2026-09-17 final execution date;
R-132 covers 2025-01-02 through that same final session. Starting
accounting: **92 shared looks, 35 ARV2 development evaluations, 27
infrastructure looks, 607 cells**. R-131 launch spends **92 -> 93 / 35 ->
36**, and only a separate one-time authenticated aggregate adds **607 ->
608 cells**. R-132 may launch only after that cell, spending **93 -> 94 /
36 -> 37** and adding at most one cell. If R-131 refuses technically,
R-132 stays unlaunched and unspent. Neither a result sign nor a winner is
chosen in advance; no six-universe, leverage, paper/live, funded, broker,
deployment, or trading authority follows. No QC operation has yet occurred
for either new run.

## R-131 — preopen QQQ residual-proxy simulated-order diagnostic (TERMINAL STATUS-NORMALIZATION REFUSAL; ZERO CELLS) — 2026-09-18

The signed, prospectively frozen R-131 plan created private QC project
`36718956` and backtest `1ff7bfae8aea579e3176652e26041891` from the
V6 source committed at `5a430a9`; the launch receipt SHA-256 is
`f4f5232f06c921ae7c67339a57debb84709bb1494b22f82371726707875c7fb6`.
The first statistics-disabled poll authenticated terminal `Runtime Error`,
receipt SHA-256
`272c5a48c4ce95cc0940d21fc326b411ba83d0ec7d9a8fa751f96ca18475f9a7`.
One bounded exact-run diagnostic selected only status/error/stack. At
`2026-01-05 09:20:00` simulated time, replay of an event emitted synchronously
during MOO submission refused: `order-level QC event status is unsupported`.
No aggregate statistic, raw order/fill/log, provider/security row, price,
return, or alpha cell was read. QuantConnect documentation establishes that
Python may stringify its order-status enum numerically, but the specific
event value was not selected; this is a strongly supported diagnosis, not
an observed-status claim.

R-131 spends **92 -> 93 shared looks / 35 -> 36 ARV2 development
evaluations** and adds **zero cells**, leaving **607 cells / 27
infrastructure looks**. R-132 is superseded unlaunched/unspent because its
authenticated-first-cell contingency and fixed starting accounting did not
hold. A fresh numbered, preregistered source/plan must isolate the status
boundary before any further QC execution. This terminal refusal is not an
analyst-signal return estimate.

## R-133 and R-134 — V7 numeric-status preopen QQQ order diagnostics (PREREGISTERED; UNLAUNCHED) — 2026-09-18

The new source/tests at `99f4fe5` version only the exact QC order-status
normalization. It keeps the previous point-in-time QQQ-weight stock core,
neutral overlapping QQQ ETF residual, 80% identity-weight floor, bounded
analyst-revision tilt, 98% gross, and 10-bps-per-side modeled fee. The
unchanged input package is SHA-256
`7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f`.
The exact private identities are frozen in lane-record section 129:

| Run | Private project / backtest | Profile SHA-256 | Projection SHA-256; plan SHA-256 |
|---|---|---|---|
| R-133, 2026 YTD | `81 ARV2_QQQ_NUMERIC_ORDER_R133_2026_YTD - 20260918` / `ARV2 R133 QQQ numeric order 2026 YTD 7803b84f` | `a2429a1f19645f6aa937d73108f6660b52e2aab2230e39cb68a2e180b58bf826` | `8f9cacbef0ef4698096cc7e22c8bd4a2991878a3d42387db3d015d8952e41f50`; `7e08bcd5881e38b643333ec4be89a0bbfdd8086fae79ef37240c69401c4224d0` |
| R-134, 2025-now contingent | `82 ARV2_QQQ_NUMERIC_ORDER_R134_2025_NOW - 20260918` / `ARV2 R134 QQQ numeric order 2025-now 7803b84f` | `48bb918df24a01507e0e8d79fc1a340f02215bb847ebc37a3cd8ac440dfa2f8c` | `fac8c6f47c0e4495ecdfe5a450e507bbd353a45906a982037a236ed8e4d26a5f`; `ebfef7a6b4f72ec66fdf5fb4ecc3a84544f9cadf296afc5f5b55df7a9ddaafae` |

Each projected source has ten files and 283,576 bytes. Starting count is
**93 shared looks, 36 development evaluations, 27 infrastructure looks,
607 cells**. A single R-133 launch spends **93 -> 94 / 36 -> 37** and adds
a cell only upon a separately authorized, authenticated aggregate read.
R-134 can spend **94 -> 95 / 37 -> 38** only after an authenticated usable
R-133 result (`run_valid` true); a technical or execution-invalid R-133
ends the pair with R-134 unspent. Neither run has a preselected return or
leverage decision. No QC action has yet occurred under these identities.

## R-133 — V7 preopen QQQ order diagnostic (TERMINAL STATUS REFUSAL; ZERO CELLS) — 2026-09-18

One signed submission from the exact plan at `aca883d` created private QC
project `36719419` and backtest `b66d1843e8d001da8ec83a1ffaaa03e4`.
The launch receipt SHA-256 is
`30c033a2d5074da833a2236f198caff9eea7444557ae9281075afe71eaca2d1e`.
The first statistics-disabled poll authenticated terminal `Runtime Error`,
receipt SHA-256
`7bb7057a2ade74236c1e0021901457401b78b20ca3c7b054f23e9f6a07e68b7d`.
One bounded error/stack diagnosis found the same `order-level QC event
status is unsupported` at simulated `2026-01-05 09:20:00`, during
replay of the first synchronous MOO event. The event status value itself
was not selected. No aggregate, raw order/fill/log, chart, provider row,
price, return, or signal verdict was obtained. V7's exact numeric string
mapping was not sufficient; a new enum-identity source and plan are
required, not an R-133 replay.

R-133 spends **93 -> 94 shared looks / 36 -> 37 development evaluations**
and adds **zero cells**, leaving **607 cells / 27 infrastructure looks**.
R-134 is superseded unlaunched/unspent because its contingent first usable
aggregate was not produced. No 2025-now, six-universe, or leveraged run
has followed this terminal refusal.

## R-135 and R-136 — V8 direct-enum QQQ simulated-order diagnostics (PREREGISTERED; UNLAUNCHED) — 2026-09-18

The prospective source at `6585d80` compares the QC `OrderStatus` members
directly and preserves the previous signal, PIT QQQ weights/residual,
80% resolved-weight floor, 98% gross, MOO schedule, and modeled 10-bps
per-side fee. The same authenticated immutable input package has SHA-256
`7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f`.
Exact private project names, profile/projection/source/plan/authority hashes
and the conditional order are frozen in lane-record section 132, before
any new QC action. R-135 is the 2026-YTD one-use plan; R-136 is 2025-now
and is contingent on an authenticated usable R-135 aggregate (`run_valid`
true and no fee mismatch). The technical status refused by R-133 was not
observed, so V8 remains a hypothesis to validate in QC, not a completed
return estimate.

Starting accounting is **94 shared looks, 37 ARV2 development evaluations,
27 infrastructure looks, 607 cells**. R-135 launch spends **94 -> 95 /
37 -> 38**; only its separately signed exact two-statistic aggregate can
add **607 -> 608 cells**. Only then can R-136 launch, spending **95 -> 96 /
38 -> 39** and adding at most one further cell. A technical refusal or
execution-invalid R-135 leaves R-136 unlaunched/unspent. Neither result
sign nor winner is selected, and no six-universe or leveraged run follows
by inference. Statistics-disabled terminal inspection precedes any result
read; raw QC orders, fills, logs, charts, provider/security rows, prices,
and unrestricted outcomes remain outside this authority.

## R-135 — V8 direct-enum 2026-YTD QQQ simulated-order diagnostic (OVERNIGHT-ACCOUNT TECHNICAL REFUSAL; ZERO CELLS) — 2026-09-18

The exact source/plan at `6585d80` / `1e6a4a6` created private QC project
`36720078`, backtest `995f7d8ff103fe2a705c5b56ad6eecac`, and launch
receipt SHA-256
`6f860889d3e514b0e6c5d72950a6b4766be5011ca418683f88115e396cde2ced`.
The first statistics-disabled status poll authenticated `Runtime Error`,
terminal receipt SHA-256
`24dbab553a0c120ba8fb98499052af8958b1d72bcc65c743c52a45669e1b208b`.
One bounded diagnostic selected only status/error/stacktrace for that run;
at simulated `2026-02-10 09:20:00`, the prior-close versus preopen account
guard refused `order-level overnight account changed after the decision`.
It did not reveal whether cash, share quantity, or both changed, and did
not select any aggregate statistic, raw account value, security/provider
row, order/fill/log/chart, price, or return. This is not an alpha estimate.

R-135 spends **94 -> 95 shared looks / 37 -> 38 development evaluations**
and adds **zero cells**, leaving **607 cells / 27 infrastructure looks**.
R-136 is superseded unlaunched/unspent because its contingent first usable
aggregate was not produced. A cash-only known-at-preopen replan with frozen
decision weights and a quantity-drift refusal is a prospective software
candidate, not a reinterpretation or retry of R-135. No 2025-now,
six-universe, or leveraged result follows.

## R-137 — V9 cash-reconciled 2026-YTD QQQ simulated-order diagnostic (UNKNOWN-ORDER TECHNICAL REFUSAL; ZERO CELLS) — 2026-09-18

The distinct signed V9 source/plan at `f0fa9eb` / `950cdbc` created private
project `36720686`, backtest `b52ad152aa4964de4f8adfe472a252b2`, and
launch receipt SHA-256
`0892eaf8c4796f3b48b289651e34165a786de82ed5fe839220345465ac872e0e`.
The first statistics-disabled terminal check authenticated `Runtime Error`,
terminal receipt SHA-256
`ab8f29ede56b4f4bc7c3cffefba84845695a1745e78601b0fac8c254f5cde7ed`.
One bounded exact-run diagnosis selected only status and a redacted
`order-level event references an unknown QC order` error/stack. It did not
select or retain any result aggregate, raw order/fill/log/chart, account
quantity/cash, security/provider row, price, return, or signal verdict.
An internal staging-to-ticket-registration callback gap is a plausible local
defect, but the error does not distinguish it from a late previous-ticket
or engine-generated order. See lane-record section 136; no speculative
economic interpretation is permitted.

R-137 spends **95 -> 96 shared looks / 38 -> 39 ARV2 development
evaluations** and adds **zero cells**, leaving **607 cells / 27 infrastructure
looks**. R-138 is superseded unlaunched/unspent because the first usable
aggregate was not produced. No order-level, 2025-now, six-universe, or
leveraged result follows this technical refusal.
