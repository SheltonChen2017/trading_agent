# Independent review — TRADE-1 discrete trading and UI consistency

Prepared: 2026-08-14 by Codex

Review base: `a5d5fe3`

Implementation branch/head: `user/claude/discrete-trading-tabs-20260814` at
`c638bc7` (`c1dec52` initial implementation plus follow-up)

Review branch: `codex/review-trade1-discrete-tabs-20260814`

Correction commits: `93953ef`, then moving-head reconciliation `7ad7f7d`

## Outcome

**Accepted after correction.** Claude selected sound architectural boundaries:
the two old workflows were renamed without changing their meaning, the
owner-directed sell path was moved rather than duplicated, dollar budgets are
converted once with Decimal and floored to whole shares, and both new pages
still create ordinary proposals behind typed approval and fresh execution-gate
validation. No live authority, automatic submission, policy bypass, schema, or
broker-adapter change was introduced.

Claude's follow-up independently restored the moved SELL-1 exact-remainder
logic, retargeted its five tests, strengthened the sell disclaimer, and named
both sides of a valid stale-selection mismatch. The review reconciliation
retains those improvements while also handling the invalid-size case that the
follow-up still allowed to render as current.

The submitted tree was not complete at its interaction and exact-state
boundaries. The suggestion picker used a forbidden post-widget session-state
write; an old approval card remained actionable when the current controls no
longer described a valid size; sell-dollar sizing discarded exact broker price
text; moving SELL-1 regressed fractional-remainder wording; and five existing
SELL-1 UI tests were left on the old page, so the full suite failed. The
requested UI pass now gives every route the same compact Alpaca-inspired page
header and description, uses a segmented sizing control, retains the existing
safe light/dark palette and severity colors, and removes deprecated width API
calls. Submitted implementation quality: **6.5/10** — good decomposition and
safety intent, but several material integration defects escaped the focused
test selection. The follow-up raised the final assessment to **7/10** by
catching and correcting two of the initial integration regressions before this
review closed.

## Exact snapshot and commit disposition

The complete ordered implementation range was `a5d5fe3..c638bc7` and contained
two commits. The branch advanced during review; `c638bc7` was added to scope
before closure rather than leaving the earlier snapshot as the reported head.

| Commit | Disposition | Review result |
|---|---|---|
| `c1dec52` | **Accepted after correction** | The four-page split, whole-share dollar-budget decision, proposal reuse, approval separation, and documentation direction are sound. TRADE1R-001 through TRADE1R-008 correct interaction, stale-state, exact-number, regression-suite, disclosure, compatibility, overflow, and direct-test gaps. |
| `c638bc7` | **Accepted after correction** | Correctly restores exact fractional-remainder copy, retargets the five moved SELL-1 tests, and strengthens disclosure and valid-mismatch copy. It retained the truthy-only stale guard, so a zero/invalid size could still leave an old card actionable; `93953ef` plus `7ad7f7d` preserve its improvements and close that remaining direction. |

## Prioritized issue ledger

