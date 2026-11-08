"""Concrete R337 quarantine execution driver with explicit preserved quote rules.

The pure contract lives separately to keep each prospective cloud source below
64KiB. No implicit source projection or old native-price initializer is used.
"""
try:
    import newrule_five_case_quarantine_contract as contract
except ImportError:
    from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_contract as contract

hashlib = contract.hashlib
json = contract.json
re = contract.re
datetime = contract.datetime
time = contract.time
timezone = contract.timezone
Decimal = contract.Decimal
ROUND_FLOOR = contract.ROUND_FLOOR
localcontext = contract.localcontext
MappingProxyType = contract.MappingProxyType
base = contract.base
monetary = contract.monetary
vendor_reader = contract.vendor_reader
quarantine = contract.quarantine
targets = contract.targets
legacy = contract.legacy
forced = contract.forced
core = contract.core
inputs = contract.inputs
figi = contract.figi
preopen = contract.preopen
number = contract.number
instant = contract.instant
FEE_RATE = contract.FEE_RATE
RESEARCH_EPOCH_ID = contract.RESEARCH_EPOCH_ID
STRATEGY_SCHEMA = contract.STRATEGY_SCHEMA
STARTING_CASH = contract.STARTING_CASH
START_SESSION = contract.START_SESSION
END_SESSION = contract.END_SESSION
MAX_ORDERS = contract.MAX_ORDERS
MAX_ROWS = contract.MAX_ROWS
weekly_axis = contract.weekly_axis
account_aggregates = contract.account_aggregates
LINEAGE_SHA256 = contract.LINEAGE_SHA256
EXPECTED_EVALUATION_SESSION_COUNT = contract.EXPECTED_EVALUATION_SESSION_COUNT
EVALUATION_SESSIONS_SHA256 = contract.EVALUATION_SESSIONS_SHA256
EXPECTED_DECISION_SESSION_COUNT = contract.EXPECTED_DECISION_SESSION_COUNT
DECISION_SESSIONS_SHA256 = contract.DECISION_SESSIONS_SHA256
SCHEMA = contract.SCHEMA
RESULT_SCHEMA = contract.RESULT_SCHEMA
MONTH_SCHEMA = contract.MONTH_SCHEMA
META_STATISTIC = contract.META_STATISTIC
MONTHLY_STATISTIC = contract.MONTHLY_STATISTIC
MAX_STATISTIC_BYTES = contract.MAX_STATISTIC_BYTES
MAX_VENDOR_COMPLETED_LOOKUPS = contract.MAX_VENDOR_COMPLETED_LOOKUPS
QUOTE_ANCESTOR_SHA256 = contract.QUOTE_ANCESTOR_SHA256
FALSE_FLAGS = contract.FALSE_FLAGS
PROFILE_KEYS = contract.PROFILE_KEYS
COMMON_RESULT_KEYS = contract.COMMON_RESULT_KEYS
FINITE = contract.FINITE
Refused = contract.Refused
require = contract.require
finite = contract.finite
canonical = contract.canonical
digest = contract.digest
quote_policy_fields = contract.quote_policy_fields
candidate_id = contract.candidate_id
make_strategy_profile = contract.make_strategy_profile
make_profile = contract.make_profile
validate_profile = contract.validate_profile
policy_record = contract.policy_record
validate_common_result = contract.validate_common_result
validate_quarantine_result = contract.validate_quarantine_result
validate_result_statistics = contract.validate_result_statistics


