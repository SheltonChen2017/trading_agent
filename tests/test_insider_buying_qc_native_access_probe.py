"""Invented native-object fixtures only; OS process-tree network denial required."""

import ast
import builtins
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import importlib
import json
from types import SimpleNamespace

import pytest

from research import insider_buying_qc_native_access_probe as m


@dataclass(frozen=True)
class Symbol:
    private_identity: int
    security_type: str = "equity"

    def __str__(self):
        raise AssertionError("Never coerce a native Symbol to a ticker")

    @property
    def value(self):
        raise AssertionError("Never access current ticker or economic value")


@dataclass
class Trade:
    symbol: Symbol
    time: datetime
    end_time: datetime
    is_fill_forward: bool = False

    def __getattr__(self, name):
        raise AssertionError("Economic fields must never be accessed: " + name)


@dataclass
class Quote:
    symbol: Symbol
    time: datetime
    end_time: datetime
    is_fill_forward: bool = False

    __getattr__ = Trade.__getattr__


def bars(symbol, cls, count=2):
    return [cls(symbol, datetime(2022, 11, 16, 9, 30) + timedelta(minutes=i),
                datetime(2022, 11, 16, 9, 31) + timedelta(minutes=i)) for i in range(count)]


class History:
    def __init__(self, qb): self.qb = qb
    def __getitem__(self, cls):
        def call(symbol, start, end, **kwargs):
            assert isinstance(symbol, Symbol)
            assert start == m.START and end == m.END
            assert kwargs == {"resolution": "minute", "fill_forward": False,
                              "extended_market_hours": False, "data_normalization_mode": "raw"}
            self.qb.calls.append(("history", symbol, cls))
            if self.qb.fail_history:
                raise RuntimeError("private-economic-value-123456789-and-SID")
            return self.qb.custom_bars(symbol, cls) if self.qb.custom_bars else bars(symbol, cls)
        return call


class Book:
    def __init__(self, candidates=None, custom_bars=None, fail_history=False):
        self.candidates = [Symbol(1)] if candidates is None else candidates
        self.calls, self.custom_bars, self.fail_history = [], custom_bars, fail_history
        self.history = History(self)
    def set_time_zone(self, value):
        assert value == "America/New_York"
        self.calls.append(("time-zone", value))
    def set_start_date(self, *value):
        assert value == (2022, 11, 17)
        self.calls.append(("start-date", value))
    def cik(self, cik, *, trading_date):
        assert cik == 2178 and trading_date == m.START
        assert self.calls[:2] == [("time-zone", "America/New_York"), ("start-date", (2022, 11, 17))]
        self.calls.append(("cik", cik))
        return iter(self.candidates)
    def add_security(self, symbol, **kwargs):
        assert isinstance(symbol, Symbol)
        self._subscription_kwargs(kwargs)
        self.calls.append(("add-security", symbol))
        return SimpleNamespace(symbol=symbol)
    def add_equity(self, ticker, **kwargs):
        assert ticker == "SPY"
        self._subscription_kwargs(kwargs)
        self.calls.append(("clock", ticker))
        return SimpleNamespace(symbol=Symbol(999))
    def _subscription_kwargs(self, kwargs):
        assert kwargs == {"resolution": "minute", "fill_forward": False,
                          "extended_market_hours": False, "data_normalization_mode": "raw"}


def api(book):
    return m.TestNativeAPI(lambda: book, Symbol, "equity", Trade, Quote, "minute", "raw")


def run(book=None):
    book = Book() if book is None else book
    return m.run_explicit(_test_native_api=api(book)), book


def test_import_is_inert_and_has_no_native_import_or_constructor(monkeypatch):
    real_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith(("QuantConnect", "AlgorithmImports")):
            raise AssertionError("Native import on ordinary import")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.reload(m)


