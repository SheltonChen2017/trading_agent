"""Three-sleeve M3: dividend -> reinvest proposals with earmark accounting.

The dangerous directions these tests exist for:

* a dividend dollar spent twice (earmark race, retry replay, or a partial
  fill's dollars returning to the pool);
* an earmark released on an AMBIGUOUS proposal outcome (submission_unknown
  is not a refusal);
* the routing rule inverted -- leveraged reinvestment while a decline-review
  add is waiting is exactly what plan section 1.1 forbids; and
* the write path touching anything beyond its two tables.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.portfolio_ledger import record_dividend
from assistant.proposal_status import (
    BLOCKED,
    BROKER_ACCEPTED,
    BROKER_EXPIRED,
    BROKER_REJECTED,
    CANCELED,
    DISMISSED,
    EXECUTED,
    EXPIRED,
    FILLED,
    PROPOSED,
    RECONCILING,
    SUBMISSION_FAILED,
    SUBMISSION_UNKNOWN,
    VALIDATION_FAILED,
)
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.sleeve_notifications import DECLINE_REVIEW, GAIN_REVIEW, REENTRY_DECLINE
from assistant.sleeve_reinvest import (
    EARMARK_FILL_DEPENDENT_STATUSES,
    EARMARK_RELEASE_STATUSES,
    EVIDENCE_STATUS_DECLINE_ADD,
    EVIDENCE_STATUS_REINVEST,
    ROUTE_DECLINE_ADD,
    ROUTE_REINVEST,
    SleeveReinvestError,
    confirmed_dividend_income_text,
    dividend_reinvest_status,
    earmark_disposition,
    generate_dividend_reinvest_proposal,
    pending_decline_reviews,
    reconcile_dividend_earmarks,
)
from assistant.storage import AssistantStore

_NOW = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)


def _store(tmp_path) -> AssistantStore:
    return AssistantStore(tmp_path / "assistant.db")


def _packet(cash=10_000.0):
    snapshot = build_portfolio_snapshot([], cash=cash)
    return DecisionPacket(
        generated_at="2026-08-13T15:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-08-12",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _policy():
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )


def _seed_dividend(store, amount="500", external_id="div-1", ticker="JEPQ"):
    record_dividend(
        store,
        external_id=external_id,
        ticker=ticker,
        gross_amount=amount,
        occurred_at="2026-08-10T00:00:00+00:00",
    )


def _watch_row(kind, ticker, *, active=True, watch_key=None):
    return {
        "watch_key": watch_key or f"{kind}:{ticker}",
        "kind": kind,
        "ticker": ticker,
        "active": active,
        "first_active_at": _NOW.isoformat() if active else None,
        "last_transition_at": _NOW.isoformat(),
        "last_evaluated_at": _NOW.isoformat(),
        "details": {},
    }


def _create(store, *, ticker="NVDL", amount="300", price="30", now=_NOW):
    return generate_dividend_reinvest_proposal(
        _packet(), _policy(), store, ticker=ticker, amount=amount, price=price,
        now=now,
    )


def _force_status(store, proposal_id, new_status, *, expected=PROPOSED):
    moved = store.update_proposal_status_if_current(
        proposal_id, expected_statuses=(expected,), new_status=new_status
    )
    assert moved is not None, f"could not force {proposal_id} to {new_status}"


def _plant_fill_event(store, proposal_id, fill_qty):
    fill_qty_text = str(fill_qty)
    order = {
        "order_id": f"order-{proposal_id}",
        "status": "partially_filled",
        "submitted_at": _NOW.isoformat(),
    }
    store.project_broker_order_event(
        event_id=f"event-{proposal_id}",
        proposal_id=proposal_id,
        order=order,
        event_type="fill",
        event_at=_NOW.isoformat(),
        new_proposal_status=PROPOSED,
        expected_current_statuses=(PROPOSED,),
        proposal_updates={"broker_order": order},
        fill_qty=fill_qty,
        fill_qty_decimal=fill_qty_text,
        fill_price=30,
        fill_price_decimal="30",
    )


def _plant_cumulative_fill_event(store, proposal_id, filled_qty):
    """Plant the shape written by broker polling (no incremental fill_qty)."""
    filled_qty_text = str(filled_qty)
    order = {
        "order_id": f"order-{proposal_id}",
        "status": "canceled",
        "submitted_at": _NOW.isoformat(),
        "filled_qty": filled_qty,
        "filled_qty_decimal": filled_qty_text,
        "filled_avg_price": 30,
        "filled_avg_price_decimal": "30",
    }
    store.project_broker_order_event(
        event_id=f"event-{proposal_id}",
        proposal_id=proposal_id,
        order=order,
        event_type="poll_reconciliation",
        event_at=_NOW.isoformat(),
        new_proposal_status=PROPOSED,
        expected_current_statuses=(PROPOSED,),
        proposal_updates={"broker_order": order},
    )


# --- income measurement ----------------------------------------------------


def test_confirmed_income_counts_only_corporate_action_dividends(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="123.45")
    assert confirmed_dividend_income_text(store.list_journal_postings()) == "123.45"


def test_confirmed_income_is_zero_on_an_empty_journal(tmp_path):
    store = _store(tmp_path)
    assert confirmed_dividend_income_text(store.list_journal_postings()) == "0"


def test_a_positive_income_posting_is_refused_not_netted():
    postings = [
        {
            "source": "corporate_action",
            "account": "INCOME:DIVIDENDS",
            "amount": "25",
            "transaction_id": "t-weird",
        }
    ]
    with pytest.raises(SleeveReinvestError):
        confirmed_dividend_income_text(postings)


def test_non_corporate_action_income_is_excluded_from_the_pool():
    postings = [
        {
            "source": "operator_acknowledgement",
            "account": "INCOME:DIVIDENDS",
            "amount": "-40",
            "transaction_id": "t-ack",
        }
    ]
    assert confirmed_dividend_income_text(postings) == "0"


# --- disposition table -----------------------------------------------------


@pytest.mark.parametrize(
    "status", [BLOCKED, VALIDATION_FAILED, SUBMISSION_FAILED, BROKER_REJECTED, EXPIRED, DISMISSED]
)
def test_provably_unspent_terminals_release(status):
    assert earmark_disposition(status, fill_evidence=False) == "release"


def test_a_fill_consumes():
    assert earmark_disposition(FILLED, fill_evidence=False) == "consume"


def test_every_still_executable_status_holds_its_earmark():
    """Counter-review M3CR-001: the sharpest case is `override_available`.

    `PolicyOverridableBlockError` leaves a proposal in that status
    PRECISELY so a human can re-invoke with override_policy_violations=True
    -- its dollars are still spendable. It reads like a stopped validation,
    so it is exactly the status a future author might add to the release
    list. It holds today only through the function's default branch, with
    nothing pinning it; releasing it would let the same dividend dollars
    fund a second proposal while the first one still executes.

    Stated as a RELATIONSHIP over the canonical status vocabulary rather
    than a copied list, so a new lifecycle status inherits the rule instead
    of silently escaping it. `blocked` is deliberately absent: the kernel
    documents it as terminal (execution_kernel/errors.py -- an overridable
    refusal goes to override_available, never blocked), so releasing there
    is correct.
    """
    from assistant.proposal_status import (
        IN_FLIGHT_INTENT_STATUSES,
        POLICY_OVERRIDE_AVAILABLE,
        PROPOSED,
    )

    still_executable = set(IN_FLIGHT_INTENT_STATUSES) | {
        PROPOSED,
        POLICY_OVERRIDE_AVAILABLE,
    }
    for status in sorted(still_executable):
        assert earmark_disposition(status, fill_evidence=False) == "hold", (
            f"{status!r} can still reach the broker; its earmark must hold"
        )


def test_no_status_releases_once_fill_evidence_exists():
    """The whole canonical vocabulary, not a sample: recorded spending
    outranks every label, including ones that do not exist yet."""
    from assistant.proposal_status import STATUSES

    releasing = [
        status
        for status in STATUSES
        if earmark_disposition(status, fill_evidence=True) == "release"
    ]
    assert not releasing, releasing
    # And without evidence, exactly the reviewed sets release -- no more.
    assert {
        status
        for status in STATUSES
        if earmark_disposition(status, fill_evidence=False) == "release"
    } == set(EARMARK_RELEASE_STATUSES) | set(EARMARK_FILL_DEPENDENT_STATUSES)


@pytest.mark.parametrize("status", [CANCELED, BROKER_EXPIRED])
def test_cancellation_is_fill_dependent(status):
    assert earmark_disposition(status, fill_evidence=False) == "release"
    # A partial fill spent real dollars; the whole earmark is consumed
    # rather than any part of it returning to the pool.
    assert earmark_disposition(status, fill_evidence=True) == "consume"


@pytest.mark.parametrize(
    "status",
    [PROPOSED, SUBMISSION_UNKNOWN, RECONCILING, BROKER_ACCEPTED, EXECUTED,
     "some_future_status", None, 7],
)
def test_ambiguous_and_unknown_states_hold(status):
    assert earmark_disposition(status, fill_evidence=False) == "hold"


# --- storage: atomic create and exactly-once resolve -----------------------


def test_migration_adds_the_earmark_table_to_a_pre_existing_database(tmp_path):
    store = _store(tmp_path)
    with store._connect() as connection:
        connection.execute("DROP TABLE sleeve_dividend_earmarks")
    reopened = AssistantStore(tmp_path / "assistant.db")
    assert reopened.list_dividend_earmarks() == []


def test_create_refuses_beyond_the_pool_and_writes_nothing(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="100")
    result = _create(store, amount="150", price="30")
    assert result["created"] is False
    assert "exceeds the available dividend pool" in result["reason"]
    assert store.list_dividend_earmarks() == []
    assert store.list_proposals_by_statuses((PROPOSED,)) == []


def test_create_within_the_pool_writes_proposal_and_earmark_together(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    result = _create(store, amount="300", price="30")
    assert result["created"] is True
    proposal = result["proposal"]
    assert proposal.evidence_status == EVIDENCE_STATUS_REINVEST
    assert proposal.intent.shares == 10
    earmarks = store.list_dividend_earmarks()
    assert len(earmarks) == 1
    assert earmarks[0]["proposal_id"] == proposal.proposal_id
    assert earmarks[0]["amount_text"] == "300"
    assert earmarks[0]["status"] == "active"
    assert store.get_proposal(proposal.proposal_id) is not None


def test_floor_rounding_earmarks_the_notional_not_the_request(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    result = _create(store, amount="100", price="30")
    assert result["created"] is True
    # 3 shares x 30 = 90 earmarked; the un-spendable 10 stays in the pool.
    assert result["earmark_amount_text"] == "90"
    status = dividend_reinvest_status(store)
    assert status["available_total"] == "410"


def test_two_earmarks_cannot_oversubscribe_the_pool(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    first = _create(store, amount="300", price="30")
    assert first["created"] is True
    second = generate_dividend_reinvest_proposal(
        _packet(), _policy(), store, ticker="SOXL", amount="300", price="30",
        now=_NOW + timedelta(minutes=1),
    )
    assert second["created"] is False
    assert "exceeds the available dividend pool" in second["reason"]


def test_recreating_the_identical_proposal_refuses_a_second_earmark(tmp_path):
    # Pool is wide enough that the duplicate passes the pool check and must
    # be stopped by the proposal-exists fence itself -- with a small pool the
    # pool check fires first and this branch would go untested.
    store = _store(tmp_path)
    _seed_dividend(store, amount="1000")
    assert _create(store)["created"] is True
    duplicate = _create(store)  # same packet timestamp -> same proposal_id
    assert duplicate["created"] is False
    assert "already exists" in duplicate["reason"]
    assert len(store.list_dividend_earmarks()) == 1


def test_the_storage_transaction_itself_enforces_the_pool(tmp_path):
    """The module pre-checks the pool for a friendly message, but the
    STORAGE transaction is the authoritative fence against a concurrent
    creator -- so it must refuse on its own, with the pre-check bypassed.
    Found by mutation: disabling the in-transaction check left every
    module-level test green because the pre-check shadowed it.
    """
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")

    def _proposal(pid):
        return {
            "proposal_id": pid,
            "created_at": _NOW.isoformat(),
            "expires_at": (_NOW + timedelta(minutes=15)).isoformat(),
            "status": "proposed",
            "idempotency_key": f"{pid}-2026-08-13",
        }

    first = store.create_dividend_earmark_with_proposal(
        _proposal("tp_direct_1"), amount_text="300", route=ROUTE_REINVEST,
        ticker="NVDL", now=_NOW.isoformat(),
    )
    assert first["created"] is True
    second = store.create_dividend_earmark_with_proposal(
        _proposal("tp_direct_2"), amount_text="300", route=ROUTE_REINVEST,
        ticker="SOXL", now=_NOW.isoformat(),
    )
    assert second["created"] is False
    assert "exceeds the available dividend pool" in second["reason"]
    assert len(store.list_dividend_earmarks()) == 1
    assert store.get_proposal("tp_direct_2") is None, (
        "a pool refusal must not leave a proposal row behind"
    )


def test_the_fence_and_the_module_measure_the_same_dividend_pool(tmp_path):
    """Counter-review M3CR-002: two implementations of one authoritative rule.

    Review correctly stopped the fence from trusting a caller-supplied
    income total, but `assistant/storage.py` cannot import
    `assistant/portfolio_ledger` (that module imports storage -- a cycle),
    so the fence repeats the account name as the SQL literal
    'INCOME:DIVIDENDS' while `sleeve_reinvest` reads
    ACCOUNT_DIVIDEND_INCOME. Nothing pinned that the two agree.

    The drift direction is the unsafe one and it is silent: rename the
    constant and the status surface reports 0 available while the fence
    keeps funding proposals from the old rows -- money the UI says is not
    there. Pinned behaviorally at the exact boundary rather than by
    grepping the SQL, so it also catches a filter/JOIN divergence, not
    just a renamed string.
    """
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")

    def _proposal(pid):
        return {
            "proposal_id": pid,
            "created_at": _NOW.isoformat(),
            "expires_at": (_NOW + timedelta(minutes=15)).isoformat(),
            "status": "proposed",
            "idempotency_key": f"{pid}-2026-08-13",
        }

    measured = confirmed_dividend_income_text(store.list_journal_postings())
    assert measured == "500"

    over = store.create_dividend_earmark_with_proposal(
        _proposal("tp_boundary_over"), amount_text="500.01",
        route=ROUTE_REINVEST, ticker="NVDL", now=_NOW.isoformat(),
    )
    assert over["created"] is False, (
        "the fence must not fund a cent beyond what the module measures"
    )
    exact = store.create_dividend_earmark_with_proposal(
        _proposal("tp_boundary_exact"), amount_text=measured,
        route=ROUTE_REINVEST, ticker="NVDL", now=_NOW.isoformat(),
    )
    assert exact["created"] is True, (
        "the fence must fund the full measured pool -- refusing less would "
        "strand confirmed dividend income the status surface advertises"
    )


def test_storage_refuses_to_create_without_journal_income(tmp_path):
    """The storage fence must derive money from durable books."""
    store = _store(tmp_path)
    proposal = {
        "proposal_id": "tp_invented_pool",
        "created_at": _NOW.isoformat(),
        "expires_at": (_NOW + timedelta(minutes=15)).isoformat(),
        "status": "proposed",
        "idempotency_key": "tp_invented_pool-2026-08-13",
    }

    result = store.create_dividend_earmark_with_proposal(
        proposal, amount_text="300", route=ROUTE_REINVEST,
        ticker="NVDL", now=_NOW.isoformat(),
    )

    assert result["created"] is False
    assert store.list_dividend_earmarks() == []
    assert store.get_proposal("tp_invented_pool") is None


def test_unknown_earmark_status_holds_dollars_in_the_read_view(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    with store._connect() as connection:  # simulate corrupt/future durable state
        connection.execute(
            "UPDATE sleeve_dividend_earmarks SET status = 'future_state' "
            "WHERE proposal_id = ?", (proposal_id,),
        )

    status = dividend_reinvest_status(store)

    assert status["available_total"] == "200"
    assert status["earmarks"][0]["effective_disposition"] == "hold"


def test_storage_fence_counts_unknown_earmark_status_as_unavailable(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    with store._connect() as connection:  # simulate corrupt/future durable state
        connection.execute(
            "UPDATE sleeve_dividend_earmarks SET status = 'future_state' "
            "WHERE proposal_id = ?", (proposal_id,),
        )
    proposal = {
        "proposal_id": "tp_after_unknown_earmark",
        "created_at": _NOW.isoformat(),
        "expires_at": (_NOW + timedelta(minutes=15)).isoformat(),
        "status": "proposed",
        "idempotency_key": "tp_after_unknown_earmark-2026-08-13",
    }

    result = store.create_dividend_earmark_with_proposal(
        proposal, amount_text="300", route=ROUTE_REINVEST,
        ticker="NVDL", now=_NOW.isoformat(),
    )

    assert result["created"] is False
    assert store.get_proposal("tp_after_unknown_earmark") is None


def test_nonpositive_stored_earmark_amount_fails_closed(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    with store._connect() as connection:  # simulate corrupt durable money
        connection.execute(
            "UPDATE sleeve_dividend_earmarks SET amount_text = '-300' "
            "WHERE proposal_id = ?", (proposal_id,),
        )

    with pytest.raises(SleeveReinvestError):
        dividend_reinvest_status(store)

    proposal = {
        "proposal_id": "tp_after_bad_amount",
        "created_at": _NOW.isoformat(),
        "expires_at": (_NOW + timedelta(minutes=15)).isoformat(),
        "status": "proposed",
        "idempotency_key": "tp_after_bad_amount-2026-08-13",
    }
    result = store.create_dividend_earmark_with_proposal(
        proposal, amount_text="100", route=ROUTE_REINVEST,
        ticker="NVDL", now=_NOW.isoformat(),
    )
    assert result["created"] is False
    assert store.get_proposal("tp_after_bad_amount") is None


def test_resolve_is_exactly_once(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    first = store.resolve_dividend_earmark_if_active(
        proposal_id, new_status="released", resolved_reason="test", now=_NOW.isoformat()
    )
    second = store.resolve_dividend_earmark_if_active(
        proposal_id, new_status="consumed", resolved_reason="replay", now=_NOW.isoformat()
    )
    assert first is True and second is False
    row = store.list_dividend_earmarks()[0]
    assert row["status"] == "released"
    assert row["resolved_reason"] == "test"


def test_resolve_rejects_an_invented_status(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.resolve_dividend_earmark_if_active(
            "p", new_status="spent", resolved_reason="", now=_NOW.isoformat()
        )


# --- routing ---------------------------------------------------------------


def test_reinvest_route_when_no_decline_review_is_pending(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store)
    status = dividend_reinvest_status(store)
    assert status["route"] == ROUTE_REINVEST
    assert status["eligible_tickers"] == sorted(
        t.upper() for t in config.DIVIDEND_REINVEST_TICKERS
    )


def test_a_pending_decline_review_outranks_leveraged_reinvestment(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store)
    store.save_sleeve_watch_states([_watch_row(DECLINE_REVIEW, "AMD")])
    status = dividend_reinvest_status(store)
    assert status["route"] == ROUTE_DECLINE_ADD
    assert status["eligible_tickers"] == ["AMD"]
    refused = _create(store, ticker="NVDL")
    assert refused["created"] is False
    assert "AMD" in refused["reason"]
    allowed = _create(store, ticker="AMD", amount="300", price="30")
    assert allowed["created"] is True
    assert allowed["proposal"].evidence_status == EVIDENCE_STATUS_DECLINE_ADD
    assert allowed["route"] == ROUTE_DECLINE_ADD


def test_a_reentry_watch_also_counts_as_a_pending_dip_add(tmp_path):
    store = _store(tmp_path)
    store.save_sleeve_watch_states([_watch_row(REENTRY_DECLINE, "TSM")])
    assert pending_decline_reviews(store) == [
        {"ticker": "TSM", "kind": REENTRY_DECLINE, "watch_key": f"{REENTRY_DECLINE}:TSM"}
    ]


def test_inactive_and_unrelated_watches_do_not_block_reinvestment(tmp_path):
    store = _store(tmp_path)
    store.save_sleeve_watch_states(
        [
            _watch_row(DECLINE_REVIEW, "AMD", active=False),
            _watch_row(GAIN_REVIEW, "NVDA"),
        ]
    )
    assert pending_decline_reviews(store) == []


def test_an_ineligible_ticker_is_refused_on_the_reinvest_route(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store)
    refused = _create(store, ticker="AAPL")
    assert refused["created"] is False
    assert "DIVIDEND_REINVEST_TICKERS" in refused["reason"]


# --- input refusals --------------------------------------------------------


@pytest.mark.parametrize("amount", ["0", "-5", "nan", "inf", "abc"])
def test_unusable_amounts_are_refused(tmp_path, amount):
    store = _store(tmp_path)
    _seed_dividend(store)
    assert _create(store, amount=amount)["created"] is False


@pytest.mark.parametrize("price", ["0", "-1", "nan", "inf", None])
def test_unusable_prices_are_refused(tmp_path, price):
    store = _store(tmp_path)
    _seed_dividend(store)
    assert _create(store, price=price)["created"] is False


def test_an_amount_below_one_share_is_refused(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store)
    result = _create(store, amount="20", price="30")
    assert result["created"] is False
    assert "cannot afford one share" in result["reason"]


# --- reconcile: durable exactly-once transitions ---------------------------


def test_reconcile_releases_an_expired_proposal_exactly_once(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    _force_status(store, proposal_id, EXPIRED)
    transitions = reconcile_dividend_earmarks(store, now=_NOW)
    assert transitions == [
        {
            "proposal_id": proposal_id,
            "action": "released",
            "reason": f"proposal status {EXPIRED!r}",
        }
    ]
    assert reconcile_dividend_earmarks(store, now=_NOW) == []
    assert dividend_reinvest_status(store)["available_total"] == "500"


def test_reconcile_consumes_a_filled_proposal(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    _force_status(store, proposal_id, FILLED)
    transitions = reconcile_dividend_earmarks(store, now=_NOW)
    assert transitions[0]["action"] == "consumed"
    assert dividend_reinvest_status(store)["available_total"] == "200"


def test_reconcile_holds_an_ambiguous_submission(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    _force_status(store, proposal_id, SUBMISSION_UNKNOWN)
    assert reconcile_dividend_earmarks(store, now=_NOW) == []
    row = store.list_dividend_earmarks()[0]
    assert row["status"] == "active"
    assert dividend_reinvest_status(store)["available_total"] == "200"


def test_reconcile_holds_and_names_an_earmark_whose_proposal_vanished(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    with store._connect() as connection:  # simulate corruption
        connection.execute(
            "DELETE FROM trade_proposals WHERE proposal_id = ?", (proposal_id,)
        )
    transitions = reconcile_dividend_earmarks(store, now=_NOW)
    assert transitions[0]["action"] == "held"
    assert store.list_dividend_earmarks()[0]["status"] == "active"


def test_a_canceled_proposal_with_a_partial_fill_consumes_not_releases(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    _plant_fill_event(store, proposal_id, fill_qty=2)
    _force_status(store, proposal_id, CANCELED)
    transitions = reconcile_dividend_earmarks(store, now=_NOW)
    assert transitions[0]["action"] == "consumed"
    assert "recorded fill quantity" in transitions[0]["reason"]
    assert dividend_reinvest_status(store)["available_total"] == "200"


def test_poll_only_cumulative_fill_consumes_a_canceled_earmark(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    _plant_cumulative_fill_event(store, proposal_id, filled_qty=2)
    _force_status(store, proposal_id, CANCELED)

    transitions = reconcile_dividend_earmarks(store, now=_NOW)

    assert transitions[0]["action"] == "consumed"
    assert dividend_reinvest_status(store)["available_total"] == "200"


def test_fill_evidence_overrides_a_nominal_release_status():
    # The lifecycle transition table permits BROKER_REJECTED after a partial
    # fill. Once any share filled, the dividend dollars cannot return to pool.
    assert earmark_disposition(BROKER_REJECTED, fill_evidence=True) == "consume"


def test_a_canceled_proposal_with_no_fill_releases(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    _force_status(store, proposal_id, CANCELED)
    transitions = reconcile_dividend_earmarks(store, now=_NOW)
    assert transitions[0]["action"] == "released"
    assert dividend_reinvest_status(store)["available_total"] == "500"


# --- read-only status honesty ----------------------------------------------


def test_status_derives_an_expired_earmark_as_available_before_reconcile(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    _force_status(store, proposal_id, EXPIRED)
    status = dividend_reinvest_status(store)
    assert status["available_total"] == "500"
    assert status["earmarks"][0]["effective_disposition"] == "release"
    assert status["earmarks"][0]["status"] == "active"  # durable row untouched


def test_status_is_read_only(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    _force_status(store, proposal_id, EXPIRED)

    def _counts():
        with store._connect() as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            return {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in tables
            }

    before = _counts()
    dividend_reinvest_status(store)
    assert _counts() == before
    assert store.list_dividend_earmarks()[0]["status"] == "active"


def test_the_write_path_touches_only_its_own_tables(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")

    def _counts():
        with store._connect() as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            return {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in tables
            }

    before = _counts()
    assert _create(store)["created"] is True
    after = _counts()
    changed = {table for table in after if after[table] != before[table]}
    assert changed <= {"trade_proposals", "sleeve_dividend_earmarks"}, changed


# --- payload hygiene -------------------------------------------------------


def _all_keys(value, prefix=""):
    keys = []
    if isinstance(value, dict):
        for key, inner in value.items():
            keys.append(f"{prefix}.{key}" if prefix else str(key))
            keys.extend(_all_keys(inner, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for inner in value:
            keys.extend(_all_keys(inner, prefix))
    return keys


def test_status_payload_carries_no_action_shaped_key(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store)
    store.save_sleeve_watch_states([_watch_row(DECLINE_REVIEW, "AMD")])
    status = dividend_reinvest_status(store)
    forbidden = ("buy", "sell", "order", "recommend", "suggest", "should", "trade")
    offending = [
        key
        for key in _all_keys(status)
        if any(word in key.rsplit(".", 1)[-1].lower() for word in forbidden)
    ]
    assert not offending, offending


def test_status_payload_is_json_serializable(tmp_path):
    import json

    store = _store(tmp_path)
    _seed_dividend(store)
    json.dumps(dividend_reinvest_status(store))


def test_the_two_routes_carry_distinct_evidence_statuses():
    assert EVIDENCE_STATUS_REINVEST != EVIDENCE_STATUS_DECLINE_ADD
    for status in (EVIDENCE_STATUS_REINVEST, EVIDENCE_STATUS_DECLINE_ADD):
        assert "confirmed" not in status


def test_the_proposal_names_its_earmark_and_release_rule(tmp_path):
    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal = _create(store)["proposal"]
    reasons = " ".join(proposal.reasons)
    assert "Earmarked" in reasons and "released" in reasons


# --- CLI surfaces ----------------------------------------------------------


def _table_counts(store):
    with store._connect() as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }


def test_cli_sleeve_reinvest_is_read_only_and_reports_the_pool(
    tmp_path, capsys
):
    import argparse
    import json

    import scripts.run_personal_assistant as cli

    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    proposal_id = _create(store)["proposal"].proposal_id
    _force_status(store, proposal_id, EXPIRED)

    before = _table_counts(store)
    cli.command_sleeve_reinvest(argparse.Namespace(json=True), store)
    assert _table_counts(store) == before, (
        "the status command must not write -- not even an earmark reconcile"
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["available_total"] == "500"
    assert payload["earmarks"][0]["effective_disposition"] == "release"


def test_cli_propose_refuses_without_a_fresh_price(tmp_path, monkeypatch):
    import argparse

    import scripts.run_personal_assistant as cli

    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    monkeypatch.setattr(cli, "load_policy", lambda *_args, **_kw: _policy())
    monkeypatch.setattr(cli, "_packet", lambda **_kw: _packet())
    import assistant.sleeve_notifications as sleeve_notifications

    monkeypatch.setattr(
        sleeve_notifications,
        "_recorded_close_fetcher",
        lambda _store, **_kw: (lambda _tickers: {}),
    )
    before = _table_counts(store)
    with pytest.raises(SystemExit, match="no fresh recorded close"):
        cli.command_sleeve_reinvest_propose(
            argparse.Namespace(
                ticker="NVDL", amount="300", json=False, policy=None
            ),
            store,
        )
    assert _table_counts(store) == before


def test_cli_propose_creates_the_proposal_and_earmark(
    tmp_path, monkeypatch, capsys
):
    import argparse

    import scripts.run_personal_assistant as cli

    store = _store(tmp_path)
    _seed_dividend(store, amount="500")
    monkeypatch.setattr(cli, "load_policy", lambda *_args, **_kw: _policy())
    monkeypatch.setattr(cli, "_packet", lambda **_kw: _packet())
    import assistant.sleeve_notifications as sleeve_notifications
    from decimal import Decimal

    monkeypatch.setattr(
        sleeve_notifications,
        "_recorded_close_fetcher",
        lambda _store, **_kw: (lambda _tickers: {"NVDL": Decimal("30")}),
    )
    cli.command_sleeve_reinvest_propose(
        argparse.Namespace(ticker="NVDL", amount="300", json=False, policy=None),
        store,
    )
    out = capsys.readouterr().out
    assert "Approve with:" in out
    earmarks = store.list_dividend_earmarks()
    assert len(earmarks) == 1 and earmarks[0]["status"] == "active"
    assert store.get_proposal(earmarks[0]["proposal_id"])["status"] == PROPOSED


def test_cli_propose_json_stays_valid_when_reconcile_emits_a_transition(
    tmp_path, monkeypatch, capsys
):
    import argparse
    import json
    from decimal import Decimal

    import scripts.run_personal_assistant as cli
    import assistant.sleeve_notifications as sleeve_notifications

    store = _store(tmp_path)
    _seed_dividend(store, amount="800")
    old_id = _create(store, ticker="SOXL")["proposal"].proposal_id
    _force_status(store, old_id, EXPIRED)
    monkeypatch.setattr(cli, "load_policy", lambda *_args, **_kw: _policy())
    monkeypatch.setattr(cli, "_packet", lambda **_kw: _packet())
    monkeypatch.setattr(
        sleeve_notifications,
        "_recorded_close_fetcher",
        lambda _store, **_kw: (lambda _tickers: {"NVDL": Decimal("30")}),
    )

    cli.command_sleeve_reinvest_propose(
        argparse.Namespace(ticker="NVDL", amount="300", json=True, policy=None),
        store,
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["earmark_transitions"][0]["proposal_id"] == old_id
    assert payload["earmark_transitions"][0]["action"] == "released"
