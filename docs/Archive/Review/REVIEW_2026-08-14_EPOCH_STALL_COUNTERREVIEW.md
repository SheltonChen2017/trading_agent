# Claude counter-review — Codex's correction of the epoch stall detector

Date: 2026-08-14
Reviewer: Claude
Base reviewed: `1babbcf` (current `main` / `origin/main`, PR #221)
Commits under review: `4273de6` (product/test correction), `4cb3a0d` (records)
Counter-review branch: `user/claude/epoch-stall-counterreview-20260814`
Disposition: **Codex's correction accepted; four further defects found and
closed**

## Scope and method

Codex reviewed and corrected `6aa7069`, the read-only epoch stall detector I
submitted earlier the same day. This document reviews Codex's correction, not
my own original commit: every changed hunk in `4273de6`, the deletion in
`assistant/paper_evidence.py`, the CLI surface it added, the four tests it
added, the one existing test expectation it inverted, and the records commit
`4cb3a0d`.

Method, per `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`:

* every commit in the range received an explicit disposition — no tip-only or
  combined-diff review;
* each of Codex's seven findings was independently re-derived before being
  accepted, rather than taken on the strength of its own report;
* each correction was proven load-bearing by reverse mutation: revert the fix,
  confirm exactly the intended test reddens, restore in a `finally`-safe copy;
* the new tests were themselves mutation-tested, which is how the vacuous one
  was found; and
* each confirmed defect was then searched for generalized instances.

No database write, scheduled-task change, deployment, epoch transition, order,
broker request, or funded-account access occurred. The operator database was
opened read-only (`mode=ro`) twice, for observation only.

## Commit-by-commit disposition

| Commit | Author | Disposition | Result |
|---|---|---|---|
| `4273de6` | Codex | **Accepted after correction** | The central finding (CODSTALL-001) is real, correctly diagnosed, and correctly fixed; five of the remaining six are real defects in my submitted commit. Two of Codex's new tests do not test what they claim, one input-validation path is incomplete, and one boundary condition is now modelled twice with no test pinning the two together. |
| `4cb3a0d` | Codex | **Accepted after correction** | The review, milestone, and handoff records are accurate and complete for their moment. They went stale the instant PR #221 merged them, and the guard written to catch exactly that missed the phrasing used. |

## Codex's findings, independently re-derived

Each was re-established against the submitted tree before being accepted.

**CODSTALL-001 (P2) — confirmed, and the most important finding here.** My
`DEFAULT_CAPTURE_AFTER_CLOSE = 3h30m` modelled the capture as a duration after
the exchange close. It is not: `TradingAgent-Paper-PaperObservation` is a
fixed Windows wall-clock trigger. On the half day after Thanksgiving
(2026-11-27, close 13:00 ET) my model made the capture due at 16:30 ET —
three hours before the task can physically run — so a check in that window
would have reported a session missing that was never late. That is precisely
the false alarm this tool exists to avoid, and it would have arrived on a
holiday week. Reverse mutation: restoring the close-derived arithmetic reddens
`test_an_early_close_does_not_move_the_fixed_task_trigger_earlier` and only
that test. Codex's fix — a configurable fixed local clock defaulting to the
measured 16:30 Pacific — is right, and it is now independently corroborated by
the real data: the three most recent captures landed at 23:30:07Z, 23:30:08Z
and 23:30:10Z, i.e. 16:30 Pacific to the second, on days with both normal
closes and different epochs.

**CODSTALL-002 (P2) — confirmed as an improvement, with one operational
consequence to note.** My `ok` property treated `NO_ACTIVE_EPOCH` as success,
which is fail-open for a tool whose entire premise is "an epoch is supposed to
be accumulating". Exit 1 is the right default. The consequence, which belongs
in the owner's hands rather than in code: if this is ever wired to a
scheduler, a *deliberate* gap between epochs — which happened during the
2026-08-10 epoch swap — will produce a daily failure until the next epoch
opens. That is the correct fail-closed direction, but it should be expected
rather than discovered.

**CODSTALL-003 (P3) — confirmed.** `stall_threshold=0` made `tail >= threshold`
true for an interior gap and produced the impossible sentence "recorded
nothing for the last 0 expected session(s)". Negative grace and a naive
wall clock were also accepted at a public boundary.

**CODSTALL-004 (P3) — confirmed.** My read-only proof was an AST/source test.
Source text is not behavior; Codex's replacement opens a real SQLite file
through the Windows URI, proves a write raises, proves the bytes are unchanged
after a full read, and proves no WAL/SHM side files appear.

**CODSTALL-005 (P3) — confirmed, and my prose was simply wrong.** I wrote that
a refused capture lets the task "report success" and that "nothing crashes".
Traced end to end: `command_paper_observation` raises `RuntimeError` on a
reconciliation mismatch, upserts a `critical` `scheduled-paper-observation-failure`
alert, and re-raises, so the process exits nonzero. My sentence would have
sent an operator hunting for a silent-success mode that does not exist. The
detector's real justification is narrower and still sound: it answers the
multi-session cadence question the per-run alert cannot.

**CODSTALL-006 (P3) — confirmed.** My feature commit did not update the
required current records.

**CODSTALL-007 (P3) — confirmed, and reachable that same evening.** During the
grace window an observation can already exist while nothing is overdue. My
`NOT_DUE_YET` detail hard-coded "Zero observations is the correct state" — a
sentence that contradicted the report's own `recorded_sessions` field. This
was not theoretical: at 23:49Z on 2026-08-14 epoch-005 had exactly one
observation and no session overdue, which is the state that produces it.

## Prioritized issue ledger — this counter-review

| ID | Priority | Status | Location | Evidence and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| STALLCR-001 | P2 | Closed | `tests/test_epoch_cadence.py` | `test_capture_clock_and_timezone_are_explicitly_configurable` asserted only that a session was ABSENT from the expected list — which was equally true under the default trigger. The whole suite passed with `capture_timezone` ignored, and again with `capture_local_time` ignored. The two CLI flags CODSTALL-001 added exist so a remeasured trigger can be supplied without a code edit; nothing verified that either one reached the calculation. | Replaced with two discriminating tests (a session must be overdue under one trigger and not under the other, asserted in both directions), one reader-level test, and one argparse-level test that captures the keywords `main` actually passes. | Both parameters mutation-verified: ignoring `capture_timezone` reddens 2 tests, ignoring `capture_local_time` reddens 2, dropping the flag in argparse reddens 1. Before the fix, all three mutations left the suite green. |
| STALLCR-002 | P3 | Closed | `scripts/check_epoch_cadence.py` | `--capture-timezone` caught only `ZoneInfoNotFoundError`, which is a `KeyError` subclass raised for an unknown key. An empty or non-normalized key (`""`, `/America/New_York`, `../etc/passwd`) raises `ValueError`, which propagated as a raw traceback instead of a usage error. Reproduced against the real CLI. | Catch `(ZoneInfoNotFoundError, ValueError)`, with a comment recording why neither subsumes the other. | Parametrized regression over all three inputs; reverting the handler reddens all three. |
| STALLCR-003 | P3 | Closed | `assistant/epoch_cadence.py`, `HOW_TO_USE.md` | The detector models session `D` as captured on `D` at the trigger clock; the enforcing side, `paper_session_schedule()`, files an observation under the EASTERN date of the capture instant. `CLAUDE.md` §5 requires a readiness report to use the enforcing function's boundary conditions. The two agree for the installed 16:30 Pacific trigger (19:30 ET, same day) but that is a property of the trigger, not of the code, and the new flags let an operator supply one where it fails. | Documented the constraint at the function and in the operator guide; replaced the guide's example with a US-market one; pinned the agreement with a test that runs every session in a two-month window, including the early-close day, through the real `paper_session_schedule()`. | Moving the default trigger past the Eastern date boundary (22:30 Pacific) reddens the new test. |
| STALLCR-004 | P3 | Closed | `docs/Archive/Plans/ACTION_PLAN_2026-08-02.md`, `tests/test_active_document_consistency.py` | The STALL-1 row said "not merged or deployed" and the topology paragraph said "This review branch has not been published"; PR #221 merged both statements, making them false on arrival — the exact structural failure CODSTALL-006 had just been raised about, recurring one commit later. `test_no_document_calls_a_merged_commit_unreachable` exists to catch this and did not, for two independent reasons: its claim pattern matched `unmerged` as one word but not `not merged` as two, and it requires the claim and the hash to share a clause, whereas the ledger row puts the status in one sentence and the hashes in the next. It also measured reachability from `HEAD`, which makes every commit on your own branch look merged. | Corrected the records to `1babbcf`/PR #221; widened the claim pattern to the multi-word forms; added a row-scoped guard using the claim sentence plus the one following it; changed the reachability base from `HEAD` to the mainline ref. | The row-scoped guard was confirmed red on the stale text (flagging `6aa7069` and `4273de6`, and correctly NOT the deployed `752d3b7` named later in the same row) and green after the records were corrected. The parser is pinned directly by fixture so a document fix alone cannot mask the next phrasing. |

Issue total: **0 P0 / 0 P1 / 1 P2 / 3 P3; all closed; 0 open.**

## Codex's work verified sound and retained

* The fixed wall-clock model, and its empirical agreement with three real
  capture instants at 23:30:0xZ.
* Deleting `session_market_closes()` from `assistant/paper_evidence.py`: it
  had exactly one caller, which CODSTALL-001 removed. No dangling reference
  remains and `_NYSE` is still used by the two surviving helpers.
* Input validation on `stall_threshold`, `grace`, `capture_local_time`, and
  `capture_timezone`, including the `bool`-is-an-`int` case.
* The behavioral read-only proof, which is strictly stronger than the AST test
  it replaced. Codex correctly narrowed the surviving AST test's comment: it
  pins the direct composition boundary only, since the shared calendar helper
  transitively loads `paper_evidence`/`storage`. Importing those modules
  builds no store and runs no migration.
* The data-aware `NOT_DUE_YET` message.
* The `NO_ACTIVE_EPOCH` exit-status inversion, with the operational note above.
* Inverting `assert report.ok` to `assert not report.ok` is a legitimate
  contract change, not a test weakened to pass: it is accompanied by an
  explanation, a new CLI-level regression, and a strictly stricter contract.

## Live read-only observation

The CLI was run twice against the operator database through `mode=ro`. It
reports `HEALTHY: paper-epoch-005 has all 1 expected observation(s) through
2026-08-14`. Epoch-005's first observation was captured at 23:30:07Z on
2026-08-14, taking the count from 0 to 1 — the first positive evidence that
the epoch is accumulating under the owner's 60-day hold, and confirmation that
the earlier `NOT_DUE_YET` reading was correct rather than masking a fault.

This is a point-in-time read. It is not deployment proof and says nothing
about the next scheduled capture.

## Validation

Environment: Python 3.13.14, Windows, repository checkout.

* `tests/test_epoch_cadence.py`: **31 passed** (was 24).
* `tests/test_active_document_consistency.py`: **28 passed** (was 26).
* Mutation verification: 5 mutations against the corrected detector, 5
  detected by exactly the intended tests; 3 further mutations proving the two
  parameters and the argparse wiring are now covered where they previously
  were not.
* Full suite and `compileall` results are recorded in
  `docs/SESSION_HANDOFF.md` for the exact final tree.

## Untested and out of scope

* No test exercises the real Windows scheduled task, the real Alpaca paper
  account, or a real reconciliation refusal. The stall path is reproduced from
  recorded epoch-002 history, not re-run.
* The detector has not been scheduled, and this counter-review does not
  authorize scheduling it, deploying it, rolling an epoch, mutating the
  operator database, accessing a funded account, or live trading.
* Whether the owner's "60 days" means 60 calendar days (≈43 weekday sessions)
  or 60 captured sessions remains an open owner clarification.
* The SET-1 design question remains open: whether strict whole-share mode
  should permit a fractional sell only when it closes an entire position.
