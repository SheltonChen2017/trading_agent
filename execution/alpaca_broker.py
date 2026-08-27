"""
Alpaca execution layer — the only module in this repo that talks to a
real (paper or live) brokerage account.

Dormant by design: every function that needs a connection calls
_get_client(), which raises AlpacaNotConfigured until you set
APCA_API_KEY_ID / APCA_API_SECRET_KEY as environment variables. Nothing
here imports alpaca-py at module load time, so the rest of the agent
(scanner, backtest, ML, risk) runs fine without the package installed or
any credentials present.

Get free paper trading keys at https://alpaca.markets — no account
funding required. NEVER hardcode keys in this file or anywhere in the
repo; use environment variables (or a local, gitignored .env you load
yourself).

config.PAPER_TRADING selects the endpoint (paper vs live). As an extra
safety net, submit_market_order() refuses to send a LIVE order unless the
CONFIRM_LIVE_TRADING environment variable is explicitly set to
"I_UNDERSTAND" — flipping PAPER_TRADING to False alone is not enough,
on purpose.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import re
import urllib.request
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import (
    Context,
    Decimal,
    DecimalException,
    Inexact,
    InvalidOperation,
    Rounded,
    localcontext,
)
from threading import Event, Lock, Thread
from typing import Any, Callable
from uuid import UUID

from config import PAPER_TRADING
from risk.execution_gate import (
    ExecutionAuthorization,
    TradeIntent,
    canonical_order_quantity,
    is_fractional_order_quantity,
    is_valid_order_quantity,
    verify_execution_authorization,
)


def _require_valid_shares(
    shares: object, *, whole_shares_only: bool = True
) -> int | str:
    """Defense in depth (GPT review, 2026-07-29): this module is the last
    line of defense before a real broker call, and must not rely solely
    on validate_trade_intent() having already run correctly -- a plain
    `shares <= 0` check does not reject NaN (every ordered comparison
    against NaN is False in Python), so a NaN share count previously
    reached client.submit_order() with zero protection here."""
    quantity = canonical_order_quantity(
        shares, whole_shares_only=whole_shares_only
    )
    if quantity is None:
        requirement = (
            "a positive whole number (int)"
            if whole_shares_only
            else "a positive exact quantity with at most 9 decimal places"
        )
        raise ValueError(
            f"shares must be {requirement}, got {shares!r} "
            f"({type(shares).__name__})."
        )
    return quantity


def _require_expected_policy_fingerprint(value: object) -> str:
    """Validate the policy binding before any account, asset, or order call."""
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(
            "expected_policy_fingerprint must be a lowercase 64-character "
            "sha256 digest"
        )
    return value


class AlpacaNotConfigured(RuntimeError):
    """Raised when Alpaca API credentials are not set in the environment."""


class LiveTradingNotConfirmed(RuntimeError):
    """Raised when live (non-paper) trading is attempted without the explicit confirmation env var."""


class BrokerPreflightError(RuntimeError):
    """Raised when the account or requested asset is not execution-ready."""


def is_configured() -> bool:
    return bool(os.environ.get("APCA_API_KEY_ID")) and bool(os.environ.get("APCA_API_SECRET_KEY"))


def _capture_connection_settings() -> tuple[str, str, bool]:
    """Capture one immutable broker connection boundary.

    Execution code must not assemble a portfolio from one set of environment
    credentials and submit through another.  The module-level compatibility
    facade intentionally opens a fresh client per call, while
    :class:`AlpacaBrokerSession` calls this helper exactly once and retains the
    resulting client, credentials, and paper/live mode for its whole lifetime.
    """
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set. Sign up for free "
            "paper trading keys at https://alpaca.markets, then set both as "
            "environment variables before calling any execution function."
        )
    paper = PAPER_TRADING
    if type(paper) is not bool:
        raise BrokerPreflightError(
            "config.PAPER_TRADING must be an actual bool before opening a broker session."
        )
    return (
        key,
        secret,
        paper,
    )


def _new_trading_client(key: str, secret: str, *, paper: bool):
    from alpaca.trading.client import TradingClient  # lazy import — package optional until used

    return TradingClient(key, secret, paper=paper)


def _new_stock_data_client(key: str, secret: str):
    from alpaca.data.historical import StockHistoricalDataClient

    return StockHistoricalDataClient(key, secret)


_TRADING_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
_TRADING_LIVE_BASE_URL = "https://api.alpaca.markets"
_MARKET_DATA_BASE_URL = "https://data.alpaca.markets"


def _assert_sdk_client_identity(
    client: Any,
    *,
    key: str,
    secret: str,
    expected_sandbox: bool,
    expected_base_url: str,
    label: str,
) -> None:
    """Prove the SDK object still carries the captured connection tuple."""
    try:
        observed_key = object.__getattribute__(client, "_api_key")
        observed_secret = object.__getattribute__(client, "_secret_key")
        observed_sandbox = object.__getattribute__(client, "_sandbox")
        observed_base_url = object.__getattribute__(client, "_base_url")
        observed_oauth_token = object.__getattribute__(client, "_oauth_token")
        observed_basic_auth = object.__getattribute__(client, "_use_basic_auth")
    except (AttributeError, TypeError) as exc:
        raise BrokerPreflightError(
            f"{label} does not expose verifiable SDK connection identity."
        ) from exc
    if (
        not isinstance(observed_key, str)
        or not isinstance(observed_secret, str)
        or observed_key != key
        or observed_secret != secret
        or type(observed_sandbox) is not bool
        or observed_sandbox is not expected_sandbox
        or observed_base_url != expected_base_url
        or observed_oauth_token is not None
        or observed_basic_auth is not False
    ):
        raise BrokerPreflightError(
            f"{label} credential, endpoint, or authentication identity changed "
            "after session open."
        )


def _get_client():
    key, secret, paper = _capture_connection_settings()
    return _new_trading_client(key, secret, paper=paper)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _optional_decimal_text(value: Any) -> str | None:
    """Preserve only source values whose original decimal digits are exact.

    ``Decimal(str(binary_float))`` is a readable canonical rendering of an
    already-rounded float, not provider-exact evidence.  Strict execution
    paths therefore see float-origin values as unavailable and must re-fetch
    an authoritative string-valued REST record.
    """
    if value is None or isinstance(value, (bool, float)):
        return None
    if not isinstance(value, (str, int, Decimal)):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return format(parsed, "f") if parsed.is_finite() else None


class QuoteUnavailable(RuntimeError):
    """The broker returned a quote this code refuses to price against."""


def _required_decimal(value: Any, name: str) -> Decimal:
    """A finite Decimal, or refuse (FCS-005).

    The guarded counterpart to ``_optional_decimal_text`` for values that have
    no meaningful "absent" answer -- a quote with no usable bid cannot be
    priced at all, so returning None would only move the failure somewhere
    less obvious.

    Deliberately local rather than importing ``assistant.money.to_decimal``:
    ``execution/`` has no ``assistant`` imports at all today, and this package
    is the one ``assistant`` defers an import INTO. Same pattern as the three
    other guarded conversion helpers in this repository, and allowlisted for
    that reason in ``tests/test_decimal_conversion_guard.py``.
    """
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuoteUnavailable(f"{name} is not a number: {value!r}") from exc
    if not parsed.is_finite():
        raise QuoteUnavailable(f"{name} is not finite: {value!r}")
    return parsed


def _exact_quote_price(bid: Decimal, ask: Decimal) -> Decimal:
    """Return the one-sided price or exact midpoint under a fixed context."""
    if bid > 0 and ask > 0:
        try:
            with localcontext(Context(prec=64)) as context:
                context.traps[Inexact] = True
                context.traps[Rounded] = True
                return (bid + ask) / Decimal("2")
        except DecimalException as exc:
            raise QuoteUnavailable(
                "quote midpoint exceeds the exact supported decimal precision"
            ) from exc
    return ask if ask > 0 else bid


def _optional_iso(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat() if callable(isoformat) else value)


def _canonical_broker_order_id(value: object) -> str | None:
    """Preserve only provider order identities safe for broker reuse."""
    if isinstance(value, UUID):
        return str(value)
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or value.lower() in {"none", "null", "unknown"}
        or len(value) > 128
        or not value.isascii()
        or not value.isprintable()
    ):
        return None
    return value


def _normalize_order(order: Any) -> dict:
    """Convert every broker order source into one lifecycle-complete shape."""
    def field(name: str, default=None):
        return order.get(name, default) if isinstance(order, Mapping) else getattr(order, name, default)

    order_id = _canonical_broker_order_id(field("id"))
    return {
        # Missing external identity must remain visibly missing.  ``str(None)``
        # manufactured the non-empty-looking order id "None", which could be
        # journaled as if the broker had supplied usable acceptance evidence.
        "order_id": order_id,
        "client_order_id": field("client_order_id"),
        "ticker": field("symbol"),
        "asset_class": (
            str(_enum_value(field("asset_class")))
            if field("asset_class") is not None
            else None
        ),
        "order_class": (
            str(_enum_value(field("order_class")))
            if field("order_class") is not None
            else None
        ),
        "extended_hours": field("extended_hours"),
        "legs": field("legs"),
        "shares": _optional_float(field("qty")),
        "shares_decimal": _optional_decimal_text(field("qty")),
        "side": str(_enum_value(field("side", "unknown"))),
        "type": str(_enum_value(field("type", "unknown"))),
        "limit_price": _optional_float(field("limit_price")),
        "limit_price_decimal": _optional_decimal_text(field("limit_price")),
        "notional": _optional_float(field("notional")),
        "notional_decimal": _optional_decimal_text(field("notional")),
        "time_in_force": (
            str(_enum_value(field("time_in_force")))
            if field("time_in_force") is not None
            else None
        ),
        "status": str(_enum_value(field("status", "unknown"))),
        # Replacement-chain identity. Alpaca exposes these on the order schema
        # and in trade-update events; dropping them meant a replacement order
        # could not be traced back to the proposal it superseded, so the
        # replacement could fill while the proposal sat cancel-pending forever
        # (GPT review, 2026-07-29). `replaces` is what
        # order_reconciler._proposal_for_update() follows.
        "replaced_by": _canonical_broker_order_id(field("replaced_by")),
        "replaces": _canonical_broker_order_id(field("replaces")),
        "replaced_at": _optional_iso(field("replaced_at")),
        "filled_qty": _optional_float(field("filled_qty")),
        "filled_qty_decimal": _optional_decimal_text(field("filled_qty")),
        "filled_avg_price": _optional_float(field("filled_avg_price")),
        "filled_avg_price_decimal": _optional_decimal_text(
            field("filled_avg_price")
        ),
        "submitted_at": _optional_iso(field("submitted_at")),
        "updated_at": _optional_iso(field("updated_at")),
        "filled_at": _optional_iso(field("filled_at")),
        "canceled_at": _optional_iso(field("canceled_at")),
        "expired_at": _optional_iso(field("expired_at")),
        "failed_at": _optional_iso(field("failed_at")),
    }


def _normalized_trade_update_numbers(
    *, fill_qty: Any, fill_price: Any
) -> dict[str, float | str | None]:
    """Normalize incremental stream fills without losing decimal evidence."""
    if fill_qty is None and fill_price is None:
        return {
            "fill_qty": None,
            "fill_qty_decimal": None,
            "fill_price": None,
            "fill_price_decimal": None,
        }
    if (fill_qty is None) != (fill_price is None):
        raise BrokerPreflightError(
            "Broker trade update must provide fill quantity and price together."
        )
    quantity = _optional_float(fill_qty)
    price = _optional_float(fill_price)
    if quantity is None or price is None or quantity <= 0 or price <= 0:
        raise BrokerPreflightError(
            "Broker trade update returned a non-positive or non-finite fill."
        )
    return {
        "fill_qty": quantity,
        "fill_qty_decimal": _optional_decimal_text(fill_qty),
        "fill_price": price,
        "fill_price_decimal": _optional_decimal_text(fill_price),
    }


def _normalize_account(account: Any, *, paper: bool) -> dict:
    account_id = getattr(account, "id", None)
    def broker_bool(field: str) -> bool | None:
        # Missing provider evidence is unknown, never an implicit safe False.
        value = getattr(account, field, None)
        return value if type(value) is bool else None

    return {
        "account_id": str(account_id) if account_id is not None else None,
        "status": str(_enum_value(getattr(account, "status", "unknown"))),
        "equity": float(account.equity),
        "equity_decimal": _optional_decimal_text(account.equity),
        "cash": float(account.cash),
        "cash_decimal": _optional_decimal_text(account.cash),
        "buying_power": float(account.buying_power),
        "buying_power_decimal": _optional_decimal_text(account.buying_power),
        "trading_blocked": broker_bool("trading_blocked"),
        "account_blocked": broker_bool("account_blocked"),
        "trade_suspended_by_user": broker_bool("trade_suspended_by_user"),
        "transfers_blocked": broker_bool("transfers_blocked"),
        "paper": paper,
    }


def _normalize_asset(asset: Any) -> dict:
    def broker_bool(field: str) -> bool | None:
        value = getattr(asset, field, None)
        return value if type(value) is bool else None

    symbol = getattr(asset, "symbol", None)
    return {
        "ticker": str(symbol).strip().upper() if symbol is not None else None,
        "status": str(_enum_value(getattr(asset, "status", "unknown"))),
        "asset_class": str(
            _enum_value(getattr(asset, "asset_class", "unknown"))
        ),
        "tradable": broker_bool("tradable"),
        "fractionable": broker_bool("fractionable"),
    }


def _usable_account_id(value: object) -> str:
    if not isinstance(value, str):
        raise BrokerPreflightError(
            "Broker account did not return a usable account identity."
        )
    account_id = value.strip()
    if value != account_id:
        raise BrokerPreflightError(
            "Broker account identity contains surrounding whitespace."
        )
    if account_id.lower() in {"", "none", "null", "unknown"}:
        raise BrokerPreflightError(
            "Broker account did not return a usable account identity."
        )
    return account_id


def _assert_asset_evidence(asset: Mapping[str, Any], ticker: str) -> None:
    expected_ticker = ticker.strip().upper()
    if asset.get("ticker") != expected_ticker:
        raise BrokerPreflightError(
            f"Broker returned asset {asset.get('ticker')!r} while {expected_ticker!r} "
            "was requested."
        )
    if asset.get("asset_class") != "us_equity":
        raise BrokerPreflightError(
            f"Broker asset class must be 'us_equity', got "
            f"{asset.get('asset_class')!r}."
        )
    for field in ("tradable", "fractionable"):
        if type(asset.get(field)) is not bool:
            raise BrokerPreflightError(
                f"Broker asset returned malformed {field} evidence."
            )


def _normalize_position(position: Any) -> dict:
    normalized = {
        "ticker": position.symbol,
        "shares": float(position.qty),
        "shares_decimal": _optional_decimal_text(position.qty),
        "avg_entry_price": float(position.avg_entry_price),
        "avg_entry_price_decimal": _optional_decimal_text(
            position.avg_entry_price
        ),
        "current_price": float(position.current_price),
        "current_price_decimal": _optional_decimal_text(position.current_price),
        "unrealized_pl": float(position.unrealized_pl),
    }
    market_value = getattr(position, "market_value", None)
    if market_value is not None:
        normalized["market_value"] = float(market_value)
        normalized["market_value_decimal"] = _optional_decimal_text(market_value)
    return normalized


def _get_raw_open_orders_for_client(client: Any) -> list[Any]:
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    return list(client.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            limit=500,
        )
    ))


def _get_orders_for_client(client: Any) -> list[dict]:
    # Alpaca defaults to only 50 rows.  A safety snapshot must explicitly ask
    # for the largest open book, and exactly-maximal output remains incomplete
    # evidence because this endpoint exposes no unambiguous cursor.
    orders = _get_raw_open_orders_for_client(client)
    if len(orders) >= 500:
        raise BrokerPreflightError(
            "Alpaca returned the 500-order maximum; the open-order book may be "
            "truncated and cannot be certified complete."
        )
    return [_normalize_order(order) for order in orders]


_EXECUTION_QUOTE_FUTURE_SKEW = timedelta(seconds=5)
_BROKER_SESSIONS_GUARD = Lock()
_REGISTERED_BROKER_SESSIONS: weakref.WeakValueDictionary[int, object] = (
    weakref.WeakValueDictionary()
)


@dataclass(frozen=True, slots=True)
class _ExecutionQuoteEvidence:
    ticker: str
    price_decimal: str
    bid_decimal: str
    ask_decimal: str
    timestamp: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class _ExecutionSnapshotRegistration:
    expires_at: datetime
    state_fingerprint: str
    quotes: tuple[_ExecutionQuoteEvidence, ...] = ()


class AlpacaBrokerSession:
    """One account-scoped Alpaca connection used across an execution attempt.

    Credentials and paper/live mode are captured at construction and are never
    read from the mutable process environment again.  All trading account,
    asset, position, order, lookup, cancellation, and SDK submission calls use
    the same ``TradingClient`` instance.  Quote data and exact fractional REST
    submissions necessarily use Alpaca's separate APIs, but they use the same
    frozen credentials and endpoint mode retained by this session.
    """

    __slots__ = (
        "__weakref__",
        "_account_id",
        "_client",
        "_data_base_url",
        "_data_client",
        "_key",
        "_owner_pid",
        "_paper",
        "_secret",
        "_snapshot_guard",
        "_trading_base_url",
        "_registered_execution_snapshots",
    )

    def __init_subclass__(cls, **kwargs) -> None:
        del kwargs
        raise TypeError("AlpacaBrokerSession is a sealed connection capability")

    def __setattr__(self, name: str, value: Any) -> None:
        """Freeze every connection/capability slot after first assignment."""
        if name in AlpacaBrokerSession.__slots__:
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                pass
            else:
                raise AttributeError(f"broker session {name} is immutable")
        object.__setattr__(self, name, value)

    def __init__(self) -> None:
        try:
            object.__getattribute__(self, "_owner_pid")
        except AttributeError:
            pass
        else:
            raise TypeError("AlpacaBrokerSession cannot be reinitialized")
        key, secret, paper = _capture_connection_settings()
        if not isinstance(key, str) or not key:
            raise AlpacaNotConfigured("Alpaca key must be a non-empty string.")
        if not isinstance(secret, str) or not secret:
            raise AlpacaNotConfigured("Alpaca secret must be a non-empty string.")
        if type(paper) is not bool:
            raise BrokerPreflightError("paper must be an actual bool.")
        trading_base_url = (
            "https://paper-api.alpaca.markets"
            if paper
            else "https://api.alpaca.markets"
        )
        data_base_url = "https://data.alpaca.markets"
        client = _new_trading_client(key, secret, paper=paper)
        if client is None:
            raise TypeError("TradingClient construction returned None")
        _assert_sdk_client_identity(
            client,
            key=key,
            secret=secret,
            expected_sandbox=paper,
            expected_base_url=trading_base_url,
            label="TradingClient",
        )
        object.__setattr__(self, "_key", key)
        object.__setattr__(self, "_secret", secret)
        object.__setattr__(self, "_owner_pid", os.getpid())
        object.__setattr__(self, "_paper", paper)
        object.__setattr__(self, "_trading_base_url", trading_base_url)
        object.__setattr__(self, "_data_base_url", data_base_url)
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_data_client", None)
        object.__setattr__(self, "_account_id", None)
        object.__setattr__(self, "_snapshot_guard", Lock())
        object.__setattr__(
            self,
            "_registered_execution_snapshots",
            (),
        )
        with _BROKER_SESSIONS_GUARD:
            prior = _REGISTERED_BROKER_SESSIONS.get(id(self))
            if prior is not None and prior is not self:
                raise RuntimeError("broker session identity collision")
            _REGISTERED_BROKER_SESSIONS[id(self)] = self

    def __copy__(self):
        raise TypeError("AlpacaBrokerSession cannot be copied")

    def __deepcopy__(self, _memo):
        raise TypeError("AlpacaBrokerSession cannot be copied")

    def __reduce__(self):
        raise TypeError("AlpacaBrokerSession cannot be serialized")

    def __reduce_ex__(self, _protocol):
        raise TypeError("AlpacaBrokerSession cannot be serialized")

    def _assert_process_owner(self) -> None:
        """Reject a session inherited by a forked child process.

        The SDK client, private snapshot registry, and cached account identity
        are one process-local capability.  Letting a forked child reuse them
        would clone a nominally single-use snapshot and authorization boundary
        while also inheriting sockets and locks in an undefined state.
        """
        with _BROKER_SESSIONS_GUARD:
            registered = _REGISTERED_BROKER_SESSIONS.get(id(self))
        if registered is not self:
            raise PermissionError(
                "This broker session was not opened by the production constructor."
            )
        if os.getpid() != self._owner_pid:
            raise PermissionError(
                "This broker session belongs to a different process; open a "
                "fresh account-scoped session and capture a new snapshot."
            )
        _assert_sdk_client_identity(
            self._client,
            key=self._key,
            secret=self._secret,
            expected_sandbox=self._paper,
            expected_base_url=self._trading_base_url,
            label="TradingClient",
        )

    @property
    def PAPER_TRADING(self) -> bool:
        """Read-only compatibility view of the captured endpoint mode."""
        self._assert_process_owner()
        return self._paper

    @property
    def account_mode(self) -> str:
        self._assert_process_owner()
        return "paper" if self._paper else "live"

    def is_configured(self) -> bool:
        return True

    def __register_execution_snapshot(
        self,
        snapshot_id: str,
        captured_at: str,
        state_fingerprint: str,
    ) -> None:
        """Register one fresh strict capture as a one-dispatch capability."""
        self._assert_process_owner()
        if not isinstance(snapshot_id, str) or re.fullmatch(
            r"[0-9a-f]{64}", snapshot_id
        ) is None:
            raise ValueError("snapshot_id must be a lowercase SHA-256 digest")
        try:
            captured = datetime.fromisoformat(captured_at)
        except (TypeError, ValueError) as exc:
            raise ValueError("captured_at must be an ISO timestamp") from exc
        if captured.tzinfo is None or captured.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        captured = captured.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if captured > now + timedelta(seconds=5):
            raise ValueError("captured_at is implausibly far in the future")
        expires_at = captured + timedelta(seconds=30)
        if expires_at <= now:
            raise ValueError("execution snapshot is already expired")
        if not isinstance(state_fingerprint, str) or re.fullmatch(
            r"[0-9a-f]{64}", state_fingerprint
        ) is None:
            raise ValueError(
                "state_fingerprint must be a lowercase SHA-256 digest"
            )
        with self._snapshot_guard:
            registrations = self._registered_execution_snapshots
            if any(
                registered_id == snapshot_id
                for registered_id, _registration in registrations
            ):
                raise PermissionError(
                    "Execution snapshot is already registered in this session."
                )
            object.__setattr__(
                self,
                "_registered_execution_snapshots",
                tuple(
                    sorted(
                        (
                            *registrations,
                            (
                                snapshot_id,
                                _ExecutionSnapshotRegistration(
                                    expires_at=expires_at,
                                    state_fingerprint=state_fingerprint,
                                ),
                            ),
                        ),
                        key=lambda item: item[0],
                    )
                ),
            )

    @staticmethod
    def _execution_snapshot_state_fingerprint(snapshot: Any) -> str:
        """Hash every broker-snapshot input that can change dispatch policy.

        Every account and position value used by the execution gate is frozen:
        equity, cash, buying power, position quantities/bases/current prices/
        market values, account authority flags, and the complete active-order
        fingerprint.  A coherent market tick can change concentration or
        exposure after authorization; allowing that drift here would submit a
        trade which no longer satisfies the policy that signed it.
        """
        material_json = snapshot.broker_snapshot_material_json
        if not isinstance(material_json, str) or not material_json:
            raise BrokerPreflightError(
                "Execution snapshot lacks canonical broker material."
            )
        try:
            material = json.loads(
                material_json,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant {value}")
                ),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BrokerPreflightError(
                "Execution snapshot material is not valid strict JSON."
            ) from exc
        if not isinstance(material, dict):
            raise BrokerPreflightError(
                "Execution snapshot material must be a JSON object."
            )
        captured_at = material.get("captured_at")
        if not isinstance(captured_at, str) or not captured_at:
            raise BrokerPreflightError(
                "Execution snapshot material lacks its capture timestamp."
            )
        account = material.get("account")
        positions = material.get("positions")
        active_order_fingerprint = material.get("active_order_fingerprint")
        if not isinstance(account, dict) or not isinstance(positions, list):
            raise BrokerPreflightError(
                "Execution snapshot material lacks account or position state."
            )
        account_fields = (
            "account_id",
            "account_mode",
            "status",
            "equity",
            "cash",
            "buying_power",
            "trading_blocked",
            "account_blocked",
            "trade_suspended_by_user",
            "transfers_blocked",
        )
        position_fields = (
            "ticker",
            "shares",
            "entry_price",
            "current_price",
            "market_value",
        )
        try:
            stable_positions = [
                {field: row[field] for field in position_fields}
                for row in positions
            ]
            state = {
                "schema": material["schema"],
                "account": {field: account[field] for field in account_fields},
                "positions": stable_positions,
                "active_order_fingerprint": active_order_fingerprint,
            }
        except (KeyError, TypeError) as exc:
            raise BrokerPreflightError(
                "Execution snapshot material lacks dispatch-relevant state."
            ) from exc
        canonical = json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def capture_execution_portfolio_snapshot(self):
        """Capture and privately register one coherent execution snapshot.

        Callers cannot register an asserted digest.  The only public route to
        a session-recognized snapshot performs the broker reads and strict
        canonical verification first, then records the returned ID inside this
        session.
        """
        from assistant.portfolio_snapshot import (
            build_portfolio_snapshot_from_alpaca,
            verify_execution_portfolio_snapshot,
        )

        self._assert_process_owner()
        snapshot = build_portfolio_snapshot_from_alpaca(
            broker_session=self,
            require_execution_coherence=True,
        )
        verify_execution_portfolio_snapshot(snapshot)
        assert snapshot.broker_snapshot_id is not None
        assert snapshot.captured_at is not None
        self.__register_execution_snapshot(
            snapshot.broker_snapshot_id,
            snapshot.captured_at,
            self._execution_snapshot_state_fingerprint(snapshot),
        )
        return snapshot

    def _assert_execution_snapshot_unchanged(self, snapshot_id: str) -> None:
        """Recapture broker state and compare it immediately before contact."""
        from assistant.portfolio_snapshot import (
            build_portfolio_snapshot_from_alpaca,
            verify_execution_portfolio_snapshot,
        )

        self._assert_process_owner()
        with self._snapshot_guard:
            registration = next(
                (
                    item
                    for registered_id, item
                    in self._registered_execution_snapshots
                    if registered_id == snapshot_id
                ),
                None,
            )
        if registration is None:
            raise PermissionError(
                "Execution snapshot was not captured by this broker session."
            )
        if registration.expires_at <= datetime.now(timezone.utc):
            with self._snapshot_guard:
                object.__setattr__(
                    self,
                    "_registered_execution_snapshots",
                    tuple(
                        item
                        for item in self._registered_execution_snapshots
                        if item[0] != snapshot_id
                    ),
                )
            raise PermissionError("Execution snapshot has expired.")

        current = build_portfolio_snapshot_from_alpaca(
            broker_session=self,
            require_execution_coherence=True,
            expected_account_id=self._account_id,
        )
        verify_execution_portfolio_snapshot(current)
        current_state_fingerprint = self._execution_snapshot_state_fingerprint(
            current
        )
        if current_state_fingerprint != registration.state_fingerprint:
            raise BrokerPreflightError(
                "Broker account, positions, balances, or active orders changed "
                "after authorization evidence was captured; revalidate the "
                "trade against a fresh snapshot."
            )

    def _assert_registered_execution_snapshot(self, snapshot_id: str | None) -> None:
        self._assert_process_owner()
        if not isinstance(snapshot_id, str):
            raise PermissionError(
                "Broker submission requires an execution snapshot registered "
                "by this exact account-scoped session."
            )
        now = datetime.now(timezone.utc)
        with self._snapshot_guard:
            registration = next(
                (
                    item
                    for registered_id, item
                    in self._registered_execution_snapshots
                    if registered_id == snapshot_id
                ),
                None,
            )
            if registration is None:
                raise PermissionError(
                    "Execution snapshot was not captured by this broker session."
                )
            if registration.expires_at <= now:
                object.__setattr__(
                    self,
                    "_registered_execution_snapshots",
                    tuple(
                        item
                        for item in self._registered_execution_snapshots
                        if item[0] != snapshot_id
                    ),
                )
                raise PermissionError("Execution snapshot has expired.")

    def _consume_registered_execution_snapshot(self, snapshot_id: str) -> None:
        self._assert_process_owner()
        with self._snapshot_guard:
            registration = next(
                (
                    item
                    for registered_id, item
                    in self._registered_execution_snapshots
                    if registered_id == snapshot_id
                ),
                None,
            )
            object.__setattr__(
                self,
                "_registered_execution_snapshots",
                tuple(
                    item
                    for item in self._registered_execution_snapshots
                    if item[0] != snapshot_id
                ),
            )
        if (
            registration is None
            or registration.expires_at <= datetime.now(timezone.utc)
        ):
            raise PermissionError(
                "Execution snapshot was expired or already consumed."
            )

    def get_account(self) -> dict:
        self._assert_process_owner()
        account = _normalize_account(
            self._client.get_account(), paper=self._paper
        )
        observed_id = _usable_account_id(account["account_id"])
        if self._account_id is None:
            object.__setattr__(self, "_account_id", observed_id)
        elif observed_id != self._account_id:
            raise BrokerPreflightError(
                "Broker account identity changed inside one account-scoped session."
            )
        account["account_id"] = observed_id
        return account

    def get_asset(self, ticker: str) -> dict:
        self._assert_process_owner()
        return _normalize_asset(self._client.get_asset(ticker.upper()))

    def assert_account_and_asset_ready(self, ticker: str) -> dict:
        account = self.get_account()
        for field in (
            "trading_blocked",
            "account_blocked",
            "trade_suspended_by_user",
        ):
            if type(account[field]) is not bool:
                raise BrokerPreflightError(
                    f"Broker account returned malformed {field} evidence."
                )
        blocked = [
            field
            for field in (
                "trading_blocked",
                "account_blocked",
                "trade_suspended_by_user",
            )
            if account[field]
        ]
        if blocked:
            raise BrokerPreflightError(
                "Broker account is not trading-ready: " + ", ".join(blocked) + "."
            )
        if str(account["status"]).upper() != "ACTIVE":
            raise BrokerPreflightError(
                f"Broker account status is {account['status']!r}, not ACTIVE."
            )
        if not self._paper:
            expected_account_id = os.environ.get(
                "TRADING_ASSISTANT_LIVE_ACCOUNT_ID"
            )
            if not expected_account_id:
                raise LiveTradingNotConfirmed(
                    "Live account execution also requires "
                    "TRADING_ASSISTANT_LIVE_ACCOUNT_ID to be set to the exact "
                    "intended Alpaca account ID."
                )
            if expected_account_id != account["account_id"]:
                raise LiveTradingNotConfirmed(
                    "TRADING_ASSISTANT_LIVE_ACCOUNT_ID does not match the "
                    "connected Alpaca account."
                )
        asset = self.get_asset(ticker)
        _assert_asset_evidence(asset, ticker)
        if asset["status"].lower() != "active" or not asset["tradable"]:
            raise BrokerPreflightError(
                f"{asset['ticker']} is not broker-tradable "
                f"(status={asset['status']!r}, tradable={asset['tradable']})."
            )
        return {"account": account, "asset": asset}

    def get_open_positions(self) -> list[dict]:
        self._assert_process_owner()
        return [
            _normalize_position(position)
            for position in self._client.get_all_positions()
        ]

    def get_open_orders(self) -> list[dict]:
        self._assert_process_owner()
        return _get_orders_for_client(self._client)

    def get_open_order_ids_for_emergency(self) -> dict[str, Any]:
        """Best-effort ID isolation for emergency cancellation only.

        Normal portfolio/risk reads remain atomic and strict.  This narrower
        surface exists solely so one malformed sibling cannot hide otherwise
        usable order IDs after bulk cancellation has failed.  ``complete`` is
        false whenever any row or endpoint-capacity condition is ambiguous.
        """
        self._assert_process_owner()
        rows = _get_raw_open_orders_for_client(self._client)
        complete = len(rows) < 500
        errors: list[dict[str, Any]] = []
        if not complete:
            errors.append(
                {
                    "row_index": None,
                    "order_id": None,
                    "error": (
                        "Alpaca returned the 500-order maximum; emergency "
                        "open-order enumeration may be truncated."
                    ),
                }
            )
        order_ids: list[str] = []
        seen: set[str] = set()
        for index, row in enumerate(rows):
            try:
                if isinstance(row, Mapping):
                    if "id" in row:
                        value = row["id"]
                    elif "order_id" in row:
                        value = row["order_id"]
                    else:
                        value = None
                else:
                    value = getattr(row, "id", None)
            except Exception as exc:
                complete = False
                errors.append(
                    {
                        "row_index": index,
                        "order_id": None,
                        "error": (
                            "broker open-order row ID could not be read: "
                            f"{type(exc).__name__}"
                        ),
                    }
                )
                continue
            order_id = _canonical_broker_order_id(value)
            if order_id is None:
                complete = False
                errors.append(
                    {
                        "row_index": index,
                        "order_id": None,
                        "error": "broker open-order row has no canonical usable ID",
                    }
                )
                continue
            if order_id in seen:
                complete = False
                errors.append(
                    {
                        "row_index": index,
                        "order_id": order_id,
                        "error": "broker open-order response repeated an order ID",
                    }
                )
                continue
            seen.add(order_id)
            order_ids.append(order_id)
        order_ids.sort()
        return {
            "order_ids": order_ids,
            "complete": complete,
            "errors": errors,
        }

    def find_order_by_client_id(self, client_order_id: str) -> dict | None:
        self._assert_process_owner()
        try:
            order = self._client.get_order_by_client_id(client_order_id)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise
        return None if order is None else _normalize_order(order)

    def get_order_by_id(self, order_id: str) -> dict | None:
        self._assert_process_owner()
        try:
            order = self._client.get_order_by_id(order_id)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise
        return None if order is None else _normalize_order(order)

    def cancel_order(self, order_id: str) -> dict:
        self._assert_process_owner()
        self._client.cancel_order_by_id(order_id)
        return {"order_id": str(order_id), "status": "pending_cancel"}

    def cancel_all_orders(self):
        """Use Alpaca's account-wide bulk cancellation as emergency coverage."""
        self._assert_process_owner()
        return self._client.cancel_orders()

    @staticmethod
    def _canonical_quote_ticker(ticker: object) -> str:
        if not isinstance(ticker, str) or ticker != ticker.strip():
            raise QuoteUnavailable("quote ticker must be a canonical string")
        canonical = ticker.upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,31}", canonical) is None:
            raise QuoteUnavailable(f"quote ticker is malformed: {ticker!r}")
        return canonical

    def _fetch_latest_quote(self, ticker: str) -> dict:
        self._assert_process_owner()
        from alpaca.data.requests import StockLatestQuoteRequest

        ticker = self._canonical_quote_ticker(ticker)
        if self._data_client is None:
            data_client = _new_stock_data_client(self._key, self._secret)
            _assert_sdk_client_identity(
                data_client,
                key=self._key,
                secret=self._secret,
                expected_sandbox=False,
                expected_base_url=self._data_base_url,
                label="StockHistoricalDataClient",
            )
            object.__setattr__(self, "_data_client", data_client)
        assert self._data_client is not None
        _assert_sdk_client_identity(
            self._data_client,
            key=self._key,
            secret=self._secret,
            expected_sandbox=False,
            expected_base_url=self._data_base_url,
            label="StockHistoricalDataClient",
        )
        quotes = self._data_client.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=[ticker])
        )
        if not isinstance(quotes, Mapping) or ticker not in quotes:
            raise QuoteUnavailable(f"broker returned no quote for {ticker}")
        return _normalize_latest_quote(ticker, quotes[ticker])

    @staticmethod
    def _execution_quote_evidence(
        quote: Mapping[str, Any],
        *,
        expected_ticker: str,
        snapshot_expires_at: datetime,
    ) -> _ExecutionQuoteEvidence:
        if quote.get("ticker") != expected_ticker:
            raise QuoteUnavailable("quote ticker does not match the requested security")
        decimals: dict[str, Decimal] = {}
        for field in ("price_decimal", "bid_decimal", "ask_decimal"):
            value = quote.get(field)
            if not isinstance(value, str) or not value or value != value.strip():
                raise QuoteUnavailable(f"quote {field} is missing or non-canonical")
            try:
                parsed = Decimal(value)
            except (InvalidOperation, ValueError) as exc:
                raise QuoteUnavailable(f"quote {field} is malformed") from exc
            if not parsed.is_finite() or format(parsed, "f") != value:
                raise QuoteUnavailable(f"quote {field} is not canonical finite decimal text")
            decimals[field] = parsed
        bid = decimals["bid_decimal"]
        ask = decimals["ask_decimal"]
        price = decimals["price_decimal"]
        if bid < 0 or ask < 0 or price <= 0 or (bid == 0 and ask == 0):
            raise QuoteUnavailable("quote prices must be finite and usable")
        expected_price = _exact_quote_price(bid, ask)
        if price != expected_price:
            raise QuoteUnavailable("quote mid price is inconsistent with bid/ask")
        timestamp = quote.get("timestamp")
        if not isinstance(timestamp, datetime):
            raise QuoteUnavailable("quote timestamp must be a datetime")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise QuoteUnavailable("quote timestamp must be timezone-aware")
        timestamp_utc = timestamp.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if timestamp_utc > now + _EXECUTION_QUOTE_FUTURE_SKEW:
            raise QuoteUnavailable("quote timestamp is implausibly in the future")
        # Price staleness remains policy-owned and is evaluated by the risk
        # gate against this exact timestamp.  The capability itself expires
        # with the much shorter session snapshot boundary.
        expires_at = snapshot_expires_at
        if expires_at <= now:
            raise QuoteUnavailable("execution quote is already expired")
        return _ExecutionQuoteEvidence(
            ticker=expected_ticker,
            price_decimal=format(price, "f"),
            bid_decimal=format(bid, "f"),
            ask_decimal=format(ask, "f"),
            timestamp=timestamp_utc.isoformat(),
            expires_at=expires_at,
        )

    def get_execution_validation_quote(
        self,
        ticker: str,
        *,
        expected_snapshot_id: str,
    ) -> dict:
        """Fetch and set-once bind the quote used by execution validation."""
        self._assert_registered_execution_snapshot(expected_snapshot_id)
        ticker = self._canonical_quote_ticker(ticker)
        with self._snapshot_guard:
            registration = next(
                (
                    item
                    for registered_id, item
                    in self._registered_execution_snapshots
                    if registered_id == expected_snapshot_id
                ),
                None,
            )
            if registration is None:
                raise PermissionError("Execution snapshot is not registered.")
            existing = next(
                (item for item in registration.quotes if item.ticker == ticker),
                None,
            )
        if existing is not None:
            if existing.expires_at <= datetime.now(timezone.utc):
                raise PermissionError("Execution validation quote has expired.")
            return {
                "ticker": existing.ticker,
                "price": float(Decimal(existing.price_decimal)),
                "price_decimal": existing.price_decimal,
                "bid": float(Decimal(existing.bid_decimal)),
                "bid_decimal": existing.bid_decimal,
                "ask": float(Decimal(existing.ask_decimal)),
                "ask_decimal": existing.ask_decimal,
                "timestamp": datetime.fromisoformat(existing.timestamp),
            }
        quote = self._fetch_latest_quote(ticker)
        evidence = self._execution_quote_evidence(
            quote,
            expected_ticker=ticker,
            snapshot_expires_at=registration.expires_at,
        )
        with self._snapshot_guard:
            current = next(
                (
                    item
                    for registered_id, item
                    in self._registered_execution_snapshots
                    if registered_id == expected_snapshot_id
                ),
                None,
            )
            if current is not registration:
                raise PermissionError("Execution snapshot registration changed.")
            current_existing = next(
                (item for item in current.quotes if item.ticker == ticker),
                None,
            )
            if current_existing is None:
                replacement = _ExecutionSnapshotRegistration(
                    expires_at=current.expires_at,
                    state_fingerprint=current.state_fingerprint,
                    quotes=tuple(
                        sorted(
                            (*current.quotes, evidence),
                            key=lambda item: item.ticker,
                        )
                    ),
                )
                object.__setattr__(
                    self,
                    "_registered_execution_snapshots",
                    tuple(
                        (
                            registered_id,
                            replacement
                            if registered_id == expected_snapshot_id
                            else item,
                        )
                        for registered_id, item
                        in self._registered_execution_snapshots
                    ),
                )
            elif current_existing != evidence:
                raise BrokerPreflightError(
                    "Execution quote changed after validation began; capture a "
                    "fresh snapshot and revalidate."
                )
        return quote

    def _assert_all_execution_quotes_unchanged(
        self,
        snapshot_id: str,
        required_ticker: str,
    ) -> None:
        """Re-fetch every policy-driving quote immediately before authority use."""
        self._assert_registered_execution_snapshot(snapshot_id)
        required_ticker = self._canonical_quote_ticker(required_ticker)
        with self._snapshot_guard:
            registration = next(
                (
                    item
                    for registered_id, item
                    in self._registered_execution_snapshots
                    if registered_id == snapshot_id
                ),
                None,
            )
        if registration is None or not registration.quotes:
            raise PermissionError(
                "Execution snapshot has no session-bound validation quote."
            )
        if required_ticker not in {item.ticker for item in registration.quotes}:
            raise PermissionError("Execution quote belongs to a different ticker.")
        for expected in registration.quotes:
            if expected.expires_at <= datetime.now(timezone.utc):
                raise PermissionError("Execution validation quote has expired.")
            current_quote = self._fetch_latest_quote(expected.ticker)
            current_evidence = self._execution_quote_evidence(
                current_quote,
                expected_ticker=expected.ticker,
                snapshot_expires_at=registration.expires_at,
            )
            if current_evidence != expected:
                raise BrokerPreflightError(
                    f"Execution quote for {expected.ticker} changed after "
                    "validation; capture a fresh snapshot and revalidate "
                    "before submission."
                )

    def _assert_execution_quote_unchanged(
        self,
        snapshot_id: str,
        ticker: str,
    ) -> None:
        """Compatibility alias for the now all-quote final recapture."""
        self._assert_all_execution_quotes_unchanged(snapshot_id, ticker)

    def get_latest_quote(self, ticker: str) -> dict:
        """Read an ordinary quote without altering execution quote authority."""
        return self._fetch_latest_quote(ticker)

    def run_trade_update_stream(
        self,
        callback: Callable[[dict], Any],
        stop_event: Event | None = None,
    ) -> None:
        """Consume updates with this session's frozen credentials and mode."""
        self._assert_process_owner()
        _run_trade_update_stream_with_credentials(
            callback,
            key=self._key,
            secret=self._secret,
            paper=self._paper,
            stop_event=stop_event,
        )

    def submit_market_order(
        self,
        ticker: str,
        shares: int | str,
        side: str = "buy",
        *,
        authorization: ExecutionAuthorization | None = None,
        idempotency_key: str,
        dispatch_permit: object | None = None,
        whole_shares_only: bool = True,
        expected_snapshot_id: str | None = None,
        expected_policy_fingerprint: str,
    ) -> dict:
        self._assert_process_owner()
        expected_policy_fingerprint = _require_expected_policy_fingerprint(
            expected_policy_fingerprint
        )
        if not idempotency_key:
            raise ValueError("idempotency_key is required and must be non-empty")
        if (
            not self._paper
            and os.environ.get("CONFIRM_LIVE_TRADING") != "I_UNDERSTAND"
        ):
            raise LiveTradingNotConfirmed(
                "The captured broker session is live but live trading was not confirmed."
            )
        quantity = _require_valid_shares(
            shares, whole_shares_only=whole_shares_only
        )
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        intent = TradeIntent(
            ticker=ticker,
            shares=quantity,
            side=side,
            order_type="market",
        )
        if authorization is None:
            # Missing authority is independently knowable and should not even
            # trigger a broker read.  A present token is checked only after the
            # session account is observed, so an account mismatch cannot
            # consume it.
            verify_execution_authorization(intent, authorization, require_bound=True)
        self._assert_registered_execution_snapshot(expected_snapshot_id)
        assert expected_snapshot_id is not None
        from assistant.dispatch_fence import (
            consume_execution_dispatch_permit,
            execution_dispatch_permit_fence,
        )

        with execution_dispatch_permit_fence(
            dispatch_permit,
            broker_session=self,
            idempotency_key=idempotency_key,
            expected_snapshot_id=expected_snapshot_id,
            expected_policy_fingerprint=expected_policy_fingerprint,
            expected_account_mode=self.account_mode,
        ):
            readiness = self.assert_account_and_asset_ready(ticker)
            if (
                is_fractional_order_quantity(quantity)
                and not readiness["asset"]["fractionable"]
            ):
                raise BrokerPreflightError(
                    f"{ticker.upper()} is not marked fractionable by the broker."
                )
            self._assert_execution_snapshot_unchanged(expected_snapshot_id)
            self._assert_execution_quote_unchanged(expected_snapshot_id, ticker)
            verify_execution_authorization(
                intent,
                authorization,
                expected_account_id=readiness["account"]["account_id"],
                expected_account_mode=self.account_mode,
                expected_snapshot_id=expected_snapshot_id,
                expected_policy_fingerprint=expected_policy_fingerprint,
                require_bound=True,
            )
            consume_execution_dispatch_permit(
                dispatch_permit,
                broker_session=self,
                idempotency_key=idempotency_key,
                expected_account_id=readiness["account"]["account_id"],
                expected_account_mode=self.account_mode,
                expected_snapshot_id=expected_snapshot_id,
                expected_policy_fingerprint=expected_policy_fingerprint,
            )
            self._consume_registered_execution_snapshot(expected_snapshot_id)
            self._assert_process_owner()
            if is_fractional_order_quantity(quantity):
                payload = {
                    "symbol": ticker,
                    "qty": str(quantity),
                    "side": side,
                    "type": "market",
                    "time_in_force": "day",
                    "client_order_id": idempotency_key,
                }
                request = urllib.request.Request(
                    f"{self._trading_base_url}/v2/orders",
                    data=json.dumps(
                        payload, separators=(",", ":")
                    ).encode("utf-8"),
                    headers={
                        "APCA-API-KEY-ID": self._key,
                        "APCA-API-SECRET-KEY": self._secret,
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    response_payload = json.loads(response.read())
                if not isinstance(response_payload, Mapping):
                    raise RuntimeError(
                        "unexpected order response shape: "
                        f"{type(response_payload).__name__}"
                    )
                return _normalize_order(response_payload)
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest

            order = self._client.submit_order(
                MarketOrderRequest(
                    symbol=ticker,
                    qty=quantity,
                    side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    client_order_id=idempotency_key,
                )
            )
            return _normalize_order(order)

    def submit_limit_order(
        self,
        ticker: str,
        shares: int | str,
        limit_price: float,
        side: str = "buy",
        *,
        authorization: ExecutionAuthorization | None = None,
        idempotency_key: str,
        dispatch_permit: object | None = None,
        whole_shares_only: bool = True,
        expected_snapshot_id: str | None = None,
        expected_policy_fingerprint: str,
    ) -> dict:
        self._assert_process_owner()
        expected_policy_fingerprint = _require_expected_policy_fingerprint(
            expected_policy_fingerprint
        )
        if not idempotency_key:
            raise ValueError("idempotency_key is required and must be non-empty")
        if (
            not self._paper
            and os.environ.get("CONFIRM_LIVE_TRADING") != "I_UNDERSTAND"
        ):
            raise LiveTradingNotConfirmed(
                "The captured broker session is live but live trading was not confirmed."
            )
        quantity = _require_valid_shares(
            shares, whole_shares_only=whole_shares_only
        )
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        intent = TradeIntent(
            ticker=ticker,
            shares=quantity,
            side=side,
            order_type="limit",
            limit_price=limit_price,
        )
        if authorization is None:
            verify_execution_authorization(intent, authorization, require_bound=True)
        self._assert_registered_execution_snapshot(expected_snapshot_id)
        assert expected_snapshot_id is not None
        from assistant.dispatch_fence import (
            consume_execution_dispatch_permit,
            execution_dispatch_permit_fence,
        )

        with execution_dispatch_permit_fence(
            dispatch_permit,
            broker_session=self,
            idempotency_key=idempotency_key,
            expected_snapshot_id=expected_snapshot_id,
            expected_policy_fingerprint=expected_policy_fingerprint,
            expected_account_mode=self.account_mode,
        ):
            readiness = self.assert_account_and_asset_ready(ticker)
            if (
                is_fractional_order_quantity(quantity)
                and not readiness["asset"]["fractionable"]
            ):
                raise BrokerPreflightError(
                    f"{ticker.upper()} is not marked fractionable by the broker."
                )
            self._assert_execution_snapshot_unchanged(expected_snapshot_id)
            self._assert_execution_quote_unchanged(expected_snapshot_id, ticker)
            verify_execution_authorization(
                intent,
                authorization,
                expected_account_id=readiness["account"]["account_id"],
                expected_account_mode=self.account_mode,
                expected_snapshot_id=expected_snapshot_id,
                expected_policy_fingerprint=expected_policy_fingerprint,
                require_bound=True,
            )
            consume_execution_dispatch_permit(
                dispatch_permit,
                broker_session=self,
                idempotency_key=idempotency_key,
                expected_account_id=readiness["account"]["account_id"],
                expected_account_mode=self.account_mode,
                expected_snapshot_id=expected_snapshot_id,
                expected_policy_fingerprint=expected_policy_fingerprint,
            )
            self._consume_registered_execution_snapshot(expected_snapshot_id)
            self._assert_process_owner()
            if is_fractional_order_quantity(quantity):
                payload = {
                    "symbol": ticker,
                    "qty": str(quantity),
                    "side": side,
                    "type": "limit",
                    "time_in_force": "day",
                    "client_order_id": idempotency_key,
                    "limit_price": limit_price,
                }
                request = urllib.request.Request(
                    f"{self._trading_base_url}/v2/orders",
                    data=json.dumps(
                        payload, separators=(",", ":")
                    ).encode("utf-8"),
                    headers={
                        "APCA-API-KEY-ID": self._key,
                        "APCA-API-SECRET-KEY": self._secret,
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    response_payload = json.loads(response.read())
                if not isinstance(response_payload, Mapping):
                    raise RuntimeError(
                        "unexpected order response shape: "
                        f"{type(response_payload).__name__}"
                    )
                return _normalize_order(response_payload)
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import LimitOrderRequest

            order = self._client.submit_order(
                LimitOrderRequest(
                    symbol=ticker,
                    qty=quantity,
                    side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=limit_price,
                    client_order_id=idempotency_key,
                )
            )
            return _normalize_order(order)


def open_alpaca_broker_session() -> AlpacaBrokerSession:
    """Open one immutable credential/mode/session boundary for execution."""
    return AlpacaBrokerSession()


def get_account() -> dict:
    """Current account snapshot, including broker-side trading blocks."""
    return _normalize_account(_get_client().get_account(), paper=PAPER_TRADING)


def get_asset(ticker: str) -> dict:
    return _normalize_asset(_get_client().get_asset(ticker.upper()))


def assert_account_and_asset_ready(ticker: str) -> dict:
    """Fail before submission if Alpaca says trading or the asset is blocked."""
    account = get_account()
    account["account_id"] = _usable_account_id(account.get("account_id"))
    for field in (
        "trading_blocked",
        "account_blocked",
        "trade_suspended_by_user",
    ):
        if type(account[field]) is not bool:
            raise BrokerPreflightError(
                f"Broker account returned malformed {field} evidence."
            )
    blocked = [
        field
        for field in ("trading_blocked", "account_blocked", "trade_suspended_by_user")
        if account[field]
    ]
    if blocked:
        raise BrokerPreflightError(
            "Broker account is not trading-ready: " + ", ".join(blocked) + "."
        )
    if str(account["status"]).upper() != "ACTIVE":
        raise BrokerPreflightError(
            f"Broker account status is {account['status']!r}, not ACTIVE."
        )
    if not PAPER_TRADING:
        expected_account_id = os.environ.get("TRADING_ASSISTANT_LIVE_ACCOUNT_ID")
        if not expected_account_id:
            raise LiveTradingNotConfirmed(
                "Live account execution also requires TRADING_ASSISTANT_LIVE_ACCOUNT_ID "
                "to be set to the exact intended Alpaca account ID."
            )
        if expected_account_id != account["account_id"]:
            raise LiveTradingNotConfirmed(
                "TRADING_ASSISTANT_LIVE_ACCOUNT_ID does not match the connected Alpaca account."
            )
    asset = get_asset(ticker)
    _assert_asset_evidence(asset, ticker)
    if asset["status"].lower() != "active" or not asset["tradable"]:
        raise BrokerPreflightError(
            f"{asset['ticker']} is not broker-tradable "
            f"(status={asset['status']!r}, tradable={asset['tradable']})."
        )
    return {"account": account, "asset": asset}


def get_open_positions() -> list[dict]:
    client = _get_client()
    return [_normalize_position(position) for position in client.get_all_positions()]


def _normalize_latest_quote(ticker: str, quote: Any) -> dict:
    """Normalize one quote while preserving exact broker decimal text."""
    bid_decimal = _required_decimal(quote.bid_price, f"{ticker} bid price")
    ask_decimal = _required_decimal(quote.ask_price, f"{ticker} ask price")
    bid, ask = float(bid_decimal), float(ask_decimal)
    price_decimal = _exact_quote_price(bid_decimal, ask_decimal)
    return {
        "ticker": ticker,
        "price": float(price_decimal),
        "price_decimal": format(price_decimal, "f"),
        "bid": bid,
        "bid_decimal": format(bid_decimal, "f"),
        "ask": ask,
        "ask_decimal": format(ask_decimal, "f"),
        "timestamp": quote.timestamp,
    }


def get_latest_quote(ticker: str) -> dict:
    """Real-time bid/ask quote with the broker's OWN timestamp -- used to
    measure actual price staleness at approval time, instead of asserting
    freshness by comparing "now" against "now" (a real bug this fixes: a
    quote fetched over a weekend can be date(s) old even though nothing
    about the code path would have noticed). Returns bid/ask separately
    (not just a collapsed mid price) so the execution gate can check
    spread width -- a market order has no limit price to compare against,
    so a wide/thin quote otherwise passes validation with zero protection.
    Mid price when both sides are quoted; falls back to whichever single
    side is nonzero (a wide or one-sided book, common outside market
    hours, still yields SOME reference price rather than crashing)."""
    if not is_configured():
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set. Sign up for free "
            "paper trading keys at https://alpaca.markets, then set both as "
            "environment variables before calling any execution function."
        )
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest

    key = os.environ["APCA_API_KEY_ID"]
    secret = os.environ["APCA_API_SECRET_KEY"]
    client = StockHistoricalDataClient(key, secret)
    quotes = client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=[ticker]))
    # FCS-005: through the guarded helper, never a bare Decimal(str(...)).
    # A NaN bid parses fine and then RAISES InvalidOperation on the `> 0`
    # comparison two lines down -- an ArithmeticError, so it escapes every
    # `except ValueError` on the way out. An Infinity bid parses, passes
    # `> 0`, and propagates as the literal string "Infinity" into the
    # reference price. Neither is hypothetical: `_optional_float` in this same
    # module already filters non-finite broker values, so this file has always
    # assumed they occur.
    return _normalize_latest_quote(ticker, quotes[ticker])


def find_order_by_client_id(client_order_id: str) -> dict | None:
    """Look up a previously-submitted order by the client_order_id we sent
    (== our idempotency_key). Used for reconciliation after an ambiguous
    submission failure (e.g. a network timeout): Alpaca may have accepted
    the order even though we never saw a successful response, and this is
    the only way to find out.

    Returns the order dict when found. Returns None ONLY when Alpaca
    definitively confirms no such order exists (HTTP 404) -- a genuine
    confirmed absence. Any other failure (network, auth, 5xx, etc.)
    PROPAGATES rather than being swallowed into None -- a prior version
    caught every exception and returned None for all of them, which made
    "the order definitely doesn't exist" indistinguishable from "I
    couldn't check." Callers need that distinction: only a confirmed
    absence justifies concluding the order was never accepted; anything
    else must stay unresolved."""
    if not is_configured():
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set. Sign up for free "
            "paper trading keys at https://alpaca.markets, then set both as "
            "environment variables before calling any execution function."
        )
    client = _get_client()
    try:
        order = client.get_order_by_client_id(client_order_id)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            return None
        raise
    if order is None:
        return None
    return _normalize_order(order)


