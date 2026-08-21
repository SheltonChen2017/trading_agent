# Independent counter-review — Claude documentation-lifecycle review

Date: 2026-08-21

Reviewer: Codex

Base mainline: `98e1d631e6458a3b68c956b9665e2486bbe5dda2`

Exact reviewed head: `cc05ce76676e9aa8798bf03bba39aa12ff881d7e`

Reviewed remote branch: `origin/user/claude/review-codex-doc-lifecycle-20260821`

Counter-review branch: `codex/counterreview-claude-doc-lifecycle-20260821`

## Outcome

**Accepted after correction.** Claude's eight findings are substantive and
the corresponding corrections are retained. Independent reproduction
confirmed the merged-commit reachability defect, the active-ledger location,
the historical capability split, and the lifecycle-guard direction.

Four counter-review findings required correction. One licensing premise was
too absolute: QuantConnect offers separate Download licences, so its terms do
not categorically prohibit local data. The selected Cloud architecture still
makes ratings transfer a blocking ACER-2 gate, but permission must cover the
exact representation uploaded rather than assuming raw rows are the only
restricted form. Claude's deliberately deferred CDR-003b guard gap was closed
with adjacent-sentence branch context and negation/history exclusions. A
second reproduction found the review-report migration count was off by one:
139 reports moved, 68 with content changes and 71 byte-identical. The current
resume prompt also continued asking the owner to authorize the cloud audit
that the corrected governing freeze already authorizes.

No vendor API, credential value, licensed row, price, outcome, backtest,
research look, broker, scheduled task, operational database, deployment, or
paper epoch was accessed or changed.

## Exact range and commit dispositions

Merge-base `98e1d63`; ordered submitted range `98e1d63..cc05ce7`:

| Commit | Disposition | Review |
|---|---|---|
| `b4129d22658cde0bee21f313ba21f97c5738e0dd` | **Accepted after correction** | All eight submitted corrections are retained. CDR-002's authorization repair is correct, but its claim that QC forbids the reverse data direction was overbroad; CDR-006's 140/69 scale was 139/68; the current resume prompt still asked for authorization that freeze §8 now grants. |
| `f14e15218435688f67753b3d292f83105f32fcb0` | **Accepted after correction** | The report accurately dispositions the reviewed Codex range and preserves its evidence. Dated counter-review notes correct the licensing premise and migration count without erasing the submitted record. Its CDR-003b risk judgement was reasonable, but the gap is now closed narrowly and regression-locked. |
| `cc05ce76676e9aa8798bf03bba39aa12ff881d7e` | **Accepted after correction** | The handoff is materially complete after correction. The propagated custom-data/reverse-direction wording, 69-report count, and stale request to re-authorize the already authorized audit were corrected, and the counter-review outcome is appended below. |

## P0–P3 issue ledger

