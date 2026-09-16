"""Accepted-risk unlevered sector/industry ETF baseline.

This module deliberately implements a small economic baseline, not the formal
ARV2-5/6 reverse-index universe.  It replays the exact R055 stock-score path,
aggregates those scores through QuantConnect point-in-time ETF constituent
snapshots with a one-session availability lag, and evaluates one fixed list of
liquid, unlevered US sector/industry ETFs.  No order API is present: portfolio
weights are an arithmetic research simulation only.
"""

import dataclasses
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from types import MappingProxyType

try:
    import accepted_risk_preliminary_rating_evaluator as _stock
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as _stock,
    )


class AcceptedRiskEtfBaselineError(ValueError):
    """The fixed ETF baseline or one of its aggregate inputs is inexact."""


class EtfHoldingsCompletenessError(AcceptedRiskEtfBaselineError):
    """A constituent snapshot failed the frozen completeness band."""


class EtfMappingCoverageError(AcceptedRiskEtfBaselineError):
    """A constituent snapshot failed the exact 99% score-mapping gate."""


PROFILE_SCHEMA = "arv2-accepted-risk-etf-sector-baseline-profile-v1"
PROFILE_ID = "arv2-etf-sector-baseline-2021-2025"
CONTRACT_ID = "arv2-accepted-risk-etf-sector-baseline-v1"
# R060/R061 keep their original identity and economic admission behavior.
# The corrected profile is local/review-only until a new run is preregistered.
CORRECTED_PROFILE_ID = "arv2-etf-sector-baseline-2021-2025-admission-v2"
CORRECTED_PROFILE_SCHEMA = "arv2-accepted-risk-etf-sector-baseline-profile-v2"
CORRECTED_CONTRACT_ID = "arv2-accepted-risk-etf-sector-baseline-v2"
SUMMARY_SCHEMA = "arv2-accepted-risk-etf-sector-baseline-summary-v1"
IC_CELL_SCHEMA = "arv2-accepted-risk-etf-sector-baseline-ic-cell-v1"
PORTFOLIO_CELL_SCHEMA = (
    "arv2-accepted-risk-etf-sector-baseline-portfolio-cell-v1"
)

WARMUP_START_SESSION = "2020-12-01"
DECISION_START_SESSION = "2021-01-04"
DECISION_END_SESSION = "2025-12-29"
MEASUREMENT_END_SESSION = "2025-12-31"
OUTCOME_MATURITY_END_SESSION = "2026-03-31"
PRIMARY_SOURCE_VIEW_ID = _stock.SOURCE_VIEW_IDS[1]
PRIMARY_SCORE_ARM = "firm_specific"
HORIZONS = (5, 20, 60)
COST_BPS_SCENARIOS = (0, 5, 10, 20)
PRIMARY_COST_BPS = 10
HOLDINGS_LAG_SESSIONS = 1
MINIMUM_MAPPED_WEIGHT = Decimal("0.99")
MINIMUM_COMPLETE_WEIGHT = Decimal("0.95")
MAXIMUM_COMPLETE_WEIGHT = Decimal("1.05")
MINIMUM_DAILY_DOLLAR_VOLUME = Decimal("5000000")
LIQUIDITY_WINDOW_SESSIONS = 20
ENTRY_PERCENTILE = Decimal("90")
EXIT_PERCENTILE = Decimal("70")
MAXIMUM_HOLDINGS = 5
ETF_WEIGHT_CAP = Decimal("0.20")
SECTOR_WEIGHT_CAP = Decimal("0.40")
OVERLAP_CLUSTER_WEIGHT_CAP = Decimal("0.30")
OVERLAP_CLUSTER_THRESHOLD = Decimal("0.60")
MINIMUM_ETF_IC_ROWS = 5
MINIMUM_INVESTED_RETURN_SESSIONS = 50
ANNUALIZATION_SESSIONS = Decimal("252")
NUMERICAL_ZERO = Decimal("1e-18")

_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,511}\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")

# Fixed before the first ETF outcome read.  Every member is present in the
# documented QuantConnect US ETF Constituents supported-ticker inventory and
# is a long, unlevered US equity sector/industry fund.  The fixed sleeve is a
# practical topology baseline; it is not represented as exhaustive discovery.
_CANDIDATE_SECTOR_ROWS = (
    ("AIQ", "technology"),
    ("BOTZ", "industrials"),
    ("FINX", "technology"),
    ("IBB", "health_care"),
    ("IGV", "technology"),
    ("IHE", "health_care"),
    ("IHF", "health_care"),
    ("IHI", "health_care"),
    ("ITA", "industrials"),
    ("IYC", "consumer_discretionary"),
    ("IYE", "energy"),
    ("IYF", "financials"),
    ("IYG", "financials"),
    ("IYH", "health_care"),
    ("IYJ", "industrials"),
    ("IYK", "consumer_staples"),
    ("IYM", "materials"),
    ("IYR", "real_estate"),
    ("IYT", "industrials"),
    ("IYW", "technology"),
    ("IYZ", "communication_services"),
    ("KBE", "financials"),
    ("KRE", "financials"),
    ("LIT", "materials"),
    ("OIH", "energy"),
    ("PBW", "energy"),
    ("PHO", "industrials"),
    ("PJP", "health_care"),
    ("PPA", "industrials"),
    ("PSI", "technology"),
    ("PXJ", "energy"),
    ("SMH", "technology"),
    ("SOXX", "technology"),
    ("TAN", "energy"),
    ("XAR", "industrials"),
    ("XBI", "health_care"),
    ("XHB", "consumer_discretionary"),
    ("XLB", "materials"),
    ("XLC", "communication_services"),
    ("XLE", "energy"),
    ("XLF", "financials"),
    ("XLI", "industrials"),
    ("XLK", "technology"),
    ("XLP", "consumer_staples"),
    ("XLRE", "real_estate"),
    ("XLU", "utilities"),
    ("XLV", "health_care"),
    ("XLY", "consumer_discretionary"),
    ("XME", "materials"),
    ("XOP", "energy"),
    ("XPH", "health_care"),
    ("XRT", "consumer_discretionary"),
    ("XSD", "technology"),
    ("XSW", "technology"),
)
CANDIDATE_ETFS = tuple(row[0] for row in _CANDIDATE_SECTOR_ROWS)
ETF_SECTOR_BY_TICKER = MappingProxyType(dict(_CANDIDATE_SECTOR_ROWS))


