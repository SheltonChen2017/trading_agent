"""Fabricated saved compact parts; never protected source or credential reads."""
from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from data.hashing import canonical_json, hash_bytes, hash_payload
from short_interest_capture_fixtures import portable_capture_platform
from test_short_interest_native_population_class_matrix import assemble, row
import scripts.load_short_interest_native_class_matrix as loader

HEAD, REMOTE = 'a' * 40, 'b' * 40


def encoded(value):
    return (canonical_json(value) + '\n').encode()


@pytest.fixture
def saved(monkeypatch, tmp_path):
    source = assemble({1: [row('FAKE')], 33: [row('OTHER', '2023-03-15')]})
    header, queries, refusals = source.parts()
    payload = source.header()
    policy = loader.matrix.matrix_policy()
    pins = copy.deepcopy(loader.SOURCE_PINS)
    pins['report_bytes_sha256'] = payload['source_manifest_bytes_sha256']
    monkeypatch.setattr(loader, 'SOURCE_PINS', pins)
    monkeypatch.setattr(loader, 'SOURCE_MANIFEST_PAYLOAD_SHA256', payload['source_manifest_payload_sha256'])
    monkeypatch.setattr(loader, 'SOURCE_POLICY_SHA256', hash_payload(policy))
    monkeypatch.setattr(loader, 'MATRIX_SHA256', source.sha256)
    counters = dict.fromkeys(loader.COUNTERS, 0)
    protocol = {'schema': 'si-native-full-population-matrix-offline-v1', 'code_head': loader.SOURCE_HEAD,
                'source_pins': pins, 'matrix_policy': policy, 'matrix_policy_sha256': hash_payload(policy), **counters}
    monkeypatch.setattr(loader, 'SOURCE_PROTOCOL_SHA256', hash_payload(protocol))
    start = {'schema': 'si-native-full-population-matrix-start-v1', 'code_head': loader.SOURCE_HEAD,
             'protocol_sha256': loader.SOURCE_PROTOCOL_SHA256, 'started_at': loader.SOURCE_START, **counters}
    complete = {'schema': 'si-native-full-population-matrix-complete-v1', 'status': 'private_source_matrix_complete',
                'code_head': loader.SOURCE_HEAD, 'protocol_sha256': loader.SOURCE_PROTOCOL_SHA256,
                'completed_at': loader.SOURCE_COMPLETED, 'backtest_result_exists': False, **counters}
    files = {'protocol.private.json': encoded(protocol), 'started.json': encoded(start),
             'completed.json': encoded(complete), 'header.private.json': header,
             'queries.private.bin': queries, 'refusals.private.bin': refusals}
    monkeypatch.setattr(loader, 'FILE_PINS', {name: hash_bytes(raw) for name, raw in files.items()})
    directory = tmp_path / loader.SOURCE
    directory.mkdir(parents=True)
    for name in files: (directory / name).touch()
    events = []
    monkeypatch.setattr(loader, '_guard', lambda *args: events.append('guard'))
    monkeypatch.setattr(loader, '_historical_policy', lambda *args, **kwargs: policy)
    def read(path, maximum):
        assert events[-1] == 'guard'
        assert maximum == loader.LIMITS[path.name]
        events.append(path.name)
        return files[path.name]
    monkeypatch.setattr(loader, '_protected_bytes', read)
    return tmp_path, files, source, events


@pytest.mark.usefixtures('portable_capture_platform')
def test_exact_six_saved_parts_reload_without_raw_chain_or_secret_reads(saved):
    root, _, source, events = saved
    result = loader.load_matrix(root, head=HEAD, remote=REMOTE)
    assert type(result) is loader.matrix.NativePopulationClassMatrix and result.parts() == source.parts()
    assert list(result.iter_queries()) == list(source.iter_queries())
    assert events[-1] == 'guard'
    assert [event for event in events if event != 'guard'] == list(loader.FILE_PINS)
    assert result.header()['authority']['actual_input_execution_admitted'] is False


@pytest.mark.parametrize('name', list(loader.FILE_PINS))
@pytest.mark.usefixtures('portable_capture_platform')
def test_every_registered_saved_file_byte_is_checked_before_typed_rebuild(saved, monkeypatch, name):
    root, files, _, _ = saved
    files[name] += b' '
    monkeypatch.setattr(loader.matrix, 'rebuild_native_population_class_matrix', lambda *args: pytest.fail('factory reached'))
    with pytest.raises(loader.CaptureRefusal, match='registered_file_bytes'):
        loader.load_matrix(root, head=HEAD, remote=REMOTE)


