"""Fresh membership-based potential price demand; never portfolio eligibility.

ETF callbacks, caps and actual selections are unavailable here. Membership at
a frozen decision is only a necessary-condition potential stock exposure,
conservatively shared by both cohorts and every AR arm. An eligible stock's
price window never ends at its binding/membership end without payoff evidence.
The caller owns the new one-use protocol and source/IPC authentication.
"""
from __future__ import annotations

from collections import defaultdict
import json

from scripts import arv2_r298_all_route_worker_v2 as loader
from research.analyst_revisions_v2_qc import newrule_comparison_qc_runtime as runtime


SCHEMA = 'arv2-r298-membership-price-demand-v1'
PRIVATE_SCHEMA = SCHEMA + '-private'
SELECTED_ROLES = ('evaluator_manifest', 'session_axis', 'memberships', 'runtime_symbol_bindings')
EXPECTED_BINDINGS, EXPECTED_FUNDS = 6151, 8
MAX_PRIVATE_BYTES, MAX_SUMMARY_BYTES = 16 * 1024 * 1024, 128 * 1024
RUNTIME_SHA256 = '674415b3179836a613afc6f7bdea23a966db21ab67221472fc5d87b4a742049d'
TARGETS_SHA256 = '30ed05cbc02bb0076d09c82467a32ad840ead87561f3e2a1ae1cc5a9ee65f29d'
LOADER_SHA256 = 'd236e3f0113046ca638296823d880ac8a93e8d31e65047b57c26fcba5dc35da1'
identity, transport, evaluator = loader.previous.identity, loader.previous.transport, loader.previous.identity.evaluator
canonical, sha, remaining = loader.canonical, loader.sha, loader.remaining
FALSE_FLAGS = {'provider_contact': False, 'credential_access': False, 'qc_contact': False,
    'price_dispatch': False, 'actual_ETF_constituent_eligibility_proven': False,
    'caps_scores_or_prices_used_for_preselection': False, 'actual_strategy_selection_proven': False,
    'initial_QC_holdings_observed': False, 'zero_holding_terminal_payoff_proven': False,
    'membership_end_is_price_end': False, 'binding_end_is_price_end': False,
    'price_coverage_proven': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('deadline', 'route_evidence', 'input', 'stream_inventory', 'stream_bound',
    'membership_stream', 'membership_rows', 'membership_identity', 'decision_axis', 'catalog_binding',
    'plain_changed', 'private_bound', 'summary', 'unknown')) | loader.FINITE


