"""Prospective matched-run diagnostics; no orders or exported market rows.

The fixed source census includes every delivered constituent, not merely
selected/held names. Equality proves source snapshots and six-ETF daily RAW
closes, not equality of all stock or minute execution bars or realistic fills.
Universe tables describe construction/coverage, never realized sleeve P&L.
"""

from datetime import datetime, timedelta
from decimal import Decimal, localcontext
import hashlib

try:
    import accepted_risk_six_universe_order_qc_runtime as _base
except ImportError:
    from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as _base

SCHEMA = "arv2-matched-historical-diagnostics-v1"
STATISTIC_NAME = "ARV2_SIX_GATE_ORDER_DIAGNOSTICS"
MAXIMUM_STATISTIC_BYTES = 8192
MAXIMUM_PANEL_SYMBOLS = 2048
ANNUAL_FIELDS = ["year", "year_observation_count", "includes_previous_year_anchor",
    "first_observation_session", "last_observation_session", "cumulative_return",
    "maximum_drawdown", "annualized_volatility", "zero_rate_sharpe"]
UNIVERSE_FIELDS = ["year", "universe", "decision_count", "coverage_valid_count",
    "selected_count_sum", "post_cap_count_sum", "fallback_target_weight_sum"]


def _fail(message):
    raise _base.AcceptedRiskSixUniverseOrderQcRuntimeError(message)


def _history_rows(driver, symbols, first, last, sessions):
    """Bind each requested SID/session including explicit missing closes."""
    sid_map = {_base._symbol_sid(symbol, "matched panel symbol"): symbol for symbol in symbols}
    if not sid_map or len(sid_map) != len(symbols) or len(symbols) > MAXIMUM_PANEL_SYMBOLS:
        _fail("matched price panel symbol census changed")
    if type(sessions) is not tuple or len(set(sessions)) != len(sessions):
        _fail("matched price panel session census changed")
    try:
        history = driver._algorithm.history[driver._trade_bar_type](
            [sid_map[sid] for sid in sorted(sid_map)],
            datetime.strptime(first, "%Y-%m-%d"),
            datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1),
            driver._daily_resolution, fill_forward=False,
            extended_market_hours=False, data_normalization_mode=driver._raw_normalization,
        )
        values = {}
        for dictionary in history:
            session = dictionary.time.date().isoformat()
            if session not in sessions:
                _fail("matched price panel returned an extra session")
            for symbol, bar in dictionary.items():
                sid = _base._symbol_sid(symbol, "matched panel bar")
                key = (session, sid)
                if (sid not in sid_map or key in values
                        or _base._symbol_sid(bar.symbol, "matched panel payload") != sid
                        or bar.time.date().isoformat() != session):
                    _fail("matched price panel returned an extra or duplicate identity")
                values[key] = _base._decimal_text(_base._decimal(
                    bar.close, "matched RAW close", positive=True))
    except _base.AcceptedRiskSixUniverseOrderQcRuntimeError:
        raise
    except Exception as exc:
        raise _base.AcceptedRiskSixUniverseOrderQcRuntimeError("matched price panel history failed") from exc
    return [[session, sid, values.get((session, sid))]
            for session in sessions for sid in sorted(sid_map)]


def annual_accounts(observations):
    """The previous year's final close anchors each later calendar year."""
    if type(observations) is not dict or not observations:
        _fail("matched annual account path is empty")
    ordered = tuple(sorted(observations.items()))
    _base._population_metrics(ordered)
    years = tuple(sorted({session[:4] for session, _ in ordered}))
    result = []
    previous = None
    for year in years:
        rows = tuple((session, equity) for session, equity in ordered if session[:4] == year)
        path = rows if previous is None else (previous,) + rows
        metrics = _base._population_metrics(path)
        result.append({"year": year, "year_observation_count": len(rows),
                       "includes_previous_year_anchor": previous is not None, **metrics})
        previous = rows[-1]
    return result


