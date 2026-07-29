# Personal trading assistant

A safety-first personal trading assistant and quantitative research
workbench. It combines portfolio awareness, deterministic risk analysis,
versioned research evidence, structured trade proposals, explicit approval,
and Alpaca paper execution.

The project does **not** claim to have discovered reliable stock-selection
alpha. Its production workflow therefore generates exposure-reducing
proposals from policy breaches; rejected or exploratory signals cannot create
buy orders.

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
- Preserves the existing signal, backtest, statistical-validation, ML, and
  leveraged-ETF research toolkit.

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
- Repeated proposal generation cannot reset an executed proposal.
- Open broker orders and recently executed intents are checked for duplicates.
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
- `TRADING_ASSISTANT_KILL_SWITCH=1` blocks proposal execution -- enforced
  inside the execution service itself (not only by callers that remember to
  read the env var and pass it in), so it can't be silently bypassed.
- The personal-assistant execution service refuses to run if
  `config.PAPER_TRADING` is `False`.
- Live-trading support is intentionally not exposed by the assistant CLI.
- If a broker submission fails ambiguously (e.g. a network timeout after the
  order may have already been accepted), the service reconciles by looking
  the order up under its own idempotency key before concluding anything --
  see "Submission reconciliation" below.

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

As of the current registry (`research_findings.json` version 1.1.0):

- **Rejected** (did not survive full confirmation and dependence-aware
  testing): the original z-score scanner; cross-sectional momentum (12-1
  month), including re-checked under realistic `next_open` entry timing;
  relative, breakout, PEAD, fundamentals, and analyst-rating signals;
  analyst price-target consensus gap; cross-asset macro signals (VIX spike,
  credit spread, yield curve); QQQ/TQQQ regime rotation; SOXX/SOXL rotation's
  **excess-return** claim (the pre-tax edge disappeared once realistic
  short-term capital-gains tax was modeled); and Kelly-criterion sizing with
  a one-way profit ratchet (looked like a breakthrough on one
  discovery/confirmation split, then failed walk-forward validation -- it
  can never re-lever once trimmed, so it structurally misses upside in an
  extended bull market).
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

Python 3.10 or newer is recommended.

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

**Windows note:** `streamlit`'s wheel unpacks a deeply nested `static/`
directory; on a Microsoft Store Python install (or any install path that's
already long), this can exceed Windows' default 260-character path limit and
leave `pip install` failing partway through with streamlit partially removed.
If that happens, either enable long paths
(`git config --system core.longpaths true` plus the Windows policy setting at
`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled`), or create
your virtualenv at a short path (e.g. `C:\venv\ta` instead of a deeply nested
project directory) before installing.

The current dependency set is:

- pandas / numpy
- yfinance
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

## Personal policy

The default versioned policy is
`assistant/default_policy.json`. It controls:

- read-only versus paper execution;
- user-approval requirement;
- per-position, total, basket, and leveraged-ETF exposure;
- minimum cash reserve;
- maximum order value;
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
`executed`, `expired`.

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
2. confirms Alpaca is configured for paper trading;
3. refreshes positions, cash, buying power, prices, and open orders;
4. checks duplicates and every execution-gate rule;
5. creates a short-lived authorization bound to that exact intent;
6. submits the paper order with an idempotent client order ID;
7. records the order and marks the proposal executed.

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

### Submission reconciliation

An exception while submitting an order to Alpaca does not prove the broker
rejected it -- a network timeout, for instance, can lose the response after
the order was actually accepted. Treating that as a plain failure risks a
later retry submitting a genuine duplicate real order. On any submission
exception, the service:

1. looks the order up at the broker by the same idempotency key
   (`client_order_id`) it originally submitted;
2. if found, journals it and marks the proposal `executed`, same as a normal
   success (`reconciled_after_error` records what the original error was);
3. if the lookup itself can't confirm either way, marks the proposal
   `submission_unknown` -- a distinct, non-terminal status. Proposals in
   `submitting` or `submission_unknown` are treated as live duplicate-order
   risk by the duplicate check, so a regenerated proposal for the same
   ticker/side is blocked until a human checks the Alpaca account directly
   and reconciles it.

