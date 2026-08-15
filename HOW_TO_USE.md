# How to use this app

A practical guide for the owner: how to start it, what the four core
modules do, how to run a backtest, and what to do when something looks
wrong. `README.md` explains what the project *is* and why; this file
explains how to *drive* it.

Everything here is **paper trading**. Nothing in this app can place a real
order, and no button changes that (see §8).

---

## 1. Start the app

**The normal way — always use the launcher:**

```powershell
pwsh -NoProfile -File C:\git\launch_trading_app.ps1
```

Then open <http://localhost:8501>.

The launcher exists because three things must be true every time, and it
guarantees all three:

1. it runs the **operational checkout** (`C:\git\trading_agent_operational`),
   which is frozen at the evidence epoch's commit — not your development
   folder, which changes daily;
2. it points at the **one operator database**, so your books never split
   across two files; and
3. it re-reads your **Alpaca credentials from the Windows user
   environment at launch**, so rotating keys only requires restarting the
   app (a long-lived terminal otherwise hands the app the old, revoked
   key and Alpaca answers `unauthorized`).

### Running the development version to try new features

Use this when you want to see a feature that has been built but not yet
deployed. It runs your development folder, which changes daily, so it is for
*trying things* — never for real paper trading, because it is not the frozen
runtime the evidence epoch is pinned to.

```powershell
pwsh -NoProfile -File C:\git\customizedAgent\trading_agent\scripts\launch_dev_app.ps1
```

Then open <http://localhost:8501>. It will look like the real app, with its
own empty set of proposals and history, and it prints which database it
opened so you can confirm at a glance. Stop it with `Ctrl+C`.

The launcher protects two separate boundaries by default. It opens a scratch
database instead of the operator database, and it engages the environment
kill switch so unreleased code cannot submit an order. The **Alpaca paper
account is still the same one** the operational runtime uses, but an approval
attempt from this default development session is refused before submission.
Browsing, creating proposals, and previewing sizing are safe.

If the owner separately authorizes a deliberate paper-order test of
development code, launch with `-AllowPaperOrders`. That explicit switch only
removes the launcher's added halt; it does not clear an inherited or
persistent kill switch. Any submitted order reaches the shared paper account
and appears in the active epoch's broker record, so do not use this option for
ordinary feature previewing.

If you prefer to run it by hand, the launcher is doing exactly this:

```powershell
$env:TRADING_ASSISTANT_DB = "C:\git\customizedAgent\trading_agent\data\dev_scratch.db"
$env:TRADING_ASSISTANT_KILL_SWITCH = "1"
python -m streamlit run scripts\personal_assistant_ui.py
```

**Set both environment lines every time.** Omitting either creates a silent
safety gap. The operator database lives at
`data\trading_assistant.db` *inside the development folder*, and that is also
the default the app falls back to when the variable is unset — so launching
the development app without it opens the **live operator database**, the one
holding the active epoch's real paper-trading record. Simply opening it
applies whatever schema migrations the development code carries, which the
frozen runtime does not have. Nothing warns you, and the app looks correct
either way. Omitting the kill switch leaves an approved development proposal
able to reach the shared paper account.

Two habits that make this safe:

* the variable is set **per terminal**, so a fresh window has forgotten it —
  set it again rather than assuming;
* `dev_scratch.db` is disposable. If it gets confusing, close the app and
  delete the file; a new empty one is created on the next launch. Never
  delete or "clean up" `trading_assistant.db`.

The operational launcher is unaffected — it sets the operator path itself on
every run, so `launch_trading_app.ps1` always reaches the right database no
matter what your terminal has in it.

**Setting this up on another computer:** run
`pwsh -NoProfile -File scripts\setup_operational_host.ps1` once. It creates
the operational checkout, the dedicated Python environment, the launcher,
and the scheduled-task installer. Two things it cannot carry for you: your
Alpaca paper credentials (set them as Windows user environment variables)
and `assistant/my_policy.json` if you use a custom policy. **Only one
computer may run the scheduled tasks during an evidence epoch** — see §6.

### Which policy file loads

The policy file decides what the app is allowed to propose, so the app
picks one in a fixed order and always tells you which one won:

