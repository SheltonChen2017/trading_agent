"""Fresh native O binding to one original Sharadar identity, never acquisition.

The new caller owns its claim, fixed worker intent, native network/credential
denial and exact source/host preflight. Each initial/final use holds the fixed
three-leaf source guard through its supplied private consumer's return. Guards
do not remain open across provider contact. Matching endpoint fingerprints are
not continuous integrity, historical availability or provider-price authority.
"""
from __future__ import annotations

import json
import math
import os
import re
import time

from scripts import observe_arv2_r298_reference_ticker as original


SCHEMA = 'arv2-r298-sharadar-reference-binding-v1'
PACKET_SCHEMA = 'arv2-r298-private-reference-locator-v1'
REFERENCE_SESSION, DECISION_SESSION = '2022-10-21', '2022-10-24'
IDENTITY_SHA256 = original.CONTEXT['witnesses'][0]['identity_sha256']
SOURCE_ROW_SHA256, BINDING_ROW_SHA256 = original.SOURCE_ROW_SHA256, original.BINDING_ROW_SHA256
CONTEXT_SHA256, JOIN_SHA256 = original.CONTEXT_SHA256, original.JOIN_SHA256
M_EVIDENCE_SHA256 = '5f9f7ecff6830571bc3fd57737ac71ffab06e21c0be84ce2a2fafbbd8c303dbb'
M_REPORT_SHA256 = 'fadb2929b5b38c9e0f4dc578c4015d640f5b6921872a4fce296d54aa7cc397ae'
M_REPORT_BYTES, CSV_ROWS, MAX_PRIVATE_BYTES = 4709, 74150, 16 * 1024
MAX_SOURCE_OBJECTS = 32
source_guard, evidence = original.source_guard, original.evidence
admission, identity_join = original.admission, original.identity_join
canonical, sha = original.canonical, original.sha
FALSE_FLAGS = {**evidence.FALSE_FLAGS, 'provider_contact': False, 'credential_access': False,
    'qc_contact': False, 'provider_route_admitted': False,
    'continuous_source_guard_across_provider_contact': False,
    'historical_security_continuity_proven': False, 'whole_machine_integrity_proven': False}
FINITE = frozenset(('deadline', 'phase', 'consumer', 'credentials_present', 'packet', 'packet_bound',
    'source_security_shape', 'source_security_bound', 'source_fingerprint', 'snapshot_shape',
    'snapshot_bound', 'source_binding', 'catalog_binding', 'evidence_binding', 'admission_changed',
    'consumer_changed', 'receipt'))


