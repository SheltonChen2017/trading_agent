"""LEAN allocation-policy family: four frozen ETF mixes, one costed log.

Frozen specification: `docs/Archive/Research/ALLOCATION_POLICY_2026-08-18_PREREGISTRATION.md`
(weights, window, gates — frozen 2026-08-18, before this file existed).
Implementation authority: `docs/Archive/Plans/ALLOCATION_POLICY_QC_PLAN.md`
(APQ-1). This algorithm REPORTS POLICY RETURNS, so every cloud run is a
counted research look. It is not an alpha cell family and does not touch
the closed cross-sectional program (A-002).

Task-specific semantics, stated because they differ from the batteries:

* FIXED instruments, no universe screen, and deliberately **no
  ACTIVE_UNIVERSE constant** — the Stage 0 driver's retargeter must have
  nothing to rewrite here (APQ-3 uploads this file's bytes unchanged).
* The bill sleeve is BIL, never Lean cash interest.
* Monthly cadence on month-end sessions. A month's return for a policy is
  the target-weight sum of member total returns between consecutive
  priced month-end closes (adjusted closes carry dividends — required
  for BIL).
* Refusal is UNION-wide and ALIGNED: if ANY of the five tickers is
  unpriceable on a month-end boundary, that boundary is refused for ALL
  FOUR policies — the four series must never diverge onto different
  date sets. A refused boundary makes both adjacent months unmeasurable
  (each needs the boundary close), and the next measured month's
  turnover is a DECLARED unavailability (empty field; the analyser
  charges the conservative full 1.0 one-way) because the drift state
  spans the gap.
* Completeness: refuse the whole run (INCOMPLETE, no rows) if fewer than
  MIN_MONTHS months were measured or the four policies' date sets differ.
"""
import math

from AlgorithmImports import *  # noqa: F403


START = (2022, 1, 1)
#: End of the frozen confirmatory window: the last complete US session on
#: or before this date (set_end_date + LEAN's calendar enforce "complete").
END = (2026, 8, 18)
#: Frozen bootstrap floor from the preregistration section 5.
MIN_MONTHS = 24
TICKERS = ("SPY", "BIL", "XLP", "XLV", "XLE")
#: Frozen percent weights (preregistration section 4). Sums are asserted
#: by tests; P3's energy satellite is a cap and a target: exactly 0.10.
POLICY_WEIGHTS = {
    "P0": {"SPY": 1.00},
    "P1": {"SPY": 0.40, "BIL": 0.60},
    "P2": {"SPY": 0.40, "BIL": 0.20, "XLP": 0.20, "XLV": 0.20},
    "P3": {"SPY": 0.35, "BIL": 0.55, "XLE": 0.10},
}
POLICY_ORDER = ("P0", "P1", "P2", "P3")


def _usable_close(value):
    """Positive finite close only. NaN/inf must refuse: `NaN <= 0` is
    False, so a positivity check alone would accept NaN and then crash
    or emit inf returns (preregistration section 3)."""
    return isinstance(value, float) and math.isfinite(value) and value > 0.0


def _is_new_calendar_month(previous_session, current_session):
    if previous_session is None or current_session <= previous_session:
        return False
    return (previous_session.year, previous_session.month) != (
        current_session.year, current_session.month
    )


def _drift_turnover(previous, target, outcomes):
    """One-way turnover from drifted prior weights to target — the same
    definition the reviewed universe benchmark uses."""
    if not previous:
        return 0.5 * sum(abs(weight) for weight in target.values())
    if any(symbol not in outcomes for symbol in previous):
        return None
    portfolio_return = sum(
        previous[symbol] * outcomes[symbol] for symbol in previous
    )
    denominator = 1.0 + portfolio_return
    if denominator <= 0.0:
        return None
    drifted = {
        symbol: weight * (1.0 + outcomes[symbol]) / denominator
        for symbol, weight in previous.items()
    }
    names = set(drifted) | set(target)
    return 0.5 * sum(
        abs(target.get(symbol, 0.0) - drifted.get(symbol, 0.0))
        for symbol in names
    )


def _member_returns(previous_closes, current_closes):
    """Per-ticker total returns between two priced boundaries, or None if
    any ticker is unpriceable at either end (union refusal)."""
    outcomes = {}
    for ticker in TICKERS:
        before = previous_closes.get(ticker)
        after = current_closes.get(ticker)
        usable = _usable_close(before) and _usable_close(after)
        if not usable:
            return None
        outcomes[ticker] = after / before - 1.0
    return outcomes


