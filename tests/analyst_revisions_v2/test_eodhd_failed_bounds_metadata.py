"""Synthetic metadata-only reconciliation of unaccepted AY; no old operation."""
import copy
import inspect
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import read_arv2_r298_eodhd_failed_bounds_metadata as m


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def original_metadata():
    ay=m.ay;whole={'byte_count':ay.DATA_BYTES,'sha256':'d'*64}
    names=lambda known:{'known_names':sorted(known),'unknown_name_count':0,'unknown_names_sha256':m.sha(b'[]')}
    listed={'schema_valid':True,'row_count':1,'ordered_records_sha256':'c'*64,'failure_code':None}
    shape={'schema':ay.SCHEMA+'-shape','external_frame_body_pins':list(ay.FRAME_PINS),'AY_observed_whole_file_pin':dict(whole),
        'mapping_top_level_type':'object','mapping_top_fields':names(ay.KNOWN_TOP),'meta_type':'object',
        'meta_fields':names(ay.KNOWN_META),'numeric_fields':{name:ay._numeric_field({'total':200001,'limit':1000,'offset':0},name)
            for name in sorted(ay.KNOWN_META)},'data_type':'array','data_row_count':1000,'all_data_records_objects':True,
        'links_type':'object','next':{'present':True,'type':'string','value_sha256':'b'*64},
        'symbol_lists':{'active':dict(listed),'delisted':dict(listed)},**ay.FALSE_FLAGS}
    receipt={'schema':ay.SCHEMA+'-framed-source-receipt','profile_sha256':m.sha(m.canonical(ay.frame_profile())),
        'relative_path':ay.DATA_RELATIVE,'byte_extent':ay.DATA_BYTES,'external_body_pins':list(ay.FRAME_PINS),
        'current_metadata_sha256':'a'*64,'current_security_sha256':'b'*64,'AY_observed_whole_file_pin':dict(whole),
        'all_extent_bytes_authenticated_by_external_frames':True,'new_AY_whole_pin_not_recovered_AW_pin':True,
        'requires_normal_return_before_use':True,'historical_continuity_proven':False,'continuous_integrity_proven':False}
    return {'binding':dict(m.AY_BINDING),'result':{'schema':ay.SCHEMA+'-result','shape':shape,
        'source_guard_receipt':receipt,'source_guard_normal_return':True,
        'AW_failure_binding_sha256':m.sha(m.canonical(ay.observed_failure())),**ay.FALSE_FLAGS}}


@pytest.fixture
def supplied(monkeypatch):
    def make(value=None):
        raw=m.canonical(original_metadata() if value is None else value)+b'\n'
        plan={'ay_reported_metadata':{'relative_path':m.DATA_PLAN['ay_reported_metadata']['relative_path'],**m.pin(raw)}}
        monkeypatch.setattr(m,'DATA_PLAN',plan);return raw
    return make


def test_fixed_failure_actual_scope_no_source_success_or_new_source_pin():
    assert m.CONTROL.name=='R326-20261027-AZ'
    assert m.DATA_PLAN['ay_reported_metadata']['byte_count']==4526
    assert m.DATA_PLAN['ay_reported_metadata']['sha256']=='d9dfeaab7818d8e9aac495f525e27a3fb40a640f23bbb7f79aef3b6014bccdf8'
    fact=m.observed_failure()
    assert fact['AY_actual_exit']==-9 and fact['AY_bound']=='outer_capture'
    assert fact['AY_native_validator_invoked'] is False and fact['AY_actual_success_accepted'] is False
    assert len(m.pins())==207 and all(m.sha((m.ROOT/name).read_bytes())==digest for name,digest in m.pins().items())
    measurement=m.profile_record()['external_actual_measurement']
    assert measurement['source_sha256']==m.CAPTURE_SOURCE_SHA256
    assert measurement['producer_stdout_limit']==65536 and measurement['producer_stderr_limit']==8192
    assert measurement['technical_profile']['all_arguments_bounds_and_environment_copied_before_Popen'] is True
    assert measurement['progress_callback'] is False
    code=inspect.getsource(m)
    assert 'ay.validate_output(' not in code and 'ay.run(' not in code and 'load_key(' not in code
    assert m.DATA_PLAN['ay_reported_metadata']['relative_path'].endswith('/R326-20261027-AY/result-metadata.json')


