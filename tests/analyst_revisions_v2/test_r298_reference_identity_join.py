"""Pure synthetic registered capabilities, never private input or operations."""
import ast
import builtins
import copy
import dataclasses
import json
from pathlib import Path
import socket
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_reference_identity_join as m
from tests.analyst_revisions_v2 import test_newrule_plain_projection as synthetic


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('operational boundary reached by synthetic join')
    monkeypatch.setattr(m.admission, 'admit', denied)
    monkeypatch.setattr(m.admission.a11.prep, 'construct', denied)
    monkeypatch.setattr(m.figi, 'resolve_preliminary_qc_figis', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)


@pytest.fixture(scope='module')
def axis():
    return m.bridge.frozen.october._sessions()


def rows(count):
    result = []
    for index in range(count):
        figi = 'BBG' + str(index + 1).zfill(9)
        result.append(m.figi.build_preliminary_qc_figi_binding(
            security_id='sharadar-composite-figi-' + figi, issuer_id='synthetic-issuer-' + str(index),
            composite_figi=figi, listing_id='synthetic-listing-' + str(index),
            diagnostic_current_ticker='SYNTH' + str(index), diagnostic_exchange_mic='XNYS',
            candidate_first_session='2021-01-04', candidate_last_session='2026-10-13',
            source_snapshot_available_at='2026-10-13T00:00:00.000000Z',
            source_row_sha256='a' * 64, identity_evidence_sha256='b' * 64,
            security_master_admission_sha256='c' * 64,
            admitted_mapping_inventory_sha256='d' * 64, admitted_mapping_count=count))
    return result


def witness_row(row, reference='2022-10-21', decision='2022-10-24', *, holding='held', kind='stock'):
    return {'identity_sha256': m.legacy._sha({'schema': m.WITNESS_SCHEMA,
        'security_id': row['security_id'], 'reference_session': reference, 'decision_session': decision}),
        'holding': holding, 'kind': kind, 'sid_date': 'on_or_before_reference'}


def context_for(bindings, axis, *, count=1):
    witnesses = sorted((witness_row(row) for row in bindings[:count]), key=lambda row: row['identity_sha256'])
    return {'schema': m.witness.CONTEXT_SCHEMA, 'predicate': 'raw_reference_census_incomplete',
        'requested': count + 1, 'returned': 1, 'missing': count,
        'missing_holdings': {'held': count, 'unheld_target': 0, 'unknown': 0},
        'missing_kind': {'own_etf': 0, 'stock': count, 'unknown': 0},
        'missing_sid_date': {'on_or_before_reference': count,
            'after_reference_through_decision': 0, 'after_decision': 0, 'unknown': 0},
        'calendar_status': 'valid', 'reference_session': '2022-10-21',
        'decision_session': '2022-10-24', 'decision_time': '09:20',
        'session_axis_sha256': m.legacy._sha(list(axis)), 'witness_status': 'complete',
        'witnesses': witnesses, 'cause_authenticated': False, 'probe_prices_used': False,
        'sizing_repaired': False, 'diagnostic_only': True,
        'extra_history_call': False, 'probe_repeated': False}


