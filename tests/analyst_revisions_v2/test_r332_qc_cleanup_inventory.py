"""Inventory projection failures cannot retain an earlier positive decision."""
from types import SimpleNamespace

import pytest

from scripts import arv2_r332_qc_cleanup_policy as policy
from scripts import inspect_arv2_r332_qc_cleanup as inventory


def project(identity=12345678):
    return {'projectId': identity, 'name': 'ARV2 Synthetic Disposable',
        'ownerId': 123, 'owner': True, 'codeRunning': False, 'language': 'Py',
        'collaborators': [], 'libraries': [], 'isLibrary': False,
        'lastLiveDeployment': '', 'leanEnvironment': 0}


class FakeAPI:
    def __init__(self, row, history):
        self.row, self.history = row, history
        self.last_http_status = 200
        self.store = SimpleNamespace(dispatches=0, intents=0)

    def request(self, endpoint, payload):
        self.store.dispatches += 1
        self.store.intents += 1
        if endpoint == 'projects/read':
            assert payload == {}
            return {'success': True, 'projects': [self.row]}
        assert endpoint == 'backtests/list'
        assert payload == {'projectId': self.row['projectId'], 'includeStatistics': False}
        return self.history


def history(count):
    return {'success': True, 'count': count, 'backtests': [
        {'backtestId': format(index + 1, '032x'), 'status': 'Runtime Error'}
        for index in range(count)]}


def run(row, packet):
    return inventory.inventory(FakeAPI(row, packet), policy,
        ('project ' + str(row['projectId'])).encode('ascii'), 123)


def test_safe_exact_history_produces_candidate_metadata_only():
    result = run(project(), history(1))
    [row] = result['projects']
    assert row['eligible'] is True and result['eligible_count'] == 1
    assert row['backtests'] == [{'backtest_id': '0' * 31 + '1', 'status': 'Runtime Error'}]
    assert result['deletion_performed'] is False and result['application_dispatch_count'] == 2


def test_post_decision_projection_refusal_erases_earlier_positive_eligibility():
    # 4097 is valid for the pure policy, but exceeds this finite inventory
    # channel's stricter selected-row cap after the decision was computed.
    row = project(); packet = history(4097)
    assert policy.decision(row, packet, user_id=123,
        record_bytes=b'project 12345678')['eligible'] is True
    result = run(row, packet)
    [selected] = result['projects']
    assert selected['eligible'] is False and selected['reason'] == 'history'
    assert result['eligible_count'] == 0


def test_protected_project_bad_history_is_retained_with_finite_refusal():
    row = project(38522505)
    packet = {'success': True, 'count': 1, 'backtests': [{'status': 'Runtime Error'}]}
    result = run(row, packet)
    [selected] = result['projects']
    assert selected['eligible'] is False and selected['reason'] == 'policy_metadata_refusal'
    assert result['eligible_count'] == 0 and 'backtests' not in selected


def test_store_opens_existing_ancestors_without_attempting_forbidden_mkdir(tmp_path, monkeypatch):
    control = tmp_path / 'fresh-parent' / 'A'
    monkeypatch.setattr(inventory, 'CONTROL', control)
    mkdir = inventory.os.mkdir
    attempted = []

    def only_new(path, mode=0o777, *, dir_fd=None):
        # Under the operational native policy, trying mkdir on an existing
        # old artifacts ancestor may be denied before EEXIST is reported.
        assert path in ('fresh-parent', 'A')
        attempted.append(path)
        return mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(inventory.os, 'mkdir', only_new)
    store = inventory.Store()
    try:
        result = store.write('report.json', {'synthetic': True})
        assert result == inventory.pin(inventory.canonical({'synthetic': True}))
        assert (control / 'report.json').read_bytes() == inventory.canonical({'synthetic': True})
    finally:
        store.close()
    assert attempted == ['fresh-parent', 'A']


def test_existing_control_is_spent_and_never_overwritten(tmp_path, monkeypatch):
    control = tmp_path / 'fresh-parent' / 'A'
    monkeypatch.setattr(inventory, 'CONTROL', control)
    store = inventory.Store()
    try:
        store.write('claim.json', {'synthetic': True})
    finally:
        store.close()
    before = (control / 'claim.json').read_bytes()
    with pytest.raises(inventory.Refused, match='^claim_spent$'):
        inventory.Store()
    assert (control / 'claim.json').read_bytes() == before
