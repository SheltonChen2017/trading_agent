"""New-study OFF-only LEAN driver; software candidate, never native acceptance.

Cloud bundle must provide exact hash-bound comparison_20261028_config and the
public predecessor execution helpers. Only unchanged RAW subscription custody,
known share-basis, prior-close order sizing, native action/fill ledger and
cancellation mechanics are inherited. Predecessor initialize/selection/export
are never called; the old six sleeve labels and old study journal are not used.
Native membership WEIGHTS ARE NEVER READ: membership identity alone defines the
stock universe; market_cap is ranked in its native represented units without
any self-declared percent conversion. Actual input/PIT/source-unit acceptance
remains false until separately verified from retained native evidence.

Official API references, checked2026-10-28:
https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/etf-constituents-universes
https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Data_1_1Fundamental_1_1MorningstarIndustryGroupCode.html
https://www.quantconnect.com/docs/v2/writing-algorithms/securities/market-hours
"""
from AlgorithmImports import *
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction
import hashlib
import json
import re

import extended_core as core
import extended_algorithm_successor as execution
import cap_observer
import comparison_20261028 as comparison

EXPECTED_CONFIG_SHA256 = "__CMP28_CONFIG_SHA256__"
PROJECT = 37650980
STUDY = comparison.STUDY_ID
CANDIDATE = STUDY + "-OFF"
SLEEVES = comparison.SLEEVES
NY, UTC = core.NY, timezone.utc
MAX_RECORD = 512 * 1024
MAX_BYTES = 256 * 1024 * 1024
MAX_RECORDS = 300000
MAX_CHUNKS = 1024
MARK_MODE = "strict_minute_or_raw_daily_equal_close_v1"
MAX_DAILY_CLOSE_CLAIMS = 86940
MARK_REFUSAL_CODES = frozenset(("valuation_clock", "not_real_minute_trade_bar",
    "minute_or_native_close_wrong_day_or_future", "ineligible_minute_or_precise_daily_clock",
    "native_job_custody", "native_raw_config_unproven", "native_cache_reference_changed",
    "captured_price_or_clock_mismatch", "native_snapshot_changed", "daily_scope_already_attempted",
    "daily_count_not_exactly_one", "daily_identity_type_or_clock", "daily_price_or_volume_mismatch",
    "daily_native_request_or_representation_failed", "mark_native_or_representation_failed",
    "daily_access_claim_key_exists_or_unknown", "daily_access_claim_publication_failed",
    "daily_access_claim_readback_mismatch", "daily_access_claim_budget_exhausted"))
KIND_NAMES = frozenset(("SUBSCRIPTION", "MEMBERSHIP", "CAPS", "COVERAGE", "FACTOR", "ORDER", "FILL", "ACTION", "NAV", "SUMMARY"))


class MarkCorroborationRefused(ValueError):
    """Fixed internal reason code, never a native exception/data body."""
    def __init__(self, code):
        self.code = code
        super().__init__("CMP28 mark corroboration refused")


class MarkWitnessStopped(BaseException):
    """Body-free nonordinary stop during private witness publication."""


def _fail():
    raise ValueError("CMP28 OFF native candidate refused") from None


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None or set(value) == {"0"}:
        _fail()
    return value


