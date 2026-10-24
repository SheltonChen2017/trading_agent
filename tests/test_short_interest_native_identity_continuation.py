"""Fabricated protected continuation custody/transport; no real sources or keys."""
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import zipfile

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_dated_identity as identity
import research.short_interest_etf.sharadar_securities_master as master
import scripts.capture_short_interest_native_identity as old_runtime
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError
from short_interest_capture_fixtures import portable_capture_platform

import scripts.continue_short_interest_native_identity as m
HEAD, NEW_HEAD = "f" * 40, "a" * 40
DATES = ("2023-10-31", "2023-11-15", "2023-11-30")
NOW = "2026-10-14T03:00:00Z"
SECRET = "fabricated-identity-continuation-secret"


def encoded(value):
    return canonical_json(value).encode()


def archive_index():
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("tickers.csv", "table,permaticker,ticker,exchange,isdelisted,category,figi\n"
                "stocks,1,SYN,XNYS,N,Domestic Common Stock Primary Class,BBG000000001\n")
    source = master.CapturedSharadarMasterArchive("tickers", target.getvalue(), master.request_sha256("download-tickers"))
    return identity.build_composite_native_index(source)


def historical(head, name):
    return ("fabricated committed " + head + " " + name).encode()


def body(following=None):
    value = {"status": "OK", "results": []}
    if following is not None:
        value["next_url"] = following
    return encoded(value)


