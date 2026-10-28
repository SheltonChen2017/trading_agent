"""Pure W5 successors: exact public calendar, capital epoch and preserved economics.

Only public source and synthetic algorithm/source objects are used. No retained
DATA, QC cache, provider, credential or operational protocol is invoked.
"""
import ast
import copy
import inspect
import json
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_available_history_comparison_runtime as base
from research.analyst_revisions_v2_qc import newrule_available_history_common_price_runtime as m
from research.analyst_revisions_v2_qc import newrule_comparison_qc_runtime as old_base
from research.analyst_revisions_v2_qc import newrule_common_price_comparison_runtime as old_common
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october
from scripts import arv2_r327_available_history_period as period
from scripts import arv2_newrule_quote_execution_projection as quote
from scripts import arv2_r298_ak_source_binding as ak
from scripts import arv2_r327_i_source_binding as identity
from tests.analyst_revisions_v2 import test_common_price_comparison_runtime as old_common_tests
from tests.analyst_revisions_v2 import test_newrule_runtime_projection as old_tests

D = Decimal
BASE_CHANGES = [
  [
    "SCHEMA = \"arv2-accepted-risk-newrule-comparison-profile-v1\"",
    "SCHEMA = \"arv2-r327-available-history-comparison-profile-v1\""
  ],
  [
    "START_SESSION = \"2021-01-04\"",
    "START_SESSION = \"2021-11-01\"\nFIRST_REFERENCE_CLOSE = \"2021-10-29\"\nRESEARCH_EPOCH_ID = \"R327-20261027-available-history-v1\"\nFULL_AXIS_COUNT = 3466\nFULL_AXIS_SHA256 = \"4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585\""
  ],
  [
    "META_STATISTIC = \"ARV2_NEWRULE_META\"",
    "META_STATISTIC = \"ARV2_AVAILABLE_HISTORY_META\""
  ],
  [
    "MONTHLY_STATISTIC = \"ARV2_NEWRULE_MONTHLY\"",
    "MONTHLY_STATISTIC = \"ARV2_AVAILABLE_HISTORY_MONTHLY\""
  ],
  [
    "    targets.cohort(universe_count)\n",
    "    require(type(axis) is tuple and len(axis) == FULL_AXIS_COUNT\n            and all(type(value) is str and len(value) == 10 for value in axis)\n            and targets.digest(axis) == FULL_AXIS_SHA256, \"available_history_full_axis\")\n    require(START_SESSION in axis and axis.index(START_SESSION) > 0\n            and axis[axis.index(START_SESSION) - 1] == FIRST_REFERENCE_CLOSE, \"available_history_prior_close\")\n    targets.cohort(universe_count)\n"
  ],
  [
    "f\"arv2-newrule-{universe_count}-ar{ar_percent}-2026-v1\"",
    "f\"arv2-r327-{universe_count}-ar{ar_percent}-2021Nov01-2026Oct13-v1\""
  ],
  [
    "    seed = {\"schema\": SCHEMA,\n",
    "    seed = {\"schema\": SCHEMA, \"research_epoch_id\": RESEARCH_EPOCH_ID,\n        \"first_reference_close\": FIRST_REFERENCE_CLOSE,\n        \"initial_state\": \"new_epoch_empty_positions_and_orders_USD1000000\",\n"
  ],
  [
    "first_2021Jan04_STARTING_CASH",
    "first_2021Nov01_new_epoch_STARTING_CASH"
  ],
  [
    "\"arv2-newrule-comparison-result-v1\"",
    "\"arv2-r327-available-history-comparison-result-v1\""
  ],
  [
    "\"arv2-newrule-monthly-return-v1\"",
    "\"arv2-r327-available-history-monthly-return-v1\""
  ],
  [
    "        require(not self._current_holding_census(), \"initial_holdings\")\n",
    "        require(not self._current_holding_census(), \"initial_holdings\")\n        require(not tuple(self._algorithm.transactions.get_open_orders()), \"initial_open_orders\")\n"
  ]
]
COMMON_CHANGES = [
  [
    "import newrule_comparison_qc_runtime as base",
    "import newrule_available_history_comparison_runtime as base"
  ],
  [
    "SCHEMA = 'arv2-r298-common-price-comparison-profile-v1'",
    "SCHEMA = 'arv2-r327-available-history-common-price-profile-v1'"
  ],
  [
    "RESULT_SCHEMA = 'arv2-r298-common-price-comparison-result-v1'",
    "RESULT_SCHEMA = 'arv2-r327-available-history-common-price-result-v1'"
  ],
  [
    "MONTH_SCHEMA = 'arv2-r298-common-price-monthly-return-v1'",
    "MONTH_SCHEMA = 'arv2-r327-available-history-common-price-monthly-return-v1'"
  ],
  [
    "META_STATISTIC, MONTHLY_STATISTIC = 'ARV2_COMMON_PRICE_META', 'ARV2_COMMON_PRICE_MONTHLY'",
    "META_STATISTIC, MONTHLY_STATISTIC = 'ARV2_AVAILABLE_COMMON_META', 'ARV2_AVAILABLE_COMMON_MONTHLY'"
  ],
  [
    "    'source_pins', 'reference_and_NAV_source_policy', 'automatic_security_price_seeding', *FALSE_FLAGS))",
    "    'source_pins', 'reference_and_NAV_source_policy', 'automatic_security_price_seeding',\n    'research_epoch_id', 'first_reference_close', *FALSE_FLAGS))"
  ],
  [
    "        and type(strategy.get('candidate_id')) is str and strategy['candidate_id'].endswith('-quote-aware-v1')",
    "        and strategy.get('candidate_id') == (f\"arv2-r327-{strategy['universe_count']}-ar{strategy['ar_percent']}\"\n            '-2021Nov01-2026Oct13-v1-quote-aware-v1')\n        and strategy.get('research_epoch_id') == base.RESEARCH_EPOCH_ID\n        and strategy.get('first_reference_close') == base.FIRST_REFERENCE_CLOSE\n        and strategy.get('initial_state') == 'new_epoch_empty_positions_and_orders_USD1000000'\n        and strategy.get('session_axis_sha256') == base.FULL_AXIS_SHA256\n        and type(strategy.get('session_count')) is int and strategy['session_count'] == base.FULL_AXIS_COUNT\n        and type(strategy.get('evaluation_sessions')) is list\n        and len(strategy['evaluation_sessions']) == EXPECTED_EVALUATION_SESSION_COUNT\n        and digest(strategy['evaluation_sessions']) == EVALUATION_SESSIONS_SHA256\n        and strategy['evaluation_sessions'][0] == START_SESSION and strategy['evaluation_sessions'][-1] == END_SESSION\n        and type(strategy.get('decision_sessions')) is list\n        and len(strategy['decision_sessions']) == EXPECTED_DECISION_SESSION_COUNT\n        and digest(strategy['decision_sessions']) == DECISION_SESSIONS_SHA256\n        and tuple(strategy['decision_sessions']) == weekly_axis(tuple(strategy['evaluation_sessions']))"
  ],
  [
    "'candidate_id': strategy['candidate_id'] + '-common-RAW-v1'",
    "'candidate_id': strategy['candidate_id'] + '-common-RAW-W5-v1'"
  ],
  [
    "        'automatic_security_price_seeding': False,\n        **FALSE_FLAGS}",
    "        'automatic_security_price_seeding': False,\n        'research_epoch_id': base.RESEARCH_EPOCH_ID, 'first_reference_close': base.FIRST_REFERENCE_CLOSE,\n        **FALSE_FLAGS}"
  ],
  [
    "    return {'schema': SCHEMA, 'frozen_quote_base_sha256': FROZEN_BASE_SHA256,",
    "    return {'schema': SCHEMA, 'frozen_quote_base_sha256': FROZEN_BASE_SHA256,\n        'research_epoch_id': base.RESEARCH_EPOCH_ID, 'evaluation_first': START_SESSION,\n        'evaluation_last': END_SESSION, 'first_reference_close': base.FIRST_REFERENCE_CLOSE,\n        'period_base': 'separately_pinned_W5_period_projection_of_frozen_quote_aware_base',"
  ],
  [
    "LINEAGE_SHA256 = 'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'",
    "LINEAGE_SHA256 = 'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'\nEXPECTED_EVALUATION_SESSION_COUNT = 1242\nEVALUATION_SESSIONS_SHA256 = 'eff4b9f8552317b16b97fbc1734aca1b27baea25d718721ddf0831e2ae85ef7e'\nEXPECTED_DECISION_SESSION_COUNT = 259\nDECISION_SESSIONS_SHA256 = '9f0bd75e1de17112bd3a571438311cd152ba3ee5ce7279e710b133553cbd1429'"
  ]
]


