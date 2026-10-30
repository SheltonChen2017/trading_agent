"""Synthetic AS metadata recovery only; no production artifact or operation."""
import copy
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import read_arv2_r298_common_price_manifest_metadata as m


def fails(code,call):
    with pytest.raises(m.Refused) as caught: call()
    assert m.finite(caught.value) == code


def synthetic_manifest():
    rows=[];left=5541040
    for month in m.ar._public_months():
        count=5644*len(month['session_indexes']); valid=min(count,left);left-=valid
        rows.append({**month,'row_count':count,'valid_count':valid,'absent_count':count-valid,
            'byte_count':100+month['month_ordinal'],'sha256':m.sha(('synthetic-'+month['month']).encode())})
    assert left==0
    return {'schema':m.ar.fmt.SCHEMA+'-manifest','catalog_pin':m.pin(b'synthetic catalog'),
        'AP_fact_sha256':m.ar.fmt.AP_FACT_SHA256,'AP_authentication_sha256':m.ar.fmt.AP_AUTH_SHA256,
        'binding_stream_sha256':m.ar.fmt.BINDING_SHA256,'full_axis_sha256':m.ar.fmt.FULL_AXIS_SHA256,
        'assignment_count':6159,'vendor_slot_count':5644,'session_count':1452,'months':rows,
        'row_count':8195088,'valid_count':5541040,'absent_count':2654048,
        'total_shard_bytes':sum(row['byte_count'] for row in rows),**m.ar.fmt.FALSE_FLAGS}


@pytest.fixture
def reconstruction(monkeypatch):
    context=m.retained_context();manifest=synthetic_manifest();raw=m.canonical(manifest)
    context['codec_summary']={**context['codec_summary'],'catalog_pin':manifest['catalog_pin'],
        'manifest_pin':m.pin(raw),'total_shard_bytes':manifest['total_shard_bytes']}
    context['output_metrics']['final_byte_count']=manifest['total_shard_bytes']
    result={'schema':m.ar.SCHEMA,'input_binding':m.ar.source_context()['source_summary']['input_binding'],
        'source_guard_receipt':context['source_guard_receipt'],'codec_summary':context['codec_summary'],
        'manifest_descriptor':m.ar._manifest_descriptor(manifest),'output_receipt':{
            'schema':m.ar.SCHEMA+'-output-receipt','catalog_pin':manifest['catalog_pin'],'manifest_pin':m.pin(raw),
            'month_pins':[{'byte_count':row['byte_count'],'sha256':row['sha256']} for row in manifest['months']],
            **context['output_metrics']},'source_guards_normal_return':True,'genuine_input_unchanged':True,
        'AP_fact_sha256':m.ar.fmt.AP_FACT_SHA256,'AP_source_sha256':m.ar.fmt.AP_SOURCE_SHA256,
        'AP_authentication_sha256':m.ar.fmt.AP_AUTH_SHA256,'post_checks_complete':True,**m.ar.FALSE_FLAGS}
    report=m.canonical({**context['binding'],'result':result});context['report']=m.pin(report)
    expected=m.canonical({'binding':context['binding'],'outcome':{'result':result,'report':context['report']}})+b'\n'
    for role in ('producer','validator'):
        context[role].update(stdout_bytes=len(expected),stdout_sha256=m.sha(expected))
    monkeypatch.setattr(m,'retained_context',lambda:copy.deepcopy(context))
    return context,raw,expected


def test_public_pins_and_retained_actual_proofs_are_exact_closed_metadata():
    assert len(m.pins())==200  # Generic guard is already in the frozen AR closure.
    assert all(m.sha((m.ROOT/name).read_bytes())==expected for name,expected in m.pins().items())
    fact=m.retained_context()
    assert fact['producer']['actual_exit']==fact['validator']['actual_exit']==0
    assert fact['report']['byte_count']==28524
    assert fact['complete_original_payload_retained'] is False
    assert m.profile_record()['original_report_and_stdout_pins_both_required'] is True
    assert m.data_plan()=={'ar_manifest':{
        'relative_path':'artifacts/analyst_revisions_v2/newrule_common_price_sidecar/R326-20261027-AR/manifest-private.json',
        'byte_count':22373,'sha256':'cf9a27d0c6ccd8ad65b676c6335de35ac6738579e49784cb532d790cf83e7189'}}


