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

Two specifications, both monthly-formed and held 21 sessions:

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


def _aligned_price_tail(values, value_sessions, market_sessions, count):
    """Return ``count + 1`` prices only when every market date matches.

    Universe exits, halts and missing bars must not turn two non-adjacent
    observations into a one-session return merely because they are adjacent
    in a deque.
    """
    required = count + 1
    if count < 0 or required > len(values) or required > len(value_sessions):
        return None
    if required > len(market_sessions):
        return None
    sessions = list(value_sessions)[-required:]
    if sessions != list(market_sessions)[-required:]:
        return None
    return list(values)[-required:]


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

    def Initialize(self):
        self.SetStartDate(*START)
        self.SetEndDate(*END)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Adjusted
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.AddUniverse(self._coarse, self._fine)

        self.closes = {}            # Symbol -> deque of daily closes
        self.close_sessions = {}    # Symbol -> matching exchange sessions
        self.sessions = deque(maxlen=LOOKBACK)
        self.fundamentals = {}      # Symbol -> dict of latest known values
        self.industry = {}          # Symbol -> Morningstar industry code
        self.selected = []          # this month's eligible symbols
        self.pending = None         # scores awaiting their forward return
        self.staged = None          # scores waiting for close t+1 entry
        # Selection is keyed off the CALENDAR, not off OnData. The first
        # version gated selection on a flag that only OnData set, and
        # OnData needs securities, which needs selection: a deadlock that
        # ran to completion reporting cap_rows=0 rather than failing.
        self.selection_month = None
        self.scored_month = None
        self.last_session = None
        self.in_universe = set()
        self.retained = set()
        self.terminal_prices = {}

        self.cap_missing = 0
        self.cap_fallback = 0
        self.cap_rows = 0
        self.results = {}           # spec -> per-date IC/return/turnover rows
        self.previous_weights = {}  # (spec, construction) -> signed weights

    # --- universe ------------------------------------------------------

    def _coarse(self, coarse):
        if self.selection_month == (self.Time.year, self.Time.month):
            return Universe.Unchanged
        return [c.Symbol for c in coarse
                if c.HasFundamentalData
                and c.Price >= self.screen["min_price"]
                and c.DollarVolume >= self.screen["min_adv"]]

    def _fine(self, fine):
        if self.selection_month == (self.Time.year, self.Time.month):
            return Universe.Unchanged
        self.selection_month = (self.Time.year, self.Time.month)
        chosen = []
        for f in fine:
            self.cap_rows += 1
            cap = float(f.MarketCap or 0.0)
            if cap <= 0.0:
                # MarketCap == 0 is MISSING, not small. Reconstruct where
                # possible; count both outcomes so the excluded set is
                # never invisible.
                shares = 0.0
                try:
                    shares = float(f.CompanyProfile.SharesOutstanding or 0.0)
                except Exception:  # noqa: BLE001
                    shares = 0.0
                price = float(f.Price or 0.0)
                if shares > 0.0 and price > 0.0:
                    cap = shares * price
                    self.cap_fallback += 1
                else:
                    self.cap_missing += 1
                    continue
            if cap < self.screen["min_cap"]:
                continue
            self.industry[f.Symbol] = int(
                f.AssetClassification.MorningstarIndustryCode or 0
            )
            self.fundamentals[f.Symbol] = {
                "gross_profit": float(
                    f.FinancialStatements.IncomeStatement.GrossProfit.Value or 0.0),
                "assets": float(
                    f.FinancialStatements.BalanceSheet.TotalAssets.Value or 0.0),
                "debt": float(
                    f.FinancialStatements.BalanceSheet.TotalDebt.Value or 0.0),
                "fcf": float(
                    f.FinancialStatements.CashFlowStatement.FreeCashFlow.Value or 0.0),
                "roe": float(f.OperationRatios.ROE.Value or 0.0),
                "cap": cap,
            }
            chosen.append(f.Symbol)
        current = set(chosen)
        needed = set()
        if self.pending is not None:
            needed.update(self.pending.get("entry", {}))
        if self.staged is not None:
            needed.update(self.staged.get("names", ()))
        for symbol in self.in_universe - current:
            if symbol in needed and symbol not in self.retained:
                self.AddSecurity(symbol, Resolution.Daily)
                self.retained.add(symbol)
        self.in_universe = current
        self.selected = chosen
        return chosen

    # --- data ----------------------------------------------------------

    def OnData(self, data):
        for symbol, delisting in data.Delistings.items():
            if delisting.Type != DelistingType.Delisted:
                continue
            raw_price = getattr(delisting, "Price", None)
            if raw_price is None:
                raw_price = getattr(delisting, "Value", 0.0)
            try:
                self.terminal_prices[symbol] = max(0.0, float(raw_price))
            except (TypeError, ValueError):
                self.terminal_prices[symbol] = 0.0

        session = self.Time.date()
        if not data.Bars or session == self.last_session:
            return
        self.last_session = session
        self.sessions.append(session)

        for symbol in list(data.Bars.Keys):
            window = self.closes.get(symbol)
            if window is None:
                window = deque(maxlen=LOOKBACK)
                self.closes[symbol] = window
                self.close_sessions[symbol] = deque(maxlen=LOOKBACK)
            window.append(float(data.Bars[symbol].Close))
            self.close_sessions[symbol].append(session)

        if self.staged is not None and session > self.staged["score_session"]:
            self._bind_staged_entry()

        # Score once per month, after the day's bars have been recorded.
        # Settling first, then forming, gives a full month between a score
        # and the return it is judged against.
        month = (self.Time.year, self.Time.month)
        if self.scored_month != month and self.selection_month == month:
            self.scored_month = month
            self._form_scores()

    def _bind_staged_entry(self):
        staged = self.staged
        self.staged = None
        prior_outcomes = self._settle() if self.pending is not None else {}
        entry = {
            symbol: self._price(symbol, 0)
            for symbol in staged["names"]
            if symbol not in self.terminal_prices and self._price(symbol, 0) is not None
        }
        if len(entry) < MIN_NAMES:
            return
        portfolios = {}
        for spec, scores in staged["scores"].items():
            usable = [(value, symbol) for symbol, value in scores.items()
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
            turns = tuple(
                _drift_turnover(self.previous_weights.get(key) or {}, target, prior_outcomes)
                for key, target in zip(keys, targets)
            )
            if any(value is None for value in turns):
                continue
            for key, target in zip(keys, targets):
                self.previous_weights[key] = target
            portfolios[spec] = {
                "longs": longs, "shorts": shorts, "long20": long20,
                "turnovers": turns,
            }
        if not portfolios:
            return
        self.pending = {
            "scores": staged["scores"],
            "entry": entry,
            "date": staged["date"],
            "portfolios": portfolios,
        }

    def _price(self, symbol, ago):
        window = self.closes.get(symbol)
        dates = self.close_sessions.get(symbol)
        if window is None or dates is None:
            return None
        aligned = _aligned_price_tail(window, dates, self.sessions, ago)
        return None if aligned is None else aligned[0]

    def _returns(self, symbol, count):
        window = self.closes.get(symbol)
        dates = self.close_sessions.get(symbol)
        if window is None or dates is None:
            return None
        values = _aligned_price_tail(window, dates, self.sessions, count)
        if values is None or any(value <= 0 for value in values):
            return None
        return [values[i + 1] / values[i] - 1.0
                for i in range(len(values) - 1)]

    def _h52_proximity(self, symbol):
        """Aligned 52-week window, then the module-level pure score."""
        window = self.closes.get(symbol)
        dates = self.close_sessions.get(symbol)
        if window is None or dates is None or len(window) < H52_SESSIONS:
            return None
        prices = _aligned_price_tail(window, dates, self.sessions, H52_SESSIONS - 1)
        if prices is None or any(value <= 0 for value in prices):
            return None
        return _h52_score(prices)

    def _idio_vol(self, symbol, market):
        """Delegates to the module-level pure function."""
        span = IDV_ESTIMATION_SESSIONS + IDV_FORMATION_SESSIONS
        stock = self._returns(symbol, span)
        if stock is None:
            return None
        return _idio_vol_score(stock, market,
                               IDV_ESTIMATION_SESSIONS, IDV_FORMATION_SESSIONS)

    def _form_scores(self):
        names = [symbol for symbol in self.selected
                 if len(self.closes.get(symbol, ())) >= H52_SESSIONS]
        if len(names) < MIN_NAMES:
            return
        market = self._index_returns(
            names, IDV_ESTIMATION_SESSIONS + IDV_FORMATION_SESSIONS)
        scores = {
            "REP_H52": {symbol: self._h52_proximity(symbol) for symbol in names},
            "REP_IDV": {symbol: self._idio_vol(symbol, market) for symbol in names},
        }
        self.staged = {
            "scores": scores,
            "names": names,
            "score_session": self.Time.date(),
            "date": str(self.Time.date()),
        }

    def _index_returns(self, names, count):
        series = []
        for index in range(count):
            values = []
            for symbol in names:
                a = self._price(symbol, count - index)
                b = self._price(symbol, count - index - 1)
                if a and b and a > 0:
                    values.append(b / a - 1.0)
            series.append(sum(values) / len(values) if values else 0.0)
        return series

    def _settle(self):
        """Score last month's ranking against the realised return."""
        pending = self.pending
        self.pending = None
        outcomes = {}
        for symbol, entry_price in pending["entry"].items():
            now = self.terminal_prices.get(symbol, self._price(symbol, 0))
            if entry_price and now is not None and entry_price > 0:
                outcomes[symbol] = now / entry_price - 1.0
        if len(outcomes) < MIN_NAMES:
            self._release_unused_retained()
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
        self._release_unused_retained()
        return outcomes

    def _release_unused_retained(self):
        needed = set(self.pending.get("entry", {})) if self.pending else set()
        for symbol in list(self.retained):
            if symbol not in needed and symbol not in self.in_universe:
                self.RemoveSecurity(symbol)
                self.retained.remove(symbol)

    def OnEndOfAlgorithm(self):
        self.Log(f"=== ALPHA STAGE1 REPLICATIONS | universe={ACTIVE_UNIVERSE} ===")
        self.Log(f"cap_rows={self.cap_rows} cap_fallback={self.cap_fallback} "
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
            self.Error(f"INCOMPLETE|missing_specs={'|'.join(missing)}")
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
        self.Log(f"SPECS|{'|'.join(order)}")
        self.Log(f"DATES|{len(by_date)}")
        for date in sorted(by_date):
            # Date compressed to YYYYMM; the cadence is monthly.
            self.Log(f"ROW|{date.replace('-', '')[:6]}|" + "|".join(by_date[date]))
        self.Log(f"orders placed: {self.Transactions.OrdersCount}")
