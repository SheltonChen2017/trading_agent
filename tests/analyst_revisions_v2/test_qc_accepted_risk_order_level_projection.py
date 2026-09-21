"""Focused source-firewall tests for the simulated-order QC projection."""

from __future__ import annotations

import ast
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
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v12_qc_runtime as v12_runtime,
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


@pytest.mark.parametrize(
    "profile_id", runtime.PROFILE_IDS + v12_runtime.FORCED_EXIT_PROFILE_IDS,
)
def test_projection_is_exact_profile_bound_and_backtest_only(
    delta_package, profile_id
):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=profile_id,
    )
    by_path = {item.project_path: item for item in value.source_files}
    profile = projection._require_profile(profile_id)
    main = by_path["main.py"].source_bytes.decode("ascii")

    assert tuple(sorted(by_path)) == tuple(
        sorted((*projection._project_source_paths(profile_id), "main.py"))
    )
    assert value.profile_sha256 == profile["profile_sha256"]
    assert (
        value.total_source_byte_count + projection.MIN_REVIEW_MARGIN_BYTES
        <= projection._maximum_total_source_bytes(profile_id)
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
    transport_override = (
        "_arv2_runtime_module.MAXIMUM_STATISTIC_BYTES = 8192"
    )
    assert (transport_override in main) is (
        profile_id in (
            runtime.TICKET_PROFILE_IDS
            + runtime.REFLECTED_TICKET_PROFILE_IDS
            + v12_runtime.FORCED_EXIT_PROFILE_IDS
        )
    )
    assert "self.schedule.on(" in main
    assert "self.time_rules.after_market_close(" in main
    if profile_id in (
        runtime.PREOPEN_PROXY_PROFILE_IDS
        + v12_runtime.FORCED_EXIT_PROFILE_IDS
    ):
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
    assert b"numeric_status=profile_id in NUMERIC_PREOPEN_PROXY_PROFILE_IDS" in next(
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


def test_v9_cash_replan_profile_retains_direct_enum_and_review_margin(delta_package):
    v9 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=runtime.CASH_PREOPEN_PROXY_PROFILE_2026_ID,
    )
    v8 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=runtime.ENUM_PREOPEN_PROXY_PROFILE_2026_ID,
    )
    main = next(
        item.source_bytes for item in v9.source_files
        if item.project_path == "main.py"
    )
    assert v9.profile_sha256 != v8.profile_sha256
    assert b"order_status_enum=OrderStatus," in main
    assert b"before_market_open(qqq_benchmark, 10)" in main
    assert max(item.byte_count for item in v9.source_files) <= 64_000
    assert (
        v9.total_source_byte_count + projection.MIN_REVIEW_MARGIN_BYTES
        <= projection.MAX_TOTAL_SOURCE_BYTES
    )


class _ReflectedValue:
    def __init__(self, number, clr_type="OrderStatus"):
        self.number = number
        self.clr_type = clr_type

    def GetType(self):
        return self.clr_type

    def __eq__(self, other):
        return (
            type(other) is _ReflectedValue
            and self.clr_type == other.clr_type
            and self.number == other.number
        )


class _DotNetEnum:
    @staticmethod
    def GetNames(enum_type):
        if getattr(enum_type, "hostile", False):
            raise RuntimeError("hostile reflection")
        return enum_type.names

    @staticmethod
    def GetValues(enum_type):
        return enum_type.values


class _DotNetConvert:
    @staticmethod
    def ToInt32(value):
        return value.number


def _v11_bridge(main_source):
    tree = ast.parse(main_source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_arv2_reflected_order_status"
    )
    namespace = {
        "_Arv2DotNetEnum": _DotNetEnum,
        "_Arv2DotNetConvert": _DotNetConvert,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "main.py", "exec"), namespace)
    return namespace[function.name]


