"""Synthetic continuation identities only; no real capture, claim or cloud job."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import ast
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_off_attempt_continuation as m
from tests.target_price_revisions_qc import test_qc_extended_native as base

ROOT = Path(__file__).resolve().parents[2]
N = m.e.JsonNumber
NOW = datetime(2026, 10, 26, 20, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def no_actual_effects(monkeypatch):
    import os
    import socket
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kwargs):
        raise AssertionError('private/provider/operator/cloud effects forbidden')
    monkeypatch.setattr(ops, 'read_private', deny)
    monkeypatch.setattr(ops, 'credential', deny)
    monkeypatch.setattr(ops.Operations, '__init__', deny)
    monkeypatch.setattr(ops.subprocess, 'run', deny)
    monkeypatch.setattr(ops.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(os, 'open', deny)


@pytest.fixture
def sources():
    return {name: (ROOT / name).read_bytes() for name in (*m.SOURCE_PINS, m.SOURCE_RELATIVE)}


def arguments(sources, *, sequence=1, prior=()):
    return dict(operation_id=f'TPR-EXT26-OFF-CONT-SYNTHETIC-{sequence:03d}', git_head='a'*40,
        owner_instruction_sha256='b'*64, producer_source_hashes={name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()},
        cloud_source_hashes={'main.py': 'c'*64, 'extended_config.py': m.CLOUD_CONFIG_SHA256},
        created_utc=(NOW + timedelta(minutes=sequence)).isoformat(),
        expires_utc=(NOW + timedelta(minutes=sequence, seconds=60)).isoformat(), prior=prior)


def draft(sources, **kwargs):
    return m.prepare_reservation(**arguments(sources, **kwargs))


def body(raw):
    return m.e.parse_json(raw)


def test_first_fresh_attempt_and_reserved_look_are_not_an_observed_run(sources):
    raw = draft(sources)
    reservation = body(raw)
    assert reservation['attempt'].fraction() == 4
    assert reservation['reserved_look_sequence'].fraction() == 34
    assert reservation['historical_anchor']['off_codex_attempts_consumed'].fraction() == 3
    assert reservation['historical_anchor']['observed_looks'].fraction() == 33
    assert reservation['prior_census']['observed_jobs_added'].fraction() == 0
    assert reservation['native_permission'] is reservation['durable_claim_published'] is False
    assert reservation['accepted_metrics'] is None


def test_compile_failure_spends_attempt_but_not_job_or_look(sources):
    raw = draft(sources)
    closure = m.close_reservation(raw, terminal='compile_failed', compile_id='compile-synthetic-4')
    prior = [{'reservation': raw, 'closure': closure}]
    census = m.continuation_census(prior)
    assert census == {'continuation_attempts_spent': 1, 'observed_jobs_added': 0,
        'observed_looks_added': 0, 'outcome_looks_added': 0, 'unresolved_predecessors': 0}
    next_raw = draft(sources, sequence=2, prior=prior)
    assert body(next_raw)['attempt'].fraction() == 5
    assert body(next_raw)['reserved_look_sequence'].fraction() == 35
    assert body(next_raw)['previous_reservation_sha256'] == m._sha(raw)
    assert body(next_raw)['previous_closure_sha256'] == m._sha(closure)


@pytest.mark.parametrize('with_job', [False, True])
def test_unresolved_effect_never_reopens_an_automatic_next_attempt(sources, with_job):
    raw = draft(sources)
    closure = m.close_reservation(raw, terminal='unresolved', compile_id='compile-synthetic-4',
        backtest_id='job-synthetic-4' if with_job else None)
    report = body(closure)
    assert report['actual_jobs_bound'] == (N('1') if with_job else None)
    assert report['terminal_resolved'] is False
    prior = [{'reservation': raw, 'closure': closure}]
    assert m.continuation_census(prior)['unresolved_predecessors'] == 1
    with pytest.raises(m.Refusal):
        draft(sources, sequence=2, prior=prior)


@pytest.mark.parametrize('terminal,outcome', [('runtime_error', False), ('completed', False), ('completed', True)])
def test_job_and_outcome_counters_are_distinct(sources, terminal, outcome):
    raw = draft(sources)
    closure = m.close_reservation(raw, terminal=terminal, compile_id='compile-synthetic-4',
        backtest_id='job-synthetic-4', outcome_observed=outcome)
    report = body(closure)
    assert report['observed_jobs_added'].fraction() == report['observed_looks_added'].fraction() == 1
    assert report['outcome_looks_added'].fraction() == int(outcome)
    assert report['accepted_metrics'] is None and report['strategy_accepted'] is False


@pytest.mark.parametrize('terminal', ['compile_failed', 'cancelled_no_job'])
def test_terminal_absence_requires_retained_compile_identity(sources, terminal):
    with pytest.raises(m.Refusal):
        m.close_reservation(draft(sources), terminal=terminal)


@pytest.mark.parametrize('terminal', [None, True, [], {}, 'invented'])
def test_invalid_terminal_is_closed_body_free_refusal(sources, terminal):
    with pytest.raises(m.Refusal, match='bounded prospective OFF continuation refused'):
        m.close_reservation(draft(sources), terminal=terminal)


def test_next_chronological_reservation_cannot_predate_previous_creation(sources):
    raw = draft(sources)
    closure = m.close_reservation(raw, terminal='compile_failed', compile_id='compile-synthetic-4')
    args = arguments(sources, sequence=2, prior=[{'reservation': raw, 'closure': closure}])
    args['created_utc'] = (NOW-timedelta(days=1)).isoformat()
    args['expires_utc'] = (NOW-timedelta(days=1)+timedelta(seconds=60)).isoformat()
    with pytest.raises(m.Refusal):
        m.prepare_reservation(**args)


@pytest.mark.parametrize('field,value', [('git_head','0'*40), ('owner_instruction_sha256','bad'),
    ('operation_id','foreign'), ('operation_id',None), ('operation_id',[]), ('operation_id','TPR-EXT26-OFF-CONT-/bad'),
    ('producer_source_hashes',object()), ('cloud_source_hashes',object()),
    ('created_utc','2026-10-26T00:00:00'), ('expires_utc',(NOW+timedelta(days=1)).isoformat())])
def test_fresh_scope_rejects_invalid_bindings(sources, field, value):
    args = arguments(sources); args[field] = value
    with pytest.raises(m.Refusal):
        m.prepare_reservation(**args)


@pytest.mark.parametrize('field,value', [('native_permission',True), ('durable_claim_published',True),
    ('qc_setup_complete',True), ('accepted_metrics',{}), ('strategy_accepted',True),
    ('attempt',3), ('reserved_look_sequence',33), ('historical_anchor',{})])
def test_draft_cannot_reset_history_or_grant_effects(sources, field, value):
    row = body(draft(sources)); row[field] = value
    with pytest.raises(m.Refusal):
        m.close_reservation(m.e.canonical(row), terminal='compile_failed', compile_id='compile-synthetic-4')


def test_duplicate_json_and_foreign_cloud_config_are_refused(sources):
    raw = draft(sources)
    duplicated = raw.rstrip()[:-1] + b',"native_permission":false}\n'
    with pytest.raises(m.Refusal):
        m.close_reservation(duplicated, terminal='compile_failed', compile_id='compile-synthetic-4')
    args = arguments(sources); args['cloud_source_hashes']['extended_config.py']='d'*64
    with pytest.raises(m.Refusal):
        m.prepare_reservation(**args)


def test_source_render_can_precede_reservation_without_a_hash_cycle(sources):
    files, report = m.prepare_off_source_bundle(attempt=4,
        completion_bundle_raw=sources[m.PREFIX+'extended_source_bundle_completion.json'])
    assert set(files) and all(type(raw) is bytes for raw in files.values())
    assert body(report)['native_permission'] is False
    assert body(report)['attempt'].fraction() == 4


def test_rendered_files_must_match_frozen_cloud_hashes_in_reservation(sources):
    with pytest.raises(m.Refusal):
        m.build_off_sources(draft(sources), sources[m.PREFIX+'extended_source_bundle_completion.json'])


def rendered_draft(sources, attempt=4):
    bundle = sources[m.PREFIX+'extended_source_bundle_completion.json']
    files, receipt = m.prepare_off_source_bundle(attempt=attempt, completion_bundle_raw=bundle)
    args = arguments(sources)
    args['cloud_source_hashes'] = {name:m._sha(raw) for name,raw in files.items()}
    return m.prepare_reservation(**args), files, receipt


def test_exact_source_build_matches_the_frozen_reservation_without_effects(sources):
    raw, files, inert = rendered_draft(sources)
    rebuilt, receipt = m.build_off_sources(raw, sources[m.PREFIX+'extended_source_bundle_completion.json'])
    assert rebuilt == files
    assert body(inert)['reservation_sha256'] is None
    assert body(receipt)['reservation_sha256'] == m._sha(raw)
    assert body(receipt)['attempt'] == N('4')
    assert body(receipt)['native_permission'] is body(receipt)['first_refusal_repaired'] is False
    assert body(receipt)['strategy_economics_changed'] is False


@pytest.mark.parametrize('attempt', [3, 0, -1, True, 4.0, '4', m.MAX_ATTEMPT_ID+1])
def test_attempt_syntax_is_not_a_launch_allowance(sources, attempt):
    with pytest.raises(m.Refusal):
        m.prepare_off_source_bundle(attempt=attempt,
            completion_bundle_raw=sources[m.PREFIX+'extended_source_bundle_completion.json'])


@pytest.mark.parametrize('attempt', [4, 5, 100, m.MAX_ATTEMPT_ID])
def test_source_template_keeps_real_fresh_attempt_identity(sources, attempt):
    files, report = m.prepare_off_source_bundle(attempt=attempt,
        completion_bundle_raw=sources[m.PREFIX+'extended_source_bundle_completion.json'])
    main = ast.parse(files['main.py'])
    literal = next(node.value.value for node in main.body if isinstance(node,ast.Assign)
        and any(isinstance(name,ast.Name) and name.id=='EXPECTED_ATTEMPT' for name in node.targets))
    assert literal == attempt
    assert body(report)['attempt'] == N(str(attempt))
    assert body(report)['native_permission'] is body(report)['qc_setup_complete'] is False
    assert all(len(raw)<=60000 for raw in files.values())


def test_exact_json_integer_attempt_is_normalized_before_source_render(sources):
    files,report=m.prepare_off_source_bundle(attempt=N('4'),
        completion_bundle_raw=sources[m.PREFIX+'extended_source_bundle_completion.json'])
    assert body(report)['attempt']==N('4')
    assert b'EXPECTED_ATTEMPT = 4\n' in files['main.py']


def test_source_adaptation_changes_only_exact_identity_nodes_not_economics(sources):
    bundle = body(sources[m.PREFIX+'extended_source_bundle_completion.json'])
    old = next(row['files'] for row in bundle['candidates'] if row['candidate_id']==m.CANDIDATE)
    files, _ = m.prepare_off_source_bundle(attempt=4,
        completion_bundle_raw=sources[m.PREFIX+'extended_source_bundle_completion.json'])
    assert set(files)==set(old)
    for name,raw in files.items():
        original = old[name].encode()
        if name not in {'main.py','extended_core.py','extended_runtime_successor.py','extended_compressed_store.py'}:
            assert raw==original
            continue
        tree = ast.parse(original)
        if name=='main.py':
            assignment = next(node for node in tree.body if isinstance(node,ast.Assign)
                and any(isinstance(item,ast.Name) and item.id=='EXPECTED_ATTEMPT' for item in node.targets))
            assert assignment.value.value==3
            assignment.value.value=4
        elif name=='extended_core.py':
            m._replace_node(tree,'evidence_prefix','not 1 <= attempt <= 3',
                'attempt != 4 or candidate != '+repr(m.CANDIDATE))
        else:
            m._replace_node(tree,'__init__',"not 1 <= binding['attempt'] <= 3",
                "binding['attempt'] != 4 or binding['candidate_id'] != "+repr(m.CANDIDATE))
        expected = ast.parse(ast.unparse(tree))
        assert ast.dump(ast.parse(raw),include_attributes=False)==ast.dump(expected,include_attributes=False)
    assert files['extended_config.py']==old['extended_config.py'].encode()


@pytest.mark.parametrize('relative', ['extended_native.py','extended_core.py','extended_runtime_successor.py','extended_compressed_store.py'])
def test_drifted_adaptation_input_refuses_even_a_harmless_newline(sources, relative):
    path=m.PREFIX+relative
    with pytest.raises(m.Refusal):
        m._adapt(sources[path]+b'\n',path,4)


def test_old_effect_controllers_and_native_binding_keep_three_attempt_cap(sources):
    with pytest.raises(ValueError):
        base.n._binding(m.CANDIDATE,m.PROJECT,'synthetic-job',4)
    assert m.e.next_attempt.__module__=='research.target_price_revisions_qc.extended_evidence'
    assert m.SOURCE_PINS[m.PREFIX+'extended_operations.py']==m._sha(sources[m.PREFIX+'extended_operations.py'])


def test_adapted_native_binding_rejects_on_arm_and_other_attempts(sources):
    namespace,_=m._normalizer(sources[m.PREFIX+'extended_native.py'],4)
    on=next(candidate for candidate,arm in m.e.CANDIDATES.items() if arm=='tpr_on')
    assert namespace['_binding'](m.CANDIDATE,m.PROJECT,'synthetic-job',4)['attempt']==4
    for candidate,attempt in ((on,4),(m.CANDIDATE,3),(m.CANDIDATE,5)):
        with pytest.raises(ValueError):
            namespace['_binding'](candidate,m.PROJECT,'synthetic-job',attempt)


def test_public_source_factory_imports_no_native_collector_config_or_dispatch(sources):
    tree=ast.parse(sources[m.SOURCE_RELATIVE])
    top_imports=[node for node in tree.body if isinstance(node,(ast.Import,ast.ImportFrom))]
    project=[node for node in top_imports if isinstance(node,ast.ImportFrom) and node.level]
    assert len(project)==1 and [(item.name,item.asname) for item in project[0].names]==[('extended_evidence','e')]
    for node in top_imports:
        names=[alias.name for alias in node.names]
        assert not any(name.split('.')[0] in {'config','assistant','execution','extended_native','extended_operations'} for name in names)


@pytest.fixture
def native_inputs(monkeypatch,sources):
    monkeypatch.setattr(base,'PROJECT',m.PROJECT)
    monkeypatch.setattr(base,'JOB','synthetic-off-job-4')
    monkeypatch.setattr(base,'ATTEMPT',4)
    monkeypatch.setattr(base,'CANDIDATE',m.CANDIDATE)
    raw=draft(sources)
    closure=m.close_reservation(raw,terminal='completed',compile_id='synthetic-compile-4',backtest_id=base.JOB)
    series,envelope=base.nav_fixture()
    pages,collection=base.order_fixture([base.order()])
    return dict(reservation_raw=raw,closure_raw=closure,native_source_raw=sources[m.PREFIX+'extended_native.py'],
        calendar_raw=base.CALENDAR,nav_series_raw=m.e.canonical(series),nav_envelope_raw=m.e.canonical(envelope),
        order_page_envelopes=pages,order_collection_raw=m.e.canonical(collection),
        expected_nav_series_sha256=m._sha(m.e.canonical(series)),expected_nav_envelope_sha256=m._sha(m.e.canonical(envelope)),
        expected_order_collection_sha256=m._sha(m.e.canonical(collection)))


def test_processing_actual_attempt4_preserves_frozen_nav_and_nonacceptance(native_inputs):
    result=m.process_off_native(**native_inputs)
    report=body(result['report'])
    assert report['attempt']==N('4')
    assert report['nav_census']['observations']==N('1449')
    assert report['execution_metrics']['order_count']==N('1')
    assert report['accepted_metrics'] is None and report['strategy_accepted'] is False
    assert report['independent_source_or_compiled_job_authenticated'] is False
    assert report['private_journal_replay_verified'] is False
    assert report['new_jobs']==report['new_observed_looks']==N('0')
    assert body(result['order_census'])['attempt']==N('4')


@pytest.mark.parametrize('mode',['missing_session','extra_session','wrong_clock','wrong_job','wrong_attempt','source_drift','wrong_hash'])
def test_processing_cannot_relax_window_clock_job_or_source(native_inputs,mode):
    args=dict(native_inputs)
    envelope=body(args['nav_envelope_raw'])
    if mode in {'missing_session','extra_session','wrong_clock','wrong_job'}:
        values=envelope['response']['chart']['series']['NAV']['values']
        if mode=='missing_session':values.pop()
        elif mode=='extra_session':values.append(values[-1])
        elif mode=='wrong_clock':values[0][0]=base.epoch(base.SESSIONS[0],16,0)
        else:envelope['response']['backtestId']='foreign-job'
        args['nav_envelope_raw']=m.e.canonical(envelope)
        args['expected_nav_envelope_sha256']=m._sha(args['nav_envelope_raw'])
    elif mode=='wrong_attempt':
        collection=body(args['order_collection_raw']);collection['attempt']=3
        args['order_collection_raw']=m.e.canonical(collection)
        args['expected_order_collection_sha256']=m._sha(args['order_collection_raw'])
    elif mode=='source_drift':args['native_source_raw']+=b'\n'
    else:args['expected_nav_series_sha256']='d'*64
    with pytest.raises(ValueError):m.process_off_native(**args)


def test_missing_native_fees_stay_null_and_no_zero_is_invented(native_inputs):
    args=dict(native_inputs)
    order=base.order()
    order['events']=[base.event(orderFeeAmount=None,orderFeeCurrency=None)]
    pages,collection=base.order_fixture([order])
    args['order_page_envelopes']=pages;args['order_collection_raw']=m.e.canonical(collection)
    args['expected_order_collection_sha256']=m._sha(args['order_collection_raw'])
    result=m.process_off_native(**args)
    row=body(result['order_pages'][0])[0]
    assert row['reported_fee'] is None
    report=body(result['report'])
    assert report['execution_metrics']['complete_reported_fees_usd'] is None
    assert report['accepted_metrics'] is None


def test_attempt4_native_journal_and_compressed_export_are_composed_synthetically(sources,monkeypatch):
    from tests.target_price_revisions_qc import test_qc_extended_runtime as fixture
    fixture.runtime.__wrapped__(monkeypatch)
    files,_=m.prepare_off_source_bundle(attempt=4,
        completion_bundle_raw=sources[m.PREFIX+'extended_source_bundle_completion.json'])
    modules={}
    for name in ('extended_core','extended_runtime_successor','extended_compressed_store'):
        module=ModuleType(name)
        monkeypatch.setitem(sys.modules,name,module)
        exec(compile(files[name+'.py'],'<synthetic-off-attempt4-'+name+'>','exec'),module.__dict__)
        modules[name]=module
    core=modules['extended_core']
    runtime=modules['extended_runtime_successor']
    compressed=modules['extended_compressed_store']
    state=SimpleNamespace(project=m.PROJECT,job='',locked=False)
    getter=lambda:(state.project,state.job,state.locked)
    binding={'candidate_id':m.CANDIDATE,'config_sha256':m.CONFIG_SHA256,'freeze_sha256':m.e.FREEZE_SHA256,
        'input_hashes':dict(m.INPUTS),'attempt':4}
    journal=runtime.DeferredPrivateEvidence(binding,getter)
    journal.append('SUBSCRIPTION',{'synthetic':True})
    state.job,state.locked='synthetic-off-native-job-4',True
    prefix=journal.require_binding()
    assert '/attempt-4/' in prefix and prefix.endswith('/37650980/synthetic-off-native-job-4/')
    class Store:
        def __init__(self):self.values={};self.calls=[]
        def contains_key(self,key):self.calls.append(('contains',key));return key in self.values
        def save_bytes(self,key,raw):
            assert key not in self.values
            self.calls.append(('save',key));self.values[key]=bytes(raw);return True
        def read_bytes(self,key):self.calls.append(('read',key));return self.values[key]
    store=Store()
    pointer=journal.export(compressed.CompressedAuditStore(store,journal.binding))
    assert journal.closed and pointer['records']==1
    assert len(store.values)==3 and all(key.startswith(prefix) for key in store.values)
    assert all('/attempt-3/' not in key for _,key in store.calls)
    assert journal.binding['attempt']==4
    index_raw=gzip.decompress(store.values[prefix+'index.json.gz'])
    assert m._sha(index_raw)==pointer['index_sha256']
    index=body(index_raw)
    assert index['attempt']==N('4') and index['canonical_admission'] is False
    storage=body(gzip.decompress(store.values[prefix+'storage.json.gz']))
    assert storage['binding']['attempt']==N('4')
    on=core.CANDIDATES['tpr_on']
    with pytest.raises(ValueError):core.evidence_prefix(on,m.CONFIG_SHA256,4,m.PROJECT,state.job)
    with pytest.raises(ValueError):compressed.CompressedAuditStore(store,{**journal.binding,'attempt':3})


def test_ledger_rejects_duplicate_operation_and_reused_job(sources):
    first=draft(sources)
    closed=m.close_reservation(first,terminal='completed',compile_id='compile-synthetic-4',backtest_id='job-synthetic')
    prior=[{'reservation':first,'closure':closed}]
    args=arguments(sources,sequence=2,prior=prior)
    args['operation_id']=body(first)['operation_id']
    with pytest.raises(m.Refusal):m.prepare_reservation(**args)
    second=draft(sources,sequence=2,prior=prior)
    second_closed=m.close_reservation(second,terminal='runtime_error',compile_id='compile-synthetic-5',backtest_id='job-synthetic')
    with pytest.raises(m.Refusal):m.continuation_census(prior+[{'reservation':second,'closure':second_closed}])


@pytest.mark.parametrize('field,value',[('reservation_sha256','d'*64),('attempt',99),('observed_jobs_added',1),
    ('outcome_looks_added',1),('terminal_resolved',False),('accepted_metrics',{}),('strategy_accepted',True)])
def test_closure_tampering_cannot_reset_or_invent_observations(sources,field,value):
    raw=draft(sources)
    closure=body(m.close_reservation(raw,terminal='compile_failed',compile_id='compile-synthetic-4'))
    closure[field]=value
    with pytest.raises(m.Refusal):m.continuation_census([{'reservation':raw,'closure':m.e.canonical(closure)}])


@pytest.mark.parametrize('before,after,probe',[
    ('observed = int(backtest_id is not None)','observed = 1','compile_failure'),
    ('None if terminal == "unresolved" and backtest_id is None else observed','observed','unknown_jobs'),
    ('if value["extended_config.py"] != CLOUD_CONFIG_SHA256:','if False:','frozen_config'),
])
def test_in_memory_semantic_mutants_are_killed_without_source_edits(sources,monkeypatch,before,after,probe):
    raw=sources[m.SOURCE_RELATIVE].decode()
    assert raw.count(before)==1
    clone=ModuleType(m.__name__+'_synthetic_mutant')
    clone.__package__=m.__package__
    exec(compile(raw.replace(before,after),'<synthetic-off-continuation-mutant>','exec'),clone.__dict__)
    monkeypatch.setitem(globals(),'m',clone)
    with pytest.raises((AssertionError,pytest.fail.Exception)):
        if probe=='compile_failure':test_compile_failure_spends_attempt_but_not_job_or_look(sources)
        elif probe=='unknown_jobs':test_unresolved_effect_never_reopens_an_automatic_next_attempt(sources,False)
        else:test_duplicate_json_and_foreign_cloud_config_are_refused(sources)
