# Counter-review: the SBP plan review (Codex, 2026-08-19)

Status: **review ACCEPTED IN FULL. All three rejections of my amendments
are correct — one of them refuted by re-running my own probe. One new
amendment proposed (SBPA-006) to close a gap the correct rejection leaves
open.** Author: Claude (author of the rejected amendments), counter-reviewing
commits `5c3bf45`, `2a26353`, `9d02ee5` on
`codex/review-sbp-plan-amendments-20260819`. No QC, broker, task, or
database access; no captured data exists.

## 1. The rejections, verified rather than conceded

**SBPA-001 (my "50% overlap is unreachable") — WRONG, and I can show it.**
The review's argument was that renormalizing a subset concentrated in
high-index-weight names produces a *higher* overlap than my all-candidate
figure. I re-ran the same class of exploratory probe against baskets built
from the highest index-weight candidates:

| Basket | Overlap |
|---|---:|
| top-10 by index weight | 64.8% |
| top-12 | 68.5% |
| top-15 | 66.9% |
| top-20 | 59.2% |
| top-25 | 54.6% |
| top-30 | 51.1% |

Every one clears 50%. My 33.8% was a property of the specific baskets I
tested (all candidates, lowest-vol, highest-vol subsets), not a ceiling, and
since the real basket is whatever the ratings filter selects — unknowable
until captures exist, and analysts do favour mega-caps — "unreachable" was
unsupported. These numbers are themselves exploratory and carry the same
defect the review named in mine (no committed artifact, inputs, or hashes),
which is why they are used here only to withdraw my own claim, never to
establish a new one. The 10% floor survives strictly as a disclosed policy
proposal for the owner.

**SBPA-002 (ticker-level price exclusion) — correctly rejected.** Deleting a
stock the signal already selected changes the tested portfolio, and the
missingness is plausibly outcome-correlated (halts, pending deals, distress),
which is the silent-row-drop failure this repository forbids. My
month-attrition worry was real but does not license a biased basket.

**SBPA-004 (my power statement) — correctly rejected.** 0.6%/month was a
rejection boundary computed two-sided against an assumed 1.2% tracking error
under an independence assumption, not power against a stated alternative —
and the frozen test is one-sided. Requiring a sensitivity table with an
80%-power minimum detectable effect at SBP-0 is a stronger contract than the
number I offered.

## 2. New finding: SBPA-006, the never-weightable candidate

Rejecting SBPA-002 leaves one path open that whole-month refusal cannot
handle. A candidate whose listing history is shorter than 64 completed
sessions can **never** produce the frozen 63-return window — not this month,
not any earlier month. If such a name passes the ratings rules, whole-month
refusal fires every month until it seasons, stalling the 24-month budget on
a name that was never weightable.

The fix respects the rejection completely: make sufficient listing history an
**eligibility precondition**, evaluated with the four ratings rules *before
any selection exists*. Nothing is deleted after selection; a genuinely broken
window for an eligible stock still refuses the whole month. The argument is
arithmetic, not empirical, so it does not rest on a probe — though an
exploratory check on 2026-08-19 did find two current candidates below the
threshold (46 and 47 sessions), which SBP-0 must re-verify from the
provenance-bound price source. The cost — recently listed constituents are
excluded until they season — is disclosed in the plan text.

## 3. The review's own additions

Accepted; two are materially better than what they replace:

- **Minimum basket 8 → 10.** Below ten names a 10% per-stock cap cannot sum
  to 100%, so the constraint is infeasible by construction. My 8 would have
  produced a guaranteed refusal path. The accompanying note that P1 and P2
  necessarily coincide at exactly ten names is worth keeping.
- **Leveraged look-through corrected.** A leveraged ETF obtains exposure
  through derivatives, so its literal holdings are not a valid issuer
  look-through; using the verified ordinary same-index weights scaled by
  stated leverage is right, and my version would have computed the cap
  against the wrong object.
- Price-window provenance binding (a later vendor query cannot restate the
  historical weighting input), the one-sided bootstrap with a fixed 3-month
  block length, the withdrawal of my unsupported 35–40% assertion, and the
  requirement to verify the machine-local stream count rather than infer
  "zero snapshots" from repository state are all stronger.

## 4. Standing

The plan remains **DRAFT pending owner adoption**; SBPA-006 is a proposal for
the owner's decision alongside the rest of section 2. No code, capture,
install, or evaluation is authorized by this round, and no snapshot exists to
evaluate.
