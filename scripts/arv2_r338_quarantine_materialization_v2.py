"""Pure private R337 six-cell materialization for one PROPOSED existing project.

Project38522505 is a historical Analyst diagnostic project selected prospectively
for source binding ONLY. Nothing here verifies or changes its current cloud
files, ownership, privacy, permissions, objects, jobs or rights. Supplied input
commitments are checked structurally; physical authentication belongs to the
new caller's separately frozen held-DATA protocol. No I/O is performed here.
"""
import hashlib
import json
import math
import re
import time

from scripts import arv2_r337_quarantine_projection as projection
from scripts import arv2_r337_quarantine_preparation as retained
from scripts import arv2_r327_k_source_binding as k_anchor
from scripts import arv2_r298_ar_source_binding as ar_anchor

SCHEMA = 'arv2-r338-quarantine-materialization-v2'
BUNDLE_SCHEMA = SCHEMA + '-bundle'
MANIFEST_SCHEMA = SCHEMA + '-private-manifest'
PROPOSED_PROJECT_ID = 38522505
PROPOSED_PROJECT_PURPOSE = 'historical_Analyst_diagnostic_proposed_reuse_ONLY_no_current_cloud_verification'
CATALOG_PIN = {'byte_count': 6924, 'sha256': 'bebe830cba48c6eafb0c99c8feb4251c59871bb7a52f054327076d946d81bc94'}
ARCHIVE_PIN = {'byte_count': 148543046, 'sha256': '2a2815b543c41728b441b0b300a9d269f282778ef1915923fd68f61993f9ca1f'}
HEADER_PIN = {'byte_count': 11650, 'sha256': '2cda5157e4b305592568d71239ba613f8e452a43ac1507c8ee33b7ead2bd65fe'}
VENDOR_CATALOG_PIN = {'byte_count': 2224206, 'sha256': 'f55e44f85f39846f0b4946860318760eab68d10d95c79d2cf87da44ad9568cb1'}
VENDOR_MANIFEST_PIN = {'byte_count': 22373, 'sha256': 'cf9a27d0c6ccd8ad65b676c6335de35ac6738579e49784cb532d790cf83e7189'}
K_INPUT_BINDING = k_anchor.archive_output()['outcome']['result']['input_binding']
MAX_SECONDS = 300
MAX_OUTPUT_BYTES = 3 * 1024 * 1024
MAX_HEADER_BYTES = 65536
MAX_MANIFEST_BYTES = 128 * 1024
MAX_BINDINGS_BYTES = 12 * 1024 * 1024
MAX_FILE_COUNT = 42
MAGIC = b'ARV2-R338-QUARANTINE-SOURCES-V1\n'
FALSE_FLAGS = {name: False for name in (
    'QC_contact', 'Safari_access', 'provider_contact', 'credential_access',
    'physical_input_authentication_performed', 'fresh_QC_resolution_performed',
    'current_cloud_project_verified', 'current_cloud_source_verified',
    'current_cloud_objects_verified', 'current_cloud_access_or_privacy_verified',
    'QC_transfer_granted', 'QC_processing_rights_granted', 'current_capacity_verified',
    'individual_price_rows_parsed', 'complete_price_coverage_proven',
    'actual_target_or_holdings_path_proven', 'source_admission_granted',
    'strategy_result_accepted', 'point_in_time_proven', 'formal_identity_admitted',
    'formal_forward_ready', 'paper_or_live_ready', 'backtest_created',
    'old_operation_invoked', 'old_control_read', 'original_data_rewritten')}
FINITE = frozenset(('deadline', 'input_binding', 'axis', 'bindings', 'assignment',
    'catalog_pin', 'catalog', 'archive_pin', 'header_pin', 'archive', 'range_pin',
    'context', 'sources', 'projection', 'output', 'bundle', 'transport_nonce', 'bound', 'json', 'unknown'))


class Refused(ValueError):
    """Finite structural predicate; never identifiers, rows or raw exceptions."""


def require(value, code):
    if not value: raise Refused(code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
            allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError): raise Refused('json') from None


def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(canonical(value))
def pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}


def finite(error):
    if type(error) is TimeoutError: return 'deadline'
    for module in (projection, retained, retained.fmt):
        if type(error) is module.Refused:
            args = BaseException.args.__get__(error)
            if args == ('deadline',): return 'deadline'
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= MAX_SECONDS, 'deadline')


