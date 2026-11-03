"""One new typed historical-symbol FirstRate coverage observation.

Only unobserved exact symbol members are read; earlier E symbols are globally
excluded. Original raw bytes are retained privately after all normal source
returns. Presence, typed role and coverage never admit identity or prices.
"""
import argparse
import csv
import zipfile
from contextlib import ExitStack
from datetime import date
from decimal import Decimal,InvalidOperation
import hashlib
import importlib
from importlib.machinery import PathFinder
import io
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE=ROOT/'scripts/inspect_arv2_r336_historical_symbol_coverage.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/firstrate/R336-20261103-O'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
USB=Path('/Volumes/SANDISK/firstrate')
STOCK_DIR='market/Stocks_Complete_10_000+_Tickers/'
CURRENT_ARCHIVES=tuple(STOCK_DIR+f'Tickers_{letter}_Day_Unadjusted_Full_Dataset.zip' for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
DELISTED_ARCHIVES=tuple(STOCK_DIR+f'1-Day_Unadjusted_Archive_{n}.zip' for n in range(1,6))+(STOCK_DIR+'1-Day_Unadjusted_2025+_Delisted_tickers.txt',)
ARCHIVES=(*CURRENT_ARCHIVES,*DELISTED_ARCHIVES)
USB_PINS={'manifest.json':{'byte_count':327907,'sha256':'c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8'},
 STOCK_DIR+'Ticker_Listing.txt':{'byte_count':889580,'sha256':'584718095d81d576af0f83d6f31d5cda565e59ea2c6677e5b164e0db39e93464'}}
MAX_ZIP_BYTES,MAX_MEMBERS,MAX_MEMBER_BYTES=64*1024*1024,20000,4*1024*1024
MAX_RAW_FILES,MAX_RAW_BYTES=128,32*1024*1024
SCHEMA='arv2-r336-historical-symbol-coverage-observation-v1'
DATA_PLAN={'semantics': {'relative_path': 'artifacts/analyst_revisions_v2/identity_recovery/R336-20261103-N/private-diagnosis.json', 'byte_count': 294888, 'sha256': 'fd52e0d4177bf5c6b74dd0f1b6e8616ca03a9c8fb60ae5d9c57f584f075de86e'}}
SOURCE_PINS={'scripts/arv2_relocation_security.py': '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30', 'scripts/arv2_r298_fixed_data_guard.py': '00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145', 'scripts/arv2_r336_original_identity_ownership.py': 'e0e829c662c5dbc7c1a1e95f720db0e87e0725f3f3d428b3b785d991b55bef5b', 'scripts/arv2_r336_action_semantics.py': 'd95bfb69b9383306bbee8c83ac34d8c22fb8e9ed9cd33500c886742b8c652bbe', 'scripts/arv2_r336_historical_symbol_coverage.py': '17cce8bed6cc084d7e9fa420e15f6f02158c6a24804117eb0e6314f002d42be5'}
SECONDS,MAX_OUTPUT,MAX_PRIVATE=300,1024*1024,8*1024*1024
WORKER_SECONDS=240
PURE_PROFILE_PIN={'byte_count':4134,'sha256':'7de294d58b8a72cec796ea08343ec4e7b76bd3ec12203414b47cbffaa33b883a'}
CHILD_OBSERVATION=None
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
FAILURE_STAGE,FAILURE_CASE='preflight',None
STAGES=frozenset(('preflight','retained_DATA','USB_manifest','USB_listing','USB_archive','member_coverage','output'))
GUARD_MODULE=PURE_MODULE=None
GUARD_CODES=frozenset(('byte_pin', 'close', 'deadline', 'metadata', 'named_changed', 'path_open', 'plan', 'read_spent', 'receipt', 'scope', 'security', 'security_changed', 'shape', 'state'))
PURE_CODES=frozenset(('input_pin', 'input', 'case_binding', 'demand', 'pair_binding', 'event_binding', 'lead_bound', 'token_bound', 'output', 'deadline', 'bytes', 'pin', 'member', 'encoding', 'line_ending', 'row_bound', 'row_shape', 'session', 'timestamp', 'date_order', 'number', 'price', 'OHLC', 'volume', 'series', 'calendar', 'reference_scope', 'unknown'))

FALSE_FLAGS={'provider_contact': False, 'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False, 'generic_prose_disclosed': False, 'instrument_rows_disclosed': False, 'security_identifiers_disclosed': False, 'aliases_admitted': False, 'identity_admitted': False, 'permanent_security_continuity_proven': False, 'terminal_payoff_applied': False, 'price_input_admitted': False, 'price_coverage_proven': False, 'source_assignment_changed': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'full_original_catalog_freshly_reauthenticated': False, 'full_current_catalog_freshly_authenticated': False, 'strategy_action_invoked': False}
FALSE_FLAGS.pop('USB_read')
FALSE_FLAGS.update({key:False for key in ('old_E_symbol_member_reread','volume_rounded_or_normalized','adjusted_prices_used',
    'cross_archive_continuous_integrity_proven','new_archive_SHA_is_independent_vendor_authentication','whole_binding_source_admitted')})
FINITE=frozenset(('arguments','bound','changed','child_failure','child_stderr','claim_spent','control','deadline','environment','git_state','host','input','output','path','scope','shape','source_changed','source_pin','unknown','listing','manifest','archive','member','known_pin','plan'))|frozenset('guard_'+v for v in GUARD_CODES)|frozenset('pure_'+v for v in PURE_CODES)


class Refused(ValueError):
    """Closed local predicate; never retain private source text in errors."""

def require(value, code):
    if not value:
        raise Refused(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}

def finite(error):
    for module,prefix,codes in ((GUARD_MODULE,'guard_',GUARD_CODES),(PURE_MODULE,'pure_',PURE_CODES)):
        if module is not None and type(error) is module.Refused:
            value=module.finite(error);return prefix+value if value in codes else 'unknown'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args)==1 and type(args[0]) is str and args[0] in FINITE:return args[0]
    return 'deadline' if isinstance(error,TimeoutError) else 'unknown'


def failure_packet(code):
    require(type(code) is str and code in FINITE, 'output')
    return {'schema': SCHEMA, 'binding': ACTIVE_BINDING, 'failure_code': code,
        'stage': FAILURE_STAGE, 'case_ordinal': FAILURE_CASE,
        'attempt_reusable': False, 'claim_state': CLAIM_STATE,'child_observation':CHILD_OBSERVATION, **FALSE_FLAGS}

def validate_failure(value, args):
    require(type(value) is dict and set(value) == {'schema', 'binding', 'failure_code',
        'stage', 'case_ordinal', 'attempt_reusable', 'claim_state','child_observation', *FALSE_FLAGS}
        and value['schema'] == SCHEMA
        and value['binding'] == binding(args) and type(value['failure_code']) is str
        and value['failure_code'] in FINITE and value['attempt_reusable'] is False
        and value['claim_state'] in ('unallocated', 'allocated_unknown', 'consumed', 'consumed_or_unknown')
        and value['stage'] in STAGES and (value['case_ordinal'] is None or
            type(value['case_ordinal']) is int and 0 <= value['case_ordinal'] < 5)
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    if value['child_observation'] is not None:validate_observation(value['child_observation'])
    return value


def validate_observation(value):
    require(type(value) is dict and set(value)=={'actual_child_exit','child_stdout_pin','child_stderr_byte_count','child_stderr_sha256','failure_code'}
        and (value['actual_child_exit'] is None or type(value['actual_child_exit']) is int)
        and type(value['child_stderr_byte_count']) is int and 0<=value['child_stderr_byte_count']<=16384
        and type(value['child_stderr_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['child_stderr_sha256'])
        and (value['failure_code'] is None or type(value['failure_code']) is str and value['failure_code'] in FINITE),'output')
    item=value['child_stdout_pin'];require(type(item) is dict and set(item)=={'byte_count','sha256'}
        and type(item['byte_count']) is int and 0<=item['byte_count']<=MAX_OUTPUT
        and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']),'output')
    return value

def parse(raw, bound):
    require(type(raw) is bytes and 0 < len(raw) <= bound, 'bound')
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'input'); result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf8'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('input')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('input') from None

def budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= SECONDS, 'deadline')
    return deadline - time.monotonic()

def meta(info):
    result = tuple(getattr(info, key, None) for key in FIELDS)
    require(all(type(value) is int and value >= 0 for value in result), 'metadata')
    return result

class HeldFile:
    """Original nofollow leaf/ancestor descriptors; current equality only.

    USB ExFAT metadata is a separate readonly transport scope. It makes no
    native ACL/xattr or historical continuity claim about the external disk.
    """
    def __init__(self, path, *, maximum, expected=None, deadline):
        self.path, self.maximum, self.expected, self.deadline = Path(path), maximum, expected, deadline
        self.directories, self.fd, self.info = [], None, None

    def __enter__(self):
        require(self.path.is_absolute() and '..' not in self.path.parts, 'path')
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.directories.append((parent, parent, '.', meta(os.fstat(parent))))
            for part in self.path.parts[1:-1]:
                budget(self.deadline)
                before = meta(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.directories.append((fd, parent, part, before))
                require(stat.S_ISDIR(before[2]) and meta(os.fstat(fd)) == before, 'changed'); parent = fd
            before = meta(os.stat(self.path.name, dir_fd=parent, follow_symlinks=False))
            self.fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            require(stat.S_ISREG(before[2]) and before[5] == 1 and 0 < before[6] <= self.maximum
                and meta(os.fstat(self.fd)) == before, 'shape')
            self.info = before; self.verify(); return self
        except BaseException:
            self.close(); raise

    def verify(self):
        budget(self.deadline)
        for fd, parent, name, before in self.directories:
            require(meta(os.fstat(fd)) == before == meta(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'changed')
        require(self.fd is not None and meta(os.fstat(self.fd)) == self.info
            == meta(os.stat(self.path.name, dir_fd=self.directories[-1][0], follow_symlinks=False)), 'changed')

    def read(self):
        self.verify(); chunks, count = [], 0
        while count <= self.info[6]:
            budget(self.deadline)
            raw = os.pread(self.fd, min(65536, self.info[6] + 1 - count), count)
            if not raw: break
            chunks.append(raw); count += len(raw)
        raw = b''.join(chunks)
        require(len(raw) == self.info[6] and (self.expected is None or pin(raw) == self.expected), 'source_pin')
        self.verify(); return raw

    def close(self):
        if self.fd is not None: os.close(self.fd); self.fd = None
        for fd, _, _, _ in reversed(self.directories): os.close(fd)
        self.directories.clear()

    def __exit__(self, kind, *_):
        try:
            if kind is None: self.verify()
        finally: self.close()

def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':BRANCH,'python':PYTHON,'control':str(CONTROL),
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'USB_pins':USB_PINS,'pure_profile_pin':PURE_PROFILE_PIN,
        'purpose':'new_typed_historical_symbol_member_and_date_coverage_not_E_replay_or_identity_price_admission',
        'maximum_seconds':SECONDS,'maximum_worker_seconds':WORKER_SECONDS,'validator_seconds':30,'own_reap_seconds':5,
        'maximum_output_bytes':MAX_OUTPUT,'maximum_private_index_bytes':MAX_PRIVATE,'maximum_archives':32,
        'maximum_transport_tokens':64,'maximum_typed_leads':128,'maximum_raw_files':MAX_RAW_FILES,
        'maximum_raw_member_bytes':MAX_MEMBER_BYTES,'maximum_raw_aggregate_bytes':MAX_RAW_BYTES,
        'raw_output_names':'member-0000.bin_through_member-0127.bin_sequential_exclusive_0600_exact_original_bytes',
        'native_USB_allowlist':'fixed_maximum26current_letter_and6delisted_archives_exact_manifest_listing_no_census_actual_reads_plan_selected',
        'known_source_pins':'all_revisited_N_nested_F_container_and_member_SHA_pins_mandatory_never_refreshed',
        'new_container_authentication':'externally_pinned_manifest_size_MD5_and_new_retained_SHA_without_E_pin_not_independent_vendor_cryptographic_provenance',
        'exclusions':'GLOBAL_all5_E_diagnostic_current_ticker_and_DELISTED_no_old_named_member_lookup_decompression_or_parse',
        'compressed_container_scope':'whole_archive_hashing_reads_compressed_bytes_including_old_and_unselected_members',
        'transport':'each_selected_archive_once_each_exact_physical_member_once_all_case_and_role_links_retained',
        'scope':'literal_symbol_and_single_standard_DELISTED_suffix_no_normalization_no_guessed_digit_archive',
        'normal_return':'N_manifest_listing_held_overall_each_archive_held_during_all_its_assessments_all_guards_return_before_any_output',
        'source_execution':'compiled_exact_held_selected_repo_bytes_no_repo_pyc_not_whole_interpreter_integrity',
        'native_worker_policy_sha256':sha(native_profile().encode('utf8')),
        'public':'counts_case_ordinals_and_source_pins_only_no_symbols_prices_or_URLs',
        'deadline_limitation':'uninterruptible_IO_host_suspension_startup_own5s_reap_and_scoped_endpoint_not_cross_archive_continuity',**FALSE_FLAGS}


def raw_name(value):
    return type(value) is str and re.fullmatch(r'member-[0-9]{4}[.]bin',value) is not None and int(value[7:11])<MAX_RAW_FILES


def checked_pin(value,maximum):
    require(type(value) is dict and set(value)=={'byte_count','sha256'} and type(value['byte_count']) is int
        and 0<value['byte_count']<=maximum and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']),'known_pin')
    return value


def known_sources(plan):
    archives={};members={};excluded=set()
    require(type(plan) is dict and type(plan.get('cases')) is list and len(plan['cases'])==5,'plan')
    for ordinal,case in enumerate(plan['cases']):
        require(type(case) is dict and type(case.get('case_ordinal')) is int and case['case_ordinal']==ordinal
            and type(case.get('previously_E_searched_symbols')) is list and type(case.get('prior_E_candidates')) is list,'plan')
        for symbol in case['previously_E_searched_symbols']:
            require(type(symbol) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,72}',symbol) is not None and '..' not in symbol,'plan');excluded.add(symbol)
        for previous in case['prior_E_candidates']:
            relative=previous['archive'];name=previous['member_name'];container=checked_pin(previous['container_pin'],MAX_ZIP_BYTES)
            member=checked_pin(previous['member_pin'],MAX_MEMBER_BYTES)
            require(relative in ARCHIVES and type(name) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,72}_full_1day_UNADJUSTED[.]txt',name)
                and (relative not in archives or archives[relative]==container)
                and ((relative,name) not in members or members[(relative,name)]==member),'known_pin')
            archives[relative]=dict(container);members[(relative,name)]=dict(member)
    return archives,members,excluded


def schedule(plan,excluded):
    require(type(plan.get('transport_tokens')) is list and len(plan['transport_tokens'])<=64
        and plan['transport_tokens']==sorted(set(plan['transport_tokens'])) and type(plan.get('transport_specs')) is list
        and len(plan['transport_specs'])==len(plan['transport_tokens']),'plan')
    result={}
    for token,spec in zip(plan['transport_tokens'],plan['transport_specs'],strict=True):
        require(type(token) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,63}',token) is not None and '..' not in token
            and type(spec) is dict and set(spec)=={'token','current_letter','member_aliases','lead_links'} and spec['token']==token
            and spec['current_letter']==(token[0] if token[0] in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' else None)
            and type(spec['member_aliases']) is list and type(spec['lead_links']) is list and spec['lead_links'],'plan')
        intended=[token] if token.endswith('-DELISTED') else [token,token+'-DELISTED']
        aliases=[alias for alias in intended if alias not in excluded]
        require(spec['member_aliases']==aliases and token not in excluded,'plan')
        relatives=(*(() if spec['current_letter'] is None else (STOCK_DIR+f"Tickers_{spec['current_letter']}_Day_Unadjusted_Full_Dataset.zip",)),*DELISTED_ARCHIVES)
        for relative in relatives:
            require(relative in ARCHIVES,'scope')
            for alias in aliases:
                name=alias+'_full_1day_UNADJUSTED.txt';target=result.setdefault(relative,{}).setdefault(name,{'alias':alias,'tokens':[],'lead_links':[]})
                if token not in target['tokens']:target['tokens'].append(token)
                for link in spec['lead_links']:
                    require(type(link) is dict and set(link)=={'case_ordinal','lead_ordinal'}
                        and type(link['case_ordinal']) is type(link['lead_ordinal']) is int
                        and 0<=link['case_ordinal']<5 and 0<=link['lead_ordinal']<128,'plan')
                    lead=plan['lead_records'][link['lead_ordinal']]
                    require(lead['lead_ordinal']==link['lead_ordinal'] and lead['case_ordinal']==link['case_ordinal']
                        and lead['raw_symbol']==token and lead['supported'] is lead['eligible'] is True
                        and lead['excluded_E'] is lead['unresolved_pair'] is False,'plan')
                    if link not in target['lead_links']:target['lead_links'].append(dict(link))
    require(len(result)<=32,'bound');return result


def study(plan_public,plan,manifest,listing_rows,pure,deadline):
    """Each physical member read once; all role/case uses keep the same raw pin."""
    global FAILURE_STAGE,FAILURE_CASE
    archive_pins,member_pins,excluded=known_sources(plan);jobs=schedule(plan,excluded)
    raw_packets=[];physical=[];private_members=[];case_hits=[[] for _ in range(5)];probes=missing=0;archive_observations=[]
    for relative,members in sorted(jobs.items()):
        budget(deadline);FAILURE_STAGE='USB_archive';FAILURE_CASE=None
        with HeldFile(USB/relative,maximum=MAX_ZIP_BYTES,deadline=deadline) as held:
            with Archive(held,manifest_entry(manifest,relative),known_pin=archive_pins.get(relative)) as archive:
                archive_observations.append({'archive':relative,'container_pin':dict(archive.container_pin),
                    'retained_E_SHA_matched':relative in archive_pins,'new_retained_SHA_without_E_pin':relative not in archive_pins})
                for name,job in sorted(members.items()):
                    FAILURE_STAGE='member_coverage';FAILURE_CASE=None
                    require(job['alias'] not in excluded,'plan');probes+=1
                    raw=archive.member(name)
                    if raw is None:missing+=1;continue
                    require(len(raw_packets)<MAX_RAW_FILES and sum(map(len,raw_packets))+len(raw)<=MAX_RAW_BYTES,'bound')
                    raw_pin=pin(raw);known_member=member_pins.get((relative,name))
                    require(known_member is None or raw_pin==known_member,'known_pin')
                    ordinal=len(raw_packets);raw_packets.append(raw)
                    physical.append({'physical_hit_ordinal':ordinal,'member_pin':raw_pin,'container_pin':dict(archive.container_pin),
                        'known_E_container_SHA_matched':relative in archive_pins,'known_E_member_SHA_matched':known_member is not None})
                    private={'physical_hit_ordinal':ordinal,'archive':relative,'member_name':name,'literal_alias':job['alias'],
                        'transport_tokens':job['tokens'],'lead_links':job['lead_links'],'raw_output_leaf':f'member-{ordinal:04d}.bin',
                        'raw_output_pin':raw_pin,'container_pin':dict(archive.container_pin),'known_E_member_SHA_pin':known_member,
                        'listing_matches':[dict(row) for row in listing_rows if row['Ticker']==job['alias']],
                        'parser_metadata':None,'case_assessments':[]}
                    for case_ordinal in sorted({link['case_ordinal'] for link in job['lead_links']}):
                        FAILURE_CASE=case_ordinal
                        case=plan['cases'][case_ordinal];links=[link for link in job['lead_links'] if link['case_ordinal']==case_ordinal]
                        coverage,opaque=pure.assess_member(raw,expected_pin=raw_pin,member_name=name,expected_ticker=job['alias'],
                            required_sessions=case['required_sessions'],reference_sessions=case['reference_sessions'])
                        pure.validate_coverage(coverage);detail=pure.private_member_index(opaque)
                        require(pure.private_original_bytes(opaque['opaque_series'])==raw and detail['member_pin']==raw_pin,'member')
                        if private['parser_metadata'] is None:
                            private['parser_metadata']={key:detail[key] for key in ('member_pin','row_count','row_offsets')}
                        else:require(private['parser_metadata']=={key:detail[key] for key in ('member_pin','row_count','row_offsets')},'member')
                        role_counts={}
                        for link in links:
                            lead=plan['lead_records'][link['lead_ordinal']];key=(lead['family'],lead['symbol_role'])
                            role_counts[key]=role_counts.get(key,0)+1
                        typed=[{'family':family,'symbol_role':role,'lead_count':count} for (family,role),count in sorted(role_counts.items())]
                        case_hits[case_ordinal].append({'physical_hit_ordinal':ordinal,'coverage':coverage,'typed_role_link_counts':typed})
                        private['case_assessments'].append({'case_ordinal':case_ordinal,'lead_links':links,'coverage':coverage,
                            'missing_required_sessions':detail['missing_required_sessions'],'missing_reference_sessions':detail['missing_reference_sessions']})
                    private_members.append(private)
    FAILURE_CASE=None
    summary={'schema':SCHEMA+'-summary','plan':plan_public,'archive_count':len(archive_observations),
        'known_E_container_SHA_count':sum(row['retained_E_SHA_matched'] for row in archive_observations),
        'new_retained_SHA_without_E_pin_count':sum(row['new_retained_SHA_without_E_pin'] for row in archive_observations),
        'physical_member_count':len(raw_packets),'raw_member_bytes':sum(map(len,raw_packets)),
        'member_probe_count':probes,'missing_member_probe_count':missing,'physical_members':physical,
        'cases':[{'case_ordinal':ordinal,'candidate_count':len(hits),'candidates':hits} for ordinal,hits in enumerate(case_hits)],**FALSE_FLAGS}
    validate_summary(summary,pure)
    private={'schema':SCHEMA+'-private','input_N_pin':dict(DATA_PLAN['semantics']),'USB_pins':USB_PINS,
        'plan':plan,'archive_observations':archive_observations,'physical_members':private_members,'inspection':summary,**FALSE_FLAGS}
    require(len(canonical(private))<=MAX_PRIVATE,'bound');return summary,private,raw_packets


def validate_summary(value,pure):
    require(type(value) is dict and set(value)=={'schema','plan','archive_count','known_E_container_SHA_count',
        'new_retained_SHA_without_E_pin_count','physical_member_count','raw_member_bytes','member_probe_count',
        'missing_member_probe_count','physical_members','cases',*FALSE_FLAGS}
        and value['schema']==SCHEMA+'-summary' and all(value[key] is False for key in FALSE_FLAGS),'output')
    pure.validate_plan_summary(value['plan'])
    for name in ('archive_count','known_E_container_SHA_count','new_retained_SHA_without_E_pin_count',
            'physical_member_count','raw_member_bytes','member_probe_count','missing_member_probe_count'):
        require(type(value[name]) is int and value[name]>=0,'output')
    n=value['physical_member_count'];require(n<=MAX_RAW_FILES and value['archive_count']<=32
        and value['known_E_container_SHA_count']+value['new_retained_SHA_without_E_pin_count']==value['archive_count']
        and value['raw_member_bytes']<=MAX_RAW_BYTES and value['member_probe_count']<=64*2*7
        and value['member_probe_count']==n+value['missing_member_probe_count']
        and type(value['physical_members']) is list and len(value['physical_members'])==n
        and type(value['cases']) is list and len(value['cases'])==5,'output')
    for ordinal,row in enumerate(value['physical_members']):
        require(type(row) is dict and set(row)=={'physical_hit_ordinal','member_pin','container_pin','known_E_container_SHA_matched','known_E_member_SHA_matched'}
            and type(row['physical_hit_ordinal']) is int and row['physical_hit_ordinal']==ordinal
            and type(row['known_E_container_SHA_matched']) is type(row['known_E_member_SHA_matched']) is bool,'output')
        checked_pin(row['member_pin'],MAX_MEMBER_BYTES);checked_pin(row['container_pin'],MAX_ZIP_BYTES)
    require(sum(row['member_pin']['byte_count'] for row in value['physical_members'])==value['raw_member_bytes'],'output')
    seen=set();physical_metadata={}
    for ordinal,case in enumerate(value['cases']):
        require(type(case) is dict and set(case)=={'case_ordinal','candidate_count','candidates'}
            and type(case['case_ordinal']) is int and case['case_ordinal']==ordinal and type(case['candidate_count']) is int
            and 0<=case['candidate_count']<=n and type(case['candidates']) is list and len(case['candidates'])==case['candidate_count'],'output')
        allowed={(row['family'],row['symbol_role']):row['eligible_count'] for row in value['plan']['cases'][ordinal]['family_symbol_role_matrix']}
        local=set()
        for row in case['candidates']:
            require(type(row) is dict and set(row)=={'physical_hit_ordinal','coverage','typed_role_link_counts'}
                and type(row['physical_hit_ordinal']) is int and 0<=row['physical_hit_ordinal']<n
                and row['physical_hit_ordinal'] not in local,'output')
            index=row['physical_hit_ordinal'];local.add(index);seen.add(index);pure.validate_coverage(row['coverage'])
            metadata={key:row['coverage'][key] for key in ('member_pin','row_count','integer_volume_row_count',
                'fractional_volume_row_count','line_ending_evidence')}
            require(index not in physical_metadata or physical_metadata[index]==metadata,'output');physical_metadata[index]=metadata
            require(row['coverage']['member_pin']==value['physical_members'][index]['member_pin']
                and row['coverage']['required_session_count']==value['plan']['cases'][ordinal]['required_session_count']
                and row['coverage']['reference_session_count']==value['plan']['cases'][ordinal]['reference_session_count']
                and type(row['typed_role_link_counts']) is list and 0<len(row['typed_role_link_counts'])<=128,'output')
            roles=set()
            for item in row['typed_role_link_counts']:
                require(type(item) is dict and set(item)=={'family','symbol_role','lead_count'}
                    and type(item['family']) is type(item['symbol_role']) is str,'output')
                key=(item['family'],item['symbol_role'])
                require(key in allowed and key not in roles and type(item['lead_count']) is int and 0<item['lead_count']<=allowed[key],'output');roles.add(key)
    require(seen==set(range(n)) and len(canonical(value))<=MAX_OUTPUT//2,'output');return value



def binding(args):
    require(all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', getattr(args, key))
        for key, length in (('expected_head', 40), ('caller_sha256', 64), ('profile_sha256', 64))), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}

def safe_env():
    support = ROOT / '.pytest_cache/r336-runtime'
    support.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(support.resolve() == support, 'environment')
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(support), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'GIT_OPTIONAL_LOCKS': '0'}

def preflight(args, deadline):
    binding(args); budget(deadline)
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3, 13) and sys.executable == PYTHON and sys.flags.isolated == 1
        and Path(__file__).absolute() == SOURCE and sys.dont_write_bytecode, 'host')
    require(args.profile_sha256 == sha(canonical(profile_record())), 'source_pin')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], BRANCH),
            (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        result = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=safe_env(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(15, budget(deadline)))
        require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 262144
            and result.stdout.decode('ascii').strip() == expected, 'git_state')
    with HeldFile(SOURCE, maximum=131072, expected={'byte_count': SOURCE.stat().st_size,
            'sha256': args.caller_sha256}, deadline=deadline) as held:
        raw = held.read()
    result = subprocess.run(['/usr/bin/git', 'cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
        cwd=ROOT, env=safe_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=min(15, budget(deadline)))
    require(result.returncode == 0 and not result.stderr and result.stdout == raw, 'source_pin')

def bootstrap(role,stack,deadline):
    """Compile exact held selected source bytes; never execute repo pyc caches."""
    global GUARD_MODULE,PURE_MODULE
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    require(role in ('worker','validate'),'arguments')
    raw_by_name={}
    for relative,expected in SOURCE_PINS.items():
        require(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected),'source_pin')
        held=stack.enter_context(HeldFile(ROOT/relative,maximum=131072,deadline=deadline))
        raw=held.read();require(sha(raw)==expected,'source_pin');raw_by_name[Path(relative).stem]=raw
    sys.path[:]=[str(ROOT),*(value for value in sys.path if value and Path(value).is_absolute()
        and Path(value)!=ROOT and ROOT not in Path(value).parents)]
    package_spec=PathFinder.find_spec('scripts',sys.path)
    require(package_spec is not None and package_spec.origin is None
        and tuple(package_spec.submodule_search_locations)==(str(ROOT/'scripts'),),'source_pin')
    package=sys.modules.get('scripts')
    if package is None:
        package=ModuleType('scripts');package.__package__='scripts';package.__path__=[str(ROOT/'scripts')]
        package.__spec__=package_spec;sys.modules['scripts']=package
    require(getattr(package,'__file__',None) is None and tuple(package.__path__)==(str(ROOT/'scripts'),),'source_pin')
    chosen=['arv2_relocation_security','arv2_r336_original_identity_ownership','arv2_r336_action_semantics','arv2_r336_historical_symbol_coverage']
    if role=='worker':chosen.append('arv2_r298_fixed_data_guard')
    modules={}
    for name in chosen:
        full='scripts.'+name;relative='scripts/'+name+'.py';path=ROOT/relative
        spec=PathFinder.find_spec(full,[str(ROOT/'scripts')])
        require(spec is not None and spec.origin==str(path) and full not in sys.modules,'source_pin')
        module=ModuleType(full);module.__file__=str(path);module.__package__='scripts'
        module.__spec__=ModuleSpec(full,loader=None,origin=str(path));sys.modules[full]=module;setattr(package,name,module)
        exec(compile(raw_by_name[name],str(path),'exec'),module.__dict__);modules[name]=module
    PURE_MODULE=modules['arv2_r336_historical_symbol_coverage'];require(PURE_MODULE.FINITE==PURE_CODES and pin(canonical(PURE_MODULE.profile_record()))==PURE_PROFILE_PIN,'source_pin')
    if role=='worker':
        GUARD_MODULE=modules['arv2_r298_fixed_data_guard'];require(GUARD_MODULE.FINITE==GUARD_CODES,'source_pin')
    require(not any(name=='AlgorithmImports' or name.startswith(('QuantConnect','quantconnect','qc.client','scripts.run_arv2_r298'))
        for name in sys.modules),'environment')
    return {'security':modules['arv2_relocation_security'],'pure':PURE_MODULE,
        **({'guard':GUARD_MODULE} if role=='worker' else {})}

