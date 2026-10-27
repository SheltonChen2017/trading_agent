"""Invented fixed-source capability probes; native denials are mandatory."""
from copy import deepcopy
from email.message import Message
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

if os.name != "posix":
    pytest.skip("IBWIN-CR01: macOS/POSIX custody support", allow_module_level=True)

from research import insider_buying_pilot_massive_evidence_probe_v2 as m

HEAD = "a" * 40
TOKEN = "invented_probe_key_20261027+/!"


def _credential(fixture=True):
    return m.prior.KeychainCredential("massive", TOKEN, fixture)


def _body(ordinal):
    kind = m.REQUESTS[ordinal - 1][0]
    row = {"accession_number": "0000320193-20-000099", "cik": "0000320193", "form_type": "4",
        "filing_date": "2020-10-08", "filing_url": "https://www.sec.gov/Archives/edgar/data/320193/0000320193-20-000099.txt",
        "ticker": "AAPL", "issuer_name": "Invented Apple"}
    if kind == "form4":
        row.pop("ticker"); row["issuer_cik"] = row.pop("cik")
        row.update(tickers=["AAPL"], transaction_value=123456.125, transaction_shares=50,
            transaction_price_per_share=2469.1225, aff_10b5_one=False, owner_cik="0000000001",
            transaction_date="2020-10-07", date_of_original_submission=None,
            footnotes=[{"id": "F1", "description": "Invented source note"}])
    if kind == "reference":
        row = {"ticker": "AAPL", "cik": "0000320193", "locale": "us", "market": "stocks", "active": True,
            "name": "Invented Apple", "type": "CS", "primary_exchange": "XNAS", "share_class_figi": "BBG000B9XRY4",
            "last_updated_utc": "2026-10-20T00:00:00Z"}
    return {"status": "OK", "request_id": "invented", "results": [row]}


def _identity(root):
    sources = {"invented.py": "b" * 64}
    return {"root": str(root), "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": m._sha(m._raw(sources))}


def _output(root):
    return root.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)


def _run(root, *, reader=None, transport=None, identity=None):
    def default_transport(url, credential):
        ordinal = next(i for i, (_, expected) in enumerate(m.REQUESTS, 1) if url == expected)
        return m.prior.date_probe.ProviderMetadataResponse(200, m._raw(_body(ordinal)), True)
    return m.run_probe(HEAD, root=root, identity=identity or (lambda head, root: _identity(root)),
        credential_reader=reader or (lambda _: _credential()), transport=transport or default_transport,
        clock=lambda: "2026-10-27T00:00:00Z")


def _snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_fixed_fresh_three_requests_one_key_and_private_metadata_only_custody(tmp_path):
    calls = []
    def reader(provider):
        assert provider == "massive" and (_output(tmp_path) / "credential-read-started.json").is_file()
        calls.append("key"); return _credential()
    def transport(url, credential):
        ordinal = len(calls)
        assert url == m.REQUESTS[ordinal - 1][1] and credential == _credential() and TOKEN not in url
        assert (_output(tmp_path) / f"{ordinal:02d}-started.json").is_file()
        calls.append(url)
        return m.prior.date_probe.ProviderMetadataResponse(200, m._raw(_body(ordinal)), True)
    result = _run(tmp_path, reader=reader, transport=transport)
    assert len(calls) == 4 and calls[0] == "key"
    assert result["transport_invocation_count"] == 3 and result["unattempted_requests"] == 0
    assert result["status"] == "completed-capability-probe" and result["fixture_only"] is True
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    assert result["research_looks"] == result["qc_jobs"] == result["backtests"] == 0
    assert result["source_financial_values_interpreted"] is False
    assert result["results"][2]["metadata"]["source_identity"]["issuer_cik"] == "0000320193"
    assert "transaction_value" in result["results"][2]["metadata"]["row_field_names"]
    assert b"123456" not in m._raw(result)
    assert (_output(tmp_path).stat().st_mode & 0o777) == 0o700
    for name, digest in result["published_leaf_sha256"].items():
        leaf = _output(tmp_path) / name
        assert leaf.stat().st_mode & 0o777 == 0o600 and leaf.stat().st_nlink == 1
        assert m._sha(leaf.read_bytes()) == digest
    assert json.loads((_output(tmp_path) / "complete.json").read_bytes()) == result
    assert TOKEN.encode() not in b"".join(_snapshot(tmp_path).values())