def test_fixed_source_bound_identity_one_day_and_counts_only():
    result, book = run()
    assert result["status"] == "completed-count-diagnostic"
    assert result["execution_mode"] == "invented-test-only"
    assert result["candidate_count_exact"] and result["candidate_count_observed"] == 1
    assert result["resolver_calls_attempted"] == 1 and result["subscriptions_attempted"] == 2
    assert result["history_requests_attempted"] == result["history_requests_completed"] == 3
    assert result["research_probe_sessions_started"] == result["backtest_launch_attempts"] == 0
    assert result["all_requested_series_nonempty"] and not result["native_access_observed"]
    assert all(value is False for value in result["claims"].values())
    assert result["source"]["parent_sha256"] == "5593bead9d1829f26c8d88ccd20472eeb95896cd3e1856be56ddc0c84f0d47cf"
    assert result["source"]["filing_date"] == "2022-11-17"
    assert result["window"]["end_exclusive"] == "2022-11-17T00:00:00"
    assert [row["bar_count"] for row in result["series"]] == [2, 2, 2]
    serialized = json.dumps(result)
    assert "private_identity" not in serialized and "999" not in serialized
    assert not any(word in serialized for word in ("open_price", "close_price", "quote_values", "123456789"))
    histories = [call for call in book.calls if call[0] == "history"]
    assert histories[0][1] is book.candidates[0] and histories[1][1] is book.candidates[0]


def test_quantbook_latest_history_frontier_allows_entire_pre_filing_day():
    # Faithful official LEAN frontier behavior: history endpoints later than
    # QuantBook.Time are clipped. Setting its date to START would produce false
    # empty access counts even though these invented pre-filing bars exist.
    class FrontierHistory(History):
        def __getitem__(self, cls):
            original = super().__getitem__(cls)
            def clipped(symbol, start, end, **kwargs):
                observed = original(symbol, start, end, **kwargs)
                return [bar for bar in observed if bar.end_time <= min(end, self.qb.frontier)]
            return clipped
    class FrontierBook(Book):
        def __init__(self):
            super().__init__()
            self.history = FrontierHistory(self)
        def set_start_date(self, *value):
            super().set_start_date(*value)
            self.frontier = datetime(*value)
    result, book = run(FrontierBook())
    assert [row["bar_count"] for row in result["series"]] == [2, 2, 2]
    assert book.frontier == m.END
    assert result["all_requested_series_nonempty"]
    assert result["window"]["start_inclusive"] == "2022-11-16T00:00:00"


def test_all_four_classes_processed_without_silent_first_class_selection():
    result, book = run(Book([Symbol(i) for i in range(1, 5)]))
    assert result["status"] == "completed-count-diagnostic"
    assert result["candidate_count_observed"] == 4 and result["candidate_count_exact"]
    assert result["history_requests_attempted"] == 9 and len(result["series"]) == 9
    assert [row["candidate_ordinal"] for row in result["series"][:-1]] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert [call[1] for call in book.calls if call[0] == "add-security"] == book.candidates


@pytest.mark.parametrize("candidates,refusal,count", [([], "no-cik-date-candidate", 0),
    ([Symbol(i) for i in range(5)], "candidate-cardinality-exceeds-four", 5),
    ([Symbol(1), Symbol(1)], "resolver-returned-duplicate-symbol", 2),
    (["not-a-Symbol"], "resolver-returned-non-equity-symbol", 1),
    ([Symbol(1, "option")], "resolver-returned-non-equity-symbol", 1)])
def test_resolver_refusals_precede_every_subscription(candidates, refusal, count):
    result, book = run(Book(candidates))
    assert result["status"] == "refused" and result["refusal"] == refusal
    assert result["candidate_count_observed"] == count
    assert result["subscriptions_attempted"] == result["history_requests_attempted"] == 0
    assert not result["native_access_observed"]
    assert len(book.calls) == 3


