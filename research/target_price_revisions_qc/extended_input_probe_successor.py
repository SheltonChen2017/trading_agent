"""Explicit one-key storage diagnostic after newly authorized continuation.

This does not renew operation003's failed claims or infer absence/free capacity.
Only the exact first content-addressed owned gzip key may be written, once, after
a fresh not-found observation. Existing matching metadata is observed without
overwriting or inventing upload success. All previous failed proofs are retained.
No launches, candidate renaming, source/config change, data export or deletion.
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

from . import extended_store_probe as probe, extended_compressed_store as storage

e, ops, census = probe.e, probe.ops, probe.census
LANE, BRANCH, PRIVATE_ROOT, INPUT_ROOT = probe.LANE, probe.BRANCH, probe.PRIVATE_ROOT, ops.INPUT_ROOT
PREFIX, BUNDLE = probe.PREFIX, probe.BUNDLE
SOURCE_RELATIVE = PREFIX + 'extended_input_probe_successor.py'
SOURCE_PATHS = (*probe.SOURCE_PATHS, PREFIX + 'extended_compressed_store.py', SOURCE_RELATIVE)
SOURCE_PINS = {**probe.SOURCE_PINS,
    PREFIX + 'extended_store_probe.py': 'ac3aae6811c8cc8f05c479381a8316e896f4a8e3f06e7f7dcde7a06257cc5cf1',
    PREFIX + 'extended_compressed_store.py': 'd661b5752c35b9dd04f783f5d78850f453d5f5f299874e5cf19700599df2356e'}
PROBE_OPERATION = 'TPR-EXT26-STORE-PROBE-20261011-002'
PROBE_RECEIPT_SHA256 = '441d9fd3833ff3dd3b7417761469a59c179049b40d6ea8ca6c8c74817ef9c2b9'
PROBE_RECEIPT_BYTES = 4667
ORIGIN_WIRE_SHA256 = '703d44310debd517fb8afc78163621f194d034ee158238e03c3712ea204a5db1'
ORIGIN_PROJECTION_SHA256 = 'a10f0528cc70c9ea92fae107bf3d7c154a0439129258518f77bb529f9e74a450'
MAX_METADATA, MAX_TOTAL_METADATA = 1024 * 1024, 2 * 1024 * 1024
MAX_INPUT_BYTES, MAX_RESPONSE, MAX_REQUESTS, MAX_SECONDS = 346371, probe.MAX_RESPONSE, 3, 120
ON, PROJECT_ID, ORGANIZATION_SHA256 = probe.ON, probe.PROJECT_ID, probe.ORGANIZATION_SHA256
Refusal = e.EvidenceError
_sha, _clock, _guard, _open_directory, _publish = probe._sha, probe._clock, probe._guard, probe._open_directory, probe._publish


def _fail(): raise Refusal('explicit one-key input diagnostic refused; no automatic retry')
def _now(): return datetime.now(timezone.utc)


def _sources(head):
    values = {}
    for name in SOURCE_PATHS:
        _guard(head); directory = _open_directory((LANE / name).parent)
        try: raw = probe._read(directory, Path(name).name, maximum=MAX_METADATA, private=False)
        finally: os.close(directory)
        committed = subprocess.run(['git', 'show', head + ':' + name], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != committed: _fail()
        values[name] = raw
    if any(_sha(values[name]) != identity for name, identity in SOURCE_PINS.items()): _fail()
    _guard(head); return values


def _first(bundle_raw):
    target, _ = probe._targets(bundle_raw)
    _, rows, mapping_hash = census._inventory(bundle_raw)
    matches = [row for row in rows if row['gzip_sha256'] == target['gzip_sha256']]
    if len(matches) != 1 or e._integer(matches[0]['gzip_bytes']) > MAX_INPUT_BYTES: _fail()
    return target, matches[0], mapping_hash


def _origin():
    return {'qc_operation_id': census.QC_OPERATION, 'request_number': 61,
        'manifest_sha256': census.MANIFEST_SHA256, 'original_wire_sha256': ORIGIN_WIRE_SHA256,
        'projection_sha256': ORIGIN_PROJECTION_SHA256}


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
          operation_id, bundle_raw, mode='production'):
    if (type(operation_id) is not str or re.fullmatch(r'TPR-EXT26-INPUT-PROBE-[A-Za-z0-9-]{1,48}', operation_id) is None
            or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS)
            or mode not in {'production', 'offline-fixture'}): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    for identity in source_hashes.values(): e._hash(identity)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 14400: _fail()
    target, row, mapping_hash = _first(bundle_raw)
    return {'schema': 'tpr-ext26-input-probe-successor-plan-v1', 'study_id': e.STUDY_ID,
        'operation_id': operation_id, 'git_head': git_head, 'source_hashes': source_hashes,
        'owner_instruction_sha256': owner_instruction_sha256, 'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'mode': mode, 'bundle_sha256': _sha(bundle_raw), 'target': target, 'input': row, 'mapping_sha256': mapping_hash,
        'probe_receipt_name': PROBE_OPERATION + '.result.json', 'probe_receipt_sha256': PROBE_RECEIPT_SHA256,
        'probe_receipt_bytes': PROBE_RECEIPT_BYTES, 'failed_origin': _origin(), 'project_id': PROJECT_ID,
        'organization_sha256': ORGANIZATION_SHA256, 'max_metadata_bytes': MAX_TOTAL_METADATA,
        'max_input_bytes': MAX_INPUT_BYTES, 'max_response_bytes': MAX_RESPONSE, 'max_requests': MAX_REQUESTS,
        'max_seconds': MAX_SECONDS, 'native_absence_attested': False, 'full_capacity_proved': False,
        'first_key_only': True, 'explicit_not_found_diagnostic_write': True, 'old_claims_renewed': False,
        'new_looks': 0, 'quantconnect_attempts': 0, 'canonical_admission': False, 'trading': False}


def _read_exact(directory, name, *, maximum, expected_size=None, optional=False):
    ops._name(name)
    if (type(maximum) is not int or not 0 < maximum <= MAX_METADATA
            or expected_size is not None and (type(expected_size) is not int or not 0 < expected_size <= maximum)):
        _fail()
    fd = None
    try:
        try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            if optional: return None
            raise
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= maximum
                or expected_size is not None and before.st_size != expected_size): _fail()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if any(getattr(before, field) != getattr(named, field) for field in fields): _fail()
        pieces, left = [], before.st_size
        while left:
            part = os.read(fd, min(65536, left))
            if not part: _fail()
            pieces.append(part); left -= len(part)
        raw = b''.join(pieces); after, named = os.fstat(fd), os.stat(name, dir_fd=directory, follow_symlinks=False)
        if any(getattr(before, field) != getattr(value, field) for value in (after, named) for field in fields): _fail()
        return raw
    finally:
        if fd is not None: os.close(fd)


def _validate_probe(raw, plan, sources, now):
    if len(raw) != plan['probe_receipt_bytes'] or _sha(raw) != plan['probe_receipt_sha256']: _fail()
    receipt = e.parse_json(raw)
    if (receipt.get('schema') != 'tpr-ext26-store-probe-receipt-v1' or receipt.get('operation_id') != PROBE_OPERATION
            or receipt.get('study_id') != e.STUDY_ID or receipt.get('status') != 'COMPLETED'
            or receipt.get('scope_spent') is not True or receipt.get('bundle_sha256') != plan['bundle_sha256']
            or receipt.get('mapping_sha256') != plan['mapping_sha256']
            or receipt.get('target_gzip_sha256') != plan['input']['gzip_sha256']
            or e._integer(receipt.get('target_gzip_bytes')) != e._integer(plan['input']['gzip_bytes'])
            or receipt.get('target_directory_sha256') != _sha(plan['target']['directory'].encode())
            or receipt.get('target_key_sha256') != _sha(plan['target']['key'].encode())
            or receipt.get('project_id') != e.JsonNumber(str(PROJECT_ID))
            or receipt.get('organization_sha256') != ORGANIZATION_SHA256
            or e.canonical(receipt.get('failed_origin_preserved')) != e.canonical(plan['failed_origin'])): _fail()
    ended = _clock(receipt.get('ended_utc'))
    if not ended <= now < ended + probe.timedelta(hours=4): _fail()
    if (type(receipt.get('source_hashes')) is not dict or set(receipt['source_hashes']) != set(probe.SOURCE_PATHS)
            or any(receipt['source_hashes'][name] != _sha(sources[name]) for name in probe.SOURCE_PATHS)): _fail()
    for field in ('input_body_reads', 'mutations', 'automatic_retry', 'old_claims_renewed'):
        if receipt.get(field) is not False: _fail()
    for field in ('new_looks', 'quantconnect_attempts'):
        if receipt.get(field) != e.JsonNumber('0'): _fail()
    if type(receipt.get('requests')) is not list or len(receipt['requests']) != 2: _fail()
    return receipt


def _validate_origin(data, plan):
    manifest_raw = data['manifest']; manifest = e.parse_json(manifest_raw)
    if _sha(manifest_raw) != plan['failed_origin']['manifest_sha256']: _fail()
    ops.validate_manifest(manifest)
    if manifest['operation_id'] != census.QC_OPERATION: _fail()
    read, upload, transport, spent, terminal = [e.parse_json(data[key]) for key in
        ('read', 'upload', 'transport', 'request', 'terminal')]
    for value, fields in ((read, {'at', 'name', 'gzip_sha256', 'mapping_sha256', 'manifest_sha256'}),
            (upload, {'at', 'manifest_sha256', 'payload_sha256'}), (transport, {'at', 'endpoint'}),
            (spent, {'at', 'endpoint', 'payload_sha256', 'manifest_sha256'}),
            (terminal, {'at', 'status', 'automatic_retry'})):
        e._closed(value, fields)
    row, identity = plan['input'], plan['failed_origin']['manifest_sha256']
    if (read['name'] != row['stored_name'] or read['gzip_sha256'] != row['gzip_sha256']
            or read['mapping_sha256'] != plan['mapping_sha256'] or read['manifest_sha256'] != identity
            or upload['manifest_sha256'] != identity or spent['manifest_sha256'] != identity
            or upload['payload_sha256'] != spent['payload_sha256'] or transport['endpoint'] != 'object/set'
            or spent['endpoint'] != 'object/set' or terminal['status'] != 'failed_or_unknown'
            or terminal['automatic_retry'] is not False): _fail()
    clocks = [_clock(manifest['created_utc'])] + [_clock(value['at']) for value in
        (read, upload, transport, spent, terminal)] + [_clock(manifest['expires_utc'])]
    if clocks != sorted(clocks): _fail()
    projection = probe.old._projection(data['projection'])
    if (projection['original_wire_sha256'] != plan['failed_origin']['original_wire_sha256']
            or projection['projection_sha256'] != plan['failed_origin']['projection_sha256']
            or projection['projection'].get('success') is not False
            or 'quota' not in probe.old._errors(projection['projection'])['classes']): _fail()


def _multipart(organization, row, encoded):
    boundary = 'tpr-ext26-gzip-' + row['gzip_sha256']
    raw = b''.join((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n').encode()
        for field, value in (('organizationId', organization), ('key', row['stored_key'])))
    raw += (f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="{row["stored_name"]}"\r\nContent-Type: application/gzip\r\n\r\n').encode()
    return raw + encoded + f'\r\n--{boundary}--\r\n'.encode(), 'multipart/form-data; boundary=' + boundary


def _transport(endpoint, raw, content_type):
    if endpoint not in {'object/properties', 'object/set'} or type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT_BYTES + 8192: _fail()
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
        report = {'schema': 'tpr-ext26-input-probe-successor-receipt-v1', 'study_id': e.STUDY_ID,
            'operation_id': operation, 'plan_sha256': plan_hash, 'git_head': plan['git_head'],
            'source_hashes': plan['source_hashes'], 'owner_instruction_sha256': plan['owner_instruction_sha256'],
            'probe_receipt_sha256': plan['probe_receipt_sha256'], 'probe_receipt_bytes': plan['probe_receipt_bytes'],
            'failed_origin_preserved': plan['failed_origin'], 'target_gzip_sha256': plan['input']['gzip_sha256'],
            'target_key_sha256': _sha(plan['input']['stored_key'].encode()), 'mapping_sha256': plan['mapping_sha256'],
            'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True, 'read_inventory': {}, 'metadata_read_bytes': 0,
            'input_read_bytes': 0, 'read_attempts': 0, 'failed_read_body_bytes_unknown': False,
            'read_bytes_semantics': 'retained custody-verified bytes; unsuccessful-read body bytes may be unknown',
            'requests': [], 'native_absence_attested': False, 'full_capacity_proved': False,
            'quota_headroom_unknown': True, 'native_content_sha256_verified': False,
            'local_gzip_and_plaintext_sha256_verified': False, 'native_md5_matched': False,
            'object_set_succeeded': False, 'global_completion_created': False, 'global_completion_sha256': None,
            'native_hash_proof_sha256': None,
            'present_matching_metadata_only': False, 'old_claims_renewed': False, 'automatic_retry': False,
            'new_looks': 0, 'quantconnect_attempts': 0, 'canonical_admission': False, 'trading': False}
        def read(role, name, *, maximum=MAX_METADATA, expected_size=None, optional=False):
            check(); _publish(directory, operation + '.read.' + role + '.spent.json', e.canonical({
                'plan_sha256': plan_hash, 'at': clock().isoformat(), 'name': name, 'maximum_bytes': maximum,
                'expected_bytes': expected_size, 'optional': optional}))
            remaining = MAX_TOTAL_METADATA - report['metadata_read_bytes']
            if remaining <= 0: _fail()
            report['read_attempts'] += 1; report['failed_read_body_bytes_unknown'] = True
            raw = _read_exact(directory, name, maximum=min(maximum, remaining), expected_size=expected_size, optional=optional)
            report['failed_read_body_bytes_unknown'] = False
            if raw is not None:
                report['metadata_read_bytes'] += len(raw); report['read_inventory'][role] = {'sha256': _sha(raw), 'bytes': len(raw)}
            return raw
        def request(endpoint, payload, content_type='application/json'):
            number = len(report['requests']) + 1
            if number > MAX_REQUESTS: _fail()
            check(); name = operation + '.request.' + str(number)
            _publish(directory, name + '.spent.json', e.canonical({'at': clock().isoformat(), 'plan_sha256': plan_hash,
                'endpoint': endpoint, 'payload_sha256': _sha(payload), 'new_looks': 0, 'quantconnect_attempts': 0}))
            observation = {'number': number, 'endpoint': endpoint, 'status': 'FAILED_OR_UNCERTAIN', 'safe_response': None}
            report['requests'].append(observation)
            try:
                raw, status = transport(endpoint, payload, content_type); check()
                if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE: _fail()
                if endpoint == 'object/properties':
                    safe = probe._response(raw, endpoint, plan['target'], {plan['target']['key']}, http_status=status)
                else:
                    body = e.parse_json(raw)
                    if type(body) is not dict or type(body.get('success')) is not bool: _fail()
                    safe = {'http_status': status, 'native_success': body['success'], 'original_wire_sha256': _sha(raw),
                        'original_wire_bytes': len(raw), 'error_classification': probe.old._errors(body)}
                    if status == 200 and body['success'] is True and ('errors' not in body or body['errors'] == []):
                        safe['classification'] = 'native_object_set_succeeded'
                    else: safe['classification'] = 'native_object_set_refused_or_unknown'
                observation.update(status='OBSERVED', safe_response=safe); return safe
            finally: _publish(directory, name + '.terminal.json', e.canonical(observation))
        try:
            receipt_raw = read('probe', plan['probe_receipt_name'], expected_size=plan['probe_receipt_bytes'])
            receipt = _validate_probe(receipt_raw, plan, sources, clock())
            project = read('project', ON + '.project.json', maximum=probe.MAX_PROJECT,
                expected_size=e._integer(receipt['project_receipt_bytes']))
            if _sha(project) != receipt['project_receipt_sha256']: _fail()
            organization = probe._project(project, plan['target'])
            prefix = 'compressed-input.' + plan['input']['gzip_sha256']
            origin = {role: read('origin-' + role, name) for role, name in {
                'manifest': 'manifest.' + census.QC_OPERATION + '.json', 'read': prefix + '.read.spent.json',
                'upload': prefix + '.upload.spent.json', 'transport': prefix + '.upload.transport.json',
                'request': 'request.0061.spent.json', 'terminal': 'request.0061.terminal.json',
                'projection': 'request.0061.projection.json'}.items()}
            _validate_origin(origin, plan)
            if read('prior-completion', prefix + '.completed.json', optional=True) is not None: _fail()
            check(); _publish(directory, operation + '.input-read.spent.json', e.canonical({
                'at': clock().isoformat(), 'plan_sha256': plan_hash, 'name': plan['input']['stored_name'],
                'expected_bytes': e._integer(plan['input']['gzip_bytes']), 'sha256': plan['input']['gzip_sha256']}))
            inputs = _open_directory(input_path); input_info = os.fstat(inputs)
            if input_info.st_uid != os.getuid() or stat.S_IMODE(input_info.st_mode) != 0o700: _fail()
            report['read_attempts'] += 1; report['failed_read_body_bytes_unknown'] = True
            encoded = _read_exact(inputs, plan['input']['stored_name'], maximum=MAX_INPUT_BYTES,
                expected_size=e._integer(plan['input']['gzip_bytes']))
            report['failed_read_body_bytes_unknown'] = False
            report['input_read_bytes'] = len(encoded)
            storage.decode_gzip(encoded, plain_bytes=e._integer(plan['input']['plain_bytes']),
                plain_sha256=plan['input']['plain_sha256'], gzip_bytes=e._integer(plan['input']['gzip_bytes']),
                gzip_sha256=plan['input']['gzip_sha256'])
            report['local_gzip_and_plaintext_sha256_verified'] = True
            md5 = hashlib.md5(encoded).hexdigest()
            original_wire, _ = _multipart(organization, plan['input'], encoded)
            if _sha(original_wire) != e.parse_json(origin['request'])['payload_sha256']: _fail()
            payload = e.canonical({'organizationId': organization, 'key': plan['input']['stored_key']})
            before = request('object/properties', payload)
            def matched(value):
                return (value.get('classification') == 'exact_own_key_metadata_observed'
                    and value.get('native_success') is True and value.get('size_matches') is True
                    and value.get('remote_md5') == md5)
            if before.get('object_existence') == 'present_metadata':
                if not matched(before): _fail()
                report.update(status='PRESENT_MATCHED_NO_UPLOAD', native_md5_matched=True,
                    present_matching_metadata_only=True)
            else:
                if (before.get('http_status') != 200 or before.get('native_success') is not False
                        or before.get('error_classification', {}).get('classes') != ['not_found']): _fail()
                check(); wire, content_type = _multipart(organization, plan['input'], encoded)
                written = request('object/set', wire, content_type)
                if written.get('classification') != 'native_object_set_succeeded': _fail()
                report['object_set_succeeded'] = True
                after = request('object/properties', payload)
                if not matched(after): _fail()
                report['native_md5_matched'] = True
                proof = {'schema': 'tpr-ext26-input-native-hash-proof-v1', 'operation_id': operation,
                    'plan_sha256': plan_hash, 'failed_origin_preserved': plan['failed_origin'],
                    'probe_receipt_sha256': plan['probe_receipt_sha256'], 'target_gzip_sha256': plan['input']['gzip_sha256'],
                    'target_key_sha256': _sha(plan['input']['stored_key'].encode()), 'native_bytes': len(encoded),
                    'local_encoded_sha256': _sha(encoded), 'local_encoded_md5': md5, 'native_md5': after['remote_md5'],
                    'native_property_wire_sha256': after['original_wire_sha256'],
                    'native_object_set_wire_sha256': written['original_wire_sha256'],
                    'object_set_succeeded': True, 'native_md5_matched': True,
                    'native_content_sha256_verified': False, 'old_claims_renewed': False, 'new_looks': 0,
                    'quantconnect_attempts': 0, 'canonical_admission': False}
                check(); raw_proof = e.canonical(proof)
                _publish(directory, operation + '.native-hash-proof.json', raw_proof)
                report['native_hash_proof_sha256'] = _sha(raw_proof)
                completed = {'schema': 'tpr-ext26-gzip-upload-v1', 'mapping_sha256': plan['mapping_sha256'],
                    **{key: plan['input'][key] for key in ('plain_sha256', 'plain_bytes', 'logical_key',
                        'gzip_sha256', 'gzip_bytes', 'stored_key')}}
                check(); raw = e.canonical(completed); _publish(directory, prefix + '.completed.json', raw)
                report.update(status='COMPLETED_FIRST_KEY_UPLOAD', global_completion_created=True,
                    global_completion_sha256=_sha(raw))
        except (Exception, KeyboardInterrupt):
            report['failure'] = 'refused_or_uncertain_no_retry'
        report['ended_utc'] = clock().isoformat(); guard(plan['git_head'])
        raw = e.canonical(report); _publish(directory, operation + '.result.json', raw); return raw
    finally:
        if inputs is not None: os.close(inputs)
        if directory is not None: os.close(directory)


def run(**arguments):
    if Path(__file__) != LANE / SOURCE_RELATIVE: _fail()
    for module, name in ((probe, 'extended_store_probe.py'), (storage, 'extended_compressed_store.py'),
            (e, 'extended_evidence.py'), (ops, 'extended_operations.py'),
            (census, 'extended_compressed_upload_diagnostic.py'), (probe.old, 'extended_upload_diagnostic.py')):
        if Path(module.__file__) != LANE / (PREFIX + name): _fail()
    head = _guard(); sources = _sources(head)
    plan = _plan(**arguments, source_hashes={name: _sha(raw) for name, raw in sources.items()},
        git_head=head, bundle_raw=sources[BUNDLE])
    with probe._deadline():
        raw = _execute(plan, sources, PRIVATE_ROOT, INPUT_ROOT, clock=_now, guard=_guard, transport=_transport)
        if _sources(head) != sources: _fail()
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('operation-id', 'owner-instruction-sha256', 'created-utc', 'expires-utc'):
        parser.add_argument('--' + name, required=True)
    try:
        raw = run(**vars(parser.parse_args(argv))); print(raw.decode(), end='')
        return 0 if e.parse_json(raw)['status'] in {'COMPLETED_FIRST_KEY_UPLOAD', 'PRESENT_MATCHED_NO_UPLOAD'} else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end=''); return 1


if __name__ == '__main__': raise SystemExit(main())
