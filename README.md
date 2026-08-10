# Personal trading assistant

A safety-first personal trading assistant and quantitative research
workbench. It combines portfolio awareness, deterministic risk analysis,
versioned research evidence, structured trade proposals, explicit approval,
and Alpaca paper execution.

The project does **not** claim to have discovered reliable stock-selection
alpha. Its production workflow therefore generates exposure-reducing
proposals from policy breaches; rejected or exploratory signals cannot create
buy orders.

For day-to-day operation (launcher, core pages, tax report, scheduled tasks,
troubleshooting), start with [`HOW_TO_USE.md`](HOW_TO_USE.md). This README
remains the project map and setup reference.

## What it does

- Reads positions, cash, buying power, and open orders from Alpaca, or uses an
  explicit sample/manual portfolio when Alpaca is not configured.
- Builds a versioned `DecisionPacket` containing portfolio state, exposure,
  market regime, upcoming earnings, research evidence, warnings, analytics,
  and data-freshness metadata.
- Produces morning briefings and persists them to SQLite.
- Answers deterministic portfolio-risk questions such as concentration,
  leveraged/unleveraged duplication, and benchmark stress impact.
- Generates typed, short-lived risk-reduction proposals with reasons,
  uncertainties, alternatives, and before/after portfolio previews.
- Requires an exact user approval phrase and reruns every risk check against a
  fresh broker snapshot before submission.
- Submits approved orders to Alpaca **paper trading only** and journals the
  resulting proposal and broker order.
- Scores portfolio research against a versioned machine-readable mandate;
  an unapproved mandate or incomplete evidence fails closed and never enables
  live trading.
- Maintains an append-only balanced portfolio journal that can be explicitly
  bootstrapped from, and reconciled against, an independent broker snapshot.
- Records active decision-packet and strategy market-data fetches with declared
  provider lineage, fails closed on stale/missing bars, and renders a visible
  degradation warning instead of presenting stale regime data confidently.
- Persists operational health alerts and verifies database backup/restore
  drills for an external process supervisor.
- Preserves the existing signal, backtest, statistical-validation, ML, and
  leveraged-ETF research toolkit.
- Provides a provider-neutral, read-only investment-committee foundation:
  privacy-controlled packet projection, addressable deterministic facts,
  strict review schemas, and fail-closed source/number/ticker/research-authority
  validation. It does not call a model or broker by itself.

## Safety model

The assistant is deliberately split into layers:

```text
broker / market / event data
            |
            v
versioned DecisionPacket
            |
            v
deterministic analytics and policy
            |
            v
typed TradeProposal
            |
            v
exact user approval
            |
            v
execution gate revalidation
            |
            v
short-lived intent-bound authorization
            |
            v
Alpaca paper broker
            |
            v
SQLite journal and reconciliation record
```

Important guarantees:

- The explanation layer never computes financial quantities from prose.
- Broker order functions reject calls without a short-lived execution-gate
  authorization tied to the exact ticker, side, quantity, and order type.
- Proposals are single-use and expire after 15 minutes by default.
- Repeated proposal generation cannot reset a working or filled proposal.
- Open broker orders, working assistant orders, legacy unresolved orders, and
  recently filled intents are checked for duplicates.
- Buys are checked against cash reserve, position, total-exposure, basket,
  leverage, order-value, stale-price, trading-hours, spread, slippage, and
  earnings rules.
- The cash-reserve check uses the tighter of raw cash and the broker's
  reported buying power (which already nets out reserved/pending-order
  funds). The position, total-exposure, basket, and leveraged-ETF checks
  also account for currently pending (not-yet-filled) buy orders, not just
  already-filled positions -- otherwise two proposals approved back-to-back
  (or an unrelated pending order) could each look individually fine while
  together exceeding a cap.
- A short-lived authorization is an HMAC signed with a process-local secret,
  not just a plain content hash of the trade's ticker/side/quantity/order
  type -- a plain hash can be recomputed by any code that imports the intent
  type, so it was never actually proof that the execution gate ran.
- Trading-hours checks use a real NYSE calendar (`pandas_market_calendars`),
  including holidays and early closes -- not just a weekday + fixed
  9:30-16:00 window, which would incorrectly approve a trade on a market
  holiday.
- A wide bid/ask spread blocks a trade (`max_spread_pct`) even for market
  orders, which have no limit price of their own to compare against. A
  one-sided or crossed quote fails closed rather than silently skipping the
  check, and a limit order requires a positive, finite `limit_price`.
- Sells cannot exceed the shares currently held.
- Share quantities are validated strictly at the authorization and broker
  boundaries: only a real positive `int` is accepted (not `bool`, `float`,
  `NaN`, infinity, a string, zero, or a negative value -- all of which would
  otherwise defeat a plain `shares <= 0` comparison). Enforced independently
  at both `validate_trade_intent()` and the broker submission functions
  (defense in depth). When reconstructing stored JSON proposal data, a
  finite, whole-valued float such as `10.0` may be normalized to the
  equivalent integer `10` (supporting numerically-equivalent JSON
  representations); a fractional or non-finite value (`10.5`, `NaN`,
  infinity) is still rejected rather than silently truncated.
