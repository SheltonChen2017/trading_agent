"""Fabricated historical packets and temporary directories, never actual sources."""
import base64
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[1] / 'scripts/persist_short_interest_usb_observation.py'
HEAD, REMOTE = 'a' * 40, 'b' * 40


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('_fabricated_usb_observation_copy', SOURCE)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    root = tmp_path.resolve(); monkeypatch.chdir(root)
    monkeypatch.setattr(module, 'ROOT', root)
    monkeypatch.setattr(module, 'BASE', root / 'observations')
    monkeypatch.setattr(module, 'DIRECTORY', module.BASE / module.INVOCATION)
    # Only the toy directory's preexisting ancestors may need this seam under
    # /tmp. Production still rejects writable ancestry; its rule is tested too.
    originals = {(p.stat().st_dev, p.stat().st_ino) for p in root.parents}
    original_dir = module._dir
    def toy_dir(info):
        if (info.st_dev, info.st_ino) in originals and info.st_mode & 0o022:
            assert stat.S_ISDIR(info.st_mode)
            return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode
        return original_dir(info)
    monkeypatch.setattr(module, '_dir', toy_dir)
    return module


def supplied(q, *, bootstrap=False, negative=False):
    authority = {'finite_offline_byte_inspection_only': True, **{key: False for key in
        ('source_qualified', 'source_admitted', 'protected_source_custody_verified', 'denominator_admitted',
         'actual_input_admitted', 'ready_for_backtest', 'QC_or_Safari')}, **{key: 0 for key in
        ('provider_HTTP', 'source_credential_reads', 'new_claims', 'new_STARTs', 'new_charged_bytes', 'outcome_looks', 'qc_attempts')}}
    body = {'schema': 'si-usb-once-envelope-v1', 'invocation_id': q.INVOCATION,
            'runtime_head': HEAD, 'matching_remote': REMOTE, 'source_qualified': False,
            'status': 'incomplete' if negative else 'closed_finite_offline_byte_inspection', 'authority': authority}
    if bootstrap:
        body = {'schema': 'si-usb-once-bootstrap-refusal-v1', 'invocation_id': q.INVOCATION,
                'status': 'incomplete', 'source_qualified': False, 'first_failure': None, 'cleanup_failures': []}
    packet = q.canonical(body) + b'\n'
    observed = {'schema': 'si-usb-once-owned-observation-v1', 'runtime_head': HEAD, 'matching_remote': REMOTE,
                'invocation_id': q.INVOCATION, 'status': 'incomplete' if bootstrap or negative else 'closed_finite_offline_byte_observation',
                'producer_status': body['status'], 'test_seams_used': False,
                'source_qualified': False, 'source_admitted': False, 'ready_for_backtest': False,
                'stdout_EOF': True, 'stderr_EOF': True, 'original_stdout_complete': True,
                'stdout_bytes_observed': len(packet), 'stdout_bytes_retained': len(packet),
                'original_stdout_sha256': q.sha(packet), 'retained_stdout_sha256': q.sha(packet),
                'actual_exit_code': 2 if negative or bootstrap else 0, 'actual_signal': None,
                'exit_observed': True, 'close_observed': True}
    value = {'schema': 'si-usb-observation-private-copy-v1', 'runtime_head': HEAD, 'matching_remote': REMOTE,
             'invocation_id': q.INVOCATION, 'original_stdout_base64': base64.b64encode(packet).decode(),
             'owned_observation': observed}
    return value, packet


def publish(q, value):
    return q.persist(q.canonical(value))


@pytest.mark.parametrize('negative,bootstrap', [(False, False), (True, False), (True, True)])
def test_exact_historical_copy_preserves_bytes_without_process_or_source_authority(prepared, negative, bootstrap):
    q = prepared; value, packet = supplied(q, negative=negative, bootstrap=bootstrap)
    result = publish(q, value)
    assert result['status'] == 'private_observation_copy_closed', (result['first_failure'], result['cleanup_failures'])
    assert result['source_authority'] is result['source_admitted'] is result['ready_for_backtest'] is False
    assert result['process_claims'] == 'caller_attested_historical_copy_not_independently_observed'
    assert set(p.name for p in q.DIRECTORY.iterdir()) == set(q.NAMES)
    assert (q.DIRECTORY / q.NAMES[0]).read_bytes() == packet
    saved = json.loads((q.DIRECTORY / q.NAMES[1]).read_bytes())
    assert saved['owned_observation'] == value['owned_observation'] and saved['source_authority'] is False
    for name in q.NAMES:
        path = q.DIRECTORY / name; pin = q._stamp(path.stat())
        assert stat.S_IMODE(pin[4]) == 0o600 and pin[5] == 1
        assert result['files'][name] == {'bytes': len(path.read_bytes()), 'sha256': q.sha(path.read_bytes()),
                                       'original_file10_sha256': q.sha(q.canonical(list(pin)))}