def loads(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'bound')
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'json'); result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
        require(canonical(value) == raw, 'json'); return value
    except Refused: raise
    except (TypeError, ValueError, UnicodeError, RecursionError): raise Refused('json') from None


def checked_pin(value, maximum):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= maximum
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'output')
    return value


def source_inventory(source_pairs):
    require(type(source_pairs) is tuple and len(source_pairs) == len(projection.HOST_SOURCE_PINS)
        and all(type(row) is tuple and len(row) == 2 and type(row[0]) is str and type(row[1]) is bytes
            for row in source_pairs)
        and tuple(name for name, _ in source_pairs) == tuple(sorted(projection.HOST_SOURCE_PINS)), 'sources')
    for name, raw in source_pairs:
        require(0 < len(raw) <= projection.MAX_HOST_BYTES and raw.isascii()
            and sha(raw) == projection.HOST_SOURCE_PINS[name], 'sources')
    return dict(source_pairs)


def validate_inputs(axis, bindings, input_binding, *, deadline):
    """Check supplied complete data commitments; perform no physical loading."""
    budget(deadline)
    require(type(input_binding) is dict and canonical(input_binding) == canonical(K_INPUT_BINDING), 'input_binding')
    expected = input_binding['binding_contract']
    require(type(axis) is tuple and len(axis) == input_binding['session_axis_count'] == 3466
        and digest(list(axis)) == input_binding['ordered_session_values_sha256'] == retained.fmt.FULL_AXIS_SHA256
        and axis[0] == input_binding['first_session'] and axis[-1] == input_binding['last_session'], 'axis')
    require(type(bindings) is tuple and len(bindings) == expected['binding_count'] == retained.fmt.STOCK_COUNT
        and len(canonical(bindings)) <= MAX_BINDINGS_BYTES, 'bindings')
    figi = projection.runtime.figi
    checked, ids, figis, semantics, stream = [], set(), set(), set(), hashlib.sha256()
    for row in bindings:
        budget(deadline)
        try: normalized = figi._input_row(row, expected['security_master_admission_sha256'])
        except Exception as error:
            if finite(error) == 'deadline': raise Refused('deadline') from None
            raise Refused('bindings') from None
        require(canonical(row) == canonical(normalized)
            and normalized['admitted_mapping_count'] == expected['binding_count']
            and normalized['admitted_mapping_inventory_sha256'] == expected['admitted_mapping_inventory_sha256']
            and normalized['security_id'] not in ids and normalized['composite_figi'] not in figis
            and normalized['row_sha256'] not in semantics
            and (not checked or checked[-1]['security_id'] < normalized['security_id']), 'bindings')
        ids.add(normalized['security_id']); figis.add(normalized['composite_figi'])
        semantics.add(normalized['row_sha256']); checked.append(normalized)
        # The genuine original stream is canonical JSONL, including each LF.
        stream.update(figi._canonical(normalized))
    require(stream.hexdigest() == expected['binding_stream_sha256'] == retained.fmt.BINDING_SHA256, 'bindings')
    budget(deadline); return tuple(checked)


def parse_archive(archive_raw, *, deadline):
    budget(deadline)
    require(type(archive_raw) is bytes and pin(archive_raw) == ARCHIVE_PIN, 'archive_pin')
    start = len(retained.MAGIC) + 8
    require(archive_raw.startswith(retained.MAGIC) and len(archive_raw) >= start, 'header_pin')
    size = int.from_bytes(archive_raw[len(retained.MAGIC):start], 'big')
    require(0 < size <= MAX_HEADER_BYTES and start + size < len(archive_raw)
        and pin(archive_raw[:start + size]) == HEADER_PIN, 'header_pin')
    try: vendor, manifest, descriptors = retained.parse_archive(archive_raw, deadline=deadline)
    except retained.Refused as error:
        raise Refused('deadline' if finite(error) == 'deadline' else 'archive') from None
    require({k: descriptors['catalog'][k] for k in ('byte_count', 'sha256')} == VENDOR_CATALOG_PIN
        and {k: descriptors['manifest'][k] for k in ('byte_count', 'sha256')} == VENDOR_MANIFEST_PIN, 'range_pin')
    # Independent retained AR range inventory, not expected_pin=pin(current_bytes).
    expected = ar_anchor.data_plan()
    require(set(expected) == set(descriptors) == set(retained.ROLES), 'range_pin')
    for role in retained.ROLES:
        budget(deadline)
        require({k: descriptors[role][k] for k in ('byte_count', 'sha256')}
            == {k: expected[role][k] for k in ('byte_count', 'sha256')}, 'range_pin')
    return vendor, manifest, descriptors


