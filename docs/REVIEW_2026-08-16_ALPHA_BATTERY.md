# Independent review — alpha battery and three-universe rerun

Date: 2026-08-16
Reviewer: Codex
Remote reviewed: `origin/main`
Base: `f63fe2cb30aa904dec131962a133e1058185427c`
Exact submitted head: `3d58f6b097610cb5df1f088e8fe0308ffcbf8161`
Review branch: `codex/review-alpha-battery-20260816`
Product/test correction: `124192ff3e29c3fc62f0c9e8bf95b9aadf216915`
Status: **Accepted as preserved exploratory work only after correction; all
submitted numerical conclusions are invalidated pending a clean rerun. Not
pushed, merged, deployed, or promoted.**

## Scope and method

Review began from the fetched, pushed `origin/main` head after PR #236. The
literal range `f63fe2c..3d58f6b` contains three Claude commits and the merge;
each was read separately. The merge was compared with both parents. It adds
Claude's branch tree to the already-merged prior Codex review and has no hidden
product conflict resolution, but the canonical handoff remained the older
pre-merge version and became semantically false.

The review treated the committed JSON and Markdown reports as claims to be
reproduced, not as ground truth. Five synthetic regressions were first run red
against the submitted implementation; a sixth pins refusal of pre-correction
membership caches. No broker, account, operator database, scheduler, epoch, or
network data source was accessed.

## Commit-by-commit dispositions

| Commit | Disposition | Evidence and issue mapping |
|---|---|---|
| `db0045a` | **Accepted after documentation correction.** | The preregistration genuinely precedes the result commit and conservatively retains 105 declared looks. Its implementation assumptions did not guarantee a resolvable test, however; ABR-001 records that the later runner's minimum attainable p-value exceeded the frozen gate. The addendum preserves rather than rewrites the frozen plan. |
| `4de88d0` | **Accepted only as an invalidated exploratory record after correction `124192f`.** | ABR-001 made “zero clear” inevitable by construction, and ABR-002 understated long/short trading costs. The original artifact remains auditable but cannot support significance or net-cost conclusions. |
| `046afc3` | **Accepted only as an invalidated exploratory record after correction `124192f`.** | ABR-003 through ABR-006 invalidate the claimed point-in-time universe, survivorship percentage, residual/industry results, and automatic robustness labels. Corrected code requires actual filing dates and unadjusted screening prices, refuses stale caches and unavailable industry inputs, and labels the panel non-point-in-time. A clean data build and rerun remain required. |
| `3d58f6b` | **Accepted after product and documentation correction.** | PR #236 contains the alpha branch as its second-parent contribution and no hidden product conflict resolution. It inherits ABR-001 through ABR-006. ABR-007 repairs the canonical handoff, which still said main was `006a9d5`, the prior review was local-only, and the alpha branch was unreviewed local work after all three statements had become false. |

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Correction and verification |
|---|---|---|---|---|---|---|---|
| ABR-001 | P2 | Closed in code; historical result invalidated | `4de88d0` | `stationary_bootstrap_p`, first result/artifact | With 2,000 draws and the add-one estimator, the smallest possible p-value was 0.00049975, above the declared 0.00047619 gate. No specification could ever pass, so “zero clear” was not an empirical result. | The artifact contains the exact floor repeatedly; the regression failed red at 2,000 draws. | Default is 10,000 and uses an actual stationary restart process, giving resolution below the gate. Regression green. A clean rerun is still required. |
| ABR-002 | P2 | Closed in code; historical result invalidated | `4de88d0`, `046afc3` | both portfolio builders | Turnover compared only the set of names held. A security flipping from long to short remained in the set and registered zero turnover, understating costs and invalidating net-Sharpe/cost-destruction claims. | A 20-name two-date complete side flip returned 0.0 red. | Turnover is now half the absolute signed-weight change; the same flip returns 1.0 green. |
| ABR-003 | P2 | Closed in code; historical result invalidated | `046afc3` | universe data/build | Market cap multiplied split-adjusted historical close by unadjusted reported shares, while fact availability was guessed as period end + 90 days rather than read from the SEC `filed` field. Both can change membership. | Synthetic $40 raw/$4 adjusted price crossed the $10B screen only under the correct raw price; an actual May 15 filing became usable June 29 in submitted code. Both regressions failed red. | Downloads retain adjusted closes for returns and raw closes for cap/ADV screens; facts use their actual filing dates and preserve later amendments. Both regressions green. |
| ABR-004 | P2 | Closed in code/docs; historical result invalidated | `046afc3` | snapshot/audit/report | The reported “70.2% survivorship loss” counted historical SEC filers before price, cap, ADV, history, venue, or security-type eligibility could be checked. It is a current-ticker/price coverage gap, not measured survivorship loss. | Loop order increments the submitted denominator before every universe screen; the artifact preserves the legacy fields. | Runtime names and audit metadata now say candidate-filer coverage gap; survivorship is explicitly present but unmeasurable here. Original JSON is banner-invalidated rather than silently rewritten. |
| ABR-005 | P2 | Closed by refusal; historical result invalidated | `046afc3` | residual and industry-adjusted universe paths | Each ticker's latest size bucket was used throughout all history as an “industry” label. This both leaks future capitalization and does not implement an industry adjustment. Residual results were invalid as well as the acknowledged industry-reversal cell. | `_sector_proxy` selected `drop_duplicates(... keep="last")` before building every historical score. | Industry-dependent specifications now refuse until point-in-time industry data exists; the retained stricter declared denominator is not loosened. |
| ABR-006 | P3 | Closed | `046afc3` | `classify` | The code called 0.27/0.02/approximately 0.00 “ROBUST”; the report manually overrode its own known defect but merged the defective classifier. | Focused classifier regression failed red with `ROBUST`. | Conservative magnitude/degradation rules return `LARGE-CAP DEPENDENT`; regression green. |
| ABR-007 | P3 | Closed in documentation | `3d58f6b` | `SESSION_HANDOFF`, Action Plan | The canonical handoff was not textually conflicted, but it semantically retained the pre-PR #234 state: wrong main head, wrong availability, and wrong alpha-branch status. | Fetched `origin/main` is `3d58f6b`; prior review `dae34d0` is reachable through `f63fe2c`; alpha work is merged through PR #236. | Current topology, exact ranges, dispositions, invalidation, validation, and next step are rewritten in the canonical documents. |

