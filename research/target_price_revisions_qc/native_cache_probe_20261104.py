"""Pure prospective cache canary renderer; no filesystem or native effects.

Non-order diagnostic exception: the previous post-close History probes cannot
measure the prospectively subscribed target's native cache at the close. This
fixed two-security canary measures that input property only. A platform banner
or engine label proves no feed change; positive fixtures or native observations
prove no portfolio mark, economic parity, rights, or financial readiness.
Bounded before/repeat/endpoint samples do not form an atomic native snapshot.

Only a future reviewed fixed dispatcher may consume production-rendered bytes
after a fresh private-input claim and committed source verification. There is
no dispatcher here. All historical builders and source epochs remain intact.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

MODULE = "research/target_price_revisions_qc/native_cache_probe_20261104.py"
EPOCH = "TPR-EXACT-SID-PROSPECTIVE-CACHE-20261104-v1"
PROJECT_ID = 38609822
TARGET_SID_SHA256 = "1122fa5f1349f79e231e106127c098da27ef730836a97052d2154ecc46f1afc1"
SESSIONS = tuple(f"2021-02-{day:02d}" for day in range(8, 13))
MAX_SOURCE_BYTES = 24000
FLAGS = ("backtesting_ready", "financial_acceptance", "economics_accepted",
    "native_origin_authenticated", "rights_verified", "point_in_time_verified",
    "portfolio_mark_admitted", "full_window_verified", "engine_feed_fix_verified",
    "canonical_admission", "trading_authority", "atomic_observation_attested")
PATTERN_SOURCES = (
    "research/target_price_revisions_qc/comparison_20261028_mark_probe.py",
    "research/target_price_revisions_qc/comparison_20261028_mark_probe_control.py",
    "research/target_price_revisions_qc/comparison_20261028_algorithm.py",
    "research/target_price_revisions_qc/extended_algorithm_successor.py")


class CacheProbeRefusal(ValueError):
    """Fixed body only: a supplied identity must never enter an exception."""


def _fail():
    raise CacheProbeRefusal("fixed prospective cache diagnostic refused") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")


RUNTIME = r'''
from AlgorithmImports import *
from QuantConnect.Data import SubscriptionDataConfig
from QuantConnect.Securities import Security
from System import Object as NetObject
from datetime import datetime, timedelta, time, timezone
from decimal import Decimal
from fractions import Fraction
from zoneinfo import ZoneInfo
import hashlib
import json
import re

def clock(value, zone):
    if not isinstance(value, datetime):
        raise ValueError("native clock unproved")
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(zone))
    return value.astimezone(timezone.utc)

def quantity_type(value):
    # Representation labels only; never stringify the value or an unknown type.
    for kind, label in ((float, "python_float"), (int, "python_int"),
            (Decimal, "python_decimal"), (Fraction, "python_fraction")):
        if type(value) is kind:
            return label
    if type(value).__module__ == "System" and type(value).__name__ == "Decimal":
        return "system_decimal"
    return "unknown"

class Main(QCAlgorithm):
    def initialize(self):
        self._job = None
        self._disabled = False
        self._seen = set()
        self._slices = self._bars = 0
        self._report = {"schema": "tpr-native-cache-observations-v1",
            "source_epoch": "TPR-EXACT-SID-PROSPECTIVE-CACHE-20261104-v1", "operation_id": None,
            "root_head": None, "status": "setup_unproved", "sessions": {},
            "input_canary_only": True, "non_order_diagnostic_exception": True,
            "direct_order_calls": 0, "history_calls": 0, "object_store_calls": 0,
            "direct_provider_calls": 0, "cache_updates": 0,
            "subscription_removals": 0, "resource_cap_changes": 0,
            "cache_reads_per_check_max": 3, "config_reads_per_check_max": 3,
            "native_close_reads_per_check_max": 2,
            **{key: False for key in FALSE_FLAGS}}
        try:
            self._configuration()
            self._report.update(operation_id=CONFIG["operation_id"], root_head=CONFIG["git_head"])
            if (self.live_mode is not False or type(self.project_id) is not int
                    or self.project_id != 38609822 or self.get_locked() is not False):
                raise ValueError("setup custody unproved")
            self.set_time_zone("America/New_York")
            self.set_start_date(2021, 2, 8)
            self.set_end_date(2021, 2, 12)
            self.settings.daily_precise_end_time = True
            parsed = SecurityIdentifier.parse(CONFIG["target_sid_text"])
            symbol = Symbol(parsed, parsed.symbol)
            if (not isinstance(parsed, SecurityIdentifier) or not isinstance(symbol, Symbol)
                    or parsed.security_type != SecurityType.EQUITY or parsed.market != Market.USA
                    or str(parsed) != CONFIG["target_sid_text"]
                    or str(symbol.id) != CONFIG["target_sid_text"]):
                raise ValueError("native identity unproved")
            control = self.add_equity("SPY", Resolution.MINUTE, fill_forward=False,
                extended_market_hours=True, data_normalization_mode=DataNormalizationMode.RAW)
            target = self.add_security(symbol, resolution=Resolution.MINUTE, fill_forward=False,
                extended_market_hours=False, data_normalization_mode=DataNormalizationMode.RAW)
            if (not isinstance(control, Security) or not isinstance(target, Security)
                    or target.symbol != symbol or control.symbol == symbol):
                raise ValueError("native registration unproved")
            self._symbols = {"control": control.symbol, "target": symbol}
            self._registered = {"control": control, "target": target}
            self.set_benchmark(control.symbol)
            self.schedule.on(self.date_rules.every_day(control.symbol),
                self.time_rules.at(16, 1), self._check_close)
            self._report["status"] = "awaiting_fixed_close_checks"
        except KeyboardInterrupt:
            raise KeyboardInterrupt("cache diagnostic cancelled") from None
        except Exception:
            self._disabled = True

    def _configuration(self):
        if (hashlib.sha256(CONFIG_JSON.encode("ascii")).hexdigest() != CONFIG_SHA256
                or json.dumps(CONFIG, sort_keys=True, separators=(",", ":")) != CONFIG_JSON
                or hashlib.sha256(CONFIG["target_sid_text"].encode("ascii")).hexdigest()
                    != CONFIG["target_sid_sha256"]):
            raise ValueError("configuration unproved")

    def _bound(self):
        self._configuration()
        job = self.algorithm_id
        if (not isinstance(self, QCAlgorithm) or self.live_mode is not False or self.is_warming_up is not False
                or not isinstance(self.current_slice, Slice) or type(self.project_id) is not int
                or self.project_id != 38609822 or self.get_locked() is not True
                or type(job) is not str or re.fullmatch("[a-f0-9]{32}", job) is None
                or self._job is not None and self._job != job):
            raise ValueError("runtime custody unproved")
        self._job = job

    def _config_values(self, row):
        tick = "trade" if row.tick_type == TickType.TRADE else "quote" if row.tick_type == TickType.QUOTE else "unknown"
        return (str(row.symbol.id), row.type.FullName, tick,
            row.resolution == Resolution.MINUTE, row.fill_data_forward,
            row.data_normalization_mode == DataNormalizationMode.RAW,
            row.extended_market_hours, row.is_internal_feed, row.is_custom_data,
            row.exchange_time_zone.id, row.data_time_zone.id)

    def _configs(self, label, symbol, security):
        if (len(self.securities) != 2 or not isinstance(security, Security)
                or security.symbol != symbol
                or not NetObject.ReferenceEquals(self.securities[symbol], security)):
            raise ValueError("registered security unproved")
        stream = self.subscription_manager.subscription_data_config_service.get_subscription_data_configs(symbol, True)
        rows, stop, cursor = [], object(), iter(stream)
        for _ in range(3):
            row = next(cursor, stop)
            if row is stop:
                break
            rows.append(row)
        if not 1 <= len(rows) <= 2:
            raise ValueError("configuration count unproved")
        kinds, frames = [], []
        for row in rows:
            if (not isinstance(row, SubscriptionDataConfig) or row.symbol != symbol
                    or row.resolution != Resolution.MINUTE or row.fill_data_forward is not False
                    or row.data_normalization_mode != DataNormalizationMode.RAW
                    or row.extended_market_hours is not (label == "control")
                    or row.is_internal_feed is not False or row.is_custom_data is not False
                    or row.exchange_time_zone.id != "America/New_York"
                    or row.data_time_zone.id != "America/New_York"):
                raise ValueError("configuration fields unproved")
            kind = row.type.FullName
            if kind == "QuantConnect.Data.Market.TradeBar" and row.tick_type == TickType.TRADE:
                kinds.append("trade")
            elif kind == "QuantConnect.Data.Market.QuoteBar" and row.tick_type == TickType.QUOTE:
                kinds.append("quote")
            else:
                raise ValueError("configuration type unproved")
            # Copy primitive values now; retaining native objects alone cannot
            # detect fields changing in place at the next native boundary.
            frames.append(self._config_values(row))
        if kinds.count("trade") != 1 or kinds.count("quote") > 1:
            raise ValueError("trade configuration unproved")
        return rows, tuple(frames)

    def _cache_values(self, last):
        if not isinstance(last, TradeBar):
            return (last is not None, False)
        if not isinstance(last.symbol, Symbol) or not isinstance(last.period, timedelta):
            raise ValueError("typed cache fields unproved")
        return (True, True, str(last.symbol.id), last.is_fill_forward, last.period,
            clock(last.time, "America/New_York"), clock(last.end_time, "America/New_York"))

    def _native_close(self, security, local_day):
        midnight = datetime.combine(local_day, time())
        closed = clock(security.exchange.hours.get_next_market_close(midnight, False), "America/New_York")
        if closed != clock(datetime.combine(local_day, time(16)), "America/New_York"):
            raise ValueError("regular close unproved")
        return closed

    def _observe(self, label, now, local_day):
        cell = {key: False for key in ("configuration_verified", "cache_present",
            "typed_trade_bar", "exact_sid", "non_fill_forward", "minute_period",
            "same_session", "end_not_future", "end_equals_close", "cache_reference_unchanged",
            "configuration_unchanged", "cache_values_unchanged", "native_close_unchanged",
            "registered_security_unchanged",
            "slice_reference_unchanged", "freshness_canary")}
        cell.update(status="observation_unproved", quantity_type="unknown",
            now_minus_end_microseconds=None, close_minus_end_microseconds=None)
        try:
            self._bound()
            current_slice = self.current_slice
            symbol, security = self._symbols[label], self._registered[label]
            before = self._configs(label, symbol, security)
            cell["configuration_verified"] = True
            cell["quantity_type"] = quantity_type(self.portfolio[symbol].quantity)
            last = security.get_last_data()
            cache_before = self._cache_values(last)
            cell["cache_present"], cell["typed_trade_bar"] = cache_before[:2]
            if cache_before[1]:
                began, ended = cache_before[5:7]
                closed = self._native_close(security, local_day)
                cell.update(exact_sid=cache_before[2] == str(symbol.id),
                    non_fill_forward=cache_before[3] is False,
                    minute_period=cache_before[4] == timedelta(minutes=1) and ended-began == timedelta(minutes=1),
                    same_session=ended.astimezone(ZoneInfo("America/New_York")).date() == local_day,
                    end_not_future=ended <= now, end_equals_close=ended == closed,
                    now_minus_end_microseconds=(now-ended)//timedelta(microseconds=1),
                    close_minus_end_microseconds=(closed-ended)//timedelta(microseconds=1))
            last_after = security.get_last_data()
            cell["cache_reference_unchanged"] = NetObject.ReferenceEquals(last, last_after)
            cell["cache_values_unchanged"] = cache_before == self._cache_values(last_after)
            after = self._configs(label, symbol, security)
            cell["configuration_unchanged"] = before[1] == after[1] and len(before[0]) == len(after[0]) and all(
                NetObject.ReferenceEquals(a, b) for a, b in zip(before[0], after[0]))
            if cache_before[1]:
                cell["native_close_unchanged"] = closed == self._native_close(security, local_day)
            # A third bounded configuration sample and a fresh CURRENT cache
            # sample follow close queries. No repeat-until-stable loop exists.
            endpoint = self._configs(label, symbol, security)
            cell["configuration_unchanged"] &= after[1] == endpoint[1] and len(after[0]) == len(endpoint[0]) and all(
                NetObject.ReferenceEquals(a, b) for a, b in zip(after[0], endpoint[0]))
            last_endpoint = security.get_last_data()
            cell["cache_reference_unchanged"] &= NetObject.ReferenceEquals(last_after, last_endpoint)
            self._bound()
            cell["slice_reference_unchanged"] = NetObject.ReferenceEquals(current_slice, self.current_slice)
            # Close/config calls are also observation boundaries. Re-read the
            # retained objects' primitive values after the final native query.
            cell["cache_values_unchanged"] &= cache_before == self._cache_values(last_endpoint)
            cell["configuration_unchanged"] &= endpoint[1] == tuple(self._config_values(row) for row in endpoint[0])
            cell["registered_security_unchanged"] = (len(self.securities) == 2 and security.symbol == symbol
                and NetObject.ReferenceEquals(self.securities[symbol], security))
            unchanged_clock = clock(self.utc_time, "UTC") == now == clock(self.time, "America/New_York")
            # Extended SPY advances the 16:01 clock; it may have an after-close
            # bar. Its control freshness never substitutes for target close data.
            fresh_end = (cell["end_equals_close"] if label == "target" else
                cell["now_minus_end_microseconds"] is not None
                and 0 <= cell["now_minus_end_microseconds"] <= 60000000)
            cell["freshness_canary"] = bool(unchanged_clock and fresh_end and all(cell[key] for key in
                ("configuration_verified", "cache_present", "typed_trade_bar", "exact_sid", "non_fill_forward",
                 "minute_period", "same_session", "end_not_future", "cache_reference_unchanged",
                 "configuration_unchanged", "cache_values_unchanged", "native_close_unchanged",
                 "registered_security_unchanged", "slice_reference_unchanged")))
            cell["status"] = "bounded_cache_observation"
        except KeyboardInterrupt:
            raise KeyboardInterrupt("cache diagnostic cancelled") from None
        except Exception:
            cell["freshness_canary"] = False
        return cell

    def _check_close(self):
        if self._disabled:
            return
        try:
            self._bound()
            now, local = clock(self.utc_time, "UTC"), clock(self.time, "America/New_York")
            day = local.astimezone(ZoneInfo("America/New_York")).date()
            session = day.isoformat()
            if (now != local or session not in CONFIG["sessions"] or session in self._seen
                    or local.astimezone(ZoneInfo("America/New_York")).time() != time(16, 1)
                    or self.settings.daily_precise_end_time is not True):
                raise ValueError("fixed observation clock unproved")
            self._seen.add(session)
            cells = {label: self._observe(label, now, day) for label in ("control", "target")}
            self._bound()
            if clock(self.utc_time, "UTC") != now or clock(self.time, "America/New_York") != now:
                raise ValueError("observation clock changed")
            self._report["sessions"][session] = cells
        except KeyboardInterrupt:
            raise KeyboardInterrupt("cache diagnostic cancelled") from None
        except Exception:
            self._disabled = True
            self._report["status"] = "native_scope_unproved"

    def on_data(self, data):
        if self._disabled:
            return
        try:
            self._bound()
            if not isinstance(data, Slice) or not 0 <= len(data.bars) <= 2:
                raise ValueError("native slice unproved")
            self._slices += 1
            self._bars += len(data.bars)
            if self._slices > 6000 or self._bars > 12000:
                raise ValueError("native observation bound")
        except KeyboardInterrupt:
            raise KeyboardInterrupt("cache diagnostic cancelled") from None
        except Exception:
            self._disabled = True
            self._report["status"] = "native_scope_unproved"

    def on_end_of_algorithm(self):
        try:
            self._bound()
            complete = not self._disabled and set(self._report["sessions"]) == set(CONFIG["sessions"])
            self._report["status"] = "complete_cache_observations" if complete else self._report["status"]
            self._report["actual_job_id"] = self._job
        except KeyboardInterrupt:
            raise KeyboardInterrupt("cache diagnostic cancelled") from None
        except Exception:
            self._report["status"] = "end_custody_unproved"
        self._report.update(close_checks=len(self._report["sessions"]), delivered_slices=self._slices,
            delivered_bar_rows=self._bars, target_close_canary_days=sum(
                row["target"]["freshness_canary"] is True for row in self._report["sessions"].values()))
        wire = json.dumps(self._report, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(wire) <= 16384:
            self.log("TPR_CACHE_PROBE_RESULT " + wire)
'''


def _render(target, digest, operation_id, git_head):
    if (type(operation_id) is not str or re.fullmatch(r"TPR-CACHE-20261104-[A-Z0-9-]{1,40}", operation_id) is None
            or type(git_head) is not str or re.fullmatch(r"[a-f0-9]{40}", git_head) is None
            or git_head == "0" * 40):
        _fail()
    config = {"schema": "tpr-native-cache-config-v1", "source_epoch": EPOCH,
        "project_id": PROJECT_ID, "operation_id": operation_id, "git_head": git_head,
        "target_sid_text": target, "target_sid_sha256": digest,
        "sessions": list(SESSIONS), "false_flags": list(FLAGS)}
    raw = _wire(config)
    source = ("CONFIG_JSON = " + repr(raw.decode("ascii")) + "\nCONFIG_SHA256 = " + repr(_sha(raw))
        + "\nCONFIG = __import__('json').loads(CONFIG_JSON)\nFALSE_FLAGS = " + repr(FLAGS) + "\n" + RUNTIME).encode("ascii")
    if not 0 < len(source) <= MAX_SOURCE_BYTES:
        _fail()
    compile(ast.parse(source), "main.py", "exec")
    report = {"schema": "tpr-native-cache-build-v1", "source_epoch": EPOCH,
        "project_id": PROJECT_ID, "operation_id": operation_id, "git_head": git_head,
        "main_bytes": len(source), "main_sha256": _sha(source), "config_sha256": _sha(raw),
        "sessions": list(SESSIONS), "prospective_initialize_subscription": True,
        "input_canary_only": True, "diagnostic_exception": "non_order_native_cache_freshness_only",
        "history_objectstore_orders_provider_effects": False, "max_securities": 2,
        "cache_reads_per_check_max": 3, "config_reads_per_check_max": 3,
        "native_close_reads_per_check_max": 2,
        "native_requests_dispatched": 0, **{key: False for key in FLAGS}}
    return source, _wire(report) + b"\n"


def build_cache_probe(*, target_sid_text, operation_id, git_head):
    """Render only the exact hash-bound private target; caller claims its read."""
    if (type(target_sid_text) is not str or not target_sid_text.isascii()
            or re.fullmatch(r"[^\s|]{1,64} [A-Z0-9]{1,13}", target_sid_text) is None
            or int(target_sid_text.split(" ")[1], 36) >= 2**64
            or _sha(target_sid_text.encode("ascii")) != TARGET_SID_SHA256):
        _fail()
    return _render(target_sid_text, TARGET_SID_SHA256, operation_id, git_head)


def _build_fixture(*, operation_id, git_head):
    """Fixed synthetic rendering only; no production input or override argument."""
    target = "SYNTHETIC.CACHE 1"
    return _render(target, _sha(target.encode("ascii")), operation_id, git_head)