def _canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise AcceptedRiskEtfBaselineError(
            "ETF baseline value is not canonical ASCII JSON"
        ) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal(value, name, *, positive=False, nonnegative=False):
    if type(value) is not Decimal:
        try:
            value = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise AcceptedRiskEtfBaselineError(name + " is not decimal") from exc
    if not value.is_finite():
        raise AcceptedRiskEtfBaselineError(name + " is not finite")
    if positive and value <= 0:
        raise AcceptedRiskEtfBaselineError(name + " is not positive")
    if nonnegative and value < 0:
        raise AcceptedRiskEtfBaselineError(name + " is negative")
    return value


def _decimal_text(value):
    value = _decimal(value, "result decimal")
    if value == 0:
        return "0"
    return format(value, "f")


def _safe(value, name):
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        raise AcceptedRiskEtfBaselineError(name + " is not canonical")
    return value


def _session(value, name="session"):
    if type(value) is not str or _DATE.fullmatch(value) is None:
        raise AcceptedRiskEtfBaselineError(name + " is not canonical")
    return value


def _mean(values):
    if type(values) is not tuple or not values:
        raise AcceptedRiskEtfBaselineError("mean requires a non-empty tuple")
    with localcontext(_stock._context()):
        return +(_stock._stable_sum(values) / Decimal(len(values)))


def _median(values):
    return _stock._median(tuple(values))


def _profile_record():
    semantic = {
        "schema": PROFILE_SCHEMA,
        "profile_id": PROFILE_ID,
        "warmup_start_session": WARMUP_START_SESSION,
        "decision_start_session": DECISION_START_SESSION,
        "decision_end_session": DECISION_END_SESSION,
        "measurement_end_session": MEASUREMENT_END_SESSION,
        "outcome_maturity_end_session": OUTCOME_MATURITY_END_SESSION,
        "candidate_etfs": list(CANDIDATE_ETFS),
        "candidate_sector_rows_sha256": _sha(
            [list(row) for row in _CANDIDATE_SECTOR_ROWS]
        ),
        "source_view_id": PRIMARY_SOURCE_VIEW_ID,
        "score_arm": PRIMARY_SCORE_ARM,
        "horizons": list(HORIZONS),
        "holdings_lag_sessions": HOLDINGS_LAG_SESSIONS,
        "holdings_staleness_rule": "exact_previous_authenticated_session",
        "minimum_mapped_weight": _decimal_text(MINIMUM_MAPPED_WEIGHT),
        "liquidity_window_sessions": LIQUIDITY_WINDOW_SESSIONS,
        "minimum_daily_dollar_volume": _decimal_text(
            MINIMUM_DAILY_DOLLAR_VOLUME
        ),
        "entry_percentile": _decimal_text(ENTRY_PERCENTILE),
        "exit_percentile": _decimal_text(EXIT_PERCENTILE),
        "maximum_holdings": MAXIMUM_HOLDINGS,
        "etf_weight_cap": _decimal_text(ETF_WEIGHT_CAP),
        "sector_weight_cap": _decimal_text(SECTOR_WEIGHT_CAP),
        "overlap_cluster_weight_cap": _decimal_text(
            OVERLAP_CLUSTER_WEIGHT_CAP
        ),
        "overlap_cluster_threshold": _decimal_text(
            OVERLAP_CLUSTER_THRESHOLD
        ),
        "overlap_cluster_method": "transitive_connected_components",
        "sector_cap_basis": "mapped_constituent_look_through",
        "turnover_basis": "drift_adjusted_open_to_open_weights",
        "minimum_invested_return_sessions": MINIMUM_INVESTED_RETURN_SESSIONS,
        "weighting": "equal_20_percent_slots_with_cash_residual",
        "cost_bps_scenarios": list(COST_BPS_SCENARIOS),
        "primary_cost_bps": PRIMARY_COST_BPS,
        "leverage": False,
        "orders": False,
        "trading": False,
    }
    return {**semantic, "profile_sha256": _sha(semantic)}


_PROFILE = MappingProxyType(_profile_record())


def _corrected_profile_record():
    semantic = _profile_record()
    semantic.pop("profile_sha256")
    semantic.update(
        schema=CORRECTED_PROFILE_SCHEMA,
        profile_id=CORRECTED_PROFILE_ID,
        portfolio_admission="percentile_hysteresis_independent_of_ic_count",
        minimum_etf_ic_rows=MINIMUM_ETF_IC_ROWS,
        singleton_percentile="50",
        tie_policy="average_rank",
        cash_return="0",
    )
    return {**semantic, "profile_sha256": _sha(semantic)}


_CORRECTED_PROFILE = MappingProxyType(_corrected_profile_record())


def require_etf_baseline_profile(profile_id):
    if type(profile_id) is not str or profile_id not in (
        PROFILE_ID, CORRECTED_PROFILE_ID,
    ):
        raise AcceptedRiskEtfBaselineError(
            "ETF baseline profile must be the exact frozen profile"
        )
    profile = _PROFILE if profile_id == PROFILE_ID else _CORRECTED_PROFILE
    # Return independent nested lists as well as an independent root mapping.
    return json.loads(_canonical(dict(profile)).decode("ascii"))


