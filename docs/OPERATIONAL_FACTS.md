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

### Differences are evidence; absolute balances are not (2026-08-10)

Established after DCCR-003 was raised against one document while the same
value sat in two others. The rule, so later rounds apply it consistently
instead of re-litigating it:

- A **difference** may be load-bearing and stays. AP-6's diagnosis is only
  checkable because the record says the ledger was **$0.03** above the
  broker; deleting that would gut the evidence.
- An **absolute balance** (cash, total equity, buying power) proves nothing
  that `matched: true` plus a mismatch count does not already prove, so it
  never belongs in a committed document. This repository is public.
- Counts, dates, session totals, lineage hashes, and mismatch counts are
  not balances and are fine.

Enforced by `test_current_documents_do_not_publish_exact_account_balances`
across every current-state document, not just the one where an instance was
last found.

### Benchmark is SPY (2026-08-06)

`paper_evidence` binds `benchmark_ticker` into every observation, defaulting
to SPY. GR-7c attribution uses the same ticker deliberately: a second index
would put two benchmarks in one epoch and leave a later reader unable to say
which was authoritative. QQQ remains available as an optional *diagnostic*
for separating a tech style bet from selection — never as the record.

---

## 2. Machine-local operational facts

Not derivable from the repository, and expensive to rediscover.

### `paper-epoch-003` is active; the AP-6 swap was executed (2026-08-10)

The AP-6 stall (three uningested post-bootstrap CAT fees, $0.03 cash
mismatch, every capture since 2026-08-07 refused) was repaired by the
owner-authorized epoch swap on 2026-08-10, executed in the required order:
tasks disabled (elevated script, UAC-approved) → `paper-epoch-002` closed at
19:25:50Z on its frozen `9a91498` runtime (single-observation record
retained) → operational checkout fast-forwarded to merged `ef05dc1`
(PR #182) → `ledger-reconcile` **matched on its first run** (the three fees
posted exactly once at their true `created_at` times; ledger cash equal to
broker cash, zero mismatches) → readiness green → `paper-epoch-003` started at
19:27:21Z with identical mandate/policy/strategy/model lineage → **all five
required drills passed and recorded under epoch-003** → tasks re-enabled and
verified by a manual green operations-cycle (3 fee duplicates on idempotent
replay, healthy, exit 0). All seven stale alerts were acknowledged after
their causes were verified resolved; there were **0 open alerts at swap
completion**.

Independent read-only review on the epoch host confirmed epoch-003's start
row and all five drill rows bind exact commit `ef05dc1`. It also confirmed
**0 epoch-003 observations** at review time. Therefore the application
summary's `lineage_consistent: true` is not observation evidence yet (the
empty observation set satisfies that check vacuously). The first successful
scheduled post-close observation is still required to prove the deployed
cadence and observation lineage and to start the 60-session / 30-order clock.
The PaperObservation task was enabled and Ready, with its next scheduled run
at 16:30 Pacific on 2026-08-10; its previous recorded result belonged to the
pre-swap stalled epoch.

The elevated swap helper left two machine-local evidence files in the
development checkout: `data/swap_disable_result_20260810.json` (695 bytes,
SHA-256 `91E06EA25D18882C36CBF0E1FBA338E1D926AC63392FB4CA18C3E38FB5E24321`)
and `data/swap_enable_result_20260810.json` (679 bytes, SHA-256
`E8E6B09631C781ED11A8B5419FD8D20D66DCABD1808583CA114181712E32B5BE`).
They contain only per-task state/results, no account or credential fields.
They are preserved locally and covered by the narrow
`data/swap_*_result_*.json` ignore rule; do not commit their contents.

Update 2026-08-10 (development only, NOT deployed): Claude's CR-W2 handler at
`25a2e7b` was independently accepted after correction on
`codex/review-broker-dividend-handler-20260810`. The reviewed scope is USD
plain/explicit-CDIV cash dividends plus explicit CSD deposits and CSW
withdrawals. Generic JNLC cash journals remain fail-closed because the type
does not prove contributed-capital treatment. Stock/substitute dividend
subtypes, interest, withholding, return-of-capital, capital-gain
distributions, and other unknowns also remain fail-closed. Until the branch is
merged and deployed through an owner-triggered epoch-004 roll, deployed
`ef05dc1` still refuses even the newly supported types. Official AEP schedule:
record/ex-date 2026-08-10, payable **2026-09-10**, $0.95 per eligible share.

