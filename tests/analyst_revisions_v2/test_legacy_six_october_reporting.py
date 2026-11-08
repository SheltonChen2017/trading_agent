"""Synthetic same-job reporting tests; no market, QC or account observations."""

import ast
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import legacy_six_october_reporting as m


ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "research/analyst_revisions_v2_qc/accepted_risk_six_universe_order_qc_runtime.py"
PROFILE = "a" * 64
PATH_SCHEMA = "synthetic-projected-legacy-account-path-v1"


def _legacy_functions():
    """Compile the actual frozen pure functions, without its cloud imports."""
    tree = ast.parse(OLD.read_text(encoding="utf-8"))
    wanted = {
        "AcceptedRiskSixUniverseOrderQcRuntimeError", "_error", "_canonical",
        "_sha", "_decimal", "_decimal_text", "_population_metrics", "_decimal_path_sha256",
    }
    selected = [node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in wanted]
    assert {node.name for node in selected} == wanted
    namespace = {}
    exec("import hashlib, json\nfrom decimal import Decimal, DecimalException, localcontext", namespace)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(OLD), "exec"), namespace)
    return namespace


@pytest.fixture(scope="module")
def legacy():
    return _legacy_functions()


def _synthetic_axis():
    # A synthetic caller-supplied axis, not a reconstruction of the NYSE calendar.
    value = date(2021, 1, 4)
    result = []
    while value <= date(2026, 10, 13):
        if value.weekday() < 5 and value.isoformat() != "2026-01-01":
            result.append(value.isoformat())
        value += timedelta(days=1)
    return tuple(result)


def _navs(axis):
    nav = Decimal("1000000")
    result = {}
    with localcontext() as context:
        context.prec = 96
        for ordinal, session in enumerate(axis):
            nav = +(nav + Decimal((ordinal % 11) - 4) * Decimal("7.25"))
            result[session] = nav
    # Explicit synthetic discontinuities make omission of either prior boundary observable.
    result["2025-12-31"] = Decimal("1000000")
    result["2026-01-02"] = Decimal("800000")
    result["2026-09-25"] = Decimal("900000")
    result["2026-09-28"] = Decimal("720000")
    result["2026-10-13"] = Decimal("990000")
    return result


@pytest.fixture
def case(legacy):
    axis = _synthetic_axis()
    navs = _navs(axis)
    rows = tuple(navs.items())
    aggregate = {
        "schema": "synthetic-legacy-summary-v1",
        "profile_sha256": PROFILE,
        "account": legacy["_population_metrics"](rows),
        "account_observation_path_sha256": legacy["_decimal_path_sha256"](PATH_SCHEMA, rows),
        "run_valid": True,
        "preliminary": True,
        "backtest_only": True,
        **{key: False for key in
           ("formal", "live_orders", "paper_orders", "funded_orders", "deployment", "trading")},
        "execution": {"run_valid": True, "source_gate": "synthetic-only"},
    }
    kwargs = {
        "evaluation_sessions": axis,
        "ar_percent": 100,
        "source_profile_sha256": PROFILE,
        "account_path_schema": PATH_SCHEMA,
        "legacy_aggregate": aggregate,
    }
    return navs, kwargs


def test_every_period_uses_exact_same_job_path_and_legacy_arithmetic(case, legacy):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    axis = kwargs["evaluation_sessions"]
    by_id = {value["period_id"]: value for value in report["periods"]}
    scopes = {
        m.PERIOD_IDS[0]: axis,
        m.PERIOD_IDS[1]: tuple(s for s in axis if s <= "2025-12-31"),
        m.PERIOD_IDS[2]: ("2025-12-31",) + tuple(s for s in axis if s > "2025-12-31"),
        m.PERIOD_IDS[3]: ("2025-12-31",) + tuple(s for s in axis if "2025-12-31" < s <= "2026-09-25"),
        m.PERIOD_IDS[4]: ("2026-09-25",) + tuple(s for s in axis if s >= "2026-09-28"),
    }
    for period_id, sessions in scopes.items():
        rows = tuple((session, navs[session]) for session in sessions)
        assert by_id[period_id]["account"] == legacy["_population_metrics"](rows)
        assert by_id[period_id]["nav_path_sha256"] == legacy["_decimal_path_sha256"](
            m.PERIOD_PATH_SCHEMA, rows
        )
    assert by_id[m.PERIOD_IDS[0]]["account"] == kwargs["legacy_aggregate"]["account"]
    assert by_id[m.PERIOD_IDS[2]]["account"]["starting_equity"] == "1000000"
    assert by_id[m.PERIOD_IDS[4]]["account"]["starting_equity"] == "900000"
    assert Decimal(by_id[m.PERIOD_IDS[2]]["account"]["maximum_drawdown"]) <= Decimal("-0.2")
    assert by_id[m.PERIOD_IDS[4]]["account"]["maximum_drawdown"] == "-0.2"
    assert by_id[m.PERIOD_IDS[4]]["account"]["cumulative_return"] == "0.1"
    assert len(m.canonical_report_bytes(report)) < 8192
    m.validate_report(report, **kwargs)


