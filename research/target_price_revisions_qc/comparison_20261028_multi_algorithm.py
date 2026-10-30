"""Native four-arm successor using the preserved RAW/order/accounting paths.

Source template only. No real input descriptors are invented here; a renderer
must bind the new closed configuration and the actual private signal packet.
Signals are bound by the native provider inside QC, after cap-only selection
for tilt arms and over complete current membership for pure TPR selection.
Zero-weight donors remain in selection/marks/evidence and are omitted ONLY
from the order planner's target mapping; held zero-target names still sell via
its holdings union. No clipping, renormalization, shorts or score fallback.
"""
from AlgorithmImports import *
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction
import hashlib
import json
import re

import comparison_20261028_algorithm as off
import comparison_20261028_signal_native as signal_native
import comparison_20261028 as comparison

core, execution, cap_observer = off.core, off.execution, off.cap_observer
native_bytes = off.native_bytes
STUDY, SLEEVES, NY, UTC = comparison.STUDY_ID, comparison.SLEEVES, core.NY, timezone.utc
DECISIONS, CUTOFFS = core.DECISIONS, core.CUTOFFS
native_fraction, calendar_sha256 = core.native_fraction, off.calendar_sha256
_wire, _hash, _identity = off._wire, off._hash, off._identity
MAX_RECORD, MAX_CHUNKS = off.MAX_RECORD, off.MAX_CHUNKS
EXPECTED_CONFIG_SHA256 = "__CMP28_MULTI_CONFIG_SHA256__"
CANDIDATES = {"cap_tilt_50": STUDY + "-CAP-TILT-50", "cap_tilt_100": STUDY + "-CAP-TILT-100",
    "cap_tilt_200": STUDY + "-CAP-TILT-200", "pure_tpr": STUDY + "-PURE-TPR"}
PROJECTS = frozenset((37650980, 37650453))


def _fail():
    raise ValueError("CMP28 multi native candidate refused") from None


def session_axis():
    return [{"session_date": day, "open_utc": datetime.combine(date.fromisoformat(day), time(9,30), NY).astimezone(UTC).isoformat()}
        for day in core.CALENDAR["warmup_sessions"] + list(core.VALUATIONS)]


def validate_config(raw, expected_hash):
    _hash(expected_hash)
    if type(raw) is not str or not 0 < len(raw.encode("utf-8")) <= 16384 or hashlib.sha256(raw.encode()).hexdigest() != expected_hash:
        _fail()
    try:
        body = json.loads(raw, object_pairs_hook=core._unique_object, parse_constant=lambda _: _fail())
        core._keys(body, ("schema", "study_id", "candidate_id", "arm", "operation_id", "attempt", "project_id",
            "policy_sha256", "calendar_sha256", "source_template_closure_sha256", "prior_attempts_looks_sha256",
            "signal_packet", "source_inputs_admitted", "canonical_admission"))
        if (body["schema"] != "tpr-cmp28-multi-native-config-v1" or body["study_id"] != STUDY
                or type(body["arm"]) is not str or body["arm"] not in CANDIDATES
                or body["candidate_id"] != CANDIDATES[body["arm"]]
                or type(body["attempt"]) is not int or not 1 <= body["attempt"] <= 2**31-1
                or type(body["project_id"]) is not int or body["project_id"] not in PROJECTS
                or body["policy_sha256"] != hashlib.sha256(comparison.policy_bytes()).hexdigest()
                or body["calendar_sha256"] != calendar_sha256()
                or body["source_inputs_admitted"] is not False or body["canonical_admission"] is not False
                or not _identity(body["operation_id"]).startswith("TPR-CMP28-")):
            _fail()
        _hash(body["source_template_closure_sha256"]); _hash(body["prior_attempts_looks_sha256"])
        packet = body["signal_packet"]
        core._keys(packet, ("key", "sha256", "bytes", "encoding", "source_inventory_sha256"))
        if (type(packet["key"]) is not str or not packet["key"].startswith("tpr-cmp28/inputs/")
                or len(packet["key"]) > 512 or re.fullmatch(r"[A-Za-z0-9_./-]+", packet["key"]) is None
                or any(part in ("", ".", "..") for part in packet["key"].split("/"))
                or packet["encoding"] != "utf-8-json"
                or type(packet["bytes"]) is not int or not 0 < packet["bytes"] <= 512*1024**2):
            _fail()
        for name in ("sha256", "source_inventory_sha256"): _hash(packet[name])
        return body
    except (ValueError, TypeError, KeyError, AttributeError):
        _fail()


