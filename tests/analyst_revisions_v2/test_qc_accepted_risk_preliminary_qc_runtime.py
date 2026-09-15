import dataclasses
import gzip
import hashlib
import io
import json
import sqlite3
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from data.exchange_calendar import trading_sessions

from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_qc_figi as figi,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_qc_runtime as runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_qc_projection as projection,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_package as package_builder,
)
SHA = "a" * 64


class _Sid:
    def __init__(self, text, market="usa"):
        self.text = text
        self.market = market

    def __str__(self):
        return self.text


class _Symbol:
    def __init__(self, sid, ticker, market="usa", security_type="Equity"):
        self.id = _Sid(sid, market)
        self.value = ticker
        self.security_type = security_type


def _binding(figi_value="BBG000000001", ticker="OLD", count=1):
    return figi.build_preliminary_qc_figi_binding(
        security_id="sharadar-composite-figi-" + figi_value,
        issuer_id="sharadar-permaticker-" + figi_value[-3:],
        composite_figi=figi_value,
        listing_id="sharadar-listing-" + figi_value[-3:].lower(),
        diagnostic_current_ticker=ticker,
        diagnostic_exchange_mic="XNYS",
        candidate_first_session="2013-01-02",
        candidate_last_session="2025-12-31",
        source_snapshot_available_at="2026-09-14T01:02:03.000000Z",
        source_row_sha256=hashlib.sha256(("source-" + figi_value).encode()).hexdigest(),
        identity_evidence_sha256=hashlib.sha256(
            ("identity-" + figi_value).encode()
        ).hexdigest(),
        security_master_admission_sha256=SHA,
        admitted_mapping_inventory_sha256="b" * 64,
        admitted_mapping_count=count,
    )


def _resolved(rows, symbols, benchmark=None):
    benchmark = benchmark or _Symbol("QC BENCHMARK SID", "SPY")
    by_figi = {row["composite_figi"]: symbol for row, symbol in zip(rows, symbols)}
    by_symbol = {id(symbol): value for value, symbol in by_figi.items()}

    def composite(value):
        if type(value) is str:
            return by_figi.get(value)
        return by_symbol[id(value)]

    return figi.resolve_preliminary_qc_figis(
        rows,
        expected_security_master_admission_sha256=SHA,
        composite_figi=composite,
        benchmark_symbol=benchmark,
    )


def test_figi_only_resolution_roundtrips_once_and_ticker_is_not_identity_gate():
    row = _binding()
    symbol = _Symbol("QC PERMANENT SID", "NEW")
    calls = []

    def composite(value):
        calls.append(value)
        return symbol if type(value) is str else "BBG000000001"

    value = figi.resolve_preliminary_qc_figis(
        [row],
        expected_security_master_admission_sha256=SHA,
        composite_figi=composite,
        benchmark_symbol=_Symbol("QC BENCHMARK SID", "SPY"),
    )

    assert calls == ["BBG000000001", symbol]
    assert value.resolved[0]["external_composite_figi"] == "BBG000000001"
    assert value.resolved[0]["qc_display_ticker"] == "NEW"
    assert value.authority_mode == figi.AUTHORITY_MODE
    assert value.point_in_time is False
    assert value.formal_security_master_authority is False
    assert figi.require_preliminary_qc_figi_resolution(value) is value


def test_figi_binding_hashes_explicit_composite_identity_and_only_diagnostic_ticker():
    row = _binding()

    assert row["schema"] == figi.INPUT_SCHEMA
    assert row["composite_figi"] == "BBG000000001"
    assert row["diagnostic_current_ticker"] == "OLD"
    assert "share_class_id" not in row
    assert "current_snapshot_ticker" not in row
    assert "exchange_mic" not in row
    semantic = dict(row)
    declared = semantic.pop("row_sha256")
    assert hashlib.sha256(figi._canonical(semantic)).hexdigest() == declared


def test_host_projection_translates_authenticated_mapping_to_explicit_figi_stream():
    mapping = {
        "security_id": "sharadar-composite-figi-BBG000000001",
        "issuer_id": "sharadar-permaticker-001",
        "composite_figi": "BBG000000001",
        "listing_id": "sharadar-listing-one",
        "ticker": "OLD",
        "exchange_id": "XNYS",
        "candidate_first_session": "2013-01-02",
        "candidate_last_session": "2025-12-31",
        "source_snapshot_available_at": "2026-09-14T01:02:03Z",
        "source_row_sha256": "1" * 64,
        "identity_evidence_sha256": "2" * 64,
    }
    mappings = (mapping,)
    inventory_sha = hashlib.sha256(
        package_builder.canonical_json_bytes(list(mappings))
    ).hexdigest()

    rows = package_builder._project_runtime_figi_bindings(
        mappings,
        security_master_admission_sha256=SHA,
        admitted_mapping_inventory_sha256=inventory_sha,
    )

    assert rows[0]["composite_figi"] == "BBG000000001"
    assert rows[0]["diagnostic_current_ticker"] == "OLD"
    assert rows[0]["admitted_mapping_inventory_sha256"] == inventory_sha
    assert rows[0]["admitted_mapping_count"] == 1


def test_figi_only_resolution_refuses_full_stock_and_benchmark_collision_groups():
    rows = [
        _binding("BBG000000001", "ONE", 4),
        _binding("BBG000000002", "TWO", 4),
        _binding("BBG000000003", "THR", 4),
        _binding("BBG000000004", "FOR", 4),
    ]
    symbols = [
        _Symbol("QC SHARED", "ONE"),
        _Symbol("QC SHARED", "TWO"),
        _Symbol("QC BENCHMARK SID", "THR"),
        _Symbol("QC UNIQUE", "FOR"),
    ]
    value = _resolved(rows, symbols)
    assert [item["security_id"] for item in value.resolved] == [rows[3]["security_id"]]
    assert [item["reason"] for item in value.named_refusals] == [
        "qc_runtime_security_identifier_collision",
        "qc_runtime_security_identifier_collision",
        "qc_runtime_benchmark_security_identifier_collision",
    ]


