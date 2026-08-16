"""LEAN delisting probe — Method V2 step 4, second smoke test. NO ALPHA.

The first smoke test observed ONE delisting across ~1,300 names over four
years, which is implausible: real delisting rates are several percent a
year. The likely mechanism is that a screened universe EJECTS a failing
company before it dies -- it falls under $5 and under $500M, leaves at the
next rebalance, and its delisting then fires while LEAN is no longer
subscribed. The screens create the blind spot, so a low count there is
evidence about the test, not about the data.

This probe removes the universe from the question entirely. It subscribes
DIRECTLY, by ticker, to companies known to have died, and reports whether
history and a delisting event exist for each. That is the claim the whole
QuantConnect argument rests on:

    the local dataset could not price a delisted company AT ALL
    (SIVB, FRC and SBNY all returned zero rows from yfinance)

If these resolve here with real bars and real delisting events, the cloud
dataset genuinely fixes the hole. If they do not, the survivorship
argument for moving is weaker than claimed and must be restated.

Inert by construction, same as the first probe: no orders, no signal, no
performance statistic. Only resolution, bar counts, and delisting events.
"""
from AlgorithmImports import *  # noqa: F403


#: Companies that died inside the window, with what killed them. Chosen
#: because the LOCAL dataset returned zero rows for the first three, which
#: is what made survivorship unfixable there.
DEAD_TICKERS = {
    "SIVB": "Silicon Valley Bank, failed 2023-03",
    "FRC": "First Republic, failed 2023-05",
    "SBNY": "Signature Bank, failed 2023-03",
    "BBBY": "Bed Bath & Beyond, bankrupt 2023-04",
    "CS": "Credit Suisse, acquired 2023-06",
}
#: A control that certainly survived. If this shows no bars either, the
#: probe itself is broken and the dead names prove nothing.
CONTROL_TICKER = "MSFT"


class DelistingProbe(QCAlgorithm):
    """Direct subscription to known-dead tickers. Places no orders."""

    def Initialize(self):
        self.SetStartDate(2022, 6, 1)
        self.SetEndDate(2023, 12, 31)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        # Raw: a delisted name's adjusted history is exactly where
        # back-adjustment artifacts live, and the local run had to discard
        # 725 series for that reason.
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw

        self._bars = {}
        self._delisted = {}
        self._resolved = {}
        self._last_price = {}

        for ticker in list(DEAD_TICKERS) + [CONTROL_TICKER]:
            try:
                equity = self.AddEquity(ticker, Resolution.Daily)
                symbol = equity.Symbol
                self._resolved[ticker] = str(symbol.ID)
                self._bars[ticker] = 0
                self.Log(f"[resolved] {ticker} -> {symbol.ID}")
            except Exception as exc:  # noqa: BLE001 - recorded, never hidden
                self._resolved[ticker] = f"UNRESOLVED: {type(exc).__name__}"
                self.Log(f"[unresolved] {ticker}: {exc}")

    def OnData(self, data):
        for ticker in self._bars:
            symbol_key = None
            for symbol in data.Bars.Keys:
                if symbol.Value == ticker:
                    symbol_key = symbol
                    break
            if symbol_key is not None:
                self._bars[ticker] += 1
                self._last_price[ticker] = float(data.Bars[symbol_key].Close)

        for symbol, delisting in data.Delistings.items():
            name = symbol.Value
            self._delisted.setdefault(name, []).append(
                f"{self.Time.date()}:{delisting.Type}"
            )
            self.Log(f"[delisting] {self.Time.date()} {name} type={delisting.Type}")

    def OnEndOfAlgorithm(self):
        self.Log("=== DELISTING PROBE — NO ALPHA STATISTIC REPORTED ===")
        for ticker, note in DEAD_TICKERS.items():
            self.Log(
                f"[dead] {ticker:6s} bars={self._bars.get(ticker, 0):5d} "
                f"last={self._last_price.get(ticker, 'none')} "
                f"delisting={self._delisted.get(ticker, 'NONE')} "
                f"id={self._resolved.get(ticker)}  ({note})"
            )
        self.Log(
            f"[control] {CONTROL_TICKER} bars={self._bars.get(CONTROL_TICKER, 0)} "
            f"-- if this is 0 the probe is broken and the rest proves nothing"
        )
        self.Log(f"orders placed: {self.Transactions.OrdersCount}")
        if self.Transactions.OrdersCount:
            self.Error("PROBE PLACED ORDERS — no longer exempt from the look count")
