"""One bounded SI recovery GET with fixed, secret-safe failure diagnostics.

The caller must first validate its existing no-proxy/no-redirect protected
opener, publish and debit a fresh START, and enforce its frozen retry policy.
This layer neither creates an opener nor retries, sleeps, persists, or reads a
credential. It does not change any previous capture's transport or claim.
"""
from __future__ import annotations

import errno
import re
import socket
import ssl
import urllib.error

from scripts.qualify_finra_short_interest import _require_capture_platform
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal


MAXIMUM_BODY_BYTES = 2 * 1024 * 1024
MAXIMUM_REASON_DEPTH = 4
_NETWORK_CLASSES = frozenset({
    "timeout", "dns_temporary", "dns_permanent", "connection_reset",
    "connection_refused", "connection_aborted", "resource_exhausted",
    "tls_certificate", "tls", "os_error", "url_error", "unknown",
})
_CLASSES = {
    "network_failure": _NETWORK_CLASSES,
    "http_not_200": frozenset({"http_status"}),
    "response_size_limit": frozenset({"response_size"}),
    "content_type": frozenset({"content_type"}),
    "response_contract_refused": frozenset({"response_contract"}),
    "response_limit": frozenset({"response_limit"}),
}
_ERRNO_NAMES = (
    "ETIMEDOUT", "ECONNRESET", "ECONNREFUSED", "ECONNABORTED", "ENOSPC",
    "EMFILE", "ENFILE", "ENOMEM", "EACCES", "EPERM", "EIO", "EBADF",
    "ENETDOWN", "ENETUNREACH", "EHOSTUNREACH", "EPIPE",
)
_DNS_NAMES = ("EAI_AGAIN", "EAI_NONAME", "EAI_FAIL", "EAI_NODATA", "EAI_MEMORY", "EAI_SYSTEM")
_SAFE_ERRNO_NAMES = frozenset((*_ERRNO_NAMES, *_DNS_NAMES))
_TRANSIENT_CLASSES = frozenset({"timeout", "dns_temporary", "connection_reset",
                                "connection_refused", "connection_aborted"})
_JSON_MEDIA = re.compile(
    r'[ \t]*application/json[ \t]*(?:;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8")[ \t]*)?',
    re.IGNORECASE,
)


def _status(value) -> int | None:
    return value if type(value) is int and 100 <= value <= 599 else None


def _http_error_status(error: urllib.error.HTTPError) -> int | None:
    try:
        return _status(error.code)
    except Exception:
        return None


class RecoveryTransportFailure(SharadarCaptureRefusal):
    """Only fixed allowlisted fields; never an external message or type name."""

    def __init__(self, code: str, *, phase: str, failure_class: str,
                 status: int | None = None, retryable: bool = False,
                 errno_name: str | None = None):
        if (type(code) is not str or code not in _CLASSES
                or type(phase) is not str or phase not in {"open", "read", "response"}
                or type(failure_class) is not str or failure_class not in _CLASSES[code]
                or type(retryable) is not bool
                or (errno_name is not None and (type(errno_name) is not str
                                               or errno_name not in _SAFE_ERRNO_NAMES))):
            raise ValueError("recovery_transport_diagnostic_contract")
        safe_status = _status(status)
        if retryable and (phase != "open" or safe_status is not None
                          or code != "network_failure" or failure_class not in _TRANSIENT_CLASSES):
            raise ValueError("recovery_transport_diagnostic_contract")
        super().__init__(code, status=safe_status)
        self.phase, self.failure_class = phase, failure_class
        self.retryable, self.errno_name = retryable, errno_name
        self._fixed_diagnostic = (code, phase, failure_class, safe_status, retryable, errno_name)

    def diagnostic(self) -> dict:
        """Return a fresh projection, with no exception, request or body object."""
        return dict(zip(("code", "phase", "failure_class", "http_status", "retryable", "errno_name"),
                        self._fixed_diagnostic))


def _errno_number(error: OSError) -> int | None:
    # Read the built-in numeric slot, not a subclass's arbitrary property.
    value = OSError.errno.__get__(error, OSError)
    return value if type(value) is int else None


def _errno_name(number: int | None, names: tuple[str, ...], module) -> str | None:
    for name in names:
        value = getattr(module, name, None)
        if type(value) is int and number == value:
            return name
    return None


