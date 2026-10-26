"""Synthetic own-job results; exact expected FD-size before body I/O."""
from datetime import timedelta
import importlib.util
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_result_reader_successor as d

reader,e=d.reader,d.e
ACTUAL_LANE=d.LANE
spec=importlib.util.spec_from_file_location('synthetic_result_reader_successor_fixture',Path(__file__).with_name('test_qc_extended_result_driver.py'))
rf=importlib.util.module_from_spec(spec);spec.loader.exec_module(rf)


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*a,**kw):raise AssertionError('actual private, credential, subprocess or network forbidden')
    monkeypatch.setattr(reader.ops,'credential',denied)
    monkeypatch.setattr(reader.ops.http.client,'HTTPSConnection',denied)
    monkeypatch.setattr(reader.ops.Operations,'__init__',denied)
    monkeypatch.setattr(d.subprocess,'run',denied)
    opening=reader._open_directory
    def external(path):
        if path==ACTUAL_LANE or path.is_relative_to(ACTUAL_LANE):denied()
        return opening(path)
    monkeypatch.setattr(reader,'_open_directory',external)


def setup(tmp_path,*,action='diagnostics',compile_failure=False):
    old_plan,sources,root,data,clock=rf.setup(tmp_path,action=action,compile_failure=compile_failure)
    base=Path(__file__).resolve().parents[2]
    for name in d._PINS:sources[name]=(base/name).read_bytes()
    sources[d.SOURCE_RELATIVE]=b'# synthetic committed result-reader successor\n'
    arguments={key:old_plan[key] for key in d._ARGS if key!='source_hashes'}
    arguments.update(read_operation_id='TPR-EXT26-RESULT-V2-SYNTHETIC-001',
        source_hashes={name:reader._sha(raw) for name,raw in sources.items()})
    return d._plan(**arguments),sources,root,data,clock


def execute(fixture,**changed):
    plan,sources,root,_,clock=fixture
    return e.parse_json(d._execute(plan,sources,root,clock=changed.pop('clock',lambda:clock),guard=changed.pop('guard',lambda *a:None),**changed))


@pytest.mark.parametrize('action,failure,count',[('diagnostics',False,9),('diagnostics',True,5),('metrics',False,17)])
def test_new_result_claim_preserves_job_binding_and_original_full_metrics(tmp_path,action,failure,count):
    fixture=setup(tmp_path,action=action,compile_failure=failure);result=execute(fixture)
    assert result['status']=='COMPLETED' and result['scope_spent'] is True
    assert len(result['read_inventory'])==count and result['read_bytes'].fraction()==sum(map(len,fixture[3].values()))
    assert result['predecessor_reader_sha256']==d.READER_SHA256
    assert result['strict_inventory_source_sha256']==d.INVENTORY_SUCCESSOR_SHA256
    assert result['body_budget_and_expected_size_enforced_before_read'] is True
    assert result['new_looks'].fraction()==result['quantconnect_attempts'].fraction()==0
    assert result['canonical_admission'] is result['trading'] is False
    if action=='metrics':
        assert result['metrics']['nav_metrics']['observations'].fraction()==1449
        assert result['metrics']['execution_metrics']['complete_reported_fees_usd'] is None
        assert result['metrics']['execution_metrics']['complete_reported_gross_turnover_decimal'] is None
        assert result['metrics']['strategy_accepted'] is False and len(result['private_output_hashes'])==2
    else:assert result['metrics'] is None
    assert b'SECRET' not in e.canonical(result) and b'PRIVATE-TICKER' not in e.canonical(result)
    assert not list(fixture[2].glob('TPR-EXT26-RESULT-SYNTHETIC-*.claim.spent.json'))
    with pytest.raises(FileExistsError):execute(fixture)


@pytest.mark.parametrize('field,value',[('read_operation_id','TPR-EXT26-RESULT-SYNTHETIC-001'),
    ('strict_read_policy','post-body-check'),('predecessor_reader_sha256','0'*64),('max_total_bytes',999999999)])
def test_scope_tamper_or_old_claim_names_refuse_before_any_read(tmp_path,field,value):
    fixture=setup(tmp_path);fixture[0][field]=value
    with pytest.raises(ValueError):execute(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))


@pytest.mark.parametrize('name',list(d._PINS)+[d.SOURCE_RELATIVE])
def test_exact_old_and_new_source_closure_cannot_be_omitted(tmp_path,name):
    fixture=setup(tmp_path);arguments={key:fixture[0][key] for key in d._ARGS};arguments['source_hashes']=dict(arguments['source_hashes'])
    arguments['source_hashes'].pop(name)
    with pytest.raises(ValueError):d._plan(**arguments)


def test_expired_head_advance_or_modified_source_refuses_before_claim(tmp_path):
    fixture=setup(tmp_path)
    with pytest.raises(ValueError):execute(fixture,clock=lambda:fixture[4]+timedelta(days=3))
    with pytest.raises(ValueError):execute(fixture,guard=lambda *a:d._fail())
    fixture[1][d.SOURCE_RELATIVE]+=b'# changed\n'
    with pytest.raises(ValueError):execute(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))


def bounded_file(tmp_path):
    root=tmp_path/'bound';root.mkdir(mode=0o700);body=root/'bounded.json';body.write_bytes(b'0'*10);body.chmod(0o600)
    directory=reader._open_directory(root)
    reader._publish(directory,'synthetic-exact-size.claim.spent.json',e.canonical({'expected_size':10,'remaining':20,'scope':'synthetic-only'}))
    return directory,body,{'sha256':reader._sha(b'0'*10),'bytes':10}


