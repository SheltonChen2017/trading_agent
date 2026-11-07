"""Fabricated, network-denied diagnostics for one recovery HTTP invocation."""
from __future__ import annotations

import errno
import io
import json
import socket
import ssl
import urllib.error

import pytest

from scripts import short_interest_recovery_transport as transport


SECRET = "fabricated-token-not-an-account-or-real-key"


class HostileText:
    def __str__(self):
        raise AssertionError("external exception text must not be inspected")

    def __repr__(self):
        raise AssertionError("external exception repr must not be inspected")


class HostileTimeout(HostileText, TimeoutError):
    pass


class HostileURL(HostileText, urllib.error.URLError):
    pass


class HostileHTTP(HostileText, urllib.error.HTTPError):
    pass


class HostileOS(HostileText, OSError):
    pass


class HostileUnknown(HostileText, RuntimeError):
    pass


class Response:
    def __init__(self, raw=b"{}", *, status=200, media="application/json", error=None):
        self.raw, self.status = raw, status
        self.headers = {"Content-Type": media}
        self.error = error
        self.reads = []
        self.closed = 0

    def read(self, maximum):
        self.reads.append(maximum)
        if self.error is not None:
            raise self.error
        return self.raw[:maximum] if type(self.raw) is bytes else self.raw

    def close(self):
        self.closed += 1


class Opener:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request, timeout))
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class NoReadBody(io.BytesIO):
    def read(self, *args, **kwargs):
        raise AssertionError("HTTP error body must not be read")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("fabricated transport tests cannot reach a network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(transport, "_require_capture_platform", lambda: None)


def failure(value):
    opener = Opener(value)
    with pytest.raises(transport.RecoveryTransportFailure) as caught:
        transport.http(opener, object(), 64)
    assert len(opener.calls) == 1  # This layer must never retry.
    error = caught.value
    result = error.diagnostic()
    assert set(result) == {"code", "phase", "failure_class", "http_status", "retryable", "errno_name"}
    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in json.dumps(result)
    assert error.__context__ is None  # Do not retain an external secret-bearing exception.
    return error, result


@pytest.mark.parametrize("media", ["application/json", "application/json; charset=utf-8", "Application/JSON; Charset=UTF-8"])
def test_success_is_one_bounded_read_and_uses_only_supplied_opener(media):
    response = Response(media=media)
    opener, request = Opener(response), object()
    assert transport.http(opener, request, 2) == (b"{}", media, 200)
    assert opener.calls == [(request, 30)]
    assert response.reads == [3] and response.closed == 1


@pytest.mark.parametrize("value,kind,name,retry", [
    (HostileTimeout(SECRET), "timeout", None, True),
    (socket.gaierror(socket.EAI_AGAIN, SECRET), "dns_temporary", "EAI_AGAIN", True),
    (socket.gaierror(socket.EAI_NONAME, SECRET), "dns_permanent", "EAI_NONAME", False),
    (ConnectionResetError(errno.ECONNRESET, SECRET), "connection_reset", "ECONNRESET", True),
    (ConnectionRefusedError(errno.ECONNREFUSED, SECRET), "connection_refused", "ECONNREFUSED", True),
    (ConnectionAbortedError(errno.ECONNABORTED, SECRET), "connection_aborted", "ECONNABORTED", True),
    (HostileOS(errno.ENOSPC, SECRET), "resource_exhausted", "ENOSPC", False),
    (HostileOS(errno.EMFILE, SECRET), "resource_exhausted", "EMFILE", False),
    (HostileOS(errno.ENFILE, SECRET), "resource_exhausted", "ENFILE", False),
    (HostileOS(errno.ENOMEM, SECRET), "resource_exhausted", "ENOMEM", False),
    (HostileOS(errno.EACCES, SECRET), "os_error", "EACCES", False),
    (HostileOS(918273, SECRET), "os_error", None, False),
    (HostileOS(SECRET), "os_error", None, False),
    (ssl.SSLCertVerificationError(1, SECRET), "tls_certificate", None, False),
    (ssl.SSLError(1, SECRET), "tls", None, False),
    (HostileUnknown(SECRET), "unknown", None, False),
    (HostileURL(SECRET), "url_error", None, False),
])
def test_failure_classes_use_only_types_and_allowlisted_numeric_errno(value, kind, name, retry):
    error, diagnostic = failure(value)
    assert diagnostic == {"code": "network_failure", "phase": "open", "failure_class": kind,
                          "http_status": None, "retryable": retry, "errno_name": name}
    assert error.http_status is None and error.retryable is retry


def test_wrapped_urllib_reason_is_classified_without_text():
    error = HostileURL(HostileURL(HostileTimeout(SECRET)))
    _, diagnostic = failure(error)
    assert diagnostic["failure_class"] == "timeout" and diagnostic["retryable"] is True


def test_wrapped_http_error_preserves_status_and_closes_without_reading():
    body = NoReadBody(b"never-read-fabricated-error-body")
    error = HostileURL(HostileHTTP("https://example.invalid/" + SECRET, 404, SECRET, {}, body))
    _, diagnostic = failure(error)
    assert diagnostic == {"code": "http_not_200", "phase": "open", "failure_class": "http_status",
                          "http_status": 404, "retryable": False, "errno_name": None}
    assert body.closed


@pytest.mark.parametrize("wrapped", [False, True])
def test_http_status_accessor_failure_is_sanitized_and_handle_still_closes(wrapped):
    class HostileCode(HostileHTTP):
        @property
        def code(self):
            raise HostileUnknown(SECRET)

        @code.setter
        def code(self, value):
            pass
    body = NoReadBody(b"never-read-fabricated-error-body")
    error = HostileCode("https://example.invalid/" + SECRET, 404, SECRET, {}, body)
    _, diagnostic = failure(HostileURL(error) if wrapped else error)
    assert diagnostic["code"] == "http_not_200" and diagnostic["http_status"] is None
    assert diagnostic["retryable"] is False and body.closed


def test_url_reason_unwrapping_is_bounded_and_cycles_refuse():
    error = HostileURL(SECRET)
    error.reason = error
    _, cyclic = failure(error)
    assert cyclic["failure_class"] == "url_error" and cyclic["retryable"] is False
    nested = HostileTimeout(SECRET)
    for _ in range(20):
        nested = HostileURL(nested)
    _, deep = failure(nested)
    assert deep["failure_class"] == "url_error" and deep["retryable"] is False


def test_untrusted_errno_override_is_not_used():
    class MaliciousErrno(HostileOS):
        @property
        def errno(self):
            raise AssertionError("subclass errno property is untrusted")
    _, diagnostic = failure(MaliciousErrno(errno.ECONNRESET, SECRET))
    assert diagnostic["errno_name"] == "ECONNRESET" and diagnostic["retryable"] is True


@pytest.mark.parametrize("error_type", [HostileTimeout, ConnectionResetError, ConnectionRefusedError])
@pytest.mark.parametrize("number,name", [(errno.ENOSPC, "ENOSPC"), (errno.EMFILE, "EMFILE")])
def test_resource_errno_overrides_transient_exception_class(error_type, number, name):
    _, diagnostic = failure(error_type(number, SECRET))
    assert diagnostic["failure_class"] == "resource_exhausted"
    assert diagnostic["errno_name"] == name and diagnostic["retryable"] is False


def test_known_response_status_is_retained_and_read_failure_never_retries():
    response = Response(error=HostileTimeout(SECRET))
    _, diagnostic = failure(response)
    assert diagnostic == {"code": "network_failure", "phase": "read", "failure_class": "timeout",
                          "http_status": 200, "retryable": False, "errno_name": None}
    assert response.closed == 1


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500, 503, SECRET, True, None, 999])
def test_http_error_status_is_sanitized_error_body_is_never_read_and_handle_closes(status):
    body = NoReadBody(b"never-read-fabricated-error-body")
    error = HostileHTTP("https://example.invalid/?key=" + SECRET,
                        status, SECRET, {"Authorization": SECRET}, body)
    _, diagnostic = failure(error)
    assert diagnostic == {"code": "http_not_200", "phase": "open", "failure_class": "http_status",
                          "http_status": status if type(status) is int and 100 <= status <= 599 else None,
                          "retryable": False, "errno_name": None}
    assert body.closed