def test_figi_only_resolution_has_named_absence_but_hard_exceptions_and_zero_gate():
    rows = [_binding("BBG000000001", "ONE", 2), _binding("BBG000000002", "TWO", 2)]
    good = _Symbol("QC GOOD", "TWO")

    def partial(value):
        if value == "BBG000000001":
            return None
        if value == "BBG000000002":
            return good
        return "BBG000000002"

    value = figi.resolve_preliminary_qc_figis(
        rows,
        expected_security_master_admission_sha256=SHA,
        composite_figi=partial,
        benchmark_symbol=_Symbol("QC BENCH", "SPY"),
    )
    assert value.named_refusals[0]["reason"] == (
        "qc_runtime_composite_figi_resolution_unavailable"
    )

    with pytest.raises(figi.PreliminaryQcFigiError, match="zero usable"):
        figi.resolve_preliminary_qc_figis(
            [_binding()],
            expected_security_master_admission_sha256=SHA,
            composite_figi=lambda _value: None,
            benchmark_symbol=_Symbol("QC BENCH", "SPY"),
        )

    def raised(_value):
        raise RuntimeError("hostile provider detail")

    with pytest.raises(figi.PreliminaryQcFigiError, match="forward resolver raised") as captured:
        figi.resolve_preliminary_qc_figis(
            [_binding()],
            expected_security_master_admission_sha256=SHA,
            composite_figi=raised,
            benchmark_symbol=_Symbol("QC BENCH", "SPY"),
        )
    assert "hostile provider detail" not in str(captured.value)


def test_figi_only_resolution_names_non_us_and_reverse_mismatch_refusals():
    rows = [
        _binding("BBG000000001", "ONE", 3),
        _binding("BBG000000002", "TWO", 3),
        _binding("BBG000000003", "THR", 3),
    ]
    non_us = _Symbol("QC NON US", "ONE", market="canada")
    mismatch = _Symbol("QC MISMATCH", "TWO")
    good = _Symbol("QC GOOD", "THR")
    by_figi = {
        "BBG000000001": non_us,
        "BBG000000002": mismatch,
        "BBG000000003": good,
    }
    reverse = {
        id(non_us): "BBG000000001",
        id(mismatch): "BBG999999999",
        id(good): "BBG000000003",
    }

    value = figi.resolve_preliminary_qc_figis(
        rows,
        expected_security_master_admission_sha256=SHA,
        composite_figi=lambda item: (
            by_figi[item] if type(item) is str else reverse[id(item)]
        ),
        benchmark_symbol=_Symbol("QC BENCH", "SPY"),
    )

    assert [item["reason"] for item in value.named_refusals] == [
        "qc_runtime_composite_figi_not_us_equity",
        "qc_runtime_composite_figi_roundtrip_mismatch",
    ]


def test_figi_only_resolution_hard_refuses_and_redacts_reverse_exception():
    symbol = _Symbol("QC ONE", "ONE")

    def composite(value):
        if type(value) is str:
            return symbol
        raise RuntimeError("sensitive reverse-provider detail")

    with pytest.raises(
        figi.PreliminaryQcFigiError,
        match="reverse resolver raised",
    ) as captured:
        figi.resolve_preliminary_qc_figis(
            [_binding()],
            expected_security_master_admission_sha256=SHA,
            composite_figi=composite,
            benchmark_symbol=_Symbol("QC BENCH", "SPY"),
        )
    assert "sensitive reverse-provider detail" not in str(captured.value)


def test_figi_only_resolution_reflected_proxy_mutation_is_detected():
    row = _binding()
    value = _resolved([row], [_Symbol("QC ONE", "ONE")])

    class Grab:
        backing = None

        def __eq__(self, other):
            self.backing = other
            return False

    class StringSubtype(str):
        pass

    grab = Grab()
    assert (value._security_by_sid == grab) is False
    assert type(grab.backing) is dict
    grab.backing["QC ONE"] = StringSubtype(str(row["security_id"]))
    with pytest.raises(figi.PreliminaryQcFigiError, match="immutable-map scalar"):
        figi.require_preliminary_qc_figi_resolution(value)


class _GenericHistory:
    def __init__(self, bars):
        self.bars = bars
        self.item = None
        self.calls = []

    def __getitem__(self, item):
        self.item = item
        return self

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return tuple(self.bars)


class _TradeBars:
    def __init__(self, observed_time, pairs):
        self.time = observed_time
        self._pairs = tuple(pairs)

    def items(self):
        return list(self._pairs)


def _request(ids):
    seed = {
        "schema": evaluator.HISTORY_REQUEST_SCHEMA,
        "request_index": 0,
        "security_ids": list(ids),
        "start_session": "2021-01-04",
        "end_session": "2021-01-05",
        "normalization_mode": "total_return",
        "observation": "session_open",
    }
    digest = hashlib.sha256(runtime._canonical(seed)).hexdigest()
    return evaluator.TotalReturnHistoryRequest(
        evaluator.HISTORY_REQUEST_SCHEMA,
        0,
        tuple(ids),
        "2021-01-04",
        "2021-01-05",
        "total_return",
        "session_open",
        digest,
    )


def test_typed_history_is_total_return_daily_no_fill_and_reverse_mapped_o1(monkeypatch):
    row = _binding()
    stock = _Symbol("QC STOCK SID", "NOW")
    benchmark = _Symbol("QC BENCHMARK SID", "SPY")
    resolution = _resolved([row], [stock], benchmark)
    stock_bar = SimpleNamespace(
        symbol=stock, time=datetime(2021, 1, 4), open="100.25"
    )
    benchmark_bar = SimpleNamespace(
        symbol=benchmark, time=datetime(2021, 1, 4), open="300.5"
    )
    bars = [
        _TradeBars(
            datetime(2021, 1, 4, 16),
            ((stock, stock_bar), (benchmark, benchmark_bar)),
        )
    ]
    generic = _GenericHistory(bars)
    algorithm = SimpleNamespace(history=generic)
    calls = 0
    original = figi.require_preliminary_qc_figi_resolution

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(figi, "require_preliminary_qc_figi_resolution", counted)
    loader = runtime.QcTotalReturnOpenHistoryLoader(
        algorithm,
        resolution=resolution,
        benchmark_symbol=benchmark,
        trade_bar_type="TradeBar",
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
        permitted_security_ids=(runtime.BENCHMARK_SECURITY_ID, row["security_id"]),
        permitted_sessions=("2021-01-04", "2021-01-05"),
    )
    observed = loader(_request((runtime.BENCHMARK_SECURITY_ID, row["security_id"])))

    assert generic.item == "TradeBar"
    args, kwargs = generic.calls[0]
    assert args[0] == [benchmark, stock]
    assert args[1] == datetime(2021, 1, 4)
    assert args[2] == datetime(2021, 1, 6)
    assert args[3] == "Daily"
    assert kwargs == {
        "fill_forward": False,
        "extended_market_hours": False,
        "data_normalization_mode": "TotalReturn",
    }
    assert [(item.security_id, item.session, item.adjusted_open) for item in observed] == [
        (runtime.BENCHMARK_SECURITY_ID, "2021-01-04", evaluator.Decimal("300.5")),
        (row["security_id"], "2021-01-04", evaluator.Decimal("100.25")),
    ]
    # Constructor, before traversal, and after traversal; never once per bar.
    assert calls == 3


