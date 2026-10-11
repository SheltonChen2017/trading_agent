from __future__ import annotations

import csv
import dataclasses
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

import scripts.capture_arv2_sharadar_identities as adapter
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes


KEY = "offline-test-sharadar-identity-key-NEVER-REAL"
ALL = tuple(ticker for _role, tickers in adapter.ROLE_TICKERS for ticker in tickers)


class Response:
    def __init__(self, body, *, status=200, url=None, method="GET", history=None, headers=None):
        self.body, self.status_code, self.override_url, self.method = body, status, url, method
        self.history, self.headers, self.close_count = history or [], headers or {}, 0

    def iter_content(self, *, chunk_size):
        for start in range(0, len(self.body), 11):
            yield self.body[start:start + 11]

    @property
    def content(self):
        raise AssertionError("bounded streaming is required")

    def close(self):
        self.close_count += 1


class Session:
    def __init__(self, responses):
        self.responses, self.calls, self.close_count = list(responses), [], 0

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        full = url + "?" + urlencode(kwargs["params"])
        response.request = SimpleNamespace(method=response.method, url=response.override_url or full)
        response.url = response.override_url or full
        return response

    def close(self):
        self.close_count += 1


def clock(*, backwards=False):
    values = iter((datetime(2026, 10, 7, 20, 0, 0, 1, tzinfo=timezone.utc),
                   datetime(2026, 10, 7, 19 if backwards else 20, 0, 1, 2, tzinfo=timezone.utc)))
    return lambda: next(values)


def price_capture(tmp_path):
    responses = []
    for role, tickers in adapter.ROLE_TICKERS:
        payload = b"ticker,date,closeunadj,lastupdated\n" + b"".join(
            f"{ticker},2026-10-06,123.45,2026-10-07\n".encode() for ticker in tickers
        )
        responses.append(Response(payload))
    return adapter.prices._capture_sharadar_prices_for_test(
        close_session="2026-10-06", artifact_root=tmp_path / "price-input",
        session=Session(responses), clock=clock(), api_key=KEY,
    )


def row(ticker):
    ordinal = ALL.index(ticker) + 1
    return {
        "table": "SEP" if ticker == "QCOM" else "SFP", "ticker": ticker,
        "permaticker": str(100000 + ordinal), "name": "Synthetic issuer " + ticker,
        "exchange": "NASDAQ" if ticker in {"QCOM", "QQQ", "SOXX"} else "NYSEARCA",
        "isdelisted": "N", "category": "Domestic Common Stock Primary Class" if ticker == "QCOM" else "ETF",
        "figi": "BBG" + f"{ordinal:09d}", "cusips": f"SYN{ordinal:06d}", "currency": "USD",
        "firstadded": "2000-01-01", "firstpricedate": "2000-01-03",
        "lastpricedate": "2026-10-07", "lastupdated": "2026-10-07",
    }


def csv_bytes(rows, *, fields=adapter.FIELDS, bom=False):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(fields)
    for values in rows:
        writer.writerow([values[field] for field in fields])
    return (b"\xef\xbb\xbf" if bom else b"") + output.getvalue().encode("utf-8")


def valid_responses(*, edits=None, fields=adapter.FIELDS):
    edits = edits or {}
    return [Response(csv_bytes([{**row(ticker), **edits.get(ticker, {})} for ticker in tickers], fields=fields))
            for role, tickers in adapter.ROLE_TICKERS]


def capture(tmp_path, *, session=None, price=None, capture_clock=None, without_figi=False, strict_cusips=False):
    price = price or price_capture(tmp_path)
    fields = adapter.FIELDS_WITHOUT_FIGI if without_figi else adapter.FIELDS
    session = session or Session(valid_responses(fields=fields))
    loaded = adapter._capture_sharadar_identities_for_test(
        artifact_root=tmp_path / "identity", price_artifact_path=price.artifact_path,
        expected_price_manifest_sha256=price.manifest_sha256,
        session=session, clock=capture_clock or clock(), api_key=KEY,
        without_figi=without_figi, strict_cusips=strict_cusips,
    )
    return loaded, price, session


def load(loaded, price, *, digest=None):
    return adapter.load_sharadar_identity_capture(
        loaded.artifact_path, expected_manifest_sha256=digest or loaded.manifest_sha256,
        price_artifact_path=price.artifact_path,
    )


def document(loaded):
    return json.loads((loaded.artifact_path / "manifest.json").read_bytes())


def repin_manifest(loaded, value):
    payload = canonical_json_bytes(value)
    (loaded.artifact_path / "manifest.json").write_bytes(payload)
    digest = sha256_bytes(payload)
    (loaded.artifact_path / "manifest.sha256").write_bytes((digest + "\n").encode())
    return digest


def test_two_exact_requests_current_candidates_and_private_readback(tmp_path):
    loaded, price, session = capture(tmp_path)
    assert loaded.capture_transport == adapter.TEST_TRANSPORT
    assert loaded.price_manifest_sha256 == price.manifest_sha256
    assert loaded.price_capture_sha256 == price.capture_sha256
    assert loaded.price_close_session == "2026-10-06"
    assert len(session.calls) == 2 and session.close_count == 0
    assert [item.ticker for item in loaded.identities] == list(ALL)
    assert loaded.matched_count == 7 and loaded.refused_count == 0
    assert all(item.status == "matched_current_candidate" for item in loaded.identities)
    assert load(loaded, price) == loaded
    for (role, tickers), (url, options) in zip(adapter.ROLE_TICKERS, session.calls, strict=True):
        assert url == "https://api.sharadar.com/v1.0/data/tickers"
        assert options == {
            "params": {"format": "csv", "table": role, "ticker": ",".join(tickers),
                       "fields": ",".join(adapter.FIELDS), "sort": "ticker.asc", "skip": "0", "limit": "100", "api_key": KEY},
            "timeout": 60, "allow_redirects": False, "stream": True, "verify": True,
            "headers": {"Accept-Encoding": "identity"},
        }
        assert "from" not in options["params"] and "to" not in options["params"]
    assert loaded.artifact_path.stat().st_mode & 0o777 == 0o700
    for file in loaded.artifact_path.iterdir():
        assert file.stat().st_mode & 0o777 == 0o600 and file.stat().st_nlink == 1
        assert KEY.encode() not in file.read_bytes()
    assert all(document(loaded)[flag] is False for flag in adapter.FALSE_FLAGS)
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.identities[0].permanent_share_class_id = "changed"
    assert "BBG" not in repr(loaded) and "Synthetic issuer" not in repr(loaded)