Issue summary: **0 P0, 0 P1, 5 closed P2, 2 closed P3, 0 open code
issue.** A clean real-data rebuild/rerun is required before any research
result can be reconsidered; that is remaining evidence work, not an open code
defect.

## Functional and safety disposition

The first preregistration is useful and properly ordered. The runner and both
artifacts are not valid evidence. The corrections prevent the same silent
failure modes on a future run: the statistical test can cross its threshold,
turnover sees side changes, universe screens use internally compatible prices
and shares, historical facts use verifiable availability, old caches refuse,
unavailable industry inputs remain unavailable, and output no longer claims a
point-in-time universe or measured survivorship.

Nothing was added to the research registry, mandate, policy, proposal,
approval, risk, execution, broker, scheduler, or evidence-epoch paths. No
signal is confirmed and no result authorizes a trade, allocation, deployment,
or further alpha selection.

## Validation

- Submitted-code reproduction: **5 focused regressions failed**, one for each
  independently confirmed code class (resolution, side-flip turnover, filing
  availability, raw-price market cap, classifier).
- Corrected focused research/backtest/cross-sectional set: **112 passed**.
- Corrected reviewer file: **10 passed**; the additional cases reject invalid
  bootstrap draw counts and stale membership caches.
- Final full suite: **4,061 passed / 0 failed / 25 known dependency warnings
  in 717.98 seconds** under repository Python 3.13.14.
- Active-document consistency: **30 passed**. Full compilation, three JSON
  artifact parses, and `git diff --check`: clean.

## Remaining scope

Do not reuse the old price or membership cache. Rebuild under universe schema
2, then perform a fresh preregistered run. Even after that, today's ticker map,
yfinance price history, absent delisted returns, absent historical venue and
security-type identity, and absent point-in-time industry data mean the panel
is exploratory and not survivorship-free. The corrected code intentionally
does not manufacture an answer to those data limitations.
