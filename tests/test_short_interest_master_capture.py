"""Fake source-only transports. No inherited credentials or network."""
from __future__ import annotations

import io
import json
from pathlib import Path
import socket
import ssl
import urllib.error
import zipfile

import pytest
from short_interest_capture_fixtures import portable_capture_platform

from data.hashing import hash_bytes
import scripts.capture_short_interest_securities_master as capture
import os

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)

KEY = "fabricated-sharadar-key-for-offline-checks"
NOW = "2026-10-12T02:00:00Z"
HEAD, REMOTE = "a" * 40, "b" * 40
SIGNED = "https://signed-storage.example/tickers.csv.zip?ephemeral=fabricated-secret-capability"


class Headers(dict):
    def get_all(self, name):
        value = self.get(name)
        return value if type(value) is list else None if value is None else [value]


class Response:
    def __init__(self, raw=b"", *, status=200, location=None, ctype="application/json"):
        self.raw, self.status, self.reads, self.closed = raw, status, 0, False
        self.headers = Headers({"Content-Type": ctype})
        if location is not None:
            self.headers["Location"] = location

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def read(self, maximum):
        self.reads += 1
        return self.raw[:maximum]

    def close(self):
        self.closed = True


class Opener:
    def __init__(self, responses):
        self.responses, self.requests = iter(responses), []

    def open(self, request, timeout):
        assert timeout == 30
        self.requests.append(request)
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


class Report:
    sha256 = "c" * 64

    def to_payload(self):
        return {"fabricated_source_only": True}


def archive(table):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        item = zipfile.ZipInfo(table + ".csv", date_time=(2020, 1, 1, 0, 0, 0))
        item.compress_type = zipfile.ZIP_DEFLATED
        zipped.writestr(item, "a,b\nfixture,only\n")
    return output.getvalue()


def metadata(table, size=None):
    return json.dumps({"table": table, "name": table + ".csv.zip",
        "size": len(archive(table)) if size is None else size, "sizeLabel": "fixture",
        "modified": "2026-10-12T01:00:00Z"}).encode()


@pytest.fixture
def offline(monkeypatch):
    guards, downloads = [], []
    monkeypatch.setattr(capture, "_guard", lambda *args: guards.append(args))
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    monkeypatch.setattr(capture.master, "validate_archive", lambda table, raw: b"fixture,only\n")
    monkeypatch.setattr(capture.master, "qualify_sharadar_securities_master", lambda *args, **kwargs: Report())
    def download(location, key):
        assert location == SIGNED and key == KEY
        table = capture.master.TABLES[len(downloads)]
        downloads.append(location)
        return archive(table), "application/zip", 200
    monkeypatch.setattr(capture, "_download", download)
    return guards, downloads


def successful_opener():
    return Opener([Response(metadata(table)) for table in capture.master.TABLES]
        + [Response(("CREATE TABLE " + table + " (x TEXT);").encode(), ctype="text/plain")
           for table in capture.master.TABLES]
        + [Response(status=302, location=SIGNED) for _ in capture.master.TABLES])


def run(tmp_path, opener):
    return capture._capture(tmp_path, tmp_path, KEY, opener, head=HEAD, remote=REMOTE)


@_POSIX_CAPTURE_ONLY
def test_twelve_requests_source_bound_no_signed_URL_or_secret_persistence(tmp_path, offline):
    guards, downloads = offline
    opener = successful_opener()
    result = run(tmp_path, opener)
    assert result["http_attempts"] == 12
    assert result["backtest_result_exists"] is False
    assert len(opener.requests) == 9 and len(downloads) == 3 and len(guards) == 25
    for ordinal, request in enumerate(opener.requests):
        if 3 <= ordinal <= 5:
            assert request.get_header("X-api-key") is None
        else:
            assert request.get_header("X-api-key") == KEY
        assert KEY not in request.full_url
    for file in tmp_path.iterdir():
        assert KEY.encode() not in file.read_bytes()
        assert SIGNED.encode() not in file.read_bytes()
        assert b"ephemeral=" not in file.read_bytes()
    for ordinal in (7, 9, 11):
        receipt = json.loads((tmp_path / f"attempt-{ordinal:02d}.received.json").read_bytes())
        assert receipt["http_status"] == 302 and receipt["raw_sha256"] is None
        assert receipt["raw_path"] is None and receipt["raw_bytes"] is None
    assert (tmp_path / "master.private.json").exists()


