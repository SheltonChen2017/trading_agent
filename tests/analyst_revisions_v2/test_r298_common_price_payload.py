"""Synthetic 73-file payload boundary tests; no production DATA or contact."""
import copy
import errno
import fcntl
import hashlib
import inspect
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_common_price_payload as m


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


@pytest.fixture
def sources(monkeypatch,tmp_path):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    plan=m.data_plan();bodies={}
    for ordinal,role in enumerate(m.ROLES):
        row=plan[role];path=root/row['relative_path'];path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        for parent in path.parents:
            if parent==root:break
            parent.chmod(0o700)
        # Intentionally not valid price/catalog JSON: byte mechanics do not parse it.
        raw=(b'\xffnot-json-private-synthetic-'+str(ordinal).encode())
        path.write_bytes(raw);path.chmod(0o600);bodies[role]=raw
        row.update(byte_count=len(raw),sha256=m.sha(raw))
    monkeypatch.chdir(root);monkeypatch.setattr(m,'ROOT',root)
    monkeypatch.setattr(m,'data_plan',lambda:copy.deepcopy(plan))
    monkeypatch.setattr(m,'PLAN_SHA256',m.sha(m.canonical(plan)))
    monkeypatch.setattr(m,'_security',lambda fd:('synthetic-security',))
    monkeypatch.setattr(m,'check_resources',lambda:{'synthetic':True})
    return root,plan,bodies


@pytest.fixture
def archive(tmp_path):
    path=tmp_path/'owned-archive.bin'
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:yield fd,path
    finally:os.close(fd)