def test_typed_multi_symbol_history_refuses_the_flat_bar_shape():
    row = _binding()
    stock = _Symbol("QC STOCK SID", "NOW")
    benchmark = _Symbol("QC BENCHMARK SID", "SPY")
    resolution = _resolved([row], [stock], benchmark)
    generic = _GenericHistory(
        [SimpleNamespace(symbol=stock, time=datetime(2021, 1, 4), open="100")]
    )
    loader = runtime.QcTotalReturnOpenHistoryLoader(
        SimpleNamespace(history=generic),
        resolution=resolution,
        benchmark_symbol=benchmark,
        trade_bar_type="TradeBar",
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
        permitted_security_ids=(runtime.BENCHMARK_SECURITY_ID, row["security_id"]),
        permitted_sessions=("2021-01-04", "2021-01-05"),
    )
    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="non-dictionary batch",
    ):
        loader(_request((runtime.BENCHMARK_SECURITY_ID, row["security_id"])))


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("unrequested", "unrequested SID"),
        ("key_bar_mismatch", "dictionary identity changed"),
        ("mixed_session", "dictionary mixes sessions"),
        ("duplicate", "duplicated an adjusted open"),
        ("out_of_axis", "dictionary is out of axis"),
        ("zero", "not positive finite"),
        ("nondecimal", "open is not decimal"),
    ),
)
def test_typed_history_isolated_refusals(case, message):
    row = _binding()
    stock = _Symbol("QC STOCK SID", "NOW")
    benchmark = _Symbol("QC BENCHMARK SID", "SPY")
    other = _Symbol("QC OTHER SID", "OTHER")
    resolution = _resolved([row], [stock], benchmark)
    dictionary_time = datetime(2021, 1, 4)
    key_symbol = stock
    bar_symbol = stock
    bar_time = dictionary_time
    observed_open = "100"
    if case == "unrequested":
        key_symbol = other
        bar_symbol = other
    elif case == "key_bar_mismatch":
        bar_symbol = other
    elif case == "mixed_session":
        bar_time = datetime(2021, 1, 5)
    elif case == "out_of_axis":
        dictionary_time = datetime(2021, 1, 6)
        bar_time = dictionary_time
    elif case == "zero":
        observed_open = "0"
    elif case == "nondecimal":
        observed_open = "not-a-decimal"
    bar = SimpleNamespace(symbol=bar_symbol, time=bar_time, open=observed_open)
    batches = [_TradeBars(dictionary_time, ((key_symbol, bar),))]
    if case == "duplicate":
        batches.append(_TradeBars(dictionary_time, ((key_symbol, bar),)))
    loader = runtime.QcTotalReturnOpenHistoryLoader(
        SimpleNamespace(history=_GenericHistory(batches)),
        resolution=resolution,
        benchmark_symbol=benchmark,
        trade_bar_type="TradeBar",
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
        permitted_security_ids=(runtime.BENCHMARK_SECURITY_ID, row["security_id"]),
        permitted_sessions=("2021-01-04", "2021-01-05"),
    )

    with pytest.raises(runtime.AcceptedRiskPreliminaryQcRuntimeError, match=message):
        loader(_request((row["security_id"],)))


def test_typed_history_call_exception_is_hard_refusal_and_redacted():
    row = _binding()
    stock = _Symbol("QC STOCK SID", "NOW")
    benchmark = _Symbol("QC BENCHMARK SID", "SPY")

    class RaisingHistory(_GenericHistory):
        def __call__(self, *_args, **_kwargs):
            raise RuntimeError("sensitive history detail")

    loader = runtime.QcTotalReturnOpenHistoryLoader(
        SimpleNamespace(history=RaisingHistory(())),
        resolution=_resolved([row], [stock], benchmark),
        benchmark_symbol=benchmark,
        trade_bar_type="TradeBar",
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
        permitted_security_ids=(runtime.BENCHMARK_SECURITY_ID, row["security_id"]),
        permitted_sessions=("2021-01-04", "2021-01-05"),
    )
    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="History call failed",
    ) as captured:
        loader(_request((row["security_id"],)))
    assert "sensitive history detail" not in str(captured.value)


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _gzip(value):
    target = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as stream:
        stream.write(_canonical(value) + b"\n")
    return target.getvalue()


class _Store:
    def __init__(self, values):
        self.values = values
        self.events = []

    def contains_key(self, key):
        self.events.append(("contains", key))
        return key in self.values

    def read_bytes(self, key):
        self.events.append(("read", key))
        return self.values[key]


def _transport_fixture():
    prefix = "arv2/preliminary-rating/fixture"
    role_values = {
        "evaluator_manifest": {"manifest_id": "manifest-one", "manifest_sha256": "c" * 64},
        "session_axis": {"session": "row"},
        "memberships": {"membership": "row"},
        "contributions": {"contribution": "row"},
        "runtime_symbol_bindings": _binding(),
    }
    values = {}
    descriptors = []
    for role, value in role_values.items():
        if role == "evaluator_manifest":
            name = "evaluator-manifest.json"
            payload = _canonical(value) + b"\n"
            compression = "identity"
        else:
            name = role + "-0000-jsonl.gz"
            payload = _gzip(value)
            compression = "gzip"
        key = prefix + "/" + name
        values[key] = payload
        descriptors.append(
            {
                "schema": runtime.UPLOAD_OBJECT_SCHEMA,
                "role": role,
                "ordinal": 0,
                "object_store_key": key,
                "relative_path": name,
                "byte_count": len(payload),
                "content_sha256": hashlib.sha256(payload).hexdigest(),
                "record_count": 1,
                "compression": compression,
                "activation_manifest": False,
            }
        )
    transport = {
        "schema": runtime.TRANSPORT_MANIFEST_SCHEMA,
        "package_id": None,
        "package_sha256": None,
        "evaluator_manifest_id": "manifest-one",
        "evaluator_manifest_sha256": "c" * 64,
        "benchmark": {
            "security_id": runtime.BENCHMARK_SECURITY_ID,
            "ticker": runtime.BENCHMARK_TICKER,
            "binding": "QC_US_equity_symbol_resolved_in_process",
        },
        "source_disposition_sha256": "d" * 64,
        "runtime_symbol_binding_count": 1,
        "runtime_symbol_bindings_sha256": runtime._stream_hash(
            (role_values["runtime_symbol_bindings"],)
        ),
        "contribution_census": {"accepted": 1},
        "objects": descriptors,
        "runtime": dict(runtime._EXPECTED_RUNTIME),
        "claims": dict(runtime._EXPECTED_CLAIMS),
    }
    digest = hashlib.sha256(_canonical(transport)).hexdigest()
    transport["package_id"] = "arv2-preliminary-qc-package-" + digest[:24]
    transport["package_sha256"] = digest
    activation_key = prefix + "/transport-manifest.json"
    activation = _canonical(transport) + b"\n"
    values[activation_key] = activation
    return values, activation_key, activation, role_values


