"""Exact cloud projection for the point-in-time market-cap stock runs."""

import dataclasses
from datetime import date
import hashlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_evaluator as evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_qc_runtime as runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_package as package_builder,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_qc_projection as projection,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_objective_synthetic_leverage_evaluator as leverage_evaluator,
)


@pytest.fixture
def package(monkeypatch):
    activation = SimpleNamespace(
        role="activation_manifest",
        activation_manifest=True,
        object_store_key=(
            "arv2/preliminary-rating/fixture/transport-manifest.json"
        ),
        content_sha256="f" * 64,
        byte_count=1234,
    )
    value = SimpleNamespace(
        package_id="arv2-preliminary-qc-package-fixture",
        package_sha256="e" * 64,
        upload_objects=(activation,),
    )
    monkeypatch.setattr(
        package_builder,
        "require_accepted_risk_preliminary_package",
        lambda candidate: candidate,
    )
    return value


@pytest.mark.parametrize("profile_id", evaluator.PROFILE_IDS)
def test_market_cap_projection_is_exact_small_and_profile_bound(
    package, profile_id
):
    value = projection.build_accepted_risk_preliminary_qc_projection(
        package,
        evaluation_profile_id=profile_id,
    )
    by_name = {item.project_path: item for item in value.source_files}
    main = by_name["main.py"].source_bytes.decode("ascii")
    tickers = evaluator.constituent_etf_tickers_for_profile(profile_id)

    assert tuple(sorted(by_name)) == tuple(
        sorted((*projection.MARKET_CAP_PROJECT_SOURCE_PATHS, "main.py"))
    )
    assert "accepted_risk_preliminary_qc_runtime.py" not in by_name
    assert "accepted_risk_regime_rating_evaluator.py" not in by_name
    assert "accepted_risk_stock_portfolio_evaluator.py" not in by_name
    assert "accepted_risk_market_cap_stock_portfolio_tilt.py" in by_name
    assert max(item.byte_count for item in value.source_files) < 60_000
    assert (
        value.total_source_byte_count + 4_096
        <= projection.MAX_MARKET_CAP_TOTAL_SOURCE_BYTES
    )
    assert value.evaluation_profile_sha256 == (
        projection.MARKET_CAP_PROFILE_SHA256S[profile_id]
    )
    assert value.train_work_units_per_slice == (
        runtime.TRAIN_WORK_UNITS_PER_SLICE
    )
    assert value.maximum_train_slice_count == runtime.MAX_TRAIN_SLICE_COUNT
    assert (
        f"evaluation_profile_id={profile_id!r}" in main
    )
    assert f"for ticker in {tickers!r}" in main
    assert "self._arv2_fundamental_universe = self.AddUniverse(" in main
    assert "lambda fundamentals: []" in main
    assert main.count("self.universe.etf(") == 1
    assert main.count("Symbol.create(") == 1
    assert "fundamental_universe=self._arv2_fundamental_universe" in main
    assert "constituent_universes=self._arv2_constituent_universes" in main
    assert projection.require_accepted_risk_preliminary_qc_projection(value) is value


def test_historical_market_cap_projection_keeps_original_total_size_cap(package):
    value = projection.build_accepted_risk_preliminary_qc_projection(
        package,
        evaluation_profile_id=evaluator.QQQ_2021_2025_PROFILE_ID,
    )
    required_padding = (
        projection.MAX_TOTAL_SOURCE_BYTES
        + 1
        - value.total_source_byte_count
    )
    assert required_padding > 0
    target = next(
        item for item in value.source_files if item.project_path != "main.py"
    )
    padded = projection._validate_source(
        target.project_path,
        target.source_bytes + b"\n#" + b"x" * (required_padding - 2),
    )
    source_files = tuple(
        padded if item is target else item for item in value.source_files
    )
    candidate = dataclasses.replace(
        value,
        projection_id="",
        projection_sha256="",
        source_files=source_files,
        total_source_byte_count=sum(item.byte_count for item in source_files),
    )
    semantic = candidate.to_record()
    semantic["projection_id"] = None
    semantic["projection_sha256"] = None
    digest = hashlib.sha256(projection._canonical(semantic)).hexdigest()
    candidate = dataclasses.replace(
        candidate,
        projection_id="arv2-preliminary-qc-projection-" + digest[:24],
        projection_sha256=digest,
    )

    assert candidate.total_source_byte_count == projection.MAX_TOTAL_SOURCE_BYTES + 1
    assert (
        candidate.total_source_byte_count
        < projection.MAX_MARKET_CAP_TOTAL_SOURCE_BYTES
    )
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match="disclosure or inventory changed",
    ):
        projection.require_accepted_risk_preliminary_qc_projection(candidate)


