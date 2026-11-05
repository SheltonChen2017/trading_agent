"""One-use, offline preparation of the old QCOM-restored six-universe extension.

No QC/provider client or credential reader exists here. A committed run decision
must bind this caller, its source inventory, clean HEAD and native policy before
the sole prepare invocation. Validation consumes original stdout only, never a
spent control. The private output is not proof of current cloud readiness.
"""
import argparse
import base64
from contextlib import ExitStack
import ctypes
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

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH = 'codex/strategy-analyst-revisions-v2'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
SOURCE = ROOT / 'scripts/prepare_arv2_r343_legacy_six.py'
INVENTORY = ROOT / 'scripts/arv2_r343_legacy_six_source_pins.json'
INVENTORY_SHA256 = '433dfb7adb661e418e81852995c0ea439552edd61eefd31f002fe4e83f9fb011'
# Leaf A is spent and holds main.py sources without the invalid-run guard (344).
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_extension/R343-20261105-B'
INPUT = ROOT / 'artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-D5/package'
PACKAGE = INPUT / 'arv2-preliminary-qc-package-411c2734da61c7d4172c4cb3'
LINEAGE = INPUT / 'arv2-october-lineage-e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9/lineage.json'
SCHEMA = 'arv2-r343-offline-legacy-six-preparation-v1'
SECONDS = 900
MAX_SOURCE = 2 * 1024 * 1024
MAX_PRIVATE = 16 * 1024 * 1024
MAX_OUTPUT = 128 * 1024
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FINITE = frozenset(('arguments', 'environment', 'git', 'source_pin', 'source_changed',
    'inventory', 'claim_spent', 'control', 'input', 'projection', 'upload', 'deadline',
    'output', 'close', 'unknown'))
FLAGS = {key: False for key in ('QC_contact', 'Safari_access', 'provider_contact',
    'credential_access', 'USB_access', 'old_operator_replayed', 'old_control_read',
    'cloud_project_verified', 'cloud_source_verified', 'cloud_objects_verified',
    'cloud_capacity_verified', 'cloud_processing_rights_verified', 'cloud_submission_permitted', 'actual_prices_verified',
    'actual_constituents_caps_verified', 'actual_holdings_path_verified',
    'strategy_result_accepted', 'point_in_time_proven', 'formal_source_admitted',
    'permanent_security_master_proven', 'paper_or_live_ready')}
CLAIM_STATE = 'unallocated'
STAGE = 'preflight'
DEPENDENCY_FAILURE = None


class Refused(ValueError):
    """A finite code only; never source rows or raw exception text."""


class RunDeadline(BaseException):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise Refused('output') from None


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def loads(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'output')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'output')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('output')))
        require(canonical(value) == raw, 'output')
        return value
    except Refused:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('output') from None


def finite(error):
    if isinstance(error, (RunDeadline, TimeoutError, subprocess.TimeoutExpired)):
        return 'deadline'
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= SECONDS, 'deadline')


def meta(info):
    values = tuple(getattr(info, key, None) for key in FIELDS)
    require(all(type(value) is int and value >= 0 for value in values), 'source_changed')
    return values


