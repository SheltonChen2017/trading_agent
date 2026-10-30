"""Exact-plan recycling with a synthetic API; no transport, worker or controls."""
import copy
import json

import pytest

from scripts import arv2_r332_qc_cleanup_policy_v2 as policy
from scripts import inspect_arv2_r332_qc_cleanup as inventory
from scripts import recycle_arv2_r332_qc_projects as m

USER, PID = 123, 37701234


def project(identity=PID, **changes):
    row = {'projectId': identity, 'name': 'ARV2 Synthetic Disposable ' + str(identity),
        'ownerId': USER, 'owner': True, 'codeRunning': False, 'language': 'Py',
        'collaborators': [{'uid': USER, 'owner': True}], 'libraries': [],
        'isLibrary': False, 'lastLiveDeployment': None, 'leanEnvironment': 1}
    row.update(changes)
    return row


def history(*statuses):
    return {'success': True, 'count': len(statuses), 'backtests': [
        {'backtestId': format(index + 1, '032x'), 'status': status}
        for index, status in enumerate(statuses)]}


def plan_for(row, packet, reason='no_successful_backtest'):
    return {'project_id': row['projectId'], 'name': row['name'], 'reason': reason,
        'history_sha256': policy.history_summary(packet)['history_sha256'],
        'summary_sha256': policy.digest(policy.project_summary(row, USER))}


class FakeAPI:
    """Only the five cleanup metadata/mutation operations are available."""
    def __init__(self, projects, histories, *, current=None, post=None, faults=None, catalogs=None):
        self.projects = copy.deepcopy(projects)
        self.histories = copy.deepcopy(histories)
        self.current = copy.deepcopy(current or {p['projectId']: p for p in projects})
        self.post = copy.deepcopy(post or {})
        self.faults = faults or {}
        self.catalogs = copy.deepcopy(catalogs or [projects])
        self.catalog_reads = 0
        self.calls, self.deleted = [], []

    def request(self, endpoint, payload):
        self.calls.append((endpoint, copy.deepcopy(payload)))
        identity = payload.get('projectId')
        stage = ('after' if identity in self.deleted else 'before')
        fault = self.faults.get((endpoint, identity, stage))
        if fault is not None:
            # A failed mutation call may already have affected the server.
            if endpoint == 'projects/delete':
                self.deleted.append(identity)
            raise fault
        if endpoint == 'projects/read' and payload == {}:
            position = min(self.catalog_reads, len(self.catalogs) - 1)
            self.catalog_reads += 1
            return {'success': True, 'projects': copy.deepcopy(self.catalogs[position])}
        if endpoint == 'projects/read':
            assert payload == {'projectId': identity}
            if identity in self.deleted:
                row = copy.deepcopy(self.post.get(identity, self.current[identity]))
                if identity not in self.post:
                    row['name'] = 'Recycle Bin/synthetic/' + row['name']
            else:
                row = copy.deepcopy(self.current[identity])
            return {'success': True, 'projects': [row]}
        if endpoint == 'backtests/list':
            assert payload == {'projectId': identity, 'includeStatistics': False}
            return copy.deepcopy(self.histories[identity])
        assert endpoint == 'projects/delete' and payload == {'projectId': identity}
        assert identity not in self.deleted, 'mutation must never retry'
        self.deleted.append(identity)
        return {'success': True}


@pytest.fixture(autouse=True)
def public_library_only(monkeypatch):
    monkeypatch.setattr(m, 'lib', inventory)


def run(api, plan):
    witness = ' '.join(str(row['project_id']) for row in plan).encode('ascii')
    return m.recycle(api, policy, witness, USER, plan)


@pytest.mark.parametrize('statuses', [(), ('Runtime Error',), ('Stopped', 'Cancelled')])
def test_exact_candidate_gets_one_delete_and_same_id_recycle_confirmation(statuses):
    row, packet = project(), history(*statuses)
    api = FakeAPI([row], {PID: packet})
    result = run(api, [plan_for(row, packet)])
    assert result['complete'] and result['recycled_count'] == result['planned_count'] == 1
    assert result['projects'][0]['recycled'] is True
    assert api.calls == [('projects/read', {}), ('projects/read', {'projectId': PID}),
        ('backtests/list', {'projectId': PID, 'includeStatistics': False}),
        ('projects/read', {}),
        ('projects/delete', {'projectId': PID}), ('projects/read', {'projectId': PID})]
    assert api.deleted == [PID]


