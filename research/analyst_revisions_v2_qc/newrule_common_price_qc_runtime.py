"""Pure common-source reference and NAV component for a future QC driver.

No deployment, source admission, vendor upload or trading authority is provided.
The frozen quote-aware strategy driver remains unchanged. Its future concrete
successor must supply actual complete QC cash/holdings snapshots and preserve
all construction, split, order, fee and forced-exit checks.
"""
import hashlib
import json
from collections import Counter
from datetime import datetime, time
from decimal import Decimal, localcontext
from types import FunctionType, MappingProxyType, MethodType
from zoneinfo import ZoneInfo

try:
    import newrule_native_price_source_diagnostic as native
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as native

SCHEMA = 'arv2-r298-common-price-monetary-component-v1'
FUND_SCHEMA = SCHEMA + '-own-fund'
NATIVE_SPECIFICATION_SHA256 = '9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66'
MAX_CENSUS, MAX_RECEIPT_BYTES = 256, 32768
NY = ZoneInfo('America/New_York')
FALSE_FLAGS = {'source_admission_granted': False, 'vendor_QC_transfer_granted': False,
    'actual_QC_snapshot_proven_by_pure_component': False, 'strategy_result_accepted': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('provider_unavailable', 'provider_type', 'provider_method', 'provider_authentication',
    'provider_receipt', 'provider_changed', 'once', 'not_authenticated', 'catalog', 'fund', 'axis',
    'specification', 'identity', 'runtime_identity', 'session', 'calendar', 'clock', 'census',
    'quantity', 'cash', 'price_missing_or_unknown', 'price', 'valuation', 'repeated_close', 'unknown'))


class Refused(ValueError):
    """Finite stop; never prices, rows, identifiers or raw exception messages."""


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


def profile_record():
    return {'schema': SCHEMA, 'native_specification_sha256': NATIVE_SPECIFICATION_SHA256,
        'stock_binding_stream_sha256': native.BINDING_STREAM_SHA256,
        'full_stock_binding_count': native.EXPECTED_BINDINGS,
        'own_funds': list(native.UNIVERSES), 'whole_original_binding_source_choice': 'exact_native_five_else_exact_vendor_no_fallback',
        'provider_types': ['newrule_native_price_book_runtime.SpecificNativePriceBook',
            'newrule_raw_vendor_price_book_runtime.SpecificVendorPriceBook'],
        'provider_authentication': 'concrete_once_readers_revalidate_their_source_contexts_no_callback_or_permission_switch',
        'reference': 'target_union_all_actual_positive_whole_holdings_immediately_prior_NYSE_RAW_USD_close_at0920',
        'split_bridge': 'future_frozen_driver_keeps_one_typed_split_History_per_decision_and_applies_same_day_factor_once',
        'NAV': 'Decimal96_actual_QC_cash_plus_actual_positive_whole_quantity_times_same_session_RAW_USD_mark',
        'gross': 'same_RAW_marked_holdings_value_divided_by_positive_authoritative_NAV',
        'cash_actions': 'QC_cash_already_contains_actual_fees_dividends_actions_no_double_credit_or_debit',
        'expiry': 'no_membership_binding_metadata_or_price_end_closes_a_positive_position',
        'payoff': 'future_driver_requires_authenticated_actual_signed_fill_and_engine_zero_not_source_absence',
        'missing': 'stop_no_scalar_quote_cache_stale_fallback_row_drop_or_eligibility_preselection',
        'engine_NAV': 'optional_diagnostic_not_authoritative_and_never_a_price_fallback',
        'repeated_close': 'cash_complete_positive_holdings_RAW_marks_NAV_gross_must_be_identical',
        'counters': 'actual_source_attempts_and_completions_reference_and_close_batches_never_fake_QC_History_calls',
        'maximum_positive_census': MAX_CENSUS,
        'integration': 'future_exact_quote_aware_BaseDriver_alias_and_new_profile_result_contract_required',
        **FALSE_FLAGS}


def fund_contracts():
    return tuple({'schema': FUND_SCHEMA, 'ticker': ticker} for ticker in native.UNIVERSES)


