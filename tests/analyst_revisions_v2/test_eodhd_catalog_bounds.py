"""Synthetic fixed-frame bounds reader; never real catalog DATA or contact."""
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import stat
import struct
import time
from types import SimpleNamespace as NS

import pytest

from scripts import read_arv2_r298_eodhd_catalog_bounds as m


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def rows():
    return [{'Code':'SYNTH','Name':'Synthetic € display','Country':'États-Unis','Exchange':'NYSE',
        'Currency':'USD','Type':'Unknown vendor class','Isin':None}]


def source_bodies(total=200001):
    return (m.canonical(rows()),m.canonical([]),m.canonical({'meta':{'total':total,'limit':1000,'offset':0},
        'data':[{'symbol':'PRIVATE-SYNTH.US','isin':None}],'links':{'next':'https://invalid.example/private-next'}}))


@pytest.fixture
def scope(monkeypatch,tmp_path):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    source=root/'data';source.mkdir(mode=0o700);path=source/'catalog-bodies.bin'
    bodies=source_bodies();raw=b''.join(struct.pack('>Q',len(body))+body for body in bodies)
    path.write_bytes(raw);path.chmod(0o600)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'DATA_RELATIVE','data/catalog-bodies.bin')
    monkeypatch.setattr(m,'CONTROL',root/'output'/'AY')
    monkeypatch.setattr(m,'FRAME_PINS',tuple(m.pin(body) for body in bodies));monkeypatch.setattr(m,'DATA_BYTES',len(raw))
    monkeypatch.chdir(root)
    return path,bodies,raw


def test_fixed_original_failure_scope_and_pins_are_inert_and_no_fake_AW_success():
    assert m.CONTROL.name=='R326-20261027-AY' and m.DATA_BYTES==16140080
    assert sum(item['byte_count']+8 for item in m.FRAME_PINS)==m.DATA_BYTES
    assert m.observed_failure()['parent_actual_exit']==2 and m.observed_failure()['native_validator_actual_exit']==0
    assert m.observed_failure()['provider_failure_code']=='mapping_bound'
    assert len(m.pins())==205 and all(m.sha((m.ROOT/name).read_bytes())==digest for name,digest in m.pins().items())
    code=inspect.getsource(m)
    assert 'aw.analyse(' not in code and 'aw.run(' not in code and 'load_key(' not in code
    assert all(name not in m.DATA_RELATIVE for name in ('claim','journal','index','report'))
    assert m.frame_profile()['new_whole_file_digest_observed_after_all_frames_authenticated'] is True


def test_original_FD_all_frame_auth_whole_SHA_observation_and_normal_return(scope):
    path,bodies,raw=scope
    with m.FramedSourceGuard(deadline=time.monotonic()+20) as guard:
        assert guard.whole_pin is None
        actual=guard.read_frames_once();assert actual==bodies
        observed=guard.whole_pin;assert observed==m.pin(raw)
        observed['sha256']='f'*64;assert guard.whole_pin==m.pin(raw)
        receipt=guard.receipt();m.validate_receipt(receipt)
        shape=m.shape(actual,guard.whole_pin);m.validate_shape(shape)
    assert not guard.active and not guard.objects and shape['AY_observed_whole_file_pin']==m.pin(raw)
    assert receipt['new_AY_whole_pin_not_recovered_AW_pin'] is True


@pytest.mark.parametrize('change',('header','first_body','last_body','trailing','short','mode','symlink','hardlink'))
def test_every_frame_and_exact_extent_is_authenticated_before_any_JSON(scope,monkeypatch,change):
    path,bodies,raw=scope
    if change=='header':path.write_bytes(struct.pack('>Q',len(bodies[0])+1)+raw[8:])
    elif change=='first_body':
        changed=bytearray(raw);changed[10]^=1;path.write_bytes(changed)
    elif change=='last_body':
        changed=bytearray(raw);changed[-2]^=1;path.write_bytes(changed)
    elif change=='trailing':path.write_bytes(raw+b'x')
    elif change=='short':path.write_bytes(raw[:-1])
    elif change=='mode':path.chmod(0o644)
    elif change=='symlink':
        other=path.with_name('other');path.rename(other);path.symlink_to(other)
    else:os.link(path,path.with_name('other'))
    monkeypatch.setattr(m,'shape',lambda *_:pytest.fail('parsed source before all external frame pins'))
    with pytest.raises((m.Refused,m.guard_module.Refused)):
        with m.FramedSourceGuard(deadline=time.monotonic()+20) as guard:
            data=guard.read_frames_once();m.shape(data,guard.whole_pin)


