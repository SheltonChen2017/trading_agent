"""Pure fixed OFF/SPY configuration census; no private input or native effect.

This non-order metadata diagnostic asks one include-internal configuration
query, records at most8projected rows plus a ninth sentinel, and never selects
or registers a target. It does not repair an SDK/data route, attribute a row
to the benchmark, or admit any financial result. Unknown fields stay None.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

from . import native_cache_probe_20261104 as base

MODULE = "research/target_price_revisions_qc/native_config_census_20261104.py"
EPOCH = "TPR-OFF-SPY-CONFIG-CENSUS-20261104-v1"
PROJECT_ID = 38609822
MAX_SOURCE_BYTES = 60000
BASE_SHA256 = "481602457ae78568b3b708cbefd0315d7115baf95a8bd27536983e8bbfec7a86"
BASE_RUNTIME_SHA256 = "4ff09e1079905afb08ee8d9a42e0bfc27a72ff0f878efbc9d591e865b661eb10"
REQUIRED_SOURCES = frozenset((MODULE, base.MODULE))
PINNED = {base.MODULE: BASE_SHA256}
FLAGS = base.FLAGS + ("source_inputs_admitted", "strategy_accepted", "source_origin_authenticated",
    "sdk_hard_timeout_proven", "sdk_preallocation_byte_bound_proven", "benchmark_origin_proven",
    "provider_wide_absence_proven")


class CensusRefusal(ValueError):
    pass


def _fail():
    raise CensusRefusal("fixed native configuration census refused") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


RUNTIME = r'''
from AlgorithmImports import *
from QuantConnect.Data import SubscriptionDataConfig
from QuantConnect.Securities import Security
from System import Object as NetObject
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import re

class Main(QCAlgorithm):
    def initialize(self):
        self._job, self._disabled, self._attempted, self._waiting_now = None, False, False, None
        self._report = {"schema": "tpr-fixed-config-census-result-v1", "source_epoch": SOURCE_EPOCH,
            "operation_id": None, "root_head": None, "project_id": 38609822, "actual_job_id": None,
            "status": "setup_unproved", "first_failure_stage": None, "first_failure_code": None,
            "current_stage": "initialize", "terminal_summary": "not_called", "query_count": 0,
            "rows_seen": 0, "rows": [], "enumeration_complete": False, "truncated": False,
            "metadata_complete": False, "scope_stable": False, "complete": False,
            "retained_row_refs_unchanged": None, "projected_metadata_unchanged": False,
            "collection_endpoint_supported": None, "collection_count_unchanged": None, "collection_reason": None,
            "on_data_entries": 0, "disabled_skips": 0, "post_query_skips": 0,
            "callback_cap_reached": False, "preopen_empty_slices": 0,
            "row_limit": 8, "sentinel_limit": 9, "callback_limit": 6400,
            "direct_order_calls": 0, "history_calls": 0, "object_store_calls": 0,
            "cache_writes": 0, "direct_provider_calls": 0, "target_registrations": 0,
            **{key: False for key in FALSE_FLAGS}}
        try:
            self._configuration()
            if (self.live_mode is not False or type(self.project_id) is not int
                    or self.project_id != 38609822 or self.get_locked() is not False):
                raise ValueError("setup custody unproved")
            self._report.update(operation_id=CONFIG["operation_id"], root_head=CONFIG["git_head"])
            self.set_time_zone("America/New_York")
            self.set_start_date(2021, 2, 8)
            self.set_end_date(2021, 2, 12)
            self.settings.daily_precise_end_time = True
            control = self.add_equity("SPY", Resolution.MINUTE, fill_forward=False,
                extended_market_hours=True, data_normalization_mode=DataNormalizationMode.RAW)
            if not isinstance(control, Security):
                raise ValueError("native control unproved")
            self._control, self._symbol = control, control.symbol
            self.set_benchmark(control.symbol)
            self._report["status"] = "awaiting_preopen_control"
        except KeyboardInterrupt:
            raise KeyboardInterrupt("configuration census cancelled") from None
        except Exception:
            self._failure("initialize_unproved")

    def _failure(self, code):
        if self._report["first_failure_stage"] is None:
            self._report.update(first_failure_stage=self._report["current_stage"], first_failure_code=code)
        self._disabled = True
        self._report.update(status="census_failed", complete=False)

    def _configuration(self):
        if (hashlib.sha256(CONFIG_JSON.encode("ascii")).hexdigest() != CONFIG_SHA256
                or json.dumps(CONFIG, sort_keys=True, separators=(",", ":")) != CONFIG_JSON):
            raise ValueError("configuration unproved")

    def _bound(self):
        self._configuration()
        job = self.algorithm_id
        if (not isinstance(self, QCAlgorithm) or self.live_mode is not False or self.is_warming_up is not False
                or type(self.project_id) is not int or self.project_id != 38609822 or self.get_locked() is not True
                or not isinstance(self.current_slice, Slice) or type(job) is not str
                or re.fullmatch("[a-f0-9]{32}", job) is None or self._job is not None and self._job != job):
            raise ValueError("runtime custody unproved")
        self._job = job

    def _scope(self, data):
        self._bound()
        now, local = clock(self.utc_time, "UTC"), clock(self.time, "America/New_York")
        ny = local.astimezone(ZoneInfo("America/New_York"))
        if (now != local or ny.date().isoformat() != "2021-02-08" or not time(4) <= ny.time() < time(9, 30)
                or not isinstance(data, Slice) or not NetObject.ReferenceEquals(data, self.current_slice)
                or len(self.securities) != 1 or not isinstance(self._control, Security)
                or self._control.symbol != self._symbol
                or not NetObject.ReferenceEquals(self.securities[self._symbol], self._control)
                or len(data.bars) != 1 or self._symbol not in data.bars):
            raise ValueError("preopen scope unproved")
        bar = data.bars[self._symbol]
        if (not isinstance(bar, TradeBar) or not isinstance(bar.symbol, Symbol)
                or not isinstance(bar.period, timedelta)):
            raise ValueError("preopen bar type unproved")
        frame = (bar.symbol == self._symbol and bar.symbol.id == self._symbol.id,
            bar.is_fill_forward, bar.period, clock(bar.time, "America/New_York"), clock(bar.end_time, "America/New_York"))
        if (frame[0] is not True or frame[1] is not False or frame[2] != timedelta(minutes=1)
                or frame[4]-frame[3] != timedelta(minutes=1)
                or frame[3].astimezone(ZoneInfo("America/New_York")).date().isoformat() != "2021-02-08"
                or not time(4) <= frame[3].astimezone(ZoneInfo("America/New_York")).time() < time(9, 30)
                or frame[4] > now or now-frame[4] > timedelta(minutes=1)):
            raise ValueError("preopen bar clock unproved")
        return now, data, self._control, bar, frame

    def _same_scope(self, data, before):
        after = self._scope(data)
        if (before[0] != after[0] or before[4] != after[4]
                or not all(NetObject.ReferenceEquals(before[i], after[i]) for i in (1, 2, 3))):
            raise ValueError("census scope changed")

    def _metadata(self, row):
        fields = ("symbol_sid_matches", "minute", "daily", "raw", "adjusted", "internal", "custom",
            "fill_forward", "extended", "exchange_timezone_ny", "data_timezone_ny")
        value = {key: None for key in fields}
        value.update(native_row=None, kind=None, unsupported=[])
        try:
            value["native_row"] = isinstance(row, SubscriptionDataConfig)
        except Exception:
            value["unsupported"].append("row_type_unavailable")
            return value
        if value["native_row"] is not True:
            value["unsupported"].append("row_not_native")
            return value
        try:
            symbol = row.symbol
            if not isinstance(symbol, Symbol): raise ValueError("symbol type")
            matched = symbol == self._symbol and symbol.id == self._symbol.id
            if type(matched) is not bool: raise ValueError("symbol predicate type")
            value["symbol_sid_matches"] = matched
        except Exception:
            value["unsupported"].append("symbol_unavailable")
        try:
            name = row.type.FullName
            if type(name) is not str: raise ValueError("kind type")
            value["kind"] = {"QuantConnect.Data.Market.TradeBar": "trade_bar",
                "QuantConnect.Data.Market.QuoteBar": "quote_bar", "QuantConnect.Data.Market.Tick": "tick"}.get(name)
            if value["kind"] is None: value["unsupported"].append("kind_unsupported")
        except Exception:
            value["unsupported"].append("kind_unavailable")
        for attr, expected_type, pairs in (("resolution", type(Resolution.MINUTE),
                (("minute", Resolution.MINUTE), ("daily", Resolution.DAILY))),
                ("data_normalization_mode", type(DataNormalizationMode.RAW),
                (("raw", DataNormalizationMode.RAW), ("adjusted", DataNormalizationMode.ADJUSTED)))):
            try:
                cell = getattr(row, attr)
                if type(cell) is not expected_type: raise ValueError("enum representation")
                results = tuple(cell == expected for label, expected in pairs)
                if any(type(item) is not bool for item in results): raise ValueError("enum predicates")
                for (label, _), item in zip(pairs, results): value[label] = item
            except Exception:
                value["unsupported"].append(attr+"_unavailable")
        for label, attr in (("internal", "is_internal_feed"), ("custom", "is_custom_data"),
                ("fill_forward", "fill_data_forward"), ("extended", "extended_market_hours")):
            try:
                cell = getattr(row, attr)
                if type(cell) is not bool: raise ValueError("boolean representation")
                value[label] = cell
            except Exception:
                value["unsupported"].append(label+"_unavailable")
        for label, attr in (("exchange_timezone_ny", "exchange_time_zone"), ("data_timezone_ny", "data_time_zone")):
            try:
                zone = getattr(row, attr).id
                if type(zone) is not str: raise ValueError("timezone representation")
                value[label] = zone == "America/New_York"
            except Exception:
                value["unsupported"].append(label+"_unavailable")
        return value

    def _collection_count(self, stream, method=None):
        try:
            if method is None:
                try: value, method = stream.Count, "count"
                except AttributeError: value, method = len(stream), "len"
            else:
                value = stream.Count if method == "count" else len(stream)
            if type(value) is not int or not 0 <= value <= 2147483647:
                return method, None
            return method, value
        except Exception:
            return method, None

    def _collection_refs(self, stream, count):
        try:
            return tuple(stream[index] for index in range(count))
        except Exception:
            return None

    def _census(self, data):
        self._report["current_stage"] = "preopen_scope"
        before = self._scope(data)
        self._attempted = True
        self._report["current_stage"] = "config_query"
        self._report["query_count"] += 1
        stream = self.subscription_manager.subscription_data_config_service.get_subscription_data_configs(self._symbol, True)
        self._same_scope(data, before)
        count_method, initial_count = self._collection_count(stream)
        self._same_scope(data, before)
        self._report["current_stage"] = "config_iteration"
        rows, stop, cursor = [], object(), iter(stream)
        for index in range(9):
            row = next(cursor, stop)
            if row is stop:
                self._report["enumeration_complete"] = True
                break
            self._report["rows_seen"] += 1
            if index == 8:
                self._report["truncated"] = True
                break
            rows.append(row)
        self._same_scope(data, before)
        retained = self._collection_refs(stream, len(rows)) if initial_count is not None else None
        endpoint_supported = initial_count is not None and retained is not None
        self._report["collection_endpoint_supported"] = endpoint_supported
        if not endpoint_supported:
            self._report["collection_reason"] = "collection_endpoint_unsupported"
        elif (not all(NetObject.ReferenceEquals(a, b) for a, b in zip(retained, rows))
                or self._report["enumeration_complete"] and initial_count != len(rows)
                or self._report["truncated"] and initial_count < 9):
            self._report["collection_reason"] = "collection_enumeration_mismatch"
            raise ValueError("collection enumeration changed")
        self._same_scope(data, before)
        self._report["current_stage"] = "metadata_sample"
        first = [self._metadata(row) for row in rows]
        self._report["rows"] = first
        self._same_scope(data, before)
        second = [self._metadata(row) for row in rows]
        self._report["projected_metadata_unchanged"] = first == second
        if not self._report["projected_metadata_unchanged"]:
            raise ValueError("projected metadata changed")
        self._report["current_stage"] = "census_endpoint"
        if endpoint_supported:
            _, final_count = self._collection_count(stream, count_method)
            final_refs = self._collection_refs(stream, len(rows))
            self._report["collection_count_unchanged"] = final_count is not None and final_count == initial_count
            self._report["retained_row_refs_unchanged"] = final_refs is not None and all(
                NetObject.ReferenceEquals(a, b) for a, b in zip(retained, final_refs))
            if not self._report["collection_count_unchanged"] or not self._report["retained_row_refs_unchanged"]:
                self._report["collection_reason"] = "collection_endpoint_changed"
                raise ValueError("collection endpoint changed")
        final_metadata = [self._metadata(row) for row in rows]
        self._report["projected_metadata_unchanged"] = first == final_metadata
        if not self._report["projected_metadata_unchanged"]:
            raise ValueError("endpoint metadata changed")
        self._same_scope(data, before)
        self._report["scope_stable"] = True
        self._report["metadata_complete"] = all(row["native_row"] is True and not row["unsupported"] for row in first)
        self._report["complete"] = (self._report["enumeration_complete"] and not self._report["truncated"]
            and self._report["metadata_complete"] and self._report["scope_stable"] and endpoint_supported
            and self._report["collection_count_unchanged"] is True and self._report["retained_row_refs_unchanged"] is True)
        self._report["status"] = "complete_config_census" if self._report["complete"] else "partial_config_census"

    def on_data(self, data):
        if self._report["on_data_entries"] >= 6400:
            self._report["callback_cap_reached"] = True
            self._failure("callback_budget")
        else:
            self._report["on_data_entries"] += 1
        if self._disabled:
            self._report["disabled_skips"] = min(6400, self._report["disabled_skips"]+1)
            return
        if self._attempted:
            self._report["post_query_skips"] = min(6400, self._report["post_query_skips"]+1)
            return
        try:
            self._report["current_stage"] = "waiting_custody"
            self._bound()
            self._report["current_stage"] = "waiting_clock"
            now, local = clock(self.utc_time, "UTC"), clock(self.time, "America/New_York")
            ny = local.astimezone(ZoneInfo("America/New_York"))
            if (now != local or ny.date().isoformat() != "2021-02-08" or not time() <= ny.time() < time(9, 30)
                    or self._waiting_now is not None and now < self._waiting_now):
                raise ValueError("waiting clock unproved")
            self._waiting_now = now
            self._report["current_stage"] = "waiting_slice"
            if not isinstance(data, Slice) or not NetObject.ReferenceEquals(data, self.current_slice) or not 0 <= len(data.bars) <= 1:
                raise ValueError("waiting slice unproved")
            if self._symbol not in data.bars:
                if len(data.bars) != 0: raise ValueError("foreign waiting trade")
                self._report["preopen_empty_slices"] += 1
                if self._report["preopen_empty_slices"] > 400: raise ValueError("waiting bound")
                return
            self._census(data)
        except KeyboardInterrupt:
            raise KeyboardInterrupt("configuration census cancelled") from None
        except Exception:
            self._failure("scope_or_native_operation_unproved")

    def on_end_of_algorithm(self):
        try:
            self._report["current_stage"] = "end_custody"
            self._bound()
            self._report["actual_job_id"] = self._job
            self._report["terminal_summary"] = "complete" if self._report["complete"] else "incomplete"
            if not self._attempted and self._report["first_failure_stage"] is None:
                self._failure("census_not_attempted")
        except KeyboardInterrupt:
            raise KeyboardInterrupt("configuration census cancelled") from None
        except Exception:
            self._failure("end_custody_unproved")
            self._report["terminal_summary"] = "custody_unproved"
        wire = json.dumps(self._report, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(wire) <= 16384:
            self.log("TPR_CONFIG_CENSUS_RESULT " + wire)
'''


def build_config_census(*, operation_id, git_head):
    """Return fixed main/report bytes; caller must separately claim any effect."""
    if (type(operation_id) is not str or re.fullmatch(r"TPR-CONFIG-CENSUS-20261104-[A-Z0-9-]{1,40}", operation_id) is None
            or type(git_head) is not str or re.fullmatch("[a-f0-9]{40}", git_head) is None or git_head == "0"*40
            or _sha(base.RUNTIME.encode("utf-8")) != BASE_RUNTIME_SHA256):
        _fail()
    clock_node = next(n for n in ast.parse(base.RUNTIME).body if isinstance(n, ast.FunctionDef) and n.name == "clock")
    config = {"schema": "tpr-fixed-config-census-config-v1", "source_epoch": EPOCH,
        "project_id": PROJECT_ID, "operation_id": operation_id, "git_head": git_head}
    raw = _wire(config)
    prefix = ("SOURCE_EPOCH = "+repr(EPOCH)+"\nCONFIG_JSON = "+repr(raw.decode("ascii"))
        +"\nCONFIG_SHA256 = "+repr(_sha(raw))+"\nCONFIG = __import__('json').loads(CONFIG_JSON)"
        +"\nFALSE_FLAGS = "+repr(FLAGS)+"\n")
    tree = ast.parse(RUNTIME)
    tree.body.insert(10, clock_node)
    source = (prefix+ast.unparse(ast.fix_missing_locations(tree))+"\n").encode("utf-8")
    if not 0 < len(source) <= MAX_SOURCE_BYTES:
        _fail()
    compile(ast.parse(source), "main.py", "exec")
    report = {"schema": "tpr-fixed-config-census-build-v1", "source_epoch": EPOCH, "project_id": PROJECT_ID,
        "operation_id": operation_id, "git_head": git_head, "main_bytes": len(source), "main_sha256": _sha(source),
        "config_sha256": _sha(raw), "base_sha256": BASE_SHA256, "max_config_queries": 1,
        "max_rows": 8, "max_next_calls": 9, "native_requests_dispatched": 0,
        "max_count_samples": 2, "max_index_reads": 16, "max_metadata_samples": 3,
        "non_order_metadata_diagnostic": True, "no_parent_or_target_path": True, **{key: False for key in FLAGS}}
    return source, _wire(report)+b"\n"
