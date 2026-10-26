"""Pure synthetic metadata packaging; actual private/provider/QC I/O denied."""
from copy import deepcopy
import http.client
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_bundle as b, extended_evidence as e, extended_operations as o

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def deny_actual_io(monkeypatch):
    def denied(*a, **kw): raise AssertionError('actual private/credential/network/QC access denied')
    monkeypatch.setattr(o, 'read_private', denied)
    monkeypatch.setattr(o, 'credential', denied)
    monkeypatch.setattr(o.Operations, 'guard', denied)
    monkeypatch.setattr(http.client, 'HTTPSConnection', denied)


def metadata(preparation):
    raw = e.canonical(preparation); prep_hash = e.digest(raw)
    prefix = 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + prep_hash + '/'
    rows = preparation['payloads']
    manifest = {'schema': 'tpr-ext26-signal-manifest-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'calendar_sha256': b.CALENDAR_SHA256, 'identity_sha256': rows[0]['sha256'], 'identity_key': prefix + rows[0]['sha256'] + '.json',
        'shards': [{'sha256': row['sha256'], 'key': prefix + row['sha256'] + '.json', 'sessions': row['sessions']} for row in rows[1:]]}
    manifest_raw = e.canonical(manifest); manifest_hash = e.digest(manifest_raw)
    inventory = [{'name': row['sha256'] + '.json', 'sha256': row['sha256'], 'bytes': row['bytes']} for row in rows]
    inventory.append({'name': manifest_hash + '.json', 'sha256': manifest_hash, 'bytes': len(manifest_raw)})
    return {'preparation_raw': raw, 'signal_manifest_raw': manifest_raw, 'expected_preparation_sha256': prep_hash,
        'expected_manifest_sha256': manifest_hash, 'input_inventory': inventory}


@pytest.fixture
def arguments():
    calendar = (ROOT / (b.PREFIX + 'extended_calendar.json')).read_bytes()
    groups = b._calendar(calendar)
    receipt = {key: {} for key in b.PREPARATION_KEYS}
    receipt.update(schema='tpr-ext26-preparation-v2', study_id=e.STUDY_ID, status='COMPLETED',
        operation_id='TPR-EXT26-PREPARATION-20261010-001', freeze_sha256=e.FREEZE_SHA256, calendar_sha256=b.CALENDAR_SHA256,
        capture_status='FAILED', repair_status='COMPLETED', source_composition='FAILED001-Massive74-plus-completed-Sharadar-repair2',
        capture_failure='refused_or_bound_hit_no_retry', original_failed_sharadar_wire_used_for_inputs=False, source_input_prepared=True,
        point_in_time_data=False, rights_verified=False, canonical_admission=False, trading=False,
        outcome_reads=0, development_looks=0, quantconnect_attempts=0, decision_count=301, monthly_shards=70,
        identity_count=1, eligible_identity_count=1, source_hashes={b.PREFIX + 'extended_preparation.py': 'f' * 64},
        started_utc='2026-10-10T01:30:00+00:00', ended_utc='2026-10-10T02:00:00+00:00',
        capture_utc='2026-10-10T01:00:00+00:00', capture_ended_utc='2026-10-10T00:30:00+00:00', repair_ended_utc='2026-10-10T01:00:00+00:00',
        limitations=['Synthetic metadata only; no native rows or actual provider truth.'],
        source_refusal_census={provider: {key: 0 for key in b.REFUSAL_CATEGORIES} for provider in ('massive', 'sharadar')},
        manifest_policy='manifest is deterministically derived after receipt hash; not a circular receipt input')
    for key in ('plan_sha256', 'owner_instruction_sha256', 'capture_index_sha256', 'capture_plan_sha256', 'capture_report_sha256',
            'repair_freeze_sha256', 'repair_index_sha256', 'repair_plan_sha256', 'repair_report_sha256'): receipt[key] = 'a' * 64
    for key in ('git_sha', 'capture_git_sha', 'repair_git_sha'): receipt[key] = 'b' * 40
    receipt['payloads'] = [{'kind': 'identities', 'sha256': e.digest(b'synthetic identities metadata only'), 'bytes': 100, 'sessions': []}]
    receipt['payloads'] += [{'kind': 'signal-month', 'sha256': e.digest(('synthetic monthly metadata ' + str(index)).encode()),
        'bytes': 200, 'sessions': group} for index, group in enumerate(groups)]
    templates = {b.PREFIX + name: (ROOT / (b.PREFIX + name)).read_bytes() for name in b.TEMPLATE_NAMES}
    sources = {name: 'c' * 64 for name in b.REQUIRED_SOURCES}
    sources.update({name: e.digest(raw) for name, raw in templates.items()})
    sources[b.PREFIX + 'extended_calendar.json'] = b.CALENDAR_SHA256
    sources[b.PREFIX + 'extended_study_freeze.json'] = e.FREEZE_SHA256
    return {'calendar_raw': calendar, 'templates': templates, 'repository_source_hashes': sources, **metadata(receipt)}


