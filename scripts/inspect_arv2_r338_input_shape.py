"""Once-only metadata observation of fixed source paths, never a source read.

The frozen external invocation must apply native_profile to this process.
Absolute lstat follows intermediate ancestors; two named endpoints are not
held descriptors, kernel-all-component nofollow or continuous-path proof.
Only the NEW own control permits byte IO. No input content, list, repair,
old control, provider, credential, QC or Safari operation exists here.
"""
import argparse
from contextlib import ExitStack
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import types

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH = 'codex/strategy-analyst-revisions-v2'
SOURCE = ROOT / 'scripts/inspect_arv2_r338_input_shape.py'
HELPER = ROOT / 'scripts/arv2_r338_input_shape.py'
SECURITY = ROOT / 'scripts/arv2_relocation_security.py'
HELPER_SHA256 = '1446e661446934114044f788a9c8702cd50d5004f51243ac358562bbfbe0dd27'
SECURITY_SHA256 = '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/quarantine/R338-20261104-B'
SCHEMA = 'arv2-r338-input-shape-metadata-caller-v1'
SECONDS = 30
MAX_CODE, MAX_OUTPUT, MAX_PRIVATE = 65536, 32768, 65536
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
    'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FALSE_FLAGS = {name: False for name in ('source_bytes_read', 'source_directory_listed',
    'source_ACL_or_xattrs_observed', 'source_bytes_authenticated', 'all_component_nofollow_proven',
    'source_held_descriptor_identity_proven', 'continuous_path_integrity_proven',
    'parent_creation_fsync_proven', 'old_failure_cause_proven', 'old_control_read',
    'old_operation_replayed', 'policy_or_metadata_repaired', 'QC_contact', 'Safari_access',
    'provider_contact', 'credential_access', 'USB_read', 'source_admission_granted',
    'price_coverage_proven', 'strategy_result_accepted', 'backtest_ready', 'point_in_time_proven',
    'formal_forward_ready', 'paper_or_live_ready')}
FINITE = frozenset(('arguments', 'host', 'environment', 'git_state', 'source_pin', 'source_changed',
    'deadline', 'claim_spent', 'control', 'security', 'metadata', 'helper', 'bound', 'output',
    'os_error', 'unknown'))
DEADLINE_FIRED = False
CLAIM_STATE = 'unallocated'
ACTIVE_BINDING = None


class Refused(ValueError):
    """Finite predicate only; never a path value, stat body or raw exception."""


class RunDeadline(BaseException):
    """Timer control flow outside ordinary private parser handlers."""


def expire(*_):
    global DEADLINE_FIRED
    DEADLINE_FIRED = True
    raise RunDeadline()


def require(value, code):
    if not value: raise Refused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}


def finite(error):
    if DEADLINE_FIRED or isinstance(error, (RunDeadline, TimeoutError, subprocess.TimeoutExpired)):
        return 'deadline'
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args) == 1 and type(args[0]) is str and args[0] in FINITE: return args[0]
    return 'os_error' if isinstance(error, OSError) else 'unknown'


def budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= SECONDS, 'deadline')
    return deadline - time.monotonic()


def metadata(info):
    value = tuple(getattr(info, field, None) for field in FIELDS)
    require(all(type(item) is int and item >= 0 for item in value), 'metadata')
    return value


def loads(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT, 'bound')
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'output'); result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('output')))
        require(canonical(value) == raw, 'output'); return value
    except Refused: raise
    except (TypeError, ValueError, UnicodeError, RecursionError): raise Refused('output') from None


