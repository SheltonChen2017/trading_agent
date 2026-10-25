"""Pure public-byte history contract tests; synthetic counts, no real captures."""
import ast
from copy import deepcopy
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_sharadar_history_design as m

PUBLIC = Path(__file__).resolve().parents[2] / 'research/target_price_revisions_qc'


@pytest.fixture
def inputs():
    return {'repair_freeze_raw': (PUBLIC / 'extended_sharadar_repair_freeze.json').read_bytes(),
        'study_freeze_raw': (PUBLIC / 'extended_study_freeze.json').read_bytes(),
        'calendar_raw': (PUBLIC / 'extended_calendar.json').read_bytes()}


def census(**changes):
    body = {'page_rows': [7], 'terminated': True, 'earliest_date': '2020-09-01',
        'latest_date': '2026-10-09', 'in_window_year_counts': {year: 1 for year in m.YEARS},
        'before_window_rows': 0, 'after_window_rows': 0, 'invalid_date_rows': 0, 'missing_date_rows': 0}
    body.update(changes)
    return body


def test_exact_explicit_full_window_query_not_old_to_only_default(inputs):
    for page in (0, 1, 127):
        assert m.query_for_page(**inputs, page=page) == {'from': '2020-09-01', 'to': '2026-10-09',
            'sort': 'date.asc', 'fields': 'ticker,date,action,contraticker', 'format': 'csv',
            'limit': '10000', 'skip': str(page * 10000)}


@pytest.mark.parametrize('page', (-1, 128, True, False, 1.0, '1', None, [], {}))
def test_invalid_or_widened_page_refuses(inputs, page):
    with pytest.raises(m.HistoryDesignRefusal): m.query_for_page(**inputs, page=page)


@pytest.mark.parametrize('name', ('repair_freeze_raw', 'study_freeze_raw', 'calendar_raw'))
@pytest.mark.parametrize('fault', ('hash', 'type', 'empty', 'oversize'))
def test_public_bytes_are_pinned_before_contract(inputs, name, fault):
    inputs[name] = (inputs[name] + b' ' if fault == 'hash' else 'not bytes' if fault == 'type'
        else b'' if fault == 'empty' else b'x' * 65537)
    with pytest.raises(m.HistoryDesignRefusal): m.build_design(**inputs)


def test_design_is_fresh_and_grants_no_operation_or_admission(inputs):
    design = m.build_design(**inputs)
    assert design['requested_from'] == '2020-09-01' and design['requested_to'] == '2026-10-09'
    assert design['active_operation'] is design['active_permit'] is None
    assert design['fresh_identified_capture_required'] and design['identity_comparison_still_required']
    for key in ('historical_entitlement_verified', 'requested_date_coverage_proven',
        'current_tickers_is_historical_identity_series', 'old_capture_modified', 'inputs_rebuilt',
        'provider_access_authorized', 'qc_access_authorized', 'off_native_recovery_blocked_by_this_design',
        'on_admission', 'canonical_admission', 'attempt_reset'): assert design[key] is False
    design['public_source_sha256']['repair'] = 'changed'
    assert m.build_design(**inputs)['public_source_sha256'] == m.PINS


def test_every_year_observed_is_still_not_full_history_or_authority(inputs):
    supplied = census(); original = deepcopy(supplied)
    result = m.coverage_summary(**inputs, census=supplied)
    assert supplied == original and result['observations_in_every_requested_year'] is True
    assert result['pagination_terminated'] is True and result['missing_requested_years'] == []
    for key in ('complete_requested_history_proven', 'provider_authenticity_verified',
        'historical_entitlement_verified', 'point_in_time_verified', 'current_tickers_is_historical_identity_series',
        'on_admission', 'canonical_admission', 'attempt_reset'): assert result[key] is False
    assert result['fresh_capture_scope_still_required']


def test_empty_terminated_sample_is_not_historical_coverage(inputs):
    supplied = census(page_rows=[0], earliest_date=None, latest_date=None,
        in_window_year_counts={year: 0 for year in m.YEARS})
    result = m.coverage_summary(**inputs, census=supplied)
    assert result['pagination_terminated'] and result['retained_rows'] == 0
    assert result['missing_requested_years'] == list(m.YEARS)
    assert result['observations_in_every_requested_year'] is result['complete_requested_history_proven'] is False


def test_attributed_one_year_pattern_remains_incomplete_not_recapture_authority(inputs):
    supplied = census(page_rows=[10000, 10000, 10000, 10000, 9716], earliest_date='2025-10-13',
        latest_date='2026-10-09', in_window_year_counts={**dict.fromkeys(m.YEARS, 0), '2025': 12803, '2026': 36913})
    result = m.coverage_summary(**inputs, census=supplied)
    assert result['retained_rows'] == 49716 and result['pagination_terminated']
    assert result['missing_requested_years'] == list(m.YEARS[:5])
    assert result['observations_in_every_requested_year'] is result['on_admission'] is False


@pytest.mark.parametrize('fault', ('extra', 'missing', 'too_many_pages', 'bool_page', 'early_short',
    'wrong_termination', 'row_mismatch', 'unknown_year', 'bool_count', 'missing_dates', 'reverse_dates',
    'uncanonical_date', 'outside_before', 'outside_after', 'contradict_year'))
def test_closed_coverage_and_count_date_contradictions_refuse(inputs, fault):
    supplied = census()
    if fault == 'extra': supplied['raw_row'] = 'forbidden'
    elif fault == 'missing': supplied.pop('terminated')
    elif fault == 'too_many_pages': supplied['page_rows'] = [10000] * 129
    elif fault == 'bool_page': supplied['page_rows'] = [True]
    elif fault == 'early_short': supplied['page_rows'] = [1, 6]
    elif fault == 'wrong_termination': supplied['terminated'] = False
    elif fault == 'row_mismatch': supplied['page_rows'] = [8]
    elif fault == 'unknown_year': supplied['in_window_year_counts']['2027'] = 0
    elif fault == 'bool_count': supplied['in_window_year_counts']['2020'] = True
    elif fault == 'missing_dates': supplied['earliest_date'] = None
    elif fault == 'reverse_dates': supplied['earliest_date'] = '2026-10-10'
    elif fault == 'uncanonical_date': supplied['earliest_date'] = '20200901'
    elif fault == 'outside_before': supplied['earliest_date'] = '2020-08-31'
    elif fault == 'outside_after': supplied['latest_date'] = '2026-10-10'
    else: supplied['earliest_date'] = '2025-01-01'
    with pytest.raises(m.HistoryDesignRefusal): m.coverage_summary(**inputs, census=supplied)


def test_missing_invalid_and_outside_rows_remain_visible(inputs):
    supplied = census(page_rows=[11], earliest_date='2020-08-31', latest_date='2026-10-10',
        before_window_rows=1, after_window_rows=1, invalid_date_rows=1, missing_date_rows=1)
    result = m.coverage_summary(**inputs, census=supplied)
    assert result['retained_rows'] == 11
    assert all(result[key] == 1 for key in ('before_window_rows', 'after_window_rows', 'invalid_date_rows', 'missing_date_rows'))
    assert result['complete_requested_history_proven'] is False


def test_pure_module_has_no_capture_controller_io_or_effect_import():
    tree = ast.parse(Path(m.__file__).read_text())
    imports = {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    imports |= {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert imports <= {'__future__', 'datetime', 'hashlib', 'json'}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {'open', 'exec', 'eval', 'main'} for node in ast.walk(tree))
