"""Execute only an in-memory cell against explicitly synthetic native modules."""
import ast
import datetime as dt
import hashlib
import http.client
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import recovery_20261028_native as m
from tests.target_price_revisions_qc import test_qc_extended_refusal_witness_read_design as base

ISSUED = dt.datetime(2026,10,28,12,tzinfo=dt.timezone.utc)
OPERATION = 'TPR-EXT26-RECOVERY-20261028-SYNTHETIC-001'


@pytest.fixture(autouse=True)
def deny_actual_effects(monkeypatch):
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args,**_kwargs): raise AssertionError('actual private/provider/operator/cloud forbidden')
    for name in ('read_private','credential'): monkeypatch.setattr(ops,name,deny)
    monkeypatch.setattr(ops.Operations,'__init__',deny)
    monkeypatch.setattr(ops.subprocess,'run',deny)
    monkeypatch.setattr(http.client,'HTTPSConnection',deny)


def arguments():
    raw=Path(m.__file__).read_bytes()
    return dict(operation_id=OPERATION,issued_utc=ISSUED.isoformat(),
        expires_utc=(ISSUED+dt.timedelta(seconds=600)).isoformat(),builder_raw=raw,
        expected_builder_sha256=hashlib.sha256(raw).hexdigest(),
        reader_raw=Path(base.d.__file__).read_bytes(),witness_raw=Path(base.w.__file__).read_bytes())


def build(**overrides):
    args=arguments();args.update(overrides)
    return m.build_cell(**args)


@pytest.fixture
def synthetic(monkeypatch):
    store=base.Store()
    state=NS(now=ISSUED+dt.timedelta(seconds=30),tick=10.0,constructor_calls=0,
        init_hook=lambda:None,store=store,qb=NS(project_id=m.reader.PROJECT,object_store=store),printed=[])
    class Clock(dt.datetime):
        @classmethod
        def now(cls,tz=None):return state.now
    fake_datetime=ModuleType('datetime');fake_datetime.__dict__.update(vars(dt));fake_datetime.datetime=Clock
    fake_time=ModuleType('time');fake_time.__dict__.update(vars(time));fake_time.monotonic=lambda:state.tick
    research=ModuleType('QuantConnect.Research')
    def constructor():
        state.constructor_calls+=1
        state.init_hook()
        return state.qb
    research.QuantBook=constructor
    system=ModuleType('System');system.Object=NS(ReferenceEquals=lambda left,right:left is right)
    monkeypatch.setitem(sys.modules,'datetime',fake_datetime)
    monkeypatch.setitem(sys.modules,'time',fake_time)
    monkeypatch.setitem(sys.modules,'QuantConnect',ModuleType('QuantConnect'))
    monkeypatch.setitem(sys.modules,'QuantConnect.Research',research)
    monkeypatch.setitem(sys.modules,'System',system)
    def execute(cell=None):
        namespace={'print':lambda value:state.printed.append(value)}
        state.namespace=namespace
        exec(compile(build()[0] if cell is None else cell,'<synthetic-recovery-cell>','exec'),namespace)
        return namespace['_tpr_recovery_result']
    state.execute=execute
    return state


def test_exact_program_is_embedded_one_fresh_constructor_and_no_notebook_effect():
    cell,manifest=build()
    tree=ast.parse(cell)
    literal=next(node.value.value for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(name,ast.Name) and name.id=='_tpr_program' for name in node.targets))
    args=arguments()
    assert literal==base.d.build_native_program(args['reader_raw'],expected_module_sha256=m.READER_SHA256,
        witness_raw=args['witness_raw'])
    assert hashlib.sha256(literal.encode()).hexdigest()==manifest['program_sha256']
    assert len([node for node in ast.walk(tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Name) and node.func.id=='_tpr_QuantBook'])==1
    assert not any(token in cell for token in ('2026-10-22','jupyter_create_notebook','jupyter_execute_cell','History('))
    assert manifest['append_owned_cell_only'] and manifest['separate_execution_claim_required']
    assert manifest['effects_authorized'] is manifest['off_baseline_valid'] is False
    assert manifest['cell_sha256']==hashlib.sha256(cell.encode()).hexdigest()
    compile(cell,'<unexecuted-public-cell>','exec')


