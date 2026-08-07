# Operational facts and standing owner decisions

**This file is APPEND-AND-AMEND, never rewritten.** That is the whole point
of it.

`docs/SESSION_HANDOFF.md` declares itself to "completely replace the prior
handoff", which is correct for a per-round status document but makes it a
bad home for anything durable: each rewrite keeps what is about the current
milestone and quietly drops the rest. On 2026-08-06 the same seven facts
below were dropped by one such rewrite, restored, and dropped again by the
next one. Restoring them a third time would not have worked either — the
container was the problem, not the author.

So: facts that outlive a milestone live here. The handoff links to this
file instead of restating it. Change an entry when it becomes wrong; do not
delete an entry because the current round is about something else.

---

## 1. Standing owner decisions

### `require_earnings_data` stays `false` (2026-08-06)

Measured, not assumed. The earnings feed resolved 5 of the account's 7
holdings. The two failures are **structurally different and the policy
cannot tell them apart**:

- **NVDL** is a leveraged ETF. It has no earnings event at all; its
  "unavailable" is correct and permanent.
- **BBB** is a small cap whose real earnings the provider does not carry.
  Its "unavailable" hides a genuine event — exactly what the blackout
  exists for.

Setting the flag `true` would therefore permanently block every ETF buy,
including the SOXX/SOXL-style strategy this project has spent the most
research effort on, while correctly blocking BBB. Leave it `false` until
"not a single-name equity" is separable from "earnings exist but are not
visible". Residual exposure is BBB-like names: real earnings, invisible to
the feed, silently unchecked. Risk-reducing SELLs are exempt either way.

### Epoch re-bind, option A (2026-08-06)

The owner initially chose to keep `paper-epoch-001` and select the policy by
hand, then reversed once the evidence consequence was explicit.
`paper-epoch-001` was closed with a single observation rather than
accumulating 60 sessions whose own lineage named a policy
(`allow_new_positions=False`) that forbade the buys they contained.

### Benchmark is SPY (2026-08-06)

`paper_evidence` binds `benchmark_ticker` into every observation, defaulting
to SPY. GR-7c attribution uses the same ticker deliberately: a second index
would put two benchmarks in one epoch and leave a later reader unable to say
which was authoritative. QQQ remains available as an optional *diagnostic*
for separating a tech style bet from selection — never as the record.

---

## 2. Machine-local operational facts

Not derivable from the repository, and expensive to rediscover.

- **Launch the app only via `C:\git\launch_trading_app.ps1`.** It pins the
  operational checkout, sets `TRADING_ASSISTANT_DB`, and re-reads Alpaca
  credentials from the **user-scope registry** at every launch. A long-lived
  shell otherwise hands the app a revoked key — observed after the
  2026-08-05 rotation.
- **`C:\git\epoch_swap_tasks_elevated.ps1`** (machine-local, elevated)
  disables and re-enables the four `TradingAgent-Paper-*` tasks around a
  deploy. On this host a non-elevated `Stop-ScheduledTask` **succeeds**
  while `Disable-ScheduledTask` returns "Access is denied" — so a merely
  *stopped* long-runner is restarted by its own 5-minute heal trigger.
  Disabling is what actually holds them down.
- **The process singleton is live.** `data/locks/order-monitor.lock` and
  `data/locks/operations-watchdog.lock` being held is direct evidence that
  the deployed tree — not the previous one — is executing. `data/locks/` is
  gitignored.
- **Backups land in `data/backups/` — the SAME disk as the operator
  database.** GR-6's off-machine requirement is **not** met. A drive failure
  currently loses the running epoch. This is the smallest high-value slice
  of GR-6 and is worth doing before the rest of it.
- **This host keeps losing console-hosted processes** to `0xC000013A`
  (console-close). The scheduled tasks self-heal via their repeating
  trigger; **the Streamlit app does not**, because nothing supervises it.

---

## 3. Standing engineering watch items

- **`Decimal(str(...))` on money or share fields.** Three consecutive review
  passes each found another one (FPS-001 → GFPS-001 → CFPS-001). All known
  remaining raw sites sit inside their own `try/except` conversion helpers.
  If a fourth appears, the answer is a lint or AST guard banning bare
  `Decimal(str(...))` outside `assistant/money.py` — not another point fix.
  The trap is that `InvalidOperation` is an `ArithmeticError`, so it escapes
  `except ValueError`, and that Decimal NaN **raises** on ordering
  comparisons where float NaN merely returns False.
- **Skipping a row in a return series drops its cash flow.** Any code that
  filters valuation points must check `net_external_flow` before dropping
  one, or a deposit is silently read as investment return (CFPS-GR7C-001,
  reproduced at +100% on a doubled-by-deposit account).
- **Reporting surfaces must not write.** `_packet(store=...)` and
  `_load_packet` both record GR-4 provider-fetch evidence. Read-only pages
  and commands use store-free, cached loaders
  (`_load_readonly_portfolio`). This defect has now appeared on the Reports
  page twice (GR-7a, then GR7BREV-002).
- **Averaging across irregularly-sampled rows.** The operator captures
  equity an arbitrary number of times per day, so any flat mean over
  snapshots silently weights each day by how often the app was running. This
  produced a real 2.3-point error in GR-7c's average invested weight
  (5.71% reported vs 8.00% session-equalized) before it was caught. Any
  future metric that averages over `portfolio_equity_snapshots` must
  equalize by session first, and should use the same independent unit its
  own sufficiency check declares.
- **FPS-003**, the intermittent `test_app_title_is_trading_assistant`
  failure, remains open. Severity looks overstated at P2 — it has passed
  every full run since. **Do not close it on a green suite**; capture the
  full traceback the next time a full run fails, since the original was
  lost to a `tail` pipe.