class AllocationPolicy(QCAlgorithm):

    def initialize(self):
        self.set_start_date(*START)
        self.set_end_date(*END)
        self.set_cash(100_000)
        for ticker in TICKERS:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
        self.closes = {}
        self.close_sessions = {}
        self.last_session = None
        #: closes at the last PRICED month-end boundary, or None before entry
        self.boundary_closes = None
        #: How the next measured month's turnover is priced: "entry" (the
        #: true first-entry cost, `_drift_turnover({} -> target)` = 0.5 per
        #: the reviewed definition), "stale" (a refused boundary broke the
        #: drift chain -> DECLARED unavailable, empty field, charged 1.0 at
        #: analysis), or "drift" (normal consecutive months).
        self.turnover_mode = "entry"
        #: The PRIOR measured month's member returns: month M's row carries
        #: the rebalance paid ENTERING M, i.e. the drift accumulated over
        #: M-1 — the reviewed universe-benchmark bind-time convention.
        self.previous_outcomes = None
        #: rows: (YYYYMM date, policy, ret, turnover-or-None, priced, targeted)
        self.rows = []

    def on_data(self, data):
        session = self.time.date()
        if not data.bars or session == self.last_session:
            return
        previous_session = self.last_session
        self.last_session = session
        # Settle the completed month BEFORE ingesting this session's bars:
        # the boundary is priced at the PREVIOUS session's closes, and
        # overwriting them first would make every boundary look unpriced
        # (each ticker's close_session would already read today).
        if _is_new_calendar_month(previous_session, session):
            self._month_boundary(previous_session)
        for symbol_key in list(data.bars.keys()):
            ticker = str(getattr(symbol_key, "value", symbol_key))
            self.closes[ticker] = float(data.bars[symbol_key].close)
            self.close_sessions[ticker] = session

    def _month_boundary(self, boundary_session):
        """previous_session was the completed month's last session."""
        current = {
            ticker: self.closes.get(ticker)
            for ticker in TICKERS
            if self.close_sessions.get(ticker) == boundary_session
        }
        if len(current) != len(TICKERS) or any(
            not _usable_close(value) for value in current.values()
        ):
            # Union refusal: one unpriceable ticker refuses the boundary
            # for every policy; both adjacent months become unmeasurable
            # and the drift chain breaks. Series stay ALIGNED.
            self.boundary_closes = None
            self.turnover_mode = "stale"
            self.previous_outcomes = None
            return
        if self.boundary_closes is None:
            # Entry (or re-entry after a refused boundary): no measurable
            # month ends here; the next boundary measures from these
            # closes. turnover_mode already says "entry" or "stale".
            self.boundary_closes = current
            return
        outcomes = _member_returns(self.boundary_closes, current)
        date_key = boundary_session.strftime("%Y%m")
        for policy in POLICY_ORDER:
            weights = POLICY_WEIGHTS[policy]
            policy_return = sum(
                weight * outcomes[ticker] for ticker, weight in weights.items()
            )
            if self.turnover_mode == "entry":
                turnover = _drift_turnover({}, weights, {})
            elif self.turnover_mode == "stale" or self.previous_outcomes is None:
                turnover = None
            else:
                turnover = _drift_turnover(
                    weights, weights, self.previous_outcomes
                )
            self.rows.append((
                date_key, policy, policy_return, turnover,
                len(weights), len(weights),
            ))
        self.boundary_closes = current
        self.previous_outcomes = outcomes
        self.turnover_mode = "drift"

    def on_end_of_algorithm(self):
        self.log("=== ALLOCATION POLICY | frozen 2026-08-18 family ===")
        dates_by_policy = {}
        for date_key, policy, _ret, _turn, _p, _t in self.rows:
            dates_by_policy.setdefault(policy, set()).add(date_key)
        date_sets = list(dates_by_policy.values())
        aligned = bool(date_sets) and all(
            date_set == date_sets[0] for date_set in date_sets
        )
        months = len(date_sets[0]) if date_sets else 0
        if (not aligned or months < MIN_MONTHS
                or set(dates_by_policy) != set(POLICY_ORDER)):
            self.error(
                "INCOMPLETE|policies="
                f"{','.join(sorted(dates_by_policy)) or 'none'}"
                f"|months={months}|aligned={aligned}"
                f"|required={MIN_MONTHS}"
            )
            return
        self.log("POLICIES|" + "|".join(POLICY_ORDER))
        self.log(f"DATES|{months}")
        for date_key, policy, ret, turnover, priced, targeted in sorted(
            self.rows, key=lambda row: (row[0], row[1])
        ):
            turn = "" if turnover is None else round(turnover, 4)
            self.log(
                f"PROW|{date_key}|{policy}|{round(ret, 6)}|{turn}|"
                f"{priced}|{targeted}"
            )
        self.log(f"orders placed: {self.transactions.orders_count}")
