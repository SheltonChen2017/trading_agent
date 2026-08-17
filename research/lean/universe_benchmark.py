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

    def initialize(self):
        self.set_start_date(*START)
        self.set_end_date(*END)
        self.set_cash(100_000)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.ADJUSTED
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.add_universe(self._coarse, self._fine)
        self.selection_month = None
        self.scored_month = None
        self.selected = []
        self.closes = {}
        self.close_sessions = {}
        self.pending = None
        self.staged = None
        self.previous_weights = {}
        self.last_session = None
        self.in_universe = set()
        self.retained = set()
        self.terminal_prices = {}
        self.rows = []

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
            cap = float(f.market_cap or 0.0)
            if cap <= 0.0:
                try:
                    shares = float(f.company_profile.shares_outstanding or 0.0)
                except Exception:  # noqa: BLE001
                    shares = 0.0
                price = float(f.price or 0.0)
                if shares > 0.0 and price > 0.0:
                    cap = shares * price
                else:
                    continue
            if cap >= self.screen["min_cap"]:
                chosen.append(f.symbol)
        current = set(chosen)
        needed = set(self.pending.get("entry", {})) if self.pending else set()
        for symbol in self.in_universe - current:
            if symbol in needed and symbol not in self.retained:
                self.add_security(symbol, Resolution.DAILY)
                self.retained.add(symbol)
        self.in_universe = current
        self.selected = chosen
        return chosen

    def on_data(self, data):
        # Mirrors the battery's proven structure: prices accumulate in a
        # window, and a month's return is measured against the entry price
        # recorded at the previous scoring. The first version kept a bare
        # `last_price` dict updated inside the monthly branch, and produced
        # DATES|0 on a run that processed 31.9 million data points -- a
        # silent empty result rather than an error. Reusing the code path
        # that is known to work is cheaper than debugging a second one.
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
        self.last_session = session

        for symbol in list(data.bars.keys()):
            self.closes[symbol] = float(data.bars[symbol].close)
            self.close_sessions[symbol] = session

        if self.staged is not None and session > self.staged["score_session"]:
            self._bind_staged_entry()

        month = (self.time.year, self.time.month)
        if self.scored_month == month or self.selection_month != month:
            return
        self.scored_month = month

        names = [
            symbol for symbol in self.selected
            if self.close_sessions.get(symbol) == session
        ]
        if len(names) >= MIN_NAMES:
            self.staged = {
                "names": names,
                "date": str(self.time.date()),
                "score_session": self.time.date(),
            }

    def _bind_staged_entry(self):
        staged = self.staged
        self.staged = None
        prior_outcomes = self._settle() if self.pending is not None else {}
        entry = {
            symbol: self.closes[symbol]
            for symbol in staged["names"]
            if self.close_sessions.get(symbol) == self.last_session
            and symbol not in self.terminal_prices
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
            if symbol in self.terminal_prices:
                now = self.terminal_prices[symbol]
            elif self.close_sessions.get(symbol) == self.last_session:
                now = self.closes.get(symbol)
            else:
                now = None
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
                self.remove_security(symbol)
                self.retained.remove(symbol)

    def on_end_of_algorithm(self):
        self.log(f"=== UNIVERSE BENCHMARK | universe={ACTIVE_UNIVERSE} ===")
        self.log(f"DATES|{len(self.rows)}")
        for date, ret, turnover, n in self.rows:
            self.log(
                f"BROW|{date.replace('-', '')[:6]}|{round(ret, 6)}|"
                f"{round(turnover, 4)}|{n}"
            )
        self.log(f"orders placed: {self.transactions.orders_count}")
