"""Specific QC-local RAW close reader; no host export or source admission.

Construction is inert. The one explicit authentication pass requires the
future strategy's exact project context, a fresh genuine full inventory and
current native identity/currency checks before reading the fixed QC object.
"""
import hashlib
import json
import math
import re
import time as clock
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal

try:
    import newrule_native_price_source_diagnostic as native
    import newrule_native_price_book_publication as publication
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as native
    from research.analyst_revisions_v2_qc import newrule_native_price_book_publication as publication

SCHEMA = 'arv2-r298-specific-native-price-book-runtime-v1'
CONTEXT_SCHEMA = 'arv2-r298-specific-native-source-context-v1'
SOURCE_CONTEXT_SHA256 = 'dca0fb0cc15093a1fd892dfbfc2f4d1216a330bcf4bf355625cc07e774e3e07b'
AK_PUBLIC_BINDING_SHA256 = '2eab16f58809f2af9eb10b1507a04796c3630c555cb0689acf61b2cdea4737ce'
SOURCE_SUMMARY_SHA256 = '88bac1c6d26fa32b92bae1f770f273d8858aae7588b3c1e1a83c8957327aeb7e'
SOURCE_PUBLICATION_SHA256 = 'e5f645f8225519bded97892a0e843fc332738129b1fd0003e751925a416e1a4e'
SOURCE_BOOK_BYTES = 1313871
SOURCE_BOOK_SHA256 = 'b149c9c659ef53084782e25ee18ffc4133bebb063180958651cafc69725c7299'
SOURCE_PROJECT_ID = 38522505
ACTIVATION = ('arv2/newrule-plain-v1/95405d1b569d4bfeeb6c6d87/transport-manifest.json',
    'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b', 5901)
MAX_AUTHENTICATION_SECONDS, MAX_LOOKUPS = 300, 200000
FALSE_FLAGS = {'raw_data_exported': False, 'price_source_policy_admitted': False,
    'price_input_admitted': False, 'NAV_input_admitted': False, 'price_coverage_proven': False,
    'historical_identity_proven': False, 'permanent_security_master_proven': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'strategy_result_accepted': False, 'paper_or_live_ready': False,
    'other_source_or_per_date_fallback': False, 'eligibility_or_holding_expiry_changed': False}
FINITE = frozenset(('context', 'project', 'once', 'state', 'deadline', 'orders', 'settings',
    'source_read_unknown', 'source_bytes', 'source_record', 'catalog', 'current_resolution',
    'current_collision', 'selected_identity', 'currency', 'subscription', 'calendar',
    'source_changed', 'binding', 'session', 'future_session', 'absent', 'invalid_or_duplicate',
    'failure_unknown', 'lookup_bound', 'unknown'))