def install_matched_diagnostics(driver, arm, slippage_bps):
    """Install only after the exact projected driver has initialized."""
    if getattr(driver, "_matched_diagnostics_state", None) is not None or driver._initialized is not True:
        _fail("matched diagnostics installation repeated or premature")
    if type(arm) is not str or arm not in ("ar_off", "ar_on100", "six_etf_basket") or type(slippage_bps) is not int or slippage_bps not in (0, 5):
        _fail("matched diagnostics arm or slippage changed")
    state = {"snapshot_hash": hashlib.sha256(), "sessions": [], "years": {}, "cached": None}
    driver._matched_diagnostics_state = state
    snapshot_method, sleeve_method, aggregate_method = driver._snapshot, driver._record_sleeve_diagnostics, driver._aggregate

    def snapshot(session):
        value = snapshot_method(session)
        if value.session != session or session not in driver._decision_set or session in state["sessions"]:
            _fail("matched diagnostics decision session repeated or unknown")
        records = []
        observed, raw_caps = driver._strictly_prior_rows(driver._fundamental_cache, session,
            "matched source fundamentals", maximum_age_sessions=_base.MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS,
            unavailable_as_empty=True)
        cap_records = [observed, [[sid, classification, None if cap is None else _base._decimal_text(cap)]
                                 for sid, classification, cap in raw_caps]]
        raw_members = []
        for ticker, cache in driver._constituent_caches.items():
            observed, raw_rows = driver._strictly_prior_rows(cache, session,
                "matched source constituents", maximum_age_sessions=_base.MAXIMUM_CONSTITUENT_SNAPSHOT_AGE_SESSIONS,
                unavailable_as_empty=True)
            raw_members.append([ticker, observed,
                [[sid, None if weight is None else _base._decimal_text(weight)] for sid, weight in raw_rows]])
        for universe in value.universes:
            members = []
            for row in universe.constituents:
                cap = row.pit_market_cap
                members.append([row.security_id, _base._decimal_text(row.reported_weight),
                                None if cap is None else _base._decimal_text(cap)])
            records.append([universe.universe_id, universe.etf_security_id,
                            sorted(members, key=_base._canonical)])
        state["snapshot_hash"].update(_base._canonical([session, cap_records, raw_members, records]) + b"\n")
        state["sessions"].append(session)
        return value

    def sleeves(rows):
        result = sleeve_method(rows)
        year = state["sessions"][-1][:4]
        for row in rows:
            key = (year, row.universe_id)
            record = state["years"].setdefault(key, [0, 0, 0, 0, Decimal(0)])
            record[0] += 1
            record[1] += int(row.coverage_valid)
            record[2] += len(row.selected_security_ids)
            record[3] += row.post_cap_stock_target_count
            record[4] += row.etf_target_weight
        return result

    def aggregate():
        value = aggregate_method()
        if state["cached"] is None:
            if tuple(state["sessions"]) != driver._decision_sessions:
                _fail("matched diagnostics decision path is incomplete")
            symbols = tuple(driver._etf_symbols.values())
            panel = _history_rows(driver, symbols, driver._evaluation_sessions[0],
                                  driver._evaluation_sessions[-1], driver._evaluation_sessions)
            if any(row[2] is None for row in panel):
                _fail("matched ETF benchmark panel is incomplete")
            yearly = annual_accounts(driver._account_observations)
            years = {session[:4] for session in driver._decision_sessions}
            universe_ids = tuple(driver._etf_symbols)
            if (set(state["years"]) != {(year, universe) for year in years for universe in universe_ids}
                    or any(record[0] != sum(session.startswith(year) for session in driver._decision_sessions)
                           for (year, _universe), record in state["years"].items())):
                _fail("matched year-universe census is incomplete")
            state["cached"] = {
                "schema": SCHEMA, "arm": arm, "slippage_bps_per_side": slippage_bps,
                "overall_cumulative_return": value["account"]["cumulative_return"],
                "annual_account_fields": ANNUAL_FIELDS,
                "annual_account_rows": [[row[field] for field in ANNUAL_FIELDS] for row in yearly],
                "membership_cap_path_sha256": state["snapshot_hash"].hexdigest(),
                "source_snapshot_count": len(state["sessions"]),
                "diagnostic_history_call_count": 1,
                "etf_daily_panel_sha256": _base._sha(panel),
                "six_etf_panel_row_count": len(panel),
                "year_universe_fields": UNIVERSE_FIELDS,
                "year_universe_rows": [[year, universe, *record[:4], _base._decimal_text(record[4])]
                    for (year, universe), record in sorted(state["years"].items())],
                "universe_realized_profit_attributed": False,
                "all_stock_price_equality_proved": False,
                "minute_execution_price_equality_proved": False,
                "daily_price_normalization": "RAW", "fill_forward": False,
            }
        text = _base._canonical(state["cached"]).decode("ascii")
        if len(text.encode("ascii")) > MAXIMUM_STATISTIC_BYTES:
            _fail("matched diagnostics exceeded its transport bound")
        driver._matched_diagnostics_statistic = text
        return value

    driver._snapshot, driver._record_sleeve_diagnostics, driver._aggregate = snapshot, sleeves, aggregate
    return True


def diagnostic_digest(driver):
    text = diagnostic_text(driver)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def diagnostic_text(driver):
    text = getattr(driver, "_matched_diagnostics_statistic", None)
    if type(text) is not str or not text or len(text.encode("ascii")) > MAXIMUM_STATISTIC_BYTES:
        _fail("matched diagnostics statistic is unavailable or oversized")
    return text


