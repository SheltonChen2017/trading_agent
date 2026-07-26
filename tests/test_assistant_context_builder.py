"""
Sanity tests for assistant/context_builder.py and schemas.py. Run with:
python tests/test_assistant_context_builder.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import execution.alpaca_broker as broker
from assistant.audit_log import append_decision_packet, read_decision_log
from assistant.context_builder import (
    build_decision_packet,
    build_portfolio_snapshot,
    build_portfolio_snapshot_from_alpaca,
    build_risk_exposure,
    get_relevant_signal_evidence,
    get_upcoming_events,
)
from assistant.schemas import EvidenceStatus


def test_build_portfolio_snapshot_computes_market_value_and_pnl():
    positions = [
        {"ticker": "AAA", "shares": 10, "entry_price": 100.0, "current_price": 110.0},
        {"ticker": "BBB", "shares": 5, "entry_price": 200.0, "current_price": 180.0},
    ]
    snapshot = build_portfolio_snapshot(positions, cash=1000.0)

    assert snapshot.cash == 1000.0
    aaa = next(p for p in snapshot.positions if p.ticker == "AAA")
    bbb = next(p for p in snapshot.positions if p.ticker == "BBB")
    assert aaa.market_value == 1100.0
    assert abs(aaa.unrealized_pnl_pct - 10.0) < 0.01
    assert bbb.market_value == 900.0
    assert abs(bbb.unrealized_pnl_pct - (-10.0)) < 0.01
    assert snapshot.total_equity == 1000.0 + 1100.0 + 900.0


def test_build_portfolio_snapshot_flags_leveraged_etfs():
    positions = [
        {"ticker": "TQQQ", "shares": 10, "entry_price": 50.0, "current_price": 60.0},
        {"ticker": "QQQ", "shares": 10, "entry_price": 400.0, "current_price": 420.0},
    ]
    snapshot = build_portfolio_snapshot(positions, cash=0.0)
    tqqq = next(p for p in snapshot.positions if p.ticker == "TQQQ")
    qqq = next(p for p in snapshot.positions if p.ticker == "QQQ")
    assert tqqq.is_leveraged_etf is True
    assert qqq.is_leveraged_etf is False


def test_build_risk_exposure_flags_basket_concentration():
    # NVDA + AMD together are >40% of a small portfolio and both live in
    # the "semiconductors" basket -- should trigger a concentration warning.
    positions = [
        {"ticker": "NVDA", "shares": 10, "entry_price": 100.0, "current_price": 100.0},
        {"ticker": "AMD", "shares": 10, "entry_price": 100.0, "current_price": 100.0},
        {"ticker": "KO", "shares": 10, "entry_price": 10.0, "current_price": 10.0},
    ]
    snapshot = build_portfolio_snapshot(positions, cash=500.0)
    risk = build_risk_exposure(snapshot, concentration_threshold_pct=40.0)

    assert "semiconductors" in risk.basket_exposure_pct
    assert risk.basket_exposure_pct["semiconductors"] > 40.0
    assert any("semiconductors" in w for w in risk.concentration_warnings)


def test_build_risk_exposure_flags_leveraged_etf_exposure():
    positions = [
        {"ticker": "TQQQ", "shares": 50, "entry_price": 50.0, "current_price": 50.0},  # $2500
        {"ticker": "KO", "shares": 10, "entry_price": 10.0, "current_price": 10.0},     # $100
    ]
    snapshot = build_portfolio_snapshot(positions, cash=100.0)  # total = 2700
    risk = build_risk_exposure(snapshot)

    assert risk.leveraged_etf_exposure_pct > 20.0
    assert any("Leveraged ETF" in w for w in risk.concentration_warnings)


def test_get_relevant_signal_evidence_includes_project_wide_and_ticker_specific():
    all_findings = get_relevant_signal_evidence(["SOXX", "SOXL"])
    tickers_covered = {t for e in all_findings for t in e.relevant_tickers}
    assert "SOXX" in tickers_covered or "SOXL" in tickers_covered
    # project-wide findings (empty relevant_tickers) should always be included
    assert any(e.relevant_tickers == [] for e in all_findings)

    no_match = get_relevant_signal_evidence(["ZZZZ"])
    # ticker-specific findings for other tickers should be excluded
    assert not any("QQQ" in e.relevant_tickers or "SOXX" in e.relevant_tickers for e in no_match)


def test_get_upcoming_events_are_unavailable_without_a_calendar_feed():
    events = get_upcoming_events(["AAPL", "MSFT"])
    assert len(events) == 2
    assert all(e.status == EvidenceStatus.UNAVAILABLE for e in events)


def test_decision_packet_to_dict_is_json_serializable():
    import json
    positions = [{"ticker": "AAA", "shares": 1, "entry_price": 10.0, "current_price": 11.0}]
    snapshot = build_portfolio_snapshot(positions, cash=50.0)
    risk = build_risk_exposure(snapshot)
    from assistant.schemas import DecisionPacket, MarketRegime
    packet = DecisionPacket(
        generated_at="2026-01-01T00:00:00Z", portfolio=snapshot, risk=risk,
        regime=MarketRegime(benchmark_ticker="QQQ", trend=None, volatility_regime=None,
                             trailing_volatility_pct=None, as_of="2026-01-01"),
        signals=get_relevant_signal_evidence(["AAA"]), upcoming_events=get_upcoming_events(["AAA"]),
        warnings=[],
    )
    serialized = json.dumps(packet.to_dict())
    assert "AAA" in serialized


def test_audit_log_round_trips_decision_packets():
    from assistant.schemas import DecisionPacket, MarketRegime
    positions = [{"ticker": "AAA", "shares": 1, "entry_price": 10.0, "current_price": 11.0}]
    snapshot = build_portfolio_snapshot(positions, cash=50.0)
    risk = build_risk_exposure(snapshot)
    packet = DecisionPacket(
        generated_at="2026-01-01T00:00:00Z", portfolio=snapshot, risk=risk,
        regime=MarketRegime(benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
                             trailing_volatility_pct=1.0, as_of="2026-01-01"),
        signals=[], upcoming_events=[], warnings=[],
    )
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "log.jsonl"
        append_decision_packet(packet, log_path=log_path)
        append_decision_packet(packet, log_path=log_path)
        entries = read_decision_log(log_path=log_path)
        assert len(entries) == 2
        assert entries[0]["portfolio"]["positions"][0]["ticker"] == "AAA"


def test_build_portfolio_snapshot_from_alpaca_uses_broker_data():
    original_get_account = broker.get_account
    original_get_positions = broker.get_open_positions
    try:
        broker.get_account = lambda: {"equity": 1000.0, "cash": 200.0, "buying_power": 200.0, "paper": True}
        broker.get_open_positions = lambda: [
            {"ticker": "AAA", "shares": 5.0, "avg_entry_price": 100.0, "current_price": 110.0, "unrealized_pl": 50.0},
        ]
        snapshot = build_portfolio_snapshot_from_alpaca()
        assert snapshot.cash == 200.0
        assert len(snapshot.positions) == 1
        assert snapshot.positions[0].ticker == "AAA"
        assert snapshot.positions[0].market_value == 550.0
    finally:
        broker.get_account = original_get_account
        broker.get_open_positions = original_get_positions


def test_build_decision_packet_falls_back_when_alpaca_not_configured():
    original_is_configured = broker.is_configured
    try:
        broker.is_configured = lambda: False
        packet = build_decision_packet(
            [{"ticker": "AAA", "shares": 1, "entry_price": 10.0, "current_price": 10.0}],
            cash=100.0, use_live_alpaca=True,
        )
        assert any("not configured" in w for w in packet.warnings)
        assert packet.portfolio.positions[0].ticker == "AAA"  # used the manual fallback data
    finally:
        broker.is_configured = original_is_configured


def test_build_decision_packet_uses_live_alpaca_when_configured():
    original_is_configured = broker.is_configured
    original_get_account = broker.get_account
    original_get_positions = broker.get_open_positions
    try:
        broker.is_configured = lambda: True
        broker.get_account = lambda: {"equity": 1000.0, "cash": 300.0, "buying_power": 300.0, "paper": True}
        broker.get_open_positions = lambda: [
            {"ticker": "ZZZ", "shares": 2.0, "avg_entry_price": 50.0, "current_price": 60.0, "unrealized_pl": 20.0},
        ]
        packet = build_decision_packet(use_live_alpaca=True)
        assert packet.portfolio.cash == 300.0
        assert packet.portfolio.positions[0].ticker == "ZZZ"
        assert not any("not configured" in w for w in packet.warnings)
    finally:
        broker.is_configured = original_is_configured
        broker.get_account = original_get_account
        broker.get_open_positions = original_get_positions


def test_read_decision_log_returns_empty_list_when_missing():
    assert read_decision_log(log_path=Path("this/path/does/not/exist.jsonl")) == []


if __name__ == "__main__":
    test_build_portfolio_snapshot_computes_market_value_and_pnl()
    test_build_portfolio_snapshot_flags_leveraged_etfs()
    test_build_risk_exposure_flags_basket_concentration()
    test_build_risk_exposure_flags_leveraged_etf_exposure()
    test_get_relevant_signal_evidence_includes_project_wide_and_ticker_specific()
    test_get_upcoming_events_are_unavailable_without_a_calendar_feed()
    test_decision_packet_to_dict_is_json_serializable()
    test_audit_log_round_trips_decision_packets()
    test_build_portfolio_snapshot_from_alpaca_uses_broker_data()
    test_build_decision_packet_falls_back_when_alpaca_not_configured()
    test_build_decision_packet_uses_live_alpaca_when_configured()
    test_read_decision_log_returns_empty_list_when_missing()
    print("All assistant context builder tests passed.")
