"""Compressed lifecycle fixtures; no real credentials, files, projects or API."""
from copy import deepcopy
import json

import pytest
from research.target_price_revisions_qc import extended_operations_compressed as c
from test_qc_extended_operations import manifest as original_manifest, Cloud
from test_qc_extended_compressed_store import mapping

base, e, ON, OFF = c.base, c.e, c.ON, c.OFF


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    monkeypatch.setattr(c, 'PROJECT_IDS', {ON: 101, OFF: 102})
    monkeypatch.setattr(c, 'ORGANIZATION_SHA256', base.digest(b'synthetic-org'))
    def deny(*_args, **_kw): raise AssertionError('actual root/credential/network operation forbidden')
    monkeypatch.setattr(base, 'credential', deny); monkeypatch.setattr(base.http.client, 'HTTPSConnection', deny)
    old = base.Operations.guard
    def guard(self):
        assert self.fixture and not self.root.is_relative_to(base.LANE)
        return old(self)
    monkeypatch.setattr(base.Operations, 'guard', guard)


def body(*, compressed=True):
    result = original_manifest(operation='TPR-EXT26-QC-SYNTHETIC-003' if compressed else 'TPR-EXT26-QC-SYNTHETIC-002')
    map_body, store, originals = mapping()
    result['preparation_sha256'] = map_body['preparation_sha256']
    result['inputs'] = [{'name': row['plain_name'], 'sha256': row['plain_sha256'], 'bytes': row['plain_bytes'], 'key': row['logical_key']} for row in map_body['payloads']]
    for row in result['candidates']:
        config = e.parse_json(row['config_raw'].encode()); config['input_hashes']['preparation.json'] = result['preparation_sha256']
        row['input_hashes'], row['config_raw'] = config['input_hashes'], e.canonical(config).decode()
        row['files']['extended_config.py'] = 'CONFIG_JSON = ' + repr(row['config_raw']) + '\n'
        attempt = 2 if compressed and row['candidate_id'] == OFF else 1
        row['planned_attempt'] = attempt
        row['files']['main.py'] = 'EXPECTED_ATTEMPT = ' + str(attempt) + '\nEXPECTED_CONFIG_SHA256 = ' + repr(e.digest(row['config_raw'].encode())) + '\n'
        if compressed:
            row['files']['extended_runtime_successor.py'] = '# pure synthetic successor\n'
            row['files']['extended_compressed_store.py'] = '# pure synthetic gzip adapter\n'
            if row['candidate_id'] == ON: row['files'].update(c.bundle._packets(c.storage.canonical(map_body)))
    result['repository_source_hashes'].update({name: 'd' * 64 for name in c.REQUIRED})
    result['repository_source_hashes'][c.PREFIX + 'extended_operations.py'] = c.previous.BASE_SOURCE_SHA256
    result['repository_source_hashes'][c.PREFIX + 'extended_driver.py'] = c.previous.BASE_DRIVER_SHA256
    return result, map_body, store, originals


def setup(tmp_path, *, closed_off=True):
    old_body, _, _, _ = body(compressed=False); cloud = Cloud()
    normal = cloud.__call__
    def transport(endpoint, raw, content_type):
        response = e.parse_json(normal(endpoint, raw, content_type))
        if endpoint == 'backtests/read': response['backtest'].update(status='Runtime Error', error='RuntimeError: synthetic initialization')
        return e.canonical(response)
    old = base.Operations(old_body, manifest_sha256=e.digest(e.canonical(old_body)), fixture_root=tmp_path / 'private', fixture_transport=transport)
    old.prepare(); old.create_project(ON); old.create_project(OFF)
    if closed_off:
        old.upload_sources(OFF); old.reserve(OFF); old.compile(OFF, 1); old.compile_status(OFF, 1); old.launch(OFF, 1); old.status(OFF, 1)
    new_body, map_body, store, originals = body()
    fresh = c.Operations(new_body, manifest_sha256=e.digest(e.canonical(new_body)), fixture_root=old.root, fixture_transport=transport)
    fresh.prepare()
    leaf = old.root / 'fixture-inputs'; leaf.mkdir(mode=0o700)
    for row in map_body['payloads']:
        path = leaf / row['stored_name']; path.write_bytes(store.values[row['stored_key']]); path.chmod(0o600)
    return old, fresh, cloud, map_body


def ready(controller, candidate, attempt):
    controller.upload_sources(candidate); controller.reserve(candidate); controller.compile(candidate, attempt); controller.compile_status(candidate, attempt)


def test_off2_before_on_uploads_preserves_off1_failure_and_both_arm_look_census(tmp_path):
    old, controller, cloud, _ = setup(tmp_path)
    old_raw = {suffix: old.read(OFF + '.attempt.1.' + suffix) for suffix in ('manifest.json', 'reservation.json', 'closure.json', 'look.json', 'terminal.json')}
    ready(controller, OFF, 2); controller.launch(OFF, 2)
    assert controller.history(OFF)[0] == 2 and controller.history(ON)[0] == 0
    for suffix, raw in old_raw.items(): assert controller.read(OFF + '.attempt.1.' + suffix) == raw
    look = controller.value(OFF + '.attempt.2.look.json')
    assert look['old_looks'].fraction() == look['observed_total_before'].fraction() == 17
    assert look['persistent_observed_looks_before'].fraction() == 1
    assert not list(controller.root.glob('compressed-input.*.read.spent.json'))
    controller.upload_inputs(ON); ready(controller, ON, 1); controller.launch(ON, 1)
    look = controller.value(ON + '.attempt.1.look.json')
    assert look['old_looks'].fraction() == 18 and look['persistent_observed_looks_before'].fraction() == 2
    assert cloud.calls.count('projects/create') == 2 and cloud.calls.count('object/set') == 72
    assert not list(controller.root.glob('input.*.completed.json'))
    assert controller.history(ON)[0] == 1
    assert c.Operations.history is base.Operations.history and c.Operations.reserve is base.Operations.reserve