class HeldSource:
    """Original descriptors and named/held metadata plus an external byte pin."""
    def __init__(self, path, expected, deadline, directory_cache=None):
        self.path, self.expected, self.deadline = Path(path), expected, deadline
        self.chain, self.fd = [], None
        self.cache = directory_cache

    def __enter__(self):
        try:
            if self.cache is not None and Path('/') in self.cache:
                row = self.cache[Path('/')]
            else:
                parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                row = (parent, parent, '.', meta(os.fstat(parent)))
                if self.cache is not None:
                    self.cache[Path('/')] = row
            self.chain.append(row)
            parent = row[0]
            current = Path('/')
            for part in self.path.parts[1:-1]:
                budget(self.deadline)
                current /= part
                if self.cache is not None and current in self.cache:
                    row = self.cache[current]
                else:
                    before = meta(os.stat(part, dir_fd=parent, follow_symlinks=False))
                    fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    row = (fd, parent, part, before)
                    if self.cache is not None:
                        self.cache[current] = row
                fd, _, _, before = row
                self.chain.append(row)
                require(meta(os.fstat(fd)) == before and stat.S_ISDIR(before[2]), 'source_changed')
                parent = fd
            before = meta(os.stat(self.path.name, dir_fd=parent, follow_symlinks=False))
            self.fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            require(stat.S_ISREG(before[2]) and before[5] == 1
                and before[3] == os.getuid() and stat.S_IMODE(before[2]) in (0o600, 0o644)
                and 0 <= before[6] <= MAX_SOURCE and meta(os.fstat(self.fd)) == before, 'source_pin')
            self.info = before
            self.raw = os.pread(self.fd, MAX_SOURCE + 1, 0)
            require(pin(self.raw) == self.expected, 'source_pin')
            self.verify()
            return self
        except BaseException:
            self.close()
            raise

    def verify(self):
        budget(self.deadline)
        for fd, parent, name, before in self.chain:
            require(meta(os.fstat(fd)) == before == meta(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'source_changed')
        require(meta(os.fstat(self.fd)) == self.info
            == meta(os.stat(self.path.name, dir_fd=self.chain[-1][0], follow_symlinks=False))
            and pin(os.pread(self.fd, MAX_SOURCE + 1, 0)) == self.expected, 'source_changed')

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.cache is None:
            for fd, _, _, _ in reversed(self.chain):
                os.close(fd)
        self.chain.clear()

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.verify()
        finally:
            self.close()


def bootstrap(stack, deadline, caller_sha256):
    cache = {}
    def close_directories():
        for row in reversed(tuple(cache.values())):
            os.close(row[0])
        cache.clear()
    stack.callback(close_directories)
    held_self = stack.enter_context(HeldSource(SOURCE,
        {'byte_count': SOURCE.stat().st_size, 'sha256': caller_sha256}, deadline, cache))
    held_inventory = stack.enter_context(HeldSource(INVENTORY,
        {'byte_count': INVENTORY.stat().st_size, 'sha256': INVENTORY_SHA256}, deadline, cache))
    inventory = loads(held_inventory.raw, MAX_SOURCE)
    require(type(inventory) is dict and inventory.get('schema') == SCHEMA + '-sources'
        and set(inventory) == {'schema', 'files'} and type(inventory['files']) is dict
        and 20 <= len(inventory['files']) <= 300, 'inventory')
    directories = {p for relative in inventory['files'] for p in (ROOT / relative).parents}
    soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    require(soft == resource.RLIM_INFINITY or soft >= len(inventory['files']) + len(directories) + 98, 'environment')
    held, raws = [held_self, held_inventory], {}
    for relative, expected in sorted(inventory['files'].items()):
        require(type(relative) is str and not relative.startswith('/')
            and '..' not in Path(relative).parts and relative.endswith(('.py', '.json'))
            and type(expected) is dict and set(expected) == {'byte_count', 'sha256'}
            and type(expected['byte_count']) is int and expected['byte_count'] >= 0
            and type(expected['sha256']) is str and re.fullmatch('[0-9a-f]{64}', expected['sha256']), 'inventory')
        item = stack.enter_context(HeldSource(ROOT / relative, expected, deadline, cache))
        held.append(item)
        raws[relative] = item.raw
    names = {key[:-3].replace('/', '.').removesuffix('.__init__'): key
        for key in raws if key.endswith('.py')}
    require_fresh_modules(names)
    class SourceLoader(Loader):
        def __init__(self, relative):
            self.relative = relative
        def create_module(self, spec):
            return None
        def exec_module(self, module):
            module.__file__ = str(ROOT / self.relative)
            if self.relative.endswith('/__init__.py'):
                module.__path__ = [str((ROOT / self.relative).parent)]
            exec(compile(raws[self.relative], str(ROOT / self.relative), 'exec'), module.__dict__)
    class SourceFinder(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == 'scripts':
                spec = ModuleSpec(fullname, loader=None, is_package=True)
                spec.submodule_search_locations = [str(ROOT / 'scripts')]
                return spec
            if fullname in names:
                relative = names[fullname]
                return spec_from_loader(fullname, SourceLoader(relative),
                    origin=str(ROOT / relative), is_package=relative.endswith('/__init__.py'))
            spec = PathFinder.find_spec(fullname, path)
            origin = None if spec is None else spec.origin
            require(not (type(origin) is str and Path(origin).is_absolute()
                and Path(origin).is_relative_to(ROOT)), 'source_pin')
            return None
    finder = SourceFinder()
    sys.meta_path.insert(0, finder)
    stack.callback(lambda: sys.meta_path.remove(finder) if finder in sys.meta_path else None)
    security = importlib.import_module('scripts.arv2_relocation_security')
    for item in held:
        item.security = public_source_security(item.fd, security)
    def verify():
        for item in held:
            item.verify()
            require(public_source_security(item.fd, security) == item.security, 'source_changed')
    roles = {name: importlib.import_module(module) for name, module in {
        'input': 'scripts.arv2_r338_quarantine_input_v2',
        'projection': 'scripts.arv2_r343_legacy_six_projection',
        'compact': 'research.analyst_revisions_v2_qc.accepted_risk_preliminary_package',
    }.items()}
    roles.update(security=security, raws=raws, verify=verify)
    verify()
    return roles


def public_source_security(fd, security):
    """Public tracked code: empty ACL and bounded, fully observed xattrs.

    This is not the private-evidence allowlist. Private package/lineage/control
    still use the unchanged stricter security.snapshot policy. No attribute is
    removed or ignored; current names/values are held fingerprints, not a claim
    of historical security continuity or approval of a new private source.
    """
    before = meta(os.fstat(fd))
    native = security._native()
    security._require_empty_acl(native, fd)
    def current_names():
        buffer = ctypes.create_string_buffer(8192)
        count = native.flistxattr(fd, buffer, 8192, security.XATTR_SHOWCOMPRESSION)
        require(type(count) is int and 0 <= count <= 8192, 'source_pin')
        if count == 0:
            return ()
        raw = buffer.raw[:count]
        require(raw.endswith(b'\0'), 'source_pin')
        names = tuple(sorted(raw[:-1].split(b'\0')))
        require(len(names) <= 32 and len(set(names)) == len(names)
            and all(0 < len(name) <= 255 for name in names), 'source_pin')
        return names
    names = current_names()
    rows = []
    remaining = 65536
    for name in names:
        buffer = ctypes.create_string_buffer(max(1, remaining))
        count = native.fgetxattr(fd, name, buffer, remaining, 0, security.XATTR_SHOWCOMPRESSION)
        require(type(count) is int and 0 <= count <= remaining, 'source_pin')
        rows.append([name.hex(), pin(buffer.raw[:count])])
        remaining -= count
    require(current_names() == names and meta(os.fstat(fd)) == before, 'source_changed')
    security._require_empty_acl(native, fd)
    return sha(canonical(rows))


def require_fresh_modules(names):
    require('scripts' not in sys.modules and not any(name in sys.modules for name in names), 'environment')


def dependency_problem(error, roles, stage):
    global DEPENDENCY_FAILURE
    if type(error) is Refused:
        raise error
    if isinstance(error, (RunDeadline, TimeoutError, subprocess.TimeoutExpired)):
        raise Refused('deadline') from None
    for name in ('input', 'projection'):
        module = roles[name]
        if type(error) is getattr(module, 'Refused', None):
            args = BaseException.args.__get__(error)
            if len(args) == 1 and type(args[0]) is str and args[0] in module.FINITE:
                DEPENDENCY_FAILURE = {'module': name, 'code': args[0]}
                raise Refused('deadline' if args[0] == 'deadline' else stage) from None
    raise Refused(stage if stage in FINITE else 'unknown') from None


class Store:
    """Exclusively allocated own control; no cleanup, overwrites or retries."""
    NAMES = frozenset(('claim.json', 'preparation-started.json', 'submission-private.json', 'report.json', 'failure.json'))
    def __init__(self, security):
        self.security, self.chain, self.leaves = security, [], []
        self.fd = None

    def __enter__(self):
        global CLAIM_STATE
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.chain.append((parent, parent, '.', meta(os.fstat(parent)), None))
            current = Path('/')
            for part in CONTROL.parts[1:]:
                current /= part
                if current in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent)
                        if current == CONTROL:
                            CLAIM_STATE = 'allocated_unknown'
                        os.fsync(parent)
                        old = self.chain[-1]
                        after = meta(os.fstat(parent))
                        require(all(after[index] == old[3][index] for index in (0, 1, 2, 3, 4, 9))
                            and (old[4] is None or self.security.snapshot(parent) == old[4]), 'control')
                        self.chain[-1] = (old[0], old[1], old[2], after, old[4])
                    except FileExistsError:
                        if current == CONTROL:
                            CLAIM_STATE = 'consumed_or_unknown'
                            raise Refused('claim_spent') from None
                before = meta(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.chain.append((fd, parent, part, before, None))
                checked = current == ROOT or ROOT in current.parents
                require(meta(os.fstat(fd)) == before and stat.S_ISDIR(before[2])
                    and (not checked or (before[3] == os.getuid()
                    and stat.S_IMODE(before[2]) == (0o755 if current == ROOT else 0o700))), 'control')
                self.chain[-1] = (fd, parent, part, before,
                    self.security.snapshot(fd) if checked else None)
                parent = fd
            self.fd = parent
            self.refresh()
            self.verify()
            return self
        except BaseException:
            self.close()
            raise

    def refresh(self):
        fd, parent, name, _, security = self.chain[-1]
        self.chain[-1] = (fd, parent, name, meta(os.fstat(fd)), security)

    def verify(self):
        require(self.fd is not None and set(os.listdir(self.fd)) == {row[0] for row in self.leaves}, 'control')
        for fd, parent, name, observed, security in self.chain:
            require(meta(os.fstat(fd)) == observed == meta(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'control')
            if security is not None:
                require(self.security.snapshot(fd) == security, 'control')
        for name, fd, observed, security, expected in self.leaves:
            require(meta(os.fstat(fd)) == observed == meta(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and stat.S_ISREG(observed[2]) and stat.S_IMODE(observed[2]) == 0o600
                and observed[3] == os.getuid() and observed[5] == 1
                and self.security.snapshot(fd) == security
                and pin(os.pread(fd, expected['byte_count'] + 1, 0)) == expected, 'control')

    def write(self, name, raw):
        global CLAIM_STATE
        require(name in self.NAMES and type(raw) is bytes and 0 < len(raw) <= MAX_PRIVATE, 'output')
        self.verify()
        before = self.chain[-1][3]
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:])
                require(count > 0, 'output')
                offset += count
            os.fsync(fd)
            observed = meta(os.fstat(fd))
            require(os.pread(fd, len(raw) + 1, 0) == raw, 'output')
            after = meta(os.fstat(self.fd))
            require(all(after[index] == before[index] for index in (0, 1, 2, 3, 4, 9))
                and self.security.snapshot(self.fd) == self.chain[-1][4], 'control')
            self.leaves.append((name, fd, observed, self.security.snapshot(fd), pin(raw)))
            fd = None
            self.refresh()
            os.fsync(self.fd)
            self.verify()
            if name == 'claim.json':
                CLAIM_STATE = 'consumed'
            return pin(raw)
        finally:
            if fd is not None:
                os.close(fd)

    def close(self):
        for _, fd, _, _, _ in self.leaves:
            os.close(fd)
        self.leaves.clear()
        for fd, _, _, _, _ in reversed(self.chain):
            os.close(fd)
        self.chain.clear()
        self.fd = None

    def __exit__(self, *_):
        try:
            self.verify()
        finally:
            self.close()


def native_profile():
    result = '(version 1)(allow default)(deny network*)'
    for path in ('/Volumes', '/Users/sheltonchen/Library/Keychains', '/Library/Keychains'):
        result += '(deny file-read* file-write* (subpath ' + json.dumps(path) + '))'
    result += '(deny process-exec (literal "/usr/bin/security"))'
    result += '(deny file-read-data (regex "[.]pyc$"))'
    result += '(deny file-write* (require-all (require-not (subpath ' + json.dumps(str(CONTROL)) + '))'
    result += '(require-not (literal ' + json.dumps(str(CONTROL.parent)) + '))'
    result += '(require-not (subpath ' + json.dumps(str(ROOT / '.pytest_cache/r343-root')) + '))'
    result += '(require-not (literal "/dev/null"))))'
    ancestors = {p for leaf in (PACKAGE, LINEAGE, CONTROL) for p in (*leaf.parents, leaf)
        if p == ROOT / 'artifacts' or ROOT / 'artifacts' in p.parents}
    result += '(deny file-read* (require-all (subpath ' + json.dumps(str(ROOT / 'artifacts')) + ')'
    result += '(require-not (subpath ' + json.dumps(str(PACKAGE)) + '))'
    result += '(require-not (subpath ' + json.dumps(str(CONTROL)) + '))'
    result += ''.join('(require-not (literal ' + json.dumps(str(p)) + '))' for p in sorted(ancestors)) + '))'
    return result


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': PYTHON,
        'source_inventory_sha256': INVENTORY_SHA256, 'control': str(CONTROL),
        'input_package_directory': str(PACKAGE), 'input_lineage': str(LINEAGE),
        'native_policy_sha256': sha(native_profile().encode()), 'seconds': SECONDS,
        'maximum_private_bytes': MAX_PRIVATE, 'maximum_output_bytes': MAX_OUTPUT,
        'ar_percents': [80, 100, 120, 140, 160, 180, 200],
        'maximum_launch_attempts_per_candidate': 3,
        'candidate_policy': 'new_R343_identities_never_reuse_spent_R260_to_R266_claims_or_projects',
        'future_submission_gate': 'QC_hold_release_then_fresh_rights_account_privacy_idle_capacity_exact_source_input_project_run_freeze',
        'result_protocol': 'actual_zero_exit_and_matching_source_receipt_terminal_and_bounded_four_statistic_authentication_or_three_legacy_statistics_when_run_valid_false',
        'period_interpretation': 'related_R223_R224_already_inspected_2026_through_Sep25;later_sessions_not_automatically_untouched;exploratory_only',
        'evaluation_first': '2021-01-04', 'valuation_end': '2026-10-13',
        'old_controls': 'never_read_or_replayed', 'source_guard_return_before_publication': True,
        'public_source_security': 'held_external_bytes_full10metadata_empty_native_ACL_all_bounded_current_xattr_names_and_values_fingerprinted_no_attribute_change',
        'private_input_security': 'unchanged_r338_v2_empty_ACL_provenance_only_xattr_policy_and_full_named_held_metadata',
        'purpose': 'genuine_October_bound_old_economics_offline_submission_package', **FLAGS}


def binding(args):
    require(all(type(getattr(args, key, None)) is str and re.fullmatch('[0-9a-f]{64}' if key != 'expected_head' else '[0-9a-f]{40}',
        getattr(args, key)) for key in ('expected_head', 'caller_sha256', 'profile_sha256')), 'arguments')
    require(args.profile_sha256 == sha(canonical(profile_record())), 'arguments')
    return {'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}


def safe_env():
    support = ROOT / '.pytest_cache/r343-root'
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(support / 'tmp'), 'SQLITE_TMPDIR': str(support / 'tmp'),
        'XDG_CACHE_HOME': str(support / 'cache'),
        'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
        'GIT_OPTIONAL_LOCKS': '0'}


def validate_environment(environment):
    expected = safe_env()
    require(type(environment) is dict and all(environment.get(key) == value for key, value in expected.items())
        and set(environment) <= set(expected) | {'__CF_USER_TEXT_ENCODING'}
        and ('__CF_USER_TEXT_ENCODING' not in environment
            or environment['__CF_USER_TEXT_ENCODING'] == f'0x{os.getuid():X}:0x0:0x0'), 'environment')
    return expected


def preflight(args, deadline):
    budget(deadline)
    binding(args)
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and sys.flags.isolated == 1 and sys.dont_write_bytecode
        and Path(sys.executable) == Path(PYTHON) and Path.cwd() == ROOT
        and ROOT.resolve() == ROOT, 'environment')
    expected_env = validate_environment(dict(os.environ))
    for key in ('TMPDIR', 'SQLITE_TMPDIR', 'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX'):
        path = Path(expected_env[key])
        require(path.is_dir() and path.resolve() == path, 'environment')
    disk = os.statvfs(ROOT)
    require(disk.f_bavail * disk.f_frsize >= 512 * 1024 * 1024, 'environment')
    require(not any(name == 'assistant.dispatch_fence' or name == 'AlgorithmImports'
        or name.startswith(('QuantConnect', 'quantconnect', 'qc.client')) for name in sys.modules), 'environment')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
            (['branch', '--show-current'], BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
            (['status', '--porcelain'], '')):
        value = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, capture_output=True,
            env=expected_env,
            timeout=min(10, max(.1, deadline - time.monotonic())), check=False)
        require(value.returncode == 0 and value.stderr == b'' and value.stdout.decode('ascii').strip() == expected, 'git')


