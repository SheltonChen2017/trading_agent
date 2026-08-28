"""Append-only balanced portfolio journal and broker reconciliation.

The journal is the platform accounting record; broker snapshots are an
independent source reconciled against it. Historical state is never inferred
silently from the app's partial fill history: the operator must bootstrap an
opening snapshot explicitly, after which app-journaled fills can be synced
idempotently.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from assistant.schemas import PortfolioSnapshot
# One definition, imported rather than restated (FCS-016). The zone that
# decides an activity date's tax year and return interval must be the same
# zone this module stamps that date with, or the two disagree silently.
from assistant.tax_lots import MARKET_TIMEZONE
from assistant.storage import (
    AssistantStore,
    JournalTransactionConflictError,
    LedgerBootstrapConflictError,
)

USD = "USD"
BALANCE_TOLERANCE = Decimal("0.000001")
CASH_TOLERANCE = Decimal("0.01")
SHARE_TOLERANCE = Decimal("0.00000001")

# Sign convention (standard credit-normal double-entry accounting, applied
# consistently everywhere in this module -- independent review, 2026-07-30):
# ASSET and EXPENSE accounts (ACCOUNT_CASH, SECURITY_ACCOUNT_PREFIX,
# ACCOUNT_FEES) are POSITIVE when they increase -- "more cash/shares/expense"
# reads as a bigger positive number, which matches intuition.
# EQUITY, INCOME, and LIABILITY accounts (ACCOUNT_OPENING_EQUITY,
# ACCOUNT_CONTRIBUTED_CAPITAL, ACCOUNT_REALIZED_PNL, ACCOUNT_DIVIDEND_INCOME)
# are NEGATIVE when they increase -- a $100 realized GAIN posts as -100 to
# ACCOUNT_REALIZED_PNL, a $50 dividend posts as -50 to ACCOUNT_DIVIDEND_INCOME.
# This is what makes every transaction sum to zero across a buy (cash -,
# security +) or a sell (cash +, security -, realized_pnl -[gain] or
# +[loss]). Any FUTURE code that reads an income/equity account's balance
# and reports it to a user as "P&L" or "capital contributed" MUST negate it
# first, or the sign will read backwards.
ACCOUNT_CASH = "ASSET:CASH"
ACCOUNT_OPENING_EQUITY = "EQUITY:OPENING_BALANCE"
ACCOUNT_CONTRIBUTED_CAPITAL = "EQUITY:CONTRIBUTED_CAPITAL"
ACCOUNT_REALIZED_PNL = "INCOME:REALIZED_PNL"
ACCOUNT_DIVIDEND_INCOME = "INCOME:DIVIDENDS"
ACCOUNT_FEES = "EXPENSE:FEES"
SECURITY_ACCOUNT_PREFIX = "ASSET:SECURITY:"


class LedgerError(ValueError):
    """Malformed, unbalanced, incomplete, or contradictory ledger input."""


class BrokerActivityReviewRequiredError(LedgerError):
    """Structured refused rows from one otherwise valid activity sync."""

    def __init__(self, activities: list[dict[str, Any]]):
        self.activities = tuple(dict(activity) for activity in activities)
        super().__init__(
            "broker activities require manual review before evidence "
            f"capture can proceed: {json.dumps(activities, sort_keys=True)}"
        )


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise LedgerError(f"{field} must be numeric, not bool")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise LedgerError(f"{field} must be numeric, got {value!r}") from exc
    if not parsed.is_finite():
        raise LedgerError(f"{field} must be finite, got {value!r}")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _parse_at(value: str | datetime, field: str = "occurred_at") -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise LedgerError(f"{field} must be ISO-8601, got {value!r}") from exc
    if parsed.tzinfo is None:
        raise LedgerError(f"{field} must include a timezone")
    return parsed


def _corporate_date(value: str, field: str) -> str:
    """Normalize an ISO date or an explicitly timezone-aware timestamp."""
    text = str(value).strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return _parse_at(text, field).isoformat()


def _security_account(ticker: str) -> str:
    normalized = str(ticker).strip().upper()
    if not normalized or ":" in normalized:
        raise LedgerError(f"invalid ticker: {ticker!r}")
    return SECURITY_ACCOUNT_PREFIX + normalized


@dataclasses.dataclass(frozen=True)
class Posting:
    account: str
    amount: Decimal
    asset: str = USD
    quantity: Decimal | None = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.account, str) or not self.account.strip():
            raise LedgerError("posting account must be non-empty")
        if not isinstance(self.asset, str) or not self.asset.strip():
            raise LedgerError("posting asset must be non-empty")
        amount = _decimal(self.amount, "posting.amount")
        quantity = (
            None
            if self.quantity is None
            else _decimal(self.quantity, "posting.quantity")
        )
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "quantity", quantity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "asset": self.asset,
            "amount": _decimal_text(self.amount),
            "quantity": (
                _decimal_text(self.quantity)
                if self.quantity is not None
                else None
            ),
            "metadata": self.metadata,
        }


@dataclasses.dataclass(frozen=True)
class JournalTransaction:
    transaction_id: str
    occurred_at: str
    source: str
    external_id: str
    description: str
    postings: tuple[Posting, ...]
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def validate(self) -> None:
        for field_name in (
            "transaction_id",
            "source",
            "external_id",
            "description",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise LedgerError(f"{field_name} must be non-empty")
        _parse_at(self.occurred_at)
        if not self.postings:
            raise LedgerError("a journal transaction requires at least one posting")
        totals: dict[str, Decimal] = {}
        for posting in self.postings:
            totals[posting.asset] = totals.get(posting.asset, Decimal("0")) + posting.amount
        unbalanced = {
            asset: total
            for asset, total in totals.items()
            if abs(total) > BALANCE_TOLERANCE
        }
        if unbalanced:
            raise LedgerError(f"journal transaction is not balanced: {unbalanced}")


def post_transaction(
    store: AssistantStore, transaction: JournalTransaction
) -> bool:
    transaction.validate()
    try:
        return store.append_journal_transaction(
            transaction_id=transaction.transaction_id,
            occurred_at=transaction.occurred_at,
            source=transaction.source,
            external_id=transaction.external_id,
            description=transaction.description,
            postings=[posting.to_dict() for posting in transaction.postings],
            metadata=transaction.metadata,
        )
    except JournalTransactionConflictError as exc:
        raise LedgerError(str(exc)) from exc


def ledger_balances(store: AssistantStore) -> dict[str, Any]:
    cash = Decimal("0")
    security_book_value: dict[str, Decimal] = {}
    shares: dict[str, Decimal] = {}
    trial_balance: dict[str, Decimal] = {}
    transaction_ids: set[str] = set()
    rows = store.list_journal_postings()

    for row in rows:
        transaction_ids.add(row["transaction_id"])
        amount = _decimal(row["amount"], "stored posting amount")
        asset = row["asset"]
        trial_balance[asset] = trial_balance.get(asset, Decimal("0")) + amount
        account = row["account"]
        if account == ACCOUNT_CASH:
            cash += amount
        if account.startswith(SECURITY_ACCOUNT_PREFIX):
            ticker = account[len(SECURITY_ACCOUNT_PREFIX) :]
            security_book_value[ticker] = (
                security_book_value.get(ticker, Decimal("0")) + amount
            )
            if row["quantity"] is not None:
                shares[ticker] = shares.get(ticker, Decimal("0")) + _decimal(
                    row["quantity"], "stored posting quantity"
                )

    unbalanced = {
        asset: _decimal_text(total)
        for asset, total in trial_balance.items()
        if abs(total) > BALANCE_TOLERANCE
    }
    if unbalanced:
        raise LedgerError(f"stored journal trial balance is not zero: {unbalanced}")
    return {
        "cash": cash,
        "security_book_value": security_book_value,
        "shares": shares,
        "transaction_count": len(transaction_ids),
        "posting_count": len(rows),
        "trial_balance": trial_balance,
    }


def bootstrap_opening_snapshot(
    store: AssistantStore,
    snapshot: PortfolioSnapshot,
    *,
    confirmation: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record the current broker state as an explicit opening balance."""
    if confirmation.strip().lower() != "bootstrap":
        raise LedgerError('opening bootstrap requires confirmation="bootstrap"')
    existing = ledger_balances(store)
    if existing["transaction_count"]:
        raise LedgerError("cannot bootstrap a non-empty portfolio journal")
    if store.get_system_state("ledger_bootstrap") is not None:
        raise LedgerError("portfolio journal was already bootstrapped")

    occurred = now or datetime.now(timezone.utc)
    if occurred.tzinfo is None:
        raise LedgerError("bootstrap time must be timezone-aware")
    if snapshot.source == "alpaca" and not snapshot.account_id:
        raise LedgerError(
            "Alpaca ledger bootstrap requires the connected broker account ID"
        )

    postings: list[Posting] = []
    total_opening_value = _decimal(snapshot.cash, "snapshot.cash")
    postings.append(Posting(ACCOUNT_CASH, total_opening_value))
    for position in snapshot.positions:
        qty = _decimal(position.shares, f"{position.ticker}.shares")
        entry_price = _decimal(
            position.entry_price, f"{position.ticker}.entry_price"
        )
        if qty < 0 or entry_price < 0:
            raise LedgerError("opening positions cannot have negative shares or basis")
        book_value = qty * entry_price
        total_opening_value += book_value
        postings.append(
            Posting(
                _security_account(position.ticker),
                book_value,
                quantity=qty,
                metadata={"opening_average_cost": _decimal_text(entry_price)},
            )
        )
    postings.append(Posting(ACCOUNT_OPENING_EQUITY, -total_opening_value))

    snapshot_material = {
        "as_of": snapshot.as_of,
        "source": snapshot.source,
        "account_mode": snapshot.account_mode,
        "account_id": snapshot.account_id,
        "cash": snapshot.cash,
        "positions": [
            {
                "ticker": position.ticker,
                "shares": position.shares,
                "entry_price": position.entry_price,
            }
            for position in snapshot.positions
        ],
    }
    digest = hashlib.sha256(
        json.dumps(snapshot_material, sort_keys=True).encode("utf-8")
    ).hexdigest()
    transaction = JournalTransaction(
        transaction_id=f"opening-{digest[:24]}",
        occurred_at=occurred.isoformat(),
        source=f"opening_snapshot:{snapshot.source}",
        external_id=f"opening_snapshot:{digest}",
        description="Explicit portfolio opening balance",
        postings=tuple(postings),
        metadata=snapshot_material,
    )
    state = {
        "bootstrapped_at": occurred.isoformat(),
        "snapshot_as_of": snapshot.as_of,
        "source": snapshot.source,
        "account_mode": snapshot.account_mode,
        "account_id": snapshot.account_id,
        "snapshot_hash": digest,
    }
    transaction.validate()
    try:
        store.bootstrap_portfolio_ledger(
            transaction_id=transaction.transaction_id,
            occurred_at=transaction.occurred_at,
            source=transaction.source,
            external_id=transaction.external_id,
            description=transaction.description,
            postings=[posting.to_dict() for posting in transaction.postings],
            metadata=transaction.metadata,
            bootstrap_state=state,
        )
    except LedgerBootstrapConflictError as exc:
        raise LedgerError(str(exc)) from exc
    return state


