"""Pure order-target paths for the frozen six-universe top-ten gate.

This module deliberately stops before prices, quantities, orders, fees, or
QuantConnect.  It advances the already-reviewed sequential R055 score, enriches
exact point-in-time six-universe snapshots, and delegates all portfolio
construction to :mod:`accepted_risk_six_universe_gate` unchanged.  The result
is an immutable, hash-bound target path suitable for a later order runtime.
"""

import dataclasses
import hashlib
import json
from decimal import Decimal, localcontext

try:
    import accepted_risk_preliminary_rating_evaluator as _base
    import accepted_risk_sequential_r055_score as _score
    import accepted_risk_six_universe_gate as _gate
    import accepted_risk_six_universe_gate_evaluator as _evaluation
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
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_gate_evaluator as _evaluation,
    )


class SixUniverseOrderTargetsError(ValueError):
    """A target role, snapshot census, or immutable record was refused."""


ROLE_SIGNAL = "signal"
ROLE_MATCHED = "matched"
ROLE_SIX_ETF_BASKET = "six_etf_basket"
ROLES = (ROLE_SIGNAL, ROLE_MATCHED, ROLE_SIX_ETF_BASKET)

SLEEVE_DIAGNOSTIC_SCHEMA = "arv2-six-universe-order-sleeve-diagnostic-v1"
DECISION_TARGET_SCHEMA = "arv2-six-universe-order-decision-target-v1"
TARGET_PATH_SCHEMA = "arv2-six-universe-order-target-path-v1"
CONSTRUCTION_PATH_SCHEMA = "arv2-six-universe-construction-path-v1"

