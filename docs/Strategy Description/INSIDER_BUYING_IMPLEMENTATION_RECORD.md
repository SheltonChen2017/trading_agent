# Insider Buying ETF Strategy — implementation and session record

Status: **THE IB-0/IB-1 STRUCTURAL SLICE, BOUNDED IB-1A RAW-SNAPSHOT
BOUNDARY, BOUNDED IB-1B OFFLINE EXPLICIT-PROFILE PARSER, AND BOUNDED IB-1C
OFFLINE EDGAR ACCEPTANCE-EVIDENCE SNAPSHOT HAVE COMPLETED INDEPENDENT CLAUDE
REVIEW. CODEX COUNTER-REVIEWED CLAUDE COMMIT `50bc867`, REJECTED IB1C-R15 AS
A FALSE POSITIVE, AND IMPLEMENTED THE BOUNDED IB-1D SUPPLIED-SAMPLE FORM 4/A
OBSERVATION CHRONOLOGY AT `73e87bc`; IB-1D NOW AWAITS CLAUDE REVIEW. IB-1 AND
BLUEPRINT SECTION 19.4 STEP 3 ARE NOT COMPLETE: NO OFFICIAL SEC PROFILE, REAL
PACKAGE, AUTHENTICATED AMENDMENT LINK, COMPLETE OR CROSS-QUARTER AMENDMENT
COVERAGE, OR CANONICAL FILTER AUTHORITY EXISTS. NORMALIZATION, SIGNAL
CONSTRUCTION, OUTCOME TESTING, ETF PORTFOLIO WORK, AND QC IMPLEMENTATION
REMAIN UNSTARTED.**

Branch: `codex/strategy-insider-buying`

Governing owner source: `INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf`, 33
pages, 945,953 bytes, SHA-256
`f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c`.

