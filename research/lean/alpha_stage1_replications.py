"""LEAN Stage 1 replications: REP-H52 and REP-IDV.

Specifications frozen in `docs/Alpha_Test_Implementation_Plan.md` section 6.
This algorithm REPORTS ALPHA STATISTICS, so every run is a counted
research look. It is not exempt.

**The machinery here is a deliberate copy of `alpha_battery_monthly.py`,
not a reimplementation.** That file's timing, delisting, alignment,
basket-freezing, drift-turnover and completeness behaviour has been
reviewed twice (QCAR-001/002/003/005, AQR1-001/005) and verified
behaviourally. Rewriting it for a new pair of scores is how the previous
round reintroduced defects that had just been fixed, so only
`_form_scores` and the spec list differ.

Two specifications, both formed at the last close of each calendar month,
entered at the next distinct close, and held for exactly 21 sessions:

REP-H52 -- 52-week-high proximity. Score is `close_t / max(close[t-251:t])`
using adjusted closes, requiring 252 aligned sessions with no imputation.
This is a METHOD replication of the local signal on a better universe, not
an exact data replication: the local signal held 126 days and this holds
21, so it answers a narrower one-month portfolio question. Stated here
rather than described as exact.

REP-IDV -- low idiosyncratic-volatility proxy. Intercept and market beta
are estimated on the 90 daily returns ENDING BEFORE the 21-session
formation month; residuals over the formation month are taken against
those frozen coefficients and the point-in-time equal-weight QC market
return; the score is the negative sample standard deviation of those 21
residuals. This replicates the project's rejected market-model proxy, NOT
the Fama-French three-factor specification.

No industry, size or factor variant may be added after seeing a result;
that would be a new named look, not this one.
"""
from AlgorithmImports import *  # noqa: F403

from collections import deque
import math


# Universe under test. The driver rewrites this constant; it refuses if it
# cannot find it, rather than silently running a different screen.
ACTIVE_UNIVERSE = "B_core"
START = (2012, 1, 1)
END = (2024, 12, 31)

UNIVERSES = {
    "A_large": {"min_price": 5.0, "min_cap": 10_000_000_000.0, "min_adv": 25_000_000.0},
    "B_core": {"min_price": 5.0, "min_cap": 500_000_000.0, "min_adv": 5_000_000.0},
    "C_broad": {"min_price": 3.0, "min_cap": 100_000_000.0, "min_adv": 1_000_000.0},
}

LOOKBACK = 300          # 252-session H52 window, or 90 fit + 21 formation
MIN_NAMES = 30          # a cross-section below this is not a ranking
DECILE = 0.10
QUINTILE = 0.20
H52_SESSIONS = 252              # 52 weeks of aligned closes
IDV_ESTIMATION_SESSIONS = 90    # frozen fit window, ends before formation
IDV_FORMATION_SESSIONS = 21     # volatility measured over this month
# The completeness guard refuses unless EVERY name here emits. Carrying the
# monthly battery's list into this file would have demanded ten
# specifications this algorithm never computes, producing an immediate and
# entirely spurious INCOMPLETE refusal.
SPECIFICATIONS = ("REP_H52", "REP_IDV")


def _aligned_price_tail(values, value_sessions, market_sessions, count, end_ago=0):
    """Return ``count + 1`` prices only when every market date matches.

    Universe exits, halts and missing bars must not turn two non-adjacent
    observations into a one-session return merely because they are adjacent
    in a deque.
    """
    required = count + 1
    if count < 0 or end_ago < 0:
        return None
    value_end = len(values) - end_ago
    market_end = len(market_sessions) - end_ago
    if value_end < required or market_end < required:
        return None
    value_start = value_end - required
    market_start = market_end - required
    sessions = list(value_sessions)[value_start:value_end]
    if sessions != list(market_sessions)[market_start:market_end]:
        return None
    return list(values)[value_start:value_end]


