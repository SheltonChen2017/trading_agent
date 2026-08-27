# Analyst Revisions V2 lane — independent review of the remediation synchronization

**Review date:** 2026-08-27
**Reviewer:** Claude (dedicated Analyst Revisions V2 lane review session)
**Lane branch:** `codex/strategy-analyst-revisions-v2`
**Reviewed range:** `a4f58e6^..5a5c7ab` — 21 commits, every one disposed below
**Review checkout:** dedicated clone `C:\git\customizedAgent\trading_agent_analyst_revisions`
(no checkout shared with another agent, per the workflow's isolation rule)

**Disposition: ACCEPTED AFTER CORRECTION**, with one correction applied by this
review and a P0–P3 ledger of eight open items, none of which blocks the
candidate's stated zero-access boundary.

**Trading authority: none.** This review authorizes no provider access, no
outcome access, no research look, no QuantConnect run, no paper or live
deployment, and no policy change. The candidate remains unaccepted research
scaffolding until Codex counter-reviews this exact pushed head.

## 1. Scope change recorded during review

The owner directed a review of `a4f58e6e^..d8d0ad6`. While the review was in
progress, the lane branch advanced three commits to `5a5c7ab` and this clone was
fast-forwarded onto it by a `pull --ff-only` at 2026-08-27 14:57 -0700 (reflog
verified; a clean fast-forward, no history rewritten).

Per `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` §1, the range was
**extended rather than silently drifted**: the review head is `5a5c7ab` and all
three additional commits carry dispositions below. The extension is safe to
combine with the earlier work because
`research/analyst_revisions_v2/`, `data/exchange_calendar.py`,
`assistant/temporal_integrity.py`, `execution/broker_contract.py`, and
`assistant/dispatch_fence.py` are **byte-identical** between `d8d0ad6` and
`5a5c7ab` (`git diff --stat` empty), so every probe and mutation performed
against `d8d0ad6` remains valid at the review head. Only
`assistant/portfolio_snapshot.py` changed, and the full suite was rerun on the
final tree.

## 2. Commit dispositions

| # | Commit | Disposition | Basis |
|---|---|---|---|
| 1 | `a4f58e6` | Accepted | Counter-review restoration; independently verified earlier this session (61/61 active-document checks; guard mutation-tested). |
| 2 | `5d99ae4` | Accepted | Bool-as-number policy weakening (SYS-P1-001) closed at the parser boundary. |
| 3 | `6b3b734` | Accepted | Cross-process dispatch fence introduced (SYS-P1-003). |
| 4 | `4c671d3` | Accepted | Execution authorization bound to broker context. |
| 5 | `26b14ff` | Accepted | Anomaly park + kill switch + alert made one `BEGIN IMMEDIATE` transaction (SYS-P1-005); halt is written even when a concurrent terminal transition wins the proposal row. |
| 6 | `7a79109` | Accepted | Cancel-all drain fenced. |
| 7 | `a7c423b` | Accepted with test-coverage note | Fork hardening is correct, but its regression test cannot execute on Windows (CLR-007). |
| 8 | `6b9ef21` | Accepted | Coherent account-scoped snapshot (SYS-P1-002); execution discards the caller preview and captures its own. |
| 9 | `31c7144` | Accepted | Closes the broker open-order indexing race; completed by later work on the branch. |
| 10 | `00954b2` | Accepted after correction | Large shared hardening commit; source of CLR-002 and CLR-004. |
| 11 | `49fe8e8` | Accepted | The ARV2 fail-closed authority layer. Independently probed; see §3. |
| 12 | `1a6f6cb` | Accepted | Registers the ARV2 research entry point and boundary. |
| 13 | `5fb451c` | Accepted (governance verified) | Edits otherwise-frozen coordination files under an explicit, bounded, in-place owner exception; see §5. |
| 14 | `130af4c` | Accepted | Lane-record boundary statement. |
| 15 | `7029acb` | Accepted | Corrects the candidate status to "assembled but unaccepted". |
| 16 | `68ae4b4` | Accepted after correction | Shared regression closure; source of CLR-001 (corrected by this review). |
| 17 | `653a9c0` | Accepted | ARV2 decimal/structural-zero hardening. |
| 18 | `d8d0ad6` | Accepted | Lane-record ledger row. |
| 19 | `a8f9071` | Accepted | Correct fix: `total_equity` was aggregated from already-rounded display values while `total_equity_exact` aggregated exact values, so a multi-position portfolio could accumulate cents of drift and fail its own display/exact integrity contract. The fix rounds the exact aggregate once, consistent with CLAUDE.md §5. |
| 20 | `c167574` | Accepted | Lane-record ledger row. |
| 21 | `5a5c7ab` | Accepted | Lane-record ledger row. |

No commit was rejected. No commit was reviewed only as part of a combined diff.

## 3. Independent reproduction of the material claims

The lane record's central claim is that the ARV2 layer is **fail-closed and has
consumed zero research looks**. That claim was not taken on trust. It was
re-derived with an adversarial probe written outside the repository and run
against the lane tree:

| Probe | Result |
|---|---|
| `require_registered_source_bytes` for all six source kinds | all six refuse |
| `run_authorized_outcome_slice` with an instrumented loader | refused; **`outcome_loader` never executed** |
| `authorize_outcome_access` | cannot mint a permit under any input |
| Forged `OutcomeAccessPermit` carrying the real module token | refused |
| Forged, internally self-consistent `VerifiedAnalystPolicy` (correct evidence hash + real token) | refused — out-of-band weakref authority defeats the forgery |
| `load_reviewed_preregistration` against the draft | refused (registry empty) |
| Legacy analyst runner entry point | refused before any network or outcome access |
| Cross-section evidence / `PortfolioRules` | both refuse; no non-empty portfolio is constructible |

The four committed authority artifacts were read directly and are genuinely
empty (`entries: []`, `authority_mode: "zero_access"`).

**Blueprint errata verified by golden values.** The PDF's defective equations
are corrected as the lane record claims:

- `N_eff` (AR-P2-006): zero mass → `0`; a single `1e-30` contributor → `0` (no
  epsilon blow-up); one contributor → `1`; four equal → `4`; `[1000,1,1]` →
  `1.004002`.
- Independence (AR-P2-007): five events from **one** firm → independent
  `N_eff = 1` (raw intensity 5 retained separately); five firms → `5`; fifteen
  firms on **one** catalyst → `1`.
- Reliability is bounded, rejects out-of-range coverage and rejects `bool`.

**Timing boundaries (AR-P2-009) verified exhaustively**, including the dangerous
direction:

| Case | Result |
|---|---|
| Exactly at the 09:30 open | next session — "strictly after" honored |
| 1 µs before / 1 µs after the open | same session / next session |
| Intraday, after-close | next session |
| Friday, Saturday | Monday |
| Jul 3 half-day, Dec 24 | Jul 5, Dec 26 (holidays skipped) |
| Date-only | **second** session strictly after (the literal V2 rule) |
| Naive / malformed / non-string clocks | all refuse |
| Four-clock monotonicity | each inversion refuses |

DST is handled correctly (13:30Z summer open vs 14:30Z winter open).

**Mutation testing — the tests genuinely bite.** Five safety invariants were
reverted one at a time in a throwaway worktree pinned at `d8d0ad6`; every one
turned the ARV2 suite red (baseline 169 passed):

| Mutation | Result |
|---|---|
| date-only delay 2 → 1 session | **6 failed** |
| accepted-event zero-access latch removed | **16 failed** |
| `N_eff` epsilon reintroduced | **1 failed** |
| independence `min` → `max` | **1 failed** |
| next-open `>` → `>=` | **1 failed** |

The worktree was restored and removed; the lane checkout was never modified.

## 4. Issue ledger

| ID | Pri | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CLR-001 | P3 | **Corrected** | `68ae4b4` | `tests/test_ml_evidence_operations.py:762` | New test passes `sys.executable` to an installer that correctly refuses Microsoft Store app-execution aliases, so it fails on any machine whose `python` is the Store alias — the default on the owner's machine. | Fails under Store alias (zero-byte reparse point); **passes** under `C:\git\trading_agent_venv\Scripts\python.exe`. | CLAUDE.md §10 requires the full suite to pass on the exact final tree; a test whose outcome depends on interpreter provenance makes that gate unreproducible and reports a permanent false failure to the owner. | Skip when the interpreter is not a real executable, matching how sibling tests skip off-Windows. | Red under Store alias before, skipped after; still passes under a real interpreter. |
| CLR-002 | P2 | Open | `00954b2` | `assistant/portfolio_ledger.py:364`, `assistant/tax_lots.py:96`, `assistant/corporate_actions.py:176` | SYS-P2-002's exact-decimal chain stops at `list_fills`. Every authoritative lot/ledger consumer still reads the float `qty`/`price` and ignores `qty_decimal`/`price_decimal`/`numeric_evidence_status`; `tax_lots.Fill` actively rejects `Decimal`. | `grep` for the exact fields in the three consumers returns **zero** hits while `storage.py` emits them. | The remediation's own definition of done is "read exact text for all ledger/lot consumers"; cost basis, realized P&L and tax lots still round-trip through binary float, and the `legacy_rounded_unrecoverable` disclosure is silently dropped. | Not applied — outside the lane's frozen-file and bounded-scope authority; belongs to the shared remediation owner. | — |
| CLR-003 | P2 | Open | `7a79109`, `31c7144` | `assistant/dispatch_fence.py:35`; `assistant/order_reconciler.py:838,939` | Cancel-all's two fence acquisitions each time out at 30 s, but the fenced dispatch body holds both fences across broker preflight + submit (2–3 × 30 s HTTP timeouts). On a degraded network the stop may never publish and an order can reach the broker after cancel-all returns. | Constants read directly; mitigation confirmed at `order_reconciler.py:1659-1688`. | The audit's "after cancel-all returns, no queued dispatch proceeds" can still be violated. | Not applied — shared execution path, needs a timeout-budget decision by the shared owner. | **Severity downgraded from the P1 originally proposed**: `containment_incomplete` forces `book_stable=False` and records a durable critical incident naming the fence/stop errors, so this fails loudly and never reports success. |
| CLR-004 | P2 | Open | `00954b2` | `assistant/portfolio_snapshot.py:1002` | The non-strict snapshot builder sets `open_orders_available=True` over unvalidated broker rows, so a malformed order is silently skipped while the book appears complete — the original SYS-P1-006 condition. | Line read; strict path validates at `:833/:838`, non-strict path has no validator call. | Advisory/preflight surfaces present an incomplete order book as complete, and operators read preflight as "this would be approved". | Not applied — shared file. | **Cannot reach execution authority**: `execution_service.py:382` does `del caller_preview` and re-captures its own strict snapshot (verified), so exposure is confined to display/preflight. |
| CLR-005 | P3 | Open | `00954b2` | `risk/execution_gate.py:1248` | The remediation widens what trips the global kill switch (any strict-validation failure), and the kill switch blocks **all** trades including legitimate risk-reducing sells. | Code read; no risk-reduction carve-out in `_check_kill_switch`. | CLAUDE.md §5 states a conservative safeguard must not obstruct a legitimate risk-reducing sell. Emergency *cancellation* correctly remains available, so this is a partial tension, but the blast radius is widened by the new halt triggers. | Not applied — requires an explicit owner policy decision, not a unilateral reviewer change to a master stop. | — |
| CLR-006 | P3 | Open | pre-existing | `ml/earnings_gap.py:39`, `data/earnings_data.py:28` | A hardcoded 16:00 ET close survives the "one neutral shared calendar" consolidation, so on ~9 early-close sessions a 14:30 ET release is misclassified `intraday` instead of `after_close`. | Both files are **untouched by this range** (verified) — pre-existing, not a regression; but the range created the shared calendar without consolidating them. | Event-time misalignment in a research path, and a second drifting definition of "market close". | Not applied — out of the bounded synchronization scope. | — |
| CLR-007 | P3 | Open | `a7c423b` | `tests/test_dispatch_fence.py:166` | The fork-inheritance regression test — the entire point of `a7c423b` — is `skipif(not hasattr(os, "fork"))`, so it never executes on Windows, the owner's only supported platform. | Line read. | The hardening is unverified on the platform that actually runs it; a regression would be invisible here. | Not applied — needs a Windows-expressible equivalent. | — |
| CLR-008 | P3 | Open | `26b14ff` | `tests/test_atomic_reconciliation_anomaly.py:127` | "Crash" fault injection is simulated with monkeypatch/`RAISE(ABORT)` on a live store object; no process kill and no database reopen. | Verified by reading the test bodies. | The audit asked for "crash after each SQL statement, reopen the database"; durability across a real crash rests on SQLite's guarantee alone. The repo already has a genuine `os._exit` crash test in `tests/test_dispatch_fence.py:144`, so the technique exists and was simply not applied here. | Not applied — shared test surface. | — |

Resolved and open items are both retained. Nothing was deleted after fixing.

## 5. Governance findings

**Frozen-file edits are covered.** `5fb451c` edits
`THREE_STRATEGY_PARALLEL_WORKFLOW.md`, `THREE_STRATEGY_PROJECT_DIRECTION.md`
and `CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md`, which the parallel workflow
otherwise freezes. It is legitimate: the commit adds an explicit, bounded,
self-describing **one-time common-remediation exception** that names its scope,
its expiry, and states that synchronization is not acceptance and grants no
credential, provider, outcome, QC, broker, or deployment authority. The same
text is present on `main`, merged by the owner, which corroborates that the
exception is owner-directed rather than self-authorized.

**Cross-lane isolation held.** The exception requires that Analyst-specific
research code must not enter the other two lanes. Verified against the live
remotes: `research/analyst_revisions_v2/` contains **30 files on this lane and 0
files on both `codex/strategy-insider-buying` and
`codex/strategy-short-interest`**.

**Shared-remediation commits are patch-identical to the merged main work.** All
sixteen synchronized commits were compared to their `main`-side sources by
stable patch ID; every pair is identical, so this lane introduced no divergent
variant of a shared safety fix.

## 6. Validation on the exact final tree (`5a5c7ab`)

- Full suite at `d8d0ad6`: **5,433 passed, 1 failed, 2 skipped, 25 warnings**
  in 1,947 s. The single failure is CLR-001 and is interpreter-provenance
  dependent, not a product defect.
- Focused ARV2 suite: **169 passed** (baseline for the mutation matrix).
- `tests/test_dispatch_fence.py`: 24 passed, 1 skipped (the skip is CLR-007).
- Full suite rerun on the final tree after the CLR-001 correction: recorded in
  the lane record ledger row for this push.
- No provider, credential, licensed row, outcome, QuantConnect, broker,
  operator-database, or live-scheduler access occurred. **Zero research looks.**

## 7. Remaining gates

Unchanged by this review: owner decisions on the ARV2-0 open cells, a reviewed
spec anchor, governed source admission, and an external cross-machine
append-only permanent-look authority must all close before any production
normalization, price/outcome join, real score, ETF construction, non-empty
portfolio, or QuantConnect run. ARV2-4 (the stock-first study) remains the
stop/go gate ahead of any ETF topology work.

## 8. Next authorized step

Codex counter-reviews this exact pushed head, including the CLR-001 correction
and its regression evidence, and disposes CLR-002 through CLR-008 — several of
which belong to the shared remediation owner rather than to this lane.