def test_full_safe_classifications_survive_without_raw_ids_scalars_clocks(synthetic):
    result=synthetic.execute()
    assert result['status']=='completed_diagnostic_only'
    assert result['quantbook_initializations_attempted']==result['quantbook_initializations_completed']==1
    assert result['contains_calls']==result['read_calls']==2
    assert synthetic.constructor_calls==1
    assert synthetic.store.calls==[(method,base.d.witness_key(kind)) for kind in base.d.KINDS
        for method in ('contains_key','read_bytes')]
    rows=result['diagnostic']['objects']
    assert rows[0]['diagnostic']['raw_weight']['range']=='above_one'
    assert rows[0]['diagnostic']['numeric_values_equal'] is True
    assert rows[0]['diagnostic']['units_proven'] is rows[0]['diagnostic']['source_date_proven'] is False
    text=synthetic.printed[0]
    assert len(synthetic.printed)==1
    assert base.PRIVATE_ID not in text and base.PRIVATE_NUMBER not in text and '2021-01-03T' not in text
    assert result['native_project_custody_proven'] is result['economics_accepted'] is False
    assert result['sdk_hard_timeout_proven'] is result['byte_bound_before_native_allocation_proven'] is False


@pytest.mark.parametrize('project',[0,1,True,'37650980',None])
def test_wrong_actual_project_refuses_before_store_calls(synthetic,project):
    synthetic.qb.project_id=project
    result=synthetic.execute()
    assert result['status']=='failed_or_uncertain'
    assert result['native_internal_project_id_observed'] is False
    assert synthetic.store.calls==[]


@pytest.mark.parametrize('fault',['expired','before_issued','naive','nan_tick','bool_tick'])
def test_invalid_start_clock_blocks_quantbook_initialization(synthetic,fault):
    if fault=='expired':synthetic.now=ISSUED+dt.timedelta(seconds=600)
    elif fault=='before_issued':synthetic.now=ISSUED-dt.timedelta(seconds=1)
    elif fault=='naive':synthetic.now=synthetic.now.replace(tzinfo=None)
    elif fault=='nan_tick':synthetic.tick=float('nan')
    else:synthetic.tick=True
    result=synthetic.execute()
    assert result['status']=='failed_or_uncertain'
    assert result['quantbook_initializations_attempted']==synthetic.constructor_calls==0
    assert synthetic.store.calls==[]


@pytest.mark.parametrize('clock',['wall','monotonic'])
def test_initialization_time_is_included_in_whole_scope_budget(synthetic,clock):
    def slow():
        if clock=='wall':synthetic.now+=dt.timedelta(seconds=601)
        else:synthetic.tick+=601
    synthetic.init_hook=slow
    result=synthetic.execute()
    assert result['quantbook_initializations_attempted']==result['quantbook_initializations_completed']==1
    assert result['status']=='failed_or_uncertain' and synthetic.store.calls==[]


@pytest.mark.parametrize('fault',['store','project','utc_rollback','tick_rollback'])
def test_post_contains_custody_clock_drift_stops_before_read(synthetic,fault):
    original=synthetic.store.contains_key
    def changed(key):
        returned=original(key)
        if fault=='store':synthetic.qb.object_store=base.Store()
        elif fault=='project':synthetic.qb.project_id=1
        elif fault=='utc_rollback':synthetic.now-=dt.timedelta(seconds=1)
        else:synthetic.tick-=1
        return returned
    synthetic.store.contains_key=changed
    result=synthetic.execute()
    assert result['status']=='failed_or_uncertain' and result['contains_calls']==1 and result['read_calls']==0
    assert synthetic.store.calls==[('contains_key',base.d.witness_key('membership'))]


def test_absent_keys_are_not_zero_inputs_or_a_successful_baseline(synthetic):
    synthetic.store.values={}
    result=synthetic.execute()
    assert result['status']=='completed_diagnostic_only'
    assert result['contains_calls']==2 and result['read_calls']==0
    assert all(row['status']=='absent_uninterpreted' for row in result['diagnostic']['objects'])
    assert result['off_baseline_valid'] is False