def _transaction_id(external_id: str) -> str:
    digest = hashlib.sha256(external_id.encode("utf-8")).hexdigest()
    return "journal-" + digest[:24]


def _exact_fill_decimal(fill: dict[str, Any], field: str) -> Decimal:
    """Prefer the provider's exact decimal text over the rounded float.

    ``list_fills`` emits both ``<field>`` as a float for compatibility and
    ``<field>_decimal`` as the provider's exact text.  Reading the float
    re-rounds a fractional fill before it reaches book cost and realized P&L,
    so the exact text is authoritative whenever it is present.  Legacy rows
    predating the text columns keep the float and are disclosed through
    ``numeric_evidence_status``.
    """
    exact = fill.get(f"{field}_decimal")
    if isinstance(exact, str) and exact.strip():
        return _decimal(exact, f"fill.{field}_decimal")
    return _decimal(fill[field], f"fill.{field}")


def _fill_transaction_header(
    fill: dict[str, Any], *, qty: Decimal, price: Decimal
) -> tuple[str, str, str, str, str, dict[str, Any]]:
    """Build the immutable journal identity shared by insert and retry paths."""
    ticker = str(fill["ticker"]).upper()
    side = str(fill["side"]).lower()
    fill_id = str(fill["fill_id"])
    external_id = f"app_fill:{fill_id}"
    metadata = {
        "fill_id": fill_id,
        "order_id": fill.get("order_id"),
        "proposal_id": fill.get("proposal_id"),
        "ticker": ticker,
        "side": side,
        "qty": _decimal_text(qty),
        "price": _decimal_text(price),
        "fees_included": False,
        # Deliberately NOT extended with numeric_evidence_status. This
        # metadata is part of the journal's content identity, so adding a key
        # makes every previously journaled row mismatch on re-sync. Carrying
        # that disclosure requires an additive migration.
    }
    return (
        _transaction_id(external_id),
        _parse_at(fill["at"], "fill.at").isoformat(),
        "assistant_broker_event",
        external_id,
        f"{side.upper()} {qty} {ticker} @ {price}",
        metadata,
    )


def _fill_transaction(
    *,
    fill: dict[str, Any],
    balances: dict[str, Any],
) -> JournalTransaction:
    ticker = str(fill["ticker"]).upper()
    side = str(fill["side"]).lower()
    qty = _exact_fill_decimal(fill, "qty")
    price = _exact_fill_decimal(fill, "price")
    if side not in ("buy", "sell") or qty <= 0 or price <= 0:
        raise LedgerError(f"invalid fill: {fill!r}")
    (
        transaction_id,
        occurred_at,
        source,
        external_id,
        description,
        metadata,
    ) = _fill_transaction_header(fill, qty=qty, price=price)
    gross = qty * price
    security_account = _security_account(ticker)

    if side == "buy":
        postings = (
            Posting(security_account, gross, quantity=qty),
            Posting(ACCOUNT_CASH, -gross),
        )
    else:
        held = balances["shares"].get(ticker, Decimal("0"))
        book_value = balances["security_book_value"].get(
            ticker, Decimal("0")
        )
        if held + SHARE_TOLERANCE < qty or held <= 0:
            raise LedgerError(
                f"cannot journal sale of {qty} {ticker}; ledger holds {held}"
            )
        average_book_cost = book_value / held
        basis_removed = average_book_cost * qty
        postings = (
            Posting(ACCOUNT_CASH, gross),
            Posting(
                security_account,
                -basis_removed,
                quantity=-qty,
                metadata={
                    "book_basis_method": "moving_average",
                    "book_cost_per_share": _decimal_text(average_book_cost),
                },
            ),
            Posting(ACCOUNT_REALIZED_PNL, basis_removed - gross),
        )

    return JournalTransaction(
        transaction_id=transaction_id,
        occurred_at=occurred_at,
        source=source,
        external_id=external_id,
        description=description,
        postings=postings,
        metadata=metadata,
    )


