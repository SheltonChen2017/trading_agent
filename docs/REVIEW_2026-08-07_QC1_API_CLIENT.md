# Independent review — QC-1 QuantConnect research client — 2026-08-07

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

## 1. Reviewed commits

Base: `610a3e9` (`main`, post GR-7c follow-up PR #165).
Implementation: `ba8ae6d`.
Review branch: `user/grok/review-qc1-api-client-20260807`.

| Commit | Disposition |
|---|---|
| `ba8ae6d` QC-1: QuantConnect research client, results-only by construction | accepted after correction (QCREV-001..005) |

No live, funded, autonomous, model-promotion, or order authority was granted.
Operational checkout stays frozen at `9a91498` under `paper-epoch-002`.
No live QuantConnect call was made during review (credentials still absent).

## 2. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| QCREV-001 | P1 | Resolved | `ba8ae6d` | `_default_transport` / `request` | No-payload calls used `urllib.Request(data=None)` → **GET**. QuantConnect documents every authenticated call as **POST**, including `authenticate` with `{}`. First live credential check would have failed the documented contract. | QC auth docs use `curl -X POST` / `requests.post`; urllib GET on `authenticate`. | Transport that cannot perform the documented smoke test is not a usable client. | Always POST; empty body is `{}` with `Content-Type: application/json`. | `test_authenticate_posts_empty_json_object`, `test_default_transport_uses_post_even_without_payload` |
| QCREV-002 | P2 | Resolved | `ba8ae6d` | `_assert_allowed` | Prefix `startswith("authenticate")` allowed `authenticateX`; `startswith("backtests/")` allowed `backtests/../data/read` before URL normalization. Licence boundary was not structural against traversal. | Parametrized paths reached `request` before refusal under the old rule. | Allowlist must survive normalization tricks or market-data paths become reachable. | Exact path set for `authenticate`; slash-terminated prefixes; reject `..`, `\`, `://`, `//`, NUL. | `test_market_data_and_unlisted_endpoints_are_unreachable` extended; mutation to loose prefix fails on `authenticateX` |
| QCREV-003 | P2 | Resolved | `ba8ae6d` | `request` success handling | HTTP 200 with missing `success` treated as OK (`is False` only). Fail-open on truncated bodies. | Body `{"backtests": []}` returned successfully. | QC signals success in-band; absence is not success. | Require `success is True`. | `test_missing_success_field_is_not_treated_as_success`; mutation restoring `is False` goes green incorrectly |
| QCREV-004 | P3 | Resolved | `ba8ae6d` | `read_backtest` / `list_backtests` / `__init__` | `bool` accepted as `project_id` (`True` → 1); blank `backtest_id`; non-finite/non-positive `timeout`. | `int(True)==1`; `str(None)=="None"`. | Same class as auth timestamp bool rejection already present. | Reject bool/non-int ids, blank ids, bad timeouts. | Parametrized refusal tests |
| QCREV-005 | P3 | Resolved | `ba8ae6d` | module docstring | Claimed pinning by "the shared import-boundary walker" in addition to the local AST test; that walker does not cover `research.quantconnect`. | `tests/test_ml_import_boundary.py` only roots `backtest.interactive` similarly. | Comments must not claim unenforced guarantees (CLAUDE.md §8). | Docstring now cites only the local AST pin. | Source review |

## 3. What was confirmed sound

- Results-only product intent and licence reasoning (OPERATIONAL_FACTS / README).
- Auth header algorithm vs independently recomputed vectors; token never on the wire.
- Credentials from env only on production path; `__repr__` redacts token.
- AST import boundary vs assistant/execution/risk/ml/signals/strategies.
- In-band `success: false` already refused (needed strengthening for missing key).
- No execution authority; research package only; nothing deployed mid-epoch.
- Offline tests with injected transport/clock — correct for machines without QC creds.

## 4. Quality score

Submitted: **8/10**.
Corrected: **9.5/10**.

Strong licence-first design and offline testability. Misses were the live POST contract, allowlist hardness, and fail-closed success parsing — exactly the failure modes that would show up on first real use or a clever path string.

## 5. Validation

Windows, Python 3.13.

- Focused: **53 passed**.
- Mutation: missing-`success` and loose-prefix allowlist each fail their regression tests; restored green.
- Exact final tree: **3008 passed / 0 skipped / 25 warnings**.
- `compileall` includes `research`; `git diff --check` clean for review files.

Nothing deployed mid-epoch. First live `authenticate()` remains unproven until `QC_USER_ID` / `QC_API_TOKEN` are set.

## 6. Claude counter-review of this review

All five findings **accepted**; no corrections needed. Two mutation-verified
independently rather than taken on the review's word: reverting the POST fix
fails `test_default_transport_uses_post_even_without_payload`, and reverting
`success is not True` to `is False` fails
`test_missing_success_field_is_not_treated_as_success`. Restored green at 53
passed.

**QCREV-001 is the one that mattered.** `urllib.Request(data=None)` issues a
GET, and QuantConnect documents every authenticated call as POST — so
`authenticate()`, the exact command the README tells the owner to run first,
would have failed on first contact. A client that cannot perform its own
documented smoke test is not usable, and no offline test could have caught
it: every test injects transport, so the real `_default_transport` was never
exercised until the reviewer looked at it. Adding
`test_default_transport_uses_post_even_without_payload` closes that blind
spot properly.

**QCREV-005 is a fair hit on comment honesty.** The submitted docstring
claimed pinning by "the shared import-boundary walker" alongside the local
AST test. That walker roots only `assistant`/`execution`/`risk` and
`backtest.interactive`; it does not cover `research.quantconnect`. A comment
asserting an unenforced guarantee is precisely what CLAUDE.md §8 forbids,
and it is the same defect this session already charged GR7CREV-002 with —
committed by the same author two milestones later.

### Residual, documented not corrected

| ID | Priority | Status | Issue |
|---|---|---|---|
| CQC-001 | P3 | Open (documented) | `success is not True` is **fail-closed but unverified against the live API**. If any QuantConnect endpoint returns a valid body without `success: true`, the client will refuse a good response. That is the safe direction and the right default, but it is an assumption about a contract nobody here has exercised — no live call has ever been made. Watch for it on the first real `read_backtest` / `list_backtests`, not just `authenticate`. |

No change made: loosening a fail-closed check on an unexercised contract
would trade a visible refusal for a silent wrong answer, which is the worse
error. Recorded so a first-call failure is read as this assumption rather
than as a credential problem.