def test_unordered_headers_bom_and_documented_table_names(tmp_path):
    stock = {**row("QCOM"), "table": "stocks"}
    funds = [{**row(ticker), "table": "funds"} for ticker in ALL[1:]]
    bodies = [csv_bytes([stock], fields=tuple(reversed(adapter.FIELDS)), bom=True), csv_bytes(funds)]
    loaded, price, _ = capture(tmp_path, session=Session([Response(body) for body in bodies]))
    assert loaded.matched_count == 7
    assert (loaded.artifact_path / "stocks.csv").read_bytes() == bodies[0]
    assert load(loaded, price) == loaded


@pytest.mark.parametrize("ticker", ALL)
def test_missing_requested_name_is_retained_as_named_refusal(tmp_path, ticker):
    responses = [Response(csv_bytes([row(name) for name in tickers if name != ticker]))
                 for _role, tickers in adapter.ROLE_TICKERS]
    loaded, price, _ = capture(tmp_path, session=Session(responses))
    assert len(loaded.identities) == 7 and loaded.matched_count == 6 and loaded.refused_count == 1
    missing = next(item for item in loaded.identities if item.ticker == ticker)
    assert missing.refusal_codes == ("CURRENT_IDENTITY_MISSING",)
    assert missing.source_row_count == 0 and missing.permanent_share_class_id is None
    assert load(loaded, price) == loaded


def test_ambiguous_rows_are_not_chosen_or_deduplicated(tmp_path):
    responses = valid_responses()
    responses[1] = Response(csv_bytes([row(ticker) for ticker in ALL[1:]] + [row("SPY")]))
    loaded, price, _ = capture(tmp_path, session=Session(responses))
    spy = next(item for item in loaded.identities if item.ticker == "SPY")
    assert spy.source_row_count == 2 and len(spy.source_row_sha256s) == 2
    assert spy.refusal_codes == ("CURRENT_IDENTITY_AMBIGUOUS",)
    assert spy.permanent_share_class_id is None and spy.composite_figi is None
    assert loaded.refused_count == 1 and load(loaded, price) == loaded


@pytest.mark.parametrize("field,reason", [
    ("permaticker", "CROSS_NAME_PERMANENT_ID_COLLISION"),
    ("figi", "CROSS_NAME_FIGI_COLLISION"),
    ("cusips", "CROSS_NAME_CUSIP_CANDIDATE_COLLISION"),
])
def test_all_stock_own_etf_collision_members_are_refused(tmp_path, field, reason):
    common = row("QCOM")[field]
    edits = {"SPY": {field: common}, "QQQ": {field: common}}
    loaded, _price, _session = capture(tmp_path, session=Session(valid_responses(edits=edits)))
    assert loaded.refused_count == 3 and loaded.matched_count == 4
    for item in loaded.identities:
        if item.ticker in {"QCOM", "SPY", "QQQ"}:
            assert reason in item.refusal_codes
            assert "DIRECT_STOCK_OWN_ETF_IDENTITY_COLLISION" in item.refusal_codes
        else:
            assert item.refusal_codes == ()


def test_collision_from_ambiguous_or_otherwise_invalid_row_marks_all_members(tmp_path):
    bad = {**row("SPY"), "figi": row("QCOM")["figi"], "category": "CEF"}
    responses = valid_responses()
    responses[1] = Response(csv_bytes([row(ticker) for ticker in ALL[1:]] + [bad]))
    loaded, _price, _session = capture(tmp_path, session=Session(responses))
    by_name = {item.ticker: item for item in loaded.identities}
    assert "CURRENT_IDENTITY_AMBIGUOUS" in by_name["SPY"].refusal_codes
    assert "CROSS_NAME_FIGI_COLLISION" in by_name["SPY"].refusal_codes
    assert "CROSS_NAME_FIGI_COLLISION" in by_name["QCOM"].refusal_codes
    assert loaded.refused_count == 2


@pytest.mark.parametrize("field,value,reason", [
    ("table", "SF1", "SOURCE_TABLE_UNRECOGNIZED"),
    ("permaticker", "", "PERMANENT_SHARE_CLASS_ID_INVALID"),
    ("permaticker", "has spaces", "PERMANENT_SHARE_CLASS_ID_INVALID"),
    ("figi", "", "COMPOSITE_FIGI_INVALID_OR_MISSING"),
    ("figi", "TOO_SHORT", "COMPOSITE_FIGI_INVALID_OR_MISSING"),
    ("name", "", "ISSUER_NAME_MISSING"),
    ("isdelisted", "Y", "CURRENT_ACTIVE_STATUS_UNPROVEN"),
    ("isdelisted", "", "CURRENT_ACTIVE_STATUS_UNPROVEN"),
    ("category", "ADR", "INSTRUMENT_CATEGORY_UNRECOGNIZED"),
    ("exchange", "OTC", "CURRENT_LISTING_EXCHANGE_UNRECOGNIZED"),
    ("currency", "", "USD_CURRENCY_UNPROVEN"),
    ("currency", "CAD", "USD_CURRENCY_UNPROVEN"),
    ("cusips", "", "CUSIP_CANDIDATES_INVALID_OR_MISSING"),
    ("cusips", "INVALID", "CUSIP_CANDIDATES_INVALID_OR_MISSING"),
    ("cusips", "SYN000001,SYN000001", "CUSIP_CANDIDATES_INVALID_OR_MISSING"),
    ("firstadded", "2026-02-30", "CURRENT_METADATA_DATE_INVALID_OR_MISSING"),
    ("firstpricedate", "", "CURRENT_METADATA_DATE_INVALID_OR_MISSING"),
    ("lastpricedate", "2000-01-04", "BOUND_PRICE_DATE_OUTSIDE_SOURCE_PRICING_RANGE"),
    ("lastupdated", "unknown", "CURRENT_METADATA_DATE_INVALID_OR_MISSING"),
    ("name", " Synthetic issuer ", "SOURCE_FIELD_OUTER_WHITESPACE"),
])
def test_bad_identity_fields_preserve_named_candidate_refusals(tmp_path, field, value, reason):
    loaded, price, _session = capture(tmp_path, session=Session(valid_responses(edits={"QCOM": {field: value}})))
    qcom = loaded.identities[0]
    assert qcom.ticker == "QCOM" and qcom.source_row_count == 1
    assert reason in qcom.refusal_codes
    assert loaded.refused_count == 1 and loaded.matched_count == 6
    assert load(loaded, price) == loaded


@pytest.mark.parametrize("category", ["CEF", "ETN", "Domestic Common Stock", "ETF Equity Unknown"])
def test_own_etf_cannot_be_misclassified_as_stock_or_other_fund(tmp_path, category):
    loaded, _price, _session = capture(tmp_path, session=Session(valid_responses(edits={"SPY": {"category": category}})))
    spy = next(item for item in loaded.identities if item.ticker == "SPY")
    assert "INSTRUMENT_CATEGORY_UNRECOGNIZED" in spy.refusal_codes


