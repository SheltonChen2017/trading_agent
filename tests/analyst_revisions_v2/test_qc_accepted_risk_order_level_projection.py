"""Focused source-firewall tests for the simulated-order QC projection."""

from __future__ import annotations

import dataclasses
import hashlib
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import (
    accepted_risk_delta_order_package as delta_package_builder,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_qc_projection as projection,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_package as package_builder,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as runtime,
)


def _exact(message: str) -> str:
    return "^" + re.escape(message) + "$"


@pytest.fixture
def delta_package(monkeypatch):
    lineage = {"schema": delta_package_builder.LINEAGE_SCHEMA, "fixture": True}
    lineage_sha256 = hashlib.sha256(canonical_json_bytes(lineage)).hexdigest()
    activation = SimpleNamespace(
        role="activation_manifest",
        activation_manifest=True,
        object_store_key="arv2/order-fixture/transport-manifest.json",
        content_sha256="a" * 64,
        byte_count=1234,
    )
    package = SimpleNamespace(
        package_id="arv2-preliminary-qc-package-order-fixture",
        package_sha256="b" * 64,
        source_disposition_sha256=lineage_sha256,
        upload_objects=(activation,),
    )
    monkeypatch.setattr(
        package_builder,
        "require_accepted_risk_preliminary_package",
        lambda candidate: candidate,
    )
    return delta_package_builder.AcceptedRiskDeltaOrderPackage(
        package=package,
        lineage=lineage,
        lineage_sha256=lineage_sha256,
        prior_contribution_count=1,
        delta_contribution_count=1,
        extended_membership_count=1,
        decision_cutoff_session=delta_package_builder.DELTA_DECISION_END_SESSION,
        final_execution_session=delta_package_builder.FINAL_EXECUTION_SESSION,
        current_snapshot_identity_only=True,
        refreshed_security_master=False,
        provider_access=False,
        quantconnect_access=False,
        outcome_access=False,
        orders=False,
        trading=False,
    )


@pytest.mark.parametrize("profile_id", runtime.PROFILE_IDS)
def test_projection_is_exact_profile_bound_and_backtest_only(
    delta_package, profile_id
):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=profile_id,
    )
    by_path = {item.project_path: item for item in value.source_files}
    profile = runtime.require_qqq_order_level_profile(profile_id)
    main = by_path["main.py"].source_bytes.decode("ascii")

    assert tuple(sorted(by_path)) == tuple(
        sorted((*projection.PROJECT_SOURCE_PATHS, "main.py"))
    )
    assert value.profile_sha256 == profile["profile_sha256"]
    assert (
        value.total_source_byte_count + projection.MIN_REVIEW_MARGIN_BYTES
        <= projection.MAX_TOTAL_SOURCE_BYTES
    )
    assert max(item.byte_count for item in value.source_files) <= (
        projection.MAX_SOURCE_FILE_BYTES
    )
    assert value.backtest_only is True
    assert value.simulated_order_submission is True
    assert value.market_on_open_orders_only is True
    assert value.live_orders is False
    assert value.paper_orders is False
    assert value.funded_orders is False
    assert value.deployment is False
    assert value.broker_credentials is False
    assert value.trading is False
    assert f"profile_id={profile_id!r}" in main
    start = tuple(
        int(part) for part in profile["evaluation_start_session"].split("-")
    )
    assert f"set_start_date({start[0]}, {start[1]}, {start[2]})" in main
    assert "set_end_date(2026, 9, 17)" in main
    assert "market_on_open_order" not in main
    assert "self.schedule.on(" in main
    assert "self.time_rules.after_market_close(" in main
    if profile_id in runtime.PREOPEN_PROXY_PROFILE_IDS:
        assert "self.time_rules.before_market_open(qqq_benchmark, 10)" in main
        assert "self._arv2_driver.on_before_open" in main
        assert main.count("extended_market_hours=True") == 1
    else:
        assert "before_market_open" not in main
        assert "extended_market_hours=True" not in main
    assert "class Arv2TenBpsFeeModel(FeeModel):" in main
    assert "parameters.order.absolute_quantity" in main
    assert "parameters.security.open" in main
    assert "parameters.security.price" not in main
    assert "price * quantity * MODELED_FEE_RATE_PER_SIDE" in main
    assert "self.set_cash(STARTING_CASH)" in main
    assert "AddUniverse" not in main
    assert "fundamental_universe" not in main
    assert "qqq_constituent_universe=qqq_constituent_universe" in main
    assert "trade_bar_type=TradeBar" in main
    assert "daily_resolution=Resolution.DAILY" in main
    assert (
        "total_return_normalization=DataNormalizationMode.TOTAL_RETURN" in main
    )
    assert (
        projection.require_accepted_risk_order_level_qc_projection(value)
        is value
    )


