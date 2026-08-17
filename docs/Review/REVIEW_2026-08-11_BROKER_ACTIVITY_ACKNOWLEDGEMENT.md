# Independent review — broker activity acknowledgement

Prepared: 2026-08-11
Reviewer: Codex
Outcome: **accepted after correction**
Implementation quality: **6/10**

## 1. Scope and repository topology

The reviewed implementation range is `3b396f8..24de4f5`. Claude's branch
`user/claude/broker-activity-acknowledgement-20260811` is published at
`b3c61cb`; PR #188 merged it to `main` / `origin/main` at `24de4f5`. Review
corrections are in local-only branch
`codex/review-broker-activity-acknowledgement-20260811`, commit `74376e4`.
Nothing in this review was pushed, merged, deployed, or applied to the
operator database or scheduler.

The feature's architecture is useful: an immutable table stores one explicit
operator decision against a SHA-256 fingerprint of a live broker row, the
bootstrap cutoff remains authoritative, and the ordinary activity sync is the
only posting path. The submitted tests covered the happy path, fingerprint
change, cutoff ordering, amount provenance, migration, and basic conflicts.
The score is nevertheless 6/10 because the submitted CLI contradicted its own
read-only/record-only contract and several broker facts could be overridden in
ways that produced incorrect durable accounting. Those are material review
misses in a money ledger even though the core design was sound.

## 2. Commit-by-commit disposition

| Commit | Disposition | Review result |
|---|---|---|
| `fb66d5f` | **Accepted after correction** | Introduced the schema, service, CLI, sync integration, tests, and initial documentation. The core fingerprint/cutoff/idempotency design is retained, but BAA-001 through BAA-008 required correction. |
| `b3c61cb` | **Accepted** | Correctly removed the accidentally tracked shell-redirection artifact and repaired handoff heading order. The physical untracked `ernkgjserng` file remains owner material and was left untouched. No product defect found. |
| `24de4f5` | **Accepted after correction** | PR #188 merge. `git diff b3c61cb..24de4f5` showed no merge-only tree change; its resulting tree inherits the implementation findings and is corrected by `74376e4`. |

