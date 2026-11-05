"""Copy caller-attested historical observation bytes, never issue custody authority.

The worker remains write-denied. This separate owner-side copier has a fixed
destination and a ten-second local deadline; its owned wait/EOF and the final
observer acceptance must also fit inside the observer's original 180 seconds.
"""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import sys
import time

ROOT = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
BASE = Path('/Users/sheltonchen/Library/Application Support/CodexShortInterestUSBObservation')
INVOCATION = 'si-usb-offline-once-20261104-v1'
DIRECTORY = BASE / INVOCATION
NAMES = ('producer.stdout.private', 'observation.private.json')
MAX_INPUT, MAX_RAW, MAX_SUMMARY = 196608, 65537, 16384
SECONDS = 10
_USED = False
_CODES = frozenset('arguments spent clock input schema lineage authority directory exists file write bytes stamp close'.split())
_PHASES = frozenset('input ancestry create write audit close postclose final'.split())
_ERRNOS = frozenset((errno.EACCES, errno.EPERM, errno.EIO, errno.ENOSPC, errno.EEXIST,
                    errno.EROFS, errno.ELOOP, errno.EBADF, errno.ETIMEDOUT, errno.EINVAL))


class CopyRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise CopyRefusal(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'schema')
        result[key] = value
    return result


def _json(raw):
    value = json.loads(raw, object_pairs_hook=_pairs,
                       parse_constant=lambda unused: require(False, 'schema'))
    require(canonical(value) == raw, 'schema')
    return value


def _fact(error, phase):
    args = BaseException.args.__get__(error, BaseException)
    code = args[0] if type(error) is CopyRefusal and len(args) == 1 and type(args[0]) is str and args[0] in _CODES else None
    number = OSError.errno.__get__(error, OSError) if isinstance(error, OSError) else None
    return {'phase': phase if phase in _PHASES else 'input', 'code': code,
            'errno': number if type(number) is int and number in _ERRNOS else None}


class _Clock:
    def __init__(self):
        self.start = self.last = time.monotonic_ns()
        require(type(self.start) is int and self.start >= 0, 'clock')

    def check(self):
        now = time.monotonic_ns()
        require(type(now) is int and self.start <= self.last <= now
                and now - self.start <= SECONDS * 10**9, 'clock')
        self.last = now
        return now


def _begin():
    global _USED
    require(not _USED, 'spent')
    _USED = True
    return _Clock()


def _validate(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT, 'input')
    value = _json(raw)
    require(type(value) is dict and set(value) == {'schema', 'runtime_head', 'matching_remote',
            'invocation_id', 'original_stdout_base64', 'owned_observation'}
            and value['schema'] == 'si-usb-observation-private-copy-v1'
            and value['invocation_id'] == INVOCATION, 'schema')
    require(all(type(value[key]) is str and re.fullmatch('[0-9a-f]{40}', value[key])
                for key in ('runtime_head', 'matching_remote')), 'lineage')
    encoded = value['original_stdout_base64']
    require(type(encoded) is str and len(encoded) <= 4 * ((MAX_RAW + 2) // 3), 'input')
    packet = base64.b64decode(encoded, validate=True)
    require(0 < len(packet) <= MAX_RAW and base64.b64encode(packet).decode() == encoded, 'input')
    observed = value['owned_observation']
    require(type(observed) is dict and len(canonical(observed)) <= MAX_SUMMARY
            and observed.get('schema') == 'si-usb-once-owned-observation-v1'
            and observed.get('status') in ('closed_finite_offline_byte_observation', 'incomplete')
            and all(observed.get(key) == value[key] for key in ('runtime_head', 'matching_remote', 'invocation_id'))
            and observed.get('test_seams_used') is False
            and all(observed.get(key) is False for key in ('source_qualified', 'source_admitted', 'ready_for_backtest')),
            'authority')
    require(observed.get('original_stdout_complete') is True
            and observed.get('stdout_EOF') is True and observed.get('stderr_EOF') is True
            and all(type(observed.get(key)) is int and observed[key] == len(packet)
                    for key in ('stdout_bytes_observed', 'stdout_bytes_retained'))
            and observed.get('original_stdout_sha256') == observed.get('retained_stdout_sha256') == sha(packet), 'bytes')
    require(packet.endswith(b'\n') and not packet.endswith(b'\n\n'), 'schema')
    body = _json(packet[:-1])
    require(type(body) is dict and body.get('invocation_id') == INVOCATION
            and body.get('source_qualified') is False
            and observed.get('producer_status') == body.get('status'), 'authority')
    if body.get('schema') == 'si-usb-once-envelope-v1':
        require(body.get('status') in ('closed_finite_offline_byte_inspection', 'incomplete')
                and all(body.get(key) == value[key] for key in ('runtime_head', 'matching_remote')), 'lineage')
        require(type(body.get('authority')) is dict and body['authority'].get('finite_offline_byte_inspection_only') is True
                and all(body['authority'].get(key) is False for key in ('source_qualified', 'source_admitted',
                    'protected_source_custody_verified', 'denominator_admitted', 'actual_input_admitted',
                    'ready_for_backtest', 'QC_or_Safari'))
                and all(type(body['authority'].get(key)) is int and body['authority'][key] == 0 for key in
                    ('provider_HTTP', 'source_credential_reads', 'new_claims', 'new_STARTs', 'new_charged_bytes',
                     'outcome_looks', 'qc_attempts')), 'authority')
    else:
        require(set(body) == {'schema', 'invocation_id', 'status', 'source_qualified', 'first_failure', 'cleanup_failures'}
                and body['schema'] == 'si-usb-once-bootstrap-refusal-v1' and body['status'] == 'incomplete', 'schema')
    for part, permitted in ((body, 'finite_offline_byte_inspection_only'),
                            (body.get('original_profile_proof'), 'external_byte_inspection_only'),
                            (body.get('private_model_aggregate'), 'inspection_only')):
        if part is None or body['schema'] == 'si-usb-once-bootstrap-refusal-v1':
            continue
        require(type(part) is dict and type(part.get('authority')) is dict
                and part['authority'].get(permitted) is True
                and all(item is True if key == permitted else item is False or type(item) is int and item == 0
                        for key, item in part['authority'].items()), 'authority')
    if observed['status'] == 'closed_finite_offline_byte_observation':
        require(body.get('status') == 'closed_finite_offline_byte_inspection'
                and observed.get('actual_exit_code') == 0 and type(observed.get('actual_exit_code')) is int
                and observed.get('actual_signal') is None and observed.get('exit_observed') is True
                and observed.get('close_observed') is True, 'lineage')
    saved = {'schema': 'si-usb-observation-private-copy-v1', 'runtime_head': value['runtime_head'],
             'matching_remote': value['matching_remote'], 'invocation_id': INVOCATION,
             'process_claims': 'caller_attested_historical_copy_not_independently_observed',
             'original_stdout_bytes': len(packet), 'original_stdout_sha256': sha(packet),
             'owned_observation': observed, 'source_authority': False}
    return packet, canonical(saved)


def _stamp(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink',
                 'st_size', 'st_mtime_ns', 'st_ctime_ns')) + (getattr(info, 'st_flags', 0),)


def _dir(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.getuid()) and not info.st_mode & 0o022, 'directory')
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode


