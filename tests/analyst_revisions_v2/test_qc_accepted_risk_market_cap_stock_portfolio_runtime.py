from __future__ import annotations

import ast
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_evaluator as evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_qc_runtime as runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as rating_evaluator,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_preliminary_qc_runtime as preliminary_fixtures,
)


RUNTIME_PATH = (
    Path(__file__).parents[2]
    / "research"
    / "analyst_revisions_v2_qc"
    / "accepted_risk_market_cap_stock_portfolio_qc_runtime.py"
)
PROFILE_ID = evaluator.QQQ_2023_2025_V2_PROFILE_ID


class _Universe:
    def __init__(self, sid):
        self.symbol = preliminary_fixtures._Symbol(sid, "UNIVERSE")


class _Fundamental:
    def __init__(self, symbol, market_cap):
        self.symbol = symbol
        self.market_cap = market_cap


class _FundamentalWithoutMarketCap:
    def __init__(self, symbol):
        self.symbol = symbol


class _Constituent:
    def __init__(self, symbol, weight):
        self.symbol = symbol
        self.weight = weight


class _Series:
    def __init__(self, rows):
        self._rows = rows

    def items(self):
        return self._rows.items()


class _Algorithm:
    def __init__(self, histories):
        self.histories = histories
        self.calls = []
        self.returned_collection_counts = []
        self.summary = {}

    def history(self, universe, start, end, *, flatten):
        self.calls.append((universe, start, end, flatten))
        bounded = {
            key: rows
            for key, rows in self.histories[universe].items()
            if start <= key[1] < end
        }
        self.returned_collection_counts.append(len(bounded))
        return _Series(bounded)

    def set_summary_statistic(self, key, value):
        self.summary[key] = value


def _resolution():
    rows = (
        preliminary_fixtures._binding("BBG000000001", "ONE", 2),
        preliminary_fixtures._binding("BBG000000002", "TWO", 2),
    )
    symbols = (
        preliminary_fixtures._Symbol("QC-SID-ONE", "ONE"),
        preliminary_fixtures._Symbol("QC-SID-TWO", "TWO"),
    )
    return preliminary_fixtures._resolved(rows, symbols), rows, symbols


def _loader(
    *,
    fundamental_rows,
    constituent_rows,
    decision_sessions=("2025-01-06",),
):
    resolution, rows, symbols = _resolution()
    fundamental_universe = _Universe("QC-FUNDAMENTAL-UNIVERSE")
    constituent_universe = _Universe("QC-QQQ-UNIVERSE")
    algorithm = _Algorithm(
        {
            fundamental_universe: {
                (fundamental_universe.symbol, observed): members
                for observed, members in fundamental_rows.items()
            },
            constituent_universe: {
                (constituent_universe.symbol, observed): members
                for observed, members in constituent_rows.items()
            },
        }
    )
    input_security_ids = tuple(sorted(row["security_id"] for row in rows))
    loader = runtime.QcPitMarketCapEligibilityLoader(
        algorithm,
        resolution=resolution,
        decision_sessions=decision_sessions,
        input_security_ids=input_security_ids,
        fundamental_universe=fundamental_universe,
        constituent_universes={"QQQ": constituent_universe},
        evaluation_profile_id=PROFILE_ID,
    )
    return loader, algorithm, rows, symbols


def _valid_rows():
    _, _, symbols = _resolution()
    fundamentals = {
        datetime(2025, 1, 3, 8): [
            _Fundamental(symbols[0], Decimal("100")),
            _Fundamental(symbols[1], Decimal("200")),
        ],
        datetime(2025, 1, 6, 8): [
            _Fundamental(symbols[0], Decimal("300.25")),
            _FundamentalWithoutMarketCap(symbols[1]),
        ],
    }
    constituents = {
        datetime(2025, 1, 3): [
            _Constituent(symbols[0], Decimal("0.6")),
            _Constituent(symbols[1], Decimal("0.4")),
        ]
    }
    return fundamentals, constituents


