from datetime import datetime, timezone
from decimal import Decimal

import pytest

from assistant.order_lifecycle import journal_broker_order_update
from assistant.paper_evidence import (
    PaperEvidenceError,
    REQUIRED_PROMOTION_DRILLS,
    build_paper_lineage,
    capture_paper_account_observation,
    paper_evidence_summary,
    paper_session_schedule,
    record_operational_drill,
    start_paper_evidence_epoch,
)
from assistant.money import to_decimal
from assistant.portfolio_ledger import record_cash_transfer
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from assistant.storage import AssistantStore


def _lineage(commit: str = "a" * 40) -> dict[str, str]:
    return build_paper_lineage(
        code_commit=commit,
        mandate_fingerprint="b" * 64,
        policy_fingerprint="c" * 64,
        strategy_id="shared-capital-scanner",
        strategy_version="1.0.0",
        model_id="deterministic-no-model",
        broker_account_id="paper-account-1",
    )


def _snapshot(
    equity: float,
    *,
    account_mode: str = "paper",
    cash: float | None = None,
    positions: list[PortfolioPosition] | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        positions=list(positions or []),
        cash=equity if cash is None else cash,
        total_equity=equity,
        as_of="2026-07-29",
        buying_power=equity,
        source="alpaca",
        account_mode=account_mode,
        account_id="paper-account-1",
    )


def _reconcile(store: AssistantStore, at: datetime) -> None:
    store.record_ledger_reconciliation(
        f"recon-{at.date().isoformat()}",
        "alpaca",
        {
            "reconciliation_id": f"recon-{at.date().isoformat()}",
            "reconciled_at": at.isoformat(),
            "matched": True,
            "mismatch_count": 0,
            "broker": {"account_id": "paper-account-1"},
        },
    )


def _capture(
    store: AssistantStore,
    *,
    at: datetime,
    equity: float,
    benchmark_close: float,
) -> dict:
    _reconcile(store, at)
    return capture_paper_account_observation(
        store,
        _snapshot(equity),
        benchmark_ticker="SPY",
        benchmark_close=benchmark_close,
        captured_at=at,
        expected_lineage=_lineage(),
    )


def _proposal(proposal_id: str) -> dict:
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-07-29T14:00:00+00:00",
        "expires_at": "2026-07-30T14:00:00+00:00",
        "status": "submitting",
        "idempotency_key": f"idem-{proposal_id}",
        "intent": {
            "ticker": "AAPL",
            "side": "buy",
            "shares": 1,
            "order_type": "market",
            "limit_price": None,
        },
    }


def _record_order(
    store: AssistantStore, proposal_id: str, status: str, submitted_at: str
) -> None:
    store.save_proposal(_proposal(proposal_id))
    journal_broker_order_update(
        store,
        proposal_id,
        {
            "order_id": f"order-{proposal_id}",
            "client_order_id": f"idem-{proposal_id}",
            "ticker": "AAPL",
            "shares": 1,
            "side": "buy",
            "type": "market",
            "limit_price": None,
            "status": status,
            "filled_qty": 0,
            "filled_avg_price": None,
            "submitted_at": submitted_at,
            "updated_at": submitted_at,
        },
        event_type=status,
        external_event_id=f"event-{proposal_id}",
    )