@pytest.fixture(scope="module")
def axis():
    value = october._sessions()
    assert len(value) == period.FULL_AXIS_COUNT and period.digest(list(value)) == period.FULL_AXIS_SHA256
    return value


def profile(axis, count=6, arm=0, *, quoted=True):
    value = base.make_profile(axis, package_sha256=m.monetary.native.PACKAGE_SHA256,
        lineage_sha256=m.LINEAGE_SHA256, universe_count=count, ar_percent=arm,
        source_pins={"fixed_source.py": "a" * 64})
    if quoted:
        value["candidate_id"] += "-quote-aware-v1"
        value.update(quote.policy_profile_fields())
        value["profile_sha256"] = m.digest({key: child for key, child in value.items() if key != "profile_sha256"})
    return value


def common_profile(axis, count=6, arm=0):
    return m.make_profile(profile(axis, count, arm), runtime_project_id=123,
        native_source_context_sha256=m.native_reader.SOURCE_CONTEXT_SHA256,
        vendor_source_context_sha256="b" * 64, source_pins={"fixed_source.py": "a" * 64})


def finite_refusal(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert m.finite(caught.value) == code


def _reverse(new, changes):
    for previous, current in reversed(changes):
        assert current in new
        new = new.replace(current, previous)
    return new


def test_entire_base_source_diff_is_only_explicit_period_epoch_and_empty_order_guard():
    assert _reverse(Path(base.__file__).read_text(), BASE_CHANGES) == Path(old_base.__file__).read_text()
    assert old_base.START_SESSION == "2021-01-04" and base.START_SESSION == period.FIRST
    assert old_common.START_SESSION == "2021-01-04"


def test_entire_common_source_diff_is_only_explicit_new_base_period_profile_and_schemas():
    assert _reverse(Path(m.__file__).read_text(), COMMON_CHANGES) == Path(old_common.__file__).read_text()


def test_all_strategy_methods_are_AST_identical_except_the_new_initial_order_guard():
    before = ast.parse(Path(old_base.__file__).read_bytes())
    after = ast.parse(Path(base.__file__).read_bytes())
    owners = [next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "NewruleComparisonDriver")
        for tree in (before, after)]
    left, right = ({node.name: node for node in owner.body if isinstance(node, ast.FunctionDef)} for owner in owners)
    assert set(left) == set(right)
    for name in left.keys() - {"initialize"}:
        # Only the two explicitly versioned result-schema literals change in
        # terminal emission; every fee/fill/action/strategy predicate remains.
        revised = copy.deepcopy(right[name])
        for node in ast.walk(revised):
            if isinstance(node, ast.Constant) and type(node.value) is str:
                node.value = {"arv2-r327-available-history-comparison-result-v1": "arv2-newrule-comparison-result-v1",
                    "arv2-r327-available-history-monthly-return-v1": "arv2-newrule-monthly-return-v1"}.get(node.value, node.value)
        assert ast.dump(left[name], include_attributes=False) == ast.dump(revised, include_attributes=False)
    assert ast.dump(ast.parse(_reverse(inspect.getsource(base.NewruleComparisonDriver.initialize),
        [BASE_CHANGES[-1]]).lstrip()), include_attributes=False) == ast.dump(
        ast.parse(inspect.getsource(old_base.NewruleComparisonDriver.initialize).lstrip()), include_attributes=False)


