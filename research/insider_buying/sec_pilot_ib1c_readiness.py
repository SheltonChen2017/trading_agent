"""In-memory IB-1C blocker inventory for the retained sixteen-filing pilot.

This is an assessment of already-verified, noncanonical projections. It does
not create an IB-1C metadata source, parse a filing into a signal, read a path,
or change any source, outcome, or trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from data.hashing import hash_payload
from research.insider_buying.sec_raw_parent_projection import (
    SecRawParentProjection,
    SecRawParentProjectionError,
)
from research.insider_buying_sec_pilot_projection_adapter import (
    OFFLINE_PILOT_ADAPTER_VERSION,
    SecOfflinePilotAdapterError,
    SecOfflinePilotProjectionReceipt,
)


SEC_PILOT_IB1C_READINESS_VERSION = "INSETF-SEC-PILOT-IB1C-BLOCKERS-v1"
_ROW_BLOCKERS = (
    "VERBATIM_IB1C_METADATA_SOURCE_UNAVAILABLE",
    "RETRIEVAL_TIMESTAMP_UNAVAILABLE",
    "OFFICIAL_SEC_METADATA_PROFILE_UNVERIFIED",
    "TIMEZONE_INTERPRETATION_UNVERIFIED",
    "SOURCE_AUTHENTICITY_UNVERIFIED",
    "DIRECT_IB1C_INGEST_NOT_AUTHORIZED",
)
_AMENDMENT_BLOCKER = "AMENDMENT_ORIGINAL_ACCESSION_LINK_UNAVAILABLE"
_CORPUS_BLOCKERS = (
    "CONTINUATION_JOURNAL_NOT_REPLAYED",
    "FIRST_PASS_CODE_SHA_ARTIFACT_UNVERIFIED",
    "FIRST_PASS_PACING_TRACE_UNVERIFIED",
    "CANONICAL_82_QUARTER_CORPUS_INCOMPLETE",
)
_FALSE_AUTHORITY = frozenset({
    "canonical_evidence", "point_in_time_data", "source_authenticated",
    "timezone_interpretation_verified", "official_sec_profile_verified",
    "direct_ib1c_ingest_authorized", "prior_code_sha_artifact_verified",
    "first_pass_pacing_trace_verified", "continuation_journal_replayed",
    "outcome_access_authorized",
})
_ZERO_AUTHORITY = frozenset({
    "research_looks", "authorized_outcome_looks", "consumed_outcome_looks",
})
_PARENT_FALSE_AUTHORITY = frozenset({
    "network_access_authorized", "direct_ib1c_ingest_authorized",
    "canonical_evidence", "point_in_time_data", "source_authenticated",
    "official_sec_profile_verified", "timezone_interpretation_verified",
    "prior_code_sha_artifact_verified", "first_pass_pacing_trace_verified",
    "completeness_verified",
})
_PARENT_ZERO_AUTHORITY = frozenset({
    "research_looks", "authorized_outcome_looks", "consumed_outcome_looks",
})
_TOKEN = object()


class SecPilotIb1cReadinessError(ValueError):
    """A purported fixed-pilot blocker report is incomplete or promoted."""


def _refuse(reason: str) -> None:
    raise SecPilotIb1cReadinessError(f"REFUSED: {reason}")


@dataclass(frozen=True)
class SecPilotIb1cReadinessRow:
    """Immutable provenance and known missing gates for one retained accession."""

    period: str
    accession_number: str
    form_type: str
    projection_sha256: str
    raw_parent_sha256s: tuple[tuple[str, str], ...]
    derived_projection_sha256: str
    reporting_owner_count: int
    blockers: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "period": self.period,
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "projection_sha256": self.projection_sha256,
            "raw_parent_sha256s": dict(self.raw_parent_sha256s),
            "derived_projection_sha256": self.derived_projection_sha256,
            "reporting_owner_count": self.reporting_owner_count,
            "blockers": list(self.blockers),
        }


def _checked_rows(
    receipt: SecOfflinePilotProjectionReceipt,
) -> tuple[str, str, str, tuple[SecPilotIb1cReadinessRow, ...]]:
    if type(receipt) is not SecOfflinePilotProjectionReceipt:
        _refuse("an exact fixed-pilot projection receipt is required")
    try:
        source = receipt.to_payload()
    except (SecOfflinePilotAdapterError, SecRawParentProjectionError) as exc:
        raise SecPilotIb1cReadinessError("REFUSED: pilot receipt no longer validates") from exc
    if type(source) is not dict or set(source) != {
        "version", "source_report_sha256", "source_inventory_sha256", "rows", "authority",
    } or source["version"] != OFFLINE_PILOT_ADAPTER_VERSION:
        _refuse("pilot receipt schema or version drifted")
    authority = source["authority"]
    if (type(authority) is not dict
            or set(authority) != _FALSE_AUTHORITY | _ZERO_AUTHORITY | {"input_scope"}
            or authority["input_scope"] not in {
                "retained_noncanonical_pilot", "synthetic_test_receipt",
            }
            or authority["input_scope"] != (
                "retained_noncanonical_pilot" if receipt._public_pilot
                else "synthetic_test_receipt"
            )
            or any(authority[key] is not False for key in _FALSE_AUTHORITY)
            or any(type(authority[key]) is not int or authority[key] != 0
                   for key in _ZERO_AUTHORITY)):
        _refuse("pilot receipt has positive or unknown authority")
    source_rows = source["rows"]
    if (type(source_rows) is not list or len(source_rows) != 16
            or type(receipt.projections) is not tuple or len(receipt.projections) != 16):
        _refuse("pilot receipt does not contain exactly sixteen projections")
    rows: list[SecPilotIb1cReadinessRow] = []
    for source_row, projection in zip(source_rows, receipt.projections, strict=True):
        if type(projection) is not SecRawParentProjection:
            _refuse("pilot projection type is not exact")
        try:
            projected = projection.to_payload()
            projection_sha256 = projection.sha256
        except SecRawParentProjectionError as exc:
            raise SecPilotIb1cReadinessError("REFUSED: pilot projection no longer validates") from exc
        parent_authority = projected["authority"]
        if (type(parent_authority) is not dict
                or set(parent_authority) != _PARENT_FALSE_AUTHORITY
                | _PARENT_ZERO_AUTHORITY | {
                    "synthetic_only", "retrieval_timestamp_unavailable",
                }
                or parent_authority["synthetic_only"] is not True
                or parent_authority["retrieval_timestamp_unavailable"] is not True
                or any(parent_authority[key] is not False
                       for key in _PARENT_FALSE_AUTHORITY)
                or any(type(parent_authority[key]) is not int
                       or parent_authority[key] != 0
                       for key in _PARENT_ZERO_AUTHORITY)):
            _refuse("raw parent claims authority absent from the pilot")
        target = projected["target"]
        derived = projected["derived_projection"]
        hashes = tuple(
            (role, projected["raw_parents"][role]["sha256"])
            for role in ("index", "header", "xml")
        )
        if (type(source_row) is not dict
                or set(source_row) != {
                    "accession_number", "period", "form_type", "projection_sha256",
                    "raw_parent_hashes", "derived_projection_sha256",
                }
                or source_row["accession_number"] != target["accession_number"]
                or source_row["period"] != target["period"]
                or source_row["form_type"] != target["form_type"]
                or source_row["projection_sha256"] != projection_sha256
                or source_row["raw_parent_hashes"] != dict(hashes)
                or source_row["derived_projection_sha256"] != derived["sha256"]
                or target["form_type"] not in {"4", "4/A"}
                or type(derived["reporting_owner_count"]) is not int
                or not 1 <= derived["reporting_owner_count"] <= 256
                or derived["buyer_attribution_available"] is not False
                or derived["ib1c_profile_compatible"] is not False
                or derived["amendment_original_accession_unavailable"]
                is not (target["form_type"] == "4/A")):
            _refuse("pilot projection disagrees with its source row or blocker state")
        blockers = _ROW_BLOCKERS + (
            (_AMENDMENT_BLOCKER,) if target["form_type"] == "4/A" else ()
        )
        rows.append(SecPilotIb1cReadinessRow(
            period=target["period"],
            accession_number=target["accession_number"],
            form_type=target["form_type"],
            projection_sha256=projection_sha256,
            raw_parent_sha256s=hashes,
            derived_projection_sha256=derived["sha256"],
            reporting_owner_count=derived["reporting_owner_count"],
            blockers=blockers,
        ))
    return (
        authority["input_scope"],
        source["source_report_sha256"], source["source_inventory_sha256"],
        tuple(rows),
    )


@dataclass(frozen=True)
class SecPilotIb1cReadinessReport:
    """Factory-bound blocker report, never an IB-1C pass or evidence bundle."""

    _receipt: SecOfflinePilotProjectionReceipt = field(repr=False, compare=False)
    input_scope: str
    source_report_sha256: str
    source_inventory_sha256: str
    rows: tuple[SecPilotIb1cReadinessRow, ...]
    _token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if self._token is not _TOKEN or (
            self.input_scope, self.source_report_sha256,
            self.source_inventory_sha256, self.rows,
        ) != _checked_rows(self._receipt):
            _refuse("readiness report was not built from its verified pilot receipt")

    def to_payload(self) -> dict[str, object]:
        self._validate()
        return {
            "version": SEC_PILOT_IB1C_READINESS_VERSION,
            "input_scope": self.input_scope,
            "source_report_sha256": self.source_report_sha256,
            "source_inventory_sha256": self.source_inventory_sha256,
            "rows": [row.to_payload() for row in self.rows],
            "corpus_blockers": list(_CORPUS_BLOCKERS),
            "authority": {
                "ib1c_ready": False,
                "canonical_evidence": False,
                "point_in_time_data": False,
                "outcome_access_authorized": False,
                "research_looks": 0,
                "authorized_outcome_looks": 0,
                "consumed_outcome_looks": 0,
            },
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def assess_sec_pilot_ib1c_readiness(
    receipt: SecOfflinePilotProjectionReceipt,
) -> SecPilotIb1cReadinessReport:
    """Describe exact-16 gaps in memory; never materialize an IB-1C source."""
    scope, report_sha, inventory_sha, rows = _checked_rows(receipt)
    return SecPilotIb1cReadinessReport(
        _receipt=receipt, input_scope=scope,
        source_report_sha256=report_sha,
        source_inventory_sha256=inventory_sha,
        rows=rows, _token=_TOKEN,
    )
