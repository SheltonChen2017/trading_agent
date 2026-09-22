"""Pure economics for the accepted-risk six-universe gate diagnostic.

The evaluator binds the already-frozen six-universe constructor to one exact
2021--2025 weekly, next-open, ten-basis-point diagnostic.  It contains no
provider, QuantConnect, Object Store, network, order, deployment, or trading
capability.  QuantConnect is only a typed history provider to ``run_callback``.
"""

import dataclasses
import hashlib
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum

try:
    import accepted_risk_preliminary_rating_evaluator as _base
    import accepted_risk_sequential_r055_score as _score
    import accepted_risk_six_universe_gate as _gate
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as _base,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_sequential_r055_score as _score,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_gate as _gate,
    )


class SixUniverseGateEvaluationError(_base.PreliminaryRatingEvaluationError):
    """A frozen profile, input, history row, or economic invariant changed."""


PROFILE_SCHEMA = "arv2-six-universe-gate-evaluation-profile-v1"
SUMMARY_SCHEMA = "arv2-six-universe-gate-summary-v1"
ACCOUNT_SCHEMA = "arv2-six-universe-gate-account-aggregate-v1"
SLEEVE_SCHEMA = "arv2-six-universe-gate-sleeve-diagnostics-v1"
SERIES_SCHEMA = "arv2-six-universe-gate-etf-series-bindings-v1"
DECISION_START_SESSION = "2021-01-04"
EVALUATION_END_SESSION = "2025-12-31"
EXPECTED_SESSION_COUNT = 1_255
EXPECTED_RETURN_SESSION_COUNT = 1_254
EXPECTED_DECISION_SESSION_COUNT = 261
PRIMARY_COST_BPS_PER_SIDE = 10
MODELED_COST_RATE_PER_SIDE = Decimal("0.001")
MINIMUM_INVESTED_RETURN_SESSIONS = 50
ANNUALIZATION_SESSIONS = Decimal(252)
MAXIMUM_HISTORY_SLOT_COUNT = 10_000_000
MAXIMUM_STATISTIC_BYTES = 4_096
GATE_SCORE_QUANTUM = Decimal("1e-48")

META_STATISTIC_NAME = "ARV2_SIX_GATE_META"
SIGNAL_STATISTIC_NAME = "ARV2_SIX_GATE_SIGNAL"
MATCHED_STATISTIC_NAME = "ARV2_SIX_GATE_MATCHED"
ETF_BASKET_STATISTIC_NAME = "ARV2_SIX_GATE_ETF_BASKET"
SLEEVES_STATISTIC_NAME = "ARV2_SIX_GATE_SLEEVES"
SERIES_STATISTIC_NAME = "ARV2_SIX_GATE_SERIES"


def _canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SixUniverseGateEvaluationError(
            "six-universe evaluation value is not canonical ASCII JSON"
        ) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal(value, name, *, positive=False, nonnegative=False):
    if type(value) is not Decimal or not value.is_finite():
        raise SixUniverseGateEvaluationError(
            name + " must be an exact finite Decimal"
        )
    if positive and value <= 0:
        raise SixUniverseGateEvaluationError(name + " must be positive")
    if nonnegative and value < 0:
        raise SixUniverseGateEvaluationError(name + " must be nonnegative")
    return value


def _decimal_text(value):
    _decimal(value, "six-universe record Decimal")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _stable_sum(values):
    with localcontext() as context:
        context.prec = 96
        result = Decimal(0)
        for value in values:
            result += value
        return +result


def _gate_score(value, *, quantum):
    if value is None:
        return None
    _decimal(value, "six-universe R055 score")
    try:
        with localcontext() as context:
            context.prec = 96
            result = value.quantize(quantum, rounding=ROUND_HALF_EVEN)
    except Exception as exc:
        raise SixUniverseGateEvaluationError(
            "six-universe R055 score escaped the gate Decimal boundary"
        ) from exc
    decimal_tuple = result.as_tuple()
    if len(decimal_tuple.digits) > 64 or decimal_tuple.exponent != -48:
        raise SixUniverseGateEvaluationError(
            "six-universe R055 score escaped the gate Decimal boundary"
        )
    return result


def _safe_text(value, name):
    if type(value) is not str or not value or value.strip() != value:
        raise SixUniverseGateEvaluationError(name + " is not exact text")
    return value


