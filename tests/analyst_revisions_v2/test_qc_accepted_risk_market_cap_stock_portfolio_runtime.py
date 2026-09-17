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
PROFILE_ID = evaluator.QQQ_2023_2025_PROFILE_ID


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


def test_later_empty_fundamental_and_etf_chunks_use_contiguous_carry():
    _, rows, symbols = _resolution()
    decisions = (
        "2025-01-06",
        "2025-01-13",
        "2025-01-21",
        "2025-01-27",
        "2025-02-03",
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
    assert later_start == first_end
    assert later_end - later_start < first_end - first_start
    assert max(fundamentals) < later_start
    assert max(constituents) < later_start
    assert algorithm.returned_collection_counts[2:] == [0, 0]
    assert loader.require_completed_market_caps()["2025-02-03"] == {
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