@pytest.mark.parametrize("status", [200, 301, 303, 307, 308, 401, 403, 500, True])
@pytest.mark.usefixtures("portable_capture_platform")
def test_issuance_requires_exact_302_and_never_reads_body(status):
    response = Response(KEY.encode(), status=status, location=SIGNED)
    with pytest.raises(capture.MasterCaptureRefusal):
        capture._issuer_location(Opener([response]), object(), KEY)
    assert response.reads == 0 and response.closed


@pytest.mark.parametrize("location", [None, [], [SIGNED, SIGNED], "https://host.example/?key=" + KEY,
    "https://host.example/?key=" + KEY.replace("-", "%2D"), SIGNED + "\n", "x" * 16385])
@pytest.mark.usefixtures("portable_capture_platform")
def test_issuance_ambiguous_or_key_echo_location_is_not_followed(location):
    response = Response(status=302, location=location)
    with pytest.raises(capture.MasterCaptureRefusal):
        capture._issuer_location(Opener([response]), object(), KEY)
    assert response.reads == 0 and response.closed


@pytest.mark.usefixtures("portable_capture_platform")
def test_documented_HTTPError_redirect_is_processed_without_body():
    value = urllib.error.HTTPError("https://api.sharadar.com/fixed", 302, "not printed",
                                  Headers({"Location": SIGNED}), io.BytesIO(KEY.encode()))
    assert capture._issuer_location(Opener([value]), object(), KEY) == SIGNED
    assert value.fp is None or value.fp.closed


@pytest.mark.parametrize("location", ["http://host.example/a", "https://user:secret@host.example/a",
    "https://host.example:444/a", "https://host.example/a#fragment", "https://host.example./a",
    "https://%6cost.example/a", "https://[::1]/a"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_download_unsafe_origin_refuses_before_DNS(location):
    def forbidden(*args, **kwargs):
        pytest.fail("must refuse before DNS")
    with pytest.raises(capture.MasterCaptureRefusal):
        capture._public_addresses(location, resolve=forbidden)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "192.0.2.1", "224.0.0.1", "::1", "fc00::1"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_private_reserved_or_multicast_DNS_is_refused(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    resolve = lambda *args, **kwargs: [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]
    with pytest.raises(capture.MasterCaptureRefusal):
        capture._public_addresses(SIGNED, resolve=resolve)


@pytest.mark.usefixtures("portable_capture_platform")
def test_mixed_public_private_DNS_is_refused_not_filtered_to_public():
    resolve = lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))
                                      for ip in ("8.8.8.8", "127.0.0.1")]
    with pytest.raises(capture.MasterCaptureRefusal):
        capture._public_addresses(SIGNED, resolve=resolve)


@pytest.mark.usefixtures("portable_capture_platform")
def test_public_address_is_detached_numeric_target_and_hostname_preserved():
    parsed, target = capture._public_addresses(SIGNED, resolve=lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))])
    assert parsed.hostname == "signed-storage.example" and target == (socket.AF_INET, ("8.8.8.8", 443))


@pytest.mark.usefixtures("portable_capture_platform")
def test_TLS_requires_certificate_and_hostname_verification_before_connect():
    context = ssl._create_unverified_context()
    connection = capture._PinnedHTTPS("signed-storage.example", (socket.AF_INET, ("8.8.8.8", 443)), context=context)
    with pytest.raises(capture.MasterCaptureRefusal, match="TLS"):
        connection.connect()


