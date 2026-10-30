"""Fresh local all-binding preparation, with no operational entry point.

The separately frozen caller owns its claim, source closure, native isolation,
private IPC and deadline. This module does not read old readiness/storage
controls, contact providers, publish files or grant acquisition authority.
The second return is PRIVATE licensed metadata and must never enter logs.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import time

from scripts import arv2_r298_reference_identity_join as identity
from scripts import arv2_r298_reference_ticker_source_guard as source_guard
from scripts import arv2_r298_sharadar_all_routes as routes
from scripts import arv2_r298_original_ticker_catalog as original_decoder
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october
from research.analyst_revisions_v2_qc import newrule_comparison_submission as original
from research.analyst_revisions_v2_qc import newrule_plain_transport as transport


SCHEMA = 'arv2-r298-all-route-worker-v1'
INPUT_SCHEMA = SCHEMA + '-input'
GUARD_SCHEMA = SCHEMA + '-source-guard'
ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
PACKAGE_SHA256 = '411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
LINEAGE_SHA256 = 'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'
INPUT_ROOT = ROOT / 'artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-D5/package'
PACKAGE = INPUT_ROOT / ('arv2-preliminary-qc-package-' + PACKAGE_SHA256[:24])
LINEAGE = INPUT_ROOT / ('arv2-october-lineage-' + LINEAGE_SHA256) / 'lineage.json'
EXPECTED_BINDINGS, EXPECTED_FUNDS = 6151, 8
MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_PRIVATE_BYTES = routes.MAX_PRIVATE_BYTES
MAX_SUMMARY_BYTES = 128 * 1024
FALSE_FLAGS = {'provider_contact': False, 'credential_access': False, 'qc_contact': False,
    'price_dispatch': False, 'old_readiness_control_read': False, 'old_storage_control_read': False,
    'old_operational_entrypoint_called': False, 'provider_route_admitted': False,
    'price_coverage_proven': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}
OCTOBER_CODES = frozenset(('october_wrapper_type', 'october_lineage_unreadable', 'october_lineage_binding',
    'october_valuation_or_prefix_policy', 'october_lineage_count', 'october_contribution_count',
    'october_false_flag', 'october_scope_binding', 'october_ratings_normalization_binding',
    'october_ratings_normalization_count', 'october_ratings_page_count', 'october_lineage_name',
    'october_lineage_inventory'))
TRANSPORT_CODES = frozenset(('json_bound', 'json_type', 'payload_type', 'hash', 'json_duplicate',
    'payload_bound', 'json', 'canonical', 'authority', 'inventory', 'source_inventory', 'source_total',
    'source_payload', 'activation_order', 'source_manifest', 'source_identity', 'source_binding_count',
    'source_census', 'source_contract', 'role', 'evaluator_manifest', 'source_rows', 'plain_rows',
    'object_bound', 'total_bound', 'role_order', 'source_duplicate', 'source_binding_stream',
    'activation_bound', 'source_pin'))
FINITE = frozenset(('deadline', 'metadata_bound', 'input', 'catalog', 'calendar',
    'plain_changed', 'original_catalog', 'source_guard', 'routes', 'private_frame', 'summary', 'unknown',
    'source_guard_refused', 'original_decoder_refused', 'routes_refused', 'identity_refused',
    'october_refused', 'transport_refused', 'compact_reload_refused', 'compact_capacity_refused',
    'binding_validation_refused', 'calendar_validation_refused', 'original_input_refused', 'os_error')) | OCTOBER_CODES | frozenset(
        prefix + code for prefix, codes in (('source_guard_', source_guard.FINITE),
            ('original_decoder_', original_decoder.FINITE), ('routes_', routes.FINITE),
            ('identity_', identity.FINITE), ('transport_', TRANSPORT_CODES)) for code in codes)
canonical, sha = routes.canonical, routes.sha


class Refused(ValueError):
    """Closed local predicate; never a source row, path or exception text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _failure_code(error):
    """Selected static labels only; never format or forward arbitrary args."""
    if type(error) is Refused:
        return finite(error)
    for kind, prefix, codes in ((source_guard.Refused, 'source_guard_', source_guard.FINITE),
            (original_decoder.Refused, 'original_decoder_', original_decoder.FINITE),
            (routes.Refused, 'routes_', routes.FINITE), (identity.Refused, 'identity_', identity.FINITE),
            (transport.PlainTransportError, 'transport_', TRANSPORT_CODES)):
        if type(error) is kind:
            args = BaseException.args.__get__(error)
            return prefix + args[0] if len(args) == 1 and type(args[0]) is str and args[0] in codes else prefix + 'refused'
    if type(error) is october.OctoberOrderInputPackageError:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in OCTOBER_CODES else 'october_refused'
    if type(error) is original.compact.AcceptedRiskPreliminaryPackageCapacityError:
        return 'compact_capacity_refused'
    if type(error) is original.compact.AcceptedRiskPreliminaryPackageError:
        return 'compact_reload_refused'
    if type(error) is identity.figi.PreliminaryQcFigiError:
        return 'binding_validation_refused'
    if type(error) is identity.evaluator.PreliminaryRatingEvaluationError:
        return 'calendar_validation_refused'
    if type(error) is original.NewruleSubmissionError:
        # This worker only calls the pure exact-input predicate, not lifecycle.
        return 'original_input_refused'
    return 'os_error' if isinstance(error, OSError) else 'unknown'


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and time.monotonic() < deadline, 'deadline')


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def profile_record():
    return {'schema': SCHEMA, 'package_sha256': PACKAGE_SHA256, 'lineage_sha256': LINEAGE_SHA256,
        'binding_count': EXPECTED_BINDINGS, 'fund_count': EXPECTED_FUNDS,
        'maximum_metadata_bytes_each': MAX_METADATA_BYTES, 'maximum_private_frame_bytes': MAX_PRIVATE_BYTES,
        'maximum_summary_bytes': MAX_SUMMARY_BYTES, 'metadata_fields': list(source_guard.FIELDS),
        'source_guard_profile_sha256': sha(canonical(source_guard.profile_record())),
        'input_scope': 'fresh_exact_October_package_process_authority_and_retained_plain_streams',
        'axis_scope': 'exact_frozen_October_calendar_not_independent_exchange_proof',
        'original_scope': 'all_fixed_original_TICKERS_rows_under_new_three_leaf_guard',
        'return_scope': 'closed_metadata_and_separate_private_all_routes_record',
        'finite_failure_codes': sorted(FINITE),
        'route_refusals_preserved': True, 'same_process_plain_capability_required': True,
        'guard_normal_return_required': True, 'whole_interpreter_integrity_proven': False,
        'continuous_or_historical_source_integrity_proven': False, **FALSE_FLAGS}