def validate_report(report, arm, slippage_bps):
    """Authenticate transport and fixed historical aggregate geometry."""
    if (type(arm) is not str or arm not in ("ar_off", "ar_on100", "six_etf_basket")
            or type(slippage_bps) is not int or slippage_bps not in (0, 5)):
        _fail("matched diagnostics expected arm or slippage changed")
    keys = {"schema", "arm", "slippage_bps_per_side", "overall_cumulative_return",
        "annual_account_fields", "annual_account_rows", "membership_cap_path_sha256",
        "source_snapshot_count", "diagnostic_history_call_count", "etf_daily_panel_sha256",
        "six_etf_panel_row_count", "year_universe_fields", "year_universe_rows",
        "universe_realized_profit_attributed", "all_stock_price_equality_proved",
        "minute_execution_price_equality_proved", "daily_price_normalization", "fill_forward"}
    if (type(report) is not dict or set(report) != keys or report["schema"] != SCHEMA
            or report["arm"] != arm or type(report["slippage_bps_per_side"]) is not int
            or report["slippage_bps_per_side"] != slippage_bps
            or len(_base._canonical(report)) > MAXIMUM_STATISTIC_BYTES):
        _fail("matched diagnostics schema, arm or transport changed")
    for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"):
        digest = report[key]
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            _fail("matched diagnostics digest changed")
    if (report["annual_account_fields"] != ANNUAL_FIELDS or report["year_universe_fields"] != UNIVERSE_FIELDS
            or type(report["source_snapshot_count"]) is not int or report["source_snapshot_count"] != 261
            or type(report["six_etf_panel_row_count"]) is not int or report["six_etf_panel_row_count"] != 7530
            or type(report["diagnostic_history_call_count"]) is not int or report["diagnostic_history_call_count"] != 1
            or any(report[key] is not False for key in ("universe_realized_profit_attributed",
                "all_stock_price_equality_proved", "minute_execution_price_equality_proved", "fill_forward"))
            or report["daily_price_normalization"] != "RAW"):
        _fail("matched diagnostics geometry or evidence boundary changed")
    annual = report["annual_account_rows"]
    if (type(annual) is not list or len(annual) != 5 or any(type(row) is not list or len(row) != 9 for row in annual)
            or [row[0] for row in annual] != [str(year) for year in range(2021, 2026)]
            or sum(row[1] for row in annual if type(row[1]) is int) != 1255):
        _fail("matched diagnostics annual census changed")
    growth = Decimal(1)
    with localcontext() as context:
        context.prec = 96
        for index, row in enumerate(annual):
            if (type(row[1]) is not int or row[1] < 2 or row[2] is not (index > 0)
                    or type(row[3]) is not str or type(row[4]) is not str
                    or row[4][:4] != row[0] or (index and row[3] != annual[index - 1][4])
                    or not index and row[3] != "2021-01-04"):
                _fail("matched diagnostics annual anchor changed")
            if any(type(row[pos]) is not str for pos in (5, 6, 7)) or row[8] is not None and type(row[8]) is not str:
                _fail("matched diagnostics annual metric type changed")
            values = [_base._decimal(row[pos], "matched annual metric") for pos in (5, 6, 7)]
            if values[0] <= -1 or not -1 < values[1] <= 0 or values[2] < 0:
                _fail("matched diagnostics annual metric bound changed")
            if row[8] is not None:
                _base._decimal(row[8], "matched annual Sharpe")
            growth *= 1 + values[0]
        if type(report["overall_cumulative_return"]) is not str:
            _fail("matched diagnostics overall return type changed")
        overall = _base._decimal(report["overall_cumulative_return"], "matched overall return")
        if annual[-1][4] != "2025-12-31" or abs(growth - 1 - overall) > Decimal("1e-90"):
            _fail("matched diagnostics annual returns do not compound")
    rows = report["year_universe_rows"]
    expected = {(str(year), universe) for year in range(2021, 2026) for universe in _base._gate.UNIVERSE_IDS}
    if (type(rows) is not list or len(rows) != 30 or any(type(row) is not list or len(row) != 7 for row in rows)
            or {(row[0], row[1]) for row in rows} != expected):
        _fail("matched diagnostics universe census changed")
    for row in rows:
        if any(type(row[pos]) is not int or row[pos] < 0 for pos in range(2, 6)) or row[3] > row[2]:
            _fail("matched diagnostics universe count changed")
        if type(row[6]) is not str:
            _fail("matched diagnostics fallback target type changed")
        weight = _base._decimal(row[6], "matched fallback target weight", nonnegative=True)
        if weight > Decimal(row[2]):
            _fail("matched diagnostics fallback target weight changed")
    if any(sum(row[2] for row in rows if row[1] == universe) != 261 for universe in _base._gate.UNIVERSE_IDS):
        _fail("matched diagnostics universe decision count changed")
    return True
