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
    def Initialize(self):
        self.SetStartDate(2022, 6, 1)
        self.SetEndDate(2023, 6, 30)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw
        self.AddUniverse(self._coarse, self._fine)
        self._coarse_hits = {}
        self._fine_hits = {}
        self._logged = 0

    def _coarse(self, coarse):
        passing = []
        for c in coarse:
            name = c.Symbol.Value
            if name in WATCH:
                self._coarse_hits[name] = self._coarse_hits.get(name, 0) + 1
                if self._logged < 60:
                    self._logged += 1
                    self.Log(
                        f"[coarse] {self.Time.date()} {name} "
                        f"price={c.Price} dv={c.DollarVolume:.0f} "
                        f"fundamentals={c.HasFundamentalData}"
                    )
            if (c.HasFundamentalData and c.Price >= SCREEN["min_price"]
                    and c.DollarVolume >= SCREEN["min_adv"]):
                passing.append(c.Symbol)
        return passing

    def _fine(self, fine):
        selected = []
        for f in fine:
            name = f.Symbol.Value
            if name in WATCH:
                self._fine_hits[name] = self._fine_hits.get(name, 0) + 1
                self.Log(f"[fine] {self.Time.date()} {name} cap={f.MarketCap}")
            if f.MarketCap and f.MarketCap >= SCREEN["min_cap"]:
                selected.append(f.Symbol)
        return selected

    def OnEndOfAlgorithm(self):
        self.Log("=== BANK TRACE PROBE - NO ALPHA STATISTIC REPORTED ===")
        for name in sorted(WATCH):
            self.Log(f"  {name}: coarse_appearances={self._coarse_hits.get(name, 0)} "
                     f"fine_appearances={self._fine_hits.get(name, 0)}")
        self.Log(f"orders placed: {self.Transactions.OrdersCount}")