@pytest.mark.parametrize("field,value", [("ticker", "OTHER"), ("name", "x" * 1025), ("name", "control\x01")])
def test_out_of_scope_or_structurally_unbounded_csv_aborts_before_second_request(tmp_path, field, value):
    responses = valid_responses(edits={"QCOM": {field: value}})
    session = Session(responses)
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        capture(tmp_path, session=session)
    assert len(session.calls) == 1
    assert not list((tmp_path / "identity").glob("*/manifest.json"))


@pytest.mark.parametrize("payload", [b"", b"\xff", b"<html>failure</html>", b'{"error":"failure"}',
                                       b"ticker,ticker\nQCOM,QCOM\n", b"\x00"])
def test_malformed_csv_is_not_persisted(tmp_path, payload):
    session = Session([Response(payload), valid_responses()[1]])
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        capture(tmp_path, session=session)
    assert len(session.calls) == 1 and not list((tmp_path / "identity").glob("*/*.csv"))


@pytest.mark.parametrize("mutation", ["host", "path", "query", "method", "history", "status", "encoding", "length"])
def test_transport_identity_encoding_status_and_length_refusals(tmp_path, mutation):
    first, second = valid_responses()
    full = "https://api.sharadar.com/v1.0/data/tickers?" + urlencode({**adapter._query("stocks"), "api_key": KEY})
    if mutation == "host":
        first.override_url = full.replace("api.sharadar.com", "untrusted.invalid")
    elif mutation == "path":
        first.override_url = full.replace("/tickers?", "/stocks?")
    elif mutation == "query":
        first.override_url = full + "&from=2026-10-06"
    elif mutation == "method":
        first.method = "POST"
    elif mutation == "history":
        first.history = [object()]
    elif mutation == "status":
        first.status_code = 302
    elif mutation == "encoding":
        first.headers = {"Content-Encoding": "gzip"}
    else:
        first.headers = {"Content-Length": "1"}
    session = Session([first, second])
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        capture(tmp_path, session=session)
    assert len(session.calls) == 1 and first.close_count == 1


def test_byte_row_limits_and_secret_echo_are_fail_closed(tmp_path, monkeypatch):
    price = price_capture(tmp_path)
    monkeypatch.setattr(adapter, "MAX_RESPONSE_BYTES", 8)
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="byte limit"):
        capture(tmp_path, price=price)
    monkeypatch.setattr(adapter, "MAX_RESPONSE_BYTES", 1024 * 1024)
    monkeypatch.setattr(adapter, "REQUEST_ROW_LIMIT", 2)
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="row limit"):
        adapter._parse_csv(csv_bytes([row("QCOM"), row("QCOM")]), "stocks")
    monkeypatch.setattr(adapter, "REQUEST_ROW_LIMIT", 100)
    session = Session([Response(KEY.encode()), valid_responses()[1]])
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="echoed a credential"):
        capture(tmp_path / "echo", session=session)


def test_provider_exception_is_redacted(tmp_path):
    session = Session([RuntimeError(KEY + " private response body")])
    with pytest.raises(adapter.SharadarIdentityCaptureError) as caught:
        capture(tmp_path, session=session)
    assert KEY not in str(caught.value) and "private response body" not in str(caught.value)
    assert caught.value.__cause__ is None and len(session.calls) == 1


def test_price_pin_is_checked_before_credentials_or_identity_request(tmp_path, monkeypatch):
    price = price_capture(tmp_path)
    monkeypatch.setattr(adapter, "PRICE_ARTIFACT_PATH", price.artifact_path)
    monkeypatch.setattr(adapter.source, "_api_key", lambda: pytest.fail("must not read credentials"))
    monkeypatch.setattr(adapter.source, "_new_session", lambda: pytest.fail("must not create Session"))
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="pinned digest"):
        adapter.capture_sharadar_identities()
    session = Session(valid_responses())
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        adapter._capture_sharadar_identities_for_test(
            artifact_root=tmp_path / "identity", price_artifact_path=price.artifact_path,
            expected_price_manifest_sha256="0" * 64, session=session, clock=clock(), api_key=KEY,
        )
    assert session.calls == []


@pytest.mark.parametrize("file", ["stocks.csv", "funds.csv", "manifest.json", "manifest.sha256"])
def test_corrupt_identity_leaf_fails_offline_authentication(tmp_path, file):
    loaded, price, _session = capture(tmp_path)
    leaf = loaded.artifact_path / file
    leaf.write_bytes(leaf.read_bytes() + b" ")
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        load(loaded, price)


def test_corrupt_external_price_leaf_fails_identity_loader(tmp_path):
    loaded, price, _session = capture(tmp_path)
    price_leaf = price.artifact_path / "stocks.csv"
    price_leaf.write_bytes(price_leaf.read_bytes().replace(b"123.45", b"123.46"))
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        load(loaded, price)


@pytest.mark.parametrize("mutation", ["unknown", "formal", "qc", "census", "price", "query", "clock"])
def test_rehashed_self_assertions_do_not_change_identity_contract(tmp_path, mutation):
    loaded, price, _session = capture(tmp_path)
    value = document(loaded)
    if mutation == "unknown":
        value["unknown"] = False
    elif mutation == "formal":
        value["formal_source_admitted"] = True
    elif mutation == "qc":
        value["qc_sid_resolved"] = True
    elif mutation == "census":
        value["identities"] = value["identities"][:-1]
    elif mutation == "price":
        value["price_capture_sha256"] = "0" * 64
    elif mutation == "query":
        value["responses"][0]["request_query"]["table"] = "funds"
    else:
        value["capture_completed_at"] = "2026-10-07T19:00:00.000001Z"
    changed_digest = repin_manifest(loaded, value)
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        load(loaded, price, digest=changed_digest)


@pytest.mark.parametrize("mutation", ["symlink", "hardlink", "file_mode", "dir_mode", "extra"])
def test_private_identity_inventory_boundary(tmp_path, mutation):
    loaded, price, _session = capture(tmp_path)
    leaf = loaded.artifact_path / "stocks.csv"
    if mutation == "symlink":
        outside = tmp_path / "outside.csv"
        leaf.rename(outside)
        leaf.symlink_to(outside)
    elif mutation == "hardlink":
        os.link(leaf, tmp_path / "extra-link.csv")
    elif mutation == "file_mode":
        leaf.chmod(0o644)
    elif mutation == "dir_mode":
        loaded.artifact_path.chmod(0o755)
    else:
        (loaded.artifact_path / "unreviewed").write_bytes(b"extra")
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        load(loaded, price)


