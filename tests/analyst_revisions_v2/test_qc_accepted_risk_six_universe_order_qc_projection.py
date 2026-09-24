import ast
import hashlib
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_delta_order_package as delta,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_projection as subject,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_targets as targets,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_runtime as runtime,
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


@pytest.mark.parametrize("role", targets.ROLES)
def test_projection_is_exact_role_specific_and_capability_bounded(
    loaded_delta, role
):
    value = subject.build_accepted_risk_six_universe_order_qc_projection(
        loaded_delta,
        role=role,
    )
    record = value.to_record()
    assert value.role == role
    assert value.profile_id == "arv2-six-universe-order-" + role + "-v2"
    assert value.package_sha256 == delta.EXPECTED_DELTA_PACKAGE_SHA256
    assert value.package_lineage_sha256 == delta.EXPECTED_DELTA_LINEAGE_SHA256
    assert value.total_source_byte_count == sum(
        item.byte_count for item in value.source_files
    )
    assert (
        value.total_source_byte_count + subject.MINIMUM_REVIEW_MARGIN_BYTES
        <= subject.MAXIMUM_TOTAL_SOURCE_BYTES
    )
    assert tuple(item.project_path for item in value.source_files) == tuple(
        sorted(item.project_path for item in value.source_files)
    )
    assert len({item.project_path for item in value.source_files}) == len(
        value.source_files
    )
    assert record["backtest_only"] is True
    assert record["simulated_order_submission"] is True
    assert record["market_on_open_orders_only"] is True
    assert record["live_orders"] is False
    assert record["paper_orders"] is False
    assert record["funded_orders"] is False
    assert record["deployment"] is False
    assert record["trading"] is False

    main = next(
        item.source_bytes
        for item in value.source_files
        if item.project_path == subject.MAIN_PROJECT_PATH
    ).decode("ascii")
    historical_main_sha256s = {
        targets.ROLE_SIGNAL: (
            "fc7ea724c6bc05ab942a7338bbb7e6d5039a9b75c185c3b612939c7706961cc3"
        ),
        targets.ROLE_MATCHED: (
            "fa1b83e386ad998f368ace18150a38f7df75b32324f0ee7eb079e8b13d803b56"
        ),
        targets.ROLE_SIX_ETF_BASKET: (
            "89f59da3628561b198b3eb8ccb10d0660855bbecbe0899834b53b48ce41ac0f5"
        ),
    }
    assert hashlib.sha256(main.encode("ascii")).hexdigest() == (
        historical_main_sha256s[role]
    )
    assert "role=" + repr(role) in main
    assert "market_on_open_order" not in main
    assert "before_market_open(benchmark, 10)" in main
    assert "set_start_date(2020, 11, 1)" in main
    assert "set_end_date(2025, 12, 31)" in main
    assert "(\"Canceled\", 5)" in main
    assert "self.settings.seed_initial_prices = True" in main
    assert "extended_market_hours=True" not in main
    assert "split_occurred_type=SplitType.SPLIT_OCCURRED" in main
    assert "def on_splits(self, splits):" in main

    runtime = next(
        item.source_bytes
        for item in value.source_files
        if item.project_path
        == "accepted_risk_six_universe_order_qc_runtime.py"
    ).decode("ascii")
    assert runtime.count("remove_security(") == 1
    assert "MAXIMUM_ACTIVE_DYNAMIC_SECURITY_COUNT = 128" in runtime


def test_projection_embeds_every_local_source_byte_for_byte(loaded_delta):
    value = subject.build_accepted_risk_six_universe_order_qc_projection(
        loaded_delta,
        role=targets.ROLE_SIGNAL,
    )
    root = Path(subject.__file__).resolve().parent
    for item in value.source_files:
        if item.project_path == subject.MAIN_PROJECT_PATH:
            continue
        assert item.source_bytes == (root / item.project_path).read_bytes()


