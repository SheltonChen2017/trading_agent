"""Guards for assistant/sleeve_notifications.py (M2, THREE_SLEEVE_ENGINE_PLAN).

The dangerous failure directions for a notification layer:

* re-notifying daily (which also RE-OPENS acknowledged alerts through the
  upsert's conflict clause) -- the exact thing the plan forbids;
* going permanently silent after the first crossing, so a genuine re-cross
  months later never surfaces;
* reading unavailable re-entry prices as "not crossed";
* a vanished lot being dropped silently instead of surfacing coverage loss;
* the whole feature failing in a way that takes the briefing down with it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

import config
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from assistant.sleeve_notifications import (
    ALERT_CATEGORY,
    AWAITING_LONG_TERM,
    COVERAGE_LOST,
    DECLINE_REVIEW,
    GAIN_REVIEW,
    REENTRY_DECLINE,
    alert_fingerprint,
    derive_reentry_references,
    evaluate_watch_transitions,
    run_sleeve_notification_cycle,
)
from assistant.sleeve_report import evaluate_sleeves
from assistant.storage import AssistantStore
from assistant.tax_lots import Fill, build_ledger

_NOW = datetime(2026, 8, 9, 15, 30, tzinfo=timezone.utc)
_NOW_ISO = _NOW.isoformat()


def _position(ticker: str, shares: float, price: float) -> PortfolioPosition:
    return PortfolioPosition(
        ticker=ticker,
        shares=shares,
        entry_price=100.0,
        current_price=price,
        market_value=shares * price,
        unrealized_pnl_pct=0.0,
        is_leveraged_etf=False,
    )


def _snapshot(positions: list[PortfolioPosition]) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        positions=positions,
        cash=50_000.0,
        total_equity=50_000.0 + sum(p.market_value for p in positions),
        as_of="2026-08-09",
        source="manual",
        account_mode="manual",
    )


def _buy(ticker: str, qty: float, price: float, *, days_ago: int, fill_id: str):
    return Fill(ticker=ticker, side="buy", qty=qty, price=price,
                at=_NOW - timedelta(days=days_ago), fill_id=fill_id)


def _sell(ticker: str, qty: float, price: float, *, days_ago: int, fill_id: str):
    return Fill(ticker=ticker, side="sell", qty=qty, price=price,
                at=_NOW - timedelta(days=days_ago), fill_id=fill_id)


def _report(positions, fills):
    return evaluate_sleeves(_snapshot(positions), build_ledger(fills), [])


def _evaluate(report, prior=(), references=None, prices=None, now_iso=_NOW_ISO):
    return evaluate_watch_transitions(
        report,
        prior_states=list(prior),
        reentry_references=references or {},
        reentry_prices=prices or {},
        now_iso=now_iso,
    )


def _states_by_key(evaluation):
    return {(s["watch_key"], s["kind"]): s for s in evaluation.states}


# ---------------------------------------------------------------------------
# Transition semantics: once per crossing, never daily, re-arms on re-cross
# ---------------------------------------------------------------------------


def test_first_crossing_activates_once_then_stays_silent():
    fills = [_buy("NVDA", 10, 100.0, days_ago=400, fill_id="n1")]
    report = _report([_position("NVDA", 10, 160.0)], fills)  # +60%, long-term

    first = _evaluate(report)
    assert [a.kind for a in first.activations] == [GAIN_REVIEW]
    assert first.activations[0].watch_key == "n1"

    second = _evaluate(report, prior=first.states)
    assert second.activations == []  # same condition next day: SILENCE
    assert _states_by_key(second)[("n1", GAIN_REVIEW)]["active"] is True


def test_condition_clearing_then_recrossing_reactivates():
    fills = [_buy("NVDA", 10, 100.0, days_ago=400, fill_id="n1")]
    crossed = _report([_position("NVDA", 10, 160.0)], fills)
    cleared = _report([_position("NVDA", 10, 120.0)], fills)

    day1 = _evaluate(crossed)
    day2 = _evaluate(cleared, prior=day1.states)
    assert day2.activations == []
    assert _states_by_key(day2)[("n1", GAIN_REVIEW)]["active"] is False

    day3 = _evaluate(crossed, prior=day2.states)
    assert [a.kind for a in day3.activations] == [GAIN_REVIEW]  # re-armed


def test_awaiting_long_term_notifies_once_and_upgrades_to_gain_review():
    """The awaiting notification fires once with the countdown, stays quiet
    while waiting, and the gate OPENING later is a genuinely new event."""
    young = [_buy("NVDA", 10, 100.0, days_ago=340, fill_id="n1")]
    report = _report([_position("NVDA", 10, 160.0)], young)

    day1 = _evaluate(report)
    assert [a.kind for a in day1.activations] == [AWAITING_LONG_TERM]
    assert "day(s)" in day1.activations[0].message

    day2 = _evaluate(report, prior=day1.states)
    assert day2.activations == []  # MUST NOT re-notify while waiting

    seasoned = [_buy("NVDA", 10, 100.0, days_ago=400, fill_id="n1")]
    opened = _report([_position("NVDA", 10, 160.0)], seasoned)
    day3 = _evaluate(opened, prior=day2.states)
    assert [a.kind for a in day3.activations] == [GAIN_REVIEW]
    assert _states_by_key(day3)[("n1", AWAITING_LONG_TERM)]["active"] is False


def test_decline_crossing_notifies_once():
    fills = [_buy("AMD", 10, 100.0, days_ago=30, fill_id="a1")]
    report = _report([_position("AMD", 10, 88.0)], fills)  # -12%

    day1 = _evaluate(report)
    assert [a.kind for a in day1.activations] == [DECLINE_REVIEW]
    day2 = _evaluate(report, prior=day1.states)
    assert day2.activations == []


# ---------------------------------------------------------------------------
# Disposal vs coverage loss
# ---------------------------------------------------------------------------


def test_disposed_lot_drops_its_rows_without_a_coverage_alert():
    """Lot sold (position gone, or remaining coverage healthy): normal life.
    Its rows disappear; no coverage_lost alert fires."""
    fills = [_buy("AMD", 10, 100.0, days_ago=30, fill_id="a1")]
    day1 = _evaluate(_report([_position("AMD", 10, 88.0)], fills))

    sold = fills + [_sell("AMD", 10, 92.0, days_ago=1, fill_id="a1-out")]
    after = _report([], sold)  # position closed entirely
    day2 = _evaluate(after, prior=day1.states)
    assert [a for a in day2.activations if a.kind == COVERAGE_LOST] == []
    assert ("a1", DECLINE_REVIEW) not in _states_by_key(day2)


def test_vanished_lot_with_broken_coverage_alerts_coverage_lost_once():
    """The same lot disappearing while the position's coverage is broken is
    blindness, not disposal -- the plan requires it to surface."""
    fills = [_buy("AMD", 10, 100.0, days_ago=30, fill_id="a1")]
    day1 = _evaluate(_report([_position("AMD", 10, 88.0)], fills))

    # Same position still held, but no fills replay (e.g. journal problem):
    # coverage 'none', the lot is gone from the report.
    blind = _report([_position("AMD", 10, 88.0)], [])
    day2 = _evaluate(blind, prior=day1.states)
    assert [a.kind for a in day2.activations] == [COVERAGE_LOST]

    day3 = _evaluate(blind, prior=day2.states)
    assert day3.activations == []  # still blind: already notified


def test_coverage_healing_flips_inactive_and_rebreak_realerts():
    fills = [_buy("AMD", 10, 100.0, days_ago=30, fill_id="a1")]
    tracked = _evaluate(_report([_position("AMD", 10, 88.0)], fills))
    blind = _evaluate(_report([_position("AMD", 10, 88.0)], []), prior=tracked.states)
    healed = _evaluate(
        _report([_position("AMD", 10, 88.0)], fills), prior=blind.states
    )
    assert healed.activations != []  # decline re-tracked counts as new lot rows
    coverage_rows = [
        s for s in healed.states if s["kind"] == COVERAGE_LOST
    ]
    assert coverage_rows and coverage_rows[0]["active"] is False

    reblind = _evaluate(
        _report([_position("AMD", 10, 88.0)], []), prior=healed.states
    )
    # The re-break must RE-ALERT (fresh inactive->active transition), via
    # whichever detection path sees it first -- the healed run re-created
    # the lot's kind rows, so the vanished-lot path fires here.
    recross = [a for a in reblind.activations if a.kind == COVERAGE_LOST]
    assert len(recross) == 1
    assert "no longer be threshold-reviewed" in recross[0].message


# ---------------------------------------------------------------------------
# Re-entry watch (decision #3)
# ---------------------------------------------------------------------------


def test_reentry_reference_is_last_sell_fill_price():
    fills = [
        _buy("NVDA", 10, 100.0, days_ago=200, fill_id="n1"),
        _sell("NVDA", 6, 150.0, days_ago=50, fill_id="s1"),
        _sell("NVDA", 4, 170.0, days_ago=10, fill_id="s2"),
    ]
    refs = derive_reentry_references(fills, flat_growth_tickers=["NVDA"])
    assert refs == {"NVDA": Decimal("170")}


def test_reentry_activates_at_exactly_the_inclusive_boundary():
    """Reference 170, threshold -10% -> trigger 153.00 exactly crosses;
    153.01 does not."""
    report = _report([], [])
    refs = {"NVDA": Decimal("170")}

    at_boundary = _evaluate(report, references=refs, prices={"NVDA": Decimal("153.00")})
    assert [a.kind for a in at_boundary.activations] == [REENTRY_DECLINE]
    assert "153" in at_boundary.activations[0].message

    above = _evaluate(report, references=refs, prices={"NVDA": Decimal("153.01")})
    assert above.activations == []
    assert _states_by_key(above)[("reentry:NVDA", REENTRY_DECLINE)]["active"] is False


def test_reentry_notifies_once_then_stays_silent():
    report = _report([], [])
    refs = {"NVDA": Decimal("170")}
    prices = {"NVDA": Decimal("150")}
    day1 = _evaluate(report, references=refs, prices=prices)
    assert len(day1.activations) == 1
    day2 = _evaluate(report, prior=day1.states, references=refs, prices=prices)
    assert day2.activations == []


def test_missing_reentry_price_pauses_the_watch_never_clears_it():
    """Unavailable data must not read as 'not crossed': the prior ACTIVE
    state is carried forward untouched and a note says the watch paused."""
    report = _report([], [])
    refs = {"NVDA": Decimal("170")}
    active = _evaluate(report, references=refs, prices={"NVDA": Decimal("150")})

    paused = _evaluate(report, prior=active.states, references=refs, prices={})
    assert paused.activations == []
    assert any("unavailable" in note for note in paused.notes)
    row = _states_by_key(paused)[("reentry:NVDA", REENTRY_DECLINE)]
    assert row["active"] is True  # NOT cleared by missing data

    # Price returns, still below trigger: no duplicate alert either.
    resumed = _evaluate(
        report, prior=paused.states, references=refs,
        prices={"NVDA": Decimal("150")},
    )
    assert resumed.activations == []


# ---------------------------------------------------------------------------
# The full cycle against a real store
# ---------------------------------------------------------------------------


def _seeded_store(tmp_path):
    from assistant.order_lifecycle import journal_broker_order_update

    store = AssistantStore(tmp_path / "m2.db")
    at = _NOW - timedelta(days=400)
    proposal_id = "p-m2"
    store.save_proposal(
        {
            "proposal_id": proposal_id,
            "created_at": at.isoformat(),
            "expires_at": (at + timedelta(hours=4)).isoformat(),
            "status": "filled",
            "idempotency_key": "idem-p-m2",
            "intent": {
                "ticker": "NVDA",
                "side": "buy",
                "shares": 10,
                "order_type": "market",
                "limit_price": None,
            },
        }
    )
    journal_broker_order_update(
        store,
        proposal_id,
        {
            "order_id": "o-m2",
            "client_order_id": "idem-p-m2",
            "ticker": "NVDA",
            "shares": 10.0,
            "side": "buy",
            "type": "market",
            "limit_price": None,
            "time_in_force": "day",
            "status": "filled",
            "filled_qty": 10.0,
            "filled_avg_price": 100.0,
            "submitted_at": at.isoformat(),
            "updated_at": None,
        },
        event_type="fill",
        event_at=at.isoformat(),
        fill_qty=10.0,
        fill_price=100.0,
    )
    return store


def test_cycle_upserts_warning_once_and_acknowledged_alert_stays_acknowledged(tmp_path):
    """THE anti-nag invariant, end to end: day two must not re-open an
    acknowledged alert, because only transitions upsert."""
    store = _seeded_store(tmp_path)
    snapshot = _snapshot([_position("NVDA", 10, 160.0)])

    first = run_sleeve_notification_cycle(store, snapshot=snapshot, now=_NOW)
    assert len(first["activations"]) == 1
    alerts = store.list_operational_alerts(status="open")
    sleeve_alerts = [a for a in alerts if a["category"] == ALERT_CATEGORY]
    assert len(sleeve_alerts) == 1
    assert sleeve_alerts[0]["severity"] == "warning"
    assert sleeve_alerts[0]["occurrences"] == 1

    store.acknowledge_operational_alert(sleeve_alerts[0]["alert_id"])

    second = run_sleeve_notification_cycle(
        store, snapshot=snapshot, now=_NOW + timedelta(days=1)
    )
    assert second["activations"] == []
    still_open = [
        a
        for a in store.list_operational_alerts(status="open")
        if a["category"] == ALERT_CATEGORY
    ]
    assert still_open == []  # acknowledged and NOT re-opened


def test_cycle_recross_reopens_the_same_fingerprint(tmp_path):
    store = _seeded_store(tmp_path)
    crossed = _snapshot([_position("NVDA", 10, 160.0)])
    cleared = _snapshot([_position("NVDA", 10, 120.0)])

    run_sleeve_notification_cycle(store, snapshot=crossed, now=_NOW)
    run_sleeve_notification_cycle(
        store, snapshot=cleared, now=_NOW + timedelta(days=1)
    )
    third = run_sleeve_notification_cycle(
        store, snapshot=crossed, now=_NOW + timedelta(days=2)
    )
    assert len(third["activations"]) == 1
    # The journaled fill's derived lot id (a hashed broker-event id) is the
    # watch key -- read it from the activation rather than assuming its
    # shape, then confirm the SAME fingerprint was re-opened, not a second
    # alert row created.
    watch_key = third["activations"][0]["watch_key"]
    alert = [
        a
        for a in store.list_operational_alerts(status="open")
        if a["fingerprint"] == alert_fingerprint(GAIN_REVIEW, watch_key)
    ]
    assert len(alert) == 1
    assert alert[0]["occurrences"] == 2  # same fingerprint, re-opened
    assert (
        len([a for a in store.list_operational_alerts(status="open")
             if a["category"] == ALERT_CATEGORY]) == 1
    )


def test_cycle_writes_only_its_own_tables(tmp_path):
    """Whole-database write-surface proof: the cycle may touch its watch
    state, operational alerts, and provider-fetch records -- nothing else,
    and never proposals/reservations/executions."""
    store = _seeded_store(tmp_path)
    snapshot = _snapshot([_position("NVDA", 10, 160.0)])

    def counts():
        with store._connect() as connection:
            tables = [
                r[0]
                for r in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            ]
            return {
                t: connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in tables
            }

    before = counts()
    run_sleeve_notification_cycle(
        store, snapshot=snapshot, now=_NOW, price_fetcher=lambda t: {}
    )
    after = counts()
    allowed = {"sleeve_watch_states", "operational_alerts", "data_provider_fetches"}
    changed = {t for t in after if after[t] != before.get(t)}
    assert changed <= allowed, f"cycle wrote unexpected tables: {changed - allowed}"


def test_cycle_failure_does_not_break_the_briefing(tmp_path, monkeypatch, capsys):
    """Failure isolation at the integration point: the cycle raising must
    cost one printed line, never the briefing or its warnings."""
    import argparse

    import scripts.run_personal_assistant as cli

    store = AssistantStore(tmp_path / "briefing.db")
    store.upsert_operational_alert(
        fingerprint="pre-existing",
        severity="warning",
        category="ops",
        message="a pre-existing warning that must still render",
    )

    monkeypatch.setattr(cli, "is_configured", lambda: False)

    import assistant.sleeve_notifications as sn

    def boom(*args, **kwargs):
        raise RuntimeError("deliberate M2 failure")

    monkeypatch.setattr(sn, "run_sleeve_notification_cycle", boom)

    cli.command_briefing(
        argparse.Namespace(no_events=True, policy=None, database=str(store.path)),
        store,
    )
    out = capsys.readouterr().out
    assert "a pre-existing warning that must still render" in out
    assert "Sleeve engine notifications unavailable" in out
    assert "deliberate M2 failure" in out
    assert "Persisted decision packet" in out  # the briefing completed


# ---------------------------------------------------------------------------
# Storage migration
# ---------------------------------------------------------------------------


def test_watch_state_table_appears_on_fresh_and_pre_migration_databases(tmp_path):
    import sqlite3

    fresh = AssistantStore(tmp_path / "fresh.db")
    assert fresh.list_sleeve_watch_states() == []

    # Pre-migration database: the REAL current schema minus this table
    # (dropping it simulates a database created before M2), then reopened
    # through the real initializer, which must recreate it idempotently.
    legacy_path = tmp_path / "legacy.db"
    AssistantStore(legacy_path)
    with sqlite3.connect(legacy_path) as connection:
        connection.execute("DROP TABLE sleeve_watch_states")
    migrated = AssistantStore(legacy_path)
    assert migrated.list_sleeve_watch_states() == []


def test_watch_state_round_trip_is_atomic_full_replacement(tmp_path):
    store = AssistantStore(tmp_path / "state.db")
    store.save_sleeve_watch_states(
        [
            {
                "watch_key": "n1",
                "kind": GAIN_REVIEW,
                "ticker": "NVDA",
                "active": True,
                "first_active_at": _NOW_ISO,
                "last_transition_at": _NOW_ISO,
                "last_evaluated_at": _NOW_ISO,
                "details": {"unrealized_pnl_pct": 60.0},
            }
        ]
    )
    rows = store.list_sleeve_watch_states()
    assert len(rows) == 1 and rows[0]["active"] is True
    store.save_sleeve_watch_states([])
    assert store.list_sleeve_watch_states() == []