def _provider_types():
    try:
        try:
            from newrule_native_price_book_runtime import SpecificNativePriceBook
        except ImportError:
            from research.analyst_revisions_v2_qc.newrule_native_price_book_runtime import SpecificNativePriceBook
        try:
            from newrule_raw_vendor_price_book_runtime import SpecificVendorPriceBook
        except ImportError:
            from research.analyst_revisions_v2_qc.newrule_raw_vendor_price_book_runtime import SpecificVendorPriceBook
        return SpecificNativePriceBook, SpecificVendorPriceBook
    except ImportError:
        raise Refused('provider_unavailable') from None


def _method(value, name):
    method = getattr(value, name, None)
    expected = getattr(type(value), name, None)
    require(type(method) is MethodType and method.__self__ is value
        and type(expected) is FunctionType and method.__func__ is expected, 'provider_method')
    return method


def _instant(value):
    require(isinstance(value, datetime), 'clock')
    return value.replace(tzinfo=NY) if value.tzinfo is None else value.astimezone(NY)


def _number(value, code):
    try:
        return native.money._decimal(value, 'common monetary input')
    except Exception:
        raise Refused(code) from None


class SpecificCommonPriceBook:
    """Specific source composition; no caller-provided prices or callbacks.

    The vendor reader is an intentionally missing dependency until a separate
    QC-local transfer/admission implementation and exact run freeze exist.
    Synthetic tests patch the private type resolver; production has no bypass.
    """
    def __init__(self, native_book, vendor_book, *, stock_bindings, own_fund_contracts,
                 session_axis, native_specification):
        types = _provider_types()
        require(type(types) is tuple and len(types) == 2 and type(native_book) is types[0]
            and type(vendor_book) is types[1], 'provider_type')
        self._native, self._vendor, self._types = native_book, vendor_book, types
        for book in (native_book, vendor_book):
            for name in ('authenticate_once', 'price', 'receipt', 'symbol_for_binding'):
                _method(book, name)
        _method(native_book, 'session_close'); _method(vendor_book, 'symbol_for_fund')
        self._method_fingerprints = tuple((book, name, _method(book, name).__func__)
            for book, names in ((native_book, ('authenticate_once', 'price', 'receipt', 'symbol_for_binding', 'session_close')),
                (vendor_book, ('authenticate_once', 'price', 'receipt', 'symbol_for_binding', 'symbol_for_fund')))
            for name in names)
        try:
            spec = native.validate_specification(native_specification)
            require(digest(spec) == NATIVE_SPECIFICATION_SHA256, 'specification')
            require(type(stock_bindings) is tuple and len(stock_bindings) == native.EXPECTED_BINDINGS
                and native.inputs._stream_hash(stock_bindings) == native.BINDING_STREAM_SHA256, 'catalog')
            normalized = tuple(native.figi._input_row(row, native.ADMISSION_SHA256) for row in stock_bindings)
            require(normalized == stock_bindings
                and tuple(sorted(normalized, key=lambda row: row['security_id'])) == normalized
                and len({row['security_id'] for row in normalized}) == native.EXPECTED_BINDINGS, 'catalog')
            require(type(own_fund_contracts) is tuple and own_fund_contracts == fund_contracts(), 'fund')
            require(type(session_axis) is tuple and len(session_axis) == native.EXPECTED_AXIS_COUNT
                and session_axis == tuple(sorted(set(session_axis)))
                and digest(list(session_axis)) == native.AXIS_SHA256, 'axis')
        except Refused:
            raise
        except Exception:
            raise Refused('catalog') from None
        stocks = {row['security_id']: canonical(row) for row in normalized}
        funds = {'own-etf-' + row['ticker']: canonical(row) for row in own_fund_contracts}
        require(set(stocks).isdisjoint(funds), 'catalog')
        self._stocks, self._funds = MappingProxyType(stocks), MappingProxyType(funds)
        self._native_pins = frozenset(spec['selected_whole_binding_sha256s'])
        require(self._native_pins <= {digest(row) for row in normalized}, 'specification')
        self._axis, self._positions = session_axis, MappingProxyType({s: i for i, s in enumerate(session_axis)})
        self._specification_sha256 = digest(spec)
        self._started = self._ready = False
        self._receipts = None
        self._counts = Counter()

    def _guard(self):
        require(type(self._native) is self._types[0] and type(self._vendor) is self._types[1], 'provider_changed')
        require(all(_method(book, name).__func__ is function for book, name, function in self._method_fingerprints),
            'provider_changed')
        for book in (self._native, self._vendor):
            for name in ('price', 'receipt', 'symbol_for_binding'):
                _method(book, name)
        _method(self._native, 'session_close'); _method(self._vendor, 'symbol_for_fund')

    def authenticate_once(self):
        require(not self._started, 'once')
        self._started = True
        self._guard()
        try:
            for book in (self._native, self._vendor):
                _method(book, 'authenticate_once')()
            receipts = []
            for book in (self._native, self._vendor):
                value = _method(book, 'receipt')()
                raw = canonical(value)
                require(type(value) is dict and 0 < len(raw) <= MAX_RECEIPT_BYTES, 'provider_receipt')
                receipts.append({'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            self._receipts = tuple(receipts)
            self._ready = True
            return self.receipt()
        except Refused:
            self._ready = False
            raise
        except Exception:
            self._ready = False
            raise Refused('provider_authentication') from None

    def require_identity(self, identity):
        require(type(identity) is str and (identity in self._stocks or identity in self._funds), 'identity')

    def previous_session(self, decision_session):
        require(type(decision_session) is str and decision_session in self._positions
            and self._positions[decision_session] > 0, 'session')
        return self._axis[self._positions[decision_session] - 1]

    def session_close(self, session):
        require(self._ready, 'not_authenticated'); self._guard()
        require(type(session) is str and session in self._positions
            and native.FIRST_SESSION <= session <= native.LAST_SESSION, 'session')
        try:
            value = _method(self._native, 'session_close')(session)
            require(isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None,
                'calendar')
            closing = _instant(value)
            require(closing.date().isoformat() == session and time(13) <= closing.time().replace(tzinfo=None) <= time(16),
                'calendar')
            return closing
        except Refused:
            raise
        except Exception:
            raise Refused('calendar') from None

    def price(self, identity, session, *, runtime_symbol):
        require(self._ready, 'not_authenticated'); self._guard(); self.require_identity(identity)
        self.session_close(session)
        contract = json.loads(self._stocks[identity] if identity in self._stocks else self._funds[identity])
        native_source = identity in self._stocks and digest(contract) in self._native_pins
        book = self._native if native_source else self._vendor
        source = 'native' if native_source else 'vendor'
        try:
            self._counts[source + '_identity_check_attempts'] += 1
            expected_symbol = (_method(book, 'symbol_for_binding')(contract) if identity in self._stocks
                else _method(book, 'symbol_for_fund')(contract))
            expected = native.figi._symbol_identity(expected_symbol, 'common expected symbol')
            actual = native.figi._symbol_identity(runtime_symbol, 'common runtime symbol')
            require(expected[0] == actual[0] and expected[2] == actual[2]
                and expected[2] in ('equity', 'securitytype.equity') and expected[3] == actual[3] == 'usa',
                'runtime_identity')
            self._counts[source + '_identity_check_completed'] += 1
            self._counts[source + '_price_lookup_attempts'] += 1
            value = _method(book, 'price')(contract, session)
            require(type(value) is Decimal and value.is_finite() and value > 0, 'price')
            self._counts[source + '_price_lookup_completed'] += 1
            return value
        except Refused:
            raise
        except Exception:
            raise Refused('price_missing_or_unknown') from None

    def receipt(self):
        require(self._ready, 'not_authenticated'); self._guard()
        return {'schema': SCHEMA + '-source-observation', 'specification_sha256': self._specification_sha256,
            'binding_stream_sha256': native.BINDING_STREAM_SHA256,
            'native_receipt': dict(self._receipts[0]), 'vendor_receipt': dict(self._receipts[1]),
            'lookup_counts': {source + '_' + event: self._counts[source + '_' + event]
                for source in ('native', 'vendor') for event in ('identity_check_attempts', 'identity_check_completed',
                    'price_lookup_attempts', 'price_lookup_completed')}, **FALSE_FLAGS}


class CommonPriceLedger:
    """Decimal96 reference and actual-snapshot valuation, never engine prices."""
    def __init__(self, source):
        require(type(source) is SpecificCommonPriceBook, 'provider_type')
        source.receipt()
        self._source, self._reference_events, self._closes = source, [], {}
        self._counts, self._engine_diagnostics = Counter(), []

    def _holdings(self, value):
        require(type(value) is dict and len(value) <= native.EXPECTED_BINDINGS + len(native.UNIVERSES), 'census')
        result = {}
        for identity, quantity in value.items():
            number = _number(quantity, 'quantity')
            require(number >= 0 and number == number.to_integral_value(), 'quantity')
            if number == 0: continue
            self._source.require_identity(identity)
            result[identity] = int(number)
        require(len(result) <= MAX_CENSUS, 'census')
        return result

    @staticmethod
    def _symbols(value, identities):
        require(type(value) is dict and set(value) == set(identities), 'runtime_identity')

    def reference_prices(self, prior_session, target_ids, holdings, runtime_symbols, *, now):
        observed = _instant(now)
        require(observed.time().replace(tzinfo=None) == time(9, 20)
            and prior_session == self._source.previous_session(observed.date().isoformat())
            and self._source.session_close(prior_session) < observed, 'clock')
        require(type(target_ids) is tuple and all(type(value) is str for value in target_ids)
            and target_ids == tuple(sorted(set(target_ids)))
            and 0 < len(target_ids) <= MAX_CENSUS, 'census')
        positive = self._holdings(holdings)
        ids = tuple(sorted(set(target_ids) | set(positive)))
        require(0 < len(ids) <= MAX_CENSUS, 'census')
        self._symbols(runtime_symbols, ids)
        self._counts['reference_batch_attempts'] += 1
        prices = {identity: self._source.price(identity, prior_session, runtime_symbol=runtime_symbols[identity]) for identity in ids}
        self._reference_events.append(digest({'decision_session': observed.date().isoformat(),
            'prior_session': prior_session, 'targets': list(target_ids), 'positive_holdings': sorted(positive.items()),
            'RAW_USD_prices': sorted((identity, str(value)) for identity, value in prices.items())}))
        self._counts['reference_batch_completed'] += 1
        return prices

    def observe_close(self, session, *, cash, holdings, runtime_symbols, now, engine_nav=None):
        observed = _instant(now)
        require(observed.date().isoformat() == session and observed >= self._source.session_close(session), 'clock')
        actual_cash = _number(cash, 'cash'); require(actual_cash >= 0, 'cash')
        positive = self._holdings(holdings)
        self._symbols(runtime_symbols, positive)
        self._counts['close_batch_attempts'] += 1
        prices = {identity: self._source.price(identity, session, runtime_symbol=runtime_symbols[identity])
            for identity in sorted(positive)}
        try:
            with localcontext() as arithmetic:
                arithmetic.prec = 96
                holdings_value = sum((Decimal(quantity) * prices[identity] for identity, quantity in positive.items()), Decimal(0))
                nav = actual_cash + holdings_value
                require(nav.is_finite() and nav > 0 and holdings_value.is_finite() and holdings_value >= 0, 'valuation')
                gross = holdings_value / nav
        except Refused:
            raise
        except Exception:
            raise Refused('valuation') from None
        record = {'cash': str(actual_cash), 'positive_whole_holdings': sorted(positive.items()),
            'same_session_RAW_USD_marks': sorted((identity, str(value)) for identity, value in prices.items()),
            'NAV': str(nav), 'gross': str(gross)}
        if session in self._closes:
            require(self._closes[session] == record, 'repeated_close')
        else:
            self._closes[session] = record
        try:
            diagnostic = _number(engine_nav, 'valuation') if engine_nav is not None else None
            diagnostic = str(diagnostic) if diagnostic is not None else None
        except Refused:
            diagnostic = None
        self._engine_diagnostics.append(digest({'session': session, 'engine_NAV_diagnostic': diagnostic}))
        self._counts['close_batch_completed'] += 1
        return nav, gross

    def summary(self):
        return {'schema': SCHEMA + '-ledger', 'source_observation': self._source.receipt(),
            'counts': {key: self._counts[key] for key in ('reference_batch_attempts', 'reference_batch_completed',
                'close_batch_attempts', 'close_batch_completed')},
            'reference_path_sha256': digest(self._reference_events),
            'authoritative_close_path_sha256': digest(sorted(self._closes.items())),
            'unique_close_count': len(self._closes), 'engine_NAV_diagnostic_path_sha256': digest(self._engine_diagnostics),
            'reference_QC_History_calls_by_component': 0, 'split_QC_History_calls_by_component': 0, **FALSE_FLAGS}
