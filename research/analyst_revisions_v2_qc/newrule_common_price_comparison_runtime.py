"""Concrete common-RAW reference/NAV successor of the frozen quote-aware driver.

Public source construction and aggregate parsing grant no source rights or
run authority. The cloud builder pins the unchanged quote-aware base bytes.
All strategy construction, splits, signed quotes, cash/fee/fill checks remain
in that base; only reference marks, actual-close valuation and result accounting
are replaced. No source rows or prices are serialized by this module.
"""
import hashlib
import json
import re
from datetime import datetime, time
from decimal import Decimal, localcontext
from types import MappingProxyType

try:
    import newrule_comparison_qc_runtime as base
    import newrule_common_price_qc_runtime as monetary
    import newrule_native_price_book_runtime as native_reader
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_comparison_qc_runtime as base
    from research.analyst_revisions_v2_qc import newrule_common_price_qc_runtime as monetary
    from research.analyst_revisions_v2_qc import newrule_native_price_book_runtime as native_reader

targets, legacy, forced = base.targets, base.legacy, base.forced
STARTING_CASH, START_SESSION, END_SESSION = base.STARTING_CASH, base.START_SESSION, base.END_SESSION
MAX_ORDERS, MAX_ROWS = base.MAX_ORDERS, base.MAX_ROWS
weekly_axis, account_aggregates = base.weekly_axis, base.account_aggregates
LINEAGE_SHA256 = 'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'
SCHEMA = 'arv2-r298-common-price-comparison-profile-v1'
RESULT_SCHEMA = 'arv2-r298-common-price-comparison-result-v1'
MONTH_SCHEMA = 'arv2-r298-common-price-monthly-return-v1'
META_STATISTIC, MONTHLY_STATISTIC = 'ARV2_COMMON_PRICE_META', 'ARV2_COMMON_PRICE_MONTHLY'
MAX_STATISTIC_BYTES = 16384
MAX_VENDOR_COMPLETED_LOOKUPS = 300000
FROZEN_BASE_SHA256 = 'c7b829020ac20704ec6f813997ebef396ed2069b8ad60c77bf3dc84cd67e2814'
FALSE_FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False,
    'source_admission_granted': False, 'strategy_result_accepted': False}
PROFILE_KEYS = frozenset(('schema', 'candidate_id', 'profile_sha256', 'strategy_profile',
    'strategy_profile_sha256', 'package_sha256', 'lineage_sha256', 'universe_count',
    'ar_percent', 'runtime_project_id', 'native_source_context_sha256',
    'vendor_source_context_sha256', 'monetary_policy_sha256', 'frozen_quote_base_sha256',
    'source_pins', 'reference_and_NAV_source_policy', 'automatic_security_price_seeding', *FALSE_FLAGS))
COMMON_RESULT_KEYS = frozenset(('schema', 'common_profile_sha256', 'strategy_profile_sha256',
    'native_source_context_sha256', 'vendor_source_context_sha256', 'monetary_policy_sha256',
    'fresh_resolution_sha256', 'fund_translation_sha256', 'ledger'))
