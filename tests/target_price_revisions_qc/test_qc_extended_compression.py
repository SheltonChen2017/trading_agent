"""Fresh compression claims and custody fixtures; real paths/network denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import subprocess

import pytest
from research.target_price_revisions_qc import extended_compression as d

e = d.e


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    import http.client
    def deny(*_args, **_kw): raise AssertionError('actual network/credential/private/repository call forbidden')
    monkeypatch.setattr(http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(subprocess, 'run', deny)
    original = d._open_directory
    def opening(path):
        assert not path.is_relative_to(d.LANE)
        return original(path)
    monkeypatch.setattr(d, '_open_directory', opening)


def fixture(tmp_path, monkeypatch):
    preparation, prefix = 'b' * 64, 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + 'b' * 64 + '/'
    values, inputs = {}, []
    for index in range(72):
        raw = ('{"synthetic":' + str(index) + ',"content":"PRIVATE-LICENSED-SENTINEL-' + 'repeated' * 100 + '"}').encode()
        identity = d._sha(raw); name = identity + '.json'
        values[name] = raw; inputs.append({'name': name, 'sha256': identity, 'bytes': len(raw), 'key': prefix + name})
    inputs.sort(key=lambda row: row['name'])
    bundle = e.canonical({'schema': 'tpr-ext26-source-bundle-v1', 'inputs': inputs,
        'candidates': [], 'repository_sources': [], 'preparation_sha256': preparation})
    monkeypatch.setattr(d, 'BUNDLE_SHA256', d._sha(bundle)); monkeypatch.setattr(d, 'ORIGINAL_BYTES', sum(map(len, values.values())))
    sources = {name: b'# synthetic committed source\n' for name in d.SOURCE_PATHS}; sources[d.BUNDLE] = bundle
    now = datetime.now(timezone.utc)
    plan = d._plan(source_hashes={name: d._sha(raw) for name, raw in sources.items()}, git_head='a' * 40,
        owner_instruction_sha256='c' * 64, created_utc=(now - timedelta(seconds=1)).isoformat(),
        expires_utc=(now + timedelta(hours=1)).isoformat(), operation_id='TPR-EXT26-COMPRESS-SYNTHETIC-001',
        bundle_raw=bundle, expected_bundle_sha256=d._sha(bundle), mode='offline-fixture')
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    for name, raw in values.items(): (root / name).write_bytes(raw); (root / name).chmod(0o600)
    return plan, sources, root, values, now


def execute(f):
    plan, sources, root, _, now = f
    return e.parse_json(d._execute(plan, sources, root, clock=lambda: now, guard=lambda *_: None))


def test_claim_precedes_all_72_original_reads_roundtrip_and_preserves_originals(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); original = d._read; seen = []
    stats = {name: (f[2] / name).stat() for name in f[3]}
    def read(directory, name, **kw):
        assert (f[2] / (f[0]['operation_id'] + '.claim.spent.json')).is_file()
        seen.append(name)
        return original(directory, name, **kw)
    monkeypatch.setattr(d, '_read', read)
    report = execute(f)
    assert report['status'] == 'COMPLETED' and report['scope_spent'] is True
    assert report['processed_count'].fraction() == 72 and report['original_bytes'].fraction() == sum(map(len, f[3].values()))
    assert report['gzip_bytes'].fraction() < report['original_bytes'].fraction()
    assert report['originals_retained_unchanged'] is report['decompressed_bytes_exact'] is True
    assert sum(name in f[3] for name in seen) == 144
    for name, raw in f[3].items():
        path = f[2] / name; after = path.stat(); before = stats[name]
        assert path.read_bytes() == raw and after.st_ino == before.st_ino and after.st_mtime_ns == before.st_mtime_ns
    for row in report['payloads']:
        encoded = (f[2] / row['stored_name']).read_bytes()
        assert d.storage.decode_gzip(encoded, plain_bytes=int(row['plain_bytes'].fraction()), plain_sha256=row['plain_sha256'],
            gzip_bytes=int(row['gzip_bytes'].fraction()), gzip_sha256=row['gzip_sha256']) == f[3][row['plain_name']]
    mapping_raw = (f[2] / report['mapping_name']).read_bytes()
    assert d._sha(mapping_raw) == report['mapping_sha256']
    assert b'PRIVATE-LICENSED-SENTINEL' not in e.canonical(report) and b'PRIVATE-LICENSED-SENTINEL' not in mapping_raw
    assert report['quantconnect_attempts'].fraction() == report['development_looks'].fraction() == 0
    with pytest.raises(FileExistsError): execute(f)


@pytest.mark.parametrize('kind', ['changed', 'missing', 'mode', 'symlink', 'hardlink', 'oversize', 'derived_collision', 'derived_budget', 'source_changed', 'roundtrip'])
def test_failed_processing_retains_originals_and_consumed_claim(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); name = f[0]['inputs'][0]['name']; path = f[2] / name
    if kind == 'changed': path.write_bytes(b'changed')
    if kind == 'missing': path.unlink()
    if kind == 'mode': path.chmod(0o644)
    if kind == 'symlink':
        target = f[2] / 'other'; target.write_bytes(path.read_bytes()); target.chmod(0o600); path.unlink(); path.symlink_to(target)
    if kind == 'hardlink': os.link(path, f[2] / 'hardlink')
    if kind == 'oversize':
        with path.open('ab') as stream: stream.truncate(d.MAX_FILE + 1)
    if kind == 'derived_collision':
        encoded = d.storage.encode_gzip(f[3][name]); collision = f[2] / ('gzip.' + d._sha(encoded) + '.json')
        collision.write_bytes(b'preserve'); collision.chmod(0o600)
    if kind == 'derived_budget': monkeypatch.setattr(d, 'MAX_DERIVED', 1); f[0]['max_derived_bytes'] = 1
    if kind == 'source_changed':
        f[1][d.PREFIX + 'extended_compression.py'] += b'# unbound changed source'
        with pytest.raises(ValueError): execute(f)
        assert not (f[2] / (f[0]['operation_id'] + '.claim.spent.json')).exists()
        return
    if kind == 'roundtrip':
        real = d.storage.decode_gzip; calls = [0]
        def wrong(*args, **kw):
            calls[0] += 1
            return real(*args, **kw) if calls[0] != 2 else b'wrong'
        monkeypatch.setattr(d.storage, 'decode_gzip', wrong)
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and answer['scope_spent'] is True
    assert answer['originals_retained_unchanged'] is False and answer['decompressed_bytes_exact'] is False
    assert answer['failure'] == 'refused_or_bound_hit_no_retry'
    assert (f[2] / (f[0]['operation_id'] + '.claim.spent.json')).is_file()
    if kind == 'derived_collision': assert collision.read_bytes() == b'preserve'
    for other, raw in f[3].items():
        if other != name: assert (f[2] / other).read_bytes() == raw


def test_24h_scope_900s_bound_fixed_inventory_and_expected_bundle(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); plan = f[0]
    args = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc', 'operation_id', 'mode')}
    args.update(bundle_raw=f[1][d.BUNDLE], expected_bundle_sha256=d.BUNDLE_SHA256)
    assert d._plan(**args)['max_seconds'] == 900
    with pytest.raises(ValueError): d._plan(**{**args, 'expected_bundle_sha256': 'd' * 64})
    with pytest.raises(ValueError): d._plan(**{**args, 'expires_utc': (f[4] + timedelta(hours=25)).isoformat()})
    with pytest.raises(ValueError): d._plan(**{**args, 'operation_id': '../arbitrary'})
    with pytest.raises(ValueError): d._execute(plan, f[1], d.PRIVATE_ROOT, clock=lambda: f[4], guard=lambda *_: None)


def test_cli_refusal_does_not_echo_private_errors(monkeypatch, capsys):
    def refused(**_kw): raise ValueError('PRIVATE-LICENSED-SENTINEL TOKEN-123')
    monkeypatch.setattr(d, 'run', refused)
    assert d.main(['--operation-id', 'TPR-EXT26-COMPRESS-SYNTHETIC-001', '--owner-instruction-sha256', 'a' * 64,
        '--created-utc', '2026-10-10T00:00:00+00:00', '--expires-utc', '2026-10-10T01:00:00+00:00',
        '--expected-bundle-sha256', 'b' * 64]) == 1
    output = capsys.readouterr().out
    assert 'PRIVATE-LICENSED-SENTINEL' not in output and 'TOKEN-123' not in output