def test_cloud_loader_reads_activation_first_authenticates_each_object_and_never_exports(monkeypatch):
    values, key, activation, roles = _transport_fixture()
    store = _Store(values)
    loaded_input = SimpleNamespace(marker="authenticated")
    calls = []

    def load(*items):
        calls.append(items)
        return loaded_input

    monkeypatch.setattr(evaluator, "load_preliminary_rating_input", load)
    algorithm = SimpleNamespace(object_store=store)
    value = runtime.load_accepted_risk_preliminary_package(
        algorithm,
        activation_manifest_key=key,
        activation_manifest_sha256=hashlib.sha256(activation).hexdigest(),
        activation_manifest_byte_count=len(activation),
    )

    assert value.evaluator_input is loaded_input
    assert value.runtime_symbol_bindings == (roles["runtime_symbol_bindings"],)
    assert store.events[:2] == [("contains", key), ("read", key)]
    assert [name for name, _key in store.events].count("read") == 6
    assert not hasattr(runtime, "download")
    assert not hasattr(runtime, "order")
    assert len(calls) == 1


def test_transport_object_count_bound_is_load_bearing():
    _values, key, activation, _roles = _transport_fixture()
    value = json.loads(activation)
    template = next(
        item for item in value["objects"] if item["role"] == "session_axis"
    )
    prefix = key.rsplit("/", 1)[0]

    # Five objects already exist.  Add valid, uniquely named session shards
    # through the exact boundary, then one more.  This keeps every later
    # descriptor/ordinal check satisfiable so only this bound can refuse.
    for ordinal in range(1, runtime.MAX_TRANSPORT_OBJECT_COUNT - 4):
        item = dict(template)
        item["ordinal"] = ordinal
        item["object_store_key"] = (
            f"{prefix}/session_axis-{ordinal:04d}-jsonl.gz"
        )
        item["relative_path"] = f"session_axis-{ordinal:04d}-jsonl.gz"
        item["content_sha256"] = hashlib.sha256(
            item["object_store_key"].encode("ascii")
        ).hexdigest()
        value["objects"].append(item)

    def reidentify(candidate):
        candidate["package_id"] = None
        candidate["package_sha256"] = None
        digest = hashlib.sha256(runtime._canonical(candidate)).hexdigest()
        candidate["package_id"] = "arv2-preliminary-qc-package-" + digest[:24]
        candidate["package_sha256"] = digest

    reidentify(value)
    assert len(value["objects"]) == runtime.MAX_TRANSPORT_OBJECT_COUNT
    runtime._validate_transport(value, key)

    ordinal = runtime.MAX_TRANSPORT_OBJECT_COUNT - 4
    extra = dict(template)
    extra["ordinal"] = ordinal
    extra["object_store_key"] = f"{prefix}/session_axis-{ordinal:04d}-jsonl.gz"
    extra["relative_path"] = f"session_axis-{ordinal:04d}-jsonl.gz"
    extra["content_sha256"] = hashlib.sha256(
        extra["object_store_key"].encode("ascii")
    ).hexdigest()
    value["objects"].append(extra)
    reidentify(value)
    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="transport object inventory changed",
    ):
        runtime._validate_transport(value, key)


def test_per_object_decompression_bound_is_load_bearing(monkeypatch):
    raw = b'{}\n' * 100
    monkeypatch.setattr(runtime, "MAX_DECOMPRESSED_OBJECT_BYTES", len(raw) - 1)
    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="compressed object exceeded decompression bound",
    ):
        runtime._gzip_rows(gzip.compress(raw), 100, "session_axis")


def test_total_decompression_bound_is_load_bearing(monkeypatch):
    values, key, activation, _roles = _transport_fixture()
    monkeypatch.setattr(runtime, "MAX_TOTAL_DECOMPRESSED_BYTES", 1)
    monkeypatch.setattr(
        evaluator,
        "load_preliminary_rating_input",
        lambda *_items: SimpleNamespace(marker="must not be reached"),
    )
    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="package exceeded total decompression bound",
    ):
        runtime.load_accepted_risk_preliminary_package(
            SimpleNamespace(object_store=_Store(values)),
            activation_manifest_key=key,
            activation_manifest_sha256=hashlib.sha256(activation).hexdigest(),
            activation_manifest_byte_count=len(activation),
        )


def test_cloud_loader_stops_on_first_object_hash_mismatch(monkeypatch):
    values, key, activation, _roles = _transport_fixture()
    first_data_key = next(item for item in values if item.endswith("session_axis-0000-jsonl.gz"))
    values[first_data_key] += b"x"
    store = _Store(values)
    monkeypatch.setattr(
        evaluator,
        "load_preliminary_rating_input",
        lambda *_items: (_ for _ in ()).throw(AssertionError("must not load")),
    )
    with pytest.raises(runtime.AcceptedRiskPreliminaryQcRuntimeError, match="object identity changed"):
        runtime.load_accepted_risk_preliminary_package(
            SimpleNamespace(object_store=store),
            activation_manifest_key=key,
            activation_manifest_sha256=hashlib.sha256(activation).hexdigest(),
            activation_manifest_byte_count=len(activation),
        )
    assert ("read", first_data_key) in store.events


def test_cloud_loader_refuses_binding_stream_hash_even_when_transport_rehashes(monkeypatch):
    values, key, activation, _roles = _transport_fixture()
    transport = json.loads(activation)
    transport["runtime_symbol_bindings_sha256"] = "0" * 64
    transport["package_id"] = None
    transport["package_sha256"] = None
    digest = hashlib.sha256(_canonical(transport)).hexdigest()
    transport["package_id"] = "arv2-preliminary-qc-package-" + digest[:24]
    transport["package_sha256"] = digest
    activation = _canonical(transport) + b"\n"
    values[key] = activation
    monkeypatch.setattr(
        evaluator,
        "load_preliminary_rating_input",
        lambda *_items: SimpleNamespace(marker="authenticated"),
    )

    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="binding stream identity changed",
    ):
        runtime.load_accepted_risk_preliminary_package(
            SimpleNamespace(object_store=_Store(values)),
            activation_manifest_key=key,
            activation_manifest_sha256=hashlib.sha256(activation).hexdigest(),
            activation_manifest_byte_count=len(activation),
        )