def _load_plain(deadline):
    remaining(deadline)
    wrapped = october.load_october_order_input_package(PACKAGE,
        expected_package_sha256=PACKAGE_SHA256, lineage_path=LINEAGE,
        expected_lineage_sha256=LINEAGE_SHA256)
    package = original._input(wrapped)
    remaining(deadline)
    plain = transport.build_plain_transport(package, expected_package_sha256=PACKAGE_SHA256,
        expected_lineage_sha256=LINEAGE_SHA256)
    remaining(deadline)
    return plain


def _catalog(plain, deadline):
    """Validate every original binding; do not reuse the witness-only join."""
    remaining(deadline)
    initial, record, inventory = identity._plain(plain)
    require(plain.source_package_sha256 == PACKAGE_SHA256
        and plain.source_lineage_sha256 == LINEAGE_SHA256, 'input')
    selected = identity._streams(plain, record)
    manifest = selected['evaluator_manifest'][0]
    admission = identity._manifest(manifest, record)
    rows = selected['runtime_symbol_bindings']
    require(type(rows) is list and len(rows) == EXPECTED_BINDINGS
        and record['runtime_symbol_binding_count'] == EXPECTED_BINDINGS, 'catalog')
    checked, identities, figis, row_pins, inventories = [], set(), set(), set(), set()
    last = None
    for source in rows:
        remaining(deadline)
        row = identity.figi._input_row(source, admission)
        key = row['security_id']
        require((last is None or last < key) and key not in identities
            and row['composite_figi'] not in figis and row['row_sha256'] not in row_pins
            and row['admitted_mapping_count'] == EXPECTED_BINDINGS, 'catalog')
        last = key
        identities.add(key); figis.add(row['composite_figi']); row_pins.add(row['row_sha256'])
        inventories.add(row['admitted_mapping_inventory_sha256'])
        checked.append(row)
    require(len(inventories) == 1, 'catalog')
    binding_digest = hashlib.sha256()
    for row in checked:
        binding_digest.update(identity.figi._canonical(row))
    require(binding_digest.hexdigest() == record['runtime_symbol_bindings_sha256'], 'catalog')
    sessions = tuple(selected['session_axis'])
    axis = identity.evaluator._parse_sessions(sessions)
    expected_axis = october._sessions()
    require(axis == expected_axis and type(manifest['session_axis_count']) is int
        and manifest['session_axis_count'] == len(axis)
        and identity.evaluator._stream_sha256(sessions) == manifest['session_axis_sha256'], 'calendar')
    contract = {'binding_count': len(checked),
        'binding_stream_sha256': record['runtime_symbol_bindings_sha256'],
        'security_master_admission_sha256': admission,
        'admitted_mapping_inventory_sha256': next(iter(inventories))}
    public = {'schema': INPUT_SCHEMA, 'source_package_sha256': PACKAGE_SHA256,
        'source_lineage_sha256': LINEAGE_SHA256, 'plain_package_sha256': plain.package_sha256,
        'activation_manifest_sha256': plain.activation_manifest_sha256,
        'parent_proof_sha256': plain.parent_proof_sha256,
        'upload_inventory_sha256': sha(canonical(inventory)),
        'evaluator_manifest_sha256': record['evaluator_manifest_sha256'],
        'session_axis_count': len(axis), 'session_axis_sha256': manifest['session_axis_sha256'],
        'ordered_session_values_sha256': identity.legacy._sha(list(axis)),
        'first_session': axis[0], 'last_session': axis[-1], 'binding_contract': contract}
    remaining(deadline)
    return initial, record, selected, checked, public