def sync_app_fills(store: AssistantStore) -> dict[str, Any]:
    """Append app-journaled fills after the explicit opening snapshot."""
    bootstrap = store.get_system_state("ledger_bootstrap")
    if not isinstance(bootstrap, dict) or not bootstrap.get("bootstrapped_at"):
        raise LedgerError("bootstrap the portfolio journal before syncing fills")
    cutoff = _parse_at(bootstrap["bootstrapped_at"], "ledger bootstrapped_at")
    inserted = 0
    duplicates = 0
    skipped_pre_bootstrap = 0
    existing_external_ids = {
        row["external_id"] for row in store.list_journal_postings()
    }
    for fill in store.list_fills():
        if _parse_at(fill["at"], "fill.at") <= cutoff:
            skipped_pre_bootstrap += 1
            continue
        external_id = f"app_fill:{fill['fill_id']}"
        if external_id in existing_external_ids:
            existing = store.get_journal_transaction_by_external_id(external_id)
            exact_header = _fill_transaction_header(
                fill,
                qty=_exact_fill_decimal(fill, "qty"),
                price=_exact_fill_decimal(fill, "price"),
            )
            # Journals written before exact companions were consumed have an
            # immutable float-derived header. Accept that legacy identity as
            # well, without rewriting it or weakening conflict detection for
            # journals already written with provider-exact digits.
            legacy_header = _fill_transaction_header(
                fill,
                qty=_decimal(fill["qty"], "fill.qty"),
                price=_decimal(fill["price"], "fill.price"),
            )
            actual_header = (
                existing["transaction_id"],
                existing["occurred_at"],
                existing["source"],
                existing["external_id"],
                existing["description"],
                existing["metadata"],
            )
            if actual_header not in (exact_header, legacy_header):
                raise LedgerError(
                    f"journal external_id {external_id!r} already exists "
                    "with different content"
                )
            duplicates += 1
            continue
        balances = ledger_balances(store)
        transaction = _fill_transaction(fill=fill, balances=balances)
        if post_transaction(store, transaction):
            inserted += 1
            existing_external_ids.add(external_id)
        else:
            duplicates += 1
    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "skipped_pre_bootstrap": skipped_pre_bootstrap,
        "fees_included": False,
    }


def record_cash_transfer(
    store: AssistantStore,
    *,
    external_id: str,
    amount: Any,
    occurred_at: str,
    description: str,
) -> bool:
    value = _decimal(amount, "amount")
    if value == 0:
        raise LedgerError("cash transfer amount cannot be zero")
    transaction = JournalTransaction(
        transaction_id=_transaction_id(f"cash_transfer:{external_id}"),
        occurred_at=_parse_at(occurred_at).isoformat(),
        source="cash_transfer",
        external_id=f"cash_transfer:{external_id}",
        description=description,
        postings=(
            Posting(ACCOUNT_CASH, value),
            Posting(ACCOUNT_CONTRIBUTED_CAPITAL, -value),
        ),
    )
    return post_transaction(store, transaction)


def record_dividend(
    store: AssistantStore,
    *,
    external_id: str,
    ticker: str,
    gross_amount: Any,
    occurred_at: str,
    ex_date: str | None = None,
    pay_date: str | None = None,
    amount_per_share: Any | None = None,
    shares_entitled: Any | None = None,
    tax_classification: str = "unknown",
) -> bool:
    amount = _decimal(gross_amount, "gross_amount")
    if amount <= 0:
        raise LedgerError("gross dividend must be positive")
    normalized_classification = str(tax_classification).strip().lower()
    if normalized_classification not in ("qualified", "ordinary", "unknown"):
        raise LedgerError(
            "tax_classification must be 'qualified', 'ordinary', or 'unknown'"
        )
    normalized_ticker = _security_account(ticker)[
        len(SECURITY_ACCOUNT_PREFIX) :
    ]
    metadata: dict[str, Any] = {
        "ticker": normalized_ticker,
        "tax_classification": normalized_classification,
    }
    if ex_date is not None:
        metadata["ex_date"] = _corporate_date(ex_date, "ex_date")
    if pay_date is not None:
        metadata["pay_date"] = _corporate_date(pay_date, "pay_date")
    if amount_per_share is not None:
        per_share = _decimal(amount_per_share, "amount_per_share")
        if per_share <= 0:
            raise LedgerError("amount_per_share must be positive")
        metadata["amount_per_share"] = _decimal_text(per_share)
    if shares_entitled is not None:
        entitled = _decimal(shares_entitled, "shares_entitled")
        if entitled <= 0:
            raise LedgerError("shares_entitled must be positive")
        metadata["shares_entitled"] = _decimal_text(entitled)
    if amount_per_share is not None and shares_entitled is not None:
        expected_gross = per_share * entitled
        if abs(expected_gross - amount) > CASH_TOLERANCE:
            raise LedgerError(
                "gross_amount does not match amount_per_share multiplied by "
                f"shares_entitled ({amount} vs {expected_gross})"
            )
    transaction = JournalTransaction(
        transaction_id=_transaction_id(f"dividend:{external_id}"),
        occurred_at=_parse_at(occurred_at).isoformat(),
        source="corporate_action",
        external_id=f"dividend:{external_id}",
        description=f"Cash dividend for {normalized_ticker}",
        postings=(
            Posting(ACCOUNT_CASH, amount),
            Posting(
                ACCOUNT_DIVIDEND_INCOME,
                -amount,
                metadata=metadata,
            ),
        ),
        metadata=metadata,
    )
    return post_transaction(store, transaction)


