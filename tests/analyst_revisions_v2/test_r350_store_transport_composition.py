"""Synthetic real Store/_exchange composition; no operational controls or I/O.

Socket/TLS/HTTP and native-security snapshots are synthetic. This exercises
real persistence, dispatch ordering, response bounds and caller projections,
not CA/DNS, production credentials, host preflight or a complete run command.
"""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import observe_arv2_r345_qc_availability as transport
from scripts import observe_arv2_r348_ar100_runtime_error as observer
from scripts import read_arv2_r348_ar100_result as reader
from tests.analyst_revisions_v2.test_r345_qc_availability import transport_api


def synthetic_root(tmp_path):
    root = tmp_path / 'synthetic-root'
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    (root / 'artifacts').mkdir(mode=0o700)
    return root


def security():
    return NS(snapshot=lambda _fd: (), Refusal=type('SyntheticSecurityRefusal', (ValueError,), {}))


def test_real_reader_store_records_transport_then_rejects_uppercase_status(tmp_path, monkeypatch):
    root = synthetic_root(tmp_path)
    monkeypatch.setattr(reader, 'ROOT', root)
    monkeypatch.setattr(reader, 'CLAIM', 'unallocated')
    api, events = transport_api(monkeypatch)
    with reader.Store(root / 'artifacts' / 'diagnosis' / 'once', security()) as store:
        store.write('claim.json', {'synthetic': True})
        store.write('events.jsonl', b'')
        api.store = store
        assert api._exchange('authenticate', {}) == {'success': True}
        assert store.application_dispatch_count == store.intents == 1
        before = bytes(store.events)
        with pytest.raises(reader.Refused) as caught:
            store.journal('known-A4-status', {'status': 'Runtime Error'})
        assert caught.value.args == ('output',)
        assert bytes(store.events) == before
        assert sum(event[0] == 'request' for event in events) == 1
        store.verify()


@pytest.mark.parametrize('oversize', [False, True])
def test_real_error_store_and_transport_feed_the_readonly_projection(tmp_path, monkeypatch, oversize):
    root = synthetic_root(tmp_path)
    monkeypatch.setattr(observer, 'ROOT', root)
    monkeypatch.setattr(observer, 'CONTROL', root / 'artifacts' / 'diagnosis' / 'once')
    monkeypatch.setattr(observer, 'SAFE', None)
    api, events = transport_api(monkeypatch)
    packet = {'success': True, 'backtest': {
        'projectId': observer.PROJECT, 'backtestId': observer.BACKTEST,
        'compileId': observer.COMPILE, 'name': observer.BACKTEST_NAME,
        'status': 'Runtime Error', 'error': None, 'stacktrace': None,
    }}
    bodies = [transport.canonical({'success': True}), transport.canonical(packet)]

    class Response:
        status = 200

        def __init__(self, raw, second):
            self.raw, self.second = raw, second

        def getheader(self, name, default=None):
            if name == 'Content-Length':
                return str(transport.MAX_BODY + 1 if oversize and self.second else len(self.raw))
            return default

        def read(self, maximum):
            events.append(('synthetic-body-read', maximum))
            return self.raw

    response_count = 0

    def response(_connection):
        nonlocal response_count
        result = Response(bodies[response_count], response_count == 1)
        response_count += 1
        return result

    monkeypatch.setattr(transport.http.client.HTTPConnection, 'getresponse', response)
    api.parent_deadline = api.deadline
    inventory = json.loads((Path(__file__).resolve().parents[2] / observer.INVENTORY).read_bytes())
    with observer.Store(security()) as store:
        store.write('claim.json', {'synthetic': True})
        api.store = store
        if oversize:
            with pytest.raises(transport.Refused) as caught:
                observer.observe(api, inventory)
            assert caught.value.args == ('bound',)
            assert observer.finite(caught.value) == 'unknown'
            assert observer.SAFE is None
            assert sum(event[0] == 'synthetic-body-read' for event in events) == 1
        else:
            projected = observer.observe(api, inventory)
            assert projected['projection_complete'] is True
            assert projected['error']['present'] is projected['stacktrace']['present'] is False
            assert [row['endpoint'] for row in projected['response_pins']] == ['authenticate', 'backtests/read']
            store.write('report.json', {'synthetic_projection': projected})
        assert response_count == 2
        assert store.application_dispatch_count == store.intents == 2
        store.verify()