def test_epoch_lineage_is_immutable_and_only_one_epoch_can_be_active(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    started = datetime(2026, 7, 29, 13, tzinfo=timezone.utc)
    first = start_paper_evidence_epoch(
        store, "paper-v1", _lineage(), started_at=started
    )
    repeated = start_paper_evidence_epoch(
        store, "paper-v1", _lineage(), started_at=started
    )
    assert first["already_started"] is False
    assert repeated["already_started"] is True

    with pytest.raises(ValueError, match="already active"):
        start_paper_evidence_epoch(
            store, "paper-v2", _lineage("d" * 40), started_at=started
        )

    store.close_paper_evidence_epoch(
        "paper-v1",
        ended_at=datetime(2026, 7, 31, tzinfo=timezone.utc).isoformat(),
    )
    second = start_paper_evidence_epoch(
        store, "paper-v2", _lineage("d" * 40), started_at=started
    )
    assert second["status"] == "active"


def test_paper_session_schedule_skips_non_trading_days():
    saturday = datetime(2026, 8, 1, 20, 30, tzinfo=timezone.utc)
    assert paper_session_schedule(saturday) is None


def test_observation_requires_paper_mode_recent_reconciliation_and_close(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        _lineage(),
        started_at=datetime(2026, 7, 29, 13, tzinfo=timezone.utc),
    )
    after_close = datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc)
    _reconcile(store, after_close)

    with pytest.raises(PaperEvidenceError, match="paper account"):
        capture_paper_account_observation(
            store,
            _snapshot(1_000, account_mode="live"),
            benchmark_ticker="SPY",
            benchmark_close=100,
            captured_at=after_close,
        )
    with pytest.raises(PaperEvidenceError, match="after the NYSE close"):
        capture_paper_account_observation(
            store,
            _snapshot(1_000),
            benchmark_ticker="SPY",
            benchmark_close=100,
            captured_at=datetime(
                2026, 7, 29, 19, 30, tzinfo=timezone.utc
            ),
        )

    recorded = capture_paper_account_observation(
        store,
        _snapshot(1_000),
        benchmark_ticker="SPY",
        benchmark_close=100,
        captured_at=after_close,
        expected_lineage=_lineage(),
    )
    repeated = capture_paper_account_observation(
        store,
        _snapshot(1_000),
        benchmark_ticker="SPY",
        benchmark_close=100,
        captured_at=after_close,
        expected_lineage=_lineage(),
    )
    assert recorded["already_recorded"] is False
    assert repeated["already_recorded"] is True
    assert recorded["portfolio_capture"]["already_recorded"] is False
    assert repeated["portfolio_capture"]["already_recorded"] is True
    assert recorded["portfolio_capture"]["position_count"] == 0

    later_retry = capture_paper_account_observation(
        store,
        _snapshot(1_500),
        benchmark_ticker="SPY",
        benchmark_close=110,
        captured_at=datetime(2026, 7, 29, 20, 40, tzinfo=timezone.utc),
        expected_lineage=_lineage(),
    )
    assert later_retry["observation_id"] == recorded["observation_id"]
    assert later_retry["total_equity"] == recorded["total_equity"]
    assert later_retry["already_recorded"] is True
    assert later_retry["portfolio_capture"]["capture_id"] == (
        recorded["portfolio_capture"]["capture_id"]
    )
    account_key = "alpaca:paper:paper-account-1"
    equity = store.list_portfolio_equity_snapshots(account_key)
    assert len(equity) == 1
    assert equity[0]["total_equity"] == "1000"
    assert store.list_portfolio_position_snapshots(account_key) == []
    assert len(store.list_portfolio_capture_sessions(account_key=account_key)) == 1


def test_paper_observation_populates_normalized_equity_positions_and_manifest(
    tmp_path,
):
    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        _lineage(),
        started_at=datetime(2026, 7, 29, 13, tzinfo=timezone.utc),
    )
    after_close = datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc)
    _reconcile(store, after_close)
    position = PortfolioPosition(
        ticker="AAPL",
        shares=2,
        entry_price=90,
        current_price=100,
        market_value=200,
        unrealized_pnl_pct=11.1111,
        is_leveraged_etf=False,
    )

    recorded = capture_paper_account_observation(
        store,
        _snapshot(1_000, cash=800, positions=[position]),
        benchmark_ticker="SPY",
        benchmark_close=500,
        captured_at=after_close,
        expected_lineage=_lineage(),
    )

    account_key = "alpaca:paper:paper-account-1"
    equity = store.list_portfolio_equity_snapshots(account_key)
    positions = store.list_portfolio_position_snapshots(account_key)
    captures = store.list_portfolio_capture_sessions(
        account_key=account_key,
        evidence_epoch="paper-v1",
    )
    assert len(equity) == 1
    assert equity[0]["total_equity"] == "1000"
    assert equity[0]["cash"] == "800"
    assert equity[0]["paper_observation_id"] == recorded["observation_id"]
    assert positions == [
        {
            "snapshot_id": positions[0]["snapshot_id"],
            "account_key": account_key,
            "session_date": "2026-07-29",
            "captured_at": after_close.isoformat(),
            "ticker": "AAPL",
            "shares": "2",
            "market_value": "200",
            "price": "100",
            "source": "alpaca",
            "snapshot_hash": positions[0]["snapshot_hash"],
        }
    ]
    assert len(captures) == 1
    assert captures[0]["observation_id"] == recorded["observation_id"]
    assert captures[0]["equity_snapshot_id"] == equity[0]["snapshot_id"]
    assert captures[0]["position_snapshot_ids"] == [positions[0]["snapshot_id"]]
    assert captures[0]["position_count"] == 1
    assert recorded["portfolio_capture"]["payload_hash"] == captures[0]["payload_hash"]


