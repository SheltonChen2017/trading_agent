// Independent, one-shot owned-process observation; never source admission.
import { spawn as nodeSpawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import * as fs from 'node:fs';
import { performance } from 'node:perf_hooks';
import { Buffer } from 'node:buffer';

const ROOT='/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest';
const PYTHON='/opt/homebrew/Cellar/python@3.13/3.13.15/Frameworks/Python.framework/Versions/3.13/bin/python3.13';
const PYTHON_SHA='fdae91cd6e017f2053cd4e10457b6130e545597b12512ee4180c433ab9ba7dab';
const DRIVER='scripts/qualify_short_interest_usb_once.py';
const HELPER='scripts/diagnose_short_interest_code_read_interval.py';
const CODE_FILES=Object.freeze(['data/__init__.py','data/hashing.py',
  'research/short_interest_etf/firstrate_short_interest_inspection.py',
  'scripts/inspect_short_interest_usb_archive.py','scripts/inspect_short_interest_usb_code_snapshot.py',HELPER,DRIVER]);
const INVOCATION='si-usb-offline-once-20261104-v1';
const OLD_PROFILE='592c05adc1691030eb5aa3d93660f060248aaa25909bd3503781a446f292c43f';
const MODEL_POLICY='a403579c17c31010ae26eaddf1350a7f1d313cbf6bdae9b6d815f1ccd83121fe';
const MAXIMUM_MS=180000, SHUTDOWN_RESERVE_MS=1500, KILL_RESERVE_MS=750;
const MAX_STDOUT=65537, MAX_STDERR=4096, MAX_PRIVATE=16384;
const INPUTS=Object.freeze([
  '/Volumes/SANDISK/firstrate/fundamentals/Short_Interest/Full_Dataset.zip',
  '/Volumes/SANDISK/firstrate/fundamentals/Short_Interest/2026_data_only.zip',
  '/Volumes/SANDISK/firstrate/manifest.json',
  '/Volumes/SANDISK/firstrate/fundamentals/Short_Interest/Read_Me_Documentation.txt']);
const DIRECTORIES=Object.freeze(['/Volumes','/Volumes/SANDISK','/Volumes/SANDISK/firstrate',
  '/Volumes/SANDISK/firstrate/fundamentals','/Volumes/SANDISK/firstrate/fundamentals/Short_Interest']);
const SANDBOX=`(version 1)
(allow default)
(deny file-read* (subpath "/Volumes"))
(allow file-read* ${[...DIRECTORIES,...INPUTS].map(p=>`(literal ${JSON.stringify(p)})`).join(' ')})
(deny file-write*)
(allow file-write-data (literal "/dev/null"))
(deny file-read* (subpath "/Users/sheltonchen/Library/Keychains"))
(deny file-read* (subpath "/Library/Keychains"))
(deny mach-lookup (global-name "com.apple.securityd"))
(deny mach-lookup (global-name "com.apple.securityd.xpc"))
(deny process-exec (literal "/usr/bin/security"))
(deny process-exec (literal "/bin/sh"))
(deny process-exec (literal "/bin/zsh"))
(deny process-exec (literal "/usr/bin/osascript"))
(deny process-exec (regex #"/git-credential-[^/]+$"))
`;
const ENV=Object.freeze({PATH:'/usr/bin:/bin',LC_ALL:'C',GIT_OPTIONAL_LOCKS:'0',
  GIT_TERMINAL_PROMPT:'0',GIT_CONFIG_NOSYSTEM:'1',PYTHONDONTWRITEBYTECODE:'1'});
const OWN_CODES=new Set(['configuration','attempt_spent','observer_source','clock','deadline','host','spawn',
  'stdout_limit','stdout_type','stderr','stderr_limit','stream','exit','close','EOF','packet','lineage',
  'proof','private_aggregate','signal','cleanup','late_getter']);
let actualUsed=false;

function need(value,code){if(!value)throw Object.freeze({fixedCode:OWN_CODES.has(code)?code:'packet'});}
function sha(raw){return createHash('sha256').update(raw).digest('hex');}
function own(obj,key){return Object.prototype.hasOwnProperty.call(obj,key);}
function dict(value){return value!==null&&typeof value==='object'&&!Array.isArray(value);}
function keys(value,expected){return dict(value)&&Object.keys(value).length===expected.length&&expected.every(k=>own(value,k));}
function hex(value,n=64){return typeof value==='string'&&new RegExp(`^[0-9a-f]{${n}}$`).test(value);}
function integer(value,min=0,max=Number.MAX_SAFE_INTEGER){return typeof value==='number'&&Number.isSafeInteger(value)&&value>=min&&value<=max;}
export function canonicalJson(value){
  if(value===null||typeof value==='boolean'||typeof value==='string')return JSON.stringify(value);
  if(typeof value==='number'){need(Number.isFinite(value)&&Number.isSafeInteger(value),'packet');return JSON.stringify(value);}
  if(Array.isArray(value))return '['+value.map(canonicalJson).join(',')+']';
  need(dict(value),'packet');return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonicalJson(value[k])).join(',')+'}';
}
function exact(value,expected){
  if(expected===null||typeof expected!=='object')return typeof value===typeof expected&&value===expected;
  if(Array.isArray(expected))return Array.isArray(value)&&value.length===expected.length&&expected.every((v,i)=>exact(value[i],v));
  return keys(value,Object.keys(expected))&&Object.keys(expected).every(k=>exact(value[k],expected[k]));
}
function configuration(encoded){
  need(typeof encoded==='string'&&Buffer.byteLength(encoded)<=8192,'configuration');
  let value;try{value=JSON.parse(encoded);}catch{need(false,'configuration');}
  need(canonicalJson(value)===encoded&&keys(value,['runtime_head','matching_remote','invocation_id','code_manifest']),'configuration');
  need(hex(value.runtime_head,40)&&hex(value.matching_remote,40)&&value.invocation_id===INVOCATION,'configuration');
  need(keys(value.code_manifest,CODE_FILES)&&CODE_FILES.every(k=>hex(value.code_manifest[k])),'configuration');
  return value;
}
function sourceIdentity(){
  const prefix='data:text/javascript;base64,';
  need(import.meta.url.startsWith(prefix),'observer_source');
  const encoded=import.meta.url.slice(prefix.length),raw=Buffer.from(encoded,'base64');
  need(raw.toString('base64')===encoded&&raw.length>0&&raw.length<=131072,'observer_source');return sha(raw);
}
function statPin(info){return ['dev','ino','uid','gid','mode','nlink','size','mtimeNs','ctimeNs'].map(k=>String(info[k]));}
function nullPin(info){return ['dev','ino','uid','gid','mode','nlink','rdev'].map(k=>String(info[k]));}
function readBounded(fd,maximum){
  const pieces=[];let count=0;
  while(true){const part=Buffer.alloc(Math.min(65536,maximum+1-count));const n=fs.readSync(fd,part,0,part.length,null);
    if(!n)break;count+=n;need(count<=maximum,'host');pieces.push(Buffer.from(part.subarray(0,n)));}
  return Buffer.concat(pieces);
}
function validateHost(original=null){
  need(process.platform==='darwin'&&process.getuid()===501,'host');
  let fd=null,first=null,result;
  try{
    fd=fs.openSync(PYTHON,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_CLOEXEC|fs.constants.O_NONBLOCK);
    const info=fs.fstatSync(fd,{bigint:true}),pin=statPin(info);
    need(info.isFile()&&info.uid===501n&&info.gid===80n&&info.mode===0o100755n&&info.nlink===1n&&info.size===34640n,'host');
    need(sha(readBounded(fd,34640))===PYTHON_SHA&&exact(statPin(fs.fstatSync(fd,{bigint:true})),pin)
      &&exact(statPin(fs.lstatSync(PYTHON,{bigint:true})),pin),'host');
    result={runtime:pin};
  }catch(error){first=error;}finally{if(fd!==null)try{fs.closeSync(fd);}catch(error){if(first===null)first=error;}}
  if(first!==null)throw first;
  need(exact(statPin(fs.lstatSync(PYTHON,{bigint:true})),result.runtime),'host');
  let parent=null,device=null;
  try{
    parent=fs.openSync('/dev',fs.constants.O_RDONLY|fs.constants.O_DIRECTORY|fs.constants.O_NOFOLLOW|fs.constants.O_CLOEXEC);
    const p=fs.fstatSync(parent,{bigint:true});
    need(p.isDirectory()&&p.uid===0n&&p.gid===0n&&(p.mode&0o022n)===0n,'host');
    device=fs.openSync('/dev/null',fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_CLOEXEC|fs.constants.O_NONBLOCK);
    const q=fs.fstatSync(device,{bigint:true});
    need(q.isCharacterDevice()&&q.uid===0n&&q.gid===0n&&q.mode===0o020666n&&q.nlink===1n&&q.rdev===50331650n&&q.dev===p.dev,'host');
    result.nullParent=['dev','ino','uid','gid','mode'].map(k=>String(p[k]));result.nullDevice=nullPin(q);
    const named=fs.lstatSync('/dev',{bigint:true});
    need(exact(['dev','ino','uid','gid','mode'].map(k=>String(named[k])),result.nullParent)
      &&exact(nullPin(fs.lstatSync('/dev/null',{bigint:true})),result.nullDevice),'host');
  }catch(error){if(first===null)first=error;}finally{
    for(const owned of [device,parent])if(owned!==null)try{fs.closeSync(owned);}catch(error){if(first===null)first=error;}
  }
  if(first!==null)throw first;
  need(exact(nullPin(fs.lstatSync('/dev/null',{bigint:true})),result.nullDevice),'host');
  if(original!==null)need(exact(result,original),'host');
  return result;
}