def make_context():
    return {'schema': retained.fmt.SCHEMA + '-QC-context', 'runtime_project_id': PROPOSED_PROJECT_ID,
        'manifest_pin': dict(VENDOR_MANIFEST_PIN), 'catalog_pin': dict(VENDOR_CATALOG_PIN),
        'object_key_prefix': str(PROPOSED_PROJECT_ID) + '/arv2/r326-common/' + VENDOR_MANIFEST_PIN['sha256'] + '/',
        'AP_fact_sha256': retained.fmt.AP_FACT_SHA256, 'AP_authentication_sha256': retained.fmt.AP_AUTH_SHA256}


def validate_assignments(rows, vendor, catalog, *, deadline):
    assignments = vendor['assignments'][:retained.fmt.STOCK_COUNT]
    require(len(assignments) == len(rows) == retained.fmt.STOCK_COUNT, 'assignment')
    for row, assigned in zip(rows, assignments, strict=True):
        budget(deadline)
        require(assigned['security_id'] == row['security_id'] and assigned['whole_binding_sha256'] == digest(row)
            and assigned['semantic_binding_sha256'] == row['row_sha256'], 'assignment')
    by_whole = {digest(row): row for row in rows}
    expected_wholes = retained.policy.QUARANTINED_WHOLE_BINDING_SHA256S
    require({row['whole_binding_sha256'] for row in assignments if row['role'] == retained.fmt.NATIVE}
        == set(expected_wholes), 'assignment')
    require(all(whole in by_whole for whole in expected_wholes)
        and canonical(tuple(by_whole[whole] for whole in expected_wholes))
        == canonical(catalog['quarantined_bindings']), 'catalog')


def _cell_prefix(size, arm): return 'cells/' + str(size) + '-ar' + str(arm) + '/'


def output_names():
    names = ['shared/' + name for name in projection.CLOUD_SOURCE_PINS]
    names.extend(_cell_prefix(size, arm) + name for size, arm in projection.CELL_ORDER
        for name in ('main.py', 'profile.json', 'projection.json'))
    names.extend(('family.json', 'vendor-context.json', 'input-binding.json',
        'quarantine-catalog.json', 'bundle-manifest.json'))
    return tuple(sorted(names))


def _files(outputs):
    return [{'relative_path': name, **pin(raw)} for name, raw in sorted(outputs.items())]


def _manifest(outputs, cells):
    logical = []
    for cell, (size, arm) in zip(cells, projection.CELL_ORDER, strict=True):
        prefix = _cell_prefix(size, arm)
        record = cell.to_record()
        logical.append({'universe_count': size, 'ar_percent': arm, 'candidate_id': record['candidate_id'],
            'profile_path': prefix + 'profile.json', 'projection_path': prefix + 'projection.json',
            'source_files': [{'project_path': name,
                'relative_path': prefix + name if name == 'main.py' else 'shared/' + name,
                **pin(raw)} for name, raw in cell.source_pairs]})
    return {'schema': MANIFEST_SCHEMA, 'research_epoch_id': projection.runtime.RESEARCH_EPOCH_ID,
        'proposed_runtime_project_id': PROPOSED_PROJECT_ID, 'proposed_project_purpose': PROPOSED_PROJECT_PURPOSE,
        'quarantine_policy_sha256': retained.policy.quarantine_policy_sha256(),
        'input_binding_sha256': digest(K_INPUT_BINDING), 'quarantine_catalog_pin': dict(CATALOG_PIN),
        'vendor_archive_pin': dict(ARCHIVE_PIN), 'vendor_archive_header_pin': dict(HEADER_PIN),
        'vendor_catalog_pin': dict(VENDOR_CATALOG_PIN), 'vendor_manifest_pin': dict(VENDOR_MANIFEST_PIN),
        'projection_builder_profile_sha256': digest(projection.profile_record()),
        'host_source_pins': dict(projection.HOST_SOURCE_PINS), 'cloud_non_main_source_pins': dict(projection.CLOUD_SOURCE_PINS),
        'logical_cells': logical, 'files': _files(outputs), 'proposed_context_only': True, **FALSE_FLAGS}


