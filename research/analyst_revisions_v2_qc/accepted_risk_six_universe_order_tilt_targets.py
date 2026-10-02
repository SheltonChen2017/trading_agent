"""Prospective cap-90 market-cap selection with a bounded revision tilt.

This module is outside the frozen R181/R182 source projection. A later v4
order runtime must supply the same-session, R055-enriched constituent snapshot
that produced its count-matched construction. This pure function only changes
the weights of stocks already selected by that construction.
"""

import dataclasses
import hashlib
import json
from decimal import Decimal, ROUND_DOWN, localcontext

try:
    import accepted_risk_sequential_r055_score as _score
    import accepted_risk_six_universe_gate as _gate
    import accepted_risk_six_universe_gate_evaluator as _evaluation
    import accepted_risk_six_universe_order_targets as _matched
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_sequential_r055_score as _score,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_gate as _gate,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_gate_evaluator as _evaluation,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_targets as _matched,
    )


class MatchedRevisionTiltError(ValueError):
    """The cap-90 construction or its bounded within-sleeve tilt was refused."""


TILT_ROLE = "matched_revision_tilt"
MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("0.20")
WEIGHT_TRANSFER_QUANTUM = Decimal("1e-30")
TILT_RANK_RULE_ID = "scored_tied_midrank_centered_v1"
DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt-decision-target-v4"
TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt-target-path-v4"


