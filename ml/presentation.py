"""ML-LR-8 section 14.1: the read-only presentation surface.

This is the first milestone that puts model output in front of a person, so
the failure mode changes shape. Every earlier milestone could be wrong by
producing a bad number. This one can be wrong by producing an *accurate*
number that reads as more than it is.

Three rules follow from that, and each is a refusal rather than a
best-effort:

  1. NOTHING IS RECONSTRUCTED. A shadow prediction today records an
     estimate and both frozen baselines, but no prospective interval and no
     calibrated probability -- its `uncertainty` says
     "refer_to_frozen_evaluation_report". An interval could be derived from
     realized outcomes and a probability from the evaluation report, and
     both would be RETROSPECTIVE quantities displayed beside a prospective
     estimate. They are reported unavailable until a future model version
     records them prospectively.

  2. THE LATEST ATTEMPT IS THE ANSWER. If the most recent attempt for a
     subject refused, the display shows that refusal. Falling back to an
     older available prediction would show a stale number as if it were
     current -- the single most misleading thing this surface could do.

  3. ABSENCE IS A BLOCKER, NOT A PASS. No monitoring report means
     monitoring evidence is unavailable and a blocker is added, because an
     empty blocker list reads as "nothing wrong".

Pure by construction: no storage, no broker, no model loading. The caller
supplies already-loaded records, which is what keeps this testable and what
keeps `assistant/` free of any `ml` import.
"""
from __future__ import annotations

import dataclasses
import math
import re
from typing import Any, Mapping, Sequence

from ml.hashing import HashingError, hash_payload

# Plan 14.1's required label, reproduced exactly. Any change to this string
# is a change to what the user is told, so it lives in one place and is
# asserted verbatim by tests.
EXPERIMENTAL_LABEL = (
    "Experimental model observation — not a recommendation and not used by "
    "the execution gate."
)

UNAVAILABLE = "unavailable"
NOT_MEASURED = "not_measured"

# Keys that would make an observation read as an instruction. Checked on the
# SERIALIZED payload so one nested inside a sub-object is caught too.
_ACTION_SHAPED_KEYS = frozenset(
    {
        "side", "shares", "quantity", "order_type", "limit_price", "stop_price",
        "approved", "approval", "authorization", "execute", "recommendation",
        "recommended", "target_weight", "target_weights", "trade_intent",
        "action", "buy", "sell", "signal",
    }
)


class PresentationError(ValueError):
    """Records cannot support an honest read-only presentation."""