Codex is the primary implementer. Claude is the independent reviewer. Both
agents work serially on this same branch and follow
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`. During parallel development neither
agent may edit `docs/ACTION_PLAN_2026-08-20.md` or
`docs/SESSION_HANDOFF.md`; this record is the lane's status and handoff.

## 1. Canonical V1 contract

The initial event family is deliberately narrow:

- parse and retain SEC Form 4/4-A lineage, while allowing only an original
  Form 4 to reach pre-aggregation eligibility; the candidate row must be
  non-derivative common stock, exact transaction code `P`, acquired (`A`),
  officer or director, direct ownership, with positive shares and price;
- preserve row/lot lineage, aggregate only the same reporting-owner identity,
  security identity, and transaction date, then apply the $50,000 minimum to
  the aggregate rather than to each XML row;
- public EDGAR acceptance time—not transaction date—as availability, with
  next-open execution; date-only data receives a conservative next-day rule;
- `ln(1 + purchase_value / 50,000)` event size, 20-trading-day half-life,
  30-day lookback, winsorized cross-sectional z-score;
- unique-buyer, role, date, dollar breadth, and clustering are separate
  diagnostics rather than hidden score multipliers;
- PIT reverse ETF holdings with a conservative five-trading-day holdings lag
  unless QC `LastUpdate`/availability semantics are proven;
- US long-equity ETFs, at least 252 sessions old, price >= $5, median 20-day
  dollar volume >= $5M, holdings mapping >=90%, at least two seed stocks, and
  seed exposure >=5%; and
- weekly top 3-5 long-only ETFs, max 25% per ETF, 40% sector/theme cap, 35%
  overlap-cluster cap, cash permitted, and no leverage.

Sales, gifts, awards, derivatives, options, Form 5, indirect ownership, price
ranges, joint owners, and amendments are explicit exclusions or quarantines;
they are never silently dropped. A pure 10% owner with no officer/director
role is excluded, while an officer/director who also holds the 10% flag is
retained with a diagnostic. Private code-`P` purchases remain eligible with a
non-semantic footnote-mention diagnostic. Structured 10b5-1 status is retained
as a tri-state feature; prose mentioning 10b5-1 is a separate diagnostic and
does not silently assert the structured flag or exclude the event.

## 2. Milestone ladder

| Milestone | Scope | Exit gate |
|---|---|---|
| IB-0 | Freeze Form 4 schema, event inclusion/exclusion, amendment handling, availability, identity, score, horizons, costs, and look budget. | Complete preregistration; no outcomes accessed. |
| IB-1 | Ingest SEC quarterly files plus full-filing XML/metadata into immutable accession-versioned storage. | Reproducible checksums; amendment and duplicate tests; fair-access compliance. |
| IB-2 | Resolve CIK/reporting owner/security/transaction identities point-in-time. | Joint-owner, issuer, ticker-reuse, share-class, and amendment mutations fail closed. |
| IB-3 | Implement canonical stock event score and separate breadth diagnostics. | Golden equations and no outcome imports. |
| IB-4 | Build PIT ETF reverse index and eligibility/aggregation. | Holdings availability/lag, >=90% mapping, seed/exposure gates, and stale-map tests pass. |
| IB-5 | Run stock-level event study first, then industry and ETF topology tests. | Permanent look logged; primary result and null rule honored. |
| IB-6 | Walk-forward ETF portfolio research with fixed costs and baselines. | OOS robustness, turnover, capacity, overlap, and concentration gates. |
| IB-7 | Implement QC algorithm from immutable precomputed/custom signals. | Deterministic parity and failure/scheduling/sizing tests; research-only. |
| IB-8 | Final holdout and promotion dossier. | Owner approval required before paper deployment. |

## 3. First implementation scope

The first Codex session should implement **IB-0/IB-1 structural tests and an
offline fixture parser only**:

1. pin SEC submission, reporting owner, non-derivative transaction, footnote,
   accession, and acceptance-time schemas;
2. encode canonical include/exclude decisions as named outcomes;
3. model original/amended filing lineage without deleting the as-filed row;
4. add dangerous-direction tests for transaction-date availability,
   same-day execution, Form 5 inclusion, indirect ownership, missing price,
   and duplicate joint owners; and
5. update this record before the first push.

No SEC network crawl, outcome join, ETF construction, QC backtest, or broker
work is authorized by this plan.

## 4. Required data and unresolved gates

- SEC quarterly Insider Transactions Data Sets are free and cover Jan-2006
  onward, but they omit some filing metadata; the complete Form 4/4-A filing
  and EDGAR acceptance timestamp must be joined by accession.
- A durable CIK-to-security/QC Symbol mapping is not established.
- QC prices, security master, fundamentals, and PIT ETF holdings entitlements
  and timing semantics remain to be audited.
- A paid insider feed is optional, not required for canonical history. A
  commercial real-time feed may later reduce live latency but cannot replace
  the SEC filing as provenance without a measured reconciliation.

## 5. Session / push ledger

Append one row before every push. Never rewrite earlier rows.

| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Next |
|---|---|---|---|---|---|---|---|
| 2026-08-25 | Codex planning | `6156ef9` -> this shared baseline | Documentation only | Source reviewed and implementation ladder recorded; no code. | PDF text and all 33 rendered pages inspected; no outcome access; 0 looks. | SEC data is sufficient for a canonical offline backbone only when full-filing metadata is joined. | Claude reviews baseline; implementation waits for owner instruction. |
| 2026-08-27 | Codex implementation | `a4f58e6` -> `e770b05` (code snapshot; this lane-record commit follows) | Owner-authorized one-time common remediation synchronization | Synchronized the bounded shared-remediation series through `52518d6`, then identical final shared patch `e770b05` (source `6770db3`, stable patch ID `30e807c0ae2cf05016a2ce17c416daaaa275dcbc`). The range contains no Analyst-only commit or file and no Insider strategy implementation. | Exact lane tree: 5,223 passed, 2 skipped, 25 dependency-deprecation warnings in 36m40s; compileall exit 0; PowerShell parser 0 errors; `git diff --check` clean; worktree clean. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or live scheduler access; **0 research looks**. | Independent final audit found no remaining P0-P3 issue in the synchronized shared diff. Synchronization is not acceptance; IB-0/IB-1 has not started. | Push this exact lane-recorded snapshot; Claude reviews every pushed commit on this lane, then Codex counter-reviews every Claude commit before IB-0/IB-1 can begin. |
| 2026-08-27 | Codex implementation | `8a65e3c` -> `f943bfc` (code snapshot; this lane-record commit follows) | Owner-authorized shared portfolio-equity correction | Cherry-picked source fix `1ed0602` into `assistant/portfolio_snapshot.py` and `tests/test_assistant_risk_copilot.py`. The builder now aggregates exact Decimal cash and position values before rounding the single total-equity display, preventing legitimate fractional-share portfolios from failing the strict display/exact integrity check. The validator, policy limits, broker contracts, strategy code, and research gates were not weakened or changed. | Focused portfolio/risk/coherent-snapshot suite: 112 passed, 0 failed, 1 dependency warning in 3.01s; compileall exit 0; `git diff --check` clean. Source correction previously passed the complete 5,442-test suite and a reverse mutation that reproduced display `100.01` versus exact `100`. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. | `SYS-FU-P1-006` reproduced: per-position display rounding accumulated into a competing equity total and prevented UI load. Corrected without adding tolerance; pending Claude review and Codex counter-review. IB-0/IB-1 remains unstarted. | Validate and push the exact recorded lane snapshot. Claude then reviews both new commits on this lane before IB-0/IB-1 or any later milestone. |
| 2026-08-27 | Codex validation | `29efc30` -> `29efc30` (exact isolated tested snapshot; this validation-record commit follows) | Portfolio-equity correction final validation | Revalidated the complete Insider Buying lane after its code and required lane-record commits in a detached isolated worktree pinned to `29efc30`; no product file changed during the run. | Complete exact-tree suite: **5,224 passed, 2 skipped, 0 failed, 25 dependency warnings in 1,832.32s (30m32s)**. The earlier focused 112-test suite, 63-test active-document suite, compileall, and diff checks were also green. Fixture-only; no SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. | No new P0-P3 finding. `SYS-FU-P1-006` remains implemented but unaccepted pending the required review chain; IB-0/IB-1 remains unstarted. | Commit this validation record and push the complete three-commit lane range; Claude reviews every new commit before IB-0/IB-1 or any later milestone. |
| 2026-08-28 | Claude review | `b4ba4b2` -> this review snapshot | Independent review of the owner-authorized shared remediation synchronization (`a4f58e6..b4ba4b2`, 16 commits) | Verified provenance by stable patch ID (12 of 13 synchronized commits patch-identical to their merged main-line counterparts; the single divergence correctly omits the analyst-only entry-point registration), confirmed the frozen-file freeze held, and reviewed every commit for fail-open, atomicity, money-type, and test-weakening defects. Corrected one confirmed defect and escalated one open P1. Full dispositions and the P0-P3 ledger are in section 6. | Complete suite at `8a65e3c`: 1 failed, 5,222 passed, 2 skipped in 29m07s (the failure is R-02, contradicting the recorded zero-failure claim on this host). After correction: affected file 49 passed, 1 skipped; import-boundary/entry-point/active-document 98 passed; execution-gate and characterization 76 passed; dispatch-fence and cancel-all 89 passed, 1 skipped; broker-binding suites 263 passed, 1 skipped; compileall exit 0; PowerShell parser 0 errors; `git diff --check` clean. Final complete suite on the exact pushed tree `58bf2f8`: **5,223 passed, 3 skipped, 0 failed, 25 warnings in 36m32s**. An intermediate complete run under host contention reported 6 `TimeoutExpired` failures against byte-identical code and is recorded as R-19 rather than omitted. Two mutations run and reverted cleanly. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or scheduler access; **0 research looks**. | R-01 (P1, OPEN): strict snapshot coherence refuses submission on any price tick with no risk-reducing-sell exemption, conflicting with the CLAUDE.md section 5 exception; escalated for an owner decision rather than corrected on a lane branch. R-02 (P2) fixed in `1c1d943`. R-03 to R-08 recorded open for counter-review. A second audit then changed the `9406a34` disposition to defect-found: R-09 to R-15 are seven further P1 issues open at HEAD, four verified directly against this host, including a machine-global execution stop currently latched active by test-origin incidents. R-18 records that the same stop defeats cross-lane isolation; R-16, R-17, and R-19 are lower-severity. Nine P1 issues are open in total and none was corrected on this lane, because they are shared execution semantics synchronized from `main`. | Codex counter-reviews every Claude commit in this range, then may begin IB-0/IB-1 in one combined push. R-01 needs an explicit owner decision before it can be closed. IB-0/IB-1 remains unstarted. |
| 2026-08-28 | Codex counter-review | `17c1bb2` -> this counter-review record commit | Counter-review of all five Claude commits after `b4ba4b2` | Re-read every diff in chronological order, independently verified the 13-commit provenance claim, reproduced the executable correction and material safety findings, generalized the affected paths, and recorded a superseding disposition for every R-01 through R-19 item in section 7. No shared production code was changed. | Stable patch IDs: 12 exact matches and the intended two-line Analyst-only omission in `800c689`; focused offline suite: **31 passed** in 30.88s; direct lifecycle probe mapped both `held` and `calculated` to critical `submission_unknown`; R-02 actual-interpreter test passed; R-07/R-15 deterministic component disagreement reproduced. `git diff --check` and active-document checks follow before commit. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, or order access; **0 research looks**. | Accepted after documentation correction. R-04 is rejected as a false positive: the outer dispatch fence is acquired before authoritative snapshot capture and the adapter fence is same-thread re-entry. R-09's historical host condition is no longer current because the reported runtime-stop file is absent; its global-state mechanism remains covered by R-10/R-18. All other classifications and residual gates are retained as scoped in section 7. | Commit this counter-review checkpoint. Because no owner decision blocks offline structure work, proceed to the bounded IB-0/IB-1 milestone before one combined lane push. |
| 2026-08-28 | Codex implementation | `4e51e14` -> this implementation record commit | IB-0/IB-1 offline structural contracts and fixture parser | Added a dependency-free `research/insider_buying` package, frozen canonical constants and zero-look authority, named include/exclude outcomes, exact/date-only public-availability contracts, SHA-256 source/event identities, original/amended accession lineage that retains every as-filed version, and a bounded XML fixture parser. Added four synthetic fixtures and dangerous-direction tests; no downloader, persisted dataset, security mapping, score engine, outcome, ETF, or execution surface exists. | Focused implementation suite: **25 passed**. Two reverse mutations were killed and restored. First complete run: **1 failed, 5,248 passed, 2 skipped** in 51m25s; the sole failure was a five-second subprocess timeout in a pre-existing dispatch-fence test. That test passed alone in 2.72s and its file passed 24 with 1 skip in 4.86s. Clean complete rerun on the unchanged code tree: **5,249 passed, 2 skipped, 0 failed, 25 warnings in 1h10m04s**. Final exact-tree checks follow below. No SEC/provider/credential/licensed-row/outcome/QC/broker/operator-database/scheduler access; **0 research looks**. | Self-review corrected four implementation issues before handoff. One shared P3 test-load finding, IB01-R05, remains open; no open P0-P3 finding exists in the new lane-owned diff. Section 8 retains every disposition. | Commit this milestone and push the combined counter-review plus implementation range for Claude review. |
| 2026-08-28 | Claude review | `65494fb` -> this review snapshot | Review of the Codex counter-review and the IB-0/IB-1 offline structural slice (`17c1bb2..65494fb`) | Verified ancestry and frozen-file isolation individually, adopted the counter-review's correct R-04 rejection, reversed its R-09/R-18 downgrade on fresh evidence, and assessed the IB-0/IB-1 slice against the governing blueprint. Added seven contract-boundary regression tests. Full dispositions are in section 8. | Lane suite 25 passed before correction and 32 after; combined lane, ml import-boundary, entry-point, and active-document suites 130 passed in 51.20s; mutation sweep of five PublicAvailability guards survived 5 of 5 before the correction and was caught 5 of 5 after, file restored clean; `git diff --check` clean; complete-suite result for the pushed tree recorded in section 8.6 and below. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or scheduler access; **0 research looks**. | R-20 (P1, OPEN): the counter-review's claim that the runtime-stop file is absent could not be reproduced; it is present, active, generation 19, with 19 open incidents including all three analyst-lane-origin ones, so R-09 is restored to current and R-18's evidence stands. R-21 (P2) fixed here: every PublicAvailability guard was untested and could be deleted with the suite green. R-04 withdrawn as a false positive. | Codex counter-reviews these Claude commits, then may continue the IB ladder. Eight shared-surface P1 issues remain open and uncorrected on this lane; R-20 needs owner attention independently. |
| 2026-08-29 | Codex counter-review + implementation | `65494fb..d8561c1` reviewed; `d8561c1` -> `8107915` implementation snapshot (this lane-record commit follows) | Claude counter-review plus bounded IB-1A raw quarterly snapshot | Dispositioned all three Claude commits, corrected the PDF contract for dual-role 10% owners, private/10b5 features, and the post-aggregation value gate, then added a caller-supplied-bytes-only SEC quarterly ZIP integrity and immutable-publication boundary. Work remained under the Insider Buying research/tests/docs lane; no Trading App or Streamlit code changed. | Exact focused tree: **166 passed, 4 platform symlink skips**; final targeted mutation audit: **17/17 killed, 0 material survivors**; six changed/new Python files compiled; `git diff --check` clean apart from line-ending notices. Read-only runtime resolver: file absent, inactive, generation 0, 0 incidents. No external/provider/outcome/QC/broker/operator/scheduler access; **0 research looks**. | R-21 and `f2875fd` accepted; `f4257de` accepted after current-record corrections; `d8561c1` retained as prior-tree validation only. IB-CR-01 through IB-CR-04 and IB1A-R01 through IB1A-R08 are resolved or explicitly dispositioned in section 10; independent exact-current P0-P3 review found no remaining code issue. | Commit the lane record, validate the exact committed tree, append an immutable validation row, and make one push. Claude then reviews every pushed commit before the next Codex counter-review plus IB-1B round. |
| 2026-08-29 | Claude review | `df1b7d4` -> this review snapshot | Review of the IB-1A raw snapshot boundary and the counter-review of the prior Claude round (`d8561c1..df1b7d4`) | Synced by fast-forward after confirming ancestry. Accepted all three counter-review defects raised against this reviewer as genuine misses, independently verified each claimed fix by direct probe rather than by reading the record, checked both removed tests for weakening, and mutation-swept the new ingest module. Full dispositions are in section 11. | IB-1A and Form 4 suites 166 passed, 4 skipped in 21.87s; ml import-boundary and entry-point suites 35 passed; active-document 63 passed; direct probes confirmed UTF-16 and UTF-8 DTD refusal and three PublicAvailability type-confusion refusals; mutation sweep of all 80 REFUSED sites in `sec_bulk_snapshot.py` gave 39 caught, 41 survived, 0 invalid, file restored clean; `git diff --check` clean; complete-suite result below. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, or scheduler access; **0 research looks**. | Three counter-review findings against this reviewer confirmed and accepted: the dual-role ten-percent-owner over-exclusion, the pre-aggregation placement of the $50,000 gate, and the UTF-16 DTD bypass. No test weakening found; both removed tests were legitimate corrections and all seven Claude contract tests survive. R-22 (P2) resolves the R-09/R-20 dispute: the runtime stop is per-machine %LOCALAPPDATA% state, so both parties were correct on their own hosts, and it stands at generation 21 on this host. R-23 and R-24 (P3) recorded. | Codex counter-reviews these Claude commits, then may continue the bounded IB ladder. Shared-surface P1 set unchanged and uncorrected on this lane. |
| 2026-08-29 | Codex validation | `82d048c` -> `82d048c` (exact tested snapshot; this validation-record commit follows) | IB-1A final exact-tree validation | Revalidated the committed code plus counter-review record without changing product files. The later validation-record commit changes this lane document only. | Combined Insider/import-boundary/entry-point/active-document suite: **266 passed, 4 skipped in 20.91s**; complete exact-tree suite: **5,390 passed, 6 skipped, 0 failed, 26 warnings in 1,053.88s (17m33s)**; whole-repository compileall exit 0. Post-suite read-only runtime resolver: file absent, inactive, generation 0, 0 incidents. No external/provider/outcome/QC/broker/operator/scheduler access; **0 research looks**. | No new P0-P3 finding. The skips are platform-conditional; the warnings are dependency/runtime notices retained in section 10. The tested snapshot stayed clean. | Commit this validation record, run the record-sensitive final checks, and make the single push. Claude independently reviews every pushed commit before any IB-1B work. |
| 2026-08-29 | Codex counter-review + implementation | `df1b7d4..8d9e70b` reviewed; `8d9e70b` -> this implementation snapshot | Claude counter-review plus bounded IB-1B offline parsed snapshot | Fast-forwarded the same worktree/branch, dispositioned both Claude commits and the omitted prior-commit verdicts, corrected the reproduced hard-process-restart gap in IB-1A, and implemented a mandatory-profile offline TSV parser plus immutable parsed snapshot. Only `research/insider_buying`, its tests, and this lane record changed; no Trading App or Streamlit work. | Exact-current Insider/import-boundary/entry-point/module-hygiene suite: **269 passed, 5 platform symlink skips in 48.78s**. Raw plus parsed boundary subset: **135 passed, 5 skips**; exact hard-restart, mixed-residue, source-key, raw-bound reload, semantic-forgery, resource-cap, concurrent-writer, and lock-domain regressions are included. No SEC/EDGAR/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, or UI access; **0 research looks**. | `76f0c21` accepted after current corrections; `8d9e70b` accepted only as validation of its prior tree. IB1B-CR-01 through IB1B-R08 are fixed or dispositioned in section 12. R-22 is host-local process evidence only; R-23 remains deferred integration debt. No official/live SEC schema compatibility is claimed. | Commit the implementation and lane record, validate the exact committed tree including the complete suite and compileall, append a validation row, then make one push. Claude reviews every pushed commit before further Insider work. |
| 2026-08-29 | Codex validation | `9cbc962` -> `9cbc962` (exact tested snapshot; this validation-record commit follows) | IB-1B final exact-tree validation | Revalidated the committed counter-review, IB-1A restart correction, IB-1B code, tests, and lane record without changing product files. The later validation-record commit changes this lane document only. | Complete exact-tree suite: **5,450 passed, 7 skipped, 0 failed, 26 warnings in 1,022.22s (17m02s)**; whole-repository compileall exit 0; focused exact-tree suite **269 passed, 5 skipped in 48.78s**; active-document checks **63 passed**; `git diff HEAD^ HEAD --check` clean. No SEC/EDGAR/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, UI, or order access; **0 research looks**. | No new P0-P3 finding. The skips are platform-conditional and the warnings are dependency/runtime notices; the exact tested snapshot stayed clean. | Commit this validation record, run record-sensitive final checks, and make the single push. Claude independently reviews every pushed commit before further Insider work. |
| 2026-08-29 | Claude review | `8d9e70b` -> this review snapshot | Independent review of the IB-1B parsed snapshot boundary and of the counter-review of the prior Claude round (`8d9e70b..03820d3`, 2 commits) | Verified frozen-file isolation and ancestry, accepted all four counter-review findings raised against this reviewer, independently reproduced the IB-1A restart correction by direct probe, and paired-mutation-swept the new module's semantic guarantees instead of counting single refusal sites. Added six regression cases for the loader's row-level rebuild and the row caps. Full dispositions are in section 13. | Focused Insider/import-boundary/hygiene/separation suite **278 passed, 5 skipped in 41.74s**; IB-1B module **61 passed, 1 skipped** after the additions (55 before); independent complete suite on the exact pushed tree `03820d3`: **5,450 passed, 7 skipped, 0 failed, 25 warnings in 867.42s**, reproducing the recorded Codex pass/skip figures; paired mutation sweep of seven semantic invariants **2 caught / 5 survived before, 7 caught / 0 survived after**, module restored byte-identical to `HEAD`; twelve direct restart probes across both modules; complete suite on the exact final review tree after correction commit `61b0bec`: **5,456 passed, 7 skipped, 0 failed, 25 warnings in 830.27s**; active-document suite 63 passed; compileall exit 0. No SEC/EDGAR, provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, or UI access; **0 research looks**. | IB1B-R10 (P2) fixed here: the loader's row-level semantic rebuild was undefended by tests, so `row_id` lineage, `schema_id` binding, ordinal sequence, accession projection, and both row caps could each be deleted with the suite green. IB1B-R09 (P2, OPEN) records that a partial-write hard restart still permanently blocks retry in both modules; deliberately not fixed because loosening a fail-closed check is an implementer decision. IB1B-R11 and IB1B-R12 (P3) recorded. No test weakening found. | Codex counter-reviews these Claude commits, then may continue the bounded IB ladder. Shared-surface P1 set unchanged and uncorrected on this lane under the owner's 2026-08-29 strategy-scope rule. |
| 2026-08-30 | Codex counter-review + implementation | `61b0bec..60c2f29` reviewed; `60c2f29` -> `7b3377b` counter-review correction -> `892218d` implementation snapshot (this lane-record commit follows) | Claude counter-review plus bounded IB-1C offline EDGAR acceptance-evidence snapshot | Accepted both Claude commits after two record corrections, closed the confirmed IB-1A/IB-1B partial-write restart gap, and added a caller-supplied, explicit-profile acceptance-evidence boundary that covers every verified IB-1B accession with exact evidence or an explicit date-only fallback. It performs no download, discovery, XML validation, amendment reconciliation, normalization, outcome access, ETF work, QC job, broker action, or UI change. | Exact current nine-file Insider/import-boundary/hygiene/separation suite: **477 passed, 7 platform skips in 130.14s**; final IB-1C module: **153 passed, 2 skips in 98.03s**; independent IB-1C plus record review: **154 passed, 2 skips**; compileall exit 0; `git diff --check` clean apart from line-ending notices. No SEC/EDGAR/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, UI, or order access; **0 research looks**. | `61b0bec` accepted; `60c2f29` accepted after current record correction. IB1B-R09 is fixed in `7b3377b`; IB1B-R10 is accepted; IB1B-R11 remains deferred neutral-I/O integration debt; IB1B-R12 is rejected as a false positive. IB1C-R01 through IB1C-R14 are fixed in section 14; two independent final audits report no remaining P0-P3 finding. | Commit this lane record, validate the exact committed tree with the complete suite and whole-repository compileall, append a validation row, then make the round's single push. Claude reviews every pushed commit before any amendment-reconciliation milestone. |
| 2026-08-30 | Codex validation | `72c5c86` -> `72c5c86` (exact tested snapshot; this validation-record commit follows) | IB-1C final exact-tree validation | Revalidated the committed counter-review correction, acceptance-evidence implementation, tests, exports, and authoritative section 14 without changing product files. This later commit changes only this lane record. | Complete exact-tree suite: **5,649 passed, 9 skipped, 0 failed, 26 warnings in 1,035.43s (17m15s)**; whole-repository compileall exit 0; exact active-document plus lane-record checks **64 passed**; focused nine-file suite **477 passed, 7 skipped in 130.14s**; `git diff HEAD^ HEAD --check` and `git diff 60c2f29..HEAD --check` clean. No SEC/EDGAR/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, UI, or order access; **0 research looks**. | No new P0-P3 finding. The nine skips are platform-conditional; the 26 warnings are dependency/runtime notices. The exact tested snapshot stayed clean. | Commit this validation record, rerun record-sensitive checks, confirm the remote remains the reviewed base, and make the round's single push. Claude independently reviews every pushed commit before further Insider work. |
| 2026-08-30 | Claude review | `60c2f29` -> this review snapshot | Independent review of the IB1B-R09 recovery correction and the bounded IB-1C EDGAR acceptance-evidence milestone (`60c2f29..d6f587b`, 4 commits) | Verified frozen-file isolation, dispositioned all four commits, accepted all six counter-review findings including three genuine errors of this reviewer, probed the R-09 relaxation guards rather than reading them, and mutation-swept the IB-1C look-ahead invariants. One new P2 found and reported. Full dispositions are in section 15. | Nine-file focused suite **477 passed, 7 skipped**, reproducing the recorded figure exactly; IB-1C module **153 passed, 2 skipped**, also exact; independent complete suite on the exact pushed tree `d6f587b`: **5649 passed, 9 skipped, 25 warnings in 975.56s (0:16:15)**; look-ahead mutation sweep **9 of 9 caught**; R-09 relaxation sweep **5 of 5 caught**; thirteen residue probes, four availability-contract probes, and five real-data timing reproductions; every module restored byte-identical to `HEAD`. No SEC/EDGAR, provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, or UI access; **0 research looks**. | IB1C-R15 (P2, OPEN): the filing-day window assumes acceptance shares a day with FILING_DATE, but EDGAR assigns the next business day to anything accepted after 17:30 ET, so routine after-hours Form 4 filings refuse and the first real package would fail in full; reported not fixed because widening a central availability invariant is an implementer decision. IB1C-R16 (P3): the immutable-I/O helper set is now triplicated and the R-09 fix had to be written three times in one milestone. My IB1B-R12 is withdrawn as a false positive caused by a silent no-match glob. No test weakening; zero test deletions in the range. | Codex counter-reviews these Claude commits and decides IB1C-R15 before the bounded amendment-reconciliation milestone. Shared-surface P1 set unchanged under the owner's strategy-scope rule. |
| 2026-08-30 | Codex counter-review + implementation | `d6f587b..50bc867` reviewed; `50bc867` -> `73e87bc` implementation snapshot (this lane-record commit follows) | Claude counter-review plus bounded IB-1D supplied-sample Form 4/A observation chronology | Rejected IB1C-R15 using the SEC ownership-form exception that preserves the filing date through 10 p.m. ET, retained the strict IB-1C filing-day guard, corrected five review-record defects, and implemented an offline exact-acceptance Form 4/A chronology whose completeness and canonical-filter gates are immutably false. The slice binds caller-supplied XML to verified IB-1C evidence, retains as-filed versions, orders supplied amendments by acceptance time, and quarantines every amendment row. It performs no publication, download, discovery, normalization, signal, outcome, ETF, QC, broker, or UI work. | IB-1C/IB-1D module: **189 passed, 2 platform skips in 132.03s**; exact nine-file Insider/import-boundary/hygiene suite: **513 passed, 7 platform skips in 210.92s**; focused final boundary slice: **32 passed, 159 deselected**; **11/11 source mutants killed** plus forged-wrapper and duplicate-lineage adversarial probes caught; compileall over the Insider package and changed test exit 0; `git diff --check` clean apart from line-ending notices. Official SEC filing-rule documentation only was consulted; no filing, package, API, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, UI, or order access; **0 research looks**. | `50bc867` accepted after current-record correction. IB1C-R15 is a false positive; IB1C-R16 stays deferred P3 debt. Pre-commit audits found and fixed the omitted-amendment authority escape, parsed-object amplification, identity-hash survivors, wrapper forgery, contradictory amendment outcomes, future-boundary exposure, and duplicate-lineage drift. Three final audits report no remaining P0-P3 finding in the implemented scope. | Commit this authoritative lane record, validate the exact committed tree with the complete suite and whole-repository compileall, append an immutable validation row, then make the round's single push. Claude reviews every pushed commit before any further Insider milestone. |

## 6. Claude review - shared remediation synchronization (2026-08-28)

Reviewer: Claude, dedicated Insider Buying lane review session, working in an
isolated worktree pinned to this branch. Range reviewed: `a4f58e6..b4ba4b2`
(13 synchronized commits plus 3 later lane commits). No `git switch` was used
and no other lane, checkout, or branch was touched.

Owner-directed authority for this range is the one-time common-remediation
exception recorded in `THREE_STRATEGY_PARALLEL_WORKFLOW.md` and
`THREE_STRATEGY_PROJECT_DIRECTION.md`. Synchronization is not acceptance.

### 6.1 Provenance and isolation verification

- 12 of the 13 synchronized commits are **patch-identical** to their
  owner-merged main-line counterparts by `git patch-id --stable`, including
  the final shared patch `e770b05`, whose stable patch ID
  `30e807c0ae2cf05016a2ce17c416daaaa275dcbc` matches the value claimed in the
  section 5 ledger.
- The single intended divergence is `800c689` versus main `8cab638`: the lane
  commit correctly **omits** the analyst-only `research/analyst_revisions_v2`
  entry-point registration and its assertion. Verified by interdiff; exactly
  two lines differ. No analyst-only file, research module, or test entered
  this lane.
- Every frozen-document change in the range traces to the single
  owner-authorized reconciliation commit `52518d6`.
  `docs/ACTION_PLAN_2026-08-20.md` and `docs/SESSION_HANDOFF.md` are
  unmodified. No `research/` file changed on this lane.
- No SEC, EDGAR, vendor, QuantConnect, credential, licensed-row, broker,
  operator-database, or scheduler access occurred during this review.
  **0 research looks.** IB-0/IB-1 remains unstarted.

### 6.2 Commit dispositions

| Commit | Subject | Disposition |
|---|---|---|
| `63987ab` | Fix boolean coercion in trading policy limits | Accepted |
| `4e60b63` | Add cross-process execution dispatch fence | Accepted after correction later in range |
| `f602792` | Harden dispatch fence across process forks | Accepted |
| `5d22602` | Bind execution authorization to broker context | Accepted after correction later in range |
| `5fc891f` | Make broker anomaly containment atomic | Accepted after correction later in range |
| `c31f1e3` | Fence and drain emergency order cancellation | Accepted after correction later in range |
| `2fc3dd6` | Bind broker access to coherent account snapshots | Accepted after correction; **one P1 open at HEAD (R-01)** |
| `b4f4532` | Close emergency cancel-all indexing races | Accepted after correction later in range |
| `9406a34` | Harden shared trading safety boundaries | **Defect-found** - seven P1 issues open at HEAD (R-09 to R-15); `assistant/storage.py` is byte-identical between this commit and HEAD, so nothing here was repaired downstream |
| `800c689` | Register shared research input boundaries | Accepted, lane-correct divergence verified |
| `52518d6` | Reconcile three-strategy review workflow | Accepted |
| `e770b05` | fix: close shared remediation regressions | Accepted after correction (**R-02**, corrected here); one silent-row-drop loosening recorded as R-16. It fixes real code and is not a loosen-the-tests commit. |
| `8a65e3c` | docs: record shared remediation synchronization | Accepted |
| `f943bfc` | Fix portfolio equity display aggregation | Accepted, mutation-verified |
| `29efc30` | Record insider lane portfolio rounding sync | Accepted |
| `b4ba4b2` | Record insider lane full validation | Accepted with a correction to its validation claim (**R-02**) |

Commits marked "accepted after correction later in range" had a real defect at
that commit which is already remediated by a later commit inside this same
synchronized range. Each was re-verified at HEAD by reading the fixed code
path, not by trusting a commit message.

### 6.3 P0-P3 issue ledger

Resolved items are retained, never deleted.

| ID | Sev | Status | Issue |
|---|---|---|---|
| R-01 | P1 | **OPEN - escalated to owner, deliberately not corrected here** | Strict execution-snapshot coherence refuses submission on any market-price movement, with **no risk-reducing-sell exemption**. `_execution_snapshot_state_fingerprint` hashes every position `current_price` and `market_value`; `_assert_execution_snapshot_unchanged` (`execution/alpaca_broker.py:857`) requires a byte-identical recapture immediately before broker contact, and both submission paths (`:1481` market, `:1610` limit) call it unconditionally with no branch on `side`. A single tick in any held symbol refuses the order. The direction is fail-closed, so nothing wrong is sent, but CLAUDE.md section 5 states a conservative safeguard must not delay or obstruct a legitimate risk-reducing sell. The branch tests pin the refusal as the specification, so this is a deliberate design that conflicts with a standing safety exception: an owner decision, not a reviewer edit. |
| R-02 | P2 | **FIXED - `1c1d943`** | `e770b05` added `test_windows_verifier_green_actions_match_installer_whatif_previews`, which passes `sys.executable` to the real installer. The installer correctly refuses a Microsoft Store app execution alias, a zero-byte reparse point a scheduled task cannot launch. On a host whose default interpreter is that alias the test failed deterministically, so the recorded zero-failure validation was not reproducible here. Corrected with a skip guard mirroring the installer enforcing condition exactly, reparse point **or** zero length, via `lstat` so the reparse point is not followed. Product behavior unchanged. |
| R-03 | P2 | OPEN - for counter-review | Re-invoking emergency cancel-all against orders already in `pending_cancel` may never satisfy the stability condition, activating a critical reconciliation halt although containment is complete. Fail-closed, a spurious critical alert and never fail-open. Depends on the broker real response to cancelling a `pending_cancel` order; not verified against a live broker, so deliberately not fixed on an unverified assumption. |
| R-04 | P2 | OPEN - for counter-review | The execution timing budget is self-defeating under contention: the snapshot authority window and the dispatch-fence acquisition timeout are both 30 seconds, so a dispatch that waits materially for the fence holds an already-expired snapshot and is refused. Affects a queued risk-reducing sell equally. |
| R-05 | P3 | OPEN | `_validated_authorization_binding` accepts `none`, `null`, and `unknown` as `account_id`, while `broker_contract.py`, `alpaca_broker.py`, and `portfolio_snapshot.py` all reject those sentinels. Not exploitable today; the layer that signs identity has the weakest identity contract of the four. |
| R-06 | P3 | OPEN | Two alert-fingerprint schemes coexist for one category: `activate_reconciliation_halt` still uses the proposal-only form while anomaly containment uses the form suffixed with an anomaly key. An operator acknowledgement of one does not suppress the other. |
| R-07 | P3 | OPEN | A permanent component-equity disagreement is raised as a transient mutation, so it burns the retry budget and is reported as broker state did not stabilize, pointing the operator at a race rather than the real cause. |
| R-08 | P3 | OPEN | Order-level account identity is self-asserted: `portfolio_snapshot.py` passes the same identity object as both expected and observed, making that mismatch check a tautology at those call sites. The durable `assert_expected_broker_account` path remains meaningful. |

| R-09 | P1 | **OPEN - LIVE OPERATIONAL CONDITION, owner action required** | The machine-global runtime execution stop is **currently active on this host**. `C:\Users\<user>\AppData\Local\trading_agent\runtime\state\execution-emergency-stop.json` reads `active: true`, `generation: 16`, `scope: execution_runtime`, with **16 open incidents whose `origin_database` values are all throwaway paths** (pytest temp directories and audit scratch databases), the most recent stamped 2026-08-28. `execution_service` consults this file for every database, so the real operational app would refuse every proposal, **risk-reducing sells included**, until an explicit clear naming the exact incident ids and generation. Verified by reading the file directly, read-only. Deliberately **not cleared**: mutating operational runtime state is an owner action, not a reviewer action. Test suites run by any lane can latch it, so this recurs until the scoping in R-15 changes. |
| R-10 | P1 | OPEN - verified by this review | Read-only and reporting paths latch that machine-global stop. `assistant/storage.py:5876` `_activate_detected_broker_integrity_incident` calls `activate_runtime_emergency_stop` **before and outside** the `if not self.read_only:` guard, and its callers include `get_execution_budget_usage`, `database_integrity_check`, and `AssistantStore.__init__`, which `assistant/readiness.py` invokes as a report. One corrupt historical row therefore lets a readiness poll halt execution. Contradicts CLAUDE.md section 7 (registry status must not be a side effect of presentation) and section 9 (read-only commands leave execution tables unchanged). This is the mechanism behind R-09. |
| R-11 | P1 | OPEN - verified by this review | `_refuse_while_prior_dispatch_is_ambiguous` (`assistant/execution_service.py:427`, called unconditionally) refuses **any** new submission while an earlier dispatch is unresolved, with no branch on `side`, although its own docstring scopes the intent to "do not add account exposure". A timed-out BUY therefore blocks an approved risk-reducing SELL, and the raised `ProposalExecutionError` is converted to `BLOCKED`, so the sell proposal is consumed and must be regenerated and re-approved. |
| R-12 | P1 | OPEN - verified by this review | `get_execution_budget_usage` (`assistant/storage.py:5644`) now issues `SELECT * FROM broker_order_events` with no `WHERE` clause, re-hashing the entire event history on the readiness and pre-dispatch hot path that the deployed monitor polls every 30 seconds. Combined with R-10, a single bad historical row halts the machine. |
| R-13 | P1 | OPEN - reported, structurally confirmed | A skewed or missing broker `submitted_at` escalates to a global halt rather than a skip. `assistant/order_reconciler.py:588` routes `not integrity_ok` into `activate_reconciliation_halt` (persistent kill switch plus runtime-global stop); `assistant/temporal_integrity.py:14` sets a 5.0 second future-skew tolerance; the deployed `OrderMonitor` task polls every 30 seconds. A local clock a few seconds behind the broker can therefore halt all trading unattended, and also suppress stale-order cancellation, itself a risk-reducing action. The prior behavior skipped instead. Tolerance constants and the halt call verified; the end-to-end unattended scenario is not reproduced here. |
| R-14 | P1 | OPEN - reported, not independently reproduced | `held` and `calculated`, both normal in-lifecycle broker states still listed in `KNOWN_BROKER_ORDER_STATUSES` and `ACTIVE_BROKER_ORDER_STATUSES`, now project to `submission_unknown` (`assistant/order_lifecycle.py:45`), which feeds both the R-11 gate and the critical-unresolved set. One order going `held` would make readiness not-ready and block every later proposal. Reported to have no test coverage for either status. |
| R-15 | P1 | OPEN - reported, not independently reproduced | Two further fail-closed traps: a legacy `broker_order_events` row with a naive `event_at` is reported to make the database permanently unopenable read-write with no self-heal, and deterministic snapshot-integrity failures (negative cash, zero entry price, component disagreement) are reported to be retried as transient and then surfaced as "broker state did not stabilize", blocking all submission while naming the wrong cause. Also the scoping question behind R-09: the runtime stop is shared per OS user and ignores the database, so a per-database fault halts every database on the host. |
| R-18 | P1 | **OPEN - cross-lane isolation defeated** | The machine-global runtime execution stop couples the three supposedly isolated strategy lanes. Enumerating the open incident set shows two whose `origin_database` is the **analyst-revisions lane** (`...\codex_arv2_full_tmp\test_real_process_crash_mid_tr0\assistant.db` and `...\trading_agent_analyst_revisions\.codex-test-tmp-counter-review\...\assistant.db`). One lane running its own test suite therefore latches an execution stop that halts every other lane and the operational app. The parallel-workflow contract requires per-lane checkouts precisely so lanes cannot affect one another; that guarantee holds for the filesystem and for git, but not for this per-user runtime file, which ignores its `database` argument. Directly related to R-09 and R-15, and recorded separately because it is a program-level isolation defect rather than only an execution-safety one. Verified by enumerating the live incident set, read-only. |
| R-19 | P3 | OPEN | The Windows verifier and installer-preview tests hard-code a 30-second `subprocess.run` timeout for each PowerShell child process, which makes them load-fragile. On a busy host the identical tree produced 6 `subprocess.TimeoutExpired` failures in `tests/test_ml_evidence_operations.py` and 24 timeout traces overall, and the same file then passed 49 of 49 (1 skipped) in 4m08s once the host was idle. The failure mode is indistinguishable at a glance from a real regression, and it appears exactly when a reviewer runs other work in parallel. A load-independent budget, or a documented serial-execution requirement for this file, would remove the ambiguity. |
| R-16 | P2 | OPEN | `e770b05` changed a zero-share position row from a refusal to a silent `continue` in `assistant/portfolio_snapshot.py`, with no record. A broker feed reporting zero shares for a genuinely held position makes it vanish from the snapshot, so a risk-reducing sell for that ticker reads as not held. Violates CLAUDE.md section 8 (no silent row dropping). The strict Alpaca path is unaffected. |
| R-17 | P2 | OPEN | Two characterization tests are now vacuous: policy revalidation moved earlier, so they fail before any reservation is made and `assert state["reservations"] == []` is trivially true. Deleting the reservation release from the submit kernel reportedly leaves the suite green, although that test was originally created by mutation testing against exactly that deletion. |

Deliberately **not** corrected: R-01, R-03 through R-08, and R-09 through R-19 are owner-level
design decisions, unverified against a live broker, or outside a reviewer
surgical-correction mandate on shared code synchronized from `main`.
Correcting them on this lane would also diverge shared execution semantics
from `main` and from the other two lanes.

### 6.4 Validation performed by this review

All runs on this exact lane tree in the isolated worktree.

- Complete suite at `8a65e3c` before correction: **1 failed, 5,222 passed,
  2 skipped, 25 warnings in 1,746.72s (29m07s)**; the failure is R-02. This
  contradicts the section 5 claim of 5,223 passed and zero failed on that
  tree, and the later 5,224 passed claim. Those runs used a non-Store
  interpreter, so the claim is environment-dependent rather than wrong in
  intent.
- `tests/test_ml_evidence_operations.py` after correction: **49 passed,
  1 skipped in 295.56s**; the single skip is the R-02 guard, reported with its
  explicit reason.
- Import-boundary, entry-point classification, and active-document
  consistency: **98 passed in 38.24s**.
- Execution-gate precision and authorization plus execution characterization:
  **76 passed in 28.18s**.
- Dispatch-fence and cancel-all suites: **89 passed, 1 skipped**; the skip is
  the correctly gated POSIX fork test.
- Broker-binding suites (authorization binding, atomic reconciliation anomaly,
  broker order contract, coherent broker snapshot, alpaca broker):
  **263 passed, 1 skipped**.
- `compileall` exit 0; PowerShell parser 0 errors on both changed scripts;
  `git diff --check` clean.

**Mutations run, so a fix is provably load-bearing:**

- `f943bfc` reverted to per-position rounded aggregation caused
  `test_snapshot_builder_aggregates_exact_values_before_display_rounding` to
  fail with a total_equity display value of 100.01 disagreeing with exact
  evidence of 100, reproducing the claimed defect exactly. The file was
  restored clean.
- The R-02 guard predicate was boundary-tested: a real non-empty interpreter
  does **not** skip, so coverage is preserved on a provisioned host; a
  zero-byte file skips; and a **missing** interpreter does not skip, so an
  absent interpreter still fails loudly instead of being masked.

### 6.4a Validation provenance for this push

Stated precisely, so that no claim is broader than what was actually run.

The complete suite was run three times on this lane:

1. Tree at `2eb3f5d`: **5,223 passed, 3 skipped, 0 failed, 25 warnings in
   2,262.86s (37m43s)**.
2. Tree at `f5f3ec5`, run while other review work loaded the host:
   **6 failed, 5,217 passed, 3 skipped in 3,411.17s (56m51s)**. All six
   failures were `subprocess.TimeoutExpired` on PowerShell child processes in
   `tests/test_ml_evidence_operations.py`, against a code tree byte-identical
   to run 1. Re-running that file alone on an idle host gave **49 passed,
   1 skipped in 248.76s**, so the failures were host contention, not a
   regression. This is recorded as R-19 rather than dismissed, and the red
   run is reported here rather than omitted.
3. Complete code tree at `58bf2f8`, run with no competing load:
   **5,223 passed, 3 skipped, 0 failed, 25 warnings in 2,192.66s (36m32s)**.
   `compileall` exit 0 and `git diff --check` clean on that same tree.

The pushed tip is one commit beyond run 3. That commit adds this record text
only and changes no code; it was revalidated with the 63-check
active-document consistency suite and `git diff --check`. No claim here rests
on a run that predates the code it describes.

The three skips are the two pre-existing platform skips plus the R-02 guard
added by this review.

### 6.5 Residual gates and next authorized step

Codex counter-reviews every Claude commit in this range, then may begin
IB-0/IB-1 in the same combined push. R-01 requires an explicit owner decision
before it can be closed: either a preregistered tolerance that distinguishes a
material policy-input change from a price mark ticking, or an explicit
risk-reducing-sell path that does not require a byte-identical recapture.

The storage, calendar, and temporal-integrity audit that was in progress when
this section was first drafted has since completed; its findings are R-09
through R-17 above and the `9406a34` disposition was corrected from accepted
to defect-found accordingly. Of the seven P1 issues, four (R-09 to R-12) were
independently verified by this reviewer against the running system and the
code paths; R-13 was structurally confirmed at its constants and call site;
R-14 and R-15 are recorded as reported and still need independent
reproduction during counter-review.

**R-09 needs owner attention before the next operational run**, independently
of this lane: the host emergency stop is latched active by throwaway test
databases and would refuse live paper proposals, including risk-reducing
sells. It was deliberately left untouched. No SEC crawl, outcome join, ETF construction, QuantConnect job, or
broker action is authorized by this review.

## 7. Codex counter-review of Claude review commits (2026-08-28)

Counter-reviewer: Codex. Exact range reviewed in chronological order:
`b4ba4b2..17c1bb2`. Work remained on
`codex/strategy-insider-buying` in its dedicated worktree; no branch switch,
provider access, outcome access, operator-database access, or operational
mutation occurred.

### 7.1 Claude commit dispositions

| Commit | Disposition | Counter-review evidence |
|---|---|---|
| `1c1d943` | Accepted | The `lstat()` predicate matches the installer refusal boundary (reparse point or zero length), leaves missing interpreters unmasked, and the real-interpreter installer-preview test passed. |
| `2eb3f5d` | Accepted after later record completion and this counter-review correction | Every implementation commit is dispositioned and the retained ledger is substantive. The initially incomplete storage audit was corrected by later Claude commits. R-04 is a false positive and R-09 is no longer a current host condition; both are superseded below without deleting Claude's original observations. |
| `f5f3ec5` | Accepted after counter-review correction | The seven added P1 code-path findings were checked individually. R-09's live-state wording is historical now; R-10 through R-15 remain open as classified below. |
| `58bf2f8` | Accepted with clarification | The runtime namespace is structurally machine-global, so R-18's isolation mechanism is real, but the two enumerated Analyst-origin incidents cannot be re-observed because the runtime-stop file is now absent. R-19's 30-second subprocess budget is present; this counter-review did not recreate artificial host contention. |
| `17c1bb2` | Accepted | Documentation-only commit. Its exact-code-tree validation provenance is internally coherent and does not claim the record-only tip received the complete suite. |

Overall disposition: **accepted after documentation correction**. No Claude
product-code change was rejected and no shared production correction is
authorized on this lane. The only executable Claude change, R-02, remains
accepted.

### 7.2 Superseding R-01 through R-19 dispositions

This table retains every Claude identifier. It supersedes status wording where
the counter-review produced stronger evidence; it does not erase section 6.

| ID | Counter-review disposition |
|---|---|
| R-01 | **Confirmed P1, OPEN / owner decision.** The snapshot fingerprint includes current prices and market values, both submit methods recapture unconditionally, and neither path branches on side. The fail-closed direction is correct, but it can obstruct a legitimate risk-reducing sell. |
| R-02 | **Confirmed P2, FIXED in `1c1d943`.** Focused regression passed under the real non-alias virtual-environment interpreter. The guard is load-bearing on Store-alias hosts and does not weaken installer behavior. |
| R-03 | **Retained P2 as a provider-conditional hypothesis, not independently confirmed.** Stable scans require successful cancel acknowledgements for every visible ID. Whether a second cancel of `pending_cancel` is acknowledged or rejected is provider behavior; provider access is prohibited in this milestone. No code change is justified from an unverified assumption. |
| R-04 | **REJECTED - false positive.** `execute_approved_paper_proposal()` acquires `execution_dispatch_fence(store.path)` before `_execute_approved_paper_proposal_under_dispatch_fence()` opens the broker session or captures the authoritative snapshot. The adapter's later permit fence is nested same-thread re-entry over the same path, so it does not spend a second 30-second contention wait. A proposal can time out waiting for the outer fence, but it does not wait while holding the execution snapshot described by R-04. |
| R-05 | **Confirmed P3, OPEN.** The authorization layer accepts `none`, `null`, and `unknown`; stricter account and broker layers reject them. Current upstream construction prevents exploitation, but the contract remains inconsistent. |
| R-06 | **Confirmed P3, OPEN.** `activate_reconciliation_halt()` keys `broker_reconciliation:<proposal>`, while anomaly parking keys `broker_reconciliation:<proposal>:<anomaly>`. Acknowledgement behavior can therefore diverge. |
| R-07 | **Confirmed P3, OPEN.** Component disagreement raises `_TransientBrokerSnapshotMutation` and is ultimately reported as failure to stabilize. The focused regression reproduced that exact message for stable contradictory inputs. |
| R-08 | **Confirmed P3, OPEN with bounded impact.** Strict snapshot order validation passes the same `BrokerAccountIdentity` as expected and observed. Account bracketing and `expected_account_id` remain independently meaningful, so only the order-level mismatch check is tautological. |
| R-09 | **Historical P1 host condition; NOT CURRENT at counter-review.** A read-only check found the recorded runtime-stop path absent. Codex did not clear or otherwise mutate it. The earlier observation remains evidence that tests can latch global state, but there is no current file or incident set requiring the owner action claimed in section 6. Underlying mechanisms remain R-10 and R-18. |
| R-10 | **Confirmed P1, OPEN.** Runtime-stop activation occurs before and outside the `read_only` branch, and reporting/readiness callers reach it. This is a real presentation-to-execution side effect. |
| R-11 | **Confirmed P1, OPEN.** The ambiguous-dispatch gate has no side branch; its `ProposalExecutionError` is converted from `VALIDATING` to `BLOCKED`, consuming a risk-reducing sell proposal before broker contact. |
| R-12 | **Confirmed structural P1 risk, OPEN.** The hot path executes unbounded `SELECT * FROM broker_order_events` and verifies every row. Counter-review confirmed the code path but did not manufacture an operational-size ledger to claim a measured latency. |
| R-13 | **Confirmed structural P1, OPEN.** Timestamp integrity outside the five-second future tolerance activates reconciliation halt, and monitor cadence defaults to 30 seconds. No provider or unattended end-to-end run was performed. |
| R-14 | **Confirmed P1, OPEN.** Direct invocation mapped both branch-declared active statuses, `held` and `calculated`, to `submission_unknown`; that status is in readiness's critical unresolved set and in the account-wide ambiguous-dispatch gate. No test otherwise names either raw status. |
| R-15 | **Confirmed P1, OPEN.** The legacy migration authenticates the original `event_at`, rejects a naive timestamp, then rolls the migration transaction back, so reopen repeats the refusal. Separately, the stable component-disagreement fixture exhausted the retry budget and reported "did not stabilize." The runtime path ignores its database argument by design. No operator database was opened. |
| R-16 | **Confirmed P2, OPEN.** The non-strict broker/read-only builder silently normalizes a zero-share/zero-value row away, while the strict execution builder rejects it. The silent drop violates the repository's no-silent-row-dropping rule even though it cannot reach strict dispatch evidence. |
| R-17 | **Confirmed P2 test gap, OPEN.** The unsupported-order characterization fails policy validation before reservation, so its reservation assertion is vacuous and cannot protect the later `release_execution_reservation()` call. This is a test-sensitivity defect, not evidence that production currently leaks a reservation. |
| R-18 | **Confirmed structural P1, OPEN; historical incident details unavailable.** Runtime fence/stop paths deliberately ignore the database and use one OS-user namespace, so lane tests can affect sibling lanes. The exact two Analyst-origin incidents recorded by Claude are not current because the state file is absent. |
| R-19 | **Confirmed P3 test-harness risk, OPEN.** The 30-second PowerShell subprocess timeouts are hard coded. Claude's red/green load evidence is retained; this counter-review ran the focused path successfully and did not force contention merely to recreate a timeout. |

The current P1 set after counter-review is R-01, R-10 through R-15, and R-18:
eight open P1 findings. R-09 remains a retained historical host condition, not
a currently active incident; R-04 is rejected. None blocks the isolated,
offline, non-executing IB-0/IB-1 structural milestone. They do block treating
the shared execution surface as operationally cleared.

### 7.3 Counter-review verification

- Recomputed stable patch IDs for all 13 synchronized commits. Twelve match
  their main-line counterparts exactly. `800c689` intentionally differs from
  `8cab638` only by omitting the Analyst licensed-surface registration and its
  matching assertion: one added line in each of two files.
- Direct lifecycle probe: `held -> submission_unknown` and
  `calculated -> submission_unknown`; both raw statuses are declared active,
  and `submission_unknown` is critical.
- Focused offline suite covering the executable correction, provenance
  boundary, re-entrant fence, vacuous reservation characterization, legacy
  migration, and deterministic snapshot disagreement: **31 passed in
  30.88 seconds**.
- The earlier two-test subset for R-02 and R-07/R-15 also passed in 5.25
  seconds. The real R-02 installer-preview test alone passed in 6.35 seconds.
- Read-only runtime-state check: the exact file named by R-09 was absent. No
  clear, acknowledgement, database open, or state mutation was performed.
- No SEC/EDGAR/provider request, credential, licensed row, research outcome,
  QuantConnect job, broker action, operator database, scheduler, order, or
  deployment was accessed. **Research looks: 0.**

Counter-review gate: **PASS, accepted after documentation correction**. The
next authorized step is the bounded offline IB-0/IB-1 milestone only.

## 8. IB-0/IB-1 offline structural slice (2026-08-28)

This is the deliberately bounded first implementation named in section 3.
It does not claim that the full IB-0 preregistration or the full IB-1 ingest
exit gate is complete. In particular, there is no network collector,
quarterly-package schema, immutable disk publisher, security mapping, score
engine, outcome join, ETF construction, or QuantConnect algorithm.

### 8.1 Frozen contracts

`research/insider_buying/contracts.py` pins the following before any outcome
access:

- canonical inputs: Form 4/4-A source family, with original Form 4 as the
  primary row family; non-derivative common stock; code `P`; acquired `A`;
  direct ownership; officer/director; and at least $50,000 of purchase value;
- public acceptance time as availability, never transaction date. An exact
  timezone-aware timestamp carries a next-regular-open-after-acceptance rule;
  date-only metadata remains date-only and carries the more conservative
  next-regular-open-after-that-date rule;
- `ln(1 + purchase_value_usd / 50000)`, 20-trading-day half-life, and
  30-trading-day lookback;
- full event-study windows `1/5/10/20/40/60/120`, primary windows `5/20/60`,
  and the required `0/5/10/20` bps-per-side cost grid; and
- outcome access disabled and authorized outcome looks fixed at zero.

The implementation names every canonical inclusion or quarantine reason.
Form 5, Form 4/A rows, derivatives, multiple reporting owners, incomplete or
ineligible roles, any 10% owner, non-common securities, non-purchase codes,
disposals, indirect ownership, missing dates, nonpositive shares, price
ranges, missing/nonpositive prices, private purchases, 10b5-1 transactions,
sub-threshold value, and unresolved footnotes cannot silently enter V1.

### 8.2 Offline parser and lineage

`research/insider_buying/form4_xml.py` accepts only caller-supplied bytes and
caller-supplied accession/acceptance metadata. It performs no file discovery
or external access. Source bytes are capped at 2 MiB, DTD/entity declarations
are refused before parsing, and the exact byte image is SHA-256 bound to the
filing and every emitted transaction. All non-derivative and derivative
transaction rows are retained with stable row indices and named outcomes.

The in-memory corpus rejects duplicate accessions, missing amendment targets,
cross-issuer amendment links, non-original targets, and amendments that do
not follow an original when exact timestamps can establish order. It retains
both the original and every amendment and records the explicit
original-to-amendment edge; it never overwrites or deletes the as-filed row.
This is the lineage contract for the future immutable publisher, not that
publisher itself.

All four XML fixtures are synthetic and repository-local. They contain no
provider row, credential, licensed data, market outcome, or operating account
information.

### 8.3 Implementation self-review ledger

Resolved findings are retained rather than erased.

| ID | Sev | Status | Finding and disposition |
|---|---|---|---|
| IB01-R01 | P2 | **FIXED before commit** | The first focused run exposed a two-site inversion: the Form 5 input allowance had been applied to the classifier instead of the parser gate. That direction failed closed by refusing Form 5, but it prevented the required explicit `exclude_unsupported_form` record. The predicates were corrected and the Form 5 fixture now parses to exactly that named exclusion. |
| IB01-R02 | P1 | **FIXED before commit** | DTD/entity screening initially examined only the first 4 KiB. A bounded payload could pad a declaration beyond that prefix and reach the XML parser. The check now examines the complete, already size-capped byte image; a 5-KiB-padding regression verifies the boundary. |
| IB01-R03 | P1 | **FIXED before commit** | The first role predicate excluded a 10% owner only when the person was neither officer nor director. That could silently mix an officer/director carrying the 10% flag into canonical V1, contrary to the frozen lane contract. Any true 10% flag now produces `exclude_ten_percent_owner`; the combined-role regression passes. |
| IB01-R04 | P2 | **FIXED before commit** | Amendment lineage compared only acceptance dates, so equal exact timestamps were accepted. When both instants are known the amendment must now be strictly later; date-only metadata remains explicitly uncertain and conservatively date-scoped. |
| IB01-R05 | P3 | **OPEN - shared test harness, not caused by this milestone** | The first complete run timed out `test_dispatch_fence_serializes_independent_processes` while waiting five seconds for its Python child process. The same test passed alone in 2.72 seconds, its complete file passed 24 with one platform skip in 4.86 seconds, and the unchanged code tree then passed the complete suite. Like R-19, this is a load-fragile subprocess budget; unlike R-19 it is a separate five-second timeout in `tests/test_dispatch_fence.py`. No shared-test correction is authorized on this lane. |

Open findings in this new lane-owned diff: **none at P0-P3**. IB01-R05 is an
open shared test-harness finding observed during validation, not an Insider
code defect. The shared execution findings retained in section 7 remain open
and unchanged; this offline package has no import path to those surfaces.

### 8.4 Verification

- Focused structural/parser suite: **25 passed**.
- Joint-owner reverse mutation (`len(owners) != 1` weakened to `< 1`): the
  joint-owner regression failed because the row incorrectly entered V1.
- Amendment reverse mutation (amended-form predicate reversed): the lineage
  regression failed because the amendment incorrectly entered V1.
- Both mutations were reverted with patches; the complete focused suite then
  returned to **25 passed**.
- Package compileall: exit 0. `git diff --check`: clean.
- First complete run: **1 failed, 5,248 passed, 2 skipped, 25 warnings in
  3,085.83 seconds (51m25s)**. The only failure was the five-second
  subprocess timeout retained as IB01-R05; it was not omitted.
- Immediate reproduction on the unchanged tree: the exact timed-out test
  passed in 2.72 seconds, then all of `tests/test_dispatch_fence.py` passed
  **24 tests with 1 platform skip** in 4.86 seconds.
- Clean complete rerun on the unchanged code tree: **5,249 passed, 2 skipped,
  0 failed, 25 warnings in 4,204.91 seconds (1h10m04s)**.
- Final focused plus active-document suite: **88 passed** in 4.84 seconds.
  Whole-repository compileall exited 0; staged `git diff --check` was clean;
  the staged file list contains only the lane-owned package, synthetic
  fixtures, tests, and this record; and the branch remained
  `codex/strategy-insider-buying` in its dedicated worktree. A final read-only
  check also confirmed the machine-global runtime-stop file remained absent.

Research-look ledger for this milestone: **0**. No outcomes were loaded or
computed, and no SEC/provider, credential, licensed row, QuantConnect,
broker, operator database, scheduler, deployment, or order surface was
accessed.

## 9. Claude review - counter-review response and IB-0/IB-1 slice (2026-08-28)

Numbering note: the immutable 2026-08-28 Claude push-ledger row refers to this
review as section 8 and its validation as section 8.6. Renumbering the duplicate
heading makes those references resolve to section 9 and section 9.6.

Reviewer: Claude, Insider Buying lane review session, same dedicated worktree.
Range reviewed: `17c1bb2..65494fb` (`4e51e14` counter-review, `65494fb`
IB-0/IB-1 implementation). Ancestry verified: `17c1bb2` is an ancestor of
`65494fb`, so no published history was rewritten. No `git switch`, no other
lane, checkout, or branch touched.

### 9.1 Isolation verification

Frozen files were re-checked individually across the range: the Action Plan,
Session Handoff, direction record, parallel workflow, Strategy Description
README, data-source register, `requirements.txt`, and `config.py` are all
untouched, and neither sibling lane record was modified. New code lives only
in lane-owned namespaces (`research/insider_buying/`,
`tests/fixtures/insider_buying/`, `tests/test_insider_buying_form4.py`), so
the eventual merges cannot collide. No SEC, EDGAR, vendor, QuantConnect,
credential, broker, operator-database, or scheduler access occurred.
**0 research looks.**

### 9.2 Commit dispositions

| Commit | Subject | Disposition |
|---|---|---|
| `4e51e14` | Counter-review Claude insider lane review | **Accepted after correction.** Its R-04 rejection is correct and is adopted. Its R-09 and R-18 downgrades rest on a false-absent file reading and are reversed below (R-20). |
| `65494fb` | Implement Insider Form 4 structural contracts | **Accepted after correction.** Faithful to the blueprint; one confirmed test-coverage defect corrected here (R-21). |

### 9.3 Counter-review dispositions accepted

- **R-04 rejection is correct and adopted.** Verified independently:
  `execute_approved_paper_proposal` acquires `execution_dispatch_fence` at
  `assistant/execution_service.py:737` **before** delegating to
  `_execute_approved_paper_proposal_under_dispatch_fence` at `:738`, which is
  where the broker session opens and the authoritative snapshot is captured. A
  proposal can therefore wait for the fence, but it does not wait while
  holding a snapshot, so the two 30-second budgets do not stack as R-04
  claimed. R-04 is **withdrawn as a false positive**; the original observation
  is retained above rather than deleted.
- The counter-review's confirmations of R-01, R-05 through R-08, R-10 through
  R-17, and R-19 are accepted as scoped, including its correct narrowing of
  R-03 to a provider-conditional hypothesis that must not be "fixed" on an
  unverified assumption.

### 9.4 New findings

| ID | Sev | Status | Issue |
|---|---|---|---|
| R-20 | P1 | **OPEN - counter-review finding reversed on fresh evidence** | The counter-review downgraded R-09 to "historical, NOT CURRENT" and weakened R-18 to "historical incident details unavailable", both on the basis that the runtime-stop file is absent. **The file is present and the condition is live.** Read through `runtime_emergency_stop_path()` and parsed directly: `active: true`, `generation: 19`, **19 open incidents**, up from 17 at the previous review, so it is still accumulating. **All three analyst-lane-origin incidents that the counter-review said could not be re-observed are still enumerable**, including `...\\codex_arv2_full_tmp\\test_real_process_crash_mid_tr0\\` and `...\\trading_agent_analyst_revisions\\.codex-test-tmp-counter-review\\`. The most likely cause of the false reading is a shell-level path check reporting absent for a file that Python resolves and opens successfully; this reviewer hit exactly that discrepancy on the same path earlier and only avoided the wrong conclusion by re-checking through the resolver. R-09 is therefore restored to a **current** condition requiring owner action, and R-18's evidence stands as originally recorded. Nothing was cleared or mutated. |
| R-21 | P2 | **FIXED - this review** | Every guard in `PublicAvailability.__post_init__` was unprotected by tests. A mutation sweep neutralised all five in turn - the timezone-aware requirement, the accepted-date/instant agreement check, both execution-rule consistency checks, and the date-only "carries no instant" check - and the suite stayed green at 25 passed each time. The existing availability tests reach these semantics through `parse_form4_xml`, so they pin the parser's refusals (`Form4ParseError`) and not the contract's own (`ContractError`). This matters because `PublicAvailability` is the object encoding the look-ahead invariant, and the blueprint's IB-1 bulk-dataset ingest constructs availability from the SEC quarterly tables **without** passing through the XML parser, so on that path these guards are the only protection. Corrected by adding seven direct contract-boundary tests, including a positive case so the guards cannot be satisfied by refusing everything. Re-running the sweep afterwards reports all five mutations **caught**. |

### 9.5 Assessment of the IB-0/IB-1 slice

The implementation is faithful to the governing blueprint. `CANONICAL_SPEC`
pins forms `4`/`4-A`, transaction code `P`, acquired indicator `A`, direct
ownership, the $50,000 minimum, `ln(1 + purchase_value / 50000)`, the
20-trading-day half-life, the 30-trading-day lookback, horizons
`1/5/10/20/40/60/120` with primaries `5/20/60`, and the `0/5/10/20` bps cost
grid - each matching the PDF. It also encodes `outcomes_authorized=False` and
`authorized_outcome_looks=0`, so the look budget is a code-level invariant
rather than only a prose commitment.

Dangerous directions are covered by named tests rather than assumed: the
transaction date can never become availability, an exact acceptance instant
does not authorize same-instant execution, date-only evidence keeps its
uncertainty and the next-open rule, Form 5 can never enter the canonical
family, indirect ownership and ten-percent owners are named exclusions rather
than silent drops, a joint-owner filing emits one economic event without
value multiplication, amendment lineage retains both as-filed versions, an
amendment without an original is refused without deleting it, and duplicate
accessions are refused even for identical bytes. Ambiguous footnotes and
unknown references are retained as named outcomes, consistent with the
blueprint's fail-closed quarantine rule.

XML handling is hardened rather than trusting the source: DTD and entity
declarations are refused before parsing and input is capped at 2 MiB, and an
AST test asserts the package imports no provider, outcome, execution, or
scheduler module. Verified by execution: the lane suite passes, and the
`ml` import-boundary and entry-point classification suites remain green.

Not audited at line level, and therefore stated rather than implied: the
detailed footnote-adjudication branches and the amendment-lineage helpers
beyond the behaviours the named tests exercise.

### 9.6 Validation performed by this review

- Lane suite before correction: **25 passed**; after adding the R-21 tests:
  **32 passed**.
- Combined lane, `ml` import-boundary, entry-point classification, and
  active-document suites: **130 passed in 51.20s**.
- Mutation sweep of the five `PublicAvailability` guards: **all five survived
  before the correction, all five caught after it**, with
  `research/insider_buying/contracts.py` restored to its original content by a
  `finally` block and confirmed clean by `git status` afterwards.
- Independent re-verification of the runtime-stop condition through
  `runtime_emergency_stop_path()`, read-only: present, active, generation 19,
  19 open incidents, 3 of analyst-lane origin.
- Complete suite on the code tree at `f4257de`, run with no competing load:
  **5,255 passed, 3 skipped, 0 failed, 25 warnings in 2,347.37s (39m07s)**.
  `compileall` (including `research/`) exit 0 and `git diff --check` clean on
  that same tree. The pushed tip adds only this validation sentence and was
  revalidated with the 63-check active-document suite.

### 9.7 Residual gates and next authorized step

Eight P1 issues remain open on the shared execution surface: R-01, R-10
through R-15, and R-18, plus R-20 restoring R-09 to current. None is corrected
on this lane, because all are shared execution semantics synchronized from
`main`; correcting them here would diverge this lane from `main` and from the
sibling lanes. They do not block further offline, non-executing IB work, but
they do block treating the shared execution surface as operationally cleared.

**R-20 needs owner attention independently of this lane**: the host runtime
stop is latched active and still accumulating, and the counter-review's
statement that no action is required rests on a reading this review could not
reproduce.

Next authorized step: Codex counter-reviews these Claude commits, then may
continue the IB ladder. No SEC crawl, outcome join, ETF construction,
QuantConnect job, or broker action is authorized.

## 10. Codex counter-review and bounded IB-1A raw snapshot (2026-08-29)

Codex reviewed the exact Claude range `65494fb..d8561c1` in chronological
order, then implemented one bounded next milestone in the same dedicated
worktree and branch. Sections 8 and 9 remain the historical records of what
each prior agent claimed at its snapshot. Where those sections conflict with
the governing PDF, the current contract in section 1 and the corrections in
this section supersede them.

Owner scope direction for this lane is now explicit: it is for the Insider
Buying strategy and its eventual QuantConnect tests only. Trading App and
Streamlit implementation are out of scope here. The existing shared-surface
findings are dispositioned below because the required counter-review cannot
omit them; no shared application or UI code is changed by this round.

### 10.1 Claude commit dispositions

| Commit | Disposition | Counter-review basis |
|---|---|---|
| `f2875fd` | **Accepted.** | The seven direct `PublicAvailability` contract tests close R-21 in the dangerous direction and weaken no production guard. |
| `f4257de` | **Defect found; accepted after this documentation correction.** | The record faithfully described Claude's work, but its current-contract assessment contradicted the PDF on dual-role 10% owners, private code-`P` purchases, 10b5-1 treatment, and the point at which the $50,000 gate applies. It also created a second section 8. The historical claims are retained, the current contract is corrected, and the Claude section is renumbered to section 9. |
| `d8561c1` | **Accepted as validation of the prior exact tree only.** | The complete-suite result remains valid evidence for `f4257de`; it does not validate the corrections or IB-1A files added after that snapshot. This round therefore runs its own exact-tree validation. |

R-20 does not authorize a shared-lane fix. Its reported runtime-stop state was
read-only operational evidence, not an Insider strategy defect, and it has no
import path into this offline package. Codex's Python-resolver check at the
start of this round returned no active stop and no incident set, so Claude's
specific live-state observation was not reproducible on the later host state.
The broader shared-surface issues remain historical/open in sections 7 and 9;
under the owner's narrowed lane scope they are not implementation work here.

### 10.2 Counter-review and implementation findings

All resolved findings remain recorded rather than erased.

| ID | Sev | Status | Finding and disposition |
|---|---|---|---|
| IB-CR-01 | P2 | **FIXED** | The prior classifier excluded every 10% owner and treated private code-`P` purchases and 10b5-1 signals as exclusions. PDF pages 6 and 12 instead retain officer/directors who also hold the 10% flag, retain private purchases for later flagged robustness work, and retain 10b5-1 as a feature. Pure 10% owners with no officer/director role still fail closed. Structured 10b5-1 true/false/absent and non-semantic footnote mentions are now distinct. |
| IB-CR-02 | P2 | **FIXED** | `PublicAvailability` accepted type-confused dates, enums, and instants. Exact type checks and direct regressions now protect the bulk-ingest construction path as well as the XML parser. |
| IB-CR-03 | P2 | **FIXED** | Raw byte scanning could be bypassed with UTF-16 DTD/entity input. The parser now accepts only a bounded UTF-8 byte image, checks the decoded image for DTD/entity declarations, requires any XML encoding declaration to name UTF-8, and parses that same decoded image. |
| IB-CR-04 | P3 | **FIXED** | The record had two section 8 headings and overstated the current contract. The Claude section is section 9 and this section supplies the superseding dispositions. |
| IB1A-R01 | P1 | **FIXED before commit** | The $50,000 minimum was applied to individual XML rows, contradicting the PDF's same-owner/security/date aggregation rule. XML rows now stop at a named pre-aggregation eligibility state, the frozen key and post-aggregation gate are explicit, and two same-date $30,000 lots remain distinct and eligible for a later $60,000 aggregate. |
| IB1A-R02 | P2 | **FIXED before commit** | The first raw-package draft required exactly eight non-empty TSVs and invented one direct SEC ZIP directory. The PDF allows up to eight and identifies three core joins. The boundary now accepts a unique allowed subset containing `SUBMISSION.tsv`, `REPORTINGOWNER.tsv`, and `NONDERIV_TRANS.tsv`, preserves allowed empty raw members, canonicalizes manifest order, and validates an exact SEC HTTPS host plus a quarter-matching ZIP filename without claiming an unaudited directory route. |
| IB1A-R03 | P2 | **FIXED before commit** | Self-review found integrity and recovery gaps around same-byte manifest parsing, file replacement, post-link failures, temporary files, concurrent retry, and commit-marker ordering. The loader now reads bounded regular-file byte images and rechecks identity/version; publication writes immutable archive and manifest members before the commit marker, settles failures according to whether a valid commit exists, preserves any observed committed set, removes only byte-verified publisher temporaries, and refuses foreign residue. |
| IB1A-R04 | P2 | **FIXED before commit** | Eligibility-bearing XML values were too permissive or insufficiently bounded. Dates, decimals, booleans, form types, transaction codes, CIKs, and footnote references now use exact fail-closed lexical contracts; bounded exact decimal multiplication avoids ambient-context rounding. |
| IB1A-R05 | P2 | **FIXED before commit** | Archive hardening now rejects nested, redirected, encrypted, unsupported-compression, duplicate, case-colliding, NUL-truncated, oversized, over-expanded, extreme-ratio, corrupt, non-UTF-8, and NUL-containing members before publication. A crafted `ZipInfo` raw name can no longer truncate into an allowed table name. |
| IB1A-R06 | P3 | **FIXED before commit** | Mutation review found missing sensitivity for bounded exponent notation, persisted empty tables, abrupt pre-commit interruption, distinct lot IDs, and scrambled ZIP order. Exact regressions now kill those dangerous-direction changes and preserve deterministic lot and package lineage. |
| IB1A-R07 | P2 | **DISPOSITIONED by explicit trust boundary** | Publication refuses pre-existing symlinks, junction/reparse points, and non-regular files and serializes cooperative writers. Its path checks are not directory-handle-bound against a hostile actor swapping path components between checks. IB-1A therefore requires a caller-controlled output root with no untrusted concurrent filesystem mutation and does not claim adversarial local-race resistance. |
| IB1A-R08 | P3 | **FIXED before commit** | A late mutation pass exposed missing direct sensitivity for non-UTC retrieval canonicalization, exact reporting-owner CIK/name/title and two relationship-flag types, and returning the recovered identity after a transient post-commit contract failure. Seven direct regressions close those gaps. The exact-current rerun killed all 13 late-refactor mutations and all four rechecked high-risk edge mutations. |

### 10.3 IB-1A implemented boundary

`research/insider_buying/sec_bulk_snapshot.py` is a caller-supplied-bytes-only
boundary for one SEC quarterly Insider Transactions ZIP. It performs no
discovery or network request. It validates the bounded archive and allowed raw
TSV inventory, computes the archive SHA-256 plus exact per-member SHA-256,
size, CRC, and compression metadata, and publishes an immutable raw snapshot
whose lineage includes year, quarter, asserted full source URL, retrieval
instant, caller-declared full Git SHA, archive identity, member inventory, and
raw-contract version. `archive_sha256` identifies the exact ZIP bytes;
`lineage_hash` and `snapshot_id` identify the complete declared lineage bundle.
The Git SHA is syntax-validated provenance supplied by the caller, not a claim
that this module queried a repository.

The commit marker hashes the immutable archive and manifest and is published
last. The loader requires the exact three-file set, canonical JSON, matching
commit hashes, matching directory/snapshot identity, exact manifest fields,
canonical member order, and a complete rebuild of the archive identity before
returning bytes. The raw contract intentionally does not claim a parsed-table
schema or parser version; those belong to IB-1B.

The XML fixture parser was corrected in this same counter-review round because
its row dispositions feed the next ingest stage. It still parses only supplied
fixtures/bytes and emits no canonical aggregated event. Private-value capping,
joint-owner attribution, security identity, normalized lot aggregation, and
the post-aggregation $50,000 decision remain deferred.

### 10.4 Verification and isolation

- Exact-current focused Form 4 plus raw-snapshot suite: **166 passed, 4
  platform skips**. The skips are Windows hosts without symlink-creation
  privilege; deterministic simulated reparse-point and Windows attribute
  tests execute and pass independently of those skips.
- Exact committed snapshot `82d048c`: the combined Insider/import-boundary/
  entry-point/active-document suite passed **266 tests with 4 platform skips
  in 20.91 seconds**. Whole-repository compileall exited 0. The complete suite
  passed **5,390 tests with 6 skips, 0 failures, and 26 warnings in 1,053.88
  seconds (17m33s)**. The warnings were one `websockets.legacy` deprecation,
  one joblib physical-core fallback, and 24 NumPy shape deprecations from
  existing ML tests.
- Independent PDF cross-check and exact-current P0-P3 self-review found no
  remaining code finding after the corrections above. The final mutation
  audit established a **166-passed/4-skipped baseline**, killed **13 of 13**
  late-refactor mutations and **4 of 4** rechecked high-risk edge mutations,
  and reported zero material survivors. All six changed/new Python files
  compiled successfully; `git diff --check` was clean apart from line-ending
  notices.
- No SEC/EDGAR/provider request, credential, licensed row, research outcome,
  QuantConnect job, broker, operator database, scheduler, deployment, order,
  Trading App, or Streamlit surface was accessed or changed. **Research looks:
  0.**
- A post-suite read-only Python-resolver check found the shared runtime-stop
  file absent and returned inactive, generation 0, zero incidents, and no
  integrity error. Nothing was cleared, acknowledged, or written.

### 10.5 Residual gates and next bounded milestone

IB-1A is not the full IB-1 exit gate and it is not a downloader. The next
bounded milestone is **IB-1B: offline explicit-schema TSV parsing from a
verified committed raw snapshot**. It must preserve identifier columns as
strings, retain every raw field and Forms 3/5, bind each row/table to the raw
snapshot and a parser version, build accession-level table lineage without
multiplying transaction rows by owner rows, and publish an immutable parsed
snapshot.

The immediate action is not IB-1B: Codex must finish exact-tree validation,
make the one combined push for this counter-review plus IB-1A round, and stop
for Claude's independent review of that pushed snapshot. IB-1B may begin only
in the following Codex round, together with Codex's counter-review of every
Claude commit from the pending review, and only if that review leaves no owner
decision blocking the milestone.

Network/EDGAR enrichment, multi-owner attribution, security resolution,
normalized lot aggregation, the canonical $50,000 aggregate gate, outcomes,
signals, ETF construction, and QuantConnect strategy tests remain deferred to
their ordered milestones. This lane's eventual executable scope is
QuantConnect testing of the Insider Buying strategy only; it grants no paper
or live deployment, broker, order, or Trading App/UI authority.

## 11. Claude review - IB-1A raw snapshot boundary (2026-08-29)

Reviewer: Claude, Insider Buying lane review session, same dedicated worktree.
Range reviewed: `d8561c1..df1b7d4` (`8107915` IB-1A implementation, `82d048c`
counter-review record, `df1b7d4` validation record). Codex worked on a
different machine this round; the branch was synced by fast-forward only after
confirming `d8561c1` is an ancestor of `df1b7d4`, so no published history was
rewritten. No `git switch`; no other lane, checkout, or branch touched.

### 11.1 Isolation verification

Frozen files were re-checked individually across the range and are all
untouched: Action Plan, Session Handoff, direction record, parallel workflow,
Strategy Description README, data-source register, `requirements.txt`,
`config.py`, and both sibling lane records. New code remains in lane-owned
namespaces. Nothing under `assistant/`, `execution/`, `risk/`, or `scripts/`
imports `research.insider_buying`, so the new module has no execution-side
coupling. No SEC, EDGAR, vendor, QuantConnect, credential, broker,
operator-database, or scheduler access occurred. **0 research looks.**

`sec_bulk_snapshot.py` imports `ml.immutable_io` for
`publish_immutable_bytes` and `exclusive_file_lock`. This is reuse of an
existing artifact helper rather than a parallel implementation, which the
repository rules prefer, and the `ml` import-boundary and entry-point
classification suites pass (35 passed). Recorded as R-23 below only as
architectural debt, not a violation.

### 11.2 Counter-review findings against Claude accepted

Three defects the counter-review raised against this reviewer are confirmed
and accepted without reservation. Each is a genuine miss, recorded plainly:

- **Dual-role ten-percent owners.** Section 9 called the classifier faithful
  to the blueprint while it excluded every ten-percent owner. PDF page 6 says
  ten-percent owners are excluded *unless they are also an officer or
  director*. This reviewer verified the frozen numeric constants against the
  PDF but did not cross-check the role logic, so an over-exclusion was
  described as correct. The replacement is stricter, not looser: pure
  ten-percent owners still fail closed, and dual-role owners now carry an
  explicit diagnostic.
- **Placement of the $50,000 gate.** The minimum was applied to individual XML
  rows, contradicting the PDF's same-owner/security/date aggregation rule.
  This reviewer checked that the constant equalled $50,000 but not *where* it
  was applied. Verified fixed: the frozen spec now carries
  `lot_aggregation_key` and `minimum_purchase_value_applies_after_aggregation`,
  and a regression proves two same-date $30,000 lots stay distinct and
  aggregate to $60,000 before the gate.
- **UTF-16 DTD bypass.** This reviewer confirmed that `<!DOCTYPE` and
  `<!ENTITY` were refused on raw bytes and stopped there, without asking
  whether a different encoding defeats a byte-level scan. It did. Verified
  fixed by direct probe: a UTF-16 payload carrying a DTD is refused with
  `REFUSED: Form 4 XML must be UTF-8 encoded`, and a UTF-8 DTD is still
  refused by the entity prohibition. Narrowing the accepted input domain is
  the right shape of fix.

Two prior Claude tests were removed in this range. Both were checked and both
removals are legitimate: `test_ten_percent_owner_is_separate_even_when_also_an_officer`
encoded the over-exclusion above and was replaced by four stricter tests, and
`test_canonical_fixture_includes_exactly_one_hashed_decimal_row` was renamed to
`..._has_one_structurally_eligible_hashed_decimal_row` with its hash, decimal,
and value assertions intact. All seven `PublicAvailability` tests added by this
reviewer survive unmodified. Test count rose from 29 to 54 in that file. **No
test weakening found.**

### 11.3 Counter-review fixes independently verified

- **IB-CR-02 type confusion** is genuinely closed, including the subtle case:
  a `datetime` passed as `accepted_date` is refused with "accepted_date must
  be an exact date". A naive `isinstance(value, date)` check would have
  admitted it, because `datetime` subclasses `date`. Verified by direct probe.
- **IB-CR-03** verified as described above.
- **IB1A-R01** verified as described above.

### 11.4 New findings

| ID | Sev | Status | Issue |
|---|---|---|---|
| R-22 | P2 | **OPEN - process finding, both parties correct** | The R-09/R-20 disagreement is resolved and neither party was wrong. The runtime execution stop is stored under `%LOCALAPPDATA%`, so it is **per-user, per-machine state that no git operation synchronizes**. Codex reviewed from a different machine this round and correctly observed no stop on its host; this reviewer correctly observes one on this host. Re-verified during this review: present, `active: true`, **generation 21, 21 open incidents**, up from 19 last round and 17 before that, so it is still accumulating with each suite run. The operationally significant host is this one, because the operational clone and operator database live here. The process consequence is general and should outlive this finding: **a counter-review performed on a different machine cannot confirm or refute any host-local operational condition**, and a "not reproducible" verdict from another host must not be recorded as evidence that the condition is absent. R-09 and R-20 stand as scoped to this host. Nothing was cleared or mutated. |
| R-24 | P3 | OPEN - stated, deliberately not "fixed" here | A mutation sweep neutralised each of the 80 `REFUSED` raise sites in `sec_bulk_snapshot.py` in turn: **39 caught, 41 survived, 0 syntactically invalid**. The survivors are not evidence that the module's integrity claims are unproven, and this reviewer's first reading of them as such was an overstatement corrected before recording. The externally reachable properties are covered by named behavioural tests: content-to-hash-and-identity binding, refusal of corrupt/truncated/non-ZIP input, idempotent exact retry with provenance-sensitive identity, a committed corrupt member never overwritten by retry, and a hash-valid but mislabelling member manifest unable to relabel raw bytes. The 41 survivors concentrate in redundant internal validation and in fault-recovery paths reachable only under injected failure, such as the commit-marker recovery branch. The honest statement is therefore about test *depth*, not about a broken trust boundary: slightly over half the individual refusal sites could be deleted without any test noticing, so a future refactor could silently thin the defence in depth. Writing 41 tests is out of a reviewer's surgical scope; the useful subset for Codex is the fault-injection recovery branch around commit-marker recovery and final integrity verification. |
| R-23 | P3 | OPEN | `research/insider_buying/sec_bulk_snapshot.py` depends on `ml.immutable_io`. Reusing the existing immutable-publication helper is correct and the import-boundary tests pass, but a general-purpose artifact-publication primitive living under `ml/` means a non-ML research lane must import `ml` to obtain it, and the other two lanes will face the same choice. Worth relocating to a neutral module during integration rather than on a lane branch. |

### 11.5 Assessment of the IB-1A slice

The module is an offline raw-snapshot boundary and behaves like one. It
performs no network access: the imports are `codecs`, `hashlib`, `io`, `json`,
`os`, `re`, `stat`, `zipfile`, `zlib`, plus the repository's own hashing and
immutable-IO helpers, with the SEC URL used only as a validated provenance
string. Provenance is checked rather than trusted: the source URL must be
canonical HTTPS `sec.gov`, the year and quarter must agree with the ZIP
filename, the year must be 2006 or later and the quarter 1 to 4, the source
commit must be a full lowercase SHA-1, and the retrieval time must be
timezone-aware and representable in UTC. Member manifests validate table
names, hashes, sizes, and CRCs. Conflicting publication at an immutable path
is refused rather than overwritten.

Not audited at line level, and therefore stated rather than implied: the ZIP
member extraction paths beyond the behaviours the named tests exercise, and
the interaction between `exclusive_file_lock` and concurrent publication on
this Windows host.

### 11.6 Validation performed by this review

- IB-1A and Form 4 suites together: **166 passed, 4 skipped in 21.87s**.
- `ml` import-boundary and entry-point classification: **35 passed in 24.38s**.
- Active-document consistency: **63 passed**.
- Direct probes, all read-only: UTF-16 and UTF-8 DTD refusal, three
  `PublicAvailability` type-confusion cases, and the runtime-stop state through
  `runtime_emergency_stop_path()`.
- Mutation sweep of all 80 `REFUSED` raise sites in `sec_bulk_snapshot.py`:
  **39 caught, 41 survived, 0 invalid**, with the file restored by a `finally`
  block and confirmed clean by `git status` afterwards. Interpretation is in
  R-24; the first sweep's summary counts were lost to this reviewer's own
  output truncation and the sweep was rerun in full rather than quoting an
  unread figure.
- Complete suite on the code tree at `76f0c21`, run with no competing load:
  **5,389 passed, 7 skipped, 0 failed, 25 warnings in 1,591.75s (26m31s)**,
  with `compileall` (including `research/`) exit 0 and `git diff --check`
  clean on that same tree. The pushed tip adds only this validation sentence
  and was revalidated with the 63-check active-document suite. The seven skips
  are the two pre-existing platform skips, the R-02 Store-alias guard, and
  four IB-1A platform-conditional skips.

### 11.7 Residual gates and next authorized step

The shared-execution-surface P1 set is unchanged and uncorrected on this lane:
R-01, R-10 through R-15, and R-18, with R-09/R-20 scoped to this host per
R-22. The IB ladder remains at IB-1A; no ingest of real SEC data, outcome
join, ETF construction, QuantConnect job, or broker action is authorized.

Next authorized step: Codex counter-reviews these Claude commits, then may
continue the bounded IB ladder.

## 12. Codex counter-review and bounded IB-1B parsed snapshot (2026-08-29)

Codex fast-forwarded the dedicated Insider worktree from `df1b7d4` to the
remote tip `8d9e70b`, without switching branches or creating another
worktree. The exact Claude range contained two documentation-only commits:
`76f0c21` and `8d9e70b`. This section supplies the commit-by-commit verdicts
missing from section 11, corrects one reproduced IB-1A recovery defect, and
records the next single bounded implementation milestone.

The owner's narrowed lane scope remains controlling. Only Insider strategy
research code, its offline synthetic tests, and this record changed. The
shared runtime/UI observations had to be dispositioned because they appear in
the required review record, but they did not authorize Trading App, Streamlit,
broker, scheduler, or shared-execution work on this lane.

### 12.1 Claude commit dispositions and record correction

| Commit | Disposition | Counter-review basis |
|---|---|---|
| `76f0c21` | **Accepted after correction in this round.** | Its substantive checks of the PDF corrections and IB-1A boundary were largely sound, but it omitted the required disposition for each reviewed Codex commit and an overall verdict, left the authoritative status stale, overstated caller-asserted provenance as checked rather than syntax/consistency-validated, and described R-24 as test depth without finding the reproducible hard-restart defect below. |
| `8d9e70b` | **Accepted as validation of the prior tree only.** | The recorded 5,389-passed/7-skipped complete run is coherent evidence for the code tree at `76f0c21`; the later commit changes only this record. It does not validate the current recovery correction, IB-1B code, or current counter-review text. |

Section 11 said “full dispositions” were present but did not state them. The
superseding dispositions for its reviewed Codex commits are:

| Reviewed Codex commit | Corrected Claude-review disposition |
|---|---|
| `8107915` | **Accepted after the hard-restart correction in this round.** Its intended IB-1A boundary is retained; exact uncommitted publication residue no longer poisons a same-input retry. |
| `82d048c` | **Accepted after this documentation correction.** Its prior counter-review content remains valid, but Claude's review needed the explicit verdict recorded here. |
| `df1b7d4` | **Accepted only as validation of the prior exact tree.** It cannot validate later review or implementation commits. |

The Claude ledger row was inserted before an already-present Codex validation
row despite the append-only instruction. History is not rewritten; this
ordering error is recorded here and all new rows are appended.

### 12.2 Counter-review findings and dispositions

| ID | Sev | Status | Finding and disposition |
|---|---|---|---|
| IB1B-CR-01 | P2 | **FIXED** | A real process/power loss after linking exact `archive.zip`, `manifest.json`, or a publisher temporary but before the commit marker left a target that every retry refused as incomplete. The old `KeyboardInterrupt` test exercised the in-process `BaseException` cleanup and did not model restart. Retry now first verifies the complete residue set, removes only a wholly byte-exact expected set, and republishes with the commit marker last. Mixed exact plus mismatched/foreign residue is refused and preserved in full. |
| IB1B-CR-02 | P2 | **FIXED IN RECORD** | Section 11 omitted mandatory commit-by-commit dispositions and an overall acceptance verdict, while the top status still said review pending. Section 12.1 and the current status supply the authoritative correction. |
| IB1B-CR-03 | P3 | **CORRECTED IN RECORD** | IB-1A validates the syntax and internal consistency of caller-asserted source URL, retrieval time, and Git SHA; it does not authenticate SEC origin, retrieval time, or repository provenance. Exact archive/member integrity and declared lineage are checked. |
| IB1B-CR-04 | P3 | **RECORDED** | The Claude ledger row was not appended in chronological order. No prior row was moved or rewritten. |
| IB1B-CR-05 | P3 | **DISPOSITIONED / NO LANE FIX** | R-22 correctly establishes that runtime-stop observations are per-user/per-machine. Claude's generation-21 observation remains historical evidence scoped to its host; this host cannot confirm or refute that state. It is unrelated to the offline Insider parser and grants no shared runtime mutation authority. |
| IB1B-CR-06 | P3 | **DEFERRED TO INTEGRATION** | R-23 correctly notes that the product-neutral immutable helper resides under `ml`. The current lane continues using the reviewed helper; relocating shared structure would exceed the owner-scoped Insider milestone. |
| IB1B-CR-07 | P3 -> P2 concrete case | **FIXED** | R-24's broad 39/41 mutation count has no durable per-site ledger, but its suggested recovery area contained the concrete hard-restart defect in IB1B-CR-01. Targeted restart, exact-temp, mixed-residue, final-verification, lock-failure, and retry tests now pin the dangerous external properties; no claim is made that every internal refusal site has a direct test. |
| IB1B-R01 | P2 | **FIXED BEFORE COMMIT** | The first parser draft generated an ordinal row ID but did not preserve or validate the SEC transaction surrogate named by the PDF. Schema variants now declare caller-asserted source-row key headers that must be separately audited, transaction variants require them, rows persist their exact string projection, and duplicate, empty, or whitespace-only accession-relative transaction keys refuse. No live header name was guessed and this boundary does not authenticate the caller's choice. |
| IB1B-R02 | P2 | **FIXED BEFORE COMMIT** | A positional row representation alone did not make the no-cartesian-join invariant visible. The accession artifact now carries separate ordered row-ID arrays for each present table and is rebuilt semantically by the loader; two owners plus one transaction stay two plus one. |
| IB1B-R03 | P2 | **FIXED BY CONTRACT** | The strategy PDF names key columns but not an exhaustive 2006-present ordered header registry, and later 10b5-1 metadata makes a timeless tuple unsafe. The API has no default schema and requires caller-supplied exact, quarter-bounded, non-overlapping variants. Synthetic test fixtures are labelled non-official. |
| IB1B-R04 | P2 | **FIXED BEFORE COMMIT** | Hash-only loading could have treated consistently rehashed values or a cross-linked accession index as self-validating. The public loader now requires the claimed committed raw snapshot, runs the IB-1A loader, deterministically reparses under the persisted profile/parser provenance, and compares the full identity, rows, source keys, table counts, and accession index. A wrong raw snapshot and a forged cross-link with every ordinary parsed hash and directory identity recomputed both refuse. |
| IB1B-R05 | P2 | **FIXED BEFORE COMMIT** | The parsed publisher needed the same restart model discovered in IB-1A. Exact rows/accessions/manifest prefixes and publisher temporaries recover after restart; a mixed unverified set is preserved and refused before any deletion. Commit observation remains the no-rollback boundary. |
| IB1B-R06 | P3 | **FIXED BEFORE COMMIT** | Malformed unhashable artifact/row names could escape as raw `TypeError`, impossible zero-byte table identities were loadable, and OS lock failures lacked precise domain translation. Public loader/writer regressions now require fail-closed `SecBulkParsedSnapshotError`/`SecBulkSnapshotError` results and distinguish target I/O from lock entry/exit. |
| IB1B-R07 | P2 | **FIXED BEFORE COMMIT** | Reusing IB-1A's multi-gigabyte expanded limits with in-memory parsed dataclasses/JSONL could exhaust memory. IB-1B adds explicit per-table and total input, header, field, row, manifest, and artifact caps, tested before publication. The parsed output root is also forbidden from being the raw snapshot or its descendant. |
| IB1B-R08 | P3 | **DISPOSITIONED / EXPLICIT GATE** | The bounded in-memory implementation is not evidence of capacity for the largest historical/live package. Streaming publication and real-package capacity remain a separately reviewed gate, alongside the missing audited official schema registry. |

### 12.3 IB-1B implemented boundary

`research/insider_buying/sec_bulk_parsed_snapshot.py` implements offline,
explicit-schema parsing from a path to a committed IB-1A snapshot. It calls
the public raw loader before reading any table and exposes no arbitrary-ZIP or
network API. A caller must provide an immutable `SecTsvSchemaProfile`; there
is no default and no bundled “official SEC” profile. Each variant freezes an
exact ordered uppercase header vector, an inclusive non-overlapping quarter
range, and caller-declared source-row key headers that require a separate
source audit. The local strategy PDF lists key
fields but not the complete historical ordered SEC dictionary, so synthetic
test headers are not represented as live compatibility evidence.

The fixed TSV dialect is strict UTF-8-with-optional-leading-BOM, tab-delimited
CSV with doubled quotes and logical records. Every present table must match
the one profile variant valid for its quarter. Zero-byte members, ragged or
blank logical records, malformed quoting, unknown/reordered/case-shifted
headers, noncanonical accessions, duplicate submissions, orphan child rows,
blank transaction source keys, and duplicate accession-relative transaction
source keys fail closed. Header-only tables may contain zero data rows. Every
field remains a string; leading zeros, decimal scale, empty strings, Unicode,
quoted tabs/newlines, Forms 3/3-A and 5/5-A, and allowed optional tables are
retained without classification or type inference.

Each parsed row stores its exact ordered values, accession, schema ID,
1-based logical source ordinal, caller-declared source-key projection, and a stable
row ID bound to the raw snapshot/member/value lineage. The accession index
requires exactly one submission row and holds separate ordered row-ID arrays
per table. It never materializes an owner-by-transaction join; two owners and
one transaction remain two owner references and one transaction reference.

Publication writes canonical `rows.jsonl`, `accessions.jsonl`, and
`manifest.json`, then publishes `snapshot.commit.json` last. The manifest
binds the parser contract/version and caller-declared parser Git SHA, complete
schema profile/hash, raw snapshot/lineage/archive/manifest hashes, exact
selected headers/source keys and member hashes, absent optional tables, row
counts, artifact hashes, lineage hash, and content-addressed directory ID.
The loader requires the exact file inventory, canonical JSON/JSONL, commit and
artifact hashes, canonical table/row/accession ordering, row-ID rebuilds,
source-key uniqueness, and a semantic rebuild of the accession index. Exact
concurrent retries are idempotent; unverified residue, redirects, conflicts,
and partial publication are refused under the same caller-controlled-root
trust boundary as IB-1A. Internal parsed hashes are not treated as proof of
raw derivation: every public load also requires, verifies, and deterministically
reparses the claimed committed raw snapshot before returning rows.

The in-memory publisher has explicit per-table, total-input, field, row, and
artifact limits. These make the first parser safely bounded; they do not prove
full-history or largest-live-quarter capacity. Lifting them requires a
separately reviewed streaming immutable publisher, not a constant-only change.

### 12.4 Verification and isolation

- Exact-current Insider Form 4, IB-1A, IB-1B, ML import-boundary, project
  separation entry-point, and module-hygiene suite: **269 passed, 5 skipped in
  48.78 seconds**. The five skips are platform symlink-privilege conditions;
  deterministic non-link path checks execute on every host.
- The IB-1B file alone passed **55 tests with 1 platform skip** after the
  restart-recovery additions. Direct dangerous-direction coverage includes
  exact and mixed hard-restart residue, exact-header mutations, typed-looking
  strings, source-key duplicates, joint-owner non-multiplication, Forms 3/5,
  semantic index forgery with all ordinary hashes recomputed, resource caps,
  concurrent exact writers, lock failures, and publication failures before
  and after each link.
- Two independent read-only code audits found and drove corrections for the
  hard-restart defect, source transaction-key preservation, malformed payload
  exception mapping, lock-error precision, impossible zero-byte identities,
  restart test depth. No remaining P0-P3 finding was reported in their assigned
  scopes after those corrections.
- The exact committed implementation snapshot `9cbc962` passed the complete
  repository suite: **5,450 passed, 7 skipped, 0 failed, 26 warnings in
  1,022.22 seconds (17m02s)**. Whole-repository compileall exited 0, the
  active-document checks passed **63 tests**, and
  `git diff HEAD^ HEAD --check` was clean. The warnings are existing
  dependency/runtime notices; no warning identifies an Insider failure.
- No SEC/EDGAR/provider request, credential, licensed row, research outcome,
  QuantConnect job, broker, operator database, scheduler, deployment, order,
  Trading App, or Streamlit surface was accessed or changed. **Research
  looks: 0.**

### 12.5 Residual gates and next step

IB-1B is a parsed-as-filed storage boundary, not completion of IB-1. The
repository still lacks an independently audited complete SEC schema/header
registry and frozen real-package fixtures, and this round had no authority to
retrieve them. Real SEC package compatibility, large-package capacity, EDGAR
acceptance/XML enrichment, amendment reconciliation, semantic normalization,
owner attribution, security identity, lot aggregation, the post-aggregation
$50,000 gate, signals, outcomes, ETF construction, and QC execution remain
deferred. No live, paper, broker, or application authority is granted.

The implementation is committed at `9cbc962` and its exact tree has passed the
focused, active-document, compileall, diff, and complete-suite validations.
Immediate next step: commit this immutable validation record, run the
record-sensitive final checks, and make the one combined push. Claude then
independently reviews every pushed commit before any further Insider milestone
begins.
## 13. Claude review - IB-1B parsed snapshot boundary (2026-08-29)

Reviewer: Claude, Insider Buying lane review session, dedicated worktree
pinned to this branch. Range reviewed: `8d9e70b..03820d3` (`9cbc962` IB-1B
implementation plus the IB-1A restart correction, `03820d3` validation
record). The remote head was fetched first and the local head confirmed
identical to `origin/codex/strategy-insider-buying`; `8d9e70b` was confirmed an
ancestor, so no published history was rewritten. No `git switch`; no other
lane, checkout, or branch touched.

**Owner scope rule, 2026-08-29.** The owner directed that this session is
dedicated to trading-strategy work, not to the general health of the Trading
App: defects found outside the strategy lane are documented in the ledger but
not fixed. Every finding below is lane-owned, so the rule did not suppress a
correction this round. The pre-existing shared-execution P1 set stays open and
uncorrected on this lane, which this rule now makes explicit policy rather than
precedent.

### 13.1 Isolation verification

Every frozen file was checked individually across the range and all are
untouched: Action Plan, Session Handoff, direction record, parallel workflow,
Strategy Description README, data-source register, both sibling lane records,
`requirements.txt`, `config.py`, `CLAUDE.md`, `AGENTS.md`, and `pytest.ini`.
The range changes exactly six files, all lane-owned: this record, the three
`research/insider_buying` modules, and the two Insider test modules.

Nothing under `assistant/`, `execution/`, `risk/`, `scripts/`, `signals/`,
`strategies/`, `data/`, or `backtest/` references `research.insider_buying`, so
the new module has no execution-side coupling. Its imports are `csv`, `io`,
`json`, `os`, `re`, `stat`, `zipfile`, `dataclasses`, `pathlib`, plus
`data.hashing`, `ml.immutable_io`, and the lane's own raw-snapshot module.
There is no network, socket, or URL surface. No SEC/EDGAR, provider,
credential, licensed row, outcome, QuantConnect, broker, operator-database,
scheduler, or UI access occurred. **0 research looks.**

### 13.2 Commit dispositions

Section 12.1 correctly criticised the previous Claude round for omitting these.
Every commit in the range is dispositioned explicitly.

| Commit | Disposition | Basis |
|---|---|---|
| `9cbc962` | **Accepted after correction.** | The IB-1A hard-restart correction is real and was independently reproduced; the IB-1B parser and immutable parsed snapshot meet their stated bounded scope. Corrected here: the loader's row-level semantic rebuild carried no test sensitivity (IB1B-R10). One further finding, IB1B-R09, is recorded rather than fixed. |
| `03820d3` | **Accepted as validation of the exact implementation tree.** | Its recorded complete-suite result was independently reproduced on the same tree (see 13.7). It changes only this record and therefore does not validate the corrections added by this review. |

### 13.3 Counter-review findings against Claude accepted

All four findings section 12 raised against this reviewer are confirmed and
accepted without reservation.

- **IB1B-CR-02, omitted dispositions.** Section 11 said "full dispositions"
  but stated none, and left the authoritative status saying review was pending.
  This violates `GENERAL_CODE_REVIEW_INSTRUCTIONS.md` section 1, which requires
  an explicit disposition for every commit in the range. The correction is
  section 13.2 above and the status line at the top of this record.
- **IB1B-CR-03, overstated provenance.** Section 11.5 said provenance "is
  checked rather than trusted". IB-1A validates the *syntax and internal
  consistency* of a caller-asserted source URL, retrieval time, and Git SHA; it
  does not authenticate SEC origin, retrieval time, or repository provenance.
  The narrower statement is the correct one.
- **IB1B-CR-07, R-24 follow-through.** This is the sharpest of the four. Last
  round's sweep put 41 survivors in the fault-recovery area and this reviewer
  described the result as test *depth*. The counter-review went into that same
  area and found a concrete reproducible hard-restart defect. Pointing at the
  right region and not opening it is a real miss, and it is the reason this
  round's sweep neutralises each invariant at every site instead of counting
  individual raise sites.
- **IB1B-CR-04, ledger ordering.** The previous Claude row was inserted before
  an existing Codex row despite the append-only instruction. This round's row
  is appended strictly after the last existing row.

### 13.4 Counter-review fixes independently verified

The IB-1A restart correction was verified by direct probe rather than by
reading the record. With a target directory holding uncommitted residue and no
commit marker, publication now recovers instead of refusing forever, and the
two-phase property holds:

| Residue in target | Result |
|---|---|
| exact `archive.zip` | recovered, republished, commit marker present |
| exact `archive.zip` + exact `manifest.json` | recovered |
| full-content publisher temporary | recovered |
| exact `archive.zip` + *mismatched* `manifest.json` | refused, **entire residue preserved byte-for-byte** |
| exact `archive.zip` + foreign file | refused, entire residue preserved |
| truncated `archive.zip` | refused, preserved |
| `archive.zip` one byte too long | refused, preserved |

The oversize case matters: `_read_regular_bytes` refuses when
`st_size > max_bytes` and re-checks the returned length, so a file whose first
bytes match the expected content cannot be silently truncated into a false
verify and then deleted. Deletion is genuinely second-phase: in every refusal
above, nothing was removed.

The IB1B-R07 containment rule was also verified rather than read. A parsed
output root equal to the raw snapshot directory, a child of it, or a deep
descendant of it is refused; the raw snapshot's parent and an ordinary sibling
directory are accepted. In all five cases the raw snapshot's own bytes were
unchanged afterwards.

### 13.5 New findings

| ID | Sev | Status | Issue, evidence, and reason |
|---|---|---|---|
| IB1B-R09 | P2 | **OPEN - reported, deliberately not fixed** | A hard restart *during* a member write still permanently blocks retry. `publish_immutable_bytes` writes to `.{name}.XXXXXX.tmp`, flushes, fsyncs, then links; a power loss inside the write leaves a partial temporary. Recovery accepts only byte-exact residue, so that partial temporary is refused on every subsequent attempt and the snapshot id can never be republished without manual filesystem intervention. Verified by direct probe in **both** modules: a `.manifest.json.crash.tmp` holding a 20-byte prefix refuses with "left unverified files", and the parsed module refuses identically. This is the same class of defect as IB1B-CR-01 and arguably the wider window, since the write window scales with archive size while the link window does not. It fails closed and destroys no evidence, which is why it is reported rather than corrected: the plausible fix is to accept a temp-named file whose content is a strict prefix of the expected bytes, and loosening a fail-closed check on immutable publication is an implementer-plus-counter-review decision, not a reviewer's unilateral edit. |
| IB1B-R10 | P2 | **FIXED IN THIS REVIEW** | The loader's row-level semantic rebuild in `_validate_rows` had no test sensitivity. Neutralising an invariant at *every* site at once, so defence in depth cannot mask it, left the suite green for: the `row_id` lineage check together with the per-table `row_ids_hash` check; the `schema_id`-to-manifest binding; the ordinal-sequence check; the accession projection check; and both row caps. This matters because section 12.3 credits exactly this layer for refusing "a forged cross-link with every ordinary hash and directory identity recomputed", while the existing forgery test forges only `accessions.jsonl`. There was no symmetric `rows.jsonl` test, so the row-side claim rested on untested code. Correction: `test_fully_rehashed_forged_row_artifact_still_refuses_semantically` (four forgeries - swapped `row_id`s, tampered `schema_id`, reversed source ordinals, and a diverted accession projection), each rebuilding the artifact hash, per-table row-id lineage, manifest lineage hash, snapshot id, and commit marker so that no content-addressed guard can be what refuses; plus `test_row_count_caps_refuse_before_any_parsed_publication` for the two row caps. Verification: the paired sweep went from **2 caught / 5 survived to 7 caught / 0 survived**, and the six new cases pass on unmodified code. |
| IB1B-R11 | P3 | OPEN | `sec_bulk_parsed_snapshot.py` re-declares eight helpers that already exist in `sec_bulk_snapshot.py` (`_status_is_redirect`, `_same_file_identity`, `_same_file_version`, `_require_regular_directory`, `_prepare_output_root`, `_require_regular_lock_slot`, `_read_regular_bytes`, `_canonical_json_bytes`), plus a near-copy of the publication-lock wrapper and of the residue-verification logic. Three are byte-identical copies and three differ only in error class or label. `_read_regular_bytes` has genuinely diverged: the parsed copy makes `max_bytes` mandatory (stricter, good) but drops the post-read `len(raw) > max_bytes` re-check. That divergence is currently safe - `_same_file_version(opened, after_read)` compares `st_size`, so with the `st_size > max_bytes` pre-check and the complete-image check the dropped branch is unreachable - but it is exactly the drift `CLAUDE.md` section 8 warns about: the hard-restart correction already had to be written twice, and a future fix to one copy will not reach the other. Consolidation belongs with R-23's neutral-module relocation at integration, not on a lane branch. |
| IB1B-R12 | P3 | OPEN | The recorded focused count "269 passed, 5 skipped" names a suite composition ("Insider/import-boundary/entry-point/module-hygiene") that does not resolve to one reproducible file set: the Insider files plus `test_ml_import_boundary.py` give 235, adding module-hygiene and separation entry-points gives 243, and adding `test_project_separation_boundary.py` gives 278. The complete-suite figures reproduce exactly, so this is a precision issue in the record rather than a disputed result. Future rows should name the exact files or the exact command so a reviewer can reproduce the number instead of approximating it. |

### 13.6 Assessment of the IB-1B slice

The module does what section 12.3 says it does. It never opens an arbitrary
ZIP: it calls the public raw loader first and derives everything from a
committed IB-1A snapshot. There is no default schema profile and no bundled
"official SEC" profile, so a caller cannot accidentally parse live SEC data
against guessed headers - a restraint worth naming, because it keeps the
unaudited-schema gate honest instead of papering over it with a plausible
default.

The invariants that carry the strategy's meaning were checked directly and they
hold. The accession index stores separate ordered row-id arrays per table and
never materialises an owner-by-transaction join; a real cross-product mutation
is caught. Duplicate accession-relative source keys are refused at both parse
and load, so neutralising either site alone is masked by the other - which is
why single-site mutation counts are not a coverage measure here.
`_validate_rows` recomputes the accession and source-key projections from
`values` rather than trusting the stored copies, rejects non-sequential
ordinals, and uses `type(ordinal) is not int`, which correctly rejects `bool`
where `isinstance` would not.

One prior test was replaced in this range and that replacement was checked
for weakening. `test_missing_commit_marker_and_partial_snapshot_refuse` encoded
the behaviour IB1B-CR-01 deliberately changed, and its replacement is strictly
broader - three recovery cases plus two refusal cases that assert the entire
residue is preserved - while retaining the original `load_sec_bulk_snapshot`
refusal assertion. **No test weakening found.**

Stated rather than implied: the row and input caps make the parser *bounded*,
not *capable*. No real SEC package has been parsed, no audited official header
registry exists, and the synthetic profiles are explicitly labelled
non-official. Streaming publication and real-package capacity remain a
separately reviewed gate, as section 12.5 already says.

### 13.7 Validation performed by this review

- Focused Insider, `ml` import-boundary, module-hygiene, and project-separation
  suites: **278 passed, 5 skipped in 41.74s**. The five skips are
  platform symlink-privilege conditions.
- IB-1B test module after the additions: **61 passed, 1 skipped** (55 before).
- Independent complete suite on the exact pushed tree `03820d3`, before any
  correction: **5,450 passed, 7 skipped, 0 failed, 25 warnings in 867.42s
  (14m27s)**. This reproduces the recorded Codex pass and skip figures exactly;
  the warning count differed by one (25 here, 26 recorded), which is ordinary
  host variance and identifies no Insider failure.
- Paired mutation sweep of seven semantic invariants, each neutralised at every
  site simultaneously: **2 caught / 5 survived before the corrections, 7 caught
  / 0 survived after**. The module was restored from git and confirmed
  byte-identical to `HEAD` after every sweep.
- Direct read-only probes: seven hard-restart residue cases against
  `sec_bulk_snapshot.py` and five against `sec_bulk_parsed_snapshot.py`.
- `compileall` over `research/insider_buying` and the changed test module: exit
  0. `git diff --check` clean apart from the repository's usual line-ending
  notice.
- This review's own diff is **128 insertions, 0 deletions**, entirely in
  `tests/test_insider_buying_sec_bulk_parsed_snapshot.py`. No product code was
  changed by this review.
- Complete suite on the exact final review tree, after the correction commit
  `61b0bec`: **5,456 passed, 7 skipped, 0 failed, 25 warnings in 830.27s
  (13m50s)**. That is exactly the pre-review 5,450 plus this review's six new
  cases, with no pre-existing test disturbed.
- Active-document consistency suite on the final tree: **63 passed**.

### 13.8 Residual gates and next authorized step

IB-1B is a parsed-as-filed storage boundary. The gates section 12.5 lists are
unchanged: no audited official SEC schema registry, no real-package fixtures,
no capacity evidence, and no EDGAR acceptance/XML enrichment, amendment
reconciliation, normalization, owner attribution, security identity, lot
aggregation, post-aggregation $50,000 gate, signal, outcome, ETF construction,
or QC execution. IB1B-R09 is open and needs an implementer decision.

The shared-execution-surface P1 set (R-01, R-10 through R-15, R-18, with
R-09/R-20 host-scoped per R-22) remains open and uncorrected on this lane, now
under the owner's explicit 2026-08-29 scope rule. R-23 and IB1B-R11 are
integration-time consolidation debt.

Next authorized step: Codex counter-reviews these Claude commits, then may
continue the bounded IB ladder. No SEC ingest, outcome join, ETF construction,
QuantConnect job, or broker action is authorized.

## 14. Codex counter-review and bounded IB-1C acceptance evidence (2026-08-30)

Implementer and counter-reviewer: Codex, in the same long-lived Insider Buying
worktree and branch. Claude range reviewed: `61b0bec..60c2f29`, two commits.
Codex correction: `7b3377b`. Bounded IB-1C implementation snapshot: `892218d`.
No branch, worktree, or lane was created or switched.

The owner scope remains strategy-only. No Trading App, Streamlit, shared
execution, provider, outcome, QuantConnect, broker, operator-database, or
scheduler surface was changed. Shared-surface findings from earlier rounds stay
documented and uncorrected on this lane.

### 14.1 Claude commit dispositions

Every Claude commit since the prior Codex push is dispositioned separately.

| Commit | Disposition | Basis |
|---|---|---|
| `61b0bec` | **Accepted.** | The six IB-1B row-level rebuild and cap regressions are valid, materially strengthen mutation sensitivity, and do not weaken or replace production behavior. |
| `60c2f29` | **Accepted after current record correction.** | The review record accurately preserves the prior validation and IB1B-R09 through IB1B-R11. Two prose/structure defects were corrected here: its long ledger row had been physically split into prose, and section 13.6 said two prior tests were replaced when exactly one was. |

### 14.2 Counter-review findings and dispositions

| ID | Sev | Disposition | Evidence and resolution |
|---|---|---|---|
| IB1C-CR-01 / IB1B-R09 | P2 | **Confirmed and fixed in `7b3377b`.** | A strict prefix left in a publisher temporary after process loss permanently blocked the same content-addressed snapshot. Both IB-1A and IB-1B now recover an exact verified prefix only when no final commit exists. Classification remains two-phase: any foreign, oversize, mixed, redirected, or committed partial residue refuses before any deletion, and a committed final accepts only byte-exact temporary residue. |
| IB1C-CR-02 / IB1B-R10 | P2 | **Accepted.** | Claude's six tests make the row-id, schema, ordinal, accession-projection, and row-cap rebuild guarantees load-bearing. No production correction or test weakening was found. |
| IB1C-CR-03 / IB1B-R11 | P3 | **Confirmed, deferred.** | The raw and parsed boundaries still duplicate immutable-I/O helpers. Consolidation belongs in a neutral shared-module integration round, not this strategy-only milestone. No unsafe current behavior was reproduced. |
| IB1C-CR-04 / IB1B-R12 | P3 | **Rejected as a false positive.** | On exact tree `9cbc962`, the files actually named by the prior row collect 274 cases and produce the recorded 269 passed plus 5 skips. Claude's later inclusion of `test_project_separation_boundary.py` plus its six new tests produces the later 278 result. The original count is reproducible; future rows nevertheless name all nine files explicitly. |
| IB1C-CR-05 | P3 | **Fixed.** | The Claude session-ledger row was physically wrapped across three lines, so Markdown rendered two fragments as prose despite the append-only table contract. It is restored to one row, and a lane-local structural test now rejects wrapped or blank-separated ledger rows. |
| IB1C-CR-06 | P3 | **Fixed.** | Section 13.6 said two prior tests were replaced, but inspection found one replacement. The statement now matches the diff. |

### 14.3 Implemented IB-1C boundary

`research/insider_buying/sec_edgar_acceptance_snapshot.py` is an offline,
bounded acceptance-evidence layer over the public raw-bound IB-1B loader. It
accepts only an explicit immutable schema profile and a tuple of caller-supplied
flat JSON byte images. The repository provides no default or "official SEC"
profile and performs no discovery or network access.

For every verified upstream accession, the canonical bundle emits exactly one
availability record:

- a supplied, valid, upstream-matching metadata image produces
  `EXACT_ACCEPTANCE_TIMESTAMP` plus `NEXT_OPEN_AFTER_ACCEPTANCE`; or
- absence of a source produces `FILING_DATE_FALLBACK` plus
  `NEXT_OPEN_AFTER_FILING_DATE`.

Supplied-but-invalid evidence never degrades to fallback. The entire build
refuses on malformed or duplicate JSON, duplicate or unknown accessions,
upstream form/date/quarter/accession-year disagreement, invalid issuer CIK,
transaction-shaped availability mappings, noncanonical URLs, source/primary
URL accession or issuer disagreement, pre-acceptance retrieval, or acceptance
outside the deterministic half-open filing-day window `[05:00Z, next-day
05:00Z)`. This UTC window deliberately avoids an unpinned timezone database,
can conservatively refuse the first EDT hour, and keeps date-only next-open
fallback from preceding supplied exact evidence.

The one canonical content-addressed JSON bundle retains reversible source bytes
as canonical base64 plus exact hashes, sizes, URLs, UTC retrieval times, capture
commit assertions, the explicit profile, upstream raw/parsed lineage, every
record, and all counts. Load revalidates canonical encoding, declared sizes,
source inventory and order, records and order, reparses every source, rebuilds
the complete snapshot against the verified raw-bound upstream, rereads the
bundle, and requires byte-for-byte equality. Caller URL, retrieval time, and
Git provenance are syntax- and internal-consistency assertions only; they are
not authenticated SEC, transport, clock, or repository evidence.

The in-memory layer is explicitly capped for source count, per-source and total
source bytes, record count, profile fields/names/values, URL characters, JSON
nesting, final bundle bytes, and publisher-temporary count. Declared source
sizes and aggregate size are checked before base64 decoding. Publication is
locked, immutable, content-addressed, two-phase for residue classification, and
requires the final bundle to remain a single-link regular file before and after
the upstream rebuild. Exact-prefix recovery is permitted only before a final
commit; committed evidence remains exact-only.

Form 4/A rows remain represented because IB-1B supplies them, but IB-1C does
not infer original/amendment relationships, supersession, or correction
semantics. It retains primary-document URLs as evidence strings but does not
fetch or validate XML. Therefore blueprint section 19.4 step 3 and IB-1 are
still incomplete.

### 14.4 IB-1C implementation and audit findings

The issue ledger retains every finding even though all are resolved in the
implementation snapshot.

| ID | Sev | Status | Issue, evidence, and resolution |
|---|---|---|---|
| IB1C-R01 | P1 | **FIXED** | Comparing an acceptance timestamp's source wall date allowed `2026-05-01T00:00:00+14:00`, an April 30 UTC instant, to qualify for a May 1 filing. Both direct record construction and assembly now use the fixed UTC filing-day window; inverse and exact-boundary cases are pinned. |
| IB1C-R02 | P2 | **FIXED** | Deep source or bundle JSON could surface a raw recursive-decoder failure. Quote/escape-aware depth preflight now runs before `json.loads`, and decoder-sentinel regressions prove ordering. Decoder recursion is also mapped to the public refusal. |
| IB1C-R03 | P2 | **FIXED** | Loader source caps originally ran after base64 decoding. Exact keys, positive declared size, canonical encoded length, per-source cap, and aggregate cap now run before any decode; direct sentinel tests make both orderings load-bearing. |
| IB1C-R04 | P1 | **FIXED** | A syntactically valid filing date from another year or quarter could contaminate date-only availability, and the accession's two-digit year was unbound. Each filing now matches the verified snapshot year/quarter and accession year before any record is emitted. |
| IB1C-R05 | P2 | **FIXED** | A source or primary-document Archive URL could name the right accession under the wrong host or issuer CIK. Canonical Archive paths now bind `www.sec.gov`, issuer CIK, compact accession, and filename to upstream lineage. |
| IB1C-R06 | P2 | **FIXED** | A preexisting hardlinked publication-lock slot could mutate an external peer when the lock primitive wrote its sentinel byte. Lock slots must be single-link regular files before and after acquisition; the external peer remains unchanged in regression. |
| IB1C-R07 | P3 | **FIXED** | Publisher temporary discovery materialized the entire output directory. Matching residue is now streamed and capped before deletion; exceeding the cap refuses with all residue preserved. |
| IB1C-R08 | P3 | **FIXED** | Using host timezone data for the SEC-day boundary would make future rebuilds depend on unversioned tzdata. A documented fixed 05:00Z boundary covers EST/EDT conservatively and is pinned at both edges. |
| IB1C-R09 | P2 | **FIXED** | Ambiguous clock-fold and caller-mutable timezone objects could canonicalize to one persisted UTC instant but compare or behave as another during recovery. Retrieval and exact-acceptance datetimes are now frozen to fixed UTC at construction, and exact bytes plus canonical provenance drive recovery equality. Fold, mutable-offset, inverse, retry, and loader round trips are pinned. |
| IB1C-R10 | P2 | **FIXED** | Unknown-upstream accession, issuer CIK, primary-document CIK, base64 canonicality, record/source ordering, and availability-tier guards initially lacked isolated mutation-sensitive tests. Self-consistent forgeries and direct private/public boundary tests now reach the intended guards rather than failing an earlier hash, URL, or length check. |
| IB1C-R11 | P1 | **FIXED** | Exact acceptance was allowed arbitrarily after `FILING_DATE`, while omitted evidence used next-open-after-date fallback. That could make fallback precede known public availability. Exact evidence is now restricted to `[filing-date 05:00Z, next-date 05:00Z)`; next-boundary and multi-day-late timestamps refuse before publication. |
| IB1C-R12 | P2 | **FIXED** | A final content-addressed bundle hardlinked outside the output root could later be mutated through its peer. Final reads require `st_nlink == 1`; a link present initially or introduced during the potentially long upstream rebuild is refused. Pre-cleanup recovery reads remain permissive only so a verified publisher-temporary hardlink can be removed first. |
| IB1C-R13 | P3 | **FIXED** | Direct exact-record construction could retain mutable or second-offset timezone state whose payload later changed or failed its own loader. Exact records canonicalize to fixed UTC and round-trip through `_record_from_payload`; the public tier/rule/evidence XOR is directly pinned. |
| IB1C-R14 | P3 | **FIXED** | The first lane-record table guard discarded blank lines before checking shape, so a blank line could terminate the Markdown table while the test stayed green. The raw slice now preserves lines and rejects every blank or whitespace-only line between the header and final row. |

Two independent final read-only audits report **no remaining P0, P1, P2, or P3
finding** in the IB-1C module, exports, tests, or lane-record guard. No valid
existing test was weakened or removed.

### 14.5 Verification and isolation

- Complete exact-tree suite at committed snapshot `72c5c86`: **5,649 passed,
  9 skipped, 0 failed, 26 warnings in 1,035.43s (17m15s)**.
- Exact current nine-file suite: `test_insider_buying_form4.py`,
  `test_insider_buying_sec_bulk_snapshot.py`,
  `test_insider_buying_sec_bulk_parsed_snapshot.py`,
  `test_insider_buying_sec_edgar_acceptance_snapshot.py`,
  `test_insider_buying_implementation_record.py`,
  `test_ml_import_boundary.py`, `test_project_separation_entrypoints.py`,
  `test_module_hygiene.py`, and `test_project_separation_boundary.py`:
  **477 passed, 7 skipped in 130.14s**.
- Final IB-1C module: **153 passed, 2 skipped in 98.03s**. Independent final
  audit of IB-1C plus the record guard: **154 passed, 2 skipped in 93.79s**.
- Focused correction slices included 29 timezone/lineage/base64/tier/CIK cases,
  14 filing-window/recovery/hardlink cases, and 11 hardlink/recovery cases; all
  passed on their respective latest trees before the final module run.
- Compileall over the four implementation Python files and later over the
  complete Insider package: exit 0. `git diff --check` is clean apart from the
  repository's line-ending notices.
- Blueprint pages 28-29 and section 19.4 were rechecked. This implementation is
  only the acceptance-evidence portion of step 3, not completion of step 3.
- There was no SEC/EDGAR/provider, credential, licensed row, outcome,
  QuantConnect, broker, operator-database, scheduler, UI, or order access.
  **0 research looks.**

### 14.6 Residual gates and next authorized step

IB-1C proves fixture-level software behavior only. It does not establish an
official SEC metadata schema, fair-access downloader, real-package
compatibility, capacity, authenticated capture provenance, XML validity,
original/amendment links, Form 4/A supersession, normalized transactions,
joint-owner handling, point-in-time security mapping, the post-aggregation
$50,000 rule, a signal, an outcome, an ETF portfolio, or a QC algorithm.

IB1B-R11 and the earlier R-23 neutral immutable-I/O consolidation remain
integration debt. The shared execution-surface P1 set remains outside this
strategy-only lane and was not changed.

Next step for this round: commit this record, validate the exact committed tree
with the complete suite and whole-repository compileall, append the immutable
validation row, and make one push. Claude must review every pushed commit before
Codex begins any bounded amendment-reconciliation milestone. No live SEC ingest,
research look, outcome join, QuantConnect job, broker action, or UI work is
authorized.
## 15. Claude review - IB-1C acceptance evidence (2026-08-30)

Reviewer: Claude, Insider Buying lane review session, dedicated worktree
pinned to this branch. Range reviewed: `60c2f29..d6f587b` (four commits). The
remote was fetched first, the local head confirmed identical to
`origin/codex/strategy-insider-buying`, and `60c2f29` confirmed an ancestor, so
no published history was rewritten. No `git switch`; no other lane, checkout,
or branch touched.

The owner's 2026-08-29 strategy-scope rule continues to apply. Every finding
below is lane-owned, so the rule suppressed no correction this round.

### 15.1 Isolation verification

All thirteen frozen files were checked individually across the range and are
untouched: Action Plan, Session Handoff, direction record, parallel workflow,
Strategy Description README, data-source register, both sibling lane records,
`requirements.txt`, `config.py`, `CLAUDE.md`, `AGENTS.md`, and `pytest.ini`.
The range changes nine files, all lane-owned: this record, four
`research/insider_buying` modules, and four Insider test modules.

Nothing under `assistant/`, `execution/`, `risk/`, `scripts/`, `signals/`,
`strategies/`, `data/`, or `backtest/` references `research.insider_buying`.
No SEC/EDGAR, provider, credential, licensed row, outcome, QuantConnect,
broker, operator-database, scheduler, or UI access occurred. **0 research
looks.**

### 15.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `7b3377b` | **Accepted.** | The IB1B-R09 correction is real, correctly bounded, and independently reproduced across thirteen probes and five dangerous-direction mutants (15.4). The relaxation is confined to name-recognised publisher temporaries in the uncommitted path and is unavailable once a commit marker or final bundle exists. |
| `892218d` | **Accepted after correction.** | The IB-1C acceptance boundary is well-constructed and its look-ahead guards are load-bearing (15.4). One material defect is open: the filing-day window contradicts EDGAR's own after-hours cutoff rule and would refuse a large share of real Form 4 filings (IB1C-R15). It fails closed, so it is reported rather than corrected. |
| `72c5c86` | **Accepted.** | The counter-review record states each Claude commit disposition explicitly, its six counter-review findings are correct including the two errors it raises against this reviewer, and its IB1C-R01 to R14 ledger is retained in full. |
| `d6f587b` | **Accepted as validation of the exact implementation tree.** | Its focused and module figures were reproduced exactly (15.7). It changes only this record and therefore does not validate this review's own findings. |

### 15.3 Counter-review findings against Claude

Three of the six findings this round are errors of this reviewer's. All are
confirmed and accepted; none is disputed.

- **IB1C-CR-04, my IB1B-R12 was a false positive.** I reported that the
  recorded "269 passed, 5 skipped" did not resolve to a reproducible file set.
  It does. My own command used the glob `tests/*entry_point*.py`, which matches
  nothing because the file is `test_project_separation_entrypoints.py`, and I
  had suppressed stderr, so the no-match was silent and I compared a six-file
  set against a seven-file one. Verified at exact tree `9cbc962`: form4 91 +
  parsed 56 + bulk 84 + import-boundary 9 + module-hygiene 8 = 248, which is
  the 243-plus-5 I reported; adding separation-entrypoints 26 gives 274, which
  is exactly the recorded 269 passed plus 5 skips. The rejection is correct and
  the finding is withdrawn. The irony is not lost: I raised an unreproducible-
  claim finding using an unreproduced command.
- **IB1C-CR-05, I broke the ledger table.** My finalisation script replaced a
  ledger substring with text containing literal newlines, splitting my own row
  into three lines so Markdown rendered two fragments as prose. Verified from
  the diff. The structural guard added in
  `tests/test_insider_buying_implementation_record.py` is legitimate and
  correctly shaped: it requires contiguous, non-blank, uniform-column rows
  between the header and section 6, and it would have caught my defect.
- **IB1C-CR-06, miscounted replaced tests.** Section 13.6 said two prior tests
  were replaced in the range. Exactly one was:
  `test_missing_commit_marker_and_partial_snapshot_refuse`. Verified by
  counting removed test definitions in `8d9e70b..03820d3`. I carried the count
  over from the previous round, where two were removed.

The other three are accepted as recorded: IB1C-CR-01 confirms and fixes my
IB1B-R09; IB1C-CR-02 accepts my IB1B-R10 tests without weakening them; and
IB1C-CR-03 confirms IB1B-R11 and defers it, which 15.5 revisits.

### 15.4 Counter-review fixes independently verified

**The IB1B-R09 relaxation is correctly bounded.** I did not read the docstring
and accept it; I probed the guards it claims. Thirteen residue cases across
both modules behaved exactly as specified:

| Residue with NO commit marker | Result |
|---|---|
| partial temporary (20-byte prefix) | recovered |
| zero-byte temporary (death before first write) | recovered |
| exact final member plus partial temporary | recovered |
| final member truncated | refused, entire residue preserved |
| temporary with one corrupted byte (not a prefix) | refused, preserved |
| temporary longer than expected | refused, preserved |
| foreign file | refused, preserved |
| temporary whose name matches no expected member | refused, preserved |

| Residue WITH a commit marker | Result |
|---|---|
| exact leftover temporary | cleaned |
| partial temporary | refused, preserved |
| zero-byte temporary | refused, preserved |
| foreign file | refused, preserved |

The asymmetry the correction claims therefore holds in practice: prefix
tolerance exists only where nothing authoritative has been published. Five
dangerous-direction mutants confirmed the tests are load-bearing rather than
incidental - dropping the `is_final` guard so a truncated final member becomes
deletable, forcing the prefix comparison true in each module, and letting the
relaxation leak past the commit marker were all caught, 5 of 5.

The same asymmetry is implemented a third time in the acceptance module through
an explicit `allow_prefix` parameter, and every call site was checked:
`allow_prefix=True` appears only where the target bundle is proven absent, and
the single `allow_prefix=False` site is the recovery path where the bundle
exists. That generalisation is correct and is the right instinct; 15.5 records
its structural cost.

**IB-1C look-ahead guards are load-bearing.** Nine invariants that could make a
filing appear publicly available earlier than it was, or attach one filing's
acceptance evidence to another, were each neutralised and the suite caught all
nine: upstream form and filing-date agreement, the filing-day window (at record
and assembly level together), retrieval-precedes-acceptance, the fallback
tier's prohibition on exact-source evidence, the exact tier's matching
next-open rule, duplicate metadata sources, metadata for an accession absent
upstream, and offset-aware second-resolution acceptance. Disabling the
assembly-level filing-day check alone survives, but that is genuine defence in
depth rather than a gap: the record constructor re-checks the same window
against the same filing date, and disabling both is caught.

One property is stronger than a test: a missing metadata source **cannot**
produce an exact tier, because the exact tier's `__post_init__` requires an
acceptance timestamp, a primary-document URL, and a source hash that simply do
not exist in the fallback branch. Verified directly - constructing that record
refuses with "exact acceptance timestamp must be a timezone-aware datetime".
Absent evidence degrades to the later availability, never the earlier one,
which is the correct direction for this strategy.

**No test weakening.** All four test files in the range are pure additions,
zero deletions, and no test definition was removed anywhere in the range. My
six IB1B-R10 regressions are present and unmodified.

### 15.5 New findings

| ID | Sev | Status | Issue, evidence, and reason |
|---|---|---|---|
| IB1C-R15 | P2 | **OPEN - reported, deliberately not fixed** | The `[filing-date 05:00Z, next-date 05:00Z)` window assumes acceptance and `FILING_DATE` fall on the same day. EDGAR's own cutoff rule breaks that assumption by design: a submission accepted after 17:30 ET is assigned the **next business day** as its filing date, so its acceptance instant necessarily precedes its filing-date window. Verified with a control and two realistic cases: accepted 17:30 ET on 2026-05-01 filed 2026-05-01 is accepted; accepted 18:00 ET Friday 2026-05-01 filed Monday 2026-05-04 is refused; accepted 20:00 ET 2026-05-04 filed 2026-05-05 is refused, both with "acceptance timestamp is outside the upstream filing-date window". After-hours Form 4 filing is routine rather than exceptional, and the guard raises rather than skips, so the first real quarterly package containing any after-hours filing would refuse in full. The same defect explains a second case I found first and which is subsumed by it: an accession assigned in one year whose filing date rolls into the next, verified as `-26-` accession filed 2027-01-04 refused while a `-27-` control is accepted, because `filing_date.year % 100 != accession_year` in `_submission_rows`. IB1C-R11's intent is right - exact acceptance must not silently follow the filing date - but it clamped both directions, and the dangerous direction is acceptance *after* the filing date, not before. Not corrected here for the same reason IB1B-R09 was not: this is a central availability-timing invariant governed by blueprint pages 28-29, and widening it is an implementer decision that should be confirmed against a real package rather than against my model of EDGAR. It fails closed, so nothing unsafe is currently possible; the cost is that real ingest cannot succeed. |
| IB1C-R16 | P3 | OPEN - escalated from IB1B-R11 | The immutable-I/O helper set is now duplicated **three** times. `_status_is_redirect`, `_same_file_identity`, `_same_file_version`, `_read_regular_bytes`, `_require_regular_directory`, `_prepare_output_root`, `_require_regular_lock_slot`, and `_canonical_json_bytes` each exist in three lane modules, alongside three publication-lock wrappers and three residue-verification implementations. The deferral was reasonable when there were two copies; this round demonstrates its cost rather than predicting it, because the single IB1B-R09 correction had to be written three times in three shapes within one milestone. Each copy is currently correct and I found no drift-caused defect, so this stays P3 and stays deferred to the neutral-module integration round alongside R-23 - but the next such correction is the one likely to reach two modules out of three. |

### 15.6 Assessment of the IB-1C slice

This is the strongest milestone in the lane so far, and its central design
decision is the right one. Availability is derived from two mutually exclusive
evidence tiers, each bound to exactly one execution rule, with the fallback
tier forbidden from carrying any exact-source field. Absence of evidence
produces the later availability rather than the earlier one, and the contract
makes the unsafe combination structurally unconstructible rather than merely
untested.

The metadata-to-submission join is genuinely defensive: one source per
accession, the accession must exist upstream, form and filing date must agree
with the parsed submission row, the primary-document and source URLs must bind
`www.sec.gov`, the issuer CIK, and the compact accession, and retrieval time
may not precede the acceptance it claims to have captured. That last check is
the kind of impossible-provenance guard that is easy to omit and hard to add
later.

`_submission_rows` re-derives everything from the parsed row values rather than
trusting the accession index, and re-checks the accession number and document
type against it. IB1C-R08's decision to pin a fixed 05:00Z boundary instead of
consulting host tzdata is correct for reproducibility, and the boundary
comfortably contains EDGAR's 06:00-22:00 ET operating window in both EST and
EDT. The defect in IB1C-R15 is not the boundary; it is the assumption that
acceptance shares a calendar day with the assigned filing date.

Stated rather than implied: this milestone establishes fixture-level software
behaviour only, as section 14.6 already says. No real SEC package, official
metadata schema, or authenticated capture provenance exists, and IB1C-R15 is
concrete evidence that fixture-level green does not imply real-package
compatibility.

### 15.7 Validation performed by this review

- Nine-file focused suite, exactly as section 14.5 now names it: **477 passed,
  7 skipped**, reproducing the recorded figure exactly.
- IB-1C module alone: **153 passed, 2 skipped**, reproducing the recorded
  figure exactly.
- Independent complete suite on the exact pushed tree `d6f587b`: recorded in
  the appended ledger row.
- Look-ahead mutation sweep: nine invariants neutralised, **9 of 9 caught**;
  one further single-site mutant survives and is explained as defence in depth,
  with the paired version caught.
- IB1B-R09 relaxation mutation sweep: **5 of 5 caught**.
- Thirteen direct residue probes across both snapshot modules, four
  availability-contract probes, and three after-hours plus two year-boundary
  reproduction probes.
- Test-weakening audit: four test files, **zero deletions**, no removed test
  definition, my six prior regressions unmodified.
- Every module restored from git and confirmed byte-identical to `HEAD` after
  each mutation sweep.
- This review changed **no file** except this record.

### 15.8 Residual gates and next authorized step

Section 14.6's gate list stands unchanged and IB1C-R15 is added to it: real
quarterly-package compatibility is now known to be blocked by a specific,
reproducible timing assumption rather than merely unproven. No official SEC
metadata schema, fair-access downloader, capacity evidence, authenticated
capture provenance, XML validity, amendment supersession, normalized
transactions, joint-owner handling, point-in-time security mapping,
post-aggregation $50,000 rule, signal, outcome, ETF portfolio, or QC algorithm
exists.

IB1C-R16, IB1B-R11, and R-23 remain integration-time consolidation debt. The
shared execution-surface P1 set remains open and uncorrected on this lane under
the owner's strategy-scope rule.

Next authorized step: Codex counter-reviews these Claude commits and decides
IB1C-R15 before beginning the bounded amendment-reconciliation milestone. No
live SEC ingest, research look, outcome join, QuantConnect job, broker action,
or UI work is authorized.

## 16. Codex counter-review and bounded IB-1D observation chronology (2026-08-30)

Counter-reviewer and implementer: Codex, in the same long-lived Insider Buying
worktree and branch. Claude range reviewed: `d6f587b..50bc867`, one docs-only
commit. Bounded implementation snapshot: `73e87bc`. No branch or worktree was
created or switched, and no sibling strategy or shared execution surface was
changed.

The counter-review used the governing blueprint pages 10, 12, 28, and 29 and
official SEC filing-rule documentation. This was documentation access only:
no SEC filing, package, API response, provider data, credential, licensed row,
market outcome, QuantConnect job, broker, operator database, scheduler, UI, or
order was accessed. Research-look count remains **0**.

### 16.1 Claude commit disposition and superseding record corrections

| Commit | Disposition | Basis |
|---|---|---|
| `50bc867` | **Accepted after current-record correction.** | The independent review and preserved validation evidence are useful, and IB1C-R16 is valid deferred P3 consolidation debt. IB1C-R15 is rejected as a false positive: the SEC's ownership-form exception gives Forms 3, 4, 5, and their amendments the receipt date through 10 p.m. ET, so the review's synthetic Friday 18:00 ET to Monday filing-date and 20:00 ET next-day cases are invalid input combinations. The strict IB-1C filing-day guard remains unchanged. This section also supersedes five P3 record defects in section 15 without rewriting that historical reviewer text. |

The superseded P3 statements are: section 15.2 says `72c5c86` recorded two
reviewer errors although section 14 records three; section 15.7 calls five
synthetic/direct timing probes "real-data" reproductions despite recording no
SEC access; section 15.6 overstates metadata-source URL lineage because
`data.sec.gov` non-Archive source URLs are permitted while the primary-document
URL alone is always the accession-addressed `www.sec.gov/Archives` path; and
section 15.5 uses a four-column finding table instead of the owner-mandated
ten-column ledger. The current section supplies the complete ledger. The fifth
defect is the resulting top-level/open-gate statement, now superseded by the
false-positive disposition and corrected status above.

### 16.2 Complete counter-review and implementation issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1D-CR01 / IB1C-R15 | P2 | Closed - false alarm | `50bc867` | `docs/Strategy Description/INSIDER_BUYING_IMPLEMENTATION_RECORD.md` section 15.5; `research/insider_buying/sec_edgar_acceptance_snapshot.py` | The review claimed routine post-17:30 ownership filings receive the next business day's filing date and asked the implementer to decide whether to widen the acceptance window. That premise would turn valid Form 4 receipts into false incompatibility. | SEC filing-date guidance explicitly exempts Forms 3, 4, 5, and amendments from the general 17:30 rollover through 22:00 ET; SEC Release 33-8230 section 232.13(a)(4) adopted the same rule before the strategy's 2006 data start. | Widening the guard for the fabricated rollover would weaken accession/date lineage and could accept an impossible early filing date. | No production change. Added same-day 18:00 and 21:59:59 ET ownership regressions, retained false-rollover refusal, and added a post-22:00 earlier-date refusal. | New timing cases pass in the 189-test module and 513-test focused suite. |
| IB1D-CR02 | P3 | Closed - corrected here | `50bc867` | Record section 15.2 | The `72c5c86` disposition says the prior record found two reviewer errors; section 14 actually records three. | Direct comparison of sections 14.2 and 15.2. | Commit dispositions must preserve the exact review history. | Current section records three; historical text remains preserved as reviewer-authored evidence. | Lane-record guard passes in the nine-file suite. |
| IB1D-CR03 | P3 | Closed - corrected here | `50bc867` | Record sections 15 ledger and 15.7 | Five synthetic/direct probes were labeled "real-data timing reproductions" while the same review states no SEC data access. | Review tests and ledger explicitly report synthetic inputs and zero external access. | Calling fixtures real data overstates evidence and obscures the unproven compatibility gate. | Current ledger calls them synthetic/direct probes and retains the no-data-access statement. | Record terminology reviewed against test fixtures and access ledger. |
| IB1D-CR04 | P3 | Closed - corrected here | `50bc867` | Record section 15.6 | The review says metadata source and primary URLs both bind `www.sec.gov`, CIK, and accession. Metadata source URLs may instead be non-Archive `data.sec.gov`; only Archive source URLs receive Archive path binding, while primary-document URLs always receive it. | `_validate_sec_source_url`, `_validate_source_url_lineage`, and `_validate_primary_document_url` have distinct contracts. | Overstating provenance could be mistaken for authenticated capture evidence. | Current section distinguishes primary-document binding from conditional metadata-source binding. | Static contract audit; existing URL mutation tests remain green. |
| IB1D-CR05 | P3 | Closed - corrected here | `50bc867` | Record section 15.5 | The four-column review table omits commit, location, evidence, reason, correction, and verification fields required by the standing review process. | `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` mandates the ten-column minimum used here. | A complete durable ledger is required for later counter-review and audit. | This table retains every review and implementation finding in the mandated shape. | Visual/table-shape review plus active lane-record tests. |
| IB1D-CR06 / IB1C-R16 | P3 | Open - deferred | `50bc867` | Three immutable snapshot modules | Immutable I/O and residue helpers remain triplicated. A future correction could drift across copies. | Static comparison confirms three current implementations; no incorrect behavior was reproduced. | Consolidation is a maintainability reduction, not an IB-1D correctness prerequisite. | No fourth publisher was added. Neutral-module consolidation remains deferred to an owner-scheduled integration round. | Three current copies retain their existing focused tests; IB-1D is in-memory only. |
| IB1D-CR07 | P3 | Open - evidence gate | `50bc867` | `research/insider_buying/sec_edgar_acceptance_snapshot.py` filing-day window | The reproducible 05:00Z window is not an authenticated proof of EDGAR operating-hour semantics and can accept a caller-fabricated same-date timestamp after 22:00 ET if every asserted input agrees. | The current boundary intentionally authenticates neither metadata transport nor an official schema. A next-business-date post-22:00 probe refuses, but no real package has been tested. | This must remain visible so fixture success is not promoted to official compatibility. | Added the correct post-cutoff mismatch regression; retained the broader deterministic date window and the explicit unauthenticated-evidence gate. | Regression passes; no official-profile or real-package claim is made. |
| IB1D-R01 | P1 | Closed - fixed before commit | `73e87bc` | `Form4VersionInterval`, `ReconciledForm4Amendments` | The first draft let a caller omit a known Form 4/A and receive an original marked effective without an end, creating unlimited canonical eligibility and look-ahead-sensitive filtering. | Independent semantic and code audits reproduced the omission using an original-only supplied XML sample while another amendment existed outside that sample. | Caller-controlled omission must never create canonical strategy authority. | Recast the entire result as observation-only, removed every effective/filter-returning API, hash-bound completeness and authority as false, and preserved only a provisional `as_filed_corpus`. | Original-only and amended-sample tests prove both authority gates remain false; forged inner flags refuse. |
| IB1D-R02 | P2 | Closed - fixed before commit | `73e87bc` | `reconcile_sec_form4_amendments` parsed-object accumulation | A 64 MiB XML sample could amplify into very large retained owner, footnote, and transaction object graphs. | Code audit traced full ElementTree and ParsedTransaction materialization across retained filings. | Bounded input bytes alone do not bound memory consumption. | Added per-filing and aggregate owner, footnote, and transaction caps checked immediately after each bounded parse and before retention. | Six cap regressions pass; a combined per-filing cap deletion mutant is killed. |
| IB1D-R03 | P2 | Closed - fixed before commit | `73e87bc` | Reconciliation identity construction | A constant reconciliation hash and omission of `amends_accession` from source identity both survived the initial tests, so different lineages could share an apparently valid identity. | Independent mutation audit produced two surviving dangerous-direction mutants. | Identity must change when exact bytes, capture lineage, parser version, or asserted amendment target changes. | Added exact expected source-inventory and reconciliation-hash equations plus valid same-issuer target and parser-commit variations. | Both former survivors are killed; input-order determinism still passes. |
| IB1D-R04 | P2 | Closed - fixed before commit | `73e87bc` | `ReconciledForm4Amendments` public constructor | A forged wrapper using a `SimpleNamespace` identity could expose true authority flags despite the valid inner identity refusing them. | Direct construction returned true for both properties in the pre-fix draft. | A public result boundary cannot let ordinary construction bypass its central safety invariant. | Added exact-type, rebuild, count, lineage, source-hash, and inventory checks; result properties return literal false. | Forged-wrapper adversarial regression refuses; final independent probe passes. |
| IB1D-R05 | P3 | Closed - fixed before commit | `73e87bc` | Form 4/A outcome guard | A contradictory outcome tuple containing both amendment exclusion and eligibility passed a membership-based guard. | Code audit constructed the contradictory tuple; current generic eligibility property happened to remain false. | Amendment rows must have one unambiguous exclusion state. | Require the exact singleton `(EXCLUDE_AMENDED_FILING,)` tuple. | Both eligibility-only and contradictory-tuple parser mutations refuse. |
| IB1D-R06 | P3 | Closed - fixed before commit | `73e87bc` | `observed_state_at` | Returning a full interval for a pre-amendment as-of query exposed the future supplied amendment timestamp. | Semantic audit inspected the returned `next_supplied_acceptance_at`. | Even a QC-only observation helper should not present future boundary data as an as-of view. | Added `Form4ObservedState`, which omits the interval end; full intervals remain explicit offline audit chronology only. | Boundary regression asserts the returned state has no future-end attribute. |
| IB1D-R07 | P3 | Closed - fixed before commit | `73e87bc` | Corpus-to-lineage reconciliation | Edge-set and total-count checks could miss duplicate original lineages while omitting another original. | Code audit supplied the two-original duplicate-lineage mutation. | Parallel corpus and chronology representations must not silently drift. | Require exact unique accession inventory equality, edge equality, and result rebuild equality. | Duplicate-lineage monkeypatch refuses; final adversarial probe passes. |
| IB1D-R08 | P2 | Open - authority blocker | `73e87bc` | One-quarter acceptance-snapshot API | One call can load only one quarterly IB-1C snapshot, so an amendment cannot be authoritatively joined to an original in an earlier quarter. | API accepts one acceptance bundle and requires every asserted target in the supplied XML corpus. | Cross-quarter coverage is required before canonical amendment resolution. | Deliberately not inferred or silently joined; completeness and filter authority remain false. | Missing-target tests refuse. A future multi-period boundary requires its own milestone and review. |
| IB1D-R09 | P2 | Open - authority blocker | `73e87bc` | `SecForm4XmlSource.amends_accession` and caller provenance | Same-issuer wrong-target assertions and same-form XML-byte swaps can pass structural checks because neither the amendment link nor transport is authenticated from an official filing source. | Semantic audit traced both cases through the caller-asserted inputs; module documentation states the limitation. | Treating asserted linkage as canonical could replace or suppress the wrong event. | Retain exact source bytes and hashes, but permanently deny completeness and filtering authority. | Wrong/missing form, URL, retrieval, issuer, order, and target-presence mutations refuse; same-issuer semantic authenticity remains an explicit future gate. |
| IB1D-R10 | P3 | Open - deferred | `73e87bc` | `tests/test_insider_buying_sec_edgar_acceptance_snapshot.py` | IB-1D tests share the large IB-1C fixture module, increasing test ownership coupling. | Code audit noted the module-size increase; extraction would duplicate or broadly refactor private fixture builders. | Dedicated ownership would improve maintainability but does not change current safety behavior. | Deferred until shared fixture extraction is an owner-scheduled bounded refactor; no test was weakened. | Full combined module and nine-file suites pass. |

No open P0 or P1 finding remains in the committed IB-1D scope. The two open
P2 items are explicit blockers on future authority, not permissions to consume
the result canonically.

### 16.3 Implemented IB-1D boundary

`research/insider_buying/form4_amendment_reconciliation.py` composes a bounded
tuple of exact caller-supplied XML byte images with one public, raw-bound IB-1C
acceptance snapshot. Every source must have an exact acceptance tier and must
match accession, Form 4 or 4/A type, primary-document URL, retrieval not before
acceptance, and issuer CIK before the existing offline XML parser is called.
Duplicate or unknown sources, date-only evidence, self-links, missing or
non-original targets, cross-issuer links, reversed/equal acceptance order,
resource-cap excess, and inconsistent corpus/lineage inventories fail closed.

The chronology orders supplied amendments by exact acceptance instant rather
than accession. Its intervals are half-open: a supplied original is observed
from acceptance to the first supplied amendment, and the amendment state starts
at that exact boundary. Every supplied Form 4/A transaction must retain the
single `EXCLUDE_AMENDED_FILING` outcome. Original parser eligibility remains an
as-filed provisional classification in `as_filed_corpus`; it is not a canonical
selection. Boundary-free `Form4ObservedState` queries do not expose a future
amendment timestamp.

The deterministic identity binds the verified IB-1C snapshot and lineage hash,
parser commit, exact XML hashes and sizes, primary URLs, UTC retrieval times,
capture-commit assertions, and asserted amendment targets. Input order does not
change the result. Both `complete_amendment_coverage_verified` and
`canonical_filter_authorized` are hash-bound false, rejected if set true, and
returned as literal false by the validated result wrapper.

This is intentionally an in-memory QC/audit primitive. It adds no immutable
publisher and therefore does not add a fourth copy of the deferred I/O helper
set. It does not discover filings, authenticate caller provenance, prove XML
schema compatibility, prove every amendment was supplied, perform field-level
correction semantics, normalize transactions, aggregate lots, create a signal,
join an outcome, build an ETF portfolio, or run QuantConnect.

### 16.4 Counter-review timing conclusion

The SEC's filing-status guide states that Forms 3, 4, and 5, including their
amendments, receive the submission date when accepted by 10 p.m. ET. SEC
Release 33-8230 codified the same ownership-form exception in Rule 13(a)(4).
Therefore Claude's 18:00 and 20:00 ET next-day filing-date examples do not
describe valid ownership-form records, and IB1C-R15 is closed as a false
positive. The central `[filing-date 05:00Z, next-day 05:00Z)` guard and
accession-year check remain unchanged.

Synthetic regressions now pin valid Form 4 receipts at 18:00 and 21:59:59 ET
to the same filing date, reject a fabricated 18:00 Friday-to-Monday rollover,
and reject a post-22:00 receipt paired to an earlier filing day. These tests do
not establish an official schema, authenticated metadata, operating-hours
completeness, or real-package compatibility.

### 16.5 Verification and isolation

- Committed implementation snapshot: `73e87bc`.
- Combined IB-1C/IB-1D module: **189 passed, 2 platform-conditional skips in
  132.03s**.
- Exact nine-file Insider/import-boundary/hygiene/separation suite: **513
  passed, 7 platform-conditional skips in 210.92s**.
- Final focused boundary slice: **32 passed, 159 deselected in 27.48s**.
- Mutation/audit evidence: the initial interval, future-observation, ordering,
  amendment-activation, URL, retrieval, form, and issuer mutations were killed;
  both initial identity survivors were then killed; the parsed-cap deletion,
  forged-wrapper, and duplicate-lineage probes were caught. No mutation was
  retained and the final module remained byte-identical after audit.
- Three independent final read-only audits report no remaining P0-P3 finding
  in the implemented scope. Changed Python parses and compileall over the
  Insider package plus changed test exit 0. `git diff --check` is clean apart
  from repository line-ending notices.
- Only `research/insider_buying`, its Insider test module, and this lane record
  changed. No Trading App, Streamlit, shared execution, sibling strategy, or
  frozen project-wide document changed.
- Official SEC documentation was read only. No filing, package, API response,
  provider, credential, licensed row, outcome, QuantConnect job, broker,
  operator database, scheduler, UI, or order was accessed. **0 research
  looks.**

### 16.6 Residual gates and next authorized step

IB-1D does not complete IB-1 or blueprint section 19.4 step 3. It has no
official SEC XML/profile compatibility evidence, authenticated original-link
source, complete amendment inventory, cross-quarter lineage composition,
field-level correction/supersession semantics, canonical normalized row, or
downstream filtering authority. Same-issuer wrong-target and XML-swap risks
remain future-authority blockers, not accepted assumptions.

The next bounded Insider milestone, only after Claude reviews this exact pushed
snapshot and Codex counter-reviews every resulting commit, is to define and
validate authoritative amendment-link and multi-period evidence before any
canonical row replacement can exist. No live SEC ingest, outcome join, ETF
construction, QuantConnect job, broker action, or UI work is authorized.

For this round: commit this record, validate the exact committed tree with the
complete suite and whole-repository compileall, append the immutable validation
row, and make exactly one push. Then stop for Claude review.