def test_unbounded_resolver_iterable_stops_at_fifth_and_refuses_not_truncates():
    def candidates():
        for i in range(5): yield Symbol(i)
        raise AssertionError("Must not consume unbounded candidate inventory")
    result, _ = run(Book(candidates()))
    assert result["refusal"] == "candidate-cardinality-exceeds-four"
    assert result["candidate_count_observed"] == 5 and not result["candidate_count_exact"]


@pytest.mark.parametrize("change,refusal", [
    ({"symbol": Symbol(77)}, "history-type-or-symbol-mismatch"),
    ({"is_fill_forward": True}, "history-fill-forward-refused"),
    ({"is_fill_forward": 1}, "history-fill-forward-refused"),
    ({"time": datetime(2022, 11, 17), "end_time": datetime(2022, 11, 17, 0, 1)}, "history-outside-fixed-minute-window"),
    ({"time": datetime(2022, 11, 15, 23, 59), "end_time": m.START}, "history-outside-fixed-minute-window"),
    ({"end_time": datetime(2022, 11, 16, 9, 32)}, "history-outside-fixed-minute-window"),
    ({"time": "bad"}, "history-time-metadata-invalid"),
    ({"time": datetime(2022, 11, 16, 9, 30, tzinfo=timezone.utc)}, "history-time-zone-profile-mismatch"),
])
def test_bar_metadata_refusals_stop_without_retry_or_export(change, refusal):
    def changed(symbol, cls):
        result = bars(symbol, cls, 1)
        for key, value in change.items(): setattr(result[0], key, value)
        return result
    result, _ = run(Book(custom_bars=changed))
    assert result["refusal"] == refusal
    assert result["history_requests_attempted"] == 1 and result["history_requests_completed"] == 0
    assert result["series"] == []


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_or_reordered_bar_time_refused(reverse):
    def malformed(symbol, cls):
        result = bars(symbol, cls)
        return list(reversed(result)) if reverse else [result[0], result[0]]
    result, _ = run(Book(custom_bars=malformed))
    assert result["refusal"] == "history-duplicate-or-reordered-time"


def test_row_bound_precedes_infinite_iterator_and_never_reports_coverage():
    def excessive(symbol, cls):
        # Valid minute metadata across one day; cap deliberately reduced only in
        # this isolated negative fixture, not a production admission bypass.
        return bars(symbol, cls, 3)
    original = m.MAX_BARS_PER_SERIES
    try:
        m.MAX_BARS_PER_SERIES = 2
        result, _ = run(Book(custom_bars=excessive))
    finally:
        m.MAX_BARS_PER_SERIES = original
    assert result["refusal"] == "history-row-bound-exceeded"


def test_empty_series_is_completed_access_diagnostic_not_coverage_or_readiness():
    result, _ = run(Book(custom_bars=lambda symbol, cls: [] if cls is Quote else bars(symbol, cls)))
    assert result["status"] == "completed-count-diagnostic"
    assert result["history_requests_completed"] == 3
    assert not result["all_requested_series_nonempty"] and not result["native_access_observed"]
    assert result["series"][1]["bar_count"] == 0


def test_native_failure_is_sanitized_and_not_retried():
    result, book = run(Book(fail_history=True))
    assert result["refusal"] == "native-api-or-metadata-error"
    assert result["history_requests_attempted"] == 1 and result["history_requests_completed"] == 0
    assert "private-economic" not in json.dumps(result) and "123456789" not in json.dumps(result)
    assert len([call for call in book.calls if call[0] == "history"]) == 1


def test_default_local_call_refuses_before_native_import_or_construction(monkeypatch):
    monkeypatch.setattr(m, "_hosted_notebook", lambda: False)
    monkeypatch.setattr(m, "_hosted_api", lambda: pytest.fail("Native API must not be loaded locally"))
    result = m.run_explicit()
    assert result["refusal"] == "hosted-research-notebook-required"
    assert result["research_probe_sessions_started"] == result["resolver_calls_attempted"] == 0


