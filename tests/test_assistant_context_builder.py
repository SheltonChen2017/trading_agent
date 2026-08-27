"""
Sanity tests for assistant/context_builder.py and schemas.py. Run with:
python tests/test_assistant_context_builder.py
"""
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import execution.alpaca_broker as broker
from assistant.context_builder import (
    build_decision_packet,
    build_portfolio_snapshot,
    build_portfolio_snapshot_from_alpaca,
    build_risk_exposure,
    get_relevant_signal_evidence,
    get_upcoming_events,
)
from assistant.schemas import EvidenceStatus


def test_build_portfolio_snapshot_rejects_non_finite_position_numbers():
    # Independent review, 2026-07-29, reproduced: a single NaN current_price
    # made market_value NaN -> total_equity NaN -> every downstream `>`/`<=`
    # comparison silently False. generate_risk_reduction_proposals() then
    # returned ZERO proposals for an over-concentrated portfolio and
    # reported nothing wrong. Fail loudly at the boundary instead.
    for field, bad in [
        ("current_price", float("nan")),
        ("current_price", float("inf")),
        ("shares", float("nan")),
        ("entry_price", float("nan")),
    ]:
        row = {"ticker": "AAA", "shares": 10, "entry_price": 100.0, "current_price": 110.0}
        row[field] = bad
        try:
            build_portfolio_snapshot([row], cash=1_000.0)
            assert False, f"expected a non-finite {field}={bad!r} to be rejected"
        except ValueError as exc:
            assert field in str(exc)


def test_build_portfolio_snapshot_still_accepts_ordinary_numbers():
    snapshot = build_portfolio_snapshot(
        [{"ticker": "AAA", "shares": 10, "entry_price": 100.0, "current_price": 110.0}], cash=1_000.0,
    )
    assert snapshot.total_equity == 2_100.0


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


def test_build_portfolio_snapshot_uppercases_and_strips_ticker():
    positions = [{"ticker": "  aapl  ", "shares": 10, "entry_price": 100.0, "current_price": 100.0}]
    snapshot = build_portfolio_snapshot(positions, cash=0.0)
    assert [p.ticker for p in snapshot.positions] == ["AAPL"]


def test_build_portfolio_snapshot_lowercase_aapl_counts_toward_tech_basket():
    # Independent review reproduction: a manually-supplied lowercase
    # "aapl" position used to be invisible to case-sensitive basket
    # membership checks even though it's economically the same exposure
    # as uppercase "AAPL".
    positions = [{"ticker": "aapl", "shares": 50, "entry_price": 100.0, "current_price": 100.0}]
    snapshot = build_portfolio_snapshot(positions, cash=5000.0)
    risk = build_risk_exposure(snapshot, concentration_threshold_pct=40.0)
    assert "tech" in risk.basket_exposure_pct
    assert risk.basket_exposure_pct["tech"] == 50.0
    assert any("tech" in w for w in risk.concentration_warnings)


def test_build_portfolio_snapshot_aggregates_duplicate_ticker_rows():
    # Independent review reproduction: two separate AAPL lots used to
    # remain two separate rows, each individually under a per-position
    # cap even though their combined exposure exceeds it.
    positions = [
        {"ticker": "AAPL", "shares": 3, "entry_price": 90.0, "current_price": 100.0},
        {"ticker": "aapl", "shares": 3, "entry_price": 90.0, "current_price": 100.0},
    ]
    snapshot = build_portfolio_snapshot(positions, cash=9400.0)
    assert len(snapshot.positions) == 1
    aapl = snapshot.positions[0]
    assert aapl.ticker == "AAPL"
    assert aapl.shares == 6
    assert aapl.market_value == 600.0
    assert abs(aapl.entry_price - 90.0) < 0.01
    assert snapshot.total_equity == 10000.0


def test_build_portfolio_snapshot_duplicate_rows_with_different_entry_prices_weight_average():
    positions = [
        {"ticker": "AAPL", "shares": 2, "entry_price": 100.0, "current_price": 150.0},
        {"ticker": "AAPL", "shares": 1, "entry_price": 130.0, "current_price": 150.0},
    ]
    snapshot = build_portfolio_snapshot(positions, cash=0.0)
    aapl = snapshot.positions[0]
    assert aapl.shares == 3
    # weighted-average cost basis: (2*100 + 1*130) / 3 = 110
    assert abs(aapl.entry_price - 110.0) < 0.01
    assert aapl.market_value == 450.0


