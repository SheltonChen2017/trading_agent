# Independent review — ACER-1 Benzinga vendor audit

Date: 2026-08-20
Reviewer: Codex
Source branch: `origin/user/claude/acer1-benzinga-audit-20260820`
Base: `8f681f9`
Exact reviewed head: `35efda1b6f477eba697c99c76e665016792c0c9a`
Ordered range: `8f681f9..35efda1`
Review branch: `codex/review-acer1-benzinga-20260820`

## Outcome

**Accepted after correction.** Snapshot A remains useful evidence that the
feed has deep dated action history and meaningful pre-delisting coverage.
The review found three implementation defects in the evidence path and two
overstated conclusions. The corrected tool now authenticates the manifest
and its page/count graph, refuses unstable comparison identities, and parses
the actual timestamp formats. The records now keep timing, security identity,
and licence/third-party-transfer uncertainty explicit.

This review did not call Massive or QuantConnect, join prices, run a backtest,
or consume a research look. The machine-local Snapshot A was read only.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `13e8081` | **Accepted** | The two ACER documentation follow-ups are bounded process corrections; no product or research result changed. |
| `062f27f` | **Accepted after correction** | The download/audit structure and Snapshot A are valuable, but analysis trusted an unauthenticated manifest, comparison silently lost invalid identities, and timestamp evidence used lexical comparison across incompatible formats. ACER1R-001..003 correct these defects. |
| `eec4823` | **Accepted after correction** | It correctly separates personal use from commercial redistribution, but overcorrected by treating written clarification as courtesy and deletion applicability as unambiguous. The disclaimer is not a research ban; separate non-display, derived-work, and third-party clauses still require dataset-specific evidence before a QC upload. |
| `35efda1` | **Accepted after correction** | The measured era split is useful evidence. The conclusion that `last_updated` is an unambiguous UTC `Z` clock is false for the purchased payload, whose values are timezone-naive. ACER now uses a date-level next-session rule that does not depend on this inference. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---:|---|---|---|---|---|---|---|---|
| ACER1R-001 | P2 | Closed | `062f27f` | audit loader | Analysis verified page hashes but never verified `manifest.sha256`; completeness, page references, and row counts could be edited while still accepted. | A changed partition list with the old manifest hash was accepted; declared page counts were never compared with hashed content. | Snapshot completeness is load-bearing evidence and must fail closed on metadata drift. | Verify the manifest first; validate partition/page shape, termination, safe unique filenames, page hashes, result structure, and page/partition counts. | New manifest-hash and row-count refusal tests pass in `2274691`. |
| ACER1R-002 | P2 | Closed | `062f27f` | snapshot comparison | Missing IDs were dropped and duplicate IDs overwritten, concealing corruption or restatement evidence. | Synthetic A/B snapshots with blank or duplicate `benzinga_id` reached misleading output under the submitted implementation. | Snapshot B cannot measure restatement if its identity map silently loses rows. | Refuse missing, blank, or duplicate identities before emitting a diff. | Parametrized dangerous-direction test passes in `2274691`. |
| ACER1R-003 | P2 | Closed | `062f27f` | timestamp analysis | `MM/DD/YYYY ...` and `YYYY-MM-DDT...` values were compared lexically; the record falsely claimed zero reverse gaps. | Correct Snapshot A parsing finds 39 preceding, 557,748 same-date, 29,259 later-date, and 22,582 >90-day rows. | Incorrect availability evidence can create look-ahead in a backtest. | Parse observed legacy and ISO forms; report date-level facts; refuse the 39 reverse-order records. | Format regression test passes; corrected analyser reproduced all counts. |
| ACER1R-004 | P2 | Closed in design; implementation gate open | `35efda1` | audit §5 / handoff | A timezone-naive field was treated as an unambiguous UTC `Z` clock, making same-day eligibility unsafe. | Raw Snapshot A values lack offsets; +4/+5 hours supports but cannot prove the interpretation. | A signal must not trade before its availability is proved. | Freeze next-session eligibility after the later action/update date for every era. | Active records agree; ACER implementation test remains required before ACER-2. |
| ACER1R-005 | P2 | Closed in operating boundary; entitlement open | `eec4823` | audit §7 / action plan | The correction treated vendor confirmation as courtesy despite separate non-display/derived-work and third-party clauses. | The quoted all-caps paragraph is an advice disclaimer; no dataset-specific transfer entitlement is committed. | An unsupported QC upload could violate the data-use contract and destroy evidence continuity. | Continue local audit; keep reconstructable data local until order terms or permission cover QC; otherwise use local LEAN. | Canonical records agree; entitlement evidence remains an explicit ACER gate. |
| ACER1R-006 | P2 | Open milestone gate | `062f27f` | field/identity analysis | No delivered ISIN/exchange exists and rename/reuse is inconsistent; ticker/name joins cannot establish issuer identity. | All 596 pages lack both fields; FB/ANTM and BBBY reproduce the hazard. | A wrong issuer join assigns one company's ratings to another. | Require security-master cross-reference and ambiguity refusals before ACER-2. | Corrected analyser reports 100% missing ISIN/exchange; mapping not yet implemented. |
| ACER1R-007 | P3 | Closed | `062f27f` | validation record | The recorded full suite preceded final licence/prose edits. | The submitted handoff disclosed that ordering. | Final claims need validation against the tree that will be handed off. | Run full tests plus final document, compile, and diff checks after all edits. | Final counts recorded below and in the handoff. |

No P0 or P1 issue was found.

## Result and milestone effect

- Snapshot A is retained; it is not a performance result and consumes no
  research look.
- No ACER milestone completes. Snapshot B, issuer mapping, and the
  dataset-specific third-party-transfer boundary remain open.
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.
- The 39 reverse-order rows and any ambiguous issuer mapping are refusals,
  not silently corrected observations.

## Validation

- Corrected audit against immutable Snapshot A: 587,046 rows loaded with all
  manifest/page/count checks passing; the exact date and identity counts in
  ACER1R-003/006 reproduced.
- Focused audit and active-document suites: **45 passed**.
- Full suite after all substantive code and documentation corrections:
  **4,362 passed / 0 failed / 25 warnings** in 921.00 seconds.
- Required full-surface `compileall`: passed.
- Final focused document/audit rerun after inserting these validation counts:
  **45 passed**.
- `git diff --check`, staged-content inspection, ordered-commit inspection,
  clean-status check after commit, and shared-checkout branch/HEAD check:
  passed.

Python 3.13.14. The only warnings were one third-party `websockets` legacy
deprecation and 24 third-party Joblib/NumPy shape deprecations.