def assert_no_action_shaped_keys(payload: Any, *, path: str = "observation") -> None:
    """Reject any key that could be read as a trade instruction."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(key)).strip("_").lower()
            if normalized in _ACTION_SHAPED_KEYS:
                raise PresentationError(
                    f"{path}.{key} is an action-shaped field; this surface displays "
                    "observations and must never read as an instruction"
                )
            assert_no_action_shaped_keys(value, path=f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_no_action_shaped_keys(value, path=f"{path}[{index}]")


def verify_monitoring_report(
    report: Mapping[str, Any] | None, *, expected_epoch: str
) -> dict[str, Any]:
    """Verify a monitoring report's own hash and epoch before trusting it.

    Returns a status record rather than raising, so a rejected report is
    DISPLAYED as rejected instead of vanishing. A silently dropped report
    and a clean one look identical to a reader, and only one of them is
    safe.
    """
    if report is None:
        return {
            "status": UNAVAILABLE,
            "reason": "no monitoring report was supplied",
            "report_hash": None,
            "evidence_epoch": None,
            "promotion_blockers": [],
        }
    if not isinstance(report, Mapping):
        return {
            "status": "rejected",
            "reason": "monitoring report is not a JSON object",
            "report_hash": None,
            "evidence_epoch": None,
            "promotion_blockers": [],
        }

    recorded = report.get("report_hash")
    material = {k: v for k, v in report.items() if k != "report_hash"}
    try:
        # A supplied report is untrusted input. hash_payload rejects NaN,
        # infinity, and non-JSON types, so an unhashable report is a report
        # that cannot be verified -- which is a rejection, not a crash.
        actual = hash_payload(material)
    except HashingError as exc:
        return {
            "status": "rejected",
            "reason": f"monitoring report is not canonically hashable: {exc}",
            "report_hash": recorded if isinstance(recorded, str) else None,
            "evidence_epoch": report.get("evidence_epoch"),
            "promotion_blockers": [],
        }
    if not isinstance(recorded, str) or recorded != actual:
        return {
            "status": "rejected",
            "reason": (
                f"monitoring report hash mismatch: records {recorded!r}, content "
                f"hashes to {actual!r}"
            ),
            "report_hash": recorded if isinstance(recorded, str) else None,
            "evidence_epoch": report.get("evidence_epoch"),
            "promotion_blockers": [],
        }

    epoch = report.get("evidence_epoch")
    if epoch != expected_epoch:
        return {
            "status": "rejected",
            "reason": (
                f"monitoring report belongs to evidence epoch {epoch!r}, not the "
                f"displayed epoch {expected_epoch!r}"
            ),
            "report_hash": recorded,
            "evidence_epoch": epoch,
            "promotion_blockers": [],
        }

    if report.get("schema_version") != "1.0":
        return {
            "status": "rejected",
            "reason": "monitoring report schema_version is not supported",
            "report_hash": recorded,
            "evidence_epoch": epoch,
            "promotion_blockers": [],
        }
    if report.get("production_authoritative") is not False:
        return {
            "status": "rejected",
            "reason": "monitoring report must be production_authoritative=false",
            "report_hash": recorded,
            "evidence_epoch": epoch,
            "promotion_blockers": [],
        }

    blockers = report.get("promotion_blockers")
    if not isinstance(blockers, (list, tuple)):
        return {
            "status": "rejected",
            "reason": "monitoring report promotion_blockers is not a list",
            "report_hash": recorded,
            "evidence_epoch": epoch,
            "promotion_blockers": [],
        }
    if any(not isinstance(item, str) or not item.strip() for item in blockers):
        return {
            "status": "rejected",
            "reason": "monitoring report promotion_blockers must be non-empty strings",
            "report_hash": recorded,
            "evidence_epoch": epoch,
            "promotion_blockers": [],
        }
    conclusions_supported = report.get("conclusions_supported")
    if (
        not isinstance(conclusions_supported, bool)
        or conclusions_supported != (len(blockers) == 0)
    ):
        return {
            "status": "rejected",
            "reason": (
                "monitoring report conclusions_supported is inconsistent with "
                "promotion_blockers"
            ),
            "report_hash": recorded,
            "evidence_epoch": epoch,
            "promotion_blockers": [],
        }
    return {
        "status": "verified",
        "reason": None,
        "report_hash": recorded,
        "evidence_epoch": epoch,
        # Surfaced verbatim. Reinterpreting, filtering, or softening a
        # blocker here would let the presentation layer overrule the
        # monitoring layer that computed it.
        "promotion_blockers": list(blockers),
    }


def latest_attempt_by_subject(
    predictions: Sequence[Mapping[str, Any]], *, evidence_epoch: str
) -> dict[str, Mapping[str, Any]]:
    """The most recent attempt per subject WITHIN one epoch.

    Scoped to a single epoch by construction: pooling attempts from a closed
    and an active epoch would present two different systems as one.

    "Most recent" is by `as_of_session` then `generated_at`, and an
    unavailable attempt competes on equal terms -- a refusal that supersedes
    an older success is the current state of the model.
    """
    scoped = [
        row for row in predictions if row.get("evidence_epoch") == evidence_epoch
    ]
    latest: dict[str, Mapping[str, Any]] = {}
    for row in scoped:
        subject = str(row.get("subject_key", ""))
        if not subject:
            continue
        current = latest.get(subject)
        key = (str(row.get("as_of_session", "")), str(row.get("generated_at", "")))
        if current is None:
            latest[subject] = row
            continue
        current_key = (
            str(current.get("as_of_session", "")),
            str(current.get("generated_at", "")),
        )
        if key > current_key:
            latest[subject] = row
    return latest


def _finite_nonnegative_value(values: Mapping[str, Any], name: str) -> float | None:
    value = values.get(name)
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise PresentationError(f"prediction value {name!r} must be finite and non-negative")
    return float(value)


def _verify_prediction_row(prediction: Mapping[str, Any]) -> Mapping[str, Any]:
    """Verify the immutable payload and its duplicated indexed identity.

    SQLite index columns make status queries efficient, but the content hash
    covers the serialized prediction.  Both representations must agree before
    a number is shown to a person.
    """
    payload = prediction.get("prediction")
    if not isinstance(payload, Mapping):
        raise PresentationError("prediction row is missing its serialized payload")
    recorded_hash = prediction.get("prediction_hash")
    if not isinstance(recorded_hash, str):
        raise PresentationError("prediction row is missing its immutable content hash")
    try:
        actual_hash = hash_payload(payload)
    except HashingError as exc:
        raise PresentationError(f"prediction payload is not canonically hashable: {exc}") from exc
    if recorded_hash != actual_hash:
        raise PresentationError(
            f"prediction content hash mismatch: records {recorded_hash!r}, "
            f"content hashes to {actual_hash!r}"
        )

    for name in (
        "prediction_id",
        "model_key",
        "task",
        "subject_key",
        "as_of_session",
        "generated_at",
        "horizon_sessions",
        "available",
        "evidence_epoch",
        "shadow_run_id",
    ):
        if payload.get(name) != prediction.get(name):
            raise PresentationError(
                f"prediction indexed field {name!r} does not match its hashed payload"
            )
    if list(payload.get("refusal_reasons") or ()) != list(
        prediction.get("refusal_reasons") or ()
    ):
        raise PresentationError(
            "prediction indexed refusal_reasons do not match its hashed payload"
        )
    if payload.get("production_authoritative") is not False:
        raise PresentationError("prediction must be production_authoritative=false")
    return payload


def _unavailable_observation(
    *,
    task: str,
    model_key: str,
    evidence_epoch: str,
    subject: str,
    reason: str,
) -> dict[str, Any]:
    model_id, separator, model_version = model_key.rpartition(":")
    if not separator:
        model_id, model_version = model_key, ""
    return {
        "task": task,
        "model_id": model_id,
        "model_version": model_version,
        "evidence_epoch": evidence_epoch,
        "subject_key": subject,
        "as_of_session": None,
        "horizon_sessions": None,
        "available": False,
        "estimate_daily_volatility_pct": None,
        "estimate_annualized_volatility_pct": None,
        "prediction_interval": UNAVAILABLE,
        "prediction_interval_reason": "no verified prospective prediction is available",
        "threshold_probability": UNAVAILABLE,
        "calibration_status": NOT_MEASURED,
        "trailing_baseline_daily_pct": None,
        "ewma_baseline_daily_pct": None,
        "feature_freshness": {},
        "refusal_reasons": [reason],
        "evidence_status": UNAVAILABLE,
        "production_authoritative": False,
        "label": EXPERIMENTAL_LABEL,
    }


@dataclasses.dataclass(frozen=True)
class ModelObservation:
    """One subject's latest attempt, presented honestly."""

    task: str
    model_id: str
    model_version: str
    evidence_epoch: str
    subject_key: str
    as_of_session: str
    horizon_sessions: int
    available: bool
    estimate_daily_volatility_pct: float | None
    estimate_annualized_volatility_pct: float | None
    prediction_interval: str
    prediction_interval_reason: str
    threshold_probability: str
    calibration_status: str
    trailing_baseline_daily_pct: float | None
    ewma_baseline_daily_pct: float | None
    feature_freshness: Mapping[str, Any]
    refusal_reasons: tuple[str, ...]
    evidence_status: str

    @property
    def production_authoritative(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "task": self.task,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "evidence_epoch": self.evidence_epoch,
            "subject_key": self.subject_key,
            "as_of_session": self.as_of_session,
            "horizon_sessions": self.horizon_sessions,
            "available": self.available,
            "estimate_daily_volatility_pct": self.estimate_daily_volatility_pct,
            "estimate_annualized_volatility_pct": self.estimate_annualized_volatility_pct,
            "prediction_interval": self.prediction_interval,
            "prediction_interval_reason": self.prediction_interval_reason,
            # Deliberately NOT named "confidence". The value is a status
            # string, never a number, until a model version records a
            # prospectively calibrated probability.
            "threshold_probability": self.threshold_probability,
            "calibration_status": self.calibration_status,
            "trailing_baseline_daily_pct": self.trailing_baseline_daily_pct,
            "ewma_baseline_daily_pct": self.ewma_baseline_daily_pct,
            "feature_freshness": dict(self.feature_freshness),
            "refusal_reasons": list(self.refusal_reasons),
            "evidence_status": self.evidence_status,
            "production_authoritative": self.production_authoritative,
            "label": EXPERIMENTAL_LABEL,
        }
        assert_no_action_shaped_keys(payload)
        return payload