class Store:
    def __init__(self, security):
        self.fd, self.held, self.security = None, [], security
        self.directory_info, self.directory_security = None, None
        self.chain, self.pending = [], []

    def verify(self):
        require(self.fd is not None and meta(os.fstat(self.fd)) == self.directory_info
            == meta(os.stat(CONTROL, follow_symlinks=False))
            and self.directory_info[3] == os.getuid() and stat.S_IMODE(self.directory_info[2]) == 0o700
            and self.security.snapshot(self.fd) == self.directory_security
            and set(os.listdir(self.fd)) == {item[0] for item in self.held}, 'control')
        for parent, name, fd, expected, observed_security in self.chain:
            require(meta(os.fstat(fd)) == expected == meta(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and (observed_security is None or self.security.snapshot(fd) == observed_security), 'control')
        for name, fd, original, expected, observed_security in self.held:
            require(meta(os.fstat(fd)) == original == meta(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and original[3] == os.getuid() and stat.S_IMODE(original[2]) == 0o600 and original[5] == 1
                and not original[9] & ~(stat.UF_TRACKED | stat.UF_HIDDEN)
                and self.security.snapshot(fd) == observed_security
                and pin(os.pread(fd, expected['byte_count'] + 1, 0)) == expected, 'output')
        raw=[item for item in self.held if raw_name(item[0])]
        require(len(raw)<=MAX_RAW_FILES and [item[0] for item in raw]==[f'member-{i:04d}.bin' for i in range(len(raw))]
            and sum(item[3]['byte_count'] for item in raw)<=MAX_RAW_BYTES
            and all(item[3]['byte_count']<=MAX_MEMBER_BYTES for item in raw),'bound')

    def __enter__(self):
        global CLAIM_STATE
        opened = []; path = Path('/')
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            opened.append((parent, '.', parent, None))
            for part in CONTROL.parts[1:]:
                path /= part
                if path in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent)
                        if path == CONTROL: CLAIM_STATE = 'allocated_unknown'
                        os.fsync(parent)
                    except FileExistsError:
                        if path == CONTROL: CLAIM_STATE = 'consumed_or_unknown'
                        require(path != CONTROL, 'claim_spent')
                before = meta(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                opened.append((parent, part, fd, None))
                require(meta(os.fstat(fd)) == before and stat.S_ISDIR(before[2]), 'control')
                if path == ROOT or ROOT in path.parents:
                    require(before[3] == os.getuid() and stat.S_IMODE(before[2]) == (0o755 if path == ROOT else 0o700), 'control')
                parent = fd
            self.fd = parent; CLAIM_STATE = 'allocated_unknown'
            self.chain = [(parent, name, fd, meta(os.fstat(fd)),
                self.security.snapshot(fd) if index >= len(ROOT.parts) - 1 else None)
                for index, (parent, name, fd, _) in enumerate(opened[:-1])]
            self.directory_info = meta(os.fstat(self.fd)); self.directory_security = self.security.snapshot(self.fd)
            os.fsync(self.fd); self.verify(); return self
        except BaseException:
            for _, _, fd, _ in reversed(opened): os.close(fd)
            self.fd = None; raise

    def write(self, name, raw):
        global CLAIM_STATE
        require((name in ('claim.json','worker-started.json','private-diagnosis.json','report.json','failure.json') or raw_name(name))
            and type(raw) is bytes and 0<len(raw)<=(MAX_MEMBER_BYTES if raw_name(name) else MAX_PRIVATE),'output')
        if raw_name(name):
            existing=[item for item in self.held if raw_name(item[0])]
            require(len(existing)<MAX_RAW_FILES and name==f'member-{len(existing):04d}.bin'
                and sum(item[3]['byte_count'] for item in existing)+len(raw)<=MAX_RAW_BYTES,'bound')
        self.verify(); before = self.directory_info
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        self.pending.append(fd)
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); require(count > 0, 'output'); offset += count
        os.fsync(fd); require(os.pread(fd, len(raw) + 1, 0) == raw, 'output')
        require(os.stat(name, dir_fd=self.fd, follow_symlinks=False) == os.fstat(fd), 'output')
        after = meta(os.fstat(self.fd))
        require(all(after[index] == before[index] for index in (0, 1, 2, 3, 4, 9))
            and after[5] in (before[5], before[5] + 1) and after[6] >= before[6]
            and self.security.snapshot(self.fd) == self.directory_security, 'control')
        self.directory_info = after
        self.held.append((name, fd, meta(os.fstat(fd)), pin(raw), self.security.snapshot(fd)))
        self.pending.remove(fd)
        os.fsync(self.fd); self.verify()
        if name == 'claim.json': CLAIM_STATE = 'consumed'
        return pin(raw)

    def __exit__(self, *_):
        try: self.verify()
        finally:
            for _, fd, _, _, _ in self.held: os.close(fd)
            for fd in self.pending: os.close(fd)
            if self.fd is not None: os.close(self.fd)
            for _, _, fd, _, _ in reversed(self.chain): os.close(fd)

def worker(args,deadline):
    global FAILURE_STAGE
    require(type(args.intent_fd) is int and args.intent_fd>=3,'arguments')
    try:intent=os.read(args.intent_fd,4097)
    finally:os.close(args.intent_fd)
    require(intent==canonical(binding(args)),'arguments');preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap('worker',sources,deadline)
        with Store(modules['security']) as store:
            store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}))
            marker_pin=store.write('worker-started.json',canonical({'binding':binding(args),'phase':'historical_symbols'}))
            FAILURE_STAGE='retained_DATA'
            with modules['guard'].FixedDataGuard(DATA_PLAN,deadline=deadline) as data:
                raw=data.read_all_once()['semantics'];n_value=parse(raw,DATA_PLAN['semantics']['byte_count'])
                require(canonical(n_value)==raw,'input')
                plan_public,plan=modules['pure'].plan(n_value,deadline=deadline)
                modules['pure'].validate_plan_summary(plan_public)
                plan=parse(canonical(plan),MAX_PRIVATE)
                require(type(plan.get('lead_records')) is list and len(plan['lead_records'])<=128,'plan')
                with ExitStack() as usb:
                    fixed={}
                    for relative,expected in USB_PINS.items():
                        FAILURE_STAGE='USB_manifest' if relative=='manifest.json' else 'USB_listing'
                        held=usb.enter_context(HeldFile(USB/relative,maximum=2*1024*1024,expected=expected,deadline=deadline))
                        fixed[relative]=held.read()
                    manifest=parse(fixed['manifest.json'],2*1024*1024);rows=listings(fixed[STOCK_DIR+'Ticker_Listing.txt'])
                    FAILURE_STAGE='member_coverage'
                    summary,private,raw_packets=study(plan_public,plan,manifest,rows,modules['pure'],deadline)
                    usb.close()
                data.verify();receipt=data.receipt();budget(deadline)
            sources.close();FAILURE_STAGE='output'
            raw_outputs=[]
            for ordinal,payload in enumerate(raw_packets):
                leaf=f'member-{ordinal:04d}.bin';raw_outputs.append({'leaf':leaf,**store.write(leaf,payload)})
            private['raw_output_inventory']=raw_outputs
            private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE,'bound')
            private_pin=store.write('private-diagnosis.json',private_raw)
            result={'schema':SCHEMA,'complete':True,'summary':summary,'private_pin':private_pin,'raw_outputs':raw_outputs,
                'N_DATA_and_USB_sources_authenticated':True,'all_source_guards_normal_return':True,'USB_read_performed':True,
                'worker_marker_pin':marker_pin,'source_receipt_sha256':sha(canonical(receipt)),**FALSE_FLAGS}
            validate_result(result,args);preflight(args,deadline)
            report={'binding':binding(args),'result':result};report_pin=store.write('report.json',canonical(report));budget(deadline)
            return {**report,'report_pin':report_pin}



