"""Synthetic metadata-only invoker tests; actual roots/credentials/HTTPS denied."""
from datetime import datetime, timezone
import http.client
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_metadata_driver as d, extended_evidence as e, extended_operations as o

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 10, 3, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def deny_actual_access(monkeypatch):
    def denied(*a, **kw): raise AssertionError('actual private/credential/HTTPS/Git access denied')
    original = d._open_inputs
    def fixture_only(path, mode):
        if mode != 'offline-fixture' or path == d.PRIVATE_ROOT or path.is_relative_to(d.LANE): denied()
        return original(path, mode)
    monkeypatch.setattr(d, '_open_inputs', fixture_only)
    monkeypatch.setattr(d, '_guard', denied)
    monkeypatch.setattr(o, 'credential', denied)
    monkeypatch.setattr(o, 'read_private', denied)
    monkeypatch.setattr(http.client, 'HTTPSConnection', denied)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    # Reuse the pure synthetic receipt fixture, not any prepared private file.
    spec = importlib.util.spec_from_file_location('synthetic_bundle_fixture', ROOT / 'tests/target_price_revisions_qc/test_qc_extended_bundle.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    arguments = module.arguments.__wrapped__()
    prep, manifest = arguments['preparation_raw'], arguments['signal_manifest_raw']
    prep_sha, manifest_sha = e.digest(prep), e.digest(manifest)
    monkeypatch.setattr(d, 'PREPARATION_SHA256', prep_sha)
    monkeypatch.setattr(d, 'MANIFEST_SHA256', manifest_sha)
    monkeypatch.setattr(d, 'METADATA_FILES', {'preparation.json': (prep_sha, 262144), manifest_sha + '.json': (manifest_sha, 128 * 1024)})
    private = tmp_path / 'inputs'; private.mkdir(mode=0o700)
    for name, raw in (('preparation.json', prep), (manifest_sha + '.json', manifest)):
        path = private / name; path.write_bytes(raw); path.chmod(0o600)
    sources = {name: (ROOT / name).read_bytes() for name in d.SOURCE_PATHS}
    plan = d._plan(sources, head='a' * 40, owner_instruction_sha256='b' * 64,
        created_utc='2026-10-10T02:00:00+00:00', expires_utc='2026-10-10T04:00:00+00:00', mode='offline-fixture')
    return SimpleNamespace(private=private, sources=sources, plan=plan, prep=prep, manifest=manifest)


def execute(fixture, *, clock=lambda: NOW, guard=lambda head: e._hash(head, 40)):
    return d._execute(fixture.plan, fixture.sources, fixture.private, clock=clock, guard=guard)


def test_claim_before_only_two_pinned_metadata_reads_and_public_bundle_write(fixture, monkeypatch):
    original = d._read_file; reads = []
    def read(directory, name, maximum, **kwargs):
        assert (fixture.private / (d.OPERATION_ID + '.metadata-claim.json')).is_file()
        reads.append(name)
        return original(directory, name, maximum, **kwargs)
    monkeypatch.setattr(d, '_read_file', read)
    result = execute(fixture); receipt = e.parse_json(result.receipt)
    assert receipt['status'] == 'COMPLETED' and receipt['scope_spent'] is True
    assert reads == ['preparation.json', d.MANIFEST_SHA256 + '.json']
    assert receipt['metadata_reads'] == e.JsonNumber('2') and receipt['private_payload_reads'] == e.JsonNumber('0')
    assert receipt['source_bundle_sha256'] == e.digest(result.source_bundle)
    assert result.source_bundle == (fixture.private / d.RENDERED_NAME).read_bytes()
    assert result.source_bundle.endswith(b'\n') and not result.source_bundle.endswith(b'\n\n')
    assert e.canonical(e.parse_json(result.source_bundle)) == result.source_bundle
    assert receipt['source_bundle_path'] == str(fixture.private / d.RENDERED_NAME)
    assert len(list(fixture.private.iterdir())) == 5  # two input metadata + claim + bundle + receipt
    for key in ('point_in_time_data', 'rights_verified', 'canonical_admission', 'trading', 'automatic_retry', 'old_receipts_renewed'): assert receipt[key] is False
    for key in ('outcome_reads', 'development_looks', 'quantconnect_attempts'): assert receipt[key] == e.JsonNumber('0')


def test_spent_metadata_claim_never_replays_or_refunds(fixture, monkeypatch):
    assert e.parse_json(execute(fixture).receipt)['status'] == 'COMPLETED'
    monkeypatch.setattr(d, '_read_file', lambda *a, **kw: pytest.fail('spent scope read metadata again'))
    with pytest.raises(FileExistsError): execute(fixture)


@pytest.mark.parametrize('change', ['wrong_hash', 'symlink', 'hardlink', 'mode', 'missing', 'oversized'])
def test_wrong_metadata_custody_or_bytes_fail_after_irreversible_claim(fixture, change):
    path = fixture.private / 'preparation.json'
    if change == 'wrong_hash': path.write_bytes(path.read_bytes() + b' ')
    elif change == 'symlink':
        sibling = fixture.private.parent / 'other'; path.rename(sibling); path.symlink_to(sibling)
    elif change == 'hardlink': (fixture.private / 'duplicate').hardlink_to(path)
    elif change == 'mode': path.chmod(0o644)
    elif change == 'missing': path.unlink()
    else: path.write_bytes(b' ' * 262145)
    result = execute(fixture); receipt = e.parse_json(result.receipt)
    assert receipt['status'] == 'FAILED' and receipt['scope_spent'] is True and result.source_bundle is None
    assert receipt['source_bundle_sha256'] is None and not (fixture.private / d.RENDERED_NAME).exists()
    assert (fixture.private / (d.OPERATION_ID + '.metadata-claim.json')).exists()


@pytest.mark.parametrize('clock', [lambda: datetime(2026,10,10,3), lambda: datetime(2026,10,10,5,tzinfo=timezone.utc)])
def test_unaware_or_expired_fresh_clock_refuses_before_claim(fixture, clock):
    with pytest.raises(d.Refusal): execute(fixture, clock=clock)
    assert len(list(fixture.private.iterdir())) == 2


def test_git_advance_refuses_before_private_claim(fixture):
    def changed(head): raise d.Refusal('synthetic Git custody changed')
    with pytest.raises(d.Refusal): execute(fixture, guard=changed)
    assert len(list(fixture.private.iterdir())) == 2


def test_source_mutation_after_plan_refuses_before_claim(fixture):
    fixture.sources[d.SOURCE_RELATIVE] += b'\n# unregistered\n'
    with pytest.raises(d.Refusal): execute(fixture)
    assert len(list(fixture.private.iterdir())) == 2


def test_metadata_file_hash_is_independently_checked_before_parsing_or_rendering(fixture):
    directory = d._open_inputs(fixture.private, 'offline-fixture')
    try:
        with pytest.raises(d.Refusal): d._read_file(directory, 'preparation.json', 262144, private=True, expected_sha='0'*64)
    finally:
        import os
        os.close(directory)


def test_bound_sources_compare_exact_committed_bytes_before_private_access(monkeypatch):
    monkeypatch.setattr(d, '_guard', lambda *a: 'a'*40)
    monkeypatch.setattr(d, '_read_public', lambda relative: b'current-public-source')
    monkeypatch.setattr(d.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=b'different-committed-source'))
    with pytest.raises(d.Refusal): d._bound_sources('a'*40)