def test_read_is_once_and_same_guard_cannot_reenter(scope):
    with m.FramedSourceGuard(deadline=time.monotonic()+20) as guard:
        guard.read_frames_once()
        with pytest.raises(m.guard_module.Refused):guard.read_frames_once()
    with pytest.raises(m.guard_module.Refused):guard.__enter__()


def test_plan_mutation_is_not_a_pin_refresh(scope):
    with pytest.raises(m.Refused):
        with m.FramedSourceGuard(deadline=time.monotonic()+20) as guard:
            guard.plan['catalog_frames']['frames'][0]['sha256']='f'*64
            guard.read_frames_once()


def test_same_bytes_named_replacement_after_read_is_not_an_original_FD_match(scope):
    path,_,raw=scope
    with pytest.raises(m.guard_module.Refused):
        with m.FramedSourceGuard(deadline=time.monotonic()+20) as guard:
            guard.read_frames_once();path.unlink();path.write_bytes(raw);path.chmod(0o600)


def test_native_security_drift_refuses_normal_return(scope,monkeypatch):
    with pytest.raises(m.guard_module.Refused):
        with m.FramedSourceGuard(deadline=time.monotonic()+20) as guard:
            guard.read_frames_once();old=guard._security
            monkeypatch.setattr(guard,'_security',lambda row:('changed',) if row['pin'] is not None else old(row))


def test_metadata_change_after_read_refuses_before_publication(scope):
    path,bodies,raw=scope
    with pytest.raises(m.guard_module.Refused):
        with m.FramedSourceGuard(deadline=time.monotonic()+20) as guard:
            data=guard.read_frames_once();m.shape(data,guard.whole_pin)
            os.utime(path,ns=(os.stat(path).st_atime_ns,os.stat(path).st_mtime_ns+1))


def test_new_whole_pin_is_not_constructed_until_all_three_external_pins_pass(scope):
    path,bodies,raw=scope;bad=bytearray(raw);bad[-1]^=1;path.write_bytes(bad)
    with m.FramedSourceGuard(deadline=time.monotonic()+20) as guard:
        fails('frame',guard.read_frames_once);assert guard.whole_pin is None


def test_mapping_bounds_200001_and_list_unicode_are_independent_public_observations(scope):
    _,bodies,raw=scope
    value=m.shape(bodies,m.pin(raw));m.validate_shape(value)
    total=value['numeric_fields']['total']
    assert total['wire_type']=='integer' and total['bounded_nonnegative_integer'] is True
    assert total['public_integer']==200001 and total['canonical_decimal_string_interpretation'] is None
    assert value['numeric_fields']['limit']['public_integer']==1000
    assert value['numeric_fields']['offset']['public_integer']==0
    assert value['data_row_count']==1 and value['symbol_lists']['active']['row_count']==1
    assert value['symbol_lists']['active']['ordered_records_sha256']==m.sha(m.canonical(rows()[0])+b'\n')
    public=m.canonical(value)
    assert b'PRIVATE-SYNTH' not in public and b'Synthetic' not in public and b'invalid.example' not in public
    assert all(value[name] is False for name in m.FALSE_FLAGS)


@pytest.mark.parametrize('wire,expected',(('0',0),('100000',100000),('100000000',100000000),
    ('100000001',None),('010',None),('00',None),(' 12',None),('12 ',None),('+12',None),
    ('-1',None),('1.0',None),('1e6',None),('１２',None),('١٢',None),('',None)))
def test_only_canonical_ASCII_meta_decimal_strings_receive_tagged_diagnostic(wire,expected):
    observed=m._numeric_field({'total':wire},'total')
    assert observed['wire_type']=='string' and observed['bounded_nonnegative_integer'] is False
    assert observed['public_integer'] is None and observed['canonical_decimal_string_interpretation']==expected
    assert observed['value_sha256']==m.sha(m.canonical(wire))


@pytest.mark.parametrize('wire,bounded',((False,False),(True,False),(12.0,False),(None,False),(-1,False),
    (0,True),(100000000,True),(100000001,False)))
def test_bool_float_null_negative_large_are_never_integer_coercions(wire,bounded):
    value=m._numeric_field({'total':wire},'total')
    assert value['bounded_nonnegative_integer'] is bounded
    assert value['public_integer']==(wire if bounded else None)
    assert value['canonical_decimal_string_interpretation'] is None


