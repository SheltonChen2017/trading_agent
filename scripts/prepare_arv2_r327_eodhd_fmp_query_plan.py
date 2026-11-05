"""One offline retained-evidence EODHD/FMP query preparation.

All four DATA byte pins authenticate before parsing. Every selected original
case and every blocker remains; this plan performs no provider or QC action
and grants no identity alias, source replacement or price admission.
"""
from __future__ import annotations
import argparse
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import inspect_arv2_r327_available_history_identity as previous
from scripts import arv2_r327_eodhd_fmp_query_plan as query
from scripts import arv2_r298_fixed_data_guard as guard_module

ar,ap=previous.ar,previous.ap
admitted,environment,PYTHON=previous.admitted,previous.environment,previous.PYTHON
canonical,sha,pin,parse,metadata=previous.canonical,previous.sha,previous.pin,previous.parse,previous.metadata
SOURCE=ROOT/'scripts/prepare_arv2_r327_eodhd_fmp_query_plan.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_eodhd_fmp_query_plan/R327-20261028-J'
SCHEMA='arv2-r327-offline-EODHD-FMP-query-preparation-j-v1'
SECONDS,OUTER_SECONDS,VALIDATOR_SECONDS=300,330,30
MAX_OUTPUT,MAX_PRIVATE,MIN_FREE_DISK=131072,16*1024*1024,64*1024*1024
PRIVATE_NAME='fmp-query-plan-private.json'
I_FACT_SHA256='8fd5f90a0990b82a08f18a5037a54ed772c9c8c033bd2430501bdfd88620874e'
DATA_PLAN={
 'identity':{'relative_path':'artifacts/analyst_revisions_v2/newrule_available_history_identity/R327-20261027-I/identity-demand-private.json',
  'byte_count':4984462,'sha256':'c85ae5ddf2e918d194f6aa2939ee1249229d0989f75c334ef92ea793b61b711d'},
 'crosswalk':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_crosswalk/R326-20261027-BB/crosswalk-private.json',
  'byte_count':13445076,'sha256':'5006dc2f1313d02c18f521172e2e454ca190a0191e2f85799b54a9d7d963d753'},
 'seed':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-BA/seed-bodies.bin',
  'byte_count':16140080,'sha256':'02d64c177446409f43f6f443cda77afa4c6e9503ebb17844a9910a52b1093005'},
 'capture':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-BA/mapping-bodies.bin',
  'byte_count':11322284,'sha256':'1b601920ea0bf26c2f7354b99276cdd88d0e9f979b4337fa8badcb5a85fe8596'}}
NEW_PINS={
 'scripts/inspect_arv2_r327_available_history_identity.py':'70b171d141798951d4a136c92e131454a4eec58f8ee6ba7ebab8a737a919250f',
 'scripts/observe_arv2_r327_available_history_identity.py':'02ae6ea51f749c60a90e216a9d8b00f268efe9532593c7f0fdef7f130ad68039',
 'scripts/arv2_r327_i_source_binding.py':'44405001183804020d8b211d79846d8ea70019758059cc73878cca883bac6416',
 'scripts/arv2_r327_eodhd_fmp_query_plan.py':'ccbd09de62703115adb971025461eb861b3fe68f52cccbe935520cd72a559d59'}
FALSE_FLAGS={'provider_contact':False,'credential_access':False,'QC_contact':False,'Safari_access':False,
 'old_operation_invoked':False,'old_control_read':False,'fresh_genuine_input_reauthenticated':False,
 'original_identifiers_rewritten':False,'different_FIGI_accepted':False,'CUSIP_only_identity_admitted':False,
 'nonempty_invalid_CUSIP_overridden':False,'vendor_collision_cleared':False,'source_assignments_changed':False,
 'price_input_admitted':False,'complete_strategy_price_coverage_proven':False,'future_K_authorized':False,
 'strategy_result_accepted':False,'point_in_time_proven':False,'permanent_master_proven':False,
 'formal_forward_ready':False,'paper_or_live_ready':False,'licensed_rows_disclosed':False,
 'continuous_integrity_proven':False}
