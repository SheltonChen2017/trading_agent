"""Strict data contracts for the read-only investment committee."""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Mapping


class PrivacyMode(str, Enum):
    """How much portfolio value information may leave the deterministic layer."""

    PERCENTAGES_ONLY = "percentages_only"
    ROUNDED_DOLLARS = "rounded_dollars"
    EXACT_DOLLARS = "exact_dollars"


class FactAvailability(str, Enum):
    AVAILABLE = "available"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class Verdict(str, Enum):
    SUPPORT = "support"
    SUPPORT_WITH_CAUTION = "support_with_caution"
    REQUEST_REVISION = "request_revision"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ConfidenceLabel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class ReviewStatus(str, Enum):
    ACCEPTED = "accepted"
    REVIEW_UNAVAILABLE = "review_unavailable"


@dataclasses.dataclass(frozen=True)
class CommitteeFact:
    """One addressable deterministic input fact.

    ``production_authoritative`` means the fact may support a committee
    endorsement.  Rejected, exploratory, stale, and unavailable research can
    still be shown as context, but cannot acquire authority merely because a
    model cited it.
    """

    source_id: str
    category: str
    label: str
    value: str | int | float | bool | None
    unit: str | None = None
    as_of: str | None = None
    availability: FactAvailability = FactAvailability.AVAILABLE
    detail: str = ""
    tickers: tuple[str, ...] = ()
    production_authoritative: bool = True
    critical: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["availability"] = self.availability.value
        result["tickers"] = list(self.tickers)
        return result

    def grounding_text(self) -> str:
        parts = [self.label, str(self.value)]
        if self.unit:
            parts.append(self.unit)
        if self.as_of:
            parts.append(self.as_of)
        if self.detail:
            parts.append(self.detail)
        parts.extend(self.tickers)
        return " | ".join(parts)


@dataclasses.dataclass(frozen=True)
class CommitteeSubject:
    proposal_id: str
    action_type: str
    ticker: str
    side: str
    evidence_status: str
    source_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["source_ids"] = list(self.source_ids)
        return result


@dataclasses.dataclass(frozen=True)
class CommitteeInput:
    packet_id: str
    packet_schema_version: str
    generated_at: str
    policy_version: str
    privacy_mode: PrivacyMode
    portfolio_tickers: tuple[str, ...]
    facts: tuple[CommitteeFact, ...]
    subject: CommitteeSubject
    input_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_version": self.input_version,
            "packet_id": self.packet_id,
            "packet_schema_version": self.packet_schema_version,
            "generated_at": self.generated_at,
            "policy_version": self.policy_version,
            "privacy_mode": self.privacy_mode.value,
            "portfolio_tickers": list(self.portfolio_tickers),
            "facts": [fact.to_dict() for fact in self.facts],
            "subject": self.subject.to_dict(),
        }

    @property
    def fact_by_id(self) -> dict[str, CommitteeFact]:
        return {fact.source_id: fact for fact in self.facts}


@dataclasses.dataclass(frozen=True)
class CitedPoint:
    text: str
    source_ids: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, path: str) -> "CitedPoint":
        if not isinstance(raw, Mapping):
            raise CommitteeSchemaError(f"{path} must be a JSON object.")
        _require_exact_keys(raw, {"text", "source_ids"}, path=path)
        text = raw["text"]
        source_ids = raw["source_ids"]
        if not isinstance(text, str) or not text.strip() or len(text) > 800:
            raise CommitteeSchemaError(f"{path}.text must be a non-empty string of at most 800 characters.")
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or len(source_ids) > 12
            or not all(isinstance(value, str) and value for value in source_ids)
        ):
            raise CommitteeSchemaError(
                f"{path}.source_ids must contain 1-12 non-empty strings."
            )
        if len(set(source_ids)) != len(source_ids):
            raise CommitteeSchemaError(f"{path}.source_ids contains duplicates.")
        return cls(text=text.strip(), source_ids=tuple(source_ids))

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "source_ids": list(self.source_ids)}


