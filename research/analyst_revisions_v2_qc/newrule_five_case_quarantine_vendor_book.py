"""Quarantine-only successor over unchanged authenticated vendor payload bytes.

The concrete bridge reuses the strategy's genuine loaded package and full
resolution. It reads no native price book, package, History or provider data.
Exact five bindings are unavailable to symbol and monetary lookup; the complete
original catalog remains present. Research quarantine is not identity admission.
"""
from collections import OrderedDict
from datetime import datetime, time as daytime, timezone
from decimal import Decimal
import json
import time

try:
    import newrule_common_price_format as fmt
    import newrule_native_price_source_diagnostic as native
    import newrule_native_price_book_publication as publication
    import newrule_five_case_quarantine_targets as quarantine
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_common_price_format as fmt
    from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as native
    from research.analyst_revisions_v2_qc import newrule_native_price_book_publication as publication
    from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_targets as quarantine

SCHEMA = 'arv2-r337-five-case-quarantine-vendor-runtime-v1'
BRIDGE_SCHEMA = SCHEMA + '-identity-calendar'
FUND_SCHEMA = 'arv2-r298-common-price-monetary-component-v1-own-fund'
Refused, require = fmt.Refused, fmt.require
canonical, digest = fmt.canonical, fmt.digest
MAX_LOOKUPS, MAX_CACHED_MONTHS = 300000, 2
MAX_AUTHENTICATION_SECONDS, MAX_MONTH_READ_SECONDS = 300, 30
FINITE = fmt.FINITE | frozenset(('project', 'settings', 'package', 'resolution',
    'quarantine', 'orders', 'calendar', 'currency', 'identity', 'once', 'not_ready'))
QUARANTINED_WHOLES = frozenset((
    'f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986',
    'b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8',
    'c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7',
    '1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331',
    'b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9'))


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def stable_native_identity(value):
    require(type(value) is dict and set(value) == {'sid', 'display', 'kind', 'market', 'sid_date'}
        and type(value['sid']) is str and native.figi._SID.fullmatch(value['sid']) is not None
        and type(value['display']) is str and native.figi._TICKER.fullmatch(value['display']) is not None
        and value['kind'] in ('equity', 'securitytype.equity') and value['market'] == 'usa'
        and type(value['sid_date']) is str, 'identity')
    try:
        require(datetime.strptime(value['sid_date'], '%Y-%m-%d').date().isoformat() == value['sid_date'], 'identity')
    except ValueError:
        raise Refused('identity') from None
    return {key: value[key] for key in ('sid', 'kind', 'market', 'sid_date')}


def _catalog(value, expected_sha256, rows):
    require(type(expected_sha256) is str and fmt.hash_string(expected_sha256), 'quarantine')
    try:
        checked = quarantine.validate_quarantine_catalog(value, expected_sha256=expected_sha256)
        require(checked == quarantine.make_quarantine_catalog(rows), 'quarantine')
        denied = quarantine.denied_security_ids(checked, expected_sha256=expected_sha256)
        require(type(denied) is tuple and len(denied) == len(set(denied)) == 5
            and {digest(row) for row in checked['quarantined_bindings']} == QUARANTINED_WHOLES,
            'quarantine')
    except Refused:
        raise
    except Exception:
        raise Refused('quarantine') from None
    return checked, frozenset(denied)


