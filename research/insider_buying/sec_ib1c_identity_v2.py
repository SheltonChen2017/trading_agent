"""Pure v2 assessment of supplied SUBMISSION and complete-parent identities.

Every source row remains in accounting. A corroborated identity means agreement
between the supplied ZIP row and reparsed header/XML bytes; it does not verify
SEC origin, index membership, publication/PIT timing or source-use rights.
Frozen IB-1C v1, scale and pilot contracts are not changed by this candidate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import LoadedSecBulkParsedSnapshot
from research.insider_buying.sec_complete_submission import (
    SecCompleteSubmissionError, SecCompleteSubmissionProjection,
)
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    SecEdgarAcceptanceSnapshotError, _upstream_submission_filing_date,
)
from research.insider_buying.sec_master_locator_reconciliation import (
    SecMasterLocatorReconciliationError, _target_inventory,
)
from research.insider_buying.sec_zip_corpus_census import (
    SecZipCensusQuarter, SecZipCorpusCensusError,
)


IDENTITY_V2_VERSION = "INSETF-IB1C-SUPPLIED-SOURCE-IDENTITY-v2"
IDENTITY_V2_EVIDENCE_EPOCH = IDENTITY_V2_VERSION + "-candidate"
MAX_CORROBORATING_PARENTS = 256
MAX_CORROBORATING_BYTES = 64 * 1024 * 1024
_CIK = re.compile(r"[0-9]{1,10}\Z")
_TOKEN = object()


class Ib1cIdentityV2Error(ValueError):
    """A malformed source input or altered assessment failed closed."""


def _refuse(reason: str) -> None:
    raise Ib1cIdentityV2Error(f"REFUSED: {reason}")


def _authority() -> dict[str, object]:
    return {
        "source_authenticated": False, "index_membership_verified": False,
        "official_acceptance_verified": False, "publication_time_verified": False,
        "point_in_time_data": False, "rights_verified": False,
        "canonical_evidence": False, "signal_authorized": False,
        "direct_ib1c_ingest_authorized": False, "scale_promotion_authorized": False,
        "pilot_ingest_authorized": False, "qc_authorized": False,
        "backtest_authorized": False, "execution_authorized": False,
        "research_looks": 0, "qc_jobs": 0, "sec_dispatches": 0,
    }


@dataclass(frozen=True, slots=True)
class Ib1cV2IdentityAssessment:
    """Factory-created immutable accounting; each returned payload is a copy."""

    _canonical_bytes: bytes = field(repr=False)
    _digest: str
    _token: object = field(repr=False, compare=False)
    _factory_bytes: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def to_payload(self) -> dict[str, object]:
        if (type(self) is not Ib1cV2IdentityAssessment or self._token is not _TOKEN
                or type(self._canonical_bytes) is not bytes
                or self._canonical_bytes != self._factory_bytes
                or hash_bytes(self._canonical_bytes) != self._digest):
            _refuse("identity assessment was not built here or was altered")
        return json.loads(self._canonical_bytes)

    @property
    def sha256(self) -> str:
        self.to_payload()
        return self._digest


def assess_ib1c_v2_quarter_identity(
    snapshot: LoadedSecBulkParsedSnapshot,
    census_quarter: SecZipCensusQuarter,
    corroborating_parents: tuple[SecCompleteSubmissionProjection, ...] = (),
) -> Ib1cV2IdentityAssessment:
    """Recheck source lineage and retain all six forms, including quarantine.

