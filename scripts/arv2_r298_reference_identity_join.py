"""Pure bounded witness join against a genuine current-vintage input catalog.

No filesystem, credentials, provider, QC or operational entrypoint exists.
The native caller owns fresh admission/reconstruction before and after this
in-memory join. A hash match identifies an admitted current-vintage catalog
row, not a historical symbol, permanent mapping, price repair or permission.
No raw identity, display locator or catalog row leaves this helper.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

from scripts import arv2_r298_launch_admission as admission
from scripts import arv2_newrule_reference_identity_projection as witness
from research.analyst_revisions_v2_qc import newrule_plain_transport as transport
from research.analyst_revisions_v2_qc import newrule_plain_projection as bridge
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_qc_figi as figi
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_rating_evaluator as evaluator
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as legacy


SCHEMA = 'arv2-r298-reference-identity-join-v1'
WITNESS_SCHEMA = 'arv2-missing-reference-identity-v1'
FIELD_SCHEMA = 'arv2-reference-identity-field-v1'
MAX_BINDINGS, MAX_WITNESSES = 100000, 16
MAX_ROW_BYTES, MAX_MANIFEST_BYTES = 65536, 1024 * 1024
SELECTED_ROLES = ('evaluator_manifest', 'session_axis', 'runtime_symbol_bindings')
FALSE_FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False,
    'permanent_mapping_proven': False, 'historical_ticker_mapping_proven': False,
    'qc_sid_available': False, 'isin_available': False, 'permaticker_available': False,
    'provider_route_admitted': False, 'provider_contact': False,
    'source_repair_performed': False, 'sizing_repaired': False,
    'raw_identity_disclosed': False, 'raw_catalog_row_disclosed': False,
    'synthetic_readiness_proven': False, 'operational_authority': False}
FINITE = frozenset(('plain_authority', 'plain_binding', 'public_admission',
    'projection_binding', 'context', 'witness_scope', 'stream_inventory',
    'stream_bound', 'stream_json', 'manifest', 'calendar', 'catalog',
    'catalog_row', 'catalog_duplicate', 'witness_unmatched', 'witness_ambiguous',
    'plain_changed', 'receipt'))
canonical, sha = transport.canonical, transport.sha


class Refused(ValueError):
    """Finite predicate only, never a row, symbol, provider message or cause."""


def require(condition, code):
    if not condition:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown'


def _hash(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
        'receipt')
    return value


def profile_record():
    return {'schema': SCHEMA, 'witness_schema': WITNESS_SCHEMA,
        'field_hash_schema': FIELD_SCHEMA, 'max_witnesses': MAX_WITNESSES,
        'max_binding_rows': MAX_BINDINGS, 'max_objects': transport.MAX_OBJECTS,
        'max_total_bytes': transport.MAX_TOTAL_BYTES,
        'max_row_shard_bytes': transport.MAX_ROW_SHARD_BYTES,
        'max_row_bytes': MAX_ROW_BYTES, 'max_manifest_bytes': MAX_MANIFEST_BYTES,
        'max_session_rows': evaluator.MAX_SESSION_COUNT,
        'selected_roles': list(SELECTED_ROLES),
        'context_hash_encoding': 'canonical_ASCII_JSON_without_LF',
        'witness_fields': ['schema', 'security_id', 'reference_session', 'decision_session'],
        'genuine_plain_registry_and_pid_required': True,
        'old_public_admission_required': True,
        'native_caller_owns_fresh_private_admission_and_postcheck': True,
        'current_ticker_is_display_only': True, 'sid_date_is_listing_proof': False,
        'receipt_is_operational_capability': False, **FALSE_FLAGS}


def _context(value):
    try:
        checked = witness.validate_complete_witness(value)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Refused('context') from None
    require(type(checked) is dict and checked.get('witness_status') == 'complete'
        and type(checked.get('witnesses')) is list
        and 1 <= len(checked['witnesses']) <= MAX_WITNESSES
        and all(row['kind'] == 'stock' for row in checked['witnesses']), 'witness_scope')
    return checked


def context_digest(value):
    """Complete v2 context identity; deliberately no terminating LF."""
    return sha(canonical(_context(value)))


def _json(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum and raw.endswith(b'\n'),
        'stream_bound')
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=transport._pairs)
        require(type(value) is dict and canonical(value) + b'\n' == raw, 'stream_json')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refused('stream_json') from None
    return value


def _plain(value):
    try:
        transport.require_plain_transport(value)
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise Refused('plain_authority') from None
    initial = transport._fingerprint(value)
    try:
        record, inventory = bridge._plain_binding(value)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise Refused('plain_binding') from None
    return initial, record, inventory


def _public(packet, plain, transport_record, inventory):
    try:
        raw, pairs = admission.validate_packet(packet)
        record = json.loads(raw)
        files = dict(pairs)
        tree = ast.parse(files['main.py'])
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == 'NewruleComparisonDriver']
        require(len(calls) == 1, 'projection_binding')
        keys = {item.arg: item for item in calls[0].keywords}
        require(len(keys) == len(calls[0].keywords), 'projection_binding')
        profile = ast.literal_eval(keys['profile'].value)
        require(type(profile) is dict and record['profile_sha256'] == profile['profile_sha256']
            and record['package_sha256'] == profile['package_sha256'] == plain.package_sha256
            and record['lineage_sha256'] == profile['lineage_sha256'] == plain.source_lineage_sha256
            and record['activation_manifest_key'] == plain.activation_manifest_key
            and record['activation_manifest_sha256'] == plain.activation_manifest_sha256
            and record['activation_manifest_byte_count'] == plain.activation_manifest_byte_count
            and canonical(record['upload_inventory']) == canonical(inventory)
            and record['upload_inventory_sha256'] == sha(canonical(inventory))
            and record['total_upload_byte_count'] == plain.total_upload_byte_count
            and record['bridge']['parent_proof_sha256'] == plain.parent_proof_sha256,
            'projection_binding')
        seed = dict(profile)
        declared = seed.pop('profile_sha256')
        require(legacy._sha(seed) == declared and profile['universe_count'] == 6
            and profile['ar_percent'] == 0, 'projection_binding')
        for key, expected in (('activation_manifest_key', plain.activation_manifest_key),
                ('activation_manifest_sha256', plain.activation_manifest_sha256),
                ('activation_manifest_byte_count', plain.activation_manifest_byte_count)):
            require(ast.literal_eval(keys[key].value) == expected, 'projection_binding')
        require(transport_record['source_disposition_sha256'] == profile['lineage_sha256'],
            'projection_binding')
    except Refused:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, SyntaxError, RecursionError):
        raise Refused('public_admission') from None
    return raw, record, profile


def _streams(plain, record):
    selected = {role: [] for role in SELECTED_ROLES}
    positions = {role: [] for role in transport.ROLES}
    order = []
    binding_digest = hashlib.sha256()
    binding_count = 0
    try:
        for descriptor, raw in transport.iter_plain_upload_objects(plain):
            if descriptor.activation_manifest:
                continue
            require(descriptor.role in positions and type(descriptor.ordinal) is int
                and descriptor.ordinal == len(positions[descriptor.role])
                and type(descriptor.record_count) is int and descriptor.record_count > 0,
                'stream_inventory')
            positions[descriptor.role].append(descriptor.ordinal)
            order.append(descriptor.role)
            if descriptor.role not in selected:
                continue  # No contribution/membership row is parsed or cataloged.
            require(len(raw) <= (MAX_MANIFEST_BYTES if descriptor.role == 'evaluator_manifest'
                else transport.MAX_ROW_SHARD_BYTES), 'stream_bound')
            if descriptor.role == 'evaluator_manifest':
                require(descriptor.ordinal == 0 and descriptor.record_count == 1,
                    'stream_inventory')
                rows = [_json(raw, MAX_MANIFEST_BYTES)]
            else:
                limit = evaluator.MAX_SESSION_COUNT if descriptor.role == 'session_axis' else MAX_BINDINGS
                require(len(selected[descriptor.role]) + descriptor.record_count <= limit,
                    'stream_bound')
                lines = raw.splitlines(keepends=True)
                require(len(lines) == descriptor.record_count, 'stream_inventory')
                rows = [_json(line, MAX_ROW_BYTES) for line in lines]
            selected[descriptor.role].extend(rows)
            if descriptor.role == 'runtime_symbol_bindings':
                binding_digest.update(raw)
                binding_count += descriptor.record_count
        require(positions['evaluator_manifest'] == [0]
            and all(values for values in positions.values())
            and order == [role for role in transport.ROLES for _ in positions[role]],
            'stream_inventory')
        require(type(record['runtime_symbol_binding_count']) is int
            and 1 <= record['runtime_symbol_binding_count'] <= MAX_BINDINGS
            and binding_count == record['runtime_symbol_binding_count']
            and binding_digest.hexdigest() == record['runtime_symbol_bindings_sha256'], 'catalog')
    except Refused:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise Refused('plain_changed') from None
    return selected


def _manifest(value, record):
    require(type(value) is dict and set(value) == set(evaluator._MANIFEST_FIELDS), 'manifest')
    seed = dict(value)
    digest, identity = seed.pop('manifest_sha256'), seed.pop('manifest_id')
    require(type(digest) is str and digest == legacy._sha(seed)
        and digest == record['evaluator_manifest_sha256']
        and type(identity) is str and identity == 'arv2-preliminary-rating-manifest-' + digest[:24]
        and identity == record['evaluator_manifest_id'], 'manifest')
    lineage = value.get('source_lineage_sha256s')
    require(type(lineage) is dict and 'security_master_admission_sha256' in lineage, 'manifest')
    return _hash(lineage['security_master_admission_sha256'])


def _calendar(rows, manifest, profile, context):
    try:
        axis = evaluator._parse_sessions(tuple(rows))
        require(manifest['session_axis_count'] == len(axis)
            and evaluator._stream_sha256(tuple(rows)) == manifest['session_axis_sha256']
            and legacy._sha(list(axis)) == profile['session_axis_sha256']
            == context['session_axis_sha256'], 'calendar')
        position = axis.index(context['decision_session'])
        require(position > 0 and axis[position - 1] == context['reference_session']
            and context['decision_time'] == '09:20'
            and context['decision_session'] in profile['decision_sessions'], 'calendar')
    except Refused:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise Refused('calendar') from None


def _field(name, value):
    return legacy._sha({'schema': FIELD_SCHEMA, 'field': name, 'value': value})


def join(plain, context, old_packet):
    """Join all complete dated witnesses, or refuse without a partial route."""
    checked = _context(context)
    context_pin = context_digest(checked)
    initial, record, inventory = _plain(plain)
    raw, projected, profile = _public(old_packet, plain, record, inventory)
    packet_pin = sha(canonical(old_packet))
    selected = _streams(plain, record)
    manifest = selected['evaluator_manifest'][0]
    admission_pin = _manifest(manifest, record)
    _calendar(selected['session_axis'], manifest, profile, checked)
    targets = {row['identity_sha256']: row for row in checked['witnesses']}
    matches, identities, figis, row_pins = {}, set(), set(), set()
    last = None
    for source in selected['runtime_symbol_bindings']:
        try:
            row = figi._input_row(source, admission_pin)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise Refused('catalog_row') from None
        identity = row['security_id']
        require((last is None or last < identity) and identity not in identities
            and row['composite_figi'] not in figis and row['row_sha256'] not in row_pins,
            'catalog_duplicate')
        last = identity
        identities.add(identity); figis.add(row['composite_figi']); row_pins.add(row['row_sha256'])
        require(row['admitted_mapping_count'] == len(selected['runtime_symbol_bindings']), 'catalog')
        digest = legacy._sha({'schema': WITNESS_SCHEMA, 'security_id': identity,
            'reference_session': checked['reference_session'], 'decision_session': checked['decision_session']})
        if digest not in targets:
            continue
        require(digest not in matches, 'witness_ambiguous')
        matches[digest] = {'identity_sha256': digest, **{key: targets[digest][key]
            for key in ('holding', 'kind', 'sid_date')},
            'binding_row_sha256': row['row_sha256'], 'whole_binding_row_sha256': legacy._sha(row),
            **{key: row[key] for key in ('source_row_sha256', 'identity_evidence_sha256',
                'security_master_admission_sha256', 'admitted_mapping_inventory_sha256')},
            **{key + '_sha256': _field(key, row[key]) for key in ('composite_figi', 'issuer_id',
                'listing_id', 'diagnostic_current_ticker', 'diagnostic_exchange_mic',
                'candidate_first_session', 'candidate_last_session', 'source_snapshot_available_at')}}
    require(set(matches) == set(targets), 'witness_unmatched')
    require(len({row['admitted_mapping_inventory_sha256'] for row in selected['runtime_symbol_bindings']}) == 1,
        'catalog')
    try:
        transport.require_plain_transport(plain)
        require(transport._fingerprint(plain) == initial, 'plain_changed')
        require(context_digest(context) == context_pin and sha(canonical(old_packet)) == packet_pin,
            'plain_changed')
    except Refused:
        raise
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise Refused('plain_changed') from None
    receipt = {'schema': SCHEMA, 'status': 'complete_current_vintage_catalog_match',
        'context_sha256': context_pin, 'public_admission_packet_sha256': packet_pin,
        'old_projection_sha256': sha(raw), 'old_profile_sha256': profile['profile_sha256'],
        'source_pins_sha256': legacy._sha(profile['source_pins']),
        'source_package_sha256': plain.source_package_sha256,
        'source_lineage_sha256': plain.source_lineage_sha256,
        'plain_package_sha256': plain.package_sha256,
        'activation_manifest_sha256': plain.activation_manifest_sha256,
        'parent_proof_sha256': plain.parent_proof_sha256,
        'upload_inventory_sha256': projected['upload_inventory_sha256'],
        'evaluator_manifest_sha256': record['evaluator_manifest_sha256'],
        'security_master_admission_sha256': admission_pin,
        'catalog_sha256': record['runtime_symbol_bindings_sha256'],
        'session_axis_sha256': profile['session_axis_sha256'],
        'd2_receipt_sha256': legacy._sha(old_packet['storage_receipt']),
        'a11_report_sha256': old_packet['readiness_pin']['sha256'],
        'catalog_row_count': len(selected['runtime_symbol_bindings']),
        'witness_count': len(targets), 'matched_count': len(matches),
        'matches': [matches[key] for key in sorted(matches)],
        'owner_accepted_current_snapshot_risk': True,
        'current_vintage_display_metadata_only': True,
        'calendar_matches_pinned_input_not_independent_exchange_proof': True,
        **FALSE_FLAGS}
    return validate_receipt(receipt)


TOP_HASHES = ('context_sha256', 'public_admission_packet_sha256', 'old_projection_sha256',
    'old_profile_sha256', 'source_pins_sha256', 'source_package_sha256',
    'source_lineage_sha256', 'plain_package_sha256', 'activation_manifest_sha256',
    'parent_proof_sha256', 'upload_inventory_sha256', 'evaluator_manifest_sha256',
    'security_master_admission_sha256', 'catalog_sha256', 'session_axis_sha256',
    'd2_receipt_sha256', 'a11_report_sha256')
MATCH_HASHES = ('identity_sha256', 'binding_row_sha256', 'whole_binding_row_sha256',
    'source_row_sha256', 'identity_evidence_sha256', 'security_master_admission_sha256',
    'admitted_mapping_inventory_sha256', 'composite_figi_sha256', 'issuer_id_sha256',
    'listing_id_sha256', 'diagnostic_current_ticker_sha256', 'diagnostic_exchange_mic_sha256',
    'candidate_first_session_sha256', 'candidate_last_session_sha256',
    'source_snapshot_available_at_sha256')
TRUE_FLAGS = ('owner_accepted_current_snapshot_risk', 'current_vintage_display_metadata_only',
    'calendar_matches_pinned_input_not_independent_exchange_proof')


def validate_receipt(value):
    """Validate only a closed redacted result, never mint source authority."""
    fields = {'schema', 'status', *TOP_HASHES, 'catalog_row_count', 'witness_count',
        'matched_count', 'matches', *TRUE_FLAGS, *FALSE_FLAGS}
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == fields, 'receipt')
    require(type(value['schema']) is str and value['schema'] == SCHEMA
        and type(value['status']) is str and value['status'] == 'complete_current_vintage_catalog_match'
        and type(value['catalog_row_count']) is int and 1 <= value['catalog_row_count'] <= MAX_BINDINGS
        and type(value['witness_count']) is int and 1 <= value['witness_count'] <= MAX_WITNESSES
        and type(value['matched_count']) is int and value['matched_count'] == value['witness_count']
        and value['matched_count'] <= value['catalog_row_count']
        and type(value['matches']) is list and len(value['matches']) == value['matched_count']
        and all(value[key] is True for key in TRUE_FLAGS)
        and all(value[key] is False for key in FALSE_FLAGS), 'receipt')
    for key in TOP_HASHES: _hash(value[key])
    seen = []
    for row in value['matches']:
        require(type(row) is dict and all(type(key) is str for key in row)
            and set(row) == {*MATCH_HASHES, 'holding', 'kind', 'sid_date'}, 'receipt')
        for key in MATCH_HASHES: _hash(row[key])
        require(type(row['holding']) is str and row['holding'] in ('held', 'unheld_target', 'unknown')
            and type(row['kind']) is str and row['kind'] == 'stock'
            and type(row['sid_date']) is str and row['sid_date'] in (
                'on_or_before_reference', 'after_reference_through_decision', 'after_decision', 'unknown')
            and row['security_master_admission_sha256'] == value['security_master_admission_sha256'],
            'receipt')
        seen.append(row['identity_sha256'])
    require(seen == sorted(set(seen)), 'receipt')
    return {**value, 'matches': [dict(row) for row in value['matches']]}


verify = join
join_validate = validate_receipt
