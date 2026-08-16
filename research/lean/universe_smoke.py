"""LEAN universe smoke test — Method V2 step 4. NO ALPHA STATISTIC.

This algorithm exists to prove the DATA PLUMBING, and it is deliberately
built so that it cannot report an alpha result even by accident:

  * it never places an order, so there is no strategy return to quote;
  * it computes no signal, no rank, no IC and no Sharpe;
  * every line it logs is a count, a date, or a field-availability check.

Method V2 section 1.9 exempts a smoke test from the research look count
only if it is INCAPABLE of reporting an alpha statistic, not merely silent
about one. `SetHoldings`, `MarketOrder` and every other ordering call are
absent by construction; if a later edit adds one, this file stops being a
smoke test and its run becomes a counted look.

What it is actually checking, which is the list Method V2 section 2.1 says
must be demonstrated by the algorithm rather than assumed from the
platform:

  1. The universe is DYNAMIC and reconstructed per rebalance, not a
     hardcoded symbol list -- membership counts should change over time.
  2. Delisted securities are present in history and leave via a delisting
     event, which is the failure the local dataset could not fix (median
     70.2% of eligible SEC filers had no price series at all).
  3. Historical fundamentals are available AS OF the date, with market cap
     and industry classification populated -- the two fields whose absence
     void ALPHA 009/010/011 and the industry-adjusted specifications
     locally.
  4. The three universe screens (A/B/C) produce sane, distinct member
     counts under point-in-time market cap and dollar volume.

Run it in QuantConnect Cloud. Read the log. Nothing here is evidence about
any signal.
"""
from AlgorithmImports import *  # noqa: F403  (LEAN's documented entry point)


# The owner's 2026-08-16 specification, unchanged. Kept as data so a reader
# can diff these against docs/ALPHA_BATTERY_2026-08-16_UNIVERSE_PREREGISTRATION.md
UNIVERSES = {
    "A_large": {"min_price": 5.0, "min_cap": 10_000_000_000.0, "min_adv": 25_000_000.0},
    "B_core": {"min_price": 5.0, "min_cap": 500_000_000.0, "min_adv": 5_000_000.0},
    "C_broad": {"min_price": 3.0, "min_cap": 100_000_000.0, "min_adv": 1_000_000.0},
}

# Which screen this run reports in detail. One universe per run keeps each
# run's purpose single and its log readable.
ACTIVE_UNIVERSE = "B_core"


class UniverseSmokeTest(QCAlgorithm):
    """Counts and field checks only. Places no orders, ever."""

    def Initialize(self):
        # A span that CONTAINS known failures. 2013-2016 is where the local
        # dataset lost 65.5% of its filers, and SVB/SBNY/FRC all failed in
        # March 2023, so a later run over 2022-2024 should show delistings
        # if the Security Master is doing its job.
        self.SetStartDate(2013, 1, 1)
        self.SetEndDate(2016, 12, 31)
        self.SetCash(100_000)

        self.UniverseSettings.Resolution = Resolution.Daily
        # Raw prices for the screen: the specification's price filter is
        # about the TRADED price, and split-adjusted history would let a
        # penny stock pass a $5 screen it never met at the time.
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw

        self.AddUniverse(self._coarse_filter, self._fine_filter)

        self._screen = UNIVERSES[ACTIVE_UNIVERSE]
        self._coarse_seen = 0
        self._selection_count = 0
        self._delistings = 0
        self._missing_cap = 0
        self._missing_industry = 0
        self._member_counts = []

    # --- universe construction --------------------------------------------

    def _coarse_filter(self, coarse):
        """Price and dollar-volume screen, plus fundamentals availability.

        `HasFundamentalData` is the security-type filter: ETFs, ETNs,
        warrants, rights and units do not carry fundamentals, which is how
        the specification's exclusion list is honoured without a separate
        security master lookup.
        """
        self._coarse_seen += 1
        eligible = [
            c for c in coarse
            if c.HasFundamentalData
            and c.Price >= self._screen["min_price"]
            and c.DollarVolume >= self._screen["min_adv"]
        ]
        # Sorted for determinism only. No ranking, no signal.
        return [c.Symbol for c in sorted(eligible, key=lambda c: c.Symbol.Value)]

    def _fine_filter(self, fine):
        """Point-in-time market-cap screen, and the field checks."""
        selected = []
        for f in fine:
            cap = f.MarketCap
            if not cap:
                self._missing_cap += 1
                continue
            # Industry classification, the field whose absence voided the
            # industry-adjusted specification locally.
            if not f.AssetClassification.MorningstarIndustryCode:
                self._missing_industry += 1
            if cap >= self._screen["min_cap"]:
                selected.append(f.Symbol)

        self._selection_count += 1
        self._member_counts.append(len(selected))
        if self._selection_count % 12 == 1:
            self.Log(
                f"[universe] {self.Time.date()} {ACTIVE_UNIVERSE} "
                f"members={len(selected)} "
                f"missing_cap={self._missing_cap} "
                f"missing_industry={self._missing_industry}"
            )
        return selected

    # --- delisting evidence -----------------------------------------------

    def OnData(self, data):
        """Records delistings. Places no orders.

        This is the whole point of the exercise: the local dataset could
        not price a delisted company at all, so a survivorship-affected
        universe was the binding constraint on every result so far. A
        non-zero count here is the evidence that the cloud dataset does not
        share that hole.
        """
        for symbol, delisting in data.Delistings.items():
            if delisting.Type == DelistingType.Delisted:
                self._delistings += 1
                self.Log(f"[delisting] {self.Time.date()} {symbol.Value}")

    def OnEndOfAlgorithm(self):
        counts = self._member_counts or [0]
        self.Log("=== UNIVERSE SMOKE TEST — NO ALPHA STATISTIC REPORTED ===")
        self.Log(f"universe screen        : {ACTIVE_UNIVERSE} {self._screen}")
        self.Log(f"coarse selections      : {self._coarse_seen}")
        self.Log(f"fine selections        : {self._selection_count}")
        self.Log(f"members min/median/max : "
                 f"{min(counts)} / {sorted(counts)[len(counts) // 2]} / {max(counts)}")
        self.Log(f"DELISTINGS OBSERVED    : {self._delistings}")
        self.Log(f"rows missing market cap: {self._missing_cap}")
        self.Log(f"rows missing industry  : {self._missing_industry}")
        self.Log(f"orders placed          : {self.Transactions.OrdersCount}")
        # If this is ever non-zero the file has stopped being a smoke test
        # and its run must be counted as a research look.
        if self.Transactions.OrdersCount:
            self.Error("SMOKE TEST PLACED ORDERS — this run is no longer exempt "
                       "from the Method V2 look count")