@pytest.mark.parametrize("count,arm", period.CELLS)
def test_six_profiles_share_exact_new_period_sources_and_capital_epoch(axis, count, arm):
    expected = period.make_period(axis)
    strategy = profile(axis, count, arm)
    checked = common_profile(axis, count, arm)
    assert strategy["evaluation_sessions"] == expected["evaluation_sessions"]
    assert strategy["decision_sessions"] == expected["decision_sessions"]
    assert len(strategy["evaluation_sessions"]) == m.EXPECTED_EVALUATION_SESSION_COUNT == 1242
    assert m.digest(strategy["evaluation_sessions"]) == m.EVALUATION_SESSIONS_SHA256
    assert len(strategy["decision_sessions"]) == m.EXPECTED_DECISION_SESSION_COUNT == 259
    assert m.digest(strategy["decision_sessions"]) == m.DECISION_SESSIONS_SHA256
    assert strategy["first_reference_close"] == "2021-10-29"
    assert strategy["research_epoch_id"] == checked["research_epoch_id"] == period.RESEARCH_EPOCH_ID
    assert strategy["initial_state"] == "new_epoch_empty_positions_and_orders_USD1000000"
    assert strategy["candidate_id"] == f"arv2-r327-{count}-ar{arm}-2021Nov01-2026Oct13-v1-quote-aware-v1"
    assert checked["candidate_id"] == strategy["candidate_id"] + "-common-RAW-W5-v1"
    assert m.validate_profile(checked) == checked
    assert checked["strategy_profile"] == strategy
    assert all(checked[key] is False for key in m.FALSE_FLAGS)
    assert checked["frozen_quote_base_sha256"] == old_common.FROZEN_BASE_SHA256
    assert checked["automatic_security_price_seeding"] is False
    assert strategy["gross_target"] == "0.98" and strategy["aggregate_stock_target_cap"] == "0.098"
    assert strategy["fee_bps"] == "10" and strategy["slippage_model_bps"] == "0"


