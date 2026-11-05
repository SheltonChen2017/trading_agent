"""Synthetic fixed-plan streaming guard tests; no production DATA access."""
import copy
import hashlib
import os
from pathlib import Path
import time

import pytest

from scripts import arv2_r298_price_corpus_guard as m


@pytest.fixture
def files(monkeypatch,tmp_path):
    root=tmp_path/'root';root.mkdir(mode=0o755)
    parent=root
    for part in ('artifacts','analyst_revisions_v2','synthetic','AP'):
        parent=parent/part;parent.mkdir(mode=0o700)
    values={'plan':b'{"synthetic":true}','dispatch':b'{}\n','captures':b'{}\n','corpus':b'AAABBBCCC'}
    plan={}
    for role,raw in values.items():
        path=parent/(role+'.data');path.write_bytes(raw);path.chmod(0o600)
        plan[role]={'relative_path':path.relative_to(root).as_posix(),'byte_count':len(raw),'sha256':m.sha(raw)}
    monkeypatch.setattr(m,'ROOT',root)
    monkeypatch.setattr(m,'_scope',lambda:None)
    monkeypatch.setattr(m.anchor,'data_plan',lambda:copy.deepcopy(plan))
    monkeypatch.setattr(m.security,'snapshot',lambda fd:('synthetic-security',))
    monkeypatch.setattr(m,'MAX_RANGES',3)
    return root,parent,values,plan