@pytest.mark.parametrize("ordinal", [1, 2, 3])
@pytest.mark.parametrize("kind", ["http", "partial", "unknown", "empty"])
def test_first_refusal_or_underfill_stops_all_remaining_requests(tmp_path, ordinal, kind):
    calls = []
    def transport(url, _):
        number = len(calls) + 1; calls.append(url); body = _body(number)
        if number == ordinal:
            if kind == "http": return m.prior.date_probe.ProviderMetadataResponse(403, TOKEN.encode(), False)
            if kind == "partial": return m.prior.date_probe.ProviderMetadataResponse(200, TOKEN.encode(), False)
            if kind == "unknown": body["outcome_return"] = 1
            if kind == "empty": body["results"] = []
        return m.prior.date_probe.ProviderMetadataResponse(200, m._raw(body), True)
    result = _run(tmp_path, transport=transport)
    assert len(calls) == result["transport_invocation_count"] == ordinal
    assert result["unattempted_requests"] == 3 - ordinal and result["status"] == "stopped-capability-probe"
    assert not (_output(tmp_path) / f"{ordinal + 1:02d}-started.json").exists()
    terminal = result["results"][-1]
    if kind == "empty":
        assert terminal["disposition"] == "requested_day_underfill" and terminal["metadata"]["result_count"] == 0
    else:
        assert terminal["metadata"] is terminal["body_sha256"] is terminal["body_size_bytes"] is None
        assert not (_output(tmp_path) / f"{ordinal:02d}-response.json").exists()
    assert TOKEN.encode() not in b"".join(_snapshot(tmp_path).values())


@pytest.mark.parametrize("ordinal", [1, 2, 3])
def test_cursor_is_recorded_but_never_followed(tmp_path, ordinal):
    calls = []
    def transport(url, _):
        number = len(calls) + 1; calls.append(url); body = _body(number)
        if number == ordinal: body["next_url"] = url.split("?", 1)[0] + "?cursor=invented"
        return m.prior.date_probe.ProviderMetadataResponse(200, m._raw(body), True)
    result = _run(tmp_path, transport=transport)
    assert calls == [url for _, url in m.REQUESTS]
    assert result["results"][ordinal - 1]["metadata"]["has_unfollowed_next_page"] is True


@pytest.mark.parametrize("ordinal", [1, 2, 3])
@pytest.mark.parametrize("change", ["issuer", "date", "unknown", "cursor-origin", "count-bool", "two-results"])
def test_wrong_identity_unknown_financial_fields_and_envelope_refuse(ordinal, change):
    body = _body(ordinal); row = body["results"][0]
    kind = m.REQUESTS[ordinal - 1][0]
    if change == "issuer": row["issuer_cik" if kind == "form4" else "cik"] = "0000000001"
    elif change == "date": row["market_cap" if kind == "reference" else "filing_date"] = "2025-01-01"
    elif change == "unknown": row["future_return"] = 0.2
    elif change == "cursor-origin": body["next_url"] = "https://api.massive.com.evil.test/steal"
    elif change == "count-bool": body["count"] = True
    else: body["results"].append(deepcopy(row))
    with pytest.raises(m.MassiveEvidenceProbeError): m._projection(m._raw(body), _credential(), ordinal)


@pytest.mark.parametrize("value", [True, "123", [], {}, float("inf")])
def test_form4_source_numbers_are_opaque_lexemes_not_coerced(value):
    body = _body(3); body["results"][0]["transaction_value"] = value
    raw = json.dumps(body).encode()
    with pytest.raises(m.MassiveEvidenceProbeError): m._projection(raw, _credential(), 3)


def test_large_numeric_lexeme_never_becomes_float_or_decimal():
    raw = m._raw(_body(3)).replace(b'123456.125', b'1.23456789e99999')
    parsed = m.prior._json(raw)
    assert type(parsed["results"][0]["transaction_value"]) is m.prior._FloatLexeme
    result = m._projection(raw, _credential(), 3)
    assert result["numeric_financial_fields_interpreted"] is False
    assert b"99999" not in m._raw(result)


@pytest.mark.parametrize("ordinal", [1, 2, 3])
@pytest.mark.parametrize("encoding", ["literal", "percent", "double", "unicode"])
def test_credential_screening_precedes_all_response_hashing(monkeypatch, ordinal, encoding):
    body = _body(ordinal); row = body["results"][0]
    key = "name" if m.REQUESTS[ordinal - 1][0] == "reference" else "issuer_name"
    row[key] = TOKEN if encoding in {"literal", "unicode"} else quote(TOKEN, safe="")
    if encoding == "double": row[key] = quote(row[key], safe="")
    raw = m._raw(body)
    if encoding == "unicode":
        raw = raw.replace(json.dumps(TOKEN).encode(), ('"' + ''.join("\\u%04x" % ord(c) for c in TOKEN) + '"').encode())
    monkeypatch.setattr(m, "_sha", lambda *_: pytest.fail("echo must not reach hash"))
    with pytest.raises(m.MassiveEvidenceProbeError, match="^source_json_or_credential_echo_refused$"):
        m._projection(raw, _credential(), ordinal)


