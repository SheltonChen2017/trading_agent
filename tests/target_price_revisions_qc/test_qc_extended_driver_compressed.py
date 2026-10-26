"""Explicit compressed driver dispatch fixtures only."""
from types import SimpleNamespace
import pytest
from research.target_price_revisions_qc import extended_driver_compressed as d


@pytest.fixture(autouse=True)
def denied(monkeypatch):
    def deny(*_a, **_kw): raise AssertionError('actual private/API/source/credential operation forbidden')
    monkeypatch.setattr(d.base, 'credential', deny)
    monkeypatch.setattr(d.base.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(d.base, 'read_private', deny)
    monkeypatch.setattr(d, 'committed', deny)
    monkeypatch.setattr(d, 'preflight', lambda: {'head': 'a' * 40, 'status': ''})


def test_prepare_refuses_consumed_operation_before_any_read():
    for operation in ('TPR-EXT26-QC-20261010-001', 'TPR-EXT26-QC-20261010-002'):
        with pytest.raises(ValueError): d.prepare(operation, 'any')


def test_off2_dispatch_keeps_exact_candidate_attempt_and_no_create(monkeypatch, capsys):
    seen = []
    class Fake:
        def __getattr__(self, _name): return lambda *_a: None
        def launch(self, candidate, attempt): seen.append((candidate, attempt)); return {'attempt': attempt}
    fake = Fake()
    monkeypatch.setattr(d, 'controller_for', lambda operation: fake)
    assert d.main(['launch', '--operation', 'synthetic003', '--candidate', d.operations.OFF, '--attempt', '2']) == 0
    assert seen == [(d.operations.OFF, 2)] and '2' in capsys.readouterr().out
    with pytest.raises(SystemExit): d.main(['create', '--operation', 'synthetic003', '--candidate', d.operations.ON])


def test_cli_sanitizes_uncertain_failure(monkeypatch, capsys):
    def bad(_operation): raise ValueError('PRIVATE-LICENSED TOKEN-123 ORGANIZATION-ID')
    monkeypatch.setattr(d, 'controller_for', bad)
    assert d.main(['authenticate', '--operation', 'synthetic003']) == 1
    text = capsys.readouterr().out
    assert 'PRIVATE-LICENSED' not in text and 'TOKEN-123' not in text and 'ORGANIZATION-ID' not in text
