from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import sys

import pytest

ROOT = Path(__file__).absolute().parents[2]
sys.path.insert(0, str(ROOT))
import scripts.verify_arv2_r286_price_capture as reader
import scripts.capture_arv2_sharadar_prices as adapter
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes

START = '2026-10-12T05:00:00.000000Z'
SOURCE_START = '2026-10-12T05:00:01.000000Z'
SOURCE_END = '2026-10-12T05:00:02.000000Z'
END = '2026-10-12T05:00:03.000000Z'
READ = datetime(2026, 10, 12, 5, 0, 4, tzinfo=timezone.utc)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    parent = tmp_path / 'synthetic-prices'
    parent.mkdir(mode=0o700)
    path = parent / adapter._artifact_id(SOURCE_START)
    path.mkdir(mode=0o700)
    responses = []
    for role, tickers in adapter.ROLE_TICKERS:
        payload = b'ticker,date,closeunadj,lastupdated\n' + b''.join(
            f'{ticker},2026-10-09,123.45,2026-10-09\n'.encode() for ticker in tickers)
        leaf = path / (role + '.csv')
        leaf.write_bytes(payload)
        leaf.chmod(0o600)
        responses.append(adapter._binding(payload, role, reader.SESSION))
    document = adapter._manifest(reader.SESSION, SOURCE_START, SOURCE_END,
                                 adapter.PRODUCTION_TRANSPORT, tuple(responses))
    raw = canonical_json_bytes(document)
    digest = sha256_bytes(raw)
    for name, payload in (('manifest.json', raw), ('manifest.sha256', (digest + '\n').encode())):
        leaf = path / name
        leaf.write_bytes(payload)
        leaf.chmod(0o600)
    monkeypatch.setattr(reader, 'PARENT', parent)
    monkeypatch.setattr(reader, 'now', lambda: READ)
    monkeypatch.setattr(reader, 'check_code', lambda: None)
    args = (str(path), digest, document['capture_sha256'], START, END, 0)
    return path, args


def test_good_real_loader_once_and_value_free_summary(fixture, monkeypatch):
    path, args = fixture
    original = adapter.load_sharadar_price_capture
    calls = []
    def load(*a, **kw):
        calls.append((a, kw))
        return original(*a, **kw)
    monkeypatch.setattr(adapter, 'load_sharadar_price_capture', load)
    result = reader.verify(*args)
    assert len(calls) == 1
    assert calls[0] == ((path,), {'expected_manifest_sha256': args[1]})
    assert result['file_count'] == 4 and result['stock_rows'] == 1 and result['fund_rows'] == 6
    assert result['readback_authenticated'] is True
    assert tuple(row['row_count'] for row in result['responses']) == (1, 6)
    assert all(len(row['csv_sha256']) == 64 and row['csv_byte_count'] > 0
               for row in result['responses'])
    assert all(result[key] is False for key in adapter.FALSE_FLAGS)
    assert result['native_acl_xattr_authenticated'] is False
    assert result['continuous_stability_proven'] is False
    assert '123.45' not in json.dumps(result)


@pytest.mark.parametrize('index,value', [
    (0, '/not/authorized/arv2-sharadar-prices-20261012T050001000000Z'),
    (1, 'not-a-hash'), (2, 'A' * 64), (3, '2026-10-12T05:00:00+00:00'),
    (4, '2026-10-12T13:20:00Z'), (5, 1), (5, True),
])
def test_bad_arguments_refuse_before_any_code_or_capture_open(fixture, monkeypatch, index, value):
    _, args = fixture
    changed = list(args)
    changed[index] = value
    monkeypatch.setattr(reader, 'check_code', lambda: pytest.fail('no source read permitted'))
    monkeypatch.setattr(reader, 'module', lambda: pytest.fail('no import permitted'))
    with pytest.raises(reader.Refusal):
        reader.verify(*changed)


@pytest.mark.parametrize('index', [1, 2])
def test_wrong_external_hash_refuses(fixture, index):
    _, args = fixture
    changed = list(args)
    changed[index] = '0' * 64
    with pytest.raises(ValueError):
        reader.verify(*changed)


@pytest.mark.parametrize('change', [
    {'close_session': '2026-10-08'},
    {'capture_transport': 'offline_test_double'},
    {'capture_started_at': '2026-10-12T04:59:59Z'},
    {'capture_completed_at': '2026-10-12T05:00:05Z'},
    {'artifact_path': Path('/another/path')},
    {'manifest_sha256': '0' * 64},
    {'capture_sha256': '0' * 64},
])
def test_returned_date_transport_time_and_binding_refusals(fixture, monkeypatch, change):
    _, args = fixture
    original = adapter.load_sharadar_price_capture
    def load(*a, **kw):
        return dataclasses.replace(original(*a, **kw), **change)
    monkeypatch.setattr(adapter, 'load_sharadar_price_capture', load)
    with pytest.raises(reader.Refusal):
        reader.verify(*args)


