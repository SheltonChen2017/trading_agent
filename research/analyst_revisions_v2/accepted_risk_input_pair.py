"""Pure accepted-risk Massive input-pair contract for ARV2-4F-C1.

The provider's historical REST rows are current-version rows: a later touch to
one Benzinga ID overwrites the earlier payload.  This module does not disguise
that limitation as point-in-time evidence.  It binds one caller-supplied,
immutable capture and derives two views from the *same* row bytes:

* ``current_row`` retains every structurally usable post-2012 row at the
  strategy's conservative date-only eligibility point; and
* ``conservative_censored`` retains the same payload only when its recorded
  ``last_updated`` value is conservatively no later than that eligibility
  cutoff.

No earlier value is invented for a censored row.  Both views are explicitly
non-pristine-PIT.  Guidance never relies on its unresolved intraday timezone:
it enters only on the third NYSE session strictly after the event date, and its
conservative-censored arm uses an explicit-offset ``last_updated`` instant when
available and otherwise requires its calendar date to precede that delayed
session.  This module performs no provider, credential, filesystem,
QuantConnect, Object Store, market-data, outcome, deployment, order, or trade
access and grants none of those capabilities.
"""
from __future__ import annotations

import dataclasses
import re
import threading
import weakref
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import Any

from .availability import (
    AvailabilityError,
    derive_event_availability,
    resolve_delayed_date_only_session_open,
)
from .canonical import (
    CanonicalEvidenceError,
    capture_frozen_container_authority,
    canonical_json_bytes,
    decode_utf8,
    format_utc_timestamp,
    frozen_container_authority_is_current,
    parse_date,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_exact_bool,
    require_exact_keys,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    sha256_bytes,
    strict_json_loads,
)


CAPTURE_PAGE_SCHEMA = "arv2-accepted-risk-capture-page-v1"
CAPTURE_QUERY_SCHEMA = "arv2-accepted-risk-redacted-query-v1"
CAPTURE_SCHEMA = "arv2-accepted-risk-massive-capture-v1"
INPUT_PAIR_CONTRACT_SCHEMA = "arv2-accepted-risk-input-pair-contract-v1"
INPUT_PAIR_CONTRACT_ID = "arv2-4f-c1-accepted-risk-input-pair-v1"
INPUT_PAIR_SCHEMA = "arv2-accepted-risk-input-pair-v1"
INPUT_PAIR_REPORT_SCHEMA = "arv2-accepted-risk-input-pair-report-v1"
OWNER_DECISION_ID = "arv2-owner-accepted-massive-current-row-risk-20260911"
CURRENT_VIEW_LABEL = "current_row_current_vintage_non_pristine_pit"
CENSORED_VIEW_LABEL = "conservative_censored_current_vintage_non_pristine_pit"
MINIMUM_ADMISSIBLE_EVENT_DATE = date(2013, 1, 1)
MAX_CAPTURE_PAGE_BYTES = 64 * 1024 * 1024
MAX_PROVIDER_ROWS_PER_PAGE = 50_000
MAX_PROVIDER_JSON_DEPTH = 32
GUIDANCE_CONSERVATIVE_SESSION_LAG = 3

_QUERY_KEYS = frozenset(
    {
        "schema",
        "source_role",
        "requested_first_event_date",
        "requested_last_event_date",
        "sort_field",
        "sort_order",
        "limit",
        "last_updated_filter_applied",
        "credential_material_included",
        "cursor_material_included",
    }
)
_RAW_TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d")
_EXPLICIT_OFFSET_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d{1,6})?(?:Z|[+-](?:0\d|1\d|2[0-3]):[0-5]\d)"
)
_GUIDANCE_LAST_UPDATED_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})(?:[T ](?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d{1,6})?(?:Z|[+-](?:0\d|1\d|2[0-3]):[0-5]\d)?)?"
)
_ROLE_ORDER: tuple["MassiveSourceRole", ...]


class AcceptedRiskInputError(CanonicalEvidenceError):
    """The capture or derived accepted-risk input pair is not authoritative."""


class MassiveSourceRole(str, Enum):
    ANALYST_RATINGS = "analyst_ratings"
    EARNINGS = "earnings"
    CORPORATE_GUIDANCE = "corporate_guidance"


_ROLE_ORDER = (
    MassiveSourceRole.ANALYST_RATINGS,
    MassiveSourceRole.EARNINGS,
    MassiveSourceRole.CORPORATE_GUIDANCE,
)

_ENDPOINT_IDENTIFIERS = MappingProxyType({
    MassiveSourceRole.ANALYST_RATINGS: "massive_benzinga_analyst_ratings_rest",
    MassiveSourceRole.EARNINGS: "massive_benzinga_earnings_rest",
    MassiveSourceRole.CORPORATE_GUIDANCE: "massive_benzinga_corporate_guidance_rest",
})

_CLOCK_INTERPRETATIONS = MappingProxyType({
    MassiveSourceRole.ANALYST_RATINGS: (
        "documented_utc_time_audit_only_date_only_two_session_eligibility"
    ),
    MassiveSourceRole.EARNINGS: (
        "literal_est_time_audit_only_no_dst_inference_date_only_two_session_eligibility"
    ),
    MassiveSourceRole.CORPORATE_GUIDANCE: (
        "unresolved_intraday_timezones_date_only_three_session_lag_and_"
        "exact_offset_or_prior_calendar_date_censoring"
    ),
})


class InputView(str, Enum):
    CURRENT_ROW = "current_row"
    CONSERVATIVE_CENSORED = "conservative_censored"


class RowDisposition(str, Enum):
    INCLUDED_CURRENT_ROW_NON_PRISTINE = "included_current_row_non_pristine"
    INCLUDED_CONSERVATIVE_CENSORED_NON_PRISTINE = (
        "included_conservative_censored_non_pristine"
    )
    INVALID_PROVIDER_EVENT_ID = "invalid_provider_event_id"
    INVALID_EVENT_DATE = "invalid_event_date"
    INVALID_EVENT_TIME = "invalid_event_time"
    EVENT_OUTSIDE_REQUESTED_CAPTURE_RANGE = "event_outside_requested_capture_range"
    EVENT_OUTSIDE_EXCHANGE_CALENDAR_AUTHORITY = (
        "event_outside_exchange_calendar_authority"
    )
    PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013 = (
        "provider_backfill_semantics_unverified_pre_2013"
    )
    INVALID_LAST_UPDATED_EXPLICIT_OFFSET = "invalid_last_updated_explicit_offset"
    LAST_UPDATED_AFTER_CAPTURE = "last_updated_after_capture"
    CENSORED_LAST_TOUCH_AFTER_DECISION_CUTOFF = (
        "censored_last_touch_after_decision_cutoff"
    )


class BreakdownDimension(str, Enum):
    OVERALL = "overall"
    EVENT_YEAR = "event_year"
    SOURCE_ROLE = "source_role"
    ACTION = "action"
    FIRM = "firm"
    SECURITY_LABEL = "security_label"


def accepted_risk_input_pair_contract_record() -> dict[str, Any]:
    """Return the static, content-addressed C1 contract."""
    return {
        "schema": INPUT_PAIR_CONTRACT_SCHEMA,
        "contract_id": INPUT_PAIR_CONTRACT_ID,
        "owner_decision_id": OWNER_DECISION_ID,
        "source_roles": [role.value for role in _ROLE_ORDER],
        "endpoint_identifiers": {
            role.value: _ENDPOINT_IDENTIFIERS[role] for role in _ROLE_ORDER
        },
        "capture": {
            "source": "one_caller_supplied_immutable_capture",
            "page_content": "exact_lf_terminated_strict_jsonl_provider_rows",
            "lineage": [
                "redacted_base_query_sha256",
                "request_cursor_sha256",
                "next_cursor_sha256",
                "raw_response_sha256_and_optional_exact_bytes",
                "provider_rows_sha256",
                "page_and_row_counts",
                "utc_receipt_instants",
            ],
            "last_updated_filter_applied": False,
            "transactional_snapshot": False,
            "complete_version_history": False,
            "complete_deletion_tombstones": False,
            "raw_response_extraction": (
                "verified_only_when_exact_response_bytes_are_bound_and_results_"
                "deterministically_match_provider_jsonl_otherwise_explicitly_unverified"
            ),
        },
        "views": {
            InputView.CURRENT_ROW.value: {
                "label": CURRENT_VIEW_LABEL,
                "rule": "post_2012_current_payload_after_date_only_two_session_eligibility",
            },
            InputView.CONSERVATIVE_CENSORED.value: {
                "label": CENSORED_VIEW_LABEL,
                "rule": (
                    "same_payload_only_when_explicit_offset_last_updated_is_not_after_"
                    "the_date_only_two_session_decision_cutoff"
                ),
            },
        },
        "clock_interpretations": {
            role.value: _CLOCK_INTERPRETATIONS[role] for role in _ROLE_ORDER
        },
        "pre_2013_policy": (
            RowDisposition.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013.value
        ),
        "guidance_policy": {
            "intraday_timezone_authenticated": False,
            "event_eligibility": (
                "third_NYSE_session_strictly_after_provider_event_date"
            ),
            "censored_last_touch_rule": (
                "explicit_offset_provider_last_updated_not_after_delayed_open_"
                "otherwise_calendar_date_strictly_precedes_delayed_session"
            ),
            "session_lag": GUIDANCE_CONSERVATIVE_SESSION_LAG,
            "earlier_version_imputation_performed": False,
        },
        "duplicate_provider_id_policy": "refuse_entire_three_role_capture",
        "ticker_policy": "current_restated_label_only_not_security_identity",
        "earlier_version_imputation_performed": False,
        "pristine_point_in_time": False,
        "reporting_dimensions": [dimension.value for dimension in BreakdownDimension],
        "mapping_disagreement_report": None,
        "signal_disagreement_report": None,
        "all_external_and_outcome_capabilities": False,
    }


def render_accepted_risk_input_pair_contract_bytes() -> bytes:
    return canonical_json_bytes(accepted_risk_input_pair_contract_record())


INPUT_PAIR_CONTRACT_SHA256 = sha256_bytes(
    render_accepted_risk_input_pair_contract_bytes()
)

_PINNED_INPUT_PAIR_CONTRACT_SHA256 = INPUT_PAIR_CONTRACT_SHA256
_PINNED_ACCEPTED_RISK_CONTRACT_RECORD = accepted_risk_input_pair_contract_record
_PINNED_RENDER_ACCEPTED_RISK_CONTRACT = (
    render_accepted_risk_input_pair_contract_bytes
)
_PINNED_DERIVE_EVENT_AVAILABILITY = derive_event_availability
_PINNED_RESOLVE_DELAYED_DATE_ONLY_SESSION_OPEN = (
    resolve_delayed_date_only_session_open
)
_PINNED_MINIMUM_ADMISSIBLE_EVENT_DATE = MINIMUM_ADMISSIBLE_EVENT_DATE
_PINNED_ROLE_ORDER = _ROLE_ORDER
_PINNED_STATIC_SCALARS = (
    CAPTURE_PAGE_SCHEMA,
    CAPTURE_QUERY_SCHEMA,
    CAPTURE_SCHEMA,
    INPUT_PAIR_CONTRACT_SCHEMA,
    INPUT_PAIR_CONTRACT_ID,
    INPUT_PAIR_SCHEMA,
    INPUT_PAIR_REPORT_SCHEMA,
    OWNER_DECISION_ID,
    CURRENT_VIEW_LABEL,
    CENSORED_VIEW_LABEL,
    MAX_CAPTURE_PAGE_BYTES,
    MAX_PROVIDER_ROWS_PER_PAGE,
    MAX_PROVIDER_JSON_DEPTH,
    GUIDANCE_CONSERVATIVE_SESSION_LAG,
)
_PINNED_QUERY_KEYS = _QUERY_KEYS
_PINNED_RAW_TIME_RE = _RAW_TIME_RE
_PINNED_EXPLICIT_OFFSET_RE = _EXPLICIT_OFFSET_RE
_PINNED_GUIDANCE_LAST_UPDATED_RE = _GUIDANCE_LAST_UPDATED_RE
_PINNED_ENUMS = (
    MassiveSourceRole,
    InputView,
    RowDisposition,
    BreakdownDimension,
)
_PINNED_ENUM_INVENTORIES = tuple(tuple(enum_type) for enum_type in _PINNED_ENUMS)
_PINNED_MAPPING_PROXY_TYPE = MappingProxyType
_PINNED_DECIMAL_TYPE = Decimal
_PINNED_ENDPOINT_IDENTIFIERS = tuple(
    (role, _ENDPOINT_IDENTIFIERS[role]) for role in _ROLE_ORDER
)
_PINNED_CLOCK_INTERPRETATIONS = tuple(
    (role, _CLOCK_INTERPRETATIONS[role]) for role in _ROLE_ORDER
)
_PINNED_CONTRACT_BYTES = render_accepted_risk_input_pair_contract_bytes()
_PINNED_IMPORTED_CALLABLES = (
    derive_event_availability,
    resolve_delayed_date_only_session_open,
    capture_frozen_container_authority,
    canonical_json_bytes,
    decode_utf8,
    format_utc_timestamp,
    frozen_container_authority_is_current,
    parse_date,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_exact_bool,
    require_exact_keys,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    sha256_bytes,
    strict_json_loads,
)