def _guard_fingerprint(guard):
    """Hash full fixed endpoint metadata/security; expose no descriptors/xattrs."""
    require(type(guard) is source_guard.SourceGuard and guard._active is True
        and type(guard._objects) is list and 1 <= len(guard._objects) <= 32, 'source_guard')
    paths = tuple(reversed(source_guard.CAPTURE.parents)) + (source_guard.CAPTURE,) + tuple(
        source_guard.CAPTURE / name for name in source_guard.LEAVES)
    require(len(paths) == len(guard._objects), 'source_guard')
    objects = []
    for row, path in zip(guard._objects, paths, strict=True):
        require(type(row) is dict and set(row) == {'path', 'fd', 'parent', 'name', 'metadata', 'leaf', 'security'}
            and type(row['path']) is type(ROOT) and row['path'] == path
            and type(row['fd']) is int and row['fd'] >= 0
            and type(row['parent']) is int and row['parent'] >= 0
            and row['name'] == ('.' if path == paths[0] else path.name)
            and type(row['leaf']) is bool and row['leaf'] == (path.parent == source_guard.CAPTURE)
            and type(row['metadata']) is tuple and len(row['metadata']) == len(source_guard.FIELDS)
            and all(type(item) is int and item >= 0 for item in row['metadata']), 'source_guard')
        security = row['security']
        if path != source_guard.ROOT and source_guard.ROOT not in path.parents:
            require(security is None, 'source_guard')
            retained = None
        elif path == source_guard.CAPTURE:
            require(type(security) is tuple and security == source_guard.VINTAGE_XATTR_PINS, 'source_guard')
            retained = [{'name_sha256': sha(name), 'size': count, 'sha256': pin}
                for name, count, pin in security]
        else:
            require(type(security) is dict and set(security) == {'acl_empty', 'xattrs'}
                and security['acl_empty'] is True and type(security['xattrs']) is dict
                and len(security['xattrs']) <= len(source_guard.security.ALLOWED_XATTRS), 'source_guard')
            retained = []
            for name, fact in security['xattrs'].items():
                require(type(name) is str and name.isascii()
                    and name.encode('ascii') in source_guard.security.ALLOWED_XATTRS
                    and type(fact) is dict and set(fact) == {'size', 'sha256'}
                    and type(fact['size']) is int and 0 <= fact['size'] <= source_guard.security.MAX_VALUE_BYTES
                    and _hash(fact['sha256']), 'source_guard')
                retained.append({'name_sha256': sha(name.encode('ascii')), **fact})
            retained.sort(key=lambda item: item['name_sha256'])
        objects.append({'path_sha256': sha(str(path).encode('utf8')),
            'metadata': list(row['metadata']), 'leaf': row['leaf'], 'security': retained})
    return sha(canonical(objects))


