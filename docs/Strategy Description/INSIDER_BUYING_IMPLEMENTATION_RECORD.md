# Insider Buying ETF Strategy — implementation and session record

Status: **THE CODEX COUNTER-REVIEW `5db0f3d`, BOUNDED SYNTHETIC IB-3A
FORMULA DIAGNOSTICS `17e613d`, ITS AGGREGATE-BOUND CORRECTION `6c03d7e`, AND
RECORD `8f61557` ARE CLAUDE-REVIEWED AND ACCEPTED, `17e613d` AFTER A
TEST-ONLY CORRECTION (SECTION 51): COMMIT `94ea25c` PINS TWELVE PREVIOUSLY
UNTESTED IB-3A GUARDS, INCLUDING THE IB3A-R06 TRAP ISOLATION WHOSE OWN
REGRESSION DID NOT EXERCISE ITS DANGEROUS DIRECTION; NO PRODUCTION MODULE
CHANGED. ALL FOUR SECTION-49 CORRECTIONS TO SECTION 48 ARE ACCEPTED, TWO OF
THEM GENUINE ERRORS OF THIS REVIEWER (NINETEEN PRIVATE UPSTREAM IMPORTS, NOT
NINE; A RENAME FAILS LOUDLY WITH `ImportError`). THE ROUND SNAPSHOT IS
`8f61557..THIS RECORD COMMIT`; CODEX COUNTER-REVIEW OF THOSE COMMITS IS THE
NEXT GATE. IB-3A REMAINS SYNTHETIC EQUATION-CONFORMANCE EVIDENCE ONLY: NO
OFFICIAL SECURITY MASTER, `qc_symbol_id`, AUTHENTICATED AMENDMENT
SUPERSESSION, CANONICAL FILTERING, DEDUPLICATION, AUTHORIZED AGGREGATION OR
`$50,000` GATE, CANONICAL STOCK SCORE, CROSS-SECTIONAL NORMALIZATION, SEED
SELECTION, OUTCOME, ETF/QC, DEPLOYMENT, CAPITAL, BROKER, OR TRADING
AUTHORITY EXISTS. TWENTY-SEVEN AUTHORITY FLAGS ARE FALSE ON EVERY PUBLIC
OBJECT, `stock_score` IS HARD `None`, AND BOTH LOOK COUNTERS ARE EXACT ZERO.
FULL IB-2 AND CANONICAL IB-3 REMAIN INCOMPLETE AND BLOCKED ON THEIR DATA
AUTHORITIES.**

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
  non-derivative common equity or an equivalent ordinary share class, exact
  transaction code `P`, acquired (`A`), officer or director, direct ownership,
  with positive shares and price;
- preserve row/lot lineage, aggregate only the same reporting-owner identity,
  security identity, and transaction date, then apply the $50,000 minimum to
  the aggregate rather than to each XML row;
- public EDGAR acceptance time—not transaction date—as availability, with
  next-open execution; date-only data receives a conservative next-day rule;
- `ln(1 + purchase_value / 50,000)` event size, 20-trading-day half-life,
  30-trading-day lookback, winsorized cross-sectional z-score;
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

The current XML parser deliberately implements a narrower provisional
common-stock title grammar. Constructed `Ordinary Shares`, `Class A Ordinary
Shares`, and `Common Shares` variants remain quarantined; they must not be
admitted until IB-2 supplies deterministic point-in-time security-class
mapping and the blueprint's manual exception dictionary. This fail-closed
implementation boundary does not narrow the canonical contract above.

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
| 2026-08-30 | Codex validation | `fdf6f15` -> `fdf6f15` (exact tested snapshot; this validation-record commit follows) | IB-1D final exact-tree validation | Revalidated the committed counter-review, observation-only amendment chronology, tests, exports, and authoritative section 16 without changing product files. This later commit changes only this lane record. | Complete exact-tree suite: **5,685 passed, 9 skipped, 0 failed, 26 warnings in 1,302.61s (21m42s)**; whole-repository compileall including `research` exit 0; pre-validation active-document plus lane-record checks **64 passed**; IB-1C/IB-1D module **189 passed, 2 skipped**; nine-file suite **513 passed, 7 skipped**; worktree clean and `git diff HEAD --check` clean. Fixture and public-rule-documentation only; no filing, package, API, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, UI, or order access; **0 research looks**. | No new P0-P3 finding. The nine skips are platform-conditional and the 26 warnings are dependency/runtime notices. Exact snapshot `fdf6f15` stayed clean throughout validation. | Commit this validation row, rerun record-sensitive checks, confirm the remote remains `50bc867`, and make the round's single push. Claude independently reviews all three pushed commits before further Insider work. |
| 2026-08-30 | Claude review | `50bc867` -> this review snapshot | Independent review of the bounded IB-1D Form 4/A observation chronology and of the counter-review rejecting IB1C-R15 (`50bc867..e2b434c`, 3 commits) | Verified frozen-file isolation, dispositioned all three commits, re-tested the IB1C-R15 rejection against the unmodified module rather than accepting the citation, ran a ten-mutant authority-escape sweep over IB-1D, and closed two untested guards in the public result constructor. Adopted the mandated ten-column ledger. Full dispositions are in section 17. | Independent complete suite on the exact pushed tree `e2b434c`: **5,685 passed, 9 skipped, 0 failed, 25 warnings in 915.99s**, reproducing the recorded pass/skip figures; nine-file focused suite **515 passed, 7 skipped** and IB-1C/1D module **191 passed, 2 skipped**, both the recorded figures plus this review's two cases; complete suite on the exact final review tree: **5687 passed, 9 skipped, 25 warnings in 1129.47s (0:18:49)**; IB-1D mutation sweep **6 of 10 caught, 2 survivors explained as defence in depth, 2 gaps closed and then caught 2 of 2**; nine synthetic probes, no SEC or provider data; compileall exit 0; every module restored byte-identical to `HEAD`. No SEC/EDGAR, provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, or UI access; **0 research looks**. | IB1D-R11 (P3) fixed here: the result constructor's semantic rebuild and source-inventory hash binding had no test sensitivity because the only direct-construction test used a SimpleNamespace identity refused by the type check first. My IB1C-R15 is **withdrawn as a false positive**: Regulation S-T Rule 13(a)(4) exempts Forms 3/4/5 through 22:00 ET, so the guard is correct and unchanged; four further record defects of mine are accepted. IB1D-R10, IB1C-R16 and R-23 stay deferred. No test weakening; three deleted lines are docstring prose. | Codex counter-reviews these Claude commits, then may define authoritative amendment-link and multi-period evidence. Shared-surface P1 set unchanged under the owner's strategy-scope rule. |
| 2026-08-30 | Codex counter-review | `e2b434c..3f2024b` reviewed; `3f2024b` -> this counter-review snapshot | Counter-review of Claude's IB-1D result-constructor regressions and review record | Reproduced both new tests, independently rechecked the Rule 13(a)(4) timing premise, generalized the constructor audit into the XML/parser and public-result boundaries, and corrected three confirmed P2 data-integrity defects plus two P3 record defects. Changes remain limited to lane-owned Insider code, tests, and this record. | Red phase: **9 failed** across conflicting singleton fields, three misplaced-row shapes, forged identity/inventory, direct constructor, and parsed-row loss. Corrected targeted slice: **15 passed**; affected parser plus IB-1C/IB-1D modules: **291 passed, 2 platform skips in 162.19s**. Four reverse mutations were killed: singleton cardinality (2 failures), row inventory (3), parsed-corpus binding (1), and factory-only construction (1); every mutation was restored. No SEC/EDGAR/provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, UI, or order access; **0 research looks**. | `dceff74` accepted; `3f2024b` accepted after current correction. IB1D-CR06 through IB1D-CR08 (P2) and IB1D-CR09/10 (P3) are closed in section 18. The analogous IB-1A/B/C direct-dataclass pattern remains documented P3 debt because those public loaders already revalidate persisted state and a broad refactor is outside this counter-review. IB1D-R08/R09 remain authority blockers. | Commit the counter-review checkpoint. Then implement only the bounded offline multi-period/amendment-evidence contract; keep completeness and canonical-filter authority false and perform no external access or canonical row replacement. |
| 2026-08-30 | Codex implementation | `ad86df0` -> `e89293b` | IB-1E offline multi-period supplied-link evidence | Added deterministic composition of contiguous verified IB-1C periods, a non-official profile over amendment-link and primary-document-hash fields already inside IB-1C-bound metadata bytes, cross-period and same-quarter observation lineages, exact XML/link binding, sequential aggregate caps, factory-only identity/result boundaries, and literal-false official-link, completeness, and canonical-filter gates. Every supplied as-filed version is retained; no canonical row is produced. | Red collection failure before the contract existed; focused IB-1E **15 passed**; independent latest-tree IB-1C/IB-1D plus IB-1E **210 passed, 2 skipped**; ten-file Insider/record/import/hygiene/separation suite **539 passed, 7 skipped in 275.10s**; focused record plus IB-1E **16 passed**; Insider compileall and `git diff --check` clean apart from line-ending notices. Synthetic fixtures only; no SEC/provider/credential/licensed row/outcome/QC/broker/operator/scheduler/UI/order access; **0 research looks**. | IB1E-R01 and R02 (P2) and R03 (P3) were fixed before commit; two independent final reviews reported no remaining P0-P3 finding. IB1D-R08 is closed only for structural cross-period composition. IB1D-R09 remains an open authority blocker. IB1E-R04/R05 are deferred P3 integration/consolidation debt. | Validate exact commit `e89293b` with the complete suite and whole-repository compileall, append the immutable result, rerun record-sensitive checks, and push the counter-review, implementation, and validation-record commits together. |
| 2026-08-30 | Codex validation | `e89293b` -> `e89293b` (exact tested snapshot; this validation-record commit follows) | IB-1E final exact-tree validation | Revalidated the committed counter-review corrections, strict metadata helper, IB-1E code, tests, exports, and section 19 without changing product files. The later validation commit changes only this lane record. | Complete exact-tree suite: **5,710 passed, 10 skipped, 0 failed, 25 warnings in 2,290.57s (38m10s)**; whole-repository compileall including `research` exit 0; pre-commit focused lane suite **539 passed, 7 skipped**; focused IB-1E **15 passed**; final active-document, lane-record, and IB-1E checks **79 passed in 19.29s**; `git diff --check` clean apart from line-ending notices. Synthetic fixtures only; no filing, package, API, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, UI, or order access; **0 research looks**. | No new P0-P3 finding. The ten skips are platform-conditional and the 25 warnings are dependency/runtime deprecations. Exact snapshot `e89293b` stayed clean throughout the 38-minute run. | Commit this validation row, rerun record-sensitive checks, confirm the remote remains `3f2024b`, and make the round's single push. Claude independently reviews all three pushed commits before further Insider work. |
| 2026-08-31 | Claude review | `3f2024b` -> this review snapshot | Independent review of the IB-1D counter-review and the bounded IB-1E multi-period supplied-link evidence contract, after the four-lane merge to main (`3f2024b..cf136e2`; 9 of 194 commits touch this lane) | Verified the sync and ancestry, dispositioned every Insider commit including the main merge, re-probed all three P2 parser/identity corrections against the unmodified tree rather than reading the record, checked the new cardinality guard is not over-broad, and mutation-swept IB-1E's authority and join guards. Adopted the ten-column ledger. Full dispositions are in section 24. | Ten-file set (named exactly in 24.8) **543 passed, 7 skipped**, 550 collected versus 549 at the committed head; complete suite on the exact final review tree: **6791 passed, 13 skipped, 25 warnings in 8025.55s (2:13:45)** after repairing three stale-CRLF analyst spec artifacts in this worktree (first run **1 failed, 6790 passed, 13 skipped, 25 warnings in 1304.28s (0:21:44)**, the single failure being that host-local checkout artifact and not this review's change; see 24.7); IB-1E sweep **2 of 7 caught, 4 traced to masking guards, 1 gap closed and then caught**; six direct corrections probes including a routine two-transaction Form 4 that still parses; compileall exit 0; every module restored byte-identical to `HEAD`. No SEC/EDGAR, provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, or UI access; **0 research looks**. | Accepted all five counter-review findings against this reviewer, including two P2 parser defects in the canonical eligibility path that I missed by treating inherited IB-0 code as settled while reviewing a milestone that newly depends on it. IB1E-R06 (P3) fixed here: the supplied XML-to-acceptance issuer binding had no test sensitivity. IB1E-R07 (P3): the recorded ten-file composite is unnamed and unreproducible. Out-of-lane items, including R-01's partial overtaking by main's EXE-001 fix and the now-moot frozen-file regime, are documented in 24.7 and not fixed. | Codex counter-reviews these Claude commits, then may begin the next bounded Insider milestone. |
| 2026-08-31 | Codex counter-review + implementation | `cf136e25..1e3594e3` reviewed; `1e3594e3` -> `273b0da8` implementation snapshot (this lane-record commit follows) | Claude counter-review plus bounded IB-1F persisted two-period offline integration proof | Accepted Claude's issuer-binding regression, corrected its merge-aware review scope and combined-range diff evidence, and added a synthetic persisted Q4-to-Q1 proof through the real IB-1A publisher, IB-1B publisher/loader, IB-1C publisher/loader, and IB-1E call-time loader. The success path uses no loader substitution; independent parsed-path, raw-path, and receipt-to-upstream cross-wires refuse before XML parsing. No production code or authority flag changed. | Exact implementation tree `273b0da8`: complete suite **6,795 passed, 13 skipped, 0 failed, 26 warnings in 2,185.89s (36m25s)**; whole-repository compileall including `research` exit 0; final IB-1F module **4 passed in 25.87s**. Claude's issuer regression passed and its in-memory issuer-binding bypass was caught. All bytes and rows are synthetic; no filing, package, API, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, UI, or order access; **0 research looks**. | `f5ce0d41` accepted; `1e3594e3` accepted after current record correction. IB1E-CCR01 (P2) and IB1E-CCR02 (P3) are closed in section 25. IB1E-R04 is closed only as persisted synthetic integration debt; IB1F-A01/A02 (P3) were fixed before commit. IB1E-R07 remains open record-precision debt. IB-1, blueprint step 3, IB1D-R09, and every official-data or canonical-authority gate remain open. | Commit this lane record, rerun record-sensitive and diff checks, confirm the remote remains `1e3594e3`, and make the round's single push. Claude independently reviews both Codex commits before any further Insider milestone. |
| 2026-08-31 | Claude review | `1e3594e3` -> this review snapshot | Independent review of the IB-1E counter-review and the bounded IB-1F persisted multi-period integration proof (`1e3594e3..f3749ff3`, 2 commits) | Verified the sync and ancestry, dispositioned both commits, reproduced both counter-review findings against this reviewer by running the methods myself, and ran a differential mutation study to test whether the new integration proof earns its place rather than duplicating mocked coverage. **No correction was required and none was applied.** Full dispositions are in section 26. | IB-1F module **4 passed** and eleven-file collection **554 tests collected**, both reproducing the recorded figures exactly; complete suite on the exact reviewed tree: **6795 passed, 13 skipped, 25 warnings in 1257.15s (0:20:57)**; differential: a swapped parsed/raw upstream at the call-time loader **survives** the mocked-loader IB-1E module but is **caught** by IB-1F, confirming it closes the IB1E-R04 blind spot; merge-review re-verified with `--full-history` and second/first-parent lane-path comparisons; compileall exit 0; every module restored byte-identical to `HEAD`. All fixtures synthetic. No SEC/EDGAR, provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, or UI access; **0 research looks**. | Accepted both findings against this reviewer: IB1E-CCR01 (P2), where default history simplification hid two lane-carrying merges from my scoping command, and IB1E-CCR02 (P3) on diff-size scope. A sharper root cause is recorded in 26.3: a silently non-matching pathspec sat inside that command, the second such case in this lane, so scoping commands feeding a completeness claim must now be asserted non-empty and merge gates must use `--full-history`. One candidate IB-1F gap was verified as duplicate coverage and deliberately left unwritten (26.5). No test weakening; the range deletes no test. | Codex counter-reviews this review commit, then may begin the next bounded Insider milestone. |
| 2026-09-01 | Codex counter-review + implementation | `f3749ff3..e8756630` reviewed; `e8756630` -> `dbe7c14f` implementation snapshot (this lane-record commit follows) | Claude counter-review plus bounded provisional IB-0 Form 4 classification hardening | Accepted Claude's no-code review after correcting four current-record defects, then narrowed provisional common-stock recognition, expanded bounded price-range quarantine, made scalar/value XML grammar fail closed, and classified each referenced immutable footnote once without cross-footnote synthesis or unreferenced-footnote contamination. No official profile, canonical filter, security mapping, data ingest, signal, ETF, QC, or UI authority was added. | Form 4 module **182 passed**; exact named Insider/import-boundary PTY set **633 passed, 7 skipped**; three independent reviews found no remaining P0-P3 in scope, killed every requested dangerous mutation, and measured flat per-filing footnote classification with linear 2 MiB near-miss behavior. Required complete suite on exact `dbe7c14f`: **3 failed, 6,878 passed, 13 skipped, 25 warnings in 1,320.92s (22m00s)**; isolated PTY rerun made the Windows `git ls-files` handle failure pass and reproduced only two unchanged, out-of-lane sleeve fixed-clock assertions at the September 1 countdown boundary. Whole-repository compileall exit 0. Synthetic fixtures only; no filing, package, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, deployment, UI, or order access; **0 research looks**. | `e8756630` accepted after documentation correction; IB1F-CR01 through IB1F-CR04 close in section 27. IB0H-R01 through IB0H-R05 close five inherited dangerous-direction gaps in the bounded parser. IB0H-R06 remains open P3 future-boundary debt: a caller can forge the public transaction dataclass, so any future filter must consume only factory-created evidence and revalidate. Two out-of-lane, real-time-dependent sleeve test failures are documented and not fixed. Official/XSD compatibility and exhaustive natural-language interpretation are not claimed. | Commit this lane record, run final record/diff/secret checks, confirm the remote remains `e8756630`, and make exactly one combined push containing `dbe7c14f` plus the record commit. Then stop for Claude's independent review before another Insider milestone. |
| 2026-09-01 | Claude review | `e8756630` -> this review snapshot | Independent review of the bounded provisional IB-0 Form 4 classification hardening and its record (`e8756630..933378fb`, 2 commits, 0 merges) | Verified sync and ancestry with `--full-history` over asserted non-empty lane pathspecs, dispositioned both commits, confirmed all four counter-review findings against this reviewer against their source of authority, quantified the fail-open this milestone closes, and mutation-swept every guard it adds. **Accepted; no correction required.** Full dispositions and the mandatory rating are in section 28. | Form 4 module **182 passed**, reproducing the recorded figure; dangerous-direction mutation sweep of the eight new guards **8 caught, 0 survived**; title grammar probes 12 compound instruments refused and 11 canonical forms accepted with 0 failures either way; six instruments the previous substring predicate admitted are now refused; three genuine anti-synthesis splits produce no exclusion while the identical prose in one footnote still does; performance measured **linear at 0.06-0.17 us/char across a 16x size increase**, implying about 0.34 s for a maximal 2 MiB footnote; complete suite on the exact reviewed tree: **2 failed, 6879 passed, 13 skipped, 25 warnings in 1185.40s (0:19:45)**, whose failures are the out-of-lane sleeve fixed-clock assertions confirmed untouched by this range; record-sensitive gate **252 passed**; compileall exit 0; value-shaped secret scan **0 matches**; every module restored byte-identical to `HEAD`. Synthetic fixtures only; no filing, package, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, deployment, UI, or order access; **0 research looks**. | Accepted all four findings against this reviewer (IB1F-CR01 through CR04); their shared root cause is that I had treated GENERAL_CODE_REVIEW_INSTRUCTIONS as the whole process while CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS step 9 carries further mandatory report controls, so section 28 now supplies all nine. Two new P3 observations recorded and deliberately not fixed: IB0H-R07, the title allowlist refuses four of eight ordinary real-world variants (fail-closed, but it would shrink the real candidate set), and IB0H-R08, the per-footnote input budget is implicit at the 2 MiB envelope. IB0H-OOL01 independently confirmed out of lane and not fixed. Implementation quality rated **9/10**. No test weakening; the range removes no test. | Codex counter-reviews this review commit, then implements the next bounded Insider milestone. |
| 2026-09-01 | Codex counter-review | `933378fb..b0e39bb1` reviewed; `b0e39bb1` -> `cb8a46a4` correction snapshot (this lane-record commit follows) | Counter-review of Claude's provisional Form 4 hardening review; owner-directed stop before the whole-module audit | Independently reproduced the accepted hardening claims and every new review finding, then found a missed P2: nested `footnote` definitions crossed ID lineage and made retained text/regex work quadratic inside the raw 2 MiB envelope. Commit `cb8a46a4` now permits only one flat root-level footnote inventory and refuses ambiguous structure before classification. Per explicit owner sequencing, this round starts no new milestone; Claude reviews the complete Insider Buying module next. | Python **3.14.6**. Reviewed-parser red phase: **6 failed, 182 deselected** because all six expected structural refusals were absent. Corrected Form 4 module: **193 passed in 1.55s**. Exact named eleven-file Insider/import/hygiene/separation suite: **644 passed, 7 skipped in 407.87s (6m47s)**. Required complete suite on exact correction commit `cb8a46a4`: **2 failed, 6,890 passed, 13 skipped, 25 warnings in 2,002.55s (33m22s)**; the only failures are the two unchanged out-of-lane sleeve fixed-clock assertions. Whole-repository compileall exit 0. Synthetic local fixtures only; no filing, package, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, deployment, UI, or order access; **0 research looks**. | `b0e39bb1` accepted after correction. IB0H-CCR01 (P2) is fixed in `cb8a46a4`; IB0H-CCR02 (P2) closes Claude's omitted mandatory whole-repository compile; IB0H-CCR03 through CCR07 correct unsupported real-data/canonical wording, the materially false R08 safety framing, mutation/performance overclaims, wrong sleeve evidence, and incomplete validation metadata. Claude's pre-correction 9/10 is superseded; the corrected bounded snapshot is 9/10. | Commit this authoritative counter-review record, run final record/diff/secret/remote checks, and make the round's single push. Then stop: Claude performs the owner-directed complete Insider Buying module review before any new milestone. |
| 2026-09-01 | Claude full-lane review | `864030a2` -> this review snapshot | Owner-directed first-principles review of the entire Insider Buying lane (20 lane files; merge-aware inventory of **55 commits, 5 merges** from `c9dcdb64` to `864030a2`), superseding the narrow latest-range review | Verified the actual synchronized head (the owner's expected `933378fb` was stale), asserted every pathspec non-empty, dispositioned all 55 commits including every merge, read the complete 33-page blueprint from the hash-verified PDF using a stdlib-only extractor (no dependency added), and audited the current tree from first principles rather than from prior conclusions. **No code correction was required**; `cb8a46a4` had already closed the one P2 defect in range. Full detail in section 30. | Interpreter **Python 3.14.6**; all seven Insider modules plus import-boundary, module-hygiene, both project-separation suites and active-document: **713 passed, 7 skipped in 263.89s**; complete repository suite: **2 failed, 6890 passed, 13 skipped, 25 warnings in 1499.20s (0:24:59)**; failures: tests/test_sleeve_report.py::test_default_gain_review_is_fifty_percent_and_long_term_gated, tests/test_sleeve_report.py::test_every_lot_row_carries_the_tax_mechanism_fields; **whole-repository compileall exit 0** (the control I omitted last round); record-sensitive gate **263 passed**; adversarial probes covering footnote structure, title grammar, 18 decimal inputs, joint owners, Form 5 and exact-product arithmetic; 4 mutants on the new footnote guard (2 caught, 2 provably redundant); every module restored byte-identical to `HEAD`. No filing, package, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, deployment, or order access; **0 research looks**. | Reproduced and accepted the P2 I missed (IB0H-CCR01): on the tree I had accepted, a row referencing only `F2` inherited nested `F1` prose and was wrongly excluded - my isolation probes varied which footnote was referenced but never how footnotes were structured. Accepted CCR02/03/04/06/07; corrected one CCR05 sub-claim with evidence (each scaling series spans 16x; the quoted 32x compares different input shapes). New: **IBFL-01** (P3) the frozen contract narrows blueprint 2.1 item 2's "equivalent ordinary share class" and the grammar refuses `Ordinary Shares`/`Common Shares` - constructed strings, no filing inspected; **IBFL-02** (P3) section 1 says "30-day lookback" where blueprint 9.2 says 30 **trading** days; **IBFL-03** (P3) blueprint step 19.4.1 is unstarted and step 4's quarantine report does not exist. All prior open findings carried forward; IB0H-R08 withdrawn. Lane rated **8/10**. | Codex counter-reviews this review commit. No milestone started or authorized. |
| 2026-09-01 | Codex counter-review + implementation | Reviewed `864030a2..4a9ca17f`; implemented `4a9ca17f` -> `5ee2c040` -> this record commit | Counter-review Claude's owner-directed full-lane review and implement bounded **IB-1G evidence-bound provisional Form 4 disposition/quarantine report** | Accepted Claude's product-code assessment but corrected seven current-record defects, including its incomplete merge/commit inventory and the live blueprint contract wording. Added an offline report that accepts only exact factory-created IB-1E evidence, pre-bounds and revalidates every nested inventory and identity, reparses every supplied XML byte image, and emits one deterministic reason-coded row per transaction. It preserves all parser outcomes/diagnostics and calls only the singleton eligible outcome a provisional pre-aggregation candidate. It performs no aggregation or `$50,000` gate. Full detail in section 31. | Red phase: missing public IB-1G API raised `ImportError`; focused final module: **40 passed in 1.24s**; intermediate affected suite: **248 passed in 15.81s**; complete repository on committed `5ee2c040`: **2 failed, 6914 passed, 13 skipped, 25 warnings in 1191.32s (0:19:51)**, solely the two unchanged out-of-lane `tests/test_sleeve_report.py` failures; whole-repository `compileall`: **exit 0**. Final named lane/boundary and record suite: **737 passed, 7 skipped in 190.34s (0:03:10)**. Python **3.14.6**, pytest **9.1.1**. No filing, package, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, deployment, order, or UI access; **0 research looks**. | `4a9ca17f` accepted after current-record correction. IBFL-CR01..07 closed. IB1G-R01..03 and R06 closed during self/audit review; IB1G-R04 and R05 remain P3 deferred provenance/coupling debt. IB01-R05 remains open out of lane. No open P0-P2 defect remains in the new product-code diff. | Commit this record, make exactly one combined push, and stop for Claude to review the exact pushed range. |
| 2026-09-01 | Claude review | `4a9ca17f` -> this review snapshot | Independent review of the IB-1G provisional Form 4 disposition report and its counter-review handoff (`4a9ca17f..e2eca996`, 2 commits, 0 merges, 4 paths, 1,786 insertions / 24 deletions - every expected value matched) | Verified state and ancestry, dispositioned both commits, reproduced all seven counter-review findings against my section 30, and exercised every adversarial direction the owner named. One bounded correction applied. | Python **3.14.6**, pytest **9.1.1**; IB-1G module **40 passed** before and **41 passed** after the addition; named 12-file Insider/boundary suite (exact set in 32.8) **738 passed, 7 skipped in 349.53s**, the recorded 737 plus one; eleven dangerous-direction mutants across two batches; whole-repository compileall **exit 0**; complete suite: **3 failed, 6914 passed, 13 skipped, 25 warnings in 1445.00s (0:24:04)**; failures: tests/test_sleeve_report.py::test_default_gain_review_is_fifty_percent_and_long_term_gated, tests/test_sleeve_report.py::test_every_lot_row_carries_the_tax_mechanism_fields, tests/test_sleeve_report.py::test_report_carries_no_action_shaped_field; record gate **pending**; every module restored byte-identical to `HEAD`. Synthetic inputs only; no filing, package, provider, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, deployment, or order access; **0 research looks**. | Both commits **accepted**. IB-1G's guarantees are load-bearing: routing inversion, row duplication, non-deterministic ordering, candidate miscount, all four authority directions, and a future `ParsedTransaction` field escaping the fingerprint were each caught. **IB1G-R06 (P3) fixed here**: the eligible-plus-quarantine guard and the singleton routing decision had no test sensitivity - unreachable from today's parser, and verified correct when invoked directly - so a regression now pins them. All seven IBFL-CR findings against me confirmed, including that `d6d26e09` is a merge adding 23 lane lines over its first parent, which my section 30 wrongly described as a lane-identical carry; I add that its combined diff is empty, so the content came from the second parent rather than conflict resolution. IB1G-R04/R05 framings independently verified accurate. No test removed or weakened. Lane rating raised to **9/10** because the blueprint-fidelity deduction is closed. | Codex counter-reviews this review commit. No milestone started or authorized. |
| 2026-09-02 | Codex counter-review + implementation | `2ef057d6294ef26afcd49542fdf7432bc4f0aa59` -> `4361232412800286a78a189223f415fdd9a7f753` -> this record commit | Counter-review Claude's IB-1G review and implement bounded **IB-1H immutable provisional disposition-report snapshots** | Accepted Claude's additive eligible-coexistence regression after six append-only P3 record corrections. Added one canonical, immutable report snapshot per `report_id`; the loader requires exact IB-1E evidence, rebuilds through the public IB-1G builder, and accepts only canonical stored bytes equal to that rebuild. Added bounded JSON/resource validation and fail-closed filename, conflict, hard-link, redirect/reparse, coherent-forgery, authority, ordering, scalar, and detected-TOCTOU checks. No mapping, aggregation, `$50,000` gate, canonical filtering, outcome, ETF, QC, UI, or trading surface was added. Full detail is in section 33. | Python **3.14.6**, pytest **9.1.1**. Focused IB-1H: **45 passed, 1 skipped in 2.46s**; affected IB-1E/IB-1G/IB-1H/import boundary: **109 passed, 1 skipped in 17.09s**; named 13-file Insider/boundary suite: **783 passed, 8 skipped in 184.57s (0:03:04)**. Complete committed-tree suite: **3 failed, 6,959 passed, 14 skipped, 25 warnings in 1,209.15s (0:20:09)**; only the three unchanged out-of-lane sleeve fixed-clock failures reproduced. Whole-repository compileall including `research`: **exit 0**. Synthetic/local inputs only; no filing, real package, provider data, credential, licensed row, outcome, QuantConnect job, broker, operator database, scheduler, deployment, order, or UI access; **0 research looks**. | `2ef057d6` accepted after current-record correction; IB1G-CCR01..06 closed. IB1H-R01 P2 and IB1H-R04/R05 P3 closed before implementation commit. IB1H-R02/R03 remain open P3 filesystem/provenance limits; inherited IB1G-R04/R05 and IB1E-R05 debt remains open. No open P0-P2 defect remains in the new product-code diff. | Run the final record/diff/secret/remote gates, commit this record, make exactly one combined push, and stop for Claude to review the exact pushed range. |
| 2026-09-02 | Claude review | `8736b4a2` -> this review snapshot | Review of the IB-1H immutable provisional-report snapshots (`2ef057d6..8736b4a2`) and correction of one lane-specific drift defect | Verified isolation, authority-gate enforcement by direct inspection, and absence of network/float in the new module. Recomputed each finding's latest status rather than grepping for `Open`, correcting an earlier claim that `IB1E-R04` was stale. Compared every helper defined in more than one lane module and found the IB-1C/IB-1H hard-link guard missing from IB-1A and IB-1B. Full dispositions are in section 34. | Focused hard-link regressions IB-1A 3 passed and IB-1B 4 passed; combined lane and boundary suite **451 passed, 8 skipped in 302.98s**; record gates 70 passed; two mutation sweeps confirmed the new guards load-bearing in both directions with positive controls still passing, each module restored byte-exact; `git diff --check` clean; complete suite on code tree `5f880c5` **3 failed, 6,965 passed, 15 skipped in 47m03s**, the three failures being the unchanged out-of-lane sleeve-clock cases recorded as `IB0H-OOL01` and reproduced at `43612324` before these commits; `compileall` including `research/` exit 0. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, or UI access; **0 research looks**. | IB1H-R06 (P2) found and **fixed**: the `st_nlink != 1` guard adopted by IB-1C and IB-1H had never propagated to IB-1A and IB-1B, which had zero such checks while performing the same immutable publication and committed reload; 15 of 16 duplicated helpers already differ between copies and the duplication is fourfold, not the threefold recorded by `IB1C-R16`. Two process defects by this reviewer are recorded in 34.6. Out-of-lane and authorization-blocked findings documented, not fixed. | Codex counter-reviews these Claude commits, then may continue the bounded IB ladder. IB-1 remains incomplete; blueprint 19.4 step 1 unstarted. |
| 2026-09-02 | Codex counter-review | `8736b4a2..3f6c2676` reviewed; `3f6c2676` -> `a615304d` correction | Counter-review Claude's IB-1H review and propagated hard-link correction | Dispositioned both Claude commits, reproduced the claimed guard, compared all four sampled link-count phases against IB-1C/IB-1H, and generalized the audit to both immutable commit markers. Corrected the missing post-read/final-path checks and commit-marker opt-ins in lane-owned IB-1A/IB-1B code. Full findings are in section 35. | Runtime red probe: both reviewed readers returned bytes with final `st_nlink == 2`; regression red phase **6 failed, 2 passed**; corrected hard-link slice **13 passed**; complete corrected IB-1A/IB-1B modules **195 passed, 5 skipped in 76.69s**; `git diff --check` clean before commit. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator database, scheduler, UI, or order access; **0 research looks**. | `5f880c5a` and `3f6c2676` accepted after correction. `IB1H-CCR01` P2 is closed by `a615304d`; `IB1H-CCR02` through `IB1H-CCR06` are append-only record corrections. No out-of-lane code was changed. | Commit this counter-review record, then implement only the bounded zero-authority four-family gate in IB-1I. Permanent look/cell identities and their alpha split remain owner-decision-required. |
| 2026-09-02 | Codex implementation | `3f6c2676` -> `a615304d` -> `322350a3` -> `b3b202d2` -> this record commit | Completed Claude counter-review and bounded **IB-1I zero-authority four-family/QC-first research gate** | Preserved the accepted-after-correction counter-review, then added one frozen lane-local contract that binds the governing blueprint, immutable 2026-08-29/30 owner-directive commits, fixed four-lane family, exact `1/20` total and `1/80` lane ceiling, expiry/no-reallocation rule, shared holdout, canonical-family null rule, future IB-7 immutable-input boundary, empty permanent allocation/look inventories, and exact-zero external/operational authority. Two independent implementation audits found and drove corrections before commit. Full detail is in section 36. | Python **3.13.14**, pytest **9.1.1**. IB-1I **120 passed in 2.41s**; named Insider/boundary suite **848 passed, 8 skipped in 393.03s**; complete committed code tree `b3b202d2`: **3 failed, 7,093 passed, 15 skipped, 25 warnings in 2,939.96s (48m59s)**, exactly the three unchanged out-of-lane sleeve-clock cases; whole-repository compileall exit 0. No SEC/provider, credential, licensed row, outcome, QuantConnect upload/processing/job/backtest, broker, operator database, scheduler, deployment, order, or UI access; **0 research looks**. | IB1I-R01 through IB1I-R09 closed; final independent code audit reports no remaining P0-P3 finding in scope. Analyst `qc_first_plan.py`, the shared Strategy Description README, sleeve-clock failures, and shared/platform debt are documented but untouched. | Commit this record, run record/diff/secret/remote gates, make the round's single push, and stop for Claude to review every pushed commit after `3f6c2676`. |
| 2026-09-02 | Claude review | `3f6c2676` -> this review snapshot | Independent review of the completed hard-link invariants and the IB-1I zero-authority four-family research gate (`3f6c2676..b21baf7c`, 5 commits, 0 merges, 8 lane-owned paths) | Fast-forwarded the lane branch in place after finding the local checkout 7 behind and a strict ancestor - no branch switch or second worktree. Reproduced the hard-link P2 rather than reading it, recomputed every IB-1I headline claim, and mutation-swept both. Full dispositions in section 37. | IB-1I module **122 passed** (recorded 120 plus this review's two); exact named 12-file suite **920 passed, 8 skipped in 255.35s**; complete suite: **3 failed, 7096 passed, 14 skipped, 25 warnings in 1390.16s (0:23:10)**; failures: tests/test_sleeve_report.py::test_default_gain_review_is_fifty_percent_and_long_term_gated, tests/test_sleeve_report.py::test_every_lot_row_carries_the_tax_mechanism_fields, tests/test_sleeve_report.py::test_report_carries_no_action_shaped_field; whole-repository compileall **exit 0**; record gate over `test_insider_buying_implementation_record.py`, `test_active_document_consistency.py` and `test_insider_buying_preregistration.py` **192 passed**; hard-link phase mutants **4 of 4 caught**; IB-1I gate mutants **8 of 12 caught, 2 structurally masked, 2 fixed then caught**; ten hard-link probes across both boundaries; semantic hash recomputes to `f532eaf3...`; 4 x Fraction(1,80) == Fraction(1,20) exactly with no float in the module; the blueprint SHA-256 constant equals the actual PDF on disk; eight authority escalations refused. Python 3.14.6. No SEC/provider data, credential, licensed row, real package, outcome, QuantConnect, broker, operator database, scheduler, deployment, or order; **0 research looks**. | All five commits accepted, two after correction. **IB1I-R01** (P3) fixed here: the four-lane-maxima-equal-shared-FWER equation and the cutoff-precedes-holdout ordering had no test sensitivity because every field is pinned to its own constant, so both guards could be deleted with the module green; two constant-drift regressions added and mutation-verified. **IBREC-01** (P3) fixed here: sections 36 and 35 sat between sections 11 and 12, out of numerical and chronological order, and were moved after section 34 with byte-identity verified. **IB1I-N01** (P3) records two mutation survivors that are structurally masked, not gaps. No test removed or weakened. | Codex counter-reviews this review commit. No milestone started. |
| 2026-09-03 | Claude review | `7c9e6f53` -> `1b836ff6` (test correction) -> this review record | Review of the IB-1I counter-review and the IB-2A observed identity inventory (`2c392cd3..7c9e6f53`), with mutation testing of the eight owner-named dangerous directions | Verified isolation, authority enforcement by direct inspection, and observed-only scope by keyword sweep and AST test. Reproduced the focused 97 and the ten-file 894 exactly. Ran twenty targeted mutants (13 caught, 7 survived), classified every survivor, and pinned the four genuinely untested guards with five additive tests, each mutation-verified. Full detail in section 40. | Focused IB-2A 101 passed; IB-1H file 46 passed, 1 skipped in 17.90s; complete ten-file Insider suite plus two boundary files 918 passed, 8 skipped in 278.70s (0:04:38) (913 - 11 - 8 = 894 reproduces Codex's figure); record-sensitive six-file gate 124 passed; complete repository suite 3 failed, 7,197 passed, 15 skipped, 25 warnings in 4,272.30s (1:11:12), the three failures being the out-of-lane sleeve-clock cases recorded as `IB0H-OOL01`; every mutated module restored byte-identical; `git diff --check` clean. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, deployment, capital, or trading access; **0 research looks**. | IB2A-CR01 (P3) **fixed**: four guards on named directions - the post-reparse re-fingerprint, the constructor replay binding disposition to outcomes, the strict-order amendment binding, and all three owner-uniqueness clauses together - could be deleted with the suite green; now pinned. IB2A-CR02 (P3): the handoff's "289 passed" gate is not in the record and the six-file gate yields 124; "22 passed, 75 deselected" has no selector. IB2A-CR03 (P3): `IB1D-CR07A` is carried forward but has no ledger row. IB2A-CR04 (P3): one mid-call re-hash remains untested and is recorded. IB2A-CR05 (P3): the 2026-09-03 push added no section-5 row. No production module changed. | Codex counter-reviews these Claude commits, then may continue the bounded ladder. IB-2A stays observed-only; IB-1 remains incomplete. |
| 2026-09-06 | Codex counter-review | `7c9e6f53..11d894b6` reviewed; this counter-review snapshot follows | Counter-review Claude's IB-2A tests/record and the owner-directed shared bug-fix integrations | Dispositioned all 12 linear commits, independently reproduced the lane tests and shared provenance, closed the remaining IB-2A report-rehash test gap, corrected three review/record claims append-only, and documented shared residuals without changing shared code. | IB-2A **102 passed**; new re-hash regression passed green, failed under the exact one-line suppression, and passed after restoration. Eight-file focused review set: **394 passed, 3 skipped, 2 known shared-EOL checkout failures**. Four cherry-picks have exact source patch IDs; final integration-record blob matches main. No external/provider/outcome/QC/broker/operator/scheduler/deployment access; **0 looks**. | Accepted after correction. `IB2A-CCR01` closes the lane test gap. `IB2A-CCR02..05` correct/close record issues. `IBSH-CCR01..04` are shared/out-of-lane P3 observations documented only. | Commit the counter-review, then implement bounded zero-authority IB-2B before the round's one combined push. |
| 2026-09-06 | Codex counter-review + implementation | `7c9e6f53..11d894b6` reviewed in `d62c063`; IB-2B `8928487` -> `9fb017c`; this record commit follows | Counter-review plus bounded IB-2B SEC entity grouping | Dispositioned all 12 incoming commits, closed the remaining IB-2A report-rehash test gap, documented five shared findings without changing shared code, and implemented factory-bound issuer/reporting-owner grouping with named attribution quarantine, original/amended lineage retention, exact one-row transaction attribution, finite resource limits, and zero authority. Final audit reproduced and corrected an ABA provenance race and directly pinned the validated-snapshot guards. | Counter-review: IB-2A **102 passed**; focused review **394 passed, 3 skipped, 2 known shared-EOL failures**. IB-2B focused final gate: **179 passed**. Exact committed lane gate at `9fb017c`: **1,054 passed, 8 skipped, 0 failed in 203.89s**. Initial exact `8928487` repository suite: **2 failed, 7,254 passed, 15 skipped, 25 warnings in 2,731.11s**, solely the two known shared EOL failures. A final corrected-tree repository run was stopped at **56%** on the owner's instruction to push; no failure marker had appeared. Whole-repository compileall exit **0**; `git diff --check` clean apart from line-ending notices. Python **3.13.14**. No SEC/provider endpoint, credential, licensed row, real filing, outcome, QuantConnect, broker, operator database, scheduler, deployment, order, or UI access; **0 research looks**. | Counter-review accepted after correction. `IB2B-R01..R12` are closed or explicitly accepted below. `IBSH-CCR01..05` remain shared/out of lane and were documented but not fixed; this corrects the prior row's truncated `IBSH-CCR01..04` range append-only. | Make this round's single push, then Claude reviews every commit in `11d894b6..HEAD`; no later milestone starts before that review and Codex counter-review. |
| 2026-09-07 | Claude review | `0027d57d` -> `ff9d17f6` (test correction) -> `532e4cde` (review record) -> this hash-naming commit | Independent review of the IB-2A counter-review and the bounded IB-2B SEC entity grouping (`11d894b6..0027d57`, 4 commits, 0 merges, 6 lane-owned paths), with adversarial mutation of the eleven owner-named directions | First Insider review on the owner's Mac: built the Python 3.13.15 venv from the pinned requirements after the system interpreter ran zero tests. Fast-forwarded 19 commits to the exact remote head, dispositioned all four commits, reproduced every counter-review provenance claim (4 of 4 stable patch IDs, blob equality, absent "289", `IB1D-CR07A` defined), reconstructed the unnamed 1,062-test lane gate, ran 33 targeted mutants (12 caught, 21 survived), classified every survivor, and pinned fourteen untested guards with twelve additive tests (23 cases), each mutation-verified. Full detail in section 44. | Pushed tree: focused IB-2A/IB-2B **179 passed** (reproduces); eleven Insider files **985 passed**; reconstructed 13-file gate **1,062 collected**; complete suite **2 failed, 7,271 passed, 38 skipped, 28 warnings in 481.19s (0:08:01)**, both failures machine-local or load-induced and passing standalone (IBSH-CCR06, IBSH-CCR07). Final tree: IB-2B file **99 passed**; IB-2A plus IB-2B **202 passed**; lane gate plus boundary and separation suites **1,131 passed in 18.79s**; complete suite **7,296 passed, 38 skipped, 28 warnings, 0 failed in 417.61s (0:06:57)**; whole-repository compileall exit **0**; `git diff --check` clean. Python 3.13.15, pytest 9.1.1. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, deployment, capital, or trading access; **0 research looks**. | All four commits accepted, three after correction. **IB2B-CR01** (P3) fixed: fourteen guards on the named directions - grouping-level attribution consistency, single-owner binding, row-level quarantined-with-owner, output amendment-to-original binding, acceptance ambiguity, owner and transaction contiguity, transaction-to-issuer-candidate link, identity count partition, upstream projection depth/text/node, and two direct upstream-revalidation refusals - could be deleted with the file green; now pinned. IB2B-CR02 (P3): the A-to-B-to-A regression is single-threaded, not "two-thread". IB2B-CR03 (P3): the 1,054/8 gate names no file set. IB2B-CR04 (P3): the attribution rule is implemented twice; drift fails closed. IB2B-CR05: six survivors classified as redundant layers. IB2B-CR06 (P3): the counter-review ledger row understates IBSH-CCR01/02 to P3. IBSH-CCR06 and IBSH-CCR07 (P3, shared): `.DS_Store` not ignored; load-sensitive UI AppTest timeout. No production module changed; no test removed or weakened. | Review commits are local to the lane branch and not pushed (the owner authorizes pushes). Owner pushes or authorizes; Codex counter-reviews. No milestone started. |
| 2026-09-07 | Codex counter-review + implementation | `0027d57..a898be5` reviewed; correction `c74a575`; IB-2C `3a5ec9f`; this lane-record commit follows | Counter-review of all three Claude commits plus bounded offline IB-2C point-in-time security mapping | Dispositioned every incoming commit, consolidated the duplicate IB-2B owner-attribution primitive, corrected the prior record append-only, added an exact process-local IB-2B provenance seal, and implemented exhaustive transaction-to-security/title/ticker mapping from caller-supplied dated reference intervals. The mapping is deterministic, replayed, resource-bounded, point-in-time sliced, CIK scoped, amendment-lineage retaining, and zero-authority. Full detail is in section 45. | Incoming exact head: IB-2B **99 passed** and named lane/boundary gate **1,131 passed**. Final code tree: IB-2C **68 passed**; IB-2B plus IB-2C **169 passed**; twelve Insider files plus active-document and module-hygiene gates **1,155 passed**; complete repository **7,366 passed, 38 skipped, 26 warnings, 0 failed in 360.48s**; whole-repository compileall exit 0; diff checks clean. Material reverse mutation: **1 failed as expected**, then **1 passed** after exact authority-guard restoration. Synthetic fixtures only; no research/data-system access; **0 research looks**. | All incoming findings are accepted, corrected, closed, or explicitly retained as shared debt. `IB2B-CR04` is fixed in `c74a575`; record precision issues are corrected in section 45. IB2C-R01..R12 are closed; IB2C-G01 explicitly defers QC-symbol/official-security-master completion. No open P0-P3 finding remains in the new lane code. Shared findings remain documented without changes. | Make the round's single combined push. Claude then independently reviews every commit in `a898be5..remote HEAD` on this same branch; Codex counter-reviews every resulting Claude commit before any later milestone. |
| 2026-09-07 | Claude review | `d6f43bd8` -> `1496244` (correction) -> this review record | Independent review of the IB-2B counter-review, the bounded IB-2C point-in-time security mapping, and its record (`a898be5e..d6f43bd8`, 3 commits, 0 merges, 6 lane-owned paths), with adversarial mutation of the thirteen owner-named directions | Fast-forwarded to the exact remote tip, dispositioned all three commits, reproduced every counter-review record correction (13 functions / 23 cases from 76->99 collected; single-thread A-to-B-to-A; 1,062 collected from the eleven then-existing Insider files plus active-document and module-hygiene at `9fb017c`; IB2A-CR04/CR05 closed in 42.2; three commits pushed), verified one shared owner-attribution primitive, ran a 20,000-case randomized oracle against the listing-overlap validator (0 mismatches, both `date.max` probes correct), and ran 38 targeted mutants (24 caught, 14 survived, 0 invalid). Eleven survivors were genuine gaps and are now pinned or fixed; three are proven redundant/unreachable layers. Full detail in section 46. | Pushed tree `d6f43bd8`: complete suite **7,366 passed, 38 skipped, 28 warnings, 0 failed in 438.58s (0:07:18)** (Codex recorded 26 warnings; the two extra are environment notices); IB-2C **68 passed**, IB-2B+IB-2C **169 passed**, twelve Insider files + active-document + module-hygiene **1,155 passed** - all three reproduce exactly. Final tree: IB-2C **80 passed**; IB-2B+IB-2C **181 passed**; lane gate + import boundary **1,178 passed in 8.97s**; complete suite **7,378 passed, 38 skipped, 28 warnings, 0 failed in 401.89s (0:06:41)**; whole-repository compileall exit **0**; `git diff --check` clean. Python 3.13.15, pytest 9.1.1. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, deployment, capital, or trading access; **0 research looks**. | All three commits accepted, `3a5ec9f` after correction. **IB2C-CR01** (P3) fixed in `1496244`: the IB-2C row constructor accepted `SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED` beside a quarantine outcome with no owner, a shape IB-2B refuses; replay passes owner outcomes through, so the constructor was the only guard (red without the clause, green with it). **IB2C-CR02** (P3) fixed in `1496244`: ten guards could be deleted with the file green - row amendment lineage, mapped-row completeness, quarantined-row partial mapping, both owner-promotion shapes, canonical row order, row/upstream id uniqueness, manual-count binding, preflight-before-projection ordering (IB2C-R09's claim was not test-distinguishable), and the reference projection node and depth bounds - now pinned by nine additive tests (12 cases), each mutation-verified. IB2C-CR03 (P3, open): `reference_sha256` is a caller-asserted label bound only by shape, not to the captured reference content. IB2C-CR04 (P3, open, design limit): child intervals must sit inside one parent record, not the union of adjacent records. IB2C-CR05 (P3, open, nit): the module has no `__all__`. IB2C-N01..N03 are notes (tz database dependency, warning-count environment delta, three survivors proven redundant/unreachable). No production behavior weakened; no test removed or weakened. | Codex counter-reviews `1496244` and this record commit. `qc_symbol_id` and an official point-in-time security master remain deferred (IB2C-G01). Full IB-2 and IB-1 remain incomplete; no milestone started or authorized. |
| 2026-09-08 | Codex counter-review + implementation | `6383019c` -> this record commit (`611dceda` counter-review correction; `68a70459` IB-2D; this record) | Counter-reviewed both Claude IB-2C commits, corrected four section-46 precision defects append-only, closed IB2C-CR03..05, and implemented bounded IB-2D provisional lot diagnostics | Accepted `1496244` and `6383019` after record correction; documented the external-reference hash contract, single-parent interval normalization, and exact IB-2C export surface; added exhaustive evidence-bound provisional lot rows/groups, complete supplied-amendment-family quarantine, exact Decimal aggregation diagnostics, and the non-authoritative post-grouping `$50,000` comparison. No canonical filter, supersession, deduplication, authorized aggregation, or operational behavior was added. | IB-2C **84 passed**; IB-2D **83 passed**; IB-2A through IB-2D **371 passed**; those four stages plus hygiene/import boundaries **390 passed**; lane gate **1,265 passed**; complete suite **7,465 passed, 38 skipped, 26 warnings, 0 failed in 359.84s (0:05:59)**; compileall exit 0; diff/status clean. No SEC/provider/credential/licensed-row/outcome/QC/broker/operator-database/scheduler/deployment/capital/order/trading access; **0 research looks**. | IB2C-CR01/02 accepted fixed; IB2C-CR03..05 and IB2C-CCR01..04 closed. IB2D-R01..R05 P2 and IB2D-R06..R11 P3 all corrected and red/green pinned before `68a7045`; final audit found no open new P0-P3. Existing lane gates and shared/out-of-lane findings remain open and unchanged. | Push this exact three-commit round once. Claude independently reviews `6383019c..THIS RECORD COMMIT` on the same branch; Codex counter-reviews every Claude commit before another milestone. |
| 2026-09-08 | Claude review | `84c9ebe1` -> `5655759` (test correction) -> this review record | Independent review of the IB-2C counter-review correction, the bounded IB-2D provisional lot diagnostics, and its record (`6383019..84c9ebe1`, 3 commits, 0 merges, 6 lane-owned paths), with adversarial mutation of the owner-named directions | Fast-forwarded to the exact remote tip after a one-minute remote watch fired on Codex's push, dispositioned all three commits, verified the exception hierarchy behind the private IB-2A imports (`ContractError` is a `ValueError`, so every upstream refusal is normalized by the public builder), confirmed the IB-1G rule the IB-2D row constructor re-derives (candidate only when outcomes are exactly `ELIGIBLE_FOR_LOT_AGGREGATION`), accepted all four section-47 corrections to section 46, verified the IB2C-CR03..05 closures, and ran 32 targeted mutants on IB-2D (11 caught, 19 survived, 1 invalid string on the first pass; 0 invalid after correction). Fourteen survivors were genuine untested guards and are now pinned; six are proven redundant or unreachable layers. Full detail in section 48. | Pushed tree `84c9ebe1`: complete suite **7,465 passed, 38 skipped, 28 warnings, 0 failed in 387.51s (0:06:27)** (Codex recorded 26 warnings); IB-2C **84 passed**, IB-2D **83 passed**, IB-2A..IB-2D **371 passed**, plus hygiene/import boundary **390 passed**, thirteen Insider files + active-document + module-hygiene **1,254 passed** (+ the 11-test import-boundary file = Codex's **1,265**) - every figure reproduces. Final tree: IB-2D **92 passed**; IB-2A..IB-2D **380 passed**; lane gate + import boundary **1,274 passed in 10.22s**; complete suite **7,474 passed, 38 skipped, 28 warnings, 0 failed in 396.39s (0:06:36)**; whole-repository compileall exit **0**; `git diff --check` clean. Python 3.13.15, pytest 9.1.1. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, deployment, capital, or trading access; **0 research looks**. | All three commits accepted, `68a7045` after a test-only correction. **IB2D-CR01** (P3) fixed in `5655759`: fourteen guards could be deleted with the file green - the SINGLE-beside-quarantine owner clause with both owner fields `None` (its only test was masked by the owner-field clause), parser/identity disposition binding, row-id and group-key binding, group non-positive totals, member-id order and uniqueness, one-key-two-issuers aggregation refusal, identity partition and group-count bounds, the Decimal digit bound, non-text projection keys, family-inventory order and uniqueness, mapping-row-id uniqueness, and the pair of final evidence rechecks - now pinned by nine additive tests, each mutation-verified. **IB2D-CR02** (owner decision, open): IB-2D introduces the lot-aggregation arithmetic and the exact `$50,000` comparison into code; only hard-false authority fields and naming separate the diagnostic from the operative post-aggregation gate, and the prior review handoffs required confirming that neither was *added*. Recorded for the owner; no code change. IB2D-CR03 (P3, open): IB-2D imports nine private names including three upstream factory tokens, so the process-local trust boundary is shared across four modules. IB2D-N01..N04 are notes (six redundant/unreachable survivors with proofs; the 1,265 gate includes the import-boundary file; warning-count delta; sibling-test imports rely on the repo root being importable). No production behavior changed; no test removed or weakened. | Codex counter-reviews `5655759` and this record commit; the owner decides IB2D-CR02. `qc_symbol_id`, an official security master, and authenticated amendment supersession remain deferred. Full IB-2 and IB-1 remain incomplete; no milestone started. |
| 2026-09-08 | Codex counter-review | `84c9ebe1..9a93d09` reviewed; this counter-review record commit follows | Claude IB-2D counter-review | Counter-reviewed both Claude commits, accepted the additive IB-2D test hardening, and corrected the review's mutation accounting, guard classification, scope-gate claim, private-import inventory, and open-lane-finding disposition append-only in section 49. No production code changed. | Exact received/remote head `9a93d09`; IB-2D **92 passed**; IB-2C + IB-2D **176 passed**; complete thirteen-file Insider + active-document + module-hygiene + import-boundary gate **1,274 passed**. Five representative in-memory reverse mutations went red and restored green. No SEC/provider/credential/licensed-row/outcome/QC/broker/operator-database/scheduler/deployment/capital/order/trading access; **0 research looks**. | `5655759` accepted with no new finding; `9a93d09` accepted after four P3 record corrections. IB2D-CR01 is accepted fixed; CR02 is closed as a non-blocking scope note; CR03 is closed as intentional design coupling. IB2D-CCR01..04 are closed in section 49. No P0-P3 finding remains open in the incoming range. | Keep this checkpoint local. Do not invent IB-2E or start canonical IB-3. Owner defines the next bounded offline IB-2 contract or expressly authorizes the coordinated security-master/amendment audit; implementation and the round's one combined push then continue. |
| 2026-09-09 | Codex counter-review + implementation | `9a93d095..5db0f3d1` counter-reviewed; `17e613d4` IB-3A; `6c03d7e7` correction; this record commit follows | Claude IB-2D counter-review plus bounded synthetic/offline IB-3A stock-signal formula diagnostics | Accepted both Claude commits after the append-only section-49 corrections, then applied the owner's express "implement the next milestone, then push" direction only to a synthetic caller-age equation-conformance slice. Added factory-sealed events, fixed 50-digit Decimal size/freshness/event-score equations, inclusive `$50,000` and age-30 routing with all rows retained, exact raw-score summation, separate buyer/role/date/dollar breadth, canonical-order/hash replay, resource bounds, duplicate post-lot-key refusal, explicit caller-declared role provenance, and hard-unavailable `stock_score`. Exact IB-2D results are refused before formula work. | Focused IB-3A **142 passed**; complete Insider/active-document/module-hygiene/import-boundary lane gate **1,416 passed in 12.30s**; complete exact-final-tree repository suite **7,616 passed, 38 skipped, 26 warnings, 0 failed in 411.45s (0:06:51)**; whole-repository compileall including `research` exit 0; source compilation and `git diff --check` clean. Red/green evidence and hashes are in section 50. No SEC/provider/credential/licensed-row/real-filing/outcome/QC/broker/operator-database/scheduler/deployment/capital/order/trading access; **0 research looks**. | `5655759` accepted with no finding; `9a93d09` accepted after four P3 record corrections. IB3A-R01 through R08 are closed; the post-commit mixed-exponent P2 is fixed in `6c03d7e` and independently reproduced red/green. Three independent final audits report no open P0-P3 finding. Full IB-2/canonical IB-3 remain blocked on official security-master/`qc_symbol_id`, authenticated amendment, PIT identity/classification, calendar, and role-normalization authority. | Commit this lane record and make the round's one push to `origin/codex/strategy-insider-buying`. Claude independently reviews every commit in `9a93d09..PUSHED_HEAD` on this same branch; Codex counter-reviews every Claude commit before any later milestone. |
| 2026-09-10 | Claude review | `8f61557` -> `94ea25c` (test correction) -> this review record | Independent review of the IB-2D counter-review, the bounded synthetic IB-3A formula diagnostics, its aggregate-bound correction, and the record (`9a93d09..8f61557`, 4 commits, 0 merges, 4 lane-owned paths), with adversarial mutation of the owner-named directions | Fast-forwarded to the exact remote tip and dispositioned all four commits. Recomputed the numeric-policy hash, derived the 774-digit aggregate bound from first principles (773 required, slack 1, below the shared 4,096 ceiling), reproduced IB3A-R08 as a real defect (512- and 763-digit totals both exceeded the old 272-digit cap) and its fix against an exact-sum oracle, checked the formulas against an independent direct-exponential oracle, confirmed ambient-context and boundary behavior, and ran 64 targeted mutants plus 10 combined mutants. Twelve survivors were genuine untested guards and are now pinned; thirteen are proven redundant or unreachable. Full detail in section 51. | Pushed tree `8f61557`: complete suite **7,616 passed, 38 skipped, 28 warnings, 0 failed in 485.90s (0:08:05)** (Codex recorded 26 warnings); focused IB-3A **142 passed**; lane/boundary gate **1,416 passed** - every recorded figure reproduces exactly. Final tree: IB-3A **162 passed**; lane/boundary gate **1,436 passed in 11.97s**; complete suite **7,636 passed, 38 skipped, 28 warnings, 0 failed in 440.88s (0:07:20)**; whole-repository compileall exit **0**; `git diff --check` clean. Python 3.13.15, pytest 9.1.1. No SEC/provider, credential, licensed row, outcome, QuantConnect, broker, operator-database, scheduler, deployment, capital, or trading access; **0 research looks**. | All four commits accepted, `17e613d` after a test-only correction. **IB3A-CR01** (P3) fixed in `94ea25c`: twelve guards could be deleted with the file green, most importantly the explicit Decimal `flags=[]`/`traps=[]` that isolate a trapping `DefaultContext` - the IB3A-R06 regression sets every trap to `False`, the harmless direction, so a trapping context provably refused a valid age-one event with the guard removed while all 142 tests passed - and the sealed-event fingerprint comparison, whose own named test forges a new object and is therefore caught by `registered is None`, leaving the in-place equal-valued representation change provably accepted. The other ten are contribution routing, contribution/breadth/identity replay, canonical event order, the result raw-score and stock-key bindings, breadth count-to-inventory binding, the breadth buyer-count bound, and identity count consistency. Thirteen additive tests (20 cases), each mutation-verified; six previously surviving combined pairs are now caught. **IB3A-CR02** (P3, open, record precision): the pre-commit red/green evidence cited for IB3A-R01..R07 is not independently reproducible because those corrections were squashed into `17e613d` before commit, so the final guards were verified by mutation instead. IB3A-N01..N04 are notes (freshness split-vs-direct divergence of 2.4e-48 relative at age 10,000, disclosed by the frozen evaluation string; thirteen classified survivors; the warning delta; the unreachable `_runtime_value` repr fallback). All four section-49 corrections accepted, two being genuine errors of this reviewer. No production module changed; no test removed or weakened. | Codex counter-reviews `94ea25c` and this record commit. `qc_symbol_id`, an official security master, authenticated amendment supersession, an authoritative calendar, and an authorized role taxonomy remain deferred. Full IB-2 and canonical IB-3 remain incomplete; no milestone started. |

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
- Complete exact-tree suite at committed record snapshot `fdf6f15`: **5,685
  passed, 9 platform-conditional skips, 0 failed, 26 dependency/runtime
  warnings in 1,302.61s (21m42s)**.
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
  in the implemented scope. Whole-repository compileall including `research`
  exits 0. `git diff --check` is clean apart from repository line-ending
  notices, and the exact tested snapshot remained clean.
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

For this round: commit this immutable validation row, rerun record-sensitive
checks, verify the remote remains the reviewed `50bc867` base, and make exactly
one push. Then stop for Claude review.
## 17. Claude review - IB-1D observation chronology (2026-08-30)

Reviewer: Claude, Insider Buying lane review session, dedicated worktree pinned
to this branch. Range reviewed: `50bc867..e2b434c` (three commits). The remote
was fetched first, the local head confirmed identical to
`origin/codex/strategy-insider-buying`, and `50bc867` confirmed an ancestor, so
no published history was rewritten. No `git switch`; no other lane, checkout, or
branch touched.

This section adopts the ten-column ledger mandated by
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` section 2. Section 16
correctly recorded that earlier Claude sections used a four-column table
instead; that is corrected here rather than only acknowledged.

### 17.1 Isolation verification

All thirteen frozen files were checked individually across the range and are
untouched: Action Plan, Session Handoff, direction record, parallel workflow,
Strategy Description README, data-source register, both sibling lane records,
`requirements.txt`, `config.py`, `CLAUDE.md`, `AGENTS.md`, and `pytest.ini`.
The range changes four files, all lane-owned: this record,
`research/insider_buying/__init__.py`, the new
`research/insider_buying/form4_amendment_reconciliation.py`, and the Insider
acceptance test module. Nothing under `assistant/`, `execution/`, `risk/`,
`scripts/`, `signals/`, `strategies/`, `data/`, or `backtest/` references
`research.insider_buying`. No SEC/EDGAR, provider, credential, licensed row,
outcome, QuantConnect, broker, operator-database, scheduler, or UI access
occurred. **0 research looks.**

### 17.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `73e87bc` | **Accepted after correction.** | The IB-1D chronology is observation-only by construction and its authority gates hold under adversarial mutation. Corrected here: two guards in the public result constructor had no test sensitivity (IB1D-R11). No production change was required. |
| `fdf6f15` | **Accepted.** | The counter-review is correct on every point it raises, including the rejection of my IB1C-R15 and four record defects of mine. Its ledger uses the mandated ten-column shape and retains all seventeen findings. |
| `e2b434c` | **Accepted as validation of the exact implementation tree.** | Its complete-suite, nine-file, and module figures were each reproduced (17.6). It changes only this record. |

### 17.3 Counter-review findings against Claude

All five findings raised against this reviewer are confirmed and accepted. None
is disputed. Each was verified independently rather than accepted on the
strength of the record.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1D-CR01 / IB1C-R15 | P2 | Closed - my false positive | `50bc867` | Record section 15.5 | I claimed the general 17:30 ET rollover applies to Form 4, so routine after-hours filings would refuse and real ingest would fail. The premise is wrong and the finding would have driven a needless widening of a correct guard. | Regulation S-T Rule 13(a)(4), adopted in Release 33-8230, exempts Forms 3, 4, 5 and their amendments through 22:00 ET. Re-probed with the correct pairings: 18:00 ET and 21:59:59 ET against a same-day filing date are both **accepted**, and my Friday-18:00-to-Monday pairing is an input combination that cannot occur. | A review finding must not rest on an unverified domain premise; acting on it would have weakened accession-to-date lineage. | Finding withdrawn. No production change was made or is needed. The subsumed year-boundary case falls with it, because a 20:00 ET 31-December receipt also keeps its same-day date. | Four direct probes against the unmodified module; the guard is unchanged and correct. |
| IB1D-CR02 | P3 | Closed - accepted | `50bc867` | Record section 15.2 | My `72c5c86` disposition said the prior record raised two reviewer errors while section 14 raised three, contradicting my own section 15.3. | Direct comparison of sections 14.2, 15.2 and 15.3. | An internally inconsistent disposition corrupts the audit trail the ledger exists to preserve. | Superseded in section 16.1; the historical text is preserved unrewritten. | Lane-record guard passes. |
| IB1D-CR03 | P3 | Closed - accepted | `50bc867` | Record sections 15.5 and 15.7 | I described five synthetic fixture probes as "real-data timing reproductions" in the same review that recorded zero SEC access. | The probes construct synthetic tables and metadata sources in `tmp_path`; the same section states no external access. | `CLAUDE.md` section 6 forbids describing fixtures as real-data evidence. This is the exact failure mode that rule exists to prevent, and I committed it while auditing someone else's evidence language. | Superseded in section 16.1. This section calls every probe synthetic. | Terminology re-checked against the probe sources. |
| IB1D-CR04 | P3 | Closed - accepted | `50bc867` | Record section 15.6 | I wrote that the primary-document and metadata source URLs both bind `www.sec.gov`, the issuer CIK and the compact accession. Source URLs receive full Archive binding only conditionally. | Verified in `_validate_source_url_accession`: the compact accession must appear in the path always, but the host, issuer-CIK and seven-segment path checks apply only when `segments[1:4] == ["Archives", "edgar", "data"]`, so a `data.sec.gov` source URL is not CIK-bound. | Overstating provenance can be misread as authenticated capture evidence, which this boundary explicitly does not provide. | Superseded in section 16.1; the distinction is stated correctly here. | Static contract read of the three URL validators. |
| IB1D-CR05 | P3 | Closed - corrected here | `50bc867` | Record section 15.5 | My four-column finding table omitted commit, location, evidence, reason for fix, correction and verification. | `GENERAL_CODE_REVIEW_INSTRUCTIONS.md` section 2 mandates a ten-column minimum. | A short table is not a durable audit ledger and cannot support later counter-review. | This section and 17.5 use the mandated shape. | Table shape reviewed against the process document. |

Taken together with the previous round, eight defects of mine have now been
confirmed across two rounds. The pattern is worth recording plainly because it
is actionable rather than merely embarrassing: my errors are concentrated in
premises and evidence language, not in the mutation and probe work. IB1C-R15
asserted an EDGAR rule from memory without checking for an ownership-form
exception, and IB1B-R12 asserted an irreproducible count from a command whose
glob silently matched nothing. The verification discipline this lane applies to
implementation code has to apply to a reviewer's own premises before a finding
is recorded, not after it is challenged.

### 17.4 Counter-review conclusions independently verified

The IB1C-R15 rejection was re-tested rather than accepted on citation. Against
the unmodified module, an ownership filing accepted at 18:00 ET and at
21:59:59 ET with a same-day filing date is accepted, an ordinary 09:00 ET
filing is accepted, and my fabricated Friday-18:00-to-Monday pairing is
refused. The `[filing-date 05:00Z, next-date 05:00Z)` window comfortably
contains EDGAR's 06:00-22:00 ET operating span in both EST and EDT, so it is
correct for ownership forms and the guard rightly stands unchanged.

IB-1D's authority gates hold under adversarial mutation. Ten dangerous-
direction mutants were run; six were caught immediately: giving amendments the
original disposition, silently dropping an orphan amendment from every lineage,
ordering amendments by accession instead of acceptance instant, accepting an
ambiguous duplicate acceptance order, dropping the Form 4/A exclusion
requirement, and allowing XML retrieval to precede public acceptance.

Two further survivors were traced to genuine defence in depth rather than gaps,
and are recorded so no later reader mistakes them for coverage holes. The
authority-flag mutant survives because a `Form4AmendmentReconciliationIdentity`
itself refuses `True`, so no true-carrying identity can exist for the wrapper or
its properties to leak; that is three independent layers. The date-only mutant
survives because IB-1C's tier/evidence exclusivity guarantees a fallback record
has `accepted_at is None`, which the adjacent check already refuses.

I also checked the orphan-amendment path directly, because
`amendments.setdefault(target, [])` creates a key that the lineage loop never
iterates. It is guarded three ways: a version-count total, an accession-set
equality, and an edge-set equality, and the corresponding mutant is caught.

**No test weakening.** Across production and test source, the range deletes
exactly three lines, all docstring prose in `__init__.py` and the test module
header. The lane-record rewrite deletes a further nine documentation lines.
No test definition was removed anywhere, and my earlier IB1B-R10 regressions
remain present and unmodified.

### 17.5 New findings

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1D-R11 | P3 | Closed - fixed in this review | `73e87bc` | `research/insider_buying/form4_amendment_reconciliation.py`, `ReconciledForm4Amendments.__post_init__` | Two guards in the public result constructor had no test sensitivity: the semantic rebuild comparison of `as_filed_corpus` and `lineages`, and the source-inventory-to-filing hash binding. Each could be deleted with the whole suite green, so a later refactor could thin the boundary that IB1D-R04 was raised to protect. | Both mutants survived a ten-mutant sweep. The only direct-construction test passes a `SimpleNamespace` identity, which the exact-type check refuses before either guard is reached, so no test ever exercised a well-typed but inconsistent result. | IB1D-R04 states that a public result boundary must not let ordinary construction bypass its invariant. Two of the checks added for that reason were unverified, which is test sensitivity rather than a live defect - hence P3, not P2. | Added `test_reconciliation_wrapper_refuses_chronology_pointing_at_other_bytes`, which keeps roles, contiguity and every count valid while pointing one supplied version at different source bytes, and `test_reconciliation_wrapper_refuses_source_inventory_hash_drift`, which keeps the identity type, flags and counts valid while drifting one inventory hash. No production code changed. | Both tests pass on unmodified code and both previously surviving mutants are now caught, 2 of 2; module restored byte-identical to `HEAD` after the sweep. |
| IB1D-R10 | P3 | Open - agreed, deferred | `73e87bc` | `tests/test_insider_buying_sec_edgar_acceptance_snapshot.py` | Confirming Codex's own finding from an independent position: the IB-1D tests live in the IB-1C acceptance module rather than a module named for `form4_amendment_reconciliation`, so the file now carries 191 tests across two boundaries and the lane's file-per-module convention is broken. | The reconciliation module has no test file of its own; 81 amendment/chronology references sit in the acceptance module. | Discoverability and ownership, not safety. Extraction would duplicate or broadly refactor private fixture builders, which is disproportionate inside a review. | No change. Recorded as agreed deferred debt alongside IB1C-R16 and R-23. | Nine-file and module suites pass with the tests where they are. |
| IB1C-R16 | P3 | Open - deferred | prior rounds | Three immutable snapshot modules | Immutable-I/O helper triplication, unchanged this round. | IB-1D adds no publisher and therefore no fourth copy, as section 16.3 states; verified by its import list. | Maintainability, not correctness. | None. Codex's decision not to add a fourth copy is the right containment for now. | Static check of the new module's imports. |

### 17.6 Assessment of the IB-1D slice

The central decision in this milestone is a good one, and it was reached by
Codex's own audit rather than by review pressure: IB1D-R01 records that the
first draft let a caller omit a known Form 4/A and receive an original marked
effective with no end, which is unbounded canonical eligibility driven by
caller omission. Recasting the entire result as observation-only, removing every
effective/filter-returning API, and hash-binding both authority flags to false
is a stronger response than patching the omission case, and it is the right
instinct for a component that must never acquire selection authority.

The authority denial is layered three deep and I could not defeat it: the
identity refuses `True`, the result wrapper refuses a non-false identity and a
wrong identity type, and both public properties return literal `False`
regardless. Role assignment is equally structural - `Form4VersionInterval`
requires that original-observation state and `accession == original_accession`
agree, and `Form4AmendmentLineage` requires index 0 to be the original, every
later index to be quarantined, and the half-open intervals to be contiguous. An
amendment therefore cannot be relabelled as an original even by hand-building
the chronology.

Ordering is by exact acceptance instant rather than accession, and equal
acceptance times refuse as ambiguous instead of being tie-broken arbitrarily,
which is the correct conservative choice for an availability-ordered
chronology. `Form4ObservedState` deliberately omits the interval end so an
as-of query cannot expose a future amendment timestamp.

Stated rather than implied: the two open P2 items Codex records, IB1D-R08
cross-quarter lineage and IB1D-R09 unauthenticated amendment linkage, are real
authority blockers and are correctly labelled as such. This milestone proves
fixture-level software behaviour only. Nothing here establishes official SEC XML
compatibility, an authenticated original-to-amendment link, or a complete
amendment inventory, and the module's own gates say so in code rather than only
in prose.

### 17.7 Validation performed by this review

- Independent complete suite on the exact pushed tree `e2b434c`, before any
  correction: **5,685 passed, 9 skipped, 0 failed, 25 warnings in 915.99s
  (15m15s)**, reproducing the recorded pass and skip figures exactly. The
  warning count differs by one from the record, which is the same ordinary host
  variance seen in earlier rounds and identifies no Insider failure.
- Nine-file focused suite after this review's additions: **515 passed, 7
  skipped**, being the recorded 513 plus two new cases.
- IB-1C/IB-1D module after the additions: **191 passed, 2 skipped**, being the
  recorded 189 plus two.
- Complete suite on the exact final review tree: recorded in the appended
  ledger row.
- IB-1D dangerous-direction mutation sweep: ten mutants, **six caught, two
  survivors explained as defence in depth and confirmed by inspection, two
  genuine gaps closed by IB1D-R11**; after the additions both former survivors
  are caught, 2 of 2.
- Nine synthetic probes: four re-testing the IB1C-R15 timing rejection and five
  earlier residue and boundary cases. All inputs were synthetic fixtures in
  temporary directories; **no SEC or provider data was accessed**.
- `compileall` over `research/insider_buying` and the changed test module: exit
  0. `git diff --check` clean apart from the repository's line-ending notice.
- This review's diff is **72 insertions, 0 deletions**, entirely in
  `tests/test_insider_buying_sec_edgar_acceptance_snapshot.py`. No production
  code was changed.
- A mutation run was interrupted by a tooling timeout and left one mutated line
  in the working tree; it was detected by `git status`, restored from git, and
  confirmed byte-identical to `HEAD` before any further test run. Recorded
  because an undetected mutant would have invalidated every subsequent figure.

### 17.8 Residual gates and next authorized step

Section 16.6's gate list stands unchanged, and IB1C-R15 is removed from it as a
withdrawn false positive. IB-1D does not complete IB-1 or blueprint section
19.4 step 3. There is no official SEC XML or profile compatibility evidence, no
authenticated original-to-amendment link, no complete amendment inventory, no
cross-quarter lineage composition, no field-level correction or supersession
semantics, no canonical normalized row, and no downstream filtering authority.
IB1D-R08 and IB1D-R09 remain open authority blockers.

IB1D-R10, IB1C-R16 and R-23 remain deferred consolidation and test-ownership
debt. The shared execution-surface P1 set remains open and uncorrected on this
lane under the owner's strategy-scope rule.

Next authorized step: Codex counter-reviews these Claude commits, then may
define and validate authoritative amendment-link and multi-period evidence as
the next bounded milestone. No live SEC ingest, research look, outcome join,
QuantConnect job, broker action, or UI work is authorized.

## 18. Codex counter-review of the IB-1D Claude review (2026-08-30)

Counter-reviewer: Codex, on the existing
`codex/strategy-insider-buying` branch and dedicated Insider worktree. Exact
Claude range reviewed in chronological order: `e2b434c..3f2024b`
(`dceff74`, `3f2024b`). Local `HEAD`, the fetched remote head, and the tracked
branch were all `3f2024bf5726443d7d277a10412951523cf27754` before edits. No
branch switch, rebase, force operation, provider request, or external data
access occurred.

### 18.1 Claude commit dispositions

| Commit | Disposition | Counter-review basis |
|---|---|---|
| `dceff74` | **Accepted.** | Both tests reproduce their stated narrow gaps. The chronology-byte case is load-bearing for the semantic rebuild, and the inventory-entry hash case remains load-bearing after the stronger correction moved that equation into the identity boundary. The tests were adjusted to use the private verified-result factory where a white-box semantic mutation is intentional; the exported constructor is now factory-only. |
| `3f2024b` | **Accepted after correction.** | The Rule 13(a)(4) ownership-form exception and the withdrawal of IB1C-R15 are correct. Its overall IB-1D acceptance missed three generalized P2 data-integrity defects and contained two P3 record errors. All five are corrected or superseded below without erasing the historical review. |

### 18.2 Counter-review findings and retained ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1D-CR06 | P2 | Closed - fixed | `3f2024b` | `research/insider_buying/form4_xml.py`, singleton lookup | Schema-singleton XML fields used the first descendant and ignored conflicting duplicates. A filing carrying both code `P` and code `S` could enter `eligible_for_lot_aggregation` as `P`; the same fail-open direction applied to form type, issuer, owner flags, shares, price, direction, and ownership fields. | Synthetic duplicate `documentType` and `transactionCode` regressions both failed red because no exception was raised. Generalized call-site inspection confirmed repeated structures use explicit descendant loops, while `_first` is reserved for singleton reads. | First-value-wins parsing contaminates the canonical candidate set and violates the blueprint's fail-closed rule. | `_first` now refuses cardinality greater than one. Added conflicting form-type and transaction-code regressions. | Both red cases pass after correction. Neutralizing the cardinality guard makes both fail again; mutation restored. |
| IB1D-CR07 | P2 | Closed - fixed | `3f2024b` | `research/insider_buying/form4_xml.py`, transaction collection | A transaction element nested under a wrapper, orphaned outside a table, or placed under the wrong table was silently omitted while the filing parsed successfully, including as a zero-transaction filing. | Three synthetic structural mutations each parsed without refusal before correction. A full descendant inventory contained the row while the direct-child collection did not. | Silent row loss breaks as-filed retention, amendment reconciliation, and later QC traceability. | The parser now inventories every derivative and non-derivative transaction element and requires exact identity/type equality with the direct children collected from their proper tables. | All three red shapes pass after correction. Neutralizing the inventory equality makes all three fail again; mutation restored. |
| IB1D-CR08 | P2 | Closed - fixed | `3f2024b` | `research/insider_buying/form4_amendment_reconciliation.py`, source identity, reconciliation identity, and result constructor | Exact-type identities accepted invalid contract/hash/count/source provenance, and an ordinary caller could reassemble a public result after deleting parsed transactions. A malformed inventory object was accepted and later crashed serialization. Claude's two tests covered only chronology bytes and one per-source XML hash. | Direct probes accepted negative XML size, invalid URLs/times/commits, invalid aggregate hashes and IDs, and a corpus with its only transaction removed. The public result constructor accepted valid components without proof they came from the verified parser path. | This is durable-state/provenance corruption at the boundary intended to support future QC evidence. Literal false authority flags prevent immediate signal escape but do not make corrupted audit state acceptable. | Source identities and reconciliation identities now validate exact types, syntax, ordering, uniqueness, aggregate hashes, counts, acceptance-snapshot linkage, and the reconciliation-ID equation. The identity binds transaction count and a deterministic hash of the full parsed corpus. Result construction requires a private factory token, and reconstructible source fields are rebound to filing envelopes. | Nine counter-review red directions became green; the focused correction slice is 15 passed. Jointly neutralizing transaction-count/corpus-hash binding exposes parsed-row loss, and neutralizing the factory token exposes direct reassembly; both mutations were killed and restored. |
| IB1D-CR09 | P3 | Closed - fixed | `3f2024b` | Record status header | The header simultaneously said IB-1D had completed Claude review and still awaited Claude review. | Direct comparison of lines 3-10 at the reviewed head. | A contradictory lane handoff can start the wrong workflow step. | Header now records completed Claude review and completed Codex counter-review. | Lane-record and active-document checks plus visual read. |
| IB1D-CR10 | P3 | Closed - fixed | `3f2024b` | Section 17.4 | The review said the range deleted exactly three lines, but `git diff --numstat 50bc867..e2b434c` shows twelve deletions: three production/test docstring lines and nine lane-record lines. | Commit-range numstat and file-level diff. | Evidence language must distinguish source-code/test weakening from documentation replacement. | Section 17.4 now scopes the three-line statement to production/test source and states the nine record deletions separately. | Rechecked the exact range and corrected prose. |
| IB1D-CR11 | P3 | Open - deferred | Prior IB-1A/B/C rounds | IB-1A/B/C identity/result dataclasses | Several earlier snapshot dataclasses rely on strict public loader validation rather than making ordinary direct construction self-validating. No loader bypass or corrupted persisted snapshot was reproduced in this counter-review. | Generalized constructor search across the three upstream modules. Their loaders rebuild hashes, row counts, schemas, ordinals, and lineage before returning loaded state. | A broad constructor/API refactor is outside the current IB-1D correction and risks duplicating deferred immutable-I/O work. | No change. Retained for an owner-scheduled lane consolidation or when a public direct-construction path is proposed. | Existing IB-1A/B/C loader and mutation suites remain in the later focused and complete validation sets. |

### 18.3 Verification and conclusion

The original Claude additions passed independently: **2 passed**. The
counter-review red phase produced **9 failed** tests across the three P2
directions. After correction, the targeted set passed **15**, and the complete
affected Form 4 plus IB-1C/IB-1D modules passed **291 with 2
platform-conditional skips in 162.19 seconds**. Four targeted reverse
mutations were killed and restored: singleton cardinality, transaction-node
inventory, paired transaction-count/parsed-corpus binding, and factory-only
result construction. The official ownership-form timing premise remains
accepted; no production timing rule changed.

Counter-review disposition: **accepted after correction**. There is no open P0,
P1, or P2 finding in this counter-review scope. IB1D-CR11, IB1D-R10,
IB1C-R16, and R-23 remain P3 debt. IB1D-R08 and IB1D-R09 remain future
authority blockers: this correction does not establish complete cross-quarter
coverage or authenticate an amendment target.

Only `research/insider_buying`, Insider tests, and this record changed. The
project-wide coordination files remain frozen. No filing, package, API,
provider, credential, licensed row, market outcome, QuantConnect job, broker,
operator database, scheduler, UI, or order was accessed. **0 research looks.**

Next bounded step: commit this counter-review checkpoint, then define an
offline, profile-bound multi-period amendment-evidence contract. It must retain
all supplied as-filed versions, refuse period gaps/overlaps and malformed,
unbound, or internally conflicting supplied links, and keep complete-amendment-
coverage and canonical-filter authority false. No canonical row replacement or
external acquisition is authorized.

## 19. Codex IB-1E offline multi-period supplied-link evidence (2026-08-30)

Implementer and self-reviewer: Codex, on the existing
`codex/strategy-insider-buying` branch and dedicated Insider worktree. The
counter-review checkpoint is `ad86df0`; the bounded IB-1E implementation
snapshot is `e89293b5414881b7448b31a08fe8433df14f2489`. No branch or
worktree was created or switched, and no sibling strategy, shared execution
surface, or project-wide coordination file changed.

This milestone is deliberately named **offline multi-period supplied-link
evidence**, not authoritative amendment reconciliation. It makes no SEC or
provider request and introduces no downloader, credential, licensed row,
outcome, QuantConnect, broker, operator-database, scheduler, UI, order, or
publication path. All inputs in validation are synthetic. **0 research
looks.**

### 19.1 Bounded implementation

`form4_multi_period_amendment_evidence.py` composes two through sixteen
contiguous IB-1C acceptance periods, loaded at call time through the verified
IB-1C loader. Caller period and XML order do not affect the result. Duplicate
quarters, gaps including a broken Q4-to-Q1 transition, mixed metadata profiles,
global duplicate accessions, aggregate resource amplification, date-only
availability, missing targets, amendment targets, issuer conflicts, and
non-increasing acceptance chronology all refuse before a result is returned.

No fourth evidence source was added. The caller-defined, explicitly
non-official IB-1E profile maps `amends_accession` and
`primary_document_sha256` fields already present inside the exact metadata JSON
bytes retained and hash-bound by IB-1C. IB-1E reparses those bytes with the same
strict duplicate-free UTF-8, exact-field, flat-object, and field-size helper as
IB-1C. The profile-derived link must equal the XML-source assertion and the
profile-derived document hash must equal the exact supplied XML bytes. The top
identity binds every period receipt, the evidence profile, supplied-link
inventory, XML-source inventory, parsed corpus, counts, and parser commit.
Both the identity and result require private verified factory paths.

Every **supplied** as-filed version is retained. Same-quarter and cross-quarter
Form 4/A versions join only to a supplied original Form 4 with the same issuer
and a strictly earlier exact acceptance instant. Original purchase rows keep
their named provisional include outcome; amended rows keep the single named
`EXCLUDE_AMENDED_FILING` outcome. Amendments remain quarantined in the
observation-only chronology, and as-of views expose no future supplied
boundary.

Three authority statements are literal, identity-bound false values and
literal-false result properties:

- `official_amendment_link_verified = False`
- `complete_amendment_coverage_verified = False`
- `canonical_filter_authorized = False`

A verified period may contain another Form 4/A that the caller did not supply;
the result retains no row for it and still cannot claim complete coverage. A
caller and non-official profile may also agree coherently on one of two
same-issuer originals; structural consistency can accept that supplied edge,
but it still cannot make the edge official. These negative cases are pinned in
tests so later documentation cannot mistake fixture consistency for SEC
authentication.

### 19.2 Implementation review and retained ledger

Two independent read-only subreviews examined contract design, test design,
fail-open directions, identity forgery, resource caps, and scope language. The
findings below include their material issues and the retained prior blockers.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1E-R01 | P2 | Closed - fixed | IB-1E implementation | Multi-period load loop | The first draft loaded every period and only then applied aggregate record and metadata-byte caps, allowing up to sixteen individually valid bundles to amplify memory and I/O before refusal. | Read-only adversarial review traced cap evaluation after the complete load list and period-identity hashing. | A resource cap that runs after amplification is not an effective boundary. | Each loaded period is now type/hash/count validated and accumulated before it is retained or the next loader call occurs; over-cap input stops the sequence immediately. | A low-cap three-period regression proves only the first two loaders run, XML parsing is never reached, and the third period is not loaded. |
| IB1E-R02 | P2 | Closed - fixed | IB-1E implementation | `Form4MultiPeriodEvidenceIdentity` | The first identity draft hash-bound link and XML inventories separately but did not semantically cross-bind URL, amendment target, and document hash. A coordinated direct identity with recomputed hashes could disagree across inventories. | A reviewer constructed the coordinated-tamper direction rather than changing only one stale hash. | Separate correct hashes do not prove that two inventories describe the same bytes and edge. | Identity construction now compares each supplied-link item with its XML-source identity, and the top identity itself is factory-only. | The regression recomputes the tampered evidence hash and evidence ID yet is refused on the semantic XML-source binding; a no-change `replace(identity)` is refused by the factory token. |
| IB1E-R03 | P3 | Closed - fixed | IB-1E implementation | Module and record scope prose | “Every as-filed version” overstated a supplied-sample boundary because a verified period can contain an unsupplied amendment. | An omitted Form 4/A remains visible in the period receipt but intentionally has no supplied XML row or lineage version. | Evidence language must not imply complete coverage that the code permanently denies. | Prose now says every **supplied** as-filed version; the omitted-amendment negative case is explicit here and in tests. | The result excludes the omitted accession and both complete-coverage and canonical-filter properties remain literal false. |
| IB1D-R08 | P2 | Closed for structural composition only | IB-1E implementation | Multi-period period and lineage inventories | IB-1D could compose only one acceptance quarter, so a Q4 original and Q1 amendment could not share one observation chronology. | The new synthetic Q4-to-Q1 case produces one ordered lineage under a contiguous two-period identity. | Multi-period structure is required before any later real amendment evidence can be assessed. | Added deterministic contiguous-period composition with cross-year quarter arithmetic and global accession uniqueness. | Forward and reversed caller order produce the same result; gap and overlap sentinels refuse before XML parsing. This does not prove complete coverage. |
| IB1D-R09 | P2 | Open - authority blocker | Prior round and IB-1E | Supplied amendment target | IB-1E validates a link field inside bytes already verified by IB-1C, but the profile and bytes are still caller-supplied and non-official. Internal agreement cannot prove that SEC named the asserted original. | A coherent alternate same-issuer target is structurally accepted while `official_amendment_link_verified` remains false. No official SEC profile, authenticated capture, or real filing was accessed. | Treating internal consistency as authenticated provenance could let the wrong original drive canonical filtering. | No authority change. The new contract explicitly names supplied-link evidence and preserves the false authority gates. | Negative-scope tests pin the alternate-target and omitted-amendment cases. Official link, completeness, and filtering authority remain false. |
| IB1E-R04 | P3 | Open - deferred | IB-1E implementation | IB-1E integration tests | The focused IB-1E tests use actual Form 4 XML fixtures but replace the call-time IB-1C loader with logically consistent verified-boundary objects; there is not yet one persisted two-period IB-1A/B/C-to-IB-1E fixture. | Existing IB-1C/IB-1D tests exercise real local publication and loader rebuilds, while the new fifteen-test module isolates multi-period logic. | A persisted two-period integration would improve wiring confidence but requires generalized multi-quarter raw/parsed fixture builders outside this bounded contract slice. | No broad fixture refactor in this milestone. | Retained for the real-package/profile compatibility phase or a dedicated test-infrastructure milestone. |
| IB1E-R05 | P3 | Open - deferred | IB-1E implementation | Private IB-1D chronology helpers and test ownership | IB-1E reuses package-private IB-1D chronology/hash/source helpers, while some source-to-filing validation remains similar across the two boundaries. | Static dependency review; no fourth publisher or immutable-I/O copy was added. | Consolidation now would broaden the diff and couple two separately reviewed public contracts. | No change; retain alongside IB1D-R10, IB1C-R16, IB1B-R11, and R-23 consolidation debt. | Import-surface regression confirms no network, outcome, execution, strategy, risk, broker, scheduler, or UI dependency entered the module. |

No review finding outside the Insider Buying QC/autopilot development purpose
required a code change. The project-wide shared execution findings remain
document-only on this lane under the owner's strategy-scope rule.

### 19.3 Validation

- Red phase: the new test module failed collection because the IB-1E contract
  did not exist.
- Focused IB-1E suite: **15 passed**. It covers cross-year and same-quarter
  lineages, input-order determinism, genuine gap/overlap refusal, global
  duplicate accessions, caller/profile link disagreement, missing target,
  issuer and chronology conflicts, exact XML-hash binding, profile drift,
  date-only refusal, pre-load and sequential aggregate caps, named include and
  amendment-exclude outcomes, omitted-amendment and coherent-alternate-target
  negative scope, factory-only identity/result construction, coordinated
  identity tampering, and the forbidden-import boundary.
- Existing IB-1C/IB-1D module after the shared strict-JSON helper extraction:
  **195 passed, 2 skipped in 166.20 seconds**.
- Independent latest-tree review slice for IB-1C/IB-1D plus IB-1E:
  **210 passed, 2 skipped**; the reviewer reported no remaining P0-P3 finding
  after the sequential-cap correction.
- Ten-file Insider, active-record, import-boundary, hygiene, and project-
  separation suite: **539 passed, 7 skipped in 275.10 seconds**.
- A direct temporary mutation of the live period-gap guard was rejected by the
  execution safety boundary before any file changed. The gap test was then
  strengthened with a genuinely valid Q2 identity, a profile covering Q2, and
  an XML-parser sentinel, so weakening the adjacency guard necessarily reaches
  the forbidden parser path.
- Complete suite on exact clean implementation commit `e89293b`: **5,710
  passed, 10 skipped, 0 failed, 25 ordinary dependency/runtime warnings in
  2,290.57 seconds (38m10s)**.
- Whole-repository compileall over `assistant`, `backtest`, `data`,
  `execution`, `ml`, `research`, `risk`, `scripts`, `signals`, `strategies`,
  `tests`, and the root Python entry points: exit 0.
- Final active-document, lane-record, and IB-1E checks on the docs-only
  validation update: **79 passed in 19.29 seconds**.
- The worktree remained clean throughout exact-tree validation. Final
  record-sensitive, diff, branch, and remote checks follow on the docs-only
  validation commit before the single push.

### 19.4 Residual gates and handoff

IB-1E closes only the structural cross-period portion of IB1D-R08. IB1D-R09
remains open. This milestone does not establish an official SEC metadata or
XML profile, authenticated transport/capture provenance, complete amendment
inventory, official original-to-amendment link, real-package compatibility,
field-level correction/supersession semantics, canonical normalized row,
joint-owner treatment, point-in-time security mapping, post-aggregation
$50,000 rule, signal, outcome, ETF portfolio, QuantConnect algorithm, broker
integration, or paper/live authority.

Next step: commit this docs-only validation evidence, rerun record-sensitive
checks, confirm the remote remains the reviewed base, then push the separate
counter-review, implementation, and validation-record commits together for
Claude's independent review on this same lane branch. No next implementation
milestone begins until that review is counter-reviewed under the serialized
lane workflow.

## 20. Project-wide main-sync conflict review (2026-08-31, local-only artifact)

Codex reviewed pushed range `e2b434c205a5e5d62f2f17e0de939ca1ab1ad6bf`
through `6e38fa1cded33cb0a0f8867ff490680f90cbe0ae` and merged exact main
`1a5264e6b1de3caf5477477d1312a762b2d42419` into that pushed lane head in an
isolated detached clone. The resulting merge commit is
`dd2cae8202a89e7ac2fb23a5b647d9a716b7f8e7`. It is a local-only artifact;
no live lane ref, dirty worktree, or remote was updated. This section
supersedes section 19.4's now-completed instruction to push `6e38fa1` but does
not claim that the later local development is published or reviewed.

All 23 textual conflicts were resolved without changing current shared
production behavior. Twenty-two stale shared production/test blobs were
restored byte-for-byte from main. `tests/test_ml_evidence_operations.py`
retains all main content plus the reviewed Store-alias interpreter skip and
matches the pushed Insider head. Relative to main, the merge candidate changes
only 19 Insider-owned record/source/fixture/test paths plus that shared test;
it changes no other strategy implementation.

| Commit | Disposition | Reason |
|---|---|---|
| `dceff74` | accepted | Adds load-bearing IB-1D result-constructor regressions. |
| `3f2024b` | accepted after correction | Its review omissions are corrected by `ad86df0`. |
| `ad86df0` | accepted | Restores stronger identity, corpus, factory, and XML structure checks. |
| `e89293b` | accepted | IB-1E remains explicitly offline, non-authoritative, and gate-preserving. |
| `6e38fa1` | accepted | Records validation of the exact pushed IB-1E tree. |

`INS-MRG-001` remains open at P3. The exported `Form4ObservedState` at the
pushed head accepts an amendment accession with `ORIGINAL` disposition, which
can create an internally inconsistent observation-only value. Local-only
commit `43d6d6ae208875e8b64106a3324f1819fdc3a67b` contains a guard and test, but
it is a sibling of the remote correction chain and must not be cherry-picked
wholesale. No new P0-P2 defect was found in the pushed delta; the previously
recorded IB1D-R09 future-authority debt remains open and correctly keeps
official-link, completeness, and filter authority false.

Validation used Python 3.12.13 and pytest 9.1.1. Focused suites passed 927
tests with two skips and one warning. The exact resolved tree passed 6,208
tests with nine skips and 26 dependency warnings in 1,211.54 seconds.
Compileall passed, the unmerged-path and conflict-marker scans were empty,
and candidate-relative/non-PDF diff checks were clean. Raw staged diff
checking reports whitespace inside main's already-committed target-price PDF;
that is not an Insider delta.

The live Insider worktree remains intentionally untouched and is not ready to
accept this artifact: its local branch is at `43d6d6a`, one commit ahead and
three commits behind the pushed lane, and it also contains substantial
uncommitted development plus two untracked source/test files. Preserve that
work in an owner-approved snapshot, reconcile the sibling histories and the
unique role-consistency guard, then regenerate or replay this main sync. Do
not reset, overwrite, fast-forward, or push the live lane from this artifact.

No provider, credential, licensed row, market outcome, permanent research
look, QuantConnect job, broker, operator database, scheduler, deployment, or
trading authority was accessed or granted.

## 21. Local-history reconciliation after main sync (2026-08-31, local-only artifact)

At the owner's direction, Codex reconciled the lane's exact local-only commit
`43d6d6ae208875e8b64106a3324f1819fdc3a67b` into the already reviewed local
main-sync artifact `1ffb6c556517610bb84c0b3b506748a65aab990e`. The resulting true merge
commit is `d6d26e09b806e24de865d237f59674ad952c4df6`, with those two commits as its
first and second parents respectively. This preserves the original local
commit as reachable ancestry; it was not cherry-picked, rebased, squashed, or
rewritten. The live lane worktree was clean at `43d6d6a` when checked and was
not modified, and no branch ref or remote was updated.

The merge produced two textual conflicts, both in lane-owned IB-1D files:
`research/insider_buying/form4_amendment_reconciliation.py` and
`tests/test_insider_buying_sec_edgar_acceptance_snapshot.py`. The resolution
keeps the later `ad86df0` factory-only constructor, parsed-corpus binding,
expanded identity, source-inventory validation, and its stronger regressions.
It adds only the local commit's non-superseded role-consistency invariant and
regression: an amendment accession cannot claim the original-filing
observation disposition, and the original accession cannot claim an amendment
disposition. No IB-1E source, test, fixture, export, or authority gate changed.
Relative to `1ffb6c5`, the resulting tree adds 23 lines in those two files.

| Commit | Disposition | Reason |
|---|---|---|
| `43d6d6a` | accepted after reconciliation | Its unique observed-state role invariant and regression are correct and retained. Its overlapping public-result and identity hardening was superseded by the later, stronger `ad86df0` factory-only and parsed-corpus design, so those older tree forms were not reintroduced. |
| `d6d26e0` | accepted as a local conflict-resolution candidate | It preserves both histories as parents, retains the later IB-1D/IB-1E tree, closes `INS-MRG-001`, and has no change outside the two lane-owned files. It remains local-only and still requires the ordinary exact-pushed-snapshot review before later lane development. |

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| `INS-MRG-001` | P3 | Closed - fixed | `d6d26e0` | `Form4ObservedState.__post_init__` | A directly constructed amendment observation could claim the original-filing role, producing an internally inconsistent exported value. | The pre-reconciliation `1ffb6c5` constructor checked syntax and enum type but did not bind role to accession identity; `43d6d6a` contained the missing invariant. | Exported observation values should not encode mutually contradictory filing identity and chronology role even though this boundary has no trading authority. | Retained the equivalence check from `43d6d6a` on top of the later remote implementation and retained its dangerous-direction regression. | Targeted regression **1 passed, 197 deselected**; affected IB-1D/IB-1E tests **211 passed, 2 skipped**; complete suite **6,209 passed, 9 skipped**. |

Validation used Python 3.12.13 and pytest 9.1.1. The targeted role regression
passed with 197 deselections in 0.74 seconds. The complete IB-1D acceptance-
snapshot and IB-1E multi-period suite passed **211 tests with 2 skips in
122.60 seconds**. The exact reconciliation code commit `d6d26e0` passed the
complete repository suite with **6,209 passed, 9 skipped, 0 failed, and 26
dependency/runtime warnings in 1,130.16 seconds (18m50s)**. Whole-repository
compileall including `research` exited 0, `git diff --check` was clean, and
the candidate remained detached from all live refs. The final active-document
and Insider lane-record checks passed **68 tests**; this documentation-only
commit changes no product behavior.

No new P0-P2 finding was introduced by this reconciliation. `IB1D-R09`
remains the open future-authority blocker: the supplied, non-official
amendment link still cannot authorize canonical filtering. No SEC/EDGAR or
other provider request, credential, licensed row, market outcome, permanent
research look, QuantConnect job, broker, operator database, scheduler,
deployment, or trading authority was accessed or granted. The next authorized
step is to transfer this exact local-only history to the clean lane only after
re-verifying its head, then obtain independent review of the exact pushed
snapshot before any further Insider milestone.

## 22. Local application of the reconciled history (2026-08-31)

Codex completed that transfer under the owner's direction. Immediately before
application, a fresh fetch confirmed exact `origin/main` at
`1a5264e6b1de3caf5477477d1312a762b2d42419` and the pushed Insider lane at
`6e38fa1cded33cb0a0f8867ff490680f90cbe0ae`; the live worktree was clean at
exact local commit `43d6d6ae208875e8b64106a3324f1819fdc3a67b`.
Codex verified the complete-history reconciliation bundle and fast-forwarded
the one long-lived local lane branch to record commit
`466af8a7597f2549a54fcc3e2b87e6f31c0947ab`.

The tested reconciliation merge `d6d26e09b806e24de865d237f59674ad952c4df6`
is now reachable from this local branch and retains `43d6d6a` as its exact
second parent. Neither the local hardening commit nor the pushed IB-1D/IB-1E
history was dropped, rebased, squashed, duplicated, or rewritten. The
application itself introduced no new tree content beyond the already reviewed
candidate; this section is the only subsequent documentation change.

No remote ref was moved and nothing was pushed. Independent review of the
eventual exact pushed snapshot remains required before another Insider
milestone. `IB1D-R09` and every provider, outcome, QuantConnect, broker,
deployment, order, and trading authority gate remain unchanged.

## 23. Owner push authorization (2026-08-31)

After Codex reported the exact clean local head
`607b5a3e39e11e637fa10e5522a2d0f01adc81d0`, confirmed that original local
commit `43d6d6a` and the pushed IB-1D/IB-1E history remain reachable parents,
and stated that nothing had been pushed, the owner explicitly instructed
`push`. This authorizes one push of the completed main-sync and local-history
reconciliation plus this required authorization record to the existing
long-lived Insider lane. It does not authorize another implementation
milestone or any provider, outcome, QuantConnect, deployment, broker, order,
or trading action.

The exact reconciled code tree passed **6,209 tests with 9 skips and 0
failures**; affected IB-1D/IB-1E validation passed **211 tests with 2 skips**;
compileall, diff, marker, and repository-integrity checks passed. Before the
push, Codex must re-fetch, require exact `origin/main@1a5264e`, pushed lane head
`6e38fa1`, and original local commit `43d6d6a` to remain ancestors of the clean
local head, commit this record, and push only this one lane branch. Independent
review of the exact pushed snapshot follows; `IB1D-R09` remains blocked.
## 24. Claude review - IB-1D counter-review and IB-1E multi-period evidence (2026-08-31)

Reviewer: Claude, Insider Buying lane review session, dedicated worktree pinned
to this branch. The branch had advanced on other machines and all four lane
branches were merged to `main` before this review began.

Sync verification: `git fetch --all --prune`; local `HEAD`,
`origin/codex/strategy-insider-buying` and `origin/main` are all
`cf136e259cf628aabdc4220865fccdb5c7204306`; the worktree was clean; and my last
reviewed head `3f2024b` is an ancestor, so no published history was rewritten.
The full range `3f2024b..cf136e2` contains 194 commits, but only nine touch
Insider lane files; the remainder are the other three lanes and shared main
history arriving through the merges. This section dispositions the Insider
range and treats the rest as merged context.

Owner scope rule for this round: correction scope is limited to trading
strategies on the QuantConnect backtest run. Issues in the Trading App or in
project structure that are not strategy-related are documented in 24.7 and not
fixed.

### 24.1 Isolation verification

The nine Insider-touching commits change only lane-owned surfaces: this record,
`research/insider_buying/{__init__,form4_xml,form4_amendment_reconciliation,form4_multi_period_amendment_evidence,sec_edgar_acceptance_snapshot}.py`,
and the Insider test modules. Nothing under `assistant/`, `execution/`,
`risk/`, `scripts/`, `signals/`, `strategies/`, `data/`, or `backtest/`
references `research.insider_buying`, and the IB-1E import surface carries no
network, outcome, execution, strategy, risk, broker, scheduler, or UI
dependency. No SEC/EDGAR, provider, credential, licensed row, outcome,
QuantConnect, broker, operator-database, scheduler, or UI access occurred.
**0 research looks.**

The parallel-phase frozen-file regime is now moot for this lane: the four lanes
are merged and the lane branch equals `main`. That is recorded as an
observation in 24.7, not acted on, because ending the frozen-file phase is an
owner coordination decision rather than a lane one.

### 24.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `43d6d6ae` Harden IB-1D public result construction | **Accepted.** | Factory-token construction and the strengthened identity equations close the direct-reassembly direction. My two prior tests were correctly relocated onto the private verified-result factory where a white-box semantic mutation is the point of the test; that is a repair, not a weakening, and both remain load-bearing. |
| `ad86df01` Complete IB-1D counter-review corrections | **Accepted.** | The three P2 corrections are real and were independently reproduced (24.4). The `_first` cardinality guard is correctly scoped and does not refuse legitimate multi-transaction filings. |
| `e89293b5` Add IB-1E multi-period amendment evidence | **Accepted after correction.** | The contract is well-built and its authority denial holds under mutation. Corrected here: the supplied-XML-to-acceptance issuer binding had no test sensitivity (IB1E-R06). |
| `6e38fa1c` Record IB-1E exact-tree validation | **Accepted as validation of the exact implementation tree.** | Its focused IB-1E and module figures reproduce; one composite figure is unreproducible as recorded and is noted as IB1E-R07. |
| `dd2cae82` Merge main into Insider Buying without weakening shared safety | **Accepted.** | Merge commit reviewed for conflict resolution: it brings shared main history and the other lanes' tests; no Insider lane file was altered by the merge itself, and no shared safety guard was weakened in the resulting tree. |
| `d6d26e09` Reconcile Insider local hardening with reviewed main sync | **Accepted.** | Reapplies the IB-1D hardening lost against the merged base and adds one regression pinning that an amendment cannot take an original role. |
| `1ffb6c55`, `466af8a7`, `607b5a3e`, `8321c807` | **Accepted as local-only coordination records.** | Sections 20-23 document the conflict review, history reconciliation, local application, and owner push authorization. They change no code. |

### 24.3 Counter-review findings against Claude

Section 18 raised three P2 defects and two P3 record errors against my IB-1D
review. All five are confirmed and accepted. The two P2 parser defects are the
most serious misses I have made in this lane, because they sit directly in the
canonical eligibility path.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1D-CR06 | P2 | Closed - my miss, fix verified | `3f2024b` | `research/insider_buying/form4_xml.py` `_first` | Schema-singleton reads took the first descendant and ignored conflicting duplicates, so a filing carrying both `P` and `S` could enter `eligible_for_lot_aggregation` as a purchase. This is contamination of the canonical candidate set, which is the strategy's whole input. | Verified by direct probe on the unmodified tree: duplicate conflicting `transactionCode` and duplicate `documentType` are both refused with "XML schema field appears more than once". | First-value-wins parsing is a fail-open direction the blueprint forbids. | Codex's fix; no further change needed. | I additionally checked the fix is not over-broad: a routine two-transaction Form 4 still parses to two `P` rows, so the cardinality guard is correctly scoped per row and per owner block rather than across the filing. |
| IB1D-CR07 | P2 | Closed - my miss, fix verified | `3f2024b` | `form4_xml.py` transaction collection | A transaction nested under a wrapper, orphaned outside a table, or filed under the wrong table was silently omitted while the filing still parsed, including as a zero-transaction filing. Silent row loss breaks as-filed retention and every downstream lineage claim. | Verified by direct probe: a wrapper-nested transaction and an orphaned transaction are both refused with "transaction XML structure is incomplete or ambiguous", while the unmodified fixture still parses. | The canonical contract says excluded rows are never silently dropped; this dropped rows without any classification at all. | Codex's fix; no further change needed. | Probed on the unmodified tree; baseline unaffected. |
| IB1D-CR08 | P2 | Closed - my miss, fix accepted | `3f2024b` | `form4_amendment_reconciliation.py` identities and result constructor | Exact-type identities accepted invalid provenance and an ordinary caller could reassemble a public result after deleting parsed transactions. My IB1D-R11 tests covered only chronology bytes and one per-source XML hash, so I found the shape of the gap and then under-generalized it. | Codex's nine red directions and the factory-token requirement. | Durable audit-state corruption at the boundary intended to carry future QC evidence. | Codex's fix; my two tests were correctly rebased onto the private verified factory. | I confirmed both of my tests survive and still fail when their guards are neutralized. |
| IB1D-CR09 | P3 | Closed - accepted | `3f2024b` | Record status header | The header said IB-1D had both completed and not completed Claude review. | Direct read of the reviewed head. | A contradictory handoff can start the wrong workflow step. | Codex corrected the header. | Lane-record and active-document checks pass. |
| IB1D-CR10 | P3 | Closed - accepted | `3f2024b` | Section 17.4 | I wrote that the range deleted exactly three lines; the range deletes twelve, being three production/test docstring lines and nine lane-record lines. | `git diff --numstat 50bc867..e2b434c`. | Evidence language must separate source/test weakening from documentation replacement; my sentence conflated them. | Codex scoped the statement. | Range re-checked. |

The two parser defects deserve a plain statement rather than a bare
acceptance. `form4_xml.py` was implemented in IB-0 and reviewed in an earlier
round, and I treated it as settled while reviewing IB-1D. That was wrong: IB-1D
routes every supplied filing through that parser and therefore gives the older
code new authority. **Inherited code that a new milestone newly depends on is
in scope for that milestone's review.** This is the third distinct root cause
behind my confirmed misses in this lane - after unverified domain premises and
imprecise evidence language - and it is the one most likely to recur, because
each milestone here composes on the last.

### 24.4 Counter-review fixes independently verified

Every claim in 24.3 was re-tested against the unmodified tree rather than read
from the record:

| Probe | Result |
|---|---|
| duplicate conflicting `transactionCode` (`P` and `S`) | refused |
| duplicate conflicting `documentType` (`4` and `5`) | refused |
| transaction nested under an extra wrapper | refused |
| transaction orphaned outside any table | refused |
| unmodified fixture | parses, one `P` transaction |
| **routine two-transaction Form 4** | **parses, two `P` transactions** |

The last row is the one that matters for a fail-closed correction: a
cardinality guard scoped too broadly would have refused ordinary real filings,
turning a safety fix into an availability defect. It does not.

### 24.5 New findings

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1E-R06 | P3 | Closed - fixed in this review | `e89293b5` | `form4_multi_period_amendment_evidence.py`, supplied-source loop | The binding between the parsed XML's declared issuer and the CIK anchored by the IB-1C-verified primary-document URL had no test sensitivity: neutralising it left the whole IB-1E module green. Without it a caller could file one issuer's XML under another issuer's verified accession, corrupting the audit lineage later QC evidence rests on. | The guard survived a seven-mutant sweep. `test_cross_period_lineage_refuses_missing_target_cross_issuer_and_reversal` exercises the corpus-level original-versus-amendment issuer comparison in `contracts.py`, not this one, so the two are distinct guards and only the former was covered. | IB-1E's own record names issuer conflict as a covered refusal direction; that coverage claim rested on a different check. Severity is P3 rather than P2 because all three authority flags remain literal false, so the exposure is audit-state integrity rather than selection authority. | Added `test_supplied_xml_issuer_must_agree_with_verified_acceptance_evidence`. Both supplied filings declare the same foreign issuer so the corpus-level comparison stays satisfied and only the XML-to-acceptance binding can refuse. No production code changed. | Passes on unmodified code; neutralising the guard makes it fail; module restored byte-identical to `HEAD`. |
| IB1E-R07 | P3 | Open - record precision | `6e38fa1c` | Section 19.3 | The recorded "ten-file ... 539 passed, 7 skipped" does not name its composition and I could not reproduce it. My ten named files collect 549 at the committed head (542 passed, 7 skipped) and 550 with this review's addition; only one test definition was added between `e89293b` and the head, so the recorded figure is roughly two cases short of any composition I can construct. | Direct `--collect-only` at the committed head and with my addition, plus a diff of added test definitions across the range. | Section 14.5 already committed to naming files explicitly after the earlier count dispute; this row reverts to an unnamed composite. Recorded as precision, **not** as a disputed result - the complete-suite and focused IB-1E figures both reproduce. | No change. Future rows should name the exact files or command. | My own figures are stated with their exact file list in 24.8. |

Four further mutants survived the IB-1E sweep and are recorded as **defence in
depth, not gaps**, because I traced each to a masking guard rather than
assuming: duplicate supplied accessions are refused by `contracts.py`
`build_filing_corpus`; the result wrapper's authority-flag check is masked
because `Form4MultiPeriodEvidenceIdentity` itself refuses a true flag, which
the identity-level mutant confirms by being caught; and the corpus/chronology
and period-record-inventory equations are now reachable only through the
factory path that always constructs them consistently, since IB1D-CR08 made
direct construction impossible. That last point is worth noting as a design
consequence: the factory token converted two previously caller-reachable
guards into internal assertions.

### 24.6 Assessment of the IB-1E slice

IB-1E does the hard part of cross-quarter composition without granting itself
any new authority. It adds a third literal-false gate,
`official_amendment_link_verified`, precisely where a naive implementation
would have claimed success: the profile-derived link and document hash are
checked against the caller's assertion and the exact supplied bytes, and the
result still refuses to call that an official SEC link. The record states the
coherent-alternate-same-issuer-target case explicitly and pins it in a test, so
a later reader cannot mistake internal consistency for authentication. That is
the correct treatment of IB1D-R09 and it is why that finding is properly still
open.

Period composition is deterministic and order-independent, contiguity is
enforced on a period index that handles the Q4-to-Q1 transition, and the
gap/overlap and cap refusals happen before any XML parsing - the caps
sequentially, so sixteen individually valid bundles cannot amplify before
refusal. Amendments join only a supplied original with the same issuer and a
strictly earlier acceptance instant, and remain quarantined.

Stated rather than implied: this is fixture-level software behaviour composed
against a monkeypatched IB-1C loader. Codex's own IB1E-R04 records that there
is no persisted two-period IB-1A/B/C-to-IB-1E integration fixture yet, and I
agree that is the honest characterisation. Nothing here establishes an official
profile, authenticated capture, complete amendment coverage, or real-package
compatibility.

### 24.7 Out-of-lane observations - documented, not fixed

Recorded under the owner's scope rule. None was changed by this review.

- **R-01 status is now partly overtaken by `main`.** The merged commit
  `eeeab137` fixed `EXE-001`, rescoping
  `_refuse_while_prior_dispatch_is_ambiguous` to exposure-increasing dispatch
  only and citing `CLAUDE.md` section 5, which is exactly the principle R-01
  raised. Whether the separate snapshot-coherence instance that R-01 originally
  named carries the same risk-reducing-sell exemption was **not determined** in
  this review; that code now lives in `assistant/portfolio_snapshot.py` and
  `execution/alpaca_broker.py` and is out of lane. R-01 should be re-scoped or
  closed by whoever owns the shared execution surface, not by this lane.
- **The parallel-phase frozen-file regime is moot.** All four lane branches are
  merged and this branch equals `main`, so the freeze that governed sections
  6-23 no longer describes the repository. The Action Plan, Session Handoff,
  direction record and workflow still describe an active parallel phase. This
  needs one owner coordination decision; a lane must not update those documents
  unilaterally.
- **Three analyst spec artifacts carried stale CRLF bytes in this worktree**
  and failed the complete suite:
  `research/analyst_revisions_v2/specs/{legacy_reproduction_registry,
  permanent_look_authority,reviewed_spec_registry}.json`. The committed
  blobs are LF and `.gitattributes` marks them `-text`, so this worktree was
  checked out before that attribute existed; `git status` hid it through the
  stat cache, exactly as the analyst lane's own test message predicts. I
  restored each file from its committed blob and verified byte-identity with
  `cmp`, so **no repository content changed** and nothing was staged. This is
  working-copy repair needed to obtain a valid validation figure, not an
  out-of-lane code fix. The underlying risk belongs to whoever owns that
  lane: a stale checkout can commit CRLF bytes into a content-addressed
  artifact, and `permanent_look_authority.json` is a research-look authority
  record where exact bytes matter.
- The remaining shared execution P1 set (R-10 through R-15, R-18) and the
  host-scoped R-09/R-20/R-22 runtime-stop observations are unchanged and remain
  outside this lane.

### 24.8 Validation performed by this review

Exact ten-file set, named so the figure is reproducible:
`test_insider_buying_form4.py`, `test_insider_buying_sec_bulk_snapshot.py`,
`test_insider_buying_sec_bulk_parsed_snapshot.py`,
`test_insider_buying_sec_edgar_acceptance_snapshot.py`,
`test_insider_buying_form4_multi_period_amendment_evidence.py`,
`test_insider_buying_implementation_record.py`, `test_ml_import_boundary.py`,
`test_project_separation_entrypoints.py`, `test_module_hygiene.py`,
`test_project_separation_boundary.py`.

- Ten-file set after this review's addition: **543 passed, 7 skipped**
  (550 collected). At the committed head without it: 549 collected.
- IB-1E mutation sweep: seven guard-condition mutants, **two caught, four
  traced to masking guards and one closed by IB1E-R06**; after the addition the
  issuer mutant is caught.
- Six direct probes of the IB1D-CR06/CR07 corrections, including the
  over-breadth check that a routine two-transaction filing still parses.
- Complete suite on the exact final review tree: **6791 passed, 13 skipped, 25 warnings in 8025.55s (2:13:45)**.
  The first attempt reported **1 failed, 6790 passed, 13 skipped, 25 warnings in 1304.28s (0:21:44)**; the single failure was
  `test_canonical_production_artifacts_survive_checkout_as_exact_bytes`,
  caused by the stale-CRLF working-copy artifacts described in 24.7 and not
  by anything in this review. It is reported here rather than omitted, and
  the rerun followed the working-copy repair on an otherwise unchanged tree.
- `compileall` over `research/insider_buying` and the changed test module: exit
  0. `git diff --check` clean apart from the repository's line-ending notice.
- This review's diff is **45 insertions, 0 deletions**, entirely in
  `tests/test_insider_buying_form4_multi_period_amendment_evidence.py`. No
  production code was changed.
- Every module was restored from git and confirmed byte-identical to `HEAD`
  after each mutation sweep.

### 24.9 Residual gates and next authorized step

Section 19.4's gate list stands. IB-1E closes only the structural cross-period
part of IB1D-R08; IB1D-R09 remains an open authority blocker and is correctly
labelled. There is still no official SEC metadata or XML profile, authenticated
capture provenance, complete amendment inventory, official original-to-amendment
link, real-package compatibility, field-level correction or supersession
semantics, canonical normalized row, joint-owner treatment, point-in-time
security mapping, post-aggregation $50,000 rule, signal, outcome, ETF
portfolio, or QuantConnect algorithm.

IB1E-R04, IB1E-R05, IB1D-R10, IB1D-CR11, IB1C-R16, IB1B-R11 and R-23 remain
deferred consolidation and test-infrastructure debt. The out-of-lane items in
24.7 need owner routing.

Next authorized step: Codex counter-reviews these Claude commits, then may
begin the next bounded Insider milestone. No live SEC ingest, research look,
outcome join, QuantConnect job, broker action, or UI work is authorized.

## 25. Codex counter-review and IB-1F persisted integration (2026-08-31)

Codex paused the `Insider Claude push monitor` heartbeat before repository
work, fetched the dedicated branch, and confirmed that local `HEAD` and
`origin/codex/strategy-insider-buying` were both
`1e3594e3108d8c48f23e1a0e3c11e78305a76651`. The worktree contained no prior
uncommitted change. This round counter-reviews Claude commits `f5ce0d41` and
`1e3594e3`, corrects their review record, and implements only the next bounded
offline Insider milestone in commit `273b0da8`.

The round changes one Insider test module and this lane record. It changes no
Trading App, Streamlit, execution, broker, risk, scheduler, signal, portfolio,
or other strategy surface. All new bytes and rows are synthetic. No SEC/EDGAR
filing or package, provider, API, credential, licensed row, market outcome,
QuantConnect job, broker, operator database, scheduler, UI, or order was
accessed. **0 research looks.**

### 25.1 Commit dispositions and merge-aware correction

| Commit | Disposition | Basis |
|---|---|---|
| `f5ce0d41` Bind supplied IB-1E XML issuers to their verified acceptance evidence | **Accepted.** | The added regression isolates the supplied-XML issuer versus IB-1C-verified primary-document-URL CIK guard while keeping the existing corpus-level same-issuer check satisfied. It passes on the unmodified tree, and an in-memory bypass of that exact guard makes the test fail with `DID NOT RAISE`. No production code changed. |
| `1e3594e3` Record review of the IB-1D counter-review and IB-1E evidence contract | **Accepted after current-record correction.** | Its code assessment and validation evidence are sound. Sections 24.2 and 24.8 undercounted the merge-aware lane history and described only the test commit's diff as the whole review diff; the superseding corrections are below. |
| `19ae3f9f` Merge pull request #322 from SheltonChen2017/codex/strategy-insider-buying | **Accepted; explicit omitted-merge disposition.** | This is the actual Insider-to-main integration merge. Every lane-owned path is byte-identical to second parent `8321c807`; there is no merge-only conflict resolution in the Insider tree. |
| `d9b05eb6` Merge updated main into Analyst Revisions after lane integrations | **Accepted as lane-carrying propagation context; explicit omitted-merge disposition.** | Every lane-owned path is byte-identical to second parent `19ae3f9f`; the merge carries the reviewed Insider tree into later history without changing it. Analyst content remains out of this lane's review scope. |

The merge-aware command `git log --full-history 3f2024b..cf136e25 --
<lane-owned paths>` returns **12**, not nine, relevant commits: the ten entries
already grouped in section 24.2 plus `19ae3f9f` and `d9b05eb6`. The other 182
commits in the 194-commit ancestry range remain merged baseline context, not
commits represented as individually reviewed for Insider behavior.

### 25.2 P0-P3 counter-review and milestone ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1E-CCR01 | P2 | Closed in this record | `1e3594e3` | Section 24 introduction and 24.2 | The review claimed every Insider commit, including the main merge, was dispositioned while counting nine and omitting both lane-carrying merges. That made an owner-mandated merge-review gate appear complete without an explicit disposition. | Full-history path traversal returns 12 commits and names `19ae3f9f` and `d9b05eb6` in addition to section 24.2's ten grouped commits. | Merge commits must be reviewed explicitly because conflict resolution can change the resulting code even when ordinary first-parent history looks clean. | Added both explicit dispositions and narrowed the remaining 182 commits to out-of-lane merged context. | Each merge's lane-owned tree is byte-identical to its lane-bearing second parent. |
| IB1E-CCR02 | P3 | Closed in this record | `1e3594e3` | Section 24.8 | “This review's diff” was stated as 45 insertions and zero deletions, but that describes only `f5ce0d41`, not the two-commit Claude range. | `cf136e25..1e3594e3` is two files, 273 insertions, and one deletion: `f5ce0d41` is 45/0 and `1e3594e3` is 228/1. | Review evidence must distinguish the test correction from the record that documents it. | This section supplies the combined and per-commit figures without rewriting historical section 24. | `git diff --shortstat` and both per-commit `git show --shortstat` results reproduce the figures. |
| IB1E-R04 | P3 | Closed only as synthetic persisted-integration debt | `273b0da8` | `tests/test_insider_buying_persisted_multi_period_evidence.py` | Prior IB-1E tests substituted the IB-1C loader, so no test proved that real persisted IB-1A/B/C artifacts could reach IB-1E across two periods. | Section 24.6 independently confirmed the missing persisted fixture. | Blueprint step 3 cannot be treated as structurally integrated solely from mocked-loader composition. | Added a real offline Q4-to-Q1 chain through all three immutable publishers/loaders and the IB-1E call-time loader. | Final module 4 passed; the complete exact-tree suite passed. This does not close IB-1, blueprint step 3, or official-data authority. |
| IB1F-A01 | P3 | Closed before commit | `273b0da8` | New path-binding refusal test | The first negative case cross-wired a receipt against a matched wrong parsed/raw pair, so mutants that ignored either caller path independently survived. | Read-only mutation audit showed raw-derived-from-parsed and parsed-derived-from-raw mutants preserved the original two tests. | Each caller-supplied upstream path must remain independently load-bearing. | Parameterized receipt-versus-pair, raw-only, and parsed-only cross-wires; each must refuse before XML parsing. | All three cases pass on the unmodified tree; the audit's path-ignoring mutants are now distinguished by the added cases. |
| IB1F-A02 | P3 | Closed before commit | `273b0da8` | New success-path transaction assertions | `all(...)` over amendment outcomes was vacuously green for zero rows and also allowed duplicates. | A read-only mutant dropping every Form 4/A transaction preserved the original material assertions. | An integration proof must pin the rows that actually crossed the boundary, not merely properties of any rows that happen to remain. | Asserted exactly one original and one amendment transaction, shares 5,000 and 6,000, exact outcome tuples, and total transaction count two. | Final success case passes and the row-dropping direction now violates the exact cardinality and identity assertions. |
| IB1E-R07 | P3 | Open - accepted record-precision debt | `6e38fa1c` | Section 19.3 historical composite count | The historical unnamed ten-file figure remains impossible to reconstruct exactly. | Claude reproduced the complete-suite and focused IB-1E results but not that unnamed composite. | Rewriting historical evidence would hide the provenance problem. | No historical rewrite. This round names its commands/files and exact-tree commit. | Current focused, complete-suite, compile, and final record-sensitive commands are stated in 25.4. |
| IB1F-D01 | P3 | Closed before record commit | This record | Section 5 session ledger boundary | The first draft left one blank line before the new ledger row, splitting the required contiguous Markdown table. Product behavior was unaffected, but the lane handoff would render incorrectly. | The first final record-sensitive run reported **1 failed, 73 passed** in `test_session_ledger_is_one_contiguous_markdown_table`. | The lane record is the branch-local handoff and must remain machine-checkable and unambiguous. | Removed the blank line; no code or historical row changed. | Exact rerun: **74 passed in 9.31s**. |

No P0 or P1 finding exists in Claude's two-commit range or in the bounded
IB-1F diff. Claude's IB1E-R06 correction is accepted as fixed. The out-of-lane
observations in section 24.7 remain documented and were not changed.

### 25.3 IB-1F contract implemented

`tests/test_insider_buying_persisted_multi_period_evidence.py` constructs two
entirely synthetic periods: a 2026-Q4 original Form 4 and a 2027-Q1 Form 4/A.
For each period it writes a real IB-1A immutable raw ZIP snapshot, builds and
loads a real IB-1B explicit-profile parsed snapshot, builds and loads a real
IB-1C acceptance-evidence snapshot, and supplies those persisted paths to the
real IB-1E assembler. The successful call contains no loader monkeypatch.

The proof pins order-independent Q4-to-Q1 composition, exact original and
amendment accession lineage, exact transaction cardinality and shares,
provisional original eligibility, amendment quarantine, and literal-false
`official_amendment_link_verified`, `complete_amendment_coverage_verified`,
and `canonical_filter_authorized` gates. Three negative cases cross-wire the
acceptance receipt, parsed directory, and raw directory in every material
independent direction and prove that the persisted boundary refuses before
any XML parse.

This is intentionally a test-only integration milestone. It adds no network
client, downloader, discovery, persisted production publisher, official
profile, authenticated amendment link, completeness claim, normalization,
canonical row, security mapping, outcome join, signal, ETF construction, or
QuantConnect implementation.

### 25.4 Validation on the exact implementation tree

- Claude regression: **1 passed** on the unmodified tree. An in-memory
  supplied-XML issuer-binding bypass made that exact test fail with
  `Failed: DID NOT RAISE`; no repository file was modified by the probe.
- Final IB-1F module:
  `pytest -q tests/test_insider_buying_persisted_multi_period_evidence.py`:
  **4 passed in 25.87s**.
- Exact named eleven-file Insider/import/hygiene/separation collection:
  **554 tests collected**, with per-file counts emitted by `pytest
  --collect-only -qq`; the list is the section 24.8 ten-file set plus
  `test_insider_buying_persisted_multi_period_evidence.py`.
- Complete suite on exact commit `273b0da8`:
  `python -B -m pytest -p no:cacheprovider --basetemp=<writable external temp>
  -q`: **6,795 passed, 13 skipped, 0 failed, 26 warnings in 2,185.89s
  (36m25s)**. This is exactly four more passing cases than Claude's final
  reviewed tree, matching the four new IB-1F cases.
- Whole-repository `compileall` over `assistant`, `backtest`, `data`,
  `execution`, `ml`, `research`, `risk`, `scripts`, `signals`, `strategies`,
  `tests`, and the root Python modules: **exit 0** with bytecode redirected
  outside the shared worktree.
- The implementation diff is **one test file, 464 insertions, zero
  deletions**. No production file changed.
- Final IB-1F, lane-record, and active-document gate over
  `test_insider_buying_persisted_multi_period_evidence.py`,
  `test_insider_buying_implementation_record.py`, and
  `test_active_document_consistency.py`: the first run was **1 failed,
  73 passed** because of IB1F-D01; after the documentation-only correction,
  the exact rerun was **74 passed in 9.31s**.
- `git diff --check` is clean apart from the repository's line-ending notice;
  a narrow secret-shape scan over the entire round diff found **0 matches**.

### 25.5 Residual gates and handoff

IB1E-R04 is closed only for the synthetic persisted integration gap.
IB1D-R09 still blocks any claim of an official SEC amendment link or complete
amendment inventory. IB-1 and blueprint section 19.4 step 3 remain incomplete,
as do official-profile validation, authenticated capture provenance,
real-package compatibility, canonical filter/quarantine, normalized security
and transaction rows, CIK-to-security mapping, joint-owner semantics,
field-level amendment supersession, post-aggregation value rules, outcomes,
ETF construction, and QC implementation. IB1E-R05, IB1D-R10, IB1D-CR11,
IB1C-R16, IB1B-R11, R-23, and the out-of-lane section 24.7 observations remain
deferred or separately owned.

Next authorized step: commit this lane record, run its record-sensitive and
diff/secret checks, confirm the remote still points to Claude's reviewed
`1e3594e3`, and make exactly one combined push containing `273b0da8` plus the
record commit. Then stop for Claude's independent review; no further Insider
milestone starts in this round.

## 26. Claude review - IB-1E counter-review and IB-1F persisted integration (2026-08-31)

Reviewer: Claude, Insider Buying lane review session, in the named lane
worktree `trading_agent_insider`. No detached or temporary worktree was
created at any point in this round.

Sync verification: `git fetch --all --prune`; local `HEAD` and
`origin/codex/strategy-insider-buying` both
`f3749ff3d757c84a2919f00e3c3e2b6107fd085e`; worktree clean; my last reviewed
head `1e3594e3` confirmed an ancestor, so no published history was rewritten.
Range reviewed: `1e3594e3..f3749ff3`, two commits, no merges.

**This review applies no correction.** Both counter-review findings against me
are correct and were already corrected in section 25; the IB-1F milestone
survived every dangerous-direction and differential probe I could construct.
The one candidate gap I found was verified as duplicate coverage and
deliberately not turned into a test. Recording that decision matters as much as
recording a fix.

### 26.1 Isolation verification

The range changes exactly two lane-owned files: this record and
`tests/test_insider_buying_persisted_multi_period_evidence.py`. No production
file changed anywhere in the range. No Trading App, Streamlit, execution,
broker, risk, scheduler, signal, portfolio, sibling-strategy, or frozen
project-wide document was touched. No SEC/EDGAR, provider, credential,
licensed row, outcome, QuantConnect, broker, operator-database, scheduler, or
UI access occurred. **0 research looks.**

### 26.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `273b0da8` Prove persisted multi-period Insider evidence integration | **Accepted.** | The integration proof is real and load-bearing, not ceremonial: a differential against the mocked-loader module shows it catches a wiring break that module is blind to by construction (26.4). Assertions are exact rather than vacuous, and the negative case proves refusal precedes XML parsing. |
| `f3749ff3` Record IB-1E counter-review and IB-1F validation | **Accepted.** | Both findings it raises against me are independently confirmed (26.3). Its IB-1F module and eleven-file collection figures reproduce exactly, and its ledger retains every prior finding including the ones it declines to close. |

### 26.3 Counter-review findings against Claude

Both are confirmed. Each was verified by running the method myself, not by
reading the record.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1E-CCR01 | P2 | Closed - my miss, accepted | `1e3594e3` | Section 24 introduction and 24.2 | I stated every Insider commit including the main merge was dispositioned, but my scoping command used default history simplification, which prunes merges whose lane-owned tree matches a parent. Two lane-carrying merges therefore never reached my table, so an owner-mandated merge-review gate looked complete when it was not. | Reproduced: the same pathspec returns **9** commits by default and **12** with `--full-history`. The three merges it reveals are `19ae3f9f`, `d9b05eb6` and `dd2cae82`; I had dispositioned only the last, having found it through the diffstat rather than the log. | Merge commits must be dispositioned explicitly because conflict resolution can change the resulting tree even when first-parent history looks clean. | Codex supplied both missing dispositions in section 25.1. I verified their substance rather than accepting them: for `19ae3f9f` and `d9b05eb6`, **zero** lane-owned files differ from their lane-bearing second parents. | I also re-verified my own `dd2cae82` disposition using the correct comparison. Its lane parent is the **first** parent, and both the combined diff (`git show --cc`) and the first-parent diff over lane paths are empty, so that merge really did leave the Insider tree unchanged. |
| IB1E-CCR02 | P3 | Closed - my miss, accepted | `1e3594e3` | Section 24.8 | I wrote "this review's diff is 45 insertions, 0 deletions", which describes only the test commit rather than the two-commit review range. | Reproduced exactly: `cf136e25..1e3594e3` is 2 files, **273 insertions, 1 deletion**; `f5ce0d41` is 45/0 and `1e3594e3` is 228/1. | Review evidence must distinguish the code correction from the record documenting it, or a later reader cannot size either. | Section 25.2 supplies combined and per-commit figures. | `git diff --shortstat` and both `git show --shortstat` results. |

A second, sharper observation belongs with CCR01. My scoping pathspec included
the literal fragment `tests/test_insider_buying_` with no glob, which matches
**zero** commits. I confirmed that directly. It did not change my conclusions,
because the diffstat surfaced the test changes anyway, but it is the second
time in this lane that a silently non-matching pathspec has sat inside a
scoping command of mine - the first produced the withdrawn IB1B-R12. Two
separate findings now trace to the same mechanical cause. The durable fix is
procedural rather than analytical: **a scoping command whose result feeds a
completeness claim must be asserted non-empty, and history-traversal commands
that feed a merge-review gate must use `--full-history`.** I have applied both
in this round.

### 26.4 Independent verification of IB-1F

The question worth answering about a test-only milestone is whether it earns
its place or merely re-covers what mocked tests already cover. I ran a
differential: break the persisted wiring, then compare the mocked-loader IB-1E
module against IB-1F.

| Wiring mutant | IB-1E (mocked loader) | IB-1F (persisted) | Meaning |
|---|---|---|---|
| upstream parsed and raw directories swapped at the call-time loader | **survived** | **caught** | IB-1F closes a real blind spot |
| call-time loader reuses the first period's upstream for every period | caught | caught | already covered; no added value, no gap |

The first row is the milestone's justification. The IB-1E fake loader keys on
the snapshot filename and ignores the upstream keyword arguments, so it cannot
observe a parsed/raw swap by construction. Only a persisted chain can. That is
exactly the gap IB1E-R04 named, and IB-1F genuinely closes it.

The success path contains no loader substitution, and its assertions are exact
rather than vacuous: one original and one amendment transaction, shares 5,000
and 6,000, exact singleton outcome tuples, `transaction_count == 2`, exact
accession ordering across the corpus and the lineage, period inventory
2026-Q4 then 2027-Q1, order independence against a reversed call, and all three
authority flags literally false. The negative case is parameterised over three
cross-wirings and installs a failing `parse_form4_xml` sentinel, so it proves
refusal happens **before** XML parsing rather than merely that it happens.

**No test weakening.** The test file is a pure addition, 464 insertions and
zero deletions; no test definition was removed anywhere in the range; and my
IB1E-R06 regression is present and unmodified.

### 26.5 A candidate finding, verified and deliberately not acted on

IB-1F has no negative case in which a tampered persisted artifact surfaces as a
refusal through IB-1E, so I checked whether that is a coverage hole. It is not,
and the check is worth recording because the conclusion is "do nothing".

Neutralising the acceptance loader's semantic-rebuild comparison leaves IB-1F
**green** but is **caught** by the IB-1C module's own tests. So the production
guard is tested where it lives. Separately, propagation of any IB-1C loader
refusal into `REFUSED: period is not a verified IB-1C boundary` is already
proven by IB-1F's path-binding case. A new tampering test would therefore
exercise an already-covered guard along a longer path and pin no distinct
property. Adding it would inflate the suite and imply coverage that the
existing tests already provide, so I did not add it.

### 26.6 Assessment

IB-1F is the right shape for what it claims and, unusually, claims no more than
it proves. Section 25.5 closes IB1E-R04 only "for the synthetic persisted
integration gap" and leaves IB1D-R09 explicitly blocking any official-link or
complete-coverage claim. Every byte in the fixture chain is synthetic, and the
milestone adds no production code, no authority, and no data access.

Stated rather than implied: a persisted chain of synthetic artifacts proves
wiring, not compatibility. No official SEC schema profile, real quarterly
package, authenticated capture provenance, or amendment-link authority exists,
and the three literal-false gates remain the correct posture.

### 26.7 Validation performed by this review

- IB-1F module: **4 passed**, reproducing the recorded figure.
- Eleven-file collection (the section 24.8 ten plus the new IB-1F module):
  **554 tests collected**, reproducing the recorded figure exactly.
- Differential mutation study: two wiring mutants across two modules, run
  separately against the mocked and persisted suites, plus one loader-guard
  mutant run against IB-1F and the IB-1C module. Every module was restored
  from git and confirmed byte-identical to `HEAD` afterwards.
- Merge-review verification: `--full-history` traversal, second-parent
  lane-path comparison for `19ae3f9f` and `d9b05eb6`, and combined-diff plus
  first-parent comparison for `dd2cae82`.
- Complete suite on the exact reviewed tree: recorded in the appended ledger
  row.
- `compileall` over `research/insider_buying` and the new test module: exit 0.
  `git diff --check` clean apart from the repository's line-ending notice.
- **This review changed no file except this record.** No correction was
  required.
- All fixtures synthetic; no SEC or provider data was accessed.

### 26.8 Residual gates and next authorized step

Section 25.5's gate list stands unchanged. IB1E-R04 is closed only for the
synthetic persisted-integration gap. IB1D-R09 remains an open authority
blocker. IB-1 and blueprint section 19.4 step 3 remain incomplete, as do
official-profile validation, authenticated capture provenance, real-package
compatibility, canonical filter/quarantine, normalized security and
transaction rows, CIK-to-security mapping, joint-owner semantics, field-level
amendment supersession, post-aggregation value rules, outcomes, ETF
construction, and QuantConnect implementation.

IB1E-R07, IB1E-R05, IB1D-R10, IB1D-CR11, IB1C-R16, IB1B-R11 and R-23 remain
deferred debt. The out-of-lane observations in section 24.7 - main's EXE-001
fix partly overtaking R-01, the now-moot parallel-phase frozen-file regime, and
the stale-CRLF artifact risk - remain documented and separately owned.

Next authorized step: Codex counter-reviews this review commit, then may begin
the next bounded Insider milestone. No live SEC ingest, research look, outcome
join, QuantConnect job, broker action, or UI work is authorized.

## 27. Codex counter-review and provisional Form 4 classification hardening (2026-09-01)

Codex worked only in the dedicated long-lived worktree
`C:\git\customizedagent\trading_agent_insider` on
`codex/strategy-insider-buying`. At the start of repository work, local
`HEAD` and `origin/codex/strategy-insider-buying` were both
`e8756630ce3558440e6d495a302928a347ce5160`; the worktree was clean and
Claude's reviewed base `f3749ff3` was an ancestor. The review range is the
sole commit `e8756630`. No branch, worktree, handoff, package, or external
service was created.

This round counter-reviews that commit, corrects its current handoff, and
implements one bounded prerequisite milestone in `dbe7c14f`: hardening the
existing provisional Form 4 classification boundary before any IB-2
disposition/filter layer is allowed to depend on it. The round changes only
`research/insider_buying/form4_xml.py`,
`tests/test_insider_buying_form4.py`, and this lane record. No Trading App,
Streamlit, execution, broker, risk, portfolio, scheduler, sibling strategy,
or frozen project-wide document changed.

### 27.1 Counter-review disposition

| Commit | Disposition | Basis |
|---|---|---|
| `e8756630` Record review of the IB-1E counter-review and IB-1F integration proof | **Accepted after current-record correction.** | Claude's code/test disposition is supported: the review commit changes only this record, its history and diff figures reproduce, the persisted IB-1F proof catches a call-time parsed/raw upstream swap that the mocked IB-1E loader cannot observe, and no production or test defect exists in the reviewed range. Four defects in the resulting current handoff are corrected by this section and the status/format edits above. |

Independent reproduction, rather than reliance on prose, established the
following:

- the relevant history command returns 9 commits under default simplification
  and 12 under `--full-history`; the literal pathspec fragment
  `tests/test_insider_buying_` matches zero paths;
- the two previously omitted lane-carrying merges preserve every lane-owned
  path byte-identically to their lane-bearing parents;
- the two-commit earlier review range is 273 insertions and one deletion,
  while its test correction alone is 45 insertions and zero deletions;
- a call-time loader with parsed and raw upstream directories swapped makes
  persisted IB-1F refuse with `REFUSED: period is not a verified IB-1C
  boundary`, while the mocked-loader side survives and the module is restored;
  and
- the reviewed tree's 4-case IB-1F module, 554-case collection, and complete
  suite claims are internally consistent with Claude's recorded evidence.

The counter-review quality rating for the reviewed IB-1F snapshot is
**9/10**. It is a strong, mutation-sensitive synthetic integration proof with
precise authority limits. It is not 10/10 because it intentionally cannot
establish official-package compatibility, authenticated amendment linkage,
or complete coverage, and its review record omitted the four handoff controls
below.

### 27.2 P0-P3 ledger

Resolved items are retained. “Closed” below means only the stated bounded
defect is closed; it does not promote any false authority gate.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for correction | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1F-CR01 | P3 | Closed in this record | `e8756630` | Section 26 assessment | The mandatory numeric 1-10 quality rating was absent, leaving the review handoff incomplete. | Section 26 contains no numeric review rating. | The standing review process requires a reproducible quality assessment rather than only an accepted/rejected label. | Added the bounded 9/10 rating and its deductions in 27.1. | Direct record inspection and the final record-sensitive gate. |
| IB1F-CR02 | P3 | Closed in this record | `e8756630` | Section 26.7 | Claude recorded diff checking but no post-edit lane-record structural check or narrow secret-shape scan for the final record-only commit. | The validation list names neither control. | The branch-local handoff is machine-checked and can itself introduce broken Markdown or credential-shaped text. | Run both controls over the final round diff and record the exact results in 27.4. | Final record-sensitive tests, `git diff --check`, and narrow diff scan below. |
| IB1F-CR03 | P3 | Closed in this record | `e8756630` | Current status header | The current status still said IB-1F awaited independent Claude review after Claude had completed and committed that review. | The pre-correction header pointed only to section 25 and called the review pending. | This file is the lane handoff; a stale top status directs the next agent to repeat completed work. | Replaced the current status with completed-review, counter-review, and new-milestone state. | Current header names section 27 and `dbe7c14f`. |
| IB1F-CR04 | P3 | Closed in this record | `e8756630` | Boundary between sections 25 and 26 | Section 26 immediately followed section 25's final paragraph without the required blank line. | Raw Markdown contained `round.` followed directly by `## 26`. | Headings require a separating blank line for stable rendering and parsing. | Inserted the blank line without rewriting either historical section. | Raw record inspection and final record-sensitive gate. |
| IB0H-R01 | P2 | Closed in `dbe7c14f` | inherited parser | `_common_stock` | Substring recognition could provisionally accept compound or semantically different instruments such as common-stock purchase rights. | Dangerous-direction title probes reproduced the fail-open. | Blueprint section 3 allows only non-derivative common equity; ambiguity must quarantine rather than become eligible. | Replaced substring/denylist behavior with a narrow positive grammar for explicit common stock, optional simple class, and optional par-value suffix. | Focused tests and common-title guard deletion mutant; independent hardening review accepted. |
| IB0H-R02 | P2 | Closed in `dbe7c14f` | inherited parser | `_footnote_features` price-range detection | Bounded range prose and numeric price-range forms could evade the prior three literal phrases and remain provisionally eligible. | Currency, comma, decimal, leading-dot, en/em dash, `through`, and `and` adversarial forms reproduced missed dangerous directions. | The blueprint explicitly quarantines price ranges; failing open changes economic value and eligibility. | Added bounded word and numeric grammars while preserving harmless private, 10b5-1, date, `from`, and `between` prose as non-range where appropriate. | Every requested token/connector deletion mutant was killed; 2 MiB near-miss probes remained linear. |
| IB0H-R03 | P2 | Closed in `dbe7c14f` | inherited parser | `_text` and `_value` | XML scalar/value containers accepted mixed content, unknown siblings, or unsupported attributes that could hide alternate economic text. | Child/tail, container text/tail/attribute, value attribute, unsupported child, and malformed footnote-reference probes reached the parser. | An offline provisional parser must refuse ambiguous structure rather than select one convenient descendant. | Enforced a strict scalar and value-container grammar with only one plain `value` plus validated empty `footnoteId` references; retained the established missing-ID refusal. | Each individual grammar-guard deletion mutant was killed and 182 Form 4 cases pass. |
| IB0H-R04 | P2 | Closed in `dbe7c14f` | inherited parser | referenced-footnote classification | Concatenating referenced footnotes could synthesize a range phrase across two unrelated notes, all filing footnotes could contaminate a row, and repeated row-level rescans amplified large-footnote cost. | Separate-footnote, unreferenced-footnote, and shared-footnote probes reproduced all three dangerous directions. | Diagnostics and exclusions must derive only from each row's immutable referenced lineage and remain bounded per filing. | Compute immutable features once per footnote ID, combine only booleans from referenced IDs, and continue preserving raw referenced prose in `ParsedTransaction.footnote_texts`. | Cache-bypass, cross-footnote-concatenation, and all-footnotes mutants were killed; 300 KB timing was effectively flat from 1 to 32 rows. |
| IB0H-R05 | P3 | Closed in `dbe7c14f` | inherited tests | Form 4 classification matrix | Several frozen directions lacked direct sensitivity: non-`A` acquired/disposed codes, nonpositive shares/price, title compounds, and the broader range grammar. | Independent read-only mutation audit showed the pre-hardening gaps and then exercised each guard independently. | These are canonical dangerous directions even though this parser remains provisional. | Added exact parameterized classification and refusal tests without deleting or loosening an existing test. | Non-`A`, shares, price, common-title, and price-range mutants all fail the final module. |
| IB0H-R06 | P3 | **Open - future boundary debt** | existing contract | public `ParsedTransaction` construction | A caller can construct or replace the public dataclass with changed economic fields while retaining an eligibility outcome. Current IB-1D/IB-1E factory and hash boundaries contain this within implemented flows, but a future filter could trust the forged object directly. | Read-only adversarial construction preserved a superficially eligible outcome with altered fields. | Fixing object provenance or redesigning the public contract would exceed this parser-hardening milestone; no current canonical filter exists. | No product change in this round. Any future disposition/filter layer must consume factory-created `ProfileBoundForm4AmendmentEvidence`, account for every transaction once, and revalidate rather than trust a caller-supplied outcome. | Remains open and must be mutation-tested at the future consumer boundary. |
| IB0H-OOL01 | P3 | **Open - documented, not fixed in this lane** | unchanged shared code | `tests/test_sleeve_report.py` fixed-clock countdown assertions | Two sleeve tests construct acquisitions from fixed `_NOW = 2026-08-07` but let production evaluate against the real clock. On 2026-09-01 the lot remains short-term while the sub-day countdown truncates to `0`, contradicting `0 < days_to_long_term`. | Both assertions failed in the complete run and isolated PTY rerun; the decimal guard passed alone. Only the two Insider parser/test files differ from `e8756630`, so sleeve production and tests are byte-identical to the reviewed base. | The owner restricted this lane to Insider strategy/QC work and requires unrelated findings to be documented, not fixed. | No sleeve, UI, or shared-code edit. | Isolated result: **2 failed, 1 passed**; exact failing values were `days_to_long_term == 0` while `term_if_sold_now == "short"`. |

No P0 or P1 finding exists in Claude's commit or the bounded implementation
diff. The P2 items are inherited parser fail-opens corrected before allowing a
new consumer to depend on them. IB0H-R06 and IB0H-OOL01 remain explicit P3
debt. Exhaustive natural-language interpretation and official SEC/XSD profile
compatibility are not claimed.

### 27.3 Bounded implementation contract

Commit `dbe7c14f` changes two files: 434 insertions and 16 deletions. The
classification remains provisional. It still emits a named outcome for every
parsed transaction, retains raw referenced footnote prose and accession
lineage, and keeps every authority gate false. It adds no normalized canonical
row, point-in-time security/share-class identity, reporting-owner resolution,
joint-owner semantics, post-aggregation value decision, authenticated
amendment link, completeness claim, downloader, signal, outcome, ETF map, or
QuantConnect surface.

Three independent read-only audits accepted the final bounded diff:

- implementation review: **182 passed**, no remaining P0-P3 in scope;
- mutation audit: every requested title, range-token, acquired/disposed,
  nonpositive-number, mixed-content, cache, cross-footnote, and contamination
  mutant was killed; and
- regex/performance audit: all adversarial cases classified correctly,
  300 KB shared-footnote work stayed effectively flat from 1 to 32 rows, and
  2 MiB near-miss inputs remained linear at 0.18-0.25 seconds.

The implementation quality rating is **9/10** for its bounded provisional
scope. The deduction is deliberate: no official profile/XSD or point-in-time
security identity has been authorized or proved, and IB0H-R06 remains for the
future consumer boundary.

### 27.4 Validation and access accounting

- Final Form 4 module:
  `python -m pytest -q tests/test_insider_buying_form4.py`:
  **182 passed**.
- Exact named eleven-file Insider/import/hygiene/separation set from sections
  24.8 and 25.4: first plain-pipe run **632 passed, 7 skipped, 1 failed** only
  because Windows `DuplicateHandle` rejected a subprocess handle in
  `test_assistant_private_runtime_identity_matches_research_behavior`; that
  case passed alone under PTY, and the exact named PTY rerun was
  **633 passed, 7 skipped in 179.07s**.
- Required complete suite on exact code commit `dbe7c14f`:
  **3 failed, 6,878 passed, 13 skipped, 25 warnings in 1,320.92s
  (22m00s)**. One failure was a Windows `git ls-files` subprocess-handle
  `WinError 50` in the decimal-conversion guard and passed in the fresh PTY
  isolation. The other two are IB0H-OOL01, reproduced unchanged and not fixed.
  Thus every Insider test and every other completed test in the run passed,
  but this record does not misstate the complete suite as zero-failure.
- Fresh isolated PTY run of the three failures: decimal-conversion guard
  **passed**; the two out-of-lane sleeve assertions **failed** with the same
  clock-boundary value.
- Whole-repository `compileall` over `assistant`, `backtest`, `data`,
  `execution`, `ml`, `research`, `risk`, `scripts`, `signals`, `strategies`,
  `tests`, and the root Python modules: **exit 0**.
- Final focused Form 4, lane-record, and active-document gate:
  **252 passed** on both post-edit runs. `git diff --check` exited 0 apart from the
  repository's LF-to-CRLF notice, and a narrow secret-shape scan over the
  entire `e8756630..` round diff found **0 matches**.

All tests used synthetic local fixtures. This round accessed no filing, real
package, API, provider data, credential, licensed row, outcome, QuantConnect
job, broker, operator database, scheduler, deployment, UI, or order.
**Research looks: 0.**

### 27.5 Residual gates and handoff

IB-1, blueprint section 19.4 step 3, IB1D-R09, official-profile validation,
authenticated capture provenance, real-package compatibility, complete
amendment coverage, point-in-time CIK/reporting-owner/security identity,
canonical filtering, field-level amendment supersession, aggregation,
post-aggregation value rules, outcomes, ETF construction, and QC remain
incomplete and unauthorized.

After the record commit, Codex must confirm the remote still points to
`e8756630`, make exactly one combined push containing `dbe7c14f` and the
record commit, and stop for Claude's independent review. If that review is
accepted and no owner gate intervenes, the next candidate bounded milestone
is an evidence-bound provisional V1 disposition/quarantine audit that consumes
only factory-created `ProfileBoundForm4AmendmentEvidence`, accounts for every
transaction exactly once, revalidates its inputs, and leaves
`canonical_filter_authorized` literally false. It must not claim to close
IB-1, blueprint step 3, IB1D-R09, mapping, aggregation, outcomes, ETF work, or
QuantConnect authority.

## 28. Claude review - provisional Form 4 classification hardening (2026-09-01)

Reviewer: Claude, Insider Buying lane review session, in the named lane
worktree `trading_agent_insider` on `codex/strategy-insider-buying`. No
detached, temporary, or additional worktree or branch was created, switched to,
or handed off at any point.

Sync verification: `git fetch --all --prune`; local `HEAD` and
`origin/codex/strategy-insider-buying` both
`933378fb6c273767ced0aa7c3e6e1b0731afde2b`; worktree clean; reviewed base
`e8756630` confirmed an ancestor, so no published history was rewritten. Range
`e8756630..933378fb`: two commits, **zero merges**, confirmed with
`--full-history` over asserted non-empty lane pathspecs.

**Outcome: accepted.** Both commits are accepted, no correction was required,
and two new P3 observations are recorded. The mandatory quality rating is in
28.6.

### 28.1 Isolation verification

The range changes exactly three lane-owned files: this record,
`research/insider_buying/form4_xml.py`, and `tests/test_insider_buying_form4.py`.
No Trading App, Streamlit, execution, broker, risk, scheduler, signal,
portfolio, sibling-strategy, or frozen project-wide file was touched. No
SEC/EDGAR filing or package, provider, API, credential, licensed row, market
outcome, QuantConnect job, broker, operator database, scheduler, deployment,
UI, or order was accessed. All fixtures are synthetic. **0 research looks.**

### 28.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `dbe7c14f` Harden provisional Form 4 classification | **Accepted.** | Every added guard is independently verified in 28.4 and every one is load-bearing: 8 of 8 dangerous-direction mutants were killed. The change closes a real fail-open in the canonical candidate set, its fail-closed direction is correct, and its performance is measured linear rather than asserted. |
| `933378fb` Record Form 4 classification hardening | **Accepted.** | Record-only. Its four findings against my prior review are all confirmed (28.3), its ledger retains resolved items, and its language is negated throughout: every occurrence of "official", "authenticated", "canonical filter" and "complete coverage" appears in a denial, so no authority is implied that the code does not hold. |

### 28.3 Counter-review findings against Claude

All four are confirmed and accepted. Each was checked against the source of
authority rather than accepted on assertion.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1F-CR01 | P3 | Closed - my miss, accepted | `e8756630` | Section 26 | I omitted the mandatory numeric 1-10 implementation-quality rating, leaving the review handoff incomplete. | I verified this is a standing requirement rather than a new one: `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md` step 9 line 377 requires "an honest 1-10 implementation-quality rating". No prior Claude section in this record contains one. | A rating is a required handoff control, and its absence across several rounds means the owner never received the assessment the process promises. | Supplied for this round in 28.6, together with the other step-9 items I had also been omitting. | Direct read of the process document and of every prior Claude section. |
| IB1F-CR02 | P3 | Closed - my miss, accepted | `e8756630` | Section 26.7 | My validation list recorded `git diff --check` but neither a post-edit lane-record structural check nor a narrow secret-shape scan. | Section 26.7's bullets confirm both are absent. I had in fact run the 74-case record-sensitive gate but did not record it; the secret-shape scan I had never run at all. | An unrecorded control cannot be audited, and the lane record is itself a file that can introduce broken Markdown or credential-shaped text. | Both controls run and recorded for this round in 28.7. | Results below, including the value-shaped scan result. |
| IB1F-CR03 | P3 | Closed - my miss, accepted | `e8756630` | Status header | After completing and committing my IB-1F review I left the top status saying IB-1F awaited independent Claude review, which would direct the next agent to repeat finished work. | My splice appended a ledger row and a section but never touched the status block. | This file is the branch-local handoff; a stale top status is an active misdirection, not a cosmetic flaw. | Codex corrected it, and I have updated the status in this round rather than repeating the omission. | Current header names this section and the reviewed commits. |
| IB1F-CR04 | P3 | Closed - my miss, accepted | `e8756630` | Boundary of sections 25 and 26 | My appended section followed the previous section's final line with no separating blank line. | Raw Markdown contained `round.` immediately followed by `## 26`. | Headings need a blank line for stable rendering and parsing of a machine-checked handoff. | Codex inserted it; this round's splice emits the separator explicitly. | Raw record inspection plus the record-sensitive gate. |

These four share one root cause worth naming, because it is different from the
causes recorded in sections 24 and 26. I had been treating
`GENERAL_CODE_REVIEW_INSTRUCTIONS.md` as the whole standing process, while
`CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md` step 9 carries additional
mandatory report controls. Having now read step 9 in full, this section
supplies all nine of its required items rather than only the rating that was
caught. The durable fix is to treat both process documents as one checklist.

### 28.4 Independent verification of the hardening

Nothing below is taken from the record; each was reproduced against the pushed
tree.

**The fail-open this closes is real and quantified.** The previous
`_common_stock` used a substring test with a five-word denylist. I reimplemented
that predicate and ran both against twelve compound instruments: **six were
previously eligible** and are all now refused - "Common Stock Purchase Rights",
"Rights to Purchase Common Stock", "Common Stock Equivalents", "Depositary
Shares representing Common Stock", "Non-Voting Common Stock Purchase Rights",
and "American Depositary Shares (each representing 2 Common Stock)". None
contains a denylisted word, so each entered `ELIGIBLE_FOR_LOT_AGGREGATION`
under the old rule. That is direct contamination of the candidate set the whole
strategy is built on, and replacing a denylist with a positive allowlist is the
right shape of fix rather than adding more blocked words.

**The grammar is not over-permissive and not over-strict on canonical titles.**
Twelve compound instruments are refused, and eleven canonical forms - bare,
upper, lower, Class A/B, and the par-value and no-par-value suffixes - are
accepted. Zero failures in either direction.

**Anti-synthesis holds, verified with paired controls.** My first attempt at a
split-footnote probe was invalid, because the half I chose was itself a complete
range phrase; recording that matters because the naive version would have
produced a false finding. I then constructed three splits where neither half
matches alone. In every case two referenced footnotes produce no price-range
exclusion, while **the identical prose inside a single footnote still does**.
The guard therefore suppresses synthesis without losing genuine detection.

**Footnote isolation holds.** A range phrase in an unreferenced footnote does
not affect the transaction, and a range in `F1` does not leak into a row that
references only `F2`.

**Performance is measured, not asserted.** Only `MAX_XML_BYTES` (2 MiB) bounds
footnote text, so I timed `_footnote_features` over adversarial inputs designed
to stress the new alternations: comma-grouped digit runs, long digit runs, a
`prices per share` prefix followed by digits, currency `and` chains, and
number-dash chains, each at 10 KB through 320 KB. Cost stayed flat at
**0.06-0.17 microseconds per character across a 16x size increase** - strictly
linear, with no catastrophic backtracking. At the 2 MiB cap the worst observed
rate implies roughly **0.34 seconds** for a single maximal footnote.

**Every new guard is load-bearing.** Eight dangerous-direction mutants, each
neutralising one guard this milestone added: the common-stock grammar reverted
to permissive substring matching, the numeric price-range patterns disabled,
scalar mixed-content refusal removed, value-container mixed-content refusal
removed, unsupported container children accepted, malformed footnote references
accepted, footnote isolation broken so every footnote affects every row, and
cross-footnote synthesis reintroduced. **8 of 8 caught.** The module was
restored from git and confirmed byte-identical to `HEAD` afterwards. This is
the strongest mutation result recorded in this lane.

**No test weakening.** The test file is a pure addition of 271 lines with zero
deletions; no test definition was removed anywhere in the range; the sixteen
production deletions are the replaced predicate and the replaced footnote
concatenation.

### 28.5 New findings

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB0H-R07 | P3 | Open - real-data grammar debt | `dbe7c14f` | `_COMMON_STOCK_TITLE_RE` | The positive grammar refuses several title forms that are ordinary on real filings, so on real data it would silently shrink the eligible candidate set. Of eight realistic borderline variants I tested, **four are refused**: a trailing period (`Common Stock, par value $0.01 per share.`), a parenthesised par value (`Common Stock ($0.01 par value)`), a spelled currency (`Common Stock, USD 0.01 par value`), and a voting qualifier (`Common Stock (voting)`). | Direct probe against the unmodified module; the other four variants, including `Class A Common Stock, par value $0.0001 per share` and mixed case, are accepted. | **Not corrected, deliberately.** Refusal is the fail-closed direction - it drops an eligible purchase rather than admitting an ineligible instrument - and widening the grammar without an official SEC profile or XSD would be exactly the guesswork this lane forbids. It is recorded so the official-profile milestone inherits concrete cases rather than rediscovering them. | No change. | Probe output retained in this review; the milestone's own scope statement already disclaims official/XSD compatibility. |
| IB0H-R08 | P3 | Open - unbudgeted per-footnote input | `dbe7c14f` | footnote text bound | There is no per-footnote or per-filing footnote-text budget; the only bound is `MAX_XML_BYTES` at 2 MiB, and every footnote is now classified through four regexes. Cost is bounded and linear, so this is not a denial-of-service finding, but the budget is implicit rather than declared. | Timings in 28.4: linear to 320 KB, implying about 0.34 s for one maximal footnote and a per-filing total bounded by the 2 MiB envelope. | **Not corrected, deliberately.** Introducing a size cap changes production refusal behaviour on a path that is measured safe, which is an implementer decision under this lane's split of roles, not a reviewer's edit. | No change. | Linear scaling measured across a 16x range; caching means each footnote is classified once per filing regardless of how many rows reference it. |
| IB0H-OOL01 | P3 | Open - out of lane, confirmed independently | unchanged shared code | `tests/test_sleeve_report.py` | Two sleeve-report tests fail. Confirmed out of lane and untouched by this range. | Reproduced: `test_default_gain_review_is_fifty_percent_and_long_term_gated` and `test_every_lot_row_carries_the_tax_mechanism_fields` fail with `assert 0 < 0` on `days_to_long_term` while `term_if_sold_now == "short"`. `git log e8756630..933378fb -- tests/test_sleeve_reinvest.py assistant/` returns zero commits. The fixture buys with `days_ago=340`, so the assertion `0 < days_to_long_term <= 30` expects roughly 25. | **Not fixed**, per owner decision 4 and the lane scope rule. | No sleeve, UI, or shared-code edit. | One routing note for the owning agent, offered as a lead rather than a diagnosis: `assistant/rebalance_trim.py:583` coerces a missing or falsy value with `int(detail.get("days_to_long_term", 0) or 0)`, so a genuinely absent countdown and a real zero are indistinguishable. Whether that is the path here was not determined and is out of scope. |

### 28.6 Mandatory implementation-quality rating

**9 / 10.**

Reasons for the score. The milestone identifies and closes a genuine fail-open
in the single most consequential predicate in the parser - which instruments
reach lot-aggregation eligibility - and it does so by replacing a denylist with
an allowlist rather than lengthening the denylist, which is the difference
between patching an instance and fixing a class. Every guard it adds is
mutation-proven load-bearing at 8 of 8. The fail-closed direction is correct
throughout: ambiguous structure, ambiguous titles, and unresolved references all
quarantine rather than qualify. Footnote handling now derives strictly from each
row's own referenced lineage, with per-footnote classification cached once, and
the anti-synthesis property survives adversarial splitting without losing
genuine detection. Performance is measured rather than asserted, and the record
claims no authority the code does not hold.

The missing point is real-data grammar coverage, not a defect. IB0H-R07 shows
the title allowlist refusing four of eight ordinary real-world variants, and
IB0H-R08 shows the input budget is implicit. Both are inherent to a provisional
offline parser with no official profile, and both are correctly out of scope for
this milestone - but until they are resolved this code cannot meet real filings,
so it would be dishonest to score it as complete. It is not lower than 9 because
nothing I could construct produced a fail-open, an over-claim, or an unproven
guard.

### 28.7 Validation performed by this review

- Form 4 module: **182 passed**, reproducing the recorded figure exactly.
- Eight-mutant dangerous-direction sweep over the new guards: **8 caught, 0
  survived**; module restored byte-identical to `HEAD`.
- Title grammar probes: 12 compound instruments refused, 11 canonical forms
  accepted, 0 failures either way; plus the six-instrument old-versus-new
  comparison in 28.4.
- Footnote probes: isolation, unreferenced non-contamination, cross-reference
  non-leakage, three genuine anti-synthesis splits, and three single-footnote
  detection controls.
- Performance probes: five adversarial shapes at three sizes each; linear.
- Complete suite on the exact reviewed tree: recorded in the appended ledger
  row, including its out-of-lane failures.
- `compileall` over `research/insider_buying` and the changed test module:
  exit 0.
- Post-edit lane-record structural and active-document gate: recorded in the
  ledger row. `git diff --check` clean apart from the repository's line-ending
  notice.
- **Narrow secret-shape scan** over the full round diff, restricted to value
  shapes (assignments of long opaque literals, PEM headers, and vendor token
  prefixes) rather than prose keywords: **0 matches**. The keyword-only variant
  matches only the words "credential" and "token" in prose and the
  `_PRICE_NUMBER_TOKEN` identifier, which is why the value-shaped form is the
  one reported.
- **This review changed no file except this record.** No correction was
  required.

### 28.8 Roadmap completeness and next authorized step

**The overall roadmap milestone is not complete.** This round hardens an
inherited provisional parser; it does not advance IB-1 or blueprint section
19.4 step 3. Still absent: official SEC profile or XSD compatibility, real
package validation, authenticated capture provenance, authenticated amendment
linkage, complete amendment coverage, point-in-time security identity,
CIK-to-security mapping, joint-owner semantics, field-level amendment
supersession, lot aggregation, the post-aggregation $50,000 rule, canonical
filtering, signals, outcomes, ETF construction, and any QuantConnect
implementation. Every authority gate remains literally false.

IB0H-R06 remains open P3 future-boundary debt and I agree with its framing: a
future consumer must consume only factory-created
`ProfileBoundForm4AmendmentEvidence`, account for every transaction once, and
revalidate rather than trust a caller-supplied `ParsedTransaction`. IB0H-R07 and
IB0H-R08 are added above. IB1E-R07, IB1E-R05, IB1D-R10, IB1D-CR11, IB1C-R16,
IB1B-R11 and R-23 remain deferred debt, and the section 24.7 out-of-lane
observations remain separately owned.

Commits this round: implementation `dbe7c14f`, its record `933378fb`, and this
review's record commit. Branch `codex/strategy-insider-buying`; exactly one
push follows this record.

Next authorized step: Codex counter-reviews this review commit and then
implements the next bounded Insider milestone. No live SEC ingest, real
package, research look, outcome join, QuantConnect job, broker action, or UI
work is authorized.

## 29. Codex counter-review of Claude's provisional Form 4 review (2026-09-01)

Counter-reviewer: Codex, in the existing dedicated worktree
`C:\git\customizedagent\trading_agent_insider` on the long-lived branch
`codex/strategy-insider-buying`. No branch, worktree, handoff, filing, package,
provider, outcome, or operational surface was created or accessed. At the
start of this counter-review, local `HEAD` and
`origin/codex/strategy-insider-buying` both pointed to
`b0e39bb15e8b966926104624d6cf9cbd594901ad`, and the worktree was clean.
The exact Claude range after the prior Codex record was
`933378fb..b0e39bb1`: one ordinary commit, zero merges, changing only this
record.

**Outcome: accepted after correction.** Claude's useful reproductions and the
two reviewed Codex commits remain accepted, but the review outcome "no
correction required" is rejected. A P2 parser defect invalidated its absolute
footnote-isolation and bounded-work claims. Commit `cb8a46a4` closes that
defect. This section supersedes section 28 wherever the two conflict; section
28 remains immutable review history.

The owner explicitly changed the normal sequencing for this round: finish
this counter-review first, start no next milestone, then have Claude review
the entire Insider Buying module and lane. That decision is binding here. No
new feature milestone was implemented.

### 29.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `b0e39bb1` Record review of the provisional Form 4 classification hardening | **Accepted after correction.** | It is record-only and preserves genuine evidence, but its accepted-without-correction disposition, 9/10 pre-correction rating, footnote-isolation conclusion, bounded-work conclusion, validation-completeness claim, and several evidence characterizations are not supportable. They are superseded below. |
| `cb8a46a4` Refuse ambiguous Form 4 footnote structures | **Accepted.** | One flat root-level `footnotes` inventory is now required before any footnote feature is classified. Nested, wrapped, duplicated, attributed, mixed-content, and tail-bearing structures fail closed, eliminating cross-ID prose inheritance and descendant-text amplification. Eleven dangerous-direction structural regressions and the complete Form 4 suite pass. |

### 29.2 Counter-review finding ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB0H-CCR01 | P2 | Closed | `cb8a46a4` | `research/insider_buying/form4_xml.py`, footnote inventory | The reviewed parser accepted nested `footnote` definitions and used descendant `itertext()`. A row referencing only an outer ID inherited a nested ID's price-range prose and was wrongly excluded; nesting also repeated the same prose once per ancestor, producing quadratic retained text and regex work inside the raw-input cap. | A synthetic row referenced only `F2`, whose nested `F1` said `Price range from 10 to 15`; the F2 text inherited F1 and received `EXCLUDE_PRICE_RANGE`. For approximately 67-69 KiB raw filings, nesting depths 1, 8, 32, and 64 retained 65,536, 524,288, 2,097,152, and 4,194,304 characters respectively. | The blueprint requires ambiguity to quarantine rather than contaminate a candidate or make bounded input imply unbounded derived work. Footnote IDs must remain isolated. | Added `_flat_footnote_definitions`; only one plain root-level container with direct, plain `footnote id=...` children is accepted. Text is read from the direct node rather than descendant `itertext()`. | On the reviewed parser, the first six new refusal cases produced **6 failed, 182 deselected**. After correction and expansion to eleven structural cases, the complete module produced **193 passed**. Neutralizing the helper in memory made all six original regressions fail and the process exited nonzero; the source was unchanged after process exit. |
| IB0H-CCR02 | P2 | Closed | this record | Section 28.7 validation | Claude did not run the mandatory whole-repository compile check, although the ledger and report said only `compileall exit 0` without the narrow scope. | Section 28.7 names only `research/insider_buying` and the changed test module. The standing review process requires compileall across the repository Python surfaces. | A required control cannot be implied by a narrower command, especially in a durable handoff. | Ran the exact whole-repository command over `assistant`, `backtest`, `data`, `execution`, `ml`, `research`, `risk`, `scripts`, `signals`, `strategies`, `tests`, and the root Python modules on immutable commit `cb8a46a4`. | Exit **0** under Python **3.14.6**. |
| IB0H-CCR03 | P3 | Closed - wording corrected; compatibility debt remains | `b0e39bb1` | IB0H-R07 and sections 28.4/28.6 | The report called synthetic title strings "ordinary on real filings" and the accepted forms "canonical" despite zero filing looks and no official profile/XSD authority. The four refusals are mechanical facts, but their real-world prevalence and canonical status are unproved. | The four named variants were independently reproduced as refused and the four named controls as accepted. All inputs were invented strings; no official corpus or real package was consulted. | Synthetic compatibility hypotheses must not be promoted into real-data or canonical claims. | IB0H-R07 remains a P3 future compatibility hypothesis. The correct labels are "plausible synthetic variants" and "currently accepted provisional forms." No grammar was widened without authority. | Direct synthetic probe reproduced all eight named outcomes; **0 research looks**. |
| IB0H-CCR04 | P3 | Closed - superseded by P2 IB0H-CCR01 | `b0e39bb1`, `cb8a46a4` | IB0H-R08 and section 28.4 | R08 said the 2 MiB envelope bounded per-filing footnote work and explicitly denied a denial-of-service concern. That conclusion was false because accepted nesting amplified retained text and repeated regex work quadratically. | The depth series in IB0H-CCR01 disproved the claimed derived-text bound. A direct single-string 2 MiB timing of roughly 0.14-0.33 seconds supports only flat single-string regex behavior, not parser-level safety. | The material defect had to be corrected, not left as an optional explicit-budget preference. | The structural correction makes every accepted footnote a flat sibling whose direct text is contained in the already bounded raw XML. R08 as written is withdrawn. A smaller separately named footnote quota remains a future policy choice, not an open defect in this bounded provisional parser. | Structural regressions, the 193-case module, the 644-case named suite, and the complete suite results in 29.5. |
| IB0H-CCR05 | P3 | Closed - evidence narrowed | `b0e39bb1` | Sections 28.4, 28.6, and 28.7 | Claude overclaimed the strength and reproducibility of its probes: eight aggregate mutants do not prove every new branch, 10 KiB to 320 KiB is 32x rather than 16x, three sizes do not establish an asymptotic proof, and the full custom 12-refused/11-accepted corpus was not retained in tests or the record. | The committed title tests enumerate 12 refused and 5 accepted forms. The eight mutants cover eight high-level dangerous directions, while the diff contains additional scalar, container, tail, attribute, and regex-alternative branches. | Review evidence must state exactly what was exercised and retained. | The supportable conclusions are that eight selected dangerous-direction categories were killed, flat single-footnote timings were linear on the tested shapes, and the named old-predicate/title outcomes were reproduced. The new structural branches now have eleven committed cases. | Complete Form 4 module **193 passed**; the new helper-neutralization mutation was killed. No "every guard" or "strongest in lane" claim is carried forward. |
| IB0H-CCR06 | P3 | Closed - out-of-lane record corrected; code untouched | `b0e39bb1` | IB0H-OOL01 | Claude cited the wrong test path in its unchanged-range proof and offered an unrelated `rebalance_trim.py` lead. | The failing file is `tests/test_sleeve_report.py`, not `tests/test_sleeve_reinvest.py`. Its executed path is `assistant.sleeve_report` to `assistant.tax_lots.unrealized_by_lot`; `rebalance_trim.py` is not imported on that path. The fixed acquisition is `2025-09-01T15:30Z`; the long-term boundary is `2026-09-02T00:00-04:00`, and a remaining positive fraction of a day truncates to zero while date classification is still short-term. | The lane must document unrelated findings accurately without editing their owner surface. | Corrected the evidence only. No sleeve, shared application, UI, or Streamlit file changed. | `git diff --quiet e8756630 933378fb -- tests/test_sleeve_report.py assistant/` returned 0 before the correction. The exact final complete suite reproduced only the same two assertions. |
| IB0H-CCR07 | P3 | Closed | this record | Section 28 validation and handoff | Claude omitted Python version, focused durations, the exact named focused file set, runtime/environment context, and an auditable final push-state statement. It also claimed all nine handoff items were supplied although the review record only said a push would follow. | Direct read of section 28 and the standing process. Python was independently resolved as 3.14.6; the focused commands and durations are now retained below. At counter-review start, local and remote were exactly `b0e39bb1`. | Reproducible validation and precise branch state are mandatory handoff evidence. | Section 29 records the interpreter, exact suites, counts, durations, immutable tested commit, branch/remote start state, and the owner-directed next action. Final remote and clean-state checks are performed immediately before and after the single push. | Validation evidence is in 29.5; final Git state is recorded in the push handoff. |

### 29.3 Independently accepted parts of Claude's review

The counter-review did not discard Claude's useful work. All six named
instruments admitted by the former substring predicate were independently
reproduced as false inclusions and are refused by the positive grammar. The
four R07 refusals and four named accepted controls were reproduced exactly.
For well-formed sibling definitions, unreferenced-footnote non-contamination,
per-row reference isolation, anti-synthesis across separate footnotes, and
once-per-definition feature caching work as intended. Direct flat-string
timings through 2 MiB showed no catastrophic regex backtracking on the tested
synthetic shapes. The two Codex commits Claude reviewed therefore remain
accepted after the nested-structure correction.

The mandatory implementation-quality rating is **9/10 for the corrected
bounded snapshot `cb8a46a4`**, not for the pre-correction tree. The point is
withheld because official-profile compatibility, point-in-time security
identity, authenticated completeness, canonical filtering, and every later
strategy layer remain deliberately unproved. Claude's section 28 rating is
superseded because its stated basis included an absolute isolation claim and a
parser-level work bound that were false on that tree.

### 29.4 Correction design and scope

The correction is intentionally fail-closed and local. A filing with no
footnote definitions is unchanged. A filing with footnotes must have exactly
one `footnotes` child directly under `ownershipDocument`; the container may
hold only direct `footnote` children, and each definition may hold only an
`id` attribute plus direct text. Container attributes or prose, nested or
wrapped definitions, multiple containers, inline child markup, extra
definition attributes, and non-whitespace tails refuse before
`_footnote_features` runs. Existing missing/duplicate ID and unresolved
reference handling remains in force.

This is provisional grammar, not an official SEC profile claim. The strict
shape is safe under the blueprint's fail-closed rule and is subject to the
owner-directed whole-module review and later official-profile authority. The
change does not ingest data, normalize events, aggregate lots, authorize a
canonical filter, construct a signal or ETF, or touch QuantConnect or UI code.

### 29.5 Validation and access accounting

All validation used Python **3.14.6** in the repository's existing virtual
environment and synthetic local fixtures only.

- Reviewed-parser red phase for the initial six structural regressions:
  **6 failed, 182 deselected** because the expected refusals did not occur.
- Corrected complete Form 4 module:
  `python -m pytest tests/test_insider_buying_form4.py -q`:
  **193 passed in 1.55s**.
- Exact named eleven-file lane/boundary suite:
  `tests/test_insider_buying_form4.py`,
  `tests/test_insider_buying_sec_bulk_snapshot.py`,
  `tests/test_insider_buying_sec_bulk_parsed_snapshot.py`,
  `tests/test_insider_buying_sec_edgar_acceptance_snapshot.py`,
  `tests/test_insider_buying_form4_multi_period_amendment_evidence.py`,
  `tests/test_insider_buying_persisted_multi_period_evidence.py`,
  `tests/test_insider_buying_implementation_record.py`,
  `tests/test_ml_import_boundary.py`,
  `tests/test_project_separation_entrypoints.py`,
  `tests/test_module_hygiene.py`, and
  `tests/test_project_separation_boundary.py`: **644 passed, 7 skipped in
  407.87s (6m47s)**.
- Required complete suite on immutable correction commit `cb8a46a4` under a
  PTY: **2 failed, 6,890 passed, 13 skipped, 25 warnings in 2,002.55s
  (33m22s)**. The only failures were
  `tests/test_sleeve_report.py::test_default_gain_review_is_fifty_percent_and_long_term_gated`
  and
  `tests/test_sleeve_report.py::test_every_lot_row_carries_the_tax_mechanism_fields`,
  both at `assert 0 < days_to_long_term` with the unchanged value 0. They are
  IB0H-OOL01, unchanged and outside this lane, and were not fixed.
- Whole-repository `compileall -q` over `assistant`, `backtest`, `data`,
  `execution`, `ml`, `research`, `risk`, `scripts`, `signals`, `strategies`,
  `tests`, `baskets.py`, `config.py`, and `market_analytics.py`: **exit 0**.
- Final post-record Form 4, lane-record, and active-document gate:
  **263 passed** on both runs, in **1.63s** and a final **1.60s** after the
  last record corrections. `git diff --check` exited 0 apart from the
  expected LF-to-CRLF notice. A value-shaped secret scan over the complete
  `b0e39bb1..` round diff found **0 matches**. Remote-tip and clean-state
  checks occur immediately before and after the single push and are reported
  in the handoff message.

No filing, real package, API, provider row, credential, licensed row, market
outcome, QuantConnect job, broker, operator database, scheduler, deployment,
UI, or order was accessed. **Research looks: 0.**

### 29.6 Residual gates and owner-directed next review

IB0H-R06 remains open future-boundary debt. IB0H-R07 is retained only as a
synthetic official-profile compatibility hypothesis. IB0H-R08 as written is
withdrawn and superseded by the closed P2 IB0H-CCR01. IB1E-R07, IB1E-R05,
IB1D-R10, IB1D-CR11, IB1C-R16, IB1B-R11, R-23, and the separately owned
out-of-lane observations remain documented under their existing scopes.

IB-1 and blueprint section 19.4 step 3 remain incomplete. No official SEC
profile, real-package validation, authenticated capture provenance,
authenticated amendment link, complete amendment coverage, point-in-time
security identity, CIK-to-security mapping, canonical filtering,
field-level amendment supersession, aggregation, post-aggregation value
rule, signal, outcome study, ETF construction, or QuantConnect implementation
is authorized or complete.

**Next action by owner decision:** after this record and `cb8a46a4` are pushed
once, Claude must independently review the complete Insider Buying strategy
module and lane, including current production code, tests, public boundaries,
all authority flags, this correction, and the accumulated implementation
record. Claude must not implement the next milestone during that audit.
Codex waits for the resulting single same-branch review push before another
counter-review decision. No next milestone starts in this round.

## 30. Claude owner-directed full-lane review (2026-09-01)

Reviewer: Claude, in the named lane worktree
`C:\git\customizedagent\trading_agent_insider` on `codex/strategy-insider-buying`.
No branch, worktree, fork, or handoff was created, switched to, or used. This
is the owner-directed first-principles audit of the entire lane; it supersedes
the normal narrow latest-range review for this round and authorizes no
milestone.

### 30.1 Synchronized starting point

The owner's expected tip `933378fb` was **stale**. The actual synchronized
state at review start was:

- local `HEAD` = `origin/codex/strategy-insider-buying` =
  **`864030a243b94392d14f49fc16daed483d9e3ed7`**, worktree clean;
- `933378fb` confirmed an ancestor of `HEAD`, so no history was rewritten;
- the three commits after the expected tip are `b0e39bb1` (my prior review
  record), `cb8a46a4` (Codex correction), and `864030a2` (Codex counter-review
  record).

Interpreter: **Python 3.14.6**. `git worktree list` confirms this lane occupies
exactly one worktree and that the other three lanes are separate checkouts.

### 30.2 File and merge-aware commit inventory

Every pathspec was asserted non-empty before use; the known-broken literal
fragment `tests/test_insider_buying_` was not used.

| Pathspec | Files |
|---|---|
| `research/insider_buying` | 8 |
| `tests/test_insider_buying_*.py` | 7 |
| `tests/fixtures/insider_buying` | 4 |
| lane record | 1 |

Merge-aware traversal (`git log --full-history` over those four pathspecs)
returns **55 commits, of which 5 are merges**, from the shared documentation
baseline `c9dcdb64` to `864030a2`. The five merges are `62b716f8`, `dd2cae82`,
`19ae3f9f`, `d9b05eb6`, and the baseline-carrying `62b716f8` chain; each was
checked for lane-owned conflict resolution and none altered the Insider tree
beyond its lane-bearing parent.

### 30.3 Commit dispositions

All 55 are dispositioned. Milestone groups carry one disposition because each
commit inside them was reviewed and dispositioned individually in the section
named beside it; the merges and the previously unreviewed tip commits are
dispositioned separately here.

| Commits | Disposition | Basis |
|---|---|---|
| `c9dcdb64`, `62b716f8` baseline and its merge | **Accepted.** | Documentation-only baseline; no lane code. |
| `8a65e3ca` .. `17c1bb28` shared remediation sync | **Accepted as synchronized, not as originated.** | Reviewed in sections 6-7; provenance verified by stable patch ID at the time. |
| `4e51e143` .. `d8561c16` IB-0/IB-1 | **Accepted after correction.** | Sections 8-9. |
| `81079156` .. `8d9e70b4` IB-1A | **Accepted after correction.** | Sections 10-11. |
| `9cbc962b` .. `60c2f297` IB-1B | **Accepted after correction.** | Sections 12-13. |
| `7b3377b1` .. `50bc8670` IB-1C | **Accepted after correction.** | Sections 14-15. |
| `73e87bce` .. `3f2024bf` IB-1D | **Accepted after correction.** | Sections 16-17. |
| `43d6d6ae`, `ad86df01` IB-1D hardening | **Accepted.** | Section 24; re-probed this round (30.5). |
| `e89293b5`, `6e38fa1c`, `f5ce0d41`, `1e3594e3` IB-1E | **Accepted after correction.** | Sections 24-25. |
| `273b0da8`, `f3749ff3`, `e8756630` IB-1F | **Accepted.** | Section 26; differential re-verified in section 26.4. |
| `dd2cae82` merge main into lane | **Accepted.** | Combined diff over lane paths empty; lane tree identical to first parent. |
| `19ae3f9f`, `d9b05eb6` PR merges | **Accepted.** | Zero lane-owned files differ from their lane-bearing second parents. |
| `dbe7c14f`, `933378fb` Form 4 hardening | **Accepted after correction.** | Section 28 accepted them, but that acceptance was incomplete: `cb8a46a4` later closed a P2 defect present in `dbe7c14f`. Superseded by 30.4. |
| `b0e39bb1` my prior review record | **Rejected in part, superseded.** | Its "no correction required" outcome and its footnote-isolation and bounded-work conclusions are wrong. See 30.4. |
| `cb8a46a4` Refuse ambiguous Form 4 footnote structures | **Accepted.** | Independently reproduced: the defect it closes and the guard it adds both verified (30.4, 30.5). |
| `864030a2` Codex counter-review record | **Accepted after one evidence correction.** | Six of its seven findings are confirmed exactly; one sub-claim is imprecise (30.4, IB0H-CCR05). |

### 30.4 Findings against my own prior review, independently reproduced

Section 29 raised seven findings against section 28. I reproduced each rather
than accepting it.

**IB0H-CCR01 (P2) is confirmed and is the most serious defect in the lane's
history.** On the exact tree I reviewed and accepted (`933378fb`), I loaded the
then-current parser side by side with the current one and fed a filing whose
row references **only** `F2`, with `F1` nested inside `F2`:

- reviewed tree `933378fb`: **PARSED**, and the row inherited the nested
  range prose, receiving `EXCLUDE_PRICE_RANGE`. The retained `F2` text was
  literally `'Outer benign note. Price range from 10 to 15 per share.'`
- current tree `864030a2`: **REFUSED**, `footnote XML structure is incomplete
  or ambiguous`.

My section 28 asserted "footnote isolation holds". It did not. The root cause
is specific and worth recording because it differs from my earlier ones: my
isolation probes varied **which** footnote a row referenced but never varied
**how footnotes were structured**. I proved isolation for flat siblings and
generalised it to isolation as such. Adversarial coverage has to vary the
structural dimension, not only the semantic one.

**IB0H-CCR02 (P2) confirmed.** I ran `compileall` only over
`research/insider_buying` and the changed test module while the ledger row said
"compileall exit 0" unscoped. The whole-repository command is run and recorded
in 30.7 for this round.

**IB0H-CCR03, CCR04, CCR06, CCR07 confirmed.** I described invented title
strings as "ordinary on real filings" and "canonical" with zero filing looks;
my IB0H-R08 conclusion that the 2 MiB envelope bounded per-filing footnote work
was false precisely because nesting amplified it; my out-of-lane proof cited
`tests/test_sleeve_reinvest.py` when the failing file is
`tests/test_sleeve_report.py`, and my `rebalance_trim.py` routing lead was
wrong - I confirmed `assistant.sleeve_report` imports `tax_lots` and does not
import `rebalance_trim`; and I omitted interpreter version, durations, the
exact focused file set, and an auditable push-state statement.

**IB0H-CCR05 confirmed except one sub-claim.** Its substantive points stand: 8
aggregate mutants do not prove every new branch, "strongest in lane" was
unsupported, and my 12-refused/11-accepted title corpus was not retained in
tests. One correction in the other direction, offered with evidence rather than
as a dispute: the report's "10 KiB to 320 KiB is 32x rather than 16x" compares
the smallest input of one shape with the largest of a different shape. Each
scaling series spans exactly 16x - comma-grouped digits 10,000 -> 40,000 ->
160,000 and currency chains 20,000 -> 80,000 -> 320,000 - and per-series
scaling is the measure that speaks to linearity. The "16x" in section 28 was
per-series and is accurate as written.

### 30.5 First-principles audit of the current tree

Reproduced directly this round, not carried over.

**Blueprint authority.** The PDF was read in full. Its SHA-256 is
`f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c`, matching
the pin in this record, so the governing authority is unchanged. Text was
extracted with a stdlib-only reader; no dependency was added.

**Authority gates.** No gate is set `True` anywhere in the lane: a search for
`canonical_filter_authorized`, `complete_amendment_coverage_verified`,
`official_amendment_link_verified` and `point_in_time_data` finds no
true-valued assignment in any module. Identity classes refuse a true flag,
result wrappers refuse a non-false identity, and public properties return
literal `False`, so the denial is three layers deep.

**Money path.** There is **no `float(` anywhere** in
`research/insider_buying`, and no float-producing operator on a money value.
`_parse_decimal` gates on an ASCII-only regex before `Decimal()`, then rejects
non-finite values, more than 64 digits, and absolute scale above 64. Verified
refused: `NaN`, `nan`, `Infinity`, `-Infinity`, `inf`, `1E999`, `1e-999`,
`0x10`, `1_000`, `1,000`, a 70-digit integer, a 70-digit fraction, the
Arabic-Indic digit `\u0663`, a full-width digit pair, and a zero-width-space
suffix. `_multiply_decimals` raises precision to the exact sum of operand digit
counts: for two 29-digit operands it returns the **truly exact** 58-digit
product, where a naive `a * b` under the default 28-digit context silently
rounds. Purchase value is therefore exact, not approximately exact.

**Blueprint section 5 fidelity.** `ALLOWED_SEC_TABLES` is exactly the
blueprint's eight tables and `REQUIRED_SEC_TABLES` is exactly the three it names
as core. The blueprint's "join without multiplying transaction rows by
joint-owner rows" holds: the joint-owner fixture yields 2 owners and **1**
transaction, and that transaction carries the named
`EXCLUDE_MULTIPLE_REPORTING_OWNERS`, not a silent drop. Form 5 parses and
receives `EXCLUDE_UNSUPPORTED_FORM`.

**No silent dropping.** `_classify` cannot return an empty tuple: with no
exclusion reason it returns `(ELIGIBLE_FOR_LOT_AGGREGATION,)`. Every parsed row
therefore carries an explicit named disposition, which is the blueprint's
"quarantine with a reason code" requirement.

**Current footnote structure guard.** Eight structural probes behave correctly:
a flat container parses, an unreferenced range does not contaminate, and
nested definitions, a footnote outside any container, two containers, a
container carrying stray text, and a footnote with an extra attribute are each
refused. Mutation: four dangerous-direction mutants, 2 caught and 2 provably
masked rather than uncovered - once the guard refuses any footnote with
children, `itertext()` is by definition equal to `.text`, and the
nested-definition identity check is redundant with the per-node child check,
which mutant 4 shows is itself load-bearing.

### 30.6 New findings

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IBFL-01 | P3 | Open - contract fidelity, not corrected | this record section 1; `research/insider_buying/form4_xml.py` | canonical contract vs `_COMMON_STOCK_TITLE_RE` | Blueprint section 2.1 item 2 admits a transaction that "represents **common equity or an equivalent ordinary share class**". This record's section 1 paraphrases that as "non-derivative **common stock**", dropping the equivalent-ordinary-share clause, and the implementation follows the narrowed wording. The provisional title grammar therefore refuses instrument titles the authority includes. | Direct probe against the unmodified module: `Ordinary Shares`, `Ordinary Shares, par value $0.0001 per share`, `Class A Ordinary Shares`, `Common Shares`, and `Common Shares, no par value` are all refused, while `Common Stock` and `Class A Common Stock` are accepted. Blueprint wording read from the hash-verified PDF. **These are constructed strings; no filing was inspected and no claim is made about their frequency in real data.** | Not corrected. Widening an eligibility grammar moves the boundary **outward**, which is the dangerous direction, and blueprint section 7 assigns "what qualifies as ordinary equity" to `security_class_normalized` in the security master - a layer this lane has explicitly deferred - while section 8 calls for "deterministic title mapping plus manual exception dictionary" that does not yet exist. A frozen enumeration belongs in the contract before the code follows it. | None. Recorded so the deferred security-identity milestone inherits the exact clause and title list rather than rediscovering them, and so the narrowed section 1 wording is not mistaken for the authority. | Probe reproduced on the exact reviewed tree; blueprint PDF hash matches its pin. |
| IBFL-02 | P3 | Open - contract precision, not corrected | this record section 1 | signal lookback wording | Section 1 states a "30-day lookback" where blueprint section 9.2 specifies the sum of event scores "for qualifying events in issuer i during the last **30 trading days**". Calendar and trading windows differ materially, and section 1 is the contract a future implementer will build to. | Both wordings read directly: record section 1 bullet 4, blueprint section 9.2. No signal code exists yet, so there is no current code impact. | Not corrected here. Section 1 is the frozen canonical contract; amending its text is a contract change rather than a bounded documentation fix, and the owner's instruction is to add a superseding correction rather than rewrite history. | None. This entry is the superseding correction: the authoritative window is **30 trading days**. | Direct comparison of the two documents. |
| IBFL-03 | P3 | Open - roadmap accuracy | this record | section 19.4 progress statements | The record consistently says "blueprint section 19.4 step 3 is not complete", which is true but understates position: **step 1 has not started at all** (no SEC quarterly package has been downloaded or hashed - IB-1A accepts only caller-supplied bytes), and step 4's required **quarantine report** artifact does not exist even though per-row outcomes do. | Blueprint section 19.4 steps read directly; IB-1A's public surface accepts `zip_bytes` from the caller and has no fetcher. | Not a defect - the lane is deliberately offline - but the handoff should name which steps are unstarted rather than only which are incomplete. | None; recorded here. | Direct read of section 19.4 and of `write_sec_bulk_snapshot`. |

### 30.7 Previously open and deferred findings

Every previously open Insider finding is carried forward; none is dropped.

| ID | Status now |
|---|---|
| IB0H-R06 | **Open.** Verified accurate as described: a caller can still construct `ParsedTransaction` directly. Current consumers are contained - `reconcile_sec_form4_amendments` and the multi-period assembler both re-parse from caller-supplied XML through `parse_form4_xml` and bind results into factory-created, hash-bound evidence, so no implemented flow trusts a caller-built transaction. The debt is real for a future filter. |
| IB0H-R07 | **Open, relabelled.** Retained as a P3 synthetic compatibility hypothesis per IB0H-CCR03; superseded in substance by IBFL-01, which supplies the blueprint clause the grammar actually diverges from. |
| IB0H-R08 | **Withdrawn**, per IB0H-CCR04. My bounded-work conclusion was false because nesting amplified retained text; `cb8a46a4` removes the amplification structurally. A named footnote quota remains a future policy choice, not an open defect. |
| IB0H-OOL01 | **Open, out of lane, evidence corrected.** Reproduced this round in the complete suite. |
| IB1C-R16 / IB1B-R11 / R-23 | **Open.** Immutable-I/O helper triplication unchanged; `form4_xml` and the amendment modules add no fourth publisher. |
| IB1E-R04 | **Closed for the synthetic persisted gap only**, as recorded. |
| IB1E-R05, IB1E-R07, IB1D-R10, IB1D-CR11 | **Open**, unchanged deferred debt. |
| IB1D-R08 | **Closed for structural composition only.** |
| IB1D-R09 | **Open authority blocker.** Correctly framed; no official amendment link exists. |
| Shared-execution set (R-01, R-10..R-15, R-18, R-09/R-20/R-22) | **Open, separately owned**, outside this lane. |

### 30.8 Architecture and data-flow assessment

The lane implements one coherent chain: caller-supplied quarterly ZIP bytes ->
IB-1A content-addressed immutable raw snapshot -> IB-1B explicit-profile parsed
snapshot with per-table row lineage and no owner-by-transaction join -> IB-1C
acceptance-evidence bundle binding EDGAR acceptance time to each accession ->
IB-1D single-period observation chronology -> IB-1E multi-period supplied-link
evidence -> IB-1F persisted integration proof. `form4_xml` sits beside this as
the provisional per-filing classifier.

The design property that matters most is that **authority never accrues by
composition**. Each layer re-derives rather than trusts: parsed snapshots
rebuild row identities and the accession index semantically, the acceptance
loader rebuilds its bundle from persisted upstream and compares, and the
multi-period assembler re-validates every supplied source against verified
acceptance evidence. Two structural choices reinforce this: factory-token
construction on public result types, and three literal-false authority
properties that no code path can flip.

The weakest structural point is the one this round exposed: the per-filing
classifier is the only layer whose input is unstructured prose, and prose
handling is where both the substring-title fail-open and the nested-footnote
contamination arose. That area deserves the most adversarial attention in
future rounds, and its guards should be varied structurally, not only
semantically.

### 30.9 Corrections made in this review

**None to code, tests, or fixtures.** The lane required no correction that is
both confirmed and bounded: `cb8a46a4` already closed the one P2 defect found
in this range, and IBFL-01 through IBFL-03 are deliberately recorded rather
than fixed for the reasons stated in their ledger rows. This section and its
ledger are the only change.

### 30.10 Validation

- Interpreter **Python 3.14.6**.
- All seven Insider test modules plus `test_ml_import_boundary`,
  `test_module_hygiene`, `test_project_separation_entrypoints`,
  `test_project_separation_boundary`, and `test_active_document_consistency`:
  **713 passed, 7 skipped in 263.89s**.
- Adversarial probes this round: 8 footnote-structure cases, 8 title-grammar
  cases plus a 12-instrument old-versus-new comparison, 18 decimal inputs, a
  joint-owner and a Form 5 case, an exact-product check against a 200-digit
  context, and the side-by-side old/new nested-footnote reproduction.
- Mutation: 4 dangerous-direction mutants against the new footnote guard, 2
  caught and 2 shown redundant by construction. Every module was restored from
  git and `git status` confirmed clean after the sweep.
- **Whole-repository `compileall`** over `assistant`, `backtest`, `data`,
  `execution`, `ml`, `research`, `risk`, `scripts`, `signals`, `strategies`,
  `tests`, and the root modules: **exit 0**.
- Complete repository suite: recorded in the appended ledger row, including
  every failure.
- `git diff --check` and a value-shaped secret scan over the complete review
  diff: results in the ledger row.

### 30.11 Lane quality rating

**8 / 10** for the Insider Buying lane as it currently stands.

What earns the score: the safety architecture is genuinely strong and is
verified rather than asserted. No authority gate can be set true anywhere; the
money path contains no floating-point arithmetic and produces exact products;
every parsed row receives a named disposition so nothing is silently dropped;
the immutable layers refuse tampering, cross-wiring and partial publication and
recover from interrupted writes; and the blueprint's structural requirements I
could check - the eight tables, the three required tables, no joint-owner row
multiplication, never overwriting raw or as-filed data, Form 5 exclusion,
ten-percent-owner handling - are implemented faithfully. The review culture is
the strongest asset: every milestone has been counter-reviewed, findings are
retained rather than deleted, and defects have consistently been caught before
any real data existed.

The two deductions. First, a P2 semantic-contamination defect - nested
footnotes leaking prose across footnote identity - survived implementation,
my independent review, and a completed review round, and was caught only on
the next counter-review. The chain worked, but it worked on the second pass,
and the shared blind spot was structural rather than semantic adversarial
coverage. Second, blueprint fidelity has drifted in the frozen contract:
section 1 narrows item 2's "equivalent ordinary share class" and softens
"30 trading days" to "30-day", and the implementation follows the record rather
than the authority. A contract that paraphrases its own authority imprecisely
will propagate that imprecision into every layer built on it.

Not lower, because no fail-open reaches the candidate set in the current tree,
the authority denial is structural rather than procedural, and every defect so
far has been found while the system is still entirely synthetic and offline -
which is exactly when defects are cheap. Not higher, because the lane has not
yet met a single real filing, and the two weakest areas are precisely the ones
real data will exercise first.

### 30.12 Authority, residual gates and access accounting

Every authority gate remains closed. The lane does **not** establish official
SEC or XSD profile compatibility, real-package compatibility, authenticated
capture provenance, authenticated amendment linkage, complete amendment
coverage, point-in-time security or share-class identity, canonical filtering
or normalized canonical rows, joint-owner resolution, field-level amendment
supersession, same-owner/security/date aggregation, the post-aggregation
$50,000 gate, signals, outcomes, ETF construction, or any QuantConnect
implementation. Blueprint section 19.4 steps 1 and 5 through 8 are unstarted;
steps 2 through 4 are partially implemented offline.

External access this round: **none**. No filing, real package, SEC or provider
data, credential, licensed row, outcome, QuantConnect job, broker, operator
database, scheduler, deployment, or order was accessed. All fixtures and probe
inputs were synthetic strings constructed in this session. The governing PDF
was read from the repository and its hash verified. **Research looks: 0.**

### 30.13 Handoff to Codex

Full-lane outcome: **accepted with no code correction required**, three new P3
contract-fidelity and roadmap-accuracy findings recorded, all prior open
findings carried forward, and one evidence sub-claim in section 29 corrected
with reproduction.

Next authorized step: Codex counter-reviews this review commit. No new
milestone was started and none is authorized by this section. The two items
most worth an implementer decision are IBFL-01, which needs a frozen
enumeration of equivalent ordinary share classes before any grammar change, and
IBFL-02, which needs section 1 reconciled to the blueprint's 30-trading-day
window. No live SEC ingest, real package, research look, outcome join,
QuantConnect job, broker action, or UI work is authorized.

## 31. Codex counter-review and bounded IB-1G provisional disposition report (2026-09-01)

Role: Codex implementer and counter-reviewer in the one named lane worktree
`C:\git\customizedagent\trading_agent_insider` on
`codex/strategy-insider-buying`. No branch, worktree, fork, merge, or handoff
was created or used. Scope remained Insider Buying strategy/QC code, tests,
and this lane record only.

### 31.1 Synchronized review state and disposition

After fetching, counter-review began from a clean, synchronized state:

- local `HEAD` = `origin/codex/strategy-insider-buying` =
  **`4a9ca17fbe6603e171316abb369b3f21203d784c`**;
- Claude's ordered review range was the single documentation commit
  `864030a243b94392d14f49fc16daed483d9e3ed7..4a9ca17fbe6603e171316abb369b3f21203d784c`;
- `4a9ca17f` changed only this lane record: 324 insertions and 3 deletions; and
- the worktree was clean and the remote tip was a fast-forward descendant of
  the last Codex snapshot.

Disposition: **`4a9ca17f` accepted after current-record correction.** Claude's
conclusion that the reviewed product tree needed no correction is accepted.
Its durable review record is not accepted verbatim because it contains two P2
and five P3 traceability/precision defects below. Historical section 30 and
its session-ledger row remain intact as Claude's review artifact; this section
is the authoritative superseding counter-review.

### 31.2 Merge-aware commit-inventory correction

The aggregate count in section 30.2 is correct: **55 commits and 5 merges**
over the asserted non-empty lane pathspecs from `c9dcdb64` through `864030a2`.
The enumerated list is not. Claude duplicated `62b716f8`, omitted
`d6d26e09`, and section 30.3 dispositioned only 50 of the 55 hashes.

The exact merges are `62b716f8`, `dd2cae82`, `d6d26e09`, `19ae3f9f`, and
`d9b05eb6`. Four carried a lane tree unchanged from one parent. The exception
is the actual reconciliation merge `d6d26e09`: relative to its first parent
`1ffb6c55`, it added 7 lines to
`research/insider_buying/form4_amendment_reconciliation.py` and 16 lines to
`tests/test_insider_buying_sec_edgar_acceptance_snapshot.py`. The 23 inserted
lines are the reconciliation already reviewed in section 24; the section
30.2 claim that no merge changed the lane beyond a lane-bearing parent is
therefore superseded.

The five hashes omitted from section 30.3 are dispositioned here:

| Commit | Disposition | Basis |
|---|---|---|
| `1ffb6c55` | **Accepted.** | Contemporaneous coordination/conflict-review record. |
| `d6d26e09` | **Accepted after reconciliation.** | Actual product/test reconciliation merge; reviewed in section 24 and re-inventoried here. |
| `466af8a7` | **Accepted.** | Reconciliation record for the same reviewed history. |
| `607b5a3e` | **Accepted.** | Local-history application record. |
| `8321c807` | **Accepted.** | Owner push-authorization record. |

### 31.3 Counter-review issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IBFL-CR01 | P2 | Closed in this record | `4a9ca17f` | sections 30.2-30.3 | The exact merge list duplicated one merge, omitted the substantive reconciliation merge, omitted five commit dispositions, and falsely said every merge carried an unchanged lane tree from a parent. This defeats the mandated every-commit disposition. | Independent full-history enumeration and parent-by-parent lane-path diffs identified the exact five omitted hashes and the 23-line `d6d26e09` delta. | A whole-lane review must be complete and merge-aware before it can be a durable handoff. | Added the exact merge list, merge-parent qualification, and five explicit dispositions in 31.2. | The corrected inventory accounts for all 55 commits and all 5 merges. |
| IBFL-CR02 | P2 | Closed in this record | `4a9ca17f` | live section 1 | Claude correctly found that the live contract narrowed blueprint section 2.1 to common stock and misstated section 9.2's 30-trading-day window, but left the active contract wrong. A future implementer could code against the stale paraphrase. | Complete blueprint read; direct comparison with section 1; `CANONICAL_SPEC.lookback_trading_days` is already 30. | The live contract must accurately state the governing PDF while code remains fail-closed where PIT identity is absent. | Section 1 now says common equity or an equivalent ordinary share class and 30 trading days; it separately documents the intentionally narrower provisional common-stock parser. | Text comparison and existing synthetic title probes; no outward grammar change was made. |
| IBFL-CR03 | P3 | Closed in this record | `4a9ca17f` | IBFL-03; roadmap wording | “Step 1 has not started at all” erased implemented caller-supplied archive/member hashing, inventory validation, and immutable raw publication. It conflated acquisition with the offline half of the step. | Direct read of `write_sec_bulk_snapshot` and its tests. | Roadmap status must distinguish unstarted acquisition/full population from implemented offline evidence mechanics. | Status and 31.7 now make the split explicit; step 4 is also narrowed to a provisional in-memory report. | Source and test review. |
| IBFL-CR04 | P3 | Closed by counter-review evidence | `4a9ca17f` | section 30.1 and handoff | Claude did not durably record the final pushed clean/equal state, despite criticizing the same omission previously. | Counter-review started after fetch with clean local and remote both at full `4a9ca17f`. | Review provenance must identify the exact pushed object accepted. | Full hashes and clean/equal start are recorded in 31.1. | Branch, upstream, ancestry, and status checks. |
| IBFL-CR05 | P3 | Closed in this record | `4a9ca17f` | section 30.6 ledger | The new finding ledger's “Commit” cells named sections or paths rather than the reviewed commit. | Direct table inspection. | A commit-by-commit ledger must trace every finding to an immutable Git object. | This superseding ledger binds all review findings to `4a9ca17f`. | Table inspection. |
| IBFL-CR06 | P3 | Closed in this record | `4a9ca17f` | section 30.7 | “Every previously open finding is carried forward” omitted `IB01-R05`, the separately owned load-fragile timeout in `tests/test_dispatch_fence.py`. | Search of the complete record and comparison of sections 8 and 30.7. | Open findings must not disappear, even when out of lane. | `IB01-R05` is restored in 31.7; it remains out of lane and was not fixed. | Record search. |
| IBFL-CR07 | P3 | Closed in this record | `4a9ca17f` | section 30.10 and session ledger | The 263-case record-sensitive gate lacks its exact file set/command and duration, so that evidence cannot be reproduced exactly from the record. | Direct comparison of the validation prose and ledger. | Review evidence must distinguish exact commands from summary labels. | The omission is retained as a historical evidence limit; this round records its own exact named file set, count, and duration below. | Final validation in 31.6. |

The independently accepted parts of Claude's review remain accepted: the
current product tree fails closed on ambiguous footnote structure; the money
path is Decimal-only and bounded; authority cannot accrue through composition;
rows are not silently dropped; and the prior out-of-lane sleeve-report
failures are real but separately owned. Claude's title strings are retained
only as **synthetic compatibility hypotheses**; no filing-frequency or
official-profile claim follows from them. `IBFL-01` is closed for the active
record wording but remains an IB-2 security-identity gate. `IBFL-02` is closed
by the live 30-trading-day correction. `IBFL-03` is only partially closed by
IB-1G; canonical filtering remains unimplemented.

### 31.4 Bounded IB-1G implementation

Commit **`5ee2c040af5e9f6cc63ac5c4d42c3af471d2a4c0`** adds
`form4_provisional_disposition_report.py` and exposes its public contract from
the Insider package. The report:

1. accepts only the exact factory-created
   `ProfileBoundForm4AmendmentEvidence` boundary from IB-1E;
2. pre-bounds the period, link, source, XML-byte, corpus, lineage, owner,
   footnote, and transaction inventories before rebuilding them;
3. revalidates the outer evidence, nested period/link/source identities,
   evidence profile, authority flags, hashes, counts, and upstream identity;
4. reconstructs every XML source from its raw fields and cached hashes,
   reparses every bounded byte image, rebuilds the as-filed corpus and
   amendment lineages, and compares them with the retained evidence;
5. emits exactly one deterministic, sorted, unique row per supplied
   transaction and hash-binds every current `ParsedTransaction` dataclass
   field, while preserving every parser outcome and diagnostic;
6. labels only a row whose sole outcome is
   `ELIGIBLE_FOR_LOT_AGGREGATION` as
   `PROVISIONAL_PRE_AGGREGATION_CANDIDATE`; every other row is retained as
   `PROVISIONAL_QUARANTINE`, including all simultaneous reasons; and
7. keeps official-profile, official-amendment-link, complete-amendment,
   point-in-time-security, canonical-filter, lot-aggregation, and outcome
   authority literal `False`, with authorized outcome looks fixed at zero.

This is a reason-coded, in-memory audit artifact, not the canonical V1 filter.
It neither aggregates nor applies the post-aggregation `$50,000` gate. A
synthetic pair of same-owner/security/date `$12,500` rows remains two separate
provisional candidates. No download, discovery, durable report publication,
security mapping, signal, outcome, ETF, QC, execution, UI, broker, deployment,
or order surface was added.

### 31.5 IB-1G implementation and audit ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1G-R01 | P2 | Closed in `5ee2c040` | `5ee2c040` | `_reparse_evidence` | An early draft did not independently revalidate every nested evidence identity, allowing coordinated partial tampering to survive outer comparisons. | Independent hostile-object probes changed nested period/link/source state and recomputed partial hashes. | The report must derive from exact bounded evidence rather than trust retained nested objects. | Added exact-type, profile, outer, nested identity, cached-source, corpus, lineage, count, and hash reconstruction. | Previously accepted hostile probes now refuse; focused tests cover each layer. |
| IB1G-R02 | P2 | Closed in `5ee2c040` | `5ee2c040` | disposition enum and module contract | The draft name `QUARANTINED_FROM_CANONICAL_V1` claimed canonical-filter authority the milestone explicitly lacks. | Contract audit compared the enum with literal-false authority flags. | A provisional report must not imply a canonical exclusion decision. | Renamed it `PROVISIONAL_QUARANTINE` and made the non-authoritative boundary explicit. | Contract tests assert the exact labels and all false gates. |
| IB1G-R03 | P2 | Closed in `5ee2c040` | `5ee2c040` | resource validation and XML reparse order | Resource validation and retained-corpus hashing initially occurred before all adversarial inputs were bounded and independently reparsed. | Hostile retained tuple/text and coherent-rehash probes. | Refusal work must remain bounded and caller-retained transactions must not become evidence. | Pre-bound every relevant inventory and byte total; reconstruct/reparse bounded XML before comparing the retained corpus and lineage. | Boundary and coherent-rehash mutations fail closed. |
| IB1G-R04 | P3 | Open - upstream provenance limit | `5ee2c040` | IB-1E -> IB-1G boundary | IB-1G proves internal consistency, not historical factory origin. A fully coordinated substitution can be internally rebuilt because IB-1E does not retain/reload the original acceptance records or metadata bytes. | Independent audit rebuilt accepted-at state, corpus, lineage, and every dependent identity consistently. | Cryptographic hashes and Python factory tokens are integrity mechanics, not authenticated historical provenance. | No change in this bounded slice. Future closure requires retained/reloaded source acceptance artifacts under separately authorized provenance work. | All related authority flags remain false; the limitation cannot create canonical eligibility. |
| IB1G-R05 | P3 | Open - deferred coupling debt | `5ee2c040` | imports from amendment/evidence modules | IB-1G reuses package-private upstream helpers and factory tokens, coupling the new verifier to internal implementation details. | Static dependency and import-boundary audit. | Consolidating all immutable/evidence validation helpers now would broaden the milestone and shared reviewed surface. | Retain with `IB1E-R05` and the existing immutable-I/O consolidation debt. | Import-boundary and module-hygiene gates remain green. |
| IB1G-R06 | P3 | Closed in `5ee2c040` | `tests/test_insider_buying_form4_multi_period_amendment_evidence.py` | transaction fingerprint future-field coverage | A future `ParsedTransaction` field could otherwise be omitted silently from the row fingerprint. | Audit compared `_transaction_payload` keys with dataclass fields. | Every parser field must remain bound into the evidence row. | Added a structural regression asserting exact equality with `dataclasses.fields(ParsedTransaction)`. | Focused suite passes; deleting a payload field fails the regression. |

`IB0H-R06` is closed only for this consumer boundary: IB-1G reparses the
factory-bound XML evidence and does not trust a directly constructed
`ParsedTransaction`. The generic public-dataclass debt remains for any future
consumer that bypasses this report.

### 31.6 Validation and access accounting

Environment: **Python 3.14.6**, pytest **9.1.1**.

- Red phase before the public IB-1G API existed: focused collection raised
  the expected `ImportError`.
- Final focused IB-1G module:
  `tests/test_insider_buying_form4_multi_period_amendment_evidence.py`:
  **40 passed in 1.24s**.
- Intermediate affected implementation suite across Form 4, multi-period,
  persisted evidence, and the ML import boundary: **248 passed in 15.81s**.
- Complete repository suite on clean committed implementation
  `5ee2c040`: **2 failed, 6914 passed, 13 skipped, 25 warnings in 1191.32s
  (0:19:51)**. The only failures are the unchanged, out-of-lane
  `tests/test_sleeve_report.py::test_default_gain_review_is_fifty_percent_and_long_term_gated`
  and
  `tests/test_sleeve_report.py::test_every_lot_row_carries_the_tax_mechanism_fields`;
  both still observe `days_to_long_term == 0` where the tests require a
  positive value. They are documented, not fixed.
- Whole-repository `python -m compileall -q` over `assistant`, `backtest`,
  `data`, `execution`, `ml`, `research`, `risk`, `scripts`, `signals`,
  `strategies`, `tests`, and `baskets.py`, `config.py`,
  `market_analytics.py`: **exit 0**.
- Exact final named Insider/boundary suite over the seven Insider test modules,
  `test_insider_buying_implementation_record`, `test_ml_import_boundary`,
  `test_module_hygiene`, both project-separation suites, and
  `test_active_document_consistency`: **737 passed, 7 skipped in 190.34s
  (0:03:10)**.
- Post-record relocation gate over `test_insider_buying_implementation_record`
  and `test_active_document_consistency`: **70 passed in 0.96s**; the same
  gate then passed **70 in 1.03s** after the evidence line was added.
- `git diff --check`: **exit 0** apart from the expected LF-to-CRLF working-copy
  notice. A narrow value-shaped secret scan over all four changed paths found
  **0 matches**.

Independent review covered contract fidelity, code/adversarial mutation,
resource ceilings, future-field fingerprinting, commit history, and record
traceability. No external access occurred. No filing, real package, SEC or
provider data, credential, licensed row, outcome, QuantConnect job, broker,
operator database, scheduler, deployment, order, or UI was accessed. Every
fixture and hostile probe was synthetic and in-memory. **Research looks: 0.**

### 31.7 Residual gates and handoff

IB-1 and blueprint section 19.4 are not complete. For step 1, acquisition,
download, and full historical population are unstarted; the offline half that
validates/hashes caller-supplied archives and members and publishes immutable
raw bytes is implemented. Steps 2 and 3 remain partial structural evidence.
Step 4 now has an in-memory provisional reason-coded report, but no durable
report publisher and no canonical filter. Steps 5 through 8 remain unstarted.

Official SEC/profile and real-package compatibility, authenticated capture
and amendment provenance, complete amendment coverage, point-in-time issuer/
owner/security/share-class identity, deterministic ordinary-equity mapping,
manual title exceptions, field-level amendment supersession, same-owner/
security/date aggregation, the post-aggregation `$50,000` gate, canonical
rows, signals, outcomes, ETF construction, and QC implementation all remain
unproven, unauthorized, or unimplemented.

Open lane debt includes `IB1G-R04`, `IB1G-R05`, `IBFL-01`'s deferred IB-2
security-mapping gate, `IB0H-R06`, the synthetic compatibility hypothesis
`IB0H-R07`, `IB1E-R07`, `IB1E-R05`, `IB1D-R10`, `IB1D-CR11`, `IB1C-R16`,
`IB1B-R11`, `R-23`, and the other previously retained authority blockers.
`IB01-R05` is restored as an open, separately owned dispatch-fence timeout;
the sleeve-report failures are likewise out of lane. Neither was fixed.

Next step: commit this record, make exactly one combined push containing
`5ee2c040` and the record commit, then stop. Claude independently reviews that
exact pushed range before any further milestone. No live acquisition, real
package, research look, outcome access, QuantConnect action, broker action, or
UI work is authorized.

## 32. Claude review - IB-1G provisional disposition report (2026-09-01)

Reviewer: Claude, in the named lane worktree
`C:\git\customizedagent\trading_agent_insider` on `codex/strategy-insider-buying`.
No branch or worktree was created, switched to, or handed off.

**Outcome: `5ee2c040` accepted; `e2eca996` accepted.** One bounded correction
was made and is committed with this record.

### 32.1 State verification

Every expected value matched exactly before review began: worktree clean;
local `HEAD` = `origin/codex/strategy-insider-buying` =
`e2eca9965d9c12c9cd136f60077d2e5552335b01`; `4a9ca17f` confirmed an ancestor;
range `4a9ca17f..e2eca996` = **2 commits, 0 merges**; **4 changed paths**;
aggregate diff **1,786 insertions, 24 deletions**. Interpreter **Python
3.14.6**, **pytest 9.1.1**.

### 32.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `5ee2c040` Add provisional Form 4 disposition report | **Accepted.** | The verifier does what it claims and its guarantees are load-bearing under mutation (32.4). Routing is singleton-equality, no aggregation or minimum-value logic exists anywhere in the module, and all eight authority fields plus the zero look-count are structurally unforgeable. One test-sensitivity gap was found and closed by this review; no production defect. |
| `e2eca996` Record IB-1G counter-review handoff | **Accepted.** | Its seven findings against my section 30 are confirmed (32.3), its deferred-limit framing is accurate (32.6), and it corrects the two contract-fidelity defects I raised last round. |

### 32.3 Codex counter-review findings against me - all confirmed

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IBFL-CR01 | P2 | Closed - my miss, confirmed | `4a9ca17f` | Section 30.2/30.3 | My merge list duplicated `62b716f8` and omitted `d6d26e09`, and my disposition table covered 50 of 55 commits, omitting `1ffb6c55`, `d6d26e09`, `466af8a7`, `607b5a3e`, `8321c807`. I also asserted no merge altered the lane tree beyond its lane-bearing parent, which is false for `d6d26e09`. | Reproduced: `--full-history --merges` over the four lane pathspecs returns exactly `62b716f8`, `dd2cae82`, `d6d26e09`, `19ae3f9f`, `d9b05eb6`. `d6d26e09` has parents `1ffb6c55` and `43d6d6ae`, and versus its **first** parent it adds **2 files changed, 23 insertions** over lane paths - exactly as recorded. | A merge-review gate cannot be satisfied by a list that duplicates one entry and drops another, and a substantive reconciliation merge must not be described as a lane-identical carry. | Codex supplied the corrected inventory. I add one precision: `d6d26e09`'s combined diff (`git show --cc`) over lane paths is **empty**, so its 23 lines came from the second parent rather than from conflict resolution - substantive relative to first-parent history, but not an evil merge. | Merge list, parent list, first-parent shortstat, and combined diff all reproduced this round. |
| IBFL-CR02 | P2 | Closed - confirmed and adopted | `4a9ca17f` | Record section 1 | The active contract still narrowed the blueprint. | Confirmed corrected in the current tree: section 1 now reads "non-derivative **common equity or an equivalent ordinary share class**" and "**30-trading-day** lookback". | This was my own IBFL-01/IBFL-02 finding; the contract is the document implementers build to. | Adopted by Codex. | Direct read of the current section 1. |
| IBFL-CR03 | P3 | Closed - accepted | `4a9ca17f` | My IBFL-03 | I called step 19.4.1 "wholly unstarted" when caller-supplied archive/member hashing, validation and immutable raw publication already exist offline. | The accurate statement is that **acquisition** is unstarted; the hashing and publication half of step 1 exists. | Evidence language must separate an absent capability from an absent input. | Accepted; restated here. | IB-1A's public surface reviewed again. |
| IBFL-CR04, CR05, CR07 | P3 | Closed - accepted | `4a9ca17f` | Section 30 | I did not durably record the final clean/equal pushed state, used sections and paths instead of immutable hashes in new ledger "Commit" cells, and gave a 263-case gate without a reproducible file set, command, or duration. | Direct read of section 30. | Ledger cells must carry immutable identifiers and validation must be reproducible. | This section records the exact file sets, durations, interpreter, and final push state. | 32.8 and the appended ledger row. |
| IBFL-CR06 | P3 | Closed - accepted | `4a9ca17f` | Section 30.7 | "All open findings carried forward" omitted `IB01-R05`. | `IB01-R05` now appears in the record; my table did not list it. | A carried-forward claim must be exhaustive or it is worse than no claim. | Accepted. `IB01-R05` remains open shared test-load debt. | Record search. |

### 32.4 Adversarial review of IB-1G

Each direction the owner named was exercised. Mutation results are from
neutralising one guard at a time in the module and running the full IB-1G
suite; the module was restored from git and confirmed clean after every batch.

| Direction | Result |
|---|---|
| Candidate/quarantine routing inversion | **caught** |
| Dropped/duplicated transaction rows | **caught** (duplicate row per transaction) |
| Non-deterministic row ordering | **caught** |
| Miscounted candidate inventory | **caught** |
| `canonical_filter_authorized` forced true in the built payload | **caught** |
| `authorized_outcome_looks` made nonzero | **caught** |
| Identity `__post_init__` authority validation removed | **caught** |
| Literal-false authority property bypassed | **caught** |
| A future `ParsedTransaction` field escaping the fingerprint | **caught** |
| Non-singleton eligible routed to candidate (`==` -> `in`) | survived - unreachable, see below |
| Eligible-plus-quarantine coexistence permitted | survived before this review; **now caught** |

**Eight of ten dangerous directions were already load-bearing.** The two
survivors are one issue, and I verified rather than assumed their status:
`_classify` returns `(ELIGIBLE_FOR_LOT_AGGREGATION,)` only when there are no
reasons, so a mixed tuple is unreachable from the current parser and no
end-to-end test can construct one. Feeding a hand-built mixed-outcome
`ParsedTransaction` directly to `_transaction_payload` on unmodified code
**refuses** with "eligible outcome cannot coexist with quarantine reasons", so
the guard is correct - it simply had no test. That is IB1G-R06 below.

The **fingerprint field-coverage guard is the strongest single control in this
milestone** and it is genuinely load-bearing: adding a field to
`ParsedTransaction` in memory takes the IB-1G module from 40 passed to 1
failed. That closes the owner's "future field escaping the fingerprint"
direction structurally rather than by vigilance.

Verified by reading rather than mutation: the module contains **no aggregation
and no `$50,000` logic at all**; `build_form4_provisional_disposition_report`
emits exactly one row per transaction over `corpus.filings x
filing.transactions`, sorted by `(accession_number, source_sha256, row_index,
event_id)`; and the eight authority fields plus `authorized_outcome_looks: 0`
are hardcoded in the identity payload, re-validated in `__post_init__`, and
re-exposed as literal-false properties - three independent layers.

### 32.5 New finding and correction

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1G-R06 | P3 | **Closed - fixed in this review** | `5ee2c040` | `form4_provisional_disposition_report.py`, `_transaction_payload` eligible-coexistence guard and the singleton routing decision | The guard that keeps candidate routing a singleton-equality decision had no test sensitivity. Neutralising it, or relaxing `==` to `in`, left all 40 IB-1G cases green. It is unreachable from today's parser, so this is depth rather than a live defect - but it is precisely the defence against the owner's "routing inversion" and "loss of one reason" directions if a future parser ever attached a reason alongside the eligible outcome. | Both mutants survived the full IB-1G suite. A hand-built mixed-outcome `ParsedTransaction` fed to `_transaction_payload` on unmodified code refuses correctly, confirming the guard works but is unexercised. | The guard is the single point that prevents a quarantined row being promoted to a candidate. An untested guard can be removed by a future refactor with the suite green. | Added `test_provisional_report_refuses_eligible_mixed_with_quarantine_reasons`, which constructs the mixed tuple directly and asserts the refusal. No production code changed. | Passes on unmodified code (41 passed, up from 40); neutralising the guard now yields **1 failed, 39 passed**; module restored byte-identical to `HEAD`. |

### 32.6 Deferred-limit framing - verified accurate

- **IB1G-R04 is correctly framed and appropriately humble.** I confirmed IB-1G
  performs **no filesystem access whatsoever** - no `open`, `Path`,
  `read_bytes`, `read_text`, loader call or directory listing appears in the
  module. The IB-1E evidence object retains `period_inventory` identities but
  not the original acceptance records or metadata artifacts, so a fully
  coordinated substitution that regenerates every hash has no external anchor
  to contradict it. IB-1G therefore proves internal consistency, not
  authenticated historical origin, exactly as stated.
- **IB1G-R05 is accurate.** The module imports the package-private
  `_build_lineages`, `_parsed_corpus_hash` and `_source_identity` from the
  reconciliation module and depends on upstream factory tokens.
- **The title-grammar framing is accurate and now honest in both directions.**
  The contract admits equivalent ordinary share classes while the parser
  deliberately keeps the narrower fail-closed common-stock grammar until IB-2
  supplies point-in-time security-class mapping and an exception dictionary.
  Because the contract was corrected this round, the divergence is now a
  disclosed deferral rather than the undisclosed drift I raised as IBFL-01.
- **IB-1 incompleteness is stated correctly** and is unchanged.

### 32.7 Test weakening

**No test was removed or weakened.** No test function is deleted anywhere in
the range; the 24 deletions are 19 lane-record lines plus five docstring and
import lines in `__init__.py` and the IB-1E test module. My own addition is
purely additive. The IB-1G tests assert externally meaningful properties -
refusals, exact counts, exact outcome tuples, determinism under reversed input
- rather than restating implementation behaviour.

### 32.8 Validation

- Interpreter **Python 3.14.6**, **pytest 9.1.1**.
- Focused IB-1G module
  (`tests/test_insider_buying_form4_multi_period_amendment_evidence.py`):
  **40 passed in 0.91s** before this review's addition, **41 passed in 0.92s**
  after.
- Named Insider/boundary suite, exact file set:
  `test_insider_buying_form4.py`, `test_insider_buying_sec_bulk_snapshot.py`,
  `test_insider_buying_sec_bulk_parsed_snapshot.py`,
  `test_insider_buying_sec_edgar_acceptance_snapshot.py`,
  `test_insider_buying_form4_multi_period_amendment_evidence.py`,
  `test_insider_buying_persisted_multi_period_evidence.py`,
  `test_insider_buying_implementation_record.py`, `test_ml_import_boundary.py`,
  `test_module_hygiene.py`, `test_project_separation_entrypoints.py`,
  `test_project_separation_boundary.py`,
  `test_active_document_consistency.py`:
  **738 passed, 7 skipped in 349.53s** - the recorded 737 plus this review's
  one new case.
- Mutation: eleven dangerous-direction mutants across two batches; every
  module restored from git and `git status` verified clean afterwards.
- Whole-repository `compileall` over `assistant`, `backtest`, `data`,
  `execution`, `ml`, `research`, `risk`, `scripts`, `signals`, `strategies`,
  `tests` and the root modules: **exit 0**.
- Complete repository suite, post-record gate, `git diff --check` and the
  value-shaped secret scan: recorded in the appended ledger row.

### 32.9 Implementation-quality rating

**Lane: 9 / 10**, raised from 8/10 last round. **IB-1G milestone: 9 / 10.**

The raise is for one specific reason with evidence, not for general progress:
the blueprint-fidelity deduction I applied last round is closed. The active
contract now reads "common equity or an equivalent ordinary share class" and
"30-trading-day lookback", matching the authority, so the document implementers
build to no longer paraphrases its own source more narrowly than the source.

IB-1G itself is strong. It refuses to trust what it is given: it reparses every
XML byte image, rebuilds the corpus and lineages, and compares them against
retained evidence rather than reading rows out of it. Its authority denial is
three layers deep and every layer is mutation-verified. The field-coverage
guard binding `_transaction_payload` to `fields(ParsedTransaction)` is the kind
of control that survives future maintainers, which is rarer than getting the
current behaviour right. And the milestone is honest about what it is not -
IB1G-R04's admission that it cannot distinguish a fully coordinated
substitution is a limitation many implementations would have left unstated.

The remaining point is not a defect but a genuine evidence gap: the lane has
still never processed a real filing, IB-1 is incomplete, blueprint steps 5
through 8 are unstarted, and the parser grammar remains deliberately narrower
than the contract pending IB-2. Those are correctly disclosed, but they mean
the lane's guarantees are all about internal consistency of synthetic inputs.
A 10 would require evidence that survives contact with real data.

### 32.10 Residual gates and handoff

Unchanged and correctly recorded: no official SEC or XSD profile
compatibility, real-package compatibility, authenticated capture provenance,
authenticated amendment linkage, complete amendment coverage, point-in-time
security or share-class identity, canonical filtering, normalized canonical
rows, joint-owner resolution, field-level amendment supersession, lot
aggregation, the post-aggregation $50,000 gate, signals, outcomes, ETF
construction, or QuantConnect implementation. All authority gates and the
authorized-look count remain literal false and zero.

Carried forward and still open: IB0H-R06, IB0H-R07 (as a synthetic
compatibility hypothesis), IB01-R05, IB1G-R04, IB1G-R05, IB1E-R05, IB1E-R07,
IB1D-R09, IB1D-R10, IB1D-CR11, IB1C-R16, IB1B-R11, R-23, and the out-of-lane
IB0H-OOL01 sleeve-report failures, which were reproduced again this round and
deliberately not fixed.

One correction to IB0H-OOL01's scope, offered for owner routing rather than
acted on: it is **not a static two-test failure**. This round reproduced a
**third** assertion, `test_report_carries_no_action_shaped_field`, failing
`assert 2 == 1` on `lots_at_gain_review`. The reviewed range and this
review's diff both touch zero files under `assistant/` or
`tests/test_sleeve_report.py`, so nothing in this lane caused it. The cause
is the same one already recorded: `_NOW = 2026-08-07` is a fixed clock used
to construct acquisitions while production evaluates against the real clock,
so each real day that passes moves another lot across the long-term boundary.
Codex observed two failures earlier the same day and this review observed
three. The failure set is therefore **drifting and will keep growing** until
the owning surface pins its clock; treating it as a fixed pair of known
failures would understate it.

External access this round: **none**. No filing, real package, SEC or provider
data, credential, licensed row, outcome, QuantConnect job, broker, operator
database, scheduler, deployment, or order. All fixtures and probe inputs were
synthetic. **Research looks: 0.**

Next authorized step: Codex counter-reviews this review commit. No milestone
was started and none is authorized here.

## 33. Codex counter-review and IB-1H immutable provisional-report snapshots (2026-09-02)

Codex worked only in
`C:\git\customizedagent\trading_agent_insider` on
`codex/strategy-insider-buying`. No branch, worktree, fork, merge, or handoff
was created or used.

The counter-review began from a clean worktree with local `HEAD` and
`origin/codex/strategy-insider-buying` both exactly
`2ef057d6294ef26afcd49542fdf7432bc4f0aa59`. Claude's review range was
`e2eca9965d9c12c9cd136f60077d2e5552335b01..2ef057d6294ef26afcd49542fdf7432bc4f0aa59`:
one commit, no merge, two changed paths, 253 insertions, and one deletion. The
bounded IB-1H implementation is
`4361232412800286a78a189223f415fdd9a7f753`.

**Outcome:** Claude's `2ef057d6` test correction is accepted after the
current-record corrections below. No product-code defect was found in Claude's
commit. Under the owner's instruction to counter-review and then implement one
next bounded milestone in the same round, IB-1H now adds an immutable,
evidence-bound persistence/reload boundary for the IB-1G provisional Form 4
disposition/quarantine report. This owner decision grants no real-data,
outcome, canonical-filter, aggregation, QuantConnect, deployment, or trading
authority.

### 33.1 Claude commit disposition

| Commit | Disposition | Basis |
|---|---|---|
| `2ef057d6294ef26afcd49542fdf7432bc4f0aa59` | **Accepted after current-record correction.** | The additive regression correctly pins the eligible-plus-quarantine coexistence refusal and no test was weakened. Independent mutation reproduced that neutralising this payload guard yields **1 failed, 40 passed**. The test does not independently execute the two later singleton-routing comparisons, which remain redundant and unreachable while the payload guard holds. Six P3 evidence/wording defects in section 32 are corrected append-only below; none is a production defect. |

### 33.2 Counter-review findings - superseding, append-only corrections

Historical section 32 is preserved. These rows supersede only the identified
current-state claims.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1G-CCR01 | P3 | Closed in this record | `2ef057d6294ef26afcd49542fdf7432bc4f0aa59` | sections 31.5 and 32.5 | Section 32 reused stable ID `IB1G-R06`, which section 31 had already assigned to future `ParsedTransaction` field-fingerprint coverage. Reuse makes the durable issue ledger ambiguous. | Direct record comparison finds two different findings under the same ID. | Stable IDs must identify exactly one finding across the lane history. | Preserve both historical rows; this section refers to Claude's eligible-coexistence test finding as **IB1G-R07**. | Record search now has an unambiguous superseding mapping without rewriting history. |
| IB1G-CCR02 | P3 | Closed in this record | `2ef057d6294ef26afcd49542fdf7432bc4f0aa59` | section 32.4/32.5 and the new coexistence regression | Claude said the new regression pins both the payload coexistence guard and singleton routing. It invokes only `_transaction_payload`; the two later equality-to-membership routing mutants remain green because the guard makes mixed outcomes unreachable. Claude also recorded the guard mutant as 1 failed / 39 passed rather than 1 failed / 40 passed. | Line-sensitive execution reaches the payload guard but not the later report routing. Replacing the routing equalities with membership tests leaves all 41 cases green; neutralising the payload guard produces **1 failed, 40 passed**. | Review evidence must distinguish the tested control from equivalent downstream logic and retain exact counts. | Accept the additive test as pinning the coexistence refusal only. Treat the later equality checks as redundant defence, not independently mutation-pinned controls. | Exact test and both mutation directions reproduced; every module was restored byte-identical afterward. |
| IB1G-CCR03 | P3 | Closed in this record | `2ef057d6294ef26afcd49542fdf7432bc4f0aa59` | section 32.4 mutation table and summary | The table contains **11** directions, while the prose says “eight of ten.” Before Claude's addition, nine listed directions were caught and two survived; afterward the coexistence guard is caught while the redundant routing mutant still survives. | Counted the table rows and reproduced the two survivor directions independently. | Mutation arithmetic must match the evidence table. | Correct total: **11 directions; 9 initially caught, 2 initially survived, and 1 of those 2 is now caught.** | Direct table recount and independent mutations. |
| IB1G-CCR04 | P3 | Closed in this record | `2ef057d6294ef26afcd49542fdf7432bc4f0aa59` | sections 32.2 and 32.4 | Claude repeatedly described “eight authority fields plus the zero look-count.” The identity has seven Boolean authority fields plus `authorized_outcome_looks`. | Runtime/dataclass inspection enumerated official profile, official amendment link, complete amendment coverage, PIT security identity, canonical filter, lot aggregation, and outcomes. | Authority accounting must not inflate or blur the actual contract. | Correct wording is **seven Boolean authority fields, all false, plus `authorized_outcome_looks == 0`**. | Structural inspection and focused assertions confirm all seven false values and zero looks. |
| IB1G-CCR05 | P3 | Closed in this record | `2ef057d6294ef26afcd49542fdf7432bc4f0aa59` | section 5 Claude ledger row and section 32.8 | Section 32.8 says the post-record gate and final pushed state are in the appended ledger row, but that row says `record gate pending` and does not record exact local/remote equality at `2ef057d6`. | Direct comparison of section 32.8 with the section 5 row. Counter-review began clean with local and remote both exactly `2ef057d6294ef26afcd49542fdf7432bc4f0aa59`. | The lane record must not claim evidence exists in a location where it is absent. | Preserve the historical row and durably record the exact observed post-review state here. Do not infer an unrecorded prior gate result. | Start-state fetch, status, and exact local/remote hash equality were independently verified. |
| IB1G-CCR06 | P3 | Closed in this record | `2ef057d6294ef26afcd49542fdf7432bc4f0aa59` | section 32.10 out-of-lane sleeve note | Claude correctly identified the fixed test clock versus real-clock mismatch, but “each real day” and “will keep growing” overstate the behavior. The failure set can change when lots cross relevant anniversary boundaries; it is not proved to grow daily or monotonically. | The three named sleeve failures were reproduced without any lane-owned file in their history range. Their outcomes depend on wall-clock-relative lot age. | An out-of-lane routing note should state the confirmed mechanism without forecasting unsupported monotonic behavior. | Retain the fixed-clock diagnosis and three observed failures; narrow the forecast to: **the failure set can drift as wall time crosses lot-age boundaries until the owning surface pins its clock.** | All three failures reproduced; no sleeve, Trading App, Streamlit, or shared production file was changed. |

### 33.3 IB-1H bounded implementation

Commit `4361232412800286a78a189223f415fdd9a7f753` adds
`form4_provisional_disposition_snapshot.py`, its public package exports, and a
dedicated synthetic test module.

The writer accepts an exact-type IB-1G report, validates its complete current
payload and seven false authority gates, serializes one canonical JSON byte
image named from `report.identity.report_id`, and publishes it immutably.
Identical retries are idempotent; different bytes at the same identity refuse.
The report-only writer proves structural self-consistency, not historical
factory origin.

The loader requires exact supplied IB-1E evidence. It validates filename,
schema, exact keys and types, hashes, row counts/order, canonical decimal text,
UTF-8, and canonical JSON before invoking the public IB-1G builder. It then
rebuilds the report from the supplied evidence and accepts the stored artifact
only when its canonical bytes equal the rebuilt snapshot bytes. Serialized
rows are never promoted directly into trusted Python evidence and no private
factory token is used to reconstruct them.

Byte, JSON-depth, row-count, and upstream resource limits are checked before
expensive parsing or rebuilding. Duplicate/unknown keys, non-finite or
noncanonical decimals, coherent readdressing, authority claims, row
duplication/reordering, filename mismatch, hard links, redirects/reparse
points, and detected read-time version changes fail closed.

IB-1H is only durable publication/reload of the existing provisional report.
It does not perform point-in-time security mapping, reporting-owner resolution,
same-owner/security/date aggregation, the post-aggregation `$50,000` gate,
canonical filtering, signal construction, outcome access, ETF construction,
or QuantConnect work.

### 33.4 IB-1H implementation findings

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1H-R01 | P2 | Closed before `43612324` | `4361232412800286a78a189223f415fdd9a7f753` | snapshot writer/loader path ancestry | An early draft could validate only the apparent leaf/root and then traverse a pre-existing nested symlink, junction, or Windows reparse ancestor while creating an output tree or opening a snapshot. That could redirect immutable publication or load outside the named lexical path. | An independent Windows junction probe made the weakened draft read and canonicalize through the redirect. | Immutable evidence must not cross an unchecked filesystem redirect. | Added lexical `lstat` validation of every existing path component before creation, after creation, under the publication lock, and before load/rebuild. Redirect, non-directory ancestor, leaf hard-link, and detected TOCTOU checks fail closed. | Simulated nested-redirect writer/loader regressions, real redirect tests where supported, hard-link tests, and version-change tests pass. |
| IB1H-R02 | P3 | Open - shared/pathname hardening limit | `4361232412800286a78a189223f415fdd9a7f753` | path ancestry and `ml.immutable_io.exclusive_file_lock` | Checks remain pathname-anchored rather than descriptor-anchored. A privileged concurrent actor could swap an ancestor between checks, and the shared lock helper does not expose its open handle so the lock pathname cannot be compared with the acquired handle after entry. | Static audit of the check/open sequence and shared lock-helper API. | Complete closure requires descriptor-relative traversal and a shared lock-handle identity contract, which would broaden this lane milestone into shared infrastructure. | No shared change. Atomic create-exclusive publication, repeated ancestry/target checks, complete-byte reread, and evidence rebuild limit the impact; all authority remains false. | Redirect, hard-link, conflict, and detected-TOCTOU tests pass. The residual concurrent pathname-swap case remains explicitly unproved. |
| IB1H-R03 | P3 | Open - provenance/attestation limit | `4361232412800286a78a189223f415fdd9a7f753` | stored `builder_git_commit` and evidence-bound reload | `builder_git_commit` is hashed structural metadata, not a signature or attestation. Rebuilding against exact supplied evidence proves current agreement, not authenticated historical origin, and the artifact is not independently usable without that evidence. | A coordinated alternate evidence graph can remain internally consistent; this is the existing `IB1G-R04` boundary. No official artifact or provenance authority was accessed. | Persistence must not be described as authenticated source provenance. | Carry `IB1G-R04` forward. The module and record describe a structural writer and evidence-bound loader, not historical attestation. | Tests refuse stored content that disagrees with unchanged evidence and accept no authority claim; authenticated historical origin remains intentionally unproved. |
| IB1H-R04 | P3 | Closed before `43612324` | `4361232412800286a78a189223f415fdd9a7f753` | module contract and writer description | An early description called the report-only writer proof of “factory-built” origin. Exact type and internal tokens establish structural construction discipline but do not authenticate historical factory invocation or upstream origin. | Contract review compared the writer's available evidence with the stronger claim. | Integrity mechanics must not be promoted into provenance authority. | Reworded the contract: the writer proves structural self-consistency; the exact-evidence rebuild performed by the loader is the trust boundary. | Current module docstring, negative-scope tests, and all literal-false authority assertions use the corrected framing. |
| IB1H-R05 | P3 | Closed before `43612324` | `4361232412800286a78a189223f415fdd9a7f753` | coherent-forgery and redundant-guard test sensitivity | Early coverage was not sensitive enough to a coherently rehashed/readdressed stored-row forgery or to removal of a local mixed-eligible/quarantine refusal before the upstream builder. | Adversarial probes recomputed dependent hashes and filenames; six redundant local guards survived the narrower draft suite. | The loader's defining guarantee is equality with a fresh upstream rebuild, and redundant fail-closed guards need direct sensitivity when they protect routing or bounded work. | Added coherent-forgery, alternate-evidence, mixed-outcome-before-builder, authority-readdressing, row-order/duplication, report-hash, resource-stage, scalar/canonical-encoding, and complete field-inventory regressions. | Focused final suite is **45 passed, 1 skipped**; the named hostile directions now refuse on the committed implementation. |

The open IB-1H P3 items are `IB1H-R02` and `IB1H-R03`. Existing
`IB1G-R05`/`IB1E-R05` private-helper and duplicated hardened immutable-I/O debt
also remains open; IB-1H does not broaden into shared-helper consolidation.
There is no open P0-P2 finding in the IB-1H commit.

### 33.5 Validation and access accounting

Environment: **Python 3.14.6**, pytest **9.1.1**.

- Focused IB-1H module,
  `tests/test_insider_buying_form4_provisional_disposition_snapshot.py`:
  **45 passed, 1 skipped in 2.46s**.
- Affected IB-1E/IB-1G/IB-1H and import/hygiene boundary set over the new
  module, `test_insider_buying_form4_multi_period_amendment_evidence.py`,
  `test_insider_buying_persisted_multi_period_evidence.py`,
  `test_ml_import_boundary.py`, and `test_module_hygiene.py`:
  **109 passed, 1 skipped in 17.09s**.
- Exact final named 13-file Insider/boundary suite - all eight
  `test_insider_buying*.py` modules plus `test_ml_import_boundary.py`,
  `test_module_hygiene.py`, both project-separation suites, and
  `test_active_document_consistency.py`: **783 passed, 8 skipped in 184.57s
  (0:03:04)**.
- Complete repository suite on clean committed implementation
  `4361232412800286a78a189223f415fdd9a7f753`: **3 failed, 6,959 passed,
  14 skipped, 25 warnings in 1,209.15s (0:20:09)**. The only failures are the
  unchanged, out-of-lane
  `tests/test_sleeve_report.py::test_default_gain_review_is_fifty_percent_and_long_term_gated`,
  `tests/test_sleeve_report.py::test_every_lot_row_carries_the_tax_mechanism_fields`,
  and
  `tests/test_sleeve_report.py::test_report_carries_no_action_shaped_field`.
  They observe the separately owned fixed-test-clock versus real-clock lot-age
  drift and were documented, not fixed.
- Whole-repository `python -m compileall -q` over `assistant`, `backtest`,
  `data`, `execution`, `ml`, **`research`**, `risk`, `scripts`, `signals`,
  `strategies`, `tests`, and the root modules: **exit 0**.
- Post-record gate over `test_insider_buying_implementation_record.py` and
  `test_active_document_consistency.py`: **70 passed in 1.04s**; the same gate
  then passed **70 in 1.06s** after its evidence line was added.
- `git diff --check`: **exit 0**. A narrow value-shaped secret scan over all
  four changed paths found **0 matches**.
- A fresh pre-push fetch left
  `origin/codex/strategy-insider-buying` exactly at
  `2ef057d6294ef26afcd49542fdf7432bc4f0aa59`; it is the direct ancestor of
  local implementation `4361232412800286a78a189223f415fdd9a7f753`, with
  only this lane-record edit uncommitted.

All validation used synthetic/local inputs. No filing, real package, SEC or
provider data, credential, licensed row, outcome, QuantConnect job, broker,
operator database, scheduler, deployment, order, or UI was accessed.
**Research looks: 0.** All seven Boolean authority fields remain literal
`False`; `authorized_outcome_looks` remains exactly `0`.

### 33.6 Residual gates and handoff

IB-1 remains incomplete. IB-1H closes only the previously recorded absence of
a durable provisional-report publisher/reloader. It does not close official
profile compatibility, authenticated source or amendment provenance, complete
coverage, point-in-time issuer/owner/security/share-class identity,
deterministic ordinary-equity mapping, manual title exceptions, field-level
amendment supersession, same-owner/security/date aggregation, the post-
aggregation `$50,000` threshold, canonical filtering, normalized canonical
rows, signals, outcomes, ETF construction, or QC implementation.

By owner decision, after the final record/diff/secret/remote gates are
recorded, Codex commits this record, verifies the remote has not advanced,
makes exactly one combined push containing `43612324` and the record commit,
then stops. Claude independently reviews that exact pushed range before
another milestone begins. No live acquisition, real package, research look,
outcome access, QuantConnect action, broker action, UI work, or trading action
is authorized.

## 34. Claude review - IB-1H snapshots and a propagated hard-link guard (2026-09-02)

Reviewer: Claude, in the lane worktree
`C:\git\customizedAgent\trading_agent_insider` on `codex/strategy-insider-buying`.
No branch, worktree, fork, or handoff was created or switched to. Reviewed
range `2ef057d6..8736b4a2`: `43612324` (IB-1H implementation) and `8736b4a2`
(counter-review and handoff record). Ancestry confirmed, no history rewritten.

### 34.1 Isolation and scope

The range touches only lane-owned paths: `research/insider_buying/`,
`tests/test_insider_buying*`, and this record. No frozen file, no sibling lane
record, no `requirements.txt`, `config.py`, or CI configuration. Verified by
listing the changed paths and excluding the lane-owned prefixes, which left an
empty set.

Under the owner's 2026-08-29 scope instruction, this review corrects
lane-specific defects only. Issues belonging to the shared platform or to
other surfaces are recorded and left untouched.

### 34.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `43612324` IB-1H immutable provisional-report snapshots | **Accepted.** | Lane-owned only; 45 passed, 1 skipped on its focused module. No network import (`urllib`, `requests`, `socket`, `http` all absent) and no `float(` anywhere in the module. The seven authority booleans are structurally enforced, not merely documented: `form4_provisional_disposition_report.py` refuses construction unless each is `is not False` and `authorized_outcome_looks == 0`. Verified by direct inspection of the enforcement block rather than from the record. |
| `8736b4a2` counter-review and handoff record | **Accepted.** | Documentation only. Its six IB1G-CCR corrections against the prior Claude review are append-only and do not rewrite history. |

### 34.3 Correction to this reviewer's prior open-findings statement

An earlier statement in this session that `IB1E-R04` was a stale open finding
was **wrong**. This record is append-only by design, so an original row may
read `Open` while a later section supersedes it. `IB1E-R04` is already recorded
closed for the synthetic persisted gap, and
`test_persisted_two_period_pipeline_reaches_ib1e_without_loader_substitution`
is exactly the fixture it asked for; it passes.

Recomputing each stable ID's **latest** status rather than grepping for the
word `Open` gives the true current position: **21 lane findings open and 22
platform findings open**, out of 127 lane findings tracked.

### 34.4 New finding, corrected and closed in this review

| ID | Sev | Status | Issue |
|---|---|---|---|
| IB1H-R06 | P2 | **FIXED in this review** | A security guard adopted by later milestones never propagated back to its siblings. The lane defines the same immutable-I/O helper set in **four** modules, one more than the three recorded by `IB1C-R16`. An AST comparison of every helper defined in more than one lane module found **16 duplicated helpers, of which 15 differ between copies**. Most differences are legitimate per-module tailoring - distinct error classes and distinct size limits - but one is not. `_read_regular_bytes` in `sec_edgar_acceptance_snapshot.py` (IB-1C) and `form4_provisional_disposition_snapshot.py` (IB-1H) refuses a file whose `st_nlink != 1`, so a committed artifact reachable under a second name is rejected as not uniquely owned. `sec_bulk_snapshot.py` (IB-1A) and `sec_bulk_parsed_snapshot.py` (IB-1B) contained **zero** `st_nlink` checks while performing the same class of immutable publication and committed reload. This is exactly the drift that `IB1B-R11` and `IB1C-R16` predicted, now demonstrated on a trust boundary rather than argued. |

**Correction applied.** The fix mirrors the existing proven pattern rather than
inventing one: `_read_regular_bytes` in both older modules gains
`require_single_link: bool = False`, and the same two conditions IB-1C uses
(`before.st_nlink != 1` before opening, `opened.st_nlink != 1` after opening).
The default is `False`, so behaviour for caller-supplied inputs is unchanged;
only the modules' own committed-artifact load paths opt in - the committed
archive and manifest in IB-1A, and the parsed rows, accessions, and manifest
artifacts in IB-1B. Five call sites total.

**Mutation-verified in both directions.** Removing the IB-1A guard fails
`test_committed_archive_with_a_hard_link_alias_refuses_load` and
`test_committed_manifest_with_a_hard_link_alias_refuses_load`; removing the
IB-1B guard fails all three parametrised parsed-artifact cases. In both
sweeps the positive control
(`test_single_link_committed_snapshot_still_loads` and its IB-1B counterpart)
kept passing, which proves the guard refuses aliased artifacts **without**
over-refusing ordinary ones. Both modules were restored from byte-exact
backups and verified clean afterwards.

`IB1C-R16` remains open and is now more precisely stated: the duplication is
fourfold, not threefold, and consolidating the helper set into one lane module
is the durable fix. That consolidation is deliberately **not** attempted here,
because it is a multi-module refactor of working evidence code rather than a
surgical defect correction.

### 34.5 Documented, not fixed - out of lane scope

Recorded under the owner's scope rule and left untouched:

- `IB1H-R02` remains open exactly as Codex framed it. Closing it needs
  descriptor-relative traversal and a lock-handle identity contract from
  `ml.immutable_io`, which is shared infrastructure.
- The two P2 authority blockers `IB1D-R09` and the residue of `IB1D-R08`, plus
  `IB1G-R04`, `IB1H-R03`, `IB1D-CR07`, and `IB0H-R07`, all close only against
  an officially sourced SEC package. No code change can close them, and no
  such acquisition is authorized.
- `IBFL-01` stays open deliberately. Widening the title grammar to admit
  "equivalent ordinary share class" moves an eligibility boundary **outward**,
  which is the dangerous direction, and the blueprint assigns that decision to
  the deferred security-identity layer with a frozen enumeration first.
- `IB0H-OOL01` and the three `tests/test_sleeve_report.py` failures remain an
  out-of-lane fixed-test-clock issue on a separately owned surface.
- The 22 open platform `R-*` findings are unchanged and uncorrected here.

### 34.6 Process defects in this review, recorded plainly

Two mistakes were made and caught during this round, both by this reviewer:

- `git checkout --` was used to restore a module after a mutation, which also
  reverted the uncommitted fix in the same file. The fix was recovered from a
  byte-exact backup taken before the mutation, and later mutations used
  backups rather than `git checkout`.
- `git stash` was run reflexively to isolate a failure, but this reviewer's own
  work was already committed, so nothing was stashed and the paired
  `git stash pop` applied a **pre-existing stash from a different branch dated
  2026-08-17**, producing conflicts in eleven unrelated files under
  `research/lean/`, `tests/test_qc_alpha_battery.py`, and an archived handoff.
  No lane file and no commit was affected. The conflicted paths were restored
  to `HEAD` individually rather than with a destructive reset, the worktree was
  confirmed clean and byte-identical to `HEAD`, and the pre-existing stash
  entry was confirmed still present and unmodified. The intended isolation
  experiment was invalid regardless, because committed work cannot be stashed;
  the attribution above rests on path analysis and on section 33.5 instead.
- A background mutation sweep against the IB-1H module was still running while
  sibling lane modules were being edited. It was found holding that module
  mutated, was stopped, the module was restored to `HEAD`, and the lane was
  searched for `MUTATED` residue with no matches. Its results were discarded
  as invalid because sibling modules changed mid-run, so **no IB-1H mutation
  sweep result is claimed by this review**.

### 34.7 Validation

- Focused hard-link regressions: IB-1A **3 passed**, IB-1B **4 passed**.
- Combined lane and boundary suite over the five Insider snapshot/evidence
  modules plus `test_ml_import_boundary.py` and `test_module_hygiene.py`:
  **451 passed, 8 skipped in 302.98s**.
- Two mutation sweeps as described in 34.4, each restored and verified clean.
- `git diff --check`: clean. Changed paths are exactly two lane modules and
  two lane test modules.
- `git diff --check`: clean. Changed paths are exactly two lane modules and
  two lane test modules.
- Complete repository suite on the code tree at `5f880c5`:
  **3 failed, 6,965 passed, 15 skipped, 25 warnings in 2,823.20s (47m03s)**,
  with `compileall` including `research/` exit 0. The three failures are the
  unchanged out-of-lane `tests/test_sleeve_report.py` cases already recorded
  as `IB0H-OOL01`. They are not attributable to this review: the changed paths
  are lane-only, `tests/test_sleeve_report.py` has no import path to
  `research.insider_buying`, and section 33.5 records the identical three
  failures at `43612324`, before these commits existed.

No SEC, EDGAR, vendor, QuantConnect, credential, licensed row, outcome,
broker, operator-database, scheduler, or UI access occurred.
**Research looks: 0.** All seven authority booleans remain literal `False`
and `authorized_outcome_looks` remains exactly `0`.

### 34.8 Residual gates and next authorized step

IB-1 remains incomplete and the ladder position is unchanged: package
acquisition and historical population are unstarted, and blueprint section
19.4 step 1 has not begun. Nothing in this review grants real-data, outcome,
canonical-filter, aggregation, QuantConnect, deployment, or trading authority.

Next authorized step: Codex counter-reviews these Claude commits, then may
continue the bounded IB ladder.

## 35. Codex counter-review of Claude's IB-1H review (2026-09-02)

Codex worked only in
`C:\git\customizedAgent\trading_agent_insider` on
`codex/strategy-insider-buying`. The worktree began clean with local `HEAD`,
the fetched remote-tracking branch, and the live remote head all exactly
`3f6c2676291f4e162ddf0aadaf1738202b69efec`. No branch, worktree, fork,
merge, handoff, rebase, or history rewrite was created or used.

The ordered counter-review range after the prior Codex handoff is
`8736b4a2b328f8bc76a81ac2fad2aa59ea1e5ff3..3f6c2676291f4e162ddf0aadaf1738202b69efec`:
two commits, no merges, five changed lane-owned paths. Each commit and its
cumulative tree were reviewed. The correction commit is
`a615304d0148b8807549e9fc36c6a76c1516daf8`.

### 35.1 Claude commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `5f880c5a75ea1f3adc497c5d7ef7f08ed41bd47d` | **Accepted after correction.** | Propagating single-link checks to IB-1A/IB-1B is correct, and the pre-existing-alias tests prove the initial-path check. The implementation omitted the reference modules' post-read and final-path link-count checks and did not protect either immutable commit marker. `a615304d` closes both generalized facets and adds independently sensitive regressions. |
| `3f6c2676291f4e162ddf0aadaf1738202b69efec` | **Accepted after current-record correction.** | The review correctly accepted IB-1H and found the sibling drift, but it closed an incomplete P2 and contains the evidence/handoff defects corrected append-only below. Its out-of-lane deferrals were appropriate. |

### 35.2 Counter-review issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1H-CCR01 | P2 | Closed in `a615304d` | `5f880c5a` | IB-1A/IB-1B regular-file readers and commit-marker loads | The propagated single-link invariant sampled only the initial path and opened handle. A link added after opening survived because version equality ignores `st_nlink`; both immutable `snapshot.commit.json` files bypassed the guard entirely. A multiply linked committed artifact can be modified through an alias after being accepted as uniquely owned. | A deterministic runtime probe added an alias at the second `fstat`; both reviewed readers returned the bytes with final link count two. New tests failed red in six directions: after-read, final-path, and hard-linked commit marker in each module. | The change claimed parity with the later immutable readers and unique ownership of the complete committed publication. Omitting later observations and the final commit marker violates that contract. | Require both `after_read.st_nlink` and `after_path.st_nlink` to remain one, pass the option through canonical-object reads, and enable it for both commit markers. Add phase-specific and public-loader regressions. | Red **6 failed, 2 passed**; corrected slice **13 passed**; full corrected IB-1A/IB-1B modules **195 passed, 5 skipped**. |
| IB1H-CCR02 | P3 | Closed in this record | `3f6c2676` | record header and current handoff | The live header still stopped at the pre-review IB-1H handoff and did not identify Claude's correction or the pending counter-review. | Direct comparison of the header, section 34, and branch head. | A stale current-state pointer can start the wrong role or range. | Section 35 establishes the exact accepted-after-correction state; the header is refreshed with the completed round in the final IB-1I handoff. | Exact hashes and ancestry were rechecked from the live remote. |
| IB1H-CCR03 | P3 | Closed in this record | `3f6c2676` | session ledger and section 34.8 | The record again called blueprint 19.4 step 1 wholly unstarted, repeating wording previously corrected by `IBFL-CR03`. Real package acquisition/full population are unstarted, but caller-supplied archive/member hashing, inventory validation, and immutable raw publication exist. | Current IB-1A API/tests and sections 10, 31.2, and 33.6. | The handoff must distinguish an absent real acquisition from implemented offline ingest contracts. | Use the precise split above. Nothing is promoted to official-package compatibility. | IB-1A full module passes; no external package was accessed. |
| IB1H-CCR04 | P3 | Closed in this record | `3f6c2676` | sections 34.6 and 34.7 | Section 34 says two process mistakes but enumerates three, and duplicates its `git diff --check` bullet. | Direct count and adjacent-line comparison. | Review evidence must be internally countable and non-duplicative. | Preserve section 34; record the correct count of **three** and treat the repeated diff bullet as one result. | Manual source comparison. |
| IB1H-CCR05 | P3 | Closed prospectively | `3f6c2676` | section 34 review evidence | The mandatory 1-10 quality rating is absent, and Python/pytest versions plus exact focused/record commands and durations are not fully reproducible from the record. | Compared section 34 with review-process step 9 and prior `IB0H-CCR07`/`IBFL-CR07` requirements. | An unrecorded environment or rating cannot be independently audited. | Do not invent Claude's missing metadata. Rating: **7/10 as submitted** because the core finding was valuable but its P2 correction was incomplete; **9/10 after `a615304d`**. Current validation records exact environment, file sets, counts, and durations in the final handoff. | Current interpreter/version and exact commands are captured with this round's validation. |
| IB1H-CCR06 | P3 | Closed by disambiguation | `3f6c2676` | sections 34.3/34.5 and historical stable IDs | The bare `21 lane / 22 platform / 127 tracked` counts are not reproducible from the stated method, partly because `IB1D-CR06` and `IB1D-CR07` were each reused for unrelated P3 and P2 findings. Section 34.5 consequently calls the older P3 `IB1D-CR07` open while the latest row under that ID is a closed P2 parser defect. | Direct expansion finds both ID collisions and no documented counting/exclusion convention. | Stable identifiers and current open-state claims must be unambiguous. | Withdraw the three bare counts. In future references, the historical open immutable-I/O item is `IB1D-CR06A` and the historical open acceptance-window evidence gate is `IB1D-CR07A`; the later P2 `IB1D-CR06`/`IB1D-CR07` parser findings remain closed. Current handoffs use named open items, not an unauditable aggregate. | Record search now maps each referenced open item to one meaning. |

### 35.3 Out-of-lane and authority-blocked findings

Claude correctly left `IB0H-OOL01`, the three drifting sleeve-report failures,
and the shared/platform `R-*` findings untouched. This counter-review also
changes no `assistant/`, execution, broker, operator-database, UI, sibling
strategy, or shared coordination file. `IB1H-R02` remains a shared/pathname
hardening limit and is not closed here.

The official-source and data-authority blockers remain open, including
`IB1D-R09`, the official-evidence residue of `IB1D-R08`, `IB1G-R04`,
`IB1H-R03`, `IB1D-CR07A`, and `IB0H-R07`. No synthetic correction can turn
them into official SEC compatibility or provenance.

### 35.4 Counter-review validation and conclusion

Environment: **Python 3.14.6**, pytest **9.1.1**.

- Direct uncorrected runtime probe: both IB-1A and IB-1B readers returned
  `b"payload"` while the accepted path had final `st_nlink == 2`.
- Exact new-regression red phase on `3f6c2676`: **6 failed, 2 passed in
  2.79s**. The failures were both post-read observations plus both unprotected
  commit markers; the opened-handle observations already passed.
- Corrected hard-link slice: **13 passed, 187 deselected in 4.79s**.
- Complete corrected `test_insider_buying_sec_bulk_snapshot.py` and
  `test_insider_buying_sec_bulk_parsed_snapshot.py`: **195 passed, 5 skipped
  in 76.69s**.
- `git diff --check`: exit 0 apart from working-copy line-ending notices.

All inputs were synthetic/local. No filing, real package, SEC/provider call,
credential, licensed row, outcome, QuantConnect job/upload/backtest, broker,
operator database, scheduler, UI, deployment, or order was accessed.
**Research looks: 0.**

**Conclusion:** the two Claude commits are accepted after correction. No
owner decision blocks a bounded, zero-authority governance re-freeze. The next
milestone is IB-1I: encode this lane's permanent four-family `1/80` ceiling,
expiry/no-redistribution rule, shared holdout, and explicit absence of any
look/cell allocation or source/outcome/QC/trading authority. Selecting or
splitting permanent alpha among the blueprint's 5/20/60-session primary
horizons remains owner-decision-required and is excluded.

## 36. IB-1I zero-authority four-family research gate (2026-09-02)

### 36.1 Scope, ancestry, and role sequence

This round stayed exclusively in
`C:\git\customizedAgent\trading_agent_insider` on the existing
`codex/strategy-insider-buying` branch. It did not switch branches, create a
worktree, merge, rebase, rewrite history, or edit a project-wide coordination
file. The exact Claude range and counter-review disposition are in section 35.
The local commits produced after Claude's reviewed head
`3f6c2676291f4e162ddf0aadaf1738202b69efec` are:

- `a615304d0148b8807549e9fc36c6a76c1516daf8` — complete the lane-specific
  hard-link invariants confirmed by counter-review;
- `322350a3` — record the commit-by-commit counter-review and retained ledger;
  and
- `b3b202d2a8bf0ecc8a3613dcbfdb3690483ad767` — implement the bounded IB-1I
  gate and its dangerous-direction tests.

The only IB-1I implementation paths are
`research/insider_buying/preregistration.py`, the public exports and package
description in `research/insider_buying/__init__.py`, and
`tests/test_insider_buying_preregistration.py`. This record is the only
documentation path changed. The action plan, three-strategy direction,
shared Strategy Description README, root Session Handoff, sibling strategies,
execution, UI, broker, and deployment surfaces remain unmodified.

### 36.2 Implemented contract

IB-1I is a structural gate, not a completed outcome preregistration and not a
QC implementation. Its canonical payload has semantic SHA-256
`f532eaf38fbdd6f3f00a4286a723ba1aa69c58f9862a596a840bd0e6d998c392`.
It binds:

- the 33-page Insider blueprint at SHA-256
  `f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c`;
- the four-family multiplicity directive to immutable source commit
  `6b12102b9710efb838e41cefd94cfcecd3ab592d`, path
  `docs/ACTION_PLAN_2026-08-20.md`, effective 2026-08-30;
- the shared-family, null, integration, and final-holdout direction to
  immutable source commit `ba01e98f9d3c8746c70182818a27a2d49a9c0fe7`,
  path `docs/THREE_STRATEGY_PROJECT_DIRECTION.md`, effective 2026-08-29;
- the fixed lane IDs `analyst-revisions-v2`, `insider-buying`,
  `short-interest`, and `target-price-revisions`, with exact rational
  two-sided family FWER `1/20` and permanent per-lane maximum and within-lane
  confirmatory ceiling `1/80`;
- permanent expiry of an unused or withdrawn slot, with transfer,
  redistribution, and denominator recomputation all false;
- the blueprint's 5/20/60-trading-day primary horizons as **candidate values
  only**. Confirmatory allocations and permanent look IDs remain empty and
  `owner_decision_required`; authorized and consumed outcome looks are both
  exact integer zero;
- shared research cutoff 2027-08-31 and an inaccessible final holdout from
  2027-09-01 through 2029-08-31;
- a valid stock-level null closing this canonical family, with post-result
  tuning/rerun and ETF/QC rescue prohibited. Any later hypothesis must be a
  separately preregistered family with a new owner-authorized permanent look
  budget and cannot retroactively rescue the canonical result; and
- future QC work only at IB-7, consuming independently reviewed immutable
  precomputed/custom signals whose research inputs cannot acquire execution
  authority.

All network, SEC, provider, credential, licensed-row, outcome, QC upload,
QC processing, QC job, QC backtest, common four-family evaluation, broker,
operator-database, scheduler, integration, capital, paper, live, deployment,
and trading authority fields are exact booleans fixed to false. The IB-0
contract version, candidate horizons, and zero-outcome authority are checked
independently against local frozen values so upstream drift refuses rather
than silently redefining this gate. No API, persistence writer, data loader,
result runner, job launcher, or execution method was added.

### 36.3 IB-1I implementation-review ledger

| ID | Priority | Status | Location | Finding and impact | Correction and verification |
|---|---|---|---|---|---|
| IB1I-R01 | P2 | Closed before `b3b202d2` | canonical payload | The first draft serialized allocation and look inventories as hard-coded empty lists. If constructor validation weakened, unauthorized inventory could leave the semantic hash unchanged. | Serialize the actual instance inventories; forged validated-shape allocation and look mutations now change the semantic hash. |
| IB1I-R02 | P2 | Closed before `b3b202d2` | stock-first/null contract | The first field name said a valid stock null closed the whole lane, overstating the owner direction, which closes only the canonical family and permits a separately preregistered later family. | Scope closure to the canonical family and separately freeze no tuning/rerun, no retroactive rescue, and the new-family plus new-owner-authorized-look-budget requirement. |
| IB1I-R03 | P2 | Closed before `b3b202d2` | authority surface | The first draft omitted explicit false fields for QC processing, common four-family evaluation, integration, capital, and QC-input execution authority. | Add, validate, serialize, directly mutate, and semantic-hash-bind every omitted field. All remain false. |
| IB1I-R04 | P3 | Closed before `b3b202d2` | governance provenance | The first draft bound only the older blueprint; an intermediate correction hashed whole mutable coordination files, which would fail on an unrelated future documentation edit. | Bind the two later directives by exact immutable source commit, path, identifier, and effective date. Tests verify the active documents still carry the named clauses without hashing unrelated bytes. |
| IB1I-R05 | P2 | Closed before `b3b202d2` | dangerous-direction tests | The initial denylist missed direct network modules and the matrix omitted forged version/blueprint, withdrawn disposition, collection type confusion, and falsey non-boolean authority. | Replace the denylist with an exact import allowlist plus dynamic-import prohibition; add each omitted mutation. The final focused suite has 120 tests. |
| IB1I-R06 | P2 | Closed before `b3b202d2` | nested types and IB-0 binding | Tuple equality alone admitted float horizons equal to integers and string subclasses; deriving both default and expectation from `CANONICAL_SPEC` let upstream horizon drift redefine the supposedly sealed gate. | Require exact member types, freeze 5/20/60 locally, and independently refuse IB-0 horizon drift. Regression mutates IB-0 and restores it in `finally`. |
| IB1I-R07 | P3 | Closed before `b3b202d2` | import and diagnostics | A denylist could admit an unlisted authority surface, and one compound null-policy error message could misidentify a new-family or rerun violation as ETF/QC rescue. | Enforce the exact seven-root import set with no dynamic import call and use field-specific true/false refusal messages. |
| IB1I-R08 | P2 | Closed before `b3b202d2` | upstream IB-0 authority | A later IB-0 version or outcome-authority mutation could contradict IB-1I while its local gate still claimed zero authority. | Freeze the IB-0 version locally and independently refuse upstream version, outcome-authorized, or nonzero-look drift. Three upstream mutations are restored in `finally` and pass. |
| IB1I-R09 | P3 | Closed before push | pre-push ancestry wrapper | The first PowerShell wrapper evaluated the outputless `git merge-base --is-ancestor` command as a Boolean, printed `BASE_IS_ANCESTOR=no`, and ignored its successful exit code. Treating empty stdout as failure makes valid ancestry evidence false. | Discard the label and rerun by capturing `$LASTEXITCODE`: merge-base exit **0**, `ANCESTOR=True`, four commits, zero merges. No repository state changed. |

Two independent final audit passes report no remaining P0-P3 finding in the
bounded IB-1I diff. Implementation quality is **9/10** for the authorized
structural scope: every identified dangerous direction was corrected before
commit and the unresolved within-lane allocation is truthfully blocked rather
than invented.

### 36.4 Validation

Environment: **Python 3.13.14**, pytest **9.1.1**.

- Final IB-1I module: **120 passed in 2.41s**.
- Named Insider and project-boundary suite covering all current Insider test
  modules plus ML import, module hygiene, and both project-separation gates:
  **848 passed, 8 platform skips in 393.03s (6m33s)**.
- Complete repository suite on exact committed code tree
  `b3b202d2a8bf0ecc8a3613dcbfdb3690483ad767`:
  **3 failed, 7,093 passed, 15 skipped, 25 warnings in 2,939.96s (48m59s)**.
  The failures are exactly the previously recorded out-of-lane cases:
  `test_default_gain_review_is_fifty_percent_and_long_term_gated`,
  `test_every_lot_row_carries_the_tax_mechanism_fields`, and
  `test_report_carries_no_action_shaped_field` in
  `tests/test_sleeve_report.py`. No Insider module imports that surface and no
  file on that surface changed.
- Whole-repository `compileall`, including `research/`, **exit 0**.
- Post-record active-document and Insider implementation-record gate:
  **70 passed in 12.40s**; the same gate reran after the evidence bullets were
  added and passed **70 in 2.17s**.
- Exact combined change inventory from Claude head `3f6c2676` contains eight
  paths, all under the permitted Insider code/test prefixes or this record;
  the out-of-lane path count is **0**.
- `git diff --check`: **exit 0** apart from expected working-copy line-ending
  notices. A narrow value-shaped secret scan over the complete combined diff
  found **0 matches**.
- Corrected ancestry gate: `git merge-base --is-ancestor 3f6c2676 HEAD`
  returned **exit 0**; the range contains **four commits and zero merges**.
- The semantic payload and every authority field are mutation-bound; invalid
  family size, `1/60` substitution, reallocation, look/cell creation, holdout
  access, stock-null rescue, IB-0 drift, float/type confusion, and each false
  authority direction refuse.

Only local source files and synthetic structural values were used. No filing,
real SEC package, provider/API, credential, licensed row, price, return,
outcome, QuantConnect upload/processing/job/backtest, broker, operator
database, scheduler, deployment, order, or UI was accessed. **Research looks:
0.** No result was observed and no alpha was spent.

### 36.5 Documented but not fixed because out of lane

The following findings are deliberately retained without a code change:

- `research/analyst_revisions_v2/qc_first_plan.py` still names a three-lane
  correction factor and `1/60` prospective alpha. That is an Analyst-lane
  correction, not Insider authority.
- `docs/Strategy Description/README.md` still calls Insider Buying and Short
  Interest "planning/baseline" and does not list the fourth Target-Price lane.
  It is a shared coordination document and remains frozen here.
- `IB0H-OOL01` and the three sleeve-clock failures above remain on their
  separately owned shared surface.
- Shared/pathname hardening `IB1H-R02`, fourfold immutable-I/O consolidation,
  and all retained platform `R-*` findings remain documented and untouched.

### 36.6 Residual gates and next review

IB-1 remains incomplete. Real package acquisition/full population, official
SEC/XSD compatibility, authenticated amendment linkage, complete amendment
coverage, PIT issuer/owner/security/share-class identity, canonical filtering,
amendment supersession, lot aggregation, the post-aggregation `$50,000` gate,
signal construction, outcomes, ETF topology, portfolio research, QC
implementation, deployment, and trading are not authorized or completed.

The limited IB-1I structural gate is complete, but a full confirmatory
preregistration is **owner-decision-blocked**. The owner has not selected one
of the 5/20/60-session horizons, divided `1/80` among multiple stock cells,
allocated any stock/ETF split, or reserved the slot for a later prospective/QC
look. Codex did not invent a cell ID, permanent look ID, or alpha split.

After the round's single push, Claude independently reviews every commit in
`3f6c2676291f4e162ddf0aadaf1738202b69efec..` the pushed head, including the
counter-review correction, counter-review record, IB-1I implementation, and
this final record. Codex then counter-reviews every resulting Claude commit
before any further Insider milestone.

## 37. Claude review - hard-link invariants and the IB-1I research gate (2026-09-02)

Reviewer: Claude, in the named lane worktree
`C:\git\customizedagent\trading_agent_insider` on
`codex/strategy-insider-buying`. No branch, worktree, fork, or handoff was
created, switched to, or used.

### 37.1 Synchronized state

The local checkout was **7 commits behind** the remote and its `HEAD`
(`8736b4a2`) preceded the review base, so `3f6c2676` was not yet reachable.
Local was confirmed a strict ancestor of the remote and the branch was
fast-forwarded in place - no branch switch, no rewrite, no second worktree.
After syncing: local `HEAD` = `origin/codex/strategy-insider-buying` =
**`b21baf7c6849a6ba7525caf917ecb2904cc1f501`**, worktree clean.

Range `3f6c2676..b21baf7c` verified as **5 commits, 0 merges, 8 lane-owned
paths, 1,541 insertions and 19 deletions**; nothing outside
`research/insider_buying`, `tests/test_insider_buying_*`, and this record.
Interpreter Python 3.14.6.

### 37.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `a615304d` Complete counter-review hard-link invariants | **Accepted.** | The P2 is genuinely closed and the phase sensitivity is real, both verified independently in 37.3. |
| `322350a3` Record IB-1H counter-review | **Accepted.** | Its findings against my prior review are correct; the hard-link defect it describes is reproduced below. |
| `b3b202d2` Add zero-authority Insider research gate | **Accepted after correction.** | The gate is rigorous and every substantive claim reproduces exactly. Corrected here: two cross-checks had no test sensitivity (IB1I-R01). No production change was required. |
| `cee97a8c` Record IB-1I implementation round | **Accepted after correction.** | Content is accurate; the section was placed out of order in the record (IBREC-01, corrected here). |
| `b21baf7c` Record final IB-1I verification | **Accepted after correction.** | Same placement defect; its recorded figures reproduce (37.6). |

### 37.3 The hard-link P2, independently reproduced

I did not accept the fix from its description. Against the current tree I
published real IB-1A and IB-1B snapshots and hard-linked each committed file in
turn:

| Snapshot | File hard-linked | Result |
|---|---|---|
| IB-1A | baseline, single link | loads |
| IB-1A | `snapshot.commit.json` | **refused** |
| IB-1A | `manifest.json` | refused |
| IB-1A | `archive.zip` | refused |
| IB-1A | link then removed again | loads, no sticky refusal |
| IB-1B | baseline, single link | loads |
| IB-1B | `snapshot.commit.json` | **refused** |
| IB-1B | `manifest.json` | refused |
| IB-1B | `rows.jsonl` | refused |
| IB-1B | `accessions.jsonl` | refused |

The two commit markers are the files the counter-review identified as
unprotected, and both now refuse. The link check is present at three phases -
pre-open `lstat`, post-open `fstat`, and post-read `fstat` plus `lstat` - and
**each phase is independently load-bearing**: removing the pre-open clause, the
post-open clause, or the post-read clause (in either module) each fails the
suite, 4 of 4 mutants caught. That is the precise claim "phase-sensitive
regressions" makes, and it holds.

### 37.4 IB-1I research gate, independently reproduced

Every headline claim was recomputed rather than read:

- **Canonical semantic hash** recomputes to
  `f532eaf38fbdd6f3f00a4286a723ba1aa69c58f9862a596a840bd0e6d998c392`, matching
  the recorded value exactly.
- **Exact multiplicity arithmetic**: 4 lanes x `Fraction(1, 80)` equals
  `Fraction(1, 20)` exactly, and both fields are `Fraction`, not float. The
  module contains **no `float` token at all**.
- **Blueprint binding is real, not nominal**: the `INSIDER_BUYING_BLUEPRINT_SHA256`
  constant equals the SHA-256 of the actual PDF on disk, so the gate is bound to
  the governing authority rather than to a copied string.
- **Authority denial**: no unexpected true flag among the boolean fields;
  authorized and consumed outcome looks are exact integer zero; confirmatory
  allocations and permanent look ids are both empty; allocation state is
  owner-decision-required. Eight attempted escalations - outcome access,
  trading authority, holdout access, slot transfer, QC backtest, capital, and
  either look counter set to 1 - were each refused.
- The 5/20/60 horizons are pinned and cross-checked against `CANONICAL_SPEC`,
  and the gate refuses if the IB-0 contract version or its zero outcome
  authority drifts.

Mutation: twelve dangerous-direction mutants over the gate's invariants, **8
caught**. The four survivors were each traced rather than assumed, and two are
structurally masked rather than uncovered:

- the single-member `InsiderBuyingSlotDisposition` enum makes "is not EXPIRES"
  unreachable - any valid enum value is EXPIRES; and
- the `Fraction` type check is redundant **for these particular values only**,
  because 1/20 and 1/80 are non-dyadic so no float can equal them
  (`Fraction(1,20) == 0.05` is `False`). It would become load-bearing for a
  dyadic ceiling such as 1/4, where `Fraction(1,4) == 0.25` is `True`, so the
  guard is correct belt-and-braces rather than dead code.

The remaining two survivors are a genuine gap and are corrected below.

### 37.5 P0-P3 ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1I-R01 | P3 | **Closed - fixed in this review** | `b3b202d2` | `research/insider_buying/preregistration.py` `__post_init__` | Two cross-checks had no test sensitivity: the equation requiring four lane maxima to multiply to the shared FWER, and the ordering requiring the research cutoff to precede the final holdout. Each could be deleted with the whole 120-case module green. They are the only guards against an inconsistently edited module constant, and the first is the arithmetic that makes the entire multiplicity contract correct - a drifted lane ceiling would silently widen the permanent alpha budget. | Both mutants survived the twelve-mutant sweep. Every instance field is pinned to its own constant, so the cross-checks are unreachable from instance tampering alone and no existing test patches a constant. | The owner's directive names the exact 1/20 and 1/80 fractions as the contract; a guard protecting that arithmetic that no test exercises can be removed by a later refactor without any signal. | Added `test_lane_maxima_must_still_multiply_to_the_shared_fwer` and `test_research_cutoff_must_still_precede_the_final_holdout`, each patching the module constant and supplying the matching field so the per-field checks pass and the cross-check is reached. No production code changed. | Both pass on unmodified code (module 120 to 122); both previously surviving mutants are now **caught, 2 of 2**; module restored byte-identical to `HEAD` after the sweep. |
| IBREC-01 | P3 | **Closed - fixed in this review** | `cee97a8c`, `b21baf7c` | this record | Sections **36 and 35 were placed between sections 11 and 12**, out of both numerical and chronological order and with 36 preceding 35, while every other section runs 1 to 34 in sequence. This record is the branch-local handoff, so a reader following it chronologically met the newest IB-1I milestone in the middle of IB-0-era history. | `grep -n "^## "` returned the ordering 11, **36, 35**, 12, 13 ... 34. | The same class of defect the counter-review has previously raised against my own record edits: a handoff that renders or reads in the wrong order misdirects the next agent. | Moved both sections to follow section 34, restoring 35 then 36, without altering a single byte of their text. | The moved blocks were compared byte-for-byte before and after the move and are identical; section order is now 1 through 37 with no repeats; the lane-record and active-document gates pass. |
| IBREC-02 | P3 | **Open - reported, historical row deliberately not edited** | `4a9ca17f` | this record, session ledger row dated 2026-09-01 | My IB-1G review round committed and pushed a ledger row still containing the literal placeholder `record gate **pending**`. A durable handoff row therefore advertises a validation figure that was never supplied, and neither that row nor section 32 records the value anywhere, so it cannot be reconstructed from the record. | `grep -n "record gate \*\*pending\*\*"` returns two hits: the 2026-09-01 row already present in `HEAD`, and this round's row before it was filled. Section 32's validation list contains no corresponding figure. | The defect is mine and is the same family as the wrapped-ledger-row and missing-blank-line defects: my splice writes a placeholder and a later step fills it, and that round's fill step targeted a different string (`record-sensitive gate`) so the placeholder survived into the commit. | **Not corrected in place.** The ledger is append-only and the owner's standing instruction is to add a superseding correction rather than rewrite historical evidence, so the 2026-09-01 row is left exactly as committed and this entry supersedes it: that round's record-sensitive gate result is **not durably captured** and should not be inferred. This round's fill step was verified to leave the historical hit untouched. | Placeholder count before fill 2, after fill 1, and the remaining hit is the untouched 2026-09-01 row. |
| IB1I-N01 | P3 | Closed - not a defect, retained | `b3b202d2` | slot-disposition enum and `Fraction` type check | Two mutation survivors that are **not** coverage gaps, retained so a later reviewer does not re-raise them. | `InsiderBuyingSlotDisposition` has exactly one member; `Fraction(1,20) == 0.05` and `Fraction(1,80) == 0.0125` are both `False` while `Fraction(1,4) == 0.25` is `True`. | No fix warranted; recording the reasoning prevents a future false alarm and explains why the type check should be kept. | None. | Direct evaluation of both, reproduced above. |

### 37.6 Validation

- IB-1I module: **122 passed** (the recorded 120 plus this review's two).
- Exact named suite - all seven `tests/test_insider_buying_*.py` modules plus
  `test_ml_import_boundary`, `test_module_hygiene`,
  `test_project_separation_entrypoints`, `test_project_separation_boundary`,
  and `test_active_document_consistency`: **920 passed, 8 skipped in 255.35s**.
  This is a wider set than the recorded 848-case run, which is why the count
  differs; the file list is named here so the figure is reproducible.
- Mutation totals this round: hard-link phases **4 of 4 caught**; IB-1I gate
  **8 of 12 caught, 2 structurally masked, 2 fixed and then caught**.
- Adversarial probes: ten hard-link cases across both snapshot boundaries, plus
  hash, arithmetic, blueprint-binding, authority-enumeration and eight
  escalation-refusal checks on the gate.
- **Whole-repository `compileall`**: exit 0.
- Complete repository suite: recorded in the appended ledger row, including
  every failure.
- **No test was removed or weakened.** No test definition is deleted anywhere
  in the range; the 19 deletions are 9 record lines, 1 export line, and 8 lines
  replaced inside the two `_read_regular_bytes` conditionals. This review's own
  change is purely additive.

### 37.7 Quality rating

**9 / 10**, held rather than raised.

The engineering is strong and the two milestones do what they claim. The
hard-link correction is complete across both boundaries and every phase of it
is load-bearing. The IB-1I gate is the most carefully constructed contract in
the lane: exact-rational arithmetic with no float anywhere, a real hash binding
to the governing PDF, cross-module drift checks against the IB-0 spec, and
twenty-one authority flags that cannot be raised.

It is not raised to 10 because the same defect shape has now recurred for a
third consecutive milestone: a correct guard with no test behind it - IB1G-R06,
then IB1I-R01. Both times the guard protected the milestone's central
invariant, and both times a whole-module green run said nothing about it. The
lane would benefit from making "every new refusal branch gets a test that fails
without it" an implementation checklist item rather than something the review
catches afterwards. The record-ordering defect is minor by itself but is the
fourth structural record defect across recent rounds, which points the same way.

### 37.8 Authority, residual gates, and access accounting

Every authority gate remains closed and every prior open finding is carried
forward: IB0H-R06, IB1G-R04, IB1G-R05, IB1E-R05, IB1E-R07, IB1D-R09,
IB1D-R10, IB1D-CR11, IB1C-R16, IB1B-R11, IB01-R05, R-23, IBFL-01, IBFL-02 and
IBFL-03 are unchanged. The framings the counter-review asked me to verify hold:
IB-1I proves an internally consistent sealed contract, not authenticated
historical origin, and the XML title grammar deliberately stays narrower than
the now-corrected canonical contract until IB-2 supplies point-in-time
security-class mapping.

IB-1 remains incomplete. Package acquisition and full historical population,
official-profile validation, authenticated amendment provenance, canonical
filtering, aggregation, the post-aggregation $50,000 gate, signals, outcomes,
ETF construction, and QuantConnect implementation are neither complete nor
authorized.

Out of lane and unchanged: the `tests/test_sleeve_report.py` fixed-clock
failures, still not fixed here, and still drifting as recorded in section 32.

External access this round: **none**. No SEC or provider data, credential,
licensed row, real package, outcome, QuantConnect action, broker action,
operator database, scheduler, deployment, or order. All inputs were synthetic
or local. **Research looks: 0**, and the gate's authorized and consumed look
counters both remain exact integer zero.

### 37.9 Handoff

Outcome: all five commits accepted, two with corrections applied here. One
bounded code-adjacent correction was authorized and made - two regression tests
- plus one record-ordering correction. Next authorized step: Codex
counter-reviews this review commit. No milestone was started and none is
authorized.

## 38. Codex counter-review of Claude's IB-1I review (2026-09-03)

Reviewer: Codex, in the dedicated lane worktree
`C:\git\customizedAgent\trading_agent_insider` on the existing
`codex/strategy-insider-buying` branch. No branch or worktree was created or
switched. The worktree was clean at `b21baf7c`; the live remote resolved to
`2c392cd30ce4979d4f36d0b6e1b8b7323f8bc6ef`, and the lane was fast-forwarded
only to that exact object.

### 38.1 Exact review scope and disposition

The complete ordered Claude range after the prior Codex head is one commit and
zero merges:

| Commit | Disposition | Basis |
|---|---|---|
| `2c392cd3` Pin the IB-1I constant-drift guards and record the review | **Accepted after documentation correction.** | The two tests are valid and load-bearing, the section relocation is byte-preserving, and the material IB-1I/hard-link claims reproduce. Five P3 defects in the review record are superseded below; no product-code correction is required. |

The five underlying Codex commits reviewed by Claude require this superseding
commit-by-commit disposition: `a615304d` is **accepted**; `322350a3`,
`b3b202d2`, `cee97a8c`, and `b21baf7c` are each **accepted after correction**.
This is four accepted-after-correction dispositions, not the two stated in
section 37.9 or the three implied by section 37.2.

### 38.2 Independent reproduction

- The two added tests pass individually and in the complete IB-1I module. Each
  patches the governing module constant and supplies the matching instance
  value, so the earlier exact-field guard passes and the intended cross-field
  invariant is actually reached. Reversible in-memory suppression of the
  four-lane-alpha equation and cutoff/holdout-order guard makes its respective
  test fail; **2 of 2 mutants caught**. `MonkeyPatch.undo()` restored both
  constants.
- The complete IB-1I module passes **122 tests**. The semantic hash recomputes
  to `f532eaf38fbdd6f3f00a4286a723ba1aa69c58f9862a596a840bd0e6d998c392`;
  four times `Fraction(1, 80)` equals `Fraction(1, 20)` exactly; authorized and
  consumed look counts are integer zero; and both allocation inventories are
  empty.
- The local blueprint SHA-256 recomputes to
  `f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c`,
  matching the gate constant and the governing-source identity in this record.
- The current hard-link-focused IB-1A/IB-1B slice passes all **15 selected
  cases**. The previously reviewed ten real-link outcomes and four
  phase-suppression mutations remain consistent with the current code; no
  hard-link logic changed in `2c392cd3`.
- Range `3f6c2676..b21baf7c` independently reproduces as five commits, zero
  merges, eight paths, 1,541 insertions, and 19 deletions. Sections 35 and 36
  compare text-identical before and after relocation at 8,683 and 12,270
  characters respectively; the current top-level section sequence is exactly
  1 through 38.
- Commit `2c392cd3` changes only this lane record and
  `tests/test_insider_buying_preregistration.py`; it adds no production,
  provider, outcome, QC, broker, scheduler, or execution surface and removes
  no test definition.

### 38.3 P0-P3 counter-review ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| IB1I-CCR01 | P3 | **Closed - corrected in this record** | `2c392cd3` | section 37.2, section 37.5 `IBREC-01`, and section 37.9 | Claude marked `322350a3` accepted and attributed the misplaced-section defect only to `cee97a8c`/`b21baf7c`, so its per-commit disposition and summary count disagree with the history. | At `3f6c2676` headings are 1..34; `322350a3` first changes them to 1..11,35,12..34; `cee97a8c` changes them to 1..11,36,35,12..34. | The mandatory review protocol requires an exact disposition for every commit; an incorrect attribution makes the durable counter-review chain ambiguous. | Historical text is retained. Section 38.1 supersedes it with one accepted and four accepted-after-correction dispositions. | Header sequences were computed at every commit from `3f6c2676` through `2c392cd3`; final order is contiguous. |
| IB1I-CCR02 | P3 | **Closed - fixed in current status** | `2c392cd3` | record status | The active status still said `b3b202d2` awaited Claude review after section 37 and the session ledger had already recorded that review. | The former status line 9 contradicted section 37 and the 2026-09-02 Claude-review ledger row. | This file is the branch-local handoff; stale current-state instructions can send the next agent backward in the workflow. | Updated the mutable top status to the completed review and current counter-review state without rewriting a historical ledger row. | Current status names `2c392cd3`, section 38, zero authority, and the owner-decision blocker. |
| IB1I-CCR03 / IBREC-02 | P3 | **Closed - append-only correction recorded here** | `2c392cd3` | section 37.5 `IBREC-02` and the 2026-09-01 Claude-review ledger row | The underlying placeholder defect is real, but section 37 attributes it to `4a9ca17f` and says the result cannot be reconstructed. The row was actually introduced by `2ef057d6`, whose immutable commit message records `Record gate 70 passed`; exact command and duration remain absent. | `git blame` assigns the row to `2ef057d6`; the placeholder does not exist at `4a9ca17f` or `e2eca996`; `git show -s --format=%B 2ef057d6` contains the 70-pass result. | Provenance and evidence-availability claims must distinguish an omitted lane-row value from information preserved elsewhere in immutable history. | The historical row remains untouched. This entry supersedes the source as `2ef057d6` and records **70 passed**, while explicitly not inventing an unrecorded command or duration. | Exactly one historical placeholder remains; its corrected value and evidence source are now durable in this append-only section. |
| IB1I-CCR04 | P3 | **Closed - corrected in this record** | `2c392cd3` | section 37.6 deletion inventory | The claimed 19-deletion explanation enumerates only 18 and mislabels the `research/insider_buying/__init__.py` deletion as an export line. | `git diff --numstat 3f6c2676..b21baf7c` gives 9 record, 1 package file, 4+4 reader, and 1 parsed-snapshot-test deletions. Diff inspection identifies one package-docstring replacement, eight reader-conditional replacements, and one test-parametrization replacement. | A no-test-weakening claim should reconcile exactly to the cited diff rather than leave an unexplained deletion. | Superseding breakdown: 9 record + 1 package-docstring + 8 reader-condition + 1 test-parametrization lines = 19. | The total now agrees with `--numstat`; no test definition was deleted or weakened. |
| IB1I-CCR05 | P3 | **Closed - corrected in this record** | `2c392cd3` | section 37.6 named-suite description | The review calls 920 passed plus 8 skipped an exact 12-file suite containing “all seven” `test_insider_buying_*.py` modules, but nine files match that pattern at the reviewed head. With the five named boundary/document files, the actual command surface is 14 files. | Current and reviewed trees contain nine matching Insider modules; collection over those nine plus the five named files yields **14 files and 928 tests**, consistent with 920 passed plus 8 skipped. | Exact validation evidence must name a command surface another reviewer can reproduce. | This section records the actual inventory as nine Insider modules plus five boundary/document modules. | Collection is 928 tests; Claude's 920+8 result totals the same 928. |

No P0, P1, or P2 defect was found in `2c392cd3`. No open lane-specific defect
remains from this counter-review. The known `tests/test_sleeve_report.py`
fixed-clock failures remain outside the Insider lane and were documented but
not fixed.

### 38.4 Validation and access accounting

Codex used Python **3.13.14** and pytest **9.1.1**; Claude's reviewed host used
Python 3.14.6. Focused IB-1I: **122 passed in 1.83s**. The two new exact nodes
pass and catch **2 of 2** reversible guard-suppression mutations. The
hard-link-focused selection passes **15 cases**. The 14-file named-suite
collection is **928 tests**. The post-correction implementation-record,
active-document, and IB-1I gate first passed **192 tests in 23.38s**; after
that result was written, its exact-tree rerun passed **192 tests in 3.11s**.

Complete repository suite on exact Claude head `2c392cd3`: **3 failed, 7,095
passed, 15 skipped, 25 warnings in 3,129.90s (52m09s)**. The three failures are
exactly the unchanged, out-of-lane sleeve-clock cases:
`test_default_gain_review_is_fifty_percent_and_long_term_gated`,
`test_every_lot_row_carries_the_tax_mechanism_fields`, and
`test_report_carries_no_action_shaped_field`. The one-pass/one-skip difference
from Claude's 3/7,096/14 result is consistent with the different
interpreter/host; both runs collect 7,113 cases. No file in `2c392cd3` touches
that surface.

Only tracked local code, synthetic fixtures, and the local governing PDF bytes
were read. No filing, real SEC package, network/provider endpoint, credential,
licensed row, outcome, QuantConnect action, broker, operator database,
scheduler, deployment, order, or UI was accessed. **Research looks: 0.**

### 38.5 Authority and handoff

No next implementation milestone is currently authorized. The latest
authoritative handoff permits this counter-review only; no `IB-1J` is defined.
Full confirmatory preregistration remains owner-decision-blocked until the
owner selects one primary 5/20/60-session horizon, divides the permanent
`1/80` ceiling among any stock confirmatory cells, decides any stock/ETF split,
and decides whether to reserve allocation for a later prospective/QC look.
Real-package acquisition, official-profile validation, authenticated amendment
provenance, canonical aggregation, outcomes, ETF construction, and QC work are
also not authorized by inference.

Accordingly, this counter-review record is committed locally but the loop stops
before a new milestone and before its single combined push. The owner must
supply the missing bounded decision before implementation resumes. All
provider, outcome, QC, operational, deployment, capital, and trading authority
remains exact zero.

## 39. Codex counter-review and IB-2A observed identity inventory (2026-09-03)

### 39.1 Scope and commit disposition

The owner's later instruction to implement the next milestone superseded the
section 38.5 stop only for bounded, offline **IB-2A observed identity
inventory** work. Codex stayed in
`C:\git\customizedAgent\trading_agent_insider` on
`codex/strategy-insider-buying` without switching branches. Claude commit
`2c392cd3` is accepted after the append-only record corrections in `726c4dcf`;
the implementation snapshot is `5c74bdee`. No project-wide coordination file
was changed.

One additional P3 record finding, **IB1I-CCR06**, is closed here without code
change: section 37.8's claimed exhaustive carry-forward was stale. `IBFL-02`
had already closed when the contract adopted 30 **trading** days; `IBFL-03`'s
claim that all of blueprint step 19.4.1 was unstarted was superseded by IB-1G
and IB-1H, although real acquisition, full population, and canonical filtering
remain unstarted; and the list omitted active `IB0H-R07`, `IB1H-R02`,
`IB1H-R03`, `IB1D-CR07A`, and out-of-lane `IB0H-OOL01`. Historical text is
retained and this paragraph is the superseding disposition.

### 39.2 Implemented contract

`form4_observed_identity_inventory.py` exposes factory-created frozen filing,
reporting-owner, and transaction inventories from retained IB-1E evidence and
the public IB-1G rebuild. It independently reparses evidence, fingerprints
inputs before and after use, binds report rows and payload hashes back to the
retained transactions, validates accession and amendment lineage, and emits
named single-owner, missing-owner, multiple-owner, and incomplete-owner-set
outcomes. Joint owners are retained as owners of one filing and are never
cross-multiplied into synthetic transaction rows. All point-in-time resolution,
canonical-selection, aggregation, outcome, QC, deployment, and trading flags
remain false; authorized and consumed research looks remain zero.

This milestone deliberately does **not** perform identity resolution, ticker or
share-class mapping, deduplication, amendment replacement, canonical filtering,
lot aggregation, or the `$50,000` gate. It therefore does not satisfy full IB-2
or blueprint section 19.4 step 5.

### 39.3 P0-P3 implementation review ledger

| ID | Priority | Status | Finding and correction |
|---|---|---|---|
| IB2A-R01 | P2 | **Closed in `5c74bdee`** | Evidence reads had a validation/use TOCTOU and incomplete observation fingerprint. Exact before/after fingerprints now bind all retained XML sources, supplied links, lineages, and timestamp precision. |
| IB2A-R02 | P2 | **Closed in `5c74bdee`** | A forged public report could spoof upstream identity or row semantics. The builder now performs an independent upstream reparse and binds exact report state, source rows, payload hashes, and factory identity. |
| IB2A-R03 | P2 | **Closed in `5c74bdee`** | Forged candidates could bypass amendment or non-single-owner quarantine. Candidate disposition is recomputed from retained evidence and named fail-closed owner-set outcomes. |
| IB2A-R04 | P2 | **Closed in `5c74bdee`** | Amendment/accession and row-cardinality invariants were incomplete. Targets must be unique earlier originals for the same issuer, lineage times must be unique, and transaction indexes are contiguous. |
| IB2A-R05 | P2 | **Closed in `5c74bdee`** | Callback-bearing or malformed structures could exploit projection, serializers, metaclasses, cycles, depth, or unbounded prehash work. Exact type/state allowlists and shared byte/text/node/depth/count budgets now fail closed. |
| IB2A-R06 | P3 | **Closed in `5c74bdee`** | Public errors, exact integer/cardinality rules, zero-owner completeness, constructor gate order, exports, and mutation-test sensitivity were tightened. |

Three independent final reviews accepted the corrected implementation with no
remaining P0-P3 finding in scope. The known sleeve-clock failures are outside
this lane and remain documented as `IB0H-OOL01`; they were not changed.

### 39.4 Verification and authority accounting

Python **3.13.14**, pytest **9.1.1**. Focused IB-2A: **97 passed**. Targeted
adversarial artifact/callback mutations: **22 passed, 75 deselected**. Complete
ten-file Insider suite: **894 passed, 8 skipped in 319.19s**. The implementation
staged diff passed `git diff --check`; its value-shaped secret scan found **0
matches**. No SEC/provider endpoint, credential, licensed row, real filing,
outcome, QuantConnect action, broker, operator database, scheduler, deployment,
order, or UI was accessed. **Research looks: 0.**

Implementation quality is **9/10**: the boundary is strongly fail-closed and
mutation-sensitive, while real authority and full IB-2 resolution remain
intentionally absent and the offline implementation still couples to a private
upstream reparse boundary.

### 39.5 Copyable Claude review handoff

> Review every commit in `2c392cd3..HEAD` on
> `codex/strategy-insider-buying`, specifically Codex counter-review commit
> `726c4dcf`, IB-2A implementation commit `5c74bdee`, and the following record
> commit. Reproduce all material claims and mutation-test the dangerous
> directions: evidence/report TOCTOU, forged factory identity, report semantic
> or payload-hash drift, owner-set escalation, amendment-lineage confusion,
> joint-owner fan-out, cycle/depth/resource bypass, and any authority becoming
> true. Confirm observed-only filing/owner/transaction normalization and exact
> zero looks/authority. Document findings in this record; fix only
> Insider-lane defects. Do not access SEC/provider data, credentials, licensed
> rows, outcomes, QuantConnect, broker, operator database, scheduler,
> deployment, capital, or trading authority.

## 40. Claude review - IB-2A observed identity inventory (2026-09-03)

Reviewer: Claude, in the lane worktree
`C:\git\customizedAgent\trading_agent_insider` on `codex/strategy-insider-buying`.
No branch, worktree, fork, or handoff was created or switched to. Range
reviewed in order: `726c4dcf` (counter-review record), `5c74bdee` (IB-2A
implementation), `7c9e6f53` (record). `2c392cd3` confirmed an ancestor of
`7c9e6f53`; no history rewritten. The owner noted that Codex did not run the
complete repository suite this round; this review ran it independently.

### 40.1 Isolation and scope

The three commits touch only lane-owned paths: `research/insider_buying/`,
`tests/test_insider_buying*`, and this record. Excluding those prefixes from
the changed-path list leaves an empty set. `git worktree list` shows this lane
in exactly one worktree; three `prunable` detached lane-sync worktrees from
2026-08-26 remain on the host and are out of lane, recorded only.

Under the owner's 2026-08-29 scope instruction, corrections here are
lane-specific test additions only. No production module was changed.

### 40.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `726c4dcf` counter-review of the IB-1I review | **Accepted after documentation correction.** | Documentation only. IB1I-CCR06 verified: `contracts.py` carries `lookback_trading_days=30`, so `IBFL-02` did close with the contract; `IB0H-R07`, `IB1H-R02`, `IB1H-R03`, and `IB0H-OOL01` are confirmed still open. One precision defect recorded as IB2A-CR03. |
| `5c74bdee` IB-2A observed identity inventory | **Accepted after correction.** | Lane-owned only; focused module **97 passed** reproduces; no network, `float`, `subprocess`, `eval`, or `__import__` surface, pinned by an AST test. Four guards on the owner's named dangerous directions were untested and are pinned by additive tests (IB2A-CR01); no product-code defect found. |
| `7c9e6f53` counter-review and implementation record | **Accepted after documentation correction.** | Two recorded validation figures are not reproducible as stated (IB2A-CR02), and the push carried no section-5 ledger row (IB2A-CR05). |

### 40.3 Material claims reproduced

- Focused IB-2A: **97 passed** at `7c9e6f53`, exactly as recorded.
- Complete ten-file Insider suite: Codex recorded **894 passed, 8 skipped**.
  This review ran the ten files plus `test_ml_import_boundary.py` (11) and
  `test_module_hygiene.py` (8): **913 passed, 8 skipped in 316.52s**, and
  913 - 11 - 8 = 894 exactly. The claim reproduces.
- Observed-only scope: a keyword sweep of the module for ticker, share-class,
  dedupe, aggregation, `$50,000`, resolution, ETF, QC, order, broker, or
  deployment surface matches only negation text and the pre-aggregation
  candidate enum. Confirmed: IB-2A emits observed filing, reporting-owner, and
  transaction inventories with named owner-set quarantine outcomes and performs
  none of the excluded work.
- Authority: the inventory identity carries **fourteen** Boolean authority
  fields and two look counters; construction refuses unless every Boolean
  `is False` and both counters `== 0`. Verified by reading the enforcement
  block and by the caught mutants below, not from the record.
- Joint owners: the joint-owner fixture yields two owner rows and exactly one
  transaction row, with the filing quarantined as a multiple-owner set. No
  cross-multiplication.

### 40.4 Mutation testing of the eight dangerous directions

Twenty targeted mutants, one neutralised guard each, focused file run after
each, module restored from a byte-exact in-memory copy in a `finally` block.
**13 caught, 7 survived, 0 invalid** on the pushed tree. Each survivor was
then classified rather than reported as a defect:

| Direction | Guard | Result on `7c9e6f53` | Classification |
|---|---|---|---|
| 1 TOCTOU | post-validation evidence re-fingerprint | caught | pinned |
| 1 TOCTOU | re-fingerprint immediately after reparse | survived | **untested; now pinned** |
| 1 TOCTOU | rebuilt-report re-hash inside validation | survived | mid-call defence, reachable only by hooking inside one function; untested, recorded |
| 2 forged factory | identity token, inventory token | caught, caught | pinned |
| 3 drift | transaction payload hash | caught | pinned |
| 3 drift | `disposition is not retained.disposition` | survived | **provably redundant**: disposition is bound to outcomes by the report row constructor, and IB-2A replays that constructor on every rebuilt row before this clause is reached |
| 4 escalation | candidate contradicts filing quarantine; multi-owner promoted to single | caught, caught | pinned |
| 5 lineage | amendment may target another issuer | caught | pinned |
| 5 lineage | amendment accepted before its original | survived | **untested; now pinned** (only the equal-time case was exercised) |
| 6 fan-out | duplicate owner observation ids; owner index and id binding | survived, survived | a **combined mutant neutralising all three owner-uniqueness clauses also survived**, so no test reached any of them; **now pinned** at the filing-level clause, the first line construction reaches |
| 7 structural | cycle, depth, dict-subclass instance state | caught x3 | pinned |
| 7 structural | projection node bound | survived | **provably unreachable**: preflight caps of 256 filings, 4,096 owners, and 100,000 transactions cannot produce 4,000,000 projection nodes |
| 8 authority | any authority flag; authorized looks; consumed looks | caught x3 | pinned |

Direction 3 needed one more step. The forged-report path first refused with
`rebuilt upstream report row is invalid`, not with the retained-evidence
comparison, because IB-2A replays `Form4ProvisionalDispositionRow.__post_init__`
on each rebuilt row. That replay is the real first line for semantic drift and
had no test either; removing it and running the new test yields a catch.

### 40.5 Findings

| ID | Sev | Status | Issue |
|---|---|---|---|
| IB2A-CR01 | P3 | **FIXED in `1b836ff6`** | Four guards on the owner's named dangerous directions could be deleted with the suite green: the re-fingerprint immediately after reparse (direction 1), the constructor replay that binds disposition to outcomes (direction 3), the strict-order half of the amendment-to-original binding (direction 5), and all three owner-uniqueness clauses together (direction 6). Five additive tests now pin them: `test_evidence_mutation_during_independent_revalidation_is_refused`, `test_forged_report_disposition_alone_cannot_drift_from_captured_evidence`, a `before_original` case on `test_self_consistent_amendment_requires_its_observed_original`, `test_filing_cannot_list_one_owner_observation_twice`, and, in the IB-1H file, `test_report_row_constructor_binds_disposition_to_outcomes` for the constructor itself. Every one was mutation-verified: the corresponding mutant is caught by that test and the test passes on the unmodified tree. No production module changed. |
| IB2A-CR02 | P3 | OPEN - record precision | Two validation figures in the handoff do not reproduce as stated. "Record/boundary gate: 289 passed" appears **nowhere in this record**; the record-sensitive gate over `test_insider_buying_implementation_record.py`, `test_active_document_consistency.py`, `test_ml_import_boundary.py`, `test_module_hygiene.py`, and both project-separation suites yields **124 passed**. "22 passed, 75 deselected" names no `-k` selector, so the exact subset cannot be rerun; 22 + 75 = 97 shows it is a subset of the focused file, nothing more. |
| IB2A-CR03 | P3 | OPEN - record precision | IB1I-CCR06 carries forward `IB1D-CR07A` as an active finding, but that identifier exists only in prose from an earlier disambiguation; **no ledger row** `| IB1D-CR07A |` exists, so it cannot be looked up or dispositioned as a stable ID. |
| IB2A-CR05 | P3 | OPEN - record precision | The parallel workflow requires one section-5 ledger row before every push. The section-5 ledger ends with the 2026-09-02 Claude review row for `3f6c2676`; sections 38 and 39, covering the 2026-09-03 push of `726c4dcf`, `5c74bdee`, and `7c9e6f53`, added **no ledger row**, so the branch-local handoff ledger is silent on that push and its validation and look accounting live only in section 39.4. Recorded, not rewritten; this review's own row is appended in order. |
| IB2A-CR04 | P3 | OPEN - stated, not fixed | The rebuilt-report re-hash inside `_validate_upstream_report` (the third direction-1 guard) is reachable only by mutating the frozen report between its rebuild and the comparison within one call. It is mid-call defence in depth; it remains untested and is recorded rather than given a hook-dependent test. |

### 40.6 Process notes, recorded plainly

- Two tests as first written **failed on the unmodified module**: `accepted_at_utc`
  is canonical ISO text, not a `datetime`, and the disposition forgery was
  refused by the constructor replay before the clause I had targeted. Their
  early appearance in "caught" lists was therefore noise and was discarded;
  both were rewritten and re-verified before anything was recorded.
- One tool call that the harness reported as rejected had in fact written the
  test file before the interrupt. The file was read directly to establish its
  true state rather than trusting the reported status; the later anchor
  failure on the same edit is explained by that, not by a second change.
- `_reparse_profile_bound_evidence` is an import alias of
  `form4_multi_period_amendment_evidence._reparse_evidence`; the TOCTOU
  regression patches the alias on the inventory module, which the call site
  resolves at call time. Confirmed by the caught mutant.

### 40.7 Validation

- Focused IB-2A after additions: **101 passed**.
- IB-1H file after the constructor pin: **46 passed, 1 skipped in 17.90s**.
- Complete ten-file Insider suite plus `test_ml_import_boundary.py` and
  `test_module_hygiene.py`: **918 passed, 8 skipped in 278.70s (0:04:38)**.
- Record-sensitive gate (six files): **124 passed** before the record edit;
  rerun after it, recorded in the section 5 row.
- Mutants: twenty on the pushed tree (13/7/0); the five pinning tests then
  re-verified against their exact mutants, including the triple fan-out
  mutant and the constructor-replay mutant, all **caught**; every module
  restored byte-identical and confirmed with `git diff --quiet`.
- Complete repository suite on the code tree: **3 failed, 7,197 passed, 15 skipped, 25 warnings in 4,272.30s (1:11:12)**. The three
  `tests/test_sleeve_report.py` failures are the out-of-lane fixed-test-clock
  drift already recorded as `IB0H-OOL01`; documented, not fixed.
- `git diff --check` clean. Test correction committed as `1b836ff6`; changed
  paths are two lane test files and this record.

No SEC, EDGAR, vendor, QuantConnect, credential, licensed row, outcome,
broker, operator-database, scheduler, deployment, capital, or trading access.
**Research looks: 0.** All fourteen authority Booleans remain literal `False`;
both look counters remain exactly `0`.

### 40.8 Residual gates and next authorized step

IB-2A is observed-only and stays that way: no identity resolution, ticker or
share-class mapping, deduplication, canonical filtering, aggregation, or
`$50,000` gate was added or authorized. IB-1 remains incomplete and blueprint
19.4 step 1 unstarted. Next: Codex counter-reviews these Claude commits, then
may continue the bounded ladder.

## 41. Owner-directed cross-lane bug-fix integration applied (2026-09-04)

The owner directed the dedicated Review lane session to fix, on the
`main`-derived branch `Feature-bug-fix-integration-2026-09-04`, the shared
trading-application / test-infrastructure / repository-tooling issues that this
record and the sibling lane records had documented but, under the lane scope
rule, deliberately not fixed, and to apply the identical commits to every lane
branch so no lane carries a divergent copy of a shared file. This lane received
them as cherry-picks; no lane-owned file changed.

| Integration-branch commit | Cherry-pick on this lane | Content |
|---|---|---|
| `7f99f303d0b6f5a2a65aa5b5b49f9c52256716d8` | `b8f49eeabf285627ef195adece04769dbb264223` | sleeve-report clock seam, runtime-stop leak redirect + conftest guard, shared EOL attributes, Briefing smoke isolation, characterization test rename |
| `3114a1530f0afa400eb200e79ff218c174657e69` | `77055da4a2f4741af8d3a80e691090dbe63fa412` | notification cycle evaluates at its own clock; guard decoder bound at import |
| docs commit | `e08f0c17a6694f8e4764d3edd992a484cbefeb3c` | `docs/Archive/Review/BUG_FIX_INTEGRATION_2026-09-04.md` (fix table, full disposition ledger, owner decisions) plus the four-lane README, the direction status paragraph, and the workflow exception paragraph |
| `6ef66eed77f9b24ea3df8aa538f42de0c871c824` (F-8, owner direction, same day) | `fb25d915de21b4c20873ec0dca1bb2e811137c05` | `tests/target_price_revisions/test_preregistration.py::test_self_declared_review_and_registry_substitution_refuse` made deterministic across harness layouts (Analyst `ARV2-UNRELATED-001` / Short-interest `SI-OOL-003`); the loader is unchanged |
| integration record update | `cf591b73e95ff6720869f616cd46083b359210a0` | F-8 recorded in `docs/Archive/Review/BUG_FIX_INTEGRATION_2026-09-04.md` (fix table, ledger rows, validation) |
| `f4764671b9f3ee0de50ab36a7cf61854bca72c4f` (2026-09-05 post-integration review of `main`, PIR-002/003/004/005) | `62beb3fad8b44726a4eb8dd07511f898ccc33d45` | `evaluate_sleeves` refuses a naive `now` with `SleeveReportError` instead of degrading every growth position; the conftest runtime-stop leak guard attributes an incident to the session only when it is under the base temp AND its `activated_at` is not before session start; `tests/test_shared_research_eol_attributes.py` also asserts working-copy bytes match the index blob and names the heal `rm <path> && git checkout -- <path>`. Review record `docs/Archive/Review/REVIEW_2026-09-05_POST_INTEGRATION_MAIN.md` lives on `main` (its handoff/record commits are not cherry-picked: the shared handoff is frozen on lanes). |

Items of this record closed by the application: IB0H-OOL01 (F-1); the R-09/R-18/R-20/R-22 test-origin leak mechanism (F-2/F-3 — the existing debris file on the host is an owner decision, integration record section 6); R-17 (F-7); item #27's stale-CRLF class for shared files (F-4); item #30 README (F-6). R-11 was already closed on `main` by EXE-001. Every other
out-of-lane item this record carries was examined; its disposition and reason
are in the integration record's section 5, and the items needing an owner
decision are listed in its section 6.

This application is not acceptance of any lane milestone and grants no
provider, outcome, look, QuantConnect, broker, operator-database, deployment,
paper, live, or trading authority. The lane's same-branch review loop resumes
from this head. Validation on this lane's resulting head: focused set (sleeve report/notifications, leak guard, EOL attributes, crash-test redirect, Briefing smoke, reservation characterizations, active-document consistency): 174 passed in 22.79s.

**Follow-up, same day (F-8).** After the integration record showed that
`ARV2-UNRELATED-001` / `SI-OOL-003` were not a stale message but a
harness-layout dependency — `_repository_root` walks up from the spec, so a
spec written straight into pytest's `tmp_path` reaches the "not inside a Git
repository" refusal under an external base temp and the "committed and clean"
refusal under a repository-local `--basetemp` — the owner directed that the
Target-price test be fixed as well. The test now asserts the exact refusal its
own location must reach (`_bare_tmp_path_refusal` mirrors the loader's
discovery order) and adds two layout-independent assertions that exercise the
other branches explicitly (a self-declared review in a foreign repository →
`share one repository`; an uncommitted one inside the anchored repository →
`committed and clean`). `research/target_price_revisions/preregistration.py`
is unchanged; this is a test-determinism correction and grants no authority. Validation on this head: Target-price preregistration test file plus active-document consistency: 152 passed, 2 skipped in 26.03s.

## 42. Codex counter-review through the shared-integration alignment (2026-09-06)

### 42.1 Exact scope and dispositions

Codex fast-forwarded the clean existing worktree to exact remote head
`11d894b6f1853c55984442b9e8b1aa097774919c` without switching branches. The
range `7c9e6f53..11d894b6` is linear: twelve commits, zero merges.

| Commit | Disposition | Counter-review basis |
|---|---|---|
| `1b836ff6` | **Accepted.** | Five additive lane tests pin four previously surviving IB-2A guard directions; no production code changed. |
| `c7b9f2f2` | **Accepted after record correction.** | Claude's product/test conclusion is sound; `IB2A-CR02` is only partly correct and `IB2A-CR03` is a false alarm, superseded below. |
| `b8f49eea` | **Accepted after later correction.** | Owner-authorized shared integration; `77055da4` and `62beb3fa` close its JSON-decoder, clock, and stale-session gaps. Patch-identical to source `7f99f303`. |
| `77055da4` | **Accepted after later correction.** | Shared notification-clock and bound-decoder correction; its naive-clock gap is closed by `62beb3fa`. Patch-identical to source `3114a153`. |
| `e08f0c17` | **Accepted.** | Owner-authorized shared integration record and coordination amendments; no authority change. |
| `c96799ff` | **Accepted after record correction.** | Correct section 41 pointer, but the lane status and section-5 push history remained incomplete. |
| `fb25d915` | **Accepted, out of lane.** | Target-price test-only harness-layout correction; its loader is unchanged. Patch-identical to source `6ef66eed`. |
| `cf591b73` | **Accepted.** | Shared integration-record F-8 update only. |
| `1f2e8136` | **Accepted after record correction.** | Correct section 41 F-8 pointer; the missing current status/push row is closed here. |
| `62beb3fa` | **Accepted with shared residuals documented.** | Shared follow-up correctly refuses naive clocks, time-bounds leak attribution, and checks working-copy EOL. Patch-identical to source `f4764671`; `IBSH-CCR01..04` remain outside this lane. |
| `7eb3ccc2` | **Accepted after record correction.** | One-line lane pointer is accurate but did not refresh current status or the push ledger. |
| `11d894b6` | **Accepted.** | Shared record alignment only; its blob `d70e6cc497da44b81064e32c989ec831389525af` exactly equals main `df388ce6`. |

Section 41's sentence that "no lane-owned file changed" is true only for its
initial three-commit application. The later owner-directed F-8 commit changes a
Target-price-owned test, but no Insider-owned production or test file changed
in any shared-integration commit.

### 42.2 Retained P0-P3 ledger

| ID | Priority | Status | Finding, evidence, and disposition |
|---|---|---|---|
| IB2A-CCR01 / IB2A-CR04 | P3 | **Closed by the counter-review test commit.** | The final rebuilt-report fingerprint was correct but untested. A new regression mutates the report only between its captured and final complete projections. It passes on the real code, fails because no exception is raised when the guard is suppressed, and passes again after exact restoration. |
| IB2A-CCR02 / IB2A-CR02 | P3 | **Partially correct; record corrected here.** | The missing selector for the historical **22 passed, 75 deselected** subset is a real reproducibility defect, so that exact subset must not be cited as independently rerunnable. However, the claimed **289-pass** defect concerns Codex's chat closeout, not section 39: the number never appeared in the committed record. Section 40's 124-pass six-file command is its own different gate. |
| IB2A-CCR03 / IB2A-CR03 | P3 | **False alarm; closed without code.** | `IB1D-CR07A` is explicitly defined as the unambiguous name of the earlier acceptance-window evidence gate in ledger row `IB1H-CCR06`. It is searchable and dispositionable even though the historical collision prevents it from having a separately introduced table row. |
| IB2A-CCR04 / IB2A-CR05 | P3 | **Closed in this record.** | The 2026-09-03 Codex push lacked its own section-5 row. Its validation and look accounting remained in section 39 and Claude's later row, so evidence was not lost; this section and the new ledger row restore the missing push-level handoff. |
| IB2A-CCR05 | P3 | **Closed in this record.** | Top status still instructed Claude to review `7c9e6f53` after section 40 had completed that review and section 41 had applied later integration commits. The mutable status now names the current accepted-after-correction state and exact next bounded step. |
| IBSH-CCR01 | P2, shared/out of lane | **Open; documented, not fixed.** | `tests/conftest.py` uses normalized-string `startswith` for base-temp containment. A sibling path whose text merely shares the prefix is falsely attributed to this pytest session, contradicting the concurrent-session isolation claim and making an unrelated concurrent suite fail. |
| IBSH-CCR02 | P2, shared/out of lane | **Open; documented, not fixed.** | The non-mutating teardown guard rereads the same current-session incident after every test. One real leak can therefore error every later test rather than only the offending test, materially obscuring the responsible test and the suite result. |
| IBSH-CCR03 | P3, shared/out of lane | **Open; documented, not fixed.** | Direct `evaluate_sleeves(now=None)` forwards `None` to each per-position lot evaluation, allowing separate wall-clock samples inside one purported evaluation instant. The notification cycle supplies one aware clock, so the operational path corrected in this range is not affected. |
| IBSH-CCR04 | P3, shared/machine-local | **Open; documented, not fixed.** | On this checkout, two pre-attribute `research/ml_specs` files remain CRLF while their index blobs are LF, producing exactly two new EOL-guard failures. Healing shared working-copy bytes is outside the Insider lane and was not performed. |
| IBSH-CCR05 | P3, shared/out of lane | **Open; documented, not fixed.** | `test_shared_research_file_working_copy_matches_its_index_blob` and the shared records say the working-copy bytes match the index blob, but `git ls-files --eol` proves only the classified EOL style. The guard detects the recorded CRLF/LF defect but not arbitrary non-EOL byte drift. |

No P0, P1, or P2 defect remains in the reviewed Insider paths. Shared findings
were not corrected under the owner's lane-specific rule.

### 42.3 Independent verification and authority

IB-2A now passes **102 tests**. The new test killed the exact final-fingerprint
suppression mutation and the production module was restored byte-clean. The
eight-file focused review command produced **394 passed, 3 skipped, 2 failed**;
both failures are the documented machine-local shared-EOL condition, while the
Insider and shared behavioral tests passed. Stable patch IDs independently
match all four cited source commits. `git diff --check` is clean apart from
line-ending notices.

No SEC/EDGAR/provider endpoint, credential, licensed row, real filing,
outcome, QuantConnect action, broker, operator database, scheduler,
deployment, order, or UI was accessed. **Research looks: 0.** The execution
safety checklist is out of scope for the lane correction; the shared changes
grant no execution authority.

### 42.4 Counter-review conclusion and next step

The range is **accepted after lane-specific correction** and does not block the
next structural milestone. IB-2B is limited to deterministic SEC-scoped issuer
and reporting-owner grouping plus named owner-attribution quarantine over exact
factory-created IB-2A inventories. Point-in-time market-security mapping,
ticker/share-class resolution, authenticated amendments, canonical filtering,
deduplication, lot aggregation, the `$50,000` gate, outcomes, ETF/QC, and all
operational authority remain excluded.

## 43. Codex IB-2B SEC entity grouping and final hardening (2026-09-06)

### 43.1 Scope and commit sequence

Codex counter-reviewed the linear twelve-commit range
`7c9e6f53..11d894b6` in `d62c063`, then implemented bounded IB-2B in
`8928487`. Final provenance-snapshot and regression hardening is
`9fb017c`; this lane-record commit follows. No branch switch, provider
access, outcome access, or project-wide coordination-file change occurred.

### 43.2 Implemented boundary

IB-2B consumes exact factory-created IB-2A inventories and deterministically:

- groups filings by observed SEC issuer CIK and reporting-owner CIK;
- binds accession, accepted timestamp, source alias, issuer, owner, and
  transaction lineage exactly;
- retains original and amended filings as distinct as-filed observations;
- emits exactly one transaction-attribution row per retained transaction,
  without joint-owner fan-out;
- emits the named outcomes
  `SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED`,
  `MISSING_OWNER_SET_QUARANTINED`,
  `MULTIPLE_OWNER_SET_QUARANTINED`,
  `DUPLICATE_OWNER_CIK_QUARANTINED`, and
  `INCOMPLETE_OWNER_RELATIONSHIP_QUARANTINED`; and
- keeps every point-in-time verification, canonical-filter, aggregation,
  outcome, QC, deployment, and trading authority flag false, with authorized
  and consumed outcome looks exactly zero.

It does not perform ticker, security, or share-class mapping; authenticated
amendment supersession; deduplication; canonical eligibility filtering; lot
aggregation; the `$50,000` gate; outcome joins; ETF construction; QC work; or
any operational action. It therefore remains a bounded IB-2 slice, not full
IB-2 or blueprint step 19.4.5.

### 43.3 Retained P0-P3 implementation ledger

| ID | Priority | Status | Finding and disposition |
|---|---|---|---|
| IB2B-R01 | P2 | **Closed in `8928487`.** | A coherent forged IB-2A value could pass structural revalidation. IB-2A now records factory-created inventory fingerprints in a process-local locked weak-reference registry, and IB-2B requires that provenance seal. |
| IB2B-R02 | P2 | **Closed in `8928487`.** | Output validation did not completely bind issuer/owner/transaction cross-links, amendment lineage, and global identifier uniqueness. Exact cross-links and uniqueness are now enforced. |
| IB2B-R03 | P2 | **Closed in `8928487`.** | Projection work was not sufficiently bounded for the intended maximum fixture shape. The projection budget is now bounded at the documented finite ceiling. |
| IB2B-R04 | P3 | **Closed before `8928487`.** | Combined cross-link tests could mask which guard was load-bearing. Owner and transaction guards were sharpened and independently failed under exact guard removal before production restoration. |
| IB2B-R05 | P2 | **Closed in `9fb017c`.** | A deterministic A-to-B-to-A concurrent state swap could make validation return B-derived state while the surrounding live fingerprints again showed A. IB-2B now builds only from the copied validated snapshot and requires equality among that snapshot fingerprint, the live fingerprint, and the factory provenance seal. The two-thread regression refuses the swap. |
| IB2B-R06 | P2 | **Closed in `9fb017c`.** | A registered genuine root could be coherently mutated before the call without a regression proving comparison to the originally stored factory digest. The new test pins refusal against that original digest. |
| IB2B-R07 | P3 | **Closed in `9fb017c`.** | Builder-level provenance failure could mask weaknesses in independent upstream revalidation. Direct validation regressions now exercise that layer separately. |
| IB2B-R08 | P3 | **Closed in `9fb017c`.** | Cross-link sensitivity was not pinned one field at a time. Parameterized regressions independently vary owner accession/source/acceptance and transaction accession/source. |
| IB2B-R09 | P3 | **Closed in `9fb017c`.** | A static network-import denylist could miss alternate imports such as `http.client`. The test now requires the exact permitted import set for the complete module. |
| IB2B-R10 | P3 | **Closed in `9fb017c`.** | Exact-zero authority and look fields were enforced but not exhaustively pinned at constructors. Twenty-four authority/look escalation cases now refuse. |
| IB2B-R11 | P3 | **Closed in `9fb017c`.** | Concurrent provenance reads and weak-registry garbage-collection cleanup lacked lifecycle coverage. Both are now tested. A redundant final bounded O(n) provenance scan is retained as defense in depth; it is an accepted performance-only residual, not an authority or correctness gap. |
| IB2B-R12 | P3 | **Closed in `9fb017c`.** | The validated-snapshot copier's own depth, node, text, cycle, key-type, and unsupported-value refusals initially lacked direct permanent regressions. Additive tests now pin every guard without relying on the earlier upstream-projection refusal. |

No P0 or P1 finding was identified. `IBSH-CCR01` and `IBSH-CCR02`
remain open shared P2 findings; `IBSH-CCR03`, `IBSH-CCR04`, and
`IBSH-CCR05` remain open shared/out-of-lane P3 findings. Per owner
direction, none was fixed in this lane.

### 43.4 Validation, access accounting, and assessment

Counter-review evidence: IB-2A **102 passed**; the final-report rehash
regression passed, failed under exact suppression, and passed after
restoration. The focused review set produced **394 passed, 3 skipped, 2
failed**, with both failures being the retained shared machine-local CRLF/LF
findings. All four shared cherry-picks had exact source patch IDs, and the
final shared record blob matched main.

IB-2B evidence: the complete lane set produced **1,014 passed, 8 skipped**
before final hardening. The initial exact `8928487` repository suite produced
**2 failed, 7,254 passed, 15 skipped, 25 warnings in 2,731.11 seconds**; both
failures were the same two shared machine-local EOL findings. After
`9fb017c`, the focused IB-2A/IB-2B gate produced **179 passed**, and the
exact committed lane gate produced **1,054 passed, 8 skipped, 0 failed in
203.89 seconds**. A corrected-tree complete repository run was stopped at
**56%** when the owner directed this lane to push immediately; no failure
marker had appeared, and no complete-suite result is claimed for
`9fb017c`. Whole-repository compileall exited **0**.

Earlier exact provenance/amendment and sharpened owner/transaction guard
mutations produced red results and were restored. A later compound mutation
was not run because safety tooling rejected it; no mutation claim is made for
the new stored-fingerprint, import-allowlist, authority-constructor,
lifecycle, or validated-snapshot guard regressions.

No SEC/EDGAR/provider endpoint, credential, licensed row, real filing,
outcome, QuantConnect action, broker, operator database, scheduler,
deployment, capital, order, or UI was accessed. **Research looks: 0.**

Counter-review quality is **8/10**: every incoming commit was dispositioned,
material provenance was independently reproduced, and the lane gap received
a red/green regression; the five shared findings remain deliberately
deferred. IB-2B implementation quality is **9/10 after correction**: the
boundary is strict, immutable, resource-bounded, factory-bound,
concurrency-hardened, and zero-authority, while real SEC compatibility and
full point-in-time identity resolution remain intentionally unimplemented.

### 43.5 Copyable Claude review handoff

> Review every commit in `11d894b6..HEAD` on
> `codex/strategy-insider-buying`, including counter-review commit
> `d62c063`, IB-2B implementation commit `8928487`, hardening commit
> `9fb017c`, and the final lane-record commit. Give every commit an explicit
> disposition and retain a P0-P3 ledger. Independently reproduce the
> counter-review claims and IB-2B validation. Adversarially test factory
> provenance, coherent registered-root mutation, deterministic A-to-B-to-A
> concurrency, copied validated-state binding, accession/source/acceptance
> cross-links, issuer and reporting-owner CIK grouping, original/amended
> separation, global IDs and keys, one-row transaction attribution without
> owner fan-out, all five named owner outcomes, projection/resource caps,
> exact import isolation, concurrent/GC provenance lifecycle, and every
> authority or look field remaining exactly zero. Run the complete repository
> suite on the pushed tree because the final Codex run was interrupted at 56%
> by owner direction. Confirm that no security/ticker/share-class mapping,
> authenticated amendment supersession, deduplication, aggregation,
> `$50,000` gate, outcomes, ETF/QC, or operational authority was added. Fix
> only confirmed Insider-lane defects; document shared or out-of-lane findings
> without fixing them. Do not access SEC/provider data, credentials, licensed
> rows, outcomes, QuantConnect, broker, operator database, scheduler,
> deployment, capital, or trading authority. Stop after committing and
> pushing the review on this same lane for Codex counter-review.

## 44. Claude review - IB-2B SEC entity grouping and the IB-2A counter-review (2026-09-07 UTC)

Reviewer: Claude, in the macOS lane worktree resolved by `git worktree list`
(`trading_agent__insider_buying`) on `codex/strategy-insider-buying`. No
branch, worktree, fork, or handoff was created or switched to. The local
checkout was 19 commits behind and a strict ancestor of the remote; it was
fast-forwarded to exact remote head
`0027d57d80f4b6be461ed8a0794e88b354cb0aba`, which was re-fetched and found
unchanged before the review commits were made. Range reviewed in order from
base `11d894b6f1853c55984442b9e8b1aa097774919c`: `d62c063` (counter-review),
`8928487` (IB-2B implementation), `9fb017c` (provenance-snapshot hardening),
`0027d57` (lane record). Four commits, zero merges.

### 44.1 Isolation and scope

The range touches six paths: this record, `research/insider_buying/__init__.py`,
`research/insider_buying/form4_observed_identity_inventory.py`,
`research/insider_buying/form4_sec_entity_grouping.py`, and the two matching
`tests/test_insider_buying_*` files. Excluding lane-owned prefixes leaves an
empty set; no shared, frozen, or coordination file changed. Corrections in
this review are additive lane tests only; no production module changed.

Environment deviation, recorded plainly: this is the first Insider review run
on the owner's Mac. The only system interpreter is Xcode Python 3.9.6 without
pytest, so the first "complete suite" invocation ran zero tests and exited 1.
Homebrew `python@3.13` was installed and a venv built from the pinned
`requirements.txt` outside every worktree at `~/.venvs/trading_agent-py313`
(Python **3.13.15**, pytest **9.1.1**). Five untracked Finder `.DS_Store`
files (verified as `Apple Desktop Services Store`) were removed from this
checkout because the one under `docs/` fails a shared document test; see
IBSH-CCR06. Everything below was re-run on that environment.

### 44.2 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `d62c063` counter-review of the IB-2A review and shared integration | **Accepted.** | Its one test addition is real and load-bearing: the final report re-hash guard in `_validate_upstream_report` was neutralised and `test_rebuilt_report_mutation_during_validation_is_refused` failed (mutant I04 caught). Every material claim reproduced: all four cherry-picks have stable patch IDs identical to their sources (`b8f49eea`=`7f99f303`, `77055da4`=`3114a153`, `fb25d915`=`6ef66eed`, `62beb3fa`=`f4764671`); the integration-record blob at `11d894b6` is `d70e6cc4...`, byte-equal to `main` `df388ce6`; "289 passed" occurs zero times in the record at `7c9e6f53`; `IB1D-CR07A` is named in ledger row `IB1H-CCR06`, so IB2A-CCR03 is correctly a false alarm and IB2A-CCR02 correctly partially correct. Shared findings IBSH-CCR01, CCR02, CCR03 and CCR05 were confirmed by reading `tests/conftest.py`, `assistant/sleeve_report.py` (`now=None` forwarded per position at lines 183 and 424) and the EOL test (compares `git ls-files --eol` classes only); IBSH-CCR04 is machine-local to the Windows checkout and absent here (`i/lf w/lf` for all three `research/ml_specs` files). One ledger-row precision defect recorded as IB2B-CR06. |
| `8928487` IB-2B SEC entity grouping | **Accepted after correction.** | Lane-owned only. Design read in full: exact-type projection, factory tokens on every result type, process-local weak-reference provenance registry in IB-2A, independent dict-state revalidation, CIK-only grouping, one attribution row per retained transaction, five named outcomes, zero-authority identity. No product defect found. Fourteen guards on the owner's named directions had no test sensitivity (IB2B-CR01) and are now pinned. Excluded-scope keyword sweep matches only the module docstring's negation sentence, the upstream `PROVISIONAL_PRE_AGGREGATION_CANDIDATE` enum name, and the word "canonical" in accession/UTC validators. |
| `9fb017c` provenance-snapshot and concurrency hardening | **Accepted after correction.** | The copied validated-state fingerprint, the three-way equality with the live fingerprint and the factory seal, and the final re-fingerprint are all present and were mutation-tested as a system (44.4). The concurrent-read/GC lifecycle test in the IB-2A file is genuine. The A-to-B-to-A regression is correct but single-threaded (IB2B-CR02 is a record defect in `0027d57`, not a code defect here). Untested guards it introduced or left (validated-snapshot binding aside) are covered by IB2B-CR01. |
| `0027d57` counter-review and IB-2B record | **Accepted after record correction.** | Section 43 is accurate on scope, ledger, exclusions and access; three precision defects recorded append-only: IB2B-CR02 ("two-thread regression"), IB2B-CR03 (unnamed file set behind the 1,054/8 gate), IB2B-CR06 (P2 findings summarised as P3 in the ledger row). The push-ledger row for the round is present. |

### 44.3 Material claims reproduced

- Focused IB-2A/IB-2B gate: **179 passed in 1.21s** on `0027d57`, exactly as recorded.
- "Exact committed lane gate 1,054 passed, 8 skipped": the eleven `tests/test_insider_buying_*` files alone give **985 passed, 0 skipped in 4.36s**. Adding `test_active_document_consistency.py` (69) and `test_module_hygiene.py` (8) gives exactly **1,062 collected**, the recorded total; here that set ran **1,061 passed, 1 failed in 5.38s**, the failure being the machine-local `.DS_Store` case (IBSH-CCR06). The 8 Windows skips do not occur on macOS. The figure reproduces only after reconstructing the file set (IB2B-CR03).
- "IB-2A now passes 102 tests" at `d62c063`: the file collects 103 today and `9fb017c` added exactly one test, so 102 holds.
- "Twenty-four authority/look escalation cases": the parametrisation has 16 identity, 1 issuer, 1 owner and 6 transaction cases, 24 exactly.
- The provenance seal is real and load-bearing: removing `_register_factory_created_inventory(inventory)` fails the first IB-2B test (mutant I01); neutralising the stored-digest comparison fails `test_registered_inventory_rejects_coherent_pre_call_mutation` (I02).
- Complete repository suite on the pushed tree `0027d57`: **2 failed, 7,271 passed, 38 skipped, 28 warnings in 481.19s (0:08:01)**. Failures: `tests/test_active_document_consistency.py::test_docs_root_contains_only_current_coordination_and_active_plan` (Finder `.DS_Store` in `docs/`, passes after removal: 69 passed in 0.51s) and `tests/test_ui_backtest_page.py::test_results_survive_navigating_away_and_back` (streamlit `AppTest` 180 s timeout while the suite shared the CPU with this review's mutation sweep and lane gates; standalone: 8 passed in 27.03s; IBSH-CCR07). Whole-repository `compileall` including `research` exit **0**; `git diff --check` clean.
- Isolation: the range changes lane-owned paths only (verified from `git diff --stat 11d894b6..0027d57`).

### 44.4 Adversarial verification of the eleven named directions

Thirty-three targeted mutants on the pushed tree, one guard each (three multi-clause), module restored byte-identically after every run and confirmed with `git diff --quiet`: **12 caught, 21 survived, 0 invalid**. Every survivor was then classified by a further mutant or a new test rather than reported as a bare number.

| Direction | Guard | Pushed tree | Classification |
|---|---|---|---|
| 1 provenance | registry check on the captured fingerprint | survived | **redundant layer**: with it and the two later registry checks all removed (G30), `test_coherent_object_forgery_without_factory_provenance_is_refused` fails |
| 1 provenance | registration in IB-2A; stored-digest compare | caught, caught | pinned |
| 1 provenance | `current[0]() is value` | survived | structurally masked: the `id()` lookup returns no entry for a forged object; unreachable without an address collision |
| 2 A-to-B-to-A | `validated != captured`; registry on validated; `final != validated` | survived x3 | **redundant layers**: both post-validation clauses removed (G04) and all three layers removed (G07) fail the swap test; the final block removed (G06) fails the post-validation mutation test |
| 3 cross-links | owner `accepted_at_utc` link | caught | pinned |
| 3 cross-links | transaction to its filing's issuer candidate | survived | **untested; now pinned** |
| 4 CIK grouping | attribution rules (duplicate CIK, single-owner completeness) in both the builder and the constructor replay | caught x3 | pinned; drift between the two copies fails closed because the replay disagrees with the builder |
| 5 original/amended | row-level lineage | caught | pinned |
| 5 original/amended | output amendment-to-original binding (absent original; amendment accepted before original) | survived | **untested; now pinned** (two cases) |
| 5/6 lineage | acceptance-time ambiguity in the grouping | survived | **untested; now pinned** |
| 6/7 uniqueness | owner and transaction contiguity per filing | survived x2 | **untested; now pinned** |
| 7/8 attribution | grouping-level attribution-outcome consistency | survived | **untested; now pinned** - a MULTIPLE-owner quarantine rewritten as SINGLE attribution, internally coherent and passing its own row constructor, was accepted |
| 7/8 attribution | single-owner candidate binding | survived | **untested; now pinned** (three swaps) |
| 8 escalation | row-level "quarantined transaction carries an owner attribution" | survived | **untested; now pinned** (three shapes) |
| 7 counts | identity single-count clause; partition clause | survived x2 | partition **now pinned**; the single-count clause is a redundant pair with the quarantined-count clause (both removed, G31, is caught) |
| 9 limits | upstream projection depth, text, node bounds | survived x3 | **untested; now pinned** - the existing bound test matched either projection's message, so the upstream projection's own checks could be deleted while the validated-snapshot copier still refused |
| 9 limits | upstream projection cycle | caught | pinned |
| 8/11 independent revalidation | candidate inside a quarantined filing; identity authority flags | survived x2 | **untested; now pinned** directly at `_validate_upstream_inventory` |
| 11 independent revalidation | upstream filing owner-set state | survived | masked behind the provenance seal in the builder path; recorded, not pinned |
| 11 authority | 24 constructor escalations | tested | verified by reading the enforcement blocks and by G28 |

### 44.5 Findings

| ID | Sev | Status | Issue |
|---|---|---|---|
| IB2B-CR01 | P3 | **FIXED in `ff9d17f6`** | Fourteen guards on the owner's named directions could be deleted with the IB-2B file green (44.4). Twelve additive test functions (23 cases) pin them: forged escalation of a quarantined row to single-owner attribution, the three quarantined-row-with-owner shapes, the three single-owner binding swaps, the transaction-to-issuer-candidate link, the absent-original and precedes-original amendment cases, lineage acceptance ambiguity, owner and transaction contiguity, the two identity count cases, the three upstream-projection bounds by exact message, and the two direct upstream-revalidation refusals. Mutation-verified: the 16 targeted mutants (14 guards, plus G16 and G30) yield **15 caught**; the one survivor (G16) is caught together with its pair by G31. All pass on the unmodified module. No production module changed. |
| IB2B-CR02 | P3 | OPEN - record precision | Section 43.3 (IB2B-R05) and the 43.5 handoff describe "the two-thread regression" and "deterministic A-to-B-to-A concurrency". `test_transient_inventory_swap_cannot_change_the_consumed_snapshot` is single-threaded: a monkeypatched `_validate_upstream_inventory` swaps the state before the real validation and restores it in `finally`. The IB-2B test module imports no threading; the only threaded test in the range is the IB-2A registry concurrent-read test. The guard is correct; the description is not. |
| IB2B-CR03 | P3 | OPEN - record precision | "Exact committed lane gate 1,054 passed, 8 skipped" names no file set. The eleven Insider files give 985; the figure reconstructs only as those eleven plus `test_active_document_consistency.py` and `test_module_hygiene.py` (1,062). Same class as IB2A-CR02: name the file set or command for every gate figure. |
| IB2B-CR04 | P3 | OPEN - noted, no change | `_outcomes_from_output_owners` and `_attribution_outcomes_from_states` implement the same attribution rule twice (`CLAUDE.md` section 8 consolidation rule). Mutants G18-G20 show drift fails closed because the constructor replay disagrees with the builder, so this is maintainability, not a safety gap; `_owner_set_outcomes` re-derives the IB-2A rule deliberately for independent revalidation. |
| IB2B-CR05 | P3 | CLOSED - classification | Six survivors are redundant defence-in-depth layers, not gaps (44.4): the captured-fingerprint registry check, the two post-validation clauses, the final `!=` clause, the identity single-count clause, and the registry identity compare. Recorded so a future round does not misread the same survivors. |
| IB2B-CR06 | P3 | OPEN - record precision | The 2026-09-06 counter-review ledger row calls `IBSH-CCR01..04` "shared/out-of-lane P3 observations" while section 42.2 rates IBSH-CCR01 and IBSH-CCR02 P2; the later row corrects the range to CCR01..05 but not the priority. |
| IBSH-CCR06 | P3, shared/out of lane | OPEN - documented, not fixed | `.gitignore` excludes `.pytest_cache/` and `.venv/` but not `.DS_Store`; a Finder `.DS_Store` under `docs/` fails `test_docs_root_contains_only_current_coordination_and_active_plan`. Either the ignore list or the test's allow-list needs the entry; both are shared files. |
| IBSH-CCR07 | P3, shared/out of lane | OPEN - documented, not fixed | `tests/test_ui_backtest_page.py::test_results_survive_navigating_away_and_back` fails with the streamlit `AppTest` 180 s timeout under CPU contention (observed once while three pytest sessions overlapped) and passes standalone. A load-sensitive timeout in the shared UI suite. |

One unreproduced observation, recorded plainly: the first thirteen-file run reported **2 failed, 1,060 passed** while the complete suite ran concurrently; only the `.DS_Store` failure was captured and only it recurred in two immediate reruns (1 failed, 1,061 passed). The second test name was not captured.

### 44.6 Validation on the final tree

- IB-2B file: **99 passed in 1.01s** (76 recorded plus 23 review cases).
- IB-2A plus IB-2B: **202 passed in 1.27s**.
- Eleven Insider files plus `test_active_document_consistency.py`, `test_module_hygiene.py`, `test_ml_import_boundary.py` and both project-separation suites: **1,131 passed in 18.79s**.
- Complete repository suite on the final code tree, with no concurrent pytest session: **7,296 passed, 38 skipped, 28 warnings, 0 failed in 417.61s (0:06:57)** (7,271 + the two explained failures now passing + 23 review cases); exit 0.
- Whole-repository `compileall` including `research`: exit **0**. `git diff --check`: clean. Changed paths: one lane test file (+456 lines) and this record.
- Mutants: 33 on the pushed tree (12/21/0); 17 verification mutants after the additions (16 caught, 1 redundant-pair survivor then caught in combination); every module restored byte-identical and confirmed against `HEAD`.

### 44.7 Quality rating

**8 / 10.** The product code is sound: no defect was found in `form4_sec_entity_grouping.py` or in the IB-2A provenance registry, the fail-closed ordering is right, and the layered provenance checks hold up as a system under combined mutation. The rating is held below the previous round because the same defect shape has recurred for a fourth consecutive milestone and grew: fourteen refusal guards on the owner's own adversarial list, including the attribution-escalation direction, could be deleted with the file green. Section 37.7 already asked for "every new refusal branch gets a test that fails without it" as an implementation checklist item; section 43.4 records that Codex's compound mutation "was not run because safety tooling rejected it" and makes no mutation claim for the new guards, which is honest but is exactly where the gaps sat.

### 44.8 Authority, residual gates, and access accounting

Every authority flag on the grouping identity, candidates, attribution rows and the grouping object remains literal `False`; both look counters remain exactly `0`, verified by direct inspection of the enforcement blocks and by the caught escalation mutants. IB-2B adds no ticker, security or share-class mapping, no amendment supersession, no deduplication, canonical filtering, aggregation, `$50,000` gate, outcome join, ETF or QC work, and no operational authority. IB-1 remains incomplete; IB-2 point-in-time identity resolution remains unstarted beyond this CIK-scoped slice. All prior open findings are carried forward unchanged, including `IBSH-CCR01..05`, `IB0H-R06`, `IB0H-R07`, `IB1H-R02`, `IB1H-R03`, `IB1G-R04`, `IB1G-R05`, `IB2A-CR02`, `IB2A-CR04` and `IB2A-CR05`.

External access this round: **none**. No SEC or EDGAR endpoint, provider, credential, licensed row, real filing, outcome, QuantConnect action, broker, operator database, scheduler, deployment, capital, or order. Package installation reached PyPI and Homebrew for the pinned toolchain only. **Research looks: 0.**

### 44.9 Handoff

Outcome: all four commits accepted, three after correction; one additive test
commit `ff9d17f6a27be80c1c1eaf1bef341880a1200ba4`, the record commit
`532e4cde68af5f6e3e84a4626d279b08c077f98a`, and this documentation-only commit
that names them. The review commits are **local to the lane branch and not pushed**: the owner's machine-wide guideline (2026-09-06) reserves pushes for explicit owner authorization in the conversation, and Codex normally makes the round's single push. Next authorized step: the owner pushes or authorizes the push of the two review commits; Codex then counter-reviews them. No milestone was started and none is authorized.

## 45. Codex counter-review and bounded IB-2C point-in-time security mapping (2026-09-07)

### 45.1 Exact scope and commit sequence

Codex stayed in the existing `codex/strategy-insider-buying` branch and
worktree. A fresh fetch confirmed that the exact pushed Claude range was
`0027d57d80f4b6be461ed8a0794e88b354cb0aba..a898be5e416679d27fed7e0f83a1b1cf24f8407e`:
three linear commits and zero merges. The counter-review correction is
`c74a5757925e3425690f6fce62b16efcd0078cf5`; the bounded IB-2C code and tests
are `3a5ec9f2930f4e4b2ec3ba2e66b2ac85e4ba6f12`; this authoritative lane-record
commit follows. No side branch, review branch, worktree, rebase, or force push
was created or used. Project-wide coordination documents remain unchanged.

| Incoming commit | Disposition | Counter-review basis |
|---|---|---|
| `ff9d17f6a27be80c1c1eaf1bef341880a1200ba4` | **Accepted after record correction.** | The additive mutation guards are real and load-bearing; exact-head IB-2B is 99/99 green. The diff adds **13 test functions / 23 parameter cases**, not the 12 functions stated in the commit message and section 44. |
| `532e4cde68af5f6e3e84a4626d279b08c077f98a` | **Accepted after current record correction.** | The technical review and mutation dispositions reproduce. Its historical status became stale after the review range was pushed; it also carries two already-closed IB-2A record findings and the 12-function count. This section corrects those facts append-only. |
| `a898be5e416679d27fed7e0f83a1b1cf24f8407e` | **Accepted after current record correction.** | It correctly names all three review commits in the status, but section 44.9 still calls them “two review commits” and says they are local/unpushed. Fresh fetch showed local and remote exactly at this commit before Codex work began. |

All six section-44 findings were independently dispositioned. `IB2B-CR01`
is accepted as fixed by `ff9d17f6`. `IB2B-CR02` is a description defect: the
A-to-B-to-A test is a deterministic single-thread monkeypatch, not a
two-thread test. `IB2B-CR03` is corrected by naming the historical gate as the
eleven then-existing `tests/test_insider_buying_*.py` files plus
`tests/test_active_document_consistency.py` and `tests/test_module_hygiene.py`.
`IB2B-CR04` is fixed in `c74a575` by one shared
`_owner_attribution_outcomes` primitive used by both builder and constructor
replay. `IB2B-CR05` remains correctly closed as redundant defense-in-depth.
`IB2B-CR06` is correct: `IBSH-CCR01` and `IBSH-CCR02` are P2, while
`IBSH-CCR03..05` are P3. Section 42.2 already closed `IB2A-CR04` and
`IB2A-CR05`; section 44.8's contrary carry-forward is superseded here.

### 45.2 Bounded IB-2C behavior

IB-2C is an offline structural mapping boundary. It consumes one exact,
process-sealed IB-2B result and three exact tuples of caller-supplied synthetic
reference records: permanent security/share-class intervals, exact raw-title
intervals, and ticker/listing intervals. It then:

- produces exactly one disposition row for every IB-2B transaction, with no
  fan-out or silent drop, while retaining accession/source, original/amended
  lineage, filing and issuer observations, transaction hashes, issuer CIK,
  and owner-attribution outcomes;
- resolves security and exact raw title on the transaction date, resolves the
  ticker on the filing's America/New_York acceptance date, and uses the exact
  acceptance instant as the knowledge cutoff;
- ignores reference facts not yet available at that cutoff and treats a
  closure whose evidence was not yet available as open; row-level
  `security_interval_asof_id`, `title_interval_asof_id`, and
  `ticker_interval_asof_id` mask every unavailable closure field while the
  full audit-bound catalog remains retained;
- refuses transactions dated after the Eastern filing date, ambiguous title
  or ticker histories, symbol mismatches, cross-CIK title selection,
  cross-security listing overlap, child intervals outside their permanent
  security, and share-class IDs assigned to more than one security;
- permits only truly half-open sequential ticker reuse across distinct
  securities, including the `date.max` boundary, and quarantines apparent
  reuse when the old closure was not yet knowable;
- permits deterministic-exact or explicitly labeled manual-exception title
  records only by exact text—never fuzzy matching—and treats supplied class
  labels as structural metadata, never canonical eligibility;
- captures reference and grouping state without callbacks, rebuilds detached
  exact records, rechecks pre/post fingerprints, replays every output row
  against the retained catalog, process-seals the result, canonicalizes order,
  and enforces preflight count, projection, cumulative text, containment, and
  resolution-work bounds; and
- names its mapping-only partition
  `security_mapping_quarantined_count`, so an independently retained upstream
  owner-attribution quarantine cannot be mistaken for mapping cleanliness.

`point_in_time_mapping_structurally_resolved=True` means only that one
caller-supplied structural mapping was unique at the cutoff. Every inherited
official-profile, amendment, issuer, reporting-owner, security, and
transaction verification gate remains present and false. Official security
master compatibility, ordinary-equity classification, canonical filtering,
lot aggregation, SEC/provider access, outcomes, QC execution, deployment, and
trading also remain false; authorized and consumed outcome looks are zero.

### 45.3 Retained P0-P3 ledger

| ID | Priority | Status | Finding, evidence, and disposition |
|---|---|---|---|
| IB2B-CCR01 | P3 | **Closed in this record.** | `ff9d17f6` added 13 test functions / 23 cases, not 12 functions. The tests and case count are unchanged; only the durable description is corrected. |
| IB2B-CCR02 | P3 | **Closed in this record.** | Section 44.8 incorrectly carried `IB2A-CR04` and `IB2A-CR05` as open although section 42.2 had closed both. The earlier text remains historical; current state is corrected above. |
| IB2B-CCR03 | P3 | **Closed in this record.** | Section 44.9 said two review commits were local/unpushed. There are three, and fresh fetch confirmed all three through `a898be5` on the remote. |
| IB2C-R01 | P2 | **Closed in `3a5ec9f`.** | Constructor-valid IB-2B clones had no process identity seal suitable for a downstream boundary. IB-2B now registers exact output fingerprints in a locked weak-reference registry; IB-2C requires the exact live factory object and stored fingerprint. The new test was red with the seal API absent and green after implementation. |
| IB2C-R02 | P2 | **Closed in `3a5ec9f`.** | Caller mutation or coherent output forgery could otherwise detach a row from the state actually resolved. Callback-free double capture, exact dataclass state, final grouping/reference rechecks, full row replay, hash/count/crosslink reconstruction, and an IB-2C process seal now fail closed. |
| IB2C-R03 | P2 | **Closed in `3a5ec9f`.** | A full-record ID or prematurely honored closure could leak future knowledge. Base and closure evidence have separate availability and lineage; unavailable facts are invisible, unavailable closures are treated as open, and only masked as-of interval IDs enter rows. Future-dated transactions receive a named quarantine. |
| IB2C-R04 | P2 | **Closed in `3a5ec9f`.** | Same-ticker reuse needed protection across issuers and security IDs. Title lookup is CIK scoped; final listing histories cannot overlap across securities; as-of listing uniqueness includes intervals whose closure was not yet known. A two-issuer regression proves correct old/new mapping and dangerous-direction quarantine. |
| IB2C-R05 | P2 | **Closed in `3a5ec9f`.** | Reference children could otherwise bind outside a permanent-security interval or reuse one share-class ID for multiple security IDs. Exact inverse identity and full half-open containment checks now refuse both shapes. Indexed resolution avoids a Cartesian product. |
| IB2C-R06 | P2 | **Closed in `3a5ec9f`.** | The first IB-2C draft omitted IB-2B's hard-false official-profile, amendment, issuer, reporting-owner, and transaction gates. Identity and rows now carry the applicable gates, constructors refuse every escalation, and result properties remain hard false. Suppressing one guard produced the expected one-test red; exact restoration returned green. |
| IB2C-R07 | P2 | **Closed in `3a5ec9f`.** | Initial structural rows did not bind the complete Form 4/4-A issuer and amendment lineage needed for deterministic replay. Document type, original/amended accessions, issuer observation, source/event/report/transaction IDs, and owner attribution are retained and replayed exactly. |
| IB2C-R08 | P3 | **Closed in `3a5ec9f`.** | Exact/manual title semantics and unrelated future records needed dangerous-direction coverage. A near-match manual title is quarantined, exact exceptions are labeled without granting canonical status, and a future unrelated same-title fact cannot poison the exact issuer match. |
| IB2C-R09 | P3 | **Closed in `3a5ec9f`.** | Early resource tests stopped at the first guard and resolution accounting omitted relevant-security and pair-key scans. Count preflight precedes projection; cumulative containment and resolver thresholds have distinct tests; the rich path asserts all six charges during build and replay. |
| IB2C-R10 | P3 | **Closed in `3a5ec9f`.** | Generic `quarantined_count` could be read as whole-row cleanliness even when upstream owner attribution remained quarantined. The identity now names the exact mapping-only partition, and the joint-owner regression proves it can be zero while upstream quarantine is retained. |
| IB2C-R11 | P3 | **Closed in `3a5ec9f`.** | The initial module prose said every closure must already be available, contradicting the implemented knowledge-cutoff rule. It now states that only available closures influence resolution and unavailable closures remain open as of the cutoff. |
| IB2C-R12 | P3 | **Closed in `3a5ec9f`.** | Encoding an open listing end as real `date.max` allowed another security to begin on `date.max` without overlap refusal. An ordinal beyond every representable date is now the open-end sentinel. The original probe now refuses, and 20,000 randomized interval sets including open/maximum-date endpoints matched a naive pairwise oracle. |
| IB2C-G01 | Gate, not a defect in this bounded slice | **OPEN / explicitly deferred.** | Blueprint section 7's durable `qc_symbol_id` binding and an official point-in-time security master are not implemented. No QC/provider access was authorized or inferred. This snapshot therefore does not claim full IB-2, the full blueprint security-master step, or QC compatibility. |

No open P0-P3 finding remains in the new lane-owned code. The pre-existing
shared/out-of-lane findings remain documented and unchanged:
`IBSH-CCR01` and `IBSH-CCR02` are P2; `IBSH-CCR03..07` are P3 (including the
machine-local status already recorded for `IBSH-CCR04`). Earlier deferred
lane debts `IB0H-R06`, `IB0H-R07`, `IB1H-R02`, `IB1H-R03`, `IB1G-R04`,
`IB1G-R05`, and the historical reproducibility item `IB2A-CR02` remain as
their authoritative sections describe. They are not silently closed or
changed by IB-2C.

### 45.4 Verification, scope, and access accounting

- Exact incoming head `a898be5`: IB-2B **99 passed**; Claude's named
  lane/boundary gate **1,131 passed**; tree clean.
- Counter-review correction: the primitive-consolidation test failed red
  because zero shared helper existed, then passed with exactly one helper;
  the complete grouping file passed **100 tests**.
- Final bounded milestone: IB-2C **68 passed**; IB-2B plus IB-2C
  **169 passed**; all twelve `tests/test_insider_buying_*.py` files plus
  `tests/test_active_document_consistency.py` and
  `tests/test_module_hygiene.py` **1,155 passed in 5.83s**.
- Exact committed code tree `3a5ec9f`: complete repository suite
  **7,366 passed, 38 skipped, 26 warnings, 0 failed in 360.48s (0:06:00)**
  under Python 3.13.15 / pytest 9.1.1. The skips are platform conditional;
  warnings are dependency/runtime notices.
- Whole-repository `python -m compileall -q assistant execution tests research`
  exited **0** using an external bytecode cache. Staged/untracked and committed
  diff checks were clean. The implementation-record, active-document,
  preregistration, and module-hygiene files passed **200 tests** after this
  record update. Three independent read-only audit streams drove corrections;
  the final re-review found no remaining P0-P3 issue and matched ticker-overlap
  enforcement to naive pairwise oracles across 20,000 open/maximum-date cases.
- Material authority reverse mutation: removing the
  `official_profile_compatibility_verified` constructor guard made its exact
  escalation test fail because no refusal was raised; restoring the line made
  the same test pass. The module was restored before commit.

Access was limited to the local repository/toolchain and a Git remote refresh.
No SEC or EDGAR endpoint, real filing, provider, credential, licensed row,
outcome, QuantConnect job or upload, QC process, broker, operator database,
scheduler, deployment, capital, order, or trading surface was accessed.
**Authorized outcome looks: 0. Consumed outcome looks: 0.**

### 45.5 Copyable Claude review handoff

> On `codex/strategy-insider-buying`, verify the remote tip and independently
> review every commit in `a898be5e416679d27fed7e0f83a1b1cf24f8407e..HEAD`:
> counter-review correction `c74a5757925e3425690f6fce62b16efcd0078cf5`,
> bounded IB-2C implementation `3a5ec9f2930f4e4b2ec3ba2e66b2ac85e4ba6f12`,
> and the lane-record commit containing section 45. Give every commit an
> explicit disposition and retain the P0-P3 ledger. Reproduce the incoming
> record corrections and red/green evidence. Adversarially review exact
> factory provenance; pre/post mutation; full deterministic replay;
> availability and hidden-closure slicing; Eastern filing-date ticker
> selection; CIK/title/share-class isolation; original/amended lineage;
> same-ticker overlap, sequential reuse, and `date.max`; exact manual-title
> behavior; aggregate bounds and charge sensitivity; mapping-only counts;
> every hard-false inherited/new authority field; and zero look counters.
> Confirm that `qc_symbol_id`, an official security master, authenticated
> amendment supersession, canonical eligibility, deduplication, aggregation,
> the `$50,000` gate, outcomes, ETF/QC, deployment, capital, broker, and
> trading authority remain absent or false. Fix only confirmed Insider-lane
> defects; document shared/out-of-lane findings without changing shared
> behavior. Do not access SEC/provider data, credentials, licensed rows,
> outcomes, QuantConnect, brokers, operator databases, deployment, capital,
> or trading. Commit and push the review on this same branch for Codex's next
> counter-review.


## 46. Claude review - IB-2B counter-review and bounded IB-2C point-in-time security mapping (2026-09-07)

Reviewer: Claude, in the lane worktree `trading_agent__insider_buying` on
`codex/strategy-insider-buying` (owner's Mac, Python 3.13.15, pytest 9.1.1).
No branch, worktree, fork, or handoff was created or switched to. The remote
tip was verified as `d6f43bd8bf92618e4bd0b7a797711a59974b7e8c` and the local
branch fast-forwarded to it. Range reviewed in order:
`c74a5757` (counter-review correction), `3a5ec9f2` (IB-2C implementation),
`d6f43bd8` (record). Three commits, zero merges; every changed path is
lane-owned (`research/insider_buying/`, `tests/test_insider_buying*`, this
record).

### 46.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `c74a5757` consolidate the owner-attribution rule | **Accepted, no issue found.** | One `_owner_attribution_outcomes` primitive over `(owner_ciks, relationships_complete)` tuples is called by both the builder and the constructor replay; `_outcomes_from_output_owners` and `_attribution_outcomes_from_states` are gone. Verified by reading the complete diff and by the AST pin plus rule table in `test_owner_attribution_uses_one_primitive_rule_implementation`. The primitive fails closed on malformed primitive input. |
| `3a5ec9f2` bounded IB-2C | **Accepted after correction.** | Lane-owned only. The eleven owner-named directions were adversarially verified (46.3). Two P3 findings were confirmed and fixed in `1496244`: one refusal clause missing from the row constructor (IB2C-CR01) and ten guards with no test sensitivity (IB2C-CR02). Three P3 observations are recorded without code change (IB2C-CR03..05). |
| `d6f43bd8` record | **Accepted.** | Every material claim reproduces: the five counter-review record corrections (46.2), the 68 / 169 / 1,155 focused figures exactly, and the complete-suite pass/skip/fail counts exactly (7,366 / 38 / 0). The only delta is 28 warnings here against the recorded 26, an environment difference, not a record defect. |

### 46.2 Counter-review record corrections reproduced

| Codex correction | Independent result |
|---|---|
| `ff9d17f6` added 13 test functions / 23 cases, not 12 functions | Confirmed. `git show ff9d17f6` adds exactly 13 `def test_` lines; the file collects 76 tests at `0027d57` and 99 at `ff9d17f6`, a difference of 23. Section 44's "twelve additive tests" was wrong. |
| The A-to-B-to-A regression is deterministic and single-threaded | Confirmed. `test_transient_inventory_swap_cannot_change_the_consumed_snapshot` swaps state inside a monkeypatched `_validate_upstream_inventory`; no thread is created. |
| The historical 1,054 / 8 gate was the eleven then-existing `tests/test_insider_buying_*.py` files plus `test_active_document_consistency.py` and `test_module_hygiene.py` | Confirmed. An exported snapshot of `9fb017c` (`git archive`, no worktree) collects **1,062** tests for that file set and **985** for the eleven Insider files alone; 1,054 + 8 = 1,062. |
| `IB2A-CR04` and `IB2A-CR05` were already closed in section 42.2 | Confirmed. Section 42.2 rows `IB2A-CCR01 / IB2A-CR04` and `IB2A-CCR04 / IB2A-CR05` close both. Section 44.8's carry-forward was this reviewer's error and is superseded. |
| All three Claude commits through `a898be5` were pushed | Confirmed. The remote tip was `a898be5e` before Codex's round began (verified in this session by dry-run push). |

### 46.3 Adversarial verification of the owner-named directions

Thirty-eight targeted mutants, one neutralised guard each, focused run over
the IB-2C and IB-2B files after each, module restored from a byte-exact
in-memory copy in a `finally` block and re-verified byte-identical.
**Pushed tree: 24 caught, 14 survived, 0 invalid.** Every survivor was then
classified rather than reported as a defect.

| Direction | Guard mutated | Pushed tree | Classification |
|---|---|---|---|
| Factory provenance | seal gate removed; snapshot-hash vs seal removed; final grouping recheck removed; IB-2B seal registration removed; IB-2B seal fingerprint comparison removed | caught x5 | pinned |
| Pre/post capture and replay | reference recapture check removed; mapping row id binding removed; row replay equality (existing test) | caught x2 | pinned |
| Knowledge cutoff / hidden closure | availability cutoff made exclusive; hidden closure honored; as-of closure masking removed | caught x3 | pinned |
| Transaction-date validity | validity end made inclusive; transaction-after-filing check removed | caught x2 | pinned |
| America/New_York filing date | filing date taken in UTC | caught | pinned |
| CIK / title / share-class / security isolation | share-class multi-security refusal removed; containment start check inverted; pair ambiguity removed; listing-level ticker ambiguity removed; issuer symbol mismatch removed | caught x5 | pinned |
| CIK / title isolation | title lookup not CIK scoped | **survived** | **provably redundant**: candidate pairs are keyed by `(security_id, share_class_id)` and security ids come from the issuer-filtered `securities_by_issuer`, so a title bound to another issuer's security can never form a pair. Defense in depth and a lookup-cost bound, not a correctness layer. |
| Original/amended lineage | row amendment lineage refusal removed | **survived** | **untested; now pinned** (three contradictory chains) |
| Ticker overlap, sequential reuse, `date.max` | overlap refusal removed; overlap made inclusive (would refuse adjacent reuse); open-end sentinel equals `date.max` | caught x3 | pinned; additionally a 20,000-case randomized oracle (securities A/B/C, starts including `date.max` and `date.max - k`, open and closed ends) matched a naive pairwise half-open check with **0 mismatches**, and both boundary probes behaved (`[BASE, open)` vs `[date.max, open)` refused; `[BASE, date.max)` then `[date.max, open)` accepted) |
| Bounds and charge sensitivity | preflight count bound removed | **survived** | **untested ordering property; now pinned**: the existing test's `match="count exceeds"` matched both the preflight and the later inventory-count refusal, so IB2C-R09's "count preflight precedes projection" claim had no test sensitivity. The new test asserts the exact preflight message and that projection never runs. |
| Bounds | reference projection node bound removed; depth bound removed | **survived x2** | **untested; now pinned** with exact `reference input exceeds the node/depth bound` messages (a loose `node bound` regex is also satisfied by the provenance projection, which is why the first draft of the pin did not catch them) |
| Bounds | closure-before-base-availability refusal removed | **survived** | **untested; now pinned** |
| Mapping-only counts | result quarantined-count binding removed | **survived** | **provably redundant**: `Form4PitSecurityMappingIdentity.__post_init__` enforces `mapped + quarantined == rows` (its removal was caught) and the result constructor binds `mapped` to the rows, which together imply `quarantined == rows - mapped`. |
| Mapping-only counts | identity partition removed; identity `manual <= mapped` removed | caught; **survived** | partition pinned by the existing forged-identity test; the manual-count bound was untested and is **now pinned** |
| Row completeness / partial mapping | mapped-row completeness removed; quarantined-row partial-mapping removed | **survived x2** | **untested; now pinned** in both directions (incomplete mapped row; leaked security id, resolved flag, and mixed outcomes on a quarantined row) |
| Owner attribution inheritance | whole owner-promotion `elif` removed | **survived** | **gap, fixed** (IB2C-CR01): the existing clause (owner on a quarantined row) was untested and the clause IB-2B carries (`SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED` beside a quarantine outcome) was absent. Both directions now pinned. |
| Canonical order / uniqueness | canonical row order removed; row and upstream id uniqueness removed | **survived x2** | **untested; now pinned** (reversed two-row result; duplicated row) |
| Authority and look counters | row authority check removed; identity authority check removed | caught x2 | pinned (17 identity fields, 11 row fields, 4 look-counter escalations already parametrized) |
| Exhaustiveness | builder exhaustiveness check removed | **survived** | **unreachable by construction**: rows are built by a one-to-one comprehension over the snapshot's transactions; the check can only fire if `_resolve_row` itself misbehaves. Defense in depth, recorded. |

After the correction commit, the eleven genuine survivors were re-run against
their exact mutants: **all caught**. The missing clause was verified
red/green in isolation: with only the new two-line clause removed the new test
fails; with it restored the test passes.

Excluded-scope confirmation: an AST test pins the exact import set (stdlib,
`data.hashing`, three Insider modules; no network, provider, execution, or
float surface). A keyword sweep of the module for `qc_symbol`, `50,000`,
aggregation, deduplication, supersession, broker, deployment, order, and
QuantConnect terms matches only the docstring's negation sentence. Every
inherited and new authority field on the identity, the rows, and the result
properties is hard `False`; both look counters are exact integer zero;
`point_in_time_mapping_structurally_resolved=True` asserts only that one
caller-supplied structural mapping was unique at the cutoff.

### 46.4 Findings

| ID | Sev | Status | Issue |
|---|---|---|---|
| IB2C-CR01 | P3 | **FIXED in `1496244`** | `Form4PitSecurityMappingRow.__post_init__` refused an owner CIK or candidate on a quarantined row but accepted `owner_attribution_outcomes` containing `SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED` beside a quarantine outcome when both owner fields were `None`. IB-2B refuses that shape at its own row constructor. Because `_replay_mapping_row` passes owner outcomes through from the row, the constructor is the only guard on this inherited state. One clause added, mirroring IB-2B; regression `test_row_constructor_refuses_owner_quarantine_promotion_shapes` covers both the pre-existing (untested) owner-field direction and the new outcome-shape direction. Reachable only through `object.__new__` forgery; no factory path emits it. |
| IB2C-CR02 | P3 | **FIXED in `1496244`** | Ten guards on owner-named directions could be deleted with the file green (46.3). Nine additive tests (12 cases) pin them; each was mutation-verified against its exact mutant. The preflight-ordering pin also converts IB2C-R09's prose claim into an enforced property. |
| IB2C-CR03 | P3 | OPEN - contract clarity, recorded for Codex | `reference_sha256` is validated only as a lowercase SHA-256 and copied into the identity; nothing binds it to the captured reference content. The content itself is bound by `security_record_inventory_hash`, `title_interval_inventory_hash`, and `ticker_interval_inventory_hash`, so no integrity gap exists, but the field name invites a reader to treat it as a content hash. Either document it as an external catalog lineage pointer (like `reference_id` / `reference_version`) or bind it to the captured payload. Not changed here because either choice alters the identity contract and is the implementer's call. |
| IB2C-CR04 | P3 | OPEN - design limit, recorded | `_validate_reference_crosslinks` requires each title or ticker interval to be contained by a single permanent-security record. A child spanning two adjacent records of the same security (for example a record split at a re-confirmation date) is refused as exceeding permanent-security validity even though the union covers it. Fail-closed and internally consistent; catalog suppliers must split children at parent boundaries. Recorded so the rule is visible, not changed. |
| IB2C-CR05 | P3 | OPEN - nit | The module defines no `__all__`, unlike IB-2A and IB-2B. The package `__init__` imports names explicitly, so nothing is functionally affected. |
| IB2C-N01 | note | recorded | `ZoneInfo("America/New_York")` is resolved at import and depends on a tz database. On Windows this is the `tzdata` package, which the pinned `pandas` pulls in transitively (2026.3 in the Mac venv); eight `assistant/` modules and the Short Interest lane already use `zoneinfo`, so this follows the established pattern. |
| IB2C-N02 | note | recorded | The pushed-tree complete suite shows 28 warnings on this Mac against the recorded 26; pass, skip, and fail counts match exactly. |
| IB2C-N03 | note | recorded | Three mutation survivors are proven redundant or unreachable layers (46.3): the CIK-scoped title lookup, the result-level quarantined-count binding, and the builder exhaustiveness check. They are retained as defense in depth and are not gaps. |

No P0, P1, or P2 finding. The shared/out-of-lane findings `IBSH-CCR01..07`
are unchanged and were not touched. `IB2C-G01` (no `qc_symbol_id`, no
official point-in-time security master) is confirmed open and correctly
labelled a gate rather than a defect.

### 46.5 Validation

Pushed tree `d6f43bd8`, before any change:

- Complete repository suite: **7,366 passed, 38 skipped, 28 warnings, 0 failed in 438.58s (0:07:18)**.
- IB-2C **68 passed**; IB-2B + IB-2C **169 passed**; twelve Insider files + active-document + module-hygiene **1,155 passed** - each reproduces Codex's figure exactly.

Final tree (`1496244` plus this record):

- IB-2C **80 passed**; IB-2B + IB-2C **181 passed**; twelve Insider files + active-document + module-hygiene + import boundary **1,178 passed in 8.97s**.
- Complete repository suite: **7,378 passed, 38 skipped, 28 warnings, 0 failed in 401.89s (0:06:41)**.
- Whole-repository compileall (the CLAUDE.md set plus `research`) exit **0**; `git diff --check` clean; worktree clean apart from untracked `.DS_Store` files (IBSH-CCR06).
- Mutants: 38 on the pushed tree (24 / 14 / 0); the 11 pinned survivors re-run after correction, all caught; every module restored byte-identical and confirmed by the harness and by `git status`.
- Oracle: 20,000 randomized listing-overlap cases, 0 mismatches; 2 explicit `date.max` probes correct.

No SEC, EDGAR, vendor, QuantConnect, credential, licensed row, outcome,
broker, operator-database, scheduler, deployment, capital, or trading access.
**Research looks: 0.** Authorized and consumed outcome looks remain exact
integer zero on every identity, row, and result property.

### 46.6 Quality rating

**9 / 10**, held. The IB-2C boundary is carefully built: callback-free double
capture, detached record rebuild, exact replay, process seal, half-open
interval semantics with a correct open-end sentinel, and a knowledge cutoff
that treats unknowable closures as open. The listing-overlap algorithm is
non-obvious and survived an independent randomized oracle. The counter-review
correction is exactly what IB2B-CR04 asked for.

It is not raised because the same defect shape recurred for a fourth
consecutive milestone: correct guards with no test behind them (fourteen in
IB-2B, ten here), plus one guard IB-2B carries that IB-2C omitted. The
lane's checklist item "every new refusal branch gets a test that fails
without it" is still not being applied before push; a mutation sweep by the
implementer would have found all eleven of these before review.

### 46.7 Authority, residual gates, and next step

Every authority gate remains closed. IB-2C is a bounded structural slice:
`qc_symbol_id` and an official point-in-time security master are deferred
(IB2C-G01); authenticated amendment supersession, canonical filtering,
deduplication, lot aggregation, the `$50,000` gate, outcomes, ETF/QC,
deployment, broker, capital, and trading authority were not added. Full IB-2
is not complete and IB-1 remains incomplete.

Review commits on this lane: correction `1496244` and this record commit.
Next authorized step: Codex counter-reviews both. No milestone was started and
none is authorized.


## 47. Codex counter-review of the IB-2C review and bounded IB-2D provisional lot diagnostics (2026-09-08 UTC)

### 47.1 Exact range and per-commit dispositions

Codex stayed in the existing `codex/strategy-insider-buying` branch and
worktree. A fresh fetch confirmed the exact pushed Claude range as
`d6f43bd8bf92618e4bd0b7a797711a59974b7e8c..6383019c49cba902876bfe9da66483cd2c07055c`:
two linear commits and zero merges. No side branch, worktree, rebase, force
push, or project-wide document edit was used.

| Incoming commit | Disposition | Counter-review basis |
|---|---|---|
| `1496244e9e8f5e503f6b2fe68df9b787567dfcc6` | **Accepted after record precision correction.** | The two-line constructor refusal is correct and fail-closed. The nine additive test functions collect as twelve cases, remove or weaken no test, and pin the intended guards. The missing-clause red/green and all eleven previously surviving genuine guard directions were independently reproduced. Its narrative misallocates one guard between IB2C-CR01 and IB2C-CR02, corrected append-only below. |
| `6383019c49cba902876bfe9da66483cd2c07055c` | **Accepted after append-only record correction.** | The technical review, mutation classifications, randomized overlap oracle, authority conclusions, and access accounting reproduce. Four P3 precision defects concerning the direction count, keyword sweep, CR01/CR02 guard inventory, and next authorization are corrected below without rewriting section 46. |

### 47.2 Counter-review reproduction and section-46 corrections

Removing only the new
`SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED`-beside-quarantine refusal made
`test_row_constructor_refuses_owner_quarantine_promotion_shapes` fail because
no exception was raised; exact restoration returned it green. The nine
functions and twelve collected cases added in `1496244` were inspected and
their eleven previously surviving guard directions were independently
mutation-verified. The three IB2C-N03 survivors were also confirmed:

- CIK-scoped title lookup is redundant for result correctness because candidate
  pair keys use security IDs drawn from the issuer-filtered security inventory;
- result-level quarantined-count binding follows from the identity partition
  plus mapped-count binding; and
- builder exhaustiveness is unreachable while rows remain a one-to-one
  comprehension over the upstream transaction inventory.

All three layers remain useful defense in depth and were retained.

Section 46 is corrected append-only as follows:

1. Section 45.5 names **thirteen**, not eleven, semicolon-delimited review
   directions: provenance; pre/post mutation; replay; availability slicing;
   Eastern-date ticker resolution; CIK/title/share-class isolation; amendment
   lineage; ticker reuse and `date.max`; manual-title behavior; resource
   bounds; mapping counts; authority flags; and look counters.
2. On the exact reviewed tree `6383019`, the fixed-string sweep yields
   `qc_symbol` 0, `50,000` 0, `aggregation` 9, `deduplication` 0,
   `supersession` 0, `broker` 0, `deployment` 10, `order` 1, and
   `QuantConnect` 0. The nonzero matches are the deliberately hard-false
   aggregation/deployment authority fields and properties plus the canonical
   row-order refusal. The exact-import AST test and semantic inspection—not
   the overbroad "docstring only" sentence—establish the excluded surface.
3. The complete `1496244` addition is nine functions / twelve cases. IB2C-CR01
   owns the one-function/one-case owner-quarantine regression, which pins both
   the pre-existing owner-promotion refusal and the newly added
   SINGLE-beside-quarantine clause. IB2C-CR02 owns eight functions / eleven
   cases covering ten guards: amendment lineage, mapped-row completeness,
   quarantined-row partial mapping, canonical row order, row/upstream-ID
   uniqueness, manual-count binding, preflight-before-projection, reference
   node bound, reference depth bound, and closure-before-base availability.
   Section 46 placed owner promotion in the CR02 inventory and omitted the
   closure-before-base guard.
4. Claude correctly stopped without starting another milestone, but "none is
   authorized" conflicts with the owner's standing serialized loop and
   explicit instruction to counter-review and implement the next milestone.
   Once this review was accepted and no owner gate blocked offline work,
   bounded IB-2D was authorized. No external-data, outcome, QC, operational,
   or trading authority followed from that authorization.

### 47.3 IB-2C retained findings ledger

| ID | Priority | Status | Disposition |
|---|---|---|---|
| IB2C-CR01 | P3 | **Accepted as fixed in `1496244`.** | The row constructor now refuses SINGLE attribution beside any quarantine outcome; the new and pre-existing promotion directions are red/green pinned. |
| IB2C-CR02 | P3 | **Accepted as fixed in `1496244`; inventory corrected here.** | Eight functions / eleven cases pin the ten guards listed in 47.2. |
| IB2C-CR03 | P3 | **Closed in `611dceda77e20960cb0b596b29b496f5675def6e`.** | Module, identity, builder, and validation prose now define `reference_sha256` as the digest of the complete external artifact named by `reference_id` and `reference_version`, while the three inventory hashes bind the captured subset. A regression proves that changing external-artifact lineage changes `mapping_id` without changing the subset hashes. |
| IB2C-CR04 | P3 | **Closed in `611dceda77e20960cb0b596b29b496f5675def6e`.** | The single-parent containment rule is now an explicit normalization contract: suppliers must split children at every parent boundary. Title and ticker intervals spanning adjacent same-security parents are both pinned as refused. |
| IB2C-CR05 | P3 | **Closed in `611dceda77e20960cb0b596b29b496f5675def6e`.** | The module now has an exact public `__all__`, pinned against the package surface. |
| IB2C-CCR01 | P3 | **Closed in this record.** | The owner handoff named thirteen directions, not eleven. |
| IB2C-CCR02 | P3 | **Closed in this record.** | The keyword-sweep claim is replaced by the exact counts and semantic classification in 47.2. |
| IB2C-CCR03 | P3 | **Closed in this record.** | The CR01/CR02 function, case, and guard allocation is corrected without changing the tests. |
| IB2C-CCR04 | P3 | **Closed in this record.** | The standing owner loop had authorized the next bounded offline milestone after accepted counter-review. |
| IB2C-N01 | Note | **Accepted.** | `zoneinfo` follows the repository's established timezone dependency pattern. |
| IB2C-N02 | Note | **Accepted as environmental.** | The 28-versus-26 warning delta did not change pass, skip, or failure counts. |
| IB2C-N03 | Note | **Confirmed.** | The three survivors are redundant or unreachable defense-in-depth layers, not correctness gaps. |

No new P0, P1, or P2 finding arose from the counter-review. `IB2C-G01`
remains an open gate: no official point-in-time security master or
`qc_symbol_id` exists.

### 47.4 Bounded IB-2D behavior

Commit `68a7045949999aee65d4fadbf88148d38843b2bf` adds
`form4_provisional_lot_diagnostics`, an offline, exhaustive, hash-bound
diagnostic boundary. It composes the exact factory-created IB-1E evidence,
IB-2A inventory, IB-2B grouping, and IB-2C mapping, rebuilds the IB-1G report
from the original evidence using the inventory's builder lineage, and verifies
the complete mapping -> grouping -> inventory -> evidence/report chain through
detached snapshots, direct constructor replay, type-sensitive runtime
fingerprints, final rechecks, and a process-local result seal.

The result:

- emits exactly one deterministic diagnostic row per mapping row, without
  fan-out, deduplication, silent drop, or promotion;
- retains accession, source, event, transaction, issuer, owner, mapped
  security/share-class, title-kind, parser, identity, attribution, mapping,
  economics, and quarantine lineage;
- builds a separately sorted amendment-family accession inventory from supplied
  filing evidence, including Form 4/A filings with zero transaction rows, and
  quarantines every retained row in any supplied amended family;
- accumulates parser, observed-identity, owner-attribution, security-mapping,
  unavailable-economics, amendment-family, and non-ordinary-class reasons
  without losing independent reasons;
- admits only otherwise-clean rows whose provisional structural class is
  `COMMON_STOCK`, `COMMON_SHARES`, or `ORDINARY_SHARES`; manual title mappings
  remain explicit and never override a non-ordinary-class quarantine;
- groups provisional candidates only by reporting-owner CIK, exact owner
  candidate ID, permanent security ID, share-class ID, and transaction date—
  never ticker or accession;
- retains sorted member row IDs, issuer CIK, exact Decimal share and purchase
  totals, and latest member acceptance for every provisional group; and
- applies the exact `>= USD 50,000` comparison only as a diagnostic after
  grouping. The `49,999.99`, `50,000`, and `50,000.01` boundaries are pinned,
  and below-threshold groups remain retained rather than filtered.

The implementation is resource bounded for rows, groups, amendment families,
enum/reason tuples, projection depth/nodes/text, and Decimal digits/exponents.
Public row, group, identity, and result objects are factory-only, replayable,
canonically ordered, hash-bound, and explicitly exported.

### 47.5 IB-2D implementation findings

All findings were verified, generalized, corrected, and red/green pinned before
`68a7045`. A final independent audit found no remaining P0-P3 issue.

| ID | Priority | Status | Finding and correction |
|---|---|---|---|
| IB2D-R01 | P2 | **Closed in `68a7045`.** | Coherent replay could clear amendment-family quarantine and promote rows. Exact row/family membership and mandatory self-family inclusion for every Form 4/A now refuse the forgery; the exact-membership and self-family regressions are red/green pins. |
| IB2D-R02 | P2 | **Closed in `68a7045`.** | `MAPPED_STRUCTURALLY` could remain a candidate with a missing normalized class or title-mapping kind. All retained mapping fields and transaction date are now mandatory; both omission directions are pinned. |
| IB2D-R03 | P2 | **Closed in `68a7045`.** | A value-only result seal erased Enum-to-string, tuple-to-list, and equal-Decimal representation changes. The seal now includes type- and Decimal-representation-sensitive runtime state; the enum and tuple mutations were accepted red and refuse green, with the Decimal representation independently pinned. |
| IB2D-R04 | P2 | **Closed in `68a7045`.** | Canonical IB-2A/IB-2B/IB-2C seals alone admitted equal-valued type corruption. IB-2D now directly replays every upstream public constructor and binds a separate runtime fingerprint for each stage before/after capture and in the final recheck. A mapping Enum-to-string mutation returned one row red and refuses green; six cross-stage cases pin the generalized fix. |
| IB2D-R05 | P2 | **Closed in `68a7045`.** | Evidence Enum-to-string mutation after report rebuild evaded an equality-only TOCTOU comparison. A type-sensitive evidence runtime fingerprint and final recheck now refuse the exact red probe (`ACCEPTED 1 True str`) with `inventory and rebuilt evidence report disagree`. |
| IB2D-R06 | P3 | **Closed in `68a7045`.** | Row replay admitted promotion-shaped owner/mapping fields beside quarantine outcomes and a purchase value beside a missing economic operand. Bidirectional owner/mapping shape and all-present-or-quarantined economics invariants now refuse those states; the two partial-economics directions failed red because no exception was raised and both pass green. |
| IB2D-R07 | P3 | **Closed in `68a7045`.** | Amendment-family and enum tuples lacked early cardinality guards, and the family identity count used the transaction ceiling rather than the filing ceiling. Pre-scan caps and the exact filing-count binding are pinned before duplicate-set or element-scan work. |
| IB2D-R08 | P3 | **Closed in `68a7045`.** | Decimal validation/projection could expand an extreme exponent disproportionately and did not charge generated Decimal text. The extreme probe expanded to 1,000,001 characters and a zero text budget accepted `Decimal("1")` red; coefficient/exponent caps and both projection budgets now pass three green regressions. |
| IB2D-R09 | P3 | **Closed test gap in `68a7045`.** | All four direct row joins—mapping/attribution, attribution/inventory, mapping/issuer, and mapping/rebuilt report—could be removed while 62 tests stayed green. Four exact mismatch cases now pin them. |
| IB2D-R10 | P3 | **Closed test gap in `68a7045`.** | Replacing per-family membership with `bool(amended_families)` kept 62 tests green and poisoned unrelated originals. An isolation regression now kills that mutant. |
| IB2D-R11 | P3 | **Closed coverage gap in `68a7045`.** | The intersection of an entirely empty transaction inventory and a zero-row original/Form 4/A family was unpinned. A direct probe and retained regression verify two filings, zero rows/groups, and one exact family. |

### 47.6 Validation, exclusions, and access accounting

Counter-review reproduction on the received tree matched Claude's focused
figures: IB-2C **80 passed**, IB-2B plus IB-2C **181 passed**, and the named
lane/boundary gate **1,178 passed**. Claude's exact final-tree complete result
remains **7,378 passed, 38 skipped, 28 warnings, 0 failed**.

The exact current tree (`68a7045` code plus this record) produced:

- IB-2C reference-contract and counter-review checks: **84 passed**;
- IB-2D focused file: **83 passed**;
- IB-2A through IB-2D: **371 passed**;
- those four stages plus hygiene/import boundaries: **390 passed**;
- complete lane/boundary gate: **1,265 passed**;
- complete repository suite: **7,465 passed, 38 skipped, 26 warnings, 0 failed
  in 359.84s (0:05:59)**; and
- whole-repository compileall exit **0**, with final diff and status checks to
  be clean before the single push.

All counter-review and IB-2D mutations were restored byte-identically before
commit. The 83-case IB-2D file covers exact Decimal aggregation and threshold
boundaries, grouping-key dimensions, amendment-family quarantine including
zero-row and unrelated-family cases, upstream quarantine accumulation,
authority/factory gates, four-stage provenance and joins, constructor/result
replay, bounded complexity, TOCTOU mutations, process seals, and the exact
offline/API surface. The final independent audit found no remaining material
mutation direction and no open P0-P3 issue.

All official-profile, official-amendment-link, complete-amendment-coverage,
official-security-master, authenticated-supersession, point-in-time identity,
ordinary-equity, deduplication, canonical-filter, lot-aggregation,
post-aggregation-minimum, SEC/provider, outcome, QC, deployment, and trading
authority fields remain literal `False`. Authorized and consumed outcome
looks remain exact integer zero.

Access was limited to the local repository/toolchain and Git remote refresh.
No SEC or EDGAR endpoint, provider, credential, licensed row, real filing,
outcome, QuantConnect job or process, broker, operator database, scheduler,
deployment, capital, order, or trading surface was accessed. **Research
looks: 0.**

`IB2C-G01`, official amendment authentication/completeness, and all earlier
documented lane gates remain open. The shared/out-of-lane findings
`IBSH-CCR01..07` and earlier retained lane debts remain unchanged and were not
fixed. IB-2D performs no authenticated amendment supersession, canonical
filtering, authorized deduplication or aggregation, operative `$50,000` gate,
stock scoring, ETF construction, QC work, or operational action. Full IB-2
and IB-1 remain incomplete.

### 47.7 Copyable Claude review handoff

> On `codex/strategy-insider-buying`, verify the remote tip and independently
> review every commit in
> `6383019c49cba902876bfe9da66483cd2c07055c..HEAD`: IB-2C contract correction
> `611dceda77e20960cb0b596b29b496f5675def6e`, bounded IB-2D implementation
> `68a7045949999aee65d4fadbf88148d38843b2bf`, and the lane-record commit
> containing section 47. Give every commit an explicit disposition and retain
> the P0-P3 ledger. Reproduce the IB-2C missing-clause red/green, the new-test
> mutation sensitivity, the three redundancy proofs, the four append-only
> section-46 corrections, and closures of IB2C-CR03..05. For IB-2D,
> adversarially review the exact mapping/grouping/inventory/evidence chain;
> direct replay and type-sensitive fingerprints; mid-build/final TOCTOU
> checks; one-row-per-mapping-row exhaustiveness; owner/security/class/date
> grouping key; exact Decimal sum/product; post-grouping diagnostic threshold;
> complete supplied-amendment-family quarantine including zero-row 4/A and
> unrelated-family isolation; latest-acceptance retention; manual-mapping
> visibility; upstream-quarantine accumulation; constructor/result replay;
> resource bounds; canonical order; public exports; every hard-false authority
> field; and zero look counters. Confirm that no official security master,
> `qc_symbol_id`, authenticated supersession, canonical filter, deduplication,
> authorized aggregation or `$50,000` gate, outcome, ETF/QC, deployment,
> capital, broker, or trading authority was added. Fix only confirmed
> Insider-lane defects; document shared/out-of-lane findings without changing
> shared behavior. Do not access SEC/provider data, credentials, licensed
> rows, outcomes, QuantConnect, QC processes, brokers, operator databases,
> deployment, capital, or trading systems. Commit and push the review on this
> same branch for Codex's next counter-review.


## 48. Claude review - IB-2C counter-review correction and bounded IB-2D provisional lot diagnostics (2026-09-08 UTC)

Reviewer: Claude, in the lane worktree `trading_agent__insider_buying` on
`codex/strategy-insider-buying` (owner's Mac, Python 3.13.15, pytest 9.1.1).
No branch, worktree, fork, or handoff was created or switched to. A
one-minute remote watch fired when Codex's push landed; the remote tip was
verified as `84c9ebe119a809fb88a1c14bfdadfe09ce83aadf` and the local branch
fast-forwarded to it. Range reviewed in order: `611dceda` (IB-2C contract
correction), `68a70459` (IB-2D implementation), `84c9ebe1` (record). Three
commits, zero merges; every changed path is lane-owned.

### 48.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `611dceda` clarify and pin the IB-2C reference contract | **Accepted, no issue found.** | Closes IB2C-CR03 by documenting `reference_sha256` as the digest of the complete external artifact named by `reference_id`/`reference_version` (the implementer's choice between the two options offered), with a regression proving a lineage change moves `mapping_id` while the three subset inventory hashes stay fixed; closes IB2C-CR04 with an explicit single-parent normalization comment and two parametrized refusals (title and ticker children spanning adjacent same-security parents); closes IB2C-CR05 with an exact `__all__` pinned against the package surface. The file collects 84 (80 + 4). |
| `68a70459` bounded IB-2D | **Accepted after test-only correction.** | Lane-owned only. The owner-named directions were adversarially verified (48.3). Fourteen guards had no test sensitivity (IB2D-CR01, fixed in `5655759`). No production defect was found; two observations are recorded (IB2D-CR02 owner decision, IB2D-CR03 coupling). |
| `84c9ebe1` record | **Accepted.** | Every material claim reproduces exactly: 84 / 83 / 371 / 390, the 1,265 lane gate (1,254 plus the 11-test import-boundary file), and the complete-suite pass/skip/fail counts 7,465 / 38 / 0. The four section-47 corrections to section 46 are all accepted (48.2). |

### 48.2 Section-47 corrections and IB-2C closures verified

| Codex correction | Independent result |
|---|---|
| Section 45.5 named thirteen directions, not eleven | Accepted. The semicolon-delimited handoff list has thirteen items; section 46's ledger row already said thirteen and its prose was inconsistent. |
| Keyword sweep counts on `6383019` (`aggregation` 9, `deployment` 10, `order` 1, others 0) | Accepted. My sweep filtered out the hard-false authority lines and the canonical-order refusal before reporting "docstring only"; the record sentence omitted that filter, so the precision correction is fair. |
| IB2C-CR01 owns the owner-quarantine regression; IB2C-CR02 owns eight functions / eleven cases over ten guards including closure-before-base availability | Accepted. Section 46 placed owner promotion under CR02 and omitted closure-before-base from the CR02 inventory. |
| "None is authorized" conflicted with the standing serialized loop | Accepted as wording. The loop authorizes the next bounded offline milestone after an accepted counter-review; whether IB-2D's content is inside the intended bound is the separate owner decision recorded as IB2D-CR02. |

`IB2A-CR04`/`CR05` remain closed; `IB2C-CR03..05` are closed by `611dceda`;
`IB2C-N01..N03` are accepted as Codex dispositioned them.

### 48.3 Adversarial verification of the owner-named directions

Thirty-two targeted mutants on `form4_provisional_lot_diagnostics.py`, one
neutralised guard each, focused IB-2D plus IB-2C run after each, module
restored from a byte-exact in-memory copy in a `finally` block and
re-verified byte-identical. **Pushed tree: 11 caught, 19 survived, 1 invalid
string (corrected and re-run: caught).** Every survivor was then classified.

| Direction | Guard mutated | Pushed tree | Classification |
|---|---|---|---|
| Amendment-family quarantine | family flag forced false; 4/A self-family registration removed; result 4/A-must-flag-own-family rule removed | caught x3 | pinned (including the zero-row 4/A and unrelated-family isolation cases) |
| Exact Decimal sum/product and threshold | non-positive economics accepted; threshold `>=` made `>`; row economics product check removed; latest acceptance `max` made `min`; builder manual count ignores disposition | caught x5 | pinned; the `49,999.99` / `50,000` / `50,000.01` boundaries and the low-ambient-precision sum are existing pins |
| Grouping key | `share_class_id` dropped from the key | caught | pinned |
| Grouping key | one key spanning two issuers accepted | **survived** | **untested; now pinned** (forged rows sharing a key with different `issuer_cik` refuse in `_aggregate_provisional_groups`; reachable through result replay because the key omits the issuer) |
| Provisional class matrix | `PREFERRED_STOCK` admitted as ordinary | caught (after string fix) | pinned by the six-class matrix |
| Constructor/result replay | result group replay refusal removed | caught | pinned |
| Constructor/result replay | row parser/identity binding; row-id binding; group-key binding; group non-positive totals; member-id order/uniqueness; identity partition; identity `groups <= candidates`; result family-inventory order/uniqueness; result `mapping_row_id` uniqueness | **survived x9** | **untested; now pinned** - the `mapping_row_id` clause was shadowed by the `diagnostic_row_id` clause until a forged second row shared the mapping id |
| Owner-quarantine inheritance | `SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED` beside a quarantine with both owner fields `None` | **survived** | **untested; now pinned** - the clause exists (unlike IB-2C before `1496244`) but its only test also set an owner field, which the earlier clause refuses first |
| Exact chain and TOCTOU | final `_recheck_inputs` removed | caught | pinned |
| Exact chain and TOCTOU | final evidence-hash recheck removed | **survived** | **redundant pair**: the runtime-fingerprint recheck immediately after it refuses the same drift; a combined mutant removing both is now **caught** by a new test that mutates the evidence during group aggregation |
| Exact chain and TOCTOU | capture-time provenance gate removed | **survived** | **provably redundant** with `_recheck_inputs` (whose removal is caught): an unsealed or mutated input is refused at the end of the build by the same registry comparison; work proceeds on it in between but nothing is returned |
| Exact chain | mapping-to-grouping identity-hash clause removed | **survived** | **provably redundant**: `grouping_id` is the prefix of that identity hash and `upstream_grouping_fingerprint` covers the whole grouping including its identity |
| Exact chain | issuer-observation count vs `filing_count` removed | **survived** | **unreachable by construction**: IB-2B emits exactly one issuer observation per filing, enforced by its own constructor |
| Exact chain | rebuilt-report identity-hash clause removed | **survived** | **provably redundant** with `rebuilt_report_id` (a prefix of the same hash) and `upstream_report_row_inventory_hash` |
| Exact chain | rebuilt-report join exhaustiveness removed | **survived** | **unreachable**: a mapping row without a report row is refused two statements later as an incomplete upstream join |
| Resource bounds | Decimal digit bound removed; non-text projection dict key accepted | **survived x2** | **untested; now pinned** |

After the correction commit every pinned guard was re-run against its exact
mutant: **all caught**, and the six classified survivors still survive for
the stated reasons. Existing pins already covered the four-stage seal and
type corruption (six cross-stage cases), the four direct joins, the
mid-build mapping and evidence mutations, the projection depth/node/text
bounds, the group-count and row-count preflights, and every authority and
look-counter escalation on rows, groups, and identity.

Structural confirmations made by reading rather than mutating: economics are
copied only from the report rebuilt from the original evidence bytes with the
inventory's builder lineage; `ContractError` derives from `ValueError`, so the
private IB-2A refusals (`_preflight_evidence`, `_validate_rebuilt_report`)
are normalized by the public builder; the row constructor's candidate rule
(`parser_outcomes == (ELIGIBLE_FOR_LOT_AGGREGATION,)`) is exactly IB-1G's
disposition rule; the group key is owner CIK, owner candidate id, security
id, share-class id, and transaction date, never ticker or accession; and the
excluded scope holds by the exact-import AST test (stdlib, two `data`
helpers, six Insider modules; no network, provider, execution, pandas, or
float surface).

### 48.4 Findings

| ID | Sev | Status | Issue |
|---|---|---|---|
| IB2D-CR01 | P3 | **FIXED in `5655759`** | Fourteen guards on the owner-named directions could be deleted with the file green (48.3). Nine additive tests pin them; each was mutation-verified against its exact mutant, and the evidence-recheck pair against a combined mutant. Test-only; no production module changed. |
| IB2D-CR02 | Owner decision | **OPEN, recorded** | IB-2D introduces the lot-aggregation arithmetic (`exact_decimal_sum` over a provisional group) and the exact `>= USD 50,000` comparison into lane code. They are labelled diagnostics, every authority field is hard `False`, and below-threshold groups are retained, so nothing filters or supersedes. But the only thing separating this from the blueprint's operative post-aggregation gate is naming and those flags; the previous two review handoffs required confirming that no aggregation or `$50,000` gate was *added*, and this round adds both as diagnostics. Section 47.2 argues the standing loop authorized it. Recorded so the owner can confirm the bound is as intended or narrow it; no code change made. |
| IB2D-CR03 | P3 | OPEN - maintainability, recorded | IB-2D imports nine private names from IB-2A/IB-2B/IB-2C (`_preflight_evidence`, `_validate_rebuilt_report`, `_contract_payload`, `_evidence_observation_hash`, three provenance payload/fingerprint pairs, and the three upstream factory tokens). Replaying upstream constructors with their tokens is what makes the type-sensitive recheck possible, but it also means the process-local trust boundary is now shared across four modules and any private rename breaks IB-2D silently at import. Established lane pattern (section 39.4 noted the same coupling for IB-2A); recorded, not changed. |
| IB2D-N01 | note | recorded | Six mutation survivors are proven redundant or unreachable (48.3): capture-time provenance gate, mapping-to-grouping identity-hash clause, issuer-count clause, report identity-hash clause, report join exhaustiveness, and the final evidence-hash recheck (pinned as a pair). Retained as defense in depth. |
| IB2D-N02 | note | recorded | The recorded "complete lane/boundary gate 1,265" is the thirteen Insider files plus active-document, module-hygiene, and the 11-test import-boundary file; the thirteen-plus-two set alone is 1,254. Both reproduce. |
| IB2D-N03 | note | recorded | 28 warnings on this Mac against the recorded 26; pass, skip, and fail counts match exactly. |
| IB2D-N04 | note | recorded | The IB-2C and IB-2D test files import sibling test modules (`from tests import test_insider_buying_form4_sec_entity_grouping as ib2b`) although `tests/` has no `__init__.py`; this works because pytest puts the repository root on `sys.path`. Lane-owned files, repository-level mechanism; noted so a future `tests` package change does not surprise the lane. |

No P0, P1, or P2 finding. `IBSH-CCR01..07` and the earlier lane debts are
unchanged. `IB2C-G01` remains an open gate.

### 48.5 Validation

Pushed tree `84c9ebe1`, before any change:

- Complete repository suite: **7,465 passed, 38 skipped, 28 warnings, 0 failed in 387.51s (0:06:27)**.
- IB-2C **84**; IB-2D **83**; IB-2A..IB-2D **371**; plus hygiene/import boundary **390**; thirteen Insider files + active-document + module-hygiene **1,254** (+ import boundary = **1,265**). Each reproduces Codex's figure.

Final tree (`5655759` plus this record):

- IB-2D **92 passed**; IB-2A..IB-2D **380 passed**; thirteen Insider files + active-document + module-hygiene + import boundary **1,274 passed in 10.22s**.
- Complete repository suite: **7,474 passed, 38 skipped, 28 warnings, 0 failed in 396.39s (0:06:36)**.
- Whole-repository compileall (the CLAUDE.md set plus `research`) exit **0**; `git diff --check` clean.
- Mutants: 32 on the pushed tree (11 / 19 / 1, the invalid string corrected and caught); the fourteen pinned survivors re-run after correction, all caught; every module restored byte-identical and confirmed by the harness and `git status`.

No SEC, EDGAR, vendor, QuantConnect, credential, licensed row, outcome,
broker, operator-database, scheduler, deployment, capital, or trading access.
**Research looks: 0.** Authorized and consumed outcome looks remain exact
integer zero on every row, group, identity, and result property.

### 48.6 Quality rating

**9 / 10**, held. IB-2D is the most thoroughly cross-bound stage in the
lane: economics come only from a report rebuilt from the original evidence,
every join is checked in both directions, the seal is type-sensitive, and
the amendment-family rule handles zero-row amendments and unrelated
families correctly. The exact-Decimal path resists a low ambient precision.

It is not raised because the same defect shape recurred for a fifth
consecutive milestone: correct guards with no test that fails when they are
removed (fourteen here), including one whose only test was masked by an
earlier clause in the same `elif`. The implementer's own mutation sweep
(section 47.5 reports several) is not yet reaching constructor replay
clauses and identity count bounds; those are exactly where the survivors
cluster in every round.

### 48.7 Authority, residual gates, and next step

Every authority gate remains closed. IB-2D is a bounded diagnostic slice:
`qc_symbol_id`, an official point-in-time security master, and
authenticated amendment supersession remain deferred; canonical filtering,
deduplication, authorized aggregation, the operative `$50,000` gate,
outcomes, ETF/QC, deployment, broker, capital, and trading authority were
not added. Whether the diagnostic aggregation and comparison are inside the
intended bound is the owner's call (IB2D-CR02). Full IB-2 and IB-1 remain
incomplete.

Review commits on this lane: test correction `5655759` and this record
commit. Next authorized step: Codex counter-reviews both; the owner decides
IB2D-CR02. No milestone was started.


## 49. Codex counter-review of the IB-2D Claude review (2026-09-08 UTC)

### 49.1 Exact range and per-commit dispositions

Codex remained in the owner-designated
`trading_agent__insider_buying` worktree on
`codex/strategy-insider-buying`. A fresh fetch and clean-state check found
local `HEAD` and `origin/codex/strategy-insider-buying` exact at
`9a93d09543c8c772a5062bf42d9d01afdbcc2bd9`. The incoming Claude range is
`84c9ebe119a809fb88a1c14bfdadfe09ce83aadf..9a93d09543c8c772a5062bf42d9d01afdbcc2bd9`:
two linear commits and zero merges. No branch, worktree, rebase, force push,
or shared/project-wide document change was made.

| Incoming commit | Disposition | Counter-review basis |
|---|---|---|
| `5655759143e2a85e2fadd12270311da09b7adfe3` | **Accepted; no P0-P3 finding.** | The complete diff changes one lane-owned test file by 300 additive lines and nine test functions. It changes no production code and removes, skips, or weakens no existing test. The focused result and five representative reverse mutations reproduce the intended red/green sensitivity. |
| `9a93d09543c8c772a5062bf42d9d01afdbcc2bd9` | **Accepted after append-only record correction.** | The technical product review and authority conclusions reproduce, but section 48 has four P3 record/process defects: unique-mutant arithmetic, overlap between genuine gaps and a redundant paired guard, a false scope blocker/non-P0-P3 severity, and an incorrect private-import count/failure mode. They are corrected below without rewriting section 48. |

### 49.2 Test-correction reproduction

The nine new tests collect as the exact expected increase from 83 to 92.
The final IB-2D file passes all **92** cases, and IB-2C plus IB-2D passes
**176**. Five representative guards were independently neutralized in
memory, without touching a repository file:

- owner `SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED` beside quarantine with both
  owner fields absent;
- diagnostic row-ID binding;
- rejection of one group key spanning two issuer CIKs;
- rejection of non-text projection keys; and
- the combined final evidence-hash and runtime-fingerprint rechecks.

Each reverse mutation either admitted the prohibited state or made its new
test fail because no exception was raised. Restoring the exact code returned
all five cases green. The worktree and module bytes remained unchanged.
This independently supports acceptance of `5655759` and confirms that its
correction is test-only.

### 49.3 Append-only corrections to section 48

1. The campaign contains **31 unique mutant directions**, not 32. Its first
   pass produced 11 caught, 19 survived, and one invalid mutation. Correcting
   and rerunning that invalid mutation adds a thirty-second execution and
   catches it. The final unique-direction result is therefore **12 caught / 19
   survived**, across **32 executions**.
2. The 19 survivors divide into **13 independently untested guards** and six
   redundant or unreachable directions. The final evidence-hash recheck is
   one of the six: it still survives when removed alone because the adjacent
   runtime-fingerprint check catches the same drift. The new test pair-pins
   that defense-in-depth layer by removing both checks together. Thus the
   accurate correction claim is thirteen independent test gaps plus one
   redundant recheck covered by a combined mutation—not fourteen independently
   untested guards whose individual exact mutants are all caught.
3. The factual core of IB2D-CR02 is accepted: IB-2D computes exact provisional
   group totals and compares them with `$50,000`. Its owner-decision blocker
   is rejected. Section 47 explicitly handed off the exact Decimal sum and
   post-grouping diagnostic threshold for review and prohibited only
   **authorized** aggregation and an operative `$50,000` gate. The canonical
   contract itself requires same-owner/security/date grouping before the
   threshold. IB-2D retains every below-threshold group, performs no canonical
   filtering, deduplication, or supersession, exposes no authorized consumer,
   keeps every authority flag false, and consumes zero looks. Behavior—not
   naming alone—therefore separates this diagnostic from the operative gate.
   IB2D-CR02 is superseded as a closed, non-blocking scope note rather than an
   open finding with the non-ledger severity `Owner decision`.
4. IB-2D imports **19** underscore-prefixed upstream symbols, not nine: nine
   from IB-2A and five each from IB-2B and IB-2C. Section 48's parenthetical
   accounts for thirteen and omits six factory-registry predicate helpers.
   Renaming one without updating IB-2D fails loudly with `ImportError`, not
   silently. The coupling is intentional same-package reuse of the exact
   provenance, replay, and process-local factory invariants; publishing the
   factory tokens as a compatibility surface would weaken that boundary.
   IB2D-CR03 is therefore closed as accepted design coupling, not an actionable
   production defect. A future public verification facade may be considered
   if another independent consumer appears, but no widening is justified now.

### 49.4 Retained findings ledger

| ID | Priority | Status | Disposition |
|---|---|---|---|
| IB2D-CR01 | P3 | **Accepted as fixed in `5655759`, with count precision corrected here.** | Nine additive functions pin thirteen independently untested guards and pair-pin the redundant final evidence recheck with its adjacent runtime-fingerprint check. |
| IB2D-CR02 | Note | **Closed; scope observation accepted, owner blocker rejected.** | Exact provisional arithmetic and comparison are present, but retain-all behavior, a non-operative API, hard-false authority, and zero looks keep them inside the previously authorized diagnostic bound. |
| IB2D-CR03 | Note | **Closed as intentional design coupling.** | Nineteen private same-package imports deliberately reuse process-local trust checks. Breakage is loud, and exposing factory tokens would be the worse boundary. |
| IB2D-CCR01 | P3 | **Closed in this record.** | The campaign used 31 unique mutants and 32 executions after the corrected rerun; final unique outcomes are 12 caught and 19 survived. |
| IB2D-CCR02 | P3 | **Closed in this record.** | The guard inventory now distinguishes thirteen genuine test gaps from the redundant evidence guard that is covered only by a combined mutation. |
| IB2D-CCR03 | P3 | **Closed in this record.** | The non-P0-P3 `Owner decision` finding and its inaccurate reading of section 47 are superseded by the exact non-authoritative diagnostic scope. |
| IB2D-CCR04 | P3 | **Closed in this record.** | The private-import count, omitted factory predicates, loud failure mode, and required disposition of a lane-owned open item are corrected. |
| IB2D-N01 | Note | **Confirmed.** | The six individually surviving directions are redundant or unreachable as section 48 describes; the final evidence-hash check is covered as a pair. |
| IB2D-N02 | Note | **Confirmed.** | The 1,265 prior gate and 1,274 corrected gate include the 11-case import-boundary file. |
| IB2D-N03 | Note | **Accepted as environmental.** | The 28-versus-26 warning delta does not change pass, skip, or failure counts. |
| IB2D-N04 | Note | **Accepted.** | The sibling-test imports rely on the repository root being importable; this is a documented repository-level test mechanism, not a current lane failure. |

No P0, P1, or P2 finding arose. No P3 finding remains open in the incoming
Claude range. Earlier lane gates and shared/out-of-lane findings remain
unchanged and were not fixed by inference.

### 49.5 Validation and access accounting

On the exact received tree, the complete thirteen-file Insider suite plus
active-document, module-hygiene, and import-boundary gates passes **1,274**
tests. This reproduces Claude's final lane-gate count. The focused **92** and
**176** results and the five representative red/green mutations are described
above. Claude's complete-suite result—**7,474 passed, 38 skipped, 28 warnings,
0 failed**—is accepted; a duplicate repository-wide run was not required for
this test-and-record-only counter-review. Final active-document, lane-gate,
diff, root, branch, status, and commit checks follow before the local
counter-review commit.

Access remained limited to the local repository, toolchain, the governing
local blueprint, and a Git remote refresh. No SEC or EDGAR endpoint, provider,
credential, licensed row, real filing, outcome, QuantConnect job or process,
broker, operator database, scheduler, deployment, capital, order, or trading
surface was accessed. **Research looks: 0.** Authorized and consumed outcome
looks remain exact integer zero.

### 49.6 Actual continuation gate

IB2D-CR02 does not block acceptance. A separate scope-definition gate blocks
automatic implementation: the authoritative record defines no IB-2E or other
post-IB-2D submilestone. The next named ladder milestone is canonical IB-3
stock event scoring, while full IB-2 remains incomplete because no official
point-in-time security master or durable `qc_symbol_id` exists and official
amendment authentication, completeness, and supersession remain unresolved.
Those shared/data-authority tasks cannot be inferred from this lane.

The owner must therefore choose one bounded continuation before code work:
define a synthetic/offline, zero-authority IB-2 completion contract, or
expressly authorize a coordinated security-master/amendment authority audit.
Codex will not invent IB-2E, start canonical IB-3, access external data, or
make the round's single push until that scope is supplied. This local
counter-review record should be combined with the selected implementation in
that one later push for Claude's next exact-snapshot review.


## 50. Codex counter-review and bounded synthetic IB-3A formula diagnostics (2026-09-09 UTC)

### 50.1 Owner direction and narrow authority interpretation

Section 49 correctly stopped because the ladder named canonical IB-3 next but
the official point-in-time security master, durable `qc_symbol_id`,
authenticated amendment completeness/supersession, ordinary-equity
classification, and canonical identity authorities remained false. The owner
then asked what the IB-2/data authorities meant. Codex explained those exact
gates and stated that the safe next slice would be pure offline formula work,
not canonical IB-2 completion. The owner's following direction was:
**"Implement the next milestone, then push."**

That is treated as express authority for only the bounded slice recorded here:
a synthetic, caller-declared event and caller-declared trading-age
equation-conformance diagnostic. It does not authorize an official security
master, symbol resolution, role normalization, amendment supersession,
calendar construction, canonical filtering, a final stock signal, outcomes,
ETF construction, QuantConnect, provider, broker, deployment, capital, order,
or trading work. This slice is named **IB-3A** only to distinguish it from the
still-blocked canonical IB-3 milestone. It does not claim that IB-2 or IB-3 is
complete.

The exact incoming Claude review range remained
`84c9ebe119a809fb88a1c14bfdadfe09ce83aadf..9a93d09543c8c772a5062bf42d9d01afdbcc2bd9`.
Codex committed its complete counter-review as
`5db0f3d19cdaeda7ef3b29f0a55667d48d3b25f6`, implemented IB-3A as
`17e613d4f58a2ff458c9a9404cc8ac9e7f35e1cc`, and corrected the final
mixed-exponent aggregate bound as
`6c03d7e7c87644e37996dd26457e1f839eeef363`. All work occurred in the
owner-designated `trading_agent__insider_buying` worktree on
`codex/strategy-insider-buying`; no branch, side worktree, merge, rebase, or
force push was created.

### 50.2 Per-commit dispositions

| Commit | Role | Disposition |
|---|---|---|
| `5655759143e2a85e2fadd12270311da09b7adfe3` | Claude IB-2D test correction | **Accepted; no P0-P3 finding.** The additive tests and representative mutations reproduce, as section 49 records. |
| `9a93d09543c8c772a5062bf42d9d01afdbcc2bd9` | Claude IB-2D review record | **Accepted after the four append-only P3 precision corrections in section 49.** No product correction was required. |
| `5db0f3d19cdaeda7ef3b29f0a55667d48d3b25f6` | Codex counter-review record | **Ready for Claude review.** It dispositions every Claude commit and closes every current-lane review item without changing product code. |
| `17e613d4f58a2ff458c9a9404cc8ac9e7f35e1cc` | Codex IB-3A implementation | **Defect found, then accepted after correction in `6c03d7e`.** The initial 272-digit aggregate coefficient cap did not cover the admitted exponent span (IB3A-R08). All other implementation findings were corrected before this commit. |
| `6c03d7e7c87644e37996dd26457e1f839eeef363` | Codex IB3A-R08 correction | **Accepted after independent red/green review; no open finding.** The 774-digit cap is derived from input width, exponent span, and maximum-batch carry, remains below the shared 4,096-digit exact-arithmetic ceiling, and is bound into the numeric-policy hash. |
| This section-50 record commit | Codex authoritative lane handoff | **Ready for Claude review.** It changes only this lane record and does not rewrite sections 48 or 49. |

### 50.3 Implemented behavior

`research/insider_buying/form4_stock_signal_formula_diagnostics.py` adds a
dependency-light offline boundary with these exact properties:

- only factory-created, process-sealed synthetic fixture events are accepted;
  an exact `Form4ProvisionalLotDiagnostics` object is refused before formula
  work, so IB-2D is neither consumed nor promoted;
- one call contains one caller-declared issuer/security/share-class triple;
  source and fixture IDs must be unique and canonical, and duplicate
  caller-declared post-lot owner/security/date keys are refused rather than
  silently summed after the nonlinear logarithm;
- every supplied event produces and retains one contribution, including
  purchase values below `$50,000` and ages above 30 trading days;
- `event_size = ln(1 + purchase_value_usd / 50000)`, freshness is the exact
  product of whole 20-day half-lives and a 50-digit half-even fractional
  half-life projection, and `event_score = event_size * freshness`;
- raw-score inclusion is exactly purchase value `>= 50000` and integer caller
  age `0 <= age_trading_days <= 30`. The raw diagnostic is the exact sum of
  included event scores; at least one event must qualify;
- buyer breadth, the inventory/count of caller-declared role IDs, date breadth,
  and `(total - largest buyer aggregate) / total` dollar breadth are separate
  diagnostics and never score multipliers;
- the result is canonical under input permutation and constructor-replayable;
  events, contributions, breadth, policy, identities, inventory hashes, and
  the raw diagnostic are mutually rebound and type checked;
- the Decimal context is freshly and completely specified at precision 50,
  `ROUND_HALF_EVEN`, fixed exponent limits/capitals/clamp, and explicit empty
  flag/trap sets, independent of caller `Context` and mutable
  `decimal.DefaultContext` state;
- public bounds are 10,000 events, 16 role tokens per event, 128 characters
  per opaque text field, caller age through 10,000, and exact input Decimals
  through 256 coefficient digits and tuple exponent `+/-256`. Separate
  derived/projection bounds preserve valid tiny scores, and the 774-digit
  aggregate width closes the entire admitted input exponent span; and
- `stock_score` is hard `None`. Cross-sectional winsorization/z-scoring,
  ranking, selection, and any consumer remain absent because their population,
  cutpoints, interpolation, denominator, minimum-N, and zero-variance rules
  are not frozen.

The package root explicitly exports the contract. The implementation imports
only stdlib modules, exact Decimal/hash helpers, `CANONICAL_SPEC`, and the
IB-2D type needed for the early refusal. It contains no float literal, dynamic
import, file/network access, provider, outcome, portfolio, QC, execution, ML,
or trading import.

### 50.4 P0-P3 findings ledger and red/green evidence

The IDs below are the durable section-50 inventory; ephemeral reviewer labels
are normalized into this single non-overlapping ledger. Resolved findings are
retained.

| ID | Priority | Status | Finding, correction, and proof |
|---|---|---|---|
| IB3A-R01 | P2 | **CLOSED before `17e613d`** | Identity/result replay accepted value-equal `str` subclasses for five fields. Five new cases were red before exact-type validation and green afterward. |
| IB3A-R02 | P2 | **CLOSED before `17e613d`** | Standalone replay did not cap event claims or per-event role/date cardinality and could admit impossible breadth concentration/value shapes. The captured red run was **117 passed, 3 failed** for count/cardinality; corrected resource and impossible-value cases are included in the final 142. |
| IB3A-R03 | P2 | **CLOSED before `17e613d`** | Two source-distinct rows with the same post-lot owner/security/date key could produce `2 * ln(2)` instead of the required one-event `ln(3)`. A direct pre-fix probe reproduced that split inflation. Final tests refuse both two `$50,000` and two `$30,000` unaggregated shapes before formulas; the module does not aggregate or grant aggregation authority. |
| IB3A-R04 | P2 | **CLOSED before `17e613d`** | A factory-permitted 256-digit Decimal became an identifier-like string and failed the unrelated 128-character projection limit in the full builder. The pre-fix factory-success/builder-refusal reproduced; typed Decimal projection and full-build boundary cases are green. |
| IB3A-R05 | P3 | **CLOSED before `17e613d`** | Caller-declared role tokens and unresolved IB-2 prerequisites were not exhaustively labelled. Provenance is now explicit (`role_ids_are_caller_declared=True`); role normalization, every PIT identity/classification/aggregation gate, canonical score, external/operational authority, and both look counters are exhaustively pinned false/zero. |
| IB3A-R06 | P3 | **CLOSED before `17e613d`** | `Context(...)` inherited mutable `decimal.DefaultContext` traps, so setting `Inexact` before import could refuse a valid age-one event. The subprocess reproduction was red; explicit context flags/traps and the same age-one golden are green. |
| IB3A-R07 | P2 | **CLOSED before `17e613d`** | The input exponent cap was reused for derived values, so a retained `Decimal('1e-256')` event beside one qualifier failed after computing its legitimate tiny score. Separate bounded derived exponents now retain that event through maximum age; both exponent extremes build end to end. |
| IB3A-R08 | P2 | **CLOSED in `6c03d7e`** | `17e613d` used a 272-digit aggregate coefficient cap and rejected two individually admitted included inputs when their exponents aligned into exact 512- or 763-digit totals. Both commit-object cases were red with `REFUSED: breadth total purchase value exceeds the Decimal resource bound`. The derived 774-digit cap and exact-sum oracle make both green; two independent final audits accepted the correction. |

There is no open P0, P1, P2, or P3 finding in the current lane change. One
review suggestion to allow duplicate post-lot keys is rejected: accepting
them would permit nonlinear split inflation. Refusing the shape is a
fail-closed synthetic-input invariant; the module never performs aggregation,
and `lot_aggregation_authorized` remains exact false.

### 50.5 Final validation and immutable evidence

Final corrected tree (`6c03d7e` plus this record change where applicable):

- Python **3.13.15**, pytest **9.1.1**;
- focused IB-3A: **142 passed in 0.76s**;
- complete Insider files plus active-document, module-hygiene, and ML
  import-boundary gate: **1,416 passed in 12.30s**;
- complete repository: **7,616 passed, 38 skipped, 26 warnings, 0 failed in
  411.45s (0:06:51)**;
- whole-repository `compileall` including `research`: **exit 0**; bytecode was
  directed to an isolated `/private/tmp` cache because the existing worktree
  cache directory was not writable under the session sandbox;
- explicit source compilation: exit 0; `git diff --check`: clean; and
- three independent reviews (formula/test, production/replay, and authority
  scope) report no remaining P0-P3 code finding. The final production,
  package, and test SHA-256 values before the record edit are respectively
  `7a820d483cd55a28d03f36bc6b390e2331d668c8180891c44dc568c91c1cd829`,
  `572222d7560ee643250d8f781d4a283ec901597bbe34cb5191458e76b70bbc94`,
  and `e62592f229c1ded57b46e58f6f7a56beea9413cf6968a4b56c8c64cdadf1e5df`.

The complete repository was run twice during the round because the final
aggregate-bound correction changed the product tree after the first pass.
The earlier tree passed 7,614 with the same 38 skips and 26 warnings; only the
final 7,616 result is the completion gate.

No SEC or EDGAR endpoint, filing, provider, credential, licensed row, outcome,
QuantConnect job/upload/process, ETF data, broker, operator database,
scheduler, deployment, capital, order, or trading surface was accessed.
**Research looks: 0.** Authorized and consumed outcome looks are exact integer
zero on every public event, contribution, breadth, identity, and result.

### 50.6 Residual gates and milestone status

IB-3A is complete only as synthetic formula-conformance evidence. The
following remain unresolved and block any canonical IB-2/IB-3 completion:

- official point-in-time issuer, reporting-owner, security/share-class, and
  transaction identities;
- official security-master compatibility and durable `qc_symbol_id` mapping;
- authenticated amendment links, complete coverage, and supersession;
- ordinary-equity classification and authorized post-lot aggregation/filtering;
- an authoritative trading calendar and age/availability-session mapping;
- an authorized role taxonomy rather than caller-declared opaque IDs; and
- frozen cross-sectional winsorization/z-score semantics and a canonical
  eligible-stock population.

No later IB milestone may infer those authorities from this diagnostic. No
outcome cell, permanent look, ETF construction, QC processing, paper/live
deployment, or trading action is authorized.

### 50.7 Copyable Claude review handoff

Claude's next action on the same long-lived branch is:

1. fast-forward the existing `trading_agent__insider_buying` worktree to the
   exact pushed `codex/strategy-insider-buying` head and verify no alternate
   worktree or branch is used;
2. review every commit in
   `9a93d09543c8c772a5062bf42d9d01afdbcc2bd9..PUSHED_HEAD`, with an explicit
   per-commit disposition for `5db0f3d`, `17e613d`, `6c03d7e`, and the
   section-50 record commit;
3. independently reproduce section 49's Claude-commit counter-review, the
   exact 50-digit formula goldens, inclusive threshold/age routing, retained
   excluded rows, post-lot duplicate-key refusal, breadth separation,
   constructor replay, resource edges, policy hash, hard-`None` stock score,
   authority matrix, and zero looks;
4. give every finding a P0-P3 disposition, retain resolved findings in this
   ledger, and apply any current-lane correction with red/green proof; document
   shared/project-wide findings without changing shared files; and
5. update only this lane record, commit on this same branch, and make the
   review round's one push. Codex then counter-reviews every Claude commit
   before any later milestone.


## 51. Claude review - IB-2D counter-review and bounded synthetic IB-3A formula diagnostics (2026-09-10 UTC)

Reviewer: Claude, in the lane worktree `trading_agent__insider_buying` on
`codex/strategy-insider-buying` (owner's Mac, Python 3.13.15, pytest 9.1.1).
No branch, worktree, fork, or handoff was created or switched to. The remote
tip was verified as `8f615572fd920c563d79f7a561d098dd416533d5` and the local
branch was already exact at it. Range reviewed in order: `5db0f3d`
(counter-review record), `17e613d` (IB-3A implementation), `6c03d7e`
(aggregate-bound correction), `8f61557` (record). Four commits, zero merges;
every changed path is lane-owned.

### 51.1 Commit dispositions

| Commit | Disposition | Basis |
|---|---|---|
| `5db0f3d` counter-review of the IB-2D review | **Accepted, no issue found.** | Documentation only. All four corrections to section 48 were independently verified (51.2), including two genuine errors of this reviewer. Its continuation gate was honoured: the owner, not Codex, supplied the scope that authorized the next slice. |
| `17e613d` bounded synthetic IB-3A | **Accepted after test-only correction.** | Lane-owned only. The formulas, routing, breadth, bounds, and authority matrix were independently reproduced (51.3, 51.4). Twelve guards had no test sensitivity (IB3A-CR01, fixed in `94ea25c`); no production defect was found beyond the one Codex had already corrected in `6c03d7e`. |
| `6c03d7e` IB3A-R08 aggregate bound | **Accepted, no issue found.** | The defect was real and reproduced: the exact totals for both committed cases need 512 and 763 coefficient digits, so the old 272-digit cap refused two individually admitted inputs. The derived 774-digit cap is exactly one digit above the 773 required by the admitted exponent span plus batch carry, and sits below the shared 4,096-digit ceiling. The numeric-policy hash recomputes to the committed constant. |
| `8f61557` record | **Accepted.** | Every material claim reproduces: 142 focused, 1,416 lane/boundary, 7,616 repository, compileall exit 0, and both recorded production and package SHA-256 values match the blobs at `6c03d7e` exactly. One record-precision item is recorded as IB3A-CR02. |

### 51.2 Section-49 corrections to section 48, independently verified

| Codex correction | Independent result |
|---|---|
| 31 unique mutant directions and 32 executions; final unique outcome 12 caught / 19 survived | **Accepted.** My section 48 reported the execution count as the direction count. The invalid mutation was corrected and re-run, which is a thirty-second execution of a thirty-first direction. |
| Thirteen independently untested guards plus one redundant evidence-recheck pair, not fourteen independent guards | **Accepted.** The final evidence-hash recheck survived its own individual mutant even after my pins and was only killed by the combined mutant, so it is defence in depth pinned as a pair. The same distinction is applied to IB-3A in 51.4. |
| IB2D-CR02 closed as a non-blocking scope note; its owner blocker rejected | **Accepted.** Section 47.7 prohibits "authorized aggregation or `$50,000` gate" and section 47.4 disclosed the exact group sum and post-grouping comparison, so the diagnostic was inside the handed-off bound. Retain-all behaviour, no operative consumer, hard-false authority, and zero looks separate it from the operative gate. `Owner decision` was also not a P0-P3 severity. The owner subsequently engaged the scope question directly and supplied the next direction. |
| Nineteen private upstream imports, not nine, and a rename fails loudly | **Accepted; both were genuine errors of mine.** An AST count gives exactly 19 (nine from IB-2A, five each from IB-2B and IB-2C). Renaming one imported private name produces `ImportError: cannot import name '_evidence_observation_hash'` at import time, so the failure is loud, not silent as section 48 stated. |

### 51.3 Material claims reproduced

- **Numeric policy hash.** `hash_payload(_numeric_policy_payload())` recomputes to the committed `56eddf2f...ac2e`. The 33/31 character split in the test literal is cosmetic; the concatenation is a valid 64-character digest.
- **Aggregate bound.** The admitted input envelope is 256 coefficient digits with exponent in `[-256, +256]`, so an exact sum spans from `10**511` down to `10**-256`, needing 768 digits, plus at most 5 carry digits for 10,000 addends: 773. The derived cap is 774 and the structure `D + 2E + len(str(N)) + 1` always leaves exactly that one-digit margin. 774 < 4,096.
- **IB3A-R08 was real.** The two committed cases produce exact totals of 512 and 763 coefficient digits; both exceed the old 272-digit cap, and both now match an independent `exact_decimal_sum` oracle.
- **Formulas.** An independent oracle that evaluates `exp(-ln(2) * age / 20)` directly, without the half-life split, matches `event_size` exactly on every probe and matches freshness to within last-digit rounding at 50 digits. Inside the frozen context, freshness equals `Decimal("0.5") ** (age // 20)` exactly at ages 0, 20, 40, 200, and 10,000, and `event_score` equals `event_size * freshness` on every probe.
- **Context isolation.** Building under ambient contexts of precision 3, 9, and 200 with `ROUND_UP`, `ROUND_FLOOR`, and `ROUND_CEILING` yields byte-identical payloads.
- **Routing.** `49,999.99` is excluded and retained, `50,000` is included, age 30 is included, and age 31 is excluded and retained.
- **Breadth.** Single buyer gives dollar breadth exactly `0`; two equal buyers `0.5`; a concentrated pair `0.25`; three equal buyers the 50-digit `0.666...67`. Buyer, role, and date breadth are independent inventories.
- **Scope.** A keyword sweep for security master, `qc_symbol`, supersession, canonical filter, deduplication, winsorization, z-scoring, ranking, seed selection, ETF, QuantConnect, broker, deployment, order, portfolio, and outcome surfaces matches only hard-false gate declarations, docstring negations, and the `raw_stock_score_diagnostic` name. `stock_score` is hard `None`; there is no hidden scoring stage. All 27 authority flags are `False` and both look counters are `0` on the result, identity, event, contribution, and breadth. On every object except the identity those flags are class properties, so they cannot be shadowed per instance; the identity carries them as fields, which is why `_require_zero_authority` exists there.

### 51.4 Adversarial verification

Sixty-four targeted mutants on the production module, one neutralised guard
each, the focused file re-run after each, module restored from a byte-exact
in-memory copy in a `finally` block and re-verified byte-identical.
**Pushed tree: 39 caught, 25 survived, 0 invalid.** Ten further combined
mutants separated mutually redundant pairs from genuine gaps. Every survivor
was then classified.

Caught on the pushed tree (39) covered the size scale and `1 +` offset, the
half-life divisor and base, the fractional-half-life sign and branch, the
event-score product, both threshold and both lookback comparisons in both the
builder and the constructor, the two post-lot key components, the raw-score
inclusion filter in both places, the dollar-breadth numerator, largest-buyer
selection, per-buyer aggregation, breadth inclusion, the impossible-value and
role/date cardinality guards, the authority value and look-counter checks,
caller-declared role provenance, projection depth/node/cycle bounds, the
aggregate cap, the event-count and age bounds, the role inventory, the Decimal
type and bound checks, all four hash-ID bindings, the text validator, and the
`stock_score` guard.

**Twelve genuine untested guards, now pinned in `94ea25c` and each
mutation-verified:**

| Guard | Why the existing suite missed it |
|---|---|
| Explicit Decimal `flags=[]` / `traps=[]` | The IB3A-R06 regression sets `DefaultContext.traps[signal] = False` for every signal, which is the harmless direction. With the arguments removed and `Inexact`/`Rounded` trapped before import, a valid age-one event is refused with "cannot be evaluated deterministically", yet all 142 tests passed. The new subprocess regression traps those signals and asserts the correct freshness. |
| Sealed-event fingerprint comparison | `test_fixture_process_seal_detects_equal_decimal_representation_change` forges a *new* object, so it is refused by `registered is None`. For an in-place change on a genuinely registered event the fingerprint comparison is the only guard, because `decimal_text` canonicalizes `50000.0` to `50000` and the `fixture_event_id` binding still holds. Removing it provably accepted the mutated representation. |
| Contribution routing consistency | No test forged a contribution at all; a combined mutant with the result-level replay also survived. |
| Contribution replay from fixture events | Same: pinned with a self-consistent contribution that describes a different event. |
| Breadth replay from included events | Combined mutants with the breadth count binding, the buyer bound, and the identity replay all survived. |
| Identity replay | Pinned with a self-consistent identity carrying a different issuer CIK. |
| Canonical event order in replay | Pinned by reversing events and contributions together so only the order clause can fire. |
| Result raw-score binding | Combined mutant with the identity replay survived. |
| Result stock-key binding | Two forged fields. |
| Breadth count-to-inventory binding | Three forged counts. |
| Breadth buyer-count bound | Forged included-event count. |
| Identity count consistency | Three forged count shapes. |

**Thirteen survivors classified as redundant or unreachable, not gaps:**
the formula finite/non-negative guard (unreachable for factory-validated
inputs, which always yield non-negative finite values); the dollar-breadth
interval guard (its own preconditions already force the quotient into
`[0, 1)`); the authority boolean *type* check (any value that is not the
singleton `False` is already refused by the value check, and `False` is
already a `bool`); the projected-Decimal text bound (the widest value the
digit and exponent caps admit renders in 1,798 characters against a 2,048
cap); the IB-2D early refusal (the following exact-tuple check still refuses
the object, so behaviour is preserved and only the message differs); the
frozen-policy check inside `_event_formula` (the public builder calls
`_require_frozen_policy` first); the post-build fixture recheck (the result
constructor's own `_require_factory_fixture_event` loop catches any mutation
before it, making the later loop mid-call defence in depth); the
contribution/event alignment clause (the reorder direction is caught by the
contribution replay, and the combined pair is now pinned); and four
mutually-redundant builder/replay pairs - the duplicate post-lot key, source
and fixture uniqueness, the single-stock-key rule, and purchase-value
positivity - whose combined mutants are all caught.

### 51.5 Findings

| ID | Sev | Status | Issue |
|---|---|---|---|
| IB3A-CR01 | P3 | **FIXED in `94ea25c`** | Twelve guards could be deleted with the focused file green (51.4). Thirteen additive tests (20 cases) pin them, each mutation-verified, and six previously surviving combined pairs are now caught. The two substantive cases are the IB3A-R06 trap isolation, whose regression exercised the harmless direction, and the sealed-event fingerprint, whose regression was masked by an earlier clause in the same condition. Test-only; no production module changed. |
| IB3A-CR02 | P3 | OPEN - record precision | Section 50.4 cites pre-commit red/green evidence for IB3A-R01 through R07, including an exact "117 passed, 3 failed" run. Those corrections were squashed into `17e613d` before it was committed, so none of that evidence is reproducible from the repository; the final guards were instead verified here by mutation. Recommend future rounds cite a reproducible probe or the exact mutation, as sections 46 and 48 do, rather than a transient pre-commit run. |
| IB3A-N01 | note | recorded | Evaluating freshness as whole half-lives times a fractional projection differs from evaluating `exp(-ln(2) * age / 20)` directly by at most 2.4e-48 relative (measured at age 10,000), i.e. last-digit rounding at 50 digits. This is disclosed by `FORM4_STOCK_SIGNAL_FRESHNESS_EVALUATION` and bound into the policy hash, so the evaluation order is contractually frozen. Not a defect; noted because a consumer reading only the formula string could implement the direct form. |
| IB3A-N02 | note | recorded | The thirteen classified survivors above are redundant or unreachable with the stated proofs, and are retained as defence in depth. |
| IB3A-N03 | note | recorded | 28 warnings on this Mac against the recorded 26; pass, skip, and failure counts match exactly. |
| IB3A-N04 | note | recorded | `_runtime_value` falls back to `repr()` for unexpected types, which would weaken the fingerprint, but `__post_init__` type-checks every field before any fingerprint is taken, so the fallback is unreachable through the public surface. |

No P0, P1, or P2 finding. `IBSH-CCR01..07` and the earlier lane debts are
unchanged and were not fixed here. Every residual gate listed in section 50.6
is confirmed open.

### 51.6 Validation

Pushed tree `8f61557`, before any change:

- Complete repository suite: **7,616 passed, 38 skipped, 28 warnings, 0 failed in 485.90s (0:08:05)**.
- Focused IB-3A **142 passed**; fourteen Insider files plus active-document, module-hygiene, and ML import-boundary **1,416 passed**. Both reproduce Codex's figures exactly.

Final tree (`94ea25c` plus this record):

- Focused IB-3A **162 passed**; lane/boundary gate **1,436 passed in 11.97s**.
- Complete repository suite: **7,636 passed, 38 skipped, 28 warnings, 0 failed in 440.88s (0:07:20)**.
- Whole-repository compileall (the CLAUDE.md set plus `research`) exit **0**; `git diff --check` clean.
- Mutants: 64 targeted plus 10 combined on the pushed tree; the twelve pinned survivors re-run after correction, all caught, and all six previously surviving combined pairs now caught. Every mutated module restored byte-identical, confirmed by the harness and by `git status`.

No SEC, EDGAR, vendor, QuantConnect, credential, licensed row, outcome,
broker, operator-database, scheduler, deployment, capital, or trading access.
**Research looks: 0.** Authorized and consumed outcome looks remain exact
integer zero on every public object.

### 51.7 Quality rating

**9 / 10**, held. IB-3A is careful work: the Decimal context is fully
specified rather than inherited, the half-life decomposition keeps whole
half-lives exact, multiplying by `0.00002` avoids an inexact division by
50,000, every excluded row is retained, breadth is kept structurally separate
from the score, the aggregate width is derived rather than guessed, and the
refusal of unaggregated duplicate keys is the correct fail-closed answer to
the nonlinearity of `ln`. Codex also found and corrected a real P2 of its own
in `6c03d7e` before handing off.

It is not raised because the recurring defect shape persists into a sixth
consecutive milestone: correct guards with no test that fails when they are
removed, twelve here. Two of them are worse than the usual pattern because
the tests that exist are named for exactly those directions but do not
exercise them: the R06 regression disables every trap instead of enabling
one, and the seal regression forges a new object so an earlier clause fires
first. A guard whose test passes for the wrong reason is more costly than an
unguarded line, because the record then claims coverage that is not there.
The lane would benefit from making every new refusal branch carry a mutation
proof at implementation time, which is the checklist item recommended in
sections 37, 46, 48, and now here.

### 51.8 Authority, residual gates, and next step

Every authority gate remains closed. IB-3A is synthetic equation-conformance
evidence over caller-declared events and a caller-declared trading age. It
establishes no official security master, `qc_symbol_id`, authenticated
amendment supersession, point-in-time identity, ordinary-equity
classification, trading calendar, or authorized role taxonomy, and it adds no
canonical filtering, deduplication, authorized aggregation, operative
`$50,000` gate, canonical stock score, cross-sectional normalization, seed
selection, outcome, ETF, QC, deployment, capital, broker, or trading
capability. Full IB-2 and canonical IB-3 remain incomplete and blocked on
those data authorities.

Review commits on this lane: test correction `94ea25c` and this record
commit. Next authorized step: Codex counter-reviews both. No milestone was
started and none is authorized by this review.
