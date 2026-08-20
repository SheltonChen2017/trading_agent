"""LEAN leveraged-threshold family: TQQQ take-profit rules, one costed log.

Frozen specification:
`docs/research/LEVERAGED_THRESHOLD_2026-08-19_PREREGISTRATION.md`
(owner-adopted as-is 2026-08-19, before this file existed). This
algorithm REPORTS SERIES RETURNS, so every cloud run is a counted
research look. Fixed instruments, no universe screen, and deliberately
NO ACTIVE_UNIVERSE constant (the driver uploads these bytes unchanged,
APQ-3 convention). Not an alpha cell family; A-002 untouched.

Task-specific semantics (stated because they differ from the batteries
and from the allocation-policy family):

* Seven aligned monthly series from adjusted daily closes: L0 = TQQQ
  buy-and-hold (the benchmark series), L1..L4 = the frozen take-profit
  variants, QREF/SREF = QQQ/SPY buy-and-hold references.
* The variant STATE MACHINE runs on DAILY closes: a trigger observed at
  a close executes at the NEXT session's close. Month-end re-entry
  (L1/L2) is a fill point, not a trigger: it fills AT the month-end
  close itself. Pullback re-entry (L3/L4) triggers at the first close
  at or below 90% of the sale fill and executes next close; if the
  pullback never comes the variant stays in cash — recorded, never
  patched.
* Monthly rows mark variant equity at month-end closes. Union refusal:
  if ANY of the three tickers is unpriceable at a boundary, that
  boundary is refused for ALL SEVEN series (aligned date sets); both
  adjacent months become unmeasurable, and the next measured month's
  turnover is a DECLARED unavailability (empty field, charged 1.0 at
  analysis) because event attribution spans the gap. The state machine
  itself keeps running — it is real state, not measurement.
* Turnover is one-way (0.5 x |weight change|): 0.5 per sale, 0.5 per
  re-entry, 0.5 entry charged to every series' first measured month.
* Every sale logs LSALE with entry/sale dates and the realized gain so
  the preregistered after-tax DESCRIPTIVE column is computable without
  re-observation.
* Log markers are LEV-specific (LEVSERIES/LEVDATES/LROW/LSALE) so no
  other family's frozen parser can misread this log.
"""
import math

from AlgorithmImports import *  # noqa: F403


START = (2011, 1, 3)
#: The frozen window end ("run date" at adoption; staying fixed if the
#: authorized run happens later keeps the window deterministic).
END = (2026, 8, 19)
#: Frozen floor from the preregistration section 6.
MIN_MONTHS = 120
TRADED = "TQQQ"
TICKERS = ("TQQQ", "QQQ", "SPY")
#: Frozen rule grid (preregistration section 3).
VARIANTS = {
    "L1": {"take_profit": 0.20, "reentry": "month_end"},
    "L2": {"take_profit": 0.40, "reentry": "month_end"},
    "L3": {"take_profit": 0.20, "reentry": "pullback"},
    "L4": {"take_profit": 0.40, "reentry": "pullback"},
}
PULLBACK = 0.10
SERIES_ORDER = ("L0", "L1", "L2", "L3", "L4", "QREF", "SREF")
#: One-way turnover of moving the whole book (0.5 x |1 - 0|).
EVENT_TURNOVER = 0.5


def _usable_close(value):
    """Positive finite close only. NaN/inf must refuse: `NaN <= 0` is
    False, so a positivity check alone would accept NaN."""
    return isinstance(value, float) and math.isfinite(value) and value > 0.0


def _is_new_calendar_month(previous_session, current_session):
    if previous_session is None or current_session <= previous_session:
        return False
    return (previous_session.year, previous_session.month) != (
        current_session.year, current_session.month
    )


