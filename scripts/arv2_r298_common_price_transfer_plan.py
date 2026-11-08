"""Pure fixed AR-to-private-QC transfer plan; no operational capability.

Supplied validated descriptors and external process facts are data bindings,
not upload permission. A new exact caller must prove current access/rights,
held source bytes, absence, attempt and transport gates before any contact.
"""
from datetime import datetime, timedelta
import json
import re
from types import SimpleNamespace

from scripts import prepare_arv2_r298_common_price_sidecar_v2 as sidecar
from research.analyst_revisions_v2_qc import newrule_common_price_format as fmt

SCHEMA = 'arv2-r326-common-price-transfer-plan-v2'
AR_SCHEMA = 'arv2-r298-offline-common-price-sidecar-ar-v2'
AR_DIRECTORY = 'artifacts/analyst_revisions_v2/newrule_common_price_sidecar/R326-20261027-AR'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
OBJECT_COUNT, MAX_TOTAL_BYTES = 73, fmt.MAX_TOTAL_BYTES + fmt.MAX_CATALOG_BYTES + fmt.MAX_MANIFEST_BYTES
FALSE_FLAGS = {'QC_contact': False, 'credential_access': False, 'private_DATA_read': False,
    'QC_transfer_granted': False, 'current_org_access_proven': False, 'current_paid_rights_proven': False,
    'current_storage_capacity_proven': False, 'properties_is_remote_SHA256_proof': False,
    'remote_durability_proven': False, 'source_admission_granted': False,
    'price_input_admitted': False, 'point_in_time_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'source_upload_or_compile_or_backtest_granted': False}
FINITE = frozenset(('binding', 'actual', 'output', 'source', 'project', 'organization', 'inventory', 'bound', 'unknown'))
canonical, sha, digest = fmt.canonical, fmt.sha, fmt.digest


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _binding(value):
    require(type(value) is dict and set(value) == {'schema', 'expected_head', 'caller_sha256', 'profile_sha256'}
        and sidecar.SCHEMA == AR_SCHEMA and value['schema'] == AR_SCHEMA and type(value['expected_head']) is str
        and re.fullmatch('[0-9a-f]{40}', value['expected_head'])
        and all(fmt.hash_string(value[key]) and value[key] != '0' * 64 for key in ('caller_sha256', 'profile_sha256')),
        'binding')
    return json.loads(canonical(value))


def _actual(value, expected_raw):
    keys = {'actual_exit', 'bound', 'spawn_observed', 'dispatched_at', 'completion_observed_at',
        'stdout_bytes', 'stdout_sha256', 'stderr_bytes', 'stderr_sha256'}
    require(type(value) is dict and set(value) == keys and type(value['actual_exit']) is int
        and value['actual_exit'] == 0 and value['bound'] is None and value['spawn_observed'] is True
        and type(value['stdout_bytes']) is int and value['stdout_bytes'] == len(expected_raw)
        and value['stdout_sha256'] == sha(expected_raw) and type(value['stderr_bytes']) is int
        and value['stderr_bytes'] == 0 and value['stderr_sha256'] == sha(b''), 'actual')
    for field in ('dispatched_at', 'completion_observed_at'):
        require(type(value[field]) is str and 20 <= len(value[field]) <= 40
            and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)', value[field]), 'actual')
    try:
        first, last = (datetime.fromisoformat(value[field].replace('Z', '+00:00'))
            for field in ('dispatched_at', 'completion_observed_at'))
        require(first.utcoffset() == last.utcoffset() == timedelta(0) and first <= last, 'actual')
    except (ValueError, TypeError): raise Refused('actual') from None
    return first, last


def make_plan(validated_AR_output, *, producer_actual, validator_actual, frozen_AR_binding,
              project_id, organization_sha256):
    """Derive exactly 73 data-only objects from supplied authenticated metadata.

    This revalidates all supplied shapes and joins; it performs no file read,
    claim, credential access, current account check or application dispatch.
    """
    binding = _binding(frozen_AR_binding)
    require(type(project_id) is int and 0 < project_id <= 2147483647, 'project')
    require(type(organization_sha256) is str and organization_sha256 == ORGANIZATION_SHA256, 'organization')
    require(type(validated_AR_output) is dict and set(validated_AR_output) == {'binding', 'outcome'}
        and validated_AR_output['binding'] == binding, 'output')
    raw = canonical(validated_AR_output) + b'\n'
    require(0 < len(raw) <= sidecar.MAX_OUTPUT, 'bound')
    _, produced = _actual(producer_actual, raw); validated, _ = _actual(validator_actual, raw)
    require(produced <= validated, 'actual')
    args = SimpleNamespace(expected_head=binding['expected_head'], caller_sha256=binding['caller_sha256'],
        profile_sha256=binding['profile_sha256'])
    try:
        checked = sidecar.validate_output(raw, 0, args)
        result = checked['outcome']['result']
        manifest = sidecar._descriptor_manifest(result['manifest_descriptor'])
        fmt.validate_manifest(manifest)
    except Exception: raise Refused('source') from None
    manifest_pin = result['output_receipt']['manifest_pin']; catalog_pin = manifest['catalog_pin']
    prefix = str(project_id) + '/arv2/r326-common/' + manifest_pin['sha256'] + '/'
    rows = []
    def add(role, source_name, remote_name, payload_pin, maximum, month=None):
        try: fmt.validate_pin(payload_pin, maximum)
        except Exception: raise Refused('bound') from None
        rows.append({'ordinal': len(rows), 'role': role, 'month_ordinal': month,
            'relative_path': AR_DIRECTORY + '/' + source_name, 'object_store_key': prefix + remote_name,
            'byte_count': payload_pin['byte_count'], 'sha256': payload_pin['sha256']})
    add('catalog', 'catalog-private.json', 'catalog.json', catalog_pin, fmt.MAX_CATALOG_BYTES)
    for index, row in enumerate(manifest['months']):
        require(type(row['month_ordinal']) is int and row['month_ordinal'] == index, 'inventory')
        payload_pin = {key: row[key] for key in ('byte_count', 'sha256')}
        add('month', 'month-' + format(index, '03d') + '.jsonl',
            'month-' + format(index, '02d') + '-' + row['sha256'] + '.jsonl', payload_pin, fmt.MAX_MONTH_BYTES, index)
    add('manifest', 'manifest-private.json', 'manifest.json', manifest_pin, fmt.MAX_MANIFEST_BYTES)
    require(len(rows) == OBJECT_COUNT and rows[-1]['role'] == 'manifest'
        and len({row['relative_path'] for row in rows}) == len({row['object_store_key'] for row in rows}) == OBJECT_COUNT
        and sum(row['byte_count'] for row in rows if row['role'] == 'month') == manifest['total_shard_bytes']
        and sum(row['byte_count'] for row in rows) <= MAX_TOTAL_BYTES, 'inventory')
    plan = {'schema': SCHEMA, 'project_id': project_id, 'organization_sha256': organization_sha256,
        'AR_binding': binding, 'AR_producer_actual': producer_actual, 'AR_validator_actual': validator_actual,
        'AR_report_pin': checked['outcome']['report'], 'AR_result_sha256': digest(result),
        'AP_fact_sha256': fmt.AP_FACT_SHA256, 'AP_source_sha256': fmt.AP_SOURCE_SHA256,
        'AP_authentication_sha256': fmt.AP_AUTH_SHA256, 'original_binding_stream_sha256': fmt.BINDING_SHA256,
        'original_full_axis_sha256': fmt.FULL_AXIS_SHA256, 'source_guard_receipt_sha256': digest(result['source_guard_receipt']),
        'format_profile_sha256': digest(fmt.profile_record()), 'codec_profile_sha256': digest(sidecar.codec.profile_record()),
        'manifest_pin': manifest_pin, 'catalog_pin': catalog_pin, 'object_key_prefix': prefix,
        'objects': rows, 'object_inventory_sha256': digest(rows), 'object_count': OBJECT_COUNT,
        'total_byte_count': sum(row['byte_count'] for row in rows),
        'source_grid': {'original_stock_assignments': 6151, 'funds': 8, 'vendor_stock_assignments': 5636,
            'native_assignments': 5, 'conditional_assignments': 510, 'sessions': 1452,
            'positive_cells': 5541040, 'explicit_absent_cells': 2654048},
        'permitted_future_storage_endpoints': ['object/properties', 'object/set'],
        'properties_initial_recheck_put_verify_maximum_dispatches': 4 * OBJECT_COUNT,
        'initial_key_policy': 'every_exact_key_must_be_known_absent_no_overwrite_or_resume',
        'manifest_publication_order': 'last_after_catalog_and_all71months_verified',
        'properties_evidence': 'bounded_metadata_not_remote_SHA_or_independent_durability',
        'no_retry_or_cleanup_or_delete_or_object_get': True, **FALSE_FLAGS}
    # The returned structure is fresh, closed public metadata. No catalog,
    # source assignment, ticker, licensed price or row enters the plan.
    return json.loads(canonical(plan))


def profile_record():
    return {'schema': SCHEMA, 'AR_schema': AR_SCHEMA, 'AR_DATA_directory': AR_DIRECTORY,
        'organization_sha256': ORGANIZATION_SHA256, 'objects': OBJECT_COUNT,
        'monthly_bytes_maximum': fmt.MAX_MONTH_BYTES, 'shard_total_bytes_maximum': fmt.MAX_TOTAL_BYTES,
        'catalog_bytes_maximum': fmt.MAX_CATALOG_BYTES, 'manifest_bytes_maximum': fmt.MAX_MANIFEST_BYTES,
        'total_bytes_maximum': MAX_TOTAL_BYTES, 'AP_fact_sha256': fmt.AP_FACT_SHA256,
        'binding_is_not_an_operation_grant': True, 'no_I_O_or_operational_entrypoint': True, **FALSE_FLAGS}