FINITE = frozenset(('profile', 'source_pins', 'base_not_quote_aware', 'context', 'project',
    'once', 'not_ready', 'resolution', 'identity', 'fund_translation', 'catalog', 'reference',
    'close_clock', 'close_state', 'terminal', 'source_counters', 'result_common',
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


def make_profile(strategy_profile, *, runtime_project_id, native_source_context_sha256,
                 vendor_source_context_sha256, source_pins):
    require(type(strategy_profile) is dict and type(runtime_project_id) is int
        and 0 < runtime_project_id <= 2147483647
        and _sha(native_source_context_sha256) and _sha(vendor_source_context_sha256), 'profile')
    raw = canonical(strategy_profile)
    require(0 < len(raw) <= 131072, 'profile')
    strategy = json.loads(raw)
    seed = dict(strategy)
    supplied = seed.pop('profile_sha256', None)
    require(seed.get('schema') == base.SCHEMA and _sha(supplied) and digest(seed) == supplied
        and strategy.get('universe_count') in (6, 8)
        and type(strategy.get('ar_percent')) is int and strategy['ar_percent'] in (0, 100, 200)
        and strategy.get('package_sha256') == monetary.native.PACKAGE_SHA256
        and strategy.get('lineage_sha256') == LINEAGE_SHA256
        and strategy.get('execution_policy') == 'arv2-newrule-quote-aware-execution-v1'
        and type(strategy.get('candidate_id')) is str and strategy['candidate_id'].endswith('-quote-aware-v1')
        and all(strategy.get(key) is False for key in ('point_in_time_proven',
            'formal_identity_admitted', 'formal_forward_ready', 'paper_or_live_ready')), 'profile')
    value = {'schema': SCHEMA, 'candidate_id': strategy['candidate_id'] + '-common-RAW-v1',
        'strategy_profile': strategy, 'strategy_profile_sha256': supplied,
        'package_sha256': strategy['package_sha256'], 'lineage_sha256': strategy['lineage_sha256'],
        'universe_count': strategy['universe_count'], 'ar_percent': strategy['ar_percent'],
        'runtime_project_id': runtime_project_id,
        'native_source_context_sha256': native_source_context_sha256,
        'vendor_source_context_sha256': vendor_source_context_sha256,
        'monetary_policy_sha256': digest(monetary.profile_record()),
        'frozen_quote_base_sha256': FROZEN_BASE_SHA256, 'source_pins': _pin_map(source_pins),
        'reference_and_NAV_source_policy': 'exact_original_native_five_else_vendor_full_window_no_fallback_same_all_six_cells',
        'automatic_security_price_seeding': False,
        **FALSE_FLAGS}
    return {**value, 'profile_sha256': digest(value)}


def validate_profile(value):
    require(type(value) is dict and set(value) == PROFILE_KEYS, 'profile')
    expected = make_profile(value['strategy_profile'], runtime_project_id=value['runtime_project_id'],
        native_source_context_sha256=value['native_source_context_sha256'],
        vendor_source_context_sha256=value['vendor_source_context_sha256'], source_pins=value['source_pins'])
    require(expected == value, 'profile')
    return json.loads(canonical(value))


def policy_record():
    return {'schema': SCHEMA, 'frozen_quote_base_sha256': FROZEN_BASE_SHA256,
        'source_policy_sha256': digest(monetary.profile_record()),
        'unchanged': 'construction_caps_ratings_memberships_0920_split_bridge_0931_signed_quotes_10bps_fees_cash_guard_fill_tolerance',
        'fund_bridge': 'bijection_current_typed_own_fund_SID_to_price_contract_only_targets_orders_fills_unchanged',
        'reference': 'one_common_source_batch_per_decision_prior_NYSE_RAW_target_union_all_positive_holdings',
        'close': 'actual_NYSE_close_or_later_Decimal96_actual_cash_plus_all_positive_whole_holdings_RAW_marks',
        'intraday': 'engine_NAV_diagnostic_only_no_future_close_mark',
        'expiry': 'no_membership_binding_or_metadata_expiry_closes_a_positive_holding',
        'counter_change': 'zero_reference_History_calls_honest_common_lookups_one_unchanged_split_History_per_decision',
        'automatic_security_price_seeding': False,
        'vendor_completed_lookup_budget': MAX_VENDOR_COMPLETED_LOOKUPS,
        'results': 'new_closed_aggregate_reader_never_fabricate_old_History_counts', **FALSE_FLAGS}


def _integer(value, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum, 'result_count')


def validate_common_result(value, *, expected_profile):
    profile = validate_profile(expected_profile)
    require(type(value) is dict and set(value) == COMMON_RESULT_KEYS
        and value['schema'] == RESULT_SCHEMA + '-source', 'result_common')
    for key in ('common_profile_sha256', 'strategy_profile_sha256', 'native_source_context_sha256',
                'vendor_source_context_sha256', 'monetary_policy_sha256'):
        expected = profile['profile_sha256'] if key == 'common_profile_sha256' else profile[key]
        require(value[key] == expected, 'result_common')
    require(_sha(value['fresh_resolution_sha256']) and _sha(value['fund_translation_sha256']), 'result_common')
    ledger = value['ledger']
    fields = {'schema', 'source_observation', 'counts', 'reference_path_sha256',
        'authoritative_close_path_sha256', 'unique_close_count', 'engine_NAV_diagnostic_path_sha256',
        'reference_QC_History_calls_by_component', 'split_QC_History_calls_by_component', *monetary.FALSE_FLAGS}
    require(type(ledger) is dict and set(ledger) == fields
        and ledger['schema'] == monetary.SCHEMA + '-ledger'
        and all(ledger[key] is False for key in monetary.FALSE_FLAGS), 'result_common')
    strategy = profile['strategy_profile']
    decision_count, close_count = len(strategy['decision_sessions']), len(strategy['evaluation_sessions'])
    require(type(ledger['counts']) is dict and set(ledger['counts']) == {
        'reference_batch_attempts', 'reference_batch_completed', 'close_batch_attempts', 'close_batch_completed'}, 'result_common')
    for key in ('reference_batch_attempts', 'reference_batch_completed'):
        _integer(ledger['counts'][key], decision_count, decision_count)
    for key in ('close_batch_attempts', 'close_batch_completed'):
        _integer(ledger['counts'][key], close_count, close_count)
    _integer(ledger['unique_close_count'], close_count, close_count)
    for key in ('reference_QC_History_calls_by_component', 'split_QC_History_calls_by_component'):
        _integer(ledger[key], 0, 0)
    for key in ('reference_path_sha256', 'authoritative_close_path_sha256', 'engine_NAV_diagnostic_path_sha256'):
        require(_sha(ledger[key]), 'result_common')
    source = ledger['source_observation']
    require(type(source) is dict and set(source) == {'schema', 'specification_sha256', 'binding_stream_sha256',
        'native_receipt', 'vendor_receipt', 'lookup_counts', *monetary.FALSE_FLAGS}
        and source['schema'] == monetary.SCHEMA + '-source-observation'
        and source['specification_sha256'] == monetary.NATIVE_SPECIFICATION_SHA256
        and source['binding_stream_sha256'] == monetary.native.BINDING_STREAM_SHA256
        and all(source[key] is False for key in monetary.FALSE_FLAGS), 'result_common')
    for key in ('native_receipt', 'vendor_receipt'):
        pin = source[key]
        require(type(pin) is dict and set(pin) == {'byte_count', 'sha256'} and _sha(pin['sha256']), 'result_common')
        _integer(pin['byte_count'], 1, monetary.MAX_RECEIPT_BYTES)
    counts = source['lookup_counts']
    names = {prefix + '_' + suffix for prefix in ('native', 'vendor') for suffix in (
        'identity_check_attempts', 'identity_check_completed', 'price_lookup_attempts', 'price_lookup_completed')}
    require(type(counts) is dict and set(counts) == names, 'result_common')
    bound = monetary.MAX_CENSUS * (decision_count + close_count)
    for name in names: _integer(counts[name], 0, bound)
    for prefix in ('native', 'vendor'):
        require(len({counts[prefix + '_' + suffix] for suffix in (
            'identity_check_attempts', 'identity_check_completed', 'price_lookup_attempts', 'price_lookup_completed')}) == 1,
            'result_common')
    total = sum(counts[prefix + '_price_lookup_completed'] for prefix in ('native', 'vendor'))
    require(decision_count <= total <= bound
        and counts['native_price_lookup_completed'] <= monetary.native.SELECTED_COUNT * (decision_count + close_count)
        and counts['vendor_price_lookup_completed'] <= MAX_VENDOR_COMPLETED_LOOKUPS,
        'result_common')
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
        "alternative_view_score_disagreements", "forced_delisting", "actual_terminal", "account_aggregates", "common_price"}, "result_meta_fields")
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
    return {"meta": meta, "monthly": monthly}