FINITE=frozenset(('host','arguments','environment','git_state','source_pin','source_binding','deadline','disk_budget',
 'claim_spent','output_changed','output_security','output_write','output_bound','source_bytes','private_binding',
 'query','output','os_error','unknown'))|frozenset('guard_'+code for code in guard_module.FINITE) \
 |frozenset('query_'+code for code in query.FINITE if code!='deadline')


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
    if type(error) is query.Refused:
        code=query.finite(error)
        if code=='deadline':return 'deadline'
        return 'query_'+code if code in query.FINITE else 'query'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline) and 0<deadline-time.monotonic()<=SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def pins():
    result=previous.pins();require(len(result)==222,'source_pin')
    for name,value in NEW_PINS.items():
        require(_hash(value) and value!='0'*64 and (name not in result or result[name]==value),'source_pin')
        result[name]=value
    return result


def source_context():
    require(query.DATA_PLAN==DATA_PLAN,'source_binding')
    guard_module.checked_plan(DATA_PLAN)
    context=query.source_context()
    require(context['I_fact_sha256']==I_FACT_SHA256,'source_binding')
    return context


def profile_record():
    context=source_context()
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),'control':str(CONTROL),
      'python':str(PYTHON),'seconds':SECONDS,'outer_seconds':OUTER_SECONDS,'validator_seconds':VALIDATOR_SECONDS,
      'source_pins':pins(),'data_plan':DATA_PLAN,'data_total_bytes':45891902,'data_guard_profile':guard_module.profile_record(DATA_PLAN),
      'I_fact_sha256':I_FACT_SHA256,'source_context_sha256':sha(canonical(context)),
      'query_profile_sha256':sha(canonical(query.profile_record())),
      'maximum_output_bytes':MAX_OUTPUT,'maximum_private_output_bytes':MAX_PRIVATE,'maximum_owned_files':4,
      'minimum_free_disk_bytes':MIN_FREE_DISK,'claim_before_any_DATA_read':True,
      'all_four_external_byte_pins_before_any_DATA_JSON':True,
      'all_seed_and_capture_frame_headers_lengths_body_hashes_and_exact_extent_checked':True,
      'whole_retained_mapping_and_symbol_inventories_checked_before_five_case_selection':True,
      'all_five_original_cases_retained_including_blocked_and_no_query_cases':True,
      'original_FIGI_AND_original_checksum_CUSIP9_gates_preserved':True,
      'observed_ISIN_queries_only_no_country_or_ISIN_fabrication':True,
      'retained_I_BB_binding_proof_join_only_no_fresh_package_or_master_reassessment':True,
      'guard_normal_return_before_private_and_public_publication':True,
      'public_counts_hashes_finite_blockers_only_no_identifier_or_row_stdout':True,
      'native_producer_and_validator_deny_all_network_Keychains_security_CLI':True,
      'QC_and_Safari_owner_hold_preserved':True,'future_provider_contact_requires_separate_frozen_K_contract':True,
      'independent_top_level_validator_requires_observed_exit_not_report_alone':True,
      'deadline_uninterruptible_IO_host_suspension_qualification':True,**FALSE_FLAGS}


def binding(args):return {'schema':SCHEMA,'expected_head':args.expected_head,
 'caller_sha256':args.caller_sha256,'profile_sha256':args.profile_sha256}


def preflight(args,deadline):
    require(not admitted.v5._under_test() and sys.platform=='darwin' and os.name=='posix'
      and sys.version_info[:2]==(3,13) and Path(sys.executable)==PYTHON and Path.cwd()==ROOT
      and ROOT.resolve()==ROOT and Path(__file__).absolute()==SOURCE,'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
      and _hash(args.caller_sha256) and _hash(args.profile_sha256),'arguments')
    ar._credential_free();environment._require_environment();source_context()
    for command,expected in ((['rev-parse','--show-toplevel'],str(ROOT)),(['branch','--show-current'],admitted.frozen.BRANCH),
      (['rev-parse','HEAD'],args.expected_head),(['status','--porcelain'],'')):
        require(admitted.v5._git(command,deadline).decode('ascii').strip()==expected,'git_state')
    for name,value in pins().items():require(sha((ROOT/name).read_bytes())==value,'source_pin')
    require(sha(SOURCE.read_bytes())==args.caller_sha256 and sha(admitted.v5._git(
      ['cat-file','blob',args.expected_head+':'+SOURCE.relative_to(ROOT).as_posix()],deadline,256*1024))==args.caller_sha256
      and sha(canonical(profile_record()))==args.profile_sha256,'source_pin')
    remaining(deadline)