def test_exact_verification_only_candidate_can_recycle_completed_diagnostic():
    row = project(37705240, name='ARV2 R284 PUBLIC SEVEN IDENTITY 20261007')
    packet = history('Completed.')
    api = FakeAPI([row], {row['projectId']: packet})
    result = run(api, [plan_for(row, packet, 'verification_only')])
    assert result['complete'] and api.deleted == [37705240]
    assert result['projects'][0]['reason'] == 'verification_only'


def test_renamed_historical_verification_project_with_success_is_preserved():
    # An ID's old diagnostic purpose cannot override current repurposing.
    row = project(37705240, name='ARV2 Synthetic Research With Successful Runs')
    packet = history('Completed.')
    api = FakeAPI([row], {row['projectId']: packet})
    result = run(api, [plan_for(row, packet, 'verification_only')])
    assert not result['complete'] and not api.deleted


@pytest.mark.parametrize('changes', [
    {'name': 'Unrelated Synthetic Research'},
    {'name': 'ARV2 Insider Buying'},
    {'name': 'ARV2 Synthetic Changed Name'},
    {'codeRunning': True},
    {'owner': False},
    {'ownerId': USER + 1},
    {'collaborators': [{'uid': USER + 1, 'owner': False}]},
    {'libraries': [{'projectId': PID + 8}]},
    {'lastLiveDeployment': 'synthetic-live-presence'},
])
def test_changed_unsafe_or_other_lane_current_metadata_stops_before_delete(changes):
    row, packet = project(), history('Runtime Error')
    api = FakeAPI([row], {PID: packet}, current={PID: project(**changes)})
    result = run(api, [plan_for(row, packet)])
    assert result['complete'] is False and result['recycled_count'] == 0
    assert api.deleted == []
    assert all(endpoint != 'projects/delete' for endpoint, _ in api.calls)
    assert result['projects'][0]['reason'] == 'changed_or_ineligible'


@pytest.mark.parametrize('identity', sorted(policy.PROTECTED))
def test_protected_dependency_refuses_even_with_matching_external_plan(identity):
    row, packet = project(identity), history()
    api = FakeAPI([row], {identity: packet})
    result = run(api, [plan_for(row, packet)])
    assert not result['complete'] and not api.deleted
    assert result['projects'][0]['reason'] == 'changed_or_ineligible'


def test_historical_success_with_later_runtime_status_drift_is_preserved():
    # R280's original record authenticates a valid result; current Runtime
    # Error status must not erase that history or make its source disposable.
    row, packet = project(37163942), history('Runtime Error')
    api = FakeAPI([row], {row['projectId']: packet})
    result = run(api, [plan_for(row, packet)])
    assert not result['complete'] and not api.deleted
    assert result['projects'][0]['reason'] == 'changed_or_ineligible'


def test_other_lane_library_reference_protects_the_target_without_exporting_other_metadata():
    row, packet = project(), history('Runtime Error')
    other = project(PID + 1, name='Unrelated Synthetic Research',
        libraries=[{'projectId': PID}], description='invented-private-extra')
    api = FakeAPI([row, other], {PID: packet})
    result = run(api, [plan_for(row, packet)])
    assert not result['complete'] and not api.deleted
    assert 'invented-private-extra' not in json.dumps(result)
    assert other['name'] not in json.dumps(result)


@pytest.mark.parametrize('change', ('library', 'busy', 'owner', 'missing-target'))
def test_fresh_catalog_blocks_new_reference_or_target_change_immediately_before_delete(change):
    row, packet = project(), history('Runtime Error')
    latest = [copy.deepcopy(row)]
    other = project(PID + 1, name='Other Synthetic Lane', description='invented-private-extra')
    if change == 'library':
        other['libraries'] = [{'projectId': PID}]
        latest.append(other)
    elif change == 'busy':
        latest[0]['codeRunning'] = True
    elif change == 'owner':
        latest[0]['ownerId'] = USER + 1
    else:
        latest = [other]
    api = FakeAPI([row], {PID: packet}, catalogs=[[row], latest])
    result = run(api, [plan_for(row, packet)])
    assert not result['complete'] and not api.deleted
    assert api.catalog_reads == 2
    assert result['projects'][0]['reason'] == 'changed_or_ineligible'
    assert result['projects'][0]['deletion_outcome_ambiguous'] is False
    assert other['name'] not in json.dumps(result)
    assert 'invented-private-extra' not in json.dumps(result)


@pytest.mark.parametrize('current_history', [history(), history('Runtime Error', 'Stopped'),
    history('Completed.'), history('In Progress...')])
