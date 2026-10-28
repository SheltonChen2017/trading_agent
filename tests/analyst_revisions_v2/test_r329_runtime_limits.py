"""Synthetic W5 size/warmup/refusal limits; no proof of QC transport or margin.

Public generated source and closed-schema fixtures only. The maximal fixture is
a schema stress case, not a simulated feasible portfolio or observed result.
Run under native network, production-artifact and Keychain denial.
"""
import ast
import copy
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_available_history_comparison_runtime as base
from research.analyst_revisions_v2_qc import newrule_available_history_common_price_runtime as common
from tests.analyst_revisions_v2 import test_r327_available_history_runtime as runtime_fixtures
from tests.analyst_revisions_v2 import test_r327_available_history_projection as projection_fixtures
from tests.analyst_revisions_v2 import test_quote_execution_projection as quote_fixtures

D = Decimal
FALLBACK_REASONS = (
    "missing_or_stale_collection", "unresolved_reported_weight", "reported_book_incomplete",
    "qc_technical_identity_below_99pct", "economic_name_coverage_below_25pct",
    "cap_weight_coverage_below_25pct", "verified_name_count_below_five", "positive_score_count_below_five",
)


@pytest.fixture(scope="module")
def public_w5():
    # This builds real pinned public code against synthetic project 123 only.
    batch = projection_fixtures.public_batch()
    raw = dict(batch.specs[0].source_pairs)[projection_fixtures.m.BASE_NAME]
    namespace = dict(vars(base))
    owner = projection_fixtures.m._node(ast.parse(raw), "NewruleComparisonDriver", ast.ClassDef)
    methods = [copy.deepcopy(node) for node in owner.body if isinstance(node, ast.FunctionDef)
        and node.name in ("_capture", "on_splits")]
    cls = ast.ClassDef(name="WarmupHarness", bases=[], keywords=[], body=methods, decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
        "synthetic_W5_warmup_methods", "exec"), namespace)
    return NS(warmup=namespace["WarmupHarness"],
        quote=NS(files={quote_fixtures.m.RUNTIME_NAME: raw}))


def maximal_schema_fixture():
    axis = runtime_fixtures.october._sessions()
    original, _ = runtime_fixtures.result_fixture(axis)
    meta = json.loads(original[common.META_STATISTIC])
    expected = runtime_fixtures.common_profile(axis, 8, 200)
    strategy = expected["strategy_profile"]
    sessions, decisions = tuple(strategy["evaluation_sessions"]), tuple(strategy["decision_sessions"])
    meta.update(candidate_id=expected["candidate_id"], profile_sha256=expected["profile_sha256"],
        order_count=common.MAX_ORDERS, fill_count=common.MAX_ORDERS,
        cash_constrained_buy_count=256 * len(decisions),
        alternative_view_eligibility_disagreements=common.MAX_ROWS * len(decisions),
        alternative_view_score_disagreements=common.MAX_ROWS * len(decisions),
        coverage_fallback_counts={fund + ":" + reason: len(decisions)
            for fund in base.targets.cohort(8) for reason in FALLBACK_REASONS})
    source = runtime_fixtures.old_common_tests.common_result(expected)
    source["schema"] = common.RESULT_SCHEMA + "-source"
    observation = source["ledger"]["source_observation"]
    for receipt in ("native_receipt", "vendor_receipt"):
        observation[receipt]["byte_count"] = common.monetary.MAX_RECEIPT_BYTES
    for key in observation["lookup_counts"]:
        observation["lookup_counts"][key] = (common.MAX_VENDOR_COMPLETED_LOOKUPS if key.startswith("vendor_")
            else common.monetary.native.SELECTED_COUNT * (len(decisions) + len(sessions)))
    meta["common_price"] = source
    forced = meta["forced_delisting"]
    forced.update(order_count=common.MAX_ORDERS, event_count=common.MAX_ORDERS,
        fill_event_count=common.MAX_ORDERS, terminal_order_count=common.MAX_ORDERS,
        absolute_filled_quantity=10 ** 40, filled_notional="9" * 49 + "." + "9" * 46,
        actual_engine_fee_amount="1" + "0" * 48 + "." + "1" * 46)
    # Use the production aggregate calculation, not guessed return/CAGR strings.
    nav = D("9" * 49 + ".123456")
    observations = {session: nav for session in sessions}
    fills = [{"fee": "1" + "0" * 44 + "." + "1" * 46}] * common.MAX_ORDERS
    meta["account_aggregates"] = common.account_aggregates(observations, sessions, fills, forced)
    ends = {}
    for session in sessions:
        ends[session[:7]] = session
    previous, rows = base.STARTING_CASH, []
    with localcontext() as arithmetic:
        arithmetic.prec = 96
        for session in ends.values():
            rows.append([session, str((nav / previous - 1).quantize(D("1e-12"))),
                str(nav.quantize(D("0.000001")))])
            previous = nav
    monthly = {"schema": common.MONTH_SCHEMA, "candidate_id": expected["candidate_id"],
        "profile_sha256": expected["profile_sha256"], "months": rows, "last_month_partial": True,
        "alternative_view_realized_performance": False}
    return {common.META_STATISTIC: common.canonical(meta).decode("ascii"),
        common.MONTHLY_STATISTIC: common.canonical(monthly).decode("ascii")}, expected


