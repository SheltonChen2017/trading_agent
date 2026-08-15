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

from assistant.money import to_decimal
from assistant.performance import Distribution
from assistant.share_reconciliation import detect_split_like_share_mismatch
from assistant.portfolio_ledger import (
    ACCOUNT_DIVIDEND_INCOME,
    SECURITY_ACCOUNT_PREFIX,
    SHARE_TOLERANCE,
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
            # to_decimal, not Decimal(str(...)): a malformed value raises
            # decimal.InvalidOperation, which is an ArithmeticError and so
            # escapes the `except (ValueError, KeyError)` below -- turning
            # this module's documented "reported as unavailable" contract
            # into an uncaught traceback in the UI and CLI callers of
            # tax_ledger_with_coverage(). to_decimal normalizes that to
            # ValueError and additionally rejects NaN/Infinity, which are
            # legal Decimal literals.
            per_share = float(
                to_decimal(metadata["amount_per_share"], name="amount_per_share")
            )
            gross_cash = float(
                abs(to_decimal(posting["amount"], name="dividend amount"))
            )
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
        # A malformed ratio must NOT be skipped: dropping a split silently
        # would leave every later share count and cost basis wrong. Raising
        # is the fail-closed direction -- tax_ledger_with_coverage() catches
        # ValueError and reports the ledger as incomplete, which is exactly
        # the designed degradation. to_decimal also folds the missing-key
        # case into the same ValueError instead of a bare KeyError.
        result.append(
            Split(
                ticker=account[len(SECURITY_ACCOUNT_PREFIX) :],
                ratio=float(
                    to_decimal(
                        metadata.get("ratio"),
                        name=f"split ratio for {posting['external_id']}",
                    )
                ),
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


def ticker_tax_ledger_with_coverage(
    store: AssistantStore, portfolio: Any, ticker: str
) -> tuple[Any | None, dict[str, Any]]:
    """Build a ledger when app events cover ONE ticker's current shares.

    A deliberate sibling of `tax_ledger_with_coverage` rather than a
    loosening of it. That function answers "can this whole book be taxed
    accurately?" and correctly withholds the ledger entirely when any
    holding is unreconciled, because a portfolio-wide tax report built from
    partial history would understate reality.

    REBAL-1 Stage 3 asks a narrower question: a trim sells ONE ticker, and
    its realized gain depends on that ticker's lots and nothing else. Under
    the portfolio-wide rule the feature could never propose anything, because
    `AssistantStore.list_fills` documents that positions "bought before the
    app existed, or through the Alpaca UI, produce no events and therefore no
    lots" -- so one pre-app holding anywhere withheld the ledger forever. A
    gate that always refuses is indistinguishable from a careful safeguard,
    which is how that defect stayed hidden through two review rounds.

    The returned coverage keeps the same shape as its sibling so callers can
    read it identically, with `complete` scoped to the requested ticker and
    `portfolio_complete` reporting the book-wide answer for disclosure.
    """
    name = str(ticker).strip().upper()
    if not name:
        return None, {"complete": False, "reason": "no ticker", "tickers": {}}

    ledger, coverage = tax_ledger_with_coverage(store, portfolio)
    details = coverage.get("tickers") or {}
    matched = bool((details.get(name) or {}).get("matched"))
    scoped = {
        "complete": matched,
        "portfolio_complete": coverage.get("complete") is True,
        "reason": (
            None if matched
            else (details.get(name) or {}).get("reason")
            or f"app fill history does not cover the current {name} position"
        ),
        "tickers": details,
    }
    if not matched:
        return None, scoped
    if ledger is not None:
        return ledger, scoped
    # The sibling withheld the ledger because some OTHER holding is
    # unreconciled. Rebuild it here: the same fills, read for one ticker
    # whose own shares do reconcile.
    try:
        return build_ledger(fills_with_confirmed_splits(store)), scoped
    except (TaxLotError, ValueError, KeyError) as exc:
        return None, {**scoped, "complete": False, "reason": str(exc)}

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
        # Same InvalidOperation escape class as FPS-001: raw Decimal(str(...))
        # raises ArithmeticError, which this function does not catch. Shares
        # are normally floats from the broker snapshot, but a corrupt or
        # hand-built portfolio must degrade to incomplete coverage — not a
        # traceback in the Reports page.
        try:
            broker_shares = sum(
                (
                    to_decimal(
                        position.shares, name=f"{ticker} broker shares"
                    )
                    for position in portfolio.positions
                    if position.ticker.upper() == ticker
                ),
                Decimal("0"),
            )
            ledger_shares = to_decimal(
                ledger.shares_held(ticker), name=f"{ticker} ledger shares"
            )
        except ValueError as exc:
            return None, {
                "complete": False,
                "reason": str(exc),
                "tickers": details,
            }
        # SHARE_TOLERANCE, not a bare literal: portfolio_ledger owns this
        # rule and PUBLISHES its value into the durable reconciliation record
        # ("tolerances.shares"). A local copy means tuning the constant --
        # e.g. for fractional shares -- would silently move ledger
        # reconciliation while leaving this coverage gate on the old value,
        # so the tax surface would disagree with the record that declares the
        # tolerance.
        matched = abs(broker_shares - ledger_shares) <= SHARE_TOLERANCE
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
