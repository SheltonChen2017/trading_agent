"""Owner-authorized cap-selected, weight-only TPR development successor.

Old executed stock/matched templates remain immutable and unaccepted gates
remain parked. This genuine portfolio experiment is not a fourth old retry.
Native cap clocks, membership, covered-subset limitations and exact selected
IDs are frozen before scores are consulted. TPR cannot change admission.
Original RAW order/accounting custody is retained. A new explicit ambient
observer qualifies only this source-bound experiment, never old outcomes.
"""
from AlgorithmImports import *
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json

import proxy_core as core
import cap_tilt
import cap_observer
from zoneinfo import ZoneInfo

EXPECTED_MATCHED_FREEZE_SHA256 = "__MATCHED_FREEZE_SHA256__"
EXPECTED_MATCHED_CONFIG_SHA256 = "__MATCHED_CONFIG_SHA256__"
STUDY = "TPR-CAP-TILT-20261009-v1"
ETFS = ("SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX")
CANDIDATES = {
    ("tpr_on", "baseline"): ("TPR-CAP-TILT-ON-BASE-v1", "0.001"),
    ("tpr_off", "baseline"): ("TPR-CAP-TILT-OFF-BASE-v1", "0.001"),
}
DECISIONS, CUTOFFS = core.DECISIONS, core.CUTOFFS
UTC, NY = timezone.utc, core.NY
MAX_SUBSCRIPTIONS = 4096


def validate_config(config_json, config_hash, freeze_hash):
    config = core._json(config_json, config_hash)
    core._keys(config, ("schema", "study_id", "freeze_sha256", "candidate_id",
                       "arm", "cost", "slippage"))
    key = (config["arm"], config["cost"])
    if (config["schema"] != "tpr-qc-cap-tilt-config-v1"
            or config["study_id"] != STUDY
            or config["freeze_sha256"] != core._hash(freeze_hash)
            or key not in CANDIDATES
            or (config["candidate_id"], config["slippage"]) != CANDIDATES[key]):
        raise ValueError("configuration is not a frozen cap-tilt arm")
    return config


def native_fraction(value):
    """Capture engine values at their represented precision; then rational only.

    .NET decimal formatting is invariant-culture. Python float exposure by a
    LEAN binding is captured as its decimal text, NOT claimed to recover extra
    market precision. No binary floating arithmetic sizes or accounts money.
    Native slippage percentages are separately passed as exact .NET decimals.
    """
    if isinstance(value, Fraction):
        return value
    if hasattr(value, "ToString"):
        from System.Globalization import CultureInfo
        text = value.ToString(CultureInfo.InvariantCulture)
    elif type(value) in (str, int, float, Decimal):
        text = str(value)
    else:
        raise ValueError("unsupported native numeric boundary")
    return core._number(text)


def _member_inventory(members):
    """Native identities and weights only; unknown weights stay explicit."""
    seen, tickers = set(), set()
    coverage = {name: {"count": 0, "weight": Fraction(0)} for name in
                ("known_weight", "unknown_weight", "zero_weight")}
    eligible = []
    for member in members:
        sid = str(member["symbol"].id)
        ticker = member["ticker"]
        if not sid or sid in seen or ticker in tickers:
            raise ValueError("ambiguous native membership identity")
        seen.add(sid)
        tickers.add(ticker)
        if member["weight"] is None:
            coverage["unknown_weight"]["count"] += 1
            continue
        weight = core._number(member["weight"])
        if not 0 <= weight <= 1:
            raise ValueError("membership weight outside bounds")
        category = "known_weight" if weight else "zero_weight"
        coverage[category]["count"] += 1
        coverage[category]["weight"] += weight
        if weight:
            eligible.append((sid, weight, member["symbol"]))
    return eligible, coverage


def plan_weighted_orders(weights, holdings, marks, nav, cash, slippage, *, etf_arm=False):
    """Prior-close soft targets, exact budget/volume caps, no sale recycling."""
    nav, cash, slippage = map(Fraction, (nav, cash, slippage))
    if nav <= 0 or cash < 0 or slippage not in (Fraction(1, 1000), Fraction(3, 2000)):
        raise ValueError("invalid frozen sizing input")
    limit = Fraction(1, 6) if etf_arm else Fraction(1, 10)
    if (any(type(sid) is not str or not sid for sid in weights)
            or any(not 0 < Fraction(weight) <= limit for weight in weights.values())
            or sum(map(Fraction, weights.values()), Fraction(0)) > 1):
        raise ValueError("invalid target weights")
    budget, result = cash * Fraction(97, 100), []
    for sid in sorted(set(weights) | set(holdings)):
        held = holdings.get(sid, 0)
        if type(held) is not int or held < 0:
            raise ValueError("whole long shares required")
        if sid not in marks:
            result.append({"security_id": sid, "requested": None,
                           "submitted": 0, "reason": "missing_mark"})
            continue
        close, volume = map(Fraction, marks[sid])
        if close <= 0 or volume < 0:
            raise ValueError("invalid prior mark")
        target = int(nav * Fraction(weights.get(sid, 0)) / close)
        delta, cap = target - held, int(volume / 100)
        quantity = min(abs(delta), cap) * (1 if delta >= 0 else -1)
        result.append({"security_id": sid, "requested": delta, "submitted": quantity,
                       "reason": "volume_cap" if abs(quantity) < abs(delta) else "complete"})
    result.sort(key=lambda row: (row["submitted"] >= 0, row["security_id"]))
    for row in result:
        if row["submitted"] <= 0:
            continue
        per_share = Fraction(marks[row["security_id"]][0]) * (1 + slippage) + Fraction(1, 100)
        affordable = int(budget / per_share)
        if row["submitted"] > affordable:
            row["submitted"] = affordable
            row["reason"] = ("cash_buffer" if row["reason"] == "complete"
                             else "volume_and_cash_buffer")
        budget -= row["submitted"] * per_share
    return result


