"""QC-local exact-original-binding RAW price availability diagnostic.

This module has no host transport, Object Store write, order, cache injection,
credential or HTTP interface. A future exact project/source/paid-organization/
run/attempt protocol must authorize its invocation. Its opaque book remains
inside QC; supplied binding hashes are source bindings, never authority.
"""
from __future__ import annotations

import hashlib
import json
import re
import time as clock
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

try:
    import accepted_risk_order_level_input_runtime as inputs
    import accepted_risk_preliminary_qc_figi as figi
    import newrule_legacy_primitives as money
except ImportError:
    from research.analyst_revisions_v2_qc import accepted_risk_order_level_input_runtime as inputs
    from research.analyst_revisions_v2_qc import accepted_risk_preliminary_qc_figi as figi
    from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as money

SCHEMA = "arv2-r298-native-price-source-diagnostic-v1"
PRIVATE_SCHEMA = SCHEMA + "-QC-private"
SPEC_SCHEMA = SCHEMA + "-specification"
FIRST_SESSION, LAST_SESSION = "2020-12-31", "2026-10-13"
EXPECTED_BINDINGS, EXPECTED_AXIS_COUNT, SELECTED_COUNT = 6151, 3466, 5
EXPECTED_SESSION_COUNT = 1452
PACKAGE_SHA256 = "1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2"
ACTIVATION_SHA256 = "ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b"
BINDING_STREAM_SHA256 = "73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f"
AXIS_SHA256 = "4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585"
ADMISSION_SHA256 = "5d0075cfe24cdfaaa56992de1d3b30bb4895d2495a8356ade47a4c3bc9dea281"
SCHEDULE_SHA256 = "d4bc21d601f7d32b2b4190fe1ce4307d2a63d56821d61d99464dbd710b7476ee"
CALENDAR_SOURCE_SHA256 = "174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89"
UNIVERSES = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE", "XLI", "XLF")
NY = ZoneInfo("America/New_York")
MAX_PRIVATE_BYTES, MAX_SUMMARY_BYTES, MAX_PRICE_TEXT = 8 * 1024 * 1024, 32768, 64
MAX_RUNTIME_SECONDS, MAX_PORTFOLIO_ROWS = 900, 32
STATUSES = frozenset(("not_dispatched_identity_refusal", "complete", "lookup_failed",
    "call_failed", "read_failed", "bound_exceeded"))
ROW_REASONS = frozenset(("batch_shape", "bar_type", "identity", "session", "time",
    "period", "fill_forward", "price", "unreadable"))
FORWARD_STATES = frozenset(("known_US_equity", "known_incompatible", "unavailable", "unreadable"))
FALSE_FLAGS = {"orders_submitted_by_module": False, "executable_quotes_substituted": False,
    "engine_price_cache_written_by_module": False, "QC_raw_rows_exported_by_module": False,
    "QC_raw_rows_published_by_module": False, "source_priority_admitted": False,
    "reference_or_NAV_price_input_admitted": False, "complete_required_price_coverage_proven": False,
    "terminal_payoff_proven": False, "historical_identity_proven": False,
    "permanent_security_master_proven": False, "point_in_time_proven": False,
    "formal_forward_ready": False, "paper_or_live_ready": False}
FINITE = frozenset(("specification", "once", "deadline", "orders", "clock", "settings",
    "package", "catalog", "axis", "resolution", "own_ETF", "native_metadata",
    "subscription", "currency", "calendar", "source_changed", "summary", "private_bound", "unknown"))


