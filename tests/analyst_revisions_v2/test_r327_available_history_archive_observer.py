"""Fixed collector synthetic seams; no K operation, source DATA or contact."""
import base64
import copy
import inspect
import io
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import zlib

import pytest

from scripts import observe_arv2_r327_available_history_archive as m
assert 'assistant.dispatch_fence' not in sys.modules


def args():return NS(expected_head='a'*40,collector_sha256='b'*64)


def fail(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def raw_frame():return m.h.canonical({'synthetic_public_metadata':True})+b'\n'


def actual(raw,stdin=b'',exit=0,**changes):
    value={'schema':m.actual_capture.SCHEMA,'dispatched_at':'2026-10-27T00:00:00.000000+00:00',
        'completion_observed_at':'2026-10-27T00:00:01.000000+00:00','spawn_observed':True,
        'actual_exit':exit,'bound':None,'stdin_bytes_requested':len(stdin),'stdin_bytes_written':len(stdin),
        'stdin_sha256':m.h.sha(stdin),'stdin_complete':True,'stdout_bytes':len(raw),'stdout_sha256':m.h.sha(raw),
        'stdout_observed_bytes':len(raw),'stdout_complete':True,'stderr_bytes':0,'stderr_sha256':m.h.sha(b''),
        'stderr_observed_bytes':0,'stderr_complete':True,'protocol_accepted':False,'operation_granted':False,
        'physical_output_bytes_measured':False}
    value.update(changes)
    # Frozen capture cannot report incomplete/unknown work as an unbounded
    # completed measurement. Preserve that real metadata invariant in doubles.
    if value['bound'] is None and (value['actual_exit'] is None or not all(value[key]
            for key in ('stdin_complete','stdout_complete','stderr_complete'))):
        value['bound']='capture_io'
    m.actual_capture.validate_metadata(value);return value


@pytest.fixture
def seam(monkeypatch,tmp_path):
    root=tmp_path/'root';root.mkdir();(root/'.pytest_cache').mkdir()
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'preflight',lambda *args:None)
    monkeypatch.setattr(m.h.ar,'_credential_free',lambda:None)
    monkeypatch.setattr(m.h.environment,'_bootstrap_cli_logging',lambda:None)
    monkeypatch.setattr(m.h.environment,'require_safe_environment',lambda:None)
    monkeypatch.setattr(m.h.ap.capture_support,'_environment',lambda runtime,unused:{'PATH':'/usr/bin:/bin'})
    observed=[]
    def check(raw,exit,a):
        assert exit in (0,2) and raw==raw_frame()
        assert a.caller_sha256==m.K_CALLER_SHA256 and a.profile_sha256==m.K_PROFILE_SHA256
        observed.append(exit)
        return {'synthetic':'checked'}
    monkeypatch.setattr(m.h,'validate_output',check)
    return NS(root=root,observed=observed)


def install_capture(monkeypatch,frames):
    calls=[]
    def capture(command,safe,input_raw,seconds,*,stdout_limit,stderr_limit):
        calls.append((command,safe,input_raw,seconds,stdout_limit,stderr_limit))
        assert stdout_limit==131072 and stderr_limit==8192 and len(calls)<=2
        return frames[len(calls)-1]
    monkeypatch.setattr(m.actual_capture,'capture',capture);return calls