- A concentration-cap or earnings-blackout block (never a data-integrity or
  hard-safety violation) can be knowingly overridden: the CLI's `approve
  --override` flag or the UI's typed `OVERRIDE ...` phrase. Every other
  violation (stale price, closed market, a bad quote, a duplicate order, the
  kill switch, insufficient cash, invalid share quantities) can never be
  overridden, even if it co-occurs with an overridable one.
- Submitting a batch of allocation proposals together (the Watchlist tab's
  "submit all") reserves each earlier leg's planned notional exactly once
  against later legs' cash, buying-power, and exposure/concentration checks
  -- never double-counted and never silently dropped -- and remains fully
  read-only until the user explicitly confirms the batch.
- A batch that finished with a leg blocked on an override-eligible violation
  re-syncs that leg from its underlying proposal (never re-submits) the next
  time it's viewed or resumed, so resolving it through that proposal's own
  override control is reflected instead of the batch showing a stale
  "blocked" status forever.
- `TRADING_ASSISTANT_KILL_SWITCH` and the durable SQLite kill switch both
  block proposal execution -- enforced
  inside the execution service itself (not only by callers that remember to
  read the env var and pass it in), so it can't be silently bypassed.
  Any value engages it EXCEPT the explicit off values `0`, `false`, `no`,
  `off`, and empty (case- and whitespace-insensitive) -- so `=true`, `=yes`
  and even a typo all halt trading. It used to require the exact string `1`,
  which meant `=true` silently did nothing on a control people reasonably
  trusted; the check now lives in one place (`assistant/kill_switch.py`)
  rather than being re-typed at eight call sites.
- The personal-assistant execution service refuses to run if
  `config.PAPER_TRADING` is `False`.
- Live-trading support is intentionally not exposed by the assistant CLI.
- If a broker submission fails ambiguously (e.g. a network timeout after the
  order may have already been accepted), the service reconciles by looking
  the order up under its own idempotency key before concluding anything --
  see "Submission reconciliation" below.
- Newly generated proposals bind the exact proposal-time share count. If the
  fresh pre-submit broker snapshot differs by a split-shaped ratio, validation
  refuses the stale intent before broker preflight and requires regeneration;
  no price-jump heuristic is used.

## Current research status

See `docs/MANDATE.md` for this project's numeric risk/return targets and
sleeve-scope decisions (which research directions are in-flight vs.
explicitly shelved).

The research registry lives in `assistant/research_findings.json` and is
loaded at runtime (`assistant/research_registry.py`). Every claim is
versioned, labeled independently by `EvidenceStatus`
(`confirmed` / `promising_unconfirmed` / `exploratory` / `rejected` /
`unavailable`), and attached to the *specific* claim it covers -- a single
strategy can carry a confirmed claim and a rejected claim at the same time
(see SOXX/SOXL below).

As of the current registry (`research_findings.json` version 1.5.0):

- **Rejected** (did not survive full confirmation and dependence-aware
  testing): the original z-score scanner; cross-sectional momentum (12-1
  month), including re-checked under realistic `next_open` entry timing;
  relative, breakout, PEAD, fundamentals, and analyst-rating signals;
  analyst price-target consensus gap; cross-asset macro signals (VIX spike,
  credit spread, yield curve); QQQ/TQQQ regime rotation; SOXX/SOXL rotation's
  **excess-return** claim (the pre-tax edge disappeared once realistic
  short-term capital-gains tax was modeled); Kelly-criterion sizing with
  a one-way profit ratchet (looked like a breakthrough on one
  discovery/confirmation split, then failed walk-forward validation -- it
  can never re-lever once trimmed, so it structurally misses upside in an
  extended bull market); and the three-sleeve engine's original growth rule
  (+5% any-term full exit / -10% add -- structurally stranded 95-99% of
  days in cash for a 3.29% modeled after-tax-proxy CAGR vs 48.14% holding
  the same names; rejected on a single descriptive window and revised to a
  long-term-gated trim before any notification code encoded it). The proxy
  uses dividend-adjusted prices, so it does not separately model dividend
  tax timing/classification and must not be read as an accountant-grade
  after-tax return.
- **Confirmed**: SOXX/SOXL trend/volatility rotation's **drawdown-reduction**
  claim (materially lower max drawdown across confirmation, walk-forward,
  sensitivity, and tax/cost checks -- a risk result, not an excess-return
  one); and a wide (15%) rebalance band vs. tight/continuous vol-targeting
  (~89% less tax/turnover for essentially the same performance).
- **Promising, unconfirmed**: the vol-targeting rotation mechanism tested on
  2 additional pairs (SPY/UPRO, NVDA/NVDL) beyond SOXX/SOXL -- designed and
  backtested only, not yet in live/paper trading. NVDL has substantially
  less real history than the other two pairs; see the underfilled-dataset
  warning below.
- **Rejected**: four additional signals tried on external (ChatGPT)
  recommendation -- idiosyncratic volatility, variance risk premium,
  residual momentum, overnight-gap reversal -- all rejected under the same
  out-of-sample + confirmation-only + block-bootstrap rigor bar, with a
  pre-registered shared Bonferroni correction across the family. See
  `assistant/research_findings.json` for per-signal detail. The
  implementations were removed from the codebase after this verdict was
  recorded -- git history (commit 8605f0e) retains them.
- **Exploratory** (first-pass only, explicitly not confirmed): a
  defensive-carry sleeve (`config.DEFENSIVE_CARRY_TICKERS` --
  TLT/IEF/SHY/GLD, deliberately kept OUT of `UNIVERSE`/`BASKETS` so the
  dip/up scanner never treats them as signal candidates). Blending them
  into an equal-weight `UNIVERSE` portfolio monotonically reduced max
  drawdown and expected shortfall as the carry weight rose from 0% to 30%,
  with downside capture narrowing slightly faster than upside capture. That
  is a **single lookback window with no walk-forward or out-of-sample
  split**, across three candidate weights -- suggestive, not evidence. See
  `scripts/run_defensive_carry_probe.py`. Not a live or paper allocation.

**One credit-spread anomaly, explicitly not promoted**: re-checked 2026-07-26
under realistic `next_open` (rather than same-close) entry timing, the
credit-spread "dip" leg flipped from non-significant to significant in
confirmation. This is **not** elevated to confirmed/promising -- testing both
timings without pre-registering which one counts is an uncorrected extra
look, the same multiple-testing risk this project's own tooling warns about
elsewhere. Treat it as an unconfirmed anomaly pending a dedicated, properly
pre-registered re-test.

**Research status is never converted automatically into production
authority; promotion remains an explicit, auditable decision.** Concretely:
a `confirmed`/`promising_unconfirmed` finding also carries a `provenance`
record (actual data date range/row count, entry timing, when it was
fetched, and a `reproduced_after_data_loader_fix` flag) and is rejected at
load time if that provenance is missing. `is_production_authoritative()`
checks that flag, not just the status string -- **as of this writing, none
of the confirmed/promising findings above have been re-verified since the
`fetch_historical` lookback-days data-loader fix** (only their data coverage
has been freshly re-checked), so every runtime consumer (CLI briefing,
Streamlit UI) displays them with an explicit
`-- UNREPRODUCED, NOT CURRENTLY PRODUCTION-AUTHORITATIVE` qualifier rather
than a bare `[confirmed]`. A dataset-underfill warning (e.g. NVDL's ~907
rows vs. the 1764 requested) is surfaced the same way, wherever that
finding is shown.

**2026-07-27 correction**: `signals/scanner.py`'s rolling z-score baseline
used to include the current row in its own rolling mean/std (pandas'
`rolling()` includes the current row by default; the code was not actually
shifting despite documentation claiming it did). This dilutes/inflates a big
move's own baseline, systematically understating its z-score, and affects
every signal that routes through `compute_features()` -- the core dip/up
scanner plus the VIX/credit-spread/yield-curve macro proxies. Fixed by
shifting the rolling window by one row. This changes exactly which dates get
flagged as signals; the existing REJECTED verdicts above have not yet been
re-run end-to-end against the corrected scanner, so treat them as needing
re-confirmation rather than as re-validated.

## Installation

Python 3.12 or newer is required by the pinned dependency set.

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m pytest tests -q
```

Dependencies in `requirements.txt` are version-pinned (exact versions, not
ranges) so a fresh install always reproduces the environment this project was
actually tested against, instead of silently picking up a newer release that
could change behavior. Bump pins deliberately and re-run the full test suite,
rather than leaving them unpinned.

**Windows note (confirmed the hard way, 2026-07-29 — read this BEFORE
installing):** `streamlit`'s wheel unpacks deeply nested asset directories; on
a Microsoft Store Python install (or any already-long install path) this
exceeds Windows' default 260-character path limit and leaves `pip install`
failing partway through with streamlit partially removed — a broken mixed
install that then also breaks `pytest` collection, since
`tests/test_personal_assistant_ui.py` imports streamlit.