def _summary(outputs, cells):
    cell_pins = []
    for cell, (size, arm) in zip(cells, projection.CELL_ORDER, strict=True):
        prefix = _cell_prefix(size, arm); record = cell.to_record()
        cell_pins.append({'universe_count': size, 'ar_percent': arm,
            'candidate_id': record['candidate_id'], 'main_pin': pin(outputs[prefix + 'main.py']),
            'profile_pin': pin(outputs[prefix + 'profile.json']),
            'projection_pin': pin(outputs[prefix + 'projection.json'])})
    return {'schema': SCHEMA, 'research_epoch_id': projection.runtime.RESEARCH_EPOCH_ID,
        'proposed_runtime_project_id': PROPOSED_PROJECT_ID, 'proposed_project_purpose': PROPOSED_PROJECT_PURPOSE,
        'quarantine_policy_sha256': retained.policy.quarantine_policy_sha256(),
        'cell_order': [list(row) for row in projection.CELL_ORDER], 'cell_count': 6,
        'logical_source_files_per_cell': 20, 'shared_source_file_count': 19,
        'private_output_file_count': len(outputs), 'private_output_byte_count': sum(map(len, outputs.values())),
        'bundle_manifest_pin': pin(outputs['bundle-manifest.json']), 'family_record_pin': pin(outputs['family.json']),
        'vendor_context_pin': pin(outputs['vendor-context.json']), 'quarantine_catalog_pin': dict(CATALOG_PIN),
        'vendor_archive_pin': dict(ARCHIVE_PIN), 'vendor_archive_header_pin': dict(HEADER_PIN),
        'vendor_catalog_pin': dict(VENDOR_CATALOG_PIN), 'vendor_manifest_pin': dict(VENDOR_MANIFEST_PIN),
        'input_binding_sha256': digest(K_INPUT_BINDING), 'binding_stream_sha256': retained.fmt.BINDING_SHA256,
        'binding_count': retained.fmt.STOCK_COUNT, 'full_axis_count': 3466, 'full_axis_sha256': retained.fmt.FULL_AXIS_SHA256,
        'source_assignment_count': retained.fmt.STOCK_COUNT + retained.fmt.FUND_COUNT,
        'quarantine_join_count': 5, 'vendor_stock_count': retained.fmt.VENDOR_COUNT,
        'conditional_stock_count': retained.fmt.CONDITIONAL_COUNT, 'fund_count': retained.fmt.FUND_COUNT,
        'archive_range_count': 73, 'cells': cell_pins,
        'projection_builder_profile_sha256': digest(projection.profile_record()),
        'host_source_pins': dict(projection.HOST_SOURCE_PINS), 'cloud_non_main_source_pins': dict(projection.CLOUD_SOURCE_PINS),
        'all_six_share_exact_non_main': True, 'input_shape_and_commitments_validated': True,
        'all_archive_range_bytes_authenticated': True, 'proposed_context_only': True, **FALSE_FLAGS}


def prepare(source_pairs, *, axis, bindings, quarantine_catalog_raw, archive_raw, input_binding, deadline):
    """Return private deterministic byte buffers, never write or grant a run."""
    budget(deadline); source_inventory(source_pairs)
    rows = validate_inputs(axis, bindings, input_binding, deadline=deadline)
    require(type(quarantine_catalog_raw) is bytes and pin(quarantine_catalog_raw) == CATALOG_PIN, 'catalog_pin')
    try:
        catalog = retained.policy.validate_quarantine_catalog(loads(quarantine_catalog_raw, CATALOG_PIN['byte_count']),
            expected_sha256=CATALOG_PIN['sha256'])
    except retained.policy.NewruleError: raise Refused('catalog') from None
    vendor, _, _ = parse_archive(archive_raw, deadline=deadline)
    require(tuple(vendor['price_sessions']) == tuple(day for day in axis
        if retained.fmt.FIRST <= day <= retained.fmt.LAST), 'axis')
    validate_assignments(rows, vendor, catalog, deadline=deadline)
    context = make_context()
    try:
        batch = projection.prepare(source_pairs, expected_source_pins=dict(projection.HOST_SOURCE_PINS),
            session_axis=axis, quarantine_catalog=catalog, expected_quarantine_catalog_sha256=CATALOG_PIN['sha256'],
            runtime_project_id=PROPOSED_PROJECT_ID, vendor_source_context=context)
    except projection.Refused as error:
        raise Refused('deadline' if finite(error) == 'deadline' else 'projection') from None
    outputs = {'family.json': batch.record_bytes, 'vendor-context.json': canonical(context),
        'input-binding.json': canonical(input_binding), 'quarantine-catalog.json': quarantine_catalog_raw}
    outputs.update(('shared/' + name, raw) for name, raw in batch.cells[0].source_pairs if name != 'main.py')
    for cell, (size, arm) in zip(batch.cells, projection.CELL_ORDER, strict=True):
        prefix = _cell_prefix(size, arm)
        outputs.update({prefix + 'main.py': dict(cell.source_pairs)['main.py'],
            prefix + 'profile.json': cell.profile_bytes, prefix + 'projection.json': cell.record_bytes})
    outputs['bundle-manifest.json'] = canonical(_manifest(outputs, batch.cells))
    summary = _summary(outputs, batch.cells)
    validate_outputs(summary, outputs, source_pairs=source_pairs, deadline=deadline)
    budget(deadline); return summary, dict(sorted(outputs.items()))