const BOOTSTRAP=String.raw`import errno,hashlib,json,os,re,stat,sys,time
started=time.monotonic_ns()
root=${JSON.stringify(ROOT)};paths=${JSON.stringify(CODE_FILES)};driver=${JSON.stringify(DRIVER)}
class Refusal(Exception):pass
def need(v,c):
 if not v:raise Refusal(c)
def check():need(0<=started<=time.monotonic_ns() and time.monotonic_ns()-started<=180000000000,'clock')
pin=lambda q:(q.st_dev,q.st_ino,q.st_uid,q.st_gid,q.st_mode,q.st_nlink,q.st_size,q.st_mtime_ns,q.st_ctime_ns,getattr(q,'st_flags',0))
fd=None;first=None;cleanup=[];stage='arguments';bodies={}
def detail(e,s):
 a=BaseException.args.__get__(e,BaseException);c=a[0] if type(e) is Refusal and len(a)==1 and a[0] in ('arguments','owner','clock','code_shape','code_hash','code_stamp') else None
 return {'phase':s,'role':'bootstrap','code':c,'code_ordinal':None,'original_comparison':None,'actor':'unknown'}
try:
 need(len(sys.argv)==4,'arguments');head,remote,encoded=sys.argv[1:];mapping=json.loads(encoded)
 need(all(re.fullmatch('[0-9a-f]{40}',v) for v in(head,remote)) and type(mapping) is dict and set(mapping)==set(paths) and all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for v in mapping.values()),'arguments')
 check();owner=os.stat(root,follow_symlinks=False).st_uid;need(owner==os.geteuid()==501 and tuple(sys.version_info[:3])==(3,13,15),'owner')
 for name in paths:
  check();stage='code_open';path=root+'/'+name;fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK);q=os.fstat(fd)
  need(stat.S_ISREG(q.st_mode) and q.st_uid==owner and q.st_nlink==1 and not q.st_mode&0o022 and 0<=q.st_size<=1048576,'code_shape')
  stage='code_read';parts=[];total=0
  while True:
   check();part=os.read(fd,min(65536,1048577-total))
   if not part:break
   parts.append(part);total+=len(part);need(total<=1048576,'code_shape')
  raw=b''.join(parts);need(len(raw)==q.st_size and hashlib.sha256(raw).hexdigest()==mapping[name],'code_hash')
  need(pin(os.fstat(fd))==pin(q)==pin(os.stat(path,follow_symlinks=False)),'code_stamp');stage='code_close';os.close(fd);fd=None
  need(pin(os.stat(path,follow_symlinks=False))==pin(q),'code_stamp');bodies[name]=raw
 stage='compile';compiled=compile(bodies[driver],root+'/'+driver,'exec');check()
except BaseException as e:first=detail(e,stage)
finally:
 if fd is not None:
  try:os.close(fd)
  except BaseException as e:cleanup.append(detail(e,'code_close'))
if first is not None or cleanup:
 print(json.dumps({'schema':'si-usb-once-bootstrap-refusal-v1','invocation_id':${JSON.stringify(INVOCATION)},'status':'incomplete','source_qualified':False,'first_failure':first,'cleanup_failures':cleanup},sort_keys=True,separators=(',',':')),flush=True);raise SystemExit(2)
sys.argv=[root+'/'+driver,head,remote,mapping[driver]]
exec(compiled,{'__name__':'__main__','__file__':root+'/'+driver,'_BOOTSTRAP_START_NS':started})
`;

