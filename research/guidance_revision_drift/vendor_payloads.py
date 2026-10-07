"""Invented Massive/Benzinga-shaped records, with explicit missing semantics.

Public field reference (read 2026-10-07):
https://massive.com/docs/rest/partners/benzinga/corporate-guidance

This is a single-record, synthetic-only decoder, not an API client. The public
schema supplies neither units, publication timezone, immutable receipt,
provider version nor correction/withdrawal semantics. A separate synthetic
context must supply each; its assertions are NOT verified source evidence.
Vendor previous_* fields are retained, never used as captured predecessors.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from data.financial_primitives import exact_decimal_multiply
from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.events import (
    EventError, NormalizedDisclosure, _date, _identifier, _text, _utc,
    decode_fixture_object,
)
from research.guidance_revision_drift.formulas import GuidanceRange, _bounded_decimal

MAX_PAYLOAD_BYTES = 32_768
MAX_CONTEXT_BYTES = 8_192
PUBLIC_SCHEMA_URL = "https://massive.com/docs/rest/partners/benzinga/corporate-guidance"
_CONTEXT_KEYS = frozenset((
    "schema", "provider_id", "ticker", "issuer_id", "security_id", "version",
    "kind", "supersedes", "published_at", "received_at", "validated_at",
    "announcement_timezone", "fiscal_start", "fiscal_end", "fiscal_year",
    "revenue_input_units", "eps_input_units", "revenue_basis", "eps_basis",
    "adjustment_definition", "share_basis", "scope", "revenue_kind", "eps_kind",
    "release_type", "positioning",
))
_IDENTITY_FIELDS = frozenset(("benzinga_id", "ticker", "date", "time", "last_updated"))
_ECONOMIC_FIELDS = frozenset((
    "currency", "eps_method", "revenue_method", "fiscal_period", "fiscal_year",
    "max_eps_guidance", "max_revenue_guidance", "min_eps_guidance",
    "min_revenue_guidance", "release_type", "positioning",
))
_OPTIONAL_FIELDS = frozenset((
    "company_name", "notes", "importance", "estimated_eps_guidance",
    "estimated_revenue_guidance", "previous_max_eps_guidance",
    "previous_max_revenue_guidance", "previous_min_eps_guidance",
    "previous_min_revenue_guidance",
))
_NUMBER_FIELDS = frozenset(name for name in _ECONOMIC_FIELDS | _OPTIONAL_FIELDS
                           if name.endswith("_guidance"))


class VendorPayloadError(ValueError):
    """A named synthetic parser refusal; no source or access authorization."""


def _refuse(reason: str) -> None:
    raise VendorPayloadError(reason)


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            _refuse("duplicate_provider_field")
        result[name] = value
    return result


def _number(value: object) -> Decimal:
    if type(value) not in (int, Decimal):
        _refuse("provider_number_required")
    try:
        return _bounded_decimal(Decimal(value), "provider number")
    except ValueError as exc:
        raise VendorPayloadError("provider_number_out_of_bounds") from exc


def _decimal_token(value: str) -> Decimal:
    # Reject excessive literals before constructing them. JSON decimal numbers
    # become Decimal directly: binary floats never enter the money path.
    if len(value) > 260:
        _refuse("provider_number_out_of_bounds")
    return _number(Decimal(value))


def _integer_token(value: str) -> int:
    if len(value) > 128:
        _refuse("provider_integer_out_of_bounds")
    return int(value)


def _nonfinite(_: str) -> None:
    _refuse("provider_nonfinite_number")


def _decode(raw: bytes) -> dict:
    if type(raw) is not bytes or not raw or len(raw) > MAX_PAYLOAD_BYTES:
        _refuse("provider_payload_must_be_bounded_bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                           parse_float=_decimal_token, parse_int=_integer_token,
                           parse_constant=_nonfinite)
    except VendorPayloadError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise VendorPayloadError("provider_payload_invalid_json") from exc
    if type(value) is not dict:
        _refuse("provider_payload_must_be_one_record")
    return value


@dataclass(frozen=True, slots=True)
class SyntheticGuidanceContext:
    """Explicit invented assertions, stored as detached canonical JSON bytes."""

    canonical_bytes: bytes

    def __post_init__(self) -> None:
        try:
            values = decode_fixture_object(self.canonical_bytes, MAX_CONTEXT_BYTES)
            if set(values) != _CONTEXT_KEYS or canonical_json(values).encode() != self.canonical_bytes:
                _refuse("context_fields_or_canonical_bytes")
            if values["schema"] != "gdr.synthetic.vendor-context.v1":
                _refuse("synthetic_context_required")
            for name in ("provider_id", "ticker", "issuer_id", "security_id"):
                _identifier(values[name])
            if type(values["version"]) is not int or not 1 <= values["version"] <= 256:
                _refuse("explicit_bounded_version_required")
            if values["kind"] not in ("disclosure", "correction", "withdrawal"):
                _refuse("explicit_event_kind_required")
            if values["kind"] == "disclosure":
                if values["supersedes"] is not None:
                    _refuse("disclosure_cannot_supersede")
            else:
                _identifier(values["supersedes"])
            clocks = [_utc(values[name]) for name in ("published_at", "received_at", "validated_at")]
            if any(clock.year not in (2024, 2025) for clock in clocks) or not clocks[0] <= clocks[1] <= clocks[2]:
                _refuse("synthetic_clocks_order_or_year")
            if values["announcement_timezone"] not in ("UTC", "America/New_York"):
                _refuse("explicit_supported_publication_timezone_required")
            start, end = _date(values["fiscal_start"]), _date(values["fiscal_end"])
            if (start.year not in (2024, 2025) or end.year not in (2024, 2025)
                    or not 300 <= (end - start).days <= 400
                    or type(values["fiscal_year"]) is not int
                    or values["fiscal_year"] != end.year):
                _refuse("explicit_supported_full_year_required")
            if values["revenue_input_units"] not in ("USD", "USD_millions"):
                _refuse("explicit_revenue_units_required")
            if values["eps_input_units"] != "USD_per_share":
                _refuse("explicit_eps_units_required")
            if values["revenue_basis"] != "gaap" or values["eps_basis"] != "adj":
                _refuse("unsupported_accounting_basis")
            for name in ("adjustment_definition", "share_basis", "scope"):
                _identifier(values[name])
            for name in ("revenue_kind", "eps_kind"):
                if values[name] not in ("point", "range"):
                    _refuse("explicit_range_kind_required")
            if values["release_type"] not in ("official", "preliminary") or values["positioning"] not in ("primary", "secondary"):
                _refuse("explicit_release_or_positioning_required")
        except EventError as exc:
            raise VendorPayloadError("malformed_synthetic_context") from exc

    @classmethod
    def from_dict(cls, values: dict) -> SyntheticGuidanceContext:
        if type(values) is not dict:
            _refuse("context_must_be_object")
        try:
            return cls(canonical_json(values).encode("utf-8"))
        except VendorPayloadError:
            raise
        except (ValueError, TypeError, RecursionError) as exc:
            raise VendorPayloadError("invalid_context_values") from exc

    def to_dict(self) -> dict:
        return decode_fixture_object(self.canonical_bytes, MAX_CONTEXT_BYTES)

    @property
    def sha256(self) -> str:
        return hash_bytes(self.canonical_bytes)


def _normalize(raw: bytes, context: SyntheticGuidanceContext) -> NormalizedDisclosure:
    values, supplied = _decode(raw), context.to_dict()
    withdrawal = supplied["kind"] == "withdrawal"
    required = _IDENTITY_FIELDS if withdrawal else _IDENTITY_FIELDS | _ECONOMIC_FIELDS
    allowed = required | (_OPTIONAL_FIELDS if not withdrawal else frozenset(("notes", "company_name")))
    if not required <= set(values) or not set(values) <= allowed:
        _refuse("provider_missing_or_unknown_fields")
    if values["benzinga_id"] != supplied["provider_id"] or values["ticker"] != supplied["ticker"]:
        _refuse("provider_identity_context_mismatch")
    try:
        _identifier(values["benzinga_id"])
        _identifier(values["ticker"])
        local = _utc(supplied["published_at"]).astimezone(ZoneInfo(supplied["announcement_timezone"]))
        if (local.date().isoformat() != values["date"]
                or local.strftime("%H:%M:%S") != values["time"]
                or local.microsecond):
            _refuse("provider_publication_clock_mismatch")
        updated = _utc(values["last_updated"])
        if not _utc(supplied["published_at"]) <= updated <= _utc(supplied["received_at"]):
            _refuse("provider_update_not_available_at_receipt")
        for name in ("notes", "company_name"):
            if name in values:
                _text(values[name], name, 4096)
        if "importance" in values and (type(values["importance"]) is not int or not 0 <= values["importance"] <= 5):
            _refuse("invalid_provider_importance")
        for name in _NUMBER_FIELDS & set(values):
            _number(values[name])
        for metric in ("revenue", "eps"):
            lower, upper = (f"previous_{side}_{metric}_guidance" for side in ("min", "max"))
            if (lower in values) != (upper in values):
                _refuse("incomplete_previous_range")
            if lower in values:
                GuidanceRange(_number(values[lower]), _number(values[upper]))
        periods = []
        if not withdrawal:
            if values["currency"] != "USD":
                _refuse("unsupported_provider_currency")
            if (values["fiscal_period"] != "FY" or type(values["fiscal_year"]) is not int
                    or values["fiscal_year"] != supplied["fiscal_year"]):
                _refuse("provider_full_year_context_mismatch")
            if values["revenue_method"] != supplied["revenue_basis"] or values["eps_method"] != supplied["eps_basis"]:
                _refuse("provider_basis_context_mismatch")
            if values["release_type"] != supplied["release_type"] or values["positioning"] != supplied["positioning"]:
                _refuse("provider_release_or_positioning_mismatch")
            period = {name: supplied[name] for name in (
                "fiscal_year", "fiscal_start", "fiscal_end", "revenue_basis", "eps_basis",
                "adjustment_definition", "share_basis", "scope",
            )}
            period.update(period="FY", currency="USD", revenue_units="USD_millions", eps_units="USD_per_share")
            for metric in ("revenue", "eps"):
                bounds = [_number(values[f"{side}_{metric}_guidance"]) for side in ("min", "max")]
                if metric == "revenue" and supplied["revenue_input_units"] == "USD":
                    bounds = [exact_decimal_multiply(value, Decimal("0.000001")) for value in bounds]
                GuidanceRange(*bounds)
                if (bounds[0] == bounds[1]) != (supplied[f"{metric}_kind"] == "point"):
                    _refuse("provider_range_kind_mismatch")
                period[metric] = {"lower": format(bounds[0], "f"), "upper": format(bounds[1], "f"),
                                  "kind": supplied[f"{metric}_kind"]}
            periods.append(period)
        semantic = {key: value for key, value in supplied.items() if key not in ("received_at", "validated_at")}
        return NormalizedDisclosure.from_dict({
            "schema": "gdr.synthetic.disclosure.v1", "issuer_id": supplied["issuer_id"],
            "disclosure_id": supplied["provider_id"], "version": supplied["version"],
            "kind": supplied["kind"], "supersedes": supplied["supersedes"],
            **{key: supplied[key] for key in ("published_at", "received_at", "validated_at")},
            "release_type": supplied["release_type"],
            "positioning": supplied["positioning"], "periods": periods,
            "metadata": "synthetic-unverified:raw=" + hash_bytes(raw) + ";context=" + hash_bytes(canonical_json(semantic).encode()),
        })
    except VendorPayloadError:
        raise
    except (EventError, ValueError, TypeError) as exc:
        raise VendorPayloadError("invalid_provider_semantics") from exc


@dataclass(frozen=True, slots=True)
class VendorObservation:
    """Raw bytes and explicit context, revalidated together at every boundary."""

    raw_bytes: bytes
    context: SyntheticGuidanceContext

    def __post_init__(self) -> None:
        if type(self.context) is not SyntheticGuidanceContext:
            _refuse("exact_synthetic_context_required")
        copied = SyntheticGuidanceContext(self.context.canonical_bytes)
        _normalize(self.raw_bytes, copied)
        object.__setattr__(self, "context", copied)

    @property
    def raw_sha256(self) -> str:
        return hash_bytes(self.raw_bytes)

    @property
    def sha256(self) -> str:
        checked = VendorObservation(self.raw_bytes, self.context)
        return hash_bytes(canonical_json({"raw": checked.raw_sha256, "context": checked.context.sha256}).encode())

    @property
    def delivery_content_sha256(self) -> str:
        checked = VendorObservation(self.raw_bytes, self.context)
        context = checked.context.to_dict()
        for name in ("received_at", "validated_at"):
            del context[name]
        return hash_bytes(canonical_json({"raw": checked.raw_sha256, "context": context}).encode())

    @property
    def disclosure(self) -> NormalizedDisclosure:
        checked = VendorObservation(self.raw_bytes, self.context)
        return _normalize(checked.raw_bytes, checked.context)

    @property
    def validated_at(self) -> datetime:
        return self.disclosure.validated_at


def parse_synthetic_guidance(raw: bytes, context: SyntheticGuidanceContext) -> VendorObservation:
    """Decode only invented SYN-* records; this function performs no I/O."""
    return VendorObservation(raw, context)
