"""
Structured schemas for the read-only trading assistant (Phase 1).

Core architectural rule (per project design discussion, 2026-07): the
assistant/LLM layer NEVER computes financial numbers itself — position
sizes, exposures, drawdowns, returns, order quantities. Every number in
these schemas is computed by deterministic Python elsewhere in this repo
(backtest/engine.py, risk/execution_gate.py, signals/regime.py, this
package's own context_builder.py). The assistant only reads, prioritizes,
and explains this already-computed, already-labeled structure — never
asked to derive these numbers from prose or raw tables.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from enum import Enum

from assistant.money import to_decimal


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
    dicts, and Enums) into plain JSON-serializable structures.

    Deliberately does NOT call `dataclasses.asdict(obj)` -- `asdict()`
    recursively converts every NESTED dataclass into a plain dict all in
    one call, so by the time this function's own
    `isinstance(obj, SignalEvidence)` check below ran on a value pulled
    back out of that pre-built dict, a `SignalEvidence` nested inside
    e.g. a `DecisionPacket` had ALREADY been flattened to a plain dict --
    the check never fired for anything but a bare, top-level
    `SignalEvidence` (GPT review, 2026-07-30, independently reproduced:
    `_to_dict(finding)` on its own worked, but
    `packet.to_dict()["signals"][0]` was missing
    `production_authoritative`/`display_status` entirely, which silently
    broke SQLite/JSONL persistence and any consumer reading a serialized
    packet). Walking `dataclasses.fields(obj)` one at a time and
    recursing through THIS function for each field's value instead means
    a nested `SignalEvidence` is still a real `SignalEvidence` instance
    -- not yet a dict -- when this function inspects it."""
    if dataclasses.is_dataclass(obj):
        result = {f.name: _to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        if isinstance(obj, SignalEvidence):
            # Computed, never stored -- can't drift out of sync with
            # status/provenance the way a manually-set field could (GPT
            # review, 2026-07-29: production authority was computed by
            # research_registry.is_production_authoritative() but never
            # actually reached any serialized/displayed output). Added
            # here, not just as in-memory properties, so every JSON
            # consumer (audit log, UI, briefing) gets it automatically.
            result["production_authoritative"] = obj.production_authoritative
            result["display_status"] = obj.display_status
        return result
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

    @property
    def entry_price_decimal(self) -> Decimal:
        return to_decimal(self.entry_price, name=f"{self.ticker}.entry_price")

    @property
    def current_price_decimal(self) -> Decimal:
        return to_decimal(self.current_price, name=f"{self.ticker}.current_price")

    @property
    def market_value_decimal(self) -> Decimal:
        return to_decimal(self.market_value, name=f"{self.ticker}.market_value")


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
    account_id: str | None = None

    @property
    def cash_decimal(self) -> Decimal:
        return to_decimal(self.cash, name="portfolio.cash")

    @property
    def total_equity_decimal(self) -> Decimal:
        return to_decimal(self.total_equity, name="portfolio.total_equity")

    @property
    def buying_power_decimal(self) -> Decimal | None:
        if self.buying_power is None:
            return None
        return to_decimal(self.buying_power, name="portfolio.buying_power")


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
class FindingProvenance:
    """Reproducibility metadata for a research claim (GPT review finding
    #8, 2026-07-29): a CONFIRMED or PROMISING_UNCONFIRMED status on its
    own doesn't say what data actually produced it, or whether that data
    predates a since-fixed data-loader bug -- this is that record.
    Required fields (see REQUIRED_PROVENANCE_FIELDS in research_registry.py)
    are enforced at load time for confirmed/promising findings; the rest
    are best-effort and may be None when genuinely unknown."""

    actual_start_date: str | None = None
    actual_end_date: str | None = None
    actual_row_count: int | None = None
    requested_lookback_sessions: int | None = None
    actual_lookback_sessions: int | None = None
    entry_timing: str | None = None
    hold_days: int | None = None
    slippage_pct: float | None = None
    discovery_frac: float | None = None
    bootstrap_method: str | None = None
    block_length_days: int | None = None
    multiple_testing_denominator: int | None = None
    data_fetched_at: str | None = None
    parameter_hash: str | None = None
    code_commit_hash: str | None = None
    # Honest reproduction flag -- False means this finding has NOT been
    # re-verified since the fetch_historical lookback-days bug fix
    # (commit 9f0ebc1) and must not be treated as current production
    # authority regardless of its status label.
    reproduced_after_data_loader_fix: bool = False


# Statuses strong enough that a reader might treat them as
# production-actionable without checking anything else, so they must carry
# provenance.
#
# THE single definition. research_registry.py used to keep its own copy,
# hand-synced via a comment; a status added to one and not the other would
# require provenance in one layer and not the other, which is precisely the
# drift a duplicated safety rule produces. That module already imports from
# this one (EvidenceStatus), so sharing it is not circular -- the old comment
# claiming otherwise had the direction backwards (2026-07-30).
STATUSES_REQUIRING_PROVENANCE = frozenset(
    {EvidenceStatus.CONFIRMED, EvidenceStatus.PROMISING_UNCONFIRMED}
)


@dataclasses.dataclass
class SignalEvidence:
    label: str            # short human name, e.g. "SOXX/SOXL regime rotation -- drawdown reduction"
    claim: str             # the SPECIFIC claim this status applies to
    status: EvidenceStatus
    detail: str             # 1-2 sentence summary of the actual finding/numbers
    source: str              # file/memory reference for where this came from
    relevant_tickers: list[str]
    provenance: FindingProvenance | None = None

    @property
    def production_authoritative(self) -> bool:
        """Whether THIS finding's status can currently be trusted as
        production evidence, as opposed to a label carried over from a
        prior (possibly superseded) data-loader methodology. A confirmed
        or promising_unconfirmed finding that has never been re-verified
        since the fetch_historical lookback-days fix (commit 9f0ebc1) is
        NOT production-authoritative regardless of its status string --
        callers deciding whether to ACT ON or DISPLAY a finding must
        check this, not just `status` (GPT review, 2026-07-29: this
        exact logic already existed as
        assistant.research_registry.is_production_authoritative(), but
        was consulted only by that module's own tests -- every runtime
        consumer, including the CLI briefing and the Streamlit UI, kept
        showing a bare "[CONFIRMED]" with no qualification). Computed
        fresh from `status`/`provenance` every time, never stored, so it
        can never go stale independently of them. Statuses that make no
        strong positive claim (rejected/exploratory/unavailable) are
        always authoritative -- there is nothing here to distrust."""
        if self.status not in STATUSES_REQUIRING_PROVENANCE:
            return True
        return self.provenance is not None and self.provenance.reproduced_after_data_loader_fix

    @property
    def display_status(self) -> str:
        """Status string safe to show a user WITHOUT destroying the
        historical status label (GPT review, 2026-07-29: "prefer
        preserving the historical status while exposing an explicit
        current-authority field or prominent warning, rather than
        destroying historical provenance"). A confirmed/promising
        finding that is not `production_authoritative` gets an explicit,
        hard-to-miss qualifier appended so it can never be displayed as
        an unqualified "confirmed" result; anything else (including a
        production-authoritative confirmed finding) is unchanged."""
        if self.production_authoritative:
            return self.status.value
        return f"{self.status.value} -- UNREPRODUCED, NOT CURRENTLY PRODUCTION-AUTHORITATIVE"


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
