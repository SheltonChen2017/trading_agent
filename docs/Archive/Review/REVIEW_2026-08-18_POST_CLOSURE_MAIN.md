# Independent review: post-closure `main` (`66e2723..f40c2c1`)

Status: **accepted**. Prepared: 2026-08-18. Reviewer: Cursor Grok 4.6.
No QuantConnect run. No frozen analyser. No operator-database open.
No product correction in this review (findings left open; none P0–P2).

## 1. Snapshot

| Item | Value |
|---|---|
| Requested range | latest commits on `main` after Stage 1 closure |
| Base | `66e27233cf05428f19d339af3cb25ae04855d576` (PR #258) |
| Review head | `f40c2c1e9bac9f91788605d0274008131a27a932` (`origin/main`) |
| Review branch | `user/cursor/review-post-closure-main-20260818` from `origin/main` |
| Isolated worktree | `C:\git\customizedAgent\trading_agent-review-main` at detached `f40c2c1` |
| Shared checkout at review start | already `main` at `f40c2c1` (clean vs `origin/main`) |

Fetched before review. Every commit in
`git log --reverse --oneline 66e2723..origin/main` is dispositioned
below. Temporary reverse mutations were applied only in the isolated
worktree and restored; both the shared checkout and that worktree ended
clean at `f40c2c1`.

## 2. Verdict

**Accept the range.** Hygiene closes S1R-001 and SHR-001. SHW-1 is
observation-only contracts plus three `overlay_*` tables; it does not
grant order, proposal, or promotion authority. The allocation-policy
documents do not reopen A-002 and do not add a QC family.

**Do not start SHW-2 until POST-001 is decided.** Storage currently
persists raw dicts, so a later runner can write an `available=True`
observation that the dataclass would refuse.

**Do not start APQ-1 until ACTION_PLAN schedules or explicitly defers
it.** Merging the plan to `main` does not complete APQ-0.

Opening this tree against the frozen `paper-epoch-005` database would
`CREATE TABLE IF NOT EXISTS` the overlay tables. Keep that host on
`752d3b7`.

No P0. No P1. No P2. Five P3 (POST-001..005).

## 3. Per-commit dispositions

| Commit | Disposition | Verification |
|---|---|---|
| `b37ff26` Close S1R-001 and SHR-001 | **Accepted.** | Stage 1 analyser gains the sibling `sys.path` bootstrap. `_optional_finite` and BROW turnover wrap `ValueError` as `InvalidLog`/`SystemExit`. Tests: subprocess `--help` with `cwd=scripts`; malformed `abc` turnover. Reverse mutation (a) red. Analysers not re-invoked. |
| `3875079` Post-closure round records | **Accepted.** | Docs only. Sequence 1-2-4-3; design first draft then superseded in `9ba7d06`; defensive-carry prereg remains DRAFT with `[TO FREEZE]` gates. |
| `74c095c` Merge stage1-runs into analyser-hygiene | **Accepted.** | Combined tree adds `REVIEW_2026-08-18_STAGE1_LAUNCH_DRIVER.md` and handoff text. No silent product merge. |
| `9ba7d06` SHW-1 contracts and storage | **Accepted** with POST-001..003. | Frozen dataclasses; overlap/authority/NaN/`≤ -100%` refusals; append-only hash identity; FK unregistered/cross-epoch refusal; outcomes refuse missing or refused observations; migration drop-tables-then-reopen keeps a `system_state` marker; non-overlay snapshot unchanged. No `ml` import; no `execution/` import of `overlay_shadow`. Reverse mutation (b) red. Storage bypass of incomplete levels confirmed (POST-001). |
| `98243a1` Record SHW-1 | **Accepted** as a record. | ACTION_PLAN POST-CLOSURE row and handoff §7ak. “Import-boundary suite green” refers to existing `ml` tests (POST-002). |
| `bb6898a` Allocation-policy plan and prereg | **Accepted** as docs. | Two files only. Frozen mixes P0–P3, window 2022-01-01 → last complete US session ≤ 2026-08-18, costs 0/5/10/25 bps, one look. APQ-0 DoD unmet (POST-004). |
| `f9f8799` Merge PR #259 | **Accepted.** | `git diff 98243a1 f9f8799` empty. Tree equals SHW-1 head. |
| `f40c2c1` Merge PR #260 | **Accepted.** | Combined tree is SHW-1/hygiene plus the two allocation docs. No conflict-resolution product edits. |

## 4. Required reverse mutations

Executed in `trading_agent-review-main`; production restored before the
review closed.

| Mutation | Result |
|---|---|
| (a) Comment out `sys.path.insert` in `scripts/analyse_qc_alpha_stage1.py` | `test_stage1_analyser_is_invocable_in_script_mode` **RED**: `ModuleNotFoundError: No module named 'scripts'`, returncode 1. Restored. |
| (b) Conflict upsert returns the existing row instead of `OverlayShadowConflictError` | `test_conflicting_content_for_a_reused_identity_is_refused` **RED**: `DID NOT RAISE OverlayShadowConflictError`. Restored. |

Focused tests after restore: **22 passed**
(`tests/test_overlay_shadow.py`, the two hygiene tests, `tests/test_ml_import_boundary.py`).

POST-001 is not a reverse mutation of an existing test: the contract
test refuses incomplete levels; storage still accepts the raw dict.
That is the finding.

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| POST-001 | P3 | Open | `9ba7d06` | `assistant/storage.py` `record_overlay_observation` | Storage persists raw dicts. Contract invariants are not re-applied. | `OverlayObservation` refused incomplete `index_levels`; `record_overlay_observation` stored `available=1` (hash prefix `60f13a59d319`). | SHW-2 could persist partial imputation, the failure the dataclass exists to make unrepresentable. | Construct/validate `OverlayObservation` (and siblings) before upsert; refuse extra/action-shaped fields. | New test: raw incomplete-available dict raises; `to_payload()` round-trip still works. |
| POST-002 | P3 | Open | `9ba7d06` / `98243a1` | `docs/Archive/Plans/SHADOW_OBSERVATION_DESIGN.md` §2; handoff §7ak | Design claims import-boundary tests “extend to prove both directions” and that `overlay_shadow.py` holds “pure computation.” | `tests/test_ml_import_boundary.py` still only walks `ml` imports. `overlay_shadow.py` is contracts only. | Overclaim will be copied as if SHW-1 already proved the overlay graph and overlay math. | Narrow the sentences, or add overlay↔execution AST tests and keep computation for SHW-2. | Test fails if `execution/` imports `overlay_shadow`. |
| POST-003 | P3 | Open | `9ba7d06` | `assistant/overlay_shadow.py:18` | Unused `field` import. | `from dataclasses import dataclass, field` — `field` unused. | Noise in a frozen contract module. | Drop `field`. | compile/linter. |
| POST-004 | P3 | Open | `bb6898a` / `f40c2c1` | ACTION_PLAN, SESSION_HANDOFF | Allocation plan is on `main` but sequencing authority does not mention it. APQ-0 DoD unmet. | APQ-0 requires ACTION_PLAN to schedule or defer APQ-1. Grep of ACTION_PLAN/handoff at review head: no `APQ-` / `ALLOCATION_POLICY`. | `main` has two frozen research tracks; §8 still reads as SHW-only. | Owner line: schedule APQ-1 **or** explicit deferral; one handoff paragraph. | Docs grep. |
| POST-005 | P3 | Open | `b37ff26` | `analyse_qc_alpha_battery.py:253-254`; benchmark `float(parts[1])` / `int(parts[3])` | SHR-001 typed only turnover. Malformed long/short returns and BROW return/counts still raise bare `ValueError`. | Source. Closed program; no analyser rerun. | Same diagnosability argument as SHR-001, leftover siblings. | Optional wrap if those parsers are touched again. | Same style as `test_parsers_refuse_malformed_tokens_with_typed_errors`. |

## 6. Explicit non-findings

- SHW-1 does not import `ml` or execution; execution does not import `overlay_shadow`.
- Outcomes cannot settle a missing or refused observation.
- Defensive-carry preregistration is still **DRAFT**. `FEATURE_MILESTONE_RECORD` correctly has no SHW-1 entry.
- Allocation plan does not retarget `ACTIVE_UNIVERSE` and does not add a driver family.
- A-002 / stock-selection closure is untouched.

## 7. What this review does not authorize

- SHW-2 runner implementation
- APQ-1 LEAN algorithm
- Freezing defensive-carry gates
- Opening the frozen paper DB with this tree
- Any live or paper order
