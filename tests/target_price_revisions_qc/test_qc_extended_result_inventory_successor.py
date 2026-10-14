"""Strict prospective byte-budget proofs with external synthetic files only."""
from datetime import timedelta
import importlib.util
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_result_inventory_successor as d

reader, e, prior = d.reader, d.e, d.predecessor
ACTUAL_LANE = d.LANE
spec = importlib.util.spec_from_file_location('synthetic_inventory_successor_fixture', Path(__file__).with_name('test_qc_extended_result_inventory.py'))
rf = importlib.util.module_from_spec(spec); spec.loader.exec_module(rf)


@pytest.fixture(autouse=True)
def forbidden_actual(monkeypatch):
    def denied(*a, **kw): raise AssertionError('actual private, credential, subprocess or network operation forbidden')
    monkeypatch.setattr(reader.ops, 'credential', denied)
    monkeypatch.setattr(reader.ops.http.client, 'HTTPSConnection', denied)
    monkeypatch.setattr(reader.ops.Operations, '__init__', denied)
    monkeypatch.setattr(d.subprocess, 'run', denied)
    opening = reader._open_directory
    def external(path):
        if path == ACTUAL_LANE or path.is_relative_to(ACTUAL_LANE): denied()
        return opening(path)
    monkeypatch.setattr(reader, '_open_directory', external)


def setup(tmp_path, *, action='diagnostics', compile_failure=False):
    old_plan, sources, root, data, clock = rf.setup(tmp_path, action=action, compile_failure=compile_failure)
    # Exact public executed predecessor bytes are not a private capture/result.
    sources[prior.SOURCE_RELATIVE] = (Path(__file__).resolve().parents[2] / prior.SOURCE_RELATIVE).read_bytes()
    sources[d.SOURCE_RELATIVE] = b'# synthetic committed successor source\n'
    arguments = {key: old_plan[key] for key in d._ARGS if key != 'source_hashes'}
    arguments.update(read_operation_id='TPR-EXT26-INVENTORY-V2-SYNTHETIC-001',
        source_hashes={name: reader._sha(raw) for name, raw in sources.items()})
    plan = d._plan(**arguments)
    return plan, sources, root, data, clock


def execute(fixture, **changed):
    plan, sources, root, _, clock = fixture
    return e.parse_json(d._execute(plan, sources, root, clock=changed.pop('clock', lambda: clock), guard=changed.pop('guard', lambda *a: None), **changed))


@pytest.mark.parametrize('action,failure,count', [('diagnostics',False,9),('diagnostics',True,5),('metrics',False,17)])
def test_successor_binds_same_own_job_with_new_hash_and_fresh_claim(tmp_path, action, failure, count):
    fixture = setup(tmp_path, action=action, compile_failure=failure); result = execute(fixture)
    assert result['status'] == 'COMPLETED' and result['scope_spent'] is True
    assert len(result['inventory']) == count and result['read_bytes'].fraction() == sum(map(len,fixture[3].values()))
    assert result['predecessor_sha256'] == d.PREDECESSOR_SHA256
    assert result['source_hashes'][d.SOURCE_RELATIVE] == reader._sha(fixture[1][d.SOURCE_RELATIVE])
    assert result['body_budget_enforced_before_read'] is True and result['own_job_lineage_verified'] is True
    assert result['native_collection_lineage_verified'] is (action == 'metrics')
    assert result['accounting_metrics_computed'] is result['canonical_admission'] is result['trading'] is False
    assert result['new_looks'].fraction() == result['quantconnect_attempts'].fraction() == 0
    assert not list(fixture[2].glob('TPR-EXT26-INVENTORY-SYNTHETIC-*.claim.spent.json'))
    with pytest.raises(FileExistsError): execute(fixture)