ORDER_GATE_PROFILE = _gate.TOP10_PRIMARY_PROFILE
ORDER_EVALUATION_PROFILE = _evaluation.TOP10_PRIMARY_PROFILE
ORDER_CAP90_GATE_PROFILE = _gate.TOP10_CAP90_EXPLORATORY_PROFILE
ORDER_CAP90_EVALUATION_PROFILE = _evaluation.TOP10_CAP90_EXPLORATORY_PROFILE


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SixUniverseOrderTargetsError(
            "six-universe order target is not canonical ASCII JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal_text(value: Decimal) -> str:
    if type(value) is not Decimal or not value.is_finite():
        raise SixUniverseOrderTargetsError(
            "six-universe order target Decimal is not exact and finite"
        )
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _sum(values) -> Decimal:
    with localcontext() as context:
        context.prec = 96
        total = Decimal(0)
        for value in values:
            total += value
        return +total


def _require_role(role: object) -> str:
    if type(role) is not str or role not in ROLES:
        raise SixUniverseOrderTargetsError(
            "six-universe order target role is not frozen"
        )
    return role


@dataclasses.dataclass(frozen=True, slots=True)
class SleeveOrderTargetDiagnostic:
    """Immutable fallback and post-cap detail for one frozen sleeve."""

    universe_id: str
    etf_ticker: str
    etf_security_id: str
    coverage_valid: bool
    coverage_refusal_reasons: tuple[str, ...]
    positive_score_count: int
    slot_count: int
    selected_security_ids: tuple[str, ...]
    post_cap_stock_target_count: int
    etf_target_weight: Decimal
    duplicate_cap_excess_weight: Decimal
    selection_status: str

    def to_record(self) -> dict[str, object]:
        return {
            "schema": SLEEVE_DIAGNOSTIC_SCHEMA,
            "universe_id": self.universe_id,
            "etf_ticker": self.etf_ticker,
            "etf_security_id": self.etf_security_id,
            "coverage_valid": self.coverage_valid,
            "coverage_refusal_reasons": list(self.coverage_refusal_reasons),
            "positive_score_count": self.positive_score_count,
            "slot_count": self.slot_count,
            "selected_security_ids": list(self.selected_security_ids),
            "post_cap_stock_target_count": self.post_cap_stock_target_count,
            "etf_target_weight": _decimal_text(self.etf_target_weight),
            "duplicate_cap_excess_weight": _decimal_text(
                self.duplicate_cap_excess_weight
            ),
            "selection_status": self.selection_status,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class SixUniverseOrderDecisionTarget:
    """One exact decision-session target map and its construction binding."""

    session: str
    role: str
    construction_id: str
    construction_sha256: str
    target_weights: tuple[_gate.PortfolioWeight, ...]
    sleeves: tuple[SleeveOrderTargetDiagnostic, ...]
    target_sha256: str

    def _semantic(self) -> dict[str, object]:
        return {
            "schema": DECISION_TARGET_SCHEMA,
            "session": self.session,
            "role": self.role,
            "construction_id": self.construction_id,
            "construction_sha256": self.construction_sha256,
            "target_weights": [item.to_record() for item in self.target_weights],
            "sleeves": [item.to_record() for item in self.sleeves],
        }

    def to_record(self) -> dict[str, object]:
        semantic = self._semantic()
        if _sha(semantic) != self.target_sha256:
            raise SixUniverseOrderTargetsError(
                "six-universe order decision target authority changed"
            )
        return {**semantic, "target_sha256": self.target_sha256}


@dataclasses.dataclass(frozen=True, slots=True)
class SixUniverseOrderTargetPath:
    """All top-ten decision targets for exactly one frozen account role."""

    role: str
    gate_profile_id: str
    gate_profile_sha256: str
    evaluation_profile_id: str
    evaluation_profile_sha256: str
    construction_path_sha256: str
    decisions: tuple[SixUniverseOrderDecisionTarget, ...]
    target_path_sha256: str

    def _semantic(self) -> dict[str, object]:
        return {
            "schema": TARGET_PATH_SCHEMA,
            "role": self.role,
            "gate_profile_id": self.gate_profile_id,
            "gate_profile_sha256": self.gate_profile_sha256,
            "evaluation_profile_id": self.evaluation_profile_id,
            "evaluation_profile_sha256": self.evaluation_profile_sha256,
            "score_source_view_id": _gate.SOURCE_VIEW_ID,
            "score_arm_id": _gate.SCORE_ARM_ID,
            "score_quantum": _decimal_text(
                ORDER_EVALUATION_PROFILE.gate_score_quantum
            ),
            "construction_path_sha256": self.construction_path_sha256,
            "decision_count": len(self.decisions),
            "decisions": [item.to_record() for item in self.decisions],
        }

    def to_record(self) -> dict[str, object]:
        semantic = self._semantic()
        if _sha(semantic) != self.target_path_sha256:
            raise SixUniverseOrderTargetsError(
                "six-universe order target path authority changed"
            )
        return {
            **semantic,
            "target_path_id": (
                "arv2-six-universe-order-target-path-"
                + self.target_path_sha256[:24]
            ),
            "target_path_sha256": self.target_path_sha256,
        }


def _role_weights(construction, role):
    if role == ROLE_SIGNAL:
        return construction.signal_weights
    if role == ROLE_MATCHED:
        return construction.matched_weights
    if role == ROLE_SIX_ETF_BASKET:
        return construction.etf_basket_weights
    raise SixUniverseOrderTargetsError(
        "six-universe order target role is not frozen"
    )


def _sleeve_diagnostic(sleeve, role, gate_profile):
    if role == ROLE_SIGNAL:
        selected_ids = sleeve.signal_security_ids
        stock_weights = sleeve.signal_stock_weights
        etf_weight = sleeve.signal_etf_fallback_weight
    elif role == ROLE_MATCHED:
        selected_ids = sleeve.matched_security_ids
        stock_weights = sleeve.matched_stock_weights
        etf_weight = sleeve.matched_etf_fallback_weight
    elif role == ROLE_SIX_ETF_BASKET:
        selected_ids = ()
        stock_weights = ()
        etf_weight = sleeve.budget
    else:
        raise SixUniverseOrderTargetsError(
            "six-universe order target role is not frozen"
        )

    with localcontext() as context:
        context.prec = 96
        slot_weight = +(sleeve.budget / Decimal(gate_profile.slot_count))
        ordinary_fallback = +(
            sleeve.budget - slot_weight * Decimal(len(selected_ids))
        )
        duplicate_excess = +(etf_weight - ordinary_fallback)
    if duplicate_excess < 0:
        raise SixUniverseOrderTargetsError(
            "six-universe order sleeve fallback is inconsistent"
        )

    if role == ROLE_SIX_ETF_BASKET:
        status = "SIX_ETF_BASKET"
    elif not sleeve.coverage.valid:
        status = "COVERAGE_FALLBACK"
    elif sleeve.positive_score_count < _gate.MINIMUM_POSITIVE_SCORE_COUNT:
        status = "POSITIVE_SCORE_FLOOR_FALLBACK"
    elif duplicate_excess > 0:
        status = "DUPLICATE_CAP_ETF_FALLBACK"
    elif len(selected_ids) < gate_profile.slot_count:
        status = "PARTIAL_STOCK_SLOTS_WITH_ETF_FALLBACK"
    else:
        status = "FULL_STOCK_SLOTS"

    return SleeveOrderTargetDiagnostic(
        universe_id=sleeve.universe_id,
        etf_ticker=sleeve.etf_ticker,
        etf_security_id=sleeve.etf_security_id,
        coverage_valid=sleeve.coverage.valid,
        coverage_refusal_reasons=tuple(sleeve.coverage.refusal_reasons),
        positive_score_count=sleeve.positive_score_count,
        slot_count=gate_profile.slot_count,
        selected_security_ids=tuple(selected_ids),
        post_cap_stock_target_count=len(stock_weights),
        etf_target_weight=etf_weight,
        duplicate_cap_excess_weight=duplicate_excess,
        selection_status=status,
    )


def _decision_target(session, role, construction, gate_profile):
    construction_record = construction.to_record()
    weights = tuple(_role_weights(construction, role))
    if (
        not weights
        or any(type(item) is not _gate.PortfolioWeight for item in weights)
        or len({item.security_id for item in weights}) != len(weights)
        or _sum(item.weight for item in weights) != _gate.TARGET_GROSS_EXPOSURE
    ):
        raise SixUniverseOrderTargetsError(
            "six-universe order target map changed"
        )
    sleeves = tuple(
        _sleeve_diagnostic(sleeve, role, gate_profile)
        for sleeve in construction.sleeves
    )
    seed = {
        "schema": DECISION_TARGET_SCHEMA,
        "session": session,
        "role": role,
        "construction_id": construction_record["construction_id"],
        "construction_sha256": construction_record["construction_sha256"],
        "target_weights": [item.to_record() for item in weights],
        "sleeves": [item.to_record() for item in sleeves],
    }
    result = SixUniverseOrderDecisionTarget(
        session=session,
        role=role,
        construction_id=construction_record["construction_id"],
        construction_sha256=construction_record["construction_sha256"],
        target_weights=weights,
        sleeves=sleeves,
        target_sha256=_sha(seed),
    )
    result.to_record()
    return result


class SixUniverseOrderTargetBuilder:
    """Advance the frozen score and build one decision target at a time.

    The builder accepts only the next frozen weekly session.  It therefore
    needs no future point-in-time snapshot and can be held by an event-driven
    order runtime.  Any failed build closes the instance because its sequential
    score state may already have advanced.
    """

    def __init__(
        self,
        value,
        *,
        profile=ORDER_EVALUATION_PROFILE,
        role,
    ):
        if type(value) is not _base.PreliminaryRatingInput:
            raise SixUniverseOrderTargetsError(
                "six-universe order targets require exact preliminary input"
            )
        if profile is ORDER_EVALUATION_PROFILE:
            expected_gate_profile = ORDER_GATE_PROFILE
        elif profile is ORDER_CAP90_EVALUATION_PROFILE:
            expected_gate_profile = ORDER_CAP90_GATE_PROFILE
        elif profile is _evaluation.TOP5_SENSITIVITY_PROFILE:
            raise SixUniverseOrderTargetsError(
                "six-universe order target profile is not frozen top-ten"
            )
        else:
            raise SixUniverseOrderTargetsError(
                "six-universe order target profile is not an approved top-ten order profile"
            )
        profile.to_record()
        if (
            profile.gate_profile is not expected_gate_profile
            or profile.gate_score_quantum
            != ORDER_EVALUATION_PROFILE.gate_score_quantum
        ):
            raise SixUniverseOrderTargetsError(
                "six-universe order target profile binding changed"
            )
        self._role = _require_role(role)
        self._profile = profile
        self._sessions = _evaluation.decision_sessions_for_input(value)
        start_position = value.session_axis.index(
            _evaluation.DECISION_START_SESSION
        )
        self._scorer = _score.SequentialR055ScoreRuntime(
            value,
            start_position=start_position,
        )
        self._next_index = 0
        self._etf_identity = None
        self._decisions = []
        self._construction_records = []
        self._failed = False

    @property
    def role(self):
        return self._role

    @property
    def next_required_session(self):
        if self._failed or self._next_index == len(self._sessions):
            return None
        return self._sessions[self._next_index]

    @property
    def completed(self):
        return not self._failed and self._next_index == len(self._sessions)

    @property
    def decisions(self):
        return tuple(self._decisions)

    def build(self, session, snapshot):
        """Build the next target from exactly one contemporaneous snapshot."""

        if self._failed:
            raise SixUniverseOrderTargetsError(
                "six-universe order target builder is closed after failure"
            )
        if self.completed:
            raise SixUniverseOrderTargetsError(
                "six-universe order target schedule is already complete"
            )
        expected = self._sessions[self._next_index]
        if (
            type(session) is not str
            or session != expected
            or type(snapshot) is not _evaluation.PitDecisionSnapshot
            or snapshot.session != session
        ):
            raise SixUniverseOrderTargetsError(
                "six-universe order target session is not the exact next session"
            )
        try:
            score = self._scorer.score_session(session)
            enriched = []
            for universe in snapshot.universes:
                rows = []
                for row in universe.constituents:
                    if row.firm_specific_score is not None:
                        raise SixUniverseOrderTargetsError(
                            "PIT snapshot attempted to inject an R055 score"
                        )
                    rows.append(
                        dataclasses.replace(
                            row,
                            firm_specific_score=(
                                None
                                if row.security_id is None
                                else _evaluation._gate_score(
                                    score.primary_view_firm_specific_scores.get(
                                        row.security_id
                                    ),
                                    quantum=self._profile.gate_score_quantum,
                                )
                            ),
                        )
                    )
                enriched.append(
                    dataclasses.replace(universe, constituents=tuple(rows))
                )
            construction = _gate.build_six_universe_construction(
                tuple(enriched), self._profile.gate_profile
            )
            current_etfs = tuple(
                (sleeve.universe_id, sleeve.etf_security_id)
                for sleeve in construction.sleeves
            )
            if self._etf_identity is None:
                self._etf_identity = current_etfs
            elif current_etfs != self._etf_identity:
                raise SixUniverseOrderTargetsError(
                    "six-universe order ETF security identity changed through time"
                )
            construction_record = construction.to_record()
            result = _decision_target(
                session, self._role, construction, self._profile.gate_profile
            )
        except Exception:
            self._failed = True
            raise
        self._construction_records.append([session, construction_record])
        self._decisions.append(result)
        self._next_index += 1
        return result

    def complete_path(self):
        """Return the immutable path only after the exact census is complete."""

        if not self.completed:
            raise SixUniverseOrderTargetsError(
                "six-universe order target path requested before completion"
            )
        construction_path_sha256 = _sha(
            {
                "schema": CONSTRUCTION_PATH_SCHEMA,
                "records": self._construction_records,
            }
        )
        evaluation_record = self._profile.to_record()
        provisional = SixUniverseOrderTargetPath(
            role=self._role,
            gate_profile_id=self._profile.gate_profile.profile_id,
            gate_profile_sha256=self._profile.gate_profile.profile_sha256,
            evaluation_profile_id=self._profile.profile_id,
            evaluation_profile_sha256=self._profile.profile_sha256,
            construction_path_sha256=construction_path_sha256,
            decisions=tuple(self._decisions),
            target_path_sha256="",
        )
        result = dataclasses.replace(
            provisional,
            target_path_sha256=_sha(provisional._semantic()),
        )
        if (
            evaluation_record["gate_profile_id"] != result.gate_profile_id
            or evaluation_record["gate_profile_sha256"]
            != result.gate_profile_sha256
        ):
            raise SixUniverseOrderTargetsError(
                "six-universe order profile authority changed"
            )
        result.to_record()
        return result


def build_six_universe_order_target_path(
    value,
    decision_snapshots,
    *,
    role,
    profile=ORDER_EVALUATION_PROFILE,
):
    """Build one explicitly selected, approved top-ten target path."""

    if type(decision_snapshots) is not tuple:
        raise SixUniverseOrderTargetsError(
            "six-universe order target snapshot census changed"
        )
    builder = SixUniverseOrderTargetBuilder(value, role=role, profile=profile)
    if (
        len(decision_snapshots) != len(builder._sessions)
        or any(
            type(item) is not _evaluation.PitDecisionSnapshot
            for item in decision_snapshots
        )
        or tuple(item.session for item in decision_snapshots)
        != builder._sessions
    ):
        raise SixUniverseOrderTargetsError(
            "six-universe order target snapshot census changed"
        )
    for item in decision_snapshots:
        builder.build(item.session, item)
    return builder.complete_path()


__all__ = (
    "DECISION_TARGET_SCHEMA",
    "ORDER_CAP90_EVALUATION_PROFILE",
    "ORDER_CAP90_GATE_PROFILE",
    "ORDER_EVALUATION_PROFILE",
    "ORDER_GATE_PROFILE",
    "ROLE_MATCHED",
    "ROLE_SIGNAL",
    "ROLE_SIX_ETF_BASKET",
    "ROLES",
    "SLEEVE_DIAGNOSTIC_SCHEMA",
    "SixUniverseOrderDecisionTarget",
    "SixUniverseOrderTargetBuilder",
    "SixUniverseOrderTargetPath",
    "SixUniverseOrderTargetsError",
    "SleeveOrderTargetDiagnostic",
    "TARGET_PATH_SCHEMA",
    "build_six_universe_order_target_path",
)