const ENVELOPE_KEYS=['schema','invocation_id','status','runtime_head','matching_remote','driver_sha256','interpreter_version',
  'maximum_whole_seconds','whole_start_monotonic_ns','whole_end_monotonic_ns','code_manifest_sha256','original_profile_proof',
  'private_model_aggregate','source_qualified','first_failure','cleanup_failures','denials',
  'external_OS_sandbox_and_independent_owned_wait_required','python_audit_covers_all_metadata',
  'extra_code_continuous_ancestor_timestamp_custody','git_scope','authority'];
const AUTHORITY={finite_offline_byte_inspection_only:true,source_qualified:false,source_admitted:false,
  protected_source_custody_verified:false,denominator_admitted:false,actual_input_admitted:false,ready_for_backtest:false,
  provider_HTTP:0,source_credential_reads:0,new_claims:0,new_STARTs:0,new_charged_bytes:0,outcome_looks:0,qc_attempts:0,QC_or_Safari:false};
const OLD_AUTHORITY={external_byte_inspection_only:true,source_admitted:false,protected_source_custody_verified:false,
  denominator_admitted:false,actual_input_admitted:false,ready_for_backtest:false,provider_HTTP:0,credential_reads:0,
  new_claims:0,new_STARTs:0,new_charged_bytes:0,outcome_looks:0,qc_attempts:0,QC_or_Safari:false};
const PROOF_KEYS=['schema','status','runtime_head','matching_remote','profile_sha256','code_mapping_sha256',
  'initial_code_file10_sha256','terminal_code_file10_sha256','code_file_original10_equal',
  'initial_ancestor_observations_sha256','terminal_ancestor_observations_sha256','continuous_shared_ancestor_timestamp_custody',
  'physical_root_identity_sha256','source_original10_sha256','inspection_report_sha256','model_policy_sha256',
  'all_initial_code_contexts_closed','all_source_contexts_closed','all_terminal_code_contexts_closed','executed_verified_RAM','authority','observation_sha256'];
