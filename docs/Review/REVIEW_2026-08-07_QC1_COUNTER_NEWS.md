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

## 6. Claude counter-review of this review

All three findings **accepted**; no corrections required. Each was
reproduced rather than taken on the review's word.

**CNEWS-001 is a genuine P1 and a precise hit.** Reproduced against
`d6ba2b4`: a model claiming "rise 847%" produced the verdict
`cites number(s) absent from the source data: 847`, so the fabricated
figure travelled into a UI caption whose entire purpose was to report that
the figure was fabricated. The commit message asserted "the withheld prose
never travels with the reason" — that assertion was false for one of the
three rejection paths.

The mechanism of the miss is worth recording, because it is the same one
this session has charged others with repeatedly. The test written to prove
the property, `test_the_withheld_prose_never_travels_with_the_reason`, used
`"You should buy NVDA now. SECRETMARKER should not appear."` — which
triggers the **action-language** verdict. One of three routes was exercised
and the conclusion was generalized to all three. A test that cannot fail on
the untested paths was treated as proof about them.

Generalized-instance check performed here: all three verdict returns in
`_reject_unsafe_prose` are now fixed labels with no interpolation, and the
other two callers are safe — `suggest_similar_tickers` records only a
suppressed-count, and `curate_recommended_tickers` writes the verdict to the
`ai_runs` audit table, which is now a fixed label too.

**CNEWS-003 is the one that should sting most.** The
`OPERATIONAL_FACTS.md` entry claimed NVDL, AFRM, AEP and SPCX were outside
the project's known ticker set. Verified: the known set holds 117 names
(`UNIVERSE ∪ LEVERAGED_ETF_TICKERS ∪ BASKETS`) and only QQQM and BBB are
absent. The stated cause of the withholding was therefore wrong, and it was
written into the file explicitly designed to outlive sessions — the worst
place in the repository to be confidently incorrect. The corrected entry
now attributes withholding to peer mentions inside the summary, which is
what the measurement actually showed.

**CNEWS-002** is a fair process point: the launcher lift had no name pin, so
dropping `ANTHROPIC_API_KEY` from the array would have stayed green and
silently reproduced the field incident it was added to fix.

Mutation results, run independently: restoring number interpolation fails
`test_invented_numbers_do_not_travel_with_the_refusal_reason`; removing
`ANTHROPIC_API_KEY` from the lift array fails
`test_generated_launcher_lifts_credentials_fresh_from_user_scope`. Both
restored green.

### Observation, not a required change

Suppressing the figure from the verdict also removes it from the `ai_runs`
audit trail, since the rejected text itself is never stored. For a
potential-injection event that is a small forensic loss. Keeping detail in
the audit record while sanitizing only what reaches the UI would be
strictly better, but it means threading two strings through a guard with
three callers — added complexity on a rarely-exercised path. Recorded
rather than built; UI safety is the correct priority if only one can hold.

**CQC-001** remains open and unchanged: `success is not True` is
fail-closed but still unverified against the live QuantConnect API.
