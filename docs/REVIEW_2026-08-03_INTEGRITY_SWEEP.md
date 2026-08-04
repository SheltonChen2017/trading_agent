# Whole-project integrity sweep — 2026-08-03

Requested by the owner after the high-velocity dual-agent cycle (~120
commits since 2026-08-02 spanning GR-1C/D/E, Phase 2 hygiene, UI feature
controls, residual signals, GR-3, and GR-5). Scope: the current merged
tree (`9e2826a`) plus a counter-review of Codex's GR-5 review chain
(`944001b..f5c6972`). Performed by Claude.

## Part 1 — GR-5 counter-review verdict

**Codex's review is accepted, 9/10.** GR5REV-001 (P2) was confirmed and
reproduced red on the exact pre-correction snapshot `27fb586`: excluding
the broken-channel alert from `undelivered_critical_alerts` let readiness
report all-clear while that alert stayed open. The correction (include it
until a successful self-test proves recovery and acknowledges it) is the
right shape and preserves the deliberate never-push-through-the-broken-
channel rule. Codex also validated the production Windows channel with one
real isolated toast — the only live-path proof so far.

Counter-review findings against the review itself were minor and are fixed
below (INT-003, INT-004). The larger routing gap (INT-001) predates the
review and was missed by both agents.

## Part 2 — integrity issue ledger (all found this sweep; all FIXED)

No P0 and no P1 issue was found.

| ID | Priority | Status | Location | Issue and impact | Fix | Verification |
|---|---|---|---|---|---|---|
| INT-001 | P2 | Fixed | briefing CLI + UI briefing tab | The owner's GR-5 routing decision has two halves; only one was wired. Warnings were excluded from immediate delivery (correct) but `pending_briefing_alerts()` was never surfaced by EITHER briefing, so warning-severity alerts were delivered nowhere at all — visible only to an operator who opened the Operations tab. Missed by the implementation and its independent review. | `_print_batched_warnings(store)` in the briefing CLI and a warnings expander at the top of the UI Briefing tab; both read the same routing helper. | Three new behavioral tests (CLI prints the batch, prints nothing when empty, AppTest proves the UI renders a seeded warning); the UI wiring was reverse-mutated (severed → AppTest test fails → restored green). |
| INT-002 | P3 | Fixed | `scripts/run_fault_drill.py` + `alert-self-test` CLI | The GR3REV-001 epoch-lineage rule was implemented twice with different shapes and error types — exactly the "same authoritative rule at multiple call sites" drift CLAUDE.md forbids, in the rule protecting promotion-evidence integrity. | One authoritative `assistant.paper_evidence.verify_drill_lineage_commit()`; both producers delegate. | Existing red-direction lineage tests pass unchanged (`PaperEvidenceError` is a `RuntimeError`; message aligned rather than tests edited); 42 focused tests green. |
| INT-003 | P3 | Fixed | `tests/test_alert_delivery.py` (review's edit) | The strengthened escalation test asserted an exact two-element ordering from `list_operational_alerts` where both rows share one `last_seen_at` — the relative order is SQLite scan detail, not contract. | Order-insensitive comparison. | Suite green; no behavior change. |
| INT-004 | P3 | Fixed | `tests/test_alert_delivery.py` | `AlertDeliveryError` imported but never used. | Import removed. | Suite green. |
| INT-005 | P3 | Fixed | `docs/ACTION_PLAN_2026-08-02.md`, `docs/GENERAL_READINESS_STATUS.md` | Doc drift from the cycle's own velocity: "seven tabs" (now eight with Operations), `reconcile.py` "269 lines" (279 after the GR-3 review's halt routing), and §1 still claiming "all of GR-2 through GR-7" do not exist (GR-3 and GR-5 are done). | All three corrected with drift provenance noted. | `git diff --check` clean; text search. |
| INT-006 | P3 | Fixed | Operations tab | `hasattr(store, "list_operational_drills")` guard around an API that exists — a rename would silently render an empty drill list instead of failing loudly. | Direct call. | UI AppTest suite green. |
| INT-007 | — | Hardening | `tests/test_alert_delivery.py` | The cycle's central cross-feature seam (GR-3's atomic halt+alert primitive feeding GR-5's delivery sweep) had per-side tests but no single joined proof. | `test_reconciliation_halt_reaches_the_operator_end_to_end`: real `activate_reconciliation_halt` → real sweep → channel receives the critical, delivery recorded, undelivered list empty. | Passes; exercises real storage + delivery code with only the channel substituted. |

## Part 2 — integration probes that came back CLEAN

- **Merge-content survival** (the lesson of the PR #123 push/merge race):
  the last 12 merges into `main` were each compared tree-level against
  their topic tips. Eleven are byte-identical; `5a6ffd5` (PR #121)
  legitimately differs because its topic was based on older main — its
  files were already verified equal to the topic tip by the signals
  review. No merged content was lost anywhere in the cycle.
- **Halt-path completeness**: zero bare `store.set_kill_switch(True)`
  call sites remain under `assistant/`; every anomaly halt routes through
  the atomic `activate_reconciliation_halt` (GR3CONF-001's mechanical
  sweep rule holds on the merged tree).
- **Fault matrix end-to-end**: `run_fault_drill.py` on the current tree:
  11/11 faults pass, zero unmapped tests, exit 0.
- **Import boundaries**: direct + transitive ML/proposal boundary tests
  7/7 on the merged tree.
- **Schema coherence**: the AP-1 verifier's reference-derived comparison
  covers every table added this cycle (`alert_deliveries` included) by
  construction; migration suite green.
- **Hygiene scans**: no TODO/FIXME markers, no bare `except:`, no mutable
  default arguments in any module added this cycle.

## Honest limits of this sweep

It reviewed the current tree and this cycle's intersection seams; it did
not re-review every one of the ~120 commits individually (each already
carries at least one independent review round), did not exercise the live
broker or a real filesystem-full condition, and did not audit the ML
research stack beyond its import boundary. The one production Windows
toast remains the only live-channel proof; scheduled invocation remains
Phase 5 work.
