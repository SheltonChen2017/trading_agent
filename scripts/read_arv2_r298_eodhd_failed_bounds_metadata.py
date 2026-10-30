"""One metadata-only reconciliation of an unaccepted AY observation.

The exact retained result-metadata bytes authenticate before JSON. Shape and
receipt checks validate only what the killed AY process reported, never its
actual success, old source admission, or the reported candidate whole pin.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import read_arv2_r298_eodhd_catalog_bounds as ay
from scripts import arv2_r298_fixed_data_guard as guard_module
from scripts import arv2_r298_bounded_actual_capture as actual_capture

SOURCE=ROOT/'scripts/read_arv2_r298_eodhd_failed_bounds_metadata.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-AZ'
SCHEMA='arv2-r298-unaccepted-AY-metadata-reconciliation-az-v1'
admitted,environment,PYTHON=ay.admitted,ay.environment,ay.PYTHON
canonical,sha,pin,metadata=ay.canonical,ay.sha,ay.pin,ay.metadata
SECONDS,MAX_OUTPUT=30,65536
AY_SOURCE_SHA256='58634dde609beee9b5272cb5bb570fefa272387533909646e3642963cfb9776f'
CAPTURE_SOURCE_SHA256='febe87c53010227eeca399b8a5087c42d2363c7d3a9ee583d18dfd06b3a68356'
AY_BINDING={'schema':ay.SCHEMA,'expected_head':'741e966cd426946877cac175dac9c569c72952af',
    'caller_sha256':AY_SOURCE_SHA256,'profile_sha256':'45d8b08b1fb5f3f26e4154898ee9aaf53be10516996cd16c7ef103b62bcec256'}
DATA_PLAN={'ay_reported_metadata':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-AY/result-metadata.json',
    'byte_count':4526,'sha256':'d9dfeaab7818d8e9aac495f525e27a3fb40a640f23bbb7f79aef3b6014bccdf8'}}
FALSE_FLAGS={'identity_accepted':False,'price_input_admitted':False,'QC_transfer_granted':False,
    'provider_contact':False,'credential_access':False,'AW_raw_source_read':False,'other_old_operational_control_read':False,
    'AY_actual_success_accepted':False,'AY_original_guard_return_authenticated':False,'reported_whole_pin_admitted':False,
    'pagination_contract_changed':False,'licensed_values_disclosed':False,'point_in_time_proven':False,
    'formal_forward_ready':False,'paper_or_live_ready':False}
FINITE=frozenset(('host','arguments','environment','git_state','source_pin','source_binding','deadline','claim_spent',
    'output_changed','output_security','output_write','output_bound','shape','output','os_error','unknown'))|frozenset(
        'guard_'+code for code in guard_module.FINITE)


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
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline) and 0<deadline-time.monotonic()<=SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def observed_failure():
    return {'schema':SCHEMA+'-AY-external-failure','AY_binding':dict(AY_BINDING),
        'AY_actual_exit':-9,'AY_bound':'outer_capture','AY_stdout_pin':{
            key:DATA_PLAN['ay_reported_metadata'][key] for key in ('byte_count','sha256')},
        'AY_stderr_bytes':0,'AY_native_validator_invoked':False,'AY_outer_actual_exit':2,
        'AY_attempt_spent':True,'AY_actual_success_accepted':False,
        'metadata_file_existence_not_preinspected':True,
        'reported_candidate_whole_pin_requires_separate_fresh_source_authentication':True,
        'new_operation_or_read_granted':False}


def pins():
    values=ay.pins();require('scripts/read_arv2_r298_eodhd_catalog_bounds.py' not in values,'source_pin')
    values['scripts/read_arv2_r298_eodhd_catalog_bounds.py']=AY_SOURCE_SHA256
    require('scripts/arv2_r298_bounded_actual_capture.py' not in values,'source_pin')
    values['scripts/arv2_r298_bounded_actual_capture.py']=CAPTURE_SOURCE_SHA256;return values


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),
        'control':str(CONTROL),'python':str(PYTHON),'source_pins':pins(),'seconds':SECONDS,
        'maximum_output_bytes':MAX_OUTPUT,'data_plan':DATA_PLAN,'source_read_schedule':guard_module.profile_record(DATA_PLAN),
        'AY_external_failure':observed_failure(),'purpose':'authenticate_only_retained_unaccepted_AY_metadata_claims',
        'byte_pin_before_JSON':True,'normal_metadata_guard_return_before_emit':True,
        'AY_shape_and_receipt_checks_are_FORMAT_ONLY_not_actual_exit_acceptance':True,
        'no_AY_validate_output_with_fabricated_zero':True,'reported_candidate_whole_pin_status':'reported_UNADMITTED',
        'new_AZ_guard_authenticates_only_metadata_leaf_not_original_AW_frames':True,
        'external_actual_measurement':{'source_sha256':CAPTURE_SOURCE_SHA256,
            'technical_profile':actual_capture.profile_record(),'producer_stdin_bytes':0,
            'producer_stdout_limit':65536,'producer_stderr_limit':8192,
            'all_limits_resolved_as_exact_integers_before_spawn':True,'progress_callback':False,
            'original_metadata_complete_flags_and_actual_exit_checked_before_acceptance':True},
        'strict_duplicate_key_refusal':True,'claim_before_metadata_read':True,
        'deadline_uninterruptible_IO_host_suspension_qualification':True,**FALSE_FLAGS}


def binding(args):return {'schema':SCHEMA,'expected_head':args.expected_head,
    'caller_sha256':args.caller_sha256,'profile_sha256':args.profile_sha256}


def preflight(args,deadline):
    require(not admitted.v5._under_test() and sys.platform=='darwin' and os.name=='posix'
        and sys.version_info[:2]==(3,13) and Path(sys.executable)==PYTHON and Path.cwd()==ROOT
        and ROOT.resolve()==ROOT and Path(__file__).absolute()==SOURCE,'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256),'arguments')
    ay.aw.ar._credential_free();environment._require_environment()
    for command,expected in ((['rev-parse','--show-toplevel'],str(ROOT)),(['branch','--show-current'],admitted.frozen.BRANCH),
        (['rev-parse','HEAD'],args.expected_head),(['status','--porcelain'],'')):
        require(admitted.v5._git(command,deadline).decode('ascii').strip()==expected,'git_state')
    for name,expected in pins().items():require(sha((ROOT/name).read_bytes())==expected,'source_pin')
    require(sha(SOURCE.read_bytes())==args.caller_sha256 and sha(admitted.v5._git(
        ['cat-file','blob',args.expected_head+':'+SOURCE.relative_to(ROOT).as_posix()],deadline,256*1024))==args.caller_sha256
        and sha(canonical(profile_record()))==args.profile_sha256,'source_pin');remaining(deadline)


def native_profile():
    value='(version 1)(allow default)(deny network*)'
    value+=''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))'
    value+=(f'(deny file-write* (require-all (require-not (subpath "{ROOT/".pytest_cache"}"))'
        f'(require-not (literal "/dev/null"))(require-not (subpath "{CONTROL}"))(require-not (literal "{CONTROL.parent}"))))')
    policy=ay.aw.ap.previous._artifact_policy([ROOT/DATA_PLAN['ay_reported_metadata']['relative_path'],CONTROL.parent])
    needle=f'(require-all (subpath "{ROOT/"artifacts"}")';require(policy.count(needle)==1,'source_binding')
    return value+policy.replace(needle,needle+f' (require-not (subpath "{CONTROL}"))',1)


def _security(fd):
    try:return ay.aw.ap.security.snapshot(fd)
    except ay.aw.ap.security.Refusal:raise Refused('output_security') from None


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
            require(chain==tuple(self.chain) and metadata(info)==metadata(os.fstat(self.fd))
                and _security(self.fd)==self.security and stat.S_IMODE(info.st_mode)==0o700
                and info.st_uid==os.getuid() and set(os.listdir(other))==set(self.files),'output_changed')
            for name,row in self.files.items():
                named=os.stat(name,dir_fd=other,follow_symlinks=False)
                require(metadata(named)==row['metadata']==metadata(os.fstat(row['fd'])) and stat.S_ISREG(named.st_mode)
                    and named.st_uid==os.getuid() and named.st_nlink==1 and stat.S_IMODE(named.st_mode)==0o600
                    and _security(row['fd'])==row['security'],'output_changed')
        finally:os.close(other)
    def write(self,name,raw):
        self.verify();require(name in ('claim.json','result-metadata.json') and name not in self.files
            and len(self.files)<2 and type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT,'output_bound')
        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        self.files[name]={'fd':fd,'metadata':metadata(os.fstat(fd)),'security':_security(fd)}
        _write(fd,raw);os.fsync(self.fd);self.files[name]['metadata']=metadata(os.fstat(fd));self.verify()
        require(os.pread(fd,len(raw)+1,0)==raw,'output_write');self.verify();return pin(raw)


def _write(fd,raw):
    view=memoryview(raw)
    while view:
        count=os.write(fd,view);require(count>0,'output_write');view=view[count:]
    os.fsync(fd)


def claimed_metadata(raw):
    expected=DATA_PLAN['ay_reported_metadata']
    require(type(raw) is bytes and pin(raw)=={key:expected[key] for key in ('byte_count','sha256')}
        and raw.endswith(b'\n') and raw.count(b'\n')==1,'shape')
    try:value=ay.aw.parse(raw[:-1])
    except BaseException:raise Refused('shape') from None
    require(type(value) is dict and set(value)=={'binding','result'} and value['binding']==AY_BINDING,'shape')
    reported=value['result']
    require(type(reported) is dict and set(reported)=={'schema','shape','source_guard_receipt','source_guard_normal_return',
        'AW_failure_binding_sha256',*ay.FALSE_FLAGS} and reported['schema']==ay.SCHEMA+'-result'
        and reported['source_guard_normal_return'] is True
        and reported['AW_failure_binding_sha256']==sha(canonical(ay.observed_failure()))
        and all(reported[key] is False for key in ay.FALSE_FLAGS),'shape')
    # These functions check the reported FORMAT only. No AY actual zero is invented.
    try:ay.validate_shape(reported['shape']);ay.validate_receipt(reported['source_guard_receipt'])
    except BaseException:raise Refused('shape') from None
    candidate=reported['shape']['AY_observed_whole_file_pin']
    require(candidate==reported['source_guard_receipt']['AY_observed_whole_file_pin'],'shape')
    result={'schema':SCHEMA+'-reported-claims','reported_binding':dict(AY_BINDING),
        'reported_bounds_shape':reported['shape'],'reported_framed_source_receipt':reported['source_guard_receipt'],
        'source_guard_normal_return_REPORTED':True,'metadata_claim_format_validated':True,
        'candidate_whole_file_pin_REPORTED_UNADMITTED':candidate,'candidate_pin_status':'reported_UNADMITTED',
        'original_AY_actual_exit':-9,'original_AY_native_validator_invoked':False,**FALSE_FLAGS}
    validate_claims(result);return result


def validate_claims(value):
    require(type(value) is dict and set(value)=={'schema','reported_binding','reported_bounds_shape',
        'reported_framed_source_receipt','source_guard_normal_return_REPORTED','metadata_claim_format_validated',
        'candidate_whole_file_pin_REPORTED_UNADMITTED','candidate_pin_status','original_AY_actual_exit',
        'original_AY_native_validator_invoked',*FALSE_FLAGS}
        and value['schema']==SCHEMA+'-reported-claims' and value['reported_binding']==AY_BINDING
        and value['source_guard_normal_return_REPORTED'] is True and value['metadata_claim_format_validated'] is True
        and value['candidate_pin_status']=='reported_UNADMITTED' and type(value['original_AY_actual_exit']) is int
        and value['original_AY_actual_exit']==-9 and value['original_AY_native_validator_invoked'] is False
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    try:ay.validate_shape(value['reported_bounds_shape']);ay.validate_receipt(value['reported_framed_source_receipt'])
    except BaseException:raise Refused('output') from None
    require(value['candidate_whole_file_pin_REPORTED_UNADMITTED']==value['reported_bounds_shape']['AY_observed_whole_file_pin']
        ==value['reported_framed_source_receipt']['AY_observed_whole_file_pin'],'output')
    return value


def source_metadata_pin():
    return {key:DATA_PLAN['ay_reported_metadata'][key] for key in ('byte_count','sha256')}


def run(args,deadline):
    with Store() as store:
        store.write('claim.json',canonical(binding(args)));preflight(args,deadline);environment.require_safe_environment()
        with guard_module.FixedDataGuard(DATA_PLAN,deadline=deadline) as guard:
            raw=guard.read_all_once()['ay_reported_metadata'];claims=claimed_metadata(raw)
            guard.verify();receipt=guard_module.validate_receipt(guard.receipt(),DATA_PLAN)
        remaining(deadline);preflight(args,deadline);environment.require_safe_environment();store.verify()
        result={'schema':SCHEMA+'-result','reported_UNADMITTED_claims':claims,
            'metadata_leaf_guard_receipt':receipt,'metadata_leaf_guard_normal_return':True,
            'AY_external_failure_sha256':sha(canonical(observed_failure())),'source_metadata_pin':source_metadata_pin(),**FALSE_FLAGS}
        raw=canonical({'binding':binding(args),'result':result})+b'\n'
        require(len(raw)<=MAX_OUTPUT,'output_bound');store.write('result-metadata.json',raw);store.verify()
    remaining(deadline);return raw


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n')
        and raw.count(b'\n')==1 and type(actual_exit) is int and actual_exit in (0,2),'output')
    value=ay.aw.parse(raw[:-1]);require(value.get('binding')==binding(args),'output')
    if set(value)=={'binding','failure_code','allocation_unknown',*FALSE_FLAGS}:
        require(actual_exit==2 and value['failure_code'] in FINITE and value['allocation_unknown'] is True
            and all(value[key] is False for key in FALSE_FLAGS),'output');return value
    require(actual_exit==0 and set(value)=={'binding','result'},'output');result=value['result']
    require(type(result) is dict and set(result)=={'schema','reported_UNADMITTED_claims','metadata_leaf_guard_receipt',
        'metadata_leaf_guard_normal_return','AY_external_failure_sha256','source_metadata_pin',*FALSE_FLAGS}
        and result['schema']==SCHEMA+'-result' and result['metadata_leaf_guard_normal_return'] is True
        and result['AY_external_failure_sha256']==sha(canonical(observed_failure()))
        and result['source_metadata_pin']==source_metadata_pin()
        and all(result[key] is False for key in FALSE_FLAGS),'output')
    validate_claims(result['reported_UNADMITTED_claims']);guard_module.validate_receipt(result['metadata_leaf_guard_receipt'],DATA_PLAN)
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);deadline=time.monotonic()+SECONDS
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline);environment._bootstrap_cli_logging();raw=run(args,deadline);validate_output(raw,0,args)
            sys.stdout.buffer.write(raw);return 0
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding':binding(args),'failure_code':finite(error),'allocation_unknown':True,**FALSE_FLAGS})+b'\n');return 2


if __name__=='__main__':raise SystemExit(main())