def native_profile(mode):
    require(mode in ('produce','validate'),'arguments')
    value='(version 1)(allow default)(deny network*)'
    value+=''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in
      ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))'
    allowed=f'(require-not (subpath "{ROOT/".pytest_cache"}"))(require-not (literal "/dev/null"))'
    if mode=='produce':allowed+=f'(require-not (subpath "{CONTROL}"))(require-not (literal "{CONTROL.parent}"))'
    value+='(deny file-write* (require-all '+allowed+'))'
    if mode=='validate':return value+f'(deny file-read* (subpath "{ROOT/"artifacts"}"))'
    leaves=[*(ROOT/row['relative_path'] for row in DATA_PLAN.values()),CONTROL.parent]
    policy=ap.previous._artifact_policy(leaves)
    needle=f'(require-all (subpath "{ROOT/"artifacts"}")';require(policy.count(needle)==1,'source_binding')
    return value+policy.replace(needle,needle+f' (require-not (subpath "{CONTROL}"))',1)


def _security(fd):
    try:return previous.ap.security.snapshot(fd)
    except previous.ap.security.Refusal:raise Refused('output_security') from None


def _write(fd,raw):
    view=memoryview(raw)
    while view:
        count=os.write(fd,view);require(count>0,'output_write');view=view[count:]
    os.fsync(fd)


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
        for offset in range(0,len(raw),65536):remaining(deadline);_write(fd,raw[offset:offset+65536])
        fresh=metadata(os.fstat(fd));require(fresh[:6]==old[:6] and fresh[9]==old[9] and fresh[6]==len(raw),'output_changed')
        self.files[name]['metadata']=fresh;os.fsync(self.fd);self.verify();digest=hashlib.sha256()
        for offset in range(0,len(raw),65536):
            remaining(deadline);chunk=os.pread(fd,min(65536,len(raw)-offset),offset)
            require(chunk,'output_write');digest.update(chunk)
        require(digest.hexdigest()==sha(raw),'output_write');self.verify();return pin(raw)


def _assert_bytes(values):
    require(type(values) is dict and set(values)==set(DATA_PLAN)
      and all(type(values[role]) is bytes and pin(values[role])=={key:row[key] for key in ('byte_count','sha256')}
        for role,row in DATA_PLAN.items()),'source_bytes')


def construct(deadline):
    environment.require_safe_environment()
    with guard_module.FixedDataGuard(DATA_PLAN,deadline=deadline) as data_guard:
        values=data_guard.read_all_once()
        _assert_bytes(values)
        # The pure helper has no I/O authority and sees only all-four-pinned bytes.
        summary,private=query.prepare(values['identity'],values['crosswalk'],values['seed'],values['capture'],deadline=deadline)
        query.validate_summary(summary)
        require(type(private) is query.PrivateFmpQueryPlan and type(private._raw) is bytes
          and 0<len(private._raw)<=MAX_PRIVATE and private.byte_count==len(private._raw)
          and private.sha256==sha(private._raw) and private.summary_sha256==sha(canonical(summary))
          and summary['private_payload_pin']==pin(private._raw),'private_binding')
        query.validate_private_record(private.private_record(),expected_summary=summary)
        data_guard.verify();receipt=guard_module.validate_receipt(data_guard.receipt(),DATA_PLAN)
        environment.require_safe_environment();remaining(deadline)
        private_raw=private._raw
    return {'query_summary':summary,'source_receipt':receipt,'source_guard_normal_return':True},private_raw


def failure(args,error,*,claim_state='unknown'):
    return {'binding':binding(args),'failure_code':finite(error),'claim_state':claim_state,
      'allocation_unknown':claim_state=='unknown',**FALSE_FLAGS}


