"""Synthetic ownership/retention boundaries; no QC or private artifacts."""
import copy
import json

import pytest

from scripts import arv2_r332_qc_cleanup_policy as m

UID, PID = 123, 37701234
RECORD = b'Public lane record project `37701234`; verification37705240.'


def project(**changes):
    value = {'projectId': PID, 'name': '101 ARV2_ORDER_RESEARCH_2026',
        'ownerId': UID, 'owner': True, 'language': 'Py', 'codeRunning': False,
        'collaborators': [{'uid': UID, 'owner': True}], 'libraries': [],
        'leanEnvironment': 0, 'lastLiveDeployment': None}
    value.update(changes)
    return value


def history(*statuses, **changes):
    value = {'success': True, 'backtests': [
        {'backtestId': format(i + 1, '032x'), 'status': status}
        for i, status in enumerate(statuses)], 'count': len(statuses)}
    value.update(changes)
    return value


def decide(p=None, h=None, **changes):
    args = {'user_id': UID, 'record_bytes': RECORD}
    args.update(changes)
    return m.decision(project() if p is None else p,
        history() if h is None else h, **args)


@pytest.mark.parametrize('statuses', [(), ('Runtime Error',), ('Stopped', 'Cancelled')])
def test_no_completed_backtest_is_candidate_including_zero_backtests(statuses):
    result = decide(h=history(*statuses))
    assert result['eligible'] and result['reason'] == 'no_successful_backtest'
    assert result['backtest_count'] == len(statuses) and result['completed_count'] == 0


@pytest.mark.parametrize('statuses', [('Completed.',), ('Runtime Error', 'Completed.'), ('Completed',)])
def test_any_successful_backtest_preserves_research_project(statuses):
    result = decide(h=history(*statuses))
    assert not result['eligible'] and result['reason'] == 'successful_backtest_retained'


def test_explicit_verification_only_project_can_recycle_despite_completed_diagnostic():
    p = project(projectId=37705240, name='ARV2 R284 PUBLIC SEVEN IDENTITY 20261007')
    result = decide(p, history('Completed.'))
    assert result['eligible'] and result['verification_only']
    assert result['reason'] == 'verification_only' and result['completed_count'] == 1


@pytest.mark.parametrize('identity,name', [
    (37705240, 'ARV2 Completed Strategy Research'),
    (37705240, 'ARV2 R284 PUBLIC SEVEN IDENTITY 20261007 renamed'),
    (36561231, 'ARV2 Historical Compile Project Now Research'),
    (36642921, 'ARV2 Historical PIT Project Now Research'),
])
def test_historical_verification_id_without_exact_current_purpose_preserves_success(identity, name):
    result = decide(project(projectId=identity, name=name), history('Completed.'),
        record_bytes=str(identity).encode())
    assert not result['eligible'] and not result['verification_only']
    assert result['reason'] == 'successful_backtest_retained'


@pytest.mark.parametrize('identity', [36561231, 36642921])
def test_former_compile_or_refusal_project_still_qualifies_without_a_completed_run(identity):
    result = decide(project(projectId=identity, name='ARV2 Historical Infrastructure'),
        history(), record_bytes=str(identity).encode())
    assert result['eligible'] and not result['verification_only']
    assert result['reason'] == 'no_successful_backtest'


@pytest.mark.parametrize('project_id', sorted(m.PROTECTED))
def test_current_dependencies_and_historical_preservation_exception_survive(project_id):
    p = project(projectId=project_id)
    result = decide(p, history(), record_bytes=str(project_id).encode())
    assert not result['eligible'] and result['reason'] == 'protected_dependency'


@pytest.mark.parametrize('name', ['Insider Buying', 'ARV2 Insider Buying',
    'ARV2 Short Interest', 'ARV2 Target-Price Revisions', 'ARV2X Other',
    'Other ARV20 lane', 'Recycle Bin/101 ARV2_OLD'])
def test_other_or_recycled_projects_never_enter_lane_scope(name):
    result = decide(project(name=name))
    assert not result['lane_owned'] and not result['eligible']
    assert result['reason'] == 'outside_lane'


def test_name_alone_is_not_creation_evidence_and_id_witness_is_not_prefix_match():
    p = project()
    assert not m.ownership(p, b'project377012345')
    assert not m.ownership(p, b'project137701234')
    assert not m.ownership(p, b'No record of this project.')
    assert m.ownership(p, RECORD)


def test_unrelated_unicode_project_name_is_ignored_before_lane_name_normalization():
    assert not m.ownership(project(name='外部研究项目'), RECORD)
    with pytest.raises(m.Refused, match='^project_name$'):
        m.ownership(project(name='ARV2 外部研究项目'), RECORD)


