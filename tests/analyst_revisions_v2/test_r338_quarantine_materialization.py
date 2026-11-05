"""Supplied synthetic data/public code; no actual artifacts or operations."""
import ast
import copy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import arv2_r338_quarantine_materialization as m
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as calendar

PUBLIC = Path(__file__).resolve().parents[2] / 'research' / 'analyst_revisions_v2_qc'
NONCE = '13' * 32


def deadline(): return time.monotonic() + 299


def binding(index):
    figi = m.projection.runtime.figi
    token = 'BBG' + str(index).zfill(9)
    return figi.build_preliminary_qc_figi_binding(
        security_id='sharadar-composite-figi-' + token, issuer_id=f'SYNTHETIC-ISSUER-{index}',
        composite_figi=token, listing_id=f'SYNTHETIC-LISTING-{index}',
        diagnostic_current_ticker=f'SYNTH{index}', diagnostic_exchange_mic='XNYS',
        candidate_first_session='2020-12-31', candidate_last_session='2026-10-13',
        source_snapshot_available_at='2026-10-01T00:00:00.000000Z',
        source_row_sha256=m.sha(f'SYNTHETIC-SOURCE-{index}'.encode()),
        identity_evidence_sha256=m.sha(f'SYNTHETIC-EVIDENCE-{index}'.encode()),
        security_master_admission_sha256=m.retained.policy.ADMISSION_SHA256,
        admitted_mapping_inventory_sha256='b' * 64, admitted_mapping_count=6151)


