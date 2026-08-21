# Counter-review: SHW-2 overlay runner review

Status: **counter-review complete. The review is VERIFIED; both P2
blockers and two P3s are FIXED in this commit series; one P3 is
partially accepted with a recorded declination.** Prepared: 2026-08-19.
Counter-reviewer: Claude (Fable 5), author of the range under review.
No QuantConnect run; no operator database opened; no scheduler install.

## 1. Findings verification and dispositions

| ID | Classification | Resolution |
|---|---|---|
| SHW2-001 | **Confirmed by reproduction.** The probe was re-executed: with DDD unpriced at the baseline session, the runner persisted an `available=1` baseline — and the consequence is worse than partial imputation alone: every later cycle's previous boundary is permanently unpriceable, an R-017-class series death at t0. | **FIXED**: the baseline refuses unless EVERY universe and carry member has a finite positive close on the target session, writing a refusal row that names the tickers; because no available row exists yet, the stream retries the baseline at the next month-end and HEALS (pinned by test). Reverse mutation (check removed) red, restored green. |
| SHW2-002 | **Confirmed by reproduction.** After a Feb→May gap, `mature` settled the pair as `monthly_returns` universe = 1.0 — a three-month span that SHW-3 would count as one month's evidence. | **FIXED**: maturity now requires ROW adjacency (gap and refusal rows occupy their cycle slots, so any intervening row disqualifies the pair) AND calendar adjacency (the later cycle must fall in the immediately following month — belt and braces should a gap slot ever lack its refusal row). The reproduced fixture now matures zero outcomes (pinned by test). Reverse mutation (both guards removed) red, restored green. |
| SHW2-003 | **Confirmed.** The closed-stream gate existed but was untested. | **FIXED**: a test registers a `closed` epoch and pins that `observe` exits 1 with a `shadow_overlay` alert. |
| SHW2-004 | **Confirmed.** Design said scheduler wiring was SHW-2; the implementation deferred it. | **FIXED**: the design's SHW-2 bullet now defers scheduler installation to SHW-4, where a registered stream exists to schedule. |
| SHW2-005 | **Partially accepted.** | **PIT half FIXED**: `OverlayObservation` gains a structural `point_in_time_data` field whose only representable value is `False` — a caller cannot assert point-in-time status (the CLAUDE.md rule), and every persisted payload carries the marking; contract refusal mutation-verified. **Decimal half DECLINED, with rationale**: the registration already stores `carry_weight` and `band_fraction` as Decimal strings (the frozen configuration); the runtime band arithmetic operates on observation ANALYTICS — index levels and drifted weights derived from float market closes — not on an authoritative money path (no order, budget, or book derives from these values), matching the float convention of the ML shadow layer and the research analysers. Converting the drift arithmetic to Decimal would imply a precision guarantee the float close inputs cannot support. If any future milestone gives these values financial authority, that milestone must revisit this. |

## 2. Review-quality verification

- The reviewer's reverse mutation (baseline `month_ends[0]`) matches the
  test it cites; both P2 probes reproduced here exactly before fixing.
- Per-commit dispositions cover the full `d4c04c4..354a233` range; the
  review's non-findings (import boundaries, dirty-tree alert,
  idempotency, POST-001 re-validation intact) were all established by
  tests that remain green after the fixes.
- The review correctly kept SHW-3 and live epoch registration blocked;
  with SHW2-001/002 fixed and mutation-verified, that blocker is
  discharged pending this round's own review.

## 3. Verdict

The review stands as the review of record for `d4c04c4..354a233`; this
round (review record + fixes) extends the branch. SHW-3 may proceed
once these fixes pass review. Nothing here authorizes SHW-4 stream
start, gate freezing, scheduler installation, or any order.
