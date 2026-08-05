"""GR-4: data-layer honesty — recorded fetches, SLAs, alerts, adapter,
degradation, and split detection.

Pins the archived plan's section 9 contract: provider fetches are recorded
success-or-failure (an all-empty response is a FAILED fetch, never "no
tickers matched"); a failure streak raises a deduplicated operational
alert; daily-bar freshness is judged against the real NYSE calendar;
GR-0's data_integrity dimension derives from recorded evidence with no
caller-settable boolean; stale bars degrade the briefing VISIBLY and block
strategy proposals while leaving risk-reduction untouched; and a split
between snapshot and submit is detected by share-count reconciliation,
never a price heuristic. Nothing anywhere synthesizes a missing price.

Run with: python -m pytest tests/test_data_integrity.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_decision_packet
from assistant.corporate_actions import detect_split_like_share_mismatch
from assistant.data_integrity import (
    PROVIDER_ALERT_FAILURE_STREAK,
    build_data_layer_evidence,
    fetch_daily_bars_recorded,
    provider_health_fingerprint,
)
from assistant.platform_readiness import BLOCKED, READY, build_data_integrity
from assistant.storage import AssistantStore
from data.price_source import (
    YFinanceDailyBars,
    build_fetch_record,
    evaluate_bar_freshness,
    expected_latest_completed_session,
)

# A Wednesday evening after the NYSE close (20:00 UTC in August):
# the expected latest completed session is that same Wednesday.
NOW = datetime(2026, 8, 5, 22, 0, 0, tzinfo=timezone.utc)
EXPECTED_SESSION = "2026-08-05"


@pytest.fixture()
def store(tmp_path):
    return AssistantStore(tmp_path / "gr4.db")


def _bars(end: str, periods: int = 30) -> pd.DataFrame:
    index = pd.bdate_range(end=pd.Timestamp(end), periods=periods)
    frame = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1_000_000,
        },
        index=index,
    )
    return frame


class _FakeSource:
    provider_id = "fake-provider"
    provides_point_in_time_lineage = False

    def __init__(self, data=None, error: Exception | None = None):
        self.data = data if data is not None else {}
        self.error = error
        self.calls = 0

    def fetch_daily_bars(self, tickers, lookback_days):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.data


# --- calendar-based freshness ----------------------------------------------


def test_expected_session_is_calendar_correct():
    # Wednesday post-close -> Wednesday; Saturday -> Friday; Monday
    # pre-close -> the previous Friday.
    assert expected_latest_completed_session(NOW) == "2026-08-05"
    saturday = datetime(2026, 8, 8, 15, 0, tzinfo=timezone.utc)
    assert expected_latest_completed_session(saturday) == "2026-08-07"
    monday_premarket = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert expected_latest_completed_session(monday_premarket) == "2026-08-07"


def test_bar_freshness_verdicts():
    fresh = evaluate_bar_freshness(EXPECTED_SESSION, now=NOW)
    assert fresh.fresh and fresh.expected_session == EXPECTED_SESSION

    # An in-progress session's partial bar is fresher than required.
    intraday_now = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    partial = evaluate_bar_freshness("2026-08-05", now=intraday_now)
    assert partial.fresh

    stale = evaluate_bar_freshness("2026-08-01", now=NOW)
    assert not stale.fresh and "expected session" in stale.detail

    nothing = evaluate_bar_freshness(None, now=NOW)
    assert not nothing.fresh and nothing.detail == "no bars available"

    # Fail-closed on data from the future: never "extra fresh".
    future = evaluate_bar_freshness("2026-08-14", now=NOW)
    assert not future.fresh and "future-dated" in future.detail


@pytest.mark.parametrize(
    ("latest_session", "now"),
    [
        (
            "2026-08-08",
            datetime(2026, 8, 8, 15, 0, tzinfo=timezone.utc),
        ),  # Saturday
        (
            "2026-08-10",
            datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        ),  # Monday before open
    ],
)
def test_current_date_bar_is_fresh_only_during_a_real_open_session(
    latest_session, now
):
    freshness = evaluate_bar_freshness(latest_session, now=now)
    assert not freshness.fresh
    assert "not an in-progress NYSE session" in freshness.detail


# --- fetch records: honesty about what came back ---------------------------


def test_fetch_record_counts_missing_tickers_and_latest_session():
    source = _FakeSource()
    record = build_fetch_record(
        source,
        ["AAA", "BBB", "CCC"],
        {"AAA": _bars("2026-08-05"), "BBB": pd.DataFrame()},
        fetched_at=NOW,
    )
    assert record.ok
    assert record.returned_count == 1
    assert record.missing_tickers == ("BBB", "CCC")  # empty frame = missing
    assert record.latest_session == "2026-08-05"
    assert record.point_in_time_lineage is False


def test_all_empty_response_is_a_failed_fetch_not_zero_matches():
    """The silent-outage mode GR-4 removes: an empty dict is a provider
    failure presenting as data."""
    record = build_fetch_record(_FakeSource(), ["AAA"], {}, fetched_at=NOW)
    assert not record.ok
    assert record.error == "provider returned no usable data"
    assert record.latest_session is None


def test_provider_exception_is_recorded_without_leaking_detail():
    record = build_fetch_record(
        _FakeSource(),
        ["AAA"],
        None,
        error=RuntimeError("secret=abc host=internal"),
        fetched_at=NOW,
    )
    assert not record.ok
    assert record.error == "RuntimeError: provider fetch failed"
    assert "secret" not in record.error


def test_fetch_record_rejects_malformed_lineage_and_naive_time():
    source = _FakeSource({"AAA": _bars(EXPECTED_SESSION)})
    source.provides_point_in_time_lineage = "false"
    with pytest.raises(ValueError, match="provides_point_in_time_lineage"):
        build_fetch_record(
            source,
            ["AAA"],
            source.data,
            fetched_at=NOW,
        )

    source.provides_point_in_time_lineage = False
    with pytest.raises(ValueError, match="timezone-aware"):
        build_fetch_record(
            source,
            ["AAA"],
            source.data,
            fetched_at=NOW.replace(tzinfo=None),
        )


def test_yfinance_source_declares_non_point_in_time_lineage():
    """Mirrors ml/availability.py's honesty rule: adjusted history must
    never claim point-in-time lineage."""
    assert YFinanceDailyBars.provides_point_in_time_lineage is False
    assert YFinanceDailyBars.provider_id == "yfinance"


# --- recorded fetches + failure-streak alerting ----------------------------


def _open_provider_alerts(store):
    return [
        alert
        for alert in store.list_operational_alerts(status="open", limit=20)
        if alert["fingerprint"]
        == provider_health_fingerprint("fake-provider", "bar")
    ]


def test_successful_fetch_is_recorded_and_returned_unaltered(store):
    frame = _bars("2026-08-05")
    data = fetch_daily_bars_recorded(
        store, ["AAA"], 30, source=_FakeSource({"AAA": frame}), now=NOW
    )
    # Never synthesized, never filled: the exact provider frame comes back.
    assert data["AAA"] is frame
    records = store.list_provider_fetches(provider_id="fake-provider")
    assert len(records) == 1 and records[0]["ok"]
    assert records[0]["latest_session"] == "2026-08-05"


def test_failure_streak_raises_one_deduplicated_alert(store):
    failing = _FakeSource(error=ConnectionError("down"))
    for attempt in range(PROVIDER_ALERT_FAILURE_STREAK):
        result = fetch_daily_bars_recorded(
            store, ["AAA"], 30, source=failing, now=NOW
        )
        assert result == {}
        alerts = _open_provider_alerts(store)
        if attempt < PROVIDER_ALERT_FAILURE_STREAK - 1:
            assert not alerts, "alert must wait for the declared streak"
    assert len(_open_provider_alerts(store)) == 1
    # One more failure re-upserts the same fingerprint, never a second row.
    fetch_daily_bars_recorded(store, ["AAA"], 30, source=failing, now=NOW)
    assert len(_open_provider_alerts(store)) == 1


def test_success_breaks_the_failure_streak(store):
    failing = _FakeSource(error=ConnectionError("down"))
    fetch_daily_bars_recorded(store, ["AAA"], 30, source=failing, now=NOW)
    fetch_daily_bars_recorded(
        store, ["AAA"], 30, source=_FakeSource({"AAA": _bars("2026-08-05")}), now=NOW
    )
    fetch_daily_bars_recorded(store, ["AAA"], 30, source=failing, now=NOW)
    assert (
        store.consecutive_provider_failures(
            provider_id="fake-provider", data_class="bar"
        )
        == 1
    )
    assert not _open_provider_alerts(store)


def test_provider_fetch_storage_rejects_assertion_shaped_lineage(store):
    with pytest.raises(ValueError, match="point_in_time_lineage"):
        store.record_provider_fetch(
            provider_id="fake-provider",
            data_class="bar",
            fetched_at=NOW.isoformat(),
            requested_count=1,
            returned_count=1,
            missing_tickers=(),
            ok=True,
            error=None,
            point_in_time_lineage="false",
            latest_session=EXPECTED_SESSION,
        )


# --- the GR-0 adapter: evidence, never assertion ---------------------------


def test_no_recorded_fetches_blocks_every_check(store):
    evidence = build_data_layer_evidence(store, now=NOW)
    for name in ("price_freshness", "provider_health", "adjustment_honesty"):
        assert evidence[name]["ok"] is False
        assert "no recorded provider fetches" in evidence[name]["detail"]


def test_healthy_records_pass_all_three_checks(store):
    fetch_daily_bars_recorded(
        store, ["AAA"], 30, source=_FakeSource({"AAA": _bars(EXPECTED_SESSION)}), now=NOW
    )
    evidence = build_data_layer_evidence(store, now=NOW)
    assert evidence["price_freshness"]["ok"] is True
    assert evidence["provider_health"]["ok"] is True
    assert evidence["adjustment_honesty"]["ok"] is True
    # Honesty, not laundering: the non-PIT provider is named.
    assert "fake-provider" in str(
        evidence["adjustment_honesty"]["evidence"]["non_point_in_time_providers"]
    )


def test_stale_latest_fetch_fails_price_freshness_only(store):
    fetch_daily_bars_recorded(
        store, ["AAA"], 30, source=_FakeSource({"AAA": _bars("2026-08-01")}), now=NOW
    )
    evidence = build_data_layer_evidence(store, now=NOW)
    assert evidence["price_freshness"]["ok"] is False
    assert evidence["provider_health"]["ok"] is True


def test_failure_streak_fails_provider_health(store):
    failing = _FakeSource(error=ConnectionError("down"))
    for _ in range(PROVIDER_ALERT_FAILURE_STREAK):
        fetch_daily_bars_recorded(store, ["AAA"], 30, source=failing, now=NOW)
    evidence = build_data_layer_evidence(store, now=NOW)
    assert evidence["provider_health"]["ok"] is False


def test_platform_readiness_dimension_derives_from_the_store(store):
    # No store: blocked with an explicit no-evidence reason.
    dimension = build_data_integrity(None)
    assert dimension.status == BLOCKED

    # Empty store: still blocked -- absence of evidence is a blocker.
    assert build_data_integrity(store).status == BLOCKED

    # Healthy recorded evidence: the dimension finally becomes ready,
    # ending GR-0's blocked-by-design data placeholder.
    fetch_daily_bars_recorded(
        store,
        ["AAA"],
        30,
        source=_FakeSource({"AAA": _bars(expected_latest_completed_session())}),
    )
    assert build_data_integrity(store).status == READY


def test_platform_readiness_rejects_non_boolean_derived_verdicts(
    store, monkeypatch
):
    import assistant.data_integrity as data_integrity

    monkeypatch.setattr(
        data_integrity,
        "build_data_layer_evidence",
        lambda _store: {
            name: {"ok": "false", "detail": "malformed", "evidence": {}}
            for name in (
                "price_freshness",
                "provider_health",
                "adjustment_honesty",
            )
        },
    )
    dimension = build_data_integrity(store)
    assert dimension.status == BLOCKED
    assert all(check.ok is False for check in dimension.checks)
    assert all("malformed" in check.detail for check in dimension.checks)


# --- degradation surfaces ---------------------------------------------------


def _positions():
    return [
        {"ticker": "NVDA", "shares": 2, "entry_price": 100.0, "current_price": 120.0}
    ]


def test_stale_bars_render_a_visible_degradation_banner_warning(store, monkeypatch):
    import assistant.data_integrity as di

    monkeypatch.setattr(
        di,
        "YFinanceDailyBars",
        # 260 bars: enough history for the 200-day trend to compute, so the
        # regime is a REAL (stale) value rather than an unavailable one.
        lambda: _FakeSource({"QQQ": _bars("2026-07-28", periods=260)}),
    )
    packet = build_decision_packet(_positions(), 1_000.0, store=store)
    degraded = [w for w in packet.warnings if w.startswith("DATA DEGRADED:")]
    assert len(degraded) == 1
    assert "2026-07-28" in degraded[0]
    assert packet.data_freshness["market_bars_fresh"] is False
    # The stale numbers are still shown as-is -- never substituted.
    assert packet.regime.trend is not None


def test_stale_short_history_still_renders_the_degradation_banner(
    store, monkeypatch
):
    import assistant.data_integrity as di

    monkeypatch.setattr(
        di,
        "YFinanceDailyBars",
        lambda: _FakeSource({"QQQ": _bars("2026-07-28", periods=10)}),
    )
    packet = build_decision_packet(_positions(), 1_000.0, store=store)
    assert packet.regime.trend is None
    assert any(
        warning.startswith("DATA DEGRADED:")
        for warning in packet.warnings
    )
    assert packet.data_freshness["market_bars_fresh"] is False


def test_fresh_bars_produce_no_degradation_warning(store, monkeypatch):
    import assistant.data_integrity as di

    fresh_end = expected_latest_completed_session()
    monkeypatch.setattr(
        di,
        "YFinanceDailyBars",
        lambda: _FakeSource({"QQQ": _bars(fresh_end, periods=260)}),
    )
    packet = build_decision_packet(_positions(), 1_000.0, store=store)
    assert not [w for w in packet.warnings if w.startswith("DATA DEGRADED:")]
    assert packet.data_freshness["market_bars_fresh"] is True


def test_empty_provider_degrades_only_the_regime_surface(store, monkeypatch):
    """Plan 9.3: an empty provider response degrades exactly one surface;
    the briefing itself still renders (portfolio, risk, warnings)."""
    import assistant.data_integrity as di

    monkeypatch.setattr(
        di, "YFinanceDailyBars", lambda: _FakeSource(error=ConnectionError("down"))
    )
    packet = build_decision_packet(_positions(), 1_000.0, store=store)
    assert packet.regime.trend is None  # the one degraded surface
    assert packet.portfolio.total_equity > 0  # briefing still built
    assert any("Market regime" in w for w in packet.warnings)
    # And the outage is now evidence, not silence.
    records = store.list_provider_fetches(provider_id="fake-provider")
    assert len(records) == 1 and not records[0]["ok"]


def test_stale_bars_block_strategy_proposals_but_not_risk_reduction():
    """Plan 9.3: stale bars block the proposals that DEPEND on them while
    risk-reduction stays available. Risk-reduction proposals never consult
    daily bars, so the stale refusal is scoped to the strategy path."""
    from assistant.policy import TradingPolicy
    from assistant.strategy_proposals import (
        CONFIGURED_LEVERAGED_PAIRS,
        StaleMarketDataError,
        generate_leveraged_pair_rebalance_proposals,
    )

    pair = CONFIGURED_LEVERAGED_PAIRS[0]
    positions = [
        {"ticker": pair.stable_ticker, "shares": 10, "entry_price": 100.0, "current_price": 100.0},
        {"ticker": pair.leveraged_ticker, "shares": 10, "entry_price": 20.0, "current_price": 20.0},
    ]
    packet = build_decision_packet(positions, 1_000.0)
    stale_data = {
        pair.stable_ticker: _bars("2026-07-01", periods=320),
        pair.leveraged_ticker: _bars("2026-07-01", periods=320),
    }
    policy = TradingPolicy(
        version="t", name="t", execution_mode="paper", max_order_value=5_000.0
    )
    with pytest.raises(StaleMarketDataError, match="stale"):
        generate_leveraged_pair_rebalance_proposals(
            packet, policy, pair, market_data=stale_data
        )

    # Risk reduction is derived from policy + portfolio only: it does not
    # touch bars and cannot be blocked by their staleness.
    from assistant.proposals import generate_risk_reduction_proposals

    proposals = generate_risk_reduction_proposals(packet, policy)
    assert isinstance(proposals, list)


def test_missing_strategy_bars_are_a_visible_refusal():
    from assistant.policy import TradingPolicy
    from assistant.strategy_proposals import (
        CONFIGURED_LEVERAGED_PAIRS,
        generate_leveraged_pair_rebalance_proposals,
    )

    pair = CONFIGURED_LEVERAGED_PAIRS[0]
    positions = [
        {
            "ticker": pair.stable_ticker,
            "shares": 10,
            "entry_price": 100.0,
            "current_price": 100.0,
        },
        {
            "ticker": pair.leveraged_ticker,
            "shares": 10,
            "entry_price": 20.0,
            "current_price": 20.0,
        },
    ]
    packet = build_decision_packet(positions, 1_000.0)
    policy = TradingPolicy(
        version="t",
        name="t",
        execution_mode="paper",
        max_order_value=5_000.0,
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        generate_leveraged_pair_rebalance_proposals(
            packet,
            policy,
            pair,
            market_data={},
        )


def test_strategy_provider_failure_is_recorded_before_refusal(
    store, monkeypatch
):
    import assistant.data_integrity as di
    from assistant.policy import TradingPolicy
    from assistant.strategy_proposals import (
        CONFIGURED_LEVERAGED_PAIRS,
        generate_leveraged_pair_rebalance_proposals,
    )

    pair = CONFIGURED_LEVERAGED_PAIRS[0]
    packet = build_decision_packet(
        [
            {
                "ticker": pair.stable_ticker,
                "shares": 10,
                "entry_price": 100.0,
                "current_price": 100.0,
            },
            {
                "ticker": pair.leveraged_ticker,
                "shares": 10,
                "entry_price": 20.0,
                "current_price": 20.0,
            },
        ],
        1_000.0,
    )
    monkeypatch.setattr(
        di,
        "YFinanceDailyBars",
        lambda: _FakeSource(error=ConnectionError("down")),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        generate_leveraged_pair_rebalance_proposals(
            packet,
            TradingPolicy(
                version="t",
                name="t",
                execution_mode="paper",
                max_order_value=5_000.0,
            ),
            pair,
            store=store,
        )
    records = store.list_provider_fetches(provider_id="fake-provider")
    assert len(records) == 1
    assert records[0]["ok"] is False


# --- split detection: share-count reconciliation, not price heuristics -----


@pytest.mark.parametrize(
    "recorded,broker,expected_ratio,expected_direction",
    [
        (Decimal("2"), Decimal("20"), "10:1", "forward"),
        (Decimal("12"), Decimal("48"), "4:1", "forward"),
        (Decimal("30"), Decimal("10"), "3:1", "reverse"),
        (Decimal("7"), Decimal("14"), "2:1", "forward"),
    ],
)
def test_split_shaped_mismatches_are_classified(
    recorded, broker, expected_ratio, expected_direction
):
    suspicion = detect_split_like_share_mismatch(recorded, broker)
    assert suspicion is not None
    assert suspicion["ratio"] == expected_ratio
    assert suspicion["direction"] == expected_direction


@pytest.mark.parametrize(
    "recorded,broker",
    [
        (Decimal("10"), Decimal("10")),  # match
        (Decimal("10"), Decimal("13")),  # not a ratio
        (Decimal("10"), Decimal("17")),  # 1.7x: not near-integer
        (Decimal("0"), Decimal("10")),  # no basis for a ratio
        (Decimal("10"), Decimal("0")),
    ],
)
def test_non_split_mismatches_are_not_classified(recorded, broker):
    assert detect_split_like_share_mismatch(recorded, broker) is None


def test_reconciliation_annotates_split_shaped_position_mismatch(store):
    """End to end through the real ledger: a 10:1 share multiplication
    between the journal and the broker snapshot is reported as a mismatch
    (fail-closed — it still counts) AND named as split-shaped so the
    operator confirms a split instead of chasing a phantom fill."""
    from assistant.context_builder import build_portfolio_snapshot
    from assistant.portfolio_ledger import bootstrap_opening_snapshot, reconcile_snapshot

    before = build_portfolio_snapshot(
        [{"ticker": "NFLX", "shares": 2, "entry_price": 700.0, "current_price": 700.0}],
        1_000.0,
    )
    bootstrap_opening_snapshot(store, before, confirmation="bootstrap")

    after = build_portfolio_snapshot(
        [{"ticker": "NFLX", "shares": 20, "entry_price": 70.0, "current_price": 70.0}],
        1_000.0,
    )
    report = reconcile_snapshot(store, after)
    assert report["matched"] is False
    position_mismatches = [
        m for m in report["mismatches"] if m["kind"] == "position"
    ]
    assert len(position_mismatches) == 1
    suspicion = position_mismatches[0]["suspected_split"]
    assert suspicion["ratio"] == "10:1"
    assert suspicion["direction"] == "forward"
    assert Decimal(suspicion["recorded_shares"]) == Decimal("2")
    assert Decimal(suspicion["broker_shares"]) == Decimal("20")