def _require_static_contract() -> None:
    current_imported_callables = (
        derive_event_availability,
        resolve_delayed_date_only_session_open,
        capture_frozen_container_authority,
        canonical_json_bytes,
        decode_utf8,
        format_utc_timestamp,
        frozen_container_authority_is_current,
        parse_date,
        parse_utc_timestamp,
        require_canonical_json_bytes,
        require_exact_bool,
        require_exact_keys,
        require_identifier,
        require_int,
        require_sha256,
        require_text,
        sha256_bytes,
        strict_json_loads,
    )
    current_static_scalars = (
        CAPTURE_PAGE_SCHEMA,
        CAPTURE_QUERY_SCHEMA,
        CAPTURE_SCHEMA,
        INPUT_PAIR_CONTRACT_SCHEMA,
        INPUT_PAIR_CONTRACT_ID,
        INPUT_PAIR_SCHEMA,
        INPUT_PAIR_REPORT_SCHEMA,
        OWNER_DECISION_ID,
        CURRENT_VIEW_LABEL,
        CENSORED_VIEW_LABEL,
        MAX_CAPTURE_PAGE_BYTES,
        MAX_PROVIDER_ROWS_PER_PAGE,
        MAX_PROVIDER_JSON_DEPTH,
        GUIDANCE_CONSERVATIVE_SESSION_LAG,
    )
    if (
        _require_static_contract is not _PINNED_REQUIRE_STATIC_CONTRACT
        or type(INPUT_PAIR_CONTRACT_SHA256) is not str
        or INPUT_PAIR_CONTRACT_SHA256 != _PINNED_INPUT_PAIR_CONTRACT_SHA256
        or type(MINIMUM_ADMISSIBLE_EVENT_DATE) is not date
        or MINIMUM_ADMISSIBLE_EVENT_DATE != _PINNED_MINIMUM_ADMISSIBLE_EVENT_DATE
        or type(GUIDANCE_CONSERVATIVE_SESSION_LAG) is not int
        or _ROLE_ORDER is not _PINNED_ROLE_ORDER
        or MappingProxyType is not _PINNED_MAPPING_PROXY_TYPE
        or Decimal is not _PINNED_DECIMAL_TYPE
        or type(_ENDPOINT_IDENTIFIERS) is not _PINNED_MAPPING_PROXY_TYPE
        or tuple((role, _ENDPOINT_IDENTIFIERS[role]) for role in _ROLE_ORDER)
        != _PINNED_ENDPOINT_IDENTIFIERS
        or type(_CLOCK_INTERPRETATIONS) is not _PINNED_MAPPING_PROXY_TYPE
        or tuple((role, _CLOCK_INTERPRETATIONS[role]) for role in _ROLE_ORDER)
        != _PINNED_CLOCK_INTERPRETATIONS
        or accepted_risk_input_pair_contract_record
        is not _PINNED_ACCEPTED_RISK_CONTRACT_RECORD
        or render_accepted_risk_input_pair_contract_bytes
        is not _PINNED_RENDER_ACCEPTED_RISK_CONTRACT
        or _PINNED_RENDER_ACCEPTED_RISK_CONTRACT()
        != _PINNED_CONTRACT_BYTES
        or any(
            type(current) is not type(expected) or current != expected
            for current, expected in zip(
                current_static_scalars, _PINNED_STATIC_SCALARS, strict=True
            )
        )
        or _QUERY_KEYS is not _PINNED_QUERY_KEYS
        or _RAW_TIME_RE is not _PINNED_RAW_TIME_RE
        or _EXPLICIT_OFFSET_RE is not _PINNED_EXPLICIT_OFFSET_RE
        or _GUIDANCE_LAST_UPDATED_RE is not _PINNED_GUIDANCE_LAST_UPDATED_RE
        or (
            MassiveSourceRole,
            InputView,
            RowDisposition,
            BreakdownDimension,
        )
        != _PINNED_ENUMS
        or any(
            tuple(enum_type) != inventory
            for enum_type, inventory in zip(
                _PINNED_ENUMS, _PINNED_ENUM_INVENTORIES, strict=True
            )
        )
        or len(current_imported_callables) != len(_PINNED_IMPORTED_CALLABLES)
        or any(
            current is not expected
            for current, expected in zip(
                current_imported_callables,
                _PINNED_IMPORTED_CALLABLES,
                strict=True,
            )
        )
        or _PINNED_DERIVE_EVENT_AVAILABILITY is not derive_event_availability
        or _PINNED_RESOLVE_DELAYED_DATE_ONLY_SESSION_OPEN
        is not resolve_delayed_date_only_session_open
        or _PINNED_CAPTURE_PAGE_POST_INIT is not CapturePageBinding.__post_init__
        or _PINNED_CAPTURE_MANIFEST_RECORD is not _capture_manifest_record
        or _PINNED_CAPTURE_FINGERPRINT is not _capture_fingerprint
        or _PINNED_VALIDATE_PAGE_SEQUENCE is not _validate_page_sequence
        or _PINNED_REFUSE_DUPLICATE_PROVIDER_IDS is not _refuse_duplicate_provider_ids
        or _PINNED_DERIVE_SOURCE_ROW is not _derive_source_row
        or _PINNED_DERIVE_ROWS is not _derive_rows
        or _PINNED_BUILD_REPORT is not _build_report
        or _PINNED_PAIR_SEMANTIC_RECORD is not _pair_semantic_record
        or _PINNED_PAIR_FINGERPRINT is not _pair_fingerprint
        or _PINNED_PAIR_CONTAINER_ROOTS is not _pair_container_roots
        or _PINNED_PREFLIGHT_PAIR_SCALAR_TYPES is not _preflight_pair_scalar_types
        or _current_local_callables is not _PINNED_CURRENT_LOCAL_CALLABLES
        or len(_PINNED_CURRENT_LOCAL_CALLABLES()) != len(_PINNED_LOCAL_CALLABLES)
        or any(
            current is not expected
            for current, expected in zip(
                _PINNED_CURRENT_LOCAL_CALLABLES(),
                _PINNED_LOCAL_CALLABLES,
                strict=True,
            )
        )
        or _current_record_types is not _PINNED_CURRENT_RECORD_TYPES
        or len(_PINNED_CURRENT_RECORD_TYPES()) != len(_PINNED_RECORD_TYPES)
        or any(
            current is not expected
            for current, expected in zip(
                _PINNED_CURRENT_RECORD_TYPES(),
                _PINNED_RECORD_TYPES,
                strict=True,
            )
        )
    ):
        raise AcceptedRiskInputError("accepted-risk static contract changed")


_PINNED_REQUIRE_STATIC_CONTRACT = _require_static_contract


def _require_exact_string(value: object, name: str) -> str:
    if type(value) is not str:
        raise AcceptedRiskInputError(f"{name} must be an exact string")
    return value


def _parse_raw_response_results(payload: bytes) -> tuple[dict[str, Any], ...]:
    """Return the exact ordered ``results`` objects from a captured REST body.

    The provider response itself is not canonicalized or rewritten.  This
    parser is used only to prove that caller-supplied JSONL rows are a complete,
    ordered extraction of the response's ``results`` array.
    """
    if type(payload) is not bytes:
        raise AcceptedRiskInputError("raw_response_bytes must be exact bytes")
    try:
        value = strict_json_loads(decode_utf8(payload, "raw provider response"), "raw provider response")
    except (CanonicalEvidenceError, RecursionError) as exc:
        raise AcceptedRiskInputError("raw provider response is not strict JSON") from exc
    if type(value) is not dict or type(value.get("results")) is not list:
        raise AcceptedRiskInputError(
            "raw provider response must contain one ordered results array"
        )
    results = value["results"]
    if any(type(item) is not dict for item in results):
        raise AcceptedRiskInputError("raw provider response results must be objects")
    return tuple(results)


def _json_value_fingerprint(value: object) -> object:
    """Preserve exact JSON scalar kinds and decimal lexeme significance."""
    if value is None:
        return ("null",)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if type(value) is str:
        return ("str", value)
    if type(value) is list:
        return ("list", tuple(_json_value_fingerprint(item) for item in value))
    if type(value) is dict:
        return (
            "object",
            tuple(
                (key, _json_value_fingerprint(item))
                for key, item in sorted(value.items())
            ),
        )
    # strict_json_loads represents every non-integral JSON number as Decimal.
    if type(value) is Decimal:
        return ("decimal", value.as_tuple())
    raise AcceptedRiskInputError("raw response contains an unsupported JSON scalar")


@dataclasses.dataclass(frozen=True)
class CapturePageBinding:
    """One redacted-query page and exact LF-terminated provider JSONL bytes."""

    schema: str
    source_role: MassiveSourceRole
    endpoint_identifier: str
    redacted_query_bytes: bytes
    redacted_query_sha256: str
    page_number: int
    request_cursor_sha256: str | None
    next_cursor_sha256: str | None
    terminal_page: bool
    response_received_at: str
    raw_response_sha256: str
    provider_rows_bytes: bytes
    provider_rows_sha256: str
    row_count: int
    raw_response_bytes: bytes | None = None

    def __post_init__(self) -> None:
        _PINNED_REQUIRE_STATIC_CONTRACT()
        _require_static_contract()
        for name in (
            "schema",
            "endpoint_identifier",
            "redacted_query_sha256",
            "response_received_at",
            "raw_response_sha256",
            "provider_rows_sha256",
        ):
            _require_exact_string(getattr(self, name), name)
        if type(self.redacted_query_bytes) is not bytes:
            raise AcceptedRiskInputError("redacted_query_bytes must be exact bytes")
        if type(self.provider_rows_bytes) is not bytes:
            raise AcceptedRiskInputError("provider_rows_bytes must be exact bytes")
        if self.schema != CAPTURE_PAGE_SCHEMA:
            raise AcceptedRiskInputError("wrong capture-page schema")
        if type(self.source_role) is not MassiveSourceRole:
            raise AcceptedRiskInputError("source_role must be an exact MassiveSourceRole")
        if self.endpoint_identifier != _ENDPOINT_IDENTIFIERS[self.source_role]:
            raise AcceptedRiskInputError("endpoint identifier does not match source role")
        _validate_redacted_query(self.redacted_query_bytes, self.source_role)
        require_sha256(self.redacted_query_sha256, "redacted_query_sha256")
        if sha256_bytes(self.redacted_query_bytes) != self.redacted_query_sha256:
            raise AcceptedRiskInputError("redacted query bytes/hash mismatch")
        require_int(self.page_number, "page_number", minimum=1)
        require_int(self.row_count, "row_count", minimum=0)
        for name in ("request_cursor_sha256", "next_cursor_sha256"):
            value = getattr(self, name)
            if value is not None:
                _require_exact_string(value, name)
                require_sha256(value, name)
        require_exact_bool(self.terminal_page, "terminal_page")
        if self.terminal_page != (self.next_cursor_sha256 is None):
            raise AcceptedRiskInputError(
                "terminal_page must agree exactly with next-cursor absence"
            )
        parse_utc_timestamp(self.response_received_at, "response_received_at")
        require_sha256(self.raw_response_sha256, "raw_response_sha256")
        require_sha256(self.provider_rows_sha256, "provider_rows_sha256")
        rows = _parse_provider_rows_bytes(self.provider_rows_bytes)
        if sha256_bytes(self.provider_rows_bytes) != self.provider_rows_sha256:
            raise AcceptedRiskInputError("provider row-page bytes/hash mismatch")
        if self.row_count != len(rows):
            raise AcceptedRiskInputError("capture page row_count is not exact")
        if self.raw_response_bytes is not None:
            if type(self.raw_response_bytes) is not bytes:
                raise AcceptedRiskInputError(
                    "raw_response_bytes must be exact bytes or null"
                )
            if sha256_bytes(self.raw_response_bytes) != self.raw_response_sha256:
                raise AcceptedRiskInputError("raw response bytes/hash mismatch")
            extracted = _parse_raw_response_results(self.raw_response_bytes)
            if tuple(_json_value_fingerprint(item) for item in extracted) != tuple(
                _json_value_fingerprint(row) for row, _ in rows
            ):
                raise AcceptedRiskInputError(
                    "provider JSONL is not the complete ordered raw-response extraction"
                )

    @property
    def parsed_rows(self) -> tuple[dict[str, Any], ...]:
        _PINNED_REQUIRE_STATIC_CONTRACT()
        _require_static_contract()
        return tuple(row for row, _ in _parse_provider_rows_bytes(self.provider_rows_bytes))

    @property
    def raw_rows(self) -> tuple[bytes, ...]:
        _PINNED_REQUIRE_STATIC_CONTRACT()
        _require_static_contract()
        return tuple(raw for _, raw in _parse_provider_rows_bytes(self.provider_rows_bytes))

    @property
    def raw_response_extraction_verified(self) -> bool:
        _PINNED_REQUIRE_STATIC_CONTRACT()
        _require_static_contract()
        return self.raw_response_bytes is not None

    def lineage_record(self) -> dict[str, Any]:
        _PINNED_REQUIRE_STATIC_CONTRACT()
        _require_static_contract()
        return {
            "schema": self.schema,
            "source_role": self.source_role.value,
            "endpoint_identifier": self.endpoint_identifier,
            "redacted_query_sha256": self.redacted_query_sha256,
            "page_number": self.page_number,
            "request_cursor_sha256": self.request_cursor_sha256,
            "next_cursor_sha256": self.next_cursor_sha256,
            "terminal_page": self.terminal_page,
            "response_received_at": self.response_received_at,
            "raw_response_sha256": self.raw_response_sha256,
            "raw_response_extraction_verified": (
                self.raw_response_extraction_verified
            ),
            "provider_rows_sha256": self.provider_rows_sha256,
            "row_count": self.row_count,
        }