def validate_summary(value):
    require(type(value) is dict, 'output')
    # Pins/counts depending on generated Main/profile bytes are checked here for
    # shape; validate_outputs binds their actual bytes and complete family.
    changing = {'private_output_byte_count', 'bundle_manifest_pin', 'family_record_pin',
        'vendor_context_pin', 'cells'}
    skeleton = {'schema': SCHEMA, 'research_epoch_id': projection.runtime.RESEARCH_EPOCH_ID,
        'proposed_runtime_project_id': PROPOSED_PROJECT_ID, 'proposed_project_purpose': PROPOSED_PROJECT_PURPOSE,
        'quarantine_policy_sha256': retained.policy.quarantine_policy_sha256(),
        'cell_order': [list(row) for row in projection.CELL_ORDER], 'cell_count': 6,
        'logical_source_files_per_cell': 20, 'shared_source_file_count': 19, 'private_output_file_count': MAX_FILE_COUNT,
        'quarantine_catalog_pin': dict(CATALOG_PIN), 'vendor_archive_pin': dict(ARCHIVE_PIN),
        'vendor_archive_header_pin': dict(HEADER_PIN), 'vendor_catalog_pin': dict(VENDOR_CATALOG_PIN),
        'vendor_manifest_pin': dict(VENDOR_MANIFEST_PIN), 'input_binding_sha256': digest(K_INPUT_BINDING),
        'binding_stream_sha256': retained.fmt.BINDING_SHA256, 'binding_count': retained.fmt.STOCK_COUNT,
        'full_axis_count': 3466, 'full_axis_sha256': retained.fmt.FULL_AXIS_SHA256,
        'source_assignment_count': retained.fmt.STOCK_COUNT + retained.fmt.FUND_COUNT, 'quarantine_join_count': 5,
        'vendor_stock_count': retained.fmt.VENDOR_COUNT, 'conditional_stock_count': retained.fmt.CONDITIONAL_COUNT,
        'fund_count': retained.fmt.FUND_COUNT, 'archive_range_count': 73,
        'projection_builder_profile_sha256': digest(projection.profile_record()),
        'host_source_pins': dict(projection.HOST_SOURCE_PINS), 'cloud_non_main_source_pins': dict(projection.CLOUD_SOURCE_PINS),
        'all_six_share_exact_non_main': True, 'input_shape_and_commitments_validated': True,
        'all_archive_range_bytes_authenticated': True, 'proposed_context_only': True, **FALSE_FLAGS}
    require(set(value) == set(skeleton) | changing
        and canonical({key: val for key, val in value.items() if key not in changing}) == canonical(skeleton), 'output')
    require(type(value['private_output_byte_count']) is int and 0 < value['private_output_byte_count'] <= MAX_OUTPUT_BYTES, 'bound')
    for name in ('bundle_manifest_pin', 'family_record_pin', 'vendor_context_pin'):
        checked_pin(value[name], MAX_MANIFEST_BYTES)
    require(type(value['cells']) is list and len(value['cells']) == 6, 'output')
    for row, (size, arm) in zip(value['cells'], projection.CELL_ORDER, strict=True):
        require(type(row) is dict and set(row) == {'universe_count', 'ar_percent', 'candidate_id',
            'main_pin', 'profile_pin', 'projection_pin'}
            and type(row['universe_count']) is type(row['ar_percent']) is int
            and (row['universe_count'], row['ar_percent']) == (size, arm)
            and row['candidate_id'] == projection.runtime.candidate_id(size, arm), 'output')
        for name, maximum in (('main_pin', projection.MAX_SOURCE_BYTES),
            ('profile_pin', projection.MAX_SOURCE_BYTES), ('projection_pin', projection.MAX_RECORD_BYTES)):
            checked_pin(row[name], maximum)
    return value


