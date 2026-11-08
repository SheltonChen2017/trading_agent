"""Specific QC-local reader for one externally frozen monthly vendor sidecar.

No upload, order, source grant, alternative source or host export is provided.
Runtime project/access/processing/run gates precede construction externally.
"""
from collections import OrderedDict
from datetime import timezone
from decimal import Decimal
import json
import time

try:
    import newrule_common_price_format as fmt
    import newrule_native_price_book_runtime as native_reader
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_common_price_format as fmt
    from research.analyst_revisions_v2_qc import newrule_native_price_book_runtime as native_reader

native = native_reader.native
SCHEMA = fmt.SCHEMA + '-vendor-runtime'
FUND_SCHEMA = 'arv2-r298-common-price-monetary-component-v1-own-fund'
Refused, require, finite = fmt.Refused, fmt.require, fmt.finite
canonical, digest = fmt.canonical, fmt.digest
MAX_LOOKUPS, MAX_CACHED_MONTHS = 300000, 2
MAX_AUTHENTICATION_SECONDS, MAX_MONTH_READ_SECONDS = 300, 30


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


class SpecificVendorPriceBook:
    """Concrete reader; fixed whole-binding choice and two bounded month cache."""
    def __init__(self, algorithm, *, native_book, resolution, stock_bindings, etf_symbols,
                 frozen_source_context, expected_context_sha256, frozen_runtime_project_id):
        context = validate_source_context(frozen_source_context)
        require(type(native_book) is native_reader.SpecificNativePriceBook
            and type(expected_context_sha256) is str and digest(context) == expected_context_sha256
            and type(frozen_runtime_project_id) is int and frozen_runtime_project_id == context['runtime_project_id'], 'source')
        require(type(stock_bindings) is tuple and len(stock_bindings) == fmt.STOCK_COUNT
            and type(etf_symbols) is tuple and len(etf_symbols) == fmt.FUND_COUNT, 'catalog')
        self._algorithm, self._native, self._resolution = algorithm, native_book, resolution
        self._rows = stock_bindings; self._fund_symbols = etf_symbols
        self._context_raw, self._context_sha = canonical(context), expected_context_sha256
        self._project = frozen_runtime_project_id; self._started = self._ready = False
        self._manifest = self._catalog = self._receipt = None
        self._cache, self._lookups, self._reads = OrderedDict(), 0, 0
        self._stock_slots, self._fund_slots, self._symbols, self._identities = {}, {}, {}, {}
        self._base_guard()

    def __repr__(self): return '<SpecificVendorPriceBook QC-local prices redacted; no export>'
    def __reduce_ex__(self, protocol): raise TypeError('QC-local vendor prices cannot enter host serialization')

    def _base_guard(self):
        try:
            algorithm = self._algorithm
            require(type(algorithm.project_id) is int and algorithm.project_id == self._project
                and algorithm.live_mode is False and str(algorithm.time_zone) == 'America/New_York'
                and algorithm.account_currency == 'USD' and algorithm.settings.daily_precise_end_time is True
                and algorithm.settings.seed_initial_prices is False and fmt.sha(self._context_raw) == self._context_sha, 'source')
            require(type(self._native) is native_reader.SpecificNativePriceBook, 'source')
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
                byte_array = native_reader.publication._SYSTEM_BYTE_ARRAY
                require(byte_array is not None and type(value) is byte_array and value.Rank == 1
                    and value.GetType().FullName == 'System.Byte[]' and type(value.Length) is int
                    and value.Length == expected['byte_count'], 'hash')
                raw = bytes(value)
            require(type(raw) is bytes and 0 < len(raw) <= maximum, 'bound')
        except Exception: raise Refused('missing') from None
        require(time.monotonic() < deadline, 'deadline')
        require(fmt.pin(raw) == expected, 'hash'); self._reads += 1; return raw

    def authenticate_once(self):
        require(not self._started, 'source'); self._started = True; self._base_guard()
        deadline = time.monotonic() + MAX_AUTHENTICATION_SECONDS
        try:
            self._native._identity._no_orders()
            receipt = self._native.receipt()
            native.figi.require_preliminary_qc_figi_resolution(self._resolution)
            require(self._resolution.resolution_sha256 == receipt['fresh_full_forward_reverse_resolution_sha256']
                and receipt['fresh_binding_stream_sha256'] == fmt.BINDING_SHA256
                and receipt['fresh_input_binding_count'] == fmt.STOCK_COUNT
                and receipt['fresh_duplicate_SID_count'] == receipt['fresh_own_ETF_collision_count'] == 0
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
            all_sids = []
            for index, (original, assigned) in enumerate(zip(normalized, catalog['assignments'][:fmt.STOCK_COUNT], strict=True)):
                require(time.monotonic() < deadline, 'deadline')
                require(assigned['whole_binding_sha256'] == digest(original)
                    and assigned['semantic_binding_sha256'] == original['row_sha256']
                    and assigned['security_id'] == original['security_id'], 'assignment')
                self._stock_slots[digest(original)] = index
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
                require(whole in self._stock_slots, 'assignment'); slot = self._stock_slots[whole]
            require(self._catalog['assignments'][slot]['role'] == fmt.VENDOR and slot in self._position, 'source')
            require(slot in self._symbols, 'missing')
            symbol = self._symbols[slot]
            require(native_reader.stable_native_identity(native._native(symbol))
                == native_reader.stable_native_identity(json.loads(self._identities[slot])), 'catalog')
            if slot < fmt.STOCK_COUNT:
                current = self._resolution.symbol_for_security(self._rows[slot]['security_id'])
                require(current is not None and native_reader.stable_native_identity(native._native(current))
                    == native_reader.stable_native_identity(json.loads(self._identities[slot])), 'catalog')
            if currency:
                security = self._algorithm.securities[symbol]
                require(native_reader.stable_native_identity(native._native(security.symbol))
                    == native_reader.stable_native_identity(json.loads(self._identities[slot]))
                    and security.quote_currency.symbol == 'USD'
                    and native.money._decimal(security.quote_currency.conversion_rate, 'vendor USD rate') == 1
                    and security.data_normalization_mode == self._native._raw_normalization, 'source')
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
    return {'schema': SCHEMA, 'format_profile_sha256': digest(fmt.profile_record()),
        'maximum_cached_months': MAX_CACHED_MONTHS, 'maximum_lookups': MAX_LOOKUPS,
        'authentication_seconds': MAX_AUTHENTICATION_SECONDS, 'month_read_parse_seconds': MAX_MONTH_READ_SECONDS,
        'uninterruptible_IO_or_host_suspension_deadline_qualification': True,
        'source_before_decode': 'fixed_manifest_and_catalog_then_full_grid_month_byte_pins',
        'fresh_identity': 'genuine_full6151_resolution_same_as_fresh_native_reader_plus8ETFcollision_check',
        'native_identity_projection': ['sid', 'kind', 'market', 'sid_date'],
        'display_ticker': 'validated_observational_not_a_permanent_identity_key',
        'same_session_before_actual_NYSE_close': 'refuse', 'source_fallback': False, **fmt.FALSE_FLAGS}