def make_case(monkeypatch, axis, *, binding_rows=None, context_count=1, changes=None):
    bindings = copy.deepcopy(binding_rows if binding_rows is not None else rows(3))
    sessions = [{'schema': m.evaluator.SESSION_SCHEMA, 'session_index': index, 'session': session}
        for index, session in enumerate(axis)]
    lineage = {key: 'c' * 64 for key in m.evaluator._SOURCE_LINEAGE_FIELDS}
    manifest = m.evaluator.build_preliminary_rating_manifest(
        benchmark_security_id='synthetic-benchmark', session_axis_records=tuple(sessions),
        membership_records=({'synthetic': 'unparsed-membership'},),
        contribution_records=({'synthetic': 'unparsed-contribution'},),
        source_lineage_sha256s=lineage)
    contents = {'evaluator_manifest': manifest, 'session_axis': sessions,
        'runtime_symbol_bindings': bindings}
    if changes is not None: changes(contents)
    payloads, descriptors = {}, []
    for role in m.transport.ROLES:
        name = 'evaluator-manifest.json' if role == 'evaluator_manifest' else role + '-0000.jsonl'
        if role == 'evaluator_manifest': raw = m.canonical(contents[role]) + b'\n'
        elif role in contents: raw = b''.join(m.canonical(row) + b'\n' for row in contents[role])
        else: raw = b'PRIVATE-UNPARSED-NOT-JSON\n'
        payloads[name] = raw
        count = 1 if role not in ('session_axis', 'runtime_symbol_bindings') else len(contents[role])
        descriptors.append({'schema': m.transport.OBJECT_SCHEMA, 'role': role, 'ordinal': 0,
            'object_store_key': 'pending/' + name, 'relative_path': name,
            'byte_count': len(raw), 'content_sha256': m.sha(raw), 'record_count': count,
            'compression': 'identity', 'activation_manifest': False})
    proof = {'schema': m.transport.PROOF_SCHEMA, 'source_package_sha256': m.bridge.parent.PACKAGE,
        'source_lineage_sha256': m.bridge.parent.LINEAGE,
        'source_activation_sha256': m.bridge.parent.ACTIVATION[1],
        'source_activation_byte_count': m.bridge.parent.ACTIVATION[2],
        'source_inventory_sha256': 'e' * 64,
        'streams': [{key: row[key] for key in ('role', 'ordinal', 'record_count', 'byte_count', 'content_sha256')}
            for row in descriptors]}
    record = {'schema': m.transport.SCHEMA, 'package_id': None, 'package_sha256': None,
        'evaluator_manifest_id': contents['evaluator_manifest']['manifest_id'],
        'evaluator_manifest_sha256': contents['evaluator_manifest']['manifest_sha256'],
        'source_disposition_sha256': m.bridge.parent.LINEAGE,
        'runtime_symbol_binding_count': len(bindings),
        'runtime_symbol_bindings_sha256': m.legacy._sha(None),
        'objects': descriptors, 'parent_proof': proof, 'parent_proof_sha256': 'f' * 64}
    import hashlib
    record['runtime_symbol_bindings_sha256'] = hashlib.sha256(
        payloads['runtime_symbol_bindings-0000.jsonl']).hexdigest()
    plain = synthetic.mint_synthetic(record, payloads)
    original_plain, inventory = m.bridge._plain_binding(plain)
    profile = m.bridge.frozen.runtime.make_profile(axis, package_sha256=plain.package_sha256,
        lineage_sha256=plain.source_lineage_sha256, universe_count=6, ar_percent=0,
        source_pins={'synthetic_source.py': 'f' * 64})
    main = ('NewruleComparisonDriver(profile=' + repr(profile)
        + ', activation_manifest_key=' + repr(plain.activation_manifest_key)
        + ', activation_manifest_sha256=' + repr(plain.activation_manifest_sha256)
        + ', activation_manifest_byte_count=' + repr(plain.activation_manifest_byte_count) + ')\n').encode('ascii')
    projected = {'profile_sha256': profile['profile_sha256'], 'package_sha256': plain.package_sha256,
        'lineage_sha256': plain.source_lineage_sha256,
        'activation_manifest_key': plain.activation_manifest_key,
        'activation_manifest_sha256': plain.activation_manifest_sha256,
        'activation_manifest_byte_count': plain.activation_manifest_byte_count,
        'upload_inventory': inventory, 'upload_inventory_sha256': m.sha(m.canonical(inventory)),
        'total_upload_byte_count': plain.total_upload_byte_count,
        'bridge': {'parent_proof_sha256': plain.parent_proof_sha256}}
    raw = m.canonical(projected)
    packet = {'synthetic-public-packet': True, 'projection_record': raw.decode('ascii'),
        'source_pairs': [['main.py', main.decode('ascii')]],
        'readiness_pin': {'sha256': '1' * 64}, 'storage_receipt': {'synthetic-D2': True}}
    def admit(value):
        assert value is packet
        return raw, (('main.py', main),)
    monkeypatch.setattr(m.admission, 'validate_packet', admit)
    return NS(plain=plain, record=original_plain, profile=profile, projected=projected,
        packet=packet, raw=raw, bindings=bindings, manifest=contents['evaluator_manifest'],
        context=context_for(bindings, axis, count=context_count))


@pytest.fixture
def case(monkeypatch, axis):
    return make_case(monkeypatch, axis)


def joined(case): return m.join(case.plain, case.context, case.packet)


def test_complete_join_is_redacted_pinned_and_detached(case):
    before = copy.deepcopy(case.context)
    value = joined(case)
    assert value['matched_count'] == value['witness_count'] == 1
    assert value['catalog_row_count'] == 3
    assert value['context_sha256'] == m.context_digest(case.context)
    assert value['old_projection_sha256'] == m.sha(case.raw)
    assert value['matches'][0]['binding_row_sha256'] == case.bindings[0]['row_sha256']
    assert value['matches'][0]['whole_binding_row_sha256'] == m.legacy._sha(case.bindings[0])
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    assert all(value[key] is True for key in m.TRUE_FLAGS)
    encoded = m.canonical(value)
    for raw in ('BBG000000001', 'SYNTH0', 'sharadar-composite-figi-',
            'synthetic-issuer-', 'synthetic-listing-', 'PRIVATE-UNPARSED'):
        assert raw.encode('ascii') not in encoded
    assert before == case.context
    value['matches'][0]['holding'] = 'unknown'
    assert joined(case)['matches'][0]['holding'] == 'held'