def prepare(args, deadline):
    global STAGE
    preflight(args, deadline)
    with ExitStack() as controls:
        with ExitStack() as sources:
            roles = bootstrap(sources, deadline, args.caller_sha256)
            store = controls.enter_context(Store(roles['security']))
            claim_pin = store.write('claim.json', canonical({'schema': SCHEMA + '-claim', 'binding': binding(args),
                'profile': profile_record(), 'claimed_at': datetime.now(timezone.utc).isoformat()}))
            store.write('preparation-started.json', canonical({'schema': SCHEMA, 'stage': 'genuine_input_entry'}))
            private_nonce = os.urandom(32).hex()
            STAGE = 'input'
            try:
                with roles['input'].GenuineInput(deadline=deadline) as fresh:
                    fresh._libraries()
                    STAGE = 'projection'
                    projection = roles['projection']
                    source_pairs = tuple((name, roles['raws']['research/analyst_revisions_v2_qc/' + name])
                        for name in sorted(projection.HOST_SOURCE_PINS))
                    prepared = projection.prepare(fresh._wrapped, axis=fresh.axis, bindings=fresh.bindings,
                        source_pairs=source_pairs,
                        reporting_source=roles['raws']['research/analyst_revisions_v2_qc/legacy_six_october_reporting.py'],
                        deadline=min(deadline, time.monotonic() + projection.MAX_SECONDS))
                    require(projection.validate_summary(prepared['summary']) == prepared['summary'], 'projection')
                    STAGE = 'upload'
                    uploads = []
                    for item, raw in roles['compact'].iter_accepted_risk_preliminary_upload_objects(fresh._package):
                        budget(deadline)
                        require(type(raw) is bytes and pin(raw) == {'byte_count': item.byte_count,
                            'sha256': item.content_sha256}, 'upload')
                        uploads.append({'descriptor': item.to_record(),
                            'payload_base64': base64.b64encode(raw).decode('ascii')})
                    require(uploads and uploads[-1]['descriptor']['activation_manifest'] is True, 'upload')
                    receipt = fresh.receipt()
                    private = {'schema': SCHEMA + '-submission', 'binding': binding(args),
                        'claim_pin': claim_pin, 'private_transport_nonce': private_nonce,
                        'input_receipt': receipt, 'prepared': prepared['bundle'], 'upload_objects': uploads,
                        'submission_candidates': [{'candidate_id': f'R343-AR{percent:03d}',
                            'ar_percent': percent,
                            'project_name': f'ARV2 R343 LEGACY SIX AR{percent} 2021 2026 OCT13',
                            'backtest_name': f'ARV2 R343 AR{percent} old-rules through 2026-10-13 A1',
                            'maximum_launch_attempts': 3, 'launch_attempts_consumed': 0,
                            'submission_permitted': False} for percent in (80, 100, 120, 140, 160, 180, 200)],
                        'upload_policy': 'exact_payloads_first_readback_activation_last_no_upload_authority', **FLAGS}
                    private_raw = canonical(private)
                    require(len(private_raw) <= MAX_PRIVATE, 'output')
                    summary = prepared['summary']
                STAGE = 'source_return'
                roles['verify']()
            except RunDeadline:
                raise
            except BaseException as error:
                dependency_problem(error, roles, STAGE)
        # Both input and held-code contexts have NOW returned normally. The
        # exclusive Store retains its original descriptors through publication.
        STAGE = 'publication'
        private_pin = store.write('submission-private.json', private_raw)
        result = {'schema': SCHEMA + '-result', 'binding': binding(args),
            'offline_submission_package_prepared': True, 'attempt_consumed': True,
            'private_pin': private_pin, 'source_summary': summary,
            'input_package_sha256': roles['input'].PACKAGE_SHA256,
            'input_lineage_sha256': roles['input'].LINEAGE_SHA256,
            'source_guard_returned': True, 'input_guard_returned': True,
            'actual_upload_object_count': len(uploads), **FLAGS}
        report = {'binding': binding(args), 'result': result}
        report_pin = store.write('report.json', canonical(report))
        store.verify()
    STAGE = 'complete'
    return {**report, 'report_pin': report_pin}


