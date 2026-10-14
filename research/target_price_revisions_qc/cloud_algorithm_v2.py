"""Successor to frozen cloud_algorithm.py; same exploratory six-case family.

Repairs current RAW subscription custody and the final valuation clock only.

The private uploader replaces only the two hash placeholders. No vendor calls,
raw QC-data export, canonical admission, or live deployment is implemented.
Packet absence/refusal is not a zero alpha. This file intentionally lives outside
the pure development package and its import boundary.
"""
from AlgorithmImports import *
from datetime import date, datetime, time, timedelta, timezone
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import re
from zoneinfo import ZoneInfo

EXPECTED_CONFIG_SHA256 = "__CONFIG_SHA256__"
EXPECTED_PACKET_SHA256 = "__PACKET_SHA256__"
EXPECTED_PACKET_KEY = "__PACKET_KEY__"
EXPECTED_FREEZE_SHA256 = "3cf40af7325265b15f7de5e03f0667a1554c889fdd2db02de228a01b2fa97ccf"
FAMILY = "TPR-QC6-20261008-v1"
CASES = {
    "sp500": ("TPR-QC6-SPY-v1", "SPY"),
    "healthcare": ("TPR-QC6-XLV-v1", "XLV"),
    "energy": ("TPR-QC6-XLE-v1", "XLE"),
    "nasdaq100": ("TPR-QC6-QQQ-v1", "QQQ"),
    "semiconductors": ("TPR-QC6-SOXX-v1", "SOXX"),
    "rare_earth_strategic_metals": ("TPR-QC6-REMX-v1", "REMX"),
}
DECISIONS = ("2025-01-02", "2025-01-06", "2025-01-13", "2025-01-21",
             "2025-01-27", "2025-02-03", "2025-02-10", "2025-02-18",
             "2025-02-24", "2025-03-03", "2025-03-10", "2025-03-17",
             "2025-03-24", "2025-03-31")
CUTOFFS = ("2024-12-31T23:00:00+00:00", "2025-01-03T23:00:00+00:00",
           "2025-01-10T23:00:00+00:00", "2025-01-17T23:00:00+00:00",
           "2025-01-24T23:00:00+00:00", "2025-01-31T23:00:00+00:00",
           "2025-02-07T23:00:00+00:00", "2025-02-14T23:00:00+00:00",
           "2025-02-21T23:00:00+00:00", "2025-02-28T23:00:00+00:00",
           "2025-03-07T23:00:00+00:00", "2025-03-14T22:00:00+00:00",
           "2025-03-21T22:00:00+00:00", "2025-03-28T22:00:00+00:00")
FROZEN_SOURCE_HASHES = {
    "structure.json": "509047244d47ec489e5a8e1dfbf74e0d0104b51c7dfff19ae7283abba1e9ccd5",
    "raw_candidate.py": "6232723188bedfbce5ba88ceccd460c1ce1011bffad5338e87b59b648458a6c0",
    "raw_revision.py": "ea4efcd9b0e73ae0b5c166d820c51e054559a3ed610041a6eb2acc8abca36353",
}
NY = ZoneInfo("America/New_York")
UTC = timezone.utc


