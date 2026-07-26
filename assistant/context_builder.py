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

from datetime import datetime, timezone

import pandas as pd

from config import BASKETS, LEVERAGED_ETF_TICKERS, MARKET_BENCHMARK_TICKERS, REGIME_VOLATILITY_LOOKBACK_DAYS
from data.market_data import fetch_historical
from signals.regime import calibrate_threshold_from_discovery, classify_regime, compute_trailing_market_volatility
from strategies.trend_vol_rotation import classify_trend
from assistant.schemas import (
    DecisionPacket,
    EvidenceStatus,
    MarketRegime,
    PortfolioPosition,
    PortfolioSnapshot,
    RiskExposure,
    SignalEvidence,
    UpcomingEvent,
)

# This project's own research findings, current as of 2026-07 — see
# memory: project_signal_findings.md, project_leverage_rotation_strategy.md.
# Kept as a static registry for now (Phase 1); a real implementation would
# read this from the trading journal / experiment database once built
# (see assistant/audit_log.py and the Phase 3 "research memory" plan).
KNOWN_FINDINGS: list[SignalEvidence] = [
    SignalEvidence(
        label="Original z-score dip/up scanner",
        claim="Beats a random-day baseline out-of-sample",
        status=EvidenceStatus.REJECTED,
        detail="0/32 basket x direction cells significant at 2yr or 7yr lookback, across the full 104-ticker universe.",
        source="memory: project_signal_findings",
        relevant_tickers=[],
    ),
    SignalEvidence(
        label="Cross-sectional momentum (12-1 month)",
        claim="Beats a random-day baseline out-of-sample",
        status=EvidenceStatus.REJECTED,
        detail="Looked real under row-level bootstrap (p=0.000 both periods) but evaporated under block bootstrap "
        "accounting for serial dependence (p=0.25-0.37) — the ~19-20 tickers it flags per day were far fewer "
        "independent observations than they appeared.",
        source="memory: project_signal_findings, project_rigor_toolkit",
        relevant_tickers=[],
    ),
    SignalEvidence(
        label="Relative scanner, 52-week breakout, PEAD, fundamentals, analyst-rating signals",
        claim="Beats a random-day baseline out-of-sample",
        status=EvidenceStatus.REJECTED,
        detail="0/2 significant cells each, after confirmation-only + by-date/by-block significance testing.",
        source="memory: project_signal_findings",
        relevant_tickers=[],
    ),
    SignalEvidence(
        label="QQQ/TQQQ trend+volatility regime rotation",
        claim="Beats 50/50 buy-and-hold on both CAGR and drawdown",
        status=EvidenceStatus.REJECTED,
        detail="Passed under a since-fixed same-close look-ahead bug; under corrected next-day-open execution, "
        "walk-forward wins dropped from 2/3 to 1/3 folds and the main confirmation no longer beats baseline on CAGR.",
        source="memory: project_leverage_rotation_strategy",
        relevant_tickers=["QQQ", "QQQM", "TQQQ"],
    ),
    SignalEvidence(
        label="SOXX/SOXL trend+volatility regime rotation — return",
        claim="Beats 50/50 buy-and-hold on CAGR",
        status=EvidenceStatus.REJECTED,
        detail="41.6% CAGR pre-tax (beat baseline's 36.3%), but only 33.9% after modeling a 37% short-term "
        "capital-gains tax in a taxable account — now LOSES to baseline. ~$9,577 paid in taxes on ~21 trades over 6.5yr.",
        source="memory: project_leverage_rotation_strategy",
        relevant_tickers=["SOXX", "SOXL"],
    ),
    SignalEvidence(
        label="SOXX/SOXL trend+volatility regime rotation — drawdown",
        claim="Reduces max drawdown vs. 50/50 buy-and-hold",
        status=EvidenceStatus.CONFIRMED,
        detail="Consistently -50% to -54% max drawdown vs. baseline's -74%, across the original confirmation, "
        "walk-forward (2/3 folds), full parameter-sensitivity sweep, AND after tax/cost modeling. The one durable "
        "result in this project so far — a smoother ride, not higher returns.",
        source="memory: project_leverage_rotation_strategy",
        relevant_tickers=["SOXX", "SOXL"],
    ),
]


def _classify_leveraged(ticker: str) -> bool:
    return ticker.upper() in LEVERAGED_ETF_TICKERS


