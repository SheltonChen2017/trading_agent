"""Exact frozen successor functions, synthetic identities/marks, no effects.

Only selected AST functions are executed, not module imports/initialization or
cloud source. Native-shaped fixtures do not prove CLR dispatch or completion.
"""
import ast
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import hashlib
import http.client
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest
from tests.target_price_revisions_qc.test_qc_extended_runtime import nav_fixture

PUBLIC = Path(__file__).resolve().parents[2] / "research/target_price_revisions_qc"
SOURCE = PUBLIC / "extended_algorithm_successor.py"
SOURCE_SHA256 = "e0077b7992dc64515384f56687b350725d694c746a8d4523336d18aa144dd9a8"
CORE_SHA256 = "706ed5efdcb3999400c5349dc8b5200be1d48c4bb01cbfc7fb080608a679d5da"


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs): raise AssertionError("actual private/provider/credential/operator/cloud forbidden")
    monkeypatch.setattr(ops,"read_private",deny)
    monkeypatch.setattr(ops,"credential",deny)
    monkeypatch.setattr(ops.Operations,"__init__",deny)
    monkeypatch.setattr(ops.subprocess,"run",deny)
    monkeypatch.setattr(http.client,"HTTPSConnection",deny)


def _extract(raw, name):
    matches = [node for node in ast.walk(ast.parse(raw)) if isinstance(node,ast.FunctionDef) and node.name == name]
    assert len(matches) == 1
    function = deepcopy(matches[0]); function.decorator_list = []
    return function


def load_runtime():
    raw,core_raw = SOURCE.read_bytes(),(PUBLIC/"extended_core.py").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA256
    assert hashlib.sha256(core_raw).hexdigest() == CORE_SHA256
    core = ModuleType("synthetic_frozen_numeric_core")
    core.__dict__.update(Fraction=Fraction,Decimal=Decimal,Context=Context,localcontext=localcontext)
    numeric = ast.Module(body=[_extract(core_raw,name) for name in ("_number","_text","native_fraction")],type_ignores=[])
    exec(compile(ast.fix_missing_locations(numeric),"<public-core-numeric-functions>","exec"),core.__dict__)
    core.VALUATIONS = {"2021-01-04"}  # The existing synthetic NAV fixture's one declared session.
    core.publish_account_nav = lambda algorithm,value:algorithm.plot("EXT26 Account NAV","NAV",value)
    namespace = dict(core=core,Fraction=Fraction,datetime=datetime,timedelta=timedelta,ZoneInfo=ZoneInfo,
        UTC=timezone.utc,NY=ZoneInfo("America/New_York"),native_fraction=core.native_fraction,
        Universe=NS(UNCHANGED=object()),TradeBar=type("SyntheticTradeBar",(),{}))
    names = ("_member_inventory","_constituents_for","_daily_audit","_native_clock")
    selected = ast.Module(body=[_extract(raw,name) for name in names],type_ignores=[])
    exec(compile(ast.fix_missing_locations(selected),str(SOURCE)+"::<selected-AST-only>","exec"),namespace)
    klass = type("SyntheticFrozenSuccessor",(),{name:namespace[name] for name in ("_constituents_for","_daily_audit")})
    klass._native_clock = staticmethod(namespace["_native_clock"])
    return NS(TargetPriceExtendedAlgorithm=klass,TradeBar=namespace["TradeBar"],core=core,
        _member_inventory=namespace["_member_inventory"],Universe=namespace["Universe"],namespace=namespace)


@pytest.fixture
def runtime(): return load_runtime()


def member(index,weight):
    return {"ticker":"SYNTHETIC-"+str(index),"symbol":NS(id="SYNTHETIC-ID-"+str(index),value="SYNTHETIC-"+str(index)),"weight":weight}


def membership_fixture(runtime,weights):
    algo = runtime.TargetPriceExtendedAlgorithm()
    algo.utc_time = datetime(2021,1,4,15)
    prior = {"effective":datetime(2021,1,3,15,tzinfo=timezone.utc),"received":datetime(2021,1,3,15,tzinfo=timezone.utc),"members":[]}
    algo._snapshots = {"SPY":[prior]}
    reasons = []; algo._reason = reasons.append
    rows = [NS(symbol=member(index,weight)["symbol"],weight=weight,end_time=datetime(2021,1,4,14))
        for index,weight in enumerate(weights)]
    return algo,rows,reasons


def test_exact_ast_functions_are_from_immutable_successor_not_earlier_runtime(runtime):
    assert str(SOURCE)+"::<selected-AST-only>" == runtime.TargetPriceExtendedAlgorithm._daily_audit.__code__.co_filename
    assert str(SOURCE)+"::<selected-AST-only>" == runtime.TargetPriceExtendedAlgorithm._constituents_for.__code__.co_filename
    assert str(SOURCE)+"::<selected-AST-only>" == runtime._member_inventory.__code__.co_filename


@pytest.mark.parametrize("weight,category,count,eligible",[(None,"unknown_weight",1,False),("0","zero_weight",1,False),
    ("0.25","known_weight",1,True),("1","known_weight",1,True)])
def test_member_unknown_zero_positive_one_have_distinct_frozen_meaning(runtime,weight,category,count,eligible):
    item = member(0,weight); before = deepcopy(item)
    selected,coverage = runtime._member_inventory([item])
    assert item["weight"] == before["weight"] and coverage[category]["count"] == count
    assert len(selected) == int(eligible)
    assert coverage[category]["weight"] == (Fraction(weight) if weight is not None else Fraction(0))
    assert sum(row["count"] for row in coverage.values()) == 1
    if eligible: assert selected[0][:2] == (str(item["symbol"].id),Fraction(weight))


