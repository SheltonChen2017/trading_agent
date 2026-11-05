"""Pure native-parent cache diagnostic: the raw witness and SID stay in QC.

This fixed non-order input canary registers the exact historical SID during
the first locked preopen SPY callback, never during unlocked Initialize.
The future-dated failure witness selects a hindsight diagnostic identity only;
it supplies no financial value and establishes no PIT or financial admission.
All caller code is rejected except the exact pinned public witness validator.
No filesystem, private read, provider, compile or job effect occurs here.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import io
import json
import re
import tokenize

from . import comparison_20261028_mark_read as reader
from . import native_cache_probe_20261104 as base

MODULE = "research/target_price_revisions_qc/native_cache_parent_probe_v5_20261104.py"
EPOCH = "TPR-NATIVE-PARENT-PREOPEN-CACHE-20261104-v5"
PROJECT_ID = base.PROJECT_ID
TARGET_SID_SHA256 = base.TARGET_SID_SHA256
SESSIONS = base.SESSIONS
MAX_SOURCE_BYTES = 60000
HELPER_SHA256 = "6539ae749aefb4884ed52258fc2f0f77c9481a5e8ee37ea80ec7065218f0da95"
BASE_SHA256 = "481602457ae78568b3b708cbefd0315d7115baf95a8bd27536983e8bbfec7a86"
BASE_RUNTIME_SHA256 = "4ff09e1079905afb08ee8d9a42e0bfc27a72ff0f878efbc9d591e865b661eb10"
PARENT_CONFIG_SHA256 = "8292239f62e01d20a221fe49f76b3c29a23e9089eed3d6468f0a0953cbbb02b3"
PARENT_KEY_SHA256 = "7a27356ccf09e0674b56dac39adaad4d1a0ef7a2cee7ef7f948982f20004e13f"
PARENT_WITNESS_SHA256 = "eef08aca32b99056dee0ce00389c53a8ee6a1628c29188afd8bebd362fe183dd"
PARENT_BYTES = 1343
REQUIRED_SOURCES = frozenset((MODULE, base.MODULE, reader.MODULE))
PINNED = {base.MODULE: BASE_SHA256, reader.MODULE: HELPER_SHA256}
FLAGS = base.FLAGS + ("sdk_hard_timeout_proven", "sdk_preallocation_byte_bound_proven",
    "parent_read_source_origin_proven", "provider_wide_absence_proven", "benchmark_origin_proven")
CONTROL_POLICY = "fixed_spy_control_configs_v5"
STAGES = ("initialize_configuration", "initialize_custody", "initialize_control", "initialize_schedule",
    "initialize_ready", "on_data_entry", "on_data_entry_budget", "waiting_custody", "waiting_clock",
    "waiting_slice", "waiting_control", "waiting_empty_slice", "bootstrap_dispatch", "preopen_custody",
    "preopen_clock_slice", "preopen_control", "preopen_bar", "preopen_configs", "preopen_endpoint",
    "parent_contains", "parent_read", "parent_validation", "parent_decode", "parent_identity_hash",
    "parent_native_identity", "target_registration", "registration_custody", "registration_control_configs",
    "registration_target_configs", "registration_endpoint", "bootstrap_complete", "data_delivery",
    "close_without_bootstrap", "close_snapshot", "end_custody", "end_without_bootstrap", "end_coverage")
BOUND_CODES = ("custody_algorithm", "custody_live_mode", "custody_warming_up", "custody_current_slice",
    "custody_project_type", "custody_project_id", "custody_locked", "custody_job_type",
    "custody_job_format", "custody_job_changed")
CONFIG_SPLITS = {
    "registered security unproved": ("cfg_sec_count", "cfg_sec_type", "cfg_sec_symbol", "cfg_sec_ref"),
    "configuration fields unproved": ("cfg_row_type", "cfg_row_symbol", "cfg_resolution", "cfg_fill_forward",
        "cfg_normalization", "cfg_extended", "cfg_internal", "cfg_custom", "cfg_exchange_tz", "cfg_data_tz"),
    "trade configuration unproved": ("cfg_trade_count", "cfg_quote_count")}
CONFIG_RAISES = {"configuration count unproved": ("cfg_no_rows", "cfg_extra_rows"),
    "configuration type unproved": "cfg_kind_tick"}
CONFIG_CODES = tuple(code for codes in CONFIG_SPLITS.values() for code in codes) + tuple(
    code for value in CONFIG_RAISES.values() for code in (value if type(value) is tuple else (value,)))
FAILURE_CODES = ("stage_failed", "entry_budget_exceeded", "bootstrap_incomplete",
    "inherited_data_unproved", "inherited_close_unproved", "coverage_incomplete", "invalid_stage") + BOUND_CODES + CONFIG_CODES
FAILURE_CATEGORIES = ("value_error", "type_error", "attribute_error", "key_error", "runtime_error",
    "overflow_error", "other_exception", "guard", "state", "budget", "inherited", "internal")
ON_DATA_ENTRY_MAX = 6400  # original400 bootstrap waits plus6000 delivered-slice budget


class ParentCacheRefusal(ValueError):
    """Body-free refusal: no source key, witness, or SID enters an exception."""


def _fail():
    raise ParentCacheRefusal("fixed native-parent cache diagnostic refused") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")


def _parse(raw):
    def pairs(items):
        value = {}
        for key, cell in items:
            if key in value:
                _fail()
            value[key] = cell
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_float=lambda _: _fail(),
            parse_constant=lambda _: _fail())
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail()


RUNTIME = r'''
class DiagnosticGuardRefusal(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in DIAGNOSTIC_CODES else "stage_failed"
        super().__init__("native-parent diagnostic guard refused")

def parent_bytes(value):
    expected = CONFIG["parent_binding"]["expected_bytes"]
    if type(value) in (bytes, bytearray):
        if len(value) != expected:
            raise ValueError("parent byte bound unproved")
    else:
        from System import Array, Byte
        if type(value) is not Array[Byte] or value.Length != expected:
            raise ValueError("parent byte type unproved")
    return bytes(value)

class Main(CacheProbeBase):
    def _stage(self, stage):
        if type(stage) is not str or stage not in DIAGNOSTIC_STAGES:
            raise ValueError("diagnostic stage unproved")
        self._report["current_stage"] = stage

    def _completed(self, stage):
        self._stage(stage)
        if self._report["first_failure_stage"] is None:
            self._report["last_completed_stage"] = stage

    def _failure(self, error=None, code=None, category=None):
        if self._report["first_failure_stage"] is not None:
            return
        if isinstance(error, DiagnosticGuardRefusal):
            code, category = error.code, "guard"
        if category is None:
            category = "other_exception"
            for kind, label in ((AttributeError, "attribute_error"), (TypeError, "type_error"),
                    (KeyError, "key_error"), (OverflowError, "overflow_error"),
                    (ValueError, "value_error"), (RuntimeError, "runtime_error")):
                if isinstance(error, kind):
                    category = label
                    break
        if code is None:
            code = "stage_failed"
        stage = self._report["current_stage"]
        if stage not in DIAGNOSTIC_STAGES:
            stage, code, category = "on_data_entry", "invalid_stage", "internal"
        self._report.update(first_failure_stage=stage,
            first_failure_code=code if code in DIAGNOSTIC_CODES else "stage_failed",
            first_failure_category=category if category in DIAGNOSTIC_CATEGORIES else "other_exception")

    def initialize(self):
        self._job, self._disabled, self._target_ready, self._bootstrap_attempted = None, False, False, False
        self._waiting_previous_now = None
        self._seen, self._slices, self._bars = set(), 0, 0
        self._report = {"schema": "tpr-native-parent-cache-observations-v5", "source_epoch": SOURCE_EPOCH,
            "operation_id": None, "root_head": None, "status": "setup_unproved", "sessions": {},
            "input_canary_only": True, "non_order_diagnostic_exception": True,
            "hindsight_identity_diagnostic_only": True, "initialize_private_effects": False,
            "external_native_read_manifest_required": True, "parent_contains_calls": 0,
            "parent_read_calls": 0, "object_store_calls": 0, "parent_bytes_expected": CONFIG_PARENT_BYTES,
            "parent_hash_verified": False, "parent_schema_verified": False, "parent_sid_hash_verified": False,
            "registration_before_open": False, "bootstrap_attempted": False, "direct_order_calls": 0, "history_calls": 0,
            "preopen_empty_slices": 0, "preopen_empty_slices_max": 400,
            "direct_provider_calls": 0, "cache_updates": 0, "subscription_removals": 0,
            "resource_cap_changes": 0, "cache_reads_per_check_max": 3, "config_reads_per_check_max": 3,
            "native_close_reads_per_check_max": 2, "current_stage": "initialize_configuration",
            "first_failure_stage": None, "first_failure_code": None, "first_failure_category": None,
            "last_completed_stage": None, "close_summary": "not_called", "terminal_summary": "not_called",
            "terminal_custody_passed": False, "on_data_entries": 0, "on_data_disabled_skips": 0,
            "control_config_policy": CONTROL_POLICY, "control_config_rows_max": 3, "control_config_next_max": 4,
            "control_internal_hour_adjusted_max": 1, "target_config_rows_max": 2, "target_config_next_max": 3,
            "on_data_entry_max": ON_DATA_ENTRY_MAX, "on_data_entry_cap_reached": False,
            "on_data_disabled_skip_cap_reached": False, **{key: False for key in FALSE_FLAGS}}
        try:
            self._configuration()
            self._completed("initialize_configuration")
            self._stage("initialize_custody")
            if (self.live_mode is not False or type(self.project_id) is not int
                    or self.project_id != 38609822 or self.get_locked() is not False):
                raise ValueError("setup custody unproved")
            self._completed("initialize_custody")
            self._report.update(operation_id=CONFIG["operation_id"], root_head=CONFIG["git_head"])
            self._stage("initialize_control")
            self.set_time_zone("America/New_York")
            self.set_start_date(2021, 2, 8)
            self.set_end_date(2021, 2, 12)
            self.settings.daily_precise_end_time = True
            control = self.add_equity("SPY", Resolution.MINUTE, fill_forward=False,
                extended_market_hours=True, data_normalization_mode=DataNormalizationMode.RAW)
            if not isinstance(control, Security):
                raise ValueError("native control unproved")
            self._symbols, self._registered = {"control": control.symbol}, {"control": control}
            self._completed("initialize_control")
            self._stage("initialize_schedule")
            self.set_benchmark(control.symbol)
            self.schedule.on(self.date_rules.every_day(control.symbol), self.time_rules.at(16, 1), self._check_close)
            self._completed("initialize_schedule")
            self._report["status"] = "awaiting_first_locked_preopen_slice"
            self._completed("initialize_ready")
        except KeyboardInterrupt:
            raise KeyboardInterrupt("native-parent diagnostic cancelled") from None
        except Exception as error:
            self._failure(error)
            self._disabled = True
            self._report["status"] = "diagnostic_failed"

    def _configuration(self):
        if (hashlib.sha256(CONFIG_JSON.encode("ascii")).hexdigest() != CONFIG_SHA256
                or json.dumps(CONFIG, sort_keys=True, separators=(",", ":")) != CONFIG_JSON
                or hashlib.sha256(PARENT_HELPER_SOURCE.encode("utf-8")).hexdigest() != HELPER_SHA256
                or CONFIG["target_sid_sha256"] != EXPECTED_TARGET_SHA256
                or CONFIG["parent_binding"]["expected_bytes"] != CONFIG_PARENT_BYTES):
            raise ValueError("configuration unproved")

    def _snapshot_values(self, label, row):
        frame = CacheProbeBase._config_values(self, row)
        if label == "control":
            return frame + (row.resolution == Resolution.HOUR,
                row.data_normalization_mode == DataNormalizationMode.ADJUSTED)
        return frame

    def _configs(self, label, symbol, security):
        if label == "control":
            return self._control_configs(symbol, security, 2)
        return CacheProbeBase._configs(self, label, symbol, security)

    def _bootstrap_configs(self, label, symbol, security):
        if label != "control":
            raise DiagnosticGuardRefusal("cfg_sec_symbol")
        return self._control_configs(symbol, security, 1)

    def _control_configs(self, symbol, security, expected_securities):
        if len(self.securities) != expected_securities:
            raise DiagnosticGuardRefusal("cfg_sec_count")
        if not isinstance(security, Security):
            raise DiagnosticGuardRefusal("cfg_sec_type")
        if security.symbol != symbol or symbol != self._symbols["control"]:
            raise DiagnosticGuardRefusal("cfg_sec_symbol")
        if (not NetObject.ReferenceEquals(self.securities[symbol], security)
                or not NetObject.ReferenceEquals(self._registered["control"], security)):
            raise DiagnosticGuardRefusal("cfg_sec_ref")
        stream = self.subscription_manager.subscription_data_config_service.get_subscription_data_configs(symbol, True)
        rows, stop, cursor = [], object(), iter(stream)
        for index in range(4):
            row = next(cursor, stop)
            if row is stop:
                break
            if index == 3:
                raise DiagnosticGuardRefusal("cfg_extra_rows")
            rows.append(row)
        if not 1 <= len(rows) <= 3:
            raise DiagnosticGuardRefusal("cfg_no_rows" if not rows else "cfg_extra_rows")
        kinds, frames, internal = [], [], 0
        for row in rows:
            if not isinstance(row, SubscriptionDataConfig):
                raise DiagnosticGuardRefusal("cfg_row_type")
            if row.symbol != symbol:
                raise DiagnosticGuardRefusal("cfg_row_symbol")
            inside = row.is_internal_feed
            if inside is True:
                internal += 1
                if (internal > 1 or type(row.resolution) is not type(Resolution.HOUR)
                        or row.resolution != Resolution.HOUR or row.fill_data_forward is not False
                        or type(row.data_normalization_mode) is not type(DataNormalizationMode.ADJUSTED)
                        or row.data_normalization_mode != DataNormalizationMode.ADJUSTED
                        or row.extended_market_hours is not False or row.is_custom_data is not False
                        or row.exchange_time_zone.id != "America/New_York"
                        or row.data_time_zone.id != "America/New_York"
                        or row.type.FullName != "QuantConnect.Data.Market.TradeBar" or row.tick_type != TickType.TRADE):
                    raise DiagnosticGuardRefusal("cfg_internal")
            else:
                if row.resolution != Resolution.MINUTE:
                    raise DiagnosticGuardRefusal("cfg_resolution")
                if row.fill_data_forward is not False:
                    raise DiagnosticGuardRefusal("cfg_fill_forward")
                if row.data_normalization_mode != DataNormalizationMode.RAW:
                    raise DiagnosticGuardRefusal("cfg_normalization")
                if row.extended_market_hours is not True:
                    raise DiagnosticGuardRefusal("cfg_extended")
                if inside is not False:
                    raise DiagnosticGuardRefusal("cfg_internal")
                if row.is_custom_data is not False:
                    raise DiagnosticGuardRefusal("cfg_custom")
                if row.exchange_time_zone.id != "America/New_York":
                    raise DiagnosticGuardRefusal("cfg_exchange_tz")
                if row.data_time_zone.id != "America/New_York":
                    raise DiagnosticGuardRefusal("cfg_data_tz")
                kind = row.type.FullName
                if kind == "QuantConnect.Data.Market.TradeBar" and row.tick_type == TickType.TRADE:
                    kinds.append("trade")
                elif kind == "QuantConnect.Data.Market.QuoteBar" and row.tick_type == TickType.QUOTE:
                    kinds.append("quote")
                else:
                    raise DiagnosticGuardRefusal("cfg_kind_tick")
            frames.append(self._snapshot_values("control", row))
        if not 1 <= len(kinds) <= 2:
            raise DiagnosticGuardRefusal("cfg_no_rows" if not kinds else "cfg_extra_rows")
        if kinds.count("trade") != 1:
            raise DiagnosticGuardRefusal("cfg_trade_count")
        if kinds.count("quote") > 1:
            raise DiagnosticGuardRefusal("cfg_quote_count")
        return rows, tuple(frames)

    def _preopen(self, data, expected_now=None, expected_slice=None, expected_control=None):
        self._stage("preopen_custody")
        self._bound()
        self._completed("preopen_custody")
        self._stage("preopen_clock_slice")
        now, local = clock(self.utc_time, "UTC"), clock(self.time, "America/New_York")
        ny = local.astimezone(ZoneInfo("America/New_York"))
        if (now != local or ny.date().isoformat() != "2021-02-08" or not time(4) <= ny.time() < time(9, 30)
                or not isinstance(data, Slice) or not NetObject.ReferenceEquals(data, self.current_slice)
                or expected_now is not None and now != expected_now
                or expected_slice is not None and not NetObject.ReferenceEquals(data, expected_slice)):
            raise ValueError("preopen native scope unproved")
        self._completed("preopen_clock_slice")
        self._stage("preopen_control")
        control = self._registered["control"]
        if (len(self.securities) != 1 or not NetObject.ReferenceEquals(self.securities[control.symbol], control)
                or expected_control is not None and not NetObject.ReferenceEquals(control, expected_control)
                or not 0 < len(data.bars) <= 1 or control.symbol not in data.bars):
            raise ValueError("preopen native control unproved")
        self._completed("preopen_control")
        self._stage("preopen_bar")
        bar = data.bars[control.symbol]
        if not isinstance(bar, TradeBar):
            raise ValueError("preopen trade clock unproved")
        values = self._cache_values(bar)
        began, ended = values[5:7]
        if (values[2] != str(control.symbol.id) or values[3] is not False
                or values[4] != timedelta(minutes=1) or ended-began != timedelta(minutes=1)
                or began.astimezone(ZoneInfo("America/New_York")).date().isoformat() != "2021-02-08"
                or not time(4) <= began.astimezone(ZoneInfo("America/New_York")).time() < time(9, 30)
                or ended > now or (now-ended) > timedelta(minutes=1)):
            raise ValueError("preopen native bar unproved")
        self._completed("preopen_bar")
        self._stage("preopen_configs")
        configs = self._bootstrap_configs("control", control.symbol, control)
        self._completed("preopen_configs")
        # The config service is a native boundary. Recheck its endpoint before
        # any ObjectStore call, rather than returning the earlier clock/bar.
        self._stage("preopen_endpoint")
        self._bound()
        if (clock(self.utc_time, "UTC") != now or clock(self.time, "America/New_York") != now
                or not NetObject.ReferenceEquals(data, self.current_slice) or len(self.securities) != 1
                or not NetObject.ReferenceEquals(self.securities[control.symbol], control)
                or control.symbol not in data.bars or not NetObject.ReferenceEquals(data.bars[control.symbol], bar)
                or self._cache_values(bar) != values
                or configs[1] != tuple(self._snapshot_values("control", row) for row in configs[0])):
            raise ValueError("preopen configuration endpoint changed")
        self._completed("preopen_endpoint")
        return now, data, control, values, configs, bar

    def _same_preopen(self, data, prior):
        current = self._preopen(data, prior[0], prior[1], prior[2])
        if (prior[3] != current[3] or not NetObject.ReferenceEquals(prior[5], current[5])
                or prior[4][1] != current[4][1]
                or len(prior[4][0]) != len(current[4][0]) or not all(
                    NetObject.ReferenceEquals(a, b) for a, b in zip(prior[4][0], current[4][0]))):
            raise ValueError("preopen scope changed")
        return current

    def _bootstrap(self, data):
        prior = self._preopen(data)
        self._stage("parent_contains")
        self._report["parent_contains_calls"] += 1
        self._report["object_store_calls"] += 1
        present = self.object_store.contains_key(CONFIG["parent_binding"]["key"])
        self._same_preopen(data, prior)
        if type(present) is not bool or present is not True:
            self._stage("parent_contains")
            raise ValueError("parent existence unproved")
        self._completed("parent_contains")
        self._stage("parent_read")
        self._report["parent_read_calls"] += 1
        self._report["object_store_calls"] += 1
        raw = parent_bytes(self.object_store.read_bytes(CONFIG["parent_binding"]["key"]))
        self._same_preopen(data, prior)
        if hashlib.sha256(raw).hexdigest() != CONFIG["parent_binding"]["expected_sha256"]:
            self._stage("parent_read")
            raise ValueError("parent hash unproved")
        self._report["parent_hash_verified"] = True
        self._completed("parent_read")
        self._stage("parent_validation")
        safe = PARENT_VALIDATOR["project_witness_v2"](raw, binding=CONFIG["parent_binding"], pointer=CONFIG["parent_pointer"])
        self._same_preopen(data, prior)
        self._report["parent_schema_verified"] = True
        self._completed("parent_validation")
        self._stage("parent_decode")
        body = PARENT_VALIDATOR["_parse"](raw)
        sid_text = body["security_id"]
        self._completed("parent_decode")
        self._stage("parent_identity_hash")
        if (safe["security_id_sha256"] != EXPECTED_TARGET_SHA256 or type(sid_text) is not str
                or not sid_text.isascii() or re.fullmatch(r"[^\s|]{1,64} [A-Z0-9]{1,13}", sid_text) is None
                or int(sid_text.split(" ")[1], 36) >= 2**64
                or hashlib.sha256(sid_text.encode("ascii")).hexdigest() != EXPECTED_TARGET_SHA256):
            raise ValueError("parent identity hash unproved")
        self._completed("parent_identity_hash")
        self._stage("parent_native_identity")
        parsed = SecurityIdentifier.parse(sid_text)
        symbol = Symbol(parsed, parsed.symbol)
        if (not isinstance(parsed, SecurityIdentifier) or not isinstance(symbol, Symbol)
                or parsed.security_type != SecurityType.EQUITY or parsed.market != Market.USA
                or str(parsed) != sid_text or str(symbol.id) != sid_text):
            raise ValueError("native parent identity unproved")
        self._completed("parent_native_identity")
        self._same_preopen(data, prior)
        self._report["parent_sid_hash_verified"] = True
        self._stage("target_registration")
        target = self.add_security(symbol, resolution=Resolution.MINUTE, fill_forward=False,
            extended_market_hours=False, data_normalization_mode=DataNormalizationMode.RAW)
        self._stage("registration_custody")
        self._bound()
        if (not isinstance(target, Security) or target.symbol != symbol or symbol == prior[2].symbol
                or clock(self.utc_time, "UTC") != prior[0] or clock(self.time, "America/New_York") != prior[0]
                or not NetObject.ReferenceEquals(data, self.current_slice)):
            raise ValueError("native registration scope changed")
        self._completed("registration_custody")
        self._symbols["target"], self._registered["target"] = symbol, target
        self._stage("registration_control_configs")
        control_after = self._configs("control", prior[2].symbol, prior[2])
        self._completed("registration_control_configs")
        self._stage("registration_target_configs")
        target_after = self._configs("target", symbol, target)
        self._completed("registration_target_configs")
        self._stage("registration_endpoint")
        self._bound()
        if (clock(self.utc_time, "UTC") != prior[0] or clock(self.time, "America/New_York") != prior[0]
                or not NetObject.ReferenceEquals(data, self.current_slice) or len(self.securities) != 2
                or not NetObject.ReferenceEquals(self.securities[prior[2].symbol], prior[2])
                or not NetObject.ReferenceEquals(self.securities[symbol], target)
                or control_after[1] != tuple(self._snapshot_values("control", row) for row in control_after[0])
                or target_after[1] != tuple(self._snapshot_values("target", row) for row in target_after[0])):
            raise ValueError("registration configuration endpoint changed")
        if (prior[4][1] != control_after[1] or len(prior[4][0]) != len(control_after[0])
                or not all(NetObject.ReferenceEquals(a, b) for a, b in zip(prior[4][0], control_after[0]))
                or prior[2].symbol not in data.bars or not NetObject.ReferenceEquals(prior[5], data.bars[prior[2].symbol])
                or self._cache_values(data.bars[prior[2].symbol]) != prior[3]):
            raise ValueError("control registration changed")
        self._target_ready = True
        self._report.update(registration_before_open=True, status="awaiting_fixed_close_checks")
        self._completed("bootstrap_complete")
        del raw, body, sid_text

    def on_data(self, data):
        self._stage("on_data_entry")
        if self._report["on_data_entries"] < ON_DATA_ENTRY_MAX:
            self._report["on_data_entries"] += 1
        else:
            self._report["on_data_entry_cap_reached"] = True
            self._stage("on_data_entry_budget")
            self._failure(code="entry_budget_exceeded", category="budget")
            self._disabled = True
            self._report["status"] = "diagnostic_failed"
        if self._disabled:
            if self._report["on_data_disabled_skips"] < ON_DATA_ENTRY_MAX:
                self._report["on_data_disabled_skips"] += 1
            else:
                self._report["on_data_disabled_skip_cap_reached"] = True
            return
        try:
            if not self._target_ready:
                self._stage("waiting_custody")
                self._bound()
                self._completed("waiting_custody")
                self._stage("waiting_clock")
                now, local = clock(self.utc_time, "UTC"), clock(self.time, "America/New_York")
                ny = local.astimezone(ZoneInfo("America/New_York"))
                if (now != local or ny.date().isoformat() != "2021-02-08" or not time() <= ny.time() < time(9, 30)
                        or self._waiting_previous_now is not None and now < self._waiting_previous_now):
                    raise ValueError("preopen waiting scope unproved")
                self._completed("waiting_clock")
                self._stage("waiting_slice")
                if (not isinstance(data, Slice) or not NetObject.ReferenceEquals(data, self.current_slice)
                        or not 0 <= len(data.bars) <= 1):
                    raise ValueError("preopen waiting scope unproved")
                self._completed("waiting_slice")
                self._waiting_previous_now = now
                self._stage("waiting_control")
                control = self._registered["control"].symbol
                if control not in data.bars:
                    if len(data.bars) != 0:
                        raise ValueError("foreign preopen trade unproved")
                    self._report["preopen_empty_slices"] += 1
                    if self._report["preopen_empty_slices"] > 400:
                        raise ValueError("preopen waiting bound")
                    self._completed("waiting_empty_slice")
                    return
                if self._bootstrap_attempted:
                    raise ValueError("parent bootstrap already spent")
                self._bootstrap_attempted = True
                self._report["bootstrap_attempted"] = True
                self._stage("bootstrap_dispatch")
                self._bootstrap(data)
            self._stage("data_delivery")
            CacheProbeBase.on_data(self, data)
            if self._disabled:
                self._failure(code="inherited_data_unproved", category="inherited")
                self._report["status"] = "diagnostic_failed"
            else:
                self._completed("data_delivery")
        except KeyboardInterrupt:
            raise KeyboardInterrupt("native-parent diagnostic cancelled") from None
        except Exception as error:
            self._failure(error)
            self._disabled = True
            self._report["status"] = "diagnostic_failed"

    def _ok(self):
        return all(c["status"] == "bounded_cache_observation" for r in self._report["sessions"].values()
            for c in (r["target"], r["control"]))

    def _check_close(self):
        if not self._target_ready:
            self._stage("close_without_bootstrap")
            self._failure(code="bootstrap_incomplete", category="state")
            self._disabled = True
            self._report.update(status="diagnostic_failed", close_summary="bootstrap_unproved")
            return
        if self._disabled:
            if self._report["close_summary"] != "snapshot_unproved":
                self._report["close_summary"] = "skipped_disabled"
            return
        self._stage("close_snapshot")
        CacheProbeBase._check_close(self)
        if self._disabled:
            self._failure(code="inherited_close_unproved", category="inherited")
            self._report.update(status="diagnostic_failed", close_summary="snapshot_unproved")
        else:
            self._completed("close_snapshot")
            self._report["close_summary"] = "bounded_snapshot_recorded" if self._ok() else "snapshot_unproved"

    def on_end_of_algorithm(self):
        try:
            self._stage("end_custody")
            self._bound()
            self._report.update(actual_job_id=self._job, terminal_custody_passed=True)
            self._completed("end_custody")
            complete = (not self._disabled and set(self._report["sessions"]) == set(CONFIG["sessions"])
                and self._ok())
            if not self._target_ready:
                self._stage("end_without_bootstrap")
                self._failure(code="bootstrap_incomplete", category="state")
            elif not complete and self._report["first_failure_stage"] is None:
                self._stage("end_coverage")
                self._failure(code="coverage_incomplete", category="state")
            self._report["terminal_summary"] = "complete_cache_observations" if complete else "incomplete_cache_observations"
        except KeyboardInterrupt:
            raise KeyboardInterrupt("native-parent diagnostic cancelled") from None
        except Exception as error:
            self._failure(error)
            self._report["terminal_summary"] = "end_custody_unproved"
        self._report["status"] = ("diagnostic_failed" if self._report["first_failure_stage"] is not None
            else self._report["terminal_summary"])
        self._report.update(close_checks=len(self._report["sessions"]), delivered_slices=self._slices,
            delivered_bar_rows=self._bars, target_close_canary_days=sum(
                row["target"]["freshness_canary"] is True for row in self._report["sessions"].values()))
        wire = json.dumps(self._report, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(wire) <= 16384:
            self.log("TPR_PARENT_CACHE_PROBE_RESULT " + wire)
'''


def _config_observability(node):
    """Instrument only fixed program raises in the SHA-pinned AST copy."""
    def message(body):
        if (len(body) == 1 and isinstance(body[0], ast.Raise) and isinstance(body[0].exc, ast.Call)
                and isinstance(body[0].exc.func, ast.Name) and body[0].exc.func.id == "ValueError"
                and len(body[0].exc.args) == 1 and isinstance(body[0].exc.args[0], ast.Constant)):
            return body[0].exc.args[0].value
        return None
    def refusal(code):
        return ast.Raise(exc=ast.Call(func=ast.Name(id="DiagnosticGuardRefusal", ctx=ast.Load()),
            args=[ast.Constant(code)], keywords=[]), cause=None)
    seen = []
    class Instrument(ast.NodeTransformer):
        def visit_If(self, item):
            text = message(item.body)
            if text in CONFIG_SPLITS:
                codes = CONFIG_SPLITS[text]
                if (item.orelse or not isinstance(item.test, ast.BoolOp) or not isinstance(item.test.op, ast.Or)
                        or len(item.test.values) != len(codes)):
                    _fail()
                seen.append(text)
                return [ast.If(test=copy.deepcopy(test), body=[refusal(code)], orelse=[])
                    for test, code in zip(item.test.values, codes)]
            return self.generic_visit(item)
        def visit_Raise(self, item):
            text = message([item])
            if text in CONFIG_RAISES:
                seen.append(text)
                code = CONFIG_RAISES[text]
                if type(code) is tuple:
                    # The original negative predicate is unchanged. Only its
                    # local Python list selects empty versus capped excess.
                    selected = ast.IfExp(test=ast.Compare(left=ast.Call(func=ast.Name(id="len", ctx=ast.Load()),
                        args=[ast.Name(id="rows", ctx=ast.Load())], keywords=[]), ops=[ast.Eq()],
                        comparators=[ast.Constant(0)]), body=ast.Constant(code[0]), orelse=ast.Constant(code[1]))
                    return ast.Raise(exc=ast.Call(func=ast.Name(id="DiagnosticGuardRefusal", ctx=ast.Load()),
                        args=[selected], keywords=[]), cause=None)
                return refusal(code)
            if text is not None:
                _fail()
            return item
    transformed = Instrument().visit(node)
    if sorted(seen) != sorted(tuple(CONFIG_SPLITS) + tuple(CONFIG_RAISES)):
        _fail()
    return transformed


def _base_source():
    if _sha(base.RUNTIME.encode("utf-8")) != BASE_RUNTIME_SHA256:
        _fail()
    tree = ast.parse(base.RUNTIME)
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Main")
    # Split only the pinned OR guard, preserving its lazy predicate order,
    # configuration/job reads and final assignment. No SDK predicate is added.
    bound = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "_bound")
    if (len(bound.body) != 4 or not isinstance(bound.body[2], ast.If)
            or not isinstance(bound.body[2].test, ast.BoolOp) or not isinstance(bound.body[2].test.op, ast.Or)
            or len(bound.body[2].test.values) != len(BOUND_CODES)):
        _fail()
    guards = [ast.If(test=copy.deepcopy(test), body=[ast.Raise(exc=ast.Call(
        func=ast.Name(id="DiagnosticGuardRefusal", ctx=ast.Load()), args=[ast.Constant(code)], keywords=[]),
        cause=None)], orelse=[]) for test, code in zip(bound.body[2].test.values, BOUND_CODES)]
    bound.body = bound.body[:2] + guards + bound.body[3:]
    configs = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "_configs")
    _config_observability(configs)
    # Route only the retained-value endpoint through a label-aware helper.
    # The target helper delegates to the original snapshot without SDK reads.
    observe = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "_observe")
    snapshots = [item for item in ast.walk(observe) if isinstance(item, ast.Call)
        and ast.unparse(item.func) == "self._config_values"]
    if len(snapshots) != 1 or ast.unparse(snapshots[0]) != "self._config_values(row)":
        _fail()
    snapshots[0].func.attr = "_snapshot_values"
    snapshots[0].args.insert(0, ast.Name(id="label", ctx=ast.Load()))
    bootstrap = copy.deepcopy(configs)
    bootstrap.name = "_bootstrap_configs"
    count = 0
    for item in ast.walk(bootstrap):
        if isinstance(item, ast.Compare) and ast.unparse(item.left) == "len(self.securities)":
            if ast.unparse(item) != "len(self.securities) != 2":
                _fail()
            item.comparators = [ast.Constant(1)]
            count += 1
    if count != 1:
        _fail()
    node.name = "CacheProbeBase"
    # Main defines its own terminal summary. This is the only newly pruned
    # base method; its unused body is omitted to retain the60000-byte API cap.
    own_main = next(n for n in ast.parse(RUNTIME).body if isinstance(n, ast.ClassDef) and n.name == "Main")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "on_end_of_algorithm" for n in own_main.body):
        _fail()
    node.body = [n for n in node.body if not isinstance(n, ast.FunctionDef)
        or n.name not in ("initialize", "_configuration", "on_end_of_algorithm")]
    node.body.append(bootstrap)
    result = ast.unparse(ast.fix_missing_locations(tree))
    return result.replace("TPR_CACHE_PROBE_RESULT ", "TPR_PARENT_CACHE_PROBE_RESULT ")


def _compact_indentation(source):
    """Shorten token-aware whitespace; preserve STRING tokens and every AST node."""
    if type(source) is not str:
        _fail()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        literal_types = {tokenize.STRING} | {getattr(tokenize, name, -1)
            for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END")}
        level, starts, protected = 0, {}, set()
        for token in tokens:
            if token.type in literal_types:
                protected.update(range(token.start[0]+1, token.end[0]+1))
            if token.type == tokenize.INDENT:
                level += 1
            elif token.type == tokenize.DEDENT:
                level -= 1
            elif token.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER):
                starts.setdefault(token.start[0], (token.start[1], level))
        lines = source.splitlines(keepends=True)
        for number, (column, depth) in starts.items():
            if number in protected:
                continue
            line = lines[number-1]
            prefix = line[:column]
            if prefix and not prefix.strip(" \t"):
                lines[number-1] = " "*depth + line[column:]
        compacted = "".join(line for number, line in enumerate(lines, 1)
            if number in protected or line.strip())
        # Commas delimit tokens already. Remove only their following same-line
        # whitespace, never text inside a STRING or across a physical newline.
        compact_tokens = list(tokenize.generate_tokens(io.StringIO(compacted).readline))
        lines, gaps = compacted.splitlines(keepends=True), {}
        for left, right in zip(compact_tokens, compact_tokens[1:]):
            if left.type == tokenize.OP and left.string == "," and left.end[0] == right.start[0]:
                number, start, end = left.end[0], left.end[1], right.start[1]
                if not lines[number-1][start:end].strip(" \t"):
                    gaps.setdefault(number, []).append((start, end))
        for number, values in gaps.items():
            for start, end in reversed(values):
                lines[number-1] = lines[number-1][:start] + lines[number-1][end:]
        compacted = "".join(lines)
        before = [token.string for token in tokens if token.type in literal_types]
        after = [token.string for token in tokenize.generate_tokens(io.StringIO(compacted).readline)
            if token.type in literal_types]
        if (before != after or ast.dump(ast.parse(source), include_attributes=False)
                != ast.dump(ast.parse(compacted), include_attributes=False)):
            _fail()
        return compacted
    except (SyntaxError, IndentationError, tokenize.TokenError, TypeError, IndexError):
        _fail()


def _render(parent, helper_source, operation_id, git_head, target_sha):
    if (type(helper_source) is not bytes or _sha(helper_source) != HELPER_SHA256
            or type(operation_id) is not str or re.fullmatch(r"TPR-CACHE-20261104-[A-Z0-9-]{1,40}", operation_id) is None
            or type(git_head) is not str or re.fullmatch("[a-f0-9]{40}", git_head) is None or git_head == "0"*40):
        _fail()
    binding = reader._binding_v2(parent["binding"])
    reader.validate_pointer_v2(parent["pointer"], binding=binding)
    config = {"schema": "tpr-native-parent-cache-config-v5", "source_epoch": EPOCH, "operation_id": operation_id,
        "git_head": git_head, "project_id": PROJECT_ID, "target_sid_sha256": target_sha,
        "parent_binding": binding, "parent_pointer": parent["pointer"], "sessions": list(SESSIONS),
        "control_config_policy": CONTROL_POLICY}
    raw = _wire(config)
    prefix = ("SOURCE_EPOCH = "+repr(EPOCH)+"\nCONFIG_JSON = "+repr(raw.decode("ascii"))
        +"\nCONFIG_SHA256 = "+repr(_sha(raw))+"\nCONFIG = __import__('json').loads(CONFIG_JSON)"
        +"\nFALSE_FLAGS = "+repr(FLAGS)+"\nDIAGNOSTIC_STAGES = "+repr(STAGES)
        +"\nDIAGNOSTIC_CODES = "+repr(FAILURE_CODES)+"\nDIAGNOSTIC_CATEGORIES = "+repr(FAILURE_CATEGORIES)
        +"\nON_DATA_ENTRY_MAX = "+repr(ON_DATA_ENTRY_MAX)+"\nHELPER_SHA256 = "+repr(HELPER_SHA256)
        +"\nCONTROL_POLICY = "+repr(CONTROL_POLICY)
        +"\nPARENT_HELPER_SOURCE = "+repr(helper_source.decode("utf-8"))
        +"\nEXPECTED_TARGET_SHA256 = "+repr(target_sha)+"\nCONFIG_PARENT_BYTES = "+repr(binding["expected_bytes"])
        +"\nPARENT_VALIDATOR = {'__name__':'_tpr_fixed_parent_validator'}\n"
        +"import hashlib as _parent_source_hash\n"
        +"if _parent_source_hash.sha256(PARENT_HELPER_SOURCE.encode('utf-8')).hexdigest() != HELPER_SHA256: raise ValueError('fixed parent helper refused')\n"
        +"exec(compile(PARENT_HELPER_SOURCE, '<fixed_parent_validator>', 'exec'), PARENT_VALIDATOR)\n")
    # Formatting removes no AST node; it avoids spending the fixed payload
    # budget on comments/indentation in the newly instrumented runtime.
    runtime_tree = ast.parse(RUNTIME)
    runtime = ast.unparse(runtime_tree)
    if ast.dump(ast.parse(runtime), include_attributes=False) != ast.dump(runtime_tree, include_attributes=False):
        _fail()
    source = _compact_indentation(prefix+_base_source()+"\n"+runtime).encode("utf-8")
    if not 0 < len(source) <= MAX_SOURCE_BYTES:
        _fail()
    compile(ast.parse(source), "main.py", "exec")
    report = {"schema": "tpr-native-parent-cache-build-v5", "source_epoch": EPOCH, "project_id": PROJECT_ID,
        "operation_id": operation_id, "git_head": git_head, "main_bytes": len(source), "main_sha256": _sha(source),
        "config_sha256": _sha(raw), "helper_sha256": HELPER_SHA256, "base_sha256": BASE_SHA256,
        "sessions": list(SESSIONS), "local_raw_sid_supplied": False, "raw_witness_export_authorized": False,
        "initialize_private_effects": False, "parent_contains_max": 1, "parent_reads_max": 1,
        "preopen_empty_slices_max": 400, "empty_slice_wait_window_ny": "00:00..09:30 exclusive; private reads only04:00..09:30 exclusive",
        "parent_bytes_expected": binding["expected_bytes"], "max_securities": 2,
        "on_data_entry_max": ON_DATA_ENTRY_MAX, "first_failure_observability": True,
        "control_config_policy": CONTROL_POLICY, "control_config_rows_max": 3, "control_config_next_max": 4,
        "control_internal_hour_adjusted_max": 1, "target_config_rows_max": 2, "target_config_next_max": 3,
        "indentation_ast_equivalent": True,
        "input_canary_only": True, "hindsight_identity_diagnostic_only": True,
        "diagnostic_exception": "non_order_native_parent_cache_freshness_only",
        "native_requests_dispatched": 0, **{key: False for key in FLAGS}}
    return source, _wire(report)+b"\n"


def build_cache_probe(*, parent_probe_config_json, helper_source, operation_id, git_head):
    """Pure exact-source configuration input; never accepts a raw SID or body."""
    try:
        if (type(parent_probe_config_json) is not str or not parent_probe_config_json.isascii()
                or not 0 < len(parent_probe_config_json) <= 65536
                or _sha(parent_probe_config_json.encode("ascii")) != PARENT_CONFIG_SHA256):
            _fail()
        parent = _parse(parent_probe_config_json)
        binding = reader._binding_v2(parent["binding"])
        if (binding["project_id"] != 37650980 or binding["job_id"] != "12dd4732ba5d9d8f57950beb2a371c79"
                or type(binding["attempt"]) is not int or binding["attempt"] != 4
                or binding["expected_bytes"] != PARENT_BYTES or binding["expected_sha256"] != PARENT_WITNESS_SHA256
                or _sha(binding["key"].encode("ascii")) != PARENT_KEY_SHA256
                or binding["source_hashes"][reader.MODULE] != HELPER_SHA256):
            _fail()
        return _render(parent, helper_source, operation_id, git_head, TARGET_SID_SHA256)
    except (ValueError, TypeError, KeyError, UnicodeError, SyntaxError, StopIteration):
        _fail()


def _fixture_parent(case="valid"):
    """Synthetic cases only; no production override flag or private argument."""
    if case not in ("valid", "wrong_schema", "wrong_sid", "wrong_clock"):
        _fail()
    args = dict(operation_id="TPR-CMP28-MARK-SYNTHETIC", git_head="a"*40,
        source_hashes={reader.MODULE: HELPER_SHA256, reader.PRODUCER: "b"*64},
        off_operation_id="TPR-CMP28-OFF-SYNTHETIC", attempt=4, job_id="c"*32,
        config_sha256="d"*64, source_template_closure_sha256="e"*64,
        policy_sha256="f"*64, calendar_sha256="1"*64, expected_sha256="2"*64, expected_bytes=1)
    binding = reader.prepare_binding_v2(**args)
    body = {key: binding[key] for key in ("study_id", "candidate_id", "arm", "attempt", "project_id", "job_id",
        "config_sha256", "source_template_closure_sha256", "policy_sha256", "calendar_sha256")}
    predicates = {"observed_equals_expected": False, "expected_date_equals_algorithm": True,
        "observed_date_equals_session": False, "observed_relation": "before"}
    body.update(schema="tpr-cmp28-private-mark-refusal-v2", operation_id=binding["off_operation_id"],
        security_id="SYNTHETIC.CACHE 1" if case != "wrong_sid" else "SYNTHETIC.OTHER 2", data_type="trade_bar",
        algorithm_utc="2021-02-10T21:01:00+00:00", algorithm_local="2021-02-10T16:01:00-05:00",
        expected_close_utc="2021-02-10T21:00:00+00:00", expected_close_local="2021-02-10T16:00:00-05:00",
        observed_end_utc="2021-02-09T21:00:00+00:00", observed_end_local="2021-02-09T16:00:00-05:00",
        predicates=predicates, source_inputs_admitted=False, strategy_accepted=False, canonical_admission=False,
        valuation_verification_mode=reader.V2_MODE, verification_policy_extended=True)
    if case == "wrong_schema": body["schema"] = "invalid"
    if case == "wrong_clock": body["observed_end_local"] = "2021-02-09T15:00:00-05:00"
    raw = _wire(body)
    binding = reader.prepare_binding_v2(**{**args, "expected_sha256": _sha(raw), "expected_bytes": len(raw)})
    pointer = {"schema": binding["pointer_schema"], "status": "verified", "key": binding["key"], "bytes": len(raw),
        "expected_sha256": _sha(raw), "verified_sha256": _sha(raw), "readback_verified": True, "data_type": "trade_bar",
        "predicates": predicates, "reason_code": "minute_or_native_close_wrong_day_or_future",
        "valuation_verification_mode": reader.V2_MODE}
    return {"binding": binding, "pointer": pointer}, raw


def _build_fixture(*, helper_source, operation_id, git_head, case="valid"):
    parent, _ = _fixture_parent(case)
    return _render(parent, helper_source, operation_id, git_head, _sha(b"SYNTHETIC.CACHE 1"))