def _v11_bridge_without_guard(main_source, guard_source):
    tree = ast.parse(main_source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_arv2_reflected_order_status"
    )
    refusal = next(
        node for node in ast.walk(function)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.BoolOp)
        and any(
            ast.unparse(item) == guard_source
            for item in node.test.values
        )
    )
    retained = tuple(
        item for item in refusal.test.values
        if ast.unparse(item) != guard_source
    )
    assert len(retained) + 1 == len(refusal.test.values)
    refusal.test.values = list(retained)
    ast.fix_missing_locations(function)
    namespace = {
        "_Arv2DotNetEnum": _DotNetEnum,
        "_Arv2DotNetConvert": _DotNetConvert,
    }
    exec(
        compile(
            ast.Module(body=[function], type_ignores=[]),
            "main.py",
            "exec",
        ),
        namespace,
    )
    return namespace[function.name]


def _reflected_type(*, names=None, values=None, hostile=False):
    expected_names = (
        "New", "Submitted", "PartiallyFilled", "Filled", "Canceled", "None",
        "Invalid", "CancelPending", "UpdateSubmitted",
    )
    expected_values = tuple(
        _ReflectedValue(number) for number in (0, 1, 2, 3, 5, 6, 7, 8, 9)
    )
    return type("ReflectedOrderStatusType", (), {
        "names": expected_names if names is None else names,
        "values": expected_values if values is None else values,
        "hostile": hostile,
    })


def _assert_v11_reflection_guard_is_load_bearing(
    delta_package, *, enum_type, guard_source,
):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=runtime.REFLECTED_TICKET_PROFILE_2026_ID,
    )
    main = next(
        item.source_bytes.decode("ascii") for item in value.source_files
        if item.project_path == "main.py"
    )
    with pytest.raises(
        RuntimeError,
        match=_exact("QC OrderStatus reflected map changed"),
    ):
        _v11_bridge(main)(enum_type)

    reflected = _v11_bridge_without_guard(main, guard_source)(enum_type)
    assert reflected.FILLED.number == 3


def test_v11_reflects_exact_clr_enum_without_changing_v10(delta_package):
    v11 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=runtime.REFLECTED_TICKET_PROFILE_2026_ID,
    )
    v10 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=runtime.TICKET_PROFILE_2026_ID,
    )
    main = next(
        item.source_bytes for item in v11.source_files
        if item.project_path == "main.py"
    )
    v10_main = next(
        item.source_bytes for item in v10.source_files
        if item.project_path == "main.py"
    )
    assert v11.profile_sha256 != v10.profile_sha256
    assert b"from System import Convert as _Arv2DotNetConvert" in main
    assert b"order_status_enum=_arv2_reflected_order_status(OrderStatus)" in main
    assert b"get_order_by_id" not in main
    assert b"self._arv2_driver.on_order_event(event)" in main
    assert b"from System import" not in v10_main
    assert b"order_status_enum=OrderStatus," in v10_main
    assert projection.MAX_TOTAL_SOURCE_BYTES == 290_000
    assert projection.MIN_REVIEW_MARGIN_BYTES == 2_048
    assert v11.total_source_byte_count == 287_697
    fixture_key_length = len("arv2/order-fixture/transport-manifest.json")
    production_total = v11.total_source_byte_count + (72 - fixture_key_length)
    assert production_total == 287_727
    assert (
        projection.MAX_TOTAL_SOURCE_BYTES - production_total
    ) == 2_273
    bridge = _v11_bridge(main.decode("ascii"))
    reflected = bridge(_reflected_type())
    members = runtime._orders.require_qc_order_status_enum_members(reflected)
    assert tuple((member.number, text) for member, text in members) == (
        (0, "New"), (1, "Submitted"), (2, "PartiallyFilled"),
        (3, "Filled"), (5, "Canceled"), (6, "None"), (7, "Invalid"),
        (8, "CancelPending"), (9, "UpdateSubmitted"),
    )
    assert runtime._orders.qc_order_status_enum_text(
        _ReflectedValue(3), members
    ) == "Filled"
    assert runtime._orders.qc_order_status_enum_text("Filled", members) is None
    assert runtime._orders.qc_order_status_enum_text(3, members) is None