def test_generated_fee_uses_moo_trade_bar_open_not_minute_close(
    tmp_path: Path, delta_package
):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.PROFILE_IDS[0],
    )
    for item in value.source_files:
        (tmp_path / item.project_path).write_bytes(item.source_bytes)
    (tmp_path / "AlgorithmImports.py").write_text(
        (
            "class FeeModel:\n    pass\n\n"
            "class QCAlgorithm:\n    pass\n\n"
            "class CashAmount:\n"
            "    def __init__(self, amount, currency):\n"
            "        self.amount = amount\n"
            "        self.currency = currency\n\n"
            "class OrderFee:\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n"
        ),
        encoding="ascii",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys;"
                "from types import SimpleNamespace;"
                f"sys.path.insert(0, {str(tmp_path)!r});"
                "import main;"
                "parameters=SimpleNamespace("
                "security=SimpleNamespace(open='100',price='111'),"
                "order=SimpleNamespace(absolute_quantity='10'));"
                "fee=main.Arv2TenBpsFeeModel().get_order_fee(parameters);"
                "assert str(fee.value.amount)=='1.000';"
                "assert fee.value.currency=='USD'"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_execution_matched_source_closure_keeps_review_margin(
    delta_package, monkeypatch
):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.PROFILE_IDS[0],
    )
    assert value.total_source_byte_count > 256_000
    assert (
        value.total_source_byte_count + projection.MIN_REVIEW_MARGIN_BYTES
        <= projection.MAX_TOTAL_SOURCE_BYTES
    )
    monkeypatch.setattr(
        projection, "MAX_TOTAL_SOURCE_BYTES",
        value.total_source_byte_count + projection.MIN_REVIEW_MARGIN_BYTES - 1,
    )
    with pytest.raises(
        projection.AcceptedRiskOrderLevelQcProjectionError,
        match="source set exceeds reviewed total size",
    ):
        projection.build_accepted_risk_order_level_qc_projection(
            delta_package, profile_id=runtime.PROFILE_IDS[0],
        )
    monkeypatch.setattr(projection, "MAX_TOTAL_SOURCE_BYTES", 256_000)
    with pytest.raises(
        projection.AcceptedRiskOrderLevelQcProjectionError,
        match="source set exceeds reviewed total size",
    ):
        projection.build_accepted_risk_order_level_qc_projection(
            delta_package,
            profile_id=runtime.PROFILE_IDS[0],
        )


def test_proxy_projection_keeps_file_and_total_margin_and_raw_executable_qqq(
    delta_package,
):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.PROXY_PROFILE_2026_ID,
    )
    assert max(item.byte_count for item in value.source_files) <= 64_000
    assert (
        value.total_source_byte_count + projection.MIN_REVIEW_MARGIN_BYTES
        <= projection.MAX_TOTAL_SOURCE_BYTES
    )
    main = next(item.source_bytes for item in value.source_files if item.project_path == "main.py")
    assert b"data_normalization_mode=DataNormalizationMode.RAW" in main
    assert b"data_normalization_mode=DataNormalizationMode.TOTAL_RETURN" in main
    assert b"self.set_benchmark(qqq_benchmark)" in main