def _profile_semantic(
    gate_profile,
    *,
    modeled_cost_rate_per_side,
    annualization_sessions,
    gate_score_quantum,
):
    gate_record = gate_profile.to_record()
    return {
        "schema": PROFILE_SCHEMA,
        "gate_profile_id": gate_record["profile_id"],
        "gate_profile_sha256": gate_record["profile_sha256"],
        "evaluation_start_session": DECISION_START_SESSION,
        "evaluation_end_session": EVALUATION_END_SESSION,
        "expected_session_count": EXPECTED_SESSION_COUNT,
        "expected_return_session_count": EXPECTED_RETURN_SESSION_COUNT,
        "expected_decision_session_count": EXPECTED_DECISION_SESSION_COUNT,
        "rebalance_schedule": "first_authenticated_session_of_each_ISO_week",
        "execution_timing": "next_authenticated_session_total_return_adjusted_open",
        "target_gross_exposure": _decimal_text(_gate.TARGET_GROSS_EXPOSURE),
        "cash_return": "0",
        "cost_bps_per_side": PRIMARY_COST_BPS_PER_SIDE,
        "modeled_cost_rate_per_side": _decimal_text(
            modeled_cost_rate_per_side
        ),
        "cost_turnover_basis": "absolute_weight_change_two_sided",
        "annualization_sessions": _decimal_text(annualization_sessions),
        "minimum_invested_return_sessions_per_stock_account": (
            MINIMUM_INVESTED_RETURN_SESSIONS
        ),
        "accounts": ["signal", "matched", "six_etf_basket"],
        "within_eligibility_missing_price_rule": (
            "carry_last_mark_and_defer_only_that_position"
        ),
        "eligibility_exit_missing_price_rule": (
            "zero_recovery_conservative_sensitivity"
        ),
        "missing_entry_price_rule": "omit_entry_and_retain_cash",
        "price_normalization": "TOTAL_RETURN",
        "price_observation": "session_open",
        "etf_price_series_requirement": (
            "all_six_ETFs_have_one_positive_open_on_every_evaluation_session"
        ),
        "analyst_source_view": _gate.SOURCE_VIEW_ID,
        "score_decimal_boundary": (
            "R055_score_ROUND_HALF_EVEN_to_exactly_48_fractional_places"
        ),
        "gate_score_quantum": _decimal_text(gate_score_quantum),
        "slot_count_per_sleeve": gate_record["slot_count_per_sleeve"],
        "point_in_time_etf_membership_and_market_cap": True,
        "point_in_time_analyst_archive": False,
        "current_vintage_identity_basis": True,
        "preliminary_accepted_risk": True,
        "orders": False,
        "deployment": False,
        "trading": False,
    }


@dataclasses.dataclass(frozen=True, slots=True)
class SixUniverseEvaluationProfile:
    profile_id: str
    profile_sha256: str
    gate_profile: _gate.GateProfile
    modeled_cost_rate_per_side: Decimal
    annualization_sessions: Decimal
    gate_score_quantum: Decimal

    def to_record(self):
        if (
            type(MODELED_COST_RATE_PER_SIDE) is not Decimal
            or MODELED_COST_RATE_PER_SIDE != self.modeled_cost_rate_per_side
            or type(ANNUALIZATION_SESSIONS) is not Decimal
            or ANNUALIZATION_SESSIONS != self.annualization_sessions
            or type(GATE_SCORE_QUANTUM) is not Decimal
            or GATE_SCORE_QUANTUM != self.gate_score_quantum
        ):
            raise SixUniverseGateEvaluationError(
                "six-universe evaluation economic constants changed"
            )
        semantic = _profile_semantic(
            self.gate_profile,
            modeled_cost_rate_per_side=self.modeled_cost_rate_per_side,
            annualization_sessions=self.annualization_sessions,
            gate_score_quantum=self.gate_score_quantum,
        )
        if _sha(semantic) != self.profile_sha256:
            raise SixUniverseGateEvaluationError(
                "six-universe evaluation profile authority changed"
            )
        return {
            **semantic,
            "profile_id": self.profile_id,
            "profile_sha256": self.profile_sha256,
        }


def _build_profile(gate_profile):
    modeled_cost_rate_per_side = _decimal(
        MODELED_COST_RATE_PER_SIDE,
        "six-universe modeled cost rate",
        nonnegative=True,
    )
    annualization_sessions = _decimal(
        ANNUALIZATION_SESSIONS,
        "six-universe annualization sessions",
        positive=True,
    )
    gate_score_quantum = _decimal(
        GATE_SCORE_QUANTUM,
        "six-universe gate score quantum",
        positive=True,
    )
    semantic = _profile_semantic(
        gate_profile,
        modeled_cost_rate_per_side=modeled_cost_rate_per_side,
        annualization_sessions=annualization_sessions,
        gate_score_quantum=gate_score_quantum,
    )
    digest = _sha(semantic)
    return SixUniverseEvaluationProfile(
        "arv2-six-universe-evaluation-"
        + gate_profile.label
        + "-"
        + digest[:24],
        digest,
        gate_profile,
        modeled_cost_rate_per_side,
        annualization_sessions,
        gate_score_quantum,
    )


TOP10_PRIMARY_PROFILE = _build_profile(_gate.TOP10_PRIMARY_PROFILE)
TOP5_SENSITIVITY_PROFILE = _build_profile(_gate.TOP5_SENSITIVITY_PROFILE)
TOP10_CAP95_EXPLORATORY_PROFILE = _build_profile(
    _gate.TOP10_CAP95_EXPLORATORY_PROFILE
)
PROFILES = (
    TOP10_PRIMARY_PROFILE,
    TOP5_SENSITIVITY_PROFILE,
    TOP10_CAP95_EXPLORATORY_PROFILE,
)
PROFILE_IDS = tuple(item.profile_id for item in PROFILES)


def require_profile(profile_id):
    if type(profile_id) is not str:
        raise SixUniverseGateEvaluationError(
            "six-universe evaluation profile id changed type"
        )
    for profile in PROFILES:
        if profile.profile_id == profile_id:
            profile.to_record()
            return profile
    raise SixUniverseGateEvaluationError(
        "six-universe evaluation profile is not frozen"
    )


