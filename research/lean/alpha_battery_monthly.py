"""LEAN monthly alpha battery. Specifications frozen in
`docs/ALPHA_BATTERY_2026-08-16_QC_PREREGISTRATION.md`.

This algorithm REPORTS ALPHA STATISTICS, so unlike the smoke probes it is
NOT exempt: every run is a counted research look.

It computes cross-sectional scores, forward returns and per-date
statistics, and logs them. It deliberately does NOT compute significance:
Method V2 forbids fresh significance code, so the per-date series are
carried home and fed to the project's reviewed, tested bootstrap.

Design decisions that follow directly from the smoke findings:

  * `MarketCap == 0` is MISSING, never small. One row in five carries zero
    and every earlier screen read it as "below threshold". Where shares
    outstanding are available the cap is reconstructed, and BOTH the
    fallback rate and the still-missing rate are logged per rebalance.
  * Symbols only, never ticker strings: `AddEquity("BBBY")` resolved to
    Overstock because the ticker was reused.
  * Industry comes from `MorningstarIndustryCode`, which is 100% present.
    The local run's size-bucket proxy leaked future capitalization.
  * Universe price screens use the raw coarse/fine price fields. Return
    arithmetic uses adjusted trade bars so stock splits are not mistaken
    for investment losses.
  * A score is staged at close t and its entry is bound only on the next
    distinct daily session, as required by the frozen pre-registration.
  * A selected name is retained while it is part of a measured portfolio,
    and a terminal delisting price is used in that portfolio's outcome.
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

LOOKBACK = 520          # 252-session residual fit + 12-1 measure + 1m skip
MIN_NAMES = 30          # a cross-section below this is not a ranking
DECILE = 0.10
QUINTILE = 0.20
RESIDUAL_ESTIMATION_SESSIONS = 252
MOMENTUM_SKIP_SESSIONS = 21
RESIDUAL_MAX_RETURNS = (
    RESIDUAL_ESTIMATION_SESSIONS + 21 * (12 - 1) + MOMENTUM_SKIP_SESSIONS
)
SPECIFICATIONS = (
    "GROSS_PROFITABILITY", "MOM_12_1", "MOM_3_1", "MOM_6_1", "MOM_9_1",
    "MULTI_ALPHA_COMPOSITE", "QUALITY_COMPOSITE", "QUALITY_MOMENTUM",
    "RESIDUAL_MOM_12_1", "RESIDUAL_MOM_6_1",
)


def _zscore(values):
    """Winsorised z-score. Winsorising before standardising stops one
    extreme fundamental ratio from setting the scale for everyone."""
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if len(clean) < 3:
        return {}
    ordered = sorted(clean)
    lo = ordered[max(0, int(0.01 * len(ordered)))]
    hi = ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))]
    clipped = [min(max(v, lo), hi) for v in clean]
    mean = sum(clipped) / len(clipped)
    var = sum((v - mean) ** 2 for v in clipped) / max(1, len(clipped) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return {}
    return {"mean": mean, "sd": sd, "lo": lo, "hi": hi}


def _apply_z(value, stats):
    if not stats or value is None or not math.isfinite(value):
        return None
    clipped = min(max(value, stats["lo"]), stats["hi"])
    return (clipped - stats["mean"]) / stats["sd"]


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


def _aligned_observation_tail(values, value_sessions, market_sessions, count):
    """Return exactly ``count`` observations on the last market sessions."""
    if count <= 0 or count > len(values) or count > len(value_sessions):
        return None
    if count > len(market_sessions):
        return None
    sessions = list(value_sessions)[-count:]
    if sessions != list(market_sessions)[-count:]:
        return None
    return list(values)[-count:]


def _leave_one_out_peer_return(symbol, stock_return, membership, aggregates):
    """Compute one PIT industry factor observation or refuse it."""
    code = membership.get(symbol)
    aggregate = aggregates.get(code)
    if code is None or aggregate is None:
        return None
    total, size = aggregate
    if size < 3:
        return None
    return (total - stock_return) / (size - 1)


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


def _joint_residual_total(stock, market, industry, measurement_sessions=21):
    """Cumulate measurement-window residuals from one joint OLS fit.

    The intercept and both loadings are estimated on observations ending
    strictly before the measurement window.  The small closed-form solve
    keeps this helper usable inside a single-file LEAN upload.
    """
    if not (len(stock) == len(market) == len(industry)):
        return None
    split = len(stock) - measurement_sessions
    if split < 40 or measurement_sessions <= 0:
        return None
    y, m, i = stock[:split], market[:split], industry[:split]
    my, mm, mi = sum(y) / split, sum(m) / split, sum(i) / split
    var_m = sum((v - mm) ** 2 for v in m)
    var_i = sum((v - mi) ** 2 for v in i)
    cov_mi = sum((a - mm) * (b - mi) for a, b in zip(m, i))
    cov_ym = sum((a - my) * (b - mm) for a, b in zip(y, m))
    cov_yi = sum((a - my) * (b - mi) for a, b in zip(y, i))
    determinant = var_m * var_i - cov_mi * cov_mi
    if abs(determinant) <= 1e-18:
        return None
    beta_m = (cov_ym * var_i - cov_yi * cov_mi) / determinant
    beta_i = (cov_yi * var_m - cov_ym * cov_mi) / determinant
    alpha = my - beta_m * mm - beta_i * mi
    return sum(
        y_t - alpha - beta_m * m_t - beta_i * i_t
        for y_t, m_t, i_t in zip(stock[split:], market[split:], industry[split:])
    )


def _residual_momentum_total(
    stock,
    market,
    industry,
    months,
    estimation_sessions=RESIDUAL_ESTIMATION_SESSIONS,
    skip_sessions=MOMENTUM_SKIP_SESSIONS,
):
    """Return a true ``months-1`` residual-momentum score.

    The joint factor fit uses a fixed window ending before the formation
    period opens.  The formation period then runs from ``t-21*months``
    through ``t-21``; the most recent month is excluded rather than being
    mistaken for the measurement window.
    """
    measurement_sessions = 21 * (months - 1)
    required = estimation_sessions + measurement_sessions + skip_sessions
    if months <= 1 or estimation_sessions < 40 or skip_sessions < 0:
        return None
    if not (len(stock) == len(market) == len(industry)) or len(stock) < required:
        return None
    measurement_end = len(stock) - skip_sessions
    estimation_start = measurement_end - measurement_sessions - estimation_sessions
    return _joint_residual_total(
        stock[estimation_start:measurement_end],
        market[estimation_start:measurement_end],
        industry[estimation_start:measurement_end],
        measurement_sessions=measurement_sessions,
    )


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


class AlphaBatteryMonthly(QCAlgorithm):

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
        self.factor_sessions = deque(maxlen=LOOKBACK)
        self.market_returns = deque(maxlen=LOOKBACK)
        self.industry_aggregates = deque(maxlen=LOOKBACK)
        self.industry_membership = {}
        # Avoid shadowing QCAlgorithm.fundamentals, a framework member.
        self.fundamental_cache = {} # Symbol -> latest point-in-time values
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
        month_membership = {}
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
            self.industry[f.symbol] = int(
                f.asset_classification.morningstar_industry_code or 0
            )
            month_membership[f.symbol] = self.industry[f.symbol]
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
        needed = set()
        if self.pending is not None:
            needed.update(self.pending.get("entry", {}))
        if self.staged is not None:
            needed.update(self.staged.get("names", ()))
        for symbol in self.in_universe - current:
            if symbol in needed and symbol not in self.retained:
                self.add_security(symbol, Resolution.DAILY)
                self.retained.add(symbol)
        self.in_universe = current
        self.selected = chosen
        self.industry_membership[self.selection_month] = month_membership
        # The longest factor window is under two years. Keep a buffer while
        # bounding state in long cloud runs.
        for month in sorted(self.industry_membership)[:-30]:
            self.industry_membership.pop(month, None)
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

        self._record_factor_returns(session, daily_returns)

        if self.staged is not None and session > self.staged["score_session"]:
            self._bind_staged_entry()

        # Score once per month, after the day's bars have been recorded.
        # Settling first, then forming, gives a full month between a score
        # and the return it is judged against.
        month = (self.time.year, self.time.month)
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

    def _momentum(self, symbol, months):
        recent = self._price(symbol, 21)
        old = self._price(symbol, 21 * months)
        if not recent or not old or old <= 0:
            return None
        return recent / old - 1.0

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

    def _record_factor_returns(self, session, daily_returns):
        """Record one point-in-time market/industry factor observation.

        The previous implementation rebuilt two years of factor history at
        every rebalance using today's membership and industry label. That
        both leaked classifications backward and repeated an O(N^2) peer
        calculation. This prospective record is O(N) per session.
        """
        membership = self.industry_membership.get(
            (session.year, session.month), {}
        )
        returns = {
            symbol: daily_returns[symbol]
            for symbol in self.selected
            if symbol in membership and symbol in daily_returns
        }
        if len(returns) < MIN_NAMES:
            return
        buckets = {}
        for symbol, value in returns.items():
            code = membership[symbol]
            total, size = buckets.get(code, (0.0, 0))
            buckets[code] = (total + value, size + 1)
        self.factor_sessions.append(session)
        self.market_returns.append(sum(returns.values()) / len(returns))
        self.industry_aggregates.append(buckets)

    def _factor_returns(self, symbol, count):
        """Return aligned PIT market and leave-one-out industry factors."""
        stock = self._returns(symbol, count)
        market = _aligned_observation_tail(
            self.market_returns, self.factor_sessions, self.sessions, count
        )
        aggregates = _aligned_observation_tail(
            self.industry_aggregates, self.factor_sessions, self.sessions, count
        )
        if stock is None or market is None or aggregates is None:
            return None
        factor_sessions = list(self.factor_sessions)[-count:]
        industry = []
        for value, session, daily in zip(stock, factor_sessions, aggregates):
            membership = self.industry_membership.get(
                (session.year, session.month), {}
            )
            peer_return = _leave_one_out_peer_return(
                symbol, value, membership, daily
            )
            if peer_return is None:
                return None
            industry.append(peer_return)
        return market, industry

    def _residual_momentum(self, symbol, months):
        """Joint market+industry regression (Method V2 section 1.7).

        A fixed 252-session fit ends where the months-minus-one formation
        window begins.  The most recent 21 sessions are then skipped, just
        as they are for the raw 6-1 and 12-1 momentum specifications.
        """
        stock = self._returns(symbol, RESIDUAL_MAX_RETURNS)
        factors = self._factor_returns(symbol, RESIDUAL_MAX_RETURNS)
        if stock is None or factors is None:
            return None
        market, peers = factors
        if len(peers) != len(stock) or len(market) != len(stock):
            return None
        return _residual_momentum_total(stock, market, peers, months)

    def _form_scores(self):
        names = [s for s in self.selected if len(self.closes.get(s, ())) >= 260]
        if len(names) < MIN_NAMES:
            return

        raw = {}
        for months in (3, 6, 9, 12):
            raw[f"MOM_{months}_1"] = {s: self._momentum(s, months) for s in names}
        for months in (6, 12):
            raw[f"RESIDUAL_MOM_{months}_1"] = {
                s: self._residual_momentum(s, months)
                for s in names
            }
        gp = {}
        quality = {}
        for symbol in names:
            f = self.fundamental_cache.get(symbol)
            if not f or f["assets"] <= 0:
                gp[symbol] = None
                quality[symbol] = None
                continue
            gp[symbol] = f["gross_profit"] / f["assets"]
            quality[symbol] = (f["roe"], f["fcf"] / f["assets"], f["debt"] / f["assets"])
        raw["GROSS_PROFITABILITY"] = gp

        roe_z = _zscore([q[0] for q in quality.values() if q])
        fcf_z = _zscore([q[1] for q in quality.values() if q])
        debt_z = _zscore([q[2] for q in quality.values() if q])
        composite = {}
        for symbol, q in quality.items():
            if not q:
                composite[symbol] = None
                continue
            parts = [_apply_z(q[0], roe_z), _apply_z(q[1], fcf_z), _apply_z(q[2], debt_z)]
            if any(p is None for p in parts):
                composite[symbol] = None
                continue
            composite[symbol] = parts[0] + parts[1] - parts[2]
        raw["QUALITY_COMPOSITE"] = composite

        mom_z = _zscore([v for v in raw["MOM_12_1"].values() if v is not None])
        qual_z = _zscore([v for v in composite.values() if v is not None])
        qm = {}
        for symbol in names:
            a = _apply_z(raw["MOM_12_1"].get(symbol), mom_z)
            b = _apply_z(composite.get(symbol), qual_z)
            qm[symbol] = None if a is None or b is None else a + b
        raw["QUALITY_MOMENTUM"] = qm

        legs = ("MOM_12_1", "RESIDUAL_MOM_12_1", "GROSS_PROFITABILITY", "QUALITY_COMPOSITE")
        leg_z = {leg: _zscore([v for v in raw[leg].values() if v is not None])
                 for leg in legs}
        multi = {}
        for symbol in names:
            parts = [_apply_z(raw[leg].get(symbol), leg_z[leg]) for leg in legs]
            multi[symbol] = None if any(p is None for p in parts) else sum(parts) / len(parts)
        raw["MULTI_ALPHA_COMPOSITE"] = multi

        self.staged = {
            "scores": raw,
            "names": names,
            "date": str(self.time.date()),
            "score_session": self.time.date(),
        }

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
                self.remove_security(symbol)
                self.retained.remove(symbol)

    def on_end_of_algorithm(self):
        self.log(f"=== ALPHA BATTERY MONTHLY | universe={ACTIVE_UNIVERSE} ===")
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