def _sha(value):
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MatchedRevisionTiltError(
            "matched revision tilt record is not canonical ASCII JSON"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _sum(values):
    return sum(values, Decimal(0))


def _transfer_capacity(baseline, rank_sign, scored_count):
    return (
        baseline
        * MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION
        * (Decimal(abs(rank_sign)) / Decimal(scored_count - 1))
    ).quantize(WEIGHT_TRANSFER_QUANTUM, rounding=ROUND_DOWN)


def tilt_matched_weights(construction, scored_snapshots):
    """Return R182's target with score-ranked, cap-aware sleeve transfers.

    The market-cap-selected stock IDs, own-ETF fallbacks, six sleeve budgets,
    total 98% gross, and 9.8% aggregate duplicate cap stay unchanged. Each
    stock's within-sleeve adjustment is bounded by 20% of its own post-cap
    baseline weight. Missing or exact-zero scores stay neutral; a tied-only
    sleeve is exact.
    """

    if (
        type(construction) is not _gate.SixUniverseConstruction
        or construction.profile is not _gate.TOP10_CAP90_EXPLORATORY_PROFILE
        or type(scored_snapshots) is not tuple
        or len(scored_snapshots) != len(_gate.UNIVERSE_IDS)
        or any(
            type(snapshot) is not _gate.UniverseSnapshot
            for snapshot in scored_snapshots
        )
    ):
        raise MatchedRevisionTiltError(
            "matched revision tilt requires exact cap-90 construction and snapshots"
        )
    unavailable = tuple(
        snapshot.universe_id
        for snapshot in scored_snapshots
        if not snapshot.constituents
    )
    # Rebuild the existing construction to bind the same point-in-time
    # members, selected identities, and fallback state. The v4 caller must
    # independently authenticate these scores against its R055 runtime.
    rebuilt = _gate.build_six_universe_construction(
        scored_snapshots,
        _gate.TOP10_CAP90_EXPLORATORY_PROFILE,
        unavailable_universe_ids=unavailable,
    )
    if (
        rebuilt.to_record()["construction_sha256"]
        != construction.to_record()["construction_sha256"]
    ):
        raise MatchedRevisionTiltError(
            "matched revision tilt construction and score snapshot differ"
        )
    stock_totals = {
        item.security_id: item.weight
        for item in construction.matched_weights
        if item.asset_kind == "stock"
    }
    if any(
        weight <= 0 or weight > _gate.DIRECT_STOCK_WEIGHT_CAP
        for weight in stock_totals.values()
    ):
        raise MatchedRevisionTiltError(
            "matched revision tilt baseline exceeds aggregate stock cap"
        )

    with localcontext() as context:
        context.prec = 96
        for sleeve, snapshot in zip(construction.sleeves, scored_snapshots):
            if (
                sleeve.universe_id != snapshot.universe_id
                or sleeve.etf_security_id != snapshot.etf_security_id
            ):
                raise MatchedRevisionTiltError(
                    "matched revision tilt sleeve identity changed"
                )
            baseline = dict(sleeve.matched_stock_weights)
            if len(baseline) != len(sleeve.matched_stock_weights):
                raise MatchedRevisionTiltError(
                    "matched revision tilt sleeve stock duplicated"
                )
            if len(baseline) < 2:
                continue
            row_by_id = {
                row.security_id: row
                for row in snapshot.constituents
                if row.security_id is not None
            }
            if any(security_id not in row_by_id for security_id in baseline):
                raise MatchedRevisionTiltError(
                    "matched revision tilt selected member is missing"
                )
            scored = []
            for security_id in baseline:
                score = row_by_id[security_id].firm_specific_score
                if score is None:
                    continue
                if type(score) is not Decimal or not score.is_finite():
                    raise MatchedRevisionTiltError(
                        "matched revision tilt score is not exact and finite"
                    )
                if score != 0:
                    scored.append((security_id, score))
            scored = tuple(scored)
            if len(scored) < 2 or len({score for _, score in scored}) < 2:
                continue

            # Twice the tied midrank is integral. Dividing its signed offset
            # from the center by m-1 gives the frozen [-1, 1] rank tilt:
            # r_i = 2 * (midrank_i - 1) / (m - 1) - 1. Near-median names
            # therefore have proportionally less transfer capacity.
            ascending = sorted(scored, key=lambda item: (item[1], item[0]))
            rank_sign = {}
            start = 0
            while start < len(ascending):
                end = start + 1
                while (
                    end < len(ascending)
                    and ascending[end][1] == ascending[start][1]
                ):
                    end += 1
                sign = start + end - len(ascending)
                for security_id, _ in ascending[start:end]:
                    rank_sign[security_id] = sign
                start = end
            receivers = sorted(
                (item for item in scored if rank_sign[item[0]] > 0),
                key=lambda item: (-item[1], item[0]),
            )
            donors = sorted(
                (item for item in scored if rank_sign[item[0]] < 0),
                key=lambda item: (item[1], item[0]),
            )
            updated = dict(baseline)
            for receiver_id, _ in receivers:
                room = min(
                    _transfer_capacity(
                        baseline[receiver_id],
                        rank_sign[receiver_id],
                        len(scored),
                    ),
                    _gate.DIRECT_STOCK_WEIGHT_CAP - stock_totals[receiver_id],
                )
                for donor_id, _ in donors:
                    available = (
                        _transfer_capacity(
                            baseline[donor_id],
                            rank_sign[donor_id],
                            len(scored),
                        )
                        - (baseline[donor_id] - updated[donor_id])
                    )
                    moved = min(room, available)
                    if moved <= 0:
                        continue
                    updated[receiver_id] += moved
                    updated[donor_id] -= moved
                    stock_totals[receiver_id] += moved
                    stock_totals[donor_id] -= moved
                    room -= moved
                    if room == 0:
                        break
            if (
                _sum(updated.values()) != _sum(baseline.values())
                or any(
                    weight < +(
                        baseline[security_id]
                        * (1 - MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION)
                    )
                    or weight > +(
                        baseline[security_id]
                        * (1 + MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION)
                    )
                    for security_id, weight in updated.items()
                )
            ):
                raise MatchedRevisionTiltError(
                    "matched revision tilt sleeve budget or weight band changed"
                )
        if any(
            weight <= 0 or weight > _gate.DIRECT_STOCK_WEIGHT_CAP
            for weight in stock_totals.values()
        ):
            raise MatchedRevisionTiltError(
                "matched revision tilt aggregate stock cap changed"
            )
        tilted = tuple(
            dataclasses.replace(
                item,
                weight=(
                    stock_totals[item.security_id]
                    if item.asset_kind == "stock" else item.weight
                ),
            )
            for item in construction.matched_weights
        )
        if _sum(item.weight for item in tilted) != _gate.TARGET_GROSS_EXPOSURE:
            raise MatchedRevisionTiltError(
                "matched revision tilt gross exposure changed"
            )
        return tilted


@dataclasses.dataclass(frozen=True, slots=True)
class TiltDecisionTarget:
    session: str
    role: str
    construction_id: str
    construction_sha256: str
    baseline_target_sha256: str
    target_weights: tuple[_gate.PortfolioWeight, ...]
    sleeves: tuple[_matched.SleeveOrderTargetDiagnostic, ...]
    target_sha256: str

    def _semantic(self):
        return {
            "schema": DECISION_TARGET_SCHEMA,
            "session": self.session,
            "role": self.role,
            "construction_id": self.construction_id,
            "construction_sha256": self.construction_sha256,
            "baseline_target_sha256": self.baseline_target_sha256,
            "tilt_rank_rule_id": TILT_RANK_RULE_ID,
            "maximum_stock_weight_change_fraction": "0.20",
            "weight_transfer_quantum": "0.000000000000000000000000000001",
            "target_weights": [item.to_record() for item in self.target_weights],
            "sleeves": [item.to_record() for item in self.sleeves],
        }

    def to_record(self):
        semantic = self._semantic()
        if _sha(semantic) != self.target_sha256:
            raise MatchedRevisionTiltError(
                "matched revision tilt decision target authority changed"
            )
        return {**semantic, "target_sha256": self.target_sha256}


@dataclasses.dataclass(frozen=True, slots=True)
class TiltTargetPath:
    role: str
    gate_profile_id: str
    gate_profile_sha256: str
    evaluation_profile_id: str
    evaluation_profile_sha256: str
    construction_path_sha256: str
    baseline_target_path_sha256: str
    decisions: tuple[TiltDecisionTarget, ...]
    target_path_sha256: str

    def _semantic(self):
        return {
            "schema": TARGET_PATH_SCHEMA,
            "role": self.role,
            "gate_profile_id": self.gate_profile_id,
            "gate_profile_sha256": self.gate_profile_sha256,
            "evaluation_profile_id": self.evaluation_profile_id,
            "evaluation_profile_sha256": self.evaluation_profile_sha256,
            "score_source_view_id": _gate.SOURCE_VIEW_ID,
            "score_arm_id": _gate.SCORE_ARM_ID,
            "score_quantum": _matched._decimal_text(
                _evaluation.GATE_SCORE_QUANTUM
            ),
            "construction_path_sha256": self.construction_path_sha256,
            "baseline_target_path_sha256": self.baseline_target_path_sha256,
            "decision_count": len(self.decisions),
            "decisions": [item.to_record() for item in self.decisions],
        }

    def to_record(self):
        semantic = self._semantic()
        if _sha(semantic) != self.target_path_sha256:
            raise MatchedRevisionTiltError(
                "matched revision tilt target path authority changed"
            )
        return {
            **semantic,
            "target_path_id": (
                "arv2-six-universe-order-tilt-target-path-"
                + self.target_path_sha256[:24]
            ),
            "target_path_sha256": self.target_path_sha256,
        }


class _ScoreCapture:
    """Capture the base builder's one authenticated R055 score advance."""

    def __init__(self, scorer):
        if type(scorer) is not _score.SequentialR055ScoreRuntime:
            raise MatchedRevisionTiltError(
                "matched revision tilt scorer type changed"
            )
        self._scorer = scorer
        self.latest = None
        self.call_count = 0

    def score_session(self, session):
        if self.latest is not None:
            raise MatchedRevisionTiltError(
                "matched revision tilt score was not consumed before advance"
            )
        result = self._scorer.score_session(session)
        if (
            type(result) is not _score.SequentialR055ScoreSnapshot
            or result.session != session
        ):
            raise MatchedRevisionTiltError(
                "matched revision tilt score session changed"
            )
        self.latest = result
        self.call_count += 1
        return result


class MatchedRevisionTiltTargetBuilder:
    """Wrap the exact cap-90 matched builder without a second score pass."""

    def __init__(self, value):
        self._matched = _matched.SixUniverseOrderTargetBuilder(
            value,
            role=_matched.ROLE_MATCHED,
            profile=_matched.ORDER_CAP90_EVALUATION_PROFILE,
        )
        self._capture = _ScoreCapture(self._matched._scorer)
        self._matched._scorer = self._capture
        self._decisions = []
        self._failed = False

    @property
    def role(self):
        return TILT_ROLE

    @property
    def next_required_session(self):
        return None if self._failed else self._matched.next_required_session

    @property
    def completed(self):
        return not self._failed and self._matched.completed

    @property
    def decisions(self):
        return tuple(self._decisions)

    def build(self, session, snapshot, *, unavailable_universe_ids=()):
        if self._failed:
            raise MatchedRevisionTiltError(
                "matched revision tilt builder is closed after failure"
            )
        if self._capture.latest is not None:
            self._failed = True
            raise MatchedRevisionTiltError(
                "matched revision tilt stale score was not consumed"
            )
        before = self._capture.call_count
        try:
            baseline = self._matched.build(
                session,
                snapshot,
                unavailable_universe_ids=unavailable_universe_ids,
            )
            score = self._capture.latest
            if (
                self._capture.call_count != before + 1
                or type(score) is not _score.SequentialR055ScoreSnapshot
                or score.session != session
            ):
                raise MatchedRevisionTiltError(
                    "matched revision tilt requires one same-session score"
                )
            self._capture.latest = None
            scored_snapshots = tuple(
                dataclasses.replace(
                    universe,
                    constituents=tuple(
                        dataclasses.replace(
                            row,
                            firm_specific_score=(
                                None
                                if row.security_id is None
                                else _evaluation._gate_score(
                                    score.primary_view_firm_specific_scores.get(
                                        row.security_id
                                    ),
                                    quantum=(
                                        _matched.ORDER_CAP90_EVALUATION_PROFILE
                                        .gate_score_quantum
                                    ),
                                )
                            ),
                        )
                        for row in universe.constituents
                    ),
                )
                for universe in snapshot.universes
            )
            construction = _gate.build_six_universe_construction(
                scored_snapshots,
                _gate.TOP10_CAP90_EXPLORATORY_PROFILE,
                unavailable_universe_ids=unavailable_universe_ids,
            )
            construction_record = construction.to_record()
            if (
                construction_record["construction_sha256"]
                != baseline.construction_sha256
                or tuple(sleeve.matched_security_ids for sleeve in construction.sleeves)
                != tuple(item.selected_security_ids for item in baseline.sleeves)
            ):
                raise MatchedRevisionTiltError(
                    "matched revision tilt construction differs from baseline"
                )
            weights = tilt_matched_weights(construction, scored_snapshots)
            provisional = TiltDecisionTarget(
                session=session,
                role=TILT_ROLE,
                construction_id=baseline.construction_id,
                construction_sha256=baseline.construction_sha256,
                baseline_target_sha256=baseline.target_sha256,
                target_weights=weights,
                sleeves=baseline.sleeves,
                target_sha256="",
            )
            result = dataclasses.replace(
                provisional,
                target_sha256=_sha(provisional._semantic()),
            )
            result.to_record()
        except Exception:
            self._failed = True
            raise
        self._decisions.append(result)
        return result

    def complete_path(self):
        if not self.completed:
            raise MatchedRevisionTiltError(
                "matched revision tilt target path requested before completion"
            )
        baseline = self._matched.complete_path()
        if (
            len(self._decisions) != len(baseline.decisions)
            or any(
                tilted.session != original.session
                or tilted.baseline_target_sha256 != original.target_sha256
                for tilted, original in zip(self._decisions, baseline.decisions)
            )
        ):
            raise MatchedRevisionTiltError(
                "matched revision tilt decision census changed"
            )
        provisional = TiltTargetPath(
            role=TILT_ROLE,
            gate_profile_id=baseline.gate_profile_id,
            gate_profile_sha256=baseline.gate_profile_sha256,
            evaluation_profile_id=baseline.evaluation_profile_id,
            evaluation_profile_sha256=baseline.evaluation_profile_sha256,
            construction_path_sha256=baseline.construction_path_sha256,
            baseline_target_path_sha256=baseline.target_path_sha256,
            decisions=tuple(self._decisions),
            target_path_sha256="",
        )
        result = dataclasses.replace(
            provisional,
            target_path_sha256=_sha(provisional._semantic()),
        )
        result.to_record()
        return result


__all__ = (
    "DECISION_TARGET_SCHEMA",
    "MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION",
    "WEIGHT_TRANSFER_QUANTUM",
    "MatchedRevisionTiltTargetBuilder",
    "MatchedRevisionTiltError",
    "TARGET_PATH_SCHEMA",
    "TILT_ROLE",
    "TILT_RANK_RULE_ID",
    "TiltDecisionTarget",
    "TiltTargetPath",
    "tilt_matched_weights",
)