def record_split(
    store: AssistantStore,
    *,
    external_id: str,
    ticker: str,
    ratio: Any,
    occurred_at: str,
) -> bool:
    """Apply a confirmed split to share quantity without changing book basis.

    Production callers must refresh broker order state and run
    :func:`sync_app_fills` immediately before calling this function.  The
    local guard below can prove that every *known* pre-split fill is
    journaled, but only broker reconciliation can discover a delayed fill
    that has not reached the local event journal yet.
    """
    split_ratio = _decimal(ratio, "ratio")
    if split_ratio <= 0 or split_ratio == 1:
        raise LedgerError("split ratio must be positive and different from 1")
    normalized_ticker = _security_account(ticker)[
        len(SECURITY_ACCOUNT_PREFIX) :
    ]
    effective_at = _parse_at(occurred_at)
    expected_external_id = f"split:{external_id}"
    postings = store.list_journal_postings()
    existing_split = store.get_journal_transaction_by_external_id(
        expected_external_id
    )
    if existing_split is not None:
        existing_metadata = existing_split["metadata"]
        try:
            pre_split = _decimal(
                existing_metadata["pre_split_shares"],
                "stored pre_split_shares",
            )
        except (KeyError, LedgerError) as exc:
            raise LedgerError(
                f"journal external_id {expected_external_id!r} already exists "
                "with different content"
            ) from exc
        post_split = pre_split * split_ratio
        retry_metadata = {
            "ticker": normalized_ticker,
            "corporate_action": "split",
            "ratio": _decimal_text(split_ratio),
            "pre_split_shares": _decimal_text(pre_split),
            "post_split_shares": _decimal_text(post_split),
            "cash_in_lieu_included": False,
        }
        retry = JournalTransaction(
            transaction_id=_transaction_id(expected_external_id),
            occurred_at=effective_at.isoformat(),
            source="corporate_action",
            external_id=expected_external_id,
            description=(
                f"Confirmed {split_ratio}:1 share adjustment for {normalized_ticker}"
            ),
            postings=(
                Posting(
                    _security_account(normalized_ticker),
                    Decimal("0"),
                    quantity=post_split - pre_split,
                    metadata=retry_metadata,
                ),
            ),
            metadata=retry_metadata,
        )
        return post_transaction(store, retry)
    security_account = _security_account(normalized_ticker)
    # Independent review, 2026-07-31: held_at_effective below only sums
    # postings ALREADY in the journal -- if ledger-sync hasn't caught up on
    # every pre-split fill yet (e.g. a delayed poll picks up an old fill
    # after the split was already recorded), the adjustment is sized
    # against too few shares, and the late-arriving fill then posts its
    # ORIGINAL non-split-adjusted qty/price with no correction, silently
    # understating post-split share count and cost basis. Fail closed here
    # instead: refuse to apply the split while any known app fill for this
    # ticker at/before the effective date has not yet been journaled.
    bootstrap = store.get_system_state("ledger_bootstrap")
    bootstrap_cutoff = (
        _parse_at(bootstrap["bootstrapped_at"], "ledger bootstrapped_at")
        if isinstance(bootstrap, dict) and bootstrap.get("bootstrapped_at")
        else None
    )
    journaled_external_ids = {posting["external_id"] for posting in postings}
    unsynced_pre_split_fills = [
        fill
        for fill in store.list_fills()
        if str(fill.get("ticker", "")).upper() == normalized_ticker
        and _parse_at(fill["at"]) <= effective_at
        # Fills at/before the bootstrap cutoff are represented by the
        # opening snapshot, not an app_fill:* posting -- sync_app_fills()
        # deliberately skips them the same way, so they must be excluded
        # here too or the split would be permanently blocked.
        and (bootstrap_cutoff is None or _parse_at(fill["at"]) > bootstrap_cutoff)
        and f"app_fill:{fill.get('fill_id')}" not in journaled_external_ids
    ]
    if unsynced_pre_split_fills:
        raise LedgerError(
            f"cannot apply split for {normalized_ticker}; "
            f"{len(unsynced_pre_split_fills)} pre-split fill(s) have not "
            "been journaled yet -- run ledger-sync before ledger-split"
        )
    held_at_effective = sum(
        (
            _decimal(posting["quantity"], "stored posting quantity")
            for posting in postings
            if posting["account"] == security_account
            and posting["quantity"] is not None
            and _parse_at(posting["occurred_at"]) <= effective_at
        ),
        Decimal("0"),
    )
    if held_at_effective <= 0:
        raise LedgerError(
            f"cannot apply split for {normalized_ticker}; journal held "
            f"{held_at_effective} shares at the effective time"
        )
    post_split = held_at_effective * split_ratio
    metadata = {
        "ticker": normalized_ticker,
        "corporate_action": "split",
        "ratio": _decimal_text(split_ratio),
        "pre_split_shares": _decimal_text(held_at_effective),
        "post_split_shares": _decimal_text(post_split),
        "cash_in_lieu_included": False,
    }
    transaction = JournalTransaction(
        transaction_id=_transaction_id(f"split:{external_id}"),
        occurred_at=effective_at.isoformat(),
        source="corporate_action",
        external_id=expected_external_id,
        description=(
            f"Confirmed {split_ratio}:1 share adjustment for {normalized_ticker}"
        ),
        postings=(
            Posting(
                _security_account(normalized_ticker),
                Decimal("0"),
                quantity=post_split - held_at_effective,
                metadata=metadata,
            ),
        ),
        metadata=metadata,
    )
    return post_transaction(store, transaction)


def record_fee(
    store: AssistantStore,
    *,
    external_id: str,
    amount: Any,
    occurred_at: str,
    description: str,
) -> bool:
    fee = _decimal(amount, "fee")
    if fee <= 0:
        raise LedgerError("fee must be positive")
    transaction = JournalTransaction(
        transaction_id=_transaction_id(f"fee:{external_id}"),
        occurred_at=_parse_at(occurred_at).isoformat(),
        source="broker_fee",
        external_id=f"fee:{external_id}",
        description=description,
        postings=(
            Posting(ACCOUNT_FEES, fee),
            Posting(ACCOUNT_CASH, -fee),
        ),
    )
    return post_transaction(store, transaction)


# Broker activity types this sync knows how to journal automatically.
# Everything else fails closed: the sync raises, the calling observation
# refuses to capture evidence, and the operator gets the exact unhandled
# rows instead of a slowly drifting cash mismatch.
# FEE -> record_fee, DIV -> record_dividend, and explicit deposits/withdrawals
# -> record_cash_transfer. Deliberately NOT handled, so they keep
# failing closed: INT (never observed on this paper account; no
# INCOME:INTEREST account or agreed treatment exists yet), every DIV*
# variant (DIVNRA/DIVROC/DIVCGL/...: withholding, return-of-capital, and
# capital-gain distributions each need their own reviewed tax treatment),
# JNLC (a generic cash journal does not prove contributed-capital treatment),
# and JNLS (a securities journal moves shares, not cash).
# The external-id prefix each handled type journals under. This is the
# single source of the handled set (counter-review DHCR-002): the
# cross-type reuse guard must have a prefix for every type the loop
# accepts, and a hand-maintained second literal would let a future type be
# accepted with no prefix -- raising KeyError, which is NOT a LedgerError
# and so escapes the per-row refusal handler as an unhandled crash instead
# of a clean fail-closed refusal.
_ACTIVITY_EXTERNAL_ID_PREFIXES = {
    "FEE": "fee:",
    "DIV": "dividend:",
    "CSD": "cash_transfer:",
    "CSW": "cash_transfer:",
}
_HANDLED_ACTIVITY_TYPES = frozenset(_ACTIVITY_EXTERNAL_ID_PREFIXES)
_CASH_TRANSFER_ACTIVITY_TYPES = frozenset({"CSD", "CSW"})
# Trade activities are deliberately NOT ingested here: fills enter the
# journal through the app's own fill records (sync_app_fills), and a fill
# the app never saw surfaces as a share-quantity mismatch in
# reconcile_snapshot rather than being silently absorbed from the broker
# feed.
_TRADE_ACTIVITY_TYPES = frozenset({"FILL"})


def _activity_posted_at(
    activity: dict[str, Any], *, created_after: datetime | None
) -> datetime:
    """Return a defensible journal time for a non-trade activity.

    Alpaca's published non-trade activity schema does not include
    ``created_at``. When that useful extension is absent, accept the row
    only if the caller fetched it with Alpaca's documented exclusive
    ``after`` bound. One microsecond after that bound is a deterministic,
    conservative journal time; the opaque activity ID is never treated as
    a timestamp contract.
    """
    raw_created_at = activity.get("created_at")
    if raw_created_at not in (None, ""):
        return _parse_at(raw_created_at, "activity created_at")

    if created_after is not None:
        if created_after.tzinfo is None:
            raise LedgerError("activity created-after bound must include a timezone")
        return created_after + timedelta(microseconds=1)
    raise LedgerError(
        "activity posting time is missing: no parseable created_at or "
        "verified broker created-after bound"
    )