@pytest.mark.parametrize('field',('producer_exit','validator_exit','producer_bool','validator_bound','stderr',
    'stdout','report','receipt','grant','extra'))
def test_retained_fact_mutation_is_not_silent_pin_refresh(monkeypatch,field):
    fact=m.anchor.observed_fact()
    if field=='producer_exit':fact['producer']['actual_exit']=2
    elif field=='validator_exit':fact['validator']['actual_exit']=71
    elif field=='producer_bool':fact['producer']['actual_exit']=False
    elif field=='validator_bound':fact['validator']['bound']='timeout'
    elif field=='stderr':fact['producer']['stderr_bytes']=1
    elif field=='stdout':fact['producer']['stdout_sha256']='a'*64
    elif field=='report':fact['report']['sha256']='b'*64
    elif field=='receipt':fact['source_guard_receipt']['source_endpoint_sha256']='c'*64
    elif field=='grant':fact['QC_transfer_granted']=True
    else:fact['extra']=True
    monkeypatch.setattr(m.anchor,'observed_fact',lambda:fact)
    fails('source_binding',m.retained_context)


def test_exact_synthetic_reconstruction_reuses_original_pure_validation(reconstruction):
    context,raw,expected=reconstruction
    assert m.reconstruct(raw)==expected
    out=m.ar.validate_output(expected,0,NS(**context['binding']))
    assert out['outcome']['report']==context['report']
    assert b'"assignments"' not in expected and b'"ticker"' not in expected
    assert b'"security_id"' not in expected and b'"session_indexes"' not in expected


@pytest.mark.parametrize('kind',('report_hash','report_size','producer_hash','producer_size','validator_hash',
    'metric_bytes','metric_stream','descriptor_closure'))
def test_reconstruction_refuses_any_missing_external_pin_or_changed_metrics(reconstruction,monkeypatch,kind):
    context,raw,_=reconstruction
    if kind=='report_hash':context['report']['sha256']='0'*64
    elif kind=='report_size':context['report']['byte_count']+=1
    elif kind=='producer_hash':context['producer']['stdout_sha256']='1'*64
    elif kind=='producer_size':context['producer']['stdout_bytes']+=1
    elif kind=='validator_hash':context['validator']['stdout_sha256']='2'*64
    elif kind=='metric_bytes':context['output_metrics']['provisional_byte_count']+=1
    elif kind=='metric_stream':context['output_metrics']['provisional_pin_stream_sha256']='3'*64
    else:context['output_metrics']['final_original_descriptors_held']=False
    monkeypatch.setattr(m,'retained_context',lambda:context)
    with pytest.raises((m.Refused,m.ar.Refused)):m.reconstruct(raw)


@pytest.mark.parametrize('change',('trailing','noncanonical','duplicate','changed','extra','wrong_type'))
def test_manifest_byte_pin_precedes_JSON_and_strict_manifest_shape(reconstruction,monkeypatch,change):
    context,raw,_=reconstruction
    if change=='trailing':bad=raw+b'\n'
    elif change=='noncanonical':bad=raw.replace(b',',b', ',1)
    elif change=='duplicate':bad=b'{"x":1,"x":2}'
    elif change=='wrong_type':bad=b'[]'
    else:
        value=m.ar.fmt.loads(raw,m.ar.fmt.MAX_MANIFEST_BYTES)
        if change=='changed':value['months'][0]['sha256']='4'*64
        else:value['ticker']='synthetic-private'
        bad=m.canonical(value)
    # Without a new byte binding, parsing must never run at all.
    monkeypatch.setattr(m.ar.fmt,'loads',lambda *_:pytest.fail('parse before bytepin'))
    fails('manifest',lambda:m.reconstruct(bad))