## 3. Prioritized issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| BAA-001 | P2 | Resolved | `fb66d5f` | `assistant/portfolio_ledger.py` acknowledgement validation/application | An acknowledgement could override immutable broker facts: a pending row could post, EUR could be journaled as USD, and a missing amount could be declared `no_cash_effect`. This permits incorrect durable cash state. | Three reviewer regressions failed red on `24de4f5`: pending and EUR acknowledgements did not raise; missing `net_amount` was accepted as zero. | Human judgement may classify an event but cannot change settlement, currency, or whether the broker supplied a cash amount. | `_validate_acknowledged_activity()` now applies both when recording and applying: status must be absent or executed, journal treatments require USD when currency is supplied and a non-zero signed amount, and `no_cash_effect` requires an explicit zero. | The same three regressions pass green; full ledger suite passes. |
| BAA-002 | P2 | Resolved | `fb66d5f` | `assistant/portfolio_ledger.py` external-ID identity | The same broker activity ID could first be journaled as a fee and later be acknowledged as a transfer, allowing two accounting meanings and two journal entries for one broker event. | Reviewer regression failed red after a `fee:<id>` row was followed by a cash-transfer acknowledgement using the same ID. | Broker event identity is immutable; cross-type reuse breaks idempotency and can double-count cash. | Acknowledgement creation and application both check every journal external-ID namespace; `no_cash_effect` is checked too. Impossible decisions are not stored. | Cross-type regression passes and asserts no acknowledgement row was inserted. |
| BAA-003 | P2 | Resolved | `fb66d5f` | `scripts/run_personal_assistant.py` review command; `assistant/storage.py`; `assistant/portfolio_ledger.py` preview | `ledger-activity-review` called the real sync. It wrote recognized fees while advertising itself as read-only, returned an empty `refused` list, and hid exact refusals in one aggregate note. Opening the store through normal CLI dispatch could also run migrations. | Reviewer regression failed red: journal postings changed after review and the requested refused row was not returned structurally. | A diagnostic command must not alter the operator ledger, and its definition of done is to identify exact rows and reasons. | Added verified `snapshot_to()` using SQLite's read-only backup source, runs the exact sync against a temporary shadow database, returns structured refusals, preserves `last_database_backup`, and marks the parser command `read_only_store=True`. Existing `backup_to()` retains its state-recording behavior. | Read-only CLI regression passes, including unchanged postings and backup state; parser regression proves read-only open; backup/operations suites pass. |
| BAA-004 | P2 | Resolved | `fb66d5f` | `scripts/run_personal_assistant.py` account binding | Standalone review/acknowledge fetched Alpaca activities without proving that the connected account matched the ledger. A different account, or a manually bootstrapped ledger, could therefore be inspected or contaminated. | Reviewer regression failed red because a mismatched account still reached the activity fetch. Source review also showed manual/non-Alpaca bootstrap was accepted by the helper. | Every broker-derived ledger mutation must be bound to the exact account whose opening snapshot created the journal. | Both commands require an Alpaca bootstrap with a bound account ID, fetch only the broker account identity, compare it through the shared binding helper, and refuse before any activity fetch on mismatch or wrong ledger source. | Account-mismatch regression and two non-Alpaca-bootstrap cases pass; activity endpoint remains uncalled. |
| BAA-005 | P2 | Resolved | `fb66d5f` | `scripts/run_personal_assistant.py` acknowledgement workflow | The CLI allowed acknowledgements for rows the sync already handled and immediately ran the full sync after recording, posting the target and potentially unrelated activities. This contradicted “one refused row” and “record decision; next sync applies.” | Two reviewer regressions failed red: an ordinary FEE was accepted, and acknowledging an unsupported row immediately created journal postings. | An acknowledgement is exceptional human evidence, not an alternative route for reclassifying supported rows or an implicit batch-post command. | The command previews the exact target on a disposable snapshot and permits a new decision only when that row is currently refused. It records the decision only; the next ordinary sync applies it. | Both CLI regressions pass and assert no journal posting at acknowledgement time. |
| BAA-006 | P2 | Resolved | `fb66d5f` | `assistant/storage.py` acknowledgement persistence | Idempotency ignored operator and rationale, so a second human or changed reason silently returned “duplicate” while preserving a materially different audit claim. The original select-then-insert sequence also left a uniqueness race. | Reviewer regression failed red when a second operator/rationale was silently accepted as idempotent; source inspection confirmed the non-atomic write sequence. | Operator identity and rationale are part of the durable judgement. Conflicting audit evidence must be loud and insertion must be atomic. | Storage now uses `INSERT ... ON CONFLICT DO NOTHING`, then compares fingerprint, treatment, operator, rationale, and details. Only the exact substantive decision is idempotent; a new retry timestamp alone is not part of identity. | Operator/rationale conflict regression passes; existing exact-retry test remains green. |
| BAA-007 | P3 | Resolved | `fb66d5f` | `assistant/portfolio_ledger.py` acknowledgement time | A caller could store a timezone-naive audit timestamp. | Reviewer regression failed red with `datetime(2026, 8, 11, 12, 0)`. | Durable cross-machine audit times must be unambiguous. | Acknowledgement time now uses the ledger's timezone-aware parser before persistence. | Naive-time regression passes green. |
| BAA-008 | P3 | Resolved | `fb66d5f` | `assistant/portfolio_ledger.py` sync report | A successfully reviewed `no_cash_effect` row was excluded from `activities_seen`, so a one-row successful sync reported zero activities. | Source calculation summed only posting/duplicate/skip counters; a no-post acknowledgement increments none. | Operational counts should describe inputs examined, not only rows that create journal entries. | Successful reports set `activities_seen` to the input-row count. | Existing no-cash-effect test now asserts `activities_seen == 1`; full ledger suite passes. |

Final issue state: **0 P0, 0 P1, 0 P2, and 0 P3 open**.