def get_order_by_id(order_id: str) -> dict | None:
    client = _get_client()
    try:
        order = client.get_order_by_id(order_id)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            return None
        raise
    return None if order is None else _normalize_order(order)


def get_open_orders() -> list[dict]:
    """Return currently open broker orders in a JSON-friendly shape."""
    return _get_orders_for_client(_get_client())


def cancel_order(order_id: str) -> dict:
    """Request cancellation and return the acknowledged local transition."""
    client = _get_client()
    client.cancel_order_by_id(order_id)
    return {"order_id": str(order_id), "status": "pending_cancel"}


_ACTIVITIES_MAX_PAGES = 100


def _account_activities_base_url() -> str:
    return (
        "https://paper-api.alpaca.markets"
        if PAPER_TRADING
        else "https://api.alpaca.markets"
    )


def _http_get_json(url: str) -> Any:
    """Authenticated GET against the Alpaca REST API.

    The pinned alpaca-py release does not expose the account-activities
    endpoint at all (no request class, no client method), so this module
    calls it directly over HTTPS with the same environment credentials the
    SDK client uses. Stdlib only -- no new dependency.
    """
    if not is_configured():
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set; cannot read "
            "account activities."
        )
    import json
    import urllib.request

    request = urllib.request.Request(
        url,
        headers={
            "APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"],
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def list_account_activities(
    *, after: str | None = None, page_size: int = 100
) -> list[dict]:
    """Every account activity (fills, fees, dividends, ...) as raw dicts.

    Amount fields stay exactly as the broker sent them (decimal strings),
    so the ledger can convert without a float round-trip. Pagination uses
    the documented page_token cursor (the id of the last row of the
    previous page); a bounded page count turns a broker-side cursor defect
    into a loud failure instead of an unbounded request loop.
    """
    from urllib.parse import urlencode

    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise TypeError(f"page_size must be an integer, got {page_size!r}")
    if not 1 <= page_size <= 100:
        raise ValueError(f"page_size must be 1..100, got {page_size!r}")
    activities: list[dict] = []
    page_token: str | None = None
    for _ in range(_ACTIVITIES_MAX_PAGES):
        params: dict[str, str] = {"page_size": str(page_size)}
        if after is not None:
            params["after"] = str(after)
        if page_token is not None:
            params["page_token"] = page_token
        url = (
            f"{_account_activities_base_url()}/v2/account/activities"
            f"?{urlencode(params)}"
        )
        page = _http_get_json(url)
        if not isinstance(page, list):
            raise RuntimeError(
                f"unexpected account-activities response shape: {type(page).__name__}"
            )
        for row in page:
            if not isinstance(row, dict) or not row.get("id"):
                raise RuntimeError(
                    "account activity row is missing its id; refusing to "
                    "paginate on an unidentifiable cursor"
                )
        activities.extend(page)
        if len(page) < page_size:
            return activities
        next_token = str(page[-1]["id"])
        if next_token == page_token:
            raise RuntimeError(
                "account-activities pagination cursor did not advance"
            )
        page_token = next_token
    raise RuntimeError(
        f"account activities exceeded {_ACTIVITIES_MAX_PAGES} pages; refusing "
        "to continue an unbounded fetch"
    )


def _run_trade_update_stream_with_credentials(
    callback: Callable[[dict], Any],
    *,
    key: str,
    secret: str,
    paper: bool,
    stop_event: Event | None = None,
) -> None:
    """Run one authenticated stream from an already captured connection."""
    from alpaca.trading.stream import TradingStream

    stream = TradingStream(key, secret, paper=paper)

    async def handle_update(update) -> None:
        order = _normalize_order(update.order)
        fill_numbers = _normalized_trade_update_numbers(
            fill_qty=getattr(update, "qty", None),
            fill_price=getattr(update, "price", None),
        )
        normalized = {
            "event": str(_enum_value(getattr(update, "event", order["status"]))),
            "event_id": getattr(update, "execution_id", None),
            "event_at": _optional_iso(getattr(update, "timestamp", None)),
            **fill_numbers,
            "order": order,
        }
        result = callback(normalized)
        if inspect.isawaitable(result):
            await result

    stream.subscribe_trade_updates(handle_update)

    if stop_event is not None:
        def _stop_when_signalled() -> None:
            stop_event.wait()
            try:
                stream.stop()
            except Exception:
                # Best-effort teardown only: monitor_orders() does not depend
                # on this succeeding, and raising from this watchdog thread
                # would be unhandled and mask the real shutdown path.
                pass

        Thread(target=_stop_when_signalled, name="trade-stream-stopper", daemon=True).start()

    stream.run()


def run_trade_update_stream(
    callback: Callable[[dict], Any], stop_event: Event | None = None
) -> None:
    """Run Alpaca's authenticated trade-update stream until interrupted.

    `stop_event`, when supplied, tears the stream down as soon as it is set so
    the socket isn't left open until process exit. order_reconciler's
    monitor_orders() already runs this on its own daemon thread (so its own
    shutdown never depends on this parameter), and passes the event only after
    signature-checking for it -- keep it optional.
    """
    if not is_configured():
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set."
        )
    key, secret, paper = _capture_connection_settings()
    _run_trade_update_stream_with_credentials(
        callback,
        key=key,
        secret=secret,
        paper=paper,
        stop_event=stop_event,
    )


