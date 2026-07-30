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
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore

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
    return store.append_journal_transaction(
        transaction_id=transaction.transaction_id,
        occurred_at=transaction.occurred_at,
        source=transaction.source,
        external_id=transaction.external_id,
        description=transaction.description,
        postings=[posting.to_dict() for posting in transaction.postings],
        metadata=transaction.metadata,
    )


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
    inserted = post_transaction(store, transaction)
    if not inserted:
        raise LedgerError("opening snapshot already exists")
    state = {
        "bootstrapped_at": occurred.isoformat(),
        "snapshot_as_of": snapshot.as_of,
        "source": snapshot.source,
        "account_mode": snapshot.account_mode,
        "snapshot_hash": digest,
    }
    store.set_system_state("ledger_bootstrap", state)
    return state


def _transaction_id(external_id: str) -> str:
    digest = hashlib.sha256(external_id.encode("utf-8")).hexdigest()
    return "journal-" + digest[:24]


def _fill_transaction(
    *,
    fill: dict[str, Any],
    balances: dict[str, Any],
) -> JournalTransaction:
    ticker = str(fill["ticker"]).upper()
    side = str(fill["side"]).lower()
    qty = _decimal(fill["qty"], "fill.qty")
    price = _decimal(fill["price"], "fill.price")
    if side not in ("buy", "sell") or qty <= 0 or price <= 0:
        raise LedgerError(f"invalid fill: {fill!r}")
    occurred_at = _parse_at(fill["at"], "fill.at").isoformat()
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

    fill_id = str(fill["fill_id"])
    external_id = f"app_fill:{fill_id}"
    return JournalTransaction(
        transaction_id=_transaction_id(external_id),
        occurred_at=occurred_at,
        source="assistant_broker_event",
        external_id=external_id,
        description=f"{side.upper()} {qty} {ticker} @ {price}",
        postings=postings,
        metadata={
            "fill_id": fill_id,
            "order_id": fill.get("order_id"),
            "proposal_id": fill.get("proposal_id"),
            "ticker": ticker,
            "side": side,
            "qty": _decimal_text(qty),
            "price": _decimal_text(price),
            "fees_included": False,
        },
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
) -> bool:
    amount = _decimal(gross_amount, "gross_amount")
    if amount <= 0:
        raise LedgerError("gross dividend must be positive")
    transaction = JournalTransaction(
        transaction_id=_transaction_id(f"dividend:{external_id}"),
        occurred_at=_parse_at(occurred_at).isoformat(),
        source="corporate_action",
        external_id=f"dividend:{external_id}",
        description=f"Cash dividend for {ticker.upper()}",
        postings=(
            Posting(ACCOUNT_CASH, amount),
            Posting(
                ACCOUNT_DIVIDEND_INCOME,
                -amount,
                metadata={"ticker": ticker.upper()},
            ),
        ),
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


def reconcile_snapshot(
    store: AssistantStore,
    snapshot: PortfolioSnapshot,
    *,
    source: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    reconciled_at = now or datetime.now(timezone.utc)
    if reconciled_at.tzinfo is None:
        raise LedgerError("reconciliation time must be timezone-aware")
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
            mismatches.append(
                {
                    "kind": "position",
                    "ticker": ticker,
                    "ledger": _decimal_text(ledger_qty),
                    "broker": _decimal_text(broker_qty),
                    "difference": _decimal_text(difference),
                }
            )

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