Read-only re-measurement at 15:21 Pacific found epoch-003 still active at
`ef05dc1`, 0 observations, 5/5 drills, and a current healthy operations
heartbeat with the latest reconciliation matched at zero mismatches.

### The open critical `portfolio_accounting` alert is a negative-age race (AP-7)

Measured read-only 2026-08-10 16:40 Pacific. The earlier description of this
alert as a merely "retained/reopened record" was **wrong** — it was actively
re-raised at 21:52:22Z by a real check failure with a false cause:

```
message      portfolio_ledger_reconciliation: at=2026-08-10T21:52:22.602589+00:00,
             matched=True, mismatches=0
details      "ok": false, "severity": "critical"
last_seen_at 2026-08-10T21:52:21.515505+00:00      <-- 1.087s BEFORE the reconciliation
occurrences  1885   first_seen 2026-08-05T17:51:42Z
```

`assistant/operations.py` requires **freshness AND matched**:
`timedelta(0) <= now - reconciliation_at <= limit and matched`. The lower
bound is deliberate (FCS-017, so a future-dated row cannot read as fresh),
but the check's `now` is captured at entry while a **concurrent** process
writes the reconciliation a moment later — OperationsCycle runs every 10
minutes and Watchdog/OrderMonitor every 5, so the overlap recurs. The age
goes negative, the conjunct fails, and the alert prints
`matched=True, mismatches=0`, which reads as self-contradictory because the
detail string never names which conjunct failed.

The books are fine: five consecutive matched, zero-mismatch reconciliations
through 23:32Z, and the epoch-003 observation carries
`ledger_mismatch_count: 0`. The failure direction is conservative (a false
alarm, not a missed one), but an open critical alert **feeds the
`promotion-status` gate** (`critical_alerts` counts open criticals) and
makes `operations-cycle` exit nonzero. `paper-observation` does not run this
check, which is why evidence capture was unaffected. Do not acknowledge it
as "resolved" without fixing the cause — it will re-raise on the next
overlap.

Post-merge independent correction `89ebcc2` fixes AP-7 in the development
tree without weakening FCS-017: reconciliation, backup, and restore-drill
freshness now use a clock captured immediately after the corresponding state
read, while an explicit as-of clock stays frozen and still rejects genuine
future timestamps. Details now include signed `age_seconds`. This correction
is **not deployed**; epoch-003 continues on `ef05dc1`, and the existing open
alert was not acknowledged or mutated. Read-only remeasurement at 16:56
Pacific found the latest operations heartbeat healthy and the recent
reconciliations matched with zero mismatches.

**Second instance, found by counter-review and fixed the same day.** The
correction covered the three checks in `assistant/operations.py` but not the
structurally identical one in `assistant/readiness.py`
(`reconciliation_freshness`), which is reached from the *same*
`operational_health()` call. That site is the more exposed of the two: the
deployed `monitor-orders` task rewrites `last_order_reconciliation` every 30
seconds, and the window between `transaction_readiness`'s entry clock and
that read contains a full SQLite `integrity_check` plus several proposal
queries. Because `operational_health` computes `healthy = all(check["ok"])`,
a *warning*-severity readiness check still drove the scheduled cycle to a
nonzero exit. Fixed with the same post-read-clock pattern and the same
frozen as-of behaviour.

**Do not "unify" this with the execution gate.** `risk/execution_gate.py`
deliberately tolerates a small negative quote age
(`_FUTURE_TIMESTAMP_TOLERANCE_MINUTES`) because that timestamp comes from an
**external** source where clock skew is real. The operations/readiness rows
are written **locally**, so capturing the clock after the read removes the
negative age entirely and no tolerance is needed. Adding a tolerance to the
local checks would weaken FCS-017 for no benefit. Two deliberate strategies,
matched to where the timestamp comes from.

Also examined and **not** implicated: `readiness.py`'s stranded-claim age
(a concurrent write makes a claim look *younger*, so it is not falsely
flagged stale), `ml/evidence_operations.py` (a pure function evaluating a
caller-supplied snapshot), and `order_reconciler.py`'s order-age checks
(caller-supplied clock, fail-safe direction).

Counter-review (Claude, same day) accepted all six review findings and
corrected two residual defects in the correction itself: economic dates are
now stamped at **market-local** midnight rather than UTC midnight (UTC
midnight is the previous evening in New York, which misattributed winter
cash flows to the previous session's return interval and a New-Year event
to the prior tax year), and a prefix-map `KeyError` that escaped the
fail-closed refusal handler is gone. Details in the review report §7.