## 4. Final accepted behavior

`ledger-activity-review` is now a genuinely read-only, account-bound preview.
It fetches post-bootstrap activities, snapshots the current SQLite database
without modifying its backup metadata, runs the real sync against that
temporary copy, and prints exact refused rows plus recorded decisions.
`ledger-activity-acknowledge` accepts one live row only when the sync currently
refuses it, records the operator, rationale, exact row fingerprint and one of
the four frozen treatments, and does not journal at command time. The next
ordinary paper-observation/activity sync applies the decision.

The operator can choose accounting treatment but cannot override a pending
status, non-USD currency for a journaled amount, a missing/zero amount for a
journal treatment, sign rules, the explicit-zero requirement for
`no_cash_effect`, the bootstrap cutoff, account binding, broker-row content,
or an existing journal identity. Changed rows and conflicting second decisions
fail closed. The new table remains an additive, idempotent migration.

## 5. Validation

Environment: Windows, Python **3.13.14**, installed Streamlit **1.52.2**.

- Submitted baseline: the implementation's ledger/CLI/schema/import focused
  set passed (**122 passed**), confirming the original tests before correction.
- Red phase: **10 reviewer regression cases failed for the intended reasons**
  on uncorrected merge `24de4f5`.
- Corrected ledger + CLI suites: **112 passed** in 28.53s.
- Schema/import/backup/operations/readiness suites: **56 passed** in 20.09s.
- Complete inventory: **3,405 tests collected**. Deterministic final batches
  passed **3,404**, with one explicit deselection:
  - A-F: 1,035 passed, one existing websockets deprecation warning;
  - G-M: 1,025 passed, 24 existing joblib/NumPy warnings;
  - N-S: 1,055 passed;
  - T-Z plus nested fault matrix: 289 passed, 1 deselected.
- The deselected test is
  `test_every_theme_test_id_is_emitted_by_the_installed_streamlit`. The
  unchanged theme files target the project's documented Streamlit 1.60
  frontend, while this computer has 1.52.2 and therefore lacks
  `stRadioOption`. The other 15 theme tests pass. This is an environment
  mismatch, not a broker-acknowledgement failure, and is not counted green.
- Repository `compileall`: clean.
- `git diff --check`: clean apart from Windows line-ending notices.
- Changed-file credential-shape scan: zero matches.

No validation called the broker, wrote the operator database, changed an
epoch, acknowledged an alert, or mutated scheduled tasks.

## 6. Boundaries and remaining operation

This review changes accounting ingestion and its operator CLI only. It adds no
proposal, approval, order submission, policy, strategy, scheduler, ML/LLM
authority, or live-trading capability. It is merged in `main` only in its
uncorrected PR #188 form; correction `74376e4` and this review record are
local-only until the owner authorizes a push and merge.

The active `paper-epoch-003` remains frozen on deployed `ef05dc1`; this review
did not remeasure or mutate it. Neither PR #188 nor the correction may be
patched into that epoch. Deployment belongs in one separately authorized,
complete epoch-004 transition following `docs/operations/OPERATIONS_RUNBOOK.md`.

---

## Counter-review (Claude, 2026-08-11) — accepted in full; one missed write path closed

Counter-review of `74376e4`, `f7742bd`, and `373f51f`. All three commits:
**accepted**. All eight findings are **confirmed** — every one of them
red-baselined. One gap in the correction was found and fixed here.

### Red baseline

The merged tree (`24de4f5`) was restored in place and the review's
regressions run against it: **14 failed, 98 passed**, then the real tree was
restored and re-verified green. Every BAA finding is a genuine, reproducible
defect in my implementation. The 6/10 is fair.

