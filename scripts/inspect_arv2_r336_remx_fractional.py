"""One new offline REMX fractional-volume temporal/unit observation.

The supplied raw source and both historical symbol eras stay unchanged. This
contract tests a new, dated fractional-feed hypothesis; no old D operation is
called. Its private evidence keeps exact original fractional source records.
No precision adjustment, rounding, feed claim or price/source admission occurs.
"""
import argparse
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
import hashlib
from importlib.machinery import PathFinder, ModuleSpec
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
from types import ModuleType

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE=ROOT/'scripts/inspect_arv2_r336_remx_fractional.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/firstrate/R336-20261103-L'
USB=Path('/Volumes/SANDISK/firstrate')
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r336-REMX-fractional-temporal-v1'
SOURCE_PINS={
 'scripts/arv2_relocation_security.py':'3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
 'scripts/arv2_r335_remx_identity.py':'8f124b390a3f81a0f50354d99f34b12d4c1cd8d5d2270661e58da5da4fefae63',
 'scripts/inspect_arv2_r335_remx_fields.py':'3cea894108d8ccc0498913aef03217e85e3f6a7aa2e7c14e718d59f04710857c',
}
ETF_DIR='market/ETF-Complete_5000+_Tickers/'
USB_PINS={
 'manifest.json':{'byte_count':327907,'sha256':'c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8'},
 ETF_DIR+'Ticker_Listing.txt':{'byte_count':355087,'sha256':'4532194e351a00a51b0e379b4df86f20bd92aa9a98f8110f81ff9d90c112f559'},
}
REMX_ARCHIVE=ETF_DIR+'Tickers_R_Day_Unadjusted_Full_Dataset.zip'
ARCHIVE_PIN={'byte_count':5532476,'sha256':'5730923356aac1b3ffedb7603fe60c2a7882eb2d43ae41a6b6bdc2a8ce3cd45e'}
REMX_MEMBER='REMX_full_1day_UNADJUSTED.txt'
REMX_PIN={'byte_count':181222,'sha256':'b8c54990689501ddc55183e6bb28c8eb7cd47a8817c04153480a6ef613b1de5e'}
ERAS=((0,'2005-01-04','2006-06-30',323),(1,'2010-10-28','2026-10-16',4016))
PARTITION_SHA256='4674c20222e26c369abbd654c61ed14f08a7e49861d34251b129db49d392632e'
CUTOFF='2026-02-23'
PRIMARY_DOCS=(
 'https://www.finra.org/sites/default/files/2026-01/Trade-Reporting-Notice-20260114.pdf',
 'https://www.ctaplan.com/publicdocs/ctaplan/CTS_Pillar_Output_Specification.pdf',
 'https://firstratedata.com/about/FAQ',
)
TEMPORAL=('before_cutoff','at_cutoff','after_cutoff')
EXPECTED_FRACTIONAL=20
MAX_SCALE=10128
SECONDS,MAX_OUTPUT,MAX_PRIVATE=300,131072,131072
MAX_ZIP_BYTES,MAX_MEMBER_BYTES,MAX_LINE_BYTES=64*1024*1024,4*1024*1024,640
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
FALSE_FLAGS={name:False for name in (
 'provider_contact','credential_access','QC_contact','Safari_access','old_control_read','old_operation_replayed',
 'old_D_operation_replayed','other_USB_source_read','source_modified','volume_rounded','volume_normalized',
 'fractional_feed_used_by_FirstRate_proven','twenty_anomalies_cause_proven','RAW_volume_units_admitted',
 'daily_close_convention_proven','identity_admitted','price_input_admitted','source_assignment_changed',
 'source_or_processing_rights_granted','point_in_time_proven','formal_forward_ready','paper_or_live_ready',
 'licensed_rows_disclosed','historical_or_continuous_integrity_proven')}