def test_daily_dedupe_refuses_distinct_common_events_even_with_equal_deltas():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE candidate("
        "view_id TEXT NOT NULL,session_index INTEGER NOT NULL,"
        "security_id TEXT NOT NULL,institution_id TEXT NOT NULL,"
        "provider_event_id TEXT NOT NULL,common_event_id TEXT NOT NULL,"
        "action TEXT NOT NULL,firm_n INTEGER NOT NULL,firm_d INTEGER NOT NULL,"
        "global_n INTEGER NOT NULL,global_d INTEGER NOT NULL,"
        "source_sha TEXT NOT NULL,ambiguous INTEGER NOT NULL)"
    )
    common = {
        "view_id": evaluator.SOURCE_VIEW_IDS[0],
        "session_index": 1,
        "security_id": "security-one",
        "institution_id": "firm-one",
        "action": "upgrades",
        "firm_delta": Fraction(1, 2),
        "global_delta": Fraction(1, 3),
    }
    for provider, event in (("provider-a", "event-a"), ("provider-b", "event-b")):
        package_builder._insert_candidate(
            connection,
            provider_event_id=provider,
            common_event_id=event,
            source_row_sha256=hashlib.sha256(provider.encode()).hexdigest(),
            **common,
        )
    assert package_builder._mark_ambiguous_daily_groups(connection) == 1
    assert connection.execute(
        "SELECT DISTINCT ambiguous FROM candidate"
    ).fetchall() == [(1,)]
    connection.close()


def test_daily_dedupe_keeps_valid_censored_arm_when_current_arm_conflicts():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE candidate("
        "view_id TEXT NOT NULL,session_index INTEGER NOT NULL,"
        "security_id TEXT NOT NULL,institution_id TEXT NOT NULL,"
        "provider_event_id TEXT NOT NULL,common_event_id TEXT NOT NULL,"
        "action TEXT NOT NULL,firm_n INTEGER NOT NULL,firm_d INTEGER NOT NULL,"
        "global_n INTEGER NOT NULL,global_d INTEGER NOT NULL,"
        "source_sha TEXT NOT NULL,ambiguous INTEGER NOT NULL)"
    )
    common = {
        "session_index": 1,
        "security_id": "security-one",
        "institution_id": "firm-one",
        "action": "upgrades",
        "firm_delta": Fraction(1, 2),
        "global_delta": Fraction(1, 3),
    }
    source_a = hashlib.sha256(b"provider-a").hexdigest()
    package_builder._insert_candidate(
        connection,
        view_id=evaluator.SOURCE_VIEW_IDS[0],
        provider_event_id="provider-a",
        common_event_id="event-a",
        source_row_sha256=source_a,
        **common,
    )
    package_builder._insert_candidate(
        connection,
        view_id=evaluator.SOURCE_VIEW_IDS[0],
        provider_event_id="provider-b",
        common_event_id="event-b",
        source_row_sha256=hashlib.sha256(b"provider-b").hexdigest(),
        **common,
    )
    package_builder._insert_candidate(
        connection,
        view_id=evaluator.SOURCE_VIEW_IDS[1],
        provider_event_id="provider-a",
        common_event_id="event-a",
        source_row_sha256=source_a,
        **common,
    )

    assert package_builder._mark_ambiguous_daily_groups(connection) == 1
    rows, duplicate_count = package_builder._select_independent_daily_contributions(
        connection
    )
    assert duplicate_count == 0
    assert len(rows) == 1
    assert rows[0]["source_view_id"] == evaluator.SOURCE_VIEW_IDS[1]
    assert rows[0]["common_event_id"] == "event-a"
    connection.close()


def test_projection_is_five_small_flat_files_and_compiles_after_qc_prelude(monkeypatch):
    activation = SimpleNamespace(
        role="activation_manifest",
        activation_manifest=True,
        object_store_key="arv2/preliminary-rating/fixture/transport-manifest.json",
        content_sha256="f" * 64,
        byte_count=1234,
    )
    package = SimpleNamespace(
        package_id="arv2-preliminary-qc-package-fixture",
        package_sha256="e" * 64,
        upload_objects=(activation,),
    )
    monkeypatch.setattr(
        package_builder,
        "require_accepted_risk_preliminary_package",
        lambda value: value,
    )
    value = projection.build_accepted_risk_preliminary_qc_projection(package)
    by_name = {item.project_path: item for item in value.source_files}

    assert set(by_name) == {
        "main.py",
        "accepted_risk_preliminary_rating_policy.py",
        "accepted_risk_preliminary_rating_evaluator.py",
        "accepted_risk_preliminary_qc_figi.py",
        "accepted_risk_preliminary_qc_runtime.py",
    }
    assert max(item.byte_count for item in value.source_files) < 60_000
    assert all(b"from __future__ import" not in item.source_bytes for item in value.source_files)
    assert all(b"sqlite3" not in item.source_bytes for item in value.source_files)
    main = by_name["main.py"].source_bytes.decode("ascii")
    assert "self._arv2_advance_training_slice()" in main
    assert "self.train(" not in main
    assert "def _arv2_advance_training_slice" in main
    assert value.maximum_train_slice_count == runtime.MAX_TRAIN_SLICE_COUNT == 113
    assert len(
        trading_sessions(date(*projection.ALGORITHM_START), date(*projection.ALGORITHM_END))
    ) == value.maximum_train_slice_count
    assert "set_start_date(2026, 4, 1)" in main
    assert "set_end_date(2026, 9, 11)" in main
    assert 'self.set_time_zone("America/New_York")' in main
    assert "self.settings.daily_precise_end_time = True" in main
    initialize = main.split("def initialize", 1)[1].split("def on_data", 1)[0]
    assert ".history" not in initialize
    assert "advance_training_slice" not in initialize
    assert "transport-manifest.json" in main
    assert "order(" not in main.lower()


def test_projection_future_import_guard_is_an_isolated_compile_refusal():
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match="future-import guard",
    ):
        projection._validate_source(
            "bad.py", b'"""doc"""\nfrom __future__ import annotations\n'
        )


def test_projection_refuses_sqlite_even_if_a_source_reintroduces_it():
    assert "sqlite3" not in projection._ALLOWED_IMPORT_MODULES
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match="forbidden network/process",
    ):
        projection._validate_source("bad.py", b"import sqlite3\n")


def test_projection_refuses_os_even_without_a_dangerous_attribute():
    assert "os" not in projection._ALLOWED_IMPORT_MODULES
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match="forbidden network/process",
    ):
        projection._validate_source("bad.py", b"import os\n")


def test_projection_refuses_syntax_newer_than_qc_python_311():
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match="valid Python AST",
    ):
        projection._validate_source("bad.py", b"type NewSyntax = int\n")


