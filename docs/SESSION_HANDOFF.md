# Development session handoff

Prepared: 2026-08-06 afternoon, after independent review and correction of
Claude's GR-7b idle-cash reporting on
`user/grok/review-gr7b-idle-cash-20260806`.

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json` (`4a942cbc…`). Operational checkout
pinned there. **Never deploy development commits mid-epoch.**

`paper-epoch-001` is CLOSED (plumbing shakedown only; do not cite).

## 2. Latest outcome — GR-7b accepted after correction

Claude tip `e25aa42` implemented idle-cash reporting vs policy bounds and
the mandate volatility objective. **Independently accepted after
correction.**

| ID | Pri | Result |
|---|---|---|
| GR7BREV-001 | P1 | CLI used `_packet(store=…)` and wrote GR-4 provider fetches while claiming read-only |
| GR7BREV-002 | P1 | Reports UI used `_load_packet` (same write class; broke STRICTLY READ-ONLY) |
| GR7BREV-003 | P1 | NaN/Inf measured vol raised `ValueError` → traceback (not `CashReportError`) |
| GR7BREV-004 | P2 | Negative measured vol accepted as available |

Ledger: `docs/REVIEW_2026-08-06_GR7B_IDLE_CASH.md`.
Claude quality: **7.8/10 submitted; 9.4/10 corrected**.

Surfaces after correction: `assistant/cash_reporting.py`, CLI `idle-cash`,
Reports expander — portfolio from Alpaca/sample only; no provider-fetch
writes; no action-shaped fields.

## 3. Validation (exact final tree)

- Focused: **33 passed**.
- Full suite: **2917 passed / 0 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.
- Nothing deployed; ops checkout stays at `9a91498`.

## 3a. Owner decisions on record (do not re-derive)

**`require_earnings_data` stays `false`** (2026-08-06, measured not
assumed). The feed resolved 5/7 of the account's holdings; the two failures
are structurally different and the policy **cannot tell them apart** —
`NVDL` is a leveraged ETF with no earnings event at all, while `BBB` is a
small cap whose real earnings the provider does not carry. Setting it
`true` would permanently block every ETF buy — including the SOXX/SOXL-style
strategy — while correctly blocking BBB. Residual exposure is BBB-like
names: real earnings, invisible to the feed, silently unchecked.
Risk-reducing SELLs are exempt either way.

**Epoch re-bind (option A)** was chosen and executed 2026-08-06 after the
owner reversed an earlier option-B decision; `paper-epoch-001` was closed
with one observation rather than accumulating 60 sessions under a policy
its own lineage forbade.

## 3b. Machine-local operational facts

Not derivable from the repository, and expensive to rediscover.

- **Launch the app only via `C:\git\launch_trading_app.ps1`.** It pins the
  operational checkout, sets `TRADING_ASSISTANT_DB`, and re-reads Alpaca
  credentials from the USER-scope registry at every launch — a long-lived
  shell otherwise hands the app a revoked key (observed after the
  2026-08-05 rotation).
- **`C:\git\epoch_swap_tasks_elevated.ps1`** (machine-local, elevated)
  disables/enables the four `TradingAgent-Paper-*` tasks for a deploy. On
  this host a non-elevated `Stop-ScheduledTask` **succeeds** while
  `Disable-ScheduledTask` returns "Access is denied" — so a merely stopped
  long-runner is restarted by its own 5-minute heal trigger. Disabling is
  what actually holds them down.
- **The process singleton is live.** `data/locks/order-monitor.lock` and
  `data/locks/operations-watchdog.lock` being held is the direct evidence
  that the deployed tree, not the previous one, is executing.
  `data/locks/` is gitignored.
- **Backups land in `data/backups/`** — on the SAME disk as the operator
  database. GR-6's off-machine requirement is NOT met; a drive failure
  currently loses the running epoch.
- This host keeps losing console-hosted processes to `0xC000013A`. The
  scheduled tasks self-heal; **the Streamlit app does not**, because
  nothing supervises it.

## 4. What is next

1. Confirm `paper-epoch-002` observation rows as sessions accumulate.
2. Roadmap: **GR-7c** performance attribution, **GR-6**, or **GR-7d** owner
   decision — GR-7b does not reorder the plan.
3. Owner decision still visible in the report: policy exposure ceiling may
   make the mandate vol floor structurally unreachable; that is not an
   engineering fix.
4. FPS-003 intermittent UI chrome title test remains open from earlier.
   Severity now looks **overstated at P2**: it has passed every full run
   since (5+), and the likely cause is contention during a ~2,900-test run.
   Do NOT close it on a green suite — capture the full traceback the next
   time a full run fails, since the original was lost to a `tail` pipe.
5. **Watch the `Decimal(str(...))` pattern.** Three consecutive review
   passes each found another raw conversion on a share or money field
   (FPS-001 → GFPS-001 → CFPS-001). The remaining raw sites sit inside
   their own try/except helpers, but if a fourth appears the answer is a
   lint/AST guard banning bare `Decimal(str(...))` outside
   `assistant/money.py`, not another point fix.

## 5. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Reports page must not write provider-fetch or execution evidence.
- Incomplete/unverified reports must say so in the artifact.
- Which policy file governs must always be visible on screen.