def _identity(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", value) is None:
        _fail()
    return value


def _wire(value):
    return core.exact_json(value).encode("utf-8")


def native_bytes(value, maximum):
    """Bounded raw Python/CLR bytes only; no codec or compressed representation."""
    if type(maximum) is not int or maximum < 1:
        _fail()
    if type(value) is bytes:
        result = value
    elif type(value) in (bytearray, memoryview):
        if (value.nbytes if type(value) is memoryview else len(value)) > maximum:
            _fail()
        result = bytes(value)
    else:
        # ObjectStore returns System.Byte[] in LEAN. Arbitrary iterables refuse.
        try:
            from System import Array, Byte
            if type(value) is not Array[Byte] or not 0 < value.Length <= maximum:
                _fail()
            result = bytes(value)
        except (ImportError, AttributeError, TypeError, OverflowError):
            _fail()
    if not 0 < len(result) <= maximum:
        _fail()
    return result


def comparison_calendar():
    """New-study calendar identity; exact reviewed legacy session dates only.

    Reusing dates does not reuse the old study identity, evidence or outcomes.
    This declaration contains public exchange dates and cutoffs, no market rows.
    """
    return {"schema": "tpr-cmp28-calendar-candidate-v1", "study_id": STUDY,
        "policy_sha256": hashlib.sha256(comparison.policy_bytes()).hexdigest(),
        "source_calendar_sha256": core.CALENDAR_SHA256,
        "timezone": "America/New_York", "start": "2021-01-04", "end": "2026-10-09",
        "warmup_start": "2020-09-01", "valuation_count": 1449, "decision_count": 301,
        "valuation_sessions": list(core.VALUATIONS), "warmup_sessions": list(core.CALENDAR["warmup_sessions"]),
        "decisions": [dict(row) for row in core.CALENDAR["decisions"]], "no_market_outcomes": True}


def calendar_sha256():
    return hashlib.sha256(_wire(comparison_calendar())).hexdigest()


def validate_config(raw, expected_hash):
    """Closed OFF-only candidate binding, not an access/launch permit.

    source_template_closure_sha256 identifies public pre-render source templates.
    The final rendered cloud source hashes must be retained separately BEFORE
    upload/compile/launch. Including a final source digest in its own embedded
    config would create a hash cycle; no self-declared hash authenticates code.
    """
    expected_hash = _hash(expected_hash)
    if type(raw) is not str or not 0 < len(raw.encode("utf-8")) <= 16384:
        _fail()
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != expected_hash:
        _fail()
    try:
        body = json.loads(raw, object_pairs_hook=core._unique_object,
            parse_constant=lambda _: _fail())
        core._keys(body, ("schema", "study_id", "candidate_id", "arm", "operation_id", "attempt",
            "project_id", "policy_sha256", "calendar_sha256", "source_template_closure_sha256",
            "prior_attempts_looks_sha256", "source_inputs_admitted", "canonical_admission"))
        if (body["schema"] != "tpr-cmp28-off-native-config-v1" or body["study_id"] != STUDY
                or body["candidate_id"] != CANDIDATE or body["arm"] != "cap_off"
                or type(body["project_id"]) is not int or body["project_id"] != PROJECT
                or type(body["attempt"]) is not int or not 1 <= body["attempt"] <= 2**31-1
                or body["policy_sha256"] != hashlib.sha256(comparison.policy_bytes()).hexdigest()
                or body["calendar_sha256"] != calendar_sha256()
                or body["source_inputs_admitted"] is not False or body["canonical_admission"] is not False):
            _fail()
        operation = _identity(body["operation_id"])
        if not operation.startswith("TPR-CMP28-OFF-"):
            _fail()
        _hash(body["source_template_closure_sha256"])
        _hash(body["prior_attempts_looks_sha256"])
        return body
    except Exception:
        _fail()


class ComparisonJournal:
    """Private immutable plain UTF-8 JSONL chunks; plain JSON index published last.

    Native identity is observed before/after every store interaction. Any failed
    publication permanently closes this object against automatic retry. A
    retained index proves bytes only, never rights, historical PIT or acceptance.
    """
    def __init__(self, config, config_sha256, native_getter):
        self._config_raw = _wire(config)
        self._config_hash = _hash(config_sha256)
        self._getter = native_getter
        self._project = self._job = None
        self._faulted = self.closed = False
        self.records, self.bytes, self.counts = [], 0, {}
        self._observe()

    def _observe(self):
        if self._faulted:
            _fail()
        try:
            value = self._getter()
            if type(value) is not tuple or len(value) != 3:
                _fail()
            project, job, locked = value
            if (type(project) is not int or project != PROJECT or type(locked) is not bool
                    or job is not None and (type(job) is not str or job and _identity(job) != job)
                    or locked and not job):
                _fail()
            if self._project is not None and project != self._project:
                _fail()
            if self._job is not None and (job != self._job or not locked):
                _fail()
            self._project = project
            return project, job, locked
        except BaseException:
            self._faulted = True
            raise

    def require_binding(self):
        project, job, locked = self._observe()
        if not locked:
            _fail()
        if self._job is None:
            self._job = job
        config = json.loads(self._config_raw)
        return ("tpr-cmp28/evidence/" + STUDY + "/" + config["operation_id"] + "/"
            + self._config_hash + "/attempt-" + str(config["attempt"]) + "/" + str(project) + "/" + job + "/")

    def append(self, kind, payload):
        _, _, locked = self._observe()
        if locked or self._job is not None:
            self.require_binding()
        if self.closed or type(kind) is not str or kind not in KIND_NAMES:
            _fail()
        raw = _wire({"ordinal": len(self.records) + 1, "kind": kind, "payload": payload}) + b"\n"
        if not 0 < len(raw) <= MAX_RECORD or self.bytes + len(raw) > MAX_BYTES or len(self.records) >= MAX_RECORDS:
            _fail()
        self.records.append(raw)
        self.bytes += len(raw)
        self.counts[kind] = self.counts.get(kind, 0) + 1
        self._observe()

    def export(self, store):
        if self.closed:
            _fail()
        prefix = self.require_binding()
        self.closed = True  # No retry or overwrite after an uncertain store effect.
        try:
            chunks, current = [], bytearray()
            for raw in self.records:
                if len(current) + len(raw) > MAX_RECORD:
                    chunks.append(bytes(current)); current = bytearray()
                current.extend(raw)
            if current:
                chunks.append(bytes(current))
            if not 1 <= len(chunks) <= MAX_CHUNKS:
                _fail()
            publications, metadata = [], []
            for index, raw in enumerate(chunks):
                key = prefix + f"chunk-{index:04d}.jsonl"
                publications.append((key, raw))
                metadata.append({"key": key, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            index = {"schema": "tpr-cmp28-private-journal-index-v2-plain", "study_id": STUDY,
                "candidate_id": CANDIDATE, "config_sha256": self._config_hash,
                "project_id": self._project, "job_id": self._job, "config": json.loads(self._config_raw),
                "records": len(self.records), "plain_bytes": self.bytes, "kind_counts": dict(self.counts),
                "chunks": metadata, "encoding": "utf-8-jsonl",
                "source_inputs_admitted": False, "strategy_accepted": False, "canonical_admission": False}
            index_raw = _wire(index)
            if not 0 < len(index_raw) <= 2 * 1024 * 1024:
                _fail()
            index_key = prefix + "index.json"
            publications.append((index_key, index_raw))
            for key, _ in publications:
                if self.require_binding() != prefix:
                    _fail()
                exists = store.contains_key(key)
                self.require_binding()
                if type(exists) is not bool or exists:
                    _fail()
            for key, raw in publications:
                self.require_binding()
                if store.save_bytes(key, raw) is not True:
                    _fail()
                self.require_binding()
                observed = native_bytes(store.read_bytes(key), len(raw))
                self.require_binding()
                if observed != raw:
                    _fail()
            return {"schema": "tpr-cmp28-private-journal-pointer-v2-plain", "index_key": index_key,
                "index_sha256": hashlib.sha256(index_raw).hexdigest(), "index_bytes": len(index_raw),
                "encoding": "utf-8-jsonl",
                "records": len(self.records), "plain_bytes": self.bytes, "chunks": len(chunks),
                "project_id": self._project, "job_id": self._job, "strategy_accepted": False,
                "source_inputs_admitted": False, "canonical_admission": False}
        except BaseException:
            self._faulted = True
            raise


class ComparisonOffAlgorithm(execution.TargetPriceExtendedAlgorithm):
    """OFF only; inherited money/RAW/action methods keep their original rules."""
    def initialize(self):
        if self.live_mode:
            _fail()
        from comparison_20261028_config import CONFIG_JSON
        self._config = validate_config(CONFIG_JSON, EXPECTED_CONFIG_SHA256)
        self._evidence = ComparisonJournal(self._config, EXPECTED_CONFIG_SHA256,
            lambda: (self.project_id, self.algorithm_id, self.get_locked()))
        self._factor_sources, self._basis_proofs = set(), {}
        self._factor_provider = self._initialized_factor_provider()
        self._signal_store = None  # No signal module, packet, admission flag or fallback.
        self._mark_refusal_witness_attempted = False
        self._initialize_mark_verification()
        self._identities, self._source_ticker_bridge, self._frames = {}, {}, {}
        self.set_start_date(2021, 1, 4)
        self.set_end_date(2026, 10, 9)
        self.set_time_zone("America/New_York")
        self.set_account_currency("USD")
        self.set_cash(100000)
        self._snapshots = {sleeve: [] for sleeve in SLEEVES}
        self._cap_snapshots, self._cap_callback_count = [], 0
        self._event_zones, self._ever_filled_ids, self._ever_targeted_ids = {}, set(), set()
        self._fill_history_unknown = False
        self._native_final_fill_authority = None
        self._native_final_delisting_compatibility_exceptions = 0
        self._delisting_audit = cap_observer.empty_audit()
        self._symbols, self._split_factors, self._custody_since = {}, {}, {}
        self._warmup_finished_minute_validated = False
        self._context_symbols = set()
        self._context_initializer_skips = self._context_change_skips = 0
        self._benchmark_internal_config_max = 0
        self._warning_ids, self._delisted_ids, self._manual_symbols, self._valuation_days = set(), set(), set(), set()
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
        self._membership_coverage_by_day, self._cap_snapshot_coverage_by_day, self._clock_assertions = {}, {}, 0
        self.universe_settings.asynchronous = False
        self.universe_settings.resolution = Resolution.MINUTE
        self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW
        self.add_security_initializer(self._initialize_security)
        self._etf_symbols = {}
        for sleeve in SLEEVES:
            symbol = self.add_equity(sleeve, Resolution.MINUTE, extended_market_hours=sleeve == "SPY",
                data_normalization_mode=DataNormalizationMode.RAW).symbol
            self._etf_symbols[sleeve] = symbol
            self._symbols[str(symbol.id)] = symbol
            universe = self.universe.etf(symbol,
                universe_filter_func=lambda rows, label=sleeve: self._constituents_for(label, rows))
            self._context_symbols.add(universe.symbol)
            self.add_universe(universe)
        cap_universe = self.add_universe(self._capture_caps)
        self._cap_context_symbol = cap_universe.symbol
        self._context_symbols.add(cap_universe.symbol)
        self._benchmark = self._clock_symbol = self._etf_symbols["SPY"]
        self.set_benchmark(self._benchmark)
        core.setup_account_chart(self)
        self.set_warm_up(datetime(2021, 1, 4)-datetime(2020, 9, 1), Resolution.DAILY)
        self.schedule.on(self.date_rules.every_day(self._benchmark), self.time_rules.at(9, 20), self._rebalance)
        self.schedule.on(self.date_rules.every_day(self._benchmark), self.time_rules.at(9, 35), self._cancel_day_orders)
        self.schedule.on(self.date_rules.every_day(self._benchmark), self.time_rules.at(16, 1), self._daily_audit)

    def _constituents_for(self, sleeve, constituents):
        if sleeve not in SLEEVES:
            _fail()
        rows = list(constituents)
        if not rows:
            self._reason("empty_membership_callback_" + sleeve)
            return Universe.UNCHANGED
        if len(rows) > comparison.MAX_IDENTITIES:
            _fail()
        now = self._native_clock(self.utc_time, "UTC")
        members, seen, clocks = [], set(), set()
        census = {"source_rows": len(rows), "us_equity_members": 0,
            "other_market_excluded": 0, "other_security_type_excluded": 0}
        for row in rows:
            if not isinstance(row, ETFConstituentUniverse):
                _fail()
            # ETF universe timestamps carry their native declared data zone.
            zone = row.data_time_zone().id
            effective = self._native_clock(row.end_time, zone)
            if effective > now:
                _fail()
            sid = str(row.symbol.id)
            if not sid or sid in seen:
                _fail()
            seen.add(sid); clocks.add(effective)
            market, kind = row.symbol.id.market, row.symbol.security_type
            if type(market) is not str or not market or kind is None:
                _fail()  # Unknown intrinsic source identity is not an exclusion.
            if kind != SecurityType.EQUITY:
                census["other_security_type_excluded"] += 1
                continue
            if market != Market.USA:
                census["other_market_excluded"] += 1
                continue
            census["us_equity_members"] += 1
            members.append({"symbol": row.symbol, "ticker": row.symbol.value})
        if len(clocks) != 1:
            _fail()
        effective = next(iter(clocks))
        self._snapshots[sleeve].append({"effective": effective, "received": now, "members": members,
            "native_member_coverage": census})
        self._snapshots[sleeve] = [snapshot for snapshot in self._snapshots[sleeve]
            if now-snapshot["effective"] <= timedelta(days=45)]
        # Every identity is subscribed; row.weight/holdings units are irrelevant.
        return [row["symbol"] for row in members]

    @staticmethod
    def _classify_insurance(row):
        from QuantConnect.Data.Fundamental import MorningstarIndustryGroupCode as Groups
        names = ("Agriculture BuildingMaterials Chemicals ForestProducts MetalsAndMining Steel VehiclesAndParts "
            "Furnishings FixturesAndAppliances HomebuildingAndConstruction ManufacturingApparelAndAccessories "
            "PackagingAndContainers PersonalServices Restaurants RetailCyclical TravelAndLeisure AssetManagement "
            "Banks CapitalMarkets Insurance DiversifiedFinancialServices CreditServices RealEstate REITs "
            "BeveragesAlcoholic BeveragesNonAlcoholic ConsumerPackagedGoods Education RetailDefensive TobaccoProducts "
            "Biotechnology DrugManufacturers HealthcarePlans HealthcareProvidersAndServices MedicalDevicesAndInstruments "
            "MedicalDiagnosticsAndResearch MedicalDistribution UtilitiesIndependentPowerProducers UtilitiesRegulated "
            "TelecommunicationServices MediaDiversified InteractiveMedia OilAndGas OtherEnergySources AerospaceAndDefense "
            "BusinessServices Conglomerates Construction FarmAndHeavyConstructionMachinery IndustrialDistribution "
            "IndustrialProducts Transportation WasteManagement Software Hardware Semiconductors").split()
        try:
            known = {int(getattr(Groups, name)) for name in names}
            if row.has_fundamental_data is not True:
                return None
            code = core.native_fraction(row.asset_classification.morningstar_industry_group_code)
            if code.denominator != 1 or int(code) not in known:
                return None
            return "insurance" if int(code) == int(Groups.Insurance) else "noninsurance"
        except (ValueError, TypeError, AttributeError, ArithmeticError):
            return None

    def _capture_caps(self, values):
        rows = list(values)
        if not 1 <= len(rows) <= 20000:
            _fail()
        configs = list(self.subscription_manager.subscription_data_config_service
            .get_subscription_data_configs(self._cap_context_symbol, True))
        if (not configs or any(config.symbol != self._cap_context_symbol or config.is_internal_feed is not True
                or config.resolution != Resolution.DAILY or config.exchange_time_zone.id != "America/New_York"
                or config.type.FullName != "QuantConnect.Data.Fundamental.FundamentalUniverse" for config in configs)):
            _fail()
        now = self._native_clock(self.utc_time, "UTC")
        asof = self._native_clock(rows[0].time, "America/New_York")
        effective = self._native_clock(rows[0].end_time, "America/New_York")
        if not asof <= effective <= now:
            _fail()
        wanted = set(self._symbols)
        for snapshots in self._snapshots.values():
            for snapshot in snapshots:
                wanted.update(str(row["symbol"].id) for row in snapshot["members"])
        caps, classifications = {}, {}
        for row in rows:
            if not isinstance(row, Fundamental):
                _fail()
            sid = str(row.symbol.id)
            if sid not in wanted:
                continue
            if (sid in caps or self._native_clock(row.time, "America/New_York") != asof
                    or self._native_clock(row.end_time, "America/New_York") != effective):
                _fail()
            classifications[sid] = self._classify_insurance(row)
            try:
                value = row.market_cap
                if value is None:
                    caps[sid] = {"state": "missing", "value": None}
                    continue
                amount = core.native_fraction(value)
                caps[sid] = {"state": "available" if amount > 0 else "nonpositive", "value": core._text(amount)}
            except (ValueError, TypeError, AttributeError, ArithmeticError):
                caps[sid] = {"state": "unknown", "value": None}
        self._cap_callback_count += 1
        self._cap_snapshots.append({"effective": effective, "asof": asof, "received": now,
            "caps": caps, "insurance": classifications})
        self._cap_snapshots = [row for row in self._cap_snapshots if now-row["effective"] <= timedelta(days=45)]
        return []

    def _prepare_targets(self, day):
        cutoff = core._clock(core.CUTOFF_BY_DAY[day])
        if cutoff >= self._native_clock(self.utc_time, "UTC") or self._config["arm"] != "cap_off":
            _fail()
        snapshots = {sleeve: core.select_snapshot(self._snapshots[sleeve], cutoff) for sleeve in SLEEVES}
        self._membership_coverage_by_day[day] = {sleeve: {"available": row is not None,
            "member_count": len(row["members"]) if row is not None else None} for sleeve, row in snapshots.items()}
        cap_snapshot = self._select_caps(cutoff)
        self._cap_snapshot_coverage_by_day[day] = cap_snapshot is not None
        if cap_snapshot is None or any(row is None for row in snapshots.values()):
            self._decision_coverage[day] = None
            self._reason("missing_lagged_native_universe_or_caps")
            return
        members, symbols, reports = {}, {}, {}
        for sleeve, snapshot in snapshots.items():
            members[sleeve] = [{"sid": str(row["symbol"].id), "ticker": row["ticker"]} for row in snapshot["members"]]
            symbols.update({str(row["symbol"].id): row["symbol"] for row in snapshot["members"]})
            reports[sleeve] = {"member_count": len(snapshot["members"]), "membership_weights_used": False,
                "native_member_coverage": dict(snapshot["native_member_coverage"]),
                "effective_utc": snapshot["effective"].isoformat(), "received_utc": snapshot["received"].isoformat()}
            self._log_audit("MEMBERSHIP", {"session": day, "sleeve": sleeve, **reports[sleeve], "members": members[sleeve]})
        finance = {row["sid"]: cap_snapshot["insurance"].get(row["sid"]) for row in members["XLF"]}
        if any(value not in ("insurance", "noninsurance") for value in finance.values()):
            self._decision_coverage[day] = None
            self._reason("unknown_asof_finance_classification")
            return
        # The native snapshot also covers old subscribed identities and recent
        # historical membership for action custody. Only the EXACT current six-
        # universe union belongs to this construction call. Preserve every
        # current missing cell; old cells cannot exhaust its4096 identity bound.
        source_caps = cap_snapshot["caps"]
        if type(source_caps) is not dict:
            _fail()
        current_caps = {sid: source_caps.get(sid, {"state": "missing", "value": None}) for sid in sorted(symbols)}
        ignored_noncurrent = len(set(source_caps) - set(symbols))
        weights, detail = comparison.construct_off(members, current_caps,
            finance_insurance_by_sid=finance, warning_ids=self._warning_ids, final_ids=self._delisted_ids)
        for sleeve in SLEEVES:
            reports[sleeve].update(detail["per_sleeve"][sleeve])
        self._targets = {sid: symbols[sid] for sid in weights}
        self._target_weights = weights
        self._symbols.update(self._targets)
        self._ever_targeted_ids.update(weights)
        self._decision_coverage[day] = {"session": day, "arm": "cap_off", "sleeves": reports,
            "construction": detail, "target_gross": core._text(detail["target_gross_weight"]),
            "unallocated_target_cash": core._text(detail["cash_weight"]),
            "source_cap_snapshot_cell_count": len(source_caps), "current_member_cap_domain_count": len(current_caps),
            "ignored_noncurrent_cap_cells": ignored_noncurrent,
            "source_inputs_admitted": False, "native_source_units_accepted": False}
        self._log_audit("CAPS", {"session": day, "effective_utc": cap_snapshot["effective"].isoformat(),
            "asof_utc": cap_snapshot["asof"].isoformat(), "received_utc": cap_snapshot["received"].isoformat(),
            "caps": current_caps, "source_cap_snapshot_cell_count": len(source_caps),
            "current_member_cap_domain_count": len(current_caps), "ignored_noncurrent_cap_cells": ignored_noncurrent,
            "finance_insurance": finance, "native_source_units_accepted": False})

    def _selected_scores(self, *_args, **_kwargs):
        _fail()  # Every non-OFF path stays closed, including inherited call seams.

    def _retain_mark_refusal_witness(self, symbol, close, observed):
        """One private <=4KiB own-job diagnostic; never repair/admit a mark.

        The exact failed close inputs are supplied by the guard, not queried
        again. There is no History call, price field, overwrite or retry. Only
        the small safe pointer/predicate envelope is eligible for public logs.
        """
        pointer = {"schema": "tpr-cmp28-mark-refusal-pointer-v2", "status": "not_published",
            "key": None, "bytes": None, "expected_sha256": None, "verified_sha256": None,
            "readback_verified": False, "data_type": "trade_bar", "predicates": {
                "observed_equals_expected": observed == close,
                "expected_date_equals_algorithm": None, "observed_date_equals_session": None,
                "observed_relation": "before" if observed < close else "after" if observed > close else "equal"}}
        if getattr(self, "_mark_refusal_witness_attempted", False):
            pointer["status"] = "already_attempted"
            return pointer
        self._mark_refusal_witness_attempted = True  # BEFORE every possible effect.
        try:
            now = self._native_clock(self.utc_time, "UTC")
            pointer["predicates"]["expected_date_equals_algorithm"] = close.date() == now.date()
            pointer["predicates"]["observed_date_equals_session"] = observed.astimezone(NY).date() == now.astimezone(NY).date()
            prefix = self._evidence.require_binding()
            project, job = self.project_id, self.algorithm_id
            config = json.loads(self._evidence._config_raw)
            if (type(project) is not int or project != config["project_id"]
                    or type(job) is not str or _identity(job) != job
                    or not prefix.endswith("/" + str(project) + "/" + job + "/")):
                _fail()
            sid = str(symbol.id)
            if not 0 < len(sid) <= 256 or sid.strip() != sid or any(ord(char) < 32 or ord(char) == 127 for char in sid):
                _fail()
            body = {"schema": "tpr-cmp28-private-mark-refusal-v2", "study_id": STUDY,
                "candidate_id": config["candidate_id"], "arm": config["arm"],
                "operation_id": config["operation_id"], "attempt": config["attempt"],
                "config_sha256": self._evidence._config_hash,
                "source_template_closure_sha256": config["source_template_closure_sha256"],
                "policy_sha256": config["policy_sha256"], "calendar_sha256": config["calendar_sha256"],
                "project_id": project, "job_id": job, "security_id": sid, "data_type": "trade_bar",
                "algorithm_utc": now.isoformat(), "algorithm_local": now.astimezone(NY).isoformat(),
                "expected_close_utc": close.isoformat(), "expected_close_local": close.astimezone(NY).isoformat(),
                "observed_end_utc": observed.isoformat(), "observed_end_local": observed.astimezone(NY).isoformat(),
                "predicates": dict(pointer["predicates"]), "valuation_verification_mode": MARK_MODE,
                "verification_policy_extended": True,
                "source_inputs_admitted": False, "strategy_accepted": False, "canonical_admission": False}
            raw = _wire(body)
            if not 0 < len(raw) <= 4096:
                _fail()
            key, digest = prefix + "mark-refusal.json", hashlib.sha256(raw).hexdigest()
            pointer.update(key=key, bytes=len(raw), expected_sha256=digest)

            def bound():
                if (self._evidence.require_binding() != prefix or type(self.project_id) is not int
                        or self.project_id != project or self.algorithm_id != job or self.get_locked() is not True):
                    _fail()

            def guarded(call):
                bound()
                try:
                    value = call()
                except BaseException as first:
                    # Observe custody after an uncertain effect too. Cancellation
                    # has priority, then the first nonordinary fatal condition.
                    try:
                        bound()
                    except BaseException as second:
                        if isinstance(second, KeyboardInterrupt):
                            raise second
                        if isinstance(first, KeyboardInterrupt) or not isinstance(first, Exception):
                            raise first
                        if not isinstance(second, Exception):
                            raise second
                    raise
                bound()
                return value

            exists = guarded(lambda: self.object_store.contains_key(key))
            if type(exists) is not bool or exists:
                pointer["status"] = "existing_or_unknown_key_refused"
                return pointer  # Never reopen or overwrite an existing object.
            saved = guarded(lambda: self.object_store.save_bytes(key, raw))
            if saved is not True:
                pointer["status"] = "save_unconfirmed"
                return pointer
            readback = native_bytes(guarded(lambda: self.object_store.read_bytes(key)), 4096)
            if len(readback) != len(raw) or hashlib.sha256(readback).hexdigest() != digest or readback != raw:
                pointer["status"] = "readback_mismatch"
                return pointer
            pointer.update(status="verified", verified_sha256=digest, readback_verified=True)
        except KeyboardInterrupt:
            raise KeyboardInterrupt("CMP28 mark witness cancelled") from None
        except Exception:
            pointer["status"] = "publication_failed"
        except BaseException:
            raise MarkWitnessStopped("CMP28 mark witness stopped") from None
        return pointer

    def _initialize_mark_verification(self):
        contract = comparison.policy()["valuation_verification_contract"]
        if contract["mode"] != MARK_MODE or contract["decision_id"] != "TPR-CMP104-D009" or contract["all_five_arms"] is not True:
            _fail()
        self._mark_verification_counts = {"strict_minute_marks": 0, "daily_requests": 0,
            "daily_claims_attempted": 0, "daily_claims_verified": 0,
            "daily_corroborated_marks": 0, "refused_marks": 0}
        self._mark_history_attempts = set()

    def _mark_verification_summary(self):
        if not hasattr(self, "_mark_verification_counts"):
            self._initialize_mark_verification()
        return {"mode": MARK_MODE, "decision_id": "TPR-CMP104-D009",
            **self._mark_verification_counts, "minute_endpoints_rewritten": 0, "prices_substituted": 0}

    def _reject_mark(self, symbol, close, observed, code, data_type="trade_bar"):
        self._mark_verification_summary()
        self._mark_verification_counts["refused_marks"] += 1
        if isinstance(close, datetime) and isinstance(observed, datetime) and symbol is not None:
            pointer = self._retain_mark_refusal_witness(symbol, close, observed)
        else:
            pointer = {"schema": "tpr-cmp28-mark-refusal-pointer-v2", "status": "clock_witness_unavailable",
                "key": None, "bytes": None, "expected_sha256": None, "verified_sha256": None,
                "readback_verified": False, "data_type": data_type, "predicates": {}}
        pointer["reason_code"] = code if type(code) is str and code in MARK_REFUSAL_CODES else "mark_native_or_representation_failed"
        pointer["valuation_verification_mode"] = MARK_MODE
        notice = "CMP28_MARK_REFUSAL " + json.dumps(pointer, sort_keys=True, separators=(",", ":"))
        try:
            self.log(notice)
        except KeyboardInterrupt:
            raise KeyboardInterrupt("CMP28 mark refusal notice cancelled") from None
        except Exception:
            pass
        except BaseException:
            raise MarkWitnessStopped("CMP28 mark refusal notice stopped") from None
        # The safe pointer survives when QC's queued Log messages are lost.
        raise ValueError(notice) from None

    def _corroborate_raw_daily_close(self, held, security, last, close, observed, now):
        """D009: corroborate the unchanged price, never rewrite cache or clock."""
        def refuse(code):
            raise MarkCorroborationRefused(code) from None
        try:
            from System import Object as NetObject
            from QuantConnect import AlgorithmSettings
            from QuantConnect.Data import SubscriptionDataConfig
            symbol, sid = held.symbol, str(held.symbol.id)
            settings = self.settings
            if (not isinstance(settings, AlgorithmSettings) or self.settings.daily_precise_end_time is not True
                    or not isinstance(last.period, timedelta) or last.period != timedelta(minutes=1)
                    or last.is_fill_forward is not False or last.symbol != symbol
                    or self._native_clock(last.time, "America/New_York") + timedelta(minutes=1) != observed
                    or observed.astimezone(NY).date() != now.astimezone(NY).date()
                    or not observed < close <= now or close.astimezone(NY).date() != now.astimezone(NY).date()
                    or self._native_clock(self.time,"America/New_York") != now):
                refuse("ineligible_minute_or_precise_daily_clock")
            prefix = self._evidence.require_binding()
            project, job = self.project_id, self.algorithm_id
            if (type(project) is not int or project != self._config["project_id"]
                    or type(job) is not str or _identity(job) != job
                    or not prefix.endswith("/"+str(project)+"/"+job+"/")):
                refuse("native_job_custody")
            def raw_snapshot():
                actual, configs = self._raw_security_configs(symbol)
                if (not NetObject.ReferenceEquals(actual, security) or not configs or len(configs)>64
                        or any(not isinstance(row, SubscriptionDataConfig) or row.symbol != symbol
                            or row.is_internal_feed is not False or row.data_normalization_mode != DataNormalizationMode.RAW
                            for row in configs)
                        or not any(row.resolution == Resolution.MINUTE and row.tick_type == TickType.TRADE
                            and row.type.FullName == "QuantConnect.Data.Market.TradeBar" for row in configs)):
                    refuse("native_raw_config_unproven")
                current_held = self.portfolio[symbol]
                current = security.get_last_data()
                if (not NetObject.ReferenceEquals(current_held, held) or not NetObject.ReferenceEquals(current, last)
                        or not isinstance(current, TradeBar) or current.is_fill_forward is not False
                        or current.symbol != symbol or not isinstance(current.period, timedelta)):
                    refuse("native_cache_reference_changed")
                return {"cache": security.cache, "values": {
                    "cache_time_utc": self._native_clock(current.time,"America/New_York").isoformat(),
                    "cache_end_utc": self._native_clock(current.end_time,"America/New_York").isoformat(),
                    "cache_period_microseconds": current.period//timedelta(microseconds=1),
                    "cache_symbol_id": str(current.symbol.id), "cache_fill_forward": current.is_fill_forward,
                    "cache_price": core.native_fraction(current.price), "security_price": core.native_fraction(security.price),
                    "quantity": core.native_fraction(current_held.quantity), "cash": core.native_fraction(self.portfolio.cash),
                    "nav": core.native_fraction(self.portfolio.total_portfolio_value),
                    "holdings_value": core.native_fraction(self.portfolio.total_holdings_value),
                    "algorithm_utc": self._native_clock(self.utc_time,"UTC").isoformat(), "algorithm_local": self.time.isoformat(),
                    "raw_configs": sorted((str(row.symbol.id),str(row.resolution),str(row.tick_type),row.type.FullName,
                        str(row.data_normalization_mode),row.extended_market_hours,row.fill_data_forward) for row in configs)}}
            before = raw_snapshot()
            if (before["values"]["cache_price"] <= 0 or before["values"]["cache_price"] != before["values"]["security_price"]
                    or before["values"]["cache_end_utc"] != observed.isoformat()
                    or before["values"]["algorithm_utc"] != now.isoformat()):
                refuse("captured_price_or_clock_mismatch")
            def bound():
                if (self._evidence.require_binding() != prefix or self.project_id != project or self.algorithm_id != job
                        or self.get_locked() is not True or not isinstance(self.settings, AlgorithmSettings)
                        or not NetObject.ReferenceEquals(settings,self.settings) or self.settings.daily_precise_end_time is not True):
                    refuse("native_job_custody")
                after = raw_snapshot()
                if not NetObject.ReferenceEquals(before["cache"], after["cache"]) or before["values"] != after["values"]:
                    refuse("native_snapshot_changed")
            def guarded(call):
                bound()
                try:
                    value = call()
                except BaseException as first:
                    try:
                        bound()
                    except BaseException as second:
                        if isinstance(second, KeyboardInterrupt): raise second
                        if isinstance(first, KeyboardInterrupt) or not isinstance(first, Exception): raise first
                        if not isinstance(second, Exception): raise second
                    raise
                bound()
                return value
            scope = (now.astimezone(NY).date().isoformat(), sid)
            if scope in self._mark_history_attempts:
                refuse("daily_scope_already_attempted")
            if self._mark_verification_counts["daily_claims_attempted"] >= MAX_DAILY_CLOSE_CLAIMS:
                refuse("daily_access_claim_budget_exhausted")
            self._mark_history_attempts.add(scope)  # Spent BEFORE claim/publication/History effects.
            self._mark_verification_counts["daily_claims_attempted"] += 1
            start, end = datetime.combine(self.time.date(),time()), self.time
            claim = {"schema": "tpr-cmp28-daily-close-access-claim-v1", "study_id": STUDY,
                "mode": MARK_MODE, "decision_id": "TPR-CMP104-D009", "candidate_id": self._config["candidate_id"],
                "arm": self._config["arm"], "operation_id": self._config["operation_id"], "attempt": self._config["attempt"],
                "project_id": project, "job_id": job, "config_sha256": self._evidence._config_hash,
                "parent_config_sha256": self._evidence._config_hash,
                "source_template_closure_sha256": self._config["source_template_closure_sha256"],
                "policy_sha256": self._config["policy_sha256"], "calendar_sha256": self._config["calendar_sha256"],
                "security_id": sid, "session": scope[0], "spent_before_effect": True,
                "request": {"start_local": start.isoformat(), "end_local": end.isoformat(), "resolution": "DAILY",
                    "normalization": "RAW", "fill_forward": False, "extended_market_hours": False, "max_rows": 2},
                "scope": "exact-held-SID-current-session-close-corroboration-only",
                "parent_external_operation_manifest_required": True, "permission_issued": False,
                "outcome_permission": False, "source_inputs_admitted": False, "canonical_admission": False}
            claim_raw = _wire(claim)
            if not 0 < len(claim_raw) <= 4096:
                refuse("daily_access_claim_publication_failed")
            claim_key = prefix + "daily-close-claims/" + scope[0] + "-" + hashlib.sha256(sid.encode("utf-8")).hexdigest() + ".json"
            claim_hash = hashlib.sha256(claim_raw).hexdigest()
            try:
                exists = guarded(lambda: self.object_store.contains_key(claim_key))
                if type(exists) is not bool or exists:
                    refuse("daily_access_claim_key_exists_or_unknown")
                saved = guarded(lambda: self.object_store.save_bytes(claim_key, claim_raw))
                if saved is not True:
                    refuse("daily_access_claim_publication_failed")
                readback = native_bytes(guarded(lambda: self.object_store.read_bytes(claim_key)),4096)
                if len(readback) != len(claim_raw) or hashlib.sha256(readback).hexdigest() != claim_hash or readback != claim_raw:
                    refuse("daily_access_claim_readback_mismatch")
            except KeyboardInterrupt:
                raise
            except MarkCorroborationRefused:
                raise
            except Exception:
                refuse("daily_access_claim_publication_failed")
            self._mark_verification_counts["daily_claims_verified"] += 1
            claim_pointer = {"key": claim_key, "sha256": claim_hash, "bytes": len(claim_raw)}
            def request_history():
                method = self.history[TradeBar]
                self._mark_verification_counts["daily_requests"] += 1
                return method(symbol, start, end, Resolution.DAILY,
                    fill_forward=False, extended_market_hours=False, data_normalization_mode=DataNormalizationMode.RAW)
            history = guarded(request_history)
            iterator = guarded(lambda: iter(history))
            sentinel = object()
            daily = guarded(lambda: next(iterator, sentinel))
            second = guarded(lambda: next(iterator, sentinel))
            if daily is sentinel or second is not sentinel:
                refuse("daily_count_not_exactly_one")
            if (not isinstance(daily, TradeBar) or daily.symbol != symbol or daily.is_fill_forward is not False
                    or self._native_clock(daily.time,"America/New_York").astimezone(NY).date() != self.time.date()
                    or self._native_clock(daily.end_time,"America/New_York") != close or close > now):
                refuse("daily_identity_type_or_clock")
            daily_price, volume = core.native_fraction(daily.close), core.native_fraction(daily.volume)
            if daily_price <= 0 or volume <= 0 or daily_price != before["values"]["security_price"] or daily_price != before["values"]["cache_price"]:
                refuse("daily_price_or_volume_mismatch")
            bound()
            self._log_audit("NAV", {"record_type": "raw_daily_equal_close_corroboration", "schema": "tpr-cmp28-raw-daily-close-proof-v1",
                "session": scope[0], "security_id": sid, "mode": MARK_MODE, "decision_id": "TPR-CMP104-D009",
                "project_id": project, "job_id": job, "config_sha256": self._evidence._config_hash,
                "source_template_closure_sha256": self._config["source_template_closure_sha256"],
                "policy_sha256": self._config["policy_sha256"], "calendar_sha256": self._config["calendar_sha256"],
                "request": {"start_local": start.isoformat(), "end_local": end.isoformat(), "resolution": "DAILY",
                    "normalization": "RAW", "fill_forward": False, "extended_market_hours": False, "max_rows": 2},
                "original_minute_end_utc": observed.isoformat(), "daily_end_utc": close.isoformat(),
                "daily_time_utc": self._native_clock(daily.time,"America/New_York").isoformat(),
                "daily_close": daily_price, "daily_volume": volume, "native_snapshot": before["values"],
                "daily_access_claim": claim_pointer,
                "minute_endpoint_equals_close": False, "daily_price_equals_unchanged_cache": True,
                "native_snapshot_unchanged": True, "source_inputs_admitted": False, "canonical_admission": False})
            bound()
            self._mark_verification_counts["daily_corroborated_marks"] += 1
        except KeyboardInterrupt:
            raise KeyboardInterrupt("CMP28 daily close corroboration cancelled") from None
        except MarkCorroborationRefused:
            raise
        except Exception:
            raise MarkCorroborationRefused("daily_native_request_or_representation_failed") from None
        except BaseException:
            raise MarkWitnessStopped("CMP28 daily close corroboration stopped") from None

    def _daily_audit(self):
        self._mark_verification_summary()
        if not self.is_warming_up and self.time.date().isoformat() in core.VALUATIONS and self.time.time() != time(16, 1):
            self._reject_mark(None,None,None,"valuation_clock","unavailable")
        if not self.is_warming_up and self.time.date().isoformat() in core.VALUATIONS:
            for held in self.portfolio.values():
                if not held.invested:
                    continue
                close = observed = last = None
                try:
                    security = self._assert_raw_subscriptions(held.symbol)
                    last = security.get_last_data()
                    if not isinstance(last, TradeBar) or last.is_fill_forward is not False or last.period != timedelta(minutes=1):
                        raise MarkCorroborationRefused("not_real_minute_trade_bar")
                    session_start = datetime.combine(self.time.date(),time())
                    close = self._native_clock(security.exchange.hours.get_next_market_close(session_start,False),"America/New_York")
                    observed = self._native_clock(last.end_time,"America/New_York")
                    now = self._native_clock(self.utc_time,"UTC")
                    if (observed.astimezone(NY).date() != self.time.date() or close.astimezone(NY).date() != self.time.date()
                            or observed > close or close > now):
                        raise MarkCorroborationRefused("minute_or_native_close_wrong_day_or_future")
                    if observed == close:
                        self._mark_verification_counts["strict_minute_marks"] += 1
                    else:
                        self._corroborate_raw_daily_close(held,security,last,close,observed,now)
                except KeyboardInterrupt:
                    raise KeyboardInterrupt("CMP28 mark verification cancelled") from None
                except MarkCorroborationRefused as error:
                    self._reject_mark(held.symbol,close,observed,error.code,
                        "trade_bar" if isinstance(last,TradeBar) else "not_trade_bar")
                except Exception:
                    self._reject_mark(held.symbol,close,observed,"mark_native_or_representation_failed",
                        "trade_bar" if isinstance(last,TradeBar) else "unavailable")
                except BaseException:
                    raise MarkWitnessStopped("CMP28 mark verification stopped") from None
        return super()._daily_audit()

    def on_end_of_algorithm(self):
        self._evidence.require_binding()
        coverage_ok = (set(self._decision_coverage) == set(core.DECISIONS)
            and all(row is not None and set(row["sleeves"]) == set(SLEEVES) for row in self._decision_coverage.values()))
        parity = (not self._position_ledger_mismatches and self._max_cash_residual <= Fraction(1, 100)
            and self._max_nav_residual <= Fraction(1, 100) and not self._risk_breaches)
        cap_observer.validate_audit(self._delisting_audit, self._reasons.get("delisting_event", 0))
        calendar_complete = self._attempted_days == set(core.DECISIONS) and self._valuation_days == set(core.VALUATIONS)
        useful = (calendar_complete and coverage_ok and parity and self._decision_count == 301
            and not self._refused_count and self._fill_events > 0 and self._warmup_finished_minute_validated
            and not any(self._reasons.get(name, 0) for name in ("missing_mark", "missing_action_custody",
                "unknown_share_basis", "basis_native_action_mismatch", "unpriced_held_nav", "missing_prior_close_nav",
                "qc_invalid_order", "qc_canceled_order")))
        summary = {"schema": "tpr-cmp28-off-native-summary-v1", "study_id": STUDY, "candidate_id": CANDIDATE,
            "arm": "cap_off", "operation_id": self._config["operation_id"], "attempt": self._config["attempt"],
            "config_sha256": EXPECTED_CONFIG_SHA256, "policy_sha256": self._config["policy_sha256"],
            "calendar_sha256": calendar_sha256(), "source_template_closure_sha256": self._config["source_template_closure_sha256"],
            "project_id": self.project_id, "job_id": self.algorithm_id,
            "decisions": self._decision_count, "refused_decisions": self._refused_count,
            "valuation_days": len(self._valuation_days), "coverage_complete": coverage_ok,
            "calendar_complete": calendar_complete, "internally_useful_order_run": useful,
            "accounting_parity_within_cent": parity, "submitted_orders": self._submitted, "fill_events": self._fill_events,
            "requested_shares": self._requested_shares, "submitted_shares": self._submitted_shares,
            "filled_shares": self._filled_shares, "fees": self._fees,
            "last_observed_nav": self._prior_close_nav if self._prior_close_day is not None else None,
            "last_valuation_session": self._prior_close_day.isoformat() if self._prior_close_day is not None else None,
            "final_nav": self._prior_close_nav if calendar_complete and self._prior_close_day == date(2026, 10, 9) else None,
            "max_cash_residual": self._max_cash_residual, "max_nav_residual": self._max_nav_residual,
            "position_ledger_mismatches": self._position_ledger_mismatches, "risk_breaches": self._risk_breaches,
            "max_name_exposure": self._max_name_exposure, "name_soft_cap_breaches": self._name_soft_cap_breaches,
            "clock_assertions": self._clock_assertions, "reason_counts": dict(self._reasons),
            "delisting_audit": self._delisting_audit, "mark_verification": self._mark_verification_summary(),
            "source_inputs_admitted": False,
            "native_basis_authenticated": False, "full_evidence_retrieval_verified": False,
            "strategy_accepted": False, "canonical_admission": False, "accepted_performance": None}
        self._log_audit("SUMMARY", summary)
        pointer = self._evidence.export(self.object_store)
        # Own-account aggregate and exact private index pointer only. Raw market,
        # cap/classification/member/factor rows never leave the private journal.
        self.log("CMP28_OFF_SUMMARY " + core.exact_json(summary))
        self.log("CMP28_OFF_EVIDENCE_INDEX " + json.dumps(pointer, sort_keys=True, separators=(",", ":")))
