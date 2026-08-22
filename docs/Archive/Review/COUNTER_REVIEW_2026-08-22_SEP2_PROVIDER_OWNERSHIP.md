# Counter-review — SEP-2 provider ownership

Reviewer: Codex, 2026-08-22

Reviewed branch: `origin/user/claude/review-sep2-provider-20260822`

Reviewed head: `0a346a282bf6f4b0c979f6079d1d5df7a5bdffc3`

Submitted Codex head: `809aa0c9ca8002ff8df1eefbaff51518ab7f94fc`

**Verdict: accepted. No P0/P1/P2/P3 findings.**

## Exact range and commit dispositions

The fetched Claude head was stable before review. Its merge-base with the
submitted Codex head was exactly `809aa0c9ca8002ff8df1eefbaff51518ab7f94fc`.

| Commit | Disposition | Reason |
|---|---|---|
| `e78d02abccca78e3bd0b4eb442c60ff305138700` — Close SEP-2 provider-tranche review findings | **Accepted** | The exact shrinking ledger correctly generalizes the repaired supervisor check, the orphaned import removal is valid, and the plan now distinguishes the exact chain removed from the residual class. No issue found. |
| `0a346a282bf6f4b0c979f6079d1d5df7a5bdffc3` — Record the independent review of the SEP-2 provider-ownership tranche | **Accepted** | Every submitted commit has a disposition; the P0–P3 ledger, reproduced counts, limitations, and remaining SEP-2 work are internally consistent. No issue found. |

## P0–P3 ledger

No counter-review issue was opened. Claude's three resolved P3 findings remain
preserved in the independent review report; this counter-review does not erase
or reclassify them.

## Independent verification

- Focused operations, entry-point, project-boundary, active-document,
  ML-boundary, and runtime-identity tests pass **106/106** on Claude's exact
  head.
- A new `assistant.operations` import in a second research-hosted entry point
  makes the shrinking-ledger test fail with both importers named; restoring the
  tree returns it green.
- The residual ledger contains exactly `scripts/run_ml_shadow.py`; it neither
  hides the remaining debt nor silently treats it as acceptable.
- `assistant/operations.py` has no remaining `json` use after the dead import
  removal.
- The plan and handoff accurately state that the exact supervisor chain is
  gone while the same class remains through `run_ml_shadow.py`.

No provider, credential, licensed row, broker, operator database, scheduled
task, deployment, backtest, result, research look, or evidence epoch was
accessed or changed.

## Remaining scope

SEP-2 remains incomplete. The next bounded tranche removes the last broad
operational reach, extracts the provider-neutral portfolio-mandate contract,
and reduces the exact composition/crossing ledgers while preserving the
assistant compatibility surface and all trading authority boundaries.
