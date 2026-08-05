"""Confirmed corporate actions for journal-aware tax-lot replay.

Reference feeds can discover a possible dividend or split, but they are not
authoritative evidence that this account received cash or shares. This module
therefore consumes only actions already confirmed in the append-only journal.
Discovery in ``data.corporate_actions`` never mutates accounting state.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from assistant.performance import Distribution
from assistant.portfolio_ledger import (
    ACCOUNT_DIVIDEND_INCOME,
    SECURITY_ACCOUNT_PREFIX,
)
from assistant.storage import AssistantStore
from assistant.tax_lots import Fill, LotEvent, Split, TaxLotError, build_ledger

_EASTERN = ZoneInfo("America/New_York")


def _parse_at(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(
            f"corporate-action timestamp must be timezone-aware: {value!r}"
        )
    return parsed


def _parse_ex_at(value: object) -> datetime:
    """Interpret a date-only ex-date at the start of its US market day."""
    text = str(value)
    try:
        parsed_date = date.fromisoformat(text)
    except ValueError:
        return _parse_at(value)
    return datetime.combine(parsed_date, time.min, tzinfo=_EASTERN)


def detect_split_like_share_mismatch(
    recorded_shares: Decimal | int | str,
    broker_shares: Decimal | int | str,
    *,
    relative_tolerance: Decimal = Decimal("0.01"),
) -> dict[str, Any] | None:
    """GR-4: classify a share-count mismatch as split-shaped, by ratio.

    A split between snapshot and submit must be DETECTED from share-count
    reconciliation, never inferred from a price jump (a price can jump for
    a hundred reasons; a share count multiplying by a near-integer ratio
    has essentially one). Returns None when the counts match or the
    mismatch is not split-shaped; otherwise a description like
    ``{"ratio": "10:1", "direction": "forward"}`` (forward = broker now
    holds MORE shares, e.g. 10-for-1) for the reconciliation report to
    carry. Pure classification: it never mutates accounting state --
    confirming a split remains a journal action, exactly as this module's
    docstring requires.
    """
    recorded = Decimal(str(recorded_shares))
    broker = Decimal(str(broker_shares))
    if recorded <= 0 or broker <= 0 or recorded == broker:
        return None
    larger, smaller, direction = (
        (broker, recorded, "forward")
        if broker > recorded
        else ((recorded, broker, "reverse"))
    )
    ratio = larger / smaller
    nearest = ratio.to_integral_value()
    if nearest < 2:
        return None
    if abs(ratio - nearest) > nearest * relative_tolerance:
        return None
    return {
        "ratio": f"{int(nearest)}:1",
        "direction": direction,
        "recorded_shares": str(recorded),
        "broker_shares": str(broker),
    }


def confirmed_distributions(
    store: AssistantStore,
    *,
    ticker: str | None = None,
) -> tuple[list[Distribution], list[dict[str, str]]]:
    """Return performance-ready dividends confirmed by the account journal.

    Older journal records may contain only a gross cash amount. Those remain
    valid accounting entries, but cannot be used for per-share asset return;
    they are reported as unavailable rather than reverse-engineered.
    """
    normalized_ticker = str(ticker).strip().upper() if ticker else None
    result: list[Distribution] = []
    unavailable: list[dict[str, str]] = []
    seen_transactions: set[str] = set()
    for posting in store.list_journal_postings():
        transaction_id = str(posting["transaction_id"])
        if (
            posting.get("source") != "corporate_action"
            or posting.get("account") != ACCOUNT_DIVIDEND_INCOME
            or transaction_id in seen_transactions
        ):
            continue
        seen_transactions.add(transaction_id)
        metadata = posting.get("metadata") or {}
        action_ticker = str(metadata.get("ticker") or "").upper()
        if normalized_ticker and action_ticker != normalized_ticker:
            continue
        if not action_ticker:
            unavailable.append(
                {
                    "external_id": str(posting.get("external_id") or ""),
                    "reason": "confirmed dividend is missing ticker metadata",
                }
            )
            continue
        if not metadata.get("ex_date") or not metadata.get("amount_per_share"):
            unavailable.append(
                {
                    "external_id": str(posting.get("external_id") or ""),
                    "ticker": action_ticker,
                    "reason": (
                        "confirmed dividend lacks ex_date or amount_per_share"
                    ),
                }
            )
            continue
        try:
            per_share = float(Decimal(str(metadata["amount_per_share"])))
            gross_cash = float(abs(Decimal(str(posting["amount"]))))
            result.append(
                Distribution(
                    ticker=action_ticker,
                    ex_at=_parse_ex_at(metadata["ex_date"]),
                    amount_per_share=per_share,
                    paid_at=_parse_at(posting["occurred_at"]),
                    cash_amount=gross_cash,
                    tax_classification=str(
                        metadata.get("tax_classification") or "unknown"
                    ),
                )
            )
        except (ValueError, KeyError) as exc:
            unavailable.append(
                {
                    "external_id": str(posting.get("external_id") or ""),
                    "ticker": action_ticker,
                    "reason": f"invalid confirmed dividend metadata: {exc}",
                }
            )
    return sorted(result, key=lambda item: (item.ex_at, item.ticker)), unavailable


def confirmed_splits(store: AssistantStore) -> list[Split]:
    """Rebuild confirmed split events from quantity-only journal postings."""
    result: list[Split] = []
    seen_transactions: set[str] = set()
    for posting in store.list_journal_postings():
        metadata = posting.get("metadata") or {}
        if (
            posting.get("source") != "corporate_action"
            or metadata.get("corporate_action") != "split"
            or posting["transaction_id"] in seen_transactions
        ):
            continue
        account = str(posting.get("account") or "")
        if not account.startswith(SECURITY_ACCOUNT_PREFIX):
            continue
        result.append(
            Split(
                ticker=account[len(SECURITY_ACCOUNT_PREFIX) :],
                ratio=float(Decimal(str(metadata["ratio"]))),
                at=_parse_at(posting["occurred_at"]),
                action_id=str(posting["external_id"]),
            )
        )
        seen_transactions.add(posting["transaction_id"])
    return sorted(result, key=lambda action: (action.at, action.action_id))


def fills_with_confirmed_splits(store: AssistantStore) -> list[LotEvent]:
    events: list[LotEvent] = [
        Fill(
            ticker=fill["ticker"],
            side=fill["side"],
            qty=fill["qty"],
            price=fill["price"],
            at=_parse_at(fill["at"]),
            fill_id=fill["fill_id"],
        )
        for fill in store.list_fills()
    ]
    events.extend(confirmed_splits(store))
    return sorted(
        events,
        key=lambda event: (
            event.at,
            event.fill_id if isinstance(event, Fill) else event.action_id,
        ),
    )


def tax_ledger_with_coverage(
    store: AssistantStore, portfolio: Any
) -> tuple[Any | None, dict[str, Any]]:
    """Build a ledger only when app events cover every current share.

    Missing pre-app/imported fills are common. Returning a partial tax result
    as complete would be worse than returning none, so proposal generation
    receives an explicit coverage report and remains non-blocking.
    """
    try:
        ledger = build_ledger(fills_with_confirmed_splits(store))
    except (TaxLotError, ValueError, KeyError) as exc:
        return None, {
            "complete": False,
            "reason": str(exc),
            "tickers": {},
        }

    details: dict[str, dict[str, Any]] = {}
    complete = True
    portfolio_tickers = {
        position.ticker.upper() for position in portfolio.positions
    }
    lot_tickers = {lot.ticker for lot in ledger.open_lots}
    for ticker in sorted(portfolio_tickers | lot_tickers):
        broker_shares = sum(
            (
                Decimal(str(position.shares))
                for position in portfolio.positions
                if position.ticker.upper() == ticker
            ),
            Decimal("0"),
        )
        ledger_shares = Decimal(str(ledger.shares_held(ticker)))
        matched = (
            abs(broker_shares - ledger_shares) <= Decimal("0.00000001")
        )
        details[ticker] = {
            "broker_shares": str(broker_shares),
            "ledger_shares": str(ledger_shares),
            "matched": matched,
        }
        complete = complete and matched
    return (
        ledger if complete else None,
        {
            "complete": complete,
            "reason": (
                None
                if complete
                else "tax-lot shares do not match the portfolio snapshot"
            ),
            "tickers": details,
        },
    )
