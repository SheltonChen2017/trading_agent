"""Synthetic local-export boundaries; no actual registry or native service."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261103_prepare as p


@pytest.fixture(autouse=True)
def _synthetic_root(tmp_path, monkeypatch):
    monkeypatch.setattr(p, 'ROOT', tmp_path)
    monkeypatch.setattr(p, '_root_fd', lambda: os.open(tmp_path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))


def test_main_propagates_keyboard_interrupt_instead_of_printing_a_refusal(monkeypatch, capsys):
    """TPR-CR34-006: an operator interrupt is not a refusal and must not become exit 1."""
    def interrupted(operation_id):
        raise KeyboardInterrupt()
    monkeypatch.setattr(p, "prepare_workspace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        p.main(["TPR-OFFLINE-20261103-SYNTHETIC-001"])
    assert capsys.readouterr().out == ""
    monkeypatch.setattr(p, "prepare_workspace", lambda operation_id: (_ for _ in ()).throw(RuntimeError("PRIVATE-PATH")))
    assert p.main(["TPR-OFFLINE-20261103-SYNTHETIC-002"]) == 1
    out = capsys.readouterr().out
    assert "PRIVATE-PATH" not in out and '"status": "refused"' in out


def test_retain_is_exclusive_and_hashes_exact_bytes(tmp_path):
    target = tmp_path / 'receipt.json'
    descriptor = p._retain(target, b'{}\n')
    assert descriptor == {'name': 'receipt.json', 'bytes': 3,
        'sha256': hashlib.sha256(b'{}\n').hexdigest()}
    with pytest.raises(FileExistsError):
        p._retain(target, b'changed')
    assert target.read_bytes() == b'{}\n'


@pytest.mark.parametrize('name', ('../escape.py', '/absolute.py', 'a/b.py', 'a\\b.py', 'main.py/other'))
def test_export_rejects_nonflat_names(tmp_path, name):
    packets = {arm: {name: b'pass\n'} for arm in p.preflight.ARMS}
    with pytest.raises(p.PreparationRefusal):
        p._export_packets(tmp_path / 'bundle', packets, b'{}\n')
    assert not (tmp_path / 'escape.py').exists()


def test_export_exact_five_arms_and_immutable_tree(tmp_path):
    packets = {arm: {'main.py': b'pass\n'} for arm in p.preflight.ARMS}
    target = tmp_path / 'bundle'
    result = p._export_packets(target, packets, b'{}\n')
    assert set(result) == set(p.preflight.ARMS)
    assert all((target / arm / 'main.py').read_bytes() == b'pass\n' for arm in result)
    with pytest.raises(FileExistsError):
        p._export_packets(target, packets, b'{}\n')


def test_reader_rejects_leaf_and_ancestor_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(p, 'ROOT', tmp_path)
    real = tmp_path / 'real'
    real.mkdir()
    (real / 'data').write_bytes(b'abc')
    (tmp_path / 'leaf').symlink_to(real / 'data')
    (tmp_path / 'alias').symlink_to(real, target_is_directory=True)
    for path in (tmp_path / 'leaf', tmp_path / 'alias' / 'data'):
        with pytest.raises((p.PreparationRefusal, OSError)):
            p._regular_bytes(path, 10)
    with pytest.raises(p.PreparationRefusal):
        p._regular_bytes(real / 'data', 2)


def test_reader_never_follows_parent_swapped_during_leaf_check(tmp_path, monkeypatch):
    parent = tmp_path / 'parent'
    outside = tmp_path / 'outside'
    parent.mkdir(); outside.mkdir()
    target = parent / 'data'
    target.write_bytes(b'INSIDE')
    (outside / 'data').write_bytes(b'OUTSIDE')
    original = Path.lstat
    swapped = False
    def lstat(path, *args, **kwargs):
        nonlocal swapped
        if path == target and not swapped:
            swapped = True
            parent.rename(tmp_path / 'saved')
            parent.symlink_to(outside, target_is_directory=True)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', lstat)
    assert p._regular_bytes(target, 20) == b'INSIDE'


def test_retain_never_writes_outside_when_absolute_path_is_swapped(tmp_path, monkeypatch):
    parent = tmp_path / 'parent'
    outside = tmp_path / 'outside'
    parent.mkdir(); outside.mkdir()
    target = parent / 'receipt'
    original = os.open
    def opener(path, *args, **kwargs):
        if path == target:
            parent.rename(tmp_path / 'saved')
            parent.symlink_to(outside, target_is_directory=True)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', opener)
    p._retain(target, b'private fixture')
    assert not (outside / 'receipt').exists()
    assert (parent / 'receipt').read_bytes() == b'private fixture'


def test_reader_holds_approved_parent_during_actual_leaf_stat_race(tmp_path, monkeypatch):
    parent, outside = tmp_path / 'parent', tmp_path / 'outside'
    parent.mkdir(); outside.mkdir()
    (parent / 'data').write_bytes(b'INSIDE')
    (outside / 'data').write_bytes(b'OUTSIDE')
    original, swapped = os.stat, False
    def leaf_stat(path, *args, **kwargs):
        nonlocal swapped
        if path == 'data' and kwargs.get('dir_fd') is not None and not swapped:
            swapped = True
            parent.rename(tmp_path / 'saved')
            parent.symlink_to(outside, target_is_directory=True)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'stat', leaf_stat)
    assert p._regular_bytes(parent / 'data', 20) == b'INSIDE'
    assert swapped


def test_retain_holds_approved_parent_during_actual_leaf_open_race(tmp_path, monkeypatch):
    parent, outside = tmp_path / 'parent', tmp_path / 'outside'
    parent.mkdir(); outside.mkdir()
    original, swapped = os.open, False
    def leaf_open(path, *args, **kwargs):
        nonlocal swapped
        if path == 'receipt' and kwargs.get('dir_fd') is not None and not swapped:
            swapped = True
            parent.rename(tmp_path / 'saved')
            parent.symlink_to(outside, target_is_directory=True)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', leaf_open)
    p._retain(parent / 'receipt', b'private fixture')
    assert swapped and not (outside / 'receipt').exists()
    assert (tmp_path / 'saved' / 'receipt').read_bytes() == b'private fixture'


@pytest.mark.parametrize('operation', ('', '../escape', 'TPR-OFFLINE-20261103-a', 'other'))
def test_bad_operation_refuses_before_context_or_private_io(operation, monkeypatch):
    monkeypatch.setattr(p, '_context', lambda: pytest.fail('context must not be reached'))
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(operation)


def _fixture_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(p, 'ROOT', tmp_path)
    head = '1' * 40
    monkeypatch.setattr(p, '_context', lambda: head)
    names = set(p.preflight.RECOVERY_REQUIRED_SOURCES) | {p.MODULE, p.preflight.MODULE}
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'public source fixture\n')
    record = tmp_path / p.RECORD
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text('synthetic retained history\n')
    def git(*args):
        assert args[0] == 'show'
        return (tmp_path / args[1].split(':', 1)[1]).read_bytes()
    monkeypatch.setattr(p, '_git', git)
    registry = tmp_path / p.REGISTRY
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.parent.chmod(0o700)
    registry.write_bytes(b'R' * p.preflight.REGISTRY_BYTES)
    monkeypatch.setattr(p.preflight, 'REGISTRY_SHA256', hashlib.sha256(registry.read_bytes()).hexdigest())
    return head, registry


def test_claim_is_fsynced_and_recorded_before_only_registry_read(tmp_path, monkeypatch):
    head, registry = _fixture_workspace(tmp_path, monkeypatch)
    original = p._regular_bytes
    reads = []
    op = 'TPR-OFFLINE-20261103-FIXTURE-001'
    operation = tmp_path / p.DESTINATION / op
    def reader(path, maximum):
        if path == registry:
            claim = json.loads((operation / 'claim.json').read_bytes())
            assert claim['git_head'] == head
            assert claim['qc_requests_authorized'] == 0
            assert claim['safari_requests_authorized'] == 0
            assert claim['owner_authority'] == 'LOCAL_PRE_BACKTEST_ONLY_NO_QC_OR_SAFARI'
            assert claim['reserved_attempt'] is None
            assert claim['signal_packet_open_authorized'] is False
            assert op in (tmp_path / p.RECORD).read_text()
            reads.append(path)
        return original(path, maximum)
    monkeypatch.setattr(p, '_regular_bytes', reader)
    packets = {arm: {'main.py': b'pass\n'} for arm in p.preflight.ARMS}
    def builder(**kwargs):
        assert all(v['attempt'] == 1 for v in kwargs['requests'].values())
        return packets, b'{"fixture_only":true}\n'
    monkeypatch.setattr(p.preflight, 'prepare_offline', builder)
    monkeypatch.setattr(p.preflight, 'prepare_recovery_candidate', builder)
    result = p.prepare_workspace(op)
    assert reads == [registry]
    assert result['qc_contacts'] == result['backtests'] == 0
    assert result['safari_contacts'] == 0
    assert result['backtesting_ready'] is False
    receipt = json.loads((operation / 'receipt.json').read_bytes())
    assert receipt['proposal_attempts_are_reserved'] is False
    assert receipt['fresh_native_attempt_assignment_required'] is True
    assert receipt['source_inputs_admitted'] is receipt['financial_acceptance'] is False
    assert receipt['all_safari_contacts'] == 0


def test_head_drift_after_claim_refuses_before_registry_read_and_keeps_receipt(tmp_path, monkeypatch):
    _fixture_workspace(tmp_path, monkeypatch)
    sequence = iter(('1' * 40, '2' * 40))
    monkeypatch.setattr(p, '_context', lambda: next(sequence))
    original = p._regular_bytes
    def reader(path, maximum):
        if path == tmp_path / p.REGISTRY:
            pytest.fail('private read after HEAD drift')
        return original(path, maximum)
    monkeypatch.setattr(p, '_regular_bytes', reader)
    op = 'TPR-OFFLINE-20261103-FIXTURE-002'
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(op)
    receipt = json.loads((tmp_path / p.DESTINATION / op / 'receipt.json').read_bytes())
    assert receipt['status'] == 'refused'
    assert receipt['all_qc_contacts'] == receipt['native_compiles'] == receipt['backtests'] == 0


def test_cli_exception_does_not_echo_exception_or_credentials(capsys, monkeypatch):
    def fail(_):
        raise RuntimeError('SENSITIVE_SENTINEL')
    monkeypatch.setattr(p, 'prepare_workspace', fail)
    assert p.main(['TPR-OFFLINE-20261103-FIXTURE-003']) == 1
    output = capsys.readouterr()
    assert 'SENSITIVE_SENTINEL' not in output.out + output.err
    assert json.loads(output.out)['automatic_retry'] is False


def test_cli_argument_refusal_does_not_echo_extra_values(capsys):
    assert p.main(['TPR-OFFLINE-20261103-FIXTURE-004', 'SENSITIVE_SENTINEL']) == 1
    output = capsys.readouterr()
    assert 'SENSITIVE_SENTINEL' not in output.out + output.err
    assert json.loads(output.out)['status'] == 'refused'