@pytest.mark.parametrize('change', ['sha', 'length', 'head', 'remote', 'invocation', 'test', 'authority', 'EOF', 'unknown', 'noncanonical'])
def test_bad_copy_binding_refuses_before_destination_creation(prepared, change):
    q = prepared; value, unused = supplied(q); observed = value['owned_observation']
    if change == 'sha': observed['original_stdout_sha256'] = 'f' * 64
    elif change == 'length': observed['stdout_bytes_retained'] += 1
    elif change == 'head': value['runtime_head'] = 'c' * 40
    elif change == 'remote': value['matching_remote'] = 'c' * 40
    elif change == 'invocation': value['invocation_id'] = 'other'
    elif change == 'test': observed['test_seams_used'] = True
    elif change == 'authority': observed['source_admitted'] = True
    elif change == 'EOF': observed['original_stdout_complete'] = False
    elif change == 'unknown': value['unfrozen'] = True
    raw = q.canonical(value) + (b' ' if change == 'noncanonical' else b'')
    result = q.persist(raw)
    assert result['status'] == 'incomplete' and not q.BASE.exists()


def test_nested_authority_is_not_granted_by_copying_json(prepared):
    q = prepared; value, packet = supplied(q); body = json.loads(packet)
    body['private_model_aggregate'] = {'authority': {'inspection_only': True, 'source_admitted': True}}
    packet = q.canonical(body) + b'\n'; value['original_stdout_base64'] = base64.b64encode(packet).decode()
    value['owned_observation'].update(stdout_bytes_observed=len(packet), stdout_bytes_retained=len(packet),
                                    original_stdout_sha256=q.sha(packet), retained_stdout_sha256=q.sha(packet))
    assert publish(q, value)['status'] == 'incomplete' and not q.BASE.exists()


def test_existing_namespace_is_never_adopted_or_overwritten(prepared):
    q = prepared; value, unused = supplied(q); first = publish(q, value)
    before = {p.name: p.read_bytes() for p in q.DIRECTORY.iterdir()}
    with pytest.raises(q.CopyRefusal, match='spent'): publish(q, value)
    q._USED = False  # Fabricate a new process; the existing namespace still vetoes it.
    second = publish(q, value)
    assert first['status'] == 'private_observation_copy_closed' and second['status'] == 'incomplete'
    assert second['first_failure']['code'] == 'exists'
    assert {p.name: p.read_bytes() for p in q.DIRECTORY.iterdir()} == before


def test_symlink_base_is_refused(prepared):
    q = prepared; value, unused = supplied(q); target = q.ROOT / 'unrelated'; target.mkdir()
    q.BASE.symlink_to(target, target_is_directory=True)
    assert publish(q, value)['status'] == 'incomplete' and not (target / q.INVOCATION).exists()


def test_permissive_existing_base_is_refused_without_chmod_or_adoption(prepared):
    q = prepared; value, unused = supplied(q); q.BASE.mkdir(mode=0o755)
    assert publish(q, value)['status'] == 'incomplete' and stat.S_IMODE(q.BASE.stat().st_mode) == 0o755
    assert not q.DIRECTORY.exists()


@pytest.mark.parametrize('change', ['input_bound', 'raw_bound', 'summary_bound', 'base64', 'duplicate'])
def test_bounded_strict_input_refuses_without_publishing(prepared, change):
    q = prepared; value, unused = supplied(q)
    if change == 'raw_bound': value['original_stdout_base64'] = base64.b64encode(b'x' * (q.MAX_RAW + 1)).decode()
    elif change == 'summary_bound': value['owned_observation']['private_padding'] = 'x' * q.MAX_SUMMARY
    elif change == 'base64': value['original_stdout_base64'] += '\n'
    raw = q.canonical(value)
    if change == 'input_bound': raw = b'x' * (q.MAX_INPUT + 1)
    elif change == 'duplicate': raw = raw[:-1] + b',"schema":"si-usb-observation-private-copy-v1"}'
    result = q.persist(raw)
    assert result['status'] == 'incomplete' and not q.BASE.exists()


def test_public_receipt_never_exports_the_private_caller_payload(prepared):
    q = prepared; value, unused = supplied(q)
    value['owned_observation']['private_marker'] = 'FABRICATED_PRIVATE_DO_NOT_ECHO'
    result = publish(q, value)
    assert result['status'] == 'private_observation_copy_closed'
    assert b'FABRICATED_PRIVATE_DO_NOT_ECHO' not in q.canonical(result)
    assert 'FABRICATED_PRIVATE_DO_NOT_ECHO' in (q.DIRECTORY / q.NAMES[1]).read_text()