@pytest.fixture(scope='module')
def case():
    # Full-size synthetic original census. No actual identifiers or source
    # prices are read; expected private pins are replaced only in memory.
    rows = tuple(binding(i) for i in range(6151))
    stream = m.sha(b''.join(m.projection.runtime.figi._canonical(row) for row in rows))
    wholes = tuple(m.digest(row) for row in rows[:5])
    axis = calendar._sessions()
    sources = tuple((name, (PUBLIC / name).read_bytes()) for name in sorted(m.projection.HOST_SOURCE_PINS))
    with pytest.MonkeyPatch.context() as patch:
        f = m.retained.fmt
        for module in (m.retained.policy, m.projection.quarantine):
            patch.setattr(module, 'QUARANTINED_WHOLE_BINDING_SHA256S', wholes)
            patch.setattr(module, 'ORIGINAL_BINDING_STREAM_SHA256', stream)
        patch.setattr(f, 'BINDING_SHA256', stream)
        supplied = copy.deepcopy(m.K_INPUT_BINDING)
        supplied['binding_contract'].update(binding_stream_sha256=stream,
            admitted_mapping_inventory_sha256='b' * 64)
        patch.setattr(m, 'K_INPUT_BINDING', supplied)
        catalog = m.retained.policy.make_quarantine_catalog_from_bindings(rows[:5])
        catalog_raw = m.canonical(catalog); patch.setattr(m, 'CATALOG_PIN', m.pin(catalog_raw))
        sessions = [day for day in axis if '2020-12-31' <= day <= '2026-10-13']
        months = f.months(sessions); assignments = []
        for ordinal, row in enumerate(rows):
            role = f.NATIVE if ordinal < 5 else f.VENDOR if ordinal < 5 + f.VENDOR_COUNT else f.CONDITIONAL
            assignments.append({'binding_ordinal': ordinal, 'security_id': row['security_id'],
                'whole_binding_sha256': m.digest(row), 'semantic_binding_sha256': row['row_sha256'],
                'role': role, 'table': 'stocks' if role == f.VENDOR else None,
                'ticker': f'STK{ordinal}' if role == f.VENDOR else None,
                'refusal_reason': None if role == f.VENDOR else 'SYNTHETIC-REFUSAL'})
        for ordinal, ticker in enumerate(f.OWN_FUNDS):
            assignments.append({'fund_ordinal': ordinal, 'own_ETF': ticker, 'role': f.VENDOR,
                'table': 'funds', 'ticker': ticker, 'route_sha256': m.sha(f'SYNTHETIC-FUND-{ordinal}'.encode())})
        vendor = {'schema': f.SCHEMA + '-catalog', 'AP_fact_sha256': f.AP_FACT_SHA256,
            'AP_source_sha256': f.AP_SOURCE_SHA256, 'AP_authentication_sha256': f.AP_AUTH_SHA256,
            'source_data_pins': copy.deepcopy(f.AP_DATA_PINS), 'binding_stream_sha256': stream,
            'full_axis_sha256': f.FULL_AXIS_SHA256, 'price_sessions': sessions,
            'assignments': assignments, 'vendor_slots': [i for i, row in enumerate(assignments)
                if row['role'] == f.VENDOR], 'months': months, **f.FALSE_FLAGS}
        f.validate_catalog(vendor)
        parts = {'catalog': m.canonical(vendor)}; month_rows = []; remaining = f.OBSERVED_ROWS
        for ordinal, month in enumerate(months):
            raw = f'OPAQUE-SYNTHETIC-NOT-PRICE-ROWS-{ordinal:03d}'.encode()
            parts[f'month_{ordinal:03d}'] = raw
            count = (f.VENDOR_COUNT + f.FUND_COUNT) * len(month['session_indexes'])
            valid = min(count, remaining); remaining -= valid
            month_rows.append({**month, 'row_count': count, 'valid_count': valid,
                'absent_count': count - valid, **m.pin(raw)})
        assert remaining == 0
        manifest = {'schema': f.SCHEMA + '-manifest', 'catalog_pin': m.pin(parts['catalog']),
            'AP_fact_sha256': f.AP_FACT_SHA256, 'AP_authentication_sha256': f.AP_AUTH_SHA256,
            'binding_stream_sha256': stream, 'full_axis_sha256': f.FULL_AXIS_SHA256,
            'assignment_count': f.STOCK_COUNT + f.FUND_COUNT, 'vendor_slot_count': f.VENDOR_COUNT + f.FUND_COUNT,
            'session_count': f.SESSION_COUNT, 'months': month_rows,
            'row_count': sum(row['row_count'] for row in month_rows),
            'valid_count': sum(row['valid_count'] for row in month_rows),
            'absent_count': sum(row['absent_count'] for row in month_rows),
            'total_shard_bytes': sum(row['byte_count'] for row in month_rows), **f.FALSE_FLAGS}
        f.validate_manifest(manifest); parts['manifest'] = m.canonical(manifest)
        entries, offset = [], 0
        for ordinal, role in enumerate(m.retained.ROLES):
            entries.append({'ordinal': ordinal, 'role': role, 'offset': offset, **m.pin(parts[role])})
            offset += len(parts[role])
        header = {'schema': m.retained.ARCHIVE_SCHEMA, 'data_plan_sha256': m.retained.PLAN_SHA256,
            'source_fact_sha256': m.retained.FACT_SHA256, 'source_output_sha256': m.retained.OUTPUT_SHA256,
            'entries': entries, 'range_count': 73, 'payload_byte_count': offset,
            **{key: False for key in m.retained.HEADER_FLAGS}}
        header_raw = m.canonical(header)
        archive = m.retained.MAGIC + len(header_raw).to_bytes(8, 'big') + header_raw + b''.join(parts[role] for role in m.retained.ROLES)
        patch.setattr(m, 'ARCHIVE_PIN', m.pin(archive)); patch.setattr(m.retained, 'ARCHIVE_PIN', m.pin(archive))
        patch.setattr(m, 'HEADER_PIN', m.pin(header_raw))
        patch.setattr(m, 'VENDOR_CATALOG_PIN', m.pin(parts['catalog']))
        patch.setattr(m, 'VENDOR_MANIFEST_PIN', m.pin(parts['manifest']))
        plan = {role: {'relative_path': 'synthetic/' + role, **m.pin(parts[role])} for role in m.retained.ROLES}
        patch.setattr(m.ar_anchor, 'data_plan', lambda: copy.deepcopy(plan))
        arguments = dict(axis=axis, bindings=rows, quarantine_catalog_raw=catalog_raw,
            archive_raw=archive, input_binding=supplied)
        summary, outputs = m.prepare(sources, **arguments, deadline=deadline())
        yield SimpleNamespace(rows=rows, axis=axis, catalog=catalog, catalog_raw=catalog_raw,
            vendor=vendor, manifest=manifest, parts=parts, header=header, header_raw=header_raw,
            archive=archive, plan=plan, sources=sources, arguments=arguments, summary=summary, outputs=outputs)


