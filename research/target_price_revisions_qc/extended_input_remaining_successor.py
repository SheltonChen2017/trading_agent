"""Single-use remaining71 input continuation; no cloud candidate changes.

The successful first-key proof is reread under this newly claimed bounded scope.
Each of the exact remaining71 objects gets a new read/request proof, no old
claim is renewed, and only an actual successful new upload plus matching native
properties permits its missing completion receipt. Stop on the first refusal.
Full input/audit headroom, absence and native SHA256 are never inferred.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.client
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time

from . import extended_input_probe_successor as first

e, ops, probe, storage, census = first.e, first.ops, first.probe, first.storage, first.census
LANE, BRANCH, PRIVATE_ROOT, INPUT_ROOT = first.LANE, first.BRANCH, first.PRIVATE_ROOT, first.INPUT_ROOT
PREFIX, BUNDLE = first.PREFIX, first.BUNDLE
SOURCE_RELATIVE = PREFIX + 'extended_input_remaining_successor.py'
SOURCE_PATHS = (*first.SOURCE_PATHS, SOURCE_RELATIVE)
SOURCE_PINS = {**first.SOURCE_PINS, first.SOURCE_RELATIVE:
    '762be6e44b6fe56981919be704ea5961a81129c659626fd0cb1e4970eebb6e7c'}
FIRST_OPERATION = 'TPR-EXT26-INPUT-PROBE-20261011-001'
FIRST_PLAN_SHA256 = '1b287f316d762021b8ec7f0d5493b8675452cde755750867c24557e237eabff2'
FIRST_PROOF_SHA256 = '6c0be8ff6f6d1efe167d2b0f4372eabbde6d19b6d6fff74980ee1c5e4c5b8884'
FIRST_COMPLETION_SHA256 = 'aa6ba0ed4752e531db13f4bceb084e347f98badb2fb5f6efe1e94fd7634b79c6'
FIRST_RECEIPT_SHA256 = 'daf2d427623cd0fadc422d1430818b62e454304b6c12a927b197939168530533'
FIRST_RECEIPT_BYTES, FIRST_PROOF_BYTES = 6421, 1403
MAX_ROWS, TOTAL_ENCODED_BYTES, MAX_INPUT_FILE = 71, 21409650, 407066
MAX_RESPONSE, MAX_REQUESTS, MAX_SECONDS, MAX_METADATA_TOTAL = 1024 * 1024, 213, 1800, 2 * 1024 * 1024
ON, PROJECT_ID, ORGANIZATION_SHA256 = first.ON, first.PROJECT_ID, first.ORGANIZATION_SHA256
Refusal = e.EvidenceError
_sha, _clock, _guard, _open_directory, _publish = first._sha, first._clock, first._guard, first._open_directory, first._publish


def _fail(): raise Refusal('bounded remaining71 continuation refused; no automatic retry')
def _now(): return datetime.now(timezone.utc)


def _sources(head):
    values = {}
    for name in SOURCE_PATHS:
        _guard(head); directory = _open_directory((LANE / name).parent)
        try: raw = probe._read(directory, Path(name).name, maximum=first.MAX_METADATA, private=False)
        finally: os.close(directory)
        committed = subprocess.run(['git', 'show', head + ':' + name], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != committed: _fail()
        values[name] = raw
    if any(_sha(values[name]) != identity for name, identity in SOURCE_PINS.items()): _fail()
    _guard(head); return values


def _inventory(bundle_raw):
    target, row, mapping = first._first(bundle_raw)
    _, rows, digest = census._inventory(bundle_raw)
    remaining = [item for item in rows if item['gzip_sha256'] != row['gzip_sha256']]
    if (digest != mapping or len(remaining) != MAX_ROWS
            or sum(e._integer(item['gzip_bytes']) for item in remaining) != TOTAL_ENCODED_BYTES
            or any(e._integer(item['gzip_bytes']) > MAX_INPUT_FILE for item in remaining)): _fail()
    return target, row, remaining, mapping


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
          operation_id, bundle_raw, mode='production'):
    if (type(operation_id) is not str or re.fullmatch(r'TPR-EXT26-INPUT-REMAINING-[A-Za-z0-9-]{1,44}', operation_id) is None
            or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS)
            or mode not in {'production', 'offline-fixture'}): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    for identity in source_hashes.values(): e._hash(identity)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 86400: _fail()
    target, first_row, rows, mapping = _inventory(bundle_raw)
    return {'schema': 'tpr-ext26-input-remaining-successor-plan-v1', 'study_id': e.STUDY_ID,
        'operation_id': operation_id, 'git_head': git_head, 'source_hashes': source_hashes,
        'owner_instruction_sha256': owner_instruction_sha256, 'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'mode': mode, 'bundle_sha256': _sha(bundle_raw), 'first_target': target, 'first_input': first_row,
        'inputs': rows, 'mapping_sha256': mapping, 'first_operation_id': FIRST_OPERATION,
        'first_plan_sha256': FIRST_PLAN_SHA256, 'first_native_proof_sha256': FIRST_PROOF_SHA256,
        'first_completion_sha256': FIRST_COMPLETION_SHA256, 'first_receipt_sha256': FIRST_RECEIPT_SHA256,
        'first_receipt_bytes': FIRST_RECEIPT_BYTES, 'first_native_proof_bytes': FIRST_PROOF_BYTES,
        'first_completion_bytes': len(e.canonical(_completed(first_row, mapping))), 'project_id': PROJECT_ID,
        'organization_sha256': ORGANIZATION_SHA256, 'max_input_rows': MAX_ROWS, 'max_input_bytes': TOTAL_ENCODED_BYTES,
        'max_input_file_bytes': MAX_INPUT_FILE, 'max_response_bytes': MAX_RESPONSE, 'max_requests': MAX_REQUESTS,
        'max_metadata_bytes': MAX_METADATA_TOTAL, 'max_seconds': MAX_SECONDS,
        'old_claims_renewed': False, 'full_capacity_proved': False, 'native_absence_attested': False,
        'stop_first_failure': True, 'new_looks': 0, 'quantconnect_attempts': 0, 'canonical_admission': False, 'trading': False}


def _completed(row, mapping):
    return {'schema': 'tpr-ext26-gzip-upload-v1', 'mapping_sha256': mapping,
        **{key: row[key] for key in ('plain_sha256', 'plain_bytes', 'logical_key', 'gzip_sha256', 'gzip_bytes', 'stored_key')}}


def _validate_first(receipt_raw, proof_raw, completion_raw, plan, sources, now):
    if (_sha(proof_raw) != plan['first_native_proof_sha256'] or _sha(completion_raw) != plan['first_completion_sha256']
            or _sha(receipt_raw) != plan['first_receipt_sha256'] or len(receipt_raw) != plan['first_receipt_bytes']
            or len(proof_raw) != plan['first_native_proof_bytes'] or len(completion_raw) != plan['first_completion_bytes']
            or completion_raw != e.canonical(_completed(plan['first_input'], plan['mapping_sha256']))): _fail()
    receipt = e.parse_json(receipt_raw)
    if (receipt.get('schema') != 'tpr-ext26-input-probe-successor-receipt-v1'
            or receipt.get('status') != 'COMPLETED_FIRST_KEY_UPLOAD' or receipt.get('scope_spent') is not True
            or receipt.get('operation_id') != plan['first_operation_id'] or receipt.get('plan_sha256') != plan['first_plan_sha256']
            or receipt.get('native_hash_proof_sha256') != plan['first_native_proof_sha256']
            or receipt.get('global_completion_sha256') != plan['first_completion_sha256']
            or receipt.get('object_set_succeeded') is not True or receipt.get('global_completion_created') is not True
            or receipt.get('native_md5_matched') is not True or receipt.get('local_gzip_and_plaintext_sha256_verified') is not True
            or receipt.get('mapping_sha256') != plan['mapping_sha256']
            or receipt.get('target_gzip_sha256') != plan['first_input']['gzip_sha256']
            or type(receipt.get('source_hashes')) is not dict or set(receipt['source_hashes']) != set(first.SOURCE_PATHS)
            or any(receipt['source_hashes'][name] != _sha(sources[name]) for name in first.SOURCE_PATHS)):
        _fail()
    if not _clock(receipt.get('ended_utc')) <= now < _clock(receipt['ended_utc']) + probe.timedelta(hours=24): _fail()
    proof = e.parse_json(proof_raw)
    if (proof.get('schema') != 'tpr-ext26-input-native-hash-proof-v1' or proof.get('operation_id') != plan['first_operation_id']
            or proof.get('plan_sha256') != plan['first_plan_sha256']
            or proof.get('target_gzip_sha256') != plan['first_input']['gzip_sha256']
            or proof.get('target_key_sha256') != _sha(plan['first_input']['stored_key'].encode())
            or proof.get('local_encoded_sha256') != plan['first_input']['gzip_sha256']
            or e._integer(proof.get('native_bytes')) != e._integer(plan['first_input']['gzip_bytes'])
            or proof.get('object_set_succeeded') is not True or proof.get('native_md5_matched') is not True
            or proof.get('native_md5') != proof.get('local_encoded_md5')
            or type(proof.get('native_md5')) is not str or re.fullmatch(r'[a-f0-9]{32}', proof['native_md5']) is None
            or proof.get('old_claims_renewed') is not False or proof.get('native_content_sha256_verified') is not False): _fail()
    return receipt, proof


def _transport(endpoint, raw, content_type):
    if endpoint not in {'object/properties', 'object/set'} or type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT_FILE + 8192: _fail()
    connection = None
    with probe._request_deadline():
        user, token = ops.credential(); stamp = str(int(time.time()))
        signed = hashlib.sha256((token + ':' + stamp).encode()).hexdigest()
        authorization = base64.b64encode((user + ':' + signed).encode()).decode()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); context.keylog_filename = None
        context.check_hostname, context.verify_mode = True, ssl.CERT_REQUIRED; context.load_default_certs()
        try:
            connection = http.client.HTTPSConnection('www.quantconnect.com', timeout=30, context=context)
            connection.request('POST', '/api/v2/' + endpoint, body=raw,
                headers={'Authorization': 'Basic ' + authorization, 'Timestamp': stamp, 'Content-Type': content_type})
            response = connection.getresponse(); wire = response.read(MAX_RESPONSE + 1)
            if not 0 < len(wire) <= MAX_RESPONSE or token.encode() in wire: _fail()
            return wire, response.status
        finally:
            if connection is not None: connection.close()


def _execute(plan, sources, path, input_path, *, clock, guard, transport):
    arguments = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256',
        'created_utc', 'expires_utc', 'operation_id', 'mode')}
    if e.canonical(plan) != e.canonical(_plan(**arguments, bundle_raw=sources[BUNDLE])): _fail()
    if (plan['mode'] == 'production' and (path != PRIVATE_ROOT or input_path != INPUT_ROOT)
            or plan['mode'] == 'offline-fixture' and (path.is_relative_to(LANE) or input_path.is_relative_to(LANE))): _fail()
    started, directory, inputs = time.monotonic(), None, None
    def check():
        guard(plan['git_head']); now = clock()
        if (type(now) is not datetime or now.utcoffset() != probe.timedelta(0)
                or not _clock(plan['created_utc']) <= now < _clock(plan['expires_utc'])
                or time.monotonic() - started >= MAX_SECONDS
                or {name: _sha(value) for name, value in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = _open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        operation, plan_hash = plan['operation_id'], _sha(e.canonical(plan))
        _publish(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-input-remaining-successor-receipt-v1', 'study_id': e.STUDY_ID,
            'operation_id': operation, 'plan_sha256': plan_hash, 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
            'owner_instruction_sha256': plan['owner_instruction_sha256'], 'first_operation_id': plan['first_operation_id'],
            'first_native_proof_sha256': plan['first_native_proof_sha256'], 'first_completion_sha256': plan['first_completion_sha256'],
            'first_receipt_sha256': plan['first_receipt_sha256'],
            'mapping_sha256': plan['mapping_sha256'], 'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True,
            'first_proof_verified': False, 'metadata_read_bytes': 0, 'input_read_bytes': 0, 'read_attempts': 0,
            'failed_read_body_bytes_unknown': False,
            'read_bytes_semantics': 'retained custody-verified bytes; unsuccessful-read body bytes may be unknown',
            'read_inventory': {}, 'requests': [], 'inputs': [], 'completed_count': 0, 'failed_count': 0,
            'unattempted_count': MAX_ROWS, 'encoded_bytes_expected': TOTAL_ENCODED_BYTES,
            'old_claims_renewed': False, 'full_capacity_proved': False, 'native_absence_attested': False,
            'native_content_sha256_verified': False, 'input_rows_exposed': False, 'automatic_retry': False,
            'new_looks': 0, 'quantconnect_attempts': 0, 'canonical_admission': False, 'trading': False}
        def read(role, name, *, optional=False, maximum=first.MAX_METADATA, expected_size=None):
            check(); _publish(directory, operation + '.read.' + role + '.spent.json', e.canonical({
                'at': clock().isoformat(), 'plan_sha256': plan_hash, 'name': name, 'optional': optional,
                'maximum_bytes': maximum, 'expected_bytes': expected_size}))
            remaining = MAX_METADATA_TOTAL - report['metadata_read_bytes']
            if remaining <= 0: _fail()
            report['read_attempts'] += 1; report['failed_read_body_bytes_unknown'] = True
            raw = first._read_exact(directory, name, maximum=min(maximum, remaining), optional=optional, expected_size=expected_size)
            report['failed_read_body_bytes_unknown'] = False
            if raw is not None:
                report['metadata_read_bytes'] += len(raw); report['read_inventory'][role] = {'sha256': _sha(raw), 'bytes': len(raw)}
            return raw
        def request(row, endpoint, payload, content_type='application/json'):
            number = len(report['requests']) + 1
            if number > MAX_REQUESTS: _fail()
            check(); name = operation + '.request.' + str(number)
            _publish(directory, name + '.spent.json', e.canonical({'at': clock().isoformat(), 'plan_sha256': plan_hash,
                'endpoint': endpoint, 'payload_sha256': _sha(payload), 'gzip_sha256': row['gzip_sha256'],
                'new_looks': 0, 'quantconnect_attempts': 0}))
            observed = {'number': number, 'endpoint': endpoint, 'gzip_sha256': row['gzip_sha256'],
                'status': 'FAILED_OR_UNCERTAIN', 'safe_response': None}
            report['requests'].append(observed)
            try:
                raw, status = transport(endpoint, payload, content_type); check()
                if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE: _fail()
                if endpoint == 'object/properties':
                    target = {'key': row['stored_key'], 'gzip_bytes': e._integer(row['gzip_bytes'])}
                    safe = probe._response(raw, endpoint, target, {row['stored_key']}, http_status=status)
                else:
                    body = e.parse_json(raw)
                    if type(body) is not dict or type(body.get('success')) is not bool: _fail()
                    safe = {'http_status': status, 'native_success': body['success'], 'original_wire_sha256': _sha(raw),
                        'original_wire_bytes': len(raw), 'error_classification': probe.old._errors(body)}
                    safe['classification'] = ('native_object_set_succeeded' if status == 200 and body['success'] is True
                        and ('errors' not in body or body['errors'] == []) else 'native_object_set_refused_or_unknown')
                observed.update(status='OBSERVED', safe_response=safe); return safe
            finally: _publish(directory, name + '.terminal.json', e.canonical(observed))
        try:
            receipt_raw = read('first-receipt', plan['first_operation_id'] + '.result.json',
                maximum=65536, expected_size=plan['first_receipt_bytes'])
            proof = read('first-proof', plan['first_operation_id'] + '.native-hash-proof.json',
                maximum=65536, expected_size=plan['first_native_proof_bytes'])
            completion_name = 'compressed-input.' + plan['first_input']['gzip_sha256'] + '.completed.json'
            completed = read('first-completion', completion_name, maximum=65536, expected_size=plan['first_completion_bytes'])
            first_receipt, first_proof = _validate_first(receipt_raw, proof, completed, plan, sources, clock())
            report['first_proof_verified'] = True
            project_binding = first_receipt['read_inventory']['project']
            project = read('project', ON + '.project.json', maximum=probe.MAX_PROJECT,
                expected_size=e._integer(project_binding['bytes']))
            if _sha(project) != project_binding['sha256']: _fail()
            organization = probe._project(project, plan['first_target'])
            inputs = _open_directory(input_path); input_info = os.fstat(inputs)
            if input_info.st_uid != os.getuid() or stat.S_IMODE(input_info.st_mode) != 0o700: _fail()
            for index, row in enumerate(plan['inputs']):
                report['unattempted_count'] -= 1
                outcome = {'index': index, 'gzip_sha256': row['gzip_sha256'], 'status': 'FAILED_OR_UNCERTAIN',
                    'object_set_succeeded': False, 'global_completion_created': False, 'native_hash_proof_sha256': None}
                report['inputs'].append(outcome)
                prefix = 'compressed-input.' + row['gzip_sha256']; role = 'item-' + str(index)
                for suffix in ('.completed.json', '.read.spent.json', '.upload.spent.json', '.upload.transport.json'):
                    if read(role + '-' + suffix.strip('.').replace('.', '-'), prefix + suffix, optional=True, maximum=65536) is not None: _fail()
                check(); _publish(directory, operation + '.' + role + '.input-read.spent.json', e.canonical({
                    'at': clock().isoformat(), 'plan_sha256': plan_hash, 'name': row['stored_name'],
                    'expected_bytes': e._integer(row['gzip_bytes']), 'sha256': row['gzip_sha256']}))
                size = e._integer(row['gzip_bytes'])
                if report['input_read_bytes'] + size > TOTAL_ENCODED_BYTES: _fail()
                report['read_attempts'] += 1; report['failed_read_body_bytes_unknown'] = True
                encoded = first._read_exact(inputs, row['stored_name'], maximum=MAX_INPUT_FILE, expected_size=size)
                report['failed_read_body_bytes_unknown'] = False; report['input_read_bytes'] += len(encoded)
                storage.decode_gzip(encoded, plain_bytes=e._integer(row['plain_bytes']), plain_sha256=row['plain_sha256'],
                    gzip_bytes=size, gzip_sha256=row['gzip_sha256'])
                md5 = hashlib.md5(encoded).hexdigest()
                payload = e.canonical({'organizationId': organization, 'key': row['stored_key']})
                before = request(row, 'object/properties', payload)
                if (before.get('http_status') != 200 or before.get('native_success') is not False
                        or before.get('error_classification', {}).get('classes') != ['not_found']): _fail()
                wire, content_type = first._multipart(organization, row, encoded)
                written = request(row, 'object/set', wire, content_type)
                if written.get('classification') != 'native_object_set_succeeded': _fail()
                outcome['object_set_succeeded'] = True
                after = request(row, 'object/properties', payload)
                if (after.get('classification') != 'exact_own_key_metadata_observed' or after.get('native_success') is not True
                        or after.get('size_matches') is not True or after.get('remote_md5') != md5): _fail()
                proof_value = {'schema': 'tpr-ext26-remaining-input-native-hash-proof-v1', 'operation_id': operation,
                    'plan_sha256': plan_hash, 'first_native_proof_sha256': plan['first_native_proof_sha256'],
                    'gzip_sha256': row['gzip_sha256'], 'plain_sha256': row['plain_sha256'],
                    'target_key_sha256': _sha(row['stored_key'].encode()), 'native_bytes': size, 'local_encoded_md5': md5,
                    'native_md5': after['remote_md5'], 'native_property_wire_sha256': after['original_wire_sha256'],
                    'native_object_set_wire_sha256': written['original_wire_sha256'], 'object_set_succeeded': True,
                    'native_md5_matched': True, 'native_content_sha256_verified': False,
                    'old_claims_renewed': False, 'new_looks': 0, 'quantconnect_attempts': 0, 'canonical_admission': False}
                check(); proof_raw = e.canonical(proof_value)
                _publish(directory, operation + '.' + role + '.native-hash-proof.json', proof_raw)
                completion_raw = e.canonical(_completed(row, plan['mapping_sha256']))
                _publish(directory, prefix + '.completed.json', completion_raw)
                outcome.update(status='COMPLETED', global_completion_created=True,
                    native_hash_proof_sha256=_sha(proof_raw), global_completion_sha256=_sha(completion_raw))
                report['completed_count'] += 1
            if report['completed_count'] != MAX_ROWS or report['input_read_bytes'] != TOTAL_ENCODED_BYTES: _fail()
            check(); report['status'] = 'COMPLETED_REMAINING71'
        except (Exception, KeyboardInterrupt):
            report['failure'] = 'refused_or_uncertain_stop_first_failure'
            report['failed_count'] = 1 if report['inputs'] and report['inputs'][-1]['status'] != 'COMPLETED' else 0
        report['ended_utc'] = clock().isoformat(); guard(plan['git_head'])
        raw = e.canonical(report); _publish(directory, operation + '.result.json', raw); return raw
    finally:
        if inputs is not None: os.close(inputs)
        if directory is not None: os.close(directory)


def run(**arguments):
    if Path(__file__) != LANE / SOURCE_RELATIVE: _fail()
    for module, name in ((first, 'extended_input_probe_successor.py'), (probe, 'extended_store_probe.py'),
            (storage, 'extended_compressed_store.py'), (e, 'extended_evidence.py'), (ops, 'extended_operations.py'),
            (census, 'extended_compressed_upload_diagnostic.py'), (probe.old, 'extended_upload_diagnostic.py')):
        if Path(module.__file__) != LANE / (PREFIX + name): _fail()
    head = _guard(); sources = _sources(head)
    plan = _plan(**arguments, source_hashes={name: _sha(raw) for name, raw in sources.items()},
        git_head=head, bundle_raw=sources[BUNDLE])
    # Nested request deadlines reuse the probe's handler; this outer scope has
    # its separately frozen1800s bound, not the executed first helper's120s.
    with ops.wall_deadline(MAX_SECONDS):
        raw = _execute(plan, sources, PRIVATE_ROOT, INPUT_ROOT, clock=_now, guard=_guard, transport=_transport)
        if _sources(head) != sources: _fail()
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('operation-id', 'owner-instruction-sha256', 'created-utc', 'expires-utc'):
        parser.add_argument('--' + name, required=True)
    try:
        raw = run(**vars(parser.parse_args(argv))); print(raw.decode(), end='')
        return 0 if e.parse_json(raw)['status'] == 'COMPLETED_REMAINING71' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end=''); return 1


if __name__ == '__main__': raise SystemExit(main())