class HeldCode:
    """Three explicitly selected public CODE leaves; never an artifact path."""
    def __init__(self, path, expected):
        require(path in (SOURCE, HELPER, SECURITY), 'source_pin')
        self.path, self.expected, self.fd = path, expected, None
    def __enter__(self):
        before = metadata(os.lstat(self.path))
        require(stat.S_ISREG(before[2]) and before[3] == os.getuid() and before[5] == 1
            and 0 < before[6] <= MAX_CODE, 'source_pin')
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            self.initial = metadata(os.fstat(self.fd)); require(self.initial == before, 'source_changed')
            self.raw = os.pread(self.fd, MAX_CODE + 1, 0)
            require(type(self.expected) is str and re.fullmatch('[0-9a-f]{64}', self.expected)
                and len(self.raw) == before[6] and self.raw.isascii() and sha(self.raw) == self.expected, 'source_pin')
            self.verify(); return self
        except BaseException:
            os.close(self.fd); self.fd = None; raise
    def verify(self):
        require(self.fd is not None and metadata(os.fstat(self.fd)) == self.initial
            == metadata(os.lstat(self.path)) and sha(os.pread(self.fd, MAX_CODE + 1, 0)) == self.expected,
            'source_changed')
    def __exit__(self, *_):
        try: self.verify()
        finally:
            if self.fd is not None: os.close(self.fd); self.fd = None


def load_modules(stack, helper_sha256):
    helper_code = stack.enter_context(HeldCode(HELPER, helper_sha256))
    security_code = stack.enter_context(HeldCode(SECURITY, SECURITY_SHA256))
    modules = []
    for name, selected in (('_arv2_r338_metadata_shape', helper_code), ('_arv2_r338_output_security', security_code)):
        module = types.ModuleType(name); module.__file__ = str(selected.path)
        exec(compile(selected.raw, str(selected.path), 'exec'), module.__dict__)
        modules.append(module)
    helper, security = modules
    require(helper.SCHEMA == 'arv2-r338-input-metadata-shape-v1'
        and helper.INPUT_SOURCE_SHA256 == 'a7e56ca57bd54b4743c18f04f5287119b91c82a9bf7165692ad2cb457b8d7ce8'
        and helper.FIELDS == FIELDS and 0 < len(helper.scope()) <= 64, 'helper')
    return helper, security


def binding(args):
    for name, length in (('expected_head', 40), ('caller_sha256', 64), ('helper_sha256', 64), ('profile_sha256', 64)):
        value = getattr(args, name, None)
        require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value), 'arguments')
    require(args.helper_sha256 == HELPER_SHA256, 'source_pin')
    return {'schema': SCHEMA, **{name: getattr(args, name) for name in
        ('expected_head', 'caller_sha256', 'helper_sha256', 'profile_sha256')}}


def safe_env():
    support = ROOT / '.pytest_cache/r338-B-runtime'
    support.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(support.resolve() == support, 'environment')
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(support), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'GIT_OPTIONAL_LOCKS': '0'}