_SOURCE_CONTEXT_JSON = "{\"schema\":\"arv2-r298-specific-native-source-context-v1\",\"source_fact_sha256\":\"13a190bd378c9b24a818c691cd5c5dcc091ddd007c8655bdb0716a67c7d39a1e\",\"source_project_id\":38522505,\"source_backtest_id\":\"d366867e9ca3a657baea9beb9b660b41\",\"source_projection_sha256\":\"65cebf606f2867b58ae203b186f3ce7ec0701fc2f3c5f576f13adef46ca5624a\",\"source_profile_sha256\":\"3e985a9d6951adf53aa058fb4116f26b4c90bd7a881e9c32c9945306363279f1\",\"scope\":{\"schema\":\"arv2-r298-native-book-namespace-v1\",\"own_project_id\":38522505,\"source_specification_sha256\":\"9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66\",\"protocol_source_profile_sha256\":\"3e8c98f4ff76e73b7c33b9d1988e7f6088aa6b32ecbc7ae82b2acb92a6e4b820\",\"run_scope_tag\":\"R326-20261027-AH\"},\"specification\":{\"NYSE_schedule_sha256\":\"d4bc21d601f7d32b2b4190fe1ce4307d2a63d56821d61d99464dbd710b7476ee\",\"activation_sha256\":\"ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b\",\"binding_stream_sha256\":\"73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f\",\"calendar_commitment\":\"canonical_ASCII_NO_LF_rows_session_open_utc_close_utc_ISO_plus00:00\",\"calendar_source_sha256\":\"174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89\",\"daily_time_policy\":\"DailyPreciseEndTime_true_Time_open_EndTime_close_Period_close_minus_open\",\"first_session\":\"2020-12-31\",\"full_axis_count\":3466,\"full_binding_count\":6151,\"history\":\"one_fixed_typed_TradeBar_Daily_call_per_selected_original_symbol_RAW_noFF_regular_hours\",\"last_session\":\"2026-10-13\",\"maximum_history_calls\":5,\"ordered_full_axis_sha256\":\"4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585\",\"own_universe_tickers\":[\"SPY\",\"QQQ\",\"SOXX\",\"XLV\",\"REMX\",\"XLE\",\"XLI\",\"XLF\"],\"package_sha256\":\"1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2\",\"requested_session_count\":1452,\"schema\":\"arv2-r298-native-price-source-diagnostic-v1-specification\",\"security_master_admission_sha256\":\"5d0075cfe24cdfaaa56992de1d3b30bb4895d2495a8356ade47a4c3bc9dea281\",\"selected_whole_binding_sha256s\":[\"1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331\",\"b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8\",\"b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9\",\"c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7\",\"f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986\"],\"source_assignment\":\"exact_five_original_bindings_entire_window_same_all_six_cells_reference_AND_NAV\",\"source_scope\":\"availability_only_no_price_admission_or_Sharadar_refusal_clearance\"},\"source_summary\":{\"NYSE_schedule_sha256\":\"d4bc21d601f7d32b2b4190fe1ce4307d2a63d56821d61d99464dbd710b7476ee\",\"QC_raw_rows_exported_by_module\":false,\"QC_raw_rows_published_by_module\":false,\"binding_stream_sha256\":\"73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f\",\"calendar_source_sha256\":\"174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89\",\"complete_required_price_coverage_proven\":false,\"engine_price_cache_written_by_module\":false,\"enumeration_complete_count\":5,\"executable_quotes_substituted\":false,\"explicit_history_calls\":5,\"formal_forward_ready\":false,\"forward_census_sha256\":\"ca7aad8cfcb43e36e08df7071f07408bedc0e92fb61cc35f9d869c89fb476a79\",\"forward_duplicate_SID_identity_count\":0,\"forward_known_SID_count\":5121,\"forward_observation_count\":6151,\"forward_state_counts\":{\"known_US_equity\":5121,\"known_incompatible\":0,\"unavailable\":1030,\"unreadable\":0},\"forward_unknown_SID_count\":1030,\"full_catalog_own_ETF_collision_count\":0,\"historical_identity_proven\":false,\"identity_phase\":\"observed\",\"input_binding_count\":6151,\"named_refusal_count\":1030,\"ordered_full_axis_sha256\":\"4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585\",\"orders_submitted_by_module\":false,\"own_ETF_count\":8,\"package_sha256\":\"1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2\",\"paper_or_live_ready\":false,\"per_selected\":[{\"absent_cell_count\":1086,\"batch_count\":366,\"call_invoked\":true,\"duplicate_payload_count\":0,\"failure_unknown_cell_count\":0,\"invalid_or_duplicate_cell_count\":0,\"invalid_row_counts\":{},\"native_sid_sha256\":\"0c3bb0cf1b6eaa4b40707ceff530b3fb30d6cbfa4c03e1aae9ab5d3e88e4504e\",\"ordinal\":0,\"payload_count\":366,\"status\":\"complete\",\"unpriced_cell_count\":1086,\"valid_cell_count\":366,\"whole_binding_sha256\":\"1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331\"},{\"absent_cell_count\":1078,\"batch_count\":374,\"call_invoked\":true,\"duplicate_payload_count\":0,\"failure_unknown_cell_count\":0,\"invalid_or_duplicate_cell_count\":0,\"invalid_row_counts\":{},\"native_sid_sha256\":\"8a613accb7cf1108728dd6b9d8e9988960b2eab6dec0494cb24f3fc353326541\",\"ordinal\":1,\"payload_count\":374,\"status\":\"complete\",\"unpriced_cell_count\":1078,\"valid_cell_count\":374,\"whole_binding_sha256\":\"b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8\"},{\"absent_cell_count\":1195,\"batch_count\":257,\"call_invoked\":true,\"duplicate_payload_count\":0,\"failure_unknown_cell_count\":0,\"invalid_or_duplicate_cell_count\":0,\"invalid_row_counts\":{},\"native_sid_sha256\":\"039fc606e5798c9fd4650d3405f5fed132a1878dd38ca285429bdd5babe304b7\",\"ordinal\":2,\"payload_count\":257,\"status\":\"complete\",\"unpriced_cell_count\":1195,\"valid_cell_count\":257,\"whole_binding_sha256\":\"b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9\"},{\"absent_cell_count\":1077,\"batch_count\":375,\"call_invoked\":true,\"duplicate_payload_count\":0,\"failure_unknown_cell_count\":0,\"invalid_or_duplicate_cell_count\":0,\"invalid_row_counts\":{},\"native_sid_sha256\":\"70f76b9251e21fad88b2d9210bf9cabc69a849ae515ee6f2d9a9a5217ea71f76\",\"ordinal\":3,\"payload_count\":375,\"status\":\"complete\",\"unpriced_cell_count\":1077,\"valid_cell_count\":375,\"whole_binding_sha256\":\"c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7\"},{\"absent_cell_count\":113,\"batch_count\":1339,\"call_invoked\":true,\"duplicate_payload_count\":0,\"failure_unknown_cell_count\":0,\"invalid_or_duplicate_cell_count\":0,\"invalid_row_counts\":{},\"native_sid_sha256\":\"0cc9c2d313b8b3515b956cf8153fa5da8cbe581e1f357079a571f67c83f4ba88\",\"ordinal\":4,\"payload_count\":1339,\"status\":\"complete\",\"unpriced_cell_count\":113,\"valid_cell_count\":1339,\"whole_binding_sha256\":\"f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986\"}],\"permanent_security_master_proven\":false,\"point_in_time_proven\":false,\"private_book_byte_count\":1313871,\"private_book_sha256\":\"b149c9c659ef53084782e25ee18ffc4133bebb063180958651cafc69725c7299\",\"purpose\":\"QC_only_exact_five_original_identity_and_RAW_availability\",\"reference_or_NAV_price_input_admitted\":false,\"requested_session_count\":1452,\"required_cell_count\":7260,\"resolution_sha256\":\"ca6d1de45df7ada9c8c86df7fd0682fb31ef4a7573a92b0ced88c6cd5724825b\",\"resolved_count\":5121,\"schema\":\"arv2-r298-native-price-source-diagnostic-v1\",\"selected_count\":5,\"source_priority_admitted\":false,\"specification_sha256\":\"9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66\",\"terminal_payoff_proven\":false,\"unpriced_cell_count\":4549,\"valid_cell_count\":2711},\"publication\":{\"NAV_input_admitted\":false,\"atomic_create_proven\":false,\"attempt_consumed\":true,\"book_byte_count\":1313871,\"book_sha256\":\"b149c9c659ef53084782e25ee18ffc4133bebb063180958651cafc69725c7299\",\"failure_code\":null,\"formal_forward_ready\":false,\"historical_identity_proven\":false,\"independent_remote_durability_proven\":false,\"known_absent_observed\":true,\"object_key\":\"38522505/arv2/r326-native/13e90215fc380c2e286c541abf6d34fda6c77e3c01d999a352ea875110a358cc/b149c9c659ef53084782e25ee18ffc4133bebb063180958651cafc69725c7299\",\"paper_or_live_ready\":false,\"phase\":\"complete\",\"point_in_time_proven\":false,\"price_coverage_proven\":false,\"price_input_admitted\":false,\"publication_API_checks_complete\":true,\"raw_data_exported\":false,\"readback_equal\":true,\"save_returned_true\":true,\"schema\":\"arv2-r298-native-book-publication-v1-attempt\",\"scope_sha256\":\"13e90215fc380c2e286c541abf6d34fda6c77e3c01d999a352ea875110a358cc\",\"source_specification_sha256\":\"9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66\",\"source_summary_sha256\":\"88bac1c6d26fa32b92bae1f770f273d8858aae7588b3c1e1a83c8957327aeb7e\",\"whole_organization_integrity_proven\":false}}"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class Refused(ValueError):
    """Finite field predicate; never a price, identity, key or exception text."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def source_context():
    return validate_source_context(json.loads(_SOURCE_CONTEXT_JSON))


def _validate_supplied_context(value):
    """Pure bounded metadata validation; production adds its exact literal pin."""
    fields = {'schema', 'source_fact_sha256', 'source_project_id', 'source_backtest_id',
        'source_projection_sha256', 'source_profile_sha256', 'scope', 'specification',
        'source_summary', 'publication'}
    require(type(value) is dict and set(value) == fields and value['schema'] == CONTEXT_SCHEMA
        and type(value['source_project_id']) is int and value['source_project_id'] > 0
        and type(value['source_backtest_id']) is str
        and re.fullmatch('[0-9a-f]{32}', value['source_backtest_id']) is not None
        and all(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]) is not None
            for key in ('source_fact_sha256', 'source_projection_sha256', 'source_profile_sha256')), 'context')
    try:
        specification = native.validate_specification(value['specification'])
        summary = native.validate_summary(value['source_summary'])
        scope = publication.validate_scope(value['scope'])
        publication.validate_receipt(value['publication'], frozen_scope=scope,
            expected_specification=specification, expected_summary=summary)
        require(scope['own_project_id'] == value['source_project_id']
            and summary['specification_sha256'] == digest(specification)
            and summary['identity_phase'] == 'observed'
            and summary['full_catalog_own_ETF_collision_count'] == 0
            and summary['forward_duplicate_SID_identity_count'] == 0
            and [row['whole_binding_sha256'] for row in summary['per_selected']]
                == specification['selected_whole_binding_sha256s']
            and all(row['status'] == 'complete' and row['call_invoked'] is True
                for row in summary['per_selected']), 'context')
    except Refused:
        raise
    except Exception:
        raise Refused('context') from None
    return json.loads(canonical(value))


def validate_source_context(value):
    try:
        require(type(value) is dict and digest(value) == SOURCE_CONTEXT_SHA256, 'context')
        checked = _validate_supplied_context(value)
        require(checked['source_project_id'] == SOURCE_PROJECT_ID
            and digest(checked['source_summary']) == SOURCE_SUMMARY_SHA256
            and digest(checked['publication']) == SOURCE_PUBLICATION_SHA256
            and checked['publication']['book_byte_count'] == SOURCE_BOOK_BYTES
            and checked['publication']['book_sha256'] == SOURCE_BOOK_SHA256, 'context')
        return checked
    except Refused:
        raise
    except Exception:
        raise Refused('context') from None


def profile_record():
    return {'schema': SCHEMA, 'source_context_sha256': SOURCE_CONTEXT_SHA256,
        'AK_public_binding_source_sha256': AK_PUBLIC_BINDING_SHA256,
        'source_project_id': SOURCE_PROJECT_ID, 'source_book_byte_count': SOURCE_BOOK_BYTES,
        'source_book_sha256': SOURCE_BOOK_SHA256, 'source_summary_sha256': SOURCE_SUMMARY_SHA256,
        'source_publication_sha256': SOURCE_PUBLICATION_SHA256,
        'construction': 'inert_then_one_consumed_authentication_before_any_strategy_orders_or_holdings',
        'future_runtime_project_binding': 'exact_positive_integer_frozen_by_new_strategy_caller',
        'current_identity': 'fresh_genuine_full_original_binding_stream_forward_reverse_census_all8_ETFs_and_selected5',
        'native_identity_projection': ['sid', 'kind', 'market', 'sid_date'],
        'display_ticker': 'validated_observational_not_a_permanent_identity_key',
        'original_SIDs': 'absent_never_inferred_from_prior_totals_or_reused_without_current_resolution',
        'initial_subscriptions': 'selected5_RAW_Daily_only_before_strategy_quote_subscriptions',
        'later_guard': 'requested_current_native_identity_USD_rate1_RAW_and_NY_clock_not_permanent_no_orders',
        'source_read': 'one_exact_QC_ObjectStore_read_bytes_after_context_and_current_identity_no_key_enumeration',
        'authentication_order': 'fixed_byte_count_and_SHA256_before_JSON_then_closed_full_book_census_grid_originals',
        'lookup': 'exact_full_original_binding_and_session_RAW_USD_Decimal_only_five_fixed_whole_hashes',
        'calendar': 'independent_frozen_full_NYSE_schedule_equal_current_QC_schedule_before_any_lookup',
        'future_cells': 'requested_session_close_must_not_exceed_current_algorithm_NY_time',
        'unpriced': 'finite_stop_absent_invalid_or_duplicate_failure_unknown_no_scalar_or_other_source_fallback',
        'missing_cells': 'do_not_change_eligibility_or_holding_lifetime_and_do_not_drop_rows',
        'lookup_bound': MAX_LOOKUPS, 'authentication_seconds': MAX_AUTHENTICATION_SECONDS,
        'deadline_qualification': 'checks_cannot_interrupt_native_IO_or_engine_suspension',
        'source_read_cache': 'same_QC_ObjectStore_API_read_not_independent_remote_durability',
        'rights': 'separate_current_paid_private_org_actual_source_job_and_qualified_source_policy_required',
        'no_serializer_or_host_transport': True, **FALSE_FLAGS}


def stable_native_identity(value):
    """Validate full observations; ticker Value is metadata, never an ID key."""
    require(type(value) is dict and set(value) == {'sid', 'display', 'kind', 'market', 'sid_date'}
        and type(value['sid']) is str and native.figi._SID.fullmatch(value['sid']) is not None
        and type(value['display']) is str and native.figi._TICKER.fullmatch(value['display']) is not None
        and value['kind'] in ('equity', 'securitytype.equity') and value['market'] == 'usa'
        and type(value['sid_date']) is str, 'selected_identity')
    try:
        require(datetime.strptime(value['sid_date'], '%Y-%m-%d').date().isoformat() == value['sid_date'], 'selected_identity')
    except ValueError:
        raise Refused('selected_identity') from None
    return {key: value[key] for key in ('sid', 'kind', 'market', 'sid_date')}


def _parse_supplied_book(raw, context):
    """Pure closed parser used only after the caller authenticates its byte pin."""
    require(type(raw) is bytes and 0 < len(raw) <= native.MAX_PRIVATE_BYTES, 'source_bytes')
    try:
        record = publication._closed_json(raw)
        opaque = native.PrivateNativeBook(record)
        require(publication._book(opaque, context['source_summary']) == raw, 'source_record')
        return record
    except Refused:
        raise
    except Exception:
        raise Refused('source_record') from None


def _parse_fixed_book(raw, context):
    checked = validate_source_context(context)
    require(type(raw) is bytes and len(raw) == SOURCE_BOOK_BYTES
        and hashlib.sha256(raw).hexdigest() == SOURCE_BOOK_SHA256, 'source_bytes')
    return _parse_supplied_book(raw, checked)


def _join_original_catalog(record, rows, context):
    require(type(rows) is tuple and len(rows) == native.EXPECTED_BINDINGS
        and native.inputs._stream_hash(rows) == native.BINDING_STREAM_SHA256, 'catalog')
    census = record['forward_sid_census']
    require(len(census) == len(rows), 'catalog')
    for index, (row, observed) in enumerate(zip(rows, census, strict=True)):
        require(observed['binding_ordinal'] == index
            and observed['whole_binding_sha256'] == digest(row), 'catalog')
    originals = {digest(row): row for row in rows}
    selected = context['specification']['selected_whole_binding_sha256s']
    require(len(originals) == len(rows) and all(pin in originals for pin in selected), 'catalog')
    for row, pin in zip(record['selected'], selected, strict=True):
        require(row['original_binding'] == originals[pin], 'catalog')
    return {pin: originals[pin] for pin in selected}


class SpecificNativePriceBook:
    """Opaque QC-local point lookup; no raw getter, serializer or data export."""
    __slots__ = ('_algorithm', '_context_raw', '_context_sha', '_runtime_project', '_identity',
        '_started', '_active', '_deadline', '_bindings', '_symbols', '_natives', '_cells',
        '_missing', '_sessions', '_closes', '_lookups', '_receipt', '_raw_normalization')

    def __init__(self, algorithm, *, frozen_source_context, expected_context_sha256,
                 frozen_runtime_project_id, benchmark_symbol, etf_symbols, trade_bar_type,
                 daily_resolution, raw_normalization):
        checked = validate_source_context(frozen_source_context)
        require(type(expected_context_sha256) is str and expected_context_sha256 == SOURCE_CONTEXT_SHA256
            and digest(checked) == expected_context_sha256, 'context')
        require(type(frozen_runtime_project_id) is int and 0 < frozen_runtime_project_id <= 2147483647, 'project')
        require(str(daily_resolution).casefold() in ('daily', 'resolution.daily')
            and str(raw_normalization).casefold() in ('raw', 'datanormalizationmode.raw'), 'subscription')
        self._algorithm, self._runtime_project = algorithm, frozen_runtime_project_id
        self._context_raw, self._context_sha = canonical(checked), expected_context_sha256
        self._identity = native.NativePriceSourceDiagnostic(algorithm,
            specification=checked['specification'], expected_specification_sha256=digest(checked['specification']),
            activation_manifest_key=ACTIVATION[0], activation_manifest_sha256=ACTIVATION[1],
            activation_manifest_byte_count=ACTIVATION[2], benchmark_symbol=benchmark_symbol,
            etf_symbols=etf_symbols, trade_bar_type=trade_bar_type, daily_resolution=daily_resolution,
            raw_normalization=raw_normalization)
        self._started, self._active, self._deadline = False, False, None
        self._bindings, self._symbols, self._natives = {}, {}, {}
        self._cells, self._missing, self._sessions, self._closes = {}, {}, {}, {}
        self._lookups, self._receipt, self._raw_normalization = 0, None, raw_normalization
        self._base_guard()

    def __repr__(self):
        return '<SpecificNativePriceBook QC-local RAW data redacted; no export interface>'

    def __reduce_ex__(self, protocol):
        raise TypeError('QC-local native book cannot enter host serialization')

    def _remaining(self):
        require(type(self._deadline) in (int, float) and math.isfinite(self._deadline)
            and clock.monotonic() < self._deadline, 'deadline')

    def _base_guard(self):
        try:
            require(type(self._algorithm.project_id) is int
                and self._algorithm.project_id == self._runtime_project, 'project')
            require(self._algorithm.live_mode is False
                and str(self._algorithm.time_zone) == 'America/New_York'
                and self._algorithm.account_currency == 'USD'
                and self._algorithm.settings.daily_precise_end_time is True
                and self._algorithm.settings.seed_initial_prices is False, 'settings')
            require(hashlib.sha256(self._context_raw).hexdigest() == self._context_sha == SOURCE_CONTEXT_SHA256,
                'source_changed')
        except Refused:
            raise
        except Exception:
            raise Refused('settings') from None

    def _configure(self, symbol, schedule):
        """Reader-local initial subscription; stable identity, mapped labels.

        The already-used diagnostic remains unchanged. No History is invoked.
        All Daily/noFF/RAW/USD and independent-calendar checks are retained.
        """
        try:
            before = native._native(symbol)
            security = self._algorithm.add_security(symbol, self._identity.daily, False, 1, False)
            security.set_data_normalization_mode(self._raw_normalization)
            current = native._native(security.symbol)
            require(stable_native_identity(current) == stable_native_identity(before)
                and security.quote_currency.symbol == 'USD'
                and native.money._decimal(security.quote_currency.conversion_rate, 'native USD rate') == 1, 'currency')
            require(str(security.exchange.hours.time_zone) == 'America/New_York'
                and security.data_normalization_mode == self._raw_normalization, 'subscription')
            trade, quote = 0, 0
            for index, config in enumerate(security.subscriptions):
                require(index < 2 and stable_native_identity(native._native(config.symbol)) == stable_native_identity(before)
                    and config.resolution == self._identity.daily and config.fill_data_forward is False
                    and config.extended_market_hours is False and config.data_normalization_mode == self._raw_normalization
                    and str(config.data_time_zone) == str(config.exchange_time_zone) == 'America/New_York', 'subscription')
                name = config.type.FullName
                require(name in ('QuantConnect.Data.Market.TradeBar', 'QuantConnect.Data.Market.QuoteBar'), 'subscription')
                trade += int(name == 'QuantConnect.Data.Market.TradeBar')
                quote += int(name == 'QuantConnect.Data.Market.QuoteBar')
            require(trade == 1 and quote <= 1, 'subscription')
            for item in schedule:
                self._remaining()
                midnight = datetime.strptime(item['session'], '%Y-%m-%d')
                opening = native._qc_ny(security.exchange.hours.get_next_market_open(midnight, False))
                closing = native._qc_ny(security.exchange.hours.get_next_market_close(opening.replace(tzinfo=None), False))
                require(opening.astimezone(timezone.utc).isoformat() == item['open_utc']
                    and closing.astimezone(timezone.utc).isoformat() == item['close_utc'], 'calendar')
            return security.symbol, current
        except Refused: raise
        except Exception: raise Refused('subscription') from None

    def authenticate_once(self):
        require(not self._started, 'once')
        self._started = True
        self._deadline = clock.monotonic() + MAX_AUTHENTICATION_SECONDS
        self._identity.deadline = self._deadline
        try:
            self._base_guard(); self._identity._no_orders(); self._remaining()
            start_clock = native._qc_ny(self._algorithm.time)
            context = validate_source_context(json.loads(self._context_raw))
            package, rows, axis, sessions = self._identity._package()
            resolution = self._identity._resolve_with_census(rows)
            native.figi.require_preliminary_qc_figi_resolution(resolution)
            census = self._identity.forward_census
            require(len(census) == native.EXPECTED_BINDINGS, 'current_resolution')
            counts = Counter(row['native_sid'] for row in census if row['native_sid'] is not None)
            require(not any(count > 1 for count in counts.values()), 'current_collision')
            static = self._identity._static_securities(); self._identity.static_snapshot = dict(static)
            require(not any(row['native_sid'] in static for row in census if row['native_sid'] is not None),
                'current_collision')
            originals = {digest(row): row for row in rows}
            wanted = context['specification']['selected_whole_binding_sha256s']
            require(len(originals) == native.EXPECTED_BINDINGS and all(pin in originals for pin in wanted), 'catalog')
            schedule = self._identity._schedule(sessions)
            symbols, current = {}, {}
            for pin, public in zip(wanted, context['source_summary']['per_selected'], strict=True):
                self._remaining()
                symbol = resolution.symbol_for_security(originals[pin]['security_id'])
                require(symbol is not None, 'selected_identity')
                current_symbol, fact = self._configure(symbol, schedule)
                require(digest({'sid': fact['sid']}) == public['native_sid_sha256'], 'selected_identity')
                symbols[pin], current[pin] = current_symbol, fact
            self._remaining(); self._base_guard()
            try:
                payload = self._algorithm.object_store.read_bytes(context['publication']['object_key'])
                raw = publication._read_bytes(payload, SOURCE_BOOK_BYTES)
            except Exception:
                raise Refused('source_read_unknown') from None
            self._remaining()
            record = _parse_fixed_book(raw, context)
            require(record['session_schedule'] == schedule, 'calendar')
            chosen = _join_original_catalog(record, rows, context)
            for entry, pin in zip(record['selected'], wanted, strict=True):
                require(stable_native_identity(entry['native']) == stable_native_identity(current[pin])
                    and entry['status'] == 'complete', 'selected_identity')
                self._bindings[pin] = canonical(chosen[pin])
                self._symbols[pin], self._natives[pin] = symbols[pin], canonical(current[pin])
                self._cells[pin] = {index: text for index, text in entry['raw_USD_closes']}
                self._missing[pin] = {index: reason for index, reason in entry['unpriced_cells']}
            self._sessions = {row['session']: index for index, row in enumerate(schedule)}
            self._closes = {index: row['close_utc'] for index, row in enumerate(schedule)}
            self._identity._postcheck(package, resolution, start_clock,
                [(symbols[pin], current[pin]) for pin in wanted])
            self._remaining(); self._base_guard()
            self._receipt = {'schema': SCHEMA + '-receipt', 'runtime_project_id': self._runtime_project,
                'source_context_sha256': self._context_sha, 'source_project_id': SOURCE_PROJECT_ID,
                'source_book_byte_count': SOURCE_BOOK_BYTES, 'source_book_sha256': SOURCE_BOOK_SHA256,
                'source_summary_sha256': SOURCE_SUMMARY_SHA256,
                'fresh_input_binding_count': len(rows), 'fresh_binding_stream_sha256': native.BINDING_STREAM_SHA256,
                'fresh_forward_census_sha256': digest(census),
                'fresh_full_forward_reverse_resolution_sha256': resolution.resolution_sha256,
                'fresh_selected_native_identity_checked_count': len(wanted),
                'fresh_own_ETF_count': len(static), 'fresh_duplicate_SID_count': 0,
                'fresh_own_ETF_collision_count': 0, 'NYSE_schedule_sha256': digest(schedule),
                'original_native_SIDs_were_re_resolved_not_assumed': True,
                'same_job_ObjectStore_API_byte_pin_authenticated': True, **FALSE_FLAGS}
            self._active = True
            return self.receipt()
        except Refused:
            raise
        except native.Refused as error:
            code = native.finite(error)
            raise Refused(code if code in FINITE else 'current_resolution') from None
        except Exception:
            raise Refused('current_resolution') from None

    def _binding(self, value):
        require(self._active, 'state')
        self._base_guard()
        try:
            require(type(value) is dict, 'binding')
            row = native.figi._input_row(value, native.ADMISSION_SHA256)
            pin = digest(row)
            require(pin in self._bindings and canonical(row) == self._bindings[pin], 'binding')
            symbol = self._symbols[pin]
            current = native._native(symbol)
            require(stable_native_identity(current) == stable_native_identity(json.loads(self._natives[pin])), 'selected_identity')
            security = self._algorithm.securities[symbol]
            require(stable_native_identity(native._native(security.symbol)) == stable_native_identity(current)
                and security.quote_currency.symbol == 'USD'
                and native.money._decimal(security.quote_currency.conversion_rate, 'native USD rate') == 1,
                'currency')
            require(security.data_normalization_mode == self._raw_normalization, 'subscription')
            return pin, symbol
        except Refused:
            raise
        except Exception:
            raise Refused('binding') from None

    def symbol_for_binding(self, original_binding):
        return self._binding(original_binding)[1]

    def session_close(self, session):
        require(self._active, 'state')
        self._base_guard()
        require(type(session) is str and session in self._sessions, 'session')
        try:
            closing = datetime.fromisoformat(self._closes[self._sessions[session]])
            require(closing.tzinfo is not None, 'calendar')
            return closing.astimezone(native.NY)
        except Refused:
            raise
        except Exception:
            raise Refused('calendar') from None

    def price(self, original_binding, session):
        pin, _ = self._binding(original_binding)
        require(type(session) is str and session in self._sessions, 'session')
        require(self._lookups < MAX_LOOKUPS, 'lookup_bound')
        self._lookups += 1
        index = self._sessions[session]
        try:
            closing = datetime.fromisoformat(self._closes[index])
            now = native._qc_ny(self._algorithm.time).astimezone(timezone.utc)
            require(closing.tzinfo is not None and closing <= now, 'future_session')
        except Refused:
            raise
        except Exception:
            raise Refused('session') from None
        if index in self._missing[pin]:
            reason = self._missing[pin][index]
            raise Refused(reason if reason in ('absent', 'invalid_or_duplicate', 'failure_unknown') else 'source_record')
        require(index in self._cells[pin], 'source_record')
        return native.money._decimal(self._cells[pin][index], 'native RAW USD close', positive=True)

    def receipt(self):
        require(self._active and type(self._receipt) is dict, 'state')
        return json.loads(canonical(self._receipt))
