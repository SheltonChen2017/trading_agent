# Independent review — Claude counter-review and AP-11

Prepared: 2026-08-13 by Codex

Final disposition: **accepted after correction**. Claude's production change,
pytest collection fix, and regression tests are correct. The review found one
P3 current-document defect, corrected it, and found no P0, P1, or P2 issue.
Implementation quality: **9/10**.

## 1. Snapshot and scope

- Base: `1a46881` (PR #196 merge).
- Submitted head: `4ae77f2` (PR #199 merge), reviewed on
  `codex/review-claude-post-ipr-20260813`.
- Ordered range: `1a46881..4ae77f2`, six commits.
- All three merge trees equal their submitted branch tips exactly; there is no
  merge-only conflict-resolution delta.
- Reviewed contracts: pytest discovery, current-record topology, explicit
  as-of-clock compatibility, live-path post-read clocks, conservative
  freshness failure, report timestamp semantics, and the cumulative current
  documentation state.
- No operator database, broker endpoint, scheduler, operational checkout,
  credential, or evidence-epoch state was read or changed.

## 2. Commit dispositions

| Commit | Disposition | Review result |
|---|---|---|
| `594decf` | **Accepted.** | IPRCR-001 accurately corrected the already-merged PR #196 topology. IPRCR-002's `pytest.ini` restates pytest 9.1.1's exact nine defaults and adds only the wholly gitignored `artifacts` directory. A planted same-basename probe was excluded with the configuration restored and produced the expected import-file-mismatch collection error when only `artifacts` was reverse-mutated out. |
| `3aaccf0` | **Accepted.** | PR #197 merge-only commit; tree equals `594decf`. |
| `0100f04` | **Accepted after correction.** | Both AP-11 forwarding changes preserve a genuine caller-supplied as-of clock and allow live nested checks to capture their own post-read clocks. Each submitted regression failed under its one-line reverting mutation. CODCR-001 corrected incomplete current-state documentation; production code and submitted tests were unchanged. |
| `72b6278` | **Accepted after correction in the cumulative tree.** | PR #198 merge-only commit; tree equals `0100f04`; no merge-only issue. |
| `18497ac` | **Accepted after correction.** | Correctly recorded PR #197/#198 topology, but the final current records still retained the older full-production-fix claim addressed by CODCR-001. |
| `4ae77f2` | **Accepted after correction in the cumulative tree.** | PR #199 merge-only commit; tree equals `18497ac`; no merge-only issue. |

## 3. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CODCR-001 | P3 | **Closed** | `0100f04`, final records at `18497ac` | `docs/ACTION_PLAN_2026-08-02.md`; `docs/OPERATIONAL_FACTS.md`; `docs/SESSION_HANDOFF.md` | AP-11 proved from a live negative-age alert that deployed orchestration still disabled the nested AP-7 post-read clock, yet the action-plan summary and durable operational facts still said the full AP-7 path was confirmed fixed in production. The action-plan AP-7 row repeated that inference. A reader could mistake deployed site-level code for the undeployed end-to-end repair. | `test_ap11_supersedes_the_full_ap7_production_fix_claim` failed on both exact stale claims before correction. Source tracing confirmed AP-11 is merged at `72b6278` but absent from frozen epoch-004 `b837374`. | Current operational records are decision inputs. They must distinguish a historical two-cycle green observation from proof of a complete fix, especially while the correcting production path remains undeployed. | Preserved the original observation as point-in-time evidence, recorded that AP-11 invalidated its full-fix inference, distinguished deployed AP-7 site code from undeployed AP-11 orchestration, and added a known-stale/relationship guard. | New guard: 1 failed red / 1 passed green. Full active-document and affected-clock/hygiene suite: 92 passed. |

No issue remains open.

## 4. Independent verification

- Submitted exact tree: **3,493 passed, 0 failed, 0 skipped, 25 known
  dependency warnings** in 697.22 seconds under the repository venv.
- AP-11 operational-health reverse mutation: expected failure with
  `age_seconds=-1.000000`; restored implementation passed.
- AP-11 platform-readiness reverse mutation: expected failure because a
  manufactured datetime was forwarded instead of `None`; restored
  implementation passed.
- IPRCR-002 behavioral probe: restored config collected 3,494 real tests and
  excluded the planted colliding module; removing only `artifacts` collected
  the probe and aborted on one import-file-mismatch error.
- CODCR-001 guard: **1 failed red / 1 passed green**.
- Corrected focused suite (`operations`, transaction readiness, readiness
  budget, platform readiness, module hygiene, active-document consistency):
  **92 passed** in 16.54 seconds.
- Corrected exact review tree: **3,494 passed, 0 failed, 0 skipped, 25 known
  dependency warnings** in 693.96 seconds under Python 3.13.14.
- Repository-prescribed `compileall` (including `research`), `git diff
  --check`, and final source/config restoration checks passed.

## 5. Safety and roadmap boundaries

This range does not change paper mode, exact human approval, kill-switch
behavior, atomic claims, budget reservations, ambiguous broker outcomes,
idempotency, replacement resolution, reconciliation matching, forbidden
imports, or ML/LLM authority. Those execution contracts were out of scope
rather than re-proven. AP-11 remains merged development code and is not
deployed into frozen `paper-epoch-004`; deployment or an epoch roll still
requires separate owner authorization.

This review is not a new product milestone, so no feature-milestone entry was
added. The action plan remains the sequencing authority.
