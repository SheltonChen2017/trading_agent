# Counter-review: Codex's ACER documentation review

- Date: 2026-08-20
- Reviewer: Claude (counter-review of the review of its own round)
- Subject: `docs/Review/REVIEW_2026-08-20_ACER_DOCUMENTATION.md` and correction
  commits `e4bef19`, `73efc11`, `832b7cf`
- Reviewed branch: `codex/review-acer-docs-20260820`, exact head `832b7cf`,
  based on submitted head `f3b960d` merged to `origin/main` at `6cdb423`
- Counter-review branch: `user/claude/acer-review-counterreview-20260820`

**Snapshot deviation, recorded:** Codex's branch was local-only, in the
worktree `C:/git/customizedAgent/trading_agent_codex_acer_review`. The snapshot
was frozen by branching from the exact local object `832b7cf`; pushing this
branch publishes all three correction commits as ancestors, the same
freeze-by-push pattern used in earlier rounds.

## Verdict

**ACCEPTED.** All four findings are confirmed against the documents rather than
the report, both claimed mutations reproduce, and no test or finding was
deleted or weakened. Two of the four are defects in my own submitted round that
I would not have caught by re-reading my own text: ACERDOC-001 and ACERDOC-002.
Four counter-review items are closed here (ACRV-001..004); none reverses a
correction.

Codex also **visually rendered the source PDF and read all nine pages**, which
is stronger evidence of faithful representation than my own check — I read it
through a stdlib text extractor and flagged at the time that two formulas came
through garbled. Its finding that the Markdown contract faithfully represents
the narrative therefore rests on better evidence than my assertion did.

## Part 1 — verification of the four findings

| Finding | Verdict | Independent evidence |
|---|---|---|
| ACERDOC-001 (P3, stale SBP-first entry points) | **CONFIRMED — my error** | Handoff §0 on the submitted tree opened "Reordered 2026-08-20 for the Strong-Buy priority", named the Action Plan "(Strong-Buy first)", and told the reader item 3 was "the draft SBP contract awaiting the owner's SBP-0 freeze". I rewrote the Action Plan and added §7bv but never touched the reading list that a new session starts from, so the *entry point* still pointed at the superseded program while the plan behind it pointed at ACER. |
| ACERDOC-002 (P3, unverified machine-local absence) | **CONFIRMED — my error, and a repeat** | The ACER plan asserted "Zero snapshots exist and the scheduled task was never installed" while the Action Plan row I wrote in the same commit said the machine-local state "has still not been measured, so 'zero snapshots' remains an expectation rather than a verified fact". Two rounds earlier I corrected precisely this overclaim in my own draft; I then reasserted it in the new document. Absence from Git is not absence on the operational host. |
| ACERDOC-003 (P3, stale archive index) | **CONFIRMED** | `docs/reference/README.md` still advertised SBP as "**draft pending owner adoption**" and had no ACER row. The archive index is a documented entry point, so a reader starting there was routed to an owner decision that no longer exists. |
| ACERDOC-004 (P3, topology stopped at PR #285) | **CONFIRMED, structural** | `origin/main` resolves to `6cdb423` after PR #286. My text was true when written and false the moment it merged — the CCR-005 class this repository has now met four times in one session. |

**Mutation claims reproduced.** Reverting the index row to "pending owner
adoption" turns the new guard red; restoring it turns it green. Verified with
copy-based restores rather than `git checkout HEAD`, after that mechanism
destroyed uncommitted work earlier in this session.

**Nothing weakened.** No test was deleted, no prior finding reopened, and the
corrections narrow claims rather than broaden them: "closed before its first
capture" becomes "closed before its first *verified* capture", and "the task
was never installed" becomes a prohibition plus an explicit statement that the
state is unmeasured.

## Part 2 — counter-review findings (closed here)

| ID | Priority | Location | Finding | Correction and verification |
|---|---|---|---|---|
| ACRV-001 | P3 | the new index guard | `next(...)` raised `StopIteration` when the SBP row was missing entirely — an error with no message rather than a failure naming what vanished. This is the same defect as CRV-003, which Codex accepted from me one round earlier and then reproduced. A deleted row is a legitimate failure mode of this guard. | Rewritten to assert exactly one matching row with a diagnostic message, then index it. Both mutations re-verified: the reverted-status case and the deleted-row case now both fail with named assertions (`assert 0 == 1 ... found 0`). |
| ACRV-002 | P3 | ACER plan §2 | **My own overstatement, which the review did not flag.** The plan asserted that ETF scores "will be strongly collinear" — reasoning presented as established fact, with no correlation computed. That is the unsupported-quantity error that sank amendment SBPA-001, reproduced in the document that cites it as a lesson. | Rewritten as an explicit expectation, labelled "reasoning, not a measurement", with ACER-3 now required to measure realized cross-sectional correlation of ETF scores and report it beside any ranking result. |
| ACRV-003 | P3 | ACER plan §3.1, §5 | The correction correctly refuses to claim verified absence, but assigns the measurement to nobody, so the disclaimer could persist indefinitely while the closure quietly rests on it. | ACER-1's row now requires measuring the machine-local SBR state (task presence and snapshot count) on the operational host and recording it in `OPERATIONAL_FACTS.md`, with the gate noting the measurement is read-only and that finding snapshots would be a material discovery. |
| ACRV-004 | P3 | the review's Validation section | It reports "The full suite exited 0 on the final review tree; a separate collection counted 4,353 tests" — an exit code and a collection count, but no pass/fail/warning counts. `CLAUDE.md` §10 requires exact pass/skip/failure counts and warnings, precisely so a green claim can be checked. | Measured independently on the final counter-review tree and recorded in `docs/SESSION_HANDOFF.md` §7bx. |

No P0, P1, or P2 findings against the correction.

## Part 3 — judgment retained, not changed

The contestable call in my round stands and stays contestable: closing the SBR
capture stream is right for ACER's *primary* revision signal, but the source
document keeps consensus levels as a secondary feature, so a reader could
reasonably argue the cheap stream should have run anyway. That is why it is
recorded as an explicit owner decision in the plan's section 7 rather than as
a silent retirement, and why the capture code, tests and installer stay in the
tree.

## Validation

- `tests/test_active_document_consistency.py`: **36 passed**; the new index
  guard verified red on both mutations before and after hardening.
- Full-suite and compile results for the exact final tree are recorded in
  `docs/SESSION_HANDOFF.md` §7bx (originally numbered 7bw; renumbered
  2026-08-20 because the reviewed head's own section already used 7bw — the
  MHP-001 numbering-collision class, caught by Codex's follow-up).
- No product behaviour, schema, CLI, migration, research result, data
  purchase, QuantConnect access, broker access, scheduled task, deployment,
  epoch action, or operational database changed. ACER remains a DRAFT and
  ACER-0 remains the owner's decision.