def expected_custom_summary_statistic_names(profile_id=PROFILE_ID):
    require_etf_baseline_profile(profile_id)
    return tuple(
        sorted(
            (
                "ARV2_ETF_2021_2025_META",
                *("ARV2_ETF_IC_H" + str(horizon) for horizon in HORIZONS),
                *(
                    "ARV2_ETF_PORTFOLIO_COST_" + str(cost)
                    for cost in COST_BPS_SCENARIOS
                ),
            )
        )
    )


@dataclasses.dataclass(frozen=True)
class ConstituentWeight:
    qc_security_id: str
    weight: Decimal

    def __post_init__(self):
        _safe(self.qc_security_id, "constituent QC security id")
        _decimal(self.weight, "constituent weight", positive=True)


@dataclasses.dataclass(frozen=True)
class EtfHoldingsSnapshot:
    ticker: str
    observed_session: str
    constituents: tuple[ConstituentWeight, ...]

    def __post_init__(self):
        if self.ticker not in CANDIDATE_ETFS or type(self.ticker) is not str:
            raise AcceptedRiskEtfBaselineError("snapshot ETF is not frozen")
        _session(self.observed_session, "snapshot session")
        if (
            type(self.constituents) is not tuple
            or not self.constituents
            or any(type(row) is not ConstituentWeight for row in self.constituents)
            or tuple(row.qc_security_id for row in self.constituents)
            != tuple(sorted({row.qc_security_id for row in self.constituents}))
        ):
            raise AcceptedRiskEtfBaselineError(
                "snapshot constituents must be sorted unique exact rows"
            )


@dataclasses.dataclass(frozen=True)
class EtfDailyBar:
    ticker: str
    session: str
    adjusted_open: Decimal
    adjusted_close: Decimal
    volume: Decimal

    def __post_init__(self):
        if self.ticker not in (*CANDIDATE_ETFS, "SPY"):
            raise AcceptedRiskEtfBaselineError("bar ticker is not permitted")
        _session(self.session, "bar session")
        _decimal(self.adjusted_open, "adjusted open", positive=True)
        _decimal(self.adjusted_close, "adjusted close", positive=True)
        _decimal(self.volume, "volume", nonnegative=True)


@dataclasses.dataclass
class _PortfolioAccumulator:
    cost_bps: int
    wealth: Decimal = Decimal("1")
    peak: Decimal = Decimal("1")
    maximum_drawdown: Decimal = Decimal("0")
    returns: list = dataclasses.field(default_factory=list)


class _StockScoreReplay:
    """A narrow adapter over the exact R055 score cross-section path."""

    def __init__(self, value):
        if type(value) is not _stock.PreliminaryRatingInput:
            raise AcceptedRiskEtfBaselineError(
                "ETF stock replay requires the exact preliminary input"
            )
        self._runtime = _stock.PreliminaryRatingEvaluationRuntime(value)
        self._runtime._destroy_history_cache()
        self._sessions = value.session_axis
        try:
            self._next_position = self._sessions.index(DECISION_START_SESSION)
        except ValueError as exc:
            raise AcceptedRiskEtfBaselineError(
                "ETF decision start escaped the authenticated session axis"
            ) from exc
        for row in value.contributions:
            if row.eligible_session_index < self._next_position:
                self._runtime._apply_contribution(row)

    def score(self, session):
        _session(session)
        if (
            self._next_position >= len(self._sessions)
            or self._sessions[self._next_position] != session
        ):
            raise AcceptedRiskEtfBaselineError(
                "ETF stock-score sessions must replay contiguously"
            )
        result = self._runtime._score_cross_section(self._next_position)
        self._next_position += 1
        return result


def _normalized_snapshot_weights(snapshot):
    if type(snapshot) is not EtfHoldingsSnapshot:
        raise AcceptedRiskEtfBaselineError("holdings snapshot type changed")
    exact_total = sum(
        (Fraction(row.weight) for row in snapshot.constituents),
        Fraction(0),
    )
    if (
        exact_total < Fraction(MINIMUM_COMPLETE_WEIGHT)
        or exact_total > Fraction(MAXIMUM_COMPLETE_WEIGHT)
    ):
        raise EtfHoldingsCompletenessError(
            "holdings snapshot failed the fixed completeness band"
        )
    total = _stock._stable_sum(row.weight for row in snapshot.constituents)
    with localcontext(_stock._context()):
        return {
            row.qc_security_id: +(row.weight / total)
            for row in snapshot.constituents
        }


