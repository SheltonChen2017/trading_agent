"""Supplied synthetic DATA and held-FD tests; no R346 private leaf is read."""
import copy
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import time

import pytest

from scripts import arv2_r347_plain_submission_data as m


PUBLIC_ROOT=Path(__file__).resolve().parents[2]
ANCESTOR='411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
LINEAGE='e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'


def refused(code,operation):
    with pytest.raises(m.Refused) as caught:operation()
    assert caught.value.args==(code,)


def test_exact_public_original_result_fact_has_six_payloads_and_eight_data_pins():
    raw=(PUBLIC_ROOT/'scripts/arv2_r346_preparation_result_fact.json').read_bytes()
    fact=m.parse_fact(raw)
    assert m.pin(raw)==m.FACT_PIN
    assert set(m.expected_files(fact))==set(m.NAMES)
    assert 'claim.json' not in m.expected_files(fact)
    assert fact['original_result']['report']['summary']['current_attempt_state']['R343-AR100']['attempts_consumed']==3
    assert fact['original_result']['report']['summary']['current_attempt_state']['R343-AR100']['A4_permitted'] is False


@pytest.mark.parametrize('change',[lambda raw:raw[:-1],lambda raw:raw+b'\n',lambda raw:b'not-json',
    lambda raw:raw.replace(b'"child_actual_exit":0',b'"child_actual_exit":2')])
def test_changed_public_fact_refuses_external_pin_before_json_parser(monkeypatch,change):
    raw=(PUBLIC_ROOT/'scripts/arv2_r346_preparation_result_fact.json').read_bytes()
    monkeypatch.setattr(m,'loads',lambda *a,**k:(_ for _ in ()).throw(AssertionError('parse before external pin')))
    refused('fact',lambda:m.parse_fact(change(raw)))


