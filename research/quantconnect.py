"""QuantConnect cloud API client — RESEARCH ONLY.

Why this exists. The binding constraint on this project's research is not
statistics, it is breadth: a hand-written 104-ticker universe with a
measured minimum detectable effect of 2-4%, against real equity edges that
live well under 1%. QuantConnect supplies a survivorship-bias-free,
point-in-time-corrected US universe of thousands of names. This module is
how the project can drive backtests there and bring the RESULTS home.

**Two hard boundaries, both load-bearing.**

1. *No execution authority.* Nothing here may create, size, approve,
   submit, cancel, or replace an order, and nothing here may be reachable
   from code that can. This module must never import ``assistant``,
   ``execution``, ``risk``, or storage. Pinned by
   ``tests/test_quantconnect_client.py``.

2. *No raw market data leaves QuantConnect.* Their terms are explicit:
   "Users shall not export any part of the Site in raw form, such as CSV,
   API, FTP, or other formats", and download licences are "for the licensed
   organization's internal LEAN use only and cannot be redistributed or
   converted in any format". So this client deliberately exposes only the
   endpoints that return an ALGORITHM'S OWN RESULTS — statistics, charts,
   the run's own orders — and never a market-data endpoint. That is not a
   politeness; pulling their data into this project's
   ``{ticker: DataFrame}`` pipeline would breach the licence that makes
   their free tier possible.

**What this unlocks that the local page cannot do.** `backtest/interactive`
states plainly that it applies no multiple-comparison correction and that
"every parameter tweak is another uncounted look". Those looks are
uncountable there because a human twiddles a widget. Driven through an
API, every backtest and every optimization sweep is a call this project
initiated -- so the search can finally be *counted by construction* rather
than estimated after the fact. Counting is a later milestone; this module
is the transport it will need.

Authentication follows QuantConnect's documented scheme, in which the API
token itself is never transmitted:

    stamped = f"{api_token}:{unix_timestamp}"
    hashed  = sha256(stamped).hexdigest()
    header  = "Basic " + base64(f"{user_id}:{hashed}")

plus a ``Timestamp`` header carrying the same unix timestamp, which acts as
the nonce. Every call is an HTTP POST (including ``authenticate`` with an
empty JSON object), matching QuantConnect's documented API contract.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib import error, request

API_BASE = "https://www.quantconnect.com/api/v2"

USER_ID_ENV_VAR = "QC_USER_ID"
API_TOKEN_ENV_VAR = "QC_API_TOKEN"

# Endpoints this client is willing to call. An allowlist rather than a
# denylist: a new market-data endpoint added to QuantConnect must not become
# reachable here merely because nobody remembered to forbid it. Results,
# projects, compiles and backtests only.
#
# ``authenticate`` is exact-match only. The others are directory prefixes
# (must end with "/"), so ``backtests/../data/read`` cannot sneak through a
# startswith check after URL normalization.
_ALLOWED_EXACT_PATHS = frozenset({"authenticate"})
_ALLOWED_PATH_PREFIXES = (
    "projects/",
    "files/",
    "compile/",
    "backtests/",
    "optimizations/",
)


class QuantConnectError(RuntimeError):
    """The QuantConnect API could not be used for this request."""


class QuantConnectNotConfigured(QuantConnectError):
    """Credentials are absent. Never a reason to fall back to anything."""


@dataclass(frozen=True)
class QuantConnectCredentials:
    """User id and API token, read from the environment.

    Deliberately NOT accepted as literals from a caller anywhere in this
    repository: a token passed as an argument tends to end up in a default,
    a test fixture, or a log line. `from_env` is the only constructor used
    in production paths.
    """

    user_id: str
    api_token: str

    def __post_init__(self) -> None:
        for name, value in (("user_id", self.user_id), ("api_token", self.api_token)):
            if not isinstance(value, str) or not value.strip():
                raise QuantConnectNotConfigured(f"{name} must be a non-empty string")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "QuantConnectCredentials":
        source = os.environ if environ is None else environ
        user_id = (source.get(USER_ID_ENV_VAR) or "").strip()
        api_token = (source.get(API_TOKEN_ENV_VAR) or "").strip()
        if not user_id or not api_token:
            raise QuantConnectNotConfigured(
                f"{USER_ID_ENV_VAR} / {API_TOKEN_ENV_VAR} are not set. Get the "
                "user id from your QuantConnect account page and request an "
                "API token from its security section."
            )
        return cls(user_id=user_id, api_token=api_token)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        # The token must not reach a traceback, a log, or a debugger dump.
        return f"QuantConnectCredentials(user_id={self.user_id!r}, api_token=<redacted>)"


def is_configured(environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return bool((source.get(USER_ID_ENV_VAR) or "").strip()) and bool(
        (source.get(API_TOKEN_ENV_VAR) or "").strip()
    )


def build_auth_headers(
    credentials: QuantConnectCredentials, timestamp: int
) -> dict[str, str]:
    """QuantConnect's documented auth headers.

    Pure by design: the timestamp is passed in rather than read from the
    clock, so the exact documented algorithm is testable against known
    vectors without freezing time or reaching the network.
    """
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        raise QuantConnectError(f"timestamp must be an int, got {timestamp!r}")
    if timestamp <= 0:
        raise QuantConnectError(f"timestamp must be positive, got {timestamp}")
    stamped = f"{credentials.api_token}:{timestamp}"
    hashed = hashlib.sha256(stamped.encode("utf-8")).hexdigest()
    encoded = base64.b64encode(
        f"{credentials.user_id}:{hashed}".encode("utf-8")
    ).decode("ascii")
    return {"Authorization": f"Basic {encoded}", "Timestamp": str(timestamp)}


def _assert_allowed(path: str) -> None:
    if not isinstance(path, str) or not path.strip():
        raise QuantConnectError(f"path must be a non-empty string, got {path!r}")
    cleaned = path.strip().lstrip("/")
    # Refuse traversal and alternate separators before any prefix check.
    # ``backtests/../data/read`` would otherwise pass startswith("backtests/")
    # and become a market-data URL after client or server normalization.
    if (
        ".." in cleaned
        or "\\" in cleaned
        or "://" in cleaned
        or "\x00" in cleaned
        or "//" in cleaned
    ):
        raise QuantConnectError(
            f"path {path!r} is not on this client's allowlist. Market-data "
            "endpoints are deliberately unreachable: QuantConnect's licence "
            "forbids exporting raw data, and this project must not convert "
            "it into local frames."
        )
    if cleaned in _ALLOWED_EXACT_PATHS:
        return
    if any(cleaned.startswith(prefix) for prefix in _ALLOWED_PATH_PREFIXES):
        return
    raise QuantConnectError(
        f"path {path!r} is not on this client's allowlist. Market-data "
        "endpoints are deliberately unreachable: QuantConnect's licence "
        "forbids exporting raw data, and this project must not convert "
        "it into local frames."
    )


def _default_transport(
    url: str, payload: bytes | None, headers: Mapping[str, str], timeout: float
) -> tuple[int, bytes]:
    # QuantConnect documents every authenticated call as POST, including
    # authenticate with an empty JSON object. urllib.Request with data=None
    # is GET, which is not the documented contract.
    req = request.Request(
        url, data=payload if payload is not None else b"{}", headers=dict(headers), method="POST"
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.getcode(), response.read()
    except error.HTTPError as exc:  # a real response, just not a 2xx
        return exc.code, exc.read()
    except Exception as exc:  # network-level failure
        raise QuantConnectError(f"request to {url} failed: {exc}") from exc


class QuantConnectClient:
    """Thin, allowlisted transport over the QuantConnect REST API.

    ``transport`` and ``clock`` are injected so every test runs offline and
    deterministically; nothing in this class needs a live account to be
    exercised.
    """

    def __init__(
        self,
        credentials: QuantConnectCredentials | None = None,
        *,
        base_url: str = API_BASE,
        transport: Callable[..., tuple[int, bytes]] | None = None,
        clock: Callable[[], int] | None = None,
        timeout: float = 30.0,
    ) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise QuantConnectError(f"timeout must be a positive finite number, got {timeout!r}")
        self._credentials = credentials or QuantConnectCredentials.from_env()
        self._base_url = base_url.rstrip("/")
        self._transport = transport or _default_transport
        if clock is not None:
            self._clock = clock
        else:
            import time

            self._clock = lambda: int(time.time())
        self._timeout = float(timeout)

    def request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """One allowlisted POST. Returns the decoded JSON body.

        QuantConnect signals failure in-band with ``success: false`` and an
        ``errors`` list, so a 200 is not sufficient evidence of success and
        is not treated as such here. A missing ``success`` field is also
        refusal — fail closed rather than invent a default.
        """
        _assert_allowed(path)
        headers = build_auth_headers(self._credentials, self._clock())
        # Always POST with a JSON body. Empty object for no-arg endpoints
        # (authenticate), matching QuantConnect's curl examples.
        body = json.dumps({} if payload is None else payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        url = f"{self._base_url}/{path.lstrip('/')}"
        status, raw = self._transport(url, body, headers, self._timeout)
        try:
            decoded = json.loads(raw.decode("utf-8") or "{}")
        except ValueError as exc:
            raise QuantConnectError(
                f"{path} returned a non-JSON body (HTTP {status})"
            ) from exc
        if not isinstance(decoded, dict):
            raise QuantConnectError(f"{path} returned {type(decoded).__name__}, expected an object")
        if status >= 400 or decoded.get("success") is not True:
            errors = decoded.get("errors") or decoded.get("messages") or []
            raise QuantConnectError(
                f"{path} failed (HTTP {status}): {'; '.join(str(e) for e in errors) or 'no reason given'}"
            )
        return decoded

    def authenticate(self) -> dict[str, Any]:
        """Cheapest possible credential check."""
        return self.request("authenticate")

    def read_backtest(self, project_id: int, backtest_id: str) -> dict[str, Any]:
        """Statistics and metadata for one backtest -- results, not data."""
        if not isinstance(project_id, int) or isinstance(project_id, bool):
            raise QuantConnectError(f"project_id must be an int, got {project_id!r}")
        if not isinstance(backtest_id, str) or not backtest_id.strip():
            raise QuantConnectError(
                f"backtest_id must be a non-empty string, got {backtest_id!r}"
            )
        return self.request(
            "backtests/read",
            {"projectId": project_id, "backtestId": backtest_id.strip()},
        )

    def list_backtests(self, project_id: int) -> dict[str, Any]:
        """Every backtest recorded for a project.

        This is the endpoint a future look-counting milestone needs: the
        number of runs against a project IS the search count that
        `backtest/interactive` currently admits it cannot measure.
        """
        if not isinstance(project_id, int) or isinstance(project_id, bool):
            raise QuantConnectError(f"project_id must be an int, got {project_id!r}")
        return self.request("backtests/list", {"projectId": project_id})
