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
        "provider response appears to echo credential material; persistence refused",
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
        "physical capture contract hash is not an admitted exact version",
        "capture transport is not reviewed",
        "capture storage mode must be an exact boolean",
        "capture timestamp could not form an artifact ID",
        "offline test transport requires a synthetic key",
        "expected capture transport is not reviewed",
        "capture page visitor must be callable",
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
        "provider row contains a non-finite number",
        "provider row contains invalid text",
        "provider row contains a non-string object key",
        "provider row contains an unsupported JSON scalar",
        "capture exceeds the reviewed retained-byte budget",
        "provider replayed a response page",
        "provider cursor repeats or cycles",
        "provider page failed capture binding",
        "capture exceeded the reviewed retained-byte budget",
        "complete provider capture failed authentication",
        "capture manifest is not canonical JSON",
        "capture manifest must be an object",
        "capture manifest schema changed",
        "artifact ID does not match its directory",
        "artifact ID timestamp does not match capture chronology",
        "manifest date range is reversed",
        "manifest stored-byte budget changed",
        "manifest stored-row budget changed",
        "manifest capture transport is not reviewed",
        "manifest capture storage mode is inconsistent",
        "production capture was not page-spooled",
        "manifest provider-I/O classification changed",
        "manifest source-role order changed",
        "manifest exceeds the stored-byte budget",
        "manifest exceeds the stored-row budget",
        "capture manifest field is invalid",
        "manifest role counts are incomplete",
        "manifest page inventory is empty",
        "manifest page inventory exceeds the bound",
        "manifest chronology is invalid",
        "manifest capture chronology is reversed",
        "manifest role count must be an object",
        "manifest role counts are out of order",
        "manifest role count is invalid",
        "manifest page must be an object",
        "manifest page source role is invalid",
        "manifest page number is invalid",
        "manifest pages are not in canonical role order",
        "manifest skipped a source role",
        "manifest role page chain did not terminate",
        "manifest terminal page was followed",
        "manifest pages are not contiguous from one",
        "manifest endpoint path changed",
        "manifest query binding changed",
        "manifest page filenames are not canonical",
        "manifest page field is invalid",
        "manifest page chronology is invalid",
        "manifest cursor chain is discontinuous",
        "manifest terminal-page state is inconsistent",
        "manifest cursor chain repeats or cycles",
        "manifest repeats a raw response page",
        "manifest did not complete every source role",
        "manifest role counts do not match pages",
        "manifest aggregate counts do not match pages",
        "capture transport does not match bridge expectation",
        "persisted provider rows are not the canonical ordered extraction",
        "manifest cursor hash does not match the exact provider response",
        "persisted page failed capture binding",
        "manifest page row count does not match authenticated bytes",
        "manifest endpoint identifier changed",
        "capture visitation was not exhaustive",
        "capture exceeds the bridge page-count budget",
        "capture exceeds the bridge row-count budget",
        "capture exceeds the bridge retained-byte budget",
        "capture exceeds the bridge provider-row byte budget",
        "capture exceeds the active bridge budget",
        "manifest did not contain every source role",
        "persisted capture failed authentication",
        "current capture identity does not reconstruct",
        "manifest capture identity does not reconstruct",
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
        "capture page did not retain exact raw response bytes",
        "manifest logical capture identity changed",
        "artifact manifest changed logical capture identity",
        "timestamped capture already exists; overwrite refused",
        "timestamped incomplete capture already exists; overwrite refused",
        "raw response bytes disappeared before persistence",
        "timestamped capture publication failed or overwrite was refused",
        "capture artifact inventory is unreadable",
        "capture artifact root inventory does not match",
        "capture artifact page inventory does not match manifest",
        "capture artifact inventory changed during inspection",
        "capture artifact inventory changed",
        "capture artifact path identity changed during visitation",
        "capture manifest digest does not authenticate bytes",
        "persisted page byte count or hash changed",
    )),
)


def classify_capture_failure(exc: BaseException) -> str:
    """Return one static code without calling caller-controlled rendering.

    Only the production import name and finite exact messages are recognized;
    unrecognized class metadata and direct built-in/network exceptions are unknown. No prefix,
    substring, regex or message parsing can accidentally echo a secret.
    """
    kind = type(exc)
    # isinstance can consult a nonexception's hostile __class__. Normal type
    # lookup, even type.__getattribute__, can invoke metadata descriptors on
    # a class or metaclass. Read the built-in storage descriptors instead.
    if not issubclass(kind, BaseException):
        return "unknown"
    module = type.__dict__["__module__"].__get__(kind)
    name = type.__dict__["__qualname__"].__get__(kind)
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