def test_all64_fallbacks_maximum_counters_and_long_valid_aggregate_encodings_fit_local_bound():
    statistics, expected = maximal_schema_fixture()
    checked = common.validate_result_statistics(statistics, expected_profile=expected)
    assert len(checked["meta"]["coverage_fallback_counts"]) == 64
    assert checked["meta"]["order_count"] == checked["meta"]["fill_count"] == 60000
    assert checked["meta"]["forced_delisting"]["absolute_filled_quantity"] == 10 ** 40
    assert len(checked["meta"]["forced_delisting"]["filled_notional"]) == 96
    assert all(len(checked["meta"]["account_aggregates"][name]) == 96 for name in (
        "strategy_order_fees", "forced_exit_engine_fees", "total_engine_fees"))
    assert len(checked["monthly"]["months"]) == 60
    sizes = {name: len(value.encode("ascii")) for name, value in statistics.items()}
    assert all(size <= common.MAX_STATISTIC_BYTES == 16384 for size in sizes.values())
    assert sizes[common.META_STATISTIC] > 8002  # Larger than the observed historical QC witness.
    print("synthetic_closed_schema_statistic_sizes=" + json.dumps(sizes, sort_keys=True))
    assert all(checked["meta"][name] is False for name in common.FALSE_FLAGS)


@dataclass(frozen=True)
class SyntheticSymbol:
    id: str
    value: str


def forbidden(*_args, **_kwargs):
    pytest.fail("warmup/refusal reached economic or result operation")


def warmup_case(public_w5):
    driver = public_w5.warmup()
    now = datetime(2021, 10, 29, 9, 0, tzinfo=base.NY)
    driver._require_initialized = lambda: None
    driver._now = lambda: now
    driver._source_row_count = 0
    driver._cache = {"FUNDAMENTALS": []}
    driver._split_records_by_session, driver._split_path = {}, []
    driver._security_by_sid, driver._security_by_etf_sid = {"synthetic-stock": "synthetic-binding"}, {}
    driver._split_occurred_type, driver._split_warning_type = "Occurred", "Warning"
    driver._decision_set = frozenset(("2021-11-01",))
    driver._submit_market = driver._reference_prices = driver._portfolio_cash = forbidden
    driver._algorithm = NS(market_order=forbidden, set_summary_statistic=forbidden)
    return driver, now, SyntheticSymbol("synthetic-stock", "SYNTHETIC")


def test_warmup_capture_is_bounded_callback_cache_without_order_or_NAV_activity(public_w5):
    driver, now, symbol = warmup_case(public_w5)
    for offset in range(base.MAX_CACHE + 1):
        end = now - timedelta(days=base.MAX_CACHE - offset + 1)
        row = NS(symbol=symbol, end_time=end, market_cap=D("123.45"))
        assert driver._capture("FUNDAMENTALS", (row,)) == []
    assert driver._source_row_count == base.MAX_CACHE + 1
    cache = driver._cache["FUNDAMENTALS"]
    assert len(cache) == base.MAX_CACHE
    assert cache[0][1] == (now - timedelta(days=base.MAX_CACHE)).isoformat()
    assert cache[-1][2] == (("synthetic-stock", "SYNTHETIC", "123.45"),)
    assert not driver._split_path


