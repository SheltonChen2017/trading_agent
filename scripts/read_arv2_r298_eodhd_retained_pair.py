"""One new retained AU pair authentication under verified Unicode display policy.

Only two exact DATA bodies are read. Current SPY vendor identity and six RAW
historical closes are qualified supplied-data observations, not strategy price,
permanent identity, PIT, QC processing or trading admission. No operation replay.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import run_arv2_r298_eodhd_history_diagnostic as au
from scripts import arv2_r298_fixed_data_guard as guard_module
from scripts import arv2_r298_eodhd_catalog_schema as catalog

SOURCE=ROOT/'scripts/read_arv2_r298_eodhd_retained_pair.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_eodhd_history_diagnostic/R326-20261027-AX'
SCHEMA='arv2-r298-offline-EODHD-retained-pair-ax-v1'
admitted,environment,PYTHON=au.admitted,au.environment,au.PYTHON
canonical,sha,pin,metadata=au.canonical,au.sha,au.pin,au.metadata
SECONDS,MAX_OUTPUT=30,65536
AU_SOURCE_SHA256='8f837fee5421cac1981894ffc40c0a2ea3b1f93c298304607f184eb98bc80f29'
DATA_PLAN={'au_metadata':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_history_diagnostic/R326-20261027-AU/metadata-private.json',
    'byte_count':170,'sha256':'27fe1cfd219c064793151e03c98ce70eb43889b568056d5810f8db3dc2b1355a'},
    'au_history':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_history_diagnostic/R326-20261027-AU/history-private.json',
        'byte_count':729,'sha256':'c55a32ca410d5b34ba7601715013b3b93b302d43d2eb7a87fde383d80d40c02d'}}
FALSE_FLAGS={**catalog.FALSE_FLAGS,'provider_contact':False,'credential_access':False,
    'old_control_read':False,'old_operation_replayed':False,'licensed_values_disclosed':False,
    'strategy_price_input_admitted':False,'formal_identity_admitted':False}
FINITE=frozenset(('host','arguments','environment','git_state','source_pin','source_binding','deadline','claim_spent',
    'output_changed','output_security','output_write','output_bound','authentication','output','os_error','unknown'))|frozenset(
        'guard_'+code for code in guard_module.FINITE)


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args=BaseException.args.__get__(error)
        return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is guard_module.Refused:return 'guard_'+guard_module.finite(error)
    if type(error) is catalog.Refused:return 'authentication'
    if type(error) is environment.EnvironmentRefused:return 'environment'
    if type(error) is admitted.helpers.Deadline:return 'deadline'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline) and 0<deadline-time.monotonic()<=SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def source_context():
    """Retained external facts; AU failure is never relabelled a success."""
    return {'schema':SCHEMA+'-source-context',
        'AU':{'head':'4302c6519d8118de265af1535f029c001202c4d6','source_sha256':AU_SOURCE_SHA256,
            'parent_actual_exit':2,'native_validator_actual_exit':0,'attempt_spent':True,
            'stdout_pin':{'byte_count':5769,'sha256':'5f3862c2e836e5ee858040bc2306b426af5352beb124b0c9bc7f6aa18a63a343'}},
        'AV':{'head':'3fc471d50cf45f937e49d2189d55a7c55bc98f8a',
            'source_sha256':'6e75b8dba85ab45d88f0382da0e4aa978d344c8ebdc02e03e8a158afc05672d6',
            'parent_actual_exit':0,'native_validator_actual_exit':0,'attempt_spent':True,
            'stdout_pin':{'byte_count':4953,'sha256':'78b1493a53951d363ded5d812489a5d3ee825c6acc7911a6b6645b13490b13c7'},
            'exact_original_seven_keys_observed':True,'only_Name_failed_ASCII_display_predicate':True,
            'Unicode_category_C_freedom_not_proven_by_AV':True},
        'new_operation_or_read_granted':False,'prior_AU_failure_evidence_preserved':True}


def pins():
    values=au.pins()
    extra={'scripts/run_arv2_r298_eodhd_history_diagnostic.py':AU_SOURCE_SHA256,
        'scripts/read_arv2_r298_eodhd_metadata_shape.py':'6e75b8dba85ab45d88f0382da0e4aa978d344c8ebdc02e03e8a158afc05672d6',
        'scripts/arv2_r298_eodhd_catalog_schema.py':'8ece5d178d2c8a1054aebd498f0968387d34dd3dca7979ddc59276f255a660f0'}
    for name,value in extra.items():
        require(name not in values or values[name]==value,'source_pin');values[name]=value
    return values


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),
        'control':str(CONTROL),'python':str(PYTHON),'source_pins':pins(),'seconds':SECONDS,
        'maximum_output_bytes':MAX_OUTPUT,'data_plan':DATA_PLAN,'source_read_schedule':guard_module.profile_record(DATA_PLAN),
        'source_context':source_context(),'purpose':'authenticate_exact_retained_AU_pair_after_verified_Unicode_display_parser_correction',
        'both_whole_byte_pins_before_any_JSON':True,'normal_source_return_before_emit':True,
        'claim_before_DATA_read':True,'pure_catalog_profile_sha256':sha(canonical(catalog.profile_record())),
        'no_provider_or_AU_AV_reader_or_worker_replay':True,
        'current_SPY_match_and_six_positive_RAW_dates_required':True,
        'Unicode_category_C_refusal_still_binding':True,
        'deadline_uninterruptible_IO_host_suspension_qualification':True,**FALSE_FLAGS}


def binding(args):return {'schema':SCHEMA,'expected_head':args.expected_head,
    'caller_sha256':args.caller_sha256,'profile_sha256':args.profile_sha256}


def preflight(args,deadline):
    require(not admitted.v5._under_test() and sys.platform=='darwin' and os.name=='posix'
        and sys.version_info[:2]==(3,13) and Path(sys.executable)==PYTHON and Path.cwd()==ROOT
        and ROOT.resolve()==ROOT and Path(__file__).absolute()==SOURCE,'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256),'arguments')
    au.ar._credential_free();environment._require_environment()
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
    policy=au.ap.previous._artifact_policy([*(ROOT/row['relative_path'] for row in DATA_PLAN.values()),CONTROL.parent])
    needle=f'(require-all (subpath "{ROOT/"artifacts"}")';require(policy.count(needle)==1,'source_binding')
    return value+policy.replace(needle,needle+f' (require-not (subpath "{CONTROL}"))',1)


def _security(fd):
    try:return au.ap.security.snapshot(fd)
    except au.ap.security.Refusal:raise Refused('output_security') from None


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
        au._write(fd,raw);os.fsync(self.fd);self.files[name]['metadata']=metadata(os.fstat(fd));self.verify()
        require(os.pread(fd,len(raw)+1,0)==raw,'output_write');self.verify();return pin(raw)


def failure(args,error):
    return {'binding':binding(args),'failure_code':finite(error),'allocation_unknown':True,**FALSE_FLAGS}


def run(args,deadline):
    with Store() as store:
        store.write('claim.json',canonical(binding(args)))
        try:
            with guard_module.FixedDataGuard(DATA_PLAN,deadline=deadline) as guard:
                raw=guard.read_all_once()
                require(set(raw)==set(DATA_PLAN) and all(pin(raw[role])=={
                    key:DATA_PLAN[role][key] for key in ('byte_count','sha256')} for role in DATA_PLAN),'source_binding')
                observation=catalog.authenticate_retained_spy(raw['au_metadata'],raw['au_history'])
                catalog.validate_spy_summary(observation)
                require(observation['metadata_schema_valid'] is observation['identity_matched']
                    is observation['history_schema_valid'] is observation['expected_date_coverage'] is True
                    and observation['positive_RAW_close_count']==6,'authentication')
                guard.verify();receipt=guard_module.validate_receipt(guard.receipt(),DATA_PLAN)
            remaining(deadline);preflight(args,deadline);environment.require_safe_environment();store.verify()
            result={'schema':SCHEMA+'-result','observation':observation,'source_guard_receipt':receipt,
                'source_guard_normal_return':True,'source_context_sha256':sha(canonical(source_context())),
                'retained_pair_authenticated':True,**FALSE_FLAGS}
            value={'binding':binding(args),'result':result}
        except BaseException as error:value=failure(args,error)
        raw=canonical(value)+b'\n';require(len(raw)<=MAX_OUTPUT,'output_bound')
        store.write('result-metadata.json',raw);store.verify()
    remaining(deadline);return raw


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n')
        and raw.count(b'\n')==1 and type(actual_exit) is int and actual_exit in (0,2),'output')
    value=au.parse(raw[:-1]);require(value.get('binding')==binding(args),'output')
    if set(value)=={'binding','failure_code','allocation_unknown',*FALSE_FLAGS}:
        require(actual_exit==2 and value['failure_code'] in FINITE and value['allocation_unknown'] is True
            and all(value[key] is False for key in FALSE_FLAGS),'output');return value
    require(actual_exit==0 and set(value)=={'binding','result'},'output');result=value['result']
    require(type(result) is dict and set(result)=={'schema','observation','source_guard_receipt','source_guard_normal_return',
        'source_context_sha256','retained_pair_authenticated',*FALSE_FLAGS} and result['schema']==SCHEMA+'-result'
        and result['source_guard_normal_return'] is result['retained_pair_authenticated'] is True
        and result['source_context_sha256']==sha(canonical(source_context()))
        and all(result[key] is False for key in FALSE_FLAGS),'output')
    observation=result['observation'];catalog.validate_spy_summary(observation)
    require(observation['body_pins']==[{key:DATA_PLAN[role][key] for key in ('byte_count','sha256')}
        for role in ('au_metadata','au_history')]
        and observation['metadata_schema_valid'] is observation['identity_matched']
            is observation['history_schema_valid'] is observation['expected_date_coverage'] is True
        and type(observation['positive_RAW_close_count']) is int and observation['positive_RAW_close_count']==6,'output')
    guard_module.validate_receipt(result['source_guard_receipt'],DATA_PLAN);return value


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);deadline=time.monotonic()+SECONDS
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline);environment._bootstrap_cli_logging();raw=run(args,deadline)
            code=0 if 'result' in au.parse(raw[:-1]) else 2;validate_output(raw,code,args)
            sys.stdout.buffer.write(raw);return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure(args,error))+b'\n');return 2


if __name__=='__main__':raise SystemExit(main())
