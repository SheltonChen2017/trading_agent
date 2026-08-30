"""Outcome-free exact stock-ratio features for the Short Interest lane.

This SI-3A tranche implements only the shares-outstanding form of blueprint
equations 4.2 and 4.4.  It deliberately stops before winsorisation, robust
sector normalisation, S0/S1 scores, seed selection, outcomes, ETFs, and
QuantConnect.  Ratios are represented as reduced rational numbers so this
boundary introduces no binary floating-point or undocumented rounding rule.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from data.exchange_calendar import ExchangeCalendarError, session_open_instant
from data.financial_primitives import decimal_text
from data.hashing import hash_payload
from research.short_interest_etf.contracts import (
    DenominatorKind,
    DenominatorObservation,
    ShortInterestContractError,
    ShortInterestSnapshot,
    _canonical_date,
    _integer,
    _required_text,
    _sha256,
    format_utc_timestamp,
    parse_utc_timestamp,
)
from research.short_interest_etf.dataset import (
    ShortInterestVintage,
    build_identity,
    visible_source_snapshots_as_of,
)
from research.short_interest_etf.pit_eligibility import (
    PitReferenceBundle,
    StockDataReadiness,
    build_stock_data_readiness,
)
from research.short_interest_etf.preregistration import PREREGISTRATION

RAW_FEATURE_SCHEMA_VERSION = "1.0"

REFUSAL_PRIOR_DENOMINATOR_UNAUDITED_FLOAT = (
    "prior_float_denominator_not_yet_audited"
)
REFUSAL_PRIOR_SNAPSHOT_NOT_AUTHENTICATED = "prior_snapshot_not_authenticated"

_FEATURE_REFUSALS = frozenset(
    {
        REFUSAL_PRIOR_DENOMINATOR_UNAUDITED_FLOAT,
        REFUSAL_PRIOR_SNAPSHOT_NOT_AUTHENTICATED,
    }
)


class StockFeatureError(ValueError):
    """An exact raw-feature contract or derivation failed closed."""


def _refuse(detail: str) -> StockFeatureError:
    return StockFeatureError(f"REFUSED: {detail}")


@dataclasses.dataclass(frozen=True)
class ExactRational:
    """A canonical reduced rational value with a positive denominator."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if type(self.numerator) is not int:
            raise _refuse("rational numerator must be an exact integer")
        if type(self.denominator) is not int or self.denominator <= 0:
            raise _refuse("rational denominator must be a positive exact integer")
        reduced = Fraction(self.numerator, self.denominator)
        if (
            reduced.numerator != self.numerator
            or reduced.denominator != self.denominator
        ):
            raise _refuse("rational value must be reduced and canonically signed")

    @classmethod
    def from_values(cls, numerator: int, denominator: int) -> "ExactRational":
        if type(numerator) is not int or type(denominator) is not int:
            raise _refuse("rational inputs must be exact integers")
        if denominator <= 0:
            raise _refuse("rational denominator must be positive")
        value = Fraction(numerator, denominator)
        return cls(value.numerator, value.denominator)

    @classmethod
    def from_fraction(cls, value: Fraction) -> "ExactRational":
        if type(value) is not Fraction:
            raise _refuse("value must be the exact Fraction type")
        return cls(value.numerator, value.denominator)

    def to_fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    def to_payload(self) -> dict[str, int]:
        return {
            "denominator": self.denominator,
            "numerator": self.numerator,
        }


def _whole_positive_shares(value: str, name: str) -> int:
    if type(value) is not str:
        raise _refuse(f"{name} must be canonical decimal text")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise _refuse(f"{name} must be canonical decimal text") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise _refuse(f"{name} must be finite and positive")
    if parsed != parsed.to_integral_value():
        raise _refuse(f"{name} must contain whole shares")
    if value != decimal_text(parsed):
        raise _refuse(f"{name} must use canonical decimal text")
    return int(parsed)


