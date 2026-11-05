"""Offline public-file preflight only; no real Git subprocess or native effect."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_off_recovery_cli as m
from research.target_price_revisions_qc import extended_off_recovery_preparation as preparation

REPO = Path(__file__).resolve().parents[2]
PUBLIC_NAME = sorted(m.WITNESS_PATHS)[0]


@pytest.fixture(autouse=True)
def no_external_effect(monkeypatch):
    import socket
    def deny(*args, **kwargs):
        raise AssertionError('native/network/process/private effects forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(m.subprocess, 'run', deny)


def observation():
    return {'physical_root': preparation.ROOT, 'git_toplevel': preparation.ROOT,
        'branch': m.BRANCH, 'git_head': 'a' * 40, 'status_short': ''}


@pytest.fixture
def closure():
    return {name: (REPO / name).read_bytes() for name in m.PUBLIC_PATHS}


def test_success_reads_only_public_closure_twice_and_emits_inert_manifest(monkeypatch, closure, capsys):
    reads = []
    monkeypatch.setattr(m, 'observe_repository', observation)
    def read(name, maximum):
        assert name in m.PUBLIC_PATHS and maximum == m.PUBLIC_LIMITS[name]
        reads.append(name)
        return closure[name]
    monkeypatch.setattr(m, '_public_read', read)
    assert m.main([]) == 0
    import json
    result = json.loads(capsys.readouterr().out)
    assert reads == sorted(m.PUBLIC_PATHS) * 2
    assert result['schema'] == 'tpr-ext26-off-pre-qc-bundle-v1'
    assert result['attempt_source_template']['attempt'] == 4
    assert result['attempt_source_template']['reservation_sha256'] is None
    assert result['attempt_source_template']['first_refusal_repaired'] is False
    assert result['witness_preparation']['pending_native']['permit'] is None
    assert set(result['public_source_hashes']) == m.PUBLIC_PATHS
    assert result['pending_native']['permit'] is None
    assert result['ready_for_dispatch'] is result['authority_granted'] is False
    assert result['new_jobs'] == result['new_codex_attempts'] == result['new_looks'] == 0


def test_combined_bundle_digest_determinism_and_no_source_or_reservation_output(monkeypatch, closure):
    import hashlib
    import json
    monkeypatch.setattr(m, 'observe_repository', observation)
    monkeypatch.setattr(m, '_public_read', lambda name, maximum: closure[name])
    result = m.build_preparation()
    assert result == m.build_preparation()
    claimed = result.pop('preparation_sha256')
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    assert claimed == hashlib.sha256(canonical(result)).hexdigest()
    assert result['public_source_hashes'] == {name: hashlib.sha256(raw).hexdigest() for name, raw in closure.items()}
    assert result['public_source_closure_sha256'] == hashlib.sha256(canonical(result['public_source_hashes'])).hexdigest()
    assert all(value is None for value in result['pending_native'].values())
    assert result['attempt_source_template']['reservation_sha256'] is None
    assert 'def Initialize' not in canonical(result).decode()
    assert 'files' not in result['attempt_source_template']


@pytest.mark.parametrize('name', sorted(m.CONTINUATION_PATHS))
def test_continuation_source_drift_refused_before_template_can_be_used(monkeypatch, closure, name):
    monkeypatch.setattr(m, 'observe_repository', observation)
    altered = {**closure, name: closure[name] + b'\n'}
    monkeypatch.setattr(m, '_public_read', lambda path, maximum: altered[path])
    with pytest.raises(m.PreparationCLIRefusal):
        m.build_preparation()


def test_claim_and_native_calls_are_not_part_of_combined_preparation(monkeypatch, closure):
    from research.target_price_revisions_qc import extended_off_attempt_continuation as continuation
    monkeypatch.setattr(m, 'observe_repository', observation)
    monkeypatch.setattr(m, '_public_read', lambda path, maximum: closure[path])
    monkeypatch.setattr(continuation, 'prepare_reservation', lambda **_: pytest.fail('no reservation minted'))
    result = m.build_preparation()
    assert result['attempt_source_template']['attempt'] == 4
    assert result['pending_native']['operation_id'] is None


def test_forged_source_path_expansion_refuses_before_open(monkeypatch):
    from research.target_price_revisions_qc import extended_off_attempt_continuation as continuation
    monkeypatch.setattr(m, 'observe_repository', observation)
    monkeypatch.setattr(continuation, 'SOURCE_PINS', {**continuation.SOURCE_PINS, 'private.json': 'a'*64})
    monkeypatch.setattr(m, '_public_read', lambda *_: pytest.fail('no path may be opened'))
    with pytest.raises(m.PreparationCLIRefusal):
        m.build_preparation()


@pytest.mark.parametrize('path,maximum', [
    (m.PREFIX + 'extended_source_bundle_completion.json', 1048577),
    (m.PREFIX + 'extended_source_bundle_completion.json', 65536),
    (m.PREFIX + 'extended_operations.py', 131073),
    (m.PREFIX + 'extended_study_freeze.json', 65536),
])
def test_each_explicit_public_budget_is_exact_before_open(monkeypatch, path, maximum):
    monkeypatch.setattr(m.os, 'open', lambda *_args, **_kwargs: pytest.fail('invalid budget cannot open'))
    with pytest.raises(m.PreparationCLIRefusal):
        m._public_read(path, maximum)


def test_fixed_large_public_bundle_uses_its_own_tight_budget(tmp_path, monkeypatch):
    name = m.PREFIX + 'extended_source_bundle_completion.json'
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    raw = b'x' * 70000
    path.write_bytes(raw)
    monkeypatch.setattr(m, 'ROOT', tmp_path.resolve())
    monkeypatch.chdir(tmp_path)
    assert m._public_read(name, 1048576) == raw


@pytest.mark.parametrize('field,value', [('git_head', 'b'*40), ('status_short', ' M x'),
    ('branch', 'main'), ('git_toplevel', '/wrong'), ('physical_root', '/wrong')])
def test_scope_drift_before_any_read_refuses(monkeypatch, field, value):
    calls = []
    first = observation()
    second = {**first, field: value}
    stream = iter((first, second))
    monkeypatch.setattr(m, 'observe_repository', lambda: next(stream))
    monkeypatch.setattr(m, '_public_read', lambda *_: calls.append(True))
    with pytest.raises(m.PreparationCLIRefusal):
        m.build_preparation()
    assert not calls


def test_working_byte_change_on_second_pass_refuses_even_clean_git(monkeypatch, closure):
    monkeypatch.setattr(m, 'observe_repository', observation)
    counts = {}
    def read(name, _maximum):
        counts[name] = counts.get(name, 0) + 1
        return closure[name] if counts[name] == 1 else closure[name] + b'\n'
    monkeypatch.setattr(m, '_public_read', read)
    with pytest.raises(m.PreparationCLIRefusal):
        m.build_preparation()


@pytest.mark.parametrize('relative,maximum', [('../private', 65536), ('private.json', 65536),
    (PUBLIC_NAME, 999999999), (PUBLIC_NAME, True)])
def test_private_or_unbounded_path_refuses_before_open(monkeypatch, relative, maximum):
    monkeypatch.setattr(m.os, 'open', lambda *_args, **_kwargs: pytest.fail('must not open'))
    with pytest.raises(m.PreparationCLIRefusal):
        m._public_read(relative, maximum)


def test_real_bounded_read_and_symlink_refusal_are_temp_only(tmp_path, monkeypatch):
    name = PUBLIC_NAME
    monkeypatch.setattr(m, 'ROOT', tmp_path.resolve())
    monkeypatch.chdir(tmp_path)
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    path.write_bytes(b'public fixture')
    assert m._public_read(name, 65536) == b'public fixture'
    path.unlink()
    target = tmp_path / 'other'
    target.write_bytes(b'not allowed via alias')
    path.symlink_to(target)
    with pytest.raises(m.PreparationCLIRefusal):
        m._public_read(name, 65536)


def test_existing_ancestor_symlink_refused_before_any_leaf_read(tmp_path, monkeypatch):
    name = PUBLIC_NAME
    root = tmp_path / 'root'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    (root / 'research').symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(m, 'ROOT', root.resolve())
    monkeypatch.chdir(root)
    monkeypatch.setattr(m.os, 'read', lambda *_: pytest.fail('ancestor must refuse before read'))
    with pytest.raises(m.PreparationCLIRefusal):
        m._public_read(name, 65536)


def test_ancestor_replaced_after_open_refused_before_leaf_access(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    name = PUBLIC_NAME
    path = root / name
    path.parent.mkdir(parents=True)
    path.write_bytes(b'public fixture')
    original_open = m.os.open
    opened = []
    def opened_then_replaced(part, flags, *args, **kwargs):
        fd = original_open(part, flags, *args, **kwargs)
        opened.append(fd)
        if part == 'research':
            (root / 'research').rename(root / 'research-before-swap')
            (root / 'research').symlink_to(outside, target_is_directory=True)
        return fd
    monkeypatch.setattr(m, 'ROOT', root.resolve())
    monkeypatch.chdir(root)
    monkeypatch.setattr(m.os, 'open', opened_then_replaced)
    monkeypatch.setattr(m.os, 'read', lambda *_: pytest.fail('must refuse before read'))
    with pytest.raises(m.PreparationCLIRefusal):
        m._public_read(name, 65536)
    for fd in opened:
        with pytest.raises(OSError):
            m.os.fstat(fd)


def test_swap_during_leaf_open_cannot_redirect_fd_relative_read(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    name = PUBLIC_NAME
    path = root / name
    path.parent.mkdir(parents=True)
    path.write_bytes(b'public fixture')
    private = outside / 'target_price_revisions_qc' / path.name
    private.parent.mkdir()
    private.write_bytes(b'synthetic private sentinel')
    original_open, original_read = m.os.open, m.os.read
    actual_reads = []
    def leaf_swap(part, flags, *args, **kwargs):
        if part == path.name:
            assert kwargs.get('dir_fd') is not None
            (root / 'research').rename(root / 'research-before-swap')
            (root / 'research').symlink_to(outside, target_is_directory=True)
            try:
                fd = original_open(part, flags, *args, **kwargs)
            finally:
                (root / 'research').unlink()
                (root / 'research-before-swap').rename(root / 'research')
            return fd
        return original_open(part, flags, *args, **kwargs)
    def read(fd, maximum):
        raw = original_read(fd, maximum)
        actual_reads.append(raw)
        return raw
    monkeypatch.setattr(m, 'ROOT', root.resolve())
    monkeypatch.chdir(root)
    monkeypatch.setattr(m.os, 'open', leaf_swap)
    monkeypatch.setattr(m.os, 'read', read)
    assert m._public_read(name, 65536) == b'public fixture'
    assert actual_reads == [b'public fixture']


def test_renamed_pinned_root_is_refused_before_read(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir()
    name = PUBLIC_NAME
    path = root / name
    path.parent.mkdir(parents=True)
    path.write_bytes(b'public fixture')
    original_open = m.os.open
    def root_swap(part, flags, *args, **kwargs):
        fd = original_open(part, flags, *args, **kwargs)
        if part == '.':
            root.rename(tmp_path / 'old-root')
            root.mkdir()
        return fd
    monkeypatch.setattr(m, 'ROOT', root.resolve())
    monkeypatch.chdir(root)
    monkeypatch.setattr(m.os, 'open', root_swap)
    monkeypatch.setattr(m.os, 'read', lambda *_: pytest.fail('root replacement must refuse'))
    with pytest.raises(m.PreparationCLIRefusal):
        m._public_read(name, 65536)


@pytest.mark.parametrize('swap', ['ancestor', 'leaf'])
def test_post_read_identity_drift_refuses_even_after_public_bytes_were_read(tmp_path, monkeypatch, swap):
    root = tmp_path / 'root'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    name = PUBLIC_NAME
    path = root / name
    path.parent.mkdir(parents=True)
    path.write_bytes(b'public fixture')
    original_read = m.os.read
    observed = []
    def read_then_swap(fd, maximum):
        raw = original_read(fd, maximum)
        observed.append(raw)
        if swap == 'ancestor':
            (root / 'research').rename(root / 'retained-research')
            (root / 'research').symlink_to(outside, target_is_directory=True)
        else:
            path.rename(path.with_suffix('.before-swap'))
            path.write_bytes(b'replacement fixture')
        return raw
    monkeypatch.setattr(m, 'ROOT', root.resolve())
    monkeypatch.chdir(root)
    monkeypatch.setattr(m.os, 'read', read_then_swap)
    with pytest.raises(m.PreparationCLIRefusal):
        m._public_read(name, 65536)
    assert observed == [b'public fixture']


@pytest.mark.parametrize('fault', ['hardlink', 'empty', 'oversize', 'directory'])
def test_nonregular_aliased_or_unbounded_public_name_refuses_without_read(tmp_path, monkeypatch, fault):
    name = PUBLIC_NAME
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    if fault == 'directory': path.mkdir()
    else:
        path.write_bytes(b'' if fault == 'empty' else b'x' * 65537 if fault == 'oversize' else b'public')
        if fault == 'hardlink': m.os.link(path, tmp_path / 'alias')
    monkeypatch.setattr(m, 'ROOT', tmp_path.resolve())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(m.os, 'read', lambda *_: pytest.fail('must refuse before read'))
    with pytest.raises(m.PreparationCLIRefusal):
        m._public_read(name, 65536)


@pytest.mark.parametrize('fatal', [KeyboardInterrupt, SystemExit])
def test_read_stop_not_demoted_by_ordinary_close_failure(tmp_path, monkeypatch, fatal):
    name = PUBLIC_NAME
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    path.write_bytes(b'public')
    original_close = m.os.close
    closed = []
    def interrupted(*_):
        raise fatal('synthetic private stop payload')
    def close(fd):
        original_close(fd)
        closed.append(fd)
        raise OSError('synthetic private cleanup payload')
    monkeypatch.setattr(m, 'ROOT', tmp_path.resolve())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(m.os, 'read', interrupted)
    monkeypatch.setattr(m.os, 'close', close)
    with pytest.raises(KeyboardInterrupt if fatal is KeyboardInterrupt else m.PreparationCLIStopped) as caught:
        m._public_read(name, 65536)
    assert 'private' not in str(caught.value) and len(closed) == 4


def test_owner_provenance_records_latest_offline_boundary_only():
    assert b'continue building to the last step before qc. skip claude review for now' in m.OWNER_INSTRUCTION
    assert b'stop the monitor' in m.OWNER_INSTRUCTION


def test_directory_chain_guard_mutant_is_detected_without_disk_source_edits(tmp_path, monkeypatch):
    import ast
    from types import ModuleType
    source = Path(m.__file__).read_text()
    tree = ast.parse(source)
    checks = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'check_chain']
    assert len(checks) == 1
    checks[0].body = [ast.Pass()]
    mutant = ModuleType('_off_cli_chain_mutant')
    exec(compile(ast.fix_missing_locations(tree), '<offline-cli-chain-mutant>', 'exec'), mutant.__dict__)
    name = PUBLIC_NAME

    def exercise(module, location, should_refuse):
        location.mkdir()
        root = location / 'root'; root.mkdir()
        outside = location / 'outside'; outside.mkdir()
        path = root / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b'public fixture')
        original_open = m.os.open
        def swapped(part, flags, *args, **kwargs):
            fd = original_open(part, flags, *args, **kwargs)
            if part == 'research':
                (root / 'research').rename(root / 'retained-research')
                (root / 'research').symlink_to(outside, target_is_directory=True)
            return fd
        with monkeypatch.context() as patch:
            patch.setattr(module, 'ROOT', root.resolve())
            patch.chdir(root)
            patch.setattr(m.os, 'open', swapped)
            if should_refuse:
                with pytest.raises(module.PreparationCLIRefusal):
                    module._public_read(name, 65536)
            else:
                # Pinned descriptors still avoid redirecting the read, but the
                # mutant wrongly accepts a detached directory as current scope.
                assert module._public_read(name, 65536) == b'public fixture'

    exercise(m, tmp_path / 'clean-before', True)
    exercise(mutant, tmp_path / 'mutant', False)
    exercise(m, tmp_path / 'clean-after', True)


@pytest.mark.parametrize('field,value', [('top', '/wrong'), ('branch', 'main'), ('status', '?? unknown')])
def test_actual_repository_observer_refuses_scope_and_dirty_status(monkeypatch, field, value):
    monkeypatch.setattr(m.os.path, 'realpath', lambda _: str(m.ROOT))
    values = {'top': str(m.ROOT), 'branch': m.BRANCH, 'head': 'a'*40, 'status': ''}
    values[field] = value
    stream = iter(values.values())
    monkeypatch.setattr(m, '_git', lambda *_: next(stream))
    with pytest.raises(m.PreparationCLIRefusal):
        m.observe_repository()


def test_git_observation_is_fixed_local_only_and_bounded(monkeypatch):
    seen = []
    def run(args, **kwargs):
        seen.append(args)
        assert kwargs['cwd'] == m.ROOT and kwargs['stdin'] == m.subprocess.DEVNULL
        assert kwargs['timeout'] == 10 and kwargs['capture_output'] is True
        return SimpleNamespace(returncode=0, stdout=b'a'*40 + b'\n')
    monkeypatch.setattr(m.subprocess, 'run', run)
    assert m._git('rev-parse', 'HEAD') == 'a'*40
    assert seen == [['git', 'rev-parse', 'HEAD']]


@pytest.mark.parametrize('result', [SimpleNamespace(returncode=1, stdout=b'private error'),
    SimpleNamespace(returncode=0, stdout=b'x'*4097), SimpleNamespace(returncode=0, stdout=b'\xff')])
def test_git_failures_do_not_echo_output(monkeypatch, result):
    monkeypatch.setattr(m.subprocess, 'run', lambda *_args, **_kwargs: result)
    with pytest.raises(m.PreparationCLIRefusal) as caught:
        m._git('rev-parse', 'HEAD')
    assert 'private error' not in str(caught.value)


def test_cli_failure_is_body_free_and_never_prints_success(monkeypatch, capsys):
    def failure():
        raise RuntimeError('sensitive underlying text')
    monkeypatch.setattr(m, 'build_preparation', failure)
    assert m.main([]) == 2
    out = capsys.readouterr()
    assert not out.out and 'sensitive underlying text' not in out.err


def test_cli_does_not_swallow_cancellation(monkeypatch):
    def cancel():
        raise KeyboardInterrupt()
    monkeypatch.setattr(m, 'build_preparation', cancel)
    with pytest.raises(KeyboardInterrupt):
        m.main([])


def test_cli_has_no_native_or_file_output_flags(monkeypatch, capsys):
    monkeypatch.setattr(m, 'build_preparation', lambda: pytest.fail('must not prepare'))
    assert m.main(['--launch']) == 2
    assert not capsys.readouterr().out
