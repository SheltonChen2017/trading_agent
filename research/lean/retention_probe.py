"""LEAN retention probe — does keeping a subscription surface the deaths?
NO ALPHA STATISTIC.

The second smoke test found the important defect: a screened universe
reported 11 delistings over 2022-2023 and MISSED SIVB, SBNY and FRC, all
three of which the direct probe proved are in the dataset with delisting
events inside that window. A failing company breaks the price, market-cap
or ADV screen, leaves the universe at the next reconstruction, and its
delisting fires while the algorithm is no longer subscribed.

That is a strategy-construction artifact rather than a data defect, and it
matters because the window between "starts failing" and "delists" holds the
most extreme negative returns. Dropping names at the start of that window
understates what a short leg would have earned.

This probe tests the proposed remedy WITHOUT trading it: when a security
leaves the universe, its subscription is deliberately RETAINED instead of
dropped, and the probe reports how many delistings become visible as a
result. If retention surfaces the three banks, the remedy is confirmed
before any alpha code depends on it.

Retention is by `Symbol`, never by ticker string. The delisting probe found
that `AddEquity("BBBY")` resolves to Overstock's security id because the
ticker was reused, so ticker strings are banned in this directory.

Inert by construction: no orders, no signal, no performance statistic.
"""
from AlgorithmImports import *  # noqa: F403


SCREEN = {"min_price": 5.0, "min_cap": 500_000_000.0, "min_adv": 5_000_000.0}


class RetentionProbe(QCAlgorithm):
    """Universe with retained subscriptions. Places no orders."""

    def initialize(self):
        # The window containing three large, fast bank failures.
        self.set_start_date(2022, 6, 1)
        self.set_end_date(2023, 12, 31)
        self.set_cash(100_000)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW

        self.add_universe(self._coarse, self._fine)

        self._retained = {}          # Symbol -> date it left the universe
        self._delistings = []        # every delisting seen, retained or not
        self._delisted_after_exit = []
        self._in_universe = set()
        self._selections = 0

    def _coarse(self, coarse):
        return [
            c.symbol for c in coarse
            if c.has_fundamental_data
            and c.price >= SCREEN["min_price"]
            and c.dollar_volume >= SCREEN["min_adv"]
        ]

    def _fine(self, fine):
        self._selections += 1
        selected = [f.symbol for f in fine
                    if f.market_cap and f.market_cap >= SCREEN["min_cap"]]
        current = set(selected)

        # The retention step. A name that just left the universe keeps its
        # subscription so its delisting can still be observed.
        for symbol in self._in_universe - current:
            if symbol not in self._retained:
                self._retained[symbol] = self.time.date()
                # Re-add BY SYMBOL. A ticker string would resolve against
                # today's map and could return a different company.
                self.add_security(symbol, Resolution.DAILY)

        self._in_universe = current
        return selected

    def on_data(self, data):
        for symbol, delisting in data.delistings.items():
            if delisting.type != DelistingType.DELISTED:
                continue
            left_on = self._retained.get(symbol)
            self._delistings.append(symbol.value)
            if left_on is not None:
                self._delisted_after_exit.append((symbol.value, str(left_on)))
                self.log(
                    f"[retained-delisting] {self.time.date()} {symbol.value} "
                    f"left_universe={left_on}"
                )
            else:
                self.log(f"[in-universe-delisting] {self.time.date()} {symbol.value}")

    def on_end_of_algorithm(self):
        self.log("=== RETENTION PROBE - NO ALPHA STATISTIC REPORTED ===")
        self.log(f"fine selections            : {self._selections}")
        self.log(f"securities retained on exit: {len(self._retained)}")
        self.log(f"TOTAL DELISTINGS OBSERVED  : {len(self._delistings)}")
        self.log(f"  of which AFTER exiting   : {len(self._delisted_after_exit)}")
        # The three the screened run missed. Naming them makes the check
        # falsifiable rather than a count the reader must interpret.
        for wanted in ("SIVB", "SBNY", "FRC"):
            self.log(f"  {wanted} observed: {wanted in self._delistings}")
        self.log(f"orders placed              : {self.transactions.orders_count}")
        if self.transactions.orders_count:
            self.error("PROBE PLACED ORDERS - no longer exempt from the look count")