def test_public73_exact_anchor_and_limits_do_not_expand_frozen_guard():
    from scripts import arv2_r298_fixed_data_guard as old
    plan=m.data_plan();assert len(plan)==73 and set(plan)==set(m.ROLES)
    assert m.ROLES[0]=='catalog' and m.ROLES[-1]=='manifest'  # Explicit, not dict insertion order.
    assert sum(row['byte_count'] for row in plan.values())==148531396
    assert plan['manifest']['byte_count']==22373 and plan['catalog']['byte_count']==2224206
    assert old.MAX_FILES==8 and old.MAX_FILE_BYTES==32*1024*1024 and old.MAX_TOTAL_BYTES==64*1024*1024
    assert m.MAX_PAYLOAD==517*1024*1024 and m.CHUNK==65536 and m.MAX_SOURCE_FDS==96
    assert m.sha((m.ROOT/'scripts/arv2_r298_ar_source_binding.py').read_bytes())==m.ANCHOR_SOURCE_SHA256
    profile=m.profile_record();assert all(profile[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('change',('missing','extra','old_control','path','bool','month_oversize','catalog_oversize','manifest_oversize','hash'))
def test_fixed_plan_has_no_alternate_source_or_silent_pin_refresh(change):
    plan=m.data_plan()
    if change=='missing':plan.pop('month_000')
    elif change=='extra':plan['report']=plan['manifest']
    elif change=='old_control':plan['manifest']['relative_path']=plan['manifest']['relative_path'].replace('manifest-private.json','report.json')
    elif change=='path':plan['catalog']['relative_path']='../catalog-private.json'
    elif change=='bool':plan['catalog']['byte_count']=True
    elif change=='month_oversize':plan['month_000']['byte_count']=m.MAX_MONTH+1
    elif change=='catalog_oversize':plan['catalog']['byte_count']=m.MAX_CATALOG+1
    elif change=='manifest_oversize':plan['manifest']['byte_count']=m.MAX_MANIFEST+1
    else:plan['catalog']['sha256']='g'*64
    fails('plan',lambda:m.checked_plan(plan))


def test_prepare_and_independent_verifier_join_all73_bytes_without_source_semantics(sources,archive,monkeypatch):
    _,plan,bodies=sources;fd,path=archive;read_sizes=[];write_sizes=[]
    original_read,original_write=os.pread,os.pwrite
    def read(fd,count,offset):read_sizes.append(count);return original_read(fd,count,offset)
    def write(fd,raw,offset):write_sizes.append(len(raw));return original_write(fd,raw,offset)
    monkeypatch.setattr(m.os,'pread',read);monkeypatch.setattr(m.os,'pwrite',write)
    ready=m.prepare_archive_fd(fd,expected_initial_metadata=m.metadata(fd),deadline=time.monotonic()+20)
    verified=m.verify_archive_fd(fd,expected_metadata=m.metadata(fd),deadline=time.monotonic()+20)
    assert ready['archive_pin']==verified['archive_pin']
    assert ready['source_guard_normal_return'] is True
    assert ready['source_receipt']['whole_hashes_checked']==ready['source_receipt']['copied_ranges']==73
    assert ready['range_count']==verified['range_count']==73
    assert all(ready[key] is verified[key] is False for key in m.FALSE_FLAGS)
    assert max(read_sizes)<=m.CHUNK and max(write_sizes)<=m.CHUNK
    raw=path.read_bytes();assert raw.startswith(m._header_bytes())
    assert raw[len(m._header_bytes()):]==b''.join(bodies[role] for role in m.ROLES)
    assert ready['archive_pin']=={'byte_count':len(raw),'sha256':m.sha(raw)}
    assert m.validate_receipt(ready,ready=True)==ready and m.validate_receipt(verified,ready=False)==verified


def test_last_source_hash_failure_prevents_any_archive_header_or_payload(sources,archive):
    root,plan,_=sources;fd,_=archive;path=root/plan['manifest']['relative_path']
    raw=path.read_bytes();path.write_bytes(bytes([raw[0]^1])+raw[1:])
    fails('byte_pin',lambda:m.prepare_archive_fd(fd,expected_initial_metadata=m.metadata(fd),deadline=time.monotonic()+20))
    assert os.fstat(fd).st_size==0


def test_copy_cannot_start_before_all_hashes_or_reorder_repeat_skip(sources,archive):
    _,plan,_=sources;fd,_=archive
    writer=m._ArchiveWriter(fd,m.metadata(fd),time.monotonic()+20)
    guard=m.PayloadSourceGuard(plan,deadline=time.monotonic()+20)
    with pytest.raises(m.Refused):
        with guard:
            fails('read_schedule',lambda:guard.copy_next('catalog',writer))
            guard.authenticate_all()
            fails('read_schedule',guard.authenticate_all)
            fails('read_schedule',lambda:guard.copy_next('manifest',writer))
            guard.copy_next('catalog',writer)
            fails('read_schedule',lambda:guard.copy_next('catalog',writer))
            # Normal return before all73 is itself refused.
    assert guard.returned is False and guard.active is False


@pytest.mark.parametrize('change',('symlink','hardlink','mode','replace','security','mtime'))
def test_source_full_identity_security_or_named_change_prevents_normal_return(sources,archive,monkeypatch,change):
    root,plan,_=sources;fd,_=archive;path=root/plan['catalog']['relative_path']
    guard=m.PayloadSourceGuard(plan,deadline=time.monotonic()+20)
    if change=='symlink':
        other=path.with_name('retained-original');path.rename(other);path.symlink_to(other)
        with pytest.raises(m.Refused):guard.__enter__()
        return
    if change=='hardlink':
        os.link(path,path.with_name('retained-hardlink'))
        with pytest.raises(m.Refused):guard.__enter__()
        return
    if change=='mode':
        path.chmod(0o640)
        with pytest.raises(m.Refused):guard.__enter__()
        return
    with pytest.raises(m.Refused):
        with guard:
            guard.authenticate_all()
            if change=='replace':
                raw=path.read_bytes();path.rename(path.with_name('retained-original'));path.write_bytes(raw);path.chmod(0o600)
            elif change=='security':monkeypatch.setattr(m,'_security',lambda fd:('changed-security',))
            else:
                info=path.stat();os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1000000000))
            guard.verify()
    assert guard.returned is False


def test_source_guard_close_failure_never_returns_READY(sources,archive,monkeypatch):
    fd,_=archive;original=m.PayloadSourceGuard.close
    def close(self):original(self);raise m.Refused('close')
    monkeypatch.setattr(m.PayloadSourceGuard,'close',close)
    fails('close',lambda:m.prepare_archive_fd(fd,expected_initial_metadata=m.metadata(fd),deadline=time.monotonic()+20))
    assert os.fstat(fd).st_size>0  # Retained, never truncated/repaired or accepted.


@pytest.mark.parametrize('change',('header','range','tail','truncated','initial_metadata','security'))
def test_independent_archive_authentication_rejects_header_range_extent_and_endpoint_drift(sources,archive,monkeypatch,change):
    fd,_=archive;m.prepare_archive_fd(fd,expected_initial_metadata=m.metadata(fd),deadline=time.monotonic()+20)
    before=m.metadata(fd)
    if change=='header':os.pwrite(fd,b'X',0)
    elif change=='range':os.pwrite(fd,b'X',len(m._header_bytes()))
    elif change=='tail':os.pwrite(fd,b'X',before[6])
    elif change=='truncated':os.ftruncate(fd,before[6]-1)
    elif change=='security':
        original=m._security;calls=[0]
        def security(fd):calls[0]+=1;return original(fd) if calls[0]==1 else ('drift',)
        monkeypatch.setattr(m,'_security',security)
    expected=before if change in ('initial_metadata','security') else m.metadata(fd)
    if change=='initial_metadata':os.pwrite(fd,b'X',len(m._header_bytes()))
    with pytest.raises(m.Refused):m.verify_archive_fd(fd,expected_metadata=expected,deadline=time.monotonic()+20)


