"""One offline identifier-format diagnosis of the fixed BB crosswalk DATA.

Complete BA bytes and all preserved BB rows are authenticated before analysis.
Identifier shape/substring observations never repair identifiers, select a new
source, admit a route, or claim fresh genuine-package or historical proof.
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
import sys
import time
from types import SimpleNamespace

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import prepare_arv2_r298_eodhd_crosswalk as bb
from scripts import arv2_r298_bb_source_binding as anchor
from scripts import arv2_r298_isin_cusip_evidence as isin_evidence

SOURCE=ROOT/'scripts/read_arv2_r298_eodhd_crosswalk_gaps.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_eodhd_crosswalk/R326-20261027-BC'
SCHEMA='arv2-r298-offline-EODHD-identifier-gap-diagnosis-bc-v1'
admitted,environment,PYTHON=bb.admitted,bb.environment,bb.PYTHON
ba,crosswalk,guard_module=bb.ba,bb.crosswalk,bb.guard_module
canonical,sha,pin,parse,metadata=bb.canonical,bb.sha,bb.pin,bb.parse,bb.metadata
SECONDS,VALIDATOR_SECONDS,MAX_OUTPUT=300,30,131072
MAX_REFERENCE_VISITS,MIN_FREE_DISK=2000000,4*1024*1024
FACT_SHA256='7b5810185359ea96cd27e94afa627887c34ed29ce82841972e61545a41f48617'
RESULT_SHA256='04526fa38e528d262affefcd038274c44536d1b0f04ee49aaac72eff6d4d559e'
CROSSWALK_SUMMARY_SHA256='00850fc4938d09782af6dc9abfb4a7acb82f2ee5f019b0fca3920d94b2ceac10'
ISIN_EVIDENCE_PROFILE_SHA256='4e2a2b4b97fa80b568b79fb3a591b2495adb6166d916b2a2bd9bd4e03bf22221'
DATA_PLAN={'crosswalk':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_crosswalk/R326-20261027-BB/crosswalk-private.json',
    'byte_count':13445076,'sha256':'5006dc2f1313d02c18f521172e2e454ca190a0191e2f85799b54a9d7d963d753'},**bb.CATALOG_PLAN}
NEW_PINS={
    'scripts/prepare_arv2_r298_eodhd_crosswalk.py':'daec25bbe62c5855e0b21420f695f9816a87093f41c2f19f83452393abe66ab6',
    'scripts/arv2_r298_bb_source_binding.py':'8aa1f5c9379f94275535c158c61c791ee482ba49fa01be299bbdd2b3ed921b5c',
    'scripts/arv2_r298_isin_cusip_evidence.py':'fb9fd313f7c88536e08ac163d299f46ab773442d8e7900ca7debcf131fb14c4e'}
FALSE_FLAGS={**bb.FALSE_FLAGS,'fresh_genuine_package_authenticated':False,'identifiers_repaired':False,
    'CUSIP8_or_zero_loss_admitted_as_identity':False,'new_route_created':False,'new_source_selected':False}
FINITE=frozenset(('host','arguments','environment','git_state','source_pin','source_binding','deadline','disk_budget',
    'claim_spent','output_changed','output_security','output_write','output_bound','source_bytes','catalog','private',
    'mapping_reproduction','reference_budget','diagnosis','output','os_error','unknown'))|frozenset('guard_'+code for code in guard_module.FINITE)
FIELD_CATEGORIES={
    'figi':('missing','null','type','empty','length','format','checksum','valid'),
    'cusip':('missing','null','type','empty','length8','length_other','format','checksum','valid'),
    'symbol':('missing','null','type','empty','length','format','valid'),
    'isin':('missing','null','type','empty','length','format','checksum','valid')}
OBSERVATIONS=('source_has_related_mapping','exact_FIGI_and_checksum_CUSIP9_pair_present',
    'same_FIGI_CUSIP8_base_equal_observed','same_FIGI_CUSIP9_leading_zero_loss_observed',
    'same_FIGI_CUSIP8_base_leading_zero_loss_observed')
TOKEN_SCOPES=('validated_original','union_only')
ISIN_RAW_STATES=('raw_missing_null_or_empty','raw_nonempty_invalid','raw_valid_different','raw_agrees')
DERIVED_FIGI_STATES=('same_valid_FIGI','other_valid_FIGI','missing_null_or_empty_FIGI','nonempty_invalid_FIGI')
COMMON_FIELDS=frozenset(('AP_role','potential','source_composite_figi','available_source_cusip_union',
    'validated_original_cusip_tokens','qualified_current_cusip_tokens','status','reason','figi_only_observed',
    'mapping_indices','catalog_references','route'))
STOCK_FIELDS=COMMON_FIELDS|frozenset(('binding_ordinal','binding','original_proof',
    'original_source_row_sha256','original_identity_evidence_sha256'))
FUND_FIELDS=COMMON_FIELDS|frozenset(('fund_ordinal','ticker'))
RESULT_FIELDS=frozenset(('status','reason','figi_only_observed','mapping_indices','catalog_references','route'))


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
    if type(error) is crosswalk.Refused:return 'deadline' if crosswalk.finite(error)=='deadline' else 'private'
    if type(error) is bb.Refused:return 'source_binding'
    if type(error) is ba.Refused:return 'catalog'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline) and 0<deadline-time.monotonic()<=SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def source_context():
    fact,result=anchor.observed_fact(),anchor.result_summary()
    require(sha(canonical(fact))==FACT_SHA256 and sha(canonical(result))==RESULT_SHA256
        and sha(canonical(anchor.crosswalk_summary()))==CROSSWALK_SUMMARY_SHA256
        and anchor.crosswalk_summary()==result['crosswalk_summary'],'source_binding')
    require(fact['binding']=={'schema':bb.SCHEMA,'expected_head':'cdc902b3b1dd3715b6f4033016b68620e02a1403',
        'caller_sha256':NEW_PINS['scripts/prepare_arv2_r298_eodhd_crosswalk.py'],
        'profile_sha256':'43f624ac4543403ac58ff2e287659382c12f3a7ef7c474c99eb3c10e733f76f7'}
        and fact['data_plan']==anchor.data_plan()=={'crosswalk':DATA_PLAN['crosswalk']},'source_binding')
    old=SimpleNamespace(**{key:value for key,value in fact['binding'].items() if key!='schema'})
    report=pin(canonical({**fact['binding'],'result':result}));require(report==fact['report'],'source_binding')
    raw=canonical({'binding':fact['binding'],'outcome':{'result':result,'report':report}})+bytes([10])
    bb.validate_output(raw,0,old)
    for role in ('producer','validator'):
        actual=fact[role]
        try:ba.ap.public_transport._actual_metadata(actual)
        except BaseException:raise Refused('source_binding') from None
        require(type(actual['actual_exit']) is int and actual['actual_exit']==0 and actual['spawn_observed'] is True
            and actual['bound'] is None and actual['stderr_bytes']==0 and actual['stderr_sha256']==sha(b'')
            and actual['stdout_bytes']==len(raw) and actual['stdout_sha256']==sha(raw),'source_binding')
    for field in ('technical_observation_authenticated','all_original_rows_retained','both_source_guards_normal_return',
        'genuine_input_unchanged','post_checks_complete'):require(fact[field] is True,'source_binding')
    for field in ('new_operation_or_read_granted','crosswalk_admitted','price_input_admitted',
        'complete_strategy_price_coverage_proven','point_in_time_proven','permanent_identity_proven','formal_forward_ready','paper_or_live_ready'):
        require(fact[field] is False,'source_binding')
    require(result['private_pin']=={key:DATA_PLAN['crosswalk'][key] for key in ('byte_count','sha256')},'source_binding')
    require(sha(canonical(isin_evidence.profile_record()))==ISIN_EVIDENCE_PROFILE_SHA256,'source_binding')
    guard_module.checked_plan(DATA_PLAN)
    return {'BB_fact_sha256':FACT_SHA256,'BB_result_sha256':RESULT_SHA256,'BB_summary_sha256':CROSSWALK_SUMMARY_SHA256,
        'BB_result':result,'BA_context':bb.source_context()}


def pins():
    values=bb.pins()
    for name,value in NEW_PINS.items():
        require(name not in values or values[name]==value,'source_pin');values[name]=value
    return values


def profile_record():
    source_context()
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),'control':str(CONTROL),
        'python':str(PYTHON),'source_pins':pins(),'seconds':SECONDS,'validator_seconds':VALIDATOR_SECONDS,
        'maximum_output_bytes':MAX_OUTPUT,'maximum_related_mapping_reference_visits':MAX_REFERENCE_VISITS,
        'minimum_free_disk_bytes':MIN_FREE_DISK,'data_plan':DATA_PLAN,'source_guard_profile':guard_module.profile_record(DATA_PLAN),
        'BB_fact_sha256':FACT_SHA256,'BB_result_sha256':RESULT_SHA256,'BB_summary_sha256':CROSSWALK_SUMMARY_SHA256,
        'purpose':'offline_preserved_full_BB_crosswalk_and_complete_BA_mapping_identifier_format_diagnosis',
        'all_six_whole_byte_pins_before_any_DATA_JSON':True,'pure_complete_BA_analysis_before_mapping_diagnosis':True,
        'normal_source_return_before_metadata_publication':True,'claim_before_DATA_read':True,
        'all6151_original_bindings_plus8_funds_preserved_and_match_results_reproduced':True,
        'no_fresh_genuine_package_or_original_source_proof_claim':True,
        'references_counted_once_per_related_mapping_row_per_source_not_unique_global_rows':True,
        'CUSIP8_base_comparison_is_exact_source_CUSIP9_first_eight_characters_only':True,
        'leading_zero_loss_comparisons_are_diagnostic_only_never_identifier_transformation':True,
        'identifier_values_mapping_indices_catalog_names_and_rows_never_output':True,
        'field_categories':FIELD_CATEGORIES,'source_observation_flags':OBSERVATIONS,
        'ISIN_supported_prefixes':['US','CA'],'ISIN_token_scopes':TOKEN_SCOPES,'ISIN_raw_CUSIP_states':ISIN_RAW_STATES,
        'ISIN_and_embedded_CUSIP_are_same_datum_not_independent_corroboration':True,
        'nonempty_raw_CUSIP_never_overridden_and_original_vs_union_only_matches_separated':True,
        'global_derived_identifier_index_includes_all_mapping_rows_even_other_or_invalid_FIGI':True,
        'ISIN_observation_helper_profile_sha256':ISIN_EVIDENCE_PROFILE_SHA256,
        'deadline_uninterruptible_IO_host_suspension_qualification':True,**FALSE_FLAGS}


def binding(args):return {'schema':SCHEMA,'expected_head':args.expected_head,'caller_sha256':args.caller_sha256,'profile_sha256':args.profile_sha256}


def preflight(args,deadline):
    require(not admitted.v5._under_test() and sys.platform=='darwin' and os.name=='posix' and sys.version_info[:2]==(3,13)
        and Path(sys.executable)==PYTHON and Path.cwd()==ROOT and ROOT.resolve()==ROOT and Path(__file__).absolute()==SOURCE,'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256),'arguments')
    ba.ar._credential_free();environment._require_environment();source_context()
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
    leaves=[*(ROOT/row['relative_path'] for row in DATA_PLAN.values()),CONTROL.parent]
    policy=ba.ap.previous._artifact_policy(leaves)
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
        self.verify();require(name in ('claim.json','report.json','failure.json') and name not in self.files
            and len(self.files)<3 and type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT,'output_bound')
        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        old=metadata(os.fstat(fd));self.files[name]={'fd':fd,'metadata':old,'security':_security(fd)}
        for offset in range(0,len(raw),65536):remaining(deadline);ba._write(fd,raw[offset:offset+65536])
        fresh=metadata(os.fstat(fd));require(fresh[:6]==old[:6] and fresh[9]==old[9] and fresh[6]==len(raw),'output_changed')
        self.files[name]['metadata']=fresh;os.fsync(self.fd);self.verify();digest=hashlib.sha256()
        for offset in range(0,len(raw),65536):
            remaining(deadline);chunk=os.pread(fd,min(65536,len(raw)-offset),offset);require(chunk,'output_write');digest.update(chunk)
        require(digest.hexdigest()==sha(raw),'output_write');self.verify();return pin(raw)


def _field_category(row,field):
    if field not in row:return 'missing'
    value=row[field]
    if value is None:return 'null'
    if type(value) is not str:return 'type'
    if not value:return 'empty'
    if field=='symbol':
        if not 3<len(value)<=68:return 'length'
        return 'valid' if crosswalk._symbol(value) else 'format'
    if field=='cusip':
        if len(value)==8:return 'length8'
        if len(value)!=9:return 'length_other'
        if re.fullmatch('[A-Z0-9*@#]{8}[0-9]',value) is None:return 'format'
        return 'valid' if crosswalk._cusip(value) else 'checksum'
    if len(value)!=12:return 'length'
    expression='[B-DF-HJ-NP-TV-Z]{2}G[B-DF-HJ-NP-TV-Z0-9]{8}[0-9]' if field=='figi' else '[A-Z]{2}[A-Z0-9]{9}[0-9]'
    if re.fullmatch(expression,value) is None:return 'format'
    return 'valid' if (crosswalk._figi(value) if field=='figi' else crosswalk._isin(value)) else 'checksum'


def _fields():return {field:{category:0 for category in categories} for field,categories in FIELD_CATEGORIES.items()}


def _group():
    return {'source_count':0,'related_mapping_row_references':0,'related_mapping_unknown_field_references':0,
        'related_mapping_field_categories':_fields(),'source_observation_counts':{key:0 for key in OBSERVATIONS},
        'same_FIGI_ISIN_source_token_row_counts':_isin_counts(),'same_FIGI_ISIN_source_token_source_counts':_isin_counts(),
        'all_mapping_derived_source_token_FIGI_counts':{scope:{state:0 for state in DERIVED_FIGI_STATES} for scope in TOKEN_SCOPES}}


def _isin_counts():return {scope:{prefix:{state:0 for state in ISIN_RAW_STATES} for prefix in ('US','CA')} for scope in TOKEN_SCOPES}


def _raw_cusip_state(row,local):
    value=row.get('cusip')
    if value is None or value=='':return 'raw_missing_null_or_empty'
    if not crosswalk._cusip(value):return 'raw_nonempty_invalid'
    return 'raw_agrees' if value==local else 'raw_valid_different'


def _decode_private(raw,summary,deadline):
    record=crosswalk._loads(raw,summary['private_payload_pin'])
    require(type(record) is dict and set(record)=={'schema','source_fingerprint','stocks','funds'}
        and record['schema']==crosswalk.PRIVATE_SCHEMA and record['source_fingerprint']==summary['source_fingerprint']
        and type(record['stocks']) is type(record['funds']) is list and len(record['stocks'])==6151 and len(record['funds'])==8,'private')
    return record


def _sources(record,summary,context,deadline):
    sources=[];stream=hashlib.sha256();proofs=Counter();dispositions={'stocks':Counter(),'funds':Counter()}
    reasons={'stocks':Counter(),'funds':Counter()};role_counts=Counter();tokens=[0,0,0];identities=set();figis=set();last=None
    admission=context['BB_result']['genuine_input_binding']['binding_contract']['security_master_admission_sha256']
    for table,items in (('stocks',record['stocks']),('funds',record['funds'])):
        for ordinal,item in enumerate(items):
            remaining(deadline);require(type(item) is dict and set(item)==(STOCK_FIELDS if table=='stocks' else FUND_FIELDS),'private')
            require(item['AP_role'] in crosswalk.AP_ROLES and type(item['potential']) is bool
                and item['status'] in ('matched_current_crosswalk','unresolved') and type(item['figi_only_observed']) is bool
                and ((item['reason'] in crosswalk.REASONS) if item['status']=='unresolved' else item['reason'] is None),'private')
            original,current,union=(item[key] for key in ('validated_original_cusip_tokens','qualified_current_cusip_tokens','available_source_cusip_union'))
            for values in (original,current):require(values is None or type(values) is list
                and all(type(value) is str and 0<len(value)<=64 for value in values) and len(values)==len(set(values)),'private')
            require(type(union) is list and union==sorted(set(original or ())|set(current or ())) and len(union)<=4096
                and type(item['source_composite_figi']) is str,'private')
            if table=='stocks':
                row=item['binding']
                try:checked=crosswalk.prices.native.figi._input_row(row,admission)
                except BaseException:raise Refused('private') from None
                require(checked==row and type(item['binding_ordinal']) is int and item['binding_ordinal']==ordinal
                    and (last is None or last<row['security_id']) and row['security_id'] not in identities
                    and row['composite_figi'] not in figis and item['source_composite_figi']==row['composite_figi']
                    and item['original_proof'] in ('pass','refused','unavailable')
                    and item['original_source_row_sha256']==row['source_row_sha256']
                    and item['original_identity_evidence_sha256']==row['identity_evidence_sha256']
                    and ((item['AP_role']=='conditional_never_potential_empty_initial_holdings_required') is (not item['potential'])),'private')
                last=row['security_id'];identities.add(last);figis.add(row['composite_figi'])
                stream.update(crosswalk.prices.native.figi._canonical(row));proofs[item['original_proof']]+=1;role_counts[item['AP_role']]+=1
                source={'kind':'stock','ordinal':ordinal,'binding':row,'original_proof':item['original_proof'],
                    'owner':('stock',row['security_id'],row['composite_figi'])}
            else:
                require(type(item['fund_ordinal']) is int and item['fund_ordinal']==ordinal and item['ticker'] in crosswalk.prices.native.UNIVERSES
                    and item['potential'] is True and item['AP_role']=='Sharadar_RAW_full_window','private')
                source={'kind':'fund','ordinal':ordinal,'ticker':item['ticker'],'owner':('fund',item['ticker'],item['source_composite_figi'])}
            for index,values in enumerate((original,current,union)):tokens[index]+=len(values or ())
            source.update(figi=item['source_composite_figi'],tokens=union,original_tokens=original,
                AP_role=item['AP_role'],potential=item['potential'])
            sources.append(source);dispositions[table][item['status']]+=1
            if item['reason'] is not None:reasons[table][item['reason']]+=1
    require(stream.hexdigest()==summary['source_pins']['genuine_binding_stream_sha256']
        and dict(proofs)=={key:value for key,value in summary['original_proof_counts'].items() if value}
        and dict(role_counts)==summary['AP_stock_role_counts']
        and tokens==[summary[key] for key in ('original_token_count','qualified_current_token_count','union_token_count')]
        and {key:dict(value) for key,value in dispositions.items()}==summary['disposition_counts']
        and {key:dict(value) for key,value in reasons.items()}==summary['reason_counts']
        and len({item['ticker'] for item in record['funds']})==8,'private')
    bb.validate_breakdown(bb._breakdown(crosswalk.PrivateCrosswalk(canonical(record),crosswalk.digest(summary)),summary),summary)
    return sources


def diagnose(record,mapping_rows,active,delisted,context,deadline):
    summary=context['BB_result']['crosswalk_summary'];sources=_sources(record,summary,context,deadline)
    require(type(mapping_rows) is list and len(mapping_rows)==summary['provider_row_counts']['mapping'],'catalog')
    indexes=crosswalk._indexes(active,delisted,mapping_rows,sources,deadline);results=[];symbol_owners=defaultdict(set)
    candidate_visits=0
    for source in sources:
        # Bound even the prospective matching traversal before a result can
        # amplify shared malformed/vendor symbol rows across many sources.
        candidates=set(indexes['map_figi'].get(source['figi'],()))
        for token in source['tokens']:candidates.update(indexes['map_cusip'].get(token,()))
        symbols={mapping_rows[index].get('symbol') for index in candidates if crosswalk._symbol(mapping_rows[index].get('symbol'))}
        for symbol in symbols:candidates.update(indexes['map_symbol'].get(symbol,()))
        candidate_visits+=len(candidates);require(candidate_visits<=MAX_REFERENCE_VISITS,'reference_budget')
        result=crosswalk._match(source,indexes,deadline);results.append(result)
        if result['route'] is not None:symbol_owners[result['route']['symbol']].add(source['owner'])
    for source,result in zip(sources,results,strict=True):
        if result['route'] is not None and len(symbol_owners[result['route']['symbol']])>1:
            result.update(status='unresolved',reason='EOD_symbol_owner_collision',route=None)
    global_fields=_fields();categories=[];derived=[];derived_index=defaultdict(set)
    for index,row in enumerate(mapping_rows):
        remaining(deadline);shape={field:_field_category(row,field) for field in FIELD_CATEGORIES};categories.append(shape)
        for field,category in shape.items():global_fields[field][category]+=1
        observation,evidence=isin_evidence.inspect(row.get('isin'))
        if evidence is None:derived.append(None)
        else:
            private=evidence.private_record();local=private['local_cusip9_from_ISIN']
            require(private['original_ISIN']==row['isin'] and private['provenance_supported_prefix'] in ('US','CA')
                and local==row['isin'][2:11] and crosswalk._cusip(local)
                and evidence.summary_sha256==isin_evidence.digest(observation),'diagnosis')
            derived.append((local,private['provenance_supported_prefix']));derived_index[local].add(index)
    groups=defaultdict(_group);funds=_group();visits=derived_visits=0
    for source,item,result in zip(sources,record['stocks']+record['funds'],results,strict=True):
        remaining(deadline);require({key:item[key] for key in RESULT_FIELDS}==result,'mapping_reproduction')
        related=item['mapping_indices'];references=item['catalog_references']
        require(type(related) is list and all(type(index) is int and 0<=index<len(mapping_rows) for index in related)
            and related==sorted(set(related)) and type(references) is list,'private')
        for reference in references:
            require(type(reference) is dict and set(reference)=={'table','ordinal'} and reference['table'] in ('active','delisted')
                and type(reference['ordinal']) is int and 0<=reference['ordinal']<len(active if reference['table']=='active' else delisted),'private')
        visits+=len(related);require(visits<=MAX_REFERENCE_VISITS,'reference_budget')
        group=groups[(source['AP_role'],source['potential'],item['status'],item['reason'])] if source['kind']=='stock' else funds
        group['source_count']+=1;group['related_mapping_row_references']+=len(related)
        flags={key:False for key in OBSERVATIONS};flags['source_has_related_mapping']=bool(related)
        source_tokens=[token for token in source['tokens'] if crosswalk._cusip(token)]
        bases={token[:8] for token in source_tokens};stripped={token.lstrip('0') for token in source_tokens if token.startswith('0')}
        stripped_bases={token[:8].lstrip('0') for token in source_tokens if token.startswith('0')}
        original_tokens=set(source['original_tokens'] or ());observed_isin=set()
        for index in related:
            remaining(deadline);row=mapping_rows[index]
            group['related_mapping_unknown_field_references']+=not indexes['records'][index]['known_fields']
            for field,category in categories[index].items():group['related_mapping_field_categories'][field][category]+=1
            if row.get('figi')!=source['figi']:continue
            value=row.get('cusip')
            flags['exact_FIGI_and_checksum_CUSIP9_pair_present']|=crosswalk._cusip(value) and value in source_tokens
            if type(value) is str:
                flags['same_FIGI_CUSIP8_base_equal_observed']|=len(value)==8 and value in bases
                flags['same_FIGI_CUSIP9_leading_zero_loss_observed']|=value in stripped
                flags['same_FIGI_CUSIP8_base_leading_zero_loss_observed']|=value in stripped_bases
            if derived[index] is not None:
                local,prefix=derived[index]
                if local in source_tokens:
                    scope='validated_original' if local in original_tokens else 'union_only';raw_state=_raw_cusip_state(row,local)
                    group['same_FIGI_ISIN_source_token_row_counts'][scope][prefix][raw_state]+=1
                    observed_isin.add((scope,prefix,raw_state))
        for flag,present in flags.items():group['source_observation_counts'][flag]+=present
        for scope,prefix,raw_state in observed_isin:group['same_FIGI_ISIN_source_token_source_counts'][scope][prefix][raw_state]+=1
        all_derived=set()
        for token in source_tokens:all_derived.update(derived_index.get(token,()))
        derived_visits+=len(all_derived);require(visits+derived_visits<=MAX_REFERENCE_VISITS,'reference_budget')
        for index in all_derived:
            local,_=derived[index];scope='validated_original' if local in original_tokens else 'union_only';value=mapping_rows[index].get('figi')
            state=('same_valid_FIGI' if value==source['figi'] else 'other_valid_FIGI') if crosswalk._figi(value) else (
                'missing_null_or_empty_FIGI' if value is None or value=='' else 'nonempty_invalid_FIGI')
            group['all_mapping_derived_source_token_FIGI_counts'][scope][state]+=1
    grouped=[{'AP_role':role,'potential':potential,'BB_status':status,'BB_reason':reason,**group}
        for (role,potential,status,reason),group in sorted(groups.items(),key=lambda item:(item[0][0],item[0][1],item[0][2],item[0][3] or ''))]
    value={'schema':SCHEMA+'-diagnosis','BB_fact_sha256':FACT_SHA256,'BB_summary_sha256':CROSSWALK_SUMMARY_SHA256,
        'complete_mapping_row_count':len(mapping_rows),'global_mapping_field_categories':global_fields,
        'stock_groups':grouped,'funds':funds,'all6151_stock_and8_fund_rows_retained':True,
        'original_binding_stream_rechecked':True,'original_BB_match_results_reproduced':True,
        'related_mapping_reference_visits':visits,'derived_mapping_reference_visits':derived_visits,
        'exact_pair_absence_is_not_an_identity_repair':True,**FALSE_FLAGS}
    validate_diagnosis(value,context);return value


def _validate_group(group,extra):
    require(type(group) is dict and set(group)=={'source_count','related_mapping_row_references','related_mapping_unknown_field_references',
        'related_mapping_field_categories','source_observation_counts','same_FIGI_ISIN_source_token_row_counts',
        'same_FIGI_ISIN_source_token_source_counts','all_mapping_derived_source_token_FIGI_counts',*extra}
        and type(group['source_count']) is int and 0<group['source_count']<=6151
        and type(group['related_mapping_row_references']) is int and 0<=group['related_mapping_row_references']<=MAX_REFERENCE_VISITS
        and type(group['related_mapping_unknown_field_references']) is int
        and 0<=group['related_mapping_unknown_field_references']<=group['related_mapping_row_references']
        and type(group['source_observation_counts']) is dict and set(group['source_observation_counts'])==set(OBSERVATIONS)
        and all(type(count) is int and 0<=count<=group['source_count'] for count in group['source_observation_counts'].values()),'diagnosis')
    _validate_fields(group['related_mapping_field_categories'],group['related_mapping_row_references'])
    for key in ('same_FIGI_ISIN_source_token_row_counts','same_FIGI_ISIN_source_token_source_counts'):
        counts=group[key];require(type(counts) is dict and set(counts)==set(TOKEN_SCOPES),'diagnosis')
        for scope in TOKEN_SCOPES:
            require(type(counts[scope]) is dict and set(counts[scope])=={'US','CA'},'diagnosis')
            for prefix in ('US','CA'):
                require(type(counts[scope][prefix]) is dict and set(counts[scope][prefix])==set(ISIN_RAW_STATES)
                    and all(type(number) is int and 0<=number<=(group['source_count'] if key.endswith('source_counts') else group['related_mapping_row_references'])
                        for number in counts[scope][prefix].values()),'diagnosis')
    row_counts=group['same_FIGI_ISIN_source_token_row_counts'];source_counts=group['same_FIGI_ISIN_source_token_source_counts']
    require(sum(count for prefixes in row_counts.values() for counts in prefixes.values() for count in counts.values())<=group['related_mapping_row_references']
        and all(source_counts[scope][prefix][state]<=row_counts[scope][prefix][state] for scope in TOKEN_SCOPES
            for prefix in ('US','CA') for state in ISIN_RAW_STATES),'diagnosis')
    counts=group['all_mapping_derived_source_token_FIGI_counts']
    require(type(counts) is dict and set(counts)==set(TOKEN_SCOPES) and all(type(counts[scope]) is dict
        and set(counts[scope])==set(DERIVED_FIGI_STATES) and all(type(number) is int and 0<=number<=MAX_REFERENCE_VISITS
        for number in counts[scope].values()) for scope in TOKEN_SCOPES),'diagnosis')


def _validate_fields(value,count):
    require(type(value) is dict and set(value)==set(FIELD_CATEGORIES),'diagnosis')
    for field,categories in FIELD_CATEGORIES.items():
        require(type(value[field]) is dict and set(value[field])==set(categories)
            and all(type(number) is int and 0<=number<=MAX_REFERENCE_VISITS for number in value[field].values())
            and sum(value[field].values())==count,'diagnosis')


def validate_diagnosis(value,context):
    require(type(value) is dict and set(value)=={'schema','BB_fact_sha256','BB_summary_sha256','complete_mapping_row_count',
        'global_mapping_field_categories','stock_groups','funds','all6151_stock_and8_fund_rows_retained','original_binding_stream_rechecked',
        'original_BB_match_results_reproduced','related_mapping_reference_visits','derived_mapping_reference_visits',
        'exact_pair_absence_is_not_an_identity_repair',*FALSE_FLAGS}
        and value['schema']==SCHEMA+'-diagnosis' and value['BB_fact_sha256']==FACT_SHA256
        and value['BB_summary_sha256']==CROSSWALK_SUMMARY_SHA256 and value['all6151_stock_and8_fund_rows_retained'] is True
        and value['original_binding_stream_rechecked'] is value['original_BB_match_results_reproduced'] is True
        and value['exact_pair_absence_is_not_an_identity_repair'] is True and type(value['result_cell']) is int and value['result_cell']==0
        and all(value[key] is False for key in FALSE_FLAGS if key!='result_cell'),'diagnosis')
    summary=context['BB_result']['crosswalk_summary'];count=summary['provider_row_counts']['mapping']
    require(type(value['complete_mapping_row_count']) is int and value['complete_mapping_row_count']==count,'diagnosis')
    _validate_fields(value['global_mapping_field_categories'],count)
    require(type(value['stock_groups']) is list and 0<len(value['stock_groups'])<=2*len(crosswalk.AP_ROLES)*(len(crosswalk.REASONS)+1),'diagnosis')
    keys=[];groups=defaultdict(lambda:{'stock_count':0,'disposition_counts':Counter(),'unresolved_reason_counts':Counter()});visits=derived_visits=0
    for group in value['stock_groups']:
        _validate_group(group,{'AP_role','potential','BB_status','BB_reason'})
        role,potential,status,reason=(group[key] for key in ('AP_role','potential','BB_status','BB_reason'))
        require(role in crosswalk.AP_ROLES and type(potential) is bool and status in ('matched_current_crosswalk','unresolved')
            and (reason in crosswalk.REASONS if status=='unresolved' else reason is None),'diagnosis')
        keys.append((role,potential,status,reason));target=groups[(role,potential)];target['stock_count']+=group['source_count']
        target['disposition_counts'][status]+=group['source_count']
        if reason is not None:target['unresolved_reason_counts'][reason]+=group['source_count']
        visits+=group['related_mapping_row_references']
        derived_visits+=sum(number for counts in group['all_mapping_derived_source_token_FIGI_counts'].values() for number in counts.values())
    require(keys==sorted(set(keys),key=lambda item:(item[0],item[1],item[2],item[3] or '')),'diagnosis')
    breakdown=[{'AP_role':role,'potential':potential,'stock_count':group['stock_count'],
        'disposition_counts':dict(group['disposition_counts']),'unresolved_reason_counts':dict(group['unresolved_reason_counts'])}
        for (role,potential),group in sorted(groups.items())]
    bb.validate_breakdown(breakdown,summary)
    _validate_group(value['funds'],set());require(value['funds']['source_count']==8,'diagnosis');visits+=value['funds']['related_mapping_row_references']
    derived_visits+=sum(number for counts in value['funds']['all_mapping_derived_source_token_FIGI_counts'].values() for number in counts.values())
    require(type(value['related_mapping_reference_visits']) is type(value['derived_mapping_reference_visits']) is int
        and value['related_mapping_reference_visits']==visits and value['derived_mapping_reference_visits']==derived_visits
        and visits+derived_visits<=MAX_REFERENCE_VISITS,'diagnosis')
    return value


def construct(context,deadline):
    with guard_module.FixedDataGuard(DATA_PLAN,deadline=deadline) as guard:
        values=guard.read_all_once();bb._assert_bytes(values,DATA_PLAN)
        # All six whole-file hashes precede private/catalog parsing.
        active_raw,delisted_raw,mappings=bb._catalog_data({key:values[key] for key in bb.CATALOG_PLAN},context['BA_context'],deadline)
        active=crosswalk.catalogs.checked_symbol_rows(active_raw);delisted=crosswalk.catalogs.checked_symbol_rows(delisted_raw)
        summary=context['BB_result']['crosswalk_summary'];record=_decode_private(values['crosswalk'],summary,deadline)
        diagnosis=diagnose(record,mappings,active,delisted,context,deadline)
        guard.verify();receipt=guard_module.validate_receipt(guard.receipt(),DATA_PLAN)
        environment.require_safe_environment();remaining(deadline)
    return {'diagnosis':diagnosis,'source_receipt':receipt,'source_guard_normal_return':True}


def failure(args,error):return {'binding':binding(args),'failure_code':finite(error),'allocation_unknown':True,**FALSE_FLAGS}


def run(args,deadline):
    context=source_context();info=os.statvfs(ROOT);require(info.f_bavail*info.f_frsize>=MIN_FREE_DISK,'disk_budget')
    with Store() as store:
        store.write('claim.json',canonical(binding(args)),deadline)
        try:
            result=construct(context,deadline)
            preflight(args,deadline);environment.require_safe_environment();store.verify()
            result={'schema':SCHEMA,**result,'BB_fact_sha256':FACT_SHA256,'post_checks_complete':True,**FALSE_FLAGS}
            validate_result(result);report=store.write('report.json',canonical({**binding(args),'result':result}),deadline);store.verify()
            return {'result':result,'report':report}
        except BaseException as error:
            value=failure(args,error)
            try:store.write('failure.json',canonical(value),deadline)
            except BaseException:pass
            return {'failure':value}


def validate_result(value):
    require(type(value) is dict and set(value)=={'schema','diagnosis','source_receipt','source_guard_normal_return','BB_fact_sha256','post_checks_complete',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['BB_fact_sha256']==FACT_SHA256
        and value['source_guard_normal_return'] is value['post_checks_complete'] is True
        and type(value['result_cell']) is int and value['result_cell']==0
        and all(value[key] is False for key in FALSE_FLAGS if key!='result_cell'),'output')
    validate_diagnosis(value['diagnosis'],source_context());guard_module.validate_receipt(value['source_receipt'],DATA_PLAN)


def _failure(value,actual_exit):
    require(actual_exit==2 and type(value) is dict and set(value)=={'binding','failure_code','allocation_unknown',*FALSE_FLAGS}
        and value['failure_code'] in FINITE and value['allocation_unknown'] is True
        and type(value['result_cell']) is int and value['result_cell']==0
        and all(value[key] is False for key in FALSE_FLAGS if key!='result_cell'),'output')


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT and raw.endswith(bytes([10])) and raw.count(bytes([10]))==1
        and type(actual_exit) is int and actual_exit in (0,2),'output');value=parse(raw[:-1])
    require(type(value) is dict and value.get('binding')==binding(args),'output')
    if set(value)=={'binding','failure_code','allocation_unknown',*FALSE_FLAGS}:_failure(value,actual_exit);return value
    require(set(value)=={'binding','outcome'} and type(value['outcome']) is dict,'output');outcome=value['outcome']
    if set(outcome)=={'failure'}:
        require(actual_exit==2 and outcome['failure'].get('binding')==binding(args),'output');_failure(outcome['failure'],actual_exit)
    else:
        require(actual_exit==0 and set(outcome)=={'result','report'},'output');validate_result(outcome['result'])
        require(outcome['report']==pin(canonical({**binding(args),'result':outcome['result']})),'output')
    return value


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