class IdentityCalendarBridge:
    """Genuine loaded identity/calendar composition; no native monetary source."""
    def __init__(self, algorithm, *, package, resolution, stock_bindings, full_axis,
                 benchmark_symbol, etf_symbols, raw_normalization, frozen_runtime_project_id,
                 quarantine_catalog, expected_quarantine_catalog_sha256):
        require(type(frozen_runtime_project_id) is int and 0 < frozen_runtime_project_id <= 2147483647,
            'project')
        require(type(package) is native.inputs.LoadedAcceptedRiskPreliminaryPackage, 'package')
        require(type(stock_bindings) is tuple and len(stock_bindings) == fmt.STOCK_COUNT
            and type(full_axis) is tuple and len(full_axis) == native.EXPECTED_AXIS_COUNT
            and type(etf_symbols) is dict and tuple(etf_symbols) == fmt.OWN_FUNDS, 'catalog')
        require(str(raw_normalization).casefold() in ('raw', 'datanormalizationmode.raw'), 'settings')
        self._algorithm, self._package, self._resolution = algorithm, package, resolution
        self._rows, self._axis, self._etfs = stock_bindings, full_axis, dict(etf_symbols)
        self._benchmark, self._raw, self._project = benchmark_symbol, raw_normalization, frozen_runtime_project_id
        checked, denied = _catalog(quarantine_catalog, expected_quarantine_catalog_sha256, stock_bindings)
        self._quarantine_raw, self._quarantine_sha = canonical(checked), expected_quarantine_catalog_sha256
        self._denied_ids = denied
        self._rows_raw, self._axis_raw = canonical(list(stock_bindings)), canonical(list(full_axis))
        self._resolution_sha = resolution.resolution_sha256 if type(resolution) is native.figi.PreliminaryQcFigiResolution else None
        self._by_whole = {digest(row): row for row in stock_bindings}
        self._started = self._ready = False
        self._closes, self._receipt = {}, None
        self._base_guard(); self._loaded_guard()

    def __repr__(self): return '<IdentityCalendarBridge full original identities; no monetary source or export>'
    def __reduce_ex__(self, protocol): raise TypeError('identity bridge cannot enter host serialization')

    @property
    def raw_normalization(self):
        self._base_guard(); return self._raw

    def _base_guard(self):
        try:
            a = self._algorithm
            require(type(a.project_id) is int and a.project_id == self._project and a.live_mode is False
                and str(a.time_zone) == 'America/New_York' and a.account_currency == 'USD'
                and a.settings.daily_precise_end_time is True and a.settings.seed_initial_prices is False,
                'settings')
            require(fmt.sha(self._quarantine_raw) == self._quarantine_sha, 'quarantine')
        except Refused:
            raise
        except Exception:
            raise Refused('settings') from None

    def _loaded_guard(self):
        try:
            p = self._package
            require(type(p) is native.inputs.LoadedAcceptedRiskPreliminaryPackage
                and p.package_sha256 == native.PACKAGE_SHA256
                and p.activation_manifest_sha256 == native.ACTIVATION_SHA256
                and p.runtime_symbol_bindings == self._rows
                and native.inputs._stream_hash(self._rows) == fmt.BINDING_SHA256 == native.BINDING_STREAM_SHA256
                and canonical(list(self._rows)) == self._rows_raw and len(self._by_whole) == fmt.STOCK_COUNT,
                'package')
            require(tuple(p.evaluator_input.session_axis) == self._axis
                and tuple(sorted(set(self._axis))) == self._axis
                and fmt.sha(self._axis_raw) == fmt.FULL_AXIS_SHA256 == native.AXIS_SHA256
                and dict(p.evaluator_input.source_lineage_sha256s)['security_master_admission_sha256'] == native.ADMISSION_SHA256,
                'package')
            normalized = tuple(native.figi._input_row(row, native.ADMISSION_SHA256) for row in self._rows)
            native.figi.require_preliminary_qc_figi_resolution(self._resolution)
            require(type(self._resolution) is native.figi.PreliminaryQcFigiResolution
                and self._resolution.resolution_sha256 == self._resolution_sha
                and tuple(self._resolution._input_rows) == normalized
                and self._resolution.input_row_count == fmt.STOCK_COUNT
                and self._resolution.resolved_count + self._resolution.named_refusal_count == fmt.STOCK_COUNT,
                'resolution')
            _catalog(json.loads(self._quarantine_raw), self._quarantine_sha, self._rows)
        except Refused:
            raise
        except Exception:
            raise Refused('resolution') from None

    def no_orders(self):
        self._base_guard()
        try:
            require(next(iter(self._algorithm.transactions.get_orders()), None) is None, 'orders')
            for index, (_, holding) in enumerate(self._algorithm.portfolio.items()):
                require(index < native.MAX_PORTFOLIO_ROWS
                    and native.money._decimal(holding.quantity, 'quarantine initial holding') == 0, 'orders')
        except Refused:
            raise
        except Exception:
            raise Refused('orders') from None

    def _static(self):
        facts = {}
        try:
            for ticker, symbol in self._etfs.items():
                fact = native._native(symbol); stable_native_identity(fact)
                security = self._algorithm.securities[symbol]
                require(fact['display'] == ticker and fact['sid'] not in facts
                    and security.quote_currency.symbol == 'USD'
                    and native.money._decimal(security.quote_currency.conversion_rate, 'quarantine fund rate') == 1
                    and str(security.exchange.hours.time_zone) == 'America/New_York'
                    and security.data_normalization_mode == self._raw, 'catalog')
                facts[fact['sid']] = fact
            require(native._native(self._benchmark)['sid'] == native._native(self._etfs['SPY'])['sid'], 'catalog')
            return facts
        except Refused:
            raise
        except Exception:
            raise Refused('catalog') from None

    def authenticate_once(self):
        require(not self._started, 'once'); self._started = True
        self._base_guard(); self.no_orders(); self._loaded_guard()
        deadline = time.monotonic() + MAX_AUTHENTICATION_SECONDS
        try:
            require(time.monotonic() < deadline, 'deadline')
            static = self._static(); resolved_sids = set()
            # Inspect cached genuine resolution metadata only. No FIGI API or
            # public symbol/price route for a quarantined row is invoked.
            for row in self._resolution.resolved:
                require(time.monotonic() < deadline, 'deadline')
                symbol = self._resolution._symbol_by_security[row['security_id']]
                fact = stable_native_identity(native._native(symbol))
                require(fact['sid'] == row['qc_security_id'] and fact['sid'] not in resolved_sids
                    and fact['sid'] not in static, 'identity')
                resolved_sids.add(fact['sid'])
            sessions = tuple(value for value in self._axis if fmt.FIRST <= value <= fmt.LAST)
            require(len(sessions) == fmt.SESSION_COUNT and sessions[0] == fmt.FIRST and sessions[-1] == fmt.LAST,
                'axis')
            hours = self._algorithm.securities[self._etfs['SPY']].exchange.hours
            schedule = []
            for session in sessions:
                require(time.monotonic() < deadline, 'deadline')
                midnight = datetime.strptime(session, '%Y-%m-%d')
                opening = native._qc_ny(hours.get_next_market_open(midnight, False))
                closing = native._qc_ny(hours.get_next_market_close(opening.replace(tzinfo=None), False))
                require(opening.date().isoformat() == closing.date().isoformat() == session
                    and opening.time().replace(tzinfo=None) == daytime(9, 30)
                    and opening < closing <= opening.replace(hour=16, minute=0), 'calendar')
                schedule.append({'session': session, 'open_utc': opening.astimezone(timezone.utc).isoformat(),
                    'close_utc': closing.astimezone(timezone.utc).isoformat()})
            require(digest(schedule) == native.SCHEDULE_SHA256, 'calendar')
            self._loaded_guard(); self.no_orders(); require(static == self._static(), 'identity')
            self._closes = {row['session']: datetime.fromisoformat(row['close_utc']) for row in schedule}
            self._receipt = {'schema': BRIDGE_SCHEMA + '-receipt', 'runtime_project_id': self._project,
                'quarantine_epoch': quarantine.RESEARCH_EPOCH_ID, 'quarantine_catalog_sha256': self._quarantine_sha,
                'fresh_resolution_sha256': self._resolution_sha, 'fresh_binding_stream_sha256': fmt.BINDING_SHA256,
                'fresh_input_binding_count': fmt.STOCK_COUNT, 'fresh_resolved_count': self._resolution.resolved_count,
                'fresh_named_refusal_count': self._resolution.named_refusal_count,
                'fresh_own_ETF_count': fmt.FUND_COUNT, 'resolved_duplicate_SID_count': 0,
                'resolved_own_ETF_collision_count': 0, 'ordered_full_axis_sha256': fmt.FULL_AXIS_SHA256,
                'NYSE_schedule_sha256': native.SCHEDULE_SHA256, 'calendar_source_sha256': native.CALENDAR_SOURCE_SHA256,
                'native_price_book_initialized': False, 'native_price_book_reads': 0,
                'native_price_lookup_attempts': 0, 'native_price_lookup_completed': 0,
                'separate_forward_native_SID_census_collected': False, **fmt.FALSE_FLAGS}
            require(time.monotonic() < deadline, 'deadline'); self._ready = True; return self.receipt()
        except Refused:
            raise
        except TimeoutError as error:
            # Classify only the canonical builtin signal, never guessed native
            # exception names, messages, nested causes or unrelated subclasses.
            raise Refused('deadline' if type(error) is TimeoutError else 'calendar') from None
        except Exception:
            raise Refused('calendar') from None

    def receipt(self):
        require(self._ready, 'not_ready'); self._base_guard()
        return json.loads(canonical(self._receipt))

    def session_close(self, session):
        require(self._ready, 'not_ready'); self._base_guard()
        require(type(session) is str and session in self._closes, 'axis')
        return self._closes[session]

    def symbol_for_binding(self, value):
        require(self._ready, 'not_ready'); self._base_guard()
        try:
            checked = native.figi._input_row(value, native.ADMISSION_SHA256); whole = digest(checked)
            require(whole in self._by_whole and checked == self._by_whole[whole], 'assignment')
            require(whole not in QUARANTINED_WHOLES and checked['security_id'] not in self._denied_ids, 'quarantine')
            native.figi.require_preliminary_qc_figi_resolution(self._resolution)
            require(self._resolution.resolution_sha256 == self._resolution_sha, 'resolution')
            symbol = self._resolution.symbol_for_security(checked['security_id'])
            require(symbol is not None, 'missing'); stable_native_identity(native._native(symbol))
            return symbol
        except Refused:
            raise
        except Exception:
            raise Refused('identity') from None


