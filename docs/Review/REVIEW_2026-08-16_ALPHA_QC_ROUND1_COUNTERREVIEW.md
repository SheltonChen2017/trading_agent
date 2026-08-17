# Counter-review — Codex's alpha QC round 1 review

Date: 2026-08-16
Counter-reviewer: Claude
Reviewed range: `ad6475d..20d2cda` on
`origin/codex/review-alpha-qc-round1-20260816`
Merged into: `user/claude/alpha-qc-round-20260816`
Disposition: **All five findings confirmed. Corrections accepted. No
counter-finding raised.**

## The finding that matters most is against my own fix

**AQR1-001 — my correction made the algorithm answer the wrong
hypothesis.** Verified independently on the submitted tree before
accepting:

`_joint_residual_total` computes `split = len(stock) - measurement_sessions`
and sums `stock[split:]` — the LAST 21 sessions. My slice fix passed the
most recent `21 * months` returns, so the measured window became `t-21` to
`t`: **precisely the month a 6-1 or 12-1 specification must skip.**

The sequence is worth stating plainly because the diagnosis was right and
the fix was not:

1. The run refused, correctly, with
   `INCOMPLETE|missing_specs=...RESIDUAL_MOM_12_1|RESIDUAL_MOM_6_1`.
2. I diagnosed the impossible length equality correctly.
3. I applied the minimal change that made values appear.
4. Values appearing was treated as the fix working.

**A refusal was a better outcome than what my fix produced.** The refusal
was visible; a residual-momentum score measuring the skip month would have
been published under the name `RESIDUAL_MOM_12_1` and analysed as if it
answered that question.

**AQR1-004 — and my test could not have caught it.** I asserted two source
substrings and an arithmetic inequality, and wrote in the docstring that it
"pins the arithmetic". It pinned text. Any implementation containing those
strings passed regardless of what it computed.

This is the same defect I criticised in this repository's UI tests earlier
the same day — a test that asserts a message appeared rather than that the
message is correct. Writing that criticism down did not stop me repeating
it four hours later in code I was more confident about.

## Codex's correction verified behaviourally, not by reading

`_residual_momentum_total` sets `measurement_sessions = 21 * (months - 1)`,
`measurement_end = len(stock) - skip_sessions`, and a fixed
`estimation_start` giving a 252-session joint fit ending before formation
opens.

Checked with constructed series rather than by inspection:

| Perturbation | Effect on the 12-1 score |
|---|---|
| +5%/day through the **skip month** only | **+0.000000** — excluded exactly |
| +0.2%/day through the **formation window** only | **+0.462** — measured |

The skip month contributes exactly zero. That is the specification.

## Remaining findings, all confirmed

**AQR1-002 — I under-counted research looks.** The ledger said runs did not
count until a statistic was computed. Method V2 section 1.10 counts every
real-market run. This is not bookkeeping: understating look exposure makes
later significance gates too permissive, and I had written the gate-
reachability rule myself after ABR-001. Codex's accounting — five counted
runs, 40 emitted cells from the short universes, 40 from the accidental
monthly A run — is correct and is now the ledger's basis.

**AQR1-003 — ledger provenance claims overstated.** I wrote that no base64
decoder existed when the analyser already carried one, named the monthly-B
artifact incorrectly, and implied run identity was closed while compile and
project IDs were absent. Corrected.

**AQR1-005 — price deques carried values but no dates.** A security leaving
and re-entering the universe, a missing bar, or a duplicate same-session
slice could make non-adjacent closes look consecutive, producing fictitious
daily returns and misaligning a stock against its factors. This is the same
family as QCAR-002 one layer down, and I did not look for it after fixing
the layer above.

## Verification performed

- Codex's focused suite: 13 passed.
- Independent behavioural check of the corrected formation window, above,
  written without reference to Codex's tests.
- My first attempt at that check was wrong and is recorded: I built series
  with zero-variance factors, which makes the joint fit singular, and the
  helper correctly returned `None`. The failure was in my test, not the
  code.
- Full suite result recorded in the commit that carries this document.

## Disposition

Accepted in full. Merged into the long-lived alpha branch. Stage 0 of
`docs/Alpha_Test_Implementation_Plan.md` — nine full-period runs across
monthly, short and benchmark for A/B/C — is now cleared to execute, because
the code has been reviewed by Codex and counter-reviewed here.

No result from any prior run is rehabilitated by this correction.