Separately, if the broker call succeeds but the local SQLite journal write
afterward fails, the proposal is still marked `executed` (the order really
was accepted) with the local failure recorded in its `error` field --
never silently reported as failed when a real order exists.

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
accepted. Every outcome (executed, submission_failed, or still
submission_unknown) is timestamped in `reconciled_at` as an audit trail.

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

Five tabs, all reading/writing the same SQLite store and policy file:

- **Briefing** -- portfolio totals, market regime, risk exposure, open
  positions with per-position trend/volatility and evidence-labeled
  research, open orders, upcoming earnings, and warnings. Click "Refresh
  briefing" to re-pull from Alpaca.
- **Watchlist** -- add tickers to a cart (pick from the universe or type any
  other symbol), then "Check cart" for each ticker's own trend/volatility,
  recent analyst price targets, recent news (optionally summarized by Claude
  if `ANTHROPIC_API_KEY` is set), a real historical best/worst hold-period
  return range, and this project's evidence-labeled signal history --
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
- **History** -- filterable proposal and broker-order tables, plus a
  "Reconcile" button that appears automatically on any proposal with an
  unresolved broker submission.

## Persistence

`assistant/storage.py` manages `data/trading_assistant.db` with these logical
records:

- versioned decision packets;
- immutable proposal identity and current status;
- broker-order submissions linked to proposals.

The database and its WAL files are gitignored because they contain personal
account state. The research registry and default policy are committed because
they define behavior and evidence, not private runtime data.

## Main packages

```text
assistant/
  schemas.py               typed DecisionPacket/PortfolioSnapshot/SignalEvidence structures
  context_builder.py       portfolio + regime + evidence DecisionPacket
  policy.py                validated, versioned personal policy
  portfolio_analytics.py   deterministic portfolio metrics and previews
  research_registry.py     file-backed evidence claims + provenance/authority checks
  proposals.py             exposure-reducing typed proposals
  strategy_proposals.py    SOXX/SOXL wide-rebalance-band strategy proposals
  allocation_proposals.py  user-directed, inverse-volatility-weighted buy proposals
  allocation_batch.py      resumable, cumulative-preflight batch submission
  execution_service.py     approval, revalidation, paper submission
  proposal_status.py       single source of truth for proposal status strings
  storage.py               SQLite state and idempotency
  risk_copilot.py          concentration, duplication, stress analysis (Briefing tab + `risk-check` CLI)
  explanations.py          "why was this ticker flagged?"
  stock_lookup.py          own-ticker trend/volatility, price targets, hold-period ranges
  news_summary.py          recent news, optional Claude-summarized (ANTHROPIC_API_KEY)
  sample_portfolio.py      manual fallback portfolio when Alpaca isn't configured

data/
  market_data.py           historical and synthetic price data
  event_data.py            upcoming earnings with availability metadata
  earnings_data.py         point-in-time earnings history
  analyst_data.py          analyst actions
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
  portfolio_simulator.py   tax/slippage-aware equity-curve simulator
  risk_metrics.py          drawdown/expected-shortfall/time-under-water/capture-ratio metrics
strategies/                leveraged-ETF rotation research (trend_vol_rotation.py,
                            vol_target_rotation.py, kelly_rotation.py, leverage_rotation.py)
baskets.py, config.py,     overlapping ticker baskets, every other tunable knob, and
market_analytics.py        generic backward-looking primitives shared by production and research
```

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
enforcement, CLI argument validation, authorization binding, and approved
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
- Tax-lot selection, wash-sale handling, dividends, and realized-tax estimates
  are not yet integrated into proposals.
- SQLite stores submitted broker state, but continuous fill/partial-fill
  reconciliation and alerting are future work.
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
- No strategy is authorized to open new positions under the default policy.

These limitations should be resolved incrementally without weakening the
execution boundary or silently promoting exploratory research.