def test_v12_adds_only_forced_exit_source_and_retains_exact_v11_bridge(
    delta_package,
):
    v12 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
    )
    v11 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=runtime.REFLECTED_TICKET_PROFILE_2026_ID,
    )
    v12_by_path = {item.project_path: item for item in v12.source_files}
    v11_paths = tuple(item.project_path for item in v11.source_files)
    assert projection.FORCED_EXIT_PROJECT_PATH in v12_by_path
    assert projection.FORCED_EXIT_PROJECT_PATH not in v11_paths
    assert set(v12_by_path) == set(v11_paths) | {
        projection.FORCED_EXIT_PROJECT_PATH,
        projection.V12_RUNTIME_PROJECT_PATH,
    }
    main = v12_by_path[projection.MAIN_PROJECT_PATH].source_bytes
    assert b"from System import Convert as _Arv2DotNetConvert" in main
    assert b"order_status_enum=_arv2_reflected_order_status(OrderStatus)" in main
    assert b"engine_order = self.transactions.get_order_by_id(event.order_id)" in main
    assert b"event, engine_order=engine_order" in main
    bridge = _v11_bridge(main.decode("ascii"))
    reflected = bridge(_reflected_type())
    assert reflected.FILLED.number == 3
    assert (
        v12.total_source_byte_count + projection.MIN_REVIEW_MARGIN_BYTES
        <= projection.MAX_FORCED_EXIT_TOTAL_SOURCE_BYTES
    )
    assert projection.MAX_FORCED_EXIT_TOTAL_SOURCE_BYTES == 325_000
    assert v12.total_source_byte_count == 322_447
    fixture_key_length = len("arv2/order-fixture/transport-manifest.json")
    production_total = v12.total_source_byte_count + (72 - fixture_key_length)
    assert production_total == 322_477
    assert (
        projection.MAX_FORCED_EXIT_TOTAL_SOURCE_BYTES - production_total
    ) == 2_523


def test_v12_total_cap_is_profile_specific_and_load_bearing(
    delta_package, monkeypatch,
):
    legacy = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=runtime.REFLECTED_TICKET_PROFILE_2026_ID,
    )
    v12 = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
    )
    assert projection._maximum_total_source_bytes(legacy.profile_id) == 290_000
    assert (
        projection._maximum_total_source_bytes(v12.profile_id)
        == projection.MAX_FORCED_EXIT_TOTAL_SOURCE_BYTES
    )
    monkeypatch.setattr(
        projection,
        "MAX_FORCED_EXIT_TOTAL_SOURCE_BYTES",
        v12.total_source_byte_count + projection.MIN_REVIEW_MARGIN_BYTES - 1,
    )
    with pytest.raises(
        projection.AcceptedRiskOrderLevelQcProjectionError,
        match="source set exceeds reviewed total size",
    ):
        projection.build_accepted_risk_order_level_qc_projection(
            delta_package, profile_id=v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        )
    assert (
        projection.require_accepted_risk_order_level_qc_projection(legacy)
        is legacy
    )


@pytest.mark.parametrize(
    "enum_type",
    (
        _reflected_type(names=(
            "New", "Submitted", "PartiallyFilled", "Filled", "Canceled", "None",
            "Invalid", "CancelPending",
        )),
        _reflected_type(names=(
            "New", "Submitted", "PartiallyFilled", "Filled", "Canceled", "None",
            "Invalid", "CancelPending", "UpdateSubmitted", "Future",
        ), values=tuple(
            _ReflectedValue(number) for number in (0, 1, 2, 3, 5, 6, 7, 8, 9, 10)
        )),
        _reflected_type(names=(
            "New", "Submitted", "PartiallyFilled", "Filled", "Canceled", "None",
            "Invalid", "CancelPending", "UpdateSubmitted", "Future",
        )),
        _reflected_type(values=tuple(
            _ReflectedValue(number)
            for number in (0, 1, 2, 3, 5, 6, 7, 8, 9, 10)
        )),
        _reflected_type(values=tuple(
            _ReflectedValue(number) for number in (0, 1, 2, 3, 4, 6, 7, 8, 9)
        )),
        _reflected_type(values=(
            _ReflectedValue(0), _ReflectedValue(1), _ReflectedValue(2),
            _ReflectedValue(3), _ReflectedValue(5), _ReflectedValue(6),
            _ReflectedValue(7), _ReflectedValue(8), _ReflectedValue(8),
        )),
        _reflected_type(values=(
            _ReflectedValue(0), _ReflectedValue(1, "WrongStatus"),
            *tuple(_ReflectedValue(number) for number in (2, 3, 5, 6, 7, 8, 9)),
        )),
        _reflected_type(values=tuple(str(number) for number in (0, 1, 2, 3, 5, 6, 7, 8, 9))),
        _reflected_type(values=(0, 1, 2, 3, 5, 6, 7, 8, 9)),
        _reflected_type(hostile=True),
    ),
)
def test_v11_reflection_refuses_missing_extra_alias_wrong_value_type_and_hostility(
    delta_package, enum_type,
):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package, profile_id=runtime.REFLECTED_TICKET_PROFILE_2026_ID,
    )
    main = next(
        item.source_bytes.decode("ascii") for item in value.source_files
        if item.project_path == "main.py"
    )
    with pytest.raises(RuntimeError, match=_exact("QC OrderStatus reflected map changed")):
        _v11_bridge(main)(enum_type)


