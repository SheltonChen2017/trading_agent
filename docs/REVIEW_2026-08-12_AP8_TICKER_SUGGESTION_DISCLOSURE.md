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

---

## Counter-review (Claude, 2026-08-12)

Outcome: **all five review findings accepted; two further defects found and
fixed on this branch.**

Each review finding was verified against the submitted tree before being
accepted, and each correction was then mutated to prove it is load-bearing
rather than decorative:

| Finding | Verified as | Mutation proof that the correction carries weight |
|---|---|---|
| AP8REV-001 | Confirmed. `require_company_name=False` contradicted the policy's own comment, which claimed identity was retained. The submission was internally inconsistent, not merely permissive. | Reverting to `False` reddens `test_disclosure_policy_still_requires_a_company_identity` and `test_suggestion_disclosure_policy_keeps_identity_and_drops_size_screening`. |
| AP8REV-002 | Confirmed on all three parts. A zero or `+inf` close became "verified"; a malformed close aborted the batch; absent volume was published as a measured `$0`, which is an invented fact rather than a missing one. | Deleting the finite/positive close check reddens both `test_disclosure_policy_rejects_invalid_close_as_not_verified` cases; restoring `0.0` as the liquidity default reddens `test_disclosure_policy_preserves_unavailable_liquidity_as_unavailable`. |
| AP8REV-003 | Confirmed. Briefing consumed the relaxed policy under a "Recommended stocks" heading while saying nothing about it. | Covered by the reviewer's offline Briefing AppTest. |
| AP8REV-004 | **Partially correct.** The reasoning is sound but the stated impact is hypothetical: at `d326a74` no module, script, or test still imported `RECENT_IPO_ELIGIBILITY_POLICY`, so no import could have broken. Accepted anyway — restoring an immutable constant costs nothing and the compatibility argument holds for tooling outside this repository. Recorded honestly so a future reader does not infer that a real breakage occurred. | n/a — inert constant. |
| AP8REV-005 | Confirmed and correctly scoped to the two AP-8 blocks. | n/a — deprecation removal. |

### AP8CR-001 — P2, closed. The disclosure fix was applied to one consumer of two.

AP8REV-003 corrected the Briefing copy on two distinct points: identity now
includes a company name ("named US-listed equity"), and omission copy must not
assert that the security itself is invalid, because a provider outage and an
unidentifiable symbol are indistinguishable from the result shape. Both points
apply verbatim to the dedicated Ticker Suggestions page — the surface AP-8 is
actually about — which still read "as a US-listed equity" and "could not be
identified and were omitted".

The review's own handoff already described the corrected behavior as present
on both pages ("Both Briefing and Ticker Suggestions ... the UI says they could
not be verified 'at this time'"), which was not true of the second page. That
makes this a missed generalized instance rather than a difference of taste.

Fixed by applying the same two corrections to the dedicated page.
`test_dropped_candidates_are_named_not_just_counted` now pins both phrases;
reverting either reddens it.

A second-order defect came with it: `test_no_dropped_candidates_produces_no_
omission_sentence` asserted the absence of the literal "could not be
identified". Once the other consumer's wording changed, that assertion could
only pass — it had stopped testing anything. It now tracks the live wording.

### AP8CR-002 — P2, closed. Batch isolation was restored one line short.

AP8REV-002 established that one malformed candidate must not hide unrelated
rows, and guarded the close. `first_session_date` was still derived unguarded
further down the same loop, so a frame whose index is not datetime-like raised
`AttributeError: 'int' object has no attribute 'date'` out of `verify_tickers()`
and destroyed the whole batch, including every already-validated ticker.

Reproduced directly: a batch of one odd frame plus one good frame aborted
entirely instead of returning the good ticker. Reachability is the same as the
malformed-close case the review did fix — `fetch_historical` normally yields a
`DatetimeIndex`, so both are defensive — which is precisely why the same
reasoning applies to both.

The candidate is dropped rather than given an empty date.
`_is_ipo_identity_mismatch()` treats a missing first-session date as "no
mismatch", so substituting `""` would silently disarm the reused/renamed-symbol
guard that exists to catch malformed identity. Removing the guard reddens
`test_unusable_index_drops_only_that_ticker_instead_of_aborting_batch`.

### AP8CR-003 — P3, closed. Orphaned host rules in the operational record.

`docs/OPERATIONAL_FACTS.md` had a block of standing host rules (launch script,
restart-after-deploy, elevated task helper, process singleton, backup location,
console-loss behavior) with no heading of its own. Each newly appended
milestone note therefore adopted it: the QC-2 note on 2026-08-11, and the AP-8
note on 2026-08-12. A reader following "AP-8 is reviewed development code"
would have found app-launch rules underneath it.

Pre-existing rather than introduced by this review, and recorded as such. Given
its own heading, with an explicit instruction to append future milestone notes
above it.

### Counter-review validation

- Full repository suite on the final tree: **3,456 passed, 0 failed, 0 skipped, 25 dependency warnings** in 839.89s, Python 3.13.14 / Streamlit 1.60.0

  An earlier counter-review run of the same tree showed one failure,
  `test_ml_evidence_operations.py::test_windows_verifier_accepts_a_freshly_installed_never_run_task`.
  It was a 30-second `subprocess.run` timeout spawning `powershell.exe`, not an
  assertion failure, and it happened because that run was competing with
  concurrently executing mutation suites and took 1:31:51 against the usual
  ~13 minutes. It passes in isolation in 8.35s and did not recur on the
  unloaded rerun recorded above. Recorded rather than dropped: together with
  the Briefing `AppTest` timeout seen during implementation, it marks a
  standing fragility in the tests that shell out or drive Streamlit under a
  30-60s deadline. Neither is caused by AP-8, and neither is fixed by it.
- Focused: `tests/test_ticker_verification.py` + `tests/test_recommended_stocks.py`
  78 passed; `tests/test_ui_ticker_suggestions.py` 4 passed.
- Every correction above mutated and confirmed to redden exactly its own test.
- No operator state read or changed. Still not deployed;
  `paper-epoch-004` remains on `b837374`.