def _activity_occurred_at(
    activity: dict[str, Any], *, activity_type: str, posted_at: datetime
) -> datetime:
    """Return the economic date for income/cash flow attribution.

    ``created_at`` (or its bootstrap-bound surrogate) proves that the row
    belongs after the opening snapshot. It is not necessarily the date on
    which a dividend or external cash flow belongs in accounting/performance
    reports. Alpaca's published NTA ``date`` is the activity/settlement date;
    prefer it for DIV/CSD/CSW while retaining creation time for fees. When
    neither economic date nor a real creation timestamp exists, refuse these
    financial types rather than assigning every future event to bootstrap.
    """
    if activity_type == "FEE":
        return posted_at
    raw_date = activity.get("date")
    if raw_date not in (None, ""):
        normalized = _corporate_date(str(raw_date), "activity date")
        try:
            activity_date = date.fromisoformat(normalized)
        except ValueError:
            return _parse_at(normalized, "activity date")
        # Market-local midnight, NOT UTC midnight (counter-review
        # DHCR-001). A bare activity date means "this happened on calendar
        # day D in the US market", and every consumer that buckets these
        # rows does so in market-local time: `tax_year_of()` converts to
        # MARKET_TIMEZONE before taking `.year`, and the external-flow
        # windows in paper_evidence/portfolio_history are bounded by real
        # post-close capture instants. UTC midnight is the PREVIOUS
        # evening in New York, so it lands on the wrong side of both
        # boundaries: a 2027-01-01 flow bucketed as tax year 2026, and --
        # under US standard time, when the 16:30 Pacific capture falls at
        # 00:30Z the next day -- a flow attributed to the previous
        # session's return interval. Market-local midnight is correct on
        # both axes year-round.
        return datetime.combine(
            activity_date, datetime.min.time(), MARKET_TIMEZONE
        ).astimezone(timezone.utc)
    if activity.get("created_at") not in (None, ""):
        return posted_at
    raise LedgerError(
        f"{activity_type} requires an activity date or real created_at; "
        "the bootstrap-bound timestamp surrogate is not an economic date"
    )


def _broker_activity_subtype(activity: dict[str, Any]) -> str:
    """Normalize legacy/current subtype spellings and reject disagreement."""
    values = {
        str(activity.get(field) or "").strip().upper()
        for field in ("activity_sub_type", "activity_subtype")
        if str(activity.get(field) or "").strip()
    }
    if len(values) > 1:
        raise LedgerError("activity carries conflicting subtype fields")
    return next(iter(values), "")


def _assert_broker_activity_id_not_retyped(
    store: AssistantStore, *, activity_type: str, activity_id: str
) -> None:
    """One immutable broker activity ID may map to one accounting event."""
    expected_prefix = _ACTIVITY_EXTERNAL_ID_PREFIXES.get(activity_type)
    if expected_prefix is None:
        raise LedgerError(
            f"no external-id prefix is declared for handled activity type "
            f"{activity_type}; refusing to journal it"
        )
    for existing_type, prefix in (
        ("FEE", "fee:"),
        ("DIV", "dividend:"),
        ("cash transfer", "cash_transfer:"),
    ):
        if prefix == expected_prefix:
            continue
        if store.get_journal_transaction_by_external_id(prefix + activity_id):
            raise LedgerError(
                f"broker activity id {activity_id!r} is already journaled as "
                f"{existing_type}; refusing to reinterpret it as {activity_type}"
            )


def _post_broker_activity(
    store: AssistantStore,
    *,
    activity: dict[str, Any],
    activity_type: str,
    activity_id: str,
    net_amount: Decimal,
    posted_at: datetime,
) -> bool:
    """Journal one recognized broker activity; True when newly inserted.

    Raises LedgerError for any shape this dispatch does not positively
    recognize (wrong sign for the type, missing symbol, inconsistent
    per-share arithmetic, ...). The caller collects that refusal into the
    fail-closed unhandled list rather than aborting the whole sync, so the
    operator sees every problem row in one error.
    """
    description = str(activity.get("description") or "").strip()
    sub_type = _broker_activity_subtype(activity)
    raw_currency = str(activity.get("currency") or "").strip().upper()
    if raw_currency and raw_currency != USD:
        raise LedgerError(
            f"{activity_type} currency is {raw_currency}, not supported {USD}"
        )
    _assert_broker_activity_id_not_retyped(
        store, activity_type=activity_type, activity_id=activity_id
    )
    occurred_at = _activity_occurred_at(
        activity, activity_type=activity_type, posted_at=posted_at
    ).isoformat()
    if activity_type == "FEE":
        if net_amount >= 0:
            # A fee credit/reversal is a shape this sync has never seen;
            # refuse rather than guess its accounting treatment.
            raise LedgerError(f"FEE with non-negative net_amount {net_amount}")
        return record_fee(
            store,
            external_id=activity_id,
            amount=-net_amount,
            occurred_at=occurred_at,
            description=description or f"Broker {sub_type or 'FEE'} fee",
        )
    if activity_type == "DIV":
        # Plain legacy cash dividend or explicit CDIV only. Current Alpaca
        # activity contracts also use DIV for SDIV (stock) and SPD
        # (substitute payment), which require different accounting/tax paths.
        if sub_type not in ("", "CDIV"):
            raise LedgerError(f"unsupported DIV subtype {sub_type}")
        if net_amount <= 0:
            raise LedgerError(f"DIV with non-positive net_amount {net_amount}")
        symbol = str(activity.get("symbol") or "").strip().upper()
        if not symbol:
            raise LedgerError("DIV activity is missing its symbol")
        extras: dict[str, Any] = {}
        raw_per_share = activity.get("per_share_amount")
        if raw_per_share not in (None, ""):
            extras["amount_per_share"] = _decimal(
                raw_per_share, "DIV per_share_amount"
            )
        raw_qty = activity.get("qty")
        if raw_qty not in (None, ""):
            extras["shares_entitled"] = _decimal(raw_qty, "DIV qty")
        # tax_classification stays "unknown": the broker feed does not say
        # qualified vs ordinary, and inventing a tax fact here would flow
        # straight into the annual tax report.
        return record_dividend(
            store,
            external_id=activity_id,
            ticker=symbol,
            gross_amount=net_amount,
            occurred_at=occurred_at,
            tax_classification="unknown",
            **extras,
        )
    if activity_type in _CASH_TRANSFER_ACTIVITY_TYPES:
        if net_amount == 0:
            raise LedgerError(f"{activity_type} with zero net_amount")
        if activity_type == "CSD" and net_amount < 0:
            raise LedgerError("CSD (deposit) with negative net_amount")
        if activity_type == "CSW" and net_amount > 0:
            raise LedgerError("CSW (withdrawal) with positive net_amount")
        return record_cash_transfer(
            store,
            external_id=activity_id,
            amount=net_amount,
            occurred_at=occurred_at,
            description=description
            or f"Broker {activity_type} cash movement",
        )
    raise LedgerError(f"no journal mapping for activity type {activity_type}")


ACKNOWLEDGEMENT_TREATMENTS = frozenset(
    {"fee", "dividend", "cash_transfer", "no_cash_effect"}
)