def validate_output(raw, actual_exit, args, *, summary_validator):
    require(type(actual_exit) is int and actual_exit == 0 and type(raw) is bytes
        and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'output')
    value = loads(raw[:-1], MAX_OUTPUT)
    require(type(value) is dict and set(value) == {'binding', 'result', 'report_pin'}
        and value['binding'] == binding(args)
        and value['report_pin'] == pin(canonical({'binding': value['binding'], 'result': value['result']})), 'output')
    result = value['result']
    require(type(result) is dict and set(result) == {'schema', 'binding', 'offline_submission_package_prepared',
        'attempt_consumed', 'private_pin', 'source_summary', 'input_package_sha256', 'input_lineage_sha256',
        'source_guard_returned', 'input_guard_returned', 'actual_upload_object_count', *FLAGS}
        and result['schema'] == SCHEMA + '-result' and result['binding'] == binding(args)
        and all(result[key] is True for key in ('offline_submission_package_prepared', 'attempt_consumed',
            'source_guard_returned', 'input_guard_returned'))
        and all(result[key] is False for key in FLAGS)
        and result['input_package_sha256'] == '411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
        and result['input_lineage_sha256'] == 'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'
        and type(result['actual_upload_object_count']) is int and 6 <= result['actual_upload_object_count'] <= 96, 'output')
    p = result['private_pin']
    require(type(p) is dict and set(p) == {'byte_count', 'sha256'} and type(p['byte_count']) is int
        and 0 < p['byte_count'] <= MAX_PRIVATE and type(p['sha256']) is str
        and re.fullmatch('[0-9a-f]{64}', p['sha256']), 'output')
    require(type(result['source_summary']) is dict and len(canonical(result['source_summary'])) <= 64 * 1024, 'output')
    try:
        require(summary_validator(result['source_summary']) == result['source_summary'], 'output')
    except Exception:
        raise Refused('output') from None
    return {'output_envelope_validated': True, 'accepted': True, 'result': result,
        'qualification': 'original_stdout_and_actual_exit_only_not_independent_private_file_attestation'}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('arguments')


