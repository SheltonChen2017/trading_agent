"""New offline full-catalog worker; no old operation or control is replayed.

The frozen v1 process-bound input readers and metadata validators are reused
as functions. The new route join accepts the exact authenticated original
header without guessing every unused column name. No input cell is renamed,
removed or normalized. The caller owns its new claim, isolation and private IPC.
"""
from __future__ import annotations

import json

from scripts import arv2_r298_all_route_worker as previous
from scripts import arv2_r298_sharadar_all_routes_v2 as routes


SCHEMA = 'arv2-r298-all-route-worker-v2'
POLICY_SCHEMA = SCHEMA + '-original-shape-policy'
ORIGINAL_SCHEMA = SCHEMA + '-original-schema-observation'
PREVIOUS_WORKER_SHA256 = '52a9ad6abf2f7385adbf844743ea2e5c06aaf707a872a4e2c17bf6a0bb6d0a81'
MAX_METADATA_BYTES, MAX_PRIVATE_BYTES, MAX_SUMMARY_BYTES = (
    previous.MAX_METADATA_BYTES, previous.MAX_PRIVATE_BYTES, previous.MAX_SUMMARY_BYTES)
FALSE_FLAGS = dict(previous.FALSE_FLAGS)
SUBPREDICATES = frozenset(('original_catalog_type', 'original_catalog_count', 'original_columns',
    'original_catalog_digest', 'original_schema', 'shape_policy'))
FINITE = previous.FINITE | SUBPREDICATES | frozenset('routes_v2_' + code for code in routes.FINITE) | {
    'routes_v2_refused'}
source_guard, original_decoder = previous.source_guard, previous.original_decoder
canonical, sha, remaining = previous.canonical, previous.sha, previous.remaining
_load_plain, _catalog = previous._load_plain, previous._catalog
_catalog_unchanged, _guard_fingerprint = previous._catalog_unchanged, previous._guard_fingerprint