@pytest.mark.parametrize(
    ("source", "message"),
    (
        (b"import requests\n", "forbidden network/process"),
        (
            b"def run(algorithm):\n    algorithm.market_order('SPY', 1)\n",
            "forbidden trading/network/log",
        ),
        (
            b"def run(algorithm):\n    algorithm.object_store.save_bytes('x', b'x')\n",
            "forbidden Object Store write",
        ),
        (
            b"def run(algorithm):\n    algorithm.object_store.save_string('x', 'x')\n",
            "forbidden Object Store write",
        ),
        (
            b"def run(algorithm):\n    algorithm.object_store.get_file_path('x')\n",
            "forbidden Object Store write",
        ),
        (
            b"def run(algorithm):\n    algorithm.market_on_open_order('SPY', 1)\n",
            "forbidden trading/network/log",
        ),
        (
            b"def run(algorithm):\n    getattr(algorithm, 'market_order')('SPY', 1)\n",
            "forbidden dynamic capability",
        ),
        (
            b"def run():\n    __import__('requests')\n",
            "forbidden dynamic capability",
        ),
        (
            b"import os\ndef run():\n    os.system('true')\n",
            "forbidden network/process",
        ),
        (
            b"from System import Net\n",
            "forbidden network/process",
        ),
        (
            b"def run(algorithm):\n    algorithm.notify.email('x', 'y', 'z')\n",
            "forbidden trading/deployment",
        ),
        (
            b"def run(algorithm, model):\n    algorithm.set_alpha(model)\n",
            "forbidden trading/network/log",
        ),
        (
            b"def run(algorithm):\n    submit = algorithm.market_order\n    submit('SPY', 1)\n",
            "forbidden trading/deployment",
        ),
        (
            b"from os import system as harmless\nharmless('true')\n",
            "forbidden network/process",
        ),
        (
            b"def run(algorithm):\n    submit = algorithm.__dict__['market_order']\n    submit('SPY', 1)\n",
            "forbidden trading/deployment",
        ),
        (
            b"import random\n",
            "forbidden network/process",
        ),
        (
            b"def run(algorithm):\n    g = getattr\n    g(algorithm, 'market_order')('SPY', 1)\n",
            "forbidden dynamic capability",
        ),
        (
            b"loader = __import__\nrequests = loader('requests')\nrequests.get('x')\n",
            "forbidden dynamic capability",
        ),
    ),
)
def test_projection_capability_audit_isolates_forbidden_surfaces(source, message):
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match=message,
    ):
        projection._validate_source("bad.py", source)


def test_package_authority_fingerprint_does_not_alias_upload_descriptors(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        evaluator,
        "load_preliminary_rating_input",
        lambda *_items: SimpleNamespace(marker="authenticated"),
    )
    manifest = {"manifest_id": "manifest-one", "manifest_sha256": "c" * 64}
    value = package_builder._materialize(
        output_root=tmp_path,
        evaluator_manifest=manifest,
        session_records=({"session": "row"},),
        membership_records=({"membership": "row"},),
        contribution_records=({"contribution": "row"},),
        runtime_binding_records=(_binding(),),
        source_disposition_sha256="d" * 64,
        contribution_census={"accepted": 1},
    )
    descriptor = value.upload_objects[1]
    original = descriptor.content_sha256
    object.__setattr__(descriptor, "content_sha256", "0" * 64)
    try:
        with pytest.raises(
            package_builder.AcceptedRiskPreliminaryPackageError,
            match="current process authority",
        ):
            package_builder.require_accepted_risk_preliminary_package(value)
    finally:
        object.__setattr__(descriptor, "content_sha256", original)


def test_package_parent_traversal_uses_pinned_dependency_not_substituted_module(
    monkeypatch,
):
    pinned = package_builder._PINNED_ITER_ACCEPTED_ROWS
    monkeypatch.setattr(
        package_builder.accepted_archive,
        "iter_physical_accepted_risk_rows",
        lambda _value: (_ for _ in ()).throw(AssertionError("substituted")),
    )

    assert package_builder._PINNED_ITER_ACCEPTED_ROWS is pinned
    source = Path(package_builder.__file__).read_text()
    assert "for source in _PINNED_ITER_ACCEPTED_ROWS(archive)" in source
    assert "accepted_archive.iter_physical_accepted_risk_rows(archive)" not in source


def test_package_final_parent_reauthentication_covers_every_authority(monkeypatch):
    parents = tuple(object() for _ in range(5))
    calls = []

    def verifier(index):
        def require(value):
            calls.append((index, value))
            return value

        return require

    for index, name in enumerate(
        (
            "_PINNED_REQUIRE_ACCEPTED_ARCHIVE",
            "_PINNED_REQUIRE_PREOPEN_SEED",
            "_PINNED_REQUIRE_SECURITY_ADMISSION",
            "_PINNED_REQUIRE_FIRM_ADMISSION",
            "_PINNED_REQUIRE_GLOBAL_CONTRACT",
        )
    ):
        monkeypatch.setattr(package_builder, name, verifier(index))

    result = package_builder._reauthenticate_package_parents(
        accepted_risk_archive=parents[0],
        seed_archive=parents[1],
        security_master_admission=parents[2],
        firm_admission=parents[3],
        global_contract=parents[4],
    )

    assert result == parents
    assert calls == list(enumerate(parents))


def _reloadable_package(monkeypatch, tmp_path):
    monkeypatch.setattr(
        evaluator,
        "load_preliminary_rating_input",
        lambda *_items: SimpleNamespace(marker="authenticated"),
    )
    value = package_builder._materialize(
        output_root=tmp_path,
        evaluator_manifest={
            "manifest_id": "manifest-reload",
            "manifest_sha256": "c" * 64,
        },
        session_records=({"session": "row"},),
        membership_records=({"membership": "row"},),
        contribution_records=({"contribution": "row"},),
        runtime_binding_records=(_binding(),),
        source_disposition_sha256="d" * 64,
        contribution_census={"accepted": 1},
    )
    package_builder._AUTHORITIES.pop(id(value), None)
    return value


def _rewrite_activation(value, mutate):
    path = value.package_path / "transport-manifest.json"
    record = json.loads(path.read_bytes())
    mutate(record)
    path.write_bytes(package_builder._canonical(record) + b"\n")


def test_persisted_package_reload_mints_authority_and_iterates_activation_last(
    monkeypatch, tmp_path
):
    original = _reloadable_package(monkeypatch, tmp_path)

    loaded = package_builder.load_accepted_risk_preliminary_package(
        original.package_path,
        expected_package_sha256=original.package_sha256,
    )

    assert loaded is not original
    assert loaded.package_sha256 == original.package_sha256
    assert package_builder.require_accepted_risk_preliminary_package(loaded) is loaded
    uploads = tuple(
        package_builder.iter_accepted_risk_preliminary_upload_objects(loaded)
    )
    assert tuple(item for item, _payload in uploads) == loaded.upload_objects
    assert uploads[-1][0].activation_manifest is True
    assert all(
        hashlib.sha256(payload).hexdigest() == item.content_sha256
        and len(payload) == item.byte_count
        for item, payload in uploads
    )