Final state: **0 P0, 0 P1, 0 P2, and 0 P3 open**.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| TRADE1R-001 | P2 | Closed | `c1dec52` | `scripts/personal_assistant_ui.py`, Discrete Buying picker | A suggestion button assigned `discrete_buy_ticker` after the text input with that key had already been instantiated. Streamlit forbids that mutation, so the requested click-to-select mechanism could raise instead of filling the ticker. | Source-order audit showed the text input rendered before every button handler; AppTest now drives the real picker callback and asserts the field changes with exactly one explicit provider call. | A primary requested interaction must work and must not turn a benign suggestion click into a page exception. | Move the assignment into a button callback, which Streamlit runs before rebuilding widgets. | Picker AppTest passes, fills NVDA, and confirms zero provider calls before the explicit button and one after it. |
| TRADE1R-002 | P2 | Closed | `c1dec52` | Discrete buy/sell stored proposal rendering | The stale-card guard compared size only when the current share value was truthy. Switching to dollar mode with a zero/invalid amount returned `None`, bypassed the mismatch, and left an old approve-gated card looking synchronized with controls that described no trade. | Red AppTest: a stored BUY 1 NVDA card remained after switching to the default zero-dollar input. The sell path had the identical condition. | An actionable proposal card must be bound to a valid current ticker and quantity; invalid controls cannot be treated as a match. | Treat `None` as stale and require exact ticker and share equality on both pages; explain why the prior card is hidden. | Green AppTests hide both stored buy and sell cards when dollar input is zero and retain the cards only for exact matches. |
| TRADE1R-003 | P2 | Closed | `c1dec52`, `c638bc7` | Discrete Selling price/remainder presentation | Dollar sizing used rounded `current_price` instead of `current_price_exact`, and the initial close-position copy compared the sale only with floored whole shares. A $100 budget at an exact $100.000000000000000001 price incorrectly sized one share, while selling 10 of 10.5 shares could be called a full close. | Red exact-price AppTest produced a one-share sizing instead of refusal. The moved SELL-1 regression exposed the missing 0.5-share remainder when pointed at the new page. | Exact broker evidence outranks a lossy display float, and fractional holdings must never be described as gone. | `c638bc7` restored exact remaining-quantity copy; review additionally sizes from exact price text and retains that wording through `7ad7f7d`. | Green tests refuse the exact over-$100 boundary and display `0.5 share(s) would remain`. |
| TRADE1R-004 | P2 | Closed | `c1dec52`, `c638bc7` | `tests/test_ui_user_directed_sell.py` | Five existing SELL-1 UI regressions still navigated to Policy Based Selling and old widget keys after the initial move, making the repository full suite fail and removing effective regression coverage from the new owner-directed page. | Broader focused run: 5 failed, 103 passed; failures showed the direct-sell section and old widgets absent from the policy page. | A milestone is not done when the required full suite fails, and moved safety coverage must follow the production behavior rather than be abandoned. | Claude's `c638bc7` retargeted the five tests; review preserves and strengthens their separation/disclaimer assertions. | Corrected adjacent suite and final full suite pass; reconciled buy/sell UI suite: 20 passed. |
| TRADE1R-005 | P3 | Closed | `c1dec52` | Sidebar page-label migration | An already-open session whose radio value was `Buying` or `Selling` silently reset to Briefing after deployment because the value no longer existed. | Red parametrized AppTests expected the corresponding renamed page and observed Briefing for both legacy values. | Renaming a page should not discard the user's current location. | Map the two legacy values before the navigation widget is instantiated. | Green parametrized AppTests retain Budgeted Buying and Policy Based Selling respectively. |
| TRADE1R-006 | P3 | Closed | `c1dec52` | Discrete Buying suggestion disclosure | The copied picker omitted BUY-1's source fetch time, cache-age disclosure, and names of candidates that could not be verified. | Diff against the reviewed Budgeted Buying mechanism showed the dropped list was ignored and only row detail was stored. | “Same suggestion mechanism” includes its freshness and omission honesty, not only the ticker buttons. | Store/display source time, UTC display time, 15-minute cache bound, adjacent ticker detail, and dropped candidate names. | AppTest asserts source timestamp, cache bound, BOGUS omission, row detail, explicit-call count, and successful selection. |
| TRADE1R-007 | P3 | Closed | `c1dec52` | `assistant/discrete_trade.py` | Finite Decimal exponent inputs could overflow during division or attempt an enormous integer conversion, contradicting the helper's refusal contract and taking down a page. | Red unit test with `1e999999999 / 1e-999999999` raised `decimal.Overflow`. | Input validation should fail closed with a usable message rather than crash the UI. | Catch Decimal arithmetic exceptions and bound share conversion before creating a Python integer. | Red overflow reproduced; green test returns a stated “too large” refusal. |
| TRADE1R-008 | P3 | Closed | `assistant/allocation_proposals.py` tests and Streamlit chrome | The new buy generator had no direct unit coverage, while UI layout still used 21 deprecated `use_container_width` calls and each route lacked one consistent active-page hierarchy. | Submitted tests covered sizing helpers and selected UI output but not generator status/evidence/exact cap behavior; source inventory found 21 deprecated calls. | Direct proposal contracts should not depend on a large UI test, and the owner explicitly requested a consistent Alpaca-style design after review. | Add direct generator tests; add one native page shell across all 12 routes; modernize the sizing selector and width API while retaining the existing reviewed theme. | Generator exact-boundary/refusal tests, UI chrome tests, theme tests, and the full suite pass. |

Issue totals: **0 P0, 0 P1, 4 P2, 4 P3; all closed**.

## Contract and safety review

- Budgeted Buying and Policy Based Selling retain their prior deterministic
  allocation and breach-only meanings. Owner-directed selling exists on one
  page only.
- Dollar entry is a budget converted to whole shares by floor. The unspent
  amount is stated; over-holding sells refuse instead of silently capping.
- Discrete buys use the new exact-share generator; discrete sells reuse the
  reviewed SELL-1 generator. Both persist a `proposed` proposal before display.
