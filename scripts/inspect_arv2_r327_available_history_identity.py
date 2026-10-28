"""One offline available-history identity and demand diagnostic.

Four exact DATA leaves and fresh genuine input are authenticated. Original
assignments survive; hierarchy observations never replace identifiers, waive
collisions, admit prices or launch a backtest.
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
from scripts import run_arv2_r327_public_figi_hierarchy as previous
from scripts import arv2_r327_h_source_binding as h_anchor
from scripts import arv2_r327_available_history_period as period
from scripts import arv2_r327_available_history_identity as diagnosis
from scripts import arv2_r298_membership_price_demand as membership
from scripts import arv2_r298_fixed_data_guard as guard_module

worker,transport=membership.loader,membership.transport
ar,ap=previous.ar,previous.ap
admitted,environment,PYTHON=previous.admitted,previous.environment,previous.PYTHON
canonical,sha,pin,parse,metadata=previous.canonical,previous.sha,previous.pin,previous.parse,previous.metadata
SOURCE=ROOT/'scripts/inspect_arv2_r327_available_history_identity.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_available_history_identity/R327-20261027-I'
SCHEMA='arv2-r327-offline-available-history-identity-i-v1'
SECONDS,OUTER_SECONDS,VALIDATOR_SECONDS=300,330,30
MAX_OUTPUT,MAX_PRIVATE,MIN_FREE_DISK=131072,16*1024*1024,64*1024*1024
PRIVATE_NAME='identity-demand-private.json'
H_FACT_SHA256='e72ff5029df04609c1f7eb4d6fc2f2a552c4dfa0065764d2c4dc00f0601beab4'
DATA_PLAN={
 'hierarchy':{'relative_path':'artifacts/analyst_revisions_v2/newrule_public_figi_diagnostic/R327-20261027-H/hierarchy-private.json',
  'byte_count':38548,'sha256':'b85c3d37acbe4f72192d4d42d6470654a2e727f0c6a23bed06a3539e2ec3aacd'},
 'catalog':{'relative_path':'artifacts/analyst_revisions_v2/newrule_common_price_sidecar/R326-20261027-AR/catalog-private.json',
  'byte_count':2224206,'sha256':'f55e44f85f39846f0b4946860318760eab68d10d95c79d2cf87da44ad9568cb1'},
 'stocks_metadata':{'relative_path':'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z/stocks-metadata.csv',
  'byte_count':2340169,'sha256':'354f578dd11ab0cebe1ff5b6f9ddb596b2d776f4e3161b34b8d4e1723ffe60e6'},
 'funds_metadata':{'relative_path':'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z/funds-metadata.csv',
  'byte_count':904679,'sha256':'a85d60f8699ae4b606ee11b7a70fd48e683fd8de223f14f5b4e2599434bdefac'}}
NEW_PINS={
 'scripts/run_arv2_r327_public_figi_hierarchy.py':'66fac17278f2468bbbca869da1b1941c5d0ea9c1d55e603efdf5c3448abcd411',
 'scripts/observe_arv2_r327_public_figi_hierarchy.py':'6979d7d63ff4d8040979f5edfd2b5cc0af63cdbfc9e42838295eb5ed407c1eab',
 'scripts/arv2_r327_h_source_binding.py':'5280c31f84bce7aa088d57df5a861ab40a159a0e597e90600d339ba9a4590fce',
 'scripts/arv2_r327_available_history_period.py':'722cffeae9fbebcd9bca656c8994273d2b1fb36f6d3e269a018c8fb18e5b7b18',
 'scripts/arv2_r327_available_history_identity.py':'e8940f07f62015e185f159ef7469955f72945efb7da6ca800c4d491ea7b10ac1'}
FALSE_FLAGS={'provider_contact':False,'credential_access':False,'QC_contact':False,'old_operation_invoked':False,
 'old_control_read':False,'source_assignments_changed':False,'original_FIGI_replaced':False,
 'vendor_collision_cleared':False,'CUSIP_only_identity_admitted':False,'new_source_selected':False,
 'price_input_admitted':False,'complete_strategy_price_coverage_proven':False,'known_native_gap_resolved':False,
 'strategy_result_accepted':False,'point_in_time_proven':False,'permanent_master_proven':False,
 'formal_forward_ready':False,'paper_or_live_ready':False,'licensed_rows_disclosed':False,
 'continuous_integrity_proven':False}
FINITE=frozenset(('host','arguments','environment','git_state','source_pin','source_binding','deadline','disk_budget',
 'claim_spent','output_changed','output_security','output_write','output_bound','source_bytes','genuine',
 'genuine_changed','diagnosis','private_binding','output','os_error','unknown'))|frozenset('guard_'+code for code in guard_module.FINITE) \
 |frozenset('diagnosis_'+code for code in diagnosis.FINITE if code!='deadline')


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
    if type(error) is diagnosis.Refused:
        code=diagnosis.finite(error)
        if code=='deadline':return 'deadline'
        return 'diagnosis_'+code if code in diagnosis.FINITE else 'diagnosis'
    if type(error) in (membership.Refused,worker.Refused):return 'genuine'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline) and 0<deadline-time.monotonic()<=SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def pins():
    result=previous.pins();require(len(result)==217,'source_pin')
    for name,value in NEW_PINS.items():
        require(_hash(value) and value!='0'*64 and (name not in result or result[name]==value),'source_pin')
        result[name]=value
    return result


def source_context():
    fact=h_anchor.observed_fact()
    require(sha(canonical(fact))==H_FACT_SHA256 and fact['private_data']==DATA_PLAN['hierarchy']
        and fact['technical_observation_authenticated'] is True and fact['all_source_provider_auth_actual_exits_zero'] is True
        and type(fact['producer']['actual_exit']) is int and fact['producer']['actual_exit']==0
        and type(fact['validator']['actual_exit']) is int and fact['validator']['actual_exit']==0
        and fact['source_or_price_admission_granted'] is False and fact['vendor_global_collision_cleared'] is False
        and fact['original_FIGI_replaced'] is False and diagnosis.DATA_PLAN==DATA_PLAN,'source_binding')
    guard_module.checked_plan(DATA_PLAN)
    return diagnosis.source_context()


def profile_record():
    context=source_context()
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),'control':str(CONTROL),
      'python':str(PYTHON),'seconds':SECONDS,'outer_seconds':OUTER_SECONDS,'validator_seconds':VALIDATOR_SECONDS,
      'source_pins':pins(),'data_plan':DATA_PLAN,'data_total_bytes':5507602,'data_guard_profile':guard_module.profile_record(DATA_PLAN),
      'H_fact_sha256':H_FACT_SHA256,'source_context_sha256':sha(canonical(context)),
      'diagnosis_profile_sha256':sha(canonical(diagnosis.profile_record())),
      'period_profile_sha256':sha(canonical(period.profile_record())),
      'maximum_output_bytes':MAX_OUTPUT,'maximum_private_output_bytes':MAX_PRIVATE,'minimum_free_disk_bytes':MIN_FREE_DISK,
      'genuine_package_path':str(worker.previous.PACKAGE),'genuine_lineage_path':str(worker.previous.LINEAGE),
      'claim_before_DATA_or_genuine_source_read':True,'all_four_DATA_byte_pins_before_any_DATA_JSON':True,
      'fresh_all6151_bindings_full3466_calendar_and_membership_stream_semantics':True,
      'all_five_transport_role_byte_inventories_checked':True,
      'parsed_role_semantics':['evaluator_manifest','session_axis','memberships','runtime_symbol_bindings'],
      'genuine_fingerprint_record_and_all_four_parsed_streams_rechecked_before_return':True,
      'separate_checked_binding_catalog_rehashed_after_pure_analysis':True,
      'normal_DATA_guard_return_before_private_and_public_publication':True,
      'all_original_stock_and_eight_fund_assignments_retained_without_replacement':True,
      'rival_rows_table_qualified_no_truncation_or_favorable_subset':True,
      'public_counts_hashes_period_geometry_only_private_rows_owned_private_output':True,
      'native_producer_and_validator_deny_all_network_Keychains_security_CLI':True,
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
    previous.ar._credential_free();environment._require_environment();source_context()
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
    leaves=[*(ROOT/row['relative_path'] for row in DATA_PLAN.values()),worker.previous.LINEAGE,CONTROL.parent]
    policy=previous.ap.previous._artifact_policy(leaves,package=worker.previous.PACKAGE)
    needle=f'(require-all (subpath "{ROOT/"artifacts"}")';require(policy.count(needle)==1,'source_binding')
    return value+policy.replace(needle,needle+f' (require-not (subpath "{CONTROL}"))',1)


def _security(fd):
    try:return previous.ap.security.snapshot(fd)
    except previous.ap.security.Refusal:raise Refused('output_security') from None


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
        for offset in range(0,len(raw),65536):remaining(deadline);previous._write(fd,raw[offset:offset+65536])
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


def _genuine(public,axis,catalog):
    context=source_context()
    require(public==context['input_binding'] and type(catalog) is list and len(catalog)==6151
      and type(axis) is tuple and len(axis)==3466 and sha(canonical(list(axis)))==period.FULL_AXIS_SHA256,'genuine')
    period.make_period(axis)


def _plain_unchanged(plain,initial,record,selected,deadline):
    remaining(deadline);transport.require_plain_transport(plain)
    require(transport._fingerprint(plain)==initial and plain.to_record()==record,'genuine_changed')
    fresh=membership._streams(plain,record,deadline)
    require(set(fresh)==set(selected)==set(membership.SELECTED_ROLES)
      and canonical(fresh)==canonical(selected),'genuine_changed')
    remaining(deadline)


def construct(deadline):
    environment.require_safe_environment()
    with guard_module.FixedDataGuard(DATA_PLAN,deadline=deadline) as data_guard:
        values=data_guard.read_all_once()
        # All four full external pins precede DATA JSON and genuine package I/O.
        _assert_bytes(values)
        plain=worker._load_plain(deadline)
        initial,record,selected,catalog,public,axis,_=membership._authenticated(plain,deadline)
        _genuine(public,axis,catalog)
        catalog_sha256=sha(canonical(catalog))
        environment.require_safe_environment()
        summary,private=diagnosis.prepare(values['hierarchy'],values['catalog'],values['stocks_metadata'],values['funds_metadata'],
          full_axis=axis,binding_rows=tuple(catalog),membership_rows=tuple(selected['memberships']),
          evaluator_manifest=selected['evaluator_manifest'][0],input_binding=public,deadline=deadline)
        diagnosis.validate_summary(summary)
        require(type(private) is diagnosis.PrivateIdentityDemand and type(private._raw) is bytes
          and 0<len(private._raw)<=MAX_PRIVATE and private.byte_count==len(private._raw)
          and private.sha256==sha(private._raw) and private.summary_sha256==sha(canonical(summary))
          and summary['private_payload_pin']==pin(private._raw),'private_binding')
        diagnosis.validate_private_record(private.private_record(),expected_summary=summary)
        require(sha(canonical(catalog))==catalog_sha256 and public==source_context()['input_binding'],'genuine_changed')
        _plain_unchanged(plain,initial,record,selected,deadline)
        data_guard.verify();receipt=guard_module.validate_receipt(data_guard.receipt(),DATA_PLAN)
        environment.require_safe_environment();remaining(deadline)
        private_raw=private._raw
    # No publication occurs until the fixed DATA guard returns normally.
    return {'identity_summary':summary,'genuine_input_binding':public,'source_receipt':receipt,
      'all_four_DATA_guard_normal_return':True,'genuine_input_checks_complete':True},private_raw


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
            require(private_pin==prepared['identity_summary']['private_payload_pin'],'private_binding')
            preflight(args,deadline);previous.ar._credential_free();environment.require_safe_environment();store.verify()
            result={'schema':SCHEMA,**prepared,'private_pin':private_pin,
              'source_context_sha256':sha(canonical(source_context())),'H_fact_sha256':H_FACT_SHA256,
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
    require(type(value) is dict and set(value)=={'schema','identity_summary','genuine_input_binding','source_receipt',
      'all_four_DATA_guard_normal_return','genuine_input_checks_complete','private_pin','source_context_sha256',
      'H_fact_sha256','post_checks_complete',*FALSE_FLAGS} and value['schema']==SCHEMA
      and value['all_four_DATA_guard_normal_return'] is value['genuine_input_checks_complete']
        is value['post_checks_complete'] is True
      and value['H_fact_sha256']==H_FACT_SHA256
      and value['source_context_sha256']==sha(canonical(source_context()))
      and value['genuine_input_binding']==source_context()['input_binding']
      and all(value[key] is False for key in FALSE_FLAGS),'output')
    diagnosis.validate_summary(value['identity_summary'])
    require(value['private_pin']==value['identity_summary']['private_payload_pin'],'output')
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
            preflight(args,deadline);environment._bootstrap_cli_logging();previous.ar._credential_free()
            if args.operation=='validate':
                raw=sys.stdin.buffer.read(MAX_OUTPUT+1);validate_output(raw,args.actual_exit,args)
                sys.stdout.buffer.write(raw);return 0
            outcome=run(args,deadline);raw=canonical({'binding':binding(args),'outcome':outcome})+b'\n'
            code=2 if 'failure' in outcome else 0;validate_output(raw,code,args);sys.stdout.buffer.write(raw);return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure(args,error))+b'\n');return 2


if __name__=='__main__':raise SystemExit(main())
