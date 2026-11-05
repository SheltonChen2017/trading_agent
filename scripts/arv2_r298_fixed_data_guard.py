"""Technical fixed-plan data guard; no protocol or source admission authority.

Import is inert. A separately frozen caller must supply its exact public file
plan, claim before entering, hold this guard through its private computation,
and wait for normal return before publication. This helper grants no attempt,
provider, license, historical continuity, price or operational authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time

from scripts import arv2_relocation_security as security

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SCHEMA = 'arv2-r298-fixed-plan-current-data-guard-v1'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
    'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_SECONDS = 8, 32 * 1024 * 1024, 64 * 1024 * 1024, 900
FINITE = frozenset(('scope', 'plan', 'deadline', 'state', 'shape', 'path_open', 'metadata',
    'named_changed', 'security', 'security_changed', 'read_spent', 'byte_pin', 'close', 'receipt'))


class Refused(ValueError):
    """Finite technical predicate, never source bytes or exception strings."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'state'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def checked_plan(plan):
    require(type(plan) is dict and 0 < len(plan) <= MAX_FILES
        and all(type(role) is str and re.fullmatch('[a-z][a-z0-9_]{0,40}', role) for role in plan), 'plan')
    result, paths = {}, set()
    for role, row in plan.items():
        require(type(row) is dict and set(row) == {'relative_path', 'byte_count', 'sha256'}
            and type(row['relative_path']) is str and len(row['relative_path']) <= 1024
            and type(row['byte_count']) is int and 0 < row['byte_count'] <= MAX_FILE_BYTES
            and _hash(row['sha256']), 'plan')
        path = PurePosixPath(row['relative_path'])
        require(not path.is_absolute() and path.as_posix() == row['relative_path']
            and path.parts[:2] == ('artifacts', 'analyst_revisions_v2') and len(path.parts) >= 4
            and all(part not in ('', '.', '..') and '\\' not in part and '\x00' not in part for part in path.parts)
            and row['relative_path'] not in paths, 'plan')
        paths.add(row['relative_path']); result[role] = dict(row)
    require(sum(row['byte_count'] for row in result.values()) <= MAX_TOTAL_BYTES, 'plan')
    return result


def profile_record(plan):
    return {'schema': SCHEMA, 'root': str(ROOT), 'file_plan': checked_plan(plan),
        'metadata_fields': list(FIELDS), 'maximum_files': MAX_FILES,
        'maximum_file_bytes': MAX_FILE_BYTES, 'maximum_total_bytes': MAX_TOTAL_BYTES,
        'maximum_seconds': MAX_SECONDS, 'all_no_follow_components_and_original_descriptors_held': True,
        'root_mode': '0755', 'root_below_directory_mode': '0700', 'leaf_mode': '0600_single_link',
        'root_below_empty_native_ACL_and_ordinary_xattrs': True,
        'normal_return_required_before_use': True, 'one_read_of_each_planned_leaf': True,
        'initial_plan_digest_checked_before_each_budgeted_stage': True,
        'endpoint_equality_not_continuous_or_historical_integrity': True,
        'generic_technical_guard_not_protocol_or_attempt_authority': True,
        'operational_authority_granted': False, 'source_admission_granted': False,
        'price_admission_granted': False, 'historical_continuity_proven': False,
        'continuous_integrity_proven': False, 'paper_or_live_ready': False}


def _metadata(fd):
    try:
        info = os.fstat(fd)
    except OSError:
        raise Refused('metadata') from None
    values = tuple(getattr(info, field, None) for field in FIELDS)
    require(all(type(value) is int and value >= 0 for value in values), 'metadata')
    return values


def _named(parent, name):
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        values = tuple(getattr(info, field, None) for field in FIELDS)
    except OSError:
        raise Refused('path_open') from None
    require(all(type(value) is int and value >= 0 for value in values), 'metadata')
    return values