def test_market_cap_main_defers_every_history_work_unit_until_callbacks(package):
    profile_id = evaluator.QQQ_2021_2025_V2_PROFILE_ID
    value = projection.build_accepted_risk_preliminary_qc_projection(
        package,
        evaluation_profile_id=profile_id,
    )
    main = next(
        item.source_bytes.decode("ascii")
        for item in value.source_files
        if item.project_path == "main.py"
    )
    initialize = main.split("def initialize", 1)[1].split(
        "def _arv2_empty_constituent_selection", 1
    )[0]

    assert ".history(" not in initialize
    assert "advance_training_slice(" not in initialize
    assert "def on_data" in main
    assert "self._arv2_advance_training_slice()" in main
    assert "maximum_work_units=TRAIN_WORK_UNITS_PER_SLICE" in main
    assert "soft_seconds=TRAIN_SLICE_SOFT_SECONDS" in main


def test_market_cap_callback_calendar_has_explicit_completion_headroom(package):
    sessions = trading_sessions(
        date(*projection.MARKET_CAP_ALGORITHM_START),
        date(*projection.MARKET_CAP_ALGORITHM_END),
    )
    assert len(sessions) == 676
    assert len(sessions) > 600
    mature_sessions = trading_sessions(
        date(2026, 3, 31), date(*projection.MARKET_CAP_ALGORITHM_END)
    )
    assert len(mature_sessions) == 114
    maximum_all_resolved_price_batches = (
        6_151 + 1 + 64 - 1
    ) // 64
    required_post_maturity_work_units = (
        maximum_all_resolved_price_batches
        + 1
        + (1_255 + 5 - 1) // 5
    )
    assert maximum_all_resolved_price_batches == 97
    assert required_post_maturity_work_units == 349
    assert len(mature_sessions) * runtime.TRAIN_WORK_UNITS_PER_SLICE == 456
    assert 456 >= required_post_maturity_work_units

    value = projection.build_accepted_risk_preliminary_qc_projection(
        package,
        evaluation_profile_id=evaluator.SPY_2021_2025_V2_PROFILE_ID,
    )
    main = next(
        item.source_bytes.decode("ascii")
        for item in value.source_files
        if item.project_path == "main.py"
    )
    assert "set_start_date(2024, 1, 2)" in main
    assert "set_end_date(2026, 9, 11)" in main


def test_market_cap_projection_inventory_and_profile_hash_are_load_bearing(
    package,
):
    value = projection.build_accepted_risk_preliminary_qc_projection(
        package,
        evaluation_profile_id=evaluator.SPY_2021_2025_V2_PROFILE_ID,
    )
    assert tuple(item.project_path for item in value.source_files) == tuple(
        sorted((*projection.MARKET_CAP_PROJECT_SOURCE_PATHS, "main.py"))
    )
    assert any(
        item.project_path == "accepted_risk_market_cap_stock_portfolio_tilt.py"
        for item in value.source_files
    )
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match="disclosure or inventory changed",
    ):
        projection.require_accepted_risk_preliminary_qc_projection(
            dataclasses.replace(
                value,
                evaluation_profile_sha256="0" * 64,
            )
        )

    assert projection.MARKET_CAP_PROFILE_IDS == evaluator.PROFILE_IDS
    assert projection.MARKET_CAP_V1_PROFILE_IDS == evaluator.V1_PROFILE_IDS
    assert projection.MARKET_CAP_V2_PROFILE_IDS == evaluator.V2_PROFILE_IDS
    assert projection.MARKET_CAP_V3_PROFILE_IDS == evaluator.V3_PROFILE_IDS
    assert projection.MARKET_CAP_ALL_PROFILE_IDS == evaluator.ALL_PROFILE_IDS
    assert set(projection.MARKET_CAP_PROFILE_SHA256S) == set(
        evaluator.PROFILE_IDS
    )
    assert set(projection.MARKET_CAP_ALL_PROFILE_SHA256S) == set(
        evaluator.ALL_PROFILE_IDS
    )


