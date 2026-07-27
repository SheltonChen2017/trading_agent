"""
Structured schemas for the read-only trading assistant (Phase 1).

Core architectural rule (per project design discussion, 2026-07): the
assistant/LLM layer NEVER computes financial numbers itself — position
sizes, exposures, drawdowns, returns, order quantities. Every number in
these schemas is computed by deterministic Python elsewhere in this repo
(backtest/engine.py, risk/manager.py, signals/regime.py, this package's
own context_builder.py). The assistant only reads, prioritizes, and
explains this already-computed, already-labeled structure — never asked
to derive these numbers from prose or raw tables.
"""
from __future__ import annotations

import dataclasses
from enum import Enum


class EvidenceStatus(str, Enum):
    """How much to trust a claim about a signal/strategy's edge —
    attached per CLAIM, not per strategy. A single strategy can carry
    two different statuses at once: SOXX/SOXL's drawdown-reduction claim
    is CONFIRMED (survived every check run), while its "beats buy-and-
    hold on CAGR" claim is REJECTED (failed once realistic taxes were
    modeled) — see memory: project_leverage_rotation_strategy."""

    CONFIRMED = "confirmed"                          # passed out-of-sample + all bootstrap layers + realistic execution/tax
    PROMISING_UNCONFIRMED = "promising_unconfirmed"   # positive result, hasn't cleared every check yet
    EXPLORATORY = "exploratory"                       # pattern noticed, not yet tested rigorously
    REJECTED = "rejected"                             # failed confirmation, look-ahead correction, or tax/cost modeling
    UNAVAILABLE = "unavailable"                       # data missing/stale/not yet integrated


def _to_dict(obj):
    """Recursively convert dataclasses (including nested ones, lists,
    dicts, and Enums) into plain JSON-serializable structures."""
    if dataclasses.is_dataclass(obj):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


@dataclasses.dataclass
class PortfolioPosition:
    ticker: str
    shares: float
    entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl_pct: float
    is_leveraged_etf: bool


@dataclasses.dataclass
class PortfolioSnapshot:
    positions: list[PortfolioPosition]
    cash: float
    total_equity: float
    as_of: str  # ISO date string
    buying_power: float | None = None
    source: str = "manual"
    account_mode: str = "manual"
    open_orders: list[dict] = dataclasses.field(default_factory=list)
    open_orders_available: bool = True


@dataclasses.dataclass
class RiskExposure:
    basket_exposure_pct: dict[str, float]     # basket name -> % of total equity (overlapping, doesn't sum to 100)
    leveraged_etf_exposure_pct: float
    cash_pct: float
    largest_single_position_pct: float
    concentration_warnings: list[str]


@dataclasses.dataclass
class MarketRegime:
    benchmark_ticker: str
    trend: str | None               # "uptrend" / "downtrend" / None if not computable
    volatility_regime: str | None   # "low_vol" / "high_vol" / None if not computable
    trailing_volatility_pct: float | None
    as_of: str


@dataclasses.dataclass
class SignalEvidence:
    label: str            # short human name, e.g. "SOXX/SOXL regime rotation -- drawdown reduction"
    claim: str             # the SPECIFIC claim this status applies to
    status: EvidenceStatus
    detail: str             # 1-2 sentence summary of the actual finding/numbers
    source: str              # file/memory reference for where this came from
    relevant_tickers: list[str]


@dataclasses.dataclass
class UpcomingEvent:
    ticker: str
    event_type: str
    days_away: int | None
    status: EvidenceStatus  # usually UNAVAILABLE until a real calendar feed is wired up
    event_date: str | None = None
    source: str | None = None
    fetched_at: str | None = None


@dataclasses.dataclass
class DecisionPacket:
    generated_at: str
    portfolio: PortfolioSnapshot
    risk: RiskExposure
    regime: MarketRegime
    signals: list[SignalEvidence]
    upcoming_events: list[UpcomingEvent]
    warnings: list[str]
    schema_version: str = "2.0"
    policy_version: str = ""
    analytics: dict = dataclasses.field(default_factory=dict)
    data_freshness: dict[str, str] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict:
        return _to_dict(self)