@pytest.mark.parametrize("arm", m.AR_PERCENTAGES)
def test_all_seven_fixed_old_arms_are_reporting_only(case, arm):
    navs, kwargs = case
    kwargs["ar_percent"] = arm
    report = m.build_report(navs, **kwargs)
    assert report["ar_percent"] == arm
    assert report["reporting_only"] is True
    assert report["legacy_validity_gates_preserved"] is True
    assert all(report[key] is False for key in m.FALSE_FLAGS)


def test_input_and_result_mutation_do_not_rewrite_each_other(case):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    original = m.canonical_report_bytes(report)
    navs["2026-01-02"] = Decimal("1")
    kwargs["legacy_aggregate"]["execution"]["source_gate"] = "changed"
    assert m.canonical_report_bytes(report) == original
    report["periods"][0]["account"]["ending_equity"] = "1"
    assert navs["2026-10-13"] == Decimal("990000")


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"),
                                  Decimal("-Infinity"), Decimal(0), Decimal(-1),
                                  1, 1.0, True, "100", None, Decimal("1E+999999999")])
def test_nonpositive_nondecimal_or_unbounded_nav_refuses(case, value):
    navs, kwargs = case
    navs["2026-01-02"] = value
    with pytest.raises(m.Refused, match="^account_value$"):
        m.build_report(navs, **kwargs)


@pytest.mark.parametrize("mode", ["missing", "extra", "wrong-key-type", "not-dict"])
def test_nav_session_census_is_exact(case, mode):
    navs, kwargs = case
    if mode == "missing":
        del navs["2026-01-02"]
    elif mode == "extra":
        navs["2026-10-14"] = Decimal(1)
    elif mode == "wrong-key-type":
        navs[1] = Decimal(1)
    else:
        navs = tuple(navs.items())
    with pytest.raises(m.Refused, match="^account_path$"):
        m.build_report(navs, **kwargs)


@pytest.mark.parametrize("mode", ["list", "duplicate", "reordered", "wrong-start", "wrong-end",
                                  "missing-history-boundary", "missing-seen-boundary",
                                  "missing-later-start", "noncanonical", "weekend", "bad-type"])
def test_axis_geometry_refusals(case, mode):
    navs, kwargs = case
    axis = kwargs["evaluation_sessions"]
    if mode == "list":
        axis = list(axis)
    elif mode == "duplicate":
        axis = axis[:2] + axis[1:]
    elif mode == "reordered":
        axis = axis[:1] + (axis[2], axis[1]) + axis[3:]
    elif mode == "wrong-start":
        axis = axis[1:]
    elif mode == "wrong-end":
        axis = axis[:-1]
    elif mode.startswith("missing-"):
        key = {"missing-history-boundary": "2025-12-31", "missing-seen-boundary": "2026-09-25",
               "missing-later-start": "2026-09-28"}[mode]
        axis = tuple(session for session in axis if session != key)
    elif mode == "noncanonical":
        axis = ("2021-1-04",) + axis[1:]
    elif mode == "weekend":
        axis = tuple(sorted(axis + ("2026-09-26",)))
    else:
        axis = (None,) + axis[1:]
    kwargs["evaluation_sessions"] = axis
    with pytest.raises(m.Refused, match="^axis$"):
        m.build_report(navs, **kwargs)


@pytest.mark.parametrize("arm", [True, False, 0, 99, 220, "100", Decimal(100), 100.0])
def test_other_arms_refuse(case, arm):
    navs, kwargs = case
    kwargs["ar_percent"] = arm
    with pytest.raises(m.Refused, match="^arm$"):
        m.build_report(navs, **kwargs)