def native_profile(helper, *, validator=False):
    value = '(version 1)(allow default)(deny network*)'
    value += ''.join('(deny file-read* file-write* (subpath "' + path + '"))' for path in
        ('/Volumes', '/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    value += '(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    support = ROOT / '.pytest_cache/r338-B-runtime'
    value += '(deny file-write* (require-all (require-not (subpath "' + str(support) + '"))'
    if not validator:
        value += '(require-not (subpath "' + str(CONTROL) + '"))(require-not (literal "' + str(CONTROL.parent) + '"))'
    value += '(require-not (literal "/dev/null"))))'
    artifact = ROOT / 'artifacts'
    if validator:
        return value + '(deny file-read* (subpath "' + str(artifact) + '"))'
    value += '(deny file-read-data (require-all (subpath "' + str(artifact) + '")(require-not (subpath "' + str(CONTROL) + '"))))'
    value += '(deny file-read-xattr (require-all (subpath "' + str(artifact) + '")(require-not (subpath "' + str(CONTROL) + '"))))'
    allowed = {Path(spec['path']) for spec in helper.scope()}
    allowed.update(CONTROL.parents)
    selected = sorted(path for path in allowed if path == artifact or artifact in path.parents)
    value += '(deny file-read* (require-all (subpath "' + str(artifact) + '")(require-not (subpath "' + str(CONTROL) + '"))'
    value += ''.join('(require-not (literal "' + str(path) + '"))' for path in selected) + '))'
    return value


def profile_record(helper):
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': PYTHON, 'control': str(CONTROL),
        'helper_source_sha256': HELPER_SHA256, 'helper_profile_pin': pin(canonical(helper.profile_record())),
        'security_source_sha256': SECURITY_SHA256, 'maximum_seconds': SECONDS,
        'maximum_private_bytes': MAX_PRIVATE, 'maximum_output_bytes': MAX_OUTPUT,
        'observe_native_policy_sha256': sha(native_profile(helper).encode()),
        'validate_native_policy_sha256': sha(native_profile(helper, validator=True).encode()),
        'metadata': 'fixed_parent_first_absolute_lstat_two_passes_block_descendants_no_source_open_read_list_or_xattrs',
        'private_transport': 'one_fresh32byte_nonce_after_exclusive_claim_and_fsync_private_only',
        'output': 'protected_original_own_FDs_byte_readback_and_security_endpoints_only_after_public_code_guards_return',
        'parent_creation': 'own_claim_and_directory_fsync_only_no_parent_directory_fsync_or_crash_reuse',
        'native_invocation': 'external_exact_frozen_sandbox_required_observe_and_separate_stdin_validator',
        'deadline': 'actual_SIGALRM_over_preflight_claim_metadata_output_uninterruptibleIO_host_suspension_qualification',
        **FALSE_FLAGS}


def preflight(args, helper, deadline):
    binding(args); budget(deadline)
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3, 13) and sys.executable == PYTHON
        and sys.flags.isolated == 1 and sys.dont_write_bytecode and Path(__file__).absolute() == SOURCE, 'host')
    environment = safe_env()
    require(set(os.environ) <= set(environment) and all(os.environ[name] == environment[name] for name in os.environ), 'environment')
    require(args.profile_sha256 == sha(canonical(profile_record(helper))), 'source_pin')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], BRANCH),
        (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        result = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(5, budget(deadline)))
        require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 131072
            and result.stdout.decode('ascii').strip() == expected, 'git_state')
    for path, expected in ((SOURCE, args.caller_sha256), (HELPER, HELPER_SHA256), (SECURITY, SECURITY_SHA256)):
        result = subprocess.run(['/usr/bin/git', 'cat-file', 'blob', args.expected_head + ':' + path.relative_to(ROOT).as_posix()],
            cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=min(5, budget(deadline)))
        require(result.returncode == 0 and not result.stderr and 0 < len(result.stdout) <= MAX_CODE
            and sha(result.stdout) == expected, 'source_pin')


class Store:
    """Only NEW own control permits byte IO; ancestors are named endpoints."""
    def __init__(self, security):
        self.security, self.fd, self.held, self.pending = security, None, [], []
    def verify(self):
        require(self.fd is not None and metadata(os.fstat(self.fd)) == self.info == metadata(os.lstat(CONTROL))
            and stat.S_ISDIR(self.info[2]) and self.info[3] == os.getuid() and stat.S_IMODE(self.info[2]) == 0o700
            and self.security.snapshot(self.fd) == self.directory_security
            and set(os.listdir(self.fd)) == {row[0] for row in self.held}, 'control')
        for path, expected in self.ancestors:
            require(metadata(os.lstat(path)) == expected, 'control')
        for name, fd, info, expected, security in self.held:
            require(metadata(os.fstat(fd)) == info == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and stat.S_ISREG(info[2]) and info[3] == os.getuid() and stat.S_IMODE(info[2]) == 0o600 and info[5] == 1
                and self.security.snapshot(fd) == security
                and pin(os.pread(fd, expected['byte_count'] + 1, 0)) == expected, 'output')
    def __enter__(self):
        global CLAIM_STATE
        try:
            try: os.mkdir(CONTROL.parent, 0o700)
            except FileExistsError: pass
            try: os.mkdir(CONTROL, 0o700); CLAIM_STATE = 'allocated_unknown'
            except FileExistsError:
                CLAIM_STATE = 'consumed_or_unknown'; raise Refused('claim_spent') from None
            self.ancestors = []
            for path in reversed(CONTROL.parents):
                observed = metadata(os.lstat(path)); require(stat.S_ISDIR(observed[2]), 'control')
                if path == ROOT or ROOT in path.parents:
                    require(observed[3] == os.getuid() and stat.S_IMODE(observed[2]) == (0o755 if path == ROOT else 0o700), 'control')
                self.ancestors.append((path, observed))
            self.fd = os.open(CONTROL, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.info = metadata(os.fstat(self.fd)); self.directory_security = self.security.snapshot(self.fd)
            os.fsync(self.fd); self.verify(); return self
        except BaseException:
            if self.fd is not None: os.close(self.fd); self.fd = None
            raise
    def write(self, name, raw):
        global CLAIM_STATE
        require(name in ('claim.json', 'metadata-private.json', 'report.json') and type(raw) is bytes
            and 0 < len(raw) <= MAX_PRIVATE, 'output')
        self.verify(); before = self.info
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        self.pending.append(fd); offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:]); require(written > 0, 'output'); offset += written
        os.fsync(fd)
        info = metadata(os.fstat(fd))
        require(info == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
            and pin(os.pread(fd, len(raw) + 1, 0)) == pin(raw), 'output')
        fresh = metadata(os.fstat(self.fd))
        require(all(fresh[index] == before[index] for index in (0, 1, 2, 3, 4, 9))
            and fresh[5] in (before[5], before[5] + 1) and fresh[6] >= before[6]
            and self.security.snapshot(self.fd) == self.directory_security, 'control')
        self.info = fresh; self.held.append((name, fd, info, pin(raw), self.security.snapshot(fd)))
        self.pending.remove(fd); os.fsync(self.fd); self.verify()
        if name == 'claim.json': CLAIM_STATE = 'consumed'
        return pin(raw)
    def __exit__(self, *_):
        try: self.verify()
        finally:
            for _, fd, _, _, _ in self.held: os.close(fd)
            for fd in self.pending: os.close(fd)
            if self.fd is not None: os.close(self.fd); self.fd = None