const FACT_KEYS=['phase','role','code_ordinal','code','original_comparison','actor'];
const PHASES=new Set(['unknown','arguments','bootstrap','initial_code','source_open','model','source_audit','source_close',
  'source_after_close','terminal_code','final_guard','namespace_cleanup','final_format','original','extra_code','cleanup','code_open','code_read','code_close','compile']);
const FACT_CODES=new Set(['arguments','interpreter','attempt_spent','clock','root','code','code_changed','module_changed','original_result','private_aggregate',
  'namespace_changed','forbidden_open','forbidden_write','forbidden_socket','forbidden_subprocess','output_bound','cleanup',
  'owner','code_shape','code_hash','code_stamp','registration','root_changed','lane_changed','remote_changed','git_refused','code_bound',
  'runtime_changed','graph_changed','import_refused','namespace_occupied','snapshot_factory','snapshot_changed','snapshot_failed',
  'window_failed','clock_failed','input_changed','inspection_refused','read_arguments','clock_nonfinite','clock_or_deadline',
  'regular_bounded_single_link','read_byte_bound','read_failure_latched','original_directory_changed','original_file_stamp_changed',
  'original_file_bytes_changed','descriptor_close_failed','closed_original_required','post_close_original_changed',
  'designated_physical_root','exact_git_hashes_required','exact_head_remote_arguments_required','fixed_usb_input_changed',
  'lane_snapshot_changed','matching_remote_changed','model_namespace_occupied','terminal_code_changed','working_code_differs_from_commit']);
