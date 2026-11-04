"""Pure R337 quarantine profile/result contract; no QC or provider operations.

All original books and baseline construction/caps/AR tilts remain intact until
exact five final sleeve weights transfer to their own ETFs. This new empty
USD1m epoch has explicit previously frozen quote execution and W5 cash bounds,
with vendor-only RAW reference/NAV marks. It never initializes the unavailable
native-five price book. No source/PIT/identity/readiness or run authority follows
from construction, pure validation, hashes or a terminal status.
"""
import hashlib
import json
import re
from datetime import datetime, time, timezone
from decimal import Decimal, ROUND_FLOOR, localcontext
from types import MappingProxyType

try:
    import newrule_available_history_comparison_runtime as base
    import newrule_five_case_quarantine_common_price as monetary
    import newrule_five_case_quarantine_vendor_book as vendor_reader
    import newrule_five_case_quarantine_targets as quarantine
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_available_history_comparison_runtime as base
    from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_common_price as monetary
    from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_vendor_book as vendor_reader
    from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_targets as quarantine

targets, legacy, forced = quarantine, base.legacy, base.forced
core, inputs, figi, preopen = base.core, base.inputs, base.figi, base.preopen
number, instant = base.number, base.instant
FEE_RATE = base.FEE_RATE
RESEARCH_EPOCH_ID = quarantine.RESEARCH_EPOCH_ID
STRATEGY_SCHEMA = "arv2-r337-five-case-quarantine-strategy-v1"
STARTING_CASH, START_SESSION, END_SESSION = base.STARTING_CASH, base.START_SESSION, base.END_SESSION
MAX_ORDERS, MAX_ROWS = base.MAX_ORDERS, base.MAX_ROWS
weekly_axis, account_aggregates = base.weekly_axis, base.account_aggregates
LINEAGE_SHA256 = 'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'
EXPECTED_EVALUATION_SESSION_COUNT = 1242
EVALUATION_SESSIONS_SHA256 = 'eff4b9f8552317b16b97fbc1734aca1b27baea25d718721ddf0831e2ae85ef7e'
EXPECTED_DECISION_SESSION_COUNT = 259
DECISION_SESSIONS_SHA256 = '9f0bd75e1de17112bd3a571438311cd152ba3ee5ce7279e710b133553cbd1429'
SCHEMA = 'arv2-r337-five-case-quarantine-profile-v1'
RESULT_SCHEMA = 'arv2-r337-five-case-quarantine-result-v1'
MONTH_SCHEMA = 'arv2-r337-five-case-quarantine-monthly-return-v1'
META_STATISTIC, MONTHLY_STATISTIC = 'ARV2_QUARANTINE_META', 'ARV2_QUARANTINE_MONTHLY'
MAX_STATISTIC_BYTES = 16384
MAX_VENDOR_COMPLETED_LOOKUPS = 300000
QUOTE_ANCESTOR_SHA256 = 'c7b829020ac20704ec6f813997ebef396ed2069b8ad60c77bf3dc84cd67e2814'
FALSE_FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False,
    'source_admission_granted': False, 'strategy_result_accepted': False}
PROFILE_KEYS = frozenset(('schema', 'candidate_id', 'profile_sha256', 'strategy_profile',
    'strategy_profile_sha256', 'package_sha256', 'lineage_sha256', 'universe_count',
    'ar_percent', 'runtime_project_id', 'vendor_source_context_sha256', 'monetary_policy_sha256',
    'quarantine_catalog_sha256', 'quarantine_policy_sha256', 'source_pins',
    'reference_and_NAV_source_policy', 'automatic_security_price_seeding',
    'research_epoch_id', 'first_reference_close', *FALSE_FLAGS))
COMMON_RESULT_KEYS = frozenset(('schema', 'common_profile_sha256', 'strategy_profile_sha256',
    'vendor_source_context_sha256', 'monetary_policy_sha256', 'quarantine_catalog_sha256',
    'quarantine_policy_sha256', 'research_epoch_id', 'fresh_resolution_sha256',
    'fund_translation_sha256', 'ledger'))
