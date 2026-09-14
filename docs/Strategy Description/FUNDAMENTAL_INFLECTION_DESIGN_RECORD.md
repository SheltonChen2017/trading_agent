# Fundamental Inflection Alpha - design and session record

Prepared: 2026-09-14 by Codex.

Status: **FOUR-VERSION DESIGN CANDIDATE PREPARED; INDEPENDENTLY UNREVIEWED.
NO STRATEGY IMPLEMENTATION OR EMPIRICAL RESULT.**

## 1. Owner scope and current artifacts

The owner requested a market-alpha strategy based on the preceding small-cap
growth/valuation/profitability/cash-flow/catalyst screen, following the
existing Analyst Revisions, Insider Buying and Short Interest design pattern.
The four requested expressions are balanced ETFs, leveraged ETFs, direct
stock rotation and leveraged stock rotation, with a specified hierarchy of
after-cost benchmark superiority.

The owner first selected drawdown limits of 15% / 25% / 20% / 30%, then
explicitly allowed higher acceptable drawdowns for riskier versions,
especially leveraged versions. Codex applied that later direction as proposed
limits of **15% / 35% / 25% / 40%**. The exact revised numbers are design
assumptions, not a claim that the owner supplied or froze those values.

- Design source:
  [Four-version blueprint](FUNDAMENTAL_INFLECTION_ALPHA_FOUR_VERSIONS_BLUEPRINT_EN.md).
- Reading edition:
  [24-page PDF](../../output/pdf/FUNDAMENTAL_INFLECTION_ALPHA_FOUR_VERSIONS_BLUEPRINT_EN.pdf).
- PDF SHA-256:
  `349a313b47838ee5033f90fff32a8be31d173f51bfb8d970ff7f8656ec045ebe`.
- PDF size: 145,298 bytes; 24 pages; 20 section bookmarks.

The Markdown source governs this unadopted design; PDF disagreements must be
corrected before a future freeze. Neither document is an implementation or a
reviewed-spec registry entry.

## 2. Repository snapshot and scope boundary

- Repository: `https://github.com/SheltonChen2017/trading_agent` (repository
  identity from the existing project context; no remote operation in this round).
- Exact initial HEAD and local `origin/main`:
  `dd6d1b897215946dd2e0ed80f3512a7798637dac`.
- Local design branch:
  `codex/fundamental-inflection-four-versions-20260914`.
- Generic workflow applies. This is not one of the named same-branch
  implementation/review exceptions. No push, PR or merge is performed.
- Existing untracked `.tmp_tpr_counterreview_edit_20260831/` and `tmp/` remain
  untouched. Git also reports pre-existing access warnings for several
  scratch directories and the user's global ignore file; no cleanup or
  permission changes were attempted.

This session adds only the new blueprint, its reading edition and this
associated record, followed by a narrow generic Session Handoff update.
It does not change the Action Plan's sequencing, any existing lane, common
family allocation, reserved holdout, application policy or executable code.
No feature-completion entry is made because required independent review has
not occurred.

## 3. Design choices

- One fixed fundamental score, explicit OR branches within AND eligibility
  gates, quarterly ROE semantics, all-in cash accounting and documented runway.
- The undefined negative-to-positive ROE percentage-growth branch remains
  inactive; TTM ROE cannot silently replace the quarterly requirement.
- ETF holdings use actual NAV denominators, minimum qualifying exposure and
  effective issuer breadth; overlapping funds and cash underfill are explicit.
- V2 finances the selected ordinary ETF portfolio. It does not substitute
  loosely related daily-leveraged sector products.
- V3 uses long positions followed by exits/replacement. V4 permits incremental
  financing only for qualifying liquid holdings outside binary-event windows.
- Both leveraged versions have a proposed maximum gross exposure of 1.75x.
  Binding volatility, margin, breadth and risk limits can produce less.
- Six fixed portfolio comparison claims plus one company-signal claim form
  a proposed new seven-claim family. A possible new-family 0.05 allocation
  would imply 1/140 per claim; actual allocation and outcome access are zero.
- The existing four-lane 1/80 slots and 2027-09-01 through 2029-08-31 reserved
  holdout are not reused. New dates, global selection accounting, source
  rights, power, independent review and an owner freeze remain prerequisites.

## 4. Author QA and corrections

Three bounded research assistants contributed ETF mechanics, stock-accounting
rules and validation design. Two then reviewed the draft as advisory author
QA. This is not the repository's independent Claude review or acceptance.

The author corrected all material advisory findings before export:

| Area | Correction |
|---|---|
| Volatility | Unit-basket risk is explicit; exposure uses min(breadth times cap, target volatility / unit-basket volatility), avoiding a second leverage multiplier. |
| Cash ledger | License/milestone obligations appear once across all-in FCF and runway. |
| Timing | ETF holdings and quarterly institutional observations have different freshness rules. |
| V4 financing | Base and incremental allocation vectors are separate; ineligible holdings receive no financing increment. |
| Execution | Bid/ask fills already include spread; only extra impact/fees are charged, and limit violations remain unfilled. |
| ETF selection | Complete raw rankings survive the incumbent buffer; daily gate/cap checks and monthly rank changes are distinct. |
| Stress | Full economic hurdles apply at canonical cost; positive advantage is required under higher costs/financing. Shocks apply to every scheduled portfolio snapshot. |
| Study order | All structural engines precede the single frozen outcome batch; company evidence gates later result release. |
| Inference | Seven conjunction claims and eleven-component simultaneous intervals have separate explicit allocations. |
| PDF layout | Removed a one-line orphan page; regenerated and inspected the final 24-page edition. |

## 5. Validation performed

Documentation-only validation used bundled Python 3.12.14 and ReportLab/PyPDF,
Poppler rendering, and image inspection. No strategy tests or backtests were
run because no strategy code or data pipeline was implemented.

- Strict PDF reopen passed; 24 nonempty pages and 20 section bookmarks.
- All 24 final pages rendered without Poppler warnings and were visually
  inspected for clipping, table overlap, missing glyphs and page transitions.
- PDF text bounds check found zero glyphs outside page boundaries.
- Deterministic Decimal arithmetic checks passed for 18%/30%=0.60 exposure,
  7/140=0.05 claim accounting and 11/220=0.05 interval accounting.
- Structural checks verified all four version chapters, six comparison rows,
  and the revised 15% / 35% / 25% / 40% risk limits.
- `git diff --check` passed before staging; final staged checks are recorded
  in the generic Session Handoff.

No full pytest/compileall run is represented as completed. These checks
validate document arithmetic and rendering, not market alpha or fill realism.

## 6. Evidence and next step

Public SEC, FINRA, issuer, New York Fed and factor-definition pages were read
for current mechanics. The artifact cites eight primary sources with dates.
Public issuer/factor pages can expose recent performance incidentally; those
dates are discovery exposure, not guaranteed untouched confirmation.

No licensed/provider dataset was acquired, no credential inspected, no
historical portfolio or outcome batch executed, and no QuantConnect, broker,
operator-database, scheduler or deployment action occurred in this design round.
The preceding stock-screen research is separate discovery context and was
not converted into a current portfolio.

Next useful step: review the exact blueprint and resolve semantic/source
feasibility before a separate specification freeze. A formal independent
review uses the generic exact-pushed-snapshot workflow after the owner
authorizes publishing the local design branch. Source procurement, outcome
runs, implementation scheduling and operational promotion are separate future
work; the design request does not enact those stages.