def validate_source_context(value):
    keys = {'schema', 'runtime_project_id', 'manifest_pin', 'catalog_pin', 'object_key_prefix',
        'AP_fact_sha256', 'AP_authentication_sha256'}
    require(type(value) is dict and set(value) == keys and value['schema'] == fmt.SCHEMA + '-QC-context'
        and type(value['runtime_project_id']) is int and value['runtime_project_id'] > 0
        and value['AP_fact_sha256'] == fmt.AP_FACT_SHA256 and value['AP_authentication_sha256'] == fmt.AP_AUTH_SHA256, 'source')
    fmt.validate_pin(value['manifest_pin'], fmt.MAX_MANIFEST_BYTES); fmt.validate_pin(value['catalog_pin'], fmt.MAX_CATALOG_BYTES)
    require(value['object_key_prefix'] == str(value['runtime_project_id']) + '/arv2/r326-common/'
        + value['manifest_pin']['sha256'] + '/', 'source')
    return json.loads(canonical(value))


class SpecificQuarantineVendorPriceBook:
    """Concrete reader; fixed whole-binding choice and two bounded month cache."""
    def __init__(self, algorithm, *, identity_bridge, resolution, stock_bindings, etf_symbols,
                 frozen_source_context, expected_context_sha256, frozen_runtime_project_id,
                 quarantine_catalog, expected_quarantine_catalog_sha256):
        context = validate_source_context(frozen_source_context)
        require(type(identity_bridge) is IdentityCalendarBridge
            and type(expected_context_sha256) is str and digest(context) == expected_context_sha256
            and type(frozen_runtime_project_id) is int and frozen_runtime_project_id == context['runtime_project_id'], 'source')
        require(type(stock_bindings) is tuple and len(stock_bindings) == fmt.STOCK_COUNT
            and type(etf_symbols) is tuple and len(etf_symbols) == fmt.FUND_COUNT, 'catalog')
        self._algorithm, self._native, self._resolution = algorithm, identity_bridge, resolution
        checked, denied = _catalog(quarantine_catalog, expected_quarantine_catalog_sha256, stock_bindings)
        require(identity_bridge._algorithm is algorithm and identity_bridge._resolution is resolution
            and identity_bridge._rows == stock_bindings
            and all(symbol is identity_bridge._etfs[ticker]
                for ticker, symbol in zip(fmt.OWN_FUNDS, etf_symbols, strict=True))
            and identity_bridge._project == frozen_runtime_project_id
            and identity_bridge._quarantine_sha == expected_quarantine_catalog_sha256, 'source')
        self._quarantine_raw, self._quarantine_sha = canonical(checked), expected_quarantine_catalog_sha256
        self._denied_ids = denied
        self._rows = stock_bindings; self._fund_symbols = etf_symbols
        self._context_raw, self._context_sha = canonical(context), expected_context_sha256
        self._project = frozen_runtime_project_id; self._started = self._ready = False
        self._manifest = self._catalog = self._receipt = None
        self._cache, self._lookups, self._reads = OrderedDict(), 0, 0
        self._stock_slots, self._fund_slots, self._symbols, self._identities = {}, {}, {}, {}
        self._base_guard()

    def __repr__(self): return '<SpecificQuarantineVendorPriceBook QC-local prices redacted; no export>'
    def __reduce_ex__(self, protocol): raise TypeError('QC-local vendor prices cannot enter host serialization')

    def _base_guard(self):
        try:
            algorithm = self._algorithm
            require(type(algorithm.project_id) is int and algorithm.project_id == self._project
                and algorithm.live_mode is False and str(algorithm.time_zone) == 'America/New_York'
                and algorithm.account_currency == 'USD' and algorithm.settings.daily_precise_end_time is True
                and algorithm.settings.seed_initial_prices is False and fmt.sha(self._context_raw) == self._context_sha, 'source')
            require(type(self._native) is IdentityCalendarBridge and self._native._algorithm is self._algorithm
                and self._native._resolution is self._resolution
                and self._native._project == self._project and self._native._quarantine_sha == self._quarantine_sha
                and fmt.sha(self._quarantine_raw) == self._quarantine_sha, 'source')
            self._native._base_guard()
        except Refused: raise
        except Exception: raise Refused('source') from None

    def _read(self, key, expected, maximum, *, deadline):
        require(time.monotonic() < deadline, 'deadline')
        fmt.validate_pin(expected, maximum)
        try:
            value = self._algorithm.object_store.read_bytes(key)
            if type(value) is bytes:
                raw = value
            else:
                byte_array = publication._SYSTEM_BYTE_ARRAY
                require(byte_array is not None and type(value) is byte_array and value.Rank == 1
                    and value.GetType().FullName == 'System.Byte[]' and type(value.Length) is int
                    and value.Length == expected['byte_count'], 'hash')
                raw = bytes(value)
            require(type(raw) is bytes and 0 < len(raw) <= maximum, 'bound')
        except TimeoutError as error:
            raise Refused('deadline' if type(error) is TimeoutError else 'missing') from None
        except Refused as error:
            if type(error) is Refused and BaseException.args.__get__(error) == ('deadline',):
                raise
            raise Refused('missing') from None
        except Exception: raise Refused('missing') from None
        require(time.monotonic() < deadline, 'deadline')
        require(fmt.pin(raw) == expected, 'hash'); self._reads += 1; return raw

    def authenticate_once(self):
        require(not self._started, 'source'); self._started = True; self._base_guard()
        deadline = time.monotonic() + MAX_AUTHENTICATION_SECONDS
        try:
            self._native.no_orders()
            receipt = self._native.receipt()
            native.figi.require_preliminary_qc_figi_resolution(self._resolution)
            require(self._resolution.resolution_sha256 == receipt['fresh_resolution_sha256']
                and receipt['fresh_binding_stream_sha256'] == fmt.BINDING_SHA256
                and receipt['fresh_input_binding_count'] == fmt.STOCK_COUNT
                and receipt['resolved_duplicate_SID_count'] == receipt['resolved_own_ETF_collision_count'] == 0
                and receipt['fresh_own_ETF_count'] == fmt.FUND_COUNT, 'catalog')
            normalized = tuple(native.figi._input_row(row, native.ADMISSION_SHA256) for row in self._rows)
            require(native.inputs._stream_hash(normalized) == fmt.BINDING_SHA256
                and tuple(self._resolution._input_rows) == normalized, 'catalog')
            context = validate_source_context(json.loads(self._context_raw)); prefix = context['object_key_prefix']
            manifest_raw = self._read(prefix + 'manifest.json', context['manifest_pin'], fmt.MAX_MANIFEST_BYTES, deadline=deadline)
            manifest = fmt.validate_manifest(fmt.loads(manifest_raw, fmt.MAX_MANIFEST_BYTES))
            require(manifest['catalog_pin'] == context['catalog_pin'], 'catalog')
            catalog_raw = self._read(prefix + 'catalog.json', context['catalog_pin'], fmt.MAX_CATALOG_BYTES, deadline=deadline)
            catalog = fmt.validate_catalog(fmt.loads(catalog_raw, fmt.MAX_CATALOG_BYTES))
            require([{key: row[key] for key in ('month_ordinal', 'month', 'session_indexes')} for row in manifest['months']] == catalog['months'], 'month')
            for session in catalog['price_sessions']:
                require(time.monotonic() < deadline, 'deadline')
                closing = self._native.session_close(session)
                require(closing.tzinfo is not None and closing.astimezone(native.NY).date().isoformat() == session, 'axis')
            require({row['whole_binding_sha256'] for row in catalog['assignments'][:fmt.STOCK_COUNT]
                if row['role'] == fmt.NATIVE} == QUARANTINED_WHOLES, 'quarantine')
            all_sids = []
            for index, (original, assigned) in enumerate(zip(normalized, catalog['assignments'][:fmt.STOCK_COUNT], strict=True)):
                require(time.monotonic() < deadline, 'deadline')
                require(assigned['whole_binding_sha256'] == digest(original)
                    and assigned['semantic_binding_sha256'] == original['row_sha256']
                    and assigned['security_id'] == original['security_id'], 'assignment')
                self._stock_slots[digest(original)] = index
                if assigned['role'] != fmt.VENDOR:
                    continue
                require(digest(original) not in QUARANTINED_WHOLES and original['security_id'] not in self._denied_ids,
                    'quarantine')
                symbol = self._resolution.symbol_for_security(original['security_id'])
                if symbol is not None:
                    fact = native._native(symbol); require(fact['kind'] in ('equity', 'securitytype.equity') and fact['market'] == 'usa', 'catalog')
                    all_sids.append(fact['sid']); self._symbols[index], self._identities[index] = symbol, canonical(fact)
            require(len(all_sids) == len(set(all_sids)), 'duplicate')
            fund_sids = []
            for index, (ticker, symbol) in enumerate(zip(fmt.OWN_FUNDS, self._fund_symbols, strict=True)):
                slot = fmt.STOCK_COUNT + index; fact = native._native(symbol)
                require(fact['kind'] in ('equity', 'securitytype.equity') and fact['market'] == 'usa' and fact['display'] == ticker, 'catalog')
                fund_sids.append(fact['sid']); self._fund_slots[ticker] = slot
                self._symbols[slot], self._identities[slot] = symbol, canonical(fact)
            require(len(set(fund_sids)) == fmt.FUND_COUNT and not set(fund_sids) & set(all_sids), 'duplicate')
            self._manifest, self._catalog = manifest, catalog
            self._session = {value: index for index, value in enumerate(catalog['price_sessions'])}
            self._month = {index: row['month_ordinal'] for row in catalog['months'] for index in row['session_indexes']}
            self._position = {slot: index for index, slot in enumerate(catalog['vendor_slots'])}
            self._resolution_sha = self._resolution.resolution_sha256
            self._receipt = {'schema': SCHEMA + '-receipt', 'source_context_sha256': self._context_sha,
                'runtime_project_id': self._project, 'manifest_pin': context['manifest_pin'], 'catalog_pin': context['catalog_pin'],
                'AP_fact_sha256': fmt.AP_FACT_SHA256, 'fresh_resolution_sha256': self._resolution_sha,
                'fresh_binding_stream_sha256': fmt.BINDING_SHA256, 'stock_count': fmt.STOCK_COUNT,
                'fund_count': fmt.FUND_COUNT, 'vendor_slot_count': len(catalog['vendor_slots']),
                'quarantine_epoch': quarantine.RESEARCH_EPOCH_ID, 'quarantine_catalog_sha256': self._quarantine_sha,
                'reader_profile_sha256': digest(profile_record()),
                'native_price_book_initialized': False, 'native_price_book_reads': 0,
                'source_rows': manifest['valid_count'], 'explicit_absent_cells': manifest['absent_count'], **fmt.FALSE_FLAGS}
            require(time.monotonic() < deadline, 'deadline')
            self._base_guard(); self._ready = True; return self.receipt()
        except Refused: raise
        except Exception: raise Refused('catalog') from None

    def _slot(self, value, *, currency=False):
        require(self._ready, 'source'); self._base_guard()
        require(type(self._resolution) is native.figi.PreliminaryQcFigiResolution
            and self._resolution.resolution_sha256 == self._resolution_sha, 'source')
        try:
            if type(value) is dict and set(value) == {'schema', 'ticker'}:
                require(value['schema'] == FUND_SCHEMA and value['ticker'] in self._fund_slots, 'assignment')
                slot = self._fund_slots[value['ticker']]
            else:
                checked = native.figi._input_row(value, native.ADMISSION_SHA256); whole = digest(checked)
                require(whole in self._stock_slots, 'assignment')
                require(whole not in QUARANTINED_WHOLES and checked['security_id'] not in self._denied_ids, 'quarantine')
                slot = self._stock_slots[whole]
            require(self._catalog['assignments'][slot]['role'] == fmt.VENDOR and slot in self._position, 'source')
            require(slot in self._symbols, 'missing')
            symbol = self._symbols[slot]
            require(stable_native_identity(native._native(symbol))
                == stable_native_identity(json.loads(self._identities[slot])), 'catalog')
            if slot < fmt.STOCK_COUNT:
                current = self._resolution.symbol_for_security(self._rows[slot]['security_id'])
                require(current is not None and stable_native_identity(native._native(current))
                    == stable_native_identity(json.loads(self._identities[slot])), 'catalog')
            if currency:
                security = self._algorithm.securities[symbol]
                require(stable_native_identity(native._native(security.symbol))
                    == stable_native_identity(json.loads(self._identities[slot]))
                    and security.quote_currency.symbol == 'USD'
                    and native.money._decimal(security.quote_currency.conversion_rate, 'vendor USD rate') == 1
                    and security.data_normalization_mode == self._native.raw_normalization, 'source')
            return slot, symbol
        except Refused: raise
        except Exception: raise Refused('catalog') from None

    def symbol_for_binding(self, value): return self._slot(value)[1]
    def symbol_for_fund(self, value):
        require(type(value) is dict and set(value) == {'schema', 'ticker'}, 'assignment')
        return self._slot(value)[1]

    def _load_month(self, ordinal):
        if ordinal in self._cache:
            self._cache.move_to_end(ordinal); return self._cache[ordinal]
        summary = self._manifest['months'][ordinal]
        deadline = time.monotonic() + MAX_MONTH_READ_SECONDS
        context = json.loads(self._context_raw)
        key = context['object_key_prefix'] + 'month-' + format(ordinal, '02d') + '-' + summary['sha256'] + '.jsonl'
        raw = self._read(key, {key: summary[key] for key in ('byte_count', 'sha256')}, fmt.MAX_MONTH_BYTES, deadline=deadline)
        values = fmt.validate_shard(raw, catalog=self._catalog, summary=summary, deadline=deadline)
        while len(self._cache) >= MAX_CACHED_MONTHS: self._cache.popitem(last=False)
        self._cache[ordinal] = values; return values

    def price(self, original_binding_or_fund, session):
        slot, _ = self._slot(original_binding_or_fund, currency=True)
        require(type(session) is str and session in self._session and self._lookups < MAX_LOOKUPS, 'axis')
        self._lookups += 1
        closing = self._native.session_close(session)
        require(closing.tzinfo is not None and closing.astimezone(timezone.utc)
            <= native._qc_ny(self._algorithm.time).astimezone(timezone.utc), 'source')
        index = self._session[session]; month = self._month[index]
        values = self._load_month(month); sessions = self._manifest['months'][month]['session_indexes']
        text = values[self._position[slot] * len(sessions) + sessions.index(index)]
        require(text is not None, 'missing'); return Decimal(fmt.price_text(text))

    def receipt(self):
        require(self._ready, 'source'); self._base_guard()
        return json.loads(canonical(self._receipt))