def test_predecessor_and_own_hashes_cannot_be_omitted_or_changed_in_plan(tmp_path):
    fixture=setup(tmp_path)
    for field in (prior.SOURCE_RELATIVE, d.SOURCE_RELATIVE):
        arguments={key:fixture[0][key] for key in d._ARGS};arguments['source_hashes']=dict(arguments['source_hashes'])
        arguments['source_hashes'].pop(field)
        with pytest.raises(ValueError): d._plan(**arguments)
    arguments={key:fixture[0][key] for key in d._ARGS};arguments['source_hashes']=dict(arguments['source_hashes'])
    arguments['source_hashes'][prior.SOURCE_RELATIVE]='0'*64
    with pytest.raises(ValueError): d._plan(**arguments)


@pytest.mark.parametrize('field,value',[('read_operation_id','TPR-EXT26-INVENTORY-SYNTHETIC-001'),('strict_read_policy','after-read-only'),
    ('predecessor_sha256','0'*64),('max_total_bytes',999999999),('files',{'operator':'operator-state.db'})])
def test_legacy_claim_or_scope_tamper_refuses_before_stat_or_body(tmp_path,field,value):
    fixture=setup(tmp_path);fixture[0][field]=value
    with pytest.raises(ValueError): execute(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))


def test_expired_moved_head_and_modified_sources_refuse_before_claim(tmp_path):
    fixture=setup(tmp_path)
    with pytest.raises(ValueError): execute(fixture,clock=lambda:fixture[4]+timedelta(days=3))
    with pytest.raises(ValueError): execute(fixture,guard=lambda *a:d._fail())
    fixture[1][d.SOURCE_RELATIVE]+=b'# changed\n'
    with pytest.raises(ValueError): execute(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))


def bounded_file(tmp_path):
    root=tmp_path/'bounded';root.mkdir(mode=0o700);body=root/'bounded.json'
    body.write_bytes(b'0'*10);body.chmod(0o600)
    directory=reader._open_directory(root)
    prior._FIXED_PUBLISH(directory,'synthetic-bounded.claim.spent.json',e.canonical({'remaining':10,'scope':'synthetic-only'}))
    return directory,body


def test_growth_between_check_and_open_never_reads_body_over_remaining(tmp_path,monkeypatch):
    directory,body=bounded_file(tmp_path);original_open,original_read=d.os.open,d.os.read;reads=[]
    def replaced_before_open(name,*a,**kw):
        if name=='bounded.json': body.write_bytes(b'0'*11);body.chmod(0o600)
        return original_open(name,*a,**kw)
    def counted(fd,count):
        raw=original_read(fd,count);reads.append(len(raw));return raw
    monkeypatch.setattr(d.os,'open',replaced_before_open);monkeypatch.setattr(d.os,'read',counted)
    try:
        with pytest.raises(ValueError): d._budgeted_read(directory,'bounded.json',10)
        assert reads==[]
    finally:os.close(directory)


@pytest.mark.parametrize('change',['grow','shrink','mode'])
def test_change_after_descriptor_validation_never_reads_more_than_validated_size(tmp_path,monkeypatch,change):
    directory,body=bounded_file(tmp_path);original_read=d.os.read;reads=[];changed=False
    def altered_before_read(fd,count):
        nonlocal changed
        if not changed:
            changed=True
            if change=='grow': body.write_bytes(b'0'*11)
            elif change=='shrink': body.write_bytes(b'0'*9)
            else: body.chmod(0o644)
        raw=original_read(fd,count);reads.append(len(raw));return raw
    monkeypatch.setattr(d.os,'read',altered_before_read)
    try:
        with pytest.raises(ValueError): d._budgeted_read(directory,'bounded.json',10)
        assert sum(reads)<=10
    finally:os.close(directory)


def test_changed_named_inode_after_open_refuses_before_any_body_read(tmp_path,monkeypatch):
    directory,body=bounded_file(tmp_path);original_fstat=d.os.fstat;changed=False
    def moved_name(fd):
        nonlocal changed
        observed=original_fstat(fd)
        if not changed:
            changed=True;replacement=body.with_name('replacement');replacement.write_bytes(b'1'*10);replacement.chmod(0o600);replacement.replace(body)
        return observed
    monkeypatch.setattr(d.os,'fstat',moved_name)
    monkeypatch.setattr(d.os,'read',lambda *a:pytest.fail('changed named inode body was read'))
    try:
        with pytest.raises(ValueError):d._budgeted_read(directory,'bounded.json',10)
    finally:os.close(directory)


