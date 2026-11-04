"""R337 exact-quarantine vendor-only RAW reference and NAV component.

The calendar/identity bridge and vendor reader are concrete genuine consumers;
there is no native-five price book, caller-supplied price callback or fallback.
Exact five denied bindings and every unsupported conditional/unknown demand
stop before prices. Ledger arithmetic and clocks preserve the frozen monetary
component. Research qualification never establishes formal source admission.
"""
import hashlib
import json
from collections import Counter
from datetime import datetime, time
from decimal import Decimal, localcontext
from types import FunctionType, MappingProxyType, MethodType
from subprocess import TimeoutExpired
from zoneinfo import ZoneInfo

try:
    import newrule_native_price_source_diagnostic as native
    import newrule_common_price_format as vendor_format
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as native
    from research.analyst_revisions_v2_qc import newrule_common_price_format as vendor_format

SCHEMA = 'arv2-r337-five-case-quarantine-monetary-v1'
FUND_SCHEMA = 'arv2-r298-common-price-monetary-component-v1-own-fund'
MAX_CENSUS, MAX_RECEIPT_BYTES = 256, 32768
NY = ZoneInfo('America/New_York')
FALSE_FLAGS = {'source_admission_granted': False, 'vendor_QC_transfer_granted': False,
    'actual_QC_snapshot_proven_by_pure_component': False, 'strategy_result_accepted': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('provider_unavailable', 'provider_type', 'provider_method', 'provider_authentication',
    'provider_receipt', 'provider_changed', 'once', 'not_authenticated', 'catalog', 'fund', 'axis',
    'specification', 'identity', 'runtime_identity', 'session', 'calendar', 'clock', 'census',
    'quantity', 'cash', 'quarantine', 'deadline', 'price_missing_or_unknown', 'price', 'valuation', 'repeated_close', 'unknown'))


