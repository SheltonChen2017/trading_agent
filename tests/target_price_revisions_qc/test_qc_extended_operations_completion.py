"""Synthetic ON1/OFF3 lifecycle only; no real filesystem/credential/cloud use."""
from copy import deepcopy
from pathlib import Path

import pytest
from research.target_price_revisions_qc import extended_operations_completion as successor
from tests.target_price_revisions_qc import test_qc_extended_operations_compressed as old_tests

old, base, e = successor.predecessor, successor.base, successor.e
ON, OFF = successor.ON, successor.OFF


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    monkeypatch.setattr(old, 'PROJECT_IDS', {ON: 101, OFF: 102})
    monkeypatch.setattr(old, 'ORGANIZATION_SHA256', base.digest(b'synthetic-org'))
    def deny(*_args, **_kw): raise AssertionError('actual filesystem/credential/network forbidden')
    monkeypatch.setattr(base, 'credential', deny); monkeypatch.setattr(base.http.client, 'HTTPSConnection', deny)
    guard, reading = base.Operations.guard, base.read_private
    def guarded(self):
        assert self.fixture and not self.root.is_relative_to(base.LANE)
        return guard(self)
    def read(root, name, maximum=e.MAX_BYTES):
        assert not root.is_relative_to(base.LANE)
        return reading(root, name, maximum)
    monkeypatch.setattr(base.Operations, 'guard', guarded)
    monkeypatch.setattr(base, 'read_private', read)


def body():
    data, _, _, _ = old_tests.body()
    data['operation_id'] = 'TPR-EXT26-QC-COMPLETION-SYNTHETIC-006'
    helper = Path('research/target_price_revisions_qc/extended_completion_successor.py').read_text()
    data['repository_source_hashes'].update({name: 'd' * 64 for name in successor.REQUIRED})
    data['repository_source_hashes'][successor.completion.PREDECESSOR_BUNDLE] = successor.completion.PREDECESSOR_SHA256
    data['repository_source_hashes'][successor.PREFIX + successor.completion.HELPER] = base.digest(helper.encode())
    data['repository_source_hashes'][successor.PREFIX + 'extended_operations.py'] = old.previous.BASE_SOURCE_SHA256
    data['repository_source_hashes'][successor.PREFIX + 'extended_driver.py'] = old.previous.BASE_DRIVER_SHA256
    for row in data['candidates']:
        row['files'][successor.completion.HELPER] = helper
        if row['candidate_id'] == OFF:
            row['planned_attempt'] = 3
            row['files']['main.py'] = row['files']['main.py'].replace('EXPECTED_ATTEMPT = 2', 'EXPECTED_ATTEMPT = 3')
    return data


def setup(tmp_path, *, close_off2=True):
    first, second, cloud, _ = old_tests.setup(tmp_path)
    old_tests.ready(second, OFF, 2); second.launch(OFF, 2)
    if close_off2: second.status(OFF, 2)
    data = body()
    current = successor.Operations(data, manifest_sha256=e.digest(e.canonical(data)),
        fixture_root=second.root, fixture_transport=second.transport)
    current.prepare()
    return first, second, current, cloud


def test_off3_preserves_two_failed_attempts_counts_and_all_inherited_effect_guards(tmp_path):
    _, previous, current, cloud = setup(tmp_path)
    preserved = {name: previous.read(name) for attempt in (1, 2)
        for name in [OFF + '.attempt.' + str(attempt) + '.' + suffix for suffix in
            ('manifest.json', 'reservation.json', 'closure.json', 'look.json', 'terminal.json')]}
    old_tests.ready(current, OFF, 3); current.launch(OFF, 3); current.status(OFF, 3)
    assert current.history(OFF)[0] == 3 and current.history(ON)[0] == 0
    assert all(current.read(name) == raw for name, raw in preserved.items())
    look = current.value(OFF + '.attempt.3.look.json')
    assert look['old_looks'].fraction() == 18 and look['persistent_observed_looks_before'].fraction() == 2
    assert current.reserve.__func__ is base.Operations.reserve and current.attempt.__func__ is base.Operations.attempt
    assert current.launch.__func__ is old.Operations.launch and current.status.__func__ is base.Operations.status
    with pytest.raises(ValueError): current.reserve(OFF)
    assert current.history(OFF)[0] == 3 and cloud.calls.count('backtests/create') == 3
    assert cloud.calls.count('projects/create') == 2
    assert not list(current.root.glob('compressed-input.*.read.spent.json'))


def test_active_off2_cannot_be_relaunched_or_reserved_under_changed_completion_source(tmp_path):
    _, _, current, cloud = setup(tmp_path, close_off2=False)
    before = cloud.calls.count('backtests/create')
    with pytest.raises(ValueError): current.status(OFF, 2)
    with pytest.raises(ValueError): current.launch(OFF, 2)
    current.upload_sources(OFF)
    with pytest.raises(ValueError): current.reserve(OFF)
    assert current.history(OFF)[0] == 2 and cloud.calls.count('backtests/create') == before


@pytest.mark.parametrize('kind', ['reset', 'helper', 'packet', 'closure', 'predecessor', 'main_attempt', 'config'])
def test_constructor_refuses_scope_or_counter_substitution(tmp_path, kind):
    data = body(); row = data['candidates'][1]
    if kind == 'reset': row['planned_attempt'] = 2
    if kind == 'helper': row['files'][successor.completion.HELPER] += '# changed\n'
    if kind == 'packet': row['files']['signal_packet.py'] = 'VALUE = 1\n'
    if kind == 'closure': data['repository_source_hashes'].pop(successor.PREFIX + 'extended_driver_completion.py')
    if kind == 'predecessor': data['repository_source_hashes'][successor.completion.PREDECESSOR_BUNDLE] = 'a' * 64
    if kind == 'main_attempt': row['files']['main.py'] = row['files']['main.py'].replace('EXPECTED_ATTEMPT = 3', 'EXPECTED_ATTEMPT = 1')
    if kind == 'config': row['files']['main.py'] = row['files']['main.py'].replace(e.digest(row['config_raw'].encode()), 'a' * 64)
    with pytest.raises(ValueError):
        successor.Operations(data, manifest_sha256=e.digest(e.canonical(data)),
            fixture_root=tmp_path / 'private', fixture_transport=old_tests.Cloud())


def test_on_transport_failure_stays_spent_and_cannot_be_renewed_by_completion_scope(tmp_path):
    _, previous, current, cloud = setup(tmp_path)
    row = previous.transport_rows[0]
    previous.write('compressed-input.' + row['gzip_sha256'] + '.read.spent.json', {'synthetic': True})
    before = len(cloud.calls)
    with pytest.raises(ValueError): current.upload_inputs(ON)
    with pytest.raises(ValueError): current.upload_inputs(OFF)
    with pytest.raises(ValueError): current.create_project(ON)
    with pytest.raises(ValueError): current.recover_project(ON)
    assert len(cloud.calls) == before and current.history(ON)[0] == 0


@pytest.mark.parametrize('field', ['project_id', 'organization_id'])
def test_inherited_bound_project_and_organization_refuse_before_cloud(tmp_path, field):
    _, _, current, cloud = setup(tmp_path)
    name = OFF + '.project.json'; row = current.value(name)
    row[field] = 999 if field == 'project_id' else 'foreign-org'
    (current.root / name).write_bytes(e.canonical(row))
    before = len(cloud.calls)
    with pytest.raises(ValueError): current.upload_sources(OFF)
    assert len(cloud.calls) == before
