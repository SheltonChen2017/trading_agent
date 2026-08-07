# Independent review — Claude QC-1 counter-review + news refusal honesty — 2026-08-07

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

## 1. Reviewed commits

Base: `2314d0b` (prior independent QC-1 acceptance).
Reviewed tip: `d6ba2b4`.
Review continues on: `user/grok/review-qc1-api-client-20260807`.

| Commit | Disposition |
|---|---|
| `d6ba2b4` Counter-review QC-1; make withheld news summaries state their reason | accepted after correction (CNEWS-001..003) |

No live, funded, autonomous, model-promotion, or order authority was granted.
Operational checkout stays frozen at `9a91498` under `paper-epoch-002`.

## 2. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CNEWS-001 | P1 | Resolved | `d6ba2b4` | `_reject_unsafe_prose` number verdict | Unsupported-number reason interpolated model-invented figures (`…: 847`). Commit claimed fixed labels / withheld prose never travels; invented numbers reached the UI caption. | Model text with `847%` → reason contained `847`. | Partial defeat of the output guard on the fabrication class most likely to mislead. | Return fixed label only: `cites number(s) absent from the source data`. | `test_invented_numbers_do_not_travel_with_the_refusal_reason`; mutation restoring interpolation fails |
| CNEWS-002 | P2 | Resolved | `d6ba2b4` | `test_setup_operational_host.py` | Anthropic launcher lift had no name pin; dropping `ANTHROPIC_API_KEY` from the foreach array would stay green. | Existing test only asserted GetEnvironmentVariable/Set-Item shape. | Field incident this commit fixes must be regression-pinned. | Assert the three credential names in the lift array. | `test_generated_launcher_lifts_credentials_fresh_from_user_scope` |
| CNEWS-003 | P3 | Resolved | `d6ba2b4` | OPERATIONAL_FACTS + docstring | Facts claimed held names (AFRM/AEP/SPCX/NVDL) were outside known membership incorrectly; `with_reason` docstring still said “Returns None”. | Config membership check; source docstring. | Durable facts and contracts must match code. | Corrected membership/peer-mention explanation; docstring returns `(summary, reason)`. | Source review |

QC counter-review residual **CQC-001** (live `success:true` unverified) remains open/documented — accepted as fail-closed watch item.

## 3. What was confirmed sound

- News refusal reasons for missing headlines, missing key, exception **type only**, and action-language withhold.
- Buying UI shows caption on refusal; withheld prose not shown on the action-language path.
- Launcher lifts `ANTHROPIC_API_KEY` without echoing values.
- QC-1 counter-review of QCREV-001..005: accepted; independent mutations re-confirmed POST and success parsing.
- Allowlist scope left as owner decision rather than silently widened.

## 4. Quality score

Claude counter-review + news honesty submitted: **8/10**.
Corrected tree: **9.5/10**.

## 5. Validation

Windows, Python 3.13.

- Focused guard + launcher + QC: **91 passed**.
- Mutation: restoring number interpolation fails CNEWS-001 test; restored green.
- Exact final tree: **3014 passed / 0 skipped / 25 warnings**.
- `compileall` clean; review diffs `--check` clean.

Nothing deployed mid-epoch.
