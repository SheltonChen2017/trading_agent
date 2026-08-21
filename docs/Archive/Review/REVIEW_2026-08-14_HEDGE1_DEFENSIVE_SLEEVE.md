# Codex independent review — HEDGE-1 defensive sleeve

Date: 2026-08-14

Reviewer: Codex

Implementation base: `1babbcf`

Submitted implementation: `1f60ebf`

Submitted integration merge: `0e5dadb`

Mainline merge: `17be33b` (PR #223)

Review branch: `codex/review-hedge1-defensive-sleeve-20260814`

Product/test correction: `46e1248`
Final disposition: **accepted after correction**

## Scope and method

This review started from the exact merged mainline tree at `17be33b` and
covered every HEDGE-1 commit, the complete implementation diff, its tests,
configuration, Streamlit surface, mandate text, action plan, and session
handoff. The review traced proposal generation into the shared allocation
planner and the existing approval/execution boundary, then generalized across
exact broker fields, pending/open orders, incomplete multi-instrument baskets,
public input normalization, stale UI binding, and evidence-epoch lineage.

The submitted focused suite passed **51 tests**. Eleven regression failures
were then demonstrated before their corrections: nine in the first combined
red run, one standalone unaffordable-leg case, and one standalone zero-value
holding case. No broker request, order, database mutation, deployment,
scheduler change, epoch transition, funded-account access, or live-trading
action occurred.

## Commit-by-commit disposition

| Commit | Type | Disposition | Result |
|---|---|---|---|
| `1f60ebf` | Claude implementation, tests, UI, configuration, and records | **Accepted after correction** | The owner-directed long-only, equal-weight, proposal-only design is useful and preserves typed approval. Five material failure directions and three minor numeric/documentation defects required correction. |
| `0e5dadb` | Merge of `origin/main` into HEDGE-1 | **Accepted after correction** | The conflict resolution was limited to the Action Plan and Session Handoff and did not damage product code, but it retained incorrect epoch/deployment language and a pre-merge topology. |
| `17be33b` | PR #223 merge to `main` | **Accepted after correction** | Its tree is byte-identical to `0e5dadb`; it introduced no additional conflict change. The inherited HEDGE-1 findings are closed by `46e1248` and the accompanying records. |
| `46e1248` | Codex product/test correction | **Accepted** | Enforces the sleeve boundary, exact inputs, pending exposure, and complete-basket contract, and adds generalized regression guards. |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| HEDGER-001 | P2 | Closed | `1f60ebf` | `assistant/hedge_sleeve.py` | The public evaluator accepted any ticker, so `AAPL` could be relabeled and sized as a configured hedge even though the UI showed only the recorded sleeve. | A direct `tickers=["AAPL"]` regression returned a usable report on the submitted behavior. | Configuration was presented as the authoritative instrument set; an internal caller must not bypass that boundary. | Normalize text tickers and refuse every name outside `HEDGE_SLEEVE_TICKERS`. | The allowlist regression failed before correction and passes after it. |
| HEDGER-002 | P2 | Closed | `1f60ebf` | `assistant/hedge_sleeve.py` | A malformed authoritative `market_value_exact` silently fell back to a rounded float, and a positive holding with exact value zero was counted as no exposure. Both paths can understate the sleeve and oversize a buy. | Separate corrupt-exact and zero-value regressions reproduced both paths. | Exact broker text is authoritative; corrupt or impossible selected-holding values must fail closed in the smaller, under-hedging direction. | Do not fall back once an exact field is present; require positive exact quantity and market value for a held selected ETF. | Both regressions pass on `46e1248`. |
| HEDGER-003 | P2 | Closed | `1f60ebf` | `assistant/hedge_sleeve.py`, `scripts/personal_assistant_ui.py` | One missing price was dropped and its share redistributed; one unaffordable whole-share leg was silently omitted while other proposals were returned. The result was not the basket the owner selected. | Submitted behavior reweighted the surviving three names to 33.3%; a high-priced BTAL produced only the affordable legs. | Omitting a leg changes the chosen defensive position and conflicts with the module's no-partial-result contract. | Require a usable price and valid minimum quantity for every selected leg; otherwise refuse the whole basket. Disable the UI action while any selected price is unavailable. | Module and AppTest regressions failed before correction and now pass. |
| HEDGER-004 | P2 | Closed | `1f60ebf` | `assistant/hedge_sleeve.py`, Hedging page | Target sizing ignored pending hedge buys and still sized when open-order data or a selected pending order's value was unavailable. This could prepare a duplicate amount above the stated target. | A known $400 SH pending buy left the original $1,000 gap; unavailable/unknown working-order cases still returned proposals. | A target gap is not measurable without existing working exposure; the safe direction is refusal or subtraction, not another full-size basket. | Derive pending buy values from the snapshot, subtract known selected values from the gap, report projected weight, and refuse unavailable or unknown selected pending exposure. | Three pending/open-order regressions failed before correction and pass after it. |
| HEDGER-005 | P3 | Closed | `1f60ebf` | Hedge generator and Streamlit price helper | Exact shortfall and recorded-close values were converted to binary floats, and `100 / 3` float weights could exceed the stated total by representation error. | Generalized numeric-path inspection found conversions before the shared planner. | The repository requires Decimal at authoritative money boundaries; avoid introducing avoidable rounding before sizing. | Keep shortfall, recorded closes, and equal weights as Decimal until the existing planner's presentation fields. | Focused and adjacent suites pass with Decimal inputs. |
| HEDGER-006 | P2 | Closed | `1f60ebf`, `0e5dadb` | `docs/operations/MANDATE.md`, `docs/SESSION_HANDOFF.md` | Records claimed unchanged mandate/policy fingerprints meant HEDGE-1 had no deployment-closes-the-epoch consequence. A deployment also changes `code_commit`, so that instruction could invalidate the active evidence lineage. | A document regression matched the exact false exemption. | Operational lineage is safety-critical durable state; stable policy and mandate hashes do not authorize a code change inside an active epoch. | State that epoch-005 is unchanged only because HEDGE-1 is not deployed and any later deployment closes it. | The documentation regression passes on the final records. |
| HEDGER-007 | P3 | Closed | `0e5dadb`, `17be33b` | Action Plan, Session Handoff, active-document tests | After PR #223, both records still called `85338fc` current main and said HEDGE-1 was not merged. The previous guard missed the row because it did not contain the feature commit hash. | `origin/main` resolved to `17be33b`; the new topology test failed against both records. | A stale handoff can send the next agent to the wrong review state. | Update both records and add a generic parse-and-compare guard for their declared current mainline hash. | The active-document suite passes on the final records. |
| HEDGER-008 | P3 | Closed | `1f60ebf` | Module docstring and user guide | The module said it did not create or size anything although its public generator did both; the guide described dropping unpriced legs. | Direct prose/code comparison. | Contradictory safety descriptions make the actual failure direction hard to audit. | State that the module creates/sizes but never approves/submits, and document the complete-basket refusal. | Prose inspection plus focused tests. |

Issue total: **0 P0 / 0 P1 / 5 P2 / 3 P3; all closed; 0 open**.

## Retained design and limits

- The target is an owner-entered, per-run UI value, not durable policy and
  not a project recommendation.
- The configured long-only ETF sleeve is split equally. The review did not
  claim that equal weights are optimal or that the basket reduces drawdown.
- Proposal generation does not approve or submit. Each leg still needs the
  typed approval phrase and a fresh execution-gate pass; there is no
  submit-all control and no hedge sell generator.
- Options, futures, short selling, automatic rebalancing, and live execution
  remain out of scope.
- No backtest or prospective evidence establishes protection, profit, or
  suitability. Software tests establish only the program behavior.

## Validation

Authoritative environment: `C:\git\trading_agent_venv`, Python 3.13.14,
Streamlit 1.60.0, Windows. The repository-local `.venv` executable was not
launchable in this restricted session, so the project-configured shared
environment with the same pinned versions was used.

- Submitted HEDGE-focused tests: **51 passed**.
- Red-before-green evidence: **9 failed** in the combined new-regression run,
  plus **1 failed** unaffordable-leg and **1 failed** zero-value regression.
- Corrected HEDGE module and UI: **59 passed**.
- Corrected HEDGE plus adjacent allocation, portfolio, execution, and UI:
  **165 passed** in 69.86 seconds.
- Final full settled tree: **3,853 passed / 0 failed / 25 known dependency
  warnings** in 729.21 seconds (12:09).
- Repository `compileall`: clean.
- Final documentation-focused suite: **94 passed** in 8.41 seconds.
- `git diff --check`: clean before the correction commit and after the final
  records update.

## Operational consequence

HEDGE-1 is merged development code but has not been deployed. The operational
runtime remains frozen at `752d3b7` in active `paper-epoch-005`, under the
owner's 2026-08-14 instruction to leave it unchanged for 60 days. Although
HEDGE-1 changes neither mandate nor policy fingerprint, deploying a new code
commit changes epoch lineage and closes the active epoch. This review does not
authorize a push, deployment, scheduler change, database mutation, epoch
roll, funded-account access, or live trading.