FINITE=frozenset(('arguments','host','environment','git_state','source_pin','source_changed','scope','deadline','bound',
 'claim_spent','control','path','shape','metadata','changed','input','listing','archive','member','source_data',
 'encoding','line_ending','row_bound','row_shape','partition','date_order','volume','precision','output','child_stderr','child_failure','unknown'))
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
STAGE='preflight'
HELPER_MODULE=None

class Refused(ValueError):
    pass



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
    if HELPER_MODULE is not None and type(error) is HELPER_MODULE.Refused:
        return 'source_data'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def failure_packet(code):
    require(type(code) is str and code in FINITE,'output')
    return {'schema':SCHEMA,'binding':ACTIVE_BINDING,'failure_code':code,'stage':STAGE,
        'claim_state':CLAIM_STATE,'attempt_reusable':False,**FALSE_FLAGS}


def validate_failure(value,args):
    require(type(value) is dict and set(value)=={'schema','binding','failure_code','stage','claim_state','attempt_reusable',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['binding']==binding(args)
        and type(value['failure_code']) is str and value['failure_code'] in FINITE
        and value['stage'] in ('preflight','USB_manifest','USB_listing','REMX_fractional','output')
        and value['claim_state'] in ('unallocated','allocated_unknown','consumed','consumed_or_unknown')
        and value['attempt_reusable'] is False and all(value[key] is False for key in FALSE_FLAGS),'output')
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
        'source_pins':SOURCE_PINS,'USB_root':str(USB),'USB_pins':USB_PINS,
        'archive_relative_path':REMX_ARCHIVE,'archive_pin':ARCHIVE_PIN,'member_name':REMX_MEMBER,'member_pin':REMX_PIN,
        'maximum_seconds':SECONDS,'maximum_output_bytes':MAX_OUTPUT,'maximum_private_bytes':MAX_PRIVATE,
        'maximum_archive_bytes':MAX_ZIP_BYTES,'maximum_member_bytes':MAX_MEMBER_BYTES,
        'purpose':'NEW_fractional_volume_temporal_precision_hypothesis_not_old_D_generic_scan',
        'cutoff':CUTOFF,'cutoff_meaning':'FINRA_NMS_fractional_share_reporting_effective_date_not_vendor_feed_proof',
        'primary_docs':list(PRIMARY_DOCS),'CTA_anchor':'CTS_v2.11b_2026Jan29_section6.6.4_Fractional_Consolidated_End_of_Day_Summary_6_implied_decimals',
        'FINRA_field_distinction':'new_Fractional_Share_Quantity_is_separate_from_still_integer_Quantity_not_every_daily_volume_field_is_fractional',
        'partition_sha256':PARTITION_SHA256,'expected_old_quarantined_rows':323,'expected_ETF_rows':4016,
        'expected_preserved_fractional_ETF_rows':EXPECTED_FRACTIONAL,'temporal_labels':list(TEMPORAL),
        'precision':'exact_Decimal_tuple_encoded_scale_vs_effective_scale_after_counting_trailing_zeros_no_normalization_or_context_arithmetic',
        'private_records':'exact_original_record_bytes_hex_with_terminator_and_original_fields_no_price_or_volume_normalization',
        'source_authentication':'held_full_SHA256_before_ZIP_parse_plus_local_manifest_MD5_and_member_CRC_full_SHA256',
        'helper_composition':'compile_pinned_D_parameterized_transport_and_pure_numeric_helpers_only_no_globals_patched_no_D_entrypoint',
        'selected_source_pins_not_whole_interpreter_integrity':True,'claim_before_USB_reads':True,
        'normal_guard_return_before_publication':True,'outputs':['claim.json','private-diagnosis.json','report.json'],
        'parent_watchdog':'SIGALRM_armed_before_parent_preflight_spawn_capture_and_publication',
        'deadline_limitation':'uninterruptible_IO_host_suspension_and_own5s_reap_not_bounded',**FALSE_FLAGS}


