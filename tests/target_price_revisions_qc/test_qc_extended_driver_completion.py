"""Completion prepare/dispatch refusal proofs; public bytes and fake calls only."""
from pathlib import Path
import pytest
from research.target_price_revisions_qc import extended_driver_completion as driver


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_args, **_kw): raise AssertionError('actual private/source/credential/cloud operation forbidden')
    monkeypatch.setattr(driver.base, 'credential', deny)
    monkeypatch.setattr(driver.base.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(driver.base, 'read_private', deny)
    monkeypatch.setattr(driver, 'committed', deny)
    monkeypatch.setattr(driver, 'preflight', lambda: {'head': 'a' * 40, 'status': ''})
    monkeypatch.setattr(driver.operations.predecessor.previous, 'verify_initializers', lambda _head: None)


def test_spent_original_scopes_refuse_before_any_file_or_network_read():
    for operation in driver.SPENT_OPERATIONS:
        with pytest.raises(ValueError): driver.prepare(operation, 'no-read')


@pytest.mark.parametrize('mutant', [None, 'economics', 'runtime', 'counter'])
def test_prepare_admits_only_public_exact_completion_render(monkeypatch, mutant):
    prefix = Path('research/target_price_revisions_qc')
    original = (prefix / 'extended_source_bundle_compressed.json').read_bytes()
    helper = (prefix / 'extended_completion_successor.py').read_bytes()
    bundle = driver.completion.render_completion_bundle(original,
        helper_raw=helper, expected_helper_sha256=driver.e.digest(helper))
    successor_path = driver.completion.PREFIX + 'extended_source_bundle_completion.json'
    if mutant == 'economics': bundle['candidates'][1]['files']['main.py'] += '\nchanged_economics = True\n'
    if mutant == 'runtime': bundle['candidates'][1]['files']['extended_runtime_successor.py'] += '\nchanged = True\n'
    if mutant == 'counter': bundle['candidates'][1]['planned_attempt'] = 1
    raw = driver.e.canonical(bundle)
    values = {name: Path(name).read_bytes() for name in bundle['repository_sources']}
    values[successor_path] = raw
    monkeypatch.setattr(driver, 'committed', lambda name, _head: values[name])
    admitted = []
    class Fake:
        def __init__(self, manifest, *, manifest_sha256):
            admitted.append((manifest, manifest_sha256))
        def prepare(self): return {'synthetic': True}
    monkeypatch.setattr(driver.operations, 'Operations', Fake)
    if mutant is not None:
        with pytest.raises(ValueError): driver.prepare('TPR-EXT26-QC-COMPLETION-SYNTHETIC-006', successor_path)
        assert not admitted
    else:
        assert driver.prepare('TPR-EXT26-QC-COMPLETION-SYNTHETIC-006', successor_path) == {'synthetic': True}
        manifest, identity = admitted[0]
        assert len(manifest['repository_source_hashes']) == 31
        assert driver.e.canonical(manifest['inputs']) == driver.e.canonical(bundle['inputs'])
        assert driver.e.digest(driver.e.canonical(manifest)) == identity
        assert manifest['candidates'][1]['planned_attempt'] == driver.e.JsonNumber('3')


def test_exact_off3_dispatch_and_no_create_cleanup_recovery_commands(monkeypatch, capsys):
    seen = []
    class Fake:
        def __getattr__(self, _name): return lambda *_args: None
        def launch(self, candidate, attempt):
            seen.append((candidate, attempt)); return {'attempt': attempt}
    monkeypatch.setattr(driver, 'controller_for', lambda _operation: Fake())
    assert driver.main(['launch', '--operation', 'synthetic006', '--candidate', driver.operations.OFF, '--attempt', '3']) == 0
    assert seen == [(driver.operations.OFF, 3)]
    for action in ('create', 'cleanup', 'recover'):
        with pytest.raises(SystemExit): driver.main([action, '--operation', 'synthetic006'])
    assert '3' in capsys.readouterr().out


def test_private_uncertain_exception_never_leaks_or_retries(monkeypatch, capsys):
    def bad(_operation): raise ValueError('LICENSED PRIVATE SECRET ORGANIZATION-ID')
    monkeypatch.setattr(driver, 'controller_for', bad)
    assert driver.main(['authenticate', '--operation', 'synthetic006']) == 1
    output = capsys.readouterr().out
    assert 'LICENSED' not in output and 'SECRET' not in output and 'ORGANIZATION-ID' not in output