def test_retry_repairs_a_capture_that_failed_after_normalized_children(
    tmp_path,
    monkeypatch,
):
    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        _lineage(),
        started_at=datetime(2026, 7, 29, 13, tzinfo=timezone.utc),
    )
    after_close = datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc)
    _reconcile(store, after_close)
    original_append = store.append_portfolio_capture_session

    def fail_manifest_once(capture):
        raise RuntimeError("simulated crash before the completion manifest")

    monkeypatch.setattr(store, "append_portfolio_capture_session", fail_manifest_once)
    with pytest.raises(RuntimeError, match="simulated crash"):
        capture_paper_account_observation(
            store,
            _snapshot(1_000),
            benchmark_ticker="SPY",
            benchmark_close=500,
            captured_at=after_close,
            expected_lineage=_lineage(),
        )

    account_key = "alpaca:paper:paper-account-1"
    assert len(store.list_paper_account_observations("paper-v1")) == 1
    assert len(store.list_portfolio_equity_snapshots(account_key)) == 1
    assert store.list_portfolio_capture_sessions(account_key=account_key) == []

    monkeypatch.setattr(store, "append_portfolio_capture_session", original_append)
    repaired = capture_paper_account_observation(
        store,
        _snapshot(1_500),
        benchmark_ticker="SPY",
        benchmark_close=550,
        captured_at=datetime(2026, 7, 29, 20, 40, tzinfo=timezone.utc),
        expected_lineage=_lineage(),
    )

    assert to_decimal(repaired["total_equity"]) == Decimal("1000")
    assert repaired["portfolio_capture"]["already_recorded"] is False
    assert len(store.list_portfolio_capture_sessions(account_key=account_key)) == 1
    equity = store.list_portfolio_equity_snapshots(account_key)
    assert len(equity) == 1
    assert equity[0]["total_equity"] == "1000"


def test_observation_rejects_a_different_broker_account(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        _lineage(),
        started_at=datetime(2026, 7, 29, 13, tzinfo=timezone.utc),
    )
    after_close = datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc)
    _reconcile(store, after_close)
    snapshot = _snapshot(1_000)
    snapshot.account_id = "paper-account-2"

    with pytest.raises(PaperEvidenceError, match="active evidence epoch"):
        capture_paper_account_observation(
            store,
            snapshot,
            benchmark_ticker="SPY",
            benchmark_close=100,
            captured_at=after_close,
        )