def test_persisted_package_reload_refuses_wrong_out_of_band_hash(
    monkeypatch, tmp_path
):
    value = _reloadable_package(monkeypatch, tmp_path)

    with pytest.raises(
        package_builder.AcceptedRiskPreliminaryPackageError,
        match="does not match its expected hash",
    ):
        package_builder.load_accepted_risk_preliminary_package(
            value.package_path,
            expected_package_sha256="0" * 64,
        )


def test_persisted_package_reload_refuses_unsafe_descriptor_path(
    monkeypatch, tmp_path
):
    value = _reloadable_package(monkeypatch, tmp_path)
    _rewrite_activation(
        value,
        lambda record: record["objects"][1].__setitem__(
            "relative_path", "../escaped-jsonl.gz"
        ),
    )

    with pytest.raises(
        package_builder.AcceptedRiskPreliminaryPackageError,
        match="descriptor schema changed",
    ):
        package_builder.load_accepted_risk_preliminary_package(
            value.package_path,
            expected_package_sha256=value.package_sha256,
        )


def test_persisted_package_reload_refuses_renamed_content_addressed_directory(
    monkeypatch, tmp_path
):
    value = _reloadable_package(monkeypatch, tmp_path)
    renamed = value.package_path.with_name("arv2-preliminary-qc-package-renamed")
    value.package_path.rename(renamed)

    with pytest.raises(
        package_builder.AcceptedRiskPreliminaryPackageError,
        match="root identity changed",
    ):
        package_builder.load_accepted_risk_preliminary_package(
            renamed,
            expected_package_sha256=value.package_sha256,
        )


def test_persisted_package_reload_refuses_symlinked_payload(
    monkeypatch, tmp_path
):
    value = _reloadable_package(monkeypatch, tmp_path)
    descriptor = value.upload_objects[1]
    path = value.package_path / descriptor.relative_path
    outside = tmp_path / "outside-payload.bin"
    outside.write_bytes(path.read_bytes())
    outside.chmod(0o600)
    path.unlink()
    path.symlink_to(outside)

    with pytest.raises(
        package_builder.AcceptedRiskPreliminaryPackageError,
        match="without following links",
    ):
        package_builder.load_accepted_risk_preliminary_package(
            value.package_path,
            expected_package_sha256=value.package_sha256,
        )


def test_persisted_package_reload_refuses_extra_file(monkeypatch, tmp_path):
    value = _reloadable_package(monkeypatch, tmp_path)
    extra = value.package_path / "undeclared.json"
    extra.write_bytes(b"{}\n")
    extra.chmod(0o600)

    with pytest.raises(
        package_builder.AcceptedRiskPreliminaryPackageError,
        match="directory inventory changed",
    ):
        package_builder.load_accepted_risk_preliminary_package(
            value.package_path,
            expected_package_sha256=value.package_sha256,
        )


def test_persisted_package_reload_refuses_descriptor_census_tamper(
    monkeypatch, tmp_path
):
    value = _reloadable_package(monkeypatch, tmp_path)
    _rewrite_activation(
        value,
        lambda record: record["objects"][1].__setitem__(
            "record_count", record["objects"][1]["record_count"] + 1
        ),
    )

    with pytest.raises(
        package_builder.AcceptedRiskPreliminaryPackageError,
        match="compressed payload census changed",
    ):
        package_builder.load_accepted_risk_preliminary_package(
            value.package_path,
            expected_package_sha256=value.package_sha256,
        )


def test_persisted_package_reload_refuses_same_length_payload_hash_tamper(
    monkeypatch, tmp_path
):
    value = _reloadable_package(monkeypatch, tmp_path)
    descriptor = value.upload_objects[1]
    path = value.package_path / descriptor.relative_path
    payload = bytearray(path.read_bytes())
    payload[-1] ^= 1
    path.write_bytes(payload)

    with pytest.raises(
        package_builder.AcceptedRiskPreliminaryPackageError,
        match="member hash changed",
    ):
        package_builder.load_accepted_risk_preliminary_package(
            value.package_path,
            expected_package_sha256=value.package_sha256,
        )


def test_persisted_package_reload_refuses_truncated_payload(
    monkeypatch, tmp_path
):
    value = _reloadable_package(monkeypatch, tmp_path)
    descriptor = value.upload_objects[1]
    path = value.package_path / descriptor.relative_path
    path.write_bytes(path.read_bytes()[:-1])

    with pytest.raises(
        package_builder.AcceptedRiskPreliminaryPackageError,
        match="member byte count changed",
    ):
        package_builder.load_accepted_risk_preliminary_package(
            value.package_path,
            expected_package_sha256=value.package_sha256,
        )


@pytest.mark.parametrize("target", ("directory", "file"))
def test_persisted_package_reload_refuses_nonprivate_identity(
    monkeypatch, tmp_path, target
):
    value = _reloadable_package(monkeypatch, tmp_path)
    if target == "directory":
        value.package_path.chmod(0o755)
    else:
        (value.package_path / value.upload_objects[1].relative_path).chmod(0o644)

    with pytest.raises(
        package_builder.AcceptedRiskPreliminaryPackageError,
        match="not an owner-private|not a bounded owner-private",
    ):
        package_builder.load_accepted_risk_preliminary_package(
            value.package_path,
            expected_package_sha256=value.package_sha256,
        )


class _DriverAlgorithm:
    def __init__(self):
        self.statistics = []

    def set_summary_statistic(self, key, value):
        self.statistics.append((key, value))


class _DriverRuntime:
    def __init__(self, complete_after):
        self.phase = evaluator.RuntimePhase.SCORING
        self.complete_after = complete_after
        self.calls = 0
        self.abort_calls = 0

    def run_callback(self, _loader):
        self.calls += 1
        if self.calls >= self.complete_after:
            self.phase = evaluator.RuntimePhase.COMPLETED
        return SimpleNamespace(call=self.calls)

    def custom_summary_statistics(self):
        return {
            key: "exact"
            for key in evaluator.EVALUATOR_CUSTOM_SUMMARY_STATISTIC_NAMES
        }

    def abort(self):
        self.abort_calls += 1
        self.phase = evaluator.RuntimePhase.CLOSED