def test_warmup_capture_keeps_conflicting_same_endtime_refusal(public_w5):
    driver, now, symbol = warmup_case(public_w5)
    row = NS(symbol=symbol, end_time=now - timedelta(days=1), market_cap=D(10))
    driver._capture("FUNDAMENTALS", (row,))
    snapshot = copy.deepcopy(driver._cache)
    row.market_cap = D(11)
    with pytest.raises(base.targets.NewruleError, match="^same_end_time_revision$"):
        driver._capture("FUNDAMENTALS", (row,))
    assert driver._cache == snapshot


def test_warmup_split_is_retained_as_diagnostic_and_duplicate_occurrence_refuses(public_w5):
    driver, now, symbol = warmup_case(public_w5)
    split = NS(type="Occurred", symbol=symbol, split_factor=D("0.5"), time=now - timedelta(hours=1))
    driver.on_splits({symbol: split})
    records = driver._split_records_by_session["2021-10-29"]
    assert records["synthetic-binding"] == {"factor": "0.5", "received": now.isoformat(),
        "event_time": split.time.isoformat()}
    assert len(driver._split_path) == 1 and driver._split_path[0][0] == "2021-10-29"
    snapshot = copy.deepcopy(driver._split_path)
    with pytest.raises(base.targets.NewruleError, match="^duplicate_split_occurrence$"):
        driver.on_splits({symbol: split})
    assert driver._split_path == snapshot


def test_mock_engine_invalid_callback_with_stale_price_stops_without_resize_or_next_buy(public_w5):
    # The engine rejection is supplied by this mock; this is NOT LEAN-margin evidence.
    # Section 330 (owner-directed ARV2R328-004): the stale engine price above the ask
    # now bounds the cash-limited size; the fee basis stays the authenticated ask.
    case = quote_fixtures.case(public_w5.quote)
    driver, security = case.driver, case.security
    security.price = D(120)  # Above the authenticated ask110; bounds the cash-limited size.
    session = quote_fixtures.NOW.date().isoformat()
    driver._require_initialized = lambda: None
    driver._status = lambda status: status
    driver._decision_set = frozenset((session,))
    driver._preopen_clock_confirmations, driver._executed = {session}, set()
    driver._split_records_by_session, driver._cash_underfill_count = {}, 0
    driver._plans = {session: {"holdings": {}, "split_records": {}, "quantities": {"A": 2, "B": 2},
        "sha256": "a" * 64}}
    driver._order_ids, driver._event_ids, driver._fills = set(), set(), []
    driver._current_holding_census = lambda: {}
    driver._current_quantity = lambda _identity: 0
    driver._ensure_security = lambda _identity: (case.symbol, security)
    driver._portfolio_cash = lambda: D("220.22")
    driver._algorithm.live_mode = False
    engine = NS(id=7, tag=None, quantity=D(1))
    driver._algorithm.transactions = NS(get_open_orders=lambda: (), get_order_by_id=lambda _id: engine)
    dispatched = []

    def reject(symbol, quantity, *, asynchronous, tag):
        assert symbol is case.symbol and quantity == 1 and asynchronous is False
        engine.tag = tag
        assert driver._intent["fee_basis_quote"] == "110"  # Preserved ask fee/size semantics.
        dispatched.append((quantity, tag))
        event = NS(status="Invalid", order_id=7, id=0, symbol=case.symbol, fill_quantity=0)
        driver.on_order_event(event)
        pytest.fail("invalid callback did not stop synchronous market submission")

    driver._algorithm.market_order = reject
    with pytest.raises(base.targets.NewruleError, match="^nonterminal_or_partial_order$"):
        driver.on_after_open()
    assert len(dispatched) == 1 and dispatched[0][0] == 1
    assert not driver._executed and not driver._order_ids and not driver._fills
    assert driver._intent is not None and driver._intent["fill"] is None
    assert driver._cash_underfill_count == 1 and security.price == D(120)