def _network_failure(error: Exception, phase: str, status: int | None) -> RecoveryTransportFailure:
    # URLError.reason alone may wrap a typed socket error. Do not consult
    # args, __cause__, __context__, URLs, arbitrary exception names, or text.
    current, seen = error, set()
    for _ in range(MAXIMUM_REASON_DEPTH):
        if not isinstance(current, urllib.error.URLError) or isinstance(current, urllib.error.HTTPError):
            break
        if id(current) in seen:
            break
        seen.add(id(current))
        try:
            reason = current.reason
        except Exception:
            break
        if not isinstance(reason, Exception) or id(reason) in seen:
            break
        current = reason

    if isinstance(current, urllib.error.HTTPError):
        observed_status = status if status is not None else _http_error_status(current)
        try:
            current.close()
        except Exception:
            pass  # The HTTP refusal remains dominant; never inspect close text.
        return RecoveryTransportFailure("http_not_200", phase=phase,
                                        failure_class="http_status", status=observed_status)

    name = None
    if isinstance(current, urllib.error.URLError):
        kind = "url_error"
    elif isinstance(current, ssl.SSLCertVerificationError):
        kind = "tls_certificate"
    elif isinstance(current, ssl.SSLError):
        kind = "tls"
    elif isinstance(current, socket.gaierror):
        name = _errno_name(_errno_number(current), _DNS_NAMES, socket)
        kind = "dns_temporary" if name == "EAI_AGAIN" else "dns_permanent"
    elif isinstance(current, OSError):
        name = _errno_name(_errno_number(current), _ERRNO_NAMES, errno)
        # A local resource failure cannot become transient merely because an
        # exception subclass carries a connection/timeout-shaped name.
        if name in {"ENOSPC", "EMFILE", "ENFILE", "ENOMEM"}:
            kind = "resource_exhausted"
        elif isinstance(current, TimeoutError):
            kind = "timeout"
        elif isinstance(current, ConnectionResetError) or name == "ECONNRESET":
            kind = "connection_reset"
        elif isinstance(current, ConnectionRefusedError) or name == "ECONNREFUSED":
            kind = "connection_refused"
        elif isinstance(current, ConnectionAbortedError) or name == "ECONNABORTED":
            kind = "connection_aborted"
        else:
            kind = "os_error"
    else:
        kind = "unknown"
    return RecoveryTransportFailure("network_failure", phase=phase, failure_class=kind,
                                    status=status, errno_name=name,
                                    retryable=phase == "open" and status is None and kind in _TRANSIENT_CLASSES)


def http(opener, request, maximum: int) -> tuple[bytes, str, int]:
    """Invoke the supplied protected opener once; return only bounded HTTP200 JSON.

    A status-less failure remains an unknown provider debit, not proof that no
    request arrived. ``retryable`` is a classification, never retry authority;
    the caller must debit every new attempt under its prospectively frozen cap.
    """
    _require_capture_platform()
    if type(maximum) is not int or not 1 <= maximum <= MAXIMUM_BODY_BYTES:
        raise RecoveryTransportFailure("response_limit", phase="response", failure_class="response_limit")
    response, result, failure = None, None, None
    phase, status = "open", None
    try:
        response = opener.open(request, timeout=30)
        phase = "response"
        status = _status(response.status)
        if status != 200:
            raise RecoveryTransportFailure("http_not_200", phase=phase,
                                            failure_class="http_status", status=status)
        media = response.headers.get("Content-Type", "")
        if type(media) is not str or len(media) > 256 or _JSON_MEDIA.fullmatch(media) is None:
            raise RecoveryTransportFailure("content_type", phase=phase,
                                            failure_class="content_type", status=status)
        phase = "read"
        raw = response.read(maximum + 1)
        if type(raw) is not bytes:
            raise RecoveryTransportFailure("response_contract_refused", phase=phase,
                                            failure_class="response_contract", status=status)
        if len(raw) > maximum:
            raise RecoveryTransportFailure("response_size_limit", phase=phase,
                                            failure_class="response_size", status=status)
        result = (raw, media, status)
    except RecoveryTransportFailure as error:
        failure = error
    except urllib.error.HTTPError as error:
        # Close without reading error bodies, headers, Location, URLs or text.
        if response is None:
            response = error
            status = _http_error_status(error)
        failure = RecoveryTransportFailure("http_not_200", phase=phase,
                                            failure_class="http_status", status=status)
    except Exception as error:
        failure = _network_failure(error, phase, status)
    finally:
        if response is not None:
            try:
                response.close()
            except Exception as error:
                if failure is None:
                    failure = _network_failure(error, "response", status)
    # Raising outside the handler does not retain a secret-bearing external
    # exception as this fixed diagnostic's __context__.
    if failure is not None:
        raise failure
    return result
