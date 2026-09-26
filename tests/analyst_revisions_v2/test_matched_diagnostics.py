"""Offline behavioral coverage for the prospective matched-run sidecar."""

from datetime import datetime, timedelta
from decimal import Decimal, localcontext
import hashlib
from types import SimpleNamespace as NS, MethodType

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_matched_diagnostics as diag


class Symbol:
    def __init__(self, sid):
        self.id = sid


class History:
    def __init__(self, sessions, *, missing=False, duplicate=False):
        self.sessions = sessions
        self.calls = []
        self.missing = missing
        self.duplicate = duplicate

    def __getitem__(self, _kind):
        def read(symbols, first, last, resolution, **kwargs):
            self.calls.append((symbols, first, last, resolution, kwargs))
            result = []
            for index, session in enumerate(self.sessions):
                clock = datetime.strptime(session, "%Y-%m-%d")
                rows = [(symbol, NS(symbol=symbol, time=clock, close=Decimal(100 + index)))
                        for symbol in symbols]
                if self.missing:
                    rows.pop()
                if self.duplicate:
                    rows.append(rows[0])
                result.append(NS(time=clock, items=lambda rows=rows: rows))
            return result
        return read


def driver_fixture():
    sessions = tuple(item for year in range(2021, 2026)
                     for item in (f"{year}-01-04", f"{year}-12-31"))
    etfs = {name: Symbol("sid-" + name) for name in diag._base._gate.UNIVERSE_IDS}
    history = History(sessions)
    universes = tuple(NS(universe_id=name, etf_security_id=symbol.id,
        constituents=(NS(security_id="stock-" + name, reported_weight=Decimal("0.25"),
                         pit_market_cap=Decimal(1000), firm_specific_score=Decimal(3)),))
        for name, symbol in etfs.items())
    driver = NS(_initialized=True, _decision_sessions=sessions, _decision_set=set(sessions),
        _evaluation_sessions=sessions, _etf_symbols=etfs,
        _algorithm=NS(history=history), _trade_bar_type=object,
        _daily_resolution="Daily", _raw_normalization="Raw",
        _account_observations={session: Decimal(100 + index) for index, session in enumerate(sessions)})
    driver._snapshot = lambda session: NS(session=session, universes=universes)
    driver._record_sleeve_diagnostics = lambda rows: None
    driver._aggregate = lambda: {"account": diag._base._population_metrics(tuple(sorted(driver._account_observations.items())))}
    prior_dates = [(datetime.strptime(session, "%Y-%m-%d") - timedelta(days=1)).date().isoformat()
                   for session in sessions]
    driver._session_positions = {date: index * 2 for index, date in enumerate(prior_dates)}
    driver._session_positions.update({session: index * 2 + 1 for index, session in enumerate(sessions)})
    driver._fundamental_cache = {date: (("stock", "positive", Decimal(1000)),) for date in prior_dates}
    driver._constituent_caches = {ticker: {date: (("unknown-original-SID", Decimal("0.5")),)
                                                        for date in prior_dates} for ticker in etfs}
    driver._strictly_prior_rows = MethodType(diag._base.AcceptedRiskSixUniverseOrderQcDriver._strictly_prior_rows, driver)
    sleeves = tuple(NS(universe_id=name, coverage_valid=True, selected_security_ids=("stock",),
        post_cap_stock_target_count=1, etf_target_weight=Decimal("0.1")) for name in etfs)
    return driver, sleeves, universes


def populate(driver, sleeves):
    for session in driver._decision_sessions:
        driver._snapshot(session)
        driver._record_sleeve_diagnostics(sleeves)
    aggregate = driver._aggregate()
    return aggregate, driver._matched_diagnostics_state["cached"]


def valid_report():
    report = {"schema": diag.SCHEMA, "arm": "ar_off", "slippage_bps_per_side": 0,
        "overall_cumulative_return": "0", "annual_account_fields": diag.ANNUAL_FIELDS,
        "annual_account_rows": [[str(year), count, index > 0,
            "2021-01-04" if not index else f"{year-1}-12-31", f"{year}-12-31", "0", "0", "0", None]
            for index, (year, count) in enumerate(zip(range(2021, 2026), (252, 251, 250, 252, 250)))],
        "membership_cap_path_sha256": "a" * 64, "source_snapshot_count": 261,
        "diagnostic_history_call_count": 1, "etf_daily_panel_sha256": "b" * 64,
        "six_etf_panel_row_count": 7530, "year_universe_fields": diag.UNIVERSE_FIELDS,
        "year_universe_rows": [[str(year), universe, count, count, count * 10, count * 10, "0"]
            for year, count in zip(range(2021, 2026), (52, 52, 52, 52, 53))
            for universe in diag._base._gate.UNIVERSE_IDS],
        "universe_realized_profit_attributed": False, "all_stock_price_equality_proved": False,
        "minute_execution_price_equality_proved": False, "daily_price_normalization": "RAW", "fill_forward": False}
    return report


def test_year_boundary_uses_previous_final_close_and_compounds():
    rows = {"2021-01-04": Decimal(100), "2021-12-31": Decimal(110),
            "2022-01-03": Decimal(121), "2022-12-30": Decimal("133.1")}
    annual = diag.annual_accounts(rows)
    assert Decimal(annual[0]["cumulative_return"]) == Decimal("0.1")
    assert Decimal(annual[1]["cumulative_return"]) == Decimal("0.21")
    assert annual[1]["first_observation_session"] == "2021-12-31"
    assert annual[1]["year_observation_count"] == 2


