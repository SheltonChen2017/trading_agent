"""Private v2 source-only binding inventory, never an empirical input permit.

Provider permatickers, observed share-class identifiers and rational financial
observations retain separate provenance.  Current reference assertions and
price-date ranges never become historical identity intervals.  This inventory
does not implement LatestRevisedBundle and cannot enter its ranking or replay
path.  Its rows and source-fitness conclusions must remain in protected storage.
"""
from __future__ import annotations

import dataclasses
import json
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.sharadar_companion_qualification import (
    PROTOCOL_SHA256 as SHARADAR_PROTOCOL_SHA256,
    SYMBOLS,
    SharadarCompanionQualification,
)

if TYPE_CHECKING:
    from research.short_interest_etf.massive_action_supplement import (
        MassiveActionSupplementQualification,
    )

SCHEMA = "si-sharadar-actual-input-binding-v2"
INTERFACE_SCHEMA = "si-provider-rational-source-only-v2"
_GAPS = (
    "historical_ticker_to_Sharadar_permaticker_link_not_established",
    "same_share_class_outstanding_denominator_not_admitted",
    "effective_historical_classification_and_taxonomy_not_established",
    "rational_price_volume_history_not_admitted_for_empirical_replay",
    "corporate_action_effective_payment_and_terminal_economics_not_admitted",
    "ten_token_source_sample_not_full_structural_study_population",
    "prospective_actual_outcome_look_and_exact_QC_processing_route_not_registered",
    "original_SI_vintages_all_corrections_and_actual_availability_not_established",
)


class SharadarActualInputBindingError(ValueError):
    """Unbound source objects cannot become an actual-input admission."""


def _refuse(reason: str) -> SharadarActualInputBindingError:
    # Never include provider rows, identifiers, response bodies or credentials.
    return SharadarActualInputBindingError("REFUSED: " + reason)


def _authority() -> dict[str, Any]:
    return {
        "source_only": True, "source_admitted": False, "point_in_time_data": False,
        "ready_for_empirical_backtest": False, "outcome_access_authorized": False,
        "qc_authorized": False, "production_authoritative": False,
        "trading_authority": False, "actual_outcome_looks": 0,
        "allocated_alpha": 0, "qc_attempts": 0,
    }


def _policy() -> dict[str, Any]:
    return {
        "schema": "si-sharadar-actual-input-binding-protocol-v2",
        "interface_schema": INTERFACE_SCHEMA,
        "source_protocol_sha256": SHARADAR_PROTOCOL_SHA256,
        "input_rule": "exact_revalidated_qualification_objects_not_caller_claims",
        "identifier_rule": "retain_Sharadar_permaticker_namespace_no_FIGI_cast",
        "reference_rule": "current_assertions_never_backdated_no_price_interval_inference",
        "matching_rule": "ticker_and_exact_requested_date_candidates_not_identity_admission",
        "financial_rule": "exact_reduced_rationals_no_rounding_or_sharefactor_transfer",
        "denominator_rule": "primary_class_fundamentals_remain_quarantined",
        "event_rule": "retain_date_only_actions_no_invented_clock_or_terminal_zero",
        "population_rule": "preserve_every_source_row_refusal_and_missing_token",
        "consumer_rule": "not_LatestRevisedBundle_no_ranking_order_or_runner_access",
        "publication_scope": "private_only_not_data_usability_publication",
        "public_known_contract_gaps": list(_GAPS), "authority": _authority(),
    }


# Independently pinned from the prospective detached interface specification.
PROTOCOL_SHA256 = "67e0a920f0acc312057719a6994c7b46309b38e9ae8bcd2684682266ee3433c4"


def binding_protocol() -> dict[str, Any]:
    payload = _policy()
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise _refuse("frozen_binding_protocol_hash_mismatch")
    return payload


def _rational(value: Any, *, positive: bool = False, nullable: bool = False,
              signed: bool = False) -> None:
    if value is None and nullable:
        return
    if (type(value) is not dict or set(value) != {"numerator", "denominator"}
            or type(value["numerator"]) is not int or type(value["denominator"]) is not int
            or value["denominator"] <= 0):
        raise _refuse("invalid_exact_rational")
    amount = Fraction(value["numerator"], value["denominator"])
    if ((amount.numerator, amount.denominator)
            != (value["numerator"], value["denominator"])):
        raise _refuse("noncanonical_rational")
    if (positive and amount <= 0) or (not signed and amount < 0):
        raise _refuse("invalid_rational_sign")


def _source(qualification: SharadarCompanionQualification) -> dict[str, Any]:
    if type(qualification) is not SharadarCompanionQualification:
        raise _refuse("exact_Sharadar_qualification_type_required")
    return SharadarCompanionQualification.to_payload(qualification)


def _supplement(supplement: MassiveActionSupplementQualification | None) -> dict | None:
    if supplement is None:
        return None
    from research.short_interest_etf.massive_action_supplement import (
        MassiveActionSupplementQualification,
    )
    if type(supplement) is not MassiveActionSupplementQualification:
        raise _refuse("exact_Massive_supplement_type_required")
    return MassiveActionSupplementQualification.to_payload(supplement)


def _check_financial(table: str, row: dict[str, Any]) -> None:
    if table == "stocks":
        for name in ("raw_open", "raw_high", "raw_low", "raw_close"):
            _rational(row[name], positive=True)
        _rational(row["raw_volume"])
    elif table == "daily":
        _rational(row["market_cap_USD"], nullable=True)
    elif table == "fundamentals":
        for name in ("sharesbas", "sharefactor"):
            _rational(row[name], positive=True, nullable=True)
        _rational(row["market_cap_USD"], nullable=True)
        if row["primary_share_class_only"] is not True:
            raise _refuse("primary_share_class_contract_changed")
    elif table == "actions":
        _rational(row["value"], nullable=True, signed=True)
        if row["payment_timestamp"] is not None or row["terminal_economics_admitted"] is not False:
            raise _refuse("source_action_authority_changed")


