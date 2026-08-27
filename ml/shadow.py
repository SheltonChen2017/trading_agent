"""ML-LR-6: pure scheduling and maturity rules for the shadow runtime
(live-readiness plan section 12.3).

Deliberately PURE. Nothing here opens a database, calls a broker, or fits a
model; `scripts/run_ml_shadow.py` supplies the I/O. That split exists so the
rules that decide *when a prediction may be made* and *when its outcome may
be attached* are testable against fixtures with no scheduler, no clock
dependency, and no market data.

Two rules carry almost all the risk:

  1. A prediction's decision cutoff must be a real instant that precedes the
     data it uses. `resolve_decision_cutoff()` derives it from the exchange
     calendar rather than from "now", so a job that runs late produces the
     SAME prediction it would have produced on time -- otherwise a delayed
     scheduler silently becomes a different experiment.

  2. An outcome may attach only once its target is genuinely observable.
     `resolve_target_availability()` walks the exchange calendar forward,
     because "as_of + 20 days" lands on a Saturday roughly two-sevenths of
     the time and inside a holiday week more often than intuition suggests.
     Attaching early would score a model against a price that did not exist.

Neither rule ever guesses. Missing calendar coverage, an ambiguous session,
or an unobservable target produces a refusal that the caller records as
evidence (plan 12.5), never a default.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Mapping

from data.exchange_calendar import (
    ExchangeCalendarError,
    is_trading_session,
    parse_session_date,
    resolve_decision_cutoff,
    resolve_target_availability,
    resolve_target_session,
    session_close_instant,
    trading_sessions,
)
from ml.hashing import hash_payload

ShadowScheduleError = ExchangeCalendarError
_parse_session = parse_session_date


def _parse_instant(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ShadowScheduleError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowScheduleError(
            f"{name} must be a timezone-aware ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        # Plan 12.6: naive timestamps fail closed. A naive instant cannot be
        # ordered against a market close without assuming a timezone, and
        # that assumption decides whether data was available.
        raise ShadowScheduleError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclasses.dataclass(frozen=True)
class MaturityDecision:
    """Whether one prediction's outcome may be attached, and why not."""

    prediction_id: str
    ready: bool
    target_session: str | None
    target_available_at: str | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def decide_maturity(
    prediction: Mapping[str, Any], *, now: str
) -> MaturityDecision:
    """Decide whether `prediction`'s outcome may be attached at `now`.

    Refuses, in order:

      * an UNAVAILABLE prediction never matures. It made no claim, so there
        is nothing to score, and attaching an outcome would quietly convert
        a refusal into a data point (plan 12.3);
      * a prediction that already has an outcome is not re-matured, because
        outcomes are immutable;
      * a target whose availability instant has not passed is PENDING, not
        zero. Recording a missing target as zero would be indistinguishable
        from a model that predicted the outcome exactly.
    """
    prediction_id = str(prediction.get("prediction_id", ""))
    if not prediction_id:
        raise ShadowScheduleError("prediction is missing prediction_id")
    current = _parse_instant(now, "now")

    if not prediction.get("available", False):
        return MaturityDecision(
            prediction_id=prediction_id, ready=False,
            target_session=None, target_available_at=None,
            reason="unavailable predictions make no claim and cannot mature",
        )

    as_of = prediction.get("as_of_session")
    horizon = prediction.get("horizon_sessions")
    recorded = prediction.get("target_available_at")
    if recorded is None:
        return MaturityDecision(
            prediction_id=prediction_id, ready=False,
            target_session=None, target_available_at=None,
            reason=(
                "prediction predates immutable target availability; its true "
                "maturity was never recorded and cannot be reconstructed"
            ),
        )

    try:
        target_session = resolve_target_session(str(as_of), horizon)
        canonical_available_at = _parse_instant(
            resolve_target_availability(str(as_of), horizon),
            "canonical_target_available_at",
        )
    except ShadowScheduleError as exc:
        return MaturityDecision(
            prediction_id=prediction_id, ready=False,
            target_session=None, target_available_at=recorded, reason=str(exc),
        )

    available_at = _parse_instant(recorded, "target_available_at")
    if available_at < canonical_available_at:
        return MaturityDecision(
            prediction_id=prediction_id,
            ready=False,
            target_session=target_session,
            target_available_at=recorded,
            reason=(
                f"recorded target availability {recorded} precedes the exchange-"
                f"calendar target close {canonical_available_at.isoformat()}; refuse "
                "early maturity"
            ),
        )
    if current < available_at:
        return MaturityDecision(
            prediction_id=prediction_id, ready=False,
            target_session=target_session, target_available_at=recorded,
            reason=(
                f"target becomes observable at {recorded}; it is {now}. Pending, "
                "not zero."
            ),
        )
    return MaturityDecision(
        prediction_id=prediction_id, ready=True,
        target_session=target_session, target_available_at=recorded,
    )


