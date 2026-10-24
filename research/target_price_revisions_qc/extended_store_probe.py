"""Single-use, two-request metadata probe of the frozen owned EXT26 input store.

Only the exact owned directory list and first failed gzip key's properties are
queried. No input bodies, object exports, mutations, retries, unrelated projects
or organization-root listing exist. Native usage has unspecified semantics:
neither capacity/free bytes, entitlement nor shared-lane contention is inferred.
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

from . import extended_evidence as e, extended_operations as ops
from . import extended_upload_diagnostic as old, extended_compressed_upload_diagnostic as census

LANE, BRANCH, PRIVATE_ROOT = ops.LANE, ops.BRANCH, ops.PRIVATE_ROOT
PREFIX = 'research/target_price_revisions_qc/'
ON, PROJECT_ID = census.ON, 37650453
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
BUNDLE, BUNDLE_SHA256 = census.BUNDLE, census.BUNDLE_SHA256
FIRST_GZIP_SHA256 = '8ed811d89c484c006447654f6257c46f285eef8f697f0cc4d94d60a8c0e40042'
FIRST_GZIP_BYTES = 346371
MAX_FILE, MAX_RESPONSE, MAX_PROJECT, MAX_SECONDS, MAX_REQUESTS = 1024 * 1024, 1024 * 1024, 8192, 120, 2
ENDPOINTS = frozenset({'object/list', 'object/properties'})
SOURCE_PATHS = tuple(census.INITIALIZERS) + tuple(PREFIX + name for name in (
    'extended_store_probe.py', 'extended_evidence.py', 'extended_operations.py',
    'extended_upload_diagnostic.py', 'extended_compressed_upload_diagnostic.py')) + (BUNDLE,)
SOURCE_PINS = {**census.INITIALIZERS, BUNDLE: BUNDLE_SHA256,
    PREFIX + 'extended_operations.py': '824b3f0c180f1aeb7038d8f280c44507b5c39687fcccc87c539f242d9256d167',
    PREFIX + 'extended_evidence.py': 'a816b1ddca5a8428f07e9029bc3a7f7db3c5e1a1f50521664992dabf556aa2d7',
    PREFIX + 'extended_upload_diagnostic.py': '9bb026bc7caf45762f84e68725f3db9768ad3d703d03549764899afc68be5b2c',
    PREFIX + 'extended_compressed_upload_diagnostic.py': 'eb9c0844d321633b035e9bb56378ea296b7e7222a2c2b054d0d599caecee0a32'}
Refusal = e.EvidenceError
_sha, _clock, _guard, _open_directory, _publish = old._sha, old._clock, old._guard, old._open_directory, old._publish


def _fail(): raise Refusal('owned store metadata probe refused or uncertain; no automatic retry')
def _now(): return datetime.now(timezone.utc)


def _read(directory, name, *, maximum=MAX_FILE, private=True):
    ops._name(name); fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if (type(maximum) is not int or not 0 < maximum <= MAX_FILE or not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1 or not (1 if private else 0) <= before.st_size <= maximum
                or private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600)): _fail()
        pieces, remaining = [], before.st_size
        while remaining:
            raw = os.read(fd, min(65536, remaining))
            if not raw: _fail()
            pieces.append(raw); remaining -= len(raw)
        after, named = os.fstat(fd), os.stat(name, dir_fd=directory, follow_symlinks=False)
        if any(getattr(before, field) != getattr(value, field) for value in (after, named) for field in
            ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')): _fail()
        return b''.join(pieces)
    finally:
        if fd is not None: os.close(fd)


def _sources(head):
    sources = {}
    for name in SOURCE_PATHS:
        _guard(head); directory = _open_directory((LANE / name).parent)
        try: raw = _read(directory, Path(name).name, private=False)
        finally: os.close(directory)
        committed = subprocess.run(['git', 'show', head + ':' + name], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != committed: _fail()
        sources[name] = raw
    if any(_sha(sources[name]) != identity for name, identity in SOURCE_PINS.items()): _fail()
    _guard(head); return sources


def _targets(bundle_raw):
    bundle, rows, mapping_sha256 = census._inventory(bundle_raw)
    first = [row for row in rows if row['gzip_sha256'] == FIRST_GZIP_SHA256]
    if len(first) != 1 or e._integer(first[0]['gzip_bytes']) != FIRST_GZIP_BYTES: _fail()
    directory = first[0]['stored_key'].rsplit('/', 1)[0] + '/'
    expected = 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + e._hash(bundle['preparation_sha256']) + '/'
    if directory != expected or any(not row['stored_key'].startswith(directory) for row in rows): _fail()
    candidates = [row for row in bundle['candidates'] if row.get('candidate_id') == ON]
    if len(candidates) != 1 or type(candidates[0].get('project_name')) is not str: _fail()
    allowed = {row['stored_key'] for row in rows} | {row['logical_key'] for row in rows}
    return {'directory': directory, 'key': first[0]['stored_key'], 'gzip_bytes': FIRST_GZIP_BYTES,
        'gzip_sha256': FIRST_GZIP_SHA256, 'mapping_sha256': mapping_sha256,
        'preparation_sha256': bundle['preparation_sha256'], 'project_name': candidates[0]['project_name']}, allowed


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
          operation_id, bundle_raw, mode='production'):
    if (type(operation_id) is not str or re.fullmatch(r'TPR-EXT26-STORE-PROBE-[A-Za-z0-9-]{1,48}', operation_id) is None
            or mode not in {'production', 'offline-fixture'} or type(source_hashes) is not dict
            or set(source_hashes) != set(SOURCE_PATHS)): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    for value in source_hashes.values(): e._hash(value)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 14400: _fail()
    targets, _ = _targets(bundle_raw)
    return {'schema': 'tpr-ext26-store-probe-plan-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'operation_id': operation_id, 'owner_instruction_sha256': owner_instruction_sha256,
        'source_hashes': source_hashes, 'git_head': git_head, 'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'mode': mode, 'bundle_sha256': _sha(bundle_raw), 'candidate_id': ON, 'project_id': PROJECT_ID,
        'organization_sha256': ORGANIZATION_SHA256, 'targets': targets, 'max_requests': MAX_REQUESTS,
        'max_project_bytes': MAX_PROJECT, 'max_response_bytes': MAX_RESPONSE, 'max_seconds': MAX_SECONDS,
        'failed_origin': {'qc_operation_id': census.QC_OPERATION, 'request_number': 61,
            'manifest_sha256': census.MANIFEST_SHA256, 'original_wire_sha256': '703d44310debd517fb8afc78163621f194d034ee158238e03c3712ea204a5db1',
            'projection_sha256': 'a10f0528cc70c9ea92fae107bf3d7c154a0439129258518f77bb529f9e74a450'},
        'input_body_reads': False, 'unrelated_projects': False, 'organization_root_listing': False,
        'mutations': False, 'automatic_retry': False, 'old_claims_renewed': False, 'new_looks': 0, 'quantconnect_attempts': 0}


def _project(raw, target):
    body = e.parse_json(raw)
    if (type(body) is not dict or body.get('candidate_id') != ON or e._integer(body.get('project_id')) != PROJECT_ID
            or body.get('name') != target['project_name'] or body.get('owner') is not True): _fail()
    organization = e._id(body.get('organization_id'))
    if _sha(organization.encode('utf-8')) != ORGANIZATION_SHA256: _fail()
    return organization


def _nonnegative(value, maximum=2**63 - 1):
    """Native metadata counts admit exact zero, not money's positive-only rule."""
    if (type(maximum) is not int or not 0 <= maximum <= 2**63 - 1 or type(value) is not e.JsonNumber
            or re.fullmatch(r'0|[1-9][0-9]{0,18}', value.lexeme) is None): _fail()
    amount = int(value.lexeme)
    if amount > maximum: _fail()
    return amount