@pytest.mark.parametrize('kind', ['count', 'order', 'file', 'role'])
def test_census_refusals(fixture, monkeypatch, kind):
    _, args = fixture
    original = adapter.load_sharadar_price_capture
    def load(*a, **kw):
        result = original(*a, **kw)
        rows = list(result.responses)
        if kind == 'count':
            rows[0] = dataclasses.replace(rows[0], row_count=2)
        elif kind == 'order':
            rows.reverse()
        elif kind == 'file':
            rows[0] = dataclasses.replace(rows[0], csv_file='other.csv')
        else:
            rows[0] = dataclasses.replace(rows[0], role='funds')
        return dataclasses.replace(result, responses=tuple(rows))
    monkeypatch.setattr(adapter, 'load_sharadar_price_capture', load)
    with pytest.raises(reader.Refusal):
        reader.verify(*args)


@pytest.mark.parametrize('kind', ['directory_replace', 'directory_mode', 'leaf_replace', 'leaf_mtime', 'extra'])
def test_late_path_and_metadata_changes_refuse(fixture, monkeypatch, kind):
    path, args = fixture
    original = adapter.load_sharadar_price_capture
    def load(*a, **kw):
        result = original(*a, **kw)
        if kind == 'directory_replace':
            path.rename(path.with_name('retained-synthetic-original'))
            path.mkdir(mode=0o700)
        elif kind == 'directory_mode':
            path.chmod(0o755)
        elif kind == 'leaf_replace':
            leaf = path / 'stocks.csv'
            replacement = path / 'replacement'
            replacement.write_bytes(leaf.read_bytes())
            replacement.chmod(0o600)
            replacement.replace(leaf)
        elif kind == 'leaf_mtime':
            leaf = path / 'stocks.csv'
            info = leaf.stat()
            os.utime(leaf, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
        else:
            (path / 'unexpected').write_bytes(b'synthetic')
        return result
    monkeypatch.setattr(adapter, 'load_sharadar_price_capture', load)
    with pytest.raises(reader.Refusal):
        reader.verify(*args)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'mode', 'fifo'])
def test_unsafe_leaf_refuses_before_loader(fixture, monkeypatch, kind):
    path, args = fixture
    leaf = path / 'stocks.csv'
    if kind == 'symlink':
        leaf.rename(path.parent / 'synthetic-original')
        leaf.symlink_to(path.parent / 'synthetic-original')
    elif kind == 'hardlink':
        os.link(leaf, path.parent / 'synthetic-second-link')
    elif kind == 'mode':
        leaf.chmod(0o644)
    else:
        leaf.rename(path.parent / 'synthetic-original')
        os.mkfifo(leaf, 0o600)
    monkeypatch.setattr(adapter, 'load_sharadar_price_capture', lambda *a, **kw: pytest.fail('must not load'))
    with pytest.raises((reader.Refusal, OSError)):
        reader.verify(*args)


@pytest.mark.parametrize('instant', [reader.CUTOFF, reader.CUTOFF.replace(hour=14), READ.replace(hour=4)])
def test_final_read_time_refuses(fixture, monkeypatch, instant):
    _, args = fixture
    sequence = iter((READ, READ, instant))
    monkeypatch.setattr(reader, 'now', lambda: next(sequence))
    with pytest.raises(reader.Refusal):
        reader.verify(*args)


def test_clock_backwards_during_final_cleanup_refuses(fixture, monkeypatch):
    _, args = fixture
    sequence = iter((READ, READ.replace(second=READ.second + 1), READ))
    monkeypatch.setattr(reader, 'now', lambda: next(sequence))
    with pytest.raises(reader.Refusal):
        reader.verify(*args)


def test_selected_code_pins_and_wrong_pin(monkeypatch):
    reader.check_code()
    monkeypatch.setattr(reader, 'PINS', {next(iter(reader.PINS)): '0' * 64})
    with pytest.raises(reader.Refusal):
        reader.check_code()


def test_cli_success_and_redacted_failure(fixture, monkeypatch, capsys):
    _, args = fixture
    argv = ['--artifact', args[0], '--manifest-sha256', args[1], '--capture-sha256', args[2],
            '--started-at', args[3], '--ended-at', args[4], '--capture-exit', '0']
    assert reader.main(argv) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)['readback_authenticated'] is True
    assert output.err == '' and '123.45' not in output.out
    def fail(*_):
        raise RuntimeError('SECRET_VALUE')
    monkeypatch.setattr(reader, 'verify', fail)
    assert reader.main(argv) == 1
    output = capsys.readouterr()
    assert output.out == '' and output.err == 'fresh price receipt refused\n'


def test_budget_return_overrun_and_handler_restoration(monkeypatch):
    previous = signal.getsignal(signal.SIGALRM)
    sequence = iter((10.0, 25.0))
    monkeypatch.setattr(reader.time, 'monotonic', lambda: next(sequence))
    with pytest.raises(reader.Refusal):
        with reader.budget():
            pass
    assert signal.getsignal(signal.SIGALRM) is previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