@pytest.mark.parametrize("issue", ("short", "reorder", "substitute", "list"))
def test_new_epoch_never_accepts_a_caller_selected_shortened_or_changed_full_axis(axis, issue):
    value = list(axis)
    if issue == "short": value.pop(10)
    elif issue == "reorder": value[10], value[11] = value[11], value[10]
    elif issue == "substitute": value[10] = "2013-01-19"
    changed = value if issue == "list" else tuple(value)
    with pytest.raises(base.targets.NewruleError, match="available_history_full_axis"):
        base.make_profile(changed, package_sha256="a" * 64, lineage_sha256="b" * 64,
            universe_count=6, ar_percent=0, source_pins={"source.py": "c" * 64})


@pytest.mark.parametrize("field,value", (
    ("research_epoch_id", "old-epoch"), ("first_reference_close", "2020-12-31"),
    ("initial_state", "carry_old_positions"), ("session_axis_sha256", "f" * 64),
    ("session_count", True), ("evaluation_sessions", ["2021-01-04", "2026-10-13"]),
    ("decision_sessions", ["2021-01-04", "2026-10-12"])))
def test_common_profile_rejects_wrong_period_even_when_claim_hash_is_recomputed(axis, field, value):
    strategy = profile(axis)
    strategy[field] = value
    strategy["profile_sha256"] = m.digest({key: child for key, child in strategy.items() if key != "profile_sha256"})
    finite_refusal("profile", lambda: m.make_profile(strategy, runtime_project_id=123,
        native_source_context_sha256=m.native_reader.SOURCE_CONTEXT_SHA256,
        vendor_source_context_sha256="b" * 64, source_pins={"source.py": "a" * 64}))


def test_old_profile_and_old_result_schema_are_not_renamed_into_new_epoch(axis):
    finite_refusal("profile", lambda: m.make_profile(old_common_tests.strategy(), runtime_project_id=123,
        native_source_context_sha256=m.native_reader.SOURCE_CONTEXT_SHA256,
        vendor_source_context_sha256="b" * 64, source_pins={"source.py": "a" * 64}))
    assert m.META_STATISTIC != old_common.META_STATISTIC and m.MONTHLY_STATISTIC != old_common.MONTHLY_STATISTIC
    assert m.RESULT_SCHEMA != old_common.RESULT_SCHEMA and m.MONTH_SCHEMA != old_common.MONTH_SCHEMA


def test_claimed_full_axis_cannot_hide_a_removed_interior_nondecision_close(axis):
    strategy = profile(axis)
    assert strategy["evaluation_sessions"][1] == "2021-11-02"
    assert "2021-11-02" not in strategy["decision_sessions"]
    strategy["evaluation_sessions"].pop(1)
    strategy["profile_sha256"] = m.digest({key: child for key, child in strategy.items() if key != "profile_sha256"})
    finite_refusal("profile", lambda: m.make_profile(strategy, runtime_project_id=123,
        native_source_context_sha256=m.native_reader.SOURCE_CONTEXT_SHA256,
        vendor_source_context_sha256="b" * 64, source_pins={"source.py": "a" * 64}))


def test_pin_map_normal_python_escape_accepts_normal_py_name_and_refuses_path_backslash():
    assert m._pin_map({"source.py": "a" * 64}) == {"source.py": "a" * 64}
    finite_refusal("source_pins", lambda: m._pin_map({"source\\xpy": "a" * 64}))
    finite_refusal("source_pins", lambda: m._pin_map({"../source.py": "a" * 64}))


