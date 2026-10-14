"""Accepted-risk retrospective 09:20/09:31 order comparison, never deployment.

Source provenance is authenticated by the package loader and actual LEAN
callbacks. Those checks do not establish immutable vendor history or a formal
security master. No forward-readiness policy is modified or admitted here.
"""

import hashlib
import itertools
import json
from datetime import datetime, time, timezone
from decimal import Decimal, ROUND_FLOOR, localcontext
from zoneinfo import ZoneInfo

try:
    import newrule_legacy_primitives as legacy
    import newrule_comparison_targets as targets
    import accepted_risk_preopen_rating_score as preopen
    import accepted_risk_order_level_core as core
    import accepted_risk_order_level_input_runtime as inputs
    import accepted_risk_preliminary_qc_figi as figi
    import accepted_risk_order_level_forced_exit as forced
except ImportError:
    from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as legacy
    from research.analyst_revisions_v2_qc import newrule_comparison_targets as targets
    from research.analyst_revisions_v2_qc import accepted_risk_preopen_rating_score as preopen
    from research.analyst_revisions_v2_qc import accepted_risk_order_level_core as core
    from research.analyst_revisions_v2_qc import accepted_risk_order_level_input_runtime as inputs
    from research.analyst_revisions_v2_qc import accepted_risk_preliminary_qc_figi as figi
    from research.analyst_revisions_v2_qc import accepted_risk_order_level_forced_exit as forced


SCHEMA = "arv2-accepted-risk-newrule-comparison-profile-v1"
STARTING_CASH = Decimal("1000000")
START_SESSION = "2021-01-04"
DECISION_CUTOFF = "2026-10-12"
END_SESSION = "2026-10-13"
NY = ZoneInfo("America/New_York")
META_STATISTIC = "ARV2_NEWRULE_META"
MONTHLY_STATISTIC = "ARV2_NEWRULE_MONTHLY"
FEE_RATE = Decimal("0.001")
MAX_STATISTIC_BYTES = 8192
MAX_ORDERS = 60000
MAX_ROWS = 25000
MAX_TOTAL_ROWS = 25000000
MAX_CACHE = 16


def require(value, code):
    targets.require(value, code)


def number(value, *, positive=False):
    return legacy._decimal(value, "newrule numeric value", positive=positive)


def instant(value):
    require(isinstance(value, datetime), "clock_type")
    return value.replace(tzinfo=NY) if value.tzinfo is None else value.astimezone(NY)


def weekly_axis(axis):
    require(type(axis) is tuple and axis and tuple(sorted(set(axis))) == axis,
            "session_axis")
    selected, seen = [], set()
    for session in axis:
        require(type(session) is str and len(session) == 10, "session_text")
        parsed = datetime.strptime(session, "%Y-%m-%d")
        require(parsed.date().isoformat() == session, "session_canonical")
        if START_SESSION <= session <= DECISION_CUTOFF:
            week = parsed.isocalendar()[:2]
            if week not in seen:
                selected.append(session)
                seen.add(week)
    require(selected and selected[0] == START_SESSION
            and selected[-1] == DECISION_CUTOFF and END_SESSION in axis,
            "weekly_geometry")
    return tuple(selected)