def binding(args):
    require(all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', getattr(args, key))
        for key, length in (('expected_head', 40), ('caller_sha256', 64), ('profile_sha256', 64))), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}

def safe_env():
    support = ROOT / '.pytest_cache/r336-l-runtime'
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
    global HELPER_MODULE
    require(role in ('worker','validate'),'arguments')
    raw_by_name={}
    for relative,expected in SOURCE_PINS.items():
        held=stack.enter_context(HeldFile(ROOT/relative,maximum=131072,deadline=deadline))
        raw=held.read();require(sha(raw)==expected,'source_pin');raw_by_name[Path(relative).stem]=raw
    sys.path[:]=[str(ROOT),*(item for item in sys.path if item and Path(item).is_absolute()
        and Path(item)!=ROOT and ROOT not in Path(item).parents)]
    spec=PathFinder.find_spec('scripts',sys.path)
    require(spec is not None and spec.origin is None and tuple(spec.submodule_search_locations)==(str(ROOT/'scripts'),),'source_pin')
    package=sys.modules.get('scripts')
    if package is None:
        package=ModuleType('scripts');package.__package__='scripts';package.__path__=[str(ROOT/'scripts')]
        package.__spec__=spec;sys.modules['scripts']=package
    require(getattr(package,'__file__',None) is None and tuple(package.__path__)==(str(ROOT/'scripts'),),'source_pin')
    modules={}
    for name in ('arv2_relocation_security','arv2_r335_remx_identity','inspect_arv2_r335_remx_fields'):
        full='scripts.'+name;path=ROOT/'scripts'/(name+'.py')
        require(full not in sys.modules,'source_pin')
        found=PathFinder.find_spec(full,[str(ROOT/'scripts')]);require(found is not None and found.origin==str(path),'source_pin')
        module=ModuleType(full);module.__file__=str(path);module.__package__='scripts'
        module.__spec__=ModuleSpec(full,loader=None,origin=str(path));sys.modules[full]=module;setattr(package,name,module)
        exec(compile(raw_by_name[name],str(path),'exec'),module.__dict__);modules[name]=module
    HELPER_MODULE=modules['inspect_arv2_r335_remx_fields']
    return {'security':modules['arv2_relocation_security'],'remx':modules['arv2_r335_remx_identity'],'helper':HELPER_MODULE}


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
        require(name in ('claim.json', 'private-diagnosis.json', 'report.json')
            and type(raw) is bytes and 0 < len(raw) <= MAX_PRIVATE, 'output')
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

def fractional_precision(value):
    """Exact finite Decimal scale and micro-share grid; never round or normalize."""
    require(type(value) is Decimal and value.is_finite() and value>=0,'precision')
    _,digits,exponent=value.as_tuple()
    require(type(exponent) is int and -10000<=exponent<=10000 and 0<len(digits)<=128,'precision')
    trailing=0
    for digit in reversed(digits):
        if digit!=0:break
        trailing+=1
    places=max(0,-exponent-trailing)
    power=exponent+6
    micro_grid=power>=0 or (trailing>=-power)
    require(1<=places<=MAX_SCALE and micro_grid is (places<=6),'precision')
    return {'encoded_decimal_scale':max(0,-exponent),'decimal_places':places,
        'at_most_six_decimal_places':places<=6,'exact_microshare_increment':micro_grid}