def test_wrapper_preserves_aggregate_and_adds_only_one_terminal_history_call():
    driver, sleeves, _ = driver_fixture()
    diag.install_matched_diagnostics(driver, "ar_off", 0)
    aggregate, report = populate(driver, sleeves)
    assert set(aggregate) == {"account"}
    assert len(driver._algorithm.history.calls) == 1
    assert report["source_snapshot_count"] == len(driver._decision_sessions)
    assert report["all_stock_price_equality_proved"] is False
    assert report["universe_realized_profit_attributed"] is False
    assert len(report["year_universe_rows"]) == 30
    assert diag.diagnostic_digest(driver) == hashlib.sha256(diag.diagnostic_text(driver).encode("ascii")).hexdigest()
    driver._aggregate()
    assert len(driver._algorithm.history.calls) == 1
    assert driver._algorithm.history.calls[0][-1] == {
        "fill_forward": False, "extended_market_hours": False, "data_normalization_mode": "Raw"}


def test_membership_cap_digest_ignores_score_but_detects_cap_change():
    hashes = []
    for score, cap in ((3, 1000), (99, 1000), (99, 1001)):
        driver, sleeves, universes = driver_fixture()
        universes[0].constituents[0].firm_specific_score = Decimal(score)
        universes[0].constituents[0].pit_market_cap = Decimal(cap)
        diag.install_matched_diagnostics(driver, "ar_off", 0)
        hashes.append(populate(driver, sleeves)[1]["membership_cap_path_sha256"])
    assert hashes[0] == hashes[1]
    assert hashes[1] != hashes[2]


def test_unknown_raw_sid_change_is_not_collapsed_to_unresolved_logical_none():
    hashes = []
    for raw_sid in ("unknown-original-SID", "different-unknown-SID"):
        driver, sleeves, _ = driver_fixture()
        first = next(iter(driver._constituent_caches))
        driver._constituent_caches[first] = {date: ((raw_sid, Decimal("0.5")),)
            for date in driver._constituent_caches[first]}
        diag.install_matched_diagnostics(driver, "ar_off", 0)
        hashes.append(populate(driver, sleeves)[1]["membership_cap_path_sha256"])
    assert hashes[0] != hashes[1]


@pytest.mark.parametrize("bad", ("missing", "duplicate"))
def test_terminal_etf_panel_refuses_missing_or_duplicate(bad):
    driver, sleeves, _ = driver_fixture()
    setattr(driver._algorithm.history, bad, True)
    diag.install_matched_diagnostics(driver, "ar_off", 0)
    with pytest.raises(diag._base.AcceptedRiskSixUniverseOrderQcRuntimeError):
        populate(driver, sleeves)


def test_install_and_duplicate_decision_refusals():
    driver, _, _ = driver_fixture()
    diag.install_matched_diagnostics(driver, "ar_off", 0)
    with pytest.raises(diag._base.AcceptedRiskSixUniverseOrderQcRuntimeError, match="repeated"):
        diag.install_matched_diagnostics(driver, "ar_off", 0)
    session = driver._decision_sessions[0]
    driver._snapshot(session)
    with pytest.raises(diag._base.AcceptedRiskSixUniverseOrderQcRuntimeError, match="repeated"):
        driver._snapshot(session)


def test_valid_report_and_worst_exact_payload_remain_bounded():
    report = valid_report()
    assert diag.validate_report(report, "ar_off", 0)
    repeating = "0." + "1" * 96
    for row in report["annual_account_rows"]:
        row[5] = repeating
        row[6:9] = ["-" + repeating, repeating, repeating]
    with localcontext() as context:
        context.prec = 96
        report["overall_cumulative_return"] = diag._base._decimal_text((Decimal(1) + Decimal(repeating)) ** 5 - 1)
    for row in report["year_universe_rows"]:
        row[6] = repeating
    assert len(diag._base._canonical(report)) < 8192
    assert diag.validate_report(report, "ar_off", 0)


def test_transport_bound_inclusive_without_altering_canonical_content():
    driver = NS(_matched_diagnostics_statistic="x" * 8192)
    assert len(diag.diagnostic_text(driver)) == 8192
    driver._matched_diagnostics_statistic += "x"
    with pytest.raises(diag._base.AcceptedRiskSixUniverseOrderQcRuntimeError, match="oversized"):
        diag.diagnostic_text(driver)


@pytest.mark.parametrize("mutation", (
    lambda r: r.update(arm="ar_on100"),
    lambda r: r.update(slippage_bps_per_side=5),
    lambda r: r.update(extra=1),
    lambda r: r.update(membership_cap_path_sha256="f" * 63),
    lambda r: r.update(source_snapshot_count=260),
    lambda r: r.update(six_etf_panel_row_count=7529),
    lambda r: r.update(all_stock_price_equality_proved=True),
    lambda r: r.update(overall_cumulative_return="0.1"),
    lambda r: r["annual_account_rows"][1].__setitem__(3, "2022-01-04"),
    lambda r: r["annual_account_rows"][1].__setitem__(5, "NaN"),
    lambda r: r["annual_account_rows"][1].__setitem__(5, 0),
    lambda r: r["year_universe_rows"].pop(),
    lambda r: r["year_universe_rows"][0].__setitem__(3, 99),
))
def test_load_bearing_report_guards_refuse(mutation):
    report = valid_report()
    mutation(report)
    with pytest.raises(diag._base.AcceptedRiskSixUniverseOrderQcRuntimeError):
        diag.validate_report(report, "ar_off", 0)