@pytest.mark.parametrize("stage", ["sync", "loader", "ambiguous_link"])
def test_owned_completion_marker_is_revoked_after_postlink_failure(tmp_path, monkeypatch, stage):
    price = price_capture(tmp_path)
    if stage == "sync":
        original = adapter.source._fsync
        def fail(fd, label):
            if label == "identity capture publication":
                raise adapter.SharadarIdentityCaptureError("simulated sync failure")
            return original(fd, label)
        monkeypatch.setattr(adapter.source, "_fsync", fail)
    elif stage == "loader":
        monkeypatch.setattr(adapter, "load_sharadar_identity_capture", lambda *_args, **_kwargs: (_ for _ in ()).throw(
            adapter.SharadarIdentityCaptureError("simulated readback failure")))
    else:
        original = adapter.os.link
        def fail(src, dst, **kwargs):
            original(src, dst, **kwargs)
            raise OSError("simulated ambiguous link result")
        monkeypatch.setattr(adapter.os, "link", fail)
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        capture(tmp_path, price=price)
    assert not list((tmp_path / "identity").glob("*/manifest.json"))


def test_foreign_completion_marker_is_never_removed(tmp_path, monkeypatch):
    price = price_capture(tmp_path)
    original = adapter.os.link
    def foreign_marker(src, dst, **kwargs):
        fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=kwargs["dst_dir_fd"])
        os.write(fd, b"foreign marker")
        os.close(fd)
        return original(src, dst, **kwargs)
    monkeypatch.setattr(adapter.os, "link", foreign_marker)
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="ambiguous"):
        capture(tmp_path, price=price)
    assert next((tmp_path / "identity").glob("*/manifest.json")).read_bytes() == b"foreign marker"


def test_backward_clock_and_existing_capture_refuse_without_overwrite(tmp_path):
    loaded, price, _session = capture(tmp_path)
    before = (loaded.artifact_path / "manifest.json").read_bytes()
    session = Session(valid_responses())
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="already exists"):
        capture(tmp_path, price=price, session=session)
    assert session.calls == [] and (loaded.artifact_path / "manifest.json").read_bytes() == before
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="clock moved backwards"):
        capture(tmp_path / "backwards", capture_clock=clock(backwards=True))
    assert not list((tmp_path / "backwards" / "identity").glob("*/manifest.json"))


def test_production_owns_key_session_and_clears_inherited_authority(tmp_path, monkeypatch):
    import requests
    raw = requests.Session()
    raw.verify = False
    raw.cert = ("fixture-certificate", "fixture-key")
    raw.auth = ("fixture", "fixture")
    raw.proxies["https"] = "https://untrusted.invalid"
    raw.params["unexpected"] = "query"
    raw.cookies.set("unexpected", "cookie")
    raw.mount("https://api.sharadar.com", requests.adapters.HTTPAdapter(max_retries=3))
    raw.hooks["response"].append(lambda response, **_kwargs: response)
    calls = []
    monkeypatch.setattr(adapter, "_price_binding", lambda *_args, **_kwargs: calls.append("price") or {})
    monkeypatch.setattr(adapter, "DEFAULT_ARTIFACT_ROOT", tmp_path / "new-identity")
    monkeypatch.setattr(adapter.source, "_api_key", lambda: calls.append("key") or "owned-key-never-real")
    monkeypatch.setattr(adapter.source, "_new_session", lambda: raw)
    def core(**kwargs):
        assert calls == ["price", "key"]
        assert kwargs["transport"] == adapter.PRODUCTION_TRANSPORT
        assert kwargs["close_owned_session"] is True
        assert raw.trust_env is False and raw.verify is True and raw.cert is None and raw.auth is None
        assert not raw.proxies and not raw.params and not raw.cookies and not raw.headers and not raw.hooks
        assert set(raw.adapters) == {"https://"} and raw.get_adapter("https://api.sharadar.com").max_retries.total == 0
        kwargs["session"].close()
        return "construction test, not actual provider evidence"
    monkeypatch.setattr(adapter, "_capture_core", core)
    assert adapter.capture_sharadar_identities().startswith("construction test")


@pytest.mark.parametrize("method", ["get", "send", "get_adapter", "mount", "resolve_redirects"])
def test_production_rejects_session_instance_overrides(tmp_path, monkeypatch, method):
    import requests
    raw = requests.Session()
    setattr(raw, method, lambda *_args, **_kwargs: pytest.fail("no provider call"))
    monkeypatch.setattr(adapter, "_price_binding", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(adapter, "DEFAULT_ARTIFACT_ROOT", tmp_path / "new-identity")
    monkeypatch.setattr(adapter.source, "_api_key", lambda: "owned-key-never-real")
    monkeypatch.setattr(adapter.source, "_new_session", lambda: raw)
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="exact/owned"):
        adapter.capture_sharadar_identities()


def test_cli_never_prints_identity_values_or_credentials(tmp_path, monkeypatch, capsys):
    loaded, _price, _session = capture(tmp_path)
    monkeypatch.setattr(adapter, "capture_sharadar_identities", lambda: loaded)
    assert adapter._main([]) == 0
    output = capsys.readouterr()
    assert "requested=7 matched=7 refused=0" in output.out
    assert "qc_sid_resolved=false" in output.out
    for private in (KEY, "100001", "BBG000000001", "Synthetic issuer", "SYN000001"):
        assert private not in output.out
    assert output.err == ""


def test_header_only_responses_retain_all_seven_missing_names(tmp_path):
    responses = [Response(csv_bytes([])), Response(csv_bytes([]))]
    loaded, price, _session = capture(tmp_path, session=Session(responses))
    assert len(loaded.identities) == 7 and loaded.matched_count == 0 and loaded.refused_count == 7
    assert sum(response.row_count for response in loaded.responses) == 0
    assert all(item.refusal_codes == ("CURRENT_IDENTITY_MISSING",) for item in loaded.identities)
    assert load(loaded, price) == loaded


def test_offline_loader_rechecks_leaf_identity_after_census(tmp_path, monkeypatch):
    loaded, price, _session = capture(tmp_path)
    original = adapter._census
    calls = 0
    def replace_after_census(rows, **kwargs):
        nonlocal calls
        value = original(rows, **kwargs)
        calls += 1
        if calls == 2:
            leaf = loaded.artifact_path / "stocks.csv"
            replacement = loaded.artifact_path / "new-leaf.csv"
            replacement.write_bytes(leaf.read_bytes())
            replacement.chmod(0o600)
            replacement.replace(leaf)
        return value
    monkeypatch.setattr(adapter, "_census", replace_after_census)
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="identity changed|single-link file"):
        load(loaded, price)