1. a path you type into the sidebar's **Policy file** box, or pass as
   `--policy` on the command line;
2. the `TRADING_ASSISTANT_POLICY` environment variable;
3. `assistant/my_policy.json`, if that file exists;
4. `assistant/default_policy.json` otherwise.

Levels 1 and 2 name a file explicitly, so if it is missing you get an
error rather than a different policy — quietly loading a *more permissive*
policy than the one you asked for is exactly the failure worth refusing.
The sidebar shows the active file name under the box; check it before
approving anything, because `my_policy.json` allows new positions and the
committed default does not.

A fresh clone has no `my_policy.json` and starts on the conservative
committed default. That is intended, not a setup error.

---

## 2. The four core modules

These are the four things the app does, in the order you use them. Each
exists as both a **page** in the UI and a **command** in the CLI, and both
call the exact same code — there is no separate "UI logic".

### Module 1 — Briefing: *what is true right now*

Portfolio totals, market regime, risk exposure, open orders, upcoming
earnings/dividends, and any warnings. Read-only. This is the "look before
you act" surface.

```bash
python scripts/run_personal_assistant.py briefing
```

A red **DATA DEGRADED** banner here means market data is stale; the
numbers shown are old, not wrong-but-fresh. Turn on *Fetch live earnings
events* in the sidebar to populate the events section — with it off, the
app honestly says "unavailable" rather than implying there are no events.

### Module 2 — Budgeted Buying: *put a budget to work*

Add tickers to a cart, check each one (trend, volatility, analyst targets,
news, a real historical best/worst hold-period range, and this project's
own evidence-labelled findings), then either propose them individually or
size a whole inverse-volatility split and submit it as one preflighted,
resumable batch.

Three ways to fill the cart: pick from common tickers, type any ticker, or
open **"Or pick from ticker suggestions"** and click a name from the
most-active screen. That third source runs only when you press its button —
never on page load — and shows the same rows as the Ticker Suggestions tab,
split by today's price direction. Read each row's detail before adding it:
that screen deliberately applies **none** of the project's usual size, age,
price, or liquidity floors, which is why a very new or very cheap listing
can appear there. The cart repeats which tickers arrived that way. Adding
one buys nothing — the split, the proposal, and the typed approval are all
still separate steps.

Deliberately absent: any probability-of-profit number. The app will not
invent one.

### Settings & Features — two switches that change what the app may do

Both live with the authoritative trading policy, not the UI preferences, and
both require the typed `UPDATE POLICY` confirmation. Changing either produces
a new policy fingerprint, which deliberately invalidates any pending proposal
created under the old one.

* **Whole shares only** — ON by default, and the default is enforced
  independently by the risk gate and the broker adapter, so a code path that
  forgets to ask still refuses. Turning it OFF permits fractional order
  quantities up to 9 decimal places on fractionable assets. Budgeted Buying,
  Discrete Buying, and Discrete Selling all follow the active setting; exact
  decimal text is preserved through proposal storage, approval, submission,
  and reconciliation.

  One consequence worth knowing before you turn it back ON. The setting
  applies to selling as well as buying, so any fraction you already hold —
  whether you bought it here, or it arrived from a dividend reinvestment or a
  corporate action — cannot be sold while it is ON. If you hold 10.5 shares,
  Discrete Selling offers 10 and tells you the remaining 0.5 is held but not
  sellable; if you hold less than one whole share, the page warns you the
  holding exists rather than hiding it. In both cases the way to close the
  position completely is to turn this setting off first. Nothing is stuck
  permanently, but the app will not quietly floor your holding and let you
  believe you sold all of it.
* **Enforce a minimum cash reserve** — unchecking writes a reserve of 0%.
  That removes the *buffer*, not the solvency check: an order that would take
  your cash balance negative is still refused. There is deliberately no
  separate on/off field, because 0 already means "no reserve".

### Module 3 — Policy Based Selling: *reduce risk*

"Check for recommended sells" surfaces **policy breaches** — concentration
over the cap, leveraged-ETF exposure, and so on. A recommendation here
means a rule was broken, never a price prediction. If nothing is flagged,
that is the correct answer, not a failure.