@pytest.mark.parametrize("field,value,code", [
    ("source_profile_sha256", "A" * 64, "source_profile"),
    ("source_profile_sha256", "a" * 63, "source_profile"),
    ("source_profile_sha256", None, "source_profile"),
    ("account_path_schema", "", "account_path_schema"),
    ("account_path_schema", "bad\n", "account_path_schema"),
    ("account_path_schema", "é", "account_path_schema"),
    ("account_path_schema", True, "account_path_schema"),
])
def test_source_binding_argument_refusals(case, field, value, code):
    navs, kwargs = case
    kwargs[field] = value
    with pytest.raises(m.Refused, match="^" + code + "$"):
        m.build_report(navs, **kwargs)


@pytest.mark.parametrize("field,value", [
    ("run_valid", False), ("run_valid", 1), ("profile_sha256", "b" * 64),
    ("preliminary", False), ("backtest_only", False), ("formal", True),
    ("live_orders", True), ("paper_orders", True), ("funded_orders", True),
    ("deployment", True), ("trading", True),
])
def test_old_aggregate_validity_cannot_be_bypassed(case, field, value):
    navs, kwargs = case
    kwargs["legacy_aggregate"][field] = value
    with pytest.raises(m.Refused, match="^legacy_aggregate$"):
        m.build_report(navs, **kwargs)


def test_same_job_nav_recomputes_old_metrics(case):
    navs, kwargs = case
    kwargs["legacy_aggregate"]["account"]["maximum_drawdown"] = "-0.99"
    with pytest.raises(m.Refused, match="^legacy_account$"):
        m.build_report(navs, **kwargs)


def test_same_metrics_with_wrong_legacy_path_pin_refuses(case):
    navs, kwargs = case
    kwargs["legacy_aggregate"]["account_observation_path_sha256"] = "b" * 64
    with pytest.raises(m.Refused, match="^legacy_path$"):
        m.build_report(navs, **kwargs)


def test_account_path_schema_is_part_of_same_job_binding(case):
    navs, kwargs = case
    kwargs["account_path_schema"] = "different-schema-v1"
    with pytest.raises(m.Refused, match="^legacy_path$"):
        m.build_report(navs, **kwargs)


def test_flat_path_none_sharpe_is_preserved(case, legacy):
    _navs_before, kwargs = case
    navs = {session: Decimal(100) for session in kwargs["evaluation_sessions"]}
    rows = tuple(navs.items())
    kwargs["legacy_aggregate"]["account"] = legacy["_population_metrics"](rows)
    kwargs["legacy_aggregate"]["account_observation_path_sha256"] = legacy["_decimal_path_sha256"](PATH_SCHEMA, rows)
    result = m.build_report(navs, **kwargs)
    assert all(row["account"]["zero_rate_sharpe"] is None for row in result["periods"])
    assert all(row["account"]["annualized_volatility"] == "0" for row in result["periods"])


def test_redundant_decimal_precision_does_not_change_legacy_formatting(case, legacy):
    _navs_before, kwargs = case
    navs = {session: Decimal("100." + "0" * 1000)
            for session in kwargs["evaluation_sessions"]}
    rows = tuple(navs.items())
    kwargs["legacy_aggregate"]["account"] = legacy["_population_metrics"](rows)
    kwargs["legacy_aggregate"]["account_observation_path_sha256"] = legacy["_decimal_path_sha256"](PATH_SCHEMA, rows)
    report = m.build_report(navs, **kwargs)
    assert report["periods"][0]["account"] == kwargs["legacy_aggregate"]["account"]


@pytest.mark.parametrize("field,value", [
    ("schema", "old"), ("reporting_profile_sha256", "b" * 64),
    ("source_profile_sha256", "b" * 64), ("ar_percent", True),
    ("account_path_schema", "other"), ("evaluation_session_count", True),
    ("evaluation_session_sha256", "b" * 64), ("legacy_aggregate_sha256", "b" * 64),
    ("legacy_account_path_sha256", "b" * 64), ("reporting_only", 1),
    ("legacy_validity_gates_preserved", False), ("preliminary", False),
    ("backtest_only", False), ("formal", True), ("point_in_time_data", True),
    ("independent_periods", True), ("historical_result_splice", True),
])
def test_report_identity_and_false_flags_are_closed(case, field, value):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    report[field] = value
    with pytest.raises(m.Refused, match="^report_shape$"):
        m.validate_report(report, **kwargs)