_PINNED_CAPTURE_PAGE_POST_INIT = CapturePageBinding.__post_init__


def render_redacted_capture_query_bytes(
    *,
    source_role: MassiveSourceRole,
    requested_first_event_date: str,
    requested_last_event_date: str,
    limit: int = MAX_PROVIDER_ROWS_PER_PAGE,
) -> bytes:
    """Render the only query descriptor admitted by C1.

    It deliberately carries neither a credential nor cursor and deliberately
    applies no ``last_updated`` filter.  Therefore both input views must be
    derived from one complete current-row capture instead of two provider
    requests with different filters.
    """
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    if type(source_role) is not MassiveSourceRole:
        raise AcceptedRiskInputError("source_role must be an exact MassiveSourceRole")
    first = parse_date(requested_first_event_date, "requested_first_event_date")
    last = parse_date(requested_last_event_date, "requested_last_event_date")
    if first > last:
        raise AcceptedRiskInputError("requested event-date range is reversed")
    require_int(limit, "limit", minimum=1, maximum=MAX_PROVIDER_ROWS_PER_PAGE)
    return canonical_json_bytes(
        {
            "schema": CAPTURE_QUERY_SCHEMA,
            "source_role": source_role.value,
            "requested_first_event_date": first.isoformat(),
            "requested_last_event_date": last.isoformat(),
            "sort_field": "date",
            "sort_order": "asc",
            "limit": limit,
            "last_updated_filter_applied": False,
            "credential_material_included": False,
            "cursor_material_included": False,
        }
    )


def _validate_redacted_query(
    payload: bytes, source_role: MassiveSourceRole
) -> dict[str, Any]:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    if type(payload) is not bytes:
        raise AcceptedRiskInputError("redacted capture query must be exact bytes")
    if type(source_role) is not MassiveSourceRole:
        raise AcceptedRiskInputError("query source role has the wrong type")
    value = require_canonical_json_bytes(payload, "redacted capture query")
    if not isinstance(value, dict):
        raise AcceptedRiskInputError("redacted capture query must be an object")
    require_exact_keys(value, _QUERY_KEYS, "redacted capture query")
    if value["schema"] != CAPTURE_QUERY_SCHEMA:
        raise AcceptedRiskInputError("wrong redacted capture-query schema")
    if value["source_role"] != source_role.value:
        raise AcceptedRiskInputError("query source role does not match page source role")
    first = parse_date(value["requested_first_event_date"], "query first date")
    last = parse_date(value["requested_last_event_date"], "query last date")
    if first > last:
        raise AcceptedRiskInputError("query event-date range is reversed")
    if value["sort_field"] != "date" or value["sort_order"] != "asc":
        raise AcceptedRiskInputError("capture query must use deterministic date ascending order")
    require_int(value["limit"], "query limit", minimum=1, maximum=MAX_PROVIDER_ROWS_PER_PAGE)
    for key in (
        "last_updated_filter_applied",
        "credential_material_included",
        "cursor_material_included",
    ):
        require_exact_bool(value[key], key)
        if value[key] is not False:
            raise AcceptedRiskInputError(f"{key} must remain literal false")
    return value


def _parse_provider_rows_bytes(
    payload: bytes,
) -> tuple[tuple[dict[str, Any], bytes], ...]:
    if type(payload) is not bytes:
        raise AcceptedRiskInputError("provider_rows_bytes must be exact bytes")
    if len(payload) > MAX_CAPTURE_PAGE_BYTES:
        raise AcceptedRiskInputError("provider row page exceeds the C1 byte limit")
    if payload and (not payload.endswith(b"\n") or b"\r" in payload):
        raise AcceptedRiskInputError(
            "provider row page must use LF-terminated JSONL"
        )
    raw_rows = () if not payload else tuple(payload[:-1].split(b"\n"))
    if any(not raw for raw in raw_rows):
        raise AcceptedRiskInputError("provider row page contains a blank JSONL row")
    if len(raw_rows) > MAX_PROVIDER_ROWS_PER_PAGE:
        raise AcceptedRiskInputError("provider row page exceeds 50,000 rows")
    parsed: list[tuple[dict[str, Any], bytes]] = []
    for offset, raw in enumerate(raw_rows):
        try:
            text = decode_utf8(raw, f"provider row page:{offset}")
            value = strict_json_loads(text, f"provider row page:{offset}")
        except RecursionError as exc:
            raise AcceptedRiskInputError(
                "provider row exceeds the JSON nesting bound"
            ) from exc
        if not isinstance(value, dict):
            raise AcceptedRiskInputError("every provider row must be a JSON object")
        pending: list[tuple[object, int]] = [(value, 1)]
        while pending:
            child, depth = pending.pop()
            if depth > MAX_PROVIDER_JSON_DEPTH:
                raise AcceptedRiskInputError(
                    "provider row exceeds the JSON nesting bound"
                )
            if type(child) is dict:
                pending.extend((item, depth + 1) for item in child.values())
            elif type(child) is list:
                pending.extend((item, depth + 1) for item in child)
        parsed.append((value, raw + b"\n"))
    return tuple(parsed)


def bind_capture_page(
    *,
    source_role: MassiveSourceRole,
    redacted_query_bytes: bytes,
    page_number: int,
    request_cursor_sha256: str | None,
    next_cursor_sha256: str | None,
    terminal_page: bool,
    response_received_at: str,
    raw_response_sha256: str,
    provider_rows_bytes: bytes,
    raw_response_bytes: bytes | None = None,
) -> CapturePageBinding:
    """Bind one already-captured page without performing any I/O."""
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    if type(source_role) is not MassiveSourceRole:
        raise AcceptedRiskInputError("source_role must be an exact MassiveSourceRole")
    if type(redacted_query_bytes) is not bytes or type(provider_rows_bytes) is not bytes:
        raise AcceptedRiskInputError("capture page byte inputs must be exact bytes")
    rows = _parse_provider_rows_bytes(provider_rows_bytes)
    return CapturePageBinding(
        schema=CAPTURE_PAGE_SCHEMA,
        source_role=source_role,
        endpoint_identifier=_ENDPOINT_IDENTIFIERS[source_role],
        redacted_query_bytes=redacted_query_bytes,
        redacted_query_sha256=sha256_bytes(redacted_query_bytes),
        page_number=page_number,
        request_cursor_sha256=request_cursor_sha256,
        next_cursor_sha256=next_cursor_sha256,
        terminal_page=terminal_page,
        response_received_at=response_received_at,
        raw_response_sha256=raw_response_sha256,
        provider_rows_bytes=provider_rows_bytes,
        provider_rows_sha256=sha256_bytes(provider_rows_bytes),
        row_count=len(rows),
        raw_response_bytes=raw_response_bytes,
    )


@dataclasses.dataclass(frozen=True)
class CaptureRowLocator:
    capture_id: str
    source_role: MassiveSourceRole
    page_number: int
    provider_rows_sha256: str
    row_offset: int
    raw_row_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.capture_id, "capture_id")
        if type(self.source_role) is not MassiveSourceRole:
            raise AcceptedRiskInputError("locator source_role has the wrong type")
        require_int(self.page_number, "page_number", minimum=1)
        require_sha256(self.provider_rows_sha256, "provider_rows_sha256")
        require_int(self.row_offset, "row_offset", minimum=0)
        require_sha256(self.raw_row_sha256, "raw_row_sha256")

    @property
    def sort_key(self) -> tuple[int, int, int]:
        return (_ROLE_ORDER.index(self.source_role), self.page_number, self.row_offset)

    def to_record(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "source_role": self.source_role.value,
            "page_number": self.page_number,
            "provider_rows_sha256": self.provider_rows_sha256,
            "row_offset": self.row_offset,
            "raw_row_sha256": self.raw_row_sha256,
        }


@dataclasses.dataclass(frozen=True, init=False)
class CaptureBinding:
    schema: str
    contract_id: str
    contract_sha256: str
    capture_id: str
    capture_sha256: str
    capture_started_at: str
    capture_completed_at: str
    requested_first_event_date: str
    requested_last_event_date: str
    pages: tuple[CapturePageBinding, ...]
    total_page_count: int
    total_row_count: int
    role_row_counts: tuple[tuple[MassiveSourceRole, int], ...]
    owner_decision_id: str
    transactional_snapshot: bool
    complete_version_history: bool
    complete_deletion_tombstones: bool
    point_in_time_ticker_identity: bool
    pristine_point_in_time: bool


_CAPTURE_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[CaptureBinding],
        tuple[object, ...],
        tuple[object, ...],
    ],
] = {}
_CAPTURE_AUTHORITIES_LOCK = threading.RLock()


def _capture_manifest_record(
    *,
    capture_started_at: str,
    capture_completed_at: str,
    requested_first_event_date: str,
    requested_last_event_date: str,
    pages: tuple[CapturePageBinding, ...],
) -> dict[str, Any]:
    counts: Counter[MassiveSourceRole] = Counter()
    for page in pages:
        counts[page.source_role] += page.row_count
    return {
        "schema": CAPTURE_SCHEMA,
        "contract_id": INPUT_PAIR_CONTRACT_ID,
        "contract_sha256": INPUT_PAIR_CONTRACT_SHA256,
        "capture_started_at": capture_started_at,
        "capture_completed_at": capture_completed_at,
        "requested_first_event_date": requested_first_event_date,
        "requested_last_event_date": requested_last_event_date,
        "pages": [page.lineage_record() for page in pages],
        "total_page_count": len(pages),
        "total_row_count": sum(page.row_count for page in pages),
        "role_row_counts": [
            {"source_role": role.value, "row_count": counts[role]}
            for role in _ROLE_ORDER
        ],
        "owner_decision_id": OWNER_DECISION_ID,
        "transactional_snapshot": False,
        "complete_version_history": False,
        "complete_deletion_tombstones": False,
        "point_in_time_ticker_identity": False,
        "pristine_point_in_time": False,
    }


def _capture_fingerprint(capture: CaptureBinding) -> tuple[object, ...]:
    return (
        capture.schema,
        capture.contract_id,
        capture.contract_sha256,
        capture.capture_id,
        capture.capture_sha256,
        capture.capture_started_at,
        capture.capture_completed_at,
        capture.requested_first_event_date,
        capture.requested_last_event_date,
        tuple(
            (
                page.schema,
                page.source_role,
                page.endpoint_identifier,
                page.redacted_query_bytes,
                page.redacted_query_sha256,
                page.page_number,
                page.request_cursor_sha256,
                page.next_cursor_sha256,
                page.terminal_page,
                page.response_received_at,
                page.raw_response_sha256,
                page.provider_rows_bytes,
                page.provider_rows_sha256,
                page.row_count,
                page.raw_response_bytes,
            )
            for page in capture.pages
        ),
        capture.total_page_count,
        capture.total_row_count,
        capture.role_row_counts,
        capture.owner_decision_id,
        capture.transactional_snapshot,
        capture.complete_version_history,
        capture.complete_deletion_tombstones,
        capture.point_in_time_ticker_identity,
        capture.pristine_point_in_time,
    )


def _forget_capture(
    identity: int, reference: weakref.ReferenceType[CaptureBinding]
) -> None:
    with _CAPTURE_AUTHORITIES_LOCK:
        current = _CAPTURE_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _CAPTURE_AUTHORITIES.pop(identity, None)