The complete-parent parser currently supports 4/4-A only. Other ownership
forms are retained with an explicit unsupported-corroboration disposition.
No whole-quarter identity digest is emitted while any row is unresolved.
The 256-parent/64-MiB bound makes this a bounded assessment, not a scale
ingestion route. Read-only artifact loading remains the caller's duty.
"""
    try:
        if type(census_quarter) is not SecZipCensusQuarter:
            _refuse("an exact census quarter is required")
        census_quarter.to_payload()
        # Reuse the existing complete SUBMISSION lineage/count checks. Its
        # Form4 return value is deliberately not this all-six-form denominator.
        _target_inventory(snapshot, census_quarter)
        if (type(corroborating_parents) is not tuple
                or len(corroborating_parents) > MAX_CORROBORATING_PARENTS
                or any(type(parent) is not SecCompleteSubmissionProjection
                       for parent in corroborating_parents)):
            _refuse("corroborating parents must be a bounded exact tuple")
        if sum(len(parent.raw_bytes) for parent in corroborating_parents
               if type(parent.raw_bytes) is bytes) > MAX_CORROBORATING_BYTES:
            _refuse("corroborating parent bytes exceed the bounded assessment")
        parents: dict[str, dict[str, object]] = {}
        for parent in corroborating_parents:
            payload = parent.to_payload()  # Reparse raw header and XML.
            accession = payload["target"]["accession_number"]
            if accession in parents:
                _refuse("duplicate complete-parent corroboration")
            parents[accession] = payload
        identity = snapshot.identity
        table = next(item for item in identity.tables
                     if item.table_name == "SUBMISSION.tsv")
        positions = {name: table.headers.index(name) for name in (
            "ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK",
        )}
        rows = []
        dialect = None
        ordinals = []
        known_accessions: set[str] = set()
        for source in snapshot.rows:
            if source.table_name != "SUBMISSION.tsv":
                continue
            raw_date = source.values[positions["FILING_DATE"]]
            filed, row_dialect = _upstream_submission_filing_date(raw_date)
            if dialect is not None and dialect != row_dialect:
                _refuse("SUBMISSION filing date dialects are mixed")
            dialect = row_dialect
            if (filed.year, (filed.month - 1) // 3 + 1) != (
                identity.year, identity.quarter,
            ):
                _refuse("SUBMISSION filing date is outside its source quarter")
            raw_cik = source.values[positions["ISSUERCIK"]]
            if _CIK.fullmatch(raw_cik) is None or int(raw_cik) == 0:
                _refuse("raw issuer CIK is not 1-to-10 nonzero ASCII digits")
            comparison_cik = raw_cik.zfill(10)
            accession = source.accession_number
            form = source.values[positions["DOCUMENT_TYPE"]]
            known_accessions.add(accession)
            ordinals.append(source.source_record_ordinal)
            mismatch = int(accession[11:13]) != filed.year % 100
            evidence = parents.get(accession)
            reasons = []
            if form not in {"4", "4/A"}:
                reasons.append("unsupported_parent_corroboration_form")
            elif evidence is None:
                reasons.append("complete_parent_corroboration_missing")
            else:
                target = evidence["target"]
                if any(target[name] != expected for name, expected in (
                    ("period", census_quarter.period), ("form_type", form),
                    ("filing_date", filed.isoformat()), ("issuer_cik", comparison_cik),
                )):
                    reasons.append("complete_parent_identity_conflict")
            rows.append({
                "period": census_quarter.period,
                "source_record_ordinal": source.source_record_ordinal,
                "accession_number": accession, "form_type": form,
                "raw_filing_date": raw_date, "filing_date": filed.isoformat(),
                "raw_issuer_cik": raw_cik, "issuer_comparison_key": comparison_cik,
                "short_cik": len(raw_cik) < 10,
                "accession_year_mismatch": mismatch,
                "submission_row_id": source.row_id,
                "raw_archive_sha256": identity.raw_archive_sha256,
                "raw_submission_member_sha256": table.raw_member_sha256,
                "parsed_lineage_hash": identity.lineage_hash,
                "corroboration": None if evidence is None else {
                    "projection_sha256": hash_payload(evidence),
                    "parent_sha256": evidence["raw_parent"]["sha256"],
                    "header_sha256": evidence["children"]["header"]["sha256"],
                    "xml_sha256": evidence["children"]["primary_xml"]["sha256"],
                    "declared_index_sha256": evidence["target"]["quarterly_index_sha256"],
                },
                "disposition": "quarantined" if reasons else "corroborated_noncanonical",
                "quarantine_reasons": reasons,
            })
        if ordinals != list(range(1, len(rows) + 1)):
            _refuse("SUBMISSION ordinals are missing, duplicated or reordered")
        if not set(parents) <= known_accessions:
            _refuse("complete parent is unrelated to the source quarter")
        unresolved = sum(row["disposition"] == "quarantined" for row in rows)
        accounting = hash_payload(rows)
        body = {
            "kind": IDENTITY_V2_VERSION, "evidence_epoch": IDENTITY_V2_EVIDENCE_EPOCH,
            "period": census_quarter.period, "scope": "all_six_ownership_forms",
            "parsed_snapshot_id": identity.snapshot_id,
            "parsed_lineage_hash": identity.lineage_hash,
            "census_quarter_sha256": hash_payload(census_quarter.to_payload()),
            "rows": rows, "submission_count": len(rows),
            "corroborated_count": len(rows) - unresolved, "quarantined_count": unresolved,
            "short_cik_count": sum(row["short_cik"] for row in rows),
            "accession_year_mismatch_count": sum(row["accession_year_mismatch"] for row in rows),
            "accounting_sha256": accounting,
            "whole_quarter_identity_sha256": accounting if rows and not unresolved else None,
            "authority": _authority(),
        }
        raw = canonical_json(body).encode("utf-8")
        result = Ib1cV2IdentityAssessment(raw, hash_bytes(raw), _TOKEN)
        object.__setattr__(result, "_factory_bytes", raw)
        return result
    except Ib1cIdentityV2Error:
        raise
    except (SecMasterLocatorReconciliationError, SecCompleteSubmissionError,
            SecEdgarAcceptanceSnapshotError, SecZipCorpusCensusError,
            AttributeError, IndexError, KeyError, TypeError, ValueError, RecursionError) as exc:
        raise Ib1cIdentityV2Error("REFUSED: supplied identity inputs failed validation") from exc
