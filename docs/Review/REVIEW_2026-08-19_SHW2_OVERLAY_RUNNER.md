# Independent review: SHW-2 overlay shadow runner

Status: **accepted with P2 blockers**. Prepared: 2026-08-19.
Reviewer: Cursor Grok 4.6.
No QuantConnect run. No operator-database open. No scheduler install.
No product correction in this review. SHW-3 and live epoch registration
are blocked on SHW2-001 and SHW2-002.

## 1. Snapshot

| Item | Value |
|---|---|
| Requested range | `d4c04c4..354a233` |
| Base | `d4c04c40b5ce5d448a5efbdbad0519262688a446` (`origin/main`, PR #263) |
| Review head | `354a233243d676aae05b1dc3bf53b29d6b96c2b3` |
| Implementation branch | `origin/user/claude/shw2-overlay-runner-20260818` |
| Review branch | `user/cursor/review-shw2-overlay-runner-20260819` from that exact head |
| Worktree at review | clean, matching origin |

Fetched before review. Every commit in
`git log --reverse --oneline d4c04c4..354a233` is dispositioned below.
Temporary reverse mutation (`month_ends[-1]` → `[0]`) was applied only
in this checkout and restored; the tree ended clean at `354a233`.

## 2. Verdict

**Accept the range with two P2 blockers.** The runner is observation-only
(`register` / `observe` / `mature` / `status`). It does not create,
approve, size, submit, cancel, or replace an order. Registration binds
a clean commit and the preregistration SHA-256. One fetch prices both
cycle boundaries. Gap month-ends occupy refusal slots. Band state is
persisted on `combined_carry_weight`. Failures record a durable
`shadow_overlay` operational alert. `status` prints counts only.

**Do not start SHW-3 and do not register a live epoch** until SHW2-001
and SHW2-002 are fixed. POST-001 re-validation remains under the
storage writers.

No P0. No P1. Two P2. Three P3.

## 3. Per-commit dispositions

| Commit | Disposition | Verification |
|---|---|---|
| `0b5434e` SHW-2: overlay shadow runner | **Accepted with SHW2-001/002.** | +879/−1 across `assistant/overlay_shadow.py` (cycle math + `combined_carry_weight`), `assistant/storage.py` getters, `scripts/run_overlay_shadow.py`, `tests/test_overlay_shadow_runner.py`, example config. `require_clean=True` on register. Provider labeled `yfinance-daily-adjusted`. Early return if the target cycle already exists. Closed-epoch observe refuses `status != "shadow"`. Reverse mutation (a) red. Probes (section 4) confirmed both P2s. |
| `53a8a32` Update SHW-1 contract tests for the combined_carry_weight field | **Accepted.** No issue found. | Available observations require a finite weight in `(0, 1)`; refusals must not carry a weight. |
| `354a233` Record the SHW-2 round in handoff and action plan | **Accepted** as a record. | ACTION_PLAN POST-CLOSURE row and handoff §7am. Scheduler honestly deferred to SHW-4. Handoff §8 still said SHW-2 was blocked on POST-001 (SHW2-004 adjacent staleness). |

## 4. Required reverse mutation and probes

| Check | Result |
|---|---|
| (a) `target = month_ends[-1]` → `month_ends[0]` in `command_observe` | `test_first_observe_is_a_prospective_baseline_not_a_backfill` **RED**: `cycle_session` `2026-01-30` vs `2026-02-27`. Restored. |
| Focused tests after restore | **28 passed** (`tests/test_overlay_shadow_runner.py`, `tests/test_overlay_shadow.py`, `tests/test_overlay_import_boundary.py`) |
| Probe SHW2-001: DDD has no close on 2026-02-27; other members do | `observe` `rc=0`, one **available** baseline at 100.0 |
| Probe SHW2-002: gap Feb→May then `mature` | one outcome for `2026-02-27` with `monthly_returns` universe `1.0`, combined `0.8` (three-month span) |

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SHW2-001 | P2 | Open | `0b5434e` | `scripts/run_overlay_shadow.py` first-observe baseline | Baseline writes `available=True` at 100.0 without requiring every universe and carry member to be priced on the target session. | Probe: DDD omitted on 2026-02-27; runner persisted an available row. | Same partial-imputation failure POST-001 closed at the dataclass; here it is the t0 cycle. Later observes then refuse forever on the unpriced previous boundary. | Refuse the baseline unless every member has a finite positive close on the target session. | New test: missing member at latest completed month-end → refused row, no available baseline. |
| SHW2-002 | P2 | Open | `0b5434e` | `command_mature` | `mature` stores multi-month spans in `monthly_returns`. | Probe: after Feb→May gap, outcome `2026-02-27` had `universe: 1.0`, `combined: 0.8`. | `OverlayOutcome` is documented as a matured **monthly** outcome; SHW-3 will count these as one-month observations. | Do not mature across a refused or missing month-end, or persist an explicit horizon and keep `monthly_returns` only for adjacent month-ends. | Gap-span fixture: `mature` writes 0 monthly outcomes, or labels the horizon and refuses the monthly field. |
| SHW2-003 | P3 | Open | `0b5434e` | `tests/test_overlay_shadow_runner.py` | Closed-stream path untested. | `test_observe_refuses_an_unregistered_or_closed_stream` asserts only the unregistered exit. | The name claims a second gate that `_registration_or_refuse` implements. | Register, set status `closed`, assert observe exits 1 with an alert. | That test red if the status check is deleted. |
| SHW2-004 | P3 | Open | `0b5434e` / `354a233` | `SHADOW_OBSERVATION_DESIGN.md` §4 | Design lists scheduler wiring as SHW-2; implementation defers it to SHW-4. | Design vs handoff §7am. | Readers will treat the milestone as incomplete or the scheduler as already due. | Move scheduler to SHW-4 in the design. | Docs grep. |
| SHW2-005 | P3 | Open | `0b5434e` | `advance_overlay`; `PROVIDER` | Band/weight math is binary float; yfinance adjusted closes are not point-in-time. | `float` in `advance_overlay`; `PROVIDER = "yfinance-daily-adjusted"`. | Operational bands are Decimal strings; CLAUDE.md requires adjusted Yahoo to stay explicitly non-PIT. | Decimal weights, or persist `point_in_time_data=false` on the observation. | Contract/test pin. |

## 6. Explicit non-findings

- No `ml` import from `overlay_shadow.py`; execution-capable modules do not import it (existing POST-002 test).
- Dirty-tree register and provider failure leave `shadow_overlay` alerts.
- Idempotent rerun of an already-recorded target cycle.
- POST-001 contract re-validation still wraps every storage write.
- Example config is a placeholder (`EXAMPLE_TICKER_A`); it is not a live universe.

## 7. What this review does not authorize

- SHW-3 sufficiency reporting
- SHW-4 stream start or Windows scheduler
- Freezing defensive-carry `[TO FREEZE]` gates
- Opening the frozen paper DB
- Any live or paper order