def split_basis_with_custody(custody_since, cutoff, factor, *, delisted=False):
    if (custody_since is None or custody_since.tzinfo is None
            or custody_since > cutoff - timedelta(days=7) or delisted):
        return None
    factor = Fraction(1) if factor is None else Fraction(factor)
    return factor if factor > 0 else None


class TargetPriceCapTiltAlgorithm(core.TargetPriceSixUniverseAlgorithm):
    def initialize(self):
        if self.live_mode:
            raise ValueError("cap-tilt exploratory backtest only; live refused")
        from matched_config import CONFIG_JSON
        self._config = validate_config(CONFIG_JSON, EXPECTED_MATCHED_CONFIG_SHA256,
                                       EXPECTED_MATCHED_FREEZE_SHA256)
        self._identities, self._frames = {}, {}
        if self._config["arm"] == "tpr_on":
            from signal_packet import CONFIG_JSON as SIGNAL_CONFIG_JSON
            key = f"tpr-cap-tilt/{STUDY}/{core._hash(core.EXPECTED_PACKET_SHA256)}.json"
            if core.EXPECTED_PACKET_KEY != key or not self.object_store.contains_key(key):
                raise ValueError("fresh cap-tilt private packet missing")
            _, self._identities, self._frames = core.validate_inputs(
                SIGNAL_CONFIG_JSON, self.object_store.read(key),
                core.EXPECTED_CONFIG_SHA256, core.EXPECTED_PACKET_SHA256)
        self.set_start_date(2025, 1, 2)
        self.set_end_date(2025, 3, 31)
        self.set_time_zone("America/New_York")
        self.set_account_currency("USD")
        self.set_cash(100000)
        self._snapshots = {etf: [] for etf in ETFS}
        self._cap_snapshots, self._cap_callback_count = [], 0
        self._event_zones, self._ever_filled_ids, self._ever_targeted_ids = {}, set(), set()
        self._fill_history_unknown = False
        self._delisting_audit = cap_observer.empty_audit()
        self._symbols, self._split_factors, self._custody_since = {}, {}, {}
        self._warmup_finished_minute_validated = False
        self._context_symbols = set()
        self._context_initializer_skips = self._context_change_skips = 0
        self._benchmark_internal_config_max = 0
        self._delisted_ids, self._manual_symbols, self._valuation_days = set(), set(), set()
        self._targets, self._target_weights, self._decision_coverage, self._tickets = {}, {}, {}, []
        self._attempted_days, self._reasons = set(), {}
        self._cash_ledger, self._quantity_ledger, self._dividend_keys = Fraction(100000), {}, set()
        self._prior_close_nav, self._prior_close_day = Fraction(100000), None
        self._fees, self._fill_events, self._submitted = Fraction(0), 0, 0
        self._requested_shares = self._submitted_shares = self._filled_shares = 0
        self._max_cash_residual = self._max_nav_residual = Fraction(0)
        self._decision_count = self._refused_count = self._position_ledger_mismatches = 0
        self._risk_breaches, self._name_soft_cap_breaches = 0, 0
        self._max_name_exposure = Fraction(0)
        self._sleeve_selected_decisions = {etf: 0 for etf in ETFS}
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.MINUTE
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self.add_security_initializer(self._initialize_security)
        self._etf_symbols = {}
        for etf in ETFS:
            symbol = self.add_equity(etf, Resolution.MINUTE, extended_market_hours=etf == "SPY",
                                     data_normalization_mode=DataNormalizationMode.RAW).symbol
            self._etf_symbols[etf] = symbol
            self._symbols[str(symbol.id)] = symbol
            universe = self.universe.etf(symbol,
                universe_filter_func=lambda rows, label=etf: self._constituents_for(label, rows))
            # LEAN ETF context symbols inherit Equity type. Their exact native
            # identities, not a prefix/type heuristic, separate them from money.
            self._context_symbols.add(universe.symbol)
            self.add_universe(universe)
        cap_universe = self.add_universe(self._capture_caps)
        self._cap_context_symbol = cap_universe.symbol
        self._context_symbols.add(cap_universe.symbol)
        self._benchmark = self._clock_symbol = self._etf_symbols["SPY"]
        self.set_benchmark(self._benchmark)
        self.set_warm_up(timedelta(days=31), Resolution.DAILY)
        self.schedule.on(self.date_rules.every_day(self._benchmark), self.time_rules.at(9, 20), self._rebalance)
        self.schedule.on(self.date_rules.every_day(self._benchmark), self.time_rules.at(9, 35), self._cancel_day_orders)
        self.schedule.on(self.date_rules.every_day(self._benchmark), self.time_rules.at(16, 1), self._daily_audit)

    def _initialize_security(self, security):
        if security.symbol in self._context_symbols:
            self._context_initializer_skips += 1
            return
        security.set_leverage(1)
        security.set_fee_model(core.CentPerShareFee())
        # LEAN's constructor accepts System.Decimal; transport the unchanged
        # frozen percentage directly, without a Python float intermediate.
        from System import Decimal as NetDecimal
        from System.Globalization import CultureInfo
        slippage = NetDecimal.Parse(self._config["slippage"], CultureInfo.InvariantCulture)
        security.set_slippage_model(ConstantSlippageModel(slippage))
        security.set_settlement_model(ImmediateSettlementModel())

    def _constituents_for(self, etf, constituents):
        rows = list(constituents)
        if not rows:
            self._reason("empty_membership_callback_" + etf)
            return Universe.UNCHANGED
        now = self.utc_time.replace(tzinfo=UTC)
        effective = max(row.end_time.replace(tzinfo=UTC) for row in rows)
        if effective > now:
            raise ValueError("future membership callback")
        members = [{"ticker": row.symbol.value, "symbol": row.symbol,
                    "weight": None if row.weight is None else core._text(native_fraction(row.weight))}
                   for row in rows]
        _member_inventory(members)
        self._snapshots[etf].append({"effective": effective, "received": now, "members": members})
        self._snapshots[etf] = [row for row in self._snapshots[etf]
                                if now - row["effective"] <= timedelta(days=45)]
        # Pre-subscribe membership, not just the eventual winners: the 7-day
        # lag is also the minimum corporate-action custody interval. Persisted
        # manual subscriptions below prevent removals from losing action data.
        return [member['symbol'] for member in members]

    def _configuration_inventory(self, configs):
        """Aggregate native metadata only: no symbols, rows, prices or clocks."""
        inventory = {}
        for config in configs:
            label = ":".join((("internal" if config.is_internal_feed else "external"),
                str(config.data_normalization_mode), str(config.resolution),
                str(config.tick_type), config.type.FullName,
                ("custom" if config.is_custom_data else "native"),
                ("ff" if config.fill_data_forward else "noff")))
            inventory[label] = inventory.get(label, 0) + 1
        return json.dumps(inventory, sort_keys=True, separators=(",", ":"))

    def _is_isolated_benchmark_config(self, config, symbol, security):
        # LEAN creates a separate benchmark Security/cache, while the global
        # registry includes its internal config under the same native symbol ID.
        # Only that engine-defined Hour Adjusted TradeBar signature is exempt.
        if (symbol != self._benchmark or config.symbol != symbol
                or not config.is_internal_feed
                or config.data_normalization_mode != DataNormalizationMode.ADJUSTED
                or config.resolution != Resolution.HOUR or config.tick_type != TickType.TRADE
                or config.type.FullName != "QuantConnect.Data.Market.TradeBar"
                or config.is_custom_data or config.fill_data_forward):
            return False
        benchmark_security = getattr(self.benchmark, "security", None)
        if benchmark_security is None or benchmark_security.symbol != symbol:
            return False
        from System import Object as NetObject
        # Native reference identity is mandatory; no Python-proxy identity or
        # synthetic fallback can grant the isolation exception in production.
        return (not NetObject.ReferenceEquals(benchmark_security, security)
                and not NetObject.ReferenceEquals(benchmark_security.cache, security.cache))

    def _raw_security_configs(self, symbol):
        if symbol in self._context_symbols:
            raise ValueError("RAW custody refused: registered universe context is not tradable")
        if symbol not in self.securities:
            raise ValueError("RAW custody refused: missing exact security")
        security = self.securities[symbol]
        if security.symbol != symbol:
            raise ValueError("RAW custody refused: changed exact security identity")
        service = self.subscription_manager.subscription_data_config_service
        configs = list(service.get_subscription_data_configs(symbol, True))
        inventory = self._configuration_inventory(configs)
        self._raw_config_inventory = inventory
        if any(config.symbol != symbol for config in configs):
            raise ValueError("RAW custody refused: changed exact configuration identity; inventory=" + inventory)
        external = [config for config in configs if not config.is_internal_feed]
        nonraw = sum(config.data_normalization_mode != DataNormalizationMode.RAW for config in external)
        if nonraw:
            raise ValueError("RAW custody refused: non-RAW configurations count=" + str(nonraw)
                             + "; external; inventory=" + inventory)
        internal_nonraw = [config for config in configs if config.is_internal_feed
                           and config.data_normalization_mode != DataNormalizationMode.RAW]
        unrecognized = [config for config in internal_nonraw
                        if not self._is_isolated_benchmark_config(config, symbol, security)]
        if unrecognized:
            raise ValueError("RAW custody refused: unrecognized non-RAW internal configurations count="
                             + str(len(unrecognized)) + "; inventory=" + inventory)
        self._benchmark_internal_config_max = max(self._benchmark_internal_config_max, len(internal_nonraw))
        if security.data_normalization_mode != DataNormalizationMode.RAW:
            raise ValueError("RAW custody refused: non-RAW security normalization; inventory=" + inventory)
        # Internal data never establishes observed RAW money/action custody.
        return security, external

    def _assert_raw_subscriptions(self, symbol):
        security, configs = self._raw_security_configs(symbol)
        # Warm-up may expose RAW daily feeds or defer the active registry until
        # an actual slice. Neither is permission to assume an observed feed.
        if self.is_warming_up:
            return security
        if not configs:
            raise ValueError("active RAW minute trade subscription required: no RAW configurations; "
                             + "inventory=" + self._raw_config_inventory)
        active = [config for config in configs if not config.is_internal_feed]
        minute = sum(config.resolution == Resolution.MINUTE and config.tick_type == TickType.TRADE
                     for config in active)
        if not minute:
            daily = sum(config.resolution == Resolution.DAILY and config.tick_type == TickType.TRADE
                        for config in active)
            raise ValueError("active RAW minute trade subscription required: no minute trade; "
                             + "active=" + str(len(active)) + "; daily_trade=" + str(daily)
                             + "; internal=" + str(len(configs) - len(active))
                             + "; inventory=" + self._raw_config_inventory)
        return security

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            if security.type != SecurityType.EQUITY:
                continue
            symbol = security.symbol
            if symbol in self._context_symbols:
                self._context_change_skips += 1
                continue
            security.set_data_normalization_mode(DataNormalizationMode.RAW)
            self._ensure_raw_subscription(symbol)
            self._symbols[str(symbol.id)] = symbol
            # Mere manager/configuration presence never starts action custody.
            # Only a subsequently observed RAW bar/action can establish it.

    def _observe_raw_custody(self, symbol):
        if symbol in self._context_symbols:
            return
        sid = str(symbol.id)
        if sid not in self._symbols or sid in self._custody_since:
            return
        _, configs = self._raw_security_configs(symbol)
        active_trade = [config for config in configs if not config.is_internal_feed
                        and config.tick_type == TickType.TRADE
                        and config.resolution in (Resolution.MINUTE, Resolution.DAILY)]
        if not active_trade:
            # The event can precede full registry installation. Do not turn this
            # unknown phase into either factor=1 or historical custody.
            return
        if not self.is_warming_up:
            self._assert_raw_subscriptions(symbol)
        zones = {config.exchange_time_zone.id for config in active_trade}
        if len(zones) == 1:
            self._event_zones[sid] = next(iter(zones))
        else:
            self._event_zones[sid] = None
        self._custody_since[sid] = self.utc_time.replace(tzinfo=UTC)

    def on_warmup_finished(self):
        if self.is_warming_up:
            raise ValueError("warm-up completion callback occurred before completion")
        # Re-attach explicit native minute configurations after the warm-up
        # transition, then require them. Subscription requests are not custody:
        # observed warm-up clocks remain intact, never invented or restarted.
        for sid, symbol in sorted(self._symbols.items()):
            self._manual_symbols.discard(sid)
            self._ensure_raw_subscription(symbol)
        self._warmup_finished_minute_validated = True

    def _ensure_raw_subscription(self, symbol):
        if symbol in self._context_symbols:
            raise ValueError("registered universe context cannot be subscribed for trading")
        sid = str(symbol.id)
        if sid not in self._manual_symbols and len(self._manual_symbols) >= MAX_SUBSCRIPTIONS:
            raise ValueError("matched persistent subscription bound exceeded")
        if sid not in self._manual_symbols:
            security = self.add_security(symbol, Resolution.MINUTE, fill_forward=True,
                leverage=1, extended_market_hours=False, data_normalization_mode=DataNormalizationMode.RAW)
            if security is None or security.symbol != symbol:
                raise ValueError("subscription changed exact native identity")
            security.set_data_normalization_mode(DataNormalizationMode.RAW)
            self._manual_symbols.add(sid)
        self._assert_raw_subscriptions(symbol)

    @staticmethod
    def _digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _native_clock(value, zone):
        if not isinstance(value, datetime):
            raise ValueError("native timestamp missing")
        if value.tzinfo is None:
            if type(zone) is not str or not zone:
                raise ValueError("native timezone missing")
            value = value.replace(tzinfo=ZoneInfo(zone))
        return value.astimezone(UTC)

    def _capture_caps(self, values):
        # Daily internal context is not money/action custody or stock admission.
        rows = list(values)
        if not rows or len(rows) > 20000:
            raise ValueError("bounded native fundamental callback required")
        configs = list(self.subscription_manager.subscription_data_config_service
                       .get_subscription_data_configs(self._cap_context_symbol, True))
        if (not configs or any(config.symbol != self._cap_context_symbol
                or not config.is_internal_feed or config.resolution != Resolution.DAILY
                or config.exchange_time_zone.id != "America/New_York"
                or config.type.FullName != "QuantConnect.Data.Fundamental.FundamentalUniverse"
                for config in configs)):
            raise ValueError("exact native daily Fundamental context clock required")
        now = self._native_clock(self.utc_time, "UTC")
        effective = self._native_clock(rows[0].end_time, "America/New_York")
        asof = self._native_clock(rows[0].time, "America/New_York")
        if not asof <= effective <= now:
            raise ValueError("future or reversed native cap clock")
        wanted, caps = set(self._symbols), {}
        for row in rows:
            sid = str(row.symbol.id)
            if sid not in wanted:
                continue
            if sid in caps:
                raise ValueError("duplicate native fundamental identity")
            if (self._native_clock(row.end_time, "America/New_York") != effective
                    or self._native_clock(row.time, "America/New_York") != asof):
                raise ValueError("mixed native cap clocks")
            try:
                raw = row.market_cap
            except Exception:
                caps[sid] = {"state": "unknown", "value": None}
                continue
            if raw is None:
                caps[sid] = {"state": "missing", "value": None}
                continue
            try:
                amount = native_fraction(raw)
            except (ValueError, TypeError, ArithmeticError):
                caps[sid] = {"state": "invalid", "value": None}
                continue
            caps[sid] = {"state": "available" if amount > 0 else "nonpositive",
                         "value": core._text(amount)}
        self._cap_callback_count += 1
        self._cap_snapshots.append({"effective": effective, "received": now,
            "asof": asof, "caps": caps})
        self._cap_snapshots = [snapshot for snapshot in self._cap_snapshots
            if now - snapshot["effective"] <= timedelta(days=45)]
        return []

    def _select_caps(self, cutoff):
        eligible = [snapshot for snapshot in self._cap_snapshots
            if snapshot["received"] <= cutoff and snapshot["effective"] <= cutoff
            and snapshot["effective"].astimezone(NY).date() == cutoff.astimezone(NY).date()]
        return max(eligible, key=lambda row: (row["effective"], row["received"])) if eligible else None

    def _selected_scores(self, selected, day):
        # Selection has already completed. No state may alter its identities.
        by_ticker = {row["ticker"]: sid for sid, row in self._identities.items()
                     if row["eligible"]}
        states = {row["security_id"]: row for row in self._frames[day]["states"]}
        result = {}
        for sid, symbol in selected.items():
            source_id = by_ticker.get(symbol.value)
            if source_id is None:
                result[sid] = {"state": "unknown", "value": None}
                continue
            row = states[source_id]
            if row["state"] == "scored":
                result[sid] = {"state": "available", "value": row["score"]}
            else:
                result[sid] = {"state": "missing" if row["state"] == "no_admissible_event"
                               else "unknown", "value": None}
        return result

    def _prepare_targets(self, day):
        cutoff = core._clock(CUTOFFS[DECISIONS.index(day)])
        if cutoff >= self._native_clock(self.utc_time, "UTC"):
            raise ValueError("frozen cutoff not yet available")
        cap_snapshot = self._select_caps(cutoff)
        if cap_snapshot is None:
            self._decision_coverage[day] = None
            self._reason("missing_prior_cap_snapshot")
            return
        selected_by_sleeve, reports, symbols = {}, {}, {}
        clocks = {"cap_effective_utc": cap_snapshot["effective"].isoformat(),
                  "cap_received_utc": cap_snapshot["received"].isoformat(),
                  "cap_asof_time": cap_snapshot["asof"].isoformat()}
        for etf in ETFS:
            snapshot = core.select_snapshot(self._snapshots[etf], cutoff)
            if snapshot is None:
                self._decision_coverage[day] = None
                self._reason("missing_lagged_membership_" + etf)
                return
            members = snapshot["members"]
            _member_inventory(members)
            rows = [{"sid": str(row["symbol"].id), "ticker": row["ticker"]} for row in members]
            caps = {row["sid"]: cap_snapshot["caps"].get(row["sid"],
                     {"state": "missing", "value": None}) for row in rows}
            selected, coverage = cap_tilt.rank_cap_members(rows, caps)
            member_symbols = {str(row["symbol"].id): row["symbol"] for row in members}
            symbols.update({sid: member_symbols[sid] for sid in selected})
            selected_by_sleeve[etf] = selected
            reports[etf] = {"membership_available": True, "etf_fallback": False,
                "snapshot_hash": self._digest(sorted((str(row["symbol"].id), row["weight"])
                                                       for row in members)),
                "member_count": len(members), "selected_count": len(selected),
                "effective_utc": snapshot["effective"].isoformat(),
                "received_utc": snapshot["received"].isoformat(),
                "cap_state_counts": coverage["cap_state_counts"],
                "eligible_count": coverage["eligible_count"], "unfilled_slots": coverage["unfilled_slots"],
                "cap_input_hash": self._digest({"clocks": clocks, "caps": caps}),
                "selected_ids_hash": self._digest(sorted(selected)),
                "baseline_weights_hash": self._digest([(sid, "1/60") for sid in sorted(selected)]),
                **clocks}
        scores = self._selected_scores(symbols, day) if self._config["arm"] == "tpr_on" else {}
        capacity = "0.20" if self._config["arm"] == "tpr_on" else "0"
        weights, diagnostics = cap_tilt.tilt_sleeves(selected_by_sleeve, scores, capacity=capacity)
        for etf in ETFS:
            detail = diagnostics["per_sleeve"][etf]
            reports[etf].update({key: core._text(detail[key]) for key in
                ("baseline_weight", "target_weight", "cash_weight", "transferred_weight",
                 "recipient_underfill", "aggregate_cap_blocked_capacity", "maximum_absolute_relative_change")})
            reports[etf].update({"ranked_score_count": detail["ranked_score_count"],
                "score_state_counts": detail["score_state_counts"] if self._config["arm"] == "tpr_on"
                                     else {"not_used": len(selected_by_sleeve[etf])},
                "transfer_count": detail["transfer_count"],
                "cap_binding_recipient_count": detail["cap_binding_recipient_count"]})
        for sid in self._delisted_ids & set(symbols):
            del symbols[sid]
            del weights[sid]
            self._reason("delisting_target_refused")
        self._targets, self._target_weights = symbols, weights
        self._ever_targeted_ids.update(weights)
        self._symbols.update(symbols)
        self._decision_coverage[day] = {"session": day, "arm": self._config["arm"],
            "sleeves": reports, "consolidated_selected_count": len(symbols),
            "target_gross": core._text(sum(weights.values(), Fraction(0))),
            "unallocated_target_cash": core._text(1 - sum(weights.values(), Fraction(0)))}

    def _prior_mark(self, symbol):
        day = self.time.date().isoformat()
        cutoff = core._clock(CUTOFFS[DECISIONS.index(day)])
        sid = str(symbol.id)
        factor = split_basis_with_custody(self._custody_since.get(sid), cutoff,
            self._split_factors.get((sid, day)), delisted=sid in self._delisted_ids)
        if factor is None:
            self._reason("missing_action_custody")
            return None
        self._assert_raw_subscriptions(symbol)
        bars = list(self.history[TradeBar](symbol, 3, Resolution.DAILY,
            data_normalization_mode=DataNormalizationMode.RAW))
        expected_day = cutoff.astimezone(NY).date()
        bars = [bar for bar in bars if bar.end_time < self.time and bar.time.date() == expected_day]
        if not bars:
            return None
        bar = max(bars, key=lambda item: item.end_time)
        price, volume = native_fraction(bar.close), native_fraction(bar.volume)
        if price <= 0 or volume < 0:
            return None
        return price * factor, volume / factor

    def _rebalance(self):
        day = self.time.date().isoformat()
        if self.is_warming_up or day not in DECISIONS or day in self._attempted_days:
            return
        self._attempted_days.add(day)
        self._decision_count += 1
        if self.time.time() != time(9, 20):
            self._refused_count += 1
            self._reason("late_decision_clock")
            return
        self._prepare_targets(day)
        coverage = self._decision_coverage.get(day)
        if coverage is None:
            self._refused_count += 1
            return
        for etf, report in coverage["sleeves"].items():
            self._sleeve_selected_decisions[etf] += bool(report["selected_count"])
        holdings = {}
        for held in self.portfolio.values():
            if not held.invested:
                continue
            sid, quantity = str(held.symbol.id), native_fraction(held.quantity)
            if sid not in self._symbols or quantity.denominator != 1 or quantity < 0:
                raise ValueError("unaddressable/fractional/short held exposure")
            holdings[sid] = int(quantity)
        marks = {}
        for sid in set(self._target_weights) | set(holdings):
            mark = self._prior_mark(self._symbols[sid])
            if mark is not None:
                marks[sid] = mark
        # Common selected-stock price/volume inputs, not outcome-dependent NAV
        # or holdings-only exit domains. Exact represented values stay private;
        # digest and prior session suffice to detect mismatched native tapes.
        coverage["prior_mark_inputs_sha256"] = self._digest([
            (sid, [core._text(value) for value in marks[sid]] if sid in marks else None)
            for sid in sorted(self._targets)])
        coverage["prior_mark_session"] = core._clock(CUTOFFS[DECISIONS.index(day)]).astimezone(NY).date().isoformat()
        coverage_log = "MATCHED_COVERAGE " + json.dumps(coverage, sort_keys=True, separators=(",", ":"))
        if len(coverage_log) > 16384:
            raise ValueError("bounded complete aggregate coverage log required")
        self.log(coverage_log)
        if any(sid not in marks for sid in holdings):
            self._refused_count += 1
            self._reason("unpriced_held_nav")
            return
        cash = native_fraction(self.portfolio.cash)
        expected_prior_day = core._clock(CUTOFFS[DECISIONS.index(day)]).astimezone(NY).date()
        if (self._prior_close_day is None and (day != DECISIONS[0] or holdings)) or (
                self._prior_close_day is not None and self._prior_close_day != expected_prior_day):
            self._refused_count += 1
            self._reason("missing_prior_close_nav")
            return
        orders = plan_weighted_orders(self._target_weights, holdings, marks,
            self._prior_close_nav, cash, Fraction(self._config["slippage"]),
            etf_arm=self._config["arm"] == "etf_basket")
        for row in orders:
            if row["requested"] is not None:
                self._requested_shares += abs(row["requested"])
            self._reason(row["reason"])
            quantity = row["submitted"]
            if not quantity:
                continue
            sid = row["security_id"]
            self._assert_raw_subscriptions(self._symbols[sid])
            intent = hashlib.sha256((self._config["candidate_id"] + ":" + day + ":" + sid).encode()).hexdigest()[:20]
            self._tickets.append(self.market_on_open_order(self._symbols[sid], quantity, tag="TPRM:" + intent))
            self._submitted += 1
            self._submitted_shares += abs(quantity)

    @staticmethod
    def _window(clock):
        local = clock.astimezone(NY)
        return "inside" if time(9, 20) <= local.time().replace(tzinfo=None) <= time(9, 35) else "outside"

    def _quantity_observation(self, symbol):
        try:
            return native_fraction(self.portfolio[symbol].quantity) != 0
        except Exception:
            return None

    def _order_observation(self, symbol):
        try:
            history = list(self.transactions.get_orders())
            opened = list(self.transactions.get_open_orders())
            if len(history) > 10000 or len(opened) > 10000:
                raise ValueError("native order history bound")
            if any(not isinstance(order, Order) for order in history + opened):
                raise ValueError("typed native Order history required")
            return (any(order.symbol == symbol for order in history),
                    any(order.symbol == symbol for order in opened))
        except Exception:
            return None, None

    def _delisting_before(self, event):
        observation = {"type": "unknown", "phase": "unknown",
            "receipt_window": "unknown", "event_window": "unknown",
            "held_before": None, "held_after": None, "ever_filled": None,
            "targeted": None, "open_order": None, "ever_ordered": None,
            "native_ticket": None, "history_unknown": self._fill_history_unknown}
        # Each observation boundary is isolated. Missing metadata is unknown,
        # never coerced into absence/UTC. The original parent is not in a catch.
        try:
            if not isinstance(event, Delisting):
                raise ValueError("typed native Delisting required")
            if event.type == DelistingType.WARNING:
                observation["type"] = "warning"
            elif event.type == DelistingType.DELISTED:
                observation["type"] = "final"
        except Exception:
            pass
        try:
            receipt = self._native_clock(self.utc_time, "UTC")
            local = receipt.astimezone(NY)
            observation["receipt_window"] = self._window(receipt)
            observation["phase"] = ("warmup" if self.is_warming_up else
                "evaluation" if date(2025, 1, 2) <= local.date() <= date(2025, 3, 31)
                else "outside")
        except Exception:
            pass
        try:
            sid = str(event.symbol.id)
            symbol = event.symbol
            observation["held_before"] = self._quantity_observation(symbol)
            observation["ever_filled"] = sid in self._ever_filled_ids
            observation["targeted"] = sid in self._ever_targeted_ids or sid in self._targets
            ever, opened = self._order_observation(symbol)
            observation["ever_ordered"], observation["open_order"] = ever, opened
            observation["history_unknown"] |= ever is None or opened is None
            observation["event_window"] = self._window(
                self._native_clock(event.time, self._event_zones.get(sid)))
        except Exception:
            pass
        try:
            observation["native_ticket"] = event.ticket is not None
        except Exception:
            pass
        return observation

    def on_data(self, data):
        events = list(data.delistings.values())
        before = []
        for event in events:
            try:
                before.append(self._delisting_before(event))
            except Exception:
                before.append({"type": "unknown", "phase": "unknown",
                    "receipt_window": "unknown", "event_window": "unknown",
                    "held_before": None, "held_after": None, "ever_filled": None,
                    "targeted": None, "open_order": None, "ever_ordered": None,
                    "native_ticket": None, "history_unknown": True})
        for collection in (getattr(data, "bars", {}), data.splits, data.dividends):
            for item in collection.values():
                self._observe_raw_custody(item.symbol)
        # Original RAW dividend/split/fill accounting executes unconditionally.
        # A genuine parent failure propagates and cannot be observer-qualified.
        super().on_data(data)
        for event, observation in zip(events, before):
            sid = str(event.symbol.id)
            self._delisted_ids.add(sid)
            self._reason("delisting_event")
            observation["held_after"] = self._quantity_observation(event.symbol)
            if sid in self._ever_filled_ids:
                observation["ever_filled"] = True
            ever_after, open_after = self._order_observation(event.symbol)
            observation["history_unknown"] |= ever_after is None or open_after is None
            for key, value in (("ever_ordered", ever_after), ("open_order", open_after)):
                if value is True or observation[key] is True:
                    observation[key] = True
                elif value is None or observation[key] is None:
                    observation[key] = None
            try:
                ticket_after = event.ticket is not None
            except Exception:
                ticket_after = None
            if observation["native_ticket"] is None or ticket_after is None:
                observation["native_ticket"] = None
            else:
                observation["native_ticket"] |= ticket_after
            # Preserve unavailable history as None, not False through 'or'.
            if self._fill_history_unknown:
                observation["history_unknown"] = True
            self._delisting_audit = cap_observer.record_event(self._delisting_audit, observation)

    def on_order_event(self, event):
        try:
            if not isinstance(event, OrderEvent):
                raise ValueError("typed native OrderEvent required")
            quantity = native_fraction(event.fill_quantity)
            if quantity:
                self._ever_filled_ids.add(str(event.symbol.id))
        except Exception:
            self._fill_history_unknown = True
        # Partial/nonterminal fills count too; original handler is never skipped.
        super().on_order_event(event)

    def _daily_audit(self):
        day = self.time.date().isoformat()
        if self.is_warming_up or not "2025-01-02" <= day <= "2025-03-31" or day in self._valuation_days:
            return
        invested = [held for held in self.portfolio.values() if held.invested]
        for held in invested:
            self._assert_raw_subscriptions(held.symbol)
        cash, nav = native_fraction(self.portfolio.cash), native_fraction(self.portfolio.total_portfolio_value)
        holdings = native_fraction(self.portfolio.total_holdings_value)
        native_quantities = {str(held.symbol.id): native_fraction(held.quantity) for held in self.portfolio.values()}
        mismatches = sum(self._quantity_ledger.get(sid, Fraction(0)) != native_quantities.get(sid, Fraction(0))
                         for sid in set(self._quantity_ledger) | set(native_quantities))
        self._position_ledger_mismatches += mismatches
        cash_residual, nav_residual = abs(cash - self._cash_ledger), abs(nav - (self._cash_ledger + holdings))
        self._max_cash_residual = max(self._max_cash_residual, cash_residual)
        self._max_nav_residual = max(self._max_nav_residual, nav_residual)
        risk_ok = nav > 0 and cash >= -Fraction(1, 100) and 0 <= holdings <= nav + Fraction(1, 100)
        self._risk_breaches += not risk_ok
        limit = Fraction(1, 6) if self._config["arm"] == "etf_basket" else Fraction(1, 10)
        exposures = [native_fraction(held.holdings_value) / nav for held in invested] if nav > 0 else []
        max_name = max(exposures, default=Fraction(0))
        self._max_name_exposure = max(self._max_name_exposure, max_name)
        self._name_soft_cap_breaches += sum(exposure > limit for exposure in exposures)
        self._prior_close_nav, self._prior_close_day = nav, self.time.date()
        self._valuation_days.add(day)
        self.log("MATCHED_NAV " + json.dumps({"session": day, "nav": core._text(nav), "cash": core._text(cash),
            "gross_exposure": core._text(holdings / nav) if nav > 0 else None,
            "risk_within_unlevered_account": risk_ok, "max_name_exposure": core._text(max_name),
            "name_cap_is_prior_close_soft_target": True, "position_ledger_mismatches": mismatches,
            "cash_ledger_residual": core._text(cash_residual), "nav_ledger_residual": core._text(nav_residual)}, sort_keys=True))

    def on_end_of_algorithm(self):
        missing = ("missing_mark", "missing_action_custody", "unpriced_held_nav", "missing_prior_close_nav",
                   "qc_invalid_order", "qc_canceled_order", "delisting_event", "delisting_target_refused")
        complete_coverage = (set(self._decision_coverage) == set(DECISIONS)
            and all(row is not None and set(row["sleeves"]) == set(ETFS)
                    for row in self._decision_coverage.values()))
        meaningful = (self._fill_events > 0 and self._decision_count == 14
            and self._attempted_days == set(DECISIONS) and self._refused_count == 0
            and complete_coverage and self._warmup_finished_minute_validated
            and self._max_nav_residual <= Fraction(1, 100)
            and self._max_cash_residual <= Fraction(1, 100) and self._position_ledger_mismatches == 0
            and self._risk_breaches == 0 and len(self._valuation_days) == 60
            and self._prior_close_day == date(2025, 3, 31)
            and "2025-03-31" in self._valuation_days
            and not any(self._reasons.get(reason, 0) for reason in missing))
        ambient_ok = cap_observer.validate_audit(
            self._delisting_audit, self._reasons.get("delisting_event", 0))
        developmental_missing = tuple(reason for reason in missing if reason != "delisting_event")
        development_qualified = (self._fill_events > 0 and self._decision_count == 14
            and self._attempted_days == set(DECISIONS) and self._refused_count == 0
            and complete_coverage and self._warmup_finished_minute_validated
            and self._max_nav_residual <= Fraction(1, 100)
            and self._max_cash_residual <= Fraction(1, 100) and self._position_ledger_mismatches == 0
            and self._risk_breaches == 0 and len(self._valuation_days) == 60
            and self._prior_close_day == date(2025, 3, 31)
            and "2025-03-31" in self._valuation_days and ambient_ok
            and self._cap_callback_count > 0 and bool(self._cap_snapshots)
            and not any(self._reasons.get(reason, 0) for reason in developmental_missing))
        self.log("MATCHED_SUMMARY " + json.dumps({"study_id": STUDY,
            "candidate_id": self._config["candidate_id"], "arm": self._config["arm"], "cost": self._config["cost"],
            "config_sha256": EXPECTED_MATCHED_CONFIG_SHA256, "freeze_sha256": EXPECTED_MATCHED_FREEZE_SHA256,
            "packet_sha256": core.EXPECTED_PACKET_SHA256 if self._config["arm"] == "tpr_on" else None,
            "decisions": self._decision_count, "refused_decisions": self._refused_count,
            "submitted_orders": self._submitted, "fill_events": self._fill_events,
            "requested_shares": self._requested_shares, "submitted_shares": self._submitted_shares,
            "filled_shares": self._filled_shares, "fees": core._text(self._fees),
            "engine_end_utc": self.utc_time.replace(tzinfo=UTC).isoformat(),
            "last_valuation_session": self._prior_close_day.isoformat() if self._prior_close_day else None,
            "valuation_days": len(self._valuation_days), "manual_subscriptions": len(self._manual_symbols),
            "reason_counts": self._reasons,
            "warmup_finished_minute_validated": self._warmup_finished_minute_validated,
            "observed_action_custody_symbols": len(self._custody_since),
            "registered_universe_contexts": len(self._context_symbols),
            "universe_context_initializer_skips": self._context_initializer_skips,
            "universe_context_change_skips": self._context_change_skips,
            "isolated_benchmark_internal_config_max": self._benchmark_internal_config_max,
            "max_cash_ledger_residual": core._text(self._max_cash_residual),
            "max_nav_ledger_residual": core._text(self._max_nav_residual),
            "position_ledger_mismatches": self._position_ledger_mismatches,
            "risk_breaches": self._risk_breaches, "max_name_exposure": core._text(self._max_name_exposure),
            "name_soft_cap_breaches": self._name_soft_cap_breaches,
            "sleeve_selected_decisions": self._sleeve_selected_decisions,
            "zero_selection_sleeve_diagnostics": [etf for etf in ETFS if not self._sleeve_selected_decisions[etf]],
            "meaningful_execution": meaningful,
            "original_no_delisting_meaningful_execution": meaningful,
            "development_execution_qualified": development_qualified,
            "cap_callback_count": self._cap_callback_count,
            "cap_snapshot_count": len(self._cap_snapshots),
            "delisting_audit": self._delisting_audit, "canonical_admission": False,
            "independent_sleeve_pnl_observed": False}, sort_keys=True))