def _aligned_observation_tail(values, value_sessions, market_sessions, count, end_ago=0):
    """Return exactly ``count`` observations ending ``end_ago`` sessions back."""
    if count <= 0 or end_ago < 0:
        return None
    value_end = len(values) - end_ago
    market_end = len(market_sessions) - end_ago
    if value_end < count or market_end < count:
        return None
    value_start = value_end - count
    market_start = market_end - count
    sessions = list(value_sessions)[value_start:value_end]
    if sessions != list(market_sessions)[market_start:market_end]:
        return None
    return list(values)[value_start:value_end]


def _is_new_calendar_month(previous_session, current_session):
    """True only on the first distinct exchange session of a new month."""
    if previous_session is None or current_session <= previous_session:
        return False
    return (previous_session.year, previous_session.month) != (
        current_session.year, current_session.month
    )


def _holding_period_complete(entry_index, current_index, hold_sessions=21):
    """A close-to-close cohort exits after exactly ``hold_sessions`` gaps."""
    return current_index - entry_index >= hold_sessions


def _spearman(pairs):
    """Rank correlation of (score, outcome). Ranks, so outlier-immune."""
    if len(pairs) < MIN_NAMES:
        return None
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = average
            i = j + 1
        return out
    xs = ranks([p[0] for p in pairs])
    ys = ranks([p[1] for p in pairs])
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy)


def _h52_score(prices):
    """close_t / max(close over the window). Pure, so tests call THIS."""
    if not prices:
        return None
    peak = max(prices)
    return None if peak <= 0 else prices[-1] / peak


def _idio_vol_score(stock, market, estimation_sessions, formation_sessions):
    """Negative stdev of market-model residuals over the formation month.

    Module level and pure on purpose. The previous round's tests
    reimplemented the score inside the test file, so they would have passed
    whatever the algorithm computed; these functions are the ones the
    algorithm actually calls.
    """
    span = estimation_sessions + formation_sessions
    if len(stock) != span or len(market) < span:
        return None
    mkt = market[-span:]
    fit_y = stock[:estimation_sessions]
    fit_x = mkt[:estimation_sessions]
    n = len(fit_y)
    if n < 2:
        return None
    mean_x = sum(fit_x) / n
    mean_y = sum(fit_y) / n
    var_x = sum((v - mean_x) ** 2 for v in fit_x)
    if var_x <= 1e-18:
        return None
    beta = sum((a - mean_x) * (b - mean_y) for a, b in zip(fit_x, fit_y)) / var_x
    alpha = mean_y - beta * mean_x
    residuals = [y - alpha - beta * x
                 for y, x in zip(stock[estimation_sessions:], mkt[estimation_sessions:])]
    if len(residuals) != formation_sessions or len(residuals) < 2:
        return None
    mean_r = sum(residuals) / len(residuals)
    variance = sum((r - mean_r) ** 2 for r in residuals) / (len(residuals) - 1)
    return -math.sqrt(variance)


def _valid_industry_code(value):
    """Return a real Morningstar industry code; missing/invalid stays missing."""
    try:
        code = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return None
    return code if code > 0 else None


def _drift_turnover(previous, target, outcomes):
    """Method V2 one-way turnover from drifted signed weights."""
    if not previous:
        return 0.5 * sum(abs(weight) for weight in target.values())
    if any(symbol not in outcomes for symbol in previous):
        return None
    portfolio_return = sum(
        weight * outcomes.get(symbol, 0.0)
        for symbol, weight in previous.items()
    )
    denominator = 1.0 + portfolio_return
    if denominator <= 0.0:
        return None
    drifted = {
        symbol: weight * (1.0 + outcomes.get(symbol, 0.0)) / denominator
        for symbol, weight in previous.items()
    }
    names = set(drifted) | set(target)
    return 0.5 * sum(
        abs(target.get(symbol, 0.0) - drifted.get(symbol, 0.0))
        for symbol in names
    )