def _catalog_unchanged(plain, initial, record, selected, deadline):
    remaining(deadline)
    transport.require_plain_transport(plain)
    require(transport._fingerprint(plain) == initial and plain.to_record() == record, 'plain_changed')
    fresh = identity._streams(plain, record)
    require(canonical(fresh) == canonical(selected), 'plain_changed')
    remaining(deadline)


def _prepare_bound(plain, stocks_raw, funds_raw, *, deadline):
    """Internal integration seam; genuine authority remains mandatory."""
    from scripts import arv2_r298_original_ticker_catalog as decoder
    remaining(deadline)
    require(all(type(raw) is bytes and 0 < len(raw) <= MAX_METADATA_BYTES
        for raw in (stocks_raw, funds_raw)), 'metadata_bound')
    initial, record, selected, binding_rows, input_binding = _catalog(plain, deadline)
    input_pin = sha(canonical(input_binding))
    with source_guard.SourceGuard(deadline=deadline) as guard:
        before = _guard_fingerprint(guard)
        original_raws = tuple(guard.read(name, deadline) for name in source_guard.LEAVES)
        original_receipt, original_catalog = decoder.decode_original_catalog(*original_raws, deadline=deadline)
        original_receipt = decoder.validate_receipt(original_receipt)
        require(type(original_catalog) is decoder.PrivateOriginalTickerCatalog, 'original_catalog')
        original_rows = original_catalog.mapping_rows()
        require(type(original_rows) is tuple and len(original_rows) == original_receipt['csv_row_count']
            and set(original_catalog.columns) == routes.ORIGINAL_FIELDS, 'original_catalog')
        source_digests = []
        for row in original_rows:
            remaining(deadline)
            source_digests.append(routes.original.source_row_digest(row))
        require(sha(decoder.canonical(source_digests)) == original_receipt['ordered_source_row_digests_sha256'],
            'original_catalog')
        remaining(deadline)
        routing_summary, private = routes.join(binding_rows, original_rows, stocks_raw, funds_raw,
            binding_contract=input_binding['binding_contract'])
        private_record = private.private_record()
        raw = canonical(private_record)
        require(0 < len(raw) <= MAX_PRIVATE_BYTES
            and routing_summary['private_payload_byte_count'] == len(raw)
            and routing_summary['private_payload_sha256'] == sha(raw), 'private_frame')
        _catalog_unchanged(plain, initial, record, selected, deadline)
        require(sha(canonical(input_binding)) == input_pin, 'plain_changed')
        guard.verify()
        require(_guard_fingerprint(guard) == before, 'source_guard')
    # Nothing is returned before normal guard __exit__ verification and close.
    remaining(deadline)
    summary = {'schema': SCHEMA, 'input_binding': input_binding,
        'original_catalog_receipt': original_receipt, 'routing_summary': routing_summary,
        'private_frame_byte_count': len(raw), 'private_frame_sha256': sha(raw),
        'current_metadata': {table: {'byte_count': len(raw), 'sha256': sha(raw)}
            for table, raw in (('stocks', stocks_raw), ('funds', funds_raw))},
        'source_guard_receipt': {'schema': GUARD_SCHEMA,
            'profile_sha256': sha(canonical(source_guard.profile_record())),
            'metadata_fields': list(source_guard.FIELDS), 'original_leaf_count': len(source_guard.LEAVES),
            'original_leaf_pins': [{'byte_count': len(raw), 'sha256': sha(raw)} for raw in original_raws],
            'source_endpoint_sha256': before, 'full_ten_field_endpoints_equal': True,
            'root_and_below_native_acl_xattr_checked': True, 'ancestors_identity_only': True,
            'guard_normal_return': True, 'continuous_integrity_proven': False,
            'historical_integrity_proven': False}, **FALSE_FLAGS}
    return validate_summary(summary), private_record


def prepare(stocks_raw, funds_raw, *, deadline):
    """Fresh authentic local input preparation; second return is PRIVATE."""
    try:
        remaining(deadline)
        require(all(type(raw) is bytes and 0 < len(raw) <= MAX_METADATA_BYTES
            for raw in (stocks_raw, funds_raw)), 'metadata_bound')
        return _prepare_bound(_load_plain(deadline), stocks_raw, funds_raw, deadline=deadline)
    except Exception as error:
        raise Refused(_failure_code(error)) from None


