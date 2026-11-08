"""One owner-authorized A4 of the same AR100 project using prepared plaintext.

The exact public plan, caller and clean HEAD precede contact. The caller claims
once, authenticates immutable DATA before credentials, checks current Object
Store metadata, and recovers only project39054561 with exact readback. It
returns only after statistics-disabled status observes running or completed
identity; result reading is separate.
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
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
SOURCE = ROOT / 'scripts/run_arv2_r347_legacy_six_a4.py'
PLAN = ROOT / 'scripts/arv2_r347_legacy_six_plan_a4.json'
PARENT_PLAN = ROOT / 'scripts/arv2_r346_legacy_plain_plan.json'
PARENT_PLAN_PIN = {'byte_count':49839,'sha256':'699788fa6d53f0bf4cd8048986e78d96e7c0a4cb0cbcd729fe5fa4a45600849a'}
SUPPORT = ROOT / '.pytest_cache/r347-operation-a4'
DATA_DIRECTORY = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_plain/R346-20261107-A'
DATA_NAMES = ('evaluator-manifest.json','session_axis-0000.jsonl','memberships-0000.jsonl',
    'contributions-0000.jsonl','runtime_symbol_bindings-0000.jsonl','transport-manifest.json',
    'source-proposal.json','report.json')
CONTROL_PARENT = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_runs'
SCHEMA = 'arv2-r347-legacy-six-operation-a4-v1'
PLAN_SCHEMA = 'arv2-r347-legacy-six-plan-a4-v1'
CANDIDATES = ('R343-AR100',)
PROJECT = 39054561
PREPARATION_FACT = ROOT / 'scripts/arv2_r346_preparation_result_fact.json'
PREPARATION_FACT_PIN = {'byte_count':43136,'sha256':'c7b22ba9e82558e23097d3d0802f864a87f6ae56d1ef9d415045f4d9cb68b4cd'}
RECONCILIATION_FACT = ROOT / 'scripts/arv2_r347_current_project_fact.json'
RECONCILIATION_FACT_PIN = {'byte_count':7353,'sha256':'9193129dc41eba2c7ee735e740b9310f69c14fca7a63e84e4eab7caa49307608'}
CONSUMER_PATH = 'scripts/arv2_r347_plain_submission_data.py'
ENGINE_PATH = 'scripts/arv2_r347_legacy_six_qc.py'
TRANSPORT_PATH = 'scripts/arv2_r345_qc_error_transport_v3.py'
FIXED_ADDITIONAL_PINS = {
    'scripts/prepare_arv2_r346_legacy_plain.py': {'byte_count':42109,'sha256':'f9bb012166df92525fd77888206b792b7279a12a2ea44485da3f75accc1c30cc'},
    'scripts/arv2_r346_preparation_result_fact.json': PREPARATION_FACT_PIN,
    'scripts/arv2_r347_current_project_fact.json': RECONCILIATION_FACT_PIN,
    'scripts/observe_arv2_r347_plain_recovery.py': {'byte_count':44205,'sha256':'0b8db07fba169b2dcad9676fbf7c1ff40e0a5bcc96552aa30ea63099cf14bfb1'},
}
SECONDS, MAX_PUBLIC, MAX_PLAN, MAX_JOURNAL = 3600, 2 * 1024 * 1024, 256 * 1024, 8 * 1024 * 1024
MAX_OUTPUT, MAX_EVENTS = 64 * 1024, 4096
STATUS_CHECKS = 30
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
CREDENTIALS = ('QC_USER_ID', 'QC_API_TOKEN')
STAGE, CLAIM, LAST_FAILURE = 'preflight', 'unallocated', None
FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False, 'result_read': False}
FINITE = frozenset(('arguments', 'environment', 'git', 'plan', 'source_pin', 'source_changed',
    'inventory', 'claim_spent', 'control', 'deadline', 'data', 'credentials', 'access', 'capacity',
    'object_admission', 'request', 'operation', 'compile', 'launch', 'output', 'close', 'unknown'))


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
    return CONTROL_PARENT / 'R347-20261107-AR100-A4'


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
    ancestors = {path for leaf in (*data_paths, own) for path in leaf.parents
        if path == ROOT / 'artifacts' or ROOT / 'artifacts' in path.parents}
    value += '(deny file-read* (require-all (subpath ' + json.dumps(str(ROOT / 'artifacts')) + ')'
    value += ''.join('(require-not (literal ' + json.dumps(str(path)) + '))' for path in data_paths)
    value += '(require-not (subpath ' + json.dumps(str(own)) + '))'
    value += ''.join('(require-not (literal ' + json.dumps(str(path)) + '))' for path in sorted(ancestors)) + '))'
    return value


def profile_record(candidate):
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': PYTHON,
        'candidate_id': candidate, 'attempt': 4, 'control': str(control(candidate)),
        'recovery_project_id': PROJECT, 'preparation_fact_pin': dict(PREPARATION_FACT_PIN),
        'reconciliation_fact_pin': dict(RECONCILIATION_FACT_PIN), 'parent_plan_pin':dict(PARENT_PLAN_PIN),
        'recovery_scope': 'owner_exact_one_additional_A4_same_project_fresh_A4_context_no_Mia_adoption_no_reset',
        'prior_attempts_consumed':3,'other_candidates_permitted':False,
        'data_directory':str(DATA_DIRECTORY),'exact_data_names':list(DATA_NAMES),'plan': str(PLAN), 'seconds': SECONDS,
        'native_policy_sha256': pin(native_profile(candidate).encode())['sha256'],
        'credential_policy': 'existing_environment_after_exclusive_claim_and_DATA_guard_normal_return',
        'object_policy': 'six_exact_prepared_plain_properties_size_and_MD5_metadata_before_mutation_and_launch_no_get_download_upload',
        'object_qualification': 'metadata_MD5_is_not_remote_SHA256_attestation_runtime_reader_checks_all_SHA256',
        'source_policy': 'all_selected_bytes_held_compiled_full_metadata_empty_ACL_all_observed_public_xattrs',
        'error_observation': 'new_bounded_response_and_context_redacted_error_projection_before_discard_no_raw_retention',
        'failed_HTTP_body': 'new_bounded_identity_encoded_JSON_only_non200_max64KiB_never_arbitrary_download',
        'max_output_bytes': MAX_OUTPUT, 'max_failure_evidence_bytes': 48 * 1024,
        'max_API_diagnostic_bytes': 24 * 1024,
        'terminal': 'one_launch_then_bounded_statistics_disabled_queue_observation_until_InProgress_or_Completed_no_result_read',
        'queue_status_checks':STATUS_CHECKS,'queue_status_interval_seconds':60,
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
                'parent_plan_pin','preparation_fact_pin','reconciliation_fact_pin','source_pins'}
                and self.plan['schema'] == PLAN_SCHEMA and self.plan['candidate_id']=='R343-AR100'
                and type(self.plan['attempt']) is int and self.plan['attempt']==4
                and type(self.plan['project_id']) is int and self.plan['project_id']==PROJECT
                and self.plan['parent_plan_pin']==PARENT_PLAN_PIN
                and self.plan['preparation_fact_pin']==PREPARATION_FACT_PIN
                and self.plan['reconciliation_fact_pin']==RECONCILIATION_FACT_PIN
                and type(self.plan['source_pins']) is dict, 'plan')
            parent = loads(self.hold(PARENT_PLAN,PARENT_PLAN_PIN),MAX_PLAN)
            require(type(parent) is dict and type(parent.get('source_pins')) is dict
                and len(parent['source_pins'])==170, 'plan')
            additional = {CONSUMER_PATH,ENGINE_PATH,*FIXED_ADDITIONAL_PINS}
            require(set(self.plan['source_pins'])==set(parent['source_pins'])|additional
                and all(self.plan['source_pins'].get(key)==value for key,value in parent['source_pins'].items())
                and all(self.plan['source_pins'].get(key)==value for key,value in FIXED_ADDITIONAL_PINS.items()), 'inventory')
            soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            require(soft == resource.RLIM_INFINITY or soft >= len(self.plan['source_pins']) + 180, 'environment')
            for relative, expected in sorted(self.plan['source_pins'].items()):
                require(type(relative) is str and not relative.startswith('/') and '..' not in Path(relative).parts
                    and relative.endswith(('.py', '.json')) and 'artifacts' not in Path(relative).parts
                    and relative != PLAN.relative_to(ROOT).as_posix(), 'plan')
                self.raws[relative] = self.hold(ROOT / relative, expected)
            for required in ('scripts/arv2_relocation_security.py', 'scripts/prepare_arv2_r343_legacy_six.py',
                    'scripts/arv2_r343_legacy_six_source_pins.json',CONSUMER_PATH,ENGINE_PATH,TRANSPORT_PATH,
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
            self.engine = importlib.import_module(ENGINE_PATH[:-3].replace('/','.'))
            self.preparation_fact_bytes=self.raws[PREPARATION_FACT.relative_to(ROOT).as_posix()]
            self.consumer.parse_fact(self.preparation_fact_bytes)
            raw_fact=self.raws[RECONCILIATION_FACT.relative_to(ROOT).as_posix()]
            require(raw_fact.endswith(b'\n'),'plan')
            self.reconciliation_fact=loads(raw_fact[:-1],MAX_PLAN)
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
        self.first_evaluation_dispatch = None
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
        require(self.application_dispatch_count < self.intents, 'request')
        self.journal('http-dispatch', {'endpoint': endpoint, 'project_id': project_id, 'ordinal': self.application_dispatch_count})
        if endpoint in ('compile/create', 'backtests/create') and self.first_evaluation_dispatch is None:
            require(project_id == PROJECT, 'request')
            self.first_evaluation_dispatch = {'endpoint': endpoint,
                'application_dispatch_ordinal': self.application_dispatch_count,
                'candidate_id': 'R343-AR100', 'attempt': 4}
        self.application_dispatch_count += 1
    def look_accounting(self):
        spent = int(self.first_evaluation_dispatch is not None)
        return {'shared_look_delta': spent, 'development_look_delta': spent,
            'infrastructure_look_delta': 0, 'accepted_result_cell_delta': 0,
            'first_application_dispatch': None if not spent else dict(self.first_evaluation_dispatch),
            'physical_request_count_measured': False}
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


def object_admission(request, uploads, organization, journal, state):
    """Fresh exact metadata only; runtime independently checks payload SHA-256."""
    require(len(uploads) == 6 and callable(request), 'object_admission')
    result = []
    for ordinal, item in enumerate(uploads):
        journal(f'objects-{ordinal}-intent', {'key_sha256': pin(item.object_store_key.encode())['sha256']})
        response = request('object/properties', {'organizationId': organization, 'key': item.object_store_key})
        require(type(response) is dict and response.get('success') is True
            and ('errors' not in response or response['errors'] == []), 'object_admission')
        row = response.get('metadata')
        local_md5 = hashlib.md5(item.payload, usedforsecurity=False).hexdigest()
        observed_size = row.get('size') if type(row) is dict else None
        observed_md5 = row.get('md5') if type(row) is dict else None
        state['last_object_observation'] = {'ordinal': ordinal,
            'key_sha256': pin(item.object_store_key.encode())['sha256'],
            'metadata_present': type(row) is dict,
            'key_exact': type(row) is dict and row.get('key') == item.object_store_key,
            'size_type': 'int' if type(observed_size) is int else 'bool' if type(observed_size) is bool
                else 'string' if type(observed_size) is str else 'null' if observed_size is None else 'other',
            'observed_size': observed_size if type(observed_size) is int and 0 <= observed_size < 2**63 else None,
            'expected_size': len(item.payload),
            'md5_lower_hex': type(observed_md5) is str and re.fullmatch('[0-9a-f]{32}', observed_md5) is not None,
            'md5_hex': type(observed_md5) is str and re.fullmatch('[0-9a-fA-F]{32}', observed_md5) is not None,
            'md5_matches': type(observed_md5) is str and observed_md5.casefold() == local_md5}
        require(type(row) is dict and row.get('key') == item.object_store_key
            and type(row.get('size')) is int and row['size'] == len(item.payload)
            and type(row.get('md5')) is str and re.fullmatch('[0-9a-fA-F]{32}', row['md5'])
            and row['md5'].casefold() == local_md5, 'object_admission')
        result.append({'key_sha256': pin(item.object_store_key.encode())['sha256'],
            'byte_count': len(item.payload), 'local_sha256': pin(item.payload)['sha256'], 'metadata_md5': local_md5})
        journal(f'objects-{ordinal}-observed', result[-1])
    return {'organization_sha256': pin(organization.encode())['sha256'], 'objects': result,
        'qualification': 'current_size_and_MD5_metadata_not_remote_SHA256_attestation_runtime_reader_rechecks_SHA256'}


def operate(submission, candidate_id, *, engine, api, secret, store, deadline, state,
            reconciliation_fact, sleep=time.sleep):
    """One A4 with a fresh own context; no project creation, retry or result."""
    global STAGE
    candidates = [row for row in submission.candidates if row.candidate_id == candidate_id]
    require(len(candidates) == 1, 'plan')
    allowed_keys = {item.object_store_key for item in submission.uploads}
    def request(endpoint, payload):
        budget(deadline)
        require(type(endpoint) is str and (endpoint in engine.PAYLOAD_KEYS or endpoint == 'object/properties')
            and endpoint not in ('projects/create','projects/collaboration/lock/release','files/delete',
                'backtests/read','object/get','object/set') and type(payload) is dict, 'request')
        if 'projectId' in payload:
            require(type(payload['projectId']) is int and payload['projectId'] in (engine.REFERENCE_PROJECT, PROJECT), 'request')
        if endpoint == 'projects/read':
            require(set(payload) == {'projectId'}, 'request')
        if 'codeSourceId' in payload:
            require(payload['codeSourceId']=='Codex R347 R343-AR100 A4','request')
        if endpoint=='projects/collaboration/lock/acquire':
            require(set(payload)=={'projectId','codeSourceId'} and payload['projectId']==PROJECT
                and not state.get('lock_dispatch_spent',False),'request')
            state['lock_dispatch_spent']=True
        if endpoint=='object/properties':
            require(set(payload)=={'organizationId','key'} and payload['key'] in allowed_keys
                and type(payload['organizationId']) is str
                and re.fullmatch('[0-9a-f]{32}',payload['organizationId'])
                and pin(payload['organizationId'].encode('ascii'))['sha256']==engine.ORGANIZATION_SHA256,'request')
        state['last_request'] = {'endpoint': endpoint, 'payload_sha256': pin(canonical(payload))['sha256']}
        api.deadline = min(deadline, time.monotonic() + 89)
        return api._exchange(endpoint, payload)
    STAGE = 'access'
    for index in range(engine.CAPACITY_POLLS):
        if index:
            require(budget(deadline)>engine.CAPACITY_INTERVAL,'deadline');sleep(engine.CAPACITY_INTERVAL)
        access = engine.access_capacity(request,user_id=int(secret['QC_USER_ID']),journal=store.journal)
        if access['public']['capacity']['available_count']>0: break
    else: raise Refused('capacity')
    uploads=tuple((loads(item.descriptor_json,MAX_OUTPUT),item.payload) for item in submission.uploads)
    operation = engine.LegacySixQc(candidates[0].cell_record(), uploads, organization_id=access['organization_id'],
        user_id=int(secret['QC_USER_ID']), attempt=4,reconciliation_fact=reconciliation_fact,
        request=request, journal=store.journal)
    state['operation'] = operation
    STAGE = 'source_compile'
    begin = operation.begin_once()
    require(begin['state'] == 'compiling', 'capacity')
    for index in range(engine.COMPILE_POLLS):
        if index:
            require(budget(deadline) > engine.COMPILE_INTERVAL, 'deadline'); sleep(engine.COMPILE_INTERVAL)
        compile_state = operation.poll_compile(index)
        require(compile_state['state'] != 'BuildError', 'compile')
        if compile_state['state'] == 'BuildSuccess':
            break
    else:
        raise Refused('compile')
    STAGE = 'launch'
    for index in range(engine.CAPACITY_POLLS):
        if index:
            require(budget(deadline) > engine.CAPACITY_INTERVAL, 'deadline'); sleep(engine.CAPACITY_INTERVAL)
        # Engine owns fresh current project/source/input-properties/compile/
        # capacity validation. A missing/mismatched object refuses; no upload.
        launched = operation.launch_once()
        if launched['state'] == 'launched':
            break
    else:
        raise Refused('capacity')
    require(type(launched.get('launch_receipt')) is dict, 'launch')
    status=launched.get('launch_status')
    require(status in ('In Queue...','In Progress...','Completed.','Runtime Error'),'launch')
    STAGE='status'
    if status=='In Queue...':
        for index in range(STATUS_CHECKS):
            require(budget(deadline)>engine.STATUS_INTERVAL,'deadline');sleep(engine.STATUS_INTERVAL)
            observed=operation.poll_status(index);status=observed.get('status')
            require(status in ('In Queue...','In Progress...','Completed.','Runtime Error'),'launch')
            if status!='In Queue...': break
        else: raise Refused('launch')
    require(status in ('In Progress...','Completed.'),'launch')
    STAGE='running' if status=='In Progress...' else 'completed_identity'
    return {'candidate_id': candidate_id, 'attempt': 4,'project_id':PROJECT,
        'launch_receipt': launched['launch_receipt'],
        'terminal_receipt': operation.terminal_receipt, 'access': access['public'],
        'observed_status':status,'running_observed':status=='In Progress...',
        'terminal_identity_observed':status=='Completed.',
        'source_identity':loads(submission.source_identity_json,MAX_OUTPUT),
        'input_metadata_admission': {'observations': loads(canonical(operation.metadata_admissions),MAX_OUTPUT),
            'qualification':'current_key_size_MD5_metadata_not_remote_SHA256_attestation_runtime_reader_rechecks_all_SHA256'},
        'application_dispatch_count': store.application_dispatch_count,
        'look_accounting':store.look_accounting(),
        'last_access_observation': access_observation(engine, operation),
        'result_semantics': 'statistics_disabled_status_only_no_strategy_result', **FLAGS}


def run(args):
    global STAGE, LAST_FAILURE
    deadline = time.monotonic() + SECONDS
    bound = preflight(args, deadline)
    with Sources(args, deadline) as sources:
        with Store(control(args.candidate), sources.security) as store:
            store.write('claim.json', {'binding': bound, 'profile': profile_record(args.candidate),
                'consumed_at': datetime.now(timezone.utc).isoformat()})
            store.write('events.jsonl', b'')
            api = None
            state = {'api': None, 'operation': None, 'last_request': None, 'last_object_observation': None,
                'store': store}
            try:
                STAGE = 'data'
                with sources.consumer.FreshPlainSubmission(fact_bytes=sources.preparation_fact_bytes,
                        deadline=min(deadline, time.monotonic() + 179)) as held:
                    submission = held.value
                # Only detached immutable buffers survive the DATA guard's
                # normal return; no secret/contact existed during that read.
                STAGE = 'credentials'
                secret = sources.transport.credentials({key: os.environ.get(key) for key in CREDENTIALS})
                api = sources.transport.API(secret, store, min(deadline, time.monotonic() + 89))
                state['api'] = api
                result = operate(submission, args.candidate, engine=sources.engine, api=api,
                    secret=secret, store=store, deadline=deadline, state=state,
                    reconciliation_fact=sources.reconciliation_fact)
                result['last_api_diagnostic'] = api_diagnostic(sources.transport, api)
                # Preserve safe allocation/contact facts even if a subsequent
                # final source/control verification or descriptor close fails
                # outside this inner handler, before stdout can be emitted.
                LAST_FAILURE = failure_evidence(state, sources, Refused('unknown'))
                api.close(); api = None
                sources.verify()
                report = {'schema': SCHEMA + '-result', 'binding': bound, 'attempt_consumed': True, 'result': result}
                report_pin = store.write('report.json', report)
                store.verify()
            except BaseException as error:
                LAST_FAILURE = failure_evidence(state, sources, error)
                if api is not None:
                    api.close()
                reason = finite(error, sources)
                store.write('failure.json', {'schema': SCHEMA + '-failure', 'binding': bound,
                    'stage': STAGE, 'failure_code': reason, 'attempt_consumed': True,
                    'application_dispatch_count': store.application_dispatch_count,
                    'evidence': LAST_FAILURE, **FLAGS})
                raise Refused(reason) from None
    STAGE = 'complete'
    LAST_FAILURE = None
    return {**report, 'report_pin': report_pin}


def finite(error, sources=None):
    if isinstance(error, (Deadline, TimeoutError, subprocess.TimeoutExpired)):
        return 'deadline'
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
        return args[0]
    if sources is not None:
        for module, code in ((sources.consumer, 'data'), (sources.engine, 'operation'), (sources.transport, 'request')):
            if type(error) is module.Refused:
                return code
    return 'unknown'


def access_observation(engine, operation):
    """Only the engine's closed type/count projection, never remote values."""
    validator = getattr(engine, 'validate_metadata_observation', None)
    if not callable(validator):
        return None
    try:
        result = validator(getattr(operation, 'last_access_observation', None))
        if type(result) is dict and len(canonical(result)) <= 4096:
            return result
    except Exception:
        pass
    return None