def _build(qualification: SharadarCompanionQualification,
           supplement: MassiveActionSupplementQualification | None) -> dict[str, Any]:
    binding_protocol()
    source, extra = _source(qualification), _supplement(supplement)
    ticker_table = next(table for table in source["tables"] if table["table"] == "tickers")
    identities = ticker_table["rows"]
    references = [] if extra is None else [
        row for table in extra["tables"] if table["table"] == "reference"
        for row in table["rows"]
    ]
    candidates = []
    for table in source["tables"]:
        kind = table["table"]
        if kind not in {"stocks", "daily", "fundamentals", "actions"}:
            continue
        for row in table["rows"]:
            normalized = row["normalized"]
            _check_financial(kind, normalized)
            ticker = normalized["ticker"]
            observed_date = normalized.get("session", normalized.get("date_key", normalized.get("date")))
            provider_candidates = [item for item in identities
                                   if item["normalized"]["ticker"] == ticker]
            dated_candidates = [item for item in references
                                if item["normalized"]["ticker"] == ticker
                                and item["normalized"]["query_date"] == observed_date]
            reasons = ["historical_ticker_to_permaticker_link_not_established"]
            if not provider_candidates:
                reasons.append("missing_current_provider_identity_assertion")
            elif len({item["normalized"]["provider_security_id"]
                      for item in provider_candidates}) != 1:
                reasons.append("ambiguous_current_provider_identity_assertions")
            if not dated_candidates:
                reasons.append("no_exact_date_reference_candidate")
            elif len(dated_candidates) != 1:
                reasons.append("ambiguous_exact_date_reference_candidates")
            if kind == "fundamentals":
                reasons.extend(("primary_class_only_no_secondary_denominator_transfer",
                                "same_share_class_denominator_not_admitted"))
            if kind == "actions":
                reasons.append("date_only_action_has_no_admitted_effective_payment_or_terminal_clock")
            candidates.append({
                "table": kind, "source_observation": row,
                "current_provider_identity_candidates": provider_candidates,
                "exact_date_reference_candidates": dated_candidates,
                "matching_semantic": "raw_ticker_exact_date_only_not_identity_admission",
                "binding_status": "unadmitted_source_only_candidate",
                "historical_ticker_permaticker_link": None,
                "same_share_class_denominator": None,
                "refusal_reasons": sorted(reasons),
            })
    payload = {
        "schema": SCHEMA, "interface_schema": INTERFACE_SCHEMA,
        "protocol_sha256": PROTOCOL_SHA256,
        "source_report_sha256": source["report_sha256"],
        "source_capture_identity_sha256": source["capture_identity_sha256"],
        "source_protocol_sha256": source["protocol_sha256"],
        "source_retrieved_at": source["retrieved_at"],
        "supplement_report_sha256": None if extra is None else extra["report_sha256"],
        "supplement_capture_identity_sha256": None if extra is None else extra["capture_identity_sha256"],
        "supplement_protocol_sha256": None if extra is None else extra["protocol_sha256"],
        "supplement_retrieved_at": None if extra is None else extra["retrieved_at"],
        "publication_scope": "private_only_not_data_usability_publication",
        "population_scope": "ten_distinct_raw_tokens_source_sample_not_full_study",
        "requested_raw_tokens": list(SYMBOLS),
        "provider_identity_assertions": identities,
        "source_tables": source["tables"],
        "supplement_tables": [] if extra is None else extra["tables"],
        "candidate_bindings": candidates,
        "required_factual_qualifications": list(_GAPS), "authority": _authority(),
    }
    payload["binding_sha256"] = hash_payload(payload)
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class SharadarActualInputBinding:
    """Exact revalidated source objects and detached private inventory."""

    qualification: SharadarCompanionQualification = dataclasses.field(repr=False)
    supplement: MassiveActionSupplementQualification | None = dataclasses.field(default=None, repr=False)
    _source_sha256: str = dataclasses.field(init=False, repr=False)
    _supplement_sha256: str | None = dataclasses.field(init=False, repr=False)
    _payload_json: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self) is not SharadarActualInputBinding:
            raise _refuse("exact_binding_type_required")
        payload = _build(self.qualification, self.supplement)
        object.__setattr__(self, "_source_sha256", payload["source_report_sha256"])
        object.__setattr__(self, "_supplement_sha256", payload["supplement_report_sha256"])
        object.__setattr__(self, "_payload_json", canonical_json(payload))

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not SharadarActualInputBinding:
            raise _refuse("exact_binding_type_required")
        expected = _build(self.qualification, self.supplement)
        if (expected["source_report_sha256"] != self._source_sha256
                or expected["supplement_report_sha256"] != self._supplement_sha256):
            raise _refuse("captured_source_identity_changed")
        if type(self._payload_json) is not str or self._payload_json != canonical_json(expected):
            raise _refuse("binding_inventory_changed")
        return json.loads(self._payload_json)

    @property
    def sha256(self) -> str:
        return SharadarActualInputBinding.to_payload(self)["binding_sha256"]


def bind_sharadar_companion(
    qualification: SharadarCompanionQualification,
    supplement: MassiveActionSupplementQualification | None = None,
) -> SharadarActualInputBinding:
    """Bind source provenance without permitting prices, outcomes or QC use."""
    return SharadarActualInputBinding(qualification, supplement)
