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
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local gitignored ARV2 delta package is unavailable")
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


def test_projection_refuses_aliased_extra_moo_capability():
    source = (
        b"def hidden(algorithm):\n"
        b"    submit = algorithm.market_on_open_order\n"
        b"    return submit('SPY', 1)\n"
    )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcProjectionError,
        match="MOO capability inventory",
    ):
        subject._source_file("accepted_risk_simulated_moo_executor.py", source)


def test_projection_refuses_reflected_extra_moo_capability():
    source = (
        b"def hidden(algorithm):\n"
        b"    submit = getattr(algorithm, 'market_on_open_order')\n"
        b"    return submit('SPY', 1)\n"
    )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcProjectionError,
        match="MOO capability inventory",
    ):
        subject._source_file("accepted_risk_simulated_moo_executor.py", source)


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


@pytest.mark.parametrize("role", targets.ROLES)
def test_cap90_runtime_ast_is_exact_and_every_cloud_file_fits_qc(
    loaded_delta, role
):
    local_runtime = Path(runtime.__file__).read_bytes()
    historical = subject.build_accepted_risk_six_universe_order_qc_projection(
        loaded_delta, role=role
    )
    projected = subject.build_accepted_risk_six_universe_order_qc_projection(
        loaded_delta, role=role, variant=runtime.CAP90_VARIANT
    )
    name = "accepted_risk_six_universe_order_qc_runtime.py"
    historical_runtime = next(
        item.source_bytes for item in historical.source_files
        if item.project_path == name
    )
    cloud_runtime = next(
        item.source_bytes for item in projected.source_files
        if item.project_path == name
    )
    assert historical_runtime == local_runtime
    assert cloud_runtime != local_runtime
    assert ast.dump(ast.parse(cloud_runtime), include_attributes=False) == (
        ast.dump(ast.parse(local_runtime), include_attributes=False)
    )
    assert all(
        len(item.source_bytes.decode("ascii"))
        <= subject.MAXIMUM_QC_SOURCE_CHARACTERS
        for item in projected.source_files
    )
    assert len(projected.source_files) == len(historical.source_files) == 13


def test_cap90_ast_normalization_refuses_semantic_rewrite(monkeypatch):
    source = Path(runtime.__file__).read_bytes()
    monkeypatch.setattr(subject.ast, "unparse", lambda _tree: "pass")
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcProjectionError,
        match="AST changed",
    ):
        subject._cap90_qc_runtime_source(source)


def test_cap90_ast_normalization_refuses_qc_file_limit(monkeypatch):
    source = Path(runtime.__file__).read_bytes()
    normalized = subject._cap90_qc_runtime_source(source)
    monkeypatch.setattr(
        subject, "MAXIMUM_QC_SOURCE_CHARACTERS", len(normalized) - 1
    )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcProjectionError,
        match="source limit",
    ):
        subject._cap90_qc_runtime_source(source)


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


def test_cap90_projection_refuses_any_oversized_projected_file(
    loaded_delta, monkeypatch
):
    """Every cap-90 file must fit QC's 64,000-character ceiling, not only the
    AST-normalized runtime: a grown gate, executor, or target builder must
    refuse locally instead of failing at QC's ``files/create``."""

    real_limit = subject.MAXIMUM_QC_SOURCE_CHARACTERS
    normalize = subject._cap90_qc_runtime_source

    def normalize_under_the_real_limit(source):
        # The runtime's own normalization check keeps the real ceiling so the
        # per-file inventory check is the only guard exercised here.
        subject.MAXIMUM_QC_SOURCE_CHARACTERS = real_limit
        try:
            return normalize(source)
        finally:
            subject.MAXIMUM_QC_SOURCE_CHARACTERS = 1_000

    monkeypatch.setattr(
        subject, "_cap90_qc_runtime_source", normalize_under_the_real_limit
    )
    monkeypatch.setattr(subject, "MAXIMUM_QC_SOURCE_CHARACTERS", 1_000)
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcProjectionError,
        match="file limit",
    ):
        subject.build_accepted_risk_six_universe_order_qc_projection(
            loaded_delta,
            role=targets.ROLE_SIGNAL,
            variant=runtime.CAP90_VARIANT,
        )


def test_cap90_projection_refuses_oversized_non_runtime_file(
    loaded_delta, monkeypatch
):
    """The final inventory check also covers a target-builder file.

    The runtime has a separate inner size check. Growing only this different
    projected file makes a runtime-only inventory check an observable defect.
    """

    source_file = subject._source_file
    limit = subject.MAXIMUM_QC_SOURCE_CHARACTERS

    def oversized_target_builder(project_path, source):
        if project_path == "accepted_risk_six_universe_order_targets.py":
            assert len(source) < limit
            padding = limit + 1 - len(source)
            source += b"\n" + b" " * (padding - 1)
        return source_file(project_path, source)

    monkeypatch.setattr(subject, "_source_file", oversized_target_builder)
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcProjectionError,
        match="file limit",
    ):
        subject.build_accepted_risk_six_universe_order_qc_projection(
            loaded_delta,
            role=targets.ROLE_SIGNAL,
            variant=runtime.CAP90_VARIANT,
        )
