# Independent review — AP-8 ticker-suggestion disclosure policy

Prepared: 2026-08-12

Outcome: **accepted after correction**

Implementation-quality assessment: **7/10**. Claude correctly separated a
research-disclosure surface from a vouched-for shortlist, preserved the
equity/US-venue checks, fixed yfinance's company-name fallback, named omitted
symbols, and added unusually good per-lane mutation coverage. The submitted
tree nevertheless weakened one identity check that the owner did not remove,
allowed invalid market values to become “verified,” omitted the relaxed-policy
warning from one of the two consumers, and removed an existing import without
need. Those four material issues and one adjacent Streamlit deprecation were
corrected before acceptance.

## Review topology and commit disposition

- Base: `cea6640` (PR #193 merge; `main` / `origin/main` at review start).
- Submitted branch: `user/claude/ticker-suggestion-disclosure-20260812`.
- Submitted commit: `d326a74`.
- Review branch: `codex/review-ap8-ticker-disclosure-20260812`.
- Corrective code commit: `7c21339`.

The submitted range was exactly `cea6640..d326a74` and contained one commit.

| Commit | Disposition | Review result |
|---|---|---|
| `d326a74` | Accepted after correction | Four P2 findings and one P3 finding, all closed by `7c21339`. No merge commit was part of the submitted range. |

## Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| AP8REV-001 | P2 | Closed | `d326a74` | `assistant/ticker_verification.py:96,195` | The new disclosure policy set `require_company_name=False`. AP-8 was authorized to remove size, age, price, and liquidity judgments—not company identity—so an LLM-authored symbol with bars, an equity quote type, and a US exchange but no name could render as verified. | Reviewer test with all three name fields absent failed red because `NONAME` was returned as verified. | The milestone explicitly retains identity as the hallucination boundary. Disabling the name requirement contradicted that contract and weakened the exact safeguard the NBIS three-field fallback was meant to repair. | Restored `require_company_name=True`; accepts only non-empty textual `longName`, `shortName`, or `displayName`. NBIS still passes through its real fallback, while all names absent fails closed. | Identity reviewer test and the existing short/display/all-missing tests pass; focused and full suites pass. |
| AP8REV-002 | P2 | Closed | `d326a74` | `assistant/ticker_verification.py:167-218`; `assistant/recommended_stocks.py:83-134` | Setting display thresholds to zero made a zero or positive-infinite close eligible. A malformed close could also raise and abort the whole batch despite the function's isolation contract. Missing volume was converted to measured `$0`, creating a false liquidity fact; non-finite volume could pass or disappear from disclosure. | Red reviewer cases: zero and `+inf` closes were verified; a text close raised `ValueError` before the good second ticker ran; absent volume became `0.0`; the disclosure helper emitted no unavailable note. (`-inf` was already rejected.) | Removing a $5 or $1M suitability floor does not authorize malformed data or invented measurements. Every removed screen must become an honest fact, and one bad ticker must not hide unrelated rows. | Finite positive close is now a baseline data-validity requirement independent of policy; malformed values drop only their row. Liquidity is optional only when the policy has no positive floor, remains `None` when unavailable/corrupt, and receives an explicit cannot-compare disclosure. Strict-policy callers still require measured liquidity. | Eight relevant reviewer cases pass, including batch continuation and unavailable-liquidity presentation; focused and full suites pass. |
| AP8REV-003 | P2 | Closed | `d326a74` | `scripts/personal_assistant_ui.py:1816-1850` | The dedicated Ticker Suggestions page disclosed the relaxed screen, but Briefing consumed the same policy without saying so when no rows were omitted. Its heading still says “Recommended stocks,” so users could reasonably infer the old eligibility screen remained. Its omission caption also stated a security “did not resolve,” even though a temporary provider failure is observationally identical. | Behavioral Briefing AppTest failed red: with every provider returning an empty/clean result, no caption contained “NOT screened on size, age, price, or liquidity.” Source inspection confirmed policy wording existed only on the dedicated page. | Disclosure is the definition of done, not optional copy. Both consumers of the relaxed policy must reveal it even when there is no dropped row. A provider outage must not be reported as a fact about the security. | Added an always-visible Briefing verification/screening caption and changed omission copy to “could not be verified at this time.” | Offline Briefing AppTest is green; dedicated-page AppTests and all page smoke/navigation tests pass. |
| AP8REV-004 | P2 | Closed | `d326a74` | `assistant/ticker_verification.py:65` | AP-8 deleted the public module-level `RECENT_IPO_ELIGIBILITY_POLICY` name even though changing the caller to the new policy did not require removal. Existing downstream imports would fail at import time. | Compatibility reviewer test failed red with `AttributeError`; the exact constant and reviewed values existed at the base commit. | Repository review rules classify public compatibility regressions as material. Preserving an unused immutable constant costs nothing and avoids coupling a behavior change to an import break. | Restored the legacy constant with its exact prior values and a comment that AP-8 no longer uses it. | Compatibility test and complete import/full suites pass. |
| AP8REV-005 | P3 | Closed | Adjacent pre-existing code in the `d326a74` rendering blocks | `scripts/personal_assistant_ui.py:1870,3320` | Both AP-8 table blocks still used deprecated `use_container_width=True`; installed Streamlit 1.60 emitted removal warnings during the reviewer Briefing run. | Runtime AppTest warning named the replacement and a post-2025 removal timeline; the required version-matched Streamlit skill prohibits adding or retaining it when encountered. | Leaving a known-deprecated parameter in the exact modified UI blocks creates avoidable upgrade failure and warning noise. | Replaced the two AP-8-area calls with `width="stretch"`; unrelated legacy sites remain outside this milestone. | Focused AppTests pass without warnings from these two calls; full suite passes. |

No P0, P1, or unresolved issue remains.

## Final behavior and boundaries

All three `build_recommended_tickers()` lanes now use one disclosure policy:
they do not hide a real named US-listed equity merely because it is young,
below $5, or below the project's usual liquidity floor. Each below-usual or
unavailable measurement is visible on its row. Identity remains fail-closed:
the ticker must resolve to non-empty real history with a finite positive close,
be an equity on an allowlisted US venue, and have a textual company name from
yfinance's three supported name fields. A failed identity check names the
omitted symbol without claiming the security itself is invalid.

The strict default policy remains unchanged for the Buying/Watchlist similar-
stocks surface. This feature is research presentation only; it does not create
or alter proposals, approvals, orders, policy, scheduler behavior, evidence
epochs, ML/LLM authority, or live-trading authority. It is not deployed into
active `paper-epoch-004`.

## Validation on the corrected tree

- `.venv`: Python 3.13.14; Streamlit 1.60.0.
- Submitted focused baseline: 71 passed in 12.08s.
- Reviewer red phase: eight cases failed for the intended reasons; the
  negative-infinity control already failed closed.
- Corrected focused AP-8 suite: 80 passed in 11.32s.
- Corrected broader consumer/UI/import suite: 160 passed in 62.17s.
- Full repository suite: **3,454 passed, 0 failed, 0 skipped, 25 dependency
  warnings** in 747.00s.
- Collection: 3,454 tests in 14.97s.
- `compileall`: clean.
- `git diff --check`: clean apart from expected Windows LF→CRLF notices.
- Changed-file credential-shape scan: zero matches (the scan command's only
  nonzero status was ripgrep's normal “no matches” result).

AP-8 is complete on the reviewed branch. It should not cause an epoch roll by
itself; it can ride a later owner-authorized deployment boundary.