class _Anchors:
    def __init__(self, clock):
        self.clock, self.fds, self.nodes, self.files, self.sealed, self.names = clock, [], [], [], {}, set()
        self.fd = None

    def open(self):
        require(ROOT.resolve() == ROOT and Path.cwd().resolve() == ROOT and BASE.is_absolute()
                and DIRECTORY == BASE / INVOCATION and ROOT.lstat().st_uid == os.getuid() == os.geteuid(), 'directory')
        self.clock.check()
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.fds.append(fd); path = Path('/'); self.nodes.append((path, fd, _dir(os.fstat(fd))))
        for part in DIRECTORY.parts[1:]:
            self.clock.check(); path /= part
            if path in (BASE, DIRECTORY):
                try: info = os.stat(part, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    os.mkdir(part, 0o700, dir_fd=fd); os.fsync(fd)
                else: require(path != DIRECTORY, 'exists')
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            self.fds.append(child); info = os.fstat(child)
            if path in (BASE, DIRECTORY):
                require(info.st_uid == os.getuid() and info.st_gid == self.nodes[-1][2][3]
                        and stat.S_IMODE(info.st_mode) == 0o700, 'directory')
            self.nodes.append((path, child, _dir(info))); fd = child
        self.fd = fd; self.audit()

    def audit(self, named=False):
        self.clock.check()
        for path, fd, pin in self.nodes:
            require(path.resolve() == path and _dir(path.lstat()) == pin
                    and (named or _dir(os.fstat(fd)) == pin), 'directory')
        if self.fd is not None:
            require(set(os.listdir(DIRECTORY if named else self.fd)) == self.names, 'directory')
        self.clock.check()

    def file_audit(self, name, fd, pin, raw):
        self.audit(); require(_stamp(os.fstat(fd)) == _stamp(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) == pin, 'stamp')
        os.lseek(fd, 0, os.SEEK_SET)
        require(os.read(fd, len(raw) + 1) == raw, 'bytes')
        require(_stamp(os.fstat(fd)) == _stamp(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) == pin, 'stamp')
        self.clock.check()

    def write(self, name, raw):
        self.audit(); require(name in NAMES and name not in self.names and type(raw) is bytes, 'file')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.fd)
        self.files.append(fd); self.names.add(name); os.fchmod(fd, 0o600); initial = _stamp(os.fstat(fd)); offset = 0
        require(stat.S_ISREG(initial[4]) and initial[2:4] == (os.getuid(), self.nodes[-1][2][3])
                and stat.S_IMODE(initial[4]) == 0o600 and initial[5] == 1, 'file')
        while offset < len(raw):
            self.audit(); current = _stamp(os.fstat(fd)); named = _stamp(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
            require(current == named and current[:6] == initial[:6] and current[9] == initial[9] and current[6] == offset, 'stamp')
            count = os.write(fd, raw[offset:]); require(type(count) is int and 0 < count <= len(raw) - offset, 'write'); offset += count
        os.fsync(fd); os.fsync(self.fd); pin = _stamp(os.fstat(fd))
        require(pin[:6] == initial[:6] and pin[9] == initial[9] and pin[6] == len(raw), 'stamp')
        self.file_audit(name, fd, pin, raw); self.sealed[name] = (pin, raw)


def _publish(raw, clock):
    scope = _Anchors(clock); first = None; later = []; phase = 'input'
    def fail(error, where):
        nonlocal first
        fact = _fact(error, where)
        if first is None: first = fact
        elif len(later) < 16: later.append(fact)
    try:
        packet, summary = _validate(raw); clock.check(); phase = 'ancestry'; scope.open()
        for name, content in zip(NAMES, (packet, summary)):
            phase = 'write'; scope.write(name, content)
        phase = 'audit'
        for name, (pin, content) in scope.sealed.items():
            scope.file_audit(name, scope.files[NAMES.index(name)], pin, content)
    except BaseException as error: fail(error, phase)
    finally:
        for fd in reversed(scope.files):
            try: os.close(fd)
            except BaseException as error: fail(error, 'close')
        for name, (pin, content) in scope.sealed.items():
            fd = None
            try:
                clock.check()
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=scope.fd)
                scope.file_audit(name, fd, pin, content)
            except BaseException as error: fail(error, 'postclose')
            finally:
                if fd is not None:
                    try: os.close(fd)
                    except BaseException as error: fail(error, 'close')
            try: require(_stamp(os.stat(name, dir_fd=scope.fd, follow_symlinks=False)) == pin, 'stamp')
            except BaseException as error: fail(error, 'postclose')
        for fd in reversed(scope.fds):
            try: os.close(fd)
            except BaseException as error: fail(error, 'close')
    try:
        scope.audit(named=True)
        for name, (pin, unused) in scope.sealed.items(): require(_stamp((DIRECTORY / name).lstat()) == pin, 'stamp')
        clock.check()
    except BaseException as error: fail(error, 'postclose')
    result = {'schema': 'si-usb-private-copy-receipt-v1', 'status': 'private_observation_copy_closed' if first is None else 'incomplete',
              'invocation_id': INVOCATION, 'process_claims': 'caller_attested_historical_copy_not_independently_observed',
              'source_authority': False, 'source_admitted': False, 'ready_for_backtest': False,
              'maximum_local_seconds': SECONDS, 'first_failure': first, 'cleanup_failures': later,
              'files': {name: {'bytes': len(content), 'sha256': sha(content), 'original_file10_sha256': sha(canonical(list(pin)))}
                        for name, (pin, content) in scope.sealed.items()},
              'directory5_sha256': sha(canonical(list(scope.nodes[-1][2]))) if scope.fd is not None else None,
              'ancestry5_sha256': sha(canonical([list(row[2]) for row in scope.nodes]))}
    try:
        require(set(scope.sealed) == set(NAMES), 'file'); canonical(result); clock.check()
    except BaseException as error:
        fail(error, 'final'); result.update(status='incomplete', first_failure=first, cleanup_failures=later)
    return result