def api_diagnostic(transport, api):
    """Validate finite/lossy diagnostic only; never serialize raw API state."""
    validator = getattr(transport, 'validate_diagnostic', None)
    if not callable(validator):
        return None
    try:
        result = validator(getattr(api, 'last_diagnostic', None))
        if type(result) is dict and len(canonical(result)) <= 24 * 1024:
            return result
    except Exception:
        pass
    return None


def failure_evidence(state, sources, error):
    """Closed finite projection; never serialize opaque API/engine instances."""
    allowed = set(sources.engine.PAYLOAD_KEYS) | {'object/properties'}
    def endpoint(value):
        return value if type(value) is str and value in allowed else None
    def digest(value):
        return value if type(value) is str and re.fullmatch('[0-9a-f]{64}', value) else None
    def identity(value):
        return value if type(value) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value) else None
    def request(value):
        if type(value) is not dict:
            return None
        result = {'endpoint': endpoint(value.get('endpoint')), 'payload_sha256': digest(value.get('payload_sha256'))}
        marker, stage = value.get('marker'), value.get('stage')
        if type(marker) is str and re.fullmatch('[a-z0-9-]{1,100}', marker): result['marker'] = marker
        if stage in ('intent_or_request_unaccepted', 'response_unaccepted'): result['stage'] = stage
        if digest(value.get('response_sha256')) is not None:
            result['response_sha256'] = value['response_sha256']
        count = value.get('response_bytes')
        if type(count) is int and 0 < count <= 2 * 1024 * 1024: result['response_bytes'] = count
        return result
    module_error = {'module': 'unknown', 'code': 'unknown'}
    for name, module in (('caller', sys.modules.get(__name__)), ('consumer', sources.consumer),
            ('engine', sources.engine), ('transport', sources.transport)):
        if module is not None and type(error) is getattr(module, 'Refused', None):
            args = BaseException.args.__get__(error)
            if len(args) == 1 and type(args[0]) is str and args[0] in module.FINITE:
                module_error = {'module': name, 'code': args[0]}
    api, operation = state.get('api'), state.get('operation')
    statuses, responses = [], []
    if api is not None:
        for row in getattr(api, 'statuses', ()):
            if type(row) is dict and endpoint(row.get('endpoint')) is not None \
                    and type(row.get('http_status')) is int and 100 <= row['http_status'] <= 599:
                statuses.append({'endpoint': row['endpoint'], 'http_status': row['http_status']})
        for row in getattr(api, 'responses', ()):
            if type(row) is dict and endpoint(row.get('endpoint')) is not None \
                    and valid_pin({key: row.get(key) for key in ('byte_count', 'sha256')}, 2 * 1024 * 1024):
                responses.append({key: row[key] for key in ('endpoint', 'byte_count', 'sha256')})
    last_status = getattr(api, 'last_http_status', None)
    project_id = getattr(operation, 'project_id', None)
    receipt = getattr(operation, 'launch_receipt', None)
    allocated = {'project_id': project_id if type(project_id) is int and 0 < project_id < 2**63 else None,
        'compile_id': identity(getattr(operation, 'compile_id', None)),
        'backtest_id': identity(receipt.get('backtest_id')) if type(receipt) is dict else None}
    # Object observations were constructed solely from exact booleans, bounded
    # integers, finite type names and an expected-key hash before refusal.
    observation = state.get('last_object_observation')
    object_keys = {'ordinal', 'key_sha256', 'metadata_present', 'key_exact', 'size_type',
        'observed_size', 'expected_size', 'md5_lower_hex', 'md5_hex', 'md5_matches'}
    if (type(observation) is not dict or set(observation) != object_keys
            or type(observation.get('ordinal')) is not int or not 0 <= observation['ordinal'] < 6
            or digest(observation.get('key_sha256')) is None
            or not all(type(observation.get(key)) is bool for key in ('metadata_present', 'key_exact', 'md5_lower_hex', 'md5_hex', 'md5_matches'))
            or observation.get('size_type') not in ('int', 'bool', 'string', 'null', 'other')
            or not (observation.get('observed_size') is None or type(observation['observed_size']) is int and 0 <= observation['observed_size'] < 2**63)
            or type(observation.get('expected_size')) is not int or not 0 < observation['expected_size'] <= 32 * 1024 * 1024):
        observation = None
    result = {'module_error': module_error,
        'last_http_status': last_status if type(last_status) is int and 100 <= last_status <= 599 else None,
        'http_status_count': len(statuses), 'http_status_vector_pin': pin(canonical(statuses)),
        'last_http_statuses': statuses[-12:], 'response_pin_count': len(responses),
        'response_pin_vector_pin': pin(canonical(responses)), 'last_response_pins': responses[-6:],
        'last_request': request(state.get('last_request')),
        'engine_last_request': request(getattr(operation, 'last_request', None)),
        'engine_last_failure': request(getattr(operation, 'last_failure', None)),
        'last_access_observation': access_observation(sources.engine, operation),
        'last_api_diagnostic': api_diagnostic(sources.transport, api),
        'allocated_identities': allocated, 'object_observation': observation,
        'look_accounting': state['store'].look_accounting() if state.get('store') is not None else None}
    require(len(canonical(result)) <= 48 * 1024, 'output')
    return result


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
            'claim_state': CLAIM, 'failure_code': finite(error), 'evidence': LAST_FAILURE, **FLAGS}) + b'\n')
        raise SystemExit(2)
