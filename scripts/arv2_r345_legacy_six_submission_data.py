"""Fresh authentication of R343-B submission DATA, without operational authority.

Import and construction are inert. The caller pins this module and its selected
dependencies, exclusively claims its own prospective operation before entry,
applies native isolation, and binds the external DATA/summary/producer pins.
No claim, report, old preparation leaf or source input is read here. Successful
normal return authenticates immutable buffers at this endpoint; it grants no QC
contact, processing rights, project, capacity, launch or result authority.
"""
import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

from scripts import arv2_relocation_security as security
from scripts import arv2_r338_quarantine_input_v2 as genuine_input
from scripts import arv2_r343_legacy_six_projection as projection
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_package as compact

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
DATA = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_extension/R343-20261105-B/submission-private.json'
SCHEMA = 'arv2-r343-offline-legacy-six-preparation-v1-submission'
MAX_DATA = 16 * 1024 * 1024
MAX_SECONDS = 900
MAX_SUMMARY = 64 * 1024
UPLOAD_TOTAL = 2776584
ACTIVATION = {'byte_count': 4631, 'sha256': '70f64450a44bedfa8ea371ac74a00e2134045fb79b433b93f0114be652bc6147'}
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FLAGS = frozenset(('QC_contact', 'Safari_access', 'provider_contact', 'credential_access',
    'USB_access', 'old_operator_replayed', 'old_control_read', 'cloud_project_verified',
    'cloud_source_verified', 'cloud_objects_verified', 'cloud_capacity_verified',
    'cloud_processing_rights_verified', 'cloud_submission_permitted', 'actual_prices_verified',
    'actual_constituents_caps_verified', 'actual_holdings_path_verified', 'strategy_result_accepted',
    'point_in_time_proven', 'formal_source_admitted', 'permanent_security_master_proven',
    'paper_or_live_ready'))
FINITE = frozenset(('scope', 'deadline', 'pin', 'json', 'binding', 'summary', 'bundle',
    'input_receipt', 'candidate', 'upload', 'metadata', 'security', 'path', 'state', 'close', 'unknown'))


