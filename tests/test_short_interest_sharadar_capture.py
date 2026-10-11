"""Offline fabricated-only checks of the protected direct-Sharadar transport."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import stat
import urllib.error
import urllib.parse
import urllib.request

import pytest

from data.hashing import hash_bytes
from research.short_interest_etf import sharadar_companion_qualification as contract
from scripts import qualify_finra_short_interest as base_capture
from scripts import qualify_sharadar_companion as capture


KEY = "fabricated-only-key-not-a-real-secret"
HEAD = "a" * 40
REMOTE = "b" * 40
NOW = "2026-10-11T12:00:00Z"


class Response:
    def __init__(self, raw, *, status=200, content_type="application/json", extra=None):
        self.raw = raw if type(raw) is bytes else json.dumps(raw).encode()
        self.status = status
        self.headers = {"Content-Type": content_type, **(extra or {})}
        self.reads = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, maximum):
        self.reads.append(maximum)
        return self.raw[:maximum]


class Opener:
    def __init__(self, responses, before_open=None):
        self.responses = iter(responses)
        self.before_open = before_open
        self.requests = []

    def open(self, request, timeout):
        assert timeout == 30
        if self.before_open is not None:
            self.before_open(request)
        self.requests.append(request)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class UnreadableBody(io.BytesIO):
    def read(self, *args):
        raise AssertionError("HTTP error body must not be read")


def documents():
    result = {}
    for table in contract.TABLES:
        result["metadata-" + table] = {
            "table": table, "name": table + ".csv.zip", "size": 1234,
            "sizeLabel": "1.2 KB", "modified": "2026-10-10T01:00:00+00:00",
        }
        result["schema-" + table] = (
            "CREATE TABLE " + table + " (" + ", ".join(
                field + " TEXT" for field in contract.FIELDS[table]) + ");\n"
        ).encode()
    for table in contract.ROW_TABLES:
        result["rows-" + table] = {"count": 0, "data": []}
    return result


def responses(docs=None):
    docs = documents() if docs is None else docs
    return [Response(docs[request_id], content_type=(
        "text/plain; charset=utf-8" if request_id.startswith("schema-")
        else "application/json; charset=utf-8")) for request_id in contract.REQUEST_IDS]


@pytest.fixture
def local_guard(monkeypatch):
    calls = []
    monkeypatch.setattr(capture, "_guard", lambda *args: calls.append(args))
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    return calls


def run_capture(tmp_path, opener):
    return capture._capture(tmp_path, tmp_path, KEY, opener,
                            expected_head=HEAD, expected_remote=REMOTE)


def assert_no_secret(directory):
    assert not any(KEY.encode() in path.read_bytes() for path in directory.rglob("*") if path.is_file())


def test_complete_frozen_order_receipts_precede_http_and_public_output_is_not_fitness(
    tmp_path, local_guard,
):
    checked = []
    def before_open(request):
        attempt = len(checked) + 1
        started = json.loads((tmp_path / f"attempt-{attempt:02d}.started.json").read_text())
        expected_id = contract.REQUEST_IDS[attempt - 1]
        assert started["request_id"] == expected_id
        assert started["request"] == contract.sharadar_request(expected_id)
        assert started["request_sha256"] == contract.request_sha256(expected_id)
        assert started["protocol_sha256"] == capture.PROTOCOL_SHA256
        assert started["code_head"] == HEAD
        assert started["attempt"] == attempt
        assert local_guard[-1] == (tmp_path, HEAD, REMOTE)
        checked.append(expected_id)
    opener = Opener(responses(), before_open)
    result = run_capture(tmp_path, opener)
    assert checked == list(contract.REQUEST_IDS)
    assert len(opener.requests) == result["http_attempts"] == 16
    for request_id, request in zip(contract.REQUEST_IDS, opener.requests):
        spec = contract.sharadar_request(request_id)
        parsed = urllib.parse.urlsplit(request.full_url)
        assert parsed.scheme == "https" and parsed.netloc == "api.sharadar.com"
        assert parsed.path == urllib.parse.urlsplit(spec["url"]).path
        assert urllib.parse.parse_qs(parsed.query) == {k: [v] for k, v in spec["params"].items()}
        assert request.get_method() == "GET" and request.data is None
        assert KEY not in request.full_url
        if request_id.startswith("schema-"):
            assert request.get_header("X-api-key") is None
            assert set(request.headers) == {"Accept"}
        else:
            assert request.get_header("X-api-key") == KEY
            assert set(request.headers) == {"Accept", "X-api-key"}
    for attempt, request_id in enumerate(contract.REQUEST_IDS, 1):
        receipt = json.loads((tmp_path / f"attempt-{attempt:02d}.received.json").read_text())
        raw_path = tmp_path / receipt["raw_path"]
        assert receipt["request_id"] == request_id
        assert receipt["request_sha256"] == contract.request_sha256(request_id)
        assert receipt["raw_sha256"] == hash_bytes(raw_path.read_bytes())
        assert receipt["raw_bytes"] == raw_path.stat().st_size
        assert receipt["http_status"] == 200
    private = json.loads((tmp_path / "qualification.private.json").read_text())
    assert private["authority"]["ready_for_empirical_backtest"] is False
    assert private["authority"]["actual_outcome_looks"] == 0
    assert result["private_report_sha256"] == private["report_sha256"]
    assert result["outcome_looks_consumed"] == result["qc_launch_attempts"] == 0
    assert result["backtest_result_exists"] is False
    assert not set(result) & {"tables", "metadata", "authority", "coverage", "source_admitted", "ready_for_empirical_backtest"}
    assert json.loads((tmp_path / "completed.json").read_text()) == result
    for path in tmp_path.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert_no_secret(tmp_path)


@pytest.mark.parametrize("position", range(10))
def test_metadata_or_schema_refusal_stops_before_every_later_request(tmp_path, local_guard, position):
    pages = responses()
    pages[position] = Response(b"{}" if position < 5 else b"CREATE TABLE wrong (ticker TEXT);",
                               content_type="application/json" if position < 5 else "text/plain")
    opener = Opener(pages)
    with pytest.raises(capture.SharadarCaptureRefusal, match="response_contract_refused"):
        run_capture(tmp_path, opener)
    assert len(opener.requests) == position + 1
    assert (tmp_path / f"attempt-{position + 1:02d}.raw").exists()
    assert (tmp_path / f"attempt-{position + 1:02d}.received.json").exists()
    assert (tmp_path / f"attempt-{position + 1:02d}.refused.json").exists()
    assert not (tmp_path / f"attempt-{position + 2:02d}.started.json").exists()
    assert not (tmp_path / "qualification.private.json").exists()
    assert not any("/data/descriptions?" in req.full_url for req in opener.requests)


@pytest.mark.parametrize("status", [True, "200", 201, 204, 301, 302, 401, 403, 500])
def test_non_200_never_reads_body_or_retries(tmp_path, local_guard, status):
    response = Response(KEY.encode(), status=status)
    opener = Opener([response])
    with pytest.raises(capture.SharadarCaptureRefusal, match="http_not_200") as error:
        run_capture(tmp_path, opener)
    assert response.reads == [] and len(opener.requests) == 1
    assert error.value.http_status == (status if type(status) is int else None)
    refusal = json.loads((tmp_path / "attempt-01.refused.json").read_text())
    assert refusal["http_status"] == error.value.http_status
    assert not (tmp_path / "attempt-01.raw").exists()
    assert_no_secret(tmp_path)


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 429, 503])
def test_http_error_never_follows_location_reads_error_or_echoes_credential(tmp_path, local_guard, status):
    error = urllib.error.HTTPError("https://example.invalid/?api_key=" + KEY, status, KEY,
                                  {"Location": "https://example.invalid/" + KEY}, UnreadableBody(KEY.encode()))
    opener = Opener([error])
    with pytest.raises(capture.SharadarCaptureRefusal, match="http_not_200") as failure:
        run_capture(tmp_path, opener)
    assert str(failure.value) == "http_not_200"
    assert failure.value.http_status == status
    assert len(opener.requests) == 1
    assert_no_secret(tmp_path)


@pytest.mark.parametrize("status", [True, None, KEY])
def test_invalid_http_error_status_cannot_be_published_as_secret(tmp_path, local_guard, status):
    error = urllib.error.HTTPError("https://example.invalid/", status, KEY, {}, UnreadableBody())
    with pytest.raises(capture.SharadarCaptureRefusal, match="http_not_200") as failure:
        run_capture(tmp_path, Opener([error]))
    assert failure.value.http_status is None
    assert_no_secret(tmp_path)


@pytest.mark.parametrize("error", [urllib.error.URLError(KEY), TimeoutError(KEY), ConnectionError(KEY), OSError(KEY)])
def test_network_failures_are_fixed_safe_code(tmp_path, local_guard, error):
    opener = Opener([error])
    with pytest.raises(capture.SharadarCaptureRefusal, match="network_failure"):
        run_capture(tmp_path, opener)
    assert len(opener.requests) == 1
    assert_no_secret(tmp_path)


@pytest.mark.parametrize("kind", ["metadata", "schema", "rows"])
def test_each_response_kind_has_bounded_read(kind):
    maximum = capture.MAXIMUM_BYTES[kind]
    response = Response(b"x" * (maximum + 1))
    with pytest.raises(capture.SharadarCaptureRefusal, match="response_size_limit"):
        capture._http(Opener([response]), urllib.request.Request("https://example.invalid"), maximum)
    assert response.reads == [maximum + 1]


@pytest.mark.parametrize("content_type", [None, 9, "x" * 257])
def test_invalid_content_type_shape_refused_before_artifact(tmp_path, local_guard, content_type):
    opener = Opener([Response(documents()["metadata-stocks"], content_type=content_type)])
    with pytest.raises(capture.SharadarCaptureRefusal, match="content_type"):
        run_capture(tmp_path, opener)
    assert not (tmp_path / "attempt-01.raw").exists()


@pytest.mark.parametrize("content_type", ["text/html", "text/plain", "application/octet-stream", ""])
def test_unexpected_metadata_media_type_stops_before_later_http(tmp_path, local_guard, content_type):
    opener = Opener([Response(documents()["metadata-stocks"], content_type=content_type)])
    with pytest.raises(capture.SharadarCaptureRefusal, match="response_contract_refused"):
        run_capture(tmp_path, opener)
    assert len(opener.requests) == 1
    assert not (tmp_path / "completed.json").exists()


def test_body_secret_echo_refused_without_saving_body(tmp_path, local_guard):
    opener = Opener([Response({"echo": KEY})])
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_echo"):
        run_capture(tmp_path, opener)
    assert not (tmp_path / "attempt-01.raw").exists()
    assert_no_secret(tmp_path)


@pytest.mark.parametrize("escaping", ["first_unicode", "all_unicode", "nested", "fieldname", "slash"])
def test_reconstructible_json_secret_echo_is_refused_before_raw_persistence(tmp_path, local_guard, escaping):
    key = "fabricated/only\\key" if escaping == "slash" else KEY
    metadata = documents()["metadata-stocks"]
    if escaping == "nested":
        metadata["echo"] = {"nested": [{"other": [key]}]}
    elif escaping == "fieldname":
        metadata[key] = "fabricated"
    else:
        metadata["echo"] = key
    raw = json.dumps(metadata).encode()
    if escaping in {"first_unicode", "nested", "fieldname"}:
        raw = raw.replace(KEY.encode(), b"\\u0066" + KEY[1:].encode())
    elif escaping == "all_unicode":
        raw = raw.replace(KEY.encode(), "".join(f"\\u{ord(char):04x}" for char in KEY).encode())
    elif escaping == "slash":
        raw = raw.replace(b"/", b"\\/")
    assert key.encode() not in raw
    opener = Opener([Response(raw)])
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_echo"):
        capture._capture(tmp_path, tmp_path, key, opener, expected_head=HEAD, expected_remote=REMOTE)
    assert len(opener.requests) == 1
    assert not (tmp_path / "attempt-01.raw").exists()
    assert not (tmp_path / "attempt-01.received.json").exists()


def test_allowed_content_type_secret_echo_must_not_enter_receipt(tmp_path, local_guard):
    opener = Opener([Response(documents()["metadata-stocks"],
                              content_type="application/json; charset=" + KEY),
                     Response(b"{}", status=403)])
    with pytest.raises(capture.SharadarCaptureRefusal):
        run_capture(tmp_path, opener)
    assert_no_secret(tmp_path)
    assert len(opener.requests) == 1


def test_real_capture_clock_satisfies_canonical_utc_validator():
    metadata = documents()["metadata-stocks"]
    metadata["modified"] = "1970-01-01T00:00:00+00:00"
    sample = contract.CapturedSharadarResponse(
        "metadata-stocks", contract.request_sha256("metadata-stocks"),
        json.dumps(metadata).encode(), "application/json",
    )
    assert contract.validate_sharadar_metadata(sample, retrieved_at=capture._utc_now())["table"] == "stocks"


def test_unlisted_response_headers_never_enter_receipts(tmp_path, local_guard):
    pages = responses()
    for page in pages:
        page.headers.update({"Authorization": KEY, "Location": KEY, "X-API-Key": KEY,
                             "Set-Cookie": KEY, "Account-ID": "private-fixture-account"})
    run_capture(tmp_path, Opener(pages))
    assert_no_secret(tmp_path)
    assert not any(b"private-fixture-account" in p.read_bytes() for p in tmp_path.iterdir())
    for path in tmp_path.glob("*.received.json"):
        receipt = json.loads(path.read_text())
        assert not set(receipt) & {"headers", "Authorization", "Location", "Set-Cookie", "Account-ID"}


@pytest.mark.parametrize("change", ["short", "duplicate", "reordered", "tuple", "extra", "hash"])
def test_inventory_or_protocol_drift_refuses_before_any_http(tmp_path, local_guard, monkeypatch, change):
    protocol = copy.deepcopy(contract.qualification_protocol())
    if change == "short":
        protocol["request_ids"].pop()
    elif change == "duplicate":
        protocol["request_ids"][1] = protocol["request_ids"][0]
    elif change == "reordered":
        protocol["request_ids"][0], protocol["request_ids"][1] = protocol["request_ids"][1], protocol["request_ids"][0]
    elif change == "tuple":
        protocol["request_ids"] = tuple(protocol["request_ids"])
    elif change == "extra":
        protocol["request_ids"].append("metadata-stocks")
    else:
        protocol["purpose"] = "unfrozen purpose"
    monkeypatch.setattr(capture, "qualification_protocol", lambda: protocol)
    opener = Opener(responses())
    with pytest.raises(capture.CaptureRefusal):
        run_capture(tmp_path, opener)
    assert opener.requests == []
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("change", ["other_origin", "http", "method", "query_secret", "extra_param", "offset", "digest"])
def test_descriptor_drift_refuses_before_start_receipt_or_http(tmp_path, local_guard, monkeypatch, change):
    original = capture.sharadar_request
    def changed(request_id):
        spec = copy.deepcopy(original(request_id))
        if change == "other_origin":
            spec["url"] = "https://example.invalid/v1.0/data/stocks"
        elif change == "http":
            spec["url"] = spec["url"].replace("https:", "http:")
        elif change == "method":
            spec["method"] = "POST"
        elif change == "query_secret":
            spec["params"]["api_key"] = KEY
        elif change == "extra_param":
            spec["params"]["unfrozen"] = "1"
        elif change == "offset":
            spec["params"]["offset"] = "1"
        return spec
    monkeypatch.setattr(capture, "sharadar_request", changed)
    if change == "digest":
        monkeypatch.setattr(capture, "request_sha256", lambda request_id: "0" * 64)
    opener = Opener(responses())
    with pytest.raises(capture.CaptureRefusal):
        run_capture(tmp_path, opener)
    assert opener.requests == []
    assert not tuple(tmp_path.iterdir())


def test_guard_rechecked_after_started_receipt_immediately_before_http(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    def guard(*args):
        if (tmp_path / "attempt-01.started.json").exists():
            raise capture.CaptureRefusal("head_changed")
    monkeypatch.setattr(capture, "_guard", guard)
    opener = Opener(responses())
    with pytest.raises(capture.CaptureRefusal, match="head_changed"):
        run_capture(tmp_path, opener)
    assert opener.requests == []
    assert (tmp_path / "attempt-01.started.json").exists()


def test_existing_started_receipt_prevents_an_attempt_counter_restart(tmp_path, local_guard):
    capture._publish_json(tmp_path, "attempt-01.started.json", {"attempt": 1})
    opener = Opener(responses())
    with pytest.raises(capture.CaptureRefusal, match="artifact_already_exists"):
        run_capture(tmp_path, opener)
    assert opener.requests == []
    assert json.loads((tmp_path / "attempt-01.started.json").read_text()) == {"attempt": 1}


@pytest.mark.parametrize("observed", ["", REMOTE + " refs/heads/main", HEAD + " " + capture.REMOTE_REF,
                                      REMOTE + " " + capture.REMOTE_REF + "\n" + HEAD + " " + capture.REMOTE_REF])
def test_matching_remote_guard_refuses_missing_advanced_or_ambiguous_refs(monkeypatch, observed):
    calls = []
    def git(root, *args):
        calls.append(args)
        return observed
    monkeypatch.setattr(capture, "_git", git)
    with pytest.raises(capture.SharadarCaptureRefusal, match="remote_advanced_or_ambiguous"):
        capture._guard_remote(Path("/fabricated"), REMOTE)
    assert calls == [("ls-remote", "origin", capture.REMOTE_REF)]


def test_matching_remote_guard_uses_only_exact_lane_ref(monkeypatch):
    monkeypatch.setattr(capture, "_git", lambda root, *args: REMOTE + "\t" + capture.REMOTE_REF)
    capture._guard_remote(Path("/fabricated"), REMOTE)


def test_combined_guard_checks_lane_then_remote_with_exact_expected_heads(monkeypatch):
    checked = []
    monkeypatch.setattr(capture, "_guard_lane", lambda *args: checked.append(("lane", args)))
    monkeypatch.setattr(capture, "_guard_remote", lambda *args: checked.append(("remote", args)))
    root = Path("/fabricated")
    capture._guard(root, HEAD, REMOTE)
    assert checked == [("lane", (root, HEAD)), ("remote", (root, REMOTE))]


@pytest.mark.parametrize("reason", ["wrong_physical_root", "wrong_git_root", "wrong_branch", "head_changed", "dirty_worktree"])
def test_lane_guard_failure_does_not_inspect_remote(monkeypatch, reason):
    def guard(*args):
        raise capture.CaptureRefusal(reason)
    monkeypatch.setattr(capture, "_guard_lane", guard)
    monkeypatch.setattr(capture, "_guard_remote", lambda *args: pytest.fail("no remote after lane mismatch"))
    with pytest.raises(capture.CaptureRefusal, match=reason):
        capture._guard(Path("/fabricated"), HEAD, REMOTE)


@pytest.mark.parametrize("expected", ["", "A" * 40, "a" * 39, "a" * 41, "not-a-hash"])
def test_invalid_expected_remote_refuses_without_git(monkeypatch, expected):
    monkeypatch.setattr(capture, "_git", lambda *args: pytest.fail("git must not run"))
    with pytest.raises(capture.SharadarCaptureRefusal, match="invalid_expected_remote"):
        capture._guard_remote(Path("/fabricated"), expected)


@pytest.fixture
def credential(tmp_path, monkeypatch):
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    path = parent / "sharadar.env"
    path.write_text("SHARADAR_API_KEY=" + KEY + "\n")
    path.chmod(0o600)
    monkeypatch.setattr(capture, "CREDENTIAL_PATH", path)
    return path


@pytest.mark.parametrize("wrapper", ["", '"', "'"])
def test_reader_only_known_protected_file_and_key_field(credential, wrapper):
    credential.write_text("# Synthetic fixture\n\n SHARADAR_API_KEY = " + wrapper + KEY + wrapper + "\n")
    assert capture._read_key(credential) == KEY


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o400, 0o700])
def test_credential_file_requires_exact_600(credential, mode):
    credential.chmod(mode)
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_file_protection"):
        capture._read_key(credential)


@pytest.mark.parametrize("mode", [0o755, 0o750, 0o600])
def test_credential_parent_requires_exact_700(credential, mode):
    credential.parent.chmod(mode)
    try:
        with pytest.raises(capture.SharadarCaptureRefusal, match="credential_directory_protection"):
            capture._read_key(credential)
    finally:
        credential.parent.chmod(0o700)


def test_credential_parent_wrong_owner_refuses(credential, monkeypatch):
    monkeypatch.setattr(capture.os, "getuid", lambda: credential.parent.stat().st_uid + 1)
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_directory_protection"):
        capture._read_key(credential)


@pytest.mark.parametrize("change", ["owner", "kind"])
def test_credential_file_wrong_owner_or_nonregular_refuses(credential, monkeypatch, change):
    original = capture.os.fstat
    def changed(fd):
        info = original(fd)
        values = list(info)
        if change == "owner":
            values[4] = info.st_uid + 1
        else:
            values[0] = stat.S_IFIFO | 0o600
        return type(info)(values)
    monkeypatch.setattr(capture.os, "fstat", changed)
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_file_protection"):
        capture._read_key(credential)


def test_unknown_credential_location_refuses_before_open(credential, monkeypatch):
    other = credential.with_name("other.env")
    monkeypatch.setattr(capture.os, "open", lambda *args: pytest.fail("unknown file must not be opened"))
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_location_or_symlink"):
        capture._read_key(other)


def test_credential_symlink_and_symlink_parent_refuse(credential, monkeypatch):
    link = credential.with_name("link.env")
    link.symlink_to(credential)
    monkeypatch.setattr(capture, "CREDENTIAL_PATH", link)
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_location_or_symlink"):
        capture._read_key(link)
    directory_link = credential.parent.with_name("linked-private")
    directory_link.symlink_to(credential.parent, target_is_directory=True)
    path = directory_link / credential.name
    monkeypatch.setattr(capture, "CREDENTIAL_PATH", path)
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_location_or_symlink"):
        capture._read_key(path)


@pytest.mark.parametrize("text", ["", "# empty", "SHARADAR_API_KEY", "OTHER=fixture", "SHARADAR_API_KEY=x\nOTHER=y",
                                "SHARADAR_API_KEY=x\nSHARADAR_API_KEY=y", "export SHARADAR_API_KEY=x"])
def test_missing_extra_or_duplicate_credential_fields_refuse(credential, text):
    credential.write_text(text)
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_fields"):
        capture._read_key(credential)


@pytest.mark.parametrize("value", ["", "test-api-key", "x" * 513, "bad key", "nonascii-ä", "bad\x00key", '"bad key"'])
def test_invalid_or_sample_key_refuses(credential, value):
    credential.write_text("SHARADAR_API_KEY=" + value)
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_value"):
        capture._read_key(credential)


def test_oversized_credential_file_refuses(credential):
    credential.write_text("#" + "x" * 4096)
    with pytest.raises(capture.SharadarCaptureRefusal, match="credential_file_protection"):
        capture._read_key(credential)


def args():
    return ["--credential-file", "/not-read-fixture.env", "--expected-head", HEAD,
            "--expected-remote", REMOTE, "--run-id", "sharadar-companion-20261011T120000Z"]


@pytest.fixture
def cli(tmp_path, local_guard, monkeypatch):
    monkeypatch.setattr(capture.Path, "cwd", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(capture, "_git", lambda root, *parts: parts[-1] if parts[0] == "check-ignore" else "")
    monkeypatch.setattr(capture, "_read_key", lambda path: KEY)
    return tmp_path / capture.CAPTURE_PARENT / "sharadar-companion-20261011T120000Z"


def test_cli_disables_proxies_redirects_and_only_emits_safe_completion(cli, monkeypatch, capsys):
    built = []
    opener = Opener(responses())
    def build(*handlers):
        built.extend(handlers)
        return opener
    monkeypatch.setattr(capture.urllib.request, "build_opener", build)
    assert capture.main(args()) == 0
    public = json.loads(capsys.readouterr().out)
    assert public["status"] == "capture_complete" and public["http_attempts"] == 16
    assert not set(public) & {"tables", "coverage", "metadata", "authority"}
    assert isinstance(built[0], urllib.request.ProxyHandler) and built[0].proxies == {}
    assert isinstance(built[1], base_capture._NoRedirect)
    assert built[1].redirect_request(None, None, None, None, None, None) is None
    assert stat.S_IMODE(cli.stat().st_mode) == stat.S_IMODE(cli.parent.stat().st_mode) == 0o700
    assert (cli / "protocol.json").exists() and (cli / "started.json").exists()
    assert_no_secret(cli)


@pytest.mark.parametrize("failure", ["not_ignored", "guard", "run_id"])
def test_cli_preflight_refuses_before_credentials_or_opener(cli, monkeypatch, capsys, failure):
    monkeypatch.setattr(capture, "_read_key", lambda *args: pytest.fail("credential must not be read"))
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: pytest.fail("opener must not be made"))
    argv = args()
    if failure == "not_ignored":
        monkeypatch.setattr(capture, "_git", lambda *args: "")
    elif failure == "guard":
        def guard(*args):
            raise capture.CaptureRefusal(KEY)
        monkeypatch.setattr(capture, "_guard", guard)
    else:
        argv[-1] = "../unsafe"
    assert capture.main(argv) == 2
    assert KEY not in capsys.readouterr().out
    assert not cli.exists()


def test_cli_http_failure_safe_refusal_records_status_without_body(cli, monkeypatch, capsys):
    error = urllib.error.HTTPError("https://example.invalid/" + KEY, 403, KEY, {"Authorization": KEY}, UnreadableBody())
    opener = Opener([error])
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: opener)
    assert capture.main(args()) == 2
    public = json.loads(capsys.readouterr().out)
    assert public == {"status": "capture_refused", "code": "http_not_200", "http_status": 403,
                      "backtest_result_exists": False}
    assert json.loads((cli / "refused.json").read_text())["http_status"] == 403
    assert len(opener.requests) == 1
    assert_no_secret(cli)


def test_existing_capture_is_not_overwritten_or_restarted(cli, monkeypatch, capsys):
    cli.parent.mkdir(mode=0o700, parents=True)
    cli.mkdir(mode=0o700)
    marker = cli / "owner-marker"
    marker.write_text("owner-owned")
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: pytest.fail("no restart"))
    assert capture.main(args()) == 2
    assert marker.read_text() == "owner-owned"
    assert json.loads(capsys.readouterr().out)["code"] == "local_preflight_refused"


def test_nonignored_destination_does_not_create_private_market_directory(cli, monkeypatch, capsys):
    monkeypatch.setattr(capture, "_git", lambda *args: "")
    assert capture.main(args()) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "capture_not_ignored"
    assert not cli.exists()