def test_consumed_namespace_never_repeats_key_or_dispatch(tmp_path):
    _run(tmp_path); snapshot = _snapshot(tmp_path)
    with pytest.raises(m.MassiveEvidenceProbeError):
        _run(tmp_path, reader=lambda *_: pytest.fail("key repeat"), transport=lambda *_: pytest.fail("dispatch repeat"))
    assert _snapshot(tmp_path) == snapshot


@pytest.mark.parametrize("value", [None, m.prior.KeychainCredential("eodhd", TOKEN, True), _credential(False)])
def test_bad_key_consumes_claim_without_dispatch(tmp_path, value):
    result = _run(tmp_path, reader=lambda _: value, transport=lambda *_: pytest.fail("bad key dispatch"))
    assert result["credential_read_observed"] is False and result["transport_invocation_count"] == 0
    assert result["unattempted_requests"] == 3


@pytest.mark.parametrize("root", [m.LANE_ROOT, m.LANE_ROOT.parent, m.LANE_ROOT / "invented", Path("/")])
def test_fixture_never_reaches_lane_or_ancestor(root):
    with pytest.raises(m.MassiveEvidenceProbeError, match="^invented_outside_lane_callbacks_required$"): _run(root)


@pytest.mark.parametrize("mutation", ["extra", "content", "mode", "restored-mtime"])
def test_custody_change_refuses_before_projection(tmp_path, mutation, monkeypatch):
    def transport(*_):
        leaf = _output(tmp_path) / "reservation.json"; original = leaf.stat()
        if mutation == "extra": (_output(tmp_path) / "foreign").write_bytes(b"x")
        elif mutation == "mode": leaf.chmod(0o644)
        else:
            leaf.write_bytes(leaf.read_bytes().replace(b'"maximum_attempts":3', b'"maximum_attempts":4'))
            if mutation == "restored-mtime": os.utime(leaf, ns=(original.st_atime_ns, original.st_mtime_ns))
        return m.prior.date_probe.ProviderMetadataResponse(200, m._raw(_body(1)), True)
    monkeypatch.setattr(m, "_projection", lambda *_: pytest.fail("mutated custody reached decode"))
    with pytest.raises(m.MassiveEvidenceProbeError): _run(tmp_path, transport=transport)


def test_source_identity_change_stops_before_credential(tmp_path):
    count = 0
    def identity(_, root):
        nonlocal count
        count += 1; value = _identity(root)
        if count > 1: value["head"] = "c" * 40
        return value
    with pytest.raises(m.MassiveEvidenceProbeError):
        _run(tmp_path, identity=identity, reader=lambda _: pytest.fail("changed identity key read"))


def test_production_transport_requires_exact_context_before_opener(monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *_: pytest.fail("no real opener"))
    with pytest.raises(m.MassiveEvidenceProbeError, match="^real_probe_context_required$"):
        m._default_transport(m.REQUESTS[0][1], _credential(), context=object(), ordinal=1)


def test_fixed_query_classes_and_predecessor_are_not_mutated():
    from urllib.parse import parse_qs, urlsplit
    queries = [parse_qs(urlsplit(url).query) for _, url in m.REQUESTS]
    assert queries[1]["cik"] == queries[2]["issuer_cik"] == ["0000320193"]
    assert queries[1]["filing_date.gte"] == queries[2]["filing_date.gte"] == ["2020-10-01"]
    assert queries[1]["filing_date.lte"] == queries[2]["filing_date.lte"] == ["2020-12-31"]
    assert queries[0]["ticker"] == ["AAPL"] and queries[0]["date"] == ["2021-01-04"]
    assert all(url != m.prior.URL for _, url in m.REQUESTS)
    assert m.prior.ASOF == "2020-01-02" and m.prior.AUDIT_ID != m.AUDIT_ID


@pytest.mark.parametrize("ordinal", [2, 3])
@pytest.mark.parametrize("day,allowed", [("2020-10-01", True), ("2020-12-31", True),
                                       ("2020-09-30", False), ("2021-01-01", False)])