def _validate_page_sequence(
    pages: tuple[CapturePageBinding, ...],
) -> tuple[str, str]:
    if type(pages) is not tuple or any(type(page) is not CapturePageBinding for page in pages):
        raise AcceptedRiskInputError("pages must be a tuple of exact CapturePageBinding values")
    if not pages:
        raise AcceptedRiskInputError("capture must contain pages")
    for page in pages:
        try:
            _PINNED_CAPTURE_PAGE_POST_INIT(page)
        except (AttributeError, CanonicalEvidenceError, TypeError, ValueError) as exc:
            raise AcceptedRiskInputError("capture page changed after binding") from exc
    observed_roles = tuple(dict.fromkeys(page.source_role for page in pages))
    if observed_roles != _ROLE_ORDER:
        raise AcceptedRiskInputError(
            "capture pages must contain all three source roles in canonical order"
        )
    expected_role_sequence = tuple(
        role
        for role in _ROLE_ORDER
        for page in pages
        if page.source_role is role
    )
    if tuple(page.source_role for page in pages) != expected_role_sequence:
        raise AcceptedRiskInputError(
            "capture pages for each source role must be contiguous"
        )

    first_date: str | None = None
    last_date: str | None = None
    for role in _ROLE_ORDER:
        role_pages = tuple(page for page in pages if page.source_role is role)
        if tuple(page.page_number for page in role_pages) != tuple(
            range(1, len(role_pages) + 1)
        ):
            raise AcceptedRiskInputError(
                f"{role.value} pages must be contiguous and ordered from one"
            )
        query_bytes = role_pages[0].redacted_query_bytes
        query_sha256 = role_pages[0].redacted_query_sha256
        if any(
            page.redacted_query_bytes != query_bytes
            or page.redacted_query_sha256 != query_sha256
            for page in role_pages
        ):
            raise AcceptedRiskInputError(
                f"{role.value} pages do not share one redacted base query"
            )
        query = _validate_redacted_query(query_bytes, role)
        if first_date is None:
            first_date = query["requested_first_event_date"]
            last_date = query["requested_last_event_date"]
        elif (
            query["requested_first_event_date"] != first_date
            or query["requested_last_event_date"] != last_date
        ):
            raise AcceptedRiskInputError(
                "all source roles must cover the same requested event-date range"
            )
        if role_pages[0].request_cursor_sha256 is not None:
            raise AcceptedRiskInputError("the first page in a role must not request a cursor")
        pagination_tokens = tuple(
            page.next_cursor_sha256
            for page in role_pages
            if page.next_cursor_sha256 is not None
        )
        if len(pagination_tokens) != len(set(pagination_tokens)):
            raise AcceptedRiskInputError(
                f"{role.value} cursor chain repeats or cycles"
            )
        raw_response_hashes = tuple(page.raw_response_sha256 for page in role_pages)
        if len(raw_response_hashes) != len(set(raw_response_hashes)):
            raise AcceptedRiskInputError(
                f"{role.value} pagination replays a response"
            )
        for prior, following in zip(role_pages, role_pages[1:]):
            if prior.terminal_page:
                raise AcceptedRiskInputError("a terminal page cannot be followed")
            if following.request_cursor_sha256 != prior.next_cursor_sha256:
                raise AcceptedRiskInputError("capture cursor chain is discontinuous")
        if not role_pages[-1].terminal_page:
            raise AcceptedRiskInputError("every source-role page chain must terminate")
    if first_date is None or last_date is None:
        raise AssertionError("required source-role pages disappeared")
    return first_date, last_date


def _candidate_provider_event_id(row: dict[str, Any]) -> str | None:
    try:
        return require_identifier(row.get("benzinga_id"), "benzinga_id")
    except CanonicalEvidenceError:
        return None


def _refuse_duplicate_provider_ids(pages: tuple[CapturePageBinding, ...]) -> None:
    # Massive describes benzinga_id as the stable record identifier, not as a
    # role-local display field.  C1 therefore refuses an ID repeated anywhere
    # in the three-role capture instead of guessing that two equal strings in
    # different endpoints denote different records.
    seen: dict[str, tuple[MassiveSourceRole, int, int]] = {}
    for page in pages:
        for offset, row in enumerate(page.parsed_rows):
            provider_event_id = _candidate_provider_event_id(row)
            if provider_event_id is None:
                continue
            if provider_event_id in seen:
                raise AcceptedRiskInputError(
                    "duplicate provider event ID invalidates the complete capture"
                )
            seen[provider_event_id] = (page.source_role, page.page_number, offset)


_PINNED_CAPTURE_MANIFEST_RECORD = _capture_manifest_record
_PINNED_CAPTURE_FINGERPRINT = _capture_fingerprint
_PINNED_VALIDATE_PAGE_SEQUENCE = _validate_page_sequence
_PINNED_REFUSE_DUPLICATE_PROVIDER_IDS = _refuse_duplicate_provider_ids


def _preflight_capture_scalar_types(capture: CaptureBinding) -> None:
    for name in (
        "schema",
        "contract_id",
        "contract_sha256",
        "capture_id",
        "capture_sha256",
        "capture_started_at",
        "capture_completed_at",
        "requested_first_event_date",
        "requested_last_event_date",
        "owner_decision_id",
    ):
        _require_exact_string(getattr(capture, name), name)
    if type(capture.pages) is not tuple or type(capture.role_row_counts) is not tuple:
        raise AcceptedRiskInputError("capture containers changed type")
    for name in ("total_page_count", "total_row_count"):
        if type(getattr(capture, name)) is not int:
            raise AcceptedRiskInputError(f"{name} must be an exact integer")
    for name in (
        "transactional_snapshot",
        "complete_version_history",
        "complete_deletion_tombstones",
        "point_in_time_ticker_identity",
        "pristine_point_in_time",
    ):
        if type(getattr(capture, name)) is not bool:
            raise AcceptedRiskInputError(f"{name} must be an exact boolean")


def _capture_container_roots(capture: CaptureBinding) -> tuple[object, ...]:
    return (capture.pages, capture.role_row_counts)


def build_capture_binding(
    *,
    capture_started_at: str,
    capture_completed_at: str,
    pages: tuple[CapturePageBinding, ...],
) -> CaptureBinding:
    """Authenticate one complete, caller-supplied, in-memory capture."""
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    _require_exact_string(capture_started_at, "capture_started_at")
    _require_exact_string(capture_completed_at, "capture_completed_at")
    started = parse_utc_timestamp(capture_started_at, "capture_started_at")
    completed = parse_utc_timestamp(capture_completed_at, "capture_completed_at")
    if started > completed:
        raise AcceptedRiskInputError("capture chronology is reversed")
    first_date, last_date = _PINNED_VALIDATE_PAGE_SEQUENCE(pages)
    received = [
        parse_utc_timestamp(page.response_received_at, "response_received_at")
        for page in pages
    ]
    if received != sorted(received):
        raise AcceptedRiskInputError("capture page receipt times must be nondecreasing")
    if any(instant < started or instant > completed for instant in received):
        raise AcceptedRiskInputError("capture page receipt falls outside capture chronology")
    _PINNED_REFUSE_DUPLICATE_PROVIDER_IDS(pages)

    manifest = _PINNED_CAPTURE_MANIFEST_RECORD(
        capture_started_at=capture_started_at,
        capture_completed_at=capture_completed_at,
        requested_first_event_date=first_date,
        requested_last_event_date=last_date,
        pages=pages,
    )
    capture_sha256 = sha256_bytes(canonical_json_bytes(manifest))
    capture_id = f"arv2-capture-{capture_sha256[:24]}"
    counts: Counter[MassiveSourceRole] = Counter()
    for page in pages:
        counts[page.source_role] += page.row_count
    capture = object.__new__(CaptureBinding)
    values: dict[str, object] = {
        "schema": CAPTURE_SCHEMA,
        "contract_id": INPUT_PAIR_CONTRACT_ID,
        "contract_sha256": INPUT_PAIR_CONTRACT_SHA256,
        "capture_id": capture_id,
        "capture_sha256": capture_sha256,
        "capture_started_at": capture_started_at,
        "capture_completed_at": capture_completed_at,
        "requested_first_event_date": first_date,
        "requested_last_event_date": last_date,
        "pages": pages,
        "total_page_count": len(pages),
        "total_row_count": sum(page.row_count for page in pages),
        "role_row_counts": tuple((role, counts[role]) for role in _ROLE_ORDER),
        "owner_decision_id": OWNER_DECISION_ID,
        "transactional_snapshot": False,
        "complete_version_history": False,
        "complete_deletion_tombstones": False,
        "point_in_time_ticker_identity": False,
        "pristine_point_in_time": False,
    }
    for name, value in values.items():
        object.__setattr__(capture, name, value)
    fingerprint = _PINNED_CAPTURE_FINGERPRINT(capture)
    container_authority = capture_frozen_container_authority(
        _capture_container_roots(capture)
    )
    identity = id(capture)
    reference = weakref.ref(
        capture, lambda ref, key=identity: _forget_capture(key, ref)
    )
    with _CAPTURE_AUTHORITIES_LOCK:
        _CAPTURE_AUTHORITIES[identity] = (
            reference,
            fingerprint,
            container_authority,
        )
    return capture


def require_capture_binding(capture: CaptureBinding) -> CaptureBinding:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    if type(capture) is not CaptureBinding:
        raise AcceptedRiskInputError("capture authority requires an exact CaptureBinding")
    try:
        _preflight_capture_scalar_types(capture)
    except AttributeError as exc:
        raise AcceptedRiskInputError("capture state is incomplete") from exc
    with _CAPTURE_AUTHORITIES_LOCK:
        authority = _CAPTURE_AUTHORITIES.get(id(capture))
    if authority is None or authority[0]() is not capture:
        raise AcceptedRiskInputError("capture is not builder-authenticated authority")
    if not frozen_container_authority_is_current(
        _capture_container_roots(capture), authority[2]
    ):
        raise AcceptedRiskInputError("capture container topology changed")
    first_date, last_date = _PINNED_VALIDATE_PAGE_SEQUENCE(capture.pages)
    if _PINNED_CAPTURE_FINGERPRINT(capture) != authority[1]:
        raise AcceptedRiskInputError("capture changed after authentication")
    _PINNED_REFUSE_DUPLICATE_PROVIDER_IDS(capture.pages)
    expected_manifest = _PINNED_CAPTURE_MANIFEST_RECORD(
        capture_started_at=capture.capture_started_at,
        capture_completed_at=capture.capture_completed_at,
        requested_first_event_date=first_date,
        requested_last_event_date=last_date,
        pages=capture.pages,
    )
    expected_sha256 = sha256_bytes(canonical_json_bytes(expected_manifest))
    if (
        capture.schema != CAPTURE_SCHEMA
        or capture.contract_id != INPUT_PAIR_CONTRACT_ID
        or capture.contract_sha256 != INPUT_PAIR_CONTRACT_SHA256
        or capture.capture_sha256 != expected_sha256
        or capture.capture_id != f"arv2-capture-{expected_sha256[:24]}"
        or capture.requested_first_event_date != first_date
        or capture.requested_last_event_date != last_date
        or capture.total_page_count != len(capture.pages)
        or capture.total_row_count != sum(page.row_count for page in capture.pages)
        or capture.owner_decision_id != OWNER_DECISION_ID
        or type(capture.transactional_snapshot) is not bool
        or capture.transactional_snapshot is not False
        or type(capture.complete_version_history) is not bool
        or capture.complete_version_history is not False
        or type(capture.complete_deletion_tombstones) is not bool
        or capture.complete_deletion_tombstones is not False
        or type(capture.point_in_time_ticker_identity) is not bool
        or capture.point_in_time_ticker_identity is not False
        or type(capture.pristine_point_in_time) is not bool
        or capture.pristine_point_in_time is not False
    ):
        raise AcceptedRiskInputError("capture semantic binding is not exact")
    started = parse_utc_timestamp(capture.capture_started_at, "capture_started_at")
    completed = parse_utc_timestamp(capture.capture_completed_at, "capture_completed_at")
    received = [parse_utc_timestamp(page.response_received_at, "response_received_at") for page in capture.pages]
    if started > completed or received != sorted(received) or any(
        instant < started or instant > completed for instant in received
    ):
        raise AcceptedRiskInputError("capture chronology is not exact")
    counts: Counter[MassiveSourceRole] = Counter()
    for page in capture.pages:
        counts[page.source_role] += page.row_count
    if capture.role_row_counts != tuple((role, counts[role]) for role in _ROLE_ORDER):
        raise AcceptedRiskInputError("capture role row counts are not exact")
    return capture