def test_imported_renderer_binding_cannot_be_replaced_in_production(monkeypatch):
    d._verify_imports()
    monkeypatch.setattr(d.bundle, 'render_bundle', lambda *a, **kw: {})
    with pytest.raises(d.Refusal): d._verify_imports()


def test_source_closure_omission_cannot_be_named_as_complete(fixture):
    fixture.sources.pop(d.SOURCE_RELATIVE)
    with pytest.raises(d.Refusal): d._source_identity(fixture.sources)


def test_expiration_between_metadata_reads_retains_first_read_and_failed_claim(fixture):
    calls = 0
    def clock():
        nonlocal calls
        calls += 1
        return NOW if calls <= 3 else datetime(2026,10,10,5,tzinfo=timezone.utc)
    result = execute(fixture, clock=clock); receipt = e.parse_json(result.receipt)
    assert receipt['status'] == 'FAILED' and receipt['metadata_reads'] == e.JsonNumber('1')
    assert result.source_bundle is None


def test_saved_metadata_bundle_does_not_overwrite_any_prior_file(fixture):
    prior = fixture.private / d.RENDERED_NAME; prior.write_bytes(b'preserve prior'); prior.chmod(0o600)
    result = execute(fixture)
    assert e.parse_json(result.receipt)['status'] == 'FAILED' and prior.read_bytes() == b'preserve prior'
    assert result.source_bundle is None


