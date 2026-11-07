"""Fresh all-seven DATA/axis tests using public code and supplied fixtures."""
import copy
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import time

import pytest

from scripts import arv2_r348_plain_submission_data as m
from scripts import arv2_r343_legacy_six_projection as projection
from .test_r347_plain_submission_data import supplied,republish_synthetic


def refused(code,operation):
    with pytest.raises(m.Refused) as caught:operation()
    assert caught.value.args==(code,)


@pytest.fixture
def data(supplied,monkeypatch):
    # Reuse the already-real transport and seven-vector fixture. Only its tiny
    # synthetic session stream is replaced at the explicit geometry seam here;
    # separate tests below exercise the unchanged real axis parser end to end.
    monkeypatch.setattr(m,'_evaluation_sessions',lambda raw,manifest,descriptor:('2021-01-04','2026-10-13'))
    return supplied


def test_all_seven_candidates_preserve_frozen_AR100_and_exact_profiles_and_sources(data):
    files,fact,proposal=data;checked=m.previous.validate_supplied(files,fact=fact)
    value=m.validate_supplied(files,fact=fact)
    assert [row.ar_percent for row in value.candidates]==list(m.PERCENTS)
    assert value.candidates[1]==checked.candidate
    assert value.uploads==checked.uploads and value.source_identity_json==checked.source_identity_json
    assert value.attempt_state_at_preparation_json==checked.attempt_state_at_preparation_json
    assert json.loads(value.attempt_state_at_preparation_json)['R343-AR100']['attempts_consumed']==3
    assert len(value.uploads)==6 and value.uploads[-1].activation_manifest is True
    for candidate,source in zip(value.candidates,proposal['cells'],strict=True):
        assert candidate.profile_json==m.canonical(source['profile'])
        assert candidate.sources==tuple((name,text.encode('ascii')) for name,text in source['source_pairs'])
    before=value.candidates[0].cell_record();proposal['cells'][0]['source_pairs'][0][1]='changed'
    assert value.candidates[0].cell_record()==before
    before['source_pairs'][0][1]='changed-again'
    assert value.candidates[0].cell_record()!=before
    with pytest.raises(FrozenInstanceError):value.candidates=()
    assert 'synthetic-evaluator' not in repr(value)


@pytest.mark.parametrize('index',range(7))
def test_every_arm_reaches_frozen_inner_source_vector_validation(data,index):
    files,fact,proposal=data;proposal['cells'][index]['source_pairs'][0][1]='changed\n'
    republish_synthetic(data)
    refused('sources',lambda:m.validate_supplied(files,fact=fact))


def test_all_eight_external_hashes_pass_before_axis_parse(data,monkeypatch):
    files,fact,_=data;files['report.json']+=b' '
    monkeypatch.setattr(m,'_evaluation_sessions',lambda *a:(_ for _ in ()).throw(AssertionError('axis before all8 hashes')))
    refused('pin',lambda:m.validate_supplied(files,fact=fact))


def test_frozen_operational_entry_is_never_called(data,monkeypatch):
    monkeypatch.setattr(m.previous.FreshPlainSubmission,'__enter__',lambda *a:
        (_ for _ in ()).throw(AssertionError('old operational protocol invoked')))
    assert len(m.validate_supplied(data[0],fact=data[1]).candidates)==7


@pytest.fixture(scope='module')
def axis():
    # Public deterministic calendar construction only; no DATA file or captured
    # source is opened and no market observation is reconstructed.
    days=projection.october._sessions()
    evaluator=m.previous.plain.evaluator
    rows=tuple({'schema':evaluator.SESSION_SCHEMA,'session_index':index,'session':day}
        for index,day in enumerate(days))
    raw=b''.join(m.canonical(row)+b'\n' for row in rows)
    manifest={'schema':evaluator.MANIFEST_SCHEMA,'session_axis_count':len(rows),'session_axis_sha256':m.pin(raw)['sha256']}
    descriptor={'record_count':len(rows)}
    return raw,manifest,descriptor,days


def test_genuine_calendar_geometry_is_parsed_from_schema_bound_canonical_rows(axis):
    raw,manifest,descriptor,days=axis
    actual=m._evaluation_sessions(raw,manifest,descriptor)
    expected,decisions=projection._geometry(days)
    assert actual==expected and len(actual)==1451 and len(decisions)==302
    assert actual[0]=='2021-01-04' and actual[-1]=='2026-10-13'


@pytest.mark.parametrize('fault',['manifest_schema','manifest_count','manifest_hash','index','row_schema',
    'duplicate','date','canonical','trailing','geometry'])
