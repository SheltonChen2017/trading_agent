"""Lossless cloud transport fixtures only; no actual storage/network/operator I/O."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import subprocess

import pytest
from research.target_price_revisions_qc import extended_compressed_store as s
from tests.target_price_revisions_qc.test_qc_extended_runtime import runtime, signal_fixture, binding


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    import http.client
    def deny(*_args, **_kw): raise AssertionError('actual API/credential/operator/private calls forbidden')
    monkeypatch.setattr(http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(subprocess, 'run', deny)


class Native:
    def __init__(self, values=None): self.values, self.reads, self.saves, self.checks = dict(values or {}), [], [], []
    def contains_key(self, key): self.checks.append(key); return key in self.values
    def read_bytes(self, key): self.reads.append(key); return self.values[key]
    def save_bytes(self, key, raw):
        self.saves.append(key)
        assert key not in self.values
        self.values[key] = bytes(raw)
        return True


def mapping(values=None):
    preparation = 'b' * 64
    prefix = 'tpr-ext26/inputs/' + s.STUDY + '/' + preparation + '/'
    if values is None:
        values = {}
        for number in range(72):
            raw = ('{"synthetic":' + str(number) + ',"unicode":"é"}').encode()
            values[prefix + s.sha256(raw) + '.json'] = raw
    rows, stored = [], {}
    for logical, raw in sorted(values.items()):
        if type(raw) is str: raw = raw.encode()
        compressed = s.encode_gzip(raw)
        sha = s.sha256(compressed); name = 'gzip.' + sha + '.json'; key = prefix + name
        rows.append({'plain_name': s.sha256(raw) + '.json', 'logical_key': logical,
            'plain_sha256': s.sha256(raw), 'plain_bytes': len(raw), 'stored_name': name, 'stored_key': key,
            'gzip_sha256': sha, 'gzip_bytes': len(compressed)})
        stored[key] = compressed
    body = {'schema': 'tpr-ext26-gzip-input-map-v1', 'study_id': s.STUDY, 'freeze_sha256': s.FREEZE_SHA256,
        'preparation_sha256': preparation, 'bundle_sha256': 'c' * 64,
        'processing_operation_id': 'TPR-EXT26-COMPRESS-SYNTHETIC-001', 'processing_plan_sha256': 'd' * 64,
        'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'payloads': rows}
    return body, Native(stored), values


def test_deterministic_single_member_gzip_exact_roundtrip():
    raw = ('{"value":"é","unchanged":"' + 'xyz' * 5000 + '"}').encode()
    first = s.encode_gzip(raw); assert first == s.encode_gzip(raw) and len(first) < len(raw)
    assert first[3] == 0 and first[4:8] == b'\0\0\0\0'
    assert s.decode_gzip(first, plain_bytes=len(raw), plain_sha256=s.sha256(raw), gzip_bytes=len(first), gzip_sha256=s.sha256(first)) == raw


def test_memoryview_multibyte_preallocation_bound_and_python_clr_spoof(monkeypatch):
    from array import array
    calls, original = [], bytes
    def allocating(value): calls.append(True); return original(value)
    monkeypatch.setattr(s, 'bytes', allocating, raising=False)
    with pytest.raises(ValueError): s._bytes(memoryview(array('I', [1, 2])), 2)
    assert not calls
    monkeypatch.delattr(s, 'bytes')
    class Spoof:
        Length = 1
        def GetType(self): return type('ReportedType', (), {'FullName': 'System.Byte[]'})()
        def __bytes__(self): raise AssertionError('arbitrary Python coercion must not execute')
    with pytest.raises(ValueError): s._bytes(Spoof(), 64)


@pytest.mark.parametrize('kind', ['hash', 'compressed_hash', 'plain_size', 'compressed_size', 'truncated', 'tail', 'concatenated', 'bomb', 'wrong_content', 'zero', 'negative', 'bool'])
def test_decoder_refuses_corruption_tails_false_hashes_and_predefined_bounds(kind):
    raw = b'plain'; encoded = s.encode_gzip(raw)
    args = dict(plain_bytes=len(raw), plain_sha256=s.sha256(raw), gzip_bytes=len(encoded), gzip_sha256=s.sha256(encoded))
    if kind == 'hash': args['plain_sha256'] = 'a' * 64
    if kind == 'compressed_hash': args['gzip_sha256'] = 'a' * 64
    if kind == 'plain_size': args['plain_bytes'] += 1
    if kind == 'compressed_size': args['gzip_bytes'] += 1
    if kind in {'truncated', 'tail', 'concatenated', 'bomb', 'wrong_content'}:
        encoded = encoded[:-1] if kind == 'truncated' else encoded + b'tail' if kind == 'tail' else encoded + encoded if kind == 'concatenated' else s.encode_gzip(b'p' * 10000) if kind == 'bomb' else s.encode_gzip(b'other')
        args.update(gzip_bytes=len(encoded), gzip_sha256=s.sha256(encoded))
    if kind == 'zero': args['plain_bytes'] = 0
    if kind == 'negative': args['plain_bytes'] = -1
    if kind == 'bool': args['plain_bytes'] = True
    with pytest.raises(ValueError): s.decode_gzip(encoded, **args)


def test_input_proxy_reads_only_exact_compressed_targets_and_retains_plaintext():
    body, native, originals = mapping(); raw_map = s.canonical(body)
    proxy = s.CompressedInputStore(native, raw_map, expected_mapping_sha256=s.sha256(raw_map))
    for logical, original in originals.items():
        assert proxy.contains_key(logical) is True
        assert proxy.read(logical).encode() == original
    assert proxy.read_count == 72 and not native.saves
    assert all('/gzip.' in key for key in native.reads)
    with pytest.raises(ValueError): proxy.read('unrelated/project/key')
    with pytest.raises(ValueError): proxy.contains_key(body['payloads'][0]['stored_key'])


def test_missing_compressed_object_never_falls_back_to_existing_plaintext():
    body, native, originals = mapping(); row = body['payloads'][0]
    native.values.pop(row['stored_key']); native.values[row['logical_key']] = originals[row['logical_key']]
    proxy = s.CompressedInputStore(native, s.canonical(body))
    assert proxy.contains_key(row['logical_key']) is False
    with pytest.raises(ValueError): proxy.read(row['logical_key'])
    assert not native.reads


@pytest.mark.parametrize('kind', ['duplicate', 'wrong_prefix', 'wrong_study', 'mtime', 'encoding', 'float_size', 'extra', 'missing', 'hash', 'wrong_payload'])
def test_mapping_closed_identity_and_transport_contract(kind):
    body, native, _ = mapping(); row = body['payloads'][0]
    if kind == 'duplicate': body['payloads'][1] = deepcopy(row)
    if kind == 'wrong_prefix': row['stored_key'] = row['stored_key'].replace('/' + 'b' * 64 + '/', '/' + 'a' * 64 + '/')
    if kind == 'wrong_study': body['study_id'] = 'foreign'
    if kind == 'mtime': body['gzip_mtime'] = 1
    if kind == 'encoding': body['encoding'] = 'identity'
    if kind == 'float_size': row['plain_bytes'] = 5.0
    if kind == 'extra': row['secret'] = 'refuse'
    if kind == 'missing': body['payloads'].pop()
    if kind == 'hash': row['gzip_sha256'] = 'invalid'
    if kind == 'wrong_payload': native.values[row['stored_key']] = s.encode_gzip(b'changed')
    with pytest.raises(ValueError):
        proxy = s.CompressedInputStore(native, s.canonical(body))
        proxy.read(row['logical_key'])


def test_all_301_original_signal_frames_match_through_compressed_proxy(runtime):
    manifest, original_store = signal_fixture(runtime)
    manifest_raw = json.dumps(manifest, sort_keys=True, separators=(',', ':'))
    manifest_key = 'tpr-ext26/inputs/' + s.STUDY + '/' + 'b' * 64 + '/' + s.sha256(manifest_raw.encode()) + '.json'
    values = dict(original_store.values); values[manifest_key] = manifest_raw
    body, native, _ = mapping(values)
    compressed = s.CompressedInputStore(native, s.canonical(body))
    baseline = runtime.core.SignalStore(original_store, manifest_raw, s.sha256(manifest_raw.encode()), 'b' * 64)
    candidate = runtime.core.SignalStore(compressed, manifest_raw, s.sha256(manifest_raw.encode()), 'b' * 64)
    assert candidate.identities == baseline.identities
    for day in runtime.core.DECISIONS: assert candidate.frame(day) == baseline.frame(day)
    assert candidate.loaded_bytes == baseline.loaded_bytes and compressed.read_count == len(original_store.reads)


def test_original_full_journal_retained_through_both_arm_audit_adapters(runtime):
    for arm in s.CANDIDATES:
        bound = {**binding(runtime), 'candidate_id': arm}
        baseline, compressed = runtime.core.PrivateEvidence(bound), runtime.core.PrivateEvidence(bound)
        for day in runtime.core.VALUATIONS:
            for journal in (baseline, compressed): journal.append('NAV', {'session': day, 'nav': Fraction(100000), 'residual': Fraction(0)})
        for day in runtime.core.DECISIONS:
            for journal in (baseline, compressed): journal.append('COVERAGE', {'session': day, 'selected': 60})
        for journal in (baseline, compressed): journal.append('SUMMARY', {'canonical_admission': False})
        original = type('Plain', (), {'contains_key': lambda self, key: key in self.values,
            'save': lambda self, key, value: self.values.update({key: value}) or True,
            'read': lambda self, key: self.values[key]})()
        original.values = {}
        expected = baseline.export(original)
        native = Native(); adapter = s.CompressedAuditStore(native, bound)
        observed = compressed.export(adapter)
        assert expected == observed and baseline.records == compressed.records
        assert compressed.closed and adapter.closed
        for logical, raw in original.values.items(): assert adapter.read(logical) == raw
        sidecar = adapter.prefix + 'storage.json.gz'
        declaration_raw = s.canonical(adapter.storage_declaration)
        assert s.decode_gzip(native.values[sidecar], plain_bytes=len(declaration_raw), plain_sha256=s.sha256(declaration_raw), maximum=s.MAX_METADATA) == declaration_raw
        assert len(adapter.storage_declaration['objects']) == len(original.values)
        assert all(key.endswith('.json.gz') for key in native.values)
        assert adapter.storage_declaration['raw_journal_records_dropped'] is False
        assert adapter.storage_declaration['stored_bytes'] < adapter.storage_declaration['logical_bytes']


@pytest.mark.parametrize('kind', ['foreign', 'collision_plain', 'collision_gzip', 'save_false', 'readback', 'second_save', 'gap', 'too_big', 'sidecar_collision'])
def test_audit_failures_never_silently_drop_or_overwrite(runtime, kind):
    native = Native(); adapter = s.CompressedAuditStore(native, binding(runtime)); key = adapter.prefix + 'chunks00000.json'
    if kind == 'foreign': key = key.replace('/123/', '/124/')
    if kind == 'collision_plain': native.values[key] = b'preserve'
    if kind == 'collision_gzip': native.values[key + '.gz'] = b'preserve'
    if kind == 'save_false': native.save_bytes = lambda *_: False
    if kind == 'readback': native.read_bytes = lambda *_: b'altered'
    if kind == 'too_big':
        with pytest.raises(ValueError): adapter.save(key, 'x' * (s.MAX_CHUNK + 1))
        return
    if kind == 'gap': key = adapter.prefix + 'chunks00001.json'
    with pytest.raises(ValueError):
        adapter.save(key, '[{"kind":"NAV","payload":{}}]')
        if kind == 'second_save': adapter.save(key, '[]')
        else:
            if kind == 'sidecar_collision': native.values[adapter.prefix + 'storage.json.gz'] = b'preserve'
            adapter.save(adapter.prefix + 'index.json', '{}')
    assert not adapter.closed
    if kind in {'collision_plain', 'collision_gzip', 'foreign'}: assert not native.saves


def test_cloud_module_size_under_existing_60000_byte_ceiling():
    path = Path(__file__).resolve().parents[2] / 'research/target_price_revisions_qc/extended_compressed_store.py'
    assert path.stat().st_size < 60000