The preview shows the tax-lot consequences of a candidate sale, so you can
see the realized-gain cost before approving.

### Modules 2b / 3b — Discrete Buying and Discrete Selling: *your own calls*

The two pages above are driven by a budget and by policy. These two are
driven by you: pick one ticker and buy or sell it because you decided to.
Discrete Buying carries the same most-active suggestion picker as Budgeted
Buying, so you can pull a candidate straight from the screen.

Both size a trade **two ways**:

* **Share count** — an exact quantity. With **Whole shares only** ON, enter a
  whole number; with it OFF, you may enter up to 9 decimal places.
* **Dollar amount** — a *budget*, not a broker-notional order. With whole-share
  mode ON, $250 at $100 buys 2 shares and leaves $50. With it OFF, the app
  calculates a fractional quantity rounded down to 9 decimal places and shows
  any tiny remainder. The exact quantity, rather than the budget itself, is
  what enters the proposal and approval path.

On the sell side a dollar amount larger than your holding is **refused, not
capped** — silently shrinking the number you typed would be the app editing
your own instruction. Neither page sells short, and neither submits
anything: each creates one ordinary proposal that still needs the typed
approval phrase and a fresh execution-gate pass.

### Module 4 — Propose & Approve: *the gate every order passes through*

No order reaches the broker without passing here. A proposal is validated
against ~20 named risk checks (kill switch, cash reserve, position and
exposure caps, price freshness, duplicate orders, earnings blackout,
trading session…), and you must type the exact phrase **`approve`** before
the submit button unlocks. An override-eligible refusal requires a second,
different typed phrase naming that specific order.

```bash
python scripts/run_personal_assistant.py propose
python scripts/run_personal_assistant.py approve <proposal-id>
python scripts/run_personal_assistant.py list
```

**History** (a fifth page worth knowing) shows every proposal and order,
filterable by outcome, with a Reconcile button for anything whose broker
outcome is unresolved, and a "Manage unused proposals" tool that
*archives* clutter without ever deleting the audit record.

---

## 3. Backtesting

### In the app — the Backtest page

Pick one of six price-based signal scanners, tune its parameters, choose
your data source, universe scope, and hold horizons, then click **Run
backtest**. You get a multi-horizon summary table and a cumulative
net-return chart.

Two labels do real work here:

- **Synthetic data (the default)** is a *plumbing check*. A ~50% win rate
  is the correct, expected result and says nothing about market edge.
- **Real data** results are labelled **exploratory**: no multiplicity
  correction is applied, every parameter tweak is another uncounted look,
  and yfinance history is not point-in-time.

### On the command line — the confirmatory pipeline

The honest statistical work deliberately lives *only* here, so it cannot
be casually re-run until it looks good:

```bash
python scripts/run_backtest.py                 # one hold period
python scripts/run_backtest_horizons.py        # several exit timings
python scripts/run_baseline_comparison.py      # vs. the stock's own typical day
python scripts/run_out_of_sample_check.py      # discovery vs. confirmation split
python scripts/run_significance_check.py       # bootstrap + multiple-comparison
python scripts/run_basket_report.py            # per-sector grouping
```

Scripts default to synthetic data; switching to real data means editing
the marked `generate_synthetic` → `fetch_historical` line, and a real run
takes minutes for the full universe.

**How to read any result** (these are standing project conclusions, not
boilerplate): fewer than ~30 signals is indistinguishable from luck; a raw
win rate means nothing without the baseline comparison; testing many
baskets guarantees a few look good by chance; and only a *confirmation*
period result counts. Eleven signals have been through this gauntlet;
**zero** survived.

---

## 4. The command line

```bash
python scripts/run_personal_assistant.py --help
python scripts/run_personal_assistant.py <command> --help
```

Global flags: `--database` (defaults to `TRADING_ASSISTANT_DB`, else
`data/trading_assistant.db`), `--policy`, `--mandate`.

The commands you are most likely to want:

| Command | What it does |
|---|---|
| `briefing` | Module 1, as text |
| `propose` / `approve` / `list` | Modules 3–4 |
| `readiness` / `platform-readiness` | Is the platform fit to trade? (read-only) |
| `tax-report --year 2026` | Realized gains for a tax year (see §5) |
| `ledger-reconcile` | Compare your books against the broker |
| `sync-orders` / `reconcile` / `recover-stale` | Fix an unresolved order |
| `alerts` / `ack-alert` / `deliver-alerts` | Operational alerts |
| `kill-switch on` | Emergency stop — blocks every order |
| `backup-db` | Consistent database backup |
| `paper-evidence-status <epoch>` | Progress toward the 60-session goal |

Ledger maintenance (`ledger-dividend`, `ledger-split`, `ledger-fee`,
`ledger-transfer`) records real-world cash and share events so your books
keep matching the broker — see §7.

---

## 5. Reports

The **Reports** page produces the annual realized-gain report: short- and
long-term totals, per-lot rows with acquisition and sale dates, advisory
wash-sale flags, and CSV/JSON download.

```bash
python scripts/run_personal_assistant.py tax-report --year 2026 \
    --format csv --output data/reports/realized-2026.csv
```

Read the **coverage line at the top of the file** before using it:

- **COMPLETE** — the app's lot records match your broker's share counts.
- **INCOMPLETE** — they do not, so realized history is missing fills. The
  file is still produced, clearly labelled; do not hand it to an
  accountant as-is.
- **UNVERIFIED** — coverage could not be checked (no live broker
  configured, broker outage, sample/manual portfolio, missing account ID,
  or a snapshot from a different Alpaca account than your books are bound
  to).

Wash-sale entries are **flags, never adjustments** — the real rule spans
every account you control, which this app cannot see. This is a
reconciliation aid, not tax advice, and not a 1099-B substitute.

---

## 6. What runs in the background

Four Windows scheduled tasks run out of the frozen checkout. Two of them
appear as console windows. Minimizing them is still the tidy habit, but
closing one is no longer an outage: both re-check every 5 minutes and
restart themselves if they are not running.

| Task | Cadence | Job |
|---|---|---|
| **OperationsCycle** | every 10 min | reconciles orders, syncs fills, compares your books to the broker, refreshes the backup, runs health checks |
| **OrderMonitor** | continuous | listens to Alpaca's trade stream (polls as fallback) so fills are recorded within seconds |
| **Watchdog** | every 60 s | health heartbeat; raises alerts as Windows notifications |
| **PaperObservation** | daily, after the close | records the immutable session snapshot — **this is what makes a day count** |

**The one recurring obligation:** if you shut the machine down before the
observation fires, that day does not count toward the 60 — so either leave it
running past that time, or ask Claude to capture the observation after the
close (it takes seconds). Running on battery is fine; the tasks used to skip
on battery power and no longer do.

**Check the actual fire time rather than computing it — they can differ:**

```powershell
(Get-ScheduledTask -TaskName 'TradingAgent-Paper-PaperObservation').Triggers.StartBoundary
```

On the current epoch host that prints `2026-08-05T16:30:00-07:00`: **16:30
local**. The installer's rule since 2026-08-08 is different — 16:30 *Eastern*
converted to local, which on a Pacific host would be 13:30 local — but this
host's task was installed on 2026-08-05, before that logic existed, and a
normal epoch roll re-enables the existing tasks rather than reinstalling
them, so the older trigger persists. Both times are safely after the 16:00 ET
close; the hazard is only in guessing. Computing 13:30 from the rule and
shutting down at 14:00 would silently cost you the session (found 2026-08-13
by reading the installed trigger instead of the installer source).

If the installer is ever re-run on this host, expect the observation to move
to 13:30 local — verify with the command above afterward.

The evidence epoch itself is a database record: it survives reboots and
never needs re-activating. The frozen checkout must not be updated until
the epoch is closed.

### Is the epoch still collecting evidence?

```powershell
python scripts\check_epoch_cadence.py
```

Run this whenever you think of it, especially during a long epoch. It reads
the operator database **read-only** — it is safe to run from the development
folder while an epoch is open, and it cannot write, submit, or change
anything.