def test_runtime_is_standalone_compact_and_uses_only_fresh_dependencies():
    source = RUNTIME_PATH.read_bytes()
    text = source.decode("ascii")
    assert len(source) < 60_000
    assert "accepted_risk_preliminary_qc_runtime" not in text
    assert "accepted_risk_regime_rating_evaluator" not in text
    tree = ast.parse(text)
    direct = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name.startswith("accepted_risk_")
    }
    assert direct == {
        "accepted_risk_market_cap_stock_portfolio_evaluator",
        "accepted_risk_preliminary_qc_figi",
        "accepted_risk_preliminary_rating_evaluator",
    }
    compile(text, RUNTIME_PATH.name, "exec")
    compile("QC_PRELUDE_SENTINEL = True\n" + text, RUNTIME_PATH.name, "exec")


def test_runtime_active_and_historical_statistic_inventories_are_exact():
    assert runtime.PROFILE_IDS == evaluator.PROFILE_IDS
    for profile_id in evaluator.PROFILE_IDS:
        names = runtime.expected_custom_summary_statistic_names(profile_id)
        assert len(names) == 9
        assert evaluator.TILT_AGGREGATES_STATISTIC_NAME in names
    for profile_id in evaluator.V1_PROFILE_IDS + evaluator.V2_PROFILE_IDS:
        names = runtime.expected_custom_summary_statistic_names(profile_id)
        assert len(names) == 8
        assert evaluator.TILT_AGGREGATES_STATISTIC_NAME not in names


def test_total_return_loader_matches_legacy_on_one_synthetic_fixture():
    """The copied current loader stays value-equivalent without legacy QC source."""

    row = preliminary_fixtures._binding()
    stock = preliminary_fixtures._Symbol("QC STOCK SID", "NOW")
    benchmark = preliminary_fixtures._Symbol("QC BENCHMARK SID", "SPY")
    resolution = preliminary_fixtures._resolved([row], [stock], benchmark)
    stock_bar = SimpleNamespace(
        symbol=stock,
        time=datetime(2021, 1, 4),
        open="100.25",
    )
    benchmark_bar = SimpleNamespace(
        symbol=benchmark,
        time=datetime(2021, 1, 4),
        open="300.5",
    )
    history = preliminary_fixtures._GenericHistory(
        [
            preliminary_fixtures._TradeBars(
                datetime(2021, 1, 4, 16),
                ((stock, stock_bar), (benchmark, benchmark_bar)),
            )
        ]
    )
    algorithm = SimpleNamespace(history=history)
    kwargs = {
        "resolution": resolution,
        "benchmark_symbol": benchmark,
        "trade_bar_type": "TradeBar",
        "daily_resolution": "Daily",
        "total_return_normalization": "TotalReturn",
        "permitted_security_ids": (
            runtime.BENCHMARK_SECURITY_ID,
            row["security_id"],
        ),
        "permitted_sessions": ("2021-01-04", "2021-01-05"),
    }
    legacy = preliminary_fixtures.runtime.QcTotalReturnOpenHistoryLoader(
        algorithm,
        **kwargs,
    )
    current = runtime.QcTotalReturnOpenHistoryLoader(algorithm, **kwargs)
    request = preliminary_fixtures._request(
        (runtime.BENCHMARK_SECURITY_ID, row["security_id"])
    )

    legacy_rows = legacy(request)
    current_rows = current(request)
    normalized = lambda rows: tuple(
        (
            item.schema,
            item.security_id,
            item.session,
            str(item.adjusted_open),
        )
        for item in rows
    )
    assert normalized(current_rows) == normalized(legacy_rows)
    assert len(history.calls) == 2


def test_incremental_pit_loader_selects_latest_preopen_cap_and_discloses_uncovered():
    fundamentals, constituents = _valid_rows()
    loader, algorithm, rows, _symbols = _loader(
        fundamental_rows=fundamentals,
        constituent_rows=constituents,
    )

    loader.advance()
    assert len(algorithm.calls) == 1
    assert loader.completed is False
    loader.advance()
    assert len(algorithm.calls) == 2
    assert loader.completed is True

    result = loader.require_completed_market_caps()
    assert result == {
        "2025-01-06": {rows[0]["security_id"]: Decimal("300.25")}
    }
    assert loader.eligible_score_bearing_count == 2
    assert loader.covered_count == 1
    assert loader.uncovered_count == 1
    assert all(call[3] is False for call in algorithm.calls)