class FiveCaseQuarantineComparisonDriver(base.NewruleComparisonDriver):
    """New empty research epoch, exact five post-tilt denials, no native-five book."""
    def __init__(self, algorithm, *, common_profile, vendor_source_context,
                 quarantine_catalog, **base_kwargs):
        profile = validate_profile(common_profile)
        require(base_kwargs.get('profile') == profile['strategy_profile'], 'profile')
        require(type(algorithm.project_id) is int and algorithm.project_id == profile['runtime_project_id']
            and algorithm.live_mode is False, 'project')
        context = vendor_reader.validate_source_context(vendor_source_context)
        require(digest(context) == profile['vendor_source_context_sha256'], 'context')
        checked = quarantine.validate_quarantine_catalog(quarantine_catalog,
            expected_sha256=profile['quarantine_catalog_sha256'])
        self._common_profile_raw, self._common_profile = canonical(profile), profile
        self._quarantine_catalog = checked
        self._denied_ids = frozenset(quarantine.denied_security_ids(checked,
            expected_sha256=profile['quarantine_catalog_sha256']))
        self._vendor_context = context
        self._common_started = self._common_ready = False
        self._common_source = self._common_ledger = self._bridge = self._vendor_book = None
        self._quarantine_ledgers = {}
        self._base_to_price, self._price_to_base = MappingProxyType({}), MappingProxyType({})
        self._initialize_strategy_state(algorithm, **base_kwargs)

    def _common_guard(self):
        require(self._common_ready and canonical(self._common_profile) == self._common_profile_raw, 'not_ready')
        self._require_initialized()
        require(type(self._algorithm.project_id) is int
            and self._algorithm.project_id == self._common_profile['runtime_project_id']
            and self._algorithm.live_mode is False, 'project')
        figi.require_preliminary_qc_figi_resolution(self._resolution)
        require(self._bridge.receipt()['fresh_resolution_sha256'] == self._resolution.resolution_sha256,
            'resolution')
        require(digest(self._quarantine_catalog) == self._common_profile['quarantine_catalog_sha256'], 'catalog')
        self._common_source.receipt()

    def initialize(self):
        require(not self._common_started, 'once'); self._common_started = True
        result = self._initialize_genuine_strategy()
        self._freeze_fund_translation()
        rows = tuple(self._package.runtime_symbol_bindings)
        self._bridge = vendor_reader.IdentityCalendarBridge(self._algorithm,
            package=self._package, resolution=self._resolution, stock_bindings=rows,
            full_axis=self._session_axis, benchmark_symbol=self._benchmark_symbol,
            etf_symbols=self._etf_symbols,
            raw_normalization=self._raw_normalization,
            frozen_runtime_project_id=self._common_profile['runtime_project_id'],
            quarantine_catalog=self._quarantine_catalog,
            expected_quarantine_catalog_sha256=self._common_profile['quarantine_catalog_sha256'])
        self._bridge.authenticate_once()
        self._vendor_book = vendor_reader.SpecificQuarantineVendorPriceBook(self._algorithm,
            identity_bridge=self._bridge, resolution=self._resolution, stock_bindings=rows,
            etf_symbols=tuple(self._etf_symbols[ticker] for ticker in monetary.native.UNIVERSES),
            frozen_source_context=self._vendor_context,
            expected_context_sha256=self._common_profile['vendor_source_context_sha256'],
            frozen_runtime_project_id=self._common_profile['runtime_project_id'],
            quarantine_catalog=self._quarantine_catalog,
            expected_quarantine_catalog_sha256=self._common_profile['quarantine_catalog_sha256'])
        self._common_source = monetary.SpecificQuarantinePriceBook(self._bridge, self._vendor_book,
            stock_bindings=rows, own_fund_contracts=monetary.fund_contracts(), session_axis=self._session_axis,
            quarantine_catalog=self._quarantine_catalog,
            expected_quarantine_catalog_sha256=self._common_profile['quarantine_catalog_sha256'])
        self._common_source.authenticate_once()
        self._common_ledger = monetary.QuarantinePriceLedger(self._common_source)
        self._common_ready = True; self._common_guard(); return result

    def _current_holding_census(self):
        result = super()._current_holding_census()
        require(not self._denied_ids.intersection(result), 'quarantine')
        if self._common_ready:
            for identity in result: self._price_identity(identity)
        return result

    def _deny_order_symbol(self, symbol):
        sid = legacy._symbol_sid(symbol, 'quarantine order')
        identity = self._security_by_sid.get(sid, self._security_by_etf_sid.get(sid))
        require(identity is not None and identity not in self._denied_ids, 'quarantine')
        if self._common_ready: self._price_identity(identity)

    def _quarantine_result(self):
        require(tuple(sorted(self._quarantine_ledgers)) == self._decision_sessions, 'quarantine_ledger')
        rows = [self._quarantine_ledgers[s] for s in self._decision_sessions]
        with localcontext() as arithmetic:
            arithmetic.prec = 96
            weight = sum((Decimal(row['transferred_to_own_etf_weight']) for row in rows), Decimal(0))
        result = {'schema': RESULT_SCHEMA + '-quarantine', 'research_epoch_id': RESEARCH_EPOCH_ID,
            'quarantine_catalog_sha256': self._common_profile['quarantine_catalog_sha256'],
            'quarantine_policy_sha256': self._common_profile['quarantine_policy_sha256'],
            'decision_count': len(rows), 'transfer_ledger_path_sha256': digest(rows),
            'total_selected_sleeve_occurrence_count': sum(row['selected_sleeve_occurrence_count'] for row in rows),
            'total_positive_sleeve_occurrence_count': sum(row['positive_sleeve_occurrence_count'] for row in rows),
            'total_transferred_to_own_etf_weight': str(weight),
            'decisions_with_positive_transfer': sum(Decimal(row['transferred_to_own_etf_weight']) > 0 for row in rows),
            'quarantined_target_count': 0, 'quarantined_order_count': 0, 'quarantined_holding_count': 0,
            'replacement_name_promotions': 0, 'renormalization_performed': False, **FALSE_FLAGS}
        return validate_quarantine_result(result, expected_profile=self._common_profile)

    def _initialize_strategy_state(self, algorithm, *, profile, activation_manifest_key, activation_manifest_sha256, activation_manifest_byte_count, benchmark_symbol, etf_symbols, fundamental_universe, constituent_universes, trade_bar_type, quote_bar_type, minute_resolution, daily_resolution, raw_normalization, fee_model_factory, slippage_model_factory, order_status_enum, order_status_to_int, split_occurred_type, split_warning_type, split_data_type):
        seed = dict(profile)
        supplied = seed.pop('profile_sha256', None)
        require(targets.digest(seed) == supplied and seed.get('schema') == STRATEGY_SCHEMA, 'profile_binding')
        self._profile = json.loads(targets.canonical(profile))
        self._algorithm = algorithm
        self._activation_manifest_key = activation_manifest_key
        self._activation_manifest_sha256 = activation_manifest_sha256
        self._activation_manifest_byte_count = activation_manifest_byte_count
        self._benchmark_symbol = benchmark_symbol
        self._etf_symbols = dict(etf_symbols)
        self._fundamental_universe = fundamental_universe
        self._constituent_universes = dict(constituent_universes)
        self._trade_bar_type = trade_bar_type
        self._quote_bar_type = quote_bar_type
        self._minute_resolution = minute_resolution
        self._daily_resolution = daily_resolution
        self._raw_normalization = raw_normalization
        self._fee_model_factory = fee_model_factory
        self._slippage_model_factory = slippage_model_factory
        self._order_status_enum = order_status_enum
        self._order_status_to_int = order_status_to_int
        self._status_members = core.require_qc_order_status_enum_members(order_status_enum)
        require(tuple((order_status_to_int(member) for member, _ in self._status_members)) == (0, 1, 2, 3, 5, 6, 7, 8, 9), 'status_numbers')
        self._split_occurred_type = split_occurred_type
        self._split_warning_type = split_warning_type
        self._split_data_type = split_data_type
        self._split_history_count = 0
        self._initialized = self._completed = self._emitted = False
        self._configured_sids, self._active_dynamic_sids = (set(), set())
        self._security_by_sid, self._label_by_sid = ({}, {})
        self._symbol_by_security, self._security_by_etf_sid = ({}, {})
        self._maximum_active_dynamic_security_count = 0
        self._removed_dynamic_security_count = self._reference_history_call_count = 0
        self._account_observations, self._gross_exposure_observations = ({}, {})
        self._cache = {key: [] for key in ('FUNDAMENTALS',) + targets.UNIVERSES}
        self._source_row_count = 0
        self._split_records_by_session = {}
        self._forced_ledger = forced.empty_forced_delisting_ledger()
        self._plans, self._executed, self._fills, self._split_path = ({}, set(), [], [])
        self._intent = None
        self._order_ids, self._event_ids = (set(), set())
        self._fallback_counts, self._score_disagreement = ({}, [])
        self._cash_underfill_count = 0
        self._preopen_clock_confirmations = {}
        self._account_safety = {}

    def _initialize_genuine_strategy(self):
        require(not self._initialized and self._algorithm.live_mode is False, 'backtest_only')
        require(tuple(self._etf_symbols) == targets.UNIVERSES and tuple(self._constituent_universes) == targets.UNIVERSES and (self._fundamental_universe is not None), 'common_source_universes')
        require(self._portfolio_equity() == STARTING_CASH and self._portfolio_cash() == STARTING_CASH, 'starting_cash')
        package = inputs.load_accepted_risk_preliminary_package(self._algorithm, activation_manifest_key=self._activation_manifest_key, activation_manifest_sha256=self._activation_manifest_sha256, activation_manifest_byte_count=self._activation_manifest_byte_count)
        axis = tuple(package.evaluator_input.session_axis)
        expected = make_strategy_profile(axis, package_sha256=self._profile['package_sha256'], lineage_sha256=self._profile['lineage_sha256'], universe_count=self._profile['universe_count'], ar_percent=self._profile['ar_percent'], source_pins=self._profile['source_pins'], quarantine_catalog_sha256=self._common_profile['quarantine_catalog_sha256'])
        require(expected == self._profile, 'loaded_profile_axis')
        require(package.package_sha256 == self._profile['package_sha256'] and package.activation_manifest_sha256 == self._activation_manifest_sha256, 'loaded_package_binding')
        lineage = dict(package.evaluator_input.source_lineage_sha256s)
        resolution = figi.resolve_preliminary_qc_figis(package.runtime_symbol_bindings, expected_security_master_admission_sha256=lineage['security_master_admission_sha256'], composite_figi=self._algorithm.composite_figi, benchmark_symbol=self._benchmark_symbol)
        require(quarantine.make_quarantine_catalog(tuple(package.runtime_symbol_bindings)) == self._quarantine_catalog, 'catalog')
        self._package, self._resolution = (package, resolution)
        self._session_axis = axis
        self._session_positions = {s: i for i, s in enumerate(axis)}
        self._evaluation_sessions = tuple(expected['evaluation_sessions'])
        self._decision_sessions = tuple(expected['decision_sessions'])
        self._decision_set = frozenset(self._decision_sessions)
        self._score = preopen.PreopenRatingScoreRuntime(package.evaluator_input, start_position=self._session_positions[START_SESSION])
        for row in resolution.resolved:
            sid, identity = (row['qc_security_id'], row['security_id'])
            require(sid not in self._security_by_sid and identity not in self._symbol_by_security, 'figi_identity_collision')
            self._security_by_sid[sid] = identity
            self._label_by_sid[sid] = row['qc_display_ticker']
            self._symbol_by_security[identity] = resolution.symbol_for_security(identity)
        for ticker, symbol in self._etf_symbols.items():
            sid = legacy._symbol_sid(symbol, 'newrule own ETF')
            require(sid not in self._security_by_sid and sid not in self._security_by_etf_sid, 'own_etf_identity_collision')
            self._security_by_etf_sid[sid] = sid
            self._symbol_by_security[sid] = symbol
        self._initialized = True
        require(not self._current_holding_census(), 'initial_holdings')
        require(not tuple(self._algorithm.transactions.get_open_orders()), 'initial_open_orders')
        for symbol in self._etf_symbols.values():
            self.configure_security(self._algorithm.securities[symbol])
        return True

    def on_before_open(self):
        self._require_initialized()
        now = self._now()
        session = now.date().isoformat()
        if session not in self._decision_set:
            return None
        require(now.time().replace(tzinfo=None) == time(9, 20), 'decision_clock')
        require(session not in self._plans and self._intent is None and (self._algorithm.live_mode is False), 'decision_once')
        books, context_sha = self._books(session)
        target = targets.build_target(books, universe_count=self._profile['universe_count'], ar_percent=self._profile['ar_percent'], source_snapshot_sha256=context_sha, quarantine_catalog=self._quarantine_catalog, expected_quarantine_catalog_sha256=self._common_profile['quarantine_catalog_sha256'])
        require(target.input_books_sha256 == targets.book_digest(books), 'runtime_book_binding')
        holdings = self._current_holding_census()
        weights = {sid: weight for sid, _, weight in target.weights}
        require(not self._denied_ids.intersection(weights) and not self._denied_ids.intersection(holdings), 'quarantine')
        census = tuple(sorted(set(weights) | set(holdings)))
        for identity in census: self._price_identity(identity)
        self._prune_execution_subscriptions(set(census))
        previous = self._session_axis[self._session_positions[session] - 1]
        references = self._reference_prices(previous, census)
        if session == START_SESSION:
            require(not holdings and (not self._order_ids) and (self._portfolio_cash() == STARTING_CASH), 'first_decision_cash_only')
            equity = STARTING_CASH
        else:
            require(previous in self._account_observations, 'missing_prior_close_sizing_nav')
            equity = self._account_observations[previous]
            require(equity.is_finite() and equity > 0, 'prior_close_sizing_nav')
        factors, split_binding = self._split_factors(census, now)
        callbacks = self._split_records_by_session.get(session, {})
        require(all((factors[sid] == 1 or sid in callbacks for sid in holdings)), 'held_split_units_not_observed')
        quantities = {}
        with localcontext() as arithmetic:
            arithmetic.prec = 96
            for sid in census:
                factor = factors[sid]
                price = references[sid] * factor
                require(price > 0 and price.is_finite(), 'split_price_units')
                quantities[sid] = int((equity * weights.get(sid, Decimal(0)) / price).to_integral_value(rounding=ROUND_FLOOR))
        binding = {'session': session, 'target_sha256': target.target_sha256, 'context_sha256': context_sha, 'books_sha256': target.input_books_sha256, 'raw_reference_session': previous, 'raw_closes': sorted(((s, str(p)) for s, p in references.items())), 'same_session_split_factors': sorted(((s, str(f)) for s, f in factors.items())), 'split_history_sha256': split_binding, 'quantities': sorted(quantities.items()), 'holdings': sorted(holdings.items()), 'sizing_nav': str(equity), 'sizing_nav_session': previous if session != START_SESSION else 'initial_cash', 'actual_engine_nav_diagnostic': str(self._portfolio_equity()), 'cash': str(self._portfolio_cash())}
        self._plans[session] = {'binding': binding, 'sha256': targets.digest(binding), 'quantities': quantities, 'holdings': holdings, 'split_records': dict(self._split_records_by_session.get(session, {})), 'target': target}
        for sleeve in target.record()['sleeves']:
            for code in sleeve['refusals']:
                key = sleeve['universe'] + ':' + code
                self._fallback_counts[key] = self._fallback_counts.get(key, 0) + 1
        self._quarantine_ledgers[session] = json.loads(target.quarantine_ledger_bytes)
        return target.target_sha256

    def _freeze_fund_translation(self):
        forward, reverse = ({}, {})
        require(tuple(self._etf_symbols) == monetary.native.UNIVERSES, 'fund_translation')
        stocks = set(self._security_by_sid.values())
        for ticker, symbol in self._etf_symbols.items():
            sid = legacy._symbol_sid(symbol, 'common own fund')
            price_id = 'own-etf-' + ticker
            require(sid not in stocks and sid not in self._security_by_sid and (sid not in forward) and (price_id not in reverse) and (self._security_by_etf_sid.get(sid) == sid) and (self._symbol_for_security(sid) is symbol), 'fund_translation')
            forward[sid], reverse[price_id] = (price_id, sid)
        require(len(forward) == len(reverse) == 8 and stocks.isdisjoint(reverse) and all((reverse[value] == key for key, value in forward.items())), 'fund_translation')
        self._base_to_price, self._price_to_base = (MappingProxyType(forward), MappingProxyType(reverse))

    def _price_identity(self, identity):
        require(type(identity) is str, 'identity')
        require(identity not in self._denied_ids, 'quarantine')
        if identity in self._base_to_price:
            price_id = self._base_to_price[identity]
            symbol = self._symbol_for_security(identity)
            require(legacy._symbol_sid(symbol, 'common fund roundtrip') == identity and self._price_to_base.get(price_id) == identity, 'fund_translation')
            return price_id
        require(identity in self._symbol_by_security, 'identity')
        self._common_source.require_identity(identity)
        return identity

    def _reference_prices(self, session, security_ids):
        self._common_guard()
        require(type(security_ids) is tuple and 0 < len(security_ids) <= monetary.MAX_CENSUS and (security_ids == tuple(sorted(set(security_ids)))), 'reference')
        holdings = self._current_holding_census()
        require(set(holdings) <= set(security_ids), 'reference')
        symbols, inverse = ({}, {})
        for identity in security_ids:
            symbol, _ = self._ensure_security(identity)
            price_id = self._price_identity(identity)
            require(price_id not in inverse, 'identity')
            inverse[price_id] = identity
            symbols[price_id] = symbol
        translated_holdings = {self._price_identity(identity): quantity for identity, quantity in holdings.items()}
        prices = self._common_ledger.reference_prices(session, tuple(sorted(inverse)), translated_holdings, symbols, now=self._now())
        require(set(prices) == set(inverse), 'reference')
        return {inverse[price_id]: value for price_id, value in prices.items()}

    def on_after_close(self):
        self._common_guard()
        now = self._now()
        session = now.date().isoformat()
        if session not in self._evaluation_sessions:
            return None
        require(now >= self._common_source.session_close(session), 'close_clock')
        if session in self._decision_set:
            require(session in self._executed, 'close_state')
        require(self._intent is None and (not tuple(self._algorithm.transactions.get_open_orders())), 'close_state')
        cash, holdings = (self._portfolio_cash(), self._current_holding_census())
        translated, symbols = ({}, {})
        for identity, quantity in holdings.items():
            price_id = self._price_identity(identity)
            require(price_id not in translated, 'identity')
            translated[price_id], symbols[price_id] = (quantity, self._symbol_for_security(identity))
        try:
            engine_diagnostic = self._portfolio_equity()
        except Exception:
            engine_diagnostic = None
        nav, gross = self._common_ledger.observe_close(session, cash=cash, holdings=translated, runtime_symbols=symbols, now=now, engine_nav=engine_diagnostic)
        if session in self._account_observations:
            require(self._account_observations[session] == nav and self._gross_exposure_observations.get(session) == gross, 'close_state')
        self._account_observations[session], self._gross_exposure_observations[session] = (nav, gross)
        self._account_safety[session] = targets.digest({'cash': str(cash), 'holdings': sorted(holdings.items()), 'open_orders': 0, 'whole_long_only': True})

    def on_end_of_algorithm(self):
        self._common_guard()
        require(not self._emitted and self._intent is None and (tuple(sorted(self._plans)) == self._decision_sessions) and (tuple(sorted(self._executed)) == self._decision_sessions) and (tuple(sorted(self._account_observations)) == self._evaluation_sessions) and (tuple(sorted(self._account_safety)) == self._evaluation_sessions) and (tuple(sorted(self._preopen_clock_confirmations)) == self._decision_sessions) and (not tuple(self._algorithm.transactions.get_open_orders())), 'incomplete_terminal_geometry')
        require(self._now().date().isoformat() >= END_SESSION, 'terminal_clock')
        self._portfolio_cash()
        self._current_holding_census()
        require(0 < len(self._order_ids) == len(self._fills) <= MAX_ORDERS and self._reference_history_call_count == 0 and (self._split_history_count == len(self._decision_sessions)), 'terminal_order_or_history_census')
        months = {}
        for session in self._evaluation_sessions:
            months[session[:7]] = (session, self._account_observations[session])
        previous, monthly = (STARTING_CASH, [])
        with localcontext() as arithmetic:
            arithmetic.prec = 96
            for session, value in months.values():
                monthly.append([session, str((value / previous - 1).quantize(Decimal('1e-12'))), str(value.quantize(Decimal('0.000001')))])
                previous = value
        meta = {'schema': RESULT_SCHEMA, 'candidate_id': self._common_profile['candidate_id'], 'profile_sha256': self._common_profile['profile_sha256'], 'package_sha256': self._profile['package_sha256'], 'lineage_sha256': self._profile['lineage_sha256'], 'decision_count': len(self._plans), 'evaluation_session_count': len(self._evaluation_sessions), 'order_count': len(self._order_ids), 'fill_count': len(self._fills), 'raw_reference_history_calls': self._reference_history_call_count, 'split_unit_history_calls': self._split_history_count, 'common_source_path_sha256': targets.digest([self._plans[s]['binding']['context_sha256'] for s in self._decision_sessions]), 'plan_path_sha256': targets.digest([self._plans[s]['sha256'] for s in self._decision_sessions]), 'fill_path_sha256': targets.digest(self._fills), 'split_path_sha256': targets.digest(self._split_path), 'account_path_sha256': targets.digest([(s, str(self._account_observations[s])) for s in self._evaluation_sessions]), 'account_safety_sha256': targets.digest(sorted(self._account_safety.items())), 'preopen_frontier_sha256': targets.digest(sorted(self._preopen_clock_confirmations.items())), 'complete_geometry': True, 'no_open_orders': True, 'nonnegative_cash_at_fills_closes_terminal': True, 'whole_long_holdings_at_fills_closes_terminal': True, 'configured_fee_checks_complete': True, 'actual_fill_cash_reconciled': True, 'actual_clock_confirmation_complete': True, 'cash_constrained_buy_count': self._cash_underfill_count, 'coverage_fallback_counts': self._fallback_counts, 'alternative_view_diagnostic_sha256': targets.digest(self._score_disagreement), 'alternative_view_eligibility_disagreements': sum((row[1] for row in self._score_disagreement)), 'alternative_view_score_disagreements': sum((row[2] for row in self._score_disagreement)), 'forced_delisting': forced.forced_delisting_summary(self._forced_ledger), 'account_aggregates': account_aggregates(self._account_observations, self._evaluation_sessions, self._fills, forced.forced_delisting_summary(self._forced_ledger)), 'actual_terminal': 'runtime_geometry_complete_not_independent_source_admission', 'point_in_time_proven': False, 'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'source_admission_granted': False, 'strategy_result_accepted': False, 'common_price': self._common_result(), 'quarantine': self._quarantine_result()}
        monthly_record = {'schema': MONTH_SCHEMA, 'candidate_id': self._common_profile['candidate_id'], 'profile_sha256': self._common_profile['profile_sha256'], 'months': monthly, 'last_month_partial': True, 'alternative_view_realized_performance': False}
        validate_result_statistics({META_STATISTIC: canonical(meta).decode('ascii'), MONTHLY_STATISTIC: canonical(monthly_record).decode('ascii')}, expected_profile=self._common_profile)
        for name, record in ((META_STATISTIC, meta), (MONTHLY_STATISTIC, monthly_record)):
            payload = targets.canonical(record)
            require(len(payload) <= MAX_STATISTIC_BYTES, 'statistic_bound')
            self._algorithm.set_summary_statistic(name, payload.decode('ascii'))
        self._completed = self._emitted = True
        return (meta, monthly_record)

    def _common_result(self):
        self._common_guard()
        result = {'schema': RESULT_SCHEMA + '-source',
            'common_profile_sha256': self._common_profile['profile_sha256'],
            'strategy_profile_sha256': self._common_profile['strategy_profile_sha256'],
            'vendor_source_context_sha256': self._common_profile['vendor_source_context_sha256'],
            'monetary_policy_sha256': self._common_profile['monetary_policy_sha256'],
            'quarantine_catalog_sha256': self._common_profile['quarantine_catalog_sha256'],
            'quarantine_policy_sha256': self._common_profile['quarantine_policy_sha256'],
            'research_epoch_id': RESEARCH_EPOCH_ID,
            'fresh_resolution_sha256': self._resolution.resolution_sha256,
            'fund_translation_sha256': digest(sorted(self._base_to_price.items())), 'ledger': self._common_ledger.summary()}
        return validate_common_result(result, expected_profile=self._common_profile)

    def _submit_market(self, identity, quantity, session):
        self._price_identity(identity)
        require(identity not in self._denied_ids, 'quarantine')
        require(type(quantity) is int and quantity != 0 and (self._intent is None), 'order_quantity')
        require(len(self._order_ids) < MAX_ORDERS and self._algorithm.live_mode is False, 'order_bound_or_live')
        symbol, security = self._ensure_security(identity)
        quote = self._current_execution_price(security, quantity)
        before_quantity, before_cash = (self._current_quantity(identity), self._portfolio_cash())
        tag = 'ARV2N-' + self._plans[session]['sha256'][:16] + '-' + str(len(self._order_ids))
        intent = {'identity': identity, 'qc_sid': legacy._symbol_sid(symbol, 'newrule intent'), 'quantity': quantity, 'tag': tag, 'order_id': None, 'fill': None, 'dispatched_at': self._now(), 'fee_basis_quote': str(quote)}
        self._intent = intent
        ticket = self._algorithm.market_order(symbol, quantity, asynchronous=False, tag=tag)
        require(ticket is not None and self._status(ticket.status) == 'Filled' and (intent['fill'] is not None) and (ticket.order_id == intent['order_id']), 'market_ticket_not_complete')
        require(ticket.order_id not in self._order_ids, 'duplicate_ticket')
        fill = intent['fill']
        expected_cash = before_cash - Decimal(quantity) * Decimal(fill['price']) - Decimal(fill['fee'])
        require(self._current_quantity(identity) == before_quantity + quantity and expected_cash >= 0 and (abs(self._portfolio_cash() - expected_cash) <= Decimal('0.0000001')), 'fill_cash_or_holdings_reconciliation')
        self._order_ids.add(ticket.order_id)
        self._fills.append({'session': session, 'security_id_sha256': hashlib.sha256(identity.encode()).hexdigest(), 'submission_time': intent['dispatched_at'].isoformat(), 'fee_basis_quote': intent['fee_basis_quote'], **fill})
        self._intent = None

    def on_after_open(self):
        self._require_initialized()
        now, session = (self._now(), self._now().date().isoformat())
        if session not in self._decision_set:
            return None
        require(now.time().replace(tzinfo=None) == time(9, 31), 'execution_clock')
        require(session in self._plans and session not in self._executed and (self._intent is None) and (self._algorithm.live_mode is False), 'execution_once')
        require(session in self._preopen_clock_confirmations, 'missing_genuine_preopen_frontier')
        plan = self._plans[session]
        require(self._current_holding_census() == plan['holdings'] and self._split_records_by_session.get(session, {}) == plan['split_records'], 'between_decision_execution_drift')
        desired = plan['quantities']
        for identity in sorted(desired):
            difference = desired[identity] - self._current_quantity(identity)
            if difference < 0:
                self._submit_market(identity, difference, session)
        for identity in sorted(desired):
            difference = desired[identity] - self._current_quantity(identity)
            if difference <= 0:
                continue
            _, security = self._ensure_security(identity)
            try:
                price = max(self._current_execution_price(security, 1), number(security.price, positive=True))
            except targets.NewruleError:
                raise
            except Exception:
                raise targets.NewruleError('quote_execution_engine_price') from None
            available = int((self._portfolio_cash() / (price * (1 + FEE_RATE))).to_integral_value(rounding=ROUND_FLOOR))
            quantity = min(difference, max(0, available))
            if quantity != difference:
                self._cash_underfill_count += 1
            if quantity:
                self._submit_market(identity, quantity, session)
        require(not tuple(self._algorithm.transactions.get_open_orders()), 'pending_orders')
        self._portfolio_cash()
        require(all((quantity >= 0 for quantity in self._current_holding_census().values())), 'short_holdings')
        self._executed.add(session)
        return plan['sha256']

    def on_order_event(self, event):
        self._deny_order_symbol(event.symbol)
        self._require_initialized()
        require(self._algorithm.live_mode is False, 'backtest_only')
        status = self._status(event.status)
        engine = self._algorithm.transactions.get_order_by_id(event.order_id)
        require(engine is not None and engine.id == event.order_id, 'engine_order_binding')
        intent = self._intent
        if intent is None:
            return self._external_order_event(event, engine, status)
        require(legacy._symbol_sid(event.symbol, 'newrule order event') == intent['qc_sid'] and engine.tag == intent['tag'] and (number(engine.quantity) == intent['quantity']), 'order_intent_binding')
        require(type(event.order_id) is int and type(event.id) is int and (event.order_id > 0) and (event.id >= 0), 'order_event_ids')
        pair = (event.order_id, event.id)
        require(pair not in self._event_ids, 'duplicate_order_event')
        self._event_ids.add(pair)
        require(intent['order_id'] in (None, event.order_id), 'intent_order_id')
        intent['order_id'] = event.order_id
        if status in ('New', 'Submitted'):
            require(number(event.fill_quantity) == 0, 'nonfill_quantity')
            return None
        require(status == 'Filled' and intent['fill'] is None, 'nonterminal_or_partial_order')
        quantity, price = (number(event.fill_quantity), number(event.fill_price, positive=True))
        require(abs(price - Decimal(intent['fee_basis_quote'])) <= Decimal('0.0000001'), 'quote_execution_fill_price')
        fee = event.order_fee.value
        fee_amount = number(fee.amount)
        require(quantity == intent['quantity'] and fee.currency == 'USD' and (fee_amount >= 0), 'fill_quantity_or_fee')
        expected_fee = Decimal(intent['fee_basis_quote']) * abs(quantity) * FEE_RATE
        require(abs(fee_amount - expected_fee) <= Decimal('0.0000001'), 'configured_fee_mismatch')
        fill_time = instant(event.utc_time.replace(tzinfo=timezone.utc) if event.utc_time.tzinfo is None else event.utc_time)
        require(intent['dispatched_at'] <= fill_time <= self._now(), 'fill_clock')
        intent['fill'] = {'quantity': int(quantity), 'price': str(price), 'fee': str(fee_amount), 'fill_time': fill_time.isoformat(), 'order_id': event.order_id, 'event_id': event.id}
        return None

    def _quote_snapshot(self, security):
        now = self._now()
        require(now.time().replace(tzinfo=None) == time(9, 31), "quote_execution_clock")
        symbol = security.symbol
        try:
            bars = self._algorithm.current_slice.quote_bars
            quote = bars[symbol] if symbol in bars else None
        except Exception:
            raise targets.NewruleError("quote_execution_slice") from None
        require(quote is not None, "quote_execution_slice")
        def fields(bar):
            try:
                supported = isinstance(bar, self._quote_bar_type)
            except Exception:
                supported = False
            require(supported, "quote_execution_type")
            require(legacy._symbol_sid(bar.symbol, "quote identity") == legacy._symbol_sid(symbol, "security quote identity"), "quote_execution_identity")
            start, end = instant(bar.time), instant(bar.end_time)
            require(start.date() == now.date() and start.time().replace(tzinfo=None) == time(9, 30)
                    and end == now and (end - start).total_seconds() == 60, "quote_execution_period")
            require(bar.is_fill_forward is False, "quote_execution_fill_forward")
            require(bar.bid is not None and bar.ask is not None, "quote_execution_sides")
            try:
                bid, ask = number(bar.bid.close, positive=True), number(bar.ask.close, positive=True)
            except Exception:
                raise targets.NewruleError("quote_execution_sides") from None
            require(bid <= ask, "quote_execution_spread")
            return (start, end, bid, ask)
        observed = fields(quote)
        try:
            cached = security.cache.get_data[self._quote_bar_type]()
        except Exception:
            raise targets.NewruleError("quote_execution_cache") from None
        require(cached is not None, "quote_execution_cache")
        require(fields(cached) == observed, "quote_execution_cache_binding")
        try:
            bid, ask = number(security.bid_price, positive=True), number(security.ask_price, positive=True)
        except Exception:
            raise targets.NewruleError("quote_execution_security_sides") from None
        require((bid, ask) == observed[2:], "quote_execution_security_sides")
        return (bid, ask)

    def _current_execution_price(self, security, quantity):
        require(type(quantity) is int and quantity != 0, "quote_execution_quantity")
        bid, ask = self._quote_snapshot(security)
        return ask if quantity > 0 else bid

    def fee_basis(self, parameters):
        intent = self._intent
        if intent is None:
            return number(parameters.security.price, positive=True)
        order, security = parameters.order, parameters.security
        require(legacy._symbol_sid(order.symbol, "fee order symbol") == intent["qc_sid"]
                and legacy._symbol_sid(security.symbol, "fee security symbol") == intent["qc_sid"]
                and order.tag == intent["tag"] and number(order.quantity) == intent["quantity"],
                "quote_execution_fee_order")
        quote = number(intent["fee_basis_quote"], positive=True)
        require(self._now() == intent["dispatched_at"]
                and self._current_execution_price(security, intent["quantity"]) == quote,
                "quote_execution_fee_intent")
        return quote