The one I want on the record as the worst: **BAA-003 — my
`ledger-activity-review` was not read-only.** I named it "review",
documented it "Read-only: what the activity sync would refuse, and why", and
then had it call the real sync, which writes journal entries. It is the same
class of defect this project already closed once in GR-7b ("CLI/UI
provider-fetch writes on a claimed read-only surface"), and I reintroduced
it while writing the safety-critical command. Codex's replacement — run the
exact sync against a verified temporary snapshot via a new `snapshot_to()`
that does not touch `last_database_backup` — is the right shape, because it
keeps validation, conflict detection, and acknowledgement handling identical
to a real sync instead of reimplementing a "what would happen" predicate
that could drift.

The other seven are equally real: an acknowledgement could override
settlement status and currency (BAA-001), reuse a broker id already
journaled under another type (BAA-002), skip the account-binding check
(BAA-004), reclassify an already-supported row and immediately batch-post
(BAA-005), silently accept a different operator's conflicting rationale over
a non-atomic select-then-insert (BAA-006), store a naive timestamp
(BAA-007), and under-count `activities_seen` (BAA-008).

### Verified and NOT findings

- `preview_broker_activities` was exercised against a real store on this
  Windows host: the temporary snapshot is created, used, and cleaned up with
  no lingering SQLite handle, live postings are unchanged, and
  `last_database_backup` stays `None`. The Windows temp-cleanup hazard I
  suspected does not occur, because `AssistantStore` opens connections per
  operation rather than holding one.
- The bare `assert amount is not None and amount != 0` in
  `_apply_acknowledged_treatment` is stripped under `python -O`, but it
  guards an invariant `_validate_acknowledged_activity` has already enforced,
  and bare asserts for unreachable postconditions are existing repository
  convention (`platform_readiness.py`, `stock_lookup.py`). Consistent, not a
  defect.

### BAACR-001 (P2, fixed here) — the binding guard covered the commands, not the write path

BAA-004 added `_require_activity_account_binding` to the two **new**
standalone commands. But the function that actually turns broker activities
into journal entries — `_sync_broker_activities_from_alpaca` — had no guard,
and it has three other callers:

| Caller | activity sync | binding first checked |
|---|---|---|
| `ledger-reconcile` | line 1464 | `reconcile_snapshot`, line 1466 |
| `paper-observation` | line 1948 | `reconcile_snapshot`, line 1950 |
| `operations-cycle` | line 2046 | `reconcile_snapshot`, line 2058 |

In every one, activities are **journaled before** the account binding is
checked. With credentials pointing at a different Alpaca account, another
account's fees, dividends, and transfers land in this append-only journal;
`reconcile_snapshot` then correctly refuses, but the immutable rows are
already written. This is not hypothetical plumbing: the launcher re-reads
credentials from the user registry at every launch, the owner rotated keys
on 2026-08-05, and this is a deliberate two-machine setup. It is also the
*higher*-traffic path — those two scheduled callers run unattended every ten
minutes and nightly, while the guarded commands are typed by hand.

**Correction:** the guard now runs inside
`_sync_broker_activities_from_alpaca`, the single choke point, before the
fetch — so every present and future caller is covered rather than the three
that exist today. Two regressions added: a behavioural one asserting the
activity endpoint is never even called once binding fails and that nothing
is journaled, and a source-level one asserting the guard sits inside that
helper and precedes the fetch.

One existing test (`test_sync_broker_activities_from_alpaca_windows_the_fetch`,
mine, from the AP-6 round) needed updating: it pins the fetch window and now
has to satisfy the new precondition, so it stubs the guard and defers guard
coverage to the new tests. The invariant it pins is unchanged.

### Mutation evidence (all restored and re-verified green)

| Mutation | Result |
|---|---|
| Remove the guard from the choke point | both BAACR-001 regressions red |
| Replace the snapshot preview with the real sync | BAA-003 read-only regression red |
| Disable the acknowledged status guard | BAA-001 settlement regression red |
| Drop operator/rationale from the idempotency comparison | BAA-006 regression red |

### Counter-review validation

Import-boundary, operations, and schema-verification suites green (33
passed); ledger and CLI suites 114 passed; `compileall` and
`git diff --check` clean. Full-suite count is recorded in the session
handoff. No broker call, no operator-database mutation, and no scheduler,
epoch, or deployment action. Nothing deployed; epoch-003 continues on
`ef05dc1`.
