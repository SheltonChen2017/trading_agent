# Independent review: APQ-3 launch-driver hook (and overlay S4U record)

Status: **accepted after correction**. Prepared: 2026-08-19. Reviewer:
Cursor Grok 4.6. Isolated worktree
`C:\git\customizedAgent\trading_agent-review-apq3` on
`user/cursor/review-apq3-20260819`. No QuantConnect launch. No operator
database. No real scheduled-task install or elevated repair.

The requested range `95a7210..1a63c8c` is two commits: APQ-3 product
and a same-day overlay-scheduler operational record. Both are
dispositioned. This review does **not** execute APQ-4.

## 1. Snapshot

| Item | Value |
|---|---|
| Branch | `origin/user/claude/apq3-driver-hook-20260819` |
| Review head | `1a63c8c4bd98f5703ae9b144c00c7cc86d011972` |
| Base | `95a721044f8c1c6a88322ee92810a08c7dffa55f` (`origin/main` at fetch; APQ-2 review merge #272) |
| Range | `95a7210..1a63c8c` (2 commits) |
| Review branch | `user/cursor/review-apq3-20260819` from that exact head |

Fetched. APQ-3 definition of done: `tests/test_qc_stage0_runner.py` green
(including new allocation tests); no QC.

## 2. Verdict

**Accept both commits after APQ3-001.** The allocation family is
universe-free: bytes upload unchanged, hashed, `require_clean=True`,
`--universe` pairing refuses both ways, `ACTIVE_UNIVERSE` declaration
refuses launch if the file is misclassified, project name is
`{n}. ALLOCATION_POLICY - {YYYYMMDD}`. Screened families still require
`--universe` and still retarget. Driver tests **18 passed**. Plan
mutations independently reproduced (3 red / 1 red). Overlay installer
default `Interactive` is the right logon for this host; SHW4-004 prefix
denylist remains.

The documented live-repair command omitted the installer's three
mandatory path parameters and would fail before registration. Corrected
in this review.

No P0. No P1. One P2 (closed here). Two P3.

## 3. Per-commit dispositions

| Commit | Disposition | Verification |
|---|---|---|
| `6542e56` APQ-3 universe-free allocation family in the launch driver | **Accepted.** | `FAMILIES["allocation"]` → `allocation_policy.py`. `UNIVERSE_FREE_FAMILIES={"allocation"}`. `_resolve_universe` refuses allocation+universe and monthly+None. `launch()` uses raw bytes when universe is None; `^ACTIVE_UNIVERSE\b` refuse; else `_retarget_universe`. `_git_commit_of` still `require_clean=True`. Name `25. ALLOCATION_POLICY - 20260819`. Retarget loop skips universe-free families. Real allocation file has no declaring line (docstring mention is not `^ACTIVE_UNIVERSE\b`). `_retarget_universe` on that file SystemExit found 0. |
| `1a63c8c` Overlay tasks never fired: S4U logon dead under Credential Guard | **Accepted after APQ3-001.** | Installer default `TaskLogonType` S4U → Interactive. Facts record silent skip / 267011 / Credential Guard. Repair is owner-elevated; this review did not run it. Paper **installer source** still defaults S4U (APQ3-002); live paper tasks are claimed Interactive. |

## 4. Reverse mutations

| Mutation | Result |
|---|---|
| (A) `UNIVERSE_FREE_FAMILIES = frozenset()` | **3 failed:** retarget precondition on the real allocation file (found 0); `allocation` not in the set; `_resolve_universe("allocation", None)` requires `--universe`. Restored. |
| (B) `require_clean=True` → `False` | `test_launch_commit_check_requires_a_clean_tree` **RED** (`require_clean is False`). Restored. |

Suite after restore: **18 passed**.

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| APQ3-001 | P2 | Closed in this review | `1a63c8c` | `docs/operations/OPERATIONAL_FACTS.md` repair command | Documented repair was only `-TaskLogonType Interactive`. The installer still requires `-PythonPath`, `-DatabasePath`, and `-ConfigPath`; that one-liner fails parameter validation and does not re-register. | Script `param` block: those three are Mandatory. Facts snippet omitted them. | An owner following the facts file would not repair the silent S4U skip. | Repair block rewritten with the three required paths (PythonPath as a non-Store placeholder). | Read the facts subsection. |
| APQ3-002 | P3 | Open | `1a63c8c` | `scripts/install_windows_operational_tasks.ps1` | Overlay default is Interactive; the **paper installer source** still defaults `S4U`. The "matching every working paper task" claim is about live tasks, not the paper script default. A future paper reinstall with defaults could hit the same Credential Guard skip. | Paper param `TaskLogonType = "S4U"`. Overlay now `"Interactive"`. | Latent sibling trap, not this overlay default. | Optional: change paper installer default in a separate ops fix. | — |
| APQ3-003 | P3 | Open | range | branch contents | APQ-3 product and an overlay ops repair share one branch (two commits). | `git log 95a7210..1a63c8c`. | One-milestone-per-branch is the standing rule; mixing is reviewable but noisy. | No split requested. | — |

## 6. Explicit non-findings

- Allocation launch does not call `_retarget_universe` when classified
  universe-free.
- Hash is of the uploaded bytes (unchanged source for allocation).
- `--universe` is optional at argparse and enforced in `_resolve_universe`.
- SHW4-004 prefix denylist is still in the overlay installer.
- Changing the installer default does not repair already-registered S4U
  tasks; that remains owner-elevated.
- Missed 14:45/14:55 overlay no-ops do not skip a month-end observation
  (July baseline exists; August incomplete).
- No QC was launched.

## 7. What this review does not authorize

APQ-4 cloud run, APQ-5 analyser pass, elevated overlay reinstall, any
paper/live order.
