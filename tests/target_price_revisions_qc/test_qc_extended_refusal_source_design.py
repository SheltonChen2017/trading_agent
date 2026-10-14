"""Pure public generator and selected-function hooks; native effects denied."""
import ast
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
import hashlib
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from research.target_price_revisions_qc import extended_refusal_source_design as d
from research.target_price_revisions_qc import extended_refusal_witness_context_successor as context
from tests.target_price_revisions_qc import test_qc_extended_frozen_guards as frozen
from tests.target_price_revisions_qc import test_qc_extended_refusal_witness_context_successor as fake

PUBLIC = Path(__file__).resolve().parents[2]/"research/target_price_revisions_qc"
BUNDLE = (PUBLIC/"extended_source_bundle_completion.json").read_bytes()


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    from research.target_price_revisions_qc import extended_operations as ops
    import http.client
    def deny(*_args,**_kwargs): raise AssertionError("actual provider/private/credential/operator/cloud forbidden")
    monkeypatch.setattr(ops,"read_private",deny)
    monkeypatch.setattr(ops,"credential",deny)
    monkeypatch.setattr(ops.Operations,"__init__",deny)
    monkeypatch.setattr(ops.subprocess,"run",deny)
    monkeypatch.setattr(http.client,"HTTPSConnection",deny)


class RecordingContext:
    def __init__(self,evidence,store,core,bar):
        self.binding_args = evidence,store,core,bar
        self.calls,self.failure = [],None
    def membership_context(self,*args):
        self.calls.append(("membership",args))
        if self.failure is not None: raise self.failure
        return False
    def mark_context(self,*args):
        self.calls.append(("mark",args))
        if self.failure is not None: raise self.failure
        return False


def runtime():
    source = d.build_main(BUNDLE)["main_py"]
    base = frozen.load_runtime(); namespace = dict(base.namespace)
    names = ("_member_inventory","_constituents_for","_daily_audit","_native_clock")
    module = ast.Module(body=[frozen._extract(source.encode(),name) for name in names],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),"<public-generated-guard-hooks>","exec"),namespace)
    klass = type("SyntheticGeneratedGuards",(),{name:namespace[name] for name in ("_constituents_for","_daily_audit")})
    klass._native_clock = staticmethod(namespace["_native_clock"])
    return NS(TargetPriceExtendedAlgorithm=klass,TradeBar=namespace["TradeBar"],core=namespace["core"],namespace=namespace,source=source)


def initialize_witness(algo,rt,constructor=RecordingContext):
    tree = ast.parse(rt.source)
    initializer = next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=="initialize")
    assignments = [node for node in initializer.body if isinstance(node,ast.Assign)
        and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=="ContextRefusalWitness"]
    assert len(assignments)==1
    algo._evidence,algo.object_store = fake.Evidence(),fake.Store()
    environment = dict(rt.namespace,self=algo,ContextRefusalWitness=constructor)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[deepcopy(assignments[0])],type_ignores=[])),
        "<public-generated-one-persistent-init>","exec"),environment)
    return algo._refusal_witness


class StripInstrumentation(ast.NodeTransformer):
    def visit_ImportFrom(self,node):
        if node.module==d.HELPER_MODULE: return None
        return node
    def visit_Assign(self,node):
        if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=="ContextRefusalWitness": return None
        if ([target.id if isinstance(target,ast.Name) else None for target in node.targets]==["last","mark_clock","price"]
                and isinstance(node.value,ast.Constant) and node.value.value is None): return None
        return node
    def visit_Try(self,node):
        methods = [call.func.attr for handler in node.handlers for call in ast.walk(handler)
            if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute)]
        if "membership_context" in methods or "mark_context" in methods:
            assert len(node.handlers)==1 and node.handlers[0].type.id=="ValueError"
            assert node.handlers[0].body[-1].exc is None and node.handlers[0].body[-1].cause is None
            return node.body
        return self.generic_visit(node)


