# Development session handoff

Prepared: 2026-08-05 (evening), after independent Codex review of GR-7a.
GR-7a annual tax reporting is complete after correction on
`codex/review-gr7a-tax-reporting-20260805`. All work is DEV-SIDE ONLY:
nothing was deployed to the frozen operational checkout, and
`paper-epoch-001` is unaffected.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Standing state: THE EPOCH (day 1 complete, do not disturb)

`paper-epoch-001` ACTIVE since 2026-08-05T18:27Z on frozen commit
`8a2233c` (lineage hash `71d228d9...a9ba2`; strategy
owner-directed-paper-policy 1.0.0; model_id `no-ml-model`; approved
mandate `693799c0...9487`). All five drills passed in-epoch. Session 1 of
60 is recorded. Operational checkout stays on `8a2233c` until
`paper-epoch-close`. Never deploy development commits mid-epoch.

## 2. Merged before this review

PR #154 closed GR-4. `main` base for GR-7a was `376175e`.

## 3. GR-7 split (unchanged)

| # | Item | State |
|---|---|---|
| GR-7a | Annual tax reporting export | **complete after independent review** |
| GR-7b | Idle-cash / mandate reporting | open |
| GR-7c | Performance attribution | open |
| GR-7d | Rebalance-to-target proposals | **BLOCKED ON OWNER DECISION** |

## 4. GR-7a — complete after independent review

Implementation: `user/claude/gr-7a-tax-reporting-20260805`
(`7dd55b6`, `365bb11`).
Review branch: `codex/review-gr7a-tax-reporting-20260805`.

Behavior after correction:

- Reporting layer over `tax_lots` / confirmed fills only.
- Decimal money via per-share multiplication (no float-product cents).
- Market-local tax year and exported timestamps.
- Wash-sale advisory flags only; basis never adjusted.
- Coverage in CSV/JSON; only live `source="alpaca"` may verify.
- Sample/manual portfolios and broker outages stay unverified with
  explicit reasons in the artifact.
- CLI keeps stdout as a pure artifact; summary/warnings on stderr when
  printing to stdout; exits 2 when incomplete/unverified while still
  writing the file.
- Reports page builds on demand without provider-fetch writes; hides a
  built report whose year disagrees with the picker.

Confirmed ledger: GR7AREV-001..007 (P0–P2, all resolved). Full
dispositions: `docs/REVIEW_2026-08-05_GR7A_TAX_REPORTING.md`.

**Claude counter-review (appended to that report):** all seven findings
independently verified — the P0 re-proven red with a fresh probe (sample
holdings, `source="manual"`, were labelled `verified=True`), the money P1
re-proven by measurement, and the rest by inspection; **6.5/10 accepted as
fair**. Four generalized-instance sweeps run: float-product conversions,
read-only surfaces calling the fetch-recording packet path, and fail-open
`assert any(...)` assertions all came back clean; the float-product class
does persist upstream in `tax_lots.py` itself (reaching the sell preview)
but was **measured at 2e-12 dollars worst case — $0.00 at cent
precision** — and is deliberately left for a future milestone rather than
refactoring core arithmetic mid-epoch.

**CRGR7A-001 (P2, resolved on the review branch):** the corrected rule
proved the snapshot came from *a* broker but not from **the account these
books belong to**. `reconcile_snapshot()` already refuses a foreign
account; the report ignored that binding, so a snapshot from another
Alpaca account could print a confident COMPLETE — or an INCOMPLETE that
sends the owner hunting for fills that were never missing (reachable: the
owner rotated credentials the same day). `account_binding_reason()` now
mirrors the ledger's rule and downgrades to unverified with an explicit
reason; four tests including a positive control and a direction-agreement
test against the ledger authority; mutation-proven.

Final validation (Windows, Python 3.13.14):

- Focused: 40 passed.
- Full suite: **2,840 passed / 1 skipped / 25 warnings** in 1565.90s.
- `compileall` and `git diff --check` clean.

Quality score: submitted **6.5/10**, corrected **9.3/10**.

## 5. What is next

1. Owner merge decision for the reviewed GR-7a branch. Under model 2 the
   merge deploys nowhere; operational checkout stays frozen.
2. Next open items: GR-7b, GR-7c, or GR-6. GR-7d still needs the owner's
   target-portfolio decision.
3. Epoch observations continue on the operational host.

## 6. Non-negotiable boundaries

- Paper trading only; never deploy mid-epoch.
- Reporting surfaces may not propose, approve, size, submit, or dismiss.
- Incomplete/unverified financial reports must say so in the artifact.
- Wash-sale output stays advisory.
- ML/LLM stays advisory/observational.

## 7. Machine-local state

Operational checkout frozen at `8a2233c`; launcher + four Interactive
tasks live. Operator database was not mutated by this review's
development work (tests used isolated databases).