def fail(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def consume(guard,values):
    guard.authenticate_all()
    for role in ('plan','dispatch','captures'):assert guard.read_small(role)==values[role]
    for index in range(3):
        raw=values['corpus'][index*3:index*3+3]
        assert guard.read_range(index,index*3,3,m.sha(raw))==raw


def test_two_pass_all_hashes_then_exact_ranges_normal_return_and_receipt(files):
    _root,_parent,values,plan=files
    guard=m.PriceCorpusGuard(plan,deadline=time.monotonic()+20)
    with guard:
        fail('read_schedule',lambda:guard.read_small('plan'))
        consume(guard,values);receipt=guard.receipt()
        assert receipt['whole_hashes_checked']==4 and receipt['range_count']==3
        assert receipt['corpus_extent']==9 and receipt['requires_normal_return_before_use']
        assert m.validate_receipt(receipt,plan)==receipt
    assert not guard.active and not guard.objects
    fail('state',lambda:guard.__enter__())


@pytest.mark.parametrize('field',('path','bytes','hash','role','extra'))
def test_exact_fixed_plan_rejects_refresh_or_extra_scope(files,field):
    *_,plan=files;changed=copy.deepcopy(plan)
    if field=='path':changed['corpus']['relative_path']='artifacts/analyst_revisions_v2/other/corpus'
    elif field=='bytes':changed['corpus']['byte_count']+=1
    elif field=='hash':changed['corpus']['sha256']='e'*64
    elif field=='role':changed['other']=changed.pop('corpus')
    else:changed['corpus']['extra']=True
    fail('plan',lambda:m.PriceCorpusGuard(changed,deadline=time.monotonic()+20))


def test_all_whole_hashes_authenticate_before_any_semantic_read(files):
    _root,parent,_values,plan=files
    # Same size corruption cannot be dismissed by path or endpoint metadata.
    path=parent/'corpus.data';path.write_bytes(b'XXXBBBCCC');path.chmod(0o600)
    with pytest.raises(m.Refused) as caught:
        with m.PriceCorpusGuard(plan,deadline=time.monotonic()+20) as guard:
            guard.authenticate_all()
    assert m.finite(caught.value)=='byte_pin'


def test_whole_hash_stream_accepts_large_corpus_without_changing_frozen_small_guard(files,monkeypatch):
    _root,parent,_values,plan=files
    from scripts import arv2_r298_fixed_data_guard as old
    assert old.MAX_FILE_BYTES==32*1024*1024 and old.MAX_TOTAL_BYTES==64*1024*1024
    size=33*1024*1024
    with (parent/'corpus.data').open('wb') as out:out.truncate(size)
    h=hashlib.sha256()
    for _ in range(size//65536):h.update(b'\0'*65536)
    plan['corpus'].update(byte_count=size,sha256=h.hexdigest())
    class Stop(Exception):pass
    chunks=[];original=m.PriceCorpusGuard._chunks
    def stream(self,role,offset,length):
        for raw in original(self,role,offset,length):
            chunks.append(len(raw));yield raw
    monkeypatch.setattr(m.PriceCorpusGuard,'_chunks',stream)
    with pytest.raises(Stop):
        with m.PriceCorpusGuard(plan,deadline=time.monotonic()+20) as guard:
            guard.authenticate_all();assert guard.authenticated
            raise Stop()
    assert len(chunks)>512 and max(chunks)<=m.CHUNK
    assert old.MAX_FILE_BYTES==32*1024*1024


@pytest.mark.parametrize('case',('before_small','duplicate','offset','length','ordinal','hash'))
def test_range_schedule_and_byte_pin_cannot_be_skipped_or_retried(files,case):
    *_,values,plan=files
    with pytest.raises(m.Refused):
        with m.PriceCorpusGuard(plan,deadline=time.monotonic()+20) as guard:
            guard.authenticate_all()
            if case!='before_small':
                for role in ('plan','dispatch','captures'):guard.read_small(role)
            if case=='duplicate':
                guard.read_range(0,0,3,m.sha(b'AAA'));guard.read_range(0,0,3,m.sha(b'AAA'))
            else:guard.read_range(1 if case=='ordinal' else 0,1 if case=='offset' else 0,
                m.MAX_RANGE+1 if case=='length' else 3,'e'*64 if case=='hash' else m.sha(b'AAA'))


@pytest.mark.parametrize('case',('missing_range','missing_small','second_hash','second_small'))
def test_incomplete_or_repeated_read_protocol_never_normally_returns(files,case):
    *_,values,plan=files
    with pytest.raises(m.Refused) as caught:
        with m.PriceCorpusGuard(plan,deadline=time.monotonic()+20) as guard:
            guard.authenticate_all()
            if case=='second_hash':guard.authenticate_all()
            elif case=='missing_small':pass
            else:
                for role in ('plan','dispatch','captures'):guard.read_small(role)
                if case=='second_small':guard.read_small('plan')
    assert m.finite(caught.value)=='read_schedule'


@pytest.mark.parametrize('change',('leaf_replaced','leaf_mode','directory_mode','security','plan_mutated'))
def test_held_named_full_metadata_and_security_refuse_drift(files,monkeypatch,change):
    _root,parent,values,plan=files
    with pytest.raises(m.Refused):
        with m.PriceCorpusGuard(plan,deadline=time.monotonic()+20) as guard:
            guard.authenticate_all()
            if change=='leaf_replaced':
                (parent/'plan.data').rename(parent/'old-plan.data')
                (parent/'plan.data').write_bytes(values['plan']);(parent/'plan.data').chmod(0o600)
            elif change=='leaf_mode':(parent/'plan.data').chmod(0o640)
            elif change=='directory_mode':parent.chmod(0o755)
            elif change=='security':monkeypatch.setattr(m.security,'snapshot',lambda fd:('changed',))
            else:guard.plan['plan']['sha256']='e'*64
            guard.verify()


def test_no_follow_refuses_symlink_leaf(files):
    _root,parent,values,plan=files
    target=parent/'original-plan.data';(parent/'plan.data').rename(target)
    (parent/'plan.data').symlink_to(target)
    with pytest.raises(m.Refused):
        with m.PriceCorpusGuard(plan,deadline=time.monotonic()+20):pass


def test_deadline_refuses_before_open(files):
    *_,plan=files
    fail('deadline',lambda:m.PriceCorpusGuard(plan,deadline=time.monotonic()-1))


def test_ten_fields_come_from_one_atomic_stat_result(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    def fstat(fd):calls.append(fd);return SimpleNamespace(**{field:1 for field in m.FIELDS})
    monkeypatch.setattr(m.os,'fstat',fstat)
    assert m._metadata(99)==(1,)*len(m.FIELDS) and calls==[99]