**Update 2026-08-11 (development only, NOT deployed): CR-W3 stops being an
epoch-killer.** The operator acknowledgement path on
`user/claude/broker-activity-acknowledgement-20260811` means a refused
activity no longer requires a code deploy — and therefore no longer costs
the accumulated run. When a nightly capture fails on an unsupported
activity, the recovery is:

1. `ledger-activity-review` — see exactly what refused and why (read-only).
2. `ledger-activity-acknowledge <id> --treatment <fee|dividend|cash_transfer|no_cash_effect> --operator <you> --rationale "<why>"` (plus `--ticker` for a dividend).
3. The next `paper-observation` journals it and capture resumes.

You choose the treatment; the amount always comes from the broker row, so
this cannot invent money. `no_cash_effect` only works on rows the broker
itself reports as zero. The decision is bound to a fingerprint of the exact
activity content, so if the provider later changes that row it refuses again
rather than reusing your judgement. **This is undeployed until the epoch-004
roll** — on deployed `ef05dc1` a refused activity still stalls the epoch.

**CR-W3 (watch item):** the DIV subtype allowlist accepts only an
absent subtype or explicit `CDIV`, and no `DIV` activity has ever appeared
on this account, so the subtype the real AEP payment carries is unverified.
If it differs, that night's observation fails closed and names the subtype
in the refusal message; the fix is a small reviewed allowlist addition.
Expect this as a possibility around 2026-09-10.

Standing watch until epoch-004 deployment: the AEP cash dividend and every
post-bootstrap JNLC/CSD/CSW activity still fail closed on deployed `ef05dc1`.
After deployment, plain cash dividends and explicit CSD/CSW movements are
handled; JNLC continues to require operator review and a more specific
accounting fact. The operations-cycle still completes backup/health work
before returning an activity failure. Never use a manual compensating entry
(the sync re-reads the broker row) and never widen reconciliation tolerance.

### There are TWO machines, and only one may run the cadence (2026-08-06; re-verified 2026-08-09)

Recorded 2026-08-06 on the branch
`user/claude/gr-7d-rebalance-targets-20260806` and never merged, so `main`
carried no trace of it — the second-host session then spent effort
re-deriving why its own `trading_agent_operational` clone looked "stale"
and its launch script was "missing". Ported here 2026-08-09 with every
machine-local claim re-verified on the second host rather than copied.

Everything in this section is host-specific; re-measure rather than assume
which one you are on. `whoami` distinguishes them.

- **Epoch host** (`REDMOND\sheltonchen`) — runs the active
  `paper-epoch-003` (at `ef05dc1` since 2026-08-10). The four
  `TradingAgent-Paper-*` tasks are installed and ENABLED here. This is the
  only host that may run the operational cadence. The bullets below this
  section (launch script, epoch-swap script, lock files, backups) describe
  THIS host.
- **Second host** (`HARRY_MELODY\shelt`) — stood up 2026-08-06 as a
  development machine. It has its own `C:\git\trading_agent_operational`
  (pinned clone — at the epoch-era merge base, NOT tracking `main`; that
  lag is by design, not drift) and `C:\git\trading_agent_venv`
  (pinned-requirements venv, full suite green at standup), and the same
  four scheduled tasks **installed but DISABLED** (re-verified 2026-08-09:
  all four report `Disabled`). `C:\git\launch_trading_app.ps1` exists only
  on the epoch host; its absence on the second host is expected.

**Why they are disabled, and why it matters.** Both hosts read the same
`APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` from their own user registry, and
those credentials point at the **same Alpaca paper account** — the one bound
to the active `paper-epoch-003`. Two hosts running
`monitor-orders`/`operations-cycle`/`watchdog` against one account means
duplicate reconciliation and competing cancellation against live epoch
evidence. The second host was therefore deliberately left with **no ledger
bootstrap and no epoch**; `paper-evidence-status` there correctly reports
"Paper evidence epoch not found". Do not bootstrap or start an epoch on the
second host while any epoch-host evidence epoch is active (currently
`paper-epoch-003`).

The non-elevated `Disable` gotcha (below, epoch host) reproduced exactly on
the second host: `Stop-ScheduledTask` succeeded unelevated while
`Disable-ScheduledTask` returned "Access is denied", and `OperationsCycle`
would have restarted on its own trigger. Disabling required an elevated
shell, and `powershell.exe` there also refuses unsigned local scripts by
default — `-ExecutionPolicy Bypass` on the invocation is needed, not a
machine-wide policy change.