def _output_shape(outputs):
    require(type(outputs) is dict and all(type(name) is str for name in outputs)
        and tuple(sorted(outputs)) == output_names() and len(outputs) == MAX_FILE_COUNT,
        'output')
    require(all(type(name) is str and type(raw) is bytes and 0 < len(raw) <= MAX_MANIFEST_BYTES
        for name, raw in outputs.items()) and sum(map(len, outputs.values())) <= MAX_OUTPUT_BYTES, 'bound')


def validate_outputs(summary, outputs, *, source_pairs, deadline):
    budget(deadline); validate_summary(summary); _output_shape(outputs); sources = source_inventory(source_pairs)
    require(outputs['input-binding.json'] == canonical(K_INPUT_BINDING)
        and outputs['vendor-context.json'] == canonical(make_context())
        and pin(outputs['quarantine-catalog.json']) == CATALOG_PIN, 'output')
    cells = []
    for size, arm in projection.CELL_ORDER:
        budget(deadline); prefix = _cell_prefix(size, arm)
        pairs = tuple(sorted([(name, outputs['shared/' + name]) for name in projection.CLOUD_SOURCE_PINS]
            + [('main.py', outputs[prefix + 'main.py'])]))
        cell = projection.Cell(outputs[prefix + 'projection.json'], outputs[prefix + 'profile.json'],
            pairs, sources[projection.TEMPLATE_NAME])
        try:
            record = cell.to_record(); profile = loads(cell.profile_bytes, projection.MAX_SOURCE_BYTES)
            require(record['runtime_project_id'] == PROPOSED_PROJECT_ID
                and record['quarantine_catalog_sha256'] == CATALOG_PIN['sha256']
                and profile['vendor_source_context_sha256'] == digest(make_context()), 'context')
        except projection.Refused as error:
            raise Refused('deadline' if finite(error) == 'deadline' else 'projection') from None
        cells.append(cell)
    try: projection.Batch(outputs['family.json'], tuple(cells)).to_record()
    except projection.Refused as error:
        raise Refused('deadline' if finite(error) == 'deadline' else 'projection') from None
    without_manifest = {name: raw for name, raw in outputs.items() if name != 'bundle-manifest.json'}
    require(outputs['bundle-manifest.json'] == canonical(_manifest(without_manifest, cells))
        and canonical(summary) == canonical(_summary(outputs, cells)), 'output')
    budget(deadline); return summary


def checked_transport_nonce(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'transport_nonce')
    return value


def pack_outputs(outputs, *, transport_nonce):
    checked_transport_nonce(transport_nonce)
    _output_shape(outputs)
    entries, offset = [], 0
    for ordinal, (name, raw) in enumerate(sorted(outputs.items())):
        entries.append({'ordinal': ordinal, 'relative_path': name, 'offset': offset, **pin(raw)})
        offset += len(raw)
    header = canonical({'schema': BUNDLE_SCHEMA, 'file_count': len(entries), 'payload_byte_count': offset,
        'entries': entries, 'proposed_runtime_project_id': PROPOSED_PROJECT_ID,
        'transport_nonce': transport_nonce,
        'proposed_context_only': True, **FALSE_FLAGS})
    require(len(header) <= MAX_HEADER_BYTES and len(MAGIC) + 8 + len(header) + offset <= MAX_OUTPUT_BYTES, 'bound')
    return MAGIC + len(header).to_bytes(8, 'big') + header + b''.join(outputs[name] for name in sorted(outputs))


