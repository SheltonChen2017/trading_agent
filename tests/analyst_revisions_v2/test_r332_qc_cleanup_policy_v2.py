"""Prospective runtime-environment interpretation; all original gates retained."""
import ast
import hashlib
from pathlib import Path

import pytest

from scripts import arv2_r332_qc_cleanup_policy as old
from scripts import arv2_r332_qc_cleanup_policy_v2 as m
from tests.analyst_revisions_v2 import test_r332_qc_cleanup_policy as fixtures

V1_PIN = '230d7e47cad588e1cc30d89cd4b881bec2a9d751752eae9081079f085d7498ea'


def decide(p=None, h=None, **changes):
    args = {'user_id': fixtures.UID, 'record_bytes': fixtures.RECORD}
    args.update(changes)
    return m.decision(fixtures.project() if p is None else p,
        fixtures.history() if h is None else h, **args)


@pytest.mark.parametrize('environment', [0, 1, 2, 2147483647])
@pytest.mark.parametrize('last_live', [None, ''])
def test_nonnegative_runtime_environment_is_metadata_not_live_indicator(environment, last_live):
    p = fixtures.project(leanEnvironment=environment, lastLiveDeployment=last_live)
    result = decide(p)
    assert result['eligible'] and result['reason'] == 'no_successful_backtest'
    assert m.project_summary(p, fixtures.UID)['live_presence'] is False
    if environment != 0:
        assert old.decision(p, fixtures.history(), user_id=fixtures.UID,
            record_bytes=fixtures.RECORD)['reason'] == 'live_metadata_present'


@pytest.mark.parametrize('environment', [-1, True, False, 1.0, '1', None, 2147483648])
def test_invalid_or_unknown_runtime_environment_still_preserves(environment):
    result = decide(fixtures.project(leanEnvironment=environment))
    assert not result['eligible'] and result['reason'] == 'live_metadata_present'


@pytest.mark.parametrize('last_live', ['2026-10-28T00:00:00Z',
    '0001-01-01T00:00:00Z', '1970-01-01T00:00:00Z', ' ', 0, False, [], {}])
def test_nonempty_timestamp_sentinel_or_other_deployment_value_stays_blocked(last_live):
    result = decide(fixtures.project(leanEnvironment=1, lastLiveDeployment=last_live))
    assert not result['eligible'] and result['reason'] == 'live_metadata_present'


@pytest.mark.parametrize('field', ['leanEnvironment', 'lastLiveDeployment'])
def test_missing_metadata_is_not_inferred_from_one_fresh_C_observation(field):
    p = fixtures.project(leanEnvironment=1)
    del p[field]
    result = decide(p)
    assert not result['eligible'] and result['reason'] == 'live_metadata_present'


def test_exact_C_verification_shape_can_qualify_but_renamed_success_cannot():
    p = fixtures.project(projectId=37705240,
        name='ARV2 R284 PUBLIC SEVEN IDENTITY 20261007', leanEnvironment=1)
    result = decide(p, fixtures.history('Completed.'), record_bytes=b'project37705240')
    assert result['eligible'] and result['reason'] == 'verification_only'
    p['name'] = 'ARV2 Successful Strategy Research'
    result = decide(p, fixtures.history('Completed.'), record_bytes=b'project37705240')
    assert not result['eligible'] and result['reason'] == 'successful_backtest_retained'


@pytest.mark.parametrize('changes,reason', [
    ({'codeRunning': True}, 'active_or_unknown'),
    ({'owner': False}, 'owner_unverified'),
    ({'ownerId': fixtures.UID + 1}, 'owner_unverified'),
    ({'collaborators': [{'uid': fixtures.UID + 1, 'owner': False}]}, 'collaborator_present'),
    ({'libraries': [{'projectId': 34567890}]}, 'library_dependency'),
    ({'isLibrary': True}, 'library_dependency'),
])
def test_new_environment_rule_does_not_relax_other_current_metadata_guards(changes, reason):
    result = decide(fixtures.project(leanEnvironment=1, **changes))
    assert not result['eligible'] and result['reason'] == reason


@pytest.mark.parametrize('identity', sorted(m.PROTECTED))
def test_all_original_protected_dependencies_remain_protected(identity):
    result = decide(fixtures.project(projectId=identity, leanEnvironment=1),
        record_bytes=str(identity).encode())
    assert not result['eligible'] and result['reason'] == 'protected_dependency'


@pytest.mark.parametrize('identity,name', m.VERIFICATION_PROJECTS[1:])
def test_record_verified_purpose_pairs_qualify_with_completed_diagnostic(identity, name):
    p = fixtures.project(projectId=identity, name=name, leanEnvironment=1)
    result = decide(p, fixtures.history('Completed.'), record_bytes=str(identity).encode())
    assert result['eligible'] and result['reason'] == 'verification_only'
    assert result['verification_only'] and result['completed_count'] == 1