class Refused(ValueError):
    """Finite predicate only; no identifiers, raw QC fields or exception text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else "unknown"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None


def make_specification(selected_binding_sha256s):
    """Pure prospective source description; no invocation or paid-rights grant."""
    require(type(selected_binding_sha256s) in (list, tuple)
        and len(selected_binding_sha256s) == SELECTED_COUNT
        and all(_hash(value) for value in selected_binding_sha256s)
        and list(selected_binding_sha256s) == sorted(set(selected_binding_sha256s)), "specification")
    return {"schema": SPEC_SCHEMA, "selected_whole_binding_sha256s": list(selected_binding_sha256s),
        "package_sha256": PACKAGE_SHA256, "activation_sha256": ACTIVATION_SHA256,
        "binding_stream_sha256": BINDING_STREAM_SHA256, "full_binding_count": EXPECTED_BINDINGS,
        "security_master_admission_sha256": ADMISSION_SHA256,
        "own_universe_tickers": list(UNIVERSES),
        "full_axis_count": EXPECTED_AXIS_COUNT, "ordered_full_axis_sha256": AXIS_SHA256,
        "first_session": FIRST_SESSION, "last_session": LAST_SESSION,
        "requested_session_count": EXPECTED_SESSION_COUNT,
        "NYSE_schedule_sha256": SCHEDULE_SHA256, "calendar_source_sha256": CALENDAR_SOURCE_SHA256,
        "calendar_commitment": "canonical_ASCII_NO_LF_rows_session_open_utc_close_utc_ISO_plus00:00",
        "source_assignment": "exact_five_original_bindings_entire_window_same_all_six_cells_reference_AND_NAV",
        "history": "one_fixed_typed_TradeBar_Daily_call_per_selected_original_symbol_RAW_noFF_regular_hours",
        "daily_time_policy": "DailyPreciseEndTime_true_Time_open_EndTime_close_Period_close_minus_open",
        "maximum_history_calls": SELECTED_COUNT,
        "source_scope": "availability_only_no_price_admission_or_Sharadar_refusal_clearance"}


def validate_specification(value):
    require(type(value) is dict and "selected_whole_binding_sha256s" in value, "specification")
    expected = make_specification(value["selected_whole_binding_sha256s"])
    require(value == expected, "specification")
    return json.loads(canonical(expected))


def profile_record():
    return {"schema": SCHEMA, "specification_schema": SPEC_SCHEMA, "private_schema": PRIVATE_SCHEMA,
        "selection": "five_externally_frozen_original_whole_binding_hashes_no_tickers_or_current_FIGI_replacement",
        "identity": "fresh_full_original_FIGI_exact_roundtrip_and_full_SID_census_including_all_8_own_ETFs",
        "forward_census": "capture_every_forward_result_in_existing_single_resolver_pass_before_any_refusal_filtering",
        "forward_unknowns": "explicit_unavailable_unreadable_incompatible_counts_no_claim_all_native_SIDs_are_known",
        "own_ETF_collision_count": "all_known_forward_identity_SIDs_including_benchmark_and_duplicate_SID_refusals_not_resolved_subset",
        "original_QC_SIDs": "absent_in_original_bindings_never_inferred_from_old_5121_1030_totals",
        "calendar": "QC_ExchangeHours_full_grid_must_match_independent_frozen_NYSE_commitment_before_History",
        "bar_policy": "all_rows_bounded_precise_regular_session_typed_RAW_noFF_same_native_SID_USD",
        "duplicate_policy": "invalidate_cell_never_choose_first_or_last",
        "unpriced_policy": "explicit_absent_invalid_duplicate_or_failure_unknown_never_clip_membership_or_binding_end",
        "absence_qualification": "unseen_exact_grid_cells_after_complete_enumeration_not_physical_provider_absence",
        "maximum_history_calls": SELECTED_COUNT, "maximum_sessions_per_symbol": EXPECTED_SESSION_COUNT,
        "maximum_private_bytes": MAX_PRIVATE_BYTES, "maximum_summary_bytes": MAX_SUMMARY_BYTES,
        "maximum_runtime_seconds": MAX_RUNTIME_SECONDS,
        "deadline_qualification": "checks_do_not_interrupt_native_uninterruptible_IO_or_host_suspension",
        "one_use": "one_instance_only_not_a_durable_cross_job_attempt_fence",
        "QC_private_book": "opaque_in_QC_memory_no_public_raw_serializer_or_ObjectStore_write",
        "future_publication": "requires_separate_exact_paid_org_private_project_namespace_and_run_protocol",
        "execution": "no_order_identity_and_source_availability_exception_not_strategy_performance",
        **FALSE_FLAGS}


def _qc_ny(value):
    # QC algorithm/data timezones are checked NY before this explicit treatment
    # of the platform's naive local DateTime representation.
    require(isinstance(value, datetime), "native_metadata")
    require(value.tzinfo is None or value.utcoffset() is not None, "native_metadata")
    return value.replace(tzinfo=NY) if value.tzinfo is None else value.astimezone(NY)


def _native(symbol):
    try:
        sid, ticker, kind, market = figi._symbol_identity(symbol, "native source")
        date_value = symbol.id.date
        require(isinstance(date_value, datetime), "native_metadata")
        return {"sid": sid, "display": ticker, "kind": kind, "market": market,
            "sid_date": date_value.date().isoformat()}
    except Refused:
        raise
    except Exception:
        raise Refused("native_metadata") from None


def _price(value):
    try:
        text = str(value)
        if len(text) > MAX_PRICE_TEXT:
            return None
        number = money._decimal(value, "native RAW close", positive=True)
        if len(number.as_tuple().digits) > MAX_PRICE_TEXT or abs(number.adjusted()) > MAX_PRICE_TEXT:
            return None
        text = money._decimal_text(number)
        return text if 0 < len(text) <= MAX_PRICE_TEXT else None
    except Exception:
        return None


class PrivateNativeBook:
    """Opaque QC-local book; never log, pickle or move it to host transport."""
    __slots__ = ("_raw", "sha256", "byte_count")

    def __init__(self, record):
        raw = canonical(record)
        require(0 < len(raw) <= MAX_PRIVATE_BYTES, "private_bound")
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "sha256", hashlib.sha256(raw).hexdigest())
        object.__setattr__(self, "byte_count", len(raw))

    def __setattr__(self, name, value):
        raise TypeError("QC-local native book is immutable")

    def __repr__(self):
        return "<PrivateNativeBook QC-local RAW data redacted; no export interface>"

    def __reduce_ex__(self, protocol):
        raise TypeError("QC-local native book cannot enter host serialization")


class NativePriceSourceDiagnostic:
    def __init__(self, algorithm, *, specification, expected_specification_sha256,
                 activation_manifest_key, activation_manifest_sha256, activation_manifest_byte_count,
                 benchmark_symbol, etf_symbols, trade_bar_type, daily_resolution, raw_normalization):
        checked = validate_specification(specification)
        require(_hash(expected_specification_sha256)
            and digest(checked) == expected_specification_sha256
            and activation_manifest_sha256 == ACTIVATION_SHA256
            and type(activation_manifest_byte_count) is int and activation_manifest_byte_count > 0,
            "specification")
        require(type(etf_symbols) is dict and tuple(etf_symbols) == UNIVERSES, "own_ETF")
        self.algorithm, self.specification = algorithm, checked
        self.specification_sha256 = expected_specification_sha256
        self.activation = (activation_manifest_key, activation_manifest_sha256, activation_manifest_byte_count)
        self.benchmark, self.etfs = benchmark_symbol, dict(etf_symbols)
        self.trade_type, self.daily, self.raw = trade_bar_type, daily_resolution, raw_normalization
        self.started, self.deadline, self.static_snapshot = False, None, None
        self.forward_census, self.forward_census_sha256 = None, None

    def _remaining(self):
        require(self.deadline is not None and clock.monotonic() < self.deadline, "deadline")

    def _no_orders(self):
        try:
            require(self.algorithm.live_mode is False, "orders")
            require(next(iter(self.algorithm.transactions.get_orders()), None) is None, "orders")
            for index, (_, holding) in enumerate(self.algorithm.portfolio.items()):
                require(index < MAX_PORTFOLIO_ROWS
                    and money._decimal(holding.quantity, "native source holding") == 0, "orders")
        except Refused:
            raise
        except Exception:
            raise Refused("orders") from None

    def _package(self):
        try:
            package = inputs.load_accepted_risk_preliminary_package(self.algorithm,
                activation_manifest_key=self.activation[0],
                activation_manifest_sha256=self.activation[1],
                activation_manifest_byte_count=self.activation[2])
            require(package.package_sha256 == PACKAGE_SHA256
                and package.activation_manifest_sha256 == ACTIVATION_SHA256, "package")
            rows = package.runtime_symbol_bindings
            require(type(rows) is tuple and len(rows) == EXPECTED_BINDINGS
                and inputs._stream_hash(rows) == BINDING_STREAM_SHA256, "catalog")
            axis = tuple(package.evaluator_input.session_axis)
            require(len(axis) == EXPECTED_AXIS_COUNT and tuple(sorted(set(axis))) == axis
                and digest(list(axis)) == AXIS_SHA256, "axis")
            sessions = tuple(value for value in axis if FIRST_SESSION <= value <= LAST_SESSION)
            require(len(sessions) == EXPECTED_SESSION_COUNT and sessions[0] == FIRST_SESSION
                and sessions[-1] == LAST_SESSION, "axis")
            lineage = dict(package.evaluator_input.source_lineage_sha256s)
            require(lineage["security_master_admission_sha256"] == ADMISSION_SHA256, "package")
            return package, rows, axis, sessions
        except Refused:
            raise
        except Exception:
            raise Refused("package") from None

    def _static_securities(self):
        require(tuple(self.etfs) == UNIVERSES, "own_ETF")
        result = {}
        try:
            for ticker, symbol in self.etfs.items():
                native = _native(symbol)
                require(native["display"] == ticker and native["kind"] in ("equity", "securitytype.equity")
                    and native["market"] == "usa" and native["sid"] not in result, "own_ETF")
                security = self.algorithm.securities[symbol]
                require(security.quote_currency.symbol == "USD"
                    and str(security.exchange.hours.time_zone) == "America/New_York", "own_ETF")
                result[native["sid"]] = ticker
            require(_native(self.benchmark)["sid"] == _native(self.etfs["SPY"])["sid"], "own_ETF")
        except Refused:
            raise
        except Exception:
            raise Refused("own_ETF") from None
        return result

    def _resolve_with_census(self, rows):
        """Retain bounded forward observations before the frozen resolver filters.

        Reverse Symbol calls and returned values pass through unchanged. This
        is one resolver traversal, not a second lookup or an alias mechanism.
        """
        expected = {row["composite_figi"]: (index, digest(row)) for index, row in enumerate(rows)}
        require(len(expected) == EXPECTED_BINDINGS, "catalog")
        observed = {}

        def observe(value):
            self._remaining()
            if type(value) is not str:
                return self.algorithm.composite_figi(value)
            require(value in expected and value not in observed, "resolution")
            result = self.algorithm.composite_figi(value)
            native_sid, state = None, "unavailable"
            if result is not None:
                try:
                    native_sid, _, kind, market = figi._symbol_identity(result, "native forward census")
                    state = ("known_US_equity" if kind in ("equity", "securitytype.equity")
                        and market == "usa" else "known_incompatible")
                except Exception:
                    state = "unreadable"
            ordinal, binding_pin = expected[value]
            observed[value] = {"binding_ordinal": ordinal, "whole_binding_sha256": binding_pin,
                "native_sid": native_sid, "state": state}
            return result

        resolution = figi.resolve_preliminary_qc_figis(rows,
            expected_security_master_admission_sha256=ADMISSION_SHA256,
            composite_figi=observe, benchmark_symbol=self.benchmark)
        require(set(observed) == set(expected) and len(observed) == EXPECTED_BINDINGS, "resolution")
        census = sorted(observed.values(), key=lambda row: row["binding_ordinal"])
        self.forward_census = json.loads(canonical(census))
        self.forward_census_sha256 = digest(census)
        return resolution

    def _schedule(self, sessions):
        schedule = []
        try:
            hours = self.algorithm.securities[self.etfs["SPY"]].exchange.hours
            for session in sessions:
                self._remaining()
                midnight = datetime.strptime(session, "%Y-%m-%d")
                opening = _qc_ny(hours.get_next_market_open(midnight, False))
                closing = _qc_ny(hours.get_next_market_close(opening.replace(tzinfo=None), False))
                require(opening.date().isoformat() == closing.date().isoformat() == session
                    and opening.time().replace(tzinfo=None) == time(9, 30)
                    and opening < closing <= opening.replace(hour=16, minute=0), "calendar")
                schedule.append({"session": session,
                    "open_utc": opening.astimezone(timezone.utc).isoformat(),
                    "close_utc": closing.astimezone(timezone.utc).isoformat()})
            require(digest(schedule) == SCHEDULE_SHA256, "calendar")
        except Refused:
            raise
        except Exception:
            raise Refused("calendar") from None
        return schedule

    def _configure(self, symbol, schedule):
        try:
            before = _native(symbol)
            security = self.algorithm.add_security(symbol, self.daily, False, 1, False)
            security.set_data_normalization_mode(self.raw)
            require(_native(security.symbol) == before
                and security.quote_currency.symbol == "USD"
                and money._decimal(security.quote_currency.conversion_rate, "native USD rate") == 1,
                "currency")
            require(str(security.exchange.hours.time_zone) == "America/New_York"
                and security.data_normalization_mode == self.raw, "subscription")
            trade, quote = 0, 0
            for index, config in enumerate(security.subscriptions):
                require(index < 2 and _native(config.symbol)["sid"] == before["sid"]
                    and config.resolution == self.daily and config.fill_data_forward is False
                    and config.extended_market_hours is False and config.data_normalization_mode == self.raw
                    and str(config.data_time_zone) == str(config.exchange_time_zone) == "America/New_York",
                    "subscription")
                name = config.type.FullName
                require(name in ("QuantConnect.Data.Market.TradeBar", "QuantConnect.Data.Market.QuoteBar"), "subscription")
                trade += int(name == "QuantConnect.Data.Market.TradeBar")
                quote += int(name == "QuantConnect.Data.Market.QuoteBar")
            require(trade == 1 and quote <= 1, "subscription")
            for item in schedule:
                self._remaining()
                midnight = datetime.strptime(item["session"], "%Y-%m-%d")
                opening = _qc_ny(security.exchange.hours.get_next_market_open(midnight, False))
                closing = _qc_ny(security.exchange.hours.get_next_market_close(opening.replace(tzinfo=None), False))
                require(opening.astimezone(timezone.utc).isoformat() == item["open_utc"]
                    and closing.astimezone(timezone.utc).isoformat() == item["close_utc"], "calendar")
            return before
        except Refused:
            raise
        except Exception:
            raise Refused("subscription") from None

    def _capture(self, symbol, schedule):
        stats = {"status": "lookup_failed", "call_invoked": False, "batch_count": 0,
            "payload_count": 0, "invalid_row_counts": {}, "duplicate_payload_count": 0}
        cells, seen, blocked, invalid = {}, set(), set(), Counter()
        positions = {item["session"]: index for index, item in enumerate(schedule)}
        native_sid = _native(symbol)["sid"]
        try:
            typed = self.algorithm.history[self.trade_type]
            if not callable(typed):
                return stats, cells, seen, blocked
        except Exception:
            return stats, cells, seen, blocked
        stats["call_invoked"] = True
        try:
            response = typed([symbol], datetime.strptime(FIRST_SESSION, "%Y-%m-%d"),
                datetime.strptime(LAST_SESSION, "%Y-%m-%d") + timedelta(days=1), self.daily,
                fill_forward=False, extended_market_hours=False, data_normalization_mode=self.raw)
        except Exception:
            stats["status"] = "call_failed"
            return stats, cells, seen, blocked
        stats["status"] = "complete"
        try:
            for index, batch in enumerate(response):
                self._remaining()
                if index >= len(schedule):
                    stats["status"] = "bound_exceeded"
                    break
                stats["batch_count"] += 1
                entries = iter(batch.items())
                first = next(entries, None)
                require(first is not None and next(entries, None) is None, "summary")
                key, bar = first
                stats["payload_count"] += 1
                position, reason, text = None, None, None
                try:
                    if not isinstance(bar, self.trade_type) or bar.GetType().FullName != "QuantConnect.Data.Market.TradeBar":
                        reason = "bar_type"
                    elif _native(key)["sid"] != native_sid or _native(bar.symbol)["sid"] != native_sid:
                        reason = "identity"
                    else:
                        opening, closing, group = _qc_ny(bar.time), _qc_ny(bar.end_time), _qc_ny(batch.time)
                        position = positions.get(opening.date().isoformat())
                        if position is None:
                            reason = "session"
                        else:
                            item = schedule[position]
                            if opening.astimezone(timezone.utc).isoformat() != item["open_utc"] \
                                    or closing.astimezone(timezone.utc).isoformat() != item["close_utc"] or group != closing:
                                reason = "time"
                            elif bar.period.total_seconds() != (closing - opening).total_seconds():
                                reason = "period"
                            elif bar.is_fill_forward is not False:
                                reason = "fill_forward"
                            else:
                                text = _price(bar.close)
                                if text is None:
                                    reason = "price"
                except Exception:
                    reason = "unreadable"
                if position is not None:
                    if position in seen:
                        blocked.add(position); cells.pop(position, None)
                        stats["duplicate_payload_count"] += 1
                    seen.add(position)
                    if reason:
                        blocked.add(position); cells.pop(position, None)
                    elif position not in blocked:
                        cells[position] = text
                if reason:
                    invalid[reason] += 1
        except Refused as error:
            if finite(error) == "deadline":
                raise
            invalid["batch_shape"] += 1
            stats["status"] = "read_failed"
        except Exception:
            stats["status"] = "read_failed"
        stats["invalid_row_counts"] = dict(sorted(invalid.items()))
        return stats, cells, seen, blocked

    def _postcheck(self, package, resolution, start_clock, pairs):
        require(package.package_sha256 == PACKAGE_SHA256
            and package.activation_manifest_sha256 == ACTIVATION_SHA256
            and inputs._stream_hash(package.runtime_symbol_bindings) == BINDING_STREAM_SHA256
            and digest(list(package.evaluator_input.session_axis)) == AXIS_SHA256
            and dict(package.evaluator_input.source_lineage_sha256s)["security_master_admission_sha256"] == ADMISSION_SHA256
            and _qc_ny(self.algorithm.time) == start_clock
            and digest(self.specification) == self.specification_sha256
            and digest(self.forward_census) == self.forward_census_sha256
            and self._static_securities() == self.static_snapshot
            and all(_native(symbol) == native for symbol, native in pairs if symbol is not None),
            "source_changed")
        try:
            figi.require_preliminary_qc_figi_resolution(resolution)
        except Exception:
            raise Refused("source_changed") from None
        self._remaining()
        self._no_orders()

    def _finish(self, *, resolution, selected, schedule, records, static_collisions, identity_phase):
        required = EXPECTED_SESSION_COUNT * SELECTED_COUNT
        public_rows, private_rows = [], []
        for ordinal, (row, symbol, native, observation) in enumerate(records):
            stats, cells, seen, blocked = observation
            unseen = set(range(EXPECTED_SESSION_COUNT)) - seen
            public_rows.append({"ordinal": ordinal, "whole_binding_sha256": digest(row),
                "native_sid_sha256": None if native is None else digest({"sid": native["sid"]}),
                **stats, "valid_cell_count": len(cells),
                "unpriced_cell_count": EXPECTED_SESSION_COUNT - len(cells),
                "invalid_or_duplicate_cell_count": len(blocked),
                "absent_cell_count": len(unseen) if stats["status"] == "complete" else None,
                "failure_unknown_cell_count": len(unseen) if stats["status"] != "complete" else 0})
            private_rows.append({"ordinal": ordinal, "original_binding": row,
                "native": native, "status": stats["status"],
                "raw_USD_closes": [[index, text] for index, text in sorted(cells.items())],
                "unpriced_cells": [[index, "invalid_or_duplicate" if index in blocked else
                    "absent" if stats["status"] == "complete" else "failure_unknown"]
                    for index in range(EXPECTED_SESSION_COUNT) if index not in cells]})
        private = PrivateNativeBook({"schema": PRIVATE_SCHEMA,
            "specification_sha256": self.specification_sha256, "package_sha256": PACKAGE_SHA256,
            "resolution_sha256": resolution.resolution_sha256, "session_schedule": schedule,
            "price_units": "RAW_unadjusted_USD_per_share_not_executable_quotes",
            "identity_phase": identity_phase, "selected": private_rows,
            "forward_sid_census": self.forward_census})
        forward_states = {state: sum(row["state"] == state for row in self.forward_census)
            for state in sorted(FORWARD_STATES)}
        known_sid_counts = Counter(row["native_sid"] for row in self.forward_census if row["native_sid"] is not None)
        known_count = sum(known_sid_counts.values())
        summary = {"schema": SCHEMA, "purpose": "QC_only_exact_five_original_identity_and_RAW_availability",
            "specification_sha256": self.specification_sha256, "package_sha256": PACKAGE_SHA256,
            "binding_stream_sha256": BINDING_STREAM_SHA256, "ordered_full_axis_sha256": AXIS_SHA256,
            "NYSE_schedule_sha256": SCHEDULE_SHA256, "calendar_source_sha256": CALENDAR_SOURCE_SHA256,
            "input_binding_count": resolution.input_row_count, "resolved_count": resolution.resolved_count,
            "named_refusal_count": resolution.named_refusal_count, "resolution_sha256": resolution.resolution_sha256,
            "own_ETF_count": len(self.etfs), "full_catalog_own_ETF_collision_count": static_collisions,
            "forward_observation_count": len(self.forward_census), "forward_state_counts": forward_states,
            "forward_known_SID_count": known_count,
            "forward_unknown_SID_count": len(self.forward_census) - known_count,
            "forward_duplicate_SID_identity_count": sum(count for count in known_sid_counts.values() if count > 1),
            "forward_census_sha256": self.forward_census_sha256,
            "identity_phase": identity_phase, "selected_count": SELECTED_COUNT,
            "requested_session_count": EXPECTED_SESSION_COUNT, "required_cell_count": required,
            "explicit_history_calls": sum(row["call_invoked"] for row in public_rows),
            "enumeration_complete_count": sum(row["status"] == "complete" for row in public_rows),
            "valid_cell_count": sum(row["valid_cell_count"] for row in public_rows),
            "unpriced_cell_count": sum(row["unpriced_cell_count"] for row in public_rows),
            "private_book_byte_count": private.byte_count, "private_book_sha256": private.sha256,
            "per_selected": public_rows, **FALSE_FLAGS}
        return validate_summary(summary), private

    def prepare(self):
        require(not self.started, "once")
        self.started = True
        self.deadline = clock.monotonic() + MAX_RUNTIME_SECONDS
        self._no_orders()
        try:
            require(str(self.algorithm.time_zone) == "America/New_York"
                and self.algorithm.account_currency == "USD", "settings")
            require(self.algorithm.settings.daily_precise_end_time is True
                and self.algorithm.settings.seed_initial_prices is False, "settings")
            start_clock = _qc_ny(self.algorithm.time)
            require(start_clock >= datetime.strptime(LAST_SESSION, "%Y-%m-%d").replace(tzinfo=NY)
                + timedelta(days=1), "clock")
            package, rows, axis, sessions = self._package()
            self._remaining()
            resolution = self._resolve_with_census(rows)
            figi.require_preliminary_qc_figi_resolution(resolution)
            require(resolution.input_row_count == EXPECTED_BINDINGS
                and resolution.resolved_count + resolution.named_refusal_count == EXPECTED_BINDINGS, "resolution")
            static = self._static_securities()
            self.static_snapshot = dict(static)
            collisions = sum(row["native_sid"] in static for row in self.forward_census
                if row["native_sid"] is not None)
            lookup = {digest(row): row for row in rows}
            chosen = self.specification["selected_whole_binding_sha256s"]
            require(len(lookup) == EXPECTED_BINDINGS and all(pin in lookup for pin in chosen), "catalog")
            selected = [lookup[pin] for pin in chosen]
            schedule = self._schedule(sessions)
            symbols = [resolution.symbol_for_security(row["security_id"]) for row in selected]
            records = []
            if collisions or any(symbol is None for symbol in symbols):
                for row, symbol in zip(selected, symbols, strict=True):
                    records.append((row, symbol, None if symbol is None else _native(symbol),
                        ({"status": "not_dispatched_identity_refusal", "call_invoked": False,
                            "batch_count": 0, "payload_count": 0, "invalid_row_counts": {},
                            "duplicate_payload_count": 0}, {}, set(), set())))
                self._postcheck(package, resolution, start_clock, [(symbol, native) for _, symbol, native, _ in records])
                return self._finish(resolution=resolution, selected=selected, schedule=schedule,
                    records=records, static_collisions=collisions, identity_phase="refused")
            natives = [self._configure(symbol, schedule) for symbol in symbols]
            self._no_orders()
            for row, symbol, native in zip(selected, symbols, natives, strict=True):
                self._remaining()
                observation = self._capture(symbol, schedule)
                records.append((row, symbol, native, observation))
                self._no_orders()
            self._postcheck(package, resolution, start_clock, list(zip(symbols, natives, strict=True)))
            return self._finish(resolution=resolution, selected=selected, schedule=schedule,
                records=records, static_collisions=0, identity_phase="observed")
        except Refused:
            raise
        except Exception:
            raise Refused("resolution") from None


def validate_summary(value):
    keys = {"schema", "purpose", "specification_sha256", "package_sha256",
        "binding_stream_sha256", "ordered_full_axis_sha256", "NYSE_schedule_sha256",
        "calendar_source_sha256", "input_binding_count", "resolved_count", "named_refusal_count",
        "resolution_sha256", "own_ETF_count", "full_catalog_own_ETF_collision_count",
        "forward_observation_count", "forward_state_counts", "forward_known_SID_count",
        "forward_unknown_SID_count", "forward_duplicate_SID_identity_count", "forward_census_sha256",
        "identity_phase", "selected_count", "requested_session_count", "required_cell_count",
        "explicit_history_calls", "enumeration_complete_count", "valid_cell_count", "unpriced_cell_count",
        "private_book_byte_count", "private_book_sha256", "per_selected", *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value["schema"] == SCHEMA
        and value["purpose"] == "QC_only_exact_five_original_identity_and_RAW_availability"
        and all(value[key] is False for key in FALSE_FLAGS)
        and value["package_sha256"] == PACKAGE_SHA256
        and value["binding_stream_sha256"] == BINDING_STREAM_SHA256
        and value["ordered_full_axis_sha256"] == AXIS_SHA256
        and value["NYSE_schedule_sha256"] == SCHEDULE_SHA256
        and value["calendar_source_sha256"] == CALENDAR_SOURCE_SHA256
        and _hash(value["specification_sha256"]) and _hash(value["resolution_sha256"])
        and _hash(value["forward_census_sha256"])
        and _hash(value["private_book_sha256"])
        and type(value["private_book_byte_count"]) is int
        and 0 < value["private_book_byte_count"] <= MAX_PRIVATE_BYTES, "summary")
    for key in ("input_binding_count", "resolved_count", "named_refusal_count", "own_ETF_count",
            "full_catalog_own_ETF_collision_count", "selected_count", "requested_session_count",
            "forward_observation_count", "forward_known_SID_count", "forward_unknown_SID_count",
            "forward_duplicate_SID_identity_count",
            "required_cell_count", "explicit_history_calls", "enumeration_complete_count",
            "valid_cell_count", "unpriced_cell_count"):
        require(type(value[key]) is int and value[key] >= 0, "summary")
    require(value["input_binding_count"] == EXPECTED_BINDINGS
        and value["resolved_count"] + value["named_refusal_count"] == EXPECTED_BINDINGS
        and value["own_ETF_count"] == len(UNIVERSES) and value["selected_count"] == SELECTED_COUNT
        and value["full_catalog_own_ETF_collision_count"] <= value["forward_known_SID_count"]
        and value["forward_observation_count"] == EXPECTED_BINDINGS
        and value["forward_known_SID_count"] + value["forward_unknown_SID_count"] == EXPECTED_BINDINGS
        and 0 <= value["forward_duplicate_SID_identity_count"] <= value["forward_known_SID_count"]
        and value["forward_duplicate_SID_identity_count"] != 1
        and type(value["forward_state_counts"]) is dict
        and set(value["forward_state_counts"]) == FORWARD_STATES
        and all(type(count) is int and count >= 0 for count in value["forward_state_counts"].values())
        and sum(value["forward_state_counts"].values()) == EXPECTED_BINDINGS
        and value["forward_state_counts"]["known_US_equity"] + value["forward_state_counts"]["known_incompatible"]
            == value["forward_known_SID_count"]
        and value["forward_state_counts"]["unavailable"] + value["forward_state_counts"]["unreadable"]
            == value["forward_unknown_SID_count"]
        and value["requested_session_count"] == EXPECTED_SESSION_COUNT
        and value["required_cell_count"] == SELECTED_COUNT * EXPECTED_SESSION_COUNT
        and value["identity_phase"] in ("observed", "refused")
        and type(value["per_selected"]) is list and len(value["per_selected"]) == SELECTED_COUNT, "summary")
    row_keys = {"ordinal", "whole_binding_sha256", "native_sid_sha256", "status", "call_invoked",
        "batch_count", "payload_count", "invalid_row_counts", "duplicate_payload_count",
        "valid_cell_count", "unpriced_cell_count", "invalid_or_duplicate_cell_count",
        "absent_cell_count", "failure_unknown_cell_count"}
    pins, native_pins = [], []
    for index, row in enumerate(value["per_selected"]):
        require(type(row) is dict and set(row) == row_keys and type(row["ordinal"]) is int
            and row["ordinal"] == index and _hash(row["whole_binding_sha256"])
            and (row["native_sid_sha256"] is None or _hash(row["native_sid_sha256"]))
            and type(row["status"]) is str and row["status"] in STATUSES
            and type(row["call_invoked"]) is bool
            and type(row["invalid_row_counts"]) is dict
            and set(row["invalid_row_counts"]) <= ROW_REASONS
            and all(type(n) is int and n > 0 for n in row["invalid_row_counts"].values()), "summary")
        for key in ("batch_count", "payload_count", "duplicate_payload_count", "valid_cell_count",
                "unpriced_cell_count", "invalid_or_duplicate_cell_count", "failure_unknown_cell_count"):
            require(type(row[key]) is int and 0 <= row[key] <= EXPECTED_SESSION_COUNT, "summary")
        require(row["valid_cell_count"] + row["unpriced_cell_count"] == EXPECTED_SESSION_COUNT
            and row["invalid_or_duplicate_cell_count"] <= row["unpriced_cell_count"]
            and row["payload_count"] <= row["batch_count"]
            and row["valid_cell_count"] + row["invalid_or_duplicate_cell_count"] <= row["payload_count"]
            and row["duplicate_payload_count"] <= row["payload_count"]
            and sum(row["invalid_row_counts"].values()) <= row["payload_count"] + 1, "summary")
        if row["status"] == "complete":
            require(type(row["absent_cell_count"]) is int
                and row["absent_cell_count"] == row["unpriced_cell_count"] - row["invalid_or_duplicate_cell_count"]
                and row["failure_unknown_cell_count"] == 0, "summary")
        else:
            require(row["absent_cell_count"] is None
                and row["failure_unknown_cell_count"] == row["unpriced_cell_count"] - row["invalid_or_duplicate_cell_count"], "summary")
        if row["status"] in ("lookup_failed", "not_dispatched_identity_refusal"):
            require(row["call_invoked"] is False and row["batch_count"] == row["payload_count"] == 0, "summary")
        else:
            require(row["call_invoked"] is True, "summary")
        if row["status"] in ("lookup_failed", "call_failed", "not_dispatched_identity_refusal"):
            require(row["batch_count"] == row["payload_count"] == row["valid_cell_count"]
                == row["invalid_or_duplicate_cell_count"] == row["duplicate_payload_count"] == 0
                and not row["invalid_row_counts"], "summary")
        pins.append(row["whole_binding_sha256"])
        if row["native_sid_sha256"] is not None:
            native_pins.append(row["native_sid_sha256"])
    require(pins == sorted(set(pins))
        and len(native_pins) == len(set(native_pins))
        and value["valid_cell_count"] == sum(row["valid_cell_count"] for row in value["per_selected"])
        and value["unpriced_cell_count"] == sum(row["unpriced_cell_count"] for row in value["per_selected"])
        and value["explicit_history_calls"] == sum(row["call_invoked"] for row in value["per_selected"])
        and value["enumeration_complete_count"] == sum(row["status"] == "complete" for row in value["per_selected"])
        and value["valid_cell_count"] + value["unpriced_cell_count"] == value["required_cell_count"], "summary")
    if value["identity_phase"] == "refused":
        require(value["explicit_history_calls"] == value["valid_cell_count"] == 0
            and all(row["status"] == "not_dispatched_identity_refusal" for row in value["per_selected"]), "summary")
    else:
        require(value["full_catalog_own_ETF_collision_count"] == 0
            and all(row["native_sid_sha256"] is not None
                and row["status"] != "not_dispatched_identity_refusal" for row in value["per_selected"]), "summary")
    require(len(canonical(value)) <= MAX_SUMMARY_BYTES, "summary")
    return json.loads(canonical(value))