@pytest.mark.parametrize("weights",[[None,0,Decimal("0.25"),1],[1,1,1,1]])
def test_callback_retains_none_zero_native_weights_and_valid_total_over_three(runtime,weights):
    algo,rows,reasons = membership_fixture(runtime,weights)
    returned = algo._constituents_for("SPY",rows)
    assert returned == [row.symbol for row in rows] and not reasons and len(algo._snapshots["SPY"]) == 2
    members = algo._snapshots["SPY"][-1]["members"]
    expected = [None if weight is None else runtime.core._text(runtime.core.native_fraction(weight)) for weight in weights]
    assert [item["weight"] for item in members] == expected
    selected,coverage = runtime._member_inventory(members)
    assert coverage["unknown_weight"]["count"] == weights.count(None)
    assert coverage["zero_weight"]["count"] == weights.count(0)
    assert sum((row["weight"] for row in coverage.values()),Fraction(0)) == sum((Fraction(weight) for weight in weights if weight is not None),Fraction(0))
    assert len(selected) == sum(weight is not None and weight != 0 for weight in weights)
    if all(weight == 1 for weight in weights): assert sum(item[1] for item in selected) == 4


@pytest.mark.parametrize("bad",["-0.0001","-1","1.0001","2","100"])
def test_member_lower_and_upper_bounds_are_not_percent_normalized(runtime,bad):
    with pytest.raises(ValueError,match="membership weight outside bounds"):
        runtime._member_inventory([member(0,bad)])


@pytest.mark.parametrize("bad",[Decimal("-0.0001"),Decimal("1.0001"),Decimal("100")])
@pytest.mark.parametrize("position",[0,1])
def test_invalid_native_member_refuses_before_any_snapshot_write(runtime,bad,position):
    weights = [Decimal("0.25"),Decimal("0.5")]; weights[position] = bad
    algo,rows,reasons = membership_fixture(runtime,weights); before = deepcopy(algo._snapshots)
    with pytest.raises(ValueError,match="membership weight outside bounds"): algo._constituents_for("SPY",rows)
    assert algo._snapshots == before and reasons == []


def test_future_membership_callback_refuses_before_any_snapshot_write(runtime):
    algo,rows,reasons = membership_fixture(runtime,[Decimal("0.25")]); rows[0].end_time = algo.utc_time+timedelta(seconds=1)
    before = deepcopy(algo._snapshots)
    with pytest.raises(ValueError,match="future membership callback"): algo._constituents_for("SPY",rows)
    assert algo._snapshots == before and reasons == []


def marked_fixture(runtime,kind):
    algo,security,bar,records = nav_fixture(runtime)
    algo._warning_ids = {"A"} if kind in {"warning","both"} else set()
    algo._delisted_ids = {"A"} if kind in {"delisted","both"} else set()
    algo._prior_close_nav,algo._prior_close_day = Fraction(199),date(2021,1,1)
    plots = []; algo.plot = lambda *args:plots.append(args)
    return algo,security,bar,records,plots


def accounting_state(algo):
    names = ("_cash_ledger","_quantity_ledger","_prior_close_nav","_prior_close_day","_valuation_days",
        "_position_ledger_mismatches","_max_cash_residual","_max_nav_residual","_max_name_exposure",
        "_risk_breaches","_name_soft_cap_breaches","_fees","_warning_ids","_delisted_ids")
    return {name:deepcopy(getattr(algo,name)) for name in names}


@pytest.mark.parametrize("kind",["ordinary","warning","delisted","both"])
def test_same_day_nonfuture_mark_is_valid_for_every_held_identity(runtime,kind):
    algo,_,bar,records,plots = marked_fixture(runtime,kind)
    algo._daily_audit()
    assert len(records) == len(plots) == 1 and records[0][0] == "NAV"
    assert algo._valuation_days == {"2021-01-04"} and algo._prior_close_nav == 200 and algo._prior_close_day == date(2021,1,4)
    payload = records[0][1]
    assert payload["independent_holdings_value"] == 100 and payload["nav_ledger_residual"] == "0"
    assert payload["raw_marks"] == [{"security_id":"A","price":Fraction(10),"mark_utc":"2021-01-04T21:00:00+00:00"}]
    assert "stale" not in payload["raw_marks"][0] and bar.end_time.date() == date(2021,1,4)


@pytest.mark.parametrize("kind",["ordinary","warning","delisted","both"])
@pytest.mark.parametrize("clock",["stale","same_day_future"])
def test_stale_or_same_day_future_mark_refuses_every_held_identity_atomically(runtime,kind,clock):
    algo,_,bar,records,plots = marked_fixture(runtime,kind)
    bar.end_time = datetime(2021,1,3,16) if clock == "stale" else datetime(2021,1,4,16,2)
    before = accounting_state(algo)
    with pytest.raises(ValueError,match="held RAW closing mark stale/future"): algo._daily_audit()
    assert accounting_state(algo) == before and records == plots == []


@pytest.mark.parametrize("kind",["ordinary","warning","delisted","both"])
def test_mark_exactly_at_current_clock_is_nonfuture_not_strictly_earlier(runtime,kind):
    algo,_,bar,records,plots = marked_fixture(runtime,kind); bar.end_time = datetime(2021,1,4,16,1)
    algo._daily_audit()
    assert len(records) == len(plots) == 1 and algo._valuation_days == {"2021-01-04"}
