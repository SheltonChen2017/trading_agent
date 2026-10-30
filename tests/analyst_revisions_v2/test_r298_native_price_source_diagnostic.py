"""Synthetic QC-only source diagnostic tests; no native QC/data/credentials."""
import copy
import json
import pickle
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest

from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as m

NY = ZoneInfo("America/New_York")


class ID:
    def __init__(self, text):
        self.text, self.market, self.date = text, "usa", datetime(2010, 1, 1)

    def __str__(self):
        return self.text


class Symbol:
    def __init__(self, ticker, sid):
        self.value, self.id, self.security_type = ticker, ID(sid), "Equity"


class Hours:
    time_zone = "America/New_York"

    def __init__(self, schedule):
        self.rows = {row["session"]: row for row in schedule}
        self.shift = timedelta(0)

    def get_next_market_open(self, when, extended):
        assert extended is False
        return datetime.fromisoformat(self.rows[when.date().isoformat()]["open_utc"]).astimezone(NY).replace(tzinfo=None) + self.shift

    def get_next_market_close(self, when, extended):
        assert extended is False
        return datetime.fromisoformat(self.rows[when.date().isoformat()]["close_utc"]).astimezone(NY).replace(tzinfo=None) + self.shift


class Security:
    def __init__(self, symbol, hours):
        self.symbol, self.exchange = symbol, NS(hours=hours)
        self.quote_currency = NS(symbol="USD", conversion_rate=Decimal(1))
        self.data_normalization_mode = "RAW"
        self.subscriptions = [NS(symbol=symbol, resolution="Daily", fill_data_forward=False,
            extended_market_hours=False, data_normalization_mode="RAW",
            data_time_zone="America/New_York", exchange_time_zone="America/New_York",
            type=NS(FullName="QuantConnect.Data.Market.TradeBar"))]

    def set_data_normalization_mode(self, value):
        self.data_normalization_mode = value


class Bar:
    def __init__(self, symbol, row):
        self.symbol = symbol
        self.time = datetime.fromisoformat(row["open_utc"]).astimezone(NY).replace(tzinfo=None)
        self.end_time = datetime.fromisoformat(row["close_utc"]).astimezone(NY).replace(tzinfo=None)
        self.period = self.end_time - self.time
        self.is_fill_forward, self.close = False, Decimal("123.45")

    def GetType(self):
        return NS(FullName="QuantConnect.Data.Market.TradeBar")


class Batch:
    def __init__(self, symbol, bar):
        self.time, self.entries = bar.end_time, [(symbol, bar)]

    def items(self):
        return iter(self.entries)


class History:
    def __init__(self, schedule):
        self.schedule, self.calls = schedule, []
        self.mutate, self.mode = None, None

    def __getitem__(self, kind):
        assert kind is Bar
        if self.mode == "lookup":
            raise RuntimeError("SYNTHETIC PRIVATE LOOKUP MESSAGE")

        def call(symbols, start, end, resolution, **kwargs):
            assert len(symbols) == 1
            symbol = symbols[0]
            self.calls.append((symbols, start, end, resolution, kwargs))
            if self.mode == "call":
                raise RuntimeError("SYNTHETIC PRIVATE CALL MESSAGE")
            batches = [Batch(symbol, Bar(symbol, row)) for row in self.schedule]
            if self.mutate:
                batches = self.mutate(symbol, batches)
            if self.mode == "read":
                def broken():
                    yield batches[0]
                    raise RuntimeError("SYNTHETIC PRIVATE ITERATOR MESSAGE")
                return broken()
            return batches
        return call


def schedule():
    result = []
    for session, close in (("2020-12-31", 16), ("2021-01-04", 16),
            ("2021-11-26", 13), ("2026-10-13", 16)):
        day = datetime.strptime(session, "%Y-%m-%d").replace(tzinfo=NY)
        result.append({"session": session,
            "open_utc": day.replace(hour=9, minute=30).astimezone(timezone.utc).isoformat(),
            "close_utc": day.replace(hour=close).astimezone(timezone.utc).isoformat()})
    return result


