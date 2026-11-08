"""Only fixed endpoint construction changes; every actual native guard remains."""
import ast
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261028_mark_probe_post_gap_native as p
from tests.target_price_revisions_qc import test_qc_comparison_20261028_mark_probe_post_gap as old

PREFIX = Path('research/target_price_revisions_qc')


@pytest.fixture
def sources():
    return {**old.sources.__wrapped__(),
        'post_gap_source':(PREFIX/'comparison_20261028_mark_probe_post_gap.py').read_bytes()}


def build(sources, **changes):
    args = dict(sources, operation_id='TPR-CMP28-MARK-PROBE-POST-GAP-NATIVE-SYNTHETIC-006', git_head='a'*40)
    args.update(changes)
    return p.build_mark_probe_post_gap_native(**args)


def make_native(sources, monkeypatch, *, successor=True):
    predecessors = {name:value for name,value in sources.items() if name != 'post_gap_source'}
    if successor:
        def render(values, **changes):
            return build(dict(values, post_gap_source=sources['post_gap_source']), **changes)
        monkeypatch.setattr(old, 'build', render)
    return old.native.__wrapped__(predecessors, monkeypatch)


@pytest.fixture
def native(sources, monkeypatch):
    return make_native(sources, monkeypatch)


class NativeClock(datetime):
    """Synthetic native-like subclass; replace retains its concrete class."""
    def replace(self, *args, **kwargs):
        result = super().replace(*args, **kwargs)
        return type(self)(result.year, result.month, result.day, result.hour, result.minute,
            result.second, result.microsecond, tzinfo=result.tzinfo, fold=result.fold)


def subclass_clock(case):
    case.algo.time = NativeClock(2021,2,12,16,1)
    case.algo.utc_time = NativeClock(2021,2,12,21,1)
    assert type(case.algo.time.replace(tzinfo=None)) is NativeClock


def test_subclass_clock_reproduces_old_zero_history_refusal_and_successor_requests_four_plain_endpoints(sources, monkeypatch):
    original = make_native(sources, monkeypatch, successor=False)
    original.initialize();subclass_clock(original);original.algo._probe();out = old.result(original)
    assert out['status'] == 'post_gap_history_scope_unproved' and out['history_calls'] == 0
    assert out['parent_hash_verified'] is out['native_identity_roundtrip'] is True
    assert len(original.control.calendar) == 10 and original.control.history == []
    corrected = make_native(sources, monkeypatch)
    corrected.initialize();subclass_clock(corrected)
    seen = []
    previous = corrected.algo.history
    class History:
        def __getitem__(self, kind):
            request = previous[kind]
            def inspect(symbol, start, end, resolution, **options):
                assert type(start) is datetime and start == datetime(2021,2,8)
                assert type(end) is datetime and end == datetime(2021,2,12,16,1)
                seen.append((start,end))
                return request(symbol,start,end,resolution,**options)
            return inspect
    corrected.algo.history = History();corrected.algo._probe();out = old.result(corrected)
    assert out['status'] == 'completed_post_gap_observations' and out['history_calls'] == len(seen) == 4
    assert len(corrected.control.calendar) == 20
    assert out['universal_absence_proven'] is out['terminal_proven'] is out['target_data_gap_proven'] is False


def test_only_enumerated_endpoint_and_metadata_change_plaintext_preserves_all_guard_method_asts(sources):
    raw, report_raw = build(sources);report = json.loads(report_raw)
    original, _ = p.prior.build_mark_probe_post_gap(**{key:value for key,value in sources.items()
        if key != 'post_gap_source'}, operation_id=report['operation_id'], git_head=report['git_head'])
    def methods(source):
        main = next(node for node in ast.parse(source).body if isinstance(node,ast.ClassDef) and node.name == 'Main')
        return {node.name:node for node in main.body if isinstance(node,ast.FunctionDef)}
    before, after = methods(original), methods(raw)
    for name in before.keys()-{'initialize','_probe'}:
        assert ast.dump(before[name]) == ast.dump(after[name])
    probe = deepcopy(before['_probe'])
    assignment = next(node for node in ast.walk(probe) if isinstance(node,ast.Assign)
        and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='end')
    assignment.value = ast.parse('datetime(2021,2,12,16,1)',mode='eval').body
    assert ast.dump(probe) == ast.dump(after['_probe'])
    initialize = deepcopy(before['initialize'])
    schemas = [node for node in ast.walk(initialize) if isinstance(node,ast.Constant)
        and node.value == 'tpr-cmp28-native-mark-probe-post-gap-result-v1']
    assert len(schemas) == 1
    schemas[0].value = 'tpr-cmp28-native-mark-probe-post-gap-native-result-v1'
    assert ast.dump(initialize) == ast.dump(after['initialize'])
    assert hashlib.sha256(sources['post_gap_source']).hexdigest() == p.POST_GAP_SHA256
    assert raw.startswith(sources['helper_source']+b'\n')
    assert len(raw) == report['main_bytes'] < 60000 and hashlib.sha256(raw).hexdigest() == report['main_sha256']
    config_raw = old.literal(raw,'PROBE_CONFIG_JSON').encode('ascii');cfg = json.loads(config_raw)
    assert hashlib.sha256(config_raw).hexdigest() == old.literal(raw,'PROBE_CONFIG_SHA256') == report['config_sha256']
    assert cfg['predecessor_post_gap_source_sha256'] == p.POST_GAP_SHA256
    assert cfg['request_endpoint_construction'] == report['request_endpoint_construction'] == p.CONSTRUCTION
    assert cfg['failure_session'] == '2021-02-10' and cfg['diagnostic_session'] == '2021-02-12'
    assert report['max_history_calls']==4 and report['max_total_history_rows']==4810
    assert report['max_native_market_hours_calls']==20 and report['max_contains']==report['max_reads']==1
    assert set(report['public_source_sha256']) == {name.name for name in (PREFIX/file for file in (
        'comparison_20261028_mark_probe_post_gap.py','comparison_20261028_mark_probe_control.py',
        'comparison_20261028_mark_probe.py','comparison_20261028_mark_read.py','comparison_20261028_algorithm.py'))}
    assert all(report[key] is False for key in ('native_clock_class_attested','financial_recovery_proven',
        'source_inputs_admitted','native_permission','universal_absence_proven','terminal_proven','target_data_gap_proven'))
    attrs={node.attr for node in ast.walk(ast.parse(raw)) if isinstance(node,ast.Attribute)}
    assert not attrs & {'set_market_price','save_bytes','market_order','set_holdings','download','liquidate','market_on_open_order'}
    compile(ast.parse(raw),'main.py','exec')