def submit_market_order(
    ticker: str,
    shares: int | str,
    side: str = "buy",
    *,
    authorization: ExecutionAuthorization | None = None,
    idempotency_key: str,
    dispatch_permit: object | None = None,
    whole_shares_only: bool = True,
    broker_session: AlpacaBrokerSession | None = None,
    expected_snapshot_id: str | None = None,
    expected_policy_fingerprint: str,
) -> dict:
    """Submit through the exact session that captured authorization evidence.

    The module facade deliberately cannot construct a broker client.  Callers
    must pass the account-scoped ``AlpacaBrokerSession`` that captured the
    coherent snapshot plus its snapshot and policy fingerprints.  The session
    owns live-confirmation, state-recapture, one-use authorization, and
    idempotency checks immediately before broker contact.
    """
    expected_policy_fingerprint = _require_expected_policy_fingerprint(
        expected_policy_fingerprint
    )
    if not isinstance(broker_session, AlpacaBrokerSession):
        raise PermissionError(
            "The module-level submit facade requires the exact account-scoped "
            "AlpacaBrokerSession that captured the execution snapshot; call "
            "open_alpaca_broker_session(), capture_execution_portfolio_snapshot(), "
            "then pass that session and its snapshot/policy expectations."
        )
    return broker_session.submit_market_order(
        ticker,
        shares,
        side,
        authorization=authorization,
        idempotency_key=idempotency_key,
        dispatch_permit=dispatch_permit,
        whole_shares_only=whole_shares_only,
        expected_snapshot_id=expected_snapshot_id,
        expected_policy_fingerprint=expected_policy_fingerprint,
    )