def make_profile(axis, *, package_sha256, lineage_sha256, universe_count,
                 ar_percent, source_pins):
    targets.cohort(universe_count)
    require(type(ar_percent) is int and ar_percent in targets.AR_PERCENTS, "arm")
    targets.require_sha(package_sha256)
    targets.require_sha(lineage_sha256)
    require(type(source_pins) is dict and source_pins and all(
        type(key) is str and key.endswith(".py") for key in source_pins), "source_pins")
    for value in source_pins.values():
        targets.require_sha(value)
    decisions = weekly_axis(axis)
    sessions = tuple(s for s in axis if START_SESSION <= s <= END_SESSION)
    require(axis[0] == "2013-01-02" and axis[-1] == END_SESSION
            and sessions[0] == START_SESSION and sessions[-1] == END_SESSION
            and axis.index(DECISION_CUTOFF) + 1 == axis.index(END_SESSION), "profile_axis")
    seed = {"schema": SCHEMA,
        "candidate_id": f"arv2-newrule-{universe_count}-ar{ar_percent}-2026-v1",
        "universe_count": universe_count, "ar_percent": ar_percent,
        "package_sha256": package_sha256, "lineage_sha256": lineage_sha256,
        "session_axis_sha256": targets.digest(axis), "session_count": len(axis),
        "evaluation_sessions": list(sessions), "decision_sessions": list(decisions),
        "source_pins": dict(sorted(source_pins.items())),
        "primary_view": targets.PRIMARY_VIEW,
        "alternative_view": "score_disagreement_only_not_realized_performance",
        "clock": "same_session_09:20_snapshot_09:31_market_submission_New_York",
        "rating_eligibility": "original_eligible_session_strictly_before_decision_session",
        "prices": "immediately_prior_NYSE_RAW_close;separate_pre0920_same_session_SplitOccurred_factor",
        "split_unit_bridge": "one_bounded_typed_Split_history_batch_midnight_to0920;QC_history_qualified_not_formal_PIT",
        "terminal": "Oct13_valuation_only_no_forced_rebalance",
        "gross_target": "0.98", "aggregate_stock_target_cap": "0.098",
        "fee_bps": "10", "slippage_model_bps": "0",
        "maximum_dynamic_subscriptions": 192, "maximum_reference_securities": 256,
        "maximum_reference_history_calls": 400,
        "whole_shares": True, "sell_before_buy": True,
        "point_in_time_proven": False, "formal_identity_admitted": False,
        "formal_forward_ready": False, "paper_or_live_ready": False,
        "accepted_risk": True, "backtest_only": True}
    return {**seed, "profile_sha256": targets.digest(seed)}