function fact(value){
  if(value===null)return null;need(keys(value,FACT_KEYS)||keys(value,[...FACT_KEYS,'exception_context_observation'])&&value.exception_context_observation===true,'packet');
  need(PHASES.has(value.phase)&&['unknown','bootstrap','code','full','year','manifest','readme'].includes(value.role)
    &&(value.code_ordinal===null||integer(value.code_ordinal,1,7))&&(value.code===null||FACT_CODES.has(value.code))&&value.actor==='unknown','packet');
  const comparison=value.original_comparison;
  if(comparison!==null){
    need(keys(comparison,['schema','entered_phase','role','code_ordinal','chain_ordinal','relation','mismatching_fields'])
      &&comparison.schema==='si-usb-original-comparison-diagnostic-v1'
      &&['initial_audit','held_audit','close_audit','post_close_reopen_initial_audit','post_close_reopen_close_audit','post_close_compare','post_close_named_audit'].includes(comparison.entered_phase)
      &&['unknown','code','full','year','manifest','readme'].includes(comparison.role)
      &&(comparison.code_ordinal===null||integer(comparison.code_ordinal,1,5))&&integer(comparison.chain_ordinal,0,32)
      &&['root_descriptor_vs_original','root_name_vs_original','directory_descriptor_vs_original','directory_name_vs_original',
        'file_descriptor_before_bytes_vs_original','file_name_before_bytes_vs_original','file_descriptor_after_bytes_vs_original',
        'file_name_after_bytes_vs_original','reopened_file_descriptor_vs_original','reopened_root_descriptor_vs_original',
        'reopened_directory_descriptor_vs_original','post_close_root_name_vs_original','post_close_directory_name_vs_original','post_close_file_name_vs_original'].includes(comparison.relation)
      &&Array.isArray(comparison.mismatching_fields)&&comparison.mismatching_fields.length>0&&comparison.mismatching_fields.length<=10
      &&new Set(comparison.mismatching_fields).size===comparison.mismatching_fields.length
      &&comparison.mismatching_fields.every(k=>['dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns','flags'].includes(k)),'packet');
  }
  return {phase:value.phase,role:value.role,code_ordinal:value.code_ordinal,code:value.code,
    original_comparison:comparison,exception_context_observation:value.exception_context_observation===true,actor:'unknown'};
}
function durationNs(start,end){need(typeof start==='string'&&/^[0-9]{1,24}$/.test(start)&&typeof end==='string'&&/^[0-9]{1,24}$/.test(end),'packet');need(BigInt(end)>=BigInt(start)&&BigInt(end)-BigInt(start)<=180000000000n,'packet');}
function validateProof(value,config){
  need(keys(value,PROOF_KEYS),'proof');
  need(value.schema==='si-usb-code-window-observation-v1'&&value.status==='closed_finite_code_windows_external_byte_inspection'
    &&value.runtime_head===config.runtime_head&&value.matching_remote===config.matching_remote&&value.profile_sha256===OLD_PROFILE
    &&value.model_policy_sha256===MODEL_POLICY,'proof');
  need(value.code_mapping_sha256===sha(canonicalJson(Object.fromEntries(CODE_FILES.slice(0,5).map(k=>[k,config.code_manifest[k]])))),'proof');
  for(const key of ['initial_code_file10_sha256','terminal_code_file10_sha256','initial_ancestor_observations_sha256',
    'terminal_ancestor_observations_sha256','physical_root_identity_sha256','source_original10_sha256','inspection_report_sha256','observation_sha256'])need(hex(value[key]),'proof');
  need(value.initial_code_file10_sha256===value.terminal_code_file10_sha256&&value.code_file_original10_equal===true
    &&value.continuous_shared_ancestor_timestamp_custody===false,'proof');
  for(const key of ['all_initial_code_contexts_closed','all_source_contexts_closed','all_terminal_code_contexts_closed','executed_verified_RAM'])need(value[key]===true,'proof');
  need(exact(value.authority,OLD_AUTHORITY),'proof');
  const unsigned={...value};delete unsigned.observation_sha256;need(sha(canonicalJson(unsigned))===value.observation_sha256,'proof');
}
function privateAggregate(value,proof){
  if(value===null)return null;need(dict(value),'private_aggregate');
  const encoded=canonicalJson(value);need(Buffer.byteLength(encoded)<=MAX_PRIVATE,'private_aggregate');
  need(keys(value,['schema','policy_sha256','scope','full','year','manifest_sha256','readme_sha256',
    'selected_manifest_observations_match','paired_member_mismatches','year_is_exact_full_2026_token_multiset_subset','semantic_gaps','authority'])
    &&value.schema==='si-firstrate-supplied-byte-inspection-v1'&&value.scope==='registered_full_and_2026_pair'
    &&value.policy_sha256===MODEL_POLICY,'private_aggregate');
  const authority={inspection_only:true,source_admitted:false,custody_qualified:false,upstream_authentication_verified:false,
    historical_availability_verified:false,point_in_time_data:false,native_identity_admitted:false,share_class_admitted:false,
    same_class_denominator_admitted:false,actual_input_execution_admitted:false,ready_for_backtesting:false,
    outcome_access_authorized:false,qc_authorized:false,trading_authority:false,provider_HTTP:0,credential_reads:0,
    new_claims:0,new_STARTs:0,new_charged_bytes:0,outcome_looks:0,allocated_alpha:0,qc_attempts:0};
  need(exact(value.authority,authority)&&value.selected_manifest_observations_match===true
    &&integer(value.paired_member_mismatches,0,100000)&&typeof value.year_is_exact_full_2026_token_multiset_subset==='boolean'
    &&value.year_is_exact_full_2026_token_multiset_subset===(value.paired_member_mismatches===0)
    &&value.manifest_sha256==='c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8'
    &&value.readme_sha256==='bbcddf477ba3ffacb4b0116e9d3f6c2c2a864576ae748abc8daa825602a16ecf'
    &&exact(value.semantic_gaps,['settlement_is_not_public_availability','revision_vintage_unverified',
      'filename_is_not_native_or_share_class_identity','same_date_own_class_denominator_missing',
      'DTC_volume_basis_and_rounding_contract_unverified','source_custody_and_upstream_authentication_unqualified',
      'processing_rights_and_actual_input_admission_unqualified']),'private_aggregate');
  const reportKeys=['archive_sha256','archive_bytes','member_count','inflated_bytes','rows','structurally_clear_rows',
    'quarantined_rows','empty_members','row_reason_counts','reported_field_observations','earliest_settlement_date',
    'latest_settlement_date','distinct_settlement_dates','member_origin_disposition_commitment_sha256',
    'all_member_tokens_commitment_sha256','year_2026_tokens_commitment_sha256','year_2026_rows','year_2026_members',
    'all_members_CRC_verified','complete_byte_inspection','DTC_recalculated_or_substituted'];
  const reasons=new Set(['row_width','field_length','settlement_date','short_interest_numeric','avg_daily_share_volume_numeric',
    'days_to_cover_numeric','short_interest_nonintegral','duplicate_settlement_all_peers']);
  const observations=new Set(['fractional_average_volume','zero_average_volume','zero_average_volume_positive_SI','zero_average_volume_positive_reported_DTC']);
  for(const [name,length,pin] of [['full',34319601,'08f019c20384bde811b10d1674dc5067cfded4e4c0097fc8c383649c528429c8'],
    ['year',9660009,'3a8a07dec5c91f4e54cda396d9b1483895769d6ecac1a8d1a15a64e873fa191a']]){
    const report=value[name];need(keys(report,reportKeys)&&report.archive_sha256===pin&&report.archive_bytes===length,'private_aggregate');
    for(const key of ['member_count','inflated_bytes','rows','structurally_clear_rows','quarantined_rows','empty_members','distinct_settlement_dates','year_2026_rows','year_2026_members'])need(integer(report[key],0,134217728),'private_aggregate');
    need(report.member_count>=1&&report.member_count<=50000&&report.rows<=3000000&&report.structurally_clear_rows+report.quarantined_rows===report.rows
      &&report.empty_members<=report.member_count&&report.year_2026_members<=report.member_count&&report.year_2026_rows<=report.rows
      &&report.all_members_CRC_verified===true&&report.complete_byte_inspection===true&&report.DTC_recalculated_or_substituted===false,'private_aggregate');
    for(const key of ['member_origin_disposition_commitment_sha256','all_member_tokens_commitment_sha256','year_2026_tokens_commitment_sha256'])need(hex(report[key]),'private_aggregate');
    for(const [key,allowed] of [['row_reason_counts',reasons],['reported_field_observations',observations]])need(dict(report[key])
      &&Object.keys(report[key]).every(k=>allowed.has(k)&&integer(report[key][k],0,report.rows)),'private_aggregate');
    const dates=[report.earliest_settlement_date,report.latest_settlement_date];
    need(dates.every(d=>d===null||typeof d==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(d))
      &&(dates[0]===null)===(dates[1]===null)&&(dates[0]===null||dates[0]<=dates[1])
      &&(dates[0]===null?report.distinct_settlement_dates===0:report.distinct_settlement_dates>=1)
      &&report.distinct_settlement_dates<=report.rows,'private_aggregate');
  }
  need(value.paired_member_mismatches<=value.full.member_count+value.year.member_count,'private_aggregate');
  const hash=sha(encoded);need(proof!==null&&hash===proof.inspection_report_sha256,'private_aggregate');
  return {sha256:hash,bytes:Buffer.byteLength(encoded)};
}
function validatePacket(raw,config){
  need(Buffer.isBuffer(raw)&&raw.length>0&&raw.length<=MAX_STDOUT,'packet');
  let value;try{value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));}catch{need(false,'packet');}
  need(canonicalJson(value)+'\n'===raw.toString('utf8'),'packet');
  if(value.schema==='si-usb-once-bootstrap-refusal-v1'){
    need(keys(value,['schema','invocation_id','status','source_qualified','first_failure','cleanup_failures'])
      &&value.invocation_id===INVOCATION&&value.status==='incomplete'&&value.source_qualified===false
      &&Array.isArray(value.cleanup_failures)&&value.cleanup_failures.length<=32,'packet');
    return {producerStatus:'incomplete',first:fact(value.first_failure),later:value.cleanup_failures.map(fact),privateInfo:null};
  }
  need(keys(value,ENVELOPE_KEYS)&&value.schema==='si-usb-once-envelope-v1'&&value.invocation_id===INVOCATION,'packet');
  need(['closed_finite_offline_byte_inspection','incomplete'].includes(value.status)
    &&value.runtime_head===config.runtime_head&&value.matching_remote===config.matching_remote
    &&value.driver_sha256===config.code_manifest[DRIVER]&&exact(value.interpreter_version,[3,13,15])
    &&value.maximum_whole_seconds===180&&value.source_qualified===false,'lineage');
  const expectedManifest=sha(canonicalJson(config.code_manifest));
  need(value.code_manifest_sha256===expectedManifest||value.status==='incomplete'&&value.code_manifest_sha256===null,'lineage');
  need(exact(value.authority,AUTHORITY)&&value.external_OS_sandbox_and_independent_owned_wait_required===true
    &&value.python_audit_covers_all_metadata===false&&value.extra_code_continuous_ancestor_timestamp_custody===false
    &&value.git_scope==='original_matching_lane_metadata_environment_ambient_credential_behavior_not_proven','packet');
  need(keys(value.denials,['python_write_attempts','python_socket_attempts','forbidden_read_open_attempts','unexpected_subprocess_attempts'])
    &&Object.values(value.denials).every(v=>integer(v,0,4096))&&Array.isArray(value.cleanup_failures)&&value.cleanup_failures.length<=32,'packet');
  const first=fact(value.first_failure),later=value.cleanup_failures.map(fact);
  if(value.whole_start_monotonic_ns!==null)durationNs(value.whole_start_monotonic_ns,value.whole_end_monotonic_ns);
  if(value.original_profile_proof!==null)validateProof(value.original_profile_proof,config);
  const privateInfo=privateAggregate(value.private_model_aggregate,value.original_profile_proof);
  if(value.status==='closed_finite_offline_byte_inspection')need(value.whole_start_monotonic_ns!==null&&first===null&&later.length===0
    &&Object.values(value.denials).every(v=>v===0)&&value.original_profile_proof!==null&&privateInfo!==null,'proof');
  return {producerStatus:value.status,first,later,privateInfo};
}

