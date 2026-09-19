import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as base,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate as gate,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate_evaluator as evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate_qc_runtime as subject,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_preliminary_qc_runtime as preliminary_fixtures,
)


def _universes(prefix):
    return {
        ticker: SimpleNamespace(
            symbol=preliminary_fixtures._Symbol(
                "QC " + prefix + " " + ticker, ticker
            )
        )
        for ticker in gate.UNIVERSE_IDS
    }


def _etfs():
    return {
        ticker: preliminary_fixtures._Symbol(
            "QC ETF " + ticker, ticker
        )
        for ticker in gate.UNIVERSE_IDS
    }


class _Series:
    def __init__(self, items):
        self._items = tuple(items)

    def items(self):
        return iter(self._items)


class _PitAlgorithm:
    def __init__(self, histories):
        self._histories = dict(histories)
        self.calls = []

    def history(self, universe, start, end, *, flatten):
        self.calls.append((universe, start, end, flatten))
        return self._histories[id(universe)]


def _pit_loader(
    *,
    constituent_stamp=datetime(2025, 1, 4),
    decision_sessions=("2025-01-06",),
    session_axis=("2025-01-02", "2025-01-03", "2025-01-06"),
    fundamental_collections=None,
):
    rows = (
        preliminary_fixtures._binding("BBG000000001", "ONE", 2),
        preliminary_fixtures._binding("BBG000000002", "TWO", 2),
    )
    one = preliminary_fixtures._Symbol("QC STOCK ONE", "ONE")
    two = preliminary_fixtures._Symbol("QC STOCK TWO", "TWO")
    unknown = preliminary_fixtures._Symbol("QC STOCK UNKNOWN", "UNKNOWN")
    resolution = preliminary_fixtures._resolved(rows, (one, two))
    fundamental = SimpleNamespace(
        symbol=preliminary_fixtures._Symbol(
            "QC FUNDAMENTAL UNIVERSE", "FUNDAMENTAL"
        )
    )
    constituent_universes = _universes("CONSTITUENT UNIVERSE")
    if fundamental_collections is None:
        fundamental_collections = (
            (datetime(2025, 1, 3, 8), "200", "100"),
        )
    histories = {
        id(fundamental): _Series(
            tuple(
                (
                    (fundamental.symbol, stamp),
                    (
                        SimpleNamespace(symbol=one, market_cap=one_cap),
                        SimpleNamespace(symbol=two, market_cap=two_cap),
                    ),
                )
                for stamp, one_cap, two_cap in fundamental_collections
            )
        )
    }
    for universe in constituent_universes.values():
        histories[id(universe)] = _Series(
            (
                (
                    (universe.symbol, constituent_stamp),
                    (
                        SimpleNamespace(symbol=one, weight="0.6"),
                        SimpleNamespace(symbol=two, weight="0.3"),
                        SimpleNamespace(symbol=unknown, weight="0.1"),
                    ),
                ),
            )
        )
    algorithm = _PitAlgorithm(histories)
    loader = subject.SixUniversePitSnapshotLoader(
        algorithm,
        resolution=resolution,
        decision_sessions=decision_sessions,
        session_axis=session_axis,
        fundamental_universe=fundamental,
        constituent_universes=constituent_universes,
        etf_symbols=_etfs(),
    )
    return loader, algorithm


def test_pit_loader_advances_one_bounded_stage_and_retains_unresolved_rows():
    loader, algorithm = _pit_loader()
    for expected_stage in range(1, 7):
        assert loader.advance() == (0, expected_stage)
        assert loader.completed is False
    assert loader.advance() == (1, 0)
    assert loader.completed is True
    snapshots = loader.require_completed_snapshots()
    assert loader.history_call_count == 7
    assert loader.source_row_count == 20
    assert len(algorithm.calls) == 7
    assert tuple(item.universe_id for item in snapshots[0].universes) == (
        gate.UNIVERSE_IDS
    )
    for universe in snapshots[0].universes:
        assert len(universe.constituents) == 3
        unresolved = universe.constituents[-1]
        assert unresolved.reported_weight == Decimal("0.1")
        assert unresolved.security_id is None
        assert unresolved.security_name is None
        assert unresolved.pit_market_cap is None
        assert unresolved.firm_specific_score is None