class FixedDataGuard:
    """Caller-supplied technical plan, never a callable operational permit."""
    def __init__(self, plan, *, deadline):
        self.plan, self.deadline = checked_plan(plan), deadline
        self.initial_plan_sha256 = sha(canonical(self.plan))
        self.objects, self.by_path, self.by_role, self.reads = [], {}, {}, set()
        self.active, self.spent = False, False
        self._budget()

    def _budget(self):
        try:
            unchanged_plan = sha(canonical(self.plan)) == self.initial_plan_sha256
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise Refused('plan') from None
        require(unchanged_plan, 'plan')
        require(type(self.deadline) in (int, float) and math.isfinite(self.deadline)
            and 0 < self.deadline - time.monotonic() <= MAX_SECONDS, 'deadline')

    def _policy(self, path, info, *, pin=None):
        require(stat.S_ISREG(info[2]) if pin is not None else stat.S_ISDIR(info[2]), 'shape')
        if path == ROOT or ROOT in path.parents:
            require(info[3] == os.getuid() and not info[9] & ~(stat.UF_TRACKED | stat.UF_HIDDEN), 'shape')
            if pin is None:
                require(stat.S_IMODE(info[2]) == (0o755 if path == ROOT else 0o700), 'shape')
            else:
                require(stat.S_IMODE(info[2]) == 0o600 and info[5] == 1 and info[6] == pin['byte_count'], 'shape')

    def _security(self, row):
        if row['path'] != ROOT and ROOT not in row['path'].parents:
            return None
        try:
            return security.snapshot(row['fd'])
        except security.Refusal:
            raise Refused('security') from None

    def _hold(self, path, parent, name, *, pin=None):
        self._budget()
        named = _named(parent, name)
        self._policy(path, named, pin=pin)
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
        flags |= os.O_DIRECTORY if pin is None else os.O_NONBLOCK
        try:
            fd = os.open(name, flags, dir_fd=parent)
        except OSError:
            raise Refused('path_open') from None
        row = {'path': path, 'fd': fd, 'parent': parent, 'name': name, 'pin': pin, 'metadata': named}
        self.objects.append(row); self.by_path[path] = row
        require(_metadata(fd) == named, 'named_changed')
        row['security'] = self._security(row)
        require(_metadata(fd) == named == _named(parent, name), 'named_changed')
        return row

    def __enter__(self):
        require(not self.active and not self.spent, 'state')
        self.spent = True
        require(type(ROOT) is type(Path()) and ROOT.is_absolute() and Path.cwd() == ROOT, 'scope')
        try:
            self._budget()
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0))
            first = {'path': Path('/'), 'fd': fd, 'parent': fd, 'name': '.', 'pin': None,
                'metadata': _metadata(fd), 'security': None}
            self.objects.append(first); self.by_path[Path('/')] = first
            for role, pin in self.plan.items():
                path, parent = Path('/'), first
                full = ROOT / pin['relative_path']
                for part in full.parent.parts[1:]:
                    path = path / part
                    parent = self.by_path[path] if path in self.by_path else self._hold(path, parent['fd'], part)
                self.by_role[role] = self._hold(full, parent['fd'], full.name, pin=pin)
            self.active = True
            self.verify()
            return self
        except BaseException:
            self.close()
            raise

    def verify(self):
        require(self.active, 'state')
        for row in self.objects:
            self._budget()
            require(_metadata(row['fd']) == row['metadata']
                == _named(row['parent'], row['name']), 'named_changed')
            self._policy(row['path'], row['metadata'], pin=row['pin'])
            require(self._security(row) == row['security'], 'security_changed')
            require(_metadata(row['fd']) == row['metadata']
                == _named(row['parent'], row['name']), 'metadata')

    def read_all_once(self):
        require(self.active and not self.reads, 'read_spent')
        self.verify()
        values = {}
        for role, pin in self.plan.items():
            self.reads.add(role)
            fd = self.by_role[role]['fd']; os.lseek(fd, 0, os.SEEK_SET)
            chunks, count = [], 0
            while count <= pin['byte_count']:
                self._budget()
                chunk = os.read(fd, min(65536, pin['byte_count'] + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk); count += len(chunk)
            raw = b''.join(chunks)
            require(len(raw) == pin['byte_count'] and sha(raw) == pin['sha256'], 'byte_pin')
            values[role] = raw
        self.verify()
        return values

    def receipt(self):
        self.verify()
        require(self.reads == set(self.plan), 'state')
        result = {'schema': SCHEMA + '-receipt', 'profile_sha256': sha(canonical(profile_record(self.plan))),
            'files': {role: {**pin,
                'current_metadata_sha256': sha(canonical(list(self.by_role[role]['metadata']))),
                'current_security_sha256': sha(canonical(self.by_role[role]['security']))}
                for role, pin in self.plan.items()}, 'fresh_current_security_authenticated': True,
            'fixed_bytes_authenticated': True, 'requires_normal_return_before_use': True,
            'historical_continuity_proven': False, 'continuous_integrity_proven': False}
        return validate_receipt(result, self.plan)

    def close(self):
        failed = False
        for row in reversed(self.objects):
            try:
                os.close(row['fd'])
            except OSError:
                failed = True
        self.objects.clear(); self.by_path.clear(); self.by_role.clear(); self.active = False
        if failed:
            raise Refused('close')

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.verify()
        finally:
            self.close()


def validate_receipt(value, plan):
    checked = checked_plan(plan)
    require(type(value) is dict and set(value) == {'schema', 'profile_sha256', 'files',
        'fresh_current_security_authenticated', 'fixed_bytes_authenticated', 'requires_normal_return_before_use',
        'historical_continuity_proven', 'continuous_integrity_proven'}
        and value['schema'] == SCHEMA + '-receipt'
        and value['profile_sha256'] == sha(canonical(profile_record(checked)))
        and value['fresh_current_security_authenticated'] is True and value['fixed_bytes_authenticated'] is True
        and value['requires_normal_return_before_use'] is True
        and value['historical_continuity_proven'] is False and value['continuous_integrity_proven'] is False
        and type(value['files']) is dict and set(value['files']) == set(checked), 'receipt')
    for role, pin in checked.items():
        row = value['files'][role]
        require(type(row) is dict and set(row) == {*pin, 'current_metadata_sha256', 'current_security_sha256'}
            and all(type(row[key]) is type(expected) and row[key] == expected for key, expected in pin.items())
            and _hash(row['current_metadata_sha256']) and _hash(row['current_security_sha256']), 'receipt')
    return json.loads(canonical(value))