def test_close_failure_is_redacted_without_completed_manifest(tmp_path):
    price = price_capture(tmp_path)
    binding = adapter._price_binding(price.artifact_path, price.manifest_sha256, synthetic=True)
    session = Session(valid_responses())
    def fail():
        raise RuntimeError(KEY + " private body")
    session.close = fail
    with pytest.raises(adapter.SharadarIdentityCaptureError) as caught:
        adapter._capture_core(
            artifact_root=tmp_path / "identity", price_artifact_path=price.artifact_path,
            price_binding=binding, session=session, key=KEY, clock=clock(),
            transport=adapter.TEST_TRANSPORT, close_owned_session=True,
        )
    assert "closure failed" in str(caught.value) and KEY not in str(caught.value)
    assert not list((tmp_path / "identity").glob("*/manifest.json"))


def test_synthetic_seam_does_not_accept_production_shaped_key(tmp_path):
    price = price_capture(tmp_path)
    session = Session(valid_responses())
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="synthetic test credential"):
        adapter._capture_sharadar_identities_for_test(
            artifact_root=tmp_path / "identity", price_artifact_path=price.artifact_path,
            expected_price_manifest_sha256=price.manifest_sha256, session=session,
            clock=clock(), api_key="production-shaped-but-not-secret-key",
        )
    assert session.calls == []


def test_header_diagnostic_one_exact_get_no_body_or_row_persistence(tmp_path, monkeypatch):
    fields = adapter.FIELDS + ("extra_schema_field",)
    values = {**row("QCOM"), "extra_schema_field": "DO_NOT_PRINT_PRIVATE_ROW_VALUE"}
    payload = csv_bytes([values], fields=fields, bom=True)
    response = Response(payload)
    session = Session([response])
    monkeypatch.setattr(adapter, "_parse_csv", lambda *_args: pytest.fail("no data-row parser"))
    monkeypatch.setattr(adapter.source, "_write_private_bytes", lambda *_args: pytest.fail("no body persistence"))
    result = adapter._inspect_stock_header_for_test(session=session, clock=clock(), api_key=KEY)
    assert len(session.calls) == 1 and response.close_count == 1
    url, options = session.calls[0]
    assert url == "https://api.sharadar.com/v1.0/data/tickers"
    assert options["params"] == {**adapter._query("stocks"), "api_key": KEY}
    assert result.header_fields == fields and result.body_byte_count == len(payload)
    assert result.body_sha256 == sha256_bytes(payload)
    assert result.body_persisted is False and result.source_capture_published is False
    assert result.point_in_time_proven is False and result.formal_source_admitted is False
    assert "DO_NOT_PRINT_PRIVATE_ROW_VALUE" not in repr(result)
    assert list(tmp_path.iterdir()) == []


def test_header_only_diagnostic_does_not_parse_later_csv_records():
    payload = b"table,ticker,extra\n\"unclosed private second record"
    assert adapter._stock_header(payload) == ("table", "ticker", "extra")


@pytest.mark.parametrize("payload", [
    b"", b"\xff", b"ticker,ticker\n", b"ticker,name with space\n",
    b"ticker,private/unsafe\n", b"ticker,100001\n", b"ticker,\"unclosed\n",
    b"ticker,\x00field\n", ("ticker," + "a" * 65 + "\n").encode(),
    (",".join("field" + str(index) for index in range(65)) + "\n").encode(),
])
def test_header_diagnostic_refuses_non_schema_or_unbounded_names(payload):
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        adapter._stock_header(payload)


def test_diagnostic_does_not_weaken_default_exact_fields(tmp_path):
    fields = adapter.FIELDS + ("extra_schema_field",)
    values = {**row("QCOM"), "extra_schema_field": "private-value"}
    payload = csv_bytes([values], fields=fields)
    assert adapter._stock_header(payload) == fields
    session = Session([Response(payload), valid_responses()[1]])
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="header differs"):
        capture(tmp_path, session=session)
    assert len(session.calls) == 1 and not list((tmp_path / "identity").glob("*/manifest.json"))


def test_header_diagnostic_clock_and_credentials_fail_closed():
    session = Session([valid_responses()[0]])
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="clock moved backwards"):
        adapter._inspect_stock_header_for_test(session=session, clock=clock(backwards=True), api_key=KEY)
    assert len(session.calls) == 1
    session = Session([valid_responses()[0]])
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="synthetic test credential"):
        adapter._inspect_stock_header_for_test(session=session, clock=clock(), api_key="not-secret-real-shaped-key")
    assert session.calls == []


def test_header_diagnostic_cli_prints_only_safe_schema_and_receipt(monkeypatch, capsys):
    payload = csv_bytes([row("QCOM")])
    result = adapter._inspect_stock_header_for_test(
        session=Session([Response(payload)]), clock=clock(), api_key=KEY,
    )
    monkeypatch.setattr(adapter, "inspect_sharadar_stock_header", lambda: result)
    monkeypatch.setattr(adapter, "capture_sharadar_identities", lambda: pytest.fail("no capture fallback"))
    assert adapter._main(["--inspect-stock-header"]) == 0
    output = capsys.readouterr()
    value = json.loads(output.out)
    assert value["header_fields"] == list(adapter.FIELDS) and value["body_sha256"] == sha256_bytes(payload)
    assert not value["body_persisted"] and not value["source_capture_published"]
    for private in (KEY, "Synthetic issuer", "BBG000000001", "SYN000001"):
        assert private not in output.out
    assert output.err == ""


def test_explicit_thirteen_field_profile_preserves_all_seven_figi_refusals(tmp_path):
    loaded, price, session = capture(tmp_path, without_figi=True)
    assert loaded.manifest_schema == adapter.SCHEMA_WITHOUT_FIGI
    assert loaded.requested_fields == adapter.FIELDS_WITHOUT_FIGI
    assert len(loaded.requested_fields) == 13 and "figi" not in loaded.requested_fields
    assert loaded.matched_count == 0 and loaded.refused_count == 7
    assert tuple(item.ticker for item in loaded.identities) == ALL
    assert all(item.composite_figi is None for item in loaded.identities)
    assert all(item.refusal_codes == ("COMPOSITE_FIGI_INVALID_OR_MISSING",)
               for item in loaded.identities)
    value = document(loaded)
    assert value["schema"] == adapter.SCHEMA_WITHOUT_FIGI
    assert value["fields"] == list(adapter.FIELDS_WITHOUT_FIGI)
    assert value["refusal_reason_counts"] == {"COMPOSITE_FIGI_INVALID_OR_MISSING": 7}
    assert all(value[flag] is False for flag in adapter.FALSE_FLAGS)
    for (role, tickers), (url, options) in zip(adapter.ROLE_TICKERS, session.calls, strict=True):
        assert url == "https://api.sharadar.com/v1.0/data/tickers"
        assert options["params"] == {
            "format": "csv", "table": role, "ticker": ",".join(tickers),
            "fields": ",".join(adapter.FIELDS_WITHOUT_FIGI), "sort": "ticker.asc",
            "skip": "0", "limit": "100", "api_key": KEY,
        }
        assert options["allow_redirects"] is False and options["verify"] is True
        payload = (loaded.artifact_path / (role + ".csv")).read_bytes()
        parsed = adapter._parse_csv(payload, role, schema=adapter.SCHEMA_WITHOUT_FIGI)
        assert all("figi" not in candidate for candidate in parsed)
        for candidate in parsed:
            item = next(item for item in loaded.identities if item.ticker == candidate["ticker"])
            actual_hash = sha256_bytes(canonical_json_bytes(candidate))
            assert item.source_row_sha256s == (actual_hash,)
            assert actual_hash != sha256_bytes(canonical_json_bytes({**candidate, "figi": ""}))
    assert load(loaded, price) == loaded
    assert "BBG" not in repr(loaded) and "Synthetic issuer" not in repr(loaded)


