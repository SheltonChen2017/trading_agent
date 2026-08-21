# Counter-review — Codex's ACER-1 Benzinga audit correction

Date: 2026-08-20
Reviewer: Claude
Reviewed work: Codex commits `2274691`, `9dcd54f`, `0f3e0a4` on
`codex/review-acer1-benzinga-20260820`, merged to `main` by the owner via
PR #288 (merge `7ab2f80`). Reviewed record:
`docs/Archive/Review/REVIEW_2026-08-20_ACER1_BENZINGA_AUDIT.md`.
Counter-review branch: `user/claude/acer1-audit-counterreview-20260820`.

## Outcome

**Accepted after one factual correction.** Every structural hardening Codex
made is real, correctly implemented, and verified here end to end against
the immutable Snapshot A; every count in its review reproduces exactly by
independent reparse. One finding (ACER1R-004) rests on a false factual
premise — the claim that delivered `last_updated` values are timezone-naive
— which a byte-level census disproves. The premise propagated into three
active documents and is corrected in this round. The frozen date-level
timing rule survives on its honest rationale (conservatism), so no design
outcome changes.

This counter-review made no API call, no price join, no backtest, consumed
no research look, and touched no operational state. Snapshot A was read
only, via its hash-verified manifest and directly at the byte level.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `2274691` | **Accepted after correction** | Manifest authentication, structural validation, row-count-graph checks, and comparison identity refusals are all confirmed defect fixes (ACER1R-001/002) and pass end to end on the real snapshot. The date-level update facts are correct and reproduce exactly. The only defect is framing: the parser docstring claimed legacy `MM/DD/YYYY` timestamps were "observed"; none exist in Snapshot A (CCRV-002). Behavior and tests are correct and unchanged. |
| `9dcd54f` | **Accepted after correction** | The review record's dispositions, ledger discipline, and validation are sound. ACER1R-004's premise ("values lack offsets") and ACER1R-003's stated mechanism (mixed-format lexical comparison) are factually wrong against the raw bytes (CCRV-001), though ACER1R-003's corrected counts and the reality of the original zero-negative-gaps error are confirmed. The record itself is retained unedited per the never-delete rule; this counter-review and the corrected active documents carry the correction. |
| `0f3e0a4` | **Accepted after correction** | The handoff sections are accurate except where the CCRV-001 premise propagated (7by bullet, 7bz summary, action-plan paragraph) and the since-superseded "local-only" status of the review branch. Corrected in section 7ca and the touched documents. |

## Verification of Codex's findings

| Codex ID | Verdict here | Evidence |
|---|---|---|
| ACER1R-001 | **Confirmed, fix verified** | Read the hardened `_load_manifest`/`_load_rows`; ran `analyse` end to end on Snapshot A — all manifest, page-hash, safe-filename, duplicate-reference, result-shape, and page/partition row-count checks pass on the real 596-page snapshot; refusal tests pass. |
| ACER1R-002 | **Confirmed, fix verified** | `compare` now refuses missing, blank, and duplicate `benzinga_id`; the parametrized dangerous-direction test passes. |
| ACER1R-003 | **Counts confirmed exactly; mechanism misdescribed** | Independent reparse of all 587,046 rows reproduces 557,748 same-date / 29,259 later / 39 reverse-order / 22,582 >90-day to the row. The original "zero negative gaps" claim was genuinely false. But no `MM/DD/YYYY` value exists in the payload, so the claimed mixed-format lexical comparison cannot be the mechanism; the real original defect was never measuring the before-direction at date level, plus trailing-`Z` making equal instants compare "later". |
| ACER1R-004 | **Premise overturned (CCRV-001); frozen rule kept** | Byte-level census: 587,046 of 587,046 `last_updated` values are ISO-8601 `Z`; zero legacy, zero missing. The naive example `10/09/2023 12:28:43` matches PowerShell `ConvertFrom-Json` culture-rendering of a `Z` timestamp — a display artifact. The era-split offset measurement is restored to "strong internal evidence, not vendor-confirmed" (a `Z` could in principle be stamped by a naive serializer). The date-level next-session rule stays frozen on conservatism alone. |
| ACER1R-005 | **Accepted unchanged** | A boundary judgment, not a factual claim: raw/reconstructable data stays off QC until dataset-specific permission exists; local LEAN fallback. Consistent with the preserved ToS bytes. |
| ACER1R-006 | **Confirmed and sharpened** | The `isin` and `exchange` keys do not exist on any row (not merely empty); 17 rows lack `company_name`. Security-master joins with ambiguity refusals remain mandatory before ACER-2. |
| ACER1R-007 | **Confirmed closed** | Codex's final validation ordering follows the corrected rule. |

## Counter-review issue ledger

| ID | Priority | Status | Location | Issue | Correction |
|---|---:|---|---|---|---|
| CCRV-001 | P2 | Fixed this round | audit record §5; `docs/ACTION_PLAN_2026-08-20.md`; handoff 7by | Active documents state that delivered `last_updated` values are timezone-naive legacy strings; all 587,046 are ISO-8601 `Z` on the wire. A future implementer reading the record would design against a format that does not exist and discount the era-split evidence for a wrong reason. | Corrected in place with dated correction notes; the frozen date-level rule is explicitly re-based on conservatism; Codex's review record is retained unedited and this record carries the dispute. |
| CCRV-002 | P3 | Fixed this round | `scripts/audit_benzinga_ratings.py` | Parser docstring claimed legacy timestamps were "observed Massive legacy timestamps". | Reworded as defensive parsing with the measured census; behavior and the format regression test are unchanged. |
| CCRV-003 | P3 | Recorded only | review record ACER1R-003 | The defect-mechanism narrative (mixed-format lexical comparison) is impossible in this payload. The corrected counts and the underlying original error are real, so no disposition changes. | Recorded here; the review record stays unedited per the never-delete rule. |

No P0 or P1 issue. No regression test pins CCRV-001 because the falsehood
concerns machine-local snapshot bytes CI cannot see; the audit record now
carries the reproduction method (byte-level format census plus date-gap
reparse) so any holder of a snapshot can re-verify.

## New measurement recorded

Each of the 39 reverse-order rows has `time` matching its update instant's
US-Eastern wall clock within 25 seconds to ~9 minutes, while `date` sits one
day after the update's UTC date (example: `2023-08-09 14:17:26` against
`2023-08-08T18:17:51Z`, which is 14:17:51 EDT). This is a systematic
next-day-dating anomaly, not random corruption, and it is additional
internal evidence that modern `time` is genuine US Eastern and `last_updated`
genuine UTC. Refusal remains the correct handling for these rows.

## Result and milestone effect

- No ACER milestone completes; ACER-0 and ACER-1 remain open exactly as the
  action plan states (Snapshot B, issuer mapping, dataset-specific transfer
  terms, owner freeze).
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.
- The vendor-audit review chain (audit → review → counter-review) is closed.

## Validation

Recorded in `docs/SESSION_HANDOFF.md` section 7ca on the final tree.