def configuration_hash(configuration: Mapping[str, Any]) -> str:
    """Stable fingerprint of everything that changes what a run produces.

    A run whose configuration hash differs is a different experiment
    occupying the same schedule slot, which `claim_ml_shadow_run()` refuses
    rather than silently accepting.
    """
    if not isinstance(configuration, Mapping) or not configuration:
        raise ShadowScheduleError("configuration must be a non-empty mapping")
    return hash_payload(dict(configuration))


def build_lineage(
    *,
    model_artifact_hash: str,
    evaluation_report_hash: str,
    feature_set_version: str,
    label_version: str,
    data_provider_id: str,
    configuration_hash: str,
    code_commit: str,
    schedule_version: str,
) -> dict[str, str]:
    """The plan-12.2 lineage payload, with every key required.

    Keyword-only and fully required on purpose: an optional lineage field is
    one that will eventually be omitted, and a missing field means two
    genuinely different systems can produce the same lineage hash and pool
    their evidence.
    """
    lineage = {
        "model_artifact_hash": model_artifact_hash,
        "evaluation_report_hash": evaluation_report_hash,
        "feature_set_version": feature_set_version,
        "label_version": label_version,
        "data_provider_id": data_provider_id,
        "configuration_hash": configuration_hash,
        "code_commit": code_commit,
        "schedule_version": schedule_version,
    }
    for name, value in lineage.items():
        if not isinstance(value, str) or not value.strip():
            raise ShadowScheduleError(f"lineage.{name} must be a non-empty string")
    return lineage


def epoch_key(model_key: str, task: str, lineage: Mapping[str, str]) -> str:
    """Deterministic epoch name derived from its own lineage.

    Naming the epoch after its lineage means an epoch cannot be reused for a
    changed system even by accident: a different lineage produces a
    different name, and the same lineage reproduces the same one, so an
    idempotent re-open is free.
    """
    digest = hash_payload({"model_key": model_key, "task": task, **dict(lineage)})
    return f"{task}:{model_key}:{digest[:16]}"


def plan_scheduled_sessions(
    *, start: str, end: str, horizon_sessions: int
) -> tuple[dict[str, str], ...]:
    """Every session in [start, end] that can support a full-horizon target.

    Sessions whose target extends past the calendar's coverage are excluded
    rather than scheduled and later refused -- a run that is guaranteed to
    produce nothing is noise in the evidence record.
    """
    first = _parse_session(start, "start")
    last = _parse_session(end, "end")
    planned: list[dict[str, str]] = []
    for session in trading_sessions(first, last):
        text = session.isoformat()
        try:
            target = resolve_target_session(text, horizon_sessions)
        except ShadowScheduleError:
            continue
        planned.append(
            {
                "as_of_session": text,
                "decision_cutoff": resolve_decision_cutoff(text),
                "target_session": target,
                "target_available_at": resolve_target_availability(
                    text, horizon_sessions
                ),
            }
        )
    return tuple(planned)