The 2026-08-06 standup is real evidence toward **GR-6**'s "second-machine
stand-up proven once" marker (pinned checkout, dedicated interpreter, full
suite, installer preview and verifier round-tripped). It is not evidence
toward any epoch, and it did not start one.

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
module is present in deployed `ef05dc1`, but has no UI wiring and nothing
calls it automatically. Without a deliberate caller and configured
credentials it cannot affect the app or the running epoch.

Do not loosen it speculatively. Confirm the real response shape, then relax
it for that specific endpoint with the observed body recorded.

## 3. Standing engineering watch items

- **`Decimal(str(...))` on money or share fields.** Three consecutive review
  passes each found another one (FPS-001 → GFPS-001 → CFPS-001). **A fourth
  appeared 2026-08-07 (FCS-005): `execution/alpaca_broker.py:273-274`, bare,
  outside any conversion helper — so the earlier claim that every remaining
  `alpaca_broker` site is wrapped was describing line 100, a different
  function.** The trigger condition below has therefore been met: build the
  guard, do not point-fix a fifth.
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
- **A guard added to one generator is not added to its sibling.** 2026-08-07
  (FCS-001): `assistant/proposals.py` has guarded
  `int(<dollars> / position.current_price)` against zero/NaN since 2026-07-29,
  with a comment naming the crash. `assistant/strategy_proposals.py` — written
  later, same idiom, four sites — never got it. An AST sweep for
  `int(<expr>/<expr>)` finds exactly six sites repo-wide, so re-checking is
  cheap: run the sweep, then read each hit **beside its sibling**, because the
  scan alone cannot tell a guarded site from an unguarded one.
- **A narrow `except` clause in the UI can suppress risk reduction.** Same
  finding; **fixed 2026-08-07**, the rule is what outlives it.
  `scripts/personal_assistant_ui.py` caught only
  `MissingResearchDependencyError` / `StrategyMarketDataError` around the
  strategy generator, while the CLI caught `Exception`. Anything else escaped
  and the already-computed risk-reduction proposals were never rendered or
  saved. Whenever an optional feature shares a handler with risk-reduction
  proposals, the optional feature's failure must not take the mandatory one
  down with it — and the handler must catch `Exception`, because the failure
  mode is by definition the exception nobody predicted (here a
  `ZeroDivisionError` from a module whose declared error types are all about
  market data). Pinned by an AST test over both entry points.
  Related severity lesson: the first write-up of this finding claimed a NaN
  price was reachable. It is not — `context_builder.build_portfolio_snapshot`
  rejects non-finite prices and the Alpaca builder delegates to it. The
  reproduction had constructed a `PortfolioPosition` directly, bypassing the
  boundary. **A repro that hand-builds a domain object may be skipping the
  validation the real path performs; check which constructor production
  actually uses before assigning severity.**
- **Counting rows a metric did not score.** FPS-004 fixed this in
  `ml/earnings_experiments.py::_slice_metrics` and added
  `ml/evaluation.py::usable_pair_count()` for it. 2026-08-07 (FCS-002) found
  the same class *twice more in the same module*: `calibration_error` divides
  a numerator over finite pairs by `len(actual)` (raw), and
  `candidate_evaluated_event_count` is a raw `len()` beside five
  pair-dropping metrics. Measured: holding four good predictions fixed and
  adding NaN predictions, the reported calibration error falls
  0.1500 → 0.0600 → 0.0300 → 0.0150. `ml/volatility_evaluation.py:405-406` is
  the correct house pattern — publish `row_count` **and** `usable_row_count`,
  and compute on `[usable]`.
- **Freshness checks without a lower bound read a future timestamp as fresh.**
  2026-08-07 (FCS-017). `now - at <= limit` is True for any `at` in the future,
  so clock skew, a timezone misconfiguration, or a hand-inserted row makes a
  stale control look current. This codebase writes the check **both ways**:
  `operations.py:304`, `alert_delivery.py:412` and
  `evidence_operations.py:125,358,375` guard with `timedelta(0) <= …`, while
  `operations.py:117,156,184` and `readiness.py:191` do not — including two
  checks (`backup age`, `restore-drill age`) that `evidence_operations`
  evaluates fail-closed over the *same facts*, so the platform can report the
  backup fresh and stale at once depending which report you read. Always write
  `timedelta(0) <= now - at <= limit`.