def test_out_of_window_collection_is_ignored_before_traversing_rows():
    fundamentals, constituents = _valid_rows()
    loader, algorithm, rows, _symbols = _loader(
        fundamental_rows=fundamentals,
        constituent_rows=constituents,
    )
    bounded_history = algorithm.history
    traversed = False

    class _HostileRows:
        def __iter__(self):
            nonlocal traversed
            traversed = True
            raise AssertionError("out-of-window rows were traversed")

    def history(universe, start, end, *, flatten):
        if universe is loader._fundamental_universe:
            algorithm.calls.append((universe, start, end, flatten))
            return _Series(
                {
                    (universe.symbol, end): _HostileRows(),
                    (
                        universe.symbol,
                        datetime(2025, 1, 6, 8),
                    ): fundamentals[datetime(2025, 1, 6, 8)],
                }
            )
        return bounded_history(universe, start, end, flatten=flatten)

    algorithm.history = history
    loader.advance()
    loader.advance()

    assert traversed is False
    assert loader.require_completed_market_caps() == {
        "2025-01-06": {rows[0]["security_id"]: Decimal("300.25")}
    }
    assert loader.fetched_source_row_count == 4
    assert len(algorithm.calls) == 2


def test_later_empty_fundamental_and_etf_chunks_use_contiguous_carry():
    assert runtime.HISTORY_CHUNK_DECISION_COUNT == 6
    _, rows, symbols = _resolution()
    decisions = (
        "2025-01-06",
        "2025-01-13",
        "2025-01-21",
        "2025-01-27",
        "2025-02-03",
        "2025-02-10",
        "2025-02-18",
    )
    fundamentals = {
        datetime(2025, 1, 6, 8): [
            _Fundamental(symbols[0], Decimal("100"))
        ],
        datetime(2025, 1, 27, 8): [
            _Fundamental(symbols[0], Decimal("400"))
        ],
    }
    constituents = {
        datetime(2025, 1, 3): [
            _Constituent(symbols[0], Decimal("1"))
        ],
    }
    loader, algorithm, _rows, _symbols = _loader(
        fundamental_rows=fundamentals,
        constituent_rows=constituents,
        decision_sessions=decisions,
    )

    for expected_calls in range(1, 5):
        loader.advance()
        assert len(algorithm.calls) == expected_calls
    first_start, first_end = algorithm.calls[0][1:3]
    later_start, later_end = algorithm.calls[2][1:3]
    assert (first_end - first_start).days <= 82
    assert later_start == first_end
    assert later_end - later_start < first_end - first_start
    assert max(fundamentals) < later_start
    assert max(constituents) < later_start
    assert algorithm.returned_collection_counts[2:] == [0, 0]
    assert loader.require_completed_market_caps()["2025-02-18"] == {
        rows[0]["security_id"]: Decimal("400")
    }


def test_post_open_fundamental_collection_refuses_behaviorally():
    fundamentals, constituents = _valid_rows()
    fundamentals = {
        datetime(2025, 1, 6, 9, 30, 0, 1): next(iter(fundamentals.values()))
    }
    loader, algorithm, _rows, _symbols = _loader(
        fundamental_rows=fundamentals,
        constituent_rows=constituents,
    )

    with pytest.raises(
        runtime.AcceptedRiskMarketCapStockPortfolioQcRuntimeError,
        match="was not observed before open",
    ):
        loader.advance()
    assert len(algorithm.calls) == 1


def test_latest_preopen_duplicate_positive_cap_value_conflict_refuses():
    fundamentals, constituents = _valid_rows()
    _, _, symbols = _resolution()
    fundamentals[datetime(2025, 1, 6, 8)] = [
        _Fundamental(symbols[0], Decimal("300.25")),
        _Fundamental(symbols[0], Decimal("300.26")),
    ]
    loader, algorithm, _rows, _symbols = _loader(
        fundamental_rows=fundamentals,
        constituent_rows=constituents,
    )

    loader.advance()
    with pytest.raises(
        runtime.AcceptedRiskMarketCapStockPortfolioQcRuntimeError,
        match="value or class conflicts",
    ):
        loader.advance()
    assert len(algorithm.calls) == 2