def test_required_warmup_quarter_sample_boundaries(ordinal, day, allowed):
    body = _body(ordinal); body["results"][0]["filing_date"] = day
    if allowed:
        assert m._projection(m._raw(body), _credential(), ordinal)["source_identity"]["filing_date"] == day
    else:
        with pytest.raises(m.MassiveEvidenceProbeError, match="^requested_filing_identity_refused$"):
            m._projection(m._raw(body), _credential(), ordinal)


class _Response:
    def __init__(self, ordinal, *, status=200, url=None, raw=None, length=None):
        self.status, self.url = status, url or m.REQUESTS[ordinal - 1][1]
        self.raw = m._raw(_body(ordinal)) if raw is None else raw
        self.headers = Message(); self.headers["Content-Length"] = str(len(self.raw)) if length is None else length
        self.offset = self.reads = self.closes = 0

    def getcode(self): return self.status
    def geturl(self): return self.url
    def read(self, amount):
        self.reads += 1
        value = self.raw[self.offset:self.offset + amount]; self.offset += len(value); return value
    def close(self): self.closes += 1


def _direct_transport(monkeypatch, ordinal, *, response=None, mutate=None, opened=None):
    """Real transport/read function, invented leaves only, opener trapped first.

    No production directory descriptor is opened. The exact private context
    TYPE is retained, while its metadata check and leaf reader are replaced
    solely in this denied-network test. All actual journal predicates still run.
    """
    calls = [] if opened is None else opened
    stream = response or _Response(ordinal)
    class Opener:
        def open(self, item, timeout):
            assert item.full_url == m.REQUESTS[ordinal - 1][1] and timeout == 15
            assert item.get_method() == "GET" and item.get_header("Authorization") == "Bearer " + TOKEN
            assert item.get_header("Accept-encoding") == "identity"
            calls.append(item.full_url); return stream
    monkeypatch.setattr(m.request, "build_opener", lambda *_: Opener())  # unconditional: no actual transport
    context = m._Context.__new__(m._Context)
    context.root, context.fixture, context.identity = m.LANE_ROOT, False, m._identity
    context.baseline = _identity(m.LANE_ROOT)
    context.directory = SimpleNamespace(fd=987654321)
    context.check = lambda: None  # no actual root/profile/artifact I/O
    leaves = {"reservation.json": m._reservation(context.baseline, False)}
    published = {"reservation.json": m._sha(m._raw(leaves["reservation.json"]))}
    leaves["credential-read-started.json"] = {"schema": m.SCHEMA, "maximum_credential_reads": 1, "reservation_sha256": published["reservation.json"]}
    published["credential-read-started.json"] = m._sha(m._raw(leaves["credential-read-started.json"]))
    leaves["credential-read-completed.json"] = {"schema": m.SCHEMA, "fixture_only": False,
        "started_sha256": published["credential-read-started.json"], "credential_read_observed": True,
        "disposition": "configured-keychain-credential-read"}
    published["credential-read-completed.json"] = m._sha(m._raw(leaves["credential-read-completed.json"]))
    for previous in range(1, ordinal):
        raw = m._raw(_body(previous)); metadata = m._projection(raw, _credential(False), previous)
        leaves[f"{previous:02d}-started.json"] = m._started(previous, published["reservation.json"])
        published[f"{previous:02d}-started.json"] = m._sha(m._raw(leaves[f"{previous:02d}-started.json"]))
        leaves[f"{previous:02d}-response.json"] = _body(previous)
        published[f"{previous:02d}-response.json"] = m._sha(raw)
        leaves[f"{previous:02d}-metadata.json"] = metadata
        published[f"{previous:02d}-metadata.json"] = m._sha(m._raw(metadata))
        leaves[f"{previous:02d}-completed.json"] = {"schema": m.SCHEMA, "ordinal": previous, "http_status": 200,
            "started_sha256": published[f"{previous:02d}-started.json"], "disposition": "capability_metadata_observed",
            "metadata": deepcopy(metadata), "body_sha256": m._sha(raw), "body_size_bytes": len(raw),
            "untrusted_error_body_hashed_or_retained": False}
        published[f"{previous:02d}-completed.json"] = m._sha(m._raw(leaves[f"{previous:02d}-completed.json"]))
    leaves[f"{ordinal:02d}-started.json"] = m._started(ordinal, published["reservation.json"])
    published[f"{ordinal:02d}-started.json"] = m._sha(m._raw(leaves[f"{ordinal:02d}-started.json"]))
    if mutate: mutate(leaves, published)
    context.published = published
    def leaf(fd, name, cap):
        assert fd == 987654321 and cap == m.MAX_CONTROL_BYTES
        return m._raw(leaves[name]), ("invented",)
    monkeypatch.setattr(m.prior.publication, "_leaf", leaf)
    result = m._default_transport(m.REQUESTS[ordinal - 1][1], _credential(False), context=context, ordinal=ordinal)
    return result, stream, calls


