"""Three-sleeve engine M2: threshold notifications (durable, batched).

THREE_SLEEVE_ENGINE_PLAN section 5, M2, against revision 2 of the rule.
Crossings become WARNING-severity operational alerts, which GR-5 routes to
the daily briefing batch (never a toast): `pending_briefing_alerts` is the
delivery surface, exactly like every other warning in this platform.

THE ANTI-NAG INVARIANT, AND WHY STATE IS REQUIRED AT ALL
--------------------------------------------------------
`upsert_operational_alert` re-OPENS an acknowledged alert on every upsert
(its ON CONFLICT clause resets `acknowledged_at`). Re-evaluating thresholds
daily and upserting unconditionally would therefore un-acknowledge the same
crossing every morning -- precisely the "re-notify daily while waiting" the
plan forbids. So this module keeps one durable row per (watch_key, kind)
and upserts an alert ONLY on an inactive->active transition:

* first crossing        -> one alert;
* still crossed next day -> silence (state already active);
* condition clears       -> state flips inactive, still silence;
* crosses AGAIN later    -> genuine new event -> the same fingerprint is
  re-upserted, re-opening the alert with occurrences+1.

Watch kinds, all observational:

* ``gain_review``          -- lot crossed the long-term-gated gain review;
* ``awaiting_long_term``   -- lot met the price threshold but the gate
  holds; notified once with the countdown, then silent while waiting;
* ``decline_review``       -- lot at or below the decline threshold;
* ``reentry_decline``      -- resolved decision #3: a growth candidate with
  no open lots whose price has fallen to the decline threshold measured
  from its LAST DISPOSAL FILL price (from the append-only journal -- the
  price recorded at sale time, not the original basis);
* ``coverage_lost``        -- a lot this module was tracking disappeared
  while its position's lot coverage is broken; the plan requires that to
  surface as "coverage lost", never as silence.

A tracked lot that disappears while its position still has healthy
coverage was DISPOSED (its shares were sold); that is normal life, drops
the lot's rows, and feeds the re-entry watch through the journal's sell
fill rather than through an alert.

Failure isolation: the caller (the briefing command) wraps the whole cycle;
this module must never be the reason a briefing, a warning render, or a
risk-reducing proposal fails. Re-entry watching needs a price for tickers
the portfolio does NOT hold, which is a provider fetch; it goes through
GR-4's ``fetch_daily_bars_recorded`` so the fetch is lineage-recorded and
streak-alerted, and an unavailable price degrades to an explicit note --
never to a silently skipped watch.

Everything here is notification about the owner's stated preference.
Nothing creates, sizes, approves, submits, or cancels anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping

import config
from assistant.money import decimal_text, to_decimal
from assistant.storage import AssistantStore

WARNING_SEVERITY = "warning"
ALERT_CATEGORY = "sleeve_engine"

GAIN_REVIEW = "gain_review"
AWAITING_LONG_TERM = "awaiting_long_term"
DECLINE_REVIEW = "decline_review"
REENTRY_DECLINE = "reentry_decline"
COVERAGE_LOST = "coverage_lost"

_LOT_KINDS = (GAIN_REVIEW, AWAITING_LONG_TERM, DECLINE_REVIEW)

# Coverage values under which a vanished lot means "we can no longer see",
# as opposed to "it was sold". Partial coverage explicitly says the journal
# cannot account for all broker-held shares, so it cannot prove that a
# vanished tracked lot was disposed either.
_BROKEN_COVERAGE = ("none", "partial", "unavailable")


def alert_fingerprint(kind: str, watch_key: str) -> str:
    return f"sleeve:{kind}:{watch_key}"


@dataclass(frozen=True)
class Activation:
    """One inactive->active transition, ready to become a batched warning."""

    kind: str
    watch_key: str
    ticker: str
    message: str
    details: dict[str, Any]


@dataclass
class WatchEvaluation:
    activations: list[Activation] = field(default_factory=list)
    states: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _lot_states(lot: Mapping[str, Any]) -> dict[str, bool]:
    return {
        GAIN_REVIEW: bool(lot["crossed_gain_review_threshold"]),
        AWAITING_LONG_TERM: bool(lot["gain_threshold_met_awaiting_long_term"]),
        DECLINE_REVIEW: bool(lot["crossed_decline_review_threshold"]),
    }


def _lot_message(kind: str, ticker: str, lot: Mapping[str, Any], engine: Mapping[str, Any]) -> str:
    pct = lot["unrealized_pnl_pct"]
    money = to_decimal(lot["unrealized_pnl_money"], name="unrealized lot gain")
    money_display = f"${money:,.2f}"
    if kind == GAIN_REVIEW:
        return (
            f"{ticker} lot {lot['lot_id']} is {pct:+.2f}% "
            f"({money_display}) and long-term "
            f"(gain review; recorded trim fraction "
            f"{engine['gain_review_trim_fraction']}). Long-term since "
            f"{lot['first_long_term_date']}."
        )
    if kind == AWAITING_LONG_TERM:
        return (
            f"{ticker} lot {lot['lot_id']} is {pct:+.2f}% "
            f"({money_display}), above the gain "
            f"threshold but short-term; the gate holds for "
            f"{lot['days_to_long_term']} more day(s) (long-term on "
            f"{lot['first_long_term_date']})."
        )
    return (
        f"{ticker} lot {lot['lot_id']} is {pct:+.2f}%, at or below the "
        f"decline-review threshold "
        f"({engine['decline_review_threshold_pct']}%)."
    )


def evaluate_watch_transitions(
    report: Mapping[str, Any],
    *,
    prior_states: Iterable[Mapping[str, Any]],
    reentry_references: Mapping[str, Decimal],
    reentry_prices: Mapping[str, Decimal],
    now_iso: str,
) -> WatchEvaluation:
    """Pure transition evaluation: (report, prior state) -> (alerts, state).

    ``reentry_references`` maps a flat growth ticker to its last disposal
    fill price; ``reentry_prices`` maps tickers to a current price. A
    reference without a price yields a NOTE, an unchanged prior state for
    that watch, and no activation -- unavailable data must never read as
    "not crossed".
    """
    engine = report["engine"]
    decline_threshold = to_decimal(
        engine["decline_review_threshold_pct"], name="decline threshold"
    )
    prior_active: dict[tuple[str, str], Mapping[str, Any]] = {
        (row["watch_key"], row["kind"]): row for row in prior_states
    }
    result = WatchEvaluation()
    seen: set[tuple[str, str]] = set()

    def emit(
        watch_key: str,
        kind: str,
        ticker: str,
        active: bool,
        message_fn: Callable[[], tuple[str, dict[str, Any]]],
    ) -> None:
        key = (watch_key, kind)
        seen.add(key)
        prior = prior_active.get(key)
        was_active = bool(prior and prior["active"])
        first_active_at = prior.get("first_active_at") if prior else None
        details: dict[str, Any] = dict(prior.get("details", {})) if prior else {}
        if active and not was_active:
            message, details = message_fn()
            result.activations.append(
                Activation(
                    kind=kind,
                    watch_key=watch_key,
                    ticker=ticker,
                    message=message,
                    details=details,
                )
            )
            first_active_at = now_iso
        result.states.append(
            {
                "watch_key": watch_key,
                "kind": kind,
                "ticker": ticker,
                "active": active,
                "first_active_at": first_active_at if active else None,
                "last_transition_at": (
                    now_iso if active != was_active else (
                        prior.get("last_transition_at", now_iso) if prior else now_iso
                    )
                ),
                "last_evaluated_at": now_iso,
                "details": details,
            }
        )

    current_lot_keys: set[str] = set()
    coverage_by_ticker: dict[str, str] = {}
    for position in report["growth_sleeve"]["positions"]:
        ticker = position["ticker"]
        coverage_by_ticker[ticker] = position["lot_coverage"]
        for lot in position["lots"]:
            lot_key = str(lot["lot_id"])
            current_lot_keys.add(lot_key)
            for kind, active in _lot_states(lot).items():
                emit(
                    lot_key,
                    kind,
                    ticker,
                    active,
                    lambda k=kind, t=ticker, l=lot: (
                        _lot_message(k, t, l, engine),
                        {
                            "unrealized_pnl_money": l["unrealized_pnl_money"],
                            "unrealized_pnl_pct": l["unrealized_pnl_pct"],
                            "term_if_sold_now": l["term_if_sold_now"],
                            "days_to_long_term": l["days_to_long_term"],
                            "first_long_term_date": l["first_long_term_date"],
                        },
                    ),
                )

    # Vanished lots: coverage-lost vs ordinary disposal. A lot carries one
    # state row per kind, so dedupe to unique lot keys FIRST -- otherwise a
    # single blind lot would alert once per kind row.
    vanished: dict[str, str] = {}
    for (watch_key, kind), prior in prior_active.items():
        if kind in _LOT_KINDS and watch_key not in current_lot_keys:
            vanished.setdefault(watch_key, prior["ticker"])
    for watch_key, ticker in sorted(vanished.items()):
        coverage = coverage_by_ticker.get(ticker)
        if coverage in _BROKEN_COVERAGE:
            emit(
                watch_key,
                COVERAGE_LOST,
                ticker,
                True,
                lambda t=ticker, w=watch_key, c=coverage: (
                    (
                        f"{t} lot {w} can no longer be threshold-reviewed: "
                        f"lot coverage is now {c}. Not silence -- the watch "
                        "is blind, which is different from nothing "
                        "happening."
                    ),
                    {"lot_coverage": c},
                ),
            )
        # Disposed or blind either way, the per-lot threshold rows end here:
        # emitting nothing for (watch_key, lot kind) drops the row, because
        # save_sleeve_watch_states replaces the whole set.

    # Standing coverage_lost rows: stay active while the ticker's coverage
    # is still broken (silent -- already notified), flip inactive when
    # coverage heals (no alert; recovery is visible in the report), and
    # RE-activate with a fresh alert if coverage breaks again later --
    # by then the per-lot threshold rows are long dropped, so this loop is
    # the only place that can see the re-break.
    for (watch_key, kind), prior in prior_active.items():
        if kind != COVERAGE_LOST or (watch_key, kind) in seen:
            continue
        ticker = prior["ticker"]
        coverage = coverage_by_ticker.get(ticker)
        still_broken = coverage in _BROKEN_COVERAGE
        emit(
            watch_key,
            COVERAGE_LOST,
            ticker,
            bool(still_broken),
            lambda t=ticker, w=watch_key, c=coverage: (
                (
                    f"{t} lot {w} can no longer be threshold-reviewed: "
                    f"lot coverage is {c} again. Not silence -- the watch "
                    "is blind, which is different from nothing happening."
                ),
                {"lot_coverage": c},
            ),
        )

    # Re-entry watch (decision #3): flat candidates against disposal price.
    for ticker, reference in sorted(reentry_references.items()):
        watch_key = f"reentry:{ticker}"
        price = reentry_prices.get(ticker)
        if price is None:
            prior = prior_active.get((watch_key, REENTRY_DECLINE))
            result.notes.append(
                f"re-entry watch for {ticker} is unavailable: no current "
                "price could be fetched; the watch is paused, not cleared"
            )
            if prior is not None:
                # Carry the prior row forward unchanged except the clock:
                # unavailable data is not evidence of either state.
                carried = dict(prior)
                carried["last_evaluated_at"] = now_iso
                result.states.append(carried)
                seen.add((watch_key, REENTRY_DECLINE))
            continue
        trigger = reference * (
            Decimal("1") + decline_threshold / Decimal("100")
        )
        active = price <= trigger
        emit(
            watch_key,
            REENTRY_DECLINE,
            ticker,
            active,
            lambda t=ticker, p=price, r=reference, g=trigger: (
                (
                    f"{t} has no open lots and trades at "
                    f"{decimal_text(p.quantize(Decimal('0.01')))}, at or "
                    f"below the re-entry review level "
                    f"{decimal_text(g.quantize(Decimal('0.01')))} "
                    f"({engine['decline_review_threshold_pct']}% from the "
                    f"last disposal fill "
                    f"{decimal_text(r.quantize(Decimal('0.01')))})."
                ),
                {
                    "reference_disposal_price": decimal_text(r),
                    "current_price": decimal_text(p),
                    "trigger_price": decimal_text(g),
                },
            ),
        )

    return result


def derive_reentry_references(
    fills: Iterable[Any],
    *,
    flat_growth_tickers: Iterable[str],
) -> dict[str, Decimal]:
    """Last disposal fill price per flat growth candidate, from the journal.

    Deterministic and stateless: the reference is derived from the same
    append-only fills the lot ledger replays, ordered exactly like
    ``build_ledger`` orders them, so no separate disposal record can drift
    from the accounting truth.
    """
    flat = {t.upper() for t in flat_growth_tickers}
    last_sell: dict[str, tuple[Any, str, Decimal]] = {}
    for fill in fills:
        side = getattr(fill, "side", None)
        if side != "sell":
            continue
        ticker = fill.ticker.upper()
        if ticker not in flat:
            continue
        order_key = (fill.at, fill.fill_id)
        current = last_sell.get(ticker)
        if current is None or order_key > (current[0], current[1]):
            last_sell[ticker] = (
                fill.at,
                fill.fill_id,
                to_decimal(fill.price, name=f"{ticker} sell fill price"),
            )
    return {ticker: price for ticker, (_, _, price) in last_sell.items()}


def run_sleeve_notification_cycle(
    store: AssistantStore,
    *,
    snapshot: Any,
    now: datetime | None = None,
    price_fetcher: Callable[[list[str]], Mapping[str, Decimal]] | None = None,
) -> dict[str, Any]:
    """One daily evaluation: report -> transitions -> batched warnings.

    Writes exactly three kinds of state, all its own: `sleeve_watch_states`
    (replaced atomically), WARNING rows in `operational_alerts` (one per
    activation, fingerprint-deduplicated), and -- only when a re-entry
    watch needs an unheld ticker's price -- a GR-4 provider-fetch record.
    It never touches proposals, reservations, executions, or policy.
    """
    from assistant.corporate_actions import fills_with_confirmed_splits
    from assistant.sleeve_report import evaluate_sleeves
    from assistant.tax_lots import build_ledger

    at = now or datetime.now(timezone.utc)
    now_iso = at.isoformat()

    fills = fills_with_confirmed_splits(store)
    ledger = build_ledger(fills)
    report = evaluate_sleeves(snapshot, ledger, store.list_journal_postings())

    held_tickers = {position.ticker.upper() for position in snapshot.positions}
    flat_growth = [
        ticker
        for ticker in config.GROWTH_ROTATION_TICKERS
        if not ledger.open_for(ticker) and ticker.upper() not in held_tickers
    ]
    references = derive_reentry_references(
        fills, flat_growth_tickers=flat_growth
    )
    prices: dict[str, Decimal] = {}
    if references:
        fetch = price_fetcher or _recorded_close_fetcher(store, now=at)
        try:
            prices = dict(fetch(sorted(references)))
        except Exception:
            # The fetcher itself failing is equivalent to no prices: the
            # evaluator turns every priceless reference into an explicit
            # note rather than a cleared or crossed watch.
            prices = {}

    evaluation = evaluate_watch_transitions(
        report,
        prior_states=store.list_sleeve_watch_states(),
        reentry_references=references,
        reentry_prices=prices,
        now_iso=now_iso,
    )
    store.commit_sleeve_notification_cycle(
        alerts=[
            {
                "fingerprint": alert_fingerprint(
                    activation.kind, activation.watch_key
                ),
                "severity": WARNING_SEVERITY,
                "category": ALERT_CATEGORY,
                "message": activation.message,
                "details": activation.details,
            }
            for activation in evaluation.activations
        ],
        states=evaluation.states,
        seen_at=now_iso,
    )
    return {
        "activations": [
            {
                "kind": a.kind,
                "watch_key": a.watch_key,
                "ticker": a.ticker,
                "message": a.message,
            }
            for a in evaluation.activations
        ],
        "notes": list(evaluation.notes),
        "states_tracked": len(evaluation.states),
        "evaluated_at": now_iso,
    }


def _recorded_close_fetcher(
    store: AssistantStore,
    *,
    now: datetime | None = None,
) -> Callable[[list[str]], Mapping[str, Decimal]]:
    """Fresh closes for unheld tickers, through the GR-4 recorded path."""

    def fetch(tickers: list[str]) -> Mapping[str, Decimal]:
        from assistant.data_integrity import fetch_daily_bars_recorded
        from data.price_source import evaluate_bar_freshness

        at = now or datetime.now(timezone.utc)
        bars = fetch_daily_bars_recorded(
            store, list(tickers), 10, now=at
        )
        prices: dict[str, Decimal] = {}
        for ticker, frame in bars.items():
            if frame is None or len(frame) == 0:
                continue
            try:
                latest_session = frame.index.max().date().isoformat()
            except (AttributeError, TypeError, ValueError):
                continue
            if not evaluate_bar_freshness(latest_session, now=at).fresh:
                continue
            close = frame["close"].iloc[-1]
            try:
                prices[ticker.upper()] = to_decimal(
                    close, name=f"{ticker} close"
                )
            except ValueError:
                continue  # a non-finite close is "no price", handled upstream
        return prices

    return fetch