def run(args,deadline):
    source_context();info=os.statvfs(ROOT)
    require(info.f_bavail*info.f_frsize>=MIN_FREE_DISK,'disk_budget')
    with Store() as store:
        store.write('claim.json',canonical(binding(args)),deadline)
        try:
            prepared,private_raw=construct(deadline)
            private_pin=store.write(PRIVATE_NAME,private_raw,deadline);private_raw=None
            require(private_pin==prepared['query_summary']['private_payload_pin'],'private_binding')
            preflight(args,deadline);ar._credential_free();environment.require_safe_environment();store.verify()
            result={'schema':SCHEMA,**prepared,'private_pin':private_pin,
              'source_context_sha256':sha(canonical(source_context())),'I_fact_sha256':I_FACT_SHA256,
              'post_checks_complete':True,**FALSE_FLAGS}
            validate_result(result)
            report=store.write('report.json',canonical({**binding(args),'result':result}),deadline);store.verify()
            return {'result':result,'report':report}
        except BaseException as error:
            value=failure(args,error,claim_state='consumed')
            try:store.write('failure.json',canonical(value),deadline)
            except BaseException:pass
            return {'failure':value}


def validate_result(value):
    require(type(value) is dict and set(value)=={'schema','query_summary','source_receipt','source_guard_normal_return',
      'private_pin','source_context_sha256','I_fact_sha256','post_checks_complete',*FALSE_FLAGS}
      and value['schema']==SCHEMA and value['source_guard_normal_return'] is value['post_checks_complete'] is True
      and value['I_fact_sha256']==I_FACT_SHA256 and value['source_context_sha256']==sha(canonical(source_context()))
      and all(value[key] is False for key in FALSE_FLAGS),'output')
    query.validate_summary(value['query_summary'])
    require(value['private_pin']==value['query_summary']['private_payload_pin'],'output')
    guard_module.validate_receipt(value['source_receipt'],DATA_PLAN)


def _failure(value,actual_exit,args):
    require(type(actual_exit) is int and actual_exit==2 and type(value) is dict
      and set(value)=={'binding','failure_code','claim_state','allocation_unknown',*FALSE_FLAGS}
      and value['binding']==binding(args) and value['failure_code'] in FINITE
      and value['claim_state'] in ('consumed','unknown')
      and value['allocation_unknown'] is (value['claim_state']=='unknown')
      and all(value[key] is False for key in FALSE_FLAGS),'output')


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n') and raw.count(b'\n')==1
      and type(actual_exit) is int and actual_exit in (0,2),'output')
    value=parse(raw[:-1]);require(value.get('binding')==binding(args),'output')
    if set(value)=={'binding','failure_code','claim_state','allocation_unknown',*FALSE_FLAGS}:
        _failure(value,actual_exit,args);return value
    require(set(value)=={'binding','outcome'} and type(value['outcome']) is dict,'output')
    outcome=value['outcome']
    if set(outcome)=={'failure'}:_failure(outcome['failure'],actual_exit,args)
    else:
        require(actual_exit==0 and set(outcome)=={'result','report'},'output')
        validate_result(outcome['result'])
        require(outcome['report']==pin(canonical({**binding(args),'result':outcome['result']})),'output')
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('produce','validate'))
    for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--actual-exit',type=int);args=parser.parse_args(argv)
    deadline=time.monotonic()+(SECONDS if args.operation=='produce' else VALIDATOR_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline);environment._bootstrap_cli_logging();ar._credential_free()
            if args.operation=='validate':
                raw=sys.stdin.buffer.read(MAX_OUTPUT+1);validate_output(raw,args.actual_exit,args)
                sys.stdout.buffer.write(raw);return 0
            outcome=run(args,deadline);raw=canonical({'binding':binding(args),'outcome':outcome})+b'\n'
            code=2 if 'failure' in outcome else 0;validate_output(raw,code,args);sys.stdout.buffer.write(raw);return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure(args,error))+b'\n');return 2


if __name__=='__main__':raise SystemExit(main())
