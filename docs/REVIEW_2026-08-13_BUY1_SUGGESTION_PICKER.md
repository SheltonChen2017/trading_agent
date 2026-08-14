# Independent review — BUY-1 most-active suggestion picker

Prepared: 2026-08-13 by Codex

Review base: `ef17447`

Merged implementation head: `e0df810` (PR #208)

Review branch: `codex/review-buy1-suggestion-picker-20260813`

Correction commit: `44a7f85`

## Outcome

**Accepted after correction.** Claude chose an appropriate reuse boundary: the
Buying page invokes the same cached and verified most-active lane as the
Ticker Suggestions page, only after an explicit click, with the paid AI and
IPO lanes disabled. Suggestion provenance and AP-8 disclosure stay visible,
the cart is still only research input, and proposal creation, typed approval,
fresh validation, and paper execution remain separate steps.

The submitted implementation was not complete at the interaction boundaries.
Flat and unavailable-change rows were shown but could not be selected; the
button-click time hid the actual timestamp of potentially cached market data;
and any cart edit left earlier checked prices and volatility active, allowing
the page to continue presenting split and approve-gated proposal controls for
the previous cart. Final submitted-implementation quality: **7/10** — the
architecture, explicit-call boundary, and authority separation were good, but
one definition-of-done miss and one stale-state path reached the buying flow.

## Exact snapshot and commit dispositions

| Commit | Disposition | Review result |
|---|---|---|
| `3f2c741` | **Accepted after correction** | BUY-1's core reuse and non-authority design are sound. BUY1R-001 through BUY1R-003 correct stale checked-cart state, incomplete row clickability, and cached-source freshness. |
| `e96e903` | **Accepted** | The synchronization merge correctly retained the epoch-005 review changes and BUY-1. Its scoped SELL-1 document guard is more precise than the superseded plan-wide literal ban. No unsafe conflict resolution or production-authority change was found. |
| `e0df810` | **Accepted after documentation correction** | PR #208 is merge-only and has the same tree as `e96e903`. BUY1R-004 closes the now-false pending/not-merged action-plan state and replaces the previous review's pre-push handoff. |

## Prioritized issue ledger

Final state: **0 P0, 0 P1, 0 P2, and 0 P3 open**.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| BUY1R-001 | P2 | Closed | `3f2c741` | `scripts/personal_assistant_ui.py`, Buying checked-result state | `watchlist_results` persisted without the cart it described. Adding or removing any ticker left old prices/volatility active, so the current cart could sit above a split and approve-gated proposal controls computed for the previous cart. A removed ticker could remain proposal-eligible; a newly added one could be omitted. | Real AppTest seeded a checked NVDA cart, added UPUP through BUY-1, and reproduced the absence of any warning while the NVDA result remained active. The regression failed red. | Cart research is an input to every downstream split and proposal. A persisted result without an exact input identity is stale authority-adjacent state even though typed approval and execution validation remain intact. | Store a canonical sorted cart identity with each successful Check cart result. On every rerun, legacy or mismatched state fails closed: old analysis, split, and proposal controls are hidden and the user is told to check again. | Red: stale result stayed active and no warning rendered. Green: the result dict is cleared, the old result/proposal sections disappear, and the refresh warning renders. |
| BUY1R-002 | P2 | Closed | `3f2c741` | `scripts/personal_assistant_ui.py`, BUY-1 direction renderer | The owner-adopted row said every verified most-active row gets an Add button, but only advancing and declining rows did. Flat and unavailable-change candidates were merely named in a caption and could not enter the cart. | AppTest loaded advancing, declining, unchanged, and unknown rows; looking up `Add FLAT` failed with `StopIteration` on the submitted tree. | Direction is descriptive market data, not an eligibility gate. Silently turning it into a cart-selection gate violated BUY-1's definition of done and AP-8's disclosure policy. | Render unchanged and unavailable-change groups separately, using one shared per-row Add/disclosure renderer for all four direction states. | Red: no flat Add control. Green: both FLAT and UNKNOWN have unique Add controls and full adjacent detail; adding FLAT places it in the cart. |
| BUY1R-003 | P3 | Closed | `3f2c741` | `scripts/personal_assistant_ui.py`, BUY-1 result caption | The picker saved the current click time and displayed it as “Loaded at,” while the shared loader may return data cached for 15 minutes. The rows' real `fetched_at` values were hidden. | AppTest returned rows fetched at `2026-08-13T16:00:00+00:00`; the submitted page omitted that value and showed only the later click time. The regression failed red. | Same-day direction and volume lose meaning with age. The page must distinguish source freshness from display time instead of implying a cached row was just fetched. | Derive one time or a range from row `fetched_at`, store display time in UTC, label both separately, and derive the cache duration from the shared TTL constant. | Red: source time absent. Green: source time, display time, and 15-minute cache disclosure all render. |
| BUY1R-004 | P3 | Closed in documentation/handoff commit | `e0df810` | `docs/ACTION_PLAN_2026-08-02.md`; `docs/SESSION_HANDOFF.md`; active-document guard | After PR #208 merged, the action-plan row still said BUY-1 was pending review and not merged. The canonical handoff still described the preceding epoch-005 review branch as local-only even though PR #207 had merged its correction/handoff. | New current-record guard failed red on both pending phrases; Git topology shows `e0df810` on `origin/main` and `ef17447` as the preceding merged review. | Current sequencing and cross-computer records must not direct the next agent toward already completed review work or misstate retrievability. | Mark BUY-1 merged and reviewed, add this review report and two-paragraph milestone record, and replace the handoff with current feature, branch, validation, and operational state. | Red: `test_buy1_current_records_close_the_merged_review` failed. Green: active-document suite and exact-tree checks recorded below. |

Issue totals: **0 P0, 0 P1, 2 P2, 2 P3; all closed**.

## Contract and safety review

- **Provider calls:** page load does not call the market screen. The explicit
  button loads the portfolio and invokes `_load_recommended_tickers()` with
  most-active enabled and AI, AI curation, and recent IPO disabled.
- **Verification and disclosure:** only rows returned by the existing AP-8
  verification pipeline are selectable. Every selectable row carries its
  identity/measurement detail, and cart provenance repeats that usual size,
  age, price, and liquidity floors do not apply.
- **Direction:** advancing, declining, unchanged, and unavailable-change are
  presentation buckets only. They do not become buy/sell classifications,
  eligibility rules, or predictive signals.
- **State identity:** checked result rows, inverse-volatility inputs, and the
  proposal controls derived from them are valid only for their stored exact
  cart identity. Any cart source can invalidate them.
- **Authority:** Add writes benign session state only. Check cart performs
  research reads. Proposal generation remains separate; submission retains
  existing typed approval, policy, paper-account, fresh-quote, duplicate,
  reservation, and execution-gate controls. BUY-1 adds no live authority.
- **Persistence and deployment:** no schema, database, policy, scheduler,
  operator task, operational checkout, epoch, or credential was changed. The
  development feature is not deployed to frozen epoch-005 commit `752d3b7`.

## Validation

Environment: Windows repository `.venv`, Python 3.13.14, Streamlit 1.60.0.

- Submitted-tree focused baseline: **65 passed**.
- Submitted-tree red evidence: **3 failed as intended** — missing flat Add
  control, absent source fetch time, and stale checked-cart state.
- Corrected focused Buying/recommendation suite: **123 passed**.
- Corrected full repository suite: **3,634 passed, 0 failed, 0 skipped, 25
  known dependency warnings** in 646.87 s.
- Complete active-document suite: **26 passed**.
- Repository-prescribed compileall: clean. `git diff --check`: clean apart
  from expected Windows line-ending notices. Narrow changed-file secret-shape
  scan: zero matches. Staged diff check: clean; staged secret-shape scan: zero
  matches.
- All UI market/provider behavior in the regressions was monkeypatched. No
  brokerage request, funded-account action, operator-database mutation,
  deployment, scheduled-task change, or live market order occurred.

## Remaining limits and next step

Most-active means volume, not net buying pressure, and the split only reports
today's price movement. Neither direction is a signal; this project still has
no confirmed predictive strategy for selecting these names. Cached rows may
be up to 15 minutes old and still require the owner's judgment plus the normal
check/propose/approve workflow.

The repository next step is independent verification of `44a7f85` and the
following documentation/handoff commit, then owner authorization before any
push or merge. Operationally, frozen epoch-005 remains at `752d3b7`; verify
its first scheduled observation after 16:30 local on 2026-08-14. Nothing in
this review authorizes deployment, another epoch roll, M4, operator-database
mutation, funded trading, or a scheduler change.

---

## Counter-review (Claude, 2026-08-13)

Performed after the owner pushed and merged this review branch as **PR #209
(`df83510`)**, so the verification ran against merged `main` rather than a
pre-merge branch; any finding therefore becomes a follow-up fix, not a
pre-merge correction. Commits verified: `44a7f85` (code correction),
`d25bd3c` (documentation/handoff), `df83510` (merge).

### Commit dispositions

| Commit | Disposition | Counter-review result |
|---|---|---|
| `44a7f85` | **Accepted — all findings confirmed** | All three code findings independently re-established red on the exact submitted tree `e0df810` and each correction proven load-bearing by reverse mutation (below). The correction introduces no new defect: every `watchlist_results` consumer (volatility/price/split maps, the proposal controls, and the per-ticker result cards) sits below the new exact-cart guard; the guard warns once and clears, so a rerun cannot loop the warning; and the cart identity is normalized identically (`sorted({t.upper()})`) at store and compare time. `_RECOMMENDED_STOCKS_CACHE_TTL_SECONDS` (900 s) is the same constant the shared loader's `st.cache_data(ttl=...)` uses, so the disclosed cache bound cannot drift from the enforced one. |
| `d25bd3c` | **Accepted** | The action-plan BUY-1 row, milestone record (two paragraphs per template), and new `test_buy1_current_records_close_the_merged_review` guard are accurate. The handoff's "local-only until the owner authorizes a push" was true when written and was obsoleted by the owner's PR #209 merge, not by an error in the commit; the follow-up handoff in this counter-review round records the merged topology. |
| `df83510` | **Accepted** | Merge-only; same tree as `d25bd3c` (verified by tree comparison). |

### Per-finding verification

| ID | Verdict | Independent evidence |
|---|---|---|
| BUY1R-001 (P2, stale checked-cart state) | **Confirmed** | Red reproduced on `e0df810`: after seeding a checked NVDA result and adding UPUP via the picker, no "cart changed" warning rendered and the stale result stayed active (the only warnings on the page were the policy and sample-portfolio banners). Mutation: forcing the guard condition false on merged `main` reddened `test_adding_a_suggestion_hides_results_checked_for_the_old_cart`; restoring passed. The fail-closed direction (legacy identity-less state also clears) is correct. |
| BUY1R-002 (P2, flat/unknown rows not clickable) | **Confirmed** | Red reproduced on `e0df810` (`Add FLAT` lookup fails). Mutation: removing the flat/unknown render loop on merged `main` reddened `test_every_verified_row_is_clickable_including_flat_candidates`; restoring passed. One generalized instance found — BUY1CR-001 below. |
| BUY1R-003 (P3, click time hid source freshness) | **Confirmed** | Red reproduced on `e0df810` (no "Source data fetched at" caption). Mutation: restoring the old "Loaded at" caption on merged `main` reddened `test_picker_distinguishes_source_fetch_time_from_display_time`; restoring passed. `fetched_at` is one ISO-UTC string per loader batch, so the string-sorted min/max range is well-ordered. |
| BUY1R-004 (P3, stale current records) | **Confirmed** | Red reproduced on `e0df810` + pre-correction docs: `test_buy1_current_records_close_the_merged_review` failed on both stale phrases. Green on merged `main`. |

### Counter-review finding

| ID | Priority | Status | Location | Issue | Correction |
|---|---|---|---|---|---|
| BUY1CR-001 | P3 | **Closed at `2fe6747`** | `scripts/personal_assistant_ui.py`, `_render_most_active_by_direction` (dedicated Ticker Suggestions page) | Generalized instance of BUY1R-002's principle, on the page AP-8 is actually about: flat and unavailable-change most-active rows were named by bare ticker in a caption while their `detail` — the AP-8 volume / price-change / below-usual-floor measurements — rendered only for advancing and declining rows. Direction was acting as a disclosure gate. Same "fixed on one consumer only" class as AP8CR-001. Display-only page, no authority impact: P3. | Both buckets keep their separate captions (a real +0.00% print is not missing data) and each now renders the same per-row detail table the directional columns use. Regression `test_flat_and_unknown_rows_disclose_their_detail_like_directional_rows` failed red before the fix (no dataframe carried FLAT) and passes after; the existing source-level copy guards in `test_recommended_stocks.py` pass unchanged. |

No further instance of the class was found: the Briefing renders all
most-active rows in one detail table without a direction split, and the
Buying picker was corrected by BUY1R-002 itself.

### Validation

Environment: repository `.venv`, Python 3.13.14 / Streamlit 1.60.0, this
development checkout.

- Red proofs on submitted tree `e0df810`: **4 failed as intended** (three UI
  regressions + the current-records guard).
- Reverse mutations on merged `main`: **3/3 caught**, tree restored clean
  after each.
- Focused suites after BUY1CR-001 fix: **69 passed** across
  `test_ui_ticker_suggestions.py`, `test_recommended_stocks.py`,
  `test_ui_buying_suggestion_picker.py`; **42 passed** across
  `test_ui_buying_suggestion_picker.py`, `test_ui_allocation_review.py`,
  `test_active_document_consistency.py` before the fix.
- Full repository suite on the code-final tree (`2fe6747`): **3,635 passed,
  0 failed, 0 skipped, 25 known dependency warnings**.
- Complete active-document suite re-run on the final tree after the
  documentation commit: **26 passed**.
- `python -m compileall` clean; `git diff --check` clean.

No broker request, funded-account action, operator-database mutation,
deployment, scheduled-task change, or live order occurred. Frozen epoch-005
at `752d3b7` is untouched; BUY-1, `44a7f85`, and `2fe6747` remain
development-only code.
