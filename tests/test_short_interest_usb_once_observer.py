"""Node observer tests with synthetic children only; never USB/source dispatch."""
import base64
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import pytest


ROOT=Path(__file__).resolve().parents[1]
OBSERVER=ROOT/'scripts/observe_short_interest_usb_once.mjs'
HEAD,REMOTE='a'*40,'b'*40
FILES=('data/__init__.py','data/hashing.py','research/short_interest_etf/firstrate_short_interest_inspection.py',
    'scripts/inspect_short_interest_usb_archive.py','scripts/inspect_short_interest_usb_code_snapshot.py',
    'scripts/diagnose_short_interest_code_read_interval.py','scripts/qualify_short_interest_usb_once.py')
MANIFEST={name:hashlib.sha256(name.encode()).hexdigest() for name in FILES}
INVOCATION='si-usb-offline-once-20261104-v1'
MODEL_POLICY='a403579c17c31010ae26eaddf1350a7f1d313cbf6bdae9b6d815f1ccd83121fe'


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()


def private_aggregate():
    from research.short_interest_etf.firstrate_short_interest_inspection import authority
    def report(which):
        pin=(34319601,'08f019c20384bde811b10d1674dc5067cfded4e4c0097fc8c383649c528429c8') if which=='full' else (9660009,'3a8a07dec5c91f4e54cda396d9b1483895769d6ecac1a8d1a15a64e873fa191a')
        return {'archive_sha256':pin[1],'archive_bytes':pin[0],'member_count':1,'inflated_bytes':100,
            'rows':0,'structurally_clear_rows':0,'quarantined_rows':0,'empty_members':1,
            'row_reason_counts':{},'reported_field_observations':{},'earliest_settlement_date':None,
            'latest_settlement_date':None,'distinct_settlement_dates':0,
            'member_origin_disposition_commitment_sha256':'c'*64,'all_member_tokens_commitment_sha256':'d'*64,
            'year_2026_tokens_commitment_sha256':'e'*64,'year_2026_rows':0,'year_2026_members':0,
            'all_members_CRC_verified':True,'complete_byte_inspection':True,'DTC_recalculated_or_substituted':False}
    return {'schema':'si-firstrate-supplied-byte-inspection-v1','policy_sha256':MODEL_POLICY,'scope':'registered_full_and_2026_pair',
        'full':report('full'),'year':report('year'),'manifest_sha256':'c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8',
        'readme_sha256':'bbcddf477ba3ffacb4b0116e9d3f6c2c2a864576ae748abc8daa825602a16ecf',
        'selected_manifest_observations_match':True,'paired_member_mismatches':0,
        'year_is_exact_full_2026_token_multiset_subset':True,
        'semantic_gaps':['settlement_is_not_public_availability','revision_vintage_unverified',
            'filename_is_not_native_or_share_class_identity','same_date_own_class_denominator_missing',
            'DTC_volume_basis_and_rounding_contract_unverified','source_custody_and_upstream_authentication_unqualified',
            'processing_rights_and_actual_input_admission_unqualified'],'authority':authority()}