def test_exact_restoration_byte_ast_and_character_budget_without_other_reformatting():
    result = d.build_main(BUNDLE); main,base = result["main_py"],d.restored_main(BUNDLE)
    assert len(base.encode())==60012 and hashlib.sha256(base.encode()).hexdigest()==d.RESTORED_SHA256
    assert len(main)==len(main.encode())==60658 and result["remaining_main_characters"]==142
    assert d.remove_hooks(main)==base
    stripped = StripInstrumentation().visit(ast.parse(main))
    assert ast.dump(stripped,include_attributes=False)==ast.dump(ast.parse(base),include_attributes=False)
    assert result["new_codex_attempts"]==result["new_jobs"]==0 and result["attempt_reset"] is False
    assert result["economics_accepted"] is False and result["compiled_source_proven"] is False


def test_single_native_import_and_unconditional_persistent_instance_after_evidence():
    source = d.build_main(BUNDLE)["main_py"]; tree = ast.parse(source)
    imports = [node for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module==d.HELPER_MODULE]
    assert len(imports)==1 and [(name.name,name.asname) for name in imports[0].names]==[("ContextRefusalWitness",None)]
    calls = [node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="ContextRefusalWitness"]
    assert len(calls)==1 and [ast.unparse(arg) for arg in calls[0].args]==["self._evidence","self.object_store","core","TradeBar"]
    initialize = next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=="initialize")
    evidence = next(index for index,node in enumerate(initialize.body) if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Attribute) and target.attr=="_evidence" for target in node.targets))
    witness = next(index for index,node in enumerate(initialize.body) if isinstance(node,ast.Assign) and node.value is calls[0])
    assert witness==evidence+1 and len(calls[0].keywords)==0
    raw = (PUBLIC/(d.HELPER_MODULE+".py")).read_bytes()
    assert hashlib.sha256(raw[:d.HELPER_PREFIX_BYTES]).hexdigest()==d.HELPER_PREFIX_SHA256


@pytest.mark.parametrize("fault",["bytes","type"])
def test_unknown_public_bundle_refuses_before_design(fault):
    value = BUNDLE+b" " if fault=="bytes" else BUNDLE.decode()
    with pytest.raises(ValueError): d.build_main(value)


def test_over_budget_design_refuses_and_exact_boundary_is_not_silently_raised(monkeypatch):
    monkeypatch.setattr(d,"MAX_MAIN_CHARACTERS",60657)
    with pytest.raises(ValueError,match="60658 > 60657"): d.build_main(BUNDLE)
    monkeypatch.setattr(d,"MAX_MAIN_CHARACTERS",60658)
    assert d.build_main(BUNDLE)["remaining_main_characters"]==0


def test_unrelated_comment_or_guard_change_cannot_be_masked_as_instrumentation():
    main = d.build_main(BUNDLE)["main_py"]
    for changed in (main+"# extra unrelated delta\n",main.replace("if not 0 <= weight <= 1:","if False:")):
        with pytest.raises(ValueError): d.remove_hooks(changed)


@pytest.mark.parametrize("bad",[Decimal("-0.1"),Decimal("1.1"),Decimal("100")])
@pytest.mark.parametrize("diagnostic_failure",[False,True])
def test_membership_hook_reraises_same_original_object_before_snapshots(bad,diagnostic_failure):
    rt = runtime(); algo,rows,reasons = frozen.membership_fixture(rt,[Decimal("0.25"),bad])
    witness = initialize_witness(algo,rt)
    if diagnostic_failure: witness.failure=RuntimeError("synthetic context-getter failure")
    before = deepcopy(algo._snapshots)
    with pytest.raises(ValueError,match="membership weight outside bounds") as caught: algo._constituents_for("SPY",rows)
    assert witness.calls[0][0]=="membership" and caught.value is witness.calls[0][1][0]
    assert witness.calls[0][1][1]=="SPY" and len(witness.calls[0][1][3])==len(rows)
    assert all(captured is original for captured,original in zip(witness.calls[0][1][3],rows))
    assert algo._snapshots==before and reasons==[] and algo._refusal_witness is witness


@pytest.mark.parametrize("kind",["ordinary","warning","delisted","both"])
@pytest.mark.parametrize("clock",["stale","same_day_future"])
def test_mark_hook_refuses_all_ids_without_partial_accounting_or_new_exception(kind,clock):
    rt = runtime(); algo,_,bar,records,plots = frozen.marked_fixture(rt,kind)
    witness = initialize_witness(algo,rt); witness.failure=RuntimeError("synthetic optional-getter failure")
    bar.end_time=datetime(2021,1,3,16) if clock=="stale" else datetime(2021,1,4,16,2)
    before=frozen.accounting_state(algo)
    with pytest.raises(ValueError,match="held RAW closing mark stale/future") as caught: algo._daily_audit()
    assert caught.value is witness.calls[0][1][0] and witness.calls[0][0]=="mark"
    assert frozen.accounting_state(algo)==before and records==plots==[] and algo._refusal_witness is witness