@dataclasses.dataclass(frozen=True)
class CommitteeReview:
    verdict: Verdict
    summary: CitedPoint
    supporting_points: tuple[CitedPoint, ...]
    counterarguments: tuple[CitedPoint, ...]
    hidden_risks: tuple[CitedPoint, ...]
    data_quality_warnings: tuple[CitedPoint, ...]
    invalidation_conditions: tuple[CitedPoint, ...]
    revision_requests: tuple[CitedPoint, ...]
    confidence_label: ConfidenceLabel
    confidence_basis: CitedPoint

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "CommitteeReview":
        if not isinstance(raw, Mapping):
            raise CommitteeSchemaError("committee review must be a JSON object.")
        required = {
            "verdict",
            "summary",
            "supporting_points",
            "counterarguments",
            "hidden_risks",
            "data_quality_warnings",
            "invalidation_conditions",
            "revision_requests",
            "confidence_label",
            "confidence_basis",
        }
        _require_exact_keys(raw, required, path="review")
        try:
            verdict = Verdict(raw["verdict"])
        except (TypeError, ValueError) as exc:
            raise CommitteeSchemaError("review.verdict is invalid.") from exc
        try:
            confidence = ConfidenceLabel(raw["confidence_label"])
        except (TypeError, ValueError) as exc:
            raise CommitteeSchemaError("review.confidence_label is invalid.") from exc

        def points(name: str, *, maximum: int = 8) -> tuple[CitedPoint, ...]:
            value = raw[name]
            if not isinstance(value, list) or len(value) > maximum:
                raise CommitteeSchemaError(
                    f"review.{name} must be an array with at most {maximum} entries."
                )
            return tuple(
                CitedPoint.from_mapping(item, path=f"review.{name}[{index}]")
                for index, item in enumerate(value)
                if isinstance(item, Mapping)
            )

        # Do not silently drop malformed list entries.
        for name in (
            "supporting_points",
            "counterarguments",
            "hidden_risks",
            "data_quality_warnings",
            "invalidation_conditions",
            "revision_requests",
        ):
            value = raw[name]
            if isinstance(value, list) and not all(isinstance(item, Mapping) for item in value):
                raise CommitteeSchemaError(f"review.{name} entries must be JSON objects.")

        return cls(
            verdict=verdict,
            summary=CitedPoint.from_mapping(raw["summary"], path="review.summary"),
            supporting_points=points("supporting_points"),
            counterarguments=points("counterarguments"),
            hidden_risks=points("hidden_risks"),
            data_quality_warnings=points("data_quality_warnings"),
            invalidation_conditions=points("invalidation_conditions"),
            revision_requests=points("revision_requests"),
            confidence_label=confidence,
            confidence_basis=CitedPoint.from_mapping(
                raw["confidence_basis"], path="review.confidence_basis"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary.to_dict(),
            "supporting_points": [value.to_dict() for value in self.supporting_points],
            "counterarguments": [value.to_dict() for value in self.counterarguments],
            "hidden_risks": [value.to_dict() for value in self.hidden_risks],
            "data_quality_warnings": [
                value.to_dict() for value in self.data_quality_warnings
            ],
            "invalidation_conditions": [
                value.to_dict() for value in self.invalidation_conditions
            ],
            "revision_requests": [value.to_dict() for value in self.revision_requests],
            "confidence_label": self.confidence_label.value,
            "confidence_basis": self.confidence_basis.to_dict(),
        }

    def all_cited_points(self) -> tuple[tuple[str, CitedPoint], ...]:
        result: list[tuple[str, CitedPoint]] = [
            ("summary", self.summary),
            ("confidence_basis", self.confidence_basis),
        ]
        for name in (
            "supporting_points",
            "counterarguments",
            "hidden_risks",
            "data_quality_warnings",
            "invalidation_conditions",
            "revision_requests",
        ):
            result.extend((name, value) for value in getattr(self, name))
        return tuple(result)


class CommitteeSchemaError(ValueError):
    pass


def _require_exact_keys(
    raw: Mapping[str, Any], expected: set[str], *, path: str
) -> None:
    actual = set(raw)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise CommitteeSchemaError(
            f"{path} has invalid fields; missing={missing}, extra={extra}."
        )


def _point_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string", "maxLength": 800},
            "source_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "uniqueItems": True,
                "items": {"type": "string"},
            },
        },
        "required": ["text", "source_ids"],
        "additionalProperties": False,
    }


COMMITTEE_REVIEW_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": [value.value for value in Verdict]},
        "summary": _point_schema(),
        "supporting_points": {
            "type": "array",
            "maxItems": 8,
            "items": _point_schema(),
        },
        "counterarguments": {
            "type": "array",
            "maxItems": 8,
            "items": _point_schema(),
        },
        "hidden_risks": {
            "type": "array",
            "maxItems": 8,
            "items": _point_schema(),
        },
        "data_quality_warnings": {
            "type": "array",
            "maxItems": 8,
            "items": _point_schema(),
        },
        "invalidation_conditions": {
            "type": "array",
            "maxItems": 8,
            "items": _point_schema(),
        },
        "revision_requests": {
            "type": "array",
            "maxItems": 8,
            "items": _point_schema(),
        },
        "confidence_label": {
            "type": "string",
            "enum": [value.value for value in ConfidenceLabel],
        },
        "confidence_basis": _point_schema(),
    },
    "required": [
        "verdict",
        "summary",
        "supporting_points",
        "counterarguments",
        "hidden_risks",
        "data_quality_warnings",
        "invalidation_conditions",
        "revision_requests",
        "confidence_label",
        "confidence_basis",
    ],
    "additionalProperties": False,
}