@pytest.mark.parametrize("peer", ["8.8.8.8", "8.8.4.4", "127.0.0.1", "224.0.0.1"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_TCP_peer_is_pinned_before_normal_hostname_TLS(monkeypatch, peer):
    class FakeSocket:
        closed = False
        def settimeout(self, timeout):
            assert timeout == 30
        def connect(self, target):
            assert target == ("8.8.8.8", 443)
        def getpeername(self):
            return peer, 443
        def close(self):
            self.closed = True
    raw_socket = FakeSocket()
    monkeypatch.setattr(capture.socket, "socket", lambda *args: raw_socket)
    class VerifiedContext:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED
        wrapped = False
        def wrap_socket(self, sock, *, server_hostname):
            assert sock is raw_socket and server_hostname == "signed-storage.example"
            self.wrapped = True
            return sock
    context = VerifiedContext()
    connection = capture._PinnedHTTPS("signed-storage.example", (socket.AF_INET, ("8.8.8.8", 443)), context=context)
    if peer == "8.8.8.8":
        connection.connect()
        assert context.wrapped and connection.sock is raw_socket and not raw_socket.closed
    else:
        with pytest.raises(capture.MasterCaptureRefusal, match="peer_changed"):
            connection.connect()
        assert raw_socket.closed and not context.wrapped


@pytest.mark.parametrize("status,length", [(200, None), (200, "3"), (302, None), (200, "99")])
@pytest.mark.usefixtures("portable_capture_platform")
def test_anonymous_download_has_no_auth_proxy_retry_or_redirect(monkeypatch, status, length):
    raw = b"zip"
    class FakeResponse(Response):
        def getheader(self, name, default=None):
            return {"Content-Type": "application/zip", "Content-Length": length}.get(name, default)
    response = FakeResponse(raw, status=status)
    instances = []
    class Connection:
        def __init__(self, hostname, target, *, context):
            assert hostname == "signed-storage.example" and target[1][0] == "8.8.8.8"
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            self.closed, self.requests = False, []
            instances.append(self)
        def request(self, method, path, *, headers):
            self.requests.append((method, path, headers))
            assert method == "GET" and "ephemeral=" in path
            assert headers == {"Accept": "application/zip, application/octet-stream"}
            assert KEY not in repr(headers) and "Authorization" not in headers and "Cookie" not in headers
        def getresponse(self):
            return response
        def close(self):
            self.closed = True
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    monkeypatch.setattr(capture, "_public_addresses", lambda url: (
        capture.urllib.parse.urlsplit(url), (socket.AF_INET, ("8.8.8.8", 443))))
    monkeypatch.setattr(capture, "_PinnedHTTPS", Connection)
    if status == 200 and length in (None, "3"):
        assert capture._download(SIGNED, KEY) == (raw, "application/zip", 200)
    else:
        with pytest.raises(capture.MasterCaptureRefusal):
            capture._download(SIGNED, KEY)
    assert len(instances) == 1 and len(instances[0].requests) == 1 and instances[0].closed
    assert response.reads == (0 if status == 302 else 1)


@_POSIX_CAPTURE_ONLY
def test_late_guard_change_blocks_request_after_started_receipt(tmp_path, monkeypatch):
    calls = 0
    def guard(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise capture.CaptureRefusal("lane changed")
    monkeypatch.setattr(capture, "_guard", guard)
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    opener = Opener([])
    with pytest.raises(capture.MasterCaptureRefusal):
        run(tmp_path, opener)
    assert not opener.requests and (tmp_path / "attempt-01.started.json").exists()


@_POSIX_CAPTURE_ONLY
def test_valid_key_checked_archive_survives_metadata_size_race(tmp_path, offline):
    responses = [Response(metadata(table, len(archive(table)) + 1 if i == 0 else None))
                 for i, table in enumerate(capture.master.TABLES)]
    responses += [Response(("CREATE TABLE " + table + " (x TEXT);").encode(), ctype="text/plain")
                  for table in capture.master.TABLES]
    responses.append(Response(status=302, location=SIGNED))
    with pytest.raises(capture.MasterCaptureRefusal, match="size_changed"):
        run(tmp_path, Opener(responses))
    assert (tmp_path / "attempt-08.raw").read_bytes() == archive("tickers")
    assert not (tmp_path / "master.private.json").exists()
    assert (tmp_path / "attempt-08.refused.json").exists()


@_POSIX_CAPTURE_ONLY
def test_compressed_credential_echo_is_checked_before_archive_persistence(tmp_path, offline, monkeypatch):
    monkeypatch.setattr(capture.master, "validate_archive", lambda *args: b"a,b\nfixture," + KEY.encode())
    with pytest.raises(capture.MasterCaptureRefusal, match="credential_echo"):
        run(tmp_path, successful_opener())
    assert not (tmp_path / "attempt-08.raw").exists()
    assert not any(KEY.encode() in file.read_bytes() for file in tmp_path.iterdir())


@pytest.mark.parametrize("where,echo", [
    ("header", SIGNED), ("CSV", SIGNED), ("ZIP", SIGNED),
    ("CSV", "fabricated-secret-capability"),
    ("CSV", capture.urllib.parse.quote(SIGNED, safe="")),
    ("CSV", SIGNED.replace("/", "\\/")),
])
@_POSIX_CAPTURE_ONLY
def test_signed_capability_echo_never_reaches_receipt_or_raw_hash(tmp_path, offline, monkeypatch, where, echo):
    def download(location, key):
        return (archive("tickers") + (echo.encode() if where == "ZIP" else b""),
                echo if where == "header" else "application/zip", 200)
    monkeypatch.setattr(capture, "_download", download)
    monkeypatch.setattr(capture.master, "validate_archive", lambda *args:
                        b"a,b\nfixture," + (echo.encode() if where == "CSV" else b"safe"))
    with pytest.raises(capture.MasterCaptureRefusal, match="signed_capability_echo"):
        run(tmp_path, successful_opener())
    assert not (tmp_path / "attempt-08.raw").exists()
    assert not (tmp_path / "attempt-08.received.json").exists()
    assert not any(echo.encode() in file.read_bytes() for file in tmp_path.iterdir())


def test_short_nonsecret_expiry_is_not_a_row_value_ban_but_short_signature_is():
    location = "https://signed-storage.example/a?expires=600&sig=abc&X-Amz-SignedHeaders=host"
    capture._refuse_capability_echo(b"price,600\nservice,host\n", "application/zip", location)
    with pytest.raises(capture.MasterCaptureRefusal, match="signed_capability_echo"):
        capture._refuse_capability_echo(b"a,abc\n", "application/zip", location)


@pytest.mark.parametrize("location,raw", [
    ("https://host.example/a?sig=abc%252Fdef", b"a,abc/def\n"),
    ("https://host.example/a?sig=abc/def", b"a,abc%2fdef\n"),
    ("https://host.example/a?sig=abc/def", b'"abc\\u002fdef"'),
    ("https://host.example/fabricated-secret-path-token/data.zip", b"a,fabricated-secret-path-token\n"),
])
def test_partial_nested_encoded_or_path_capability_echo_is_refused(location, raw):
    with pytest.raises(capture.MasterCaptureRefusal, match="signed_capability_echo"):
        capture._refuse_capability_echo(raw, "application/zip", location)


@pytest.mark.usefixtures("portable_capture_platform")
def test_capture_clock_reversal_refuses_before_request(tmp_path, offline, monkeypatch):
    clocks = iter([NOW, "2026-10-12T01:59:59Z"])
    monkeypatch.setattr(capture, "_utc_now", lambda: next(clocks))
    opener = Opener([])
    with pytest.raises(capture.MasterCaptureRefusal, match="clock_reversed"):
        run(tmp_path, opener)
    assert not opener.requests


@_POSIX_CAPTURE_ONLY
def test_new_time_or_HEAD_cannot_reset_global_budget(tmp_path, offline, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(capture, "_git", lambda root, *args: args[-1])
    monkeypatch.setattr(capture, "_read_key", lambda path: KEY)
    monkeypatch.setattr(capture, "_capture", lambda *args, **kwargs: {"status": "fake_capture"})
    assert capture.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 0
    monkeypatch.setattr(capture, "_utc_now", lambda: "2026-10-12T02:00:01Z")
    assert capture.main(["--expected-head", "d" * 40, "--expected-remote", REMOTE]) == 2
    claims = list((tmp_path / capture.CAPTURE_PARENT).glob("budget-*.json"))
    assert len(claims) == 1 and claims[0].stat().st_mode & 0o777 == 0o600
    assert "whole_round_budget_claimed" in capsys.readouterr().out
