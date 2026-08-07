# Development session handoff

Prepared: 2026-08-06 evening, after a session on the **second machine**
(`HARRY_MELODY\shelt`) that stood that host up as a development standby and
implemented the GR-7d report-only slice on
`user/claude/gr-7d-rebalance-targets-20260806`.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff
**and is therefore the wrong place for anything durable.**

> **Read `docs/OPERATIONAL_FACTS.md` first.** Standing owner decisions
> (`require_earnings_data`, the epoch re-bind, the SPY benchmark, and now
> the GR-7d rebalance target), machine-local operational knowledge (the
> launch script, the elevated task-swap script, the non-elevated `Disable`
> gotcha, where backups land, **and the fact that there are now two
> machines**), and engineering watch items live there because this file is
> rewritten every round. Do not copy them back into this file; link to it.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json`. Operational checkout on the **epoch
host** (`REDMOND\sheltonchen`) pinned there. **Never deploy development
commits mid-epoch.**

`paper-epoch-001` is CLOSED (plumbing shakedown only; do not cite).

**New this round:** a second machine now exists and shares the same Alpaca
paper account. Its four scheduled tasks are installed but DISABLED, and it
has no ledger bootstrap and no epoch, deliberately. See
`docs/OPERATIONAL_FACTS.md` §2 before touching either host's scheduler.

## 2. This round's work — GR-7d unblocked and split

GR-7d was blocked on an owner decision, not on code: a cap is not a target,
and neither the mandate nor the policy contains a target allocation.

**Owner decided (2026-08-06)**, recorded durably in `OPERATIONAL_FACTS.md`
§1: equal weight across all 104 `UNIVERSE` tickers scaled to the policy
exposure ceiling; ±25% relative band, inclusive; both directions;
**report-only first**.

Three measurements drove the shape — the union of all 16 `BASKETS` is
*exactly* `UNIVERSE`; 30 tickers sit in 2–4 baskets so membership-weighting
would be an evidence-free mega-cap tilt; and `_check_basket_concentration`
caps every basket, so overlapping baskets make single-basket targets breach
a basket they never aimed at.

**Implemented (awaiting independent review):**

- `assistant/rebalance.py` — pure Decimal drift math, no float in money
  paths, presentation rounding applied strictly *after* classification.
- `config.REBALANCE_TARGET_TICKERS` / `REBALANCE_BAND_PCT` — the explicit
  named list `ALLOCATION_SERVICE_DESIGN.md` §6 asked for, defined *from*
  `UNIVERSE` and pinned by a test so a research edit cannot silently
  enlarge the target portfolio.
- CLI `rebalance-report` — read-only, no `_packet(store=...)`, degrades on
  broker outage.

**Deliberately NOT implemented:** proposal generation, share counts, batch
execution, any UI surface.

## 3. Validation (exact final tree, commit `e973113`)

- `tests/test_rebalance.py` **54 passed**.
- Full suite **3004 passed / 0 failed / 0 skipped / 25 warnings** (249s).
- `compileall` clean; `git diff --check` clean.
- Second host, operational checkout at `63d38a8`: full suite **2950 passed
  / 0 failed / 0 skipped**.
- **Six reverse mutations applied, all caught**, tree restored and verified.
  One (a zero-target row falling through to "inside band") was **NOT**
  caught on the first pass and exposed a real coverage gap; two tests were
  added and it is caught now.

## 4. Review guidance

Range: the single commit `e973113` on
`user/claude/gr-7d-rebalance-targets-20260806`, based on `63d38a8`.
Adversarial attention is most useful on:

- whether any emitted field is action-shaped (the report must propose
  nothing, and computes no share counts on purpose);
- the zero-target / undefined-relative-drift branches, which are the
  fail-open direction and were the weakest tested area;
- band-boundary inclusivity and that classification never reads a rounded
  value;
- the read-only claim — the GR-4 provider-fetch write defect has now
  appeared on reporting surfaces twice (GR-7a, GR-7b); and
- whether the documented residual (equal weights cannot sum exactly to 50%
  across 104 names) is handled honestly rather than papered over.

## 5. What is next

1. **Resolve the target-vs-strategy conflict before any GR-7d proposal
   slice.** SOXX/SOXL (traded by `CONFIGURED_LEVERAGED_PAIRS`), NVDL and
   BBB are absent from `UNIVERSE`, so the target implies exiting positions
   another configured component exists to hold. Two components would
   propose opposite trades. This is an owner decision, not a code fix.
2. Open owner option: the target sits exactly at the exposure ceiling, so
   it has zero headroom and ordinary upward drift reads as a
   `max_total_exposure_pct` breach. Lowering the target below the ceiling
   is available.
3. Confirm `paper-epoch-002` observation accumulation on the epoch host.
4. Roadmap: **GR-6** (the second-machine standup above is real evidence
   toward its "stand-up proven once" marker; off-machine backup remains the
   smallest high-value slice), then GR-7d-propose once item 1 is resolved.
5. FPS-003 intermittent UI chrome title test remains open from earlier.

## 6. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Only the epoch host runs the operational cadence. Two hosts share one
  Alpaca paper account.
- Reporting may not propose/approve/size/submit/dismiss.
- Reports/CLI reporting must not write provider-fetch or execution evidence.
- Incomplete/insufficient samples must say so in the artifact.
- Selection residual is not a skill claim.