def test_broker_decimal_precision_survives_into_immutable_evidence(tmp_path):
    """Sub-cent broker precision must reach the normalized ML tables intact.

    Paper observations are immutable: precision discarded at write time can
    never be reconstructed. These share/price values are chosen so that a
    float round-trip visibly loses digits, which is what happened while the
    observation stored ``float(...)`` and the normalized tables then
    re-derived a Decimal from the already-damaged value.
    """
    shares = "3.141592653589793238"
    price = "197.339999999999999999"
    market_value = str(Decimal(shares) * Decimal(price))
    cash = "10000.005"

    position = PortfolioPosition(
        ticker="AAPL",
        shares=float(shares),
        entry_price=float(price),
        current_price=float(price),
        market_value=float(market_value),
        unrealized_pnl_pct=0.0,
        is_leveraged_etf=False,
        shares_exact=shares,
        entry_price_exact=price,
        current_price_exact=price,
        market_value_exact=market_value,
    )
    equity_exact = str(Decimal(cash) + Decimal(market_value))
    snapshot = PortfolioSnapshot(
        positions=[position],
        cash=float(cash),
        total_equity=float(equity_exact),
        as_of="2026-07-29",
        buying_power=float(cash),
        source="alpaca",
        account_mode="paper",
        account_id="paper-account-1",
        cash_exact=cash,
        total_equity_exact=equity_exact,
        buying_power_exact=cash,
    )
    assert snapshot.has_exact_numerics is True
    # Guard the premise: these values really do not survive a float trip.
    assert to_decimal(float(shares)) != Decimal(shares)
    assert to_decimal(float(market_value)) != Decimal(market_value)
    assert to_decimal(float(equity_exact)) != Decimal(equity_exact)

    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        _lineage(),
        started_at=datetime(2026, 7, 28, 13, tzinfo=timezone.utc),
    )
    at = datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc)
    _reconcile(store, at)
    recorded = capture_paper_account_observation(
        store,
        snapshot,
        benchmark_ticker="SPY",
        benchmark_close=550,
        captured_at=at,
        expected_lineage=_lineage(),
    )

    assert recorded["exact_numerics"] is True
    assert to_decimal(recorded["cash"]) == Decimal(cash)
    assert to_decimal(recorded["total_equity"]) == Decimal(equity_exact)
    assert to_decimal(recorded["positions"][0]["shares"]) == Decimal(shares)
    assert to_decimal(
        recorded["positions"][0]["market_value"]
    ) == Decimal(market_value)

    # ...and into the normalized rows the portfolio ML target builder reads.
    account_key = (
        f"{recorded['source']}:{recorded['account_mode']}:{recorded['account_id']}"
    )
    equity_rows = store.list_portfolio_equity_snapshots(account_key)
    assert len(equity_rows) == 1
    assert to_decimal(equity_rows[0]["total_equity"]) == Decimal(equity_exact)
    assert to_decimal(equity_rows[0]["cash"]) == Decimal(cash)

    position_rows = store.list_portfolio_position_snapshots(account_key)
    assert len(position_rows) == 1
    assert to_decimal(position_rows[0]["shares"]) == Decimal(shares)
    assert to_decimal(position_rows[0]["market_value"]) == Decimal(market_value)


def test_snapshot_without_preserved_decimals_is_recorded_as_inexact(tmp_path):
    """A snapshot with no exact fields must say so rather than imply exactness."""
    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        _lineage(),
        started_at=datetime(2026, 7, 28, 13, tzinfo=timezone.utc),
    )
    recorded = _capture(
        store,
        at=datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc),
        equity=1_000,
        benchmark_close=100,
    )
    assert recorded["exact_numerics"] is False
    assert recorded["schema_version"] == "1.2"