def inspect_fractional(raw,listing,remx,helper):
    require(type(raw) is bytes and pin(raw)==REMX_PIN,'source_pin')
    lexical=helper.validate_lexical(helper.line_ending_evidence(raw))
    require(lexical['line_endings_supported'] is True,'line_ending')
    try:raw.decode('ascii')
    except UnicodeDecodeError:raise Refused('encoding') from None
    pieces=raw.split(b'\n')
    records=[piece+b'\n' for piece in pieces[:-1]]+([pieces[-1]] if pieces[-1] else [])
    require(len(records)==4339 and b''.join(records)==raw,'partition')
    segments=[{'first_date':None,'last_date':None,'row_count':0} for _ in ERAS]
    temporal={key:0 for key in TEMPORAL};scales={};preserved=[];previous=None;width=None
    old_integer=ETF_integer=0
    for index,record in enumerate(records):
        line=record[:-2] if record.endswith(b'\r\n') else record[:-1] if record.endswith(b'\n') else record
        require((index==len(records)-1 or record.endswith(b'\n')) and b'\r' not in line
            and b'\n' not in line and 0<len(line)<=MAX_LINE_BYTES,'line_ending')
        fields=line.decode('ascii').split(',');require(len(fields)==6,'row_shape')
        current=helper.timestamp(fields[0]);require(previous is None or previous<current,'date_order')
        if width is None:width=len(fields[0])
        require(len(fields[0])==width,'row_shape')
        opening,high,low,close=tuple(helper.price_number(item) for item in fields[1:5])
        require(low<=min(opening,close)<=max(opening,close)<=high,'source_data')
        category,_=helper.volume_class(fields[5]);require(category in ('integer_nonnegative_count','fractional_nonnegative_count'),'volume')
        era=0 if index<323 else 1;segment=segments[era]
        if segment['first_date'] is None:segment['first_date']=current
        segment['last_date']=current;segment['row_count']+=1
        if era==0:
            require(category=='integer_nonnegative_count','volume');old_integer+=1
        elif category=='integer_nonnegative_count':ETF_integer+=1
        else:
            precision=fractional_precision(Decimal(fields[5]))
            label='before_cutoff' if current<CUTOFF else 'at_cutoff' if current==CUTOFF else 'after_cutoff'
            temporal[label]+=1;places=precision['decimal_places'];scales[places]=scales.get(places,0)+1
            preserved.append({'source_record_ordinal':index,'source_record_hex':record.hex(),'original_fields':fields,
                'temporal_relation':label,'precision':precision})
        previous=current
    metadata={'raw_member_pin':REMX_PIN,'ticker':'REMX','listing':listing,'segments':segments,'total_row_count':len(records)}
    partition=remx.validate_partition(metadata).to_record()
    require(partition.get('metadata_partition_matches_policy') is True and remx.profile_sha256()==PARTITION_SHA256,'partition')
    require(old_integer==323 and ETF_integer==3996 and len(preserved)==EXPECTED_FRACTIONAL,'volume')
    scale_rows=[{'decimal_places':places,'row_count':scales[places]} for places in sorted(scales)]
    within=sum(count for places,count in scales.items() if places<=6)
    public={'row_count':4339,'quarantined_old_row_count':323,'ETF_row_count':4016,
        'old_integer_volume_count':old_integer,'ETF_integer_volume_count':ETF_integer,'fractional_ETF_row_count':len(preserved),
        'cutoff':CUTOFF,'temporal_counts':temporal,'fractional_scale_counts':scale_rows,
        'at_most_six_decimal_places_count':within,'over_six_decimal_places_count':len(preserved)-within,
        'exact_microshare_increment_count':sum(item['precision']['exact_microshare_increment'] for item in preserved),
        'not_microshare_increment_count':sum(not item['precision']['exact_microshare_increment'] for item in preserved),
        'partition_policy_sha256':PARTITION_SHA256,'all_original_rows_validated_without_volume_admission':True,
        'exact_original_fractional_records_preserved':True,'guarded_full_member_pin':REMX_PIN}
    validate_inspection(public)
    private={'schema':SCHEMA+'-private','inspection':public,'fractional_records':preserved,
        'original_member_pin':REMX_PIN,'old_323_rows_quarantined':True,**FALSE_FLAGS}
    return public,private


