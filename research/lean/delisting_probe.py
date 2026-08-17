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

    def initialize(self):
        self.set_start_date(2022, 6, 1)
        self.set_end_date(2023, 12, 31)
        self.set_cash(100_000)
        self.universe_settings.resolution = Resolution.DAILY
        # Raw: a delisted name's adjusted history is exactly where
        # back-adjustment artifacts live, and the local run had to discard
        # 725 series for that reason.
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW

        self._bars = {}
        self._delisted = {}
        self._resolved = {}
        self._last_price = {}

        for ticker in list(DEAD_TICKERS) + [CONTROL_TICKER]:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                symbol = equity.symbol
                self._resolved[ticker] = str(symbol.id)
                self._bars[ticker] = 0
                self.log(f"[resolved] {ticker} -> {symbol.id}")
            except Exception as exc:  # noqa: BLE001 - recorded, never hidden
                self._resolved[ticker] = f"UNRESOLVED: {type(exc).__name__}"
                self.log(f"[unresolved] {ticker}: {exc}")

    def on_data(self, data):
        for ticker in self._bars:
            symbol_key = None
            for symbol in data.bars.keys():
                if symbol.value == ticker:
                    symbol_key = symbol
                    break
            if symbol_key is not None:
                self._bars[ticker] += 1
                self._last_price[ticker] = float(data.bars[symbol_key].close)

        for symbol, delisting in data.delistings.items():
            name = symbol.value
            self._delisted.setdefault(name, []).append(
                f"{self.time.date()}:{delisting.type}"
            )
            self.log(f"[delisting] {self.time.date()} {name} type={delisting.type}")

    def on_end_of_algorithm(self):
        self.log("=== DELISTING PROBE — NO ALPHA STATISTIC REPORTED ===")
        for ticker, note in DEAD_TICKERS.items():
            self.log(
                f"[dead] {ticker:6s} bars={self._bars.get(ticker, 0):5d} "
                f"last={self._last_price.get(ticker, 'none')} "
                f"delisting={self._delisted.get(ticker, 'NONE')} "
                f"id={self._resolved.get(ticker)}  ({note})"
            )
        self.log(
            f"[control] {CONTROL_TICKER} bars={self._bars.get(CONTROL_TICKER, 0)} "
            f"-- if this is 0 the probe is broken and the rest proves nothing"
        )
        self.log(f"orders placed: {self.transactions.orders_count}")
        if self.transactions.orders_count:
            self.error("PROBE PLACED ORDERS — no longer exempt from the look count")