def render(arguments, **changed):
    values = dict(arguments); values.update(changed)
    return b.render_bundle(**values)


def altered_receipt(arguments, change):
    receipt = e.parse_json(arguments['preparation_raw']); change(receipt)
    return render(arguments, **metadata(receipt))


def test_exact_two_attempt1_candidates_readable_config_calendar_and_metadata_only_packet(arguments):
    output = render(arguments)
    assert set(output) == {'schema', 'candidates', 'inputs', 'preparation_sha256', 'repository_sources'}
    assert output['schema'] == 'tpr-ext26-source-bundle-v1' and len(output['candidates']) == 2 and len(output['inputs']) == 72
    for row, (candidate, arm) in zip(output['candidates'], e.CANDIDATES.items()):
        assert row['candidate_id'] == candidate and row['planned_attempt'] == 1 and row['project_name'] == candidate + '-private'
        files = row['files']; config = e.parse_json(row['config_raw'].encode())
        assert len(files) == (8 if arm == 'tpr_on' else 7)
        assert config['input_hashes']['preparation.json'] == arguments['expected_preparation_sha256']
        assert b._literal(files['main.py'], 'EXPECTED_CONFIG_SHA256') == e.digest(row['config_raw'].encode())
        assert b._literal(files['main.py'], 'EXPECTED_ATTEMPT') == 1
        assert b._literal(files['extended_loader.py'], 'CALENDAR_JSON').encode() == arguments['calendar_raw']
        for name, text in files.items():
            compile(text, name, 'exec'); assert len(text.encode()) <= 60000
        if arm == 'tpr_on':
            manifest_raw = b._literal(files['signal_packet.py'], 'CONFIG_JSON').encode()
            assert manifest_raw == arguments['signal_manifest_raw']
            assert set(e.parse_json(manifest_raw)) == {'schema', 'study_id', 'freeze_sha256', 'calendar_sha256', 'identity_sha256', 'identity_key', 'shards'}
        else:
            assert 'signal_packet.py' not in files and set(config['input_hashes']) == {'calendar.json', 'preparation.json'}


def test_immutable_helper_and_core_bytes_are_copied_and_only_import_boundary_is_flattened(arguments):
    cases = render(arguments)['candidates']
    for row in cases:
        for name in ('cap_tilt.py', 'cap_observer.py', 'extended_core.py'):
            assert row['files'][name].encode() == arguments['templates'][b.PREFIX + name]
        expected = arguments['templates'][b.PREFIX + 'extended_construction.py'].decode().replace('from . import cap_tilt', 'import cap_tilt')
        assert row['files']['extended_construction.py'] == expected


@pytest.mark.parametrize('field,value', [('study_id', 'old-study'), ('status', 'FAILED'), ('source_input_prepared', False),
    ('rights_verified', True), ('canonical_admission', True), ('trading', True), ('outcome_reads', True),
    ('monthly_shards', 69), ('decision_count', 300), ('identity_count', 0), ('eligible_identity_count', 2),
    ('capture_status', 'COMPLETED'), ('original_failed_sharadar_wire_used_for_inputs', True)])
def test_unapproved_or_incomplete_receipt_metadata_refuses(arguments, field, value):
    with pytest.raises(b.Refusal): altered_receipt(arguments, lambda body: body.__setitem__(field, value))