def validate_inspection(value):
    keys={'row_count','quarantined_old_row_count','ETF_row_count','old_integer_volume_count','ETF_integer_volume_count',
        'fractional_ETF_row_count','cutoff','temporal_counts','fractional_scale_counts','at_most_six_decimal_places_count',
        'over_six_decimal_places_count','exact_microshare_increment_count','not_microshare_increment_count',
        'partition_policy_sha256','all_original_rows_validated_without_volume_admission',
        'exact_original_fractional_records_preserved','guarded_full_member_pin'}
    require(type(value) is dict and set(value)==keys and value['cutoff']==CUTOFF
        and value['partition_policy_sha256']==PARTITION_SHA256 and value['guarded_full_member_pin']==REMX_PIN
        and value['all_original_rows_validated_without_volume_admission'] is value['exact_original_fractional_records_preserved'] is True,'output')
    for key,expected in (('row_count',4339),('quarantined_old_row_count',323),('ETF_row_count',4016),
        ('old_integer_volume_count',323),('ETF_integer_volume_count',3996),('fractional_ETF_row_count',EXPECTED_FRACTIONAL)):
        require(type(value[key]) is int and value[key]==expected,'output')
    temporal=value['temporal_counts'];require(type(temporal) is dict and set(temporal)==set(TEMPORAL)
        and all(type(count) is int and 0<=count<=EXPECTED_FRACTIONAL for count in temporal.values())
        and sum(temporal.values())==EXPECTED_FRACTIONAL and temporal['at_cutoff']<=1,'output')
    scales=value['fractional_scale_counts'];require(type(scales) is list and 1<=len(scales)<=EXPECTED_FRACTIONAL,'output')
    places=[];total=within=0
    for item in scales:
        require(type(item) is dict and set(item)=={'decimal_places','row_count'}
            and type(item['decimal_places']) is int and 1<=item['decimal_places']<=MAX_SCALE
            and type(item['row_count']) is int and 1<=item['row_count']<=EXPECTED_FRACTIONAL,'output')
        places.append(item['decimal_places']);total+=item['row_count']
        if item['decimal_places']<=6:within+=item['row_count']
    require(places==sorted(set(places)) and total==EXPECTED_FRACTIONAL,'output')
    for key,expected in (('at_most_six_decimal_places_count',within),('over_six_decimal_places_count',EXPECTED_FRACTIONAL-within),
        ('exact_microshare_increment_count',within),('not_microshare_increment_count',EXPECTED_FRACTIONAL-within)):
        require(type(value[key]) is int and value[key]==expected,'output')
    return value


def hash_held(held,expected):
    held.verify();digest=hashlib.sha256();offset=0
    while offset<held.info[6]:
        budget(held.deadline);raw=os.pread(held.fd,min(65536,held.info[6]-offset),offset)
        require(raw,'archive');digest.update(raw);offset+=len(raw)
    require({'byte_count':offset,'sha256':digest.hexdigest()}==expected,'source_pin');held.verify()


def worker(args,deadline):
    global STAGE
    require(type(args.intent_fd) is int and args.intent_fd>=3,'arguments')
    try:intent=os.read(args.intent_fd,4097)
    finally:os.close(args.intent_fd)
    require(intent==canonical(binding(args)),'arguments');preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap('worker',sources,deadline);helper=modules['helper']
        with Store(modules['security']) as store:
            store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}))
            fixed={}
            for relative,expected in USB_PINS.items():
                STAGE='USB_manifest' if relative=='manifest.json' else 'USB_listing'
                held=sources.enter_context(helper.HeldFile(USB/relative,maximum=2*1024*1024,expected=expected,deadline=deadline))
                fixed[relative]=held.read()
            manifest=parse(fixed['manifest.json'],USB_PINS['manifest.json']['byte_count'])
            matches=[row for row in helper.listings(fixed[ETF_DIR+'Ticker_Listing.txt']) if row['Ticker']=='REMX']
            require(len(matches)==1,'listing')
            listing={'name':matches[0]['Name'],'first_date':matches[0]['First Date'],'last_date':matches[0]['Last Date']}
            expected=helper.manifest_entry(manifest,REMX_ARCHIVE)
            held=sources.enter_context(helper.HeldFile(USB/REMX_ARCHIVE,maximum=MAX_ZIP_BYTES,deadline=deadline))
            hash_held(held,ARCHIVE_PIN)
            archive=sources.enter_context(helper.Archive(held,expected));require(archive.container_pin==ARCHIVE_PIN,'source_pin')
            STAGE='REMX_fractional';raw=archive.member(REMX_MEMBER);require(raw is not None,'member')
            inspection,private=inspect_fractional(raw,listing,modules['remx'],helper)
            sources.close();STAGE='output'
            private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE,'output')
            private_pin=store.write('private-diagnosis.json',private_raw)
            result={'schema':SCHEMA,'complete':True,'inspection':inspection,'private_pin':private_pin,
                'original_member_pin':REMX_PIN,'archive_pin':ARCHIVE_PIN,'source_guard_normal_return':True,**FALSE_FLAGS}
            validate_result(result);preflight(args,deadline)
            report={'binding':binding(args),'result':result};report_pin=store.write('report.json',canonical(report));budget(deadline)
            return {**report,'report_pin':report_pin}