def submit_limit_order(
    ticker: str,
    shares: int | str,
    limit_price: float,
    side: str = "buy",
    *,
    authorization: ExecutionAuthorization | None = None,
    idempotency_key: str,
    dispatch_permit: object | None = None,
    whole_shares_only: bool = True,
    broker_session: AlpacaBrokerSession | None = None,
    expected_snapshot_id: str | None = None,
    expected_policy_fingerprint: str,
) -> dict:
    """Submit a limit order through its snapshot-owning broker session.

    This remains separate from ``submit_market_order`` so the approved intent
    cannot be reconstructed with the wrong order type.  See that facade for
    the account-scoped session and evidence requirements.
    """
    expected_policy_fingerprint = _require_expected_policy_fingerprint(
        expected_policy_fingerprint
    )
    if not isinstance(broker_session, AlpacaBrokerSession):
        raise PermissionError(
            "The module-level submit facade requires the exact account-scoped "
            "AlpacaBrokerSession that captured the execution snapshot."
        )
    return broker_session.submit_limit_order(
        ticker,
        shares,
        limit_price,
        side,
        authorization=authorization,
        idempotency_key=idempotency_key,
        dispatch_permit=dispatch_permit,
        whole_shares_only=whole_shares_only,
        expected_snapshot_id=expected_snapshot_id,
        expected_policy_fingerprint=expected_policy_fingerprint,
    )