def test_default_fourteen_field_contract_remains_unchanged(tmp_path):
    loaded, price, session = capture(tmp_path)
    assert loaded.manifest_schema == adapter.SCHEMA and loaded.requested_fields == adapter.FIELDS
    assert loaded.matched_count == 7 and loaded.refused_count == 0
    assert adapter._query("stocks")["fields"] == ",".join(adapter.FIELDS)
    assert document(loaded)["schema"] == adapter.SCHEMA
    assert "figi" in document(loaded)["fields"]
    assert len(session.calls) == 2 and load(loaded, price) == loaded


@pytest.mark.parametrize("without_figi", [False, True])
def test_mismatched_profile_header_refuses_without_fallback_or_second_get(tmp_path, without_figi):
    fields = adapter.FIELDS if without_figi else adapter.FIELDS_WITHOUT_FIGI
    session = Session(valid_responses(fields=fields))
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="header differs"):
        capture(tmp_path, session=session, without_figi=without_figi)
    assert len(session.calls) == 1
    assert session.calls[0][1]["params"]["fields"] == ",".join(
        adapter.FIELDS_WITHOUT_FIGI if without_figi else adapter.FIELDS)
    assert not list((tmp_path / "identity").glob("*/*.csv"))
    assert not list((tmp_path / "identity").glob("*/manifest.json"))


@pytest.mark.parametrize("mutation", ["schema", "fields", "query", "figi", "qc", "formal"])
def test_thirteen_profile_loader_refuses_rehashed_contract_or_admission_changes(tmp_path, mutation):
    loaded, price, _session = capture(tmp_path, without_figi=True)
    value = document(loaded)
    if mutation == "schema":
        value["schema"] = adapter.SCHEMA
    elif mutation == "fields":
        value["fields"] = list(adapter.FIELDS)
    elif mutation == "query":
        value["responses"][0]["request_query"]["fields"] = ",".join(adapter.FIELDS)
    elif mutation == "figi":
        value["identities"][0]["composite_figi"] = row("QCOM")["figi"]
    elif mutation == "qc":
        value["qc_sid_resolved"] = True
    else:
        value["formal_source_admitted"] = True
    digest = repin_manifest(loaded, value)
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        load(loaded, price, digest=digest)


@pytest.mark.parametrize("mutation", ["permaticker", "cusips"])
def test_thirteen_profile_preserves_every_collision_member(tmp_path, mutation):
    edits = {"SPY": {mutation: row("QCOM")[mutation]}, "QQQ": {mutation: row("QCOM")[mutation]}}
    responses = valid_responses(fields=adapter.FIELDS_WITHOUT_FIGI, edits=edits)
    loaded, price, _session = capture(tmp_path, session=Session(responses), without_figi=True)
    expected = ("CROSS_NAME_PERMANENT_ID_COLLISION" if mutation == "permaticker"
                else "CROSS_NAME_CUSIP_CANDIDATE_COLLISION")
    for item in loaded.identities:
        assert "COMPOSITE_FIGI_INVALID_OR_MISSING" in item.refusal_codes
        if item.ticker in {"QCOM", "SPY", "QQQ"}:
            assert expected in item.refusal_codes
            assert "DIRECT_STOCK_OWN_ETF_IDENTITY_COLLISION" in item.refusal_codes
        else:
            assert item.refusal_codes == ("COMPOSITE_FIGI_INVALID_OR_MISSING",)
    assert load(loaded, price) == loaded


def test_thirteen_profile_missing_ambiguous_bad_source_metadata_remain_refusals(tmp_path):
    responses = [Response(csv_bytes([], fields=adapter.FIELDS_WITHOUT_FIGI)),
                 Response(csv_bytes([row(name) for name in ALL[1:]] +
                                    [{**row("SPY"), "permaticker": row("QQQ")["permaticker"]}],
                                    fields=adapter.FIELDS_WITHOUT_FIGI))]
    loaded, price, _session = capture(tmp_path, session=Session(responses), without_figi=True)
    by_name = {item.ticker: item for item in loaded.identities}
    assert by_name["QCOM"].refusal_codes == ("COMPOSITE_FIGI_INVALID_OR_MISSING", "CURRENT_IDENTITY_MISSING")
    assert "CURRENT_IDENTITY_AMBIGUOUS" in by_name["SPY"].refusal_codes
    assert "CROSS_NAME_PERMANENT_ID_COLLISION" in by_name["SPY"].refusal_codes
    assert "CROSS_NAME_PERMANENT_ID_COLLISION" in by_name["QQQ"].refusal_codes
    assert loaded.refused_count == 7 and load(loaded, price) == loaded
    bad = valid_responses(fields=adapter.FIELDS_WITHOUT_FIGI, edits={"QCOM": {"table": "SF1", "category": "ADR", "currency": "CAD"}})
    rejected, _price, _session = capture(tmp_path / "bad", session=Session(bad), without_figi=True)
    assert set(rejected.identities[0].refusal_codes) == {
        "COMPOSITE_FIGI_INVALID_OR_MISSING", "SOURCE_TABLE_UNRECOGNIZED",
        "INSTRUMENT_CATEGORY_UNRECOGNIZED", "USD_CURRENCY_UNPROVEN",
    }


def test_thirteen_profile_holds_external_price_and_capture_path_pins(tmp_path, monkeypatch):
    loaded, price, _session = capture(tmp_path, without_figi=True)
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="pinned digest"):
        load(loaded, price, digest="0" * 64)
    moved = loaded.artifact_path.with_name(loaded.artifact_path.name + "-other")
    loaded.artifact_path.rename(moved)
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="manifest/path"):
        adapter.load_sharadar_identity_capture(moved, expected_manifest_sha256=loaded.manifest_sha256,
                                               price_artifact_path=price.artifact_path)
    monkeypatch.setattr(adapter, "PRICE_ARTIFACT_PATH", price.artifact_path)
    monkeypatch.setattr(adapter.source, "_api_key", lambda: pytest.fail("price pin before credentials"))
    monkeypatch.setattr(adapter, "_owned_session", lambda: pytest.fail("price pin before transport"))
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="pinned digest"):
        adapter.capture_sharadar_identities_without_figi()