def test_owner_uid_is_required_without_elevation(prepared, monkeypatch):
    q = prepared; value, unused = supplied(q)
    monkeypatch.setattr(q.os, 'geteuid', lambda: os.getuid() + 1)
    assert publish(q, value)['status'] == 'incomplete' and not q.BASE.exists()


def test_original_directory_rule_does_not_accept_writable_ancestry(prepared):
    q = prepared
    function = q._Anchors.audit.__globals__['_dir']
    # The fixture seam applies only to exact preexisting toy ancestor inodes.
    bad = SimpleNamespace(st_mode=stat.S_IFDIR | 0o777, st_uid=os.getuid(), st_gid=os.getgid(), st_dev=-1, st_ino=-1)
    with pytest.raises(q.CopyRefusal, match='directory'): function(bad)


def test_creator_gid_is_the_original_held_parent_not_process_gid(prepared, monkeypatch):
    q = prepared; value, unused = supplied(q)
    original_gid = os.getgid()
    monkeypatch.setattr(q.os, 'getgid', lambda: original_gid + 1)
    result = publish(q, value)
    assert result['status'] == 'private_observation_copy_closed'
    assert q.BASE.stat().st_gid == q.BASE.parent.stat().st_gid
    assert all((q.DIRECTORY / name).stat().st_gid == q.DIRECTORY.stat().st_gid for name in q.NAMES)


def test_metadata_drift_after_first_seal_stays_negative_and_preserves_content(prepared, monkeypatch):
    q = prepared; value, packet = supplied(q); original = q._Anchors.file_audit; changed = False
    def drift(self, name, fd, pin, raw):
        nonlocal changed
        original(self, name, fd, pin, raw)
        if not changed and name == q.NAMES[0]:
            changed = True; os.utime(q.DIRECTORY / name, ns=(pin[7], pin[7] + 1))
    monkeypatch.setattr(q._Anchors, 'file_audit', drift)
    result = publish(q, value)
    assert changed and result['status'] == 'incomplete'
    assert (q.DIRECTORY / q.NAMES[0]).read_bytes() == packet


def test_partial_write_failure_preserves_spent_prefix_without_retry(prepared, monkeypatch):
    q = prepared; value, packet = supplied(q); original = os.write; count = 0
    def broken(fd, raw):
        nonlocal count
        count += 1
        if count == 1: return original(fd, raw[:3])
        raise OSError(errno.EIO, 'private exception text must not escape')
    monkeypatch.setattr(q.os, 'write', broken)
    result = publish(q, value)
    assert result['status'] == 'incomplete' and (q.DIRECTORY / q.NAMES[0]).read_bytes() == packet[:3]
    assert 'private exception' not in q.canonical(result).decode() and not (q.DIRECTORY / q.NAMES[1]).exists()


@pytest.mark.parametrize('which', [1, 4])
def test_constructor_fstat_failure_closes_every_owned_descriptor(prepared, monkeypatch, which):
    q = prepared; value, unused = supplied(q); opened = set(); calls = 0
    real_open, real_close, real_fstat = os.open, os.close, os.fstat
    def opening(*args, **kwargs):
        fd = real_open(*args, **kwargs); opened.add(fd); return fd
    def closing(fd):
        try: return real_close(fd)
        finally: opened.discard(fd)
    def failure(fd):
        nonlocal calls
        calls += 1
        if calls == which: raise OSError(errno.EIO, 'secret')
        return real_fstat(fd)
    monkeypatch.setattr(q.os, 'open', opening); monkeypatch.setattr(q.os, 'close', closing); monkeypatch.setattr(q.os, 'fstat', failure)
    assert publish(q, value)['status'] == 'incomplete' and not opened


def test_close_failure_is_negative_but_other_descriptors_still_close(prepared, monkeypatch):
    q = prepared; value, unused = supplied(q); real_open, real_close = os.open, os.close; opened = set(); failed = False
    def opening(*args, **kwargs):
        fd = real_open(*args, **kwargs); opened.add(fd); return fd
    def closing(fd):
        nonlocal failed
        real_close(fd); opened.discard(fd)
        if not failed:
            failed = True; raise OSError(errno.EIO, 'hidden')
    monkeypatch.setattr(q.os, 'open', opening); monkeypatch.setattr(q.os, 'close', closing)
    result = publish(q, value)
    assert failed and result['status'] == 'incomplete' and not opened
    assert result['first_failure']['phase'] == 'close'


