"""One new offline full current-EOD crosswalk over fixed authenticated DATA.

Two unchanged technical guard groups retain all eight original DATA file
descriptors while fresh genuine inputs and the full BA inventory are checked.
Private publication follows both normal returns. No provider/QC contact,
old operation replay, source selection, price or formal identity admission.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time
from types import SimpleNamespace

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import run_arv2_r298_eodhd_catalog_continuation as ba
from scripts import arv2_r298_ba_source_binding as anchor
from scripts import arv2_r298_aa_source_binding as aa_anchor
from scripts import arv2_r298_ac_source_binding as ac_anchor
from scripts import arv2_r298_eodhd_crosswalk as crosswalk
from scripts import arv2_r298_fixed_data_guard as guard_module
from scripts import arv2_r298_all_route_worker_v2 as worker

SOURCE=ROOT/'scripts/prepare_arv2_r298_eodhd_crosswalk.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_eodhd_crosswalk/R326-20261027-BB'
SCHEMA='arv2-r298-offline-full-EODHD-crosswalk-bb-v1'
admitted,environment,PYTHON=ba.admitted,ba.environment,ba.PYTHON
canonical,sha,pin,parse,metadata=ba.canonical,ba.sha,ba.pin,ba.parse,ba.metadata
SECONDS,VALIDATOR_SECONDS,MAX_OUTPUT,MAX_PRIVATE=300,30,131072,64*1024*1024
MAX_COMBINED_INPUT,MIN_FREE_DISK=96*1024*1024,192*1024*1024
PRIVATE_NAME='crosswalk-private.json'
SOURCE_PLAN={
    'aa':{'relative_path':'artifacts/analyst_revisions_v2/newrule_all_routes_offline/R326-20261027-AA/routes-private.json',
        'byte_count':19895631,'sha256':'3776f03b4941d8e6d014dee19f5ee8a05080f214ab7f502d10738f00a689f561'},
    'ac':{'relative_path':'artifacts/analyst_revisions_v2/newrule_price_lineage/R326-20261027-AC/price-lineage-private.json',
        'byte_count':16344399,'sha256':'4366e1e8a218fb21afc6ef3d88dfed9c2ab8b784a7718a405616850e1a4d6ddc'},
    'ap_plan':{'relative_path':'artifacts/analyst_revisions_v2/newrule_raw_price_acquisition/R326-20261027-AP/plan-private.json',
        'byte_count':2927971,'sha256':'7703c8e29d7bef5928b0a776628759ff97715b003045c2c00df2b01e7b03f51e'}}
CATALOG_PLAN={
    'seed':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-BA/seed-bodies.bin',
        'byte_count':16140080,'sha256':'02d64c177446409f43f6f443cda77afa4c6e9503ebb17844a9910a52b1093005'},
    'capture':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-BA/mapping-bodies.bin',
        'byte_count':11322284,'sha256':'1b601920ea0bf26c2f7354b99276cdd88d0e9f979b4337fa8badcb5a85fe8596'},
    'journal':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-BA/requests.jsonl',
        'byte_count':10890,'sha256':'8f76f8af4e47ceef0e6b03cc51df6ac72ec2c1c1386e9a7b58609f68c0ccf128'},
    'index':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-BA/catalog-index.json',
        'byte_count':15152,'sha256':'ca250b3555a554e9a805cc5befaf4bf095d16760075489493983ec73033aad29'},
    'source_metadata':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-BA/source-metadata.json',
        'byte_count':3658,'sha256':'c0d738188e352a490a789ecb3522c900591af1d8f971828846c1295c4eb27038'}}
FACT_SHA256='11efb22aaf20aeb65445868fc86d5a2d049bdd4a43615fd1278c8d6ac256ed3d'
SOURCE_SHA256='c0d738188e352a490a789ecb3522c900591af1d8f971828846c1295c4eb27038'
PROVIDER_SHA256='972e564b42ec5845bd359575964e06e3e5e5e753fb653493a38b4f7963330ae0'
AUTH_SHA256='bfa32f26ad55fc9a0446e7d8cdc89886a9bc77239cd8125689f25285948c1e23'
AA_SUMMARY_SHA256='2f78e37c12d1781f73ecb4d2df6e131b501dfe114f5d5d4169f40f02afd68b22'
AC_SUMMARY_SHA256='112daa665daefaaef723e3fd3379196f4d85a7d920f80edf0b9d0fdb063ee5ef'
CROSSWALK_PROFILE_SHA256='9ece75189b6f16625388a8beb9b360f23371e6f332508dc6963fd48de0feca4e'
NEW_PINS={
    'scripts/run_arv2_r298_eodhd_catalog_continuation.py':'8eb6b92db6c8833998cd2fef4388091f8e65c6dbc8e0a77a79f86d9b2d4dc6e7',
    'scripts/arv2_r298_ba_source_binding.py':'fdc6cd8eb38a017961f67b351ae525e280e3e8bd6c141a1af7710c7bf27dc0d4',
    'scripts/arv2_r298_eodhd_crosswalk.py':'39464645b7acb8187eac2209e7e994d74ddd3c077911cb32d1a9c1820ffd6843',
    'scripts/arv2_r298_aa_source_binding.py':'e881c694b516ad7d773ab6c3a8ef996873616862dc55ffda4e371733f6c6bd11',
    'scripts/arv2_r298_ac_source_binding.py':'112221b42d0c35065fec96ea55dc124c2e66101d8e6011bd91160d4a97576d0b',
    'scripts/arv2_r298_all_route_worker_v2.py':'d236e3f0113046ca638296823d880ac8a93e8d31e65047b57c26fcba5dc35da1'}
FALSE_FLAGS={**crosswalk.FALSE_FLAGS,'provider_contact':False,'credential_access':False,'QC_contact':False,
    'old_control_read':False,'old_operational_entrypoint_called':False,'licensed_rows_disclosed':False,
    'source_or_price_admission_granted':False,'result_cell':0}
FINITE=frozenset(('host','arguments','environment','git_state','source_pin','source_binding','deadline','input_budget',
    'disk_budget','claim_spent','output_changed','output_security','output_write','output_bound','source_bytes','genuine',
    'catalog','inventory','private_binding','output','os_error','unknown'))|frozenset('guard_'+code for code in guard_module.FINITE)


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args=BaseException.args.__get__(error)
        return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is guard_module.Refused:return 'guard_'+guard_module.finite(error)
    if type(error) is environment.EnvironmentRefused:return 'environment'
    if type(error) is admitted.helpers.Deadline:return 'deadline'
    if type(error) is crosswalk.Refused:return 'deadline' if crosswalk.finite(error)=='deadline' else 'catalog'
    if type(error) is worker.previous.Refused:return 'genuine'
    if type(error) is ba.Refused:return 'catalog'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline) and 0<deadline-time.monotonic()<=SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def checked_groups():
    a,b=guard_module.checked_plan(SOURCE_PLAN),guard_module.checked_plan(CATALOG_PLAN)
    require(len(a)==3 and len(b)==5 and sum(row['byte_count'] for row in (*a.values(),*b.values()))<=MAX_COMBINED_INPUT,
        'input_budget');return a,b


def source_context():
    fact=anchor.observed_fact();source_observation=anchor.source_summary();provider=anchor.provider_summary();authentication=anchor.authentication_summary()
    require(sha(canonical(fact))==FACT_SHA256 and sha(canonical(source_observation))==SOURCE_SHA256
        and sha(canonical(provider))==PROVIDER_SHA256 and sha(canonical(authentication))==AUTH_SHA256,'source_binding')
    source={'observation':source_observation,'source_metadata_pin':pin(canonical(source_observation))}
    ba.validate_source(source);ba.validate_provider(provider,success=True);ba.validate_authentication(authentication,source,provider)
    require(fact['binding']=={'schema':ba.SCHEMA,'expected_head':'0b6c42d1c66dbe3fdb704443ee803693a2c7df50',
        'caller_sha256':NEW_PINS['scripts/run_arv2_r298_eodhd_catalog_continuation.py'],
        'profile_sha256':'c2db43c6f1b664de393418755f7917d2b9fad327e7e447c6d06b803a8084aac3'}
        and fact['data_plan']==anchor.data_plan()==CATALOG_PLAN,'source_binding')
    old=SimpleNamespace(**{key:value for key,value in fact['binding'].items() if key!='schema'})
    packets={role:{'binding':fact['binding'],'role':role,'result':result,'failure_code':None}
        for role,result in (('source',source),('provider',provider),('authenticate',authentication))}
    for role,key in (('source','source_actual'),('provider','provider_actual'),('authenticate','authentication_actual')):
        ba.ap._actual(fact[key],zero=True);ba._packet_join(packets[role],fact[key],old,role)
    result={'schema':ba.SCHEMA,'stage':'postflight','credential_handoff_complete':True,'source':source,
        'source_actual':fact['source_actual'],'provider':provider,'provider_actual':fact['provider_actual'],
        'authentication':authentication,'authentication_actual':fact['authentication_actual'],'child_packets':packets,
        'prior_context':ba.source_context(),'provider_request_count':None,'post_checks_complete':True,**ba.FALSE_FLAGS}
    report=pin(canonical({**fact['binding'],'result':result}));require(report==fact['report'],'source_binding')
    raw=canonical({'binding':fact['binding'],'outcome':{'result':result,'report':report}})+bytes([10])
    ba.validate_output(raw,0,old)
    for role in ('producer','validator'):
        actual=fact[role]
        try:ba.ap.public_transport._actual_metadata(actual)
        except BaseException:raise Refused('source_binding') from None
        require(type(actual['actual_exit']) is int and actual['actual_exit']==0 and actual['spawn_observed'] is True
            and actual['bound'] is None and actual['stderr_bytes']==0 and actual['stderr_sha256']==sha(b'')
            and actual['stdout_bytes']==len(raw) and actual['stdout_sha256']==sha(raw),'source_binding')
    require(fact['application_dispatch_intents']==fact['completed_HTTP200_bodies']==110
        and type(fact['application_dispatch_intents']) is type(fact['completed_HTTP200_bodies']) is int
        and fact['provider_request_count'] is None and fact['bounded_catalog_protocol_complete'] is True
        and fact['source_guard_normal_return'] is fact['post_checks_complete'] is True,'source_binding')
    for field in ('new_operation_or_read_granted','identity_crosswalk_admitted','price_input_admitted',
        'complete_strategy_price_coverage_proven','point_in_time_proven','permanent_identity_proven','formal_forward_ready','paper_or_live_ready'):
        require(fact[field] is False,'source_binding')
    aa=aa_anchor.expected_summary();ac=ac_anchor.expected_summary()
    require(sha(canonical(aa['routing_summary']))==AA_SUMMARY_SHA256 and sha(canonical(ac))==AC_SUMMARY_SHA256
        and aa_anchor.observed_fact()['private_file']==SOURCE_PLAN['aa'] and ac_anchor.observed_fact()['private_file']==SOURCE_PLAN['ac'],
        'source_binding')
    for prior in (aa_anchor.observed_fact(),ac_anchor.observed_fact()):
        for role in ('producer','validator'):
            require(type(prior[role]['actual_exit']) is int and prior[role]['actual_exit']==0
                and prior[role]['spawn_observed'] is True and prior[role]['bound'] is None,'source_binding')
    return {'source':source,'provider':provider,'authentication':authentication,'BA_fact_sha256':FACT_SHA256,
        'AA_routing_summary':aa['routing_summary'],'AC_summary':ac,'genuine_input_binding':aa['input_binding']}


def inventory_context(context):
    authentication=context['authentication'];frames=ba.SOURCE_FRAME_PINS
    value={'schema':crosswalk.INVENTORY_SCHEMA,'aw_authentication_sha256':AUTH_SHA256,
        'active':{'body_pin':dict(frames[0]),**{key:authentication['active'][key] for key in ('row_count','ordered_records_sha256')}},
        'delisted':{'body_pin':dict(frames[1]),**{key:authentication['delisted'][key] for key in ('row_count','ordered_records_sha256')}},
        'mapping':{key:authentication['mapping'][key] for key in ('row_count','ordered_records_sha256')}}
    return crosswalk._inventory_metadata(value)


def pins():
    values=ba.pins()
    for name,value in NEW_PINS.items():
        require(name not in values or values[name]==value,'source_pin');values[name]=value
    return values


def profile_record():
    checked_groups();source_context()
    require(sha(canonical(crosswalk.profile_record()))==CROSSWALK_PROFILE_SHA256,'source_binding')
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),'control':str(CONTROL),
        'python':str(PYTHON),'source_pins':pins(),'seconds':SECONDS,'validator_seconds':VALIDATOR_SECONDS,
        'maximum_output_bytes':MAX_OUTPUT,'maximum_private_bytes':MAX_PRIVATE,'maximum_combined_input_bytes':MAX_COMBINED_INPUT,
        'minimum_free_disk_bytes':MIN_FREE_DISK,'source_plan':SOURCE_PLAN,'catalog_plan':CATALOG_PLAN,
        'source_guard_profile':guard_module.profile_record(SOURCE_PLAN),'catalog_guard_profile':guard_module.profile_record(CATALOG_PLAN),
        'BA_fact_sha256':FACT_SHA256,'BA_source_sha256':SOURCE_SHA256,'BA_provider_sha256':PROVIDER_SHA256,
        'BA_authentication_sha256':AUTH_SHA256,'crosswalk_profile_sha256':CROSSWALK_PROFILE_SHA256,
        'purpose':'new_offline_full_current_EOD_crosswalk_with_fresh_genuine_binding_and_authenticated_complete_BA_inventory',
        'both_groups_all_eight_whole_pins_before_any_DATA_JSON_or_genuine_load':True,
        'fresh_genuine_6151_bindings_and3466_sessions_unchanged_inside_guards':True,
        'pure_BA_analyse_required_not_operational_replay':True,'all113_bodies_and110346_mapping_rows':True,
        'both_guard_normal_returns_before_private_publication':True,'legacy_AW_named_API_fields_bind_complete_BA_authentication':True,
        'all6151_and8_assignments_retained_no_selector_or_source_fallback':True,
        'AP_role_and_potential_reason_counts_derived_inside_source_guards':True,
        'private_serialized_cap_is_not_total_Python_RAM_guarantee':True,
        'deadline_uninterruptible_IO_host_suspension_qualification':True,**FALSE_FLAGS}


def binding(args):return {'schema':SCHEMA,'expected_head':args.expected_head,'caller_sha256':args.caller_sha256,
    'profile_sha256':args.profile_sha256}


def preflight(args,deadline):
    require(not admitted.v5._under_test() and sys.platform=='darwin' and os.name=='posix' and sys.version_info[:2]==(3,13)
        and Path(sys.executable)==PYTHON and Path.cwd()==ROOT and ROOT.resolve()==ROOT and Path(__file__).absolute()==SOURCE,'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256),'arguments')
    ba.ar._credential_free();environment._require_environment();source_context();checked_groups()
    for command,expected in ((['rev-parse','--show-toplevel'],str(ROOT)),(['branch','--show-current'],admitted.frozen.BRANCH),
            (['rev-parse','HEAD'],args.expected_head),(['status','--porcelain'],'')):
        require(admitted.v5._git(command,deadline).decode('ascii').strip()==expected,'git_state')
    for name,expected in pins().items():require(sha((ROOT/name).read_bytes())==expected,'source_pin')
    require(sha(SOURCE.read_bytes())==args.caller_sha256 and sha(admitted.v5._git(
        ['cat-file','blob',args.expected_head+':'+SOURCE.relative_to(ROOT).as_posix()],deadline,256*1024))==args.caller_sha256
        and sha(canonical(profile_record()))==args.profile_sha256,'source_pin');remaining(deadline)


def native_profile(mode):
    require(mode in ('produce','validate'),'arguments');value='(version 1)(allow default)(deny network*)'
    value+=''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))'
    allowed=f'(require-not (subpath "{ROOT/".pytest_cache"}"))(require-not (literal "/dev/null"))'
    if mode=='produce':allowed+=f'(require-not (subpath "{CONTROL}"))(require-not (literal "{CONTROL.parent}"))'
    value+='(deny file-write* (require-all '+allowed+'))'
    if mode=='validate':return value+f'(deny file-read* (subpath "{ROOT/"artifacts"}"))'
    leaves=[*(ROOT/row['relative_path'] for plan in (SOURCE_PLAN,CATALOG_PLAN) for row in plan.values()),
        worker.previous.LINEAGE,CONTROL.parent]
    policy=ba.ap.previous._artifact_policy(leaves,package=worker.previous.PACKAGE)
    needle=f'(require-all (subpath "{ROOT/"artifacts"}")';require(policy.count(needle)==1,'source_binding')
    return value+policy.replace(needle,needle+f' (require-not (subpath "{CONTROL}"))',1)


def _security(fd):
    try:return ba.ap.security.snapshot(fd)
    except ba.ap.security.Refusal:raise Refused('output_security') from None


class Store:
    def __init__(self):
        self.fd,self.chain,self.files=None,[],{};fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for index,part in enumerate(CONTROL.parts[1:],1):
                here=Path(*CONTROL.parts[:index+1])
                if here in (CONTROL.parent,CONTROL):
                    try:os.mkdir(part,0o700,dir_fd=fd);os.fsync(fd)
                    except FileExistsError:require(here!=CONTROL,'claim_spent')
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=nxt;self.chain.append((os.fstat(fd).st_dev,os.fstat(fd).st_ino))
            self.fd,self.security=fd,_security(fd);self.verify()
        except BaseException:os.close(fd);raise
    def __enter__(self):return self
    def __exit__(self,*_):
        failed=False
        for row in self.files.values():
            try:os.close(row['fd'])
            except OSError:failed=True
        try:os.close(self.fd)
        except OSError:failed=True
        require(not failed,'output_changed')
    def verify(self):
        other,chain=admitted._storage_module()._walk(CONTROL)
        try:
            info=os.fstat(other)
            require(chain==tuple(self.chain) and metadata(info)==metadata(os.fstat(self.fd)) and _security(self.fd)==self.security
                and stat.S_IMODE(info.st_mode)==0o700 and info.st_uid==os.getuid() and set(os.listdir(other))==set(self.files),'output_changed')
            for name,row in self.files.items():
                info=os.stat(name,dir_fd=other,follow_symlinks=False)
                require(metadata(info)==row['metadata']==metadata(os.fstat(row['fd'])) and stat.S_ISREG(info.st_mode)
                    and stat.S_IMODE(info.st_mode)==0o600 and info.st_uid==os.getuid() and info.st_nlink==1
                    and _security(row['fd'])==row['security'],'output_changed')
        finally:os.close(other)
    def write(self,name,raw,deadline):
        self.verify();maximum=MAX_PRIVATE if name==PRIVATE_NAME else MAX_OUTPUT
        require(name in ('claim.json',PRIVATE_NAME,'report.json','failure.json') and name not in self.files
            and len(self.files)<4 and type(raw) is bytes and 0<len(raw)<=maximum,'output_bound')
        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        old=metadata(os.fstat(fd));self.files[name]={'fd':fd,'metadata':old,'security':_security(fd)}
        for offset in range(0,len(raw),65536):remaining(deadline);ba._write(fd,raw[offset:offset+65536])
        fresh=metadata(os.fstat(fd));require(fresh[:6]==old[:6] and fresh[9]==old[9] and fresh[6]==len(raw),'output_changed')
        self.files[name]['metadata']=fresh;os.fsync(self.fd);self.verify();digest=hashlib.sha256()
        for offset in range(0,len(raw),65536):
            remaining(deadline);chunk=os.pread(fd,min(65536,len(raw)-offset),offset)
            require(chunk,'output_write');digest.update(chunk)
        require(digest.hexdigest()==sha(raw),'output_write');self.verify();return pin(raw)


def _assert_bytes(values,plan):
    require(type(values) is dict and set(values)==set(plan)
        and all(type(values[role]) is bytes and pin(values[role])=={key:plan[role][key] for key in ('byte_count','sha256')}
            for role in plan),'source_bytes')


def _catalog_data(values,context,deadline):
    source,provider=context['source'],context['provider']
    require(values['source_metadata']==canonical(source['observation']),'inventory')
    authenticated=ba.analyse(values['seed'],values['capture'],values['index'],values['journal'],source,provider,deadline)
    require(authenticated==context['authentication'] and sha(canonical(authenticated))==AUTH_SHA256,'inventory')
    seed=ba._seed_bodies(values['seed']);index=ba._decode(values['index'],'index',ba.MAX_INDEX)
    mapping=list(ba._mapping_envelope(seed[2],0))
    for ordinal,entry in enumerate(index['bodies']):
        remaining(deadline);start=entry['offset']+8;length=entry['body']['byte_count']
        body=values['capture'][start:start+length]
        require(pin(body)==entry['body'],'inventory');mapping.extend(ba._mapping_envelope(body,(ordinal+1)*ba.PAGE_SIZE))
    require(len(mapping)==110346,'inventory');return seed[0],seed[1],mapping


def _genuine(public,selected,rows,context):
    require(public==context['genuine_input_binding'] and len(rows)==6151,'genuine')
    axis=worker.previous.identity.evaluator._parse_sessions(tuple(selected['session_axis']))
    require(len(axis)==3466 and sha(canonical(list(axis)))==crosswalk.prices.FULL_AXIS_SHA256,'genuine')
    crosswalk.prices._axis(axis)


def _breakdown(private,summary):
    record=private.private_record()
    require(type(record) is dict and set(record)=={'schema','source_fingerprint','stocks','funds'}
        and record['schema']==crosswalk.PRIVATE_SCHEMA and record['source_fingerprint']==summary['source_fingerprint']
        and type(record['stocks']) is type(record['funds']) is list and len(record['stocks'])==6151 and len(record['funds'])==8,
        'private_binding')
    groups=defaultdict(lambda:{'stock_count':0,'disposition_counts':Counter(),'unresolved_reason_counts':Counter()})
    for item in record['stocks']:
        require(type(item) is dict and item.get('AP_role') in crosswalk.AP_ROLES and type(item.get('potential')) is bool
            and item.get('status') in ('matched_current_crosswalk','unresolved'),'private_binding')
        group=groups[(item['AP_role'],item['potential'])];group['stock_count']+=1;group['disposition_counts'][item['status']]+=1
        if item['status']=='unresolved':
            require(item.get('reason') in crosswalk.REASONS,'private_binding');group['unresolved_reason_counts'][item['reason']]+=1
        else:require(item.get('reason') is None,'private_binding')
    value=[{'AP_role':role,'potential':potential,'stock_count':group['stock_count'],
        'disposition_counts':dict(sorted(group['disposition_counts'].items())),
        'unresolved_reason_counts':dict(sorted(group['unresolved_reason_counts'].items()))}
        for (role,potential),group in sorted(groups.items())]
    validate_breakdown(value,summary);return value


def validate_breakdown(value,summary):
    require(type(value) is list and 0<len(value)<=2*len(crosswalk.AP_ROLES),'output')
    identities=[];roles=Counter();dispositions=Counter();reasons=Counter();potential_counts=Counter()
    for row in value:
        require(type(row) is dict and set(row)=={'AP_role','potential','stock_count','disposition_counts','unresolved_reason_counts'}
            and row['AP_role'] in crosswalk.AP_ROLES and type(row['potential']) is bool
            and type(row['stock_count']) is int and 0<row['stock_count']<=6151
            and type(row['disposition_counts']) is type(row['unresolved_reason_counts']) is dict
            and set(row['disposition_counts'])<={'matched_current_crosswalk','unresolved'}
            and set(row['unresolved_reason_counts'])<=crosswalk.REASONS
            and all(type(count) is int and count>0 for counts in (row['disposition_counts'],row['unresolved_reason_counts']) for count in counts.values())
            and sum(row['disposition_counts'].values())==row['stock_count']
            and sum(row['unresolved_reason_counts'].values())==row['disposition_counts'].get('unresolved',0),'output')
        identities.append((row['AP_role'],row['potential']));roles[row['AP_role']]+=row['stock_count']
        potential_counts[row['potential']]+=row['stock_count'];dispositions.update(row['disposition_counts']);reasons.update(row['unresolved_reason_counts'])
    require(identities==sorted(set(identities)) and dict(roles)==summary['AP_stock_role_counts']
        and dict(dispositions)==summary['disposition_counts']['stocks'] and dict(reasons)==summary['reason_counts']['stocks']
        and potential_counts[True]==5641 and potential_counts[False]==510,'output')
    return value


def construct(context,deadline):
    with guard_module.FixedDataGuard(SOURCE_PLAN,deadline=deadline) as source_guard:
        with guard_module.FixedDataGuard(CATALOG_PLAN,deadline=deadline) as catalog_guard:
            source_values=source_guard.read_all_once();catalog_values=catalog_guard.read_all_once()
            _assert_bytes(source_values,SOURCE_PLAN);_assert_bytes(catalog_values,CATALOG_PLAN)
            # All eight DATA leaves are byte-authenticated before any DATA JSON
            # or the independently guarded genuine package loader is used.
            plain=worker._load_plain(deadline);initial,record,selected,rows,public=worker._catalog(plain,deadline)
            _genuine(public,selected,rows,context)
            active,delisted,mappings=_catalog_data(catalog_values,context,deadline)
            expected_inventory=inventory_context(context)
            summary,private=crosswalk.prepare(rows,source_values['aa'],source_values['ac'],source_values['ap_plan'],
                active,delisted,mappings,expected_aa_routing_summary=context['AA_routing_summary'],
                expected_ac_summary=context['AC_summary'],expected_aw_inventory=expected_inventory,deadline=deadline)
            crosswalk.validate_summary(summary)
            require(summary['source_pins']['AW']==expected_inventory and type(private) is crosswalk.PrivateCrosswalk
                and private.summary_sha256==crosswalk.digest(summary) and type(private._raw) is bytes
                and private.byte_count==len(private._raw)<=MAX_PRIVATE and private.sha256==sha(private._raw)
                and summary['private_payload_pin']==pin(private._raw),'private_binding')
            breakdown=_breakdown(private,summary)
            worker._catalog_unchanged(plain,initial,record,selected,deadline)
            source_guard.verify();catalog_guard.verify()
            source_receipt=guard_module.validate_receipt(source_guard.receipt(),SOURCE_PLAN)
            catalog_receipt=guard_module.validate_receipt(catalog_guard.receipt(),CATALOG_PLAN)
            environment.require_safe_environment();remaining(deadline)
            private_raw=private._raw
    # Both source contexts have returned normally before any private publication.
    return {'crosswalk_summary':summary,'stock_AP_role_potential_breakdown':breakdown,
        'genuine_input_binding':public,'source_receipt':source_receipt,
        'catalog_receipt':catalog_receipt,'both_source_guards_normal_return':True,'genuine_input_unchanged':True},private_raw


def failure(args,error):return {'binding':binding(args),'failure_code':finite(error),'allocation_unknown':True,**FALSE_FLAGS}


def run(args,deadline):
    context=source_context();checked_groups();info=os.statvfs(ROOT)
    require(info.f_bavail*info.f_frsize>=MIN_FREE_DISK,'disk_budget')
    with Store() as store:
        store.write('claim.json',canonical(binding(args)),deadline)
        try:
            result,private_raw=construct(context,deadline)
            private_pin=store.write(PRIVATE_NAME,private_raw,deadline);private_raw=None
            require(private_pin==result['crosswalk_summary']['private_payload_pin'],'private_binding')
            preflight(args,deadline);environment.require_safe_environment();store.verify()
            result={'schema':SCHEMA,**result,'private_pin':private_pin,'BA_fact_sha256':FACT_SHA256,
                'BA_authentication_sha256':AUTH_SHA256,'post_checks_complete':True,**FALSE_FLAGS}
            validate_result(result)
            report=store.write('report.json',canonical({**binding(args),'result':result}),deadline);store.verify()
            return {'result':result,'report':report}
        except BaseException as error:
            value=failure(args,error)
            try:store.write('failure.json',canonical(value),deadline)
            except BaseException:pass
            return {'failure':value}


def validate_result(value):
    require(type(value) is dict and set(value)=={'schema','crosswalk_summary','stock_AP_role_potential_breakdown','genuine_input_binding','source_receipt',
        'catalog_receipt','both_source_guards_normal_return','genuine_input_unchanged','private_pin','BA_fact_sha256',
        'BA_authentication_sha256','post_checks_complete',*FALSE_FLAGS} and value['schema']==SCHEMA
        and value['both_source_guards_normal_return'] is value['genuine_input_unchanged'] is value['post_checks_complete'] is True
        and value['BA_fact_sha256']==FACT_SHA256 and value['BA_authentication_sha256']==AUTH_SHA256
        and type(value['result_cell']) is int and value['result_cell']==0
        and all(value[key] is False for key in FALSE_FLAGS if key!='result_cell'),'output')
    context=source_context();crosswalk.validate_summary(value['crosswalk_summary'])
    validate_breakdown(value['stock_AP_role_potential_breakdown'],value['crosswalk_summary'])
    require(value['crosswalk_summary']['source_pins']['AW']==inventory_context(context)
        and value['genuine_input_binding']==context['genuine_input_binding']
        and value['private_pin']==value['crosswalk_summary']['private_payload_pin'],'output')
    guard_module.validate_receipt(value['source_receipt'],SOURCE_PLAN);guard_module.validate_receipt(value['catalog_receipt'],CATALOG_PLAN)


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT and raw.endswith(bytes([10])) and raw.count(bytes([10]))==1
        and type(actual_exit) is int and actual_exit in (0,2),'output');value=parse(raw[:-1])
    require(value.get('binding')==binding(args),'output')
    if set(value)=={'binding','failure_code','allocation_unknown',*FALSE_FLAGS}:
        _failure(value,actual_exit);return value
    require(set(value)=={'binding','outcome'} and type(value['outcome']) is dict,'output');outcome=value['outcome']
    if set(outcome)=={'failure'}:
        require(actual_exit==2 and outcome['failure'].get('binding')==binding(args),'output');_failure(outcome['failure'],actual_exit)
    else:
        require(actual_exit==0 and set(outcome)=={'result','report'},'output');validate_result(outcome['result'])
        require(outcome['report']==pin(canonical({**binding(args),'result':outcome['result']})),'output')
    return value


def _failure(value,actual_exit):
    require(actual_exit==2 and type(value) is dict and set(value)=={'binding','failure_code','allocation_unknown',*FALSE_FLAGS}
        and value['failure_code'] in FINITE and value['allocation_unknown'] is True
        and type(value['result_cell']) is int and value['result_cell']==0
        and all(value[key] is False for key in FALSE_FLAGS if key!='result_cell'),'output')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('produce','validate'))
    for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--actual-exit',type=int);args=parser.parse_args(argv)
    deadline=time.monotonic()+(SECONDS if args.operation=='produce' else VALIDATOR_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline);environment._bootstrap_cli_logging()
            if args.operation=='validate':
                raw=sys.stdin.buffer.read(MAX_OUTPUT+1);validate_output(raw,args.actual_exit,args);sys.stdout.buffer.write(raw);return 0
            outcome=run(args,deadline);raw=canonical({'binding':binding(args),'outcome':outcome})+bytes([10])
            code=2 if 'failure' in outcome else 0;validate_output(raw,code,args);sys.stdout.buffer.write(raw);return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure(args,error))+bytes([10]));return 2


if __name__=='__main__':raise SystemExit(main())