@pytest.mark.parametrize('change',('nonempty','boolfd','metadata','readonly','append','multiple_links'))
def test_archive_is_exact_empty_owned_original_private_regular_FD(sources,archive,change):
    fd,path=archive;original=m.metadata(fd);other=None
    if change=='nonempty':os.write(fd,b'retained')
    elif change=='boolfd':fd=True
    elif change=='metadata':original=tuple(value+1 if index==1 else value for index,value in enumerate(original))
    elif change=='readonly':other=os.open(path,os.O_RDONLY);fd=other;original=m.metadata(fd)
    elif change=='append':fcntl.fcntl(fd,fcntl.F_SETFL,fcntl.fcntl(fd,fcntl.F_GETFL)|os.O_APPEND)
    else:os.link(path,path.with_name('extra-link'));original=m.metadata(fd)
    try:
        with pytest.raises(m.Refused):m.prepare_archive_fd(fd,expected_initial_metadata=original,deadline=time.monotonic()+20)
    finally:
        if other is not None:os.close(other)


@pytest.mark.parametrize('field',('extra','float','flag','normal','hash','range','source_extra','source_count'))
def test_READY_closed_metadata_does_not_accept_authority_or_count_forgery(sources,archive,field):
    fd,_=archive;value=m.prepare_archive_fd(fd,expected_initial_metadata=m.metadata(fd),deadline=time.monotonic()+20)
    if field=='extra':value['catalog']={'private':'row'}
    elif field=='float':value['archive_pin']['byte_count']=float(value['archive_pin']['byte_count'])
    elif field=='flag':value['QC_transfer_granted']=True
    elif field=='normal':value['source_guard_normal_return']=False
    elif field=='hash':value['archive_pin']['sha256']='z'*64
    elif field=='range':value['range_count']=72
    elif field=='source_extra':value['source_receipt']['raw']=b'private'
    else:value['source_receipt']['whole_hashes_checked']=72
    fails('receipt',lambda:m.validate_receipt(value,ready=True))


@pytest.mark.parametrize('issue',('fd_soft','fd_busy','disk'))
def test_resource_checks_refuse_without_changing_limits(monkeypatch,issue):
    monkeypatch.setattr(m.resource,'getrlimit',lambda _:((64 if issue=='fd_soft' else 128),128))
    def check(fd,op):
        if issue=='fd_busy' and fd<20:return 0
        if fd<3:return 0
        raise OSError(errno.EBADF,'synthetic')
    monkeypatch.setattr(m.fcntl,'fcntl',check)
    monkeypatch.setattr(m.os,'statvfs',lambda _:NS(f_bavail=(0 if issue=='disk' else m.MIN_FREE_DISK),f_frsize=1))
    fails('disk_budget' if issue=='disk' else 'descriptor_budget',m.check_resources)
    assert 'setrlimit' not in inspect.getsource(m.check_resources)


def test_header_is_exact_bounded_contiguous73_and_contains_no_private_rows():
    value=m.header_record();offset=0
    assert len(value['entries'])==73 and len(m._header_bytes())<=m.MAX_HEADER+len(m.MAGIC)+8
    for index,row in enumerate(value['entries']):
        assert row['ordinal']==index and row['role']==m.ROLES[index] and row['offset']==offset
        offset+=row['byte_count']
    assert offset==value['payload_byte_count']==148531396
    raw=m._header_bytes();assert b'"ticker"' not in raw and b'"assignments"' not in raw and b'"prices"' not in raw


def test_source_security_observer_is_native_and_finite_not_silently_ignored(archive,monkeypatch):
    fd,_=archive;observation=m._security(fd)
    assert observation is not None
    monkeypatch.setattr(m.security,'snapshot',lambda fd:(_ for _ in ()).throw(m.security.Refusal('extended ACL entry present')))
    fails('security',lambda:m._security(fd))


def test_no_operational_entrypoint_credentials_or_JSON_body_semantics_in_helper():
    source=inspect.getsource(m)
    assert 'if __name__' not in source and 'requests.' not in source and 'load_key(' not in source
    assert '_load_plain' not in source and '_catalog(' not in source and 'subprocess.' not in source
    for function in (m.PayloadSourceGuard.authenticate_all,m.PayloadSourceGuard.copy_next,m.verify_archive_fd):
        code=inspect.getsource(function);assert 'json.loads' not in code and 'parse(' not in code