- Suggestion loading is explicit, uses the shared cached AP-8 verification
  pipeline, disables IPO/AI lanes, and does not itself propose or trade.
- Typed approval, current-policy fingerprint checks, fresh quote/account
  validation, duplicate protection, reservation, paper-mode enforcement, and
  broker execution remain downstream and unchanged.
- The UI pass is presentation-only. Existing light/dark theme tokens and
  severity colors remain authoritative; no remote font or external styling
  dependency was added.
- No migration, operator database, deployment, scheduler, credential, funded
  account, operational checkout, or evidence epoch was changed. Frozen
  epoch-005 remains on `752d3b7`.

## Validation

Environment: Windows repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Submitted focused baseline: **37 passed**.
- Confirmed submitted-tree red evidence: legacy navigation reset (2 cases),
  invalid-size stale buy card, exact sell-price boundary, and Decimal overflow.
- Broader pre-correction adjacent run: **5 failed, 103 passed** because moved
  SELL-1 tests still targeted the old page.
- Corrected feature/proposal/chrome/SELL-1 suite: **83 passed**.
- Corrected full repository suite with a dedicated writable base temp:
  **3,691 passed, 0 failed, 0 skipped, 25 known dependency warnings** in
  731.00 s.
- After the moving-head copy/test reconciliation, a second full attempt crossed
  local midnight and finished **3,676 passed / 15 failed / 25 warnings**. The
  failures were isolated as environment/test-fixture effects outside TRADE-1:
  four ML immutable-store tests exceeded Windows MAX_PATH only under the
  overly long base-temp path and immediately passed **9/9** with `.t`; eleven
  strategy tests generated Aug-14 weekday bars before the Aug-14 NYSE session
  was in progress, which the production freshness gate correctly refused. No
  freshness logic was weakened. The exact final TRADE-1/proposal/chrome suite
  then passed **83/83**, including the reconciled disclosure and stale-card
  paths.
- Repository-prescribed `compileall`: clean. `git diff --check`: clean apart
  from expected Windows line-ending notices. Narrow changed-file secret-shape
  scan: no values found; matches were environment-variable names only.
- All provider seams in the new UI tests were monkeypatched. No broker call,
  order, deployment, task change, or operational-state mutation occurred.

## Remaining limits and next step

Dollar sizing is still a reference-price estimate for a whole-share market
order, not a guarantee that the eventual fill spends exactly the entered
amount. Most-active suggestions describe volume and same-day direction, not a
predictive edge. This project still has zero confirmed individual-stock
selection signal, and neither discrete page changes that.

The review branch is published at
`origin/codex/review-trade1-discrete-tabs-20260814`. The next step is
independent verification of `93953ef`, `7ad7f7d`, and the documentation /
handoff commits, then owner authorization before any merge. Nothing in this
review authorizes deployment, another epoch roll, M4, operator-database
mutation, funded trading, or a scheduler change.

---

## Counter-review (Claude, 2026-08-14)

Owner-requested verification of this review, performed on the review branch
at `f693c4d` while the owner was away.

### Every finding verified

All eight findings are **confirmed genuine**, each re-established by
reverting the correction and observing the intended regression redden, then
restoring. Several are defects in code I wrote and are worth stating plainly:

| ID | Independent verification |
|---|---|
| TRADE1R-001 | **Confirmed, and the severity is right.** The picker assigned `discrete_buy_ticker` after the text input owning that key had been instantiated — which Streamlit forbids, so the feature's *primary* interaction could raise rather than fill the field. My own tests never clicked a suggestion button; I built click-to-select and only tested that the expander existed. Mutation: removing `on_click=_select_discrete_buy_ticker` reddens. |
| TRADE1R-002 | **Confirmed, with a mutation caveat worth recording.** Deleting the added `or _db_shares is None` clause does NOT reproduce the defect, because the following `!= _db_shares` already catches `None` — a naive mutation here reports a false "test doesn't work". The faithful mutation restores the original truthy short-circuit `or (_db_shares and ... != _db_shares)`, and that reddens on both pages. The clause is redundant to the comparison but load-bearing for the explanatory copy. |
| TRADE1R-003 | **Confirmed.** Sell dollar sizing used the rounded display `current_price` while I had carefully used `shares_exact` two lines above — exactly the SELREV-001 lesson applied to one field and not its neighbour. Mutation reddens. |
| TRADE1R-004 | **Confirmed**; this was my own `c638bc7` follow-up, and review preserved and strengthened the retargeted tests rather than accepting them as-is. |
| TRADE1R-005 | **Confirmed.** An open session sitting on `Buying`/`Selling` silently reset to Briefing after the rename. Mutation of the legacy-label map reddens two parametrized tests. |
| TRADE1R-006 | **Confirmed.** I copied BUY-1's picker mechanism but dropped its fetch time, 15-minute cache disclosure, and dropped-candidate names — violating, in my own next feature, the "the disclosure travels with the ticker" principle I had argued for when building BUY-1. Verified restored on both pages. |
| TRADE1R-007 | **Confirmed.** `1e999999999 / 1e-999999999` raised `decimal.Overflow` out of a helper whose docstring promises it "never raises for ordinary bad input". Mutation of the `except DecimalException` guard reddens. |
| TRADE1R-008 | **Confirmed.** The new buy generator had only indirect UI coverage; 21 deprecated `use_container_width` calls remained (now 0). |

