"""Equal-weight universe benchmark, one return series per universe.

Declared as a counted research look. It tests no alpha hypothesis, but it
DOES report performance, so claiming the inert exemption would be false
and the conservative classification is the correct one.

Why this exists: the single most valuable correction from the local work
was that a long-only decile Sharpe means nothing without the return of
simply holding the same universe. On the local data that comparison turned
a 35% CAGR "result" into market beta, and turned a 19.15% benchmark into
11.95% once the universe was built honestly. Every long-only number in the
QuantConnect battery needs the same line drawn under it.

Screens, window and cadence are identical to the batteries, so the series
is directly comparable rather than approximately so.
"""
from AlgorithmImports import *  # noqa: F403


ACTIVE_UNIVERSE = "B_core"
START = (2012, 1, 1)
END = (2024, 12, 31)

UNIVERSES = {
    "A_large": {"min_price": 5.0, "min_cap": 10_000_000_000.0, "min_adv": 25_000_000.0},
    "B_core": {"min_price": 5.0, "min_cap": 500_000_000.0, "min_adv": 5_000_000.0},
    "C_broad": {"min_price": 3.0, "min_cap": 100_000_000.0, "min_adv": 1_000_000.0},
}
MIN_NAMES = 30


class UniverseBenchmark(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(*START)
        self.SetEndDate(*END)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.AddUniverse(self._coarse, self._fine)
        self.selection_month = None
        self.scored_month = None
        self.selected = []
        self.closes = {}
        self.entry = {}
        self.rows = []

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
            cap = float(f.MarketCap or 0.0)
            if cap <= 0.0:
                try:
                    shares = float(f.CompanyProfile.SharesOutstanding or 0.0)
                except Exception:  # noqa: BLE001
                    shares = 0.0
                price = float(f.Price or 0.0)
                if shares > 0.0 and price > 0.0:
                    cap = shares * price
                else:
                    continue
            if cap >= self.screen["min_cap"]:
                chosen.append(f.Symbol)
        self.selected = chosen
        return chosen

    def OnData(self, data):
        # Mirrors the battery's proven structure: prices accumulate in a
        # window, and a month's return is measured against the entry price
        # recorded at the previous scoring. The first version kept a bare
        # `last_price` dict updated inside the monthly branch, and produced
        # DATES|0 on a run that processed 31.9 million data points -- a
        # silent empty result rather than an error. Reusing the code path
        # that is known to work is cheaper than debugging a second one.
        for symbol in list(data.Bars.Keys):
            self.closes[symbol] = float(data.Bars[symbol].Close)

        month = (self.Time.year, self.Time.month)
        if self.scored_month == month or self.selection_month != month:
            return
        self.scored_month = month

        if self.entry:
            rets = []
            for symbol, entry_price in self.entry.items():
                now = self.closes.get(symbol)
                if now and entry_price and entry_price > 0:
                    rets.append(now / entry_price - 1.0)
            if len(rets) >= MIN_NAMES:
                self.rows.append(
                    (str(self.Time.date()), sum(rets) / len(rets), len(rets)))
        self.entry = {s: self.closes[s] for s in self.selected if s in self.closes}

    def OnEndOfAlgorithm(self):
        self.Log(f"=== UNIVERSE BENCHMARK | universe={ACTIVE_UNIVERSE} ===")
        self.Log(f"DATES|{len(self.rows)}")
        for date, ret, n in self.rows:
            self.Log(f"BROW|{date.replace('-', '')[:6]}|{round(ret, 6)}|{n}")
        self.Log(f"orders placed: {self.Transactions.OrdersCount}")
