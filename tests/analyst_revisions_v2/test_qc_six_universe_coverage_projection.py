"""The diagnostic's QC source is exact, bounded, and outcome-free."""

import hashlib
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_delta_order_package as delta,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_coverage_qc_projection as subject,
)


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/"
    "accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)


@pytest.fixture(scope="module")
def loaded_delta():
    return delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )


def test_projection_closes_exact_nine_file_counts_only_source(loaded_delta):
    projection = subject.build_six_universe_coverage_qc_projection(loaded_delta)
    assert len(projection.source_files) == 9
    assert projection.total_source_byte_count == sum(
        item.byte_count for item in projection.source_files
    )
    assert projection.total_source_byte_count <= subject.MAXIMUM_TOTAL_SOURCE_BYTES
    assert tuple(item.project_path for item in projection.source_files) == tuple(
        sorted(item.project_path for item in projection.source_files)
    )
    assert len({item.project_path for item in projection.source_files}) == 9
    assert projection.to_record()["outcome_access"] is False
    assert projection.to_record()["price_access"] is False
    assert projection.to_record()["orders"] is False
    assert projection.to_record()["backtest_only"] is True
    assert projection.to_record()["trading"] is False
    assert len(projection.statistic_names) == 7

    root = Path(subject.__file__).resolve().parent
    for item in projection.source_files:
        assert item.byte_count == len(item.source_bytes)
        assert item.content_sha256 == hashlib.sha256(item.source_bytes).hexdigest()
        if item.project_path != subject.MAIN_PROJECT_PATH:
            assert item.source_bytes == (root / item.project_path).read_bytes()
    main = next(
        item.source_bytes.decode("ascii") for item in projection.source_files
        if item.project_path == subject.MAIN_PROJECT_PATH
    )
    assert "set_start_date(2020, 11, 1)" in main
    # QC invokes OnEndOfAlgorithm at the following midnight. Ending on the
    # prior trading day preserves the diagnostic's 2025-12-31 end-clock pin;
    # the final weekly coverage decision was already made on 2025-12-29.
    assert subject.ALGORITHM_END == (2025, 12, 30)
    assert "set_end_date(2025, 12, 30)" in main
    assert "set_end_date(2025, 12, 31)" not in main
    assert "after_market_close(benchmark, 0)" in main
    assert "market_on_open_order" not in main
    assert "on_order_event" not in main
    assert "history(" not in main


@pytest.mark.parametrize(
    "source",
    [
        b"import urllib.request\n",
        b"def x():\n    market_on_open_order('SPY', 1)\n",
        b"def x():\n    history('SPY', 5)\n",
        b"def x():\n    set_holdings('SPY', 1)\n",
        b"def x():\n    object_store.save_bytes('x', b'x')\n",
        b"from __future__ import annotations\n",
    ],
)
def test_projection_refuses_capability_or_prelude_expansion(source):
    with pytest.raises(subject.SixUniverseCoverageQcProjectionError):
        subject._source_file("hostile.py", source)


def test_projection_refuses_unreviewed_input_type():
    with pytest.raises(subject.SixUniverseCoverageQcProjectionError):
        subject.build_six_universe_coverage_qc_projection(object())