def test_upload_claims_before_exact72_compressed_reads_and_no_original_reads(tmp_path, monkeypatch):
    _, controller, cloud, mapping_body = setup(tmp_path, closed_off=False)
    read, seen = base.read_private, []
    names = {row['stored_name']: row for row in mapping_body['payloads']}
    def reading(root, name, maximum=e.MAX_BYTES):
        if name in names:
            row = names[name]
            assert (controller.root / ('compressed-input.' + row['gzip_sha256'] + '.read.spent.json')).exists()
            assert maximum == row['gzip_bytes']; seen.append(name)
        assert not (name.endswith('.json') and len(name) == 69 and name[:64].isalnum())
        return read(root, name, maximum)
    monkeypatch.setattr(base, 'read_private', reading)
    result = controller.upload_inputs(ON)
    assert result['uploaded_count'] == 72 and result['original_upload_success_synthesized'] is False
    assert len(seen) == 72 and cloud.calls.count('object/set') == 72
    with pytest.raises(ValueError): controller.upload_inputs(ON)
    with pytest.raises(ValueError): controller.upload_inputs(OFF)
    assert cloud.calls.count('object/set') == 72


@pytest.mark.parametrize('kind', ['absent', 'wrong_mapping', 'wrong_plain', 'wrong_key', 'wrong_bytes'])
def test_on_launch_without_all72_exact_transport_receipts_refuses_no_look(tmp_path, kind):
    _, controller, cloud, map_body = setup(tmp_path, closed_off=False)
    if kind != 'absent':
        for row in controller.transport_rows: controller.write('compressed-input.' + row['gzip_sha256'] + '.completed.json', controller._completed(row))
        row = controller.transport_rows[0]; name = 'compressed-input.' + row['gzip_sha256'] + '.completed.json'; path = controller.root / name
        value = controller.value(name)
        key = {'wrong_mapping': 'mapping_sha256', 'wrong_plain': 'plain_sha256', 'wrong_key': 'stored_key', 'wrong_bytes': 'gzip_bytes'}[kind]
        value[key] = e.JsonNumber('1') if kind == 'wrong_bytes' else 'foreign'
        path.write_bytes(e.canonical(value))
    ready(controller, ON, 1)
    before = cloud.calls.count('backtests/create')
    with pytest.raises(ValueError): controller.launch(ON, 1)
    assert cloud.calls.count('backtests/create') == before and not (controller.root / (ON + '.attempt.1.look.json')).exists()


@pytest.mark.parametrize('kind', ['cap_reset', 'main_attempt', 'config', 'packet_extra', 'source_missing', 'off_signal'])
def test_constructor_refuses_adaptive_attempt_or_packet_scope_changes(tmp_path, kind):
    data, _, _, _ = body(); row = data['candidates'][1]
    if kind == 'cap_reset': row['planned_attempt'] = 1
    if kind == 'main_attempt': row['files']['main.py'] = row['files']['main.py'].replace('EXPECTED_ATTEMPT = 2', 'EXPECTED_ATTEMPT = 1')
    if kind == 'config': row['files']['main.py'] = row['files']['main.py'].replace(e.digest(row['config_raw'].encode()), 'a' * 64)
    if kind == 'packet_extra': data['candidates'][0]['files']['compressed_packet_extra.py'] = '# unexpected\n'
    if kind == 'source_missing': data['repository_source_hashes'].pop(c.PREFIX + 'extended_operations_compressed.py')
    if kind == 'off_signal': row['files']['signal_packet.py'] = 'CONFIG_JSON = "{}"\n'
    with pytest.raises(ValueError): c.Operations(data, manifest_sha256=e.digest(e.canonical(data)), fixture_root=tmp_path / 'private', fixture_transport=Cloud())


def test_unclosed_off1_cannot_reset_or_reserve_off2(tmp_path):
    _, controller, _, _ = setup(tmp_path, closed_off=False)
    controller.upload_sources(OFF)
    with pytest.raises(ValueError): controller.reserve(OFF)
    assert controller.history(OFF)[0] == 0


def test_no_new_project_adoption_or_original_plaintext_upload_route(tmp_path):
    _, controller, cloud, _ = setup(tmp_path, closed_off=False)
    calls = list(cloud.calls)
    with pytest.raises(ValueError): controller.create_project(ON)
    with pytest.raises(ValueError): controller.recover_project(ON)
    with pytest.raises(ValueError): controller.effect('object/set', b'plaintext', 'input.' + 'a' * 64 + '.upload')
    assert cloud.calls == calls


@pytest.mark.parametrize('candidate', [ON, OFF])
@pytest.mark.parametrize('kind', ['organization', 'project'])
def test_changed_receipt_destination_refuses_before_any_api(tmp_path, candidate, kind):
    _, controller, cloud, _ = setup(tmp_path, closed_off=False)
    name = candidate + '.project.json'
    row = controller.value(name)
    row['organization_id' if kind == 'organization' else 'project_id'] = 'foreign-org' if kind == 'organization' else 999
    (controller.root / name).write_bytes(e.canonical(row))
    calls = list(cloud.calls)
    with pytest.raises(ValueError): controller.upload_sources(candidate)
    if candidate == ON:
        with pytest.raises(ValueError): controller.upload_inputs(candidate)
    assert cloud.calls == calls