def result_fixture(axis):
    old_stats, _ = old_common_tests.result_fixture()
    meta = json.loads(old_stats[old_common.META_STATISTIC])
    expected = common_profile(axis)
    strategy = expected["strategy_profile"]
    sessions, decisions = tuple(strategy["evaluation_sessions"]), tuple(strategy["decision_sessions"])
    observations = {session: D("1000000.123456789") for session in sessions}
    months = {}
    for session in sessions: months[session[:7]] = session
    rows, previous = [], base.STARTING_CASH
    with localcontext() as arithmetic:
        arithmetic.prec = 96
        for session in months.values():
            value = observations[session]
            rows.append([session, str((value / previous - 1).quantize(D("1e-12"))),
                str(value.quantize(D("0.000001")))])
            previous = value
    source = old_common_tests.common_result(expected)
    source["schema"] = m.RESULT_SCHEMA + "-source"
    meta.update(schema=m.RESULT_SCHEMA, candidate_id=expected["candidate_id"],
        profile_sha256=expected["profile_sha256"], package_sha256=expected["package_sha256"],
        lineage_sha256=expected["lineage_sha256"], decision_count=len(decisions),
        evaluation_session_count=len(sessions), raw_reference_history_calls=0,
        split_unit_history_calls=len(decisions), common_price=source,
        account_aggregates=m.account_aggregates(observations, sessions, [{"fee": "1"}], meta["forced_delisting"]))
    monthly = {"schema": m.MONTH_SCHEMA, "candidate_id": expected["candidate_id"],
        "profile_sha256": expected["profile_sha256"], "months": rows, "last_month_partial": True,
        "alternative_view_realized_performance": False}
    return {m.META_STATISTIC: m.canonical(meta).decode("ascii"),
        m.MONTHLY_STATISTIC: m.canonical(monthly).decode("ascii")}, expected


def test_new_result_reader_uses_W5_closes_decisions_months_and_calendar_CAGR(axis):
    statistics, expected = result_fixture(axis)
    checked = m.validate_result_statistics(statistics, expected_profile=expected)
    sessions = expected["strategy_profile"]["evaluation_sessions"]
    assert checked["monthly"]["months"][0][0].startswith("2021-11")
    assert len(checked["monthly"]["months"]) == 60
    assert checked["meta"]["raw_reference_history_calls"] == 0
    assert checked["meta"]["split_unit_history_calls"] == len(expected["strategy_profile"]["decision_sessions"])
    aggregate = checked["meta"]["account_aggregates"]
    assert aggregate["elapsed_calendar_days"] == (datetime(2026, 10, 13) - datetime(2021, 11, 1)).days
    assert aggregate["observed_close_count"] == len(sessions)
    assert aggregate["starting_cash"] == "1000000"
    assert checked["meta"]["common_price"]["ledger"]["counts"]["close_batch_completed"] == len(sessions)
    assert checked["meta"]["source_admission_granted"] is False


@pytest.mark.parametrize("issue", ("old_schema", "old_month_schema", "old_history_302", "old_split_302",
    "old_months_70", "old_CAGR_start", "missing_close", "missing_reference", "failed_lookup",
    "fee", "fill_count", "bad_first_month", "formal_flag", "source_extra"))
def test_new_reader_rejects_old_period_and_source_or_monetary_tampering(axis, issue):
    statistics, expected = result_fixture(axis)
    meta, monthly = (json.loads(statistics[key]) for key in (m.META_STATISTIC, m.MONTHLY_STATISTIC))
    ledger = meta["common_price"]["ledger"]
    if issue == "old_schema": meta["schema"] = old_common.RESULT_SCHEMA
    elif issue == "old_month_schema": monthly["schema"] = old_common.MONTH_SCHEMA
    elif issue == "old_history_302": meta["raw_reference_history_calls"] = 302
    elif issue == "old_split_302": meta["split_unit_history_calls"] = 302
    elif issue == "old_months_70": monthly["months"] = [["2021-01-29", "0.000000000000", "1000000.000000"]] * 70
    elif issue == "old_CAGR_start":
        meta["account_aggregates"]["elapsed_calendar_days"] = (datetime(2026, 10, 13) - datetime(2021, 1, 4)).days
    elif issue == "missing_close": ledger["unique_close_count"] -= 1
    elif issue == "missing_reference": ledger["counts"]["reference_batch_completed"] -= 1
    elif issue == "failed_lookup": ledger["source_observation"]["lookup_counts"]["vendor_price_lookup_completed"] -= 1
    elif issue == "fee": meta["account_aggregates"]["total_engine_fees"] = "999"
    elif issue == "fill_count": meta["fill_count"] += 1
    elif issue == "bad_first_month": monthly["months"][0][1] = "0.000000000000"
    elif issue == "formal_flag": meta["formal_forward_ready"] = True
    else: ledger["private_prices"] = ["NEVER_ACCEPT"]
    changed = {m.META_STATISTIC: m.canonical(meta).decode("ascii"),
        m.MONTHLY_STATISTIC: m.canonical(monthly).decode("ascii")}
    with pytest.raises(m.Refused):
        m.validate_result_statistics(changed, expected_profile=expected)


