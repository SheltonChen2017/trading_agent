"""Fixed AP DATA streaming guard for a separately frozen offline consumer.

This adds an explicit two-pass read contract without changing the frozen
32-MiB FixedDataGuard. It grants no operation, source, price or upload authority.
All four whole-file hashes precede parsing; bounded corpus ranges are then
consumed exactly once in contiguous order through the original held FD.
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
from scripts import arv2_r298_ap_source_binding as anchor

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SCHEMA = 'arv2-r298-fixed-AP-price-corpus-streaming-guard-v1'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
    'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
ROLES = ('plan', 'dispatch', 'captures', 'corpus')
CAPS = {'plan': 16 * 1024 * 1024, 'dispatch': 2 * 1024 * 1024,
    'captures': 2 * 1024 * 1024, 'corpus': 2 * 1024 * 1024 * 1024}
MAX_SECONDS, MAX_RANGES, MAX_RANGE, CHUNK = 1800, 1256, 4 * 1024 * 1024, 65536
FINITE = frozenset(('plan', 'scope', 'deadline', 'state', 'path', 'metadata', 'shape', 'security',
    'changed', 'byte_pin', 'read_schedule', 'range', 'close', 'receipt'))


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'state'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def checked_plan(plan):
    require(type(plan) is dict and set(plan) == set(ROLES) and plan == anchor.data_plan(), 'plan')
    for role in ROLES:
        row = plan[role]
        require(type(row) is dict and set(row) == {'relative_path', 'byte_count', 'sha256'}
            and type(row['byte_count']) is int and 0 < row['byte_count'] <= CAPS[role]
            and _hash(row['sha256']) and type(row['relative_path']) is str, 'plan')
        path = PurePosixPath(row['relative_path'])
        require(not path.is_absolute() and path.as_posix() == row['relative_path']
            and path.parts[:2] == ('artifacts', 'analyst_revisions_v2')
            and all(part not in ('', '.', '..') and '\\' not in part and '\x00' not in part for part in path.parts), 'plan')
    require(len({row['relative_path'] for row in plan.values()}) == len(ROLES), 'plan')
    return json.loads(canonical(plan))


def profile_record(plan):
    return {'schema': SCHEMA, 'root': str(ROOT), 'file_plan': checked_plan(plan),
        'role_caps': CAPS, 'seconds': MAX_SECONDS, 'maximum_ranges': MAX_RANGES,
        'maximum_range_bytes': MAX_RANGE, 'chunk_bytes': CHUNK, 'metadata_fields': list(FIELDS),
        'read_schedule': 'whole_hash_each_role_then_one_small_read_each_metadata_role_then_contiguous_corpus_ranges',
        'all_four_whole_hashes_before_semantic_bytes': True,
        'original_no_follow_descriptors_held_through_normal_return': True,
        'native_ACL_xattr_and_ten_field_endpoints': True,
        'normal_return_requires_all_1256_ranges_and_exact_corpus_extent': True,
        'continuous_or_historical_integrity_proven': False, 'operation_granted': False,
        'source_admission_granted': False, 'price_admission_granted': False,
        'QC_transfer_granted': False, 'paper_or_live_ready': False}


def _scope():
    require(type(ROOT) is type(Path()) and ROOT.is_absolute() and ROOT.resolve() == ROOT
        and Path.cwd() == ROOT, 'scope')


def validate_receipt(value, plan):
    checked = checked_plan(plan)
    require(type(value) is dict and set(value) == {'schema', 'profile_sha256', 'file_pins',
        'whole_hashes_checked', 'range_count', 'corpus_extent', 'source_endpoint_sha256',
        'requires_normal_return_before_use', 'continuous_or_historical_integrity_proven',
        'source_or_price_admission_granted'} and value['schema'] == SCHEMA + '-receipt'
        and value['profile_sha256'] == sha(canonical(profile_record(checked))) and value['file_pins'] == checked
        and type(value['whole_hashes_checked']) is int and value['whole_hashes_checked'] == len(ROLES)
        and type(value['range_count']) is int and value['range_count'] == MAX_RANGES
        and type(value['corpus_extent']) is int and value['corpus_extent'] == checked['corpus']['byte_count']
        and _hash(value['source_endpoint_sha256']) and value['requires_normal_return_before_use'] is True
        and value['continuous_or_historical_integrity_proven'] is False
        and value['source_or_price_admission_granted'] is False, 'receipt')
    return json.loads(canonical(value))


def _metadata(fd):
    try:
        info=os.fstat(fd)
        values = tuple(getattr(info, field, None) for field in FIELDS)
    except OSError: raise Refused('metadata') from None
    require(all(type(value) is int and value >= 0 for value in values), 'metadata'); return values


def _named(parent, name):
    try: info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except OSError: raise Refused('path') from None
    values = tuple(getattr(info, field, None) for field in FIELDS)
    require(all(type(value) is int and value >= 0 for value in values), 'metadata'); return values


class PriceCorpusGuard:
    def __init__(self, plan, *, deadline):
        self.plan, self.deadline = checked_plan(plan), deadline
        self.plan_sha256 = sha(canonical(self.plan))
        self.objects, self.paths, self.roles = [], {}, {}
        self.active = self.spent = self.authenticated = False
        self.small_reads, self.range_count, self.range_extent = set(), 0, 0
        self._budget()

    def _budget(self):
        require(sha(canonical(self.plan)) == self.plan_sha256, 'plan')
        require(type(self.deadline) in (int, float) and math.isfinite(self.deadline)
            and 0 < self.deadline - time.monotonic() <= MAX_SECONDS, 'deadline')

    def _policy(self, path, info, pin=None):
        require(stat.S_ISREG(info[2]) if pin else stat.S_ISDIR(info[2]), 'shape')
        if path == ROOT or ROOT in path.parents:
            require(info[3] == os.getuid() and not info[9] & ~(stat.UF_TRACKED | stat.UF_HIDDEN), 'shape')
            require(stat.S_IMODE(info[2]) == ((0o755 if path == ROOT else 0o700) if pin is None else 0o600), 'shape')
            if pin is not None: require(info[5] == 1 and info[6] == pin['byte_count'], 'shape')

    def _security(self, row):
        if row['path'] != ROOT and ROOT not in row['path'].parents: return None
        try: return security.snapshot(row['fd'])
        except security.Refusal: raise Refused('security') from None

    def _hold(self, path, parent, name, pin=None):
        self._budget(); before = _named(parent, name); self._policy(path, before, pin)
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
        flags |= os.O_DIRECTORY if pin is None else os.O_NONBLOCK
        try: fd = os.open(name, flags, dir_fd=parent)
        except OSError: raise Refused('path') from None
        row = {'path': path, 'parent': parent, 'name': name, 'fd': fd, 'pin': pin, 'metadata': before}
        self.objects.append(row); self.paths[path] = row
        require(_metadata(fd) == before, 'changed'); row['security'] = self._security(row)
        require(_metadata(fd) == before == _named(parent, name), 'changed'); return row

    def __enter__(self):
        require(not self.active and not self.spent, 'state'); self.spent = True; _scope()
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            first = {'path': Path('/'), 'parent': fd, 'name': '.', 'fd': fd, 'pin': None,
                'metadata': _metadata(fd), 'security': None}
            self.objects.append(first); self.paths[Path('/')] = first
            for role in ROLES:
                pin = self.plan[role]; full = ROOT / pin['relative_path']; path, parent = Path('/'), first
                for part in full.parent.parts[1:]:
                    path = path / part
                    parent = self.paths[path] if path in self.paths else self._hold(path, parent['fd'], part)
                self.roles[role] = self._hold(full, parent['fd'], full.name, pin)
            self.active = True; self.verify(); return self
        except BaseException: self.close(); raise

    def verify(self):
        require(self.active, 'state')
        for row in self.objects:
            self._budget()
            require(_metadata(row['fd']) == row['metadata'] == _named(row['parent'], row['name']), 'changed')
            self._policy(row['path'], row['metadata'], row['pin'])
            require(self._security(row) == row['security'], 'security')
            require(_metadata(row['fd']) == row['metadata'] == _named(row['parent'], row['name']), 'changed')

    def _chunks(self, role, offset, length):
        row = self.roles[role]; consumed = 0
        while consumed < length:
            self._budget()
            require(_metadata(row['fd']) == row['metadata'] == _named(row['parent'], row['name']), 'changed')
            raw = os.pread(row['fd'], min(CHUNK, length - consumed), offset + consumed)
            require(raw and len(raw) <= length - consumed, 'byte_pin')
            consumed += len(raw); yield raw

    def authenticate_all(self):
        require(self.active and not self.authenticated and not self.small_reads and self.range_count == 0, 'read_schedule')
        self.verify()
        for role in ROLES:
            hasher = hashlib.sha256()
            for raw in self._chunks(role, 0, self.plan[role]['byte_count']): hasher.update(raw)
            require(hasher.hexdigest() == self.plan[role]['sha256'], 'byte_pin'); self.verify()
        self.authenticated = True

    def read_small(self, role):
        require(self.active and self.authenticated and role in ROLES[:-1]
            and role not in self.small_reads and self.range_count == 0, 'read_schedule')
        self.verify(); self.small_reads.add(role)
        raw = b''.join(self._chunks(role, 0, self.plan[role]['byte_count']))
        require(len(raw) == self.plan[role]['byte_count'] and sha(raw) == self.plan[role]['sha256'], 'byte_pin')
        self.verify(); return raw

    def read_range(self, ordinal, offset, length, expected_sha256):
        require(self.active and self.authenticated and self.small_reads == set(ROLES[:-1])
            and type(ordinal) is int and ordinal == self.range_count < MAX_RANGES
            and type(offset) is int and offset == self.range_extent and type(length) is int
            and 0 < length <= MAX_RANGE and offset + length <= self.plan['corpus']['byte_count']
            and _hash(expected_sha256), 'range')
        self.verify(); raw = b''.join(self._chunks('corpus', offset, length))
        require(len(raw) == length and sha(raw) == expected_sha256, 'byte_pin')
        self.range_count += 1; self.range_extent += length; self.verify(); return raw

    def receipt(self):
        self.verify()
        require(self.authenticated and self.small_reads == set(ROLES[:-1]) and self.range_count == MAX_RANGES
            and self.range_extent == self.plan['corpus']['byte_count'], 'read_schedule')
        value = {'schema': SCHEMA + '-receipt', 'profile_sha256': sha(canonical(profile_record(self.plan))),
            'file_pins': self.plan, 'whole_hashes_checked': len(ROLES), 'range_count': self.range_count,
            'corpus_extent': self.range_extent, 'source_endpoint_sha256': sha(canonical([
                {'path_sha256': sha(str(row['path']).encode('utf8')), 'metadata': list(row['metadata']),
                    'security_sha256': sha(canonical(row['security']))} for row in self.objects])),
            'requires_normal_return_before_use': True, 'continuous_or_historical_integrity_proven': False,
            'source_or_price_admission_granted': False}
        return validate_receipt(value, self.plan)

    def close(self):
        failed = False
        for row in reversed(self.objects):
            try: os.close(row['fd'])
            except OSError: failed = True
        self.objects.clear(); self.paths.clear(); self.roles.clear(); self.active = False
        if failed: raise Refused('close')

    def __exit__(self, kind, *_):
        try:
            if kind is None: self.receipt()
        finally: self.close()