def test_all_witnesses_matched_sorted_without_partial_routing(monkeypatch, axis):
    case = make_case(monkeypatch, axis, context_count=3)
    result = joined(case)
    assert result['matched_count'] == result['witness_count'] == 3
    assert [row['identity_sha256'] for row in result['matches']] == sorted(
        row['identity_sha256'] for row in case.context['witnesses'])


def test_witness_domain_uses_exact_dates_and_no_LF(case):
    row = case.bindings[0]
    seed = {'schema': m.WITNESS_SCHEMA, 'security_id': row['security_id'],
        'reference_session': '2022-10-21', 'decision_session': '2022-10-24'}
    digest = case.context['witnesses'][0]['identity_sha256']
    assert digest == m.sha(m.canonical(seed))
    assert digest != m.sha(m.canonical(seed) + b'\n')
    assert digest != m.legacy._sha({key: value for key, value in seed.items() if key != 'decision_session'})


@pytest.mark.parametrize('kind', ['copy', 'replace', 'mutated', 'pid'])
def test_forged_or_changed_plain_capability_refuses(case, monkeypatch, kind):
    plain = case.plain
    if kind == 'copy': plain = copy.copy(plain)
    elif kind == 'replace': plain = dataclasses.replace(plain)
    elif kind == 'mutated': object.__setattr__(plain, 'source_lineage_sha256', '0' * 64)
    else:
        registry = m.transport._AUTHORITIES[id(plain)]
        monkeypatch.setitem(m.transport._AUTHORITIES, id(plain), (*registry[:2], registry[2] + 1))
    with pytest.raises(m.Refused, match='^plain_authority$'): m.join(plain, case.context, case.packet)


@pytest.mark.parametrize('mutation', ['unavailable', 'partial', 'duplicate', 'own_etf',
    'unknown_kind', 'not_complete', 'histogram', 'clock', 'context_flag'])
def test_context_must_have_complete_stock_witness_inventory(case, mutation):
    value = case.context
    if mutation == 'unavailable': value['calendar_status'] = 'unavailable'
    elif mutation == 'partial': value['witnesses'] = []
    elif mutation == 'duplicate': value['witnesses'].append(copy.deepcopy(value['witnesses'][0]))
    elif mutation == 'own_etf':
        value['witnesses'][0]['kind'] = 'own_etf'
        value['missing_kind'] = {'stock': 0, 'own_etf': 1, 'unknown': 0}
    elif mutation == 'unknown_kind':
        value['witnesses'][0]['kind'] = 'unknown'
        value['missing_kind'] = {'stock': 0, 'own_etf': 0, 'unknown': 1}
    elif mutation == 'not_complete': value['witness_status'] = 'unavailable'; value['witnesses'] = []
    elif mutation == 'histogram': value['missing_holdings']['held'] = 0
    elif mutation == 'clock': value['decision_time'] = '09:21'
    else: value['sizing_repaired'] = True
    with pytest.raises(m.Refused): joined(case)


def test_unmatched_or_date_renamed_witness_never_routes(case):
    case.context['witnesses'][0]['identity_sha256'] = '0' * 64
    with pytest.raises(m.Refused, match='^witness_unmatched$'): joined(case)


@pytest.mark.parametrize('field', ['package_sha256', 'activation_manifest_sha256',
    'upload_inventory_sha256', 'total_upload_byte_count'])
def test_public_admission_must_match_exact_genuine_plain(case, monkeypatch, field):
    projected = copy.deepcopy(case.projected)
    projected[field] = 1 if field == 'total_upload_byte_count' else '0' * 64
    monkeypatch.setattr(m.admission, 'validate_packet', lambda _: (m.canonical(projected),
        (('main.py', case.packet['source_pairs'][0][1].encode('ascii')),)))
    with pytest.raises(m.Refused, match='^projection_binding$'): joined(case)


def test_failed_public_admission_is_not_replaced_by_context_boolean(case, monkeypatch):
    def refused(_): raise m.admission.Refused('public_packet')
    monkeypatch.setattr(m.admission, 'validate_packet', refused)
    with pytest.raises(m.Refused, match='^public_admission$'): joined(case)


@pytest.mark.parametrize('change', ['wrong_day', 'wrong_axis'])
def test_calendar_must_bind_actual_adjacent_source_sessions(case, change):
    if change == 'wrong_day': case.context['reference_session'] = '2022-10-20'
    else: case.context['session_axis_sha256'] = '0' * 64
    with pytest.raises(m.Refused): joined(case)


