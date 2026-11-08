"""Strict R access recovery; unchanged P scientific contract, synthetic only."""
import ast
import copy

import pytest

from scripts import arv2_r298_reference_series_recovery_remote as m
from tests.analyst_revisions_v2 import test_r298_reference_series_phase_remote as base
from tests.analyst_revisions_v2 import test_r298_reference_series_phase_projection as public_tests
from tests.analyst_revisions_v2 import test_post_mia_access as access_tests

STRICT_VERIFY = m.access.verify_access
CURRENT_VERIFY = m.frozen.access.verify_access
launch = base.launch


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(base.m, 'QuoteDiagnostic', m.QuoteDiagnostic)
    state = base.cloud.__wrapped__(monkeypatch)
    monkeypatch.setattr(m.access, 'verify_access', m.frozen.access.verify_access)
    for name in ('PROJECTION_SHA256', 'PROFILE_SHA256', 'SOURCE_MANIFEST_SHA256'):
        monkeypatch.setattr(m, name, getattr(m.frozen, name))
    return state


def test_wrapper_only_overrides_access_and_never_mutates_frozen_globals():
    assert m.QuoteDiagnostic.__bases__ == (m.frozen.QuoteDiagnostic,)
    assert {name for name in vars(m.QuoteDiagnostic) if not name.startswith('__')} == {'_access'}
    assert m.BACKTEST_NAME == m.frozen.BACKTEST_NAME and m.ATTEMPT == 'P'
    assert m.SCHEMA == m.frozen.SCHEMA == 'arv2-r298-reference-series-phase-p-v1'
    assert m.access is not m.frozen.access
    raw = m.frozen.__file__
    from pathlib import Path
    assert m.sha(Path(raw).read_bytes()) == '660d8f5f2ac8d0bf7f1382d2667db9a229c44ee47d47d96cd1408a927da182fd'
    tree = ast.parse(Path(m.__file__).read_bytes())
    assert not any(isinstance(node, ast.Assign) and any(isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name) and target.value.id == 'frozen'
        for target in node.targets) for node in ast.walk(tree))
    profile = m.profile_record()
    assert profile['scientific_attempt'] == 2 and profile['maximum_scientific_attempts'] == 3
    assert profile['mia_general_row_accepted'] is profile['scientific_source_changed'] is False


@pytest.mark.parametrize('mia', [False, True])
def test_strict_owner_A5_pass_but_Mia_general_row_refuses_before_write(cloud, monkeypatch, mia):
    supplied = access_tests.supplied.__wrapped__(monkeypatch)
    monkeypatch.setattr(m.access, 'verify_access', STRICT_VERIFY)
    if mia:
        row = {'name': 'Mia', 'uid': None, 'owner': False, 'permission': 'write', 'liveControl': True,
            'publicId': 'synthetic-Mia-ID', 'email': 'synthetic-Mia-email'}
        supplied.project['projects'][0]['collaborators'].append(row)
        # Even the exact third-row shape accepted by the former P access
        # policy is outside R's strictly narrower owner/A5-only contract.
        for name in ('OWNER_ROW_SHA256', 'A5_ROW_SHA256'):
            monkeypatch.setattr(m.frozen.access, name, getattr(m.access, name))
        monkeypatch.setattr(m.frozen.access, 'MIA_ROW_SHA256', m.sha(m.access._canonical(row)))
        monkeypatch.setattr(m.frozen.access, 'MIA_PUBLIC_ID_SHA256', m.sha(m.access._canonical(row['publicId'])))
        assert CURRENT_VERIFY(supplied.project, supplied.dedicated)['matched_current_access_representation'] is True
        # An omission must exercise the real former broader verifier, not
        # the cloud fixture's unrelated {'busy': ...} access stub.
        monkeypatch.setattr(m.frozen.access, 'verify_access', CURRENT_VERIFY)
    prior = cloud.runner._request
    def request(endpoint, payload):
        if endpoint == 'projects/read':
            cloud.calls.append((endpoint, copy.deepcopy(payload))); return copy.deepcopy(supplied.project)
        if endpoint == 'projects/collaboration/read':
            cloud.calls.append((endpoint, copy.deepcopy(payload))); return copy.deepcopy(supplied.dedicated)
        return prior(endpoint, payload)
    cloud.runner._request = request
    if mia:
        with pytest.raises(m.access.AccessRefused, match='general_collaborators'): cloud.runner.prepare_once()
        assert not any(endpoint in ('files/update', 'compile/create', 'backtests/create') for endpoint, _ in cloud.calls)
    else:
        launch(cloud)
        assert sum(endpoint == 'files/update' for endpoint, _ in cloud.calls) == 2


def test_recovery_keeps_each_fresh_prewrite_source_and_access_gate(cloud):
    launch(cloud)
    names = [endpoint for endpoint, _ in cloud.calls]
    for index, name in enumerate(names):
        if name == 'files/update':
            assert names[index-4:index] == ['projects/read', 'projects/collaboration/read', 'backtests/list', 'files/read']
    assert names.count('backtests/create') == 1 and not any('lock' in name for name in names)


def test_busy_during_recovery_stops_before_second_write(cloud):
    def mutation(endpoint, payload):
        if endpoint == 'files/update': cloud.busy = True
    cloud.mutation = mutation
    with pytest.raises(m.access.AccessRefused): cloud.runner.prepare_once()
    assert sum(endpoint == 'files/update' for endpoint, _ in cloud.calls) == 1


def test_unmodified_scientific_result_metadata_and_read_once(cloud):
    cloud.create_status = 'Completed.'; launch(cloud)
    result = cloud.runner.read_once()
    assert result['schema'] == m.SCHEMA and result['attempt'] == 'P'
    assert result['result_cell'] == 0 and result['metadata']['diagnostic_complete'] is True
    with pytest.raises(ValueError): cloud.runner.read_once()


def test_genuine_public_scientific_constructor_is_P_and_dispatches_nothing():
    public = public_tests.public.__wrapped__()
    def deny(*args, **kwargs): pytest.fail('constructor dispatched')
    value = m.QuoteDiagnostic(public.projection.record_bytes, public.projection.source_pairs,
        request=deny, journal=deny)
    assert public.projection.projection_sha256 == m.PROJECTION_SHA256
    assert value.compile_receipt is value.launch_receipt is value.terminal_receipt is None
