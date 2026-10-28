"""Twenty synthetic sources; no account, credential or real private archive."""
import ast
from copy import deepcopy
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261028_capture as m
from research.target_price_revisions_qc import extended_mia_capture_notebook_successor as old
from tests.target_price_revisions_qc import test_qc_extended_mia_capture_notebook_successor as base

ROOT=Path(__file__).resolve().parents[2]
SOURCES={name:(ROOT/name).read_bytes() for name in m.SOURCE_PATHS}


@pytest.fixture(autouse=True)
def synthetic_only(monkeypatch):
    def deny(*_args,**_kwargs):raise AssertionError('actual private/account/credential/network/subprocess forbidden')
    monkeypatch.setattr(m.ops,'credential',deny)
    monkeypatch.setattr(m.http.client,'HTTPSConnection',deny)
    monkeypatch.setattr(m.subprocess,'run',deny)
    original=m.files._directory
    def bounded_directory(path,*,private):
        if private and path.is_relative_to(m.LANE):deny()
        return original(path,private=private)
    monkeypatch.setattr(m.files,'_directory',bounded_directory)
    monkeypatch.setattr(base,'c',m)
    monkeypatch.setattr(base,'SOURCES',SOURCES)


def twenty(*,new_main=False):
    files=deepcopy(base.PUBLIC_OFF)
    files['research.ipynb']='{"cells":[]}\n'
    for name in sorted(m.PUBLIC_FILES-set(files)):
        files[name]='# synthetic public comparison source\n'
    for index in range(20-len(files)):files[f'synthetic_extra_{index:02d}.py']='# synthetic privately retained\n'
    if new_main:files['main.py']='# synthetic new comparison driver\n'
    assert len(files)==20
    return files


def test_only_identified_module_cap_display_and_historical_metadata_change():
    previous=ast.parse(Path(old.__file__).read_bytes())
    actual=ast.parse(Path(m.__file__).read_bytes())
    actual.body[0]=deepcopy(previous.body[0])
    actual.body=[node for node in actual.body if not (isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id in {'HISTORICAL_COMPARISON','PUBLIC_FILES'} for target in node.targets))]
    class Normalize(ast.NodeTransformer):
        def visit_Assign(self,node):
            if any(isinstance(target,ast.Name) and target.id=='MODULE' for target in node.targets):
                node.value=ast.parse('PREFIX + "extended_mia_capture_notebook_successor.py"',mode='eval').body
            elif any(isinstance(target,ast.Tuple) and [getattr(item,'id',None) for item in target.elts]==['MAX_FILES','MAX_FILE'] for target in node.targets):
                node.value.elts[0]=ast.Constant(17)
            return self.generic_visit(node)
        def visit_Dict(self,node):
            keep=[index for index,key in enumerate(node.keys) if not isinstance(key,ast.Constant)
                or key.value not in {'expected_comparison_kind','new_study_economics_accepted','baseline_mismatch_is_new_study_rejection'}]
            node.keys=[node.keys[index] for index in keep];node.values=[node.values[index] for index in keep]
            return self.generic_visit(node)
        def visit_Name(self,node):
            if node.id=='PUBLIC_FILES':return ast.parse('EXPECTED_FILES | {"research.ipynb"}',mode='eval').body
            return node
    Normalize().visit(actual)
    assert ast.dump(actual,include_attributes=False)==ast.dump(previous,include_attributes=False)
    assert old.MAX_FILES==17 and m.MAX_FILES==24
    assert m.PROJECT==old.PROJECT==37650980


def test_twenty_sources_are_retained_exactly_in_both_archives(tmp_path):
    values=base.fixture(tmp_path,suffix='SYNTHETIC-COMPARE-001')
    sources=twenty();transport,calls=base.cloud(sources)
    result,_=base.execute(values,transport)
    assert result['status']=='COMPLETED' and result['stable_source_inventory'] is True
    assert result['expected_comparison_kind']=='HISTORICAL_DIAGNOSTIC'
    assert result['new_study_economics_accepted'] is False
    assert len(calls)==len(result['source_archives'])==2
    for archived in result['source_archives']:
        value=m.e.parse_json((values[2]/archived['name']).read_bytes())
        assert value['files']==sources and len(value['files'])==20
    assert result['new_codex_attempts'].fraction()==result['new_looks'].fraction()==0


