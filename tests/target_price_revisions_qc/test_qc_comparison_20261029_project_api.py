"""Synthetic HTTP and private artifacts only; actual credentials/network denied."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import stat

import pytest

from research.target_price_revisions_qc import comparison_20261029_project_api as m

NOW=datetime(2026,10,28,17,tzinfo=timezone.utc)
OP='TPR-CMP29-API-SYNTHETIC-001'
PROJECT=49000001
ROOT=Path(__file__).resolve().parents[2]



def registry():
    # Synthetic custody metadata only; no native receipt or privacy attestation.
    adapter_sha=m._sha((ROOT/m.PROJECTS_MODULE).read_bytes())
    keys=('OFF','TPR050','TPR100','TPR200LONG','PURE')
    return {'schema':'tpr-cmp28-five-project-bindings-v1',
        'round_id':'TPR-CMP28-R107-20261029A','owner_instruction_sha256':'b'*64,
        'git_head':'a'*40,'adapter_source_sha256':adapter_sha,
        'organization_id':'a'*32,'owner_id':123,
        'baseline_receipt_sha256':'d'*64,
        'privacy_basis':'documented_private_default_and_observed_collaborators',
        'explicit_privacy_flag_observed':False,'independent_native_origin_attested':False,
        'projects':{key:{'project_id':PROJECT+i,'name':'TPR-CMP28-R107-20261029A-'+key,
            'organization_id':'a'*32,'owner_id':123,'language':'Py',
            'create_receipt_sha256':m._sha(('create-'+key).encode()),
            'read_receipt_sha256':m._sha(('read-'+key).encode()),
            'collaboration_receipt_sha256':m._sha(('collaborators-'+key).encode()),'collaborator_count':1,
            'nonowner_collaborator_count':0,'collaborators_sha256':'9'*64} for i,key in enumerate(keys)}}


@pytest.fixture(autouse=True)
def deny_real(monkeypatch):
    def deny(*_args,**_kwargs):raise AssertionError('actual credential/network/subprocess forbidden')
    monkeypatch.setattr(m.ops,'credential',deny)
    monkeypatch.setattr(m.http.client,'HTTPSConnection',deny)
    monkeypatch.setattr(m.subprocess,'run',deny)


def row(endpoint,payload,identity='r001',**extra):
    return dict(id=identity,endpoint=endpoint,payload=payload,payload_file=None,
        payload_sha256=m._sha(m._canonical(payload)),max_response_bytes=65536,seconds=10,**extra)


def plan(requests=None,**extra):
    raw=m._canonical(registry())
    arguments=dict(project_bindings_raw=raw,expected_project_bindings_sha256=m._sha(raw),
        arm='cap_off',candidate_config_sha256='c'*64,candidate_attempt=5,
        operation_id=OP,git_head='a'*40,
        source_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in m.REQUIRED_SOURCES},
        owner_instruction_sha256='b'*64,created_utc=(NOW-timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW+timedelta(seconds=599)).isoformat(),
        requests=requests or [row('files/read',{'projectId':PROJECT})],mode='offline-fixture')
    arguments.update(extra)
    return m.prepare_plan(**arguments)


def execute(tmp_path,p,transport):
    return m._execute_fixture(p,tmp_path/'synthetic-api',transport=transport,clock=lambda:NOW)


def response(body):return m._canonical(body),200,'SYNTHETIC-TOKEN'


def inventory(files):return {name:{'bytes':len(text.encode()),'sha256':m._sha(text.encode())} for name,text in files.items()}


def source_response(files):return {'success':True,'projectId':PROJECT,
    'files':[{'name':name,'content':text} for name,text in files.items()]}


def upload_plan():
    before={'main.py':'# old\n','research.ipynb':'{"cells":["do not touch"]}\n','mia_diag.py':'# preserved helper\n'}
    after={**before,'main.py':'# new exact source\n'}
    first=row('files/read',{'projectId':PROJECT},'before',source_inventory_sha256=m._sha(m._canonical(inventory(before))))
    write=row('files/update',{'projectId':PROJECT,'name':'main.py','content':after['main.py']},'write')
    last=row('files/read',{'projectId':PROJECT},'after',source_inventory_sha256=m._sha(m._canonical(inventory(after))))
    return plan([first,write,last],allowed_source_hashes={'main.py':m._sha(after['main.py'].encode())},
        attempt_id='fresh-attempt-4',reserved_look_id='fresh-reserved-look-34'),before,after


def test_upload_preconditions_extras_and_claims_are_verified_before_each_effect(tmp_path):
    p,before,after=upload_plan();cloud=dict(before);calls=[];root=tmp_path/'synthetic-api'
    def transport(endpoint,raw,seconds,maximum):
        payload=json.loads(raw);calls.append(endpoint)
        assert (root/(OP+'.operation.spent.json')).exists()
        assert len(list(root.glob(OP+'.*.request.spent.json')))==len(calls)
        if endpoint=='files/read':return response(source_response(cloud))
        cloud[payload['name']]=payload['content'];return response({'success':True})
    result=execute(tmp_path,p,transport)
    assert result['status']=='completed' and cloud==after
    assert calls==['files/read','files/update','files/read']
    assert result['requests'][-1]['source_inventory']==inventory(after)
    assert cloud['research.ipynb']==before['research.ipynb'] and cloud['mia_diag.py']==before['mia_diag.py']
    assert result['receipt_published'] and result['lock_cleanup_complete']
    assert result['atomic_remote_compare_and_swap_proven'] is False
    for item in result['requests']:
        artifact=root/item['raw_response']['name']
        assert stat.S_IMODE(artifact.stat().st_mode)==0o600
        assert m._sha(artifact.read_bytes())==item['raw_response']['sha256']
    assert '# preserved helper' not in json.dumps(result)


def test_changed_before_inventory_stops_before_first_write(tmp_path):
    p,before,_=upload_plan();before['mia_diag.py']='# somebody changed helper\n';calls=[]
    def transport(endpoint,*_):calls.append(endpoint);return response(source_response(before))
    result=execute(tmp_path,p,transport)
    assert result['status']=='failed_or_uncertain' and calls==['files/read']
    assert result['requests'][0]['raw_response'] is not None


@pytest.mark.parametrize('name',['comparison_20261028_multi_algorithm.py','comparison_20261028_signal_native.py','raw_revision.py','comparison_20261028_accounting_runtime.py'])
@pytest.mark.parametrize('fault',[None,'wrong_hash','missing_inventory_gate'])
def test_exact_multi_packaging_names_keep_hash_and_inventory_admission(name,fault):
    source='# synthetic exact packaging source\n'
    before=row('files/read',{'projectId':PROJECT},'before',source_inventory_sha256=m._sha(m._canonical({})))
    write=row('files/create',{'projectId':PROJECT,'name':name,'content':source},'write')
    after=row('files/read',{'projectId':PROJECT},'after',
        source_inventory_sha256=m._sha(m._canonical(inventory({name:source}))))
    allowed={name:m._sha(source.encode())}
    if fault=='wrong_hash':allowed[name]='f'*64
    elif fault=='missing_inventory_gate':after.pop('source_inventory_sha256')
    arguments=dict(allowed_source_hashes=allowed,attempt_id='fresh-multi-attempt',reserved_look_id='fresh-multi-look')
    if fault is None:
        prepared=plan([before,write,after],**arguments)
        assert prepared['allowed_source_hashes']==allowed
    else:
        with pytest.raises(m.APIRefusal):plan([before,write,after],**arguments)


def test_packaging_allowlist_does_not_admit_arbitrary_comparison_names():
    name='comparison_20261028_unapproved.py'
    with pytest.raises(m.APIRefusal):plan(allowed_source_hashes={name:m._sha(b'# not admitted')})


def test_exact_public_raw_numeric_helper_source_is_bound_in_upload_plan_without_new_write_authority():
    name='research/target_price_revisions_development/raw_revision.py'
    raw=(ROOT/name).read_bytes()
    assert m._sha(raw)=='ea4efcd9b0e73ae0b5c166d820c51e054559a3ed610041a6eb2acc8abca36353'
    upload,before,after=upload_plan()
    sources={**upload['source_hashes'],name:m._sha(raw)}
    prepared=plan(upload['requests'],source_hashes=sources,allowed_source_hashes=upload['allowed_source_hashes'],
        attempt_id=upload['attempt_id'],reserved_look_id=upload['reserved_look_id'])
    assert m._validated(prepared)==prepared and prepared['source_hashes'][name]==m._sha(raw)
    assert prepared['allowed_source_hashes']=={'main.py':m._sha(after['main.py'].encode())}
    assert name not in m.WRITE_FILES and prepared['automatic_retry'] is prepared['market_trading_authorized'] is False
    assert before['mia_diag.py']==after['mia_diag.py']


@pytest.mark.parametrize('name',[
    'research/target_price_revisions_development/raw_revision2.py',
    'research/target_price_revisions_development/RAW_revision.py',
    'research/target_price_revisions_development/raw_revision.json',
    'research/target_price_revisions_development/__init__.py',
    'research/target_price_revisions_development/subdir/raw_revision.py',
    'research/target_price_revisions_development/raw_revision.py/extra',
    './research/target_price_revisions_development/raw_revision.py',
    '../research/target_price_revisions_development/raw_revision.py',
    'research/target_price_revisions_qc/../target_price_revisions_development/raw_revision.py',
    'research/target_price_revisions_development/./raw_revision.py',
    'research/other_lane/raw_revision.py', 'docs/ACTION_PLAN_2026-08-20.md',
    str(ROOT/'research/target_price_revisions_development/raw_revision.py'),
])
def test_public_helper_exception_does_not_allow_neighbor_paths_aliases_or_other_repository_sources(name):
    sources={**plan()['source_hashes'],name:'c'*64}
    with pytest.raises(m.APIRefusal):plan(source_hashes=sources)


@pytest.mark.parametrize('digest',['0'*64,'g'*64,'a'*63,True,None])
def test_exact_public_helper_path_still_requires_a_valid_supplied_source_hash(digest):
    sources={**plan()['source_hashes'],'research/target_price_revisions_development/raw_revision.py':digest}
    with pytest.raises(m.APIRefusal):plan(source_hashes=sources)


def test_changed_after_extra_fails_without_rollback_or_further_effect(tmp_path):
    p,before,after=upload_plan();calls=[]
    def transport(endpoint,*_):
        calls.append(endpoint)
        if len(calls)==1:return response(source_response(before))
        if endpoint=='files/update':return response({'success':True})
        return response(source_response({**after,'mia_diag.py':'# remote race\n'}))
    result=execute(tmp_path,p,transport)
    assert result['status']=='failed_or_uncertain' and len(calls)==3
    assert result['requests'][-1]['source_inventory']['mia_diag.py']!=inventory(after)['mia_diag.py']


def test_compile_claim_spends_identity_but_adds_no_backtest_or_look(tmp_path):
    p=plan([row('compile/create',{'projectId':PROJECT})],attempt_id='attempt-4',reserved_look_id='reserved-34')
    result=execute(tmp_path,p,lambda *_:response({'success':True,'compileId':'compile-4','state':'BuildQueued'}))
    assert result['compile_requests_attempted']==1
    assert result['requests'][0]['compile_id']=='compile-4' and result['requests'][0]['compile_state']=='BuildQueued'
    assert result['actual_new_backtests']==result['new_observed_looks']==0


def test_observed_in_progress_status_is_preserved_without_claiming_completion(tmp_path):
    # Exact native status spelling observed by root under a fresh scope;
    # original1483-byte envelope SHA00794a35d5e3586e51bdf49fd587d93003a1c9c1da27db2ad4fa17ca008a273b.
    # This synthetic response does not reopen or authenticate that private body.
    p=plan([row('backtests/read',{'projectId':PROJECT,'backtestId':'synthetic-running-off'})])
    result=execute(tmp_path,p,lambda *_:response({'success':True,'backtest':{
        'projectId':PROJECT,'backtestId':'synthetic-running-off','status':'In Progress...',
        'completed':False,'progress':0.055}}))
    observed=result['requests'][0]
    assert result['status']=='completed'
    assert observed['backtest_status']=='In Progress...' and observed['backtest_completed'] is False
    assert result['actual_new_backtests']==result['new_observed_looks']==0
    assert result['economics_accepted'] is False


def chart_payload():
    return {'projectId':PROJECT,'backtestId':'synthetic-own-job','name':'EXT26 Account NAV',
        'start':m.ops.CHART_START,'end':m.ops.CHART_END,'count':m.ops.CHART_COUNT}


@pytest.mark.parametrize('fault',['foreign_project','foreign_chart','chart_case','arbitrary_window',
    'end_past_freeze','short_count','oversized_count','bool_count','bad_job','missing_end','extra_key','live_endpoint'])
def test_chart_read_is_closed_to_exact_own_nav_frozen_window(fault):
    payload=chart_payload();endpoint='backtests/chart/read'
    if fault=='foreign_project':payload['projectId']=PROJECT+1
    elif fault=='foreign_chart':payload['name']='Strategy Equity'
    elif fault=='chart_case':payload['name']='EXT26 account NAV'
    elif fault=='arbitrary_window':payload['start']+=86400
    elif fault=='end_past_freeze':payload['end']+=86400
    elif fault=='short_count':payload['count']=1449
    elif fault=='oversized_count':payload['count']=m.ops.CHART_COUNT+1
    elif fault=='bool_count':payload['count']=True
    elif fault=='bad_job':payload['backtestId']='../foreign-job'
    elif fault=='missing_end':payload.pop('end')
    elif fault=='extra_key':payload['resolution']='minute'
    elif fault=='live_endpoint':endpoint='live/chart/read'
    with pytest.raises(m.APIRefusal):plan([row(endpoint,payload)])


def test_chart_read_claims_then_retains_only_private_raw_body_and_no_acceptance(tmp_path):
    payload=chart_payload();p=plan([row('backtests/chart/read',payload)])
    body={'success':True,'chart':{'name':'EXT26 Account NAV','projectId':PROJECT,
        'backtestId':payload['backtestId'],'series':{'NAV':{'values':[[1609794060,123456.78]]}}}}
    raw=m._canonical(body);calls=[];root=tmp_path/'synthetic-api'
    def transport(endpoint,wire,seconds,maximum):
        calls.append(endpoint)
        assert endpoint=='backtests/chart/read' and json.loads(wire)==payload
        assert (root/(OP+'.operation.spent.json')).exists()
        assert (root/(OP+'.r001.request.spent.json')).exists()
        assert seconds==10 and maximum==65536
        return raw,200,'SYNTHETIC-TOKEN'
    result=execute(tmp_path,p,transport);observed=result['requests'][0]
    assert result['status']=='completed' and calls==['backtests/chart/read']
    assert result['actual_new_backtests']==result['new_observed_looks']==result['compile_requests_attempted']==0
    assert p['attempt_id'] is p['reserved_look_id'] is None
    assert result['economics_accepted'] is result['automatic_retry'] is False
    assert observed['backtest_completed'] is None and observed['backtest_status'] is None
    artifact=root/observed['raw_response']['name']
    assert artifact.read_bytes()==raw and observed['raw_response']['sha256']==m._sha(raw)
    assert stat.S_IMODE(artifact.stat().st_mode)==0o600
    assert '123456.78' not in json.dumps(result)


@pytest.mark.parametrize('fault',['foreign_project','foreign_job','foreign_chart','missing_chart','unrecognized_loading'])
def test_chart_read_retains_but_refuses_foreign_identity_or_unrecognized_body(tmp_path,fault):
    payload=chart_payload();body={'success':True,'chart':{'name':'EXT26 Account NAV'}}
    if fault=='foreign_project':body['chart']['projectId']=PROJECT+1
    elif fault=='foreign_job':body['chart']['backtestId']='other-native-job'
    elif fault=='foreign_chart':body['chart']['name']='Strategy Equity'
    elif fault=='missing_chart':body.pop('chart')
    else:body={'success':True,'status':'ready'}
    result=execute(tmp_path,plan([row('backtests/chart/read',payload)]),lambda *_:response(body))
    assert result['status']=='failed_or_uncertain' and len(result['requests'])==1
    assert result['requests'][0]['raw_response']['sha256']==m._sha(m._canonical(body))
    assert result['economics_accepted'] is False


def test_loading_chart_is_retained_without_retry_or_claiming_nav_observations(tmp_path):
    calls=[]
    def transport(endpoint,*_):
        calls.append(endpoint)
        return response({'success':True,'status':'loading','progress':0})
    result=execute(tmp_path,plan([row('backtests/chart/read',chart_payload())]),transport)
    assert result['status']=='completed' and calls==['backtests/chart/read']
    assert result['requests'][0]['raw_response'] is not None
    assert result['requests'][0]['backtest_completed'] is None
    assert result['economics_accepted'] is result['automatic_retry'] is False


def test_chart_response_budget_is_enforced_before_retention_and_no_retry(tmp_path):
    request=row('backtests/chart/read',chart_payload());request['max_response_bytes']=10
    calls=[]
    def transport(endpoint,*_):
        calls.append(endpoint);return response({'success':True,'status':'loading','progress':0})
    result=execute(tmp_path,plan([request]),transport)
    assert result['status']=='failed_or_uncertain' and calls==['backtests/chart/read']
    assert result['requests'][0]['raw_response'] is None


@pytest.mark.parametrize('mode',['success','unknown','cancelled'])
def test_launch_counts_only_actual_returned_job_and_uncertainty_stops(tmp_path,mode):
    p=plan([row('backtests/create',{'projectId':PROJECT,'compileId':'compile-4','backtestName':'candidate-attempt-4'})],
        attempt_id='attempt-4',reserved_look_id='reserved-34')
    def transport(*_):
        if mode=='unknown':raise TimeoutError('synthetic-private-body')
        if mode=='cancelled':raise KeyboardInterrupt('synthetic-private-body')
        return response({'success':True,'backtest':{'projectId':PROJECT,'backtestId':'job-4'}})
    if mode=='cancelled':
        with pytest.raises(m.APICancelled) as stopped:execute(tmp_path,p,transport)
        result=stopped.value.report
    else:result=execute(tmp_path,p,transport)
    assert 'synthetic-private-body' not in json.dumps(result)
    assert result['actual_new_backtests']==(1 if mode=='success' else None)
    assert result['new_observed_looks']==(1 if mode=='success' else 0)
    assert result['receipt_published'] and result['lock_cleanup_complete']


def test_private_payload_read_has_exact_fresh_claim_and_integrity(tmp_path,monkeypatch):
    root=tmp_path/'synthetic-api';root.mkdir(mode=0o700)
    raw=m._canonical({'projectId':PROJECT});path=root/'payload.synthetic.json';path.write_bytes(raw);path.chmod(0o600)
    request=row('files/read',{'projectId':PROJECT});request['payload']=None
    request['payload_file']={'name':path.name,'bytes':len(raw),'sha256':m._sha(raw)}
    original=m.ops.read_private
    def read(directory,name,maximum):
        assert (root/(OP+'.r001.payload-read.spent.json')).exists()
        assert (root/(OP+'.r001.request.spent.json')).exists()
        return original(directory,name,maximum)
    monkeypatch.setattr(m.ops,'read_private',read)
    result=execute(tmp_path,plan([request]),lambda *_:response(source_response({})))
    assert result['status']=='completed' and result['requests'][0]['payload_read_claim'] is not None


def test_spent_operation_refuses_before_any_repeat_transport(tmp_path):
    p=plan();calls=[]
    def transport(*_):calls.append(True);return response(source_response({}))
    execute(tmp_path,p,transport)
    with pytest.raises(FileExistsError):execute(tmp_path,p,transport)
    assert len(calls)==1


def test_secret_echo_is_refused_before_raw_or_projection_retention(tmp_path):
    result=execute(tmp_path,plan(),lambda *_:response({'success':True,'message':'SYNTHETIC-TOKEN'}))
    assert result['status']=='failed_or_uncertain'
    assert result['requests'][0]['raw_response'] is result['requests'][0]['projection'] is None
    assert 'SYNTHETIC-TOKEN' not in json.dumps(result)


@pytest.mark.parametrize('fault',['project','notebook_write','helper_write','hash','endpoint','no_attempt',
    'no_precondition','too_many_compile','budget','expired','wrong_compile_id'])
def test_closed_endpoint_source_identity_budget_guards(fault,tmp_path):
    if fault=='wrong_compile_id':
        p=plan([row('compile/read',{'projectId':PROJECT,'compileId':'expected'})])
        result=execute(tmp_path,p,lambda *_:response({'success':True,'compileId':'foreign','state':'BuildSuccess'}))
        assert result['status']=='failed_or_uncertain';return
    args={};requests=[row('files/read',{'projectId':PROJECT})]
    if fault=='project':requests[0]=row('files/read',{'projectId':1})
    elif fault in {'notebook_write','helper_write'}:
        name='research.ipynb' if fault=='notebook_write' else 'mia_diag.py'
        requests=[row('files/update',{'projectId':PROJECT,'name':name,'content':'#bad'})]
        args.update(allowed_source_hashes={name:m._sha(b'#bad')},attempt_id='a',reserved_look_id='l')
    elif fault=='hash':requests[0]['payload_sha256']='c'*64
    elif fault=='endpoint':requests[0]['endpoint']='projects/create'
    elif fault=='no_attempt':requests=[row('compile/create',{'projectId':PROJECT})]
    elif fault=='no_precondition':requests=[row('files/update',{'projectId':PROJECT,'name':'main.py','content':'#x'})];args.update(allowed_source_hashes={'main.py':m._sha(b'#x')},attempt_id='a',reserved_look_id='l')
    elif fault=='too_many_compile':requests=[row('compile/create',{'projectId':PROJECT},'one'),row('compile/create',{'projectId':PROJECT},'two')];args.update(attempt_id='a',reserved_look_id='l')
    elif fault=='budget':args['max_total_response_bytes']=1
    else:args['expires_utc']=(NOW-timedelta(seconds=1)).isoformat()
    with pytest.raises(m.APIRefusal):plan(requests,**args)


def test_native_transport_uses_actual_tls_hmac_deadline_bounded_read_and_close(monkeypatch):
    calls=[]
    @contextmanager
    def deadline(seconds):calls.append(('deadline',seconds));yield
    monkeypatch.setattr(m.ops,'wall_deadline',deadline)
    monkeypatch.setattr(m.ops,'credential',lambda:('123','SYNTHETIC-TOKEN'))
    class Connection:
        def __init__(self,host,timeout,context):
            assert host=='www.quantconnect.com' and timeout==7
            assert context.check_hostname and context.verify_mode==m.ssl.CERT_REQUIRED
            assert context.keylog_filename is None
        def request(self,method,path,body,headers):
            assert method=='POST' and path=='/api/v2/files/read' and body==b'{}'
            assert headers['Authorization'].startswith('Basic ') and 'Timestamp' in headers
            calls.append(('request',path))
        def getresponse(self):return self
        @property
        def status(self):return 200
        def read(self,maximum):calls.append(('read',maximum));return b'{}'
        def close(self):calls.append(('close',))
    monkeypatch.setattr(m.http.client,'HTTPSConnection',Connection)
    assert m._native_request('files/read',b'{}',7,101)==(b'{}',200,'SYNTHETIC-TOKEN')
    assert calls==[('deadline',7),('request','/api/v2/files/read'),('read',102),('close',)]


def test_production_has_no_fixture_transport_or_root_override():
    with pytest.raises(m.APIRefusal):m.execute_plan(plan())


def test_cancellation_stays_cancelled_when_receipt_publication_is_unavailable(tmp_path,monkeypatch):
    original=m._publish
    def publish(root,name,raw):
        if name.endswith('.result.json'):raise OSError('synthetic publication body')
        return original(root,name,raw)
    monkeypatch.setattr(m,'_publish',publish)
    def stopped(*_):raise KeyboardInterrupt('synthetic cancellation body')
    with pytest.raises(m.APICancelled) as result:execute(tmp_path,plan(),stopped)
    assert result.value.report['status']=='cancelled'
    assert result.value.report['receipt_published'] is False


def test_cleanup_fatal_is_not_demoted_by_an_earlier_ordinary_failure(tmp_path,monkeypatch):
    original=m.os.unlink
    def unlink(path,*args,**kwargs):
        result=original(path,*args,**kwargs)
        if str(path).endswith('comparison-api.lock'):raise SystemExit('synthetic fatal body')
        return result
    monkeypatch.setattr(m.os,'unlink',unlink)
    def failed(*_):raise RuntimeError('synthetic earlier body')
    with pytest.raises(m.APIFatal) as result:execute(tmp_path,plan(),failed)
    assert result.value.report['status']=='failed_or_uncertain'
    assert 'synthetic fatal body' not in str(result.value)


@pytest.mark.parametrize('start,size,accepted',[(0,20,True),(20,99,True),(0,100,False),(20,101,False)])
def test_orders_page_range_is_strictly_less_than_100(start,size,accepted):
    request=row('backtests/orders/read',{'projectId':PROJECT,'backtestId':'c'*32,
        'start':start,'end':start+size})
    if accepted:
        assert plan([request])['requests'][0]['payload']['end']==start+size
    else:
        with pytest.raises(m.APIRefusal):plan([request])


@pytest.mark.parametrize('size,accepted',[(200,True),(201,False)])
def test_order_bound_correction_preserves_separate_log_window(size,accepted):
    request=row('backtests/read/log',{'projectId':PROJECT,'backtestId':'c'*32,
        'start':0,'end':size,'query':'CMP28'})
    if accepted:
        assert plan([request])['requests'][0]['payload']['end']==size
    else:
        with pytest.raises(m.APIRefusal):plan([request])


@pytest.mark.parametrize('count,accepted',[(25,True),(26,False)])
def test_one_bounded_accounting_helper_extends_physical_census_only_to_25(tmp_path,count,accepted):
    files={f'preserved_{i}.py':'# untouched\n' for i in range(count)}
    result=execute(tmp_path,plan(),lambda *_:response(source_response(files)))
    assert (result['status']=='completed') is accepted
    assert result['requests'][0]['raw_response'] is not None
    if accepted:
        assert result['requests'][0]['source_inventory']==inventory(files)


def test_exact_accounting_helper_creation_preserves_all_existing_24_files(tmp_path):
    name='comparison_20261028_accounting_runtime.py';content='# synthetic pure helper\n'
    before={f'preserved_{i}.py':'# unchanged\n' for i in range(24)}
    after={**before,name:content};cloud=dict(before)
    rows=[row('files/read',{'projectId':PROJECT},'before',source_inventory_sha256=m._sha(m._canonical(inventory(before)))),
        row('files/create',{'projectId':PROJECT,'name':name,'content':content},'helper'),
        row('files/read',{'projectId':PROJECT},'after',source_inventory_sha256=m._sha(m._canonical(inventory(after))))]
    p=plan(rows,allowed_source_hashes={name:m._sha(content.encode())},
        attempt_id='fresh-accounting-helper-attempt',reserved_look_id='fresh-accounting-helper-look')
    def transport(endpoint,raw,*_):
        payload=json.loads(raw)
        if endpoint=='files/read':return response(source_response(cloud))
        assert endpoint=='files/create' and payload['name']==name
        cloud[name]=payload['content'];return response({'success':True})
    result=execute(tmp_path,p,transport)
    assert result['status']=='completed' and cloud==after
    assert {key:cloud[key] for key in before}==before


@pytest.mark.parametrize('arm,key,index',[
    ('cap_off','OFF',0),('cap_tilt_50','TPR050',1),('cap_tilt_100','TPR100',2),
    ('cap_tilt_200','TPR200LONG',3),('pure_tpr','PURE',4)])
def test_exact_registered_arm_selects_only_its_own_project_and_binds_manifest(tmp_path,arm,key,index):
    project=PROJECT+index
    p=plan([row('files/read',{'projectId':project})],arm=arm)
    assert p['project_id']==project and p['project_registration_key']==key
    calls=[]
    def transport(endpoint,raw,*_):
        calls.append(json.loads(raw))
        return response({'success':True,'projectId':project,'files':[]})
    report=execute(tmp_path,p,transport)
    assert report['status']=='completed' and calls==[{'projectId':project}]
    assert report['arm']==arm and report['project_bindings_sha256']==p['project_bindings_sha256']
    assert report['candidate_config_sha256']=='c'*64 and report['candidate_attempt']==5
    assert report['project_registry_framing_verified'] is True
    assert report['project_native_custody_independently_attested'] is False
    assert report['financial_outcome_looks_count'] is None
    assert report['new_observed_looks_semantics']=='returned_native_job_ids_not_financial_outcome_looks'


@pytest.mark.parametrize('project',[37650980,37650453,1,49000002,True])
def test_foreign_or_old_project_payload_refuses_before_any_effect(project):
    with pytest.raises(m.APIRefusal):plan([row('files/read',{'projectId':project})])


@pytest.mark.parametrize('change',[
    {'arm':'foreign'}, {'candidate_config_sha256':'0'*64}, {'candidate_attempt':0},
    {'candidate_attempt':True}, {'candidate_attempt':2**31},
    {'expected_project_bindings_sha256':'a'*64},
    {'project_bindings_raw':b'{}'},
])
def test_closed_registered_candidate_binding_refuses_bad_identity(change):
    with pytest.raises(m.APIRefusal):plan(**change)


@pytest.mark.parametrize('fault',['owner','adapter','missing_adapter_source','unknown_registry_key',
    'duplicate_id','old_id','foreign_org','collaborator'])
def test_registry_receipt_provenance_and_source_binding_are_not_optional(fault):
    body=registry();extra={}
    if fault=='owner':body['owner_instruction_sha256']='a'*64
    elif fault=='adapter':body['adapter_source_sha256']='a'*64
    elif fault=='missing_adapter_source':
        extra['source_hashes']={name:m._sha((ROOT/name).read_bytes()) for name in m.REQUIRED_SOURCES if name!=m.PROJECTS_MODULE}
    elif fault=='unknown_registry_key':body['native_verified']=True
    elif fault=='duplicate_id':body['projects']['PURE']['project_id']=PROJECT
    elif fault=='old_id':body['projects']['OFF']['project_id']=37650980
    elif fault=='foreign_org':body['projects']['OFF']['organization_id']='foreign-org'
    else:body['projects']['OFF']['nonowner_collaborator_count']=1
    raw=m._canonical(body)
    with pytest.raises(m.APIRefusal):
        plan(project_bindings_raw=raw,expected_project_bindings_sha256=m._sha(raw),**extra)


@pytest.mark.parametrize('field,value',[
    ('project_id',49000002),('project_registration_key','PURE'),('arm','pure_tpr'),
    ('candidate_attempt',6),('candidate_config_sha256','e'*64),('project_bindings_sha256','d'*64)])
def test_changed_frozen_binding_or_arm_plan_cannot_reach_transport(tmp_path,field,value):
    p=plan();p[field]=value;calls=[]
    with pytest.raises(m.APIRefusal):
        execute(tmp_path,p,lambda *_:calls.append(True))
    assert calls==[]


@pytest.mark.parametrize('endpoint,body',[
    ('files/read',{'success':True,'projectId':49000002,'files':[]}),
    ('files/read',{'success':True,'files':[{'name':'main.py','content':'#foreign','projectId':49000002}]}),
    ('compile/read',{'success':True,'projectId':49000002,'compileId':'expected','state':'BuildSuccess'}),
    ('backtests/create',{'success':True,'backtest':{'projectId':49000002,'backtestId':'foreign-job'}}),
    ('backtests/read',{'success':True,'backtest':{'projectId':49000002,'backtestId':'expected-job','completed':True,'status':'Completed'}}),
    ('backtests/list',{'success':True,'backtests':[{'projectId':49000002,'backtestId':'other'}]}),
    ('backtests/orders/read',{'success':True,'orders':[{'projectId':49000002,'backtestId':'expected-job'}]}),
])
def test_returned_other_registered_project_is_still_foreign_for_selected_arm(tmp_path,endpoint,body):
    payload={'projectId':PROJECT};extra={}
    if endpoint=='compile/read':payload['compileId']='expected'
    elif endpoint=='backtests/create':
        payload.update(compileId='expected',backtestName='fresh')
        extra.update(attempt_id='attempt-6',reserved_look_id='look-6')
    elif endpoint in {'backtests/read','backtests/orders/read'}:
        payload['backtestId']='expected-job'
        if endpoint=='backtests/orders/read':payload.update(start=0,end=20)
    result=execute(tmp_path,plan([row(endpoint,payload)],**extra),lambda *_:response(body))
    assert result['status']=='failed_or_uncertain' and result['receipt_published']
    assert result['requests'][0]['raw_response'] is not None
    assert result['economics_accepted'] is False


def test_registry_json_is_deep_frozen_and_included_in_each_prior_effect_claim(tmp_path):
    body=registry();raw=m._canonical(body);p=plan(project_bindings_raw=raw,
        expected_project_bindings_sha256=m._sha(raw))
    body['projects']['OFF']['project_id']=123
    root=tmp_path/'synthetic-api'
    def transport(*_):
        frozen=json.loads((root/(OP+'.operation.spent.json')).read_bytes())
        claim=json.loads((root/(OP+'.r001.request.spent.json')).read_bytes())
        assert frozen['project_bindings_sha256']==m._sha(raw)
        assert frozen['project_bindings_json']==raw.decode()
        assert claim['plan_sha256']==m._sha(m._canonical(p))
        return response(source_response({}))
    assert execute(tmp_path,p,transport)['status']=='completed'


@pytest.mark.parametrize('fault',[None,'wrong_head','wrong_branch','uncommitted_source','wrong_loaded_adapter'])
def test_real_source_guard_requires_exact_lane_loaded_adapter_and_committed_bytes(monkeypatch,fault):
    from types import SimpleNamespace
    p=plan();calls=[]
    def git(command,**kwargs):
        assert command[0]=='git' and kwargs.get('cwd')==m.LANE
        args=command[1:];calls.append(args)
        if args[:1]==['check-ignore']:return SimpleNamespace(returncode=0,stdout=b'')
        if args==['rev-parse','--show-toplevel']:value=str(m.LANE)
        elif args==['branch','--show-current']:value='foreign' if fault=='wrong_branch' else m.BRANCH
        elif args==['rev-parse','HEAD']:value='d'*40 if fault=='wrong_head' else p['git_head']
        elif args==['status','--short']:value=''
        elif args[0]=='show':
            name=args[1].split(':',1)[1]
            raw=(ROOT/name).read_bytes()
            if fault=='uncommitted_source' and name==m.MODULE:raw+=b'# not committed'
            return SimpleNamespace(returncode=0,stdout=raw)
        else:raise AssertionError('unexpected public source guard command')
        return SimpleNamespace(returncode=0,stdout=(value+'\n').encode())
    monkeypatch.setattr(m.subprocess,'run',git)
    if fault=='wrong_loaded_adapter':monkeypatch.setattr(m.projects,'__file__','/foreign/projects.py')
    if fault is None:
        m._guard(p)
        shown={args[1].split(':',1)[1] for args in calls if args[0]=='show'}
        assert shown==set(p['source_hashes']) and m.PROJECTS_MODULE in shown and m.predecessor.MODULE in shown
    else:
        with pytest.raises(m.APIRefusal):m._guard(p)


def test_source_guard_failure_after_effect_retains_receipt_and_never_retries(tmp_path):
    p=plan();calls=[];effect_done=False
    def guard(_):
        if effect_done:raise m.APIRefusal('source changed')
    def transport(*_):
        nonlocal effect_done
        effect_done=True;calls.append(True)
        return response(source_response({}))
    result=m._execute_fixture(p,tmp_path/'synthetic-api',transport=transport,guard=guard,clock=lambda:NOW)
    assert result['status']=='failed_or_uncertain' and result['receipt_published'] and calls==[True]
    assert result['requests'][0]['raw_response'] is not None
    assert 'source changed' not in json.dumps(result)