def test_v11_reflection_requires_exact_string_name_type(delta_package):
    class StringSubclass(str):
        pass

    names = list(_reflected_type().names)
    names[0] = StringSubclass(names[0])
    _assert_v11_reflection_guard_is_load_bearing(
        delta_package,
        enum_type=_reflected_type(names=tuple(names)),
        guard_source="any((type(name) is not str for name in names))",
    )


def test_v11_reflection_requires_exact_integer_conversion_type(delta_package):
    values = list(_reflected_type().values)
    values[1] = _ReflectedValue(True)
    _assert_v11_reflection_guard_is_load_bearing(
        delta_package,
        enum_type=_reflected_type(values=tuple(values)),
        guard_source="any((type(number) is not int for number in numbers))",
    )


def test_v11_reflection_requires_homogeneous_python_wrapper_type(delta_package):
    class ReflectedValueSubclass(_ReflectedValue):
        pass

    values = list(_reflected_type().values)
    values[1] = ReflectedValueSubclass(1)
    _assert_v11_reflection_guard_is_load_bearing(
        delta_package,
        enum_type=_reflected_type(values=tuple(values)),
        guard_source=(
            "any((type(value) is not type(values[0]) for value in values))"
        ),
    )


def test_v11_reflection_refuses_pairwise_alias_equality(delta_package):
    class AliasedReflectedValue(_ReflectedValue):
        def __eq__(self, other):
            if type(other) is not AliasedReflectedValue:
                return False
            if self.clr_type != other.clr_type:
                return False
            return (
                self.number == other.number
                or {self.number, other.number} == {0, 1}
            )

    values = tuple(
        AliasedReflectedValue(number)
        for number in (0, 1, 2, 3, 5, 6, 7, 8, 9)
    )
    _assert_v11_reflection_guard_is_load_bearing(
        delta_package,
        enum_type=_reflected_type(values=values),
        guard_source=(
            "any((value == prior for index, value in enumerate(values) "
            "for prior in values[:index]))"
        ),
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


def test_firewall_allows_only_exact_v12_read_only_engine_order_lookup():
    accepted = (
        "from accepted_risk_qqq_order_level_v12_qc_runtime import (\n"
        "    AcceptedRiskQqqOrderLevelV12QcRuntime as AcceptedRiskQqqOrderLevelQcRuntime,\n"
        "    STARTING_CASH,\n"
        ")\n"
        "class Algorithm:\n"
        "    def initialize(self):\n"
        "        self._arv2_driver = AcceptedRiskQqqOrderLevelQcRuntime(\n"
        "            self, profile_id='arv2-qqq-order-level-tilt-2026-cutoff-v12',\n"
        "        )\n"
        "    def on_order_event(self, event):\n"
        "        engine_order = self.transactions.get_order_by_id(event.order_id)\n"
        "        self._driver.on_order_event(event, engine_order=engine_order)\n"
    )
    projection._audit_cloud_capabilities(
        accepted, projection.MAIN_PROJECT_PATH
    )
    refused = (
        (accepted, projection.RUNTIME_PROJECT_PATH),
        (accepted.replace("event.order_id)", "event.other_id)"), projection.MAIN_PROJECT_PATH),
        (accepted.replace("get_order_by_id", "cancel_order"), projection.MAIN_PROJECT_PATH),
        (accepted.replace(".transactions", ".brokerage"), projection.MAIN_PROJECT_PATH),
        (accepted.replace("engine_order =", "other_order ="), projection.MAIN_PROJECT_PATH),
        (
            accepted.replace(
                "arv2-qqq-order-level-tilt-2026-cutoff-v12",
                runtime.REFLECTED_TICKET_PROFILE_2026_ID,
            ),
            projection.MAIN_PROJECT_PATH,
        ),
        (
            accepted.replace(
                "accepted_risk_qqq_order_level_v12_qc_runtime",
                "accepted_risk_qqq_order_level_qc_runtime",
            ),
            projection.MAIN_PROJECT_PATH,
        ),
        (
            accepted.replace(
                "get_order_by_id(event.order_id)",
                "get_order_by_id(event.order_id, include_tag=True)",
            ),
            projection.MAIN_PROJECT_PATH,
        ),
        (
            "class Algorithm:\n"
            "    def on_order_event(self, event):\n"
            "        lookup = self.transactions.get_order_by_id\n"
            "        engine_order = lookup(event.order_id)\n",
            projection.MAIN_PROJECT_PATH,
        ),
    )
    for source, path in refused:
        with pytest.raises(
            projection.AcceptedRiskOrderLevelQcProjectionError
        ):
            projection._audit_cloud_capabilities(source, path)


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


def test_firewall_allows_only_the_exact_v11_system_enum_import_in_main():
    projection._audit_cloud_capabilities(
        "from System import Convert as _Arv2DotNetConvert, Enum as _Arv2DotNetEnum\n",
        projection.MAIN_PROJECT_PATH,
    )
    for source, path in (
        ("import System\n", projection.MAIN_PROJECT_PATH),
        ("from System import IO\n", projection.MAIN_PROJECT_PATH),
        (
            "from System import Convert as _Arv2DotNetConvert, Enum as _Arv2DotNetEnum\n",
            projection.RUNTIME_PROJECT_PATH,
        ),
        (
            "from System import Enum as _Arv2DotNetEnum, Convert as _Arv2DotNetConvert\n",
            projection.MAIN_PROJECT_PATH,
        ),
    ):
        with pytest.raises(
            projection.AcceptedRiskOrderLevelQcProjectionError,
            match="imports a forbidden capability",
        ):
            projection._audit_cloud_capabilities(source, path)


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


@pytest.mark.parametrize(
    ("profile_id", "statistic_limit"),
    (
        (runtime.PROFILE_IDS[0], 4096),
        (runtime.TICKET_PROFILE_2026_ID, 8192),
        (runtime.REFLECTED_TICKET_PROFILE_2026_ID, 8192),
        (v12_runtime.FORCED_EXIT_PROFILE_2026_ID, 8192),
    ),
)
def test_generated_main_imports_from_exact_flat_qc_projection(
    tmp_path: Path, delta_package, profile_id, statistic_limit
):
    value = projection.build_accepted_risk_order_level_qc_projection(
        delta_package,
        profile_id=profile_id,
    )
    for item in value.source_files:
        (tmp_path / item.project_path).write_bytes(item.source_bytes)
    (tmp_path / "AlgorithmImports.py").write_text(
        "class FeeModel:\n    pass\n\nclass QCAlgorithm:\n    pass\n",
        encoding="ascii",
    )
    (tmp_path / "System.py").write_text(
        "class Convert:\n    pass\n\nclass Enum:\n    pass\n",
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
                "assert main.ARV2QqqOrderLevelAlgorithm;"
                "import accepted_risk_qqq_order_level_qc_runtime as runtime;"
                f"assert runtime.MAXIMUM_STATISTIC_BYTES == {statistic_limit}"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
