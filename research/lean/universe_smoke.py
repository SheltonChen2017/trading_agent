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
# can diff these against docs/research/ALPHA_BATTERY_2026-08-16_UNIVERSE_PREREGISTRATION.md
UNIVERSES = {
    "A_large": {"min_price": 5.0, "min_cap": 10_000_000_000.0, "min_adv": 25_000_000.0},
    "B_core": {"min_price": 5.0, "min_cap": 500_000_000.0, "min_adv": 5_000_000.0},
    "C_broad": {"min_price": 3.0, "min_cap": 100_000_000.0, "min_adv": 1_000_000.0},
}

# Which screen this run reports in detail. One universe per run keeps each
# run's purpose single and its log readable.
ACTIVE_UNIVERSE = "B_core"

# The window, declared HERE rather than patched into the source at upload
# time. Run 3 of 2026-08-16 was produced by the driver rewriting the dates
# in flight, which left the committed file saying 2013-2016 while the run
# that produced the "11 delistings" number used 2022-2023 -- reproducible,
# but not self-documenting, and a reader comparing the doc to the file
# would have found a mismatch with no way to tell which was right.
START = (2013, 1, 1)
END = (2016, 12, 31)


class UniverseSmokeTest(QCAlgorithm):
    """Counts and field checks only. Places no orders, ever."""

    def initialize(self):
        # A span that CONTAINS known failures. 2013-2016 is where the local
        # dataset lost 65.5% of its filers, and SVB/SBNY/FRC all failed in
        # March 2023, so a later run over 2022-2024 should show delistings
        # if the Security Master is doing its job.
        self.set_start_date(*START)
        self.set_end_date(*END)
        self.set_cash(100_000)

        self.universe_settings.resolution = Resolution.DAILY
        # Raw prices for the screen: the specification's price filter is
        # about the TRADED price, and split-adjusted history would let a
        # penny stock pass a $5 screen it never met at the time.
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW

        self.add_universe(self._coarse_filter, self._fine_filter)

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
            if c.has_fundamental_data
            and c.price >= self._screen["min_price"]
            and c.dollar_volume >= self._screen["min_adv"]
        ]
        # Sorted for determinism only. No ranking, no signal.
        return [c.symbol for c in sorted(eligible, key=lambda c: c.symbol.value)]

    def _fine_filter(self, fine):
        """Point-in-time market-cap screen, and the field checks."""
        selected = []
        for f in fine:
            cap = f.market_cap
            if not cap:
                self._missing_cap += 1
                continue
            # Industry classification, the field whose absence voided the
            # industry-adjusted specification locally.
            if not f.asset_classification.morningstar_industry_code:
                self._missing_industry += 1
            if cap >= self._screen["min_cap"]:
                selected.append(f.symbol)

        self._selection_count += 1
        self._member_counts.append(len(selected))
        if self._selection_count % 12 == 1:
            self.log(
                f"[universe] {self.time.date()} {ACTIVE_UNIVERSE} "
                f"members={len(selected)} "
                f"missing_cap={self._missing_cap} "
                f"missing_industry={self._missing_industry}"
            )
        return selected

    # --- delisting evidence -----------------------------------------------

    def on_data(self, data):
        """Records delistings. Places no orders.

        This is the whole point of the exercise: the local dataset could
        not price a delisted company at all, so a survivorship-affected
        universe was the binding constraint on every result so far. A
        non-zero count here is the evidence that the cloud dataset does not
        share that hole.
        """
        for symbol, delisting in data.delistings.items():
            if delisting.type == DelistingType.DELISTED:
                self._delistings += 1
                self.log(f"[delisting] {self.time.date()} {symbol.value}")

    def on_end_of_algorithm(self):
        counts = self._member_counts or [0]
        self.log("=== UNIVERSE SMOKE TEST — NO ALPHA STATISTIC REPORTED ===")
        self.log(f"universe screen        : {ACTIVE_UNIVERSE} {self._screen}")
        self.log(f"coarse selections      : {self._coarse_seen}")
        self.log(f"fine selections        : {self._selection_count}")
        self.log(f"members min/median/max : "
                 f"{min(counts)} / {sorted(counts)[len(counts) // 2]} / {max(counts)}")
        self.log(f"DELISTINGS OBSERVED    : {self._delistings}")
        self.log(f"rows missing market cap: {self._missing_cap}")
        self.log(f"rows missing industry  : {self._missing_industry}")
        self.log(f"orders placed          : {self.transactions.orders_count}")
        # If this is ever non-zero the file has stopped being a smoke test
        # and its run must be counted as a research look.
        if self.transactions.orders_count:
            self.error("SMOKE TEST PLACED ORDERS — this run is no longer exempt "
                       "from the Method V2 look count")
