"""Supplied public-metadata AR plans; no actual old or new DATA/QC access."""
import ast
import builtins
import copy
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_common_price_transfer_plan as m
from tests.analyst_revisions_v2 import test_r298_common_price_sidecar_producer as fixture


@pytest.fixture
def case():
    args = NS(expected_head='a' * 40, caller_sha256='b' * 64, profile_sha256='c' * 64)
    # Port only this pre-existing SYNTHETIC public metadata fixture's schema;
    # no prior producer/validator/data/control operation is called or replayed.
    result = m.fmt.loads(m.canonical(fixture.result()).replace(
        fixture.m.SCHEMA.encode('ascii'), m.AR_SCHEMA.encode('ascii')), m.sidecar.MAX_OUTPUT)
    binding = m.sidecar.binding(args)
    outcome = {'result': result, 'report': m.fmt.pin(m.canonical({**binding, 'result': result}))}
    output = {'binding': binding, 'outcome': outcome}; raw = m.canonical(output) + b'\n'
    def actual(start, end):
        return {'actual_exit': 0, 'bound': None, 'spawn_observed': True,
            'dispatched_at': start, 'completion_observed_at': end, 'stdout_bytes': len(raw),
            'stdout_sha256': m.sha(raw), 'stderr_bytes': 0, 'stderr_sha256': m.sha(b'')}
    kwargs = {'producer_actual': actual('2026-10-27T14:00:00Z', '2026-10-27T14:01:00Z'),
        'validator_actual': actual('2026-10-27T14:01:01Z', '2026-10-27T14:01:02Z'),
        'frozen_AR_binding': binding, 'project_id': 40000002,
        'organization_sha256': m.ORGANIZATION_SHA256}
    return NS(output=output, kwargs=kwargs, raw=raw)