class NewruleComparisonDriver(legacy.AcceptedRiskSixUniverseOrderQcDriver):
    """One genuine single-portfolio arm; no legacy initializer or MOO executor."""

    def __init__(self, algorithm, *, profile, activation_manifest_key,
                 activation_manifest_sha256, activation_manifest_byte_count,
                 benchmark_symbol, etf_symbols, fundamental_universe,
                 constituent_universes, trade_bar_type, minute_resolution,
                 daily_resolution, raw_normalization, fee_model_factory,
                 slippage_model_factory, order_status_enum, order_status_to_int,
                 split_occurred_type, split_data_type):
        seed = dict(profile)
        supplied = seed.pop("profile_sha256", None)
        require(targets.digest(seed) == supplied and seed.get("schema") == SCHEMA,
                "profile_binding")
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
        self._minute_resolution = minute_resolution
        self._daily_resolution = daily_resolution
        self._raw_normalization = raw_normalization
        self._fee_model_factory = fee_model_factory
        self._slippage_model_factory = slippage_model_factory
        self._order_status_enum = order_status_enum
        self._order_status_to_int = order_status_to_int
        self._status_members = core.require_qc_order_status_enum_members(order_status_enum)
        require(tuple(order_status_to_int(member) for member, _ in self._status_members)
                == (0, 1, 2, 3, 5, 6, 7, 8, 9), "status_numbers")
        self._split_occurred_type = split_occurred_type
        self._split_data_type = split_data_type
        self._split_history_count = 0
        self._initialized = self._completed = self._emitted = False
        self._configured_sids, self._active_dynamic_sids = set(), set()
        self._security_by_sid, self._label_by_sid = {}, {}
        self._symbol_by_security, self._security_by_etf_sid = {}, {}
        self._maximum_active_dynamic_security_count = 0
        self._removed_dynamic_security_count = self._reference_history_call_count = 0
        self._account_observations, self._gross_exposure_observations = {}, {}
        self._cache = {key: [] for key in ("FUNDAMENTALS",) + targets.UNIVERSES}
        self._source_row_count = 0
        self._split_records_by_session = {}
        self._forced_ledger = forced.empty_forced_delisting_ledger()
        self._plans, self._executed, self._fills, self._split_path = {}, set(), [], []
        self._intent = None
        self._order_ids, self._event_ids = set(), set()
        self._fallback_counts, self._score_disagreement = {}, []
        self._cash_underfill_count = 0

    def initialize(self):
        require(not self._initialized and self._algorithm.live_mode is False, "backtest_only")
        require(tuple(self._etf_symbols) == targets.UNIVERSES
                and tuple(self._constituent_universes) == targets.UNIVERSES
                and self._fundamental_universe is not None, "common_source_universes")
        require(self._portfolio_equity() == STARTING_CASH
                and self._portfolio_cash() == STARTING_CASH, "starting_cash")
        package = inputs.load_accepted_risk_preliminary_package(self._algorithm,
            activation_manifest_key=self._activation_manifest_key,
            activation_manifest_sha256=self._activation_manifest_sha256,
            activation_manifest_byte_count=self._activation_manifest_byte_count)
        axis = tuple(package.evaluator_input.session_axis)
        expected = make_profile(axis, package_sha256=self._profile["package_sha256"],
            lineage_sha256=self._profile["lineage_sha256"],
            universe_count=self._profile["universe_count"], ar_percent=self._profile["ar_percent"],
            source_pins=self._profile["source_pins"])
        require(expected == self._profile, "loaded_profile_axis")
        # The host projection validates source_disposition == October lineage.
        # Its exact package hash commits that transport field; the unchanged
        # cloud loader exposes package/activation hashes, not disposition.
        require(package.package_sha256 == self._profile["package_sha256"]
                and package.activation_manifest_sha256 == self._activation_manifest_sha256,
                "loaded_package_binding")
        lineage = dict(package.evaluator_input.source_lineage_sha256s)
        resolution = figi.resolve_preliminary_qc_figis(package.runtime_symbol_bindings,
            expected_security_master_admission_sha256=lineage["security_master_admission_sha256"],
            composite_figi=self._algorithm.composite_figi, benchmark_symbol=self._benchmark_symbol)
        self._package, self._resolution = package, resolution
        self._session_axis = axis
        self._session_positions = {s: i for i, s in enumerate(axis)}
        self._evaluation_sessions = tuple(expected["evaluation_sessions"])
        self._decision_sessions = tuple(expected["decision_sessions"])
        self._decision_set = frozenset(self._decision_sessions)
        self._score = preopen.PreopenRatingScoreRuntime(package.evaluator_input,
            start_position=self._session_positions[START_SESSION])
        for row in resolution.resolved:
            sid, identity = row["qc_security_id"], row["security_id"]
            require(sid not in self._security_by_sid and identity not in self._symbol_by_security,
                    "figi_identity_collision")
            self._security_by_sid[sid] = identity
            self._label_by_sid[sid] = row["qc_display_ticker"]
            self._symbol_by_security[identity] = resolution.symbol_for_security(identity)
        for ticker, symbol in self._etf_symbols.items():
            sid = legacy._symbol_sid(symbol, "newrule own ETF")
            require(sid not in self._security_by_sid and sid not in self._security_by_etf_sid,
                    "own_etf_identity_collision")
            self._security_by_etf_sid[sid] = sid
            self._symbol_by_security[sid] = symbol
        self._initialized = True
        require(not self._current_holding_census(), "initial_holdings")
        for symbol in self._etf_symbols.values():
            self.configure_security(self._algorithm.securities[symbol])
        return True

    def configure_security(self, security):
        result = super().configure_security(security)
        security.set_leverage(1)
        return result

    def _now(self):
        return instant(self._algorithm.time)

    def _capture(self, source, collection):
        self._require_initialized()
        now = self._now()
        values = inputs.collection_rows(collection, "newrule source collection")
        require(len(values) <= MAX_ROWS, "source_rows")
        self._source_row_count += len(values)
        require(self._source_row_count <= MAX_TOTAL_ROWS, "total_source_rows")
        observed, ends, rows = set(), set(), []
        for row in values:
            sid = legacy._symbol_sid(row.symbol, "newrule callback")
            require(sid not in observed, "duplicate_callback_sid")
            observed.add(sid)
            end = instant(row.end_time)
            require(end <= now, "source_end_after_callback")
            ends.add(end.isoformat())
            label = row.symbol.value
            label = label if type(label) is str and label and label == label.strip() else None
            raw = row.market_cap if source == "FUNDAMENTALS" else row.weight
            try:
                numeric = number(raw) if raw is not None else None
            except (ValueError, TypeError):
                numeric = None
            if numeric is not None and (numeric <= 0 if source == "FUNDAMENTALS" else numeric < 0):
                numeric = None
            rows.append((sid, label, None if numeric is None else str(numeric)))
        require(len(ends) <= 1, "mixed_source_end_times")
        frozen = tuple(sorted(rows))
        end = next(iter(ends)) if ends else None
        record = (now.isoformat(), end, frozen)
        cache = self._cache[source]
        require(not cache or instant(datetime.fromisoformat(cache[-1][0])) <= now,
                "callback_clock_reversal")
        # Do not silently replace two conflicting renditions of one EndTime.
        for prior in cache:
            if end is not None and prior[1] == end:
                require(prior[2] == frozen, "same_end_time_revision")
        cache.append(record)
        if len(cache) > MAX_CACHE:
            del cache[0]
        return []

    def accept_fundamentals(self, values):
        return self._capture("FUNDAMENTALS", values)

    def accept_constituents(self, ticker, values):
        require(type(ticker) is str and ticker in targets.UNIVERSES, "universe")
        return self._capture(ticker, values)

    def _collection(self, source, cutoff):
        prior = [row for row in self._cache[source]
                 if datetime.fromisoformat(row[0]) < cutoff]
        if not prior:
            return (), None
        row = prior[-1]
        if row[1] is None:
            return (), row
        end = datetime.fromisoformat(row[1])
        age = (cutoff.date() - end.astimezone(NY).date()).days
        if end >= cutoff or not 0 <= age <= (4 if source == "FUNDAMENTALS" else 10):
            return (), row
        return row[2], row

    def _books(self, session):
        cutoff = datetime.combine(datetime.strptime(session, "%Y-%m-%d").date(), time(9, 20), NY)
        snapshot = self._score.score_session(session)
        scores = snapshot.primary_view_firm_specific_scores
        active = {row.security_id for row in snapshot.memberships}
        require(len(active) == len(snapshot.memberships), "active_membership_collision")
        fundamentals, fundamental_context = self._collection("FUNDAMENTALS", cutoff)
        by_sid = {sid: (label, cap) for sid, label, cap in fundamentals}
        result, contexts = [], {"FUNDAMENTALS": fundamental_context}
        for ticker in targets.UNIVERSES:
            members, context = self._collection(ticker, cutoff)
            contexts[ticker] = context
            reason = None if fundamentals and members else "missing_or_stale_collection"
            if any(weight is None for _, _, weight in members):
                reason = "unresolved_reported_weight"
            frozen = []
            for sid, label, weight in members:
                fundamental_label, cap = by_sid.get(sid, (None, None))
                economic = self._security_by_sid.get(sid)
                economic = economic if economic in active else None
                frozen.append(targets.Member(sid, label, fundamental_label,
                    Decimal(weight) if weight is not None else Decimal(0), economic,
                    self._label_by_sid.get(sid) if economic is not None else None,
                    Decimal(cap) if economic is not None and cap is not None else None,
                    scores.get(economic) if economic is not None else None))
            own = legacy._symbol_sid(self._etf_symbols[ticker], "newrule own ETF")
            result.append(targets.Book(ticker, own, tuple(frozen), reason))
        books = tuple(result)
        view_maps = {view: snapshot.scores_by_axis[(view, "firm_specific")]
                     for view in preopen._r055.SOURCE_VIEW_IDS}
        left, right = (view_maps[view] for view in preopen._r055.SOURCE_VIEW_IDS)
        both = set(left) & set(right)
        self._score_disagreement.append((session, len(set(left) ^ set(right)),
            sum(left[key] != right[key] for key in both)))
        context = {"session": session, "cutoff": cutoff.isoformat(),
            "package_sha256": self._profile["package_sha256"],
            "lineage_sha256": self._profile["lineage_sha256"],
            "input_books_sha256": targets.book_digest(books),
            "callbacks_sha256": targets.digest(contexts),
            "score_views_sha256": targets.digest({view: sorted((key, str(value)) for key, value in values.items())
                for view, values in view_maps.items()}),
            "qc_callback_is_vendor_availability": False, "formal_identity_admitted": False}
        return books, targets.digest(context)

    def on_before_open(self):
        self._require_initialized()
        now = self._now()
        session = now.date().isoformat()
        if session not in self._decision_set:
            return None
        require(now.time().replace(tzinfo=None) == time(9, 20), "decision_clock")
        require(session not in self._plans and self._intent is None
                and self._algorithm.live_mode is False, "decision_once")
        books, context_sha = self._books(session)
        target = targets.build_target(books, universe_count=self._profile["universe_count"],
            ar_percent=self._profile["ar_percent"], source_snapshot_sha256=context_sha)
        require(target.input_books_sha256 == targets.book_digest(books), "runtime_book_binding")
        holdings = self._current_holding_census()
        weights = {sid: weight for sid, _, weight in target.weights}
        census = tuple(sorted(set(weights) | set(holdings)))
        self._prune_execution_subscriptions(set(census))
        previous = self._session_axis[self._session_positions[session] - 1]
        references = self._reference_prices(previous, census)
        equity = self._portfolio_equity()
        factors, split_binding = self._split_factors(census, now)
        quantities = {}
        with localcontext() as arithmetic:
            arithmetic.prec = 96
            for sid in census:
                factor = factors[sid]
                price = references[sid] * factor
                require(price > 0 and price.is_finite(), "split_price_units")
                quantities[sid] = int((equity * weights.get(sid, Decimal(0)) / price)
                                      .to_integral_value(rounding=ROUND_FLOOR))
        binding = {"session": session, "target_sha256": target.target_sha256,
            "context_sha256": context_sha, "books_sha256": target.input_books_sha256,
            "raw_reference_session": previous, "raw_closes": sorted((s, str(p)) for s, p in references.items()),
            "same_session_split_factors": sorted((s, str(f)) for s, f in factors.items()),
            "split_history_sha256": split_binding,
            "quantities": sorted(quantities.items()), "holdings": sorted(holdings.items()),
            "equity": str(equity), "cash": str(self._portfolio_cash())}
        self._plans[session] = {"binding": binding, "sha256": targets.digest(binding),
            "quantities": quantities, "holdings": holdings, "split_records": dict(
                self._split_records_by_session.get(session, {})), "target": target}
        for sleeve in target.record()["sleeves"]:
            for code in sleeve["refusals"]:
                key = sleeve["universe"] + ":" + code
                self._fallback_counts[key] = self._fallback_counts.get(key, 0) + 1
        return target.target_sha256

    def _split_factors(self, census, cutoff):
        """Qualify today's share units before freezing a prior-RAW-close plan.

        New subscriptions may not have received midnight callbacks. A bounded
        exact typed history query covers them; an empty completed result means
        none *under QC's retrospective data*, never an independent PIT proof.
        """
        require(type(census) is tuple and 0 < len(census) <= 256
                and tuple(sorted(set(census))) == census and cutoff == self._now(),
                "split_history_census")
        symbols = [self._symbol_for_security(identity) for identity in census]
        by_sid = {legacy._symbol_sid(symbol, "split history symbol"): identity
                  for symbol, identity in zip(symbols, census, strict=True)}
        require(len(by_sid) == len(census), "split_history_sid_collision")
        start = datetime.combine(cutoff.date(), time(0))
        end = cutoff.replace(tzinfo=None)
        self._split_history_count += 1
        require(self._split_history_count <= 400, "split_history_call_bound")
        response = self._algorithm.history[self._split_data_type](symbols, start, end,
            self._daily_resolution, fill_forward=False, extended_market_hours=False)
        batches = tuple(itertools.islice(iter(response), 513))
        require(len(batches) <= 512, "split_history_batch_bound")
        observed, rows = {}, []
        total_rows = 0
        for batch in batches:
            batch_time = instant(batch.time)
            require(batch_time.date() == cutoff.date() and batch_time < cutoff, "split_history_batch_clock")
            items = tuple(itertools.islice(iter(batch.items()), 257))
            require(len(items) <= 256, "split_history_row_bound")
            total_rows += len(items)
            require(total_rows <= 512, "split_history_total_bound")
            for symbol, event in items:
                sid = legacy._symbol_sid(symbol, "split history key")
                identity = by_sid.get(sid)
                require(identity is not None and legacy._symbol_sid(event.symbol, "split history payload") == sid,
                        "split_history_identity")
                event_time, event_end = instant(event.time), instant(event.end_time)
                require(event_time.date() == cutoff.date() and event_time <= event_end < cutoff,
                        "split_history_event_clock")
                if event.type != self._split_occurred_type:
                    continue  # Warning never supplies an economic adjustment.
                require(identity not in observed, "split_history_duplicate")
                factor = number(event.split_factor, positive=True)
                observed[identity] = factor
                rows.append([identity, str(factor), event_time.isoformat(), event_end.isoformat()])
        callbacks = self._split_records_by_session.get(cutoff.date().isoformat(), {})
        for identity in census:
            if identity in callbacks:
                require(identity in observed and Decimal(callbacks[identity]["factor"]) == observed[identity],
                        "split_callback_history_conflict")
        factors = {identity: observed.get(identity, Decimal(1)) for identity in census}
        binding = targets.digest({"query_start": instant(start).isoformat(), "query_end": cutoff.isoformat(),
            "census": list(census), "rows": sorted(rows), "batches": len(batches),
            "total_rows": total_rows, "complete_typed_query": True,
            "qc_retrospective_absence_qualification": True, "point_in_time_proven": False})
        return factors, binding

    def on_splits(self, splits):
        self._require_initialized()
        now = self._now()
        session = now.date().isoformat()
        records = self._split_records_by_session.setdefault(session, {})
        for symbol, split in tuple(splits.items()):
            if split.type != self._split_occurred_type:
                continue
            sid = legacy._symbol_sid(symbol, "newrule split")
            require(legacy._symbol_sid(split.symbol, "newrule split payload") == sid,
                    "split_sid")
            identity = self._security_by_sid.get(sid, self._security_by_etf_sid.get(sid))
            if identity is None:
                continue
            factor = number(split.split_factor, positive=True)
            event_time = instant(split.time)
            require(event_time.date() == now.date() and event_time <= now, "split_event_clock")
            record = {"factor": str(factor), "received": now.isoformat(), "event_time": event_time.isoformat()}
            require(identity not in records, "duplicate_split_occurrence")
            if session in self._decision_set:
                require(now.time().replace(tzinfo=None) < time(9, 20), "split_not_predecision")
            records[identity] = record
            self._split_path.append((session, hashlib.sha256(identity.encode("utf-8")).hexdigest(), record))

    def _status(self, status):
        result = core.qc_order_status_enum_text(status, self._status_members)
        require(result is not None, "order_status")
        return result

    def on_order_event(self, event):
        self._require_initialized()
        require(self._algorithm.live_mode is False, "backtest_only")
        status = self._status(event.status)
        engine = self._algorithm.transactions.get_order_by_id(event.order_id)
        require(engine is not None and engine.id == event.order_id, "engine_order_binding")
        intent = self._intent
        if intent is None:
            return self._external_order_event(event, engine, status)
        require(legacy._symbol_sid(event.symbol, "newrule order event") == intent["qc_sid"]
                and engine.tag == intent["tag"] and number(engine.quantity) == intent["quantity"],
                "order_intent_binding")
        require(type(event.order_id) is int and type(event.id) is int
                and event.order_id > 0 and event.id >= 0, "order_event_ids")
        pair = (event.order_id, event.id)
        require(pair not in self._event_ids, "duplicate_order_event")
        self._event_ids.add(pair)
        require(intent["order_id"] in (None, event.order_id), "intent_order_id")
        intent["order_id"] = event.order_id
        if status in ("New", "Submitted"):
            require(number(event.fill_quantity) == 0, "nonfill_quantity")
            return None
        require(status == "Filled" and intent["fill"] is None, "nonterminal_or_partial_order")
        quantity, price = number(event.fill_quantity), number(event.fill_price, positive=True)
        fee = event.order_fee.value
        fee_amount = number(fee.amount)
        require(quantity == intent["quantity"] and fee.currency == "USD" and fee_amount >= 0,
                "fill_quantity_or_fee")
        expected_fee = Decimal(intent["fee_basis_quote"]) * abs(quantity) * FEE_RATE
        # LEAN may cross its decimal/double fee bridge; one ten-millionth of
        # a dollar is the fixed absolute tolerance, never a percentage waiver.
        require(abs(fee_amount - expected_fee) <= Decimal("0.0000001"), "configured_fee_mismatch")
        fill_time = instant(event.utc_time.replace(tzinfo=timezone.utc)
                            if event.utc_time.tzinfo is None else event.utc_time)
        require(intent["dispatched_at"] <= fill_time <= self._now(), "fill_clock")
        intent["fill"] = {"quantity": int(quantity), "price": str(price),
            "fee": str(fee_amount), "fill_time": fill_time.isoformat(),
            "order_id": event.order_id, "event_id": event.id}
        return None

    def _current_execution_price(self, security):
        now = self._now()
        data = security.get_last_data()
        require(data is not None and instant(data.end_time) == now, "execution_price_not_current_minute")
        return number(security.price, positive=True)

    def _submit_market(self, identity, quantity, session):
        require(type(quantity) is int and quantity != 0 and self._intent is None,
                "order_quantity")
        require(len(self._order_ids) < MAX_ORDERS and self._algorithm.live_mode is False,
                "order_bound_or_live")
        symbol, security = self._ensure_security(identity)
        quote = self._current_execution_price(security)
        before_quantity, before_cash = self._current_quantity(identity), self._portfolio_cash()
        tag = "ARV2N-" + self._plans[session]["sha256"][:16] + "-" + str(len(self._order_ids))
        intent = {"identity": identity, "qc_sid": legacy._symbol_sid(symbol, "newrule intent"),
            "quantity": quantity, "tag": tag, "order_id": None, "fill": None,
            "dispatched_at": self._now(), "fee_basis_quote": str(quote)}
        self._intent = intent  # Install before the re-entrant synchronous callback.
        ticket = self._algorithm.market_order(symbol, quantity, asynchronous=False, tag=tag)
        require(ticket is not None and self._status(ticket.status) == "Filled"
                and intent["fill"] is not None and ticket.order_id == intent["order_id"],
                "market_ticket_not_complete")
        require(ticket.order_id not in self._order_ids, "duplicate_ticket")
        fill = intent["fill"]
        expected_cash = before_cash - Decimal(quantity) * Decimal(fill["price"]) - Decimal(fill["fee"])
        require(self._current_quantity(identity) == before_quantity + quantity
                and expected_cash >= 0 and abs(self._portfolio_cash() - expected_cash) <= Decimal("0.0000001"),
                "fill_cash_or_holdings_reconciliation")
        self._order_ids.add(ticket.order_id)
        self._fills.append({"session": session, "security_id_sha256": hashlib.sha256(identity.encode()).hexdigest(),
            "submission_time": intent["dispatched_at"].isoformat(),
            "fee_basis_quote": intent["fee_basis_quote"], **fill})
        self._intent = None

    def on_after_open(self):
        self._require_initialized()
        now, session = self._now(), self._now().date().isoformat()
        if session not in self._decision_set:
            return None
        require(now.time().replace(tzinfo=None) == time(9, 31), "execution_clock")
        require(session in self._plans and session not in self._executed
                and self._intent is None and self._algorithm.live_mode is False, "execution_once")
        plan = self._plans[session]
        require(self._current_holding_census() == plan["holdings"]
                and self._split_records_by_session.get(session, {}) == plan["split_records"],
                "between_decision_execution_drift")
        desired = plan["quantities"]
        # No buy may begin before every necessary sell completed/reconciled.
        for identity in sorted(desired):
            difference = desired[identity] - self._current_quantity(identity)
            if difference < 0:
                self._submit_market(identity, difference, session)
        for identity in sorted(desired):
            difference = desired[identity] - self._current_quantity(identity)
            if difference <= 0:
                continue
            _, security = self._ensure_security(identity)
            price = self._current_execution_price(security)
            available = int((self._portfolio_cash() / (price * (1 + FEE_RATE)))
                            .to_integral_value(rounding=ROUND_FLOOR))
            quantity = min(difference, max(0, available))
            if quantity != difference:
                self._cash_underfill_count += 1
            if quantity:
                self._submit_market(identity, quantity, session)
        require(not tuple(self._algorithm.transactions.get_open_orders()), "pending_orders")
        self._portfolio_cash()
        require(all(quantity >= 0 for quantity in self._current_holding_census().values()), "short_holdings")
        self._executed.add(session)
        return plan["sha256"]

    def on_after_close(self):
        self._require_initialized()
        session = self._now().date().isoformat()
        if session not in self._evaluation_sessions:
            return None
        require(self._now().time().replace(tzinfo=None) >= time(13), "close_clock")
        if session in self._decision_set:
            require(session in self._executed, "unexecuted_decision")
        require(self._intent is None and not tuple(self._algorithm.transactions.get_open_orders()), "close_pending_orders")
        self._observe_account(session)

    def on_data(self, data):
        self._require_initialized()

    def on_end_of_algorithm(self):
        self._require_initialized()
        require(not self._emitted and self._intent is None
                and tuple(sorted(self._plans)) == self._decision_sessions
                and tuple(sorted(self._executed)) == self._decision_sessions
                and tuple(sorted(self._account_observations)) == self._evaluation_sessions
                and not tuple(self._algorithm.transactions.get_open_orders()), "incomplete_terminal_geometry")
        require(self._now().date().isoformat() >= END_SESSION, "terminal_clock")
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
        meta = {"schema": "arv2-newrule-comparison-result-v1",
            "candidate_id": self._profile["candidate_id"], "profile_sha256": self._profile["profile_sha256"],
            "package_sha256": self._profile["package_sha256"], "lineage_sha256": self._profile["lineage_sha256"],
            "decision_count": len(self._plans), "evaluation_session_count": len(self._evaluation_sessions),
            "order_count": len(self._order_ids), "fill_count": len(self._fills),
            "raw_reference_history_calls": self._reference_history_call_count,
            "split_unit_history_calls": self._split_history_count,
            "common_source_path_sha256": targets.digest([self._plans[s]["binding"]["context_sha256"] for s in self._decision_sessions]),
            "plan_path_sha256": targets.digest([self._plans[s]["sha256"] for s in self._decision_sessions]),
            "fill_path_sha256": targets.digest(self._fills), "split_path_sha256": targets.digest(self._split_path),
            "account_path_sha256": targets.digest([(s, str(self._account_observations[s])) for s in self._evaluation_sessions]),
            "cash_constrained_buy_count": self._cash_underfill_count,
            "coverage_fallback_counts": self._fallback_counts,
            "alternative_view_diagnostic_sha256": targets.digest(self._score_disagreement),
            "alternative_view_eligibility_disagreements": sum(row[1] for row in self._score_disagreement),
            "alternative_view_score_disagreements": sum(row[2] for row in self._score_disagreement),
            "forced_delisting": forced.forced_delisting_summary(self._forced_ledger),
            "actual_terminal": "runtime_geometry_complete_not_independent_source_admission",
            "point_in_time_proven": False, "formal_identity_admitted": False,
            "formal_forward_ready": False, "paper_or_live_ready": False}
        monthly_record = {"schema": "arv2-newrule-monthly-return-v1", "candidate_id": self._profile["candidate_id"],
            "profile_sha256": self._profile["profile_sha256"], "months": monthly,
            "last_month_partial": True, "alternative_view_realized_performance": False}
        for name, record in ((META_STATISTIC, meta), (MONTHLY_STATISTIC, monthly_record)):
            payload = targets.canonical(record)
            require(len(payload) <= MAX_STATISTIC_BYTES, "statistic_bound")
            self._algorithm.set_summary_statistic(name, payload.decode("ascii"))
        self._completed = self._emitted = True
        return meta, monthly_record
