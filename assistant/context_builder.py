"""
Builds a DecisionPacket: one versioned, JSON-serializable snapshot of
"everything worth knowing right now" — portfolio state, risk exposure,
market regime, and this project's own research findings, each labeled
with an honest EvidenceStatus. This is the deterministic layer; nothing
here is computed by an LLM (see schemas.py's module docstring).

Phase 1 scope (read-only, no trading capability): portfolio positions
can come from a live Alpaca (paper or live) account via
build_portfolio_snapshot_from_alpaca(), or from a manually-supplied list
of dicts (see sample_portfolio.py) when Alpaca isn't configured yet.
Either way, nothing downstream of build_decision_packet() needs to know
or care which source was used.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd

from config import BASKETS, REGIME_VOLATILITY_LOOKBACK_DAYS
from data.market_data import fetch_historical
from assistant.market_analytics import (
    calibrate_volatility_threshold,
    classify_trend,
    classify_volatility_regime,
    compute_trailing_market_volatility,
)
from assistant.schemas import (
    DecisionPacket,
    EvidenceStatus,
    MarketRegime,
    PortfolioSnapshot,
    RiskExposure,
    SignalEvidence,
    UpcomingEvent,
)
from assistant.policy import TradingPolicy, load_policy
from assistant.portfolio_analytics import compute_portfolio_analytics
from assistant.portfolio_snapshot import (
    build_portfolio_snapshot,
    build_portfolio_snapshot_from_alpaca,
)
from assistant.research_registry import load_research_findings, registry_version

# Backward-compatible import used by explanations.py and existing tests.
# The source of truth is now assistant/research_findings.json.
KNOWN_FINDINGS: list[SignalEvidence] = load_research_findings()


def build_risk_exposure(snapshot: PortfolioSnapshot, concentration_threshold_pct: float = 40.0) -> RiskExposure:
    """Deterministic exposure analysis: basket (overlapping) exposure,
    leveraged-ETF exposure, cash %, and simple concentration warnings.
    Baskets overlap by design (see config.BASKETS) — a ticker can and
    often does count toward several basket exposures at once."""
    total = snapshot.total_equity
    # isfinite first, not just `<= 0`: NaN loses every ordered comparison, so a
    # corrupt total silently produced NaN percentages and ZERO concentration
    # warnings on a portfolio that was 100% in one name. build_portfolio_snapshot()
    # rejects non-finite inputs, so this is defence in depth rather than a live
    # path -- but risk/execution_gate.py and assistant/paper_evidence.py both
    # re-check anyway, and risk_copilot.py was hardened on 2026-07-30 while these
    # siblings were left inconsistent with it.
    if not math.isfinite(total) or total <= 0:
        return RiskExposure(
            basket_exposure_pct={}, leveraged_etf_exposure_pct=0.0, cash_pct=0.0,
            largest_single_position_pct=0.0,
            concentration_warnings=[
                f"Portfolio total equity is not a usable number ({total!r}); "
                "exposure percentages cannot be computed."
                if not math.isfinite(total)
                else "Portfolio has zero or negative total equity."
            ],
        )

    basket_exposure_pct = {}
    for basket_name, tickers in BASKETS.items():
        basket_value = sum(p.market_value for p in snapshot.positions if p.ticker.upper() in tickers)
        if basket_value > 0:
            basket_exposure_pct[basket_name] = round(basket_value / total * 100, 1)

    leveraged_value = sum(p.market_value for p in snapshot.positions if p.is_leveraged_etf)
    leveraged_etf_exposure_pct = round(leveraged_value / total * 100, 1)
    cash_pct = round(snapshot.cash / total * 100, 1)
    largest_single_position_pct = (
        round(max((p.market_value for p in snapshot.positions), default=0.0) / total * 100, 1)
    )

    warnings = []
    for basket_name, pct in basket_exposure_pct.items():
        if pct > concentration_threshold_pct:
            tickers_held = [p.ticker for p in snapshot.positions if p.ticker.upper() in BASKETS[basket_name]]
            warnings.append(
                f"{basket_name} exposure is {pct}% of total equity (via {', '.join(tickers_held)}) — "
                f"above the {concentration_threshold_pct}% concentration threshold."
            )
    if leveraged_etf_exposure_pct > 20.0:
        warnings.append(f"Leveraged ETF exposure is {leveraged_etf_exposure_pct}% of total equity.")

    return RiskExposure(
        basket_exposure_pct=basket_exposure_pct,
        leveraged_etf_exposure_pct=leveraged_etf_exposure_pct,
        cash_pct=cash_pct,
        largest_single_position_pct=largest_single_position_pct,
        concentration_warnings=warnings,
    )


def build_market_regime(
    benchmark_ticker: str = "QQQ",
    lookback_days: int = 1764,
    store=None,
) -> MarketRegime:
    """
    Trend + volatility-regime read on a benchmark, using the same
    machinery as strategies/trend_vol_rotation.py and signals/regime.py.
    The high/low-vol threshold is calibrated from the ENTIRE fetched
    history (there's no discovery/confirmation split for a live "what's
    today's regime" read, unlike a backtest) — a simplification worth
    knowing about, not a bug.

    GR-4: when a ``store`` is supplied, the fetch is recorded in the
    append-only provider-health table (success or failure) and a failure
    streak raises a deduplicated operational alert. The DATA is identical
    either way — recording never alters, fills, or synthesizes a value —
    and the storeless path keeps working for research callers.
    """
    if store is not None:
        from assistant.data_integrity import fetch_daily_bars_recorded

        # The recorded path swallows the provider exception into a failed
        # fetch record (the briefing must survive an outage), so no
        # try/except is needed here — the outage becomes evidence.
        data = fetch_daily_bars_recorded(
            store, [benchmark_ticker], lookback_days
        )
    else:
        try:
            data = fetch_historical(
                [benchmark_ticker], lookback_days=lookback_days
            )
        except Exception:
            # A read-only briefing should remain available during a market-data
            # outage. Keep this degradation at the briefing/regime boundary:
            # fetch_historical() is also the data source for research scripts,
            # where swallowing a provider/API failure as an empty dataset would
            # hide the cause and could make a broken run look like missing tickers.
            data = {}
    if benchmark_ticker not in data or data[benchmark_ticker].empty:
        return MarketRegime(
            benchmark_ticker=benchmark_ticker, trend=None, volatility_regime=None,
            trailing_volatility_pct=None, as_of=datetime.now(timezone.utc).date().isoformat(),
        )

    close = data[benchmark_ticker]["close"]
    as_of_date = close.index[-1]
    benchmark_df = pd.DataFrame({"close": close})

    trend = classify_trend(close, as_of_date, lookback_days=200)
    trailing_vol = compute_trailing_market_volatility(benchmark_df, as_of_date, lookback_days=REGIME_VOLATILITY_LOOKBACK_DAYS)
    vol_regime = None
    if trailing_vol is not None:
        threshold = calibrate_volatility_threshold(benchmark_df, as_of_date, lookback_days=REGIME_VOLATILITY_LOOKBACK_DAYS)
        vol_regime = classify_volatility_regime(benchmark_df, as_of_date, threshold, lookback_days=REGIME_VOLATILITY_LOOKBACK_DAYS)

    return MarketRegime(
        benchmark_ticker=benchmark_ticker,
        trend=trend,
        volatility_regime=vol_regime,
        trailing_volatility_pct=round(trailing_vol, 3) if trailing_vol is not None else None,
        as_of=as_of_date.date().isoformat(),
    )


def get_relevant_signal_evidence(portfolio_tickers: list[str]) -> list[SignalEvidence]:
    """Project-wide findings always show (they're relevant background
    regardless of current holdings); ticker-specific findings are
    included only when a held ticker matches."""
    portfolio_set = set(t.upper() for t in portfolio_tickers)
    return [
        e for e in KNOWN_FINDINGS
        if not e.relevant_tickers or portfolio_set.intersection(t.upper() for t in e.relevant_tickers)
    ]


def get_upcoming_events(tickers: list[str], fetch_live: bool = False) -> list[UpcomingEvent]:
    """Return upcoming earnings or explicit UNAVAILABLE records."""
    if fetch_live and tickers:
        from data.corporate_actions import fetch_upcoming_ex_dividends
        from data.event_data import (
            fetch_upcoming_earnings,
            upcoming_quad_witching_dates,
        )

        # CXL-003: these feeds are optional presentation enrichment. A new
        # provider exception class, malformed response, or outage must become
        # explicit UNAVAILABLE evidence, never abort packet construction and
        # suppress deterministic risk-reduction proposals.
        try:
            raw = fetch_upcoming_earnings(tickers)
        except Exception:
            raw = {}
        try:
            dividends = fetch_upcoming_ex_dividends(tickers)
        except Exception:
            dividends = {}

        def provider_event(ticker: str, event_type: str, records: dict) -> UpcomingEvent:
            record = records.get(ticker) or records.get(ticker.upper())
            if not isinstance(record, dict):
                return UpcomingEvent(
                    ticker=ticker,
                    event_type=event_type,
                    days_away=None,
                    status=EvidenceStatus.UNAVAILABLE,
                    source="provider_unavailable",
                )
            try:
                available = bool(record["available"])
                return UpcomingEvent(
                    ticker=ticker,
                    event_type=event_type,
                    days_away=record.get("days_away"),
                    status=(
                        EvidenceStatus.EXPLORATORY
                        if available
                        else EvidenceStatus.UNAVAILABLE
                    ),
                    event_date=record.get("event_date"),
                    source=record.get("source"),
                    fetched_at=record.get("fetched_at"),
                )
            except (KeyError, TypeError, ValueError):
                return UpcomingEvent(
                    ticker=ticker,
                    event_type=event_type,
                    days_away=None,
                    status=EvidenceStatus.UNAVAILABLE,
                    source="provider_malformed",
                )

        events = [provider_event(t, "earnings", raw) for t in tickers]
        events.extend(provider_event(t, "ex_dividend", dividends) for t in tickers)
        try:
            calendar_events = upcoming_quad_witching_dates()
        except Exception:
            calendar_events = []
        events.extend(
            UpcomingEvent(
                ticker=event["ticker"],
                event_type=event["event_type"],
                days_away=event["days_away"],
                status=EvidenceStatus.EXPLORATORY,
                event_date=event["event_date"],
                source=event["source"],
                fetched_at=event["fetched_at"],
            )
            for event in calendar_events
        )
        return events
    return [
        UpcomingEvent(ticker=t, event_type="earnings", days_away=None, status=EvidenceStatus.UNAVAILABLE)
        for t in tickers
    ]


def build_decision_packet(
    positions: list[dict] | None = None,
    cash: float | None = None,
    benchmark_ticker: str = "QQQ",
    use_live_alpaca: bool = False,
    include_live_events: bool = False,
    policy: TradingPolicy | None = None,
    store=None,
) -> DecisionPacket:
    """
    Assembles the full read-only decision packet. This is the one
    function a CLI/briefing script should call — everything else in this
    module is a building block.

    Set `use_live_alpaca=True` to pull real positions/cash from a
    connected Alpaca account instead of the manually-supplied
    `positions`/`cash`. Falls back to the manual values (with a warning
    appended to the packet) if Alpaca isn't configured yet, rather than
    raising — a briefing script should still produce useful output even
    before credentials are set.
    """
    extra_warnings = []
    if use_live_alpaca:
        from execution.alpaca_broker import is_configured

        if is_configured():
            snapshot = build_portfolio_snapshot_from_alpaca()
        else:
            extra_warnings.append(
                "Alpaca requested but not configured (APCA_API_KEY_ID / APCA_API_SECRET_KEY not set) — "
                "falling back to the manually-supplied portfolio."
            )
            snapshot = build_portfolio_snapshot(positions or [], cash or 0.0)
    else:
        snapshot = build_portfolio_snapshot(positions or [], cash or 0.0)

    risk = build_risk_exposure(snapshot)
    regime = build_market_regime(benchmark_ticker, store=store)
    tickers = [p.ticker for p in snapshot.positions]
    signals = get_relevant_signal_evidence(tickers)
    events = get_upcoming_events(tickers, fetch_live=include_live_events)
    active_policy = policy or load_policy()
    analytics = compute_portfolio_analytics(snapshot)

    warnings = list(risk.concentration_warnings) + extra_warnings
    if regime.trend is None or regime.volatility_regime is None:
        warnings.append(
            f"Market regime for {benchmark_ticker} could not be fully "
            "computed (market data unavailable or insufficient history)."
        )

    # GR-4 staleness SLA for daily bars: the regime's as_of IS the newest
    # bar date when trend was computed. Evaluate it against the real NYSE
    # calendar and degrade VISIBLY -- the "DATA DEGRADED:" prefix is the
    # contract the UI banner and tests key on, and warnings are already
    # critical facts for the committee projection, so degraded data
    # automatically reaches every downstream consumer. Never fills or
    # substitutes a value; the stale numbers stay visibly stale.
    bar_freshness = None
    freshness_derivation_failed = False
    # A non-empty fetch always sets regime.as_of to its actual newest bar,
    # even when history is too short to calculate trend. An empty fetch uses
    # today's fallback date and already emits the explicit unavailable
    # warning above; do not misrepresent that fallback as an observed bar.
    observed_bar_date = (
        regime.trend is not None
        or regime.volatility_regime is not None
        or regime.trailing_volatility_pct is not None
        or regime.as_of != datetime.now(timezone.utc).date().isoformat()
    )
    if observed_bar_date:
        from data.price_source import evaluate_bar_freshness

        try:
            bar_freshness = evaluate_bar_freshness(regime.as_of)
        except ValueError:
            freshness_derivation_failed = True
    if freshness_derivation_failed:
        warnings.append(
            f"DATA DEGRADED: {benchmark_ticker} daily-bar freshness could "
            "not be derived from the recorded provider outcome. "
            "Trend/regime and bar-derived surfaces are unverified."
        )
    elif bar_freshness is not None and not bar_freshness.fresh:
        warnings.append(
            f"DATA DEGRADED: {benchmark_ticker} daily bars failed freshness "
            f"({bar_freshness.detail}). Trend/regime and bar-derived "
            "surfaces reflect stale or unavailable data."
        )

    return DecisionPacket(
        generated_at=datetime.now(timezone.utc).isoformat(),
        portfolio=snapshot,
        risk=risk,
        regime=regime,
        signals=signals,
        upcoming_events=events,
        warnings=warnings,
        policy_version=active_policy.version,
        analytics=analytics,
        data_freshness={
            "portfolio_as_of": snapshot.as_of,
            "market_regime_as_of": regime.as_of,
            "research_registry_version": registry_version(),
            "market_bars_expected_session": (
                bar_freshness.expected_session if bar_freshness else None
            ),
            "market_bars_fresh": (
                bar_freshness.fresh if bar_freshness else None
            ),
        },
    )