def refused(code, call):
    with pytest.raises(m.Refused) as caught: call()
    assert m.finite(caught.value) == code


def test_actual_all_six_profile_source_buffers_and_full_original_census(case):
    summary, outputs = case.summary, case.outputs
    assert summary == m.validate_summary(summary)
    assert summary['proposed_runtime_project_id'] == 38522505
    assert summary['proposed_context_only'] is True
    assert summary['binding_count'] == 6151 and summary['source_assignment_count'] == 6159
    assert summary['vendor_stock_count'] == 5636 and summary['conditional_stock_count'] == 510
    assert summary['private_output_file_count'] == 42 and len(outputs) == 42
    assert summary['archive_range_count'] == 73
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    assert b'sharadar-composite-figi-' not in m.canonical(summary)
    assert outputs['quarantine-catalog.json'] == case.catalog_raw
    assert tuple(outputs) == m.output_names()
    assert all(type(raw) is bytes for raw in outputs.values())
    assert sum(map(len, outputs.values())) < m.MAX_OUTPUT_BYTES
    for size, arm in m.projection.CELL_ORDER:
        prefix = m._cell_prefix(size, arm)
        profile = json.loads(outputs[prefix + 'profile.json'])
        assert profile['runtime_project_id'] == 38522505
        assert profile['quarantine_catalog_sha256'] == m.CATALOG_PIN['sha256']
        assert profile['vendor_source_context_sha256'] == m.digest(m.make_context())
        assert profile['source_pins'] == m.projection.CLOUD_SOURCE_PINS
        assert len(profile['strategy_profile']['decision_sessions']) == 259
        assert len(profile['strategy_profile']['evaluation_sessions']) == 1242
        assert len(outputs[prefix + 'main.py']) <= 64000
        compile(outputs[prefix + 'main.py'], 'synthetic-main.py', 'exec')
    assert 'assistant.dispatch_fence' not in sys.modules


def test_bundle_roundtrip_deterministic_and_each_logical_cell_has_twenty_sources(case):
    raw = m.pack_outputs(case.outputs, transport_nonce=NONCE)
    assert raw == m.pack_outputs(dict(reversed(tuple(case.outputs.items()))), transport_nonce=NONCE)
    observed = m.validate_bundle(raw, expected_pin=m.pin(raw), summary=case.summary,
        source_pairs=case.sources, deadline=deadline())
    assert observed == case.outputs
    manifest = json.loads(observed['bundle-manifest.json'])
    assert len(manifest['files']) == 41
    assert len(manifest['logical_cells']) == 6
    assert all(len(cell['source_files']) == 20 for cell in manifest['logical_cells'])
    assert [row['relative_path'] for row in manifest['files']] == sorted(set(case.outputs) - {'bundle-manifest.json'})


@pytest.mark.parametrize('field', ['upload_inventory_sha256', 'parent_proof_sha256', 'evaluator_manifest_sha256',
    'plain_package_sha256', 'source_lineage_sha256', 'activation_manifest_sha256', 'source_package_sha256'])
def test_every_complete_original_input_binding_field_required(case, field):
    supplied = copy.deepcopy(case.arguments['input_binding']); supplied[field] = 'f' * 64
    refused('input_binding', lambda: m.validate_inputs(case.axis, case.rows, supplied, deadline=deadline()))


@pytest.mark.parametrize('fault', ['extra', 'missing', 'bool_count', 'inventory', 'stream', 'admission'])
def test_input_contract_not_replaced_by_partial_or_claimed_identity(case, fault):
    supplied = copy.deepcopy(case.arguments['input_binding'])
    if fault == 'extra': supplied['authorized'] = True
    elif fault == 'missing': supplied.pop('parent_proof_sha256')
    elif fault == 'bool_count': supplied['binding_contract']['binding_count'] = True
    elif fault == 'inventory': supplied['binding_contract']['admitted_mapping_inventory_sha256'] = 'f' * 64
    elif fault == 'stream': supplied['binding_contract']['binding_stream_sha256'] = 'f' * 64
    else: supplied['binding_contract']['security_master_admission_sha256'] = 'f' * 64
    refused('input_binding', lambda: m.validate_inputs(case.axis, case.rows, supplied, deadline=deadline()))