Measured on this machine: `LongPathsEnabled=0`, and streamlit 1.60.0's
`streamlit/.agents/skills/developing-with-streamlit/assets/templates/apps/dashboard-seattle-weather/streamlit_app.py`
lands at exactly **260** characters under the Store-Python site-packages
prefix (144 chars). Do NOT try to repair it with `--ignore-installed`; that
writes the new version over the old one and produces `ImportError: cannot
import name 'calc_md5'`.

Two working remedies:

- **Short-path virtualenv (no admin needed, verified):** `python -m venv
  C:\venvs\ta` gives a 29-character prefix, bringing that same path to ~145
  characters. `C:\venvs\ta\Scripts\python.exe -m pip install -r
  requirements.txt` then installs the pinned set cleanly (`pip check` clean,
  928 tests pass, dashboard serves HTTP 200).
- **Enable long paths (needs elevation):** set
  `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled` to `1`
  in an admin shell, then install normally.

Beware a trap when downgrading as a workaround: `streamlit==1.52.2` requires
`pandas<3`, so installing it silently **downgrades the pinned pandas 3.0.5 to
2.3.x** (and protobuf/cachetools with it). `pip check` will then report
"no broken requirements" while the environment no longer matches
`requirements.txt` at all — check actual versions, not just `pip check`.

Also note streamlit 1.60.0 no longer uses **tornado** (it ships
starlette/uvicorn); a missing `tornado` is only a problem for older pins.

The current dependency set is:

- pandas / numpy
- yfinance
- Databento (cost-capped, immutable real-data ML ingestion; see
  `docs/DATABENTO_DATA_SOURCE.md`)
- alpaca-py
- lxml
- pandas_market_calendars (real NYSE trading-hours/holiday calendar)

### Continuous integration

`.github/workflows/tests.yml` runs `python -m pytest tests/` automatically on
every push and pull request to `main` via GitHub Actions -- the full suite
(deterministic/synthetic data and mocked broker calls only, no network or
credentials required) so a regression can't be merged without the CI check
failing first, instead of relying on a human remembering to run `pytest`
locally before every merge.

## Configure Alpaca paper trading

Create Alpaca paper credentials and provide them as environment variables.
Never commit credentials.

```powershell
$env:APCA_API_KEY_ID = "..."
$env:APCA_API_SECRET_KEY = "..."
```

```bash
export APCA_API_KEY_ID="..."
export APCA_API_SECRET_KEY="..."
```

Keep this setting unchanged:

```python
# config.py
PAPER_TRADING = True
```

Without credentials, briefings and proposals use
`assistant/sample_portfolio.py` and clearly identify the source as `manual`.

## Configure QuantConnect (research only, optional)

`research/quantconnect.py` drives backtests on QuantConnect's cloud and
brings the **results** home. It is research-only: it cannot create, size,
approve, or submit an order, and it is not reachable from any code that
can.

Get both values from your QuantConnect account page — the user id is shown
in account settings; the API token is requested from the security section
(they email it to you).

**Persist them for this machine (recommended)** so scheduled tasks and new
shells both see them:

```powershell
[Environment]::SetEnvironmentVariable("QC_USER_ID", "123456", "User")
[Environment]::SetEnvironmentVariable("QC_API_TOKEN", "your-token", "User")
```

Open a **new** shell afterwards — a running process keeps the environment it
started with. For one session only:

```powershell
$env:QC_USER_ID = "123456"
$env:QC_API_TOKEN = "your-token"
```

```bash
export QC_USER_ID="123456"
export QC_API_TOKEN="your-token"
```

Verify without running a backtest:

```powershell
python -c "from research.quantconnect import QuantConnectClient; print(QuantConnectClient().authenticate())"
```

**Known caveat on first real use (CQC-001).** The client refuses any
response lacking `success: true`. That is deliberate — QuantConnect reports
failure in-band with HTTP 200 — but no live call has ever been made from
this project, so it is an unverified assumption. If a call fails with
`failed (HTTP 200): no reason given` on a body that looks fine, suspect that
check rather than your credentials, and see
`docs/OPERATIONAL_FACTS.md`. A clean `authenticate()` does not prove it
holds for `read_backtest` / `list_backtests`.

The token is never transmitted: authentication sends
`sha256(f"{token}:{unix_timestamp}")` with the timestamp as a nonce, so each
request carries a different signature.

**What this deliberately cannot do.** QuantConnect's terms forbid exporting
site content "in raw form, such as CSV, API, FTP, or other formats", and
download licences are "for the licensed organization's internal LEAN use
only and cannot be redistributed or converted in any format". So their
market data cannot be pulled into this project's `{ticker: DataFrame}`
pipeline, however well it would fit. The client enforces this with an
endpoint allowlist rather than a comment — market-data paths are
structurally unreachable, so an endpoint QuantConnect adds later does not
become callable by default.

## Personal policy

The default versioned policy is
`assistant/default_policy.json`. It controls:

- read-only versus paper execution;
- user-approval requirement;
- per-position, total, basket, and leveraged-ETF exposure;
- minimum cash reserve;
- maximum order value;
- maximum daily submitted notional, daily order count, concurrent open orders,
  and working-order age;
- price freshness, spread, and slippage;
- earnings blackout window;
- allowed sides and order types (market and limit are both routed correctly
  to the matching broker call; anything else is rejected at policy-load time
  by `TradingPolicy.validate()`, which also rejects empty/negative/
  wrong-typed fields instead of failing silently later);
- whether new positions may be opened;
- whether validated strategy proposals (currently just the SOXX/SOXL
  wide-rebalance-band strategy) are checked by default on `propose`;
- whether a BUY is blocked when live earnings-date data can't be
  resolved at approval time (`require_earnings_data`; risk-reducing
  SELLs are always exempt, since blocking a concentration-reducing sale
  would increase risk, not reduce it).

The checked-in default is deliberately restrictive:

```json
{
  "execution_mode": "paper",
  "max_position_pct": 0.05,
  "max_total_exposure_pct": 0.50,
  "max_basket_pct": 0.40,
  "max_leveraged_etf_pct": 0.20,
  "min_cash_reserve_pct": 0.10,
  "max_order_value": 5000.0,
  "max_daily_submitted_notional": 25000.0,
  "max_daily_order_count": 10,
  "max_open_orders": 5,
  "max_order_age_minutes": 30.0,
  "max_spread_pct": 0.5,
  "allow_new_positions": false,
  "enable_strategy_proposals": false,
  "require_earnings_data": false
}
```

Create a separate policy file for personal changes and pass it using
`--policy`. Copy `assistant/my_policy.example.json` to
`assistant/my_policy.json` (gitignored, so your own risk-tolerance edits
never get committed or conflict with a repo update) and edit that copy.

