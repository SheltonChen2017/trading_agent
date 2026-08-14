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

**Development preview** (a throwaway view of unreleased code — never for
real paper trading, because it is not the frozen runtime):

```powershell
python -m streamlit run scripts\personal_assistant_ui.py
```

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

### Module 2 — Buying: *put money to work*

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
  quantities. Note the current scope: this milestone delivers the switch and
  its authority; the order path is not yet fractional end to end.
* **Enforce a minimum cash reserve** — unchecking writes a reserve of 0%.
  That removes the *buffer*, not the solvency check: an order that would take
  your cash balance negative is still refused. There is deliberately no
  separate on/off field, because 0 already means "no reserve".

### Module 3 — Selling: *reduce risk*

"Check for recommended sells" surfaces **policy breaches** — concentration
over the cap, leveraged-ETF exposure, and so on. A recommendation here
means a rule was broken, never a price prediction. If nothing is flagged,
that is the correct answer, not a failure.

The preview shows the tax-lot consequences of a candidate sale, so you can
see the realized-gain cost before approving.

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
