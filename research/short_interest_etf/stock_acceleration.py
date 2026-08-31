"""Outcome-free exact short-ratio acceleration for the Short Interest lane.

This SI-3B tranche implements only blueprint equation 4.6 on the exact
shares-outstanding ratio deltas produced by :mod:`stock_features`.  It does not
normalise, rank, select stocks, read prices or outcomes, aggregate ETFs, or
touch QuantConnect.  Every input disposition is retained, including the two
cycles needed to warm up a three-cycle acceleration.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from data.hashing import hash_payload
from research.short_interest_etf.contracts import (
    ShortInterestContractError,
    _canonical_date,
    _required_text,
    _sha256,
    parse_utc_timestamp,
)
from research.short_interest_etf.pit_eligibility import REFUSAL_MISSING_PRIOR
from research.short_interest_etf.stock_features import (
    ExactRational,
    PitStockRawFeature,
    StockFeatureDisposition,
)

ACCELERATION_SCHEMA_VERSION = "1.0"
REFUSAL_PRIOR_DELTA_FEATURE_NOT_AVAILABLE = (
    "prior_delta_feature_not_available"
)
REFUSAL_INSUFFICIENT_PRIOR_DELTA_HISTORY = (
    "insufficient_prior_delta_history"
)


class StockAccelerationError(ValueError):
    """An exact acceleration contract or complete-batch invariant failed."""


def _refuse(detail: str) -> StockAccelerationError:
    return StockAccelerationError(f"REFUSED: {detail}")


def _checked_required(value: Any, name: str) -> str:
    try:
        return _required_text(value, name)
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        raise _refuse(f"invalid {name}: {exc}") from exc


def _checked_sha256(value: Any, name: str) -> str:
    try:
        return _sha256(value, name)
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        raise _refuse(f"invalid {name}: {exc}") from exc


def _checked_date(value: Any, name: str):
    try:
        return _canonical_date(value, name)
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        raise _refuse(f"invalid {name}: {exc}") from exc


def _checked_timestamp(value: Any, name: str):
    try:
        return parse_utc_timestamp(value, name)
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        raise _refuse(f"invalid {name}: {exc}") from exc


@dataclasses.dataclass(frozen=True)
class PitStockAccelerationFeature:
    """Equation 4.6 with both raw-feature witnesses referenced by hash."""

    source_dataset_id: str
    source_vintage_sha256: str
    reference_bundle_sha256: str
    preregistration_sha256: str
    current_raw_feature_sha256: str
    prior_raw_feature_sha256: str
    security_id: str
    event_id: str
    prior_event_id: str
    prior_prior_event_id: str
    settlement_date: str
    previous_settlement_date: str
    prior_previous_settlement_date: str
    current_delta_short_ratio: ExactRational
    prior_delta_short_ratio: ExactRational
    acceleration_short_ratio: ExactRational
    current_feature: PitStockRawFeature
    prior_feature: PitStockRawFeature
    schema_version: str = ACCELERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.current_feature) is not PitStockRawFeature:
            raise _refuse(
                "current_feature must be the exact PitStockRawFeature type"
            )
        if type(self.prior_feature) is not PitStockRawFeature:
            raise _refuse(
                "prior_feature must be the exact PitStockRawFeature type"
            )
        for name in (
            "source_dataset_id",
            "security_id",
        ):
            _checked_required(getattr(self, name), f"acceleration.{name}")
        for name in (
            "source_vintage_sha256",
            "reference_bundle_sha256",
            "preregistration_sha256",
            "current_raw_feature_sha256",
            "prior_raw_feature_sha256",
            "event_id",
            "prior_event_id",
            "prior_prior_event_id",
        ):
            _checked_sha256(getattr(self, name), f"acceleration.{name}")
        prior_previous = _checked_date(
            self.prior_previous_settlement_date,
            "acceleration.prior_previous_settlement_date",
        )
        previous = _checked_date(
            self.previous_settlement_date,
            "acceleration.previous_settlement_date",
        )
        settlement = _checked_date(
            self.settlement_date,
            "acceleration.settlement_date",
        )
        if not prior_previous < previous < settlement:
            raise _refuse(
                "acceleration settlements must form a strict three-cycle chain"
            )

        current = self.current_feature
        prior = self.prior_feature
        for name in (
            "source_dataset_id",
            "source_vintage_sha256",
            "reference_bundle_sha256",
            "preregistration_sha256",
            "security_id",
        ):
            if getattr(current, name) != getattr(prior, name):
                raise _refuse(
                    f"current and prior raw features have different {name}"
                )
        if current.prior_snapshot != prior.current_snapshot:
            raise _refuse(
                "current prior_snapshot must equal prior current_snapshot"
            )
        if current.prior_readiness_sha256 != prior.readiness_sha256:
            raise _refuse(
                "current prior readiness must equal prior feature readiness"
            )
        if _checked_timestamp(
            prior.execution_at, "prior_feature.execution_at"
        ) > _checked_timestamp(current.execution_at, "current_feature.execution_at"):
            raise _refuse("prior raw feature cannot execute after current raw feature")
        for name in (
            "current_delta_short_ratio",
            "prior_delta_short_ratio",
            "acceleration_short_ratio",
        ):
            if type(getattr(self, name)) is not ExactRational:
                raise _refuse(
                    f"acceleration.{name} must be the exact ExactRational type"
                )

        expected = {
            "source_dataset_id": current.source_dataset_id,
            "source_vintage_sha256": current.source_vintage_sha256,
            "reference_bundle_sha256": current.reference_bundle_sha256,
            "preregistration_sha256": current.preregistration_sha256,
            "current_raw_feature_sha256": current.sha256,
            "prior_raw_feature_sha256": prior.sha256,
            "security_id": current.security_id,
            "event_id": current.event_id,
            "prior_event_id": current.prior_event_id,
            "prior_prior_event_id": prior.prior_event_id,
            "settlement_date": current.settlement_date,
            "previous_settlement_date": current.previous_settlement_date,
            "prior_previous_settlement_date": prior.previous_settlement_date,
            "current_delta_short_ratio": current.delta_short_ratio,
            "prior_delta_short_ratio": prior.delta_short_ratio,
        }
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise _refuse(
                    f"acceleration.{name} does not match its raw-feature witnesses"
                )
        if current.prior_event_id != prior.event_id:
            raise _refuse(
                "current prior_event_id must equal prior feature event_id"
            )
        expected_acceleration = ExactRational.from_fraction(
            current.delta_short_ratio.to_fraction()
            - prior.delta_short_ratio.to_fraction()
        )
        if self.acceleration_short_ratio != expected_acceleration:
            raise _refuse(
                "acceleration_short_ratio does not match exact delta difference"
            )
        if (
            type(self.schema_version) is not str
            or self.schema_version != ACCELERATION_SCHEMA_VERSION
        ):
            raise _refuse(
                "unsupported acceleration schema_version "
                f"{self.schema_version!r}"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "acceleration_short_ratio": self.acceleration_short_ratio.to_payload(),
            "current_delta_short_ratio": self.current_delta_short_ratio.to_payload(),
            "current_raw_feature_sha256": self.current_raw_feature_sha256,
            "event_id": self.event_id,
            "preregistration_sha256": self.preregistration_sha256,
            "previous_settlement_date": self.previous_settlement_date,
            "prior_delta_short_ratio": self.prior_delta_short_ratio.to_payload(),
            "prior_event_id": self.prior_event_id,
            "prior_previous_settlement_date": self.prior_previous_settlement_date,
            "prior_prior_event_id": self.prior_prior_event_id,
            "prior_raw_feature_sha256": self.prior_raw_feature_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "schema_version": self.schema_version,
            "security_id": self.security_id,
            "settlement_date": self.settlement_date,
            "source_dataset_id": self.source_dataset_id,
            "source_vintage_sha256": self.source_vintage_sha256,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


@dataclasses.dataclass(frozen=True)
class StockAccelerationDisposition:
    """One retained SI-3A row and its acceleration or exact refusal."""

    current: StockFeatureDisposition
    prior: StockFeatureDisposition | None
    feature: PitStockAccelerationFeature | None
    refusal_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.current) is not StockFeatureDisposition:
            raise _refuse(
                "current must be the exact StockFeatureDisposition type"
            )
        if self.prior is not None and type(self.prior) is not StockFeatureDisposition:
            raise _refuse(
                "prior must be the exact StockFeatureDisposition type"
            )
        if self.feature is not None and type(
            self.feature
        ) is not PitStockAccelerationFeature:
            raise _refuse(
                "feature must be the exact PitStockAccelerationFeature type"
            )
        if type(self.refusal_reasons) is not tuple:
            raise _refuse(
                "acceleration refusal_reasons must be the exact tuple type"
            )
        if not all(
            type(item) is str and item and item == item.strip()
            for item in self.refusal_reasons
        ):
            raise _refuse("acceleration refusal_reasons must be canonical strings")
        if self.refusal_reasons != tuple(sorted(set(self.refusal_reasons))):
            raise _refuse(
                "acceleration refusal_reasons must be unique and sorted"
            )

        current_feature = self.current.feature
        if current_feature is None:
            if self.prior is not None or self.feature is not None:
                raise _refuse(
                    "upstream stock-feature refusal cannot carry acceleration data"
                )
            if self.refusal_reasons != self.current.refusal_reasons:
                raise _refuse(
                    "upstream stock-feature refusals must be preserved exactly"
                )
            return

        if self.prior is None:
            raise _refuse("raw stock feature requires its prior disposition")
        if self.current.prior_readiness != self.prior.readiness:
            raise _refuse(
                "current prior_readiness must equal prior disposition readiness"
            )
        if current_feature.prior_event_id != self.prior.readiness.event_id:
            raise _refuse(
                "raw feature prior_event_id must equal prior disposition event_id"
            )
        prior_feature = self.prior.feature
        if prior_feature is None:
            if self.feature is not None:
                raise _refuse("missing prior delta cannot carry acceleration")
            expected_refusal = (
                REFUSAL_INSUFFICIENT_PRIOR_DELTA_HISTORY
                if self.prior.refusal_reasons == (REFUSAL_MISSING_PRIOR,)
                else REFUSAL_PRIOR_DELTA_FEATURE_NOT_AVAILABLE
            )
            if self.refusal_reasons != (expected_refusal,):
                raise _refuse(
                    "missing prior delta requires its exact state-specific refusal"
                )
            return

        if self.refusal_reasons:
            raise _refuse("completed acceleration cannot carry refusal reasons")
        if self.feature is None:
            raise _refuse("consecutive raw features require acceleration")
        if self.feature.current_feature != current_feature:
            raise _refuse(
                "acceleration current_feature does not match current disposition"
            )
        if self.feature.prior_feature != prior_feature:
            raise _refuse(
                "acceleration prior_feature does not match prior disposition"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "current": self.current.to_payload(),
            "feature": self.feature.to_payload() if self.feature is not None else None,
            "prior": self.prior.to_payload() if self.prior is not None else None,
            "refusal_reasons": list(self.refusal_reasons),
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def build_pit_stock_accelerations(
    raw_dispositions: tuple[StockFeatureDisposition, ...],
) -> tuple[StockAccelerationDisposition, ...]:
    """Disposition a complete homogeneous SI-3A batch without silent drops."""
    if type(raw_dispositions) is not tuple or not all(
        type(item) is StockFeatureDisposition for item in raw_dispositions
    ):
        raise _refuse(
            "raw_dispositions must be an exact tuple of exact "
            "StockFeatureDisposition values"
        )
    if not raw_dispositions:
        return ()

    event_ids = [item.readiness.event_id for item in raw_dispositions]
    if len(event_ids) != len(set(event_ids)):
        raise _refuse("raw_dispositions contain duplicate readiness event_id")
    for name in (
        "source_dataset_id",
        "source_vintage_sha256",
        "reference_dataset_id",
        "reference_bundle_sha256",
    ):
        values = {getattr(item.readiness, name) for item in raw_dispositions}
        if len(values) != 1:
            raise _refuse(f"raw_dispositions mix {name}")

    source_context = raw_dispositions[0].source_context
    if source_context is None:
        raise _refuse("raw_dispositions have no authenticated source_context")
    source_context_sha256 = source_context.sha256
    if any(
        item.source_context is None
        or item.source_context.sha256 != source_context_sha256
        for item in raw_dispositions
    ):
        raise _refuse("raw_dispositions mix source_context_sha256")
    expected_event_ids = {
        item.event_id for item in source_context.source_vintage.snapshots
    }
    if set(event_ids) != expected_event_ids:
        raise _refuse(
            "raw_dispositions event set is incomplete for source_vintage"
        )

    by_event = {item.readiness.event_id: item for item in raw_dispositions}
    results: list[StockAccelerationDisposition] = []
    for current in raw_dispositions:
        current_feature = current.feature
        if current_feature is None:
            results.append(
                StockAccelerationDisposition(
                    current=current,
                    prior=None,
                    feature=None,
                    refusal_reasons=current.refusal_reasons,
                )
            )
            continue

        prior = by_event.get(current_feature.prior_event_id)
        if prior is None:
            raise _refuse(
                "raw_dispositions omit the event required by prior_event_id"
            )
        if prior.feature is None:
            refusal = (
                REFUSAL_INSUFFICIENT_PRIOR_DELTA_HISTORY
                if prior.refusal_reasons == (REFUSAL_MISSING_PRIOR,)
                else REFUSAL_PRIOR_DELTA_FEATURE_NOT_AVAILABLE
            )
            results.append(
                StockAccelerationDisposition(
                    current=current,
                    prior=prior,
                    feature=None,
                    refusal_reasons=(refusal,),
                )
            )
            continue

        acceleration = ExactRational.from_fraction(
            current_feature.delta_short_ratio.to_fraction()
            - prior.feature.delta_short_ratio.to_fraction()
        )
        feature = PitStockAccelerationFeature(
            source_dataset_id=current_feature.source_dataset_id,
            source_vintage_sha256=current_feature.source_vintage_sha256,
            reference_bundle_sha256=current_feature.reference_bundle_sha256,
            preregistration_sha256=current_feature.preregistration_sha256,
            current_raw_feature_sha256=current_feature.sha256,
            prior_raw_feature_sha256=prior.feature.sha256,
            security_id=current_feature.security_id,
            event_id=current_feature.event_id,
            prior_event_id=current_feature.prior_event_id,
            prior_prior_event_id=prior.feature.prior_event_id,
            settlement_date=current_feature.settlement_date,
            previous_settlement_date=current_feature.previous_settlement_date,
            prior_previous_settlement_date=prior.feature.previous_settlement_date,
            current_delta_short_ratio=current_feature.delta_short_ratio,
            prior_delta_short_ratio=prior.feature.delta_short_ratio,
            acceleration_short_ratio=acceleration,
            current_feature=current_feature,
            prior_feature=prior.feature,
        )
        results.append(
            StockAccelerationDisposition(
                current=current,
                prior=prior,
                feature=feature,
                refusal_reasons=(),
            )
        )

    return tuple(
        sorted(
            results,
            key=lambda item: (
                item.current.readiness.settlement_date,
                item.current.readiness.security_id,
                item.current.readiness.event_id,
            ),
        )
    )
