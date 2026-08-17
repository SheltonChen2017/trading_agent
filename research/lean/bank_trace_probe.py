"""LEAN bank-trace probe - why did the universe never see SIVB/SBNY/FRC?
NO ALPHA STATISTIC.

The retention probe raised total delistings from 11 to 88 and confirmed
that screens hide deaths, but SIVB, SBNY and FRC still never appeared --
not as in-universe delistings, not as retained ones. The direct probe
proved all three carry full bars and real delisting events in the same
window, so their absence is a UNIVERSE SELECTION question, not a data one.

This probe answers exactly one thing: at each selection, are these three
present in coarse, do they pass each screen, and with what values? If they
are absent from coarse entirely, the fault is upstream of every screen and
the alpha battery would silently exclude the most important failures.

Inert: no orders, no signal, no performance statistic.
"""
from AlgorithmImports import *  # noqa: F403

WATCH = {"SIVB", "SBNY", "FRC", "PACW"}
SCREEN = {"min_price": 5.0, "min_cap": 500_000_000.0, "min_adv": 5_000_000.0}


class BankTraceProbe(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2022, 6, 1)
        self.set_end_date(2023, 6, 30)
        self.set_cash(100_000)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self.add_universe(self._coarse, self._fine)
        self._coarse_hits = {}
        self._fine_hits = {}
        self._logged = 0

    def _coarse(self, coarse):
        passing = []
        for c in coarse:
            name = c.symbol.value
            if name in WATCH:
                self._coarse_hits[name] = self._coarse_hits.get(name, 0) + 1
                if self._logged < 60:
                    self._logged += 1
                    self.log(
                        f"[coarse] {self.time.date()} {name} "
                        f"price={c.price} dv={c.dollar_volume:.0f} "
                        f"fundamentals={c.has_fundamental_data}"
                    )
            if (c.has_fundamental_data and c.price >= SCREEN["min_price"]
                    and c.dollar_volume >= SCREEN["min_adv"]):
                passing.append(c.symbol)
        return passing

    def _fine(self, fine):
        selected = []
        for f in fine:
            name = f.symbol.value
            if name in WATCH:
                self._fine_hits[name] = self._fine_hits.get(name, 0) + 1
                self.log(f"[fine] {self.time.date()} {name} cap={f.market_cap}")
            if f.market_cap and f.market_cap >= SCREEN["min_cap"]:
                selected.append(f.symbol)
        return selected

    def on_end_of_algorithm(self):
        self.log("=== BANK TRACE PROBE - NO ALPHA STATISTIC REPORTED ===")
        for name in sorted(WATCH):
            self.log(f"  {name}: coarse_appearances={self._coarse_hits.get(name, 0)} "
                     f"fine_appearances={self._fine_hits.get(name, 0)}")
        self.log(f"orders placed: {self.transactions.orders_count}")