def fixture():
    index = archive_index()
    protocol = old_runtime.protocol()
    protocol["settlement_dates_sha256"] = hash_payload(list(DATES))
    sha = hash_payload(protocol)
    code = hash_payload({"git_commit": HEAD, "files": [
        {"path": name, "sha256": hash_bytes(historical(HEAD, name))} for name in m.SOURCE_CODE_FILES]})
    start = {"schema": "si-native-dated-identity-start-v1", "code_head": HEAD, "remote_head": "1" * 40,
        "protocol_sha256": sha, "source_pins": protocol["source_pins"], "code_identity_sha256": code,
        "started_at": NOW, "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    refused = {"schema": "si-native-dated-identity-refusal-v1", "status": "dated_identity_capture_refused",
        "refused_at": NOW, "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    files = {"protocol.json": encoded(protocol), "started.json": encoded(start), "refused.json": encoded(refused)}
    pages, attempt = [], 0

    def received(number, active, ordinal, url, following=None):
        nonlocal attempt
        attempt += 1
        raw, name, at = body(following), m.prefix(number, active, ordinal), DATES[number - 1]
        request = m.descriptor(url)
        files[name + ".started.json"] = encoded({"schema": "si-native-identity-page-start-v1", "code_head": HEAD,
            "protocol_sha256": sha, "query_date": at, "active_panel": active, "ordinal": ordinal,
            "attempt": attempt, "request": request, "request_sha256": hash_payload(request), "started_at": NOW})
        files[name + ".received.json"] = encoded({"schema": "si-native-identity-page-received-v1", "query_date": at,
            "active_panel": active, "ordinal": ordinal, "request_sha256": hash_payload(request), "http_status": 200,
            "content_type": "application/json", "raw_path": name + ".raw", "raw_sha256": hash_bytes(raw),
            "raw_bytes": len(raw), "received_at": NOW})
        files[name + ".raw"] = raw
        return identity.CapturedDatedIdentityPage(at, active, ordinal, url, raw, NOW, NOW, 200, "application/json")

    for active in (True, False):
        pages.append(received(1, active, 1, m.initial_url(DATES[0], active)))
    files["date-001.qualified.private.json"] = identity.qualify_dated_identity(
        tuple(pages), index, query_date=DATES[0], started_at=NOW, retrieved_at=NOW).to_bytes()
    failed_url = identity.ENDPOINT + "?cursor=fabricated-exact-retained-cursor&date=" + DATES[1] + "&active=true"
    received(2, True, 1, m.initial_url(DATES[1], True), failed_url)
    request = m.descriptor(failed_url)
    name = m.prefix(2, True, 2)
    files[name + ".started.json"] = encoded({"schema": "si-native-identity-page-start-v1", "code_head": HEAD,
        "protocol_sha256": sha, "query_date": DATES[1], "active_panel": True, "ordinal": 2,
        "attempt": 4, "request": request, "request_sha256": hash_payload(request), "started_at": NOW})
    files[name + ".refused.json"] = encoded({"schema": "si-native-identity-page-refused-v1", "query_date": DATES[1],
        "active_panel": True, "ordinal": 2, "attempt": 4, "http_status": None, "refused_at": NOW,
        "code": "identity_page_refused_no_retry"})
    budget = encoded({"schema": "si-native-dated-identity-global-budget-v1", "code_head": HEAD, "remote_head": "1" * 40,
        "protocol_sha256": sha, "source_pins": protocol["source_pins"], "started_at": NOW,
        "maximum_attempts": identity.MAXIMUM_REQUESTS, "run_id": "fabricated-run", "restart_or_resume": False,
        "unused_slots_repurposable": False})
    args = {"expected_head": HEAD, "expected_protocol_sha256": sha, "expected_code_identity_sha256": code,
            "historical_code": historical, "dates": DATES, "dates_sha256": hash_payload(list(DATES)), "index": index,
            "local_guard": lambda: None, "completed_dates": 1, "failed_date_number": 2,
            "failed_active": True, "failed_ordinal": 2, "expected_attempts": 4,
            "budget_raw": budget, "budget_sha256": hash_bytes(budget)}
    return files, args


def repin(files, args):
    args = dict(args)
    args["byte_pins"] = {name: hash_bytes(raw) for name, raw in files.items()}
    args["inventory_sha256"] = hash_payload([{"name": name, "sha256": args["byte_pins"][name], "bytes": len(files[name])}
                                             for name in sorted(files)])
    return args


def source():
    files, args = fixture()
    return m.verify_parent(files, **repin(files, args))


class Harness:
    def __init__(self, source_value=None):
        self.source = source_value or source()
        self.saved, self.calls, self.claims, self.keys, self.events = {}, [], [], [], []
        self.tick = 0
        self.reply = lambda call, key, bound: (body(), "application/json", 200)
        self.on_publish = lambda name, raw: None

    def clock(self):
        self.tick += 1
        return (datetime(2026, 10, 14, 4, tzinfo=timezone.utc) + timedelta(seconds=self.tick)).isoformat().replace("+00:00", "Z")

    def local(self):
        self.events.append("local")

    def remote(self):
        self.events.append("remote")

    def claim(self, name, value):
        self.events.append("claim")
        self.claims.append((name, value))

    def publish(self, name, raw):
        assert name not in self.saved
        assert self.events[-1] == "local"
        self.events.append("publish:" + name)
        self.saved[name] = raw
        self.on_publish(name, raw)

    def key(self, provider):
        self.events.append("key")
        self.keys.append(provider)
        return KeychainSecret(SECRET)

    def request(self, call, key, bound):
        self.events.append("HTTP")
        self.calls.append(dict(call))
        assert bound == identity.MAXIMUM_RESPONSE_BYTES
        assert type(key) is KeychainSecret
        assert self.events[-3:-1] == ["remote", "local"]
        return self.reply(call, key, bound)

    def run(self, **changes):
        args = dict(expected_protocol_sha256=hash_payload(m.freeze_protocol(self.source)), code_head=NEW_HEAD,
                    code_identity_sha256="c" * 64, claim=self.claim, publish=self.publish,
                    get_secret=self.key, request=self.request, local_guard=self.local, remote_guard=self.remote, now=self.clock)
        args.update(changes)
        return m.capture_continuation(self.source, **args)


def test_replay_binds_original_reports_partial_chain_and_spent_failure():
    value = source().payload()
    assert value["source_attempts"] == 4 and value["source_received_pages"] == 3
    assert value["source_failure_category"] == "legacy_failure_unclassified"
    assert value["source_failure_http_status"] is None
    assert value["completed_reports"][0]["retrieved_at"] == NOW
    assert value["failed_request"]["url"].endswith("date=2023-11-15&active=true")


@pytest.mark.parametrize("name", ["date-001.qualified.private.json", "date-002-active-page-02.started.json",
                                  "date-002-active-page-02.refused.json", "budget"])
def test_bound_semantics_are_rebuilt_not_accepted_after_repin(name):
    files, args = fixture()
    if name == "budget":
        value = m.parsed(args["budget_raw"])
        value["unused_slots_repurposable"] = True
        args["budget_raw"] = encoded(value)
        args["budget_sha256"] = hash_bytes(args["budget_raw"])
    else:
        value = m.parsed(files[name])
        if "qualified" in name:
            value["authority"]["source_admitted"] = True
        elif "started" in name:
            value["request"]["url"] = identity.ENDPOINT + "?cursor=other"
            value["request_sha256"] = hash_payload(value["request"])
        else:
            value["http_status"] = 429
        files[name] = encoded(value)
    with pytest.raises((m.ContinuationRefusal, identity.NativeDatedIdentityError)):
        m.verify_parent(files, **repin(files, args))


def test_unregistered_source_byte_mutation_refuses_before_replay():
    files, args = fixture()
    args = repin(files, args)
    files["date-001-active-page-01.raw"] += b" "
    with pytest.raises(m.ContinuationRefusal, match="registered_parent_file_bytes"):
        m.verify_parent(files, **args)


@pytest.mark.parametrize("change", ["extra_failed_raw", "missing_report", "clock_inversion", "wrong_code"])
def test_original_complete_inventory_and_historical_identity_required(change):
    files, args = fixture()
    if change == "extra_failed_raw":
        files["date-002-active-page-02.raw"] = body()
    elif change == "missing_report":
        del files["date-001.qualified.private.json"]
    elif change == "clock_inversion":
        value = m.parsed(files["date-002-active-page-02.started.json"])
        value["started_at"] = "2026-10-14T02:59:59Z"
        files["date-002-active-page-02.started.json"] = encoded(value)
    else:
        args["historical_code"] = lambda head, name: b"different committed bytes"
    with pytest.raises(m.ContinuationRefusal):
        m.verify_parent(files, **repin(files, args))


@pytest.mark.parametrize("field", ["_metadata", "_partial", "_index"])
def test_parent_reflection_mutation_refuses_before_claim_key_or_HTTP(field):
    value = source()
    object.__setattr__(value, field, "changed" if field == "_metadata" else ())
    h = Harness.__new__(Harness)
    Harness.__init__(h, source_value=value)
    with pytest.raises(m.ContinuationRefusal):
        h.run()
    assert not h.calls and not h.keys and not h.claims and not h.saved


def test_manual_resume_once_no_old_recapture_and_all_dates_close():
    h = Harness()
    result = h.run()
    assert h.calls[0] == h.source.payload()["failed_request"]
    assert len(h.calls) == 4 and result["parent_attempts_consumed"] == 4
    assert result["new_attempts_consumed"] == 4 and result["cumulative_attempts_consumed"] == 8
    assert h.keys == ["massive"]
    assert h.events.index("claim") < h.events.index("publish:started.json") < h.events.index("key") < h.events.index("HTTP")
    assert "date-001.qualified.private.json" not in h.saved
    inventory = m.parsed(h.saved["inventory.private.json"])
    assert inventory["schema"] == "si-native-identity-continuation-inventory-v1"
    assert [item["query_date"] for item in inventory["dates"]] == list(DATES)
    assert inventory["dates"][0]["retrieved_at"] == NOW
    assert result["inventory_bytes_sha256"] == hash_bytes(h.saved["inventory.private.json"])
    assert result["inventory_payload_sha256"] == hash_payload(inventory)
    assert all(result[key] == 0 for key in ("outcome_looks", "qc_attempts"))
    assert result["source_admitted"] is result["ready_for_empirical_backtest"] is False
    assert h.events.count("remote") == len(h.calls) + 2


def test_duplicate_claim_reads_no_key_and_publishes_nothing():
    h = Harness()
    with pytest.raises(FileExistsError):
        h.run(claim=lambda *args: (_ for _ in ()).throw(FileExistsError("owned prior claim")))
    assert not h.saved and not h.keys and not h.calls


def test_missing_named_key_retains_owned_zero_new_attempt_refusal():
    h = Harness()
    with pytest.raises(ShortInterestKeychainError):
        h.run(get_secret=lambda provider: (_ for _ in ()).throw(ShortInterestKeychainError("fixed-key-unavailable")))
    refusal = m.parsed(h.saved["refused.json"])
    assert refusal["new_attempts_consumed"] == 0 and refusal["parent_attempts_consumed"] == 4
    assert refusal["failure_category"] == "credential_access_refused"
    assert not h.calls and "started.json" in h.saved


@pytest.mark.parametrize("code,status,expected", [("http_not_200", 403, "http_status_refused"),
        ("http_not_200", 429, "http_status_refused"), ("network_failure", None, "transport_unavailable")])
def test_fixed_failure_category_HTTP_status_and_no_retry(code, status, expected):
    h = Harness()
    h.reply = lambda *args: (_ for _ in ()).throw(SharadarCaptureRefusal(code, status=status))
    with pytest.raises(SharadarCaptureRefusal):
        h.run()
    failure = m.parsed(h.saved["date-002-active-page-02.refused.json"])
    assert failure["failure_category"] == expected and failure["http_status"] == status
    assert failure["cumulative_attempt"] == 5 and len(h.calls) == 1
    assert not any(name.endswith(".raw") or name.endswith(".received.json") for name in h.saved)
    assert "completed.json" not in h.saved


@pytest.mark.parametrize("encoding", ["raw", "unicode", "percent", "media"])
def test_credential_echo_refuses_before_body_hash_or_persistence(monkeypatch, encoding):
    h = Harness()
    raw, media = body(), "application/json"
    if encoding == "raw":
        raw = SECRET.encode()
    elif encoding == "unicode":
        raw = "".join("\\u%04x" % ord(c) for c in SECRET).encode()
    elif encoding == "percent":
        raw = "".join("%%%02x" % ord(c) for c in SECRET).encode()
    else:
        media += ";" + SECRET
    original = m.hash_bytes
    def observed(candidate):
        assert candidate != raw
        return original(candidate)
    monkeypatch.setattr(m, "hash_bytes", observed)
    h.reply = lambda *args: (raw, media, 200)
    with pytest.raises(m.ContinuationRefusal, match="credential_echo_refused"):
        h.run()
    assert len(h.calls) == 1 and not any(name.endswith(".raw") for name in h.saved)
    assert SECRET.encode() not in b"".join(h.saved.values())


def test_malformed_received_prefix_is_preserved_but_never_completed():
    h = Harness()
    h.reply = lambda *args: (b"{malformed JSON", "application/json", 200)
    with pytest.raises(identity.NativeDatedIdentityError):
        h.run()
    assert h.saved["date-002-active-page-02.raw"] == b"{malformed JSON"
    assert "date-002-active-page-02.received.json" in h.saved
    assert "date-002-active-page-02.refused.json" in h.saved
    assert len(h.calls) == 1 and "completed.json" not in h.saved


@pytest.mark.parametrize("url", ["https://evil.example/v3/reference/tickers?cursor=x", identity.ENDPOINT + "?cursor=x&apiKey=fake",
                                  identity.ENDPOINT + "?cursor=x&date=2024-01-01"])
def test_unsafe_following_cursor_is_retained_and_never_requested(url):
    h = Harness()
    h.reply = lambda *args: (body(url), "application/json", 200)
    with pytest.raises(identity.NativeDatedIdentityError):
        h.run()
    assert len(h.calls) == 1 and "date-002-active-page-02.raw" in h.saved
    assert "completed.json" not in h.saved


def test_valid_origin_cycle_stops_without_second_HTTP():
    h = Harness()
    h.reply = lambda *args: (body(h.source.payload()["failed_request"]["url"]), "application/json", 200)
    with pytest.raises(m.ContinuationRefusal, match="continuation_panel_cycle"):
        h.run()
    assert len(h.calls) == 1 and "completed.json" not in h.saved


@pytest.mark.parametrize("limit", ["MAXIMUM_TOTAL_BYTES", "MAXIMUM_ROWS"])
def test_full_page_reservation_retains_owned_refusal_before_HTTP(monkeypatch, limit):
    h = Harness()
    value = h.source.payload()
    maximum = value["source_raw_bytes"] + identity.MAXIMUM_RESPONSE_BYTES - 1 if limit == "MAXIMUM_TOTAL_BYTES" else 999
    monkeypatch.setattr(identity, limit, maximum)
    with pytest.raises(m.ContinuationRefusal, match="continuation_cumulative_storage_or_row_budget"):
        h.run()
    assert not h.calls and m.parsed(h.saved["refused.json"])["new_attempts_consumed"] == 0


def test_protocol_mutation_during_HTTP_refuses_before_raw_publication(monkeypatch):
    h = Harness()
    def reply(*args):
        monkeypatch.setattr(identity, "MAXIMUM_ROWS", identity.MAXIMUM_ROWS - 1)
        return body(), "application/json", 200
    h.reply = reply
    with pytest.raises(m.ContinuationRefusal, match="continuation_source_or_protocol_changed"):
        h.run()
    assert len(h.calls) == 1 and not any(name.endswith(".raw") for name in h.saved)


def test_final_receipt_uses_a_new_checked_clock_after_inventory_publication():
    h = Harness()
    inverted = False
    ordinary = h.clock
    def clock():
        return NOW if inverted else ordinary()
    def after_publish(name, raw):
        nonlocal inverted
        if name == "inventory.private.json":
            inverted = True
    h.on_publish = after_publish
    with pytest.raises(m.ContinuationRefusal, match="chronology"):
        h.run(now=clock)
    assert "inventory.private.json" in h.saved and "completed.json" not in h.saved


def test_exception_text_and_secret_are_never_receipt_diagnostics():
    h = Harness()
    h.reply = lambda *args: (_ for _ in ()).throw(OSError("external-URL " + SECRET))
    with pytest.raises(OSError):
        h.run()
    assert SECRET.encode() not in b"".join(h.saved.values())
    assert m.parsed(h.saved["date-002-active-page-02.refused.json"])["failure_category"] == "transport_or_storage_refused"


def test_new_claim_identity_is_clock_and_head_independent():
    first, second = Harness(), Harness()
    first.run()
    second.run(code_head="b" * 40)
    assert first.claims[0][0] == second.claims[0][0]
    assert first.claims[0][1]["maximum_new_attempts"] == 255
    assert first.claims[0][1]["parent_attempts_consumed"] == 4


def test_unsupported_host_or_lane_guard_is_first_before_claim_key_request():
    h = Harness()
    with pytest.raises(m.ContinuationRefusal, match="unsupported_host"):
        h.run(local_guard=lambda: (_ for _ in ()).throw(m.ContinuationRefusal("unsupported_host")))
    assert not h.saved and not h.keys and not h.claims and not h.calls
    assert "remote" not in h.events


def test_remote_failure_before_HTTP_consumes_started_attempt_without_request():
    h = Harness()
    checks = 0
    def remote():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise m.ContinuationRefusal("remote_advanced")
    with pytest.raises(m.ContinuationRefusal, match="remote_advanced"):
        h.run(remote_guard=remote)
    assert not h.calls and "date-002-active-page-02.started.json" in h.saved
    assert m.parsed(h.saved["refused.json"])["new_attempts_consumed"] == 1
    assert "completed.json" not in h.saved


def test_publication_guard_rechecked_after_HTTP_before_raw_save():
    h = Harness()
    permitted = True
    def local():
        h.local()
        if not permitted:
            raise m.ContinuationRefusal("local_lane_changed")
    def reply(*args):
        nonlocal permitted
        permitted = False
        return body(), "application/json", 200
    h.reply = reply
    with pytest.raises(m.ContinuationRefusal, match="local_lane_changed"):
        h.run(local_guard=local)
    assert len(h.calls) == 1 and "date-002-active-page-02.started.json" in h.saved
    assert not any(name.endswith(".raw") for name in h.saved)


def test_unregistered_protocol_refuses_before_claim_secret_or_request():
    h = Harness()
    with pytest.raises(m.ContinuationRefusal, match="unregistered"):
        h.run(expected_protocol_sha256="0" * 64)
    assert not h.claims and not h.keys and not h.calls and not h.saved


def test_new_attempt_budget_is_not_unused_parent_slot_reuse(monkeypatch):
    h = Harness()
    freeze = m.freeze_protocol
    def bounded(source_value):
        value = freeze(source_value)
        value["maximum_new_attempts"] = 1
        value["maximum_cumulative_attempts"] = value["source"]["source_attempts"] + 1
        return value
    monkeypatch.setattr(m, "freeze_protocol", bounded)
    with pytest.raises(m.ContinuationRefusal, match="new_attempt_budget"):
        h.run()
    assert len(h.calls) == 1
    assert m.parsed(h.saved["refused.json"])["cumulative_attempts_consumed"] == 5
    assert "date-002.qualified.private.json" not in h.saved and "completed.json" not in h.saved


@pytest.mark.parametrize("position", ["response", "report", "completion"])
def test_clock_inversions_cannot_publish_completion(position):
    h = Harness()
    ordinary = h.clock
    trigger = {"response": 3, "report": 6, "completion": 12}[position]
    count = 0
    def clock():
        nonlocal count
        count += 1
        return NOW if count == trigger else ordinary()
    with pytest.raises(m.ContinuationRefusal, match="chronology"):
        h.run(now=clock)
    assert "completed.json" not in h.saved


def test_response_media_size_types_refuse_without_unsafe_body_persistence():
    h = Harness()
    h.reply = lambda *args: (body(), "text/html", 200)
    with pytest.raises(m.ContinuationRefusal, match="HTTP_or_media"):
        h.run()
    assert len(h.calls) == 1 and not any(name.endswith(".raw") for name in h.saved)


def test_successful_new_date_report_retains_original_partial_origin_clocks():
    h = Harness()
    h.run()
    report = m.parsed(h.saved["date-002.qualified.private.json"])
    assert report["started_at"] == NOW
    assert report["page_origins"][0]["received_at"] == NOW
    assert report["page_origins"][0]["ordinal"] == 1
    assert report["page_origins"][1]["ordinal"] == 2
    assert report["page_origins"][1]["received_at"] > NOW
    assert report["authority"]["source_admitted"] is False


def test_malformed_error_code_keeps_fixed_refusal_instead_of_masking_failure():
    h = Harness()
    error = SharadarCaptureRefusal("network_failure", status=429)
    error.code = ["unhashable", SECRET]
    h.reply = lambda *args: (_ for _ in ()).throw(error)
    with pytest.raises(SharadarCaptureRefusal):
        h.run()
    refusal = m.parsed(h.saved["date-002-active-page-02.refused.json"])
    assert refusal["failure_category"] == "source_or_guard_refused" and refusal["http_status"] == 429
    assert len(h.calls) == 1 and SECRET.encode() not in b"".join(h.saved.values())


def test_current_named_key_cannot_be_echoed_by_retained_cursor_before_request_hash_or_publication(monkeypatch):
    h = Harness()
    key = "fabricated-exact-retained-cursor"
    h.key = lambda provider: KeychainSecret(key)
    real_hash = m.hash_payload
    def safe_hash(value):
        if type(value) is dict and set(value) == {"method", "url", "authentication"}:
            assert key not in value["url"], "current credential in new request digest"
        return real_hash(value)
    monkeypatch.setattr(m, "hash_payload", safe_hash)
    with pytest.raises(m.ContinuationRefusal, match="request_credential_echo"):
        h.run(get_secret=h.key)
    assert not h.calls
    assert not any(name.endswith(".started.json") for name in h.saved)
    assert m.parsed(h.saved["refused.json"])["new_attempts_consumed"] == 0


def lazy_files(files, reader=None):
    value = object.__new__(m._ParentFiles)
    entries = m.MappingProxyType({name: (hash_bytes(raw), len(raw)) for name, raw in files.items()})
    callback = reader or files.__getitem__
    anchor = (entries, callback)
    for name, item in (("_entries", entries), ("_reader", callback), ("_anchor", anchor), ("_anchor_identity", anchor)):
        object.__setattr__(value, name, item)
    return value


def test_streamed_parent_replay_matches_dict_without_retaining_all_raw_bodies():
    files, args = fixture()
    args = repin(files, args)
    reads = []
    source_files = lazy_files(files, lambda name: (reads.append(name), files[name])[1])
    actual = m.verify_parent(source_files, **args)
    expected = m.verify_parent(files, **args)
    assert actual.payload() == expected.payload()
    assert reads.count("date-001-active-page-01.raw") == 1
    assert all(type(value) is tuple for value in source_files._entries.values())
    assert len(actual._partial) == 1


def test_streamed_parent_rechecks_digest_on_each_source_read():
    files, args = fixture()
    args = repin(files, args)
    source_files = lazy_files(files)
    files["date-001-active-page-01.raw"] += b" "
    with pytest.raises(m.ContinuationRefusal, match="protected_parent_replay_bytes_changed"):
        m.verify_parent(source_files, **args)


@pytest.mark.parametrize("field", ["_entries", "_reader"])
def test_streamed_parent_reflection_mutation_refuses(field):
    files, args = fixture()
    source_files = lazy_files(files)
    object.__setattr__(source_files, field, {})
    with pytest.raises(m.ContinuationRefusal, match="protected_parent_files_changed"):
        m.verify_parent(source_files, **repin(files, args))


def test_operational_run_uses_owned_exclusive_output_named_key_fixed_headers_and_guard_schedule(monkeypatch):
    h = Harness()
    saved, requests, remote_calls, locals_seen = {}, [], [], []
    monkeypatch.setattr(m, "_require_capture_platform", lambda: None)
    monkeypatch.setattr(m, "_local", lambda *args: locals_seen.append("local"))
    monkeypatch.setattr(m, "_guard_remote", lambda *args: remote_calls.append("remote"))
    monkeypatch.setattr(m, "load_parent", lambda *args, **kwargs: h.source)
    monkeypatch.setattr(m, "EXPECTED_PROTOCOL_SHA256", hash_payload(m.freeze_protocol(h.source)))
    monkeypatch.setattr(m, "_code_identity", lambda *args: "c" * 64)
    monkeypatch.setattr(m, "_utc_now", h.clock)
    monkeypatch.setattr(m, "_git", lambda root, *args: args[1] if args[0] == "check-ignore" else "")
    monkeypatch.setattr(m, "_prepare_capture_directory", lambda target: Path("/fabricated/owned/run"))
    def publish(where, name, raw):
        pair = str(where), name
        assert pair not in saved
        saved[pair] = raw
        h.events.append("save:" + name)
    class FakeOwned:
        def __init__(self, directory, guard):
            self.directory, self.guard = directory, guard
        def check(self):
            self.guard()
        def publish(self, name, raw, *, parent=False):
            self.check()
            publish(self.directory.parent if parent else self.directory, name, raw)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(m, "_OwnedOutput", FakeOwned)
    def key(provider):
        assert provider == "massive"
        assert any(name.startswith("budget-") for _, name in saved)
        assert ("/fabricated/owned/run", "started.json") in saved
        return KeychainSecret(SECRET)
    monkeypatch.setattr(m, "read_named_keychain", key)
    def http(opener, request, maximum):
        requests.append(request)
        assert request.get_header("Authorization") == "Bearer " + SECRET
        assert request.get_header("Accept") == "application/json"
        assert SECRET not in request.full_url
        return body(), "application/json", 200
    monkeypatch.setattr(m, "_http", http)
    result = m.run(Path("/fabricated/root"), head=NEW_HEAD, remote="1" * 40)
    assert result["new_attempts_consumed"] == len(requests) == 4
    assert len(remote_calls) == len(requests) + 3
    assert len(locals_seen) > len(remote_calls)
    budgets = [m.parsed(raw) for (_, name), raw in saved.items() if name.startswith("budget-")]
    assert budgets[0]["schema"] == "si-native-identity-manual-continuation-budget-v1"
    assert budgets[0]["unused_parent_slots_repurposable"] is False
    assert budgets[0]["credential_item"]["service"] == "trading-agent-massive"


def test_pending_literal_protocol_refuses_before_any_private_source_or_key(monkeypatch):
    monkeypatch.setattr(m, "_require_capture_platform", lambda: None)
    monkeypatch.setattr(m, "_local", lambda *args: None)
    monkeypatch.setattr(m, "_guard_remote", lambda *args: None)
    monkeypatch.setattr(m, "EXPECTED_PROTOCOL_SHA256", "PENDING")
    monkeypatch.setattr(m, "load_parent", lambda *args, **kwargs: pytest.fail("unregistered private read"))
    monkeypatch.setattr(m, "read_named_keychain", lambda *args: pytest.fail("unregistered secret read"))
    with pytest.raises(m.ContinuationRefusal, match="protocol_pending"):
        m.run(Path("/fabricated"), head=NEW_HEAD, remote="1" * 40)


def test_fixed_historical_blob_reader_guards_binary_Git_without_other_refs(monkeypatch):
    seen, commands = [], []
    monkeypatch.setattr(m, "_local", lambda *args: seen.append("guard"))
    class Result:
        returncode, stdout = 0, b"fabricated frozen original code\r\n"
    def run(command, **kwargs):
        commands.append(command)
        return Result()
    monkeypatch.setattr(m.subprocess, "run", run)
    raw = m._historical_code(Path("/fabricated"), m.SOURCE_HEAD, m.SOURCE_CODE_FILES[0], head=NEW_HEAD)
    assert raw == Result.stdout and commands == [["git", "show", m.SOURCE_HEAD + ":" + m.SOURCE_CODE_FILES[0]]]
    assert seen == ["guard", "guard"]
    with pytest.raises(m.ContinuationRefusal, match="fixed_original_commit"):
        m._historical_code(Path("/fabricated"), "b" * 40, "../unknown", head=NEW_HEAD)
    assert len(commands) == 1


def test_guarded_existing_master_PathLike_blocks_read_if_lane_changes(tmp_path):
    calls = []
    permitted = True
    def local():
        calls.append("guard")
        if not permitted:
            raise m.ContinuationRefusal("lane_changed")
    path = m._GuardedSourcePath(tmp_path, local) / "original.private"
    assert Path(path) == tmp_path / "original.private"
    permitted = False
    with pytest.raises(m.ContinuationRefusal, match="lane_changed"):
        m.os.fspath(path)
    assert len(calls) >= 3


def test_protected_read_has_only_local_checks_before_and_after(monkeypatch):
    seen = []
    monkeypatch.setattr(m, "_local", lambda *args: seen.append("local"))
    monkeypatch.setattr(m, "_protected_bytes", lambda *args: (seen.append("read"), b"fabricated")[1])
    monkeypatch.setattr(m, "_guard_remote", lambda *args: pytest.fail("remote per private file"))
    assert m._read(Path("/fabricated"), Path("/fabricated/source"), 64, head=NEW_HEAD) == b"fabricated"
    assert seen == ["local", "read", "local"]


def test_guarded_original_source_path_reflection_cannot_disable_local_guard(tmp_path):
    seen = []
    value = m._GuardedSourcePath(tmp_path, lambda: seen.append("guard"))
    object.__setattr__(value, "guard", lambda: None)
    with pytest.raises(m.ContinuationRefusal, match="guarded_source_path_changed"):
        m.os.fspath(value)
    assert not seen


def test_pending_preflight_emits_only_digests_zero_access_and_no_private_cursor(monkeypatch):
    h = Harness()
    remote = []
    monkeypatch.setattr(m, "_require_capture_platform", lambda: None)
    monkeypatch.setattr(m, "_local", lambda *args: None)
    monkeypatch.setattr(m, "_guard_remote", lambda *args: remote.append("remote"))
    monkeypatch.setattr(m, "load_parent", lambda *args, **kwargs: h.source)
    monkeypatch.setattr(m, "_code_identity", lambda *args: "c" * 64)
    monkeypatch.setattr(m, "EXPECTED_PROTOCOL_SHA256", "PENDING")
    monkeypatch.setattr(m, "read_named_keychain", lambda *args: pytest.fail("preflight key read"))
    monkeypatch.setattr(m, "_http", lambda *args: pytest.fail("preflight HTTP"))
    monkeypatch.setattr(m, "_prepare_capture_directory", lambda *args: pytest.fail("preflight output mutation"))
    result = m.preflight(Path("/fabricated"), head=NEW_HEAD, remote="1" * 40)
    assert result["prospective_protocol_sha256"] == hash_payload(m.freeze_protocol(h.source))
    assert all(result[key] == 0 for key in ("provider_requests", "credential_reads", "outcome_looks", "qc_attempts"))
    assert b"cursor" not in encoded(result) and len(remote) == 2


@pytest.mark.skipif(m.os.name != "posix" or not hasattr(m.os, "O_NOFOLLOW") or not callable(getattr(m.os, "getuid", None)),
                    reason="real protected-directory POSIX ownership required")
@pytest.mark.parametrize("replacement", ["symlink", "mode"])
def test_owned_run_directory_drift_refuses_before_key_or_external_publication(tmp_path, monkeypatch, replacement):
    h = Harness()
    tmp_path = tmp_path.resolve()
    tmp_path.chmod(0o700)
    owner, outside = tmp_path / "run", tmp_path / "outside"
    outside.mkdir(mode=0o700)
    monkeypatch.setattr(m, "_local", lambda *args: None)
    monkeypatch.setattr(m, "_guard_remote", lambda *args: None)
    monkeypatch.setattr(m, "load_parent", lambda *args, **kwargs: h.source)
    monkeypatch.setattr(m, "EXPECTED_PROTOCOL_SHA256", hash_payload(m.freeze_protocol(h.source)))
    monkeypatch.setattr(m, "_code_identity", lambda *args: "c" * 64)
    monkeypatch.setattr(m, "_utc_now", h.clock)
    monkeypatch.setattr(m, "_git", lambda root, *args: args[1] if args[0] == "check-ignore" else "")
    prepare = m._prepare_capture_directory
    def substituted(target):
        directory = prepare(owner)
        if replacement == "symlink":
            directory.rename(tmp_path / "original")
            directory.symlink_to(outside, target_is_directory=True)
        else:
            directory.chmod(0o755)
        return directory
    monkeypatch.setattr(m, "_prepare_capture_directory", substituted)
    monkeypatch.setattr(m, "read_named_keychain", h.key)
    monkeypatch.setattr(m, "_http", lambda *args: (body(), "application/json", 200))
    with pytest.raises((m.ContinuationRefusal, m.CaptureRefusal, OSError)):
        m.run(tmp_path, head=NEW_HEAD, remote="1" * 40)
    assert not h.keys
    assert not list(outside.iterdir())


@pytest.mark.skipif(m.os.name != "posix" or not hasattr(m.os, "O_NOFOLLOW") or not callable(getattr(m.os, "getuid", None)),
                    reason="real protected-directory POSIX ownership required")
def test_owned_FD_publication_is_exclusive0600_and_anchors_parent_budget(tmp_path):
    tmp_path = tmp_path.resolve()
    tmp_path.chmod(0o700)
    directory = m._prepare_capture_directory(tmp_path / "run")
    with m._OwnedOutput(directory, lambda: None) as owned:
        owned.publish("fabricated.raw", b"fabricated source only")
        owned.publish("budget-fabricated.json", b"{}", parent=True)
        assert m.stat.S_IMODE((directory / "fabricated.raw").stat().st_mode) == 0o600
        assert m.stat.S_IMODE((directory.parent / "budget-fabricated.json").stat().st_mode) == 0o600
        with pytest.raises(FileExistsError):
            owned.publish("fabricated.raw", b"different")
    assert (directory / "fabricated.raw").read_bytes() == b"fabricated source only"


@pytest.mark.skipif(m.os.name != "posix" or not hasattr(m.os, "O_NOFOLLOW") or not callable(getattr(m.os, "getuid", None)),
                    reason="real protected-directory POSIX ownership required")
def test_output_swap_between_validation_and_open_cannot_redirect_a_payload(tmp_path, monkeypatch):
    tmp_path = tmp_path.resolve()
    tmp_path.chmod(0o700)
    directory = m._prepare_capture_directory(tmp_path / "run")
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    with m._OwnedOutput(directory, lambda: None) as owned:
        original = m.os.open
        def raced(name, flags, *args, **kwargs):
            if name == "fabricated.raw":
                directory.rename(tmp_path / "original")
                directory.symlink_to(outside, target_is_directory=True)
            return original(name, flags, *args, **kwargs)
        monkeypatch.setattr(m.os, "open", raced)
        with pytest.raises(m.ContinuationRefusal, match="owned_output"):
            owned.publish("fabricated.raw", b"must not escape the original protected inode")
    assert not list(outside.iterdir())
    assert (tmp_path / "original" / "fabricated.raw").read_bytes() == b""


@pytest.mark.skipif(m.os.name != "posix" or not hasattr(m.os, "O_NOFOLLOW") or not callable(getattr(m.os, "getuid", None)),
                    reason="real protected-directory POSIX ownership required")
@pytest.mark.parametrize("replacement", ["new_directory", "mode"])
def test_retained_outputFD_detects_inode_or_permission_change_before_any_write(tmp_path, replacement):
    tmp_path = tmp_path.resolve()
    tmp_path.chmod(0o700)
    directory = m._prepare_capture_directory(tmp_path / "run")
    with m._OwnedOutput(directory, lambda: None) as owned:
        if replacement == "new_directory":
            directory.rename(tmp_path / "original")
            directory.mkdir(mode=0o700)
        else:
            directory.chmod(0o755)
        with pytest.raises(m.ContinuationRefusal, match="owned_output"):
            owned.publish("fabricated.raw", b"must not publish")
    assert not list(directory.iterdir())
