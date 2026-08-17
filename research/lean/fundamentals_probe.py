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
    def initialize(self):
        self.set_start_date(*START)
        self.set_end_date(*END)
        self.set_cash(100_000)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self.add_universe(self._coarse, self._fine)
        self._rows = 0
        self._present = {}
        self._zero = {}
        self._selections = 0

    def _coarse(self, coarse):
        return [c.symbol for c in coarse
                if c.has_fundamental_data and c.price >= 5
                and c.dollar_volume >= 5_000_000][:900]

    def _fine(self, fine):
        self._selections += 1
        if self._selections % 6:            # sample; the counts are the point
            return []
        for f in fine:
            self._rows += 1
            probes = {
                "MarketCap": f.market_cap,
                "GrossProfit": f.financial_statements.income_statement.gross_profit.value,
                "TotalAssets": f.financial_statements.balance_sheet.total_assets.value,
                "TotalDebt": f.financial_statements.balance_sheet.total_debt.value,
                "NetIncome": f.financial_statements.income_statement.net_income.value,
                "FreeCashFlow": f.financial_statements.cash_flow_statement.free_cash_flow.value,
                "ROE": f.operation_ratios.roe.value,
                "ROA": f.operation_ratios.roa.value,
                "GrossMargin": f.operation_ratios.gross_margin.value,
                "TotalEquity": f.financial_statements.balance_sheet.total_equity_gross_minority_interest.value,
                "IndustryCode": f.asset_classification.morningstar_industry_code,
                "SectorCode": f.asset_classification.morningstar_sector_code,
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

    def on_end_of_algorithm(self):
        self.log("=== FUNDAMENTALS PROBE - NO ALPHA STATISTIC REPORTED ===")
        self.log(f"rows sampled: {self._rows}")
        for name in sorted(self._present):
            present = self._present[name]
            zero = self._zero.get(name, 0)
            self.log(
                f"  {name:22s} present={present:6d} "
                f"({100.0 * present / max(1, self._rows):5.1f}%)  "
                f"zero={zero:6d} ({100.0 * zero / max(1, present):5.1f}% of present)"
            )
        self.log(f"orders placed: {self.transactions.orders_count}")