def _driver_with_runtime(complete_after):
    algorithm = _DriverAlgorithm()
    driver = runtime.AcceptedRiskPreliminaryQcDriver(
        algorithm,
        activation_manifest_key="arv2/preliminary-rating/test/transport-manifest.json",
        activation_manifest_sha256="a" * 64,
        activation_manifest_byte_count=1,
        benchmark_symbol=object(),
        trade_bar_type="TradeBar",
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
    )
    driver._package = SimpleNamespace(
        package_id="package-one",
        package_sha256="b" * 64,
        activation_manifest_sha256="c" * 64,
    )
    driver._resolution = SimpleNamespace(
        resolution_id="resolution-one",
        resolution_sha256="d" * 64,
        resolved_count=1,
        named_refusal_count=0,
    )
    driver._history_loader = object()
    driver._runtime = _DriverRuntime(complete_after)
    return driver, algorithm


def test_driver_completes_in_bounded_train_slice_emits_once_and_closes_cleanly():
    driver, algorithm = _driver_with_runtime(3)

    assert runtime.EXPECTED_CUSTOM_SUMMARY_STATISTIC_NAMES == tuple(
        sorted(
            (
                *evaluator.EVALUATOR_CUSTOM_SUMMARY_STATISTIC_NAMES,
                runtime.RUNTIME_META_STATISTIC,
            )
        )
    )
    assert len(runtime.EXPECTED_CUSTOM_SUMMARY_STATISTIC_NAMES) == 34

    driver.advance_training_slice(maximum_work_units=10, monotonic=lambda: 0)
    assert driver.completed is True
    assert driver._runtime.calls == 3
    assert [key for key, _value in algorithm.statistics] == [
        *runtime.EXPECTED_CUSTOM_SUMMARY_STATISTIC_NAMES,
    ]
    driver.advance_training_slice(maximum_work_units=10, monotonic=lambda: 1)
    assert len(algorithm.statistics) == 34
    assert driver.require_completed_at_end() is True


def test_full_geometry_completes_in_41_unslowed_daily_slices():
    driver, algorithm = _driver_with_runtime(400)
    planned_runtime = driver._runtime
    driver._runtime = None
    driver._initialize_in_training = lambda: setattr(
        driver, "_runtime", planned_runtime
    )

    for _ in range(40):
        driver.advance_training_slice(maximum_work_units=10, monotonic=lambda: 0)
    assert driver.completed is False
    assert driver._runtime.calls == 399

    driver.advance_training_slice(maximum_work_units=10, monotonic=lambda: 0)
    assert driver.completed is True
    assert driver._runtime.calls == 400
    assert driver._training_slice_count == 41
    assert len(algorithm.statistics) == 34


def test_driver_end_refuses_incomplete_runtime_and_aborts_cache():
    driver, _algorithm = _driver_with_runtime(100)

    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="ended before aggregate completion",
    ):
        driver.require_completed_at_end()
    assert driver._runtime.abort_calls == 1


def test_driver_enforces_monotonic_clock_soft_bound_and_train_slice_census():
    driver, _algorithm = _driver_with_runtime(100)
    clock = iter((0, 0, 241))
    driver.advance_training_slice(
        maximum_work_units=10,
        soft_seconds=240,
        monotonic=lambda: next(clock),
    )
    assert driver._runtime.calls == 1

    driver._training_slice_count = runtime.MAX_TRAIN_SLICE_COUNT
    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="runtime-slice census",
    ):
        driver.advance_training_slice(monotonic=lambda: 242)

    reversed_driver, _algorithm = _driver_with_runtime(100)
    reversed_clock = iter((10, 9))
    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="monotonic clock",
    ):
        reversed_driver.advance_training_slice(
            monotonic=lambda: next(reversed_clock)
        )


def test_driver_backtest_runtime_bound_is_load_bearing():
    driver, _algorithm = _driver_with_runtime(100)
    driver._runtime_started_monotonic = 0
    with pytest.raises(
        runtime.AcceptedRiskPreliminaryQcRuntimeError,
        match="exceeded twelve-hour backtest bound",
    ):
        driver.advance_training_slice(
            monotonic=lambda: runtime.MAX_BACKTEST_RUNTIME_SECONDS + 1
        )


def test_preliminary_projection_size_bounds_are_load_bearing_and_have_headroom():
    """ARV2R74-002: the per-file bound exists to respect QC's 64,000-char limit.

    Removing it turns no other test red, and the largest projected module
    already occupies 96% of the bound, so the next edit to the evaluator can
    cross it.  Pin both the refusal and the remaining headroom.
    """
    from pathlib import Path

    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_qc_projection as projection,
    )

    # The lane bound must stay strictly under QuantConnect's observed limit.
    assert projection.MAX_SOURCE_FILE_BYTES < 64_000

    body = b"X = 1\n"
    filler = b"# " + b"f" * 60 + b"\n"
    oversized = body + filler * (
        (projection.MAX_SOURCE_FILE_BYTES // len(filler)) + 2
    )
    assert len(oversized) > projection.MAX_SOURCE_FILE_BYTES
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match="size, path, or future-import guard",
    ):
        projection._validate_source("oversized.py", oversized)

    # A file exactly at the bound is admitted; one byte more is refused.
    exact = body + b"#" * (projection.MAX_SOURCE_FILE_BYTES - len(body) - 1) + b"\n"
    assert len(exact) == projection.MAX_SOURCE_FILE_BYTES
    projection._validate_source("exact.py", exact)
    with pytest.raises(projection.AcceptedRiskPreliminaryQcProjectionError):
        projection._validate_source("over.py", exact + b"#\n")

    # Every live projected module must stay inside the bound, and the tightest
    # one must retain real headroom rather than sitting on the boundary.
    base = Path(__file__).resolve().parents[2] / "research" / "analyst_revisions_v2_qc"
    sizes = {
        name: len((base / name).read_bytes())
        for name in projection.PROJECT_SOURCE_PATHS
    }
    assert max(sizes.values()) <= projection.MAX_SOURCE_FILE_BYTES, sizes
    assert sum(sizes.values()) <= projection.MAX_TOTAL_SOURCE_BYTES, sizes


def test_preliminary_projection_invokes_qc_prelude_compilation():
    """ARV2R74-003: isolate the prelude compile after earlier guards pass."""
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_qc_projection as projection,
    )

    # This is valid on its own and passes every earlier source audit. Once the
    # QC sentinel is prepended, its global declaration follows an assignment
    # to that name and Python must reject it.
    prelude_hostile = b"global QC_PRELUDE_SENTINEL\nX = 1\n"
    compile(prelude_hostile.decode("ascii"), "probe.py", "exec")
    with pytest.raises(
        projection.AcceptedRiskPreliminaryQcProjectionError,
        match="after QC prelude",
    ):
        projection._validate_source("prelude_hostile.py", prelude_hostile)
