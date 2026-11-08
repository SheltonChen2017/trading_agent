"""One offline exact-public-code comparison of eleven observed Safari downloads.

The canonical path map and its external hash must be frozen before use. No
directory search, QC access, credential read, code execution, source mutation,
cleanup or retry exists here. The separately bound original descriptors and
finite Safari transport metadata remain unchanged through report publication.
"""
import argparse
from contextlib import contextmanager
import ctypes
import hashlib
from importlib.machinery import PathFinder
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
STAGE_SHA256 = '652a46b6b0db83f50cf042e1b374b9beed3192d897e5886557e48cf25a75193e'
ENTRY_DEADLINE = time.monotonic() + 60


def _bootstrap_stage():
    """Bind this one import before execution; its own bootstrap binds closure."""
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
    def record(info):
        return tuple(getattr(info, key, None) for key in fields)
    path = ROOT / 'scripts/prepare_arv2_r329_native_coverage_source.py'
    opened, rows = [], []
    try:
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        opened.append(fd)
        for part in path.parts[1:-1]:
            before = record(os.stat(part, dir_fd=fd, follow_symlinks=False))
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            opened.append(child)
            if record(os.fstat(child)) != before or not stat.S_ISDIR(before[2]):
                raise RuntimeError('public_bootstrap')
            rows.append((fd, part, child, before))
            fd = child
        before = record(os.stat(path.name, dir_fd=fd, follow_symlinks=False))
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        opened.append(leaf)
        if not stat.S_ISREG(before[2]) or before[3] != os.getuid() or before[5] != 1 \
                or not 0 < before[6] <= 131072 or record(os.fstat(leaf)) != before:
            raise RuntimeError('public_bootstrap')
        raw = os.pread(leaf, 131073, 0)
        if len(raw) != before[6] or hashlib.sha256(raw).hexdigest() != STAGE_SHA256 \
                or record(os.fstat(leaf)) != before \
                or record(os.stat(path.name, dir_fd=fd, follow_symlinks=False)) != before:
            raise RuntimeError('public_bootstrap')
        for parent, name, child, before in rows:
            if record(os.fstat(child)) != before or record(os.stat(name, dir_fd=parent, follow_symlinks=False)) != before:
                raise RuntimeError('public_bootstrap')
        leaf_metadata = record(os.fstat(leaf))
    finally:
        for fd in reversed(opened):
            os.close(fd)
    sys.path[:] = [str(ROOT), *(item for item in sys.path if item and Path(item).is_absolute()
        and Path(item) != ROOT and ROOT not in Path(item).parents)]
    spec = PathFinder.find_spec('scripts', sys.path)
    if spec is None or spec.origin is not None or tuple(spec.submodule_search_locations) != (str(ROOT / 'scripts'),):
        raise RuntimeError('public_bootstrap')
    if 'scripts' in sys.modules and tuple(sys.modules['scripts'].__path__) != (str(ROOT / 'scripts'),):
        raise RuntimeError('public_bootstrap')
    name = 'scripts.prepare_arv2_r329_native_coverage_source'
    spec = PathFinder.find_spec(name, [str(ROOT / 'scripts')])
    if spec is None or spec.origin != str(path) or time.monotonic() >= ENTRY_DEADLINE:
        raise RuntimeError('public_bootstrap')
    if name in sys.modules and (__name__ == '__main__' or getattr(sys.modules[name], '__file__', None) != str(path)):
        raise RuntimeError('public_bootstrap')
    return leaf_metadata


try:
    BOOTSTRAP_STAGE_METADATA = _bootstrap_stage()
except BaseException:
    if __name__ == '__main__':
        sys.stdout.buffer.write(b'{"failure_code":"public_bootstrap"}\n')
        raise SystemExit(2)
    raise RuntimeError('public_bootstrap') from None

from scripts import prepare_arv2_r329_native_coverage_source as stage