@dataclasses.dataclass(frozen=True)
class PitStockRawFeature:
    """One exact PIT stock-ratio feature with complete upstream lineage."""

    source_dataset_id: str
    source_vintage_sha256: str
    reference_dataset_id: str
    reference_bundle_sha256: str
    preregistration_sha256: str
    readiness_sha256: str
    event_id: str
    prior_event_id: str
    security_id: str
    settlement_date: str
    previous_settlement_date: str
    execution_session: str
    execution_at: str
    security_identity_sha256: str
    lifecycle_record_id: str
    classification_record_id: str
    taxonomy_id: str
    sector_code: str
    industry_code: str
    current_denominator_kind: DenominatorKind
    current_denominator_value: str
    current_denominator_sha256: str
    prior_denominator_kind: DenominatorKind
    prior_denominator_value: str
    prior_denominator_sha256: str
    current_denominator: DenominatorObservation
    prior_denominator: DenominatorObservation
    current_short_shares: int
    prior_short_shares: int
    current_short_ratio: ExactRational
    prior_short_ratio: ExactRational
    delta_short_ratio: ExactRational
    schema_version: str = RAW_FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            self._validate()
        except StockFeatureError:
            raise
        except (
            ExchangeCalendarError,
            InvalidOperation,
            ShortInterestContractError,
            TypeError,
            ValueError,
        ) as exc:
            raise _refuse(f"invalid PIT stock raw feature: {exc}") from exc

    def _validate(self) -> None:
        for name in (
            "source_dataset_id",
            "reference_dataset_id",
            "security_id",
            "execution_session",
            "execution_at",
            "taxonomy_id",
            "sector_code",
            "industry_code",
        ):
            _required_text(getattr(self, name), f"feature.{name}")
        for name in (
            "source_vintage_sha256",
            "reference_bundle_sha256",
            "preregistration_sha256",
            "readiness_sha256",
            "event_id",
            "prior_event_id",
            "security_identity_sha256",
            "lifecycle_record_id",
            "classification_record_id",
            "current_denominator_sha256",
            "prior_denominator_sha256",
        ):
            _sha256(getattr(self, name), f"feature.{name}")
        if self.preregistration_sha256 != PREREGISTRATION.sha256:
            raise _refuse("feature is not bound to the current preregistration")
        expected_dataset_id = (
            f"short-interest-vintage-{self.source_vintage_sha256[:16]}"
        )
        if self.source_dataset_id != expected_dataset_id:
            raise _refuse("feature source_dataset_id does not match its vintage")

        previous = _canonical_date(
            self.previous_settlement_date, "feature.previous_settlement_date"
        )
        settlement = _canonical_date(
            self.settlement_date, "feature.settlement_date"
        )
        execution = _canonical_date(
            self.execution_session, "feature.execution_session"
        )
        if previous >= settlement:
            raise _refuse("feature previous settlement must precede settlement")
        if execution <= settlement:
            raise _refuse("feature execution session must follow settlement")
        parse_utc_timestamp(self.execution_at, "feature.execution_at")
        expected_execution_at = format_utc_timestamp(
            session_open_instant(self.execution_session)
        )
        if self.execution_at != expected_execution_at:
            raise _refuse("feature execution_at must be the XNYS session open")

        for name in ("taxonomy_id", "sector_code", "industry_code"):
            value = getattr(self, name)
            if value != value.upper():
                raise _refuse(f"feature.{name} must be canonical uppercase")
        for name in ("current_denominator_kind", "prior_denominator_kind"):
            if type(getattr(self, name)) is not DenominatorKind:
                raise _refuse(f"feature.{name} must be an exact DenominatorKind")
            if (
                getattr(self, name)
                is not DenominatorKind.POINT_IN_TIME_SHARES_OUTSTANDING
            ):
                raise _refuse("SI-3A accepts PIT shares-outstanding ratios only")

        for side in ("current", "prior"):
            observation = getattr(self, f"{side}_denominator")
            if type(observation) is not DenominatorObservation:
                raise _refuse(
                    f"feature.{side}_denominator must be the exact "
                    "DenominatorObservation type"
                )
            if hash_payload(observation.to_payload()) != getattr(
                self, f"{side}_denominator_sha256"
            ):
                raise _refuse(
                    f"feature.{side}_denominator_sha256 does not digest "
                    f"feature.{side}_denominator"
                )
            if decimal_text(Decimal(observation.value)) != getattr(
                self, f"{side}_denominator_value"
            ):
                raise _refuse(
                    f"feature.{side}_denominator_value does not match "
                    f"feature.{side}_denominator"
                )

        current_denominator = _whole_positive_shares(
            self.current_denominator_value,
            "feature.current_denominator_value",
        )
        prior_denominator = _whole_positive_shares(
            self.prior_denominator_value,
            "feature.prior_denominator_value",
        )
        _integer(self.current_short_shares, "feature.current_short_shares")
        _integer(self.prior_short_shares, "feature.prior_short_shares")
        for name in (
            "current_short_ratio",
            "prior_short_ratio",
            "delta_short_ratio",
        ):
            if type(getattr(self, name)) is not ExactRational:
                raise _refuse(f"feature.{name} must be the exact ExactRational type")

        expected_current = ExactRational.from_values(
            self.current_short_shares, current_denominator
        )
        expected_prior = ExactRational.from_values(
            self.prior_short_shares, prior_denominator
        )
        expected_delta = ExactRational.from_fraction(
            expected_current.to_fraction() - expected_prior.to_fraction()
        )
        if self.current_short_ratio != expected_current:
            raise _refuse("current_short_ratio does not match current PIT facts")
        if self.prior_short_ratio != expected_prior:
            raise _refuse("prior_short_ratio does not match prior PIT facts")
        if self.delta_short_ratio != expected_delta:
            raise _refuse("delta_short_ratio does not match exact ratio difference")
        if self.schema_version != RAW_FEATURE_SCHEMA_VERSION:
            raise _refuse(
                f"unsupported raw feature schema_version {self.schema_version!r}"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "classification_record_id": self.classification_record_id,
            "current_denominator": self.current_denominator.to_payload(),
            "current_denominator_kind": self.current_denominator_kind.value,
            "current_denominator_sha256": self.current_denominator_sha256,
            "current_denominator_value": self.current_denominator_value,
            "current_short_ratio": self.current_short_ratio.to_payload(),
            "current_short_shares": self.current_short_shares,
            "delta_short_ratio": self.delta_short_ratio.to_payload(),
            "event_id": self.event_id,
            "execution_at": self.execution_at,
            "execution_session": self.execution_session,
            "industry_code": self.industry_code,
            "lifecycle_record_id": self.lifecycle_record_id,
            "preregistration_sha256": self.preregistration_sha256,
            "previous_settlement_date": self.previous_settlement_date,
            "prior_denominator": self.prior_denominator.to_payload(),
            "prior_denominator_kind": self.prior_denominator_kind.value,
            "prior_denominator_sha256": self.prior_denominator_sha256,
            "prior_denominator_value": self.prior_denominator_value,
            "prior_event_id": self.prior_event_id,
            "prior_short_ratio": self.prior_short_ratio.to_payload(),
            "prior_short_shares": self.prior_short_shares,
            "readiness_sha256": self.readiness_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "reference_dataset_id": self.reference_dataset_id,
            "schema_version": self.schema_version,
            "sector_code": self.sector_code,
            "security_id": self.security_id,
            "security_identity_sha256": self.security_identity_sha256,
            "settlement_date": self.settlement_date,
            "source_dataset_id": self.source_dataset_id,
            "source_vintage_sha256": self.source_vintage_sha256,
            "taxonomy_id": self.taxonomy_id,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


@dataclasses.dataclass(frozen=True)
class StockFeatureDisposition:
    """One retained readiness row and its feature or named refusal."""

    readiness: StockDataReadiness
    feature: PitStockRawFeature | None
    refusal_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.readiness) is not StockDataReadiness:
            raise _refuse("readiness must be the exact StockDataReadiness type")
        if self.feature is not None and type(self.feature) is not PitStockRawFeature:
            raise _refuse("feature must be the exact PitStockRawFeature type")
        if not isinstance(self.refusal_reasons, tuple) or not all(
            type(item) is str and item and item == item.strip()
            for item in self.refusal_reasons
        ):
            raise _refuse("feature refusal_reasons must be canonical strings")
        if self.refusal_reasons != tuple(sorted(set(self.refusal_reasons))):
            raise _refuse("feature refusal_reasons must be unique and sorted")

        if not self.readiness.ready:
            if self.feature is not None:
                raise _refuse("non-ready source data cannot carry a stock feature")
            if self.refusal_reasons != self.readiness.refusal_reasons:
                raise _refuse("source readiness refusals must be preserved exactly")
            return

        if self.feature is None:
            if len(self.refusal_reasons) != 1 or not set(
                self.refusal_reasons
            ).issubset(_FEATURE_REFUSALS):
                raise _refuse("ready source without a feature needs one named refusal")
            return
        if self.refusal_reasons:
            raise _refuse("a completed stock feature cannot carry refusal reasons")

        feature = self.feature
        expected = {
            "classification_record_id": self.readiness.classification_record_id,
            "current_denominator_sha256": self.readiness.denominator_sha256,
            "event_id": self.readiness.event_id,
            "execution_at": self.readiness.execution_at,
            "execution_session": self.readiness.execution_session,
            "industry_code": self.readiness.industry_code,
            "lifecycle_record_id": self.readiness.lifecycle_record_id,
            "readiness_sha256": self.readiness.sha256,
            "reference_bundle_sha256": self.readiness.reference_bundle_sha256,
            "reference_dataset_id": self.readiness.reference_dataset_id,
            "sector_code": self.readiness.sector_code,
            "security_id": self.readiness.security_id,
            "security_identity_sha256": self.readiness.security_identity_sha256,
            "settlement_date": self.readiness.settlement_date,
            "source_dataset_id": self.readiness.source_dataset_id,
            "source_vintage_sha256": self.readiness.source_vintage_sha256,
            "taxonomy_id": self.readiness.taxonomy_id,
        }
        for name, value in expected.items():
            if getattr(feature, name) != value:
                raise _refuse(f"feature.{name} does not match its readiness row")

    def to_payload(self) -> dict[str, Any]:
        return {
            "feature": self.feature.to_payload() if self.feature is not None else None,
            "readiness": self.readiness.to_payload(),
            "refusal_reasons": list(self.refusal_reasons),
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def _select_authenticated_prior(
    vintage: ShortInterestVintage,
    current: ShortInterestSnapshot,
    execution_at: str,
) -> ShortInterestSnapshot | None:
    visible = visible_source_snapshots_as_of(
        vintage,
        parse_utc_timestamp(execution_at, "readiness.execution_at"),
    )
    candidates = [
        item
        for item in visible
        if item.security.security_id == current.security.security_id
        and item.settlement_date == current.previous_settlement_date
    ]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise _refuse("execution-visible prior snapshot is ambiguous")
    return candidates[0]


def build_pit_stock_raw_features(
    vintage: ShortInterestVintage,
    references: PitReferenceBundle,
) -> tuple[StockFeatureDisposition, ...]:
    """Disposition every source event and derive exact ratios for ready rows."""
    if type(vintage) is not ShortInterestVintage:
        raise _refuse("vintage must be the exact ShortInterestVintage type")
    if type(references) is not PitReferenceBundle:
        raise _refuse("references must be the exact PitReferenceBundle type")

    source_identity = build_identity(vintage)
    readiness_rows = build_stock_data_readiness(vintage, references)
    snapshot_by_event = {item.event_id: item for item in vintage.snapshots}
    dispositions: list[StockFeatureDisposition] = []

    for readiness in readiness_rows:
        if not readiness.ready:
            dispositions.append(
                StockFeatureDisposition(
                    readiness=readiness,
                    feature=None,
                    refusal_reasons=readiness.refusal_reasons,
                )
            )
            continue

        current = snapshot_by_event.get(readiness.event_id)
        if current is None:
            raise _refuse("ready event is absent from the authenticated vintage")
        prior = _select_authenticated_prior(
            vintage,
            current,
            readiness.execution_at,
        )
        if prior is None:
            dispositions.append(
                StockFeatureDisposition(
                    readiness=readiness,
                    feature=None,
                    refusal_reasons=(REFUSAL_PRIOR_SNAPSHOT_NOT_AUTHENTICATED,),
                )
            )
            continue
        if (
            prior.denominator.kind
            is not DenominatorKind.POINT_IN_TIME_SHARES_OUTSTANDING
        ):
            dispositions.append(
                StockFeatureDisposition(
                    readiness=readiness,
                    feature=None,
                    refusal_reasons=(REFUSAL_PRIOR_DENOMINATOR_UNAUDITED_FLOAT,),
                )
            )
            continue

        current_denominator_value = decimal_text(Decimal(current.denominator.value))
        prior_denominator_value = decimal_text(Decimal(prior.denominator.value))
        current_denominator = _whole_positive_shares(
            current_denominator_value, "current denominator"
        )
        prior_denominator = _whole_positive_shares(
            prior_denominator_value, "prior denominator"
        )
        current_ratio = ExactRational.from_values(
            current.current_short_shares, current_denominator
        )
        prior_ratio = ExactRational.from_values(
            prior.current_short_shares, prior_denominator
        )
        delta_ratio = ExactRational.from_fraction(
            current_ratio.to_fraction() - prior_ratio.to_fraction()
        )
        if current.previous_short_shares != prior.current_short_shares:
            raise _refuse(
                "current previous_short_shares does not match authenticated prior"
            )

        feature = PitStockRawFeature(
            source_dataset_id=source_identity["dataset_id"],
            source_vintage_sha256=source_identity["content_hash"],
            reference_dataset_id=references.manifest.reference_dataset_id,
            reference_bundle_sha256=references.sha256,
            preregistration_sha256=PREREGISTRATION.sha256,
            readiness_sha256=readiness.sha256,
            event_id=current.event_id,
            prior_event_id=prior.event_id,
            security_id=current.security.security_id,
            settlement_date=current.settlement_date,
            previous_settlement_date=current.previous_settlement_date,
            execution_session=readiness.execution_session,
            execution_at=readiness.execution_at,
            security_identity_sha256=readiness.security_identity_sha256,
            lifecycle_record_id=readiness.lifecycle_record_id,
            classification_record_id=readiness.classification_record_id,
            taxonomy_id=readiness.taxonomy_id,
            sector_code=readiness.sector_code,
            industry_code=readiness.industry_code,
            current_denominator_kind=current.denominator.kind,
            current_denominator_value=current_denominator_value,
            current_denominator_sha256=readiness.denominator_sha256,
            current_denominator=current.denominator,
            prior_denominator_kind=prior.denominator.kind,
            prior_denominator_value=prior_denominator_value,
            prior_denominator_sha256=hash_payload(prior.denominator.to_payload()),
            prior_denominator=prior.denominator,
            current_short_shares=current.current_short_shares,
            prior_short_shares=prior.current_short_shares,
            current_short_ratio=current_ratio,
            prior_short_ratio=prior_ratio,
            delta_short_ratio=delta_ratio,
        )
        dispositions.append(
            StockFeatureDisposition(
                readiness=readiness,
                feature=feature,
                refusal_reasons=(),
            )
        )

    return tuple(
        sorted(
            dispositions,
            key=lambda item: (
                item.readiness.settlement_date,
                item.readiness.security_id,
                item.readiness.event_id,
            ),
        )
    )