def _number(body, field, *, maximum=2**63 - 1):
    return None if field not in body else _nonnegative(body[field], maximum)


def _not_found_message(value, depth=0):
    """A closed message category, never an attested absence or retry authority."""
    if depth > 16: _fail()
    if type(value) is str:
        return re.search(r'\b(not found|does not exist|no such)\b', value.lower()) is not None
    if type(value) is list:
        if len(value) > 4096: _fail()
        return any(_not_found_message(item, depth + 1) for item in value)
    if type(value) is dict:
        return any(_not_found_message(value[name], depth + 1) for name in ('errors', 'error', 'message') if name in value)
    return False


def _response(raw, endpoint, target, allowed, *, http_status):
    if endpoint not in ENDPOINTS or type(http_status) is not int or not 100 <= http_status <= 599: _fail()
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE: _fail()
    body = e.parse_json(raw)
    if type(body) is not dict or type(body.get('success')) is not bool: _fail()
    errors = old._errors(body)
    if _not_found_message(body):
        errors['classes'] = sorted(set(errors['classes']) | {'not_found'})
        errors['unknown_classification'] = False
    answer = {'http_status': http_status, 'native_success': body['success'], 'error_classification': errors,
        'original_wire_sha256': _sha(raw), 'original_wire_bytes': len(raw), 'capacity_bytes': None, 'free_bytes': None,
        'capacity_sufficient': None, 'other_lane_contention': None, 'provider_attestation': False}
    if http_status != 200 or body['success'] is not True:
        answer.update(classification='native_refusal_or_unknown', object_existence='unknown', remote_content_verified=False)
        return answer
    if 'errors' in body and (type(body['errors']) is not list or body['errors']): _fail()
    if endpoint == 'object/list':
        if type(body.get('path')) is not str or body['path'].rstrip('/') + '/' != target['directory']: _fail()
        objects = body.get('objects')
        if type(objects) is not list or len(objects) > 144: _fail()
        seen, gzip_count, original_count, folders = set(), 0, 0, 0
        for row in objects:
            if type(row) is not dict or type(row.get('key')) is not str or type(row.get('folder')) is not bool: _fail()
            key = row['key']
            if key in seen: _fail()
            seen.add(key)
            if row['folder'] is True:
                if key.rstrip('/') + '/' != target['directory']: _fail()
                folders += 1; continue
            if key not in allowed: _fail()
            _nonnegative(row.get('size'))
            if key.rsplit('/', 1)[1].startswith('gzip.'): gzip_count += 1
            else: original_count += 1
        page, pages = _number(body, 'page', maximum=10000), _number(body, 'totalPages', maximum=10000)
        if pages is not None and page is not None and page > max(1, pages): _fail()
        answer.update(classification='own_directory_metadata_observed', reported_object_storage_used=_number(body, 'objectStorageUsed'),
            usage_semantics='native_field_unspecified_not_free_or_limit', reported_page=page, reported_total_pages=pages,
            pagination_followed=False, directory_census_complete=False,
            pagination_semantics='native_page_index_semantics_unverified_no_complete_census',
            own_gzip_objects_on_page=gzip_count, own_plain_objects_on_page=original_count, own_folders_on_page=folders,
            row_names_or_keys_returned=False, remote_content_verified=False)
    else:
        metadata = body.get('metadata')
        if type(metadata) is not dict or metadata.get('key') != target['key']: _fail()
        size = _nonnegative(metadata.get('size'))
        md5 = metadata.get('md5')
        if type(md5) is not str or re.fullmatch(r'[a-fA-F0-9]{32}', md5) is None: _fail()
        answer.update(classification='exact_own_key_metadata_observed', object_existence='present_metadata',
            remote_bytes=size, expected_bytes=target['gzip_bytes'], size_matches=size == target['gzip_bytes'],
            remote_md5=md5.lower(), expected_md5=None, md5_matches=None, remote_content_verified=False)
    return answer