def collect(helper, deadline):
    plan = helper.scope(); passes = []
    for _ in range(2):
        observed = {}; current = []
        for spec in plan:
            budget(deadline); path = Path(spec['path'])
            blocked = any(parent in observed and (observed[parent][1] != 'observed'
                or not stat.S_ISDIR(observed[parent][0][2])) for parent in path.parents)
            if blocked: value, status = None, 'blocked_ancestor'
            else:
                try: value, status = metadata(os.lstat(path)), 'observed'
                except OSError as error:
                    value = None; status = {errno.ENOENT: 'not_found', errno.EACCES: 'permission_denied',
                        errno.EPERM: 'permission_denied', errno.ENOTDIR: 'not_directory'}.get(error.errno, 'unavailable')
            observed[path] = (value, status); current.append((value, status))
        passes.append(current)
    return [{'path_index': spec['path_index'], 'path': spec['path'],
        'first_metadata': first[0], 'second_metadata': second[0], 'first_status': first[1], 'second_status': second[1]}
        for spec, first, second in zip(plan, passes[0], passes[1], strict=True)]


def failure(code):
    require(code in FINITE, 'output')
    return {'schema': SCHEMA, 'binding': ACTIVE_BINDING, 'failure_code': code,
        'claim_state': CLAIM_STATE, 'deadline_fired': DEADLINE_FIRED, 'attempt_reusable': False, **FALSE_FLAGS}


def validate_result(value, args, helper):
    require(type(value) is dict and set(value) == {'schema', 'diagnostic_complete', 'summary',
        'private_evidence_pin', 'source_code_guards_normal_return', 'claim_pin', *FALSE_FLAGS}
        and value['schema'] == SCHEMA and value['diagnostic_complete'] is True
        and value['source_code_guards_normal_return'] is True and all(value[key] is False for key in FALSE_FLAGS), 'output')
    try: helper.validate_summary(value['summary'])
    except helper.Refused: raise Refused('helper') from None
    require(value['private_evidence_pin'] == value['summary']['private_evidence_pin']
        and value['claim_pin'] == pin(canonical({'binding': binding(args), 'profile_sha256': args.profile_sha256})), 'output')
    for key in ('private_evidence_pin', 'claim_pin'):
        item = value[key]
        require(type(item) is dict and set(item) == {'byte_count', 'sha256'} and type(item['byte_count']) is int
            and 0 < item['byte_count'] <= MAX_PRIVATE and type(item['sha256']) is str
            and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'output')
    return value