| ID | Priority | Status | Location | Issue and impact | Evidence | Correction | Verification |
|---|---:|---|---|---|---|---|---|
| CDCR-001 | P2 | Corrected | `docs/research/ACER_2026-08-20_ACER0A_FREEZE.md` §8; review report; Action Plan; handoff | “QC's terms forbid bringing its data down” falsely converted the current project choice into a categorical licensing impossibility. “Ratings must go up as custom data” also implied that normalized events or derived features were automatically safe alternatives. This could distort an owner architecture or purchase decision. | QuantConnect's official licensing documentation distinguishes Cloud licences from separately purchasable Download licences for local storage/internal LEAN use. The current repository has no authorized Download route and Cloud remains the owner-selected engine. | Retain the blocking transfer gate, but require permission for the exact representation sent; record that raw/reconstructable rows, normalized events and derived features are not presumed exempt. State accurately that a local QC route would require separate entitlement and an owner engine reversal. | Governing freeze, Action Plan, review clarification and current handoff agree. Official source: https://www.quantconnect.com/docs/v2/cloud-platform/datasets/licensing. |
| CDCR-002 | P3 | Corrected | `tests/test_active_document_consistency.py` | The merged-commit guard missed the exact shipped shape because hashes and the current branch-status claim were in adjacent sentences. It also treated “not local-only” as an unreachability claim. A false handoff could merge again, while a correction could fail noisily. | Two focused regressions failed red on submitted head: the four prior-sentence hashes produced an empty set, while the negated claim produced a false hit. | Preserve same-sentence matching; add only an immediately prior sentence that explicitly names a `codex/` or `user/claude/` branch when the next sentence says “the/this/that branch remains/is …”. Exclude negated and explicitly historical states. Do not widen to paragraph scope. | Red: 2 failed / 1 passed. Green: 3 passed; final complete active-document suite 51 passed. |
| CDCR-003 | P3 | Corrected | Action Plan; Claude review report CDR-006; handoff §7cz | The report said 140 review reports moved and 69 changed, and asserted the count matched measurement. The exact rename diff contains 139 reports: 68 changed, 71 byte-identical. | `git diff --summary --find-renames=20% a1dc779^ a1dc779 -- docs/Review docs/Archive/Review`. The erroneous 140th item was the separately modified `docs/process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md` included by filtering a broader name-status listing for “Review”. | Current records use 139/68/71; a dated note preserves and corrects the submitted review record. | Exact rename summary totals reproduced independently; 68 + 71 = 139. |
| CDCR-004 | P2 | Corrected | `docs/SESSION_HANDOFF.md` current resume prompt; `tests/test_active_document_consistency.py` | CDR-002 widened governing freeze §8 to authorize the QC structural audit, but the most-read resume block still said “get owner authorization” and “obtain the owner's … authorization” before the same audit. That could stop the next authorized step or solicit an unnecessary duplicate decision. | The new relationship regression failed red on submitted/current handoff while confirming the freeze's authorization sentence. | Direct the already authorized narrow audit and require work to remain inside freeze §8; do not request a new authorization. Add a guard coupling the current resume block to the governing freeze. | Red: 1 failed. Green: 1 passed; complete active-document suite 51 passed; complete suite below. |

No P0 or P1 finding was identified.

## Generalized review and the owner's two gates

The **ratings-transfer gate is real under the selected architecture**. Before
ACER-2, the owner needs written evidence or applicable order terms that name
the Benzinga Analyst Ratings product, QuantConnect Cloud as the receiving
third party/processor, internal research/backtesting as the use, and the exact
representation allowed (raw rows, normalized events, derived features, or a
specified subset), together with storage, retention/deletion and output rules.
Until then no ratings-derived representation is uploaded.

The **QC cloud capability audit remains the next authorized technical step**.
Freeze §8 permits read-only, zero-outcome structural measurement of account
entitlements, coverage and field semantics. It still forbids a Benzinga
upload, price/outcome join, backtest, and research look. The audit may inform
whether the architecture is feasible; it does not itself close the transfer,
terminal-delisting-return, issuer-identity, provenance, or preregistration
gates.

## Validation

- Focused red reproduction on the submitted parser: **2 failed, 1 passed**.
- Corrected parser regressions: **3 passed**.
- Complete active-document consistency suite: **50 passed**.
- Historical capability split at detached `14a3a83`: **12 requirements, 1
  available, 6 unavailable, 5 unmeasured, 11 blocking,
  `acer2_runnable=false`**.
- All eight commits named by CDR-003 are ancestors of `origin/main`; the new
  active ledger exists, the old archived path does not, and no old live
  reference remains.
- Required `compileall` including `research/` and `tests/`: **passed**.
- Complete repository suite on the final exact tree: **4,491 passed, 0
  failed, 25 dependency warnings in 918.62 seconds** on Python 3.13.
- Repository reference scan found no obsolete **live** ledger reference; the
  sole old-path mention is the historical CDR-004 location inside Claude's
  review record. Final diff, staged-content, narrow-secret, remote-head,
  ordered-commit, clean-status and shared-checkout checks are performed before
  handoff.

No feature milestone completed; `docs/FEATURE_MILESTONE_RECORD.md` remains
unchanged.
