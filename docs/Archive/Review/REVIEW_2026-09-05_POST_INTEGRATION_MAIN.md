# Review — `main` after the 2026-09-04 cross-lane integration (2026-09-05)

Reviewer: Claude (independent), generic separate-review-branch workflow
Review/fix branch: `user/claude/post-integration-review-fixes-2026-09-05`
Implementer under review: the Review lane session that produced PR #331

## 1. Exact snapshot

| Item | Exact value |
|---|---|
| Base commit | `aefa0ecc` (pre-integration `main`) |
| Review head | `86417b89` (merge of PR #331, current `origin/main` at review time) |
| Ordered range | 7 non-merge commits, 17 files, +768 / −28 |
| Fix commit (this review) | `f4764671` — six files, +190 / −12, branched from `86417b89` |

Working tree was clean apart from the pre-existing untracked `tmp/`;
`git diff --check` clean on the range and on the fix.

## 2. Verdict

**Accepted with corrections.** The integration's fixes are correct in
direction and mutation-verified. Two P2 items and three P3 items were found;
all five are shared-application or test-infrastructure issues. **None touches
`strategies/`, `backtest/`, `signals/`, a lane package under `research/`, or
any QC backtest run.** The one P1 is operational state on this host, not a
defect in the range.

## 3. Per-commit disposition

| Commit | Content | Disposition |
|---|---|---|
| `7f99f303` | F-1 sleeve clock seam, F-2 child-process redirect, F-3 conftest leak guard, F-4 `.gitattributes`, F-5 Briefing smoke stubs, F-7 test rename | Accept with issues (PIR-002, PIR-003, PIR-005) |
| `3114a153` | cycle passes `now=at`; guard decoder bound at import | Accept |
| `6ef66eed` | F-8 layout-deterministic TPR self-declared-review test | Accept — `_bare_tmp_path_refusal` mirrors `_repository_root` (`preregistration.py:1802`) and the loader's refusal order (1807 → 1914 → 1936) exactly |
| `149be1ce` | integration record + lane docs | Accept |
| `0ebac7fc` | handoff | Accept; see PIR-006 for a claim that did not hold |
| `1955fdbc` | F-8 record | Accept |
| `c0a8aeb2` | handoff F-8 hash | Accept |

Every symbol the new code references was confirmed to exist
(`_canonical_runtime_root`, `_RUNTIME_FENCE_ROOT`, `_STATE_DIRECTORY_NAME`,
`_EMERGENCY_STOP_FILE_NAME`, `_RUNTIME_STOP_STATE_VERSION`,
`unrealized_by_lot(now=)`, the telemetry test named in the F-7 docstring).

## 4. Issue ledger

| ID | Pri | Where | Finding | Classification | Status |
|---|---|---|---|---|---|
| PIR-001 | P1 | this host's `%LOCALAPPDATA%\trading_agent\runtime\state\execution-emergency-stop.json` | Real runtime stop is `active`, generation 26, 26 open incidents, all with `origin_database` under `…\Temp\pytest-of-shelt\pytest-NNN`. Every proposal on this host — including risk-reducing sells — is refused. The integration record's "generation 42 / 42" figure was the other host. | Confirmed (read-only inspection) | **Open — owner decision.** Not repository code; the integration stops new debris. The documented clear path needs the origin databases, which are gone. |
| PIR-002 | P2 | `.gitattributes`, `tests/test_shared_research_eol_attributes.py` | F-4's attribute does not rewrite an existing checkout; `git ls-files --eol` on this checkout of `86417b89` showed `i/lf w/crlf attr/-text` for both `research/ml_specs/*.json` while the attribute test stayed green (it deliberately asserted the attribute, not the bytes). The integration record's SI-SYNC-001 row says stale copies "are restored"; on this host they were not. | Confirmed | **Fixed** in `f4764671`: second guard asserts worktree EOL == index EOL; failure names the heal `rm <path> && git checkout -- <path>` (a plain `git checkout --` is a no-op on a stat-clean file — verified). This host's `main` checkout was healed. |
| PIR-003 | P2 | `assistant/sleeve_report.py::evaluate_sleeves`, `assistant/sleeve_notifications.py::run_sleeve_notification_cycle` | Injected `now` was not validated. A naive `datetime` reaches `is_long_term` (`tax_lots.py:318`), raises `TypeError`, and the per-position branch at `sleeve_report.py:185` converts it to `lot_coverage="unavailable"` for **every** growth position — a plausible, lot-less report instead of a refusal (CLAUDE.md §7/§8). No production caller passes `now` today. | Confirmed | **Fixed** in `f4764671`: refused with `SleeveReportError` at the boundary; the cycle inherits the refusal before any watch state or alert is committed. |
| PIR-004 | P3 | `tests/conftest.py` leak guard | Attribution by `tmp_path.parent` alone: a stale incident left under a reused fixed `--basetemp` by an earlier run would error every test of the next run; under xdist (not installed) a sibling worker's leak would be missed. | Confirmed (a); (b) not exercisable here | **Fixed (a)** in `f4764671`: an incident is attributed only if its `activated_at` is not before session start; unparseable/naive stamps stay attributed by path. (b) documented only. |
| PIR-005 | P3 | `tests/conftest.py`, integration record F-3 wording | The guard runs in fixture teardown, so a leak is a teardown ERROR; the leaking test's own assertions still show passed. Record says "fails any test". | Confirmed | **Fixed (wording)** in `f4764671` docstring; the mechanism is inherent to teardown-phase checks. |
| PIR-006 | P2 | handoff §0B, lane branches | The handoff states the integration commits were applied to every lane branch and pushed. `git branch -r --contains` for `7f99f303`, `3114a153`, `6ef66eed` returns only `origin/main`; no lane checkout or lane doc references the round. The four lanes therefore still carry the wall-clock failures, the unguarded child-process leak, and no EOL attributes. | Confirmed | **Open — owner decision** on how the lanes receive the integration (cherry-pick the three commits plus `f4764671`, or merge `main`). |
| PIR-007 | P3 | `tests/conftest.py` leak guard | Reads the operator's real stop file (`SHGetFolderPathW` + file read) at every test teardown. Read-only; harmless. | Confirmed | Noted, no change. |

Cleared (checked, not issues): other `sys.executable` child tests
(`test_dispatch_fence.py`) already redirect `_RUNTIME_FENCE_ROOT` in the
child; `test_ml_evidence_operations` builds its store in-process;
`rebalance_trim.py:518` already threads `now`; both production
`evaluate_sleeves` callers keep the live clock; `research/__init__.py` is an
empty blob so its `eol=lf` is moot but harmless.

## 5. Consequence if left unfixed (owner question, answered 2026-09-05)

None of the seven can produce a wrong financial number, an unintended order,
or corrupted evidence; every one fails closed. PIR-001 has a present-day cost
(paper operation on this host is dead, so prospective evidence is not
accumulating here). PIR-002 is latent and machine-local (parsers are
CRLF-tolerant; byte digests are not). PIR-003 would become a silent no-op in
tax-lot alerts only if a caller ever wired a naive timestamp in.

## 6. Validation of the fix (`f4764671`)

- Focused: `tests/test_sleeve_report.py tests/test_sleeve_notifications.py
  tests/test_runtime_stop_leak_guard.py
  tests/test_shared_research_eol_attributes.py` — **97 passed**.
- Mutations (each restored in a `finally`): drop the naive-clock refusal →
  `2 failed`; drop session-start attribution → `1 failed, 1 error`; make an
  unusable stamp hide a leak → `1 failed`; rewrite a protected spec to CRLF
  in the working copy → `1 failed`, healed by the message's own command.
- `python -m compileall -q assistant backtest data execution ml risk scripts
  signals strategies tests research baskets.py config.py market_analytics.py`:
  clean. `git diff --check`: clean. Staged blobs verified `i/lf`.
- Broader focused run on the committed tree (twelve files including the
  integration's own targets): **618 passed, 4 skipped, 0 failed** (245 s).
- Not run: the full suite. The change is one boundary check in
  `evaluate_sleeves` plus test infrastructure; the last full run remains the
  one on `3114a15` recorded in `BUG_FIX_INTEGRATION_2026-09-04.md` §7.

## 7. Untested / remaining

- PIR-004(b): xdist attribution is untested (not installed).
- The leak guard's real-file read was exercised on this host only.
- PIR-001 and PIR-006 await owner decisions; neither was touched.