**No test was weakened or deleted.** The one renamed test
(`test_discrete_selling_is_the_only_owner_directed_sell_surface`) is
strictly stronger than mine: it additionally pins that the policy-breach
section is ABSENT from the discrete page, i.e. the separation itself.

**Topology note:** my follow-up `c638bc7` is *not* an ancestor of this review
head — its fixes were reimplemented in `7ad7f7d` rather than merged. Content
was verified equivalent for both files it touched; the only differences are
the deprecated-width removals and the UI pass. If both branches are merged,
expect a textual conflict rather than a lost fix.

### Counter-review finding

| ID | Priority | Status | Finding |
|---|---|---|---|
| TRADE1CR-001 | P3 | **Resolved in this counter-review** | The Alpaca-style pass replaced `st.radio` with `st.segmented_control` for the sizing selector. Unlike radio, that widget lets the user **deselect** the active option, so its value can be `None` — a state the previous control could not produce. Unhandled, `_render_discrete_sizing` fell through to its dollar branch and rendered the "Dollar amount ($)" input while the selector showed nothing selected: the page behaving as one mode while claiming none. Reproduced on both discrete pages by deselecting and re-running. Not unsafe on its own — dollar sizing still floors, refuses zero, and caps a sell at the holding — but a control that does not describe what the page will do is the class AP-9 and the stale-card work closed. Fixed by treating `None` as "no mode chosen": size nothing, offer nothing to create, and ask for a mode. Red-first on both pages, and mutation-verified. |

| TRADE1CR-002 | P3 | **Recorded, deliberately not fixed here** | The repository-prescribed validation (`python -m pytest -q`) cannot pass between roughly 00:00 and 09:30 Eastern, and could not on any day this week. `tests/test_strategy_proposals_generic.py:50` builds its bars with `pd.bdate_range(end=pd.Timestamp.today().normalize(), ...)`. After local midnight that end date is the NEW session — later than the latest completed one, and not yet an in-progress NYSE session — so `evaluate_bar_freshness` correctly reports the bars stale and `generate_leveraged_pair_rebalance_proposals` refuses. The production guard is right; the FIXTURE is wrong to anchor on "today". Consequence for this project's own discipline: every "full suite green" recorded today (including 3,674 and 3,680) was measured before midnight, and CLAUDE.md's completed-milestone requirement is unsatisfiable overnight. Same class as the two already-recorded fragilities (machine load, the WindowsApps interpreter). Not fixed here because it touches shared strategy tests unrelated to TRADE-1 and belongs on its own branch; the fix is to anchor fixtures to the latest completed session instead of `today`. |

### Counter-review validation

- Focused TRADE-1 suites (discrete trade, discrete tabs, owner-directed
  sell, allocation proposals, UI chrome): **83 passed** before the fix,
  **17 passed** in the discrete-tab suite after adding the two new cases.
- Eight review-finding mutations plus one faithful re-mutation: each
  reddened its intended regression and passed restored; worktree confirmed
  byte-clean afterwards.
- Generalized-instance sweep: no other post-widget session-state write
  (`watchlist_from_suggestions` is not a widget key), and the remaining
  `current_price` uses are display-only.
- Exact counter-review tree: **3,681 passed, 12 failed** in 736.43 s. The
  12 are accounted for exactly and NONE is caused by this change:
  - **11** are the pre-existing time-dependent strategy-proposal family
    described in TRADE1CR-002 below. Proven environmental by running the
    same tests on an untouched `origin/main` worktree at `a5d5fe3`, where
    they fail identically (11 failed, 19 passed), every one raising
    `StaleMarketDataError`.
  - **1** was the placeholder guard correctly rejecting this line's own
    then-unfilled token.
  Reporting this as "green" would have required either measuring before
  midnight or quietly excluding the family; both were rejected.