@pytest.mark.parametrize('value',[False,1])
def test_native_reference_result_must_be_exact_true_before_reads(synthetic,monkeypatch,value):
    monkeypatch.setattr(sys.modules['System'],'Object',NS(ReferenceEquals=lambda *_:value))
    result=synthetic.execute()
    assert result['status']=='failed_or_uncertain' and synthetic.store.calls==[]


@pytest.mark.parametrize('program,contains,reads',[
    ("NATIVE_OBJECT_STORE.contains_key('foreign-private-key')",0,0),
    ("NATIVE_OBJECT_STORE.read_bytes(SYNTHETIC_KEY)",0,0),
    ("NATIVE_OBJECT_STORE.contains_key(SYNTHETIC_KEY)\nNATIVE_OBJECT_STORE.contains_key(SYNTHETIC_KEY)",1,0),
    ("NATIVE_OBJECT_STORE.contains_key(SYNTHETIC_KEY)\nNATIVE_OBJECT_STORE.read_bytes(SYNTHETIC_KEY)\nNATIVE_OBJECT_STORE.read_bytes(SYNTHETIC_KEY)",1,1),
])
def test_store_proxy_independently_refuses_extra_keys_and_repeated_effects(synthetic,program,contains,reads):
    # Instrument only an in-memory synthetic cell to probe its intrinsic guard;
    # this hash is never presented as the genuine pinned program or native cell.
    program=program.replace('SYNTHETIC_KEY',repr(base.d.witness_key('membership')))
    tree=ast.parse(build()[0])
    for node in tree.body:
        if not isinstance(node,ast.Assign):continue
        if any(isinstance(name,ast.Name) and name.id=='_tpr_program' for name in node.targets):
            node.value=ast.Constant(program)
        elif any(isinstance(name,ast.Name) and name.id=='_tpr_bound' for name in node.targets):
            bound=ast.literal_eval(node.value);bound['program_sha256']=hashlib.sha256(program.encode()).hexdigest()
            node.value=ast.parse(repr(bound),mode='eval').body
    result=synthetic.execute(ast.unparse(ast.fix_missing_locations(tree)))
    assert result['status']=='failed_or_uncertain'
    assert result['contains_calls']==contains and result['read_calls']==reads
    assert len(synthetic.store.calls)==contains+reads


def test_unstructured_native_initialization_output_is_withheld(synthetic):
    def noisy():
        print('synthetic-private-initialization-output')
        print('synthetic-private-stderr',file=sys.stderr)
    synthetic.init_hook=noisy
    result=synthetic.execute()
    assert result['status']=='completed_diagnostic_only'
    assert all('synthetic-private-' not in text for text in synthetic.printed)


@pytest.mark.parametrize('error',[RuntimeError,KeyboardInterrupt,SystemExit])
def test_body_free_errors_preserve_attempted_counts_and_cancellation_propagates(synthetic,error):
    def broken(_key):raise error('synthetic-body-NEVER-EMIT')
    synthetic.store.read_bytes=broken
    if error is RuntimeError:result=synthetic.execute()
    else:
        with pytest.raises(BaseException) as stopped:synthetic.execute()
        assert type(stopped.value).__name__ in {'_TPRRecoveryCancelled','_TPRRecoveryFatal'}
        result=stopped.value.result
        assert 'synthetic-body-NEVER-EMIT' not in str(stopped.value)
    assert result['contains_calls']==result['read_calls']==1
    assert 'synthetic-body-NEVER-EMIT' not in synthetic.printed[0]
    assert result['status']==('cancelled' if error is KeyboardInterrupt else 'failed_or_uncertain')


@pytest.mark.parametrize('field,value',[
    ('operation_id','old-operation'),('operation_id',None),('issued_utc','2026-10-28T12:00:00'),
    ('expires_utc',ISSUED.isoformat()),('expires_utc',(ISSUED+dt.timedelta(seconds=601)).isoformat()),
    ('expected_builder_sha256','a'*64),('reader_raw',b'foreign'),('witness_raw',b'foreign'),
    ('builder_raw',b'oversized'*10000),
])
def test_public_source_scope_shape_and_drift_refuse_closed(field,value):
    with pytest.raises(m.RecoveryBuildRefusal):build(**{field:value})