def test_thirteen_profile_rejects_non_bool_selector_before_source_or_contact(tmp_path):
    session = Session(valid_responses(fields=adapter.FIELDS_WITHOUT_FIGI))
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="selector must be a bool"):
        adapter._capture_sharadar_identities_for_test(
            artifact_root=tmp_path / "identity", price_artifact_path=tmp_path / "no-price",
            expected_price_manifest_sha256="0" * 64, session=session, clock=clock(),
            api_key=KEY, without_figi=1,
        )
    assert session.calls == [] and list(tmp_path.iterdir()) == []


def test_thirteen_profile_cli_is_explicit_safe_and_excludes_header_mode(tmp_path, monkeypatch, capsys):
    loaded, _price, _session = capture(tmp_path, without_figi=True)
    monkeypatch.setattr(adapter, "capture_sharadar_identities_without_figi", lambda: loaded)
    monkeypatch.setattr(adapter, "capture_sharadar_identities", lambda: pytest.fail("no default fallback"))
    monkeypatch.setattr(adapter, "inspect_sharadar_stock_header", lambda: pytest.fail("no diagnostic fallback"))
    assert adapter._main(["--without-figi"]) == 0
    output = capsys.readouterr()
    assert "requested=7 matched=0 refused=7" in output.out
    assert "COMPOSITE_FIGI_INVALID_OR_MISSING:7" in output.out
    assert "qc_sid_resolved=false" in output.out
    for private in (KEY, "100001", "BBG000000001", "Synthetic issuer", "SYN000001"):
        assert private not in output.out
    assert output.err == ""
    with pytest.raises(SystemExit) as caught:
        adapter._main(["--without-figi", "--inspect-stock-header"])
    assert caught.value.code == 2


@pytest.mark.parametrize("schema", ["unknown", None, 2])
def test_unknown_schema_profile_never_constructs_query_or_reads_source(schema):
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="profile is not supported"):
        adapter._query("stocks", schema=schema)


def census_rows(*, edits=None, schema=adapter.SCHEMA, extra_funds=()):
    edits = edits or {}
    return tuple((role, tuple(
        {field: candidate[field] for field in adapter._fields(schema)}
        for candidate in [
            *({**row(ticker), **edits.get(ticker, {})} for ticker in tickers),
            *(extra_funds if role == "funds" else ()),
        ]
    )) for role, tickers in adapter.ROLE_TICKERS)


@pytest.mark.parametrize("value", [
    "SYN000001,broken", "broken,SYN000001", "SYN000001 SYN000002",
    "SYN000002  SYN000001", "SYN000001,,SYN000002", "[SYN000001]",
    "SYN000001;broken", "SYN000001,SYN000001",
])
def test_v3_malformed_cusip_field_poisons_all_collision_members(value):
    rows = census_rows(edits={"SPY": {"cusips": value}})
    by_name = {item.ticker: item for item in adapter._census(rows, schema=adapter.SCHEMA_STRICT_CUSIPS)}
    assert "CUSIP_CANDIDATES_INVALID_OR_MISSING" in by_name["SPY"].refusal_codes
    assert by_name["SPY"].cusip_candidates == ()
    for ticker in ("QCOM", "SPY"):
        assert "CROSS_NAME_CUSIP_CANDIDATE_COLLISION" in by_name[ticker].refusal_codes
        assert "DIRECT_STOCK_OWN_ETF_IDENTITY_COLLISION" in by_name[ticker].refusal_codes
        assert by_name[ticker].status == "refused_current_candidate"
    assert by_name["XLE"].status == "matched_current_candidate"


@pytest.mark.parametrize("value", [
    "SYN000008, SYN000009", "SYN000008 ,SYN000009", " SYN000008", "SYN000008 ",
    "SYN000008,\tSYN000009", "SYN000008,\u00a0SYN000009",
])
def test_v3_cusip_whitespace_refuses_without_normalization(value):
    by_name = {item.ticker: item for item in adapter._census(
        census_rows(edits={"SPY": {"cusips": value}}), schema=adapter.SCHEMA_STRICT_CUSIPS,
    )}
    assert "CUSIP_CANDIDATES_INVALID_OR_MISSING" in by_name["SPY"].refusal_codes
    assert by_name["SPY"].cusip_candidates == ()


@pytest.mark.parametrize("schema,value,expected", [
    (adapter.SCHEMA, "SYN000001,broken", "5e93e720beddcf142773898f8f0451119b32ceb73c2bb10f9a1b3ab8575081f6"),
    (adapter.SCHEMA, "SYN000008, SYN000009", "b37abaa1d2738aef437c84c4cc0267df8e3567dffe3c849ff490934bdac59b50"),
    (adapter.SCHEMA_WITHOUT_FIGI, "SYN000001,broken", "c3d195d8838c8fe04585cd4779a839b1e6664c5b4f11513a17775f96ec2741ce"),
    (adapter.SCHEMA_WITHOUT_FIGI, "SYN000008, SYN000009", "80713fdb2bbd581f63ed526f18cd70399af9234cc989c948d130890f8f272590"),
])
def test_frozen_v1_v2_cusip_interpretations_keep_exact_disposition_bytes(schema, value, expected):
    # Baseline 64b5a355 synthetic dispositions, including the historical limitations.
    result = adapter._census(census_rows(edits={"SPY": {"cusips": value}}, schema=schema), schema=schema)
    assert sha256_bytes(canonical_json_bytes([dataclasses.asdict(item) for item in result])) == expected


@pytest.mark.parametrize("value", ["SYN0000010", "0SYN000001", "xSYN000001", "SYN000001x", "SYN000 001"])
def test_v3_does_not_extract_substrings_or_join_split_cusips(value):
    by_name = {item.ticker: item for item in adapter._census(
        census_rows(edits={"SPY": {"cusips": value}}), schema=adapter.SCHEMA_STRICT_CUSIPS,
    )}
    assert by_name["QCOM"].refusal_codes == ()
    assert by_name["SPY"].refusal_codes == ("CUSIP_CANDIDATES_INVALID_OR_MISSING",)
    assert by_name["SPY"].cusip_candidates == ()