def build_portfolio_snapshot(positions: list[dict], cash: float) -> PortfolioSnapshot:
    """
    `positions` is a list of dicts: {ticker, shares, entry_price, current_price}.
    See build_portfolio_snapshot_from_alpaca() for pulling this shape
    from a live account instead of supplying it manually.
    """
    built = []
    for p in positions:
        market_value = p["shares"] * p["current_price"]
        cost = p["shares"] * p["entry_price"]
        unrealized_pnl_pct = ((market_value - cost) / cost * 100) if cost else 0.0
        built.append(
            PortfolioPosition(
                ticker=p["ticker"],
                shares=p["shares"],
                entry_price=p["entry_price"],
                current_price=p["current_price"],
                market_value=round(market_value, 2),
                unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
                is_leveraged_etf=_classify_leveraged(p["ticker"]),
            )
        )
    total_equity = cash + sum(p.market_value for p in built)
    return PortfolioSnapshot(
        positions=built,
        cash=round(cash, 2),
        total_equity=round(total_equity, 2),
        as_of=datetime.now(timezone.utc).date().isoformat(),
    )


def build_portfolio_snapshot_from_alpaca() -> PortfolioSnapshot:
    """
    Pulls live positions and cash from the connected Alpaca account
    (paper or live, per config.PAPER_TRADING) and builds the same
    PortfolioSnapshot shape as the manual path. Raises
    execution.alpaca_broker.AlpacaNotConfigured if APCA_API_KEY_ID /
    APCA_API_SECRET_KEY aren't set — callers should check
    execution.alpaca_broker.is_configured() first (see
    build_decision_packet()'s use_live_alpaca handling) rather than
    relying on this exception for control flow.
    """
    from execution.alpaca_broker import get_account, get_open_positions

    account = get_account()
    positions = [
        {
            "ticker": p["ticker"],
            "shares": p["shares"],
            "entry_price": p["avg_entry_price"],
            "current_price": p["current_price"],
        }
        for p in get_open_positions()
    ]
    return build_portfolio_snapshot(positions, cash=account["cash"])


def build_risk_exposure(snapshot: PortfolioSnapshot, concentration_threshold_pct: float = 40.0) -> RiskExposure:
    """Deterministic exposure analysis: basket (overlapping) exposure,
    leveraged-ETF exposure, cash %, and simple concentration warnings.
    Baskets overlap by design (see config.BASKETS) — a ticker can and
    often does count toward several basket exposures at once."""
    total = snapshot.total_equity
    if total <= 0:
        return RiskExposure(
            basket_exposure_pct={}, leveraged_etf_exposure_pct=0.0, cash_pct=0.0,
            largest_single_position_pct=0.0, concentration_warnings=["Portfolio has zero or negative total equity."],
        )

    basket_exposure_pct = {}
    for basket_name, tickers in BASKETS.items():
        basket_value = sum(p.market_value for p in snapshot.positions if p.ticker in tickers)
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
            tickers_held = [p.ticker for p in snapshot.positions if p.ticker in BASKETS[basket_name]]
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


def build_market_regime(benchmark_ticker: str = "QQQ", lookback_days: int = 1764) -> MarketRegime:
    """
    Trend + volatility-regime read on a benchmark, using the same
    machinery as strategies/trend_vol_rotation.py and signals/regime.py.
    The high/low-vol threshold is calibrated from the ENTIRE fetched
    history (there's no discovery/confirmation split for a live "what's
    today's regime" read, unlike a backtest) — a simplification worth
    knowing about, not a bug.
    """
    data = fetch_historical([benchmark_ticker], lookback_days=lookback_days)
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
        threshold = calibrate_threshold_from_discovery(benchmark_df, as_of_date, lookback_days=REGIME_VOLATILITY_LOOKBACK_DAYS)
        vol_regime = classify_regime(benchmark_df, as_of_date, threshold, lookback_days=REGIME_VOLATILITY_LOOKBACK_DAYS)

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


def get_upcoming_events(tickers: list[str]) -> list[UpcomingEvent]:
    """No live earnings/macro-event calendar is wired up yet — every
    entry is honestly UNAVAILABLE rather than guessed or omitted
    silently. Wire up a real calendar feed to fill this in for real."""
    return [
        UpcomingEvent(ticker=t, event_type="earnings", days_away=None, status=EvidenceStatus.UNAVAILABLE)
        for t in tickers
    ]


def build_decision_packet(
    positions: list[dict] | None = None,
    cash: float | None = None,
    benchmark_ticker: str = "QQQ",
    use_live_alpaca: bool = False,
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
    regime = build_market_regime(benchmark_ticker)
    tickers = [p.ticker for p in snapshot.positions]
    signals = get_relevant_signal_evidence(tickers)
    events = get_upcoming_events(tickers)

    warnings = list(risk.concentration_warnings) + extra_warnings
    if regime.trend is None or regime.volatility_regime is None:
        warnings.append(f"Market regime for {benchmark_ticker} could not be fully computed (insufficient history).")

    return DecisionPacket(
        generated_at=datetime.now(timezone.utc).isoformat(),
        portfolio=snapshot,
        risk=risk,
        regime=regime,
        signals=signals,
        upcoming_events=events,
        warnings=warnings,
    )
