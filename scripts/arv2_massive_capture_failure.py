"""Finite redacted failure labels for future bounded Massive callers.

This import-free helper performs no I/O and never renders an exception, its
arguments, traceback or cause. The labels describe recognized refusal messages,
not independently authenticated causes, contact accounting or retry authority.
The module/name check is deliberately not claimed as class authentication.
Unknown messages, classes and argument shapes remain unknown. In particular,
this cannot recover the discarded reason for the spent R287 invocation.
"""


_GROUPS = (
    ("credential", (
        "MASSIVE_API_KEY is unavailable or malformed; refusing provider access",
    )),
    ("unsafe_configuration", (
        "requests is required for Massive capture",
        "operational capture root must remain beneath repository artifacts",
        "Massive capture requires POSIX dirfd, no-follow, and private-mode enforcement",
        "spooled capture configuration is not reviewed",
        "accepted-risk pair construction requires a separately reviewed bounded bridge",
        "requested event-date range is reversed",
        "capture clock did not return an aware instant",
        "artifact root must be an owner-held private 0700 directory",
        "artifact root must not traverse a link and must be a directory",
        "provider next_url changed host, endpoint, or secret boundary",
        "provider next_url contains credential material",
        "provider next_url contains an unreviewed query field",
        "provider next_url changed the frozen query",
        "provider response URL left the reviewed endpoint",
        "provider response URL contains credential material",
        "provider request was not prepared as exact GET",
        "prepared provider request changed the frozen query",
        "provider response URL changed the prepared request",
    )),
    # The frozen adapter uses these messages for its request/session boundary,
    # including preparation, response iteration and session close. This label
    # does not prove a network failure or whether provider contact occurred.
    ("network_request", (
        "Timeout: provider request failed; details redacted",
        "ConnectTimeout: provider request failed; details redacted",
        "ReadTimeout: provider request failed; details redacted",
        "ConnectionError: provider request failed; details redacted",
        "SSLError: provider request failed; details redacted",
        "ProxyError: provider request failed; details redacted",
        "RequestException: provider request failed; details redacted",
        "ChunkedEncodingError: provider request failed; details redacted",
        "ContentDecodingError: provider request failed; details redacted",
        "OSError: provider request failed; details redacted",
        "RuntimeError: provider request failed; details redacted",
        "AttributeError: provider request failed; details redacted",
        "TypeError: provider request failed; details redacted",
        "ValueError: provider request failed; details redacted",
    )),
    ("http_status", (
        "provider returned a non-success HTTP status",
    )),
    ("response_schema", (
        "provider response is not bounded exact bytes",
        "provider response is not strict JSON",
        "provider response must contain one ordered results array",
        "provider response status is not exact OK",
        "provider returned more rows than the requested limit",
        "provider results must contain only JSON objects",
        "provider next_url must be absent, null, or nonempty text",
        "provider next_url is malformed",
        "provider next_url query is malformed",
        "provider next_url repeats a query parameter",
        "provider next_url lacks one bounded cursor",
        "provider rows could not be rendered canonically",
        "canonical provider rows exceed the page-byte limit",
        "provider response URL is malformed",
        "provider response URL query is malformed",
        "prepared request URL query is malformed",
        "prepared request URL repeats a query parameter",
        "provider response stream yielded non-bytes",
        "provider response exceeded the byte limit",
        "provider response body is not exact bytes",
        "capture page receipt times must be nondecreasing",
        "capture chronology is reversed",
        "capture exceeded the bounded page count",
        "capture exceeded the reviewed stored-byte budget",
        "capture exceeded the reviewed stored-row budget",
        "capture manifest exceeds the byte limit",
        "capture exceeds the reviewed stored-byte budget",
    )),
    ("persistence_publication", (
        "artifact directory entry could not be inspected",
        "artifact root root directory is unavailable",
        "artifact root is unavailable",
        "artifact root could not be prepared safely",
        "timestamped capture or incomplete staging already exists",
        "timestamped capture staging could not be created",
        "capture publication failed",
        "capture publication state is ambiguous after identity verification failure",
        "capture publication state is ambiguous after root-sync failure",
        "capture publication state is ambiguous after rollback sync failure",
        "capture staging artifact directory sync failed",
        "capture root publication directory sync failed",
        "capture root rollback directory sync failed",
        "capture manifest could not be created",
        "capture manifest could not be durably written",
        "capture manifest write failed",
        "capture manifest write stalled",
        "capture manifest digest could not be created",
        "capture manifest digest could not be durably written",
        "capture manifest digest write failed",
        "capture manifest digest write stalled",
    )),
)


def classify_capture_failure(exc: BaseException) -> str:
    """Return one static code without calling caller-controlled rendering.

    Only the production import name and finite exact messages are recognized;
    unrecognized class metadata and direct built-in/network exceptions are unknown. No prefix,
    substring, regex or message parsing can accidentally echo a secret.
    """
    if not isinstance(exc, BaseException):
        return "unknown"
    kind = type(exc)
    module = type.__getattribute__(kind, "__module__")
    name = type.__getattribute__(kind, "__qualname__")
    if (
        type(module) is not str
        or type(name) is not str
        or module != "scripts.capture_arv2_massive"
        or name != "MassiveCaptureError"
    ):
        return "unknown"
    args = BaseException.args.__get__(exc)
    if (
        type(args) is not tuple or len(args) != 1
        or type(args[0]) is not str or len(args[0]) > 200
    ):
        return "unknown"
    for code, messages in _GROUPS:
        if args[0] in messages:
            return code
    return "unknown"