def _transport(endpoint, raw):
    if endpoint not in ENDPOINTS or type(raw) is not bytes or not 0 < len(raw) <= MAX_PROJECT: _fail()
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
            if not 0 < len(wire) <= MAX_RESPONSE or token.encode() in wire: _fail()
            return wire, response.status
        finally:
            if connection is not None: connection.close()


@contextmanager
def _request_deadline():
    if threading.current_thread() is not threading.main_thread(): _fail()
    remaining, interval = signal.getitimer(signal.ITIMER_REAL)
    if interval != 0.0: _fail()
    previous, started = signal.getsignal(signal.SIGALRM), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: _fail()); signal.setitimer(signal.ITIMER_REAL, min(30, remaining) if remaining else 30)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        if remaining: signal.setitimer(signal.ITIMER_REAL, max(0.000001, remaining - (time.monotonic() - started)))


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0): _fail()
    previous = signal.getsignal(signal.SIGALRM); signal.signal(signal.SIGALRM, lambda *_: _fail()); signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
    try: yield
    finally: signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def _execute(plan, sources, path, *, clock, guard, transport):
    arguments = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc', 'operation_id', 'mode')}
    expected = _plan(**arguments, bundle_raw=sources[BUNDLE])
    if e.canonical(plan) != e.canonical(expected): _fail()
    if plan['mode'] == 'production' and path != PRIVATE_ROOT or plan['mode'] == 'offline-fixture' and path.is_relative_to(LANE): _fail()
    started, directory = time.monotonic(), None
    def check():
        guard(plan['git_head']); now = clock()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0) or not _clock(plan['created_utc']) <= now < _clock(plan['expires_utc'])
                or time.monotonic() - started >= MAX_SECONDS or {name: _sha(raw) for name, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = _open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        operation = plan['operation_id']; plan_hash = _sha(e.canonical(plan))
        _publish(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-store-probe-receipt-v1', 'study_id': e.STUDY_ID, 'operation_id': operation,
            'plan_sha256': plan_hash, 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
            'owner_instruction_sha256': plan['owner_instruction_sha256'], 'bundle_sha256': plan['bundle_sha256'],
            'project_id': PROJECT_ID, 'organization_sha256': ORGANIZATION_SHA256,
            'target_directory_sha256': _sha(plan['targets']['directory'].encode()),
            'target_key_sha256': _sha(plan['targets']['key'].encode()),
            'target_gzip_sha256': plan['targets']['gzip_sha256'], 'target_gzip_bytes': plan['targets']['gzip_bytes'],
            'mapping_sha256': plan['targets']['mapping_sha256'], 'preparation_sha256': plan['targets']['preparation_sha256'],
            'failed_origin_preserved': plan['failed_origin'], 'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True,
            'project_receipt_sha256': None, 'project_receipt_bytes': None,
            'requests': [], 'failure': None, 'capacity_bytes': None, 'free_bytes': None,
            'capacity_sufficient': None, 'other_lane_contention': None, 'new_looks': 0, 'quantconnect_attempts': 0,
            'input_body_reads': False, 'mutations': False, 'automatic_retry': False, 'old_claims_renewed': False}
        try:
            check(); name = ON + '.project.json'
            project_raw = _read(directory, name, maximum=MAX_PROJECT)
            report['project_receipt_sha256'], report['project_receipt_bytes'] = _sha(project_raw), len(project_raw)
            organization = _project(project_raw, plan['targets']); _, allowed = _targets(sources[BUNDLE]); check()
            for number, endpoint, field, value in ((1, 'object/list', 'path', plan['targets']['directory']),
                    (2, 'object/properties', 'key', plan['targets']['key'])):
                if number > MAX_REQUESTS: _fail()
                check(); payload = e.canonical({'organizationId': organization, field: value})
                request_name = operation + '.request.' + str(number)
                _publish(directory, request_name + '.spent.json', e.canonical({'at': clock().isoformat(), 'plan_sha256': plan_hash,
                    'endpoint': endpoint, 'payload_sha256': _sha(payload), 'new_looks': 0, 'quantconnect_attempts': 0}))
                observation = {'endpoint': endpoint, 'number': number, 'status': 'FAILED_OR_UNCERTAIN', 'safe_response': None}
                report['requests'].append(observation)
                try:
                    check(); raw, status = transport(endpoint, payload)
                    check(); safe = _response(raw, endpoint, plan['targets'], allowed, http_status=status)
                    observation.update(status='OBSERVED', safe_response=safe)
                finally: _publish(directory, request_name + '.terminal.json', e.canonical(observation))
            check(); report['status'] = 'COMPLETED'
        except (Exception, KeyboardInterrupt): report['failure'] = 'refused_or_uncertain_no_retry'
        report['ended_utc'] = clock().isoformat(); guard(plan['git_head'])
        raw = e.canonical(report); _publish(directory, operation + '.result.json', raw); return raw
    finally:
        if directory is not None: os.close(directory)


def run(**arguments):
    for module, name in ((e, 'extended_evidence.py'), (ops, 'extended_operations.py'),
            (old, 'extended_upload_diagnostic.py'), (census, 'extended_compressed_upload_diagnostic.py')):
        if Path(module.__file__) != LANE / (PREFIX + name): _fail()
    if Path(__file__) != LANE / (PREFIX + 'extended_store_probe.py'): _fail()
    head = _guard(); sources = _sources(head)
    plan = _plan(**arguments, source_hashes={name: _sha(raw) for name, raw in sources.items()}, git_head=head, bundle_raw=sources[BUNDLE])
    with _deadline():
        raw = _execute(plan, sources, PRIVATE_ROOT, clock=_now, guard=_guard, transport=_transport)
        if _sources(head) != sources: _fail()
        return raw


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
