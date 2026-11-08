"""One read-only status/result observation of the exact already-launched A4.

No old operational control is read. A new exclusive claim and fresh eight-DATA
guard precede existing environment credentials. All eighteen exact source hashes
precede status; only matching Completed permits one bounded aggregate read.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder
from importlib.util import spec_from_loader
import json
import math
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import time
from types import ModuleType

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH = 'codex/strategy-analyst-revisions-v2'
BASELINE = '4117c1a409cb4a2c2a71c06397b40238804a5962'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
SOURCE = ROOT / 'scripts/read_arv2_r348_ar100_result.py'
PLAN = ROOT / 'scripts/arv2_r348_ar100_result_plan.json'
PARENT_PLAN = ROOT / 'scripts/arv2_r347_legacy_six_plan_a4.json'
PARENT_PLAN_PIN = {'byte_count':28396,'sha256':'66f305b15fcf9cfef0a4ad4b5d6b74d376384384bf540f4cd980b746c9369243'}
SUPPORT = ROOT / '.pytest_cache/r348-ar100-result'
CONTROL_PARENT = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_results'
SCHEMA = 'arv2-r348-ar100-status-result-v1'
PLAN_SCHEMA = 'arv2-r348-ar100-result-plan-v1'
CANDIDATES = ('R343-AR100',)
PROJECT = 39054561
RUNNING_FACT = ROOT / 'scripts/arv2_r347_a4_running_fact.json'
RUNNING_FACT_PIN = {'byte_count':12469,'sha256':'992caae1f839b7228d65e0aed3d320b9d210d250d889755eb855cdbce5553278'}
VALIDATOR_PATH = 'scripts/arv2_r348_legacy_result.py'
CONSUMER_PATH = 'scripts/arv2_r348_plain_submission_data.py'
PREPARATION_FACT = ROOT / 'scripts/arv2_r346_preparation_result_fact.json'
DATA_DIRECTORY = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_plain/R346-20261107-A'
DATA_NAMES = ('evaluator-manifest.json','session_axis-0000.jsonl','memberships-0000.jsonl',
    'contributions-0000.jsonl','runtime_symbol_bindings-0000.jsonl','transport-manifest.json',
    'source-proposal.json','report.json')
TRANSPORT_PATH = 'scripts/arv2_r345_qc_error_transport_v3.py'
FIXED_ADDITIONAL_PINS = {
    RUNNING_FACT.relative_to(ROOT).as_posix(): RUNNING_FACT_PIN,
}
SECONDS, MAX_PUBLIC, MAX_PLAN, MAX_JOURNAL = 180, 2 * 1024 * 1024, 256 * 1024, 8 * 1024 * 1024
MAX_OUTPUT, MAX_EVENTS = 64 * 1024, 4096
BACKTEST = '007d4ab27c26d337ae53acb492a83410'
COMPILE = '251b7dbcc94a6db5740a3b83a83ec133-232313c1c0b6b9f62aae03cca921fd2f'
PROJECT_NAME = 'ARV2 LEGACY SIX R343-AR100 OCT2026'
BACKTEST_NAME = PROJECT_NAME + ' A4'
CODE_SOURCE = 'Codex R347 R343-AR100 A4'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
OWNER_ROWS_PIN = {'byte_count':266,'sha256':'17629cbf0728da4646158efdc2251d502b969c112d962231105fe8b6b11c80af'}
SOURCE_VECTOR_PIN = {'byte_count':2775,'sha256':'71857bac63298b6b9dd4221ffc180ca4a59f10574edd109220a335d9370a232c'}
SOURCE_BYTE_TOTAL = 417652
INPUT_IDENTITY_PIN = {'byte_count':1061,'sha256':'bb336fdf1ed1388d32922bc25f0bc719ed9407d03604d46f5cf1ea86739ae8b8'}
SOURCE_PROFILE_PIN = {'byte_count':4178,'sha256':'c8ecb6ba6feae4dddb1eb9c7d36c9c3d74c99e95d603f699687f970eb5b115d0'}
STATISTICS = ('ARV2_SIX_GATE_ORDER_META','ARV2_SIX_GATE_ORDER_AGGREGATES',
    'ARV2_SIX_GATE_ORDER_DIAGNOSTICS','ARV2_R343_LEGACY_SIX_PERIODS')
PAYLOAD_KEYS = {'authenticate':set(),'projects/read':{'projectId'},
    'projects/collaboration/read':{'projectId'},'files/read':{'projectId'},
    'backtests/list':{'projectId','includeStatistics'},'backtests/read':{'projectId','backtestId'}}
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
CREDENTIALS = ('QC_USER_ID', 'QC_API_TOKEN')
STAGE, CLAIM, LAST_FAILURE = 'preflight', 'unallocated', None
RESULT_READ_DISPATCHED = RESULT_READ_RESPONSE_RECEIVED = SELECTED_RESULT_READ = False
FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('arguments', 'environment', 'git', 'plan', 'source_pin', 'source_changed',
    'inventory', 'claim_spent', 'control', 'deadline', 'data', 'credentials', 'access', 'capacity',
    'object_admission', 'request', 'operation', 'compile', 'launch', 'output', 'close', 'unknown',
    'project','collaborators','source','status','runtime_error','not_completed','statistics','semantic','running_fact'))


class Refused(ValueError):
    pass


class Deadline(BaseException):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise Refused('output') from None


def pin(raw):
    return {'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def loads(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'plan')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'plan')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('plan')))
        require(canonical(value) == raw, 'plan')
        return value
    except Refused:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('plan') from None


def valid_pin(value, maximum):
    return type(value) is dict and set(value) == {'byte_count', 'sha256'} and type(value['byte_count']) is int \
        and 0 <= value['byte_count'] <= maximum and type(value['sha256']) is str \
        and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None


def budget(deadline):
    left = deadline - time.monotonic()
    require(type(deadline) in (int, float) and math.isfinite(left) and 0 < left <= SECONDS, 'deadline')
    return left


def metadata(info):
    result = tuple(getattr(info, name, None) for name in FIELDS)
    require(all(type(item) is int and item >= 0 for item in result), 'source_changed')
    return result


def control(candidate):
    require(candidate in CANDIDATES, 'arguments')
    return CONTROL_PARENT / 'R348-20261107-AR100-RESULT-A'


def safe_env():
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(SUPPORT), 'XDG_CACHE_HOME': str(SUPPORT / 'cache'),
        'SQLITE_TMPDIR': str(SUPPORT), 'PYTHONPYCACHEPREFIX': str(SUPPORT / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'GIT_OPTIONAL_LOCKS': '0'}


def native_profile(candidate):
    own = control(candidate)
    value = '(version 1)(allow default)(deny network-bind)(deny network-inbound)'
    value += '(deny network-outbound (require-all (require-not (remote tcp "*:443"))(require-not (remote tcp "*:53"))(require-not (remote udp "*:53"))(require-not (literal "/private/var/run/mDNSResponder"))))'
    for path in ('/Volumes', '/Users/sheltonchen/Library/Keychains', '/Library/Keychains'):
        value += '(deny file-read* file-write* (subpath ' + json.dumps(path) + '))'
    value += '(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value += '(deny file-write* (require-all (require-not (subpath ' + json.dumps(str(own)) + '))'
    value += '(require-not (literal ' + json.dumps(str(CONTROL_PARENT)) + '))'
    value += '(require-not (subpath ' + json.dumps(str(SUPPORT)) + '))(require-not (literal "/dev/null"))))'
    data_paths = tuple(DATA_DIRECTORY / name for name in DATA_NAMES)
    ancestors = {path for leaf in (*data_paths,own) for path in leaf.parents
        if path == ROOT / 'artifacts' or ROOT / 'artifacts' in path.parents}
    value += '(deny file-read* (require-all (subpath ' + json.dumps(str(ROOT / 'artifacts')) + ')'
    value += ''.join('(require-not (literal ' + json.dumps(str(path)) + '))' for path in data_paths)
    value += '(require-not (subpath ' + json.dumps(str(own)) + '))'
    value += ''.join('(require-not (literal ' + json.dumps(str(path)) + '))' for path in sorted(ancestors)) + '))'
    return value


def profile_record(candidate):
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': PYTHON,
        'candidate_id': candidate, 'attempt': 4, 'control': str(control(candidate)),
        'project_id': PROJECT,'compile_id':COMPILE,'backtest_id':BACKTEST,'backtest_name':BACKTEST_NAME,
        'running_fact_pin':dict(RUNNING_FACT_PIN),'parent_plan_pin':dict(PARENT_PLAN_PIN),
        'scope':'new_readonly_exact_A4_status_and_Completed_bounded_aggregate_only',
        'prior_attempts_consumed':4,'other_candidates_permitted':False,
        'private_DATA_policy':'exact_fresh_eight_externally_pinned_preparation_leaves_no_old_control',
        'old_controls_read':False,'plan': str(PLAN), 'seconds': SECONDS,
        'native_policy_sha256': pin(native_profile(candidate).encode())['sha256'],
        'credential_policy':'existing_environment_after_new_exclusive_fsynced_claim_and_fresh_eight_DATA_normal_return',
        'current_source_policy':'exact_eighteen_plain_source_vector_before_status_and_result',
        'current_access_policy':'dedicated_pinned_owner_only_plus_zero_or_one_exact_A4_uid_null_technical_row',
        'source_policy': 'all_selected_bytes_held_compiled_full_metadata_empty_ACL_all_observed_public_xattrs',
        'error_observation': 'new_bounded_response_and_context_redacted_error_projection_before_discard_no_raw_retention',
        'failed_HTTP_body': 'new_bounded_identity_encoded_JSON_only_non200_max64KiB_never_arbitrary_download',
        'max_output_bytes': MAX_OUTPUT, 'max_failure_evidence_bytes': 48 * 1024,
        'max_API_diagnostic_bytes': 24 * 1024,
        'terminal':'one_statistics_disabled_status_read_pending_or_runtime_refuses_no_retry_only_Completed_one_result',
        'maximum_application_requests':6,'result_statistics':list(STATISTICS),
        'no_logs_charts_orders_provider_rows_persisted':True,
        'result_body_qualification':'bounded_full_backtests_read_JSON_is_ephemerally_parsed_only_four_custom_strings_retained',
        'deadline_qualification': 'cannot_bound_uninterruptible_IO_or_host_suspension', **FLAGS}


def binding(args):
    require(args.candidate in CANDIDATES and type(args.expected_head) is str
        and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{64}', getattr(args, key))
            for key in ('caller_sha256', 'plan_sha256')), 'arguments')
    return {'schema': SCHEMA, 'candidate_id': args.candidate, 'attempt': 4,
        'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'plan_sha256': args.plan_sha256, 'profile_sha256': pin(canonical(profile_record(args.candidate)))['sha256']}


def preflight(args, deadline):
    bound = binding(args)
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin'
        and os.name == 'posix' and sys.version_info[:2] == (3, 13) and sys.executable == PYTHON
        and sys.flags.isolated == 1 and sys.dont_write_bytecode and Path(__file__).absolute() == SOURCE, 'environment')
    safe = safe_env()
    require(set(os.environ) <= set(safe) | set(CREDENTIALS) | {'__CF_USER_TEXT_ENCODING'}
        and all(os.environ.get(key) == value for key, value in safe.items())
        and ('__CF_USER_TEXT_ENCODING' not in os.environ
            or os.environ['__CF_USER_TEXT_ENCODING'] == f'0x{os.getuid():X}:0x0:0x0'), 'environment')
    for key in ('TMPDIR', 'XDG_CACHE_HOME', 'SQLITE_TMPDIR', 'PYTHONPYCACHEPREFIX'):
        path = Path(safe[key]); require(path.is_dir() and path.resolve() == path, 'environment')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], BRANCH),
            (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        result = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=safe, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(15, budget(deadline)), check=False)
        require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 262144
            and result.stdout.decode('ascii').strip() == expected, 'git')
    return bound


class Sources:
    """Selected code/JSON held through the operation and executed from buffers."""
    def __init__(self, args, deadline):
        self.args, self.deadline, self.rows, self.cache, self.raws = args, deadline, [], {}, {}
        self.finder = self.security = self.public_security = None

    def hold(self, path, expected):
        require(valid_pin(expected, MAX_PUBLIC), 'source_pin')
        if not self.cache:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.cache[Path('/')] = (fd, fd, '.', metadata(os.fstat(fd)))
        row = self.cache[Path('/')]
        current = Path('/')
        for part in path.parts[1:-1]:
            budget(self.deadline); current /= part
            if current not in self.cache:
                before = metadata(os.stat(part, dir_fd=row[0], follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=row[0])
                self.cache[current] = (fd, row[0], part, before)
                require(stat.S_ISDIR(before[2]) and metadata(os.fstat(fd)) == before, 'source_changed')
            row = self.cache[current]
        before = metadata(os.stat(path.name, dir_fd=row[0], follow_symlinks=False))
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=row[0])
        item = [fd, row[0], path.name, before, expected, None]
        self.rows.append(item)
        require(stat.S_ISREG(before[2]) and before[3] == os.getuid() and before[5] == 1
            and stat.S_IMODE(before[2]) in (0o600, 0o644) and metadata(os.fstat(fd)) == before, 'source_pin')
        raw = os.pread(fd, MAX_PUBLIC + 1, 0)
        require(pin(raw) == expected and before[6] == len(raw), 'source_pin')
        return raw

    def __enter__(self):
        try:
            self.hold(SOURCE, {'byte_count': SOURCE.stat().st_size, 'sha256': self.args.caller_sha256})
            raw = self.hold(PLAN, {'byte_count': PLAN.stat().st_size, 'sha256': self.args.plan_sha256})
            require(len(raw) <= MAX_PLAN, 'plan')
            self.plan = loads(raw, MAX_PLAN)
            require(type(self.plan) is dict and set(self.plan) == {'schema','candidate_id','attempt','project_id',
                'parent_plan_pin','running_fact_pin','source_pins','additional_pins'}
                and self.plan['schema'] == PLAN_SCHEMA and self.plan['candidate_id']=='R343-AR100'
                and type(self.plan['attempt']) is int and self.plan['attempt']==4
                and type(self.plan['project_id']) is int and self.plan['project_id']==PROJECT
                and self.plan['parent_plan_pin']==PARENT_PLAN_PIN
                and self.plan['running_fact_pin']==RUNNING_FACT_PIN
                and type(self.plan['source_pins']) is dict and len(self.plan['source_pins'])<=300
                and type(self.plan['additional_pins']) is dict, 'plan')
            parent = loads(self.hold(PARENT_PLAN,PARENT_PLAN_PIN),MAX_PLAN)
            require(type(parent) is dict and type(parent.get('source_pins')) is dict
                and len(parent['source_pins'])==176, 'plan')
            additional=self.plan['additional_pins']
            require({CONSUMER_PATH,VALIDATOR_PATH,*FIXED_ADDITIONAL_PINS}<=set(additional)
                and not set(additional)&set(parent['source_pins'])
                and set(self.plan['source_pins'])==set(parent['source_pins'])|set(additional)
                and all(self.plan['source_pins'].get(key)==value for key,value in parent['source_pins'].items())
                and all(self.plan['source_pins'].get(key)==value for key,value in additional.items())
                and all(self.plan['source_pins'].get(key)==value for key,value in FIXED_ADDITIONAL_PINS.items()), 'inventory')
            soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            require(soft == resource.RLIM_INFINITY or soft >= len(self.plan['source_pins']) + 180, 'environment')
            for relative, expected in sorted(self.plan['source_pins'].items()):
                require(type(relative) is str and not relative.startswith('/') and '..' not in Path(relative).parts
                    and relative.endswith(('.py', '.json')) and 'artifacts' not in Path(relative).parts
                    and relative != PLAN.relative_to(ROOT).as_posix(), 'plan')
                self.raws[relative] = self.hold(ROOT / relative, expected)
                if relative in additional and relative not in (CONSUMER_PATH,VALIDATOR_PATH):
                    baseline=subprocess.run(['/usr/bin/git','show',BASELINE+':'+relative],cwd=ROOT,
                        env=safe_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        timeout=min(15,budget(self.deadline)),check=False)
                    require(baseline.returncode==0 and not baseline.stderr
                        and len(baseline.stdout)<=MAX_PUBLIC and pin(baseline.stdout)==expected,'source_pin')
            for required in ('scripts/arv2_relocation_security.py', 'scripts/prepare_arv2_r343_legacy_six.py',
                    'scripts/arv2_r343_legacy_six_source_pins.json',CONSUMER_PATH,VALIDATOR_PATH,TRANSPORT_PATH,
                    'scripts/arv2_r298_qc_error_text.py','scripts/arv2_r298_qc_response_evidence.py',
                    *FIXED_ADDITIONAL_PINS):
                require(required in self.raws, 'inventory')
            original = loads(self.raws['scripts/arv2_r343_legacy_six_source_pins.json'], MAX_PUBLIC)
            require(type(original) is dict and type(original.get('files')) is dict
                and all(self.plan['source_pins'].get(key) == expected for key, expected in original['files'].items()), 'inventory')
            helper = ModuleType('_r345_public_source_helpers')
            exec(compile(self.raws['scripts/prepare_arv2_r343_legacy_six.py'],
                str(ROOT / 'scripts/prepare_arv2_r343_legacy_six.py'), 'exec'), helper.__dict__)
            security_module = ModuleType('_r345_exact_security')
            exec(compile(self.raws['scripts/arv2_relocation_security.py'],
                str(ROOT / 'scripts/arv2_relocation_security.py'), 'exec'), security_module.__dict__)
            self.security, self.public_security = security_module, helper.public_source_security
            for item in self.rows:
                item[5] = self.public_security(item[0], self.security)
            names = {key[:-3].replace('/', '.').removesuffix('.__init__'): key
                for key in self.raws if key.endswith('.py')}
            require('scripts' not in sys.modules and not any(name in sys.modules for name in names), 'environment')
            raws = self.raws
            class ExactLoader(Loader):
                def __init__(self, relative): self.relative = relative
                def create_module(self, spec): return None
                def exec_module(self, module):
                    module.__file__ = str(ROOT / self.relative)
                    if self.relative.endswith('/__init__.py'):
                        module.__path__ = [str((ROOT / self.relative).parent)]
                    exec(compile(raws[self.relative], module.__file__, 'exec'), module.__dict__)
            class ExactFinder(MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == 'scripts':
                        result = ModuleSpec(fullname, loader=None, is_package=True)
                        result.submodule_search_locations = [str(ROOT / 'scripts')]
                        return result
                    if fullname in names:
                        relative = names[fullname]
                        return spec_from_loader(fullname, ExactLoader(relative), origin=str(ROOT / relative),
                            is_package=relative.endswith('/__init__.py'))
                    found = PathFinder.find_spec(fullname, path)
                    origin = None if found is None else found.origin
                    require(not (type(origin) is str and Path(origin).is_absolute()
                        and Path(origin).is_relative_to(ROOT)), 'source_pin')
                    return None
            self.finder = ExactFinder(); sys.meta_path.insert(0, self.finder)
            self.consumer = importlib.import_module(CONSUMER_PATH[:-3].replace('/','.'))
            self.validator = importlib.import_module(VALIDATOR_PATH[:-3].replace('/','.'))
            self.preparation_fact_bytes=self.raws[PREPARATION_FACT.relative_to(ROOT).as_posix()]
            self.consumer.parse_fact(self.preparation_fact_bytes)
            raw_fact=self.raws[RUNNING_FACT.relative_to(ROOT).as_posix()]
            require(raw_fact.endswith(b'\n'),'plan')
            self.running_fact=loads(raw_fact[:-1],MAX_PLAN)
            validate_running_fact(self.running_fact)
            self.transport = importlib.import_module(TRANSPORT_PATH[:-3].replace('/','.'))
            self.verify()
            return self
        except BaseException:
            self.close(); raise

    def verify(self):
        for fd, parent, name, before in self.cache.values():
            budget(self.deadline)
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'source_changed')
        for fd, parent, name, before, expected, native in self.rows:
            budget(self.deadline)
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and pin(os.pread(fd, MAX_PUBLIC + 1, 0)) == expected, 'source_changed')
            if native is not None:
                require(self.public_security(fd, self.security) == native, 'source_changed')

    def close(self):
        if self.finder in sys.meta_path:
            sys.meta_path.remove(self.finder)
        failed = False
        for fd in [item[0] for item in reversed(self.rows)] + [row[0] for row in reversed(tuple(self.cache.values()))]:
            try: os.close(fd)
            except OSError: failed = True
        self.rows.clear(); self.cache.clear()
        require(not failed, 'close')

    def __exit__(self, *_):
        try: self.verify()
        finally: self.close()


class Store:
    """Exclusive original-FD claim, append-only fsynced journal and final output."""
    def __init__(self, path, security_module):
        self.path, self.security = path, security_module
        self.chain, self.leaves, self.events = [], [], bytearray()
        self.fd = self.journal_fd = None
        self.application_dispatch_count = self.intents = self.event_count = 0
    def __enter__(self):
        global CLAIM
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.chain.append([parent, parent, '.', metadata(os.fstat(parent)), None])
            path = Path('/')
            for part in self.path.parts[1:]:
                path /= part
                if path in (self.path.parent, self.path):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent); os.fsync(parent)
                        if path == self.path: CLAIM = 'allocated_unknown'
                        old = self.chain[-1]; after = metadata(os.fstat(parent))
                        require(all(after[i] == old[3][i] for i in (0, 1, 2, 3, 4, 9)), 'control')
                        old[3] = after
                    except FileExistsError:
                        require(path != self.path, 'claim_spent')
                before = metadata(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                checked = path == ROOT or ROOT in path.parents
                require(stat.S_ISDIR(before[2]) and metadata(os.fstat(fd)) == before
                    and (not checked or before[3] == os.getuid() and stat.S_IMODE(before[2]) == (0o755 if path == ROOT else 0o700)), 'control')
                self.chain.append([fd, parent, part, before, self.security.snapshot(fd) if checked else None])
                parent = fd
            self.fd = parent; self.verify(); return self
        except BaseException:
            self.close(); raise
    def verify(self):
        require(self.fd is not None and set(os.listdir(self.fd)) == {item[0] for item in self.leaves}, 'control')
        for fd, parent, name, before, native in self.chain:
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and (native is None or self.security.snapshot(fd) == native), 'control')
        for name, fd, before, native, raw in self.leaves:
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and self.security.snapshot(fd) == native and os.pread(fd, len(raw) + 1, 0) == raw, 'control')
    def write(self, name, value):
        global CLAIM
        require(name in ('claim.json', 'events.jsonl', 'report.json', 'failure.json'), 'output')
        raw = canonical(value) if name != 'events.jsonl' else value
        require(type(raw) is bytes and len(raw) <= MAX_JOURNAL, 'output')
        self.verify(); before = self.chain[-1][3]
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            require(not raw or os.write(fd, raw) == len(raw), 'output'); os.fsync(fd)
            info = metadata(os.fstat(fd)); secure = self.security.snapshot(fd)
            require(stat.S_ISREG(info[2]) and info[3] == os.getuid() and info[5] == 1
                and stat.S_IMODE(info[2]) == 0o600, 'control')
            self.leaves.append([name, fd, info, secure, raw]); fd = None
            after = metadata(os.fstat(self.fd))
            require(all(after[i] == before[i] for i in (0, 1, 2, 3, 4, 9)), 'control')
            self.chain[-1][3] = after; os.fsync(self.fd); self.verify()
            if name == 'claim.json': CLAIM = 'consumed'
            if name == 'events.jsonl': self.journal_fd = self.leaves[-1][1]
            return pin(raw)
        finally:
            if fd is not None: os.close(fd)
    def journal(self, marker, value):
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,120}', marker)
            and self.journal_fd is not None and self.event_count < MAX_EVENTS, 'output')
        raw = canonical({'ordinal': self.event_count, 'marker': marker, 'value': value}) + b'\n'
        require(len(raw) <= 32768 and len(self.events) + len(raw) <= MAX_JOURNAL, 'output')
        self.verify()
        row = next(item for item in self.leaves if item[0] == 'events.jsonl')
        before = row[2]
        require(os.lseek(self.journal_fd, 0, os.SEEK_END) == len(self.events)
            and os.write(self.journal_fd, raw) == len(raw), 'output')
        os.fsync(self.journal_fd); after = metadata(os.fstat(self.journal_fd))
        require(all(after[i] == before[i] for i in (0, 1, 2, 3, 4, 5, 9)), 'control')
        self.events.extend(raw); row[2], row[4] = after, bytes(self.events)
        self.event_count += 1; self.verify()
    def intent(self, endpoint, project_id):
        self.journal('http-intent', {'endpoint': endpoint, 'project_id': project_id, 'ordinal': self.intents})
        self.intents += 1
    def attempt(self, endpoint, project_id):
        global RESULT_READ_DISPATCHED
        require(endpoint in PAYLOAD_KEYS and self.application_dispatch_count < self.intents
            and (project_id is None if endpoint=='authenticate' else type(project_id) is int and project_id==PROJECT)
            and self.application_dispatch_count<6, 'request')
        self.journal('http-dispatch', {'endpoint': endpoint, 'project_id': project_id, 'ordinal': self.application_dispatch_count})
        self.application_dispatch_count += 1
        if endpoint=='backtests/read':RESULT_READ_DISPATCHED=True
    def close(self):
        failed = False
        for fd in [row[1] for row in reversed(self.leaves)] + [row[0] for row in reversed(self.chain)]:
            try: os.close(fd)
            except OSError: failed = True
        self.leaves.clear(); self.chain.clear(); self.fd = self.journal_fd = None
        require(not failed, 'close')
    def __exit__(self, *_):
        try: self.verify()
        finally: self.close()


def validate_running_fact(value):
    require(type(value) is dict and value.get('schema')=='arv2-r347-A4-running-result-fact-v1'
        and type(value.get('external_observation')) is dict
        and type(value['external_observation'].get('actual_exit')) is int
        and value['external_observation']['actual_exit']==0
        and value['external_observation'].get('original_stdout_validated') is True,'running_fact')
    record=value.get('original_result',{}).get('result',{})
    receipt=record.get('launch_receipt')
    require(type(record) is dict and record.get('observed_status')=='In Progress...'
        and record.get('running_observed') is True and record.get('terminal_identity_observed') is False
        and receipt=={'candidate_id':'R343-AR100','attempt':4,'project_id':PROJECT,
            'compile_id':COMPILE,'backtest_id':BACKTEST,'backtest_name':BACKTEST_NAME},'running_fact')
    return receipt


def scoped(packet):
    require(type(packet) is dict and packet.get('success') is True
        and ('errors' not in packet or type(packet['errors']) is list and not packet['errors'])
        and ('projectId' not in packet or type(packet['projectId']) is int and packet['projectId']==PROJECT),'request')
    return packet


def access_probe(project_packet,dedicated_packet,user_id):
    rows=project_packet.get('projects') if type(project_packet) is dict else None
    row=rows[0] if type(rows) is list and len(rows)==1 and type(rows[0]) is dict else {}
    general=row.get('collaborators');dedicated=dedicated_packet.get('collaborators') if type(dedicated_packet) is dict else None
    def bounded_pin(value):
        return pin(canonical(value)) if type(value) is list and len(value)<=8 and len(canonical(value))<=65536 else None
    extras=[item for item in general if type(item) is dict and item.get('owner') is not True] if type(general) is list and len(general)<=8 else []
    return {'general_count':len(general) if type(general) is list and len(general)<=8 else None,
        'dedicated_count':len(dedicated) if type(dedicated) is list and len(dedicated)<=8 else None,
        'general_rows_pin':bounded_pin(general),'dedicated_rows_pin':bounded_pin(dedicated),
        'extra_row_pins':[pin(canonical(item)) for item in extras if len(canonical(item))<=65536],
        'extra_rows_match_A4_name':[item.get('name')==CODE_SOURCE for item in extras],
        'editor_running':row.get('codeRunning') if type(row.get('codeRunning')) is bool else None,
        'private_field_present_and_false':'public' in row and row['public'] is False,
        'general_collaborators_authorize_mutation':False}


def validate_access(project_packet,dedicated_packet,user_id):
    rows=scoped(project_packet).get('projects');dedicated=scoped(dedicated_packet)
    require(type(rows) is list and len(rows)==1 and type(rows[0]) is dict,'project')
    row=rows[0];organization=row.get('organizationId')
    require(type(row.get('projectId')) is int and row['projectId']==PROJECT
        and row.get('name')==PROJECT_NAME and row.get('language')=='Py'
        and row.get('owner') is True and type(row.get('ownerId')) is int and row['ownerId']==user_id
        and type(organization) is str and re.fullmatch('[0-9a-f]{32}',organization)
        and pin(organization.encode('ascii'))['sha256']==ORGANIZATION_SHA256,'project')
    require(type(row.get('codeRunning')) is bool and ('public' not in row or row['public'] is False)
        and type(row.get('libraries')) is list and not row['libraries']
        and ('isLibrary' not in row or row['isLibrary'] is False)
        and ('libraryIds' not in row or type(row['libraryIds']) is list and not row['libraryIds'])
        and 'lastLiveDeployment' in row and row['lastLiveDeployment'] in (None,'')
        and type(row.get('leanEnvironment')) is int and row['leanEnvironment']>=0
        and all(name not in row or row[name] is False for name in ('liveMode','liveRunning','live'))
        and ('liveResults' not in row or type(row['liveResults']) is list and not row['liveResults']),'project')
    require('organizationId' not in dedicated or dedicated['organizationId']==organization,'collaborators')
    owner_rows=dedicated.get('collaborators');general=row.get('collaborators')
    require(type(owner_rows) is list and pin(canonical(owner_rows))==OWNER_ROWS_PIN
        and len(owner_rows)==1 and type(owner_rows[0]) is dict
        and owner_rows[0].get('owner') is True and type(owner_rows[0].get('uid')) is int
        and owner_rows[0]['uid']==user_id and owner_rows[0].get('permission')=='write'
        and owner_rows[0].get('liveControl') is True and dedicated.get('userPermissions')=='write'
        and dedicated.get('userLiveControl') is True and type(general) is list and 1<=len(general)<=2
        and all(type(item) is dict for item in general),'collaborators')
    owners=[item for item in general if item.get('owner') is True]
    require(len(owners)==1 and canonical(owners[0])==canonical(owner_rows[0]),'collaborators')
    extras=[item for item in general if item is not owners[0]]
    if extras:
        extra=extras[0]
        require(set(extra)=={'uid','owner','name','publicId','permission','liveControl','profileImage','email','bio'}
            and extra['uid'] is None and extra['owner'] is False and extra['name']==CODE_SOURCE
            and extra['permission']=='write' and extra['liveControl'] is True
            and type(extra['publicId']) is str and 0<len(extra['publicId'])<=1024
            and all(type(extra[key]) is str and len(extra[key])<=65536 for key in ('profileImage','email','bio'))
            and len(canonical(extra))<=65536,'collaborators')
    return access_probe(project_packet,dedicated_packet,user_id)


def validate_sources(packet,candidate_record):
    rows=scoped(packet).get('files');expected={name:text for name,text in candidate_record['source_pairs']}
    require(len(expected)==18 and type(rows) is list and len(rows)==18,'source')
    observed={}
    for row in rows:
        require(type(row) is dict and type(row.get('projectId')) is int and row['projectId']==PROJECT
            and type(row.get('name')) is str and row['name'] in expected and row['name'] not in observed
            and type(row.get('content')) is str and row['content'].isascii() and 0<len(row['content'])<=64000,'source')
        observed[row['name']]=row['content']
        require(row['content']==expected[row['name']],'source')
    vector=[{'project_path':name,**pin(observed[name].encode('ascii'))} for name in sorted(observed)]
    require(pin(canonical(vector))==SOURCE_VECTOR_PIN
        and sum(item['byte_count'] for item in vector)==SOURCE_BYTE_TOTAL,'source')
    return {'file_count':18,'source_byte_total':SOURCE_BYTE_TOTAL,'source_inventory_pin':pin(canonical(vector))}


def status_row(packet):
    rows=scoped(packet).get('backtests')
    require(type(rows) is list and len(rows)==1
        and ('count' not in packet or type(packet['count']) is int and packet['count']==1),'status')
    row=rows[0]
    require(type(row) is dict and row.get('backtestId')==BACKTEST and row.get('name')==BACKTEST_NAME
        and ('projectId' not in row or type(row['projectId']) is int and row['projectId']==PROJECT)
        and ('compileId' not in row or row['compileId']==COMPILE)
        and row.get('status') in ('In Queue...','In Progress...','Completed.','Runtime Error'),'status')
    require('statistics' not in row or row['statistics'] in (None,{}),'status')
    return row['status']


def selected_statistics(packet):
    row=scoped(packet).get('backtest')
    require(type(row) is dict and type(row.get('projectId')) is int and row['projectId']==PROJECT
        and row.get('backtestId')==BACKTEST and row.get('name')==BACKTEST_NAME and row.get('status')=='Completed.'
        and ('compileId' not in row or row['compileId']==COMPILE),'statistics')
    statistics=row.get('statistics');require(type(statistics) is dict and all(type(key) is str for key in statistics),'statistics')
    names={name for name in statistics if name.startswith('ARV2_')}
    require(names in (set(STATISTICS[:3]),set(STATISTICS)),'statistics')
    retained={}
    for name in sorted(names):
        text=statistics[name];maximum=16384 if name.endswith('DIAGNOSTICS') else 8192
        require(type(text) is str and text.isascii() and 0<len(text)<=maximum,'statistics')
        loads(text.encode('ascii'),maximum)
        retained[name]=text
    return retained


def operate(submission,*,validator,api,secret,store,deadline,state):
    global STAGE,RESULT_READ_DISPATCHED,RESULT_READ_RESPONSE_RECEIVED,SELECTED_RESULT_READ
    # Candidate and axis come only from the fresh DATA guard's normal return.
    candidates=[item for item in submission.candidates if item.candidate_id=='R343-AR100']
    require(len(candidates)==1,'data');candidate=candidates[0].cell_record()
    dispatched=set()
    def request(endpoint,payload):
        budget(deadline)
        require(endpoint in PAYLOAD_KEYS and type(payload) is dict and set(payload)==PAYLOAD_KEYS[endpoint]
            and endpoint not in dispatched,'request')
        if 'projectId' in payload:require(type(payload['projectId']) is int and payload['projectId']==PROJECT,'request')
        if endpoint=='backtests/list':require(payload['includeStatistics'] is False,'request')
        if endpoint=='backtests/read':require(payload['backtestId']==BACKTEST and state.get('observed_status')=='Completed.','request')
        dispatched.add(endpoint);state['last_request']={'endpoint':endpoint,'payload_sha256':pin(canonical(payload))['sha256']}
        api.deadline=min(deadline,time.monotonic()+89)
        return api._exchange(endpoint,payload)
    STAGE='access';request('authenticate',{})
    project=request('projects/read',{'projectId':PROJECT})
    dedicated=request('projects/collaboration/read',{'projectId':PROJECT})
    state['last_access_observation']=access_probe(project,dedicated,int(secret['QC_USER_ID']))
    access=validate_access(project,dedicated,int(secret['QC_USER_ID']))
    STAGE='source'
    source=validate_sources(request('files/read',{'projectId':PROJECT}),candidate)
    state['source_observation']=source
    STAGE='status'
    status=status_row(request('backtests/list',{'projectId':PROJECT,'includeStatistics':False}))
    state['observed_status']=status
    store.journal('known-A4-status',{'project_id':PROJECT,'backtest_id':BACKTEST,'status':status})
    require(status!='Runtime Error','runtime_error');require(status=='Completed.','not_completed')
    STAGE='statistics'
    packet=request('backtests/read',{'projectId':PROJECT,'backtestId':BACKTEST})
    RESULT_READ_RESPONSE_RECEIVED=True;state['result_read_response_received']=True
    statistics=selected_statistics(packet)
    SELECTED_RESULT_READ=True;state['selected_result_read']=True
    # Retain exact bounded original strings before semantics, including invalid
    # legacy runs which deliberately do not emit the fourth period statistic.
    for index,name in enumerate(sorted(statistics)):
        store.journal('selected-original-statistic-'+str(index),{'name':name,'text':statistics[name]})
    state['statistics_pin']=pin(canonical(statistics))
    STAGE='semantic'
    validation=validator.validate_statistics(statistics,candidate_record=candidate,
        evaluation_sessions=submission.evaluation_sessions)
    require(type(validation) is dict and len(canonical(validation))<=16384,'semantic')
    state['semantic_observation']=loads(canonical(validation),16384)
    require(validation.get('accepted') is True and validation.get('run_valid') is True,'semantic')
    return {'candidate_id':'R343-AR100','attempt':4,'project_id':PROJECT,'compile_id':COMPILE,
        'backtest_id':BACKTEST,'backtest_name':BACKTEST_NAME,'observed_status':status,
        'source':source,'access':access,'statistics':statistics,'statistics_pin':state['statistics_pin'],
        'DATA_guard_returned':True,'input_source_identity':loads(submission.source_identity_json,MAX_OUTPUT),
        'semantic_validation':validation,'application_dispatch_count':store.application_dispatch_count,
        'result_read':True,'selected_result_read':True,'point_in_time_proven':False,'formal_identity_admitted':False,
        'formal_forward_ready':False,'paper_or_live_ready':False,
        'look_accounting':{'shared_look_delta':0,'development_look_delta':0,'infrastructure_look_delta':0,
            'accepted_result_cell_delta':0,'physical_request_count_measured':False},
        'result_body_qualification':'bounded_full_response_parsed_ephemerally_only_selected_custom_statistics_retained'}


def run(args):
    global STAGE,LAST_FAILURE
    deadline=time.monotonic()+SECONDS;bound=preflight(args,deadline)
    with Sources(args,deadline) as sources:
        with Store(control(args.candidate),sources.security) as store:
            store.write('claim.json',{'binding':bound,'profile':profile_record(args.candidate),
                'consumed_at':datetime.now(timezone.utc).isoformat()})
            store.write('events.jsonl',b'')
            state={'api':None,'last_request':None,'store':store}
            api=None
            try:
                STAGE='data'
                with sources.consumer.FreshAllPlainSubmission(fact_bytes=sources.preparation_fact_bytes,
                        deadline=min(deadline,time.monotonic()+179)) as held:
                    submission=held.value
                state['DATA_guard_returned']=True
                STAGE='credentials'
                secret=sources.transport.credentials({key:os.environ.get(key) for key in CREDENTIALS})
                api=sources.transport.API(secret,store,min(deadline,time.monotonic()+89));state['api']=api
                result=operate(submission,validator=sources.validator,api=api,secret=secret,
                    store=store,deadline=deadline,state=state)
                result['last_api_diagnostic']=api_diagnostic(sources.transport,api)
                LAST_FAILURE=failure_evidence(state,sources,Refused('unknown'))
                api.close();api=None;sources.verify()
                report={'schema':SCHEMA+'-result','binding':bound,'attempt_consumed':True,'result':result}
                report_pin=store.write('report.json',report);store.verify()
            except BaseException as error:
                validator_error=getattr(sources.validator,'Refused',None)
                if type(error) is validator_error:
                    details=BaseException.args.__get__(error)
                    if (len(details)==1 and type(details[0]) is str
                            and details[0] in getattr(sources.validator,'FINITE',frozenset())):
                        state['semantic_failure_code']=details[0]
                LAST_FAILURE=failure_evidence(state,sources,error)
                if api is not None:api.close()
                reason=finite(error,sources)
                store.write('failure.json',{'schema':SCHEMA+'-failure','binding':bound,'stage':STAGE,
                    'failure_code':reason,'attempt_consumed':True,'evidence':LAST_FAILURE,**FLAGS})
                raise Refused(reason) from None
    STAGE='complete';LAST_FAILURE=None
    return {**report,'report_pin':report_pin}


def finite(error,sources=None):
    if isinstance(error,(Deadline,TimeoutError,subprocess.TimeoutExpired)):return 'deadline'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args)==1 and type(args[0]) is str and args[0] in FINITE:return args[0]
    if sources is not None:
        for module,code in ((sources.consumer,'data'),(sources.validator,'semantic'),(sources.transport,'request')):
            if type(error) is getattr(module,'Refused',None):return code
    return 'unknown'


def api_diagnostic(transport,api):
    validator=getattr(transport,'validate_diagnostic',None)
    if not callable(validator):return None
    try:
        result=validator(getattr(api,'last_diagnostic',None))
        if type(result) is dict and len(canonical(result))<=24*1024:return result
    except Exception:pass
    return None


def failure_evidence(state,sources,error):
    global RESULT_READ_RESPONSE_RECEIVED
    api=state.get('api');statuses=[];responses=[]
    for row in getattr(api,'statuses',()):
        if type(row) is dict and row.get('endpoint') in PAYLOAD_KEYS and type(row.get('http_status')) is int and 100<=row['http_status']<=599:
            statuses.append({'endpoint':row['endpoint'],'http_status':row['http_status']})
    for row in getattr(api,'responses',()):
        if type(row) is dict and row.get('endpoint') in PAYLOAD_KEYS and valid_pin({key:row.get(key) for key in ('byte_count','sha256')},2*1024*1024):
            responses.append({key:row[key] for key in ('endpoint','byte_count','sha256')})
    if any(row['endpoint']=='backtests/read' for row in responses):
        RESULT_READ_RESPONSE_RECEIVED=True
    last_status=getattr(api,'last_http_status',None)
    result={'known_identities':{'project_id':PROJECT,'compile_id':COMPILE,'backtest_id':BACKTEST,'attempt':4},
        'observed_status':state.get('observed_status'),'last_request':state.get('last_request'),
        'last_access_observation':state.get('last_access_observation'),
        'source_observation':state.get('source_observation'),'statistics_pin':state.get('statistics_pin'),
        'semantic_observation':state.get('semantic_observation'),
        'semantic_failure_code':state.get('semantic_failure_code'),
        'last_http_status':last_status if type(last_status) is int and 100<=last_status<=599 else None,
        'http_status_count':len(statuses),'http_status_vector_pin':pin(canonical(statuses)),
        'http_statuses':statuses,'response_pin_count':len(responses),'response_pins':responses,
        'last_api_diagnostic':api_diagnostic(sources.transport,api),
        'application_dispatch_count':state['store'].application_dispatch_count if state.get('store') is not None else 0,
        'look_delta':0,'new_launch_performed':False,'result_read_accepted':False,
        'DATA_guard_returned':state.get('DATA_guard_returned',False),
        'result_read_dispatched':RESULT_READ_DISPATCHED,
        'result_read_response_received':RESULT_READ_RESPONSE_RECEIVED,
        'selected_result_read':state.get('selected_result_read',False)}
    require(len(canonical(result))<=48*1024,'output');return result


def validate_original_stdout(raw,*,actual_exit,expected_binding):
    """Pure supplied-original bytes/exit check, not disk or QC attestation."""
    require(type(actual_exit) is int and actual_exit in (0,2),'output')
    require(type(expected_binding) is dict and set(expected_binding)=={'schema','candidate_id','attempt',
        'expected_head','caller_sha256','plan_sha256','profile_sha256'}
        and expected_binding['schema']==SCHEMA and expected_binding['candidate_id']=='R343-AR100'
        and type(expected_binding['attempt']) is int and expected_binding['attempt']==4
        and type(expected_binding['expected_head']) is str
        and re.fullmatch('[0-9a-f]{40}',expected_binding['expected_head'])
        and all(type(expected_binding[key]) is str and re.fullmatch('[0-9a-f]{64}',expected_binding[key])
            for key in ('caller_sha256','plan_sha256','profile_sha256'))
        and expected_binding['profile_sha256']==pin(canonical(profile_record('R343-AR100')))['sha256'],'output')
    require(type(raw) is bytes and 1<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n'),'output')
    value=loads(raw[:-1],MAX_OUTPUT)
    require(type(value) is dict,'output')
    def keys(record,expected):require(type(record) is dict and set(record)==set(expected),'output')
    def checked_pin(item,maximum=MAX_PUBLIC):require(valid_pin(item,maximum),'output')
    def safe_tree(item,depth=0):
        require(depth<=32,'output')
        if type(item) is dict:
            require(len(item)<=128 and all(type(key) is str and len(key)<=128 for key in item),'output')
            for child in item.values():safe_tree(child,depth+1)
        elif type(item) is list:
            require(len(item)<=4096,'output')
            for child in item:safe_tree(child,depth+1)
        elif type(item) is str:require(item.isascii() and len(item)<=24576,'output')
        elif type(item) is int:require(-(2**63)<item<2**63,'output')
        else:require(item is None or type(item) is bool,'output')
    safe_tree(value)
    if actual_exit==0:
        keys(value,('schema','binding','attempt_consumed','result','report_pin'))
        require(value['schema']==SCHEMA+'-result' and value['binding']==expected_binding
            and value['attempt_consumed'] is True,'output')
        report={key:value[key] for key in ('schema','binding','attempt_consumed','result')}
        require(value['report_pin']==pin(canonical(report)),'output')
        result=value['result']
        keys(result,('candidate_id','attempt','project_id','compile_id','backtest_id','backtest_name',
            'observed_status','source','access','statistics','statistics_pin','DATA_guard_returned',
            'input_source_identity','semantic_validation','application_dispatch_count','result_read',
            'selected_result_read','look_accounting','result_body_qualification','last_api_diagnostic',*FLAGS))
        require(result['candidate_id']=='R343-AR100' and type(result['attempt']) is int and result['attempt']==4
            and type(result['project_id']) is int and result['project_id']==PROJECT
            and result['compile_id']==COMPILE and result['backtest_id']==BACKTEST
            and result['backtest_name']==BACKTEST_NAME and result['observed_status']=='Completed.'
            and result['DATA_guard_returned'] is True and result['result_read'] is True
            and result['selected_result_read'] is True and all(result[key] is False for key in FLAGS)
            and type(result['application_dispatch_count']) is int and result['application_dispatch_count']==6
            and result['last_api_diagnostic'] is None,'output')
        require(result['source']=={'file_count':18,'source_byte_total':SOURCE_BYTE_TOTAL,
            'source_inventory_pin':SOURCE_VECTOR_PIN}
            and pin(canonical(result['input_source_identity']))==INPUT_IDENTITY_PIN,'output')
        access=result['access'];keys(access,('general_count','dedicated_count','general_rows_pin','dedicated_rows_pin',
            'extra_row_pins','extra_rows_match_A4_name','editor_running','private_field_present_and_false',
            'general_collaborators_authorize_mutation'))
        require(type(access['general_count']) is int and access['general_count'] in (1,2)
            and type(access['dedicated_count']) is int and access['dedicated_count']==1
            and access['dedicated_rows_pin']==OWNER_ROWS_PIN
            and type(access['extra_row_pins']) is list and len(access['extra_row_pins'])==access['general_count']-1
            and access['extra_rows_match_A4_name']==[True]*(access['general_count']-1)
            and type(access['editor_running']) is bool and type(access['private_field_present_and_false']) is bool
            and access['general_collaborators_authorize_mutation'] is False,'output')
        checked_pin(access['general_rows_pin'],65536)
        for item in access['extra_row_pins']:checked_pin(item,65536)
        statistics=result['statistics'];require(type(statistics) is dict and set(statistics)==set(STATISTICS),'output')
        statistic_pins={}
        for name,text in statistics.items():
            maximum=16384 if name.endswith('DIAGNOSTICS') else 8192
            require(type(text) is str and text.isascii() and 0<len(text)<=maximum,'output')
            loads(text.encode('ascii'),maximum);statistic_pins[name]=pin(text.encode('ascii'))
        require(result['statistics_pin']==pin(canonical(statistics)),'output')
        semantic=result['semantic_validation']
        keys(semantic,('schema','candidate_id','ar_percent','accepted','run_valid','invalid_reason','account','execution',
            'cash_and_tracking','direct_stock_target_counts_by_sleeve','diagnostic_summary','periods','statistics_pins',
            'source_profile_pin','source_vector_pin','evaluation_session_count','evaluation_sessions_sha256','validation',
            'subperiod_path_metrics_independently_recomputed','preliminary','backtest_only',*FLAGS,
            'independent_historical_snapshot_authenticated'))
        require(type(semantic) is dict and len(canonical(semantic))<=16384
            and semantic.get('schema')=='arv2-r348-legacy-six-result-validation-v1'
            and semantic.get('candidate_id')=='R343-AR100' and type(semantic.get('ar_percent')) is int
            and semantic['ar_percent']==100 and semantic.get('accepted') is True
            and semantic.get('run_valid') is True and semantic.get('invalid_reason') is None
            and semantic.get('source_profile_pin')==SOURCE_PROFILE_PIN
            and semantic.get('source_vector_pin')==SOURCE_VECTOR_PIN
            and type(semantic.get('evaluation_session_count')) is int and semantic['evaluation_session_count']==1451
            and type(semantic.get('evaluation_sessions_sha256')) is str
            and re.fullmatch('[0-9a-f]{64}',semantic['evaluation_sessions_sha256'])
            and semantic.get('statistics_pins')==statistic_pins
            and all(semantic.get(key) is False for key in (*FLAGS,'independent_historical_snapshot_authenticated'))
            and semantic.get('subperiod_path_metrics_independently_recomputed') is False
            and semantic.get('preliminary') is True and semantic.get('backtest_only') is True,'output')
        require(result['look_accounting']=={'shared_look_delta':0,'development_look_delta':0,
            'infrastructure_look_delta':0,'accepted_result_cell_delta':0,'physical_request_count_measured':False}
            and all(type(result['look_accounting'][key]) is int for key in ('shared_look_delta',
                'development_look_delta','infrastructure_look_delta','accepted_result_cell_delta'))
            and result['result_body_qualification']=='bounded_full_response_parsed_ephemerally_only_selected_custom_statistics_retained','output')
    else:
        keys(value,('schema','stage','claim_state','failure_code','evidence','result_read_dispatched',
            'result_read_response_received','selected_result_read',*FLAGS))
        require(value['schema']==SCHEMA+'-failure'
            and value['stage'] in ('preflight','data','credentials','access','source','status','statistics','semantic','complete')
            and value['claim_state'] in ('unallocated','allocated_unknown','consumed')
            and type(value['failure_code']) is str and value['failure_code'] in FINITE
            and all(value[key] is False for key in FLAGS)
            and all(type(value[key]) is bool for key in ('result_read_dispatched','result_read_response_received','selected_result_read'))
            and (not value['selected_result_read'] or value['result_read_response_received'])
            and (not value['result_read_response_received'] or value['result_read_dispatched']),'output')
        evidence=value['evidence']
        if evidence is not None:
            keys(evidence,('known_identities','observed_status','last_request','last_access_observation','source_observation',
                'statistics_pin','semantic_observation','semantic_failure_code','last_http_status','http_status_count',
                'http_status_vector_pin','http_statuses','response_pin_count','response_pins','last_api_diagnostic',
                'application_dispatch_count','look_delta','new_launch_performed','result_read_accepted','DATA_guard_returned',
                'result_read_dispatched','result_read_response_received','selected_result_read'))
            require(evidence['known_identities']=={'project_id':PROJECT,'compile_id':COMPILE,'backtest_id':BACKTEST,'attempt':4}
                and evidence['observed_status'] in (None,'In Queue...','In Progress...','Completed.','Runtime Error')
                and type(evidence['application_dispatch_count']) is int and 0<=evidence['application_dispatch_count']<=6
                and type(evidence['look_delta']) is int and evidence['look_delta']==0
                and evidence['new_launch_performed'] is False and evidence['result_read_accepted'] is False
                and type(evidence['DATA_guard_returned']) is bool
                and all(type(evidence[key]) is bool and evidence[key]==value[key]
                    for key in ('result_read_dispatched','result_read_response_received','selected_result_read')),'output')
    return {'schema':SCHEMA+'-original-output-validation','original_output_validated':True,'actual_exit':actual_exit,
        'accepted_result':actual_exit==0,'original_stdout_pin':pin(raw),'original_envelope':loads(canonical(value),MAX_OUTPUT),
        'qualification':'supplied_original_bytes_and_observed_exit_only_not_independent_disk_process_or_QC_attestation'}


class Parser(argparse.ArgumentParser):
    def error(self, message): raise Refused('arguments')


def main():
    parser = Parser(add_help=False)
    parser.add_argument('mode', choices=('profile', 'run'))
    parser.add_argument('candidate', choices=CANDIDATES)
    for key in ('expected-head', 'caller-sha256', 'plan-sha256'):
        parser.add_argument('--' + key)
    args = parser.parse_args()
    if args.mode == 'profile':
        require(all(getattr(args, key) is None for key in ('expected_head', 'caller_sha256', 'plan_sha256')), 'arguments')
        return profile_record(args.candidate)
    def expired(*_): raise Deadline()
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, SECONDS)
    return run(args)


if __name__ == '__main__':
    try:
        raw = canonical(main()) + b'\n'
        require(len(raw) <= MAX_OUTPUT, 'output'); sys.stdout.buffer.write(raw)
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'schema': SCHEMA + '-failure', 'stage': STAGE,
            'claim_state': CLAIM, 'failure_code': finite(error), 'evidence': LAST_FAILURE,
            'result_read_dispatched':RESULT_READ_DISPATCHED,'result_read_response_received':RESULT_READ_RESPONSE_RECEIVED,
            'selected_result_read':SELECTED_RESULT_READ,**FLAGS}) + b'\n')
        raise SystemExit(2)