class Refused(ValueError):
    """Finite stop; never prices, rows, identifiers or raw exception messages."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _preserve_deadline(error):
    """Preserve only exact known timeout classes/codes across component guards.

    This imports a stdlib exception class only; no process is created. Error
    messages, causes, callback properties and arbitrary subclasses are unread.
    """
    if type(error) in (TimeoutError, TimeoutExpired):
        raise Refused('deadline') from None
    if type(error) is vendor_format.Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] == 'deadline':
            raise Refused('deadline') from None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


try:
    import newrule_five_case_quarantine_targets as quarantine
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_targets as quarantine

RESEARCH_EPOCH_ID = quarantine.RESEARCH_EPOCH_ID


def profile_record():
    return {'schema': SCHEMA, 'research_epoch_id': RESEARCH_EPOCH_ID,
        'quarantine_policy_sha256': digest(quarantine.profile_record()),
        'stock_binding_stream_sha256': native.BINDING_STREAM_SHA256,
        'full_stock_binding_count': native.EXPECTED_BINDINGS,
        'own_funds': list(native.UNIVERSES), 'own_fund_schema': FUND_SCHEMA,
        'source_choice': 'unchanged_vendor_only_5636_nonquarantine_and_eight_funds_conditional510_hard_stop',
        'quarantine': 'exact_five_original_whole_bindings_denied_before_price_target_order_or_held_position',
        'native_price_book_initialized': False, 'native_price_book_reads': 0,
        'provider_types': ['IdentityCalendarBridge', 'SpecificQuarantineVendorPriceBook'],
        'reference': 'target_union_all_actual_positive_whole_holdings_immediately_prior_NYSE_RAW_USD_close_at0920',
        'NAV': 'Decimal96_actual_QC_cash_plus_actual_positive_whole_quantity_times_same_session_RAW_USD_mark',
        'gross': 'same_RAW_marked_holdings_value_divided_by_positive_authoritative_NAV',
        'cash_actions': 'actual_QC_cash_no_double_credit_or_debit',
        'expiry': 'no_membership_metadata_or_price_end_liquidation',
        'missing': 'hard_stop_no_fallback_row_drop_quote_substitution_or_renormalization',
        'fresh_epoch': 'USD1000000_empty_positions_empty_orders_no_imaginary_quarantine_liquidation',
        'source_identity': 'genuine_full6151_package_and_resolution_same_objects_and_exact_quarantine_catalog',
        'maximum_positive_census': MAX_CENSUS,
        'failure_taxonomy': 'exact_vendor_format_deadline_or_exact_stdlib_TimeoutError_TimeoutExpired_preserved_before_method_error_wrapping',
        **FALSE_FLAGS}


def fund_contracts():
    return tuple({'schema': FUND_SCHEMA, 'ticker': ticker} for ticker in native.UNIVERSES)


def _provider_types():
    try:
        try:
            from newrule_five_case_quarantine_vendor_book import IdentityCalendarBridge, SpecificQuarantineVendorPriceBook
        except ImportError:
            from research.analyst_revisions_v2_qc.newrule_five_case_quarantine_vendor_book import IdentityCalendarBridge, SpecificQuarantineVendorPriceBook
        return IdentityCalendarBridge, SpecificQuarantineVendorPriceBook
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


class SpecificQuarantinePriceBook:
    """Concrete vendor-only source; the denied five have no price fallback."""
    def __init__(self, identity_bridge, vendor_book, *, stock_bindings, own_fund_contracts,
                 session_axis, quarantine_catalog, expected_quarantine_catalog_sha256):
        types = _provider_types()
        require(type(types) is tuple and len(types) == 2 and type(identity_bridge) is types[0]
            and type(vendor_book) is types[1], 'provider_type')
        self._bridge, self._vendor, self._types = identity_bridge, vendor_book, types
        self._providers = (identity_bridge, vendor_book)
        require(vendor_book._native is identity_bridge, 'provider_type')
        names = ((identity_bridge, ('receipt', 'symbol_for_binding', 'session_close', 'no_orders')),
            (vendor_book, ('authenticate_once', 'price', 'receipt', 'symbol_for_binding', 'symbol_for_fund')))
        self._method_fingerprints = tuple((book, name, _method(book, name).__func__)
            for book, methods in names for name in methods)
        try:
            checked = quarantine.validate_quarantine_catalog(quarantine_catalog,
                expected_sha256=expected_quarantine_catalog_sha256)
            require(quarantine.make_quarantine_catalog(stock_bindings) == checked, 'catalog')
            require(type(own_fund_contracts) is tuple and own_fund_contracts == fund_contracts(), 'fund')
            require(type(session_axis) is tuple and len(session_axis) == native.EXPECTED_AXIS_COUNT
                and session_axis == tuple(sorted(set(session_axis)))
                and digest(list(session_axis)) == native.AXIS_SHA256, 'axis')
        except Refused:
            raise
        except Exception:
            raise Refused('catalog') from None
        stocks = {row['security_id']: canonical(row) for row in stock_bindings}
        funds = {'own-etf-' + row['ticker']: canonical(row) for row in own_fund_contracts}
        require(len(stocks) == native.EXPECTED_BINDINGS and set(stocks).isdisjoint(funds), 'catalog')
        self._stocks, self._funds = MappingProxyType(stocks), MappingProxyType(funds)
        self._denied_ids = frozenset(quarantine.denied_security_ids(checked,
            expected_sha256=expected_quarantine_catalog_sha256))
        require(len(self._denied_ids) == 5 and self._denied_ids <= set(stocks), 'catalog')
        self._catalog_raw, self._catalog_sha = canonical(checked), expected_quarantine_catalog_sha256
        self._axis, self._positions = session_axis, MappingProxyType({s: i for i, s in enumerate(session_axis)})
        self._started = self._ready = False
        self._receipts = None
        self._counts = Counter()

    def _guard(self):
        require(self._bridge is self._providers[0] and self._vendor is self._providers[1]
            and type(self._bridge) is self._types[0] and type(self._vendor) is self._types[1]
            and self._vendor._native is self._bridge, 'provider_changed')
        require(all(_method(book, name).__func__ is function for book, name, function in self._method_fingerprints),
            'provider_changed')

    def authenticate_once(self):
        require(not self._started, 'once'); self._started = True; self._guard()
        try:
            bridge = _method(self._bridge, 'receipt')()
            require(type(bridge) is dict and bridge.get('quarantine_epoch') == RESEARCH_EPOCH_ID
                and bridge.get('quarantine_catalog_sha256') == self._catalog_sha
                and bridge.get('fresh_binding_stream_sha256') == native.BINDING_STREAM_SHA256
                and bridge.get('fresh_input_binding_count') == native.EXPECTED_BINDINGS
                and type(bridge.get('fresh_input_binding_count')) is int
                and bridge.get('native_price_book_initialized') is False
                and type(bridge.get('native_price_book_reads')) is int
                and bridge['native_price_book_reads'] == 0, 'provider_receipt')
            _method(self._vendor, 'authenticate_once')()
            receipts = []
            for value in (bridge, _method(self._vendor, 'receipt')()):
                raw = canonical(value)
                require(type(value) is dict and 0 < len(raw) <= MAX_RECEIPT_BYTES, 'provider_receipt')
                receipts.append({'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            self._receipts = tuple(receipts); self._ready = True
            return self.receipt()
        except Refused:
            self._ready = False; raise
        except Exception as error:
            self._ready = False
            _preserve_deadline(error)
            raise Refused('provider_authentication') from None

    def require_identity(self, identity):
        require(self._ready, 'not_authenticated'); self._guard()
        require(type(identity) is str and (identity in self._stocks or identity in self._funds), 'identity')
        require(identity not in self._denied_ids, 'quarantine')
        contract = json.loads(self._stocks[identity] if identity in self._stocks else self._funds[identity])
        try:
            # This validates vendor assignment before any subscription or price request.
            # A conditional/nonvendor role is a hard stop, never an ETF transfer.
            return (_method(self._vendor, 'symbol_for_binding')(contract) if identity in self._stocks
                else _method(self._vendor, 'symbol_for_fund')(contract))
        except Exception as error:
            _preserve_deadline(error)
            raise Refused('identity') from None

    def previous_session(self, decision_session):
        require(type(decision_session) is str and decision_session in self._positions
            and self._positions[decision_session] > 0, 'session')
        return self._axis[self._positions[decision_session] - 1]

    def session_close(self, session):
        require(self._ready, 'not_authenticated'); self._guard()
        require(type(session) is str and session in self._positions
            and native.FIRST_SESSION <= session <= native.LAST_SESSION, 'session')
        try:
            value = _method(self._bridge, 'session_close')(session)
            require(isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None,
                'calendar')
            closing = _instant(value)
            require(closing.date().isoformat() == session and time(13) <= closing.time().replace(tzinfo=None) <= time(16),
                'calendar')
            return closing
        except Refused:
            raise
        except Exception as error:
            _preserve_deadline(error)
            raise Refused('calendar') from None

    def price(self, identity, session, *, runtime_symbol):
        require(self._ready, 'not_authenticated'); self._guard()
        self._counts['vendor_identity_check_attempts'] += 1
        expected_symbol = self.require_identity(identity)
        self.session_close(session)
        try:
            expected = native.figi._symbol_identity(expected_symbol, 'quarantine expected symbol')
            actual = native.figi._symbol_identity(runtime_symbol, 'quarantine runtime symbol')
            require(expected[0] == actual[0] and expected[2] == actual[2]
                and expected[2] in ('equity', 'securitytype.equity') and expected[3] == actual[3] == 'usa',
                'runtime_identity')
            self._counts['vendor_identity_check_completed'] += 1
            self._counts['vendor_price_lookup_attempts'] += 1
            contract = json.loads(self._stocks[identity] if identity in self._stocks else self._funds[identity])
            value = _method(self._vendor, 'price')(contract, session)
            require(type(value) is Decimal and value.is_finite() and value > 0, 'price')
            self._counts['vendor_price_lookup_completed'] += 1
            return value
        except Refused:
            raise
        except Exception as error:
            _preserve_deadline(error)
            raise Refused('price_missing_or_unknown') from None

    def receipt(self):
        require(self._ready, 'not_authenticated'); self._guard()
        return {'schema': SCHEMA + '-source-observation', 'research_epoch_id': RESEARCH_EPOCH_ID,
            'quarantine_catalog_sha256': self._catalog_sha,
            'quarantine_policy_sha256': digest(quarantine.profile_record()),
            'binding_stream_sha256': native.BINDING_STREAM_SHA256,
            'full_stock_binding_count': native.EXPECTED_BINDINGS,
            'bridge_receipt': dict(self._receipts[0]), 'vendor_receipt': dict(self._receipts[1]),
            'native_price_book_initialized': False, 'native_price_book_reads': 0,
            'lookup_counts': {source + '_' + event: self._counts[source + '_' + event]
                for source in ('native', 'vendor') for event in ('identity_check_attempts', 'identity_check_completed',
                    'price_lookup_attempts', 'price_lookup_completed')}, **FALSE_FLAGS}


class QuarantinePriceLedger:
    """Decimal96 reference and actual-snapshot valuation, never engine prices."""
    def __init__(self, source):
        require(type(source) is SpecificQuarantinePriceBook, 'provider_type')
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