It exists because the evidence summary is blind to a trailing stall. A
nightly capture that cannot reconcile correctly exits nonzero and creates a
critical alert; this tool does not replace those controls. It answers the
separate direct question: has the active epoch actually kept accumulating?
Epoch-002 sat at one observation until the incident was traced by hand. The
existing gap check could not see it because it only looks *between* the first
and last observation already present — a run that stops has nothing after it
to compare against.

The default trigger is the **measured current epoch-host schedule: 16:30
Pacific**, with a two-hour late-run grace. A task's trigger is a fixed local
clock, not "market close plus a duration"; that distinction prevents a false
missing session after a 13:00 Eastern early close. If the task is reinstalled
or moved, first read its real `StartBoundary` as described above, then supply
the host-local clock and IANA timezone explicitly, for example:

```powershell
python scripts\check_epoch_cadence.py --capture-time 17:00 --capture-timezone America/New_York
```

One constraint on that pair: the capture command files an observation under
the **Eastern** date of the moment it runs, while this tool models a session
as captured on its own date at the trigger clock. They agree for any trigger
whose local date matches its Eastern date — 16:30 Pacific is 19:30 Eastern
the same evening — but a trigger late enough to roll past Eastern midnight
would make this tool expect a session the capture files under the next one.
Keep the trigger in a US market timezone and the two stay aligned.

The five answers:

| Result | Meaning |
|---|---|
| `NOT DUE YET` | Nothing is owed yet. Zero observations is correct, not a fault. |
| `HEALTHY` | Every session owed so far was captured. |
| `BEHIND` | Something is missing, but it may be one late run. Re-check after the next session. |
| `STALLED` | Nothing has been captured for two or more owed sessions. The epoch is open but no longer accumulating. |
| `NO ACTIVE EPOCH` | Nothing is being collected at all. This is distinct from a stall and returns failure so a scheduled check cannot silently accept a missing promised epoch. |

If it says `STALLED`, the two usual causes are the scheduled task not
running (check it with the command above) and ledger reconciliation
refusing to capture — which is the machinery working correctly and pointing
at real books that need explaining, not something to override.

---

## 7. When something looks wrong

| Symptom | What it means | What to do |
|---|---|---|
| `APIError: unauthorized` | The app is holding credentials from before a key rotation | Restart the app via the launcher |
| "Duplicate order detected" but you have no open order | A previous order actually filled; the local record was stale | Ask Claude to sync/reconcile, or wait for OrderMonitor |
| Watchdog prints `"healthy": false` | One or more health checks are failing | Read the failing check names; most are one-time setup gaps |
| Ledger reconciliation mismatch after a dividend or split | Real cash/shares arrived that your books do not explain | Record it with `ledger-dividend` / `ledger-split` — never edit tables by hand |
| `platform-readiness` exits non-zero | Expected for months: evidence needs 60 sessions and strategy readiness needs a confirmed finding | Not a fault; do not "fix" it |
| A refusal you did not expect | The gate found a real rule breach | Read the message — it names the exact rule |
| A buy is refused as policy-ineligible | The conservative default policy is loaded, which forbids new positions | Check the file name under the sidebar's Policy file box (see §1) |
| A console task window vanished | It was closed or Ctrl+C'd | Nothing to do — it restarts itself within 5 minutes |

A refusal is the system working. The dangerous outcome is a trade that
goes through when it should not have.

---

## 8. What this app will never do

- **Place, size, approve, or cancel an order on its own.** Every order
  requires your exact typed phrase, then a fresh re-validation.
- **Trade real money.** `PAPER_TRADING` is on, and switching it off
  requires deliberately editing `config.py` outside the app.
- **Let AI touch a trade.** LLM and ML output is advisory or
  observational only; it cannot create, approve, size, or submit
  anything, and it cannot weaken any safety control.
- **Invent a number.** A missing price, a stale bar, or an unavailable
  earnings date produces a refusal or a visible degradation — never a
  filled-in guess.
- **Claim edge it has not measured.** Backtest output is labelled
  exploratory unless it has passed the frozen confirmation pipeline, and
  nothing so far has.