@pytest.mark.parametrize('fault', ['axis_short', 'axis_list', 'axis_order', 'rows_short', 'rows_list', 'rows_order', 'row_duplicate', 'unselected_changed'])
def test_full_axis_and_all_6151_original_binding_rows_checked(case, fault):
    axis, rows = case.axis, case.rows
    if fault == 'axis_short': axis = axis[:-1]
    elif fault == 'axis_list': axis = list(axis)
    elif fault == 'axis_order': axis = tuple(reversed(axis))
    elif fault == 'rows_short': rows = rows[:-1]
    elif fault == 'rows_list': rows = list(rows)
    elif fault == 'rows_order': rows = tuple(reversed(rows))
    elif fault == 'row_duplicate': rows = rows[:-1] + (rows[-2],)
    else: rows = rows[:-1] + (binding(99999),)
    refused('axis' if fault.startswith('axis') else 'bindings',
        lambda: m.validate_inputs(axis, rows, case.arguments['input_binding'], deadline=deadline()))


@pytest.mark.parametrize('index', [0, 6000, 6150])
@pytest.mark.parametrize('field', ['security_id', 'whole_binding_sha256', 'semantic_binding_sha256'])
def test_source_index_joins_cover_unselected_and_conditional_originals(case, index, field):
    vendor = copy.deepcopy(case.vendor)
    vendor['assignments'][index][field] = 'f' * 64
    refused('assignment', lambda: m.validate_assignments(case.rows, vendor, case.catalog, deadline=deadline()))


def test_archive_and_catalog_whole_pins_precede_any_parse(case, monkeypatch):
    monkeypatch.setattr(m.retained, 'parse_archive', lambda *args, **kwargs: pytest.fail('unpinned source parsed'))
    refused('archive_pin', lambda: m.parse_archive(case.archive + b' ', deadline=deadline()))
    monkeypatch.setattr(m, 'loads', lambda *args, **kwargs: pytest.fail('unpinned catalog parsed'))
    arguments = {**case.arguments, 'quarantine_catalog_raw': case.catalog_raw + b' '}
    refused('catalog_pin', lambda: m.prepare(case.sources, **arguments, deadline=deadline()))


def test_external_header_pin_not_self_generated_from_current_header(case, monkeypatch):
    monkeypatch.setattr(m, 'HEADER_PIN', {'byte_count': len(case.header_raw), 'sha256': 'f' * 64})
    refused('header_pin', lambda: m.parse_archive(case.archive, deadline=deadline()))


def test_independent_retained_all_range_pins_not_only_computed_member_hashes(case, monkeypatch):
    plan = copy.deepcopy(case.plan); plan['month_070']['sha256'] = 'f' * 64
    monkeypatch.setattr(m.ar_anchor, 'data_plan', lambda: plan)
    refused('range_pin', lambda: m.parse_archive(case.archive, deadline=deadline()))


def test_supplied_archive_date_grid_must_match_entire_genuine_axis(case, monkeypatch):
    original = m.parse_archive
    def shifted(*args, **kwargs):
        vendor, manifest, descriptors = original(*args, **kwargs)
        vendor = copy.deepcopy(vendor)
        vendor['price_sessions'][10] = '2021-01-18'
        return vendor, manifest, descriptors
    monkeypatch.setattr(m, 'parse_archive', shifted)
    refused('axis', lambda: m.prepare(case.sources, **case.arguments, deadline=deadline()))