def main():
    parser = Parser(add_help=False)
    parser.add_argument('mode', choices=('profile', 'prepare', 'validate'))
    for name in ('expected-head', 'caller-sha256', 'profile-sha256'):
        parser.add_argument('--' + name)
    parser.add_argument('--actual-exit', type=int)
    args = parser.parse_args()
    if args.mode == 'profile':
        require(all(getattr(args, key) is None for key in ('expected_head', 'caller_sha256', 'profile_sha256', 'actual_exit')), 'arguments')
        return profile_record()
    deadline = time.monotonic() + (30 if args.mode == 'validate' else SECONDS)
    def expired(*_):
        raise RunDeadline()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, deadline - time.monotonic())
    if args.mode == 'validate':
        preflight(args, deadline)
        with ExitStack() as sources:
            roles = bootstrap(sources, deadline, args.caller_sha256)
            answer = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args,
                summary_validator=roles['projection'].validate_summary)
            roles['verify']()
        return answer
    require(args.actual_exit is None, 'arguments')
    return prepare(args, deadline)


if __name__ == '__main__':
    try:
        answer = main()
        raw = canonical(answer) + b'\n'
        require(len(raw) <= MAX_OUTPUT, 'output')
        sys.stdout.buffer.write(raw)
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'schema': SCHEMA + '-failure', 'stage': STAGE,
            'failure_code': finite(error), 'claim_state': CLAIM_STATE,
            'dependency_failure': DEPENDENCY_FAILURE, **FLAGS}) + b'\n')
        raise SystemExit(2)