@pytest.mark.parametrize('extra', ['unexpected.raw', 'budget-reset.json', 'header.json'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_extra_inventory_name_is_not_credential_download_or_custody_authority(saved, extra):
    root, _, _, _ = saved
    (root / loader.SOURCE / extra).touch()
    with pytest.raises(loader.CaptureRefusal, match='six_file_inventory'):
        loader.load_matrix(root, head=HEAD, remote=REMOTE)


@pytest.mark.parametrize('kind', ['bool_counter', 'nonzero_counter', 'true_backtest', 'head', 'protocol', 'status', 'clock', 'source_manifest'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_coherently_rehashed_metadata_does_not_admit_counters_lineage_or_clocks(saved, monkeypatch, kind):
    root, files, _, _ = saved
    name = 'header.private.json' if kind == 'source_manifest' else 'completed.json'
    value = json.loads(files[name])
    if kind == 'bool_counter': value['outcome_looks'] = False
    elif kind == 'nonzero_counter': value['qc_attempts'] = 1
    elif kind == 'true_backtest': value['backtest_result_exists'] = True
    elif kind == 'head': value['code_head'] = 'f' * 40
    elif kind == 'protocol': value['protocol_sha256'] = 'f' * 64
    elif kind == 'status': value['status'] = 'market_source_admitted'
    elif kind == 'clock': value['completed_at'] = '2026-10-13T00:00:00Z'
    else: value['source_manifest_payload_sha256'] = 'f' * 64
    files[name] = encoded(value)
    monkeypatch.setitem(loader.FILE_PINS, name, hash_bytes(files[name]))
    with pytest.raises(loader.CaptureRefusal): loader.load_matrix(root, head=HEAD, remote=REMOTE)


@pytest.mark.usefixtures('portable_capture_platform')
def test_opaque_source_pin_never_followed_when_protocol_bytes_are_not_registered(saved, monkeypatch):
    root, files, _, _ = saved
    value = json.loads(files['protocol.private.json'])
    value['source_pins']['child_run'] = '/unknown/secret/file'
    files['protocol.private.json'] = encoded(value)
    monkeypatch.setitem(loader.FILE_PINS, 'protocol.private.json', hash_bytes(files['protocol.private.json']))
    monkeypatch.setattr(loader, 'SOURCE_PROTOCOL_SHA256', hash_payload(value))
    with pytest.raises(loader.CaptureRefusal, match='offline_protocol_binding'):
        loader.load_matrix(root, head=HEAD, remote=REMOTE)


@pytest.mark.usefixtures('portable_capture_platform')
def test_publication_or_source_race_guard_is_rechecked_after_every_read(saved, monkeypatch):
    root, _, _, events = saved
    def guard(*args):
        if 'queries.private.bin' in events: raise loader.CaptureRefusal('concurrent_lane_changed')
        events.append('guard')
    monkeypatch.setattr(loader, '_guard', guard)
    with pytest.raises(loader.CaptureRefusal, match='concurrent_lane_changed'):
        loader.load_matrix(root, head=HEAD, remote=REMOTE)
    assert 'refusals.private.bin' not in events


def test_unsupported_host_refuses_first_before_git_files_or_parser(monkeypatch):
    def refuse(): raise loader.CaptureRefusal('unsupported_host')
    monkeypatch.setattr(loader, '_require_capture_platform', refuse)
    for name in ('_guard', '_historical_policy', '_protected_bytes'):
        monkeypatch.setattr(loader, name, lambda *args, **kwargs: pytest.fail('after first host guard'))
    with pytest.raises(loader.CaptureRefusal, match='unsupported_host'):
        loader.load_matrix(Path('/fabricated'), head=HEAD, remote=REMOTE)


@pytest.mark.parametrize('kind', ['valid', 'wrong_blob', 'policy_changed', 'not_ancestor'])
@pytest.mark.usefixtures('portable_capture_platform')
def test_historical_policy_checks_exact_committed_blob_without_invented_receipt_metadata(tmp_path, monkeypatch, kind):
    raw = (inspect.getsource(loader.matrix._authority) + '\n' + inspect.getsource(loader.matrix.matrix_policy)).encode()
    target = tmp_path / loader.MODULE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(raw if kind != 'policy_changed' else raw.replace(b'NoSuchLiteral', b'NoSuchOtherLiteral') + b'\n')
    if kind == 'policy_changed':
        target.write_bytes(raw.replace(b'"schema":', b'"changed_schema":'))
    monkeypatch.setattr(loader, 'HISTORICAL_MODULE_SHA256', hash_bytes(raw))
    calls = []
    def git(args, **kwargs):
        calls.append(args)
        if args[1] == 'merge-base': return SimpleNamespace(returncode=1 if kind == 'not_ancestor' else 0, stdout=b'')
        return SimpleNamespace(returncode=0, stdout=raw if kind != 'wrong_blob' else raw + b'\n')
    monkeypatch.setattr(loader.subprocess, 'run', git)
    monkeypatch.setattr(loader, '_guard', lambda *args: None)
    if kind == 'valid':
        assert loader._historical_policy(tmp_path, head=HEAD, remote=REMOTE) == loader.matrix.matrix_policy()
    else:
        with pytest.raises(loader.CaptureRefusal): loader._historical_policy(tmp_path, head=HEAD, remote=REMOTE)
    assert calls[0] == ['git', 'merge-base', '--is-ancestor', loader.SOURCE_HEAD, HEAD]
