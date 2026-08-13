# Session handoff — independent review merged and counter-reviewed

Prepared: 2026-08-12, after Claude's counter-review of the independent
full-project review (PR #196), performed on merged `main`.

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
- Exact final tree: **3,491 passed, 0 failed, 0 skipped, 25 known dependency
  warnings** under the repository venv, Python 3.13.14 / Streamlit 1.60.0.
- Environment note (operational, this machine): the PATH `python` is the
  WindowsApps interpreter with Streamlit 1.52.2, which fails the known
  frontend-hook assertion in `tests/test_ui_theme.py`. Prescribed validation
  must use `.venv\Scripts\python.exe`. This session's mutation checks ran
  under the PATH interpreter (also Python 3.13.14; the checks are
  content-level and Streamlit-independent); both full-suite measurements
  above used the repository venv.
- Repository-prescribed `compileall` (venv) and `git diff --check`: clean
  (only the expected LF→CRLF working-copy notice).

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

The counter-review closes the independent-review round. The action plan's
sequencing decides what happens next; nothing is left mid-flight. Open owner
decisions, unchanged: epoch-roll timing for the merged-but-undeployed work
(before the ~2026-09-10 AEP dividend window if the owner wants CR-W3 slack),
the physical-media-only off-machine backup, and the GR-7d target portfolio.

## 6. Resume prompt

```text
Verify a clean worktree on main and confirm origin/main == main. Read
CLAUDE.md, docs/ACTION_PLAN_2026-08-02.md, docs/OPERATIONAL_FACTS.md,
docs/SESSION_HANDOFF.md, and the counter-review section of
docs/REVIEW_2026-08-12_INDEPENDENT_FULL_PROJECT.md. Do not deploy, touch the
operator database, or roll paper-epoch-004 without a new owner instruction.
```
