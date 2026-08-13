# Session handoff — independent review counter-reviewed; AP-11 clock race fixed

Prepared: 2026-08-13, after Claude's counter-review of the independent
full-project review (PR #196) and a follow-on production-defect fix (AP-11)
found by investigating a live negative-age freshness alert.

Audience: repository owner, Claude Code, Codex, and the next verifier.

## 0. Read this first

Read, in order:

1. `CLAUDE.md`
2. `docs/ACTION_PLAN_2026-08-02.md`
3. `docs/OPERATIONAL_FACTS.md`
4. `docs/REVIEW_2026-08-12_INDEPENDENT_FULL_PROJECT.md` (including its
   counter-review section)
5. `docs/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`
6. `docs/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`

The action plan remains the sequencing authority. Nothing in this session
authorizes M3, deployment, an epoch roll, live trading, or any funded action.

## 1. Repository topology

- `main` / `origin/main` before this session: `1a46881` — the PR #196 merge
  of `codex/independent-full-review-20260812` (`67558f5` production
  correction, `78a69b3` review record, `428bb56` handoff). The owner pushed
  and merged that branch after its handoff was written; the merge tree equals
  branch tip `428bb56` exactly.
- This session's counter-review branch:
  `user/claude/counter-review-ipr-20260812`, created from `1a46881`.
  Its commits carry the IPRCR-001 correction (stale post-merge handoff
  topology), the IPRCR-002 correction (`pytest.ini` collection exclusion for
  machine-local `artifacts/`), the AP-10 merge disposition, the counter-review
  section of the independent-review report, two new guard tests, and this
  handoff.
- Both session branches are MERGED to `main` by the owner (2026-08-13):
  the counter-review branch (`594decf`) via PR #197 at `3aaccf0`, then the
  stacked AP-11 fix branch (`0100f04`) via PR #198 at `72b6278`. The final
  merge tree equals the AP-11 branch tip exactly (no merge-only delta).
  This handoff revision itself rides a small post-merge documentation
  branch (`user/claude/post-merge-handoff-20260813`).
- Before staging or committing anything else, re-check `HEAD` and
  `git status`.

## 2. What the counter-review concluded

Full dispositions are in the counter-review section of
`docs/REVIEW_2026-08-12_INDEPENDENT_FULL_PROJECT.md`.

- **All four IPR findings confirmed and correctly fixed.** IPR-001 was
  reproduced from pre-fix source and its 7-case mutation independently
  re-run; IPR-004 was verified against the installer source (both task
  installers schedule `Convert-EasternClockToLocal -Hour 16 -Minute 30`);
  all four new documentation guards were mutation-verified sensitive.
- **IPRCR-001 (P3), resolved here:** after the owner merged PR #196, the
  handoff on `main` still called the review branch local-only and directed
  the next operator to a pre-merge branch and range. The same recurrence
  class IPR-002 fixed. Corrected with a red-first known-stale-phrase guard;
  historical review reports keeping their as-written topology are
  deliberately untouched.
- **IPRCR-002 (P2), resolved here:** the review's leftover worktree at
  gitignored `artifacts/codex-independent-full-review` broke the prescribed
  `python -m pytest -q` on this checkout — 163 "import file mismatch"
  collection errors, zero tests run, `git status` clean throughout (pytest
  does not honor `.gitignore`). Fixed with a `pytest.ini` `norecursedirs`
  exclusion, proven to restore collection with the worktree still present
  (3,491 collected), then the clean, merged worktree was removed. A
  mutation-verified hygiene test pins the config.
- No further instance of the IPR-001 class (raw optional provider field into
  the format mini-language) was found in a repo-wide sweep.

## 2b. AP-11 — the live negative-age warning, root-caused and fixed

The owner asked why `reconciliation_freshness` warned
`age_seconds=-0.117315, errors=0` at 2026-08-13T05:40:49Z on the deployed
epoch-004 runtime, where AP-7 was recorded as fixed. Root cause, verified
against the deployed source at `b837374` (content-identical to `main` for
both files) and the alert's own timestamps:

- The AP-7/DCCR-CR-002 fixes capture a post-read clock only when `now` is
  None. `operational_health()` manufactured `now = now or datetime.now(...)`
  at entry and passed it DOWN as an explicit `now`, so
  `transaction_readiness()` froze to a clock captured before ~5 s of
  integrity/broker work. `monitor-orders` commits
  `last_order_reconciliation` every 30 s; tonight's write landed 0.117 s
  after the frozen clock and the `timedelta(0) <=` guard flagged a healthy
  reconciliation as future-dated. `build_platform_readiness()` shared the
  manufacture-then-pass shape.
- The AP-7 regression tests stayed green because they call each function
  directly with `now=None` — a call shape production never uses.
- Impact is bounded: warning noise plus nonzero operations-cycle exits.
  No observation, ledger, reconciliation, or money path is affected; the
  2026-08-12 observation captured cleanly with 0 mismatches.
- Fix: both sites forward the caller's original clock (`now=explicit_now`).
  Frozen as-of semantics for genuine caller-supplied clocks are preserved
  and pinned in both directions. Both fixes reddened their new tests under
  reverting mutation and passed restored.
- The running epoch keeps the warning noise until the next authorized roll;
  the open `reconciliation_freshness` alert row (fingerprint
  `17852815…a6be`, 9 occurrences since 2026-08-06) can be acknowledged as
  root-caused rather than investigated again.

## 3. Validation

Environment: repository virtual environment, Python 3.13.14, Streamlit 1.60.0.

- New guard `test_handoff_does_not_describe_the_merged_independent_review_branch_as_stale_topology`:
  **failed red** against the pre-correction handoff, passes after.
- IPR-001 mutation independently re-run: **7 failed** reverted, **7 passed**
  restored.
- Placeholder, epoch-host, and Eastern-clock documentation guards: each
  **reddened** under targeted regression and passed restored; clean tree
  confirmed after every restoration.
- Focused pre-change: `tests/test_active_document_consistency.py` +
  `tests/test_recommended_stocks.py` — **71 passed**.
- Penultimate tree (everything final except this validation line): **3,490
  passed, 1 failed, 25 known dependency warnings** in 641.07 s — the single
  failure was the extended placeholder guard correctly rejecting this line's
  own then-unfilled token.
- Exact counter-review branch tip (`594decf`): **3,491 passed, 0 failed,
  0 skipped, 25 known dependency warnings** under the repository venv,
  Python 3.13.14 / Streamlit 1.60.0.
- Environment note (operational, this machine): the PATH `python` is the
  WindowsApps interpreter with Streamlit 1.52.2, which fails the known
  frontend-hook assertion in `tests/test_ui_theme.py`. Prescribed validation
  must use `.venv\Scripts\python.exe`. This session's mutation checks ran
  under the PATH interpreter (also Python 3.13.14; the checks are
  content-level and Streamlit-independent); both full-suite measurements
  above used the repository venv.
- Repository-prescribed `compileall` (venv) and `git diff --check`: clean
  (only the expected LF→CRLF working-copy notice).

AP-11 branch validation (all under the repository venv):

- New production-call-path test: **failed red** before the fix (on the
  concurrent-write assertion), passes after.
- Both fix sites mutation-verified: reverting each `now=explicit_now` back
  to `now=now` reddened exactly its own regression test; both restored
  green.
- Focused: `tests/test_operations.py`, `tests/test_transaction_readiness.py`,
  `tests/test_readiness_budget.py`, `tests/test_platform_readiness.py` —
  **64 passed** before the new platform test, all green after.
- Exact AP-11 final tree: **3,493 passed, 0 failed, 0 skipped, 25 known
  dependency warnings** in 674.19 s.

## 4. Operational truth — do not disturb the epoch

- `paper-epoch-004` is the only active evidence epoch. Its frozen deployed
  runtime is `b837374` in `C:\git\trading_agent_operational`.
- CR-W2, AP-7, MADCR-001, and the broker-activity acknowledgement path are
  deployed there. AP-8, AP-9, QC-2, AP-10/IPR-001, and this counter-review
  are merged development code and are **not deployed**; they ride the next
  owner-authorized epoch roll.
- CR-W3 remains a genuine watch: the first real AEP dividend subtype may
  over-refuse safely around 2026-09-10. JNLC still needs explicit operator
  accounting judgement. Never widen reconciliation tolerance or use a manual
  compensating entry.

## 5. Next step

Both session branches are merged; nothing is mid-flight. The AP-11 fix has
NOT yet had an independent Codex review — it merged on Claude's own
validation — so a Codex review of the merged range `1a46881..72b6278` is
the expected next step of the standing loop. Open owner decisions,
unchanged: epoch-roll timing for the merged-but-undeployed work (before the
~2026-09-10 AEP dividend window if the owner wants CR-W3 slack; AP-11 joins
that queue), the physical-media-only off-machine backup, and the GR-7d
target portfolio.

## 6. Resume prompt

```text
Verify a clean worktree on main and confirm origin/main == main. Read
CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md, docs/OPERATIONAL_FACTS.md,
docs/SESSION_HANDOFF.md, and the counter-review section of
docs/REVIEW_2026-08-12_INDEPENDENT_FULL_PROJECT.md. Do not deploy, touch the
operator database, or roll paper-epoch-004 without a new owner instruction.
```
