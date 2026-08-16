"""LEAN fundamentals-availability probe. NO ALPHA STATISTIC.

Writing an alpha against a field that turns out to be absent is how three
specifications were refused locally and one was voided. This probe answers,
for the fields the remaining alphas need, TWO questions per field:

  * how often is it present at all, and
  * how often is it present but ZERO, which the bank-trace probe showed is
    a distinct and dangerous case -- FRC and SBNY carried MarketCap = 0 on
    every appearance, and a screen read that as "small" rather than
    "unknown".

Reports counts only. No signal, no ranking, no performance statistic.
"""
from AlgorithmImports import *  # noqa: F403

START = (2015, 1, 1)
END = (2016, 12, 31)


class FundamentalsProbe(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(*START)
        self.SetEndDate(*END)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw
        self.AddUniverse(self._coarse, self._fine)
        self._rows = 0
        self._present = {}
        self._zero = {}
        self._selections = 0

    def _coarse(self, coarse):
        return [c.Symbol for c in coarse
                if c.HasFundamentalData and c.Price >= 5 and c.DollarVolume >= 5_000_000][:900]

    def _fine(self, fine):
        self._selections += 1
        if self._selections % 6:            # sample; the counts are the point
            return []
        for f in fine:
            self._rows += 1
            probes = {
                "MarketCap": f.MarketCap,
                "GrossProfit": f.FinancialStatements.IncomeStatement.GrossProfit.Value,
                "TotalAssets": f.FinancialStatements.BalanceSheet.TotalAssets.Value,
                "TotalDebt": f.FinancialStatements.BalanceSheet.TotalDebt.Value,
                "NetIncome": f.FinancialStatements.IncomeStatement.NetIncome.Value,
                "FreeCashFlow": f.FinancialStatements.CashFlowStatement.FreeCashFlow.Value,
                "ROE": f.OperationRatios.ROE.Value,
                "ROA": f.OperationRatios.ROA.Value,
                "GrossMargin": f.OperationRatios.GrossMargin.Value,
                "TotalEquity": f.FinancialStatements.BalanceSheet.TotalEquityGrossMinorityInterest.Value,
                "IndustryCode": f.AssetClassification.MorningstarIndustryCode,
                "SectorCode": f.AssetClassification.MorningstarSectorCode,
            }
            for name, value in probes.items():
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                self._present[name] = self._present.get(name, 0) + 1
                if numeric == 0.0:
                    self._zero[name] = self._zero.get(name, 0) + 1
        return []

    def OnEndOfAlgorithm(self):
        self.Log("=== FUNDAMENTALS PROBE - NO ALPHA STATISTIC REPORTED ===")
        self.Log(f"rows sampled: {self._rows}")
        for name in sorted(self._present):
            present = self._present[name]
            zero = self._zero.get(name, 0)
            self.Log(
                f"  {name:22s} present={present:6d} "
                f"({100.0 * present / max(1, self._rows):5.1f}%)  "
                f"zero={zero:6d} ({100.0 * zero / max(1, present):5.1f}% of present)"
            )
        self.Log(f"orders placed: {self.Transactions.OrdersCount}")
