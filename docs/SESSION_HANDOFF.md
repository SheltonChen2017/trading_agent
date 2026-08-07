# Development session handoff

Prepared: 2026-08-07, after independent review and correction of Claude's
GR-7c follow-ups (cash-flow skip + capture-frequency weight bias) on
`user/grok/review-gr7c-weight-bias-20260807`.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff
**and is therefore the wrong place for anything durable.**

> **Read `docs/OPERATIONAL_FACTS.md` first.** Standing owner decisions,
> machine-local operational knowledge, and engineering watch items live
> there because this file is rewritten every round. Do not copy them back
> into this file; link to them.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json`. Operational checkout pinned there.
**Never deploy development commits mid-epoch.**

`paper-epoch-001` is CLOSED (plumbing shakedown only; do not cite).

## 2. Latest outcome — GR-7c follow-ups accepted after correction

Claude tip `6cebe09` (merged via PR #164 as `fbc9ed2`) session-equalizes
the average invested weight. Prior counter-review `0e84c40` (PR #163)
refuses skips that drop external cash flows. **Both accepted after
correction.**

| ID | Pri | Result |
|---|---|---|
| GR7CFOLLOW-001 | P1 | **Fixed.** Snapshots store post-flow equity; attribution fed it to TWR as pre-flow. Pure deposit series reported **+33.3333%** into selection. Now `value_before_flow = total_equity - flow`, matching `portfolio_performance_report`. |
| GR7CFOLLOW-002 | P3 | **Fixed.** Payload now declares `average_invested_weight_method` / `_unit`. |
| GR7CFOLLOW-003 | P3 | **Fixed.** Human CLI no longer hardcodes "cash drag" when weight > 100%. |

Ledger: `docs/REVIEW_2026-08-07_GR7C_WEIGHT_BIAS.md`.
Claude quality: **8/10 submitted; 9.5/10 corrected**.

Prior GR-7c acceptance (`58a10ab`, ledger
`docs/REVIEW_2026-08-06_GR7C_ATTRIBUTION.md`) remains in force for
GR7CREV-001..005. CFPS-GR7C-001 skip refusal retained; it was necessary
but not sufficient without GR7CFOLLOW-001.

## 3. Validation (exact final tree)

- Focused `test_attribution`: **35 passed**.
- Mutation: old wiring fails deposit tests at `33.3333`; restored green.
- Full suite: **2955 passed / 0 failed / 0 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.
- Nothing deployed; ops checkout stays at `9a91498`.

## 4. What is next

1. Confirm `paper-epoch-002` observation accumulation.
2. Roadmap: **GR-6**, or **GR-7d** owner decision (rebalance targets).
   GR-7a/b/c reporting trio is complete after this follow-up review.
3. Optional later: surface attribution on the Reports page (not required
   for GR-7c DoD as scoped).
4. FPS-003 intermittent UI chrome title test remains open from earlier.

## 5. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Reports/CLI reporting must not write provider-fetch or execution evidence.
- Incomplete/insufficient samples must say so in the artifact.
- Selection residual is not a skill claim.
- Snapshot `total_equity` is post-flow; subtract `net_external_flow` before
  any `Observation.value_before_flow` mapping.