def new_variant_state(entry_price, entry_session):
    """Invested from the first aligned close (preregistration: all four
    variants start invested at the first window close)."""
    return {
        "invested": True,
        "entry_fill": entry_price,
        "entry_session": entry_session,
        "equity_at_fill": 1.0,
        "equity": 1.0,
        "pending": None,
        "sale_fill": None,
        "await_month_end": False,
        "month_turnover": 0.0,
        "sales": [],
    }


def variant_equity(state, close):
    """Mark-to-close equity multiplier."""
    if state["invested"]:
        return state["equity_at_fill"] * close / state["entry_fill"]
    return state["equity"]


def advance_variant(state, spec, close, session):
    """One daily step at a USABLE close: execute yesterday's trigger at
    today's close, then evaluate today's triggers. Mutates state."""
    if state["pending"] == "sell":
        gain = close / state["entry_fill"] - 1.0
        state["equity"] = state["equity_at_fill"] * (1.0 + gain)
        state["invested"] = False
        state["sale_fill"] = close
        state["month_turnover"] += EVENT_TURNOVER
        state["sales"].append((state["entry_session"], session, gain))
        state["await_month_end"] = spec["reentry"] == "month_end"
        state["pending"] = None
    elif state["pending"] == "buy":
        state["invested"] = True
        state["entry_fill"] = close
        state["entry_session"] = session
        state["equity_at_fill"] = state["equity"]
        state["month_turnover"] += EVENT_TURNOVER
        state["pending"] = None
    if state["invested"]:
        if close >= state["entry_fill"] * (1.0 + spec["take_profit"]):
            state["pending"] = "sell"
    elif (spec["reentry"] == "pullback" and state["sale_fill"] is not None
            and close <= state["sale_fill"] * (1.0 - PULLBACK)):
        state["pending"] = "buy"


def reenter_at_month_end(state, close, session):
    """L1/L2 fill point: the month-end close itself, no next-close lag."""
    if state["await_month_end"] and not state["invested"]:
        state["invested"] = True
        state["entry_fill"] = close
        state["entry_session"] = session
        state["equity_at_fill"] = state["equity"]
        state["month_turnover"] += EVENT_TURNOVER
        state["await_month_end"] = False