def test_duplicate_or_unclosed_JSON_refuses_even_when_supplied_fixture_pin_matches(reconstruction,monkeypatch):
    context,_,_=reconstruction;raw=b'{"x":1,"x":2}'
    context['codec_summary']['manifest_pin']=m.pin(raw)
    monkeypatch.setattr(m,'retained_context',lambda:context)
    fails('manifest',lambda:m.reconstruct(raw))


def test_native_policy_only_one_AR_DATA_leaf_and_exact_AS_parent():
    policy=m.native_profile()
    assert '(deny network*)' in policy and '(deny process-exec (literal "/usr/bin/security"))' in policy
    assert 'remote tcp' not in policy and '/Library/Keychains' in policy
    assert f'(require-not (literal "{m.CONTROL.parent}"))' in policy
    assert f'(require-not (subpath "{m.CONTROL.parent}"))' not in policy
    assert f'(require-not (subpath "{m.CONTROL}"))' in policy
    assert m.data_plan()['ar_manifest']['relative_path'] in policy
    for forbidden in ('/catalog-private.json','/report.json','/claim.json','/month-000.jsonl',
            '/R326-20261027-AP/','/R326-20261027-AQ/',str(m.ar.worker.previous.PACKAGE)):
        assert forbidden not in policy


@pytest.fixture
def own_store(monkeypatch,tmp_path):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'parent'/'AS')
    monkeypatch.setattr(m,'_security',lambda fd:('synthetic',))
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:index+1])).st_dev,os.stat(Path(*path.parts[:index+1])).st_ino)
            for index in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk))
    return m.CONTROL


def test_own_claim_is_exclusive_original_descriptors_held_no_third_file(own_store):
    with m.Store() as store:
        store.write('claim.json',b'{"claim":true}')
        store.write('result-metadata.json',b'{"public":true}')
        store.verify()
        assert len(store.files)==2
        fails('output_bound',lambda:store.write('report.json',b'{}'))
    fails('claim_spent',m.Store)


def test_own_output_named_replacement_refused(own_store):
    with m.Store() as store:
        store.write('claim.json',b'{}')
        path=own_store/'claim.json';path.rename(own_store/'retained.json')
        path.write_bytes(b'{}');path.chmod(0o600)
        fails('output_changed',store.verify)


@pytest.mark.parametrize('drift',(False,True))
def test_real_generic_one_leaf_guard_rejects_drift_before_return_without_other_data(monkeypatch,tmp_path,drift):
    root=tmp_path/'synthetic-root';root.mkdir(mode=0o755);root.chmod(0o755)
    path=root/'artifacts'/'analyst_revisions_v2'/'synthetic'/'manifest-private.json'
    path.parent.mkdir(parents=True,mode=0o700)
    for parent in (root/'artifacts',root/'artifacts'/'analyst_revisions_v2',path.parent):parent.chmod(0o700)
    raw=b'{"synthetic":"manifest-only"}';path.write_bytes(raw);path.chmod(0o600)
    plan={'ar_manifest':{'relative_path':path.relative_to(root).as_posix(),**m.pin(raw)}}
    monkeypatch.chdir(root);monkeypatch.setattr(m.guard_module,'ROOT',root)
    guard=m.guard_module.FixedDataGuard(plan,deadline=time.monotonic()+20)
    def read_and_return():
        with guard:
            assert guard.read_all_once()=={'ar_manifest':raw}
            assert guard.receipt()['fixed_bytes_authenticated'] is True
            if drift:path.write_bytes(b'{"synthetic":"manifest-drift"}')
    if drift:
        with pytest.raises(m.guard_module.Refused):read_and_return()
    else:read_and_return()
    assert guard.active is False