@pytest.mark.parametrize('name',['post_gap_source','control_source','base_probe_source','helper_source','producer_source'])
def test_each_closed_public_source_pin_refuses_byte_drift(sources,name):
    sources[name] += b'\n'
    with pytest.raises(p.NativeEndpointProbeRefusal):build(sources)


@pytest.mark.parametrize('changes',[{'operation_id':'foreign'},{'git_head':'0'*40},{'git_head':True}])
def test_operation_and_head_cannot_escape_existing_closed_binding(sources,changes):
    with pytest.raises(p.NativeEndpointProbeRefusal):build(sources,**changes)


@pytest.mark.parametrize('fault',['utc_mismatch','wrong_day','wrong_time','job_drift'])
def test_real_child_clock_and_custody_still_deny_before_any_private_effect(native,fault):
    native.initialize();subclass_clock(native)
    if fault=='utc_mismatch':native.algo.utc_time+=timedelta(minutes=1)
    elif fault=='wrong_day':native.algo.time-=timedelta(days=1);native.algo.utc_time-=timedelta(days=1)
    elif fault=='wrong_time':native.algo.time-=timedelta(minutes=1);native.algo.utc_time-=timedelta(minutes=1)
    else:native.algo.get_locked=lambda:False
    native.algo._probe();out=old.result(native)
    assert out['history_calls']==0 and native.algo.object_store.calls==[]
    assert out['status'] in ('post_gap_runtime_clock_unproved','runtime_custody_unproved')


@pytest.mark.parametrize('fault',['wrong_sid','fillforward','future','before_window','extended','daily_wrong_close','bad_volume'])
def test_existing_exact_row_predicates_remain_enforced(native,fault):
    old.test_exact_rows_must_be_typed_native_identity_noff_within_own_regular_session(native,fault)


@pytest.mark.parametrize('fault',['wrong_day','wrong_zone','wrong_type','calendar_custody'])
def test_existing_native_calendar_and_per_call_custody_proof_remain_enforced(native,fault):
    old.test_native_calendar_proof_refuses_before_history_if_calendar_or_custody_unproved(native,fault)


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_native_calendar_nonordinary_failures_stay_body_free(native,kind):
    old.test_nonordinary_stops_preserve_body_free_semantics_during_native_calendar(native,kind)


@pytest.mark.parametrize('change',[{'start':datetime(2020,2,8)},{'end':datetime(2022,2,12,16,1)},
    {'end':NativeClock(2021,2,12,16,1)},{'maximum':2401},{'maximum':None,'resolution':'unsupported'},
    {'label':'daily'},{'windows':{}}])
def test_history_exact_plain_type_range_year_label_and_row_bounds_are_unchanged(native,change):
    old.test_private_history_helper_cannot_broaden_closed_range_type_label_or_row_budget(native,change)


def test_hard_row_and_call_budgets_do_not_peek_an_extra_row(native):
    old.test_per_symbol_history_bounds_are_hard_and_no_extra_row_is_peeked(native)


def test_ordinary_native_failures_do_not_export_exception_bodies_or_retry(native):
    native.initialize()
    def stop(*_):raise RuntimeError('PRIVATE-ERROR-price-SID-clock')
    native.control.hook=stop
    native.algo._probe();out=old.result(native)
    assert out['status']=='ordinary_native_or_schema_failure' and out['history_calls']==1
    before=list(native.control.events);native.algo._probe();assert native.control.events==before


@pytest.mark.parametrize('fault',['clock','utc','project','job','locked','live'])
def test_drift_during_uncertain_history_stops_before_result_processing_and_never_retries(native,fault):
    native.initialize();subclass_clock(native)
    def drift(*_):
        if fault=='clock':native.algo.time+=timedelta(minutes=1)
        elif fault=='utc':native.algo.utc_time+=timedelta(minutes=1)
        elif fault=='project':native.algo.project_id+=1
        elif fault=='job':native.algo.algorithm_id='d'*32
        elif fault=='locked':native.algo.get_locked=lambda:False
        else:native.algo.live_mode=True
    native.control.hook=drift
    native.algo._probe();out=old.result(native)
    assert out['history_calls']==1 and native.control.yielded==0
    assert out['status'] in ('post_gap_runtime_clock_unproved','runtime_custody_unproved','runtime_custody_changed')
    assert out['native_exact_subscription']['add_security_calls']==0
    before=list(native.control.events);native.algo._probe();assert native.control.events==before