def test_first_decision_maps_holiday_fundamental_collection_to_next_session():
    loader, _algorithm = _pit_loader(
        constituent_stamp=datetime(2026, 1, 1),
        decision_sessions=("2026-01-02",),
        session_axis=("2025-12-31", "2026-01-02"),
        fundamental_collections=(
            (datetime(2026, 1, 1, 8), "200", "100"),
        ),
    )

    for _ in range(7):
        loader.advance()

    snapshot = loader.require_completed_snapshots()[0]
    assert snapshot.session == "2026-01-02"
    assert loader._age(
        datetime(2026, 1, 1, 8),
        "2026-01-02",
        "six-universe PIT fundamentals",
        permit_non_session=True,
    ) == 0


def test_non_session_constituent_source_date_still_refuses():
    loader, _algorithm = _pit_loader(
        # Sunday EndTime normalizes to Saturday, which cannot be treated as
        # authenticated Friday constituent evidence.
        constituent_stamp=datetime(2025, 1, 5)
    )
    for _ in range(6):
        loader.advance()
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="constituents collection escaped the authenticated session axis",
    ):
        loader.advance()


def test_non_session_fundamental_mapping_refuses_outside_or_after_axis():
    loader, _algorithm = _pit_loader(
        decision_sessions=("2026-01-02",),
        session_axis=("2025-12-31", "2026-01-02", "2026-01-05"),
    )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="escaped the authenticated session axis",
    ):
        loader._age(
            datetime(2025, 12, 30, 8),
            "2026-01-02",
            "six-universe PIT fundamentals",
            permit_non_session=True,
        )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="collection is after its decision",
    ):
        loader._age(
            datetime(2026, 1, 3, 8),
            "2026-01-02",
            "six-universe PIT fundamentals",
            permit_non_session=True,
        )


def test_pit_loader_refuses_a_same_decision_constituent_state():
    loader, _algorithm = _pit_loader(
        # QC daily EndTime normalizes back one day to the decision itself,
        # which is not strictly prior evidence.
        constituent_stamp=datetime(2025, 1, 7)
    )
    for _ in range(6):
        loader.advance()
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="strictly prior collection",
    ):
        loader.advance()


def test_reused_constituent_collection_rebinds_each_fundamental_snapshot():
    loader, _algorithm = _pit_loader(
        decision_sessions=("2025-01-06", "2025-01-07"),
        session_axis=(
            "2025-01-02",
            "2025-01-03",
            "2025-01-06",
            "2025-01-07",
        ),
        fundamental_collections=(
            (datetime(2025, 1, 3, 8), "200", "100"),
            (datetime(2025, 1, 7, 8), "100", "300"),
        ),
    )
    for _ in range(7):
        loader.advance()
    first, second = loader.require_completed_snapshots()

    def caps(snapshot):
        return {
            item.security_name: item.pit_market_cap
            for item in snapshot.universes[0].constituents
            if item.security_name is not None
        }

    assert caps(first) == {"ONE": Decimal(200), "TWO": Decimal(100)}
    assert caps(second) == {"ONE": Decimal(100), "TWO": Decimal(300)}


def test_fundamental_snapshot_at_maximum_age_plus_one_refuses():
    loader, _algorithm = _pit_loader(
        fundamental_collections=((datetime(2025, 1, 2, 8), "200", "100"),)
    )
    for _ in range(6):
        loader.advance()
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="fundamental snapshot is too old",
    ):
        loader.advance()


def test_constituent_snapshot_at_maximum_age_plus_one_refuses():
    loader, _algorithm = _pit_loader(
        constituent_stamp=datetime(2024, 12, 24),
        session_axis=(
            "2024-12-23",
            "2024-12-24",
            "2024-12-26",
            "2024-12-27",
            "2024-12-30",
            "2025-01-03",
            "2025-01-06",
        ),
    )
    for _ in range(6):
        loader.advance()
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="constituent snapshot is too old",
    ):
        loader.advance()


class _Bar:
    def __init__(self, symbol, observed, price):
        self.symbol = symbol
        self.time = observed
        self.open = price