def expected_custom_summary_statistic_names(profile_id):
    require_profile(profile_id)
    return tuple(
        sorted(
            (
                META_STATISTIC_NAME,
                SIGNAL_STATISTIC_NAME,
                MATCHED_STATISTIC_NAME,
                ETF_BASKET_STATISTIC_NAME,
                SLEEVES_STATISTIC_NAME,
                SERIES_STATISTIC_NAME,
            )
        )
    )


def decision_sessions_for_input(value):
    if type(value) is not _base.PreliminaryRatingInput:
        raise SixUniverseGateEvaluationError(
            "six-universe decision schedule requires exact preliminary input"
        )
    axis = value.session_axis
    if (
        type(axis) is not tuple
        or any(type(item) is not str for item in axis)
        or tuple(sorted(set(axis))) != axis
    ):
        raise SixUniverseGateEvaluationError(
            "six-universe authenticated session axis changed"
        )
    try:
        start = axis.index(DECISION_START_SESSION)
        end = axis.index(EVALUATION_END_SESSION)
    except ValueError as exc:
        raise SixUniverseGateEvaluationError(
            "six-universe window escaped the authenticated session axis"
        ) from exc
    period = axis[start : end + 1]
    if len(period) != EXPECTED_SESSION_COUNT:
        raise SixUniverseGateEvaluationError(
            "six-universe session geometry changed"
        )
    decisions = []
    prior_week = None
    for session in period:
        try:
            parsed = date.fromisoformat(session)
        except ValueError as exc:
            raise SixUniverseGateEvaluationError(
                "six-universe session axis contains a non-date"
            ) from exc
        week = (parsed.isocalendar().year, parsed.isocalendar().week)
        if week != prior_week:
            decisions.append(session)
            prior_week = week
    if (
        len(decisions) != EXPECTED_DECISION_SESSION_COUNT
        or any(axis.index(session) + 1 > end for session in decisions)
    ):
        raise SixUniverseGateEvaluationError(
            "six-universe decision geometry changed"
        )
    return tuple(decisions)


@dataclasses.dataclass(frozen=True, slots=True)
class PitDecisionSnapshot:
    session: str
    universes: tuple[_gate.UniverseSnapshot, ...]


class EvaluationPhase(Enum):
    HISTORY = "history"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclasses.dataclass(frozen=True, slots=True)
class _Decision:
    session: str
    construction: _gate.SixUniverseConstruction
    mapped_member_ids: frozenset[str]


@dataclasses.dataclass
class _Accumulator:
    wealth: Decimal = Decimal(1)
    peak: Decimal = Decimal(1)
    maximum_drawdown: Decimal = Decimal(0)
    returns: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class _Account:
    role: str
    weights: dict = dataclasses.field(default_factory=dict)
    marks: dict = dataclasses.field(default_factory=dict)
    accumulator: _Accumulator = dataclasses.field(default_factory=_Accumulator)
    turnover_sum: Decimal = Decimal(0)
    cash_weight_sum: Decimal = Decimal(0)
    holding_count_sum: int = 0
    invested_return_session_count: int = 0
    rebalance_count: int = 0
    full_target_count: int = 0
    underfilled_target_count: int = 0
    locked_over_target_count: int = 0
    entry_price_refusal_count: int = 0
    stale_mark_session_count: int = 0
    stale_position_deferral_count: int = 0
    eligibility_exit_zero_recovery_count: int = 0
    target_effective_holdings: list = dataclasses.field(default_factory=list)
    target_maximum_weights: list = dataclasses.field(default_factory=list)


def _risk_metrics(returns, *, annualization_sessions):
    if not returns:
        return None, None, None
    with localcontext() as context:
        context.prec = 96
        mean = +(_stable_sum(returns) / Decimal(len(returns)))
        annual = +(mean * annualization_sessions)
        if len(returns) < 2:
            return annual, None, None
        variance = +(
            _stable_sum((item - mean) ** 2 for item in returns)
            / Decimal(len(returns) - 1)
        )
        volatility = +(variance.sqrt() * annualization_sessions.sqrt())
        sharpe = None if volatility == 0 else +(annual / volatility)
    return annual, volatility, sharpe