class CommonPriceComparisonDriver(base.NewruleComparisonDriver):
    """The frozen quote-aware strategy with an exact common mark provider."""

    def __init__(self, algorithm, *, common_profile, native_source_context,
                 vendor_source_context, **base_kwargs):
        profile = validate_profile(common_profile)
        require(base_kwargs.get('profile') == profile['strategy_profile'], 'profile')
        require(callable(getattr(base.NewruleComparisonDriver, '_quote_snapshot', None))
            and callable(getattr(base.NewruleComparisonDriver, 'fee_basis', None)), 'base_not_quote_aware')
        require(type(algorithm.project_id) is int and algorithm.project_id == profile['runtime_project_id']
            and algorithm.live_mode is False, 'project')
        native_context = native_reader.validate_source_context(native_source_context)
        require(digest(native_context) == profile['native_source_context_sha256']
            and type(vendor_source_context) is dict
            and 0 < len(canonical(vendor_source_context)) <= 131072
            and digest(vendor_source_context) == profile['vendor_source_context_sha256'], 'context')
        super().__init__(algorithm, **base_kwargs)
        self._common_profile_raw = canonical(profile)
        self._common_profile = json.loads(self._common_profile_raw)
        self._native_context, self._vendor_context = native_context, json.loads(canonical(vendor_source_context))
        self._common_started = self._common_ready = False
        self._common_source = self._common_ledger = self._native_book = self._vendor_book = None
        self._base_to_price, self._price_to_base = MappingProxyType({}), MappingProxyType({})

    def _common_guard(self):
        require(self._common_ready and canonical(self._common_profile) == self._common_profile_raw, 'not_ready')
        self._require_initialized()
        require(type(self._algorithm.project_id) is int
            and self._algorithm.project_id == self._common_profile['runtime_project_id']
            and self._algorithm.live_mode is False, 'project')
        base.figi.require_preliminary_qc_figi_resolution(self._resolution)
        require(self._native_book.receipt()['fresh_full_forward_reverse_resolution_sha256']
            == self._resolution.resolution_sha256, 'resolution')

    def _freeze_fund_translation(self):
        forward, reverse = {}, {}
        require(tuple(self._etf_symbols) == monetary.native.UNIVERSES, 'fund_translation')
        stocks = set(self._security_by_sid.values())
        for ticker, symbol in self._etf_symbols.items():
            sid = legacy._symbol_sid(symbol, 'common own fund')
            price_id = 'own-etf-' + ticker
            require(sid not in stocks and sid not in self._security_by_sid
                and sid not in forward and price_id not in reverse
                and self._security_by_etf_sid.get(sid) == sid
                and self._symbol_for_security(sid) is symbol, 'fund_translation')
            forward[sid], reverse[price_id] = price_id, sid
        require(len(forward) == len(reverse) == 8
            and stocks.isdisjoint(reverse) and all(reverse[value] == key for key, value in forward.items()),
            'fund_translation')
        self._base_to_price, self._price_to_base = MappingProxyType(forward), MappingProxyType(reverse)

    def _price_identity(self, identity):
        require(type(identity) is str, 'identity')
        if identity in self._base_to_price:
            price_id = self._base_to_price[identity]
            symbol = self._symbol_for_security(identity)
            require(legacy._symbol_sid(symbol, 'common fund roundtrip') == identity
                and self._price_to_base.get(price_id) == identity, 'fund_translation')
            return price_id
        require(identity in self._symbol_by_security, 'identity')
        self._common_source.require_identity(identity)
        return identity

    def initialize(self):
        require(not self._common_started, 'once')
        self._common_started = True
        result = super().initialize()
        self._freeze_fund_translation()
        rows = tuple(self._package.runtime_symbol_bindings)
        Native, Vendor = monetary._provider_types()
        require(Native is native_reader.SpecificNativePriceBook, 'context')
        self._native_book = Native(self._algorithm,
            frozen_source_context=self._native_context,
            expected_context_sha256=self._common_profile['native_source_context_sha256'],
            frozen_runtime_project_id=self._common_profile['runtime_project_id'],
            benchmark_symbol=self._benchmark_symbol, etf_symbols=self._etf_symbols,
            trade_bar_type=self._trade_bar_type, daily_resolution=self._daily_resolution,
            raw_normalization=self._raw_normalization)
        self._vendor_book = Vendor(self._algorithm, native_book=self._native_book,
            resolution=self._resolution, stock_bindings=rows,
            etf_symbols=tuple(self._etf_symbols[ticker] for ticker in monetary.native.UNIVERSES),
            frozen_source_context=self._vendor_context,
            expected_context_sha256=self._common_profile['vendor_source_context_sha256'],
            frozen_runtime_project_id=self._common_profile['runtime_project_id'])
        self._common_source = monetary.SpecificCommonPriceBook(self._native_book, self._vendor_book,
            stock_bindings=rows, own_fund_contracts=monetary.fund_contracts(),
            session_axis=self._session_axis, native_specification=self._native_context['specification'])
        self._common_source.authenticate_once()
        require(self._native_book.receipt()['fresh_full_forward_reverse_resolution_sha256']
            == self._resolution.resolution_sha256, 'resolution')
        self._common_ledger = monetary.CommonPriceLedger(self._common_source)
        self._common_ready = True
        self._common_guard()
        return result

    def _reference_prices(self, session, security_ids):
        self._common_guard()
        require(type(security_ids) is tuple and 0 < len(security_ids) <= monetary.MAX_CENSUS
            and security_ids == tuple(sorted(set(security_ids))), 'reference')
        holdings = self._current_holding_census()
        require(set(holdings) <= set(security_ids), 'reference')
        symbols, inverse = {}, {}
        for identity in security_ids:
            symbol, _ = self._ensure_security(identity)
            price_id = self._price_identity(identity)
            require(price_id not in inverse, 'identity')
            inverse[price_id] = identity
            symbols[price_id] = symbol
        translated_holdings = {self._price_identity(identity): quantity for identity, quantity in holdings.items()}
        prices = self._common_ledger.reference_prices(session, tuple(sorted(inverse)),
            translated_holdings, symbols, now=self._now())
        require(set(prices) == set(inverse), 'reference')
        return {inverse[price_id]: value for price_id, value in prices.items()}

    def on_after_close(self):
        self._common_guard()
        now = self._now()
        session = now.date().isoformat()
        if session not in self._evaluation_sessions: return None
        require(now >= self._common_source.session_close(session), 'close_clock')
        if session in self._decision_set:
            require(session in self._executed, 'close_state')
        require(self._intent is None and not tuple(self._algorithm.transactions.get_open_orders()), 'close_state')
        cash, holdings = self._portfolio_cash(), self._current_holding_census()
        translated, symbols = {}, {}
        for identity, quantity in holdings.items():
            price_id = self._price_identity(identity)
            require(price_id not in translated, 'identity')
            translated[price_id], symbols[price_id] = quantity, self._symbol_for_security(identity)
        try:
            engine_diagnostic = self._portfolio_equity()
        except Exception:
            engine_diagnostic = None
        nav, gross = self._common_ledger.observe_close(session, cash=cash, holdings=translated,
            runtime_symbols=symbols, now=now, engine_nav=engine_diagnostic)
        if session in self._account_observations:
            require(self._account_observations[session] == nav
                and self._gross_exposure_observations.get(session) == gross, 'close_state')
        self._account_observations[session], self._gross_exposure_observations[session] = nav, gross
        self._account_safety[session] = targets.digest({'cash': str(cash), 'holdings': sorted(holdings.items()),
            'open_orders': 0, 'whole_long_only': True})

    def _common_result(self):
        self._common_guard()
        result = {'schema': RESULT_SCHEMA + '-source',
            'common_profile_sha256': self._common_profile['profile_sha256'],
            'strategy_profile_sha256': self._common_profile['strategy_profile_sha256'],
            'native_source_context_sha256': self._common_profile['native_source_context_sha256'],
            'vendor_source_context_sha256': self._common_profile['vendor_source_context_sha256'],
            'monetary_policy_sha256': self._common_profile['monetary_policy_sha256'],
            'fresh_resolution_sha256': self._resolution.resolution_sha256,
            'fund_translation_sha256': digest(sorted(self._base_to_price.items())),
            'ledger': self._common_ledger.summary()}
        return validate_common_result(result, expected_profile=self._common_profile)

    def on_end_of_algorithm(self):
        self._common_guard()
        require(not self._emitted and self._intent is None
                and tuple(sorted(self._plans)) == self._decision_sessions
                and tuple(sorted(self._executed)) == self._decision_sessions
                and tuple(sorted(self._account_observations)) == self._evaluation_sessions
                and tuple(sorted(self._account_safety)) == self._evaluation_sessions
                and tuple(sorted(self._preopen_clock_confirmations)) == self._decision_sessions
                and not tuple(self._algorithm.transactions.get_open_orders()), "incomplete_terminal_geometry")
        require(self._now().date().isoformat() >= END_SESSION, "terminal_clock")
        self._portfolio_cash()
        self._current_holding_census()
        require(0 < len(self._order_ids) == len(self._fills) <= MAX_ORDERS
                and self._reference_history_call_count == 0
                and self._split_history_count == len(self._decision_sessions),
                "terminal_order_or_history_census")
        months = {}
        for session in self._evaluation_sessions:
            months[session[:7]] = (session, self._account_observations[session])
        previous, monthly = STARTING_CASH, []
        with localcontext() as arithmetic:
            arithmetic.prec = 96
            for session, value in months.values():
                monthly.append([session, str((value / previous - 1).quantize(Decimal("1e-12"))),
                                str(value.quantize(Decimal("0.000001")))])
                previous = value
        meta = {"schema": RESULT_SCHEMA,
            "candidate_id": self._common_profile["candidate_id"], "profile_sha256": self._common_profile["profile_sha256"],
            "package_sha256": self._profile["package_sha256"], "lineage_sha256": self._profile["lineage_sha256"],
            "decision_count": len(self._plans), "evaluation_session_count": len(self._evaluation_sessions),
            "order_count": len(self._order_ids), "fill_count": len(self._fills),
            "raw_reference_history_calls": self._reference_history_call_count,
            "split_unit_history_calls": self._split_history_count,
            "common_source_path_sha256": targets.digest([self._plans[s]["binding"]["context_sha256"] for s in self._decision_sessions]),
            "plan_path_sha256": targets.digest([self._plans[s]["sha256"] for s in self._decision_sessions]),
            "fill_path_sha256": targets.digest(self._fills), "split_path_sha256": targets.digest(self._split_path),
            "account_path_sha256": targets.digest([(s, str(self._account_observations[s])) for s in self._evaluation_sessions]),
            "account_safety_sha256": targets.digest(sorted(self._account_safety.items())),
            "preopen_frontier_sha256": targets.digest(sorted(self._preopen_clock_confirmations.items())),
            "complete_geometry": True, "no_open_orders": True,
            "nonnegative_cash_at_fills_closes_terminal": True, "whole_long_holdings_at_fills_closes_terminal": True,
            "configured_fee_checks_complete": True, "actual_fill_cash_reconciled": True,
            "actual_clock_confirmation_complete": True,
            "cash_constrained_buy_count": self._cash_underfill_count,
            "coverage_fallback_counts": self._fallback_counts,
            "alternative_view_diagnostic_sha256": targets.digest(self._score_disagreement),
            "alternative_view_eligibility_disagreements": sum(row[1] for row in self._score_disagreement),
            "alternative_view_score_disagreements": sum(row[2] for row in self._score_disagreement),
            "forced_delisting": forced.forced_delisting_summary(self._forced_ledger),
            "account_aggregates": account_aggregates(self._account_observations, self._evaluation_sessions,
                self._fills, forced.forced_delisting_summary(self._forced_ledger)),
            "actual_terminal": "runtime_geometry_complete_not_independent_source_admission",
            "point_in_time_proven": False, "formal_identity_admitted": False,
            "formal_forward_ready": False, "paper_or_live_ready": False,
            "source_admission_granted": False, "strategy_result_accepted": False,
            "common_price": self._common_result()}
        monthly_record = {"schema": MONTH_SCHEMA, "candidate_id": self._common_profile["candidate_id"],
            "profile_sha256": self._common_profile["profile_sha256"], "months": monthly,
            "last_month_partial": True, "alternative_view_realized_performance": False}
        validate_result_statistics({META_STATISTIC: canonical(meta).decode("ascii"),
            MONTHLY_STATISTIC: canonical(monthly_record).decode("ascii")}, expected_profile=self._common_profile)
        for name, record in ((META_STATISTIC, meta), (MONTHLY_STATISTIC, monthly_record)):
            payload = targets.canonical(record)
            require(len(payload) <= MAX_STATISTIC_BYTES, "statistic_bound")
            self._algorithm.set_summary_statistic(name, payload.decode("ascii"))
        self._completed = self._emitted = True
        return meta, monthly_record