def test_metadata_shape_format_never_invents_original_actual_zero(supplied,monkeypatch):
    raw=supplied()
    monkeypatch.setattr(m.ay,'validate_output',lambda *_:pytest.fail('fabricated original actual exit'))
    claims=m.claimed_metadata(raw);m.validate_claims(claims)
    assert claims['metadata_claim_format_validated'] is True and claims['original_AY_actual_exit']==-9
    assert claims['original_AY_native_validator_invoked'] is False
    assert claims['candidate_pin_status']=='reported_UNADMITTED'
    assert claims['reported_bounds_shape']['numeric_fields']['total']['public_integer']==200001
    assert claims['candidate_whole_file_pin_REPORTED_UNADMITTED']['sha256']=='d'*64
    assert all(claims[name] is False for name in m.FALSE_FLAGS)


def test_exact_external_metadata_byte_pin_is_checked_before_any_JSON(supplied,monkeypatch):
    raw=supplied();seen=[];original=m.ay.aw.parse
    def observed(value):
        seen.append(value);return original(value)
    monkeypatch.setattr(m.ay.aw,'parse',observed)
    fails('shape',lambda:m.claimed_metadata(raw+b'x'))
    bad=bytearray(raw);bad[5]^=1;fails('shape',lambda:m.claimed_metadata(bytes(bad)))
    assert seen==[]


@pytest.mark.parametrize('change',('head','source','profile','schema','unknown','normal','old_failure_hash',
    'false_flag','candidate_join','old_shape','old_receipt'))
def test_reported_metadata_binding_schema_and_candidate_join_remain_strict(supplied,change):
    value=original_metadata();result=value['result']
    if change=='head':value['binding']['expected_head']='f'*40
    elif change=='source':value['binding']['caller_sha256']='f'*64
    elif change=='profile':value['binding']['profile_sha256']='f'*64
    elif change=='schema':result['schema']='different'
    elif change=='unknown':result['extra']='cannot leak'
    elif change=='normal':result['source_guard_normal_return']=False
    elif change=='old_failure_hash':result['AW_failure_binding_sha256']='f'*64
    elif change=='false_flag':result['identity_accepted']=True
    elif change=='candidate_join':result['source_guard_receipt']['AY_observed_whole_file_pin']['sha256']='f'*64
    elif change=='old_shape':result['shape']['numeric_fields']['total']['wire_type']='string'
    else:result['source_guard_receipt']['requires_normal_return_before_use']=False
    raw=supplied(value);fails('shape',lambda:m.claimed_metadata(raw))


def test_duplicate_keys_and_literal_backslash_separator_refuse(supplied):
    value=original_metadata();raw=m.canonical(value)+b'\n'
    raw=raw.replace(b'"binding":',b'"binding":{},"binding":',1)
    m.DATA_PLAN['ay_reported_metadata'].update(m.pin(raw))
    fails('shape',lambda:m.claimed_metadata(raw))
    raw=supplied().replace(b'\n',b'\\n');m.DATA_PLAN['ay_reported_metadata'].update(m.pin(raw))
    fails('shape',lambda:m.claimed_metadata(raw))


@pytest.mark.parametrize('change',('old_exit','validator','admit','status','candidate','shape','receipt'))
def test_claim_output_cannot_promote_or_relabel_reported_source(supplied,change):
    claims=m.claimed_metadata(supplied())
    if change=='old_exit':claims['original_AY_actual_exit']=0
    elif change=='validator':claims['original_AY_native_validator_invoked']=True
    elif change=='admit':claims['reported_whole_pin_admitted']=True
    elif change=='status':claims['candidate_pin_status']='accepted'
    elif change=='candidate':claims['candidate_whole_file_pin_REPORTED_UNADMITTED']={'byte_count':1,'sha256':'f'*64}
    elif change=='shape':claims['reported_bounds_shape']['identity_accepted']=True
    else:claims['reported_framed_source_receipt']['continuous_integrity_proven']=True
    fails('output',lambda:m.validate_claims(claims))