@pytest.mark.parametrize('new_size',[9,11])
def test_exact_expected10_changed_before_open_reads_zero_body_bytes(tmp_path,monkeypatch,new_size):
    directory,body,expected=bounded_file(tmp_path);opening,reading=d.os.open,d.os.read;reads=[]
    def changed_before_open(name,*a,**kw):
        if name=='bounded.json':body.write_bytes(b'0'*new_size);body.chmod(0o600)
        return opening(name,*a,**kw)
    def counted(fd,count):
        raw=reading(fd,count);reads.append(len(raw));return raw
    monkeypatch.setattr(d.os,'open',changed_before_open);monkeypatch.setattr(d.os,'read',counted)
    try:
        with pytest.raises(ValueError):d._read_bound(directory,'bounded.json',expected,20)
        assert reads==[]
    finally:os.close(directory)


def test_exact_expected_size_above_remaining_refuses_before_open(tmp_path,monkeypatch):
    monkeypatch.setattr(d.os,'open',lambda *a,**kw:pytest.fail('body budget exceeded before opening'))
    with pytest.raises(ValueError):d._read_bound(None,'bounded.json',{'sha256':'a'*64,'bytes':10},9)


@pytest.mark.parametrize('change',['grow','shrink','same_size_hash','mode'])
def test_change_after_expected_fd_size_validation_stays_bounded_and_refuses(tmp_path,monkeypatch,change):
    directory,body,expected=bounded_file(tmp_path);reading=d.os.read;reads=[];changed=False
    def altered_before_read(fd,count):
        nonlocal changed
        if not changed:
            changed=True
            if change=='grow':body.write_bytes(b'0'*11)
            elif change=='shrink':body.write_bytes(b'0'*9)
            elif change=='same_size_hash':body.write_bytes(b'1'*10)
            else:body.chmod(0o644)
        raw=reading(fd,count);reads.append(len(raw));return raw
    monkeypatch.setattr(d.os,'read',altered_before_read)
    try:
        with pytest.raises(ValueError):d._read_bound(directory,'bounded.json',expected,20)
        assert sum(reads)<=10
    finally:os.close(directory)


@pytest.mark.parametrize('fault',['expected_size','expected_hash','mode','missing','symlink','hardlink','fifo'])
def test_failed_result_access_keeps_claim_and_null_metrics(tmp_path,fault):
    fixture=setup(tmp_path);role='operations_manifest';target=fixture[2]/reader._names(fixture[0]['candidate_id'],1,fixture[0]['qc_operation_id'],'diagnostics',True,0,0)[role]
    if fault=='expected_size':fixture[0]['inventory'][role]['bytes']+=1
    elif fault=='expected_hash':fixture[0]['inventory'][role]['sha256']='0'*64
    elif fault=='mode':target.chmod(0o644)
    elif fault=='missing':target.unlink()
    elif fault=='symlink':target.unlink();target.symlink_to(fixture[2]/'absent')
    elif fault=='hardlink':os.link(target,fixture[2]/'duplicate')
    else:target.unlink();os.mkfifo(target,0o600)
    result=execute(fixture)
    assert result['status']=='FAILED_OR_UNCERTAIN' and result['scope_spent'] is True
    assert result['metrics'] is result['diagnostic'] is None and result['read_bytes'].fraction()==0
    assert result['failed_read_body_bytes_unknown'] is True


def test_descriptor_stat_and_body_reads_follow_fresh_claim(tmp_path,monkeypatch):
    fixture=setup(tmp_path);original=d.os.fstat;claim=fixture[2]/(fixture[0]['read_operation_id']+'.claim.spent.json')
    def observing(fd):
        observed=original(fd)
        import stat
        if stat.S_ISREG(observed.st_mode):assert claim.exists()
        return observed
    monkeypatch.setattr(d.os,'fstat',observing)
    assert execute(fixture)['status']=='COMPLETED'


def test_foreign_job_rebound_hash_inventory_does_not_invent_lineage(tmp_path):
    fixture=setup(tmp_path);body=e.parse_json(fixture[3]['terminal']);body['request']['backtestId']='foreign-job'
    raw=e.canonical(body);target=fixture[2]/reader._names(fixture[0]['candidate_id'],1,fixture[0]['qc_operation_id'],'diagnostics',True,0,0)['terminal']
    target.write_bytes(raw);target.chmod(0o600);fixture[0]['inventory']['terminal']={'sha256':reader._sha(raw),'bytes':len(raw)}
    result=execute(fixture);assert result['status']=='FAILED_OR_UNCERTAIN' and result['metrics'] is None


def test_cli_explicit_inventory_hash_and_failure_sanitization(monkeypatch,capsys):
    def fail(**kw):raise ValueError('SECRET-TOKEN PRIVATE-ROW NEVER PRINT')
    monkeypatch.setattr(d,'run_result',fail)
    inventory=e.canonical({}).decode()
    args=['--read-operation-id','TPR-EXT26-RESULT-V2-SYNTHETIC-001','--qc-operation-id','synthetic-operation-001',
        '--candidate-id',rf.nf.CANDIDATE,'--attempt','1','--project-id','123','--backtest-id','none','--action','diagnostics',
        '--inventory-json',inventory,'--inventory-sha256',reader._sha(inventory.encode()),
        '--owner-instruction-sha256','f'*64,'--created-utc','2026-10-10T00:00:00Z','--expires-utc','2026-10-11T00:00:00Z']
    assert d.main(args)==1
    raw=capsys.readouterr().out.encode();assert b'SECRET' not in raw and b'PRIVATE' not in raw
    assert set(e.parse_json(raw))=={'status','scope_spent','automatic_retry'}