def profile_record():
    return {'schema': SCHEMA, 'quarantine_epoch': quarantine.RESEARCH_EPOCH_ID,
        'format_profile_sha256': digest(fmt.profile_record()),
        'quarantine_policy_sha256': digest(quarantine.profile_record()),
        'quarantined_whole_binding_sha256s': sorted(QUARANTINED_WHOLES),
        'maximum_cached_months': MAX_CACHED_MONTHS, 'maximum_lookups': MAX_LOOKUPS,
        'authentication_seconds': MAX_AUTHENTICATION_SECONDS, 'month_read_parse_seconds': MAX_MONTH_READ_SECONDS,
        'timeout_classification': 'exact_builtin_TimeoutError_or_local_deadline_refusal_no_native_cause_inference',
        'uninterruptible_IO_or_host_suspension_deadline_qualification': True,
        'payload': 'unchanged_exact_full6151_assignment_catalog_and_all_month_blocks_versioned_headers_hashes_decimal_rows',
        'source_context': 'unchanged_r326_vendor_payload_namespace_requires_external_current_project_and_exact_manifest_catalog_pins',
        'identity': 'genuine_loaded_package_and_genuine_full_resolution_no_package_reread_or_second_FIGI_resolution',
        'calendar': 'fixed_current_SPY_full1452_NYSE_schedule_no_native_price_book_or_History',
        'resolved_census': 'full6151_terminals_resolved_duplicates_and_8_ETF_collision_check_not_unfiltered_forward_native_census',
        'display_ticker': 'observational_never_permanent_identity_key',
        'quarantine': 'exact_five_whole_bindings_and_their_security_IDs_before_symbol_or_price_lookup_no_native_fallback',
        'conditional': 'unchanged510_never_potential_stops_on_any_actual_price_or_symbol_request',
        'same_session_before_actual_NYSE_close': 'refuse', 'source_fallback': False,
        'old_native_price_book_allocated_or_read': False, **fmt.FALSE_FLAGS}