def test_changed_history_or_nonterminal_run_stops_before_delete(current_history):
    row, packet = project(), history('Runtime Error')
    api = FakeAPI([row], {PID: current_history})
    result = run(api, [plan_for(row, packet)])
    assert not result['complete'] and not api.deleted


@pytest.mark.parametrize('field,value', [('summary_sha256', 'f' * 64),
    ('history_sha256', 'f' * 64), ('reason', 'verification_only')])
def test_external_summary_history_and_reason_bindings_all_precede_delete(field, value):
    row, packet = project(), history('Runtime Error')
    selected = plan_for(row, packet); selected[field] = value
    api = FakeAPI([row], {PID: packet})
    assert not run(api, [selected])['complete'] and not api.deleted


def test_ambiguous_delete_stops_batch_and_retains_attempt_without_retry():
    first, second = project(), project(PID + 1)
    packet = history('Runtime Error')
    api = FakeAPI([first, second], {PID: packet, PID + 1: packet},
        faults={('projects/delete', PID, 'before'): inventory.Refused('transport')})
    result = run(api, [plan_for(first, packet), plan_for(second, packet)])
    assert not result['complete'] and result['recycled_count'] == 0
    [selected] = result['projects']
    assert selected['reason'] == 'transport' and selected['delete_attempted'] is True
    assert api.deleted == [PID]
    assert all(payload.get('projectId') != PID + 1 for _, payload in api.calls)
    assert sum(endpoint == 'projects/delete' for endpoint, _ in api.calls) == 1


@pytest.mark.parametrize('post_changes', [{'name': 'Still Original'},
    {'name': 'Recycle Bin/synthetic/Not The Intended Project'},
    {'projectId': PID + 1}])
def test_unconfirmed_post_delete_identity_is_terminal_without_second_target(post_changes):
    first, second = project(), project(PID + 1)
    packet = history('Runtime Error')
    after = dict(first, **post_changes)
    api = FakeAPI([first, second], {PID: packet, PID + 1: packet}, post={PID: after})
    result = run(api, [plan_for(first, packet), plan_for(second, packet)])
    assert not result['complete'] and result['recycled_count'] == 0
    assert result['projects'][0]['reason'] == 'recycle_not_confirmed'
    assert api.deleted == [PID]
    assert all(payload.get('projectId') != PID + 1 for _, payload in api.calls)


def test_confirmed_first_delete_is_retained_when_second_target_metadata_changed():
    first, second, third = project(), project(PID + 1), project(PID + 2)
    packet = history('Runtime Error')
    api = FakeAPI([first, second, third], dict.fromkeys((PID, PID + 1, PID + 2), packet),
        current={PID: first, PID + 1: project(PID + 1, codeRunning=True), PID + 2: third})
    result = run(api, [plan_for(p, packet) for p in (first, second, third)])
    assert not result['complete'] and result['planned_count'] == 3
    assert result['recycled_count'] == 1 and len(result['projects']) == 2
    assert result['projects'][0]['recycled'] and not result['projects'][1]['recycled']
    assert api.deleted == [PID]
    assert all(payload.get('projectId') != PID + 2 for _, payload in api.calls)


def test_safe_failure_does_not_render_arbitrary_exception_objects():
    class PrivateError(ValueError):
        def __str__(self):
            raise AssertionError('exception rendering is forbidden')
    assert m.safe_failure(PrivateError('invented-private-value')) == 'unknown'
    assert m.safe_failure(ValueError({'invented': 'private-value'})) == 'unknown'


@pytest.mark.parametrize('mutation', [
    lambda rows: rows.reverse(),
    lambda rows: rows.append(copy.deepcopy(rows[0])),
    lambda rows: rows[0].update(project_id=True),
    lambda rows: rows[0].update(history_sha256='bad'),
    lambda rows: rows[0].update(unexpected=True),
])
def test_plan_schema_sorting_uniqueness_and_exact_scalar_types_refuse(mutation):
    packet = history('Runtime Error')
    rows = [plan_for(project(), packet), plan_for(project(PID + 1), packet)]
    mutation(rows)
    with pytest.raises(ValueError, match='^plan$'):
        m.plan_value(inventory.canonical(rows).decode('ascii'), policy.digest(rows))


def test_plan_content_hash_is_external_and_exact():
    rows = [plan_for(project(), history())]
    raw = inventory.canonical(rows).decode('ascii')
    assert m.plan_value(raw, policy.digest(rows)) == rows
    with pytest.raises(ValueError, match='^plan$'):
        m.plan_value(raw, '0' * 64)