def test_hosted_seam_once_guard_counts_research_separately_no_backtest(monkeypatch):
    book = Book()
    monkeypatch.setattr(m, "_hosted_notebook", lambda: True)
    monkeypatch.setattr(m, "_hosted_api", lambda: api(book))
    monkeypatch.setattr(m, "_HOSTED_RUN_STARTED", False)
    first = m.run_explicit()
    second = m.run_explicit()
    assert first["research_probe_sessions_started"] == 1 and first["native_access_observed"]
    assert first["backtest_launch_attempts"] == 0
    assert second["refusal"] == "hosted-probe-already-started-in-this-kernel"
    assert second["resolver_calls_attempted"] == second["research_probe_sessions_started"] == 0


def test_full_cell_redefinition_preserves_started_kernel_guard():
    # Model a second paste into the same Research kernel without executing QC.
    # Source and globals remain in memory; no native imports/data calls occur.
    import inspect
    namespace = {"__name__": "invented_research_cell", "_HOSTED_RUN_STARTED": True}
    exec(compile(inspect.getsource(m), "<invented-cell-redefinition>", "exec"), namespace)
    assert namespace["_HOSTED_RUN_STARTED"] is True
    namespace["_hosted_notebook"] = lambda: True
    namespace["_hosted_api"] = lambda: pytest.fail("Second cell paste must not load native APIs")
    result = namespace["run_explicit"]()
    assert result["refusal"] == "hosted-probe-already-started-in-this-kernel"
    assert result["resolver_calls_attempted"] == result["research_probe_sessions_started"] == 0


def test_bad_injected_api_refuses_not_native_evidence():
    result = m.run_explicit(_test_native_api=object())
    assert result["refusal"] == "invalid-test-native-api"
    assert result["execution_mode"] == "invented-test-only" and not result["native_access_observed"]


def test_subscription_changed_symbol_stops_before_history():
    book = Book()
    book.add_security = lambda *args, **kwargs: SimpleNamespace(symbol=Symbol(55))
    result, _ = run(book)
    assert result["refusal"] == "subscription-changed-native-symbol"
    assert result["subscriptions_attempted"] == 1 and result["history_requests_attempted"] == 0


def test_wrong_typed_bar_refuses_before_clock_or_next_history():
    result, _ = run(Book(custom_bars=lambda symbol, cls: bars(symbol, Quote if cls is Trade else Trade)))
    assert result["refusal"] == "history-type-or-symbol-mismatch"
    assert result["history_requests_attempted"] == 1


@pytest.mark.parametrize("clock,refusal", [("untyped", "clock-symbol-invalid"),
    (Symbol(8, "option"), "clock-symbol-invalid"), (Symbol(1), "source-candidate-equals-clock")])
def test_invalid_or_source_equal_clock_stops_before_clock_history(clock, refusal):
    book = Book()
    book.add_equity = lambda *args, **kwargs: SimpleNamespace(symbol=clock)
    result, _ = run(book)
    assert result["refusal"] == refusal
    assert result["history_requests_attempted"] == result["history_requests_completed"] == 2


def test_resolver_native_error_sanitized_before_any_subscription():
    book = Book()
    def fail(*args, **kwargs): raise RuntimeError("private-CIK-mapping-and-SID-content")
    book.cik = fail
    result, _ = run(book)
    assert result["refusal"] == "native-api-or-metadata-error"
    assert result["stage"] == "cik-date-resolution"
    assert result["subscriptions_attempted"] == 0
    assert "private-CIK" not in json.dumps(result)


def test_source_has_only_permitted_native_calls_and_no_economic_access():
    # Source inspection is test-only; hosted code never reads its own source/file.
    import inspect
    tree = ast.parse(inspect.getsource(m))
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {"download", "object_store", "read", "write", "save", "open", "close",
                             "bid", "ask", "value", "volume", "portfolio", "market_order", "equity"}
    imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)}
    assert imports == {"json"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in
                   {"open", "eval", "exec", "compile"} for node in ast.walk(tree))
