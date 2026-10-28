"""Synthetic archive/token preservation only; no private archive or native I/O."""
from copy import deepcopy
import hashlib
import http.client
import json

import pytest

from research.target_price_revisions_qc import recovery_20261028_cell_install as m

OPERATION='TPR-EXT26-MIA-SOURCE-BASELINE-20261028-SYNTHETIC-002'
SOURCE="print('ONLY-SYNTHETIC-OWNED-CELL002')\n"


@pytest.fixture(autouse=True)
def no_actual_effects(monkeypatch):
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args,**_kwargs):raise AssertionError('actual private/provider/operator/cloud forbidden')
    for name in ('read_private','credential'):monkeypatch.setattr(ops,name,deny)
    monkeypatch.setattr(ops.Operations,'__init__',deny)
    monkeypatch.setattr(ops.subprocess,'run',deny)
    monkeypatch.setattr(http.client,'HTTPSConnection',deny)


def code(source,identity='owned002',**extra):
    return dict(cell_type='code',metadata={'source':'metadata decoy'},id=identity,
        execution_count=None,outputs=[],source=source,**extra)


def notebook(source=None):
    target=code(m.PLACEHOLDER if source is None else source)
    old=code(['# café old cell\n',"answer = 'source'\n"],identity='older001')
    old['execution_count']=7;old['outputs']=[{'output_type':'stream','name':'stdout','text':['old output\n']}]
    return dict(cells=[old,target],metadata={'private':'SYNTHETIC-OLD-METADATA'},nbformat=4,nbformat_minor=5)


def text(book):
    return json.dumps(book,indent=2,ensure_ascii=False).replace('\n','\r\n')+'\r\n'


