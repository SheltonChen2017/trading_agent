"""One project-independent offline archive of the fixed AR73 DATA leaves.

This new claim authenticates genuine input and copies only frozen local vendor
DATA. It does not replay an AR operation, read a QC book, contact a provider,
or admit price coverage. Partial output and verification markers are retained.
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
from scripts import prepare_arv2_r327_eodhd_fmp_query_plan as previous
from scripts import arv2_r298_common_price_payload as payload
from scripts import arv2_r298_all_route_worker_v2 as worker
from scripts import arv2_r327_available_history_period as period

ar,ap=previous.ar,previous.ap
admitted,environment,PYTHON=previous.admitted,previous.environment,previous.PYTHON
canonical,sha,pin,parse=previous.canonical,previous.sha,previous.pin,previous.parse
SOURCE=ROOT/'scripts/prepare_arv2_r327_available_history_archive.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_available_history_archive/R327-20261028-K'
SCHEMA='arv2-r327-project-independent-AR-archive-k-v1'
ARCHIVE_NAME='vendor-payload-private.bin'
VERIFY_NAME='verification-start.json'
SECONDS,OUTER_SECONDS,VALIDATOR_SECONDS=1800,1830,1800
MAX_OUTPUT=131072
ARCHIVE_BYTES=148543046
PERIOD_SHA256='88113155d49f74e00a89ba743aaa314d718cfd0d29b017ac501058460fe5d11a'
NEW_PINS={
 'scripts/prepare_arv2_r327_eodhd_fmp_query_plan.py':'8ba4fa609a9d2b049f88e937a71473189888e6473c1b05b0ed3abd7a1d7059b7',
 'scripts/arv2_r298_common_price_payload.py':'aff0a446a44c8c76cf83fd084c69d8a82877a4f451bf55c2c53045b511bf51e9',
 'scripts/arv2_r298_all_route_worker_v2.py':'d236e3f0113046ca638296823d880ac8a93e8d31e65047b57c26fcba5dc35da1',
 'scripts/arv2_r327_available_history_period.py':'722cffeae9fbebcd9bca656c8994273d2b1fb36f6d3e269a018c8fb18e5b7b18'}
FALSE_FLAGS={'provider_contact':False,'credential_access':False,'QC_contact':False,'Safari_access':False,
 'old_operation_invoked':False,'old_control_read':False,'native_QC_book_read':False,
 'source_assignments_changed':False,'source_or_processing_rights_granted':False,
 'price_input_admitted':False,'complete_strategy_price_coverage_proven':False,
 'actual_target_or_holdings_path_proven':False,'strategy_result_accepted':False,
 'point_in_time_proven':False,'permanent_master_proven':False,'formal_forward_ready':False,
 'paper_or_live_ready':False,'licensed_rows_disclosed':False,'continuous_integrity_proven':False,
 'runtime_project_id_verified':False,'QC_transfer_granted':False}
FINITE=frozenset(('host','arguments','environment','git_state','source_pin','source_binding','deadline',
 'claim_spent','verification_spent','output_changed','output_security','output_write','output_bound',
 'genuine','genuine_changed','archive_binding','archive_verify','output','os_error','unknown')) \
 |frozenset('payload_'+code for code in payload.FINITE) \
 |frozenset('worker_'+code for code in worker.FINITE)


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args=BaseException.args.__get__(error)
        return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is payload.Refused:return 'payload_'+payload.finite(error)
    if type(error) is worker.Refused:return 'worker_'+worker.finite(error)
    if type(error) is worker.previous.Refused:return 'worker_'+worker.previous.finite(error)
    if type(error) is environment.EnvironmentRefused:return 'environment'
    if type(error) is admitted.helpers.Deadline:return 'deadline'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline)
        and 0<deadline-time.monotonic()<=SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None
def metadata(fd):return payload.metadata(fd)


def pins():
    result=previous.pins();require(len(result)==226,'source_pin')
    for name,value in NEW_PINS.items():
        require(_hash(value) and (name not in result or result[name]==value),'source_pin');result[name]=value
    return result


def source_context():
    plan=payload.data_plan()
    require(set(plan)==set(payload.ROLES) and len(plan)==73
        and sum(row['byte_count'] for row in plan.values())==148531396
        and len(payload._header_bytes())+148531396==ARCHIVE_BYTES,'source_binding')
    expected=payload.anchor.sidecar_output()['outcome']['result']['input_binding']
    worker.previous._validate_input(expected)
    require(expected['binding_contract']['binding_count']==6151
        and expected['ordered_session_values_sha256']==period.FULL_AXIS_SHA256,'source_binding')
    return {'AR_fact_sha256':payload.FACT_SHA256,'AR_output_sha256':payload.OUTPUT_SHA256,
        'data_plan_sha256':payload.PLAN_SHA256,'input_binding':expected,'archive_byte_count':ARCHIVE_BYTES,
        'period_sha256':PERIOD_SHA256}


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),
        'control':str(CONTROL),'python':str(PYTHON),'source_pins':pins(),
        'seconds':SECONDS,'outer_seconds':OUTER_SECONDS,'validator_seconds':VALIDATOR_SECONDS,
        'source_context':source_context(),'data_plan':payload.data_plan(),
        'payload_profile_sha256':sha(canonical(payload.profile_record())),'archive_name':ARCHIVE_NAME,
        'verification_marker':VERIFY_NAME,'maximum_public_output_bytes':MAX_OUTPUT,'maximum_owned_files':5,
        'archive_bytes':ARCHIVE_BYTES,'minimum_free_disk_bytes':payload.MIN_FREE_DISK,
        'fresh_genuine_full_6151_catalog_and_full_axis_before_copy':True,
        'all73_whole_hashes_before_payload_copy':True,'copy_original_held_FDs_and_full_metadata':True,
        'source_guard_normal_return_before_READY':True,'genuine_input_rechecked_after_archive_copy':True,
        'own_output_original_FDs_named_full_metadata_native_security_checked':True,
        'own_directory_refresh':'only_successful_EXCL_file_create_requires_Darwin_APFS_nlink_plus1;own_mkdir_allows0or1;no_external_or_source_nlink_relaxation',
        'one_exclusive_claim_consumed_before_any_genuine_or_AR_DATA_read':True,
        'one_exclusive_verification_marker_before_any_archive_read':True,
        'independent_native_validator_reads_only_new_archive_DATA_not_old_controls':True,
        'archive_verifier_exact_header_all73_ranges_whole_pin_and_native_metadata':True,
        'producer_actual0_and_separate_validator_actual0_required_by_collector':True,
        'actual2_failure_authentication_does_not_read_archive':True,
        'partial_output_retained_no_cleanup_retry_overwrite_or_alternate_path':True,
        'native_deny_all_network_Keychains_security_CLI':True,'project_independent_local_bytes_only':True,
        'deadlines_do_not_bound_uninterruptible_IO_or_host_suspension':True,**FALSE_FLAGS}


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
    else:allowed+=f'(require-not (literal "{CONTROL/VERIFY_NAME}"))(require-not (literal "{CONTROL}"))'
    value+='(deny file-write* (require-all '+allowed+'))'
    if mode=='produce':
        leaves=[*(ROOT/row['relative_path'] for row in payload.data_plan().values()),worker.previous.LINEAGE,CONTROL.parent]
        policy=ap.previous._artifact_policy(leaves,package=worker.previous.PACKAGE)
        needle=f'(require-all (subpath "{ROOT/"artifacts"}")';require(policy.count(needle)==1,'source_binding')
        return value+policy.replace(needle,needle+f' (require-not (subpath "{CONTROL}"))',1)
    return value+ap.previous._artifact_policy([CONTROL/ARCHIVE_NAME,CONTROL/VERIFY_NAME])


def _security(fd):
    try:return ap.security.snapshot(fd)
    except ap.security.Refusal:raise Refused('output_security') from None


def _named(parent,name):
    try:info=os.stat(name,dir_fd=parent,follow_symlinks=False)
    except OSError:raise Refused('output_changed') from None
    return tuple(getattr(info,key,None) for key in payload.FIELDS)


def _regular(info):
    return stat.S_ISREG(info[2]) and stat.S_IMODE(info[2])==0o600 \
        and info[3]==os.getuid() and info[5]==1 and not info[9] & ~(stat.UF_TRACKED|stat.UF_HIDDEN)


def _write(fd,raw,deadline):
    view=memoryview(raw)
    while view:
        remaining(deadline);count=os.write(fd,view[:65536]);require(type(count) is int and count>0,'output_write')
        view=view[count:]
    os.fsync(fd)


class DirectoryGuard:
    """Hold every original path FD; only known own creates refresh a directory."""
    def __init__(self,*,create):
        self.rows=[];self.fd=None;self.active=False
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.rows.append({'path':Path('/'),'parent':fd,'name':'.','fd':fd,'metadata':metadata(fd),'security':None})
        try:
            parent=self.rows[0]
            for index,part in enumerate(CONTROL.parts[1:],1):
                here=Path(*CONTROL.parts[:index+1]);self.verify()
                if create and here in (CONTROL.parent,CONTROL):
                    try:os.mkdir(part,0o700,dir_fd=parent['fd']);os.fsync(parent['fd']);self.refresh(parent,created_directory=True)
                    except FileExistsError:require(here!=CONTROL,'claim_spent')
                before=_named(parent['fd'],part)
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent['fd'])
                row={'path':here,'parent':parent['fd'],'name':part,'fd':nxt,'metadata':before,
                    'security':_security(nxt) if here==ROOT or ROOT in here.parents else None}
                self.rows.append(row);self._policy(row)
                require(metadata(nxt)==before==_named(parent['fd'],part),'output_changed');parent=row
            self.fd=parent['fd'];self.active=True;self.verify()
        except BaseException:self.close();raise
    def _policy(self,row):
        info=metadata(row['fd']);require(stat.S_ISDIR(info[2]),'output_changed')
        if row['path']==ROOT or ROOT in row['path'].parents:
            require(info[3]==os.getuid() and stat.S_IMODE(info[2])==(0o755 if row['path']==ROOT else 0o700)
                and not info[9] & ~(stat.UF_TRACKED|stat.UF_HIDDEN)
                and _security(row['fd'])==row['security'],'output_security')
    def refresh(self,row,*,created_directory=False,created_file=False):
        fresh=metadata(row['fd']);old=row['metadata']
        require(type(created_directory) is type(created_file) is bool
            and not (created_directory and created_file),'output_changed')
        links=(old[5]+1,) if created_file else ((old[5],old[5]+1) if created_directory else (old[5],))
        require(fresh[:5]==old[:5] and fresh[9]==old[9]
            and fresh[5] in links,'output_changed')
        self._policy(row);row['metadata']=fresh
    def verify(self):
        for row in self.rows:
            require(metadata(row['fd'])==row['metadata']==_named(row['parent'],row['name']),'output_changed')
            self._policy(row)
    def close(self):
        failed=False
        for row in reversed(self.rows):
            try:os.close(row['fd'])
            except OSError:failed=True
        self.rows=[];self.active=False
        require(not failed,'output_changed')
    def __enter__(self):return self
    def __exit__(self,kind,*_):
        try:
            if kind is None:self.verify()
        finally:self.close()


class Store:
    def __init__(self):
        self.guard=DirectoryGuard(create=True);self.fd=self.guard.fd;self.files={};self.failed=False
    def __enter__(self):return self
    def __exit__(self,kind,*_):
        failed=False
        try:
            if kind is None and not self.failed:self.verify()
        finally:
            for row in self.files.values():
                try:os.close(row['fd'])
                except OSError:failed=True
            self.guard.close()
        require(not failed,'output_changed')
    def verify(self):
        self.guard.verify()
        require(set(os.listdir(self.fd))==set(self.files),'output_changed')
        for name,row in self.files.items():
            info=metadata(row['fd'])
            require(info==row['metadata']==_named(self.fd,name) and _regular(info)
                and _security(row['fd'])==row['security'],'output_changed')
    def create(self,name):
        self.verify();require(name in ('claim.json',ARCHIVE_NAME,'report.json','failure.json') and name not in self.files
            and len(self.files)<4,'output_bound')
        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        try:
            initial=metadata(fd);security=_security(fd)
            require(_regular(initial) and initial[6]==0 and initial==_named(self.fd,name),'output_changed')
            # The returned EXCL child is bound before acknowledging its one
            # verified APFS parent-directory link increment. No source changes.
            self.guard.refresh(self.guard.rows[-1],created_file=True);os.fsync(self.fd)
            self.files[name]={'fd':fd,'metadata':initial,'security':security};self.verify()
        except BaseException:
            if name not in self.files:os.close(fd)
            raise
        return fd
    def finish(self,name,old):
        row=self.files[name];fresh=metadata(row['fd'])
        require(fresh[:6]==old[:6] and fresh[9]==old[9] and _regular(fresh)
            and _security(row['fd'])==row['security'],'output_changed')
        row['metadata']=fresh;self.verify();return fresh
    def write(self,name,raw,deadline):
        require(name!=ARCHIVE_NAME and type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT,'output_bound')
        fd=self.create(name);old=self.files[name]['metadata'];_write(fd,raw,deadline);self.finish(name,old)
        require(os.pread(fd,len(raw)+1,0)==raw,'output_write');return pin(raw)


def _genuine(deadline):
    environment.require_safe_environment();plain=worker._load_plain(deadline)
    initial,record,selected,rows,public=worker._catalog(plain,deadline)
    expected=source_context()['input_binding']
    axis=worker.previous.identity.evaluator._parse_sessions(tuple(selected['session_axis']))
    view=period.make_period(axis)
    require(public==expected and len(rows)==6151 and view['period_sha256']==PERIOD_SHA256,'genuine')
    return plain,initial,record,selected,public


def failure(args,error,*,claim_state='unknown'):
    return {'binding':binding(args),'failure_code':finite(error),'claim_state':claim_state,
        'allocation_unknown':claim_state=='unknown',**FALSE_FLAGS}


def run(args,deadline):
    with Store() as store:
        store.write('claim.json',canonical(binding(args)),deadline)
        try:
            plain,initial,record,selected,public=_genuine(deadline)
            fd=store.create(ARCHIVE_NAME);old=store.files[ARCHIVE_NAME]['metadata']
            ready=payload.prepare_archive_fd(fd,expected_initial_metadata=old,deadline=deadline)
            payload.validate_receipt(ready,ready=True);fresh=store.finish(ARCHIVE_NAME,old)
            require(ready['archive_pin']['byte_count']==ARCHIVE_BYTES and ready['archive_metadata_sha256']
                ==sha(canonical(list(fresh))),'archive_binding')
            worker._catalog_unchanged(plain,initial,record,selected,deadline)
            preflight(args,deadline);ar._credential_free();environment.require_safe_environment();store.verify()
            result={'schema':SCHEMA,'input_binding':public,'period_sha256':PERIOD_SHA256,
                'ready_receipt':ready,'archive_pin':ready['archive_pin'],
                'archive_security_sha256':sha(canonical(store.files[ARCHIVE_NAME]['security'])),
                'genuine_input_checks_complete':True,'genuine_input_postchecks_complete':True,
                'own_output_postchecks_complete':True,'source_context_sha256':sha(canonical(source_context())),**FALSE_FLAGS}
            validate_result(result)
            report=store.write('report.json',canonical({**binding(args),'result':result}),deadline);store.verify()
            outcome={'result':result,'report':report}
        except BaseException as error:
            # Failure never publishes readiness. Preserve its finite predicate
            # even when the retained partial archive cannot pass normal checks.
            store.failed=True
            value=failure(args,error,claim_state='consumed')
            try:store.write('failure.json',canonical(value),deadline)
            except BaseException:pass
            outcome={'failure':value}
    return outcome


def validate_result(value):
    require(type(value) is dict and set(value)=={'schema','input_binding','period_sha256','ready_receipt','archive_pin',
        'archive_security_sha256','genuine_input_checks_complete','genuine_input_postchecks_complete',
        'own_output_postchecks_complete','source_context_sha256',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['input_binding']==source_context()['input_binding']
        and value['period_sha256']==PERIOD_SHA256 and value['genuine_input_checks_complete']
            is value['genuine_input_postchecks_complete'] is value['own_output_postchecks_complete'] is True
        and value['source_context_sha256']==sha(canonical(source_context()))
        and _hash(value['archive_security_sha256']) and all(value[key] is False for key in FALSE_FLAGS),'output')
    payload.validate_receipt(value['ready_receipt'],ready=True)
    require(value['archive_pin']==value['ready_receipt']['archive_pin']
        and value['archive_pin']['byte_count']==ARCHIVE_BYTES,'output')


def _failure(value,actual_exit,args):
    require(type(actual_exit) is int and actual_exit==2 and type(value) is dict
        and set(value)=={'binding','failure_code','claim_state','allocation_unknown',*FALSE_FLAGS}
        and value['binding']==binding(args) and type(value['failure_code']) is str and value['failure_code'] in FINITE
        and value['claim_state'] in ('consumed','unknown')
        and value['allocation_unknown'] is (value['claim_state']=='unknown')
        and all(value[key] is False for key in FALSE_FLAGS),'output')


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n') and raw.count(b'\n')==1
        and type(actual_exit) is int and actual_exit in (0,2),'output')
    value=parse(raw[:-1]);require(type(value) is dict and value.get('binding')==binding(args),'output')
    if set(value)=={'binding','failure_code','claim_state','allocation_unknown',*FALSE_FLAGS}:
        _failure(value,actual_exit,args);return value
    require(set(value)=={'binding','outcome'} and type(value['outcome']) is dict,'output')
    outcome=value['outcome']
    if set(outcome)=={'failure'}:_failure(outcome['failure'],actual_exit,args)
    else:
        require(actual_exit==0 and set(outcome)=={'result','report'},'output');validate_result(outcome['result'])
        require(outcome['report']==pin(canonical({**binding(args),'result':outcome['result']})),'output')
    return value


def verify_output_archive(raw,actual_exit,args,deadline):
    value=validate_output(raw,actual_exit,args)
    if actual_exit==2:return
    result=value['outcome']['result']
    with DirectoryGuard(create=False) as directory:
        # Marker creation consumes verification before any archive bytes.
        require(set(os.listdir(directory.fd))=={'claim.json',ARCHIVE_NAME,'report.json'},'verification_spent')
        try:marker=os.open(VERIFY_NAME,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory.fd)
        except FileExistsError:raise Refused('verification_spent') from None
        archive=None
        try:
            marker_initial=metadata(marker)
            require(_regular(marker_initial) and marker_initial[6]==0
                and marker_initial==_named(directory.fd,VERIFY_NAME),'output_changed')
            marker_initial_security=_security(marker)
            directory.refresh(directory.rows[-1],created_file=True);os.fsync(directory.fd)
            marker_raw=canonical({'binding':binding(args),'producer_public_pin':pin(raw),'producer_actual_exit':actual_exit})
            marker_old=metadata(marker);_write(marker,marker_raw,deadline);marker_fresh=metadata(marker)
            require(marker_fresh[:6]==marker_old[:6] and marker_fresh[9]==marker_old[9]
                and _regular(marker_fresh) and os.pread(marker,len(marker_raw)+1,0)==marker_raw
                and _security(marker)==marker_initial_security,'output_write')
            marker_security=marker_initial_security;directory.verify()
            before=_named(directory.fd,ARCHIVE_NAME)
            archive=os.open(ARCHIVE_NAME,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory.fd)
            require(metadata(archive)==before and _regular(before)
                and sha(canonical(list(before)))==result['ready_receipt']['archive_metadata_sha256']
                and sha(canonical(_security(archive)))==result['archive_security_sha256'],'archive_binding')
            receipt=payload.verify_archive_fd(archive,expected_metadata=before,deadline=deadline)
            payload.validate_receipt(receipt,ready=False)
            require(receipt['archive_pin']==result['archive_pin'] and receipt['header_pin']==result['ready_receipt']['header_pin']
                and receipt['data_plan_sha256']==result['ready_receipt']['data_plan_sha256'],'archive_verify')
            require(metadata(archive)==before==_named(directory.fd,ARCHIVE_NAME)
                and sha(canonical(_security(archive)))==result['archive_security_sha256'],'archive_binding')
            directory.verify()
            require(metadata(marker)==marker_fresh==_named(directory.fd,VERIFY_NAME)
                and _security(marker)==marker_security,'output_changed')
            preflight(args,deadline);ar._credential_free();environment.require_safe_environment()
        finally:
            if archive is not None:os.close(archive)
            os.close(marker)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('produce','validate'))
    for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--actual-exit',type=int);args=parser.parse_args(argv)
    deadline=time.monotonic()+(SECONDS if args.operation=='produce' else VALIDATOR_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline);environment._bootstrap_cli_logging();ar._credential_free()
            if args.operation=='validate':
                raw=sys.stdin.buffer.read(MAX_OUTPUT+1);verify_output_archive(raw,args.actual_exit,args,deadline)
                sys.stdout.buffer.write(raw);return 0
            outcome=run(args,deadline);raw=canonical({'binding':binding(args),'outcome':outcome})+b'\n'
            code=2 if 'failure' in outcome else 0;validate_output(raw,code,args);sys.stdout.buffer.write(raw);return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure(args,error))+b'\n');return 2


if __name__=='__main__':raise SystemExit(main())