@pytest.fixture
def supplied():
    # Build a small canonical physical plain transport. The enclosing supplied
    # fact is deliberately synthetic, and is NOT accepted by parse_fact.
    payloads={m.OBJECT_NAMES[0]:m.canonical({'manifest_id':'synthetic-evaluator','manifest_sha256':'c'*64})+b'\n'}
    for name in m.OBJECT_NAMES[1:-1]:payloads[name]=m.canonical({'synthetic':name})+b'\n'
    descriptors=[]
    for role,name in zip(m.plain._ROLE_ORDER,m.OBJECT_NAMES[:-1],strict=True):
        raw=payloads[name]
        descriptors.append({'schema':m.plain.UPLOAD_OBJECT_SCHEMA,'role':role,'ordinal':0,
            'object_store_key':'placeholder/'+name,'relative_path':name,'byte_count':len(raw),
            'content_sha256':m.pin(raw)['sha256'],'record_count':1,'compression':'identity','activation_manifest':False})
    parent={'schema':m.plain.PARENT_PROOF_SCHEMA,'source_package_sha256':ANCESTOR,
        'source_lineage_sha256':LINEAGE,'source_activation_sha256':'d'*64,'source_activation_byte_count':100,
        'source_inventory_sha256':'e'*64,'streams':[{key:row[key] for key in m.plain._STREAM_FIELDS} for row in descriptors]}
    parent_sha=m.pin(m.canonical(parent))['sha256'];prefix='arv2/newrule-plain-v1/'+parent_sha[:24]+'/'
    for descriptor in descriptors:descriptor['object_store_key']=prefix+descriptor['relative_path']
    transport={'schema':m.plain.TRANSPORT_MANIFEST_SCHEMA,'package_id':None,'package_sha256':None,
        'evaluator_manifest_id':'synthetic-evaluator','evaluator_manifest_sha256':'c'*64,
        'benchmark':{'security_id':m.plain.BENCHMARK_SECURITY_ID,'ticker':m.plain.BENCHMARK_TICKER,
            'binding':'QC_US_equity_symbol_resolved_in_process'},
        'source_disposition_sha256':LINEAGE,'runtime_symbol_binding_count':1,
        'runtime_symbol_bindings_sha256':'f'*64,'contribution_census':{'synthetic':1},
        'objects':descriptors,'runtime':dict(m.plain._EXPECTED_RUNTIME),'claims':dict(m.plain._EXPECTED_CLAIMS),
        'parent_proof':parent,'parent_proof_sha256':parent_sha}
    digest=m.pin(m.canonical(transport))['sha256']
    transport.update(package_id='arv2-newrule-plain-package-'+digest[:24],package_sha256=digest)
    raw=m.canonical(transport)+b'\n';payloads[m.OBJECT_NAMES[-1]]=raw
    activation={'schema':m.plain.UPLOAD_OBJECT_SCHEMA,'role':'activation_manifest','ordinal':0,
        'object_store_key':prefix+m.OBJECT_NAMES[-1],'relative_path':m.OBJECT_NAMES[-1],
        'byte_count':len(raw),'content_sha256':m.pin(raw)['sha256'],'record_count':1,
        'compression':'identity','activation_manifest':True}
    cells=[];public=[]
    sources=[(f'module_{index:02d}.py',b'pass\n') for index in range(18)]
    for percent in (80,100,120,140,160,180,200):
        profile={'candidate_id':f'R343-AR{percent:03d}',
            'research_epoch_id':'R343-legacy-six-QCOM-restored-through-2026Oct13-v1',
            'source_package_sha256':ANCESTOR,'source_lineage_sha256':LINEAGE,'original_profile_sha256':'a'*64}
        profile['profile_sha256']=m.pin(m.canonical(profile))['sha256']
        row={'candidate_id':profile['candidate_id'],'ar_percent':percent,
            'unchanged_profile_pin':m.pin(m.canonical(profile)),'ancestral_source_package_sha256':ANCESTOR,
            'source_lineage_sha256':LINEAGE,'source_files':[{'project_path':name,**m.pin(body)} for name,body in sources]}
        public.append(row)
        cells.append({'candidate_id':profile['candidate_id'],'ar_percent':percent,'profile':profile,
            'source_pairs':[[name,body.decode('ascii')] for name,body in sources],'bridge_record':copy.deepcopy(row)})
    attempt={'R343-AR100':{'attempts_consumed':3,'A4_permitted':False},'attempt_budget_reset':False}
    summary={'actual_plain_package_sha256':digest,'parent_proof_sha256':parent_sha,
        'source_inventory_pin':{'byte_count':123,'sha256':'e'*64},'parent_source_vector_pin':{'byte_count':321,'sha256':'f'*64},
        'actual_activation':activation,'cells':public,'current_attempt_state':attempt,
        'object_files':[{'relative_path':name,**m.pin(payloads[name])} for name in m.OBJECT_NAMES]}
    binding={'synthetic_binding':'no operational authority'}
    proposal={'schema':m.preparation.SCHEMA+'-source-proposal','binding':binding,
        'parent_B_data_pin':dict(m.preparation.DATA_PIN),'source_inventory_pin':summary['source_inventory_pin'],
        'parent_source_vector_pin':summary['parent_source_vector_pin'],'parent_proof':parent,
        'actual_plain_package_sha256':digest,'actual_plain_activation':activation,
        'objects':[*descriptors,activation],'cells':cells,'current_attempt_state':attempt,**m.preparation.FLAGS}
    report={'summary':summary}
    payloads['source-proposal.json']=m.canonical(proposal)
    report['source_proposal_pin']=m.pin(payloads['source-proposal.json'])
    payloads['report.json']=m.canonical(report)
    fact={'binding':binding,'original_result':{'report':report,'report_pin':m.pin(payloads['report.json'])}}
    return payloads,fact,proposal


def republish_synthetic(supplied):
    """Rebind only explicitly synthetic supplied facts to reach inner checks."""
    files,fact,proposal=supplied
    report=fact['original_result']['report']
    files['source-proposal.json']=m.canonical(proposal)
    report['source_proposal_pin']=m.pin(files['source-proposal.json'])
    report['summary']['object_files']=[{'relative_path':name,**m.pin(files[name])} for name in m.OBJECT_NAMES]
    files['report.json']=m.canonical(report);fact['original_result']['report_pin']=m.pin(files['report.json'])