@dataclasses.dataclass(frozen=True)
class ViewEligibility:
    view: InputView
    included: bool
    disposition: RowDisposition
    eligible_session: str | None
    eligible_at: str | None
    decision_cutoff_at: str | None
    event_clock_not_after_cutoff: bool | None
    last_updated_not_after_cutoff: bool | None

    def __post_init__(self) -> None:
        if type(self.view) is not InputView or type(self.disposition) is not RowDisposition:
            raise AcceptedRiskInputError("view eligibility enums must have exact types")
        require_exact_bool(self.included, "included")
        for name in ("event_clock_not_after_cutoff", "last_updated_not_after_cutoff"):
            value = getattr(self, name)
            if value is not None:
                require_exact_bool(value, name)
        clock_fields = (self.eligible_session, self.eligible_at, self.decision_cutoff_at)
        if any(value is None for value in clock_fields) and any(
            value is not None for value in clock_fields
        ):
            raise AcceptedRiskInputError("eligibility clock fields must be all present or all null")
        if self.eligible_at is not None:
            parse_date(self.eligible_session, "eligible_session")
            parse_utc_timestamp(self.eligible_at, "eligible_at")
            parse_utc_timestamp(self.decision_cutoff_at, "decision_cutoff_at")
            if self.eligible_at != self.decision_cutoff_at:
                raise AcceptedRiskInputError("C1 decision cutoff must equal conservative eligibility")
        allowed_current = {
            RowDisposition.INCLUDED_CURRENT_ROW_NON_PRISTINE,
            RowDisposition.INVALID_PROVIDER_EVENT_ID,
            RowDisposition.INVALID_EVENT_DATE,
            RowDisposition.INVALID_EVENT_TIME,
            RowDisposition.EVENT_OUTSIDE_REQUESTED_CAPTURE_RANGE,
            RowDisposition.EVENT_OUTSIDE_EXCHANGE_CALENDAR_AUTHORITY,
            RowDisposition.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013,
            RowDisposition.LAST_UPDATED_AFTER_CAPTURE,
        }
        allowed_censored = set(RowDisposition) - {
            RowDisposition.INCLUDED_CURRENT_ROW_NON_PRISTINE
        }
        if self.view is InputView.CURRENT_ROW and self.disposition not in allowed_current:
            raise AcceptedRiskInputError("current-row view has an impossible disposition")
        if self.view is InputView.CONSERVATIVE_CENSORED and self.disposition not in allowed_censored:
            raise AcceptedRiskInputError("censored view has an impossible disposition")
        expected_included = self.disposition in {
            RowDisposition.INCLUDED_CURRENT_ROW_NON_PRISTINE,
            RowDisposition.INCLUDED_CONSERVATIVE_CENSORED_NON_PRISTINE,
        }
        if self.included != expected_included:
            raise AcceptedRiskInputError("view included flag disagrees with disposition")

    def to_record(self) -> dict[str, Any]:
        return {
            "view": self.view.value,
            "included": self.included,
            "disposition": self.disposition.value,
            "eligible_session": self.eligible_session,
            "eligible_at": self.eligible_at,
            "decision_cutoff_at": self.decision_cutoff_at,
            "event_clock_not_after_cutoff": self.event_clock_not_after_cutoff,
            "last_updated_not_after_cutoff": self.last_updated_not_after_cutoff,
        }


@dataclasses.dataclass(frozen=True)
class AcceptedRiskSourceRow:
    locator: CaptureRowLocator
    raw_row_bytes: bytes
    provider_event_id: str | None
    event_date: str | None
    event_year: int | None
    raw_event_time: str | None
    normalized_last_updated_at: str | None
    last_updated_calendar_date: str | None
    clock_interpretation: str
    action_label: str
    firm_label: str
    current_restated_security_label: str
    current_view: ViewEligibility
    censored_view: ViewEligibility

    def __post_init__(self) -> None:
        if type(self.locator) is not CaptureRowLocator:
            raise AcceptedRiskInputError("source row locator has the wrong type")
        if type(self.raw_row_bytes) is not bytes:
            raise AcceptedRiskInputError("raw_row_bytes must be exact bytes")
        parsed_rows = _parse_provider_rows_bytes(self.raw_row_bytes)
        if len(parsed_rows) != 1:
            raise AcceptedRiskInputError(
                "accepted-risk source row must contain one JSONL object"
            )
        if sha256_bytes(self.raw_row_bytes) != self.locator.raw_row_sha256:
            raise AcceptedRiskInputError("source row bytes/hash mismatch")
        if self.provider_event_id is not None:
            require_identifier(self.provider_event_id, "provider_event_id")
        if (self.event_date is None) != (self.event_year is None):
            raise AcceptedRiskInputError("event date and year must be jointly present or null")
        if self.event_date is not None:
            parsed_date = parse_date(self.event_date, "event_date")
            if self.event_year != parsed_date.year:
                raise AcceptedRiskInputError("event_year is not source-derived")
        if self.raw_event_time is not None and (
            type(self.raw_event_time) is not str
            or _RAW_TIME_RE.fullmatch(self.raw_event_time) is None
        ):
            raise AcceptedRiskInputError("raw_event_time is not HH:MM:SS")
        if self.normalized_last_updated_at is not None:
            parse_utc_timestamp(self.normalized_last_updated_at, "normalized_last_updated_at")
        if self.last_updated_calendar_date is not None:
            parse_date(
                self.last_updated_calendar_date, "last_updated_calendar_date"
            )
        if self.clock_interpretation != _CLOCK_INTERPRETATIONS[self.locator.source_role]:
            raise AcceptedRiskInputError("row clock interpretation does not match source role")
        for name in ("action_label", "firm_label", "current_restated_security_label"):
            require_text(getattr(self, name), name)
        if type(self.current_view) is not ViewEligibility or type(self.censored_view) is not ViewEligibility:
            raise AcceptedRiskInputError("source row needs exact view-eligibility values")
        if self.current_view.view is not InputView.CURRENT_ROW or self.censored_view.view is not InputView.CONSERVATIVE_CENSORED:
            raise AcceptedRiskInputError("source row view order is not exact")
        if self.censored_view.included and not self.current_view.included:
            raise AcceptedRiskInputError("censored inclusion cannot exceed current-row inclusion")
        if self.locator.source_role is MassiveSourceRole.CORPORATE_GUIDANCE:
            if self.current_view.included:
                if self.event_date is None:
                    raise AcceptedRiskInputError(
                        "included guidance lost its provider event date"
                    )
                eligible_session, eligible_at = _guidance_date_only_availability(
                    self.event_date
                )
                if (
                    self.current_view.eligible_session != eligible_session
                    or self.current_view.eligible_at != eligible_at
                ):
                    raise AcceptedRiskInputError(
                        "guidance did not retain its conservative date-only cutoff"
                    )
            if self.censored_view.included:
                if self.normalized_last_updated_at is not None:
                    if (
                        self.censored_view.decision_cutoff_at is None
                        or parse_utc_timestamp(
                            self.normalized_last_updated_at,
                            "normalized_last_updated_at",
                        )
                        > parse_utc_timestamp(
                            self.censored_view.decision_cutoff_at,
                            "decision_cutoff_at",
                        )
                    ):
                        raise AcceptedRiskInputError(
                            "censored guidance exact last_updated exceeded its delayed cutoff"
                        )
                elif (
                    self.last_updated_calendar_date is None
                    or self.censored_view.eligible_session is None
                    or self.last_updated_calendar_date
                    >= self.censored_view.eligible_session
                ):
                    raise AcceptedRiskInputError(
                        "censored guidance did not precede its delayed session"
                    )

    def to_record(self) -> dict[str, Any]:
        return {
            "locator": self.locator.to_record(),
            "provider_event_id": self.provider_event_id,
            "event_date": self.event_date,
            "event_year": self.event_year,
            "raw_event_time": self.raw_event_time,
            "normalized_last_updated_at": self.normalized_last_updated_at,
            "last_updated_calendar_date": self.last_updated_calendar_date,
            "clock_interpretation": self.clock_interpretation,
            "action_label": self.action_label,
            "firm_label": self.firm_label,
            "current_restated_security_label": self.current_restated_security_label,
            "raw_row_sha256": self.locator.raw_row_sha256,
            "current_view": self.current_view.to_record(),
            "censored_view": self.censored_view.to_record(),
        }


@dataclasses.dataclass(frozen=True)
class ExactRate:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        require_int(self.numerator, "rate numerator", minimum=0)
        require_int(self.denominator, "rate denominator", minimum=1)
        if self.numerator > self.denominator:
            raise AcceptedRiskInputError("rate numerator exceeds denominator")

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    def to_record(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}


@dataclasses.dataclass(frozen=True)
class DispositionCount:
    view: InputView
    disposition: RowDisposition
    count: int

    def __post_init__(self) -> None:
        if type(self.view) is not InputView or type(self.disposition) is not RowDisposition:
            raise AcceptedRiskInputError("disposition count enums have the wrong type")
        require_int(self.count, "disposition count", minimum=0)

    def to_record(self) -> dict[str, Any]:
        return {
            "view": self.view.value,
            "disposition": self.disposition.value,
            "count": self.count,
        }


@dataclasses.dataclass(frozen=True)
class DispositionBreakdown:
    dimension: BreakdownDimension
    key: str
    total_count: int
    current_included_count: int
    censored_included_count: int
    disagreement_count: int
    current_inclusion_rate: ExactRate
    censored_inclusion_rate: ExactRate
    disagreement_rate: ExactRate

    def __post_init__(self) -> None:
        if type(self.dimension) is not BreakdownDimension:
            raise AcceptedRiskInputError("breakdown dimension has the wrong type")
        require_text(self.key, "breakdown key")
        for name in (
            "total_count",
            "current_included_count",
            "censored_included_count",
            "disagreement_count",
        ):
            require_int(getattr(self, name), name, minimum=0)
        if self.total_count <= 0:
            raise AcceptedRiskInputError("breakdown must represent at least one row")
        if not (
            self.censored_included_count
            <= self.current_included_count
            <= self.total_count
        ):
            raise AcceptedRiskInputError("breakdown inclusion counts are inconsistent")
        if self.disagreement_count != (
            self.current_included_count - self.censored_included_count
        ):
            raise AcceptedRiskInputError("breakdown disagreement count is not exact")
        rates = (
            (self.current_inclusion_rate, self.current_included_count),
            (self.censored_inclusion_rate, self.censored_included_count),
            (self.disagreement_rate, self.disagreement_count),
        )
        if any(
            type(rate) is not ExactRate
            or rate.numerator != count
            or rate.denominator != self.total_count
            for rate, count in rates
        ):
            raise AcceptedRiskInputError("breakdown rational rate is not count-derived")

    def to_record(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "key": self.key,
            "total_count": self.total_count,
            "current_included_count": self.current_included_count,
            "censored_included_count": self.censored_included_count,
            "disagreement_count": self.disagreement_count,
            "current_inclusion_rate": self.current_inclusion_rate.to_record(),
            "censored_inclusion_rate": self.censored_inclusion_rate.to_record(),
            "disagreement_rate": self.disagreement_rate.to_record(),
        }


@dataclasses.dataclass(frozen=True)
class InputPairReport:
    schema: str
    total_row_count: int
    current_included_count: int
    censored_included_count: int
    disagreement_count: int
    disposition_counts: tuple[DispositionCount, ...]
    breakdowns: tuple[DispositionBreakdown, ...]
    mapping_disagreement_report: None
    signal_disagreement_report: None

    def __post_init__(self) -> None:
        if self.schema != INPUT_PAIR_REPORT_SCHEMA:
            raise AcceptedRiskInputError("wrong input-pair report schema")
        require_int(self.total_row_count, "total_row_count", minimum=1)
        for name in ("current_included_count", "censored_included_count", "disagreement_count"):
            require_int(getattr(self, name), name, minimum=0)
        if not self.censored_included_count <= self.current_included_count <= self.total_row_count:
            raise AcceptedRiskInputError("report inclusion counts are inconsistent")
        if self.disagreement_count != self.current_included_count - self.censored_included_count:
            raise AcceptedRiskInputError("report disagreement count is not exact")
        if type(self.disposition_counts) is not tuple or any(
            type(item) is not DispositionCount for item in self.disposition_counts
        ):
            raise AcceptedRiskInputError("disposition_counts must be an exact tuple")
        expected_pairs = tuple(
            (view, disposition) for view in InputView for disposition in RowDisposition
        )
        if tuple((item.view, item.disposition) for item in self.disposition_counts) != expected_pairs:
            raise AcceptedRiskInputError("disposition count inventory is not exhaustive and ordered")
        for view in InputView:
            if sum(item.count for item in self.disposition_counts if item.view is view) != self.total_row_count:
                raise AcceptedRiskInputError("disposition counts do not exhaust every row")
        if type(self.breakdowns) is not tuple or any(
            type(item) is not DispositionBreakdown for item in self.breakdowns
        ):
            raise AcceptedRiskInputError("breakdowns must be an exact tuple")
        if not self.breakdowns or self.breakdowns[0].dimension is not BreakdownDimension.OVERALL:
            raise AcceptedRiskInputError("report must begin with an overall breakdown")
        if self.mapping_disagreement_report is not None or self.signal_disagreement_report is not None:
            raise AcceptedRiskInputError("C1 cannot contain mapping or signal disagreement results")

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "total_row_count": self.total_row_count,
            "current_included_count": self.current_included_count,
            "censored_included_count": self.censored_included_count,
            "disagreement_count": self.disagreement_count,
            "disposition_counts": [item.to_record() for item in self.disposition_counts],
            "breakdowns": [item.to_record() for item in self.breakdowns],
            "mapping_disagreement_report": None,
            "signal_disagreement_report": None,
        }