def validate_output(raw, actual_exit, args, helper):
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes
        and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'output')
    value = loads(raw[:-1])
    if actual_exit == 2:
        require(type(value) is dict and set(value) == {'schema', 'binding', 'failure_code', 'claim_state',
            'deadline_fired', 'attempt_reusable', *FALSE_FLAGS} and value['schema'] == SCHEMA
            and value['binding'] == binding(args) and type(value['failure_code']) is str and value['failure_code'] in FINITE
            and value['claim_state'] in ('unallocated', 'allocated_unknown', 'consumed', 'consumed_or_unknown')
            and type(value['deadline_fired']) is bool and (not value['deadline_fired'] or value['failure_code'] == 'deadline')
            and value['attempt_reusable'] is False and all(value[key] is False for key in FALSE_FLAGS), 'output')
    else:
        require(type(value) is dict and set(value) == {'binding', 'result', 'report_pin'}
            and value['binding'] == binding(args), 'output')
        validate_result(value['result'], args, helper)
        require(value['report_pin'] == pin(canonical({'binding': binding(args), 'result': value['result']})), 'output')
    return value


def observe(args, helper, security, codes, deadline):
    with Store(security) as store:
        claim_pin = store.write('claim.json', canonical({'binding': binding(args), 'profile_sha256': args.profile_sha256}))
        nonce = os.urandom(32).hex()
        rows = collect(helper, deadline)
        try: summary, private = helper.inspect_metadata(rows, uid=os.getuid(), transport_nonce=nonce)
        except helper.Refused: raise Refused('helper') from None
        private_raw = canonical(private); require(len(private_raw) <= MAX_PRIVATE, 'bound')
        require(summary['private_evidence_pin'] == pin(private_raw), 'output')
        codes.close(); budget(deadline)
        private_pin = store.write('metadata-private.json', private_raw)
        result = {'schema': SCHEMA, 'diagnostic_complete': True, 'summary': summary,
            'private_evidence_pin': private_pin, 'source_code_guards_normal_return': True,
            'claim_pin': claim_pin, **FALSE_FLAGS}
        validate_result(result, args, helper); preflight(args, helper, deadline)
        report = {'binding': binding(args), 'result': result}
        report_pin = store.write('report.json', canonical(report)); budget(deadline)
        packet = {**report, 'report_pin': report_pin}
        validate_output(canonical(packet) + b'\n', 0, args, helper); return packet


class Parser(argparse.ArgumentParser):
    def error(self, message): raise Refused('arguments')


def main(argv=None):
    global ACTIVE_BINDING
    parser = Parser(add_help=False); parser.add_argument('operation', choices=('observe', 'validate', 'profile'))
    for name in ('expected-head', 'caller-sha256', 'helper-sha256', 'profile-sha256'): parser.add_argument('--' + name)
    parser.add_argument('--actual-exit', type=int); args = parser.parse_args(argv)
    deadline = time.monotonic() + SECONDS
    signal.signal(signal.SIGALRM, expire); signal.setitimer(signal.ITIMER_REAL, budget(deadline))
    if args.operation != 'profile': ACTIVE_BINDING = binding(args)
    with ExitStack() as codes:
        helper, security = load_modules(codes, HELPER_SHA256)
        if args.operation == 'profile':
            require(all(getattr(args, name) is None for name in ('expected_head', 'caller_sha256',
                'helper_sha256', 'profile_sha256', 'actual_exit')), 'arguments')
            return profile_record(helper)
        codes.enter_context(HeldCode(SOURCE, args.caller_sha256))
        preflight(args, helper, deadline)
        if args.operation == 'validate':
            raw = sys.stdin.buffer.read(MAX_OUTPUT + 1)
            validate_output(raw, args.actual_exit, args, helper); return {'output_authenticated': True,
                'accepted_observation': args.actual_exit == 0, 'original_stdout_pin': pin(raw),
                'observation': loads(raw[:-1]), **FALSE_FLAGS}
        require(args.actual_exit is None, 'arguments')
        return observe(args, helper, security, codes, deadline)


if __name__ == '__main__':
    try:
        value = main(); raw = canonical(value) + b'\n'; require(len(raw) <= MAX_OUTPUT, 'bound')
        sys.stdout.buffer.write(raw); raise SystemExit(0)
    except SystemExit: raise
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure(finite(error))) + b'\n'); raise SystemExit(2)