class LeveragedThreshold(QCAlgorithm):

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
        self.variants = None
        #: buy-and-hold base closes for L0/QREF/SREF, set at the entry close
        self.base_closes = None
        #: equity marks at the last PRICED boundary, or None before entry
        #: and after a refused boundary
        self.previous_marks = None
        #: "entry" (first measured month, charge 0.5), "stale" (refused
        #: boundary broke attribution -> declared unavailable), "normal"
        self.turnover_mode = "entry"
        #: reference-series turnover accumulator (entry only; they never
        #: trade again) is implied by turnover_mode
        self.rows = []

    def on_data(self, data):
        session = self.time.date()
        if not data.bars or session == self.last_session:
            return
        previous_session = self.last_session
        self.last_session = session
        # Settle the completed month BEFORE ingesting this session's bars
        # (the boundary is priced at the PREVIOUS session's closes).
        if _is_new_calendar_month(previous_session, session):
            self._month_boundary(previous_session)
        for symbol_key in list(data.bars.keys()):
            ticker = str(getattr(symbol_key, "value", symbol_key))
            self.closes[ticker] = float(data.bars[symbol_key].close)
            self.close_sessions[ticker] = session
        self._daily_step(session)

    def _daily_step(self, session):
        close = self.closes.get(TRADED)
        if self.close_sessions.get(TRADED) != session or not _usable_close(close):
            return
        if self.variants is None:
            # Entry: the first session where ALL tickers are priced today.
            current = {
                ticker: self.closes.get(ticker)
                for ticker in TICKERS
                if self.close_sessions.get(ticker) == session
            }
            if len(current) != len(TICKERS) or any(
                not _usable_close(value) for value in current.values()
            ):
                return
            self.base_closes = current
            self.variants = {
                name: new_variant_state(current[TRADED], session)
                for name in VARIANTS
            }
            return
        for name, spec in VARIANTS.items():
            advance_variant(self.variants[name], spec, close, session)

    def _boundary_closes(self, boundary_session):
        current = {
            ticker: self.closes.get(ticker)
            for ticker in TICKERS
            if self.close_sessions.get(ticker) == boundary_session
        }
        if len(current) != len(TICKERS) or any(
            not _usable_close(value) for value in current.values()
        ):
            return None
        return current

    def _month_boundary(self, boundary_session):
        if self.variants is None:
            return
        current = self._boundary_closes(boundary_session)
        if current is None:
            # Union refusal: aligned for all seven series; attribution of
            # events across the gap is declared unavailable.
            self.previous_marks = None
            self.turnover_mode = "stale"
            return
        # L1/L2 month-end re-entry fills AT this boundary close, so its
        # turnover belongs to the month this boundary closes.
        for name, spec in VARIANTS.items():
            if spec["reentry"] == "month_end":
                reenter_at_month_end(
                    self.variants[name], current[TRADED], boundary_session
                )
        marks = {
            "L0": current[TRADED] / self.base_closes[TRADED],
            "QREF": current["QQQ"] / self.base_closes["QQQ"],
            "SREF": current["SPY"] / self.base_closes["SPY"],
        }
        for name in VARIANTS:
            marks[name] = variant_equity(self.variants[name], current[TRADED])
        if self.previous_marks is not None:
            date_key = boundary_session.strftime("%Y%m")
            for series in SERIES_ORDER:
                ret = marks[series] / self.previous_marks[series] - 1.0
                turnover = self._series_turnover(series)
                self.rows.append((date_key, series, ret, turnover, 1, 1))
            self.turnover_mode = "normal"
            # Accumulators reset ONLY when a row consumes them: events in
            # unmeasured gap months roll forward into the next measured
            # row (or are covered by its declared-unavailable 1.0 charge)
            # rather than being silently dropped. Over-charging is the
            # accepted failure direction; under-charging is not.
            for name in VARIANTS:
                self.variants[name]["month_turnover"] = 0.0
        self.previous_marks = marks

    def _series_turnover(self, series):
        if self.turnover_mode == "stale":
            return None
        entry = EVENT_TURNOVER if self.turnover_mode == "entry" else 0.0
        if series in VARIANTS:
            return entry + self.variants[series]["month_turnover"]
        return entry

    def on_end_of_algorithm(self):
        self.log("=== LEVERAGED THRESHOLD | frozen 2026-08-19 family ===")
        dates_by_series = {}
        for date_key, series, _r, _t, _p, _n in self.rows:
            dates_by_series.setdefault(series, set()).add(date_key)
        date_sets = list(dates_by_series.values())
        aligned = bool(date_sets) and all(
            date_set == date_sets[0] for date_set in date_sets
        )
        months = len(date_sets[0]) if date_sets else 0
        if (not aligned or months < MIN_MONTHS
                or set(dates_by_series) != set(SERIES_ORDER)):
            self.error(
                "INCOMPLETE|series="
                f"{','.join(sorted(dates_by_series)) or 'none'}"
                f"|months={months}|aligned={aligned}"
                f"|required={MIN_MONTHS}"
            )
            return
        self.log("LEVSERIES|" + "|".join(SERIES_ORDER))
        self.log(f"LEVDATES|{months}")
        for date_key, series, ret, turnover, priced, targeted in sorted(
            self.rows, key=lambda row: (row[0], row[1])
        ):
            turn = "" if turnover is None else round(turnover, 4)
            self.log(
                f"LROW|{date_key}|{series}|{round(ret, 6)}|{turn}|"
                f"{priced}|{targeted}"
            )
        for name in sorted(VARIANTS):
            for entry_session, sale_session, gain in self.variants[name]["sales"]:
                self.log(
                    f"LSALE|{name}|{entry_session.isoformat()}|"
                    f"{sale_session.isoformat()}|{round(gain, 6)}"
                )
        self.log(f"orders placed: {self.transactions.orders_count}")