def test_exact73_content_addressed_objects_and_manifest_last_match_QC_reader(case):
    plan = m.make_plan(case.output, **case.kwargs); rows = plan['objects']
    assert len(rows) == plan['object_count'] == 73
    assert [row['ordinal'] for row in rows] == list(range(73))
    assert rows[0]['role'] == 'catalog' and rows[-1]['role'] == 'manifest'
    assert rows[0]['relative_path'] == m.AR_DIRECTORY + '/catalog-private.json'
    assert rows[0]['object_store_key'] == plan['object_key_prefix'] + 'catalog.json'
    assert rows[-1]['relative_path'] == m.AR_DIRECTORY + '/manifest-private.json'
    assert rows[-1]['object_store_key'] == plan['object_key_prefix'] + 'manifest.json'
    for index, row in enumerate(rows[1:-1]):
        assert row['role'] == 'month' and row['month_ordinal'] == index
        assert row['relative_path'] == m.AR_DIRECTORY + '/month-' + format(index, '03d') + '.jsonl'
        assert row['object_store_key'] == plan['object_key_prefix'] + 'month-' + format(index, '02d') + '-' + row['sha256'] + '.jsonl'
    assert plan['object_inventory_sha256'] == m.digest(rows)
    assert plan['total_byte_count'] == sum(row['byte_count'] for row in rows) <= m.MAX_TOTAL_BYTES
    assert plan['object_key_prefix'] == '40000002/arv2/r326-common/' + plan['manifest_pin']['sha256'] + '/'
    assert plan['permitted_future_storage_endpoints'] == ['object/properties', 'object/set']
    assert all(plan[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('role', ['producer_actual', 'validator_actual'])
@pytest.mark.parametrize('field,value', [('actual_exit', 2), ('actual_exit', None), ('actual_exit', True),
    ('bound', 'deadline'), ('spawn_observed', False), ('stderr_bytes', 1), ('stderr_sha256', 'f' * 64),
    ('stdout_sha256', 'f' * 64), ('stdout_bytes', 1)])
def test_nonzero_unknown_or_mismatched_actual_process_is_not_success(case, role, field, value):
    args = copy.deepcopy(case.kwargs); args[role][field] = value
    with pytest.raises(m.Refused): m.make_plan(case.output, **args)


def test_actual_records_and_AR_binding_are_exact_closed_types(case):
    for change in ('extra', 'timestamps', 'ordering', 'binding', 'float_project', 'other_org'):
        args = copy.deepcopy(case.kwargs)
        if change == 'extra': args['producer_actual']['extra'] = 'no'
        elif change == 'timestamps': args['producer_actual']['completion_observed_at'] = 'invalid'
        elif change == 'ordering': args['validator_actual']['dispatched_at'] = '2026-10-27T13:59:00Z'
        elif change == 'binding': args['frozen_AR_binding']['caller_sha256'] = 'd' * 64
        elif change == 'float_project': args['project_id'] = 40000002.0
        else: args['organization_sha256'] = 'd' * 64
        with pytest.raises(m.Refused): m.make_plan(case.output, **args)


@pytest.mark.parametrize('field', ['source_guards_normal_return', 'genuine_input_unchanged', 'post_checks_complete'])
def test_closed_source_normal_return_and_original_input_proofs_are_retained(case, field):
    output = copy.deepcopy(case.output); output['outcome']['result'][field] = False
    # Preserve actual-channel equality for the changed synthetic output so the
    # decisive refusal must be AR's semantic proof, not the outer hash alone.
    output['outcome']['report'] = m.fmt.pin(m.canonical({**output['binding'], 'result': output['outcome']['result']}))
    raw = m.canonical(output) + b'\n'; args = copy.deepcopy(case.kwargs)
    for role in ('producer_actual', 'validator_actual'):
        args[role]['stdout_bytes'] = len(raw); args[role]['stdout_sha256'] = m.sha(raw)
    with pytest.raises(m.Refused): m.make_plan(output, **args)


def test_source_inventory_pin_cap_and_payload_smuggling_refuse(case):
    for change in ('month_size', 'catalog_size', 'unknown_payload'):
        output = copy.deepcopy(case.output)
        descriptor = output['outcome']['result']['manifest_descriptor']
        if change == 'month_size': descriptor['months'][0]['byte_count'] = m.fmt.MAX_MONTH_BYTES + 1
        elif change == 'catalog_size': descriptor['catalog_pin']['byte_count'] = m.fmt.MAX_CATALOG_BYTES + 1
        else: descriptor['assignments'] = [{'ticker': 'SYNTHETIC'}]
        raw = m.canonical(output) + b'\n'; args = copy.deepcopy(case.kwargs)
        for role in ('producer_actual', 'validator_actual'):
            args[role]['stdout_bytes'] = len(raw); args[role]['stdout_sha256'] = m.sha(raw)
        with pytest.raises(m.Refused): m.make_plan(output, **args)


def test_plan_is_metadata_only_deepcopy_and_all_boundaries_stay_false(case):
    before = copy.deepcopy(case.output); plan = m.make_plan(case.output, **case.kwargs)
    raw = m.canonical(plan)
    assert b'"assignments"' not in raw and b'"ticker"' not in raw and b'"prices"' not in raw
    assert b'"closeunadj"' not in raw and b'"api_key"' not in raw
    assert plan['source_grid']['original_stock_assignments'] == 6151
    assert plan['source_grid']['positive_cells'] + plan['source_grid']['explicit_absent_cells'] == 8195088
    assert plan['properties_initial_recheck_put_verify_maximum_dispatches'] == 292
    assert plan['no_retry_or_cleanup_or_delete_or_object_get'] is True
    plan['objects'][0]['sha256'] = 'f' * 64
    plan['AR_producer_actual']['actual_exit'] = 2
    assert case.output == before and case.kwargs['producer_actual']['actual_exit'] == 0
    assert m.make_plan(case.output, **case.kwargs)['objects'][0]['sha256'] != 'f' * 64


def test_fresh_import_and_full_plan_derivation_have_no_I_O_or_operation(case, monkeypatch):
    raw = Path(m.__file__).read_bytes(); tree = ast.parse(raw)
    assert not any(isinstance(node, ast.Import) and any(alias.name in ('os', 'socket', 'subprocess', 'requests')
        for alias in node.names) for node in ast.walk(tree))
    def denied(*args, **kwargs): raise AssertionError('pure transfer plan attempted I/O/operation')
    namespace = {'__name__': 'synthetic_transfer_plan_import'}
    with monkeypatch.context() as patch:
        for obj, name in ((builtins, 'open'), (os, 'open'), (Path, 'read_bytes'), (Path, 'read_text'),
                (socket, 'socket'), (socket, 'getaddrinfo'), (subprocess, 'Popen'),
                (m.sidecar, 'run'), (m.sidecar, 'construct'), (m.sidecar, 'preflight')):
            patch.setattr(obj, name, denied)
        exec(compile(raw, '<public-transfer-plan>', 'exec'), namespace)
        plan = namespace['make_plan'](case.output, **case.kwargs)
        assert plan['object_count'] == 73 and plan['QC_contact'] is False


def test_old_AQ_schema_and_control_namespace_cannot_be_admitted_as_new_AR(case):
    args = copy.deepcopy(case.kwargs); output = copy.deepcopy(case.output)
    args['frozen_AR_binding']['schema'] = fixture.m.SCHEMA
    output['binding'] = copy.deepcopy(args['frozen_AR_binding'])
    raw = m.canonical(output) + b'\n'
    for role in ('producer_actual', 'validator_actual'):
        args[role]['stdout_bytes'] = len(raw); args[role]['stdout_sha256'] = m.sha(raw)
    with pytest.raises(m.Refused): m.make_plan(output, **args)
    plan = m.make_plan(case.output, **case.kwargs)
    assert all('/R326-20261027-AR/' in row['relative_path'] and '/R326-20261027-AQ/' not in row['relative_path']
        for row in plan['objects'])