@pytest.mark.parametrize('fault', ['extra', 'missing', 'mutable', 'path', 'source', 'profile', 'catalog', 'context', 'family', 'manifest'])
def test_output_closed_inventory_and_actual_six_cell_bytes_authenticated(case, fault):
    outputs = dict(case.outputs)
    if fault == 'extra': outputs['arbitrary.txt'] = b'no'
    elif fault == 'missing': outputs.pop('quarantine-catalog.json')
    elif fault == 'mutable': outputs['quarantine-catalog.json'] = bytearray(case.catalog_raw)
    elif fault == 'path': outputs['../escape'] = outputs.pop('quarantine-catalog.json')
    elif fault == 'source': outputs['shared/newrule_common_price_format.py'] += b'# changed\n'
    elif fault == 'profile': outputs['cells/8-ar200/profile.json'] += b' '
    elif fault == 'catalog': outputs['quarantine-catalog.json'] += b' '
    elif fault == 'context': outputs['vendor-context.json'] = m.canonical({**m.make_context(), 'runtime_project_id': 7})
    elif fault == 'family': outputs['family.json'] += b' '
    else: outputs['bundle-manifest.json'] = b'{}'
    with pytest.raises(m.Refused): m.validate_outputs(case.summary, outputs, source_pairs=case.sources, deadline=deadline())


@pytest.mark.parametrize('field,value', [('QC_contact', 0), ('current_cloud_project_verified', True),
    ('complete_price_coverage_proven', True), ('proposed_runtime_project_id', True),
    ('binding_count', True), ('proposed_context_only', 1), ('private_output_file_count', 41)])
def test_public_summary_never_accepts_permission_claims_or_bool_numeric_equivalence(case, field, value):
    summary = {**case.summary, field: value}
    refused('output', lambda: m.validate_summary(summary))


@pytest.mark.parametrize('fault', ['whole_pin', 'magic', 'short', 'trailing', 'header', 'range'])
def test_private_bundle_hash_geometry_and_framing(case, fault):
    raw = m.pack_outputs(case.outputs, transport_nonce=NONCE); expected = m.pin(raw)
    if fault == 'whole_pin': expected = {'byte_count': len(raw), 'sha256': 'f' * 64}
    elif fault == 'magic': raw = b'X' + raw[1:]
    elif fault == 'short': raw = raw[:-1]
    elif fault == 'trailing': raw += b'X'
    else:
        start = len(m.MAGIC) + 8; size = int.from_bytes(raw[len(m.MAGIC):start], 'big')
        header = json.loads(raw[start:start + size]); payload = raw[start + size:]
        if fault == 'header': header['file_count'] = True
        else: header['entries'][-1]['sha256'] = 'f' * 64
        encoded = m.canonical(header)
        raw = m.MAGIC + len(encoded).to_bytes(8, 'big') + encoded + payload
    if fault != 'whole_pin': expected = m.pin(raw)
    with pytest.raises(m.Refused): m.validate_bundle(raw, expected_pin=expected, summary=case.summary,
        source_pairs=case.sources, deadline=deadline())


def test_all_private_bundle_ranges_authenticate_before_any_semantics(case, monkeypatch):
    raw = m.pack_outputs(case.outputs, transport_nonce=NONCE); start = len(m.MAGIC) + 8
    size = int.from_bytes(raw[len(m.MAGIC):start], 'big')
    header = json.loads(raw[start:start + size]); header['entries'][-1]['sha256'] = 'f' * 64
    encoded = m.canonical(header); bad = m.MAGIC + len(encoded).to_bytes(8, 'big') + encoded + raw[start + size:]
    calls = []
    def forbidden(*args, **kwargs): calls.append(True); raise AssertionError('semantic parse before last range hash')
    monkeypatch.setattr(m, 'validate_outputs', forbidden)
    refused('bundle', lambda: m.validate_bundle(bad, expected_pin=m.pin(bad), summary=case.summary,
        source_pairs=case.sources, deadline=deadline()))
    assert not calls


@pytest.mark.parametrize('value', [True, None, 0, float('nan'), float('inf'), -1])
def test_deadline_must_be_finite_live_exact_number(value):
    refused('deadline', lambda: m.budget(value))