@pytest.mark.parametrize("level", ["report", "period", "metric"])
def test_unknown_public_fields_refuse(case, level):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    target = report if level == "report" else report["periods"][0]
    if level == "metric":
        target = target["account"]
    target["private_row"] = "not allowed"
    with pytest.raises(m.Refused):
        m.validate_report(report, **kwargs)


@pytest.mark.parametrize("field,value", [
    ("period_id", "arbitrary"), ("first_session", "2026-09-25"),
    ("last_session", "2026-10-14"), ("session_count", True),
    ("prior_boundary_session", None), ("nav_path_sha256", "A" * 64),
])
def test_later_period_scope_is_fixed(case, field, value):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    report["periods"][4][field] = value
    with pytest.raises(m.Refused, match="^period_shape$"):
        m.validate_report(report, **kwargs)


@pytest.mark.parametrize("field,value", [
    ("observation_count", True), ("first_observation_session", "2026-09-28"),
    ("last_observation_session", "2026-10-14"), ("starting_equity", "0"),
    ("ending_equity", "NaN"), ("cumulative_return", "0.2"),
    ("maximum_drawdown", "-1"), ("maximum_drawdown", "0.01"),
    ("annualized_volatility", "-1"), ("zero_rate_sharpe", None),
    ("zero_rate_sharpe", "Infinity"), ("ending_equity", "1E+999999999"),
    ("ending_equity", "0990000"), ("starting_equity", 900000),
])
def test_period_metric_validation_refuses_invalid_values(case, field, value):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    report["periods"][4]["account"][field] = value
    with pytest.raises(m.Refused, match="^period_metric$"):
        m.validate_report(report, **kwargs)


def test_period_boundary_consistency_cannot_be_forged(case):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    later = report["periods"][4]["account"]
    later["starting_equity"] = "1000000"
    later["cumulative_return"] = "-0.01"
    with pytest.raises(m.Refused, match="^boundary$"):
        m.validate_report(report, **kwargs)


def test_legacy_aggregate_is_bound_in_full_not_only_account(case):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    kwargs["legacy_aggregate"]["execution"]["source_gate"] = "another-aggregate"
    with pytest.raises(m.Refused, match="^report_shape$"):
        m.validate_report(report, **kwargs)


def test_profile_and_report_are_canonical_bounded_ascii(case):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    raw = m.canonical_report_bytes(report)
    assert json.loads(raw) == report
    assert raw == json.dumps(report, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")
    assert m.profile_sha256() == hashlib.sha256(m._canonical(m.profile_record())).hexdigest()
    assert "not_independently_recomputed" in m.profile_record()["external_validation_limit"]
    assert "first_2021_01_04_close" in m.profile_record()["total_and_historical_base"]
    assert report["legacy_account_path_sha256"] == kwargs["legacy_aggregate"]["account_observation_path_sha256"]
    assert not any(key in raw.decode("ascii") for key in ("daily_NAV", "security_id", "ticker", "price_rows"))
    with pytest.raises(m.Refused, match="^report_bound$"):
        m.canonical_report_bytes({"oversize": "x" * m.MAXIMUM_STATISTIC_BYTES})
    with pytest.raises(m.Refused, match="^canonical$"):
        m.canonical_report_bytes({"bad": float("nan")})


def test_source_cloud_import_boundary_and_no_action_surface():
    tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)
    assert imports == {"hashlib", "json", "datetime", "decimal"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr in {"market_order", "market_on_open_order", "set_holdings", "read_bytes", "save", "open"}
                   for node in ast.walk(tree))


def test_historical_statistic_bound_is_exactly_8192_bytes():
    assert m.MAXIMUM_STATISTIC_BYTES == 8192
    overhead = len(m._canonical({"x": ""}))
    assert len(m.canonical_report_bytes({"x": "x" * (8192 - overhead)})) == 8192
    with pytest.raises(m.Refused, match="^report_bound$"):
        m.canonical_report_bytes({"x": "x" * (8193 - overhead)})


def test_report_external_validator_honestly_does_not_claim_daily_recomputation(case):
    navs, kwargs = case
    report = m.build_report(navs, **kwargs)
    # The external report validator has no daily rows. A finite alternative
    # subperiod volatility is structurally admissible, never independent proof.
    report["periods"][4]["account"]["annualized_volatility"] = "0.123"
    m.validate_report(report, **kwargs)
    assert report["independent_periods"] is False
    assert "not_independently_recomputed" in m.profile_record()["external_validation_limit"]
