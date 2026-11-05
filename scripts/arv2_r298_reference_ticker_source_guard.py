"""One fixed current-use TICKERS guard, not historical relocation acceptance.

No operation occurs on import. The caller must claim its separate one-use
protocol before entering. Only the three fixed leaves are opened; the old v4
assessment/snapshot and its historical device/ctime projection are not called.
Fresh ten-field endpoint equality is not continuous or historical integrity.
"""
from __future__ import annotations

import ctypes
import hashlib
import math
import os
from pathlib import Path
import stat
import time

from scripts import arv2_relocation_security as security
from scripts import arv2_relocation_security_v4 as historical


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
CAPTURE = ROOT / 'artifacts/analyst_revisions_v2/sharadar_capture/arv2-sharadar-source-20260914T003329843989Z'
SCHEMA = 'arv2-r298-reference-ticker-fresh-source-guard-v1'
MANIFEST_SHA256 = '94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b'
ARCHIVE_SHA256 = 'a7b129f159631ee50f1eefd2be8d4215c1c7818880570c0ad0a79c76c25e51bf'
ARCHIVE_BYTES = 4937076
MANIFEST_MAX_BYTES = 128 * 1024
LEAVES = ('manifest.json', 'manifest.sha256', '01-tickers-years-full.zip')
VINTAGE_XATTR_PINS = tuple(historical.XATTR_PINS)
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FINITE = frozenset({'scope', 'deadline', 'state', 'path_open', 'metadata',
    'named_changed', 'metadata_changed', 'directory_policy', 'file_policy',
    'security_observation', 'xattr_names', 'xattr_values', 'security_changed',
    'leaf', 'read_spent', 'read', 'byte_pin', 'close'})


class Refused(Exception):
    pass


def finite(error):
    return (error.args[0] if type(error) is Refused and len(error.args) == 1
            and type(error.args[0]) is str and error.args[0] in FINITE else 'state')


def require(value, code):
    if value is not True:
        raise Refused(code)


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'capture': str(CAPTURE),
        'leaves': list(LEAVES), 'manifest_sha256': MANIFEST_SHA256,
        'archive_sha256': ARCHIVE_SHA256, 'archive_byte_count': ARCHIVE_BYTES,
        'manifest_max_bytes': MANIFEST_MAX_BYTES, 'marker_byte_count': 65,
        'metadata_fields': list(FIELDS),
        'vintage_xattrs': [{'name': name.decode('ascii'), 'size': size, 'sha256': pin}
                           for name, size, pin in VINTAGE_XATTR_PINS],
        'ordinary_xattrs': ['com.apple.provenance'],
        'native_empty_acl_required': True, 'held_named_full_chain': True,
        'fresh_current_use_only': True, 'historical_metadata_refreshed': False,
        'old_v4_replayed': False, 'continuous_integrity_proven': False,
        'historical_continuity_proven': False, 'hidden_xattrs_authenticated': False,
        'source_admission_granted': False, 'operational_authority_granted': False,
        'point_in_time_proven': False, 'formal_identity_admitted': False,
        'formal_forward_ready': False, 'paper_or_live_ready': False}


def _tuple(info):
    try:
        values = tuple(getattr(info, field) for field in FIELDS)
    except AttributeError:
        raise Refused('metadata') from None
    require(all(type(value) is int and value >= 0 for value in values)
            and (stat.S_ISDIR(values[2]) or stat.S_ISREG(values[2])), 'metadata')
    return values


def _metadata(fd):
    try:
        return security._metadata(fd)
    except security.Refusal:
        raise Refused('metadata') from None


def _names(native, fd):
    # The old v4 names-only helper does not invoke its spent policy snapshot.
    try:
        return historical._names(native, fd)
    except security.Refusal:
        raise Refused('security_observation') from None


def _vintage_security(fd):
    before = _metadata(fd)
    try:
        native = security._native()
        security._require_empty_acl(native, fd)
        names = _names(native, fd)
        require(names == tuple(row[0] for row in VINTAGE_XATTR_PINS), 'xattr_names')
        values, remaining = [], security.MAX_VALUE_BYTES
        for name, expected_size, expected_pin in VINTAGE_XATTR_PINS:
            buffer = ctypes.create_string_buffer(max(1, remaining))
            count = native.fgetxattr(fd, name, buffer, remaining, 0,
                                    security.XATTR_SHOWCOMPRESSION)
            require(type(count) is int and 0 <= count <= remaining, 'xattr_values')
            pin = hashlib.sha256(buffer.raw[:count]).hexdigest()
            require(count == expected_size and pin == expected_pin, 'xattr_values')
            values.append((name, count, pin))
            remaining -= count
        require(_names(native, fd) == names, 'xattr_names')
        security._require_empty_acl(native, fd)
    except security.Refusal:
        raise Refused('security_observation') from None
    require(_metadata(fd) == before, 'metadata_changed')
    return tuple(values)


