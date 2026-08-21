# Counter-review: the MPQ and HPQ plan proposals

Status: **both plans ACCEPTED as proposals, with pre-freeze
corrections applied in this round.** Prepared: 2026-08-19. Author:
Claude, counter-reviewing Cursor Grok 4.6's docs-only branch
`user/cursor/max-profit-hedge-plans-20260819` (commits `04c916f`,
`03ed474`, base `5694975`). No QC access; no code exists for either
family. The plans are DRAFTS pending the owner freeze, so corrections
belong in the documents now — after the freeze they would need new
named preregistrations.

## 1. What was reviewed

Four documents: `docs/Plan/MAX_PROFIT_POLICY_QC_PLAN.md`,
`docs/Plan/Research/MAX_PROFIT_POLICY_2026-08-19_PREREGISTRATION.md`,
`docs/Plan/HEDGE_POLICY_QC_PLAN.md`,
`docs/Plan/Research/HEDGE_POLICY_2026-08-19_PREREGISTRATION.md`, plus the
branch's action-plan rows and handoff section. Both commits
dispositioned: accepted.

Strengths, verified line by line: correct PROPOSED posture with owner
freeze required before any code; own families explicitly outside the
closed A-002 program; one-run-one-pass look budgets with refusals
counted; caps stated as cap-and-target (SOXL 20%, SH 20%); union
alignment and `_drift_turnover` reuse; daily-reset decay disclosure
(MPQ) and the SH decay note (HPQ); the HEDGE-1 UI firewall stated in
both directions; forbidden-after-output lists that anticipate the real
temptations (rotating to the winner, raising caps, second passes);
HPQ's gate algebra spot-checked (H0 −20% → threshold −18%, consistent
with "≥10% relative"); window regime-conditioning disclosed.

## 2. Findings and dispositions

| ID | Priority | Status | Finding | Resolution |
|---|---|---|---|---|
| MHP-001 | P2 (record) | FIXED this round | The branch was based at `5694975` (pre-APQ-4), so its handoff section was numbered **7be — a collision with merged main's 7be** — and its §8 rewrite regressed main's current state; auto-merging would have duplicated sections and resurrected a stale "APQ-4 in flight" status. | `origin/main` merged into the branch; both conflicts resolved keeping main's sections; the plans section renumbered **7bi**; §8 rewritten current; every action-plan row from BOTH parents verified present (SHW4-001 lesson). |
| MHP-002 | P2 (substance) | FIXED this round (pre-freeze label) | MPQ's composite gate ("net CAGR higher than G0") is **beta-dominated**: a 3x product clears it in nearly any net-up window and fails it in nearly any net-down window — it measures the tape, not the policy. The draft's own section 2 discloses path-dependence but the gate itself carried no such label, inviting a "pass = leverage worked" misreading (the Stage 0/1 long-only lesson). | A descriptive-classification label added to the gate in the preregistration: no p-value, no statistical claim; a pass is a leverage/beta reading conditional on this tape. Only the optional bootstrap family (0.05/3, report-vs-omit frozen at MPQ-2 review per the APQ precedent) carries significance. HPQ's composite gate got the same label for consistency, though its risk-shaped clauses are less beta-exposed. |
| MHP-003 | P3 | FIXED this round | Both plans' sequencing guards ("do not start while APQ-4 is in flight") were **already obsolete when pushed**: APQ-4/5 completed and the family closed (A-003) the same day, invisible from the stale branch base. | Sequencing text replaced in both plans and both action-plan rows: start only when the owner freezes and schedules; LEV-2 is the currently scheduled QC-code milestone. |
| MHP-004 | P3 | FIXED this round | MPQ-3 said "add a second universe-free family beside `defensive_carry`" — **factually wrong**: `defensive_carry` is the overlay shadow stream, not a driver family; the existing universe-free driver family is `allocation` (APQ-3), with LEV's arriving at LEV-2. | Corrected in the MPQ plan. |
| MHP-005 | P3 (disclosure) | FIXED this round | **MPQ overlaps the frozen LEV family**, drafted the same day and invisible from the branch base: LEV's L0 (TQQQ buy-and-hold) vs SREF (SPY) descriptives already contain MPQ's G1-vs-G0 question on the longer 2011+ window. Not a defect — different window, mixes, and SOXL satellite — but the owner should decide MPQ with this known, since two families observing TQQQ-vs-SPY statistics in close succession is family proliferation even when each is separately gated. | Cross-referenced in the MPQ preregistration, the action-plan row, and here. Run-level looks remain globally counted, which is the structural protection. |
| MHP-006 | P3 (disclosure) | FIXED this round | BTAL is thin for its class; the flat bps cost grid may understate realized spread for H3. | Liquidity note added to the HPQ instrument table: read H3's net rows as optimistic. |
| MHP-007 | P3 | FIXED this round | Minor wording: MPQ-2 said "same JSONL contract as APQ" (the APQ analyser emits a single JSON report). | Corrected. |

## 3. Recommendation to the owner

Both families are honest, well-scoped proposals. Decision points:

- **HPQ** asks a question nothing else in the program covers (inverse /
  anti-beta overlay) with risk-shaped gates; its main caveat is the
  2022+ window (one crash, one rebound).
- **MPQ**'s question is partially covered by LEV descriptively; its
  marginal content is the mixes (G2/G3) and the SOXL satellite. If
  adopted, adopt it knowing a composite-gate "pass" is a beta reading —
  the optional bootstrap cells are where any non-trivial finding would
  have to live, and the APQ precedent (ratify reporting at the *-2
  review) applies.
- Neither plan authorizes code: MPQ-1/HPQ-1 start only on your freeze
  and schedule, and the current QC-code milestone remains LEV-2.

## 4. Scope not touched

No QC, no code, no operator or shadow database. The stale-process app
ImportError diagnosed mid-round is unrelated to these plans (records
in handoff §8's operational notes).