@pytest.mark.parametrize("pending", (False, True))
def test_new_epoch_initialize_requires_real_empty_positions_cash_and_open_orders(axis, monkeypatch, pending):
    _, algorithm, symbols = old_tests.driver()
    expected = profile(axis, quoted=False)
    value = base.NewruleComparisonDriver(algorithm, profile=expected,
        activation_manifest_key="synthetic/activation.json", activation_manifest_sha256="d" * 64,
        activation_manifest_byte_count=100, benchmark_symbol=symbols["SPY"],
        etf_symbols={ticker: symbols[ticker] for ticker in base.targets.UNIVERSES},
        fundamental_universe=object(), constituent_universes={ticker: object() for ticker in base.targets.UNIVERSES},
        trade_bar_type=object(), minute_resolution="minute", daily_resolution="daily",
        raw_normalization="raw", fee_model_factory=lambda: object(), slippage_model_factory=lambda: object(),
        order_status_enum=old_tests.Status, order_status_to_int=int,
        split_occurred_type="occurred", split_warning_type="warning", split_data_type="Split")
    evaluator = NS(session_axis=axis, source_lineage_sha256s={"security_master_admission_sha256": "a" * 64})
    package = NS(evaluator_input=evaluator, package_sha256=expected["package_sha256"],
        activation_manifest_sha256="d" * 64, runtime_symbol_bindings=())
    monkeypatch.setattr(base.inputs, "load_accepted_risk_preliminary_package", lambda *_a, **_k: package)
    monkeypatch.setattr(base.figi, "resolve_preliminary_qc_figis", lambda *_a, **_k: NS(resolved=()))
    monkeypatch.setattr(base.preopen, "PreopenRatingScoreRuntime", lambda *_a, **_k: NS())
    algorithm.composite_figi = lambda *_: None
    algorithm.transactions.get_open_orders = lambda: (object(),) if pending else ()
    if pending:
        with pytest.raises(base.targets.NewruleError, match="initial_open_orders"): value.initialize()
    else:
        assert value.initialize() is True
        assert value._evaluation_sessions[0] == "2021-11-01"
        assert not value._current_holding_census()
        assert value._portfolio_cash() == D("1000000")


def test_common_methods_keep_frozen_quote_split_fill_intraday_and_cash_behavior():
    owner = m.CommonPriceComparisonDriver
    allowed = {"__init__", "initialize", "_reference_prices", "on_after_close", "on_end_of_algorithm"}
    assert {name for name in owner.__dict__ if callable(owner.__dict__[name])
        and hasattr(base.NewruleComparisonDriver, name)} == allowed
    for name in ("on_before_open", "_split_factors", "on_splits", "_submit_market", "on_order_event",
        "on_after_open", "on_data", "configure_security"):
        assert getattr(owner, name) is getattr(base.NewruleComparisonDriver, name)


def test_public_native_cell_counts_bound_only_a_conservative_potential_exposure_envelope(axis):
    source = ak.expected_source_summary()
    observation = identity.observed_fact()["result"]["identity_summary"]
    assert observation["actual_target_or_holdings_path_proven"] is False
    cases = observation["cases"]
    valid = {row["whole_binding_sha256"]: row["valid_cell_count"] for row in source["per_selected"]}
    assert len(cases) == len(valid) == 5
    # A dense potential-held envelope is conservative. These counts cannot
    # locate missing dates or prove that any actual target/holding needs one.
    necessary = {}
    for case in cases:
        assert case["potential"] is True and case["required_price_last"] == period.LAST
        required = tuple(session for session in axis if case["required_price_first"] <= session <= case["required_price_last"])
        assert required[0] == case["required_price_first"] and required[-1] == period.LAST
        necessary[case["whole_binding_sha256"]] = {"needed": len(required),
            "AK_total_valid": valid[case["whole_binding_sha256"]],
            "count_disproves_full_envelope": len(required) > valid[case["whole_binding_sha256"]]}
    assert len(necessary) == 5
    assert {key for key, row in necessary.items() if row["count_disproves_full_envelope"]} == {
        "1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331",
        "b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8",
        "b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9",
        "c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7"}