def _history_request(ids):
    seed = {
        "schema": base.HISTORY_REQUEST_SCHEMA,
        "request_index": 0,
        "security_ids": list(ids),
        "start_session": "2021-01-04",
        "end_session": "2021-01-04",
        "normalization_mode": "total_return",
        "observation": "session_open",
    }
    return base.TotalReturnHistoryRequest(
        base.HISTORY_REQUEST_SCHEMA,
        0,
        ids,
        "2021-01-04",
        "2021-01-04",
        "total_return",
        "session_open",
        subject._sha(seed),
    )


def test_typed_total_return_history_maps_stocks_and_all_six_etfs_exactly():
    row = preliminary_fixtures._binding()
    stock = preliminary_fixtures._Symbol("QC STOCK SID", "STOCK")
    resolution = preliminary_fixtures._resolved((row,), (stock,))
    etfs = _etfs()
    security_ids = tuple(
        sorted(
            (row["security_id"],)
            + tuple(str(symbol.id) for symbol in etfs.values())
        )
    )
    observed = datetime(2021, 1, 4)
    by_id = {row["security_id"]: stock}
    by_id.update({str(symbol.id): symbol for symbol in etfs.values()})
    bars = preliminary_fixtures._TradeBars(
        observed,
        tuple(
            (symbol, _Bar(symbol, observed, "100"))
            for symbol in by_id.values()
        ),
    )
    algorithm = SimpleNamespace(
        history=preliminary_fixtures._GenericHistory((bars,))
    )
    loader = subject.QcSixUniverseTotalReturnOpenHistoryLoader(
        algorithm,
        resolution=resolution,
        etf_symbols=etfs,
        permitted_security_ids=security_ids,
        permitted_sessions=("2021-01-04",),
        trade_bar_type=object(),
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
    )

    result = loader(_history_request(security_ids))

    assert tuple(item.security_id for item in result) == security_ids
    assert all(item.adjusted_open == Decimal(100) for item in result)
    assert loader.call_count == 1
    ((args, kwargs),) = algorithm.history.calls
    assert len(args[0]) == 7
    assert kwargs == {
        "fill_forward": False,
        "extended_market_hours": False,
        "data_normalization_mode": "TotalReturn",
    }


def _typed_loader_at(observed):
    row = preliminary_fixtures._binding()
    stock = preliminary_fixtures._Symbol("QC STOCK SID", "STOCK")
    resolution = preliminary_fixtures._resolved((row,), (stock,))
    etfs = _etfs()
    security_ids = tuple(
        sorted(
            (row["security_id"],)
            + tuple(str(symbol.id) for symbol in etfs.values())
        )
    )
    symbols = (stock,) + tuple(etfs.values())
    bars = preliminary_fixtures._TradeBars(
        observed,
        tuple(
            (symbol, _Bar(symbol, observed, "100")) for symbol in symbols
        ),
    )
    algorithm = SimpleNamespace(
        history=preliminary_fixtures._GenericHistory((bars,))
    )
    loader = subject.QcSixUniverseTotalReturnOpenHistoryLoader(
        algorithm,
        resolution=resolution,
        etf_symbols=etfs,
        permitted_security_ids=security_ids,
        permitted_sessions=("2021-01-04",),
        trade_bar_type=object(),
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
    )
    return loader, security_ids


def test_typed_history_refuses_malformed_request_hash_before_calling_qc():
    loader, security_ids = _typed_loader_at(datetime(2021, 1, 4))
    valid = _history_request(security_ids)
    malformed = base.TotalReturnHistoryRequest(
        valid.schema,
        valid.request_index,
        valid.security_ids,
        valid.start_session,
        valid.end_session,
        valid.normalization_mode,
        valid.observation,
        "0" * 64,
    )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="request identity changed",
    ):
        loader(malformed)
    assert loader.call_count == 0


def test_typed_history_refuses_a_bar_batch_outside_the_request():
    loader, security_ids = _typed_loader_at(datetime(2021, 1, 5))
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="escaped its request",
    ):
        loader(_history_request(security_ids))


class _IncompletePit:
    completed = False
    next_required_session = "2025-12-31"

    def __init__(self):
        self.calls = 0

    def advance(self):
        self.calls += 1
        return self.calls


