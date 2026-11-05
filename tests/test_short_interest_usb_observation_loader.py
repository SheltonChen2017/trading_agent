"""Fabricated historical evidence only; never actual private artifacts or USB."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import ModuleType,SimpleNamespace

import pytest

REPO=Path(__file__).resolve().parents[1]
DRIVER='scripts/load_short_interest_usb_observation.py'
MODEL='research/short_interest_etf/firstrate_retained_qualification.py'
ANCHOR='research/short_interest_etf/specs/usb_observation_anchor_20261104_v1.json'
HEAD,REMOTE='a'*40,'b'*40


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def stamp(info):return tuple(getattr(info,key) for key in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))+(getattr(info,'st_flags',0),)


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    root=tmp_path.resolve();directory=root/'history'/'si-usb-offline-once-20261104-v1';directory.mkdir(parents=True,mode=0o700)
    (root/'history').chmod(0o700);monkeypatch.chdir(root)
    raw=(REPO/DRIVER).read_bytes();pure=(REPO/MODEL).read_bytes();anchor=json.loads((REPO/ANCHOR).read_bytes())
    historical={name:(REPO/name).read_bytes() for name in anchor['historical_runtime']['source_code_mapping']}
    # Reuse only the public fabricated aggregate fixture, never actual values.
    spec=importlib.util.spec_from_file_location('_retained_public_test_support',REPO/'tests/test_firstrate_retained_qualification.py')
    support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
    model=ModuleType('_retained_fake_model');exec(compile(pure,'<public-pure-model>','exec'),model.__dict__)
    aggregate=support.aggregate(model);aggregate_raw=canonical(aggregate)
    history=anchor['historical_runtime'];history['physical_root']=str(root)
    owned=anchor['original_owned_observation'];proof=anchor['original_profile_proof']
    proof['inspection_report_sha256']=digest(aggregate_raw);proof['observation_sha256']=digest(canonical({k:v for k,v in proof.items() if k!='observation_sha256'}))
    owned.update(private_model_aggregate_sha256=digest(aggregate_raw),private_model_aggregate_bytes=len(aggregate_raw))
    closed={'finite_offline_byte_inspection_only':True,**{key:False for key in ('source_qualified','source_admitted','protected_source_custody_verified','denominator_admitted','actual_input_admitted','ready_for_backtest','QC_or_Safari')},**{key:0 for key in ('provider_HTTP','source_credential_reads','new_claims','new_STARTs','new_charged_bytes','outcome_looks','qc_attempts')}}
    packet={'schema':'si-usb-once-envelope-v1','status':'closed_finite_offline_byte_inspection','invocation_id':owned['invocation_id'],
        'runtime_head':owned['runtime_head'],'matching_remote':owned['matching_remote'],'original_profile_proof':proof,
        'private_model_aggregate':aggregate,'source_qualified':False,'first_failure':None,'cleanup_failures':[],
        'denials':{key:0 for key in ('python_write_attempts','python_socket_attempts','forbidden_read_open_attempts','unexpected_subprocess_attempts')},
        'code_manifest_sha256':owned['producer_code_manifest_sha256'],'authority':closed}
    packet_raw=canonical(packet)+b'\n';owned.update(original_stdout_sha256=digest(packet_raw),retained_stdout_sha256=digest(packet_raw),stdout_bytes_observed=len(packet_raw),stdout_bytes_retained=len(packet_raw))
    anchor['original_owned_observation_sha256']=digest(canonical(owned))
    saved={'schema':'si-usb-observation-private-copy-v1','runtime_head':owned['runtime_head'],'matching_remote':owned['matching_remote'],
        'invocation_id':owned['invocation_id'],'process_claims':'caller_attested_historical_copy_not_independently_observed',
        'original_stdout_bytes':len(packet_raw),'original_stdout_sha256':digest(packet_raw),'owned_observation':owned,'source_authority':False}
    contents={'producer.stdout.private':packet_raw,'observation.private.json':canonical(saved)}
    for name,content in contents.items():(directory/name).write_bytes(content);(directory/name).chmod(0o600)
    files={name:{'bytes':len(content),'sha256':digest(content),'original_file10_sha256':digest(canonical(list(stamp((directory/name).stat()))))} for name,content in contents.items()}
    paths=list(reversed(directory.parents))+[directory]
    chain=[[info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode] for info in (path.stat() for path in paths)]
    for field in ('private_artifacts','original_copier_receipt','original_independent_audit'):
        anchor[field].update(files=files,directory5_sha256=digest(canonical(chain[-1])),ancestry5_sha256=digest(canonical(chain)))
    anchor['private_artifacts']['fixed_run']=str(directory)
    shared=tuple((p.stat().st_dev,p.stat().st_ino) for p in root.parents)
    h=SimpleNamespace(root=root,directory=directory,anchor=anchor,contents=contents,historical=historical,calls=[],after_mid=None,after_final=None,ls_count=0)
    def install(changed=None):
        if changed is not None:h.anchor=changed
        anchor_raw=canonical(h.anchor)+b'\n';tree=ast.parse(raw)
        replacements={'ROOT':'Path('+repr(str(root))+')','DIRECTORY':'Path('+repr(str(directory))+')','ANCHOR_SHA256':repr(digest(anchor_raw))}
        for node in tree.body:
            if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in replacements:
                node.value=ast.parse(replacements[node.targets[0].id],mode='eval').body
            if isinstance(node,ast.FunctionDef) and node.name=='_dir':
                # Explicit fixed shared-system-ancestor seam; every owned path
                # and all original file10 comparisons remain real and strict.
                gate=node.body[0].value.args[0]
                node.body[0].value.args[0]=ast.BoolOp(op=ast.Or(),values=[ast.parse('(info.st_dev,info.st_ino) in '+repr(shared),mode='eval').body,gate])
        body=(ast.unparse(ast.fix_missing_locations(tree))+'\n').encode()
        h.code={DRIVER:body,MODEL:pure,ANCHOR:anchor_raw}
        for name,content in h.code.items():path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        q=ModuleType('_fabricated_usb_loader');q.__file__=str(root/DRIVER);exec(compile(body,q.__file__,'exec'),q.__dict__);h.q=q
        h.ls_count=0;return q
    h.install=install;install()
    def run(arguments,**kwargs):
        assert arguments[0]=='git' and kwargs['cwd']==root and kwargs['stdin'] is None
        assert kwargs['env']=={'PATH':'/usr/bin:/bin','GIT_OPTIONAL_LOCKS':'0'}
        h.calls.append(arguments[1:]);args=arguments[1:];out=b'';status=0
        if args[0]=='show':
            revision,name=args[1].split(':',1);collection=h.code if revision==HEAD else historical
            if name not in collection:status=1
            else:out=collection[name]
        elif args==['rev-parse','--show-toplevel']:out=str(root).encode()
        elif args==['branch','--show-current']:out=b'codex/strategy-short-interest'
        elif args==['rev-parse','HEAD']:out=HEAD.encode()
        elif args[0]=='status':out=b''
        elif args[0]=='merge-base':out=b''
        elif args[0]=='ls-remote':
            h.ls_count+=1
            if h.ls_count==2 and h.after_mid:h.after_mid(h)
            if h.ls_count==3 and h.after_final:h.after_final(h)
            out=(REMOTE+'\trefs/heads/codex/strategy-short-interest').encode()
        else:out=REMOTE.encode()
        return SimpleNamespace(returncode=status,stdout=out,stderr=b'')
    monkeypatch.setattr(subprocess,'run',run);return h


def result(h):
    try:return h.q.qualify_registered_observation(HEAD,REMOTE),None
    except BaseException as error:return None,h.q.failure_summary(error)


def test_genuine_fabricated_history_closes_without_source_or_live_process_authority(prepared):
    h=prepared;value,negative=result(h);assert value is not None,negative
    public=value.public_summary();private=json.loads(value.canonical_bytes())
    assert public['status']=='closed_authenticated_historical_metadata_only' and public['first_failure'] is None
    assert private['assessment']['inspection_aggregate']['full']['rows']==6
    assert value.sha256==digest(value.canonical_bytes())
    assert b'quarantine_dispositions_retained' not in canonical(public)
    assert all(item is False or type(item) is int and item==0 for key,item in public['authority'].items() if key!='historical_observation_only')
    assert not any(hasattr(value,name) for name in ('iter_rows','iter_cells','source_lease','execution_inputs'))
    assert h.q.ALIAS not in sys.modules


def test_anchor_must_be_committed_before_any_private_open(prepared,monkeypatch):
    h=prepared;del h.code[ANCHOR];opened=[];real=os.open
    def opening(path,*args,**kwargs):
        if str(path) in (*h.q.NAMES,h.directory.name):opened.append(path)
        return real(path,*args,**kwargs)
    monkeypatch.setattr(os,'open',opening);value,negative=result(h)
    assert value is None and negative['status']=='incomplete' and not opened


@pytest.mark.parametrize('change',['ordered','hash','owned','proof','authority','process'])
def test_counterfactual_anchor_cannot_relabel_historical_lineage(prepared,change):
    h=prepared;a=copy.deepcopy(h.anchor)
    if change=='ordered':a['historical_runtime']['execution9_path_list'].reverse()
    elif change=='hash':a['historical_runtime']['source_code_mapping'][next(iter(a['historical_runtime']['source_code_mapping']))]='f'*64
    elif change=='owned':a['original_owned_observation']['source_qualified']=True
    elif change=='proof':a['original_profile_proof']['inspection_report_sha256']='f'*64
    elif change=='authority':a['original_profile_proof']['authority']['source_admitted']=True
    else:a['original_local_process_closures'][0]['exit_code']=True
    h.install(a);value,negative=result(h);assert value is None and negative['first_failure']['phase']=='anchor'


@pytest.mark.parametrize('change',['mtime','mode','extra','replacement','ancestor'])
def test_final_private_audit_vetoes_drift_during_last_git_guard(prepared,change):
    h=prepared
    def drift(h):
        path=h.directory/h.q.NAMES[0];info=path.stat()
        if change=='mtime':os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1))
        elif change=='mode':path.chmod(0o640)
        elif change=='extra':(h.directory/'unexpected').write_bytes(b'not a source row')
        elif change=='replacement':raw=path.read_bytes();path.unlink();path.write_bytes(raw);path.chmod(0o600)
        else:
            parent=h.directory.parent;moved=parent.with_name('original-history');parent.rename(moved);parent.symlink_to(moved,target_is_directory=True)
    h.after_final=drift;value,negative=result(h)
    assert value is None and h.ls_count==3 and negative['first_failure']['phase']=='final'


def test_flags_only_drift_is_not_rebased(prepared,monkeypatch):
    h=prepared;inode=(h.directory/h.q.NAMES[0]).stat().st_ino;drift=[False];fstat,stat_fn,lstat=os.fstat,os.stat,os.lstat
    class Info:
        def __init__(self,value):self.value=value
        def __getattr__(self,name):return getattr(self.value,name)
        @property
        def st_flags(self):return getattr(self.value,'st_flags',0)^(1 if drift[0] and self.value.st_ino==inode else 0)
    monkeypatch.setattr(os,'fstat',lambda fd:Info(fstat(fd)))
    monkeypatch.setattr(os,'stat',lambda *a,**k:Info(stat_fn(*a,**k)))
    monkeypatch.setattr(os,'lstat',lambda *a,**k:Info(lstat(*a,**k)))
    h.after_final=lambda unused:drift.__setitem__(0,True);value,negative=result(h)
    assert value is None and negative['first_failure']['code']=='stamp'


def test_close_failure_preserves_negative_and_independent_cleanup(prepared,monkeypatch):
    h=prepared;opened=set();real_open,real_close=os.open,os.close;failed=[False]
    def opening(*args,**kwargs):fd=real_open(*args,**kwargs);opened.add(fd);return fd
    def closing(fd):
        real_close(fd);opened.discard(fd)
        if not failed[0]:failed[0]=True;raise OSError('PRIVATE close failure')
    monkeypatch.setattr(os,'open',opening);monkeypatch.setattr(os,'close',closing)
    value,negative=result(h);assert value is None and not opened and negative['first_failure']['phase']=='close'
    assert 'PRIVATE' not in json.dumps(negative)


@pytest.mark.parametrize('field',['authority','authority_counter_bool','denials','proof','proof_counter_bool','aggregate','wrapper','wrapper_counter_bool'])
def test_strict_private_packet_relationships_do_not_accept_counterfactuals(prepared,field):
    h=prepared;q=h.q;bodies=dict(h.contents);packet=json.loads(bodies[q.NAMES[0]])
    if field=='authority':packet['authority']['source_admitted']=True
    elif field=='authority_counter_bool':packet['authority']['provider_HTTP']=False
    elif field=='denials':packet['denials']['python_write_attempts']=False
    elif field=='proof':packet['original_profile_proof']['executed_verified_RAM']=False
    elif field=='proof_counter_bool':packet['original_profile_proof']['authority']['provider_HTTP']=False
    elif field=='aggregate':packet['private_model_aggregate']['scope']='not the original aggregate'
    else:
        saved=json.loads(bodies[q.NAMES[1]])
        if field=='wrapper_counter_bool':saved['owned_observation']['actual_exit_code']=False
        else:saved['unknown']=True
        bodies[q.NAMES[1]]=canonical(saved)
    bodies[q.NAMES[0]]=canonical(packet)+b'\n'
    with pytest.raises(q.UsbObservationRefusal):q._packet(bodies,h.anchor)


@pytest.mark.parametrize('change',['entry','getter','property','class'])
def test_original_pure_bindings_are_checked_after_assessment_and_during_closure(prepared,change):
    h=prepared
    def substitute(h):
        model=sys.modules[h.q.ALIAS]
        if change=='entry':model.evaluate_retained_aggregate=lambda raw:None
        elif change=='getter':model.RetainedAggregateAssessment.canonical_bytes.__code__=(lambda value:b'{}').__code__
        elif change=='property':model.RetainedAggregateAssessment.sha256.fget.__code__=(lambda value:'0'*64).__code__
        else:model.RetainedAggregateAssessment=type('Replacement',(),{})
    h.after_mid=substitute;value,negative=result(h)
    assert value is None and negative['first_failure']=={'phase':'close','code':'model_changed'}


@pytest.mark.parametrize('ordinal',[1,4])
def test_early_fstat_failure_closes_every_owned_descriptor(prepared,monkeypatch,ordinal):
    h=prepared;opened=set();real_open,real_close,real_fstat=os.open,os.close,os.fstat;calls=[0]
    def opening(*args,**kwargs):fd=real_open(*args,**kwargs);opened.add(fd);return fd
    def closing(fd):real_close(fd);opened.discard(fd)
    def failing(fd):
        calls[0]+=1
        if calls[0]==ordinal:raise OSError('PRIVATE fstat failure')
        return real_fstat(fd)
    monkeypatch.setattr(os,'open',opening);monkeypatch.setattr(os,'close',closing);monkeypatch.setattr(os,'fstat',failing)
    value,negative=result(h);assert value is None and not opened and 'PRIVATE' not in json.dumps(negative)


def test_forged_or_copied_metadata_report_cannot_become_an_issued_object(prepared):
    h=prepared;value,negative=result(h);assert value is not None,negative
    with pytest.raises(h.q.UsbObservationRefusal):h.q.ClosedRetainedUsbQualification()
    copied=object.__new__(h.q.ClosedRetainedUsbQualification);copied._anchor=value._anchor
    h.q._ISSUED[id(copied)]=tuple([copied,*value._anchor[1:]])
    with pytest.raises(h.q.UsbObservationRefusal):copied.public_summary()
    assert value.public_summary()['authority']['source_admitted'] is False


def test_report_failure_is_permanent_even_after_registry_row_restored(prepared):
    h=prepared;value,negative=result(h);assert value is not None,negative
    original=value._anchor;bad=tuple(list(original));value._anchor=bad
    with pytest.raises(h.q.UsbObservationRefusal):value.canonical_bytes()
    value._anchor=original
    with pytest.raises(h.q.UsbObservationRefusal):value.canonical_bytes()


def test_clock_start_cannot_be_rebased_after_original_context_closure(prepared,monkeypatch):
    now=[0];monkeypatch.setattr(prepared.q.time,'monotonic_ns',lambda:now[0]);value,negative=result(prepared);assert value is not None,negative
    clock=value._anchor[5];now[0]=31*10**9;clock.start=clock.last=now[0]
    with pytest.raises(prepared.q.UsbObservationRefusal,match='clock'):clock.check()


def test_actual_cli_serialization_is_inside_original_deadline(prepared,monkeypatch,capsys):
    h=prepared;now=[0];count=[0];original=h.q.json.dumps
    monkeypatch.setattr(h.q.time,'monotonic_ns',lambda:now[0])
    def dumps(value,*args,**kwargs):
        if type(value) is dict and value.get('schema')=='si-retained-usb-qualification-summary-v1' and value.get('status')=='closed_authenticated_historical_metadata_only':
            count[0]+=1
            if count[0]==3:now[0]=31*10**9
        return original(value,*args,**kwargs)
    monkeypatch.setattr(h.q.json,'dumps',dumps);assert h.q.main([HEAD,REMOTE])==2
    packet=json.loads(capsys.readouterr().out);assert count[0]==3 and packet['status']=='incomplete'
    assert packet['first_failure']=={'phase':'final_format','code':'clock'}


def test_issuance_serialization_expiry_keeps_honest_phase_and_original_negative(prepared,monkeypatch):
    h=prepared;now=[0];original=h.q.json.dumps;reached=[False]
    monkeypatch.setattr(h.q.time,'monotonic_ns',lambda:now[0])
    def dumps(value,*args,**kwargs):
        raw=original(value,*args,**kwargs)
        if type(value) is dict and value.get('schema')=='si-authenticated-historical-usb-qualification-v1':
            reached[0]=True;now[0]=31*10**9
        return raw
    monkeypatch.setattr(h.q.json,'dumps',dumps);value,negative=result(h)
    assert reached[0] and value is None and negative['first_failure']=={'phase':'issue','code':'clock'}


@pytest.mark.parametrize('genuine',[False,True])
def test_negative_authority_is_original_even_when_current_authority_code_changes(prepared,genuine):
    h=prepared;expected=h.q.authority();original=h.q.authority.__code__
    h.q.authority.__code__=(lambda:{'historical_observation_only':True,'source_admitted':True,'private':'PRIVATE'}).__code__
    try:
        if genuine:
            value,negative=result(h);assert value is None and negative['first_failure']['code']=='code'
        else:negative=h.q.failure_summary(h.q.UsbObservationRefusal('code'))
        assert negative['authority']==expected and 'PRIVATE' not in json.dumps(negative)
    finally:h.q.authority.__code__=original


def test_final_format_authority_mutation_veto_uses_closed_projection_and_latches_report(prepared,monkeypatch,capsys):
    h=prepared;expected=h.q.authority();code=h.q.authority.__code__;dumps=h.q.json.dumps;count=[0]
    def serialize(value,*args,**kwargs):
        raw=dumps(value,*args,**kwargs)
        if type(value) is dict and value.get('schema')=='si-retained-usb-qualification-summary-v1' and value.get('status')=='closed_authenticated_historical_metadata_only':
            count[0]+=1
            if count[0]==3:h.q.authority.__code__=(lambda:{'historical_observation_only':True,'source_admitted':True}).__code__
        return raw
    monkeypatch.setattr(h.q.json,'dumps',serialize)
    try:
        assert h.q.main([HEAD,REMOTE])==2
        negative=json.loads(capsys.readouterr().out)
        assert negative['first_failure']=={'phase':'final_format','code':'code'} and negative['authority']==expected
    finally:h.q.authority.__code__=code
    value=next(iter(h.q._ISSUED.values()))[0]
    with pytest.raises(h.q.UsbObservationRefusal):value.canonical_bytes()


def test_bad_cli_arguments_never_echo_values(prepared,capsys):
    assert prepared.q.main(['PRIVATE/path',REMOTE])==2
    assert 'PRIVATE' not in capsys.readouterr().out


def test_attempt_failure_cannot_be_restarted_by_resetting_public_used_flag(prepared):
    h=prepared;h.q._USED=True;value,negative=result(h);assert value is None
    h.q._USED=False;value,negative=result(h)
    # A first refusal before an attempt is registered has no data access; an
    # actual completed attempt is independently retained by _ATTEMPTS.
    assert value is not None,negative
    h.q._USED=False;value,negative=result(h);assert value is None and negative['first_failure']['code']=='spent'