projection, security = stage.projection, stage.security
SOURCE = ROOT / 'scripts/verify_arv2_r329_native_coverage_readback.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_available_history_native_coverage_source/R329-20261028-B'
DOWNLOADS = Path('/Users/sheltonchen/Downloads')
SCHEMA = 'arv2-r329-native-coverage-code-readback-v1'
SECONDS, MAX_DOWNLOAD_BYTES, MAX_PUBLIC_OUTPUT, MAX_MAP_BYTES = 60, 400 * 1024, 32768, 16384
MAX_XATTR_NAMES_BYTES, MAX_XATTR_VALUE_BYTES = 1024, 64 * 1024
ALLOWED_DOWNLOAD_XATTRS = frozenset((b'com.apple.provenance', b'com.apple.quarantine',
    b'com.apple.metadata:kMDItemWhereFroms', b'com.apple.lastuseddate#PS'))
FALSE_FLAGS = {'QC_contact': False, 'Safari_access': False, 'provider_contact': False,
    'credential_access': False, 'private_source_DATA_read': False, 'old_control_read': False,
    'downloaded_code_executed': False, 'download_origin_proven_by_verifier': False,
    'cloud_saved_source_currently_authenticated': False, 'new_launch_attempt_granted': False,
    'price_coverage_admitted': False, 'point_in_time_proven': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False, 'continuous_integrity_proven': False}
FINITE = frozenset(('arguments', 'map', 'host', 'environment', 'git_state', 'source_pin', 'source_bound',
    'source_changed', 'projection', 'deadline', 'path', 'security', 'download_bound', 'download_pin',
    'download_changed', 'claim_spent', 'output_changed', 'output_write', 'output_bound', 'output', 'os_error', 'unknown'))