def test_build_portfolio_snapshot_duplicate_rows_with_inconsistent_current_price_raises():
    positions = [
        {"ticker": "AAPL", "shares": 3, "entry_price": 90.0, "current_price": 100.0},
        {"ticker": "AAPL", "shares": 3, "entry_price": 90.0, "current_price": 101.0},
    ]
    try:
        build_portfolio_snapshot(positions, cash=0.0)
        assert False, "expected ValueError on inconsistent current_price"
    except ValueError:
        pass


def test_build_portfolio_snapshot_unique_uppercase_positions_unchanged():
    # Existing single-row, already-uppercase behavior must be exactly
    # preserved by the aggregation rewrite.
    positions = [
        {"ticker": "AAA", "shares": 10, "entry_price": 100.0, "current_price": 110.0},
        {"ticker": "BBB", "shares": 5, "entry_price": 200.0, "current_price": 180.0},
    ]
    snapshot = build_portfolio_snapshot(positions, cash=1000.0)
    aaa = next(p for p in snapshot.positions if p.ticker == "AAA")
    bbb = next(p for p in snapshot.positions if p.ticker == "BBB")
    assert aaa.market_value == 1100.0
    assert abs(aaa.unrealized_pnl_pct - 10.0) < 0.01
    assert bbb.market_value == 900.0
    assert abs(bbb.unrealized_pnl_pct - (-10.0)) < 0.01
    assert snapshot.total_equity == 1000.0 + 1100.0 + 900.0


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


def test_unexpected_optional_earnings_failure_degrades_to_unavailable(monkeypatch):
    import data.corporate_actions as corporate_actions
    import data.event_data as event_data

    def provider_down(_tickers):
        raise RuntimeError("provider down")

    monkeypatch.setattr(event_data, "fetch_upcoming_earnings", provider_down)
    monkeypatch.setattr(
        corporate_actions,
        "fetch_upcoming_ex_dividends",
        lambda tickers: {
            ticker: {
                "available": False,
                "days_away": None,
                "event_date": None,
                "source": "test",
                "fetched_at": None,
            }
            for ticker in tickers
        },
    )
    monkeypatch.setattr(event_data, "upcoming_quad_witching_dates", lambda: [])

    events = get_upcoming_events(["AAPL"], fetch_live=True)

    earnings = next(event for event in events if event.event_type == "earnings")
    assert earnings.ticker == "AAPL"
    assert earnings.status == EvidenceStatus.UNAVAILABLE
    assert earnings.days_away is None


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


