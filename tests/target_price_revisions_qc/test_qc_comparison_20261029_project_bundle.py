"""Public source plus synthetic registry only; no project/private/native I/O."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261029_project_bundle as p
from tests.target_price_revisions_qc import test_qc_comparison_20261028_bundle as off_tests
from tests.target_price_revisions_qc import test_qc_comparison_20261028_multi_bundle as multi_tests


@pytest.fixture(autouse=True)
def no_actual_effects(monkeypatch):
    import http.client
    from research.target_price_revisions_qc import extended_operations as operations
    def denied(*_args,**_kwargs):raise AssertionError('private/native/account/operator effect forbidden')
    monkeypatch.setattr(operations,'credential',denied);monkeypatch.setattr(operations,'read_private',denied)
    monkeypatch.setattr(operations.Operations,'__init__',denied)
    monkeypatch.setattr(http.client,'HTTPSConnection',denied)


@pytest.fixture
def sources():return {path:Path(path).read_bytes() for path in p.SOURCE_PATHS}


def registry():
    organization='a'*32;owner=1234567
    return {'schema':'tpr-cmp28-five-project-bindings-v1','round_id':p.ROUND,
        'owner_instruction_sha256':'a'*64,'git_head':'b'*40,'adapter_source_sha256':p.PROJECTS_SHA256,
        'organization_id':organization,'owner_id':owner,'baseline_receipt_sha256':'c'*64,
        'privacy_basis':'documented_private_default_and_observed_collaborators',
        'explicit_privacy_flag_observed':False,'independent_native_origin_attested':False,
        'projects':{key:{'project_id':41000001+n,'name':name,'organization_id':organization,'owner_id':owner,
            'language':'Py','create_receipt_sha256':hashlib.sha256((key+'create').encode()).hexdigest(),
            'read_receipt_sha256':hashlib.sha256((key+'read').encode()).hexdigest(),
            'collaboration_receipt_sha256':hashlib.sha256((key+'collaboration').encode()).hexdigest(),
            'collaborator_count':1,'nonowner_collaborator_count':0,
            'collaborators_sha256':'1'*64} for n,(key,name) in enumerate(p.NAMES.items())}}


def packet():
    return {'key':p.PACKET_KEY,'sha256':p.PACKET_SHA256,'bytes':p.PACKET_BYTES,
        'encoding':'utf-8-json','source_inventory_sha256':p.INVENTORY_SHA256}


def build(sources,arm='cap_off',binding=None,**changes):
    raw=p._wire(registry() if binding is None else binding)
    args=dict(public_sources=sources,project_binding_raw=raw,expected_project_binding_sha256=hashlib.sha256(raw).hexdigest(),
        arm=arm,operation_id='TPR-CMP28-OFF-R107-SYNTHETIC-005' if arm=='cap_off' else 'TPR-CMP28-R107-SYNTHETIC-005',
        attempt=5,prior_attempts_looks_sha256='2'*64,signal_packet=None if arm=='cap_off' else packet())
    args.update(changes);return p.build_project_candidate(**args)


@pytest.mark.parametrize('arm',tuple(p.ARM_KEYS))
def test_all_five_project_configs_are_exact_source_bound_and_financial_bodies_unchanged(sources,arm):
    before=deepcopy(sources);binding=registry();binding_before=deepcopy(binding);files,raw=build(sources,arm,binding)
    report=json.loads(raw);assert sources==before and binding==binding_before
    native_project=binding['projects'][p.ARM_KEYS[arm]]['project_id']
    assert report['project_id']==native_project and report['project_name']==p.NAMES[p.ARM_KEYS[arm]]
    assert report['file_count']==len(files)==(11 if arm=='cap_off' else 15)
    assert not any(name.endswith('.ipynb') for name in files)
    assert not any(name.endswith('_projects.py') or name.endswith('_project_bundle.py') for name in files)
    config_raw=off_tests.literal(files['comparison_20261028_config.py'],'CONFIG_JSON');config=json.loads(config_raw)
    assert config['project_id']==native_project and config['arm']==arm and config['attempt']==5
    assert config['prior_attempts_looks_sha256']=='2'*64
    assert report['config_sha256']==hashlib.sha256(config_raw.encode()).hexdigest()
    assert off_tests.literal(files['comparison_20261028_algorithm.py'],'PROJECT')==native_project
    assert config['source_template_closure_sha256']==report['source_template_closure_sha256']
    assert report['template_source_hashes']=={path:hashlib.sha256(value).hexdigest() for path,value in sources.items()}
    assert report['rendered_source_closure_sha256']==hashlib.sha256(p._wire(report['cloud_source_hashes'])).hexdigest()
    assert report['cloud_source_hashes']=={name:hashlib.sha256(value).hexdigest() for name,value in files.items()}
    assert report['cloud_source_bytes']=={name:len(value) for name,value in files.items()}
    assert report['project_binding_sha256']==hashlib.sha256(p._wire(binding)).hexdigest()
    if arm=='cap_off':
        baseline,base_raw=p.off.build_off_candidate(public_sources={path:sources[path] for path in p.off.SOURCE_PATHS},
            operation_id=config['operation_id'],attempt=5,prior_attempts_looks_sha256='2'*64)
        assert off_tests.literal(files['comparison_20261028_algorithm.py'],'EXPECTED_CONFIG_SHA256')==report['config_sha256']
    else:
        baseline,base_raw=p.multi.build_multi_candidate(public_sources={path:sources[path] for path in p.multi.SOURCE_PATHS},
            arm=arm,operation_id=config['operation_id'],attempt=5,prior_attempts_looks_sha256='2'*64,signal_packet=packet(),project_id=37650980)
        assert config['signal_packet']==packet()
        tree=ast.parse(files['comparison_20261028_multi_algorithm.py'])
        project_node=next(n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1
            and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='PROJECTS')
        assert ast.literal_eval(project_node.value.args[0])==(native_project,)
        assert off_tests.literal(files['comparison_20261028_multi_algorithm.py'],'EXPECTED_CONFIG_SHA256')==report['config_sha256']
    for name,value in files.items():
        compile(ast.parse(value),name,'exec');assert len(value)<=60000
        assert p._functions(value)==p._functions(baseline[name]),name
        if name not in report['changed_project_binding_files']:assert value==baseline[name]
    old_config=json.loads(off_tests.literal(baseline['comparison_20261028_config.py'],'CONFIG_JSON'))
    assert {key:value for key,value in config.items() if key not in ('project_id','source_template_closure_sha256')}=={
        key:value for key,value in old_config.items() if key not in ('project_id','source_template_closure_sha256')}
    assert report['financial_function_bodies_unchanged'] is True
    for key in ('native_permission','independent_native_origin_attested','project_metadata_native_origin_attested',
            'retired_project_write_authorized','prior_attempts_reset','strategy_economics_changed','mark_policy_changed',
            'source_inputs_admitted','canonical_admission','strategy_accepted','legacy_notebooks_copied','legacy_extras_required'):
        assert report[key] is False
    assert report['new_attempts']==report['new_observed_looks']==0 and report['reservation_sha256'] is report['accepted_performance'] is None


@pytest.mark.parametrize('arm',tuple(p.ARM_KEYS))
def test_real_flat_initialization_uses_only_its_bound_project_without_packet_reads(sources,monkeypatch,arm):
    files,raw=build(sources,arm);report=json.loads(raw)
    if arm=='cap_off':
        modules=off_tests.load_flat(files,monkeypatch)
        # The existing synthetic setup has the same six-universe initialization
        # dependencies for both classes and performs no packet access.
        module=modules['comparison_20261028_algorithm']
        original=module.ComparisonOffAlgorithm
        module.ComparisonMultiAlgorithm=original
    else:
        modules=multi_tests.load_flat(files,monkeypatch);module=modules['comparison_20261028_multi_algorithm']
    algo,reads,labels,universes=multi_tests.setup_native_stubs(module,b'not a packet and must never be read')
    algo.project_id=report['project_id'];algo.initialize()
    assert reads==[] and algo.object_store.calls==[]
    assert labels==['SPY','XLE','REMX','KIE','XLF','IWM'] and len(universes)==7
    assert algo._config['project_id']==report['project_id'] and algo._config['arm']==arm
    algo.algorithm_id='3'*32;algo.get_locked=lambda:True
    prefix=algo._evidence.require_binding()
    assert prefix.endswith('/'+str(report['project_id'])+'/'+'3'*32+'/')
    assert '/37650980/' not in prefix and '/37650453/' not in prefix
    for foreign in (37650980,37650453,41000999,*[row['project_id'] for row in registry()['projects'].values() if row['project_id']!=report['project_id']]):
        fresh,_,_,_=multi_tests.setup_native_stubs(module,b'forbidden')
        fresh.project_id=foreign
        with pytest.raises(ValueError):fresh.initialize()


@pytest.mark.parametrize('path',tuple(p.SOURCE_PATHS))
def test_every_independent_public_source_rejects_one_byte_drift(sources,path):
    sources[path]+=b'\n'
    with pytest.raises(p.ProjectBundleRefusal):build(sources)


@pytest.mark.parametrize('fault',['arbitrary_id','old_id','duplicate','wrong_name','wrong_org','wrong_owner','not_python',
    'nonowner','missing_receipt','bad_receipt','extra_arm','missing_arm','wrong_round','source_relabel','origin_claim','privacy_basis'])
def test_all_five_registered_custody_rows_are_required_not_selected_id_or_marker(sources,fault):
    value=registry();row=value['projects']['TPR100']
    if fault=='arbitrary_id':value={'project_id':41000001,'owner':True,'private':True}
    elif fault=='old_id':row['project_id']=37650980
    elif fault=='duplicate':row['project_id']=value['projects']['OFF']['project_id']
    elif fault=='wrong_name':row['name']='TPR-CMP28-FOREIGN'
    elif fault=='wrong_org':row['organization_id']='OTHER'
    elif fault=='wrong_owner':row['owner_id']='OTHER'
    elif fault=='not_python':row['language']='C#'
    elif fault=='nonowner':row['nonowner_collaborator_count']=1
    elif fault=='missing_receipt':row.pop('read_receipt_sha256')
    elif fault=='bad_receipt':row['collaboration_receipt_sha256']='not-a-hash'
    elif fault=='extra_arm':value['projects']['OTHER']=deepcopy(row)
    elif fault=='missing_arm':value['projects'].pop('PURE')
    elif fault=='wrong_round':value['round_id']='FOREIGN'
    elif fault=='source_relabel':value['adapter_source_sha256']='4'*64
    elif fault=='origin_claim':value['independent_native_origin_attested']=True
    else:value['privacy_basis']='self-declared-private'
    with pytest.raises(p.ProjectBundleRefusal):build(sources,binding=value)


@pytest.mark.parametrize('changes',[{'project_binding_raw':b'{}'},{'project_binding_raw':'{}'},
    {'expected_project_binding_sha256':'4'*64},{'arm':'other'},{'attempt':True},{'attempt':0},
    {'attempt':2**31},{'prior_attempts_looks_sha256':'0'*64},{'operation_id':'foreign'}])
def test_closed_binding_arm_hash_attempt_and_operation_cannot_be_bypassed(sources,changes):
    with pytest.raises(p.ProjectBundleRefusal):build(sources,**changes)


@pytest.mark.parametrize('field,value',[('key','tpr-cmp28/inputs/foreign/packet.json'),('sha256','5'*64),
    ('bytes',True),('bytes',100),('encoding','gzip'),('source_inventory_sha256','6'*64),('extra',True)])
def test_shared_signal_descriptor_is_exact_immutable_and_never_reinterpreted(sources,field,value):
    descriptor=packet();descriptor[field]=value
    with pytest.raises(p.ProjectBundleRefusal):build(sources,arm='pure_tpr',signal_packet=descriptor)


def test_off_never_accepts_signal_packet_and_builder_is_pure_source_only(sources):
    with pytest.raises(p.ProjectBundleRefusal):build(sources,signal_packet=packet())
    tree=ast.parse(Path(p.__file__).read_bytes())
    calls={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    assert not calls&{'open','exec','eval','__import__'}
    attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not attrs&{'read_bytes','read_text','write_bytes','write_text','credential','read_private','HTTPSConnection'}


def test_observed_optional_privacy_flag_is_metadata_not_origin_or_effect_authority(sources):
    binding=registry();binding['explicit_privacy_flag_observed']=True
    _,raw=build(sources,binding=binding);report=json.loads(raw)
    assert report['explicit_privacy_flag_observed'] is True
    assert report['independent_native_origin_attested'] is report['native_permission'] is report['project_metadata_native_origin_attested'] is False


def test_new_attempt_keeps_prior_ledger_template_and_financial_policy_without_allocating_look(sources):
    first_files,first_raw=build(sources);second_files,second_raw=build(sources,attempt=6,operation_id='TPR-CMP28-OFF-R107-SYNTHETIC-006')
    first,second=json.loads(first_raw),json.loads(second_raw)
    assert first['source_template_closure_sha256']==second['source_template_closure_sha256']
    assert first['config_sha256']!=second['config_sha256'] and first['rendered_source_closure_sha256']!=second['rendered_source_closure_sha256']
    assert first['prior_attempts_looks_sha256']==second['prior_attempts_looks_sha256']=='2'*64
    assert first_files['main.py']==second_files['main.py']
    assert first['policy_sha256']==second['policy_sha256']==p.off.PINS['comparison_20261028_policy.json']
    assert first['new_attempts']==second['new_attempts']==first['new_observed_looks']==second['new_observed_looks']==0