@pytest.mark.parametrize("ordinal", [1, 2, 3])
def test_real_production_transport_body_reader_and_exact_journals_positive(monkeypatch, ordinal):
    result, stream, calls = _direct_transport(monkeypatch, ordinal)
    assert calls == [m.REQUESTS[ordinal - 1][1]] and stream.reads >= 2 and stream.closes == 1
    assert result.status == 200 and result.body_complete and result.body == m._raw(_body(ordinal))
    assert m._projection(result.body, _credential(False), ordinal)["result_count"] == 1


@pytest.mark.parametrize("mutation,code", [
    ("started", "observed_started_journal_required"), ("reservation", "observed_started_journal_required"),
    ("keyreceipt", "observed_started_journal_required"), ("missingprevious", "observed_started_journal_required"),
    ("previousmetadata", "preceding_capability_success_required"), ("boolprevious", "preceding_capability_success_required")])
def test_real_transport_refuses_wrong_journal_before_opener(monkeypatch, mutation, code):
    calls = []
    def mutate(leaves, published):
        if mutation == "started": leaves["02-started.json"]["ordinal"] = 1
        elif mutation == "reservation": leaves["reservation.json"]["requests"][1]["url"] += "&unexpected=true"
        elif mutation == "keyreceipt": leaves["credential-read-completed.json"]["credential_read_observed"] = 1
        elif mutation == "missingprevious": published.pop("01-response.json")
        elif mutation == "previousmetadata": leaves["01-metadata.json"]["result_count"] = 0
        else:
            leaves["01-metadata.json"]["result_count"] = True
            leaves["01-completed.json"]["metadata"]["result_count"] = True
    with pytest.raises(m.MassiveEvidenceProbeError, match="^" + code + "$"):
        _direct_transport(monkeypatch, 2, mutate=mutate, opened=calls)
    assert calls == []


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
def test_real_transport_non200_never_reads_or_hashes_error_body(monkeypatch, status):
    stream = _Response(1, status=status, raw=TOKEN.encode())
    result, stream, calls = _direct_transport(monkeypatch, 1, response=stream)
    assert len(calls) == 1 and stream.reads == 0 and stream.closes == 1
    assert result.status == status and result.body == b"" and result.body_complete is False
    assert result.disposition == ("redirect-refused" if status == 302 else None)


def test_real_transport_refuses_redirected_response_without_body_read(monkeypatch):
    stream = _Response(1, url="https://api.massive.com/other", raw=TOKEN.encode())
    result, stream, calls = _direct_transport(monkeypatch, 1, response=stream)
    assert len(calls) == 1 and stream.reads == 0 and stream.closes == 1
    assert result.body == b"" and result.disposition == "response-origin-mismatch"


@pytest.mark.parametrize("length,raw,code", [
    ("bad", b"x", "invalid-content-length"), (str(m.MAX_BODY_BYTES + 1), b"x", "oversized-response"),
    ("10", b"x", "truncated-response")])
def test_real_bounded_reader_refuses_framing_and_oversize(monkeypatch, length, raw, code):
    result, stream, calls = _direct_transport(monkeypatch, 1, response=_Response(1, raw=raw, length=length))
    assert len(calls) == 1 and stream.closes == 1 and result.disposition == code
    assert result.body == b"" and result.body_complete is False


def test_real_wall_alarm_bounds_a_stalled_body(monkeypatch):
    import signal
    import time
    original = signal.setitimer
    def short_alarm(which, seconds, interval=0):
        return original(which, min(seconds, .01) if seconds else 0, interval)
    monkeypatch.setattr(signal, "setitimer", short_alarm)
    stream = _Response(1)
    def stalled(_): time.sleep(.2); pytest.fail("wall alarm was not enforced")
    stream.read = stalled
    result, stream, calls = _direct_transport(monkeypatch, 1, response=stream)
    # The inherited reader honestly classifies the interrupted read as partial;
    # the real alarm still supplies the finite wall, and no body is retained.
    assert len(calls) == 1 and stream.closes == 1 and result.disposition == "partial-read"
    assert result.body == b"" and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