FINITE = frozenset(('profile', 'source_pins', 'base_not_quote_aware', 'context', 'project',
    'once', 'not_ready', 'resolution', 'identity', 'fund_translation', 'catalog', 'reference',
    'close_clock', 'close_state', 'quarantine', 'quarantine_ledger', 'terminal', 'source_counters', 'result_common',
    'incomplete_terminal_geometry', 'terminal_clock', 'terminal_order_or_history_census', 'statistic_bound',
    'result_expected_profile', 'result_statistics', 'result_duplicate_key',
    'result_payload_bound', 'result_canonical', 'result_json', 'result_count', 'result_decimal',
    'result_meta_fields', 'result_schema', 'result_identity', 'result_safety_flags',
    'result_profile_geometry', 'result_fallback_inventory', 'result_forced_fields',
    'result_forced_flags', 'result_forced_census', 'result_monthly_fields',
    'result_monthly_identity', 'result_monthly_geometry', 'result_month_endpoint',
    'result_return', 'result_rounding', 'result_nav_rounding_resolution',
    'result_return_nav_mismatch', 'result_aggregate_fields', 'result_aggregate_binding',
    'result_aggregate_decimal', 'result_aggregate_rounding', 'result_aggregate_range',
    'result_total_return', 'result_cagr', 'result_fee_reconciliation', 'unknown'))


