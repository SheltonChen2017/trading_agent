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

    def Initialize(self):
        # The window containing three large, fast bank failures.
        self.SetStartDate(2022, 6, 1)
        self.SetEndDate(2023, 12, 31)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw

        self.AddUniverse(self._coarse, self._fine)

        self._retained = {}          # Symbol -> date it left the universe
        self._delistings = []        # every delisting seen, retained or not
        self._delisted_after_exit = []
        self._in_universe = set()
        self._selections = 0

    def _coarse(self, coarse):
        return [
            c.Symbol for c in coarse
            if c.HasFundamentalData
            and c.Price >= SCREEN["min_price"]
            and c.DollarVolume >= SCREEN["min_adv"]
        ]

    def _fine(self, fine):
        self._selections += 1
        selected = [f.Symbol for f in fine
                    if f.MarketCap and f.MarketCap >= SCREEN["min_cap"]]
        current = set(selected)

        # The retention step. A name that just left the universe keeps its
        # subscription so its delisting can still be observed.
        for symbol in self._in_universe - current:
            if symbol not in self._retained:
                self._retained[symbol] = self.Time.date()
                # Re-add BY SYMBOL. A ticker string would resolve against
                # today's map and could return a different company.
                self.AddSecurity(symbol, Resolution.Daily)

        self._in_universe = current
        return selected

    def OnData(self, data):
        for symbol, delisting in data.Delistings.items():
            if delisting.Type != DelistingType.Delisted:
                continue
            left_on = self._retained.get(symbol)
            self._delistings.append(symbol.Value)
            if left_on is not None:
                self._delisted_after_exit.append((symbol.Value, str(left_on)))
                self.Log(
                    f"[retained-delisting] {self.Time.date()} {symbol.Value} "
                    f"left_universe={left_on}"
                )
            else:
                self.Log(f"[in-universe-delisting] {self.Time.date()} {symbol.Value}")

    def OnEndOfAlgorithm(self):
        self.Log("=== RETENTION PROBE - NO ALPHA STATISTIC REPORTED ===")
        self.Log(f"fine selections            : {self._selections}")
        self.Log(f"securities retained on exit: {len(self._retained)}")
        self.Log(f"TOTAL DELISTINGS OBSERVED  : {len(self._delistings)}")
        self.Log(f"  of which AFTER exiting   : {len(self._delisted_after_exit)}")
        # The three the screened run missed. Naming them makes the check
        # falsifiable rather than a count the reader must interpret.
        for wanted in ("SIVB", "SBNY", "FRC"):
            self.Log(f"  {wanted} observed: {wanted in self._delistings}")
        self.Log(f"orders placed              : {self.Transactions.OrdersCount}")
        if self.Transactions.OrdersCount:
            self.Error("PROBE PLACED ORDERS - no longer exempt from the look count")