class SourceGuard:
    """Hold the complete no-follow chain and all three leaves until return.

    There is no caller-supplied root, leaf inventory or security policy. Tests
    substitute these fixed module constants explicitly with in-root fixtures.
    Absolute ancestors above ROOT receive identity checks, not the private
    owner/mode/ACL policy that historically applied only to ROOT and below.
    """
    def __init__(self, *, deadline):
        require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
        self._deadline = deadline
        self._objects, self._by_path, self._reads = [], {}, set()
        self._active = False
        self._spent = False

    @property
    def deadline(self):
        return self._deadline

    def _budget(self, deadline=None):
        limit = self.deadline if deadline is None else deadline
        require(type(limit) in (int, float) and math.isfinite(limit)
                and limit <= self.deadline and time.monotonic() < limit, 'deadline')

    def _close(self):
        failed = False
        for row in reversed(self._objects):
            try:
                os.close(row['fd'])
            except OSError:
                failed = True
        self._objects.clear(); self._by_path.clear(); self._active = False
        return failed

    def _named(self, row):
        try:
            return _tuple(os.stat(row['name'], dir_fd=row['parent'], follow_symlinks=False))
        except OSError:
            raise Refused('path_open') from None

    def _policy(self, path, metadata, leaf):
        self._budget()
        if path == ROOT or ROOT in path.parents:
            require(metadata[3] == os.getuid(), 'file_policy' if leaf else 'directory_policy')
            require(not metadata[9] & ~(stat.UF_TRACKED | stat.UF_HIDDEN),
                    'file_policy' if leaf else 'directory_policy')
            if leaf:
                require(stat.S_ISREG(metadata[2]) and stat.S_IMODE(metadata[2]) == 0o600
                        and metadata[5] == 1, 'file_policy')
                bound = (MANIFEST_MAX_BYTES if path.name == LEAVES[0] else
                         65 if path.name == LEAVES[1] else ARCHIVE_BYTES)
                require(0 < metadata[6] <= bound
                        and (path.name == LEAVES[0] or metadata[6] == bound), 'file_policy')
            else:
                require(stat.S_ISDIR(metadata[2])
                        and stat.S_IMODE(metadata[2]) == (0o755 if path == ROOT else 0o700),
                        'directory_policy')
        else:
            require(not leaf and stat.S_ISDIR(metadata[2]), 'directory_policy')

    def _security(self, row):
        if row['path'] != ROOT and ROOT not in row['path'].parents:
            return None
        if row['path'] == CAPTURE:
            return _vintage_security(row['fd'])
        try:
            return security.snapshot(row['fd'])
        except security.Refusal:
            raise Refused('security_observation') from None

    def _hold(self, path, parent, name, *, leaf=False):
        self._budget()
        try:
            named = _tuple(os.stat(name, dir_fd=parent, follow_symlinks=False))
            self._policy(path, named, leaf)
            flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
            flags |= os.O_NONBLOCK if leaf else os.O_DIRECTORY
            fd = os.open(name, flags, dir_fd=parent)
        except OSError:
            raise Refused('path_open') from None
        row = {'path': path, 'fd': fd, 'parent': parent, 'name': name,
               'metadata': named, 'leaf': leaf}
        self._objects.append(row); self._by_path[path] = row
        require(_metadata(fd) == named, 'named_changed')
        row['security'] = self._security(row)
        require(_metadata(fd) == named and self._named(row) == named, 'named_changed')

    def __enter__(self):
        require(not self._active and not self._spent, 'state')
        self._spent = True
        require(type(ROOT) is type(Path()) and type(CAPTURE) is type(Path())
                and ROOT.is_absolute() and ROOT in CAPTURE.parents
                and CAPTURE.relative_to(ROOT).parts == ('artifacts', 'analyst_revisions_v2',
                    'sharadar_capture', 'arv2-sharadar-source-20260914T003329843989Z')
                and Path.cwd() == ROOT, 'scope')
        self._budget()
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                         | getattr(os, 'O_CLOEXEC', 0))
            first = {'path': Path('/'), 'fd': fd, 'parent': fd, 'name': '.',
                     'metadata': _metadata(fd), 'leaf': False, 'security': None}
            self._objects.append(first); self._by_path[Path('/')] = first
            current = Path('/')
            for component in CAPTURE.parts[1:]:
                current = current / component
                self._hold(current, self._objects[-1]['fd'], component)
            parent = self._by_path[CAPTURE]['fd']
            for leaf in LEAVES:
                self._hold(CAPTURE / leaf, parent, leaf, leaf=True)
            self._active = True
            self.verify()
            return self
        except BaseException:
            self._close()
            raise

    def verify(self):
        require(self._active, 'state')
        for row in self._objects:
            self._budget()
            require(_metadata(row['fd']) == row['metadata'], 'metadata_changed')
            require(self._named(row) == row['metadata'], 'named_changed')
            self._policy(row['path'], row['metadata'], row['leaf'])
            require(self._security(row) == row['security'], 'security_changed')
            require(_metadata(row['fd']) == row['metadata']
                    and self._named(row) == row['metadata'], 'metadata_changed')
        self._budget()

    def read(self, name, deadline):
        require(self._active and type(name) is str and name in LEAVES, 'leaf')
        require(name not in self._reads, 'read_spent')
        self._reads.add(name)
        self._budget(deadline)
        self.verify()
        row = self._by_path[CAPTURE / name]
        try:
            os.lseek(row['fd'], 0, os.SEEK_SET)
            chunks, count = [], 0
            while True:
                self._budget(deadline)
                chunk = os.read(row['fd'], min(1024 * 1024, row['metadata'][6] + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                require(count <= row['metadata'][6], 'byte_pin')
                chunks.append(chunk)
            payload = b''.join(chunks)
        except OSError:
            raise Refused('read') from None
        require(count == row['metadata'][6], 'byte_pin')
        if name == LEAVES[0]:
            require(hashlib.sha256(payload).hexdigest() == MANIFEST_SHA256, 'byte_pin')
        elif name == LEAVES[1]:
            require(payload == (MANIFEST_SHA256 + '\n').encode('ascii'), 'byte_pin')
        else:
            require(count == ARCHIVE_BYTES and hashlib.sha256(payload).hexdigest() == ARCHIVE_SHA256,
                    'byte_pin')
        self.verify()
        self._budget(deadline)
        return payload

    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.verify()
        finally:
            failed = self._close()
        if kind is None and failed:
            raise Refused('close')
        return False