def test_real_transport_validation_joins_all_seven_vectors_but_exposes_only_immutable_AR100(supplied):
    files,fact,proposal=supplied
    value=m.validate_supplied(files,fact=fact)
    assert len(value.candidates)==1 and value.candidate.candidate_id=='R343-AR100'
    assert len(value.candidate.sources)==18 and len(value.uploads)==6
    assert [row.activation_manifest for row in value.uploads]==[False]*5+[True]
    assert json.loads(value.attempt_state_at_preparation_json)['R343-AR100']=={'attempts_consumed':3,'A4_permitted':False}
    identity=json.loads(value.source_identity_json)
    assert identity['actual_plain_package_sha256']!=identity['ancestral_source_package_sha256']
    assert identity['current_QC_admission_granted'] is identity['attempt_budget_reset'] is False
    before=value.candidate.cell_record();proposal['cells'][1]['source_pairs'][0][1]='changed'
    assert value.candidate.cell_record()==before
    before['source_pairs'][0][1]='changed-again'
    assert value.candidate.cell_record()!=before
    with pytest.raises(FrozenInstanceError):value.candidate.ar_percent=200
    assert 'synthetic-evaluator' not in repr(value)
    assert 'synthetic-evaluator' not in repr(value.uploads)


def test_all_eight_external_hashes_precede_any_private_parser(supplied,monkeypatch):
    files,fact,_=supplied;files['report.json']+=b' '
    monkeypatch.setattr(m,'loads',lambda *a,**k:(_ for _ in ()).throw(AssertionError('parser before hash')))
    refused('pin',lambda:m.validate_supplied(files,fact=fact))


@pytest.mark.parametrize('index',range(7))
def test_changed_source_in_any_of_seven_cells_refuses_even_outside_selected_AR100(supplied,index):
    files,fact,proposal=supplied
    proposal['cells'][index]['source_pairs'][0][1]='changed\n';republish_synthetic(supplied)
    refused('sources',lambda:m.validate_supplied(files,fact=fact))


@pytest.mark.parametrize('fault,code',[('binding','proposal'),('extra','proposal'),('ancestor','proposal'),
    ('parent','parent'),('package','objects'),('activation_order','objects'),('row_count','objects'),
    ('profile','profile'),('profile_hash','profile'),('attempt','proposal'),('cell_extra','sources')])
def test_closed_proposal_ancestry_profile_and_payload_joins_refuse_reached_fault(supplied,fault,code):
    files,fact,p=supplied
    if fault=='binding':p['binding']={'other':'not frozen'}
    elif fault=='extra':p['permission']=True
    elif fault=='ancestor':p['parent_B_data_pin']={'byte_count':1,'sha256':'a'*64}
    elif fault=='parent':p['parent_proof']['source_package_sha256']='a'*64
    elif fault=='package':
        manifest=json.loads(files['transport-manifest.json']);manifest['package_sha256']='0'*64
        files['transport-manifest.json']=m.canonical(manifest)+b'\n'
    elif fault=='activation_order':p['objects'][0],p['objects'][-1]=p['objects'][-1],p['objects'][0]
    elif fault=='row_count':files[m.OBJECT_NAMES[1]]+=b'\n'
    elif fault=='profile':p['cells'][1]['profile']['candidate_id']='R343-AR200'
    elif fault=='profile_hash':
        c=p['cells'][1];c['profile']['profile_sha256']='0'*64
        # Reach the inner self-hash predicate while only using synthetic pins.
        c['bridge_record']['unchanged_profile_pin']=m.pin(m.canonical(c['profile']))
        fact['original_result']['report']['summary']['cells'][1]['unchanged_profile_pin']=c['bridge_record']['unchanged_profile_pin']
    elif fault=='attempt':p['current_attempt_state']={'attempt_budget_reset':True}
    else:p['cells'][3]['new_field']=False
    republish_synthetic(supplied)
    refused(code,lambda:m.validate_supplied(files,fact=fact))


@pytest.mark.parametrize('key',sorted(m.preparation.FLAGS))
def test_no_preparation_flag_can_supply_new_operational_or_formal_authority(supplied,key):
    files,fact,p=supplied;p[key]=True;republish_synthetic(supplied)
    refused('proposal',lambda:m.validate_supplied(files,fact=fact))


@pytest.mark.parametrize('raw',[b'{"x":1,"x":1}',b'{"x":NaN}',b' {}',b'{}\n\n',b'\xff'])
def test_canonical_json_rejects_ambiguous_input(raw):refused('output',lambda:m.loads(raw,100))