class Refused(ValueError):
    """Finite failure code only, never private values or raw exceptions."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise Refused('json') from None


def pin(raw):
    return {'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def valid_pin(value, maximum):
    return (type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= maximum
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None)


def loads(raw, maximum, *, lf=False):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'json')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'json')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
        require(canonical(value) + (b'\n' if lf else b'') == raw, 'json')
        return value
    except Refused:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('json') from None


def budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= MAX_SECONDS, 'deadline')


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    ar_percent: int
    project_name: str
    backtest_name: str
    profile_json: bytes
    sources: tuple[tuple[str, bytes], ...]
    public_json: bytes

    def cell_record(self):
        """A new mutable plan input; callers must bind it before dispatch."""
        return {**loads(self.public_json, MAX_SUMMARY), 'profile': loads(self.profile_json, MAX_SUMMARY),
            'source_pairs': [[name, raw.decode('ascii')] for name, raw in self.sources]}


@dataclass(frozen=True, slots=True)
class Upload:
    descriptor_json: bytes
    object_store_key: str
    activation_manifest: bool
    payload: bytes


@dataclass(frozen=True, slots=True)
class Submission:
    """Detached immutable buffers; these are data, not a launch permit."""
    producer_binding_json: bytes
    source_summary_json: bytes
    input_receipt_json: bytes
    candidates: tuple[Candidate, ...]
    uploads: tuple[Upload, ...]


def validate_uploads(value):
    require(type(value) is list and len(value) == 6, 'upload')
    objects, result = [], []
    for row in value:
        require(type(row) is dict and set(row) == {'descriptor', 'payload_base64'}
            and type(row['payload_base64']) is str and row['payload_base64'].isascii()
            and 0 < len(row['payload_base64']) <= 4 * MAX_DATA // 3 + 4, 'upload')
        try:
            descriptor = compact._upload_object_from_record(row['descriptor'])
            raw = base64.b64decode(row['payload_base64'], validate=True)
        except (compact.AcceptedRiskPreliminaryPackageError, ValueError, binascii.Error, TypeError):
            raise Refused('upload') from None
        require(base64.b64encode(raw).decode('ascii') == row['payload_base64']
            and pin(raw) == {'byte_count': descriptor.byte_count, 'sha256': descriptor.content_sha256}, 'upload')
        objects.append(descriptor)
        result.append(Upload(canonical(row['descriptor']), descriptor.object_store_key,
            descriptor.activation_manifest, raw))
    require(tuple(item.role for item in objects) == compact._UPLOAD_ROLE_ORDER
        and all(item.ordinal == 0 for item in objects)
        and len({item.object_store_key for item in objects}) == 6
        and len({item.relative_path for item in objects}) == 6
        and sum(len(item.payload) for item in result) == UPLOAD_TOTAL
        and [item.activation_manifest for item in objects] == [False] * 5 + [True], 'upload')
    final = objects[-1]
    require(pin(result[-1].payload) == ACTIVATION
        and final.object_store_key == 'arv2/preliminary-rating/27645603c1a6e0fc9fa81655/transport-manifest.json'
        and all(item.object_store_key.rsplit('/', 1)[0] == final.object_store_key.rsplit('/', 1)[0]
            for item in objects), 'upload')
    activation = loads(result[-1].payload, 64 * 1024, lf=True)
    require(type(activation) is dict and activation.get('schema') == compact.TRANSPORT_MANIFEST_SCHEMA
        and activation.get('package_sha256') == projection.OCTOBER_PACKAGE
        and activation.get('source_disposition_sha256') == projection.OCTOBER_LINEAGE
        and canonical(activation.get('objects')) == canonical([item.to_record() for item in objects[:-1]]), 'upload')
    return tuple(result)


def validate_submission(value, *, expected_summary, expected_binding):
    """Join every buffer to external canonical summary and producer bindings."""
    require(type(expected_summary) is bytes and type(expected_binding) is bytes, 'binding')
    summary = loads(expected_summary, MAX_SUMMARY)
    binding = loads(expected_binding, 4096)
    require(type(binding) is dict and set(binding) == {'expected_head', 'caller_sha256', 'profile_sha256'}
        and all(type(binding[key]) is str and re.fullmatch('[0-9a-f]{40}' if key == 'expected_head'
            else '[0-9a-f]{64}', binding[key]) for key in binding), 'binding')
    keys = {'schema', 'binding', 'claim_pin', 'private_transport_nonce', 'input_receipt',
        'prepared', 'upload_objects', 'submission_candidates', 'upload_policy', *FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and canonical(value['binding']) == expected_binding
        and valid_pin(value['claim_pin'], 128 * 1024)
        and type(value['private_transport_nonce']) is str
        and re.fullmatch('[0-9a-f]{64}', value['private_transport_nonce'])
        and value['upload_policy'] == 'exact_payloads_first_readback_activation_last_no_upload_authority'
        and all(value[key] is False for key in FLAGS), 'binding')
    try:
        projection.validate_summary(summary)
        projection.validate_bundle(value['prepared'])
    except projection.Refused:
        raise Refused('bundle') from None
    require(canonical(value['prepared']['summary']) == expected_summary, 'summary')
    try:
        receipt = genuine_input.validate_receipt(value['input_receipt'])
    except genuine_input.Refused:
        raise Refused('input_receipt') from None
    require(type(value['submission_candidates']) is list and len(value['submission_candidates']) == 7, 'candidate')
    candidates = []
    for percent, row, cell in zip(projection.AR_PERCENTS, value['submission_candidates'], value['prepared']['cells'], strict=True):
        expected = {'candidate_id': f'R343-AR{percent:03d}', 'ar_percent': percent,
            'project_name': f'ARV2 R343 LEGACY SIX AR{percent} 2021 2026 OCT13',
            'backtest_name': f'ARV2 R343 AR{percent} old-rules through 2026-10-13 A1',
            'maximum_launch_attempts': 3, 'launch_attempts_consumed': 0, 'submission_permitted': False}
        require(type(row) is dict and canonical(row) == canonical(expected), 'candidate')
        candidates.append(Candidate(row['candidate_id'], percent, row['project_name'], row['backtest_name'],
            canonical(cell['profile']), tuple((name, content.encode('ascii')) for name, content in cell['source_pairs']),
            canonical({key: cell[key] for key in summary['cells'][len(candidates)]})))
    return Submission(expected_binding, expected_summary, canonical(receipt), tuple(candidates), validate_uploads(value['upload_objects']))


def metadata(info):
    values = tuple(getattr(info, key, None) for key in FIELDS)
    require(all(type(value) is int and value >= 0 for value in values), 'metadata')
    return values


class FreshSubmission:
    """Only B DATA held through immutable-buffer consumption and final checks.

    The caller may use buffers after normal return under a separate run freeze.
    Endpoint checks are not continuous integrity, native sandboxing, source
    admission or whole-interpreter attestation. No output-leaf census occurs.
    """
    def __init__(self, *, expected_pin, expected_summary, expected_binding, deadline):
        self.expected_pin = loads(canonical(expected_pin), 4096)
        require(valid_pin(self.expected_pin, MAX_DATA), 'pin')
        require(type(expected_summary) is bytes and type(expected_binding) is bytes, 'binding')
        self.expected_summary, self.expected_binding = expected_summary, expected_binding
        self.deadline, self.rows, self.fd, self.value = deadline, [], None, None
        self.entered = False

    def _hold(self, path, parent, name, *, leaf=False):
        budget(self.deadline)
        before = metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
        require(stat.S_ISREG(before[2]) if leaf else stat.S_ISDIR(before[2]), 'path')
        if path == ROOT or ROOT in path.parents:
            require(before[3] == os.getuid() and stat.S_IMODE(before[2]) == (0o600 if leaf else 0o755 if path == ROOT else 0o700)
                and not before[9] & ~(getattr(stat, 'UF_TRACKED', 0) | getattr(stat, 'UF_HIDDEN', 0)), 'metadata')
        if leaf:
            require(before[5] == 1 and before[6] == self.expected_pin['byte_count'], 'pin')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
            | (os.O_NONBLOCK if leaf else os.O_DIRECTORY), dir_fd=parent)
        row = [fd, parent, name, before, None]
        self.rows.append(row)
        require(metadata(os.fstat(fd)) == before, 'metadata')
        if path == ROOT or ROOT in path.parents:
            row[4] = security.snapshot(fd)
        require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'metadata')
        return fd

    def _read(self):
        budget(self.deadline)
        raw, offset = bytearray(), 0
        while offset < self.expected_pin['byte_count']:
            budget(self.deadline)
            chunk = os.pread(self.fd, min(65536, self.expected_pin['byte_count'] - offset), offset)
            require(chunk, 'pin')
            raw.extend(chunk)
            offset += len(chunk)
        require(pin(raw) == self.expected_pin and not os.pread(self.fd, 1, offset), 'pin')
        return bytes(raw)

    def __enter__(self):
        require(Path.cwd() == ROOT and ROOT.resolve() == ROOT
            and DATA == ROOT / 'artifacts/analyst_revisions_v2/legacy_six_extension/R343-20261105-B/submission-private.json', 'scope')
        require(not self.entered and not self.rows and self.fd is None, 'state')
        self.entered = True
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.rows.append([fd, fd, '.', metadata(os.fstat(fd)), None])
            path = Path('/')
            for part in DATA.parts[1:]:
                path /= part
                fd = self._hold(path, fd, part, leaf=path == DATA)
            self.fd = fd
            raw = self._read()
            self.value = validate_submission(loads(raw, MAX_DATA), expected_summary=self.expected_summary,
                expected_binding=self.expected_binding)
            self.verify()
            return self
        except BaseException:
            self.close()
            raise

    def verify(self):
        require(self.fd is not None and type(self.value) is Submission, 'state')
        for fd, parent, name, before, native in self.rows:
            budget(self.deadline)
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'metadata')
            if native is not None:
                require(security.snapshot(fd) == native, 'security')
            require(metadata(os.fstat(fd)) == before, 'metadata')
        self._read()

    def close(self):
        failed = False
        for fd, *_ in reversed(self.rows):
            try:
                os.close(fd)
            except OSError:
                failed = True
        self.rows.clear()
        self.fd = None
        require(not failed, 'close')

    def __exit__(self, *_):
        try:
            self.verify()
        finally:
            self.close()