def test_public_frozen_context_is_exact_and_inert():
    value=m.profile_record()
    assert value['K_caller_sha256']==m.K_CALLER_SHA256
    assert value['K_profile_sha256']==m.K_PROFILE_SHA256
    assert m.h.sha(m.h.canonical(m.h.profile_record()))==m.K_PROFILE_SHA256
    assert value['capture_source_sha256']=='febe87c53010227eeca399b8a5087c42d2363c7d3a9ee583d18dfd06b3a68356'
    assert value['capture_byte_count']==12105
    assert all(value[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('exit',[0,2])
def test_observed_exit_forwarded_once_and_output_byte_equal(seam,monkeypatch,exit):
    raw=raw_frame();calls=install_capture(monkeypatch,[(raw,actual(raw,exit=exit)),(raw,actual(raw,stdin=raw))])
    result=m.observe(args(),time.monotonic()+m.SECONDS)
    assert len(calls)==2 and calls[0][0][:2]==['/usr/bin/sandbox-exec','-p']
    assert calls[0][0][2]==m.h.native_profile('produce') and calls[0][0][6]=='produce'
    assert calls[1][0][:2]==['/usr/bin/sandbox-exec','-p']
    assert calls[1][0][2]==m.h.native_profile('validate')
    assert calls[1][0][-2:]==['--actual-exit',str(exit)]
    assert calls[0][2]==b'' and calls[1][2]==raw
    assert calls[0][3]<=1830 and calls[1][3]<=1830
    assert result['output_authenticated'] is True
    assert result['collector_actual_success'] is (exit==0)
    assert result['K_failure_authenticated'] is (exit==2)
    assert m._unpack(result['validated_public_envelope_zlib_base64'])==raw
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert seam.observed==[exit,exit]


@pytest.mark.parametrize('exit',[None,-9,1,3])
def test_unknown_or_unsupported_producer_exit_never_dispatches_validator(seam,monkeypatch,exit):
    raw=raw_frame();calls=install_capture(monkeypatch,[(raw,actual(raw,exit=exit))])
    result=m.observe(args(),time.monotonic()+m.SECONDS)
    assert len(calls)==1 and result['terminal']=='external_failure'
    assert result['external_failure_code']==('producer_incomplete' if exit is None else 'producer_exit')
    assert result['validator'] is None
    assert result['output_authenticated'] is False


@pytest.mark.parametrize('change',[
    {'stdout_complete':False},{'stderr_complete':False},{'stdin_complete':False},
    {'bound':'deadline','actual_exit':-9},{'stdout_sha256':'d'*64},
    {'stderr_bytes':1,'stderr_observed_bytes':1,'stderr_sha256':'c'*64}])
def test_incomplete_or_mismatched_producer_never_validates(seam,monkeypatch,change):
    raw=raw_frame();calls=install_capture(monkeypatch,[(raw,actual(raw,**change))])
    result=m.observe(args(),time.monotonic()+m.SECONDS)
    assert len(calls)==1 and result['output_authenticated'] is False
    assert result['external_failure_code']=='producer_incomplete'


def test_malformed_producer_metadata_never_serialized_as_valid(seam,monkeypatch):
    raw=raw_frame();invalid=actual(raw);invalid['private_unknown']='DO-NOT-OUTPUT'
    calls=install_capture(monkeypatch,[(raw,invalid)])
    with pytest.raises(m.Refused):m.observe(args(),time.monotonic()+m.SECONDS)
    assert len(calls)==1


def test_producer_public_schema_refusal_prevents_validator(seam,monkeypatch):
    raw=raw_frame();calls=install_capture(monkeypatch,[(raw,actual(raw))])
    def refusal(*args):raise ValueError('DO-NOT-OUTPUT')
    monkeypatch.setattr(m.h,'validate_output',refusal)
    result=m.observe(args(),time.monotonic()+m.SECONDS)
    assert len(calls)==1 and result['external_failure_code']=='producer_format'
    assert b'DO-NOT-OUTPUT' not in m.h.canonical(result)


@pytest.mark.parametrize('exit',[None,-9,1,2])
def test_validator_nonzero_or_unknown_cannot_authenticate(seam,monkeypatch,exit):
    raw=raw_frame();calls=install_capture(monkeypatch,[(raw,actual(raw)),(raw,actual(raw,stdin=raw,exit=exit))])
    result=m.observe(args(),time.monotonic()+m.SECONDS)
    assert len(calls)==2 and result['output_authenticated'] is False
    assert result['external_failure_code']==('validator_incomplete' if exit is None else 'validator_exit')


def test_validator_byte_difference_cannot_authenticate(seam,monkeypatch):
    raw=raw_frame();different=m.h.canonical({'different':'public'})+b'\n'
    calls=install_capture(monkeypatch,[(raw,actual(raw)),(different,actual(different,stdin=raw))])
    result=m.observe(args(),time.monotonic()+m.SECONDS)
    assert len(calls)==2 and result['external_failure_code']=='validator_output'
    assert result['validated_public_envelope_zlib_base64'] is None


def test_validator_input_consumption_must_be_complete(seam,monkeypatch):
    raw=raw_frame();bad=actual(raw,stdin=raw,stdin_complete=False,stdin_bytes_written=0)
    calls=install_capture(monkeypatch,[(raw,actual(raw)),(raw,bad)])
    result=m.observe(args(),time.monotonic()+m.SECONDS)
    assert len(calls)==2 and result['external_failure_code']=='validator_incomplete'


def test_postflight_source_drift_cannot_publish_encoded_frame(seam,monkeypatch):
    raw=raw_frame();calls=install_capture(monkeypatch,[(raw,actual(raw)),(raw,actual(raw,stdin=raw))])
    visits=[]
    def check(*args):
        visits.append(True)
        if len(visits)==3:raise m.Refused('preflight')
    monkeypatch.setattr(m,'preflight',check)
    result=m.observe(args(),time.monotonic()+m.SECONDS)
    assert len(calls)==2 and result['external_failure_code']=='postflight'
    assert result['validated_public_envelope_pin'] is None


def test_preflight_failure_has_no_capture_or_runtime(seam,monkeypatch):
    calls=[]
    def check(*args):raise m.Refused('preflight')
    monkeypatch.setattr(m,'preflight',check)
    monkeypatch.setattr(m.actual_capture,'capture',lambda *args,**kwargs:calls.append(True))
    result=m.observe(args(),time.monotonic()+m.SECONDS)
    assert result['external_failure_code']=='preflight' and calls==[]
    assert list((seam.root/'.pytest_cache').iterdir())==[]


@pytest.mark.parametrize('raw',[b'x',b'x'*131072])
def test_compression_roundtrip_bounded(raw):
    assert m._unpack(m._pack(raw))==raw


@pytest.mark.parametrize('mutator',[
    lambda text:text+'!',lambda text:base64.b64encode(zlib.compress(b'x'*131073)).decode('ascii'),
    lambda text:base64.b64encode(base64.b64decode(text)+b'trailing').decode('ascii')])
def test_encoded_envelope_corruption_and_bomb_refuse(mutator):
    encoded=m._pack(raw_frame());fail('public_output_bound',lambda:m._unpack(mutator(encoded)))


def test_incompressible_encoding_limit_refuses():
    # Deterministic nonsecret bytes; no system randomness or data input.
    raw=b''.join(__import__('hashlib').sha256(str(i).encode()).digest() for i in range(4096))
    fail('public_output_bound',lambda:m._pack(raw))


def test_authenticated_failure_cannot_be_relabelled_success(seam,monkeypatch):
    raw=raw_frame();install_capture(monkeypatch,[(raw,actual(raw,exit=2)),(raw,actual(raw,stdin=raw))])
    value=m.observe(args(),time.monotonic()+m.SECONDS)
    bad=copy.deepcopy(value);bad.update(terminal='technical_observation_complete',
        K_failure_authenticated=False,J_technical_observation_succeeded=True,collector_actual_success=True)
    fail('public_output_bound',lambda:m.validate_result(bad,args()))


def test_invalid_argument_binding_not_echoed():
    bad=NS(expected_head='DO-NOT-OUTPUT',collector_sha256='b'*64)
    fail('preflight',lambda:m.binding(bad))


def test_source_has_no_operation_adapter_or_private_artifact_reader():
    source=inspect.getsource(m)
    assert 'keychain.load_key' not in source and 'h.run(' not in source
    assert 'h.CONTROL' not in source and 'h.SOURCE' in source
    assert 'actual_capture.capture(command,safe,b\'\'' in source
    assert 'actual_capture.capture(command,safe,raw' in source


def test_outer_failure_is_finite_without_traceback(seam,monkeypatch):
    def broken(*args):raise ValueError('SYNTHETIC-PRIVATE-ERROR')
    monkeypatch.setattr(m,'observe',broken)
    output=io.BytesIO();monkeypatch.setattr(sys,'stdout',NS(buffer=output))
    assert m.main(['--expected-head','a'*40,'--collector-sha256','b'*64])==2
    assert b'SYNTHETIC-PRIVATE-ERROR' not in output.getvalue()
    value=m.h.parse(output.getvalue()[:-1]);assert value['external_failure_code']=='unknown'