class Refused(ValueError):
    """Finite predicate only; never filenames, file contents or native values."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        values = BaseException.args.__get__(error)
        return values[0] if len(values) == 1 and type(values[0]) is str and values[0] in FINITE else 'unknown'
    if type(error) is stage.Refused:
        code = stage.finite(error)
        return code if code in FINITE else 'unknown'
    if type(error) is security.Refusal:
        return 'security'
    if type(error) is projection.Refused:
        return 'projection'
    return 'os_error' if isinstance(error, OSError) else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _pairs(rows):
    value = {}
    for key, child in rows:
        require(key not in value, 'map')
        value[key] = child
    return value


def _loads(raw, code):
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused(code)))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused(code) from None


def validate_map(value):
    require(type(value) is dict and set(value) == set(projection.CLOUD_NAMES), 'map')
    paths = []
    for name in projection.CLOUD_NAMES:
        text = value[name]
        require(type(text) is str and text.isascii() and 0 < len(text) <= 512, 'map')
        path = Path(text)
        stem, suffix = name[:-3], '.py'
        pattern = re.escape(stem) + r'(?: [1-9][0-9]{0,2}| \([1-9][0-9]{0,2}\)|-[1-9][0-9]{0,2})?' + re.escape(suffix)
        require(path.is_absolute() and path.parent == DOWNLOADS and str(path) == text
            and re.fullmatch(pattern, path.name) is not None, 'map')
        paths.append(text)
    require(len(set(paths)) == 11 and len(canonical(value)) <= MAX_MAP_BYTES, 'map')
    return {name: value[name] for name in projection.CLOUD_NAMES}


def path_map(args):
    require(type(args.download_map_json) is str and args.download_map_json.isascii()
        and 0 < len(args.download_map_json) <= MAX_MAP_BYTES and _hash(args.download_map_sha256), 'arguments')
    raw = args.download_map_json.encode('ascii')
    require(sha(raw) == args.download_map_sha256, 'map')
    value = validate_map(_loads(raw, 'map'))
    require(canonical(value) == raw, 'map')
    return value


def selected_plan():
    require(_hash(STAGE_SHA256), 'source_pin')
    return {**stage.public_plan(), stage.SOURCE.relative_to(ROOT).as_posix(): STAGE_SHA256}


def native_profile(download_map):
    paths = validate_map(download_map)
    value = '(version 1)(allow default)(deny network*)(deny file-read-data (regex "[.]pyc$"))'
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
    value += f'(deny file-read* (require-all (subpath "{DOWNLOADS}")' \
        + f'(require-not (literal "{DOWNLOADS}"))' \
        + ''.join(f'(require-not (literal "{path}"))' for path in paths.values()) + '))'
    # macOS requires read permission even for O_EVTONLY directory handles.
    # This exact directory literal is allowed for held-FD traversal; its census
    # prohibition is program-level. Every nonlisted leaf remains denied.
    return value


def profile_record(download_map):
    value = validate_map(download_map)
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': stage.BRANCH, 'python': str(stage.PYTHON),
        'source': str(SOURCE), 'control': str(CONTROL), 'project_id': stage.PROJECT_ID,
        'download_map': value, 'download_map_sha256': sha(canonical(value)),
        'selected_public_source_pins': selected_plan(), 'projector_policy_sha256': sha(canonical(projection.profile_record())),
        'expected_projection_pin': dict(stage.EXPECTED_PROJECTION_PIN),
        'expected_profile_pin': dict(stage.EXPECTED_PROFILE_PIN),
        'native_policy_sha256': sha(native_profile(value).encode('ascii')),
        'maximum_seconds': SECONDS, 'maximum_download_bytes': MAX_DOWNLOAD_BYTES,
        'maximum_download_file_bytes': projection.MAX_CLOUD_FILE_BYTES,
        'maximum_public_output_bytes': MAX_PUBLIC_OUTPUT, 'maximum_map_bytes': MAX_MAP_BYTES,
        'download_xattr_names': sorted(name.decode('ascii') for name in ALLOWED_DOWNLOAD_XATTRS),
        'maximum_xattr_names_bytes': MAX_XATTR_NAMES_BYTES, 'maximum_xattr_value_bytes': MAX_XATTR_VALUE_BYTES,
        'download_security': 'owner_regular_singlelink_emptyACL_finite_Safari_transport_xattrs_opaque_bounded_hashes',
        'ancestor_security': 'original_nofollow_metadata_bound_directory_FDs_no_emptyACL_claim_outsideROOT',
        'before_download_read': 'public_source_authentication_expected_projection_regeneration_exclusive_claim_fsync',
        'no_download_directory_census_or_fallback_search': True,
        'directory_handle_census_prohibition_is_program_level_not_native': True,
        'actual_exit_zero_and_external_matching_bounded_report_required': True,
        'partial_evidence_retained_no_cleanup_retry_or_attribute_change': True,
        'source_pin_scope': 'selected_public_code_only_not_whole_interpreter_integrity',
        'native_bytecode_reads_denied': True,
        'deadline_does_not_bound_uninterruptible_IO_or_host_suspension': True, **FALSE_FLAGS}


def binding(args):
    paths = path_map(args)
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head) is not None
        and _hash(args.caller_sha256) and _hash(args.profile_sha256), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256, 'download_map_sha256': sha(canonical(paths)),
        'project_id': stage.PROJECT_ID}


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


def preflight(args, deadline):
    paths = path_map(args)
    binding(args)
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == stage.PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE and hasattr(os, 'O_EVTONLY'), 'host')
    stage._environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], stage.BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
        (['status', '--porcelain'], '')):
        require(stage._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    require(sha(stage._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()], deadline))
        == args.caller_sha256 and sha(canonical(profile_record(paths))) == args.profile_sha256, 'source_pin')
    remaining(deadline)


def _download_names(native, fd):
    buffer = ctypes.create_string_buffer(MAX_XATTR_NAMES_BYTES)
    count = native.flistxattr(fd, buffer, MAX_XATTR_NAMES_BYTES, security.XATTR_SHOWCOMPRESSION)
    require(type(count) is int and 0 <= count <= MAX_XATTR_NAMES_BYTES, 'security')
    if not count:
        return ()
    raw = buffer.raw[:count]
    require(raw.endswith(b'\0'), 'security')
    names = raw[:-1].split(b'\0')
    require(len(names) <= len(ALLOWED_DOWNLOAD_XATTRS) and len(set(names)) == len(names)
        and all(0 < len(name) <= 127 and name in ALLOWED_DOWNLOAD_XATTRS for name in names), 'security')
    return tuple(sorted(names))


def download_security(fd):
    """New public-download transport scope; original source security is unchanged."""
    before = stage.metadata(fd)
    native = security._native()
    security._require_empty_acl(native, fd)
    names = _download_names(native, fd)
    values, budget = {}, MAX_XATTR_VALUE_BYTES
    for name in names:
        buffer = ctypes.create_string_buffer(max(1, budget))
        count = native.fgetxattr(fd, name, buffer, budget, 0, security.XATTR_SHOWCOMPRESSION)
        require(type(count) is int and 0 <= count <= budget, 'security')
        values[name.decode('ascii')] = {'byte_count': count, 'sha256': sha(buffer.raw[:count])}
        budget -= count
    require(_download_names(native, fd) == names, 'security')
    security._require_empty_acl(native, fd)
    require(stage.metadata(fd) == before, 'download_changed')
    return {'acl_empty': True, 'bounded_visible_xattrs': values}


class DownloadDirectory:
    """Known path traversal only; this code never enumerates directory FDs."""
    def __init__(self):
        self.rows, self.fd = [], None
        try:
            fd = os.open('/', os.O_EVTONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.rows.append({'fd': fd, 'parent': fd, 'name': '.', 'metadata': stage.metadata(fd)})
            for part in DOWNLOADS.parts[1:]:
                self.verify()
                parent = self.rows[-1]['fd']
                before = stage.named(parent, part)
                require(stat.S_ISDIR(before[2]), 'path')
                child = os.open(part, os.O_EVTONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.rows.append({'fd': child, 'parent': parent, 'name': part, 'metadata': before})
                require(stage.metadata(child) == before == stage.named(parent, part), 'download_changed')
            self.fd = self.rows[-1]['fd']
            last = self.rows[-1]['metadata']
            require(last[3] == os.getuid() and stat.S_IMODE(last[2]) in (0o700, 0o755), 'path')
            self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        for row in self.rows:
            require(stage.metadata(row['fd']) == row['metadata'] == stage.named(row['parent'], row['name'])
                and stat.S_ISDIR(row['metadata'][2]), 'download_changed')

    def close(self):
        failed = False
        for row in reversed(self.rows):
            try:
                os.close(row['fd'])
            except OSError:
                failed = True
        self.rows = []
        require(not failed, 'download_changed')


def _regular(values):
    return stat.S_ISREG(values[2]) and values[3] == os.getuid() and values[5] == 1 \
        and stat.S_IMODE(values[2]) in (0o600, 0o644) and not values[9] & ~stage.FLAGS


class Downloads:
    def __init__(self, paths, expected, deadline):
        self.directory, self.rows, self.descriptors = None, {}, []
        paths = validate_map(paths)
        require(type(expected) is dict and set(expected) == set(projection.CLOUD_NAMES)
            and all(type(raw) is bytes and 0 < len(raw) <= projection.MAX_CLOUD_FILE_BYTES for raw in expected.values())
            and sum(map(len, expected.values())) <= MAX_DOWNLOAD_BYTES, 'download_bound')
        try:
            self.directory = DownloadDirectory()
            for name in projection.CLOUD_NAMES:
                remaining(deadline)
                basename = Path(paths[name]).name
                before = stage.named(self.directory.fd, basename)
                require(_regular(before) and before[6] == len(expected[name]), 'download_bound')
                fd = os.open(basename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd)
                self.descriptors.append(fd)
                observed = download_security(fd)
                require(stage.metadata(fd) == before == stage.named(self.directory.fd, basename), 'download_changed')
                row = {'fd': fd, 'name': basename, 'metadata': before, 'security': observed}
                self.rows[name] = row
                raw = os.pread(fd, len(expected[name]) + 1, 0)
                require(len(raw) == before[6] and raw == expected[name] and sha(raw) == sha(expected[name]), 'download_pin')
                remaining(deadline)
                self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        self.directory.verify()
        for row in self.rows.values():
            require(stage.metadata(row['fd']) == row['metadata'] == stage.named(self.directory.fd, row['name'])
                and download_security(row['fd']) == row['security'], 'download_changed')

    def receipt(self):
        self.verify()
        return {'file_count': len(self.rows), 'total_byte_count': sum(row['metadata'][6] for row in self.rows.values()),
            'download_endpoint_metadata_sha256': sha(canonical({name: list(row['metadata']) for name, row in self.rows.items()})),
            'download_endpoint_security_sha256': sha(canonical({name: row['security'] for name, row in self.rows.items()}))}

    def close(self):
        failed = False
        for fd in self.descriptors:
            try:
                os.close(fd)
            except OSError:
                failed = True
        self.descriptors = []
        if self.directory is not None:
            self.directory.close()
        require(not failed, 'download_changed')

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.verify()
        finally:
            self.close()


class Store(stage.Store):
    def __init__(self):
        self.guard = stage.DirectoryGuard(CONTROL, create=True, control=CONTROL)
        self.fd, self.files, self.failed = self.guard.fd, {}, False

    def write(self, name, raw, deadline):
        require(name in ('claim.json', 'report.json', 'failure.json') and len(self.files) < 3
            and type(raw) is bytes and 0 < len(raw) <= MAX_PUBLIC_OUTPUT, 'output_bound')
        remaining(deadline)
        return super().write(name, raw, deadline)


def failure(args, error, *, consumed=False):
    return {'binding': binding(args), 'failure_code': finite(error), 'claim_consumed': consumed,
        'allocation_unknown': not consumed, **FALSE_FLAGS}


def produce(args, deadline):
    preflight(args, deadline)
    paths = path_map(args)
    plan = {**selected_plan(), SOURCE.relative_to(ROOT).as_posix(): args.caller_sha256}
    with stage.PublicSources(plan, deadline) as sources:
        require(sources.files[stage.SOURCE.relative_to(ROOT).as_posix()]['metadata'] == BOOTSTRAP_STAGE_METADATA,
            'source_changed')
        by_name = {Path(name).name: raw for name, raw in sources.raw.items()}
        generated = projection.generate(project_id=stage.PROJECT_ID,
            sources={name: by_name[name] for name in projection.SOURCE_PINS},
            generator_source_bytes=by_name[projection.PATCHER_NAME], expected_generator_sha256=stage.GENERATOR_SHA256)
        require(pin(generated.record_bytes) == stage.EXPECTED_PROJECTION_PIN
            and pin(generated.profile_bytes) == stage.EXPECTED_PROFILE_PIN, 'projection')
        expected = dict(generated.source_pairs)
        sources.verify()
        with Store() as store:
            store.write('claim.json', canonical(binding(args)), deadline)
            try:
                with Downloads(paths, expected, deadline) as downloads:
                    receipt = downloads.receipt()
                    preflight(args, deadline)
                    sources.verify()
                    result = {'schema': SCHEMA, 'project_id': stage.PROJECT_ID, 'download_map_sha256': args.download_map_sha256,
                        'source_files': generated.to_record()['source_files'], 'projection_record': generated.to_record(),
                        'projection_pin': pin(generated.record_bytes),
                        'profile_pin': pin(generated.profile_bytes), 'selected_public_sources_sha256': sha(canonical(plan)),
                        'source_endpoint_metadata_sha256': sha(canonical({name: list(row['metadata']) for name, row in sources.files.items()})),
                        'all_original_download_bytes_equal_expected': True, 'all_original_descriptors_postchecked': True,
                        **receipt, **FALSE_FLAGS}
                    validate_result(result, args)
                    report = canonical({'binding': binding(args), 'result': result})
                    report_pin = store.write('report.json', report, deadline)
                    downloads.verify()
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


def validate_result(value, args):
    keys = {'schema', 'project_id', 'download_map_sha256', 'source_files', 'projection_record', 'projection_pin', 'profile_pin',
        'selected_public_sources_sha256', 'source_endpoint_metadata_sha256', 'file_count', 'total_byte_count',
        'download_endpoint_metadata_sha256', 'download_endpoint_security_sha256',
        'all_original_download_bytes_equal_expected', 'all_original_descriptors_postchecked', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and type(value['project_id']) is int and value['project_id'] == stage.PROJECT_ID
        and value['download_map_sha256'] == path_map_sha(args)
        and type(value['projection_record']) is dict
        and pin(canonical(value['projection_record'])) == value['projection_pin'] == stage.EXPECTED_PROJECTION_PIN
        and value['projection_record'].get('source_files') == value['source_files']
        and value['profile_pin'] == stage.EXPECTED_PROFILE_PIN
        and value['all_original_download_bytes_equal_expected'] is value['all_original_descriptors_postchecked'] is True
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    rows = value['source_files']
    require(type(rows) is list and len(rows) == 11
        and all(type(row) is dict and set(row) == {'name', 'byte_count', 'sha256'} for row in rows)
        and tuple(row['name'] for row in rows) == projection.CLOUD_NAMES
        and all(type(row['byte_count']) is int and 0 < row['byte_count'] <= projection.MAX_CLOUD_FILE_BYTES
            and _hash(row['sha256']) for row in rows)
        and type(value['file_count']) is int and value['file_count'] == 11
        and type(value['total_byte_count']) is int and value['total_byte_count'] == sum(row['byte_count'] for row in rows)
        and value['total_byte_count'] <= MAX_DOWNLOAD_BYTES, 'output')
    require({row['name']: row['sha256'] for row in rows if row['name'] != 'main.py'} == projection.CLOUD_DEPENDENCY_PINS,
        'output')
    require(next(row for row in rows if row['name'] == 'main.py') == {'name': 'main.py', 'byte_count': 6892,
        'sha256': '6f59864e930fba4c2ebc3ca16622b50fe859bb3ae1d793e0bc96b44a4794e298'}, 'output')
    for name in ('selected_public_sources_sha256', 'source_endpoint_metadata_sha256',
            'download_endpoint_metadata_sha256', 'download_endpoint_security_sha256'):
        require(_hash(value[name]), 'output')
    return value


def path_map_sha(args):
    return sha(canonical(path_map(args)))


def validate_output(raw, actual_exit, args):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PUBLIC_OUTPUT and raw.endswith(b'\n')
        and raw.count(b'\n') == 1 and type(actual_exit) is int and actual_exit in (0, 2), 'output')
    value = _loads(raw, 'output')
    require(type(value) is dict and canonical(value) + b'\n' == raw, 'output')
    if set(value) == {'binding', 'outcome'}:
        require(value['binding'] == binding(args) and type(value['outcome']) is dict, 'output')
        outcome = value['outcome']
        if set(outcome) == {'result', 'report_pin'}:
            require(actual_exit == 0, 'output')
            validate_result(outcome['result'], args)
            require(outcome['result']['selected_public_sources_sha256'] == sha(canonical({**selected_plan(),
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


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('arguments')


def main(argv=None):
    args = None
    try:
        parser = _Parser(add_help=False)
        for name in ('expected-head', 'caller-sha256', 'profile-sha256', 'download-map-json', 'download-map-sha256'):
            parser.add_argument('--' + name, required=True)
        args = parser.parse_args(argv)
        deadline = min(ENTRY_DEADLINE, time.monotonic() + SECONDS)
        with alarm(deadline):
            value = produce(args, deadline)
            code = 2 if 'failure' in value['outcome'] else 0
            raw = canonical(value) + b'\n'
            validate_output(raw, code, args)
            sys.stdout.buffer.write(raw)
            return code
    except BaseException as error:
        try:
            raw = canonical(failure(args, error)) + b'\n'
            validate_output(raw, 2, args)
        except BaseException:
            raw = b'{"failure_code":"arguments"}\n'
        sys.stdout.buffer.write(raw)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