def test_v6_preopen_schedule_is_load_bearing_and_legacy_main_is_stable(
    delta_package,
):
    v6 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.PREOPEN_PROXY_PROFILE_2026_ID,
    )
    v5 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.PROXY_PROFILE_2026_ID,
    )
    v6_main = next(
        item.source_bytes for item in v6.source_files
        if item.project_path == "main.py"
    )
    v5_main = next(
        item.source_bytes for item in v5.source_files
        if item.project_path == "main.py"
    )
    assert v6_main.count(b"self.schedule.on(") == 2
    assert v5_main.count(b"self.schedule.on(") == 1
    assert b"before_market_open(qqq_benchmark, 10)" in v6_main
    assert b"before_market_open" not in v5_main
    assert v6_main.count(b"extended_market_hours=True") == 1
    assert b"extended_market_hours=True" not in v5_main
    assert v6_main != v5_main


def test_v7_status_codec_keeps_v6_preopen_schedule_and_distinct_profile(
    delta_package,
):
    v7 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID,
    )
    v6 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.PREOPEN_PROXY_PROFILE_2026_ID,
    )
    v7_main = next(
        item.source_bytes for item in v7.source_files
        if item.project_path == "main.py"
    )
    v6_main = next(
        item.source_bytes for item in v6.source_files
        if item.project_path == "main.py"
    )
    assert v7.profile_sha256 != v6.profile_sha256
    assert v7_main.count(b"self.schedule.on(") == v6_main.count(b"self.schedule.on(") == 2
    assert b"before_market_open(qqq_benchmark, 10)" in v7_main
    assert v7_main.count(b"extended_market_hours=True") == 1
    assert b"numeric_status=True" in next(
        item.source_bytes for item in v7.source_files
        if item.project_path == projection.RUNTIME_PROJECT_PATH
    )


def test_v8_injects_qc_order_status_enum_only_for_new_profile(delta_package):
    v8 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=runtime.ENUM_PREOPEN_PROXY_PROFILE_2026_ID,
    )
    v7 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID,
    )
    v8_main = next(
        item.source_bytes for item in v8.source_files
        if item.project_path == "main.py"
    )
    v7_main = next(
        item.source_bytes for item in v7.source_files
        if item.project_path == "main.py"
    )
    assert v8.profile_sha256 != v7.profile_sha256
    assert b"order_status_enum=OrderStatus," in v8_main
    assert b"order_status_enum=" not in v7_main
    assert v8_main.count(b"extended_market_hours=True") == 1
    assert v8_main.count(b"self.schedule.on(") == 2
    assert max(item.byte_count for item in v8.source_files) <= 64_000
    assert projection.MIN_REVIEW_MARGIN_BYTES == 2_048
    assert (
        v8.total_source_byte_count + projection.MIN_REVIEW_MARGIN_BYTES
        <= projection.MAX_TOTAL_SOURCE_BYTES
    )


def test_projection_disclosure_is_load_bearing(delta_package):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.PROFILE_IDS[0],
    )
    with pytest.raises(
        projection.AcceptedRiskOrderLevelQcProjectionError,
        match=_exact("order-level QC projection disclosure or inventory changed"),
    ):
        projection.require_accepted_risk_order_level_qc_projection(
            dataclasses.replace(value, live_orders=True)
        )


def test_firewall_allows_only_direct_runtime_market_on_open_and_live_read():
    source = """
class Runtime:
    def submit(self):
        if self._algorithm.live_mode:
            raise RuntimeError("backtest only")
        return self._algorithm.market_on_open_order("QQQ", 1)
"""
    projection._audit_cloud_capabilities(
        source,
        projection.RUNTIME_PROJECT_PATH,
    )


@pytest.mark.parametrize(
    "source",
    (
        "self._algorithm.market_order('QQQ', 1)",
        "self._algorithm.limit_order('QQQ', 1, 100)",
        "self._algorithm.stop_market_order('QQQ', 1, 100)",
        "self._algorithm.set_holdings('QQQ', 1)",
        "self._algorithm.liquidate()",
        "self._algorithm.transactions.cancel_open_orders()",
        "ticket.cancel()",
    ),
)
def test_firewall_rejects_every_non_moo_order_family(source):
    with pytest.raises(
        projection.AcceptedRiskOrderLevelQcProjectionError,
        match="forbidden operational capability",
    ):
        projection._audit_cloud_capabilities(
            "def f(self):\n    " + source + "\n",
            projection.RUNTIME_PROJECT_PATH,
        )


