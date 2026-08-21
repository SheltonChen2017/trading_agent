# Independent review: Stage 1 launch-driver delta

Status: **accepted**. Prepared: 2026-08-18. Reviewer: Cursor Grok 4.6.
Scaled to a two-commit plumbing delta. No QuantConnect run was launched.
No frozen analyser was executed.

## 1. Snapshot

| Item | Value |
|---|---|
| Requested range | `08f23a1..f821fb1` (2 commits) |
| Base | `08f23a1a3bf3db5decc3cffec45e318a87808b1b` |
| Review head | `f821fb14926c91a8ac683fe98acf02d97efa65ac` (`origin/user/claude/stage1-launch-driver-20260818`) |
| `origin/main` at review start | `875d0036a9eda25be325d9f9103c1da0c9b9fc18` (PR #256 merge of the review head) |
| Merge tree | `875d003^{tree}` == `f821fb1^{tree}` == `e748f3e608ac42f532841bca37335895fdfe451f` |
| Review branch | `user/cursor/review-stage1-launch-driver-20260818` from `origin/main` |
| Worktree | clean at review start |

Fetched before review. Both commits in
`git log --reverse --oneline 08f23a1..f821fb1` are dispositioned below.
The PR #256 merge is not in the named range; it is a clean fast-merge of
`f821fb1` and adds no product delta.

## 2. Verdict

**Accept both commits.** `595170c` adds two `FAMILIES` entries and the
tests that pin them. Driver behavior outside that table and the module
docstring is unchanged: `require_clean=True`, the log-fetch `query=""`
parameter, paging, evidence immutability, and serial wait are untouched.

**This review accepts the plumbing, not a launch.** The owner GO is
already on record (`f821fb1` / handoff 7af). Six serial cloud runs remain
an owner-executed next step after this review, one at a time, each
parser-round-tripped before the next. This document does not start them.

No P0. No P1. No P2. No open P3.

## 3. Per-commit dispositions

| Commit | Disposition | Verification |
|---|---|---|
| `595170c` Teach the launch driver the Stage 1 families | **Accepted.** No issue found. | Diff is docstring + two `FAMILIES` entries in `scripts/run_qc_stage0.py` and two tests in `tests/test_qc_stage0_runner.py` (8 + 36 lines). `git diff 08f23a1 595170c -- scripts/run_qc_stage0.py` is that eight-line change only. `require_clean=True` remains at `_git_commit_of`. `_fetch_full_log` still sends `query: ""`. `--family` choices are `sorted(FAMILIES)`, so the new keys become launchable by construction. Family paths are the reviewed Stage 1 files: `research/lean/alpha_stage1_replications.py` and `research/lean/alpha_stage1_benchmark.py`. Each file has exactly one `ACTIVE_UNIVERSE = "B_core"` assignment matching the retarget regex. Two reverse mutations red then restored (section 4). 15/15 runner tests green. |
| `f821fb1` Record owner GO for Stage 1 and the launch-driver round | **Accepted.** No issue found. | Docs only (`ACTION_PLAN`, `SESSION_HANDOFF` 7af). Records the owner GO, the null-ends-the-program protocol, the two-entry driver claim, and the sequence review → six serial runs → one analyser pass. No statistic, no live-authority claim, no skipped review. |

## 4. Required reverse mutations

Both mutations executed this session; production restored via
`git checkout --` after each red run.

| Mutation | Command | Result |
|---|---|---|
| (a) Remove the two Stage 1 `FAMILIES` entries (and their comment) | `pytest tests/test_qc_stage0_runner.py::test_stage1_families_map_to_the_frozen_replication_sources` and `::test_every_family_file_retargets_each_universe_by_one_line` | **RED** on the mapping test: `KeyError: 'stage1'`. Retarget test **still passed** (it only iterates remaining families). Restored; mapping test green. |
| (b) Duplicate `ACTIVE_UNIVERSE = "B_core"` in `research/lean/alpha_stage1_benchmark.py` | same two tests | **RED** on the retarget test: `SystemExit: expected exactly one ACTIVE_UNIVERSE constant, found 2`. Traceback shows `_retarget_universe` running on the real benchmark source. Mapping test still passed. Restored; 15/15 green. |

Mutation (a) proves the mapping test is not vacuous. Mutation (b) proves
the retarget test reads the real family files, not a fixture string.
Together they are why both tests are required: dropping the entries
does not redden the retarget loop.

## 5. Launch-plumbing class check

Historical defects named in the request:

- Dropped `require_clean=True` (QCS0CR-002). Still present at
  `scripts/run_qc_stage0.py:77`. Still pinned by
  `test_launch_commit_check_requires_a_clean_tree` (spy asserts the
  kwarg is `True`; a refusing `RuntimeIdentityError` becomes
  `SystemExit`). The delta does not touch `_git_commit_of`.
- Log-fetch missing `query` parameter. Still present at
  `_fetch_full_log` (`"query": ""`). Still pinned by `_PagedClient`
  (`assert payload["query"] == ""`). Completion is still persisted
  before log fetch. The delta does not touch wait/log paths.

No new sibling of either class in this range. `--family` growing with
`FAMILIES` is the intended launch enablement, not a silent behavior
change in compile/upload/wait.

`universe_smoke.py` also declares `ACTIVE_UNIVERSE` and is correctly
**not** in `FAMILIES`.

## 6. Issue ledger

No findings. Empty ledger retained so the review does not skip the
required table:

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | No P0–P3 finding in this range. | Tests, mutations, and `git show 595170c` / `f821fb1`. | — | — | 15 passed; mutations (a)/(b) red then restored. |

## 7. Validation

On `user/cursor/review-stage1-launch-driver-20260818` (tree identical to
`f821fb1` / `875d003` plus this report commit):

```text
python -m pytest -q tests/test_qc_stage0_runner.py
    -> 15 passed in 0.20s (post-restore; 0.62s on the first green run)
python -m compileall -q scripts/run_qc_stage0.py tests/test_qc_stage0_runner.py
    -> clean
git diff --check
    -> clean
```

Full suite was not re-run (out of proportion to an 8-line driver table
change). Not tested: QuantConnect cloud execution. This review does not
launch it.

## 8. What this review does and does not authorize

- The launch-driver delta **passes independent review**.
- **No QuantConnect run is authorized by the act of writing this file.**
  The owner GO is already recorded; the remaining operational sequence
  is still six serial cloud runs then one frozen Stage 1 analyser pass,
  with parser round-trip before the next launch.
- No deployment, epoch roll, operator-database mutation, paper orders,
  or live trading.
- No `FEATURE_MILESTONE_RECORD.md` entry: research plumbing, not a
  completed platform milestone.