@pytest.mark.parametrize('changes,reason', [
    ({'owner': False}, 'owner_unverified'),
    ({'ownerId': UID + 1}, 'owner_unverified'),
    ({'ownerId': True}, 'owner_unverified'),
    ({'codeRunning': True}, 'active_or_unknown'),
    ({'codeRunning': None}, 'active_or_unknown'),
    ({'language': 'C#'}, 'language_unverified'),
    ({'collaborators': [{'uid': UID + 1, 'owner': False}]}, 'collaborator_present'),
    ({'collaborators': [{'uid': 'edit-lock', 'owner': False}]}, 'collaborator_present'),
    ({'libraries': [{'projectId': 34567890}]}, 'library_dependency'),
    ({'isLibrary': True}, 'library_dependency'),
    ({'lastLiveDeployment': '2026-10-01T00:00:00Z'}, 'live_metadata_present'),
    ({'leanEnvironment': 1}, 'live_metadata_present'),
    ({'leanEnvironment': False}, 'live_metadata_present'),
])
def test_unsafe_project_state_preserves_even_if_no_successful_backtest(changes, reason):
    result = decide(project(**changes))
    assert not result['eligible'] and result['reason'] == reason


def test_reverse_library_reference_from_another_lane_preserves_target():
    projects = [project(), project(projectId=40000000, name='Other lane',
        libraries=[{'projectId': PID, 'ownerName': 'ignored'}])]
    references = m.referenced_project_ids(projects)
    assert references == frozenset((PID,))
    result = decide(referenced_ids=references)
    assert not result['eligible'] and result['reason'] == 'referenced_library'


@pytest.mark.parametrize('field', ['lastLiveDeployment', 'leanEnvironment'])
def test_missing_live_state_metadata_is_unknown_and_preserves(field):
    p = project()
    del p[field]
    result = decide(p)
    assert not result['eligible'] and result['reason'] == 'live_metadata_present'


@pytest.mark.parametrize('status', ['In Queue...', 'In Progress...', 'Unknown', 'Completed. '])
def test_nonterminal_or_unknown_history_prevents_candidate_selection(status):
    p = project(projectId=37705240)
    result = decide(p, history(status), record_bytes=b'37705240')
    assert not result['eligible'] and result['reason'] == 'nonterminal_or_unknown_history'


@pytest.mark.parametrize('packet,code', [
    (None, 'history_shape'),
    ({'success': False, 'backtests': [], 'count': 0}, 'history_shape'),
    (history(errors=['refused']), 'history_shape'),
    (history(count=None), 'history_count'),
    (history('Runtime Error', count=0), 'history_count'),
    (history('Runtime Error', count=True), 'history_count'),
    ({'success': True, 'backtests': None, 'count': 0}, 'history_shape'),
    ({'success': True, 'backtests': [{'backtestId': 'bad', 'status': 'Runtime Error'}], 'count': 1}, 'history_row'),
])
def test_missing_or_malformed_history_is_refusal_never_empty_success(packet, code):
    with pytest.raises(m.Refused) as caught:
        m.history_summary(packet)
    assert m.finite(caught.value) == code


def test_duplicate_history_id_refuses_and_new_run_or_status_changes_comparison_pin():
    packet = history('Runtime Error')
    packet['backtests'] *= 2
    packet['count'] = 2
    with pytest.raises(m.Refused, match='^history_duplicate$'):
        m.history_summary(packet)
    assert m.history_summary(history())['history_sha256'] != m.history_summary(history('Runtime Error'))['history_sha256']
    assert m.history_summary(history('Completed.'))['history_sha256'] != m.history_summary(history('Runtime Error'))['history_sha256']


def test_result_discards_sensitive_extras_and_never_mutates_supplied_metadata():
    p = project(apiToken='invented-secret', liveForm={'private': 'invented-secret'},
        description='invented-secret', sharingTokenBacktest='invented-secret')
    h = history('Runtime Error')
    h['backtests'][0].update(netProfit='invented-private-value', statistics={'price': 'invented-private-value'})
    before = copy.deepcopy((p, h))
    result, summary = decide(p, h), m.project_summary(p, UID)
    assert (p, h) == before
    assert 'invented-secret' not in json.dumps((result, summary))
    assert 'invented-private-value' not in json.dumps((result, summary))
    assert set(result) == {'project_id', 'name', 'lane_owned', 'eligible', 'reason',
        'verification_only', 'completed_count', 'backtest_count', 'history_sha256'}
    assert set(summary) == {'project_id', 'name', 'owner_current', 'idle', 'python',
        'sole_owner', 'libraries', 'library', 'live_presence'}


@pytest.mark.parametrize('bad', [None, True, 0, -1, 2147483648, '37701234'])
def test_project_id_requires_exact_positive_native_int(bad):
    with pytest.raises(m.Refused, match='^project_id$'):
        m.ownership(project(projectId=bad), RECORD)


def test_source_is_pure_and_all_failure_messages_are_finite():
    import ast
    from pathlib import Path
    tree = ast.parse(Path(m.__file__).read_text())
    imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)}
    assert imports == {'hashlib', 'json', 're'}
    assert m.finite(ValueError('invented-private-value')) == 'unknown'
    assert m.finite(m.Refused({'invented': 'private'})) == 'unknown'