@dataclasses.dataclass(frozen=True, init=False)
class AcceptedRiskInputPair:
    schema: str
    contract_id: str
    contract_sha256: str
    pair_id: str
    pair_sha256: str
    capture: CaptureBinding
    rows: tuple[AcceptedRiskSourceRow, ...]
    report: InputPairReport
    current_view_label: str
    censored_view_label: str
    pristine_point_in_time: bool
    earlier_version_imputation_performed: bool
    views_share_one_capture: bool
    guidance_clock_authenticated: bool
    identity_mapping_authenticated: bool
    rating_mapping_authenticated: bool
    signal_rows_constructed: bool
    production_input_authority: bool
    outcome_gate_open: bool
    provider_binding: None
    security_master_binding: None
    outcome_binding: None
    provider_io_performed: bool
    credential_access_performed: bool
    filesystem_io_performed: bool
    quantconnect_io_performed: bool
    object_store_io_performed: bool
    market_data_access_performed: bool
    outcome_access_performed: bool
    deployment_performed: bool
    order_access_performed: bool
    trading_performed: bool

    @property
    def current_rows(self) -> tuple[AcceptedRiskSourceRow, ...]:
        _PINNED_REQUIRE_STATIC_CONTRACT()
        _require_static_contract()
        require_accepted_risk_input_pair(self)
        return tuple(row for row in self.rows if row.current_view.included)

    @property
    def censored_rows(self) -> tuple[AcceptedRiskSourceRow, ...]:
        _PINNED_REQUIRE_STATIC_CONTRACT()
        _require_static_contract()
        require_accepted_risk_input_pair(self)
        return tuple(row for row in self.rows if row.censored_view.included)


_PAIR_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[AcceptedRiskInputPair],
        tuple[object, ...],
        tuple[object, ...],
    ],
] = {}
_PAIR_AUTHORITIES_LOCK = threading.RLock()


def _normalize_explicit_offset_timestamp(value: object) -> str | None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or _EXPLICIT_OFFSET_RE.fullmatch(value) is None
    ):
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    try:
        return format_utc_timestamp(parsed.astimezone(timezone.utc))
    except (CanonicalEvidenceError, OSError, OverflowError, ValueError):
        return None


def _guidance_last_updated_calendar_date(value: object) -> str | None:
    """Parse only the provider calendar date; never infer an unknown zone."""

    if type(value) is not str or value != value.strip() or len(value) > 64:
        return None
    match = _GUIDANCE_LAST_UPDATED_RE.fullmatch(value)
    if match is None:
        return None
    candidate = match.group("date")
    try:
        return parse_date(candidate, "guidance last_updated date").isoformat()
    except CanonicalEvidenceError:
        return None


def _guidance_date_only_availability(public_date: str) -> tuple[str, str]:
    """Return a timezone-independent, deliberately delayed guidance cutoff."""

    try:
        eligible_session, market_open = (
            _PINNED_RESOLVE_DELAYED_DATE_ONLY_SESSION_OPEN(
                public_date=public_date,
                session_lag=GUIDANCE_CONSERVATIVE_SESSION_LAG,
            )
        )
        eligible_at = format_utc_timestamp(market_open)
    except (
        CanonicalEvidenceError,
        AvailabilityError,
        OSError,
        OverflowError,
        ValueError,
    ) as exc:
        raise AcceptedRiskInputError(
            "guidance date is outside exchange-calendar authority"
        ) from exc
    return eligible_session, eligible_at