@pytest.mark.parametrize("status", [201, 403, 503, SECRET, True, None, 999])
def test_response_status_refusal_precedes_body_or_headers(status):
    response = Response(status=status)
    response.headers = object()  # Access would fail if a bad status reached headers.
    _, diagnostic = failure(response)
    assert diagnostic["code"] == "http_not_200" and diagnostic["phase"] == "response"
    assert diagnostic["retryable"] is False and response.reads == [] and response.closed == 1


@pytest.mark.parametrize("media", ["", "text/html", "application/json; charset=latin-1", "application/json\r\n" + SECRET,
                                  SECRET, "a" * 257, None, True])
def test_invalid_media_is_fixed_refusal_without_echo_or_body_read(media):
    response = Response(media=media)
    _, diagnostic = failure(response)
    assert diagnostic["code"] == "content_type" and diagnostic["phase"] == "response"
    assert diagnostic["http_status"] == 200 and diagnostic["retryable"] is False
    assert response.reads == [] and response.closed == 1


def test_oversize_and_nonbytes_body_refuse_without_retaining_body():
    response = Response(raw=b"x" * 65)
    _, diagnostic = failure(response)
    assert diagnostic["code"] == "response_size_limit" and diagnostic["http_status"] == 200
    assert response.reads == [65] and response.closed == 1
    response = Response(raw=SECRET)
    _, diagnostic = failure(response)
    assert diagnostic["code"] == "response_contract_refused" and response.closed == 1


@pytest.mark.parametrize("maximum", [0, -1, True, 1.0, "64", None, 2 * 1024 * 1024 + 1])
def test_invalid_maximum_refuses_before_open(maximum):
    opener = Opener(Response())
    with pytest.raises(transport.RecoveryTransportFailure) as caught:
        transport.http(opener, object(), maximum)
    assert caught.value.code == "response_limit" and opener.calls == []


def test_platform_preflight_runs_before_any_open(monkeypatch):
    def denied():
        raise ValueError("fabricated_platform_refusal")
    monkeypatch.setattr(transport, "_require_capture_platform", denied)
    opener = Opener(Response())
    with pytest.raises(ValueError, match="^fabricated_platform_refusal$"):
        transport.http(opener, object(), 64)
    assert opener.calls == []


def test_close_failure_is_safe_nonretry_and_does_not_replace_original_failure():
    class BrokenClose(Response):
        def close(self):
            super().close()
            raise HostileUnknown(SECRET)
    _, diagnostic = failure(BrokenClose())
    assert diagnostic["phase"] == "response" and diagnostic["retryable"] is False
    _, original = failure(BrokenClose(error=HostileTimeout(SECRET)))
    assert original["phase"] == "read" and original["failure_class"] == "timeout"


def test_diagnostic_constructor_rejects_arbitrary_text_in_fixed_fields():
    with pytest.raises(ValueError, match="^recovery_transport_diagnostic_contract$"):
        transport.RecoveryTransportFailure(SECRET, phase="open", failure_class="unknown")