class Refused(ValueError):
    """Closed predicate, never identifiers, source rows or exception values."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _failure_code(error):
    if type(error) is Refused:
        return finite(error)
    if type(error) is evaluator.PreliminaryRatingEvaluationError:
        return 'membership_rows'
    if type(error) is runtime.targets.NewruleError:
        return 'decision_axis'
    return loader._failure_code(error)


def profile_record():
    return {'schema': SCHEMA, 'private_schema': PRIVATE_SCHEMA,
        'source_package_sha256': loader.previous.PACKAGE_SHA256,
        'source_lineage_sha256': loader.previous.LINEAGE_SHA256,
        'genuine_loader_sha256': LOADER_SHA256, 'runtime_sha256': RUNTIME_SHA256,
        'targets_sha256': TARGETS_SHA256, 'binding_count': EXPECTED_BINDINGS,
        'fund_count': EXPECTED_FUNDS, 'selected_roles': list(SELECTED_ROLES),
        'start_session': runtime.START_SESSION, 'decision_cutoff': runtime.DECISION_CUTOFF,
        'valuation_end': runtime.END_SESSION, 'universe_counts': [6, 8], 'AR_percent_arms': [0, 100, 200],
        'decision_rule': 'unchanged_runtime_weekly_axis_first_actual_session_of_each_ISO_week',
        'membership_rule': 'genuine_evaluator_inclusive_first_exclusive_last_at_each_frozen_decision',
        'ETF_membership': 'not_in_package_not_inferred_from_sector_or_names',
        'potential_stock_sets': 'identical_conservative_membership_necessary_condition_for_all_six_cells',
        'stock_price_window': 'immediately_prior_first_potential_decision_through_END_no_binding_end_clip',
        'never_potential_condition': 'complete_authenticated_membership_absence_at_ALL_decisions_and_frozen_zero_initial_stock_runtime',
        'zero_initial_runtime_gate': 'frozen_initialize_requires_empty_current_holding_census_before_callbacks',
        'fund_price_window': 'immediately_prior_START_through_END',
        'all_bindings_and_original_route_refusals_retained': True,
        'maximum_private_bytes': MAX_PRIVATE_BYTES, 'maximum_summary_bytes': MAX_SUMMARY_BYTES,
        'root_caller_must_pin_empty_initial_runtime_source_and_own_new_protocol': True,
        'membership_not_actual_portfolio_or_source_admission': True, **FALSE_FLAGS}


def _streams(plain, record, deadline):
    selected = {role: [] for role in SELECTED_ROLES}
    positions = {role: [] for role in transport.ROLES}
    order, activation_seen = [], False
    for descriptor, raw in transport.iter_plain_upload_objects(plain):
        remaining(deadline)
        require(type(raw) is bytes and descriptor.byte_count == len(raw)
            and descriptor.content_sha256 == sha(raw), 'stream_inventory')
        if descriptor.activation_manifest:
            require(not activation_seen and descriptor.role == 'activation_manifest', 'stream_inventory')
            activation_seen = True
            continue
        require(not activation_seen and descriptor.role in positions and type(descriptor.ordinal) is int
            and descriptor.ordinal == len(positions[descriptor.role])
            and type(descriptor.record_count) is int and descriptor.record_count > 0, 'stream_inventory')
        positions[descriptor.role].append(descriptor.ordinal); order.append(descriptor.role)
        if descriptor.role not in selected:
            continue
        maximum = (identity.MAX_MANIFEST_BYTES if descriptor.role == 'evaluator_manifest'
            else transport.MAX_ROW_SHARD_BYTES)
        require(0 < len(raw) <= maximum, 'stream_bound')
        if descriptor.role == 'evaluator_manifest':
            require(descriptor.ordinal == 0 and descriptor.record_count == 1, 'stream_inventory')
            rows = [identity._json(raw, identity.MAX_MANIFEST_BYTES)]
        else:
            bound = (evaluator.MAX_SESSION_COUNT if descriptor.role == 'session_axis'
                else evaluator.MAX_SECURITY_COUNT if descriptor.role == 'memberships' else identity.MAX_BINDINGS)
            require(len(selected[descriptor.role]) + descriptor.record_count <= bound, 'stream_bound')
            lines = raw.splitlines(keepends=True)
            require(len(lines) == descriptor.record_count, 'stream_inventory')
            rows = []
            for line in lines:
                remaining(deadline)
                rows.append(identity._json(line, identity.MAX_ROW_BYTES))
        selected[descriptor.role].extend(rows)
    require(activation_seen and positions['evaluator_manifest'] == [0]
        and all(values for values in positions.values())
        and order == [role for role in transport.ROLES for _ in positions[role]], 'stream_inventory')
    return selected


def _authenticated(plain, deadline):
    initial, record, old_selected, catalog, input_binding = loader._catalog(plain, deadline)
    selected = _streams(plain, record, deadline)
    require(all(canonical(selected[role]) == canonical(old_selected[role])
        for role in old_selected), 'plain_changed')
    manifest = selected['evaluator_manifest'][0]
    rows = tuple(selected['memberships'])
    axis = evaluator._parse_sessions(tuple(selected['session_axis']))
    require(axis == loader.previous.october._sessions()
        and type(manifest['membership_row_count']) is int and manifest['membership_row_count'] == len(rows)
        and evaluator._stream_sha256(rows) == manifest['membership_rows_sha256'], 'membership_stream')
    memberships = evaluator._parse_memberships(rows, len(axis))
    ids = {row['security_id'] for row in catalog}
    require(len(catalog) == EXPECTED_BINDINGS and len(ids) == EXPECTED_BINDINGS
        and all(row.security_id in ids for row in memberships), 'membership_identity')
    return initial, record, selected, catalog, input_binding, axis, memberships


def _decisions(axis):
    decisions = runtime.weekly_axis(axis)
    require(runtime.START_SESSION in axis and runtime.END_SESSION in axis
        and axis.index(runtime.START_SESSION) > 0 and axis[-1] == runtime.END_SESSION, 'decision_axis')
    positions = {session: index for index, session in enumerate(axis)}
    require(all(positions[session] > 0 for session in decisions), 'decision_axis')
    return decisions, positions


def _derive(axis, memberships, stocks, funds, deadline):
    decisions, positions = _decisions(axis)
    intervals = defaultdict(list)
    for row in memberships:
        require(type(row) is evaluator.SecurityMembership, 'membership_rows')
        intervals[row.security_id].append(row)
    stock_rows, groups, reasons = [], {}, {}
    for item in stocks:
        remaining(deadline)
        binding = item['binding']; security = binding['security_id']
        values = intervals.get(security, ())
        eligible = tuple(session for session in decisions if any(
            row.first_session_index <= positions[session] < row.last_session_index_exclusive for row in values))
        potential = bool(eligible)
        first, last = (eligible[0], eligible[-1]) if eligible else (None, None)
        prior = axis[positions[first] - 1] if potential else None
        row = {'binding_ordinal': item['binding_ordinal'], 'security_id': security,
            'binding_row_sha256': binding['row_sha256'], 'route_disposition': item['disposition'],
            'route_reason': item['reason'], 'membership_interval_count': len(values),
            'membership_rows_sha256': sha(canonical([value.row_sha256 for value in values])),
            'potential_for_both_cohorts_all_AR_arms': potential, 'eligible_decision_count': len(eligible),
            'eligible_decisions_sha256': sha(canonical(list(eligible))),
            'first_eligible_decision': first, 'last_eligible_decision': last,
            'required_price_start': prior, 'required_price_end': runtime.END_SESSION if potential else None,
            'binding_last_session_not_used_as_price_end': True,
            'zero_initial_runtime_condition_required_for_never_potential': not potential}
        stock_rows.append(row)
        group = groups.setdefault(item['disposition'], {'potential': 0, 'never_potential': 0, 'total': 0})
        group['potential' if potential else 'never_potential'] += 1; group['total'] += 1
        if item['disposition'] == 'refused':
            reason = reasons.setdefault(item['reason'], {'potential': 0, 'never_potential': 0, 'total': 0})
            reason['potential' if potential else 'never_potential'] += 1; reason['total'] += 1
    first_prior = axis[positions[runtime.START_SESSION] - 1]
    fund_rows = [{'fund_ordinal': item['fund_ordinal'], 'ticker': item['ticker'],
        'route_disposition': item['disposition'], 'route_reason': item['reason'],
        'six_universe': item['fund_ordinal'] < 6, 'eight_universe': True,
        'required_price_start': first_prior, 'required_price_end': runtime.END_SESSION} for item in funds]
    potential_rows = [row for row in stock_rows if row['potential_for_both_cohorts_all_AR_arms']]
    aggregate = {'potential_stock_count': len(potential_rows),
        'never_potential_stock_count': len(stock_rows) - len(potential_rows),
        'disposition_relevance': dict(sorted(groups.items())), 'refusal_reason_relevance': dict(sorted(reasons.items())),
        'stock_required_first_min': min((row['required_price_start'] for row in potential_rows), default=None),
        'stock_required_first_max': max((row['required_price_start'] for row in potential_rows), default=None),
        'stock_required_last': runtime.END_SESSION if potential_rows else None,
        'own_etf_price_first': first_prior, 'own_etf_price_last': runtime.END_SESSION}
    return stock_rows, fund_rows, aggregate, decisions


def _prepare_bound(plain, route_private_record, evidence_summary, deadline):
    from scripts import arv2_r298_route_disposition_evidence as evidence
    try:
        checked_evidence = evidence.validate_summary(evidence_summary)
        route = evidence.validate_private_record(route_private_record, expected_summary=checked_evidence)
    except Exception:
        raise Refused('route_evidence') from None
    require(type(route) is dict and type(route['stocks']) is list and len(route['stocks']) == EXPECTED_BINDINGS
        and type(route['funds']) is list and len(route['funds']) == EXPECTED_FUNDS, 'route_evidence')
    route_pin = sha(canonical(route)); evidence_pin = sha(canonical(checked_evidence))
    initial, record, selected, catalog, input_binding, axis, memberships = _authenticated(plain, deadline)
    require([item['binding'] for item in route['stocks']] == catalog
        and route['binding_contract'] == input_binding['binding_contract']
        and [item['binding_ordinal'] for item in route['stocks']] == list(range(EXPECTED_BINDINGS))
        and [item['fund_ordinal'] for item in route['funds']] == list(range(EXPECTED_FUNDS))
        and tuple(item['ticker'] for item in route['funds']) == runtime.targets.UNIVERSES, 'catalog_binding')
    stocks, funds, aggregate, decisions = _derive(axis, memberships, route['stocks'], route['funds'], deadline)
    private = {'schema': PRIVATE_SCHEMA, 'source_frame_pin': dict(route['frame_pin']),
        'evidence_summary_sha256': evidence_pin, 'binding_contract': dict(route['binding_contract']),
        'stocks': stocks, 'funds': funds}
    private_raw = canonical(private)
    require(0 < len(private_raw) <= MAX_PRIVATE_BYTES, 'private_bound')
    remaining(deadline)
    loader.previous.transport.require_plain_transport(plain)
    require(loader.previous.transport._fingerprint(plain) == initial and plain.to_record() == record
        and canonical(_streams(plain, record, deadline)) == canonical(selected), 'plain_changed')
    require(sha(canonical(route)) == route_pin and sha(canonical(checked_evidence)) == evidence_pin, 'route_evidence')
    stream = selected['memberships']
    summary = {'schema': SCHEMA, 'source_frame_pin': dict(route['frame_pin']),
        'evidence_summary_sha256': evidence_pin, 'route_evidence_private_sha256': route_pin,
        'input_binding': input_binding, 'membership_row_count': len(stream),
        'membership_rows_sha256': evaluator._stream_sha256(tuple(stream)),
        'selected_four_streams_sha256': sha(canonical(selected)),
        'decision_count': len(decisions), 'decision_sessions_sha256': sha(canonical(list(decisions))),
        'first_decision': decisions[0], 'last_decision': decisions[-1],
        'cohorts': {str(count): {**aggregate, 'universe_count': count, 'own_etf_count': count,
            'cohort_definition_sha256': runtime.targets.digest(list(runtime.targets.cohort(count)))} for count in (6, 8)},
        'all_AR_arms_same_potential_stocks': True,
        'private_frame_byte_count': len(private_raw), 'private_frame_sha256': sha(private_raw), **FALSE_FLAGS}
    return validate_summary(summary), private


def prepare(route_private_record, *, evidence_summary, deadline):
    try:
        remaining(deadline)
        return _prepare_bound(loader._load_plain(deadline), route_private_record, evidence_summary, deadline)
    except Exception as error:
        raise Refused(_failure_code(error)) from None


def _hash(value):
    return loader.previous._hash(value)


def validate_summary(value):
    try:
        keys = {'schema', 'source_frame_pin', 'evidence_summary_sha256', 'route_evidence_private_sha256',
            'input_binding', 'membership_row_count', 'membership_rows_sha256', 'selected_four_streams_sha256',
            'decision_count', 'decision_sessions_sha256', 'first_decision', 'last_decision', 'cohorts',
            'all_AR_arms_same_potential_stocks', 'private_frame_byte_count', 'private_frame_sha256', *FALSE_FLAGS}
        require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
            and all(value[key] is False for key in FALSE_FLAGS)
            and value['all_AR_arms_same_potential_stocks'] is True, 'summary')
        raw = canonical(value); require(len(raw) <= MAX_SUMMARY_BYTES, 'summary')
        checked = json.loads(raw)
        loader.previous._validate_input(checked['input_binding'])
        frame = checked['source_frame_pin']
        require(type(frame) is dict and set(frame) == {'byte_count', 'sha256'}
            and type(frame['byte_count']) is int and 0 < frame['byte_count'] <= 128 * 1024 * 1024
            and _hash(frame['sha256']), 'summary')
        for key in ('evidence_summary_sha256', 'route_evidence_private_sha256', 'membership_rows_sha256',
                'selected_four_streams_sha256', 'decision_sessions_sha256', 'private_frame_sha256'):
            require(_hash(checked[key]), 'summary')
        require(type(checked['membership_row_count']) is int
            and 0 < checked['membership_row_count'] <= evaluator.MAX_SECURITY_COUNT
            and type(checked['private_frame_byte_count']) is int
            and 0 < checked['private_frame_byte_count'] <= MAX_PRIVATE_BYTES, 'summary')
        axis = loader.previous.october._sessions(); decisions, positions = _decisions(axis)
        require(type(checked['decision_count']) is int and checked['decision_count'] == len(decisions)
            and checked['decision_sessions_sha256'] == sha(canonical(list(decisions)))
            and checked['first_decision'] == decisions[0] and checked['last_decision'] == decisions[-1], 'summary')
        require(type(checked['cohorts']) is dict and set(checked['cohorts']) == {'6', '8'}, 'summary')
        common = None
        for count in (6, 8):
            group = checked['cohorts'][str(count)]
            fixed = {'potential_stock_count', 'never_potential_stock_count', 'disposition_relevance',
                'refusal_reason_relevance', 'stock_required_first_min', 'stock_required_first_max',
                'stock_required_last', 'own_etf_price_first', 'own_etf_price_last', 'universe_count',
                'own_etf_count', 'cohort_definition_sha256'}
            require(type(group) is dict and set(group) == fixed
                and type(group['universe_count']) is int and group['universe_count'] == count
                and type(group['own_etf_count']) is int and group['own_etf_count'] == count
                and group['cohort_definition_sha256'] == runtime.targets.digest(list(runtime.targets.cohort(count)))
                and all(type(group[key]) is int and 0 <= group[key] <= EXPECTED_BINDINGS
                    for key in ('potential_stock_count', 'never_potential_stock_count'))
                and group['potential_stock_count'] + group['never_potential_stock_count'] == EXPECTED_BINDINGS
                and group['own_etf_price_first'] == axis[positions[runtime.START_SESSION] - 1]
                and group['own_etf_price_last'] == runtime.END_SESSION, 'summary')
            bins, reasons = group['disposition_relevance'], group['refusal_reason_relevance']
            require(type(bins) is dict and set(bins) <= {'routed', 'refused', 'outside_window'}
                and bool(bins) and type(reasons) is dict
                and set(reasons) <= loader.routes.REASONS, 'summary')
            for item in (*bins.values(), *reasons.values()):
                require(type(item) is dict and set(item) == {'potential', 'never_potential', 'total'}
                    and all(type(number) is int and 0 <= number <= EXPECTED_BINDINGS for number in item.values())
                    and item['potential'] + item['never_potential'] == item['total'], 'summary')
            require(sum(item['total'] for item in bins.values()) == EXPECTED_BINDINGS
                and sum(item['potential'] for item in bins.values()) == group['potential_stock_count']
                and sum(item['never_potential'] for item in bins.values()) == group['never_potential_stock_count']
                and all(sum(item[key] for item in reasons.values()) == bins.get('refused', {}).get(key, 0)
                    for key in ('potential', 'never_potential', 'total')), 'summary')
            if group['potential_stock_count']:
                prior = {axis[positions[session] - 1] for session in decisions}
                require(group['stock_required_first_min'] in prior and group['stock_required_first_max'] in prior
                    and group['stock_required_first_min'] <= group['stock_required_first_max']
                    and group['stock_required_last'] == runtime.END_SESSION, 'summary')
            else:
                require(all(group[key] is None for key in ('stock_required_first_min',
                    'stock_required_first_max', 'stock_required_last')), 'summary')
            comparable = {key: item for key, item in group.items() if key not in
                ('universe_count', 'own_etf_count', 'cohort_definition_sha256')}
            require(common is None or common == comparable, 'summary'); common = comparable
        return checked
    except Exception as error:
        raise Refused(_failure_code(error)) from None
