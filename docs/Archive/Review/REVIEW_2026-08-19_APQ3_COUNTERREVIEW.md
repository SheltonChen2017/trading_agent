# Counter-review: the APQ-3 independent review

Status: **review VERIFIED; APQ3-001 closure confirmed live; APQ3-002
confirmed, GENERALIZED to three instances, and closed; APQ3-003
acknowledged.** Prepared: 2026-08-19. Author: Claude (implementer),
counter-reviewing `docs/Archive/Review/REVIEW_2026-08-19_APQ3_DRIVER_HOOK.md`
(Cursor Grok 4.6, review commit `6a2d2da` on
`user/cursor/review-apq3-20260819`). No QuantConnect access.

## 1. Verification of the review itself

- Range and head match: the review dispositions exactly `95a7210..1a63c8c`
  (two commits), the pushed APQ-3 branch head.
- The reviewer's two mutation re-runs match my implementation-round
  results exactly (mutation A: 3 red including the launch-precondition
  retarget test; mutation B: QCS0CR-002 red). Driver suite 18 passed,
  re-confirmed on this tree.
- The reviewer's handoff §7bc / §8 rewrite and action-plan row update
  were read line by line against the report: consistent, no dropped
  rows (SHW4-001 lesson applied).
- Explicit non-findings section spot-checked: allocation launch cannot
  reach `_retarget_universe` (code path), the uploaded-bytes hash is of
  the unchanged source, and the SHW4-004 denylist is intact.

## 2. Finding dispositions

### APQ3-001 (P2, closed by the reviewer) — CONFIRMED, including live

The documented repair one-liner omitted the installer's three mandatory
path parameters. This was independently confirmed **in production
before the review landed**: the owner ran the short command and was
stopped at the `PythonPath:` / `DatabasePath:` prompts in real time;
the completed command (same three parameters the reviewer added to the
facts file) then re-registered all three tasks. The reviewer's facts
rewrite is correct and closure stands.

Post-closure live proof (this counter-review, on the operational host):

- all three `TradingAgent-Overlay-Shadow-*` tasks now show
  `LogonType=Interactive`;
- a manual `Start-ScheduledTask` of each task **actually ran and exited
  0** (under S4U even `schtasks /run` reported SUCCESS while the task
  stayed at the never-run sentinel);
- the runs were the expected "up to date" no-ops: `shadow_overlay.db`
  counts unchanged (1 registration / 1 baseline observation / 0
  outcomes) and the sufficiency artifact was rewritten at 15:45 local.

Remaining proof, deliberately left to the schedule: the first
**automatic** trigger firing (2026-08-20 14:45 local) demonstrates the
trigger construction itself; manual starts cannot prove that.

### APQ3-002 (P3, was open) — CONFIRMED, GENERALIZED, CLOSED

The reviewer found the paper installer source still defaulting to S4U.
The mandated sibling sweep (`grep S4U` across `scripts/*.ps1` — the
turnover-gate lesson: file-local copies of a defect class) found **three**
instances, two beyond the review:

1. `scripts/install_windows_operational_tasks.ps1` — `TaskLogonType`
   default `"S4U"` (the reviewer's instance);
2. `scripts/install_windows_ml_shadow_tasks.ps1` — same default;
3. `scripts/verify_windows_evidence_tasks.ps1` —
   `ExpectedTaskLogonType` default `"S4U"`: a defaults-run verification
   would FAIL correctly registered Interactive tasks and PASS an S4U
   misregistration — the verifier trap points the dangerous direction.

All three defaults are now `"Interactive"` with the incident comment.
The one test that relied on the verifier's S4U default (the mock
harness in `tests/test_ml_evidence_operations.py`, which invokes the
real verifier without `-ExpectedTaskLogonType`) was updated to mock an
Interactive principal — a contract change matching the only supported
host, not a weakening. Regression coverage:
`test_every_task_logon_type_default_is_interactive` in
`tests/test_operational_task_resilience.py` scans every `scripts/*.ps1`
for `TaskLogonType`/`ExpectedTaskLogonType` string defaults and refuses
any non-Interactive value; it includes a non-vacuity assertion (at
least one default found). Reverse mutation: flipping the ML-shadow
default back to `"S4U"` turns the test red; restored green.

The generated setup wrapper was never exposed (it passes both
parameters explicitly, test-pinned in `test_setup_operational_host.py`);
only defaults-run direct invocations were.

### APQ3-003 (P3, open) — ACKNOWLEDGED, no action

APQ-3 product and the overlay S4U record share one branch. The record
commit was a same-day operational discovery made while verifying the
overlay tasks' first firing, disclosed in the push summary; splitting
it retroactively would rewrite pushed history for tidiness. The
standing one-milestone-per-branch rule is reaffirmed; this
counter-review round (review-record verification + APQ3-002 closure)
stays on the reviewer's branch per the owner's round workflow.

## 3. Scope not touched

No QC launch, no analyser pass, no operator (paper) database access —
the shadow DB reads and task starts above touch only the dedicated
`shadow_overlay.db` and the already-authorized overlay tasks. APQ-4
remains the owner-executed single cloud run after this round merges.