class Refused(ValueError):
    """Finite protocol stop; never prices, identifiers, keys or raw errors."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _sha(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _pin_map(value):
    require(type(value) is dict and 1 <= len(value) <= 256 and all(
        type(name) is str and re.fullmatch('[A-Za-z0-9_]+\\.py', name) is not None
        and _sha(pin) for name, pin in value.items()), 'source_pins')
    return dict(sorted(value.items()))


def quote_policy_fields():
    # The exact previously frozen side-aware execution plus W5 engine-cash bound.
    return {'execution_policy': 'arv2-newrule-quote-aware-execution-v1',
        'execution_quote': 'own_current_Slice_QuoteBar_and_typed_cache;bid_sell_ask_buy;no_stale_or_one_sided_fallback',
        'quote_readiness': 'same_SID;Time0930_EndTime0931_exact60s;non_fill_forward;positive_bid_le_ask;typed_cache_and_security_sides_equal',
        'strategy_fee_basis': '10bps_times_absolute_quantity_times_frozen_intent_side_quote;exact_order_symbol_tag_signed_quantity_binding',
        'outside_intent_fee_basis': 'unchanged_security_price_for_engine_forced_delisting_orders;separately_accounted',
        'buy_cash_bound': 'floor_current_cash_divided_by_max_of_ask_and_engine_security_price_times_1point001;prior_RAW_close_target_quantities_unchanged',
        'fill_price_binding': 'actual_engine_market_fill_equals_frozen_side_quote_absolute_USD_tolerance_0.0000001',
        'quote_liquidity_qualification': 'minute_quote_bar_not_independent_per_side_tick_freshness_or_size_market_impact_proof'}


def candidate_id(universe_count, ar_percent):
    targets.cohort(universe_count)
    require(type(ar_percent) is int and ar_percent in (0, 100, 200), 'profile')
    return f'arv2-r337-{universe_count}-ar{ar_percent}-W5-five-case-quarantine-v1'


def make_strategy_profile(axis, *, package_sha256, lineage_sha256, universe_count,
                          ar_percent, source_pins, quarantine_catalog_sha256):
    require(_sha(quarantine_catalog_sha256), 'profile')
    # The old pure period constructor supplies unchanged clock/geometry/economics,
    # never a runtime initializer, prepared source, result or run identity.
    template = base.make_profile(axis, package_sha256=package_sha256,
        lineage_sha256=lineage_sha256, universe_count=universe_count,
        ar_percent=ar_percent, source_pins=_pin_map(source_pins))
    seed = {key: value for key, value in template.items() if key != 'profile_sha256'}
    seed.update(quote_policy_fields())
    seed.update(schema=STRATEGY_SCHEMA, research_epoch_id=RESEARCH_EPOCH_ID,
        candidate_id=candidate_id(universe_count, ar_percent),
        quarantine_catalog_sha256=quarantine_catalog_sha256,
        quarantine_policy_sha256=digest(quarantine.profile_record()),
        quarantine_timing='post_construction_caps_final_AR_tilt_to_own_ETF',
        quarantined_binding_count=5, native_price_book_initialized=False,
        maximum_reference_history_calls=0)
    return {**seed, 'profile_sha256': digest(seed)}


STRATEGY_FIXED_FIELDS = {'initial_state': 'new_epoch_empty_positions_and_orders_USD1000000', 'alternative_view': 'score_disagreement_only_not_realized_performance', 'clock': 'same_session_09:20_snapshot_09:31_market_submission_New_York', 'rating_eligibility': 'original_eligible_session_strictly_before_decision_session', 'prices': 'immediately_prior_NYSE_RAW_close;separate_pre0920_same_session_SplitOccurred_factor', 'split_unit_bridge': 'one_bounded_typed_Split_history_batch_prior_NYSE_midnight_to0920;apply_same_day_only;QC_history_qualified_not_formal_PIT', 'clock_subscription': 'SPY_minute_extended_hours_fill_forward_for_clock_only;genuine0920_OnData_confirmation_before_orders', 'sizing_nav': 'exact_prior_NYSE_after_close_NAV;first_2021Nov01_new_epoch_STARTING_CASH;current_cash_bounds_buys', 'execution_quote': 'current_regular_hours_minute_non_fill_forward;no_clock_bar_price_substitution', 'terminal': 'Oct13_valuation_only_no_forced_rebalance', 'gross_target': '0.98', 'aggregate_stock_target_cap': '0.098', 'fee_bps': '10', 'slippage_model_bps': '0', 'account_statistics': 'actual_daily_close_NAV;CAGR_365.25_over_calendar_end_minus_start;drawdown_includes_initial_cash_peak;no_Sharpe', 'maximum_dynamic_subscriptions': 192, 'maximum_reference_securities': 256, 'maximum_reference_history_calls': 0, 'whole_shares': True, 'sell_before_buy': True, 'point_in_time_proven': False, 'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'accepted_risk': True, 'backtest_only': True}
STRATEGY_DYNAMIC_KEYS = ('schema', 'research_epoch_id', 'first_reference_close', 'candidate_id', 'universe_count', 'ar_percent', 'package_sha256', 'lineage_sha256', 'session_axis_sha256', 'session_count', 'evaluation_sessions', 'decision_sessions', 'source_pins', 'primary_view', 'quarantine_catalog_sha256', 'quarantine_policy_sha256', 'quarantine_timing', 'quarantined_binding_count', 'native_price_book_initialized', 'profile_sha256')

STRATEGY_FIXED_FIELDS = {key: value for key, value in STRATEGY_FIXED_FIELDS.items() if key not in quote_policy_fields()}

def make_profile(strategy_profile, *, runtime_project_id, vendor_source_context_sha256,
                 quarantine_catalog_sha256, source_pins):
    require(type(strategy_profile) is dict and type(runtime_project_id) is int
        and 0 < runtime_project_id <= 2147483647 and _sha(vendor_source_context_sha256)
        and _sha(quarantine_catalog_sha256), 'profile')
    strategy = json.loads(canonical(strategy_profile))
    seed = dict(strategy); supplied = seed.pop('profile_sha256', None)
    require(set(strategy) == set(STRATEGY_FIXED_FIELDS) | set(STRATEGY_DYNAMIC_KEYS) | set(quote_policy_fields())
        and all(type(strategy.get(k)) is type(v) and strategy[k] == v for k, v in STRATEGY_FIXED_FIELDS.items())
        and strategy.get('source_pins') == _pin_map(source_pins)
        and strategy.get('quarantine_timing') == 'post_construction_caps_final_AR_tilt_to_own_ETF'
        and type(strategy.get('maximum_reference_history_calls')) is int
        and strategy['maximum_reference_history_calls'] == 0, 'profile')
    require(_sha(supplied) and digest(seed) == supplied and strategy.get('schema') == STRATEGY_SCHEMA
        and strategy.get('candidate_id') == candidate_id(strategy.get('universe_count'), strategy.get('ar_percent'))
        and strategy.get('research_epoch_id') == RESEARCH_EPOCH_ID
        and strategy.get('quarantine_catalog_sha256') == quarantine_catalog_sha256
        and strategy.get('quarantine_policy_sha256') == digest(quarantine.profile_record())
        and type(strategy.get('quarantined_binding_count')) is int and strategy['quarantined_binding_count'] == 5
        and strategy.get('native_price_book_initialized') is False
        and strategy.get('package_sha256') == monetary.native.PACKAGE_SHA256
        and strategy.get('lineage_sha256') == LINEAGE_SHA256
        and strategy.get('primary_view') == targets.PRIMARY_VIEW
        and strategy.get('initial_state') == 'new_epoch_empty_positions_and_orders_USD1000000'
        and strategy.get('first_reference_close') == base.FIRST_REFERENCE_CLOSE
        and strategy.get('session_count') == base.FULL_AXIS_COUNT and type(strategy.get('session_count')) is int
        and strategy.get('session_axis_sha256') == base.FULL_AXIS_SHA256
        and type(strategy.get('evaluation_sessions')) is list
        and len(strategy['evaluation_sessions']) == EXPECTED_EVALUATION_SESSION_COUNT
        and digest(strategy['evaluation_sessions']) == EVALUATION_SESSIONS_SHA256
        and type(strategy.get('decision_sessions')) is list
        and len(strategy['decision_sessions']) == EXPECTED_DECISION_SESSION_COUNT
        and digest(strategy['decision_sessions']) == DECISION_SESSIONS_SHA256
        and tuple(strategy['decision_sessions']) == weekly_axis(tuple(strategy['evaluation_sessions']))
        and all(strategy.get(k) == v for k, v in quote_policy_fields().items())
        and all(strategy.get(k) is False for k in ('point_in_time_proven', 'formal_identity_admitted',
            'formal_forward_ready', 'paper_or_live_ready')), 'profile')
    value = {'schema': SCHEMA, 'candidate_id': strategy['candidate_id'],
        'strategy_profile': strategy, 'strategy_profile_sha256': supplied,
        'package_sha256': strategy['package_sha256'], 'lineage_sha256': strategy['lineage_sha256'],
        'universe_count': strategy['universe_count'], 'ar_percent': strategy['ar_percent'],
        'runtime_project_id': runtime_project_id,
        'vendor_source_context_sha256': vendor_source_context_sha256,
        'quarantine_catalog_sha256': quarantine_catalog_sha256,
        'quarantine_policy_sha256': digest(quarantine.profile_record()),
        'monetary_policy_sha256': digest(monetary.profile_record()), 'source_pins': _pin_map(source_pins),
        'reference_and_NAV_source_policy': 'vendor_only_admitted_nonquarantine5636_plus8_funds_conditional510_hardstop',
        'automatic_security_price_seeding': False, 'research_epoch_id': RESEARCH_EPOCH_ID,
        'first_reference_close': base.FIRST_REFERENCE_CLOSE, **FALSE_FLAGS}
    return {**value, 'profile_sha256': digest(value)}


def validate_profile(value):
    require(type(value) is dict and set(value) == PROFILE_KEYS, 'profile')
    expected = make_profile(value['strategy_profile'], runtime_project_id=value['runtime_project_id'],
        vendor_source_context_sha256=value['vendor_source_context_sha256'],
        quarantine_catalog_sha256=value['quarantine_catalog_sha256'], source_pins=value['source_pins'])
    require(expected == value, 'profile')
    return json.loads(canonical(value))


def policy_record():
    return {'schema': SCHEMA, 'research_epoch_id': RESEARCH_EPOCH_ID,
        'source_policy_sha256': digest(monetary.profile_record()),
        'quarantine_policy_sha256': digest(quarantine.profile_record()),
        'evaluation_first': START_SESSION, 'evaluation_last': END_SESSION,
        'first_reference_close': base.FIRST_REFERENCE_CLOSE,
        'candidate_revision': 'new_five_case_quarantine_no_old_result_relabelling',
        'target_change': 'post_all_baseline_caps_AR_tilt_transfer_exact_five_weight_to_own_sleeve_ETF',
        'unchanged': 'all_other_construction_caps_ratings_memberships_clock_split_signed_quote_fee_cash_fill_rules',
        'held_or_ordered_quarantine': 'hard_stop_no_synthetic_liquidation_or_cash_credit',
        'native_price_book_initialized': False, 'full6151_genuine_binding_proof': 'runtime_loaded_package_only',
        'automatic_security_price_seeding': False, 'quote_policy': quote_policy_fields(), **FALSE_FLAGS}


def _integer(value, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum, 'result_count')


def validate_common_result(value, *, expected_profile):
    profile = validate_profile(expected_profile)
    require(type(value) is dict and set(value) == COMMON_RESULT_KEYS
        and value['schema'] == RESULT_SCHEMA + '-source', 'result_common')
    for key in ('common_profile_sha256', 'strategy_profile_sha256', 'vendor_source_context_sha256',
                'monetary_policy_sha256', 'quarantine_catalog_sha256', 'quarantine_policy_sha256', 'research_epoch_id'):
        expected = profile['profile_sha256'] if key == 'common_profile_sha256' else profile[key]
        require(value[key] == expected, 'result_common')
    require(_sha(value['fresh_resolution_sha256']) and _sha(value['fund_translation_sha256']), 'result_common')
    ledger = value['ledger']
    fields = {'schema', 'source_observation', 'counts', 'reference_path_sha256',
        'authoritative_close_path_sha256', 'unique_close_count', 'engine_NAV_diagnostic_path_sha256',
        'reference_QC_History_calls_by_component', 'split_QC_History_calls_by_component', *monetary.FALSE_FLAGS}
    require(type(ledger) is dict and set(ledger) == fields and ledger['schema'] == monetary.SCHEMA + '-ledger'
        and all(ledger[key] is False for key in monetary.FALSE_FLAGS), 'result_common')
    decisions, closes = len(profile['strategy_profile']['decision_sessions']), len(profile['strategy_profile']['evaluation_sessions'])
    require(type(ledger['counts']) is dict and set(ledger['counts']) == {
        'reference_batch_attempts', 'reference_batch_completed', 'close_batch_attempts', 'close_batch_completed'}, 'result_common')
    for key in ('reference_batch_attempts', 'reference_batch_completed'): _integer(ledger['counts'][key], decisions, decisions)
    for key in ('close_batch_attempts', 'close_batch_completed'): _integer(ledger['counts'][key], closes, closes)
    _integer(ledger['unique_close_count'], closes, closes)
    for key in ('reference_QC_History_calls_by_component', 'split_QC_History_calls_by_component'): _integer(ledger[key], 0, 0)
    for key in ('reference_path_sha256', 'authoritative_close_path_sha256', 'engine_NAV_diagnostic_path_sha256'):
        require(_sha(ledger[key]), 'result_common')
    source = ledger['source_observation']
    require(type(source) is dict and set(source) == {'schema', 'research_epoch_id', 'quarantine_catalog_sha256',
        'quarantine_policy_sha256', 'binding_stream_sha256', 'full_stock_binding_count', 'bridge_receipt',
        'vendor_receipt', 'native_price_book_initialized', 'native_price_book_reads', 'lookup_counts', *monetary.FALSE_FLAGS}
        and source['schema'] == monetary.SCHEMA + '-source-observation'
        and source['research_epoch_id'] == RESEARCH_EPOCH_ID
        and source['quarantine_catalog_sha256'] == profile['quarantine_catalog_sha256']
        and source['quarantine_policy_sha256'] == profile['quarantine_policy_sha256']
        and source['binding_stream_sha256'] == monetary.native.BINDING_STREAM_SHA256
        and source['native_price_book_initialized'] is False
        and all(source[key] is False for key in monetary.FALSE_FLAGS), 'result_common')
    _integer(source['full_stock_binding_count'], 6151, 6151); _integer(source['native_price_book_reads'], 0, 0)
    for key in ('bridge_receipt', 'vendor_receipt'):
        pin = source[key]
        require(type(pin) is dict and set(pin) == {'byte_count', 'sha256'} and _sha(pin['sha256']), 'result_common')
        _integer(pin['byte_count'], 1, monetary.MAX_RECEIPT_BYTES)
    names = {prefix + '_' + suffix for prefix in ('native', 'vendor') for suffix in (
        'identity_check_attempts', 'identity_check_completed', 'price_lookup_attempts', 'price_lookup_completed')}
    counts = source['lookup_counts']; require(type(counts) is dict and set(counts) == names, 'result_common')
    bound = min(monetary.MAX_CENSUS * (decisions + closes), MAX_VENDOR_COMPLETED_LOOKUPS)
    for name in names: _integer(counts[name], 0, 0 if name.startswith('native_') else bound)
    require(len({counts['vendor_' + suffix] for suffix in ('identity_check_attempts', 'identity_check_completed',
        'price_lookup_attempts', 'price_lookup_completed')}) == 1
        and counts['vendor_price_lookup_completed'] >= decisions, 'result_common')
    return json.loads(canonical(value))


def validate_quarantine_result(value, *, expected_profile):
    profile = validate_profile(expected_profile)
    require(type(value) is dict and set(value) == {'schema', 'research_epoch_id', 'quarantine_catalog_sha256',
        'quarantine_policy_sha256', 'decision_count', 'transfer_ledger_path_sha256',
        'total_selected_sleeve_occurrence_count', 'total_positive_sleeve_occurrence_count',
        'total_transferred_to_own_etf_weight', 'decisions_with_positive_transfer',
        'quarantined_target_count', 'quarantined_order_count', 'quarantined_holding_count',
        'replacement_name_promotions', 'renormalization_performed', *FALSE_FLAGS}, 'quarantine_ledger')
    require(value['schema'] == RESULT_SCHEMA + '-quarantine'
        and value['research_epoch_id'] == RESEARCH_EPOCH_ID
        and value['quarantine_catalog_sha256'] == profile['quarantine_catalog_sha256']
        and value['quarantine_policy_sha256'] == profile['quarantine_policy_sha256']
        and _sha(value['transfer_ledger_path_sha256'])
        and value['renormalization_performed'] is False
        and all(value[k] is False for k in FALSE_FLAGS), 'quarantine_ledger')
    decisions = len(profile['strategy_profile']['decision_sessions'])
    _integer(value['decision_count'], decisions, decisions)
    for key in ('quarantined_target_count', 'quarantined_order_count', 'quarantined_holding_count', 'replacement_name_promotions'):
        _integer(value[key], 0, 0)
    _integer(value['total_selected_sleeve_occurrence_count'], 0, 5 * profile['universe_count'] * decisions)
    _integer(value['total_positive_sleeve_occurrence_count'], 0, value['total_selected_sleeve_occurrence_count'])
    _integer(value['decisions_with_positive_transfer'], 0, decisions)
    raw = value['total_transferred_to_own_etf_weight']
    require(type(raw) is str and 0 < len(raw) <= 96, 'quarantine_ledger')
    try: weight = Decimal(raw)
    except Exception: raise Refused('quarantine_ledger') from None
    require(weight.is_finite() and 0 <= weight <= Decimal('0.98') * decisions
        and (weight > 0) == (value['total_positive_sleeve_occurrence_count'] > 0)
        == (value['decisions_with_positive_transfer'] > 0), 'quarantine_ledger')
    return json.loads(canonical(value))


def validate_result_statistics(custom_statistics, *, expected_profile):
    """Strict finite aggregate reader; Completed status alone is insufficient.

    The caller separately authenticates cloud project/source and actual job
    identity. Hash fields bind reported paths, not independent private rows.
    No provider, Object Store, filesystem, or order operation occurs here.
    """
    common_profile = validate_profile(expected_profile)
    expected_profile = {**common_profile['strategy_profile'],
        'candidate_id': common_profile['candidate_id'], 'profile_sha256': common_profile['profile_sha256']}
    supplied = common_profile['profile_sha256']
    require(type(custom_statistics) is dict and len(custom_statistics) <= 256,
            "result_statistics")

    def pairs(items):
        result = {}
        for key, value in items:
            require(type(key) is str and key not in result, "result_duplicate_key")
            result[key] = value
        return result

    def parse(name):
        payload = custom_statistics.get(name)
        require(type(payload) is str and 0 < len(payload) <= MAX_STATISTIC_BYTES,
                "result_payload_bound")
        try:
            raw = payload.encode("ascii")
            value = json.loads(raw, object_pairs_hook=pairs)
            require(type(value) is dict and targets.canonical(value) == raw,
                    "result_canonical")
            return value
        except (UnicodeError, ValueError, RecursionError, TypeError):
            raise Refused("result_json") from None

    def integer(value, minimum, maximum):
        require(type(value) is int and minimum <= value <= maximum, "result_count")

    def decimal(value, *, positive=False):
        require(type(value) is str and 0 < len(value) <= 96, "result_decimal")
        try:
            result = Decimal(value)
        except Exception:
            raise Refused("result_decimal") from None
        require(result.is_finite() and abs(result) < Decimal("1e50")
                and (result > 0 if positive else result >= 0), "result_decimal")
        return result

    meta, monthly = parse(META_STATISTIC), parse(MONTHLY_STATISTIC)
    hashes = {"common_source_path_sha256", "plan_path_sha256", "fill_path_sha256", "split_path_sha256",
        "account_path_sha256", "account_safety_sha256", "preopen_frontier_sha256", "alternative_view_diagnostic_sha256"}
    safeguards = {"complete_geometry", "no_open_orders", "nonnegative_cash_at_fills_closes_terminal",
        "whole_long_holdings_at_fills_closes_terminal", "configured_fee_checks_complete",
        "actual_fill_cash_reconciled", "actual_clock_confirmation_complete"}
    false_flags = set(FALSE_FLAGS)
    identity_fields = {"candidate_id", "profile_sha256", "package_sha256", "lineage_sha256"}
    require(set(meta) == hashes | safeguards | false_flags | identity_fields | {
        "schema", "decision_count", "evaluation_session_count", "order_count", "fill_count",
        "raw_reference_history_calls", "split_unit_history_calls", "cash_constrained_buy_count",
        "coverage_fallback_counts", "alternative_view_eligibility_disagreements",
        "alternative_view_score_disagreements", "forced_delisting", "actual_terminal", "account_aggregates", "common_price", "quarantine"}, "result_meta_fields")
    require(meta["schema"] == RESULT_SCHEMA
            and meta["actual_terminal"] == "runtime_geometry_complete_not_independent_source_admission",
            "result_schema")
    for key in identity_fields:
        require(meta[key] == expected_profile[key], "result_identity")
    for key in hashes:
        targets.require_sha(meta[key])
    require(all(meta[key] is True for key in safeguards)
            and all(meta[key] is False for key in false_flags), "result_safety_flags")
    sessions, decisions = expected_profile["evaluation_sessions"], expected_profile["decision_sessions"]
    require(type(sessions) is list and type(decisions) is list
            and sessions[0] == START_SESSION and sessions[-1] == END_SESSION
            and tuple(sorted(set(sessions))) == tuple(sessions)
            and tuple(decisions) == weekly_axis(tuple(sessions)), "result_profile_geometry")
    for key, wanted in (("decision_count", len(decisions)), ("evaluation_session_count", len(sessions)),
                        ("raw_reference_history_calls", 0), ("split_unit_history_calls", len(decisions))):
        integer(meta[key], wanted, wanted)
    integer(meta["order_count"], 1, MAX_ORDERS)
    integer(meta["fill_count"], meta["order_count"], meta["order_count"])
    integer(meta["cash_constrained_buy_count"], 0, 256 * len(decisions))
    for key in ("alternative_view_eligibility_disagreements", "alternative_view_score_disagreements"):
        integer(meta[key], 0, MAX_ROWS * len(decisions))
    fallback = meta["coverage_fallback_counts"]
    reasons = {"missing_or_stale_collection", "unresolved_reported_weight", "reported_book_incomplete",
        "qc_technical_identity_below_99pct", "economic_name_coverage_below_25pct", "cap_weight_coverage_below_25pct",
        "verified_name_count_below_five", "positive_score_count_below_five"}
    allowed = {universe + ":" + reason for universe in targets.cohort(expected_profile["universe_count"]) for reason in reasons}
    require(type(fallback) is dict and set(fallback) <= allowed, "result_fallback_inventory")
    for count in fallback.values():
        integer(count, 1, len(decisions))
    forced_record = meta["forced_delisting"]
    require(type(forced_record) is dict and set(forced_record) == {
        "schema", "order_count", "event_count", "fill_event_count", "terminal_order_count",
        "absolute_filled_quantity", "filled_notional", "actual_engine_fee_amount", "accounting_complete",
        "ledger_sha256", "raw_order_rows_in_summary", "raw_security_rows_in_summary"}, "result_forced_fields")
    require(forced_record["schema"] == forced.FORCED_DELISTING_SUMMARY_SCHEMA
            and forced_record["accounting_complete"] is True
            and forced_record["raw_order_rows_in_summary"] is False
            and forced_record["raw_security_rows_in_summary"] is False, "result_forced_flags")
    count = forced_record["order_count"]
    integer(count, 0, MAX_ORDERS)
    for key in ("event_count", "fill_event_count", "terminal_order_count"):
        integer(forced_record[key], count, count)
    quantity = forced_record["absolute_filled_quantity"]
    integer(quantity, count, 10 ** 40)
    notional = decimal(forced_record["filled_notional"])
    fee = decimal(forced_record["actual_engine_fee_amount"])
    require((count > 0 and notional > 0) or (count == quantity == 0 and notional == fee == 0), "result_forced_census")
    targets.require_sha(forced_record["ledger_sha256"])
    require(set(monthly) == {"schema", "candidate_id", "profile_sha256", "months", "last_month_partial",
                            "alternative_view_realized_performance"}, "result_monthly_fields")
    require(monthly["schema"] == MONTH_SCHEMA
            and monthly["candidate_id"] == expected_profile["candidate_id"]
            and monthly["profile_sha256"] == supplied and monthly["last_month_partial"] is True
            and monthly["alternative_view_realized_performance"] is False, "result_monthly_identity")
    endpoints = {}
    for session in sessions:
        endpoints[session[:7]] = session
    rows = monthly["months"]
    require(type(rows) is list and len(rows) == len(endpoints), "result_monthly_geometry")
    previous, previous_error = STARTING_CASH, Decimal(0)
    with localcontext() as arithmetic:
        arithmetic.prec = 96
        for row, session in zip(rows, endpoints.values(), strict=True):
            require(type(row) is list and len(row) == 3 and row[0] == session, "result_month_endpoint")
            require(type(row[1]) is str and 0 < len(row[1]) <= 96, "result_return")
            try:
                change = Decimal(row[1])
            except Exception:
                raise Refused("result_return") from None
            nav = decimal(row[2], positive=True)
            require(change.is_finite() and -1 < change < Decimal("1e50")
                    and change.as_tuple().exponent == -12 and nav.as_tuple().exponent == -6,
                    "result_rounding")
            expected = nav / previous - 1
            require(previous > previous_error, "result_nav_rounding_resolution")
            tolerance = Decimal("5e-13") + Decimal("5e-7") / (previous - previous_error)
            tolerance += nav * previous_error / (previous * (previous - previous_error))
            require(abs(change - expected) <= tolerance, "result_return_nav_mismatch")
            previous, previous_error = nav, Decimal("5e-7")
        aggregate = meta["account_aggregates"]
        require(type(aggregate) is dict and set(aggregate) == {"starting_cash", "terminal_nav", "net_total_return",
            "cagr", "elapsed_calendar_days", "cagr_year_days", "daily_close_max_drawdown", "observed_close_count",
            "strategy_order_fees", "forced_exit_engine_fees", "total_engine_fees",
            "daily_drawdown_not_independently_reconstructed_from_monthly"}, "result_aggregate_fields")
        days = (datetime.strptime(sessions[-1], "%Y-%m-%d") - datetime.strptime(START_SESSION, "%Y-%m-%d")).days
        integer(aggregate["elapsed_calendar_days"], days, days)
        integer(aggregate["observed_close_count"], len(sessions), len(sessions))
        require(aggregate["starting_cash"] == str(STARTING_CASH)
                and aggregate["terminal_nav"] == rows[-1][2] and aggregate["cagr_year_days"] == "365.25"
                and aggregate["daily_drawdown_not_independently_reconstructed_from_monthly"] is True,
                "result_aggregate_binding")
        def signed_stat(name):
            value = aggregate[name]
            require(type(value) is str and 0 < len(value) <= 96, "result_aggregate_decimal")
            try:
                result = Decimal(value)
            except Exception:
                raise Refused("result_aggregate_decimal") from None
            require(result.is_finite() and result.as_tuple().exponent == -12, "result_aggregate_rounding")
            return result
        net, cagr, drawdown = (signed_stat(name) for name in ("net_total_return", "cagr", "daily_close_max_drawdown"))
        require(-1 < drawdown <= 0 and -1 < net and -1 < cagr, "result_aggregate_range")
        lower = (previous - Decimal("5e-7")) / STARTING_CASH
        upper = (previous + Decimal("5e-7")) / STARTING_CASH
        require(lower - 1 - Decimal("5e-13") <= net <= upper - 1 + Decimal("5e-13"), "result_total_return")
        require(lower ** (Decimal("365.25") / days) - 1 - Decimal("5e-13") <= cagr
                <= upper ** (Decimal("365.25") / days) - 1 + Decimal("5e-13"), "result_cagr")
        strategy_fee = decimal(aggregate["strategy_order_fees"])
        forced_fee = decimal(aggregate["forced_exit_engine_fees"])
        total_fee = decimal(aggregate["total_engine_fees"])
        require(forced_fee == fee and total_fee == strategy_fee + forced_fee, "result_fee_reconciliation")
    validate_common_result(meta["common_price"], expected_profile=common_profile)
    validate_quarantine_result(meta["quarantine"], expected_profile=common_profile)
    return {"meta": meta, "monthly": monthly}
