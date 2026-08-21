# Counter-review: APQ-2 analyser review

Status: **counter-review complete. The review is VERIFIED; the ratified
reporting decision stands; both P3s are closed.** Prepared: 2026-08-19.
Counter-reviewer: Claude (Fable 5), author of the range. No QC, no real
log, no APQ-3 change.

## 1. Findings

| ID | Classification | Resolution |
|---|---|---|
| Reporting decision | **Ratified as implemented** — the excess-mean family is IN the schema (3 cells, 0.05/3, both labels), fixed before any run; the reviewer's framing is recorded: striking it later would be a new schema, never a post-result choice. | Binding. |
| APQ2-001 (P3) | **Confirmed by reproduction**: with turnovers [0.0, unavailable, 0.0, 0.0], the reported skipna `mean_turnover` is 0.0 while the net blocks charge a 0.25 mean — the descriptive mean understates costed activity whenever unavailability fired. | **Closed as documented** at the plan's APQ-5 section, exactly per the reviewer's correction guidance: read beside `unavailable_turnover_periods`, never alone; substituting the charged mean is a later, separately reviewed schema version. No product change pre-run. |
| APQ2-002 (P3) | **Confirmed** — my handoff §8 was stale again (third occurrence of this class); the reviewer's commit repointed it at APQ-3. Verified at HEAD. | Closed by the reviewer. Standing note to self: §8 must be touched in the SAME commit as any new 7-series section. |

## 2. Review-quality verification

The reviewer's fillna mutation re-run: RED on the magnitude pin,
restored green, 9 passed. The non-findings were spot-checked: the
transitive `ml.evaluation` import arrives via the reviewed
`run_alpha_battery_20260815` helper (analyser scripts are not
execution-capable modules; the boundary tests are unaffected), and the
bootstrap path refuses under 24 observations independently of the
parser floor.

## 3. Verdict

The review stands as the review of record for `92a0077..5364ae6`.
APQ-2 is complete, reviewed, and its schema frozen by ratification.
**APQ-3 (the launch-driver hook) is next** — still no QC; APQ-4's
single cloud run stays owner-gated behind the APQ-1..3 review chain.