def test_historical_baseline_mismatch_keeps_new_sources_without_economic_verdict(tmp_path):
    values=base.fixture(tmp_path,suffix='SYNTHETIC-COMPARE-MISMATCH')
    sources=twenty(new_main=True);transport,calls=base.cloud(sources)
    result,_=base.execute(values,transport)
    assert result['status']=='BASELINE_MISMATCH' and result['stable_source_inventory'] is True
    assert result['expected_comparison_kind']=='HISTORICAL_DIAGNOSTIC'
    assert result['baseline_mismatch_is_new_study_rejection'] is False
    assert result['new_study_economics_accepted'] is result['economics_accepted'] is False
    assert len(calls)==2 and len(result['source_archives'])==2
    final=m.e.parse_json((values[2]/result['source_archives'][-1]['name']).read_bytes())
    assert final['files']==sources


@pytest.mark.parametrize('count',[24,25])
def test_exact_file_count_ceiling_has_no_global_effect(count):
    sources={f'synthetic{i:02d}.py':'# synthetic\n' for i in range(count)}
    response={'success':True,'projectId':m.PROJECT,
        'files':[{'name':name,'content':text} for name,text in sources.items()]}
    if count==25:
        with pytest.raises(m.Refusal):m._capture(response)
    else:
        captured,inventory,returned=m._capture(response)
        assert captured==sources and len(inventory)==24 and returned is True
    with pytest.raises(old.Refusal):old._capture(response)


def test_public_names_are_bounded_and_unknown_source_names_stay_hash_only():
    inventory=m._inventory({'comparison_20261028_config.py':'#public\n','synthetic_unknown_secret.py':'#private\n'})
    public=m._public_inventory(inventory)
    assert 'comparison_20261028_config.py' in public
    assert 'synthetic_unknown_secret.py' not in public
    assert any(key.startswith('unrecognized-name-sha256-') for key in public)


def test_new_module_is_its_own_committed_source_binding_not_legacy_alias(monkeypatch):
    assert m.MODULE=='research/target_price_revisions_qc/comparison_20261028_capture.py'
    assert m.SOURCE_PATHS[0]==m.MODULE and old.MODULE not in m.SOURCE_PATHS
    m._imports()
    monkeypatch.setattr(m,'__file__',old.__file__)
    with pytest.raises(m.Refusal):m._imports()


@pytest.mark.parametrize('fault',['empty_token','foreign_project','different_second_read','http_failure'])
def test_original_secret_project_stability_http_guards_are_preserved(tmp_path,fault):
    values=base.fixture(tmp_path,suffix='SYNTHETIC-COMPARE-'+fault.replace('_','-'))
    def mutate(response,number):
        if fault=='foreign_project':response['projectId']=1
        elif fault=='different_second_read' and number==2:response['files'][0]['content']+='# changed\n'
    transport,calls=base.cloud(twenty(),mutate=mutate,
        token='' if fault=='empty_token' else 'SYNTHETIC-TOKEN',status=500 if fault=='http_failure' else 200)
    result,_=base.execute(values,transport)
    assert result['status']=='FAILED_OR_UNCERTAIN' and 1<=len(calls)<=2
    assert result['economics_accepted'] is False


def test_claim_is_no_replace_and_spent_scope_is_not_reopened(tmp_path):
    values=base.fixture(tmp_path,suffix='SYNTHETIC-COMPARE-NORETRY')
    transport,calls=base.cloud(twenty());base.execute(values,transport)
    before=len(calls)
    with pytest.raises(FileExistsError):base.execute(values,transport)
    assert len(calls)==before==2