def build_observation(
    prediction: Mapping[str, Any], *, evidence_epoch: str
) -> ModelObservation:
    """Present one stored attempt without inventing anything it lacks."""
    payload = _verify_prediction_row(prediction)
    if prediction.get("evidence_epoch") != evidence_epoch:
        raise PresentationError(
            "refusing to present a prediction from a different evidence epoch"
        )

    available = bool(prediction.get("available"))
    values = payload.get("values") if isinstance(payload.get("values"), Mapping) else {}
    uncertainty = (
        payload.get("uncertainty")
        if isinstance(payload.get("uncertainty"), Mapping)
        else {}
    )

    # An interval is shown only if the prediction PROSPECTIVELY recorded one.
    # `refer_to_frozen_evaluation_report` is not an interval; deriving one
    # from the report would be a retrospective quantity beside a prospective
    # estimate.
    interval = uncertainty.get("prediction_interval_daily_pct")
    if available and isinstance(interval, (list, tuple)) and len(interval) == 2:
        if any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in interval
        ):
            raise PresentationError("prediction interval bounds must be finite numbers")
        lower, upper = float(interval[0]), float(interval[1])
        if lower < 0 or upper < lower:
            raise PresentationError(
                "prediction interval must be non-negative and ordered lower-to-upper"
            )
        interval_text = f"[{lower:.6f}, {upper:.6f}]"
        interval_reason = "recorded prospectively by the model"
    else:
        interval_text = UNAVAILABLE
        interval_reason = (
            "this model version does not record a prospective prediction interval; "
            "it is not reconstructed from realized outcomes or the evaluation report"
        )

    probability = uncertainty.get(
        "threshold_probability", uncertainty.get("probability_above_ceiling")
    )
    probability_label = uncertainty.get(
        "threshold_probability_label",
        "calibrated_probability"
        if "probability_above_ceiling" in uncertainty
        else None,
    )
    calibration_value = uncertainty.get("calibration_status")
    calibration = (
        calibration_value
        if isinstance(calibration_value, str) and calibration_value.strip()
        else NOT_MEASURED
    )
    if probability is not None and (
        isinstance(probability, bool)
        or not isinstance(probability, (int, float))
        or not math.isfinite(float(probability))
        or not 0 <= float(probability) <= 1
    ):
        raise PresentationError("threshold probability must be a finite value in [0, 1]")
    if (
        available
        and probability is not None
        and probability_label == "calibrated_probability"
        and calibration in {"calibrated", "calibrated_prospectively"}
    ):
        probability_text = f"{float(probability):.6f}"
    else:
        probability_text = UNAVAILABLE

    return ModelObservation(
        task=str(payload.get("task", prediction.get("task", ""))),
        model_id=str(payload.get("model_id", "")),
        model_version=str(payload.get("model_version", "")),
        evidence_epoch=evidence_epoch,
        subject_key=str(prediction.get("subject_key", "")),
        as_of_session=str(prediction.get("as_of_session", "")),
        horizon_sessions=int(prediction.get("horizon_sessions", 0) or 0),
        available=available,
        estimate_daily_volatility_pct=(
            _finite_nonnegative_value(values, "daily_volatility_pct")
            if available
            else None
        ),
        estimate_annualized_volatility_pct=(
            _finite_nonnegative_value(values, "annualized_volatility_pct")
            if available
            else None
        ),
        prediction_interval=interval_text,
        prediction_interval_reason=interval_reason,
        threshold_probability=probability_text,
        calibration_status=calibration,
        trailing_baseline_daily_pct=(
            _finite_nonnegative_value(values, "trailing_baseline_daily_pct")
            if available
            else None
        ),
        ewma_baseline_daily_pct=(
            _finite_nonnegative_value(values, "ewma_baseline_daily_pct")
            if available
            else None
        ),
        feature_freshness=(
            payload.get("feature_freshness")
            if isinstance(payload.get("feature_freshness"), Mapping)
            else {}
        ),
        refusal_reasons=tuple(
            str(item) for item in (prediction.get("refusal_reasons") or ())
        ),
        evidence_status=str(payload.get("evidence_status", "")),
    )


