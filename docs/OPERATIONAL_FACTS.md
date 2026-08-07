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

### GR-7d rebalance target: equal-weight UNIVERSE, wide band (2026-08-06)

The decision that unblocked GR-7d. The action plan had recorded it as
blocked on an owner decision, not on code, because **a cap is not a
target**: the mandate defines risk-shape targets and the policy defines
caps, and neither is a target allocation. Deriving one in code would have
been inventing an investment policy.

Owner chose, after seeing the feasibility arithmetic:

- **Target set** — equal weight across all 104 `config.UNIVERSE` tickers,
  scaled to the policy's `max_total_exposure_pct` ceiling (0.48% each at
  the current 50% ceiling). Chosen because equal weight asserts the least:
  no security selection and no sector view, which is the honest default
  given seven-plus candidate signals tested and zero confirmed.
- **Band** — ±25% *relative* drift, boundary inclusive.
- **Both directions** — sells to trim overweight, not buy-only.
- **Report-only first** — drift measurement and a read-only CLI this
  milestone; proposal generation is a separate, separately reviewed
  milestone. The owner reads real numbers before any proposal code exists.

Three facts that decided the shape, all measured rather than assumed:

1. The union of all 16 `config.BASKETS` **is exactly `UNIVERSE`** (104
   names, 152 slots) — baskets are not a subset, so "use BASKETS" and "use
   UNIVERSE" are the same target.
2. 30 tickers sit in 2–4 baskets each. Weighting by basket membership would
   hand mega-cap tech 4× a utility's weight on curation density alone —
   an allocation claim with no evidence, so it was rejected.
3. `risk/execution_gate.py::_check_basket_concentration` caps **every**
   basket at `max_basket_pct`, and because baskets overlap, a target can
   breach a basket it was not aiming at (`semiconductors` is bound by
   *tech*, not by itself). Equal-weighting all 104 clears this easily
   (worst basket 12% against a 40% cap); single-basket targets do not.

**Known unresolved conflict, deliberately left visible.** Real holdings sit
outside the target set — NVDL and BBB, plus the SOXX/SOXL pair that
`CONFIGURED_LEVERAGED_PAIRS` exists to trade. A UNIVERSE-derived target
gives all of them an implied 0% target, i.e. "exit entirely", which puts
the rebalance target in direct conflict with a deliberately configured
strategy. The report surfaces these as `held_not_in_target` rows and
decides nothing. **This must be resolved before any proposal-generating
slice ships**, or the two components will propose opposite trades.

Also standing: the target is scaled to the exposure *ceiling*, so the
target portfolio sits at the cap with zero headroom — ordinary upward drift
then reads as a `max_total_exposure_pct` breach. The CLI says so on every
run. Lowering the target below the ceiling is an open owner option.

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

### There are TWO machines, and only one may run the cadence (2026-08-06)

The epoch host described above is **not** the only development machine.
Everything in this section is host-specific; re-measure rather than assume
which one you are on. `whoami` distinguishes them.

- **Epoch host** (`REDMOND\sheltonchen`) — runs `paper-epoch-002`. The four
  `TradingAgent-Paper-*` tasks are installed and ENABLED here. This is the
  only host that may run the operational cadence.
- **Second host** (`HARRY_MELODY\shelt`) — stood up 2026-08-06 as a
  development machine. It has its own `C:\git\trading_agent_operational`
  (pinned clone) and `C:\git\trading_agent_venv` (pinned-requirements venv,
  full suite green), and the same four scheduled tasks **installed but
  DISABLED**.

**Why they are disabled, and why it matters.** Both hosts read the same
`APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` from their own user registry, and
those credentials point at the **same Alpaca paper account** — the one
`paper-epoch-002` is accumulating evidence on. Two hosts running
`monitor-orders`/`operations-cycle`/`watchdog` against one account means
duplicate reconciliation and competing cancellation against live epoch
evidence. The second host was therefore deliberately left with **no ledger
bootstrap and no epoch**; `paper-evidence-status` there correctly reports
"Paper evidence epoch not found". Do not bootstrap or start an epoch on the
second host while `paper-epoch-002` is active on the first.

The non-elevated `Disable` gotcha above reproduced exactly on the second
host: `Stop-ScheduledTask` succeeded unelevated while `Disable-ScheduledTask`
returned "Access is denied", and `OperationsCycle` would have restarted on
its own 10-minute trigger. Disabling required an elevated shell, and
`powershell.exe` there also refuses unsigned local scripts by default —
`-ExecutionPolicy Bypass` on the invocation is needed, not a machine-wide
policy change.

This standup is real evidence toward **GR-6**'s "second-machine stand-up
proven once" marker (pinned checkout, dedicated interpreter, full suite,
installer preview and verifier round-tripped). It is not evidence toward any
epoch, and it did not start one.

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
- **FPS-003**, the intermittent `test_app_title_is_trading_assistant`
  failure, remains open. Severity looks overstated at P2 — it has passed
  every full run since. **Do not close it on a green suite**; capture the
  full traceback the next time a full run fails, since the original was
  lost to a `tail` pipe.
