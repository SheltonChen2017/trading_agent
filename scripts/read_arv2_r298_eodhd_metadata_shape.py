"""One new fixed AU metadata DATA shape read, never a capture or admission.

Only known public field names, types, hashes and predicate flags are emitted.
Unknown names are hash-only. No vendor values, names, prices, token, historical
body or old operational report/control is returned or read by this protocol.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
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
from scripts import run_arv2_r298_eodhd_history_diagnostic as au
from scripts import arv2_r298_fixed_data_guard as guard_module

SOURCE=ROOT/'scripts/read_arv2_r298_eodhd_metadata_shape.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_eodhd_history_diagnostic/R326-20261027-AV'
SCHEMA='arv2-r298-fixed-EODHD-metadata-shape-av-v1'
admitted,environment,PYTHON=au.admitted,au.environment,au.PYTHON
canonical,sha,pin,metadata=au.canonical,au.sha,au.pin,au.metadata
SECONDS,MAX_OUTPUT=30,65536
AU_SOURCE_SHA256='8f837fee5421cac1981894ffc40c0a2ea3b1f93c298304607f184eb98bc80f29'
DATA_PLAN={'au_metadata':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_history_diagnostic/R326-20261027-AU/metadata-private.json',
    'byte_count':170,'sha256':'27fe1cfd219c064793151e03c98ce70eb43889b568056d5810f8db3dc2b1355a'}}
KNOWN=frozenset(('Code','Name','Country','Exchange','Currency','Type','Isin','ISIN','isin',
    'code','name','country','exchange','currency','type'))
EXPECTED={'code':'SPY','type':'ETF','currency':'USD','isin':'US78462F1030'}
TYPES=frozenset(('null','boolean','number','string','array','object'))
FALSE_FLAGS={'identity_accepted':False,'price_input_admitted':False,'QC_transfer_granted':False,
    'provider_contact':False,'credential_access':False,'history_body_read':False,'old_control_read':False,
    'licensed_values_disclosed':False,'point_in_time_proven':False,'formal_forward_ready':False,'paper_or_live_ready':False}
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
    """Exact externally retained facts, not a fabricated AU success or new grant."""
    return {'schema':SCHEMA+'-AU-failure-binding','AU_head':'4302c6519d8118de265af1535f029c001202c4d6',
        'AU_source_sha256':AU_SOURCE_SHA256,'parent_actual_exit':2,'native_validator_actual_exit':0,
        'parent_stdout_pin':{'byte_count':5769,'sha256':'5f3862c2e836e5ee858040bc2306b426af5352beb124b0c9bc7f6aa18a63a343'},
        'validator_stdout_pin':{'byte_count':5769,'sha256':'5f3862c2e836e5ee858040bc2306b426af5352beb124b0c9bc7f6aa18a63a343'},
        'metadata_DATA_pin':{key:DATA_PLAN['au_metadata'][key] for key in ('byte_count','sha256')},
        'AU_attempt_spent':True,'failure_evidence_authenticated':True,'AU_identity_accepted':False,
        'history_RAW_six_dates_reported':True,'history_report_is_not_identity_or_price_admission':True,
        'new_operation_or_read_granted':False}


def pins():
    values=au.pins();require('scripts/run_arv2_r298_eodhd_history_diagnostic.py' not in values,'source_pin')
    values['scripts/run_arv2_r298_eodhd_history_diagnostic.py']=AU_SOURCE_SHA256;return values


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),
        'control':str(CONTROL),'python':str(PYTHON),'source_pins':pins(),'seconds':SECONDS,
        'maximum_output_bytes':MAX_OUTPUT,'data_plan':DATA_PLAN,'source_read_schedule':guard_module.profile_record(DATA_PLAN),
        'AU_failure_binding':observed_failure(),'purpose':'diagnose_exact_retained_AU_metadata_shape_without_values_or_new_provider_contact',
        'known_field_names':sorted(KNOWN),'unknown_field_names_hash_only':True,'maximum_fields':32,
        'public_expected_constants':EXPECTED,'byte_pin_before_JSON':True,'normal_source_return_before_emit':True,
        'strict_duplicate_key_refusal':True,'value_hash_namespace':'typed_canonical_JSON_Decimal_as_exact_text',
        'claim_before_metadata_DATA_read':True,'deadline_uninterruptible_IO_host_suspension_qualification':True,**FALSE_FLAGS}


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
    policy=au.ap.previous._artifact_policy([ROOT/DATA_PLAN['au_metadata']['relative_path'],CONTROL.parent])
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


def _type(value):
    if value is None:return 'null'
    if type(value) is bool:return 'boolean'
    if type(value) is Decimal:return 'number'
    if type(value) is str:return 'string'
    if type(value) is list:return 'array'
    if type(value) is dict:return 'object'
    raise Refused('shape')


def _typed(value,depth=0):
    require(depth<=16,'shape');kind=_type(value)
    if kind=='number':require(value.is_finite(),'shape');payload=str(value)
    elif kind=='object':
        require(len(value)<=32,'shape');payload=[[key,_typed(child,depth+1)] for key,child in sorted(value.items())]
    elif kind=='array':require(len(value)<=32,'shape');payload=[_typed(child,depth+1) for child in value]
    else:payload=value
    return {'type':kind,'value':payload}


def shape(raw):
    require(type(raw) is bytes and 0<len(raw)<=65536,'shape')
    try:value=au._decode(raw,'metadata_shape')
    except BaseException:raise Refused('shape') from None
    top=_type(value);count=len(value) if type(value) is list else None
    require(count is None or count<=32,'shape')
    row=value[0] if type(value) is list and len(value)==1 and type(value[0]) is dict else value if type(value) is dict else None
    selection='single_array_object' if type(value) is list and row is not None else 'top_object' if type(value) is dict else 'no_unique_object'
    require(row is None or len(row)<=32,'shape');fields=[]
    if row is not None:
        for name,item in sorted(row.items()):
            require(type(name) is str and len(name)<=128,'shape');known=name in KNOWN
            ascii_string=type(item) is str and all(ord(char)<128 for char in item)
            printable=type(item) is str and all(32<=ord(char)<=126 for char in item)
            entry={'known_name':known,'name_sha256':sha(canonical(name)),'value_type':_type(item),
                'value_sha256':sha(canonical(_typed(item))),'ASCII_string':ascii_string,'printable_ASCII_string':printable,
                'old_AU_bounded_nonempty_printable_ASCII_string':printable and 0<len(item)<=512,
                'public_expected_match':item==EXPECTED[name.casefold()] if known and name.casefold() in EXPECTED else None}
            if known:entry['name']=name
            fields.append(entry)
    one=type(value) is list and len(value)==1;is_object=one and type(value[0]) is dict
    exact=is_object and set(value[0])=={'Code','Name','Country','Exchange','Currency','Type','Isin'}
    strings=bool(is_object and all(key in value[0] and type(value[0][key]) is str and 0<len(value[0][key])<=512
        and all(32<=ord(char)<=126 for char in value[0][key]) for key in ('Code','Name','Country','Exchange','Currency','Type')))
    isin=bool(is_object and 'Isin' in value[0] and (value[0]['Isin'] is None or type(value[0]['Isin']) is str and len(value[0]['Isin'])<=32))
    result={'schema':SCHEMA+'-shape','source_pin':pin(raw),'top_level_type':top,'array_row_count':count,
        'field_selection':selection,'selected_field_count':len(fields),'fields':fields,
        'field_inventory_sha256':sha(canonical(fields)),'original_AU_predicates':{'one_row_array':one,'row_object':is_object,
            'exact_seven_keys':exact,'six_bounded_printable_ASCII_strings':strings,'Isin_type_bound':isin,
            'would_pass_metadata_shape':bool(exact and strings and isin)},**FALSE_FLAGS}
    validate_shape(result);return result


def validate_shape(value):
    require(type(value) is dict and set(value)=={'schema','source_pin','top_level_type','array_row_count','field_selection',
        'selected_field_count','fields','field_inventory_sha256','original_AU_predicates',*FALSE_FLAGS}
        and value['schema']==SCHEMA+'-shape' and value['top_level_type'] in TYPES
        and (value['array_row_count'] is None or type(value['array_row_count']) is int and 0<=value['array_row_count']<=32)
        and value['field_selection'] in ('single_array_object','top_object','no_unique_object')
        and type(value['fields']) is list and type(value['selected_field_count']) is int
        and value['selected_field_count']==len(value['fields'])<=32
        and value['field_inventory_sha256']==sha(canonical(value['fields']))
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    au.ap._pin(value['source_pin'],65536)
    for field in value['fields']:
        require(type(field) is dict and type(field.get('known_name')) is bool and set(field)=={
            'known_name','name_sha256','value_type','value_sha256','ASCII_string','printable_ASCII_string',
            'old_AU_bounded_nonempty_printable_ASCII_string','public_expected_match',*({'name'} if field['known_name'] else set())}
            and _hash(field['name_sha256']) and _hash(field['value_sha256']) and field['value_type'] in TYPES
            and all(type(field[key]) is bool for key in ('ASCII_string','printable_ASCII_string','old_AU_bounded_nonempty_printable_ASCII_string'))
            and (field['public_expected_match'] is None or type(field['public_expected_match']) is bool),'output')
        if field['known_name']:require(field['name'] in KNOWN and field['name_sha256']==sha(canonical(field['name'])),'output')
        require(type(field['public_expected_match']) is bool if field['known_name'] and field['name'].casefold() in EXPECTED
            else field['public_expected_match'] is None,'output')
    predicates=value['original_AU_predicates']
    require(type(predicates) is dict and set(predicates)=={'one_row_array','row_object','exact_seven_keys',
        'six_bounded_printable_ASCII_strings','Isin_type_bound','would_pass_metadata_shape'}
        and all(type(item) is bool for item in predicates.values())
        and predicates['would_pass_metadata_shape'] is (predicates['exact_seven_keys'] and predicates['six_bounded_printable_ASCII_strings'] and predicates['Isin_type_bound']),'output')
    return value


def run(args,deadline):
    with Store() as store:
        store.write('claim.json',canonical(binding(args)))
        with guard_module.FixedDataGuard(DATA_PLAN,deadline=deadline) as guard:
            raw=guard.read_all_once()['au_metadata'];require(pin(raw)=={key:DATA_PLAN['au_metadata'][key] for key in ('byte_count','sha256')},'source_binding')
            result=shape(raw);guard.verify();receipt=guard_module.validate_receipt(guard.receipt(),DATA_PLAN)
        remaining(deadline);preflight(args,deadline);environment.require_safe_environment();store.verify()
        result={'schema':SCHEMA+'-result','shape':result,'source_guard_receipt':receipt,'source_guard_normal_return':True,
            'AU_failure_binding_sha256':sha(canonical(observed_failure())),**FALSE_FLAGS}
        raw=canonical({'binding':binding(args),'result':result})+b'\n'
        require(len(raw)<=MAX_OUTPUT,'output_bound');store.write('result-metadata.json',raw);store.verify()
    remaining(deadline);return raw


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n')
        and raw.count(b'\n')==1 and type(actual_exit) is int and actual_exit in (0,2),'output')
    value=au.parse(raw[:-1]);require(value.get('binding')==binding(args),'output')
    if set(value)=={'binding','failure_code','allocation_unknown',*FALSE_FLAGS}:
        require(actual_exit==2 and value['failure_code'] in FINITE and value['allocation_unknown'] is True
            and all(value[key] is False for key in FALSE_FLAGS),'output');return value
    require(actual_exit==0 and set(value)=={'binding','result'},'output');result=value['result']
    require(type(result) is dict and set(result)=={'schema','shape','source_guard_receipt','source_guard_normal_return',
        'AU_failure_binding_sha256',*FALSE_FLAGS} and result['schema']==SCHEMA+'-result'
        and result['source_guard_normal_return'] is True and result['AU_failure_binding_sha256']==sha(canonical(observed_failure()))
        and all(result[key] is False for key in FALSE_FLAGS),'output')
    validate_shape(result['shape']);require(result['shape']['source_pin']=={
        key:DATA_PLAN['au_metadata'][key] for key in ('byte_count','sha256')},'output')
    guard_module.validate_receipt(result['source_guard_receipt'],DATA_PLAN);return value


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