@pytest.mark.parametrize('field,value', [('owner_instruction_sha256', True), ('created_utc','2026-10-10T02:00:00'),
    ('expires_utc','2026-10-13T04:00:00+00:00'), ('head', 'not-git')])
def test_fresh_explicit_plan_identity_clock_and_bound_refuse(fixture, field, value):
    fields = {'head':'a'*40,'owner_instruction_sha256':'b'*64,'created_utc':'2026-10-10T02:00:00+00:00','expires_utc':'2026-10-10T04:00:00+00:00','mode':'offline-fixture'}
    fields[field] = value
    with pytest.raises((d.Refusal, e.EvidenceError)): d._plan(fixture.sources, **fields)


def test_production_dispatch_has_no_fixture_hooks_and_requires_committed_sources(monkeypatch):
    calls=[]
    monkeypatch.setattr(d, '_verify_imports', lambda: calls.append('imports'))
    monkeypatch.setattr(d, '_guard', lambda *a: calls.append('Git') or 'a'*40)
    def uncommitted(head):
        calls.append('committed-source-refusal'); raise d.Refusal('synthetic uncommitted producer')
    monkeypatch.setattr(d, '_bound_sources', uncommitted)
    with pytest.raises(d.Refusal): d.run_metadata(owner_instruction_sha256='b'*64, created_utc='2026-10-10T02:00:00+00:00', expires_utc='2026-10-10T04:00:00+00:00')
    assert calls == ['imports','Git','committed-source-refusal']


@pytest.mark.parametrize('emit', [False, True])
def test_cli_emits_only_compact_receipt_unless_public_bundle_explicitly_requested(fixture, monkeypatch, capsys, emit):
    result = execute(fixture)
    monkeypatch.setattr(d, 'run_metadata', lambda **kw: result)
    args=['--owner-instruction-sha256','b'*64,'--created-utc','2026-10-10T02:00:00+00:00','--expires-utc','2026-10-10T04:00:00+00:00']
    if emit: args.append('--emit-bundle')
    assert d.main(args) == 0
    output = e.parse_json(capsys.readouterr().out.encode())
    assert set(output) == ({'receipt','source_bundle_raw'} if emit else {'receipt'})
    if emit: assert output['source_bundle_raw'].encode() == result.source_bundle


def test_cli_never_echoes_malformed_private_or_exception_text(monkeypatch, capsys):
    def private_error(**kw): raise ValueError('LICENSED ROW OR SECRET NEVER PRINTED')
    monkeypatch.setattr(d, 'run_metadata', private_error)
    assert d.main(['--owner-instruction-sha256','b'*64,'--created-utc','bad','--expires-utc','bad']) == 1
    output=capsys.readouterr().out
    assert 'LICENSED' not in output and 'SECRET' not in output and 'Traceback' not in output
    assert e.parse_json(output.encode())['receipt']['status'] == 'REFUSED_OR_UNCERTAIN'