def test_external_flow_accumulates_exactly_not_in_binary_float(tmp_path):
    """Several exact cent transfers must not accumulate float error.

    These four amounts sum to exactly 10000.30, but ``flow += float(amount)``
    accumulates to 10000.300000000001. The normalized portfolio tables store
    whatever this field holds as "the broker's decimal value", and the
    flow-adjusted return series subtracts it from equity, so the error would
    be preserved and compounded rather than caught.
    """
    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        _lineage(),
        started_at=datetime(2026, 7, 28, 13, tzinfo=timezone.utc),
    )
    _capture(
        store,
        at=datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc),
        equity=1_000,
        benchmark_close=100,
    )

    amounts = ("1234.57", "8765.43", "0.10", "0.20")
    for index, amount in enumerate(amounts):
        record_cash_transfer(
            store,
            external_id=f"deposit-{index}",
            amount=amount,
            occurred_at=f"2026-07-30T15:0{index}:00+00:00",
            description="Exact cent deposit",
        )

    # Guard the premise: this set really is float-inexact.
    naive = 0.0
    for amount in amounts:
        naive += float(amount)
    assert naive != float(Decimal("10000.30"))

    second = _capture(
        store,
        at=datetime(2026, 7, 30, 20, 30, tzinfo=timezone.utc),
        equity=11_000,
        benchmark_close=101,
    )

    assert to_decimal(second["net_external_flow"]) == Decimal("10000.30")
    # The normalized row that ML portfolio research reads must agree exactly.
    account_key = (
        f"{second['source']}:{second['account_mode']}:{second['account_id']}"
    )
    equity_rows = store.list_portfolio_equity_snapshots(account_key)
    captured = [
        row
        for row in equity_rows
        if row["session_date"] == second["session_date"]
    ]
    assert len(captured) == 1
    assert to_decimal(captured[0]["net_external_flow"]) == Decimal("10000.30")


def test_summary_adjusts_external_flows_counts_orders_and_requires_coverage(
    tmp_path,
):
    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        _lineage(),
        started_at=datetime(2026, 7, 28, 13, tzinfo=timezone.utc),
    )
    _record_order(
        store,
        "pre-observation",
        "accepted",
        "2026-07-28T15:00:00+00:00",
    )
    _capture(
        store,
        at=datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc),
        equity=1_000,
        benchmark_close=100,
    )
    record_cash_transfer(
        store,
        external_id="deposit-1",
        amount=100,
        occurred_at="2026-07-30T15:00:00+00:00",
        description="Paper evidence deposit",
    )
    _record_order(
        store, "p-accepted", "accepted", "2026-07-30T15:30:00+00:00"
    )
    _record_order(
        store, "p-rejected", "rejected", "2026-07-30T16:00:00+00:00"
    )
    second = _capture(
        store,
        at=datetime(2026, 7, 30, 20, 30, tzinfo=timezone.utc),
        equity=1_110,
        benchmark_close=101,
    )
    _capture(
        store,
        at=datetime(2026, 7, 31, 20, 30, tzinfo=timezone.utc),
        equity=1_121.10,
        benchmark_close=102,
    )

    summary = paper_evidence_summary(store, "paper-v1")
    assert to_decimal(second["net_external_flow"]) == Decimal("100")
    assert summary["paper_sessions"] == 3
    assert summary["coverage_complete"] is True
    assert summary["paper_orders"]["count"] == 2
    assert summary["paper_orders"]["status_counts"] == {
        "accepted": 1,
        "rejected": 1,
    }
    assert summary["metrics"]["sessions"] == 3
    assert summary["lineage_consistent"] is True


def test_latest_drill_result_controls_promotion_evidence(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        _lineage(),
        started_at=datetime(2026, 7, 29, 13, tzinfo=timezone.utc),
    )
    base = datetime(2026, 7, 29, 14, tzinfo=timezone.utc)
    with pytest.raises(PaperEvidenceError, match="evidence.operator"):
        record_operational_drill(
            store,
            drill_type="kill_switch",
            passed=True,
            performed_at=base,
            evidence={"artifact": "missing-operator.log"},
        )
    for index, drill_type in enumerate(REQUIRED_PROMOTION_DRILLS):
        record_operational_drill(
            store,
            drill_type=drill_type,
            passed=True,
            performed_at=base.replace(hour=14 + index),
            evidence={"operator": "test", "artifact": f"{drill_type}.log"},
        )
    assert paper_evidence_summary(store)["all_required_drills_passed"] is True

    record_operational_drill(
        store,
        drill_type="restart_recovery",
        passed=False,
        performed_at=datetime(2026, 7, 30, 14, tzinfo=timezone.utc),
        evidence={"operator": "test", "artifact": "failed-restart.log"},
    )
    summary = paper_evidence_summary(store)
    assert summary["all_required_drills_passed"] is False
    assert summary["required_drills"]["restart_recovery"]["passed"] is False
