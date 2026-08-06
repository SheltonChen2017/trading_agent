# Development session handoff

Prepared: 2026-08-06 late afternoon, after independent review and correction
of Claude's GR-7c performance attribution on
`user/grok/review-gr7c-attribution-20260806`.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json`. Operational checkout pinned there.
**Never deploy development commits mid-epoch.**

`paper-epoch-001` is CLOSED (plumbing shakedown only; do not cite).

## 2. Latest outcome — GR-7c accepted after correction

Claude tip `1da4154` decomposes active return vs SPY into invested-weight
effect (cash drag when underinvested) and a labelled residual. **Accepted
after correction.**

| ID | Pri | Result |
|---|---|---|
| GR7CREV-001 | P2 | NaN cost/tax raised `ValueError` not `AttributionError` |
| GR7CREV-002 | P2 | CLI clamped cash>equity to invested=0 (hid corrupt rows) |
| GR7CREV-003 | P2 | Missing CLI read-only regression |
| GR7CREV-004 | P3 | Help text said valuation points; limit not positive-checked |
| GR7CREV-005 | P3 | "Cash drag" label lied when average weight > 100% |

Ledger: `docs/REVIEW_2026-08-06_GR7C_ATTRIBUTION.md`.
Claude quality: **8.5/10 submitted; 9.5/10 corrected**.

Surfaces: `assistant/attribution.py`, CLI `attribution`, storage
`list_portfolio_equity_account_keys()`. No Reports UI in this milestone
(ACTION_PLAN scoped to module + CLI). Sample remains insufficient until
≥20 independent sessions.

## 3. Validation (exact final tree)

- Focused: **35 passed**.
- Full suite: **2947 passed / 0 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.
- Nothing deployed; ops checkout stays at `9a91498`.

## 4. What is next

1. Confirm `paper-epoch-002` observation accumulation.
2. Roadmap: **GR-6**, or **GR-7d** owner decision (rebalance targets).
   GR-7a/b/c reporting trio is complete after review.
3. Optional later: surface attribution on the Reports page (not required
   for GR-7c DoD as scoped).
4. FPS-003 intermittent UI chrome title test remains open from earlier.

## 5. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Reports/CLI reporting must not write provider-fetch or execution evidence.
- Incomplete/insufficient samples must say so in the artifact.
- Selection residual is not a skill claim.