Every proposal is bound to the policy that generated it by both a
human-readable `policy_version` string AND a `policy_fingerprint` --
a SHA256 hash over every policy field except `notes` (free text, not
behavior-affecting). Approval checks both: if you edit your policy file
without bumping its version, the fingerprint mismatch still blocks
approval and tells you to regenerate the proposal, instead of silently
approving a trade against stale risk limits.

## How to use

There are two front ends over the exact same underlying functions --
neither computes anything the other doesn't; pick whichever fits how you
work:

- **CLI** (`scripts/run_personal_assistant.py`) -- scriptable, good for
  quick checks or automation.
- **Browser UI** (`scripts/personal_assistant_ui.py`, Streamlit) -- click-
  around, better for browsing research/news per ticker and for the
  Watchlist's multi-ticker allocation-split workflow.

### Quickstart

1. Install dependencies and (optionally) set Alpaca paper credentials --
   see [Installation](#installation) and
   [Configure Alpaca paper trading](#configure-alpaca-paper-trading) above.
   Without credentials, the briefing and proposal-generation steps still
   work against `assistant/sample_portfolio.py`, but approval, submission,
   and broker reconciliation require Alpaca paper credentials.
2. Get a briefing: `python scripts/run_personal_assistant.py briefing`
3. Check for anything that needs attention:
   `python scripts/run_personal_assistant.py propose`
4. If a proposal was generated, review it, then approve it explicitly
   (requires Alpaca paper credentials):
   `python scripts/run_personal_assistant.py approve <proposal_id> --confirm approve`
5. Or run the Streamlit UI for the same briefing/proposal/approval workflow,
   plus the UI-only Watchlist cart and multi-ticker allocation-split
   features (no CLI equivalent exists for those):
   `python -m streamlit run scripts/personal_assistant_ui.py`

Nothing above places a real order until you type the exact confirmation
phrase for a specific proposal ID -- generating a briefing or a proposal is
always read-only.

### Build a briefing

```bash
python scripts/run_personal_assistant.py briefing
```

This retrieves the portfolio, market regime, open orders, research registry,
and upcoming earnings, then stores the packet in
`data/trading_assistant.db`.

Skip live earnings lookup when working offline:

```bash
python scripts/run_personal_assistant.py briefing --no-events
```

### Generate proposals

```bash
python scripts/run_personal_assistant.py propose
```

By default only deterministic exposure-reducing sells are generated. Add
`--strategy-proposals` to also check the SOXX/SOXL wide-rebalance-band
strategy (`evidence_status=promising_unconfirmed_strategy`, never
`confirmed` -- see `assistant/strategy_proposals.py`; only produces a
proposal if you already hold both SOXX and SOXL). Set
`"enable_strategy_proposals": true` in your policy file instead to make
this durable across runs rather than passing the flag every time.

```bash
python scripts/run_personal_assistant.py propose --strategy-proposals
```

A proposal resembles:

```text
tp_0123456789abcdef [deterministic_risk_policy]: SELL 10 SOXL at reference $55.00
  - Leveraged-ETF exposure exceeds the 20.0% policy limit.
  Preview: position 12.4% -> 9.8%
  ? <uncertainties/caveats specific to this proposal>
  Approve with: approve tp_0123456789abcdef --confirm approve
```

Generating a proposal does not place or approve an order.

### Review proposal state

```bash
python scripts/run_personal_assistant.py list
python scripts/run_personal_assistant.py list --status proposed
```

Proposal states (`assistant/proposal_status.py` is the single source of
truth used by the service, the UI's History filter, and tests -- so these
can't drift out of sync with each other again): `proposed`, `validating`,
`override_available`, `blocked`, `validation_failed`, `approved`,
`submitting`, `submission_unknown`, `reconciling`, `submission_failed`,
`broker_accepted`, `partially_filled`, `cancel_pending`, `filled`,
`canceled`, `broker_rejected`, `broker_expired`, legacy `executed`, and
`expired`. New orders never use legacy `executed`: broker acceptance is
working exposure, while only broker-confirmed `filled` means execution.

### Approve one paper order

Run this during standard US market hours with a fresh proposal. The
confirmation phrase is exactly `approve` (case-insensitive) -- it no longer
needs to repeat the proposal ID, since that's already the positional
argument you're passing:

```bash
python scripts/run_personal_assistant.py approve tp_0123456789abcdef --confirm approve
```

Immediately before submission the service:

1. verifies the proposal is still `proposed`, unexpired, and uses the active
   policy version and fingerprint;
2. confirms Alpaca is configured for paper trading and that the account is
   active/unblocked and the asset is active/tradable;
3. refreshes positions, cash, buying power, prices, and open orders;
4. checks duplicates, the durable kill switch, and every execution-gate rule;
5. creates a short-lived authorization bound to that exact intent;
6. atomically reserves the persistent daily order/notional budget;
7. submits the paper order with an idempotent client order ID;
8. journals the response as `broker_accepted`, `partially_filled`, or
   `filled` according to the broker's actual state.

If the proposal is blocked ONLY by an override-eligible violation (a
concentration cap or the earnings blackout window -- never a data-integrity
or hard-safety issue), the CLI tells you so and leaves the proposal in a
distinct `override_available` status. Re-run with `--override` to knowingly
proceed anyway:

```bash
python scripts/run_personal_assistant.py approve tp_0123456789abcdef --confirm approve --override
```

To stop all approvals without changing code:

```powershell
$env:TRADING_ASSISTANT_KILL_SWITCH = "1"
```

The persistent switch survives process restarts:

```bash
python scripts/run_personal_assistant.py kill-switch on --reason "operator stop"
python scripts/run_personal_assistant.py kill-switch status
python scripts/run_personal_assistant.py kill-switch off --reason "investigation complete"
```

### Submission reconciliation

An exception while submitting an order to Alpaca does not prove the broker
rejected it -- a network timeout, for instance, can lose the response after
the order was actually accepted. Treating that as a plain failure risks a
later retry submitting a genuine duplicate real order. On any submission
exception, the service:

1. looks the order up at the broker by the same idempotency key
   (`client_order_id`) it originally submitted;
2. if found, journals its real broker lifecycle state (accepted, partially
   filled, filled, canceled, rejected, or expired;
   `reconciled_after_error` records what the original error was);
3. if the lookup itself can't confirm either way, marks the proposal
   `submission_unknown` -- a distinct, non-terminal status. Proposals in
   `submitting` or `submission_unknown` are treated as live duplicate-order
   risk by the duplicate check, so a regenerated proposal for the same
   ticker/side is blocked until a human checks the Alpaca account directly
   and reconciles it.

Separately, if the broker call succeeds but the local SQLite journal write
afterward fails, the proposal preserves the broker response as working
exposure with the local failure recorded in its `error` field -- it is never
silently reported as a failed/no-order outcome.

The broker lookup itself distinguishes a *confirmed* absence (the broker's
own HTTP 404 -- genuinely no such order) from an *unconfirmed* one (the
lookup itself failed, e.g. a network error) -- only a confirmed absence
resolves straight to `submission_failed`; an unconfirmed one stays
`submission_unknown`.

### Resolving a stuck `submitting` / `submission_unknown` proposal

Re-running `approve` cannot help here -- the proposal is no longer
`proposed`. Reconcile it directly:

```bash
python scripts/run_personal_assistant.py reconcile tp_0123456789abcdef
```

(Also available as a "Reconcile" button in the browser UI's History tab,
shown automatically whenever a proposal has an unresolved broker
submission.) This re-queries Alpaca by the same idempotency key and
cross-checks the ticker/side against the proposal's own intent before
trusting it -- a mismatched order is left unresolved rather than silently
accepted. Every outcome (a broker lifecycle state, `submission_failed`, or
still `submission_unknown`) is timestamped in `reconciled_at`.

### Continuous order monitoring

Run one startup/poll reconciliation:

```bash
python scripts/run_personal_assistant.py sync-orders
```

Run the long-lived trade-update stream with a 30-second polling fallback:

```bash
python scripts/run_personal_assistant.py monitor-orders --cancel-stale --poll-seconds 30
```

Streaming and polling share one append-only, deduplicated event journal and
an atomic monotonic projection, so a replayed old `accepted` event cannot
move a `filled` proposal backward. To request cancellation of working orders
older than `max_order_age_minutes`, opt in with `--cancel-stale`; the service
never automatically reprices or replaces an order.

An operator can cancel the authoritative order for one proposal even after
the broker has replaced it:

```bash
python scripts/run_personal_assistant.py cancel-order tp_0123456789abcdef --confirm cancel
```

Annual realized-gain reporting (GR-7a), read-only, from recorded fills and
journal-confirmed corporate actions:

```bash
python scripts/run_personal_assistant.py tax-report --year 2026 \
    --format csv --output data/reports/realized-2026.csv
```

It exits 2 when share coverage is **incomplete** (the tax-lot ledger and
the broker disagree, so realized history is missing fills) or
**unverified** (`--no-coverage-check`, or the broker snapshot was
unavailable) — while still writing the artifact, because the limitation
belongs in the file an accountant reads, not only in the terminal.
Wash-sale entries are advisory flags; cost basis is never adjusted, since
the rule spans accounts this project cannot see. Not tax advice.

For an incident, the emergency command activates the persistent kill switch
first and then attempts to cancel every open broker order, including orders
not created by this app. It continues through individual failures and exits
nonzero if any cancellation or local projection failed:

```bash
python scripts/run_personal_assistant.py cancel-all-orders --confirm "cancel all open orders" --reason "operator incident"
```

The Windows scheduled-task installer enables `--cancel-stale` on the order
monitor, operations cycle, and post-close observation. Stale cancellation is
therefore enforced by the supplied unattended configuration, while direct
ad-hoc commands retain an explicit opt-in.

Before a paper soak or operator handoff:

```bash
python scripts/run_personal_assistant.py sync-orders
python scripts/run_personal_assistant.py readiness
python scripts/run_personal_assistant.py backup-db
```

`readiness` exits nonzero unless the policy and SQLite database are valid,
the persistent kill switch is off, no broker outcome is ambiguous,
reconciliation is recent/error-free, budgets are within policy, and the
connected paper account is active and unblocked.

### Production-foundation controls

Inspect the owner-approved, fingerprint-bound machine-readable mandate:

```bash
python scripts/run_personal_assistant.py mandate-status
```

The owner approved the current targets on 2026-08-04. `mandate-status`
recomputes the behavior fingerprint and refuses a mismatched approval.
Approval satisfies only one review gate: passing mandate metrics and every
other evidence check can make a run eligible for human review, but never
changes paper mode or authorizes live trading. See
`docs/LIVE_PROMOTION_CHECKLIST.md`.

After reviewing the connected paper account, initialize the accounting
journal exactly once and reconcile it:

```bash
python scripts/run_personal_assistant.py ledger-bootstrap --confirm bootstrap
python scripts/run_personal_assistant.py ledger-sync
python scripts/run_personal_assistant.py ledger-transfer --external-id deposit-2026-08-01 --amount 1000 --occurred-at 2026-08-01T14:00:00+00:00 --description "Broker cash deposit"
python scripts/run_personal_assistant.py ledger-fee --external-id fee-2026-08-01 --amount 0.03 --occurred-at 2026-08-01T14:00:00+00:00 --description "Regulatory fee"
python scripts/run_personal_assistant.py ledger-reconcile
```

The opening snapshot is explicit because this app's broker-event history does
not include positions acquired before the app existed. After bootstrap,
`ledger-sync` records app fills exactly once. Before comparing cash and shares,
`ledger-reconcile` also fetches Alpaca account activities created after the
bootstrap. It journals supported USD fees, plain cash dividends, and explicit
cash deposits/withdrawals exactly once. Dividend tax classification remains
`unknown`; non-cash/substitute-payment dividend subtypes, generic `JNLC` cash
journals, interest, and other unsupported activities fail closed rather than
being guessed. They cannot be cleared merely by entering a separate manual
journal row. The journal is permanently bound
to the Alpaca account ID captured at bootstrap; reconciliation refuses a
different or unidentified account. Transfers use signed amounts (positive
deposit, negative withdrawal), while fees use positive amounts. Tax lots
remain separate because the financial journal uses moving-average book basis
while tax elections can use FIFO/LIFO/HIFO/specific identification.

If the journal was bootstrapped by a version from before account-ID binding,
`ledger-reconcile` fails closed. Migrate it once while connected to the
original account; the command binds only after cash and every share quantity
match the journal within its strict cent/share tolerances:

```bash
python scripts/run_personal_assistant.py ledger-bind-account --confirm "bind account"
```

Run operational controls and a recovery drill:

```bash
python scripts/run_personal_assistant.py recovery-drill
python scripts/run_personal_assistant.py operations-check
python scripts/run_personal_assistant.py alerts
```

For a supervised paper soak, start an immutable evidence epoch and derive its
status from recorded post-close observations rather than entering session or
order counts manually:

```bash
python scripts/run_personal_assistant.py paper-epoch-start paper-2026q3 --strategy-id shared-capital-scanner --strategy-version 1.0.0 --model-id deterministic-no-model
python scripts/run_personal_assistant.py operations-cycle --alerts-jsonl data/alerts.jsonl
python scripts/run_personal_assistant.py paper-observation --alerts-jsonl data/alerts.jsonl
python scripts/run_personal_assistant.py paper-evidence-status paper-2026q3
```

The epoch requires a clean worktree and binds the exact Git commit, mandate,
policy, strategy, model, and Alpaca paper-account identity. Every observation
also verifies that the most recent ledger reconciliation belongs to that same
account. `paper-observation` only records a reconciled post-close Alpaca paper
snapshot and removes journaled cash transfers from period returns.
`operations-cycle` is a scheduler-friendly
order/ledger/reconciliation/backup/health pass. A Windows Task Scheduler
installer and the drill/evidence procedures are in
`docs/OPERATIONS_RUNBOOK.md`.

### Recovering a stranded reconciliation

If the process crashes mid-reconciliation (no in-process handler survives
that), a proposal can be left stuck in `reconciling` with no normal way to
retry it -- `reconcile` only claims from `submitting`/`submission_unknown`.
Recover it first, then reconcile as usual:

```bash
python scripts/run_personal_assistant.py recover-stale tp_0123456789abcdef
python scripts/run_personal_assistant.py reconcile tp_0123456789abcdef
```

Only recovers a proposal that has genuinely sat in `reconciling` for at
least `--stale-after-seconds` (default 300); a recent claim is presumed to
be an actually in-flight reconciliation and is left untouched. This window
must be a positive whole number of seconds -- zero, negative, or fractional
values are rejected (both by the CLI's argument parser and, authoritatively,
by the service itself), since a non-positive window would let a genuinely
active reconciliation be reclaimed immediately. There is no button for this
in the browser UI (CLI-only) since it's an intentionally rare crash-recovery
path, not a routine action.

### Browser UI

`scripts/personal_assistant_ui.py` is a Streamlit front end over the exact
same functions the CLI above uses -- no separate logic, just a different way
to view/click through briefing, proposals, and approval instead of typing
commands. Run it with:

```bash
python -m streamlit run scripts/personal_assistant_ui.py
```

then open the local URL it prints (defaults to `http://localhost:8501`).
The same safety property as the CLI is preserved: each proposal has a text
box requiring you to type the exact `approve` phrase before the submit
button becomes clickable -- there is no one-click "approve" button that
could submit an order by accident. An override-eligible block adds a second,
separate text box requiring an exact `OVERRIDE <SIDE> <SHARES> <TICKER>`
phrase naming that specific order.

Ten pages are selected from a left-sidebar menu, and only the selected
page's body executes per rerun. Operational pages share the same SQLite
store and policy file where applicable; research-only pages do not gain a
write path merely by living in the same UI:

- **Briefing** -- portfolio totals, market regime, risk exposure, open
  positions with per-position trend/volatility and evidence-labeled
  research, open orders, upcoming earnings, and warnings (including the
  batched GR-5 operational warnings). Click "Refresh briefing" to re-pull
  from Alpaca.
- **Buying** (formerly Watchlist) -- add tickers to a cart (pick from the
  universe or type any other symbol), then "Check cart" for each ticker's
  own trend/volatility, recent analyst price targets, recent news
  (optionally summarized by Claude if `ANTHROPIC_API_KEY` is set), a real
  historical best/worst hold-period return range, and this project's
  evidence-labeled signal history --
  **no probability-of-return number is ever shown**. With 2+ tickers
  checked, an inverse-volatility purchase split appears (a risk-sizing
  heuristic, not a stock pick), with a "max weight per ticker" cap slider.
  Enter a dollar amount to see the actual whole-share plan -- including
  existing holdings and known pending buys -- then either create individual
  proposals per ticker (each needs its own typed `approve`), or generate the
  whole split and submit it as one preflighted, sequential, resumable batch
  (typed confirmation: `I approve this transaction`). A batch is
  all-or-nothing at the start (any leg failing preflight submits none of
  them) but not atomic once started -- some legs can fill while a later one
  is blocked; safe to reload and resume, never resubmits an already-filled
  leg.
- **Selling** -- current holdings plus a "Check for recommended sells"
  button; a recommendation here means a policy-limit breach (concentration,
  leveraged-ETF exposure, etc.), the same deterministic check as `propose`,
  never a price prediction.
- **Propose & Approve** -- the same risk-reduction (and optionally SOXX/SOXL
  strategy) proposals as the CLI's `propose`/`approve`, in card form.
- **History** -- proposal and broker-order tables with an outcome-group
  filter (Awaiting decision / Processing / Broker working / Filled /
  Refused / Closed without fill / Other-unknown; exact status remains
  under Advanced, combining by intersection), plus a "Reconcile" button
  that appears automatically on any proposal with an unresolved broker
  submission. Expired and dismissed proposals are hidden by default and
  recoverable through explicit include-checkboxes (an explicit outcome or
  status selection always shows its rows). A "Manage unused proposals"
  expander **dismisses** (archives -- never deletes) unused
  never-broker-touched `proposed`/`expired` rows behind a preview, a
  required reason, and an exact typed phrase; the complete database
  record, audit metadata, and idempotency key remain, and dismissal can
  never call the broker. CLI parity: `dismiss-proposals` (preview-first;
  mutation requires the preview hash and
  `--confirm-dismiss unused-paper-proposals`).
- **Ticker Suggestions** -- research-only candidate tickers from
  most-active/IPO/AI sources, each independently verified before display;
  acting on one still requires the normal Buying-cart workflow.
- **Backtest** -- read-only research surface: pick one of the project's
  price-only signal scanners, tune its parameters, choose synthetic
  (default, seconds) or real yfinance data, universe or basket scope, and
  hold horizons, then run the same walk-forward engine the CLI research
  scripts use. Shows a multi-horizon summary table and a cumulative
  net-return chart per signal direction. Synthetic results are labeled as
  plumbing checks; real-data results are labeled exploratory, disclose
  missing or short-history tickers, and refuse an empty provider response
  or a signal configuration with too little history. No multiplicity
  correction runs here, and confirmatory significance lives only in the
  frozen CLI pipeline.
- **Reports** -- read-only owner reporting (GR-7). Today: the annual
  realized-gain report for a chosen tax year, built from recorded fills
  and journal-confirmed corporate actions, with short/long-term totals,
  per-lot rows, advisory wash-sale flags, and CSV/JSON download. It
  always states whether share coverage was verified **complete**,
  **incomplete** (the ledger disagrees with the broker, so realized
  history is missing fills), or **unverified** -- an incomplete export is
  labelled as such in the file itself, not just on screen. Not tax
  advice, and not a substitute for a broker 1099-B.
- **Operations** -- GR-5's read-only operator dashboard: platform
  readiness, alert-delivery records, and the two explicit alert-delivery
  buttons.
- **Settings & Features** -- session AI-feature preferences, read-only
  data-source/safety status, and the protected typed-confirmation policy
  editor for `allow_new_positions` / `enable_strategy_proposals`.

## Persistence

`assistant/storage.py` manages `data/trading_assistant.db` with these logical
records:

- versioned decision packets;
- immutable proposal identity and current status;
- current broker-order snapshots linked to proposals;
- append-only broker order/fill events;
- immutable balanced journal transactions and postings;
- broker-versus-ledger reconciliation runs;
- persistent daily execution reservations;
- deduplicated durable operational alerts;
- durable operator/reconciliation state.
- append-only provider-fetch outcomes used by data-integrity readiness.

The database and its WAL files are gitignored because they contain personal
account state. The research registry and default policy are committed because
they define behavior and evidence, not private runtime data.

## Main packages

```text
assistant/
  schemas.py               typed DecisionPacket/PortfolioSnapshot/SignalEvidence structures
  context_builder.py       portfolio + regime + evidence DecisionPacket
  data_integrity.py        recorded provider fetches, health alerts, readiness evidence
  policy.py                validated, versioned personal policy
  mandate.py               risk targets + fail-closed live-promotion review gate
  portfolio_ledger.py      balanced journal + broker snapshot reconciliation
  share_reconciliation.py  pure split-shaped share-count mismatch detection
  operations.py            health, alerts, backup/restore drills
  portfolio_analytics.py   deterministic portfolio metrics and previews
  research_registry.py     file-backed evidence claims + provenance/authority checks
  proposals.py             exposure-reducing typed proposals
  strategy_proposals.py    SOXX/SOXL wide-rebalance-band strategy proposals
  allocation_proposals.py  user-directed, inverse-volatility-weighted buy proposals
  allocation_batch.py      resumable, cumulative-preflight batch submission
  execution_service.py     approval, revalidation, paper submission
  order_lifecycle.py       broker status mapping + atomic event projection
  order_reconciler.py      stream, polling fallback, stale cancellation
  readiness.py             operational preflight/readiness report
  proposal_status.py       single source of truth for proposal status strings
  storage.py               SQLite state and idempotency
  risk_copilot.py          concentration, duplication, stress analysis (Briefing tab + `risk-check` CLI)
  explanations.py          "why was this ticker flagged?"
  stock_lookup.py          own-ticker trend/volatility, price targets, hold-period ranges
  news_summary.py          recent news, optional Claude-summarized (ANTHROPIC_API_KEY)
  ai_advisor.py            optional LLM notes, output-validated so it can never advise an allocation
  llm/                     read-only committee contracts, privacy projection, provider boundary, validators
research/
  quantconnect.py          QuantConnect cloud client -- RESULTS only, allowlisted endpoints, no execution reach
  ticker_verification.py   confirms a ticker is real/liquid before it enters a cart
  similarity_evidence.py   deterministic co-movement evidence behind "similar tickers"
  recommended_stocks.py    not-currently-held candidates surfaced in the Briefing tab (exploration only)
  sample_portfolio.py      manual fallback portfolio when Alpaca isn't configured

data/
  market_data.py           historical and synthetic price data
  price_source.py          provider-lineage and NYSE-session freshness contracts
  event_data.py            upcoming earnings with availability metadata
  earnings_data.py         point-in-time earnings history
  analyst_data.py          analyst actions [DORMANT: rejected signal, manual-only]
  price_target_data.py     point-in-time price-target consensus
  macro_data.py            credit-spread and yield-curve proxies

risk/
  execution_gate.py        typed validation and short-lived authorization

execution/
  alpaca_broker.py         authorized broker reads and paper/live endpoint

signals/                   pluggable research signals (scanner, momentum, relative,
                            breakout, PEAD, fundamentals, analyst/analyst_target,
                            vix_spike/credit_spread/yield_curve, regime)
backtest/
  engine.py                walk-forward and dependence-aware testing
  portfolio_simulator.py   tax/slippage-aware shared-capital equity-curve simulator
  research_report.py       data lineage + embargo + mandate-scored immutable report
  risk_metrics.py          drawdown/expected-shortfall/time-under-water/capture-ratio metrics
strategies/                leveraged-ETF rotation research (trend_vol_rotation.py,
                            vol_target_rotation.py, kelly_rotation.py, leverage_rotation.py)
baskets.py, config.py,     overlapping ticker baskets, every other tunable knob, and
market_analytics.py        generic backward-looking primitives shared by production and research
```

**Dormant modules — an explicit decision, not an oversight** (2026-07-29): an
orphan/dead-code audit originally found six modules that no script under
`scripts/` reached through imports. `backtest/portfolio_simulator.py` has
since been activated by `scripts/run_portfolio_research_report.py`; the five
research-evidence modules below remain deliberately dormant. The framing
matters, because "unreachable from the import graph" is not the same as
"abandoned":

- `data/earnings_data.py` + `signals/pead.py` + `signals/fundamentals.py`, and
  `data/analyst_data.py` + `signals/analyst.py`, are **completed experiments,
  not pending integrations.** Both clusters were built, tested against real
  data, and recorded `rejected` in `research_findings.json` (PEAD 0/2 cells
  significant, fundamentals 0/2, analyst-rating 0/2 — the last being the
  pooled-vs-confirmation-only near-miss, p=0.014 → p=0.656, that caused
  `out_of_sample_significance()` to be built in the first place). The code is
  retained as the **evidence trail for those verdicts** and so they can be
  re-tested; deleting it would destroy the record that the work was done.
  They are manually invocable (see the corrected PEAD snippet printed by
  `scripts/run_new_signals_report.py`) and are deliberately **not** wired into
  the CLI, the UI, or any automated pipeline. They are not app capabilities.
  One genuine open item: these verdicts predate the by-block bootstrap, so
  they rest on the older row-level method. Re-testing them under
  `out_of_sample_significance_by_block()` would be a real (if unexciting)
  improvement — noted, not done here, because it is a research decision with
  real compute cost, not a cleanup task.
No existing finding in `research_findings.json` was produced using the
portfolio simulator. Activation supplies a reproducible runner; it does not
retroactively upgrade or reproduce any registered finding.

`tests/test_module_hygiene.py` pins the cleanup that came out of the same
audit (a duplicate private SOXX/SOXL wrapper, five unused imports, and a
printed PEAD snippet that named a function — `fetch_earnings_surprises` — which
never existed, so anyone copying the displayed instructions got an
`ImportError`).

**Production vs. research** (2026-07-28): `assistant/`, `risk/execution_gate.py`,
`execution/`, and the two entry points (`scripts/run_personal_assistant.py`,
`scripts/personal_assistant_ui.py`) are the production surface -- the only
code with authority to build proposals, validate them, and submit paper
orders. `signals/`, `strategies/`, `backtest/`, and the `scripts/run_*.py`
research scripts are the research workbench -- ideas are developed and
rigor-tested there, and only gain production authority by being
explicitly wired into `assistant/` (as `strategy_proposals.py`'s SOXX/SOXL
rebalancer was) and recorded `confirmed` in `research_findings.json` --
never automatically, and never by a rejected signal generating a buy
proposal. `market_analytics.py` and `backtest/risk_metrics.py` are the
two intentional exceptions: generic, network-free computation (trend
classification, forward-return baselines, drawdown/tail-risk metrics)
that both sides depend on, not signal logic itself. See
`docs/ARCHITECTURE_DEBT.md` for known gaps in that boundary
(risk-check logic still scattered across a few production files) and
`docs/MANDATE.md` for which research directions are in-flight vs. shelved.

## Research workflow

The signal API returns:

```text
ticker, date, close, return_pct, return_zscore,
volume_zscore, direction
```

This lets every signal reuse the same:

- forward-return backtest;
- own-ticker and market baselines;
- discovery/confirmation split;
- by-date and moving-block bootstrap;
- equal-date and trade weighting;
- multiple-comparison correction.

The most rigorous available check is
`out_of_sample_significance_by_block()`. Only the pre-specified primary row
in the confirmation period counts as evidence. Sensitivity variants are not
independent chances to declare success.

Useful research commands:

```bash
python scripts/run_backtest.py
python scripts/run_backtest_horizons.py
python scripts/run_baseline_comparison.py
python scripts/run_out_of_sample_check.py
python scripts/run_significance_check.py
python scripts/run_macro_signals_significance_check.py
python scripts/run_analyst_target_significance_check.py
python scripts/run_momentum_block_significance.py
python scripts/run_execution_timing_revalidation.py
python scripts/run_basket_report.py
```

The Streamlit UI's **Backtest** page runs the same walk-forward engine
interactively (signal picker, parameter widgets, summary table, cumulative
net-return chart) for exploratory looks. It records the actual loaded data
coverage with each session result, warns about missing/short histories, and
refuses inputs that would silently describe a different or impossible
experiment. The confirmatory significance/out-of-sample pipeline above
remains CLI-only on purpose.

`scripts/` also holds the leveraged-ETF rotation research line: regime-
rotation backtests/walk-forward/sensitivity/grid-search
(`run_regime_rotation_*.py`), per-pair vol-target rotation backtests
(`run_vol_target_rotation_backtest.py`, `_soxx_soxl.py`, `_spy_upro.py`,
`_nvda_nvdl.py`), the Kelly-ratchet walk-forward check
(`run_kelly_ratchet_walkforward_soxx_soxl.py`), the leverage-rotation
backtest (`run_leverage_rotation_backtest.py`), and a head-to-head idea
comparison (`run_idea_comparison_soxx_soxl.py`) -- these are the scripts
behind the confirmed/rejected claims in
[Current research status](#current-research-status) above. Use the
`real-data-check` project skill (or its equivalent checklist) before
trusting any real-data run: verify a new ticker resolves and has adequate
history, run in the background (these take minutes against real data), and
apply the project's standing statistical caveats (small-sample skepticism,
multiple-hold-period checks, baseline comparison, multiple-testing
correction) before reporting a result.

The leveraged-ETF strategies enforce next-day-open execution after using a
day's close to classify state. Tax and transaction-cost modeling are
available in their simulators (`backtest/portfolio_simulator.py`).

## Tests

```bash
python -m pytest tests -q
```

The suite covers scanners, backtests, research statistics, strategies,
assistant schemas, context building, explanations, stress
analysis, execution limits (including strict share-quantity validation),
policy validation, SQLite idempotency, proposal generation, allocation
batch preflight/execution, research-registry provenance/authority
enforcement, balanced journal accounting, broker reconciliation,
mandate/promotion gates, immutable research manifests, operational alerting,
recovery drills, CLI argument validation, authorization binding, and approved
paper submission with a mocked broker.

Broker tests do not contact Alpaca. Real-data research scripts do require
network access.

## Remaining limitations

- See `docs/ARCHITECTURE_DEBT.md` for known structural gaps (the execution
  kernel's mixed concerns, risk-check scatter across several files) that
  have been consciously deferred rather than fixed, and why.
- There is a CLI and a browser UI (Streamlit), but no conversational API.
- Earnings come from a free best-effort data source; unavailable values remain
  explicitly unavailable.
- The financial journal supports explicit dividend, split, fee, and
  cash-transfer entries. Risk-reducing sell proposals already display an
  advisory FIFO/LIFO/HIFO lot comparison when complete app-derived lot
  coverage exists, and missing coverage never blocks a sell. Automatic
  broker ingestion is deliberately narrow (fees, plain cash dividends, and
  explicit deposits/withdrawals); other corporate actions and generic cash
  journals fail closed. Broker-side specific-lot
  election, wash-sale basis adjustment, and actual tax-liability calculation
  remain unimplemented.
- Order monitoring and an operations watchdog are implemented, with durable
  SQLite alerts and an optional local JSONL delivery boundary. An actual pager
  or hosted supervisor still must be configured outside this repository.
- Market data used in research is not an institutional production feed.
- Survivorship bias, delistings, liquidity, and borrow constraints remain
  important research limitations. Quantified 2026-07-26: `config.UNIVERSE`
  is confirmed survivorship-biased -- of the three regional banks that
  failed/were seized during this project's own 7-year lookback window
  (SIVB, SBNY, FRC, all Mar-May 2023), none are in the universe. SIVB and
  FRC return no data at all via yfinance ("possibly delisted"); SBNY is
  worse -- that ticker symbol was silently REUSED by an unrelated company
  starting Aug 2024, so fetching "SBNY" today returns a different
  company's ~1.9 years of history with no error, not an absence. Any
  future universe expansion should sanity-check a new ticker's listing
  date/company identity (see the `real-data-check` skill), not just that
  `fetch_historical` returned something. Separately, 11/104 current
  UNIVERSE tickers (PLTR, SNOW, ABNB, COIN, SOFI, AFRM, RIVN, TMC, LAC,
  MP, and SPCX at only 28 days) have under 90% of the 1764-day lookback,
  diluting their contribution to any 7-year backtest.
  Practical impact on this project's findings: LOW for the "0 signals
  confirmed" conclusions, since each signal's edge is measured against
  that same ticker's own baseline return, and survivorship bias inflates
  both sides roughly equally -- if anything this makes the rejections
  more credible, not less. HIGHER for any absolute return number (e.g.
  buy-and-hold CAGR baselines, portfolio-simulator equity curves), which
  are computed on a "survivors only" universe and likely run somewhat
  optimistic. The "dip" signal specifically never saw a real
  bought-the-dip-and-it-went-to-zero case, since bankrupt names aren't in
  the universe at all -- its measured downside tail is understated
  (low-stakes since it's already rejected).
- **Legacy reports have no embargo between discovery and confirmation**
  (found 2026-07-29). The split boundary itself is clean --
  `backtest/engine.py`'s
  `_split_by_date()` puts a date in exactly one side -- but a signal firing
  ON the split date has its forward return measured over the following
  `hold_days`, which land inside the confirmation period. So the last
  ~`hold_days` of discovery and the first ~`hold_days` of confirmation
  share overlapping return windows and are not fully independent. Standard
  walk-forward practice embargoes `hold_days` around the split. Practical
  impact on current findings: LOW -- the overlap is roughly `hold_days`
  dates out of a several-hundred-date confirmation period, and it biases
  the two periods toward AGREEING, so it cannot manufacture a rejection;
  every finding recorded so far is a rejection or a risk-shape result. It
  was deliberately not changed retroactively, since doing so would shift
  every number in the versioned research registry. New immutable portfolio
  reports generated through `backtest/research_report.py` use a conservative
  symmetric embargo equal to `hold_days`; legacy findings still need to be
  reproduced through that path before they can be promoted.
- No strategy is authorized to open new positions under the default policy.

These limitations should be resolved incrementally without weakening the
execution boundary or silently promoting exploratory research.