def test_unknown_field_names_are_hash_only_and_next_value_never_emitted(scope,monkeypatch):
    _,bodies,_=scope;page=json.loads(bodies[2]);page['private-unknown']={'a':'NEVER-PUBLIC'}
    page['meta']['secret-field']='NEVER-PUBLIC'
    bodies=(*bodies[:2],m.canonical(page))
    monkeypatch.setattr(m,'FRAME_PINS',tuple(m.pin(body) for body in bodies))
    raw=b''.join(struct.pack('>Q',len(body))+body for body in bodies);monkeypatch.setattr(m,'DATA_BYTES',len(raw))
    value=m.shape(bodies,m.pin(raw));out=m.canonical(value)
    assert value['mapping_top_fields']['unknown_name_count']==1 and value['meta_fields']['unknown_name_count']==1
    assert b'private-unknown' not in out and b'secret-field' not in out and b'NEVER-PUBLIC' not in out


def test_bad_list_display_does_not_destroy_mapping_metadata_diagnostic(scope,monkeypatch):
    _,bodies,_=scope;bad=rows();bad[0]['Name']='bad\ncontrol'
    bodies=(m.canonical(bad),*bodies[1:]);monkeypatch.setattr(m,'FRAME_PINS',tuple(m.pin(body) for body in bodies))
    raw=b''.join(struct.pack('>Q',len(body))+body for body in bodies);monkeypatch.setattr(m,'DATA_BYTES',len(raw))
    value=m.shape(bodies,m.pin(raw))
    assert value['symbol_lists']['active']['schema_valid'] is False
    assert value['symbol_lists']['delisted']['schema_valid'] is True
    assert value['numeric_fields']['total']['public_integer']==200001


@pytest.mark.parametrize('change',('byte_count','pins','normal','whole_join','actual','flag','string_as_integer'))
def test_output_requires_actual_zero_complete_framed_receipt_and_false_gates(scope,change):
    _,bodies,raw=scope
    with m.FramedSourceGuard(deadline=time.monotonic()+20) as guard:
        checked=guard.read_frames_once();shape=m.shape(checked,guard.whole_pin);receipt=guard.receipt()
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    result={'schema':m.SCHEMA+'-result','shape':shape,'source_guard_receipt':receipt,'source_guard_normal_return':True,
        'AW_failure_binding_sha256':m.sha(m.canonical(m.observed_failure())),**m.FALSE_FLAGS}
    value={'binding':m.binding(args),'result':result};encoded=m.canonical(value)+b'\n';m.validate_output(encoded,0,args)
    if change=='byte_count':result['source_guard_receipt']['byte_extent']+=1
    elif change=='pins':result['source_guard_receipt']['external_body_pins'][0]['sha256']='f'*64
    elif change=='normal':result['source_guard_normal_return']=False
    elif change=='whole_join':result['source_guard_receipt']['AY_observed_whole_file_pin']['sha256']='f'*64
    elif change=='flag':result['shape']['pagination_contract_changed']=True
    elif change=='string_as_integer':
        result['shape']['numeric_fields']['total']['wire_type']='string'
    fails('output',lambda:m.validate_output(m.canonical(value)+b'\n',2 if change=='actual' else 0,args))


def test_failure_packet_can_authenticate_only_actual_two():
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    value={'binding':m.binding(args),'failure_code':'frame','allocation_unknown':True,**m.FALSE_FLAGS}
    raw=m.canonical(value)+b'\n';m.validate_output(raw,2,args)
    fails('output',lambda:m.validate_output(raw,0,args))


def test_native_policy_only_exact_AW_DATA_and_new_AY_outputs():
    policy=m.native_profile()
    assert '(deny network*)' in policy and '/usr/bin/security' in policy and '/Library/Keychains' in policy
    assert m.DATA_RELATIVE in policy and str(m.CONTROL) in policy
    assert '/R326-20261027-AW/claim.json' not in policy and 'catalog-index.json' not in policy
    assert 'requests.jsonl' not in policy and 'HTTP' not in policy


def test_claim_before_private_read_and_guard_normal_return_before_result(scope,monkeypatch):
    _,bodies,raw=scope
    monkeypatch.setattr(m,'preflight',lambda *_:None)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk))
    old=m.FramedSourceGuard.read_frames_once;seen=[]
    def read(guard):
        assert (m.CONTROL/'claim.json').is_file();seen.append('read');return old(guard)
    monkeypatch.setattr(m.FramedSourceGuard,'read_frames_once',read)
    old_exit=m.FramedSourceGuard.__exit__
    def finish(guard,*args):
        out=old_exit(guard,*args);seen.append('normal-return');return out
    monkeypatch.setattr(m.FramedSourceGuard,'__exit__',finish)
    old_write=m.Store.write
    def write(store,name,raw):
        if name=='result-metadata.json':assert seen==['read','normal-return']
        return old_write(store,name,raw)
    monkeypatch.setattr(m.Store,'write',write)
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    out=m.run(args,time.monotonic()+20);m.validate_output(out,0,args)
