"""Pure, source-only v2 quarter and downstream scope coverage.

Every assessed row remains visible to pilot/scale consumers. Corroborated
identity is agreement between supplied sources, never financial eligibility,
SEC authenticity, acceptance/PIT timing, rights, or execution permission.
This module does not load artifacts: callers separately prove raw-bound
artifact replay and the externally supplied producer metadata.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, fields
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    _upstream_submission_filing_date,
)
from research.insider_buying.sec_ib1c_identity_v2 import (
    IDENTITY_V2_VERSION, IDENTITY_V2_EVIDENCE_EPOCH, Ib1cV2IdentityAssessment,
    _authority,
)


QUARTER_COVERAGE_VERSION = "INSETF-IB1C-V2-DOWNSTREAM-QUARTER-v1"
SCOPE_COVERAGE_VERSION = "INSETF-IB1C-V2-DOWNSTREAM-SCOPE-v1"
COVERAGE_EVIDENCE_EPOCH = "INSETF-IB1C-V2-DOWNSTREAM-SOURCE-ONLY-v1"
EXPECTED_PERIODS = tuple(f"{year}Q{quarter}" for year in range(2006, 2027)
                         for quarter in range(1, 5) if (year, quarter) <= (2026, 2))
MAX_QUARTER_FILINGS = 500_000
MAX_TOTAL_FILINGS = 5_000_000
MAX_ASSESSMENT_ENVELOPE_BYTES = 128 * 1024 * 1024
_FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")
_REASONS = {
    "unsupported_parent_corroboration_form", "complete_parent_corroboration_missing",
    "complete_parent_identity_conflict",
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_ROW_KEYS = {
    "period", "source_record_ordinal", "accession_number", "form_type",
    "raw_filing_date", "filing_date", "raw_issuer_cik", "issuer_comparison_key",
    "short_cik", "accession_year_mismatch", "submission_row_id",
    "raw_archive_sha256", "raw_submission_member_sha256", "parsed_lineage_hash",
    "corroboration", "disposition", "quarantine_reasons",
}
_ASSESSMENT_KEYS = {
    "kind", "evidence_epoch", "period", "scope", "parsed_snapshot_id",
    "parsed_lineage_hash", "census_quarter_sha256", "rows", "submission_count",
    "corroborated_count", "quarantined_count", "short_cik_count",
    "accession_year_mismatch_count", "accounting_sha256",
    "whole_quarter_identity_sha256", "authority",
}
_QUARTER_TOKEN = object()
_SCOPE_TOKEN = object()


class V2DownstreamCoverageError(ValueError):
    """A supplied v2 context or downstream composition failed closed."""


def _refuse(reason: str) -> None:
    raise V2DownstreamCoverageError("REFUSED: " + reason)


def _sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class V2PreparationBinding:
    """Externally pinned producer context; its shape is not an attestation."""

    period: str
    producer_commit: str
    producer_source_inventory_sha256: str
    completion_envelope_sha256: str
    assessment_envelope_sha256: str
    assessment_envelope_bytes: int
    raw_snapshot_id: str
    raw_lineage_sha256: str
    parsed_snapshot_id: str
    parsed_lineage_sha256: str
    profile_sha256: str
    census_quarter_sha256: str

    def __post_init__(self) -> None:
        if (type(self) is not V2PreparationBinding or type(self.period) is not str
                or self.period not in EXPECTED_PERIODS
                or type(self.producer_commit) is not str
                or _COMMIT.fullmatch(self.producer_commit) is None
                or any(not _sha(getattr(self, name)) for name in (
                    "producer_source_inventory_sha256", "completion_envelope_sha256",
                    "assessment_envelope_sha256", "raw_lineage_sha256",
                    "parsed_lineage_sha256", "profile_sha256", "census_quarter_sha256"))
                or type(self.assessment_envelope_bytes) is not int
                or not 0 < self.assessment_envelope_bytes <= MAX_ASSESSMENT_ENVELOPE_BYTES):
            _refuse("preparation binding types, period, hashes or byte cap differ")
        period = self.period.lower()
        if (type(self.raw_snapshot_id) is not str
                or self.raw_snapshot_id != f"sec-insider-bulk-{period}-{self.raw_lineage_sha256[:16]}"
                or type(self.parsed_snapshot_id) is not str
                or self.parsed_snapshot_id != f"sec-insider-parsed-{period}-{self.parsed_lineage_sha256[:16]}"):
            _refuse("preparation snapshot identifiers differ from their full lineage")

    def to_payload(self) -> dict[str, object]:
        self.__post_init__()
        return {item.name: getattr(self, item.name) for item in fields(self)}


def _validate_assessment(assessment: Ib1cV2IdentityAssessment, binding: V2PreparationBinding):
    if type(assessment) is not Ib1cV2IdentityAssessment or type(binding) is not V2PreparationBinding:
        _refuse("an exact factory assessment and preparation binding are required")
    declared = binding.to_payload()
    body = assessment.to_payload()
    assessment_sha = assessment.sha256
    if (type(body) is not dict or set(body) != _ASSESSMENT_KEYS
            or body["kind"] != IDENTITY_V2_VERSION
            or body["evidence_epoch"] != IDENTITY_V2_EVIDENCE_EPOCH
            or body["scope"] != "all_six_ownership_forms"
            or body["period"] != binding.period
            or body["parsed_snapshot_id"] != binding.parsed_snapshot_id
            or body["parsed_lineage_hash"] != binding.parsed_lineage_sha256
            or body["census_quarter_sha256"] != binding.census_quarter_sha256
            or hash_payload(body) != assessment_sha
            or type(body["authority"]) is not dict
            or set(body["authority"]) != set(_authority())
            or any(type(body["authority"][name]) is not type(value)
                   or body["authority"][name] != value for name, value in _authority().items())):
        _refuse("assessment policy, epoch, producer context or authority differs")
    envelope = (canonical_json({"payload": body, "payload_sha256": assessment_sha}) + "\n").encode("utf-8")
    if (len(envelope) != binding.assessment_envelope_bytes
            or hash_bytes(envelope) != binding.assessment_envelope_sha256):
        _refuse("assessment envelope differs from the external preparation binding")
    rows = body["rows"]
    if type(rows) is not list or len(rows) > MAX_QUARTER_FILINGS:
        _refuse("quarter assessment rows exceed the exact bounded list")
    seen, archive_hashes, member_hashes = set(), set(), set()
    dialect = None
    counts = Counter()
    forms, reasons = Counter(), Counter()
    for ordinal, row in enumerate(rows, start=1):
        if (type(row) is not dict or set(row) != _ROW_KEYS
                or row["period"] != binding.period
                or type(row["source_record_ordinal"]) is not int
                or row["source_record_ordinal"] != ordinal
                or type(row["accession_number"]) is not str
                or _ACCESSION.fullmatch(row["accession_number"]) is None
                or row["accession_number"] in seen
                or type(row["form_type"]) is not str or row["form_type"] not in _FORMS
                or any(not _sha(row[name]) for name in (
                    "submission_row_id", "raw_archive_sha256", "raw_submission_member_sha256",
                    "parsed_lineage_hash"))
                or row["parsed_lineage_hash"] != binding.parsed_lineage_sha256):
            _refuse("assessment row identity, ordinal, form or lineage differs")
        seen.add(row["accession_number"])
        archive_hashes.add(row["raw_archive_sha256"])
        member_hashes.add(row["raw_submission_member_sha256"])
        if (type(row["raw_issuer_cik"]) is not str
                or _CIK.fullmatch(row["raw_issuer_cik"]) is None
                or int(row["raw_issuer_cik"]) == 0
                or row["issuer_comparison_key"] != row["raw_issuer_cik"].zfill(10)
                or type(row["short_cik"]) is not bool
                or row["short_cik"] != (len(row["raw_issuer_cik"]) < 10)):
            _refuse("raw issuer CIK or comparison-only short-CIK flag differs")
        filed, current_dialect = _upstream_submission_filing_date(row["raw_filing_date"])
        if (dialect is not None and dialect != current_dialect
                or (filed.year, (filed.month - 1) // 3 + 1)
                != (int(binding.period[:4]), int(binding.period[-1]))
                or row["filing_date"] != filed.isoformat()
                or type(row["accession_year_mismatch"]) is not bool
                or row["accession_year_mismatch"] != (int(row["accession_number"][11:13]) != filed.year % 100)):
            _refuse("raw filing date, quarter, dialect or year-mismatch flag differs")
        dialect = current_dialect
        evidence = row["corroboration"]
        if evidence is not None and (type(evidence) is not dict or set(evidence) != {
                "projection_sha256", "parent_sha256", "header_sha256", "xml_sha256", "declared_index_sha256"}
                or any(not _sha(value) for value in evidence.values())):
            _refuse("corroboration descriptor is malformed")
        expected_reasons = (["unsupported_parent_corroboration_form"] if row["form_type"] not in {"4", "4/A"}
                            else ["complete_parent_corroboration_missing"] if evidence is None
                            else [] if row["disposition"] == "corroborated_noncanonical"
                            else ["complete_parent_identity_conflict"])
        if (type(row["quarantine_reasons"]) is not list
                or row["quarantine_reasons"] != expected_reasons
                or row["disposition"] != ("quarantined" if expected_reasons else "corroborated_noncanonical")):
            _refuse("row disposition does not preserve supported corroboration or quarantine")
        counts[row["disposition"]] += 1
        counts["short_cik"] += row["short_cik"]
        counts["accession_year_mismatch"] += row["accession_year_mismatch"]
        forms[row["form_type"]] += 1
        reasons.update(row["quarantine_reasons"])
    accounting_sha = hash_payload(rows)
    identity_complete = bool(rows) and counts["quarantined"] == 0
    if (len(archive_hashes) > 1 or len(member_hashes) > 1
            or body["accounting_sha256"] != accounting_sha
            or body["whole_quarter_identity_sha256"] != (accounting_sha if identity_complete else None)
            or any(type(body[name]) is not int or body[name] != value for name, value in (
                ("submission_count", len(rows)), ("corroborated_count", counts["corroborated_noncanonical"]),
                ("quarantined_count", counts["quarantined"]), ("short_cik_count", counts["short_cik"]),
                ("accession_year_mismatch_count", counts["accession_year_mismatch"])))):
        _refuse("assessment complete accounting or withheld identity digest differs")
    return declared, body, assessment_sha, forms, reasons, identity_complete


@dataclass(frozen=True, slots=True)
class V2QuarterCoverage:
    """Factory-sealed all-row quarter view; returned payloads are detached."""

    _summary_raw: bytes = field(repr=False)
    _rows_raw: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_bytes: tuple[bytes, bytes] | None = field(default=None, init=False, repr=False, compare=False)

    def _check(self) -> None:
        if (type(self) is not V2QuarterCoverage or self._token is not _QUARTER_TOKEN
                or type(self._summary_raw) is not bytes or type(self._rows_raw) is not bytes
                or self._factory_bytes != (self._summary_raw, self._rows_raw)):
            _refuse("quarter coverage was not built here or was altered")

    def to_payload(self) -> dict[str, object]:
        self._check()
        return json.loads(self._summary_raw)

    @property
    def sha256(self) -> str:
        self._check()
        return hash_bytes(self._summary_raw)

    def pilot_rows(self) -> list[dict[str, object]]:
        """Retain every row; this is not an old-pilot admission operation."""
        self._check()
        return json.loads(self._rows_raw)

    def admitted_rows(self) -> list[dict[str, object]]:
        """Return source-corroborated, still-noncanonical identities only."""
        return [row for row in self.pilot_rows() if row["disposition"] == "corroborated_noncanonical"]


def build_v2_quarter_coverage(assessment: Ib1cV2IdentityAssessment,
                              binding: V2PreparationBinding) -> V2QuarterCoverage:
    """Consume a sealed assessment without claiming artifact I/O or origin."""
    try:
        declared, body, assessment_sha, forms, reasons, complete = _validate_assessment(assessment, binding)
        summary = {
            "kind": QUARTER_COVERAGE_VERSION, "evidence_epoch": COVERAGE_EVIDENCE_EPOCH,
            "policy_version": IDENTITY_V2_VERSION, "policy_epoch": IDENTITY_V2_EVIDENCE_EPOCH,
            "period": binding.period, "preparation_binding": declared,
            "assessment_sha256": assessment_sha, "rows_sha256": body["accounting_sha256"],
            **{name: body[name] for name in (
                "submission_count", "corroborated_count", "quarantined_count",
                "short_cik_count", "accession_year_mismatch_count")},
            "form_counts": {name: forms[name] for name in _FORMS},
            "quarantine_reason_counts": {name: reasons[name] for name in sorted(_REASONS)},
            "source_identity_complete": complete,
            "source_identity_sha256": body["whole_quarter_identity_sha256"],
            "artifact_loading_verified_here": False,
            "binding_is_external_attestation": False,
            "authority": _authority(),
        }
        result = V2QuarterCoverage(canonical_json(summary).encode("utf-8"),
                                   canonical_json(body["rows"]).encode("utf-8"), _QUARTER_TOKEN)
        object.__setattr__(result, "_factory_bytes", (result._summary_raw, result._rows_raw))
        return result
    except V2DownstreamCoverageError:
        raise
    except (AttributeError, TypeError, ValueError, KeyError, IndexError, RecursionError) as exc:
        raise V2DownstreamCoverageError("REFUSED: supplied v2 coverage context failed validation") from exc


@dataclass(frozen=True, slots=True)
class V2ScopeCoverage:
    """Sealed prefix checkpoint retaining all quarter coverage and rows."""

    _summary_raw: bytes = field(repr=False)
    _quarters: tuple[V2QuarterCoverage, ...] = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_summary: bytes | None = field(default=None, init=False, repr=False, compare=False)
    _factory_quarter_hashes: tuple[str, ...] | None = field(default=None, init=False, repr=False, compare=False)

    def _check(self) -> None:
        if (type(self) is not V2ScopeCoverage or self._token is not _SCOPE_TOKEN
                or type(self._summary_raw) is not bytes or self._summary_raw != self._factory_summary
                or type(self._quarters) is not tuple
                or any(type(quarter) is not V2QuarterCoverage for quarter in self._quarters)
                or tuple(quarter.sha256 for quarter in self._quarters) != self._factory_quarter_hashes):
            _refuse("scope coverage was not built here or its quarter contexts changed")

    def to_payload(self) -> dict[str, object]:
        self._check()
        return json.loads(self._summary_raw)

    @property
    def sha256(self) -> str:
        self._check()
        return hash_bytes(self._summary_raw)

    def pilot_rows(self) -> list[dict[str, object]]:
        self._check()
        return [row for quarter in self._quarters for row in quarter.pilot_rows()]

    def admitted_rows(self) -> list[dict[str, object]]:
        self._check()
        return [row for quarter in self._quarters for row in quarter.admitted_rows()]


def compose_v2_scope_coverage(quarters: tuple[V2QuarterCoverage, ...],
                              expected_periods: tuple[str, ...]) -> V2ScopeCoverage:
    """Compose an explicit frozen-window subset, never widening a source window."""
    try:
        if (type(expected_periods) is not tuple or not 1 <= len(expected_periods) <= len(EXPECTED_PERIODS)
                or any(type(period) is not str or period not in EXPECTED_PERIODS for period in expected_periods)
                or tuple(sorted(set(expected_periods), key=EXPECTED_PERIODS.index)) != expected_periods
                or type(quarters) is not tuple or len(quarters) > len(expected_periods)
                or any(type(quarter) is not V2QuarterCoverage for quarter in quarters)):
            _refuse("scope requires an ordered unique frozen-period subset and exact quarter tuple")
        contexts = [quarter.to_payload() for quarter in quarters]
        loaded_periods = tuple(item["period"] for item in contexts)
        if loaded_periods != expected_periods[:len(quarters)]:
            _refuse("loaded quarters are not the exact expected scope prefix")
        epoch_keys = ("producer_commit", "producer_source_inventory_sha256", "profile_sha256")
        epochs = {tuple(item["preparation_binding"][name] for name in epoch_keys)
                  + (item["policy_version"], item["policy_epoch"], item["evidence_epoch"])
                  for item in contexts}
        if len(epochs) > 1:
            _refuse("producer, profile or policy epochs cannot be silently mixed")
        counts, forms, reasons = Counter(), Counter(), Counter()
        accessions = set()
        for quarter, context in zip(quarters, contexts, strict=True):
            if context["submission_count"] > MAX_QUARTER_FILINGS:
                _refuse("loaded quarter exceeds the v2 scope row cap")
            for row in quarter.pilot_rows():
                if row["accession_number"] in accessions:
                    _refuse("an accession repeats across the supplied scope")
                accessions.add(row["accession_number"])
            for name in ("submission_count", "corroborated_count", "quarantined_count",
                         "short_cik_count", "accession_year_mismatch_count"):
                counts[name] += context[name]
            forms.update(context["form_counts"])
            reasons.update(context["quarantine_reason_counts"])
        if counts["submission_count"] > MAX_TOTAL_FILINGS:
            _refuse("supplied scope exceeds the v2 total filing cap")
        loaded_complete = len(quarters) == len(expected_periods)
        identity_complete = loaded_complete and bool(quarters) and all(
            item["source_identity_complete"] for item in contexts)
        quarter_bindings = [{"period": item["period"], "coverage_sha256": quarter.sha256,
                             "source_identity_sha256": item["source_identity_sha256"]}
                            for quarter, item in zip(quarters, contexts, strict=True)]
        identity_sha = hash_payload({"policy_version": IDENTITY_V2_VERSION,
                                    "expected_periods": list(expected_periods),
                                    "quarters": quarter_bindings}) if identity_complete else None
        summary = {
            "kind": SCOPE_COVERAGE_VERSION, "evidence_epoch": COVERAGE_EVIDENCE_EPOCH,
            "policy_version": IDENTITY_V2_VERSION, "policy_epoch": IDENTITY_V2_EVIDENCE_EPOCH,
            "expected_periods": list(expected_periods), "loaded_periods": list(loaded_periods),
            "missing_periods": list(expected_periods[len(quarters):]),
            "loaded_scope_complete": loaded_complete, "source_identity_complete": identity_complete,
            "source_identity_sha256": identity_sha, "quarter_bindings": quarter_bindings,
            **{name: counts[name] for name in (
                "submission_count", "corroborated_count", "quarantined_count",
                "short_cik_count", "accession_year_mismatch_count")},
            "form_counts": {name: forms[name] for name in _FORMS},
            "quarantine_reason_counts": {name: reasons[name] for name in sorted(_REASONS)},
            "artifact_loading_verified_here": False,
            "authority": _authority(),
        }
        result = V2ScopeCoverage(canonical_json(summary).encode("utf-8"), quarters, _SCOPE_TOKEN)
        object.__setattr__(result, "_factory_summary", result._summary_raw)
        object.__setattr__(result, "_factory_quarter_hashes", tuple(quarter.sha256 for quarter in quarters))
        return result
    except V2DownstreamCoverageError:
        raise
    except (AttributeError, TypeError, ValueError, KeyError, IndexError, RecursionError) as exc:
        raise V2DownstreamCoverageError("REFUSED: supplied v2 scope failed validation") from exc


__all__ = [
    "V2DownstreamCoverageError", "V2PreparationBinding", "V2QuarterCoverage", "V2ScopeCoverage",
    "build_v2_quarter_coverage", "compose_v2_scope_coverage",
]