function hostSeams(){
  const now=performance.now,hr=process.hrtime.bigint,set=globalThis.setTimeout,clear=globalThis.clearTimeout;
  return {now:()=>now.call(performance),hrtime:()=>hr.call(process.hrtime),setTimeout:set,clearTimeout:clear,
    identity:()=>performance.now===now&&process.hrtime.bigint===hr&&globalThis.setTimeout===set&&globalThis.clearTimeout===clear,
    spawn:nodeSpawn,signal:(pid,sig)=>process.kill(pid,sig),host:validateHost,deadlineMs:MAXIMUM_MS};
}
async function run(encoded,seams,test){
  const begin=seams.now(),beginHr=seams.hrtime();let last=begin,lastHr=beginHr;
  let config=null,self=null,host=null,child=null,pid=null,exit=null,signal=null,exitSeen=false,closeSeen=false;
  let stdoutEOF=false,stderrEOF=false,stdoutBytes=0,stderrBytes=0,retained=0,complete=true,producer=null;
  let chunks=[],first=null,later=[],timedOut=false,done=false,finalElapsed=null;const timers=[];
  const maximum=seams.deadlineMs;
  const fail=code=>{const fixed=OWN_CODES.has(code)?code:'packet';if(first===null)first=fixed;else if(later.length<16)later.push(fixed);};
  const check=()=>{
    need(seams.identity(),'clock');const now=seams.now(),hr=seams.hrtime();
    need(Number.isFinite(now)&&typeof hr==='bigint'&&Number.isFinite(begin)&&typeof beginHr==='bigint'
      &&now>=last&&hr>=lastHr&&now>=begin&&hr>=beginHr,'clock');last=now;lastHr=hr;
    need(now-begin<=maximum&&hr-beginHr<=BigInt(Math.round(maximum*1e6)),'deadline');return now-begin;
  };
  const safeCode=error=>dict(error)&&typeof error.fixedCode==='string'&&OWN_CODES.has(error.fixedCode)?error.fixedCode:'packet';
  let resolve;const ended=new Promise(r=>{resolve=r;});
  const signalOwned=sig=>{
    if(child===null||exitSeen||closeSeen)return;
    if(child.pid!==pid||!integer(pid,1)||child.exitCode!==null||child.signalCode!==null){fail('signal');return;}
    try{seams.signal(-pid,sig);}catch{fail('signal');try{child.kill(sig);}catch{fail('cleanup');}}
  };
  const stop=()=>{signalOwned('SIGTERM');};
  const finish=(force=false)=>{
    if(done)return;
    if(child!==null&&!closeSeen&&!force){stop();return;}
    done=true;
    for(const id of timers)try{seams.clearTimeout(id);}catch{fail('cleanup');}
    try{
      check();if(host!==null)seams.host(host);check();
      if(!exitSeen||!closeSeen)fail('close');if(!stdoutEOF||!stderrEOF)fail('EOF');
      if(exit!==0||signal!==null)fail('exit');if(stderrBytes!==0)fail('stderr');
      if(complete&&stdoutEOF){try{producer=validatePacket(Buffer.concat(chunks),config);}catch(error){fail(safeCode(error));}}
      else fail('packet');
      if(producer!==null&&producer.producerStatus!=='closed_finite_offline_byte_inspection')fail('proof');
      finalElapsed=check();
    }catch(error){fail(safeCode(error));}
    resolve();
  };
  const schedule=(fn,delay)=>{const id=seams.setTimeout(fn,Math.max(0,delay));timers.push(id);};
  try{
    check();config=configuration(encoded);self=sourceIdentity();host=seams.host();check();
    schedule(()=>{timedOut=true;fail('deadline');stop();},Math.max(1,maximum-SHUTDOWN_RESERVE_MS-(seams.now()-begin)));
    schedule(()=>{timedOut=true;fail('deadline');signalOwned('SIGKILL');},Math.max(1,maximum-KILL_RESERVE_MS-(seams.now()-begin)));
    schedule(()=>{timedOut=true;fail('deadline');signalOwned('SIGKILL');
      for(const stream of child===null?[]:[child.stdout,child.stderr])try{stream.destroy();}catch{fail('cleanup');}
      finish(true);},maximum-(seams.now()-begin));
    check();
    const args=['-p',SANDBOX,PYTHON,'-I','-S','-B','-c',BOOTSTRAP,config.runtime_head,config.matching_remote,canonicalJson(config.code_manifest)];
    child=seams.spawn('/usr/bin/sandbox-exec',args,{cwd:ROOT,env:{...ENV},stdio:['ignore','pipe','pipe'],shell:false,detached:true});
    pid=child.pid;
    child.once('close',(code,sig)=>{closeSeen=true;
      if(!exitSeen||code!==exit||sig!==signal)fail('close');finish();});
    child.once('exit',(code,sig)=>{
      exitSeen=true;exit=integer(code,-2147483648,2147483647)?code:null;
      signal=['SIGTERM','SIGKILL','SIGABRT','SIGSEGV','SIGBUS','SIGINT'].includes(sig)?sig:null;
      if(code!==0||sig!==null)fail('exit');
    });
    child.once('error',()=>{fail('spawn');stop();});
    need(integer(pid,1)&&child.stdout&&child.stderr,'spawn');
    child.stdout.on('data',chunk=>{
      try{
        check();need(Buffer.isBuffer(chunk),'stdout_type');stdoutBytes+=chunk.length;
        const room=Math.max(0,MAX_STDOUT-retained),copy=Buffer.from(chunk.subarray(0,room));
        if(copy.length){chunks.push(copy);retained+=copy.length;}
        if(stdoutBytes>MAX_STDOUT){complete=false;fail('stdout_limit');stop();}
        check();
      }catch(error){complete=false;fail(safeCode(error));stop();}
    });
    child.stderr.on('data',chunk=>{
      try{check();need(Buffer.isBuffer(chunk),'stream');stderrBytes+=chunk.length;fail(stderrBytes>MAX_STDERR?'stderr_limit':'stderr');stop();check();}
      catch(error){fail(safeCode(error));stop();}
    });
    child.stdout.once('end',()=>{stdoutEOF=true;});child.stderr.once('end',()=>{stderrEOF=true;});
    for(const stream of [child.stdout,child.stderr])stream.once('error',()=>{fail('stream');stop();});
    check();
  }catch(error){fail(safeCode(error));stop();finish();}
  await ended;
  const raw=Buffer.concat(chunks);chunks=[];
  const summary=()=>{
    try{check();}catch(error){fail(safeCode(error));}
    const value={schema:'si-usb-once-owned-observation-v1',status:first===null?'closed_finite_offline_byte_observation':'incomplete',
      invocation_id:config===null?INVOCATION:config.invocation_id,runtime_head:config?.runtime_head??null,
      matching_remote:config?.matching_remote??null,observer_source_sha256:self,
      producer_code_manifest_sha256:config===null?null:sha(canonicalJson(config.code_manifest)),
      actual_exit_code:exit,actual_signal:signal,exit_observed:exitSeen,close_observed:closeSeen,
      stdout_EOF:stdoutEOF,stderr_EOF:stderrEOF,stdout_bytes_observed:stdoutBytes,stdout_bytes_retained:raw.length,
      retained_stdout_sha256:sha(raw),original_stdout_sha256:complete&&stdoutEOF&&retained===stdoutBytes?sha(raw):null,
      original_stdout_complete:complete&&stdoutEOF&&retained===stdoutBytes,stderr_bytes_discarded:stderrBytes,
      original_child_pid:pid,automatic_deadline_shutdown:timedOut,owner_action_required:child!==null&&(!exitSeen||!closeSeen||!stdoutEOF||!stderrEOF),
      maximum_whole_ms:maximum,original_close_validation_elapsed_ms:finalElapsed===null?null:Math.round(finalElapsed),
      first_failure:first,cleanup_failures:[...later],producer_status:producer?.producerStatus??null,
      producer_first_failure:producer?.first??null,producer_cleanup_failures:producer?.later??[],
      private_model_aggregate_present:producer?.privateInfo!==null&&producer?.privateInfo!==undefined,
      private_model_aggregate_sha256:producer?.privateInfo?.sha256??null,private_model_aggregate_bytes:producer?.privateInfo?.bytes??null,
      source_qualified:false,source_admitted:false,ready_for_backtest:false,test_seams_used:test,
      scope:'finite_original_external_byte_observation_not_model_fitness_source_qualification_or_input_admission'};
    const encodedSummary=canonicalJson(value);
    try{check();}catch(error){fail(safeCode(error));return canonicalJson({...value,status:'incomplete',first_failure:first,cleanup_failures:[...later]});}
    return encodedSummary;
  };
  const privateStdoutBytes=()=>{
    try{check();need(complete&&stdoutEOF&&stderrEOF&&closeSeen&&retained===stdoutBytes,'EOF');const copy=Buffer.from(raw);check();return copy;}
    catch(error){fail(safeCode(error));throw Object.freeze({fixedCode:safeCode(error)});}
  };
  return Object.freeze({summaryJson:summary,summary:()=>JSON.parse(summary()),privateStdoutBytes});
}

export async function observeOnce(configJson){
  if(actualUsed)throw Object.freeze({fixedCode:'attempt_spent'});actualUsed=true;
  return run(configJson,hostSeams(),false);
}
export async function observeOnceForTests(configJson,seams){
  need(dict(seams)&&['now','hrtime','setTimeout','clearTimeout','identity','spawn','signal','host'].every(k=>typeof seams[k]==='function'),'configuration');
  need(typeof seams.deadlineMs==='number'&&Number.isFinite(seams.deadlineMs)&&seams.deadlineMs>0&&seams.deadlineMs<=MAXIMUM_MS,'configuration');
  return run(configJson,seams,true);
}
export const profile=Object.freeze({root:ROOT,python:PYTHON,python_sha256:PYTHON_SHA,invocation_id:INVOCATION,
  code_files:CODE_FILES,maximum_whole_ms:MAXIMUM_MS,maximum_stdout_bytes:MAX_STDOUT,
  sandbox:SANDBOX,directory_scope:'literal_ancestor_directory_open_read_permission_not_metadata_only_no_extra_volume_files',
  network_scope:'Python_provider_denials_matching_lane_Git_metadata_exception_not_universal_native_packet_or_credential_zero_claim',
  source_qualified:false,ready_for_backtest:false});