@pytest.mark.parametrize(
    "source",
    [
        b"import requests\n",
        b"import urllib.request\n",
        b"def x():\n    market_order('SPY', 1)\n",
        b"def x():\n    set_holdings('SPY', 1)\n",
        b"def x():\n    object_store.save_bytes('x', b'x')\n",
        b"def x():\n    remove_security('SPY')\n",
    ],
)
def test_projection_capability_audit_refuses_expansion(source):
    with pytest.raises(subject.AcceptedRiskSixUniverseOrderQcProjectionError):
        subject._source_file("hostile.py", source)


def test_projection_refuses_unfrozen_role(loaded_delta):
    with pytest.raises(subject.AcceptedRiskSixUniverseOrderQcProjectionError):
        subject.build_accepted_risk_six_universe_order_qc_projection(
            loaded_delta,
            role="top5",
        )


@pytest.mark.parametrize("role", targets.ROLES)
def test_cap90_projection_binds_new_profile_and_runtime_selection(
    loaded_delta, role
):
    old = subject.build_accepted_risk_six_universe_order_qc_projection(
        loaded_delta,
        role=role,
    )
    value = subject.build_accepted_risk_six_universe_order_qc_projection(
        loaded_delta,
        role=role,
        variant=runtime.CAP90_VARIANT,
    )
    record = value.to_record()
    assert old.schema == subject.PROJECTION_SCHEMA
    assert "variant" not in old.to_record()
    assert value.schema == subject.CAP90_PROJECTION_SCHEMA
    assert record["variant"] == runtime.CAP90_VARIANT
    assert value.profile_id == (
        "arv2-six-universe-order-" + role + "-cap90-exploratory-v3"
    )
    assert value.profile_sha256 == runtime.require_six_universe_order_profile(
        role, variant=runtime.CAP90_VARIANT
    )["profile_sha256"]
    assert value.projection_sha256 != old.projection_sha256
    assert value.package_sha256 == old.package_sha256
    assert value.package_lineage_sha256 == old.package_lineage_sha256
    assert [item.project_path for item in value.source_files] == [
        item.project_path for item in old.source_files
    ]
    main = next(
        item.source_bytes.decode("ascii")
        for item in value.source_files
        if item.project_path == subject.MAIN_PROJECT_PATH
    )
    old_main = next(
        item.source_bytes.decode("ascii")
        for item in old.source_files
        if item.project_path == subject.MAIN_PROJECT_PATH
    )
    assert "role=" + repr(role) in main
    assert "variant=" + repr(runtime.CAP90_VARIANT) in main
    assert "variant=" not in old_main
    assert "market_on_open_order" not in main
    # An order run needs the final Dec 31 account mark.  R-180's earlier
    # Dec 30 endpoint was safe only for its counts-only Dec 29 decision.
    assert "set_end_date(2025, 12, 31)" in main
    assert record["backtest_only"] is True
    assert record["live_orders"] is False
    assert record["paper_orders"] is False
    assert record["funded_orders"] is False


@pytest.mark.parametrize("variant", ["", "cap95", "r177 ", None, 1])
def test_projection_refuses_unfrozen_variant(loaded_delta, variant):
    with pytest.raises(subject.AcceptedRiskSixUniverseOrderQcProjectionError):
        subject.build_accepted_risk_six_universe_order_qc_projection(
            loaded_delta,
            role=targets.ROLE_SIGNAL,
            variant=variant,
        )


def test_projection_source_file_bound_is_inclusive_and_finite():
    exact = b"#" + b"x" * (subject.MAXIMUM_SOURCE_FILE_BYTES - 2) + b"\n"
    item = subject._source_file("boundary.py", exact)
    assert item.byte_count == subject.MAXIMUM_SOURCE_FILE_BYTES
    with pytest.raises(subject.AcceptedRiskSixUniverseOrderQcProjectionError):
        subject._source_file("boundary.py", exact + b"#")


def test_projection_source_is_qc_prelude_safe():
    source = Path(subject.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module == "__future__"
        for node in ast.walk(tree)
    )
    compile(source, subject.__file__, "exec")
