"""One freshly claimed, recoverable cleanup of 22 proved own EXT26 uploads.

Only official properties/delete are available. All 72 lossless processing
proofs, 22 unchanged originals and 22 remote key/size/MD5 observations precede
the first deletion. Claims are permanent, including uncertain requests; there
is no retry, export, listing, compression, upload, outcome or trading route.
POSIX cooperative custody is not provider attestation or canonical acceptance.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import subprocess
import threading
import time

from . import extended_evidence as e, extended_operations as ops, extended_compression as compression

LANE, BRANCH, PRIVATE_ROOT, INPUT_ROOT = ops.LANE, ops.BRANCH, ops.PRIVATE_ROOT, ops.INPUT_ROOT
PREFIX = 'research/target_price_revisions_qc/'
ON = 'TPR-CAP-TILT-EXT26-ON-BASE-v1'
PROJECT_ID = 37650453
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
OPERATION_ID = 'TPR-EXT26-CLEANUP-20261010-001'
QC_OPERATION = 'TPR-EXT26-QC-20261010-002'
DISCOVERY_RECEIPT_SHA256 = '7e167c35854290c5096afdcd6d9552272eb620ca4ad20bcab93d9f573e97e08f'
DISCOVERY_ADMISSION_SHA256 = '0b7abb5cfcc7525165769e47862f73a0838f62ae1bc07dba897073e34f45ea3b'
DISCOVERY_ADMISSION = 'TPR-EXT26-PROJECT-DIAG-20261010-001.project-admission.json'
DISCOVERY_ADMISSION_BYTES = 1616
DIAGNOSTIC = 'TPR-EXT26-UPLOAD-DIAG-20261010-001.result.json'
DIAGNOSTIC_SHA256 = '2966bfbdd3c5c726f2f1c1284e043cc6ee19409e6c1e46c5778ec34f50a54699'
DIAGNOSTIC_BYTES = 68233
COMP_OPERATION = 'TPR-EXT26-COMPRESS-20261010-001'
COMP_SHA256 = 'fac2b57ef3f70e5bb086d95c0c24237987078527667586aaea9c7dc85039dc87'
COMP_BYTES = 58858
MAPPING_SHA256 = '1088cd012cfa0a99dc248a526ee64a01bc08b0da7061d7f722d1017a409f6933'
MAPPING_BYTES = 57064
COMP_PLAN_SHA256 = 'a22c899f38fa4d3cd9c2737e5758e24916dcf48ed1d0997ac8cec6c680ffd2c9'
MANIFEST_SHA256 = 'd20d96f9a69ddaccbc8e0866794e1106897b19cbfa8aa72fc9f6f4458669ab9b'
BUNDLE = compression.BUNDLE
BUNDLE_SHA256 = compression.BUNDLE_SHA256
TARGET_SHA256 = tuple('''0517643e30eefdbe1625db4eb470f343b7e322d5c438be710b0ac85ccc347a9b
1399319deec9dba471f93105dce70dd54e988e986e17fe28638098d6eae6984c
13a156b050127bf0976afd737208e4bddc03fb9bfd1fb477bc155f0f42429287
15c40988a821fb1ec7747f1acfc7df9a3bb984b60e982a2473165eaf0744bb2b
19e13989ab61b04073797922c2a16a1563afc16efc6f8c2b055270e51fbf8e6b
1aea46de4167b20c916f82957d112f76941c75d151604ca98a24135177c81919
1ca0d67b9acf10d6382277f24dfc462f8af48de8654a995de92f74eb9c93a0cb
1db075bc8f8b9e2c00db90fb4013124d3690f94eee8c1d423abd3d3622e1f10d
1fb5ab89b79ca866e7a24756af3954dd34c3e5d295fed1d8722680711ab5586b
20ae1c99dbc3558746b5c543d146b2891208fc11f647b539ba9042c2200623ba
221cd42251fad3bfa722b10df62ce4b6be9753b87f2c204c8cb23d7761b8fb2a
2375ffe3726bec9dcaa54e4fb91b3eb4daa6bc98355142a40a52fdf6c747c96a
26ba993bb361fa3c4abbc276bd5d845251870d46ec68980fd3ec7bfd2adb78b4
2c6a90bdd2faef7b8f3f8af810316e5833d06c6a94c28659e9128533ff7c950c
2cf0efc355e551fa853db3a00a4a10f235509a729a8119425845fe7575b06561
2dc16aab8adcdefe9a67c865b38b75ffe7ef4df4e57e6cd623d19bc755a4f9e1
34182f08ef39f471289e2ddce82a94732c120704f8d52a226223a6b806f49231
3dadb8216f969de2c554e212f71b5bf8135010f5c137b090bc56cc32287e3dd7
42b3d77626a8fe072dda2122c93fd586ddd3fede4c8d4aab8d2925c5caa66e32
42e89cd6d54d29b627e8fc3a4f55442e5c6002d7f52d6c3ec0247a8d17193ada
43fe008bb652fc5ada8e428e20fa2a38597513ccdd1bbc7a654c55d397cdffcf
4ffbccfb4f56105e73fa134617127e4b6957fb3ce80a08cb833f97ff4b40eb49'''.split())
TARGET_BYTES = 74557156
MAX_FILE, MAX_TOTAL, MAX_RESPONSE, MAX_SECONDS = 32 * 1024 * 1024, 128 * 1024 * 1024, 1024 * 1024, 1500
ENDPOINTS = frozenset({'object/properties', 'object/delete'})
INITIALIZERS = compression.INITIALIZERS
SOURCE_PATHS = tuple(INITIALIZERS) + tuple(PREFIX + name for name in (
    'extended_cleanup.py', 'extended_compression.py', 'extended_compressed_store.py',
    'extended_evidence.py', 'extended_operations.py', 'extended_operations_successor.py', 'extended_upload_diagnostic.py')) + (BUNDLE,)
SOURCE_PINS = {**INITIALIZERS, BUNDLE: BUNDLE_SHA256,
    PREFIX + 'extended_compression.py': '7031ef283e58951332a083a4ef3de079d2fe8a5a43baeb1c6b4f066736476cab',
    PREFIX + 'extended_compressed_store.py': 'd661b5752c35b9dd04f783f5d78850f453d5f5f299874e5cf19700599df2356e',
    PREFIX + 'extended_operations.py': '824b3f0c180f1aeb7038d8f280c44507b5c39687fcccc87c539f242d9256d167',
    PREFIX + 'extended_operations_successor.py': '2b40663647ad13b55388c5b11e0bbb6a62d611cfb81a17953c2f3ea175fd4723',
    PREFIX + 'extended_upload_diagnostic.py': '9bb026bc7caf45762f84e68725f3db9768ad3d703d03549764899afc68be5b2c'}
Refusal = e.EvidenceError
_sha, _clock, _guard, _open_directory, _publish = compression._sha, compression._clock, compression._guard, compression._open_directory, compression._publish


def _fail(): raise Refusal('scoped cleanup refused or uncertain; no automatic retry')
def _now(): return datetime.now(timezone.utc)


def _read(directory, name, *, expected=None, maximum=MAX_FILE, private=True):
    """Owned FD exact size/budget BEFORE body; growth is never budget-refunded."""
    compression._name(name); fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if (type(maximum) is not int or not 0 <= maximum <= MAX_FILE or not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1 or not (1 if private else 0) <= before.st_size <= maximum
                or expected is not None and before.st_size != expected
                or private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600)): _fail()
        pieces, remaining = [], before.st_size
        while remaining:
            raw = os.read(fd, min(65536, remaining))
            if not raw: _fail()
            pieces.append(raw); remaining -= len(raw)
        after = os.fstat(fd); named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if any(getattr(before, key) != getattr(value, key) for value in (after, named) for key in
            ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')): _fail()
        return b''.join(pieces)
    finally:
        if fd is not None: os.close(fd)


def _sources(head):
    result = {}
    for relative in SOURCE_PATHS:
        _guard(head); directory = _open_directory((LANE / relative).parent)
        try: raw = _read(directory, Path(relative).name, private=False)
        finally: os.close(directory)
        committed = subprocess.run(['git', 'show', head + ':' + relative], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != committed: _fail()
        result[relative] = raw
    if any(_sha(result[name]) != identity for name, identity in SOURCE_PINS.items()): _fail()
    _guard(head); return result


def _targets(bundle_raw):
    preparation, inventory = compression._inventory(bundle_raw)
    if len(TARGET_SHA256) != 22 or len(set(TARGET_SHA256)) != 22: _fail()
    for identity in TARGET_SHA256: e._hash(identity)
    targets = [row for row in inventory if row['sha256'] in TARGET_SHA256]
    if len(targets) != 22 or tuple(row['sha256'] for row in targets) != TARGET_SHA256 or sum(row['bytes'] for row in targets) != TARGET_BYTES: _fail()
    return preparation, inventory, targets


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
          operation_id, bundle_raw, mode='production'):
    if operation_id != OPERATION_ID or mode not in {'production', 'offline-fixture'} or set(source_hashes) != set(SOURCE_PATHS): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    for identity in source_hashes.values(): e._hash(identity)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 86400: _fail()
    preparation, _, targets = _targets(bundle_raw)
    return {'schema': 'tpr-ext26-cleanup-plan-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'operation_id': operation_id, 'owner_instruction_sha256': owner_instruction_sha256,
        'git_head': git_head, 'source_hashes': source_hashes, 'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'candidate_id': ON, 'project_id': PROJECT_ID, 'organization_id_sha256': ORGANIZATION_SHA256, 'bundle_sha256': BUNDLE_SHA256,
        'preparation_sha256': preparation, 'qc_operation_id': QC_OPERATION, 'manifest_sha256': MANIFEST_SHA256,
        'upload_diagnostic_sha256': DIAGNOSTIC_SHA256, 'compression_sha256': COMP_SHA256,
        'compression_mapping_sha256': MAPPING_SHA256, 'compression_plan_sha256': COMP_PLAN_SHA256,
        'discovery_admission_name': DISCOVERY_ADMISSION, 'discovery_admission_sha256': DISCOVERY_ADMISSION_SHA256,
        'discovery_admission_bytes': DISCOVERY_ADMISSION_BYTES,
        'targets': targets, 'target_count': 22, 'target_original_bytes': TARGET_BYTES,
        'max_file_bytes': MAX_FILE, 'max_total_read_bytes': MAX_TOTAL, 'max_response_bytes': MAX_RESPONSE,
        'max_requests': 44, 'request_seconds': 30, 'max_seconds': MAX_SECONDS,
        'mode': mode, 'lane_root': str(LANE), 'lane_branch': BRANCH,
        'private_root': str(PRIVATE_ROOT), 'input_root': str(INPUT_ROOT),
        'originals_deleted': False, 'source_reaccess': False, 'outcome_reads': False, 'exports': False,
        'automatic_retry': False, 'old_receipts_renewed': False, 'quantconnect_attempts': 0,
        'development_looks': 0, 'canonical_admission': False, 'trading': False}


def _compression_proof(result_raw, mapping_raw, bundle_raw, sources):
    if len(result_raw) != COMP_BYTES or _sha(result_raw) != COMP_SHA256 or len(mapping_raw) != MAPPING_BYTES or _sha(mapping_raw) != MAPPING_SHA256: _fail()
    receipt, mapping = e.parse_json(result_raw), e.parse_json(mapping_raw)
    keys = ('schema study_id freeze_sha256 operation_id plan_sha256 git_head source_hashes owner_instruction_sha256 bundle_sha256 '
        'preparation_sha256 status scope_spent failure input_count processed_count original_bytes gzip_bytes ratio payloads original_read_bytes '
        'derived_read_bytes stored_derived_bytes mapping_name mapping_sha256 mapping_bytes encoding gzip_level gzip_mtime gzip_filename '
        'python_version zlib_compile_version zlib_runtime_version originals_retained_unchanged decompressed_bytes_exact source_reaccess '
        'outcome_reads cloud_uploads cloud_deletes quantconnect_attempts development_looks automatic_retry old_receipts_renewed '
        'canonical_admission trading ended_utc').split()
    e._closed(receipt, keys)
    preparation, inventory, _ = _targets(bundle_raw)
    expected = {'schema': 'tpr-ext26-compression-receipt-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'operation_id': COMP_OPERATION, 'plan_sha256': COMP_PLAN_SHA256, 'bundle_sha256': BUNDLE_SHA256,
        'preparation_sha256': preparation, 'status': 'COMPLETED', 'scope_spent': True, 'failure': None,
        'mapping_name': COMP_OPERATION + '.mapping.json', 'mapping_sha256': MAPPING_SHA256,
        'encoding': 'gzip', 'gzip_filename': '', 'originals_retained_unchanged': True, 'decompressed_bytes_exact': True}
    if any(receipt[key] != value for key, value in expected.items()): _fail()
    for key in ('source_reaccess', 'outcome_reads', 'automatic_retry', 'old_receipts_renewed', 'canonical_admission', 'trading'):
        if receipt[key] is not False: _fail()
    def count(value):
        if type(value) is not e.JsonNumber or value.fraction().denominator != 1 or value.fraction() < 0: _fail()
        return int(value.fraction())
    gzip_total = count(receipt['gzip_bytes'])
    exact = {'input_count': 72, 'processed_count': 72, 'original_bytes': compression.ORIGINAL_BYTES,
        'original_read_bytes': 2 * compression.ORIGINAL_BYTES, 'mapping_bytes': MAPPING_BYTES,
        'gzip_level': 9, 'gzip_mtime': 0, 'derived_read_bytes': gzip_total + MAPPING_BYTES,
        'stored_derived_bytes': gzip_total + MAPPING_BYTES, 'cloud_uploads': 0, 'cloud_deletes': 0,
        'quantconnect_attempts': 0, 'development_looks': 0}
    if any(count(receipt[key]) != value for key, value in exact.items()) or not 0 < gzip_total < compression.MAX_DERIVED: _fail()
    e._closed(receipt['ratio'], {'numerator', 'denominator'})
    if count(receipt['ratio']['numerator']) != gzip_total or count(receipt['ratio']['denominator']) != compression.ORIGINAL_BYTES: _fail()
    e._hash(receipt['git_head'], 40); e._hash(receipt['owner_instruction_sha256']); _clock(receipt['ended_utc'])
    source_hashes = {name: _sha(sources[name]) for name in compression.SOURCE_PATHS}
    if receipt['source_hashes'] != source_hashes: _fail()
    if type(receipt['payloads']) is not list or len(receipt['payloads']) != 72: _fail()
    stored = set(); total = 0
    for row, original in zip(receipt['payloads'], inventory):
        e._closed(row, {'plain_name', 'logical_key', 'plain_sha256', 'plain_bytes', 'stored_name', 'stored_key', 'gzip_sha256', 'gzip_bytes'})
        identity = e._hash(row['gzip_sha256']); encoded = e._integer(row['gzip_bytes'], MAX_FILE)
        if (row['plain_name'] != original['name'] or row['logical_key'] != original['key'] or row['plain_sha256'] != original['sha256']
                or e._integer(row['plain_bytes'], MAX_FILE) != original['bytes'] or row['stored_name'] != 'gzip.' + identity + '.json'
                or row['stored_key'] != original['key'].rsplit('/', 1)[0] + '/' + row['stored_name'] or row['stored_name'] in stored): _fail()
        stored.add(row['stored_name']); total += encoded
    if total != gzip_total: _fail()
    expected_mapping = {'schema': 'tpr-ext26-gzip-input-map-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'preparation_sha256': preparation, 'bundle_sha256': BUNDLE_SHA256, 'processing_operation_id': COMP_OPERATION,
        'processing_plan_sha256': COMP_PLAN_SHA256, 'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'payloads': receipt['payloads']}
    if e.canonical(mapping) != e.canonical(expected_mapping): _fail()
    return receipt


def _upload_proof(raw, targets):
    if len(raw) != DIAGNOSTIC_BYTES or _sha(raw) != DIAGNOSTIC_SHA256: _fail()
    body = e.parse_json(raw)
    if (body.get('schema') != 'tpr-ext26-upload-diagnostic-receipt-v1' or body.get('status') != 'COMPLETED'
            or body.get('scope_spent') is not True or body.get('study_id') != e.STUDY_ID
            or body.get('candidate_id') != ON or body.get('qc_operation_id') != QC_OPERATION
            or body.get('read_operation_id') + '.result.json' != DIAGNOSTIC
            or body.get('source_hashes', {}).get(PREFIX + 'extended_upload_diagnostic.py') != SOURCE_PINS[PREFIX + 'extended_upload_diagnostic.py']): _fail()
    for key in ('automatic_retry', 'upload_repeated', 'old_receipts_renewed', 'licensed_payload_reads', 'off_response_reads', 'canonical_admission', 'trading'):
        if body.get(key) is not False: _fail()
    census = body.get('census')
    if type(census) is not dict or type(census.get('inputs')) is not list or len(census['inputs']) != 72: _fail()
    rows = census['inputs']; completed = {row.get('input_sha256') for row in rows if type(row) is dict and row.get('status') == 'completed'}
    if completed != set(TARGET_SHA256) or len(completed) != 22: _fail()
    for row in rows:
        if type(row) is not dict: _fail()
        if row.get('input_sha256') in TARGET_SHA256:
            if row.get('terminal_status') != 'succeeded' or row.get('error_classification') is not None: _fail()
            e._hash(row.get('original_wire_sha256')); e._hash(row.get('projection_sha256')); e._integer(row.get('request_sequence'), 96)
    inventory = body.get('read_inventory', {})
    if inventory.get('manifest.' + QC_OPERATION + '.json', {}).get('sha256') != MANIFEST_SHA256: _fail()
    return body


def _md5(value):
    if type(value) is not str: _fail()
    if re.fullmatch(r'[0-9a-fA-F]{32}', value): return value.lower()
    if re.fullmatch(r'[A-Za-z0-9+/]{22}==', value):
        try: decoded = base64.b64decode(value, validate=True)
        except ValueError: _fail()
        if len(decoded) == 16 and base64.b64encode(decoded).decode() == value: return decoded.hex()
    _fail()


def _project(value):
    """Exact immutable recovered-project producer shape, not attestation."""
    e._closed(value, {'candidate_id', 'project_id', 'name', 'organization_id', 'owner', 'lean_version_id', 'max_file_size', 'at',
        'privacy_provenance', 'recovery_provenance'})
    if value['candidate_id'] != ON or e._integer(value['project_id']) != PROJECT_ID or value['name'] != ON + '-private' or value['owner'] is not True: _fail()
    organization = e._id(value['organization_id']); _clock(value['at']); e._integer(value['max_file_size'])
    if _sha(organization.encode('utf-8')) != ORGANIZATION_SHA256: _fail()
    if value['lean_version_id'] is not None: e._integer(value['lean_version_id'])
    privacy = value['privacy_provenance']
    e._closed(privacy, {'is_public_field_returned', 'returned_is_public', 'documented_default_private', 'documented_default_reference',
        'privacy_attested', 'provider_privacy_attestation', 'collaborators_field_returned', 'origin_operation_id', 'origin_kind'})
    if (type(privacy['is_public_field_returned']) is not bool or type(privacy['collaborators_field_returned']) is not bool
            or privacy['returned_is_public'] is not (False if privacy['is_public_field_returned'] else None)
            or privacy['documented_default_private'] is not True
            or privacy['documented_default_reference'] != 'https://www.quantconnect.com/docs/v2/cloud-platform/security-and-ip'
            or privacy['privacy_attested'] is not False or privacy['provider_privacy_attestation'] is not False
            or privacy['origin_operation_id'] != 'TPR-EXT26-QC-20261010-001'
            or privacy['origin_kind'] != 'immutable_original_create_response_recovery'): _fail()
    recovery = value['recovery_provenance']
    e._closed(recovery, {'discovery_receipt_sha256', 'discovery_admission_sha256', 'original_six_file_hashes', 'original_wire_sha256',
        'original_projection_sha256', 'network_creates', 'new_looks', 'quantconnect_attempts', 'arbitrary_project_adoption'})
    if (recovery['discovery_receipt_sha256'] != DISCOVERY_RECEIPT_SHA256
            or recovery['discovery_admission_sha256'] != DISCOVERY_ADMISSION_SHA256
            or recovery['arbitrary_project_adoption'] is not False): _fail()
    for key in ('network_creates', 'new_looks', 'quantconnect_attempts'):
        if type(recovery[key]) is not e.JsonNumber or recovery[key].fraction() != 0: _fail()
    e._closed(recovery['original_six_file_hashes'], {'operations_manifest', 'stage_spent', 'stage_transport', 'request_spent', 'request_terminal', 'request_projection'})
    for identity in recovery['original_six_file_hashes'].values(): e._hash(identity)
    e._hash(recovery['original_wire_sha256']); e._hash(recovery['original_projection_sha256'])
    return organization


def _echo_safe(raw, token):
    body = e.parse_json(raw)
    # Echo detection precedes any receipt persistence, including escaped strings.
    def echo(value):
        if type(value) is str: return bool(token) and token in value
        if type(value) is dict: return any(echo(key) or echo(item) for key, item in value.items())
        if type(value) is list: return any(echo(item) for item in value)
        return False
    if token and (token.encode() in raw or echo(body)): _fail()
    if type(body) is not dict: _fail()
    metadata = body.get('metadata')
    if type(metadata) is dict: metadata.pop('preview', None)  # Never retain a projection or row-bearing preview.
    return body


def _admission(raw, project):
    """Independently pinned original destination; provenance strings alone fail."""
    if len(raw) != DISCOVERY_ADMISSION_BYTES or _sha(raw) != DISCOVERY_ADMISSION_SHA256: _fail()
    value = e.parse_json(raw)
    e._closed(value, {'schema', 'study_id', 'candidate_id', 'origin_operation_id', 'discovery_read_operation_id',
        'discovery_plan_sha256', 'field_census_sha256', 'six_file_hashes', 'response_wire_sha256',
        'response_projection_sha256', 'request_payload_sha256', 'project', 'privacy', 'admitted'})
    if (value['schema'] != 'tpr-ext26-project-discovery-admission-v1' or value['study_id'] != e.STUDY_ID
            or value['candidate_id'] != ON or value['origin_operation_id'] != 'TPR-EXT26-QC-20261010-001'
            or value['discovery_read_operation_id'] + '.project-admission.json' != DISCOVERY_ADMISSION
            or value['admitted'] is not False): _fail()
    original = value['project']
    e._closed(original, {'project_id', 'name', 'organization_id', 'owner', 'lean_version_id', 'max_file_size'})
    if (e._integer(original['project_id']) != PROJECT_ID or original['name'] != ON + '-private'
            or original['owner'] is not True or e._id(original['organization_id']) != project['organization_id']
            or original['name'] != project['name'] or original['owner'] is not project['owner']
            or e._integer(original['max_file_size']) != e._integer(project['max_file_size'])): _fail()
    if original['lean_version_id'] is None:
        if project['lean_version_id'] is not None: _fail()
    elif project['lean_version_id'] is None or e._integer(original['lean_version_id']) != e._integer(project['lean_version_id']): _fail()
    recovery = project['recovery_provenance']
    if (value['six_file_hashes'] != recovery['original_six_file_hashes']
            or value['response_wire_sha256'] != recovery['original_wire_sha256']
            or value['response_projection_sha256'] != recovery['original_projection_sha256']): _fail()
    for key in ('discovery_plan_sha256', 'field_census_sha256', 'request_payload_sha256'): e._hash(value[key])
    privacy = value['privacy']
    e._closed(privacy, {'is_public_returned', 'is_public', 'documented_default_private', 'returned_private_field_false', 'privacy_attested'})
    if (privacy['is_public_returned'] is not project['privacy_provenance']['is_public_field_returned']
            or privacy['is_public'] is not project['privacy_provenance']['returned_is_public']
            or privacy['documented_default_private'] is not False
            or privacy['returned_private_field_false'] is not (privacy['is_public'] is False)
            or privacy['privacy_attested'] is not False): _fail()
    return original['organization_id']


def _response(raw, endpoint, target, *, token='', http_status=200):
    body = _echo_safe(raw, token)
    metadata = body.get('metadata')
    required = {'success', 'metadata'} if endpoint == 'object/properties' else {'success'}
    if not required <= set(body) or set(body) - required - {'errors'}: _fail()
    if endpoint not in ENDPOINTS or 'errors' in body and (type(body['errors']) is not list or body['errors']) or body['success'] is not True or type(http_status) is not int or http_status != 200: _fail()
    if endpoint == 'object/delete': return {'success': True}
    if type(metadata) is not dict or not {'key', 'size', 'md5'} <= set(metadata) or set(metadata) - {'key', 'size', 'md5', 'modified', 'created', 'mime'}: _fail()
    if metadata['key'] != target['key'] or e._integer(metadata['size'], MAX_FILE) != target['bytes'] or _md5(metadata['md5']) != target['md5']: _fail()
    return {'success': True, 'key': target['key'], 'size': metadata['size'], 'md5': _md5(metadata['md5'])}


def _transport(endpoint, raw):
    """Exact two-endpoint TLS route, called only after durable request claim."""
    if endpoint not in ENDPOINTS: _fail()
    connection = None
    with _request_deadline():
        user, token = ops.credential()
        stamp = str(int(time.time())); signed = hashlib.sha256((token + ':' + stamp).encode()).hexdigest()
        authorization = base64.b64encode((user + ':' + signed).encode()).decode()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); context.keylog_filename = None
        context.check_hostname, context.verify_mode = True, ssl.CERT_REQUIRED; context.load_default_certs()
        try:
            connection = http.client.HTTPSConnection('www.quantconnect.com', timeout=30, context=context)
            connection.request('POST', '/api/v2/' + endpoint, body=raw,
                headers={'Authorization': 'Basic ' + authorization, 'Timestamp': stamp, 'Content-Type': 'application/json'})
            response = connection.getresponse(); wire = response.read(MAX_RESPONSE + 1)
            if not 0 < len(wire) <= MAX_RESPONSE: _fail()
            return wire, response.status, token
        finally:
            if connection is not None: connection.close()


@contextmanager
def _request_deadline():
    """Bound total request wall time without discarding the outer scope timer."""
    if threading.current_thread() is not threading.main_thread(): _fail()
    remaining, interval = signal.getitimer(signal.ITIMER_REAL)
    if interval != 0.0: _fail()
    previous, started = signal.getsignal(signal.SIGALRM), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: _fail())
    signal.setitimer(signal.ITIMER_REAL, min(30, remaining) if remaining else 30)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        if remaining: signal.setitimer(signal.ITIMER_REAL, max(0.000001, remaining - (time.monotonic() - started)))


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0): _fail()
    old = signal.getsignal(signal.SIGALRM); signal.signal(signal.SIGALRM, lambda *_: _fail()); signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
    try: yield
    finally: signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old)


def _execute(plan, sources, operations_path, inputs_path, *, clock, guard, transport):
    args = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc', 'operation_id', 'mode')}
    if e.canonical(plan) != e.canonical(_plan(**args, bundle_raw=sources[BUNDLE])): _fail()
    if (plan['mode'] == 'production' and (operations_path != PRIVATE_ROOT or inputs_path != INPUT_ROOT)
            or plan['mode'] == 'offline-fixture' and any(path.is_relative_to(LANE) for path in (operations_path, inputs_path))): _fail()
    started, operation_fd, input_fd, total = time.monotonic(), None, None, 0
    def check():
        guard(plan['git_head']); now = clock()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0) or not _clock(plan['created_utc']) <= now < _clock(plan['expires_utc'])
                or time.monotonic() - started >= MAX_SECONDS or {name: _sha(raw) for name, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        operation_fd = _open_directory(operations_path)
        info = os.fstat(operation_fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        _publish(operation_fd, OPERATION_ID + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-cleanup-receipt-v1', 'study_id': e.STUDY_ID, 'operation_id': OPERATION_ID,
            'plan_sha256': _sha(e.canonical(plan)), 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
            'owner_instruction_sha256': plan['owner_instruction_sha256'], 'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True,
            'failure': None, 'read_inventory': {}, 'read_bytes': 0, 'local_verified': [], 'properties_verified': [],
            'deleted': [], 'requests': [], 'all_72_processing_proof_verified': False, 'all_22_prechecks_verified': False,
            'originals_preserved': True, 'source_reaccess': False, 'outcome_reads': False, 'exports': False,
            'automatic_retry': False, 'old_receipts_renewed': False, 'quantconnect_attempts': 0, 'development_looks': 0,
            'canonical_admission': False, 'trading': False, 'provider_authenticity_independently_verified': False}
        def read(directory, domain, name, *, identity=None, expected=None):
            nonlocal total
            check(); raw = _read(directory, name, expected=expected, maximum=min(MAX_FILE, MAX_TOTAL - total))
            total += len(raw); report['read_inventory'][domain + '/' + name] = {'sha256': _sha(raw), 'bytes': len(raw)}
            if identity is not None and _sha(raw) != identity: _fail()
            return raw
        def request(endpoint, target, organization):
            check()
            if endpoint not in ENDPOINTS or len(report['requests']) >= 44: _fail()
            payload = e.canonical({'organizationId': organization, 'key': target['key']})
            kind = endpoint.split('/')[-1]
            claim_name = 'ext26.cleanup.' + kind + '.' + target['sha256'] + '.spent.json'
            _publish(operation_fd, claim_name, e.canonical({'at': clock().isoformat(), 'operation_id': OPERATION_ID,
                'plan_sha256': report['plan_sha256'], 'endpoint': endpoint, 'payload_sha256': _sha(payload), 'input_sha256': target['sha256']}))
            observation = {'endpoint': endpoint, 'input_sha256': target['sha256'], 'payload_sha256': _sha(payload),
                'status': 'FAILED_OR_UNCERTAIN', 'original_wire_sha256': None, 'original_wire_bytes': None,
                'safe_metadata': None, 'automatic_retry': False}
            report['requests'].append(observation)
            try:
                check(); raw, status, token = transport(endpoint, payload)
                if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE: _fail()
                _echo_safe(raw, token)
                observation.update(original_wire_sha256=_sha(raw), original_wire_bytes=len(raw))
                safe = _response(raw, endpoint, target, token=token, http_status=status)
                observation.update(status='SUCCEEDED', original_wire_sha256=_sha(raw), original_wire_bytes=len(raw), safe_metadata=safe)
                check()
            except (Exception, KeyboardInterrupt):
                _publish(operation_fd, claim_name.replace('.spent.json', '.terminal.json'), e.canonical(observation)); _fail()
            _publish(operation_fd, claim_name.replace('.spent.json', '.terminal.json'), e.canonical(observation))
        try:
            input_fd = _open_directory(inputs_path); info = os.fstat(input_fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
            project = e.parse_json(read(operation_fd, 'operations', ON + '.project.json'))
            organization = _project(project)
            if _admission(read(operation_fd, 'operations', DISCOVERY_ADMISSION,
                    identity=DISCOVERY_ADMISSION_SHA256, expected=DISCOVERY_ADMISSION_BYTES), project) != organization: _fail()
            manifest_raw = read(operation_fd, 'operations', 'manifest.' + QC_OPERATION + '.json', identity=MANIFEST_SHA256)
            manifest, bundle = e.parse_json(manifest_raw), e.parse_json(sources[BUNDLE])
            ops.validate_manifest(manifest)
            if manifest['operation_id'] != QC_OPERATION or any(manifest[key] != bundle[key] for key in ('candidates', 'inputs', 'preparation_sha256')): _fail()
            _upload_proof(read(operation_fd, 'operations', DIAGNOSTIC, identity=DIAGNOSTIC_SHA256, expected=DIAGNOSTIC_BYTES), plan['targets'])
            result_raw = read(input_fd, 'inputs', COMP_OPERATION + '.result.json', identity=COMP_SHA256, expected=COMP_BYTES)
            mapping_raw = read(input_fd, 'inputs', COMP_OPERATION + '.mapping.json', identity=MAPPING_SHA256, expected=MAPPING_BYTES)
            _compression_proof(result_raw, mapping_raw, sources[BUNDLE], sources); report['all_72_processing_proof_verified'] = True
            targets = []
            for row in plan['targets']:
                raw = read(input_fd, 'inputs', row['name'], identity=row['sha256'], expected=row['bytes'])
                target = {**row, 'md5': hashlib.md5(raw, usedforsecurity=False).hexdigest()}; targets.append(target)
                report['local_verified'].append({'sha256': row['sha256'], 'bytes': row['bytes'], 'md5': target['md5']})
            for target in targets:
                request('object/properties', target, organization); report['properties_verified'].append(target['sha256'])
            if len(report['local_verified']) != 22 or len(report['properties_verified']) != 22: _fail()
            report['all_22_prechecks_verified'] = True
            for target in targets:
                request('object/delete', target, organization); report['deleted'].append(target['sha256'])
            report['status'] = 'COMPLETED'
        except (Exception, KeyboardInterrupt): report['failure'] = 'refused_or_unknown_no_retry'
        report.update(read_bytes=total, ended_utc=clock().isoformat()); guard(plan['git_head'])
        raw = e.canonical(report); _publish(operation_fd, OPERATION_ID + '.result.json', raw)
        return raw
    finally:
        for directory in (operation_fd, input_fd):
            if directory is not None: os.close(directory)


def run(**arguments):
    for module, name in ((e, 'extended_evidence.py'), (ops, 'extended_operations.py'), (compression, 'extended_compression.py'), (compression.storage, 'extended_compressed_store.py')):
        if Path(module.__file__) != LANE / (PREFIX + name): _fail()
    if Path(__file__) != LANE / (PREFIX + 'extended_cleanup.py'): _fail()
    head = _guard(); sources = _sources(head)
    plan = _plan(**arguments, source_hashes={name: _sha(raw) for name, raw in sources.items()}, git_head=head, bundle_raw=sources[BUNDLE])
    with _deadline():
        answer = _execute(plan, sources, PRIVATE_ROOT, INPUT_ROOT, clock=_now, guard=_guard, transport=_transport)
        if _sources(head) != sources: _fail()
        return answer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('operation-id', 'owner-instruction-sha256', 'created-utc', 'expires-utc'):
        parser.add_argument('--' + name, required=True)
    try:
        raw = run(**vars(parser.parse_args(argv))); print(raw.decode(), end='')
        return 0 if e.parse_json(raw)['status'] == 'COMPLETED' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end=''); return 1


if __name__ == '__main__': raise SystemExit(main())