class Refused(ValueError):
    """Finite prospective predicate; never contains column names or row data."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _failure_code(error):
    if type(error) is Refused:
        return finite(error)
    if type(error) is routes.Refused:
        args = BaseException.args.__get__(error)
        return ('routes_v2_' + args[0] if len(args) == 1 and type(args[0]) is str
            and args[0] in routes.FINITE else 'routes_v2_refused')
    return previous._failure_code(error)


def original_shape_policy():
    return {'schema': POLICY_SCHEMA, 'exact_original_column_count': 28,
        'header_authority': 'unchanged_fixed_original_decoder_manifest_member_and_header_hashes',
        'semantic_columns': 'new_routes_valid_original_columns_required_identity_fields',
        'required_identity_fields': sorted(routes.REQUIRED_ORIGINAL_FIELDS),
        'unused_columns': 'authenticated_original_names_and_cells_preserved_without_guessed_full_name_set',
        'legacy_name_set_equality': 'closed_observation_only_never_admission',
        'source_row_hash': 'unchanged_frozen_full_original_row_canonicalization',
        'original_decoder_profile_sha256': sha(original_decoder.canonical(original_decoder.profile_record())),
        'original_header_sha256': original_decoder.HEADER_SHA256,
        'original_header_byte_count': original_decoder.HEADER_BYTES,
        'point_in_time_proven': False, 'provider_route_admitted': False,
        'source_admission_granted': False, 'price_coverage_proven': False}


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'new_offline_full_catalog_schema_recovery_without_provider_contact',
        'previous_worker_sha256': PREVIOUS_WORKER_SHA256,
        'previous_pure_profile_sha256': sha(canonical(previous.profile_record())),
        'reused_pure_functions': ['_load_plain', '_catalog', '_catalog_unchanged', '_guard_fingerprint',
            'validate_summary_metadata_projection'],
        'original_shape_policy': original_shape_policy(),
        'original_shape_policy_sha256': sha(canonical(original_shape_policy())),
        'routes_profile_sha256': sha(canonical(routes.profile_record())),
        'new_summary_schema_required_before_metadata_projection': True,
        'projection_changes_only_schema_tags_and_removes_new_closed_observation_fields': True,
        'source_guard_and_decoder_unchanged': True, 'original_row_bytes_preserved': True,
        'normal_guard_return_required_before_private_return': True,
        'finite_failure_codes': sorted(FINITE), **FALSE_FLAGS}


def _prepare_bound(plain, stocks_raw, funds_raw, *, deadline):
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
        require(type(original_catalog) is decoder.PrivateOriginalTickerCatalog, 'original_catalog_type')
        original_rows = original_catalog.mapping_rows()
        require(type(original_rows) is tuple and len(original_rows) == original_receipt['csv_row_count'],
            'original_catalog_count')
        columns = original_catalog.columns
        require(routes.valid_original_columns(columns), 'original_columns')
        original_schema = {'schema': ORIGINAL_SCHEMA, 'column_count': len(columns),
            'ordered_column_names_sha256': sha(canonical(list(columns))),
            'legacy_known_name_set_equal': set(columns) == previous.routes.ORIGINAL_FIELDS,
            'required_identity_fields_present': True}
        source_digests = []
        for row in original_rows:
            remaining(deadline)
            source_digests.append(routes.original.source_row_digest(row))
        require(sha(decoder.canonical(source_digests)) == original_receipt['ordered_source_row_digests_sha256'],
            'original_catalog_digest')
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
    remaining(deadline)
    summary = {'schema': SCHEMA, 'input_binding': input_binding,
        'original_catalog_receipt': original_receipt, 'routing_summary': routing_summary,
        'original_schema': original_schema,
        'original_shape_policy_sha256': sha(canonical(original_shape_policy())),
        'private_frame_byte_count': len(raw), 'private_frame_sha256': sha(raw),
        'current_metadata': {table: {'byte_count': len(raw), 'sha256': sha(raw)}
            for table, raw in (('stocks', stocks_raw), ('funds', funds_raw))},
        'source_guard_receipt': {'schema': previous.GUARD_SCHEMA,
            'profile_sha256': sha(canonical(source_guard.profile_record())),
            'metadata_fields': list(source_guard.FIELDS), 'original_leaf_count': len(source_guard.LEAVES),
            'original_leaf_pins': [{'byte_count': len(raw), 'sha256': sha(raw)} for raw in original_raws],
            'source_endpoint_sha256': before, 'full_ten_field_endpoints_equal': True,
            'root_and_below_native_acl_xattr_checked': True, 'ancestors_identity_only': True,
            'guard_normal_return': True, 'continuous_integrity_proven': False,
            'historical_integrity_proven': False}, **FALSE_FLAGS}
    return validate_summary(summary), private_record


def prepare(stocks_raw, funds_raw, *, deadline):
    try:
        remaining(deadline)
        require(all(type(raw) is bytes and 0 < len(raw) <= MAX_METADATA_BYTES
            for raw in (stocks_raw, funds_raw)), 'metadata_bound')
        return _prepare_bound(_load_plain(deadline), stocks_raw, funds_raw, deadline=deadline)
    except Exception as error:
        raise Refused(_failure_code(error)) from None


def validate_summary(value):
    """Closed metadata projection; never invokes old prepare or any I/O."""
    try:
        keys = {'schema', 'input_binding', 'original_catalog_receipt', 'routing_summary',
            'current_metadata', 'source_guard_receipt', 'private_frame_byte_count', 'private_frame_sha256',
            'original_schema', 'original_shape_policy_sha256', *FALSE_FLAGS}
        require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
            and type(value['routing_summary']) is dict
            and value['routing_summary'].get('schema') == routes.SCHEMA, 'summary')
        require(value['original_shape_policy_sha256'] == sha(canonical(original_shape_policy())), 'shape_policy')
        observed = value['original_schema']
        require(type(observed) is dict and set(observed) == {'schema', 'column_count',
            'ordered_column_names_sha256', 'legacy_known_name_set_equal', 'required_identity_fields_present'}
            and observed['schema'] == ORIGINAL_SCHEMA and type(observed['column_count']) is int
            and observed['column_count'] == 28 and previous._hash(observed['ordered_column_names_sha256'])
            and type(observed['legacy_known_name_set_equal']) is bool
            and observed['required_identity_fields_present'] is True, 'original_schema')
        projected = {key: item for key, item in value.items()
            if key not in ('original_schema', 'original_shape_policy_sha256')}
        projected['schema'] = previous.SCHEMA
        projected['routing_summary'] = dict(projected['routing_summary'], schema=previous.routes.SCHEMA)
        checked = previous.validate_summary(projected)
        checked['schema'] = SCHEMA
        checked['routing_summary']['schema'] = routes.SCHEMA
        checked['original_schema'] = json.loads(canonical(observed))
        checked['original_shape_policy_sha256'] = value['original_shape_policy_sha256']
        require(len(canonical(checked)) <= MAX_SUMMARY_BYTES, 'summary')
        return checked
    except Exception as error:
        raise Refused(_failure_code(error)) from None