def _score_etf(
    snapshot,
    stock_scores,
    qc_sid_to_security_id,
    sector_by_security,
):
    weights = _normalized_snapshot_weights(snapshot)
    if type(sector_by_security) is not dict:
        raise AcceptedRiskEtfBaselineError(
            "stock-sector membership must be an exact dictionary"
        )
    exact_total = sum(
        (Fraction(row.weight) for row in snapshot.constituents),
        Fraction(0),
    )
    exact_mapped = sum(
        (
            Fraction(row.weight)
            for row in snapshot.constituents
            if qc_sid_to_security_id.get(row.qc_security_id) in stock_scores
        ),
        Fraction(0),
    )
    if exact_mapped * 100 < exact_total * 99:
        raise EtfMappingCoverageError(
            "ETF mapped score weight is below ninety-nine percent"
        )
    mapped_weight = Decimal(0)
    weighted_score = Decimal(0)
    contributions = []
    sector_exposures = {}
    with localcontext(_stock._context()):
        for qc_sid, weight in sorted(weights.items()):
            security_id = qc_sid_to_security_id.get(qc_sid)
            if security_id is None or security_id not in stock_scores:
                continue
            score = stock_scores[security_id]
            if type(score) is not Decimal or not score.is_finite():
                raise AcceptedRiskEtfBaselineError(
                    "mapped stock score is not an exact finite Decimal"
                )
            mapped_weight = +(mapped_weight + weight)
            weighted_score = +(weighted_score + weight * score)
            contributions.append(abs(+(weight * score)))
            sector = sector_by_security.get(security_id)
            if type(sector) is not str:
                raise AcceptedRiskEtfBaselineError(
                    "mapped stock lacks one authenticated sector"
                )
            sector_exposures[sector] = +(
                sector_exposures.get(sector, Decimal(0)) + weight
            )
        normalized = +(weighted_score / mapped_weight)
        total_contribution = _stock._stable_sum(contributions)
        if total_contribution <= NUMERICAL_ZERO:
            return (
                Decimal(0),
                mapped_weight,
                Decimal(0),
                weights,
                sector_exposures,
            )
        squares = _stock._stable_sum(value * value for value in contributions)
        if squares <= NUMERICAL_ZERO:
            return (
                Decimal(0),
                mapped_weight,
                Decimal(0),
                weights,
                sector_exposures,
            )
        n_eff = +(total_contribution * total_contribution / squares)
        breadth = min(Decimal(1), +(n_eff / Decimal(5)).sqrt())
        reliability = +(mapped_weight.sqrt() * breadth)
        return (
            +(normalized * reliability),
            mapped_weight,
            n_eff,
            weights,
            sector_exposures,
        )


def _percentiles(scores):
    if type(scores) is not dict:
        raise AcceptedRiskEtfBaselineError("ETF scores must be an exact dictionary")
    if not scores:
        return {}
    if len(scores) == 1:
        # A singleton has no relative rank: do not manufacture a top-percentile
        # signal. Equal-score cross-sections likewise receive neutral midranks.
        return {ticker: Decimal(50) for ticker in scores}
    ordered = tuple(sorted(scores))
    values = tuple(scores[ticker] for ticker in ordered)
    ranks = _stock._average_ranks(values)
    denominator = Decimal(len(values) - 1)
    result = {}
    with localcontext(_stock._context()):
        for ticker, rank in zip(ordered, ranks, strict=True):
            rank_decimal = Decimal(rank.numerator) / Decimal(rank.denominator)
            result[ticker] = +((rank_decimal - Decimal(1)) * Decimal(100) / denominator)
    return result


def _overlap(left, right):
    with localcontext(_stock._context()):
        return +_stock._stable_sum(
            min(weight, right.get(security_id, Decimal(0)))
            for security_id, weight in left.items()
        )


def _overlap_cluster_ids(tickers, snapshot_weights):
    ordered = tuple(sorted(tickers))
    parent = {ticker: ticker for ticker in ordered}

    def root(ticker):
        while parent[ticker] != ticker:
            parent[ticker] = parent[parent[ticker]]
            ticker = parent[ticker]
        return ticker

    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1:]:
            if (
                _overlap(snapshot_weights[left], snapshot_weights[right])
                < OVERLAP_CLUSTER_THRESHOLD
            ):
                continue
            left_root = root(left)
            right_root = root(right)
            if left_root != right_root:
                parent[max(left_root, right_root)] = min(left_root, right_root)
    return {ticker: root(ticker) for ticker in ordered}


def _target_weights(
    scores,
    snapshot_weights,
    sector_exposures,
    incumbents,
):
    percentiles = _percentiles(scores)
    eligible = [
        ticker
        for ticker in scores
        if (
            percentiles[ticker] >= EXIT_PERCENTILE
            if ticker in incumbents
            else percentiles[ticker] >= ENTRY_PERCENTILE
        )
    ]
    eligible.sort(
        key=lambda ticker: (
            -scores[ticker],
            0 if ticker in incumbents else 1,
            ticker,
        )
    )
    cluster_ids = _overlap_cluster_ids(eligible, snapshot_weights)
    selected = []
    sector_weights = {}
    cluster_weights = {}
    for ticker in eligible:
        if len(selected) >= MAXIMUM_HOLDINGS:
            break
        exposures = sector_exposures[ticker]
        if any(
            sector_weights.get(sector, Decimal(0))
            + ETF_WEIGHT_CAP * exposure
            > SECTOR_WEIGHT_CAP
            for sector, exposure in exposures.items()
        ):
            continue
        cluster = cluster_ids[ticker]
        if (
            cluster_weights.get(cluster, Decimal(0)) + ETF_WEIGHT_CAP
            > OVERLAP_CLUSTER_WEIGHT_CAP
        ):
            continue
        selected.append(ticker)
        cluster_weights[cluster] = (
            cluster_weights.get(cluster, Decimal(0)) + ETF_WEIGHT_CAP
        )
        for sector, exposure in exposures.items():
            sector_weights[sector] = (
                sector_weights.get(sector, Decimal(0))
                + ETF_WEIGHT_CAP * exposure
            )
    return {ticker: ETF_WEIGHT_CAP for ticker in selected}, percentiles