def test_v3_ambiguous_invalid_row_still_poisons_every_stock_and_fund_owner():
    ambiguous = {**row("SPY"), "cusips": "broken,SYN000001 SYN000003", "category": "CEF"}
    by_name = {item.ticker: item for item in adapter._census(
        census_rows(extra_funds=(ambiguous,)), schema=adapter.SCHEMA_STRICT_CUSIPS,
    )}
    assert "CURRENT_IDENTITY_AMBIGUOUS" in by_name["SPY"].refusal_codes
    assert by_name["SPY"].cusip_candidates == ()
    for ticker in ("QCOM", "SPY", "QQQ"):
        assert "CROSS_NAME_CUSIP_CANDIDATE_COLLISION" in by_name[ticker].refusal_codes
    for ticker in ("QCOM", "SPY"):
        assert "DIRECT_STOCK_OWN_ETF_IDENTITY_COLLISION" in by_name[ticker].refusal_codes
    assert "DIRECT_STOCK_OWN_ETF_IDENTITY_COLLISION" not in by_name["QQQ"].refusal_codes


def test_v3_exact_comma_list_admission_and_collision_refusals():
    by_name = {item.ticker: item for item in adapter._census(census_rows(edits={
        "QCOM": {"cusips": "SYN000009,SYN000008"},
        "SPY": {"cusips": "SYN000010,SYN000003"},
    }), schema=adapter.SCHEMA_STRICT_CUSIPS)}
    assert by_name["QCOM"].cusip_candidates == ("SYN000008", "SYN000009")
    assert by_name["QCOM"].refusal_codes == ()
    for ticker in ("SPY", "QQQ"):
        assert by_name[ticker].refusal_codes == ("CROSS_NAME_CUSIP_CANDIDATE_COLLISION",)


def test_v3_capture_roundtrip_preserves_raw_rows_and_declares_prospective_semantics(tmp_path):
    edits = {"SPY": {"cusips": "SYN000001,broken"}, "XLE": {"cusips": "SYN000008, SYN000009"}}
    loaded, price, session = capture(tmp_path, session=Session(valid_responses(edits=edits)), strict_cusips=True)
    assert loaded.manifest_schema == adapter.SCHEMA_STRICT_CUSIPS
    assert loaded.requested_fields == adapter.FIELDS
    assert loaded.matched_count == 4 and loaded.refused_count == 3
    value = document(loaded)
    assert value["schema"] == "arv2-sharadar-seven-current-identities-v3"
    assert value["cusip_parser_semantics"] == "exact_comma_separated_ASCII_shape_tokens_without_whitespace_normalization"
    assert value["cusip_collision_semantics"] == "bounded_shape_tokens_from_every_row_for_refusal_only_not_admission"
    assert all(value[flag] is False for flag in adapter.FALSE_FLAGS)
    for role, _tickers in adapter.ROLE_TICKERS:
        payload = (loaded.artifact_path / (role + ".csv")).read_bytes()
        parsed = adapter._parse_csv(payload, role, schema=adapter.SCHEMA_STRICT_CUSIPS)
        for candidate in parsed:
            item = next(item for item in loaded.identities if item.ticker == candidate["ticker"])
            assert item.source_row_sha256s == (sha256_bytes(canonical_json_bytes(candidate)),)
            if candidate["ticker"] in edits:
                assert candidate["cusips"] == edits[candidate["ticker"]]["cusips"]
    for (role, _tickers), (_url, options) in zip(adapter.ROLE_TICKERS, session.calls, strict=True):
        assert options["params"] == {**adapter._query(role), "api_key": KEY}
    assert len(session.calls) == 2 and load(loaded, price) == loaded


@pytest.mark.parametrize("mutation", ["schema", "parser", "collision", "refusal"])
def test_v3_loader_rejects_rehashed_semantic_or_disposition_changes(tmp_path, mutation):
    loaded, price, _session = capture(tmp_path, strict_cusips=True)
    value = document(loaded)
    if mutation == "schema":
        value["schema"] = adapter.SCHEMA
    elif mutation == "parser":
        del value["cusip_parser_semantics"]
    elif mutation == "collision":
        value["cusip_collision_semantics"] = "whole_field_only"
    else:
        value["identities"][0]["refusal_codes"] = ["invented"]
    with pytest.raises(adapter.SharadarIdentityCaptureError):
        load(loaded, price, digest=repin_manifest(loaded, value))


def test_v3_fourteen_field_profile_has_no_thirteen_field_fallback(tmp_path):
    session = Session(valid_responses(fields=adapter.FIELDS_WITHOUT_FIGI))
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="header differs"):
        capture(tmp_path, session=session, strict_cusips=True)
    assert len(session.calls) == 1
    assert not list((tmp_path / "identity").glob("*/manifest.json"))


@pytest.mark.parametrize("strict_cusips,without_figi", [(1, False), (True, True)])
def test_v3_invalid_selector_refuses_before_price_or_provider(tmp_path, strict_cusips, without_figi):
    session = Session(valid_responses())
    with pytest.raises(adapter.SharadarIdentityCaptureError, match="selector must be a bool|mutually exclusive"):
        adapter._capture_sharadar_identities_for_test(
            artifact_root=tmp_path / "identity", price_artifact_path=tmp_path / "absent-price",
            expected_price_manifest_sha256="0" * 64, session=session, clock=clock(), api_key=KEY,
            strict_cusips=strict_cusips, without_figi=without_figi,
        )
    assert session.calls == [] and list(tmp_path.iterdir()) == []


def test_v3_public_api_explicitly_selects_only_v3(monkeypatch):
    calls = []
    monkeypatch.setattr(adapter, "_capture_production", lambda schema: calls.append(schema) or "synthetic")
    assert adapter.capture_sharadar_identities_strict_cusips() == "synthetic"
    assert calls == [adapter.SCHEMA_STRICT_CUSIPS]


def test_v3_cli_requires_explicit_profile_and_never_prints_identifiers(tmp_path, monkeypatch, capsys):
    loaded, _price, _session = capture(tmp_path, strict_cusips=True)
    monkeypatch.setattr(adapter, "capture_sharadar_identities_strict_cusips", lambda: loaded)
    monkeypatch.setattr(adapter, "capture_sharadar_identities", lambda: pytest.fail("no default fallback"))
    monkeypatch.setattr(adapter, "capture_sharadar_identities_without_figi", lambda: pytest.fail("no v2 fallback"))
    assert adapter._main(["--strict-cusips"]) == 0
    output = capsys.readouterr()
    assert "requested=7 matched=7 refused=0" in output.out
    assert "qc_sid_resolved=false" in output.out
    for private in (KEY, "100001", "BBG000000001", "Synthetic issuer", "SYN000001"):
        assert private not in output.out
    assert output.err == ""
    for other in ("--without-figi", "--inspect-stock-header"):
        with pytest.raises(SystemExit) as caught:
            adapter._main(["--strict-cusips", other])
        assert caught.value.code == 2