def build_presentation(
    *,
    task: str,
    model_key: str,
    evidence_epoch: str | None,
    epoch_status: str | None,
    predictions: Sequence[Mapping[str, Any]],
    monitoring_report: Mapping[str, Any] | None,
    subjects: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Assemble the full read-only surface for one evidence epoch.

    `subjects`, when supplied, restricts the display; otherwise every
    configured subject with an attempt in this epoch is shown. Plan 14.1
    forbids arbitrarily picking one, because the reader would have no way to
    know which.
    """
    blockers: list[str] = []

    if evidence_epoch is None:
        return {
            "presentation_available": False,
            "reason": (
                "no active evidence epoch for this model and task; a closed epoch "
                "is not shown implicitly"
            ),
            "task": task,
            "model_key": model_key,
            "evidence_epoch": None,
            "observations": [],
            "monitoring": verify_monitoring_report(None, expected_epoch=""),
            "promotion_blockers": ["no_active_evidence_epoch"],
            "production_authoritative": False,
            "label": EXPERIMENTAL_LABEL,
        }

    monitoring = verify_monitoring_report(
        monitoring_report, expected_epoch=evidence_epoch
    )
    if monitoring["status"] == UNAVAILABLE:
        # Absence is not a pass. An empty blocker list reads as "nothing
        # wrong", which is the opposite of what no evidence means.
        blockers.append("monitoring_evidence_unavailable")
    elif monitoring["status"] == "rejected":
        blockers.append("monitoring_report_rejected")
    else:
        blockers.extend(monitoring["promotion_blockers"])

    latest = latest_attempt_by_subject(predictions, evidence_epoch=evidence_epoch)
    selected = sorted(subjects) if subjects else sorted(latest)
    observations: list[dict[str, Any]] = []
    for subject in selected:
        row = latest.get(subject)
        if row is None:
            observations.append(
                _unavailable_observation(
                    task=task,
                    model_key=model_key,
                    evidence_epoch=evidence_epoch,
                    subject=subject,
                    reason="no attempt recorded in this evidence epoch",
                )
            )
            continue
        try:
            observations.append(
                build_observation(row, evidence_epoch=evidence_epoch).to_dict()
            )
        except PresentationError as exc:
            observations.append(
                _unavailable_observation(
                    task=task,
                    model_key=model_key,
                    evidence_epoch=evidence_epoch,
                    subject=subject,
                    reason=f"latest prediction rejected: {exc}",
                )
            )
            blockers.append("latest_prediction_integrity_rejected")

    if any(not item.get("available") for item in observations):
        blockers.append("latest_attempt_unavailable_for_at_least_one_subject")
    if not observations:
        blockers.append("no_observations_in_evidence_epoch")
    # No prediction today records a prospective interval or calibrated
    # probability, so this is currently unconditional -- and it should stay
    # visible until a model version actually changes that.
    if any(item.get("prediction_interval") == UNAVAILABLE for item in observations):
        blockers.append("prospective_prediction_interval_unavailable")
    if any(
        item.get("threshold_probability") == UNAVAILABLE
        or item.get("calibration_status")
        not in {"calibrated", "calibrated_prospectively"}
        for item in observations
    ):
        blockers.append("threshold_probability_calibration_not_measured")
    if any(
        item.get("trailing_baseline_daily_pct") is None
        or item.get("ewma_baseline_daily_pct") is None
        for item in observations
    ):
        blockers.append("frozen_baseline_unavailable")

    payload = {
        "presentation_available": True,
        "task": task,
        "model_key": model_key,
        "evidence_epoch": evidence_epoch,
        "evidence_epoch_status": epoch_status,
        "subject_count": len(observations),
        "observations": observations,
        "monitoring": monitoring,
        "promotion_blockers": list(dict.fromkeys(blockers)),
        "production_authoritative": False,
        "label": EXPERIMENTAL_LABEL,
        "what_this_does_not_mean": (
            "This is a research observation about how much a security may "
            "fluctuate. It is not a forecast of direction, not advice, and is "
            "never consulted by the execution gate. Read-only visibility does "
            "not grant this model any trading authority."
        ),
    }
    assert_no_action_shaped_keys(payload)
    return payload