@pytest.mark.parametrize('identity,name', m.VERIFICATION_PROJECTS[1:])
def test_each_added_purpose_pair_loses_exception_if_current_name_changes(identity, name):
    p = fixtures.project(projectId=identity, name=name + ' renamed', leanEnvironment=1)
    result = decide(p, fixtures.history('Completed.'), record_bytes=str(identity).encode())
    assert not result['eligible'] and not result['verification_only']
    assert result['reason'] == 'successful_backtest_retained'


def test_recorded_historical_success_survives_current_failed_only_history():
    p = fixtures.project(projectId=37163942, name='ARV2 Historical R280', leanEnvironment=1)
    result = decide(p, fixtures.history('Runtime Error'), record_bytes=b'project37163942')
    assert not result['eligible'] and result['reason'] == 'protected_dependency'
    assert 37072332 not in m.VERIFICATION_ONLY


def test_exact_legacy_pair_is_owned_only_with_record_id_witness_and_is_protected():
    p = fixtures.project(projectId=37017548, name='Systematic Weekly Large-Cap Equity', leanEnvironment=1)
    assert m.ownership(p, b'project37017548')
    assert not m.ownership(p, b'no project witness')
    result = decide(p, fixtures.history('Runtime Error'), record_bytes=b'project37017548')
    assert not result['eligible'] and result['reason'] == 'protected_dependency'


@pytest.mark.parametrize('identity,name', [(37017548, 'Systematic Weekly Large-Cap Equity renamed'),
    (37017549, 'Systematic Weekly Large-Cap Equity')])
def test_legacy_exception_is_exact_pair_not_a_general_name_or_id_rule(identity, name):
    p = fixtures.project(projectId=identity, name=name, leanEnvironment=1)
    assert not m.ownership(p, str(identity).encode())
    result = decide(p, record_bytes=str(identity).encode())
    assert not result['eligible'] and result['reason'] == 'outside_lane'


def test_other_lane_unknown_history_and_reverse_library_reference_stay_preserved():
    p = fixtures.project(name='Insider Buying', leanEnvironment=1)
    assert decide(p)['reason'] == 'outside_lane'
    assert decide(fixtures.project(leanEnvironment=1), fixtures.history('In Progress...'))['reason'] == 'nonterminal_or_unknown_history'
    assert decide(fixtures.project(leanEnvironment=1), referenced_ids=frozenset((fixtures.PID,)))['reason'] == 'referenced_library'


def test_additive_V2_diff_is_exactly_declared_schema_environment_scope_and_retention():
    raw = Path(old.__file__).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == V1_PIN
    old_tree = ast.parse(raw)
    new_tree = ast.parse(Path(m.__file__).read_bytes())
    def assignments(tree):
        return {node.targets[0].id: node for node in tree.body if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    previous, current = assignments(old_tree), assignments(new_tree)
    schema = [current['SCHEMA']]
    assert len(schema) == 1 and schema[0].value.value == 'arv2-r332-qc-cleanup-policy-v2'
    schema[0].value.value = old.SCHEMA
    for key in ('PROTECTED', 'VERIFICATION_PROJECTS'):
        current[key].value = previous[key].value
    new_tree.body.remove(current['KNOWN_LEGACY_NAMES'])
    old_predicate = ast.parse("project['leanEnvironment'] != 0", mode='eval').body
    new_predicate = ast.parse("not 0 <= project['leanEnvironment'] <= 2147483647", mode='eval').body
    old_ownership = ast.parse('not _LANE.search(name)', mode='eval').body
    new_ownership = ast.parse('not (_LANE.search(name) or (project_id, name) in KNOWN_LEGACY_NAMES)', mode='eval').body
    count = scope_count = 0

    class Restore(ast.NodeTransformer):
        def visit_UnaryOp(self, node):
            nonlocal count, scope_count
            if ast.dump(node) == ast.dump(new_predicate):
                count += 1
                return old_predicate
            if ast.dump(node) == ast.dump(new_ownership):
                scope_count += 1
                return old_ownership
            return self.generic_visit(node)

    restored = Restore().visit(new_tree)
    assert count == scope_count == 1
    assert ast.dump(restored, include_attributes=False) == ast.dump(old_tree, include_attributes=False)
    assert set(m.PROTECTED) == set(old.PROTECTED) | {37163942, 37017548}
    assert m.VERIFICATION_PROJECTS[:1] == old.VERIFICATION_PROJECTS and len(m.VERIFICATION_PROJECTS) == 9
    assert m.KNOWN_LEGACY_NAMES == frozenset(((37017548, 'Systematic Weekly Large-Cap Equity'),))
    assert set(m.project_summary(fixtures.project(leanEnvironment=1), fixtures.UID)) == set(old.project_summary(fixtures.project(), fixtures.UID))