def test_all_eight_reviewed_profile_sha256s_are_frozen_before_launch():
    """ARV2R93-006: every reviewed R-083--R-090 profile is an exact pin."""

    assert {
        profile_id: evaluator.require_profile(profile_id)["profile_sha256"]
        for profile_id in evaluator.V1_PROFILE_IDS
    } == {
        evaluator.QQQ_2021_2025_PROFILE_ID:
            "3025fff20f0742b60b5e75af22bc71230608fcc7a3af9b043c0c8865dfe0548e",
        evaluator.SPY_2021_2025_PROFILE_ID:
            "6dcb9a08790a40407622d5a6ec34e5cd8fab5978d8e4cdc0f1ba16fb984063d7",
        evaluator.QQQ_2019_2023_PROFILE_ID:
            "1069bb9717584632cc64a11394ff0cb7bef1d080d4ed0a79ca9eaaf1975596c0",
        evaluator.SPY_2019_2023_PROFILE_ID:
            "75f0841eeddbba74f4ac618b754a6d31698716bb5baf12d96461c8f10ea18cde",
        evaluator.QQQ_2023_2025_PROFILE_ID:
            "a6eeb831372894fd2ba2d95a6a23daefffe86555dd0d93a97a63d977fc27cc05",
        evaluator.SPY_2023_2025_PROFILE_ID:
            "bbc3e88fd66cd8ad93ec1d3e48675c03df75460922e0c21d855dc8aa27ab68e4",
    }
    assert {
        profile_id: leverage_evaluator.require_profile(profile_id)[
            "profile_sha256"
        ]
        for profile_id in leverage_evaluator.V1_PROFILE_IDS
    } == {
        leverage_evaluator.QQQ_2021_2025_PROFILE_ID:
            "e9ed4d6e1df27c38273958ddfc66b4d8d0adc62c5995bb2f5941d7d3540cc68e",
        leverage_evaluator.SPY_2021_2025_PROFILE_ID:
            "ed7e3151daf3ae5868695e7753b0bb47119555124efe457cbca5db26a4208584",
    }
    expected_v2_market_cap_hashes = {
        evaluator.QQQ_2021_2025_V2_PROFILE_ID:
            "71fe35e9a200e61c9c908fe839e244d97bcef89664a921ddaa3dfd09b8a09178",
        evaluator.SPY_2021_2025_V2_PROFILE_ID:
            "0b6587206c68452b7468aff42432cb3b587a0f96cc078fbf57a6473f86feb59d",
        evaluator.QQQ_2019_2023_V2_PROFILE_ID:
            "661d87e282f6c37cc258db7a3e814e5a261369209fc3fc4a96c1769edd71f83d",
        evaluator.SPY_2019_2023_V2_PROFILE_ID:
            "72a4b469d7f8fa79ea4ea62836b6b43000069b5e0a7dca6941af00124ca68f4a",
        evaluator.QQQ_2023_2025_V2_PROFILE_ID:
            "da7f4c75b9504c02f209362d2aebf69188d32cf608ac167fd543beb196067f93",
        evaluator.SPY_2023_2025_V2_PROFILE_ID:
            "e56aa1c7777720ec36b8414ae2525858d0911b7c7954adca292d211c767fa0b3",
    }
    assert {
        profile_id: projection.MARKET_CAP_ALL_PROFILE_SHA256S[profile_id]
        for profile_id in evaluator.V2_PROFILE_IDS
    } == expected_v2_market_cap_hashes
    assert projection.MARKET_CAP_PROFILE_SHA256S == {
        profile_id: evaluator.require_profile(profile_id)["profile_sha256"]
        for profile_id in evaluator.PROFILE_IDS
    }
    assert {
        profile_id: projection.MARKET_CAP_ALL_PROFILE_SHA256S[profile_id]
        for profile_id in evaluator.V3_PROFILE_IDS
    } == {
        evaluator.QQQ_2021_2025_V3_PROFILE_ID: (
            "9efa7e09241f0f20772260e4e6852bb8a71c46cdc77264cfd10e2b569a4b1b00"
        ),
        evaluator.SPY_2021_2025_V3_PROFILE_ID: (
            "8ac07f9fe48d2d6448d4adeb5b2f53c364bad8d4ee3eacd8a23a40a509eb8e38"
        ),
    }
    assert {
        profile_id: leverage_evaluator.require_profile(profile_id)[
            "profile_sha256"
        ]
        for profile_id in leverage_evaluator.V2_PROFILE_IDS
    } == {
        leverage_evaluator.QQQ_2021_2025_V2_PROFILE_ID:
            "a800d1db535ca22fa1bcfc238fbcfabbb463e21b18cf3fc384b606542878192e",
        leverage_evaluator.SPY_2021_2025_V2_PROFILE_ID:
            "07106d52bed121064659b97173f66d1776adf5e72f0f231600d2b7b53299a014",
    }
    assert projection.OBJECTIVE_LEVERAGE_PROFILE_SHA256S == {
        leverage_evaluator.QQQ_2021_2025_V3_PROFILE_ID:
            "b89cae4bdd9c8caa21f0ee8658097550794f5c63ca71ff30d546cf14356abb23",
        leverage_evaluator.SPY_2021_2025_V3_PROFILE_ID:
            "b89ffdb06b56ca5024667e2d6e510026f65d47b00f5bbb0c1f9ba2286d01becc",
    }