@pytest.fixture
def location(tmp_path,monkeypatch,supplied):
    files,fact,_=supplied
    root=tmp_path/'synthetic-repository';root.mkdir(mode=0o755)
    directory=root/'artifacts/analyst_revisions_v2/legacy_six_plain/R346-20261107-A'
    current=root
    for part in directory.relative_to(root).parts:
        current/=part;current.mkdir(mode=0o700)
    for name,raw in files.items():
        path=directory/name;path.write_bytes(raw);path.chmod(0o600)
    monkeypatch.chdir(root);monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'DIRECTORY',directory)
    # Synthetic fact seam stays separate from fixed production parse_fact.
    monkeypatch.setattr(m,'parse_fact',lambda raw:copy.deepcopy(fact))
    monkeypatch.setattr(m.security,'snapshot',lambda fd:('synthetic-native-security',os.fstat(fd).st_uid))
    return directory


def context():return m.FreshPlainSubmission(fact_bytes=b'synthetic supplied fact seam',deadline=time.monotonic()+179)


def test_eight_original_fds_survive_consuming_no_claim_or_directory_enumeration(location,monkeypatch):
    opened=[];real_open=os.open
    def observed(name,*args,**kwargs):opened.append(str(name));return real_open(name,*args,**kwargs)
    monkeypatch.setattr(m.os,'open',observed)
    monkeypatch.setattr(m.os,'listdir',lambda *a,**k:(_ for _ in ()).throw(AssertionError('directory census')))
    hold=context()
    with hold as live:
        assert len([row for row in live.rows if row[6] is not None])==8
        assert live.value.candidate.candidate_id=='R343-AR100'
        live.verify()
        assert all(os.fstat(row[1]) for row in live.rows)
    assert not hold.rows and not hold.cache
    assert all(opened.count(name)==1 for name in m.NAMES)
    assert 'claim.json' not in opened
    refused('state',hold.__enter__)


@pytest.mark.parametrize('fault,code',[('mode','metadata'),('symlink','path'),('bytes','pin'),('hardlink','pin')])
def test_bad_leaf_refuses_before_private_parse_and_closes_held_fds(location,monkeypatch,fault,code):
    path=location/m.OBJECT_NAMES[0]
    if fault=='mode':path.chmod(0o644)
    elif fault=='symlink':
        old=path.with_name('retained-synthetic');path.rename(old);path.symlink_to(old)
    elif fault=='hardlink':os.link(path,path.with_name('retained-synthetic'))
    else:path.write_bytes(b'changed');path.chmod(0o600)
    monkeypatch.setattr(m,'validate_supplied',lambda *a,**k:(_ for _ in ()).throw(AssertionError('private parse reached')))
    hold=context();refused(code,hold.__enter__);assert not hold.rows


def test_named_swap_refuses_at_exit_while_original_descriptor_remains_bound(location):
    hold=context();path=location/m.OBJECT_NAMES[0]
    with pytest.raises(m.Refused,match='metadata'):
        with hold as live:
            row=next(row for row in live.rows if row[0]==path)
            raw=os.pread(row[1],row[6]['byte_count'],0)
            path.rename(path.with_name('retained-synthetic'));path.write_bytes(raw);path.chmod(0o600)
            assert os.pread(row[1],len(raw),0)==raw
    assert not hold.rows


def test_native_security_change_refuses_and_closes_every_descriptor(location,monkeypatch):
    hold=context()
    with pytest.raises(m.Refused,match='security'):
        with hold:
            monkeypatch.setattr(m.security,'snapshot',lambda fd:('changed-native',))
    assert not hold.rows


def test_late_close_error_attempts_all_owned_descriptors_and_never_becomes_success(location,monkeypatch):
    hold=context();hold.__enter__();fds=[row[1] for row in hold.rows];attempted=[];real_close=os.close
    def failed_once(fd):
        attempted.append(fd);real_close(fd)
        if len(attempted)==1:raise OSError('synthetic-close-after-real-close')
    monkeypatch.setattr(m.os,'close',failed_once)
    refused('close',lambda:hold.__exit__(None,None,None))
    assert set(attempted)==set(fds) and len(attempted)==len(fds)
    assert not hold.rows and not hold.cache


@pytest.mark.parametrize('deadline',[True,float('inf'),float('nan'),-1,0])
def test_invalid_deadline_refuses_without_private_reads(deadline):refused('deadline',lambda:m.budget(deadline))