def _risk_metrics(returns):
    values = tuple(returns)
    if not values:
        return (None, None, None, None)
    mean = _mean(values)
    with localcontext(_stock._context()):
        variance = _mean(tuple((value - mean) * (value - mean) for value in values))
        annual_return = +(mean * ANNUALIZATION_SESSIONS)
        annual_volatility = +(variance * ANNUALIZATION_SESSIONS).sqrt()
        sharpe = (
            None
            if annual_volatility <= NUMERICAL_ZERO
            else +(annual_return / annual_volatility)
        )
        downside = tuple(min(Decimal(0), value) for value in values)
        downside_deviation = +(
            _mean(tuple(value * value for value in downside))
            * ANNUALIZATION_SESSIONS
        ).sqrt()
        sortino = (
            None
            if downside_deviation <= NUMERICAL_ZERO
            else +(annual_return / downside_deviation)
        )
    return annual_return, annual_volatility, sharpe, sortino


class AcceptedRiskEtfBaselineRuntime:
    """Pure aggregate-only ETF score and arithmetic portfolio evaluator."""

    def __init__(
        self,
        value,
        *,
        evaluation_profile_id,
        qc_sid_to_security_id,
        package_id,
        package_sha256,
    ):
        self._profile = require_etf_baseline_profile(evaluation_profile_id)
        self._contract_id = (
            CONTRACT_ID
            if evaluation_profile_id == PROFILE_ID
            else CORRECTED_CONTRACT_ID
        )
        if type(qc_sid_to_security_id) is not dict or any(
            type(key) is not str or type(item) is not str
            for key, item in qc_sid_to_security_id.items()
        ):
            raise AcceptedRiskEtfBaselineError(
                "QC-to-input security map must be an exact string dictionary"
            )
        self._input = value
        self._replay = _StockScoreReplay(value)
        self._session_positions = {
            session: index for index, session in enumerate(value.session_axis)
        }
        self._qc_sid_to_security_id = dict(qc_sid_to_security_id)
        self._package_id = _safe(package_id, "package id")
        self._package_sha256 = _safe(package_sha256, "package hash")
        self._incoming_snapshots = {}
        self._available_snapshots = {}
        self._last_processed_session = None
        self._bars_by_session = {}
        self._liquidity = {ticker: [] for ticker in CANDIDATE_ETFS}
        self._score_history = {}
        self._active_weights = {}
        self._pending_weights = None
        self._return_accumulators = {
            cost: _PortfolioAccumulator(cost) for cost in COST_BPS_SCENARIOS
        }
        self._spy_wealth = Decimal(1)
        self._previous_opens = None
        self._turnover_sum = Decimal(0)
        self._cash_weight_sum = Decimal(0)
        self._portfolio_return_session_count = 0
        self._invested_return_session_count = 0
        self._decision_session_count = 0
        self._selected_decision_session_count = 0
        self._eligible_etf_count_sum = 0
        self._selected_etf_count_sum = 0
        self._holdings_snapshot_refusal_count = 0
        self._stale_holdings_snapshot_refusal_count = 0
        self._holdings_completeness_refusal_count = 0
        self._mapping_refusal_count = 0
        self._liquidity_refusal_count = 0
        self._stock_sector_refusal_session_count = 0
        self._completed = False
        self._summary = None

    def accept_holdings_snapshot(self, snapshot):
        if type(snapshot) is not EtfHoldingsSnapshot:
            raise AcceptedRiskEtfBaselineError("ETF snapshot type changed")
        snapshot.__post_init__()
        prior = self._incoming_snapshots.get(snapshot.ticker)
        available = self._available_snapshots.get(snapshot.ticker)
        latest = prior if prior is not None else available
        if (
            latest is not None
            and snapshot.observed_session <= latest.observed_session
        ):
            raise AcceptedRiskEtfBaselineError(
                "ETF snapshot sessions must advance strictly per ticker"
            )
        self._incoming_snapshots[snapshot.ticker] = snapshot

    def _record_portfolio_return(self, session, opens):
        previous = self._previous_opens
        if previous is None:
            return
        if not (DECISION_START_SESSION < session <= MEASUREMENT_END_SESSION):
            return
        gross = Decimal(0)
        with localcontext(_stock._context()):
            starting_invested = _stock._stable_sum(
                self._active_weights.values()
            )
            for ticker, weight in self._active_weights.items():
                if ticker not in previous or ticker not in opens:
                    raise AcceptedRiskEtfBaselineError(
                        "held ETF lacks a required adjusted-open endpoint"
                    )
                gross = +(gross + weight * (opens[ticker] / previous[ticker] - Decimal(1)))
            if gross <= Decimal(-1):
                raise AcceptedRiskEtfBaselineError(
                    "ETF portfolio gross return is not survivable"
                )
            if "SPY" not in previous or "SPY" not in opens:
                raise AcceptedRiskEtfBaselineError(
                    "SPY lacks a required adjusted-open endpoint"
                )
            spy_return = +(opens["SPY"] / previous["SPY"] - Decimal(1))
            self._spy_wealth = +(self._spy_wealth * (Decimal(1) + spy_return))
            gross_multiplier = +(Decimal(1) + gross)
            drifted_weights = {
                ticker: +(
                    weight
                    * (opens[ticker] / previous[ticker])
                    / gross_multiplier
                )
                for ticker, weight in self._active_weights.items()
            }
            drifted_cash = +(
                (Decimal(1) - starting_invested) / gross_multiplier
            )
            target = self._pending_weights
            turnover = (
                Decimal(0)
                if target is None
                else _stock._stable_sum(
                    abs(
                        target.get(ticker, Decimal(0))
                        - drifted_weights.get(ticker, Decimal(0))
                    )
                    for ticker in sorted(set(drifted_weights) | set(target))
                )
            )
            for cost, accumulator in self._return_accumulators.items():
                net = +(gross - Decimal(cost) / Decimal(10000) * turnover)
                if net <= Decimal(-1):
                    raise AcceptedRiskEtfBaselineError(
                        "ETF portfolio daily net return is not survivable"
                    )
                accumulator.returns.append(net)
                accumulator.wealth = +(accumulator.wealth * (Decimal(1) + net))
                accumulator.peak = max(accumulator.peak, accumulator.wealth)
                drawdown = +(accumulator.wealth / accumulator.peak - Decimal(1))
                accumulator.maximum_drawdown = min(
                    accumulator.maximum_drawdown, drawdown
                )
            self._turnover_sum = +(self._turnover_sum + turnover)
            self._cash_weight_sum = +(self._cash_weight_sum + drifted_cash)
        self._portfolio_return_session_count += 1
        if starting_invested > 0:
            self._invested_return_session_count += 1
        self._active_weights = (
            drifted_weights if target is None else dict(target)
        )
        self._pending_weights = None

    def _liquid(self, ticker):
        values = self._liquidity[ticker]
        return (
            len(values) >= LIQUIDITY_WINDOW_SESSIONS
            and _median(values[-LIQUIDITY_WINDOW_SESSIONS:])
            >= MINIMUM_DAILY_DOLLAR_VOLUME
        )

    def _decision(self, session):
        memberships, all_scores, sector_refused = self._replay.score(session)
        stock_scores = all_scores[(PRIMARY_SOURCE_VIEW_ID, PRIMARY_SCORE_ARM)]
        sector_by_security = {
            item.security_id: item.sector_id for item in memberships
        }
        if len(sector_by_security) != len(memberships):
            raise AcceptedRiskEtfBaselineError(
                "stock membership contains a duplicate security"
            )
        if sector_refused[(PRIMARY_SOURCE_VIEW_ID, PRIMARY_SCORE_ARM)]:
            self._stock_sector_refusal_session_count += 1
            self._pending_weights = {}
            self._score_history[session] = None
            self._decision_session_count += 1
            return
        position = self._session_positions.get(session)
        if position is None or position == 0:
            raise AcceptedRiskEtfBaselineError(
                "ETF decision session lacks an authenticated prior session"
            )
        required_snapshot_session = self._input.session_axis[position - 1]
        etf_scores = {}
        snapshot_weights = {}
        sector_exposures = {}
        for ticker in CANDIDATE_ETFS:
            if not self._liquid(ticker):
                self._liquidity_refusal_count += 1
                continue
            snapshot = self._available_snapshots.get(ticker)
            if (
                snapshot is None
                or snapshot.observed_session != required_snapshot_session
            ):
                self._holdings_snapshot_refusal_count += 1
                if snapshot is not None:
                    self._stale_holdings_snapshot_refusal_count += 1
                continue
            try:
                score, _coverage, _n_eff, weights, exposures = _score_etf(
                    snapshot,
                    stock_scores,
                    self._qc_sid_to_security_id,
                    sector_by_security,
                )
            except EtfHoldingsCompletenessError:
                self._holdings_completeness_refusal_count += 1
                continue
            except EtfMappingCoverageError:
                self._mapping_refusal_count += 1
                continue
            etf_scores[ticker] = score
            snapshot_weights[ticker] = weights
            sector_exposures[ticker] = exposures
        if (
            self._profile["profile_id"] == PROFILE_ID
            and len(etf_scores) < MINIMUM_ETF_IC_ROWS
        ):
            # Historical R060/R061 only; never re-label their economic rule.
            self._pending_weights = {}
        else:
            self._pending_weights, _percentile_map = _target_weights(
                etf_scores,
                snapshot_weights,
                sector_exposures,
                frozenset(self._active_weights),
            )
        # Statistical sufficiency is separate from admitting economic targets.
        self._score_history[session] = (
            dict(etf_scores) if len(etf_scores) >= MINIMUM_ETF_IC_ROWS else None
        )
        if self._pending_weights:
            self._selected_decision_session_count += 1
        self._decision_session_count += 1
        self._eligible_etf_count_sum += len(etf_scores)
        self._selected_etf_count_sum += len(self._pending_weights)

    def process_session(self, session, bars):
        if self._completed:
            raise AcceptedRiskEtfBaselineError("ETF runtime is already complete")
        _session(session)
        if (
            self._last_processed_session is not None
            and session <= self._last_processed_session
        ):
            raise AcceptedRiskEtfBaselineError(
                "ETF runtime sessions must be strictly increasing"
            )
        if type(bars) is not tuple or any(type(row) is not EtfDailyBar for row in bars):
            raise AcceptedRiskEtfBaselineError("ETF bars must be an exact tuple")
        by_ticker = {}
        for row in bars:
            row.__post_init__()
            if row.session != session or row.ticker in by_ticker:
                raise AcceptedRiskEtfBaselineError(
                    "ETF bars contain a duplicate or mixed session"
                )
            by_ticker[row.ticker] = row
        self._bars_by_session[session] = {
            ticker: row.adjusted_open for ticker, row in by_ticker.items()
        }
        for ticker in CANDIDATE_ETFS:
            row = by_ticker.get(ticker)
            if row is not None:
                with localcontext(_stock._context()):
                    self._liquidity[ticker].append(+(row.adjusted_close * row.volume))
        opens = {ticker: row.adjusted_open for ticker, row in by_ticker.items()}
        self._record_portfolio_return(session, opens)
        if DECISION_START_SESSION <= session <= DECISION_END_SESSION:
            self._decision(session)
        self._previous_opens = opens
        for ticker, snapshot in self._incoming_snapshots.items():
            if snapshot.observed_session <= session:
                self._available_snapshots[ticker] = snapshot
        self._incoming_snapshots = {}
        self._last_processed_session = session

    def _ic_cell(self, horizon):
        valid = 0
        invalid = 0
        values = []
        accepted_pairs = 0
        missing_pairs = 0
        sessions = self._input.session_axis
        session_positions = {session: index for index, session in enumerate(sessions)}
        for session, scores in sorted(self._score_history.items()):
            if scores is None:
                invalid += 1
                continue
            position = session_positions[session]
            if position + 1 + horizon >= len(sessions):
                invalid += 1
                continue
            entry_session = sessions[position + 1]
            exit_session = sessions[position + 1 + horizon]
            entry = self._bars_by_session.get(entry_session, {})
            exit_values = self._bars_by_session.get(exit_session, {})
            spy_entry = entry.get("SPY")
            spy_exit = exit_values.get("SPY")
            pairs = []
            for ticker, score in sorted(scores.items()):
                start = entry.get(ticker)
                end = exit_values.get(ticker)
                if None in (start, end, spy_entry, spy_exit):
                    missing_pairs += 1
                    continue
                with localcontext(_stock._context()):
                    excess = +(
                        end / start
                        - Decimal(1)
                        - (spy_exit / spy_entry - Decimal(1))
                    )
                pairs.append((score, excess))
            accepted_pairs += len(pairs)
            if len(pairs) < MINIMUM_ETF_IC_ROWS:
                invalid += 1
                continue
            try:
                value = _stock._spearman(
                    tuple(row[0] for row in pairs),
                    tuple(row[1] for row in pairs),
                )
            except _stock.PreliminaryRatingEvaluationError:
                invalid += 1
                continue
            valid += 1
            values.append(value)
        return {
            "schema": IC_CELL_SCHEMA,
            "profile_id": self._profile["profile_id"],
            "horizon_sessions": horizon,
            "status": (
                "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
                if valid >= 50
                else "INCONCLUSIVE_UNDERFILLED"
            ),
            "valid_ic_date_count": valid,
            "invalid_ic_date_count": invalid,
            "accepted_outcome_pair_count": accepted_pairs,
            "missing_outcome_pair_count": missing_pairs,
            "mean_daily_spearman_ic": (
                None if not values else _decimal_text(_mean(tuple(values)))
            ),
            "median_daily_spearman_ic": (
                None if not values else _decimal_text(_median(tuple(values)))
            ),
            "positive_ic_date_share": (
                None
                if not values
                else _decimal_text(
                    _stock._positive_share(tuple(values))
                )
            ),
            "entry_timing": "next_session_open",
            "benchmark": "SPY_total_return_adjusted_open_to_open",
            "formal_accept_reject_disposition": None,
        }

    def _portfolio_cell(self, cost, accumulator):
        annual_return, annual_volatility, sharpe, sortino = _risk_metrics(
            accumulator.returns
        )
        with localcontext(_stock._context()):
            average_turnover = (
                None
                if self._portfolio_return_session_count == 0
                else +(
                    self._turnover_sum
                    / Decimal(self._portfolio_return_session_count)
                )
            )
            average_cash = (
                None
                if self._portfolio_return_session_count == 0
                else +(
                    self._cash_weight_sum
                    / Decimal(self._portfolio_return_session_count)
                )
            )
            cumulative_return = +(accumulator.wealth - Decimal(1))
            spy_cumulative_return = +(self._spy_wealth - Decimal(1))
            cumulative_excess = +(accumulator.wealth - self._spy_wealth)
        return {
            "schema": PORTFOLIO_CELL_SCHEMA,
            "profile_id": self._profile["profile_id"],
            "cost_bps_per_side": cost,
            "primary_cost_scenario": cost == PRIMARY_COST_BPS,
            "status": (
                "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
                if (
                    self._portfolio_return_session_count >= 252
                    and self._invested_return_session_count
                    >= MINIMUM_INVESTED_RETURN_SESSIONS
                )
                else "INCONCLUSIVE_UNDERFILLED"
            ),
            "return_session_count": self._portfolio_return_session_count,
            "invested_return_session_count": (
                self._invested_return_session_count
            ),
            "cumulative_return": _decimal_text(cumulative_return),
            "spy_cumulative_return": _decimal_text(spy_cumulative_return),
            "cumulative_return_minus_spy": _decimal_text(cumulative_excess),
            "annualized_arithmetic_return": (
                None if annual_return is None else _decimal_text(annual_return)
            ),
            "annualized_volatility": (
                None if annual_volatility is None else _decimal_text(annual_volatility)
            ),
            "zero_rate_sharpe": None if sharpe is None else _decimal_text(sharpe),
            "zero_rate_sortino": None if sortino is None else _decimal_text(sortino),
            "maximum_drawdown": _decimal_text(accumulator.maximum_drawdown),
            "average_daily_two_sided_turnover": (
                None if average_turnover is None else _decimal_text(average_turnover)
            ),
            "average_cash_weight": (
                None if average_cash is None else _decimal_text(average_cash)
            ),
            "leverage": False,
            "orders_submitted": 0,
            "formal_accept_reject_disposition": None,
        }

    def complete(self):
        if self._completed:
            return
        if (
            self._last_processed_session is None
            or self._last_processed_session < OUTCOME_MATURITY_END_SESSION
        ):
            raise AcceptedRiskEtfBaselineError(
                "ETF outcome history ended before the frozen maturity date"
            )
        expected_decision_sessions = tuple(
            session for session in self._input.session_axis
            if DECISION_START_SESSION <= session <= DECISION_END_SESSION
        )
        if (
            tuple(sorted(self._score_history)) != expected_decision_sessions
            or self._decision_session_count != len(expected_decision_sessions)
        ):
            raise AcceptedRiskEtfBaselineError(
                "ETF decision-score census is not exhaustive"
            )
        ic_cells = [self._ic_cell(horizon) for horizon in HORIZONS]
        portfolio_cells = [
            self._portfolio_cell(cost, self._return_accumulators[cost])
            for cost in COST_BPS_SCENARIOS
        ]
        with localcontext(_stock._context()):
            mean_eligible = (
                Decimal(0)
                if self._decision_session_count == 0
                else +(
                    Decimal(self._eligible_etf_count_sum)
                    / Decimal(self._decision_session_count)
                )
            )
            mean_selected = (
                Decimal(0)
                if self._decision_session_count == 0
                else +(
                    Decimal(self._selected_etf_count_sum)
                    / Decimal(self._decision_session_count)
                )
            )
        record = {
            "schema": SUMMARY_SCHEMA,
            "contract_id": self._contract_id,
            "profile": dict(self._profile),
            "package_id": self._package_id,
            "package_sha256": self._package_sha256,
            "input_manifest_id": self._input.manifest_id,
            "input_manifest_sha256": self._input.manifest_sha256,
            "status": "PRELIMINARY_ACCEPTED_RISK_UNLEVERED_ETF_BASELINE",
            "decision_session_count": self._decision_session_count,
            "portfolio_return_session_count": self._portfolio_return_session_count,
            "invested_return_session_count": self._invested_return_session_count,
            "selected_decision_session_count": (
                self._selected_decision_session_count
            ),
            "mean_eligible_etf_count": _decimal_text(mean_eligible),
            "mean_selected_etf_count": _decimal_text(mean_selected),
            "holdings_snapshot_refusal_count": self._holdings_snapshot_refusal_count,
            "stale_holdings_snapshot_refusal_count": (
                self._stale_holdings_snapshot_refusal_count
            ),
            "holdings_completeness_refusal_count": (
                self._holdings_completeness_refusal_count
            ),
            "mapping_refusal_count": self._mapping_refusal_count,
            "liquidity_refusal_count": self._liquidity_refusal_count,
            "stock_sector_refusal_session_count": (
                self._stock_sector_refusal_session_count
            ),
            "holdings_source": "QuantConnect_US_ETF_Constituents",
            "holdings_point_in_time_claim": (
                "QC_callback_observation_from_exact_previous_authenticated_session"
            ),
            "fixed_sleeve_is_exhaustive_reverse_index": False,
            "aum_filter_applied": False,
            "aum_filter_omission": "no_reliable_point_in_time_AUM_input",
            "peer_normalization": "global_fixed_sleeve_percentile",
            "direct_stock_comparator_present": False,
            "industry_comparator_present": False,
            "market_benchmark_present": True,
            "terminal_payoff_applied": False,
            "current_vintage_non_pristine_pit_input": True,
            "raw_provider_rows_in_summary": False,
            "raw_constituent_rows_in_summary": False,
            "raw_price_rows_in_summary": False,
            "formal_result": False,
            "alpha_claim_authorized": False,
            "economic_portfolio_evaluation": True,
            "leverage": False,
            "deployment": False,
            "orders": False,
            "trading": False,
            "ic_cells": ic_cells,
            "portfolio_cells": portfolio_cells,
        }
        digest = _sha(record)
        self._summary = {
            **record,
            "summary_id": "arv2-etf-sector-baseline-summary-" + digest[:24],
            "summary_sha256": digest,
        }
        self._completed = True

    @property
    def completed(self):
        return self._completed

    def aggregate_summary(self):
        if not self._completed or self._summary is None:
            raise AcceptedRiskEtfBaselineError("ETF summary is not complete")
        return json.loads(_canonical(self._summary).decode("ascii"))

    def custom_summary_statistics(self):
        summary = self.aggregate_summary()
        ic_cells = summary.pop("ic_cells")
        portfolio_cells = summary.pop("portfolio_cells")
        output = {"ARV2_ETF_2021_2025_META": _canonical(summary).decode("ascii")}
        for cell in ic_cells:
            output["ARV2_ETF_IC_H" + str(cell["horizon_sessions"])] = (
                _canonical(cell).decode("ascii")
            )
        for cell in portfolio_cells:
            output[
                "ARV2_ETF_PORTFOLIO_COST_" + str(cell["cost_bps_per_side"])
            ] = _canonical(cell).decode("ascii")
        if tuple(sorted(output)) != expected_custom_summary_statistic_names(
            self._profile["profile_id"]
        ):
            raise AcceptedRiskEtfBaselineError(
                "ETF custom summary statistic inventory changed"
            )
        if any(len(key) > 64 or len(value) > 4096 for key, value in output.items()):
            raise AcceptedRiskEtfBaselineError(
                "ETF custom summary statistic exceeded compact bound"
            )
        return dict(sorted(output.items()))


__all__ = (
    "AcceptedRiskEtfBaselineError",
    "AcceptedRiskEtfBaselineRuntime",
    "CANDIDATE_ETFS",
    "CONTRACT_ID",
    "CORRECTED_CONTRACT_ID",
    "CORRECTED_PROFILE_ID",
    "CORRECTED_PROFILE_SCHEMA",
    "ConstituentWeight",
    "COST_BPS_SCENARIOS",
    "DECISION_END_SESSION",
    "DECISION_START_SESSION",
    "ETF_SECTOR_BY_TICKER",
    "EtfDailyBar",
    "EtfHoldingsSnapshot",
    "HORIZONS",
    "IC_CELL_SCHEMA",
    "MEASUREMENT_END_SESSION",
    "OUTCOME_MATURITY_END_SESSION",
    "PORTFOLIO_CELL_SCHEMA",
    "PRIMARY_COST_BPS",
    "PROFILE_ID",
    "PROFILE_SCHEMA",
    "SUMMARY_SCHEMA",
    "WARMUP_START_SESSION",
    "expected_custom_summary_statistic_names",
    "require_etf_baseline_profile",
)