class SixUniverseGateEvaluationRuntime:
    """Construct and evaluate the two frozen six-universe diagnostics."""

    def __init__(
        self,
        value,
        *,
        profile_id,
        package_id,
        package_sha256,
        symbol_resolution_id,
        symbol_resolution_sha256,
        decision_snapshots,
        pit_history_call_count=0,
        pit_source_row_count=0,
    ):
        if type(value) is not _base.PreliminaryRatingInput:
            raise SixUniverseGateEvaluationError(
                "six-universe evaluator requires exact preliminary input"
            )
        self._input = value
        self._profile = require_profile(profile_id)
        self._package_id = _safe_text(package_id, "six-universe package id")
        self._package_sha256 = self._hash_text(
            package_sha256, "six-universe package"
        )
        self._symbol_resolution_id = _safe_text(
            symbol_resolution_id, "six-universe resolution id"
        )
        self._symbol_resolution_sha256 = self._hash_text(
            symbol_resolution_sha256, "six-universe resolution"
        )
        if (
            type(pit_history_call_count) is not int
            or pit_history_call_count < 0
            or type(pit_source_row_count) is not int
            or pit_source_row_count < 0
        ):
            raise SixUniverseGateEvaluationError(
                "six-universe PIT runtime census changed"
            )
        self._pit_history_call_count = pit_history_call_count
        self._pit_source_row_count = pit_source_row_count
        decisions = decision_sessions_for_input(value)
        if (
            type(decision_snapshots) is not tuple
            or len(decision_snapshots) != len(decisions)
            or any(type(item) is not PitDecisionSnapshot for item in decision_snapshots)
            or tuple(item.session for item in decision_snapshots) != decisions
        ):
            raise SixUniverseGateEvaluationError(
                "six-universe PIT decision snapshot census changed"
            )
        self._decisions = self._construct(decision_snapshots)
        target_ids = set()
        for decision in self._decisions.values():
            for weights in (
                decision.construction.signal_weights,
                decision.construction.matched_weights,
                decision.construction.etf_basket_weights,
            ):
                target_ids.update(item.security_id for item in weights)
        if not target_ids:
            raise SixUniverseGateEvaluationError(
                "six-universe target inventory is empty"
            )
        self._history_security_ids = tuple(sorted(target_ids))
        batch_size = value.history_batch_security_count
        self._history_batches = tuple(
            self._history_security_ids[index : index + batch_size]
            for index in range(0, len(self._history_security_ids), batch_size)
        )
        sessions = value.session_axis
        start = sessions.index(DECISION_START_SESSION)
        end = sessions.index(EVALUATION_END_SESSION)
        self._history_sessions = sessions[start : end + 1]
        if (
            len(self._history_sessions) != EXPECTED_SESSION_COUNT
            or len(self._history_sessions) * len(self._history_security_ids)
            > MAXIMUM_HISTORY_SLOT_COUNT
        ):
            raise SixUniverseGateEvaluationError(
                "six-universe price-history geometry changed"
            )
        self._history_prices = {}
        self._history_batch_index = 0
        self._phase = EvaluationPhase.HISTORY
        self._summary = None

    @staticmethod
    def _hash_text(value, name):
        if (
            type(value) is not str
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise SixUniverseGateEvaluationError(name + " is not SHA-256")
        return value

    @property
    def phase(self):
        return self._phase

    @property
    def history_security_ids(self):
        return tuple(self._history_security_ids)

    @property
    def history_batch_count(self):
        return len(self._history_batches)

    def _construct(self, snapshots):
        axis = self._input.session_axis
        start_position = axis.index(DECISION_START_SESSION)
        scorer = _score.SequentialR055ScoreRuntime(
            self._input,
            start_position=start_position,
        )
        decisions = {}
        etf_id_by_universe = None
        construction_records = []
        for item in snapshots:
            score = scorer.score_session(item.session)
            enriched = []
            mapped_members = set()
            for snapshot in item.universes:
                rows = []
                for row in snapshot.constituents:
                    if row.firm_specific_score is not None:
                        raise SixUniverseGateEvaluationError(
                            "PIT snapshot attempted to inject an R055 score"
                        )
                    if row.security_id is not None:
                        mapped_members.add(row.security_id)
                    rows.append(
                        dataclasses.replace(
                            row,
                            firm_specific_score=(
                                None
                                if row.security_id is None
                                else _gate_score(
                                    score.primary_view_firm_specific_scores.get(
                                        row.security_id
                                    ),
                                    quantum=self._profile.gate_score_quantum,
                                )
                            ),
                        )
                    )
                enriched.append(
                    dataclasses.replace(snapshot, constituents=tuple(rows))
                )
            construction = _gate.build_six_universe_construction(
                tuple(enriched), self._profile.gate_profile
            )
            current_etfs = tuple(
                (sleeve.universe_id, sleeve.etf_security_id)
                for sleeve in construction.sleeves
            )
            if etf_id_by_universe is None:
                etf_id_by_universe = current_etfs
            elif current_etfs != etf_id_by_universe:
                raise SixUniverseGateEvaluationError(
                    "six-universe ETF security identity changed through time"
                )
            record = construction.to_record()
            construction_records.append([item.session, record])
            decisions[item.session] = _Decision(
                item.session,
                construction,
                frozenset(mapped_members),
            )
        self._construction_path_sha256 = _sha(
            {
                "schema": "arv2-six-universe-construction-path-v1",
                "records": construction_records,
            }
        )
        self._etf_id_by_universe = tuple(etf_id_by_universe or ())
        return decisions

    def _history_request(self, index):
        security_ids = self._history_batches[index]
        seed = {
            "schema": _base.HISTORY_REQUEST_SCHEMA,
            "request_index": index,
            "security_ids": list(security_ids),
            "start_session": DECISION_START_SESSION,
            "end_session": EVALUATION_END_SESSION,
            "normalization_mode": "total_return",
            "observation": "session_open",
        }
        return _base.TotalReturnHistoryRequest(
            _base.HISTORY_REQUEST_SCHEMA,
            index,
            security_ids,
            DECISION_START_SESSION,
            EVALUATION_END_SESSION,
            "total_return",
            "session_open",
            _sha(seed),
        )

    def _accept_history(self, request, observations):
        if type(observations) is not tuple:
            raise SixUniverseGateEvaluationError(
                "six-universe history loader must return an exact tuple"
            )
        maximum = len(request.security_ids) * len(self._history_sessions)
        if len(observations) > maximum:
            raise SixUniverseGateEvaluationError(
                "six-universe history loader exceeded request geometry"
            )
        permitted_ids = set(request.security_ids)
        permitted_sessions = set(self._history_sessions)
        seen = set()
        pending = []
        for item in observations:
            if type(item) is not _base.TotalReturnOpenObservation:
                raise SixUniverseGateEvaluationError(
                    "six-universe history loader returned the wrong record type"
                )
            item.__post_init__()
            key = (item.security_id, item.session)
            if (
                item.security_id not in permitted_ids
                or item.session not in permitted_sessions
                or key in seen
                or key in self._history_prices
            ):
                raise SixUniverseGateEvaluationError(
                    "six-universe history observation identity changed"
                )
            seen.add(key)
            pending.append((key, item.adjusted_open))
        for key, value in pending:
            self._history_prices[key] = value

    def run_callback(self, history_loader):
        if self._phase is EvaluationPhase.ABORTED:
            raise SixUniverseGateEvaluationError(
                "six-universe evaluator is closed after abort"
            )
        if self._phase is EvaluationPhase.COMPLETED:
            return None
        if not callable(history_loader):
            raise SixUniverseGateEvaluationError(
                "six-universe history loader is not callable"
            )
        try:
            request = self._history_request(self._history_batch_index)
            observations = history_loader(request)
            self._accept_history(request, observations)
            self._history_batch_index += 1
            if self._history_batch_index == len(self._history_batches):
                self._summary = self._build_summary()
                self._phase = EvaluationPhase.COMPLETED
        except Exception:
            self._phase = EvaluationPhase.ABORTED
            raise
        return self._history_batch_index, len(self._history_batches)

    def abort(self):
        if self._phase is not EvaluationPhase.COMPLETED:
            self._phase = EvaluationPhase.ABORTED

    def _price(self, security_id, position):
        session = self._input.session_axis[position]
        return self._history_prices.get((security_id, session))

    @staticmethod
    def _target_map(weights):
        result = {}
        for item in weights:
            if item.security_id in result:
                raise SixUniverseGateEvaluationError(
                    "six-universe final target identity is duplicated"
                )
            result[item.security_id] = item.weight
        if _stable_sum(result.values()) != _gate.TARGET_GROSS_EXPOSURE:
            raise SixUniverseGateEvaluationError(
                "six-universe final target gross changed"
            )
        return result

    def _advance_account(self, account, position, desired, eligible):
        starting_invested = _stable_sum(account.weights.values())
        ratios = {}
        stale = set()
        eligibility_exits = set()
        for security_id in tuple(sorted(account.weights)):
            prior = account.marks.get(security_id)
            if prior is None:
                raise SixUniverseGateEvaluationError(
                    "six-universe holding lacks its prior observed mark"
                )
            current = self._price(security_id, position)
            if current is None and security_id not in eligible:
                ratios[security_id] = Decimal(0)
                eligibility_exits.add(security_id)
                account.eligibility_exit_zero_recovery_count += 1
            elif current is None:
                ratios[security_id] = Decimal(1)
                stale.add(security_id)
            else:
                with localcontext() as context:
                    context.prec = 96
                    ratios[security_id] = +(current / prior)
                account.marks[security_id] = current
        if stale:
            account.stale_mark_session_count += 1
        with localcontext() as context:
            context.prec = 96
            gross_return = +_stable_sum(
                weight * (ratios[security_id] - Decimal(1))
                for security_id, weight in account.weights.items()
            )
            multiplier = +(Decimal(1) + gross_return)
            if multiplier <= 0:
                raise SixUniverseGateEvaluationError(
                    "six-universe gross return is not survivable"
                )
            pretrade = {
                security_id: +(weight * ratios[security_id] / multiplier)
                for security_id, weight in account.weights.items()
            }
            drifted = {
                security_id: weight
                for security_id, weight in pretrade.items()
                if security_id not in eligibility_exits
            }
        for security_id in eligibility_exits:
            account.marks.pop(security_id, None)

        turnover = Decimal(0)
        if desired is not None:
            locked = {
                security_id: drifted[security_id]
                for security_id in sorted(stale)
            }
            locked_gross = _stable_sum(locked.values())
            remaining = max(Decimal(0), _gate.TARGET_GROSS_EXPOSURE - locked_gross)
            proposed = {}
            for security_id, target_weight in sorted(desired.items()):
                if security_id in locked:
                    continue
                price = self._price(security_id, position)
                if price is None:
                    account.entry_price_refusal_count += 1
                    continue
                proposed[security_id] = target_weight
            proposed_gross = _stable_sum(proposed.values())
            if proposed_gross > remaining and proposed_gross > 0:
                with localcontext() as context:
                    context.prec = 96
                    scale = +(remaining / proposed_gross)
                    proposed = {
                        security_id: +(weight * scale)
                        for security_id, weight in proposed.items()
                    }
            targets = {**locked, **proposed}
            with localcontext() as context:
                context.prec = 96
                turnover = +_stable_sum(
                    abs(
                        targets.get(security_id, Decimal(0))
                        - pretrade.get(security_id, Decimal(0))
                    )
                    for security_id in sorted(set(targets) | set(pretrade))
                    if security_id not in stale
                )
            gross = _stable_sum(targets.values())
            account.rebalance_count += 1
            account.stale_position_deferral_count += len(stale)
            if gross == _gate.TARGET_GROSS_EXPOSURE:
                account.full_target_count += 1
            elif gross < _gate.TARGET_GROSS_EXPOSURE:
                account.underfilled_target_count += 1
            else:
                account.locked_over_target_count += 1
            account.weights = targets
            account.marks = {
                **{
                    security_id: account.marks[security_id]
                    for security_id in locked
                },
                **{
                    security_id: self._price(security_id, position)
                    for security_id in proposed
                },
            }
            if gross > 0:
                with localcontext() as context:
                    context.prec = 96
                    hhi = +_stable_sum(
                        (weight / gross) ** 2 for weight in targets.values()
                    )
                    account.target_effective_holdings.append(+(Decimal(1) / hhi))
                    account.target_maximum_weights.append(max(targets.values()))
        else:
            account.weights = drifted

        with localcontext() as context:
            context.prec = 96
            net_return = +(
                gross_return
                - self._profile.modeled_cost_rate_per_side * turnover
            )
            if net_return <= -1:
                raise SixUniverseGateEvaluationError(
                    "six-universe net return is not survivable"
                )
            accumulator = account.accumulator
            accumulator.returns.append(net_return)
            accumulator.wealth = +(accumulator.wealth * (Decimal(1) + net_return))
            accumulator.peak = max(accumulator.peak, accumulator.wealth)
            accumulator.maximum_drawdown = min(
                accumulator.maximum_drawdown,
                +(accumulator.wealth / accumulator.peak - Decimal(1)),
            )
            account.turnover_sum = +(account.turnover_sum + turnover)
            invested = _stable_sum(account.weights.values())
            cash = +(Decimal(1) - invested)
            if cash < Decimal("-1e-18"):
                raise SixUniverseGateEvaluationError(
                    "six-universe account exceeded one hundred percent"
                )
            account.cash_weight_sum = +(account.cash_weight_sum + max(Decimal(0), cash))
        account.holding_count_sum += len(account.weights)
        if starting_invested > 0:
            account.invested_return_session_count += 1

    def _simulate(self):
        accounts = {
            "signal": _Account("signal"),
            "matched": _Account("matched"),
            "six_etf_basket": _Account("six_etf_basket"),
        }
        sessions = self._input.session_axis
        start = sessions.index(DECISION_START_SESSION)
        end = sessions.index(EVALUATION_END_SESSION)
        etf_ids = frozenset(item[1] for item in self._etf_id_by_universe)
        active_eligible = {
            "signal": etf_ids,
            "matched": etf_ids,
            "six_etf_basket": etf_ids,
        }
        for position in range(start + 1, end + 1):
            decision = self._decisions.get(sessions[position - 1])
            if decision is None:
                desired = {role: None for role in accounts}
            else:
                construction = decision.construction
                desired = {
                    "signal": self._target_map(construction.signal_weights),
                    "matched": self._target_map(construction.matched_weights),
                    "six_etf_basket": self._target_map(
                        construction.etf_basket_weights
                    ),
                }
                active_eligible = {
                    "signal": decision.mapped_member_ids | etf_ids,
                    "matched": decision.mapped_member_ids | etf_ids,
                    "six_etf_basket": etf_ids,
                }
            for role, account in accounts.items():
                self._advance_account(
                    account,
                    position,
                    desired[role],
                    active_eligible[role],
                )
        if len(accounts["signal"].accumulator.returns) != EXPECTED_RETURN_SESSION_COUNT:
            raise SixUniverseGateEvaluationError(
                "six-universe return-session geometry changed"
            )
        return accounts

    def _account_record(self, account):
        returns = account.accumulator.returns
        annual, volatility, sharpe = _risk_metrics(
            returns,
            annualization_sessions=self._profile.annualization_sessions,
        )
        count = Decimal(len(returns))
        with localcontext() as context:
            context.prec = 96
            average_daily_turnover = +(account.turnover_sum / count)
            annualized_turnover = +(
                average_daily_turnover * self._profile.annualization_sessions
            )
        path_sha = _sha(
            {
                "schema": "arv2-six-universe-equity-return-path-v1",
                "returns": [_decimal_text(item) for item in returns],
            }
        )
        mean_effective = (
            Decimal(0)
            if not account.target_effective_holdings
            else _stable_sum(account.target_effective_holdings)
            / Decimal(len(account.target_effective_holdings))
        )
        return {
            "schema": ACCOUNT_SCHEMA,
            "role": account.role,
            "cost_bps_per_side": PRIMARY_COST_BPS_PER_SIDE,
            "cumulative_return": _decimal_text(account.accumulator.wealth - Decimal(1)),
            "annualized_arithmetic_return": _decimal_text(annual),
            "annualized_volatility": (
                None if volatility is None else _decimal_text(volatility)
            ),
            "zero_rate_sharpe": None if sharpe is None else _decimal_text(sharpe),
            "maximum_drawdown": _decimal_text(account.accumulator.maximum_drawdown),
            "average_daily_two_sided_turnover": _decimal_text(
                average_daily_turnover
            ),
            "annualized_two_sided_turnover": _decimal_text(
                annualized_turnover
            ),
            "average_cash_weight": _decimal_text(account.cash_weight_sum / count),
            "mean_holding_count": _decimal_text(
                Decimal(account.holding_count_sum) / count
            ),
            "mean_target_effective_holdings": _decimal_text(mean_effective),
            "maximum_target_weight": _decimal_text(
                max(account.target_maximum_weights, default=Decimal(0))
            ),
            "return_session_count": len(returns),
            "invested_return_session_count": account.invested_return_session_count,
            "rebalance_count": account.rebalance_count,
            "full_target_count": account.full_target_count,
            "underfilled_target_count": account.underfilled_target_count,
            "locked_over_target_count": account.locked_over_target_count,
            "entry_price_refusal_count": account.entry_price_refusal_count,
            "stale_mark_session_count": account.stale_mark_session_count,
            "stale_position_deferral_count": account.stale_position_deferral_count,
            "eligibility_exit_zero_recovery_count": (
                account.eligibility_exit_zero_recovery_count
            ),
            "return_metric_conditioning": (
                "per_name_stale_mark_carry_and_eligibility_exit_zero_recovery"
            ),
            "equity_return_path_sha256": path_sha,
            "raw_price_rows_in_output": False,
            "raw_security_ids_in_output": False,
        }

    def _sleeve_diagnostics(self):
        records = []
        decisions = tuple(self._decisions.values())
        for index, spec in enumerate(_gate.UNIVERSE_SPECS):
            sleeves = tuple(item.construction.sleeves[index] for item in decisions)
            count = Decimal(len(sleeves))
            records.append(
                {
                    "universe_id": spec.universe_id,
                    "decision_count": len(sleeves),
                    "coverage_valid_count": sum(item.coverage.valid for item in sleeves),
                    "signal_full_etf_fallback_count": sum(
                        item.signal_etf_fallback_weight == item.budget for item in sleeves
                    ),
                    "signal_partial_etf_fallback_count": sum(
                        Decimal(0) < item.signal_etf_fallback_weight < item.budget
                        for item in sleeves
                    ),
                    "matched_full_etf_fallback_count": sum(
                        item.matched_etf_fallback_weight == item.budget for item in sleeves
                    ),
                    "mean_positive_score_count": _decimal_text(
                        Decimal(sum(item.positive_score_count for item in sleeves)) / count
                    ),
                    "mean_signal_stock_count": _decimal_text(
                        Decimal(sum(len(item.signal_security_ids) for item in sleeves)) / count
                    ),
                    "mean_matched_stock_count": _decimal_text(
                        Decimal(sum(len(item.matched_security_ids) for item in sleeves)) / count
                    ),
                    "minimum_mapping_ratio": _decimal_text(
                        min(item.coverage.mapping_ratio for item in sleeves)
                    ),
                    "minimum_cap_weight_coverage_ratio": _decimal_text(
                        min(item.coverage.cap_weight_coverage_ratio for item in sleeves)
                    ),
                }
            )
        return {"schema": SLEEVE_SCHEMA, "universes": records}

    def _series_bindings(self):
        records = []
        sessions = self._history_sessions
        for universe_id, security_id in self._etf_id_by_universe:
            raw = [
                [
                    session,
                    None
                    if (security_id, session) not in self._history_prices
                    else _decimal_text(self._history_prices[(security_id, session)]),
                ]
                for session in sessions
            ]
            prior = None
            returns = []
            observation_count = 0
            for session in sessions:
                current = self._history_prices.get((security_id, session))
                if current is not None:
                    observation_count += 1
                if prior is not None:
                    effective = prior if current is None else current
                    with localcontext() as context:
                        context.prec = 96
                        returns.append([session, _decimal_text(+(effective / prior - Decimal(1)))])
                    prior = effective
                elif current is not None:
                    prior = current
            records.append(
                {
                    "universe_id": universe_id,
                    "normalization_mode": "TOTAL_RETURN",
                    "observation": "session_open",
                    "expected_session_count": len(sessions),
                    "observation_count": observation_count,
                    "raw_observation_sha256": _sha(
                        {"schema": "arv2-six-universe-etf-raw-series-v1", "rows": raw}
                    ),
                    "used_return_path_sha256": _sha(
                        {"schema": "arv2-six-universe-etf-used-return-path-v1", "rows": returns}
                    ),
                }
            )
        return {"schema": SERIES_SCHEMA, "series": records}

    def _require_complete_etf_series(self):
        expected = set(self._history_sessions)
        for universe_id, security_id in self._etf_id_by_universe:
            observed = {
                session
                for candidate_id, session in self._history_prices
                if candidate_id == security_id and session in expected
            }
            if observed != expected:
                raise SixUniverseGateEvaluationError(
                    "six-universe "
                    + universe_id
                    + " ETF price series is incomplete"
                )

    @staticmethod
    def _require_invested_evidence(accounts):
        for role in ("signal", "matched"):
            if (
                accounts[role].invested_return_session_count
                < MINIMUM_INVESTED_RETURN_SESSIONS
            ):
                raise SixUniverseGateEvaluationError(
                    "six-universe "
                    + role
                    + " invested-session evidence is underfilled"
                )

    def _build_summary(self):
        self._require_complete_etf_series()
        accounts = self._simulate()
        self._require_invested_evidence(accounts)
        signal = self._account_record(accounts["signal"])
        matched = self._account_record(accounts["matched"])
        basket = self._account_record(accounts["six_etf_basket"])
        sleeves = self._sleeve_diagnostics()
        series = self._series_bindings()
        profile = self._profile.to_record()
        fragments = {
            "signal": signal,
            "matched": matched,
            "six_etf_basket": basket,
            "sleeves": sleeves,
            "series": series,
        }
        fragment_sha = _sha(
            {"schema": "arv2-six-universe-result-fragments-v1", **fragments}
        )
        meta = {
            "schema": SUMMARY_SCHEMA,
            "status": "PRELIMINARY_ACCEPTED_RISK_SIX_UNIVERSE_GATE_COMPLETED",
            "profile_id": profile["profile_id"],
            "profile_sha256": profile["profile_sha256"],
            "gate_profile_id": profile["gate_profile_id"],
            "gate_profile_sha256": profile["gate_profile_sha256"],
            "package_id": self._package_id,
            "package_sha256": self._package_sha256,
            "input_manifest_id": self._input.manifest_id,
            "input_manifest_sha256": self._input.manifest_sha256,
            "symbol_resolution_id": self._symbol_resolution_id,
            "symbol_resolution_sha256": self._symbol_resolution_sha256,
            "construction_path_sha256": self._construction_path_sha256,
            "result_fragments_sha256": fragment_sha,
            "decision_session_count": len(self._decisions),
            "price_history_batch_count": len(self._history_batches),
            "pit_history_call_count": self._pit_history_call_count,
            "pit_source_row_count": self._pit_source_row_count,
            "analyst_source_view": _gate.SOURCE_VIEW_ID,
            "point_in_time_etf_membership_and_market_cap": True,
            "point_in_time_analyst_archive": False,
            "current_vintage_identity_basis": True,
            "aggregate_only": True,
            "raw_rows_in_output": False,
            "orders": False,
            "deployment": False,
            "trading": False,
        }
        summary_sha = _sha({"profile": profile, "meta": meta, **fragments})
        meta = {
            **meta,
            "summary_id": "arv2-six-universe-summary-" + summary_sha[:24],
            "summary_sha256": summary_sha,
        }
        return {"profile": profile, "meta": meta, **fragments}

    def aggregate_summary(self):
        if self._phase is not EvaluationPhase.COMPLETED or self._summary is None:
            raise SixUniverseGateEvaluationError(
                "six-universe summary requested before completion"
            )
        return json.loads(_canonical(self._summary).decode("ascii"))

    def custom_summary_statistics(self):
        summary = self.aggregate_summary()
        output = {
            META_STATISTIC_NAME: _canonical(summary["meta"]).decode("ascii"),
            SIGNAL_STATISTIC_NAME: _canonical(summary["signal"]).decode("ascii"),
            MATCHED_STATISTIC_NAME: _canonical(summary["matched"]).decode("ascii"),
            ETF_BASKET_STATISTIC_NAME: _canonical(
                summary["six_etf_basket"]
            ).decode("ascii"),
            SLEEVES_STATISTIC_NAME: _canonical(summary["sleeves"]).decode("ascii"),
            SERIES_STATISTIC_NAME: _canonical(summary["series"]).decode("ascii"),
        }
        if (
            tuple(sorted(output))
            != expected_custom_summary_statistic_names(self._profile.profile_id)
            or any(
                len(name) > 64
                or len(value.encode("ascii")) > MAXIMUM_STATISTIC_BYTES
                for name, value in output.items()
            )
        ):
            raise SixUniverseGateEvaluationError(
                "six-universe aggregate transport exceeded its exact bound"
            )
        return dict(sorted(output.items()))


__all__ = (
    "ACCOUNT_SCHEMA",
    "ANNUALIZATION_SESSIONS",
    "DECISION_START_SESSION",
    "ETF_BASKET_STATISTIC_NAME",
    "EVALUATION_END_SESSION",
    "EXPECTED_DECISION_SESSION_COUNT",
    "EXPECTED_RETURN_SESSION_COUNT",
    "EXPECTED_SESSION_COUNT",
    "EvaluationPhase",
    "GATE_SCORE_QUANTUM",
    "MATCHED_STATISTIC_NAME",
    "META_STATISTIC_NAME",
    "MINIMUM_INVESTED_RETURN_SESSIONS",
    "MODELED_COST_RATE_PER_SIDE",
    "PRIMARY_COST_BPS_PER_SIDE",
    "PROFILE_IDS",
    "PROFILES",
    "PitDecisionSnapshot",
    "SERIES_STATISTIC_NAME",
    "SIGNAL_STATISTIC_NAME",
    "SLEEVES_STATISTIC_NAME",
    "SixUniverseEvaluationProfile",
    "SixUniverseGateEvaluationError",
    "SixUniverseGateEvaluationRuntime",
    "TOP10_PRIMARY_PROFILE",
    "TOP10_CAP95_EXPLORATORY_PROFILE",
    "TOP5_SENSITIVITY_PROFILE",
    "decision_sessions_for_input",
    "expected_custom_summary_statistic_names",
    "require_profile",
)
