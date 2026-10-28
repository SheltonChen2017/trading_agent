"""Synthetic HTTP/bounded small packet only; no production private data read."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261028_object_upload as m

ROOT=Path(__file__).resolve().parents[2]
NOW=datetime(2026,10,28,19,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_real(monkeypatch):
    def deny(*_args,**_kwargs):raise AssertionError('actual credential/network/subprocess forbidden')
    monkeypatch.setattr(m.ops,'credential',deny)
    monkeypatch.setattr(m.http.client,'HTTPSConnection',deny)
    monkeypatch.setattr(m.api.subprocess,'run',deny)


def common(operation='META001'):
    return dict(operation_id='TPR-CMP28-OBJECT-SYNTHETIC-'+operation,git_head='a'*40,
        source_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in m.REQUIRED_SOURCES},
        owner_instruction_sha256='b'*64,created_utc=(NOW-timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW+timedelta(seconds=299)).isoformat(),mode='offline-fixture')


def response(body,status=200):return m.e.canonical(body),status,'SYNTHETIC-TOKEN'


def execute(plan,root,json_transport,upload_transport=lambda *_:pytest.fail('unexpected object upload')):
    return m._execute_fixture(plan,root,json_transport=json_transport,upload_transport=upload_transport,clock=lambda:NOW)


def organization(root,**changes):
    row={'projectId':m.PROJECT,'owner':True,'organizationId':'SYNTHETIC-ORG'};row.update(changes)
    calls=[]
    def read(endpoint,payload):calls.append((endpoint,payload));return response({'success':True,'projects':[row]})
    result=execute(m.prepare_metadata_plan(**common()),root,read)
    return result,calls


def upload_plan(binding,operation='UPLOAD001',**changes):
    arguments=dict(common(operation),organization_binding_ref=binding,
        packet_file={'name':'synthetic.packet.json','bytes':m.PACKET_BYTES,'sha256':m.PACKET_SHA256})
    arguments.update(changes)
    return m.prepare_upload_plan(**arguments)


def test_metadata_is_one_own_project_read_with_private_org_binding(tmp_path):
    root=tmp_path/'synthetic';result,calls=organization(root)
    assert result['status']=='completed_metadata'
    assert calls==[('projects/read',{'projectId':37650980})]
    assert 'SYNTHETIC-ORG' not in json.dumps(result)
    descriptor=result['organization_binding'];raw=(root/descriptor['name']).read_bytes()
    assert m._sha(raw)==descriptor['sha256']
    assert json.loads(raw)['organization_id']=='SYNTHETIC-ORG'


@pytest.mark.parametrize('field,value',[('projectId',1),('owner',False),('organizationId','bad\r\nheader')])
def test_wrong_project_ownership_or_org_binding_does_not_admit_upload(tmp_path,field,value):
    result,_=organization(tmp_path/'synthetic',**{field:value})
    assert result['status']=='failed_or_uncertain' and result['organization_binding'] is None


def test_one_exact_plain_upload_and_metadata_size_verification(tmp_path):
    root=tmp_path/'synthetic';metadata,_=organization(root);calls=[];uploads=[]
    def properties(endpoint,payload):
        calls.append((endpoint,payload))
        if len(calls)==1:return response({'success':True,'metadata':None,'errors':[]})
        return response({'success':True,'metadata':{'key':m.KEY,'size':m.PACKET_BYTES,'md5':'a'*32,
            'preview':'SYNTHETIC-PRIVATE-PREVIEW'}})
    def upload(org,key,descriptor,check,claim,report):
        check();claim('read');claim('effect')
        assert org=='SYNTHETIC-ORG' and key==m.KEY
        assert (root/(report['operation_id']+'.packet-read.spent.json')).exists()
        assert (root/('object-key.'+m.PACKET_SHA256+'.write.spent.json')).exists()
        uploads.append(key);report['upload_attempted']=True;report['object_created']=None
        return (*response({'success':True}),'a'*32)
    result=execute(upload_plan(metadata['organization_binding']),root,properties,upload)
    assert result['status']=='completed_upload_metadata_verified' and uploads==[m.KEY]
    assert [endpoint for endpoint,_ in calls]==['object/properties','object/properties']
    assert result['metadata_size_verified'] and result['server_md5_matches_local']
    assert result['source_inputs_admitted'] is False
    assert 'SYNTHETIC-PRIVATE-PREVIEW' not in json.dumps(result)
    assert 'SYNTHETIC-ORG' not in json.dumps(result)
    assert result['object_listing'] is result['object_download'] is result['object_delete'] is False


@pytest.mark.parametrize('body,status',[
    ({'success':True,'metadata':{'key':m.KEY,'size':1,'preview':'SYNTHETIC-CONTENT'}},200),
    ({'success':False,'errors':['permission denied']},403),
    ({'success':False,'errors':['not found']},404),
    ({'success':True},200),
])
def test_existing_or_ambiguous_key_never_spends_a_write_or_packet_read(tmp_path,body,status):
    root=tmp_path/'synthetic';metadata,_=organization(root)
    result=execute(upload_plan(metadata['organization_binding']),root,lambda *_:response(body,status))
    assert result['status']=='failed_or_uncertain' and result['upload_attempted'] is False
    assert not list(root.glob('*.packet-read.spent.json'))
    assert not list(root.glob('object-key.*.write.spent.json'))
    assert 'SYNTHETIC-CONTENT' not in json.dumps(result)


def test_cooperative_content_key_claim_prevents_second_write_with_fresh_operation(tmp_path):
    root=tmp_path/'synthetic';metadata,_=organization(root)
    present_calls=[]
    def properties(*_):
        if present_calls:return response({'success':True,'metadata':{'key':m.KEY,'size':m.PACKET_BYTES}})
        return response({'success':True,'metadata':None,'errors':[]})
    def upload(org,key,descriptor,check,claim,report):
        claim('read');claim('effect');present_calls.append(key)
        return (*response({'success':True}),'a'*32)
    first=execute(upload_plan(metadata['organization_binding']),root,properties,upload)
    assert first['status']=='completed_upload_metadata_verified'
    # Simulate a falsely absent metadata race; the durable content claim still
    # refuses a second setter before its actual upload function can continue.
    second=execute(upload_plan(metadata['organization_binding'],'UPLOAD002'),root,
        lambda *_:response({'success':True,'metadata':None,'errors':[]}),upload)
    assert second['status']=='failed_or_uncertain' and len(present_calls)==1


def test_multipart_is_plain_binary_objectData_with_exact_org_and_key_fields():
    prefix,suffix,content_type=m.multipart_parts('SYNTHETIC-ORG',m.KEY)
    assert b'name="organizationId"' in prefix and b'name="key"' in prefix
    assert b'name="objectData"' in prefix and b'Content-Type: application/json' in prefix
    assert m.KEY.encode() in prefix and suffix.endswith(b'--\r\n')
    assert content_type.startswith('multipart/form-data; boundary=')
    assert '37650980/'+m.STUDY+'/' in m.KEY and m.PACKET_SHA256 in m.KEY
    assert m.PACKET_BYTES==280105389


def test_native_stream_hashes_before_credentials_and_streams_exact_plain_bytes_twice(tmp_path,monkeypatch):
    packet=b'{"synthetic":true}\n';packet_hash=m._sha(packet)
    inputs=tmp_path/'inputs';inputs.mkdir(mode=0o700)
    path=inputs/'synthetic.json';path.write_bytes(packet);path.chmod(0o600)
    monkeypatch.setattr(m,'INPUT_ROOT',inputs);monkeypatch.setattr(m,'PACKET_BYTES',len(packet))
    monkeypatch.setattr(m,'PACKET_SHA256',packet_hash)
    monkeypatch.setattr(m,'KEY',f'{m.PROJECT}/{m.STUDY}/signals/{packet_hash}.json')
    claims=[];sent=[];events=[]
    @contextmanager
    def deadline(seconds):assert seconds==120;yield
    monkeypatch.setattr(m.ops,'wall_deadline',deadline)
    class Connection:
        def putrequest(self,method,endpoint):assert (method,endpoint)==('POST','/api/v2/object/set')
        def putheader(self,key,value):events.append((key,value))
        def endheaders(self):events.append(('endheaders',))
        def send(self,raw):sent.append(raw)
        def getresponse(self):return self
        def read(self,maximum):assert maximum==m.MAX_RESPONSE+1;return b'{"success":true}'
        @property
        def status(self):return 200
        def close(self):events.append(('closed',))
    def connection(seconds):
        assert claims==['read','effect']
        return Connection(),{'Authorization':'SYNTHETIC','Timestamp':'123'},'SYNTHETIC-TOKEN'
    monkeypatch.setattr(m,'_connection',connection)
    report={'expires_utc':(datetime.now(timezone.utc)+timedelta(seconds=299)).isoformat(),'local_packet_bytes_read':0,
        'upload_attempted':False,'object_created':False}
    descriptor={'name':path.name,'bytes':len(packet),'sha256':packet_hash}
    raw,status,token,md5=m._native_upload('SYNTHETIC-ORG',m.KEY,descriptor,lambda:None,claims.append,report)
    prefix,suffix,_=m.multipart_parts('SYNTHETIC-ORG',m.KEY)
    assert b''.join(sent)==prefix+packet+suffix
    assert report['local_packet_bytes_read']==2*len(packet)
    assert report['multipart_body_bytes']==len(prefix)+len(packet)+len(suffix)
    assert md5==hashlib.md5(packet).hexdigest() and status==200


@pytest.mark.parametrize('fault',['packet_hash','packet_size','no_binding','long_deadline','wrong_key_source'])
def test_plans_pin_exact_plain_packet_source_and_scope(fault):
    arguments=dict(common('UPLOAD'),organization_binding_ref={'name':'binding.json','bytes':100,'sha256':'c'*64},
        packet_file={'name':'packet.json','bytes':m.PACKET_BYTES,'sha256':m.PACKET_SHA256})
    if fault=='packet_hash':arguments['packet_file']['sha256']='d'*64
    elif fault=='packet_size':arguments['packet_file']['bytes']+=1
    elif fault=='no_binding':arguments['organization_binding_ref']=None
    elif fault=='long_deadline':arguments['expires_utc']=(NOW+timedelta(seconds=600)).isoformat()
    else:arguments['packet_file']['name']='../operator.db'
    with pytest.raises(m.api.APIRefusal):m.prepare_upload_plan(**arguments)


def test_native_json_cleanup_cannot_replace_cancellation_with_ordinary_close_error(monkeypatch):
    @contextmanager
    def deadline(_seconds):yield
    monkeypatch.setattr(m.ops,'wall_deadline',deadline)
    class Connection:
        def request(self,*args,**kwargs):raise KeyboardInterrupt('synthetic cancellation')
        def close(self):raise OSError('synthetic cleanup')
    monkeypatch.setattr(m,'_connection',lambda _:(Connection(),{},'SYNTHETIC-TOKEN'))
    with pytest.raises(KeyboardInterrupt):m._native_json('projects/read',{'projectId':m.PROJECT})


def test_production_wrappers_do_not_accept_fixture_plans():
    with pytest.raises(m.api.APIRefusal):m.execute_metadata_plan(m.prepare_metadata_plan(**common()))