def validate_summary(value):
    """Validate closed metadata only; this is never source/route authority."""
    try:
        return _validated_summary(value)
    except Exception as error:
        raise Refused(_failure_code(error)) from None


def _validated_summary(value):
    from scripts import arv2_r298_original_ticker_catalog as decoder
    require(type(value) is dict and set(value) == {'schema', 'input_binding', 'original_catalog_receipt',
        'routing_summary', 'current_metadata', 'source_guard_receipt', 'private_frame_byte_count',
        'private_frame_sha256', *FALSE_FLAGS}
        and value['schema'] == SCHEMA and all(value[key] is False for key in FALSE_FLAGS), 'summary')
    raw = canonical(value)
    require(0 < len(raw) <= MAX_SUMMARY_BYTES, 'summary')
    checked = json.loads(raw)
    decoder.validate_receipt(checked['original_catalog_receipt'])
    _validate_input(checked['input_binding'])
    _validate_routing(checked['routing_summary'], checked['input_binding']['binding_contract'])
    require(type(checked['private_frame_byte_count']) is int
        and checked['private_frame_byte_count'] == checked['routing_summary']['private_payload_byte_count']
        and checked['private_frame_sha256'] == checked['routing_summary']['private_payload_sha256']
        and checked['routing_summary']['original_row_count'] == checked['original_catalog_receipt']['csv_row_count'], 'summary')
    metadata = checked['current_metadata']
    require(type(metadata) is dict and set(metadata) == {'stocks', 'funds'}, 'summary')
    for fact in metadata.values():
        require(type(fact) is dict and set(fact) == {'byte_count', 'sha256'}
            and type(fact['byte_count']) is int and 0 < fact['byte_count'] <= MAX_METADATA_BYTES
            and _hash(fact['sha256']), 'summary')
    guard = checked['source_guard_receipt']
    require(type(guard) is dict and set(guard) == {'schema', 'profile_sha256', 'metadata_fields',
        'original_leaf_count', 'original_leaf_pins', 'source_endpoint_sha256', 'full_ten_field_endpoints_equal',
        'root_and_below_native_acl_xattr_checked', 'ancestors_identity_only', 'guard_normal_return',
        'continuous_integrity_proven', 'historical_integrity_proven'}
        and guard['schema'] == GUARD_SCHEMA
        and guard['profile_sha256'] == sha(canonical(source_guard.profile_record()))
        and guard['metadata_fields'] == list(source_guard.FIELDS)
        and type(guard['original_leaf_count']) is int and guard['original_leaf_count'] == 3
        and type(guard['original_leaf_pins']) is list and len(guard['original_leaf_pins']) == 3
        and _hash(guard['source_endpoint_sha256'])
        and all(guard[key] is True for key in ('full_ten_field_endpoints_equal',
            'root_and_below_native_acl_xattr_checked', 'ancestors_identity_only', 'guard_normal_return'))
        and guard['continuous_integrity_proven'] is False and guard['historical_integrity_proven'] is False, 'summary')
    for fact in guard['original_leaf_pins']:
        require(type(fact) is dict and set(fact) == {'byte_count', 'sha256'}
            and type(fact['byte_count']) is int and fact['byte_count'] > 0 and _hash(fact['sha256']), 'summary')
    require(guard['original_leaf_pins'][0]['sha256'] == source_guard.MANIFEST_SHA256
        and guard['original_leaf_pins'][0]['byte_count'] <= source_guard.MANIFEST_MAX_BYTES
        and guard['original_leaf_pins'][1] == {'byte_count': 65,
            'sha256': sha((source_guard.MANIFEST_SHA256 + '\n').encode('ascii'))}
        and guard['original_leaf_pins'][2] == {'byte_count': source_guard.ARCHIVE_BYTES,
            'sha256': source_guard.ARCHIVE_SHA256}, 'summary')
    receipt = checked['original_catalog_receipt']
    require(guard['original_leaf_pins'][0]['sha256'] == receipt['manifest_sha256']
        and guard['original_leaf_pins'][2] == {'byte_count': receipt['archive_byte_count'],
            'sha256': receipt['archive_sha256']}, 'summary')
    return checked


