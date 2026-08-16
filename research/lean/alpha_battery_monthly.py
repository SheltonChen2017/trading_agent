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
  * Prices are raw, so a split-adjusted history cannot let a name pass a
    price screen it never met at the time.
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


class AlphaBatteryMonthly(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(*START)
        self.SetEndDate(*END)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.AddUniverse(self._coarse, self._fine)

        self.closes = {}            # Symbol -> deque of daily closes
        self.fundamentals = {}      # Symbol -> dict of latest known values
        self.industry = {}          # Symbol -> Morningstar industry code
        self.selected = []          # this month's eligible symbols
        self.pending = None         # scores awaiting their forward return
        self.rebalance_due = False
        self.month = -1

        self.cap_missing = 0
        self.cap_fallback = 0
        self.cap_rows = 0
        self.results = {}           # spec -> list of (date, ic, spread, turnover)
        self.previous_weights = {}  # spec -> {symbol: weight}

    # --- universe ------------------------------------------------------

    def _coarse(self, coarse):
        if not self.rebalance_due:
            return Universe.Unchanged
        return [c.Symbol for c in coarse
                if c.HasFundamentalData
                and c.Price >= self.screen["min_price"]
                and c.DollarVolume >= self.screen["min_adv"]]

    def _fine(self, fine):
        if not self.rebalance_due:
            return Universe.Unchanged
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
        self.selected = chosen
        return chosen

    # --- data ----------------------------------------------------------

    def OnData(self, data):
        for symbol in list(data.Bars.Keys):
            window = self.closes.get(symbol)
            if window is None:
                window = deque(maxlen=LOOKBACK)
                self.closes[symbol] = window
            window.append(float(data.Bars[symbol].Close))

        if self.Time.month != self.month:
            self.month = self.Time.month
            # Score LAST month's ranking against the return that followed,
            # then form this month's ranking. Entry lag is one session by
            # construction: scores use closes through yesterday.
            if self.pending is not None:
                self._settle()
            self.rebalance_due = True
            self.Schedule.On(self.DateRules.Today, self.TimeRules.BeforeMarketClose("SPY", 5),
                             self._form_scores)

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
        peers = industry_returns.get(self.industry.get(symbol))
        if peers is None or len(peers) != len(stock):
            peers = None
        mkt = market[-len(stock):] if len(market) >= len(stock) else None
        if mkt is None:
            return None
        # Estimation half, measurement half.
        split = 21
        est_stock, est_mkt = stock[:-split], mkt[:-split]
        if len(est_stock) < 40:
            return None
        beta_m = _ols(est_stock, est_mkt)
        beta_i = 0.0
        if peers is not None:
            est_peer = peers[:-split]
            resid = [s - beta_m * m for s, m in zip(est_stock, est_mkt)]
            peer_resid = [p - beta_m * m for p, m in zip(est_peer, est_mkt)]
            beta_i = _ols(resid, peer_resid)
        total = 0.0
        for index in range(len(stock) - split):
            expected = beta_m * mkt[index]
            if peers is not None:
                expected += beta_i * (peers[index] - beta_m * mkt[index])
            total += stock[index] - expected
        return total

    def _form_scores(self):
        self.rebalance_due = False
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

        entry = {s: self._price(s, 0) for s in names}
        self.pending = {"scores": raw, "entry": entry, "date": str(self.Time.date())}

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
            out[code] = self._index_returns(members, count)
        return out

    def _settle(self):
        """Score last month's ranking against the realised return."""
        pending = self.pending
        self.pending = None
        outcomes = {}
        for symbol, entry_price in pending["entry"].items():
            now = self._price(symbol, 0)
            if entry_price and now and entry_price > 0:
                outcomes[symbol] = now / entry_price - 1.0
        if len(outcomes) < MIN_NAMES:
            return

        for spec, scores in pending["scores"].items():
            pairs = [(v, outcomes[s]) for s, v in scores.items()
                     if v is not None and math.isfinite(v) and s in outcomes]
            if len(pairs) < MIN_NAMES:
                continue
            ic = _spearman(pairs)
            ranked = sorted(
                [(v, s) for s, v in scores.items()
                 if v is not None and math.isfinite(v) and s in outcomes],
                key=lambda p: p[0], reverse=True)
            cut = max(1, int(round(len(ranked) * DECILE)))
            longs = [s for _, s in ranked[:cut]]
            shorts = [s for _, s in ranked[-cut:]]
            quint = max(1, int(round(len(ranked) * QUINTILE)))
            long20 = [s for _, s in ranked[:quint]]

            long_ret = sum(outcomes[s] for s in longs) / len(longs)
            short_ret = sum(outcomes[s] for s in shorts) / len(shorts)
            long20_ret = sum(outcomes[s] for s in long20) / len(long20)

            weights = {s: 0.5 / len(longs) for s in longs}
            for s in shorts:
                weights[s] = weights.get(s, 0.0) - 0.5 / len(shorts)
            turnover = self._turnover(spec, weights, outcomes)

            self.results.setdefault(spec, []).append(
                (pending["date"], ic, long_ret, short_ret, long20_ret, turnover, len(pairs))
            )

    def _turnover(self, spec, weights, outcomes):
        """Drift-aware one-way turnover (Method V2 section 1.2)."""
        previous = self.previous_weights.get(spec) or {}
        self.previous_weights[spec] = weights
        if not previous:
            return 1.0
        grown = {}
        for symbol, weight in previous.items():
            grown[symbol] = weight * (1.0 + outcomes.get(symbol, 0.0))
        gross = sum(abs(v) for v in grown.values())
        target_gross = sum(abs(v) for v in previous.values()) or 1.0
        if gross > 0:
            grown = {s: v / gross * target_gross for s, v in grown.items()}
        names = set(grown) | set(weights)
        return 0.5 * sum(abs(weights.get(n, 0.0) - grown.get(n, 0.0)) for n in names)

    def OnEndOfAlgorithm(self):
        self.Log(f"=== ALPHA BATTERY MONTHLY | universe={ACTIVE_UNIVERSE} ===")
        self.Log(f"cap_rows={self.cap_rows} cap_fallback={self.cap_fallback} "
                 f"cap_missing={self.cap_missing}")
        for spec in sorted(self.results):
            for row in self.results[spec]:
                date, ic, lr, sr, l20, turn, n = row
                self.Log(
                    f"RESULT|{spec}|{date}|"
                    f"{'' if ic is None else round(ic, 6)}|"
                    f"{round(lr, 8)}|{round(sr, 8)}|{round(l20, 8)}|"
                    f"{round(turn, 6)}|{n}"
                )
        self.Log(f"orders placed: {self.Transactions.OrdersCount}")


def _ols(y, x):
    """Slope of y on x through the origin-adjusted means."""
    n = len(x)
    if n < 5:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = sum((a - mx) ** 2 for a in x)
    return 0.0 if den <= 0 else num / den