def archive(book=None,**changes):
    value=dict(schema='tpr-ext26-mia-all-source-v1',operation_id=OPERATION,
        project_id=m.PROJECT,request_index=2,files={'main.py':'# untouched original\n',
            'research.ipynb':text(notebook() if book is None else book)})
    value.update(changes)
    return (json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode()


def install(raw=None,**changes):
    raw=archive() if raw is None else raw
    arguments=dict(expected_archive_sha256=hashlib.sha256(raw).hexdigest(),expected_archive_bytes=len(raw),
        expected_capture_operation=OPERATION,cell_source=SOURCE,expected_cell_sha256=hashlib.sha256(SOURCE.encode()).hexdigest())
    arguments.update(changes)
    return m.prepare_install(raw,**arguments)


@pytest.mark.parametrize('shape',['string','list'])
def test_replaces_only_owned_source_token_preserving_every_other_notebook_byte(shape):
    book=notebook(m.PLACEHOLDER if shape=='string' else [m.PLACEHOLDER[:17],m.PLACEHOLDER[17:]])
    original=text(book);raw=archive(book)
    report,replacement=install(raw)
    begin,end=report['source_token_character_span']
    after=json.loads(replacement)
    token_value=SOURCE if shape=='string' else SOURCE.splitlines(keepends=True)
    token=json.dumps(token_value,ensure_ascii=False,separators=(',',':'))
    assert replacement==original[:begin]+token+original[end:]
    assert replacement[:begin].encode()==original[:begin].encode()
    assert replacement[begin+len(token):].encode()==original[end:].encode()
    assert after['cells'][0]==book['cells'][0]
    expected=deepcopy(book);expected['cells'][1]['source']=token_value
    assert after==expected
    assert report['cell_index']==1 and report['cell_id']=='owned002'
    assert report['only_owned_source_token_changed'] and report['other_cells_unchanged']
    assert report['effects_authorized'] is report['cell_executed'] is False
    assert report['inventory_before']['main.py']==report['inventory_after']['main.py']
    assert report['all_cell_sources_before']['research.ipynb'][0]==report['all_cell_sources_after']['research.ipynb'][0]
    assert report['new_notebook']['sha256']==hashlib.sha256(replacement.encode()).hexdigest()
    assert 'SYNTHETIC-OLD-METADATA' not in json.dumps(report)


def test_json_decoder_locates_escaped_actual_source_key_not_metadata_source_token():
    raw=archive();outer=json.loads(raw)
    original=outer['files']['research.ipynb']
    # Escape only the owned source key; JSON semantic spelling is unchanged.
    needle='"source": '+json.dumps(m.PLACEHOLDER)
    assert original.count(needle)==1
    changed=original.replace(needle,'"\\u0073ource": '+json.dumps(m.PLACEHOLDER))
    outer['files']['research.ipynb']=changed
    report,replacement=install(json.dumps(outer,ensure_ascii=False).encode())
    begin,_=report['source_token_character_span']
    assert replacement[:begin]==changed[:begin]
    assert '"\\u0073ource": ' in replacement
    assert json.loads(replacement)['cells'][1]['metadata']=={'source':'metadata decoy'}


@pytest.mark.parametrize('fault',['missing','duplicate_cell','duplicate_notebook','partial_placeholder','already_installed','duplicate_id'])
def test_missing_or_colliding_owned_cells_refuse(fault):
    book=notebook();files=None
    if fault=='missing':book['cells'][1]['source']='# unrelated\n'
    elif fault=='duplicate_cell':book['cells'].append(code(m.PLACEHOLDER,identity='owned003'))
    elif fault=='duplicate_notebook':files={'research.ipynb':text(book),'other.ipynb':text(notebook())}
    elif fault=='partial_placeholder':book['cells'][1]['source']=m.PLACEHOLDER+'# unexpected second line\n'
    elif fault=='already_installed':book['cells'][0]['source']=SOURCE
    else:book['cells'][0]['id']='owned002'
    with pytest.raises(m.CellInstallRefusal):install(archive(book,**({} if files is None else {'files':files})))


@pytest.mark.parametrize('field,value',[('execution_count',1),('execution_count',True),('execution_count',0.0),
    ('outputs',[{'output_type':'stream','text':['unexpected']}]),('outputs',None),('cell_type','markdown'),
    ('id','bad id'),('extra',True)])
def test_owned_cell_is_unexecuted_empty_and_closed(field,value):
    book=notebook();book['cells'][1][field]=value
    with pytest.raises(m.CellInstallRefusal):install(archive(book))


def test_zero_execution_count_is_preserved_without_lifecycle_mutation():
    book=notebook();book['cells'][1]['execution_count']=0
    _,replacement=install(archive(book))
    assert json.loads(replacement)['cells'][1]['execution_count']==0


@pytest.mark.parametrize('field,value',[('schema','foreign'),('project_id',1),('project_id',True),
    ('operation_id','foreign'),('request_index',0),('request_index',True),('extra',1),('files',{}),
    ('files',{'../private.ipynb':'{}'}),('files',{f'module{i}.py':'#' for i in range(18)})])
def test_closed_own_project_bounded_source_archive(field,value):
    with pytest.raises(m.CellInstallRefusal):install(archive(**{field:value}))


@pytest.mark.parametrize('fault',['archive_duplicate','notebook_duplicate','invalid_utf8','nonfinite','trailing','wrong_hash','wrong_size','huge'])
def test_duplicate_json_encoding_and_integrity_gates_refuse(fault):
    raw=archive();overrides={}
    if fault=='archive_duplicate':raw=raw.rstrip()[:-1]+b',"project_id":37650980}'
    elif fault=='notebook_duplicate':
        outer=json.loads(raw);book=outer['files']['research.ipynb']
        outer['files']['research.ipynb']=book.replace('"nbformat": 4','"nbformat": 4,"nbformat":4')
        raw=json.dumps(outer).encode()
    elif fault=='invalid_utf8':raw=b'\xff'
    elif fault=='nonfinite':
        outer=json.loads(raw);outer['files']['research.ipynb']=outer['files']['research.ipynb'].replace('"nbformat": 4','"nbformat": NaN')
        raw=json.dumps(outer).encode()
    elif fault=='trailing':raw+=b'{}'
    elif fault=='wrong_hash':overrides['expected_archive_sha256']='a'*64
    elif fault=='wrong_size':overrides['expected_archive_bytes']=len(raw)+1
    else:raw=b' '* (m.MAX_ARCHIVE+1)
    with pytest.raises(m.CellInstallRefusal):install(raw,**overrides)


def test_archive_hash_and_size_are_checked_before_any_parse(monkeypatch):
    called=[]
    def forbidden(_text):called.append(True);raise AssertionError('parse before integrity')
    monkeypatch.setattr(m,'_decode',forbidden)
    with pytest.raises(m.CellInstallRefusal):install(expected_archive_sha256='b'*64)
    assert called==[]


@pytest.mark.parametrize('field,value',[('cell_source',''),('cell_source',m.PLACEHOLDER),
    ('cell_source','x'*(m.MAX_CELL_SOURCE+1)),('cell_source','\x00'),('expected_cell_sha256','a'*64),
    ('expected_capture_operation','foreign'),('expected_project',1)])
def test_new_source_and_bindings_are_exact_before_install(field,value):
    with pytest.raises(m.CellInstallRefusal):install(**{field:value})