def validate_result(value):
    require(type(value) is dict and set(value)=={'schema','complete','inspection','private_pin','original_member_pin',
        'archive_pin','source_guard_normal_return',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['complete'] is value['source_guard_normal_return'] is True
        and value['original_member_pin']==REMX_PIN and value['archive_pin']==ARCHIVE_PIN
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    validate_inspection(value['inspection']);item=value['private_pin']
    require(type(item) is dict and set(item)=={'byte_count','sha256'} and type(item['byte_count']) is int
        and 0<item['byte_count']<=MAX_PRIVATE and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']),'output')
    return value


def native_profile():
    value='(version 1)(allow default)(deny network*)(deny file-write* (subpath "/Volumes"))'
    for path in ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'):
        value+='(deny file-read* file-write* (subpath "'+path+'"))'
    value+='(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value+='(deny file-write* (require-all (require-not (subpath "'+str(CONTROL)+'"))'
    value+='(require-not (literal "'+str(CONTROL.parent)+'"))(require-not (subpath "'+str(ROOT/'.pytest_cache')+'"))(require-not (literal "/dev/null"))))'
    own={path for path in (*CONTROL.parents,CONTROL) if path==ROOT/'artifacts' or ROOT/'artifacts' in path.parents}
    value+='(deny file-read* (require-all (subpath "'+str(ROOT/'artifacts')+'")'
    value+='(require-not (subpath "'+str(CONTROL)+'"))'
    value+=''.join('(require-not (literal "'+str(path)+'"))' for path in sorted(own))+'))'
    leaves=[USB/name for name in (*USB_PINS,REMX_ARCHIVE)]
    allowed={path for leaf in leaves for path in (*leaf.parents,leaf) if path==Path('/Volumes') or Path('/Volumes') in path.parents}
    value+='(deny file-read* (require-all (subpath "/Volumes")'
    value+=''.join('(require-not (literal "'+str(path)+'"))' for path in sorted(allowed))+'))'
    return value


def parent(args):
    preflight(args, ENTRY_DEADLINE)
    reader, writer = os.pipe()
    try:
        raw = canonical(binding(args)); require(len(raw) < 4096 and os.write(writer, raw) == len(raw), 'bound')
    finally: os.close(writer)
    child, output, stderr_count = None, bytearray(), 0
    try:
        child = subprocess.Popen(['/usr/bin/sandbox-exec', '-p', native_profile(), PYTHON, '-I', '-B', str(SOURCE), 'worker',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
            '--profile-sha256', args.profile_sha256, '--intent-fd', str(reader), '--outer-deadline', repr(ENTRY_DEADLINE)],
            cwd=ROOT, env=safe_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True, pass_fds=(reader,))
        with selectors.DefaultSelector() as selected:
            for stream, label in ((child.stdout, 'stdout'), (child.stderr, 'stderr')):
                os.set_blocking(stream.fileno(), False); selected.register(stream, selectors.EVENT_READ, label)
            while selected.get_map() or child.poll() is None:
                for key, _ in selected.select(min(.1, budget(ENTRY_DEADLINE))):
                    raw = os.read(key.fileobj.fileno(), 8192)
                    if not raw: selected.unregister(key.fileobj)
                    elif key.data == 'stderr': stderr_count += len(raw); raise Refused('child_stderr')
                    else:
                        require(len(output) + len(raw) <= MAX_OUTPUT, 'bound'); output.extend(raw)
        actual = child.wait(timeout=min(5, budget(ENTRY_DEADLINE)))
        require(type(actual) is int and actual in (0, 2) and bytes(output).endswith(b'\n')
            and bytes(output).count(b'\n') == 1, 'child_failure')
        if actual == 0:
            value = validate_envelope(bytes(output), actual, args); key = 'outcome'
        else:
            value = parse(bytes(output)[:-1], MAX_OUTPUT)
            require(canonical(value) + b'\n' == bytes(output), 'output')
            validate_failure(value, args); key = 'failure'
        return {'binding': binding(args), 'actual_child_exit': actual, 'output_authenticated': True,
            'child_stdout_pin': pin(bytes(output)), 'child_stderr_byte_count': stderr_count, key: value}
    finally:
        os.close(reader)
        if child is not None:
            if child.poll() is None: child.kill()
            child.wait(timeout=5)
            child.stdout.close(); child.stderr.close()

def validate_envelope(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit == 0 and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'child_failure')
    value = parse(raw[:-1], MAX_OUTPUT); require(canonical(value) + b'\n' == raw and type(value) is dict
        and set(value) == {'binding', 'result', 'report_pin'} and value['binding'] == binding(args), 'output')
    validate_result(value['result'])
    require(value['report_pin'] == pin(canonical({'binding': binding(args), 'result': value['result']})), 'output')
    return value

def validate_parent_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2), 'output')
    value = parse(raw, MAX_OUTPUT)
    require(canonical(value) + b'\n' == raw, 'output')
    key = 'outcome' if actual_exit == 0 else 'failure'
    require(type(value) is dict and set(value) == {'binding', 'actual_child_exit', 'output_authenticated',
        'child_stdout_pin', 'child_stderr_byte_count', key} and value['binding'] == binding(args)
        and value['actual_child_exit'] == actual_exit and type(value['actual_child_exit']) is int
        and value['output_authenticated'] is True and type(value['child_stderr_byte_count']) is int
        and value['child_stderr_byte_count'] == 0, 'output')
    child_raw = canonical(value[key]) + b'\n'
    require(pin(child_raw) == value['child_stdout_pin'], 'output')
    if key == 'failure':
        validate_failure(value[key], args)
        return {'binding': binding(args), 'output_authenticated': True, 'accepted': False,
            'actual_child_exit': value['actual_child_exit'], 'failure': value[key]}
    validate_envelope(child_raw, value['actual_child_exit'], args)
    return {'binding': binding(args), 'output_authenticated': True, 'result': value['outcome']['result']}

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
        signal.signal(signal.SIGALRM, parent_expired)
        signal.setitimer(signal.ITIMER_REAL, budget(ENTRY_DEADLINE))
        return parent(args)
    if args.mode == 'validate':
        require(args.intent_fd is args.outer_deadline is None and type(args.actual_parent_exit) is int
            and args.actual_parent_exit in (0, 2), 'arguments')
        def validation_expired(*_): raise Refused('deadline')
        signal.signal(signal.SIGALRM, validation_expired); signal.setitimer(signal.ITIMER_REAL, 30)
        preflight(args, ENTRY_DEADLINE)
        with ExitStack() as sources:
            bootstrap('validate', sources, ENTRY_DEADLINE)
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