def test_decision_packet_to_dict_reaches_nested_signal_authority_fields():
    # GPT review, 2026-07-30: _to_dict() used to call dataclasses.asdict(obj),
    # which recursively flattens EVERY nested dataclass (including a
    # SignalEvidence nested inside signals=[...]) into a plain dict before
    # this function's own isinstance(obj, SignalEvidence) check could ever
    # run on it -- so production_authoritative/display_status were present
    # on a bare _to_dict(finding) call but silently MISSING from
    # packet.to_dict()["signals"][0]. Reproduced directly here against a
    # real DecisionPacket (not just a bare SignalEvidence).
    from assistant.schemas import DecisionPacket, FindingProvenance, MarketRegime, SignalEvidence

    unreproduced_confirmed = SignalEvidence(
        label="Test finding", claim="Beats a baseline", status=EvidenceStatus.CONFIRMED,
        detail="...", source="test", relevant_tickers=[],
        provenance=FindingProvenance(
            actual_start_date="2019-07-22", actual_end_date="2026-07-28", actual_row_count=1764,
            entry_timing="next_open", data_fetched_at="2026-07-28T00:00:00+00:00",
            reproduced_after_data_loader_fix=False,
        ),
    )
    positions = [{"ticker": "AAA", "shares": 1, "entry_price": 10.0, "current_price": 11.0}]
    snapshot = build_portfolio_snapshot(positions, cash=50.0)
    risk = build_risk_exposure(snapshot)
    packet = DecisionPacket(
        generated_at="2026-01-01T00:00:00Z", portfolio=snapshot, risk=risk,
        regime=MarketRegime(benchmark_ticker="QQQ", trend=None, volatility_regime=None,
                             trailing_volatility_pct=None, as_of="2026-01-01"),
        signals=[unreproduced_confirmed], upcoming_events=[], warnings=[],
    )

    serialized = packet.to_dict()
    signal = serialized["signals"][0]
    assert signal["status"] == "confirmed"  # historical verdict preserved, not destroyed
    assert signal["production_authoritative"] is False
    assert "NOT CURRENTLY PRODUCTION-AUTHORITATIVE" in signal["display_status"]

    # Round-trip through SQLite (AssistantStore.save_decision_packet()).
    import json
    import sqlite3

    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        store.save_decision_packet(packet)
        conn = sqlite3.connect(store.path)
        try:
            row = conn.execute("SELECT payload_json FROM decision_packets ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        stored_signal = json.loads(row[0])["signals"][0]
        assert stored_signal["production_authoritative"] is False
        assert "NOT CURRENTLY PRODUCTION-AUTHORITATIVE" in stored_signal["display_status"]



# --- AssistantStore.save_decision_packet() identity, deduplication,
# and retention. Identity is (generated_at, payload_hash), NOT
# generated_at alone (GPT review, 2026-08-01): the UI's cached base
# packet and that same packet enriched with live events via
# dataclasses.replace(base_packet, upcoming_events=events) share
# generated_at but serialize to different payloads -- a generated_at-
# only unique key silently discarded whichever variant was saved
# second. payload_hash disambiguates those while generated_at still
# collapses genuinely IDENTICAL re-saves (e.g. a second browser tab)
# into one row rather than only living in UI session state.

def _decision_packet(generated_at: str, cash: float = 50.0, upcoming_events: list | None = None):
    from assistant.schemas import DecisionPacket, MarketRegime

    positions = [{"ticker": "AAA", "shares": 1, "entry_price": 10.0, "current_price": 11.0}]
    snapshot = build_portfolio_snapshot(positions, cash=cash)
    risk = build_risk_exposure(snapshot)
    return DecisionPacket(
        generated_at=generated_at, portfolio=snapshot, risk=risk,
        regime=MarketRegime(benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
                             trailing_volatility_pct=1.0, as_of="2026-01-01"),
        signals=[], upcoming_events=upcoming_events or [], warnings=[],
    )


def test_save_decision_packet_two_sessions_saving_the_same_packet_produce_one_row():
    from assistant.storage import AssistantStore

    packet = _decision_packet("2026-07-31T10:00:00+00:00")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "assistant.db"
        # Two separate AssistantStore instances stand in for two
        # independent browser-like sessions saving the exact same
        # st.cache_data-cached packet -- neither has any shared in-memory
        # state with the other.
        session_a = AssistantStore(db_path)
        session_b = AssistantStore(db_path)
        id_a = session_a.save_decision_packet(packet)
        id_b = session_b.save_decision_packet(packet)
        assert id_a == id_b  # same row, not a new duplicate

        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM decision_packets WHERE generated_at = ?", (packet.generated_at,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1


def test_save_decision_packet_two_different_timestamps_remain_separate():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        # Identical payload content aside from generated_at -- these
        # still hash the same modulo the timestamp field itself, but
        # remain two distinct historical observations.
        id_a = store.save_decision_packet(_decision_packet("2026-07-31T10:00:00+00:00"))
        id_b = store.save_decision_packet(_decision_packet("2026-07-31T10:00:15+00:00"))
        assert id_a != id_b

        conn = sqlite3.connect(store.path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM decision_packets").fetchone()[0]
        finally:
            conn.close()
        assert count == 2


def test_save_decision_packet_different_portfolio_content_at_same_timestamp_produces_two_rows():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        same_timestamp = "2026-07-31T10:00:00+00:00"
        id_a = store.save_decision_packet(_decision_packet(same_timestamp, cash=1000.0))
        id_b = store.save_decision_packet(_decision_packet(same_timestamp, cash=2000.0))
        assert id_a != id_b  # different payload_hash despite the shared timestamp

        conn = sqlite3.connect(store.path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM decision_packets WHERE generated_at = ?", (same_timestamp,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 2


def test_save_decision_packet_event_enrichment_receives_a_distinct_identity():
    # This is the exact collision GPT reproduced: dataclasses.replace()
    # preserves generated_at while changing upcoming_events, and the
    # UI's Briefing tab can persist whichever variant -- base or
    # event-enriched -- happens to be the one it sees on a given rerun.
    import dataclasses

    from assistant.schemas import UpcomingEvent
    from assistant.storage import AssistantStore

    base = _decision_packet("2026-07-31T10:00:00+00:00", upcoming_events=[])
    event = UpcomingEvent(
        ticker="AAA", event_type="earnings", event_date="2026-08-05", days_away=5,
        status=EvidenceStatus.UNAVAILABLE,
    )
    enriched = dataclasses.replace(base, upcoming_events=[event])
    assert base.generated_at == enriched.generated_at  # the exact precondition for the collision

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        base_id = store.save_decision_packet(base)
        enriched_id = store.save_decision_packet(enriched)
        assert base_id != enriched_id

        conn = sqlite3.connect(store.path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM decision_packets WHERE generated_at = ?", (base.generated_at,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 2  # both the base snapshot and the enriched view survive, regardless of order


def test_save_decision_packet_exact_duplicate_insert_does_not_overwrite_the_original_payload():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "assistant.db"
        store = AssistantStore(db_path)
        original = _decision_packet("2026-07-31T10:00:00+00:00", cash=50.0)
        first_id = store.save_decision_packet(original)
        # The EXACT same object/content saved again -- not a different
        # payload sharing a timestamp, which is covered separately above.
        second_id = store.save_decision_packet(original)
        assert first_id == second_id

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT payload_json FROM decision_packets WHERE generated_at = ?", (original.generated_at,)
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        stored_cash = json.loads(rows[0]["payload_json"])["portfolio"]["cash"]
        assert stored_cash == 50.0


def test_migration_preserves_distinct_payloads_sharing_a_generated_at():
    # Regression guard for the migration's dedup step itself: a
    # pre-existing (pre-payload_hash-column) database could contain a
    # genuine base/enriched collision under the OLD generated_at-only
    # scheme -- the migration must collapse only the exact duplicate
    # pair, never the differing third row.
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "assistant.db"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "CREATE TABLE decision_packets (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "generated_at TEXT NOT NULL, schema_version TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            same_timestamp = "2026-07-31T10:00:00+00:00"
            for payload in ('{"a": 1}', '{"a": 1}', '{"a": 2}'):  # rows 1&2 identical, row 3 differs
                conn.execute(
                    "INSERT INTO decision_packets(generated_at, schema_version, payload_json) VALUES (?, ?, ?)",
                    (same_timestamp, "2.0", payload),
                )
            conn.commit()
        finally:
            conn.close()

        store = AssistantStore(db_path)  # migration runs here
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT payload_json FROM decision_packets").fetchall()
        finally:
            conn.close()
        assert len(rows) == 2  # the exact duplicate collapsed; the distinct payload survived
        assert {r["payload_json"] for r in rows} == {'{"a": 1}', '{"a": 2}'}


def test_prune_decision_packets_older_than_deletes_both_base_and_enriched_variants():
    import dataclasses

    from assistant.schemas import UpcomingEvent
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        old_base = _decision_packet("2020-01-01T00:00:00+00:00", upcoming_events=[])
        old_enriched = dataclasses.replace(
            old_base, upcoming_events=[UpcomingEvent(
                ticker="AAA", event_type="earnings", event_date="2020-01-05", days_away=4,
                status=EvidenceStatus.UNAVAILABLE,
            )]
        )
        store.save_decision_packet(old_base)
        store.save_decision_packet(old_enriched)

        deleted = store.prune_decision_packets_older_than(days=30)
        assert deleted == 2

        conn = sqlite3.connect(store.path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM decision_packets").fetchone()[0]
        finally:
            conn.close()
        assert count == 0


def test_prune_decision_packets_older_than_deletes_only_old_rows():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        old_packet = _decision_packet("2020-01-01T00:00:00+00:00")
        recent_packet = _decision_packet(datetime.now(timezone.utc).isoformat())
        store.save_decision_packet(old_packet)
        store.save_decision_packet(recent_packet)

        deleted = store.prune_decision_packets_older_than(days=30)
        assert deleted == 1

        conn = sqlite3.connect(store.path)
        try:
            remaining = [
                r[0] for r in conn.execute("SELECT generated_at FROM decision_packets").fetchall()
            ]
        finally:
            conn.close()
        assert old_packet.generated_at not in remaining
        assert recent_packet.generated_at in remaining


def test_prune_decision_packets_rejects_non_positive_days():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        for bad_days in (0, -5):
            try:
                store.prune_decision_packets_older_than(days=bad_days)
                assert False, f"expected days={bad_days} to raise"
            except ValueError:
                pass


def test_prune_decision_packets_never_touches_proposals_or_broker_orders():
    # No FK relationship from trade_proposals/broker_orders to
    # decision_packets exists in this schema -- pruning must only ever
    # affect the decision_packets table.
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        store.save_decision_packet(_decision_packet("2020-01-01T00:00:00+00:00"))
        store.save_proposal(
            {
                "proposal_id": "tp_test", "created_at": "2020-01-01T00:00:00+00:00",
                "expires_at": "2099-01-01T00:00:00+00:00", "status": "proposed",
                "idempotency_key": "idem-test",
                "intent": {"ticker": "AAA", "side": "sell", "shares": 1},
            }
        )
        store.prune_decision_packets_older_than(days=1)
        assert store.get_proposal("tp_test") is not None


# --- strategy_evaluations table (docs/Archive/Plans/ALLOCATION_SERVICE_DESIGN.md,
# 2026-07-28): persisted "last evaluated" bookkeeping for strategy
# proposal generators, closing a gap assistant/strategy_proposals.py's
# generate_soxx_soxl_rebalance_proposals() already documented.

def test_record_and_get_strategy_evaluation_round_trips():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        assert store.get_last_strategy_evaluation("soxx_soxl_rebalance") is None
        store.record_strategy_evaluation(
            "soxx_soxl_rebalance", "2026-08-01T10:00:00+00:00", {"fired": True, "proposal_count": 1},
        )
        result = store.get_last_strategy_evaluation("soxx_soxl_rebalance")
        assert result["last_evaluated_at"] == "2026-08-01T10:00:00+00:00"
        assert result["last_result"] == {"fired": True, "proposal_count": 1}


def test_record_strategy_evaluation_overwrites_the_previous_row():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        store.record_strategy_evaluation("soxx_soxl_rebalance", "2026-08-01T10:00:00+00:00", {"fired": False})
        store.record_strategy_evaluation("soxx_soxl_rebalance", "2026-08-01T11:00:00+00:00", {"fired": True})
        result = store.get_last_strategy_evaluation("soxx_soxl_rebalance")
        assert result["last_evaluated_at"] == "2026-08-01T11:00:00+00:00"
        assert result["last_result"] == {"fired": True}

        conn = sqlite3.connect(store.path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM strategy_evaluations").fetchone()[0]
        finally:
            conn.close()
        assert count == 1  # overwritten, not a second row


# --- ai_runs table (independent review: AI runs were not persisted
# anywhere -- no model, prompt version, input hash, latency, or response
# was recorded, making the AI advisory layer unauditable after the fact).
# Unlike strategy_evaluations, this IS meant to accumulate as a log.

def test_record_and_list_ai_run_round_trips():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        assert store.list_ai_runs() == []
        store.record_ai_run(
            function_name="review_allocation_plan", model="claude-opus-5", prompt_version="v1",
            input_hash="abc123", latency_ms=42.5, success=True, response={"summary": "ok"},
        )
        runs = store.list_ai_runs()
        assert len(runs) == 1
        run = runs[0]
        assert run["function_name"] == "review_allocation_plan"
        assert run["model"] == "claude-opus-5"
        assert run["prompt_version"] == "v1"
        assert run["input_hash"] == "abc123"
        assert run["latency_ms"] == 42.5
        assert run["success"] is True
        assert run["response"] == {"summary": "ok"}
        assert run["error"] is None


def test_record_ai_run_persists_failures_with_error_and_no_response():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        store.record_ai_run(
            function_name="suggest_similar_tickers", model="claude-opus-5", prompt_version="v1",
            input_hash="def456", latency_ms=10.0, success=False, error="API error",
        )
        run = store.list_ai_runs()[0]
        assert run["success"] is False
        assert run["error"] == "API error"
        assert run["response"] is None


def test_ai_runs_accumulate_rather_than_overwrite():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        for i in range(3):
            store.record_ai_run(
                function_name="suggest_similar_tickers", model="claude-opus-5", prompt_version="v1",
                input_hash=f"hash{i}", latency_ms=1.0, success=True,
            )
        assert len(store.list_ai_runs()) == 3


def test_list_ai_runs_filters_by_function_name():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        store.record_ai_run(function_name="review_allocation_plan", model="claude-opus-5", prompt_version="v1", input_hash="a", latency_ms=1.0, success=True)
        store.record_ai_run(function_name="suggest_similar_tickers", model="claude-opus-5", prompt_version="v1", input_hash="b", latency_ms=1.0, success=True)
        runs = store.list_ai_runs(function_name="review_allocation_plan")
        assert len(runs) == 1
        assert runs[0]["function_name"] == "review_allocation_plan"


def test_list_ai_runs_respects_limit_and_newest_first():
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        for i in range(5):
            store.record_ai_run(function_name="suggest_similar_tickers", model="claude-opus-5", prompt_version="v1", input_hash=str(i), latency_ms=1.0, success=True)
        runs = store.list_ai_runs(limit=2)
        assert len(runs) == 2
        assert runs[0]["input_hash"] == "4"  # newest first
        assert runs[1]["input_hash"] == "3"


def test_pruning_a_pre_existing_db_with_duplicate_generated_at_rows_does_not_crash():
    # Regression guard for the migration itself: a pre-existing database
    # (from before this fix) could already contain duplicate generated_at
    # rows -- CREATE UNIQUE INDEX would fail outright on those. Confirms
    # _initialize()'s deduplication-before-indexing runs safely by
    # manually inserting duplicates through a raw connection (bypassing
    # save_decision_packet()'s own dedup logic) before AssistantStore
    # ever creates the unique index, then re-opening the store.
    from assistant.storage import AssistantStore

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "assistant.db"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "CREATE TABLE decision_packets (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "generated_at TEXT NOT NULL, schema_version TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO decision_packets(generated_at, schema_version, payload_json) VALUES (?, ?, ?)",
                ("2026-07-31T10:00:00+00:00", "2.0", "{}"),
            )
            conn.execute(
                "INSERT INTO decision_packets(generated_at, schema_version, payload_json) VALUES (?, ?, ?)",
                ("2026-07-31T10:00:00+00:00", "2.0", "{}"),
            )
            conn.commit()
        finally:
            conn.close()

        store = AssistantStore(db_path)  # must not raise despite the pre-existing duplicate
        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM decision_packets").fetchone()[0]
        finally:
            conn.close()
        assert count == 1


def test_build_portfolio_snapshot_from_alpaca_uses_broker_data():
    original_get_account = broker.get_account
    original_get_positions = broker.get_open_positions
    try:
        broker.get_account = lambda: {
            "account_id": "paper-account-1",
            "equity": 1000.0,
            "cash": 200.0,
            "buying_power": 200.0,
            "paper": True,
        }
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
        broker.get_account = lambda: {
            "account_id": "paper-account-1",
            "equity": 1000.0,
            "cash": 300.0,
            "buying_power": 300.0,
            "paper": True,
        }
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


if __name__ == "__main__":
    test_build_portfolio_snapshot_computes_market_value_and_pnl()
    test_build_portfolio_snapshot_flags_leveraged_etfs()
    test_build_portfolio_snapshot_uppercases_and_strips_ticker()
    test_build_portfolio_snapshot_lowercase_aapl_counts_toward_tech_basket()
    test_build_portfolio_snapshot_aggregates_duplicate_ticker_rows()
    test_build_portfolio_snapshot_duplicate_rows_with_different_entry_prices_weight_average()
    test_build_portfolio_snapshot_duplicate_rows_with_inconsistent_current_price_raises()
    test_build_portfolio_snapshot_unique_uppercase_positions_unchanged()
    test_build_risk_exposure_flags_basket_concentration()
    test_build_risk_exposure_flags_leveraged_etf_exposure()
    test_get_relevant_signal_evidence_includes_project_wide_and_ticker_specific()
    test_get_upcoming_events_are_unavailable_without_a_calendar_feed()
    test_decision_packet_to_dict_is_json_serializable()
    test_decision_packet_to_dict_reaches_nested_signal_authority_fields()
    test_save_decision_packet_two_sessions_saving_the_same_packet_produce_one_row()
    test_save_decision_packet_two_different_timestamps_remain_separate()
    test_save_decision_packet_different_portfolio_content_at_same_timestamp_produces_two_rows()
    test_save_decision_packet_event_enrichment_receives_a_distinct_identity()
    test_save_decision_packet_exact_duplicate_insert_does_not_overwrite_the_original_payload()
    test_migration_preserves_distinct_payloads_sharing_a_generated_at()
    test_prune_decision_packets_older_than_deletes_both_base_and_enriched_variants()
    test_prune_decision_packets_older_than_deletes_only_old_rows()
    test_prune_decision_packets_rejects_non_positive_days()
    test_prune_decision_packets_never_touches_proposals_or_broker_orders()
    test_record_and_get_strategy_evaluation_round_trips()
    test_record_strategy_evaluation_overwrites_the_previous_row()
    test_record_and_list_ai_run_round_trips()
    test_record_ai_run_persists_failures_with_error_and_no_response()
    test_ai_runs_accumulate_rather_than_overwrite()
    test_list_ai_runs_filters_by_function_name()
    test_list_ai_runs_respects_limit_and_newest_first()
    test_pruning_a_pre_existing_db_with_duplicate_generated_at_rows_does_not_crash()
    test_build_portfolio_snapshot_from_alpaca_uses_broker_data()
    test_build_decision_packet_falls_back_when_alpaca_not_configured()
    test_build_decision_packet_uses_live_alpaca_when_configured()
    print("All assistant context builder tests passed.")


def test_non_finite_total_equity_says_so_instead_of_reporting_no_warnings():
    """NaN loses every ordered comparison, so a `total <= 0` guard passes it
    through and every `pct > threshold` check is then False -- a portfolio 100%
    in one name reported ZERO concentration warnings and NaN percentages.
    build_portfolio_snapshot() rejects non-finite inputs so this is defence in
    depth, matching what risk/execution_gate.py and paper_evidence.py already
    do (2026-07-30)."""
    import dataclasses
    import math

    from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure

    healthy = build_portfolio_snapshot(
        [{"ticker": "NVDA", "shares": 100, "entry_price": 100.0, "current_price": 100.0}],
        cash=0.0,
    )
    assert build_risk_exposure(healthy).concentration_warnings, "setup: should warn"

    for bad in (float("nan"), float("inf")):
        corrupt = dataclasses.replace(healthy, total_equity=bad)
        exposure = build_risk_exposure(corrupt)
        assert exposure.concentration_warnings, "must not report a clean portfolio"
        warning = exposure.concentration_warnings[0]
        assert warning.startswith("Portfolio integrity unavailable:")
        assert "finite decimal number" in warning
        assert math.isfinite(exposure.leveraged_etf_exposure_pct)
        assert math.isfinite(exposure.cash_pct)


def test_non_finite_total_equity_does_not_silently_suppress_risk_reduction():
    import dataclasses

    from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
    from assistant.policy import TradingPolicy
    from assistant.proposals import generate_risk_reduction_proposals
    from assistant.schemas import DecisionPacket, MarketRegime

    policy = TradingPolicy(
        version="t", name="t", execution_mode="paper", max_position_pct=0.20,
        max_total_exposure_pct=1.0, max_basket_pct=1.0, max_leveraged_etf_pct=1.0,
        min_cash_reserve_pct=0.0, max_order_value=500_000.0,
    )
    snapshot = build_portfolio_snapshot(
        [{"ticker": "NVDA", "shares": 100, "entry_price": 100.0, "current_price": 100.0}],
        cash=1000.0,
    )

    def packet_for(snap):
        return DecisionPacket(
            generated_at="2026-07-30T12:00:00+00:00", portfolio=snap,
            risk=build_risk_exposure(snap),
            regime=MarketRegime("QQQ", "uptrend", "low_vol", 1.0, "2026-07-29"),
            signals=[], upcoming_events=[], warnings=[], policy_version="t",
        )

    assert generate_risk_reduction_proposals(packet_for(snapshot), policy), "setup"
    corrupt = dataclasses.replace(snapshot, total_equity=float("nan"))
    # NOT a behavioural pin, and deliberately said so: removing the isfinite
    # guard in proposals.py still yields [], because every
    # `market_value > max_*_value` comparison against NaN is already False. The
    # guard changes intent, not output -- it makes "we refuse to reason about a
    # corrupt total" explicit instead of an accident of IEEE-754. Measured: that
    # mutation survives this assertion. Kept anyway to document the contract,
    # and to stop a future edit from computing something from the NaN.
    assert generate_risk_reduction_proposals(packet_for(corrupt), policy) == []