class AlphaStage1Replications(QCAlgorithm):

    def initialize(self):
        self.set_start_date(*START)
        self.set_end_date(*END)
        self.set_cash(100_000)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.ADJUSTED
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.add_universe(self._coarse, self._fine)

        self.closes = {}            # Symbol -> deque of daily closes
        self.close_sessions = {}    # Symbol -> matching exchange sessions
        self.sessions = deque(maxlen=LOOKBACK)
        # Avoid shadowing QCAlgorithm.fundamentals, a framework member.
        self.fundamental_cache = {} # Symbol -> latest point-in-time values
        self.industry = {}          # Symbol -> Morningstar industry code
        self.selected = []          # this month's eligible symbols
        self.selection_history = {} # (year, month) -> PIT selected symbols
        self.cohorts = []           # independently settled 21-session cohorts
        # Selection is keyed off the CALENDAR, not off OnData. The first
        # version gated selection on a flag that only OnData set, and
        # OnData needs securities, which needs selection: a deadlock that
        # ran to completion reporting cap_rows=0 rather than failing.
        self.selection_month = None
        self.last_session = None
        self.session_index = -1
        self.in_universe = set()
        self.retained = set()
        self.terminal_prices = {}
        self.market_returns = deque(maxlen=LOOKBACK)
        self.market_return_sessions = deque(maxlen=LOOKBACK)

        self.cap_missing = 0
        self.cap_fallback = 0
        self.cap_rows = 0
        self.results = {}           # spec -> per-date IC/return/turnover rows
        self.previous_weights = {}  # (spec, construction) -> signed weights
        self.previous_entries = {}  # matching prices at prior rebalance

    # --- universe ------------------------------------------------------

    def _coarse(self, coarse):
        if self.selection_month == (self.time.year, self.time.month):
            return Universe.UNCHANGED
        return [c.symbol for c in coarse
                if c.has_fundamental_data
                and c.price >= self.screen["min_price"]
                and c.dollar_volume >= self.screen["min_adv"]]

    def _fine(self, fine):
        if self.selection_month == (self.time.year, self.time.month):
            return Universe.UNCHANGED
        self.selection_month = (self.time.year, self.time.month)
        chosen = []
        for f in fine:
            self.cap_rows += 1
            cap = float(f.market_cap or 0.0)
            if cap <= 0.0:
                # MarketCap == 0 is MISSING, not small. Reconstruct where
                # possible; count both outcomes so the excluded set is
                # never invisible.
                shares = 0.0
                try:
                    shares = float(f.company_profile.shares_outstanding or 0.0)
                except Exception:  # noqa: BLE001
                    shares = 0.0
                price = float(f.price or 0.0)
                if shares > 0.0 and price > 0.0:
                    cap = shares * price
                    self.cap_fallback += 1
                else:
                    self.cap_missing += 1
                    continue
            if cap < self.screen["min_cap"]:
                continue
            # Stage 1 computes no industry factor; this mirrors the corrected
            # monthly ingestion (FQCV-004) so the retained machinery cannot
            # hand a future variant a fictitious code-0 industry bucket.
            code = _valid_industry_code(
                f.asset_classification.morningstar_industry_code)
            if code is None:
                self.industry.pop(f.symbol, None)
            else:
                self.industry[f.symbol] = code
            self.fundamental_cache[f.symbol] = {
                "gross_profit": float(
                    f.financial_statements.income_statement.gross_profit.value or 0.0),
                "assets": float(
                    f.financial_statements.balance_sheet.total_assets.value or 0.0),
                "debt": float(
                    f.financial_statements.balance_sheet.total_debt.value or 0.0),
                "fcf": float(
                    f.financial_statements.cash_flow_statement.free_cash_flow.value or 0.0),
                "roe": float(f.operation_ratios.roe.value or 0.0),
                "cap": cap,
            }
            chosen.append(f.symbol)
        current = set(chosen)
        # The prior month's members are still needed for the month-end score
        # and next-session entry that occur in this very slice. Open cohorts
        # and prior rebalance weights must also survive universe removal.
        needed = set(self.selected)
        for cohort in self.cohorts:
            needed.update(cohort.get("entry", {}))
        for weights in self.previous_weights.values():
            needed.update(weights)
        for symbol in self.in_universe - current:
            if symbol in needed and symbol not in self.retained:
                self.add_security(symbol, Resolution.DAILY)
                self.retained.add(symbol)
        self.in_universe = current
        self.selected = chosen
        self.selection_history[self.selection_month] = tuple(chosen)
        if len(self.selection_history) > 3:
            oldest = sorted(self.selection_history)[:-3]
            for key in oldest:
                self.selection_history.pop(key, None)
        return chosen

    # --- data ----------------------------------------------------------

    def on_data(self, data):
        for symbol, delisting in data.delistings.items():
            if delisting.type != DelistingType.DELISTED:
                continue
            raw_price = getattr(delisting, "price", None)
            if raw_price is None:
                raw_price = getattr(delisting, "value", 0.0)
            try:
                self.terminal_prices[symbol] = max(0.0, float(raw_price))
            except (TypeError, ValueError):
                self.terminal_prices[symbol] = 0.0

        session = self.time.date()
        if not data.bars or session == self.last_session:
            return
        previous_session = self.last_session
        self.last_session = session
        self.session_index += 1
        self.sessions.append(session)

        daily_returns = {}
        for symbol in list(data.bars.keys()):
            window = self.closes.get(symbol)
            if window is None:
                window = deque(maxlen=LOOKBACK)
                self.closes[symbol] = window
                self.close_sessions[symbol] = deque(maxlen=LOOKBACK)
            close = float(data.bars[symbol].close)
            dates = self.close_sessions[symbol]
            if (previous_session is not None and window and dates
                    and dates[-1] == previous_session and window[-1] > 0):
                daily_returns[symbol] = close / window[-1] - 1.0
            window.append(close)
            self.close_sessions[symbol].append(session)

        self._record_market_return(daily_returns)
        self._settle_due_cohorts()

        # On the first session of a new month, the immediately preceding
        # exchange close is the prior month-end. Score strictly as of that
        # close (end_ago=1) and bind entry to today's close. This avoids
        # depending on LEAN callback ordering at the closing bell.
        if _is_new_calendar_month(previous_session, session):
            prior_month = (previous_session.year, previous_session.month)
            names = self.selection_history.get(prior_month, ())
            self._form_and_bind(names, previous_session)
        self._release_unused_retained()

    def _record_market_return(self, daily_returns):
        """Record the PIT equal-weight universe return for this session."""
        values = [
            daily_returns[symbol]
            for symbol in self.selected
            if symbol in daily_returns
        ]
        # Do not insert a plausible zero when the factor is unavailable.
        # A missing date makes the later aligned factor window refuse.
        if len(values) >= MIN_NAMES:
            self.market_returns.append(sum(values) / len(values))
            self.market_return_sessions.append(self.last_session)

    def _form_and_bind(self, names, score_session):
        scores = self._form_scores(names, end_ago=1)
        if scores is None:
            return
        entry = {
            symbol: self._price(symbol, 0)
            for symbol in names
            if symbol not in self.terminal_prices and self._price(symbol, 0) is not None
        }
        if len(entry) < MIN_NAMES:
            return
        portfolios = {}
        for spec, spec_scores in scores.items():
            usable = [(value, symbol) for symbol, value in spec_scores.items()
                      if value is not None and math.isfinite(value) and symbol in entry]
            if len(usable) < MIN_NAMES:
                continue
            ranked = sorted(usable, key=lambda pair: pair[0], reverse=True)
            cut = max(1, int(round(len(ranked) * DECILE)))
            quint = max(1, int(round(len(ranked) * QUINTILE)))
            longs = [symbol for _, symbol in ranked[:cut]]
            shorts = [symbol for _, symbol in ranked[-cut:]]
            long20 = [symbol for _, symbol in ranked[:quint]]
            ls_weights = {symbol: 0.5 / len(longs) for symbol in longs}
            for symbol in shorts:
                ls_weights[symbol] = ls_weights.get(symbol, 0.0) - 0.5 / len(shorts)
            keys = (
                (spec, "long_short"),
                (spec, "long_only_10"),
                (spec, "long_only_20"),
            )
            targets = (
                ls_weights,
                {symbol: 1.0 / len(longs) for symbol in longs},
                {symbol: 1.0 / len(long20) for symbol in long20},
            )
            turns = tuple(self._rebalance_turnover(key, target)
                          for key, target in zip(keys, targets))
            if any(value is None for value in turns):
                continue
            for key, target in zip(keys, targets):
                self.previous_weights[key] = target
                self.previous_entries[key] = {
                    symbol: entry[symbol] for symbol in target
                }
            portfolios[spec] = {
                "longs": longs, "shorts": shorts, "long20": long20,
                "turnovers": turns,
            }
        if not portfolios:
            return
        self.cohorts.append({
            "scores": scores,
            "entry": entry,
            "date": str(score_session),
            "portfolios": portfolios,
            "entry_index": self.session_index,
        })

    def _rebalance_turnover(self, key, target):
        previous = self.previous_weights.get(key) or {}
        if not previous:
            return _drift_turnover({}, target, {})
        prior_entries = self.previous_entries.get(key) or {}
        outcomes = {}
        for symbol in previous:
            entry_price = prior_entries.get(symbol)
            now = self.terminal_prices.get(symbol, self._price(symbol, 0))
            if entry_price is None or entry_price <= 0 or now is None:
                return None
            outcomes[symbol] = now / entry_price - 1.0
        return _drift_turnover(previous, target, outcomes)

    def _price(self, symbol, ago):
        window = self.closes.get(symbol)
        dates = self.close_sessions.get(symbol)
        if window is None or dates is None:
            return None
        aligned = _aligned_price_tail(window, dates, self.sessions, 0, end_ago=ago)
        return None if aligned is None else aligned[0]

    def _returns(self, symbol, count, end_ago=0):
        window = self.closes.get(symbol)
        dates = self.close_sessions.get(symbol)
        if window is None or dates is None:
            return None
        values = _aligned_price_tail(window, dates, self.sessions, count, end_ago=end_ago)
        if values is None or any(value <= 0 for value in values):
            return None
        return [values[i + 1] / values[i] - 1.0
                for i in range(len(values) - 1)]

    def _h52_proximity(self, symbol, end_ago=0):
        """Aligned 52-week window, then the module-level pure score."""
        window = self.closes.get(symbol)
        dates = self.close_sessions.get(symbol)
        if window is None or dates is None or len(window) < H52_SESSIONS:
            return None
        prices = _aligned_price_tail(
            window, dates, self.sessions, H52_SESSIONS - 1, end_ago=end_ago
        )
        if prices is None or any(value <= 0 for value in prices):
            return None
        return _h52_score(prices)

    def _idio_vol(self, symbol, market, end_ago=0):
        """Delegates to the module-level pure function."""
        span = IDV_ESTIMATION_SESSIONS + IDV_FORMATION_SESSIONS
        stock = self._returns(symbol, span, end_ago=end_ago)
        if stock is None:
            return None
        return _idio_vol_score(stock, market,
                               IDV_ESTIMATION_SESSIONS, IDV_FORMATION_SESSIONS)

    def _form_scores(self, selected_names, end_ago=0):
        names = [symbol for symbol in selected_names
                 if len(self.closes.get(symbol, ())) >= H52_SESSIONS]
        if len(names) < MIN_NAMES:
            return None
        market = _aligned_observation_tail(
            self.market_returns,
            self.market_return_sessions,
            self.sessions,
            IDV_ESTIMATION_SESSIONS + IDV_FORMATION_SESSIONS,
            end_ago=end_ago,
        )
        if market is None:
            return None
        return {
            "REP_H52": {
                symbol: self._h52_proximity(symbol, end_ago=end_ago)
                for symbol in names
            },
            "REP_IDV": {
                symbol: self._idio_vol(symbol, market, end_ago=end_ago)
                for symbol in names
            },
        }

    def _settle_due_cohorts(self):
        remaining = []
        for cohort in self.cohorts:
            if _holding_period_complete(cohort["entry_index"], self.session_index):
                self._settle_cohort(cohort)
            else:
                remaining.append(cohort)
        self.cohorts = remaining

    def _settle_cohort(self, pending):
        """Score one cohort at its exact 21-session close."""
        outcomes = {}
        for symbol, entry_price in pending["entry"].items():
            now = self.terminal_prices.get(symbol, self._price(symbol, 0))
            if entry_price and now is not None and entry_price > 0:
                outcomes[symbol] = now / entry_price - 1.0
        if len(outcomes) < MIN_NAMES:
            return outcomes

        for spec, portfolio in pending["portfolios"].items():
            scores = pending["scores"][spec]
            pairs = [(v, outcomes[s]) for s, v in scores.items()
                     if v is not None and math.isfinite(v) and s in outcomes]
            if len(pairs) < MIN_NAMES:
                continue
            ic = _spearman(pairs)
            longs = portfolio["longs"]
            shorts = portfolio["shorts"]
            long20 = portfolio["long20"]
            if any(symbol not in outcomes for symbol in longs + shorts + long20):
                continue

            long_ret = sum(outcomes[s] for s in longs) / len(longs)
            short_ret = sum(outcomes[s] for s in shorts) / len(shorts)
            long20_ret = sum(outcomes[s] for s in long20) / len(long20)

            self.results.setdefault(spec, []).append(
                (pending["date"], ic, long_ret, short_ret, long20_ret,
                 portfolio["turnovers"][0], portfolio["turnovers"][1],
                 portfolio["turnovers"][2], len(pairs))
            )
        return outcomes

    def _release_unused_retained(self):
        needed = set()
        for cohort in self.cohorts:
            needed.update(cohort.get("entry", {}))
        for weights in self.previous_weights.values():
            needed.update(weights)
        for symbol in list(self.retained):
            if symbol not in needed and symbol not in self.in_universe:
                self.remove_security(symbol)
                self.retained.remove(symbol)

    def on_end_of_algorithm(self):
        self.log(f"=== ALPHA STAGE1 REPLICATIONS | universe={ACTIVE_UNIVERSE} ===")
        self.log(f"cap_rows={self.cap_rows} cap_fallback={self.cap_fallback} "
                 f"cap_missing={self.cap_missing}")

        # ONE LINE PER DATE, not per (spec, date). QuantConnect truncates
        # cloud backtest logs at roughly a thousand lines, and the first
        # run of this algorithm lost three of ten specifications to that
        # limit -- it would have been reported as "residual momentum
        # produced no data" when the data existed and the log ran out.
        # Packing by date makes the volume independent of spec count.
        # Spec INDEX rather than name, and five decimals rather than
        # eight. The limit is on total log volume, so shortening each line
        # is what buys back the lost dates: the packed-by-date version
        # still lost 7 of 142, which DATES| made visible.
        order = list(SPECIFICATIONS)
        missing = [spec for spec in order if spec not in self.results]
        if missing:
            self.error(f"INCOMPLETE|missing_specs={'|'.join(missing)}")
            return
        index_of = {spec: i for i, spec in enumerate(order)}
        by_date = {}
        for spec, rows in self.results.items():
            for date, ic, lr, sr, l20, turn_ls, turn_l10, turn_l20, n in rows:
                by_date.setdefault(date, []).append(
                    f"{index_of[spec]}~{'' if ic is None else round(ic, 5)}~"
                    f"{round(lr, 6)}~{round(sr, 6)}~{round(l20, 6)}~"
                    f"{round(turn_ls, 4)}~{round(turn_l10, 4)}~"
                    f"{round(turn_l20, 4)}~{n}"
                )
        self.log(f"SPECS|{'|'.join(order)}")
        self.log(f"DATES|{len(by_date)}")
        for date in sorted(by_date):
            # Date compressed to YYYYMM; the cadence is monthly.
            self.log(f"ROW|{date.replace('-', '')[:6]}|" + "|".join(by_date[date]))
        self.log(f"orders placed: {self.transactions.orders_count}")
