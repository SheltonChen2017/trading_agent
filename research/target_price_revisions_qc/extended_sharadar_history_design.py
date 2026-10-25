"""Pure prospective full-window ACTIONS query and coverage contract.

No file, credential, provider, capture controller or QC opener exists here.
Pinned public bytes establish the frozen requested dates, not data availability
or authority. Pagination termination and year counts cannot attest complete
history. Current TICKERS remains a snapshot, not historical identity evidence.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json

STUDY = 'TPR-CAP-TILT-EXT26-20261010-v1'
PINS = {'repair': '0d0f67a6d02915ff7357018ef51108fdeb3e334cbcccc7e2fa65bbeb1f1d6097',
    'study': '90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067',
    'calendar': '3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d'}
START, END = '2020-09-01', '2026-10-09'
MAX_PAGES, PAGE_ROWS = 128, 10000
YEARS = tuple(str(year) for year in range(2020, 2027))
_CENSUS_KEYS = frozenset(('page_rows terminated earliest_date latest_date in_window_year_counts '
    'before_window_rows after_window_rows invalid_date_rows missing_date_rows').split())


class HistoryDesignRefusal(ValueError):
    """Body-free contract refusal, never source rows or provider errors."""


def _fail():
    raise HistoryDesignRefusal('prospective Sharadar history design refused')


def _closed(value, keys):
    if type(value) is not dict or set(value) != keys: _fail()


def _count(value, maximum=MAX_PAGES * PAGE_ROWS):
    if type(value) is not int or not 0 <= value <= maximum: _fail()
    return value


def _day(value):
    try:
        if type(value) is not str or len(value) != 10: _fail()
        result = date.fromisoformat(value)
        if result.isoformat() != value: _fail()
        return result
    except (TypeError, ValueError): _fail()


def _public(raw, name):
    if (type(raw) is not bytes or not 0 < len(raw) <= 65536
            or hashlib.sha256(raw).hexdigest() != PINS[name]): _fail()
    try:
        body = json.loads(raw)
        if type(body) is not dict: _fail()
        return body
    except (TypeError, ValueError, UnicodeError, RecursionError): _fail()


def _bind(repair_freeze_raw, study_freeze_raw, calendar_raw):
    repair = _public(repair_freeze_raw, 'repair')
    study = _public(study_freeze_raw, 'study')
    calendar = _public(calendar_raw, 'calendar')
    if (repair.get('study_id') != STUDY or study.get('study_id') != STUDY
            or calendar.get('study_id') != STUDY
            or study.get('dates', {}).get('signal_warmup_start') != START
            or study['dates'].get('end') != END or calendar.get('warmup_start') != START
            or calendar.get('end') != END or calendar.get('decision_count') != 301
            or calendar.get('valuation_count') != 1449): _fail()
    # This deliberately identifies the old no-lower-bound request; it neither
    # edits that executed producer nor treats missing from= as new authority.
    actions = repair.get('sharadar', {}).get('datasets', {}).get('actions', {})
    if actions.get('lower_date_bound') is not None or actions.get('to') != END: _fail()


def build_design(*, repair_freeze_raw, study_freeze_raw, calendar_raw):
    """Return fresh descriptive metadata only, without an operation or permit."""
    _bind(repair_freeze_raw, study_freeze_raw, calendar_raw)
    return {'schema': 'tpr-ext26-sharadar-full-window-design-v1', 'study_id': STUDY,
        'public_source_sha256': dict(PINS), 'provider': 'sharadar', 'method': 'GET',
        'host': 'api.sharadar.com', 'endpoint': '/v1.0/data/actions',
        'requested_from': START, 'requested_to': END, 'max_pages': MAX_PAGES,
        'page_rows': PAGE_ROWS, 'fresh_identified_capture_required': True,
        'fresh_source_custody_and_access_scope_required': True,
        'historical_entitlement_verified': False, 'requested_date_coverage_proven': False,
        'current_tickers_is_historical_identity_series': False,
        'identity_comparison_still_required': True, 'old_capture_modified': False,
        'inputs_rebuilt': False, 'active_operation': None, 'active_permit': None,
        'provider_access_authorized': False, 'qc_access_authorized': False,
        'off_native_recovery_blocked_by_this_design': False, 'on_admission': False,
        'canonical_admission': False, 'attempt_reset': False, 'new_looks': 0,
        'quantconnect_attempts': 0}


def query_for_page(*, repair_freeze_raw, study_freeze_raw, calendar_raw, page):
    """Exact prospective query; caller cannot change dates, fields or limits."""
    _bind(repair_freeze_raw, study_freeze_raw, calendar_raw)
    if type(page) is not int or not 0 <= page < MAX_PAGES: _fail()
    return {'from': START, 'to': END, 'sort': 'date.asc', 'fields': 'ticker,date,action,contraticker',
        'format': 'csv', 'limit': str(PAGE_ROWS), 'skip': str(page * PAGE_ROWS)}


def coverage_summary(*, repair_freeze_raw, study_freeze_raw, calendar_raw, census):
    """Assess supplied retained-date counts, never authenticate provider truth.

    An empty terminated response proves no historical window. Nonempty rows in
    every requested year establish only those observations, not omitted-event
    completeness, original availability, entitlement or source admission.
    """
    _bind(repair_freeze_raw, study_freeze_raw, calendar_raw)
    _closed(census, _CENSUS_KEYS)
    pages = census['page_rows']
    if (type(pages) is not list or not 1 <= len(pages) <= MAX_PAGES
            or type(census['terminated']) is not bool): _fail()
    for count in pages: _count(count, PAGE_ROWS)
    if any(count != PAGE_ROWS for count in pages[:-1]): _fail()
    if census['terminated'] != (pages[-1] < PAGE_ROWS): _fail()
    years = census['in_window_year_counts']; _closed(years, frozenset(YEARS))
    for count in years.values(): _count(count)
    counts = {key: _count(census[key]) for key in ('before_window_rows', 'after_window_rows',
        'invalid_date_rows', 'missing_date_rows')}
    total = sum(pages)
    if sum(years.values()) + sum(counts.values()) != total: _fail()
    valid = total - counts['invalid_date_rows'] - counts['missing_date_rows']
    first, last = census['earliest_date'], census['latest_date']
    if not valid:
        if first is not None or last is not None: _fail()
    else:
        first_day, last_day = _day(first), _day(last)
        if (first_day > last_day
                or (first < START) != bool(counts['before_window_rows'])
                or (last > END) != bool(counts['after_window_rows'])): _fail()
        for year in YEARS:
            if years[year] and not first[:4] <= year <= last[:4]: _fail()
    observed = [year for year in YEARS if years[year]]
    return {'schema': 'tpr-ext26-sharadar-coverage-observation-v1', 'study_id': STUDY,
        'requested_from': START, 'requested_to': END, 'page_count': len(pages), 'retained_rows': total,
        'pagination_terminated': census['terminated'], 'earliest_retained_date': first,
        'latest_retained_date': last, 'in_window_year_counts': dict(years),
        'observed_requested_years': observed, 'missing_requested_years': [year for year in YEARS if year not in observed],
        'observations_in_every_requested_year': len(observed) == len(YEARS), **counts,
        'complete_requested_history_proven': False, 'provider_authenticity_verified': False,
        'historical_entitlement_verified': False, 'point_in_time_verified': False,
        'current_tickers_is_historical_identity_series': False, 'fresh_capture_scope_still_required': True,
        'on_admission': False, 'canonical_admission': False, 'attempt_reset': False,
        'provider_reads': 0, 'outcome_reads': 0, 'new_looks': 0, 'quantconnect_attempts': 0}