def test_same_value_duplicate_cap_collapses_and_same_day_etf_is_not_prior():
    fundamentals, constituents = _valid_rows()
    _, rows, symbols = _resolution()
    fundamentals[datetime(2025, 1, 6, 8)] = [
        _Fundamental(symbols[0], Decimal("300.25")),
        _Fundamental(symbols[0], Decimal("300.250")),
    ]
    constituents[datetime(2025, 1, 6)] = [
        _Constituent(symbols[1], Decimal("1"))
    ]
    loader, _algorithm, _rows, _symbols = _loader(
        fundamental_rows=fundamentals,
        constituent_rows=constituents,
    )

    loader.advance()
    loader.advance()
    assert loader.require_completed_market_caps() == {
        "2025-01-06": {rows[0]["security_id"]: Decimal("300.25")}
    }


def test_empty_cap_covered_score_bearing_membership_refuses():
    fundamentals, constituents = _valid_rows()
    _, _, symbols = _resolution()
    fundamentals[datetime(2025, 1, 6, 8)] = [
        _FundamentalWithoutMarketCap(symbols[0]),
        _FundamentalWithoutMarketCap(symbols[1]),
    ]
    loader, _algorithm, _rows, _symbols = _loader(
        fundamental_rows=fundamentals,
        constituent_rows=constituents,
    )

    loader.advance()
    with pytest.raises(
        runtime.AcceptedRiskMarketCapStockPortfolioQcRuntimeError,
        match="covered eligibility is empty",
    ):
        loader.advance()


def test_runtime_meta_is_point_in_time_count_only_and_not_etf_or_leverage():
    fundamentals, constituents = _valid_rows()
    pit_loader, algorithm, _rows, _symbols = _loader(
        fundamental_rows=fundamentals,
        constituent_rows=constituents,
    )
    pit_loader.advance()
    pit_loader.advance()
    driver = runtime.AcceptedRiskMarketCapStockPortfolioQcDriver(
        algorithm,
        activation_manifest_key="arv2/test/transport-manifest.json",
        activation_manifest_sha256="a" * 64,
        activation_manifest_byte_count=1,
        benchmark_symbol=preliminary_fixtures._Symbol("QC-BENCH", "SPY"),
        trade_bar_type=object,
        daily_resolution=object(),
        total_return_normalization=object(),
        evaluation_profile_id=PROFILE_ID,
        fundamental_universe=next(iter(algorithm.histories)),
        constituent_universes={"QQQ": list(algorithm.histories)[1]},
    )
    driver._package = SimpleNamespace(
        package_id="arv2-test-package",
        package_sha256="b" * 64,
        activation_manifest_sha256="c" * 64,
    )
    driver._resolution = SimpleNamespace(
        resolution_id="arv2-test-resolution",
        resolution_sha256="d" * 64,
        resolved_count=2,
        named_refusal_count=0,
    )
    driver._pit_loader = pit_loader
    driver._runtime_slice_count = 4

    class _CompletedRuntime:
        phase = rating_evaluator.RuntimePhase.COMPLETED

        @staticmethod
        def custom_summary_statistics():
            return {
                name: "{}"
                for name in evaluator.expected_custom_summary_statistic_names(
                    PROFILE_ID
                )
            }

    driver._runtime = _CompletedRuntime()
    driver.emit_completed_summary()
    meta = json.loads(algorithm.summary[runtime.RUNTIME_META_STATISTIC])
    assert meta["point_in_time"] is True
    assert meta["etf_or_leverage"] is False
    assert meta["point_in_time_market_cap_uncovered_count"] == 1
    assert "security_id" not in json.dumps(meta)
    assert "market_cap_values" not in json.dumps(meta)