@pytest.mark.parametrize('which', ['preparation', 'manifest'])
def test_external_expected_hash_cannot_be_implicitly_recomputed(arguments, which):
    key = 'expected_preparation_sha256' if which == 'preparation' else 'expected_manifest_sha256'
    with pytest.raises(b.Refusal): render(arguments, **{key: '0' * 64})


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'wrong_month', 'row_injection'])
def test_complete_global301_metadata_frames_never_drop_or_inject_inputs(arguments, change):
    def mutate(body):
        if change == 'missing': body['payloads'].pop()
        elif change == 'duplicate': body['payloads'][2]['sha256'] = body['payloads'][1]['sha256']
        elif change == 'wrong_month': body['payloads'][1]['sessions'].reverse()
        else: body['payloads'][0]['rows'] = [{'licensed': 'NOT ALLOWED'}]
    with pytest.raises(b.Refusal): altered_receipt(arguments, mutate)


@pytest.mark.parametrize('change', ['foreign_prefix', 'identity_hash', 'extra_rows', 'wrong_shard'])
def test_manifest_only_metadata_exactly_derived_from_bound_receipt(arguments, change):
    body = e.parse_json(arguments['signal_manifest_raw'])
    if change == 'foreign_prefix': body['identity_key'] = body['identity_key'].replace(arguments['expected_preparation_sha256'], '0' * 64)
    elif change == 'identity_hash': body['identity_sha256'] = '0' * 64
    elif change == 'extra_rows': body['rows'] = ['LICENSED INPUT NOT ALLOWED']
    else: body['shards'][-1]['sessions'].pop()
    raw = e.canonical(body)
    # Rebind the independently supplied inventory metadata too. Otherwise an
    # inventory/hash disagreement would mask a missing manifest-content gate.
    identity = e.digest(raw); inventory = deepcopy(arguments['input_inventory'])
    inventory[-1] = {'name': identity + '.json', 'sha256': identity, 'bytes': len(raw)}
    with pytest.raises(b.Refusal): render(arguments, signal_manifest_raw=raw, expected_manifest_sha256=identity, input_inventory=inventory)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'foreign_name', 'wrong_bytes', 'bool_bytes', 'raw_capture'])
def test_upload_inventory_is_exhaustive_hash_named_and_never_old_capture_rows(arguments, change):
    rows = deepcopy(arguments['input_inventory'])
    if change == 'missing': rows.pop()
    elif change == 'duplicate': rows[-1] = rows[0]
    elif change == 'foreign_name': rows[0]['name'] = 'old-input.json'
    elif change == 'wrong_bytes': rows[0]['bytes'] = 101
    elif change == 'bool_bytes': rows[0]['bytes'] = True
    else: rows[0]['name'] = 'request.0001.wire.json'
    with pytest.raises(b.Refusal): render(arguments, input_inventory=rows)


@pytest.mark.parametrize('change', ['missing', 'foreign', 'source_edit', 'bool_hash'])
def test_exact_repository_template_source_closure_required(arguments, change):
    hashes, templates = dict(arguments['repository_source_hashes']), dict(arguments['templates'])
    if change == 'missing': hashes.pop(b.PREFIX + 'extended_bundle.py')
    elif change == 'foreign': hashes['../shared.py'] = 'a' * 64
    elif change == 'source_edit': templates[b.PREFIX + 'cap_tilt.py'] += b'\n# unbound change\n'
    else: hashes[b.PREFIX + 'extended_core.py'] = True
    with pytest.raises(b.Refusal): render(arguments, templates=templates, repository_source_hashes=hashes)


@pytest.mark.parametrize('marker', ['__EXTENDED_CONFIG_SHA256__', '__ATTEMPT_NUMBER__', '__CALENDAR_JSON_LITERAL__'])
@pytest.mark.parametrize('change', ['absent', 'duplicate'])
def test_exact_runtime_placeholders_required_before_capped_compile(arguments, marker, change):
    templates, hashes = dict(arguments['templates']), dict(arguments['repository_source_hashes'])
    name = b.PREFIX + ('extended_loader.py' if marker == '__CALENDAR_JSON_LITERAL__' else 'extended_algorithm.py')
    raw = templates[name].replace(marker.encode(), b'NONE') if change == 'absent' else templates[name] + ('\n# ' + marker).encode()
    templates[name], hashes[name] = raw, e.digest(raw)
    with pytest.raises(b.Refusal): render(arguments, templates=templates, repository_source_hashes=hashes)


