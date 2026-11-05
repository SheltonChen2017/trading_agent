"""One QC-only W5 necessary-demand observation over the retained native book.

The concrete reader authenticates current identities and the old immutable book;
no History call, object write, order or price export exists here.  Dense coverage
of the five necessary envelopes is not the strategy's actual holdings path.
"""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
import re
import time as clock

try:
    import newrule_native_price_book_runtime as reader
    import arv2_r327_available_history_period as period
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_native_price_book_runtime as reader
    from scripts import arv2_r327_available_history_period as period

SCHEMA = 'arv2-r329-W5-native-dated-coverage-v1'
STATISTIC = 'ARV2_W5_NATIVE_COVERAGE'
MAX_STATISTIC_BYTES, MAX_SECONDS = 8002, 600
MEMBERSHIP_STREAM_SHA256 = '6da39a900784aea5f0be81a9a329b28a1399d8dc5d95ec60b3951f55e31f40cd'
PERIOD_SHA256 = '88113155d49f74e00a89ba743aaa314d718cfd0d29b017ac501058460fe5d11a'
# These are already-public I observations, checked against fresh memberships.
# No date here is used to retire holdings or replace an unavailable price.
EXPECTED_DEMAND = (
    ('1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331', '2025-01-24', 90),
    ('b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8', '2025-02-14', 87),
    ('b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9', '2025-08-01', 63),
    ('c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7', '2025-02-14', 87),
    ('f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986', '2023-12-01', 150),
)
# Exact public calendar derivation for those five frozen I demand envelopes:
# (dense session count, dense session digest, eligible decision digest).
EXPECTED_GEOMETRY = (
    (432, 'b656433185ecbd14a9b49de24cda0200eb43769c76d373d353658eb4da56836b', '86ed3decb2ab7c5d6a99aae89f494d86a2585c438a3efe3e11aebf079f809b25'),
    (417, '4560ecf123f4c4b41059b0769d202e15bf6d1e83934770a0d5f95c6534f60ac1', 'daf514d8c49c0b504f2740711b601dd02040350f27c2bbc85f82503711e7352e'),
    (302, '39482e443afe824c08620c57bd48997d7e374b2075718ffd8318aa394021c5b1', 'f66d561b40b70a7272ae27b63ffb088a9b0d18225b2a6c9d40421f2a305378b2'),
    (417, '4560ecf123f4c4b41059b0769d202e15bf6d1e83934770a0d5f95c6534f60ac1', 'daf514d8c49c0b504f2740711b601dd02040350f27c2bbc85f82503711e7352e'),
    (718, '2bddfbb2bd6f6523cb8f84030e6eebf671da4ce7c38a02dabc4bab580b770199', '920a5400e5076b12ed99b7486f9921edbf2f159beabafbbc3bcb0910d8a35008'),
)
MISSING = ('absent', 'invalid_or_duplicate', 'failure_unknown')
GAP_REGIONS = ('missing_before_first_valid', 'missing_between_first_and_last_valid',
    'missing_after_last_valid', 'missing_without_any_valid')
FALSE_FLAGS = {
    'orders_submitted': False, 'History_called': False, 'ObjectStore_written': False,
    'raw_prices_exported': False, 'source_assignment_changed': False,
    'per_date_or_other_source_fallback': False, 'membership_end_retires_holdings': False,
    'actual_target_or_holdings_path_proven': False, 'vendor_coverage_proven': False,
    'complete_strategy_price_coverage_proven': False, 'terminal_payoff_proven': False,
    'processing_rights_granted': False, 'price_input_admitted': False,
    'historical_identity_proven': False, 'permanent_security_master_proven': False,
    'point_in_time_proven': False, 'formal_forward_ready': False,
    'strategy_result_accepted': False, 'paper_or_live_ready': False,
}
FINITE = frozenset(('project', 'profile', 'once', 'deadline', 'clock', 'orders', 'settings',
    'package', 'catalog', 'axis', 'memberships', 'demand', 'reader', 'source_changed',
    'price', 'summary', 'statistic_bound', 'unknown', *reader.FINITE))
PHASES = ('initial', 'source', 'authenticate', 'coverage', 'postcheck', 'complete')


