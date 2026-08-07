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
  currently loses the running epoch.
  **This slice is BLOCKED on this host, not merely unbuilt (owner, 2026-08-07).**
  This is a corporate-managed computer and the owner is not permitted to
  upload from it, so every cloud destination is out — including the two
  sitting right there in the profile directory. Do not propose them:
  `C:\Users\<user>\OneDrive - Microsoft` is the **employer's tenant**, and a
  copy of the operator database carries broker account identifiers and the
  full position history, so replicating it there would be wrong even if
  uploading were permitted. Personal OneDrive is equally barred by the host
  rule. Google Drive is not installed, and installing it would not change the
  rule.
  What remains available, if the owner wants this later, is **physical**
  rather than cloud: an external USB drive or SD card is off-machine without
  an upload. A second internal volume would not help — `Get-PSDrive` shows
  only `C:` on this host, and a same-disk copy is what already exists.
  Until then the honest statement is that the running epoch survives file
  corruption and accidental deletion (the local backup and its restore drill
  do cover those) but **not** loss of the machine or its disk.
- **This host keeps losing console-hosted processes** to `0xC000013A`
  (console-close). The scheduled tasks self-heal via their repeating
  trigger; **the Streamlit app does not**, because nothing supervises it.

---

### QuantConnect: results may leave, data may not (2026-08-07)

QuantConnect's terms forbid exporting site content "in raw form, such as
CSV, API, FTP, or other formats", and download licences are "for the
licensed organization's internal LEAN use only and cannot be redistributed
or converted in any format".

So the tempting integration — pull their survivorship-free universe into
this project's `{ticker: DataFrame}` pipeline and run the existing
significance toolkit on it — is **not permitted**, however well it would
fit. `research/quantconnect.py` enforces this with an endpoint allowlist
rather than a comment: market-data paths are structurally unreachable, so a
new endpoint QuantConnect adds does not become callable merely because
nobody remembered to forbid it.

What may come home is an algorithm's **own results** — statistics, charts,
its own orders. That is enough for the thing the local backtest page
cannot do: `backtest/interactive` states it applies no multiple-comparison
correction because "every parameter tweak is another uncounted look". Runs
driven through the API are countable by construction.

Credentials: `QC_USER_ID` / `QC_API_TOKEN`, environment only, never
literals. The token is never transmitted — auth sends
`sha256(f"{token}:{unix_ts}")` with the timestamp as nonce.

Every authenticated call is an HTTP **POST** (including `authenticate`
with `{}`). A missing in-band `success: true` is failure. The allowlist
uses exact match for `authenticate` and slash-terminated prefixes
elsewhere, and rejects `..` / `\` / scheme-shaped paths so
`backtests/../data/read` cannot bypass the licence boundary.

### AI news summaries are often withheld for held names (2026-08-07)

`summarize_news_for_ticker` builds `allowed_tickers` as
`{query_ticker} ∪ (headline_tokens ∩ known)`, where `known` is
`config.UNIVERSE ∪ LEVERAGED_ETF_TICKERS ∪ BASKETS`. A summary that names
any other ticker (a peer company not present in both the headlines and
`known`) is refused as "mentions a ticker outside the verified candidate
set".

**Measured on the owner's real holdings: 7 of 8 tickers withheld**, while
AAPL and MSFT summaries passed repeatedly. The guard is behaving correctly
— news is third-party text and therefore an injection surface — but for
this portfolio the common outcome is refusal, so the feature looked broken
when refusals were silent.

Do not invent the membership story: several held names (for example AFRM,
AEP, SPCX) are already in `UNIVERSE`, and NVDL is already in
`LEVERAGED_ETF_TICKERS`. Withholding is driven by *peer mentions in the
summary*, not by "the holding itself is unknown to the project".

The *silence* was fixed 2026-08-07: every refusal path now returns a fixed
reason label and the UI prints it, so a withheld summary no longer looks
identical to a disabled feature. Invented figures must not travel inside
that reason (CNEWS-001). **The allowlist scope is an open owner decision**:
should held tickers and recognized ETFs widen what a summary may name, or
stay as-is? That widens a safety control and should be reviewed, not
quietly changed.

### CQC-001: the QuantConnect success check is unverified (2026-08-07)

`research/quantconnect.py` refuses any response whose body does not carry
`success: true`. That is fail-closed and correct in principle — QuantConnect
signals failure in-band with HTTP 200, so treating a missing field as
success would be fail-open.

**But no live call has ever been made from this project.** Whether every
endpoint sets `success` is an assumption, not a verified contract. If a real
call fails with `"failed (HTTP 200): no reason given"` on an otherwise
sensible body, **suspect that check before suspecting the credentials.**

Expect it on `read_backtest` / `list_backtests` rather than `authenticate`,
which QuantConnect documents as returning `success` — so a clean
`authenticate()` does **not** prove the assumption holds for the endpoints
that matter.

Dormant until someone deliberately points the client at QuantConnect: the
module has no UI wiring, nothing calls it automatically, and it is not in
the frozen operational checkout. It cannot affect the app or the running
epoch.

Do not loosen it speculatively. Confirm the real response shape, then relax
it for that specific endpoint with the observed body recorded.

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
- **`portfolio_equity_snapshots.total_equity` is post-flow.** The broker
  equity already includes deposits/withdrawals recorded in
  `net_external_flow`. `portfolio_performance_report` subtracts flow before
  computing the period return. Any caller that feeds snapshot equity into
  `Observation.value_before_flow` without subtracting flow credits deposits
  as return (GR7CFOLLOW-001: attribution reported ~+33% on a pure deposit
  series). Invested weight still uses post-flow equity.
- **FPS-003**, the intermittent `test_app_title_is_trading_assistant`
  failure, remains open. Severity looks overstated at P2 — it has passed
  every full run since. **Do not close it on a green suite**; capture the
  full traceback the next time a full run fails, since the original was
  lost to a `tail` pipe.