def broker_activity_fingerprint(activity: Any) -> str:
    """Content identity of one broker activity row.

    Binds an operator decision to the exact row it was made about. If the
    provider later edits the row -- or reuses the id for something else --
    the fingerprint changes and the decision stops applying, which is the
    fail-closed direction.
    """
    if not isinstance(activity, dict):
        raise LedgerError("broker activity must be an object to fingerprint")
    canonical = json.dumps(activity, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _acknowledged_amount(activity: dict[str, Any]) -> Decimal | None:
    raw = activity.get("net_amount")
    if raw is None or str(raw).strip() == "":
        return None
    return _decimal(raw, "activity net_amount")


def _validate_acknowledged_activity(
    activity: dict[str, Any], treatment: str
) -> Decimal | None:
    """Validate facts an operator is never allowed to override."""
    raw_status = activity.get("status")
    status = str(raw_status or "").strip().lower()
    if raw_status is not None and status != "executed":
        raise LedgerError(
            f"activity status is {status or '(empty)'}, not executed"
        )
    amount = _acknowledged_amount(activity)
    if treatment == "no_cash_effect":
        if amount is None:
            raise LedgerError(
                "no_cash_effect requires an explicit zero broker net_amount; "
                "a missing amount is unknown"
            )
        if amount != 0:
            raise LedgerError(
                "no_cash_effect is only valid when the broker reports no cash "
                f"movement; this row reports {_decimal_text(amount)}"
            )
        return amount

    raw_currency = str(activity.get("currency") or "").strip().upper()
    if raw_currency and raw_currency != USD:
        raise LedgerError(
            f"acknowledged activity currency is {raw_currency}, not supported {USD}"
        )
    if amount is None or amount == 0:
        raise LedgerError(
            f"treatment {treatment!r} needs a non-zero broker net_amount to journal"
        )
    if treatment == "fee" and amount > 0:
        raise LedgerError("a fee must have a negative broker net_amount")
    if treatment == "dividend" and amount < 0:
        raise LedgerError("a dividend must have a positive broker net_amount")
    return amount


_ACKNOWLEDGED_TREATMENT_ACTIVITY_TYPES = {
    "fee": "FEE",
    "dividend": "DIV",
    "cash_transfer": "CSD",
}


def _assert_acknowledged_activity_id_not_retyped(
    store: AssistantStore, *, treatment: str, activity_id: str
) -> None:
    mapped_type = _ACKNOWLEDGED_TREATMENT_ACTIVITY_TYPES.get(treatment)
    if mapped_type is not None:
        _assert_broker_activity_id_not_retyped(
            store, activity_type=mapped_type, activity_id=activity_id
        )
        return
    for existing_type, prefix in (
        ("FEE", "fee:"),
        ("DIV", "dividend:"),
        ("cash transfer", "cash_transfer:"),
    ):
        if store.get_journal_transaction_by_external_id(prefix + activity_id):
            raise LedgerError(
                f"broker activity id {activity_id!r} is already journaled as "
                f"{existing_type}; refusing to mark it no_cash_effect"
            )


def acknowledge_broker_activity(
    store: AssistantStore,
    activity: Any,
    *,
    treatment: str,
    operator: str,
    rationale: str,
    ticker: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record an operator's accounting decision about one refused activity.

    This is the ONLY way an unsupported broker activity stops blocking
    evidence capture without a code change. It deliberately does not
    journal anything itself: `sync_broker_activities` remains the single
    posting path, so the decision is applied idempotently on the next run
    and can be re-applied after a restore.

    The operator chooses the TREATMENT, never the AMOUNT. Every figure is
    taken from the broker row, so an acknowledgement cannot introduce money
    the broker never reported. `no_cash_effect` is therefore restricted to
    rows where the broker explicitly reports zero -- it is an assertion
    that there is nothing to journal, not a way to wave money away.
    """
    normalized_treatment = str(treatment).strip().lower()
    if normalized_treatment not in ACKNOWLEDGEMENT_TREATMENTS:
        raise LedgerError(
            f"unsupported treatment {treatment!r}; choose one of "
            + ", ".join(sorted(ACKNOWLEDGEMENT_TREATMENTS))
        )
    operator_name = str(operator).strip()
    reason_text = str(rationale).strip()
    if not operator_name:
        raise LedgerError("an acknowledgement requires the operator's name")
    if not reason_text:
        raise LedgerError("an acknowledgement requires a written rationale")
    if not isinstance(activity, dict) or not activity.get("id"):
        raise LedgerError("broker activity must be an object carrying its id")

    amount = _validate_acknowledged_activity(activity, normalized_treatment)
    _assert_acknowledged_activity_id_not_retyped(
        store,
        treatment=normalized_treatment,
        activity_id=str(activity["id"]),
    )
    details: dict[str, Any] = {}
    if normalized_treatment == "no_cash_effect":
        pass
    else:
        if normalized_treatment == "dividend":
            if not str(ticker or "").strip():
                raise LedgerError("a dividend acknowledgement requires --ticker")
            details["ticker"] = _security_account(str(ticker))[
                len(SECURITY_ACCOUNT_PREFIX) :
            ]
    acknowledged_at = _parse_at(
        now or datetime.now(timezone.utc), "acknowledged_at"
    ).isoformat()
    fingerprint = broker_activity_fingerprint(activity)
    inserted = store.record_broker_activity_acknowledgement(
        activity_id=str(activity["id"]),
        activity_fingerprint=fingerprint,
        treatment=normalized_treatment,
        operator=operator_name,
        rationale=reason_text,
        acknowledged_at=acknowledged_at,
        details=details,
    )
    return {
        "activity_id": str(activity["id"]),
        "treatment": normalized_treatment,
        "activity_fingerprint": fingerprint,
        "inserted": inserted,
        "operator": operator_name,
    }


def _apply_acknowledged_treatment(
    store: AssistantStore,
    activity: dict[str, Any],
    *,
    activity_id: str,
    posted_at: datetime,
) -> tuple[str, bool] | None:
    """Apply a stored operator decision, or None when there is no usable one.

    Raises LedgerError when a decision exists but no longer matches the
    broker row, so a changed provider payload refuses instead of inheriting
    a judgement made about different content.
    """
    acknowledgement = store.get_broker_activity_acknowledgement(activity_id)
    if acknowledgement is None:
        return None
    if acknowledgement["activity_fingerprint"] != broker_activity_fingerprint(
        activity
    ):
        raise LedgerError(
            f"broker activity {activity_id!r} changed since it was "
            "acknowledged; re-review it rather than applying the old decision"
        )
    treatment = acknowledgement["treatment"]
    amount = _validate_acknowledged_activity(activity, treatment)
    _assert_acknowledged_activity_id_not_retyped(
        store, treatment=treatment, activity_id=activity_id
    )
    if treatment == "no_cash_effect":
        return ("no_cash_effect", False)

    assert amount is not None and amount != 0
    description = str(activity.get("description") or "").strip() or (
        f"Operator-acknowledged {treatment}"
    )
    occurred_at = _activity_occurred_at(
        activity,
        activity_type=str(activity.get("activity_type") or "").upper(),
        posted_at=posted_at,
    ).isoformat()
    if treatment == "fee":
        return ("fee", record_fee(
            store,
            external_id=activity_id,
            amount=-amount,
            occurred_at=occurred_at,
            description=description,
        ))
    if treatment == "dividend":
        return ("dividend", record_dividend(
            store,
            external_id=activity_id,
            ticker=acknowledgement["details"]["ticker"],
            gross_amount=amount,
            occurred_at=occurred_at,
            tax_classification="unknown",
        ))
    if treatment == "cash_transfer":
        return ("cash_transfer", record_cash_transfer(
            store,
            external_id=activity_id,
            amount=amount,
            occurred_at=occurred_at,
            description=description,
        ))
    raise LedgerError(f"stored treatment {treatment!r} has no journal mapping")


def sync_broker_activities(
    store: AssistantStore,
    activities: Any,
    *,
    created_after: datetime | None = None,
) -> dict[str, Any]:
    """Journal broker non-trade activities idempotently.

    Handled: FEE, plain DIV (cash dividend, tax classification recorded as
    unknown), and explicit CSD/CSW cash movements. Everything else fails
    closed -- see _HANDLED_ACTIVITY_TYPES for what is deliberately excluded
    and why.

    ``activities`` is the raw list from the broker's account-activities
    feed (execution.alpaca_broker.list_account_activities); passing it in
    keeps this module free of broker imports and the fetch mockable.

    Cutoff semantics: an activity's cash impact happens at its posting
    time, NOT its ``date`` label. Prefer Alpaca's ``created_at`` extension;
    otherwise require the documented exclusive ``after`` query bound.
    The 2026-08
    incident that motivated this sync: a CAT fee dated 08-05 posted at
    08-06T00:06Z, after the 08-05T18:22Z opening snapshot -- so it was
    missing from the journal, while the fees POSTED before bootstrap were
    already baked into opening cash. Filtering on ``date`` would have
    mis-bucketed that fee and double-posted the earlier ones. Activities
    posted at or before the bootstrap instant are therefore skipped, and
    an activity without either supported timestamp shape fails closed.
    """
    bootstrap = store.get_system_state("ledger_bootstrap")
    if not isinstance(bootstrap, dict) or not bootstrap.get("bootstrapped_at"):
        raise LedgerError(
            "bootstrap the portfolio journal before syncing broker activities"
        )
    cutoff = _parse_at(bootstrap["bootstrapped_at"], "ledger bootstrapped_at")
    if created_after is not None:
        if not isinstance(created_after, datetime) or created_after.tzinfo is None:
            raise LedgerError(
                "activity created-after bound must be a timezone-aware datetime"
            )
        if created_after != cutoff:
            raise LedgerError(
                "activity created-after bound must match the ledger bootstrap"
            )
    activity_rows = list(activities)
    types_by_id: dict[str, str] = {}
    for activity in activity_rows:
        if not isinstance(activity, dict) or not activity.get("id"):
            continue
        activity_id = str(activity["id"])
        activity_type = str(activity.get("activity_type") or "").upper()
        previous_type = types_by_id.setdefault(activity_id, activity_type)
        if previous_type != activity_type:
            raise LedgerError(
                f"broker activity id {activity_id!r} appears with conflicting "
                f"activity types {previous_type or '(missing)'} and "
                f"{activity_type or '(missing)'}"
            )
    inserted = 0
    duplicates = 0
    skipped_pre_bootstrap = 0
    trade_activities_skipped = 0
    by_type: dict[str, dict[str, int]] = {}
    by_treatment: dict[str, dict[str, int]] = {}
    acknowledged_no_cash_effect: list[str] = []
    unhandled: list[dict[str, Any]] = []

    def _refuse(activity: Any, reason: str) -> None:
        row = activity if isinstance(activity, dict) else {}
        unhandled.append(
            {
                "id": row.get("id"),
                "activity_type": row.get("activity_type"),
                "net_amount": row.get("net_amount"),
                "date": row.get("date"),
                "reason": reason,
            }
        )

    for activity in activity_rows:
        if not isinstance(activity, dict):
            _refuse(activity, f"activity is not an object: {type(activity).__name__}")
            continue
        activity_type = str(activity.get("activity_type") or "").upper()
        if activity_type in _TRADE_ACTIVITY_TYPES:
            trade_activities_skipped += 1
            continue
        activity_id = activity.get("id")
        if not activity_id:
            _refuse(activity, "activity is missing its broker id")
            continue
        try:
            posted_at = _activity_posted_at(
                activity, created_after=created_after
            )
        except LedgerError as exc:
            _refuse(activity, str(exc))
            continue
        if posted_at <= cutoff:
            # Every pre-bootstrap non-trade activity is already inside the
            # opening snapshot, including types this sync does not yet know
            # how to journal after bootstrap.
            skipped_pre_bootstrap += 1
            continue
        # An operator decision, if one exists for this exact row, is what
        # lets an unsupported type stop blocking evidence capture without a
        # code deploy. It is consulted only AFTER the pre-bootstrap cutoff,
        # so an acknowledgement can never resurrect opening-balance activity.
        def _try_acknowledged(refusal_reason: str) -> None:
            nonlocal inserted, duplicates
            try:
                applied = _apply_acknowledged_treatment(
                    store,
                    activity,
                    activity_id=str(activity_id),
                    posted_at=posted_at,
                )
            except LedgerError as ack_error:
                _refuse(activity, str(ack_error))
                return
            if applied is None:
                _refuse(activity, refusal_reason)
                return
            treatment, newly = applied
            counts = by_treatment.setdefault(
                treatment, {"inserted": 0, "duplicates": 0}
            )
            if treatment == "no_cash_effect":
                acknowledged_no_cash_effect.append(str(activity_id))
            elif newly:
                inserted += 1
                counts["inserted"] += 1
            else:
                duplicates += 1
                counts["duplicates"] += 1

        if activity_type not in _HANDLED_ACTIVITY_TYPES:
            _try_acknowledged(
                f"unhandled activity type {activity_type or '(missing)'}"
            )
            continue
        raw_status = activity.get("status")
        status = str(raw_status or "").lower()
        if raw_status is not None and status != "executed":
            _refuse(activity, f"activity status is {status or '(empty)'}, not executed")
            continue
        try:
            net_amount = _decimal(activity.get("net_amount"), "activity net_amount")
        except LedgerError:
            _refuse(activity, "activity net_amount is missing or not numeric")
            continue
        try:
            newly_inserted = _post_broker_activity(
                store,
                activity=activity,
                activity_type=activity_type,
                activity_id=str(activity_id),
                net_amount=net_amount,
                posted_at=posted_at,
            )
        except LedgerError as exc:
            # A handled type can still be refused on its own terms (an
            # unsupported DIV subtype, a wrong sign). An operator decision
            # covers that case too -- CR-W3's first real dividend is exactly
            # this shape.
            _try_acknowledged(str(exc))
            continue
        type_counts = by_type.setdefault(
            activity_type, {"inserted": 0, "duplicates": 0}
        )
        if newly_inserted:
            inserted += 1
            type_counts["inserted"] += 1
        else:
            duplicates += 1
            type_counts["duplicates"] += 1

    if unhandled:
        # Recognized fees above are already journaled (each idempotently),
        # so raising here loses no work; it blocks evidence capture until
        # support for the listed activity types is deliberately added.
        raise BrokerActivityReviewRequiredError(unhandled)
    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "by_type": by_type,
        "by_acknowledged_treatment": by_treatment,
        "acknowledged_no_cash_effect": sorted(acknowledged_no_cash_effect),
        "skipped_pre_bootstrap": skipped_pre_bootstrap,
        "trade_activities_skipped": trade_activities_skipped,
        # A successful report has classified every input row. In particular,
        # a no-cash-effect acknowledgement is still an activity that was
        # examined even though it intentionally creates no posting.
        "activities_seen": len(activity_rows),
    }


def preview_broker_activities(
    store: AssistantStore,
    activities: Any,
    *,
    created_after: datetime | None = None,
) -> dict[str, Any]:
    """Run the exact sync against a disposable snapshot of ``store``.

    This is the read-only review path: validation, existing-journal conflicts,
    and stored acknowledgements are identical to a real sync, while every
    prospective posting lands only in a temporary verified SQLite copy.
    """
    activity_rows = list(activities)
    with TemporaryDirectory(prefix="broker-activity-review-") as directory:
        snapshot_path = store.snapshot_to(Path(directory) / "review.db")
        shadow = AssistantStore(snapshot_path)
        try:
            report = sync_broker_activities(
                shadow, activity_rows, created_after=created_after
            )
        except BrokerActivityReviewRequiredError as exc:
            return {
                "refused": [dict(activity) for activity in exc.activities],
                "refused_count": len(exc.activities),
            }
    return {"refused": [], "refused_count": 0, "would_apply": report}


def alpaca_account_binding_block_reason(
    store: AssistantStore,
    snapshot: Any,
    *,
    allow_unbound_alpaca: bool = False,
) -> str | None:
    """Stable binding-block code, or None when the snapshot may bind.

    Codes:
      - ``unbound_journal``: Alpaca journal exists but predates account-ID binding
      - ``account_mismatch``: snapshot account differs from the bound account
      - ``missing_account_id``: Alpaca snapshot carries no account ID

    ``reconcile_snapshot`` and tax-report coverage both consume this helper
    so the accountant-facing report cannot drift from the ledger gate.
    """
    bootstrap = store.get_system_state("ledger_bootstrap")
    snapshot_account = str(getattr(snapshot, "account_id", None) or "").strip()
    source = getattr(snapshot, "source", None)
    if isinstance(bootstrap, dict) and bootstrap.get("source") == "alpaca":
        bound_account = str(bootstrap.get("account_id") or "").strip()
        if not bound_account and not allow_unbound_alpaca:
            return "unbound_journal"
        if bound_account and snapshot_account != bound_account:
            return "account_mismatch"
    elif source == "alpaca" and not snapshot_account:
        return "missing_account_id"
    return None


_BINDING_LEDGER_ERRORS = {
    "unbound_journal": (
        "The existing Alpaca journal predates account-ID binding. "
        "Run ledger-bind-account to migrate it only after verifying "
        "the connected broker account."
    ),
    "account_mismatch": (
        "Connected Alpaca account does not match the account bound "
        "to the portfolio journal."
    ),
    "missing_account_id": (
        "Alpaca reconciliation requires the connected broker account ID"
    ),
}


def reconcile_snapshot(
    store: AssistantStore,
    snapshot: PortfolioSnapshot,
    *,
    source: str | None = None,
    now: datetime | None = None,
    _allow_unbound_alpaca: bool = False,
) -> dict[str, Any]:
    reconciled_at = now or datetime.now(timezone.utc)
    if reconciled_at.tzinfo is None:
        raise LedgerError("reconciliation time must be timezone-aware")
    binding_block = alpaca_account_binding_block_reason(
        store, snapshot, allow_unbound_alpaca=_allow_unbound_alpaca
    )
    if binding_block is not None:
        raise LedgerError(_BINDING_LEDGER_ERRORS[binding_block])
    balances = ledger_balances(store)
    ledger_cash = balances["cash"]
    broker_cash = _decimal(snapshot.cash, "snapshot.cash")
    mismatches: list[dict[str, Any]] = []
    cash_difference = ledger_cash - broker_cash
    if abs(cash_difference) > CASH_TOLERANCE:
        mismatches.append(
            {
                "kind": "cash",
                "ledger": _decimal_text(ledger_cash),
                "broker": _decimal_text(broker_cash),
                "difference": _decimal_text(cash_difference),
            }
        )

    broker_shares = {
        position.ticker.upper(): _decimal(
            position.shares, f"{position.ticker}.shares"
        )
        for position in snapshot.positions
    }
    ledger_shares = balances["shares"]
    for ticker in sorted(set(broker_shares) | set(ledger_shares)):
        ledger_qty = ledger_shares.get(ticker, Decimal("0"))
        broker_qty = broker_shares.get(ticker, Decimal("0"))
        difference = ledger_qty - broker_qty
        if abs(difference) > SHARE_TOLERANCE:
            mismatch: dict[str, Any] = {
                "kind": "position",
                "ticker": ticker,
                "ledger": _decimal_text(ledger_qty),
                "broker": _decimal_text(broker_qty),
                "difference": _decimal_text(difference),
            }
            # GR-4: a share count that multiplied by a near-integer ratio
            # is split-shaped -- name it, so the operator confirms a split
            # in the journal instead of chasing a phantom fill. Detection
            # by share-count reconciliation only; the mismatch still
            # counts as a mismatch (fail-closed) until the split is
            # CONFIRMED as a journal action.
            from assistant.share_reconciliation import (
                detect_split_like_share_mismatch,
            )

            suspicion = detect_split_like_share_mismatch(ledger_qty, broker_qty)
            if suspicion is not None:
                mismatch["suspected_split"] = suspicion
            mismatches.append(mismatch)

    report = {
        "reconciliation_id": "recon-" + uuid.uuid4().hex,
        "reconciled_at": reconciled_at.isoformat(),
        "source": source or snapshot.source,
        "matched": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "ledger": {
            "cash": _decimal_text(ledger_cash),
            "shares": {
                ticker: _decimal_text(qty)
                for ticker, qty in sorted(ledger_shares.items())
                if abs(qty) > SHARE_TOLERANCE
            },
            "transaction_count": balances["transaction_count"],
            "posting_count": balances["posting_count"],
        },
        "broker": {
            "cash": _decimal_text(broker_cash),
            "shares": {
                ticker: _decimal_text(qty)
                for ticker, qty in sorted(broker_shares.items())
                if abs(qty) > SHARE_TOLERANCE
            },
            "snapshot_as_of": snapshot.as_of,
            "account_mode": snapshot.account_mode,
            "account_id": snapshot.account_id,
        },
        "tolerances": {
            "cash": _decimal_text(CASH_TOLERANCE),
            "shares": _decimal_text(SHARE_TOLERANCE),
        },
    }
    store.record_ledger_reconciliation(
        report["reconciliation_id"], report["source"], report
    )
    return report


def bind_legacy_alpaca_account(
    store: AssistantStore,
    snapshot: PortfolioSnapshot,
    *,
    confirmation: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Bind a pre-account-ID Alpaca journal after an exact reconciliation."""
    if str(confirmation).strip().lower() != "bind account":
        raise LedgerError(
            'legacy account binding requires confirmation "bind account"'
        )
    bootstrap = store.get_system_state("ledger_bootstrap")
    if not isinstance(bootstrap, dict) or bootstrap.get("source") != "alpaca":
        raise LedgerError(
            "legacy account binding requires an existing Alpaca bootstrap"
        )
    account_id = str(snapshot.account_id or "").strip()
    if snapshot.source != "alpaca" or not account_id:
        raise LedgerError(
            "legacy account binding requires an identified Alpaca snapshot"
        )
    expected_mode = str(bootstrap.get("account_mode") or "").strip()
    if expected_mode and snapshot.account_mode != expected_mode:
        raise LedgerError(
            "connected Alpaca account mode does not match the journal "
            f"bootstrap ({snapshot.account_mode!r} vs {expected_mode!r})"
        )
    existing = str(bootstrap.get("account_id") or "").strip()
    if existing:
        if existing != account_id:
            raise LedgerError(
                "journal is already bound to a different Alpaca account"
            )
        return {
            "bound": True,
            "already_bound": True,
            "account_id": existing,
        }

    report = reconcile_snapshot(
        store,
        snapshot,
        now=now,
        _allow_unbound_alpaca=True,
    )
    if not report["matched"]:
        raise LedgerError(
            "refusing to bind the legacy journal because cash/positions do "
            "not reconcile within the journal's strict cash/share "
            "tolerances with the connected Alpaca account"
        )
    bound_at = (now or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )
    migrated = dict(bootstrap)
    migrated.update(
        {
            "account_id": account_id,
            "account_bound_at": bound_at.isoformat(),
            "account_binding_method": "exact_ledger_reconciliation",
            "account_binding_reconciliation_id": report[
                "reconciliation_id"
            ],
        }
    )
    store.set_system_state("ledger_bootstrap", migrated)
    return {
        "bound": True,
        "already_bound": False,
        "account_id": account_id,
        "account_bound_at": bound_at.isoformat(),
        "reconciliation_id": report["reconciliation_id"],
    }
