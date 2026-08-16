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

LOOKBACK = 300          # sessions retained per name; 12m momentum needs 253
MIN_NAMES = 30          # a cross-section below this is not a ranking
DECILE = 0.10
QUINTILE = 0.20
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

    def Initialize(self):
        self.SetStartDate(*START)
        self.SetEndDate(*END)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Adjusted
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.AddUniverse(self._coarse, self._fine)

        self.closes = {}            # Symbol -> deque of daily closes
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

        for symbol in list(data.Bars.Keys):
            window = self.closes.get(symbol)
            if window is None:
                window = deque(maxlen=LOOKBACK)
                self.closes[symbol] = window
            window.append(float(data.Bars[symbol].Close))

        session = self.Time.date()
        if not data.Bars or session == self.last_session:
            return
        self.last_session = session

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
        if window is None or len(window) <= ago:
            return None
        return window[len(window) - 1 - ago]

    def _momentum(self, symbol, months):
        recent = self._price(symbol, 21)
        old = self._price(symbol, 21 * months)
        if not recent or not old or old <= 0:
            return None
        return recent / old - 1.0

    def _returns(self, symbol, count):
        window = self.closes.get(symbol)
        if window is None or len(window) < count + 1:
            return None
        values = list(window)[-(count + 1):]
        return [values[i + 1] / values[i] - 1.0
                for i in range(len(values) - 1) if values[i] > 0]

    def _residual_momentum(self, symbol, months, market, industry_returns):
        """Joint market+industry regression (Method V2 section 1.7).

        Estimated on the window that ENDS where the measurement window
        begins, so no part of the estimation sees the period being scored.
        """
        span = 21 * months
        stock = self._returns(symbol, span)
        if stock is None or len(stock) < 60:
            return None
        peers = industry_returns.get(symbol)
        # The peer series is built over `count` sessions (260) while `stock`
        # spans 21*months (126 or 252), so a strict equality check can NEVER
        # hold and this returned None for every name on every date. The
        # corrected monthly run refused to emit at all, correctly, reporting
        # INCOMPLETE|missing_specs=MULTI_ALPHA_COMPOSITE|RESIDUAL_MOM_12_1|
        # RESIDUAL_MOM_6_1. Peers are sliced exactly as the market leg two
        # lines below already is.
        if peers is None or len(peers) < len(stock):
            return None
        peers = peers[-len(stock):]
        mkt = market[-len(stock):] if len(market) >= len(stock) else None
        if mkt is None:
            return None
        return _joint_residual_total(stock, mkt, peers, measurement_sessions=21)

    def _form_scores(self):
        names = [s for s in self.selected if len(self.closes.get(s, ())) >= 260]
        if len(names) < MIN_NAMES:
            return

        market = self._index_returns(names, 260)
        industry_returns = self._industry_returns(names, 260)

        raw = {}
        for months in (3, 6, 9, 12):
            raw[f"MOM_{months}_1"] = {s: self._momentum(s, months) for s in names}
        for months in (6, 12):
            raw[f"RESIDUAL_MOM_{months}_1"] = {
                s: self._residual_momentum(s, months, market, industry_returns)
                for s in names
            }
        gp = {}
        quality = {}
        for symbol in names:
            f = self.fundamentals.get(symbol)
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
            "date": str(self.Time.date()),
            "score_session": self.Time.date(),
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

    def _industry_returns(self, names, count):
        buckets = {}
        for symbol in names:
            buckets.setdefault(self.industry.get(symbol), []).append(symbol)
        out = {}
        for code, members in buckets.items():
            if len(members) < 3:
                continue
            for symbol in members:
                peers = [member for member in members if member != symbol]
                if len(peers) >= 2:
                    out[symbol] = self._index_returns(peers, count)
        return out

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
        self.Log(f"=== ALPHA BATTERY MONTHLY | universe={ACTIVE_UNIVERSE} ===")
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