def test_no_file_transport_credential_or_old_operational_entrypoints_available():
    tree = ast.parse(Path(m.__file__).read_bytes())
    forbidden = {'open', 'read', 'read_bytes', 'write', 'write_bytes', 'Popen', 'urlopen',
        'request', 'produce', 'run', 'main', 'load_october_order_input_package', '_load_plain', 'prepare_arv2_r337_quarantine'}
    calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))}
    assert not calls.intersection(forbidden)
    assert m.finite(TimeoutError()) == 'deadline'
    assert m.finite(m.retained.Refused('deadline')) == 'deadline'
    assert m.finite(m.Refused('PRIVATE')) == 'unknown'
    assert all(m.profile_record()[key] is False for key in m.FALSE_FLAGS)


def test_profile_nested_input_is_defensive_and_cannot_change_enforced_contract():
    original = m.canonical(m.K_INPUT_BINDING)
    profile = m.profile_record()
    profile['complete_K_input_binding']['binding_contract']['binding_count'] = 1
    assert m.canonical(m.K_INPUT_BINDING) == original


def test_input_stream_matches_actual_frozen_figi_serializer_including_LF(monkeypatch):
    rows = tuple(binding(i) for i in range(6151))
    figi = m.projection.runtime.figi
    assert all(figi._canonical(row) == m.canonical(row) + b'\n' for row in rows)
    stream = m.sha(b''.join(figi._canonical(row) for row in rows))
    supplied = copy.deepcopy(m.K_INPUT_BINDING)
    supplied['binding_contract'].update(binding_stream_sha256=stream,
        admitted_mapping_inventory_sha256='b' * 64)
    monkeypatch.setattr(m, 'K_INPUT_BINDING', supplied)
    monkeypatch.setattr(m.retained.fmt, 'BINDING_SHA256', stream)
    assert m.validate_inputs(calendar._sessions(), rows, supplied, deadline=deadline()) == rows


@pytest.mark.parametrize('outputs', [None, [], {1: b'x'}, {'x': b'x', 1: b'y'}])
def test_invalid_output_names_and_non_mapping_have_finite_refusal(outputs):
    refused('output', lambda: m.pack_outputs(outputs, transport_nonce=NONCE))


def test_fresh_private_transport_nonce_changes_container_pin_only(case):
    first = m.pack_outputs(case.outputs, transport_nonce=NONCE)
    second = m.pack_outputs(case.outputs, transport_nonce='24' * 32)
    assert first != second and m.pin(first) != m.pin(second)
    assert m.validate_bundle(first, expected_pin=m.pin(first), summary=case.summary,
        source_pairs=case.sources, deadline=deadline()) == m.validate_bundle(second,
            expected_pin=m.pin(second), summary=case.summary, source_pairs=case.sources, deadline=deadline()) == case.outputs
    assert NONCE.encode() not in m.canonical(case.summary)
    assert NONCE.encode() not in b''.join(case.outputs.values())


@pytest.mark.parametrize('nonce', [None, True, b'1' * 64, '', '0' * 63, 'A' * 64, 'g' * 64, '0' * 65])
def test_private_transport_nonce_is_mandatory_closed_lowerhex(case, nonce):
    refused('transport_nonce', lambda: m.pack_outputs(case.outputs, transport_nonce=nonce))


def test_missing_nonce_cannot_use_implicit_time_project_or_head_default(case):
    with pytest.raises(TypeError): m.pack_outputs(case.outputs)


@pytest.mark.parametrize('nonce', [None, True, 'A' * 64, '0' * 63])
def test_rehashed_container_with_invalid_nonce_refuses_before_outputs_parse(case, nonce, monkeypatch):
    raw = m.pack_outputs(case.outputs, transport_nonce=NONCE); start = len(m.MAGIC) + 8
    size = int.from_bytes(raw[len(m.MAGIC):start], 'big')
    header = json.loads(raw[start:start + size]); header['transport_nonce'] = nonce
    encoded = m.canonical(header); candidate = m.MAGIC + len(encoded).to_bytes(8, 'big') + encoded + raw[start + size:]
    monkeypatch.setattr(m, 'validate_outputs', lambda *a, **k: pytest.fail('invalid nonce parsed as source output'))
    refused('transport_nonce', lambda: m.validate_bundle(candidate, expected_pin=m.pin(candidate),
        summary=case.summary, source_pairs=case.sources, deadline=deadline()))
