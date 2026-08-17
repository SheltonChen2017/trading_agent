"""Cadence-matched equal-weight benchmark for Stage 1 replications.

The cohort is the point-in-time universe selected for the score month. It is
entered at the next distinct session's adjusted close and exited exactly 21
sessions later, matching REP-H52 and REP-IDV. This is a counted research look,
but it is not an alpha cell.
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
HOLD_SESSIONS = 21


def _is_new_calendar_month(previous_session, current_session):
    if previous_session is None or current_session <= previous_session:
        return False
    return (previous_session.year, previous_session.month) != (
        current_session.year, current_session.month
    )


def _holding_period_complete(entry_index, current_index):
    return current_index - entry_index >= HOLD_SESSIONS


def _drift_turnover(previous, target, outcomes):
    if not previous:
        return 0.5 * sum(abs(weight) for weight in target.values())
    if any(symbol not in outcomes for symbol in previous):
        return None
    portfolio_return = sum(previous[symbol] * outcomes[symbol] for symbol in previous)
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


class AlphaStage1Benchmark(QCAlgorithm):

    def initialize(self):
        self.set_start_date(*START)
        self.set_end_date(*END)
        self.set_cash(100_000)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.ADJUSTED
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.add_universe(self._coarse, self._fine)

        self.selection_month = None
        self.selection_history = {}
        self.selected = []
        self.in_universe = set()
        self.retained = set()
        self.closes = {}
        self.close_sessions = {}
        self.terminal_prices = {}
        self.last_session = None
        self.session_index = -1
        self.cohorts = []
        self.previous_weights = {}
        self.previous_entries = {}
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
        needed = set(self.selected) | set(self.previous_weights)
        for cohort in self.cohorts:
            needed.update(cohort["entry"])
        for symbol in self.in_universe - current:
            if symbol in needed and symbol not in self.retained:
                self.add_security(symbol, Resolution.DAILY)
                self.retained.add(symbol)
        self.in_universe = current
        self.selected = chosen
        self.selection_history[self.selection_month] = tuple(chosen)
        if len(self.selection_history) > 3:
            for key in sorted(self.selection_history)[:-3]:
                self.selection_history.pop(key, None)
        return chosen

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
        for symbol in list(data.bars.keys()):
            self.closes[symbol] = float(data.bars[symbol].close)
            self.close_sessions[symbol] = session

        self._settle_due()
        if _is_new_calendar_month(previous_session, session):
            prior_month = (previous_session.year, previous_session.month)
            self._enter(self.selection_history.get(prior_month, ()), previous_session)
        self._release_unused_retained()

    def _enter(self, names, score_session):
        entry = {
            symbol: self.closes[symbol]
            for symbol in names
            if self.close_sessions.get(symbol) == self.last_session
            and symbol not in self.terminal_prices
        }
        if len(entry) < MIN_NAMES:
            return
        target = {symbol: 1.0 / len(entry) for symbol in entry}
        prior_outcomes = {}
        for symbol in self.previous_weights:
            start = self.previous_entries.get(symbol)
            if symbol in self.terminal_prices:
                now = self.terminal_prices[symbol]
            elif self.close_sessions.get(symbol) == self.last_session:
                now = self.closes.get(symbol)
            else:
                now = None
            if start is None or start <= 0 or now is None:
                return
            prior_outcomes[symbol] = now / start - 1.0
        turnover = _drift_turnover(self.previous_weights, target, prior_outcomes)
        if turnover is None:
            return
        self.previous_weights = target
        self.previous_entries = {symbol: entry[symbol] for symbol in target}
        self.cohorts.append({
            "entry": entry,
            "date": str(score_session),
            "turnover": turnover,
            "entry_index": self.session_index,
        })

    def _settle_due(self):
        remaining = []
        for cohort in self.cohorts:
            if not _holding_period_complete(cohort["entry_index"], self.session_index):
                remaining.append(cohort)
                continue
            outcomes = {}
            for symbol, start in cohort["entry"].items():
                if symbol in self.terminal_prices:
                    now = self.terminal_prices[symbol]
                elif self.close_sessions.get(symbol) == self.last_session:
                    now = self.closes.get(symbol)
                else:
                    now = None
                if start > 0 and now is not None:
                    outcomes[symbol] = now / start - 1.0
            if len(outcomes) == len(cohort["entry"]) and len(outcomes) >= MIN_NAMES:
                self.rows.append((
                    cohort["date"],
                    sum(outcomes.values()) / len(outcomes),
                    cohort["turnover"],
                    len(outcomes),
                ))
        self.cohorts = remaining

    def _release_unused_retained(self):
        needed = set(self.previous_weights)
        for cohort in self.cohorts:
            needed.update(cohort["entry"])
        for symbol in list(self.retained):
            if symbol not in needed and symbol not in self.in_universe:
                self.remove_security(symbol)
                self.retained.remove(symbol)

    def on_end_of_algorithm(self):
        self.log(f"=== ALPHA STAGE1 BENCHMARK | universe={ACTIVE_UNIVERSE} ===")
        if not self.rows:
            self.error("INCOMPLETE|missing_benchmark_rows")
            return
        self.log(f"DATES|{len(self.rows)}")
        for date, ret, turnover, names in self.rows:
            self.log(
                f"BROW|{date.replace('-', '')[:6]}|{round(ret, 6)}|"
                f"{round(turnover, 4)}|{names}"
            )
        self.log(f"orders placed: {self.transactions.orders_count}")