- **"Not submitted" is a claim about the broker, and most callers cannot make
  it.** 2026-08-07 (FCS-018, the only P1 of that sweep). A raising submit does
  not prove rejection -- the response can be lost after the broker accepted --
  so the kernel leaves the proposal in `submission_unknown`, keeps the
  reservation, and raises a message beginning *"Could not confirm whether the
  order ... was accepted"*. The Streamlit approval handler prefixed that with
  `Order not submitted:`, producing a sentence that contradicted itself and
  pointed the operator at the obvious wrong move: place the trade by hand at
  the broker, outside every guard this codebase has. Both submit buttons had
  drifted the same way; the CLI had not, because it lets the exception
  propagate untouched.
  The rule: **decide submitted-vs-unknown from the DURABLE proposal status,
  never from exception text**, and fail toward UNKNOWN when the row cannot be
  re-read. `UNRESOLVED_BROKER_STATE_STATUSES` is the predicate. Pinned by an
  AST test over every broad handler around
  `execute_approved_paper_proposal`.
- **A leap day can sit on either side of a holding period.** 2026-08-07/08
  (FCS-016 → CXL-001 → CCX-001; three passes, three answers). Anchor the
  boundary on the day counting STARTS -- `acquired + 1 day` -- and take its
  first anniversary. Anchoring on the acquisition date needs two special cases
  and gets one of them wrong whichever way you write it: acquisition ON 29 Feb
  came out a day late, and 29 Feb INSIDE the window came out a day early. Test
  every leap position, not the one that was reported, and derive the expected
  value from Pub 550's own worked example (buy 5 Feb 2020 → long-term 6 Feb
  2021) rather than from the implementation.
- **A consistency test must assert relationships, not current values.**
  2026-08-08 (CCX-002). A doc guard that pinned the CURRENT epoch by name
  would have failed the suite on the next legitimate epoch roll, and the
  obvious fix would have been to edit the assertion -- so it would enforce
  today's state and be weakened every time reality moved. Assert instead that
  no document calls one epoch both active and closed, and that current
  documents do not disagree about which epoch is active. Literal strings are
  safe only for known-stale phrases that should never be true again.
- **A boundary test whose inputs cannot fail the bug.** 2026-08-07 (FCS-016):
  `tax_lots.is_long_term` compares timestamps where the rule is date-based, so
  a sale on the one-year anniversary at a later time of day than the purchase
  is wrongly long-term. Both existing boundary tests
  (`tests/test_tax_lots.py:189-199`) use **15:00 for the buy and 15:00 for the
  sell** — the single alignment where the buggy comparison agrees with the
  correct one. Three review rounds read a green test named
  `test_one_year_exactly_is_still_short_term` and moved on. When a test names
  a boundary, check that its inputs actually straddle it in every dimension
  the implementation reads (here: time-of-day, not just date).
- **A stylesheet guard that greps the stylesheet cannot fail when the
  framework moves.** 2026-08-09 (AUI-001/002/003, then AUICR-001/003). Three
  theme corrections shipped with green tests and did nothing in the browser:
  two styled nodes that never receive the rendered mark, and one styled
  `stVerticalBlockBorderWrapper`, a test id Streamlit 1.60 does not emit. The
  declared backstop was "caught by the next review pass"; it missed twice.
  Two rules follow. **First, a rendered measurement is the only evidence that
  a selector works** — reproduce the defect by restoring the old CSS in the
  live page and re-measuring the same node, because a screenshot of the fixed
  state cannot tell you the fix is what changed it. **Second, pin the painted
  VALUE, not the selector shape.** Reverse mutation found the checkbox tick,
  radio dot, and ink focus ring could each revert to white with the whole
  suite green: the shape was asserted, the colour was not, and the only
  colour assertions sat in a legacy `data-baseweb` block that the pinned
  Streamlit never matches (1.60 emits no `data-baseweb` attribute at all).
  `tests/test_ui_theme.py::test_every_theme_test_id_is_emitted_by_the_installed_streamlit`
  now compares the stylesheet against the installed distribution so a version
  bump fails on its own commit; keep its `LEGACY_ONLY_TEST_IDS` allowlist
  shrinking, since an undeclared dead selector is the original defect.
  Related: run the app for review on an isolated port with a scratch
  `TRADING_ASSISTANT_DB` and cleared credentials — never the operational
  launcher — and do not toggle a policy control to test its styling, because
  that writes `my_policy.json`.
- **FPS-003**, the intermittent `test_app_title_is_trading_assistant`
  failure, remains open. Severity looks overstated at P2 — it has passed
  every full run since. **Do not close it on a green suite**; capture the
  full traceback the next time a full run fails, since the original was
  lost to a `tail` pipe.