class Refused(ValueError):
    """Closed predicate only; never a price, identity, path or raw exception."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is reader.Refused:
        code = reader.finite(error)
        return code if code in FINITE else 'unknown'
    if type(error) is reader.native.Refused:
        code = reader.native.finite(error)
        return code if code in FINITE else 'unknown'
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def profile_record(runtime_project_id):
    require(type(runtime_project_id) is int and 0 < runtime_project_id <= 2147483647, 'project')
    return {'schema': SCHEMA, 'runtime_project_id': runtime_project_id,
        'source_context_sha256': reader.SOURCE_CONTEXT_SHA256,
        'source_book_byte_count': reader.SOURCE_BOOK_BYTES, 'source_book_sha256': reader.SOURCE_BOOK_SHA256,
        'period_sha256': PERIOD_SHA256, 'membership_stream_sha256': MEMBERSHIP_STREAM_SHA256,
        'full_axis_sha256': period.FULL_AXIS_SHA256, 'binding_stream_sha256': period.BINDING_STREAM_SHA256,
        'evaluation_first': period.FIRST, 'evaluation_last': period.LAST,
        'first_reference_close': period.PRIOR, 'research_epoch_id': period.RESEARCH_EPOCH_ID,
        'expected_demand': [{'whole_binding_sha256': pin, 'first_prior': first,
            'eligible_decision_count': count, 'required_session_count': geometry[0],
            'required_sessions_sha256': geometry[1], 'eligible_decisions_sha256': geometry[2]}
            for (pin, first, count), geometry in zip(EXPECTED_DEMAND, EXPECTED_GEOMETRY, strict=True)],
        'dense_coverage': 'conservative_potential_envelope_not_actual_holdings_or_unconditional_launch_gate',
        'dense_period': 'first_potential_prior_through_evaluation_last_all_sessions_no_expiry_shortening',
        'gap_classification': 'missing_before_between_after_observed_valid_cells_or_no_valid_no_cause_inference',
        'potential_references': 'prior_close_for_every_membership_eligible_decision_not_actual_selected_target',
        'initial_state_requirement': 'future_W5_empty_holdings_open_orders_before_first_decision',
        'observation_clock': '2026Oct14_New_York_all_requested_closes_in_past',
        'source_reads': 'fresh_genuine_package_then_concrete_reader_fresh_package_and_one_exact_QC_book_read',
        'rights_and_access': 'external_current_paid_private_owner_scope_before_invocation',
        'maximum_seconds': MAX_SECONDS, 'maximum_statistic_bytes': MAX_STATISTIC_BYTES,
        'deadline_limitation': 'cooperative_checks_cannot_interrupt_engine_or_native_IO', **FALSE_FLAGS}


def _membership_rows(value):
    """Reconstruct exact immutable parser rows to bind the original full stream."""
    evaluator = reader.native.inputs.evaluator
    require(type(value) is tuple and 0 < len(value) <= evaluator.MAX_SECURITY_COUNT, 'memberships')
    rows = []
    for item in value:
        require(type(item) is evaluator.SecurityMembership and type(item.q_data) is Decimal
            and item.q_data.is_finite() and item.q_data == 1, 'memberships')
        row = evaluator.build_membership_record(security_id=item.security_id,
            first_session_index=item.first_session_index,
            last_session_index_exclusive=item.last_session_index_exclusive, sector_id=item.sector_id)
        require(row['row_sha256'] == item.row_sha256, 'memberships')
        rows.append(row)
    require(evaluator._stream_sha256(tuple(rows)) == MEMBERSHIP_STREAM_SHA256, 'memberships')
    require(evaluator._parse_memberships(tuple(rows), period.FULL_AXIS_COUNT) == value, 'memberships')
    return rows


def _genuine(package):
    inputs = reader.native.inputs
    require(type(package) is inputs.LoadedAcceptedRiskPreliminaryPackage
        and package.package_sha256 == reader.native.PACKAGE_SHA256
        and package.activation_manifest_sha256 == reader.native.ACTIVATION_SHA256
        and type(package.evaluator_input) is inputs.evaluator.PreliminaryRatingInput, 'package')
    bindings = package.runtime_symbol_bindings
    require(type(bindings) is tuple and len(bindings) == reader.native.EXPECTED_BINDINGS
        and inputs._stream_hash(bindings) == reader.native.BINDING_STREAM_SHA256, 'catalog')
    axis = package.evaluator_input.session_axis
    require(type(axis) is tuple, 'axis')
    view = period.make_period(axis)
    require(view['period_sha256'] == PERIOD_SHA256, 'axis')
    lineage = dict(package.evaluator_input.source_lineage_sha256s)
    require(lineage.get('security_master_admission_sha256') == reader.native.ADMISSION_SHA256, 'package')
    memberships = package.evaluator_input.memberships
    rows = _membership_rows(memberships)
    by_pin = {digest(row): row for row in bindings}
    ids = {row['security_id'] for row in bindings}
    require(len(by_pin) == len(bindings) == len(ids)
        and all(item.security_id in ids for item in memberships), 'catalog')
    fingerprint = digest({'package': package.package_sha256, 'activation': package.activation_manifest_sha256,
        'manifest': package.evaluator_input.manifest_sha256, 'axis': list(axis),
        'bindings': bindings, 'memberships': rows,
        'lineage': list(package.evaluator_input.source_lineage_sha256s)})
    return axis, view, by_pin, memberships, fingerprint


def _derive_demand(axis, view, by_pin, memberships):
    positions = {session: index for index, session in enumerate(axis)}
    intervals = defaultdict(list)
    for row in memberships:
        intervals[row.security_id].append(row)
    rows, dates, references = [], {}, {}
    require(tuple(pin for pin, _, _ in EXPECTED_DEMAND) == period.NATIVE_WHOLE_BINDING_SHA256S, 'demand')
    for ordinal, (pin, expected_first, expected_count) in enumerate(EXPECTED_DEMAND):
        require(pin in by_pin, 'catalog')
        eligible = [session for session in view['decision_sessions'] if any(
            interval.first_session_index <= positions[session] < interval.last_session_index_exclusive
            for interval in intervals[by_pin[pin]['security_id']])]
        require(len(eligible) == expected_count and eligible and positions[eligible[0]] > 0, 'demand')
        first = axis[positions[eligible[0]] - 1]
        require(first == expected_first, 'demand')
        selected = tuple(session for session in axis if first <= session <= period.LAST)
        require(selected and selected[0] == first and selected[-1] == period.LAST, 'demand')
        require((len(selected), digest(list(selected)), digest(eligible)) == EXPECTED_GEOMETRY[ordinal], 'demand')
        dates[pin] = selected
        references[pin] = tuple(axis[positions[session] - 1] for session in eligible)
        require(len(set(references[pin])) == len(eligible)
            and set(references[pin]) <= set(selected), 'demand')
        rows.append({'ordinal': ordinal, 'whole_binding_sha256': pin,
            'eligible_decision_count': len(eligible), 'eligible_decisions_sha256': digest(eligible),
            'required_session_count': len(selected), 'required_sessions_sha256': digest(list(selected))})
    return rows, dates, references


def _integer(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def validate_summary(value, *, expected_profile):
    require(type(expected_profile) is dict and type(expected_profile.get('runtime_project_id')) is int
        and expected_profile == profile_record(expected_profile['runtime_project_id']), 'profile')
    keys = {'schema', 'profile_sha256', 'runtime_project_id', 'attempt_consumed', 'terminal',
        'phase', 'failure_code', 'source_fingerprint_sha256', 'reader_receipt_sha256',
        'fresh_resolution_sha256', 'dense_envelopes_complete', 'required_cell_count',
        'valid_cell_count', 'missing_cell_count', 'per_selected', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and value['profile_sha256'] == digest(expected_profile)
        and type(value['runtime_project_id']) is int
        and value['runtime_project_id'] == expected_profile['runtime_project_id']
        and value['attempt_consumed'] is True and value['phase'] in PHASES
        and value['terminal'] in ('complete', 'refused')
        and all(value[key] is False for key in FALSE_FLAGS), 'summary')
    for key in ('source_fingerprint_sha256', 'reader_receipt_sha256', 'fresh_resolution_sha256'):
        require(value[key] is None or _hash(value[key]), 'summary')
    require(type(value['per_selected']) is list and len(value['per_selected']) in (0, 5), 'summary')
    rows = value['per_selected']
    row_keys = {'ordinal', 'whole_binding_sha256', 'eligible_decision_count', 'eligible_decisions_sha256',
        'required_session_count', 'required_sessions_sha256', 'valid_cell_count', *MISSING,
        *GAP_REGIONS, 'potential_reference_count', 'potential_reference_missing_count'}
    for index, row in enumerate(rows):
        require(type(row) is dict and set(row) == row_keys and type(row['ordinal']) is int
            and row['ordinal'] == index and row['whole_binding_sha256'] == EXPECTED_DEMAND[index][0]
            and type(row['eligible_decision_count']) is int
            and row['eligible_decision_count'] == EXPECTED_DEMAND[index][2]
            and type(row['required_session_count']) is int
            and (row['required_session_count'], row['required_sessions_sha256'], row['eligible_decisions_sha256'])
                == EXPECTED_GEOMETRY[index]
            and all(_integer(row[key], row['required_session_count']) for key in ('valid_cell_count', *MISSING))
            and sum(row[key] for key in ('valid_cell_count', *MISSING)) == row['required_session_count']
            and all(_integer(row[key], row['required_session_count']) for key in GAP_REGIONS)
            and sum(row[key] for key in GAP_REGIONS) == sum(row[key] for key in MISSING)
            and row['missing_without_any_valid'] == (row['required_session_count'] if row['valid_cell_count'] == 0 else 0)
            and type(row['potential_reference_count']) is int
            and row['potential_reference_count'] == row['eligible_decision_count']
            and _integer(row['potential_reference_missing_count'], row['potential_reference_count'])
            and row['potential_reference_missing_count'] <= sum(row[key] for key in MISSING)
            and row['potential_reference_count'] - row['potential_reference_missing_count'] <= row['valid_cell_count']
            and (row['valid_cell_count'] > 1 or row['missing_between_first_and_last_valid'] == 0), 'summary')
    for key in ('required_cell_count', 'valid_cell_count', 'missing_cell_count'):
        require(_integer(value[key], 6215), 'summary')
    require(value['required_cell_count'] == sum(row['required_session_count'] for row in rows)
        and value['valid_cell_count'] == sum(row['valid_cell_count'] for row in rows)
        and value['missing_cell_count'] == sum(sum(row[code] for code in MISSING) for row in rows)
        and type(value['dense_envelopes_complete']) is bool, 'summary')
    if value['terminal'] == 'complete':
        require(value['phase'] == 'complete' and value['failure_code'] is None and len(rows) == 5
            and all(_hash(value[key]) for key in ('source_fingerprint_sha256', 'reader_receipt_sha256', 'fresh_resolution_sha256'))
            and value['dense_envelopes_complete'] == (value['missing_cell_count'] == 0), 'summary')
    else:
        require(value['phase'] != 'complete' and type(value['failure_code']) is str
            and value['failure_code'] in FINITE and value['dense_envelopes_complete'] is False, 'summary')
    raw = canonical(value)
    require(0 < len(raw) <= MAX_STATISTIC_BYTES, 'statistic_bound')
    return json.loads(raw)


class AvailableHistoryNativeCoverage:
    """Concrete one-use no-order observation; no supplied price callback."""
    def __init__(self, algorithm, *, runtime_project_id, benchmark_symbol, etf_symbols,
                 trade_bar_type, daily_resolution, raw_normalization):
        self._profile = profile_record(runtime_project_id)
        self._algorithm = algorithm
        self._reader = reader.SpecificNativePriceBook(algorithm,
            frozen_source_context=reader.source_context(),
            expected_context_sha256=reader.SOURCE_CONTEXT_SHA256,
            frozen_runtime_project_id=runtime_project_id, benchmark_symbol=benchmark_symbol,
            etf_symbols=etf_symbols, trade_bar_type=trade_bar_type,
            daily_resolution=daily_resolution, raw_normalization=raw_normalization)
        self._started, self._deadline = False, None

    def __repr__(self):
        return '<AvailableHistoryNativeCoverage QC-only data redacted>'

    def __reduce_ex__(self, protocol):
        raise TypeError('QC-only observation cannot enter host serialization')

    def _remaining(self):
        require(type(self._deadline) in (int, float) and math.isfinite(self._deadline)
            and clock.monotonic() < self._deadline, 'deadline')

    def _guard(self):
        self._remaining()
        require(type(self._reader) is reader.SpecificNativePriceBook, 'reader')
        self._reader._base_guard()
        self._reader._identity._no_orders()
        require(next(iter(self._algorithm.transactions.get_open_orders()), None) is None, 'orders')
        require(reader.native._qc_ny(self._algorithm.time).date().isoformat() == '2026-10-14', 'clock')

    def assert_no_orders(self):
        """Ongoing callback guard, independent of the completed work deadline."""
        require(type(self._reader) is reader.SpecificNativePriceBook, 'reader')
        self._reader._base_guard()
        self._reader._identity._no_orders()
        require(next(iter(self._algorithm.transactions.get_open_orders()), None) is None, 'orders')

    def observe_once(self):
        require(not self._started, 'once')
        self._started = True
        self._deadline = clock.monotonic() + MAX_SECONDS
        value = {'schema': SCHEMA, 'profile_sha256': digest(self._profile),
            'runtime_project_id': self._profile['runtime_project_id'], 'attempt_consumed': True,
            'terminal': 'refused', 'phase': 'initial', 'failure_code': None,
            'source_fingerprint_sha256': None, 'reader_receipt_sha256': None,
            'fresh_resolution_sha256': None, 'dense_envelopes_complete': False,
            'required_cell_count': 0, 'valid_cell_count': 0, 'missing_cell_count': 0,
            'per_selected': [], **FALSE_FLAGS}
        try:
            self._guard(); value['phase'] = 'source'
            inputs = reader.native.inputs
            package = inputs.load_accepted_risk_preliminary_package(self._algorithm,
                activation_manifest_key=reader.ACTIVATION[0], activation_manifest_sha256=reader.ACTIVATION[1],
                activation_manifest_byte_count=reader.ACTIVATION[2])
            axis, view, by_pin, memberships, fingerprint = _genuine(package)
            rows, dates, references = _derive_demand(axis, view, by_pin, memberships)
            value['source_fingerprint_sha256'] = fingerprint
            self._guard(); value['phase'] = 'authenticate'
            receipt = self._reader.authenticate_once()
            require(type(receipt) is dict and receipt == self._reader.receipt()
                and receipt['runtime_project_id'] == self._profile['runtime_project_id']
                and receipt['source_context_sha256'] == reader.SOURCE_CONTEXT_SHA256
                and receipt['source_book_sha256'] == reader.SOURCE_BOOK_SHA256
                and receipt['fresh_input_binding_count'] == reader.native.EXPECTED_BINDINGS
                and receipt['fresh_selected_native_identity_checked_count'] == 5
                and receipt['fresh_duplicate_SID_count'] == receipt['fresh_own_ETF_collision_count'] == 0
                and receipt['fresh_own_ETF_count'] == 8
                and all(receipt[key] is False for key in reader.FALSE_FLAGS), 'reader')
            value['reader_receipt_sha256'] = digest(receipt)
            value['fresh_resolution_sha256'] = receipt['fresh_full_forward_reverse_resolution_sha256']
            self._guard(); value['phase'] = 'coverage'
            checked = []
            for row in rows:
                result = {**row, 'valid_cell_count': 0, **{code: 0 for code in MISSING}}
                pin = row['whole_binding_sha256']
                states = []
                for session in dates[pin]:
                    self._remaining()
                    try:
                        price = self._reader.price(by_pin[pin], session)
                        require(type(price) is Decimal and price.is_finite() and price > 0, 'price')
                        result['valid_cell_count'] += 1
                        states.append('valid')
                    except reader.Refused as error:
                        code = reader.finite(error)
                        require(code in MISSING, code if code in FINITE else 'unknown')
                        result[code] += 1
                        states.append(code)
                valid_indices = [index for index, state in enumerate(states) if state == 'valid']
                result.update({key: 0 for key in GAP_REGIONS})
                if not valid_indices:
                    result['missing_without_any_valid'] = len(states)
                else:
                    first, last = valid_indices[0], valid_indices[-1]
                    for index, state in enumerate(states):
                        if state != 'valid':
                            region = 'missing_before_first_valid' if index < first else (
                                'missing_after_last_valid' if index > last else 'missing_between_first_and_last_valid')
                            result[region] += 1
                indexed = dict(zip(dates[pin], states, strict=True))
                result['potential_reference_count'] = len(references[pin])
                result['potential_reference_missing_count'] = sum(
                    indexed[session] != 'valid' for session in references[pin])
                checked.append(result)
            value['per_selected'] = checked
            value['required_cell_count'] = sum(row['required_session_count'] for row in checked)
            value['valid_cell_count'] = sum(row['valid_cell_count'] for row in checked)
            value['missing_cell_count'] = sum(sum(row[code] for code in MISSING) for row in checked)
            value['phase'] = 'postcheck'; self._guard()
            require(_genuine(package)[-1] == fingerprint and self._reader.receipt() == receipt, 'source_changed')
            value['phase'] = value['terminal'] = 'complete'
            value['dense_envelopes_complete'] = value['missing_cell_count'] == 0
        except Exception as error:
            value['failure_code'] = finite(error)
        return validate_summary(value, expected_profile=self._profile)