def test_firewall_rejects_moo_outside_runtime_and_indirect_alias():
    direct = "def f(self):\n    self._algorithm.market_on_open_order('QQQ', 1)\n"
    alias = (
        "def f(self):\n"
        "    submit = self._algorithm.market_on_open_order\n"
        "    submit('QQQ', 1)\n"
    )
    for source, path in (
        (direct, "main.py"),
        (alias, projection.RUNTIME_PROJECT_PATH),
    ):
        with pytest.raises(
            projection.AcceptedRiskOrderLevelQcProjectionError,
            match="permitted only as the runtime's direct simulated call",
        ):
            projection._audit_cloud_capabilities(source, path)


def test_firewall_rejects_locally_defined_non_moo_order_wrapper():
    source = (
        "def market_order(symbol, quantity):\n"
        "    return (symbol, quantity)\n\n"
        "market_order('QQQ', 1)\n"
    )
    with pytest.raises(
        projection.AcceptedRiskOrderLevelQcProjectionError,
        match="forbidden operational capability",
    ):
        projection._audit_cloud_capabilities(source, "fixture.py")


def test_firewall_rejects_live_write_and_paper_broker_deploy_references():
    cases = (
        "def f(self):\n    self._algorithm.live_mode = False\n",
        "def f(self):\n    self._algorithm.set_brokerage_model('x')\n",
        "def f(self):\n    self._algorithm.deploy()\n",
        "def f(self):\n    return self._algorithm.paper_trading\n",
    )
    for source in cases:
        with pytest.raises(projection.AcceptedRiskOrderLevelQcProjectionError):
            projection._audit_cloud_capabilities(
                source,
                projection.RUNTIME_PROJECT_PATH,
            )


def test_firewall_rejects_dynamic_network_and_object_store_writes():
    cases = (
        "import requests\n",
        "def f():\n    return getattr(object(), 'x')\n",
        "def f(self):\n    self._algorithm.object_store.save('k', 'v')\n",
    )
    for source in cases:
        with pytest.raises(projection.AcceptedRiskOrderLevelQcProjectionError):
            projection._audit_cloud_capabilities(
                source,
                projection.RUNTIME_PROJECT_PATH,
            )


def test_firewall_allows_re_compile_but_rejects_builtin_compile():
    projection._audit_cloud_capabilities(
        "import re\nPATTERN = re.compile(r'x')\n",
        "fixture.py",
    )
    with pytest.raises(
        projection.AcceptedRiskOrderLevelQcProjectionError,
        match="dynamic capability",
    ):
        projection._audit_cloud_capabilities(
            "VALUE = compile('1', 'x', 'eval')\n",
            "fixture.py",
        )


def test_qc_prelude_compilation_and_future_import_regression():
    accepted = projection._validate_source(
        "fixture.py",
        b"VALUE = 1\n",
    )
    assert accepted.project_path == "fixture.py"
    with pytest.raises(
        projection.AcceptedRiskOrderLevelQcProjectionError,
        match="future-import guard",
    ):
        projection._validate_source(
            "fixture.py",
            b"from __future__ import annotations\nVALUE = 1\n",
        )


def test_generated_main_imports_from_exact_flat_qc_projection(
    tmp_path: Path, delta_package
):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.PROFILE_IDS[0],
    )
    for item in value.source_files:
        (tmp_path / item.project_path).write_bytes(item.source_bytes)
    (tmp_path / "AlgorithmImports.py").write_text(
        "class FeeModel:\n    pass\n\nclass QCAlgorithm:\n    pass\n",
        encoding="ascii",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys;"
                f"sys.path.insert(0, {str(tmp_path)!r});"
                "import main;"
                "assert main.ARV2QqqOrderLevelAlgorithm"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