def positive_order_targets(weights):
    if type(weights) is not dict:
        _fail()
    exact = {sid: comparison.legacy._exact_number(value) for sid,value in weights.items()}
    if any(type(sid) is not str or not sid or not 0 <= value <= Fraction(1,10) for sid,value in exact.items()) or sum(exact.values(), Fraction(0)) > 1:
        _fail()
    return {sid: value for sid,value in exact.items() if value != 0}


def score_frame_sha256(scores):
    if type(scores) is not dict or len(scores) > comparison.MAX_IDENTITIES:
        _fail()
    for sid, cell in scores.items():
        comparison._sid(sid)
        core._keys(cell, ("state", "value"))
        if (type(cell["state"]) is not str or cell["state"] not in ("available","nonzero","zero","missing","unknown","invalid")
                or cell["value"] is not None and (type(cell["value"]) is not str or len(cell["value"]) > 128)):
            _fail()
    raw = json.dumps(scores,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")
    if len(raw) > 8*1024**2:
        _fail()
    return hashlib.sha256(raw).hexdigest()


class SignalRuntimeStopped(BaseException):
    """Body-free nonordinary stop; never demoted into an ordinary refusal."""


class MultiJournal(off.ComparisonJournal):
    def __init__(self, config, config_sha256, native_getter):
        if (type(config) is not dict or type(config.get("project_id")) is not int
                or config["project_id"] not in PROJECTS or config.get("arm") not in CANDIDATES
                or config.get("candidate_id") != CANDIDATES[config["arm"]]):
            _fail()
        self._expected_project = config["project_id"]
        super().__init__(config, config_sha256, native_getter)

    def _observe(self):
        if self._faulted:
            _fail()
        try:
            value = self._getter()
            if type(value) is not tuple or len(value) != 3:
                _fail()
            project, job, locked = value
            if (type(project) is not int or project != self._expected_project or type(locked) is not bool
                    or job is not None and (type(job) is not str or job and _identity(job) != job)
                    or locked and not job or self._project is not None and project != self._project
                    or self._job is not None and (job != self._job or not locked)):
                _fail()
            self._project = project
            return project, job, locked
        except BaseException:
            self._faulted = True
            raise

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
                "candidate_id": json.loads(self._config_raw)["candidate_id"], "config_sha256": self._config_hash,
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




class ComparisonMultiAlgorithm(off.ComparisonOffAlgorithm):
    def initialize(self):
        if self.live_mode:
            _fail()
        from comparison_20261028_config import CONFIG_JSON
        self._config = validate_config(CONFIG_JSON, EXPECTED_CONFIG_SHA256)
        self._evidence = MultiJournal(self._config, EXPECTED_CONFIG_SHA256,
            lambda: (self.project_id, self.algorithm_id, self.get_locked()))
        self._factor_sources, self._basis_proofs = set(), {}
        self._factor_provider = self._initialized_factor_provider()
        self._signal_store = None
        self._mark_refusal_witness_attempted = False
        self._initialize_mark_verification()
        if type(self.project_id) is not int or self.project_id != self._config["project_id"]:
            _fail()
        self._initialize_signal_runtime()
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


    def _initialize_signal_runtime(self):
        # Initialization has no actual job ID yet: no private read or parse.
        self._signal_provider = None
        self._signal_packet_attempted = False
        self._signal_runtime_faulted = False
        self._signal_native_binding = None
        self._signal_runtime = {"claim_attempts":0,"claim_same_node_verified":False,
            "backend_durability_proven":False,"claim_key":None,"claim_sha256":None,"claim_bytes":None,
            "packet_reads":0,"provider_ready":False,"scores_calls":0,"drain_calls":0}

    def _signal_bound(self):
        project, job, locked = self.project_id, self.algorithm_id, self.get_locked()
        if (self.live_mode is not False or type(project) is not int or project != self._config["project_id"]
                or type(job) is not str or re.fullmatch(r"[0-9a-f]{32}",job) is None or locked is not True
                or self._evidence._config_hash != EXPECTED_CONFIG_SHA256
                or self._evidence._config_raw != _wire(self._config)):
            _fail()
        prefix = self._evidence.require_binding()
        if type(prefix) is not str or not prefix.endswith("/"+str(project)+"/"+job+"/"):
            _fail()
        binding = (project,job,prefix)
        if self._signal_native_binding is None:
            self._signal_native_binding = binding
        elif self._signal_native_binding != binding:
            _fail()
        return prefix

    def _signal_effect(self, call):
        """Real runtime custody around each bounded private phase, even errors."""
        try:
            if self._signal_runtime_faulted:
                _fail()
            self._signal_bound()
            try:
                value = call()
            except BaseException as first:
                try:
                    self._signal_bound()
                except BaseException as second:
                    if isinstance(first,KeyboardInterrupt):raise first
                    if isinstance(second,KeyboardInterrupt):raise second
                    if not isinstance(first,Exception):raise first
                    if not isinstance(second,Exception):raise second
                raise
            self._signal_bound()
            return value
        except KeyboardInterrupt:
            self._signal_runtime_faulted = True
            raise KeyboardInterrupt("CMP28 signal operation cancelled") from None
        except Exception:
            self._signal_runtime_faulted = True
            raise ValueError("CMP28 signal runtime refused") from None
        except BaseException:
            self._signal_runtime_faulted = True
            raise SignalRuntimeStopped("CMP28 signal operation stopped") from None

    def _require_signal_provider(self):
        if self._signal_provider is not None:
            return self._signal_effect(lambda:self._signal_provider)
        def prepare():
            if self._signal_packet_attempted:
                _fail()
            self._signal_packet_attempted = True  # Before claim/read; no retry.
            self._signal_runtime["claim_attempts"] += 1
            prefix = self._signal_bound()
            packet = dict(self._config["signal_packet"])
            body = {"schema":"tpr-cmp28-native-signal-packet-access-v1","study_id":STUDY,
                "candidate_id":self._config["candidate_id"],"arm":self._config["arm"],
                "operation_id":self._config["operation_id"],"attempt":self._config["attempt"],
                "project_id":self.project_id,"job_id":self.algorithm_id,
                "parent_config_sha256":EXPECTED_CONFIG_SHA256,
                "source_template_closure_sha256":self._config["source_template_closure_sha256"],
                "policy_sha256":self._config["policy_sha256"],"calendar_sha256":self._config["calendar_sha256"],
                "prior_attempts_looks_sha256":self._config["prior_attempts_looks_sha256"],
                "signal_packet":packet,"maximum_packet_reads":1,"maximum_packet_bytes":packet["bytes"],
                "maximum_scores_calls":301,"spent_before_effect":True,
                "no_standalone_outcome_permission":True,"backend_durability_proven":False}
            raw = _wire(body)
            if not 0 < len(raw) <= 4096:
                _fail()
            key = prefix+"signal-packet-access.json"
            digest = hashlib.sha256(raw).hexdigest()
            self._signal_runtime.update(claim_key=key,claim_sha256=digest,claim_bytes=len(raw))
            exists = self._signal_effect(lambda:self.object_store.contains_key(key))
            if type(exists) is not bool or exists:
                _fail()
            if self._signal_effect(lambda:self.object_store.save_bytes(key,raw)) is not True:
                _fail()
            observed = self._signal_effect(lambda:native_bytes(self.object_store.read_bytes(key),len(raw)))
            if observed != raw or len(observed) != len(raw) or hashlib.sha256(observed).hexdigest() != digest:
                _fail()
            # Local readback can be cache-backed; root external manifest is the
            # durable authority. This is only verified same-node publication.
            self._signal_runtime["claim_same_node_verified"] = True
            self._signal_runtime["packet_reads"] += 1
            observed = self._signal_effect(lambda:self.object_store.read_bytes(packet["key"]))
            packet_raw = self._signal_effect(lambda:native_bytes(observed,packet["bytes"]))
            del observed  # Release the native byte-array wrapper before parsing.
            if len(packet_raw) != packet["bytes"] or self._signal_effect(lambda:hashlib.sha256(packet_raw).hexdigest()) != packet["sha256"]:
                _fail()
            provider = self._signal_effect(lambda:signal_native.prepare_native_signals(packet_raw,
                expected_sha256=packet["sha256"],expected_bytes=packet["bytes"],sessions=session_axis(),
                expected_source_inventory_sha256=packet["source_inventory_sha256"]))
            if provider is None:
                _fail()
            return provider
        provider = self._signal_effect(prepare)
        self._signal_provider = provider
        self._signal_runtime["provider_ready"] = True
        return provider

    def _signal_runtime_summary(self):
        return {**self._signal_runtime,"faulted":self._signal_runtime_faulted,
            "packet_scope_spent":self._signal_packet_attempted,
            "actual_job_bound":self._signal_native_binding is not None}

    def _capture_caps(self, values):
        if self._config["arm"] != "pure_tpr":
            return super()._capture_caps(values)
        rows = list(values)
        if not 1 <= len(rows) <= 20000:
            _fail()
        configs = list(self.subscription_manager.subscription_data_config_service.get_subscription_data_configs(self._cap_context_symbol, True))
        if (not configs or any(config.symbol != self._cap_context_symbol or config.is_internal_feed is not True
                or config.resolution != Resolution.DAILY or config.exchange_time_zone.id != "America/New_York"
                or config.type.FullName != "QuantConnect.Data.Fundamental.FundamentalUniverse" for config in configs)):
            _fail()
        now = self._native_clock(self.utc_time, "UTC")
        asof, effective = self._native_clock(rows[0].time, "America/New_York"), self._native_clock(rows[0].end_time, "America/New_York")
        if not asof <= effective <= now:
            _fail()
        wanted = {str(row["symbol"].id) for snapshot in self._snapshots["XLF"] for row in snapshot["members"]}
        classifications = {}
        for row in rows:
            if not isinstance(row, Fundamental):
                _fail()
            sid = str(row.symbol.id)
            if sid not in wanted:
                continue
            if sid in classifications or self._native_clock(row.time,"America/New_York") != asof or self._native_clock(row.end_time,"America/New_York") != effective:
                _fail()
            classifications[sid] = self._classify_insurance(row)
        self._cap_callback_count += 1
        self._cap_snapshots.append({"effective": effective, "asof": asof, "received": now, "insurance": classifications})
        self._cap_snapshots = [row for row in self._cap_snapshots if now-row["effective"] <= timedelta(days=45)]
        return []

    def _prepare_targets(self, day):
        cutoff = core._clock(core.CUTOFF_BY_DAY[day])
        arm = self._config["arm"]
        if cutoff >= self._native_clock(self.utc_time,"UTC") or arm not in CANDIDATES:
            _fail()
        snapshots = {sleeve:core.select_snapshot(self._snapshots[sleeve],cutoff) for sleeve in SLEEVES}
        self._membership_coverage_by_day[day] = {sleeve:{"available":row is not None,
            "member_count":len(row["members"]) if row is not None else None} for sleeve,row in snapshots.items()}
        if any(row is None for row in snapshots.values()):
            self._decision_coverage[day]=None; self._reason("missing_lagged_native_universe"); return
        members, symbols, reports = {}, {}, {}
        for sleeve,snapshot in snapshots.items():
            members[sleeve]=[{"sid":str(row["symbol"].id),"ticker":row["ticker"]} for row in snapshot["members"]]
            symbols.update({str(row["symbol"].id):row["symbol"] for row in snapshot["members"]})
            reports[sleeve]={"member_count":len(snapshot["members"]),"membership_weights_used":False,
                "native_member_coverage":dict(snapshot["native_member_coverage"]),"effective_utc":snapshot["effective"].isoformat(),
                "received_utc":snapshot["received"].isoformat()}
            self._log_audit("MEMBERSHIP",{"session":day,"sleeve":sleeve,**reports[sleeve],"members":members[sleeve]})
        snapshot = self._select_caps(cutoff)
        finance = {row["sid"]:snapshot["insurance"].get(row["sid"]) if snapshot is not None else None for row in members["XLF"]}
        if any(value not in ("insurance","noninsurance") for value in finance.values()):
            self._decision_coverage[day]=None; self._reason("unknown_asof_finance_classification"); return
        if arm == "pure_tpr":
            self._cap_snapshot_coverage_by_day[day] = None  # Caps are not an input to this arm.
            requested = dict(symbols)
            current_caps = None
        else:
            self._cap_snapshot_coverage_by_day[day] = snapshot is not None
            if snapshot is None:
                self._decision_coverage[day]=None; self._reason("missing_prior_cap_snapshot"); return
            source_caps = snapshot["caps"]
            if type(source_caps) is not dict:
                _fail()
            current_caps={sid:source_caps.get(sid,{"state":"missing","value":None}) for sid in sorted(symbols)}
            baseline,_ = comparison.construct_off(members,current_caps,finance_insurance_by_sid=finance,
                warning_ids=self._warning_ids,final_ids=self._delisted_ids)
            requested={sid:symbols[sid] for sid in baseline}
        provider = self._require_signal_provider()
        if self._signal_runtime["scores_calls"] >= 301:
            self._signal_effect(_fail)
        self._signal_runtime["scores_calls"] += 1
        signal = self._signal_effect(lambda:provider.scores_for(day,cutoff.isoformat(),requested))
        if type(signal) is not dict or type(signal.get("scores_by_sid")) is not dict or set(signal["scores_by_sid"]) != set(requested):
            _fail()
        scores=signal["scores_by_sid"]
        # Event-date native binding metadata is PRIVATE evidence. Drain bounded
        # batches so the provider does not retain the whole run's observations.
        receipts = 0
        for part in range((386000+199)//200+1):
            self._signal_runtime["drain_calls"] += 1
            rows = self._signal_effect(lambda:provider.drain_private_binding_receipts(maximum=200))
            if type(rows) is not list or len(rows)>200 or any(type(row) is not dict for row in rows):
                _fail()
            if not rows:
                break
            receipts += len(rows)
            if receipts>386000:
                _fail()
            self._log_audit("COVERAGE",{"kind":"native_binding_receipts","session":day,"part":part,
                "receipts":rows,"source_inputs_admitted":False,"historical_identity_proven":False})
        else:
            _fail()
        if arm == "pure_tpr":
            weights,detail=self._signal_effect(lambda:comparison.construct_pure_tpr(members,scores,
                finance_insurance_by_sid=finance,warning_ids=self._warning_ids,final_ids=self._delisted_ids))
        else:
            weights,detail=self._signal_effect(lambda:comparison.construct_tilt(members,current_caps,scores,arm=arm,
                finance_insurance_by_sid=finance,warning_ids=self._warning_ids,final_ids=self._delisted_ids))
        # Complete private scores are retained in bounded parts, not one
        # potentially oversized whole-IWM record or a public log message.
        ordered = self._signal_effect(lambda:sorted(scores))
        parts = max(1, (len(ordered)+199)//200)
        score_hash = self._signal_effect(lambda:score_frame_sha256(scores))
        for part in range(parts):
            self._log_audit("COVERAGE",{"kind":"signal_frame","session":day,"part":part,"parts":parts,
                "requested_count":len(requested),"score_frame_sha256":score_hash,
                "scores_by_sid":{sid:scores[sid] for sid in ordered[part*200:(part+1)*200]},
                "signal_packet_sha256":self._config["signal_packet"]["sha256"],"source_inputs_admitted":False})
        self._log_audit("COVERAGE",{"kind":"signal_census","session":day,"requested_count":len(requested),
            "score_frame_sha256":score_hash,"census":signal.get("census"),"binding_census":signal.get("binding_census"),
            "signal_packet_sha256":self._config["signal_packet"]["sha256"],"source_inputs_admitted":False})
        if arm != "pure_tpr":
            self._log_audit("CAPS",{"session":day,"caps":current_caps,"finance_insurance":finance,
                "effective_utc":snapshot["effective"].isoformat(),"asof_utc":snapshot["asof"].isoformat(),
                "received_utc":snapshot["received"].isoformat(),"native_source_units_accepted":False})
        for sleeve in SLEEVES:reports[sleeve].update(detail["per_sleeve"][sleeve])
        self._targets={sid:symbols[sid] for sid in weights};self._target_weights=weights
        self._symbols.update(self._targets);self._ever_targeted_ids.update(weights)
        self._decision_coverage[day]={"session":day,"arm":arm,"sleeves":reports,"construction":detail,
            "target_gross":core._text(detail["target_gross_weight"]),"unallocated_target_cash":core._text(detail["cash_weight"]),
            "caps_used":arm!="pure_tpr","signal_packet_sha256":self._config["signal_packet"]["sha256"],
            "signal_requested_count":len(requested),"signal_scores_sha256":score_frame_sha256(scores),"source_inputs_admitted":False}

    def _rebalance(self):
        self._evidence.require_binding()
        day = self.time.date().isoformat()
        if self.is_warming_up or day not in DECISIONS or day in self._attempted_days:
            return
        self._attempted_days.add(day)
        self._decision_count += 1
        if self.time.time() != time(9, 20):
            self._refused_count += 1
            self._reason("late_decision_clock")
            return
        self._assert_clock_subscription()
        self._prepare_targets(day)
        coverage = self._decision_coverage.get(day)
        if coverage is None:
            self._refused_count += 1
            return
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
        coverage["prior_mark_session"] = core._clock(core.CUTOFF_BY_DAY[day]).astimezone(NY).date().isoformat()
        coverage["prior_mark_sleeve_sha256"] = core.sleeve_mark_hashes(coverage, marks)
        self._log_audit("COVERAGE", coverage)
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
        orders = execution.plan_weighted_orders(positive_order_targets(self._target_weights), holdings, marks,
            self._prior_close_nav, cash, Fraction(core.SLIPPAGE),
            etf_arm=False)
        self._log_audit("ORDER", {"session": day, "planned": orders,
            "prior_nav": self._prior_close_nav, "settled_cash": cash,
            "marks": {sid: list(value) for sid, value in marks.items()},
            "zero_weight_selected_count": sum(value == 0 for value in self._target_weights.values())})
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
            ticket = self.market_on_open_order(self._symbols[sid], quantity, tag="TPRE:" + intent)
            self._tickets.append(ticket)
            self._log_audit("ORDER", {"session": day, "security_id": sid, "order_id": ticket.order_id,
                "requested": row["requested"], "submitted": quantity, "reason": row["reason"],
                "intent": intent, "utc": self._native_clock(self.utc_time, "UTC").isoformat()})
            self._submitted += 1
            self._submitted_shares += abs(quantity)


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
        summary = {"schema": "tpr-cmp28-multi-native-summary-v1", "study_id": STUDY, "candidate_id": self._config["candidate_id"],
            "arm": self._config["arm"], "operation_id": self._config["operation_id"], "attempt": self._config["attempt"],
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
            "signal_runtime_access":self._signal_runtime_summary(),
            "source_inputs_admitted": False,
            "native_basis_authenticated": False, "full_evidence_retrieval_verified": False,
            "strategy_accepted": False, "canonical_admission": False, "accepted_performance": None}
        self._log_audit("SUMMARY", summary)
        pointer = self._evidence.export(self.object_store)
        # Own-account aggregate and exact private index pointer only. Raw market,
        # cap/classification/member/factor rows never leave the private journal.
        self.log("CMP28_MULTI_SUMMARY " + core.exact_json(summary))
        self.log("CMP28_MULTI_EVIDENCE_INDEX " + json.dumps(pointer, sort_keys=True, separators=(",", ":")))
