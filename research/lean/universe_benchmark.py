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


def _drift_turnover(previous, target, outcomes):
    if not previous:
        return 0.5 * sum(abs(weight) for weight in target.values())
    if any(symbol not in outcomes for symbol in previous):
        return None
    portfolio_return = sum(
        weight * outcomes[symbol] for symbol, weight in previous.items()
    )
    denominator = 1.0 + portfolio_return
    if denominator <= 0.0:
        return None
    drifted = {
        symbol: weight * (1.0 + outcomes[symbol]) / denominator
        for symbol, weight in previous.items()
    }
    names = set(drifted) | set(target)
    return 0.5 * sum(
        abs(target.get(symbol, 0.0) - drifted.get(symbol, 0.0))
        for symbol in names
    )


class UniverseBenchmark(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(*START)
        self.SetEndDate(*END)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Adjusted
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.AddUniverse(self._coarse, self._fine)
        self.selection_month = None
        self.scored_month = None
        self.selected = []
        self.closes = {}
        self.pending = None
        self.staged = None
        self.previous_weights = {}
        self.last_session = None
        self.in_universe = set()
        self.retained = set()
        self.terminal_prices = {}
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
        current = set(chosen)
        needed = set(self.pending.get("entry", {})) if self.pending else set()
        for symbol in self.in_universe - current:
            if symbol in needed and symbol not in self.retained:
                self.AddSecurity(symbol, Resolution.Daily)
                self.retained.add(symbol)
        self.in_universe = current
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
            self.closes[symbol] = float(data.Bars[symbol].Close)

        session = self.Time.date()
        if not data.Bars or session == self.last_session:
            return
        self.last_session = session

        if self.staged is not None and session > self.staged["score_session"]:
            self._bind_staged_entry()

        month = (self.Time.year, self.Time.month)
        if self.scored_month == month or self.selection_month != month:
            return
        self.scored_month = month

        names = [symbol for symbol in self.selected if symbol in self.closes]
        if len(names) >= MIN_NAMES:
            self.staged = {
                "names": names,
                "date": str(self.Time.date()),
                "score_session": self.Time.date(),
            }

    def _bind_staged_entry(self):
        staged = self.staged
        self.staged = None
        prior_outcomes = self._settle() if self.pending is not None else {}
        entry = {
            symbol: self.closes[symbol]
            for symbol in staged["names"]
            if symbol in self.closes and symbol not in self.terminal_prices
        }
        if len(entry) < MIN_NAMES:
            return
        weights = {symbol: 1.0 / len(entry) for symbol in entry}
        turnover = _drift_turnover(self.previous_weights, weights, prior_outcomes)
        if turnover is None:
            return
        self.previous_weights = weights
        self.pending = {
            "entry": entry,
            "date": staged["date"],
            "turnover": turnover,
        }

    def _settle(self):
        pending = self.pending
        self.pending = None
        outcomes = {}
        for symbol, entry_price in pending["entry"].items():
            now = self.terminal_prices.get(symbol, self.closes.get(symbol))
            if entry_price > 0 and now is not None:
                outcomes[symbol] = now / entry_price - 1.0
        if len(outcomes) == len(pending["entry"]) and len(outcomes) >= MIN_NAMES:
            self.rows.append((
                pending["date"],
                sum(outcomes.values()) / len(outcomes),
                pending["turnover"],
                len(outcomes),
            ))
        self._release_unused_retained()
        return outcomes

    def _release_unused_retained(self):
        needed = set(self.pending.get("entry", {})) if self.pending else set()
        for symbol in list(self.retained):
            if symbol not in needed and symbol not in self.in_universe:
                self.RemoveSecurity(symbol)
                self.retained.remove(symbol)

    def OnEndOfAlgorithm(self):
        self.Log(f"=== UNIVERSE BENCHMARK | universe={ACTIVE_UNIVERSE} ===")
        self.Log(f"DATES|{len(self.rows)}")
        for date, ret, turnover, n in self.rows:
            self.Log(
                f"BROW|{date.replace('-', '')[:6]}|{round(ret, 6)}|"
                f"{round(turnover, 4)}|{n}"
            )
        self.Log(f"orders placed: {self.Transactions.OrdersCount}")