def validate_bundle(raw, *, expected_pin, summary, source_pairs, deadline):
    budget(deadline); checked_pin(expected_pin, MAX_OUTPUT_BYTES)
    require(type(raw) is bytes and pin(raw) == expected_pin, 'bundle')
    start = len(MAGIC) + 8
    require(raw.startswith(MAGIC) and len(raw) >= start, 'bundle')
    size = int.from_bytes(raw[len(MAGIC):start], 'big')
    require(0 < size <= MAX_HEADER_BYTES and start + size < len(raw), 'bundle')
    header = loads(raw[start:start + size], MAX_HEADER_BYTES); base = start + size
    require(type(header) is dict and set(header) == {'schema', 'file_count', 'payload_byte_count',
        'entries', 'proposed_runtime_project_id', 'proposed_context_only', 'transport_nonce', *FALSE_FLAGS}
        and header['schema'] == BUNDLE_SCHEMA and type(header['file_count']) is int
        and header['file_count'] == MAX_FILE_COUNT and type(header['payload_byte_count']) is int
        and header['payload_byte_count'] == len(raw) - base
        and type(header['proposed_runtime_project_id']) is int
        and header['proposed_runtime_project_id'] == PROPOSED_PROJECT_ID
        and header['proposed_context_only'] is True and all(header[key] is False for key in FALSE_FLAGS)
        and type(header['entries']) is list and len(header['entries']) == MAX_FILE_COUNT, 'bundle')
    checked_transport_nonce(header['transport_nonce'])
    outputs, offset = {}, 0
    for ordinal, (name, entry) in enumerate(zip(output_names(), header['entries'], strict=True)):
        budget(deadline)
        require(type(entry) is dict and set(entry) == {'ordinal', 'relative_path', 'offset', 'byte_count', 'sha256'}
            and type(entry['ordinal']) is int and entry['ordinal'] == ordinal and entry['relative_path'] == name
            and type(entry['offset']) is int and entry['offset'] == offset, 'bundle')
        expected = checked_pin({key: entry[key] for key in ('byte_count', 'sha256')}, MAX_MANIFEST_BYTES)
        end = base + offset + expected['byte_count']; require(end <= len(raw), 'bundle')
        body = raw[base + offset:end]; require(pin(body) == expected, 'bundle')
        outputs[name] = body; offset += len(body)
    require(base + offset == len(raw), 'bundle')
    # Every range is authenticated before any Main/profile/private JSON parse.
    validate_outputs(summary, outputs, source_pairs=source_pairs, deadline=deadline)
    return outputs


def profile_record():
    return {'schema': SCHEMA, 'bundle_schema': BUNDLE_SCHEMA, 'private_manifest_schema': MANIFEST_SCHEMA,
        'proposed_runtime_project_id': PROPOSED_PROJECT_ID, 'proposed_project_purpose': PROPOSED_PROJECT_PURPOSE,
        'quarantine_catalog_pin': dict(CATALOG_PIN), 'vendor_archive_pin': dict(ARCHIVE_PIN),
        'vendor_archive_header_pin': dict(HEADER_PIN), 'vendor_catalog_pin': dict(VENDOR_CATALOG_PIN),
        'vendor_manifest_pin': dict(VENDOR_MANIFEST_PIN), 'complete_K_input_binding': json.loads(canonical(K_INPUT_BINDING)),
        'projection_profile_sha256': digest(projection.profile_record()),
        'host_source_pins': dict(projection.HOST_SOURCE_PINS), 'cloud_non_main_source_pins': dict(projection.CLOUD_SOURCE_PINS),
        'maximum_seconds': MAX_SECONDS, 'maximum_private_bundle_bytes': MAX_OUTPUT_BYTES,
        'maximum_header_bytes': MAX_HEADER_BYTES, 'private_output_file_count': MAX_FILE_COUNT,
        'output_names': list(output_names()), 'logical_source_files_per_cell': 20,
        'archive': 'externally_pinned_whole_header_all73_ranges_and_independent_retained_AR_pins_before_semantics',
        'archive_header_pin_scope': 'full_original_MAGIC_plus_8byte_big_endian_JSON_length_plus_canonical_JSON_frame_not_JSON_only',
        'input': 'supplied_complete_commitments_axis_and_all6151_original_bindings_not_physical_authentication',
        'private_output': 'immutable_byte_buffers_only_parent_owns_claim_guard_normal_return_and_publication',
        'private_transport_blinding': 'mandatory_64lowerhex_nonce_in_container_header_only_parent_fresh32randombytes_after_claim_and_marker_not_published',
        'source_buffers_deterministic': True,
        'coverage_join': 'separate_actual_coverage_must_match_same_input_catalog_archive_axis_and_all_six_cell_order',
        'current_cloud': 'all_current_access_privacy_objects_source_rights_and_run_gates_remain_pending',
        **FALSE_FLAGS}
