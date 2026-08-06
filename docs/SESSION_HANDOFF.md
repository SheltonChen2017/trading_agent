# Development session handoff

Prepared: 2026-08-06 late afternoon, after independent review and correction
of Claude's GR-7c performance attribution on
`user/grok/review-gr7c-attribution-20260806`.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff
**and is therefore the wrong place for anything durable.**

> **Read `docs/OPERATIONAL_FACTS.md` first.** Standing owner decisions
> (`require_earnings_data`, the epoch re-bind, the SPY benchmark),
> machine-local operational knowledge (the launch script, the elevated
> task-swap script, the non-elevated `Disable` gotcha, where backups land),
> and engineering watch items live there because this file is rewritten
> every round. On 2026-08-06 the same seven facts were dropped by one
> rewrite, restored, and dropped again by the next — restoring them here a
> third time would have failed the same way. Do not copy them back into
> this file; link to them.

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

Claude then counter-reviewed those corrections (§6 of the ledger). All five
findings accepted. Two worth naming: GR7CREV-002 was worse than a silent
clamp — the code clamped under a comment claiming it would "clamp **and
report**", and it did not report; and GR7CREV-004 was self-inflicted drift,
help text left describing the sufficiency model that had been superseded.

| ID | Pri | Result |
|---|---|---|
| CFPS-GR7C-001 | P2 | **Fixed.** Skipping a valuation point dropped its external cash flow, silently reintroducing deposit-as-gain: the chain links across the gap and reads the deposit's equity jump as return. Reproduced at **+100%** on an account doubled purely by a deposit. Originally my own defect (the pre-existing "no benchmark close" skip had it); the new `cash > equity` skip widened it. All skip sites now refuse the report when a dropped point carried a non-zero or unreadable flow. |
| CFPS-GR7C-002 | P2 | **Fixed (structurally).** The seven durable facts restored into this handoff one round earlier were dropped again by the next rewrite. Rather than restore them a third time, they now live in `docs/OPERATIONAL_FACTS.md`, which is append-and-amend, and this file links to it. |

## 3. Validation (exact final tree)

Review tree (`58a10ab`): focused **35 passed**; full suite **2947 passed /
0 skipped / 25 warnings**.

Counter-reviewed tree (current):

- `test_attribution` **30 passed**.
- Full suite: **2950 passed / 0 failed / 0 skipped / 25 warnings** (618s).
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
