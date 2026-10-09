"""One explicitly executed hosted QC Research cell; counts only, not a backtest.

Paste this entire file into one hosted Research cell. Imports are inert. Ordinary
Python execution refuses before QuantBook construction. No HTTP, credentials,
files, ObjectStore, platform export, orders, or economic bar fields are used.
The host/operator must register the exact source bytes before executing once;
the in-kernel guard is not durable across kernel resets.

Official API signatures checked 2026-10-07:
https://www.lean.io/docs/v2/lean-engine/class-reference/py/QuantConnect/Research/QuantBook/
https://www.quantconnect.com/docs/v2/research-environment/datasets/us-equity
https://www.quantconnect.com/docs/v2/research-environment/initialization
CIK/date -> all native Symbols; add_security(Symbol) preserves identity;
history[T](Symbol,start,end,...) supplies typed objects rather than a DataFrame.
This explicit regular-hours access profile is NOT canonical study-clock parity.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import json


PROFILE = "insider-qc-native-access-count-probe-v1"
SOURCE_CIK = 2178
SOURCE_PARENT_SHA256 = "5593bead9d1829f26c8d88ccd20472eeb95896cd3e1856be56ddc0c84f0d47cf"
SOURCE_ACCESSION = "0000002178-22-000091"
SOURCE_FILING_DATE = "2022-11-17"
START = datetime(2022, 11, 16)
END = datetime(2022, 11, 17)
MAX_CANDIDATES = 4
MAX_BARS_PER_SERIES = 1440
# A second paste/rerun of this whole cell must not rearm native processing.
# Kernel reset remains an external journal/operator boundary, not a durable seal.
_HOSTED_RUN_STARTED = globals().get("_HOSTED_RUN_STARTED", False)


@dataclass(frozen=True)
class TestNativeAPI:
    """Invented-test seam only; injected results can never claim native access."""

    __test__ = False
    quantbook_factory: object
    symbol_type: type
    equity_security_type: object
    trade_bar_type: type
    quote_bar_type: type
    minute_resolution: object
    raw_normalization: object


class _Refusal(Exception):
    pass


def _hosted_notebook():
    try:
        from IPython import get_ipython
        return getattr(get_ipython(), "kernel", None) is not None
    except ImportError:
        return False


def _hosted_api():
    # Lazy imports only after an explicit call in a notebook kernel. Authentication
    # and authorization are external owner facts, not inferred from these imports.
    from QuantConnect.Research import QuantBook
    from QuantConnect import Symbol, SecurityType, Resolution, DataNormalizationMode
    from QuantConnect.Data.Market import TradeBar, QuoteBar
    return TestNativeAPI(QuantBook, Symbol, SecurityType.EQUITY, TradeBar,
                         QuoteBar, Resolution.MINUTE, DataNormalizationMode.RAW)


def _summary(synthetic):
    return {
        "profile": PROFILE,
        "execution_mode": "invented-test-only" if synthetic else "hosted-native-research",
        "source": {"issuer_cik": "0000002178", "accession": SOURCE_ACCESSION,
                   "parent_sha256": SOURCE_PARENT_SHA256, "filing_date": SOURCE_FILING_DATE},
        "window": {"start_inclusive": "2022-11-16T00:00:00", "end_exclusive": "2022-11-17T00:00:00",
                   "quantbook_history_frontier": "2022-11-17T00:00:00",
                   "time_zone": "America/New_York", "pre_filing_day_only": True},
        "request_profile": {"resolution": "minute", "normalization": "raw", "fill_forward": False,
                            "stock_extended_market_hours": False, "clock_extended_market_hours": False,
                            "maximum_candidates": MAX_CANDIDATES, "maximum_history_requests": 9,
                            "maximum_bars_per_series": MAX_BARS_PER_SERIES},
        "status": "not-started", "stage": "preflight", "refusal": None,
        "candidate_count_observed": 0, "candidate_count_exact": False,
        "resolver_calls_attempted": 0, "subscriptions_attempted": 0,
        "history_requests_attempted": 0, "history_requests_completed": 0,
        "research_probe_sessions_started": 0, "backtest_launch_attempts": 0,
        "series": [], "native_access_observed": False, "all_requested_series_nonempty": False,
        "claims": {"exact_sec_title_or_share_class_mapping_verified": False,
                   "source_authenticity_verified": False, "historical_mapping_pit_verified": False,
                   "first_listing_provenance_verified": False, "rights_verified": False,
                   "dataset_entitlement_verified": False, "canonical_profile_parity_verified": False,
                   "registered_look_completed": False, "research_ready": False,
                   "backtest_ready": False, "trading_authority": False,
                   "economic_values_evaluated_or_exported": False,
                   "symbol_identifiers_exported": False},
    }


def _candidates(resolved, api, result):
    candidates = []
    for symbol in resolved:
        result["candidate_count_observed"] += 1
        if len(candidates) == MAX_CANDIDATES:
            raise _Refusal("candidate-cardinality-exceeds-four")
        if not isinstance(symbol, api.symbol_type) or symbol.security_type != api.equity_security_type:
            raise _Refusal("resolver-returned-non-equity-symbol")
        if any(symbol == prior for prior in candidates):
            raise _Refusal("resolver-returned-duplicate-symbol")
        candidates.append(symbol)
    result["candidate_count_exact"] = True
    if not candidates:
        raise _Refusal("no-cik-date-candidate")
    return candidates


def _count_bars(bars, symbol, bar_type):
    count, previous = 0, None
    for bar in bars:
        count += 1
        if count > MAX_BARS_PER_SERIES:
            raise _Refusal("history-row-bound-exceeded")
        if not isinstance(bar, bar_type) or bar.symbol != symbol:
            raise _Refusal("history-type-or-symbol-mismatch")
        start, end = bar.time, bar.end_time
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise _Refusal("history-time-metadata-invalid")
        if start.tzinfo is not None or end.tzinfo is not None:
            raise _Refusal("history-time-zone-profile-mismatch")
        if not START <= start < end <= END or end - start != timedelta(minutes=1):
            raise _Refusal("history-outside-fixed-minute-window")
        if previous is not None and start <= previous:
            raise _Refusal("history-duplicate-or-reordered-time")
        if type(bar.is_fill_forward) is not bool or bar.is_fill_forward:
            raise _Refusal("history-fill-forward-refused")
        previous = start
        del bar
    return count


def _history(qb, api, symbol, bar_type, role, ordinal, result):
    result["stage"] = role + "-history"
    result["history_requests_attempted"] += 1
    bars = qb.history[bar_type](
        symbol, START, END, resolution=api.minute_resolution,
        fill_forward=False, extended_market_hours=False,
        data_normalization_mode=api.raw_normalization,
    )
    count = _count_bars(bars, symbol, bar_type)
    result["history_requests_completed"] += 1
    result["series"].append({"role": role, "candidate_ordinal": ordinal,
                             "bar_count": count, "nonempty": count > 0})


def run_explicit(*, _test_native_api=None):
    """Run one fixed count diagnostic. Never returns native Symbols or bar data.

    A supplied TestNativeAPI is always identified as invented test evidence.
    Failure stops the remaining requests; there is no retry or widened fallback.
    All candidates are retained and checked, not resolved to one assumed class.
    """
    global _HOSTED_RUN_STARTED
    synthetic = _test_native_api is not None
    result = _summary(synthetic)
    try:
        if synthetic:
            if type(_test_native_api) is not TestNativeAPI:
                raise _Refusal("invalid-test-native-api")
            api = _test_native_api
        else:
            if not _hosted_notebook():
                raise _Refusal("hosted-research-notebook-required")
            if _HOSTED_RUN_STARTED is not False:
                raise _Refusal("hosted-probe-already-started-in-this-kernel")
            _HOSTED_RUN_STARTED = True
            api = _hosted_api()
        result["stage"] = "quantbook-construction"
        result["research_probe_sessions_started"] = 0 if synthetic else 1
        qb = api.quantbook_factory()
        qb.set_time_zone("America/New_York")
        # In Research, start_date is the LATEST history frontier, not this
        # request's first day. END permits all Nov16 bars without admitting any
        # Nov17 bar. The CIK resolver below still uses START exactly.
        qb.set_start_date(2022, 11, 17)
        result["stage"] = "cik-date-resolution"
        result["resolver_calls_attempted"] += 1
        candidates = _candidates(qb.cik(SOURCE_CIK, trading_date=START), api, result)
        for ordinal, symbol in enumerate(candidates, 1):
            result["stage"] = "source-symbol-subscription"
            result["subscriptions_attempted"] += 1
            security = qb.add_security(symbol, resolution=api.minute_resolution,
                fill_forward=False, extended_market_hours=False,
                data_normalization_mode=api.raw_normalization)
            if security.symbol != symbol:
                raise _Refusal("subscription-changed-native-symbol")
            _history(qb, api, symbol, api.trade_bar_type, "source-trade", ordinal, result)
            _history(qb, api, symbol, api.quote_bar_type, "source-quote", ordinal, result)
        result["stage"] = "fixed-clock-subscription"
        result["subscriptions_attempted"] += 1
        clock = qb.add_equity("SPY", resolution=api.minute_resolution,
            fill_forward=False, extended_market_hours=False,
            data_normalization_mode=api.raw_normalization).symbol
        if not isinstance(clock, api.symbol_type) or clock.security_type != api.equity_security_type:
            raise _Refusal("clock-symbol-invalid")
        if any(clock == symbol for symbol in candidates):
            raise _Refusal("source-candidate-equals-clock")
        _history(qb, api, clock, api.trade_bar_type, "fixed-clock-trade", None, result)
        result["status"] = "completed-count-diagnostic"
        result["stage"] = "complete"
        result["all_requested_series_nonempty"] = all(row["nonempty"] for row in result["series"])
        result["native_access_observed"] = not synthetic and result["all_requested_series_nonempty"]
    except _Refusal as exc:
        result["status"], result["refusal"] = "refused", str(exc)
    except Exception:
        # Native exception messages/tracebacks can contain identifiers or values.
        result["status"], result["refusal"] = "refused", "native-api-or-metadata-error"
    return result


if __name__ == "__main__":
    print(json.dumps(run_explicit(), sort_keys=True, separators=(",", ":")))