def _validate_input(value):
    hashes = ('plain_package_sha256', 'activation_manifest_sha256', 'parent_proof_sha256',
        'upload_inventory_sha256', 'evaluator_manifest_sha256', 'session_axis_sha256',
        'ordered_session_values_sha256')
    expected_axis = october._sessions()
    require(type(value) is dict and set(value) == {'schema', 'source_package_sha256',
        'source_lineage_sha256', 'session_axis_count', 'first_session', 'last_session', 'binding_contract', *hashes}
        and value['schema'] == INPUT_SCHEMA and value['source_package_sha256'] == PACKAGE_SHA256
        and value['source_lineage_sha256'] == LINEAGE_SHA256 and all(_hash(value[key]) for key in hashes)
        and type(value['session_axis_count']) is int and value['session_axis_count'] == len(expected_axis)
        and type(value['first_session']) is str and type(value['last_session']) is str
        and re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', value['first_session']) is not None
        and value['last_session'] == expected_axis[-1] == october.VALUATION_END_SESSION
        and value['first_session'] == expected_axis[0]
        and value['ordered_session_values_sha256'] == identity.legacy._sha(list(expected_axis)), 'summary')
    contract = routes._contract(value['binding_contract'])
    require(contract['binding_count'] == EXPECTED_BINDINGS, 'summary')


def _validate_routing(value, contract):
    keys = {'schema', 'scope', 'binding_contract', 'price_window', 'original_row_count',
        'original_rows_digest', 'metadata_rows_sha256', 'metadata_row_counts',
        'catalog_unknown_vocabulary_row_count', 'catalog_collision_group_counts',
        'disposition_counts', 'refusal_counts', 'private_payload_byte_count', 'private_payload_sha256'}
    require(type(value) is dict and set(value) == keys and value['schema'] == routes.SCHEMA
        and value['scope'] == 'supplied_current_route_crosscheck_not_admission'
        and value['binding_contract'] == contract
        and value['price_window'] == [routes.PRICE_FIRST, routes.PRICE_LAST]
        and type(value['original_row_count']) is int and 0 < value['original_row_count'] <= routes.MAX_ORIGINAL_ROWS
        and _hash(value['original_rows_digest']) and _hash(value['private_payload_sha256'])
        and type(value['private_payload_byte_count']) is int and 0 < value['private_payload_byte_count'] <= MAX_PRIVATE_BYTES
        and type(value['catalog_unknown_vocabulary_row_count']) is int
        and value['catalog_unknown_vocabulary_row_count'] >= 0, 'summary')
    for field in ('metadata_rows_sha256', 'metadata_row_counts', 'disposition_counts', 'refusal_counts'):
        require(type(value[field]) is dict and set(value[field]) == {'stocks', 'funds'}, 'summary')
    for table, expected in (('stocks', EXPECTED_BINDINGS), ('funds', EXPECTED_FUNDS)):
        require(_hash(value['metadata_rows_sha256'][table]) and type(value['metadata_row_counts'][table]) is int
            and 0 <= value['metadata_row_counts'][table] < routes.current.MAX_ROWS, 'summary')
        dispositions, reasons = value['disposition_counts'][table], value['refusal_counts'][table]
        allowed = {'routed', 'refused', 'outside_window'} if table == 'stocks' else {'routed', 'refused'}
        require(type(dispositions) is dict and set(dispositions) <= allowed
            and bool(dispositions) and all(type(count) is int and count > 0 for count in dispositions.values())
            and sum(dispositions.values()) == expected and type(reasons) is dict
            and set(reasons) <= routes.REASONS and all(type(count) is int and count > 0 for count in reasons.values())
            and sum(reasons.values()) == dispositions.get('refused', 0), 'summary')
    collisions = value['catalog_collision_group_counts']
    require(type(collisions) is dict and set(collisions) == {'permaticker_collision_groups',
        'figi_collision_groups', 'ticker_collision_groups', 'complete_token_collision_groups',
        'malformed_overlap_token_groups'} and all(type(count) is int and count >= 0
            for count in collisions.values()), 'summary')
    total = sum(value['metadata_row_counts'].values())
    require(value['catalog_unknown_vocabulary_row_count'] <= total
        and all(count <= (64 * total if 'token' in key else total // 2)
            for key, count in collisions.items()), 'summary')