class Refused(ValueError):
    """Closed local predicate only; no private value is rendered."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    values = BaseException.args.__get__(error) if type(error) is Refused else ()
    return values[0] if len(values) == 1 and type(values[0]) is str and values[0] in FINITE else 'unknown'


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and time.monotonic() < deadline, 'deadline')


def _hash(value, code='receipt'):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, code)
    return value


def validate_packet(value):
    """Normalize private native/IPC fields; never print or persist the return."""
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == {'permaticker', 'expected_composite_figi', 'exchange_mic', 'original_cusips'}, 'packet')
    perma, figi, mic, cusips = (value[key] for key in
        ('permaticker', 'expected_composite_figi', 'exchange_mic', 'original_cusips'))
    require(type(perma) is str and re.fullmatch('[0-9]{1,32}', perma) is not None
        and type(figi) is str and re.fullmatch('[A-Z0-9]{12}', figi) is not None
        and type(mic) is str and mic in ('XASE', 'XNAS', 'XNYS')
        and type(cusips) in (tuple, list) and 1 <= len(cusips) <= 16
        and all(type(item) is str and re.fullmatch('[0-9A-Z]{9}', item) is not None for item in cusips)
        and tuple(cusips) == tuple(sorted(set(cusips))), 'packet')
    result = {'permaticker': perma, 'expected_composite_figi': figi,
        'exchange_mic': mic, 'original_cusips': tuple(cusips)}
    encoded = {**result, 'original_cusips': list(cusips)}
    require(len(canonical(encoded)) <= MAX_PRIVATE_BYTES, 'packet_bound')
    return result


def private_record(packet):
    """Private IPC only; this object must not enter a report, journal or chat."""
    checked = validate_packet(packet)
    return {**checked, 'original_cusips': list(checked['original_cusips'])}


def packet_digest(packet):
    return sha(canonical({'schema': PACKET_SCHEMA, 'private_fields': private_record(packet)}))


def profile_record():
    return {'schema': SCHEMA, 'private_packet_schema': PACKET_SCHEMA,
        'private_packet_fields': ['permaticker', 'expected_composite_figi', 'exchange_mic', 'original_cusips'],
        'max_private_packet_bytes': MAX_PRIVATE_BYTES, 'cusip_count_maximum': 16,
        'reference_session': REFERENCE_SESSION, 'decision_session': DECISION_SESSION,
        'identity_sha256': IDENTITY_SHA256, 'context_sha256': CONTEXT_SHA256,
        'join_sha256': JOIN_SHA256, 'source_row_sha256': SOURCE_ROW_SHA256,
        'whole_binding_row_sha256': BINDING_ROW_SHA256,
        'm_actual_exit': 0, 'm_report_byte_count': M_REPORT_BYTES, 'm_report_sha256': M_REPORT_SHA256,
        'm_nested_evidence_sha256': M_EVIDENCE_SHA256, 'm_evidence_documentary_only': True,
        'm_control_read': False, 'm_operational_entrypoint_called': False,
        'source_guard_profile_sha256': sha(canonical(source_guard.profile_record())),
        'evidence_profile_sha256': sha(canonical(evidence.profile_record())),
        'metadata_fields': list(source_guard.FIELDS), 'fixed_three_original_leaves': list(source_guard.LEAVES),
        'phases': ['initial', 'final'], 'phase_recorded_by_caller_not_receipt': True,
        'consumer_runs_before_guard_return': True, 'private_packet_escapes_only_after_guard_close': True,
        'fresh_private_admission_and_construct_rechecked_after_consumer': True,
        'endpoint_fingerprints_must_match_across_phases': True,
        'no_sf1_ticker_currency_or_raw_dates_in_private_packet': True,
        'no_other_original_archives_opened': True, 'all_corpus_file_census_performed': False,
        'fixed_original_TICKERS_member_row_census': True,
        'fresh_input_scope': 'genuine_October_D2_A11_admission_construct_and_exact_L_join',
        'source_guard_scope': 'new_fixed_current_use_not_old_v4_assessment', **FALSE_FLAGS}


def _security(value, *, vintage=False, ancestor=False):
    if ancestor:
        require(value is None, 'source_security_shape')
        return None
    if vintage:
        require(type(value) is tuple and len(value) == len(source_guard.VINTAGE_XATTR_PINS), 'source_security_shape')
        rows = []
        for item, expected in zip(value, source_guard.VINTAGE_XATTR_PINS, strict=True):
            require(type(item) is tuple and len(item) == 3 and type(item[0]) is bytes
                and type(item[1]) is int and item[1] >= 0
                and type(item[2]) is str and item == expected, 'source_security_shape')
            rows.append({'name_sha256': sha(item[0]), 'byte_count': item[1], 'sha256': _hash(item[2])})
        return {'empty_acl_required_by_guard': True, 'vintage_xattrs': rows}
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == {'acl_empty', 'xattrs'} and value['acl_empty'] is True
        and type(value['xattrs']) is dict and len(value['xattrs']) <= len(source_guard.security.ALLOWED_XATTRS),
        'source_security_shape')
    rows = []
    for name, item in value['xattrs'].items():
        require(type(name) is str and name.isascii() and name.encode('ascii') in source_guard.security.ALLOWED_XATTRS
            and type(item) is dict and all(type(key) is str for key in item)
            and set(item) == {'size', 'sha256'} and type(item['size']) is int
            and 0 <= item['size'] <= source_guard.security.MAX_VALUE_BYTES, 'source_security_shape')
        rows.append({'name_sha256': sha(name.encode('ascii')), 'byte_count': item['size'], 'sha256': _hash(item['sha256'])})
    return {'acl_empty': True, 'xattrs': sorted(rows, key=lambda item: item['name_sha256'])}


def source_fingerprint(guard):
    """Hash only known fixed guard objects, never descriptors or raw xattrs."""
    require(type(guard) is source_guard.SourceGuard and guard._active is True
        and type(guard._objects) is list and 1 <= len(guard._objects) <= MAX_SOURCE_OBJECTS, 'source_security_shape')
    paths = tuple(reversed(source_guard.CAPTURE.parents)) + (source_guard.CAPTURE,) + tuple(
        source_guard.CAPTURE / name for name in source_guard.LEAVES)
    require(len(guard._objects) == len(paths), 'source_security_shape')
    objects = []
    for item, path in zip(guard._objects, paths, strict=True):
        require(type(item) is dict and all(type(key) is str for key in item)
            and set(item) == {'path', 'fd', 'parent', 'name', 'metadata', 'leaf', 'security'}
            and type(item['path']) is type(source_guard.ROOT) and item['path'] == path
            and type(item['fd']) is int and item['fd'] >= 0
            and type(item['parent']) is int and item['parent'] >= 0
            and type(item['name']) is str and item['name'] == ('.' if path == paths[0] else path.name)
            and type(item['leaf']) is bool and item['leaf'] == (path.parent == source_guard.CAPTURE)
            and type(item['metadata']) is tuple and len(item['metadata']) == len(source_guard.FIELDS)
            and all(type(value) is int and value >= 0 for value in item['metadata']), 'source_security_shape')
        ancestor = path != source_guard.ROOT and source_guard.ROOT not in path.parents
        objects.append({'path': str(path), 'metadata': list(item['metadata']), 'leaf': item['leaf'],
            'security': _security(item['security'], vintage=path == source_guard.CAPTURE, ancestor=ancestor)})
    encoded = canonical({'schema': SCHEMA + '-source-endpoint', 'objects': objects})
    require(len(encoded) <= 32 * 1024, 'source_security_bound')
    return sha(encoded)


def _snapshot_digest(value, deadline):
    require(type(value) is tuple and len(value) == 5 and all(type(item) is bytes for item in value[:3])
        and type(value[3]) is tuple and 6 <= len(value[3]) <= admission.transport.MAX_OBJECTS
        and type(value[4]) is tuple and len(value[4]) == 11, 'snapshot_shape')
    uploads, sources = [], []
    for item in value[3]:
        remaining(deadline)
        require(type(item) is tuple and len(item) == 2 and all(type(raw) is bytes and 0 < len(raw)
            <= admission.transport.MAX_OBJECT_BYTES for raw in item), 'snapshot_shape')
        uploads.append([sha(item[0]), sha(item[1])])
    for item in value[4]:
        require(type(item) is tuple and len(item) == 2 and type(item[0]) is str and item[0].isascii()
            and type(item[1]) is bytes and 0 < len(item[1]) <= 64000, 'snapshot_shape')
        sources.append([item[0], sha(item[1])])
    remaining(deadline)
    return sha(canonical({'schema': SCHEMA + '-input-snapshot', 'records': [sha(item) for item in value[:3]],
        'uploads': uploads, 'sources': sources}))


def _fixed_receipt():
    return {'schema': SCHEMA, 'status': 'fresh_original_identity_bound',
        'reference_session': REFERENCE_SESSION, 'decision_session': DECISION_SESSION,
        'identity_sha256': IDENTITY_SHA256, 'context_sha256': CONTEXT_SHA256, 'join_sha256': JOIN_SHA256,
        'source_row_sha256': SOURCE_ROW_SHA256, 'whole_binding_row_sha256': BINDING_ROW_SHA256,
        'm_report_sha256': M_REPORT_SHA256, 'm_nested_evidence_sha256': M_EVIDENCE_SHA256,
        'source_guard_profile_sha256': sha(canonical(source_guard.profile_record())),
        'evidence_profile_sha256': sha(canonical(evidence.profile_record())),
        'csv_row_count': CSV_ROWS, 'result_cell': 0, **FALSE_FLAGS}


def validate_receipt(value):
    fixed = _fixed_receipt()
    variable = {'private_packet_sha256', 'source_endpoint_sha256', 'fresh_input_snapshot_sha256', 'fresh_admission_sha256'}
    require(type(value) is dict and all(type(key) is str for key in value) and set(value) == {*fixed, *variable}
        and all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items()), 'receipt')
    for key in variable:
        _hash(value[key])
    return json.loads(canonical(value))


def fingerprint(receipt):
    return sha(canonical(validate_receipt(receipt)))


def validate_pair(receipt, packet):
    checked, private = validate_receipt(receipt), validate_packet(packet)
    require(checked['private_packet_sha256'] == packet_digest(private), 'receipt')
    return checked, private


def prepare(deadline, *, phase, consumer=None):
    """One new caller-owned phase; private consumer runs before guard return."""
    remaining(deadline)
    require(type(phase) is str and phase in ('initial', 'final'), 'phase')
    require(consumer is None or callable(consumer), 'consumer')
    require(not any(key in os.environ for key in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY',
        'MASSIVE_API_KEY', 'POLYGON_API_KEY', 'EODHD_API_TOKEN', 'FMP_API_KEY')), 'credentials_present')
    original.environment.require_safe_environment()
    dated = original.context()
    with source_guard.SourceGuard(deadline=deadline) as guard:
        endpoint = source_fingerprint(guard)
        admitted = admission.admit(deadline)
        plain, projected = original.admitted.prep.construct(deadline)
        snapshot = original.previous._constructed_matches(plain, projected, admitted)
        snapshot_pin = _snapshot_digest(snapshot, deadline)
        joined = identity_join.join(plain, dated, admitted)
        binding, match = original._catalog(plain, joined)
        row, count = original.original_row(guard.read('manifest.json', deadline),
            guard.read('manifest.sha256', deadline), guard.read(original.ARCHIVE_NAME, deadline), deadline)
        proof, opaque_route = evidence.verify(row, binding, dated, expected_match=match)
        opaque_route = None  # The verified original row, not the opaque route, supplies these locators.
        proof = evidence.validate_receipt(proof)
        require(evidence.receipt_digest(proof) == M_EVIDENCE_SHA256 and count == CSV_ROWS, 'evidence_binding')
        packet = validate_packet({'permaticker': evidence.composer._text(row['permaticker'], 'permaticker'),
            'expected_composite_figi': evidence.composer._text(row['figi'], 'figi'),
            'exchange_mic': binding['diagnostic_exchange_mic'],
            'original_cusips': evidence.composer._sharadar_cusips(row['cusips'])})
        receipt = validate_receipt({**_fixed_receipt(), 'private_packet_sha256': packet_digest(packet),
            'source_endpoint_sha256': endpoint, 'fresh_input_snapshot_sha256': snapshot_pin,
            'fresh_admission_sha256': sha(canonical(admitted))})
        fresh_plain, fresh_projected = original.admitted.prep.construct(deadline)
        require(original.previous._constructed_matches(fresh_plain, fresh_projected, admitted) == snapshot
            and admission.admit(deadline) == admitted, 'admission_changed')
        original.environment.require_safe_environment()
        guard.verify()
        require(source_fingerprint(guard) == endpoint, 'source_fingerprint')
        before_receipt, before_packet = fingerprint(receipt), packet_digest(packet)
        result = (receipt, packet) if consumer is None else consumer(receipt, packet)
        validate_pair(receipt, packet)
        require(fingerprint(receipt) == before_receipt and packet_digest(packet) == before_packet, 'consumer_changed')
        final_plain, final_projected = original.admitted.prep.construct(deadline)
        require(original.previous._constructed_matches(final_plain, final_projected, admitted) == snapshot
            and admission.admit(deadline) == admitted, 'admission_changed')
        original.environment.require_safe_environment()
        remaining(deadline)
        guard.verify()
        require(source_fingerprint(guard) == endpoint, 'source_fingerprint')
    return result