@pytest.fixture
def scenario(monkeypatch):
    grid = schedule()
    rows, symbols = [], {}
    for index in range(7):
        figi = "BBG" + str(index).zfill(9)
        row = m.figi.build_preliminary_qc_figi_binding(
            security_id="sharadar-composite-figi-" + figi, issuer_id="synthetic-issuer-" + str(index),
            composite_figi=figi, listing_id="synthetic-listing-" + str(index),
            diagnostic_current_ticker="SYNTH" + str(index), diagnostic_exchange_mic="XNYS",
            candidate_first_session="2020-12-31", candidate_last_session="2021-01-04",
            source_snapshot_available_at="2026-10-01T00:00:00.000000Z",
            source_row_sha256=m.digest({"source": index}), identity_evidence_sha256=m.digest({"evidence": index}),
            security_master_admission_sha256=m.ADMISSION_SHA256,
            admitted_mapping_inventory_sha256="a" * 64, admitted_mapping_count=7)
        rows.append(row)
        symbols[figi] = Symbol("SYNTH" + str(index), "SYNTH" + str(index) + " 123")
    axis = tuple(row["session"] for row in grid)
    monkeypatch.setattr(m, "EXPECTED_BINDINGS", 7)
    monkeypatch.setattr(m, "EXPECTED_AXIS_COUNT", len(axis))
    monkeypatch.setattr(m, "EXPECTED_SESSION_COUNT", len(axis))
    monkeypatch.setattr(m, "AXIS_SHA256", m.digest(list(axis)))
    monkeypatch.setattr(m, "SCHEDULE_SHA256", m.digest(grid))
    monkeypatch.setattr(m, "BINDING_STREAM_SHA256", m.inputs._stream_hash(rows))
    monkeypatch.setattr(m, "PACKAGE_SHA256", "b" * 64)
    loaded = NS(package_sha256=m.PACKAGE_SHA256, activation_manifest_sha256=m.ACTIVATION_SHA256,
        runtime_symbol_bindings=tuple(rows),
        evaluator_input=NS(session_axis=axis, source_lineage_sha256s=(
            ("security_master_admission_sha256", m.ADMISSION_SHA256),)))
    loads = []

    def load(algorithm, **kwargs):
        loads.append(kwargs)
        return loaded
    monkeypatch.setattr(m.inputs, "load_accepted_risk_preliminary_package", load)
    etfs = {ticker: Symbol(ticker, ticker + " ETF123") for ticker in m.UNIVERSES}
    hours = Hours(grid)
    securities = {symbol: Security(symbol, hours) for symbol in (*symbols.values(), *etfs.values())}
    history = History(grid)
    unavailable = set()
    forward_changes, reverse_changes, forwards, reverses = {}, {}, [], []

    def resolver(value):
        if type(value) is str:
            forwards.append(value)
            if value in unavailable:
                return None
            return forward_changes.get(value, symbols[value])
        reverses.append(value)
        for key, symbol in symbols.items():
            if symbol is value:
                return reverse_changes.get(key, key)
        raise RuntimeError("synthetic unknown symbol")

    algorithm = NS(live_mode=False, time_zone="America/New_York", account_currency="USD",
        settings=NS(daily_precise_end_time=True, seed_initial_prices=False),
        time=datetime(2026, 10, 14), portfolio={}, transactions=NS(get_orders=lambda: ()),
        composite_figi=resolver, securities=securities, history=history)
    adds = []

    def add(symbol, resolution, fill_forward, leverage, extended):
        adds.append((symbol, resolution, fill_forward, leverage, extended))
        assert (resolution, fill_forward, leverage, extended) == ("Daily", False, 1, False)
        return securities[symbol]
    algorithm.add_security = add
    chosen = sorted(m.digest(row) for row in rows[:5])
    spec = m.make_specification(chosen)

    def driver(specification=None):
        current = spec if specification is None else specification
        return m.NativePriceSourceDiagnostic(algorithm, specification=current,
            expected_specification_sha256=m.digest(current), activation_manifest_key="synthetic/activation.json",
            activation_manifest_sha256=m.ACTIVATION_SHA256, activation_manifest_byte_count=1,
            benchmark_symbol=etfs["SPY"], etf_symbols=etfs, trade_bar_type=Bar,
            daily_resolution="Daily", raw_normalization="RAW")
    return NS(grid=grid, rows=rows, symbols=symbols, etfs=etfs, hours=hours,
        securities=securities, history=history, unavailable=unavailable,
        forward_changes=forward_changes, reverse_changes=reverse_changes, algorithm=algorithm,
        forwards=forwards, reverses=reverses,
        loaded=loaded, loads=loads, adds=adds, spec=spec, driver=driver)


