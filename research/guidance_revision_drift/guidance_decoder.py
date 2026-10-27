"""Offline single-record Massive/Benzinga guidance semantic decoder.

The hash-bound sidecar supplies normalized semantics, units, identity mapping,
and clocks as unverified assertions. Matching provider fields establishes local
consistency only, never origin, rights, completeness, or historical availability.
No provider, file, environment, account, or native-engine access occurs here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

from data.financial_primitives import exact_decimal_multiply
from data.hashing import hash_bytes
from research.guidance_revision_drift.guidance_inputs import (
    GuidanceDocument, GuidanceReceipt, MAX_RAW_BYTES,
)
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, day, decode_object, digest, identifier,
    keys, utc,
)

CONTEXT_SCHEMA = "gdr.guidance-semantic-context.v1"
PROVIDER = "massive_benzinga"
MAX_CONTEXT_BYTES = 73_728
_CONTEXT_FIELDS = frozenset({
    "schema", "source_payload_sha256", "ticker", "document", "received_at",
    "validated_at", "announcement_timezone", "revenue_input_units",
    "eps_input_units", "revenue_kind", "eps_kind",
})
_REQUIRED_FIELDS = frozenset({
    "benzinga_id", "ticker", "date", "time", "currency", "eps_method",
    "revenue_method", "fiscal_period", "fiscal_year", "max_eps_guidance",
    "min_eps_guidance", "max_revenue_guidance", "min_revenue_guidance",
    "release_type", "positioning",
})
_OPTIONAL_FIELDS = frozenset({
    "last_updated", "company_name", "notes", "importance",
    "estimated_eps_guidance", "estimated_revenue_guidance",
    "previous_max_eps_guidance", "previous_max_revenue_guidance",
    "previous_min_eps_guidance", "previous_min_revenue_guidance",
})
_NUMBER_FIELDS = frozenset(name for name in _REQUIRED_FIELDS | _OPTIONAL_FIELDS
                           if name.endswith("_guidance"))


class GuidanceDecoderError(InputError):
    """Static local-consistency refusal that never echoes source content."""


def _refuse(reason: str) -> None:
    raise GuidanceDecoderError(reason)


def _number(value: object) -> Decimal:
    if type(value) not in (int, Decimal):
        _refuse("provider_exact_numeric_token_required")
    # Zero/negative guidance must remain observable as the immediate prior;
    # comparison, rather than decoding, owns economic floors and refusals.
    return amount(value)


def _publication_clock(values: dict, supplied: dict, document: dict) -> None:
    zone_name = supplied["announcement_timezone"]
    if zone_name not in ("UTC", "America/New_York"):
        _refuse("explicit_supported_announcement_timezone_required")
    source_day = day(values["date"])
    if (type(values["time"]) is not str
            or re.fullmatch(r"[0-9]{2}:[0-9]{2}:[0-9]{2}", values["time"]) is None):
        _refuse("explicit_provider_publication_time_required")
    try:
        naive = datetime.fromisoformat(source_day.isoformat() + "T" + values["time"])
    except ValueError:
        raise GuidanceDecoderError("invalid_provider_publication_time") from None
    zone = ZoneInfo(zone_name)
    # A sidecar's UTC instant cannot silently choose one occurrence of an
    # ambiguous local clock. Round trips also reject nonexistent spring clocks.
    candidates = set()
    for fold in (0, 1):
        instant = naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if instant.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(instant)
    if len(candidates) != 1:
        _refuse("ambiguous_or_nonexistent_provider_publication_clock")
    if next(iter(candidates)) != utc(document["published_at"]):
        _refuse("provider_publication_clock_context_mismatch")
    if "last_updated" in values:
        updated = utc(values["last_updated"])
        if not utc(document["published_at"]) <= updated <= utc(supplied["received_at"]):
            _refuse("provider_update_clock_inconsistent_with_receipt")


def _optional_fields(values: dict) -> None:
    for name in ("company_name", "notes"):
        if name in values and (type(values[name]) is not str or not values[name]
                               or len(values[name]) > 4096
                               or any(ord(char) < 32 for char in values[name])):
            _refuse("bounded_provider_text_required")
    if "importance" in values and (type(values["importance"]) is not int
                                    or not 0 <= values["importance"] <= 5):
        _refuse("bounded_provider_importance_required")
    # Estimates and previous values are checked for structure only. They are
    # neither predecessor captures nor filters, rankings, or positive signals.
    for name in _NUMBER_FIELDS & set(values):
        _number(values[name])
    for metric in ("revenue", "eps"):
        lower, upper = (f"previous_{side}_{metric}_guidance" for side in ("min", "max"))
        if (lower in values) != (upper in values):
            _refuse("incomplete_provider_previous_range")
        if lower in values and amount(values[lower]) > amount(values[upper]):
            _refuse("inverted_provider_previous_range")


def _crosscheck(values: dict, supplied: dict, document: dict) -> None:
    if not _REQUIRED_FIELDS <= set(values) or not set(values) <= _REQUIRED_FIELDS | _OPTIONAL_FIELDS:
        _refuse("provider_missing_or_unknown_fields")
    identifier(values["benzinga_id"])
    identifier(values["ticker"])
    if (values["benzinga_id"] != document["disclosure_id"]
            or values["ticker"] != supplied["ticker"]):
        _refuse("provider_identity_context_mismatch")
    _publication_clock(values, supplied, document)
    _optional_fields(values)
    period = document["periods"][0]
    if (values["fiscal_period"] != "FY" or type(values["fiscal_year"]) is not int
            or values["fiscal_year"] != period["fiscal_year"]):
        _refuse("provider_fiscal_period_context_mismatch")
    if values["currency"] != period["currency"]:
        _refuse("provider_currency_context_mismatch")
    for source, normalized, allowed in (("revenue_method", "revenue_basis", ("gaap", "adj")),
                                        ("eps_method", "eps_basis", ("gaap", "adj", "ffo"))):
        if values[source] not in allowed:
            _refuse("unrecognized_provider_accounting_method")
        if values[source] != period[normalized]:
            _refuse("provider_accounting_context_mismatch")
    for name in ("release_type", "positioning"):
        if values[name] != document[name]:
            _refuse("provider_release_context_mismatch")
    for metric in ("revenue", "eps"):
        bounds = [_number(values[f"{side}_{metric}_guidance"])
                  for side in ("min", "max")]
        if bounds[0] > bounds[1]:
            _refuse("inverted_provider_current_range")
        kind = supplied[f"{metric}_kind"]
        if ((bounds[0] == bounds[1]) != (kind == "point")
                or period[metric]["kind"] != kind):
            _refuse("provider_range_kind_context_mismatch")
        if metric == "revenue":
            # Convert both explicit unit systems to USD without division or
            # ambient decimal rounding; preserve the supplied document units.
            source_scale = Decimal("1000000") if supplied["revenue_input_units"] == "USD_millions" else Decimal("1")
            document_scale = Decimal("1000000") if period["revenue_units"] == "USD_millions" else Decimal("1")
        else:
            source_scale = document_scale = Decimal("1")
        for index, side in enumerate(("lower", "upper")):
            if (exact_decimal_multiply(bounds[index], source_scale)
                    != exact_decimal_multiply(amount(period[metric][side]), document_scale)):
                _refuse("provider_current_range_context_mismatch")


def decode_guidance(raw: bytes, semantic_context_bytes: bytes, *,
                    expected_context_sha256: str) -> GuidanceReceipt:
    """Return a retained receipt only after hash and known-field crosschecks.

    The caller must separately retain the context/hash. This return value adds
    no provenance attestation. Unsupported mutation/version/availability claims
    refuse because this raw schema has no field that can corroborate them.
    """
    try:
        digest(expected_context_sha256)
        if (type(semantic_context_bytes) is not bytes or not semantic_context_bytes
                or len(semantic_context_bytes) > MAX_CONTEXT_BYTES):
            _refuse("bounded_semantic_context_bytes_required")
        if hash_bytes(semantic_context_bytes) != expected_context_sha256:
            _refuse("semantic_context_content_hash_mismatch")
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_RAW_BYTES:
            _refuse("bounded_raw_guidance_bytes_required")
        raw_sha256 = hash_bytes(raw)
        supplied = keys(decode_object(semantic_context_bytes, MAX_CONTEXT_BYTES), set(_CONTEXT_FIELDS))
        if supplied["schema"] != CONTEXT_SCHEMA or canonical_bytes(supplied) != semantic_context_bytes:
            _refuse("canonical_guidance_semantic_context_required")
        if digest(supplied["source_payload_sha256"]) != raw_sha256:
            _refuse("semantic_context_source_hash_mismatch")
        identifier(supplied["ticker"])
        if (supplied["revenue_input_units"] not in ("USD", "USD_millions")
                or supplied["eps_input_units"] != "USD_per_share"):
            _refuse("explicit_supported_input_units_required")
        if any(supplied[name] not in ("point", "range") for name in ("revenue_kind", "eps_kind")):
            _refuse("explicit_point_or_range_context_required")
        document = GuidanceDocument.from_dict(supplied["document"])
        normalized = document.to_dict()
        if normalized["source_payload_sha256"] != raw_sha256:
            _refuse("normalized_document_source_hash_mismatch")
        if normalized["provider"] != PROVIDER:
            _refuse("massive_benzinga_provider_required")
        if (normalized["kind"] != "disclosure" or normalized["supersedes"] is not None
                or normalized["provider_version"] is not None
                or normalized["provider_available_at"] is not None):
            _refuse("provider_schema_cannot_verify_mutation_version_or_availability")
        if len(normalized["periods"]) != 1:
            _refuse("single_full_year_provider_period_required")
        # Known nonbaseline bases remain in the ledger as immediate priors.
        # Comparison owns eligibility; dropping one here could select an older,
        # apparently comparable disclosure and fabricate a positive revision.
        # Validate asserted receipt clocks before parsing provider content.
        receipt = GuidanceReceipt(raw, document, supplied["received_at"], supplied["validated_at"])
        _crosscheck(decode_object(raw, MAX_RAW_BYTES, provider_numbers=True), supplied, normalized)
        return receipt
    except GuidanceDecoderError:
        raise
    except (InputError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise GuidanceDecoderError("invalid_guidance_semantic_input") from None