def persist(raw):
    """One historical copy; a returned receipt cannot prove a process ran."""
    return _publish(raw, _begin())


def main():
    clock = None
    try:
        clock = _begin(); require(len(sys.argv) == 1, 'arguments'); parts = []; size = 0
        while True:
            clock.check(); remaining = max(0, (SECONDS * 10**9 - (time.monotonic_ns() - clock.start)) / 10**9)
            require(select.select([sys.stdin.fileno()], [], [], remaining)[0], 'clock')
            part = os.read(sys.stdin.fileno(), min(65536, MAX_INPUT + 1 - size))
            if not part: break
            parts.append(part); size += len(part); require(size <= MAX_INPUT, 'input')
        result = _publish(b''.join(parts), clock)
    except BaseException as error:
        result = {'schema': 'si-usb-private-copy-receipt-v1', 'status': 'incomplete', 'invocation_id': INVOCATION,
                  'process_claims': 'caller_attested_historical_copy_not_independently_observed',
                  'source_authority': False, 'first_failure': _fact(error, 'input'), 'cleanup_failures': []}
    terminal = canonical(result)
    try:
        if clock is not None:
            clock.check()
    except BaseException as error:
        result['status'] = 'incomplete'; fact = _fact(error, 'final')
        if result['first_failure'] is None: result['first_failure'] = fact
        else: result['cleanup_failures'] = [*result['cleanup_failures'], fact][:16]
        terminal = canonical(result)
    print(terminal.decode(), flush=True)
    return 0 if result['status'] == 'private_observation_copy_closed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