def _history_phase_driver(current_time):
    calls = []

    class _HistoryRuntime:
        phase = rating_evaluator.RuntimePhase.HISTORY

        @staticmethod
        def _history_request(_index):
            return SimpleNamespace(end_session="2026-03-30")

        @staticmethod
        def run_callback(loader):
            calls.append(loader)
            return len(calls)

    driver = object.__new__(
        runtime.AcceptedRiskMarketCapStockPortfolioQcDriver
    )
    driver._algorithm = SimpleNamespace(time=current_time)
    driver._package = object()
    driver._pit_loader = SimpleNamespace(completed=True)
    driver._runtime = _HistoryRuntime()
    driver._history_loader = object()
    driver._emitted = False
    driver._runtime_slice_count = 0
    driver._runtime_started_monotonic = None
    return driver, calls


def test_driver_waits_for_complete_history_then_uses_bounded_work_units():
    driver, calls = _history_phase_driver(datetime(2026, 3, 30, 16))

    assert driver.advance_training_slice(monotonic=lambda: 0) is None
    assert calls == []

    driver._algorithm.time = datetime(2026, 3, 31)
    assert driver.advance_training_slice(monotonic=lambda: 0) == 4
    assert len(calls) == runtime.TRAIN_WORK_UNITS_PER_SLICE == 4


def test_driver_waits_for_each_point_in_time_chunk_before_history_calls():
    driver, history_calls = _history_phase_driver(datetime(2025, 1, 6, 16))
    pit_calls = []

    class _PitLoader:
        _chunks = (
            (datetime(2025, 1, 6),),
            (datetime(2025, 2, 17),),
        )
        _chunk_index = 0
        _stage = "fundamental"

        @property
        def completed(self):
            return self._chunk_index == len(self._chunks)

        def advance(self):
            pit_calls.append((self._chunk_index, self._stage))
            if self._stage == "fundamental":
                self._stage = "constituent"
            else:
                self._stage = "fundamental"
                self._chunk_index += 1
            return self._chunk_index, self._stage

    driver._pit_loader = _PitLoader()

    assert driver.advance_training_slice(monotonic=lambda: 0) is None
    assert pit_calls == []

    driver._algorithm.time = datetime(2025, 1, 7)
    assert driver.advance_training_slice(monotonic=lambda: 0) == (
        1,
        "fundamental",
    )
    assert pit_calls == [(0, "fundamental"), (0, "constituent")]
    assert history_calls == []

    driver._algorithm.time = datetime(2025, 2, 18)
    driver.advance_training_slice(monotonic=lambda: 0)
    assert pit_calls[-2:] == [(1, "fundamental"), (1, "constituent")]
    assert driver._pit_loader.completed is True
    assert history_calls == []


def test_driver_soft_time_bound_stops_additional_work_units():
    driver, calls = _history_phase_driver(datetime(2026, 3, 31))
    clock = iter((0, 0, runtime.TRAIN_SLICE_SOFT_SECONDS))

    assert driver.advance_training_slice(monotonic=lambda: next(clock)) == 1
    assert len(calls) == 1


def test_history_items_bound_iteration_before_materializing_the_collection_cap():
    """ARV2R93: the collection cap must bound iteration, not follow materialization."""

    cap = runtime.MAX_COLLECTIONS_PER_CALL
    pulled = 0

    def oversized_but_finite():
        nonlocal pulled
        for _ in range(cap * 4):
            pulled += 1
            yield (object(), object())

    class _History:
        @staticmethod
        def items():
            return oversized_but_finite()

    with pytest.raises(
        runtime.AcceptedRiskMarketCapStockPortfolioQcRuntimeError,
        match="exceeded the collection cap",
    ):
        runtime._history_items(_History(), "ETF constituent")

    assert pulled == cap + 1


def test_collection_rows_bound_iteration_before_materializing_the_row_cap():
    """ARV2CR94: the row cap must stop traversal before full materialization."""

    cap = runtime.MAX_COLLECTION_ROWS
    pulled = 0

    def oversized_but_finite():
        nonlocal pulled
        for _ in range(cap + 17):
            pulled += 1
            yield object()

    with pytest.raises(
        runtime.AcceptedRiskMarketCapStockPortfolioQcRuntimeError,
        match="collection row bound changed",
    ):
        runtime._collection_rows(oversized_but_finite(), "Fundamental")

    assert pulled == cap + 1