@pytest.mark.parametrize('remaining',[0,-1,True,'10',d.MAX_TOTAL+1])
def test_invalid_remaining_budget_refuses_even_before_open(tmp_path,monkeypatch,remaining):
    monkeypatch.setattr(d.os,'open',lambda *a,**kw:pytest.fail('opened without valid remaining budget'))
    with pytest.raises(ValueError):d._budgeted_read(None,'bounded.json',remaining)


@pytest.mark.parametrize('fault',['missing','symlink','hardlink','mode','fifo','oversize','aggregate'])
def test_bad_private_custody_and_budget_remain_spent_without_inventory(tmp_path,monkeypatch,fault):
    fixture=setup(tmp_path);target=fixture[2]/fixture[0]['files']['operations_manifest']
    if fault=='missing':target.unlink()
    elif fault=='symlink':target.unlink();target.symlink_to(fixture[2]/'absent')
    elif fault=='hardlink':os.link(target,fixture[2]/'duplicate')
    elif fault=='mode':target.chmod(0o644)
    elif fault=='fifo':target.unlink();os.mkfifo(target,0o600)
    elif fault=='oversize':monkeypatch.setattr(d,'MAX_FILE',100)
    else:monkeypatch.setattr(d,'MAX_TOTAL',100)
    result=execute(fixture)
    assert result['status']=='FAILED_OR_UNCERTAIN' and result['scope_spent'] is True and result['inventory'] is None
    assert result['read_bytes'].fraction()==0 and result['read_attempts'].fraction()==1


def test_claim_precedes_descriptor_stat_and_body_reads(tmp_path,monkeypatch):
    fixture=setup(tmp_path);original=d.os.fstat;private_claim=fixture[2]/(fixture[0]['read_operation_id']+'.claim.spent.json')
    def observing(fd):
        stat_result=original(fd)
        # Directory custody fstat precedes the claim, file fstat never does.
        import stat
        if stat.S_ISREG(stat_result.st_mode):assert private_claim.exists()
        return stat_result
    monkeypatch.setattr(d.os,'fstat',observing)
    assert execute(fixture)['status']=='COMPLETED'


@pytest.mark.parametrize('fault',['foreign_terminal','foreign_page'])
def test_existing_independent_job_and_collection_bindings_are_preserved(tmp_path,fault):
    fixture=setup(tmp_path,action='metrics')
    role='terminal' if fault=='foreign_terminal' else 'orders_page_0';body=e.parse_json(fixture[3][role])
    body['request']['backtestId']='foreign-job';rf.rewrite(fixture,role,body)
    result=execute(fixture)
    assert result['status']=='FAILED_OR_UNCERTAIN' and result['inventory'] is None


def test_cli_sanitizes_failures_and_has_no_path_or_credential_options(monkeypatch,capsys):
    def refused(**kw):raise RuntimeError('SECRET-TOKEN PRIVATE-ROW NEVER PRINT')
    monkeypatch.setattr(d,'run_inventory',refused)
    args=['--read-operation-id','TPR-EXT26-INVENTORY-V2-SYNTHETIC-001','--qc-operation-id','synthetic-operation-001',
        '--candidate-id',rf.rf.nf.CANDIDATE,'--attempt','1','--project-id','123','--backtest-id','none','--action','diagnostics',
        '--owner-instruction-sha256','f'*64,'--created-utc','2026-10-10T00:00:00Z','--expires-utc','2026-10-11T00:00:00Z']
    assert d.main(args)==1
    raw=capsys.readouterr().out.encode();assert b'SECRET' not in raw and b'PRIVATE' not in raw
    assert set(e.parse_json(raw))=={'status','scope_spent','automatic_retry'}
