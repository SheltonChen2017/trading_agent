"""Private v3 joins of rewritten provider keys and exact rational observations.

This is not a historical raw-market alias map or an empirical bundle. Current
master classification is not backdated; issuer fundamentals are not a class
denominator; actions do not acquire invented payable/terminal clocks. All
observations, refusals and missing requested cells remain private and intact.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.sharadar_actual_input_binding import _check_financial
from research.short_interest_etf.sharadar_companion_qualification import (
    PROTOCOL_SHA256 as COMPANION_PROTOCOL_SHA256,
    SharadarCompanionQualification,
)
from research.short_interest_etf.sharadar_native_master_index import (
    PROTOCOL_SHA256 as INDEX_PROTOCOL_SHA256,
    SharadarNativeMasterIndex,
    resolve_rewritten_provider_key,
)

SCHEMA = "si-sharadar-native-rational-observation-binding-v3"
INTERFACE_SCHEMA = "si-provider-native-rational-observations-v3"


class SharadarNativeObservationError(ValueError):
    """Named refusals never interpolate private provider observations."""


def _refuse(reason: str) -> SharadarNativeObservationError:
    return SharadarNativeObservationError("REFUSED: " + reason)


def _authority() -> dict[str, Any]:
    return {"source_only": True, "source_admitted": False,
            "point_in_time_data": False, "historical_raw_market_alias_admitted": False,
            "denominator_admitted": False, "payment_or_terminal_economics_admitted": False,
            "ready_for_empirical_backtest": False, "outcome_access_authorized": False,
            "qc_authorized": False, "production_authoritative": False,
            "trading_authority": False, "actual_outcome_looks": 0,
            "allocated_alpha": 0, "qc_attempts": 0}


def _policy() -> dict[str, Any]:
    return {"schema": "si-sharadar-native-rational-observation-protocol-v3",
            "interface_schema": INTERFACE_SCHEMA,
            "companion_protocol_sha256": COMPANION_PROTOCOL_SHA256,
            "native_index_protocol_sha256": INDEX_PROTOCOL_SHA256,
            "key_rule": "Sharadar_rewritten_dataset_keys_only_never_FINRA_or_Massive_raw_alias",
            "tables": {"stocks": "stocks", "daily": "stocks", "fundamentals": "fundamentals"},
            "identity_conflict_rule": "exactly_one_prior_master_native_assertion_must_agree_no_identifiable_refused_peer",
            "financial_rule": "exact_reduced_rationals_no_float_volume_rounding_or_sharefactor_transfer",
            "classification_rule": "current_master_assertions_only_no_backdated_sector_class_or_listing",
            "action_rule": "retain_unbound_actions_without_guessed_label_direction_clock_or_payoff",
            "retention_rule": "all_original_tables_rows_refusals_missing_cells_and_origins_private",
            "population_rule": "captured_full_master_plus_original_ten_token_observations_not_full_study",
            "consumer_rule": "distinct_v3_not_LatestRevisedBundle_or_actual_runner_admission",
            "authority": _authority()}


# Frozen before applying to the retained captures, not an owner verified flag.
PROTOCOL_SHA256 = "583a288d7ccd00679cc3ce468525ab5e845ed62657d9b075a67c35acf0464394"


def observation_protocol() -> dict[str, Any]:
    payload = _policy()
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise _refuse("frozen_native_observation_protocol_hash_mismatch")
    return payload


def _inputs(source: SharadarCompanionQualification, index: SharadarNativeMasterIndex):
    if type(source) is not SharadarCompanionQualification:
        raise _refuse("exact_companion_qualification_required")
    if type(index) is not SharadarNativeMasterIndex:
        raise _refuse("exact_native_index_required")
    observation_protocol()
    return SharadarCompanionQualification.to_payload(source), index.sha256


def _build(source: SharadarCompanionQualification, index: SharadarNativeMasterIndex,
           authenticated=None) -> dict[str, Any]:
    original, digest = _inputs(source, index) if authenticated is None else authenticated
    # The companion parser has already quarantined malformed/duplicate records.
    # Preserve those tables, including refusals, without turning them into rows.
    master = next(table for table in original["tables"] if table["table"] == "tickers")
    identities = {}
    for row in master["rows"]:
        identities.setdefault(row["normalized"]["ticker"], []).append(row)
    refused_prior = {}
    for row in master["refusals"]:
        key = row["ticker"]
        if type(key) is str:
            refused_prior.setdefault(key.strip(), []).append(row)
    observations = []
    for table in original["tables"]:
        kind = table["table"]
        if kind not in {"stocks", "daily", "fundamentals", "actions"}:
            continue
        for row in table["rows"]:
            value = row["normalized"]
            _check_financial(kind, value)
            reasons, resolution = [], None
            if kind == "actions":
                reasons.append("date_only_action_semantics_not_admitted")
            else:
                resolution = resolve_rewritten_provider_key(
                    index, value["ticker"], "fundamentals" if kind == "fundamentals" else "stocks")
                reasons.extend(resolution["refusal_reasons"])
                if refused_prior.get(value["ticker"]):
                    reasons.append("prior_current_master_has_identifiable_refused_peer")
                peers = identities.get(value["ticker"], [])
                if len(peers) != 1:
                    reasons.append("unique_prior_native_identity_assertion_required")
                if peers and resolution["provider_dataset_key_bound"]:
                    if any(peer["normalized"]["provider_security_id"] != resolution["provider_security_id"]
                           for peer in peers):
                        reasons.append("prior_current_master_native_identity_conflict")
            bound = (resolution is not None and resolution["provider_dataset_key_bound"]
                     and not reasons)
            observations.append({
                "table": kind, "source_observation": row,
                "status": "bound_rewritten_provider_observation" if bound else "unresolved_provider_observation",
                "provider_dataset_key_bound": bound,
                "provider_security_id": resolution["provider_security_id"] if bound else None,
                "native_resolution": resolution,
                "prior_current_master_assertions": identities.get(value["ticker"], []),
                "prior_current_master_refusals": refused_prior.get(value["ticker"], []),
                "lookup_semantic": "source_rewritten_provider_key_not_historical_raw_market_alias",
                "same_share_class_denominator": None,
                "historical_effective_intervals": [], "refusal_reasons": sorted(set(reasons)),
            })
    payload = {"schema": SCHEMA, "interface_schema": INTERFACE_SCHEMA,
               "protocol_sha256": PROTOCOL_SHA256,
               "native_index_sha256": digest,
               "source_report_sha256": original["report_sha256"],
               "source_capture_identity_sha256": original["capture_identity_sha256"],
               "source_protocol_sha256": original["protocol_sha256"],
               "source_retrieved_at": original["retrieved_at"],
               "publication_scope": "private_only_not_data_usability_publication",
               "population_scope": "full_captured_master_original_ten_token_observations_not_full_study",
               "source_tables": original["tables"], "observations": observations,
               "consumer_type": "not_LatestRevisedBundle", "authority": _authority()}
    payload["binding_sha256"] = hash_payload(payload)
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class SharadarNativeObservations:
    qualification: SharadarCompanionQualification = dataclasses.field(repr=False)
    native_index: SharadarNativeMasterIndex = dataclasses.field(repr=False)
    _source_sha256: str = dataclasses.field(init=False, repr=False)
    _index_sha256: str = dataclasses.field(init=False, repr=False)
    _payload_json: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        if type(self) is not SharadarNativeObservations:
            raise _refuse("exact_native_observations_required")
        payload = _build(self.qualification, self.native_index)
        object.__setattr__(self, "_source_sha256", payload["source_report_sha256"])
        object.__setattr__(self, "_index_sha256", payload["native_index_sha256"])
        object.__setattr__(self, "_payload_json", canonical_json(payload))

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not SharadarNativeObservations:
            raise _refuse("exact_native_observations_required")
        inputs = _inputs(self.qualification, self.native_index)
        if inputs[0]["report_sha256"] != self._source_sha256 or inputs[1] != self._index_sha256:
            raise _refuse("native_observation_source_identity_changed")
        expected = canonical_json(_build(self.qualification, self.native_index, inputs))
        if type(self._payload_json) is not str or self._payload_json != expected:
            raise _refuse("native_observation_binding_changed")
        return json.loads(expected)

    @property
    def sha256(self) -> str:
        return self.to_payload()["binding_sha256"]


def bind_sharadar_native_observations(qualification: SharadarCompanionQualification,
                                     native_index: SharadarNativeMasterIndex) -> SharadarNativeObservations:
    return SharadarNativeObservations(qualification, native_index)