def test_template_runtime_literal_tamper_refuses_despite_rebound_template_hash(arguments):
    templates, hashes = dict(arguments['templates']), dict(arguments['repository_source_hashes'])
    name = b.PREFIX + 'extended_algorithm.py'
    raw = templates[name].replace(b'EXPECTED_ATTEMPT = __ATTEMPT_NUMBER__', b'EXPECTED_ATTEMPT = "__ATTEMPT_NUMBER__"')
    templates[name], hashes[name] = raw, e.digest(raw)
    with pytest.raises(b.Refusal): render(arguments, templates=templates, repository_source_hashes=hashes)


def test_final_rendered_cloud_quota_checked_not_template_alone(arguments):
    templates, hashes = dict(arguments['templates']), dict(arguments['repository_source_hashes'])
    name = b.PREFIX + 'extended_loader.py'; raw = templates[name] + b'\n#' + b'x' * 20000
    assert len(raw) < 60000
    templates[name], hashes[name] = raw, e.digest(raw)
    with pytest.raises(b.Refusal): render(arguments, templates=templates, repository_source_hashes=hashes)


@pytest.mark.parametrize('change', ['null_provider', 'unknown_reason', 'missing_reason', 'bool_count'])
def test_source_refusal_census_is_closed_and_incomplete_is_not_zero(arguments, change):
    def mutate(body):
        if change == 'null_provider': body['source_refusal_census']['massive'] = None
        elif change == 'unknown_reason': body['source_refusal_census']['massive']['other'] = 0
        elif change == 'missing_reason': body['source_refusal_census']['massive'].pop('invalid_event_id')
        else: body['source_refusal_census']['massive']['invalid_event_id'] = True
    with pytest.raises(b.Refusal): altered_receipt(arguments, mutate)


@pytest.mark.parametrize('change', ['preparation_before_capture', 'naive_capture'])
def test_receipt_clock_order_and_awareness_bind_original_and_repair_captures(arguments, change):
    field, value = ('started_utc', '2026-10-10T00:00:00+00:00') if change == 'preparation_before_capture' else ('capture_utc', '2026-10-10T01:00:00')
    with pytest.raises(b.Refusal): altered_receipt(arguments, lambda body: body.__setitem__(field, value))


def test_receipt_key_contract_matches_current_public_producer_source_without_executing_it():
    import ast
    source = (ROOT / (b.PREFIX + 'extended_preparation.py')).read_text()
    tree = ast.parse(source)
    receipts = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'receipt' for target in node.targets)
        and isinstance(node.value, ast.Dict)]
    assert len(receipts) == 1
    assert {ast.literal_eval(key) for key in receipts[0].keys} == b.PREPARATION_KEYS


def test_renderer_output_obeys_actual_controller_manifest_and_readback_contract_without_operations(arguments):
    bundle = render(arguments)
    manifest = {'schema': 'tpr-ext26-operations-manifest-v1', 'study_id': e.STUDY_ID,
        'operation_id': 'SYNTHETIC-BUNDLE-INTEGRATION', 'created_utc': '2026-10-10T01:00:00+00:00',
        'expires_utc': '2026-10-11T01:00:00+00:00', 'git_head': 'a' * 40, 'freeze_sha256': e.FREEZE_SHA256,
        'preparation_sha256': bundle['preparation_sha256'], 'repository_source_hashes': arguments['repository_source_hashes'],
        'candidates': bundle['candidates'], 'inputs': bundle['inputs'], 'max_requests': 4096,
        'max_response_bytes': e.MAX_BYTES, 'request_seconds': 30, 'max_orders': 50000, 'max_collections': 3}
    candidates = o.validate_manifest(e.parse_json(e.canonical(manifest)))
    for row in candidates.values():
        source_manifest = {'schema': 'tpr-ext26-execution-manifest-v1', 'study_id': e.STUDY_ID,
            'freeze_sha256': e.FREEZE_SHA256, 'candidate_id': row['candidate_id'], 'arm': e.CANDIDATES[row['candidate_id']],
            'project_id': 123, 'baseline_git_sha': 'a' * 40, 'config_sha256': row['config_sha256'],
            'source_hashes': row['source_hashes'], 'input_hashes': row['input_hashes'], 'max_attempts': 3}
        envelope = e.canonical({'schema': 'tpr-ext26-request-response-v1', 'endpoint': 'files/read',
            'stage': 'source_readback', 'request': {'projectId': 123}, 'response': {'success': True,
                'files': [{'name': name, 'content': text} for name, text in row['files'].items()]}})
        assert e._readback(envelope, row['config_raw'].encode(), e.parse_json(e.canonical(source_manifest))) == row['source_hashes']