def test_each_held_iteration_clears_context_locals_before_getter_failure():
    rt=runtime(); algo,security,_,records,plots=frozen.marked_fixture(rt,"both")
    second=type("SyntheticHashableSymbol",(),{})(); second.id=second.value="B"
    held=NS(symbol=second,invested=True,quantity="10",holdings_value="100")
    original=ValueError("held RAW native closing mark missing")
    def refuse(): raise original
    bad_security=NS(price="10",get_last_data=refuse)
    algo.portfolio[second]=held; algo.portfolio.total_holdings_value="200"; algo.portfolio.total_portfolio_value="300"
    algo._quantity_ledger["B"]=Fraction(10); algo._assert_raw_subscriptions=lambda symbol:security if symbol.id=="A" else bad_security
    witness=initialize_witness(algo,rt); before=frozen.accounting_state(algo)
    with pytest.raises(ValueError) as caught: algo._daily_audit()
    assert caught.value is original and witness.calls[0][1][0] is original
    assert witness.calls[0][1][4:7]==(None,None,None)
    assert frozen.accounting_state(algo)==before and records==plots==[]


@pytest.mark.parametrize("guard",["membership","mark"])
@pytest.mark.parametrize("cancellation",[KeyboardInterrupt,SystemExit])
def test_genuine_cancellation_is_not_swallowed_by_thin_hook(guard,cancellation):
    rt=runtime()
    if guard=="membership":
        algo,rows,_=frozen.membership_fixture(rt,[Decimal("1.1")]); invoke=lambda:algo._constituents_for("SPY",rows)
    else:
        algo,_,bar,_,_=frozen.marked_fixture(rt,"both"); bar.end_time=datetime(2021,1,3,16); invoke=algo._daily_audit
    witness=initialize_witness(algo,rt); witness.failure=cancellation()
    with pytest.raises(cancellation): invoke()


def test_valid_membership_total_four_and_mark_are_unchanged_without_witness_call():
    rt=runtime(); algo,rows,_=frozen.membership_fixture(rt,[1,1,1,1]); witness=initialize_witness(algo,rt)
    assert algo._constituents_for("SPY",rows)==[row.symbol for row in rows] and witness.calls==[]
    assert sum(Fraction(row["weight"]) for row in algo._snapshots["SPY"][-1]["members"])==4
    algo,_,_,records,plots=frozen.marked_fixture(rt,"both"); witness=initialize_witness(algo,rt)
    algo._daily_audit()
    assert witness.calls==[] and len(records)==len(plots)==1 and algo._prior_close_nav==200


def test_same_real_context_instance_limits_repeated_generated_guard_witnesses_to_two_objects():
    rt=runtime(); algo,rows,_=frozen.membership_fixture(rt,[Decimal("1.1")])
    witness=initialize_witness(algo,rt,context.ContextRefusalWitness); store=algo.object_store
    snapshot=deepcopy(algo._snapshots)
    for _ in range(2):
        with pytest.raises(ValueError,match="membership weight outside bounds"): algo._constituents_for("SPY",rows)
    assert algo._refusal_witness is witness and algo._snapshots==snapshot
    nav_algo,_,bar,records,plots=frozen.marked_fixture(rt,"both"); nav_algo._refusal_witness=witness
    bar.end_time=datetime(2021,1,3,16); before=frozen.accounting_state(nav_algo)
    for _ in range(2):
        with pytest.raises(ValueError,match="held RAW closing mark stale/future"): nav_algo._daily_audit()
    assert frozen.accounting_state(nav_algo)==before and records==plots==[]
    assert len(store.data)==2 and sum(kind=="save" for kind,_ in store.calls)==2
    assert all("/37650980/synthetic_context_31/" in key for key in store.data)
    assert all(row["status"]=="verified_private_witness" for row in witness.outcomes.values())