@pytest.mark.parametrize(
    ("profile_id", "expected_count", "expect_tilt"),
    (
        (evaluator.QQQ_2021_2025_V4_PROFILE_ID, 9, True),
        (evaluator.QQQ_2021_2025_V2_PROFILE_ID, 8, False),
    ),
)
def test_current_and_preserved_market_cap_source_sets_import_in_isolation(
    package, tmp_path, profile_id, expected_count, expect_tilt
):
    value = projection.build_accepted_risk_preliminary_qc_projection(
        package,
        evaluation_profile_id=profile_id,
    )
    for item in value.source_files:
        if item.project_path != "main.py":
            (tmp_path / item.project_path).write_bytes(item.source_bytes)

    probe = subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(tmp_path)!r}); "
                "import accepted_risk_market_cap_stock_portfolio_qc_runtime "
                "as runtime; "
                "names = runtime.expected_custom_summary_statistic_names("
                f"{profile_id!r}); "
                f"assert len(names) == {expected_count}; "
                "assert ('ARV2_STOCK_PORTFOLIO_TILT_AGGREGATES' in names) "
                f"is {expect_tilt!r}; "
                "assert 'accepted_risk_market_cap_stock_portfolio_tilt' "
                "in sys.modules; "
                "assert 'accepted_risk_preliminary_qc_runtime' "
                "not in sys.modules; "
                "assert 'accepted_risk_regime_rating_evaluator' "
                "not in sys.modules"
            ),
        ),
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


@pytest.mark.parametrize(
    "profile_id", projection.SUPERSEDED_UNSPENT_PROFILE_IDS
)
def test_each_r109_through_r114_fresh_projection_refuses_by_name(
    package, profile_id
):
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match="profile is superseded and cannot be projected",
    ):
        projection.build_accepted_risk_preliminary_qc_projection(
            package,
            evaluation_profile_id=profile_id,
        )


def test_superseded_objective_leverage_profiles_remain_loadable_and_frozen():
    assert projection.OBJECTIVE_LEVERAGE_PROFILE_IDS == (
        leverage_evaluator.PROFILE_IDS
    )
    assert set(projection.OBJECTIVE_LEVERAGE_PROFILE_SHA256S) == set(
        leverage_evaluator.PROFILE_IDS
    )
    assert projection.OBJECTIVE_LEVERAGE_PROJECT_SOURCE_PATHS == (
        *projection.MARKET_CAP_LEGACY_PROJECT_SOURCE_PATHS,
        "accepted_risk_objective_synthetic_leverage_evaluator.py",
        "accepted_risk_objective_synthetic_leverage_qc_runtime.py",
    )
    assert "accepted_risk_market_cap_stock_portfolio_tilt.py" not in (
        projection.OBJECTIVE_LEVERAGE_PROJECT_SOURCE_PATHS
    )
    for profile_id in leverage_evaluator.PROFILE_IDS:
        profile = leverage_evaluator.require_profile(profile_id)
        assert profile["profile_sha256"] == (
            projection.OBJECTIVE_LEVERAGE_PROFILE_SHA256S[profile_id]
        )
        assert profile["base_evaluator_source_sha256"] == (
            leverage_evaluator.BASE_EVALUATOR_SOURCE_SHA256
        )