def test_manifest_session_stream_pin_cannot_be_ignored(monkeypatch, axis):
    def mutate(contents):
        value = contents['evaluator_manifest']
        value['session_axis_sha256'] = '0' * 64
        seed = dict(value); seed.pop('manifest_sha256'); seed.pop('manifest_id')
        pin = m.legacy._sha(seed)
        value.update(manifest_sha256=pin, manifest_id='arv2-preliminary-rating-manifest-' + pin[:24])
    case = make_case(monkeypatch, axis, changes=mutate)
    with pytest.raises(m.Refused, match='^calendar$'): joined(case)


def test_final_context_and_public_packet_snapshot_rechecked(case, monkeypatch):
    original = m.transport.iter_plain_upload_objects
    def iterator(value):
        yield from original(value)
        case.packet['synthetic-public-packet'] = False
    monkeypatch.setattr(m.transport, 'iter_plain_upload_objects', iterator)
    with pytest.raises(m.Refused, match='^plain_changed$'): joined(case)


@pytest.mark.parametrize('kind', ['duplicate', 'unsorted', 'wrong_admission', 'wrong_count',
    'row_hash', 'ticker_type', 'mixed_inventory'])
def test_catalog_schema_uniqueness_and_lineage_preserved(monkeypatch, axis, kind):
    binding = rows(3)
    if kind == 'duplicate': binding[1] = copy.deepcopy(binding[0])
    elif kind == 'unsorted': binding.reverse()
    elif kind == 'wrong_admission': binding[0]['security_master_admission_sha256'] = 'e' * 64
    elif kind == 'wrong_count': binding[0]['admitted_mapping_count'] = 2
    elif kind == 'row_hash': binding[0]['row_sha256'] = '0' * 64
    elif kind == 'ticker_type': binding[0]['diagnostic_current_ticker'] = True
    else: binding[1]['admitted_mapping_inventory_sha256'] = 'e' * 64
    if kind in ('wrong_count', 'mixed_inventory'):
        for row in binding:
            seed = dict(row); seed.pop('row_sha256')
            row['row_sha256'] = m.legacy._sha(seed)
    case = make_case(monkeypatch, axis, binding_rows=binding)
    with pytest.raises(m.Refused): joined(case)


def test_no_extra_catalog_contribution_membership_or_operational_query(case, monkeypatch):
    def denied(*args, **kwargs): raise AssertionError('no filesystem or network from pure join')
    monkeypatch.setattr(builtins, 'open', denied)
    monkeypatch.setattr(Path, 'read_bytes', denied)
    assert joined(case)['matched_count'] == 1


def test_genuine_transport_rechecked_after_catalog_iteration(case, monkeypatch):
    original = m.transport.iter_plain_upload_objects
    def iterator(value):
        yield from original(value)
        object.__setattr__(value, 'source_lineage_sha256', '0' * 64)
    monkeypatch.setattr(m.transport, 'iter_plain_upload_objects', iterator)
    with pytest.raises(m.Refused, match='^plain_changed$'): joined(case)


@pytest.mark.parametrize('change', ['extra', 'count_bool', 'count_mismatch', 'flag', 'raw_row',
    'duplicate', 'hash_type', 'foreign_field', 'match_admission'])
def test_receipt_closed_and_no_false_readiness(case, change):
    value = joined(case)
    if change == 'extra': value['private'] = 'should-not-be-kept'
    elif change == 'count_bool': value['matched_count'] = True
    elif change == 'count_mismatch': value['witness_count'] = 2
    elif change == 'flag': value['formal_identity_admitted'] = True
    elif change == 'raw_row': value['matches'][0]['ticker'] = 'PRIVATE'
    elif change == 'duplicate': value['matches'] *= 2
    elif change == 'hash_type': value['catalog_sha256'] = 1
    elif change == 'foreign_field': value['matches'][0]['kind'] = []
    else: value['matches'][0]['security_master_admission_sha256'] = '0' * 64
    with pytest.raises(m.Refused, match='^receipt$'): m.validate_receipt(value)


@pytest.mark.parametrize('code', sorted(m.FINITE))
def test_finite_error_never_echoes_private_values(code):
    assert m.finite(m.Refused(code)) == code


def test_unknown_or_foreign_error_details_not_retained():
    class Foreign(m.Refused): pass
    for error in (ValueError('PRIVATE'), Foreign('calendar'), m.Refused('PRIVATE'),
            m.Refused(), m.Refused('calendar', 'PRIVATE')):
        assert m.finite(error) == 'unknown'


def test_profile_truth_and_no_operational_entrypoint():
    profile = m.profile_record()
    assert profile['witness_fields'] == ['schema', 'security_id', 'reference_session', 'decision_session']
    assert profile['max_binding_rows'] == 100000 and profile['max_witnesses'] == 16
    assert profile['context_hash_encoding'] == 'canonical_ASCII_JSON_without_LF'
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert not any(hasattr(m, name) for name in ('main', 'run', 'Store', 'claim', 'launch', 'request'))