def envelope():
    from scripts.inspect_short_interest_usb_code_snapshot import authority as old_authority
    from scripts.qualify_short_interest_usb_once import authority
    aggregate=private_aggregate()
    proof={'schema':'si-usb-code-window-observation-v1','status':'closed_finite_code_windows_external_byte_inspection',
        'runtime_head':HEAD,'matching_remote':REMOTE,'profile_sha256':'592c05adc1691030eb5aa3d93660f060248aaa25909bd3503781a446f292c43f',
        'code_mapping_sha256':sha(canonical({name:MANIFEST[name] for name in FILES[:5]})),
        'initial_code_file10_sha256':'c'*64,'terminal_code_file10_sha256':'c'*64,'code_file_original10_equal':True,
        'initial_ancestor_observations_sha256':'d'*64,'terminal_ancestor_observations_sha256':'e'*64,
        'continuous_shared_ancestor_timestamp_custody':False,'physical_root_identity_sha256':'f'*64,
        'source_original10_sha256':'1'*64,'inspection_report_sha256':sha(canonical(aggregate)),'model_policy_sha256':MODEL_POLICY,
        'all_initial_code_contexts_closed':True,'all_source_contexts_closed':True,'all_terminal_code_contexts_closed':True,
        'executed_verified_RAM':True,'authority':old_authority()}
    proof['observation_sha256']=sha(canonical(proof))
    return {'schema':'si-usb-once-envelope-v1','invocation_id':INVOCATION,'status':'closed_finite_offline_byte_inspection',
        'runtime_head':HEAD,'matching_remote':REMOTE,'driver_sha256':MANIFEST[FILES[-1]],'interpreter_version':[3,13,15],
        'maximum_whole_seconds':180,'whole_start_monotonic_ns':'100','whole_end_monotonic_ns':'200',
        'code_manifest_sha256':sha(canonical(MANIFEST)),'original_profile_proof':proof,
        'private_model_aggregate':aggregate,'source_qualified':False,'first_failure':None,'cleanup_failures':[],
        'denials':{name:0 for name in ('python_write_attempts','python_socket_attempts','forbidden_read_open_attempts','unexpected_subprocess_attempts')},
        'external_OS_sandbox_and_independent_owned_wait_required':True,'python_audit_covers_all_metadata':False,
        'extra_code_continuous_ancestor_timestamp_custody':False,
        'git_scope':'original_matching_lane_metadata_environment_ambient_credential_behavior_not_proven','authority':authority()}