@pytest.mark.parametrize('boundary',('ok','guard_enter','guard_read','guard_return','postflight','store_return'))
def test_claim_then_one_manifest_normal_return_then_postflight_before_emission(monkeypatch,boundary):
    events=[];args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    class Store:
        def __enter__(self):events.append('store-enter');return self
        def __exit__(self,kind,*_):
            events.append('store-return')
            if boundary=='store_return':raise m.Refused('output_changed')
        def write(self,name,raw):events.append(name)
        def verify(self):events.append('store-check')
    class Guard:
        def __init__(self,plan,*,deadline):assert set(plan)=={'ar_manifest'}
        def __enter__(self):
            events.append('guard-enter')
            if boundary=='guard_enter':raise m.guard_module.Refused('path_open')
            return self
        def read_all_once(self):
            events.append('manifest-read')
            if boundary=='guard_read':raise m.guard_module.Refused('byte_pin')
            return {'ar_manifest':b'synthetic-manifest'}
        def verify(self):events.append('guard-check')
        def receipt(self):return {'synthetic':'receipt'}
        def __exit__(self,kind,*_):
            events.append('guard-normal' if kind is None else 'guard-exception')
            if boundary=='guard_return' and kind is None:raise m.guard_module.Refused('named_changed')
    monkeypatch.setattr(m,'Store',Store);monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard)
    monkeypatch.setattr(m.guard_module,'validate_receipt',lambda value,plan:value)
    def reconstruct(raw):events.append('reconstruct');return b'public-original\n'
    monkeypatch.setattr(m,'reconstruct',reconstruct)
    def preflight(*_):
        events.append('postflight')
        if boundary=='postflight':raise m.Refused('source_pin')
    monkeypatch.setattr(m,'preflight',preflight)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    if boundary=='ok':
        assert m.run(args,time.monotonic()+20)==b'public-original\n'
        assert events.index('claim.json')<events.index('guard-enter')<events.index('manifest-read')
        assert events.index('guard-normal')<events.index('postflight')<events.index('result-metadata.json')<events.index('store-return')
    else:
        with pytest.raises((m.Refused,m.guard_module.Refused)):m.run(args,time.monotonic()+20)
        if boundary!='store_return':assert 'result-metadata.json' not in events
    assert events.count('manifest-read')<=1


def test_main_never_outputs_recovered_bytes_when_late_run_raises(monkeypatch,capsys):
    monkeypatch.setattr(m,'preflight',lambda *_:None)
    monkeypatch.setattr(m.environment,'_bootstrap_cli_logging',lambda:None)
    monkeypatch.setattr(m,'run',lambda *_:(_ for _ in ()).throw(m.Refused('output_changed')))
    assert m.main(['--expected-head','a'*40,'--caller-sha256','b'*64,'--profile-sha256','c'*64])==2
    output=capsys.readouterr().out.encode();value=m.ar.parse(output[:-1])
    assert value['failure_code']=='output_changed' and value['allocation_unknown'] is True
    assert 'outcome' not in value and value['QC_transfer_granted'] is False


def test_no_old_run_or_control_reader_path_in_reconstruction_source():
    import ast
    tree=ast.parse(m.SOURCE.read_text())
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)]
    assert not any(isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name)
        and node.func.value.id=='ar' and node.func.attr in ('run','construct','main','Store') for node in calls)
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='run')
    code=ast.unparse(function)
    assert code.count('guard.read_all_once()')==1 and 'FixedDataGuard' in code
    assert 'PriceCorpusGuard' not in code and '_load_plain' not in code and '_catalog(' not in code


@pytest.mark.parametrize('value',(0,-1,float('nan'),float('inf'),True,'30'))
def test_deadline_is_finite_strict_and_bounded(value):
    fails('deadline',lambda:m.remaining(value))


def test_source_preflight_is_bound_to_exact_host_HEAD_clean_git_committed_source():
    import inspect
    code=inspect.getsource(m.preflight)
    for required in ('_under_test()',"sys.platform == 'darwin'",'(3,13)','Path(sys.executable) == PYTHON',
        "['status','--porcelain']","['rev-parse','HEAD']","['cat-file','blob'",'args.profile_sha256','_credential_free'):
        assert required in code