def test_original_file_protection_change_after_close_is_not_resealed(prepared, monkeypatch):
    q = prepared; value, unused = supplied(q); real_close = os.close; changed = False
    def closing(fd):
        nonlocal changed
        real_close(fd)
        if not changed and (q.DIRECTORY / q.NAMES[0]).exists():
            changed = True; os.chmod(q.DIRECTORY / q.NAMES[0], 0o644)
    monkeypatch.setattr(q.os, 'close', closing)
    result = publish(q, value)
    assert changed and result['status'] == 'incomplete' and stat.S_IMODE((q.DIRECTORY / q.NAMES[0]).stat().st_mode) == 0o644


def test_fresh_postclose_read_checks_original_bytes_without_stamp_rebaseline(prepared, monkeypatch):
    q = prepared; value, unused = supplied(q); original = q._Anchors.file_audit; count = 0; reached = False
    def corrupt_read(self, name, fd, pin, raw):
        nonlocal count, reached
        if name == q.NAMES[0]: count += 1
        if name != q.NAMES[0] or count != 3: return original(self, name, fd, pin, raw)
        reached = True; real_read = os.read
        try:
            q.os.read = lambda actual, size: b'wrong' if actual == fd else real_read(actual, size)
            return original(self, name, fd, pin, raw)
        finally: q.os.read = real_read
    monkeypatch.setattr(q._Anchors, 'file_audit', corrupt_read)
    result = publish(q, value)
    assert reached and result['status'] == 'incomplete' and result['first_failure']['code'] == 'bytes'


def test_last_named_file_audit_runs_after_all_ancestor_handles_close(prepared, monkeypatch):
    q = prepared; value, packet = supplied(q); original_open = q._Anchors.open; real_close = os.close; scope = []; changed = False
    def capture(self):
        original_open(self); scope.append(self)
    def closing(fd):
        nonlocal changed
        real_close(fd)
        if scope and fd == scope[0].fds[0] and not changed:
            changed = True; path = q.DIRECTORY / q.NAMES[0]; info = path.stat()
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
    monkeypatch.setattr(q._Anchors, 'open', capture); monkeypatch.setattr(q.os, 'close', closing)
    result = publish(q, value)
    assert changed and result['status'] == 'incomplete' and result['first_failure']['code'] == 'stamp'
    assert (q.DIRECTORY / q.NAMES[0]).read_bytes() == packet


def test_expiry_before_writes_does_not_create_payload_files(prepared, monkeypatch):
    q = prepared; value, unused = supplied(q); now = [0]; original = q._Anchors.write
    monkeypatch.setattr(q.time, 'monotonic_ns', lambda: now[0])
    def expired(self, name, raw):
        now[0] = 11 * 10**9; return original(self, name, raw)
    monkeypatch.setattr(q._Anchors, 'write', expired)
    result = publish(q, value)
    assert result['status'] == 'incomplete' and q.DIRECTORY.exists() and not list(q.DIRECTORY.iterdir())


def test_actual_cli_terminal_serialization_expiry_cannot_emit_closed_receipt(prepared, monkeypatch, capsys):
    q = prepared; value, unused = supplied(q); now = [0]; serializations = 0; original = q.canonical
    monkeypatch.setattr(q.time, 'monotonic_ns', lambda: now[0])
    def serialize(value):
        nonlocal serializations
        if type(value) is dict and value.get('schema') == 'si-usb-private-copy-receipt-v1':
            serializations += 1
            if serializations == 2: now[0] = 11 * 10**9
        return original(value)
    read, write = os.pipe(); os.write(write, q.canonical(value)); os.close(write)
    with os.fdopen(read, 'rb') as stream:
        monkeypatch.setattr(q.sys, 'stdin', stream); monkeypatch.setattr(q.sys, 'argv', ['publisher'])
        monkeypatch.setattr(q, 'canonical', serialize)
        assert q.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert serializations >= 2 and result['status'] == 'incomplete' and result['first_failure']['code'] == 'clock'


@pytest.mark.parametrize('change', ['exit_code', 'exit_bool', 'producer_incomplete'])
def test_closed_copy_requires_a_closed_process_and_producer(prepared, change):
    """SI-CR28-019: the copier's own lineage check before anything is created."""
    q = prepared; value, packet = supplied(q, negative=change == 'producer_incomplete'); observed = value['owned_observation']
    if change == 'exit_code': observed['actual_exit_code'] = 2
    elif change == 'exit_bool': observed['actual_exit_code'] = False
    else: observed.update(status='closed_finite_offline_byte_observation', actual_exit_code=0)
    result = publish(q, value)
    assert result['status'] == 'incomplete' and result['first_failure']['code'] == 'lineage' and not q.BASE.exists()
