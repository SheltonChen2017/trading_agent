"""Post-session-stop L identity plus inherited read-only K protocol regressions."""
import ast

import pytest

from scripts import run_arv2_r298_a19_error_after_session_stop as m
from scripts import run_arv2_r298_a19_error_reconciliation as frozen
from tests.analyst_revisions_v2 import test_r298_a19_error_reconciliation_caller as k_tests
from tests.analyst_revisions_v2._post_merge_pins import current_pin

args, control, projected, packet = k_tests.args, k_tests.control, k_tests.projected, k_tests.packet
workflow, joined, witness_terminal = k_tests.workflow, k_tests.joined, k_tests.witness_terminal


@pytest.fixture(autouse=True)
def new_parent_only(monkeypatch):
    monkeypatch.setattr(k_tests, 'm', m)
    k_tests.synthetic_boundaries.__wrapped__(monkeypatch)
    def forbidden(*_, **__): raise AssertionError('spent K operation invoked')
    for name in ('main', 'observe', 'run', 'worker', 'run_worker', 'join_worker', 'run_join_worker'):
        monkeypatch.setattr(frozen, name, forbidden)


def test_new_L_identity_binds_actual_K_and_scoped_stop_without_access_authority():
    assert m.CONTROL.name == 'R323-20261025-L' and m.CONTROL != frozen.CONTROL
    assert m.SCHEMA == 'arv2-r298-a19-error-after-session-stop-v1'
    assert m._remote() is frozen._remote()
    assert m.NEW_PINS == {**frozen.NEW_PINS,
        'scripts/run_arv2_r298_a19_error_reconciliation.py': '5ec52ee38a10a50e991d6136f376392966df65645834ca3467df17c2e6c0c9e3'}
    record = m.profile_record()
    assert record['k_spent'] is True and record['k_control_read'] is False
    assert record['k_actual_exit'] == 2 and record['k_validator_actual_exit'] == 0
    assert record['k_head'] == '960a3ceaeb4f1b7af235f2f971a40185f86d841a'
    assert record['k_stdout_bytes'] == 717
    assert record['k_stdout_sha256'] == 'c87498622660407cd3dac9a734d57baf7d410fda2852250bec807d073ab5b173'
    assert record['k_report_pin_returned'] is False
    assert record['k_failure_code'] == 'access_idle' and record['k_failure_stage'] == 'idle'
    assert record['k_application_dispatch_count'] == record['k_returned_response_count'] == 6
    assert record['k_selected_error_or_private_join_dispatched'] is False
    assert record['k_observation_and_error_null'] is True and record['k_evidence_documentary_only'] is True
    assert record['k_historical_cause_authenticated'] is False
    assert record['new_ui_verified_R298_environment_absent_other_lane_retained'] is True
    assert record['new_ui_R298_editor_opened'] is record['new_ui_source_build_or_job_dispatched'] is False
    assert record['new_ui_lock_or_permissions_changed'] is False
    assert record['new_ui_action_timestamp_instrumented'] is False
    assert record['new_ui_clock_after_verification_only'] == '2026-10-25T23:32:59Z'
    assert record['new_ui_observation_is_access_authority'] is False
    assert record['fresh_unchanged_access_verifier_required'] is True
    assert record['result_cell'] == record['new_jobs'] == record['new_compiles'] == record['new_source_writes'] == 0
    for name, pin in m.pins().items():
        assert len(pin) == 64 and m.sha((m.ROOT / name).read_bytes()) == current_pin(name, pin)


def test_L_denies_spent_K_as_well_as_all_old_controls_without_reading_them():
    for artifacts in (False, True):
        assert str(frozen.CONTROL) in m.native_profile(artifacts=artifacts)
        assert str(k_tests.previous.CONTROL) in m.native_profile(artifacts=artifacts)
    assert m.native_profile() == frozen.native_profile() + '(deny file-read* (subpath "' + str(frozen.CONTROL) + '"))'


def test_all_nonidentity_protocol_methods_are_AST_equal_to_spent_K():
    def selected(raw, newer=False):
        tree = ast.parse(raw)
        if newer:
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value == 'r323-l-observer-':
                    node.value = 'r323-k-observer-'
            remote = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_remote')
            comparisons = [node for node in ast.walk(remote) if isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Attribute) and node.left.attr == 'SCHEMA']
            assert len(comparisons) == 1
            assert comparisons[0].comparators[0].value == 'arv2-r298-a19-error-reconciliation-v1'
            comparisons[0].comparators[0] = ast.Name(id='SCHEMA', ctx=ast.Load())
        return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name not in ('profile_record', 'native_profile')}
    assert m.sha(frozen.SOURCE.read_bytes()) == '5ec52ee38a10a50e991d6136f376392966df65645834ca3467df17c2e6c0c9e3'
    assert selected(m.SOURCE.read_bytes(), True) == selected(frozen.SOURCE.read_bytes())


# Every inherited synthetic broker, native-worker, once-only join, postcheck,
# selected-response and output-authentication regression executes against L.
for _name in dir(k_tests):
    if _name.startswith('test_') and _name != 'test_fixed_read_only_scope_new_control_and_source_closure':
        globals()[_name] = getattr(k_tests, _name)
del _name
