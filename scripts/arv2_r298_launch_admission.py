"""Native-worker admission of the compiled plain R298 candidate.

No operational entrypoint, credential, transport, claim or publication exists
here. A separately frozen caller supplies the credential-free native sandbox.
The A11 exit is an externally observed frozen fact; report content cannot prove
that exit. Only A11's externally pinned report is read from that spent leaf.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import stat
import time
from types import SimpleNamespace

from scripts import run_arv2_r298_plain_readiness as a11
from research.analyst_revisions_v2_qc import newrule_plain_transport as transport
from research.analyst_revisions_v2_qc import newrule_plain_projection as projection


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
READINESS_CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_plain_readiness/R322-20261025-C'
READINESS_HEAD = '9d4725e78ce4baaa39fc080de54aba25ce69b56f'
READINESS_CALLER = 'ec7f08b6483dcac360f1cffdaa54c956f9b734543ab6f7a7579c84b7253d94e3'
READINESS_ACTUAL_EXIT = 0
READINESS_BYTES = 10684
READINESS_SHA256 = 'a0ac64a13299e9fa2a37816a15394448bbec8236c9b6636bc379b00dece375e7'
COMPILE_ID = '5bd25474163eb6cf13a005139d1c4998-2a348312a9ff411534083f2012d355b5'
SOURCE_MANIFEST = '8dfc3d3e16c0f6b555c565d9cac5d4e86a2fe35d037f95538e2a7dfe70a7bfa9'
SCHEMA = 'arv2-r298-launch-admission-v1'
FINITE = frozenset(('deadline', 'readiness_fact', 'readiness_pin', 'readiness_report',
                    'readiness_identity', 'readiness_changed', 'source', 'fresh_source',
                    'public_packet'))
canonical, parse, sha, metadata = a11.canonical, a11.parse, a11.sha, a11.metadata


class Refused(ValueError):
    """Finite local refusal with no raw evidence or exception rendering."""


def require(value, code):
    if not value:
        raise Refused(code)


def remaining(deadline):
    require(type(deadline) in (float, int) and math.isfinite(deadline)
            and deadline > time.monotonic(), 'deadline')


def selected_pins():
    return {**a11.selected_pins(),
            'scripts/run_arv2_r298_plain_readiness.py': READINESS_CALLER}


def source_checks(deadline):
    remaining(deadline)
    for relative, pin in selected_pins().items():
        require(type(relative) is str and type(pin) is str
                and re.fullmatch('[0-9a-f]{64}', pin)
                and a11.helpers._source_digest(ROOT / relative) == pin, 'source')
        remaining(deadline)


def readiness_pin():
    require(type(READINESS_ACTUAL_EXIT) is int and READINESS_ACTUAL_EXIT == 0
            and type(READINESS_HEAD) is str and re.fullmatch('[0-9a-f]{40}', READINESS_HEAD)
            and type(READINESS_BYTES) is int and 0 < READINESS_BYTES <= 128 * 1024
            and all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
                    for value in (READINESS_CALLER, READINESS_SHA256, SOURCE_MANIFEST))
            and type(COMPILE_ID) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', COMPILE_ID),
            'readiness_fact')
    return {'byte_count': READINESS_BYTES, 'sha256': READINESS_SHA256,
            'actual_readiness_exit': READINESS_ACTUAL_EXIT, 'expected_head': READINESS_HEAD,
            'caller_sha256': READINESS_CALLER, 'compile_id': COMPILE_ID,
            'source_manifest_sha256': SOURCE_MANIFEST}


class ReadinessReport:
    """Retain A11's report descriptor and full metadata until admission returns."""

    def __init__(self):
        self.fd, self.chain = a11._storage_module()._walk(READINESS_CONTROL)
        self.leaf = None
        try:
            self.baseline = metadata(os.fstat(self.fd))
            self.verify()
        except BaseException:
            os.close(self.fd)
            raise

    def __enter__(self): return self

    def __exit__(self, *_):
        if self.leaf is not None:
            os.close(self.leaf[0])
        os.close(self.fd)

    def verify(self):
        other, chain = a11._storage_module()._walk(READINESS_CONTROL)
        try:
            held, named = os.fstat(self.fd), os.fstat(other)
            require(chain == self.chain and metadata(held) == metadata(named) == self.baseline
                    and stat.S_ISDIR(held.st_mode) and held.st_uid == os.getuid()
                    and stat.S_IMODE(held.st_mode) == 0o700, 'readiness_changed')
            if self.leaf is not None:
                fd, baseline, _ = self.leaf
                require(metadata(os.fstat(fd)) == baseline
                        == metadata(os.stat('report.json', dir_fd=other, follow_symlinks=False)),
                        'readiness_changed')
            require(metadata(os.fstat(other)) == self.baseline, 'readiness_changed')
        finally:
            os.close(other)

    def read(self, deadline):
        remaining(deadline)
        self.verify()
        require(self.leaf is None, 'readiness_report')
        fd = os.open('report.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                    and info.st_size == READINESS_BYTES, 'readiness_report')
            raw = bytearray()
            while len(raw) <= info.st_size:
                remaining(deadline)
                chunk = os.read(fd, min(65536, info.st_size + 1 - len(raw)))
                if not chunk: break
                raw.extend(chunk)
            require(len(raw) == info.st_size and metadata(info) == metadata(os.fstat(fd))
                    == metadata(os.stat('report.json', dir_fd=self.fd, follow_symlinks=False)),
                    'readiness_changed')
            raw = bytes(raw)
            require(sha(raw) == READINESS_SHA256, 'readiness_pin')
            self.leaf = fd, metadata(info), raw
        except BaseException:
            os.close(fd)
            raise
        self.verify()
        return raw


def validate_report(raw):
    """Authenticate supplied report bytes before parsing or using its receipt."""
    pin = readiness_pin()
    require(type(raw) is bytes and len(raw) == pin['byte_count']
            and sha(raw) == pin['sha256'], 'readiness_pin')
    try:
        value = parse(raw)
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise Refused('readiness_report') from None
    args = SimpleNamespace(operation='recover', expected_head=READINESS_HEAD,
                           caller_sha256=READINESS_CALLER)
    binding = a11.binding(args)
    require(set(value) == set(binding) | {'result', 'operation_completed', *a11.FALSE_FLAGS}
            and canonical({key: value[key] for key in binding}) == canonical(binding)
            and value['operation_completed'] is True
            and all(value[key] is False for key in a11.FALSE_FLAGS), 'readiness_report')
    envelope = {'schema': a11.SCHEMA, 'operation': 'recover', 'binding': binding,
                'operation_completed': True, 'result': {'report': {
                    'byte_count': pin['byte_count'], 'sha256': pin['sha256']}, 'result': value['result']},
                **a11.FALSE_FLAGS}
    validated = a11.validate_output(canonical(envelope) + b'\n', READINESS_ACTUAL_EXIT, args)
    receipt = validated['result']['result']['ready_receipt']
    require(receipt['compile_id'] == COMPILE_ID
            and receipt['source_manifest_sha256'] == SOURCE_MANIFEST, 'readiness_identity')
    return pin


def _snapshot(plain, projected):
    transport.require_plain_transport(plain)
    projection.require_plain_projection(projected, a11.remote.PROJECTION_SHA256)
    require(projected._transport is plain, 'fresh_source')
    return (plain.record_bytes, projected.record_bytes, projected.profile_bytes,
            tuple((canonical(item.to_record()), item.payload) for item in plain.upload_objects),
            tuple((item.project_path, item.source_bytes) for item in projected.source_files))


def validate_packet(packet):
    """Pure receiver check for the native worker's bounded public evidence."""
    try:
        require(type(packet) is dict and set(packet) == {'admission_authenticated',
                'projection_record', 'source_pairs', 'readiness_pin', 'storage_receipt'}
                and canonical(packet['readiness_pin']) == canonical(readiness_pin()), 'public_packet')
        result = a11._validate_worker_result({key: value for key, value in packet.items()
                                             if key != 'readiness_pin'})
        require(len(canonical(packet)) <= a11.WORKER_MAX_OUTPUT, 'public_packet')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refused('public_packet') from None
    return result


def admit(deadline):
    """Fresh current input plus pinned D2 and A11 evidence; no remote action."""
    readiness_pin()
    source_checks(deadline)
    plain, projected = a11.prep.construct(deadline)
    initial = _snapshot(plain, projected)
    receipt = a11.authenticate_storage(plain, projected, deadline)
    with ReadinessReport() as report:
        pin = validate_report(report.read(deadline))
        fresh_plain, fresh_projected = a11.prep.construct(deadline)
        require(_snapshot(fresh_plain, fresh_projected) == initial, 'fresh_source')
        source_checks(deadline)
        report.verify()
        remaining(deadline)
        packet = {'admission_authenticated': True, 'projection_record': projected.record_bytes.decode('ascii'),
                  'source_pairs': [[item.project_path, item.source_bytes.decode('ascii')]
                                   for item in projected.source_files],
                  'readiness_pin': pin, 'storage_receipt': receipt}
        validate_packet(packet)
        return packet