def test_native_scope_all_network_denied_and_only_fixed_metadata_leaf():
    policy=m.native_profile()
    assert '(deny network*)' in policy and '/usr/bin/security' in policy and '/Library/Keychains' in policy
    assert m.DATA_PLAN['ay_reported_metadata']['relative_path'] in policy
    assert '/R326-20261027-AW/catalog-bodies.bin' not in policy
    assert '/R326-20261027-AY/claim.json' not in policy
    assert 'requests.jsonl' not in policy and 'catalog-index.json' not in policy


@pytest.fixture
def store_scope(monkeypatch,tmp_path,supplied):
    raw=supplied();root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    directory=root/'artifacts';directory.mkdir(mode=0o700)
    directory=directory/'analyst_revisions_v2';directory.mkdir(mode=0o700)
    directory=directory/'data';directory.mkdir(mode=0o700)
    source=directory/'metadata.json';source.write_bytes(raw);source.chmod(0o600)
    monkeypatch.setattr(m,'DATA_PLAN',{'ay_reported_metadata':{'relative_path':'artifacts/analyst_revisions_v2/data/metadata.json',**m.pin(raw)}})
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m.guard_module,'ROOT',root)
    monkeypatch.setattr(m,'CONTROL',root/'output'/'AZ');monkeypatch.chdir(root)
    monkeypatch.setattr(m,'preflight',lambda *_:None);monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk))
    return source,raw


def test_real_fixed_metadata_guard_claim_before_read_and_return_before_publish(store_scope,monkeypatch):
    source,raw=store_scope;seen=[]
    old=m.claimed_metadata
    def checked(value):
        assert (m.CONTROL/'claim.json').is_file();assert value==raw;seen.append('metadata-read');return old(value)
    monkeypatch.setattr(m,'claimed_metadata',checked)
    old_exit=m.guard_module.FixedDataGuard.__exit__
    def finish(guard,*args):
        result=old_exit(guard,*args);seen.append('guard-return');return result
    monkeypatch.setattr(m.guard_module.FixedDataGuard,'__exit__',finish)
    old_write=m.Store.write
    def write(store,name,value):
        if name=='result-metadata.json':assert seen==['metadata-read','guard-return']
        return old_write(store,name,value)
    monkeypatch.setattr(m.Store,'write',write)
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    output=m.run(args,time.monotonic()+20);m.validate_output(output,0,args)
    fails('output',lambda:m.validate_output(output,2,args))
    result=json.loads(output)['result']
    assert result['metadata_leaf_guard_normal_return'] is True
    assert result['reported_UNADMITTED_claims']['original_AY_actual_exit']==-9
    assert result['AY_original_guard_return_authenticated'] is False


def test_fixed_metadata_hash_refusal_never_calls_claim_parser(store_scope,monkeypatch):
    path,raw=store_scope;changed=bytearray(raw);changed[10]^=1;path.write_bytes(changed)
    monkeypatch.setattr(m,'claimed_metadata',lambda *_:pytest.fail('unauthenticated metadata parsed'))
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    with pytest.raises(m.guard_module.Refused):m.run(args,time.monotonic()+20)
    assert not (m.CONTROL/'result-metadata.json').exists()


def test_failed_new_reader_output_accepts_only_actual_two():
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    raw=m.canonical({'binding':m.binding(args),'failure_code':'guard_byte_pin','allocation_unknown':True,**m.FALSE_FLAGS})+b'\n'
    m.validate_output(raw,2,args);fails('output',lambda:m.validate_output(raw,0,args))