def run_node(body,payload=None):
    raw=canonical(envelope() if payload is None else payload)+b'\n'
    config={'runtime_head':HEAD,'matching_remote':REMOTE,'invocation_id':INVOCATION,'code_manifest':MANIFEST}
    module='data:text/javascript;base64,'+base64.b64encode(OBSERVER.read_bytes()).decode()
    prefix='''import {EventEmitter} from 'node:events';
import {createHash} from 'node:crypto';
const m=await import(MODULE_URL);
const encodedConfig=CONFIG_JSON;
const originalRaw=Buffer.from(RAW64,'base64');
function setup(mode='normal',budget=180000){
 let now=0,identity=true,hostGood=true,next=1;const timers=new Map(),signals=[],launches=[];
 const child=new EventEmitter();child.pid=424242;child.exitCode=null;child.signalCode=null;
 for(const channel of ['stdout','stderr']){child[channel]=new EventEmitter();child[channel].destroy=()=>{};}
 child.kill=sig=>{signals.push({direct:child.pid,sig});return true;};
 function close(code=0,sig=null,eof=true){
  child.exitCode=code;child.signalCode=sig;
  if(eof){child.stdout.emit('end');child.stderr.emit('end');}
  child.emit('exit',code,sig);child.emit('close',code,sig);
 }
 function send(raw=originalRaw){child.stdout.emit('data',raw);}
 const host=Object.freeze({runtime:['fixture'],nullDevice:['fixture']});
 const seams={now:()=>now,hrtime:()=>BigInt(Math.round(now*1000000)),identity:()=>identity,
  setTimeout:(fn,delay)=>{const id=next++;timers.set(id,{fn,at:now+delay});return id;},clearTimeout:id=>timers.delete(id),
  host:original=>{if(!hostGood)throw {fixedCode:'host'};if(original!==undefined&&original!==null&&original!==host)throw {fixedCode:'host'};return host;},
  signal:(pid,sig)=>{signals.push({pid,sig});if(mode==='ignore_TERM'&&sig==='SIGKILL')close(null,'SIGKILL');},
  spawn:(exe,args,options)=>{launches.push({exe,args,options});
   if(mode==='clock_after_spawn')identity=false;
   if(mode==='listener_failure'){const original=child.stdout.on;child.stdout.on=function(name,...args){if(name==='data')throw new Error('PRIVATE listener');return original.call(this,name,...args);};}
   return child;},deadlineMs:budget};
 function advance(value){now=value;let again=true;while(again){again=false;for(const[id,t]of [...timers])if(t.at<=now){timers.delete(id);t.fn();again=true;}}}
 return {child,seams,signals,launches,timers,close,send,advance,setIdentity:v=>identity=v,setHost:v=>hostGood=v};
}
'''
    prefix=prefix.replace('MODULE_URL',json.dumps(module)).replace('CONFIG_JSON',json.dumps(canonical(config).decode())).replace('RAW64',json.dumps(base64.b64encode(raw).decode()))
    script=prefix+'\n'+body
    result=subprocess.run(['/opt/homebrew/bin/node','--input-type=module','-'],input=script.encode(),
        cwd=ROOT,env={'PATH':'/usr/bin:/bin'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False)
    assert result.returncode==0,result.stderr.decode(errors='replace')[:4000]
    assert result.stderr==b''
    return json.loads(result.stdout)


def test_owned_positive_exact_proof_is_observation_only_and_raw_stays_private():
    result=run_node("""const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();const r=await p;
const a=r.privateStdoutBytes();a[0]^=255;const b=r.privateStdoutBytes();
console.log(JSON.stringify({s:r.summary(),same:b.equals(originalRaw),mutableCopy:!a.equals(b),keys:Object.keys(r)}));""")
    s=result['s']
    assert s['status']=='closed_finite_offline_byte_observation' and s['source_qualified'] is False and s['ready_for_backtest'] is False
    assert s['exit_observed'] and s['close_observed'] and s['stdout_EOF'] and s['stderr_EOF']
    assert s['private_model_aggregate_present'] and s['test_seams_used']
    assert result['same'] and result['mutableCopy'] and 'paired_member_mismatches' not in json.dumps(s)
    assert 'earliest_settlement_date' not in json.dumps(s)


@pytest.mark.parametrize('change',[
    lambda p:p.update(runtime_head='e'*40),lambda p:p.update(matching_remote='e'*40),
    lambda p:p.update(invocation_id='wrong'),lambda p:p.update(driver_sha256='e'*64),
    lambda p:p.update(code_manifest_sha256='e'*64),lambda p:p.update(source_qualified=0),
    lambda p:p['denials'].update(python_write_attempts=False),lambda p:p['authority'].update(source_qualified=0),
    lambda p:p.update(whole_start_monotonic_ns=None),lambda p:p.update(whole_end_monotonic_ns='999999999999999'),
    lambda p:p.update(extra_key='PRIVATE'),lambda p:p['original_profile_proof'].update(observation_sha256='f'*64),
    lambda p:p['original_profile_proof'].update(code_file_original10_equal=1),
    lambda p:p['original_profile_proof'].update(all_source_contexts_closed=False),
    lambda p:p['original_profile_proof'].update(terminal_code_file10_sha256='e'*64),
    lambda p:p['original_profile_proof'].update(model_policy_sha256='e'*64),
    lambda p:p['private_model_aggregate']['authority'].update(ready_for_backtesting=True),
    lambda p:p['private_model_aggregate'].update(PRIVATE_ROWS=['PRIVATE']),
    lambda p:p['private_model_aggregate']['full'].update(rows=1),
])
def test_lineage_exact_types_complete_proof_and_private_aggregate_mismatch_refuse(change):
    payload=envelope();change(payload)
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();console.log((await p).summaryJson());",payload)
    assert result['status']=='incomplete' and result['first_failure'] is not None
    assert result['source_qualified'] is False and 'PRIVATE' not in json.dumps(result)


def test_original_negative_first_cleanup_and_raw_commitment_are_preserved():
    payload=envelope();payload['status']='incomplete';payload['private_model_aggregate']=None;payload['original_profile_proof']=None
    payload['first_failure']={'phase':'initial_code','role':'code','code_ordinal':5,'code':'original_directory_changed','original_comparison':None,'actor':'unknown'}
    payload['cleanup_failures']=[{**payload['first_failure'],'code':'window_failed','exception_context_observation':True}]
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close(2);const r=await p;console.log(JSON.stringify({s:r.summary(),same:r.privateStdoutBytes().equals(originalRaw)}));",payload)
    assert result['s']['status']=='incomplete' and result['same']
    assert result['s']['producer_first_failure']['code']=='original_directory_changed'
    assert result['s']['producer_cleanup_failures'][0]['exception_context_observation'] is True


@pytest.mark.parametrize('code',[
    'designated_physical_root','exact_git_hashes_required','exact_head_remote_arguments_required',
    'fixed_usb_input_changed','lane_snapshot_changed','matching_remote_changed','model_namespace_occupied',
    'terminal_code_changed','working_code_differs_from_commit',
])
def test_genuine_reader_codes_survive_negative_envelope_without_admission(code):
    payload=envelope();payload.update(status='incomplete',private_model_aggregate=None,original_profile_proof=None)
    payload['first_failure']={'phase':'source_open','role':'full','code_ordinal':None,
        'code':code,'original_comparison':None,'actor':'unknown'}
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close(2);const r=await p;console.log(JSON.stringify({s:r.summary(),same:r.privateStdoutBytes().equals(originalRaw)}));",payload)
    assert result['s']['status']=='incomplete' and result['same']
    assert result['s']['producer_first_failure']['code']==code
    assert result['s']['source_qualified'] is False and result['s']['ready_for_backtest'] is False


def test_fixed_fact_catalogue_covers_original_reader_snapshot_and_producer_codes():
    source=OBSERVER.read_bytes().decode()
    match=re.search(r'const FACT_CODES=new Set\((\[.*?\])\);',source,re.S)
    assert match is not None
    accepted=set(ast.literal_eval(match.group(1)))
    for name in ('scripts/inspect_short_interest_usb_archive.py',
        'scripts/inspect_short_interest_usb_code_snapshot.py','scripts/qualify_short_interest_usb_once.py'):
        tree=ast.parse((ROOT/name).read_bytes(),name)
        node=next(row.value for row in tree.body if isinstance(row,ast.Assign)
            and any(isinstance(target,ast.Name) and target.id=='_CODES' for target in row.targets))
        assert isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='frozenset'
        split=node.args[0]
        assert isinstance(split,ast.Call) and isinstance(split.func,ast.Attribute) and split.func.attr=='split'
        assert isinstance(split.func.value,ast.Constant) and isinstance(split.func.value.value,str)
        assert set(split.func.value.value.split())<=accepted


def test_authentic_pre_output_bootstrap_arguments_refusal_is_not_masked():
    payload={'schema':'si-usb-once-bootstrap-refusal-v1','invocation_id':INVOCATION,'status':'incomplete',
        'source_qualified':False,'first_failure':{'phase':'arguments','role':'bootstrap','code':'owner',
            'code_ordinal':None,'original_comparison':None,'actor':'unknown'},'cleanup_failures':[]}
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close(2);console.log((await p).summaryJson());",payload)
    assert result['status']=='incomplete' and result['producer_first_failure']['phase']=='arguments'
    assert result['producer_first_failure']['code']=='owner'


@pytest.mark.parametrize('mode',['stderr','nonzero','noEOF','extra','invalidUTF','stdoutLimit'])
def test_stderr_exit_EOF_extra_bytes_and_caps_are_negative_without_leaking_rows(mode):
    body="""const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);MODE;
const r=await p;console.log(JSON.stringify({s:r.summary(),signals:w.signals}));"""
    action={
        'stderr':"w.child.stderr.emit('data',Buffer.from('PRIVATE stderr'));w.send();w.close()",
        'nonzero':"w.send();w.close(2)",
        'noEOF':"w.send();w.close(0,null,false)",
        'extra':"w.send(Buffer.concat([originalRaw,Buffer.from('{}\\n')]));w.close()",
        'invalidUTF':"w.send(Buffer.from([255,254]));w.close()",
        'stdoutLimit':"w.send(Buffer.alloc(65538,120));w.close()",
    }[mode]
    result=run_node(body.replace('MODE',action))
    assert result['s']['status']=='incomplete' and 'PRIVATE' not in json.dumps(result)
    if mode=='stdoutLimit':assert result['s']['original_stdout_complete'] is False and result['s']['original_stdout_sha256'] is None
    assert all(item.get('pid',-424242)==-424242 for item in result['signals'])


@pytest.mark.parametrize('mode',['clock_after_spawn','listener_failure'])
def test_postspawn_failure_retains_automatic_KILL_and_waits_for_owned_close(mode):
    result=run_node(f"""const w=setup({json.dumps(mode)});const p=m.observeOnceForTests(encodedConfig,w.seams);
let settled=false;p.then(()=>settled=true);await Promise.resolve();const before=settled,scheduled=w.timers.size;
w.advance(179500);w.close(null,'SIGKILL');const r=await p;
console.log(JSON.stringify({{s:r.summary(),before,scheduled,signals:w.signals}}));""")
    assert result['before'] is False and result['scheduled']>0
    assert any(row['sig']=='SIGKILL' for row in result['signals'])
    assert result['s']['status']=='incomplete'


def test_deadline_bounded_unknown_exit_does_not_signal_after_original_child_exit():
    result=run_node("""const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();
w.child.exitCode=0;w.child.emit('exit',0,null);w.advance(180000);const r=await p;
console.log(JSON.stringify({s:r.summary(),signals:w.signals}));""")
    assert result['signals']==[] and result['s']['owner_action_required'] is True
    assert result['s']['status']=='incomplete' and result['s']['automatic_deadline_shutdown']


def test_actual_timers_terminate_then_kill_only_owned_synthetic_child():
    result=run_node("""const w=setup('ignore_TERM',35);w.seams.setTimeout=setTimeout;w.seams.clearTimeout=clearTimeout;
const p=m.observeOnceForTests(encodedConfig,w.seams);const r=await p;
console.log(JSON.stringify({s:r.summary(),signals:w.signals}));""")
    assert [row['sig'] for row in result['signals']][:2]==['SIGTERM','SIGKILL']
    assert result['s']['status']=='incomplete' and result['s']['actual_signal']=='SIGKILL'


def test_late_getter_and_private_copy_reject_original_clock_without_rebaseline():
    result=run_node("""const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();const r=await p;
const early=r.summary();w.advance(180001);let code=null;try{r.privateStdoutBytes();}catch(e){code=e.fixedCode;}
console.log(JSON.stringify({early,late:r.summary(),copyCode:code}));""")
    assert result['early']['status']=='closed_finite_offline_byte_observation'
    assert result['late']['status']=='incomplete' and result['copyCode']=='deadline'


def test_byte_chunks_are_copied_and_no_caller_command_or_secret_environment_exists():
    result=run_node("""const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);const copied=Buffer.from(originalRaw);w.send(copied);copied.fill(120);w.close();const r=await p;
console.log(JSON.stringify({s:r.summary(),same:r.privateStdoutBytes().equals(originalRaw),launch:w.launches[0]}));""")
    assert result['same']
    launch=result['launch'];assert launch['exe']=='/usr/bin/sandbox-exec' and launch['options']['shell'] is False
    assert launch['options']['cwd']==str(ROOT) and launch['options']['detached'] is True
    assert set(launch['options']['env'])=={'PATH','LC_ALL','GIT_OPTIONAL_LOCKS','GIT_TERMINAL_PROMPT','GIT_CONFIG_NOSYSTEM','PYTHONDONTWRITEBYTECODE'}
    assert launch['args'][2].endswith('/python3.13') and launch['args'][3:6]==['-I','-S','-B']


@pytest.mark.parametrize('extra',['command','cwd','env','deadlineMs','executable','complete'])
def test_caller_config_cannot_inject_control_arguments(extra):
    result=run_node(f"""const w=setup();const config=JSON.parse(encodedConfig);config[{json.dumps(extra)}]='PRIVATE';
const r=await m.observeOnceForTests(m.canonicalJson(config),w.seams);console.log(JSON.stringify({{s:r.summary(),launched:w.launches.length}}));""")
    assert result['launched']==0 and result['s']['status']=='incomplete'
    assert 'PRIVATE' not in json.dumps(result)


def test_extra_original_proof_field_and_missing_false_marker_are_not_accepted():
    payload=envelope();payload['original_profile_proof']['caller_complete']=True
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();console.log((await p).summaryJson());",payload)
    assert result['status']=='incomplete'


def test_private_union_mismatch_bound_uses_both_archives_without_fitness_promotion():
    payload=envelope();private=payload['private_model_aggregate']
    private['full'].update(member_count=50000,empty_members=50000)
    private['year'].update(member_count=50000,empty_members=50000)
    private['paired_member_mismatches']=100000;private['year_is_exact_full_2026_token_multiset_subset']=False
    proof=payload['original_profile_proof'];proof['inspection_report_sha256']=sha(canonical(private))
    proof.pop('observation_sha256');proof['observation_sha256']=sha(canonical(proof))
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();console.log((await p).summaryJson());",payload)
    assert result['status']=='closed_finite_offline_byte_observation' and result['source_qualified'] is False
    assert '100000' not in json.dumps(result) and 'paired_member_mismatches' not in json.dumps(result)


def test_final_summary_serialization_checks_original_clock_after_formatting():
    result=run_node("""const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();const r=await p;
const original=JSON.stringify;let tripped=false;
JSON.stringify=function(value,...args){if(value==='si-usb-once-owned-observation-v1'&&!tripped){tripped=true;w.advance(180001);}return original.call(JSON,value,...args);};
let summary;try{summary=r.summaryJson();}finally{JSON.stringify=original;}
console.log(JSON.stringify({s:JSON.parse(summary),tripped}));""")
    assert result['tripped'] and result['s']['status']=='incomplete'
    assert result['s']['first_failure']=='deadline'


def test_static_observer_has_no_market_or_file_write_dispatch_and_preserves_literal_scope():
    source=OBSERVER.read_text()
    assert 'writeFile' not in source and 'appendFile' not in source and 'fetch(' not in source
    assert '(deny file-read* (subpath "/Volumes"))' in source
    assert '(allow file-write-data (literal "/dev/null"))' in source
    assert 'Source qualification' not in source


@pytest.mark.parametrize('change,code',[
    (lambda p:p['denials'].update(python_socket_attempts=1),'proof'),
    (lambda p:p.update(first_failure={'phase':'original','role':'unknown','code_ordinal':None,'code':'clock','original_comparison':None,'actor':'unknown'}),'proof'),
    (lambda p:p.update(cleanup_failures=[{'phase':'cleanup','role':'unknown','code_ordinal':None,'code':'cleanup','original_comparison':None,'actor':'unknown'}]),'proof'),
    (lambda p:p.update(original_profile_proof=None),'private_aggregate'),
    (lambda p:p.update(private_model_aggregate=None),'proof'),
])
def test_closed_status_alone_never_closes_the_observation(change,code):
    """SI-CR28-018: the closed packet's own facts must agree with its status string."""
    payload=envelope();change(payload)
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();console.log(JSON.stringify((await p).summary()));",payload)
    assert result['status']=='incomplete' and result['first_failure']==code and result['source_qualified'] is False


def test_incomplete_producer_never_closes_the_observation():
    """SI-CR28-018: a clean exit does not outrank the producer's own status."""
    payload=envelope();payload.update(status='incomplete')
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();console.log(JSON.stringify((await p).summary()));",payload)
    assert result['status']=='incomplete' and result['producer_status']=='incomplete' and result['first_failure']=='proof'


def test_private_aggregate_must_be_the_one_the_proof_commits_to():
    """SI-CR28-018: a valid aggregate with another hash is not the retained report."""
    payload=envelope();payload['private_model_aggregate']['full']['member_count']=2
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();console.log(JSON.stringify((await p).summary()));",payload)
    assert result['status']=='incomplete' and result['first_failure']=='private_aggregate' and not result['private_model_aggregate_present']


@pytest.mark.parametrize('field',['profile_sha256','code_mapping_sha256'])
def test_proof_must_bind_the_registered_profile_and_five_code_map(field):
    """SI-CR28-018: re-signed, so only the named pin can refuse."""
    payload=envelope();proof=payload['original_profile_proof'];proof[field]='f'*64;del proof['observation_sha256'];proof['observation_sha256']=sha(canonical(proof))
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.close();console.log(JSON.stringify((await p).summary()));",payload)
    assert result['status']=='incomplete' and result['first_failure']=='proof'


@pytest.mark.parametrize('before',["w.child.emit('exit',0,null);","w.child.exitCode=0;"])
def test_exited_child_group_is_never_signalled_during_shutdown(before):
    """SI-CR28-018: the group id may already belong to someone else after exit."""
    result=run_node("const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();"+before+"""
w.advance(178501);w.close();const r=await p;console.log(JSON.stringify({signals:w.signals,s:r.summary()}));""")
    assert result['signals']==[] and result['s']['status']=='incomplete'


def test_missing_stderr_EOF_never_closes_the_observation():
    """SI-CR28-018: stdout EOF alone does not prove the child's streams closed."""
    result=run_node("""const w=setup();const p=m.observeOnceForTests(encodedConfig,w.seams);w.send();w.child.stdout.emit('end');w.child.exitCode=0;
w.child.emit('exit',0,null);w.child.emit('close',0,null);const r=await p;console.log(JSON.stringify(r.summary()));""")
    assert result['status']=='incomplete' and result['first_failure']=='EOF' and result['stderr_EOF'] is False