def _keys(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError("closed schema refused")


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("invalid hash")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json(text, expected):
    if type(text) is not str or len(text.encode("utf-8")) > 16 * 1024 * 1024:
        raise ValueError("packet size refused")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != _hash(expected):
        raise ValueError("packet hash refused")
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _number(value):
    if type(value) is not str or len(value) > 128:
        raise ValueError("decimal string required")
    parsed = Decimal(value)
    if not parsed.is_finite() or abs(parsed) > Decimal("1e18") or parsed.as_tuple().exponent < -100:
        raise ValueError("decimal outside bounds")
    return Fraction(parsed)


def _clock(value):
    if type(value) is not str or len(value) > 64:
        raise ValueError("clock string required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("aware clock required")
    return result.astimezone(UTC)


def _text(value):
    """Deterministic decimal presentation; computations remain exact rational."""
    value = Fraction(value)
    with localcontext(Context(prec=48)):
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def validate_inputs(config_json, packet_json, config_hash, packet_hash):
    """Strict admission of data shape/hash, not proof of historical source truth."""
    config = _json(config_json, config_hash)
    _keys(config, ("schema", "freeze_sha256", "candidate_id", "universe_id"))
    if (config["schema"] != "tpr-qc-six-config-v1"
            or config["freeze_sha256"] != EXPECTED_FREEZE_SHA256
            or config["universe_id"] not in CASES
            or config["candidate_id"] != CASES[config["universe_id"]][0]):
        raise ValueError("configuration is not a frozen case")
    packet = _json(packet_json, packet_hash)
    _keys(packet, ("schema", "candidate_id", "freeze_sha256", "source_hashes", "identities", "frames"))
    if (packet["schema"] != "tpr-qc-six-signals-v1" or packet["candidate_id"] != FAMILY
            or packet["freeze_sha256"] != config["freeze_sha256"]):
        raise ValueError("packet family/freeze mismatch")
    if type(packet["source_hashes"]) is not dict or not packet["source_hashes"]:
        raise ValueError("missing source binding")
    for name, value in packet["source_hashes"].items():
        if type(name) is not str or not name or len(name) > 128:
            raise ValueError("invalid source label")
        _hash(value)
    if any(packet["source_hashes"].get(name) != value for name, value in FROZEN_SOURCE_HASHES.items()):
        raise ValueError("frozen source/scorer binding mismatch")
    rows = packet["identities"]
    if type(rows) is not list or not 1 <= len(rows) <= 4096:
        raise ValueError("identity bound refused")
    identities, eligible_tickers = {}, set()
    for row in rows:
        _keys(row, ("security_id", "ticker", "eligible", "reason"))
        sid, ticker = row["security_id"], row["ticker"]
        if (type(sid) is not str or not sid or len(sid) > 128 or sid in identities
                or type(ticker) is not str or not ticker or len(ticker) > 32
                or type(row["eligible"]) is not bool or type(row["reason"]) is not str
                or not row["reason"] or len(row["reason"]) > 256):
            raise ValueError("invalid/duplicate identity")
        if row["eligible"]:
            if ticker in eligible_tickers:
                raise ValueError("ambiguous eligible ticker")
            eligible_tickers.add(ticker)
        identities[sid] = row
    if type(packet["frames"]) is not list or len(packet["frames"]) != len(DECISIONS):
        raise ValueError("fourteen complete frames required")
    frames = {}
    for day, expected_cutoff, frame in zip(DECISIONS, CUTOFFS, packet["frames"]):
        _keys(frame, ("session", "cutoff_utc", "states"))
        if frame["session"] != day:
            raise ValueError("decision calendar mismatch")
        cutoff = _clock(frame["cutoff_utc"])
        if cutoff != _clock(expected_cutoff):
            raise ValueError("frozen prior exchange-session cutoff mismatch")
        local = cutoff.astimezone(NY)
        opened = datetime.combine(date.fromisoformat(day), time(9, 20), NY)
        if (local.time() != time(18) or local.date() >= opened.date()
                or not timedelta(0) < opened - local <= timedelta(days=7)):
            raise ValueError("decision cutoff is not prior-session 18:00")
        if type(frame["states"]) is not list or len(frame["states"]) != len(identities):
            raise ValueError("incomplete frame")
        seen = set()
        for row in frame["states"]:
            _keys(row, ("security_id", "state", "score", "reasons"))
            sid, state = row["security_id"], row["state"]
            if sid not in identities or sid in seen:
                raise ValueError("frame identity mismatch")
            seen.add(sid)
            if (type(row["reasons"]) is not list or len(row["reasons"]) > 64
                    or any(type(reason) is not str or not reason or len(reason) > 256
                           for reason in row["reasons"])):
                raise ValueError("reason schema refused")
            if state == "scored":
                if not identities[sid]["eligible"]:
                    raise ValueError("ineligible identity scored")
                _number(row["score"])
            elif state in ("no_admissible_event", "unknown_input", "identity_ineligible"):
                if row["score"] is not None or not row["reasons"]:
                    raise ValueError("missing state cannot be numerical zero")
                if (state == "identity_ineligible") == identities[sid]["eligible"]:
                    raise ValueError("identity eligibility state mismatch")
            else:
                raise ValueError("unknown signal state")
        frames[day] = frame
    return config, identities, frames


def select_snapshot(snapshots, cutoff):
    """No future receipts; 7-day effective lag and 21-day staleness bound."""
    candidates = [row for row in snapshots
                  if row["received"] <= cutoff
                  and cutoff - timedelta(days=21) <= row["effective"] <= cutoff - timedelta(days=7)]
    return max(candidates, key=lambda row: (row["effective"], row["received"])) if candidates else None


def rank_members(identities, frame, members):
    """Selection is independent of subsequent price/liquidity availability."""
    by_ticker = {row["ticker"]: sid for sid, row in identities.items() if row["eligible"]}
    all_tickers = {row["ticker"] for row in identities.values()}
    states = {row["security_id"]: row for row in frame["states"]}
    coverage = {name: {"count": 0, "weight": Fraction(0)} for name in
                ("scored", "no_admissible_event", "unknown_input", "missing_identity", "ineligible", "unknown_weight", "zero_weight")}
    ranked, symbols = [], {}
    for member in members:
        ticker, weight = member["ticker"], member["weight"]
        if weight is None:
            coverage["unknown_weight"]["count"] += 1
            continue
        weight = _number(weight)
        if weight <= 0:
            coverage["zero_weight"]["count"] += 1
            continue
        sid = by_ticker.get(ticker)
        category = (states[sid]["state"] if sid else "ineligible" if ticker in all_tickers else "missing_identity")
        coverage[category]["count"] += 1
        coverage[category]["weight"] += weight
        if sid and category == "scored":
            score = _number(states[sid]["score"])
            if score > 0:
                ranked.append((sid, score))
                symbols[sid] = member["symbol"]
    selected = [sid for sid, _ in sorted(ranked, key=lambda pair: (-pair[1], pair[0]))[:10]]
    return {sid: symbols[sid] for sid in selected}, coverage


def plan_orders(targets, holdings, marks, nav, cash):
    """Exact rational prior-close sizing, volume cap, settled-cash-only budget.

marks: sid -> (positive close, nonnegative lagged share volume). Caller excludes
unknown/split-ambiguous marks; no replacement stock is promoted into targets.
"""
    nav, cash = Fraction(nav), Fraction(cash)
    if nav <= 0 or cash < 0:
        raise ValueError("invalid NAV/cash")
    budget = cash * Fraction(97, 100)
    result = []
    for sid in sorted(set(targets) | set(holdings)):
        held = holdings.get(sid, 0)
        if type(held) is not int or held < 0:
            raise ValueError("whole long shares required")
        if sid not in marks:
            result.append({"security_id": sid, "requested": None, "submitted": 0, "reason": "missing_mark"})
            continue
        close, volume = map(Fraction, marks[sid])
        if close <= 0 or volume < 0:
            raise ValueError("invalid prior mark")
        target = int(nav / (10 * close)) if sid in targets else 0
        delta = target - held
        cap = int(volume / 100)
        quantity = min(abs(delta), cap) * (1 if delta >= 0 else -1)
        reason = "volume_cap" if abs(quantity) < abs(delta) else "complete"
        result.append({"security_id": sid, "requested": delta, "submitted": quantity, "reason": reason})
    # Deterministic sell-first submission, but no use of expected sell proceeds.
    result.sort(key=lambda row: (row["submitted"] >= 0, row["security_id"]))
    for row in result:
        if row["submitted"] <= 0:
            continue
        price = Fraction(marks[row["security_id"]][0])
        per_share = price * Fraction(1001, 1000) + Fraction(1, 100)
        affordable = int(budget / per_share)
        if row["submitted"] > affordable:
            row["submitted"] = affordable
            row["reason"] = "cash_buffer" if row["reason"] == "complete" else "volume_and_cash_buffer"
        budget -= row["submitted"] * per_share
    return result


class CentPerShareFee(FeeModel):
    def get_order_fee(self, parameters):
        # Exact decimal conversion at the .NET engine boundary, no money float.
        from System import Decimal as NetDecimal
        from System.Globalization import CultureInfo
        cents = abs(int(parameters.order.quantity))
        value = f"{cents // 100}.{cents % 100:02d}"
        return OrderFee(CashAmount(NetDecimal.Parse(value, CultureInfo.InvariantCulture), "USD"))


class TargetPriceSixUniverseAlgorithm(QCAlgorithm):
    def initialize(self):
        if self.live_mode:
            raise ValueError("exploratory backtest only; live mode refused")
        from signal_packet import CONFIG_JSON
        if EXPECTED_PACKET_KEY != f"tpr-qc6/{FAMILY}/{_hash(EXPECTED_PACKET_SHA256)}.json":
            raise ValueError("ObjectStore key outside frozen private family")
        if not self.object_store.contains_key(EXPECTED_PACKET_KEY):
            raise ValueError("private signal packet missing")
        packet_json = self.object_store.read(EXPECTED_PACKET_KEY)
        self._config, self._identities, self._frames = validate_inputs(
            CONFIG_JSON, packet_json, EXPECTED_CONFIG_SHA256, EXPECTED_PACKET_SHA256)
        self.set_start_date(2025, 1, 2)
        self.set_end_date(2025, 3, 31)
        self.set_time_zone("America/New_York")
        self.set_account_currency("USD")
        self.set_cash(100000)
        self._snapshots, self._symbols, self._split_factors = [], {}, {}
        self._manual_symbols, self._valuation_days = set(), set()
        self._targets, self._decision_coverage, self._tickets = {}, {}, []
        self._attempted_days, self._reasons = set(), {}
        self._cash_ledger = Fraction(100000)
        self._quantity_ledger, self._dividend_keys = {}, set()
        self._position_ledger_mismatches = 0
        self._prior_close_nav, self._prior_close_day = Fraction(100000), None
        self._fees, self._fill_events, self._submitted = Fraction(0), 0, 0
        self._requested_shares, self._submitted_shares, self._filled_shares = 0, 0, 0
        self._max_cash_residual, self._max_nav_residual = Fraction(0), Fraction(0)
        self._decision_count, self._refused_count = 0, 0
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.MINUTE
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self.add_security_initializer(self._initialize_security)
        ticker = CASES[self._config["universe_id"]][1]
        # A liquid, untraded extended-hours clock keeps 09:20 and 16:01 events
        # from being deferred to the next regular-hours bar in backtests.
        self._clock_symbol = self.add_equity("SPY", Resolution.MINUTE,
            extended_market_hours=True, data_normalization_mode=DataNormalizationMode.RAW).symbol
        self._benchmark = self._clock_symbol if ticker == "SPY" else self.add_equity(
            ticker, Resolution.MINUTE, data_normalization_mode=DataNormalizationMode.RAW).symbol
        self.set_benchmark(self._benchmark)
        self.add_universe(self.universe.etf(self._benchmark, universe_filter_func=self._constituents))
        self.set_warm_up(timedelta(days=31), Resolution.DAILY)
        self.schedule.on(self.date_rules.every_day(self._benchmark), self.time_rules.at(9, 20), self._rebalance)
        self.schedule.on(self.date_rules.every_day(self._benchmark), self.time_rules.at(9, 35), self._cancel_day_orders)
        self.schedule.on(self.date_rules.every_day(self._benchmark), self.time_rules.at(16, 1), self._daily_audit)

    def _initialize_security(self, security):
        security.set_leverage(1)
        security.set_fee_model(CentPerShareFee())
        security.set_slippage_model(ConstantSlippageModel(0.001))
        security.set_settlement_model(ImmediateSettlementModel())

    def _reason(self, reason):
        self._reasons[reason] = self._reasons.get(reason, 0) + 1

    def _constituents(self, constituents):
        rows = list(constituents)
        if not rows:
            self._reason("empty_membership_callback")
            return Universe.UNCHANGED
        now = self.utc_time.replace(tzinfo=UTC)
        effective = max(row.end_time.replace(tzinfo=UTC) for row in rows)
        if effective > now:
            raise ValueError("future membership callback")
        members, seen = [], set()
        for row in rows:
            ticker = row.symbol.value
            if ticker in seen:
                raise ValueError("ambiguous membership ticker")
            seen.add(ticker)
            weight = None if row.weight is None else str(row.weight)
            if weight is not None and not 0 <= _number(weight) <= 1:
                raise ValueError("invalid membership weight")
            members.append({"ticker": ticker, "weight": weight, "symbol": row.symbol})
        self._snapshots.append({"effective": effective, "received": now, "members": members})
        self._snapshots = [row for row in self._snapshots if now - row["effective"] <= timedelta(days=45)]
        day = self.time.date().isoformat()
        if day in self._frames:
            self._prepare_targets(day)
        held = [holding.symbol for holding in self.portfolio.values() if holding.invested]
        return list(set(self._targets.values()) | set(held))

    def _prepare_targets(self, day):
        frame = self._frames[day]
        cutoff = _clock(frame["cutoff_utc"])
        if cutoff >= self.utc_time.replace(tzinfo=UTC):
            raise ValueError("signal cutoff not yet available")
        snapshot = select_snapshot(self._snapshots, cutoff)
        if snapshot is None:
            self._decision_coverage[day] = None
            return
        self._targets, coverage = rank_members(self._identities, frame, snapshot["members"])
        self._symbols.update(self._targets)
        membership_digest = hashlib.sha256(json.dumps(sorted(
            (str(row["symbol"].id), row["weight"]) for row in snapshot["members"]),
            separators=(",", ":")).encode()).hexdigest()
        report = {key: {"count": value["count"], "weight": _text(value["weight"])}
                  for key, value in coverage.items()}
        report.update({"session": day, "snapshot_hash": membership_digest,
                       "member_count": len(snapshot["members"]), "selected_count": len(self._targets),
                       "effective_utc": snapshot["effective"].isoformat(),
                       "received_utc": snapshot["received"].isoformat()})
        self._decision_coverage[day] = report

    def _assert_raw_subscriptions(self, symbol):
        """SecurityManager presence alone does not prove an active subscription."""
        if symbol not in self.securities:
            raise ValueError("missing active RAW security")
        security = self.securities[symbol]
        # Query the current registry used by corporate-action processing, not
        # merely Security's retained/obsolete subscription bag.
        service = self.subscription_manager.subscription_data_config_service
        configs = list(service.get_subscription_data_configs(symbol, True))
        active = [config for config in configs if not config.is_internal_feed]
        if (not any(config.resolution == Resolution.MINUTE and config.tick_type == TickType.TRADE
                    for config in active)
                or any(config.data_normalization_mode != DataNormalizationMode.RAW for config in configs)
                or security.data_normalization_mode != DataNormalizationMode.RAW):
            raise ValueError("active RAW minute trade subscription required")
        return security

    def _ensure_raw_subscription(self, symbol):
        # ETF callbacks are UTC-timed; the local date can still be the previous
        # day. Add the exact constituent Symbol at the frozen 09:20 decision,
        # independently of callback selection timing. Manual subscriptions stay
        # alive for action custody; at most 14 frames * 10 new winners.
        identifier = str(symbol.id)
        if identifier not in self._manual_symbols and len(self._manual_symbols) >= 140:
            raise ValueError("manual subscription bound exceeded")
        security = self.add_security(symbol, Resolution.MINUTE, fill_forward=True,
            leverage=1, extended_market_hours=False,
            data_normalization_mode=DataNormalizationMode.RAW)
        if security is None or security.symbol != symbol:
            raise ValueError("subscription changed exact constituent identity")
        # Initializers run before universe configs exist; establish and verify
        # normalization only after AddSecurity has actually attached configs.
        security.set_data_normalization_mode(DataNormalizationMode.RAW)
        self._assert_raw_subscriptions(symbol)
        self._manual_symbols.add(identifier)

    def _prior_mark(self, symbol):
        expected_day = _clock(self._frames[self.time.date().isoformat()]["cutoff_utc"]).astimezone(NY).date()
        bars = list(self.history[TradeBar](symbol, 3, Resolution.DAILY))
        # History EndTime is security-exchange local; request is at 09:20 NY.
        bars = [bar for bar in bars if bar.end_time < self.time and bar.time.date() == expected_day]
        if not bars:
            return None
        bar = max(bars, key=lambda item: item.end_time)
        price, volume = Fraction(str(bar.close)), Fraction(str(bar.volume))
        factor = self._split_factors.get((str(symbol.id), self.time.date().isoformat()), Fraction(1))
        if factor <= 0 or price <= 0 or volume < 0:
            return None
        # Raw historical shares are converted into today's split-share basis.
        price, volume = price * factor, volume / factor
        if not self.securities[symbol].has_data and factor == 1:
            self.securities[symbol].set_market_price(bar)
        return price, volume

    def _rebalance(self):
        day = self.time.date().isoformat()
        if self.is_warming_up or day not in self._frames or day in self._attempted_days:
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
            self._reason("missing_lagged_membership")
            return
        self.log("TPR_COVERAGE " + json.dumps(coverage, sort_keys=True))
        holdings = {}
        reverse = {str(symbol.id): sid for sid, symbol in self._symbols.items()}
        for holding in self.portfolio.values():
            if not holding.invested:
                continue
            sid = reverse.get(str(holding.symbol.id))
            if sid is None:
                raise ValueError("held identity missing")
            quantity = Fraction(str(holding.quantity))
            if quantity.denominator != 1 or quantity < 0:
                raise ValueError("fractional/short held shares refused")
            holdings[sid] = int(quantity)
        marks = {}
        for sid in set(self._targets) | set(holdings):
            symbol = self._symbols[sid]
            self._ensure_raw_subscription(symbol)
            mark = self._prior_mark(symbol)
            if mark is not None:
                marks[sid] = mark
        # Unknown held mark invalidates NAV; do not substitute zero or current open.
        if any(sid not in marks for sid in holdings):
            self._refused_count += 1
            self._reason("unpriced_held_nav")
            return
        cash = Fraction(str(self.portfolio.cash))
        expected_prior_day = _clock(self._frames[day]["cutoff_utc"]).astimezone(NY).date()
        if (self._prior_close_day is None and (day != DECISIONS[0] or holdings)) or (
                self._prior_close_day is not None and self._prior_close_day != expected_prior_day):
            self._refused_count += 1
            self._reason("missing_prior_close_nav")
            return
        nav = self._prior_close_nav
        orders = plan_orders(self._targets, holdings, marks, nav, cash)
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
            ticket = self.market_on_open_order(self._symbols[sid], quantity, tag="TPR6:" + intent)
            self._tickets.append(ticket)
            self._submitted += 1
            self._submitted_shares += abs(quantity)

    def _cancel_day_orders(self):
        if self.is_warming_up:
            return
        for order in self.transactions.get_open_orders():
            self.transactions.cancel_order(order.id, "TPR6 day-only 09:35 cancellation")

    def on_data(self, data):
        # LEAN applies cash dividends BEFORE splits, then calls OnData. Its
        # portfolio is already post-action here, so use our fill-driven shares.
        if not self.is_warming_up:
            for dividend in data.dividends.values():
                symbol_id = str(dividend.symbol.id)
                key = (symbol_id, self.time.date().isoformat())
                if key in self._dividend_keys:
                    raise ValueError("duplicate dividend action")
                self._dividend_keys.add(key)
                held = self._quantity_ledger.get(symbol_id, Fraction(0))
                if held:
                    self._assert_raw_subscriptions(dividend.symbol)
                self._cash_ledger += held * Fraction(str(dividend.distribution))
        for split in data.splits.values():
            if split.type == SplitType.SPLIT_OCCURRED:
                key = (str(split.symbol.id), self.time.date().isoformat())
                if key in self._split_factors:
                    raise ValueError("duplicate split action")
                factor = Fraction(str(split.split_factor))
                if factor <= 0:
                    raise ValueError("invalid split factor")
                self._split_factors[key] = factor
                if self.is_warming_up:
                    continue
                prior_quantity = self._quantity_ledger.get(key[0], Fraction(0))
                if prior_quantity:
                    self._assert_raw_subscriptions(split.symbol)
                entitled = prior_quantity / factor
                whole = int(entitled)
                remainder = entitled - whole
                self._quantity_ledger[key[0]] = Fraction(whole)
                if remainder:
                    # Mirrors SecurityPortfolioManager.ApplySplit: native RAW
                    # cache is already split-adjusted; no invented payable date
                    # and no unexplained cash-delta absorption.
                    last = self.securities[split.symbol].get_last_data()
                    price = (Fraction(str(last.price)) if last is not None
                             else Fraction(str(split.reference_price)) * factor)
                    if price <= 0:
                        raise ValueError("split cash-in-lieu price missing")
                    self._cash_ledger += remainder * price

    def on_order_event(self, event):
        quantity = Fraction(str(event.fill_quantity))
        fee = Fraction(str(event.order_fee.value.amount))
        if quantity:
            self._assert_raw_subscriptions(event.symbol)
            if quantity.denominator != 1:
                raise ValueError("fractional fill outside frozen contract")
            self._fill_events += 1
            self._filled_shares += abs(int(quantity))
            self._cash_ledger -= quantity * Fraction(str(event.fill_price))
            symbol_id = str(event.symbol.id)
            self._quantity_ledger[symbol_id] = self._quantity_ledger.get(symbol_id, Fraction(0)) + quantity
            if self._quantity_ledger[symbol_id] < 0:
                raise ValueError("short quantity outside frozen contract")
        self._cash_ledger -= fee
        self._fees += fee
        if event.status == OrderStatus.INVALID:
            self._reason("qc_invalid_order")
        elif event.status == OrderStatus.CANCELED:
            self._reason("qc_canceled_order")

    def _daily_audit(self):
        day = self.time.date().isoformat()
        if self.is_warming_up or not "2025-01-02" <= day <= "2025-03-31" or day in self._valuation_days:
            return
        for holding in self.portfolio.values():
            if holding.invested:
                self._assert_raw_subscriptions(holding.symbol)
        cash = Fraction(str(self.portfolio.cash))
        nav = Fraction(str(self.portfolio.total_portfolio_value))
        holdings = Fraction(str(self.portfolio.total_holdings_value))
        native_quantities = {str(held.symbol.id): Fraction(str(held.quantity))
                             for held in self.portfolio.values()}
        position_mismatches = sum(self._quantity_ledger.get(key, Fraction(0)) != native_quantities.get(key, Fraction(0))
                                  for key in set(self._quantity_ledger) | set(native_quantities))
        self._position_ledger_mismatches += position_mismatches
        cash_residual = abs(cash - self._cash_ledger)
        nav_residual = abs(nav - (self._cash_ledger + holdings))
        self._max_cash_residual = max(self._max_cash_residual, cash_residual)
        self._max_nav_residual = max(self._max_nav_residual, nav_residual)
        self._prior_close_nav, self._prior_close_day = nav, self.time.date()
        self._valuation_days.add(day)
        self.log("TPR_NAV " + json.dumps({"session": self.time.date().isoformat(),
            "nav": _text(nav), "cash": _text(cash),
            "gross_exposure": _text(holdings / nav) if nav else None,
            "position_ledger_mismatches": position_mismatches,
            "cash_ledger_residual": _text(cash_residual),
            "nav_ledger_residual": _text(nav_residual)}, sort_keys=True))

    def on_end_of_algorithm(self):
        # LEAN can call this at April 1: do not invent a valuation session.
        self.log("TPR_SUMMARY " + json.dumps({"candidate_id": self._config["candidate_id"],
            "config_sha256": EXPECTED_CONFIG_SHA256, "packet_sha256": EXPECTED_PACKET_SHA256,
            "freeze_sha256": EXPECTED_FREEZE_SHA256, "decisions": self._decision_count,
            "refused_decisions": self._refused_count, "submitted_orders": self._submitted,
            "engine_end_utc": self.utc_time.replace(tzinfo=UTC).isoformat(),
            "last_valuation_session": (self._prior_close_day.isoformat() if self._prior_close_day else None),
            "valuation_days": len(self._valuation_days), "manual_subscriptions": len(self._manual_symbols),
            "fill_events": self._fill_events, "requested_shares": self._requested_shares,
            "submitted_shares": self._submitted_shares, "filled_shares": self._filled_shares,
            "fees": _text(self._fees), "reason_counts": self._reasons,
            "max_cash_ledger_residual": _text(self._max_cash_residual),
            "max_nav_ledger_residual": _text(self._max_nav_residual),
            "position_ledger_mismatches": self._position_ledger_mismatches,
            "meaningful_execution": (self._fill_events > 0 and self._decision_count == 14
                and self._attempted_days == set(DECISIONS)
                and self._refused_count == 0 and self._max_nav_residual <= Fraction(1, 100)
                and self._max_cash_residual <= Fraction(1, 100)
                and self._position_ledger_mismatches == 0
                and len(self._valuation_days) == 60 and "2025-03-31" in self._valuation_days
                and self._prior_close_day == date(2025, 3, 31)
                and not any(self._reasons.get(reason, 0) for reason in
                    ("missing_mark", "missing_security_subscription", "unpriced_held_nav"))),
            "canonical_admission": False}, sort_keys=True))