def validate_result(value,args):
    require(type(value) is dict and set(value)=={'schema','complete','summary','private_pin','raw_outputs',
        'N_DATA_and_USB_sources_authenticated','all_source_guards_normal_return','USB_read_performed','worker_marker_pin',
        'source_receipt_sha256',*FALSE_FLAGS} and value['schema']==SCHEMA and value['complete'] is True
        and value['N_DATA_and_USB_sources_authenticated'] is value['all_source_guards_normal_return'] is value['USB_read_performed'] is True
        and value['worker_marker_pin']==pin(canonical({'binding':binding(args),'phase':'historical_symbols'}))
        and type(value['source_receipt_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['source_receipt_sha256'])
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    require(PURE_MODULE is not None,'source_pin');validate_summary(value['summary'],PURE_MODULE);checked_pin(value['private_pin'],MAX_PRIVATE)
    require(type(value['raw_outputs']) is list and len(value['raw_outputs'])==value['summary']['physical_member_count'],'output')
    for ordinal,(row,physical) in enumerate(zip(value['raw_outputs'],value['summary']['physical_members'],strict=True)):
        require(type(row) is dict and set(row)=={'leaf','byte_count','sha256'} and row['leaf']==f'member-{ordinal:04d}.bin'
            and {key:row[key] for key in ('byte_count','sha256')}==physical['member_pin'],'output')
    return value



def native_profile():
    value='(version 1)(allow default)(deny network*)(deny file-write* (subpath "/Volumes"))'
    paths=[USB/name for name in (*USB_PINS,*ARCHIVES)]
    allowed_USB={path for leaf in paths for path in (*leaf.parents,leaf) if path==Path('/Volumes') or Path('/Volumes') in path.parents}
    value+='(deny file-read* (require-all (subpath "/Volumes")'+''.join('(require-not (literal "'+str(path)+'"))' for path in sorted(allowed_USB))+'))'
    value+=''.join('(deny file-read* file-write* (subpath "'+path+'"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value+='(deny file-write* (require-all (require-not (subpath "'+str(CONTROL)+'"))'
    value+='(require-not (literal "'+str(CONTROL.parent)+'"))(require-not (subpath "'+str(ROOT/'.pytest_cache')+'"))(require-not (literal "/dev/null"))))'
    paths=[*(ROOT/item['relative_path'] for item in DATA_PLAN.values()),CONTROL]
    allowed={path for leaf in paths for path in (*leaf.parents,leaf) if path==ROOT/'artifacts' or ROOT/'artifacts' in path.parents}
    value+='(deny file-read* (require-all (subpath "'+str(ROOT/'artifacts')+'")'
    value+='(require-not (subpath "'+str(CONTROL)+'"))'
    value+=''.join('(require-not (literal "'+str(path)+'"))' for path in sorted(allowed))+'))'
    return value

def parent(args):
    preflight(args, ENTRY_DEADLINE)
    with ExitStack() as sources:
        bootstrap('validate',sources,ENTRY_DEADLINE)
        return _parent_bound(args)

def _parent_bound(args):
    global CHILD_OBSERVATION,CLAIM_STATE
    CHILD_OBSERVATION=None;preflight(args,ENTRY_DEADLINE)
    reader,writer=os.pipe()
    try:
        intent=canonical(binding(args));require(len(intent)<4096 and os.write(writer,intent)==len(intent),'bound')
    finally:os.close(writer)
    stop=min(ENTRY_DEADLINE,time.monotonic()+WORKER_SECONDS)
    command=['/usr/bin/sandbox-exec','-p',native_profile(),PYTHON,'-I','-B',str(SOURCE),'worker',
        '--expected-head',args.expected_head,'--caller-sha256',args.caller_sha256,'--profile-sha256',args.profile_sha256,
        '--intent-fd',str(reader),'--outer-deadline',repr(stop)]
    CLAIM_STATE='consumed_or_unknown'
    try:actual,raw,stderr_count,stderr_sha,problem=run_child(command,(reader,),stop)
    finally:os.close(reader)
    observed={'actual_child_exit':actual,'child_stdout_pin':pin(raw),'child_stderr_byte_count':stderr_count,
        'child_stderr_sha256':stderr_sha,'failure_code':problem}
    CHILD_OBSERVATION=observed
    require(problem is None,problem if problem in FINITE else 'child_failure')
    require(type(actual) is int and actual in (0,2) and stderr_count==0 and stderr_sha==sha(b'')
        and raw.endswith(b'\n') and raw.count(b'\n')==1,'child_failure')
    value=parse(raw[:-1],MAX_OUTPUT);require(canonical(value)+b'\n'==raw,'output')
    if actual==0:validate_envelope(raw,actual,args);key='outcome'
    else:validate_failure(value,args);key='failure'
    return {'binding':binding(args),'observation':observed,'output_authenticated':True,key:value}

def validate_envelope(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit == 0 and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'child_failure')
    value = parse(raw[:-1], MAX_OUTPUT); require(canonical(value) + b'\n' == raw and type(value) is dict
        and set(value) == {'binding', 'result', 'report_pin'} and value['binding'] == binding(args), 'output')
    validate_result(value['result'],args)
    require(value['report_pin'] == pin(canonical({'binding': binding(args), 'result': value['result']})), 'output')
    return value

def validate_parent_output(raw,actual_exit,args):
    require(type(actual_exit) is int and actual_exit in (0,2) and type(raw) is bytes
        and raw.endswith(b'\n') and raw.count(b'\n')==1,'output')
    value=parse(raw[:-1],MAX_OUTPUT);require(canonical(value)+b'\n'==raw and type(value) is dict,'output')
    if value.get('schema')==SCHEMA:
        require(actual_exit==2,'output');validate_failure(value,args)
        return {'binding':binding(args),'output_authenticated':True,'accepted':False,'failure':value}
    key='outcome' if actual_exit==0 else 'failure'
    require(set(value)=={'binding','observation','output_authenticated',key} and value['binding']==binding(args)
        and value['output_authenticated'] is True,'output')
    observed=validate_observation(value['observation'])
    require(type(observed['actual_child_exit']) is int and observed['actual_child_exit']==actual_exit
        and observed['child_stderr_byte_count']==0 and observed['child_stderr_sha256']==sha(b'')
        and observed['failure_code'] is None and observed['child_stdout_pin']==pin(canonical(value[key])+b'\n'),'output')
    if key=='failure':validate_failure(value[key],args)
    else:validate_envelope(canonical(value[key])+b'\n',actual_exit,args)
    return {'binding':binding(args),'output_authenticated':True,'accepted':actual_exit==0,
        **({'result':value[key]['result']} if actual_exit==0 else {'failure':value[key]})}

def run_child(command,descriptors,deadline):
    output=bytearray();stderr=hashlib.sha256();count=0;child=None;problem=None
    try:
        child=subprocess.Popen(command,cwd=ROOT,env=safe_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,close_fds=True,pass_fds=descriptors)
        with selectors.DefaultSelector() as selector:
            for stream,label in ((child.stdout,'out'),(child.stderr,'err')):
                os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,label)
            while selector.get_map() or child.poll() is None:
                for key,_ in selector.select(min(.1,budget(deadline))):
                    chunk=os.read(key.fileobj.fileno(),8192)
                    if not chunk:selector.unregister(key.fileobj)
                    elif key.data=='out':require(len(output)+len(chunk)<=MAX_OUTPUT,'bound');output.extend(chunk)
                    else:count+=len(chunk);stderr.update(chunk);require(count<=8192,'child_stderr')
        child.wait(timeout=min(5,budget(deadline)))
    except BaseException as error:problem=finite(error)
    finally:
        if child is not None:
            if child.poll() is None:child.kill()
            child.wait(timeout=5);child.stdout.close();child.stderr.close()
    return (None if child is None else child.returncode),bytes(output),count,stderr.hexdigest(),problem

def listings(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 2 * 1024 * 1024, 'listing')
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        require(reader.fieldnames == ['Ticker', 'Name', 'First Date', 'Last Date'], 'listing')
        rows = list(reader)
    except (ValueError, UnicodeError, csv.Error): raise Refused('listing') from None
    require(0 < len(rows) <= 30000 and all(set(row) == set(reader.fieldnames)
        and all(type(value) is str and len(value) <= 1024 for value in row.values()) for row in rows), 'listing')
    return rows

def manifest_entry(manifest, relative):
    require(relative in ARCHIVES, 'scope')
    key = relative[:-4] if relative.endswith(('.zip', '.txt')) else relative
    value = manifest.get(key)
    require(type(value) is dict and set(value) == {'path', 'bytes', 'md5', 'ok', 'fetched', 'url'}
        and value['ok'] is True and type(value['bytes']) is int and 0 < value['bytes'] <= MAX_ZIP_BYTES
        and type(value['md5']) is str and re.fullmatch('[0-9a-fA-F]{32}', value['md5']), 'manifest')
    return {'byte_count': value['bytes'], 'md5': value['md5'].lower()}

class Archive:
    def __init__(self, held, expected, *, known_pin=None):
        self.held, self.expected, self.zip, self.file, self.container_pin = held, expected, None, None, None
        self.known_pin=known_pin

    def __enter__(self):
        require(self.held.info[6] == self.expected['byte_count'], 'archive')
        self.held.verify(); digest, transport, offset = hashlib.sha256(), hashlib.md5(), 0
        while offset < self.held.info[6]:
            budget(self.held.deadline); raw = os.pread(self.held.fd, min(65536, self.held.info[6] - offset), offset)
            require(raw, 'archive'); digest.update(raw); transport.update(raw); offset += len(raw)
        require(offset == self.expected['byte_count'] and transport.hexdigest() == self.expected['md5'], 'archive')
        self.container_pin = {'byte_count': offset, 'sha256': digest.hexdigest()}
        require(self.known_pin is None or self.container_pin==self.known_pin,'known_pin')
        self.held.verify(); self.file = os.fdopen(os.dup(self.held.fd), 'rb')
        try:
            self.zip = zipfile.ZipFile(self.file)
            infos = self.zip.infolist()
            require(0 < len(infos) <= MAX_MEMBERS and len({item.filename for item in infos}) == len(infos), 'archive')
            return self
        except BaseException:
            self.__exit__(None, None, None); raise

    def member(self, name):
        self.held.verify()
        found = [item for item in self.zip.infolist() if item.filename == name]
        require(len(found) <= 1, 'member')
        if not found: return None
        item = found[0]
        require(not item.is_dir() and '/' not in name and '\\' not in name and not item.flag_bits & 1
            and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
            and not stat.S_ISLNK(item.external_attr >> 16) and 0 < item.file_size <= MAX_MEMBER_BYTES
            and item.file_size <= max(1, item.compress_size) * 1000, 'member')
        try: raw = self.zip.read(item)
        except (zipfile.BadZipFile, RuntimeError, OSError, ValueError): raise Refused('member') from None
        require(len(raw) == item.file_size, 'member'); self.held.verify(); return raw

    def __exit__(self, *_):
        if self.zip is not None: self.zip.close()
        if self.file is not None: self.file.close()
        self.held.verify()

class Parser(argparse.ArgumentParser):
    def error(self, message): raise Refused('arguments')

def main():
    global ACTIVE_BINDING
    parser = Parser(add_help=False)
    parser.add_argument('mode', choices=('launch', 'worker', 'validate', 'profile'))
    for name in ('expected-head', 'caller-sha256', 'profile-sha256'): parser.add_argument('--' + name)
    parser.add_argument('--intent-fd', type=int); parser.add_argument('--outer-deadline', type=float)
    parser.add_argument('--actual-parent-exit', type=int)
    args = parser.parse_args()
    if args.mode == 'profile':
        require(all(getattr(args, key) is None for key in ('expected_head', 'caller_sha256', 'profile_sha256',
            'intent_fd', 'outer_deadline', 'actual_parent_exit')), 'arguments')
        return profile_record()
    ACTIVE_BINDING = binding(args)
    if args.mode == 'launch':
        require(args.intent_fd is args.outer_deadline is args.actual_parent_exit is None, 'arguments')
        def parent_expired(*_): raise Refused('deadline')
        signal.signal(signal.SIGALRM,parent_expired);signal.setitimer(signal.ITIMER_REAL,budget(ENTRY_DEADLINE))
        return parent(args)
    if args.mode == 'validate':
        require(args.intent_fd is args.outer_deadline is None and type(args.actual_parent_exit) is int
            and args.actual_parent_exit in (0, 2), 'arguments')
        def validation_expired(*_): raise Refused('deadline')
        signal.signal(signal.SIGALRM, validation_expired); signal.setitimer(signal.ITIMER_REAL, 30)
        preflight(args, ENTRY_DEADLINE)
        with ExitStack() as sources:
            bootstrap('validate',sources,ENTRY_DEADLINE)
            return validate_parent_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_parent_exit, args)
    require(args.outer_deadline is not None and args.actual_parent_exit is None, 'arguments')
    deadline = min(ENTRY_DEADLINE, args.outer_deadline); budget(deadline)
    def expired(*_): raise Refused('deadline')
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, budget(deadline))
    return worker(args, deadline)

if __name__ == '__main__':
    try:
        value = main(); raw = canonical(value) + b'\n'; require(len(raw) <= MAX_OUTPUT, 'bound')
        sys.stdout.buffer.write(raw); raise SystemExit(2 if type(value) is dict and 'failure' in value else 0)
    except SystemExit: raise
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure_packet(finite(error))) + b'\n')
        raise SystemExit(2)