def refuses(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert m.finite(caught.value) == code
    assert "PRIVATE" not in str(caught.value)


def test_full_bound_capture_is_QC_local_no_order_and_not_price_or_identity_admission(scenario):
    summary, book = scenario.driver().prepare()
    assert summary["input_binding_count"] == summary["resolved_count"] == 7
    assert summary["selected_count"] == summary["explicit_history_calls"] == summary["enumeration_complete_count"] == 5
    assert summary["required_cell_count"] == summary["valid_cell_count"] == 20
    assert summary["unpriced_cell_count"] == summary["named_refusal_count"] == 0
    assert summary["identity_phase"] == "observed"
    assert summary["forward_observation_count"] == summary["forward_known_SID_count"] == 7
    assert summary["forward_unknown_SID_count"] == summary["forward_duplicate_SID_identity_count"] == 0
    assert summary["forward_state_counts"]["known_US_equity"] == 7
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    assert len(scenario.loads) == 1 and len(scenario.adds) == len(scenario.history.calls) == 5
    assert len(scenario.forwards) == len(set(scenario.forwards)) == 7
    for symbols, first, last, resolution, kwargs in scenario.history.calls:
        assert len(symbols) == 1 and resolution == "Daily"
        assert first == datetime(2020, 12, 31) and last == datetime(2026, 10, 14)
        assert kwargs == {"fill_forward": False, "extended_market_hours": False, "data_normalization_mode": "RAW"}
    assert "SYNTH" not in repr(book) and "123.45" not in repr(book)
    with pytest.raises(TypeError):
        json.dumps(book)
    with pytest.raises(TypeError):
        pickle.dumps(book)
    with pytest.raises(TypeError):
        book._raw = b"changed"
    assert summary["private_book_sha256"] == book.sha256
    assert m.validate_summary(summary) == summary
    public = m.canonical(summary)
    assert b"123.45" not in public and b"SYNTH" not in public and b"BBG000" not in public


def test_half_day_and_DST_match_independent_schedule_and_expired_binding_does_not_clip(scenario):
    summary, book = scenario.driver().prepare()
    record = json.loads(book._raw)  # Synthetic-only inspection, never a production host export.
    assert record["session_schedule"] == scenario.grid
    assert scenario.grid[2]["close_utc"].endswith("18:00:00+00:00")
    assert scenario.grid[-1]["open_utc"].endswith("13:30:00+00:00")
    assert all(len(row["raw_USD_closes"]) == 4 for row in record["selected"])
    assert summary["valid_cell_count"] == 20


@pytest.mark.parametrize("mode", ["selected_unavailable", "selected_roundtrip", "selected_nonUS",
    "selected_stock_collision", "unselected_own_ETF_collision", "unselected_SPY_collision",
    "duplicate_unselected_own_ETF_collision"])
def test_all_five_and_full_catalog_collisions_are_required_before_any_price_call(scenario, mode):
    if mode == "selected_unavailable":
        scenario.unavailable.add(scenario.rows[0]["composite_figi"])
    elif mode == "selected_roundtrip":
        scenario.reverse_changes[scenario.rows[0]["composite_figi"]] = scenario.rows[5]["composite_figi"]
    elif mode == "selected_nonUS":
        scenario.symbols[scenario.rows[0]["composite_figi"]].id.market = "other"
    elif mode == "selected_stock_collision":
        scenario.symbols[scenario.rows[0]["composite_figi"]].id.text = str(
            scenario.symbols[scenario.rows[1]["composite_figi"]].id)
    elif mode == "duplicate_unselected_own_ETF_collision":
        for row in scenario.rows[5:]:
            scenario.symbols[row["composite_figi"]].id.text = str(scenario.etfs["QQQ"].id)
    elif mode == "unselected_SPY_collision":
        scenario.symbols[scenario.rows[5]["composite_figi"]].id.text = str(scenario.etfs["SPY"].id)
    else:
        scenario.symbols[scenario.rows[5]["composite_figi"]].id.text = str(scenario.etfs["QQQ"].id)
    summary, book = scenario.driver().prepare()
    assert summary["identity_phase"] == "refused"
    assert summary["explicit_history_calls"] == summary["valid_cell_count"] == 0
    assert scenario.history.calls == scenario.adds == []
    assert summary["unpriced_cell_count"] == 20
    assert all(row["absent_cell_count"] is None and row["failure_unknown_cell_count"] == 4
        for row in summary["per_selected"])
    if mode in ("unselected_SPY_collision", "unselected_own_ETF_collision"):
        assert summary["full_catalog_own_ETF_collision_count"] == 1
    elif mode == "duplicate_unselected_own_ETF_collision":
        assert summary["full_catalog_own_ETF_collision_count"] == 2
        assert summary["forward_duplicate_SID_identity_count"] == 2
        assert summary["named_refusal_count"] == 2
    assert len(scenario.forwards) == len(set(scenario.forwards)) == 7


@pytest.mark.parametrize("mode", ["unavailable", "incompatible", "generic_duplicate"])
def test_unselected_named_refusals_remain_visible_not_claimed_as_complete_SID_knowledge(scenario, mode):
    if mode == "unavailable":
        scenario.unavailable.add(scenario.rows[6]["composite_figi"])
    elif mode == "incompatible":
        scenario.symbols[scenario.rows[6]["composite_figi"]].id.market = "other"
    else:
        for row in scenario.rows[5:]:
            scenario.symbols[row["composite_figi"]].id.text = "SYNTHETIC COLLIDING123"
    summary, book = scenario.driver().prepare()
    assert summary["identity_phase"] == "observed" and summary["explicit_history_calls"] == 5
    assert summary["full_catalog_own_ETF_collision_count"] == 0
    if mode == "unavailable":
        assert summary["forward_unknown_SID_count"] == 1 and summary["forward_known_SID_count"] == 6
        assert summary["forward_state_counts"]["unavailable"] == 1
    elif mode == "incompatible":
        assert summary["forward_state_counts"]["known_incompatible"] == 1
        assert summary["forward_known_SID_count"] == 7
    else:
        assert summary["forward_duplicate_SID_identity_count"] == 2
        assert summary["named_refusal_count"] == 2
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    assert len(scenario.forwards) == len(set(scenario.forwards)) == 7


@pytest.mark.parametrize("field", ["package", "stream", "axis", "activation", "admission"])
def test_exact_original_input_commitments_precede_native_history(scenario, field):
    if field == "package":
        scenario.loaded.package_sha256 = "c" * 64
    elif field == "stream":
        scenario.rows[0]["diagnostic_current_ticker"] = "CHANGED"
    elif field == "axis":
        scenario.loaded.evaluator_input.session_axis = tuple(reversed(scenario.loaded.evaluator_input.session_axis))
    elif field == "activation":
        scenario.loaded.activation_manifest_sha256 = "c" * 64
    else:
        scenario.loaded.evaluator_input.source_lineage_sha256s = (("security_master_admission_sha256", "c" * 64),)
    with pytest.raises(m.Refused):
        scenario.driver().prepare()
    assert not scenario.history.calls


@pytest.mark.parametrize("field", ["live", "holding", "order", "account_currency", "algorithm_zone",
    "precise_time", "seed_prices", "future_history", "security_currency", "conversion",
    "subscription_FF", "subscription_extended", "subscription_resolution", "native_hours",
    "calendar_commitment"])
def test_unsafe_or_unmatched_native_context_refuses_before_history(scenario, monkeypatch, field):
    selected = scenario.symbols[scenario.rows[0]["composite_figi"]]
    security = scenario.securities[selected]
    if field == "live":
        scenario.algorithm.live_mode = True
    elif field == "holding":
        scenario.algorithm.portfolio = {selected: NS(quantity=Decimal(1))}
    elif field == "order":
        scenario.algorithm.transactions.get_orders = lambda: [object()]
    elif field == "account_currency":
        scenario.algorithm.account_currency = "EUR"
    elif field == "algorithm_zone":
        scenario.algorithm.time_zone = "UTC"
    elif field == "precise_time":
        scenario.algorithm.settings.daily_precise_end_time = False
    elif field == "seed_prices":
        scenario.algorithm.settings.seed_initial_prices = True
    elif field == "future_history":
        scenario.algorithm.time = datetime(2026, 10, 13, 23, 59)
    elif field == "security_currency":
        security.quote_currency.symbol = "EUR"
    elif field == "conversion":
        security.quote_currency.conversion_rate = Decimal(2)
    elif field == "subscription_FF":
        security.subscriptions[0].fill_data_forward = True
    elif field == "subscription_extended":
        security.subscriptions[0].extended_market_hours = True
    elif field == "subscription_resolution":
        security.subscriptions[0].resolution = "Minute"
    elif field == "native_hours":
        different = Hours(scenario.grid)
        different.shift = timedelta(minutes=1)
        security.exchange.hours = different
    else:
        monkeypatch.setattr(m, "SCHEDULE_SHA256", "d" * 64)
        scenario.spec = m.make_specification(scenario.spec["selected_whole_binding_sha256s"])
    with pytest.raises(m.Refused):
        scenario.driver(scenario.spec).prepare()
    assert not scenario.history.calls


@pytest.mark.parametrize("mode", ["missing", "wrong_sid", "wrong_bar_sid", "fill_forward",
    "unknown_FF", "zero", "negative", "nan", "infinite", "overlong_price", "midnight_time",
    "wrong_close", "wrong_group", "wrong_period", "wrong_type", "outside_axis", "duplicate"])
def test_missing_invalid_and_duplicate_cells_never_get_price_fallback(scenario, mode):
    def mutate(symbol, batches):
        bar = batches[0].entries[0][1]
        if mode == "missing":
            return batches[1:]
        if mode == "wrong_sid":
            batches[0].entries[0] = (scenario.etfs["SPY"], bar)
        elif mode == "wrong_bar_sid":
            bar.symbol = scenario.etfs["SPY"]
        elif mode == "fill_forward":
            bar.is_fill_forward = True
        elif mode == "unknown_FF":
            bar.is_fill_forward = None
        elif mode == "zero":
            bar.close = Decimal(0)
        elif mode == "negative":
            bar.close = Decimal(-1)
        elif mode == "nan":
            bar.close = Decimal("NaN")
        elif mode == "infinite":
            bar.close = Decimal("Infinity")
        elif mode == "overlong_price":
            bar.close = Decimal("1e-1000")
        elif mode == "midnight_time":
            bar.time = bar.time.replace(hour=0, minute=0)
        elif mode == "wrong_close":
            bar.end_time += timedelta(minutes=1)
        elif mode == "wrong_group":
            batches[0].time += timedelta(minutes=1)
        elif mode == "wrong_period":
            bar.period += timedelta(minutes=1)
        elif mode == "wrong_type":
            bar.GetType = lambda: NS(FullName="Wrong.Native.Type")
        elif mode == "outside_axis":
            bar.time -= timedelta(days=1)
        else:
            return [batches[0], batches[0], *batches[2:]]
        return batches
    scenario.history.mutate = mutate
    summary, book = scenario.driver().prepare()
    assert summary["valid_cell_count"] < 20 and summary["unpriced_cell_count"] > 0
    assert summary["explicit_history_calls"] == 5
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    if mode == "duplicate":
        assert all(row["duplicate_payload_count"] == 1 and row["valid_cell_count"] == 2
            for row in summary["per_selected"])
    if mode == "missing":
        assert all(row["absent_cell_count"] == 1 and row["failure_unknown_cell_count"] == 0
            for row in summary["per_selected"])


@pytest.mark.parametrize("mode,call_count,status", [("lookup", 0, "lookup_failed"),
    ("call", 5, "call_failed"), ("read", 5, "read_failed")])
def test_fixed_independent_symbol_calls_do_not_retry_or_mislabel_failure_as_absence(scenario, mode, call_count, status):
    scenario.history.mode = mode
    summary, book = scenario.driver().prepare()
    assert summary["explicit_history_calls"] == len(scenario.history.calls) == call_count
    assert all(row["status"] == status and row["absent_cell_count"] is None
        and row["failure_unknown_cell_count"] > 0 for row in summary["per_selected"])
    assert "PRIVATE" not in m.canonical(summary).decode("ascii")


def test_empty_complete_enumeration_is_absence_observation_not_coverage_success(scenario):
    scenario.history.mutate = lambda symbol, batches: []
    summary, book = scenario.driver().prepare()
    assert summary["enumeration_complete_count"] == 5
    assert summary["valid_cell_count"] == 0 and summary["unpriced_cell_count"] == 20
    assert all(row["absent_cell_count"] == 4 for row in summary["per_selected"])
    assert summary["complete_required_price_coverage_proven"] is False


def test_one_instance_is_spent_even_if_first_preflight_fails(scenario):
    driver = scenario.driver()
    scenario.algorithm.live_mode = True
    refuses("orders", driver.prepare)
    scenario.algorithm.live_mode = False
    refuses("once", driver.prepare)
    assert not scenario.history.calls


def test_late_original_binding_or_native_metadata_change_is_not_success(scenario):
    changed = False
    def mutate(symbol, batches):
        nonlocal changed
        if not changed:
            scenario.rows[-1]["diagnostic_current_ticker"] = "CHANGED"
            changed = True
        return batches
    scenario.history.mutate = mutate
    refuses("source_changed", scenario.driver().prepare)


@pytest.mark.parametrize("field", ["package", "activation", "admission", "own_ETF_SID"])
def test_late_input_or_complete_static_identity_drift_is_not_success(scenario, field):
    def mutate(symbol, batches):
        if field == "package":
            scenario.loaded.package_sha256 = "d" * 64
        elif field == "activation":
            scenario.loaded.activation_manifest_sha256 = "d" * 64
        elif field == "admission":
            scenario.loaded.evaluator_input.source_lineage_sha256s = (("security_master_admission_sha256", "d" * 64),)
        else:
            scenario.etfs["QQQ"].id.text = "CHANGED ETF123"
        return batches
    scenario.history.mutate = mutate
    refuses("source_changed", scenario.driver().prepare)


def test_failed_call_cannot_be_relabelled_as_valid_price_cells_by_metadata_only(scenario):
    scenario.history.mode = "call"
    summary, _ = scenario.driver().prepare()
    summary["per_selected"][0]["valid_cell_count"] = 1
    summary["per_selected"][0]["unpriced_cell_count"] -= 1
    summary["per_selected"][0]["failure_unknown_cell_count"] -= 1
    summary["valid_cell_count"] += 1
    summary["unpriced_cell_count"] -= 1
    refuses("summary", lambda: m.validate_summary(summary))


@pytest.mark.parametrize("change", ["flag", "extra", "count_bool", "counter", "ordinal",
    "price_ready", "absent_on_failure", "unknown_reason", "forward_count", "forward_unknown",
    "forward_state_bool", "forward_collision_bound"])
def test_closed_summary_cannot_be_relabelled_as_admission_or_impossible_accounting(scenario, change):
    summary, _ = scenario.driver().prepare()
    if change == "flag":
        summary["source_priority_admitted"] = True
    elif change == "extra":
        summary["ticker"] = "SYNTH"
    elif change == "count_bool":
        summary["valid_cell_count"] = True
    elif change == "counter":
        summary["unpriced_cell_count"] = 1
    elif change == "ordinal":
        summary["per_selected"][0]["ordinal"] = 2
    elif change == "price_ready":
        summary["complete_required_price_coverage_proven"] = True
    elif change == "absent_on_failure":
        summary["per_selected"][0]["failure_unknown_cell_count"] = 1
    elif change == "forward_count":
        summary["forward_observation_count"] -= 1
    elif change == "forward_unknown":
        summary["forward_unknown_SID_count"] = 1
    elif change == "forward_state_bool":
        summary["forward_state_counts"]["unreadable"] = False
    elif change == "forward_collision_bound":
        summary["full_catalog_own_ETF_collision_count"] = 8
    else:
        summary["per_selected"][0]["invalid_row_counts"] = {"arbitrary_private_message": 1}
    refuses("summary", lambda: m.validate_summary(summary))


def test_source_only_module_exposes_no_raw_serializer_or_publication_or_execution_method():
    import ast
    from pathlib import Path
    tree = ast.parse(Path(m.__file__).read_bytes())
    forbidden = {"save", "save_bytes", "write", "write_bytes", "debug", "log", "error",
        "market_order", "set_holdings", "liquidate", "set_market_price", "download", "post", "get"}
    # Dictionary .get is a pure lookup; no HTTP/client imports exist.
    forbidden.remove("get")
    assert not any(isinstance(node, ast.Attribute) and node.attr in forbidden for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        and node.id in {"print", "open", "requests", "subprocess", "os"} for node in ast.walk(tree))
    assert not hasattr(m.PrivateNativeBook, "to_record") and not hasattr(m.PrivateNativeBook, "private_record")
    profile = m.profile_record()
    assert "requires_separate_exact_paid_org" in profile["future_publication"]
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
