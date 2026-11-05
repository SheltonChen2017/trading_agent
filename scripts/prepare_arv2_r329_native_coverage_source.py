"""One offline public-code stage for the new R329 native-coverage observation.

This creates no QC project/job and reads no retained private source or old
control. Only a separately frozen operational caller may consume its new DATA.
Actual exit zero and the externally matched bounded public report are required;
a report left by a late failure is not an admissible stage.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from importlib.machinery import PathFinder
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

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
GENERATOR_SHA256 = 'd1058aefd6ca879f2c6d4879d5993697e4f721c81fe012a9ac5365e58faf9caf'
SECURITY_SHA256 = '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30'
# Exact public execution closure plus transform-only plain loader. These literals
# are frozen before any repository dependency is imported; no disk-derived pin.
BOOTSTRAP_PINS = {
    'scripts/arv2_r329_native_coverage_projection.py': GENERATOR_SHA256,
    'scripts/arv2_relocation_security.py': SECURITY_SHA256,
    'scripts/arv2_r298_native_price_source_projection.py': 'a34385be7b5dbf95c30a669fc251689edbe3e8e0429386b188d2ac103907da3e',
    'scripts/arv2_r327_available_history_period.py': '722cffeae9fbebcd9bca656c8994273d2b1fb36f6d3e269a018c8fb18e5b7b18',
    'scripts/arv2_r298_ae_source_binding.py': 'd67e13dfb73885a335345648a4149f1968b3ba2aebc26405ea409681a1be6bb1',
    'research/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'research/analyst_revisions_v2_qc/__init__.py': 'ce8f07aeab0358f5eb3241190169d4f967a5423dc88719f0783a83d010d43dcc',
    'research/analyst_revisions_v2_qc/accepted_risk_preliminary_rating_policy.py': '7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd',
    'research/analyst_revisions_v2_qc/accepted_risk_preliminary_rating_evaluator.py': '2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910',
    'research/analyst_revisions_v2_qc/accepted_risk_preliminary_qc_figi.py': '4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9',
    'research/analyst_revisions_v2_qc/accepted_risk_six_universe_order_qc_runtime.py': '84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a',
    'research/analyst_revisions_v2_qc/newrule_plain_input_runtime.py': 'bc07c0bebc141ecad38c774a52ea3bddaad4664a7dd85ccf47581572ef9beb8f',
    'research/analyst_revisions_v2_qc/newrule_native_price_source_diagnostic.py': '57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697',
    'research/analyst_revisions_v2_qc/newrule_native_price_book_publication.py': '03d100e962b98cd8b174d947a33636e421692445422c0dcce2282b46015435e2',
    'research/analyst_revisions_v2_qc/newrule_native_price_book_runtime.py': '76b2a193fe1b8de9c9f8c598464edc2d0058b61aa690e13cc6216051f862a3f6',
    'research/analyst_revisions_v2_qc/newrule_available_history_native_coverage.py': 'f0f74cdc920f79d13e1e89ac0e60f71f993edeb72d2ac6853e13fc7a83798202',
    'research/analyst_revisions_v2_qc/accepted_risk_order_level_core.py': '063ed8fb7024c879a640780c07723c7edfb95665acc711d02fc8be0d964e965f',
    'research/analyst_revisions_v2_qc/accepted_risk_order_level_forced_exit.py': '21ef6978d7c26b833b0ec553298584c360f03d602f3c244f2fc8645bd113ec3f',
    'research/analyst_revisions_v2_qc/accepted_risk_order_level_input_runtime.py': 'a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee',
    'research/analyst_revisions_v2_qc/accepted_risk_sequential_r055_score.py': '6c34940cb821c04554e9073a77e013d306d059a688dbac02fe5b0511d91d217b',
    'research/analyst_revisions_v2_qc/accepted_risk_simulated_moo_executor.py': 'e2f4b5508427e6f4c5bf20813e255cecae1d8652177391eeb226dc56084c5fb7',
    'research/analyst_revisions_v2_qc/accepted_risk_six_universe_gate.py': '158445ae072ef6c66a49b2069c53b02ee805adbccbb9a522650ccd3a72fa9f1e',
    'research/analyst_revisions_v2_qc/accepted_risk_six_universe_gate_evaluator.py': 'd0f1ba677c63f2caf3703cd7a4df5fbc8ef6225aac4a2357c7d54003da73eb1c',
    'research/analyst_revisions_v2_qc/accepted_risk_six_universe_order_targets.py': '0b280fdc1ebcb5f8ab073ff78f3008057e86db14b6254145bc5f86e18d2e5ea0',
}


def _bootstrap():
    """Stdlib-only pinned public imports; native ACL/xattrs follow before claim.

    This authenticates current source endpoints and import paths. It is not
    whole-interpreter integrity or protection against arbitrary same-user races.
    """
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
    def record(info):
        return tuple(getattr(info, field, None) for field in fields)
    endpoints = {}
    for relative, expected in BOOTSTRAP_PINS.items():
        opened, directories = [], []
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            opened.append(fd)
            for component in (ROOT / relative).parts[1:-1]:
                before = record(os.stat(component, dir_fd=fd, follow_symlinks=False))
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                opened.append(child)
                if record(os.fstat(child)) != before:
                    raise RuntimeError('public_bootstrap')
                directories.append((fd, component, child, before))
                fd = child
            name = Path(relative).name
            before = record(os.stat(name, dir_fd=fd, follow_symlinks=False))
            leaf = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            opened.append(leaf)
            if not stat.S_ISREG(before[2]) or not 0 <= before[6] <= 131072 or before[5] != 1 \
                    or record(os.fstat(leaf)) != before:
                raise RuntimeError('public_bootstrap')
            raw = os.pread(leaf, 131073, 0)
            if len(raw) != before[6] or hashlib.sha256(raw).hexdigest() != expected \
                    or record(os.fstat(leaf)) != before \
                    or record(os.stat(name, dir_fd=fd, follow_symlinks=False)) != before:
                raise RuntimeError('public_bootstrap')
            for parent, component, child, before in directories:
                if record(os.fstat(child)) != before \
                        or record(os.stat(component, dir_fd=parent, follow_symlinks=False)) != before:
                    raise RuntimeError('public_bootstrap')
            endpoints[relative] = record(os.fstat(leaf))
        finally:
            for fd in reversed(opened):
                os.close(fd)
    # Script execution otherwise puts ROOT/scripts first, permitting unpinned
    # flat aliases. Resolve only the fixed namespace/package paths instead.
    sys.path[:] = [str(ROOT), *(item for item in sys.path if item and Path(item).is_absolute()
        and Path(item) != ROOT and ROOT not in Path(item).parents)]
    namespace = PathFinder.find_spec('scripts', sys.path)
    if namespace is None or namespace.origin is not None \
            or tuple(namespace.submodule_search_locations) != (str(ROOT / 'scripts'),):
        raise RuntimeError('public_bootstrap')
    if 'scripts' in sys.modules and tuple(sys.modules['scripts'].__path__) != (str(ROOT / 'scripts'),):
        raise RuntimeError('public_bootstrap')
    for relative in BOOTSTRAP_PINS:
        path = ROOT / relative
        parts = Path(relative).with_suffix('').parts
        name = '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)
        parent = path.parent.parent if path.name == '__init__.py' else path.parent
        spec = PathFinder.find_spec(name, [str(parent)])
        if spec is None or spec.origin != str(path):
            raise RuntimeError('public_bootstrap')
        if name in sys.modules:
            if __name__ == '__main__' or getattr(sys.modules[name], '__file__', None) != str(path):
                raise RuntimeError('public_bootstrap')
        if path.name != '__init__.py' and (path.stem in sys.modules or PathFinder.find_spec(path.stem, sys.path) is not None):
            raise RuntimeError('public_bootstrap')
    return endpoints


try:
    if __name__ == '__main__':
        allowed = {'PATH', 'TMPDIR', 'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE',
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD', 'LC_ALL', 'LANG', '__CF_USER_TEXT_ENCODING'}
        if not set(os.environ) <= allowed:
            raise RuntimeError('public_bootstrap')
    BOOTSTRAP_METADATA = _bootstrap()
except BaseException:
    if __name__ == '__main__':
        sys.stdout.buffer.write(b'{"failure_code":"public_bootstrap"}\n')
        raise SystemExit(2)
    raise RuntimeError('public_bootstrap') from None

from scripts import arv2_r329_native_coverage_projection as projection
from scripts import arv2_relocation_security as security

SOURCE = ROOT / 'scripts/prepare_arv2_r329_native_coverage_source.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_available_history_native_coverage_source/R329-20261028-A'
BRANCH = 'codex/strategy-analyst-revisions-v2'
PYTHON = Path('/Users/sheltonchen/.venvs/trading_agent-py313/bin/python')
SCHEMA = 'arv2-r329-offline-native-coverage-source-stage-v1'
PROJECT_ID = 38522505
EXPECTED_PROJECTION_PIN = {'byte_count': 2495, 'sha256': 'a3a3a4a1a46b2760bc56964a89088a83f23c1918f74f5998c3e73d995fe64dba'}
EXPECTED_PROFILE_PIN = {'byte_count': 7635, 'sha256': 'bd22b98f02de9a81266e3768534aa5364a8c3d633220bd5b9d20794389a6ce5c'}
SECONDS, EXTERNAL_SECONDS, MAX_PUBLIC_OUTPUT, MAX_SOURCE_BYTES = 180, 210, 65536, 131072
MAX_OWNED_FILES = 16  # claim +11 cloud files +profile +projection +report +failure
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
    'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FLAGS = stat.UF_TRACKED | stat.UF_HIDDEN
FALSE_FLAGS = {'QC_contact': False, 'Safari_access': False, 'provider_contact': False,
    'credential_access': False, 'private_source_DATA_read': False, 'old_control_read': False,
    'project_access_verified': False, 'source_book_recreated': False, 'source_data_exported': False,
    'price_coverage_admitted': False, 'QC_transfer_granted': False, 'new_launch_attempt_granted': False,
    'source_or_processing_rights_granted': False, 'point_in_time_proven': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False, 'continuous_integrity_proven': False}
FINITE = frozenset(('host', 'arguments', 'environment', 'git_state', 'source_pin', 'source_changed',
    'source_bound', 'path', 'security', 'deadline', 'claim_spent', 'output_changed', 'output_write',
    'output_bound', 'projection', 'output', 'os_error', 'unknown'))


class Refused(ValueError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is security.Refusal:
        return 'security'
    if type(error) is projection.Refused:
        return 'projection'
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    value = deadline - time.monotonic()
    require(0 < value <= SECONDS, 'deadline')
    return value


@contextmanager
def alarm(deadline):
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'deadline')
    old = signal.getsignal(signal.SIGALRM)
    def expired(_signum, _frame):
        raise Refused('deadline')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, remaining(deadline))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def public_plan():
    scripts = {projection.PREDECESSOR_NAME, projection.PERIOD_NAME, projection.previous.AE_NAME}
    result = {('scripts/' if name in scripts else 'research/analyst_revisions_v2_qc/') + name: expected
        for name, expected in projection.SOURCE_PINS.items()}
    result['scripts/' + projection.PATCHER_NAME] = GENERATOR_SHA256
    result['scripts/arv2_relocation_security.py'] = SECURITY_SHA256
    require(len(result) == 14 and all(_hash(value) and BOOTSTRAP_PINS.get(name) == value
        for name, value in result.items()) and len(BOOTSTRAP_PINS) == 24, 'source_pin')
    return dict(BOOTSTRAP_PINS)


def native_profile():
    value = '(version 1)(allow default)(deny network*)'
    value += '(deny file-read-data (regex "[.]pyc$"))'
    for path in ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'):
        value += f'(deny file-read* file-write* (subpath "{path}"))'
    value += '(deny process-exec (literal "/usr/bin/security"))'
    value += '(deny file-write* (require-all ' + ''.join((
        f'(require-not (subpath "{CONTROL}"))', f'(require-not (literal "{CONTROL.parent}"))',
        f'(require-not (subpath "{ROOT / ".pytest_cache"}"))', '(require-not (literal "/dev/null"))')) + '))'
    ancestors = (ROOT / 'artifacts', ROOT / 'artifacts/analyst_revisions_v2', CONTROL.parent)
    value += f'(deny file-read* (require-all (subpath "{ROOT / "artifacts"}")' \
        + f'(require-not (subpath "{CONTROL}"))' \
        + ''.join(f'(require-not (literal "{path}"))' for path in ancestors) + '))'
    return value


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': str(PYTHON),
        'source': str(SOURCE), 'control': str(CONTROL), 'project_id': PROJECT_ID,
        'selected_public_source_pins': public_plan(), 'projector_policy_sha256': sha(canonical(projection.profile_record())),
        'expected_projection_pin': dict(EXPECTED_PROJECTION_PIN), 'expected_profile_pin': dict(EXPECTED_PROFILE_PIN),
        'source_pin_scope': 'selected_public_code_only_not_whole_interpreter_integrity',
        'seconds': SECONDS, 'external_seconds': EXTERNAL_SECONDS, 'maximum_public_output_bytes': MAX_PUBLIC_OUTPUT,
        'maximum_input_file_bytes': MAX_SOURCE_BYTES, 'maximum_owned_files': MAX_OWNED_FILES,
        'maximum_cloud_file_bytes': projection.MAX_CLOUD_FILE_BYTES,
        'maximum_total_cloud_bytes': projection.MAX_TOTAL_CLOUD_BYTES,
        'cloud_file_names': list(projection.CLOUD_NAMES), 'native_policy_sha256': sha(native_profile().encode('ascii')),
        'one_exclusive_claim_before_generation_and_staging': True,
        'public_sources_held_named_ten_field_native_security_and_hashes': True,
        'stdlib_only_public_execution_closure_pins_before_repository_imports': True,
        'fixed_package_resolution_and_no_flat_alias_imports_before_claim': True,
        'bootstrap_source_metadata_equal_again_before_claim': True, 'native_bytecode_cache_reads_denied': True,
        'external_deadline_must_cover_python_bootstrap_imports_before_internal_alarm': True,
        'outputs_original_exclusive_FDs_exact_bytes_readback_and_metadata': True,
        'directory_updates': 'only_own_successful_exclusive_create_bound_child;file_nlink_plus1;mkdir_same_or_plus1',
        'actual_exit_zero_and_matching_bounded_public_report_required': True,
        'partial_outputs_retained_no_cleanup_retry_overwrite_alternate_path': True,
        'deadline_does_not_bound_uninterruptible_IO_or_host_suspension': True, **FALSE_FLAGS}


def binding(args):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256, 'project_id': PROJECT_ID}


def _environment():
    allowed = {'PATH', 'TMPDIR', 'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD', 'LC_ALL', 'LANG', '__CF_USER_TEXT_ENCODING'}
    require(set(os.environ) <= allowed and os.environ.get('PYTHONDONTWRITEBYTECODE') == '1'
        and os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD') == '1', 'environment')
    for name in ('TMPDIR', 'PYTHONPYCACHEPREFIX'):
        value = os.environ.get(name)
        require(type(value) is str and Path(value).is_absolute()
            and ROOT / '.pytest_cache' in Path(value).parents
            and Path(value).resolve() == Path(value), 'environment')


def _git(arguments, deadline):
    try:
        result = subprocess.run(['/usr/bin/git', *arguments], cwd=str(ROOT),
            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(20, remaining(deadline)), check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Refused('git_state') from None
    require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 262144, 'git_state')
    return result.stdout


def preflight(args, deadline):
    binding(args)
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE, 'host')
    _environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], BRANCH),
        (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(_git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    require(sha(_git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()], deadline))
        == args.caller_sha256 and sha(canonical(profile_record())) == args.profile_sha256, 'source_pin')
    remaining(deadline)


def metadata(fd):
    info = os.fstat(fd)
    values = tuple(getattr(info, field, None) for field in FIELDS)
    require(all(type(value) is int and value >= 0 for value in values), 'source_changed')
    return values


def named(parent, name):
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    return tuple(getattr(info, field, None) for field in FIELDS)


def _security(fd):
    try:
        return security.snapshot(fd)
    except security.Refusal:
        raise Refused('security') from None


class DirectoryGuard:
    """Original chain FDs; only bound children created by this guard alter it."""
    def __init__(self, path, *, create=False, control=None):
        require(type(path) is Path or isinstance(path, Path), 'path')
        require(path.is_absolute() and (path == ROOT or ROOT in path.parents), 'path')
        self.control = CONTROL if control is None else control
        require(isinstance(self.control, Path) and self.control.is_absolute()
            and ROOT / 'artifacts' in self.control.parents
            and (not create or path == self.control), 'path')
        self.rows, self.fd = [], None
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.rows.append({'path': Path('/'), 'parent': fd, 'name': '.', 'fd': fd,
            'metadata': metadata(fd), 'security': None})
        try:
            parent = self.rows[0]
            for index, part in enumerate(path.parts[1:], 1):
                here = Path(*path.parts[:index + 1])
                self.verify()
                created = False
                if create and here in (self.control.parent, self.control):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent['fd'])
                        os.fsync(parent['fd'])
                        created = True
                    except FileExistsError:
                        require(here != self.control, 'claim_spent')
                before = named(parent['fd'], part)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent['fd'])
                row = {'path': here, 'parent': parent['fd'], 'name': part, 'fd': child, 'metadata': before,
                    'security': None}
                self.rows.append(row)
                row['security'] = _security(child) if here == ROOT or ROOT in here.parents else None
                self._policy(row)
                require(metadata(child) == before == named(parent['fd'], part), 'source_changed')
                if created:
                    self.own_created(parent, row, directory=True)
                parent = row
            self.fd = parent['fd']
            self.verify()
        except BaseException:
            self.close()
            raise

    def _policy(self, row):
        info = metadata(row['fd'])
        require(stat.S_ISDIR(info[2]), 'path')
        if row['path'] == ROOT or ROOT in row['path'].parents:
            require(info[3] == os.getuid() and stat.S_IMODE(info[2]) in (0o700, 0o755)
                and not info[9] & ~FLAGS and _security(row['fd']) == row['security'], 'security')
            if row['path'] == self.control.parent or self.control.parent in row['path'].parents:
                require(stat.S_IMODE(info[2]) == 0o700, 'security')

    def own_created(self, parent, child, *, directory):
        require(type(directory) is bool and child['parent'] == parent['fd']
            and metadata(child['fd']) == child['metadata'] == named(parent['fd'], child['name']), 'output_changed')
        info = child['metadata']
        require((stat.S_ISDIR(info[2]) and stat.S_IMODE(info[2]) == 0o700) if directory
            else (_regular(info, private=True) and info[6] == 0), 'output_changed')
        old, fresh = parent['metadata'], metadata(parent['fd'])
        links = (old[5], old[5] + 1) if directory else (old[5] + 1,)
        require(fresh[:5] == old[:5] and fresh[9] == old[9] and fresh[5] in links, 'output_changed')
        self._policy(parent)
        parent['metadata'] = fresh

    def verify(self):
        for row in self.rows:
            require(metadata(row['fd']) == row['metadata'] == named(row['parent'], row['name']), 'source_changed')
            self._policy(row)

    def close(self):
        failed = False
        for row in reversed(self.rows):
            try:
                os.close(row['fd'])
            except OSError:
                failed = True
        self.rows = []
        require(not failed, 'source_changed')

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.verify()
        finally:
            self.close()


def _regular(info, *, private):
    return stat.S_ISREG(info[2]) and stat.S_IMODE(info[2]) in ((0o600,) if private else (0o600, 0o644, 0o755)) \
        and info[3] == os.getuid() and info[5] == 1 and not info[9] & ~FLAGS


class PublicSources:
    def __init__(self, plan, deadline):
        self.directories, self.files, self.raw = {}, {}, {}
        try:
            for relative, expected in sorted(plan.items()):
                require(type(relative) is str and '..' not in Path(relative).parts and not Path(relative).is_absolute()
                    and relative.endswith('.py') and _hash(expected), 'path')
                path = ROOT / relative
                require(ROOT in path.parents and ROOT / 'artifacts' not in path.parents, 'path')
                if path.parent not in self.directories:
                    self.directories[path.parent] = DirectoryGuard(path.parent)
                directory = self.directories[path.parent]
                before = named(directory.fd, path.name)
                empty_init = relative == 'research/__init__.py' and expected == sha(b'')
                require(_regular(before, private=False) and (empty_init or before[6] > 0)
                    and before[6] <= MAX_SOURCE_BYTES, 'source_bound')
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory.fd)
                row = {'fd': fd, 'parent': directory.fd, 'name': path.name, 'metadata': before, 'security': None}
                self.files[relative] = row
                row['security'] = _security(fd)
                require(metadata(fd) == before == named(directory.fd, path.name), 'source_changed')
                remaining(deadline)
                raw = os.pread(fd, MAX_SOURCE_BYTES + 1, 0)
                require(len(raw) == before[6] and sha(raw) == expected, 'source_pin')
                self.raw[relative] = raw
                self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        for directory in self.directories.values():
            directory.verify()
        for row in self.files.values():
            require(metadata(row['fd']) == row['metadata'] == named(row['parent'], row['name'])
                and _security(row['fd']) == row['security'], 'source_changed')

    def close(self):
        failed = False
        for row in self.files.values():
            try:
                os.close(row['fd'])
            except OSError:
                failed = True
        self.files = {}
        for directory in self.directories.values():
            directory.close()
        self.directories = {}
        require(not failed, 'source_changed')

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.verify()
        finally:
            self.close()


class Store:
    def __init__(self):
        self.guard = DirectoryGuard(CONTROL, create=True)
        self.fd, self.files, self.failed = self.guard.fd, {}, False

    def verify(self):
        self.guard.verify()
        require(set(os.listdir(self.fd)) == set(self.files), 'output_changed')
        for row in self.files.values():
            require(metadata(row['fd']) == row['metadata'] == named(self.fd, row['name'])
                and _regular(row['metadata'], private=True) and _security(row['fd']) == row['security'], 'output_changed')

    def write(self, name, raw, deadline):
        allowed = {'claim.json', 'profile.json', 'projection.json', 'report.json', 'failure.json', *projection.CLOUD_NAMES}
        limit = projection.MAX_CLOUD_FILE_BYTES if name in projection.CLOUD_NAMES else MAX_PUBLIC_OUTPUT
        require(name in allowed and name not in self.files and len(self.files) < MAX_OWNED_FILES
            and type(raw) is bytes and 0 < len(raw) <= limit, 'output_bound')
        self.verify()
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            initial = metadata(fd)
            row = {'fd': fd, 'parent': self.fd, 'name': name, 'metadata': initial, 'security': _security(fd)}
            require(_regular(initial, private=True) and initial[6] == 0 and initial == named(self.fd, name), 'output_changed')
            self.guard.own_created(self.guard.rows[-1], row, directory=False)
            self.files[name] = row
            os.fsync(self.fd)
            view = memoryview(raw)
            while view:
                remaining(deadline)
                count = os.write(fd, view[:65536])
                require(type(count) is int and count > 0, 'output_write')
                view = view[count:]
            os.fsync(fd)
            fresh = metadata(fd)
            require(fresh[:6] == initial[:6] and fresh[9] == initial[9]
                and fresh[6] == len(raw) and _security(fd) == row['security'], 'output_changed')
            row['metadata'] = fresh
            require(os.pread(fd, len(raw) + 1, 0) == raw, 'output_write')
            self.verify()
            return pin(raw)
        except BaseException:
            if name not in self.files:
                os.close(fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        failed = False
        try:
            if kind is None and not self.failed:
                self.verify()
        finally:
            for row in self.files.values():
                try:
                    os.close(row['fd'])
                except OSError:
                    failed = True
            self.guard.close()
        require(not failed, 'output_changed')


def failure(args, error, *, consumed=False):
    return {'binding': binding(args), 'failure_code': finite(error), 'claim_consumed': consumed,
        'allocation_unknown': not consumed, **FALSE_FLAGS}


def produce(args, deadline):
    preflight(args, deadline)
    plan = {**public_plan(), SOURCE.relative_to(ROOT).as_posix(): args.caller_sha256}
    with PublicSources(plan, deadline) as sources:
        require(set(BOOTSTRAP_METADATA) == set(public_plan())
            and all(sources.files[name]['metadata'] == BOOTSTRAP_METADATA[name] for name in BOOTSTRAP_METADATA), 'source_changed')
        with Store() as store:
            store.write('claim.json', canonical(binding(args)), deadline)
            try:
                by_name = {Path(name).name: raw for name, raw in sources.raw.items()}
                generated = projection.generate(project_id=PROJECT_ID,
                    sources={name: by_name[name] for name in projection.SOURCE_PINS},
                    generator_source_bytes=by_name[projection.PATCHER_NAME], expected_generator_sha256=GENERATOR_SHA256)
                record = generated.to_record()
                require(record['project_id'] == PROJECT_ID and len(generated.source_pairs) == 11
                    and pin(generated.record_bytes) == EXPECTED_PROJECTION_PIN
                    and pin(generated.profile_bytes) == EXPECTED_PROFILE_PIN, 'projection')
                outputs = []
                for name, raw in generated.source_pairs:
                    outputs.append({'name': name, **store.write(name, raw, deadline)})
                projection_pin = store.write('projection.json', generated.record_bytes, deadline)
                profile_pin = store.write('profile.json', generated.profile_bytes, deadline)
                sources.verify()
                preflight(args, deadline)
                store.verify()
                result = {'schema': SCHEMA, 'project_id': PROJECT_ID, 'source_files': outputs,
                    'projection_record': record,
                    'projection_pin': projection_pin, 'profile_pin': profile_pin,
                    'selected_public_sources_sha256': sha(canonical(plan)),
                    'source_endpoint_metadata_sha256': sha(canonical({name: list(row['metadata']) for name, row in sources.files.items()})),
                    'output_endpoint_metadata_sha256': sha(canonical({name: list(row['metadata']) for name, row in store.files.items()})),
                    'source_and_output_original_FDs_postchecked': True, **FALSE_FLAGS}
                validate_result(result)
                report = canonical({'binding': binding(args), 'result': result})
                report_pin = store.write('report.json', report, deadline)
                sources.verify()
                store.verify()
                outcome = {'result': result, 'report_pin': report_pin}
            except BaseException as error:
                store.failed = True
                value = failure(args, error, consumed=True)
                try:
                    store.write('failure.json', canonical(value), deadline)
                except BaseException:
                    pass
                outcome = {'failure': value}
    return {'binding': binding(args), 'outcome': outcome}


def _pin(value, *, bound):
    return type(value) is dict and set(value) == {'byte_count', 'sha256'} \
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= bound and _hash(value['sha256'])


def validate_result(value):
    keys = {'schema', 'project_id', 'source_files', 'projection_record', 'projection_pin', 'profile_pin',
        'selected_public_sources_sha256', 'source_endpoint_metadata_sha256', 'output_endpoint_metadata_sha256',
        'source_and_output_original_FDs_postchecked', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and type(value['project_id']) is int and value['project_id'] == PROJECT_ID
        and value['source_and_output_original_FDs_postchecked'] is True
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    require(type(value['source_files']) is list and len(value['source_files']) == 11
        and all(type(row) is dict and set(row) == {'name', 'byte_count', 'sha256'} for row in value['source_files'])
        and tuple(row['name'] for row in value['source_files']) == projection.CLOUD_NAMES
        and all(_pin({key: row[key] for key in ('byte_count', 'sha256')}, bound=projection.MAX_CLOUD_FILE_BYTES)
            for row in value['source_files'])
        and sum(row['byte_count'] for row in value['source_files']) <= projection.MAX_TOTAL_CLOUD_BYTES, 'output')
    for name in ('projection_pin', 'profile_pin'):
        require(_pin(value[name], bound=MAX_PUBLIC_OUTPUT), 'output')
    require(type(value['projection_record']) is dict
        and pin(canonical(value['projection_record'])) == value['projection_pin'] == EXPECTED_PROJECTION_PIN
        and value['profile_pin'] == EXPECTED_PROFILE_PIN
        and value['source_files'] == value['projection_record'].get('source_files'), 'output')
    for name in ('selected_public_sources_sha256', 'source_endpoint_metadata_sha256', 'output_endpoint_metadata_sha256'):
        require(_hash(value[name]), 'output')
    return value


def validate_output(raw, actual_exit, args):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PUBLIC_OUTPUT and raw.endswith(b'\n')
        and raw.count(b'\n') == 1 and type(actual_exit) is int and actual_exit in (0, 2), 'output')
    def pairs(items):
        result = {}
        for name, value in items:
            require(name not in result, 'output')
            result[name] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('output')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('output') from None
    require(type(value) is dict and canonical(value) + b'\n' == raw, 'output')
    if set(value) == {'binding', 'outcome'}:
        require(value['binding'] == binding(args) and type(value['outcome']) is dict, 'output')
        outcome = value['outcome']
        if set(outcome) == {'result', 'report_pin'}:
            require(actual_exit == 0, 'output')
            validate_result(outcome['result'])
            require(outcome['result']['selected_public_sources_sha256'] == sha(canonical({**public_plan(),
                SOURCE.relative_to(ROOT).as_posix(): args.caller_sha256}))
                and outcome['report_pin'] == pin(canonical({'binding': binding(args), 'result': outcome['result']})), 'output')
            return value
        require(set(outcome) == {'failure'}, 'output')
        value = outcome['failure']
    require(actual_exit == 2 and type(value) is dict and set(value) == {'binding', 'failure_code',
        'claim_consumed', 'allocation_unknown', *FALSE_FLAGS} and value['binding'] == binding(args)
        and type(value['failure_code']) is str and value['failure_code'] in FINITE
        and type(value['claim_consumed']) is bool and value['allocation_unknown'] is (not value['claim_consumed'])
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    return value


def main(argv=None):
    class FiniteParser(argparse.ArgumentParser):
        def error(self, _message):
            raise Refused('arguments')
    parser = FiniteParser(description=__doc__)
    for name in ('expected-head', 'caller-sha256', 'profile-sha256'):
        parser.add_argument('--' + name, required=True)
    try:
        args = parser.parse_args(argv)
    except Refused:
        sys.stdout.buffer.write(b'{"failure_code":"arguments"}\n')
        return 2
    deadline = time.monotonic() + SECONDS
    try:
        with alarm(deadline):
            value = produce(args, deadline)
            code = 2 if 'failure' in value['outcome'] else 0
            raw = canonical(value) + b'\n'
            validate_output(raw, code, args)
            sys.stdout.buffer.write(raw)
            return code
    except BaseException as error:
        # Invalid CLI bindings cannot be echoed as unbounded/secret-bearing text.
        try:
            raw = canonical(failure(args, error)) + b'\n'
            validate_output(raw, 2, args)
        except BaseException:
            raw = b'{"failure_code":"arguments"}\n'
        sys.stdout.buffer.write(raw)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