def test_axis_header_rows_and_fixed_full_source_geometry_are_load_bearing(axis,fault):
    original,header,descriptor,_=axis;manifest=copy.deepcopy(header);descriptor=copy.deepcopy(descriptor);raw=original
    if fault=='manifest_schema':manifest['schema']='other'
    elif fault=='manifest_count':manifest['session_axis_count']=True
    elif fault=='manifest_hash':manifest['session_axis_sha256']='0'*64
    else:
        rows=[json.loads(line) for line in raw.splitlines()]
        if fault=='index':rows[0]['session_index']=True
        elif fault=='row_schema':rows[0]['schema']='other'
        elif fault=='duplicate':rows[1]['session']=rows[0]['session']
        elif fault=='date':rows[0]['session']='2013-1-2'
        elif fault=='geometry':rows[-1]['session']='2026-10-16'
        raw=b''.join(m.canonical(row)+b'\n' for row in rows)
        if fault=='canonical':raw=b' '+raw
        elif fault=='trailing':raw+=b'\n'
        # Only this supplied synthetic header is rebound to reach inner schema
        # and fixed-axis checks. Production still requires original8 leaf pins.
        manifest['session_axis_sha256']=m.pin(raw)['sha256']
    refused('axis',lambda:m._evaluation_sessions(raw,manifest,descriptor))


@pytest.fixture
def location(tmp_path,monkeypatch,data):
    files,fact,_=data
    root=tmp_path/'synthetic-repository';root.mkdir(mode=0o755)
    directory=root/'artifacts/analyst_revisions_v2/legacy_six_plain/R346-20261107-A'
    current=root
    for part in directory.relative_to(root).parts:
        current/=part;current.mkdir(mode=0o700)
    for name,raw in files.items():
        path=directory/name;path.write_bytes(raw);path.chmod(0o600)
    monkeypatch.chdir(root);monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'DIRECTORY',directory)
    monkeypatch.setattr(m,'parse_fact',lambda raw:copy.deepcopy(fact))
    monkeypatch.setattr(m.security,'snapshot',lambda fd:('synthetic-native',os.fstat(fd).st_uid))
    return directory


def context():return m.FreshAllPlainSubmission(fact_bytes=b'explicit-synthetic-fact-seam',deadline=time.monotonic()+179)


def test_new_context_keeps_all_original_fds_and_never_opens_claim_or_invokes_old_entry(location,monkeypatch):
    opened=[];real_open=os.open
    def observed(name,*args,**kwargs):opened.append(str(name));return real_open(name,*args,**kwargs)
    monkeypatch.setattr(m.os,'open',observed)
    monkeypatch.setattr(m.os,'listdir',lambda *a:(_ for _ in ()).throw(AssertionError('directory census')))
    monkeypatch.setattr(m.previous.FreshPlainSubmission,'__enter__',lambda *a:
        (_ for _ in ()).throw(AssertionError('old entry called')))
    hold=context()
    with hold as live:
        assert len(live.value.candidates)==7
        assert len([row for row in live.rows if row[6] is not None])==8
        assert all(os.fstat(row[1]) for row in live.rows)
        live.verify()
    assert not hold.rows and not hold.cache
    assert all(opened.count(name)==1 for name in m.NAMES) and 'claim.json' not in opened
    refused('state',hold.__enter__)


@pytest.mark.parametrize('fault,code',[('mode','metadata'),('symlink','path'),('bytes','pin'),('hardlink','pin')])
def test_failed_leaf_cannot_reach_private_source_or_axis_parsing(location,monkeypatch,fault,code):
    path=location/m.NAMES[0]
    if fault=='mode':path.chmod(0o644)
    elif fault=='symlink':
        old=path.with_name('retained-synthetic');path.rename(old);path.symlink_to(old)
    elif fault=='hardlink':os.link(path,path.with_name('retained-synthetic'))
    else:path.write_bytes(b'changed');path.chmod(0o600)
    monkeypatch.setattr(m,'validate_supplied',lambda *a,**k:(_ for _ in ()).throw(AssertionError('private parse')))
    hold=context();refused(code,hold.__enter__);assert not hold.rows


def test_named_swap_keeps_original_bytes_but_refuses_normal_return(location):
    hold=context();path=location/m.NAMES[0]
    with pytest.raises(m.Refused,match='metadata'):
        with hold as live:
            row=next(row for row in live.rows if row[0]==path);raw=os.pread(row[1],row[6]['byte_count'],0)
            path.rename(path.with_name('retained-synthetic'));path.write_bytes(raw);path.chmod(0o600)
            assert os.pread(row[1],len(raw),0)==raw
    assert not hold.rows


def test_late_security_change_refuses_all_seven_consumption_and_closes(location,monkeypatch):
    hold=context()
    with pytest.raises(m.Refused,match='security'):
        with hold:monkeypatch.setattr(m.security,'snapshot',lambda fd:('changed',))
    assert not hold.rows


def test_close_failure_still_attempts_all_owned_descriptors(location,monkeypatch):
    hold=context();hold.__enter__();fds=[row[1] for row in hold.rows];closed=[];real_close=os.close
    def failing_once(fd):
        closed.append(fd);real_close(fd)
        if len(closed)==1:raise OSError('synthetic close fault')
    monkeypatch.setattr(m.os,'close',failing_once)
    refused('close',lambda:hold.__exit__(None,None,None))
    assert set(closed)==set(fds) and len(closed)==len(fds) and not hold.rows