def _valid_raw_time(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is str and _RAW_TIME_RE.fullmatch(value) is not None:
        return value
    raise AcceptedRiskInputError("invalid raw event time")


def _dimension_text(value: object, *, missing: str, maximum_length: int = 256) -> str:
    if type(value) is str:
        try:
            return require_text(value, "dimension value", maximum_length=maximum_length)
        except CanonicalEvidenceError:
            pass
    return missing


def _row_dimension_labels(
    role: MassiveSourceRole, row: dict[str, Any]
) -> tuple[str, str, str]:
    if role is MassiveSourceRole.ANALYST_RATINGS:
        action = _dimension_text(
            row.get("rating_action") or row.get("price_target_action"),
            missing="__missing_rating_or_target_action__",
        )
        firm = _dimension_text(
            row.get("benzinga_firm_id"), missing="__missing_provider_firm_id__"
        )
    elif role is MassiveSourceRole.EARNINGS:
        action = "earnings_event"
        firm = "__not_applicable_to_earnings__"
    else:
        action = _dimension_text(
            row.get("guidance_type"), missing="corporate_guidance_event"
        )
        firm = "__not_applicable_to_corporate_guidance__"
    security = _dimension_text(
        row.get("ticker"),
        missing="__missing_current_restated_security_label__",
        maximum_length=64,
    )
    return action, firm, security


def _excluded_view(
    *,
    view: InputView,
    disposition: RowDisposition,
    eligible_session: str | None = None,
    eligible_at: str | None = None,
    event_clock_not_after_cutoff: bool | None = None,
    last_updated_not_after_cutoff: bool | None = None,
) -> ViewEligibility:
    return ViewEligibility(
        view=view,
        included=False,
        disposition=disposition,
        eligible_session=eligible_session,
        eligible_at=eligible_at,
        decision_cutoff_at=eligible_at,
        event_clock_not_after_cutoff=event_clock_not_after_cutoff,
        last_updated_not_after_cutoff=last_updated_not_after_cutoff,
    )


def _joint_exclusion(disposition: RowDisposition) -> tuple[ViewEligibility, ViewEligibility]:
    return (
        _excluded_view(view=InputView.CURRENT_ROW, disposition=disposition),
        _excluded_view(view=InputView.CONSERVATIVE_CENSORED, disposition=disposition),
    )


def _derive_source_row(
    *,
    capture: CaptureBinding,
    page: CapturePageBinding,
    row_offset: int,
    row: dict[str, Any],
    raw_row_bytes: bytes,
) -> AcceptedRiskSourceRow:
    locator = CaptureRowLocator(
        capture_id=capture.capture_id,
        source_role=page.source_role,
        page_number=page.page_number,
        provider_rows_sha256=page.provider_rows_sha256,
        row_offset=row_offset,
        raw_row_sha256=sha256_bytes(raw_row_bytes),
    )
    provider_event_id = _candidate_provider_event_id(row)
    raw_date = row.get("date")
    event_date: str | None = None
    event_year: int | None = None
    try:
        parsed_event_date = parse_date(raw_date, "provider event date")
        event_date = parsed_event_date.isoformat()
        event_year = parsed_event_date.year
    except CanonicalEvidenceError:
        parsed_event_date = None

    raw_event_time: str | None = None
    time_invalid = False
    try:
        raw_event_time = _valid_raw_time(row.get("time"))
    except AcceptedRiskInputError:
        time_invalid = True
    normalized_last_updated_at = _normalize_explicit_offset_timestamp(
        row.get("last_updated")
    )
    last_updated_calendar_date = (
        _guidance_last_updated_calendar_date(row.get("last_updated"))
        if page.source_role is MassiveSourceRole.CORPORATE_GUIDANCE
        else None
    )
    action, firm, security = _row_dimension_labels(page.source_role, row)

    if provider_event_id is None:
        current, censored = _joint_exclusion(RowDisposition.INVALID_PROVIDER_EVENT_ID)
    elif parsed_event_date is None:
        current, censored = _joint_exclusion(RowDisposition.INVALID_EVENT_DATE)
    elif time_invalid:
        current, censored = _joint_exclusion(RowDisposition.INVALID_EVENT_TIME)
    elif parsed_event_date < _PINNED_MINIMUM_ADMISSIBLE_EVENT_DATE:
        current, censored = _joint_exclusion(
            RowDisposition.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
        )
    elif not (
        parse_date(capture.requested_first_event_date, "capture first date")
        <= parsed_event_date
        <= parse_date(capture.requested_last_event_date, "capture last date")
    ):
        current, censored = _joint_exclusion(
            RowDisposition.EVENT_OUTSIDE_REQUESTED_CAPTURE_RANGE
        )
    else:
        try:
            if page.source_role is MassiveSourceRole.CORPORATE_GUIDANCE:
                eligible_session, eligible_at = _guidance_date_only_availability(
                    event_date
                )
            else:
                availability = _PINNED_DERIVE_EVENT_AVAILABILITY(
                    evidence_id=(
                        f"{capture.capture_id}:{page.source_role.value}:"
                        f"{provider_event_id}"
                    ),
                    public_date=event_date,
                )
                eligible_at = format_utc_timestamp(
                    datetime.fromisoformat(
                        availability.eligible_at.replace("Z", "+00:00")
                    )
                )
                eligible_session = availability.eligible_session
        except (
            AcceptedRiskInputError,
            AvailabilityError,
            CanonicalEvidenceError,
            OSError,
            OverflowError,
            ValueError,
        ):
            current, censored = _joint_exclusion(
                RowDisposition.EVENT_OUTSIDE_EXCHANGE_CALENDAR_AUTHORITY
            )
        else:
            received = parse_utc_timestamp(
                page.response_received_at, "response_received_at"
            )
            updated = (
                parse_utc_timestamp(
                    normalized_last_updated_at, "normalized_last_updated_at"
                )
                if normalized_last_updated_at is not None
                else None
            )
            naive_guidance_touch_after_receipt = (
                page.source_role is MassiveSourceRole.CORPORATE_GUIDANCE
                and updated is None
                and last_updated_calendar_date is not None
                and last_updated_calendar_date > received.date().isoformat()
            )
            if (
                (updated is not None and updated > received)
                or naive_guidance_touch_after_receipt
            ):
                current = _excluded_view(
                    view=InputView.CURRENT_ROW,
                    disposition=RowDisposition.LAST_UPDATED_AFTER_CAPTURE,
                    eligible_session=eligible_session,
                    eligible_at=eligible_at,
                    event_clock_not_after_cutoff=True,
                )
                censored = _excluded_view(
                    view=InputView.CONSERVATIVE_CENSORED,
                    disposition=RowDisposition.LAST_UPDATED_AFTER_CAPTURE,
                    eligible_session=eligible_session,
                    eligible_at=eligible_at,
                    event_clock_not_after_cutoff=True,
                    last_updated_not_after_cutoff=False,
                )
            else:
                current = ViewEligibility(
                    view=InputView.CURRENT_ROW,
                    included=True,
                    disposition=RowDisposition.INCLUDED_CURRENT_ROW_NON_PRISTINE,
                    eligible_session=eligible_session,
                    eligible_at=eligible_at,
                    decision_cutoff_at=eligible_at,
                    event_clock_not_after_cutoff=True,
                    last_updated_not_after_cutoff=None,
                )
                if page.source_role is MassiveSourceRole.CORPORATE_GUIDANCE:
                    decision_cutoff = parse_utc_timestamp(
                        eligible_at, "decision cutoff"
                    )
                    if updated is not None and updated <= decision_cutoff:
                        censored = ViewEligibility(
                            view=InputView.CONSERVATIVE_CENSORED,
                            included=True,
                            disposition=(
                                RowDisposition.INCLUDED_CONSERVATIVE_CENSORED_NON_PRISTINE
                            ),
                            eligible_session=eligible_session,
                            eligible_at=eligible_at,
                            decision_cutoff_at=eligible_at,
                            event_clock_not_after_cutoff=True,
                            last_updated_not_after_cutoff=True,
                        )
                    elif updated is not None:
                        censored = _excluded_view(
                            view=InputView.CONSERVATIVE_CENSORED,
                            disposition=(
                                RowDisposition.CENSORED_LAST_TOUCH_AFTER_DECISION_CUTOFF
                            ),
                            eligible_session=eligible_session,
                            eligible_at=eligible_at,
                            event_clock_not_after_cutoff=True,
                            last_updated_not_after_cutoff=False,
                        )
                    elif last_updated_calendar_date is None:
                        censored = _excluded_view(
                            view=InputView.CONSERVATIVE_CENSORED,
                            disposition=(
                                RowDisposition.INVALID_LAST_UPDATED_EXPLICIT_OFFSET
                            ),
                            eligible_session=eligible_session,
                            eligible_at=eligible_at,
                            event_clock_not_after_cutoff=True,
                        )
                    elif last_updated_calendar_date < eligible_session:
                        censored = ViewEligibility(
                            view=InputView.CONSERVATIVE_CENSORED,
                            included=True,
                            disposition=(
                                RowDisposition.INCLUDED_CONSERVATIVE_CENSORED_NON_PRISTINE
                            ),
                            eligible_session=eligible_session,
                            eligible_at=eligible_at,
                            decision_cutoff_at=eligible_at,
                            event_clock_not_after_cutoff=True,
                            last_updated_not_after_cutoff=True,
                        )
                    else:
                        censored = _excluded_view(
                            view=InputView.CONSERVATIVE_CENSORED,
                            disposition=(
                                RowDisposition.CENSORED_LAST_TOUCH_AFTER_DECISION_CUTOFF
                            ),
                            eligible_session=eligible_session,
                            eligible_at=eligible_at,
                            event_clock_not_after_cutoff=True,
                            last_updated_not_after_cutoff=False,
                        )
                elif updated is None:
                    censored = _excluded_view(
                        view=InputView.CONSERVATIVE_CENSORED,
                        disposition=RowDisposition.INVALID_LAST_UPDATED_EXPLICIT_OFFSET,
                        eligible_session=eligible_session,
                        eligible_at=eligible_at,
                        event_clock_not_after_cutoff=True,
                    )
                elif updated <= parse_utc_timestamp(eligible_at, "decision cutoff"):
                    censored = ViewEligibility(
                        view=InputView.CONSERVATIVE_CENSORED,
                        included=True,
                        disposition=(
                            RowDisposition.INCLUDED_CONSERVATIVE_CENSORED_NON_PRISTINE
                        ),
                        eligible_session=eligible_session,
                        eligible_at=eligible_at,
                        decision_cutoff_at=eligible_at,
                        event_clock_not_after_cutoff=True,
                        last_updated_not_after_cutoff=True,
                    )
                else:
                    censored = _excluded_view(
                        view=InputView.CONSERVATIVE_CENSORED,
                        disposition=(
                            RowDisposition.CENSORED_LAST_TOUCH_AFTER_DECISION_CUTOFF
                        ),
                        eligible_session=eligible_session,
                        eligible_at=eligible_at,
                        event_clock_not_after_cutoff=True,
                        last_updated_not_after_cutoff=False,
                    )

    return AcceptedRiskSourceRow(
        locator=locator,
        raw_row_bytes=raw_row_bytes,
        provider_event_id=provider_event_id,
        event_date=event_date,
        event_year=event_year,
        raw_event_time=raw_event_time,
        normalized_last_updated_at=normalized_last_updated_at,
        last_updated_calendar_date=last_updated_calendar_date,
        clock_interpretation=_CLOCK_INTERPRETATIONS[page.source_role],
        action_label=action,
        firm_label=firm,
        current_restated_security_label=security,
        current_view=current,
        censored_view=censored,
    )


_PINNED_DERIVE_SOURCE_ROW = _derive_source_row


def _derive_rows(capture: CaptureBinding) -> tuple[AcceptedRiskSourceRow, ...]:
    rows = tuple(
        _PINNED_DERIVE_SOURCE_ROW(
            capture=capture,
            page=page,
            row_offset=offset,
            row=row,
            raw_row_bytes=raw_row_bytes,
        )
        for page in capture.pages
        for offset, (row, raw_row_bytes) in enumerate(
            _parse_provider_rows_bytes(page.provider_rows_bytes)
        )
    )
    if len(rows) != capture.total_row_count:
        raise AcceptedRiskInputError("derived row count does not match capture")
    if tuple(row.locator.sort_key for row in rows) != tuple(
        sorted(row.locator.sort_key for row in rows)
    ):
        raise AcceptedRiskInputError("derived rows are not canonically source-ordered")
    return rows


_PINNED_DERIVE_ROWS = _derive_rows


def _breakdown(
    dimension: BreakdownDimension,
    key: str,
    rows: tuple[AcceptedRiskSourceRow, ...],
) -> DispositionBreakdown:
    total = len(rows)
    current = sum(row.current_view.included for row in rows)
    censored = sum(row.censored_view.included for row in rows)
    disagreement = sum(
        row.current_view.included != row.censored_view.included for row in rows
    )
    return DispositionBreakdown(
        dimension=dimension,
        key=key,
        total_count=total,
        current_included_count=current,
        censored_included_count=censored,
        disagreement_count=disagreement,
        current_inclusion_rate=ExactRate(current, total),
        censored_inclusion_rate=ExactRate(censored, total),
        disagreement_rate=ExactRate(disagreement, total),
    )


def _build_report(rows: tuple[AcceptedRiskSourceRow, ...]) -> InputPairReport:
    if not rows:
        raise AcceptedRiskInputError("accepted-risk input pair cannot be empty")
    disposition_counts = tuple(
        DispositionCount(
            view=view,
            disposition=disposition,
            count=sum(
                1
                for row in rows
                if (row.current_view if view is InputView.CURRENT_ROW else row.censored_view).disposition
                is disposition
            ),
        )
        for view in InputView
        for disposition in RowDisposition
    )
    breakdowns: list[DispositionBreakdown] = [
        _breakdown(BreakdownDimension.OVERALL, "all_rows", rows)
    ]
    dimensions = (
        (
            BreakdownDimension.EVENT_YEAR,
            lambda row: str(row.event_year) if row.event_year is not None else "__invalid_event_year__",
        ),
        (BreakdownDimension.SOURCE_ROLE, lambda row: row.locator.source_role.value),
        (BreakdownDimension.ACTION, lambda row: row.action_label),
        (BreakdownDimension.FIRM, lambda row: row.firm_label),
        (
            BreakdownDimension.SECURITY_LABEL,
            lambda row: row.current_restated_security_label,
        ),
    )
    for dimension, key_function in dimensions:
        grouped: dict[str, list[AcceptedRiskSourceRow]] = defaultdict(list)
        for row in rows:
            grouped[key_function(row)].append(row)
        for key in sorted(grouped):
            breakdowns.append(_breakdown(dimension, key, tuple(grouped[key])))
    current = sum(row.current_view.included for row in rows)
    censored = sum(row.censored_view.included for row in rows)
    disagreement = sum(row.current_view.included != row.censored_view.included for row in rows)
    return InputPairReport(
        schema=INPUT_PAIR_REPORT_SCHEMA,
        total_row_count=len(rows),
        current_included_count=current,
        censored_included_count=censored,
        disagreement_count=disagreement,
        disposition_counts=disposition_counts,
        breakdowns=tuple(breakdowns),
        mapping_disagreement_report=None,
        signal_disagreement_report=None,
    )


def _pair_semantic_record(
    capture: CaptureBinding,
    rows: tuple[AcceptedRiskSourceRow, ...],
    report: InputPairReport,
) -> dict[str, Any]:
    return {
        "schema": INPUT_PAIR_SCHEMA,
        "contract_id": INPUT_PAIR_CONTRACT_ID,
        "contract_sha256": INPUT_PAIR_CONTRACT_SHA256,
        "capture_id": capture.capture_id,
        "capture_sha256": capture.capture_sha256,
        "rows": [row.to_record() for row in rows],
        "report": report.to_record(),
        "current_view_label": CURRENT_VIEW_LABEL,
        "censored_view_label": CENSORED_VIEW_LABEL,
        "pristine_point_in_time": False,
        "earlier_version_imputation_performed": False,
        "views_share_one_capture": True,
        "guidance_clock_authenticated": False,
        "identity_mapping_authenticated": False,
        "rating_mapping_authenticated": False,
        "signal_rows_constructed": False,
        "production_input_authority": False,
        "outcome_gate_open": False,
        "provider_binding": None,
        "security_master_binding": None,
        "outcome_binding": None,
        "provider_io_performed": False,
        "credential_access_performed": False,
        "filesystem_io_performed": False,
        "quantconnect_io_performed": False,
        "object_store_io_performed": False,
        "market_data_access_performed": False,
        "outcome_access_performed": False,
        "deployment_performed": False,
        "order_access_performed": False,
        "trading_performed": False,
    }


def _pair_fingerprint(pair: AcceptedRiskInputPair) -> tuple[object, ...]:
    return (
        pair.schema,
        pair.contract_id,
        pair.contract_sha256,
        pair.pair_id,
        pair.pair_sha256,
        pair.capture,
        tuple(
            (
                row.locator,
                row.raw_row_bytes,
                row.provider_event_id,
                row.event_date,
                row.event_year,
                row.raw_event_time,
                row.normalized_last_updated_at,
                row.last_updated_calendar_date,
                row.clock_interpretation,
                row.action_label,
                row.firm_label,
                row.current_restated_security_label,
                row.current_view,
                row.censored_view,
            )
            for row in pair.rows
        ),
        pair.report,
        pair.current_view_label,
        pair.censored_view_label,
        pair.pristine_point_in_time,
        pair.earlier_version_imputation_performed,
        pair.views_share_one_capture,
        pair.guidance_clock_authenticated,
        pair.identity_mapping_authenticated,
        pair.rating_mapping_authenticated,
        pair.signal_rows_constructed,
        pair.production_input_authority,
        pair.outcome_gate_open,
        pair.provider_binding,
        pair.security_master_binding,
        pair.outcome_binding,
        pair.provider_io_performed,
        pair.credential_access_performed,
        pair.filesystem_io_performed,
        pair.quantconnect_io_performed,
        pair.object_store_io_performed,
        pair.market_data_access_performed,
        pair.outcome_access_performed,
        pair.deployment_performed,
        pair.order_access_performed,
        pair.trading_performed,
    )


def _pair_container_roots(pair: AcceptedRiskInputPair) -> tuple[object, ...]:
    return (
        pair.capture,
        pair.rows,
        pair.report,
        pair.report.disposition_counts,
        pair.report.breakdowns,
    )


def _require_exact_optional_string(value: object, name: str) -> None:
    if value is not None:
        _require_exact_string(value, name)


def _preflight_view_scalar_types(view: ViewEligibility, name: str) -> None:
    if type(view) is not ViewEligibility:
        raise AcceptedRiskInputError(f"{name} must be an exact ViewEligibility")
    if type(view.view) is not InputView or type(view.disposition) is not RowDisposition:
        raise AcceptedRiskInputError(f"{name} enum fields changed type")
    if type(view.included) is not bool:
        raise AcceptedRiskInputError(f"{name}.included must be an exact boolean")
    for field_name in ("eligible_session", "eligible_at", "decision_cutoff_at"):
        _require_exact_optional_string(getattr(view, field_name), f"{name}.{field_name}")
    for field_name in (
        "event_clock_not_after_cutoff",
        "last_updated_not_after_cutoff",
    ):
        value = getattr(view, field_name)
        if value is not None and type(value) is not bool:
            raise AcceptedRiskInputError(
                f"{name}.{field_name} must be null or an exact boolean"
            )


def _preflight_pair_scalar_types(pair: AcceptedRiskInputPair) -> None:
    for name in (
        "schema",
        "contract_id",
        "contract_sha256",
        "pair_id",
        "pair_sha256",
        "current_view_label",
        "censored_view_label",
    ):
        _require_exact_string(getattr(pair, name), name)
    if type(pair.capture) is not CaptureBinding:
        raise AcceptedRiskInputError("pair capture changed type")
    if type(pair.rows) is not tuple or type(pair.report) is not InputPairReport:
        raise AcceptedRiskInputError("pair row/report containers changed type")
    for name in (
        "pristine_point_in_time",
        "earlier_version_imputation_performed",
        "views_share_one_capture",
        "guidance_clock_authenticated",
        "identity_mapping_authenticated",
        "rating_mapping_authenticated",
        "signal_rows_constructed",
        "production_input_authority",
        "outcome_gate_open",
        "provider_io_performed",
        "credential_access_performed",
        "filesystem_io_performed",
        "quantconnect_io_performed",
        "object_store_io_performed",
        "market_data_access_performed",
        "outcome_access_performed",
        "deployment_performed",
        "order_access_performed",
        "trading_performed",
    ):
        if type(getattr(pair, name)) is not bool:
            raise AcceptedRiskInputError(f"{name} must be an exact boolean")
    for name in ("provider_binding", "security_master_binding", "outcome_binding"):
        if getattr(pair, name) is not None:
            raise AcceptedRiskInputError(f"{name} must remain null")

    for row_index, row in enumerate(pair.rows):
        prefix = f"rows[{row_index}]"
        if type(row) is not AcceptedRiskSourceRow:
            raise AcceptedRiskInputError(f"{prefix} changed type")
        if type(row.locator) is not CaptureRowLocator:
            raise AcceptedRiskInputError(f"{prefix}.locator changed type")
        locator = row.locator
        for field_name in ("capture_id", "provider_rows_sha256", "raw_row_sha256"):
            _require_exact_string(
                getattr(locator, field_name), f"{prefix}.locator.{field_name}"
            )
        if type(locator.source_role) is not MassiveSourceRole:
            raise AcceptedRiskInputError(f"{prefix}.locator.source_role changed type")
        for field_name in ("page_number", "row_offset"):
            if type(getattr(locator, field_name)) is not int:
                raise AcceptedRiskInputError(
                    f"{prefix}.locator.{field_name} must be an exact integer"
                )
        if type(row.raw_row_bytes) is not bytes:
            raise AcceptedRiskInputError(f"{prefix}.raw_row_bytes changed type")
        for field_name in (
            "provider_event_id",
            "event_date",
            "raw_event_time",
            "normalized_last_updated_at",
            "last_updated_calendar_date",
        ):
            _require_exact_optional_string(
                getattr(row, field_name), f"{prefix}.{field_name}"
            )
        if row.event_year is not None and type(row.event_year) is not int:
            raise AcceptedRiskInputError(f"{prefix}.event_year changed type")
        for field_name in (
            "clock_interpretation",
            "action_label",
            "firm_label",
            "current_restated_security_label",
        ):
            _require_exact_string(getattr(row, field_name), f"{prefix}.{field_name}")
        _preflight_view_scalar_types(row.current_view, f"{prefix}.current_view")
        _preflight_view_scalar_types(row.censored_view, f"{prefix}.censored_view")

    report = pair.report
    _require_exact_string(report.schema, "report.schema")
    for field_name in (
        "total_row_count",
        "current_included_count",
        "censored_included_count",
        "disagreement_count",
    ):
        if type(getattr(report, field_name)) is not int:
            raise AcceptedRiskInputError(f"report.{field_name} changed type")
    if type(report.disposition_counts) is not tuple or type(report.breakdowns) is not tuple:
        raise AcceptedRiskInputError("report containers changed type")
    if report.mapping_disagreement_report is not None or report.signal_disagreement_report is not None:
        raise AcceptedRiskInputError("C1 report bindings must remain null")
    for index, count in enumerate(report.disposition_counts):
        if type(count) is not DispositionCount:
            raise AcceptedRiskInputError(f"report.disposition_counts[{index}] changed type")
        if type(count.view) is not InputView or type(count.disposition) is not RowDisposition:
            raise AcceptedRiskInputError("report disposition enums changed type")
        if type(count.count) is not int:
            raise AcceptedRiskInputError("report disposition count changed type")
    for index, breakdown in enumerate(report.breakdowns):
        prefix = f"report.breakdowns[{index}]"
        if type(breakdown) is not DispositionBreakdown:
            raise AcceptedRiskInputError(f"{prefix} changed type")
        if type(breakdown.dimension) is not BreakdownDimension:
            raise AcceptedRiskInputError(f"{prefix}.dimension changed type")
        _require_exact_string(breakdown.key, f"{prefix}.key")
        for field_name in (
            "total_count",
            "current_included_count",
            "censored_included_count",
            "disagreement_count",
        ):
            if type(getattr(breakdown, field_name)) is not int:
                raise AcceptedRiskInputError(f"{prefix}.{field_name} changed type")
        for field_name in (
            "current_inclusion_rate",
            "censored_inclusion_rate",
            "disagreement_rate",
        ):
            rate = getattr(breakdown, field_name)
            if type(rate) is not ExactRate:
                raise AcceptedRiskInputError(f"{prefix}.{field_name} changed type")
            if type(rate.numerator) is not int or type(rate.denominator) is not int:
                raise AcceptedRiskInputError(f"{prefix}.{field_name} scalars changed type")


_PINNED_BUILD_REPORT = _build_report
_PINNED_PAIR_SEMANTIC_RECORD = _pair_semantic_record
_PINNED_PAIR_FINGERPRINT = _pair_fingerprint
_PINNED_PAIR_CONTAINER_ROOTS = _pair_container_roots
_PINNED_PREFLIGHT_PAIR_SCALAR_TYPES = _preflight_pair_scalar_types


def _forget_pair(
    identity: int, reference: weakref.ReferenceType[AcceptedRiskInputPair]
) -> None:
    with _PAIR_AUTHORITIES_LOCK:
        current = _PAIR_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _PAIR_AUTHORITIES.pop(identity, None)


def build_accepted_risk_input_pair(capture: CaptureBinding) -> AcceptedRiskInputPair:
    """Derive the two non-pristine views without I/O or outcome access."""
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    require_capture_binding(capture)
    rows = _PINNED_DERIVE_ROWS(capture)
    report = _PINNED_BUILD_REPORT(rows)
    semantic = _PINNED_PAIR_SEMANTIC_RECORD(capture, rows, report)
    pair_sha256 = sha256_bytes(canonical_json_bytes(semantic))
    pair_id = f"arv2-accepted-risk-pair-{pair_sha256[:24]}"
    pair = object.__new__(AcceptedRiskInputPair)
    values: dict[str, object] = {
        "schema": INPUT_PAIR_SCHEMA,
        "contract_id": INPUT_PAIR_CONTRACT_ID,
        "contract_sha256": INPUT_PAIR_CONTRACT_SHA256,
        "pair_id": pair_id,
        "pair_sha256": pair_sha256,
        "capture": capture,
        "rows": rows,
        "report": report,
        "current_view_label": CURRENT_VIEW_LABEL,
        "censored_view_label": CENSORED_VIEW_LABEL,
        "pristine_point_in_time": False,
        "earlier_version_imputation_performed": False,
        "views_share_one_capture": True,
        "guidance_clock_authenticated": False,
        "identity_mapping_authenticated": False,
        "rating_mapping_authenticated": False,
        "signal_rows_constructed": False,
        "production_input_authority": False,
        "outcome_gate_open": False,
        "provider_binding": None,
        "security_master_binding": None,
        "outcome_binding": None,
        "provider_io_performed": False,
        "credential_access_performed": False,
        "filesystem_io_performed": False,
        "quantconnect_io_performed": False,
        "object_store_io_performed": False,
        "market_data_access_performed": False,
        "outcome_access_performed": False,
        "deployment_performed": False,
        "order_access_performed": False,
        "trading_performed": False,
    }
    for name, value in values.items():
        object.__setattr__(pair, name, value)
    _PINNED_PREFLIGHT_PAIR_SCALAR_TYPES(pair)
    fingerprint = _PINNED_PAIR_FINGERPRINT(pair)
    container_authority = capture_frozen_container_authority(
        _PINNED_PAIR_CONTAINER_ROOTS(pair)
    )
    identity = id(pair)
    reference = weakref.ref(pair, lambda ref, key=identity: _forget_pair(key, ref))
    with _PAIR_AUTHORITIES_LOCK:
        _PAIR_AUTHORITIES[identity] = (reference, fingerprint, container_authority)
    return pair


def require_accepted_risk_input_pair(
    pair: AcceptedRiskInputPair,
) -> AcceptedRiskInputPair:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    if type(pair) is not AcceptedRiskInputPair:
        raise AcceptedRiskInputError("pair authority requires an exact AcceptedRiskInputPair")
    with _PAIR_AUTHORITIES_LOCK:
        authority = _PAIR_AUTHORITIES.get(id(pair))
    if authority is None or authority[0]() is not pair:
        raise AcceptedRiskInputError("input pair is not builder-authenticated authority")
    try:
        if not frozen_container_authority_is_current(
            _PINNED_PAIR_CONTAINER_ROOTS(pair), authority[2]
        ):
            raise AcceptedRiskInputError("input pair container topology changed")
        _PINNED_PREFLIGHT_PAIR_SCALAR_TYPES(pair)
    except AttributeError as exc:
        raise AcceptedRiskInputError("input pair state is incomplete") from exc
    if _PINNED_PAIR_FINGERPRINT(pair) != authority[1]:
        raise AcceptedRiskInputError("input pair changed after authentication")
    require_capture_binding(pair.capture)
    expected_rows = _PINNED_DERIVE_ROWS(pair.capture)
    expected_report = _PINNED_BUILD_REPORT(expected_rows)
    expected_semantic = _PINNED_PAIR_SEMANTIC_RECORD(
        pair.capture, expected_rows, expected_report
    )
    expected_sha256 = sha256_bytes(canonical_json_bytes(expected_semantic))
    if (
        pair.schema != INPUT_PAIR_SCHEMA
        or pair.contract_id != INPUT_PAIR_CONTRACT_ID
        or pair.contract_sha256 != INPUT_PAIR_CONTRACT_SHA256
        or pair.rows != expected_rows
        or pair.report != expected_report
        or pair.pair_sha256 != expected_sha256
        or pair.pair_id != f"arv2-accepted-risk-pair-{expected_sha256[:24]}"
        or pair.current_view_label != CURRENT_VIEW_LABEL
        or pair.censored_view_label != CENSORED_VIEW_LABEL
    ):
        raise AcceptedRiskInputError("input pair is not exactly source-derived")
    semantic_flags = (
        pair.pristine_point_in_time,
        pair.earlier_version_imputation_performed,
        pair.guidance_clock_authenticated,
        pair.identity_mapping_authenticated,
        pair.rating_mapping_authenticated,
        pair.signal_rows_constructed,
        pair.production_input_authority,
        pair.outcome_gate_open,
        pair.provider_io_performed,
        pair.credential_access_performed,
        pair.filesystem_io_performed,
        pair.quantconnect_io_performed,
        pair.object_store_io_performed,
        pair.market_data_access_performed,
        pair.outcome_access_performed,
        pair.deployment_performed,
        pair.order_access_performed,
        pair.trading_performed,
    )
    if any(type(flag) is not bool or flag is not False for flag in semantic_flags):
        raise AcceptedRiskInputError("C1 false capability boundary changed")
    if type(pair.views_share_one_capture) is not bool or pair.views_share_one_capture is not True:
        raise AcceptedRiskInputError("C1 views must share one exact capture")
    if any(
        binding is not None
        for binding in (
            pair.provider_binding,
            pair.security_master_binding,
            pair.outcome_binding,
            pair.report.mapping_disagreement_report,
            pair.report.signal_disagreement_report,
        )
    ):
        raise AcceptedRiskInputError("C1 null external/report binding changed")
    return pair


def _current_local_callables() -> tuple[object, ...]:
    """Return every local callable that contributes to C1 authentication."""
    return (
        _require_exact_string,
        _parse_raw_response_results,
        _json_value_fingerprint,
        CapturePageBinding.__post_init__,
        CapturePageBinding.parsed_rows.fget,
        CapturePageBinding.raw_rows.fget,
        CapturePageBinding.raw_response_extraction_verified.fget,
        CapturePageBinding.lineage_record,
        render_redacted_capture_query_bytes,
        _validate_redacted_query,
        _parse_provider_rows_bytes,
        bind_capture_page,
        CaptureRowLocator.__post_init__,
        CaptureRowLocator.sort_key.fget,
        CaptureRowLocator.to_record,
        _capture_manifest_record,
        _capture_fingerprint,
        _forget_capture,
        _validate_page_sequence,
        _candidate_provider_event_id,
        _refuse_duplicate_provider_ids,
        _preflight_capture_scalar_types,
        _capture_container_roots,
        build_capture_binding,
        require_capture_binding,
        ViewEligibility.__post_init__,
        ViewEligibility.to_record,
        AcceptedRiskSourceRow.__post_init__,
        AcceptedRiskSourceRow.to_record,
        ExactRate.__post_init__,
        ExactRate.fraction.fget,
        ExactRate.to_record,
        DispositionCount.__post_init__,
        DispositionCount.to_record,
        DispositionBreakdown.__post_init__,
        DispositionBreakdown.to_record,
        InputPairReport.__post_init__,
        InputPairReport.to_record,
        AcceptedRiskInputPair.current_rows.fget,
        AcceptedRiskInputPair.censored_rows.fget,
        _normalize_explicit_offset_timestamp,
        _guidance_last_updated_calendar_date,
        _guidance_date_only_availability,
        _valid_raw_time,
        _dimension_text,
        _row_dimension_labels,
        _excluded_view,
        _joint_exclusion,
        _derive_source_row,
        _derive_rows,
        _breakdown,
        _build_report,
        _pair_semantic_record,
        _pair_fingerprint,
        _pair_container_roots,
        _require_exact_optional_string,
        _preflight_view_scalar_types,
        _preflight_pair_scalar_types,
        _forget_pair,
        build_accepted_risk_input_pair,
        require_accepted_risk_input_pair,
        _current_record_types,
    )


def _current_record_types() -> tuple[type[object], ...]:
    return (
        CapturePageBinding,
        CaptureRowLocator,
        CaptureBinding,
        ViewEligibility,
        AcceptedRiskSourceRow,
        ExactRate,
        DispositionCount,
        DispositionBreakdown,
        InputPairReport,
        AcceptedRiskInputPair,
    )


_PINNED_CURRENT_LOCAL_CALLABLES = _current_local_callables
_PINNED_LOCAL_CALLABLES = _current_local_callables()
_PINNED_CURRENT_RECORD_TYPES = _current_record_types
_PINNED_RECORD_TYPES = _current_record_types()


__all__ = [
    "AcceptedRiskInputError",
    "AcceptedRiskInputPair",
    "AcceptedRiskSourceRow",
    "BreakdownDimension",
    "CAPTURE_PAGE_SCHEMA",
    "CAPTURE_QUERY_SCHEMA",
    "CAPTURE_SCHEMA",
    "CENSORED_VIEW_LABEL",
    "CURRENT_VIEW_LABEL",
    "CaptureBinding",
    "CapturePageBinding",
    "CaptureRowLocator",
    "DispositionBreakdown",
    "DispositionCount",
    "ExactRate",
    "INPUT_PAIR_CONTRACT_ID",
    "INPUT_PAIR_CONTRACT_SCHEMA",
    "INPUT_PAIR_CONTRACT_SHA256",
    "INPUT_PAIR_REPORT_SCHEMA",
    "INPUT_PAIR_SCHEMA",
    "InputPairReport",
    "InputView",
    "MAX_PROVIDER_ROWS_PER_PAGE",
    "MassiveSourceRole",
    "OWNER_DECISION_ID",
    "RowDisposition",
    "ViewEligibility",
    "accepted_risk_input_pair_contract_record",
    "bind_capture_page",
    "build_accepted_risk_input_pair",
    "build_capture_binding",
    "render_accepted_risk_input_pair_contract_bytes",
    "render_redacted_capture_query_bytes",
    "require_accepted_risk_input_pair",
    "require_capture_binding",
]