class _DriverAlgorithm:
    def __init__(self):
        self.time = datetime(2026, 1, 2)
        self.statistics = {}
        self.calls = []

    def set_summary_statistic(self, name, value):
        self.calls.append((name, value))
        self.statistics[name] = value


def _driver():
    algorithm = _DriverAlgorithm()
    return subject.AcceptedRiskSixUniverseGateQcDriver(
        algorithm,
        activation_manifest_key="private/read-only/key",
        activation_manifest_sha256="a" * 64,
        activation_manifest_byte_count=1,
        benchmark_symbol=preliminary_fixtures._Symbol(
            "QC BENCHMARK", "SPY"
        ),
        etf_symbols=_etfs(),
        profile_id=evaluator.TOP10_PRIMARY_PROFILE.profile_id,
        fundamental_universe=SimpleNamespace(
            symbol=preliminary_fixtures._Symbol("QC FUNDAMENTAL", "FUND")
        ),
        constituent_universes=_universes("DRIVER UNIVERSE"),
        trade_bar_type=object(),
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
    )


def test_driver_performs_only_two_work_units_per_simulated_time_callback():
    driver = _driver()
    pit = _IncompletePit()
    driver._package = object()
    driver._pit_loader = pit

    assert driver.advance_training_slice(monotonic=lambda: 0) == 2
    assert pit.calls == subject.TRAIN_WORK_UNITS_PER_SLICE == 2
    assert driver._slice_count == 1
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="slice bound changed",
    ):
        driver.advance_training_slice(maximum_work_units=3, monotonic=lambda: 0)


def test_incomplete_driver_refuses_end_of_algorithm_instead_of_emitting():
    driver = _driver()
    with pytest.raises(
        subject.AcceptedRiskSixUniverseGateQcRuntimeError,
        match="ended before aggregate completion",
    ):
        driver.require_completed_at_end()


def test_complete_driver_emits_each_aggregate_once_and_runtime_meta():
    driver = _driver()
    driver._package = SimpleNamespace(
        package_id="arv2-package",
        package_sha256="a" * 64,
    )
    driver._resolution = SimpleNamespace(
        resolution_id="arv2-resolution",
        resolution_sha256="b" * 64,
    )
    driver._pit_loader = SimpleNamespace(
        history_call_count=77,
        source_row_count=1234,
    )
    driver._history_loader = SimpleNamespace(call_count=9)
    driver._runtime = SimpleNamespace(
        phase=evaluator.EvaluationPhase.COMPLETED,
        custom_summary_statistics=lambda: {
            name: "{}"
            for name in evaluator.expected_custom_summary_statistic_names(
                evaluator.TOP10_PRIMARY_PROFILE.profile_id
            )
        },
    )
    driver._slice_count = 11

    driver.emit_completed_summary()
    driver.emit_completed_summary()

    expected = set(
        evaluator.expected_custom_summary_statistic_names(
            evaluator.TOP10_PRIMARY_PROFILE.profile_id
        )
    ) | {subject.RUNTIME_META_STATISTIC_NAME}
    assert set(driver._algorithm.statistics) == expected
    assert len(driver._algorithm.calls) == len(expected)
    meta = json.loads(
        driver._algorithm.statistics[subject.RUNTIME_META_STATISTIC_NAME]
    )
    assert meta["runtime_slice_count"] == 11
    assert meta["pit_history_call_count"] == 77
    assert meta["price_history_call_count"] == 9
    assert meta["orders"] is False
    assert meta["deployment"] is False


def test_runtime_source_compiles_after_projection_prelude_and_has_no_orders():
    source = Path(subject.__file__).read_text(encoding="utf-8")
    compile("_projection_prelude = True\n" + source, "runtime.py", "exec")
    lowered = source.lower()
    for forbidden in (
        ".market_order(",
        ".limit_order(",
        ".set_holdings(",
        ".liquidate(",
        ".save(",
        "deployment",
    ):
        if forbidden == "deployment":
            # The word is present only in explicit negative capability records.
            assert '"deployment": false' in lowered
        else:
            assert forbidden not in lowered
